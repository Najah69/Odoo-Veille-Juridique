from odoo import fields, models


class LegalTag(models.Model):
    # EN: Business taxonomy independent from any DMS-specific tagging system.
    # FR: Taxonomie métier indépendante de tout système de tags propre à un DMS.
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
