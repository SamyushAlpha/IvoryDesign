from django.contrib import admin
from .models import CustomFAQ, Service, TeamPortfolio


@admin.register(CustomFAQ)
class CustomFAQAdmin(admin.ModelAdmin):
    list_display = ("question", "category", "is_active", "order")
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
    ProjectCategory,
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
class ProjectCategoryAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "slug",
        "created_at",
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

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "category",
        "location",
        "year",
        "featured",
        "created_at",
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
class AboutCompanyAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "updated_at",
    )


# ==========================================================
# TEAM MEMBERS
# ==========================================================

class TeamPortfolioInline(admin.StackedInline):
    model = TeamPortfolio
    extra = 0
    show_change_link = True


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "description")


@admin.register(TeamPortfolio)
class TeamPortfolioAdmin(admin.ModelAdmin):
    list_display = ("title", "member", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("member", "is_active")
    search_fields = ("title", "description", "member__name")
    autocomplete_fields = ("member",)


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    inlines = (TeamPortfolioInline,)

    list_display = (
        "name",
        "designation",
        "order",
        "is_active",
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
class PopupAdAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "is_active",
        "created_at",
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
class ClientAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "logo",
        "order",
        "is_active",
        "created_at",
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
class BusinessInformationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "pricing_mode", "updated_at")
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
