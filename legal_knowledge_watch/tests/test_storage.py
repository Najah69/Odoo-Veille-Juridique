"""Storage backend tests. This environment never has OCA DMS installed, so
the attachment-fallback scenarios are genuinely exercised end to end, while
the DMS-specific scenarios mock exactly the boundary that would call into
the (absent) dms.file model — see services/storage_dms.py's module
docstring for what still needs validating against a live DMS install.

FR : Tests des backends de stockage. Cet environnement n'a jamais OCA DMS
installé, donc les scénarios de repli sur attachment sont réellement
exercés de bout en bout, tandis que les scénarios spécifiques à DMS
mockent exactement la frontière qui appellerait le modèle dms.file
(absent) — voir la docstring de module de services/storage_dms.py pour ce
qui reste encore à valider contre une vraie installation DMS.
"""
from types import SimpleNamespace
from unittest.mock import patch

from odoo.exceptions import UserError

from ..services import storage_service
from ..services.storage_dms import DmsStorageBackend
from .common import LegalWatchTransactionCase

_DMS_AVAILABLE = "odoo.addons.legal_knowledge_watch.services.storage_dms.DmsStorageBackend.is_available"
_DMS_CREATE_FILE = "odoo.addons.legal_knowledge_watch.services.storage_dms.DmsStorageBackend._create_dms_file"


class TestStorageServiceDispatch(LegalWatchTransactionCase):
    def test_auto_mode_falls_back_to_attachment_when_dms_unavailable(self):
        # EN: Genuine, unmocked: DMS really isn't installed in this
        # environment.
        # FR : Réel, sans mock : DMS n'est vraiment pas installé dans cet
        # environnement.
        backend = storage_service.get_backend(self.env, "auto")
        self.assertEqual(backend.code, "attachment")

    def test_attachment_mode_is_forced_even_if_dms_were_available(self):
        with patch(_DMS_AVAILABLE, return_value=True):
            backend = storage_service.get_backend(self.env, "attachment")
        self.assertEqual(backend.code, "attachment")

    def test_dms_mode_without_dms_raises_clean_user_error(self):
        with self.assertRaises(UserError):
            storage_service.get_backend(self.env, "dms")

    def test_auto_mode_prefers_dms_when_available(self):
        with patch(_DMS_AVAILABLE, return_value=True):
            backend = storage_service.get_backend(self.env, "auto")
        self.assertEqual(backend.code, "dms")


class TestIngestionStorageFallback(LegalWatchTransactionCase):
    def test_ingest_with_auto_mode_stores_as_attachment(self):
        result = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-STORAGE-1", storage_mode="auto")
        )
        version = result["version"]
        self.assertEqual(version.storage_backend, "attachment")
        self.assertFalse(version.dms_file_res_id)
        self.assertEqual(result["document"].storage_backend, "attachment")

    def test_ingest_with_dms_mode_raises_and_leaves_no_orphan_document(self):
        candidate = self._candidate(external_id="EXT-STORAGE-2", storage_mode="dms")
        with self.assertRaises(UserError):
            self.env["legal.knowledge.document"]._ingest_candidate(candidate)

        remaining = self.env["legal.knowledge.document"].search_count(
            [("external_id", "=", "EXT-STORAGE-2")]
        )
        self.assertEqual(remaining, 0)

    def test_new_version_with_dms_mode_raises_without_corrupting_existing_version(self):
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-STORAGE-3", storage_mode="auto")
        )["document"]
        original_version = document.current_version_id

        changed = self._candidate(
            external_id="EXT-STORAGE-3", storage_mode="dms",
            plain_text="Contenu changé pour forcer une nouvelle version.",
        )
        with self.assertRaises(UserError):
            self.env["legal.knowledge.document"]._ingest_candidate(changed)

        document.invalidate_recordset()
        self.assertEqual(document.version_count, 1)
        self.assertTrue(original_version.is_current)


class TestDmsDirectoryRouting(LegalWatchTransactionCase):
    def test_resolve_directory_prefers_tag_specific_route(self):
        self.env["legal.dms.directory.route"].create([
            {"tag_id": False, "dms_directory_id": 1, "sequence": 10},
            {"tag_id": self.tag_social.id, "dms_directory_id": 42, "sequence": 20},
        ])
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-ROUTE-1", tag_ids=[self.tag_social.id])
        )["document"]

        backend = DmsStorageBackend(self.env)
        self.assertEqual(backend._resolve_directory_id(document), 42)

    def test_resolve_directory_falls_back_to_default_route(self):
        self.env["legal.dms.directory.route"].create(
            {"tag_id": False, "dms_directory_id": 7}
        )
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-ROUTE-2")
        )["document"]

        backend = DmsStorageBackend(self.env)
        self.assertEqual(backend._resolve_directory_id(document), 7)

    def test_resolve_directory_falls_back_to_config_parameter(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "legal_knowledge_watch.dms_default_directory_id", "99"
        )
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-ROUTE-3")
        )["document"]

        backend = DmsStorageBackend(self.env)
        self.assertEqual(backend._resolve_directory_id(document), 99)

    def test_resolve_directory_raises_when_nothing_configured(self):
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-ROUTE-4")
        )["document"]

        backend = DmsStorageBackend(self.env)
        with self.assertRaises(UserError):
            backend._resolve_directory_id(document)


class TestDmsStorageMocked(LegalWatchTransactionCase):
    """Exercises DmsStorageBackend.store() end to end with only the actual
    dms.file creation call mocked out — everything else (routing lookup,
    return value shape) runs for real.

    FR : Exerce DmsStorageBackend.store() de bout en bout, seul l'appel
    réel de création du dms.file est mocké — tout le reste (résolution du
    routage, forme de la valeur de retour) tourne réellement.
    """

    def test_store_creates_dms_file_with_resolved_directory(self):
        self.env["legal.dms.directory.route"].create(
            {"tag_id": False, "dms_directory_id": 55}
        )
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-MOCK-1")
        )["document"]

        backend = DmsStorageBackend(self.env)
        with patch(_DMS_AVAILABLE, return_value=True), \
             patch(_DMS_CREATE_FILE, return_value=SimpleNamespace(id=321)) as mocked_create:
            result = backend.store(document, {
                "name": "test.txt", "datas": b"ZmFrZQ==", "mimetype": "text/plain",
            })

        self.assertEqual(result, {"storage_backend": "dms", "dms_file_res_id": 321})
        mocked_create.assert_called_once_with({
            "name": "test.txt", "directory_id": 55, "content": b"ZmFrZQ==",
        })

    def test_open_action_returns_none_when_not_stored_in_dms(self):
        backend = DmsStorageBackend(self.env)
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._candidate(external_id="EXT-MOCK-2")
        )["document"]
        version = self.env["legal.document.version"].create({
            "document_id": document.id,
            "sequence": 2,
            "content_hash": "0" * 64,
            "storage_backend": "attachment",
        })
        self.assertIsNone(backend.open_action(version))
