# AI / export providers

# Providers IA / export

## Principle / Principe

The core module (`legal.ai.job`, `legal.knowledge.document`) never imports
a specific provider. It only knows `BaseAIProvider`
(`services/ai_provider_base.py`) and dispatches by `provider_type` through
`services/ai_provider_registry.py` — exactly the same pattern as
connectors (`connector_registry.py`). Two providers ship with this module:

Le module cœur (`legal.ai.job`, `legal.knowledge.document`) n'importe
jamais un provider concret. Il ne connaît que `BaseAIProvider`
(`services/ai_provider_base.py`) et dispatche par `provider_type` via
`services/ai_provider_registry.py` — exactement le même patron que les
connecteurs (`connector_registry.py`). Deux providers sont livrés avec ce
module :

- `webhook` (`generic_webhook_provider.py`): the simplest possible example
  — a single URL, one JSON body with an `"action"` discriminator. Use it
  as a template for a new provider (Qdrant, OpenWebUI, AnythingLLM, MCP...).
  <br>`webhook` (`generic_webhook_provider.py`) : l'exemple le plus
  simple possible — une seule URL, un corps JSON avec un discriminant
  `"action"`. À utiliser comme modèle pour un nouveau provider (Qdrant,
  OpenWebUI, AnythingLLM, MCP...).
- `ai_brain_http` (`ai_brain_provider.py`): implements the contract below.
  <br>`ai_brain_http` (`ai_brain_provider.py`) : implémente le contrat
  ci-dessous.
- `filesystem` (`filesystem_jsonl_provider.py`): no network at all — one
  JSON file per document (`<directory>/<reference>.json`), configured via
  `configuration_json: {"directory": "/path/to/export"}`. Writing always
  overwrites the file for that reference, so upsert is trivially
  idempotent without needing an `Idempotency-Key`. `classify()` raises
  (a flat file has nothing to classify against) — leave
  `enabled_for_classification` off for this provider_type. Lets you
  rebuild a local index (e.g. by globbing `*.json`) with zero external
  service, matching the "Odoo is the durable registry, any index is a
  reconstructible projection" principle end to end.
  <br>`filesystem` (`filesystem_jsonl_provider.py`) : aucun réseau du
  tout — un fichier JSON par document (`<directory>/<reference>.json`),
  configuré via `configuration_json: {"directory": "/path/to/export"}`.
  L'écriture écrase toujours le fichier pour cette référence, donc
  l'upsert est trivialement idempotent sans avoir besoin d'une
  `Idempotency-Key`. `classify()` lève une erreur (un fichier plat n'a
  rien contre quoi classifier) — laisser `enabled_for_classification`
  désactivé pour ce provider_type. Permet de reconstruire un index local
  (par ex. en globbant `*.json`) sans aucun service externe, appliquant
  de bout en bout le principe « Odoo est le registre durable, tout index
  est une projection reconstructible ».

**AI is never the source of truth.** `legal.knowledge.document` (status,
hash, dates, source) always wins. AI output only ever:
- sets `needs_review = True` on a classify result that asks for it — it
  never changes `status` directly;
- gets recorded in `legal.document.enrichment`, versioned by provider,
  prompt version and input hash, always kept separate from the source
  content it was computed from.

**L'IA n'est jamais la source de vérité.** `legal.knowledge.document`
(status, hash, dates, source) l'emporte toujours. Le résultat de l'IA ne
fait jamais que :
- positionner `needs_review = True` sur un résultat de classification qui
  le demande — il ne change jamais `status` directement ;
- être enregistré dans `legal.document.enrichment`, versionné par
  provider, version de prompt et hash d'entrée, toujours conservé séparé
  du contenu source à partir duquel il a été calculé.

A malformed classify response (fails `legal-enrichment-1.0` validation,
see `docs/legal-enrichment-schema-1.0.json` and
`services/enrichment_schema.py`) never silently mutates the document — the
job fails and a `state=failed` enrichment records why, for audit.

Une réponse de classification mal formée (échoue à la validation
`legal-enrichment-1.0`, voir `docs/legal-enrichment-schema-1.0.json` et
`services/enrichment_schema.py`) ne modifie jamais silencieusement le
document — le job échoue et un enrichment `state=failed` enregistre
pourquoi, pour l'audit.

## AI-Brain HTTP contract / Contrat HTTP AI-Brain

This contract is this project's own design — not a pre-existing external
API to reverse-engineer. Any server implementing it works with the
`ai_brain_http` provider. `base_url` is entirely admin-configured on
`legal.ai.provider`; nothing here is hardcoded.

