from odoo import fields, models


class LegalDocumentVersion(models.Model):
    # Immutable content snapshot. A document accumulates versions over time;
    # the source content of a past version is never edited or deleted.
    _name = "legal.document.version"
    _description = "Legal Knowledge Document Version"
    _order = "document_id, sequence"

    document_id = fields.Many2one(
        comodel_name="legal.knowledge.document", string="Document",
        required=True, ondelete="cascade", index=True,
    )
    sequence = fields.Integer(string="Version", required=True, default=1)
    content_hash = fields.Char(
        string="Content Hash", required=True, index=True,
        help="SHA-256 of the normalized plain text for this version.",
    )
    plain_text = fields.Text(string="Normalized Text")
    mime_type = fields.Char(string="Original MIME Type")
    attachment_id = fields.Many2one(
        comodel_name="ir.attachment", string="Original Content",
        help="Original file/content as collected, stored as an attachment. "
             "Set only when storage_backend = 'attachment'.",
    )
    storage_backend = fields.Selection(
        selection=[("attachment", "Attachment"), ("dms", "OCA DMS")],
        string="Storage Backend", required=True, default="attachment",
    )
    dms_file_res_id = fields.Integer(
        string="DMS File ID",
        help="Numeric id of the dms.file record holding this version's "
             "content. Deliberately a plain integer, not a Many2one: this "
             "module must stay installable without OCA DMS, and a Many2one "
             "would require the dms.file model to exist. Set only when "
             "storage_backend = 'dms'.",
    )
    collected_at = fields.Datetime(
        string="Collected At", required=True, default=fields.Datetime.now,
    )
    source_updated_at = fields.Datetime(string="Source Updated At")
    change_summary = fields.Text(string="Change Summary")
    is_current = fields.Boolean(string="Is Current", default=True, index=True)

    _sql_constraints = [
        (
            "legal_document_version_sequence_unique",
            "unique(document_id, sequence)",
            "Version sequence must be unique per document.",
        ),
    ]
