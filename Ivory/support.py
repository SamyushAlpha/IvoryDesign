import logging
import re
import secrets
import uuid
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.signing import salted_hmac
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .chat import chat_reply, local_reply
from .models import SupportConversation, SupportMessage, SupportAttachment

logger = logging.getLogger(__name__)

BOT_TAKEOVER_MESSAGE = (
    "I’m the automated Ivory Design assistant. A team member wasn’t able to reply "
    "within five minutes. I can help with studio FAQs and collect contact details "
    "so the team can follow up. With your permission, please share your name first. "
    "We’ll use your name and phone only to contact you about this enquiry."
)
PHONE_PROMPT = (
    "Thank you, {name}. Please share a phone number in international format, for "
    "example +9779812345678. Ivory Design will use it only to follow up about this enquiry."
)
LEAD_COMPLETE = (
    "Thank you. Your contact details are saved for the Ivory Design team. I’m the "
    "automated assistant and can now help with services, portfolio, location, pricing "
    "guidance, or requesting a consultation. A staff member can join at any time."
)


def ensure_visitor_seed(session):
    seed = session.get("ivory_support_seed")
    if not seed:
        seed = secrets.token_urlsafe(32)
        session["ivory_support_seed"] = seed
    return seed


def visitor_key_from_seed(seed):
    return salted_hmac("ivory.support.visitor", seed).hexdigest()


def visitor_key_for_request(request):
    return visitor_key_from_seed(ensure_visitor_seed(request.session))


def visitor_key_for_scope(scope):
    seed = scope["session"].get("ivory_support_seed")
    return visitor_key_from_seed(seed) if seed else None


def request_ip_key(request):
    address = request.META.get("REMOTE_ADDR", "unknown")
    if settings.IVORY_TRUST_PROXY_HEADERS:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            address = forwarded.split(",", 1)[0].strip() or address
    return salted_hmac("ivory.support.ip", address).hexdigest()


def same_origin(request):
    origin = request.headers.get("Origin")
    return not (
        (origin and origin != f"{request.scheme}://{request.get_host()}")
        or request.headers.get("Sec-Fetch-Site") == "cross-site"
    )


def _staff_name(user):
    return (user.get_full_name() or user.get_username() or "Ivory team member").strip()


def conversation_group(public_id):
    return f"ivory_support_{public_id.hex}"


def serialize_message(message):
    label = {
        SupportMessage.SenderType.VISITOR: "You",
        SupportMessage.SenderType.ASSISTANT: "Automated assistant",
        SupportMessage.SenderType.SYSTEM: "Ivory Design",
    }.get(message.sender_type, _staff_name(message.sender_user) if message.sender_user else "Ivory team member")
    return {
        "id": message.pk,
        "sequence": message.sequence,
        "sender": message.sender_type,
        "label": label,
        "body": message.body,
        "created_at": message.created_at.isoformat(),
        "attachments": [{"id": str(a.public_id), "name": a.filename, "type": a.content_type,
                         "size": a.size, "duration": a.duration,
                         "url": f"/chatbox/support/files/{a.public_id}/"} for a in message.attachments.all()],
    }


def serialize_conversation(conversation, include_private=False):
    assigned_name = _staff_name(conversation.assigned_to) if conversation.assigned_to else ""
    payload = {
        "id": str(conversation.public_id),
        "status": conversation.status,
        "status_label": conversation.get_status_display(),
        "handoff_state": conversation.handoff_state,
        "assigned_name": assigned_name,
        "lead_state": conversation.lead_state,
        "visitor_name": conversation.visitor_name,
        "last_activity_at": conversation.last_activity_at.isoformat(),
        "visitor_unread_count": conversation.visitor_unread_count,
    }
    if include_private:
        payload.update(
            visitor_name=conversation.visitor_name,
            visitor_phone=conversation.visitor_phone,
            staff_unread_count=conversation.staff_unread_count,
            created_at=conversation.created_at.isoformat(),
        )
    return payload


def _broadcast(group, event):
    try:
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(group, {"type": "support.event", "event": event})
    except Exception as exc:
        logger.warning("Support broadcast unavailable (%s).", type(exc).__name__)


