from odoo import fields, models


class LegalWatchRule(models.Model):
    # Deterministic, explainable relevance rule evaluated before any AI
    # involvement. See services/relevance_service.py for the evaluation
    # logic and docs/connectors.md for the field/operator/effect contract.
    _name = "legal.watch.rule"
    _description = "Legal Knowledge Watch Rule"
    _order = "watch_id, sequence, id"

    watch_id = fields.Many2one(
        comodel_name="legal.watch", string="Watch", required=True,
        ondelete="cascade",
    )
    name = fields.Char(string="Name", required=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)
    rule_type = fields.Selection(
        selection=[
            ("keyword", "Keyword"),
            ("regex", "Regex"),
            ("source_field", "Source Field"),
        ],
        string="Rule Type", required=True, default="keyword",
    )
    target_field = fields.Selection(
        selection=[
            ("title", "Title"),
            ("plain_text", "Text"),
            ("authority", "Authority"),
            ("source_url", "Source URL"),
            ("canonical_url", "Canonical URL"),
        ],
        string="Target Field", required=True, default="title",
    )
    operator = fields.Selection(
        selection=[
            ("contains", "Contains"),
            ("equals", "Equals"),
            ("matches", "Matches (regex)"),
            ("in", "In (comma-separated)"),
            ("not_in", "Not In (comma-separated)"),
        ],
        string="Operator", required=True, default="contains",
    )
    value = fields.Char(string="Value", required=True)
    effect = fields.Selection(
        selection=[
            ("include", "Include"),
            ("exclude", "Exclude"),
            ("score", "Score"),
            ("tag", "Tag"),
            ("requires_review", "Requires Review"),
        ],
        string="Effect", required=True, default="score",
    )
    score_delta = fields.Integer(string="Score Delta", default=0)
    tag_id = fields.Many2one(comodel_name="legal.tag", string="Tag to Apply")
