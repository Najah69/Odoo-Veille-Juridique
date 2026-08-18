# Legal Knowledge Watch

Odoo 18 Community module to collect, normalize, deduplicate and archive legal
and regulatory content from trusted sources, with a human review workflow and
a locally-owned document history.

> **This is a documentation and monitoring tool. It does not provide legal,
> tax or accounting advice, and it does not replace consultation with a
> qualified lawyer, accountant or other professional.**

## Status: Phase 0 (foundation)

This first version implements the foundation only:

- Manual import (file upload or pasted text) — **no network connector yet**.
- Normalization, SHA-256 content hashing, deduplication, version history.
- Document review workflow (`new → qualified → review → approved/rejected →
  archived/superseded`).
- Multi-company record rules and role-based access control.
- Storage via `ir.attachment` (no dependency on OCA DMS).

RSS/Atom, Légifrance/PISTE, OCA DMS storage and AI-assisted qualification are
planned in later phases and are **not** part of this version. See
`CHANGELOG.md` for exactly what is implemented today.

## Compatibility

- Odoo 18.0 Community.
- Python 3.12.
- Dependencies: `base`, `mail` (core Odoo only). `beautifulsoup4` is used for
  HTML normalization; `PyPDF2` is used opportunistically for PDF text
  extraction if it is installed — if it is not, the original PDF is still
  kept as an attachment and the document is flagged for human review instead
  of failing the import.

## Installation

1. Copy `legal_knowledge_watch/` into your Odoo addons path.
2. Install `beautifulsoup4` in the Odoo Python environment if it is not
   already present (`pip install beautifulsoup4`).
3. Update the apps list and install **Legal Knowledge Watch**.

No OCA module and no external API credentials are required for this phase.

## Quick start

1. **Configuration → Sources**: create at least one `legal.source` (name,
   code, authority type, trust level).
2. **Manual Import**: choose "Upload a file" (.txt, .md, .html, .htm, .pdf)
   or "Paste text", fill in the source and metadata, and import.
3. The resulting **Document** is created (or a new version is added to an
   existing one if the same source/external ID/URL already exists with
   different content). Re-importing identical content is a no-op.
4. Move the document through the review workflow from its status bar
   (`Reviewer` role or above).

## Architecture in one paragraph

`legal.knowledge.document` is the business source of truth: it never mixes
raw source content with any later analysis. Content itself lives in
`legal.document.version` records (each pointing to an `ir.attachment` for the
original file), so the full history of a document is kept even when it
changes. Deduplication is checked in this order: `(source, external_id)`,
then canonical URL within the same source, then content hash globally — this
is what makes re-importing the same content a safe, idempotent no-op instead
of creating clutter.

## Security & data

- No secrets are used or stored in this phase (no external API, no OAuth).
- Access is controlled by four groups (`User`, `Reviewer`, `Manager`,
  `Administrator`) and company-scoped record rules.
- Document deletion (`unlink`) is restricted to `Administrator`; use
  **Archive** for normal end-of-life instead, so the audit trail (chatter,
  version history) is preserved.

## Known limitation to be hardened later

Users with the base `User` role can create `legal.document.version` records
(required so the manual-import wizard works for them) and technically retain
ORM write access to that model, even though the standard UI never lets them
edit a version's content directly. This is an accepted Phase 0 trade-off,
flagged here for the dedicated security-audit phase rather than silently
left undocumented.

## Running the tests

From an Odoo 18 environment with this module on the addons path:

```bash
odoo --test-enable --stop-after-init -i legal_knowledge_watch -d <test_db>
```

All tests run offline: there is no network connector in this phase, so
nothing in the test suite makes an HTTP call.

## License

AGPL-3.0-or-later. See `LICENSE`.