def broadcast_conversation(conversation, messages=()):
    public_event = {
        "kind": "conversation",
        "conversation": serialize_conversation(conversation),
        "messages": [serialize_message(message) for message in messages],
    }
    staff_event = {
        "kind": "conversation",
        "conversation": serialize_conversation(conversation, include_private=True),
        "messages": [serialize_message(message) for message in messages],
    }
    _broadcast(conversation_group(conversation.public_id), public_event)
    _broadcast("ivory_support_staff", staff_event)


def _next_sequence(conversation):
    return (conversation.support_messages.aggregate(value=Max("sequence"))["value"] or 0) + 1


def _message(conversation, sender_type, body, *, user=None, client_message_id=None):
    message = SupportMessage(
        conversation=conversation,
        sender_type=sender_type,
        sender_user=user,
        client_message_id=client_message_id,
        sequence=_next_sequence(conversation),
        body=body,
        read_by_staff=sender_type != SupportMessage.SenderType.VISITOR,
        read_by_visitor=sender_type == SupportMessage.SenderType.VISITOR,
    )
    message.full_clean()
    message.save()
    return message


def _schedule_takeover(conversation):
    from .tasks import activate_bot_if_unanswered

    delay = max(0, int((conversation.bot_deadline - timezone.now()).total_seconds()))
    try:
        activate_bot_if_unanswered.apply_async(
            args=[conversation.pk, str(conversation.handoff_token)],
            countdown=delay,
        )
    except Exception as exc:
        # The database deadline remains durable and the periodic reconciliation
        # will recover once workers return. Never fail the visitor's saved send.
        logger.warning("Support handoff scheduling unavailable (%s).", type(exc).__name__)


def active_conversation(visitor_key):
    return (
        SupportConversation.objects.filter(visitor_key=visitor_key)
        .exclude(status=SupportConversation.Status.RESOLVED)
        .order_by("-created_at")
        .first()
    )


def start_conversation(visitor_key):
    conversation = active_conversation(visitor_key)
    if conversation:
        return conversation
    previous = SupportConversation.objects.filter(visitor_key=visitor_key).exclude(visitor_name="").first()
    with transaction.atomic():
        conversation = SupportConversation.objects.create(
            visitor_key=visitor_key, visitor_name=previous.visitor_name if previous else "",
            lead_state=SupportConversation.LeadState.NOT_STARTED if previous else SupportConversation.LeadState.AWAITING_NAME,
        )
        body = (f"Welcome back, {conversation.visitor_name}. How can the Ivory Design team help?" if previous else
                "Welcome to Ivory Design. I’m the automated welcome assistant. What name should our team use? We save your name with this conversation so we can help you.")
        message = _message(conversation, SupportMessage.SenderType.ASSISTANT, body)
        transaction.on_commit(lambda: broadcast_conversation(conversation, [message]))
    return conversation


def conversation_history(conversation, *, for_staff=False):
    messages = list(conversation.support_messages.select_related("sender_user").all())
    if for_staff:
        conversation.support_messages.filter(sender_type=SupportMessage.SenderType.VISITOR, read_by_staff=False).update(read_by_staff=True)
        if conversation.staff_unread_count:
            conversation.staff_unread_count = 0
            conversation.save(update_fields=["staff_unread_count", "updated_at"])
    else:
        conversation.support_messages.exclude(sender_type=SupportMessage.SenderType.VISITOR).filter(read_by_visitor=False).update(read_by_visitor=True)
        if conversation.visitor_unread_count:
            conversation.visitor_unread_count = 0
            conversation.save(update_fields=["visitor_unread_count", "updated_at"])
    return messages


def validate_name(value):
    value = " ".join(value.strip().split())
    if not 2 <= len(value) <= 80 or any(ch.isdigit() or ch in "<>" for ch in value):
        raise ValidationError("Please enter a name between 2 and 80 characters without numbers.")
    if len([ch for ch in value if ch.isalpha()]) < 2:
        raise ValidationError("Please enter your name using letters.")
    return value


def normalize_phone(value):
    value = value.strip()
    value = re.sub(r"[\s().-]", "", value)
    if value.startswith("00"):
        value = "+" + value[2:]
    if re.fullmatch(r"9[678]\d{8}", value):
        value = "+977" + value
    if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
        raise ValidationError("Please use a valid international number, such as +9779812345678.")
    return value


