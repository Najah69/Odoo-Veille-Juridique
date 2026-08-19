# Legal Knowledge Watch

[![Tests](https://github.com/Najah69/Odoo-Veille-Juridique/actions/workflows/tests.yml/badge.svg)](https://github.com/Najah69/Odoo-Veille-Juridique/actions/workflows/tests.yml)

Odoo 18 Community module to collect, normalize, deduplicate and archive legal
and regulatory content from trusted sources, with a human review workflow and
a locally-owned document history.

> **This is a documentation and monitoring tool. It does not provide legal,
> tax or accounting advice, and it does not replace consultation with a
> qualified lawyer, accountant or other professional.**

## Status: Phase 6 (security audit & release candidate)

- Manual import (file upload or pasted text).
- **RSS/Atom connector**: conditional GET (ETag/Last-Modified), bounded
  retries, domain whitelist, never scrapes a linked article by default.
- **Légifrance/PISTE connector** (LODA collection: lois, ordonnances,
  décrets, arrêtés) — OAuth2 Client Credentials, keyword+date+nature
  search, full-text retrieval. See `docs/legifrance-piste.md` for exactly
  what was verified against real sources (no PISTE account was available
  to test this live) vs. what still needs checking against a live sandbox.
- **Deterministic relevance rules** (keyword/regex/source-field →
  include/exclude/score/tag/requires_review), evaluated before ingestion.
- Scheduled fetch cron with a PostgreSQL-row-lock guard against concurrent
  runs of the same watch (see `docs/connectors.md`).
- **Optional OCA DMS storage backend**, selectable per watch/import
  (`auto`/`dms`/`attachment`) — never a hard dependency; see
  `docs/oca-dms-integration.md`.
- **Agnostic AI/export provider layer** (`legal.ai.provider`/`legal.ai.job`/
  `legal.document.enrichment`): `webhook`, `ai_brain_http` (this project's
  own documented HTTP contract) and a network-free `filesystem` (JSONL)
  provider. AI never overrides a human decision — classification only ever
  sets a "needs review" flag, and export is gated by a configurable,
  fail-closed policy re-checked fresh on every job attempt. See
  `docs/ai-providers.md`.
- **Configurable export policies** (`legal.export.policy`, per
  company/source/watch) and a **reconciliation cron** that detects and
  repairs drift (missing exports, superseded-but-still-exported documents,
  stuck jobs/runs) without ever deleting local history — Odoo remains the
  durable registry, any export index is a reconstructible projection.
- **Retention** (`legal.retention.policy`): archive old rejected documents
  (reversible), then — only after a separate explicit grace period —
  purge just the binary content of non-current (superseded) versions on
  already-archived documents. The current version and every metadata row
  are never touched. Dry-run by default; a real run is always a
  deliberate action. See `docs/operations.md`.
- Normalization, SHA-256 content hashing, deduplication, version history.
- Document review workflow (`new → qualified → review → approved/rejected →
  archived/superseded`).
- Multi-company record rules and role-based access control.
- **Security-hardening pass**: closed a cross-company data-exposure gap on
  `legal.ai.job`/`legal.document.enrichment`/3 other config models,
  restricted `legal.document.version` writes to the sanctioned creation
  path only, and added SSRF/redirect/response-size protection to every
  outbound call to an admin-configured URL. See `docs/security.md` for the
  full audit, including what remains a documented residual risk.

See `CHANGELOG.md` for exactly what is implemented today.

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

No OCA module is required. A Légifrance/PISTE watch needs PISTE
credentials (see `docs/legifrance-piste.md`); every other feature works
with zero external accounts.

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
For a Légifrance/PISTE watch, see `docs/legifrance-piste.md`. To store
content in OCA DMS instead of `ir.attachment`, see
`docs/oca-dms-integration.md`. To classify documents with AI or export
approved ones to a RAG/vector-store service, see `docs/ai-providers.md`.

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

Full data model, document lifecycle and ingestion pipeline:
`docs/architecture.md`. Contributing a change: `CONTRIBUTING.md`.

## Security & data

- Manual import, RSS and OCA DMS need no secrets at all. Légifrance/PISTE
  and any AI/export provider using bearer or header auth need a token,
  read via environment variables (preferred) or system parameters — never
  committed, never displayed in the UI, never logged. See
  `docs/legifrance-piste.md` and `docs/ai-providers.md`.
- Access is controlled by four groups (`User`, `Reviewer`, `Manager`,
  `Administrator`), company-scoped record rules on every model that
  carries a `company_id`, and a restricted write path on
  `legal.document.version` (see `docs/security.md`).
- Document deletion (`unlink`) is restricted to `Administrator`; use
  **Archive** for normal end-of-life instead, so the audit trail (chatter,
  version history) is preserved.
- Every outbound call to an admin-configured URL (RSS `feed_url`, AI
  provider `base_url`) is checked against literal private/loopback/
  link-local addresses, never follows a redirect, and is capped at 5 MB.
  See `docs/security.md` for exactly what this does and does not cover
  (hostname-based SSRF via DNS is a documented residual gap, not silently
  ignored).

Full audit, threat model and residual risks: `docs/security.md`.

## Running the tests

From an Odoo 18 environment with this module on the addons path:

```bash
odoo --test-enable --stop-after-init -i legal_knowledge_watch -d <test_db>
```

All tests run offline: every RSS/Légifrance/AI-provider test mocks the
`requests` calls (including the OAuth token request) — the suite never
makes a real HTTP call.

## License

AGPL-3.0-or-later. See `LICENSE`.
