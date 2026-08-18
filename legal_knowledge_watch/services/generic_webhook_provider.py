"""Minimal generic webhook provider: a single URL, one JSON body shape
with an "action" discriminator. Intended as the simplest possible example
of implementing BaseAIProvider — a contributor building a Qdrant/
OpenWebUI/filesystem provider can use this as a template.
"""
from . import secrets_service
from .ai_provider_base import AIProviderError, BaseAIProvider
from .ai_provider_registry import register_provider
from .http_retry import request_with_retries


@register_provider
class GenericWebhookProvider(BaseAIProvider):
    provider_type = "webhook"

    def _get_token(self):
        if not self.record.secret_parameter_key:
            raise AIProviderError(
                "No secret_parameter_key configured for this provider."
            )
        token = secrets_service.get_secret(self.env, self.record.secret_parameter_key)
        if not token:
            raise AIProviderError(
                "Configured secret is not set (environment variable or "
                "system parameter)."
            )
        return token

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.record.auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {self._get_token()}"
        elif self.record.auth_mode == "header":
            headers[self.record.auth_header_name or "Authorization"] = self._get_token()
        return headers

    def _post(self, payload, idempotency_key=None):
        if not self.record.base_url:
            raise AIProviderError("No base_url configured for this provider.")
        headers = self._headers()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        response = request_with_retries(
            "post", self.record.base_url, AIProviderError,
            headers=headers, json=payload,
            timeout=self.record.timeout_seconds or 20,
            verify=self.record.verify_tls,
        )
        try:
            return response.json()
        except ValueError as exc:
            raise AIProviderError("Provider response was not valid JSON.") from exc

    def healthcheck(self):
        return self._post({"action": "healthcheck"})

    def classify(self, document_payload):
        return self._post({"action": "classify", "document": document_payload})

    def export_document(self, document_payload):
        return self._post(
            {"action": "export", "document": document_payload},
            idempotency_key=document_payload.get("content_hash"),
        )

    def delete_document(self, reference):
        self._post({"action": "delete", "reference": reference})
