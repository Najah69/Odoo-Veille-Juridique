"""AI/export provider contract. The job-processing pipeline
(legal.ai.job._process) only ever talks to this interface — it never
knows about ai_brain_http, webhook, or any future provider_type
specifically. See docs/ai-providers.md.
"""
from abc import ABC, abstractmethod


class AIProviderError(Exception):
    """Raised for any provider call failure. Never includes a token or the
    full document text in its message.
    """


class BaseAIProvider(ABC):
    provider_type = None

    def __init__(self, provider_record):
        self.record = provider_record
        self.env = provider_record.env

    @abstractmethod
    def healthcheck(self) -> dict:
        """Return a small status dict. Raise AIProviderError on failure."""

    @abstractmethod
    def classify(self, document_payload: dict) -> dict:
        """Return the raw parsed JSON response (validated by the caller
        against enrichment_schema, not here — a provider must not assume
        its own output is well-formed).
        """

    @abstractmethod
    def export_document(self, document_payload: dict) -> dict:
        """Upsert a document. Must be idempotent for the same
        document_payload["content_hash"]. Return a dict that may include
        a "remote_id" key.
        """

    @abstractmethod
    def delete_document(self, reference: str) -> None:
        """Remove/archive a previously exported document. Rare in
        practice — see docs/ai-providers.md.
        """
