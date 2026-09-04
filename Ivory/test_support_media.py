import io
import json
import shutil
import tempfile
import uuid
import wave
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import SupportConversation
from .support import visitor_key_from_seed
from .support_uploads import validate_upload


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class SupportMediaTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings_override = override_settings(PRIVATE_SUPPORT_ROOT=self.temp.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.visitor = Client(enforce_csrf_checks=True)
        self.visitor.get(reverse("home"))
        session = self.visitor.session
        session["ivory_support_seed"] = "media-test-visitor"
        session.save()
        self.conversation = SupportConversation.objects.create(
            visitor_key=visitor_key_from_seed("media-test-visitor"), visitor_name="Test Visitor")
        self.staff = Client(enforce_csrf_checks=True)
        self.staff.force_login(get_user_model().objects.create_superuser("media-staff", password="test-only"))
        self.staff.get(reverse("support_inbox"))

    def upload(self, client, url, file):
        return client.post(url, {"message": "", "client_message_id": str(uuid.uuid4()), "file": file},
                           HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
                           HTTP_ORIGIN="http://testserver")

    def test_visitor_file_is_in_staff_history_and_private_download(self):
        with patch("Ivory.support._schedule_takeover"):
            response = self.upload(self.visitor, reverse("support_visitor_message"),
                                   SimpleUploadedFile("plan.txt", b"A room plan", "text/plain"))
        self.assertEqual(response.status_code, 200, response.content)
        history = self.staff.get(reverse("support_staff_history", args=[self.conversation.public_id])).json()
        file = history["messages"][-1]["attachments"][0]
        self.assertEqual(file["name"], "plan.txt")
        self.assertEqual(file["type"], "text/plain")
        response = self.staff.get(file["url"])
        self.assertEqual(b"".join(response.streaming_content), b"A room plan")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(Client().get(file["url"]).status_code, 403)

    def test_staff_file_is_in_visitor_history(self):
        response = self.upload(self.staff, reverse("support_staff_message", args=[self.conversation.public_id]),
                               SimpleUploadedFile("proposal.txt", b"Test proposal", "text/plain"))
        self.assertEqual(response.status_code, 200, response.content)
        history = self.visitor.get(reverse("support_visitor_history")).json()
        file = history["messages"][-1]["attachments"][0]
        self.assertEqual(file["name"], "proposal.txt")
        self.assertEqual(b"".join(self.visitor.get(file["url"]).streaming_content), b"Test proposal")

    def test_staff_audio_is_playable_in_visitor_history(self):
        if not shutil.which("ffprobe"):
            self.skipTest("ffprobe is installed in the Docker image")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 8000)
        response = self.upload(self.staff, reverse("support_staff_message", args=[self.conversation.public_id]),
                               SimpleUploadedFile("voice.wav", buffer.getvalue(), "audio/wav"))
        self.assertEqual(response.status_code, 200, response.content)
        file = self.visitor.get(reverse("support_visitor_history")).json()["messages"][-1]["attachments"][0]
        self.assertAlmostEqual(file["duration"], 1)
        response = self.visitor.get(file["url"])
        self.assertEqual(response["Content-Type"], "audio/wav")
        self.assertIn("inline", response["Content-Disposition"])
        self.assertEqual(b"".join(response.streaming_content), buffer.getvalue())

    @patch("Ivory.support_uploads.subprocess.run")
    def test_browser_webm_without_duration_uses_packet_timestamps(self, run):
        run.side_effect = [
            SimpleNamespace(stdout=json.dumps({"streams": [{"codec_type": "audio"}], "format": {}})),
            SimpleNamespace(stdout=json.dumps({"packets": [{"pts_time": "0", "duration_time": ".02"},
                                                          {"pts_time": "1", "duration_time": ".02"}]})),
        ]
        file = validate_upload(SimpleUploadedFile("voice.webm", b"\x1aE\xdf\xa3test", "audio/webm"))
        self.assertAlmostEqual(file["duration"], 1.02)

    def test_disallowed_attachment_and_missing_csrf_are_rejected(self):
        response = self.upload(self.staff, reverse("support_staff_message", args=[self.conversation.public_id]),
                               SimpleUploadedFile("script.html", b"<script></script>", "text/html"))
        self.assertEqual(response.status_code, 400)
        response = self.staff.post(reverse("support_staff_message", args=[self.conversation.public_id]),
                                   {"message": "", "client_message_id": str(uuid.uuid4()),
                                    "file": SimpleUploadedFile("test.txt", b"test", "text/plain")})
        self.assertEqual(response.status_code, 403)
