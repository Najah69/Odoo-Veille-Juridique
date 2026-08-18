import base64

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services import normalize_service

_TEXT_EXTENSIONS = (".txt", ".md", ".markdown")
_HTML_EXTENSIONS = (".html", ".htm")
_PDF_EXTENSIONS = (".pdf",)


class LegalManualImportWizard(models.TransientModel):
    # No network connector runs here: this wizard only ingests content the
    # user pastes or uploads. "source_url" is provenance metadata only and
    # is never fetched.
    _name = "legal.manual.import.wizard"
    _description = "Legal Knowledge Manual Import"

    import_mode = fields.Selection(
        selection=[("file", "Upload a file"), ("text", "Paste text")],
        string="Import Mode", required=True, default="file",
    )
    title = fields.Char(string="Title", required=True)
    source_id = fields.Many2one(
        comodel_name="legal.source", string="Source", required=True,
    )
    watch_id = fields.Many2one(
        comodel_name="legal.watch", string="Watch",
        domain=[("connector_code", "=", "manual")],
    )
    external_id = fields.Char(string="External ID")
    source_url = fields.Char(
        string="Source URL",
        help="Provenance only: this URL is never fetched by the wizard.",
    )
    published_at = fields.Datetime(string="Published At")
    document_type = fields.Selection(
        selection=[
            ("law", "Law"),
            ("decree", "Decree"),
            ("order", "Order"),
            ("case_law", "Case Law"),
            ("guidance", "Guidance"),
            ("news", "News"),
            ("manual", "Manual Entry"),
            ("other", "Other"),
        ],
        string="Document Type", required=True, default="manual",
    )
    language = fields.Char(string="Language", default="fr_FR")
    tag_ids = fields.Many2many(comodel_name="legal.tag", string="Tags")
    attachment_data = fields.Binary(string="File")
    attachment_filename = fields.Char(string="Filename")
    plain_text_input = fields.Text(string="Text")
    review_state_choice = fields.Selection(
        selection=[
            ("review", "Send to review"),
            ("new", "Leave as new"),
        ],
        string="Initial Status", required=True, default="review",
    )
    storage_mode = fields.Selection(
        selection=[
            ("auto", "Auto (DMS if installed, else Attachment)"),
            ("dms", "OCA DMS (fails clearly if not installed)"),
            ("attachment", "Attachment (always)"),
        ],
        string="Storage Mode", required=True, default="auto",
    )

    @api.onchange("import_mode")
    def _onchange_import_mode(self):
        if self.import_mode == "file":
            self.plain_text_input = False
        else:
            self.attachment_data = False
            self.attachment_filename = False

    def _extract_from_file(self):
        self.ensure_one()
        if not self.attachment_data:
            raise UserError(self.env._("Please upload a file."))
        raw_bytes = base64.b64decode(self.attachment_data)
        filename = (self.attachment_filename or "").lower()
        needs_review = False
        review_note = False

        if filename.endswith(_HTML_EXTENSIONS):
            plain_text = normalize_service.html_to_text(
                normalize_service.decode_bytes(raw_bytes)
            )
            mime_type = "text/html"
        elif filename.endswith(_PDF_EXTENSIONS):
            extracted = normalize_service.extract_pdf_text(raw_bytes)
            mime_type = "application/pdf"
            if extracted:
                plain_text = extracted
            else:
                plain_text = ""
                needs_review = True
                review_note = self.env._(
                    "Automatic text extraction from this PDF failed or is "
                    "unavailable. The original file was kept as an "
                    "attachment; please review and complete the text "
                    "manually if needed."
                )
        elif filename.endswith(_TEXT_EXTENSIONS) or not filename:
            plain_text = normalize_service.decode_bytes(raw_bytes)
            mime_type = "text/plain"
        else:
            raise UserError(
                self.env._(
                    "Unsupported file type for '%(filename)s'. Supported "
                    "extensions: .txt, .md, .html, .htm, .pdf.",
                    filename=self.attachment_filename,
                )
            )

        attachment_vals = {
            "name": self.attachment_filename or self.title,
            "datas": self.attachment_data,
            "mimetype": mime_type,
        }
        return plain_text, mime_type, attachment_vals, needs_review, review_note

    def _extract_from_text(self):
        self.ensure_one()
        if not (self.plain_text_input or "").strip():
            raise UserError(self.env._("Please paste some text to import."))
        plain_text = self.plain_text_input
        attachment_vals = {
            "name": f"{self.title}.txt",
            "datas": base64.b64encode(plain_text.encode("utf-8")),
            "mimetype": "text/plain",
        }
        return plain_text, "text/plain", attachment_vals, False, False

    def action_import(self):
        self.ensure_one()
        if self.import_mode == "file":
            plain_text, mime_type, attachment_vals, needs_review, review_note = (
                self._extract_from_file()
            )
        else:
            plain_text, mime_type, attachment_vals, needs_review, review_note = (
                self._extract_from_text()
            )

        candidate = {
            "source_id": self.source_id.id,
            "watch_id": self.watch_id.id or False,
            "external_id": self.external_id or False,
            "source_url": self.source_url or False,
            "canonical_url": self.source_url or False,
            "title": self.title,
            "published_at": self.published_at or False,
            "document_type": self.document_type,
            "language": self.language or "fr_FR",
            "tag_ids": self.tag_ids.ids,
            "plain_text": plain_text,
            "mime_type": mime_type,
            "attachment_vals": attachment_vals,
            "needs_review": needs_review,
            "default_status": self.review_state_choice,
            "storage_mode": self.storage_mode,
        }

        result = self.env["legal.knowledge.document"]._ingest_candidate(candidate)
        document = result["document"]

        if result["result"] == "duplicate":
            document.message_post(
                body=self.env._(
                    "Duplicate manual import ignored: identical content "
                    "was already collected for this document."
                )
            )
        elif needs_review and review_note:
            document.message_post(body=review_note)

        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Legal Knowledge Document"),
            "res_model": "legal.knowledge.document",
            "view_mode": "form",
            "res_id": document.id,
        }
