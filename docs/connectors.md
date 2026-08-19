# Connectors

# Connecteurs

## Contract / Contrat

A connector never writes to Odoo. It only turns a remote source into a list
of `CandidateItem` objects (`legal_knowledge_watch/services/base_connector.py`).
All persistence — deduplication, versioning, storage — happens in
`legal.knowledge.document._ingest_candidate()`, called by the orchestrator
(`legal.watch._run_ingestion()`).

Un connecteur n'écrit jamais dans Odoo. Il transforme uniquement une
source distante en une liste d'objets `CandidateItem`
(`legal_knowledge_watch/services/base_connector.py`). Toute la
persistance — déduplication, versionnage, stockage — se fait dans
`legal.knowledge.document._ingest_candidate()`, appelée par
l'orchestrateur (`legal.watch._run_ingestion()`).

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

Champs de `CandidateItem` : `source_url`, `canonical_url`, `title`,
`external_id`, `raw_content`, `plain_text`, `published_at`, `updated_at`,
`content_type`, `language`, `source_metadata` (dict).

`FetchResult` fields: `items` (list of `CandidateItem`), `next_cursor` (an
opaque string persisted on `legal.watch.last_cursor`, passed back on the
next call), `diagnostics` (dict; connectors should set
`diagnostics["item_errors"]` — a list of `{"title", "error"}` — for entries
that failed to parse without aborting the whole fetch).

Champs de `FetchResult` : `items` (liste de `CandidateItem`),
`next_cursor` (une chaîne opaque persistée sur `legal.watch.last_cursor`,
renvoyée à l'appel suivant), `diagnostics` (dict ; les connecteurs
doivent renseigner `diagnostics["item_errors"]` — une liste de
`{"title", "error"}` — pour les entrées qui ont échoué à l'analyse, sans
faire échouer toute la récupération).

To add a connector: implement `BaseConnector`, decorate the class with
`@register_connector` (from `services/connector_registry.py`), and add its
code to `legal.watch.connector_code`'s selection.

Pour ajouter un connecteur : implémenter `BaseConnector`, décorer la
classe avec `@register_connector` (depuis `services/connector_registry.py`),
et ajouter son code à la sélection `legal.watch.connector_code`.

## RSS/Atom connector / Connecteur RSS/Atom

Code: `rss`. Configuration lives in `legal.watch.configuration_json` as a
JSON object:

Code : `rss`. La configuration vit dans `legal.watch.configuration_json`
sous forme d'objet JSON :

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

Behavior: / Comportement :

- `feed_url` is required and must be `http(s)`. If `allowed_domains` is set,
  `feed_url`'s host must be in it (validated before any network call).
  <br>`feed_url` est obligatoire et doit être en `http(s)`. Si
  `allowed_domains` est renseigné, l'hôte de `feed_url` doit y figurer
  (vérifié avant tout appel réseau).
- `fetch_linked_content` (default `false`): when `true`, the full article
  page is fetched **only** if its own host is also in `allowed_domains`.
  Never scrapes a linked page by default — the feed's own summary/title is
  used as the normalized text instead, and the link itself is always kept
  as `source_url` regardless.
  <br>`fetch_linked_content` (par défaut `false`) : si `true`, la page
  complète de l'article n'est récupérée **que** si son propre hôte figure
  aussi dans `allowed_domains`. Aucun scraping d'une page liée par défaut
  — le résumé/titre du flux sert de texte normalisé à la place, et le
  lien lui-même reste toujours conservé comme `source_url`.
- Conditional GET: `ETag`/`Last-Modified` from the previous response are
  sent back as `If-None-Match`/`If-Modified-Since` on the next run. A `304`
  response returns an empty `FetchResult` without touching `last_cursor`.
  <br>GET conditionnel : l'`ETag`/`Last-Modified` de la réponse précédente
  sont renvoyés en `If-None-Match`/`If-Modified-Since` à la prochaine
  exécution. Une réponse `304` renvoie un `FetchResult` vide sans toucher
  à `last_cursor`.
- Transient failures (timeout, connection error, HTTP 429/5xx) are retried
  up to 3 times with a bounded exponential backoff (1s, 2s). A `4xx` other
  than 429 is never retried. A response over `max_response_bytes` aborts
  the fetch for that URL.
  <br>Les échecs transitoires (timeout, erreur de connexion, HTTP
  429/5xx) sont retentés jusqu'à 3 fois avec un backoff exponentiel borné
  (1s, 2s). Un `4xx` autre que 429 n'est jamais retenté. Une réponse
  dépassant `max_response_bytes` interrompt la récupération pour cette
  URL.
