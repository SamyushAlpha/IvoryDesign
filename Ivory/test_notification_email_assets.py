from email import policy

from django.conf import settings
from django.core import mail
from django.test import SimpleTestCase, override_settings

from .emails import send_contact_confirmation


@override_settings(
    MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}},
    IVORY_GMAIL_ADDRESS="ivory-company@example.com",
)
class ConfirmationLogoTests(SimpleTestCase):
    def test_logo_is_embedded_inline_and_referenced_by_content_id(self):
        enquiry = type("Enquiry", (), {"name": "Asha", "email": "visitor@example.com"})()

        self.assertEqual(send_contact_confirmation(enquiry), 1)
        message = mail.outbox[0].message(policy=policy.default)
        parts = list(message.walk())
        html = next(part for part in parts if part.get_content_type() == "text/html")
        logo = next(part for part in parts if part.get_content_type() == "image/png")

        self.assertEqual(message.get_content_subtype(), "related")
        self.assertEqual(logo.get_content_disposition(), "inline")
        self.assertEqual(logo.get_filename(), "ivory-arvena-logo.png")
        self.assertIn("ivory-arvena-logo", logo["Content-ID"])
        self.assertIn(f"cid:{logo['Content-ID'][1:-1]}", html.get_content())
        self.assertGreater(len(logo.get_payload(decode=True)), 1000)


class AdminNotificationScriptTests(SimpleTestCase):
    def test_admin_notifications_use_current_support_route_in_background(self):
        script = (settings.BASE_DIR / "static" / "admin" / "support-notifications.js").read_text()

        self.assertIn('location.pathname.startsWith("/my-lo/")', script)
        self.assertIn('fetch("/my-lo/support/api/conversations/', script)
        self.assertIn('location.href = "/my-lo/support/"', script)
        self.assertNotIn("if (document.hidden) return", script)
        self.assertNotIn("/admin/support/", script)