Ce contrat est une conception propre à ce projet — pas une API externe
préexistante à rétro-ingénierer. Tout serveur qui l'implémente
fonctionne avec le provider `ai_brain_http`. `base_url` est entièrement
configuré par un admin sur `legal.ai.provider` ; rien ici n'est codé en
dur.

### Healthcheck / Contrôle de santé

```
GET {base_url}/api/v1/legal-knowledge/health
```

```json
{"status": "ok", "api_version": "1.0", "capabilities": ["classify", "upsert", "delete"]}
```

### Classify / Classification

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

Le corps de la réponse est validé par ce module contre
`legal-enrichment-1.0` avant d'être fait confiance — voir
`docs/legal-enrichment-schema-1.0.json`. Tout le reste (y compris une
réponse 2xx avec la mauvaise forme) fait échouer le job.

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

`Idempotency-Key` est le `content_hash` du document — un serveur
implémentant ce contrat devrait traiter un appel répété avec la même clé
comme un no-op, afin que relancer un job d'export après un incident
réseau n'écrive jamais deux fois.

### Delete / Suppression

```
DELETE {base_url}/api/v1/legal-knowledge/documents/{reference}
```

Rare in practice: prefer `status: archived`/`is_current: false` in your
own index over hard deletion, since Odoo/the storage backend remains the
durable record either way (see `docs/architecture.md`).

Rare en pratique : préférez `status: archived`/`is_current: false` dans
votre propre index à une suppression définitive, puisqu'Odoo/le backend
de stockage reste de toute façon l'enregistrement durable (voir
`docs/architecture.md`).

## Export policy (fail-closed) / Politique d'export (fail-closed)

`legal.ai.job._run_export()` re-checks this fresh every time the job runs
(not just once at approval time), via
`legal.knowledge.document._check_export_policy()`. Two layers:

