import os
import runpy
from email import policy
from email.parser import BytesParser
from smtplib import SMTPAuthenticationError
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import ContactMessage, InvoiceCounter, RoomEstimate


@override_settings(
    MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
    IVORY_GMAIL_ADDRESS="ivory-company@example.com",
)
class ContactConfirmationTests(TestCase):
    def setUp(self):
        self.form_data = {
            "name": "Asha Rai",
            "email": "visitor@example.com",
            "contact": "+977 9800000000",
            "message": "Private project details that must stay in the admin.",
        }

    def test_submission_keeps_database_fields_and_original_success_redirect(self):
        response = self.client.post(reverse("contact"), self.form_data)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        enquiry = ContactMessage.objects.get()
        for field, value in self.form_data.items():
            self.assertEqual(enquiry.__dict__[field], value)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(
            "Your message has been successfully submitted.",
            str(list(response.wsgi_request._messages)[0]),
        )

    def test_confirmation_sender_recipient_bodies_and_hosted_logo(self):
        self.client.post(reverse("contact"), self.form_data)
        email = mail.outbox[0]
        self.assertEqual(email.from_email, "Ivory Arvena <ivory-company@example.com>")
        self.assertEqual(email.to, [self.form_data["email"]])
        self.assertEqual(email.reply_to, ["ivory-company@example.com"])
        self.assertEqual(email.cc, [])
        self.assertEqual(email.bcc, [])
        self.assertIn("submitted successfully", email.body)
        self.assertIn("get in touch with you soon", email.body)
        self.assertIn("Regards,\nIvory Arvena Team", email.body)
        self.assertIn("https://ivoryarvena.vercel.app/", email.body)
        self.assertNotIn(self.form_data["message"], email.body)

        # Inspect the MIME actually serialized for sending, not just template text.
        serialized = BytesParser(policy=policy.default).parsebytes(
            email.message(policy=policy.SMTP).as_bytes(policy=policy.SMTP)
        )
        self.assertEqual(serialized.defects, [])
        parts = list(serialized.walk())
        plain = next(part for part in parts if part.get_content_type() == "text/plain")
        html = next(part for part in parts if part.get_content_type() == "text/html")
        self.assertIn("submitted successfully", plain.get_content())
        self.assertIn("get in touch with you soon", html.get_content())
        self.assertNotIn(self.form_data["message"], html.get_content())
        self.assertIn("Regards,<br><strong>Ivory Arvena Team", html.get_content())
        self.assertIn("https://ivoryarvena.vercel.app/static/images/ivoryarvena-email-logo.png", html.get_content())

        # The hosted logo does not create a file attachment in Gmail.
        self.assertEqual(serialized.get_content_type(), "multipart/alternative")
        alternatives = list(serialized.iter_parts())
        self.assertEqual(len(alternatives), 2)
        self.assertEqual(alternatives[0].get_content_type(), "text/plain")
        self.assertEqual(alternatives[1].get_content_type(), "text/html")
        self.assertEqual(email.attachments, [])
        self.assertIn('alt="Ivory Arvena Interior &amp; Design logo"', html.get_content())
        for part in parts:
            self.assertNotEqual(part.get_content_type(), "multipart/mixed")
            self.assertNotEqual(part.get_content_disposition(), "attachment")
            self.assertEqual(part.defects, [])

    def test_headers_are_clear_unique_and_stable_when_serialized_again(self):
        self.client.post(reverse("contact"), self.form_data)
        self.client.post(reverse("contact"), self.form_data)
        first = mail.outbox[0].message(policy=policy.SMTP)
        second = mail.outbox[1].message(policy=policy.SMTP)
        self.assertRegex(first["Message-ID"], r"^<[^<>\s]+@example\.com>$")
        self.assertNotEqual(first["Message-ID"], second["Message-ID"])
        self.assertEqual(first["Message-ID"], mail.outbox[0].message()["Message-ID"])
        self.assertEqual(first["Auto-Submitted"], "auto-generated")
        for header in ("From", "Reply-To", "To", "Subject", "Date", "Message-ID"):
            self.assertEqual(len(first.get_all(header)), 1)
        self.assertEqual(first["From"].addresses[0].addr_spec, "ivory-company@example.com")
        self.assertEqual(first["Reply-To"].addresses[0].addr_spec, "ivory-company@example.com")
        self.assertEqual(first["Subject"], "We've received your enquiry | Ivory Arvena")

    def test_visitor_name_is_html_escaped(self):
        self.form_data["name"] = '<script>alert("x")</script>'
        self.client.post(reverse("contact"), self.form_data)
        html = mail.outbox[0].alternatives[0].content
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_smtp_failure_does_not_lose_enquiry_or_expose_credentials(self):
        with patch(
            "Ivory.emails.EmailMultiAlternatives.send",
            side_effect=SMTPAuthenticationError(535, b"sensitive SMTP response"),
        ), self.assertLogs("Ivory.views", level="ERROR") as logs:
            response = self.client.post(reverse("contact"), self.form_data)
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertIn("SMTPAuthenticationError", logs.output[0])
        self.assertNotIn("sensitive SMTP response", logs.output[0])
        self.assertNotIn(self.form_data["email"], logs.output[0])

    def test_confirmation_does_not_depend_on_a_local_logo_attachment(self):
        with patch("pathlib.Path.read_bytes", side_effect=FileNotFoundError):
            response = self.client.post(reverse("contact"), self.form_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_mailer_reporting_zero_deliveries_is_logged(self):
        with patch("Ivory.emails.EmailMultiAlternatives.send", return_value=0), self.assertLogs(
            "Ivory.views", level="ERROR"
        ) as logs:
            response = self.client.post(reverse("contact"), self.form_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertIn("was not sent", logs.output[0])

    def test_invalid_recipient_is_not_mailed_but_original_save_behavior_remains(self):
        self.form_data["email"] = "visitor@example.com,another@example.com"
        with self.assertLogs("Ivory.views", level="ERROR"):
            response = self.client.post(reverse("contact"), self.form_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_get_does_not_send_email(self):
        self.assertEqual(self.client.get(reverse("contact")).status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(ContactMessage.objects.count(), 0)

    def test_successful_submission_triggers_whatsapp_confirmation(self):
        with patch("Ivory.views.send_whatsapp_confirmation", return_value=True) as send:
            response = self.client.post(reverse("contact"), self.form_data)
        self.assertEqual(response.status_code, 302)
        send.assert_called_once_with(ContactMessage.objects.get())

    def test_whatsapp_failure_does_not_lose_enquiry(self):
        with patch(
            "Ivory.views.send_whatsapp_confirmation", side_effect=TimeoutError
        ), self.assertLogs("Ivory.views", level="ERROR") as logs:
            response = self.client.post(reverse("contact"), self.form_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertIn("WhatsApp confirmation failed", logs.output[0])
        self.assertNotIn(self.form_data["contact"], logs.output[0])

    def test_failed_database_save_does_not_send_email(self):
        with patch("Ivory.views.ContactMessage.objects.create", side_effect=RuntimeError), patch(
            "Ivory.views.send_contact_confirmation"
        ) as send:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse("contact"), self.form_data)
        send.assert_not_called()


class GmailConfigurationTests(SimpleTestCase):
    def load_config(self, environment):
        with patch.dict(os.environ, environment, clear=True):
            return runpy.run_path(str(settings.BASE_DIR / "config/settings.py"))

    def test_default_is_non_delivering_console(self):
        config = self.load_config({})
        self.assertEqual(
            config["MAILERS"]["default"]["BACKEND"],
            "django.core.mail.backends.console.EmailBackend",
        )

    def test_gmail_smtp_uses_env_credentials_and_tls(self):
        config = self.load_config({
            "IVORY_EMAIL_MODE": "smtp",
            "IVORY_GMAIL_ADDRESS": "studio@example.com",
            "IVORY_GMAIL_APP_PASSWORD": "test app password only",
        })
        options = config["MAILERS"]["default"]["OPTIONS"]
        self.assertEqual(options["host"], "smtp.gmail.com")
        self.assertEqual(options["port"], 587)
        self.assertTrue(options["use_tls"])
        self.assertEqual(options["timeout"], 10)
        self.assertEqual(options["username"], config["IVORY_GMAIL_ADDRESS"])
        self.assertEqual(options["password"], "testapppasswordonly")

    def test_smtp_fails_closed_without_credentials_or_valid_sender(self):
        for environment in (
            {"IVORY_EMAIL_MODE": "smtp"},
            {"IVORY_EMAIL_MODE": "smtp", "IVORY_GMAIL_ADDRESS": "studio@example.com"},
            {"IVORY_EMAIL_MODE": "typo"},
            {"IVORY_EMAIL_MODE": "smtp", "IVORY_GMAIL_ADDRESS": "not-an-address", "IVORY_GMAIL_APP_PASSWORD": "test-only"},
        ):
            with self.subTest(environment=environment), self.assertRaises(ImproperlyConfigured):
                self.load_config(environment)


class RoomEstimateTests(TestCase):
    def valid_data(self):
        return {
            "name": "Asha Rai", "phone_number": "+977 9812345678", "room_count": "2", "rate": "120",
            "room_1_name": "Kitchen", "room_2_name": "Living Room",
            "room_1_length": "12", "room_1_width": "10",
            "room_2_length": "15", "room_2_width": "11",
        }

    def test_calculator_saves_breakdown_and_totals(self):
        response = self.client.post(reverse("calculator"), self.valid_data())
        estimate = RoomEstimate.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("estimate_pdf", args=[estimate.public_id]) + "?access="))
        self.assertEqual(estimate.total_area_sq_ft, 285)
        self.assertEqual(estimate.total_amount, 34200)
        self.assertEqual(estimate.phone_number, "+977 9812345678")
        self.assertEqual(len(estimate.rooms), 2)
        self.assertEqual([room["name"] for room in estimate.rooms], ["Kitchen", "Living Room"])

    def test_calculator_requires_phone_and_defaults_rate_to_120(self):
        response = self.client.get(reverse("calculator"))
        self.assertContains(response, 'id="estimate-form" target="_blank"')
        self.assertContains(response, 'name="rate" type="number" min="90" max="180" step="0.01" required value="120"')
        data = self.valid_data()
        data["phone_number"] = ""
        response = self.client.post(reverse("calculator"), data)
        self.assertContains(response, "Please enter your phone number.")
        self.assertEqual(RoomEstimate.objects.count(), 0)

    def test_rate_must_be_between_90_and_180(self):
        for rate in ("89.99", "180.01"):
            data = self.valid_data(); data["rate"] = rate
            with self.subTest(rate=rate):
                response = self.client.post(reverse("calculator"), data)
                self.assertContains(response, "between NPR 90 and NPR 180")
        self.assertEqual(RoomEstimate.objects.count(), 0)

    def test_room_name_is_required(self):
        data = self.valid_data()
        data["room_1_name"] = ""
        response = self.client.post(reverse("calculator"), data)
        self.assertContains(response, "Please enter a name for room 1.")
        self.assertEqual(RoomEstimate.objects.count(), 0)

    def test_generated_invoice_is_downloadable_pdf(self):
        created = self.client.post(reverse("calculator"), self.valid_data())
        estimate = RoomEstimate.objects.get()
        pdf_path = created["Location"]
        from reportlab.graphics.barcode.qr import QrCodeWidget
        with patch("reportlab.graphics.barcode.qr.QrCodeWidget", wraps=QrCodeWidget) as qr_widget:
            response = self.client.get(pdf_path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(estimate.invoice_number, response["Content-Disposition"])
        self.assertTrue(response["Content-Disposition"].startswith("inline;"))
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")
        self.assertEqual(response["Cache-Control"], "private, no-store, max-age=0")
        qr_widget.assert_called_once_with(f"http://testserver{pdf_path}")

    def test_invoice_requires_a_valid_signed_link(self):
        created = self.client.post(reverse("calculator"), self.valid_data())
        estimate = RoomEstimate.objects.get()
        unsigned = reverse("estimate_pdf", args=[estimate.public_id])
        self.assertEqual(self.client.get(unsigned).status_code, 403)
        self.assertEqual(self.client.get(created["Location"]).status_code, 200)

    def test_invoice_numbers_use_the_dedicated_counter(self):
        self.client.post(reverse("calculator"), self.valid_data())
        first = RoomEstimate.objects.get()
        self.assertEqual(first.invoice_number, f"IVY-{timezone.localdate().year}-00001")

        first.delete()
        self.client.post(reverse("calculator"), self.valid_data())
        second = RoomEstimate.objects.get()
        self.assertEqual(second.invoice_number, f"IVY-{timezone.localdate().year}-00002")

    def test_superuser_can_delete_test_estimates_and_reset_next_invoice(self):
        self.client.post(reverse("calculator"), self.valid_data())
        self.client.post(reverse("calculator"), self.valid_data())
        user = User.objects.create_superuser("owner", "owner@example.com", "password")
        self.client.force_login(user)

        reset_url = reverse("admin:roomestimate_reset_invoice_numbering")
        response = self.client.post(reset_url)

        self.assertRedirects(response, reverse("admin:Ivory_roomestimate_changelist"))
        self.assertEqual(RoomEstimate.objects.count(), 0)
        self.assertEqual(InvoiceCounter.objects.get(year=timezone.localdate().year).last_number, 0)

        self.client.logout()
        self.client.post(reverse("calculator"), self.valid_data())
        estimate = RoomEstimate.objects.get()
        self.assertEqual(estimate.invoice_number, f"IVY-{timezone.localdate().year}-00001")


class SearchVisibilityTests(TestCase):
    def test_default_favicon_url_uses_our_brand_icon(self):
        response = self.client.get(reverse("favicon"))
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "/static/images/ivory-arvena-favicon-v2.png")

    def test_google_search_console_verification_file(self):
        response = self.client.get(reverse("google_site_verification"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.content,
            b"google-site-verification: google5995f313dfce11d4.html",
        )

    def test_homepage_identifies_official_brand_and_social_profiles(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Ivory Arvena Interior &amp; Design | Interior Designer in Kathmandu, Nepal")
        self.assertContains(response, '"alternateName":["Ivory Arvena","ivoryarvena"]')
        self.assertContains(response, '"legalName":"Ivory Arvena Interior & Design"')
        self.assertContains(response, "ivorydesign2083@gmail.com")
        self.assertContains(response, '"@type":"WebSite"')
        self.assertContains(response, 'images/ivory-arvena-favicon-v2.png')
        self.assertContains(response, "https://www.facebook.com/profile.php?id=61594457698243")
        self.assertContains(response, "https://www.instagram.com/ivoryarvena/")

    @override_settings(ALLOWED_HOSTS=["testserver", "ivory-design.vercel.app"])
    def test_legacy_vercel_domain_redirects_to_official_brand_domain(self):
        response = self.client.get("/about/?source=google", HTTP_HOST="ivory-design.vercel.app")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response["Location"],
            "https://ivoryarvena.vercel.app/about/?source=google",
        )

    def test_sitemap_and_robots_are_public(self):
        self.assertContains(self.client.get(reverse("robots_txt")), "Sitemap: http://testserver/sitemap.xml")
        sitemap = self.client.get(reverse("sitemap"))
        self.assertEqual(sitemap.status_code, 200)
        self.assertContains(sitemap, "http://testserver/projects/")
