import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from . import chat
from .models import ContactMessage


@override_settings(OPENAI_API_KEY="", OPENAI_CHAT_MODEL="gpt-4.1-mini")
class StudioReplyTests(TestCase):
    def test_faqs_cover_published_facts_without_calling_openai(self):
        questions = {
            "Hello!": chat.ABOUT,
            "What services do you offer?": chat.SERVICES,
            "Show me your portfolio": chat.PORTFOLIO,
            "How long does a renovation take?": chat.CONSULTATION,
        }
        with patch("openai.OpenAI") as sdk:
            for question, expected in questions.items():
                with self.subTest(question=question):
                    self.assertEqual(chat.chat_reply(question), (expected, "faq"))
            reply, source = chat.chat_reply("Where are you located?")
            self.assertEqual(source, "faq")
            for fact in ("Kathmandu", "+977 9825776806", "hello@ivorydesign.com"):
                self.assertIn(fact, reply)
            for question in ("How do I start a project?", "What are your prices?", "Book a consultation"):
                reply, source = chat.chat_reply(question)
                self.assertEqual(source, "faq")
                self.assertIn("Contact form", reply)
            sdk.assert_not_called()

    @override_settings(OPENAI_API_KEY="test-only-not-a-real-key")
    def test_faqs_remain_first_even_with_key(self):
        with patch("openai.OpenAI") as sdk:
            self.assertEqual(chat.chat_reply("What are your services?"), (chat.SERVICES, "faq"))
            sdk.assert_not_called()

    def test_no_key_returns_useful_contact_fallback(self):
        with patch("openai.OpenAI") as sdk:
            self.assertEqual(chat.chat_reply("Help with lighting a small room"), (chat.UNAVAILABLE, "fallback"))
            sdk.assert_not_called()

    @override_settings(OPENAI_API_KEY="test-only-not-a-real-key")
    def test_unrelated_question_does_not_use_paid_api(self):
        with patch("openai.OpenAI") as sdk:
            self.assertEqual(chat.chat_reply("Who won yesterday's football game?"), (chat.FALLBACK, "fallback"))
            sdk.assert_not_called()

    @override_settings(OPENAI_API_KEY="test-only-not-a-real-key", OPENAI_CHAT_MODEL="gpt-4.1-mini")
    def test_official_responses_flow_is_stateless_and_bounded(self):
        question = "Suggest lighting for a small room"
        with patch("openai.OpenAI") as sdk:
            api = sdk.return_value.__enter__.return_value
            api.responses.create.return_value = SimpleNamespace(status="completed", output_text=" General guidance: layer your lighting. ")
            self.assertEqual(chat.chat_reply(question), ("General guidance: layer your lighting.", "ai"))
        sdk.assert_called_once_with(
            api_key="test-only-not-a-real-key", base_url="https://api.openai.com/v1", timeout=12.0, max_retries=0,
        )
        api.responses.create.assert_called_once_with(
            model="gpt-4.1-mini", instructions=chat.INSTRUCTIONS, input=question,
            max_output_tokens=320, store=False,
        )
        for instruction in ("Never invent prices", "Admit uncertainty", "/contact/", "not a general chatbot"):
            self.assertIn(instruction, chat.INSTRUCTIONS)
        self.assertNotIn("test-only-not-a-real-key", chat.INSTRUCTIONS)
        sdk.return_value.__exit__.assert_called_once()

    @override_settings(OPENAI_API_KEY="test-only-not-a-real-key")
    def test_sdk_errors_return_fallback_without_logging_sensitive_details(self):
        for failure in (TimeoutError, ConnectionError, RuntimeError):
            with self.subTest(failure=failure), patch("openai.OpenAI") as sdk:
                sdk.return_value.__enter__.return_value.responses.create.side_effect = failure("private-question test-only-not-a-real-key")
                with self.assertLogs("Ivory.chat", level="WARNING") as logs:
                    self.assertEqual(chat.chat_reply("Suggest a room design"), (chat.UNAVAILABLE, "fallback"))
                self.assertIn(failure.__name__, logs.output[0])
                self.assertNotIn("private-question", "".join(logs.output))
                self.assertNotIn("test-only-not-a-real-key", "".join(logs.output))

    @override_settings(OPENAI_API_KEY="test-only-not-a-real-key")
    def test_empty_incomplete_or_excessive_model_output(self):
        for status, output in (("completed", "  "), ("incomplete", "Partial"), ("failed", "Failed")):
            with self.subTest(status=status), patch("openai.OpenAI") as sdk:
                sdk.return_value.__enter__.return_value.responses.create.return_value = SimpleNamespace(status=status, output_text=output)
                self.assertEqual(chat.chat_reply("Suggest a room design"), (chat.UNAVAILABLE, "fallback"))
        with patch("openai.OpenAI") as sdk:
            sdk.return_value.__enter__.return_value.responses.create.return_value = SimpleNamespace(status="completed", output_text="x" * 2000)
            self.assertEqual(len(chat.chat_reply("Suggest a room design")[0]), 1800)


