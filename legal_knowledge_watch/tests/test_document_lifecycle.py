from odoo.exceptions import UserError

from .common import LegalWatchTransactionCase


class TestIngestCandidate(LegalWatchTransactionCase):
    def test_creates_document_and_first_version(self):
        result = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-100")
        )
        self.assertEqual(result["result"], "created")
        document = result["document"]
        self.assertTrue(document.reference.startswith("LKW-"))
        self.assertEqual(document.version_count, 1)
        self.assertTrue(document.current_version_id.is_current)
        self.assertEqual(document.content_hash, document.current_version_id.content_hash)

    def test_reimporting_identical_content_is_a_no_op(self):
        candidate = self._candidate(external_id="EXT-101")
        first = self.env["legal.knowledge.document"]._ingest_candidate(candidate)
        second = self.env["legal.knowledge.document"]._ingest_candidate(candidate)

        self.assertEqual(second["result"], "duplicate")
        self.assertEqual(first["document"], second["document"])
        self.assertEqual(first["document"].version_count, 1)

    def test_changed_content_creates_new_version_and_keeps_history(self):
        candidate = self._candidate(external_id="EXT-102")
        first = self.env["legal.knowledge.document"]._ingest_candidate(candidate)
        document = first["document"]
        old_version = document.current_version_id

        changed = dict(candidate, plain_text="Contenu totalement différent et modifié.")
        second = self.env["legal.knowledge.document"]._ingest_candidate(changed)

        self.assertEqual(second["result"], "new_version")
        self.assertEqual(second["document"], document)
        self.assertEqual(document.version_count, 2)
        self.assertFalse(old_version.is_current)
        self.assertTrue(document.current_version_id.is_current)
        self.assertNotEqual(old_version.id, document.current_version_id.id)
        self.assertEqual(document.content_hash, document.current_version_id.content_hash)

    def test_identical_content_from_different_source_is_flagged_duplicate_without_new_document(self):
        candidate = self._candidate(external_id="EXT-103")
        first = self.env["legal.knowledge.document"]._ingest_candidate(candidate)

        other_source = self.env["legal.source"].create({
            "name": "Other Source", "code": "other_source",
        })
        cross_source_candidate = self._candidate(
            source_id=other_source.id,
            external_id="EXT-DIFFERENT",
            title="Titre différent",
        )
        # same plain_text as `candidate` by default from _candidate()
        result = self.env["legal.knowledge.document"]._ingest_candidate(
            cross_source_candidate
        )

        self.assertEqual(result["result"], "duplicate")
        self.assertEqual(result["document"], first["document"])
        doc_count = self.env["legal.knowledge.document"].search_count(
            [("content_hash", "=", first["document"].content_hash)]
        )
        self.assertEqual(doc_count, 1)

    def test_external_id_unique_per_source_sql_constraint(self):
        candidate = self._candidate(external_id="EXT-104")
        self.env["legal.knowledge.document"]._ingest_candidate(candidate)
        # A direct create() bypassing the ingestion service must still be
        # blocked by the SQL constraint.
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env["legal.knowledge.document"].create({
                    "name": "Doublon direct",
                    "source_id": self.source.id,
                    "external_id": "EXT-104",
                })


class TestStatusTransitions(LegalWatchTransactionCase):
    def setUp(self):
        super().setUp()
        self.document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-200")
        )["document"]

    def test_new_to_review_to_approved_allowed(self):
        self.document.action_set_review()
        self.assertEqual(self.document.status, "review")
        self.document.action_approve()
        self.assertEqual(self.document.status, "approved")

    def test_approved_to_new_is_blocked(self):
        self.document.action_set_review()
        self.document.action_approve()
        with self.assertRaises(UserError):
            self.document._check_transition("new")

    def test_archived_is_terminal(self):
        self.document.action_set_review()
        self.document.action_approve()
        self.document.action_archive_document()
        self.assertEqual(self.document.status, "archived")
        with self.assertRaises(UserError):
            self.document._check_transition("approved")
