from decimal import Decimal
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator, URLValidator
from django.db import models
from django.core.files.storage import FileSystemStorage
from django.utils import timezone


def private_support_storage():
    return FileSystemStorage(location=settings.PRIVATE_SUPPORT_ROOT, base_url=None)


def support_upload_path(instance, filename):
    return f"attachments/{uuid.uuid4().hex}"


DEFAULT_PRICING_GUIDANCE = "Pricing depends on the project scope and specifications. Please use the Contact form for a tailored quote."
DEFAULT_APPOINTMENT_INSTRUCTIONS = "Use the Contact form with your name, email, phone number, and project details to request a consultation. The team will confirm availability."


class SiteStatistics(models.Model):
    total_visits = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Website statistics"
        verbose_name_plural = "Website statistics"

    def __str__(self):
        return "Website visits"


class ActiveVisitor(models.Model):
    visitor_hash = models.CharField(max_length=64, unique=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "Visitor session"
        verbose_name_plural = "Visitor sessions"


class ContactMessage(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    contact = models.CharField(max_length=20)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# Portifolio models
class ProjectCategory(models.Model):

    name = models.CharField(max_length=100)

    slug = models.SlugField(
        unique=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Project Category"
        verbose_name_plural = "Project Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Project(models.Model):

    name = models.CharField(
        max_length=200
    )

    category = models.ForeignKey(
        ProjectCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="projects"
    )

    description = models.TextField(
        blank=True
    )

    image = models.ImageField(
        upload_to="projects/",
        max_length=500,
    )

    location = models.CharField(
        max_length=200,
        blank=True
    )

    year = models.PositiveIntegerField(
        blank=True,
        null=True
    )

    featured = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = "Project"
        verbose_name_plural = "Projects"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ProjectImage(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="gallery")
    image = models.ImageField(upload_to="projects/gallery/", max_length=500)
    caption = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Project gallery image"
        verbose_name_plural = "Project gallery images"

    def __str__(self):
        return self.caption or f"{self.project.name} image"
#For Aboutus section
# ==========================================================
# ABOUT COMPANY
# ==========================================================

class AboutCompany(models.Model):

    title = models.CharField(
        max_length=200,
        default="About Ivory Design"
    )

    description = models.TextField()

    vision = models.TextField(
        blank=True
    )

    mission = models.TextField(
        blank=True
    )

    image = models.ImageField(
        upload_to="about/",
        max_length=500,
        blank=True,
        null=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.title


# ==========================================================
# TEAM MEMBERS
# ==========================================================

class TeamMember(models.Model):

    name = models.CharField(
        max_length=150
    )

    designation = models.CharField(
        max_length=150
    )

    photo = models.ImageField(
        upload_to="team/",
        max_length=500,
    )

    bio = models.TextField(
        blank=True
    )

    order = models.PositiveIntegerField(
        default=0
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return f"{self.name} — {self.designation}"
    
#for popup ads 
class Service(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to="services/", blank=True, max_length=500)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "pk"]

    def __str__(self):
        return self.title


class TeamPortfolio(models.Model):
    member = models.ForeignKey(TeamMember, on_delete=models.CASCADE, related_name="portfolio")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="team/portfolio/", max_length=500)
    portfolio_pdf = models.URLField(
        max_length=500,
        blank=True,
        help_text="Uploaded PDF URL. Use the PDF chooser in the admin form.",
    )
    location = models.CharField(max_length=200, blank=True)
    year = models.PositiveIntegerField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Team portfolio entry"
        verbose_name_plural = "Team portfolio entries"

    def __str__(self):
        return self.title


class PopupAd(models.Model):

    title = models.CharField(max_length=200)

    description = models.TextField()

    image = models.ImageField(upload_to="popup_ads/", max_length=500)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Popup Advertisement"
        verbose_name_plural = "Popup Advertisements"
        ordering = ["-created_at"]

#for Model Logo

class Client(models.Model):
    name = models.CharField(max_length=200)

    logo = models.ImageField(
        upload_to="clients/",
        max_length=500,
    )

    order = models.PositiveIntegerField(
        default=0
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class BusinessInformation(models.Model):
    """One owner-maintained, public FAQ configuration. Never store secrets here."""

    class PricingMode(models.TextChoices):
        QUOTE_ONLY = "quote_only", "Quote only — no automatic estimates"
        PER_SQ_FT = "per_sq_ft", "Estimate = rate × stated floor area in square feet"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    pricing_mode = models.CharField(max_length=20, choices=PricingMode, default=PricingMode.QUOTE_ONLY)
    pricing_guidance = models.TextField(max_length=400, default=DEFAULT_PRICING_GUIDANCE,
                                      help_text="Public pricing notes, exclusions, or quote-only guidance. No secrets.")
    currency = models.CharField(max_length=3, blank=True,
                                validators=[RegexValidator(r"^[A-Z]{3}$", "Enter a three-letter uppercase currency code, e.g. NPR.")],
                                help_text="Required for estimates. Enter your actual billing currency, e.g. NPR.")
    rate_per_sq_ft = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                        validators=[MinValueValidator(Decimal("0.01"))],
                                        help_text="Owner-approved rate for one square foot of floor area. No rate is assumed.")
    pricing_scope = models.CharField(max_length=180, blank=True,
                                    help_text="Required for estimates: explain exactly what the rate covers, including tax/exclusions where relevant.")
    location = models.CharField(max_length=240, blank=True, default="Kathmandu, Nepal",
                               help_text="Public studio address/location. The default is only the city already published on the site.")
    nearby_landmark = models.CharField(max_length=180, blank=True,
                                      help_text="Verified nearby landmark only; leave blank if unknown.")
    appointment_instructions = models.TextField(max_length=400, default=DEFAULT_APPOINTMENT_INSTRUCTIONS)
    appointment_url = models.URLField(max_length=200, blank=True, validators=[URLValidator(schemes=["http", "https"])],
                                     help_text="Optional public booking page. Without it, visitors use /contact/. The chat never confirms a booking.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Chat business information"
        verbose_name_plural = "Chat business information"
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="ivory_business_singleton"),
            models.CheckConstraint(condition=models.Q(rate_per_sq_ft__isnull=True) | models.Q(rate_per_sq_ft__gt=0), name="ivory_business_positive_rate"),
        ]

    def clean(self):
        errors = {}
        if self.pk != 1:
            errors["id"] = "There is only one Chat business information record."
        if self.pricing_mode == self.PricingMode.PER_SQ_FT:
            if self.rate_per_sq_ft is None:
                errors["rate_per_sq_ft"] = "Enter a positive rate before enabling estimates."
            if not self.currency.strip():
                errors["currency"] = "Enter the currency before enabling estimates."
            if not self.pricing_scope.strip():
                errors["pricing_scope"] = "Explain what the rate covers before enabling estimates."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return "Ivory Design — public chat answers"


class BusinessSocialProfile(models.Model):
    class Platform(models.TextChoices):
        INSTAGRAM = "instagram", "Instagram"
        FACEBOOK = "facebook", "Facebook"
        LINKEDIN = "linkedin", "LinkedIn"
        TIKTOK = "tiktok", "TikTok"
        PINTEREST = "pinterest", "Pinterest"
        YOUTUBE = "youtube", "YouTube"
        X = "x", "X / Twitter"

    business = models.ForeignKey(BusinessInformation, on_delete=models.CASCADE, related_name="social_profiles")
    platform = models.CharField(max_length=20, choices=Platform)
    handle = models.CharField(max_length=80, blank=True, help_text="The verified public handle, e.g. @youractualhandle. Leave blank if using a URL only.")
    url = models.URLField(max_length=200, blank=True, validators=[URLValidator(schemes=["http", "https"])])

    class Meta:
        verbose_name = "Public social profile"
        ordering = ["platform"]
        constraints = [models.UniqueConstraint(fields=["business", "platform"], name="ivory_one_social_per_platform")]

    def clean(self):
        if not self.handle.strip() and not self.url.strip():
            raise ValidationError("Enter a verified handle or a public http(s) URL.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.get_platform_display()


class SupportConversation(models.Model):
    """Durable visitor support thread shared by the website and staff inbox."""

    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting for staff"
        BOT_HANDLED = "bot_handled", "Automated assistant"
        HUMAN_ACTIVE = "human_active", "Staff handling"
        RESOLVED = "resolved", "Resolved"

    class HandoffState(models.TextChoices):
        WAITING = "waiting", "Waiting for a team member"
        ASSISTANT = "assistant", "Automated assistant"
        STAFF = "staff", "Staff member"

    class LeadState(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        AWAITING_NAME = "awaiting_name", "Waiting for name"
        AWAITING_PHONE = "awaiting_phone", "Waiting for phone"
        COMPLETE = "complete", "Complete"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    visitor_key = models.CharField(max_length=64, db_index=True, editable=False)
    status = models.CharField(max_length=20, choices=Status, default=Status.WAITING, db_index=True)
    handoff_state = models.CharField(max_length=20, choices=HandoffState, default=HandoffState.WAITING)
    lead_state = models.CharField(max_length=20, choices=LeadState, default=LeadState.NOT_STARTED)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_support_conversations",
    )
    visitor_name = models.CharField(max_length=80, blank=True)
    visitor_phone = models.CharField(
        max_length=24,
        blank=True,
        validators=[RegexValidator(r"^\+[1-9]\d{7,14}$", "Use an international number such as +9779812345678.")],
    )
    staff_unread_count = models.PositiveIntegerField(default=0)
    visitor_unread_count = models.PositiveIntegerField(default=0)
    bot_deadline = models.DateTimeField(null=True, blank=True, db_index=True)
    handoff_token = models.UUIDField(default=uuid.uuid4, editable=False)
    first_staff_reply_at = models.DateTimeField(null=True, blank=True)
    bot_takeover_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-last_activity_at"]
        indexes = [
            models.Index(fields=["status", "last_activity_at"], name="ivory_support_status_activity"),
            models.Index(fields=["visitor_key", "status"], name="ivory_support_visitor_status"),
        ]

    def __str__(self):
        label = self.visitor_name or "Anonymous visitor"
        return f"{label} · {self.get_status_display()}"


class SupportMessage(models.Model):
    class SenderType(models.TextChoices):
        VISITOR = "visitor", "Visitor"
        STAFF = "staff", "Staff"
        ASSISTANT = "assistant", "Automated assistant"
        SYSTEM = "system", "System"

    conversation = models.ForeignKey(SupportConversation, on_delete=models.CASCADE, related_name="support_messages")
    sender_type = models.CharField(max_length=12, choices=SenderType)
    sender_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_messages",
    )
    client_message_id = models.UUIDField(null=True, blank=True, unique=True, editable=False)
    sequence = models.PositiveBigIntegerField()
    body = models.TextField(max_length=1800)
    read_by_staff = models.BooleanField(default=False)
    read_by_visitor = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(fields=["conversation", "sequence"], name="ivory_support_message_sequence"),
        ]
        indexes = [models.Index(fields=["conversation", "created_at"], name="ivory_support_message_time")]

    def clean(self):
        if self.sender_type == self.SenderType.STAFF and not self.sender_user_id:
            raise ValidationError({"sender_user": "Staff messages require a staff user."})
        if self.sender_type != self.SenderType.STAFF and self.sender_user_id:
            raise ValidationError({"sender_user": "Only staff messages may reference a user."})

    def __str__(self):
        return f"{self.get_sender_type_display()} #{self.sequence}"


class CustomFAQ(models.Model):
    question = models.CharField(max_length=240)
    answer = models.TextField(max_length=1400)
    aliases = models.TextField(blank=True, max_length=1500, help_text="Alternative complete questions, one per line. Avoid generic single words.")
    category = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "pk"]
        verbose_name = "Custom chat FAQ"

    def __str__(self):
        return self.question


class SupportAttachment(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    message = models.ForeignKey(SupportMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(storage=private_support_storage, upload_to=support_upload_path)
    filename = models.CharField(max_length=120)
    content_type = models.CharField(max_length=80)
    size = models.PositiveIntegerField()
    duration = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.filename
