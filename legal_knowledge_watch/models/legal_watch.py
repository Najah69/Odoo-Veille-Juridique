import base64
import json
import logging
from datetime import timedelta, timezone

from psycopg2 import errors as psycopg2_errors

from odoo import api, fields, models

from ..services import connector_registry, relevance_service
from ..services.base_connector import ConnectorConfigError, ConnectorFetchError

_logger = logging.getLogger(__name__)


def _to_odoo_datetime(value):
    if value is None:
        return False
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class LegalWatch(models.Model):
    _name = "legal.watch"
    _description = "Legal Knowledge Watch"
    _order = "name"

    name = fields.Char(string="Name", required=True)
    source_id = fields.Many2one(
        comodel_name="legal.source", string="Source", required=True,
    )
    connector_code = fields.Selection(
        selection=[
            ("manual", "Manual import"),
            ("rss", "RSS/Atom"),
        ],
        string="Connector", required=True, default="manual",
    )
    active = fields.Boolean(string="Active", default=True)
    owner_id = fields.Many2one(
        comodel_name="res.users", string="Responsible",
        default=lambda self: self.env.user,
    )
    notes = fields.Text(string="Notes")
    company_id = fields.Many2one(
        comodel_name="res.company", string="Company",
        default=lambda self: self.env.company,
    )
    document_ids = fields.One2many(
        comodel_name="legal.knowledge.document", inverse_name="watch_id",
        string="Documents",
    )
    document_count = fields.Integer(
        string="Document Count", compute="_compute_document_count",
    )

    # Scheduling
    schedule_enabled = fields.Boolean(
        string="Scheduling Enabled", default=False,
        help="Whether the fetch cron may run this watch. Has no effect on "
             "the 'manual' connector.",
    )
    interval_minutes = fields.Integer(string="Interval (minutes)", default=360)
    last_run_at = fields.Datetime(string="Last Run At", readonly=True)
    last_success_at = fields.Datetime(string="Last Success At", readonly=True)
    last_cursor = fields.Text(
        string="Cursor", readonly=True,
        help="Opaque connector-specific cursor (e.g. HTTP ETag/Last-Modified "
             "for RSS). Never edit manually.",
    )

    # Connector configuration (JSON, connector-specific — see
    # docs/connectors.md for the schema of each connector).
    configuration_json = fields.Text(string="Configuration (JSON)")

    storage_mode = fields.Selection(
        selection=[
            ("auto", "Auto (DMS if installed, else Attachment)"),
            ("dms", "OCA DMS (fails clearly if not installed)"),
            ("attachment", "Attachment (always)"),
        ],
        string="Storage Mode", required=True, default="auto",
    )

    rule_ids = fields.One2many(
        comodel_name="legal.watch.rule", inverse_name="watch_id",
        string="Relevance Rules",
    )

    def _compute_document_count(self):
        for watch in self:
            watch.document_count = len(watch.document_ids)

    # -- Concurrency -----------------------------------------------------
    def _try_lock_for_run(self):
        """Take a PostgreSQL row lock for the duration of the current
        transaction. Returns False without blocking if another session
        already holds it. Locks are released automatically by PostgreSQL
        when the holding transaction ends (commit, rollback or crash), so
        there is no stale-lock state to recover from.
        """
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute(
                    "SELECT id FROM legal_watch WHERE id = %s FOR UPDATE NOWAIT",
                    (self.id,),
                )
            return True
        except psycopg2_errors.LockNotAvailable:
            return False

    def _is_due(self):
        self.ensure_one()
        if not self.last_run_at:
            return True
        interval = max(self.interval_minutes, 1)
        return fields.Datetime.now() >= self.last_run_at + timedelta(minutes=interval)

    # -- Cron entry point --------------------------------------------------
    @api.model
    def _cron_fetch_due_watches(self):
        watches = self.search([
            ("active", "=", True),
            ("schedule_enabled", "=", True),
            ("connector_code", "!=", "manual"),
        ])
        for watch in watches:
            if watch._is_due():
                watch._run_ingestion(trigger="cron")

    # -- UI actions ----------------------------------------------------
    def action_test_connection(self):
        self.ensure_one()
        try:
            connector = connector_registry.get_connector(self.connector_code)(
                self, _logger
            )
            connector.validate_configuration()
        except (ValueError, ConnectorConfigError) as exc:
            return self._notify("danger", str(exc))
        return self._notify("success", self.env._("Configuration is valid."))

    def action_run_now(self):
        self.ensure_one()
        run = self._run_ingestion(trigger="manual")
        notif_type = {
            "success": "success", "partial": "warning", "skipped": "warning",
        }.get(run.state, "danger")
        message = self.env._(
            "Run %(state)s: %(created)s created, %(updated)s new versions, "
            "%(duplicate)s duplicates, %(filtered)s filtered, %(error)s errors.",
            state=run.state, created=run.created_count, updated=run.updated_count,
            duplicate=run.duplicate_count, filtered=run.filtered_count,
            error=run.error_count,
        )
        return self._notify(notif_type, message)

    def _notify(self, notif_type, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": notif_type, "message": message,
                "sticky": notif_type == "danger",
            },
        }

    # -- Ingestion orchestration -----------------------------------------
    def _run_failure_vals(self, message):
        return {
            "state": "failed",
            "finished_at": fields.Datetime.now(),
            "log_excerpt": (message or "")[:4000],
        }

    def _build_candidate_dict(self, item, relevance):
        attachment_bytes = item.raw_content or (item.plain_text or "").encode("utf-8")
        return {
            "source_id": self.source_id.id,
            "watch_id": self.id,
            "external_id": item.external_id or False,
            "source_url": item.source_url,
            "canonical_url": item.canonical_url,
            "title": item.title,
            "published_at": _to_odoo_datetime(item.published_at),
            "document_type": "news",
            "authority": (item.source_metadata or {}).get("author") or self.source_id.name,
            "jurisdiction": "fr",
            "language": item.language or "fr_FR",
            "tag_ids": relevance["tag_ids"],
            "source_metadata_json": json.dumps(item.source_metadata or {}, default=str),
            "plain_text": item.plain_text,
            "mime_type": item.content_type or "text/plain",
            "attachment_vals": {
                "name": (item.title or "item")[:120],
                "datas": base64.b64encode(attachment_bytes),
                "mimetype": item.content_type or "text/plain",
            },
            "needs_review": relevance["requires_review"],
            "default_status": "new",
            "relevance_score": relevance["score"],
            "storage_mode": self.storage_mode,
        }

    def _run_ingestion(self, trigger="manual"):
        self.ensure_one()
        run_model = self.env["legal.ingestion.run"]
        base_vals = {
            "watch_id": self.id, "source_id": self.source_id.id, "trigger": trigger,
        }

        if not self._try_lock_for_run():
            return run_model.create({
                **base_vals, "state": "skipped",
                "started_at": fields.Datetime.now(), "finished_at": fields.Datetime.now(),
                "log_excerpt": "Skipped: another run is already in progress for this watch.",
            })

        run = run_model.create({
            **base_vals, "state": "running", "started_at": fields.Datetime.now(),
        })
        self.last_run_at = fields.Datetime.now()

        try:
            connector_class = connector_registry.get_connector(self.connector_code)
        except ValueError as exc:
            run.write(self._run_failure_vals(str(exc)))
            return run

        connector = connector_class(self, _logger)
        try:
            connector.validate_configuration()
        except ConnectorConfigError as exc:
            run.write(self._run_failure_vals(str(exc)))
            return run

        try:
            result = connector.fetch(cursor=self.last_cursor or None, limit=100)
        except ConnectorFetchError as exc:
            run.write(self._run_failure_vals(str(exc)))
            return run

        counters = {
            "fetched_count": 0, "created_count": 0, "updated_count": 0,
            "duplicate_count": 0, "filtered_count": 0, "error_count": 0,
        }
        log_lines = []

        for item in result.items:
            counters["fetched_count"] += 1
            try:
                with self.env.cr.savepoint():
                    relevance = relevance_service.evaluate_rules(
                        self.rule_ids.filtered("active"),
                        {
                            "title": item.title, "plain_text": item.plain_text,
                            "authority": (item.source_metadata or {}).get("author") or "",
                            "source_url": item.source_url,
                            "canonical_url": item.canonical_url,
                        },
                    )
                    if relevance["excluded"]:
                        counters["filtered_count"] += 1
                        continue
                    candidate = self._build_candidate_dict(item, relevance)
                    ingest_result = self.env["legal.knowledge.document"]._ingest_candidate(
                        candidate
                    )
                    if relevance["triggered"]:
                        ingest_result["document"].message_post(
                            body=self.env._(
                                "Relevance rules triggered: %(rules)s",
                                rules=", ".join(relevance["triggered"]),
                            )
                        )
                if ingest_result["result"] == "created":
                    counters["created_count"] += 1
                elif ingest_result["result"] == "new_version":
                    counters["updated_count"] += 1
                else:
                    counters["duplicate_count"] += 1
            except Exception as exc:  # noqa: BLE001 - one bad item must not break the run
                counters["error_count"] += 1
                log_lines.append(f"Item error ({item.title!r}): {exc}")

        for item_error in result.diagnostics.get("item_errors", []):
            counters["error_count"] += 1
            log_lines.append(
                f"Connector item error ({item_error['title']!r}): {item_error['error']}"
            )

        self.last_cursor = result.next_cursor
        success_count = (
            counters["created_count"] + counters["updated_count"]
            + counters["duplicate_count"] + counters["filtered_count"]
        )
        if counters["error_count"] and counters["fetched_count"] and not success_count:
            state = "failed"
        elif counters["error_count"]:
            state = "partial"
        else:
            state = "success"
        if state in ("success", "partial"):
            self.last_success_at = fields.Datetime.now()

        run.write({
            **counters,
            "state": state,
            "finished_at": fields.Datetime.now(),
            "log_excerpt": "\n".join(log_lines)[:4000] or False,
        })
        return run
