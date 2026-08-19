from datetime import timedelta

from odoo import fields

from .common import LegalWatchTransactionCase


class TestReconciliation(LegalWatchTransactionCase):
    def setUp(self):
        super().setUp()
        self.provider = self.env["legal.ai.provider"].create({
            "name": "Recon Provider", "provider_type": "webhook",
            "base_url": "https://example.org", "auth_mode": "none",
            "enabled_for_export": True,
        })

    def _approved_document(self, external_id, plain_text="Contenu de test."):
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(
                external_id=external_id, plain_text=plain_text,
                canonical_url=f"https://exemple.gouv.example.org/{external_id}",
            )
        )["document"]
        document.action_set_review()
        document.action_approve()
        return document

    def test_superseded_but_exported_gets_flagged_stale_and_delete_job_queued(self):
        document = self._approved_document("EXT-RECON-1")
        document.write({"export_state": "exported", "is_current": False})

        self.env["legal.knowledge.document"]._cron_reconcile_exports()

        self.assertEqual(document.export_state, "stale")
        delete_jobs = document.ai_job_ids.filtered(lambda j: j.job_type == "delete_export")
        self.assertEqual(len(delete_jobs), 1)

    def test_reconciliation_does_not_duplicate_pending_delete_jobs(self):
        document = self._approved_document("EXT-RECON-2")
        document.write({"export_state": "exported", "is_current": False})

        self.env["legal.knowledge.document"]._cron_reconcile_exports()
        self.env["legal.knowledge.document"]._cron_reconcile_exports()

        delete_jobs = document.ai_job_ids.filtered(lambda j: j.job_type == "delete_export")
        self.assertEqual(len(delete_jobs), 1)

    def test_approved_current_not_requested_gets_export_queued(self):
        document = self._approved_document("EXT-RECON-3")
        self.assertEqual(document.export_state, "queued")  # auto-queued on approve already
        document.export_state = "not_requested"
        document.ai_job_ids.unlink()

        self.env["legal.knowledge.document"]._cron_reconcile_exports()

        self.assertEqual(document.export_state, "queued")
        export_jobs = document.ai_job_ids.filtered(lambda j: j.job_type == "export")
        self.assertEqual(len(export_jobs), 1)

    def test_reconciliation_skips_documents_blocked_by_policy(self):
        low_source = self.env["legal.source"].create({
            "name": "Low Trust Recon", "code": "low_trust_recon", "trust_level": "low",
        })
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(
                source_id=low_source.id, external_id="EXT-RECON-4",
                canonical_url="https://exemple.gouv.example.org/EXT-RECON-4",
            )
        )["document"]
        document.action_set_review()
        document.action_approve()  # queues jobs; simulate they were cleared
        document.ai_job_ids.unlink()
        document.export_state = "not_requested"

        self.env["legal.knowledge.document"]._cron_reconcile_exports()

        self.assertFalse(document.ai_job_ids.filtered(lambda j: j.job_type == "export"))

    def test_stuck_running_ai_job_is_reset_to_retry(self):
        document = self._approved_document("EXT-RECON-5")
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "export", "state": "running",
        })
        old_write_date = fields.Datetime.now() - timedelta(hours=2)
        self.env.cr.execute(
            "UPDATE legal_ai_job SET write_date = %s WHERE id = %s",
            (old_write_date, job.id),
        )
        job.invalidate_recordset()

        self.env["legal.ai.job"]._reconcile_stuck_jobs()

        self.assertEqual(job.state, "retry")
        self.assertTrue(job.next_attempt_at)

    def test_recently_running_ai_job_is_left_alone(self):
        document = self._approved_document("EXT-RECON-6")
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "export", "state": "running",
        })
        self.env["legal.ai.job"]._reconcile_stuck_jobs()
        self.assertEqual(job.state, "running")

    def test_stuck_running_ingestion_run_is_marked_failed(self):
        watch = self.env["legal.watch"].create({
            "name": "Recon Watch", "source_id": self.source.id, "connector_code": "manual",
        })
        run = self.env["legal.ingestion.run"].create({
            "watch_id": watch.id, "source_id": self.source.id,
            "trigger": "cron", "state": "running",
        })
        old_start = fields.Datetime.now() - timedelta(hours=3)
        run.write({"started_at": old_start})

        self.env["legal.ingestion.run"]._reconcile_stuck_runs()

        self.assertEqual(run.state, "failed")
        self.assertTrue(run.finished_at)
