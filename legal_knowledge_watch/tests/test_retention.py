from datetime import timedelta

from odoo import fields

from .common import LegalWatchTransactionCase


class TestRetentionArchive(LegalWatchTransactionCase):
    def _rejected_document(self, external_id, days_old=0):
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(
                external_id=external_id,
                canonical_url=f"https://exemple.gouv.example.org/{external_id}",
            )
        )["document"]
        document.action_reject()
        if days_old:
            document.write({
                "last_checked_at": fields.Datetime.now() - timedelta(days=days_old),
            })
        return document

    def test_dry_run_changes_nothing(self):
        self.env["legal.retention.policy"].create({
            "name": "Archive after 30d", "archive_rejected_after_days": 30,
        })
        document = self._rejected_document("EXT-RET-1", days_old=40)

        report = self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=True)

        self.assertIn(document.reference, report["archived"])
        self.assertEqual(document.status, "rejected")  # unchanged

    def test_real_run_archives_eligible_document(self):
        self.env["legal.retention.policy"].create({
            "name": "Archive after 30d", "archive_rejected_after_days": 30,
        })
        document = self._rejected_document("EXT-RET-2", days_old=40)

        report = self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=False)

        self.assertIn(document.reference, report["archived"])
        self.assertEqual(document.status, "archived")
        self.assertTrue(document.archived_at)

    def test_too_recent_document_is_not_archived(self):
        self.env["legal.retention.policy"].create({
            "name": "Archive after 30d", "archive_rejected_after_days": 30,
        })
        document = self._rejected_document("EXT-RET-3", days_old=5)

        report = self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=False)

        self.assertNotIn(document.reference, report["archived"])
        self.assertEqual(document.status, "rejected")

    def test_zero_days_policy_never_archives(self):
        self.env["legal.retention.policy"].create({
            "name": "No auto-archive", "archive_rejected_after_days": 0,
        })
        document = self._rejected_document("EXT-RET-4", days_old=9999)

        report = self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=False)

        self.assertNotIn(document.reference, report["archived"])
        self.assertEqual(document.status, "rejected")

    def test_running_twice_is_idempotent(self):
        self.env["legal.retention.policy"].create({
            "name": "Archive after 30d", "archive_rejected_after_days": 30,
        })
        document = self._rejected_document("EXT-RET-5", days_old=40)

        self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=False)
        report_2 = self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=False)

        # EN: Already archived -> no longer matches the 'rejected' domain.
        # FR : Déjà archivé -> ne correspond plus au domaine 'rejected'.
        self.assertNotIn(document.reference, report_2["archived"])
        self.assertEqual(document.status, "archived")


class TestRetentionPurge(LegalWatchTransactionCase):
    def _archived_document_with_two_versions(self, external_id, archived_days_old=0):
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(
                external_id=external_id,
                canonical_url=f"https://exemple.gouv.example.org/{external_id}",
                plain_text="Version un du texte.",
            )
        )["document"]
        first_version = document.current_version_id
        self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(
                external_id=external_id,
                canonical_url=f"https://exemple.gouv.example.org/{external_id}",
                plain_text="Version deux, contenu changé.",
            )
        )
        document.action_set_review()
        document.action_approve()
        document.action_archive_document()
        if archived_days_old:
            document.write({
                "archived_at": fields.Datetime.now() - timedelta(days=archived_days_old),
            })
        return document, first_version

    def test_dry_run_purge_changes_nothing(self):
        self.env["legal.retention.policy"].create({
            "name": "Purge after 30d", "delete_binary_after_archived_days": 30,
        })
        document, old_version = self._archived_document_with_two_versions(
            "EXT-PURGE-1", archived_days_old=40
        )
        old_attachment = old_version.attachment_id
        self.assertTrue(old_attachment)

        report = self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=True)

        self.assertTrue(any("v1" in label for label in report["purged_versions"]))
        self.assertTrue(old_version.attachment_id)
        self.assertTrue(old_attachment.exists())

    def test_real_purge_removes_only_non_current_version_binary(self):
        self.env["legal.retention.policy"].create({
            "name": "Purge after 30d", "delete_binary_after_archived_days": 30,
        })
        document, old_version = self._archived_document_with_two_versions(
            "EXT-PURGE-2", archived_days_old=40
        )
        old_attachment_id = old_version.attachment_id.id
        current_attachment = document.current_version_id.attachment_id
        self.assertTrue(current_attachment)

        self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=False)

        self.assertFalse(old_version.attachment_id)
        self.assertFalse(self.env["ir.attachment"].browse(old_attachment_id).exists())
        # EN: The current version's content and the document/version rows
        # themselves are never touched by retention.
        # FR : Le contenu de la version courante et les enregistrements
        # document/version eux-mêmes ne sont jamais touchés par la
        # rétention.
        self.assertTrue(document.current_version_id.attachment_id)
        self.assertTrue(document.current_version_id.attachment_id.exists())
        self.assertEqual(document.version_count, 2)
        self.assertTrue(old_version.exists())
        self.assertEqual(old_version.plain_text, "Version un du texte.")

    def test_too_recently_archived_is_not_purged(self):
        self.env["legal.retention.policy"].create({
            "name": "Purge after 30d", "delete_binary_after_archived_days": 30,
        })
        document, old_version = self._archived_document_with_two_versions(
            "EXT-PURGE-3", archived_days_old=5
        )
        self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=False)
        self.assertTrue(old_version.attachment_id)

    def test_purge_is_idempotent(self):
        self.env["legal.retention.policy"].create({
            "name": "Purge after 30d", "delete_binary_after_archived_days": 30,
        })
        document, old_version = self._archived_document_with_two_versions(
            "EXT-PURGE-4", archived_days_old=40
        )
        self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=False)
        # EN: Second run must not error even though the binary is already
        # gone.
        # FR : Le second passage ne doit pas échouer même si le binaire a
        # déjà disparu.
        report_2 = self.env["legal.knowledge.document"]._cron_apply_retention(dry_run=False)
        self.assertFalse(report_2["purged_versions"])
