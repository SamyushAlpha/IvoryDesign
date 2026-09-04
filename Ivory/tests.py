import os
import runpy
from email import policy
from email.parser import BytesParser
from smtplib import SMTPAuthenticationError
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .models import ContactMessage


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

    def test_confirmation_sender_recipient_bodies_and_inline_logo(self):
        self.client.post(reverse("contact"), self.form_data)
        email = mail.outbox[0]
        self.assertEqual(email.from_email, "Ivory Design <ivory-company@example.com>")
        self.assertEqual(email.to, [self.form_data["email"]])
        self.assertEqual(email.reply_to, ["ivory-company@example.com"])
        self.assertEqual(email.cc, [])
        self.assertEqual(email.bcc, [])
        self.assertIn("submitted successfully", email.body)
        self.assertIn("get in touch with you soon", email.body)
        self.assertIn("Regards,\nIvory Design Team", email.body)
        self.assertNotIn(self.form_data["message"], email.body)

        # Inspect the MIME actually serialized for sending, not just template text.
        serialized = BytesParser(policy=policy.default).parsebytes(
            email.message(policy=policy.SMTP).as_bytes(policy=policy.SMTP)
        )
        self.assertEqual(serialized.defects, [])
        parts = list(serialized.walk())
        plain = next(part for part in parts if part.get_content_type() == "text/plain")
        html = next(part for part in parts if part.get_content_type() == "text/html")
        logo = next(part for part in parts if part.get_content_type() == "image/png")
        self.assertIn("submitted successfully", plain.get_content())
        self.assertIn("get in touch with you soon", html.get_content())
        self.assertNotIn(self.form_data["message"], html.get_content())
        self.assertIn("Regards,<br><strong>Ivory Design Team", html.get_content())
        self.assertIn('cid:' + logo["Content-ID"].strip("<>"), html.get_content())
        self.assertEqual(logo.get_content_disposition(), "inline")
        self.assertEqual(
            logo.get_payload(decode=True),
            (settings.BASE_DIR / "static/images/b.png").read_bytes(),
        )

        # The plaintext is a sibling of the HTML+logo related group. There is
        # no multipart/mixed wrapper, named file or attachment disposition.
        self.assertEqual(serialized.get_content_type(), "multipart/alternative")
        alternatives = list(serialized.iter_parts())
        self.assertEqual(len(alternatives), 2)
        self.assertEqual(alternatives[0].get_content_type(), "text/plain")
        related = alternatives[1]
        self.assertEqual(related.get_content_type(), "multipart/related")
        self.assertEqual(related.get_param("type"), "text/html")
        self.assertEqual(related.get_param("start"), html["Content-ID"])
        self.assertEqual(list(related.iter_parts()), [html, logo])
        self.assertEqual(logo["Content-Transfer-Encoding"], "base64")
        self.assertEqual(logo["Content-Disposition"], "inline")
        self.assertIsNone(logo.get_filename())
        self.assertIsNone(logo.get_param("name"))
        self.assertEqual(email.attachments, [])
        self.assertIn('alt="Ivory Design logo"', html.get_content())
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
        self.assertEqual(first["Subject"], "We've received your enquiry | Ivory Design")

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

    def test_missing_logo_does_not_lose_enquiry(self):
        with patch("pathlib.Path.read_bytes", side_effect=FileNotFoundError), self.assertLogs(
            "Ivory.views", level="ERROR"
        ):
            response = self.client.post(reverse("contact"), self.form_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)

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
