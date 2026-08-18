# AI / export providers

## Principle

The core module (`legal.ai.job`, `legal.knowledge.document`) never imports
a specific provider. It only knows `BaseAIProvider`
(`services/ai_provider_base.py`) and dispatches by `provider_type` through
`services/ai_provider_registry.py` — exactly the same pattern as
connectors (`connector_registry.py`). Two providers ship with this module:

- `webhook` (`generic_webhook_provider.py`): the simplest possible example
  — a single URL, one JSON body with an `"action"` discriminator. Use it
  as a template for a new provider (Qdrant, OpenWebUI, AnythingLLM,
  filesystem JSONL, MCP...).
- `ai_brain_http` (`ai_brain_provider.py`): implements the contract below.

**AI is never the source of truth.** `legal.knowledge.document` (status,
hash, dates, source) always wins. AI output only ever:
- sets `needs_review = True` on a classify result that asks for it — it
  never changes `status` directly;
- gets recorded in `legal.document.enrichment`, versioned by provider,
  prompt version and input hash, always kept separate from the source
  content it was computed from.

A malformed classify response (fails `legal-enrichment-1.0` validation,
see `docs/legal-enrichment-schema-1.0.json` and
`services/enrichment_schema.py`) never silently mutates the document — the
job fails and a `state=failed` enrichment records why, for audit.

## AI-Brain HTTP contract

This contract is this project's own design — not a pre-existing external
API to reverse-engineer. Any server implementing it works with the
`ai_brain_http` provider. `base_url` is entirely admin-configured on
`legal.ai.provider`; nothing here is hardcoded.

### Healthcheck

```
GET {base_url}/api/v1/legal-knowledge/health
```

```json
{"status": "ok", "api_version": "1.0", "capabilities": ["classify", "upsert", "delete"]}
```

### Classify

```
POST {base_url}/api/v1/legal-knowledge/classify
Content-Type: application/json
Authorization: Bearer <token>        (if auth_mode = bearer)
X-Legal-Knowledge-Schema: 1.0
```

```json
{
  "request_id": "uuid",
  "document": {
    "local_id": 42,
    "reference": "LKW-2026-00042",
    "title": "Décret n° ...",
    "canonical_url": "https://...",
    "source": {"code": "legifrance", "name": "Légifrance", "trust_level": "primary"},
    "published_at": "2026-08-18T00:00:00",
    "effective_at": null,
    "document_type": "decree",
    "content_hash": "sha256:...",
    "plain_text": "...",
    "metadata": {"authority": "...", "jurisdiction": "fr"}
  },
  "policy": {"locale": "fr_FR", "require_json_schema": "legal-enrichment-1.0", "allow_legal_advice": false}
}
```

The response body is validated by this module against
`legal-enrichment-1.0` before it is trusted — see
`docs/legal-enrichment-schema-1.0.json`. Anything else (including a 2xx
response with the wrong shape) fails the job.

### Upsert (export)

```
PUT {base_url}/api/v1/legal-knowledge/documents/{reference}
Idempotency-Key: <content_hash>
```

```json
{
  "schema_version": "1.0",
  "reference": "LKW-2026-00042",
  "content_hash": "sha256:...",
  "status": "approved",
  "title": "Décret n° ...",
  "text": "Texte normalisé complet...",
  "metadata": {
    "source_url": "https://...", "canonical_url": "https://...",
    "source_name": "Légifrance", "trust_level": "primary",
    "published_at": "2026-08-18T00:00:00", "effective_at": null,
    "document_type": "decree", "themes": [], "tags": ["cotisations"],
    "jurisdiction": "fr", "language": "fr_FR", "odoo_document_id": 42
  },
  "provenance": {"collected_at": "2026-08-18T18:00:00", "version": 1, "source_metadata": {}}
}
```

`Idempotency-Key` is the document's `content_hash` — a server implementing
this contract should treat a repeated call with the same key as a no-op,
so re-running an export job after a network blip never double-writes.

### Delete

```
DELETE {base_url}/api/v1/legal-knowledge/documents/{reference}
```

Rare in practice: prefer `status: archived`/`is_current: false` in your
own index over hard deletion, since Odoo/the storage backend remains the
durable record either way (see `docs/architecture.md`).

## Export policy (fail-closed)

`legal.ai.job._run_export()` re-checks this fresh every time the job runs
(not just once at approval time), via
`legal.knowledge.document._check_export_policy()`:

- `status == 'approved'`
- `is_current == True`
- normalized text is non-empty
- `source_id.trust_level` is `primary` or `high`

If any check fails, the job is cancelled (`state=cancelled`,
`document.export_state='blocked'`) **without ever calling the provider** —
no network call, no partial export.

## Secrets

`legal.ai.provider.secret_parameter_key` names an `ir.config_parameter` —
never the secret's value. Read priority
(`services/secrets_service.py`, shared with the Légifrance connector):

1. An environment variable derived from the key, e.g.
   `legal_knowledge_watch.ai_brain.token` → `LKW_AI_BRAIN_TOKEN`.
2. The `ir.config_parameter` itself (set manually via Settings >
   Technical > System Parameters — never committed).

`verify_tls` defaults to `True`. Timeouts and bounded exponential-backoff
retry (429/5xx/network errors; other 4xx are never retried) are shared
across both providers via `services/http_retry.py`.

## Job lifecycle

`legal.ai.job.state`: `pending → running → done` (success) or
`running → retry → running → ... → failed` (transient failures, backoff
`2 × 2^(attempt-1)` minutes, capped at 5 attempts) or
`running → cancelled` (export blocked by policy — terminal, no retry,
since retrying won't change the policy outcome) or
`running → failed` directly (classify response fails schema validation —
also terminal, since a malformed response won't fix itself on retry).

Jobs are created, never processed synchronously:
- `legal.knowledge.document.action_request_ai_classification()` (manual
  button) queues one `classify` job per provider with
  `enabled_for_classification=True`.
- `action_approve()` queues one `export` job per provider with
  `enabled_for_export=True`, and sets `export_state='queued'` immediately.
- Cron `Legal Knowledge Watch: Process AI jobs` (10 min, small batches)
  calls `legal.ai.job._cron_process_pending_jobs()`, each job in its own
  PostgreSQL-row-lock guard (same self-releasing pattern as
  `legal.watch`, see `docs/connectors.md`) and savepoint.

## Prompt templates

`services/ai_prompts.py` — versioned by an explicit `prompt_version`
string stored on every enrichment, so editing a template here always
produces a new version rather than silently reinterpreting old results:

- `legal_summary_classification_fr_v1`: the only one currently wired into
  an automatic job (`classify`). Produces `legal-enrichment-1.0` JSON.
- `legal_business_impact_fr_v1`: defined and importable, but not wired
  into an automatic job type in this phase (its output shape —
  `review_priority`/`control_questions`/... — is a different, ad hoc
  shape not covered by the strict `legal-enrichment-1.0` schema). A future
  phase adding a `job_type='impact'` should give it its own schema rather
  than reusing `legal-enrichment-1.0`.

Both templates explicitly forbid personalized legal advice and require
the model to separate what the source text states from what is inferred
or uncertain.
