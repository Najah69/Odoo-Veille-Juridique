from odoo import api, fields, models

# Ordered so "at least X" comparisons are simple integer comparisons.
TRUST_LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2, "primary": 3}


class LegalExportPolicy(models.Model):
    # Configurable refinement on top of the non-negotiable export floor
    # (approved, current, non-empty text, canonical_url and content_hash
    # present — enforced unconditionally in
    # legal.knowledge.document._check_export_policy(), never here). The
    # most specific matching policy (by company/source/watch) wins; with
    # no matching policy at all, the Phase 4 default (min trust_level
    # 'high') applies — see _resolve() below.
    _name = "legal.export.policy"
    _description = "Legal Knowledge Watch: Export Policy"
    _order = "sequence, id"

    name = fields.Char(string="Name", required=True)
    sequence = fields.Integer(string="Sequence", default=10)
    active = fields.Boolean(string="Active", default=True)
    company_id = fields.Many2one(
        comodel_name="res.company", string="Company",
        help="Leave empty to apply to every company.",
    )
    source_id = fields.Many2one(
        comodel_name="legal.source", string="Source",
        help="Leave empty to apply to every source.",
    )
    watch_id = fields.Many2one(
        comodel_name="legal.watch", string="Watch",
        help="Leave empty to apply to every watch (including manual imports).",
    )
    min_trust_level = fields.Selection(
        selection=[
            ("low", "Low"), ("medium", "Medium"),
            ("high", "High"), ("primary", "Primary"),
        ],
        string="Minimum Source Trust Level", required=True, default="high",
    )
    require_review_cleared = fields.Boolean(
        string="Require Review Cleared", default=True,
        help="If set, needs_review must be False for the document to export.",
    )
    min_relevance_score = fields.Float(string="Minimum Relevance Score", default=0.0)
    max_text_length = fields.Integer(
        string="Maximum Text Length", default=0,
        help="0 = unlimited. Blocks export of unusually large documents.",
    )

    @api.model
    def _resolve(self, document):
        """Return the most specific active policy matching this document's
        company/source/watch, or an empty recordset if none is configured
        (caller falls back to the Phase 4 default in that case).
        """
        domain = [
            "|", ("company_id", "=", False), ("company_id", "=", document.company_id.id),
        ]
        candidates = self.search(domain, order="sequence")
        best = self.browse()
        best_score = -1
        for policy in candidates:
            if policy.source_id and policy.source_id != document.source_id:
                continue
            if policy.watch_id and policy.watch_id != document.watch_id:
                continue
            score = (
                (2 if policy.source_id else 0)
                + (2 if policy.watch_id else 0)
                + (1 if policy.company_id else 0)
            )
            if score > best_score:
                best, best_score = policy, score
        return best
