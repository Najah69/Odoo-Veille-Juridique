# Security

This document is the release-candidate security audit for
`legal_knowledge_watch` (Phase 6) and the reference for how the module
handles access control, secrets, outbound network calls and deletion. It
also honestly lists what is *not* covered, rather than implying more
coverage than exists.

## Access control

Four groups, each implying the previous (`User ⊂ Reviewer ⊂ Manager ⊂
Administrator`) — see `security/security.xml`. `security/ir.model.access.csv`
grants per-model CRUD per group; every model with a `company_id` (direct or
related) also has a multi-company `ir.rule` in `security/security.xml`
restricting rows to the current user's allowed companies.

Two write paths are deliberately narrower than "own the record you can
read":

- **`legal.document.version`**: `User`/`Reviewer` get `perm_write=0,
  perm_create=0` (read-only). Versions are meant to be created exactly one
  way — through `legal.knowledge.document.create_or_update_from_candidate()`
  / `_create_new_version()` (models/legal_knowledge_document.py), the single
  entry point reached by the manual-import wizard and every connector,
  which computes the content hash, runs deduplication and keeps history
  consistent. Before this phase, `User` had `perm_write=1, perm_create=1`
  here so the wizard would work — which also meant a `User`-level account
  could call `env["legal.document.version"].create(...)` directly over
  RPC/ORM and forge a version (arbitrary content, `is_current`, hash) with
  none of those rules applied. Fixed by tightening the ACL and having
  `create_or_update_from_candidate()` / `_create_new_version()` call
  `.sudo()` only on the `legal.document.version` create/write calls
  themselves — the wizard and connectors keep working unchanged, direct
  forgery no longer does.
