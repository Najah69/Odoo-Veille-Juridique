"""legal.ai.job orchestration tests. The AI provider itself is replaced by
a fake (this file is about job state machine / policy enforcement / audit
trail correctness, not HTTP — see test_ai_providers.py for that).

FR : Tests d'orchestration de legal.ai.job. Le provider IA lui-même est
remplacé par un faux (ce fichier porte sur la machine à états du job, le
respect de la politique et la justesse de la trace d'audit, pas sur le
HTTP — voir test_ai_providers.py pour ça).
"""
from unittest.mock import patch

from ..services.ai_provider_base import AIProviderError, BaseAIProvider
from .common import LegalWatchTransactionCase

_REGISTRY_PATCH = "odoo.addons.legal_knowledge_watch.services.ai_provider_registry.get_provider"

_VALID_CLASSIFY_RESULT = {
    "schema_version": "1.0",
    "summary": "Résumé.",
    "themes": ["social"],
    "tags": [],
    "legal_nature": "decret",
    "effective_date": None,
    "affected_audiences": [],
    "obligations": [],
    "business_relevance": {"score_delta": 5, "rationale": "x"},
    "requires_human_review": True,
    "uncertainties": [],
    "citations": [],
}


class _FakeProvider(BaseAIProvider):
    provider_type = "fake"
    classify_result = _VALID_CLASSIFY_RESULT
    classify_exception = None
    export_result = None
    export_exception = None
    calls = []

    def healthcheck(self):
        return {"status": "ok"}

    def classify(self, document_payload):
        type(self).calls.append(("classify", document_payload))
        if self.classify_exception:
            raise self.classify_exception
        return self.classify_result

    def export_document(self, document_payload):
        type(self).calls.append(("export", document_payload))
        if self.export_exception:
            raise self.export_exception
        return self.export_result or {"remote_id": "remote-1"}

    def delete_document(self, reference):
        type(self).calls.append(("delete", reference))