`legal.ai.job._run_export()` revérifie ceci à chaque exécution du job
(pas une seule fois à l'approbation), via
`legal.knowledge.document._check_export_policy()`. Deux niveaux :

**Unconditional floor** (no `legal.export.policy` can loosen this):
`status == 'approved'`, `is_current == True`, `canonical_url` and
`content_hash` are set, and normalized text is non-empty.

**Plancher inconditionnel** (aucune `legal.export.policy` ne peut
l'assouplir) : `status == 'approved'`, `is_current == True`,
`canonical_url` et `content_hash` sont renseignés, et le texte normalisé
est non vide.

**Configurable refinement** — the most specific active
`legal.export.policy` matching the document's company/source/watch (source-
or watch-specific beats company-specific beats global; see
`legal.export.policy._resolve()`), or, with **no policy configured at
all**, the Phase 4 default (`min_trust_level = high`,
`require_review_cleared = False`, no score/length gate — this keeps
upgrading the module a no-op until an admin deliberately configures
something stricter or more lenient):

**Raffinement configurable** — la `legal.export.policy` active la plus
spécifique correspondant à la société/source/veille du document (une
politique spécifique à la source ou à la veille l'emporte sur celle de
la société, qui l'emporte sur le global ; voir
`legal.export.policy._resolve()`), ou, en l'**absence totale de
politique configurée**, le défaut de la Phase 4 (`min_trust_level =
high`, `require_review_cleared = False`, aucun filtre de score/longueur
— cela garde la mise à niveau du module comme un no-op tant qu'un admin
ne configure pas délibérément quelque chose de plus strict ou plus
souple) :

| Field / Champ | Effect / Effet |
|---|---|
| `min_trust_level` | `source_id.trust_level` must be at least this (`low < medium < high < primary`) <br>`source_id.trust_level` doit être au moins celui-ci (`low < medium < high < primary`) |
| `require_review_cleared` | if set, `needs_review` must be `False` <br>si activé, `needs_review` doit être `False` |
| `min_relevance_score` | `relevance_score` must be at least this <br>`relevance_score` doit être au moins celui-ci |
| `max_text_length` | normalized text must not exceed this (0 = unlimited) <br>le texte normalisé ne doit pas dépasser cette taille (0 = illimité) |

If any check fails, the job is cancelled (`state=cancelled`,
`document.export_state='blocked'`) **without ever calling the provider** —
no network call, no partial export. Configuration → **Export Policies**.

Si une vérification échoue, le job est annulé (`state=cancelled`,
`document.export_state='blocked'`) **sans jamais appeler le provider** —
aucun appel réseau, aucun export partiel. Configuration → **Politiques
d'export**.

## Secrets

`legal.ai.provider.secret_parameter_key` names an `ir.config_parameter` —
never the secret's value. Read priority
(`services/secrets_service.py`, shared with the Légifrance connector):

`legal.ai.provider.secret_parameter_key` nomme un `ir.config_parameter`
— jamais la valeur du secret. Ordre de lecture
(`services/secrets_service.py`, partagé avec le connecteur Légifrance) :

1. An environment variable derived from the key, e.g.
   `legal_knowledge_watch.ai_brain.token` → `LKW_AI_BRAIN_TOKEN`.
   <br>Une variable d'environnement dérivée de la clé, ex.
   `legal_knowledge_watch.ai_brain.token` → `LKW_AI_BRAIN_TOKEN`.
2. The `ir.config_parameter` itself (set manually via Settings >
   Technical > System Parameters — never committed).
   <br>Le `ir.config_parameter` lui-même (renseigné manuellement via
   Réglages > Technique > Paramètres système — jamais committé).

`verify_tls` defaults to `True`. Timeouts and bounded exponential-backoff
retry (429/5xx/network errors; other 4xx are never retried) are shared
across both providers via `services/http_retry.py`.

`verify_tls` vaut `True` par défaut. Les timeouts et le réessai avec
backoff exponentiel borné (erreurs 429/5xx/réseau ; les autres 4xx ne
sont jamais retentés) sont partagés entre les deux providers via
`services/http_retry.py`.

## Job lifecycle / Cycle de vie d'un job

`legal.ai.job.state`: `pending → running → done` (success) or
`running → retry → running → ... → failed` (transient failures, backoff
`2 × 2^(attempt-1)` minutes, capped at 5 attempts) or
`running → cancelled` (export blocked by policy — terminal, no retry,
since retrying won't change the policy outcome) or
`running → failed` directly (classify response fails schema validation —
also terminal, since a malformed response won't fix itself on retry).

`legal.ai.job.state` : `pending → running → done` (succès) ou
`running → retry → running → ... → failed` (échecs transitoires, backoff
`2 × 2^(attempt-1)` minutes, plafonné à 5 tentatives) ou
`running → cancelled` (export bloqué par la politique — terminal, pas de
nouvel essai, puisqu'un nouvel essai ne changera pas le résultat de la
politique) ou `running → failed` directement (la réponse de
classification échoue la validation de schéma — terminal aussi, puisqu'une
réponse mal formée ne se corrigera pas d'elle-même au prochain essai).

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

Les jobs sont créés, jamais traités de façon synchrone :
- `legal.knowledge.document.action_request_ai_classification()` (bouton
  manuel) met en file un job `classify` par provider avec
  `enabled_for_classification=True`.
- `action_approve()` met en file un job `export` par provider avec
  `enabled_for_export=True`, et positionne `export_state='queued'`
  immédiatement.
- Le cron `Legal Knowledge Watch: Process AI jobs` (10 min, petits lots)
  appelle `legal.ai.job._cron_process_pending_jobs()`, chaque job dans
  son propre verrou de ligne PostgreSQL (même patron auto-libéré que
  `legal.watch`, voir `docs/connectors.md`) et savepoint.

## Prompt templates / Modèles de prompt

`services/ai_prompts.py` — versioned by an explicit `prompt_version`
string stored on every enrichment, so editing a template here always
produces a new version rather than silently reinterpreting old results:

`services/ai_prompts.py` — versionné par une chaîne `prompt_version`
explicite stockée sur chaque enrichment, afin qu'éditer un modèle ici
produise toujours une nouvelle version plutôt que de réinterpréter
silencieusement d'anciens résultats :

- `legal_summary_classification_fr_v1`: the only one currently wired into
  an automatic job (`classify`). Produces `legal-enrichment-1.0` JSON.
  <br>`legal_summary_classification_fr_v1` : le seul actuellement câblé
  dans un job automatique (`classify`). Produit du JSON
  `legal-enrichment-1.0`.
- `legal_business_impact_fr_v1`: defined and importable, but not wired
  into an automatic job type in this phase (its output shape —
  `review_priority`/`control_questions`/... — is a different, ad hoc
  shape not covered by the strict `legal-enrichment-1.0` schema). A future
  phase adding a `job_type='impact'` should give it its own schema rather
  than reusing `legal-enrichment-1.0`.
  <br>`legal_business_impact_fr_v1` : défini et importable, mais pas
  câblé dans un type de job automatique à cette phase (sa forme de
  sortie — `review_priority`/`control_questions`/... — est une forme ad
  hoc différente, non couverte par le schéma strict
  `legal-enrichment-1.0`). Une phase future ajoutant un
  `job_type='impact'` devrait lui donner son propre schéma plutôt que de
  réutiliser `legal-enrichment-1.0`.

Both templates explicitly forbid personalized legal advice and require
the model to separate what the source text states from what is inferred
or uncertain.

Les deux modèles interdisent explicitement le conseil juridique
personnalisé et exigent du modèle qu'il sépare ce que le texte source
énonce de ce qui est déduit ou incertain.