def _lead_reply_locked(conversation, text):
    messages = []
    if conversation.lead_state == SupportConversation.LeadState.AWAITING_NAME:
        try:
            conversation.visitor_name = validate_name(text)
        except ValidationError as exc:
            messages.append(_message(conversation, SupportMessage.SenderType.ASSISTANT, exc.messages[0]))
            return messages
        conversation.lead_state = SupportConversation.LeadState.AWAITING_PHONE
        messages.append(_message(conversation, SupportMessage.SenderType.ASSISTANT, PHONE_PROMPT.format(name=conversation.visitor_name)))
        return messages
    if conversation.lead_state == SupportConversation.LeadState.AWAITING_PHONE:
        if text.casefold().strip() in {"skip", "no thanks", "prefer not to say"}:
            conversation.lead_state = SupportConversation.LeadState.COMPLETE
            return [_message(conversation, SupportMessage.SenderType.ASSISTANT, "That’s fine—you can continue without a phone number. How can I help with Ivory Design?")]
        from .chat import faq_reply
        faq = faq_reply(text)
        if faq:
            return [_message(conversation, SupportMessage.SenderType.ASSISTANT, faq)]
        try:
            conversation.visitor_phone = normalize_phone(text)
        except ValidationError as exc:
            messages.append(_message(conversation, SupportMessage.SenderType.ASSISTANT, exc.messages[0]))
            return messages
        conversation.lead_state = SupportConversation.LeadState.COMPLETE
        messages.append(_message(conversation, SupportMessage.SenderType.ASSISTANT, LEAD_COMPLETE))
        return messages

    name_match = re.fullmatch(r"(?:change|correct|update)\s+(?:my\s+)?name\s*(?:to|:)?\s*(.+)", text, re.I)
    phone_match = re.fullmatch(r"(?:change|correct|update)\s+(?:my\s+)?phone(?:\s+number)?\s*(?:to|:)?\s*(.+)", text, re.I)
    if name_match:
        try:
            conversation.visitor_name = validate_name(name_match.group(1))
            messages.append(_message(conversation, SupportMessage.SenderType.ASSISTANT, "Your name has been corrected for the team."))
        except ValidationError as exc:
            messages.append(_message(conversation, SupportMessage.SenderType.ASSISTANT, exc.messages[0]))
    elif phone_match:
        try:
            conversation.visitor_phone = normalize_phone(phone_match.group(1))
            messages.append(_message(conversation, SupportMessage.SenderType.ASSISTANT, "Your phone number has been corrected for the team."))
        except ValidationError as exc:
            messages.append(_message(conversation, SupportMessage.SenderType.ASSISTANT, exc.messages[0]))
    return messages


