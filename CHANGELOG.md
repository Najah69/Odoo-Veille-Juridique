# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
