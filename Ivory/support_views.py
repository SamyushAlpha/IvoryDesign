import json
import time
import uuid

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse, FileResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_POST

from .models import SupportConversation, SupportAttachment
from .support_uploads import validate_upload
from .support import (
    active_conversation,
    add_visitor_message,
    claim_conversation,
    conversation_history,
    request_ip_key,
    resolve_conversation,
    same_origin,
    serialize_conversation,
    serialize_message,
    staff_reply,
    visitor_key_for_request,
    start_conversation, assign_assistant,
)

MAX_BODY_BYTES = 8192
MAX_VISITOR_MESSAGE = 600
MAX_STAFF_MESSAGE = 1800


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _body(request, required):
    if request.content_type != "application/json":
        raise ValidationError("Send JSON data.")
    if int(request.META.get("CONTENT_LENGTH") or 0) > MAX_BODY_BYTES:
        raise ValidationError("The message is too long.")
    try:
        raw = request.body
        if len(raw) > MAX_BODY_BYTES:
            raise ValidationError("The message is too long.")
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Send valid JSON data.")
    if not isinstance(payload, dict) or set(payload) != set(required):
        raise ValidationError("Send only the required support fields.")
    return payload


def _bounded_text(value, limit):
    if not isinstance(value, str):
        raise ValidationError("Enter a text message.")
    value = value.strip()
    if not value or len(value) > limit or any(ord(char) < 32 and char not in "\n\t\r" for char in value):
        raise ValidationError(f"Enter a message between 1 and {limit} characters.")
    return value


