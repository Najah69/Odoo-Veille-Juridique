from odoo import fields, models


class LegalIngestionRun(models.Model):
    # Immutable execution log. In Phase 0 only 'manual' imports create runs;
    # 'cron'/'api'/'retry' triggers are wired in when connectors are added.
    _name = "legal.ingestion.run"
    _description = "Legal Knowledge Ingestion Run"
    _order = "started_at desc"

    watch_id = fields.Many2one(
        comodel_name="legal.watch", string="Watch", ondelete="set null",
    )
    source_id = fields.Many2one(
        comodel_name="legal.source", string="Source",
    )
    trigger = fields.Selection(
        selection=[
            ("manual", "Manual"),
            ("cron", "Scheduled"),
            ("api", "API"),
            ("retry", "Retry"),
        ],
        string="Trigger", required=True, default="manual",
    )
    state = fields.Selection(
        selection=[
            ("running", "Running"),
            ("success", "Success"),
            ("partial", "Partial"),
            ("failed", "Failed"),
            ("skipped", "Skipped"),
        ],
        string="State", required=True, default="running",
    )
    started_at = fields.Datetime(
        string="Started At", required=True, default=fields.Datetime.now,
    )
    finished_at = fields.Datetime(string="Finished At")
    fetched_count = fields.Integer(string="Fetched", default=0)
    created_count = fields.Integer(string="Documents Created", default=0)
    updated_count = fields.Integer(string="Versions Created", default=0)
    duplicate_count = fields.Integer(string="Duplicates Ignored", default=0)
    filtered_count = fields.Integer(
        string="Filtered by Rules", default=0,
        help="Candidates excluded by a relevance rule before ingestion "
             "(distinct from duplicates: these were never even compared "
             "against existing documents).",
    )
    error_count = fields.Integer(string="Errors", default=0)
    log_excerpt = fields.Text(
        string="Diagnostics",
        help="Non-sensitive diagnostic excerpt. Never store secrets or full "
             "document content here.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company", string="Company",
        default=lambda self: self.env.company,
    )
