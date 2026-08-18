"""The only file in this module that references OCA DMS model names. Every
`dms.*` field used here (dms.file.name/directory_id/content,
dms.directory.name/parent_id/storage_id) was verified against the real
OCA/dms 18.0 source (github.com/OCA/dms, branch 18.0) before being written,
not guessed. What still needs validating against a *live* DMS install
before relying on this in production is called out explicitly below.

Availability is always checked at runtime via `"dms.file" in self.env` —
never import anything from the dms module itself, so this file (and the
module as a whole) loads fine whether or not OCA DMS is installed.

sudo() is used for dms.file/dms.directory writes: this module's own
security groups already gate who may trigger an ingestion, and coupling
that to OCA DMS's separate per-directory "Access Groups" permission layer
would make ingestion fail for reasons an admin configured somewhere else
entirely. Document/directory ownership at the DMS level is a deliberate
admin-configuration concern (docs/oca-dms-integration.md), not something
this module tries to infer.
"""
from .storage_service import LegalStorageBackend, LegalStorageError


class DmsStorageBackend(LegalStorageBackend):
    code = "dms"

    def is_available(self):
        return "dms.file" in self.env

    def _resolve_directory_id(self, document):
        """Route by (company, tag) using legal.dms.directory.route, falling
        back to ir.config_parameter
        'legal_knowledge_watch.dms_default_directory_id'. Raises
        LegalStorageError (fail closed) if nothing is configured — never
        guesses or hardcodes a directory id.
        """
        routes = self.env["legal.dms.directory.route"].search(
            ["|", ("company_id", "=", False), ("company_id", "=", document.company_id.id)],
            order="sequence",
        )
        tag_ids = set(document.tag_ids.ids)
        for route in routes:
            if route.tag_id and route.tag_id.id in tag_ids:
                return route.dms_directory_id
        for route in routes:
            if not route.tag_id:
                return route.dms_directory_id

        default_id = self.env["ir.config_parameter"].sudo().get_param(
            "legal_knowledge_watch.dms_default_directory_id"
        )
        if default_id:
            try:
                return int(default_id)
            except ValueError:
                pass

        raise LegalStorageError(self.env._(
            "No DMS directory route is configured for company "
            "'%(company)s' and no default directory id is set in "
            "legal_knowledge_watch.dms_default_directory_id. Configure "
            "Configuration > DMS Directory Routing first.",
            company=document.company_id.name,
        ))

    def store(self, document, attachment_vals):
        if not self.is_available():
            raise LegalStorageError(self.env._("OCA DMS is not installed."))
        if not attachment_vals:
            return {"storage_backend": "dms", "dms_file_res_id": False}

        directory_id = self._resolve_directory_id(document)
        # dms.file.create() requires name/directory_id/content — confirmed
        # against dms/models/dms_file.py. It internally decides how to
        # physically persist the bytes (database/filestore/attachment)
        # based on the target directory's dms.storage.save_type; that
        # choice is entirely DMS's own concern, not ours.
        dms_file = self._create_dms_file({
            "name": attachment_vals["name"],
            "directory_id": directory_id,
            "content": attachment_vals["datas"],
        })
        return {"storage_backend": "dms", "dms_file_res_id": dms_file.id}

    def _create_dms_file(self, vals):
        # Isolated in its own method so tests can mock exactly this call
        # without needing a real DMS install (see docs/oca-dms-integration.md
        # — "what still needs validating against a live install").
        return self.env["dms.file"].sudo().create(vals)

    def open_action(self, version):
        if not version.dms_file_res_id or not self.is_available():
            return None
        return {
            "type": "ir.actions.act_window",
            "res_model": "dms.file",
            "res_id": version.dms_file_res_id,
            "view_mode": "form",
        }
