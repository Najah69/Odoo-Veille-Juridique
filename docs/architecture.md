# Architecture

This is the consolidated reference for how the pieces fit together — the
document behind three `see docs/architecture.md` pointers already left in
the code since Phase 0 (`models/legal_knowledge_document.py`,
`services/deduplication_service.py`, `docs/ai-providers.md`) that were
never actually resolved until now. For a specific layer's own detail, see
`docs/connectors.md` (ingestion), `docs/ai-providers.md` (AI/export),
`docs/oca-dms-integration.md` (storage), `docs/operations.md`
(reconciliation/retention/crons), `docs/security.md` (access/network).

## The source-of-truth principle

`legal.knowledge.document` is the business record: identity, status,
review workflow, relevance score, tags. It never mixes raw source content
with any later analysis (`legal.document.enrichment`) or hard-couples to
a storage technology. Content itself lives in `legal.document.version`
records — immutable snapshots, never edited or deleted (only their
*binary* can later be purged by retention, see `docs/operations.md`) —
each pointing to wherever it was actually stored: an `ir.attachment` by
default, or a `dms.file` if OCA DMS is installed and selected
(`storage_backend`, `services/storage_service.py` +
`services/storage_dms.py`). This is what lets the storage backend change,
or a document accumulate 20 versions over years, without ever losing
history or needing a migration.

The same principle extends outward: Odoo (plus whichever storage backend
a version chose) is the **durable registry**. Any AI-Brain/webhook/
filesystem export index is a **reconstructible projection** of it — see
`docs/ai-providers.md` and `docs/operations.md`'s "Reconciliation"
section for what that means operationally.

## Data model at a glance

```
legal.source            (referential — no company_id, shared across companies)
   └─ legal.watch        (company-scoped: what to fetch, how, how often)
        ├─ legal.watch.rule        (relevance rules, evaluated pre-ingestion)
        └─ legal.ingestion.run     (one row per fetch attempt, manual or cron)

legal.knowledge.document          (company-scoped: the business record)
   ├─ legal.document.version[]     (immutable content snapshots, 1..N)
   ├─ legal.document.enrichment[]  (AI/rule analysis results, append-only)
   ├─ legal.ai.job[]               (classify/export/delete_export work units)
   └─ legal.tag[] (m2m)

legal.ai.provider        (company-scoped or global: webhook/ai_brain_http/filesystem)
legal.export.policy      (company/source/watch → export gate, most-specific-wins)
legal.retention.policy   (company/source → archive/purge day thresholds)
```

`legal.source` deliberately has **no** `company_id` — it's a shared
referential list (an official gazette exists independently of which
company is watching it); `legal.watch` and `legal.knowledge.document` are
where company-scoping actually starts. See `docs/security.md` for the
full multi-company `ir.rule` coverage across every other model.

## Ingestion pipeline

```
connector.fetch() → CandidateItem[] → relevance rules → deduplication → document/version
```

1. A **connector** (`docs/connectors.md`) turns a remote source into
   `CandidateItem` objects. It never writes to Odoo directly.
2. **Relevance rules** (`legal.watch.rule`) run first, per candidate:
   `exclude` always wins, `include` is opt-in gating, `score`/`tag`/
   `requires_review` are additive. A filtered-out candidate never reaches
   deduplication (`filtered_count`, distinct from `duplicate_count`).
3. **Deduplication** (`services/deduplication_service.py`) checks, in
   this fixed order: `(source_id, external_id)` when `external_id` is
   known, then `canonical_url` within the same source, then
   `content_hash` globally (an identical republication elsewhere is
   flagged a duplicate of the *first* document that had that content, not
   a second document). This order — identity signals before content —
   is what makes re-running a watch idempotent: the same item fetched
   twice never creates clutter, and a genuinely updated item creates a
   new version instead of a duplicate document.
4. `legal.knowledge.document._ingest_candidate()` (called by both the
   manual-import wizard and `legal.watch._run_ingestion()`) does the
   actual create-or-new-version work, wrapped in a savepoint so a storage
   failure can never leave an orphan document with zero versions.

## Document lifecycle

```
new ──┬──────────────► qualified ──► review ──► approved ──┬──► archived
      │                    │                                 └──► superseded ──► archived
      ├──────────────────► review
      └──────────────────► rejected ◄── review
                              │
                              └──► review / archived
```

`_ALLOWED_TRANSITIONS` (`models/legal_knowledge_document.py`) is the
single source of truth for which `write({"status": ...})` calls are
legal — enforced in `action_*()` methods, never left to the UI alone to
police. `archived` is terminal (no transition out); getting a document
back into circulation from there is a new import/version, not a status
change.

Orthogonal to `status`: `is_current` (only one version is current per
document — see `_compute_current_version_id`), `needs_review` (set by a
relevance rule or an AI classify result, never by direct AI override —
see `docs/ai-providers.md`), and `export_state`
(`not_requested/queued/exported/failed/blocked/stale` — see
`docs/ai-providers.md`'s export policy and `docs/operations.md`'s
reconciliation).

## Why an architecture doc separate from the README

The README's "Architecture in one paragraph" section stays the fast,
one-screen version for a first-time reader. This document is the version
those three code comments actually meant to point to — updated whenever
the model relationships or lifecycle actually change, not whenever the
README's marketing-facing summary gets reworded.
