from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import CustomFAQ, Service, TeamPortfolio


class TeamPortfolioAdminForm(forms.ModelForm):
    portfolio_pdf_upload = forms.FileField(
        required=False,
        label="Portfolio PDF",
        help_text="Choose a PDF file up to 50 MB. It uploads when you save.",
        widget=forms.ClearableFileInput(attrs={"accept": "application/pdf,.pdf"}),
    )

    class Meta:
        model = TeamPortfolio
        fields = "__all__"
        widgets = {"portfolio_pdf": forms.HiddenInput()}


class EditButtonAdmin(admin.ModelAdmin):
    """Show an unmistakable edit action beside every editable content item."""

    @admin.display(description="EDIT")
    def edit_button(self, obj):
        url = reverse(
            f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change",
            args=(obj.pk,),
        )
        return format_html(
            '<a class="button" href="{}" aria-label="Edit {}">Edit</a>',
            url,
            obj,
        )


@admin.register(CustomFAQ)
class CustomFAQAdmin(EditButtonAdmin):
    list_display = ("question", "category", "is_active", "order", "edit_button")
    list_editable = ("is_active", "order")
    list_filter = ("is_active", "category")
    search_fields = ("question", "answer", "aliases")
from .models import (
    AboutCompany, TeamMember, PopupAd, Client, BusinessInformation,
    BusinessSocialProfile, SupportConversation, SupportMessage,
)

from .models import (
    ContactMessage,
    Project,
    ProjectCategory, ProjectImage,
)


# ==========================================================
# CONTACT MESSAGES
# ==========================================================

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "email",
        "contact",
        "short_message",
        "created_at",
    )

    search_fields = (
        "name",
        "email",
        "contact",
        "message",
    )

    list_filter = (
        "created_at",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 20

    list_display_links = (
        "name",
    )

    @admin.display(description="MESSAGE")
    def short_message(self, obj):

        if len(obj.message) > 60:
            return obj.message[:60] + "..."

        return obj.message


# ==========================================================
# PROJECT CATEGORIES
# ==========================================================

@admin.register(ProjectCategory)
class ProjectCategoryAdmin(EditButtonAdmin):

    list_display = (
        "name",
        "slug",
        "created_at",
        "edit_button",
    )

    search_fields = (
        "name",
    )

    prepopulated_fields = {
        "slug": ("name",)
    }


# ==========================================================
# PROJECTS
# ==========================================================

class ProjectImageInline(admin.StackedInline):
    model = ProjectImage
    extra = 1


@admin.register(Project)
class ProjectAdmin(EditButtonAdmin):
    inlines = (ProjectImageInline,)

    list_display = (
        "name",
        "category",
        "location",
        "year",
        "featured",
        "created_at",
        "edit_button",
    )

    list_filter = (
        "category",
        "featured",
        "year",
    )

    search_fields = (
        "name",
        "description",
        "location",
    )

    ordering = (
        "-created_at",
    )

    list_per_page = 20

    list_editable = (
        "featured",
    )

    autocomplete_fields = (
        "category",
    )
# ==========================================================
# ABOUT COMPANY
# ==========================================================

@admin.register(AboutCompany)
class AboutCompanyAdmin(EditButtonAdmin):

    list_display = (
        "title",
        "updated_at",
        "edit_button",
    )


# ==========================================================
# TEAM MEMBERS
# ==========================================================

class TeamPortfolioInline(admin.StackedInline):
    model = TeamPortfolio
    form = TeamPortfolioAdminForm
    extra = 0
    show_change_link = True
    fields = (
        "title", "description", "image", "portfolio_pdf_upload",
        "portfolio_pdf", "location", "year", "order", "is_active",
    )

    class Media:
        js = ("admin/team-portfolio-pdf-upload-v3.js",)


@admin.register(Service)
class ServiceAdmin(EditButtonAdmin):
    list_display = ("title", "order", "is_active", "edit_button")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "description")


