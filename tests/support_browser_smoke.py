"""Disposable, loopback-only UI fixture. Never run as a deployment server.

Run with: python tests/support_browser_smoke.py
Uses a temporary database/files and synthetic staff login smoke / smoke-only.
No company data, real credentials, email, AI requests or background tasks.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
from django.conf import settings

temporary = tempfile.TemporaryDirectory(prefix="ivory-support-smoke-")
settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(Path(temporary.name) / "test.sqlite3")}}
settings.PRIVATE_SUPPORT_ROOT = Path(temporary.name) / "files"
settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
settings.OPENAI_API_KEY = ""
settings.DEBUG = True
settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
settings.CSRF_TRUSTED_ORIGINS = ["http://localhost:8767"]

import django
django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from Ivory.models import SupportConversation
from Ivory.support import add_visitor_message
from Ivory import support
from Ivory.support_uploads import validate_upload
import uuid

support._schedule_takeover = lambda *args: None
call_command("migrate", verbosity=0)
get_user_model().objects.create_superuser("smoke", password="smoke-only")
conversation = SupportConversation.objects.create(visitor_key="synthetic-smoke-only", visitor_name="Synthetic Visitor")
add_visitor_message(conversation.visitor_key, "Shared a file.", uuid.uuid4(),
                    validate_upload(SimpleUploadedFile("sample-plan.txt", b"Synthetic room plan", "text/plain")))
try:
    # Container use requires an explicit opt-in and a loopback-only port mapping.
    bind = "0.0.0.0:8767" if "--container" in sys.argv else "127.0.0.1:8767"
    call_command("runserver", bind, use_reloader=False)
finally:
    temporary.cleanup()
