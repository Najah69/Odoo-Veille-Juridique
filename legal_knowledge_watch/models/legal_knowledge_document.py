from odoo import api, fields, models

from ..services import deduplication_service, normalize_service

# Allowed status transitions (see docs/architecture.md - document lifecycle).
_ALLOWED_TRANSITIONS = {
    "new": {"qualified", "review", "rejected"},
    "qualified": {"approved", "review", "rejected"},
    "review": {"approved", "rejected"},
    "approved": {"archived", "superseded"},
    "rejected": {"review", "archived"},
    "superseded": {"archived"},
    "archived": set(),
}


class LegalKnowledgeDocument(models.Model):
    # Business source of truth for one collected piece of legal content.
    # Never confuse this with its storage backend (ir.attachment today,
    # optionally OCA DMS in a later phase): those only hold the bytes.
    _name = "legal.knowledge.document"
    _description = "Legal Knowledge Document"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "collected_at desc"

    name = fields.Char(string="Title", required=True, tracking=True)
    reference = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: self.env["ir.sequence"].next_by_code(
            "legal.knowledge.document"
        ) or "/",
    )
    source_id = fields.Many2one(
        comodel_name="legal.source", string="Source", required=True,
        tracking=True,
    )
    watch_id = fields.Many2one(
        comodel_name="legal.watch", string="Watch", ondelete="set null",
    )
    external_id = fields.Char(string="External ID", index=True)
    source_url = fields.Char(string="Source URL")
    canonical_url = fields.Char(string="Canonical URL", index=True)
    published_at = fields.Datetime(string="Published At")
    collected_at = fields.Datetime(
        string="Collected At", required=True, default=fields.Datetime.now,
    )
    last_checked_at = fields.Datetime(string="Last Checked At")
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
    authority = fields.Char(string="Issuing Authority")
    jurisdiction = fields.Selection(
        selection=[("fr", "France"), ("eu", "European Union"), ("other", "Other")],
        string="Jurisdiction", default="fr",
    )
    language = fields.Char(string="Language", default="fr_FR")
    status = fields.Selection(
        selection=[
            ("new", "New"),
            ("qualified", "Qualified"),
            ("review", "In Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("archived", "Archived"),
            ("superseded", "Superseded"),
        ],
        string="Status", required=True, default="new", tracking=True,
    )
    relevance_score = fields.Float(string="Relevance Score", default=0.0)
    needs_review = fields.Boolean(string="Needs Human Review", default=False)
    is_current = fields.Boolean(string="Is Current", default=True)
    content_hash = fields.Char(
        string="Content Hash", index=True,
        help="SHA-256 of the current version's normalized text.",
    )
    source_metadata_json = fields.Text(string="Source Metadata (JSON)")
    tag_ids = fields.Many2many(
        comodel_name="legal.tag", string="Tags",
    )
    version_ids = fields.One2many(
        comodel_name="legal.document.version", inverse_name="document_id",
        string="Versions",
    )
    version_count = fields.Integer(
        string="Version Count", compute="_compute_version_count",
    )
    current_version_id = fields.Many2one(
        comodel_name="legal.document.version", string="Current Version",
        compute="_compute_current_version_id", store=True,
    )
    attachment_id = fields.Many2one(
        comodel_name="ir.attachment", string="Current Attachment",
        compute="_compute_current_version_id", store=True,
    )
    current_version_text = fields.Text(
        string="Normalized Text",
        related="current_version_id.plain_text", readonly=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company", string="Company",
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(string="Active", default=True)

    _sql_constraints = [
        (
            "legal_document_external_source_unique",
            "unique(source_id, external_id)",
            "An external identifier may only be used once per source.",
        ),
    ]

    @api.depends("version_ids")
    def _compute_version_count(self):
        for document in self:
            document.version_count = len(document.version_ids)

    @api.depends("version_ids.is_current", "version_ids.attachment_id")
    def _compute_current_version_id(self):
        for document in self:
            current = document.version_ids.filtered("is_current")[:1]
            document.current_version_id = current
            document.attachment_id = current.attachment_id

    def _check_transition(self, target_status):
        self.ensure_one()
        allowed = _ALLOWED_TRANSITIONS.get(self.status, set())
        if target_status not in allowed:
            from odoo.exceptions import UserError

            raise UserError(
                self.env._(
                    "Cannot move document from status '%(current)s' to "
                    "'%(target)s'.",
                    current=self.status, target=target_status,
                )
            )

    def action_set_review(self):
        for document in self:
            document._check_transition("review")
            document.status = "review"

    def action_approve(self):
        for document in self:
            document._check_transition("approved")
            document.status = "approved"

    def action_reject(self):
        for document in self:
            document._check_transition("rejected")
            document.status = "rejected"

    def action_archive_document(self):
        for document in self:
            document._check_transition("archived")
            document.status = "archived"

    def action_view_versions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Versions"),
            "res_model": "legal.document.version",
            "view_mode": "list,form",
            "domain": [("document_id", "=", self.id)],
        }

    @api.model
    def _ingest_candidate(self, candidate):
        """Create or update a document from a normalized candidate dict.

        Expected keys: source_id (required), watch_id, external_id,
        source_url, canonical_url, title, published_at, document_type,
        authority, jurisdiction, language, tag_ids (list of ids),
        source_metadata_json, plain_text, mime_type, attachment_vals
        (dict passed to ir.attachment.create, optional), needs_review,
        default_status (status to apply to a brand-new document).

        Returns a dict: {"document": recordset, "version": recordset or
        empty, "result": "created" | "new_version" | "duplicate"}.
        """
        plain_text = normalize_service.normalize_whitespace(
            candidate.get("plain_text") or ""
        )
        content_hash = normalize_service.compute_content_hash(plain_text)
        canonical_url = normalize_service.normalize_canonical_url(
            candidate.get("canonical_url") or candidate.get("source_url") or ""
        ) or False

        existing, match_type = deduplication_service.find_existing_document(
            self.env,
            source_id=candidate["source_id"],
            external_id=candidate.get("external_id") or None,
            canonical_url=canonical_url or None,
            content_hash=content_hash,
        )

        if match_type == "content_hash":
            # Identical normalized content already stored, under a document
            # that this candidate's (source, external_id/canonical_url)
            # does not identify: treat as a duplicate, do not create a
            # second document or version.
            return {
                "document": existing,
                "version": self.env["legal.document.version"].browse(),
                "result": "duplicate",
            }

        if existing and match_type in ("external_id", "canonical_url"):
            if existing.content_hash == content_hash:
                return {
                    "document": existing,
                    "version": existing.current_version_id,
                    "result": "duplicate",
                }
            version = self._create_new_version(existing, candidate, plain_text, content_hash)
            return {"document": existing, "version": version, "result": "new_version"}

        document = self.create({
            "name": candidate["title"],
            "source_id": candidate["source_id"],
            "watch_id": candidate.get("watch_id"),
            "external_id": candidate.get("external_id") or False,
            "source_url": candidate.get("source_url") or False,
            "canonical_url": canonical_url,
            "published_at": candidate.get("published_at") or False,
            "collected_at": fields.Datetime.now(),
            "last_checked_at": fields.Datetime.now(),
            "document_type": candidate.get("document_type") or "manual",
            "authority": candidate.get("authority") or False,
            "jurisdiction": candidate.get("jurisdiction") or "fr",
            "language": candidate.get("language") or "fr_FR",
            "status": candidate.get("default_status") or "new",
            "needs_review": bool(candidate.get("needs_review")),
            "relevance_score": candidate.get("relevance_score") or 0.0,
            "content_hash": content_hash,
            "source_metadata_json": candidate.get("source_metadata_json") or False,
            "tag_ids": [(6, 0, candidate.get("tag_ids") or [])],
        })
        version = self.env["legal.document.version"].create({
            "document_id": document.id,
            "sequence": 1,
            "content_hash": content_hash,
            "plain_text": plain_text,
            "mime_type": candidate.get("mime_type") or False,
            "collected_at": fields.Datetime.now(),
            "is_current": True,
            "attachment_id": self._create_attachment(
                document, candidate.get("attachment_vals")
            ),
        })
        return {"document": document, "version": version, "result": "created"}

    def _create_new_version(self, document, candidate, plain_text, content_hash):
        document.current_version_id.write({"is_current": False})
        next_sequence = (max(document.version_ids.mapped("sequence")) + 1) if document.version_ids else 1
        version = self.env["legal.document.version"].create({
            "document_id": document.id,
            "sequence": next_sequence,
            "content_hash": content_hash,
            "plain_text": plain_text,
            "mime_type": candidate.get("mime_type") or False,
            "collected_at": fields.Datetime.now(),
            "source_updated_at": candidate.get("published_at") or False,
            "change_summary": candidate.get("change_summary") or False,
            "is_current": True,
            "attachment_id": self._create_attachment(
                document, candidate.get("attachment_vals")
            ),
        })
        document.write({
            "content_hash": content_hash,
            "last_checked_at": fields.Datetime.now(),
            "relevance_score": candidate.get("relevance_score", document.relevance_score),
        })
        document.message_post(
            body=self.env._(
                "New version collected (previous version kept in history)."
            )
        )
        return version

    def _create_attachment(self, document, attachment_vals):
        if not attachment_vals:
            return False
        attachment = self.env["ir.attachment"].create({
            **attachment_vals,
            "res_model": self._name,
            "res_id": document.id,
        })
        return attachment.id
