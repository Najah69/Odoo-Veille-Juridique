import json
import logging
import uuid
from datetime import timedelta

from odoo import api, fields, models

from ..services import deduplication_service, normalize_service, storage_service
from .legal_export_policy import TRUST_LEVEL_ORDER

_logger = logging.getLogger(__name__)

# EN: Allowed status transitions (see docs/architecture.md - document lifecycle).
# FR: Transitions de statut autorisées (voir docs/architecture.md — cycle
# de vie du document).
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
    # EN: Business source of truth for one collected piece of legal
    # content. Never confuse this with its storage backend (ir.attachment
    # today, optionally OCA DMS in a later phase): those only hold the
    # bytes.
    # FR: Source de vérité métier pour un contenu juridique collecté.
    # Jamais à confondre avec son backend de stockage (ir.attachment
    # aujourd'hui, optionnellement OCA DMS dans une phase ultérieure) :
    # ceux-ci ne font que porter les octets.
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
        related="current_version_id.attachment_id", store=True, readonly=True,
    )
    storage_backend = fields.Selection(
        related="current_version_id.storage_backend", store=True, readonly=True,
        string="Storage Backend",
    )
    dms_file_res_id = fields.Integer(
        related="current_version_id.dms_file_res_id", store=True, readonly=True,
        string="DMS File ID",
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

    export_state = fields.Selection(
        selection=[
            ("not_requested", "Not Requested"),
            ("queued", "Queued"),
            ("exported", "Exported"),
            ("stale", "Stale (content changed since last export)"),
            ("failed", "Failed"),
            ("blocked", "Blocked"),
        ],
        string="Export State", required=True, default="not_requested",
    )
    archived_at = fields.Datetime(
        string="Archived At", readonly=True,
        help="Set when the document is archived. Used by retention policies "
             "to time the grace period before old-version binaries are "
             "purged — see legal.retention.policy.",
    )
    enrichment_ids = fields.One2many(
        comodel_name="legal.document.enrichment", inverse_name="document_id",
        string="Enrichments",
    )
    ai_job_ids = fields.One2many(
        comodel_name="legal.ai.job", inverse_name="document_id",
        string="AI Jobs",
    )

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

    @api.depends("version_ids.is_current")
    def _compute_current_version_id(self):
        for document in self:
            document.current_version_id = document.version_ids.filtered("is_current")[:1]

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
            document._queue_export_jobs()

    def action_reject(self):
        for document in self:
            document._check_transition("rejected")
            document.status = "rejected"

    def action_archive_document(self):
        for document in self:
            document._check_transition("archived")
            document.write({"status": "archived", "archived_at": fields.Datetime.now()})

    def action_view_versions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Versions"),
            "res_model": "legal.document.version",
            "view_mode": "list,form",
            "domain": [("document_id", "=", self.id)],
        }

    def action_open_in_dms(self):
        self.ensure_one()
        from ..services.storage_dms import DmsStorageBackend

        backend = DmsStorageBackend(self.env)
        action = backend.open_action(self.current_version_id) if backend.is_available() else None
        if not action:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "warning",
                    "message": self.env._(
                        "The current version of this document is not stored in DMS."
                    ),
                },
            }
        return action

    def action_request_ai_classification(self):
        """Manual trigger: queue a classify job for every provider enabled
        for classification. Classification is opt-in/manual in this phase
        (unlike export, which auto-queues on approval) — see
        docs/ai-providers.md.

        FR : Déclenchement manuel : met en file un job de classification
        pour chaque provider activé pour la classification. La
        classification est optionnelle/manuelle à ce stade (contrairement
        à l'export, mis en file automatiquement à l'approbation) — voir
        docs/ai-providers.md.
        """
        providers = self.env["legal.ai.provider"].search([
            ("active", "=", True), ("enabled_for_classification", "=", True),
        ])
        job_model = self.env["legal.ai.job"]
        for document in self:
            for provider in providers:
                job_model.create({
                    "document_id": document.id,
                    "provider_id": provider.id,
                    "job_type": "classify",
                })

    def _queue_export_jobs(self):
        """Called on approval. Always creates the job (so the export
        policy — trust_level/is_current/non-empty text — is re-checked
        fresh when the job actually runs, not frozen at approval time);
        export_state is set to 'queued' immediately so the UI reflects
        that *something* is pending even before the cron picks it up.

        FR : Appelée à l'approbation. Crée toujours le job (afin que la
        politique d'export — trust_level/is_current/texte non vide — soit
        revérifiée à chaque exécution réelle du job, jamais figée au
        moment de l'approbation) ; export_state passe immédiatement à
        'queued' pour que l'UI reflète qu'*une action* est en attente,
        même avant que le cron ne la traite.
        """
        providers = self.env["legal.ai.provider"].search([
            ("active", "=", True), ("enabled_for_export", "=", True),
        ])
        if not providers:
            return
        job_model = self.env["legal.ai.job"]
        for document in self:
            for provider in providers:
                job_model.create({
                    "document_id": document.id,
                    "provider_id": provider.id,
                    "job_type": "export",
                })
            document.export_state = "queued"

    def _check_export_policy(self):
        """Fail-closed export policy. The floor below is unconditional and
        cannot be loosened by any legal.export.policy record: approved,
        current, canonical_url and content_hash present, non-empty text.
        On top of that floor, the most specific matching
        legal.export.policy (company/source/watch) — or the Phase 4
        default (min trust_level 'high') if none is configured — adds
        trust_level/review/score/length gates. Returns (allowed: bool,
        reason: str|None).

        FR : Politique d'export fail-closed. Le plancher ci-dessous est
        inconditionnel et ne peut être assoupli par aucun enregistrement
        legal.export.policy : approuvé, courant, canonical_url et
        content_hash présents, texte non vide. Au-dessus de ce plancher,
        le legal.export.policy correspondant le plus spécifique
        (société/source/veille) — ou le défaut de la Phase 4 (trust_level
        minimum 'high') si aucun n'est configuré — ajoute des contraintes
        de confiance/revue/score/longueur. Renvoie (allowed: bool,
        reason: str|None).
        """
        self.ensure_one()
        if self.status != "approved":
            return False, "document status is not 'approved'"
        if not self.is_current:
            return False, "document is not the current one (superseded)"
        if not self.canonical_url:
            return False, "document has no canonical_url"
        if not self.content_hash:
            return False, "document has no content_hash"
        text = (self.current_version_text or "").strip()
        if not text:
            return False, "document has no normalized text"

        policy = self.env["legal.export.policy"]._resolve(self)
        min_trust_level, require_review_cleared, min_score, max_length = (
            (policy.min_trust_level, policy.require_review_cleared,
             policy.min_relevance_score, policy.max_text_length)
            if policy else ("high", False, 0.0, 0)
        )
        if TRUST_LEVEL_ORDER.get(self.source_id.trust_level, -1) < TRUST_LEVEL_ORDER.get(min_trust_level, 99):
            return False, (
                f"source trust_level '{self.source_id.trust_level}' is below "
                f"the required minimum '{min_trust_level}'"
            )
        if require_review_cleared and self.needs_review:
            return False, "document still needs human review"
        if self.relevance_score < min_score:
            return False, (
                f"relevance_score {self.relevance_score} is below the "
                f"required minimum {min_score}"
            )
        if max_length and len(text) > max_length:
            return False, (
                f"normalized text length {len(text)} exceeds the maximum "
                f"{max_length}"
            )
        return True, None

    def _build_ai_classify_payload(self):
        self.ensure_one()
        return {
            "request_id": str(uuid.uuid4()),
            "document": {
                "local_id": self.id,
                "reference": self.reference,
                "title": self.name,
                "canonical_url": self.canonical_url,
                "source": {
                    "code": self.source_id.code,
                    "name": self.source_id.name,
                    "trust_level": self.source_id.trust_level,
                },
                "published_at": self.published_at.isoformat() if self.published_at else None,
                "effective_at": None,
                "document_type": self.document_type,
                "content_hash": f"sha256:{self.content_hash}" if self.content_hash else None,
                "plain_text": self.current_version_text or "",
                "metadata": {
                    "authority": self.authority,
                    "jurisdiction": self.jurisdiction,
                },
            },
            "policy": {
                "locale": "fr_FR",
                "require_json_schema": "legal-enrichment-1.0",
                "allow_legal_advice": False,
            },
        }

    def _build_ai_export_payload(self):
        self.ensure_one()
        try:
            source_metadata = json.loads(self.source_metadata_json or "{}")
        except (TypeError, ValueError):
            source_metadata = {}
        return {
            "schema_version": "1.0",
            "reference": self.reference,
            "content_hash": f"sha256:{self.content_hash}" if self.content_hash else None,
            "status": self.status,
            "title": self.name,
            "text": self.current_version_text or "",
            "metadata": {
                "source_url": self.source_url,
                "canonical_url": self.canonical_url,
                "source_name": self.source_id.name,
                "trust_level": self.source_id.trust_level,
                "published_at": self.published_at.isoformat() if self.published_at else None,
                "effective_at": None,
                "document_type": self.document_type,
                "themes": [],
                "tags": self.tag_ids.mapped("name"),
                "jurisdiction": self.jurisdiction,
                "language": self.language,
                "odoo_document_id": self.id,
            },
            "provenance": {
                "collected_at": self.collected_at.isoformat() if self.collected_at else None,
                "version": self.current_version_id.sequence if self.current_version_id else None,
                "source_metadata": source_metadata,
            },
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

        FR : Crée ou met à jour un document à partir d'un dict candidat
        normalisé.

        Clés attendues : source_id (requis), watch_id, external_id,
        source_url, canonical_url, title, published_at, document_type,
        authority, jurisdiction, language, tag_ids (liste d'ids),
        source_metadata_json, plain_text, mime_type, attachment_vals
        (dict passé à ir.attachment.create, optionnel), needs_review,
        default_status (statut à appliquer à un document tout neuf).

        Renvoie un dict : {"document": recordset, "version": recordset ou
        vide, "result": "created" | "new_version" | "duplicate"}.
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
            # EN: Identical normalized content already stored, under a
            # document that this candidate's (source, external_id/
            # canonical_url) does not identify: treat as a duplicate, do
            # not create a second document or version.
            # FR: Contenu normalisé identique déjà stocké, sous un document
            # que le (source, external_id/canonical_url) de ce candidat
            # n'identifie pas : traité comme un doublon, aucun second
            # document ni version n'est créé.
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

        # EN: Wrapped in a savepoint so a storage failure (e.g. storage_mode
        # 'dms' requested without DMS installed) cannot leave an orphan
        # document with zero versions: either both succeed, or neither does.
        # FR: Enveloppé dans un savepoint pour qu'un échec de stockage (ex :
        # storage_mode 'dms' demandé sans DMS installé) ne puisse jamais
        # laisser un document orphelin sans aucune version : soit les deux
        # réussissent, soit aucun des deux.
        with self.env.cr.savepoint():
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
            storage_vals = self._store_content(
                document, candidate.get("attachment_vals"),
                candidate.get("storage_mode", "auto"),
            )
            # EN: sudo(): legal.document.version create/write is restricted
            # to Reviewer+ (see ir.model.access.csv, Phase 7 security audit)
            # so a plain User can't forge a version directly via the
            # ORM/RPC — this centralized method is the only sanctioned
            # creation path, reached from the manual-import wizard and
            # every connector.
            # FR: sudo() : la création/écriture de legal.document.version
            # est restreinte à Reviewer+ (voir ir.model.access.csv, audit
            # sécurité Phase 7) afin qu'un simple User ne puisse pas forger
            # une version directement via l'ORM/RPC — cette méthode
            # centralisée est le seul chemin de création sanctionné,
            # atteint depuis l'assistant d'import manuel et chaque
            # connecteur.
            version = self.env["legal.document.version"].sudo().create({
                "document_id": document.id,
                "sequence": 1,
                "content_hash": content_hash,
                "plain_text": plain_text,
                "mime_type": candidate.get("mime_type") or False,
                "collected_at": fields.Datetime.now(),
                "is_current": True,
                **storage_vals,
            })
        return {"document": document, "version": version, "result": "created"}

    def _create_new_version(self, document, candidate, plain_text, content_hash):
        with self.env.cr.savepoint():
            # EN: sudo(): see the matching note in create_or_update_from_candidate().
            # FR: sudo() : voir la note équivalente dans create_or_update_from_candidate().
            document.current_version_id.sudo().write({"is_current": False})
            next_sequence = (
                max(document.version_ids.mapped("sequence")) + 1
                if document.version_ids else 1
            )
            storage_vals = self._store_content(
                document, candidate.get("attachment_vals"),
                candidate.get("storage_mode", "auto"),
            )
            version = self.env["legal.document.version"].sudo().create({
                "document_id": document.id,
                "sequence": next_sequence,
                "content_hash": content_hash,
                "plain_text": plain_text,
                "mime_type": candidate.get("mime_type") or False,
                "collected_at": fields.Datetime.now(),
                "source_updated_at": candidate.get("published_at") or False,
                "change_summary": candidate.get("change_summary") or False,
                "is_current": True,
                **storage_vals,
            })
            # EN: sudo(): User/Reviewer only have perm_write=0 on
            # legal.knowledge.document (see ir.model.access.csv) — these
            # writes only ever touch fields this method itself computed
            # (content_hash/relevance_score) or a derived state flag, never
            # user-supplied values, so sudo() here doesn't reopen a gap.
            # FR: sudo() : User/Reviewer n'ont que perm_write=0 sur
            # legal.knowledge.document (voir ir.model.access.csv) — ces
            # écritures ne touchent jamais que des champs calculés par
            # cette méthode elle-même (content_hash/relevance_score) ou un
            # indicateur d'état dérivé, jamais des valeurs fournies par
            # l'utilisateur, donc ce sudo() ne rouvre aucune faille.
            document.sudo().write({
                "content_hash": content_hash,
                "last_checked_at": fields.Datetime.now(),
                "relevance_score": candidate.get("relevance_score", document.relevance_score),
            })
            if document.export_state == "exported":
                # EN: The previously exported copy no longer matches the
                # current content — flag it rather than silently leaving
                # a stale export_state='exported'. Reconciliation
                # (_cron_reconcile_exports) re-queues a fresh export.
                # FR: La copie précédemment exportée ne correspond plus au
                # contenu actuel — on la signale plutôt que de laisser
                # silencieusement un export_state='exported' périmé. La
                # réconciliation (_cron_reconcile_exports) remet un export
                # frais en file.
                document.sudo().export_state = "stale"
        document.message_post(
            body=self.env._(
                "New version collected (previous version kept in history)."
            )
        )
        return version

    def _store_content(self, document, attachment_vals, storage_mode):
        """Delegate to the configured storage backend (ir.attachment or
        OCA DMS if installed and requested — see services/storage_service.py).
        Returns legal.document.version field values (storage_backend +
        backend-specific id field), defaulting the unused id field to False
        so callers can always unpack the dict the same way.

        FR : Délègue au backend de stockage configuré (ir.attachment ou
        OCA DMS si installé et demandé — voir
        services/storage_service.py). Renvoie les valeurs de champ
        legal.document.version (storage_backend + champ id propre au
        backend), avec le champ id inutilisé mis à False par défaut afin
        que les appelants puissent toujours décomposer le dict de la même
        façon.
        """
        if not attachment_vals:
            return {
                "storage_backend": "attachment",
                "attachment_id": False,
                "dms_file_res_id": False,
            }
        backend = storage_service.get_backend(self.env, storage_mode)
        result = backend.store(document, attachment_vals)
        result.setdefault("attachment_id", False)
        result.setdefault("dms_file_res_id", False)
        return result

    # -- Reconciliation ----------------------------------------------
    @api.model
    def _cron_reconcile_exports(self, batch_size=50):
        """Odoo/DMS is the durable registry; any RAG/export index is a
        derived, reconstructible projection. This detects drift between
        the two and repairs it — never by deleting local history, only by
        (re)queuing jobs or flagging state. See docs/operations.md.

        FR : Odoo/DMS est le registre durable ; tout index RAG/export en
        est une projection dérivée, reconstructible. Ceci détecte l'écart
        entre les deux et le répare — jamais en supprimant l'historique
        local, uniquement en (re)mettant des jobs en file ou en signalant
        un état. Voir docs/operations.md.
        """
        self._reconcile_superseded_but_exported()
        self._reconcile_missing_exports(batch_size)
        self.env["legal.ai.job"]._reconcile_stuck_jobs()
        self.env["legal.ingestion.run"]._reconcile_stuck_runs()

    def _reconcile_superseded_but_exported(self):
        stale_exported = self.search([
            ("export_state", "in", ("exported", "queued")),
            ("is_current", "=", False),
        ])
        providers = self.env["legal.ai.provider"].search([
            ("active", "=", True), ("enabled_for_export", "=", True),
        ])
        job_model = self.env["legal.ai.job"]
        for document in stale_exported:
            document.export_state = "stale"
            for provider in providers:
                pending = job_model.search_count([
                    ("document_id", "=", document.id), ("provider_id", "=", provider.id),
                    ("job_type", "=", "delete_export"),
                    ("state", "in", ("pending", "retry", "running")),
                ])
                if not pending:
                    job_model.create({
                        "document_id": document.id, "provider_id": provider.id,
                        "job_type": "delete_export",
                    })
            document.message_post(body=self.env._(
                "Reconciliation: document is no longer current but was "
                "still marked exported — queued for de-indexing."
            ))

    def _reconcile_missing_exports(self, batch_size):
        providers = self.env["legal.ai.provider"].search([
            ("active", "=", True), ("enabled_for_export", "=", True),
        ])
        if not providers:
            return
        candidates = self.search([
            ("status", "=", "approved"), ("is_current", "=", True),
            ("export_state", "in", ("not_requested", "stale", "failed")),
        ], limit=batch_size)
        job_model = self.env["legal.ai.job"]
        for document in candidates:
            allowed, _reason = document._check_export_policy()
            if not allowed:
                continue
            for provider in providers:
                pending = job_model.search_count([
                    ("document_id", "=", document.id), ("provider_id", "=", provider.id),
                    ("job_type", "=", "export"),
                    ("state", "in", ("pending", "retry", "running")),
                ])
                if not pending:
                    job_model.create({
                        "document_id": document.id, "provider_id": provider.id,
                        "job_type": "export",
                    })
            document.export_state = "queued"

    # -- Retention -----------------------------------------------------
    @api.model
    def _cron_apply_retention(self, dry_run=False, batch_size=50):
        """dry_run=True (or the "Retention (Dry Run)" server action) logs
        what WOULD happen without writing anything. See
        legal.retention.policy and docs/operations.md — this only ever
        archives (reversible status change) and, well after that, purges
        the binary content of non-current versions on already-archived
        documents. The current version and every metadata row are always
        kept.

        FR : dry_run=True (ou l'action serveur « Rétention (essai à
        blanc) ») journalise ce qui SE PASSERAIT sans rien écrire. Voir
        legal.retention.policy et docs/operations.md — ceci ne fait
        jamais qu'archiver (changement de statut réversible) et, bien
        après, purger le contenu binaire des versions non courantes sur
        des documents déjà archivés. La version courante et toute ligne
        de métadonnées sont toujours conservées.
        """
        report = {"archived": [], "purged_versions": []}
        self._apply_retention_archive(report, dry_run, batch_size)
        self._apply_retention_purge(report, dry_run, batch_size)
        _logger.info(
            "Legal Knowledge Watch retention run (dry_run=%s): %s",
            dry_run, report,
        )
        return report

    def _apply_retention_archive(self, report, dry_run, batch_size):
        policies = self.env["legal.retention.policy"].search([
            ("archive_rejected_after_days", ">", 0),
        ])
        for policy in policies:
            domain = [("status", "=", "rejected")]
            if policy.company_id:
                domain.append(("company_id", "=", policy.company_id.id))
            if policy.source_id:
                domain.append(("source_id", "=", policy.source_id.id))
            threshold = fields.Datetime.now() - timedelta(
                days=policy.archive_rejected_after_days
            )
            domain.append(("last_checked_at", "<=", threshold))
            for document in self.search(domain, limit=batch_size):
                report["archived"].append(document.reference)
                if not dry_run:
                    document.action_archive_document()
                    document.message_post(body=self.env._(
                        "Retention policy '%(policy)s': archived (rejected "
                        "and unchanged for %(days)s+ days).",
                        policy=policy.name, days=policy.archive_rejected_after_days,
                    ))

    def _apply_retention_purge(self, report, dry_run, batch_size):
        policies = self.env["legal.retention.policy"].search([
            ("delete_binary_after_archived_days", ">", 0),
        ])
        for policy in policies:
            domain = [("status", "=", "archived"), ("archived_at", "!=", False)]
            if policy.company_id:
                domain.append(("company_id", "=", policy.company_id.id))
            if policy.source_id:
                domain.append(("source_id", "=", policy.source_id.id))
            threshold = fields.Datetime.now() - timedelta(
                days=policy.delete_binary_after_archived_days
            )
            domain.append(("archived_at", "<=", threshold))
            for document in self.search(domain, limit=batch_size):
                old_versions = document.version_ids.filtered(lambda v: not v.is_current)
                for version in old_versions:
                    self._purge_version_binary(document, version, report, dry_run)

    def _purge_version_binary(self, document, version, report, dry_run):
        label = f"{document.reference}#v{version.sequence}"
        if version.storage_backend == "attachment" and version.attachment_id:
            report["purged_versions"].append(label)
            if not dry_run:
                version.attachment_id.unlink()
                version.write({
                    "attachment_id": False,
                    "change_summary": (
                        (version.change_summary or "")
                        + "\n[retention] binary purged"
                    ),
                })
        elif version.storage_backend == "dms" and version.dms_file_res_id:
            from ..services.storage_dms import DmsStorageBackend

            if not DmsStorageBackend(self.env).is_available():
                return
            report["purged_versions"].append(label)
            if dry_run:
                return
            try:
                self.env["dms.file"].sudo().browse(version.dms_file_res_id).unlink()
            except Exception as exc:  # noqa: BLE001 - never let a purge failure abort the batch
                _logger.warning(
                    "Retention: failed to purge dms.file %s for %s: %s",
                    version.dms_file_res_id, document.reference, exc,
                )
                return
            version.write({"dms_file_res_id": False})