- **`ir.attachment` via `services/storage_service.py`**: writing this
  regression test surfaced a second, older, pre-existing gap in the same
  area — `AttachmentStorageBackend.store()` calls `ir.attachment.create()`
  on the document, which Odoo's core `ir.attachment` security requires
  *write* access on the target record for; `User`/`Reviewer` never had
  `perm_write` on `legal.knowledge.document` (by design — see the ACL
  table), so the manual-import wizard was silently broken for every role
  below `Reviewer` since Phase 0, never caught because no prior test
  exercised it as a restricted user. Fixed the same way: `.sudo()` on that
  one `ir.attachment.create()` call (matching the pattern
  `storage_dms.py`'s DMS backend already used), plus `.sudo()` on the two
  `legal.knowledge.document`/`legal.document.version` writes inside
  `_create_new_version()` that had the identical problem for a *second*
  import of already-known content. See
  `test_manual_import_wizard.py::
  test_plain_user_can_import_but_not_create_version_directly` for the
  regression test proving both this and the point above.
- **`legal.knowledge.document.unlink`**: restricted to `Administrator` via
  the model's own `_check_company_domain`-independent ACL row; every other
  role uses **Archive** instead, which preserves chatter and version
  history. (Unchanged from earlier phases — noted here for completeness.)

### Multi-company coverage (P0 finding, fixed this phase)

`legal.ai.job` and `legal.document.enrichment` carry a `company_id` related
to their document but, before this phase, had no `ir.rule` enforcing it —
a real cross-company data exposure gap, and the most sensitive one:
`legal.document.enrichment.output_json` can contain a summary/excerpt of
another company's document. `legal.dms.directory.route`,
`legal.export.policy` and `legal.retention.policy` had the same gap
(config rather than content, but still cross-company leakage of internal
routing/policy). Fixed by adding the missing `company_id` field (the two
content models) and all five `ir.rule` records — see
`security/security.xml`. Regression tests:
`tests/test_multicompany.py::test_ai_job_isolated_by_document_company` and
`::test_enrichment_isolated_by_document_company`.

`legal.ai.job.company_id`/`legal.document.enrichment.company_id` are
`related` but deliberately **not** `store=True` — a first attempt stored
both and broke `_reconcile_stuck_jobs()`'s write_date-based staleness
check (a stored related field can be lazily flushed by the ORM ahead of
an unrelated `search()`, which silently bumps `write_date`); caught by
`test_stuck_running_ai_job_is_reset_to_retry` in this phase's own test
run. A non-stored related field still works fully in an `ir.rule`/search
domain (Odoo joins through it), it just isn't its own indexed DB column —
an acceptable tradeoff at this table's size.

## Secrets

`services/secrets_service.get_secret()` is the only way any connector or
AI provider reads a credential: environment variable first (derived name,
e.g. `legal_knowledge_watch.ai_brain.token` → `LKW_AI_BRAIN_TOKEN`), then
`ir.config_parameter` as a fallback. A secret is:

- never logged (error messages are truncated and never interpolate a raw
  token — see e.g. `piste_oauth_client.py`'s
  `test_get_token_401_raises_without_leaking_secret` and
  `test_ai_providers.py`'s `test_failure_message_never_contains_the_token`);
- never displayed in a view (`secret_parameter_key` stores the *name* of
  the parameter, not its value);
- never committed — confirmed by a `git log -p` + working-tree scan across
  the full history at audit time, clean.

## Outbound network hardening

Three admin-configurable URL surfaces exist: RSS `feed_url` /
`fetch_linked_content`, and every AI/export provider's `base_url`.
Légifrance/PISTE's own API and OAuth hosts are hardcoded constants, not
admin input, so they carry a much smaller version of the same risk
(mainly: never leak the client_secret to a redirect target).

### SSRF: `services/url_safety.py`

`assert_public_host(url)` is called before every request to an admin-
configured URL (`rss_connector.py._get_with_retries`,
`http_retry.request_with_retries` — shared by both AI providers). It
rejects:

- any scheme other than `http`/`https`;
- a URL whose host is **literally** a private/loopback/link-local/
  multicast/reserved/unspecified IP address (`127.0.0.1`, `10.x`,
  `172.16-31.x`, `192.168.x`, `169.254.169.254`, `::1`, etc.), via
  Python's `ipaddress` module.

**What this does not cover, on purpose:** a *hostname* that resolves (now
or later, via DNS rebinding) to a private address. Resolving DNS to check
this was tried and reverted — it would make `assert_public_host` a real
network call, which breaks this project's hard rule that the test suite
never touches the network (every RSS/Légifrance/AI-provider test uses fake
`*.example.org` hostnames), and a resolve-then-connect check is
rebinding-vulnerable anyway unless the resolved IP is pinned for the
actual connection (a custom transport adapter — out of scope for this
phase). The mitigations that *do* apply to a malicious hostname:

- RSS: the `allowed_domains` allowlist, when configured, is checked in
  `validate_configuration()`/`_host_allowed()` independently of
  `assert_public_host` — this is the real control for RSS.
- AI providers: **no equivalent allowlist exists yet.** A `base_url`
  pointing at an attacker-controlled hostname that itself resolves to a
  private address is not caught by this phase's hardening. `base_url` is
  Administrator-only to configure (`access_legal_ai_provider_admin`), which
  bounds who could set this, but it is a real residual gap — tracked as a
  P2 follow-up (a per-provider domain allowlist mirroring RSS's).

### Redirects

Every outbound call in this module now passes `allow_redirects=False` and
treats any `3xx` response as a hard failure (`rss_connector.py`,
`legifrance_connector.py`, `piste_oauth_client.py`, `http_retry.py`). A
followed redirect would silently reach a URL that was never checked by
`assert_public_host` or the RSS allowlist — worse, for
`piste_oauth_client.py`, a followed redirect on the token request would
send `client_secret` to whatever host it points to. None of the four call
sites will do this now; regression tests exist for each (see
`test_rss_connector.py::test_redirect_is_not_followed`,
`test_legifrance_connector.py::test_fetch_search_redirect_raises` and
`::test_get_token_redirect_is_not_followed`,
`test_ai_providers.py::test_redirect_is_not_followed`).

### Response size caps

RSS already capped response size (`max_response_bytes`, default 5 MB,
streamed and checked incrementally). This phase adds the same 5 MB default
cap, checked via `Content-Length` when present and the actual body length
otherwise, to `legifrance_connector.py` and `http_retry.py` (both AI
providers) — an admin-configured or compromised endpoint can no longer
exhaust memory with an oversized response. See
`test_legifrance_connector.py::test_fetch_search_over_size_limit_raises`
and `test_ai_providers.py::test_oversized_response_is_rejected`.

### TLS

`legal.ai.provider.verify_tls` defaults to `True` and is passed straight
through to `requests` (`verify=...`) by both AI providers. There is no way
to disable it for RSS or Légifrance/PISTE (both always verify — `requests`
verifies by default and neither connector overrides that).

## Deletion and audit trail

- `legal.knowledge.document.unlink()` is Administrator-only; every other
  role archives instead, keeping chatter and `legal.document.version`
  history intact.
- Retention (`docs/operations.md`) purges only the *binary content* of
  *non-current* versions, only after archiving plus a separate explicit
  grace period, and never touches the current version's content or any
  metadata row (hash, dates, provenance) on any version. Dry-run by
  default; a real run is always an explicit action (wizard, or a manual
  `dry_run=False` call) — the scheduled cron, even if enabled, only ever
  runs `dry_run=True`.
- `legal.document.enrichment` is append-only in practice (no UI or code
  path updates an existing enrichment row) — a new classify/export attempt
  always creates a new row, preserving the full history of what an AI
  provider was asked and returned, including failed/rejected attempts.

## AI data handling

- Only `plain_text` (normalized) plus non-sensitive metadata is sent to a
  classify/export call — never the raw uploaded file, never internal Odoo
  IDs beyond `local_id`/`reference` used for round-tripping (see
  `docs/ai-providers.md`'s payload shapes).
- A classify response is validated against `legal-enrichment-1.0`
  (`services/enrichment_schema.py`) before anything is trusted; on
  failure, the raw (attacker- or bug-influenced) response is stored **as
  the enrichment record's own audit content**, never merged into the
  document. AI output can only ever set `needs_review=True` — it never
  changes `status`, never touches document content or metadata fields.
- Export is fail-closed: an unconditional floor (approved, current,
  `canonical_url`/`content_hash` set, non-empty text) that no
  `legal.export.policy` can loosen, re-checked on every job attempt, not
  cached from approval time (`docs/ai-providers.md`).

## Known, deliberately deferred (P2)

Not fixed in this phase — tracked here rather than silently left
undocumented:

- **Retry/backoff code duplication**: `rss_connector.py`,
  `legifrance_connector.py`, `piste_oauth_client.py` and `http_retry.py`
  each implement their own bounded-retry loop with slightly different
  status-code handling (Légifrance treats 401/403 specially; RSS handles
  304; the OAuth client has no size cap since token responses are tiny).
  A shared retry helper across all four would remove duplication, but the
  four call sites have different-enough semantics (streaming vs. not,
  different terminal-error sets) that unifying them was judged riskier
  than valuable for a first release candidate.
- **No CI / lint tooling configured** in this repository (no
  `.github/workflows`, no `pyproject.toml`/`flake8`/`ruff` config).
  Running the test suite is currently a manual step (`README.md`'s
  "Running the tests"). Adding CI is Prompt 8/9 territory (public
  docs/publish prep), not this phase.
- **AI provider `base_url` has no domain allowlist** equivalent to RSS's
  `allowed_domains` — see the SSRF section above. `base_url` is
  Administrator-only to set, which bounds but does not close this.

## Secrets scan

`git log -p` across the full history plus a working-tree grep for common
credential patterns (API keys, bearer tokens, private key headers,
`client_secret=`) was run at audit time: clean. No secret has ever been
committed to this repository.
