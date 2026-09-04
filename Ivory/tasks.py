from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from .models import SupportConversation
from .support import activate_bot


@shared_task(ignore_result=True, acks_late=True)
def activate_bot_if_unanswered(conversation_id, handoff_token):
    """Idempotent delayed handoff; the database is the source of truth."""
    result = activate_bot(conversation_id, handoff_token)
    if result is False:
        conversation = SupportConversation.objects.filter(pk=conversation_id).first()
        if conversation and conversation.bot_deadline:
            delay = max(1, int((conversation.bot_deadline - timezone.now()).total_seconds()))
            activate_bot_if_unanswered.apply_async(
                args=[conversation_id, handoff_token],
                countdown=delay,
            )


@shared_task(ignore_result=True)
def activate_due_support_conversations():
    """Restart-safe reconciliation for delayed broker messages."""
    due = list(
        SupportConversation.objects.filter(
            status=SupportConversation.Status.WAITING,
            first_staff_reply_at__isnull=True,
            bot_deadline__lte=timezone.now(),
        ).values_list("pk", "handoff_token")[:500]
    )
    for conversation_id, token in due:
        activate_bot(conversation_id, token)
    return len(due)


@shared_task(ignore_result=True)
def delete_expired_support_conversations():
    cutoff = timezone.now() - timedelta(days=settings.IVORY_SUPPORT_RETENTION_DAYS)
    deleted, _ = SupportConversation.objects.filter(
        status=SupportConversation.Status.RESOLVED,
        resolved_at__lt=cutoff,
    ).delete()
    return deleted
