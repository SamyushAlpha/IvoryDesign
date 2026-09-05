import mimetypes
from urllib.parse import quote
from urllib.request import urlopen

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from vercel.blob import BlobClient


@deconstructible
class VercelBlobStorage(Storage):
    """Persistent public storage for website images uploaded on Vercel."""

    def _save(self, name, content):
        pathname = name.lstrip("/")
        content_type = getattr(content, "content_type", None)
        if not content_type:
            content_type = mimetypes.guess_type(pathname)[0] or "application/octet-stream"
        if hasattr(content, "seek"):
            content.seek(0)
        data = content.read()
        with BlobClient() as client:
            result = client.put(
                pathname,
                data,
                access="public",
                content_type=content_type,
                add_random_suffix=True,
            )
        return result.url

    def _open(self, name, mode="rb"):
        if not name.startswith(("https://", "http://")):
            return super()._open(name, mode)
        with urlopen(name, timeout=30) as response:
            return ContentFile(response.read(), name=name.rsplit("/", 1)[-1])

    def delete(self, name):
        # Old assets remain available if an admin replaces an image. This avoids
        # deleting an asset still referenced by cached pages or email content.
        return None

    def exists(self, name):
        return False

    def url(self, name):
        if name.startswith(("https://", "http://")):
            return name
        return f"/media/{quote(name.lstrip('/'), safe='/')}"
