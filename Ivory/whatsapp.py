"""Transactional WhatsApp confirmation delivery through Meta Cloud API."""

import json
import re
from urllib.request import Request, urlopen

from django.conf import settings


def normalize_whatsapp_number(value):
    """Return the contact number in the digits-only format Meta expects."""
    raw = (value or "").strip()
    international = raw.startswith("+") or raw.startswith("00")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if not international and digits.startswith("0"):
        digits = f"{settings.WHATSAPP_DEFAULT_COUNTRY_CODE}{digits[1:]}"
    elif not international and len(digits) == 10:
        digits = f"{settings.WHATSAPP_DEFAULT_COUNTRY_CODE}{digits}"
    if not 8 <= len(digits) <= 15:
        raise ValueError("Contact number is not valid for WhatsApp")
    return digits


def send_whatsapp_confirmation(enquiry):
    """Send the approved form-submission template; return None when disabled."""
    if not settings.WHATSAPP_CONFIRMATION_ENABLED:
        return None

    recipient = normalize_whatsapp_number(enquiry.contact)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "template",
        "template": {
            "name": settings.WHATSAPP_CONFIRMATION_TEMPLATE,
            "language": {"code": settings.WHATSAPP_CONFIRMATION_LANGUAGE},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": (enquiry.name or "there")[:60]}],
            }],
        },
    }
    request = Request(
        f"https://graph.facebook.com/{settings.WHATSAPP_GRAPH_API_VERSION}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return 200 <= response.status < 300
