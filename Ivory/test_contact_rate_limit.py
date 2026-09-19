from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(IVORY_TRUST_PROXY_HEADERS=False)
class ContactRateLimitTests(TestCase):
    def submission(self, email="client@example.com"):
        return self.client.post(
            reverse("contact"),
            {
                "name": "Test Client",
                "email": email,
                "contact": "+977 9800000000",
                "message": "I would like to discuss an interior design project.",
            },
            REMOTE_ADDR="203.0.113.10",
        )

    @patch("Ivory.views.send_whatsapp_confirmation", return_value=True)
    @patch("Ivory.views.send_contact_confirmation", return_value=1)
    def test_repeated_email_gets_styled_rate_limit_response(self, _email, _whatsapp):
        for _ in range(10):
            self.assertEqual(self.submission().status_code, 302)

        response = self.submission()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "900")
        self.assertContains(
            response,
            "You have sent several enquiries recently.",
            status_code=429,
        )
        self.assertContains(response, "client@example.com", status_code=429)
        self.assertContains(response, "Let's Create Something Beautiful", status_code=429)

    @patch("Ivory.views.send_whatsapp_confirmation", return_value=True)
    @patch("Ivory.views.send_contact_confirmation", return_value=1)
    def test_shared_network_can_submit_with_another_email(self, _email, _whatsapp):
        for _ in range(10):
            self.assertEqual(self.submission().status_code, 302)

        self.assertEqual(self.submission("another-client@example.com").status_code, 302)