- A malformed entry (e.g. missing `<link>`) is skipped and reported in
  `diagnostics["item_errors"]`; it does not abort the rest of the feed.
  <br>Une entrée mal formée (ex. `<link>` manquant) est ignorée et
  signalée dans `diagnostics["item_errors"]` ; elle n'interrompt pas le
  reste du flux.

## Relevance rules / Règles de pertinence

`legal.watch.rule` (`services/relevance_service.py`) are evaluated **before**
ingestion, once per candidate, in this phase without any AI involvement:

Les `legal.watch.rule` (`services/relevance_service.py`) sont évaluées
**avant** l'ingestion, une fois par candidat, sans aucune intervention de
l'IA à ce stade :

| Field / Champ | Values / Valeurs |
|---|---|
| `rule_type` | `keyword`, `regex`, `source_field` (documentation-only categorisation / catégorisation documentaire seulement) |
| `target_field` | `title`, `plain_text`, `authority`, `source_url`, `canonical_url` |
| `operator` | `contains`, `equals`, `matches` (regex), `in`, `not_in` (comma-separated `value` / `value` séparé par des virgules) |
| `effect` | `include`, `exclude`, `score`, `tag`, `requires_review` |

Semantics: / Sémantique :

- `exclude` always wins: if any `exclude` rule matches, the candidate is
  filtered out before ever reaching deduplication (counted as
  `filtered_count` on the run, distinct from `duplicate_count`).
  <br>`exclude` l'emporte toujours : si une règle `exclude` correspond, le
  candidat est filtré avant même d'atteindre la déduplication (compté
  dans `filtered_count` sur l'exécution, distinct de `duplicate_count`).
- `include` is opt-in gating: if at least one `include` rule exists on the
  watch, the candidate is excluded unless at least one `include` rule
  matches. With no `include` rules at all, nothing is excluded on that
  basis.
  <br>`include` est un filtrage optionnel (opt-in) : si au moins une
  règle `include` existe sur la veille, le candidat est exclu sauf si au
  moins une règle `include` correspond. Sans aucune règle `include`, rien
  n'est exclu sur cette base.
- `score` rules accumulate into `legal.knowledge.document.relevance_score`.
  <br>Les règles `score` s'accumulent dans
  `legal.knowledge.document.relevance_score`.
- `tag` rules add `legal.tag` records to the document.
  <br>Les règles `tag` ajoutent des enregistrements `legal.tag` au
  document.
- `requires_review` sets `needs_review = True` on the document — it does
  **not** change `status` on its own; auto-approval thresholds are a later
  phase.
  <br>`requires_review` positionne `needs_review = True` sur le document
  — elle ne change **pas** `status` à elle seule ; les seuils
  d'auto-approbation sont une phase ultérieure.

Triggered rule names are posted to the document's chatter for auditability.

Les noms des règles déclenchées sont postés dans le chatter du document
pour la traçabilité.

## Concurrency and scheduling / Concurrence et planification

`legal.watch._try_lock_for_run()` takes a PostgreSQL row lock
(`SELECT ... FOR UPDATE NOWAIT`) for the duration of the transaction. If
another run already holds it, the new run is recorded as `state=skipped`
instead of blocking or erroring. Locks are released automatically by
PostgreSQL when the holding transaction ends — there is no stale-lock flag
to reset after a crash.

`legal.watch._try_lock_for_run()` prend un verrou de ligne PostgreSQL
(`SELECT ... FOR UPDATE NOWAIT`) pour la durée de la transaction. Si une
autre exécution le détient déjà, la nouvelle exécution est enregistrée
avec `state=skipped` au lieu de bloquer ou d'échouer. Les verrous sont
libérés automatiquement par PostgreSQL à la fin de la transaction qui les
détient — il n'y a aucun indicateur de verrou périmé à réinitialiser
après un crash.

`_cron_fetch_due_watches()` (cron `Legal Knowledge Watch: Fetch due
watches`, every 15 minutes) selects active watches with
`schedule_enabled=True` and a `connector_code` other than `manual`, and
runs each one whose `last_run_at + interval_minutes` has elapsed.

`_cron_fetch_due_watches()` (cron `Legal Knowledge Watch: Fetch due
watches`, toutes les 15 minutes) sélectionne les veilles actives avec
`schedule_enabled=True` et un `connector_code` autre que `manual`, et
exécute chacune dont `last_run_at + interval_minutes` est dépassé.
