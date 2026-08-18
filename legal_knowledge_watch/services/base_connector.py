"""Connector contract. A connector never writes to Odoo: it only turns a
remote source into a list of normalized candidate items. All persistence
(dedup, versioning, storage) happens in legal.knowledge.document, called by
the orchestrator (legal.watch._run_ingestion).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


class ConnectorConfigError(Exception):
    """Raised by validate_configuration() for a fixable configuration
    problem (missing/invalid field). Never raised for transient network
    issues.
    """


class ConnectorFetchError(Exception):
    """Raised by fetch() for a fetch attempt that failed after retries, or
    that must not be retried (e.g. domain not allowed).
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
        """

    @abstractmethod
    def fetch(self, cursor, limit=100):
        """Return a FetchResult. Must raise ConnectorFetchError instead of
        letting a network/parsing exception propagate uncaught, so the
        orchestrator can record a clean failure reason.
        """