@override_settings(OPENAI_API_KEY="")
class ChatEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("chat_ask")

    def post(self, payload, client=None, **extra):
        return (client or self.client).post(self.url, data=json.dumps(payload), content_type="application/json", **extra)

    def test_valid_faq_returns_json_and_is_not_cacheable(self):
        response = self.post({"message": "  What services do you offer?  "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"reply": chat.SERVICES, "source": "faq"})
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIn("no-store", response["Cache-Control"])

    def test_get_and_other_methods_are_rejected(self):
        for method in ("get", "head", "put", "delete", "options"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(self.url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response["Allow"], "POST")

    def test_content_type_and_malformed_json(self):
        self.assertEqual(self.client.post(self.url, {"message": "hello"}).status_code, 415)
        for body in (b"{", b"\xff", b" "):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(self.url, body, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.generic("POST", self.url, b"", CONTENT_TYPE="application/json").status_code, 400)

    def test_invalid_input_and_history_are_rejected_before_answering(self):
        invalid = (None, [], "hello", {}, {"message": None}, {"message": 17}, {"message": []},
                   {"message": ""}, {"message": " \n\t "}, {"message": "x" * 601},
                   {"message": "hello\u0000"}, {"message": "hi", "history": ["private"]})
        with patch("Ivory.chat.chat_reply") as reply:
            for payload in invalid:
                with self.subTest(payload=payload):
                    self.assertEqual(self.post(payload).status_code, 400)
            reply.assert_not_called()

    def test_maximum_length_and_unicode(self):
        for message in ("x" * 600, "नमस्ते Ivory Design", "Room\nlighting\tideas"):
            with self.subTest(message=message):
                self.assertEqual(self.post({"message": message}).status_code, 200)

    def test_oversized_body_is_rejected(self):
        self.assertEqual(self.post({"message": "x" * chat.MAX_BODY_BYTES}).status_code, 413)

    def test_per_session_rate_limit_and_reset(self):
        with patch("Ivory.chat.time.time", return_value=120):
            for _ in range(chat.RATE_LIMIT):
                self.assertEqual(self.post({"message": "services"}).status_code, 200)
            with patch("Ivory.chat.chat_reply") as reply:
                limited = self.post({"message": "services"})
                self.assertEqual(limited.status_code, 429)
                self.assertEqual(limited["Retry-After"], "60")
                reply.assert_not_called()
            self.assertEqual(self.post({"message": "services"}, client=Client()).status_code, 200)
        with patch("Ivory.chat.time.time", return_value=180):
            self.assertEqual(self.post({"message": "services"}).status_code, 200)

    def test_invalid_requests_do_not_consume_rate_limit(self):
        for _ in range(chat.RATE_LIMIT + 1):
            self.assertEqual(self.post({"message": ""}).status_code, 400)
        self.assertEqual(self.post({"message": "hello"}).status_code, 200)

    def test_no_chat_transcript_or_enquiry_is_stored(self):
        self.post({"message": "private conversation sentinel"})
        session = self.client.session
        self.assertEqual(set(session.keys()), {"ivory_chat_token"})
        self.assertNotIn("private conversation sentinel", str(session.items()))
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertEqual(set(Session.objects.get(session_key=session.session_key).get_decoded()), {"ivory_chat_token"})

    def test_csrf_and_origin_are_enforced(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post({"message": "hello"}, client=client).status_code, 403)
        page = client.get(reverse("home"))
        self.assertContains(page, 'id="ivory-chat-form"')
        token = client.cookies["csrftoken"].value
        self.assertEqual(self.post({"message": "hello"}, client=client, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="http://testserver").status_code, 200)
        self.assertEqual(self.post({"message": "hello"}, client=client, HTTP_X_CSRFTOKEN="invalid").status_code, 403)
        self.assertEqual(self.post({"message": "hello"}, client=client, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://evil.example").status_code, 403)
        # Even another globally trusted origin must not access this endpoint.
        with override_settings(CSRF_TRUSTED_ORIGINS=["https://trusted.example"]):
            self.assertEqual(self.post({"message": "hello"}, client=client, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://trusted.example").status_code, 403)
        self.assertEqual(self.post({"message": "hello"}, HTTP_SEC_FETCH_SITE="cross-site").status_code, 403)

    def test_no_key_http_fallback(self):
        response = self.post({"message": "Suggest lighting for my room"})
        self.assertEqual(response.json(), {"reply": chat.UNAVAILABLE, "source": "fallback"})

    @override_settings(OPENAI_API_KEY="test-only-not-a-real-key")
    def test_mocked_ai_response_through_endpoint(self):
        with patch("openai.OpenAI") as sdk:
            api = sdk.return_value.__enter__.return_value
            api.responses.create.return_value = SimpleNamespace(status="completed", output_text="General guidance: consider layered lighting.")
            response = self.post({"message": "Suggest lighting for my room"})
            self.assertEqual(response.json(), {"reply": "General guidance: consider layered lighting.", "source": "ai"})
        self.assertNotIn("test-only-not-a-real-key", response.content.decode())

    def test_home_exposes_chat_assets_links_and_csrf_but_not_keys(self):
        with override_settings(OPENAI_API_KEY="test-only-not-a-real-key"):
            page = self.client.get(reverse("home"))
        for fragment in ('/static/chat.js', '/static/chat.css', 'name="csrfmiddlewaretoken"', 'role="log"', 'maxlength="600"', 'href="/contact/"', 'href="/projects/"'):
            self.assertContains(page, fragment)
        self.assertNotContains(page, "test-only-not-a-real-key")
        self.assertNotContains(page, 'onclick="toggleChat()"')
        self.assertNotContains(page, 'async function sendMessage')
