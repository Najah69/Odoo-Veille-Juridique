"""Storage backend abstraction. legal.knowledge.document is always the
business source of truth; a backend only holds the bytes for one version.

OCA DMS is never imported here or anywhere else in the module — it is
detected at runtime (see storage_dms.py) so the module stays installable
and fully functional without it.
"""
from odoo.exceptions import UserError


class LegalStorageError(UserError):
    """A storage operation could not be completed. Always a clean, User
    facing error — never let a raw backend exception (DMS or otherwise)
    propagate uncaught.
    """


class LegalStorageBackend:
    code = None

    def __init__(self, env):
        self.env = env

    def is_available(self):
        raise NotImplementedError

    def store(self, document, attachment_vals):
        """attachment_vals: {"name", "datas" (base64), "mimetype"} or falsy.
        Returns a dict of legal.document.version field values describing
        the stored link (storage_backend + backend-specific id fields).
        """
        raise NotImplementedError

    def open_action(self, version):
        """Return an ir.actions dict to open the stored content in its
        native UI, or None if not applicable/available.
        """
        return None


class AttachmentStorageBackend(LegalStorageBackend):
    code = "attachment"

    def is_available(self):
        return True

    def store(self, document, attachment_vals):
        if not attachment_vals:
            return {"storage_backend": "attachment", "attachment_id": False}
        # sudo(): ir.attachment.create() requires *write* access on the
        # target record (legal.knowledge.document), which the User/
        # Reviewer groups deliberately don't have — see
        # access_legal_knowledge_document_user in ir.model.access.csv.
        # Reached only through create_or_update_from_candidate()/
        # _create_new_version(), the same sanctioned path already sudo()d
        # for legal.document.version (see legal_knowledge_document.py) —
        # matches the DmsStorageBackend.store() pattern in storage_dms.py.
        attachment = self.env["ir.attachment"].sudo().create({
            **attachment_vals,
            "res_model": "legal.knowledge.document",
            "res_id": document.id,
        })
        return {"storage_backend": "attachment", "attachment_id": attachment.id}

    def open_action(self, version):
        if not version.attachment_id:
            return None
        return {
            "type": "ir.actions.act_window",
            "res_model": "ir.attachment",
            "res_id": version.attachment_id.id,
            "view_mode": "form",
        }


def get_backend(env, storage_mode):
    """storage_mode: 'auto', 'dms' or 'attachment'."""
    from .storage_dms import DmsStorageBackend  # local import: isolates DMS

    attachment_backend = AttachmentStorageBackend(env)
    dms_backend = DmsStorageBackend(env)

    if storage_mode == "attachment":
        return attachment_backend
    if storage_mode == "dms":
        if not dms_backend.is_available():
            raise LegalStorageError(env._(
                "Storage mode 'dms' was requested but OCA DMS is not "
                "installed on this database. Install OCA DMS, or switch "
                "this watch's (or import's) storage mode to 'auto' or "
                "'attachment'."
            ))
        return dms_backend
    # auto
    return dms_backend if dms_backend.is_available() else attachment_backend
