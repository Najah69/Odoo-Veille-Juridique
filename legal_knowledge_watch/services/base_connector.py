"""Connector contract. A connector never writes to Odoo: it only turns a
remote source into a list of normalized candidate items. All persistence
(dedup, versioning, storage) happens in legal.knowledge.document, called by
the orchestrator (legal.watch._run_ingestion).

FR : Contrat des connecteurs. Un connecteur n'écrit jamais dans Odoo : il
se contente de transformer une source distante en liste d'éléments
candidats normalisés. Toute la persistance (dédup, versioning, stockage)
se fait dans legal.knowledge.document, appelé par l'orchestrateur
(legal.watch._run_ingestion).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


class ConnectorConfigError(Exception):
    """Raised by validate_configuration() for a fixable configuration
    problem (missing/invalid field). Never raised for transient network
    issues.

    FR : Levée par validate_configuration() pour un problème de
    configuration réparable (champ manquant/invalide). Jamais levée pour
    un incident réseau transitoire.
    """


class ConnectorFetchError(Exception):
    """Raised by fetch() for a fetch attempt that failed after retries, or
    that must not be retried (e.g. domain not allowed).

    FR : Levée par fetch() pour une tentative de récupération ayant
    échoué après les tentatives de réessai, ou qui ne doit pas être
    réessayée (ex : domaine non autorisé).
    """


@dataclass(frozen=True)
class CandidateItem:
    source_url: str
    canonical_url: str
    title: str
    external_id: Optional[str] = None
    raw_content: Optional[bytes] = None
    plain_text: Optional[str] = None
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    content_type: Optional[str] = None
    language: str = "fr_FR"
    source_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class FetchResult:
    items: list
    next_cursor: Optional[str]
    diagnostics: dict


class BaseConnector(ABC):
    code = None

    def __init__(self, watch, logger):
        self.watch = watch
        self.logger = logger

    @abstractmethod
    def validate_configuration(self):
        """Raise ConnectorConfigError on a fixable problem. Must not make
        any network call or Odoo write.

        FR : Lève ConnectorConfigError en cas de problème réparable. Ne
        doit faire aucun appel réseau ni aucune écriture Odoo.
        """

    @abstractmethod
    def fetch(self, cursor, limit=100):
        """Return a FetchResult. Must raise ConnectorFetchError instead of
        letting a network/parsing exception propagate uncaught, so the
        orchestrator can record a clean failure reason.

        FR : Retourne un FetchResult. Doit lever ConnectorFetchError
        plutôt que de laisser une exception réseau/parsing se propager
        sans être interceptée, afin que l'orchestrateur puisse
        enregistrer une raison d'échec claire.
        """
