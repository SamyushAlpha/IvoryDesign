"""Conservative private uploads. Signature checks are not malware scanning."""
import io
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".pdf": "application/pdf", ".txt": "text/plain", ".webm": "audio/webm",
         ".ogg": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4"}


def validate_upload(upload):
    if not upload.size or upload.size > settings.IVORY_SUPPORT_UPLOAD_BYTES:
        raise ValidationError("Choose a non-empty file no larger than the upload limit (5 MB by default).")
    name = re.sub(r"[^\w. -]", "_", Path(upload.name.replace("\\", "/")).name)[:120]
    ext = Path(name).suffix.lower()
    if ext not in TYPES:
        raise ValidationError("Allowed files: PNG, JPG, PDF, TXT, or audio WEBM, OGG, MP3, WAV, M4A.")
    mime = TYPES[ext]
    claimed = (upload.content_type or "").split(";", 1)[0].lower()
    aliases = {"audio/x-wav": "audio/wav", "audio/x-m4a": "audio/mp4", "application/ogg": "audio/ogg"}
    if aliases.get(claimed, claimed) not in {mime, "application/octet-stream", ""}:
        raise ValidationError("The file type does not match its extension.")
    data = upload.read(settings.IVORY_SUPPORT_UPLOAD_BYTES + 1)
    if len(data) > settings.IVORY_SUPPORT_UPLOAD_BYTES:
        raise ValidationError("File is too large.")
    duration = None
    if mime.startswith("image/"):
        try:
            with Image.open(io.BytesIO(data)) as picture:
                if picture.format not in {"PNG", "JPEG"} or picture.width * picture.height > 16000000:
                    raise ValidationError("Use a PNG/JPG image under 16 megapixels.")
                if (mime == "image/png") != (picture.format == "PNG"):
                    raise ValidationError("Image signature does not match its extension.")
                picture.load()
                output = io.BytesIO()
                picture.convert("RGB").save(output, format="PNG" if mime == "image/png" else "JPEG")
                data = output.getvalue()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValidationError("The image could not be validated.")
    elif mime == "application/pdf":
        if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
            raise ValidationError("The PDF signature is invalid.")
    elif mime == "text/plain":
        try:
            value = data.decode("utf-8")
            if "\x00" in value:
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            raise ValidationError("Text files must contain UTF-8 text.")
    else:
        signatures = {
            ".webm": data.startswith(b"\x1aE\xdf\xa3"), ".ogg": data.startswith(b"OggS"),
            ".mp3": data.startswith(b"ID3") or data[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"},
            ".wav": data.startswith(b"RIFF") and data[8:12] == b"WAVE",
            ".m4a": data[4:8] == b"ftyp",
        }
        if not signatures.get(ext):
            raise ValidationError("The audio signature is invalid.")
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp:
                path = temp.name
                temp.write(data)
            result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                                     "-of", "json", path], capture_output=True, timeout=10, check=True)
            metadata = json.loads(result.stdout)
            raw_duration = metadata.get("format", {}).get("duration")
            if raw_duration in (None, "N/A"):
                # MediaRecorder's live WebM containers commonly omit Duration.
                # Inspect actual packet timestamps instead of trusting the browser.
                packets_result = subprocess.run([
                    "ffprobe", "-v", "error", "-show_entries", "packet=pts_time,duration_time",
                    "-of", "json", path,
                ], capture_output=True, timeout=10, check=True)
                packets = json.loads(packets_result.stdout).get("packets", [])
                starts = [float(p["pts_time"]) for p in packets]
                ends = [float(p["pts_time"]) + float(p.get("duration_time", 0)) for p in packets]
                duration = max(ends) - min(starts)
            else:
                duration = float(raw_duration)
            streams = metadata.get("streams", [])
            if not streams or any(s.get("codec_type") != "audio" for s in streams):
                raise ValueError
            if not 0 < duration <= settings.IVORY_SUPPORT_AUDIO_SECONDS:
                raise ValueError
        except (OSError, ValueError, KeyError, subprocess.SubprocessError):
            raise ValidationError("Audio must be valid, audio-only, and at most 120 seconds. Audio validation requires ffprobe.")
        finally:
            if path:
                os.unlink(path)
    if len(data) > settings.IVORY_SUPPORT_UPLOAD_BYTES:
        raise ValidationError("Processed file exceeds the upload limit.")
    return {"file": ContentFile(data, name=name), "filename": name, "content_type": mime, "size": len(data), "duration": duration}
