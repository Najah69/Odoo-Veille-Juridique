from ..services import deduplication_service
from .common import LegalWatchTransactionCase


class TestDeduplicationService(LegalWatchTransactionCase):
    def setUp(self):
        super().setUp()
        self.document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(
                external_id="EXT-001",
                canonical_url="https://example.com/decret-1",
            )
        )["document"]

    def test_matches_by_external_id(self):
        found, match_type = deduplication_service.find_existing_document(
            self.env, source_id=self.source.id, external_id="EXT-001",
        )
        self.assertEqual(found, self.document)
        self.assertEqual(match_type, "external_id")

    def test_matches_by_canonical_url_same_source(self):
        found, match_type = deduplication_service.find_existing_document(
            self.env, source_id=self.source.id,
            canonical_url="https://example.com/decret-1",
        )
        self.assertEqual(found, self.document)
        self.assertEqual(match_type, "canonical_url")

    def test_matches_by_content_hash_across_sources(self):
        found, match_type = deduplication_service.find_existing_document(
            self.env, source_id=self.source.id,
            content_hash=self.document.content_hash,
        )
        self.assertEqual(found, self.document)
        self.assertEqual(match_type, "content_hash")

    def test_no_match_returns_empty_recordset_and_none(self):
        found, match_type = deduplication_service.find_existing_document(
            self.env, source_id=self.source.id, external_id="UNKNOWN",
            canonical_url="https://example.com/unknown",
            content_hash="0" * 64,
        )
        self.assertFalse(found)
        self.assertIsNone(match_type)

    def test_external_id_takes_precedence_over_url(self):
        # EN: Same source, different external_id but same canonical_url would
        # normally match by URL; external_id must be checked first.
        # FR : Même source, external_id différent mais même canonical_url —
        # correspondrait normalement par URL ; external_id doit primer.
        found, match_type = deduplication_service.find_existing_document(
            self.env, source_id=self.source.id, external_id="EXT-001",
            canonical_url="https://example.com/decret-1",
            content_hash="0" * 64,
        )
        self.assertEqual(match_type, "external_id")
