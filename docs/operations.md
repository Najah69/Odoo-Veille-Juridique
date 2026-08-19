# Operations

## Crons

| Cron | Cadence | Role |
|---|---:|---|
| `Legal Knowledge Watch: Fetch due watches` | 15 min | Runs `legal.watch._cron_fetch_due_watches()`, which selects due, schedule-enabled, non-manual watches and calls `_run_ingestion(trigger="cron")` on each. |
| `Legal Knowledge Watch: Process AI jobs` | 10 min | Runs `legal.ai.job._cron_process_pending_jobs()` — see `docs/ai-providers.md`. |
| `Legal Knowledge Watch: Reconcile` | daily | Runs `legal.knowledge.document._cron_reconcile_exports()` — see "Reconciliation" below. Active by default; purely corrective, never deletes anything. |
| `Legal Knowledge Watch: Apply Retention (dry run)` | weekly | Runs `_cron_apply_retention(dry_run=True)` — **disabled by default**. Enabling it only ever logs what would happen; a real run requires the **Apply Retention** wizard (Configuration menu) or a manual `dry_run=False` call. See "Retention" below. |

In this Odoo 18 build, `ir.cron` no longer carries `model_id`/`state`/`code`
directly: it delegates to an `ir.actions.server` record via
`ir_actions_server_id` (see `data/ir_cron.xml`). Do not write a cron record
in the older single-record style — it will not install.

## Diagnosing a run

Every attempt (manual or cron) creates a `legal.ingestion.run` record with:

- `state`: `running` (transient), `success`, `partial`, `failed`, `skipped`.
- Counters: `fetched_count`, `created_count`, `updated_count`
  (new versions of an existing document), `duplicate_count` (identical
  content re-submitted), `filtered_count` (excluded by a relevance rule
  before ever reaching deduplication), `error_count`.
- `log_excerpt`: non-sensitive diagnostic text (item-level error messages).
  Never contains secrets, tokens or full document content.

A `skipped` run means another run for the same watch was already in
progress when this one tried to start (see the concurrency note in
`docs/connectors.md`) — it is not an error and needs no action.

A `failed` run means either the connector configuration was invalid, or the
fetch itself failed (network/HTTP error) before any item could be
processed — check `log_excerpt` first.

A `partial` run means at least one item failed after the fetch succeeded;
`created_count`/`updated_count`/`duplicate_count`/`filtered_count` still
reflect what *did* succeed. Re-running the watch is always safe: ingestion
is idempotent (see the deduplication order in `docs/connectors.md`).

## Manual controls

On a `legal.watch` with a non-`manual` connector:

- **Test Connection**: validates `configuration_json` (and, for RSS, the
  `allowed_domains` gate) without making a network call for anything beyond
  what `validate_configuration()` needs — no documents are created.
- **Run Now**: runs `_run_ingestion(trigger="manual")` immediately, ignoring
  `schedule_enabled`/`interval_minutes` (those only gate the cron), and
  shows a notification with the resulting counters.

## Adding a new RSS watch — minimal example

1. Configuration → Sources: create a `legal.source` if none fits yet.
2. Watches → New: set `connector_code = rss`, and
   `configuration_json = {"feed_url": "https://example.gouv.fr/actualites.rss"}`.
3. **Test Connection**, then **Run Now** once to verify manually before
   enabling `schedule_enabled`.
4. Add relevance rules under the "Relevance Rules" tab if you want automatic
   scoring/tagging/filtering; without any rule, every fetched item is kept
   as `status=new` with `relevance_score=0`.

## Reconciliation

Odoo/DMS is the durable registry; any export index (AI-Brain, a webhook
receiver, the filesystem/JSONL provider) is a derived, reconstructible
projection of it. `_cron_reconcile_exports()` detects and repairs drift
between the two — it never deletes local history, only (re)queues jobs or
flags state:

- A document that is no longer current (`is_current=False`) but is still
  `export_state in (exported, queued)` gets flagged `stale` and a
  `delete_export` job is queued for every export-enabled provider (skipped
  if one is already pending, so re-running reconciliation is idempotent).
- An approved, current document sitting in `export_state in (not_requested,
  stale, failed)` that would actually pass `_check_export_policy()` gets a
  fresh `export` job queued.
- A `legal.ai.job` stuck in `state=running` for over an hour (a crash
  during processing — the PostgreSQL row lock itself is released
  automatically, but the job's own state field isn't) is reset to `retry`.
- A `legal.ingestion.run` stuck in `state=running` for over two hours is
  marked `failed` (not retried automatically — the watch's own next
  scheduled/manual run creates a fresh, independent run).

## Retention

Deliberately conservative, configured via `legal.retention.policy`
(company/source → day thresholds; a policy with `0` in a field disables
that half of retention entirely, and with **no policy configured at all,
retention does nothing**):

1. **Archive**: a `rejected` document untouched (`last_checked_at`) for
   longer than `archive_rejected_after_days` is archived — a normal,
   reversible status change via `action_archive_document()`, which also
   stamps `archived_at`.
2. **Purge** (only after archiving, and only after a *separate* grace
   period `delete_binary_after_archived_days` counted from `archived_at`):
   removes the stored binary content of **non-current (superseded)
   versions only** on an already-archived document. The current version's
   content and every version/document metadata row (hash, dates,
   provenance) are never touched by retention, under any configuration.

Both steps run through `_cron_apply_retention(dry_run=...)`, which returns
a report (`{"archived": [...], "purged_versions": [...]}`) logged via
`_logger.info` regardless of `dry_run`. To actually apply retention:
Configuration → **Apply Retention**, uncheck **Dry Run**, click **Run**.
The scheduled cron itself is disabled by default and, even if enabled,
only ever runs with `dry_run=True` — a real run is always a deliberate,
one-off action, never something a forgotten cron toggle can trigger.
