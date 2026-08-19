"""Filesystem provider tests. Real local filesystem I/O against a
tempfile.TemporaryDirectory — no mocking needed (unlike the HTTP
providers), since there is no network involved by construction.

FR : Tests du provider filesystem. Vraies entrées/sorties sur un
tempfile.TemporaryDirectory local — aucun mock nécessaire (contrairement
aux providers HTTP), puisqu'il n'y a aucun réseau impliqué par
construction.
"""
import json
import os
import tempfile

from ..services.ai_provider_base import AIProviderError
from ..services.filesystem_jsonl_provider import FilesystemJsonlProvider
from .common import LegalWatchTransactionCase


class TestFilesystemJsonlProvider(LegalWatchTransactionCase):
    def _make_provider(self, directory):
        return self.env["legal.ai.provider"].create({
            "name": "Filesystem Test", "provider_type": "filesystem",
            "auth_mode": "none",
            "configuration_json": json.dumps({"directory": directory}),
        })

    def test_missing_directory_config_raises(self):
        provider = self.env["legal.ai.provider"].create({
            "name": "No dir", "provider_type": "filesystem", "auth_mode": "none",
        })
        with self.assertRaises(AIProviderError):
            FilesystemJsonlProvider(provider).healthcheck()

    def test_healthcheck_on_nonexistent_directory_raises(self):
        provider = self._make_provider("/nonexistent/path/for/sure")
        with self.assertRaises(AIProviderError):
            FilesystemJsonlProvider(provider).healthcheck()

    def test_classify_is_not_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(tmp)
            with self.assertRaises(AIProviderError):
                FilesystemJsonlProvider(provider).classify({"document": {}})

    def test_export_writes_one_json_file_per_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(tmp)
            result = FilesystemJsonlProvider(provider).export_document({
                "reference": "LKW-2026-00001", "content_hash": "sha256:abc",
                "title": "Test",
            })
            path = os.path.join(tmp, "LKW-2026-00001.json")
            self.assertTrue(os.path.exists(path))
            self.assertEqual(result["remote_id"], path)
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data["title"], "Test")

    def test_export_upsert_overwrites_the_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(tmp)
            backend = FilesystemJsonlProvider(provider)
            backend.export_document({"reference": "LKW-2026-00002", "title": "First"})
            backend.export_document({"reference": "LKW-2026-00002", "title": "Second"})

            path = os.path.join(tmp, "LKW-2026-00002.json")
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data["title"], "Second")
            self.assertEqual(len(os.listdir(tmp)), 1)

    def test_export_without_reference_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(tmp)
            with self.assertRaises(AIProviderError):
                FilesystemJsonlProvider(provider).export_document({"title": "No ref"})

    def test_delete_removes_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(tmp)
            backend = FilesystemJsonlProvider(provider)
            backend.export_document({"reference": "LKW-2026-00003"})
            path = os.path.join(tmp, "LKW-2026-00003.json")
            self.assertTrue(os.path.exists(path))

            backend.delete_document("LKW-2026-00003")
            self.assertFalse(os.path.exists(path))

    def test_delete_nonexistent_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(tmp)
            FilesystemJsonlProvider(provider).delete_document("LKW-DOES-NOT-EXIST")

    def test_reference_is_sanitized_in_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            provider = self._make_provider(tmp)
            FilesystemJsonlProvider(provider).export_document({
                "reference": "../../etc/passwd", "title": "x",
            })
            # EN: Path traversal characters must be neutralized: no file
            # should land outside the configured directory.
            # FR : Les caractères de traversée de chemin doivent être
            # neutralisés : aucun fichier ne doit atterrir hors du
            # répertoire configuré.
            for name in os.listdir(tmp):
                self.assertNotIn("..", name)
                self.assertNotIn(os.sep, name)