def add_visitor_message(visitor_key, text, client_message_id, attachment=None):
    client_message_id = uuid.UUID(str(client_message_id))
    now = timezone.now()
    needs_optional_reply = False
    with transaction.atomic():
        duplicate = SupportMessage.objects.select_related("conversation").filter(client_message_id=client_message_id).first()
        if duplicate:
            if duplicate.conversation.visitor_key != visitor_key:
                raise ValidationError("Invalid message identifier.")
            return duplicate.conversation, duplicate, [], True

        conversation = (
            SupportConversation.objects.select_for_update()
            .filter(visitor_key=visitor_key)
            .exclude(status=SupportConversation.Status.RESOLVED)
            .order_by("-created_at")
            .first()
        )
        created = conversation is None
        if created:
            conversation = SupportConversation.objects.create(
                visitor_key=visitor_key,
                bot_deadline=now + timedelta(seconds=settings.IVORY_SUPPORT_TIMEOUT_SECONDS),
            )
        visitor_message = _message(
            conversation,
            SupportMessage.SenderType.VISITOR,
            text,
            client_message_id=client_message_id,
        )
        if attachment:
            SupportAttachment.objects.create(message=visitor_message, **attachment)
        conversation.staff_unread_count += 1
        conversation.last_activity_at = now
        automated = []
        schedule = created
        if conversation.handoff_state == SupportConversation.HandoffState.WAITING and conversation.lead_state == SupportConversation.LeadState.AWAITING_NAME:
            try:
                conversation.visitor_name = validate_name(text)
                conversation.lead_state = SupportConversation.LeadState.NOT_STARTED
                body = f"Thank you, {conversation.visitor_name}. What would you like to ask our team?"
            except ValidationError as exc:
                body = exc.messages[0]
            automated.append(_message(conversation, SupportMessage.SenderType.ASSISTANT, body))
        elif conversation.handoff_state == SupportConversation.HandoffState.WAITING and not conversation.bot_deadline:
            conversation.bot_deadline = now + timedelta(seconds=settings.IVORY_SUPPORT_TIMEOUT_SECONDS)
            schedule = True
        elif conversation.handoff_state == SupportConversation.HandoffState.ASSISTANT:
            automated = _lead_reply_locked(conversation, text)
            needs_optional_reply = conversation.lead_state == SupportConversation.LeadState.COMPLETE and not automated
            conversation.visitor_unread_count += len(automated)
        conversation.save()
        transaction.on_commit(lambda: broadcast_conversation(conversation, [visitor_message, *automated]))
        if schedule:
            transaction.on_commit(lambda: _schedule_takeover(conversation))

    if needs_optional_reply:
        local = local_reply(text)
        reply, source = local if local else chat_reply(text)
        with transaction.atomic():
            current = SupportConversation.objects.select_for_update().get(pk=conversation.pk)
            if current.handoff_state == SupportConversation.HandoffState.ASSISTANT and current.status != SupportConversation.Status.RESOLVED:
                automated_message = _message(current, SupportMessage.SenderType.ASSISTANT, reply)
                current.visitor_unread_count += 1
                current.last_activity_at = timezone.now()
                current.save()
                transaction.on_commit(lambda: broadcast_conversation(current, [automated_message]))
                automated.append(automated_message)
                conversation = current
    return conversation, visitor_message, automated, False


def activate_bot(conversation_id, handoff_token, *, now=None):
    now = now or timezone.now()
    with transaction.atomic():
        conversation = SupportConversation.objects.select_for_update().filter(pk=conversation_id).first()
        if not conversation or str(conversation.handoff_token) != str(handoff_token):
            return None
        if conversation.status != SupportConversation.Status.WAITING or conversation.first_staff_reply_at:
            return None
        if not conversation.bot_deadline or conversation.bot_deadline > now:
            return False
        conversation.status = SupportConversation.Status.BOT_HANDLED
        conversation.handoff_state = SupportConversation.HandoffState.ASSISTANT
        conversation.lead_state = (SupportConversation.LeadState.AWAITING_PHONE if conversation.visitor_name else SupportConversation.LeadState.AWAITING_NAME)
        conversation.bot_takeover_at = now
        conversation.last_activity_at = now
        body = ("I’m the automated Ivory Design assistant. The team hasn’t replied yet. " + PHONE_PROMPT.format(name=conversation.visitor_name) + " You can type skip or ask a studio FAQ instead." if conversation.visitor_name else BOT_TAKEOVER_MESSAGE)
        message = _message(conversation, SupportMessage.SenderType.ASSISTANT, body)
        conversation.visitor_unread_count += 1
        conversation.save()
        transaction.on_commit(lambda: broadcast_conversation(conversation, [message]))
        return conversation


def claim_conversation(conversation_id, user):
    now = timezone.now()
    with transaction.atomic():
        conversation = SupportConversation.objects.select_for_update().get(public_id=conversation_id)
        if conversation.status == SupportConversation.Status.RESOLVED:
            raise ValidationError("This conversation is already resolved.")
        conversation.assigned_to = user
        conversation.status = SupportConversation.Status.HUMAN_ACTIVE
        conversation.handoff_state = SupportConversation.HandoffState.STAFF
        conversation.handoff_token = uuid.uuid4()
        conversation.bot_deadline = None
        conversation.last_activity_at = now
        joined = _message(
            conversation,
            SupportMessage.SenderType.SYSTEM,
            f"{_staff_name(user)} from Ivory Design joined the conversation.",
        )
        conversation.visitor_unread_count += 1
        conversation.save()
        transaction.on_commit(lambda: broadcast_conversation(conversation, [joined]))
        return conversation, joined


