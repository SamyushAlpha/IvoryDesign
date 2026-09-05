from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .storage import VercelBlobStorage


class VercelBlobStorageTests(SimpleTestCase):
    def setUp(self):
        self.storage = VercelBlobStorage()

    def test_upload_returns_public_blob_url(self):
        result = {"url": "https://example.public.blob.vercel-storage.com/projects/room-abc.jpg"}
        upload = SimpleUploadedFile("room.jpg", b"image-bytes", content_type="image/jpeg")
        with patch("Ivory.storage.BlobClient") as client_class:
            client_class.return_value.__enter__.return_value.put.return_value = result
            saved_name = self.storage.save("projects/room.jpg", upload)

        self.assertEqual(saved_name, result["url"])
        client_class.return_value.__enter__.return_value.put.assert_called_once_with(
            "projects/room.jpg",
            b"image-bytes",
            access="public",
            content_type="image/jpeg",
            add_random_suffix=True,
        )

    def test_url_supports_new_blob_and_existing_bundled_media(self):
        blob_url = "https://example.public.blob.vercel-storage.com/projects/room.jpg"
        self.assertEqual(self.storage.url(blob_url), blob_url)
        self.assertEqual(self.storage.url("projects/old room.jpg"), "/media/projects/old%20room.jpg")
