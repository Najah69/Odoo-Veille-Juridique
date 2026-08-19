from odoo import fields, models


class LegalSource(models.Model):
    # EN: A publisher or authority a legal.watch/document can be traced back to.
    # FR: Un éditeur ou une autorité à laquelle un legal.watch/document peut être rattaché.
    _name = "legal.source"
    _description = "Legal Knowledge Source"
    _order = "name"

    name = fields.Char(
        string="Name", required=True,
        help='Display name, e.g. "Légifrance".',
    )
    code = fields.Char(
        string="Code", required=True,
        help='Stable technical identifier, e.g. "legifrance".',
    )
    authority_type = fields.Selection(
        selection=[
            ("official", "Official (state/authority)"),
            ("institutional", "Institutional"),
            ("professional", "Professional body"),
            ("editorial", "Editorial"),
            ("manual", "Manual entry"),
        ],
        string="Authority Type", required=True, default="manual",
    )
    trust_level = fields.Selection(
        selection=[
            ("primary", "Primary"),
            ("high", "High"),
            ("medium", "Medium"),
            ("low", "Low"),
        ],
        string="Trust Level", required=True, default="medium",
        help="Used by qualification/export rules to decide what may be trusted.",
    )
    base_url = fields.Char(string="Base URL")
    terms_url = fields.Char(
        string="Terms/Licence URL",
        help="Link to the terms of use, licence or API policy of this source.",
    )
    active = fields.Boolean(string="Active", default=True)
    description = fields.Html(string="Description")

    _sql_constraints = [
        (
            "legal_source_code_unique",
            "unique(code)",
            "The source code must be unique.",
        ),
    ]
