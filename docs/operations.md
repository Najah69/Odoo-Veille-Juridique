# Operations

## Crons

| Cron | Cadence | Role |
|---|---:|---|
| `Legal Knowledge Watch: Fetch due watches` | 15 min | Runs `legal.watch._cron_fetch_due_watches()`, which selects due, schedule-enabled, non-manual watches and calls `_run_ingestion(trigger="cron")` on each. |

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
