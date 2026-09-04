import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from . import chat


def event(kind, **kwargs):
    return SimpleNamespace(type=kind, **kwargs)


def decode_events(response):
    try:
        body = b"".join(response.streaming_content).decode()
    finally:
        response.close()
    result = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        result.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return result


@override_settings(OPENAI_API_KEY="test-only-not-a-real-key", OPENAI_CHAT_MODEL="gpt-4.1-mini")
class ChatStreamingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("chat_ask")
        self.sdk_patch = patch("openai.OpenAI")
        self.sdk = self.sdk_patch.start()
        self.addCleanup(self.sdk_patch.stop)
        self.api = self.sdk.return_value.__enter__.return_value
        self.stream = self.api.responses.create.return_value
        self.entered = self.stream.__enter__.return_value

    def post(self, message="Suggest lighting for my room", client=None, **headers):
        return (client or self.client).post(self.url, json.dumps({"message": message}), content_type="application/json", HTTP_ACCEPT="text/event-stream", **headers)

    def events(self, events):
        self.entered.__iter__.return_value = iter(events)

    def test_streams_only_text_deltas_in_order_with_no_provider_metadata(self):
        self.events([
            event("response.created", id="private-response-id"),
            event("response.reasoning_text.delta", delta="private reasoning"),
            event("response.output_text.delta", delta="General guidance: "),
            event("response.output_text.delta", delta="warm light.\nनमस्ते <img src=x>"),
            event("response.output_text.done", text="do not duplicate this"),
            event("response.completed", response=SimpleNamespace()),
        ])
        response = self.post()
        self.assertTrue(response.streaming)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        self.assertIn("no-transform", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        frames = decode_events(response)
        self.assertEqual(frames, [
            ("start", {"source": "ai"}),
            ("delta", {"text": "General guidance: "}),
            ("delta", {"text": "warm light.\nनमस्ते <img src=x>"}),
            ("done", {"source": "ai"}),
        ])
        self.api.responses.create.assert_called_once_with(
            model="gpt-4.1-mini", instructions=chat.INSTRUCTIONS,
            input="Suggest lighting for my room", max_output_tokens=320, store=False, stream=True,
        )
        self.stream.__exit__.assert_called_once()
        self.sdk.return_value.__exit__.assert_called_once()

    def test_response_is_lazy_and_yields_before_whole_generation(self):
        consumed = []
        def upstream():
            consumed.append("first")
            yield event("response.output_text.delta", delta="First ")
            consumed.append("second")
            yield event("response.output_text.delta", delta="second")
            yield event("response.completed", response=SimpleNamespace())
        self.entered.__iter__.return_value = upstream()
        response = self.post()
        self.sdk.assert_not_called()
        iterator = iter(response.streaming_content)
        self.assertIn(b"event: start", next(iterator))
        self.assertIn(b"First", next(iterator))
        self.assertEqual(consumed, ["first"])
        response.close()  # Simulates client disconnect; no continuation or retry.
        self.assertEqual(consumed, ["first"])
        self.stream.__exit__.assert_called_once()
        self.sdk.return_value.__exit__.assert_called_once()

    def test_faq_and_no_key_return_json_for_local_typewriter(self):
        response = self.post("services")
        self.assertFalse(response.streaming)
        self.assertEqual(response.json(), {"reply": chat.SERVICES, "source": "faq"})
        with override_settings(OPENAI_API_KEY=""):
            response = self.post()
        self.assertEqual(response.json(), {"reply": chat.UNAVAILABLE, "source": "fallback"})
        self.sdk.assert_not_called()

    def test_api_start_failure_is_safe_typewriter_fallback_without_retry(self):
        failure = RuntimeError("private-question test-only-not-a-real-key")
        failure.status_code = 429
        failure.body = {"error": {"code": "insufficient_quota", "message": "private error"}}
        self.api.responses.create.side_effect = failure
        with self.assertLogs("Ivory.chat", level="WARNING") as logs:
            frames = decode_events(self.post())
        self.assertEqual(frames[-2:], [("reply", {"reply": chat.UNAVAILABLE, "source": "fallback"}), ("done", {"source": "fallback"})])
        self.assertIn("billing_or_quota", logs.output[0])
        for secret in ("private-question", "test-only-not-a-real-key", "private error"):
            self.assertNotIn(secret, str(frames) + str(logs.output))
        self.api.responses.create.assert_called_once()
        self.sdk.return_value.__exit__.assert_called_once()

    def test_midstream_failure_replaces_partial_answer(self):
        def upstream():
            yield event("response.output_text.delta", delta="Unfinished advice")
            raise ConnectionError("secret exception")
        self.entered.__iter__.return_value = upstream()
        with self.assertLogs("Ivory.chat", level="WARNING"):
            frames = decode_events(self.post())
        self.assertEqual(frames[1][0], "delta")
        self.assertEqual(frames[-2], ("reply", {"reply": chat.UNAVAILABLE, "source": "fallback"}))
        self.stream.__exit__.assert_called_once()

    def test_failed_incomplete_error_or_missing_completion_is_not_success(self):
        for kind in ("response.failed", "response.incomplete", "error", "response.refusal.delta"):
            with self.subTest(kind=kind):
                self.events([event(kind, message="private error", delta="refusal")])
                with self.assertLogs("Ivory.chat", level="WARNING"):
                    frames = decode_events(self.post())
                self.assertEqual(frames[-1], ("done", {"source": "fallback"}))
                self.assertNotIn("private error", str(frames))

    def test_empty_completed_stream_falls_back_and_final_only_text_is_supported(self):
        self.events([event("response.completed", response=SimpleNamespace(output_text=""))])
        self.assertEqual(decode_events(self.post())[-1], ("done", {"source": "fallback"}))
        self.events([event("response.completed", response=SimpleNamespace(output_text="General guidance."))])
        self.assertEqual(decode_events(self.post())[-2:], [("reply", {"reply": "General guidance.", "source": "ai"}), ("done", {"source": "ai"})])

    def test_stream_output_and_duration_are_bounded(self):
        self.events([event("response.output_text.delta", delta="x" * (chat.MAX_REPLY_LENGTH + 1))])
        with self.assertLogs("Ivory.chat", level="WARNING"):
            frames = decode_events(self.post())
        self.assertNotIn("x" * (chat.MAX_REPLY_LENGTH + 1), str(frames))
        self.assertEqual(frames[-1], ("done", {"source": "fallback"}))
        self.events([event("response.output_text.delta", delta="Too late")])
        with patch("Ivory.chat.time.monotonic", side_effect=[0, chat.MAX_STREAM_SECONDS + 1]), self.assertLogs("Ivory.chat", level="WARNING"):
            self.assertEqual(decode_events(self.post())[-1], ("done", {"source": "fallback"}))

    def test_stream_requests_share_rate_limit_and_validate_before_api(self):
        with patch("Ivory.chat.time.time", return_value=120):
            for _ in range(chat.RATE_LIMIT):
                self.assertEqual(self.post("services").status_code, 200)
            self.assertEqual(self.post().status_code, 429)
            self.assertEqual(self.client.post(self.url, json.dumps({"message": "services"}), content_type="application/json").status_code, 429)
        self.assertEqual(self.post("x" * 601).status_code, 400)
        self.assertEqual(self.post("x" * 9000).status_code, 413)
        self.assertEqual(self.client.get(self.url, HTTP_ACCEPT="text/event-stream").status_code, 405)
        self.sdk.assert_not_called()

    def test_stream_csrf_same_origin_and_stateless_session(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post(client=client).status_code, 403)
        client.get(reverse("home"))
        token = client.cookies["csrftoken"].value
        self.assertEqual(self.post(client=client, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="https://evil.example").status_code, 403)
        self.events([event("response.output_text.delta", delta="General guidance."), event("response.completed", response=SimpleNamespace())])
        response = self.post(client=client, HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="http://testserver")
        self.assertTrue(response.streaming)
        decode_events(response)
        self.assertEqual(set(client.session.keys()), {"ivory_chat_token"})


class ChatRoutingDiagnosticTests(TestCase):
    @override_settings(OPENAI_API_KEY="test-only-not-a-real-key")
    def test_general_design_questions_not_swallowed_by_faqs(self):
        for question in ("How much light does a bedroom need?", "How long should curtains be?", "Which rug works with a dark sofa?", "Suggest colours for an apartment"):
            with self.subTest(question=question):
                self.assertIsNone(chat.local_reply(question))
        self.assertEqual(chat.local_reply("How long does a renovation take?"), (chat.CONSULTATION, "faq"))
        reply, source = chat.local_reply("What is the price of a consultation?")
        self.assertEqual(source, "faq")
        self.assertIn("No confirmed per-square-foot rate", reply)

    def test_diagnostic_categories_are_allowlisted(self):
        for status, expected in ((401, "authentication"), (403, "permission"), (404, "model_access"), (429, "rate_limit"), (500, "connection_or_service")):
            failure = RuntimeError("secret error")
            failure.status_code = status
            self.assertEqual(chat.failure_category(failure), expected)
        for body in ({"code": "insufficient_quota"}, {"error": {"type": "insufficient_quota"}}):
            failure.body = body
            self.assertEqual(chat.failure_category(failure), "billing_or_quota")
