# Changelog

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [18.0.10.0.0] - Unreleased — Phase 10 (reading page)

### Added
- `/veille-juridique`: a simple, non-technical reading page for
  `legal.knowledge.document` — recent documents as clean cards (title,
  source, date, status badge, content preview), newest first. Meant as
  the landing point for a non-technical stakeholder button/link, as
  opposed to the Watches configuration screen (`/odoo/action-...`).
  `controllers/legal_watch_reader.py` + `views/legal_watch_reader_templates.xml`.
  No `sudo()` — the page respects the visiting user's own
  group/company access exactly like the backend would.
- New `website` module dependency (required for the page's layout/routing).

## [18.0.9.0.0] - Unreleased — Phase 9 (Open Lefebvre Dalloz connector)

### Added
- `services/open_lefebvre_dalloz_connector.py`
  (`connector_code = "open_lefebvre_dalloz"`): watches
  `open.lefebvre-dalloz.fr/actualites` (the free Droit social / Droit des
  affaires legal-news portal) for new articles. No documented public
  API or RSS/Atom feed exists for this site (checked live: homepage +
  `/actualites` HTML, `robots.txt`) — instead parses the
  `__NEXT_DATA__` JSON every Next.js page embeds directly in its raw
  server-rendered HTML (confirmed present via a plain HTTP GET, before
  any JavaScript runs): `props.pageProps.page.actualites`, a real list of
  `id`/`title`/`href`/`date`/`summary`/`matter`/`topicTitle`. See
  `docs/open-lefebvre-dalloz.md` for the full grounding, including the
  honest comparison to Légifrance/OpenFisca (a documented contract vs. an
  internal implementation detail) and what was tested and found NOT to
  work (`?matter=`-style server-side filtering).
- Deliberately does **not** depend on the Next.js build id (`buildId`,
  which changes on every site deploy) — re-parses the embedded JSON
  fresh on every request rather than hardcoding a build-specific URL, so
  an ordinary redeploy doesn't break it; only an actual page/data-shape
  redesign would (and does so loudly, via `ConnectorFetchError`, never
  silently).
- Cursor tracks `last_seen_date` (ISO 8601 string comparison); dedup's
  real safety net is still the module's own `(source_id, external_id)`
  order, `external_id` being the site's own stable article id.
- Offline test suite mocks `requests.get` at `services.http_retry`
  against a realistic fixture HTML embedding `__NEXT_DATA__` — no real
  network call, per this project's hard rule.

## [18.0.8.0.0] - Unreleased — Phase 8 (OpenFisca connector)

### Added
- `services/openfisca_connector.py` (`connector_code = "openfisca"`):
  watches specific legislative *parameters* (e.g. `marche_travail.
  salaire_minimum.smic.smic_b_horaire`, `prelevements_sociaux.pss.
  plafond_securite_sociale_mensuel` — the two `DEFAULT_PARAMETERS`, each
  individually verified live) for a new dated value — a different content
  model from RSS/Légifrance's document feed. Grounded against the real,
  public, unauthenticated `api.fr.openfisca.org` API and cross-checked
  against the open-source `openfisca-france` parameter source files
  (never guessed); see `docs/openfisca.md` for the full breakdown,
  including what's explicitly out of scope (scale/bareme parameters — a
  structurally different `"brackets"` response shape, detected and
  reported as a per-parameter error rather than force-parsed).
- Cursor tracks the last-seen effective date per watched parameter;
  first run for a parameter surfaces only its current value (never
  backfills decades of history), later runs surface only strictly newer
  dates. Reuses the shared `services/http_retry.py` (bounded retry, SSRF
  host check, no redirects followed, response size cap) rather than a
  new bespoke retry loop.
- `legal.watch.connector_code` gains the `openfisca` option.
- Offline test suite (`tests/test_openfisca_connector.py`): mocks
  `requests.get` at `services.http_retry` — no real network call, per
  this project's hard rule.

## [Unreleased] — Phase 7 (public docs / GitHub publish prep)

### Added
- `docs/architecture.md`: consolidated data-model/lifecycle/dedup-order
  reference — the doc three code comments have pointed to since Phase 0
  (`models/legal_knowledge_document.py`,
  `services/deduplication_service.py`, `docs/ai-providers.md`) without it
  ever actually existing.
- `.github/workflows/tests.yml`: runs the full test suite (official Odoo
  18 image + throwaway Postgres) on push/PR. Confirmed green on its first
  real run (2026-08-19, 126/126 tests, ~1m20s) after the initial GitHub
  publish.
