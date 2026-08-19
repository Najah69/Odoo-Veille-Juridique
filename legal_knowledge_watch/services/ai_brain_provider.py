"""AI-Brain HTTP adapter. The contract below (endpoints, headers, payload
shape) is this project's own design (docs/ai-providers.md), not an
external API to reverse-engineer — any server implementing it works with
this provider. No URL is hardcoded: base_url is entirely admin-configured
on the legal.ai.provider record.

FR : Adaptateur HTTP AI-Brain. Le contrat ci-dessous (endpoints, en-têtes,
forme du payload) est une conception propre à ce projet
(docs/ai-providers.md), pas une API externe à rétro-ingénierer — tout
serveur qui l'implémente fonctionne avec ce provider. Aucune URL n'est
codée en dur : base_url est entièrement configuré par un administrateur
sur l'enregistrement legal.ai.provider.
"""
from . import secrets_service
from .ai_provider_base import AIProviderError, BaseAIProvider
from .ai_provider_registry import register_provider
from .http_retry import request_with_retries

SCHEMA_HEADER_VALUE = "1.0"


@register_provider
class AiBrainHttpProvider(BaseAIProvider):
    provider_type = "ai_brain_http"

    def _get_token(self):
        if self.record.auth_mode == "none":
            return None
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

    def _headers(self, extra=None):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Legal-Knowledge-Schema": SCHEMA_HEADER_VALUE,
        }
        if self.record.auth_mode == "bearer":
            headers["Authorization"] = f"Bearer {self._get_token()}"
        elif self.record.auth_mode == "header":
            headers[self.record.auth_header_name or "Authorization"] = self._get_token()
        if extra:
            headers.update(extra)
        return headers

    def _url(self, path):
        if not self.record.base_url:
            raise AIProviderError("No base_url configured for this provider.")
        return f"{self.record.base_url.rstrip('/')}{path}"

    def _request_kwargs(self):
        return {
            "timeout": self.record.timeout_seconds or 20,
            "verify": self.record.verify_tls,
        }

    def healthcheck(self):
        response = request_with_retries(
            "get", self._url("/api/v1/legal-knowledge/health"), AIProviderError,
            headers=self._headers(), **self._request_kwargs(),
        )
        try:
            return response.json()
        except ValueError as exc:
            raise AIProviderError("Health response was not valid JSON.") from exc

    def classify(self, document_payload):
        response = request_with_retries(
            "post", self._url("/api/v1/legal-knowledge/classify"), AIProviderError,
            headers=self._headers(), json=document_payload, **self._request_kwargs(),
        )
        try:
            return response.json()
        except ValueError as exc:
            raise AIProviderError("Classify response was not valid JSON.") from exc

    def export_document(self, document_payload):
        reference = document_payload.get("reference")
        if not reference:
            raise AIProviderError("document_payload is missing 'reference'.")
        content_hash = document_payload.get("content_hash")
        headers = self._headers(
            {"Idempotency-Key": content_hash} if content_hash else None
        )
        response = request_with_retries(
            "put", self._url(f"/api/v1/legal-knowledge/documents/{reference}"),
            AIProviderError, headers=headers, json=document_payload,
            **self._request_kwargs(),
        )
        try:
            return response.json()
        except ValueError:
            return {}

    def delete_document(self, reference):
        request_with_retries(
            "delete", self._url(f"/api/v1/legal-knowledge/documents/{reference}"),
            AIProviderError, headers=self._headers(), **self._request_kwargs(),
        )
