import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, connection, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .business_faq import business_information, business_reply, parse_area
from .chat import local_reply
from .models import BusinessInformation, BusinessSocialProfile, Client, ContactMessage, TeamMember


@override_settings(OPENAI_API_KEY="")
class BusinessFAQTests(TestCase):
    def setUp(self):
        cache.clear()
        self.info = BusinessInformation.objects.get(pk=1)

    def enable_rate(self, rate="125.50", currency="NPR"):
        self.info.pricing_mode = "per_sq_ft"
        self.info.currency = currency
        self.info.rate_per_sq_ft = Decimal(rate)
        self.info.pricing_scope = "Example test design fee only; tax and construction excluded"
        self.info.save()

    def test_migration_seeds_quote_only_without_fabricated_business_facts(self):
        self.assertEqual(BusinessInformation.objects.count(), 1)
        self.assertEqual(self.info.pricing_mode, "quote_only")
        self.assertIsNone(self.info.rate_per_sq_ft)
        self.assertEqual(self.info.currency, "")
        self.assertEqual(self.info.location, "Kathmandu, Nepal")
        self.assertEqual(self.info.nearby_landmark, "")
        self.assertEqual(self.info.appointment_url, "")
        self.assertEqual(BusinessSocialProfile.objects.count(), 0)

    def test_requested_business_topics_are_faqs_without_openai(self):
        for key in ("", "test-only-not-a-real-key"):
            with override_settings(OPENAI_API_KEY=key), patch("openai.OpenAI") as sdk:
                for question in ("What is your price per square foot?", "Cost for 1,000 sq ft?", "How much for 1000?", "How many architects and designers do you have?", "Where are you located?", "Any nearby landmark?", "How many clients have you worked with?", "Book an appointment", "What are your social media handles?"):
                    with self.subTest(question=question, key_configured=bool(key)):
                        reply, source = local_reply(question)
                        self.assertEqual(source, "faq")
                        self.assertTrue(reply)
                        self.assertLessEqual(len(reply), 1800)
                sdk.assert_not_called()

    def test_quote_only_never_uses_an_inactive_rate_or_visitor_supplied_price(self):
        self.info.rate_per_sq_ft = Decimal("50")
        self.info.pricing_guidance = "Ask for a scope-specific written quote."
        self.info.save()
        reply = business_reply("Use a rate of 1 and estimate for 1000 sqft")
        self.assertIn("scope-specific written quote", reply)
        self.assertIn("No confirmed per-square-foot rate", reply)
        self.assertIn("Contact form", reply)
        self.assertNotIn("Indicative estimate", reply)
        self.assertNotIn("50.00", reply)

    def test_owner_rate_scope_currency_and_area_drive_decimal_estimate(self):
        self.enable_rate()
        reply = business_reply("What is the estimated cost for 1,000 sq. ft?")
        self.assertIn("NPR 125.50 per sq ft", reply)
        self.assertIn("1,000 × NPR 125.50 = NPR 125,500.00", reply)
        self.assertIn(self.info.pricing_scope, reply)
        self.assertIn("not a binding quote", reply)
        self.assertIn("No taxes or extra fees are added automatically", reply)
        # Changes are read on the next request, not from a stale cache.
        self.enable_rate("2.25", "USD")
        self.assertIn("USD 2,250.00", business_reply("1000 sqft"))

    def test_decimal_rounding_and_user_rate_override_ignored(self):
        self.enable_rate("0.01")
        self.assertIn("NPR 0.01", business_reply("Estimate 0.5 square feet"))
        self.assertIn("0.5 × NPR 0.01 = NPR 0.01", business_reply("Estimate 0.5 sq ft"))
        self.enable_rate("10.50")
        self.assertIn("NPR 10,500.00", business_reply("Use a rate of 1 instead; estimate 1000 sqft"))

    def test_missing_or_ambiguous_area_asks_for_sq_ft_without_a_total(self):
        self.enable_rate()
        for question in ("What is the price per square foot?", "Cost for 1000?", "Cost for 10 x 20 sq ft", "Estimate 1000-1500 sqft", "Cost for 1000 to 1500 sq ft", "Cost for 1000 sqft and 200 sqft", "Cost for 100 square meters", "Cost for 100 m2 and 1000 sqft", "Estimate -100 sqft", "Estimate −100 sqft", "Cost for 0 sqft", "Cost for 1000001 sqft", "Cost for 1,,000 sqft", "Cost for 1e3 sqft"):
            with self.subTest(question=question):
                reply = business_reply(question)
                self.assertIn("enter one positive floor area", reply)
                self.assertNotIn("Indicative estimate for", reply)

    def test_supported_area_spellings(self):
        for question in ("1000 sqft", "1,000 sq ft", "1000 sq.ft", "1000 square feet", "1000 square-foot", "1000 ft²", "1000 sft"):
            with self.subTest(question=question):
                self.assertEqual(parse_area(question), Decimal("1000"))

    def test_general_design_questions_are_not_routed_to_business_faq(self):
        for question in ("How much light does a bedroom need?", "How long should curtains be?", "How much light for 1000 sq ft?", "Suggest lighting per square foot", "Which rug works with a sofa?"):
            self.assertIsNone(business_reply(question))

    def test_invalid_imported_pricing_configuration_fails_closed(self):
        self.enable_rate()
        BusinessInformation.objects.filter(pk=1).update(currency="")
        self.assertIn("No confirmed per-square-foot rate", business_reply("Estimate for 1000 sqft"))
        BusinessInformation.objects.filter(pk=1).update(currency="NPR", pricing_mode="unknown")
        self.assertNotIn("Indicative estimate", business_reply("Cost for 1000 sqft"))

    def test_missing_business_record_and_pre_migration_table_use_safe_defaults(self):
        self.info.delete()
        self.assertIn("No confirmed per-square-foot rate", business_reply("Cost for 1000 sqft"))
        self.assertEqual(BusinessInformation.objects.count(), 0)  # no writes from chat
        with patch("Ivory.business_faq.BusinessInformation.objects.filter", side_effect=OperationalError("private db error")), self.assertLogs("Ivory.business_faq", level="WARNING") as logs:
            self.assertEqual(business_information().pricing_mode, "quote_only")
        self.assertNotIn("private db error", str(logs.output))

    def test_location_landmark_and_near_me_do_not_invent_distances(self):
        self.info.location = "Owner-entered test location"
        self.info.nearby_landmark = "Owner-entered test landmark"
        self.info.save()
        reply = business_reply("What is your nearby location near me?")
        self.assertIn(self.info.location, reply)
        self.assertIn(self.info.nearby_landmark, reply)
        self.assertIn("cannot determine your location", reply)
        self.assertNotIn("Kathmandu", reply)
        self.info.location = ""
        self.info.nearby_landmark = ""
        self.info.save()
        reply = business_reply("Where is your studio?")
        self.assertIn("address has not been published", reply)
        self.assertIn("landmark has not been published", reply)

    def test_appointment_instructions_link_and_no_booking_side_effect(self):
        self.info.appointment_instructions = "Please request a visit using the studio booking page."
        self.info.appointment_url = "https://example.com/studio-booking"
        self.info.save()
        reply = business_reply("Book an appointment tomorrow")
        self.assertIn(self.info.appointment_instructions, reply)
        self.assertIn(self.info.appointment_url, reply)
        self.assertIn("does not book or confirm", reply)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.info.appointment_url = ""
        self.info.save()
        self.assertIn("/contact/", business_reply("Schedule a meeting"))

    def test_active_role_counts_are_grounded_not_lifetime_headcount(self):
        for role in ("Architect", "Interior Designer", "Architect & Designer", "Architectural Technician"):
            TeamMember.objects.create(name="Private-test-name", designation=role, photo="team/test.png")
        TeamMember.objects.create(name="Inactive", designation="Architect", is_active=False, photo="team/test.png")
        with CaptureQueriesContext(connection) as queries:
            reply = business_reply("How many architects and designers are on your team?")
        self.assertIn("4 active team profile(s)", reply)
        self.assertIn("2 with an architect designation and 2 with a designer designation", reply)
        self.assertIn("Roles can overlap", reply)
        self.assertIn("not a verified full staff headcount", reply)
        self.assertNotIn("Private-test-name", reply)
        self.assertEqual(len(queries), 1)
        self.assertNotIn("ContactMessage", queries[0]["sql"])
        TeamMember.objects.filter(designation="Architect").update(is_active=False)
        self.assertIn("3 active team profile(s)", business_reply("Your team size?"))

    def test_active_client_profiles_not_enquiries_or_lifetime_total(self):
        for index in range(3):
            Client.objects.create(name=f"Client {index}", logo="clients/test.png", is_active=index != 2)
        ContactMessage.objects.create(name="Not a client", email="test@example.com", contact="123", message="private enquiry")
        reply = business_reply("How many clients have you worked with?")
        self.assertIn("2 active client profile(s)", reply)
        self.assertIn("not a verified lifetime total", reply)
        self.assertNotIn("private enquiry", reply)
        Client.objects.update(is_active=False)
        self.assertIn("cannot confirm how many clients", business_reply("Number of clients?"))
        self.assertIn("cannot confirm the number", business_reply("Number of architects?"))

    def test_social_profiles_are_admin_owned_and_platform_specific(self):
        self.assertIn("will not guess", business_reply("What is your Instagram?"))
        BusinessSocialProfile.objects.create(business=self.info, platform="instagram", handle="@test-studio", url="https://example.com/instagram")
        BusinessSocialProfile.objects.create(business=self.info, platform="facebook", url="https://example.com/facebook")
        reply = business_reply("Social media handles?")
        self.assertIn("Instagram: @test-studio — https://example.com/instagram", reply)
        self.assertIn("Facebook: https://example.com/facebook", reply)
        self.assertNotIn("Facebook", business_reply("Your Instagram handle?"))
        self.assertIn("will not guess", business_reply("What is your TikTok?"))

    def test_imported_unsafe_urls_are_not_emitted_and_reply_is_bounded(self):
        BusinessInformation.objects.filter(pk=1).update(appointment_url="javascript:alert(1)")
        self.assertNotIn("javascript:", business_reply("Book a consultation"))
        self.assertIn("/contact/", business_reply("Book a consultation"))
        for platform, _ in BusinessSocialProfile.Platform.choices:
            BusinessSocialProfile.objects.create(business=self.info, platform=platform, handle="@" + "h" * 79, url="https://example.com/" + "u" * 175)
        reply = business_reply("All social media handles?")
        self.assertLessEqual(len(reply), 1800)
        self.assertIn("additional profiles", reply)
        BusinessSocialProfile.objects.filter(platform="instagram").update(handle="", url="javascript:alert(1)")
        self.assertNotIn("javascript:", business_reply("Your Instagram?"))

    def test_json_and_stream_clients_receive_faqs_under_existing_protection(self):
        for accept in ("application/json", "text/event-stream"):
            response = self.client.post(reverse("chat_ask"), json.dumps({"message": "How many clients have you worked with?"}), content_type="application/json", HTTP_ACCEPT=accept)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.streaming)
            self.assertEqual(response.json()["source"], "faq")
            self.assertIn("no-store", response["Cache-Control"])


