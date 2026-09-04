"""Visitor confirmations; no changes to the enquiry stored in Django admin."""

from email import policy as email_policy
from email.utils import formataddr, make_msgid

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string


class ContactConfirmationEmail(EmailMultiAlternatives):
    """Keep the logo related to the HTML body, not a separate attachment."""

    def __init__(self, *, logo_content, logo_cid, html_cid, **kwargs):
        super().__init__(**kwargs)
        self.logo_content = logo_content
        self.logo_cid = logo_cid
        self.html_cid = html_cid

    def message(self, *, policy=email_policy.default):
        # Use Django's public serialization hook so headers, SMTP policy and
        # normal plaintext/HTML handling are retained. Do not use attach(),
        # which creates multipart/mixed and treats the image as a separate file.
        message = super().message(policy=policy)
        html = message.get_body(preferencelist=("html",))
        if html is None:
            raise ValueError("A confirmation email requires an HTML body.")
        html["Content-ID"] = self.html_cid
        html.add_related(
            self.logo_content,
            maintype="image",
            subtype="png",
            cid=self.logo_cid,
            disposition="inline",
            cte="base64",
        )
        # add_related() turns the HTML part into a related container and moves
        # its content headers into the first child. Explicitly identify that
        # child as the root document. Omit filename/name attachment hints.
        html.set_param("type", "text/html")
        html.set_param("start", self.html_cid)
        return message


def send_contact_confirmation(enquiry):
    """Send one confirmation, raising delivery errors for the caller to log."""
    recipient = (enquiry.email or "").strip()
    # Do not allow malformed addresses or extra recipients in mail headers.
    validate_email(recipient)
    # The preview-only fallback is never used for live SMTP: settings reject
    # SMTP configuration without the company's address and app password.
    sender = settings.IVORY_GMAIL_ADDRESS or "preview@localhost"
    sender_domain = sender.rsplit("@", 1)[-1].encode("idna").decode("ascii")
    logo_cid = make_msgid(idstring="ivory-logo", domain=sender_domain)
    context = {"name": enquiry.name, "logo_cid": logo_cid[1:-1]}

    email = ContactConfirmationEmail(
        subject="We've received your enquiry | Ivory Design",
        body=render_to_string("emails/contact_confirmation.txt", context),
        from_email=formataddr(("Ivory Design", sender)),
        to=[recipient],
        reply_to=[sender],
        headers={
            "Message-ID": make_msgid(idstring="ivory-confirmation", domain=sender_domain),
            "Auto-Submitted": "auto-generated",
        },
        logo_content=(settings.BASE_DIR / "static/images/b.png").read_bytes(),
        logo_cid=logo_cid,
        html_cid=make_msgid(idstring="ivory-html", domain=sender_domain),
    )
    email.attach_alternative(
        render_to_string("emails/contact_confirmation.html", context), "text/html"
    )

    return email.send(using="default")
