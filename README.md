# Legal Knowledge Watch

Odoo 18 Community module to collect, normalize, deduplicate and archive legal
and regulatory content from trusted sources, with a human review workflow and
a locally-owned document history.

> **This is a documentation and monitoring tool. It does not provide legal,
> tax or accounting advice, and it does not replace consultation with a
> qualified lawyer, accountant or other professional.**

## Status: Phase 2 (optional OCA DMS storage)

- Manual import (file upload or pasted text).
- **RSS/Atom connector**: conditional GET (ETag/Last-Modified), bounded
  retries, domain whitelist, never scrapes a linked article by default.
- **Deterministic relevance rules** (keyword/regex/source-field →
  include/exclude/score/tag/requires_review), evaluated before ingestion.
- Scheduled fetch cron with a PostgreSQL-row-lock guard against concurrent
  runs of the same watch (see `docs/connectors.md`).
- **Optional OCA DMS storage backend**, selectable per watch/import
  (`auto`/`dms`/`attachment`) — never a hard dependency; see
  `docs/oca-dms-integration.md`.
- Normalization, SHA-256 content hashing, deduplication, version history.
- Document review workflow (`new → qualified → review → approved/rejected →
  archived/superseded`).
- Multi-company record rules and role-based access control.

Légifrance/PISTE and AI-assisted qualification are planned in later phases
and are **not** part of this version. See `CHANGELOG.md` for exactly what
is implemented today.

## Compatibility

- Odoo 18.0 Community.
- Python 3.12.
- Dependencies: `base`, `mail` (core Odoo only). External Python packages:
  `requests`, `feedparser`, `bs4` (beautifulsoup4) — declared in the
  manifest's `external_dependencies`, so the module refuses to install if
  any is missing. `PyPDF2` is used opportunistically for PDF text
  extraction in the manual-import wizard if it is installed — if it is not,
  the original PDF is still kept as an attachment and the document is
  flagged for human review instead of failing the import.

## Installation

1. Copy `legal_knowledge_watch/` into your Odoo addons path.
2. Install the required Python packages in the Odoo environment if not
   already present: `pip install requests feedparser beautifulsoup4`.
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

For an RSS watch instead, see `docs/operations.md` ("Adding a new RSS watch
— minimal example") and the connector/rule contract in `docs/connectors.md`.
To store content in OCA DMS instead of `ir.attachment`, see
`docs/oca-dms-integration.md`.

## Architecture in one paragraph

`legal.knowledge.document` is the business source of truth: it never mixes
raw source content with any later analysis, and it never hard-couples to a
storage technology. Content itself lives in `legal.document.version`
records, each pointing to wherever it was actually stored — an
`ir.attachment` by default, or a `dms.file` if OCA DMS is installed and
selected — so the full history of a document is kept even when it changes
or the storage backend changes. Deduplication is checked in this order:
`(source, external_id)`, then canonical URL within the same source, then
content hash globally — this is what makes re-importing the same content a
safe, idempotent no-op instead of creating clutter.

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

All tests run offline: every RSS test mocks `requests.get` — the suite never
makes a real HTTP call.

## License

AGPL-3.0-or-later. See `LICENSE`.
