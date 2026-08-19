"""AI/export provider tests. Every test mocks requests.get/post/put/delete
at services.http_retry — no test reaches the network.

FR : Tests des providers IA/export. Chaque test mocke
requests.get/post/put/delete au niveau de services.http_retry — aucun
test n'atteint le réseau.
"""
import os
from unittest.mock import patch

import requests

from ..services.ai_brain_provider import AiBrainHttpProvider
from ..services.ai_provider_base import AIProviderError
from ..services.generic_webhook_provider import GenericWebhookProvider
from .common import LegalWatchTransactionCase

_HTTP_GET = "odoo.addons.legal_knowledge_watch.services.http_retry.requests.get"
_HTTP_POST = "odoo.addons.legal_knowledge_watch.services.http_retry.requests.post"
_HTTP_PUT = "odoo.addons.legal_knowledge_watch.services.http_retry.requests.put"
_HTTP_DELETE = "odoo.addons.legal_knowledge_watch.services.http_retry.requests.delete"
_SLEEP = "odoo.addons.legal_knowledge_watch.services.http_retry.time.sleep"


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}
        self.content = text.encode("utf-8") if text else b""

    def json(self):
        if self._json_data is None:
            raise ValueError("no JSON")
        return self._json_data


class TestGenericWebhookProvider(LegalWatchTransactionCase):
    def _make_provider(self, **overrides):
        vals = {
            "name": "Webhook Test",
            "provider_type": "webhook",
            "base_url": "https://example.org/webhook",
            "auth_mode": "none",
            "timeout_seconds": 10,
            "verify_tls": True,
        }
        vals.update(overrides)
        return self.env["legal.ai.provider"].create(vals)

    def test_missing_base_url_raises(self):
        provider = self._make_provider(base_url=False)
        with self.assertRaises(AIProviderError):
            GenericWebhookProvider(provider).healthcheck()

    def test_bearer_auth_without_secret_raises(self):
        provider = self._make_provider(
            auth_mode="bearer", secret_parameter_key="legal_knowledge_watch.test.token",
        )
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LKW_TEST_TOKEN", None)
            with self.assertRaises(AIProviderError):
                GenericWebhookProvider(provider).healthcheck()

    @patch(_HTTP_POST)
    def test_healthcheck_success(self, mock_post):
        mock_post.return_value = _FakeResponse(200, {"status": "ok"})
        provider = self._make_provider()
        result = GenericWebhookProvider(provider).healthcheck()
        self.assertEqual(result, {"status": "ok"})

    @patch(_HTTP_POST)
    def test_export_sends_idempotency_key_from_content_hash(self, mock_post):
        mock_post.return_value = _FakeResponse(200, {"remote_id": "abc"})
        provider = self._make_provider()
        result = GenericWebhookProvider(provider).export_document(
            {"content_hash": "sha256:deadbeef", "reference": "LKW-1"}
        )
        self.assertEqual(result["remote_id"], "abc")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "sha256:deadbeef")

    @patch(_HTTP_POST)
    def test_invalid_json_response_raises(self, mock_post):
        mock_post.return_value = _FakeResponse(200, None, text="not json")
        provider = self._make_provider()
        with self.assertRaises(AIProviderError):
            GenericWebhookProvider(provider).classify({"document": {}})

    @patch(_SLEEP)
    @patch(_HTTP_POST)
    def test_timeout_is_retried_then_succeeds(self, mock_post, _mock_sleep):
        mock_post.side_effect = [
            requests.exceptions.Timeout("slow"),
            _FakeResponse(200, {"status": "ok"}),
        ]
        provider = self._make_provider()
        result = GenericWebhookProvider(provider).healthcheck()
        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(mock_post.call_count, 2)

    @patch(_SLEEP)
    @patch(_HTTP_POST)
    def test_429_exhausts_retries_and_raises(self, mock_post, _mock_sleep):
        mock_post.return_value = _FakeResponse(429, text="rate limited")
        provider = self._make_provider()
        with self.assertRaises(AIProviderError):
            GenericWebhookProvider(provider).healthcheck()
        self.assertEqual(mock_post.call_count, 3)

    @patch(_HTTP_POST)
    def test_401_is_not_retried(self, mock_post):
        mock_post.return_value = _FakeResponse(401, text="unauthorized")
        provider = self._make_provider()
        with self.assertRaises(AIProviderError):
            GenericWebhookProvider(provider).healthcheck()
        self.assertEqual(mock_post.call_count, 1)