class TestAiJobProcessing(LegalWatchTransactionCase):
    def setUp(self):
        super().setUp()
        _FakeProvider.classify_result = dict(_VALID_CLASSIFY_RESULT)
        _FakeProvider.classify_exception = None
        _FakeProvider.export_result = None
        _FakeProvider.export_exception = None
        _FakeProvider.calls = []
        self.provider = self.env["legal.ai.provider"].create({
            "name": "Fake Provider", "provider_type": "webhook",
            "base_url": "https://example.org", "auth_mode": "none",
            "enabled_for_classification": True, "enabled_for_export": True,
        })

    def _make_document(self, trust_level="primary", status="new", plain_text="Contenu de test."):
        self._doc_counter = getattr(self, "_doc_counter", 0) + 1
        unique = self._doc_counter
        source = self.env["legal.source"].create({
            "name": "Trusted Source", "code": f"trusted_{trust_level}_{status}_{unique}",
            "trust_level": trust_level,
        })
        result = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(
                source_id=source.id, external_id=f"EXT-{trust_level}-{status}-{unique}",
                plain_text=f"{plain_text} (unique {unique})",
                canonical_url=f"https://exemple.gouv.example.org/test-{unique}",
            )
        )
        document = result["document"]
        if status == "approved":
            document.action_set_review()
            document.action_approve()
        elif status == "review":
            document.action_set_review()
        return document

    def test_classify_success_creates_enrichment_and_flags_needs_review(self):
        document = self._make_document()
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "classify",
        })
        with patch(_REGISTRY_PATCH, return_value=_FakeProvider(self.provider)):
            job._process()

        self.assertEqual(job.state, "done")
        self.assertTrue(document.needs_review)
        enrichment = document.enrichment_ids
        self.assertEqual(len(enrichment), 1)
        self.assertEqual(enrichment.state, "success")
        self.assertEqual(enrichment.kind, "ai_classification")

    def test_classify_schema_failure_marks_job_failed_with_audit_trail(self):
        document = self._make_document()
        _FakeProvider.classify_result = {"not": "a valid enrichment payload"}
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "classify",
        })
        with patch(_REGISTRY_PATCH, return_value=_FakeProvider(self.provider)):
            job._process()

        self.assertEqual(job.state, "failed")
        self.assertTrue(job.last_error)
        enrichment = document.enrichment_ids
        self.assertEqual(len(enrichment), 1)
        self.assertEqual(enrichment.state, "failed")
        self.assertTrue(enrichment.error_message)
        # EN: Schema failure must not silently flip document metadata.
        # FR : Un échec de schéma ne doit jamais modifier silencieusement
        # les métadonnées du document.
        self.assertFalse(document.needs_review)

    def test_export_blocked_for_non_approved_document_never_calls_provider(self):
        document = self._make_document(status="new")  # not approved
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "export",
        })
        with patch(_REGISTRY_PATCH, return_value=_FakeProvider(self.provider)):
            job._process()

        self.assertEqual(job.state, "cancelled")
        self.assertEqual(document.export_state, "blocked")
        self.assertNotIn("export", [call[0] for call in _FakeProvider.calls])

    def test_export_blocked_for_low_trust_source(self):
        document = self._make_document(trust_level="low", status="approved")
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "export",
        })
        with patch(_REGISTRY_PATCH, return_value=_FakeProvider(self.provider)):
            job._process()

        self.assertEqual(job.state, "cancelled")
        self.assertEqual(document.export_state, "blocked")
        self.assertFalse(_FakeProvider.calls)

    def test_export_success_sets_exported_and_stores_remote_id(self):
        document = self._make_document(status="approved")
        _FakeProvider.export_result = {"remote_id": "ai-brain-doc-99"}
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "export",
        })
        with patch(_REGISTRY_PATCH, return_value=_FakeProvider(self.provider)):
            job._process()

        self.assertEqual(job.state, "done")
        self.assertEqual(job.remote_id, "ai-brain-doc-99")
        self.assertEqual(document.export_state, "exported")
        export_enrichment = document.enrichment_ids.filtered(
            lambda e: e.kind == "embedding_export"
        )
        self.assertEqual(len(export_enrichment), 1)

    def test_export_transient_failure_schedules_retry(self):
        document = self._make_document(status="approved")
        _FakeProvider.export_exception = AIProviderError("network blip")
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "export",
        })
        with patch(_REGISTRY_PATCH, return_value=_FakeProvider(self.provider)):
            job._process()

        self.assertEqual(job.state, "retry")
        self.assertTrue(job.next_attempt_at)
        self.assertEqual(document.export_state, "failed")

    def test_job_exhausts_max_attempts_then_fails_permanently(self):
        document = self._make_document(status="approved")
        _FakeProvider.export_exception = AIProviderError("still failing")
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "export", "attempt_count": 4,  # next failure is attempt 5 = MAX_ATTEMPTS
        })
        with patch(_REGISTRY_PATCH, return_value=_FakeProvider(self.provider)):
            job._process()

        self.assertEqual(job.state, "failed")
        self.assertFalse(job.next_attempt_at)

    def test_action_approve_queues_export_job_only_for_enabled_providers(self):
        self.provider.enabled_for_export = False
        document = self._make_document(status="review")
        document.action_approve()
        self.assertFalse(document.ai_job_ids.filtered(lambda j: j.job_type == "export"))

        self.provider.enabled_for_export = True
        document2 = self._make_document(status="review")
        document2.action_approve()
        export_jobs = document2.ai_job_ids.filtered(lambda j: j.job_type == "export")
        self.assertEqual(len(export_jobs), 1)
        self.assertEqual(document2.export_state, "queued")

    def test_action_request_ai_classification_creates_one_job_per_enabled_provider(self):
        other_provider = self.env["legal.ai.provider"].create({
            "name": "Other Provider", "provider_type": "webhook",
            "base_url": "https://other.example.org", "auth_mode": "none",
            "enabled_for_classification": True,
        })
        document = self._make_document()
        document.action_request_ai_classification()

        classify_jobs = document.ai_job_ids.filtered(lambda j: j.job_type == "classify")
        self.assertEqual(len(classify_jobs), 2)
        self.assertEqual(
            set(classify_jobs.mapped("provider_id.id")),
            {self.provider.id, other_provider.id},
        )

    def test_cron_processes_due_jobs(self):
        document = self._make_document()
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "classify",
        })
        with patch(_REGISTRY_PATCH, return_value=_FakeProvider(self.provider)):
            self.env["legal.ai.job"]._cron_process_pending_jobs()
        self.assertEqual(job.state, "done")

    def test_cron_skips_jobs_not_yet_due_for_retry(self):
        from odoo import fields as odoo_fields
        from datetime import timedelta

        document = self._make_document()
        job = self.env["legal.ai.job"].create({
            "document_id": document.id, "provider_id": self.provider.id,
            "job_type": "classify", "state": "retry",
            "next_attempt_at": odoo_fields.Datetime.now() + timedelta(hours=1),
        })
        with patch(_REGISTRY_PATCH, return_value=_FakeProvider(self.provider)):
            self.env["legal.ai.job"]._cron_process_pending_jobs()
        self.assertEqual(job.state, "retry")
