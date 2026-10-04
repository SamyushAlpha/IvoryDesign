from django import forms
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin, UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, Permission, User
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm
from .models import (
    ActiveVisitor, CustomFAQ, Project, ProjectImage, Service, SiteStatistics,
    TeamPortfolio, InvoiceCounter, RoomEstimate, SalaryAdvance, SalaryPayment,
    SalaryRecord, TeamMember, ClientProjectAccount, ClientProjectPayment,
    AttendanceRecord, monthly_attendance_salary,
)
from .payroll import client_payment_invoice_response, salary_invoice_response


class StaffAccountCreationForm(UserCreationForm):
    """Create a staff login and assign its access in one form."""

    team_member = forms.ModelChoiceField(
        label="Team member profile",
        queryset=TeamMember.objects.filter(user__isnull=True),
        required=False,
        help_text=(
            "Link this login to a team member. Salary access will then show only that member's records."
        ),
    )
    can_use_live_support = forms.BooleanField(
        label="Live Support access",
        required=False,
        help_text="Allow this member to open Live Support, read client conversations, and reply to clients.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username", "first_name", "last_name", "email", "is_active",
            "is_staff", "groups", "user_permissions", "can_use_live_support", "team_member",
        )


class StaffAccountChangeForm(UserChangeForm):
    """Edit a staff login and its linked team member profile."""

    team_member = forms.ModelChoiceField(
        label="Team member profile",
        queryset=TeamMember.objects.none(),
        required=False,
        help_text=(
            "Link this login to a team member. The member's photo appears in the admin profile, "
            "and salary access is limited to that member's records."
        ),
    )
    can_use_live_support = forms.BooleanField(
        label="Live Support access",
        required=False,
        help_text="Allow this member to open Live Support, read client conversations, and reply to clients.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_member = None
        if self.instance and self.instance.pk:
            current_member = TeamMember.objects.filter(user=self.instance).first()

        available = TeamMember.objects.filter(user__isnull=True)
        if current_member:
            available = TeamMember.objects.filter(Q(user__isnull=True) | Q(pk=current_member.pk))

        self.fields["team_member"].queryset = available.order_by("name")
        self.fields["team_member"].initial = current_member
        if self.instance and self.instance.pk:
            self.fields["can_use_live_support"].initial = self.instance.has_perms(
                ("Ivory.view_supportconversation", "Ivory.change_supportconversation")
            )


admin.site.unregister(User)


@admin.register(User)
class StaffAccountAdmin(BaseUserAdmin, ModelAdmin):
    form = StaffAccountChangeForm
    add_form = StaffAccountCreationForm
    change_password_form = AdminPasswordChangeForm
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "is_active")
    list_filter = ("is_staff", "is_active", "groups")
    filter_horizontal = ("groups", "user_permissions")
    fieldsets = (
        ("Account", {"fields": ("username", "password")}),
        ("Personal details", {"fields": ("first_name", "last_name", "email")}),
        ("Access control", {
            "description": (
                "Enable Staff status so this person can sign in. Assign an access role, "
                "individual permissions, or both. View, add, change and delete are separate permissions."
            ),
            "fields": (
                "is_active", "is_staff", "groups", "user_permissions",
                "can_use_live_support", "team_member",
            ),
        }),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        ("Login details", {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2"),
        }),
        ("Personal details", {
            "classes": ("wide",),
            "fields": ("first_name", "last_name", "email"),
        }),
        ("Access control", {
            "classes": ("wide",),
            "description": (
                "Enable Staff status, then choose only the access this person needs. "
                "Use roles when several people need the same access."
            ),
            "fields": (
                "is_active", "is_staff", "groups", "user_permissions",
                "can_use_live_support", "team_member",
            ),
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        member = form.cleaned_data.get("team_member")
        TeamMember.objects.filter(user=obj).exclude(pk=getattr(member, "pk", None)).update(user=None)
        if member and member.user_id != obj.pk:
            member.user = obj
            member.save(update_fields=("user",))

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        support_permissions = Permission.objects.filter(
            content_type__app_label="Ivory",
            content_type__model="supportconversation",
            codename__in=("view_supportconversation", "change_supportconversation"),
        )
        if form.cleaned_data.get("can_use_live_support"):
            form.instance.user_permissions.add(*support_permissions)
        else:
            form.instance.user_permissions.remove(*support_permissions)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser and obj != request.user


admin.site.unregister(Group)


@admin.register(Group)
class AccessRoleAdmin(BaseGroupAdmin, ModelAdmin):
    filter_horizontal = ("permissions",)
    fieldsets = (
        ("Access role", {
            "description": (
                "Create a reusable role such as Project Editor or Live Support. "
                "Everyone assigned to this role receives the selected permissions."
            ),
            "fields": ("name", "permissions"),
        }),
    )

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


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


class DirectProjectImageForm(forms.ModelForm):
    image_upload = forms.ImageField(
        required=False,
        label="Image",
        help_text="Choose an image up to 50 MB. It uploads directly when you save.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )

    def clean(self):
        cleaned = super().clean()
        raw_url = self.data.get(self.add_prefix("image_url"), "").strip()
        if raw_url:
            try:
                cleaned["image_url"] = forms.URLField().clean(raw_url)
            except forms.ValidationError as error:
                self.add_error("image_upload", error)
        elif cleaned.get("image_upload"):
            self.add_error("image_upload", "The upload did not finish. Please choose the image again.")
        elif not getattr(self.instance, "image", None):
            self.add_error("image_upload", "Choose an image.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        image_url = self.cleaned_data.get("image_url")
        if image_url:
            instance.image = image_url
        if commit:
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = Project
        fields = "__all__"


class DirectProjectGalleryImageForm(DirectProjectImageForm):
    class Meta:
        model = ProjectImage
        fields = "__all__"


class SalaryRecordAdminForm(forms.ModelForm):
    salary_month = forms.DateField(
        label="Salary month",
        help_text="Choose the month this salary belongs to.",
        input_formats=("%Y-%m", "%Y-%m-%d"),
        widget=forms.DateInput(format="%Y-%m", attrs={"type": "month"}),
    )
    salary_amount = forms.DecimalField(
        label="Monthly salary amount (NPR)",
        help_text="Filled from the selected team member's profile. You can adjust it for this month.",
        required=False,
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )
    advances_to_deduct = forms.ModelMultipleChoiceField(
        label="Choose advances to deduct this month",
        queryset=SalaryAdvance.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text=(
            "Only checked advances will reduce this month's pending salary. "
            "Unchecked advances remain available for a later month."
        ),
    )

    class Meta:
        model = SalaryRecord
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        member_id = None
        if self.is_bound:
            member_id = self.data.get(self.add_prefix("member"))
        elif self.instance.pk:
            member_id = self.instance.member_id
        if member_id:
            eligible = SalaryAdvance.objects.filter(member_id=member_id).filter(
                Q(salary_record__isnull=True) | Q(salary_record=self.instance if self.instance.pk else None)
            )
            self.fields["advances_to_deduct"].queryset = eligible.order_by("given_on", "pk")
        if self.instance.pk:
            self.fields["advances_to_deduct"].initial = self.instance.advances.all()

    def clean(self):
        cleaned = super().clean()
        member = cleaned.get("member")
        salary_month = cleaned.get("salary_month")
        amount = cleaned.get("salary_amount")
        if member and salary_month and member.monthly_salary and (
            amount is None or (not self.instance.pk and amount == member.monthly_salary)
        ):
            summary = monthly_attendance_salary(member, salary_month, member.monthly_salary)
            amount = summary["payable_salary"]
            cleaned["salary_amount"] = amount
            self.instance.gross_salary = member.monthly_salary
            self.instance.attendance_working_days = summary["working_days"]
            self.instance.attendance_present_days = summary["present_days"]
            self.instance.attendance_worked_hours = summary["worked_hours"]
            self.instance.attendance_leave_units = summary["leave_units"]
            self.instance.attendance_deduction = summary["deduction"]
        if amount is None:
            self.add_error(
                "salary_amount",
                "Add a monthly salary to the team member profile or enter an amount here.",
            )
        if self.instance.pk and amount is not None:
            selected_advances = cleaned.get("advances_to_deduct")
            advance_total = sum(
                (advance.amount for advance in selected_advances),
                0,
            ) if selected_advances is not None else self.instance.advance_total
            committed = advance_total + self.instance.payment_total
            if amount < committed:
                self.add_error(
                    "salary_amount",
                    f"Salary cannot be below the NPR {committed:,.2f} already recorded.",
                )
        elif amount is not None:
            selected_advances = cleaned.get("advances_to_deduct")
            advance_total = sum(
                (advance.amount for advance in selected_advances),
                0,
            ) if selected_advances is not None else 0
            if advance_total > amount:
                self.add_error(
                    "advances_to_deduct",
                    f"Selected advances cannot exceed the NPR {amount:,.2f} monthly salary.",
                )
        return cleaned


class SalaryAdvanceInlineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors) or not self.instance.pk:
            return
        advance_total = sum(
            (
                form.cleaned_data["amount"]
                for form in self.forms
                if form.cleaned_data
                and not form.cleaned_data.get("DELETE")
                and form.cleaned_data.get("amount")
            ),
            0,
        )
        payment_total = self.instance.payment_total
        if advance_total + payment_total > self.instance.salary_amount:
            raise forms.ValidationError(
                "Advances and payments cannot be greater than the monthly salary."
            )


class SalaryAdvanceInline(TabularInline):
    model = SalaryAdvance
    formset = SalaryAdvanceInlineFormSet
    extra = 1
    fields = ("given_on", "amount", "note")


class SalaryAdvanceAdminForm(forms.ModelForm):
    given_on = forms.DateField(
        label="Given on",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = SalaryAdvance
        fields = ("member", "amount", "given_on", "note")


class AttendanceRecordAdminForm(forms.ModelForm):
    attendance_date = forms.DateField(
        label="Date",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = AttendanceRecord
        fields = (
            "member", "attendance_date", "attendance_type", "check_in_at", "check_out_at",
            "approval_status", "note",
        )

    def clean(self):
        cleaned = super().clean()
        check_in = cleaned.get("check_in_at")
        check_out = cleaned.get("check_out_at")
        if check_out and not check_in:
            self.add_error("check_out_at", "An entry time is required before an exit time.")
        elif check_in and check_out and check_out <= check_in:
            self.add_error("check_out_at", "Exit time must be later than entry time.")
        return cleaned

    def clean_attendance_date(self):
        attendance_date = self.cleaned_data["attendance_date"]
        if attendance_date > timezone.localdate():
            raise forms.ValidationError("Attendance or leave cannot be submitted for a future date.")
        return attendance_date


class SalaryPaymentInline(TabularInline):
    model = SalaryPayment
    extra = 0
    fields = ("invoice_number_display", "paid_on", "amount", "note", "invoice_link")
    readonly_fields = fields
    can_delete = False
    verbose_name = "Payment receipt"
    verbose_name_plural = "Payment receipts"

    @admin.display(description="Invoice")
    def invoice_number_display(self, obj):
        return obj.invoice_number

    @admin.display(description="PDF")
    def invoice_link(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("admin:salary_payment_invoice", args=(obj.public_id,))
        return format_html('<a class="button" href="{}" target="_blank">Open invoice</a>', url)

    def has_add_permission(self, request, obj=None):
        return False


def _payroll_members_for(request):
    members = TeamMember.objects.all()
    if request.user.is_superuser:
        return members
    return members.filter(user=request.user)


def _restrict_member_field_to_user(form_class, request):
    if request.user.is_superuser:
        return form_class
    allowed_members = _payroll_members_for(request)
    member_id = allowed_members.values_list("pk", flat=True).first()

    class RestrictedMemberForm(form_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if "member" in self.fields:
                self.fields["member"].queryset = allowed_members
                self.fields["member"].initial = member_id

    return RestrictedMemberForm


class PaySalaryForm(forms.Form):
    amount = forms.DecimalField(
        label="Payment amount",
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )
    paid_on = forms.DateField(
        label="Payment date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    note = forms.CharField(
        required=False,
        max_length=240,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Optional payment note"}),
    )


class ClientProjectAccountAdminForm(forms.ModelForm):
    initial_advance = forms.DecimalField(
        label="Advance received (NPR)",
        min_value=0.01,
        max_digits=14,
        decimal_places=2,
        required=False,
        help_text="Required for a new account. Saving creates the first transaction and invoice.",
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )
    advance_received_on = forms.DateField(
        label="Advance transaction date",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        model = ClientProjectAccount
        fields = "__all__"
        widgets = {
            "project_started_on": forms.DateInput(attrs={"type": "date"}),
            "agreed_amount": forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["initial_advance"].required = True
            self.fields["advance_received_on"].required = True
            self.fields["advance_received_on"].initial = timezone.localdate()
        else:
            self.fields.pop("initial_advance", None)
            self.fields.pop("advance_received_on", None)

    def clean(self):
        cleaned = super().clean()
        agreed = cleaned.get("agreed_amount")
        advance = cleaned.get("initial_advance")
        if agreed is not None and advance is not None and advance > agreed:
            self.add_error("initial_advance", "Advance cannot be greater than the agreed project amount.")
        if self.instance.pk and agreed is not None and agreed < self.instance.payment_total:
            self.add_error(
                "agreed_amount",
                f"Project amount cannot be below the NPR {self.instance.payment_total:,.2f} already received.",
            )
        return cleaned


class AddClientPaymentForm(forms.Form):
    amount = forms.DecimalField(
        label="Amount received",
        min_value=0.01,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
    )
    paid_on = forms.DateField(
        label="Transaction date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    note = forms.CharField(
        required=False,
        max_length=240,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Optional payment note"}),
    )


class ClientProjectPaymentInline(TabularInline):
    model = ClientProjectPayment
    extra = 0
    fields = ("invoice_number_display", "paid_on", "amount", "note", "invoice_link")
    readonly_fields = fields
    can_delete = False
    verbose_name = "Payment receipt"
    verbose_name_plural = "Payment history and invoices"

    @admin.display(description="Invoice")
    def invoice_number_display(self, obj):
        return obj.invoice_number

    @admin.display(description="PDF")
    def invoice_link(self, obj):
        if not obj.pk:
            return "—"
        url = reverse("admin:client_project_payment_invoice", args=(obj.public_id,))
        return format_html('<a class="button" href="{}" target="_blank">Open invoice</a>', url)

    def has_add_permission(self, request, obj=None):
        return False


class EditButtonAdmin(ModelAdmin):
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


@admin.register(SiteStatistics)
class SiteStatisticsAdmin(ModelAdmin):
    list_display = ("visits_display", "online_display", "updated_at")
    readonly_fields = ("total_visits", "updated_at")

    @admin.display(description="TOTAL VISITS")
    def visits_display(self, obj):
        return format_html('<strong id="ivory-total-visits">{}</strong>', obj.total_visits)

    @admin.display(description="ONLINE NOW")
    def online_display(self, obj):
        return format_html('<strong id="ivory-online-visitors">{}</strong>', "—")

    def changelist_view(self, request, extra_context=None):
        SiteStatistics.objects.get_or_create(pk=1)
        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    class Media:
        js = ("site-metrics.js",)


@admin.register(ActiveVisitor)
class ActiveVisitorAdmin(ModelAdmin):
    list_display = ("first_seen", "last_seen")
    readonly_fields = ("visitor_hash", "first_seen", "last_seen")
    ordering = ("-last_seen",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("Ivory.view_activevisitor")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RoomEstimate)
class RoomEstimateAdmin(ModelAdmin):
    change_list_template = "admin/roomestimate_change_list.html"
    list_display = ("invoice_number_display", "customer_name", "phone_number", "room_names_display", "room_count", "total_area_sq_ft", "rate_per_sq_ft", "total_amount", "created_at")
    search_fields = ("customer_name", "phone_number", "public_id")
    ordering = ("-created_at",)
    readonly_fields = ("public_id", "customer_name", "phone_number", "room_count", "rooms", "rate_per_sq_ft", "total_area_sq_ft", "total_amount", "created_at", "invoice_number_display")

    @admin.display(description="Invoice")
    def invoice_number_display(self, obj):
        return obj.invoice_number

    @admin.display(description="Room names")
    def room_names_display(self, obj):
        return ", ".join(room.get("name") or f"Room {room.get('room', '')}" for room in obj.rooms)

    def has_add_permission(self, request):
        return False

    def get_urls(self):
        custom_urls = [
            path(
                "reset-invoice-numbering/",
                self.admin_site.admin_view(self.reset_invoice_numbering_view),
                name="roomestimate_reset_invoice_numbering",
            ),
        ]
        return custom_urls + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["reset_invoice_url"] = reverse("admin:roomestimate_reset_invoice_numbering")
        return super().changelist_view(request, extra_context=extra_context)

    def reset_invoice_numbering_view(self, request):
        if not request.user.is_superuser:
            return HttpResponseForbidden("Only a superuser can reset invoice numbering.")

        year = timezone.localdate().year
        estimate_count = RoomEstimate.objects.count()
        if request.method == "POST":
            with transaction.atomic():
                RoomEstimate.objects.all().delete()
                InvoiceCounter.objects.all().delete()
                InvoiceCounter.objects.create(year=year, last_number=0)
            self.message_user(
                request,
                f"Invoice numbering reset. The next invoice will be IVY-{year}-00001.",
                level=messages.SUCCESS,
            )
            return redirect(reverse("admin:Ivory_roomestimate_changelist"))

        context = {
            **self.admin_site.each_context(request),
            "title": "Reset invoice numbering",
            "opts": self.model._meta,
            "estimate_count": estimate_count,
            "next_invoice": f"IVY-{year}-00001",
            "changelist_url": reverse("admin:Ivory_roomestimate_changelist"),
        }
        return TemplateResponse(request, "admin/reset_invoice_numbering.html", context)


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(ModelAdmin):
    form = AttendanceRecordAdminForm
    change_list_template = "admin/attendance_record_change_list.html"
    list_display = (
        "member_display", "attendance_date", "attendance_type_display",
        "entry_time_display", "exit_time_display", "worked_hours_display",
        "approval_display", "note",
    )
    list_filter = ("attendance_type", "approval_status", "attendance_date", "member")
    search_fields = ("member__name", "member__designation", "note")
    ordering = ("-attendance_date", "member__name")
    date_hierarchy = "attendance_date"
    actions = ("approve_leave_requests", "reject_leave_requests")
    fieldsets = (
        ("Attendance or leave request", {
            "description": (
                "Members use Check in when they arrive and Check out when they leave. "
                "Choose a leave type to request a full-day or half-day leave."
            ),
            "fields": (
                "member", "attendance_date", "attendance_type", "check_in_at", "check_out_at",
                "worked_hours_display", "approval_status", "note",
            ),
        }),
    )
    readonly_fields = ("worked_hours_display",)

    def get_urls(self):
        custom_urls = [
            path("check-in/", self.admin_site.admin_view(self.check_in), name="attendance_check_in"),
            path("check-out/", self.admin_site.admin_view(self.check_out), name="attendance_check_out"),
        ]
        return custom_urls + super().get_urls()

    def _clock_member(self, request):
        return TeamMember.objects.filter(user=request.user).first()

    def check_in(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        member = self._clock_member(request)
        if not member or not request.user.is_active or not request.user.is_staff:
            raise PermissionDenied("A linked team member profile is required to check in.")
        record, created = AttendanceRecord.objects.get_or_create(
            member=member,
            attendance_date=timezone.localdate(),
            defaults={
                "attendance_type": AttendanceRecord.AttendanceType.PRESENT,
                "approval_status": AttendanceRecord.ApprovalStatus.APPROVED,
                "check_in_at": timezone.now(),
            },
        )
        if not created:
            if record.attendance_type != AttendanceRecord.AttendanceType.PRESENT:
                self.message_user(request, "You already have a leave record for today.", level=messages.ERROR)
            elif record.check_in_at:
                self.message_user(request, "You have already checked in today.", level=messages.WARNING)
            else:
                record.check_in_at = timezone.now()
                record.save(update_fields=("check_in_at", "updated_at"))
                self.message_user(request, "Entry time recorded.", level=messages.SUCCESS)
        else:
            self.message_user(request, "Entry time recorded.", level=messages.SUCCESS)
        return redirect("admin:Ivory_attendancerecord_changelist")

    def check_out(self, request):
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        member = self._clock_member(request)
        if not member or not request.user.is_active or not request.user.is_staff:
            raise PermissionDenied("A linked team member profile is required to check out.")
        record = AttendanceRecord.objects.filter(
            member=member,
            attendance_date=timezone.localdate(),
            attendance_type=AttendanceRecord.AttendanceType.PRESENT,
        ).first()
        if not record or not record.check_in_at:
            self.message_user(request, "Check in first before recording your exit.", level=messages.ERROR)
        elif record.check_out_at:
            self.message_user(request, "You have already checked out today.", level=messages.WARNING)
        else:
            record.check_out_at = timezone.now()
            record.save(update_fields=("check_out_at", "updated_at"))
            self.message_user(request, "Exit time recorded.", level=messages.SUCCESS)
        return redirect("admin:Ivory_attendancerecord_changelist")

    def changelist_view(self, request, extra_context=None):
        extra_context = dict(extra_context or {})
        member = self._clock_member(request)
        extra_context["clock_member"] = member
        extra_context["today_attendance"] = (
            AttendanceRecord.objects.filter(member=member, attendance_date=timezone.localdate()).first()
            if member else None
        )
        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(member__user=request.user)
        return queryset.select_related("member")

    def get_form(self, request, obj=None, **kwargs):
        return _restrict_member_field_to_user(super().get_form(request, obj, **kwargs), request)

    def get_readonly_fields(self, request, obj=None):
        base = ("worked_hours_display",)
        return base if request.user.is_superuser else base + ("approval_status", "check_in_at", "check_out_at")

    def get_list_filter(self, request):
        return self.list_filter if request.user.is_superuser else ("attendance_type", "approval_status", "attendance_date")

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_superuser:
            actions.pop("approve_leave_requests", None)
            actions.pop("reject_leave_requests", None)
        return actions

    def has_module_permission(self, request):
        return request.user.is_superuser or (
            request.user.is_active and request.user.is_staff and _payroll_members_for(request).exists()
        )

    def has_add_permission(self, request):
        return request.user.is_superuser or (
            request.user.is_active and request.user.is_staff and _payroll_members_for(request).exists()
        )

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or (
            request.user.is_active and request.user.is_staff
            and _payroll_members_for(request).exists()
            and (obj is None or obj.member.user_id == request.user.id)
        )

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            if obj.member.user_id != request.user.id:
                raise PermissionDenied("You can save only your own attendance.")
            if obj.attendance_type != AttendanceRecord.AttendanceType.PRESENT:
                obj.approval_status = AttendanceRecord.ApprovalStatus.PENDING
        super().save_model(request, obj, form, change)

    @admin.display(description="Team member", ordering="member__name")
    def member_display(self, obj):
        return obj.member.name

    @admin.display(description="Record")
    def attendance_type_display(self, obj):
        return obj.get_attendance_type_display()

    @admin.display(description="Entry")
    def entry_time_display(self, obj):
        return timezone.localtime(obj.check_in_at).strftime("%I:%M %p") if obj.check_in_at else "—"

    @admin.display(description="Exit")
    def exit_time_display(self, obj):
        return timezone.localtime(obj.check_out_at).strftime("%I:%M %p") if obj.check_out_at else "—"

    @admin.display(description="Hours")
    def worked_hours_display(self, obj):
        if not obj or not obj.pk:
            return "Calculated after check out"
        return f"{obj.worked_hours:.2f} hours" if obj.check_out_at else "In progress" if obj.check_in_at else "—"

    @admin.display(description="Approval")
    def approval_display(self, obj):
        css_class = {
            AttendanceRecord.ApprovalStatus.APPROVED: "is-paid",
            AttendanceRecord.ApprovalStatus.PENDING: "is-partial",
            AttendanceRecord.ApprovalStatus.REJECTED: "is-pending",
        }[obj.approval_status]
        return format_html('<span class="salary-status {}">{}</span>', css_class, obj.get_approval_status_display())

    @admin.action(description="Approve selected leave requests")
    def approve_leave_requests(self, request, queryset):
        updated = queryset.exclude(attendance_type=AttendanceRecord.AttendanceType.PRESENT).update(
            approval_status=AttendanceRecord.ApprovalStatus.APPROVED
        )
        self.message_user(request, f"Approved {updated} leave request(s).", level=messages.SUCCESS)

    @admin.action(description="Reject selected leave requests")
    def reject_leave_requests(self, request, queryset):
        updated = queryset.exclude(attendance_type=AttendanceRecord.AttendanceType.PRESENT).update(
            approval_status=AttendanceRecord.ApprovalStatus.REJECTED
        )
        self.message_user(request, f"Rejected {updated} leave request(s).", level=messages.SUCCESS)

    class Media:
        css = {"all": ("admin/payroll.css",)}


@admin.register(SalaryRecord)
class SalaryRecordAdmin(ModelAdmin):
    form = SalaryRecordAdminForm
    inlines = (SalaryPaymentInline,)
    change_list_template = "admin/salary_record_change_list.html"
    change_form_template = "admin/salary_record_change_form.html"
    list_display = (
        "member_display",
        "salary_month_display",
        "salary_display",
        "attendance_deduction_list",
        "advance_display",
        "paid_display",
        "pending_display",
        "status_display",
        "record_actions",
    )
    list_filter = ("salary_month", "member")
    search_fields = ("member__name", "member__designation", "notes")
    autocomplete_fields = ("member",)
    ordering = ("-salary_month", "member__name")
    date_hierarchy = "salary_month"
    save_on_top = True
    readonly_fields = (
        "gross_salary_display", "attendance_working_days", "attendance_present_days",
        "attendance_worked_hours", "attendance_leave_units", "attendance_deduction_display",
    )
    fieldsets = (
        ("Monthly salary", {
            "description": (
                "Create the amount owed to this team member for one month. "
                "The balance starts as awaiting payment until you record an advance or pay it."
            ),
            "fields": ("member", "salary_month", "salary_amount", "notes"),
        }),
        ("Salary advances", {
            "description": (
                "Select the advances that should be deducted from this month's salary. "
                "Unused advances remain available for another month."
            ),
            "fields": ("advances_to_deduct",),
        }),
        ("Attendance calculation", {
            "description": (
                "Salary is reduced for approved full-day and half-day leave. Saturdays are excluded "
                "from the working-day count; pending or rejected requests are not deducted."
            ),
            "fields": (
                "gross_salary_display", "attendance_working_days", "attendance_present_days",
                "attendance_worked_hours", "attendance_leave_units", "attendance_deduction_display",
            ),
        }),
    )

    @admin.display(description="Salary before attendance")
    def gross_salary_display(self, obj):
        if not obj or not obj.pk:
            return "Calculated when saved"
        return f"NPR {obj.salary_before_attendance:,.2f}"

    @admin.display(description="Approved leave deduction")
    def attendance_deduction_display(self, obj):
        if not obj or not obj.pk:
            return "Calculated when saved"
        return f"NPR {obj.attendance_deduction:,.2f}"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(member__user=request.user)
        return queryset.select_related("member").prefetch_related("advances", "payments")

    def get_form(self, request, obj=None, **kwargs):
        return _restrict_member_field_to_user(super().get_form(request, obj, **kwargs), request)

    def get_autocomplete_fields(self, request):
        return self.autocomplete_fields if request.user.is_superuser else ()

    def get_list_filter(self, request):
        return self.list_filter if request.user.is_superuser else ("salary_month",)

    def has_add_permission(self, request):
        return super().has_add_permission(request) and (
            request.user.is_superuser or _payroll_members_for(request).exists()
        )

    def has_view_permission(self, request, obj=None):
        allowed = super().has_view_permission(request, obj)
        return allowed and (
            obj is None or request.user.is_superuser or obj.member.user_id == request.user.id
        )

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        return allowed and (
            obj is None or request.user.is_superuser or obj.member.user_id == request.user.id
        )

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        return allowed and (
            obj is None or request.user.is_superuser or obj.member.user_id == request.user.id
        )

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and obj.member.user_id != request.user.id:
            raise PermissionDenied("You can save only your own salary record.")
        super().save_model(request, obj, form, change)

    @admin.display(description="Team member", ordering="member__name")
    def member_display(self, obj):
        return format_html(
            '<span class="salary-member"><strong>{}</strong><small>{}</small></span>',
            obj.member.name,
            obj.member.designation,
        )

    @admin.display(description="Salary month", ordering="salary_month")
    def salary_month_display(self, obj):
        return obj.salary_month.strftime("%B %Y")

    @admin.display(description="Salary after attendance")
    def salary_display(self, obj):
        return f"NPR {obj.salary_amount:,.2f}"

    @admin.display(description="Leave deduction")
    def attendance_deduction_list(self, obj):
        return f"NPR {obj.attendance_deduction:,.2f}"

    @admin.display(description="Advance")
    def advance_display(self, obj):
        return f"NPR {obj.advance_total:,.2f}"

    @admin.display(description="Paid")
    def paid_display(self, obj):
        return f"NPR {obj.payment_total:,.2f}"

    @admin.display(description="Pending")
    def pending_display(self, obj):
        return format_html("<strong>{}</strong>", f"NPR {obj.pending_amount:,.2f}")

    @admin.display(description="Status")
    def status_display(self, obj):
        css_class = {
            "Paid": "is-paid",
            "Partly paid": "is-partial",
            "Awaiting payment": "is-pending",
        }[obj.payment_status]
        return format_html('<span class="salary-status {}">{}</span>', css_class, obj.payment_status)

    @admin.display(description="Actions")
    def record_actions(self, obj):
        edit_url = reverse("admin:Ivory_salaryrecord_change", args=(obj.pk,))
        if obj.pending_amount:
            pay_url = reverse("admin:salary_record_pay", args=(obj.pk,))
            return format_html(
                '<span class="salary-actions"><a class="button" href="{}">Details / advance</a>'
                '<a class="button salary-pay" href="{}">Pay &amp; create invoice</a></span>',
                edit_url,
                pay_url,
            )
        latest = obj.payments.first()
        if latest:
            invoice_url = reverse("admin:salary_payment_invoice", args=(latest.public_id,))
            return format_html(
                '<span class="salary-actions"><a class="button" href="{}">View</a>'
                '<a class="button" href="{}" target="_blank">Invoice</a></span>',
                edit_url,
                invoice_url,
            )
        return format_html('<a class="button" href="{}">View</a>', edit_url)

    def response_add(self, request, obj, post_url_continue=None):
        if "_save_and_pay" in request.POST:
            self.message_user(
                request,
                "Monthly salary saved. Confirm the payment to generate its invoice.",
                level=messages.SUCCESS,
            )
            return redirect(reverse("admin:salary_record_pay", args=(obj.pk,)))
        self.message_user(
            request,
            "Monthly salary saved as awaiting payment. Use Details / advance or Pay & create invoice when ready.",
            level=messages.INFO,
        )
        return super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        if "_save_and_pay" in request.POST and obj.pending_amount:
            self.message_user(
                request,
                "Monthly salary updated. Confirm the payment to generate its invoice.",
                level=messages.SUCCESS,
            )
            return redirect(reverse("admin:salary_record_pay", args=(obj.pk,)))
        return super().response_change(request, obj)

    def get_urls(self):
        custom_urls = [
            path(
                "member-salary/<int:member_id>/",
                self.admin_site.admin_view(self.member_salary_view),
                name="salary_record_member_salary",
            ),
            path(
                "member-advances/<int:member_id>/",
                self.admin_site.admin_view(self.member_advances_view),
                name="salary_record_member_advances",
            ),
            path(
                "<int:object_id>/pay/",
                self.admin_site.admin_view(self.pay_salary_view),
                name="salary_record_pay",
            ),
            path(
                "payments/<uuid:public_id>/invoice/",
                self.admin_site.admin_view(self.salary_invoice_view),
                name="salary_payment_invoice",
            ),
        ]
        return custom_urls + super().get_urls()

    def member_salary_view(self, request, member_id):
        member = get_object_or_404(_payroll_members_for(request), pk=member_id)
        if not (self.has_add_permission(request) or self.has_view_permission(request)):
            return HttpResponseForbidden("You do not have permission to view monthly salaries.")
        return JsonResponse({
            "member": member.name,
            "monthly_salary": str(member.monthly_salary) if member.monthly_salary else None,
        })

    def member_advances_view(self, request, member_id):
        if not (self.has_add_permission(request) or self.has_view_permission(request)):
            return HttpResponseForbidden("You do not have permission to view monthly salaries.")
        record_id = request.GET.get("record")
        member = get_object_or_404(_payroll_members_for(request), pk=member_id)
        advances = SalaryAdvance.objects.filter(member=member).filter(
            Q(salary_record__isnull=True) | Q(salary_record_id=record_id)
        ).order_by("given_on", "pk")
        return JsonResponse({
            "advances": [
                {
                    "id": advance.pk,
                    "amount": str(advance.amount),
                    "given_on": advance.given_on.isoformat(),
                    "note": advance.note,
                    "selected": bool(record_id) and str(advance.salary_record_id) == str(record_id),
                }
                for advance in advances
            ],
        })

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        selected = form.cleaned_data.get("advances_to_deduct", SalaryAdvance.objects.none())
        SalaryAdvance.objects.filter(salary_record=form.instance).exclude(
            pk__in=selected.values("pk")
        ).update(salary_record=None)
        selected.update(salary_record=form.instance)

    def pay_salary_view(self, request, object_id):
        record = get_object_or_404(
            self.get_queryset(request),
            pk=object_id,
        )
        if not self.has_change_permission(request, record):
            return HttpResponseForbidden("You do not have permission to record salary payments.")
        pending = record.pending_amount
        if request.method == "POST":
            form = PaySalaryForm(request.POST)
            if form.is_valid():
                with transaction.atomic():
                    locked_queryset = SalaryRecord.objects.select_for_update()
                    if not request.user.is_superuser:
                        locked_queryset = locked_queryset.filter(member__user=request.user)
                    locked = locked_queryset.get(pk=record.pk)
                    locked_pending = locked.pending_amount
                    amount = form.cleaned_data["amount"]
                    if amount > locked_pending:
                        form.add_error(
                            "amount",
                            f"Payment cannot be greater than the NPR {locked_pending:,.2f} pending balance.",
                        )
                    else:
                        payment = SalaryPayment.objects.create(
                            salary_record=locked,
                            amount=amount,
                            paid_on=form.cleaned_data["paid_on"],
                            note=form.cleaned_data["note"],
                        )
                        self.message_user(
                            request,
                            f"Salary payment recorded. Invoice {payment.invoice_number} is ready.",
                            level=messages.SUCCESS,
                        )
                        return redirect(reverse("admin:salary_payment_invoice", args=(payment.public_id,)))
        else:
            form = PaySalaryForm(initial={"amount": pending, "paid_on": timezone.localdate()})
        context = {
            **self.admin_site.each_context(request),
            "title": f"Pay {record.member.name}",
            "opts": self.model._meta,
            "record": record,
            "form": form,
            "change_url": reverse("admin:Ivory_salaryrecord_change", args=(record.pk,)),
        }
        return TemplateResponse(request, "admin/salary_record_pay.html", context)

    def salary_invoice_view(self, request, public_id):
        payments = SalaryPayment.objects.select_related("salary_record__member")
        if not request.user.is_superuser:
            payments = payments.filter(salary_record__member__user=request.user)
        payment = get_object_or_404(
            payments,
            public_id=public_id,
        )
        if not self.has_view_permission(request, payment.salary_record):
            return HttpResponseForbidden("You do not have permission to view this salary invoice.")
        return salary_invoice_response(payment)

    class Media:
        css = {"all": ("admin/payroll.css",)}
        js = ("admin/payroll.js",)


@admin.register(ClientProjectAccount)
class ClientProjectAccountAdmin(ModelAdmin):
    form = ClientProjectAccountAdminForm
    inlines = (ClientProjectPaymentInline,)
    change_list_template = "admin/client_project_account_change_list.html"
    change_form_template = "admin/client_project_account_change_form.html"
    list_display = (
        "client_display",
        "project_started_on",
        "agreed_display",
        "received_display",
        "remaining_display",
        "status_display",
        "account_actions",
    )
    list_filter = ("project_started_on",)
    search_fields = ("client_name", "client_location", "notes")
    ordering = ("-project_started_on", "client_name")
    date_hierarchy = "project_started_on"
    save_on_top = True

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            ("Client and project", {
                "description": "Record the client, location, project date, and total amount agreed for the project.",
                "fields": ("client_name", "client_location", "project_started_on", "agreed_amount", "notes"),
            }),
        ]
        if obj is None:
            fieldsets.append(("First transaction", {
                "description": "Enter the advance received now. Saving creates this transaction and opens its invoice.",
                "fields": ("initial_advance", "advance_received_on"),
            }))
        return fieldsets

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("payments")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            payment = ClientProjectPayment.objects.create(
                account=obj,
                amount=form.cleaned_data["initial_advance"],
                paid_on=form.cleaned_data["advance_received_on"],
                note="Initial project advance",
            )
            obj._created_payment = payment

    @admin.display(description="Client", ordering="client_name")
    def client_display(self, obj):
        return format_html(
            '<span class="salary-member"><strong>{}</strong><small>{}</small></span>',
            obj.client_name,
            obj.client_location,
        )

    @admin.display(description="Project amount")
    def agreed_display(self, obj):
        return f"NPR {obj.agreed_amount:,.2f}"

    @admin.display(description="Received")
    def received_display(self, obj):
        return f"NPR {obj.payment_total:,.2f}"

    @admin.display(description="Remaining")
    def remaining_display(self, obj):
        return format_html("<strong>{}</strong>", f"NPR {obj.remaining_amount:,.2f}")

    @admin.display(description="Status")
    def status_display(self, obj):
        css_class = {
            "Paid": "is-paid",
            "Partly paid": "is-partial",
            "Awaiting payment": "is-pending",
        }[obj.payment_status]
        return format_html('<span class="salary-status {}">{}</span>', css_class, obj.payment_status)

    @admin.display(description="Actions")
    def account_actions(self, obj):
        details_url = reverse("admin:Ivory_clientprojectaccount_change", args=(obj.pk,))
        if obj.remaining_amount:
            pay_url = reverse("admin:client_project_account_pay", args=(obj.pk,))
            return format_html(
                '<span class="salary-actions"><a class="button" href="{}">Details</a>'
                '<a class="button salary-pay" href="{}">Add payment &amp; invoice</a></span>',
                details_url,
                pay_url,
            )
        latest = obj.payments.first()
        if latest:
            invoice_url = reverse("admin:client_project_payment_invoice", args=(latest.public_id,))
            return format_html(
                '<span class="salary-actions"><a class="button" href="{}">Details</a>'
                '<a class="button" href="{}" target="_blank">Latest invoice</a></span>',
                details_url,
                invoice_url,
            )
        return format_html('<a class="button" href="{}">Details</a>', details_url)

    def response_add(self, request, obj, post_url_continue=None):
        payment = getattr(obj, "_created_payment", None) or obj.payments.first()
        if payment:
            self.message_user(
                request,
                f"Client account and advance saved. Invoice {payment.invoice_number} is ready.",
                level=messages.SUCCESS,
            )
            return redirect(reverse("admin:client_project_payment_invoice", args=(payment.public_id,)))
        return super().response_add(request, obj, post_url_continue)

    def get_urls(self):
        custom_urls = [
            path(
                "<int:object_id>/add-payment/",
                self.admin_site.admin_view(self.add_payment_view),
                name="client_project_account_pay",
            ),
            path(
                "payments/<uuid:public_id>/invoice/",
                self.admin_site.admin_view(self.payment_invoice_view),
                name="client_project_payment_invoice",
            ),
        ]
        return custom_urls + super().get_urls()

    def add_payment_view(self, request, object_id):
        account = get_object_or_404(self.get_queryset(request), pk=object_id)
        if not self.has_change_permission(request, account):
            return HttpResponseForbidden("You do not have permission to record client payments.")
        pending = account.remaining_amount
        if pending == 0:
            self.message_user(request, "This client account is already fully paid.", level=messages.INFO)
            return redirect(reverse("admin:Ivory_clientprojectaccount_change", args=(account.pk,)))
        if request.method == "POST":
            form = AddClientPaymentForm(request.POST)
            if form.is_valid():
                with transaction.atomic():
                    locked = ClientProjectAccount.objects.select_for_update().get(pk=account.pk)
                    amount = form.cleaned_data["amount"]
                    if amount > locked.remaining_amount:
                        form.add_error(
                            "amount",
                            f"Payment cannot be greater than the NPR {locked.remaining_amount:,.2f} remaining balance.",
                        )
                    else:
                        payment = ClientProjectPayment.objects.create(
                            account=locked,
                            amount=amount,
                            paid_on=form.cleaned_data["paid_on"],
                            note=form.cleaned_data["note"],
                        )
                        self.message_user(
                            request,
                            f"Client payment recorded. Invoice {payment.invoice_number} is ready.",
                            level=messages.SUCCESS,
                        )
                        return redirect(reverse("admin:client_project_payment_invoice", args=(payment.public_id,)))
        else:
            form = AddClientPaymentForm(initial={"amount": pending, "paid_on": timezone.localdate()})
        context = {
            **self.admin_site.each_context(request),
            "title": f"Add payment for {account.client_name}",
            "opts": self.model._meta,
            "account": account,
            "form": form,
            "change_url": reverse("admin:Ivory_clientprojectaccount_change", args=(account.pk,)),
        }
        return TemplateResponse(request, "admin/client_project_account_pay.html", context)

    def payment_invoice_view(self, request, public_id):
        payment = get_object_or_404(
            ClientProjectPayment.objects.select_related("account"),
            public_id=public_id,
        )
        if not self.has_view_permission(request, payment.account):
            return HttpResponseForbidden("You do not have permission to view this client invoice.")
        return client_payment_invoice_response(payment)

    class Media:
        css = {"all": ("admin/payroll.css",)}


@admin.register(ClientProjectPayment)
class ClientProjectPaymentAdmin(ModelAdmin):
    list_display = (
        "invoice_number_display", "client_display", "amount_display", "paid_on",
        "remaining_after_display", "invoice_link",
    )
    list_filter = ("paid_on",)
    search_fields = ("account__client_name", "account__client_location", "invoice_year", "invoice_sequence", "note")
    ordering = ("-paid_on", "-pk")
    readonly_fields = (
        "public_id", "account", "amount", "paid_on", "note",
        "invoice_number_display", "created_at", "invoice_link",
    )
    fields = readonly_fields

    @admin.display(description="Invoice")
    def invoice_number_display(self, obj):
        return obj.invoice_number

    @admin.display(description="Client", ordering="account__client_name")
    def client_display(self, obj):
        return obj.account.client_name

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return f"NPR {obj.amount:,.2f}"

    @admin.display(description="Remaining now")
    def remaining_after_display(self, obj):
        return f"NPR {obj.account.remaining_amount:,.2f}"

    @admin.display(description="PDF")
    def invoice_link(self, obj):
        url = reverse("admin:client_project_payment_invoice", args=(obj.public_id,))
        return format_html('<a class="button" href="{}" target="_blank">Open invoice</a>', url)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("account").prefetch_related("account__payments")

    class Media:
        css = {"all": ("admin/payroll.css",)}


@admin.register(SalaryAdvance)
class SalaryAdvanceAdmin(ModelAdmin):
    form = SalaryAdvanceAdminForm
    fieldsets = (
        ("Advance details", {
            "description": (
                "Record money given in advance. It remains unused until a superuser selects it "
                "inside a monthly salary record."
            ),
            "fields": ("member", "amount", "given_on", "note"),
        }),
    )
    list_display = ("member_display", "amount_display", "given_on", "deduction_status", "note", "salary_link")
    list_filter = ("given_on", "salary_record__salary_month", "salary_record__member")
    search_fields = ("member__name", "note")
    ordering = ("-given_on", "-pk")

    @admin.display(description="Team member", ordering="member__name")
    def member_display(self, obj):
        return obj.member.name

    @admin.display(description="Salary month", ordering="salary_record__salary_month")
    def salary_month(self, obj):
        return obj.salary_record.salary_month.strftime("%B %Y") if obj.salary_record else "Not deducted"

    @admin.display(description="Status")
    def deduction_status(self, obj):
        if obj.salary_record:
            return f"Deducted from {obj.salary_record.salary_month:%B %Y}"
        return "Available for deduction"

    @admin.display(description="Advance amount")
    def amount_display(self, obj):
        return f"NPR {obj.amount:,.2f}"

    @admin.display(description="Monthly salary")
    def salary_link(self, obj):
        if not obj.salary_record_id:
            return "Not deducted yet"
        url = reverse("admin:Ivory_salaryrecord_change", args=(obj.salary_record_id,))
        return format_html('<a class="button" href="{}">Open monthly salary</a>', url)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(member__user=request.user)
        return queryset.select_related("member", "salary_record")

    def get_form(self, request, obj=None, **kwargs):
        return _restrict_member_field_to_user(super().get_form(request, obj, **kwargs), request)

    def get_list_filter(self, request):
        if request.user.is_superuser:
            return self.list_filter
        return ("given_on", "salary_record__salary_month")

    def has_add_permission(self, request):
        return super().has_add_permission(request) and (
            request.user.is_superuser or _payroll_members_for(request).exists()
        )

    def has_view_permission(self, request, obj=None):
        allowed = super().has_view_permission(request, obj)
        return allowed and (
            obj is None or request.user.is_superuser or obj.member.user_id == request.user.id
        )

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        return allowed and (
            obj is None or request.user.is_superuser or obj.member.user_id == request.user.id
        )

    def has_delete_permission(self, request, obj=None):
        allowed = super().has_delete_permission(request, obj)
        return allowed and (
            obj is None or request.user.is_superuser or obj.member.user_id == request.user.id
        )

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and obj.member.user_id != request.user.id:
            raise PermissionDenied("You can save only your own salary advance.")
        super().save_model(request, obj, form, change)

    class Media:
        css = {"all": ("admin/payroll.css",)}


@admin.register(SalaryPayment)
class SalaryPaymentAdmin(ModelAdmin):
    list_display = ("invoice_number_display", "member_display", "salary_month", "amount_display", "paid_on", "invoice_link")
    list_filter = ("paid_on", "salary_record__member")
    search_fields = ("salary_record__member__name", "invoice_year", "invoice_sequence", "note")
    ordering = ("-paid_on", "-pk")
    readonly_fields = ("public_id", "salary_record", "amount", "paid_on", "note", "invoice_number_display", "created_at", "invoice_link")
    fields = readonly_fields

    @admin.display(description="Invoice")
    def invoice_number_display(self, obj):
        return obj.invoice_number

    @admin.display(description="Team member", ordering="salary_record__member__name")
    def member_display(self, obj):
        return obj.salary_record.member.name

    @admin.display(description="Salary month", ordering="salary_record__salary_month")
    def salary_month(self, obj):
        return obj.salary_record.salary_month.strftime("%B %Y")

    @admin.display(description="Amount")
    def amount_display(self, obj):
        return f"NPR {obj.amount:,.2f}"

    @admin.display(description="PDF")
    def invoice_link(self, obj):
        url = reverse("admin:salary_payment_invoice", args=(obj.public_id,))
        return format_html('<a class="button" href="{}" target="_blank">Open invoice</a>', url)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(salary_record__member__user=request.user)
        return queryset.select_related("salary_record__member")

    class Media:
        css = {"all": ("admin/payroll.css",)}


@admin.register(CustomFAQ)
class CustomFAQAdmin(EditButtonAdmin):
    list_display = ("question", "category", "is_active", "order", "edit_button")
    list_editable = ("is_active", "order")
    list_filter = ("is_active", "category")
    search_fields = ("question", "answer", "aliases")
from .models import (
    AboutCompany, PopupAd, Client, BusinessInformation,
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
class ContactMessageAdmin(ModelAdmin):

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

class ProjectImageInline(StackedInline):
    model = ProjectImage
    form = DirectProjectGalleryImageForm
    extra = 1
    fields = ("image_upload", "caption", "description", "order")


@admin.register(Project)
class ProjectAdmin(EditButtonAdmin):
    form = DirectProjectImageForm
    inlines = (ProjectImageInline,)
    fields = (
        "name", "category", "description", "image_upload",
        "location", "year", "featured",
    )

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

    class Media:
        js = ("admin/project-image-upload.js",)
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

class TeamPortfolioInline(StackedInline):
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
    fieldsets = (
        ("Member details", {
            "fields": ("name", "category", "designation", "photo", "bio", "website_url"),
        }),
        ("Payroll", {
            "description": (
                "Set the default salary and link the staff login. A linked non-superuser can see only "
                "this member's salary records and advances."
            ),
            "fields": ("monthly_salary", "user"),
        }),
        ("Publishing", {
            "fields": ("order", "is_active"),
        }),
    )

    list_display = (
        "name",
        "category",
        "designation",
        "user",
        "monthly_salary_display",
        "website_url",
        "salary_records_button",
        "order",
        "is_active",
        "edit_button",
    )

    list_filter = (
        "is_active",
        "category",
        "designation",
    )

    search_fields = (
        "name",
        "designation",
        "user__username",
        "bio",
        "website_url",
    )

    list_editable = (
        "order",
        "is_active",
    )

    ordering = (
        "order",
        "name",
    )

    @admin.display(description="MONTHLY SALARY", ordering="monthly_salary")
    def monthly_salary_display(self, obj):
        if obj.monthly_salary is None:
            return "Not set"
        return f"NPR {obj.monthly_salary:,.2f}"

    @admin.display(description="SALARY")
    def salary_records_button(self, obj):
        url = reverse("admin:Ivory_salaryrecord_changelist")
        count = obj.salary_records.count()
        return format_html(
            '<a class="button" href="{}?member__id__exact={}">{} record{}</a>',
            url,
            obj.pk,
            count,
            "" if count == 1 else "s",
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


class BusinessSocialProfileInline(TabularInline):
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


class SupportMessageInline(TabularInline):
    model = SupportMessage
    extra = 0
    can_delete = False
    fields = ("sequence", "sender_type", "sender_user", "body", "created_at")
    readonly_fields = fields
    ordering = ("sequence",)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SupportConversation)
class SupportConversationAdmin(ModelAdmin):
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
class SupportMessageAdmin(ModelAdmin):
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
