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
        "logo_url": "https://ivory-design.vercel.app/static/images/b.png",
    }

    email = EmailMultiAlternatives(
        subject="We've received your enquiry | Ivory Design",
        body=render_to_string("emails/contact_confirmation.txt", context),
        from_email=formataddr(("Ivory Design", sender)),
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
