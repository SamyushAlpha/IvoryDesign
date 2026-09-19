from django.conf import settings
from django.test import SimpleTestCase


class AdminNotificationScriptTests(SimpleTestCase):
    def test_admin_notifications_use_current_support_route_in_background(self):
        script = (settings.BASE_DIR / "static" / "admin" / "support-notifications.js").read_text()

        self.assertIn('location.pathname.startsWith("/my-lo/")', script)
        self.assertIn('fetch("/my-lo/support/api/conversations/', script)
        self.assertIn('location.href = "/my-lo/support/"', script)
        self.assertNotIn("if (document.hidden) return", script)
        self.assertNotIn("/admin/support/", script)
