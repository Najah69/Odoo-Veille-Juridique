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

FR : Le seul fichier de ce module qui référence des noms de modèles OCA
DMS. Chaque champ `dms.*` utilisé ici (dms.file.name/directory_id/content,
dms.directory.name/parent_id/storage_id) a été vérifié contre le vrai
code source d'OCA/dms 18.0 (github.com/OCA/dms, branche 18.0) avant
d'être écrit, jamais deviné. Ce qui reste à valider contre une
installation DMS *réelle* avant de s'y fier en production est signalé
explicitement plus bas.

La disponibilité est toujours vérifiée à l'exécution via `"dms.file" in
self.env` — on n'importe jamais rien depuis le module dms lui-même, afin
que ce fichier (et le module dans son ensemble) se charge correctement
qu'OCA DMS soit installé ou non.

sudo() est utilisé pour les écritures dms.file/dms.directory : les
groupes de sécurité propres à ce module contrôlent déjà qui peut
déclencher une ingestion, et coupler cela à la couche de permissions
séparée « Access Groups » par répertoire d'OCA DMS ferait échouer
l'ingestion pour des raisons configurées ailleurs par un administrateur.
La propriété des documents/répertoires au niveau DMS est volontairement
une préoccupation de configuration administrateur
(docs/oca-dms-integration.md), pas quelque chose que ce module cherche à
déduire.
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

        FR : Route par (société, tag) via legal.dms.directory.route, avec
        repli sur ir.config_parameter
        'legal_knowledge_watch.dms_default_directory_id'. Lève
        LegalStorageError (échec fermé) si rien n'est configuré — ne
        devine ni ne code en dur un id de répertoire.
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
        # EN: dms.file.create() requires name/directory_id/content — confirmed
        # against dms/models/dms_file.py. It internally decides how to
        # physically persist the bytes (database/filestore/attachment)
        # based on the target directory's dms.storage.save_type; that
        # choice is entirely DMS's own concern, not ours.
        # FR : dms.file.create() exige name/directory_id/content — confirmé
        # dans dms/models/dms_file.py. Il décide en interne comment
        # persister physiquement les octets (base de données/filestore/
        # pièce jointe) selon le save_type du dms.storage du répertoire
        # cible ; ce choix relève entièrement de DMS, pas de nous.
        dms_file = self._create_dms_file({
            "name": attachment_vals["name"],
            "directory_id": directory_id,
            "content": attachment_vals["datas"],
        })
        return {"storage_backend": "dms", "dms_file_res_id": dms_file.id}

    def _create_dms_file(self, vals):
        # EN: Isolated in its own method so tests can mock exactly this call
        # without needing a real DMS install (see docs/oca-dms-integration.md
        # — "what still needs validating against a live install").
        # FR : Isolé dans sa propre méthode pour que les tests puissent
        # mocker précisément cet appel sans nécessiter une vraie
        # installation DMS (voir docs/oca-dms-integration.md — « ce qui
        # reste à valider contre une installation réelle »).
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
