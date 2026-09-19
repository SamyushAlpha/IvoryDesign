"""Visitor confirmation email delivery."""

from copy import deepcopy
from email.mime.image import MIMEImage
from email.utils import formataddr, make_msgid

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string


class InlineImageEmail(EmailMultiAlternatives):
    """Build a multipart/related message for CID images."""

    def __init__(self, *args, inline_images=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.inline_images = tuple(inline_images)

    def _add_attachments(self, message):
        super()._add_attachments(message)
        if self.inline_images:
            body = deepcopy(message)
            message.clear()
            message.make_related()
            message.attach(body)
            for image in self.inline_images:
                message.attach(image)


def send_contact_confirmation(enquiry):
    """Send a multipart confirmation with a Gmail-compatible inline logo."""
    recipient = (enquiry.email or "").strip()
    validate_email(recipient)
    sender = settings.IVORY_GMAIL_ADDRESS or "preview@localhost"
    sender_domain = sender.rsplit("@", 1)[-1].encode("idna").decode("ascii")
    logo_content_id = make_msgid(idstring="ivory-arvena-logo", domain=sender_domain)
    context = {
        "name": enquiry.name,
        "logo_cid": logo_content_id[1:-1],
        "site_url": "https://ivoryarvena.vercel.app/",
    }

    email = InlineImageEmail(
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
    # Static files are served separately on Vercel and are intentionally excluded
    # from the Django function bundle. Keep the mail asset beside the application
    # code so it is available when the serverless function builds the message.
    logo_path = settings.BASE_DIR / "Ivory" / "email_assets" / "ivoryarvena-email-logo.png"
    logo = MIMEImage(logo_path.read_bytes(), _subtype="png")
    logo.add_header("Content-ID", logo_content_id)
    logo.add_header("Content-Disposition", "inline", filename="ivory-arvena-logo.png")
    email.inline_images = (logo,)
    return email.send(using="default")
