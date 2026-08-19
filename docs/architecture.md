# Architecture

This is the consolidated reference for how the pieces fit together — the
document behind three `see docs/architecture.md` pointers already left in
the code since Phase 0 (`models/legal_knowledge_document.py`,
`services/deduplication_service.py`, `docs/ai-providers.md`) that were
never actually resolved until now. For a specific layer's own detail, see
`docs/connectors.md` (ingestion), `docs/ai-providers.md` (AI/export),
`docs/oca-dms-integration.md` (storage), `docs/operations.md`
(reconciliation/retention/crons), `docs/security.md` (access/network).

Ce document consolide la façon dont les pièces s'assemblent — c'est le
document que trois pointeurs `see docs/architecture.md` laissés dans le
code depuis la Phase 0 (`models/legal_knowledge_document.py`,
`services/deduplication_service.py`, `docs/ai-providers.md`) attendaient
sans jamais être réellement résolus jusqu'à maintenant. Pour le détail
d'une couche précise, voir `docs/connectors.md` (ingestion),
`docs/ai-providers.md` (IA/export), `docs/oca-dms-integration.md`
(stockage), `docs/operations.md` (réconciliation/rétention/crons),
`docs/security.md` (accès/réseau).

## The source-of-truth principle / Le principe de la source de vérité

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

`legal.knowledge.document` est l'enregistrement métier : identité,
statut, workflow de revue, score de pertinence, tags. Il ne mélange
jamais le contenu source brut avec une analyse ultérieure
(`legal.document.enrichment`) et ne se lie jamais en dur à une technologie
de stockage. Le contenu lui-même vit dans des enregistrements
`legal.document.version` — des instantanés immuables, jamais modifiés ni
supprimés (seul leur *binaire* peut être purgé plus tard par la
rétention, voir `docs/operations.md`) — chacun pointant vers l'endroit
où il a réellement été stocké : un `ir.attachment` par défaut, ou un
`dms.file` si OCA DMS est installé et sélectionné (`storage_backend`,
`services/storage_service.py` + `services/storage_dms.py`). C'est ce qui
permet au backend de stockage de changer, ou à un document d'accumuler
20 versions sur plusieurs années, sans jamais perdre l'historique ni
nécessiter de migration.

The same principle extends outward: Odoo (plus whichever storage backend
a version chose) is the **durable registry**. Any AI-Brain/webhook/
filesystem export index is a **reconstructible projection** of it — see
`docs/ai-providers.md` and `docs/operations.md`'s "Reconciliation"
section for what that means operationally.

Le même principe s'étend vers l'extérieur : Odoo (plus le backend de
stockage choisi par chaque version) est le **registre durable**. Tout
index d'export AI-Brain/webhook/filesystem en est une **projection
reconstructible** — voir `docs/ai-providers.md` et la section
« Réconciliation » de `docs/operations.md` pour ce que cela signifie
concrètement.

## Data model at a glance / Le modèle de données en un coup d'œil

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

`legal.source` n'a **volontairement pas** de `company_id` — c'est une
liste référentielle partagée (un journal officiel existe indépendamment
de la société qui le surveille) ; c'est `legal.watch` et
`legal.knowledge.document` qui introduisent réellement le cloisonnement
par société. Voir `docs/security.md` pour la couverture complète des
règles `ir.rule` multi-société sur tous les autres modèles.

## Ingestion pipeline / Pipeline d'ingestion

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

1. Un **connecteur** (`docs/connectors.md`) transforme une source
   distante en objets `CandidateItem`. Il n'écrit jamais directement dans
   Odoo.
2. Les **règles de pertinence** (`legal.watch.rule`) s'exécutent en
   premier, pour chaque candidat : `exclude` l'emporte toujours,
   `include` est un filtrage optionnel (opt-in), `score`/`tag`/
   `requires_review` sont additifs. Un candidat filtré n'atteint jamais
   la déduplication (`filtered_count`, distinct de `duplicate_count`).
3. La **déduplication** (`services/deduplication_service.py`) vérifie,
   dans cet ordre fixe : `(source_id, external_id)` quand `external_id`
   est connu, puis `canonical_url` au sein de la même source, puis
   `content_hash` globalement (une republication identique ailleurs est
   marquée comme doublon du *premier* document ayant eu ce contenu, pas
   comme un second document). Cet ordre — les signaux d'identité avant
   le contenu — est ce qui rend une veille idempotente en cas de
   relance : le même élément récupéré deux fois ne crée jamais de bruit,
   et un élément réellement mis à jour crée une nouvelle version au lieu
   d'un document en double.
4. `legal.knowledge.document._ingest_candidate()` (appelée à la fois par
   l'assistant d'import manuel et par `legal.watch._run_ingestion()`)
   effectue le travail réel de création ou de nouvelle version, entouré
   d'un savepoint pour qu'un échec de stockage ne puisse jamais laisser
   un document orphelin sans aucune version.

## Document lifecycle / Cycle de vie d'un document

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

`_ALLOWED_TRANSITIONS` (`models/legal_knowledge_document.py`) est la
seule source de vérité pour savoir quels appels `write({"status": ...})`
sont autorisés — la règle est appliquée dans les méthodes `action_*()`,
jamais laissée à la seule discipline de l'interface. `archived` est un
état terminal (aucune transition n'en sort) ; faire revenir un document
en circulation depuis cet état passe par un nouvel import/une nouvelle
version, pas par un changement de statut.

Orthogonal to `status`: `is_current` (only one version is current per
document — see `_compute_current_version_id`), `needs_review` (set by a
relevance rule or an AI classify result, never by direct AI override —
see `docs/ai-providers.md`), and `export_state`
(`not_requested/queued/exported/failed/blocked/stale` — see
`docs/ai-providers.md`'s export policy and `docs/operations.md`'s
reconciliation).

Orthogonaux au `status` : `is_current` (une seule version est courante
par document — voir `_compute_current_version_id`), `needs_review`
(positionné par une règle de pertinence ou un résultat de classification
IA, jamais par une IA qui outrepasserait directement une décision — voir
`docs/ai-providers.md`), et `export_state`
(`not_requested/queued/exported/failed/blocked/stale` — voir la politique
d'export de `docs/ai-providers.md` et la réconciliation de
`docs/operations.md`).

## Why an architecture doc separate from the README / Pourquoi un document d'architecture séparé du README

The README's "Architecture in one paragraph" section stays the fast,
one-screen version for a first-time reader. This document is the version
those three code comments actually meant to point to — updated whenever
the model relationships or lifecycle actually change, not whenever the
README's marketing-facing summary gets reworded.

La section « Architecture in one paragraph » du README reste la version
rapide, tenant sur un écran, pour un premier lecteur. Ce document est
celui que les trois commentaires de code visaient réellement — mis à
jour chaque fois que les relations entre modèles ou le cycle de vie
changent vraiment, pas chaque fois que le résumé grand public du README
est reformulé.