def assign_assistant(conversation_id):
    from .chat import faq_reply, FALLBACK
    with transaction.atomic():
        conversation = SupportConversation.objects.select_for_update().get(public_id=conversation_id)
        if conversation.status == SupportConversation.Status.RESOLVED:
            raise ValidationError("This conversation is resolved.")
        if conversation.handoff_state == SupportConversation.HandoffState.ASSISTANT:
            return conversation, None
        conversation.assigned_to = None
        conversation.status = SupportConversation.Status.BOT_HANDLED
        conversation.handoff_state = SupportConversation.HandoffState.ASSISTANT
        conversation.handoff_token = uuid.uuid4()
        conversation.bot_deadline = None
        conversation.bot_takeover_at = timezone.now()
        conversation.lead_state = (SupportConversation.LeadState.COMPLETE if conversation.visitor_phone else
                                   SupportConversation.LeadState.AWAITING_PHONE if conversation.visitor_name else
                                   SupportConversation.LeadState.AWAITING_NAME)
        pending = conversation.support_messages.filter(sender_type="visitor").last()
        answer = faq_reply(pending.body) if pending else None
        body = "I’m the automated Ivory Design FAQ assistant. " + (answer or "I can help with services, pricing guidance, our portfolio, location or consultation requests.")
        if not conversation.visitor_name:
            body += " What name should our team use?"
        elif not conversation.visitor_phone:
            body += " You may share a phone for follow-up, type skip, or continue asking studio questions."
        message = _message(conversation, SupportMessage.SenderType.ASSISTANT, body[:1800])
        conversation.visitor_unread_count += 1
        conversation.last_activity_at = timezone.now()
        conversation.save()
        transaction.on_commit(lambda: broadcast_conversation(conversation, [message]))
        return conversation, message


def staff_reply(conversation_id, user, text, client_message_id, attachment=None):
    client_message_id = uuid.UUID(str(client_message_id))
    now = timezone.now()
    with transaction.atomic():
        duplicate = SupportMessage.objects.select_related("conversation").filter(client_message_id=client_message_id).first()
        if duplicate:
            if duplicate.sender_user_id != user.pk:
                raise ValidationError("Invalid message identifier.")
            return duplicate.conversation, duplicate, True
        conversation = SupportConversation.objects.select_for_update().get(public_id=conversation_id)
        if conversation.status == SupportConversation.Status.RESOLVED:
            raise ValidationError("This conversation is already resolved.")
        conversation.assigned_to = user
        conversation.status = SupportConversation.Status.HUMAN_ACTIVE
        conversation.handoff_state = SupportConversation.HandoffState.STAFF
        conversation.handoff_token = uuid.uuid4()
        conversation.bot_deadline = None
        if not conversation.first_staff_reply_at:
            conversation.first_staff_reply_at = now
        message = _message(
            conversation,
            SupportMessage.SenderType.STAFF,
            text,
            user=user,
            client_message_id=client_message_id,
        )
        if attachment:
            SupportAttachment.objects.create(message=message, **attachment)
        conversation.visitor_unread_count += 1
        conversation.last_activity_at = now
        conversation.save()
        transaction.on_commit(lambda: broadcast_conversation(conversation, [message]))
        return conversation, message, False


def resolve_conversation(conversation_id, user):
    with transaction.atomic():
        conversation = SupportConversation.objects.select_for_update().get(public_id=conversation_id)
        if conversation.status == SupportConversation.Status.RESOLVED:
            return conversation, None
        conversation.assigned_to = conversation.assigned_to or user
        conversation.status = SupportConversation.Status.RESOLVED
        conversation.handoff_state = SupportConversation.HandoffState.STAFF
        conversation.handoff_token = uuid.uuid4()
        conversation.bot_deadline = None
        conversation.resolved_at = timezone.now()
        conversation.last_activity_at = timezone.now()
        message = _message(conversation, SupportMessage.SenderType.SYSTEM, "This conversation was marked resolved by the Ivory Design team.")
        conversation.visitor_unread_count += 1
        conversation.save()
        transaction.on_commit(lambda: broadcast_conversation(conversation, [message]))
        return conversation, message