- `.github/ISSUE_TEMPLATE/` (bug report, feature request),
  `.github/PULL_REQUEST_TEMPLATE.md`.
- `SECURITY.md`: points to GitHub private vulnerability reporting and to
  `docs/security.md` for what's already a documented, accepted tradeoff.

## [18.0.7.0.0] - Unreleased — Phase 6 (security audit / release candidate)

### Security
- **P0 — cross-company data exposure**: `legal.ai.job` and
  `legal.document.enrichment` carried a `company_id`-derivable link to
  their document but had no `ir.rule` enforcing it; `output_json` on the
  latter can hold a summary/excerpt of another company's document. Fixed:
  added `company_id` (related, deliberately **not** stored — see below)
  to both models plus `ir.rule` records for these two and three
  previously-uncovered config models (`legal.dms.directory.route`,
  `legal.export.policy`, `legal.retention.policy`). Regression tests in
  `test_multicompany.py`.
- **Fixed while testing the above**: a first attempt stored the new
  `company_id` field on `legal.ai.job`. A stored related field can be
  lazily flushed by the ORM ahead of an unrelated `search()` — which
  silently bumps `write_date` — and `_reconcile_stuck_jobs()` relies on
  `write_date` to detect a job stuck in `running`. Caught by
  `test_stuck_running_ai_job_is_reset_to_retry` failing in the release
  candidate's own test pass; fixed by leaving `company_id` unstored on
  both `legal.ai.job` and `legal.document.enrichment` (still fully usable
  in `ir.rule`/search domains — Odoo joins through a non-stored related
  field, it just isn't its own DB column).
- **P0 — direct version forgery**: `legal.document.version` granted
  `User`/`Reviewer` `perm_write=1, perm_create=1` so the manual-import
  wizard would work, which also let a plain-`User` account forge a version
  directly over ORM/RPC (arbitrary content/hash/`is_current`, bypassing
  dedup and history rules). Fixed: ACL tightened to read-only for those
  groups; `create_or_update_from_candidate()`/`_create_new_version()`
  (the single sanctioned creation path) now `.sudo()` only the
  `legal.document.version` create/write calls. Regression test in
  `test_manual_import_wizard.py`.
- **P1 — SSRF / redirects / response size** on every admin-configured
  outbound URL (RSS `feed_url`/linked-content fetch, both AI providers'
  `base_url`): new `services/url_safety.py` rejects a literal private/
  loopback/link-local/reserved IP host before any request is made
  (deliberately IP-literal-only, not DNS-resolution-based — see the
  module docstring and `docs/security.md` for why). Every outbound call
  (`rss_connector.py`, `http_retry.py`, `legifrance_connector.py`,
  `piste_oauth_client.py`) now sets `allow_redirects=False` and treats any
  `3xx` as a hard failure, and `legifrance_connector.py`/`http_retry.py`
  gained the same 5 MB response cap RSS already had. Regression tests
  across `test_rss_connector.py`, `test_ai_providers.py`,
  `test_legifrance_connector.py`.
- Full audit, what's fixed, and what's a documented residual risk (P2,
  deferred): `docs/security.md` (new). `CONTRIBUTING.md` (new): setup,
  test conventions (must run fully offline), code conventions, versioning.

## [18.0.6.0.0] - Unreleased — Phase 5

### Added
- `legal.export.policy`: configurable export gate per company/source/watch
  (most specific match wins) on top of an unconditional floor (approved,
  current, `canonical_url`/`content_hash` present, non-empty text) that no
  policy can loosen. With no policy configured, the Phase 4 default
  (`min_trust_level=high`) applies unchanged — upgrading is a no-op until
  an admin deliberately configures something.
- `legal.retention.policy` + `legal.knowledge.document.archived_at` +
  `_cron_apply_retention(dry_run=...)`: archives old `rejected` documents
  (reversible), then — only after a *separate* explicit grace period from
  `archived_at` — purges the stored binary of **non-current versions
  only** on already-archived documents. The current version's content and
  every version/document metadata row are never touched by retention,
  under any configuration. The scheduled cron is disabled by default and,
  even enabled, only ever runs `dry_run=True`; a real run requires the new
  **Apply Retention** wizard — always a deliberate, one-off action.
- `export_state` gains `stale`: a document whose exported copy no longer
  matches current content (new version arrived) or is no longer current
  (superseded) is flagged rather than left silently marked `exported`.
- `legal.knowledge.document._cron_reconcile_exports()` (daily, enabled by
  default, purely corrective): re-queues missing exports for
  approved/current/policy-eligible documents, queues `delete_export` jobs
  for superseded-but-still-exported documents, resets `legal.ai.job`
  stuck in `running` >1h, and marks `legal.ingestion.run` stuck in
  `running` >2h as `failed`. Every repair is idempotent (checks for an
  already-pending job before creating another) and logged.
- `services/filesystem_jsonl_provider.py`: network-free export provider —
  one JSON file per document (`<directory>/<reference>.json`), upsert =
  overwrite = trivially idempotent. Lets a local index be rebuilt with
  zero external service. Filename sanitization was hardened after writing
  its test: path separators are stripped and runs of dots are collapsed,
  so a malicious `reference` (e.g. containing `../`) can never traverse
  outside the configured directory or leave confusing residue in the
  filename.
- Document list search view: filters for "Approved & Not Exported",
  "Export Failed", "Export Stale", "Export Blocked", "Superseded", plus
  group-by status/export_state/source — the "report" this phase asked for,
  built as filters on the existing list rather than a new dashboard model.
- Test suite: export policy resolution/precedence and every configurable
  gate, reconciliation (stale-flagging, missing-export re-queueing,
  idempotence, policy-aware skipping, stuck job/run reset), retention
  (archive dry-run/real/too-recent/idempotent, purge
  dry-run/real/current-version-preserved/idempotent), filesystem provider
  (including the path-traversal-hardening test above) — all against real
  local state (no HTTP involved in most of these; the few that are mock
  `requests` as usual).

## [18.0.5.0.0] - Unreleased — Phase 4

### Added
- Agnostic AI/export provider layer. `services/ai_provider_base.py`
  (`BaseAIProvider`) + `services/ai_provider_registry.py` dispatch by
  `provider_type` — the job pipeline never imports a specific provider,
  matching the connector pattern from earlier phases.
- `services/generic_webhook_provider.py`: minimal reference
  implementation (single URL, `{"action": ...}` JSON body) for a
  contributor building a new provider.
- `services/ai_brain_provider.py`: implements this project's own
  documented HTTP contract (`docs/ai-providers.md`) — healthcheck
  (GET `/api/v1/legal-knowledge/health`), classify (POST `.../classify`
  with `X-Legal-Knowledge-Schema: 1.0`), upsert (PUT
  `.../documents/{reference}` with `Idempotency-Key: <content_hash>`),
  delete (DELETE `.../documents/{reference}`). This contract is this
  project's own design, not an external API — no grounding research
  needed, unlike Légifrance/OCA DMS in earlier phases.
- `services/http_retry.py`: shared bounded-retry HTTP helper (429/5xx/
  network errors retried with backoff, other 4xx not retried) used by
  both providers.
- `legal.ai.provider`, `legal.ai.job`, `legal.document.enrichment` models.
  Jobs: `pending → running → done`, `→ retry → ...` (backoff, capped at 5
  attempts) `→ failed`, or straight to `cancelled` (export blocked by
  policy) / `failed` (classify response fails schema validation) — both
  terminal, no pointless retry of an outcome retrying can't change.
- `services/enrichment_schema.py` + `docs/legal-enrichment-schema-1.0.json`:
  hand-rolled JSON Schema validator for `legal-enrichment-1.0` (no
  `jsonschema` dependency added). A schema violation never silently
  mutates document metadata — the job fails and a `state=failed`
  enrichment records why, for audit.
- `legal.knowledge.document.export_state`
  (not_requested/queued/exported/failed/blocked),
  `_check_export_policy()` (approved + current + non-empty text +
  primary/high trust_level), re-checked fresh on every job attempt, not
  frozen at approval time. A blocked export never calls the provider.
- `_ingest_candidate`'s existing per-item savepoint pattern extended: job
  processing wraps each attempt in its own savepoint too, but
  policy-blocked/schema-invalid outcomes are handled *outside* that
  savepoint (via `ExportBlockedError`/`SchemaValidationError`) so the
  audit-trail record and the final state both survive the rollback of the
  failed attempt itself.
- `services/ai_prompts.py`: two versioned prompt templates
  (`legal_summary_classification_fr_v1`, `legal_business_impact_fr_v1`),
  French, explicitly forbidding personalized legal advice. Only the first
  is wired into an automatic job type this phase — see
  `docs/ai-providers.md` for why the second isn't yet.
- Test suite: schema validator (valid/invalid payloads), both providers
  (healthcheck/classify/export/delete, timeout/429/401/invalid-JSON/
  retry/idempotency-key), job orchestration (classify success, schema
  failure with audit trail, export blocked for non-approved/low-trust
  documents with the provider never called, export success, transient
  failure retry/backoff, max-attempts exhaustion, cron batch selection) —
  entirely offline.

## [18.0.4.0.0] - Unreleased — Phase 3

### Added
- Légifrance/PISTE connector (`services/legifrance_connector.py`), LODA
  collection (lois, ordonnances, décrets, arrêtés) only in this phase.
  No PISTE Swagger UI was reachable in this environment (requires a
  registered account), so instead of guessing: cross-checked two real,
  independent sources — the public PISTE API catalog
  (`piste.gouv.fr/api-catalog-sandbox`, confirms OAuth/API hostnames) and
  `github.com/rdassignies/pylegifrance`, whose
  `models/generated/model.py` is mechanically generated by
  `datamodel-codegen` from a real `legifrance.json` OpenAPI snapshot dated
  2025-05-28. Endpoint routes, request DTOs (search/consult payloads) and
  response schemas were read from that generated file, not invented. Full
  confidence breakdown per endpoint in `docs/legifrance-piste.md`.
- `services/piste_oauth_client.py`: OAuth2 Client Credentials, short
  in-memory-only token cache (never persisted), sandbox/production host
  separation.
- `services/secrets_service.py`: environment variable
  (`LKW_LEGIFRANCE_CLIENT_ID`/`_SECRET`) checked before `ir.config_parameter`
  (`legal_knowledge_watch.legifrance.client_id`/`client_secret`, declared
  empty in `data/legifrance_config_parameters.xml` — never a real value in
  a committed file).
- Full-text retrieval (`consult/lawDecree`) walks the confirmed real
  `articles`/`sections` recursive structure and `ConsultArticle.content`
  field; a consult failure never drops the candidate — it falls back to
  title-only and records the error in `source_metadata.consult_error`
  (same fallback philosophy as the manual-import wizard's PDF handling).
- Fixed a latent bug caught during this connector's implementation:
  `legal.watch._build_candidate_dict()` hardcoded `document_type: "news"`
  for every connector — Légifrance-sourced documents now get their real
  nature (`law`/`decree`/`order`) via `source_metadata.document_type`,
  which any connector can now set; RSS still defaults to `news`.
- Test suite: OAuth success/reuse/401/timeout/missing-token, connector
  configuration validation (including "credentials configured but not
  revealed in error messages"), search+consult happy path, consult failure
  fallback, 401/429/5xx handling, `max_items_per_run` bounding, and cursor
  continuation — entirely offline (mocked `requests.post` for both the
  token and API calls).

## [18.0.3.0.0] - Unreleased — Phase 2

### Added
- Optional OCA DMS storage backend (`services/storage_dms.py`), selectable
  per watch/manual-import via `storage_mode` (`auto`/`dms`/`attachment`).
  `dms` is never a manifest dependency — availability is detected at
  runtime (`"dms.file" in self.env`), and every `dms.*` field reference was
  verified against the real OCA/dms 18.0 source before being written (see
  `docs/oca-dms-integration.md` for the exact fields confirmed and what
  still needs validating against a live install).
- `services/storage_service.py`: backend dispatch (`get_backend`) with a
  fail-closed policy — `storage_mode=dms` without DMS installed raises a
  clear `LegalStorageError` (a `UserError`) instead of silently falling
  back; `auto` prefers DMS when available; `attachment` always forces the
  attachment backend regardless of DMS availability.
- `legal.document.version.storage_backend`/`dms_file_res_id`: storage is
  recorded **per version**, not per document, so switching a watch's
  storage mode never rewrites history — only future versions use the new
  backend. `dms_file_res_id` is a plain Integer (not a Many2one) so the
  module stays installable without the `dms.file` model existing.
  `legal.knowledge.document` exposes the same info as related/stored
  fields for the current version, plus an "Open in DMS" button.
  `_ingest_candidate`'s document-creation and new-version paths are now
  wrapped in a savepoint each, so a storage failure can never leave an
  orphan document with zero versions.
- `legal.dms.directory.route`: routes a `legal.tag` (or none = default) +
  company to a target `dms.directory` id. No DMS folder/tag id is ever
  hardcoded in code — routing is purely admin-configured data, with a
  single `ir.config_parameter` fallback
  (`legal_knowledge_watch.dms_default_directory_id`) if no route matches.
- Test suite: attachment fallback in `auto` mode (genuine, unmocked — this
  environment never has DMS installed), `dms` mode's clean failure and
  no-orphan guarantee, directory-routing precedence (tag-specific > default
  > config-parameter fallback > clear error), and `DmsStorageBackend.store()`
  exercised end to end with only the actual `dms.file` creation call
  mocked (`_create_dms_file`) — per the "mock only what's genuinely
  unavailable" policy from the blueprint.

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