class TestAiBrainHttpProvider(LegalWatchTransactionCase):
    def _make_provider(self, **overrides):
        vals = {
            "name": "AI-Brain Test",
            "provider_type": "ai_brain_http",
            "base_url": "https://ai-brain.internal.example",
            "auth_mode": "bearer",
            "secret_parameter_key": "legal_knowledge_watch.test.ai_brain_token",
            "timeout_seconds": 10,
            "verify_tls": True,
        }
        vals.update(overrides)
        provider = self.env["legal.ai.provider"].create(vals)
        return provider

    def _with_token(self):
        return patch.dict(os.environ, {"LKW_TEST_AI_BRAIN_TOKEN": "s3cr3t"})

    @patch(_HTTP_GET)
    def test_healthcheck_calls_expected_url_and_headers(self, mock_get):
        mock_get.return_value = _FakeResponse(200, {"status": "ok", "api_version": "1.0"})
        provider = self._make_provider()
        with self._with_token():
            result = AiBrainHttpProvider(provider).healthcheck()

        self.assertEqual(result["status"], "ok")
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://ai-brain.internal.example/api/v1/legal-knowledge/health")
        self.assertEqual(kwargs["headers"]["X-Legal-Knowledge-Schema"], "1.0")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer s3cr3t")

    @patch(_HTTP_PUT)
    def test_export_uses_put_with_idempotency_key_and_reference_in_url(self, mock_put):
        mock_put.return_value = _FakeResponse(200, {"remote_id": "doc-42"})
        provider = self._make_provider()
        with self._with_token():
            result = AiBrainHttpProvider(provider).export_document({
                "reference": "LKW-2026-00001", "content_hash": "sha256:abc123",
            })

        self.assertEqual(result["remote_id"], "doc-42")
        args, kwargs = mock_put.call_args
        self.assertEqual(
            args[0],
            "https://ai-brain.internal.example/api/v1/legal-knowledge/documents/LKW-2026-00001",
        )
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "sha256:abc123")

    def test_export_without_reference_raises(self):
        provider = self._make_provider()
        with self._with_token():
            with self.assertRaises(AIProviderError):
                AiBrainHttpProvider(provider).export_document({"content_hash": "x"})

    @patch(_HTTP_DELETE)
    def test_delete_calls_expected_url(self, mock_delete):
        mock_delete.return_value = _FakeResponse(200, {})
        provider = self._make_provider()
        with self._with_token():
            AiBrainHttpProvider(provider).delete_document("LKW-2026-00001")
        args, _ = mock_delete.call_args
        self.assertEqual(
            args[0],
            "https://ai-brain.internal.example/api/v1/legal-knowledge/documents/LKW-2026-00001",
        )

    @patch(_HTTP_POST)
    def test_classify_uses_post(self, mock_post):
        mock_post.return_value = _FakeResponse(200, {"schema_version": "1.0"})
        provider = self._make_provider()
        with self._with_token():
            result = AiBrainHttpProvider(provider).classify({"document": {}})
        self.assertEqual(result["schema_version"], "1.0")
        args, _ = mock_post.call_args
        self.assertEqual(args[0], "https://ai-brain.internal.example/api/v1/legal-knowledge/classify")

    @patch(_SLEEP)
    @patch(_HTTP_GET)
    def test_failure_message_never_contains_the_token(self, mock_get, _mock_sleep):
        mock_get.return_value = _FakeResponse(500, text="internal error")
        provider = self._make_provider()
        with self._with_token():
            with self.assertRaises(AIProviderError) as ctx:
                AiBrainHttpProvider(provider).healthcheck()
        self.assertNotIn("s3cr3t", str(ctx.exception))

    def test_none_auth_mode_never_requires_secret(self):
        provider = self._make_provider(auth_mode="none", secret_parameter_key=False)
        with patch(_HTTP_GET, return_value=_FakeResponse(200, {"status": "ok"})):
            AiBrainHttpProvider(provider).healthcheck()  # must not raise

    @patch(_HTTP_GET)
    def test_base_url_pointing_at_loopback_ip_is_rejected(self, mock_get):
        # EN: No network call must happen: assert_public_host() rejects
        # the literal loopback IP before requests.get is ever called.
        # FR : Aucun appel réseau ne doit avoir lieu : assert_public_host()
        # rejette l'IP loopback littérale avant même que requests.get ne
        # soit appelé.
        provider = self._make_provider(base_url="http://127.0.0.1:9999")
        with self._with_token():
            with self.assertRaises(AIProviderError):
                AiBrainHttpProvider(provider).healthcheck()
        mock_get.assert_not_called()

    @patch(_HTTP_GET)
    def test_redirect_is_not_followed(self, mock_get):
        mock_get.return_value = _FakeResponse(
            302, headers={"Location": "http://127.0.0.1/internal"},
        )
        provider = self._make_provider()
        with self._with_token():
            with self.assertRaises(AIProviderError):
                AiBrainHttpProvider(provider).healthcheck()
        # EN: A redirect is a hard failure, never retried.
        # FR : Une redirection est un échec dur, jamais réessayée.
        self.assertEqual(mock_get.call_count, 1)
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["allow_redirects"], False)

    @patch(_HTTP_GET)
    def test_oversized_response_is_rejected(self, mock_get):
        mock_get.return_value = _FakeResponse(
            200, headers={"Content-Length": "50000000"},
        )
        provider = self._make_provider()
        with self._with_token():
            with self.assertRaises(AIProviderError):
                AiBrainHttpProvider(provider).healthcheck()
