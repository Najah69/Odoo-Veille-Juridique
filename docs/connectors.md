# Connectors

## Contract

A connector never writes to Odoo. It only turns a remote source into a list
of `CandidateItem` objects (`legal_knowledge_watch/services/base_connector.py`).
All persistence — deduplication, versioning, storage — happens in
`legal.knowledge.document._ingest_candidate()`, called by the orchestrator
(`legal.watch._run_ingestion()`).

```python
class BaseConnector(ABC):
    code = None  # unique registry key, e.g. "rss"

    def __init__(self, watch, logger): ...

    def validate_configuration(self):
        """Raise ConnectorConfigError on a fixable problem. No network call,
        no Odoo write."""

    def fetch(self, cursor, limit=100):
        """Return a FetchResult. Raise ConnectorFetchError instead of
        letting a raw exception propagate, so the orchestrator can record a
        clean failure reason."""
```

`CandidateItem` fields: `source_url`, `canonical_url`, `title`,
`external_id`, `raw_content`, `plain_text`, `published_at`, `updated_at`,
`content_type`, `language`, `source_metadata` (dict).

`FetchResult` fields: `items` (list of `CandidateItem`), `next_cursor` (an
opaque string persisted on `legal.watch.last_cursor`, passed back on the
next call), `diagnostics` (dict; connectors should set
`diagnostics["item_errors"]` — a list of `{"title", "error"}` — for entries
that failed to parse without aborting the whole fetch).

To add a connector: implement `BaseConnector`, decorate the class with
`@register_connector` (from `services/connector_registry.py`), and add its
code to `legal.watch.connector_code`'s selection.

## RSS/Atom connector

Code: `rss`. Configuration lives in `legal.watch.configuration_json` as a
JSON object:

```json
{
  "feed_url": "https://example.gouv.fr/actualites.rss",
  "fetch_linked_content": false,
  "allowed_domains": ["example.gouv.fr"],
  "max_items_per_run": 50,
  "request_timeout_seconds": 20,
  "max_response_bytes": 5000000,
  "user_agent": "optional override"
}
```

Behavior:

- `feed_url` is required and must be `http(s)`. If `allowed_domains` is set,
  `feed_url`'s host must be in it (validated before any network call).
- `fetch_linked_content` (default `false`): when `true`, the full article
  page is fetched **only** if its own host is also in `allowed_domains`.
  Never scrapes a linked page by default — the feed's own summary/title is
  used as the normalized text instead, and the link itself is always kept
  as `source_url` regardless.
- Conditional GET: `ETag`/`Last-Modified` from the previous response are
  sent back as `If-None-Match`/`If-Modified-Since` on the next run. A `304`
  response returns an empty `FetchResult` without touching `last_cursor`.
- Transient failures (timeout, connection error, HTTP 429/5xx) are retried
  up to 3 times with a bounded exponential backoff (1s, 2s). A `4xx` other
  than 429 is never retried. A response over `max_response_bytes` aborts
  the fetch for that URL.
- A malformed entry (e.g. missing `<link>`) is skipped and reported in
  `diagnostics["item_errors"]`; it does not abort the rest of the feed.

## Relevance rules

`legal.watch.rule` (`services/relevance_service.py`) are evaluated **before**
ingestion, once per candidate, in this phase without any AI involvement:

| Field | Values |
|---|---|
| `rule_type` | `keyword`, `regex`, `source_field` (documentation-only categorisation) |
| `target_field` | `title`, `plain_text`, `authority`, `source_url`, `canonical_url` |
| `operator` | `contains`, `equals`, `matches` (regex), `in`, `not_in` (comma-separated `value`) |
| `effect` | `include`, `exclude`, `score`, `tag`, `requires_review` |

Semantics:

- `exclude` always wins: if any `exclude` rule matches, the candidate is
  filtered out before ever reaching deduplication (counted as
  `filtered_count` on the run, distinct from `duplicate_count`).
- `include` is opt-in gating: if at least one `include` rule exists on the
  watch, the candidate is excluded unless at least one `include` rule
  matches. With no `include` rules at all, nothing is excluded on that
  basis.
- `score` rules accumulate into `legal.knowledge.document.relevance_score`.
- `tag` rules add `legal.tag` records to the document.
- `requires_review` sets `needs_review = True` on the document — it does
  **not** change `status` on its own; auto-approval thresholds are a later
  phase.

Triggered rule names are posted to the document's chatter for auditability.

## Concurrency and scheduling

`legal.watch._try_lock_for_run()` takes a PostgreSQL row lock
(`SELECT ... FOR UPDATE NOWAIT`) for the duration of the transaction. If
another run already holds it, the new run is recorded as `state=skipped`
instead of blocking or erroring. Locks are released automatically by
PostgreSQL when the holding transaction ends — there is no stale-lock flag
to reset after a crash.

`_cron_fetch_due_watches()` (cron `Legal Knowledge Watch: Fetch due
watches`, every 15 minutes) selects active watches with
`schedule_enabled=True` and a `connector_code` other than `manual`, and
runs each one whose `last_run_at + interval_minutes` has elapsed.