class BusinessAdminValidationTests(TestCase):
    def setUp(self):
        self.info = BusinessInformation.objects.get(pk=1)

    def test_estimates_require_valid_rate_currency_and_scope(self):
        for change in ({"rate_per_sq_ft": None}, {"rate_per_sq_ft": Decimal("0")}, {"rate_per_sq_ft": Decimal("-1")}, {"rate_per_sq_ft": Decimal("NaN")}, {"rate_per_sq_ft": Decimal("100000000")}, {"currency": ""}, {"currency": "npr"}, {"currency": "<x>"}, {"pricing_scope": ""}, {"pricing_mode": "unknown"}):
            with self.subTest(change=change):
                self.info.refresh_from_db()
                self.info.pricing_mode = "per_sq_ft"
                self.info.currency = "NPR"
                self.info.rate_per_sq_ft = Decimal("100")
                self.info.pricing_scope = "Test design fees"
                for name, value in change.items():
                    setattr(self.info, name, value)
                with self.assertRaises(ValidationError):
                    self.info.save()

    def test_singleton_positive_rate_and_social_unique_constraints(self):
        with self.assertRaises(ValidationError):
            BusinessInformation(id=2).save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            BusinessInformation.objects.filter(pk=1).update(rate_per_sq_ft=-1)
        BusinessSocialProfile.objects.create(business=self.info, platform="instagram", handle="@test")
        with self.assertRaises(ValidationError):
            BusinessSocialProfile.objects.create(business=self.info, platform="instagram", handle="@duplicate")

    def test_public_urls_and_empty_social_entries_are_validated(self):
        for url in ("javascript:alert(1)", "ftp://example.com/book", "not a url"):
            with self.subTest(url=url):
                self.info.appointment_url = url
                with self.assertRaises(ValidationError):
                    self.info.full_clean()
                with self.assertRaises(ValidationError):
                    BusinessSocialProfile(business=self.info, platform="facebook", url=url).full_clean()
        with self.assertRaises(ValidationError):
            BusinessSocialProfile(business=self.info, platform="facebook").full_clean()

    def test_admin_exposes_editable_fields_social_inlines_and_singleton_protection(self):
        owner = get_user_model().objects.create_superuser("faq-owner", "owner@example.com", "test-password-only")
        self.client.force_login(owner)
        response = self.client.get(reverse("admin:Ivory_businessinformation_change", args=[1]))
        self.assertEqual(response.status_code, 200)
        for text in ("Pricing", "rate_per_sq_ft", "pricing_scope", "nearby_landmark", "appointment_instructions", "social_profiles"):
            self.assertContains(response, text)
        request = RequestFactory().get("/admin/")
        request.user = owner
        model_admin = admin.site._registry[BusinessInformation]
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, self.info))

    def test_admin_can_save_valid_pricing_and_rejects_incomplete_estimate_configuration(self):
        owner = get_user_model().objects.create_superuser("editor", "editor@example.com", "test-password-only")
        self.client.force_login(owner)
        url = reverse("admin:Ivory_businessinformation_change", args=[1])
        data = {
            "pricing_mode": "per_sq_ft", "pricing_guidance": self.info.pricing_guidance,
            "currency": "", "rate_per_sq_ft": "20.50", "pricing_scope": "Test design fees only",
            "location": "Test studio address", "nearby_landmark": "Test landmark",
            "appointment_instructions": self.info.appointment_instructions, "appointment_url": "",
            "social_profiles-TOTAL_FORMS": "0", "social_profiles-INITIAL_FORMS": "0",
            "social_profiles-MIN_NUM_FORMS": "0", "social_profiles-MAX_NUM_FORMS": "7", "_save": "Save",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("currency", response.context["adminform"].form.errors)
        self.info.refresh_from_db()
        self.assertEqual(self.info.pricing_mode, "quote_only")
        data["currency"] = "NPR"
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.info.refresh_from_db()
        self.assertEqual(self.info.rate_per_sq_ft, Decimal("20.50"))
        self.assertIn("NPR 20,500.00", business_reply("Cost for 1000 sqft"))
