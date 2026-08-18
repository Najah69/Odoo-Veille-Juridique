from odoo import fields, models


class LegalWatch(models.Model):
    # Minimal skeleton for a future recurring watch. No connector runs in
    # Phase 0: only 'manual' is selectable. RSS/Légifrance connectors and
    # scheduling fields are added in a later phase (see docs/architecture.md).
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
        ],
        string="Connector", required=True, default="manual",
        help="Only 'manual' is available in this phase. Network connectors "
             "(RSS, Légifrance/PISTE, ...) are added in later phases.",
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

    def _compute_document_count(self):
        for watch in self:
            watch.document_count = len(watch.document_ids)