def _uuid(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Invalid message identifier.")


def _message_payload(request, limit):
    attachment = None
    if request.content_type == "multipart/form-data":
        if int(request.META.get("CONTENT_LENGTH") or 0) > settings.IVORY_SUPPORT_UPLOAD_BYTES + 16384:
            raise ValidationError("Upload is too large.")
        if set(request.POST) != {"message", "client_message_id"} or set(request.FILES) != {"file"} or len(request.FILES.getlist("file")) != 1:
            raise ValidationError("Send one attachment at a time.")
        attachment = validate_upload(request.FILES["file"])
        payload = request.POST
    else:
        payload = _body(request, ("message", "client_message_id"))
    text = _bounded_text(payload["message"] or ("Shared a file." if attachment else ""), limit)
    return text, _uuid(payload["client_message_id"]), attachment


@never_cache
@csrf_protect
@require_POST
def visitor_start(request):
    if not same_origin(request):
        return _error("Please use the Ivory website.", 403)
    key = visitor_key_for_request(request)
    conversation = start_conversation(key)
    request.session["ivory_support_conversation"] = str(conversation.public_id)
    return JsonResponse({"conversation": serialize_conversation(conversation),
                         "messages": [serialize_message(m) for m in conversation.support_messages.all()]})


def _rate_limit(request, visitor_key):
    now = int(time.time())
    window = settings.IVORY_SUPPORT_RATE_WINDOW
    bucket = now // window
    keys = [
        f"ivory-support-session:{visitor_key}:{bucket}",
        f"ivory-support-ip:{request_ip_key(request)}:{bucket}",
    ]
    for key in keys:
        cache.add(key, 0, timeout=window + 2)
        try:
            count = cache.incr(key)
        except ValueError:
            cache.add(key, 1, timeout=window + 2)
            count = 1
        if count > settings.IVORY_SUPPORT_RATE_LIMIT:
            return max(1, window - now % window)
    return None


@never_cache
@require_GET
def visitor_history(request):
    visitor_key = visitor_key_for_request(request)
    conversation = None
    saved_id = request.session.get("ivory_support_conversation")
    if saved_id:
        conversation = SupportConversation.objects.filter(public_id=saved_id, visitor_key=visitor_key).first()
    conversation = conversation or active_conversation(visitor_key)
    if not conversation:
        return JsonResponse({"conversation": None, "messages": []})
    request.session["ivory_support_conversation"] = str(conversation.public_id)
    # Closed chat widgets poll without clearing unread staff replies. Opening the
    # chat uses the default value and marks those replies as read.
    mark_read = request.GET.get("mark_read", "1") != "0"
    messages = conversation_history(conversation, mark_read=mark_read)
    conversation.refresh_from_db()
    return JsonResponse({
        "conversation": serialize_conversation(conversation),
        "messages": [serialize_message(message) for message in messages],
    })


@never_cache
@csrf_protect
@require_POST
def visitor_message(request):
    if not same_origin(request):
        return _error("Please use support on the Ivory Design website.", 403)
    try:
        text, client_message_id, attachment = _message_payload(request, MAX_VISITOR_MESSAGE)
    except ValidationError as exc:
        return _error(exc.messages[0])
    visitor_key = visitor_key_for_request(request)
    if attachment and not SupportConversation.objects.filter(visitor_key=visitor_key).exclude(visitor_name="").exists():
        return _error("Please tell us your name before uploading a file.")
    retry_after = _rate_limit(request, visitor_key)
    if retry_after:
        response = _error("Please pause before sending another message.", 429)
        response["Retry-After"] = str(retry_after)
        return response
    try:
        conversation, message, automated, duplicate = add_visitor_message(visitor_key, text, client_message_id, attachment)
    except ValidationError as exc:
        return _error(exc.messages[0])
    request.session["ivory_support_conversation"] = str(conversation.public_id)
    return JsonResponse({
        "conversation": serialize_conversation(conversation),
        "messages": [serialize_message(item) for item in [message, *automated]],
        "duplicate": duplicate,
    })


def _require_support_permission(request, permission="Ivory.view_supportconversation"):
    if not request.user.has_perm(permission):
        raise PermissionDenied


@never_cache
@staff_member_required
def staff_inbox(request):
    _require_support_permission(request)
    return render(request, "admin/support_inbox.html", {
        "title": "Live support inbox",
        "can_change_support": request.user.has_perm("Ivory.change_supportconversation"),
    })


@never_cache
@staff_member_required
@require_GET
def staff_conversations(request):
    _require_support_permission(request)
    status = request.GET.get("status", "active")
    queryset = SupportConversation.objects.select_related("assigned_to")
    if status == "active":
        queryset = queryset.exclude(status=SupportConversation.Status.RESOLVED)
    elif status in SupportConversation.Status.values:
        queryset = queryset.filter(status=status)
    else:
        return _error("Unknown conversation filter.")
    conversations = list(queryset.order_by("-last_activity_at")[:100])
    return JsonResponse({"conversations": [serialize_conversation(item, include_private=True) for item in conversations]})


@never_cache
@staff_member_required
@require_GET
def staff_history(request, public_id):
    _require_support_permission(request)
    conversation = get_object_or_404(SupportConversation.objects.select_related("assigned_to"), public_id=public_id)
    messages = conversation_history(conversation, for_staff=True)
    conversation.refresh_from_db()
    return JsonResponse({
        "conversation": serialize_conversation(conversation, include_private=True),
        "messages": [serialize_message(message) for message in messages],
    })


def _staff_post(request, public_id, action):
    _require_support_permission(request, "Ivory.change_supportconversation")
    if not same_origin(request):
        return _error("Use the protected support inbox.", 403)
    try:
        result = action()
    except (ValidationError, SupportConversation.DoesNotExist) as exc:
        message = exc.messages[0] if isinstance(exc, ValidationError) else "Conversation not found."
        return _error(message, 409 if isinstance(exc, ValidationError) else 404)
    conversation = result[0] if isinstance(result, tuple) else result
    return JsonResponse({"conversation": serialize_conversation(conversation, include_private=True)})


@never_cache
@csrf_protect
@staff_member_required
@require_POST
def staff_claim(request, public_id):
    return _staff_post(request, public_id, lambda: claim_conversation(public_id, request.user))


@never_cache
@csrf_protect
@staff_member_required
@require_POST
def staff_assign_assistant(request, public_id):
    return _staff_post(request, public_id, lambda: assign_assistant(public_id))


@never_cache
@csrf_protect
@staff_member_required
@require_POST
def staff_resolve(request, public_id):
    return _staff_post(request, public_id, lambda: resolve_conversation(public_id, request.user))


@never_cache
@csrf_protect
@staff_member_required
@require_POST
def staff_message(request, public_id):
    _require_support_permission(request, "Ivory.change_supportconversation")
    if not same_origin(request):
        return _error("Use the protected support inbox.", 403)
    try:
        text, client_message_id, attachment = _message_payload(request, MAX_STAFF_MESSAGE)
    except ValidationError as exc:
        return _error(exc.messages[0])
    return _staff_post(
        request,
        public_id,
        lambda: staff_reply(public_id, request.user, text, client_message_id, attachment),
    )


@never_cache
@require_GET
def attachment_download(request, public_id):
    attachment = get_object_or_404(SupportAttachment.objects.select_related("message__conversation"), public_id=public_id)
    user = request.user
    staff = user.is_active and user.is_staff and user.has_perm("Ivory.view_supportconversation")
    if not staff and attachment.message.conversation.visitor_key != visitor_key_for_request(request):
        raise PermissionDenied
    inline = attachment.content_type.startswith(("image/", "audio/")) and request.GET.get("download") != "1"
    response = FileResponse(attachment.file.open("rb"), content_type=attachment.content_type,
                            as_attachment=not inline, filename=attachment.filename)
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Security-Policy"] = "default-src 'none'; sandbox"
    response["Cache-Control"] = "private, no-store"
    return response
