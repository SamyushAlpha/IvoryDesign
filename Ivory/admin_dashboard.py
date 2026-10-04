from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from .models import (
    AttendanceRecord,
    ClientProjectAccount,
    SalaryRecord,
    SiteStatistics,
    SupportConversation,
)


def _money(value):
    return f"NPR {Decimal(value):,.2f}"


def dashboard_callback(request, context):
    today = timezone.localdate()
    statistics = SiteStatistics.objects.first()
    client_accounts = ClientProjectAccount.objects.prefetch_related("payments")
    salary_records = SalaryRecord.objects.filter(
        salary_month__year=today.year,
        salary_month__month=today.month,
    ).prefetch_related("advances", "payments")

    client_outstanding = sum(
        (account.remaining_amount for account in client_accounts),
        Decimal("0.00"),
    )
    client_collected = sum(
        (account.payment_total for account in client_accounts),
        Decimal("0.00"),
    )
    salary_outstanding = sum(
        (record.pending_amount for record in salary_records),
        Decimal("0.00"),
    )
    pending_leave = AttendanceRecord.objects.filter(
        approval_status=AttendanceRecord.ApprovalStatus.PENDING,
    ).count()
    open_support = SupportConversation.objects.exclude(
        status=SupportConversation.Status.RESOLVED,
    ).count()

    context.update({
        "ivory_today": today,
        "ivory_metrics": [
            {
                "label": "Website visits",
                "value": f"{statistics.total_visits:,}" if statistics else "0",
                "detail": "All-time visits",
                "icon": "monitoring",
            },
            {
                "label": "Open support chats",
                "value": f"{open_support:,}",
                "detail": "Waiting or active conversations",
                "icon": "forum",
                "url": reverse("support_inbox"),
            },
            {
                "label": "Total client payments collected",
                "value": _money(client_collected),
                "detail": "All recorded client payments",
                "icon": "savings",
                "url": reverse("admin:Ivory_clientprojectpayment_changelist"),
            },
            {
                "label": "Client balance due",
                "value": _money(client_outstanding),
                "detail": f"Across {client_accounts.count()} project accounts",
                "icon": "account_balance_wallet",
                "url": reverse("admin:Ivory_clientprojectaccount_changelist"),
            },
            {
                "label": "Salary balance due",
                "value": _money(salary_outstanding),
                "detail": today.strftime("For %B %Y"),
                "icon": "payments",
                "url": reverse("admin:Ivory_salaryrecord_changelist"),
            },
        ],
        "ivory_pending_leave": pending_leave,
        "ivory_quick_actions": [
            {"label": "Open Live Support", "icon": "forum", "url": reverse("support_inbox")},
            {"label": "Add client account", "icon": "person_add", "url": reverse("admin:Ivory_clientprojectaccount_add")},
            {"label": "Review attendance", "icon": "how_to_reg", "url": reverse("admin:Ivory_attendancerecord_changelist")},
            {"label": "Create monthly salary", "icon": "payments", "url": reverse("admin:Ivory_salaryrecord_add")},
        ],
    })
    return context
