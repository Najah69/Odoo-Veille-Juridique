from odoo import fields, models


class LegalTag(models.Model):
    # Business taxonomy independent from any DMS-specific tagging system.
    _name = "legal.tag"
    _description = "Legal Knowledge Tag"
    _order = "name"

    name = fields.Char(string="Name", required=True, translate=True)
    color = fields.Integer(string="Color")
    active = fields.Boolean(string="Active", default=True)

    _sql_constraints = [
        (
            "legal_tag_name_unique",
            "unique(name)",
            "A tag with this name already exists.",
        ),
    ]
