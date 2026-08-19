from odoo import fields, models


class LegalDmsDirectoryRoute(models.Model):
    # EN: Maps a legal.tag (or no tag = default) to a target OCA DMS
    # directory, per company. Deliberately independent from DMS's own
    # tagging system: this module never assumes anything about how DMS
    # internally organizes tags/categories, it only needs a directory id
    # to file new content into. See services/storage_dms.py for how this
    # is resolved.
    # FR: Fait correspondre un legal.tag (ou aucun tag = route par défaut)
    # à un répertoire OCA DMS cible, par société. Volontairement
    # indépendant du système de tags propre à DMS : ce module ne suppose
    # jamais rien sur la façon dont DMS organise en interne ses
    # tags/catégories, il a seulement besoin d'un identifiant de répertoire
    # où classer le nouveau contenu. Voir services/storage_dms.py pour la
    # résolution de cette route.
    _name = "legal.dms.directory.route"
    _description = "Legal Knowledge Watch: DMS Directory Routing"
    _order = "sequence, id"

    sequence = fields.Integer(string="Sequence", default=10)
    tag_id = fields.Many2one(
        comodel_name="legal.tag", string="Tag",
        help="Leave empty for the default/catch-all route of a company.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company", string="Company",
        help="Leave empty to apply to every company.",
    )
    dms_directory_id = fields.Integer(
        string="DMS Directory ID", required=True,
        help="Numeric id of the target dms.directory record. In OCA DMS, "
             "open the target directory and read its id from the URL, or "
             "from Settings > Technical > Database Structure > Records.",
    )
    active = fields.Boolean(string="Active", default=True)
