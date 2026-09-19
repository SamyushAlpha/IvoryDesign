"""Visitor confirmation email delivery."""

from email.utils import formataddr, make_msgid

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string


def send_contact_confirmation(enquiry):
    """Send a multipart confirmation with a Gmail-compatible hosted logo."""
    recipient = (enquiry.email or "").strip()
    validate_email(recipient)
    sender = settings.IVORY_GMAIL_ADDRESS or "preview@localhost"
    sender_domain = sender.rsplit("@", 1)[-1].encode("idna").decode("ascii")
    context = {
        "name": enquiry.name,
        # Use a versioned path so Gmail's image proxy does not reuse the cached
        # failure from the earlier deployment. Keep it hosted so the message has
        # no attachment and retains the inbox-friendly MIME structure.
        "logo_url": "https://ivoryarvena.vercel.app/static/images/ivory-arvena-mail-logo-2026.png",
        "site_url": "https://ivoryarvena.vercel.app/",
    }

    email = EmailMultiAlternatives(
        subject="We've received your enquiry | Ivory Arvena",
        body=render_to_string("emails/contact_confirmation.txt", context),
        from_email=formataddr(("Ivory Arvena", sender)),
        to=[recipient],
        reply_to=[sender],
        headers={
            "Message-ID": make_msgid(idstring="ivory-confirmation", domain=sender_domain),
            "Auto-Submitted": "auto-generated",
        },
    )
    email.attach_alternative(
        render_to_string("emails/contact_confirmation.html", context), "text/html"
    )
    return email.send(using="default")
