import hashlib
import json
import logging
from datetime import timedelta

from psycopg2 import errors as psycopg2_errors

from odoo import api, fields, models

from ..services import ai_provider_registry, enrichment_schema
from ..services.ai_provider_base import AIProviderError

_logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
BACKOFF_BASE_MINUTES = 2


class ExportBlockedError(AIProviderError):
    """The local export policy refused this document — never a provider
    failure. No retry: the job is cancelled and export_state is set to
    'blocked', both outside the per-attempt savepoint so the reason
    survives (see _process()).
    """


class SchemaValidationError(AIProviderError):
    """The provider's classify response failed legal-enrichment-1.0
    validation. Terminal (no retry — a malformed response won't fix itself)
    and, like ExportBlockedError, must be handled outside the per-attempt
    savepoint so the audit-trail enrichment record actually persists.
    """

    def __init__(self, message, errors, raw_result):
        super().__init__(message)
        self.errors = errors
        self.raw_result = raw_result


class LegalAiJob(models.Model):
    # Asynchronous unit of work against an AI/export provider. Never called
    # synchronously from the ingestion pipeline — see
    # legal.knowledge.document.action_request_ai_classification() /
    # action_approve() for where jobs get created, and
    # _cron_process_pending_jobs() for where they get processed, in small
    # batches, each in its own savepoint.
    _name = "legal.ai.job"
    _description = "Legal Knowledge Watch: AI Job"
    _order = "id"

    document_id = fields.Many2one(
        comodel_name="legal.knowledge.document", string="Document",
        required=True, ondelete="cascade", index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company", string="Company",
        related="document_id.company_id", readonly=True,
        help="Follows the document's company — used by the multi-company "
             "record rule so a job (and its provider/error details) is "
             "never visible outside the document's own company. "
             "Deliberately NOT store=True: this model's own reconciliation "
             "(_reconcile_stuck_jobs) detects a stuck job by write_date, "
             "and a stored related field can get lazily flushed by the "
             "ORM ahead of an unrelated search — which silently bumps "
             "write_date and defeats that check. A non-stored related "
             "field is still fully usable in ir.rule/search domains "
             "(Odoo joins through it), it just isn't its own DB column.",
    )
    provider_id = fields.Many2one(
        comodel_name="legal.ai.provider", string="Provider",
        required=True, ondelete="restrict",
    )
    job_type = fields.Selection(
        selection=[
            ("classify", "Classify"),
            ("export", "Export"),
            ("delete_export", "Delete Export"),
        ],
        string="Job Type", required=True,
    )
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("running", "Running"),
            ("done", "Done"),
            ("retry", "Retry"),
            ("failed", "Failed"),
            ("cancelled", "Cancelled"),
        ],
        string="State", required=True, default="pending",
    )
    attempt_count = fields.Integer(string="Attempts", default=0)
    next_attempt_at = fields.Datetime(string="Next Attempt At")
    payload_hash = fields.Char(
        string="Payload Hash",
        help="SHA-256 of the request payload, for idempotence checks.",
    )
    remote_id = fields.Char(string="Remote ID")
    last_error = fields.Text(string="Last Error")

    def _try_lock_for_run(self):
        # Same PostgreSQL row-lock pattern as legal.watch — see
        # models/legal_watch.py for why (self-releasing, no stale-lock
        # recovery code needed).
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "SELECT id FROM legal_ai_job WHERE id = %s FOR UPDATE NOWAIT",
                    (self.id,),
                )
            return True
        except psycopg2_errors.LockNotAvailable:
            return False

    @api.model
    def _cron_process_pending_jobs(self, batch_size=20):
        jobs = self.search([
            ("state", "in", ("pending", "retry")),
            "|", ("next_attempt_at", "=", False),
            ("next_attempt_at", "<=", fields.Datetime.now()),
        ], limit=batch_size)
        for job in jobs:
            job._process()

    def action_retry_now(self):
        for job in self:
            if job.state in ("failed", "retry"):
                job.write({"state": "pending", "next_attempt_at": False})
        for job in self:
            if job.state == "pending":
                job._process()

    @api.model
    def _reconcile_stuck_jobs(self, stuck_after_minutes=60):
        """A job left in 'running' this long almost certainly means the
        worker crashed mid-attempt (the row lock itself is released
        automatically by PostgreSQL in that case — see
        _try_lock_for_run() — but the job's own 'running' state is not).
        Reset to 'retry' with an immediate next_attempt_at rather than
        left stuck forever.
        """
        threshold = fields.Datetime.now() - timedelta(minutes=stuck_after_minutes)
        stuck = self.search([
            ("state", "=", "running"), ("write_date", "<=", threshold),
        ])
        for job in stuck:
            job.write({
                "state": "retry",
                "next_attempt_at": fields.Datetime.now(),
                "last_error": (
                    (job.last_error or "")
                    + "\nReconciliation: job was stuck in 'running' "
                      "(likely a crash) and was reset."
                ),
            })

    def _process(self):
        self.ensure_one()
        if not self._try_lock_for_run():
            return
        self.write({"state": "running", "attempt_count": self.attempt_count + 1})
        try:
            with self.env.cr.savepoint():
                provider = ai_provider_registry.get_provider(self.provider_id)
                if self.job_type == "classify":
                    self._run_classify(provider)
                elif self.job_type == "export":
                    self._run_export(provider)
                elif self.job_type == "delete_export":
                    self._run_delete_export(provider)
            self.write({"state": "done", "last_error": False})
        except ExportBlockedError as exc:
            # Outside the savepoint (it already rolled back): the
            # cancellation and the reason both need to persist.
            self.write({"state": "cancelled", "last_error": str(exc)[:4000]})
            self.document_id.export_state = "blocked"
        except SchemaValidationError as exc:
            # Outside the savepoint for the same reason: the audit-trail
            # enrichment record must survive even though the job fails.
            input_hash = hashlib.sha256(
                (self.document_id.current_version_text or "").encode("utf-8")
            ).hexdigest()
            self.env["legal.document.enrichment"].create({
                "document_id": self.document_id.id,
                "kind": "ai_classification",
                "provider_id": self.provider_id.id,
                "prompt_version": "legal_summary_classification_fr_v1",
                "input_hash": input_hash,
                "output_json": json.dumps(exc.raw_result, ensure_ascii=False, default=str),
                "state": "failed",
                "error_message": "; ".join(exc.errors)[:4000],
            })
            self.write({"state": "failed", "last_error": str(exc)[:4000]})
        except AIProviderError as exc:
            self._handle_failure(str(exc))
            if self.job_type == "export":
                self.document_id.export_state = "failed"
        except Exception as exc:  # noqa: BLE001 - never let a job crash the cron
            _logger.exception("Unexpected error processing legal.ai.job %s", self.id)
            self._handle_failure(f"Unexpected error: {exc}")
            if self.job_type == "export":
                self.document_id.export_state = "failed"

    def _handle_failure(self, message):
        self.ensure_one()
        if self.attempt_count >= MAX_ATTEMPTS:
            self.write({"state": "failed", "last_error": message[:4000]})
            return
        backoff_minutes = BACKOFF_BASE_MINUTES * (2 ** (self.attempt_count - 1))
        self.write({
            "state": "retry",
            "last_error": message[:4000],
            "next_attempt_at": fields.Datetime.now() + timedelta(minutes=backoff_minutes),
        })

    def _run_classify(self, provider):
        self.ensure_one()
        document = self.document_id
        payload = document._build_ai_classify_payload()

        result = provider.classify(payload)
        errors = enrichment_schema.validate(result)
        if errors:
            raise SchemaValidationError(
                f"Classify response failed legal-enrichment-1.0 validation: "
                f"{'; '.join(errors)[:500]}",
                errors, result,
            )

        input_hash = hashlib.sha256(
            (document.current_version_text or "").encode("utf-8")
        ).hexdigest()
        self.env["legal.document.enrichment"].create({
            "document_id": document.id,
            "kind": "ai_classification",
            "provider_id": self.provider_id.id,
            "prompt_version": "legal_summary_classification_fr_v1",
            "input_hash": input_hash,
            "output_json": json.dumps(result, ensure_ascii=False, default=str),
            "state": "success",
            "confidence": (result.get("business_relevance") or {}).get("score_delta"),
        })

        if result.get("requires_human_review"):
            document.needs_review = True

    def _run_export(self, provider):
        self.ensure_one()
        document = self.document_id
        allowed, reason = document._check_export_policy()
        if not allowed:
            raise ExportBlockedError(f"Export blocked by policy: {reason}")

        payload = document._build_ai_export_payload()
        result = provider.export_document(payload)

        self.remote_id = (result or {}).get("remote_id") or self.remote_id
        document.export_state = "exported"
        self.env["legal.document.enrichment"].create({
            "document_id": document.id,
            "kind": "embedding_export",
            "provider_id": self.provider_id.id,
            "input_hash": hashlib.sha256(
                (payload.get("content_hash") or "").encode("utf-8")
            ).hexdigest(),
            "output_json": json.dumps(result or {}, ensure_ascii=False, default=str),
            "state": "success",
        })

    def _run_delete_export(self, provider):
        self.ensure_one()
        document = self.document_id
        provider.delete_document(document.reference)
        document.export_state = "not_requested"
