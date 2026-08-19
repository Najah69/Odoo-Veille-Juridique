"""AI/export provider contract. The job-processing pipeline
(legal.ai.job._process) only ever talks to this interface — it never
knows about ai_brain_http, webhook, or any future provider_type
specifically. See docs/ai-providers.md.

FR : Contrat des fournisseurs IA/export. Le pipeline de traitement des
jobs (legal.ai.job._process) ne parle jamais qu'à cette interface — il
ne connaît jamais ai_brain_http, webhook, ni aucun futur provider_type
en particulier. Voir docs/ai-providers.md.
"""
from abc import ABC, abstractmethod


class AIProviderError(Exception):
    """Raised for any provider call failure. Never includes a token or the
    full document text in its message.

    FR : Levée pour tout échec d'appel à un fournisseur. Ne doit jamais
    inclure un token ni le texte complet du document dans son message.
    """


class BaseAIProvider(ABC):
    provider_type = None

    def __init__(self, provider_record):
        self.record = provider_record
        self.env = provider_record.env

    @abstractmethod
    def healthcheck(self) -> dict:
        """Return a small status dict. Raise AIProviderError on failure.

        FR : Retourne un petit dict de statut. Lève AIProviderError en cas
        d'échec.
        """

    @abstractmethod
    def classify(self, document_payload: dict) -> dict:
        """Return the raw parsed JSON response (validated by the caller
        against enrichment_schema, not here — a provider must not assume
        its own output is well-formed).

        FR : Retourne la réponse JSON brute parsée (validée par
        l'appelant via enrichment_schema, pas ici — un fournisseur ne
        doit jamais supposer que sa propre sortie est bien formée).
        """

    @abstractmethod
    def export_document(self, document_payload: dict) -> dict:
        """Upsert a document. Must be idempotent for the same
        document_payload["content_hash"]. Return a dict that may include
        a "remote_id" key.

        FR : Crée ou met à jour un document (upsert). Doit être idempotent
        pour un même document_payload["content_hash"]. Retourne un dict
        pouvant contenir une clé "remote_id".
        """

    @abstractmethod
    def delete_document(self, reference: str) -> None:
        """Remove/archive a previously exported document. Rare in
        practice — see docs/ai-providers.md.

        FR : Supprime/archive un document précédemment exporté. Rare en
        pratique — voir docs/ai-providers.md.
        """
