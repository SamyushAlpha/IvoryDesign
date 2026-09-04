import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from config.asgi import application
from .models import SupportConversation, SupportMessage
from .support import (
    BOT_TAKEOVER_MESSAGE,
    activate_bot,
    add_visitor_message,
    claim_conversation,
    normalize_phone,
    staff_reply,
    validate_name,
    visitor_key_from_seed,
)
from .tasks import activate_due_support_conversations, delete_expired_support_conversations


TEST_CHANNELS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


@override_settings(CHANNEL_LAYERS=TEST_CHANNELS, IVORY_SUPPORT_TIMEOUT_SECONDS=300)
class SupportServiceTests(TestCase):
    def setUp(self):
        self.key = visitor_key_from_seed("test-visitor-seed")
        self.user = get_user_model().objects.create_user("designer", password="test", first_name="Asha")

    def conversation(self, **kwargs):
        values = {
            "visitor_key": self.key,
            "bot_deadline": timezone.now() - timedelta(seconds=1),
        }
        values.update(kwargs)
        return SupportConversation.objects.create(**values)

    def test_message_sender_constraints_and_sequence(self):
        conversation = self.conversation()
        invalid = SupportMessage(conversation=conversation, sender_type="staff", sequence=1, body="Hello")
        with self.assertRaises(ValidationError):
            invalid.full_clean()
        first = SupportMessage.objects.create(conversation=conversation, sender_type="visitor", sequence=1, body="Hi")
        self.assertEqual(str(first), "Visitor #1")

    def test_timeout_is_idempotent(self):
        conversation = self.conversation()
        self.assertIsNotNone(activate_bot(conversation.pk, conversation.handoff_token))
        self.assertIsNone(activate_bot(conversation.pk, conversation.handoff_token))
        conversation.refresh_from_db()
        self.assertEqual(conversation.status, SupportConversation.Status.BOT_HANDLED)
        self.assertEqual(conversation.lead_state, SupportConversation.LeadState.AWAITING_NAME)
        self.assertEqual(conversation.support_messages.filter(body=BOT_TAKEOVER_MESSAGE).count(), 1)

    def test_staff_reply_wins_timeout_race(self):
        conversation = self.conversation()
        old_token = conversation.handoff_token
        staff_reply(conversation.public_id, self.user, "Hello from the team", uuid.uuid4())
        self.assertIsNone(activate_bot(conversation.pk, old_token))
        conversation.refresh_from_db()
        self.assertEqual(conversation.status, SupportConversation.Status.HUMAN_ACTIVE)
        self.assertEqual(conversation.handoff_state, SupportConversation.HandoffState.STAFF)
        self.assertEqual(conversation.support_messages.filter(sender_type="assistant").count(), 0)

    def test_staff_can_take_over_after_bot(self):
        conversation = self.conversation()
        activate_bot(conversation.pk, conversation.handoff_token)
        claim_conversation(conversation.public_id, self.user)
        conversation.refresh_from_db()
        self.assertEqual(conversation.status, SupportConversation.Status.HUMAN_ACTIVE)
        self.assertEqual(conversation.assigned_to, self.user)
        self.assertIn("Asha", conversation.support_messages.last().body)

    def test_restart_reconciliation_activates_due_only_once(self):
        conversation = self.conversation()
        activate_due_support_conversations.run()
        activate_due_support_conversations.run()
        conversation.refresh_from_db()
        self.assertEqual(conversation.status, SupportConversation.Status.BOT_HANDLED)
        self.assertEqual(conversation.support_messages.filter(sender_type="assistant").count(), 1)

    @override_settings(IVORY_SUPPORT_RETENTION_DAYS=90)
    def test_resolved_retention_deletes_only_expired_threads(self):
        old = self.conversation(status="resolved", resolved_at=timezone.now() - timedelta(days=91))
        recent = self.conversation(status="resolved", resolved_at=timezone.now() - timedelta(days=2))
        delete_expired_support_conversations.run()
        self.assertFalse(SupportConversation.objects.filter(pk=old.pk).exists())
        self.assertTrue(SupportConversation.objects.filter(pk=recent.pk).exists())

    def test_lead_capture_validation_correction_and_local_faq(self):
        conversation = self.conversation()
        activate_bot(conversation.pk, conversation.handoff_token)
        with patch("Ivory.support.broadcast_conversation"):
            add_visitor_message(self.key, "7", uuid.uuid4())
            conversation.refresh_from_db()
            self.assertEqual(conversation.lead_state, SupportConversation.LeadState.AWAITING_NAME)
            self.assertIn("name", conversation.support_messages.last().body.lower())

            add_visitor_message(self.key, "Sita Gautam", uuid.uuid4())
            conversation.refresh_from_db()
            self.assertEqual(conversation.visitor_name, "Sita Gautam")
            self.assertEqual(conversation.lead_state, SupportConversation.LeadState.AWAITING_PHONE)

            add_visitor_message(self.key, "9812345678", uuid.uuid4())
            conversation.refresh_from_db()
            self.assertEqual(conversation.visitor_phone, "+9779812345678")
            self.assertEqual(conversation.lead_state, SupportConversation.LeadState.COMPLETE)

            add_visitor_message(self.key, "change my phone to +9779800000000", uuid.uuid4())
            add_visitor_message(self.key, "change my name to Sita Sharma", uuid.uuid4())
            conversation.refresh_from_db()
            self.assertEqual(conversation.visitor_phone, "+9779800000000")
            self.assertEqual(conversation.visitor_name, "Sita Sharma")

            with patch("openai.OpenAI") as sdk:
                add_visitor_message(self.key, "What services do you offer?", uuid.uuid4())
                sdk.assert_not_called()
            self.assertIn("interior architecture", conversation.support_messages.last().body)

    def test_name_phone_helpers_reject_bad_values(self):
        for value in ("1", "123 Name", "<script>"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_name(value)
        for value in ("123", "+012345678", "not a phone"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize_phone(value)


@override_settings(
    CHANNEL_LAYERS=TEST_CHANNELS,
    IVORY_SUPPORT_TIMEOUT_SECONDS=300,
    IVORY_SUPPORT_RATE_LIMIT=3,
    IVORY_SUPPORT_RATE_WINDOW=60,
)
class SupportHttpTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.client.get(reverse("home"))
        self.csrf = self.client.cookies["csrftoken"].value
        self.url = reverse("support_visitor_message")

    def post(self, message="Hello", message_id=None, client=None, **headers):
        origin = headers.pop("HTTP_ORIGIN", "http://testserver")
        return (client or self.client).post(
            self.url,
            json.dumps({"message": message, "client_message_id": str(message_id or uuid.uuid4())}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
            HTTP_ORIGIN=origin,
            **headers,
        )

    @patch("Ivory.support._schedule_takeover")
    def test_send_persists_waiting_conversation_and_reconnect_history(self, schedule):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post("I need help with my apartment")
        self.assertEqual(response.status_code, 200)
        conversation = SupportConversation.objects.get()
        self.assertEqual(conversation.status, "waiting")
        self.assertEqual(conversation.staff_unread_count, 1)
        self.assertEqual(conversation.support_messages.get().body, "I need help with my apartment")
        schedule.assert_called_once()
        history = self.client.get(reverse("support_visitor_history")).json()
        self.assertEqual(history["conversation"]["id"], str(conversation.public_id))
        self.assertEqual(history["messages"][0]["body"], "I need help with my apartment")
        self.assertEqual(Client().get(reverse("support_visitor_history")).json()["messages"], [])

    @patch("Ivory.support._schedule_takeover")
    def test_client_message_id_is_idempotent(self, schedule):
        message_id = uuid.uuid4()
        first = self.post("Hello", message_id)
        second = self.post("Hello", message_id)
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(SupportMessage.objects.count(), 1)

    def test_csrf_origin_payload_and_length_protection(self):
        no_csrf = Client(enforce_csrf_checks=True).post(self.url, "{}", content_type="application/json")
        self.assertEqual(no_csrf.status_code, 403)
        self.assertEqual(self.post("Hello", HTTP_ORIGIN="https://evil.example").status_code, 403)
        bad = self.client.post(
            self.url,
            json.dumps({"message": "Hello", "client_message_id": str(uuid.uuid4()), "history": []}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf,
            HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.post("x" * 601).status_code, 400)

    @patch("Ivory.support._schedule_takeover")
    def test_session_and_ip_rate_limit(self, schedule):
        for _ in range(3):
            self.assertEqual(self.post().status_code, 200)
        limited = self.post()
        self.assertEqual(limited.status_code, 429)
        self.assertIn("Retry-After", limited)

    def test_staff_inbox_permissions_and_actions(self):
        conversation = SupportConversation.objects.create(visitor_key="a" * 40)
        regular = get_user_model().objects.create_user("regular", password="test")
        staff = get_user_model().objects.create_user("staff", password="test", is_staff=True)
        self.client.force_login(regular)
        self.assertEqual(self.client.get(reverse("support_inbox")).status_code, 302)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("support_inbox")).status_code, 403)
        staff.user_permissions.add(*Permission.objects.filter(codename__in=["view_supportconversation", "change_supportconversation"]))
        staff = get_user_model().objects.get(pk=staff.pk)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("support_inbox")).status_code, 200)
        for status in ("active", "waiting", "bot_handled", "human_active", "resolved"):
            with self.subTest(status=status):
                response = self.client.get(reverse("support_staff_conversations"), {"status": status})
                self.assertEqual(response.status_code, 200)
                self.assertIn("conversations", response.json())
                ids = [item["id"] for item in response.json()["conversations"]]
                if status in ("active", "waiting"):
                    self.assertIn(str(conversation.public_id), ids)
                else:
                    self.assertNotIn(str(conversation.public_id), ids)
        self.assertEqual(
            self.client.get(reverse("support_staff_conversations"), {"status": "invalid"}).status_code,
            400,
        )
        claim = self.client.post(
            reverse("support_staff_claim", args=[conversation.public_id]),
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
            HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(claim.status_code, 200)
        reply = self.client.post(
            reverse("support_staff_message", args=[conversation.public_id]),
            json.dumps({"message": "Hello from staff", "client_message_id": str(uuid.uuid4())}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value,
            HTTP_ORIGIN="http://testserver",
        )
        self.assertEqual(reply.status_code, 200)
        conversation.refresh_from_db()
        self.assertEqual(conversation.assigned_to, staff)
        self.assertEqual(conversation.support_messages.filter(sender_type="staff").count(), 1)


@override_settings(CHANNEL_LAYERS=TEST_CHANNELS)
class SupportWebSocketTests(TransactionTestCase):
    reset_sequences = True

    def cookie_header(self, client):
        return "; ".join(f"{key}={morsel.value}" for key, morsel in client.cookies.items()).encode()

    def test_visitor_authorization_and_delivery(self):
        client = Client()
        client.get(reverse("support_visitor_history"))
        seed = client.session["ivory_support_seed"]
        conversation = SupportConversation.objects.create(visitor_key=visitor_key_from_seed(seed))
        async_to_sync(self._visitor_authorization_and_delivery)(client, conversation)

    async def _visitor_authorization_and_delivery(self, client, conversation):
        unauthorized = WebsocketCommunicator(
            application,
            f"/ws/support/{conversation.public_id}/",
            headers=[(b"origin", b"http://testserver")],
        )
        connected, _ = await unauthorized.connect()
        self.assertFalse(connected)
        communicator = WebsocketCommunicator(
            application,
            f"/ws/support/{conversation.public_id}/",
            headers=[(b"origin", b"http://testserver"), (b"cookie", self.cookie_header(client))],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        self.assertEqual((await communicator.receive_json_from())["kind"], "connected")
        await get_channel_layer().group_send(
            f"ivory_support_{conversation.public_id.hex}",
            {"type": "support.event", "event": {"kind": "conversation", "messages": [{"body": "Live"}]}},
        )
        self.assertEqual((await communicator.receive_json_from())["messages"][0]["body"], "Live")
        await communicator.disconnect()

    def test_staff_websocket_requires_permission(self):
        async_to_sync(self._staff_websocket_requires_permission)()

    async def _staff_websocket_requires_permission(self):
        from asgiref.sync import sync_to_async

        user = await sync_to_async(get_user_model().objects.create_superuser)("owner", "owner@example.com", "test")
        client = Client()
        await sync_to_async(client.force_login)(user)
        communicator = WebsocketCommunicator(
            application,
            "/ws/support/staff/",
            headers=[(b"origin", b"http://testserver"), (b"cookie", self.cookie_header(client))],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        self.assertEqual((await communicator.receive_json_from())["kind"], "connected")
        await communicator.disconnect()
