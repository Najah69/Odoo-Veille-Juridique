"""Filesystem export provider: one JSON file per document
(`<directory>/<reference>.json`), so a local index can be rebuilt without
AI-Brain or any other network service — `cat *.json` (or a small script
wrapping each in a line) reconstructs a JSONL corpus. Writing always
overwrites the file for that reference, which makes "upsert" trivially
idempotent — no separate Idempotency-Key mechanism is needed here, unlike
the HTTP-based providers.

classify() is intentionally unsupported (raises AIProviderError): a flat
file sink has nothing to classify against — enable_for_classification
should stay False for this provider_type.
"""
import json
import os
import re

from .ai_provider_base import AIProviderError, BaseAIProvider
from .ai_provider_registry import register_provider


def _safe_filename(reference):
    # Strip path separators first, then collapse any run of dots down to a
    # single one: without this second step, e.g. "../../etc/passwd" would
    # sanitize to the merely-odd-looking (but not actually traversal-
    # capable, since no separator survives) ".._.._etc_passwd" — collapsing
    # dots avoids leaving that confusing residue at all.
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", reference)
    safe = re.sub(r"\.{2,}", ".", safe)
    return safe + ".json"


@register_provider
class FilesystemJsonlProvider(BaseAIProvider):
    provider_type = "filesystem"

    def _directory(self):
        try:
            config = json.loads(self.record.configuration_json or "{}")
        except (TypeError, ValueError) as exc:
            raise AIProviderError(
                f"configuration_json is not valid JSON: {exc}"
            ) from exc
        directory = config.get("directory")
        if not directory:
            raise AIProviderError(
                "configuration_json.directory is required for the "
                "filesystem provider."
            )
        return directory

    def healthcheck(self):
        directory = self._directory()
        if not os.path.isdir(directory):
            raise AIProviderError(f"Directory does not exist: {directory}")
        if not os.access(directory, os.W_OK):
            raise AIProviderError(f"Directory is not writable: {directory}")
        return {"status": "ok", "directory": directory}

    def classify(self, document_payload):
        raise AIProviderError(
            "The filesystem provider does not support classify()."
        )

    def export_document(self, document_payload):
        directory = self._directory()
        reference = document_payload.get("reference")
        if not reference:
            raise AIProviderError("document_payload is missing 'reference'.")
        try:
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, _safe_filename(reference))
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(
                    document_payload, handle, ensure_ascii=False,
                    indent=2, sort_keys=True,
                )
        except OSError as exc:
            raise AIProviderError(f"Failed to write export file: {exc}") from exc
        return {"remote_id": path}

    def delete_document(self, reference):
        directory = self._directory()
        path = os.path.join(directory, _safe_filename(reference))
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError as exc:
            raise AIProviderError(f"Failed to delete export file: {exc}") from exc
