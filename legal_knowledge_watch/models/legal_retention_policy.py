from odoo import fields, models


class LegalRetentionPolicy(models.Model):
    # EN: Retention is opt-in and conservative by construction: a document
    # is only ever archived (a reversible status change, never a
    # deletion), and only the *binary content of non-current (superseded)
    # versions* of an already-archived document is ever physically
    # removed — the current version's content, and every
    # version/document metadata row, is never touched by retention. See
    # legal.knowledge.document._cron_apply_retention() and
    # docs/operations.md.
    # FR: La rétention est optionnelle (opt-in) et conservatrice par
    # construction : un document est seulement archivé (un changement de
    # statut réversible, jamais une suppression), et seul le *contenu
    # binaire des versions non courantes (remplacées)* d'un document déjà
    # archivé est physiquement supprimé — le contenu de la version
    # courante, et toute ligne de métadonnées de version/document, n'est
    # jamais touché par la rétention. Voir
    # legal.knowledge.document._cron_apply_retention() et
    # docs/operations.md.
    _name = "legal.retention.policy"
    _description = "Legal Knowledge Watch: Retention Policy"
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
    archive_rejected_after_days = fields.Integer(
        string="Archive Rejected After (days)", default=0,
        help="0 = never auto-archive rejected documents under this policy. "
             "Counted from the document's last_checked_at.",
    )
    delete_binary_after_archived_days = fields.Integer(
        string="Purge Old-Version Binaries After Archived (days)", default=0,
        help="0 = never purge. Counted from archived_at. Only ever removes "
             "the stored content of non-current versions — the current "
             "version and all metadata rows are always kept.",
    )
