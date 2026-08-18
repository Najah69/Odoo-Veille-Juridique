# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [18.0.2.0.0] - Unreleased — Phase 1

### Added
- RSS/Atom connector (`services/rss_connector.py`): conditional GET
  (ETag/Last-Modified), bounded exponential-backoff retries on
  timeout/connection error/HTTP 429/5xx, no retry on other 4xx, response
  size cap, domain whitelist, `fetch_linked_content` opt-in (off by
  default — never scrapes a linked article automatically).
- Connector contract and registry (`services/base_connector.py`,
  `services/connector_registry.py`) so future connectors don't touch the
  orchestrator.
- `legal.watch.rule`: deterministic relevance rules
  (keyword/regex/source_field × contains/equals/matches/in/not_in →
  include/exclude/score/tag/requires_review), evaluated by
  `services/relevance_service.py` before ingestion.
- `legal.watch._run_ingestion()` orchestrator: PostgreSQL row-lock
  concurrency guard (`SELECT ... FOR UPDATE NOWAIT`, self-releasing on
  transaction end — no stale-lock recovery needed), per-item savepoints so
  one bad item degrades a run to `partial` instead of aborting it, cursor
  persistence, `Test Connection`/`Run Now` UI actions.
- Cron `Legal Knowledge Watch: Fetch due watches` (15 min) via the Odoo 18
  `ir.actions.server` + `ir.cron` pattern (this build's `ir.cron` no longer
  carries `model_id`/`state`/`code` directly).
- `legal.ingestion.run.filtered_count` to distinguish rule-excluded
  candidates from true content duplicates.
- `legal.knowledge.document.relevance_score` is now populated from
  triggered `score` rules (updated on every new version, not just creation).
- Test suite: RSS parsing (RSS 2.0 and Atom), malformed/dateless items,
  ETag/304, timeout/HTTP-error retry and backoff, relevance-rule
  precedence, cross-run deduplication, partial-run-on-item-error, and the
  concurrency lock's exception-handling path — entirely offline (mocked
  `requests.get`, no test tag reaches the network).

### Changed
- `external_dependencies.python` now declares `requests`, `feedparser`,
  `bs4` — the module refuses to install if any is missing (was previously
  none for the manual-import-only Phase 0).

## [18.0.1.0.0] - Unreleased — Phase 0

### Added
- Foundation of the `legal_knowledge_watch` module for Odoo 18 Community.
- Models: `legal.source`, `legal.tag`, `legal.watch` (skeleton), `legal.ingestion.run`,
  `legal.knowledge.document`, `legal.document.version`.
- Manual import wizard (file upload or pasted text — no network fetch).
- Normalization service (HTML→text, whitespace, canonical URL, SHA-256 content hash).
- Deduplication service: match by `(source, external_id)`, then canonical URL, then
  content hash.
- Document lifecycle with guarded status transitions and version history.
- Security groups (`User`, `Reviewer`, `Manager`, `Administrator`), ACLs and
  multi-company record rules.
- Test suite covering normalization, deduplication, document lifecycle, the manual
  import wizard, and multi-company isolation.

### Known limitations (by design, this phase)
- No network connector (RSS, Légifrance/PISTE): manual import only.
- No AI enrichment or export.
- No OCA DMS integration: content is stored via `ir.attachment`.
- No `static/description/icon.png` yet.