@admin.register(TeamPortfolio)
class TeamPortfolioAdmin(EditButtonAdmin):
    form = TeamPortfolioAdminForm
    fields = (
        "member", "title", "description", "image", "portfolio_pdf_upload",
        "portfolio_pdf", "location", "year", "order", "is_active",
    )
    list_display = ("title", "member", "order", "is_active", "edit_button")
    list_editable = ("order", "is_active")
    list_filter = ("member", "is_active")
    search_fields = ("title", "description", "member__name")
    autocomplete_fields = ("member",)

    class Media:
        js = ("admin/team-portfolio-pdf-upload-v3.js",)


@admin.register(TeamMember)
class TeamMemberAdmin(EditButtonAdmin):
    inlines = (TeamPortfolioInline,)

    list_display = (
        "name",
        "designation",
        "order",
        "is_active",
        "edit_button",
    )

    list_filter = (
        "is_active",
        "designation",
    )

    search_fields = (
        "name",
        "designation",
        "bio",
    )

    list_editable = (
        "order",
        "is_active",
    )

    ordering = (
        "order",
        "name",
    )

#For popup ad section
# ==========================================================
# POPUP AD
# ==========================================================    
@admin.register(PopupAd)
class PopupAdAdmin(EditButtonAdmin):

    list_display = (
        "title",
        "is_active",
        "created_at",
        "edit_button",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
    )

    list_editable = (
        "is_active",
    )

    readonly_fields = (
        "created_at",
    )

@admin.register(Client)
class ClientAdmin(EditButtonAdmin):

    list_display = (
        "name",
        "logo",
        "order",
        "is_active",
        "created_at",
        "edit_button",
    )

    list_editable = (
        "order",
        "is_active",
    )

    ordering = (
        "order",
        "name",
    )


class BusinessSocialProfileInline(admin.TabularInline):
    model = BusinessSocialProfile
    extra = 1
    max_num = 7


@admin.register(BusinessInformation)
class BusinessInformationAdmin(EditButtonAdmin):
    list_display = ("__str__", "pricing_mode", "updated_at", "edit_button")
    readonly_fields = ("updated_at",)
    inlines = (BusinessSocialProfileInline,)
    fieldsets = (
        ("Pricing — public guidance, not a binding quote", {
            "description": "Start with Quote only. Enable per-square-foot estimates only after confirming the currency, rate and exact scope. Estimates use stated floor area × rate; no unit conversions, taxes, or other fees are added automatically.",
            "fields": ("pricing_mode", "pricing_guidance", "currency", "rate_per_sq_ft", "pricing_scope"),
        }),
        ("Studio location", {"fields": ("location", "nearby_landmark")}),
        ("Appointment requests", {"fields": ("appointment_instructions", "appointment_url")}),
        ("Record details", {"fields": ("updated_at",)}),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not BusinessInformation.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class SupportMessageInline(admin.TabularInline):
    model = SupportMessage
    extra = 0
    can_delete = False
    fields = ("sequence", "sender_type", "sender_user", "body", "created_at")
    readonly_fields = fields
    ordering = ("sequence",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SupportConversation)
class SupportConversationAdmin(admin.ModelAdmin):
    list_display = (
        "public_id", "visitor_name", "status", "assigned_to",
        "staff_unread_count", "last_activity_at",
    )
    list_filter = ("status", "handoff_state", "lead_state", "created_at")
    search_fields = ("public_id", "visitor_name", "visitor_phone")
    readonly_fields = (
        "public_id", "visitor_key", "staff_unread_count", "visitor_unread_count",
        "bot_deadline", "handoff_token", "first_staff_reply_at", "bot_takeover_at",
        "resolved_at", "created_at", "updated_at", "last_activity_at",
    )
    fields = (
        "public_id", "status", "handoff_state", "lead_state", "assigned_to",
        "visitor_name", "visitor_phone", "staff_unread_count", "visitor_unread_count",
        "bot_deadline", "first_staff_reply_at", "bot_takeover_at", "resolved_at",
        "created_at", "updated_at", "last_activity_at", "visitor_key", "handoff_token",
    )
    inlines = (SupportMessageInline,)
    ordering = ("-last_activity_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "sequence", "sender_type", "sender_user", "created_at")
    list_filter = ("sender_type", "created_at")
    search_fields = ("conversation__public_id", "body")
    readonly_fields = (
        "conversation", "sender_type", "sender_user", "client_message_id", "sequence",
        "body", "read_by_staff", "read_by_visitor", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("Ivory.view_supportmessage")

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
