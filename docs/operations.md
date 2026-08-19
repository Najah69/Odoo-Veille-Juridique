# Operations

# Exploitation

## Crons

| Cron | Cadence | Role / Rôle |
|---|---:|---|
| `Legal Knowledge Watch: Fetch due watches` | 15 min | Runs `legal.watch._cron_fetch_due_watches()`, which selects due, schedule-enabled, non-manual watches and calls `_run_ingestion(trigger="cron")` on each. <br>Exécute `legal.watch._cron_fetch_due_watches()`, qui sélectionne les veilles échues, planifiées et non manuelles, et appelle `_run_ingestion(trigger="cron")` sur chacune. |
| `Legal Knowledge Watch: Process AI jobs` | 10 min | Runs `legal.ai.job._cron_process_pending_jobs()` — see `docs/ai-providers.md`. <br>Exécute `legal.ai.job._cron_process_pending_jobs()` — voir `docs/ai-providers.md`. |
| `Legal Knowledge Watch: Reconcile` | daily / quotidien | Runs `legal.knowledge.document._cron_reconcile_exports()` — see "Reconciliation" below. Active by default; purely corrective, never deletes anything. <br>Exécute `legal.knowledge.document._cron_reconcile_exports()` — voir « Réconciliation » plus bas. Actif par défaut ; purement correctif, ne supprime jamais rien. |
| `Legal Knowledge Watch: Apply Retention (dry run)` | weekly / hebdomadaire | Runs `_cron_apply_retention(dry_run=True)` — **disabled by default**. Enabling it only ever logs what would happen; a real run requires the **Apply Retention** wizard (Configuration menu) or a manual `dry_run=False` call. See "Retention" below. <br>Exécute `_cron_apply_retention(dry_run=True)` — **désactivé par défaut**. L'activer ne fait que journaliser ce qui se produirait ; une exécution réelle nécessite l'assistant **Appliquer la rétention** (menu Configuration) ou un appel manuel `dry_run=False`. Voir « Rétention » plus bas. |

In this Odoo 18 build, `ir.cron` no longer carries `model_id`/`state`/`code`
directly: it delegates to an `ir.actions.server` record via
`ir_actions_server_id` (see `data/ir_cron.xml`). Do not write a cron record
in the older single-record style — it will not install.

Dans cette version d'Odoo 18, `ir.cron` ne porte plus directement
`model_id`/`state`/`code` : il délègue à un enregistrement
`ir.actions.server` via `ir_actions_server_id` (voir `data/ir_cron.xml`).
N'écrivez pas un enregistrement cron dans l'ancien style à un seul
enregistrement — il ne s'installera pas.

## Diagnosing a run / Diagnostiquer une exécution

Every attempt (manual or cron) creates a `legal.ingestion.run` record with:

Chaque tentative (manuelle ou cron) crée un enregistrement
`legal.ingestion.run` avec :

- `state`: `running` (transient), `success`, `partial`, `failed`, `skipped`.
  <br>`state` : `running` (transitoire), `success`, `partial`, `failed`,
  `skipped`.
- Counters: `fetched_count`, `created_count`, `updated_count`
  (new versions of an existing document), `duplicate_count` (identical
  content re-submitted), `filtered_count` (excluded by a relevance rule
  before ever reaching deduplication), `error_count`.
  <br>Compteurs : `fetched_count`, `created_count`, `updated_count`
  (nouvelles versions d'un document existant), `duplicate_count` (contenu
  identique resoumis), `filtered_count` (exclu par une règle de
  pertinence avant même d'atteindre la déduplication), `error_count`.
- `log_excerpt`: non-sensitive diagnostic text (item-level error messages).
  Never contains secrets, tokens or full document content.
  <br>`log_excerpt` : texte de diagnostic non sensible (messages
  d'erreur au niveau de l'élément). Ne contient jamais de secrets, de
  jetons ni le contenu intégral d'un document.

A `skipped` run means another run for the same watch was already in
progress when this one tried to start (see the concurrency note in
`docs/connectors.md`) — it is not an error and needs no action.

Une exécution `skipped` signifie qu'une autre exécution pour la même
veille était déjà en cours quand celle-ci a tenté de démarrer (voir la
note sur la concurrence dans `docs/connectors.md`) — ce n'est pas une
erreur et ne nécessite aucune action.

A `failed` run means either the connector configuration was invalid, or the
fetch itself failed (network/HTTP error) before any item could be
processed — check `log_excerpt` first.

Une exécution `failed` signifie soit que la configuration du connecteur
était invalide, soit que la récupération elle-même a échoué (erreur
réseau/HTTP) avant qu'aucun élément n'ait pu être traité — vérifiez
d'abord `log_excerpt`.

A `partial` run means at least one item failed after the fetch succeeded;
`created_count`/`updated_count`/`duplicate_count`/`filtered_count` still
reflect what *did* succeed. Re-running the watch is always safe: ingestion
is idempotent (see the deduplication order in `docs/connectors.md`).

Une exécution `partial` signifie qu'au moins un élément a échoué après le
succès de la récupération ; `created_count`/`updated_count`/
`duplicate_count`/`filtered_count` reflètent quand même ce qui *a*
réussi. Relancer la veille est toujours sûr : l'ingestion est idempotente
(voir l'ordre de déduplication dans `docs/connectors.md`).

## Manual controls / Contrôles manuels

On a `legal.watch` with a non-`manual` connector:

Sur une `legal.watch` avec un connecteur autre que `manual` :

- **Test Connection**: validates `configuration_json` (and, for RSS, the
  `allowed_domains` gate) without making a network call for anything beyond
  what `validate_configuration()` needs — no documents are created.
  <br>**Tester la connexion** : valide `configuration_json` (et, pour
  RSS, le filtre `allowed_domains`) sans faire d'appel réseau au-delà de
  ce dont `validate_configuration()` a besoin — aucun document n'est créé.
- **Run Now**: runs `_run_ingestion(trigger="manual")` immediately, ignoring
  `schedule_enabled`/`interval_minutes` (those only gate the cron), and
  shows a notification with the resulting counters.
  <br>**Exécuter maintenant** : lance `_run_ingestion(trigger="manual")`
  immédiatement, en ignorant `schedule_enabled`/`interval_minutes`
  (qui ne contrôlent que le cron), et affiche une notification avec les
  compteurs résultants.

## Adding a new RSS watch — minimal example / Ajouter une veille RSS — exemple minimal

1. Configuration → Sources: create a `legal.source` if none fits yet.
   <br>Configuration → Sources : créer une `legal.source` si aucune ne
   convient déjà.
2. Watches → New: set `connector_code = rss`, and
   `configuration_json = {"feed_url": "https://example.gouv.fr/actualites.rss"}`.
   <br>Veilles → Nouveau : positionner `connector_code = rss`, et
   `configuration_json = {"feed_url": "https://example.gouv.fr/actualites.rss"}`.
3. **Test Connection**, then **Run Now** once to verify manually before
   enabling `schedule_enabled`.
   <br>**Tester la connexion**, puis **Exécuter maintenant** une fois
   pour vérifier manuellement avant d'activer `schedule_enabled`.
4. Add relevance rules under the "Relevance Rules" tab if you want automatic
   scoring/tagging/filtering; without any rule, every fetched item is kept
   as `status=new` with `relevance_score=0`.
   <br>Ajouter des règles de pertinence sous l'onglet « Règles de
   pertinence » pour un scoring/étiquetage/filtrage automatique ; sans
   aucune règle, chaque élément récupéré est conservé avec
   `status=new` et `relevance_score=0`.

## Reconciliation / Réconciliation

Odoo/DMS is the durable registry; any export index (AI-Brain, a webhook
receiver, the filesystem/JSONL provider) is a derived, reconstructible
projection of it. `_cron_reconcile_exports()` detects and repairs drift
between the two — it never deletes local history, only (re)queues jobs or
flags state:

Odoo/DMS est le registre durable ; tout index d'export (AI-Brain, un
récepteur webhook, le provider filesystem/JSONL) en est une projection
dérivée et reconstructible. `_cron_reconcile_exports()` détecte et
répare les écarts entre les deux — il ne supprime jamais l'historique
local, il ne fait que (re)mettre des jobs en file ou marquer un état :

- A document that is no longer current (`is_current=False`) but is still
  `export_state in (exported, queued)` gets flagged `stale` and a
  `delete_export` job is queued for every export-enabled provider (skipped
  if one is already pending, so re-running reconciliation is idempotent).
  <br>Un document qui n'est plus courant (`is_current=False`) mais reste
  `export_state in (exported, queued)` est marqué `stale` et un job
  `delete_export` est mis en file pour chaque provider activé pour
  l'export (ignoré si un job est déjà en attente, ce qui rend la
  réconciliation idempotente en cas de relance).
- An approved, current document sitting in `export_state in (not_requested,
  stale, failed)` that would actually pass `_check_export_policy()` gets a
  fresh `export` job queued.
  <br>Un document approuvé et courant, dont `export_state in
  (not_requested, stale, failed)` et qui passerait réellement
  `_check_export_policy()`, se voit mettre en file un nouveau job
  `export`.
- A `legal.ai.job` stuck in `state=running` for over an hour (a crash
  during processing — the PostgreSQL row lock itself is released
  automatically, but the job's own state field isn't) is reset to `retry`.
  <br>Un `legal.ai.job` bloqué en `state=running` depuis plus d'une heure
  (un crash pendant le traitement — le verrou de ligne PostgreSQL
  lui-même est libéré automatiquement, mais le champ state du job ne
  l'est pas) est réinitialisé à `retry`.
- A `legal.ingestion.run` stuck in `state=running` for over two hours is
  marked `failed` (not retried automatically — the watch's own next
  scheduled/manual run creates a fresh, independent run).
  <br>Une `legal.ingestion.run` bloquée en `state=running` depuis plus de
  deux heures est marquée `failed` (pas de nouvel essai automatique — la
  prochaine exécution planifiée/manuelle de la veille crée une nouvelle
  exécution indépendante).

## Retention / Rétention

Deliberately conservative, configured via `legal.retention.policy`
(company/source → day thresholds; a policy with `0` in a field disables
that half of retention entirely, and with **no policy configured at all,
retention does nothing**):

Délibérément conservatrice, configurée via `legal.retention.policy`
(société/source → seuils en jours ; une politique avec `0` dans un champ
désactive entièrement cette moitié de la rétention, et **sans aucune
politique configurée, la rétention ne fait rien**) :

1. **Archive**: a `rejected` document untouched (`last_checked_at`) for
   longer than `archive_rejected_after_days` is archived — a normal,
   reversible status change via `action_archive_document()`, which also
   stamps `archived_at`.
   <br>**Archivage** : un document `rejected` inchangé (`last_checked_at`)
   depuis plus longtemps que `archive_rejected_after_days` est archivé —
   un changement de statut normal et réversible via
   `action_archive_document()`, qui horodate aussi `archived_at`.
2. **Purge** (only after archiving, and only after a *separate* grace
   period `delete_binary_after_archived_days` counted from `archived_at`):
   removes the stored binary content of **non-current (superseded)
   versions only** on an already-archived document. The current version's
   content and every version/document metadata row (hash, dates,
   provenance) are never touched by retention, under any configuration.
   <br>**Purge** (seulement après archivage, et seulement après une
   période de grâce *séparée* `delete_binary_after_archived_days` comptée
   depuis `archived_at`) : supprime le contenu binaire stocké des
   **versions non courantes (remplacées) uniquement** sur un document
   déjà archivé. Le contenu de la version courante et chaque ligne de
   métadonnées de version/document (hash, dates, provenance) ne sont
   jamais touchés par la rétention, quelle que soit la configuration.

Both steps run through `_cron_apply_retention(dry_run=...)`, which returns
a report (`{"archived": [...], "purged_versions": [...]}`) logged via
`_logger.info` regardless of `dry_run`. To actually apply retention:
Configuration → **Apply Retention**, uncheck **Dry Run**, click **Run**.
The scheduled cron itself is disabled by default and, even if enabled,
only ever runs with `dry_run=True` — a real run is always a deliberate,
one-off action, never something a forgotten cron toggle can trigger.

Les deux étapes passent par `_cron_apply_retention(dry_run=...)`, qui
retourne un rapport (`{"archived": [...], "purged_versions": [...]}`)
journalisé via `_logger.info` quel que soit `dry_run`. Pour appliquer
réellement la rétention : Configuration → **Appliquer la rétention**,
décocher **Dry Run**, cliquer sur **Exécuter**. Le cron planifié
lui-même est désactivé par défaut et, même activé, ne s'exécute jamais
qu'avec `dry_run=True` — une exécution réelle est toujours une action
délibérée et ponctuelle, jamais quelque chose qu'un interrupteur de cron
oublié pourrait déclencher.

## Release checklist / Checklist de release

Before tagging a release: / Avant de taguer une release :

1. **Tests**: `odoo --test-enable --stop-after-init -i legal_knowledge_watch
   -d <throwaway_test_db>` passes fully, on a real Odoo 18 instance (not
   just read-through). The full suite must stay network-free — see
   `CONTRIBUTING.md`.
   <br>**Tests** : `odoo --test-enable --stop-after-init -i
   legal_knowledge_watch -d <throwaway_test_db>` passe intégralement, sur
   une vraie instance Odoo 18 (pas juste une relecture). La suite
   complète doit rester hors réseau — voir `CONTRIBUTING.md`.
2. **Secrets scan**: `git log -p` across the full history plus a
   working-tree grep for credential-shaped strings (API keys, bearer
   tokens, `client_secret=`, private-key headers). Any hit blocks the
   release.
   <br>**Recherche de secrets** : `git log -p` sur tout l'historique plus
   un grep de l'arbre de travail pour des chaînes ayant la forme
   d'identifiants (clés API, jetons bearer, `client_secret=`, en-têtes
   de clé privée). Toute occurrence bloque la release.
3. **`docs/security.md` is current**: any access-control, secrets, or
   outbound-network change since the last release is reflected there, not
   just in the code.
   <br>**`docs/security.md` est à jour** : tout changement de contrôle
   d'accès, de secrets, ou de réseau sortant depuis la dernière release
   y est reflété, pas seulement dans le code.
4. **`CHANGELOG.md`** has an entry for the release, and
   `__manifest__.py`'s `version` matches it.
   <br>**`CHANGELOG.md`** a une entrée pour la release, et la `version`
   de `__manifest__.py` lui correspond.
5. **Manifest sanity**: `external_dependencies` still lists every non-core
   Python package actually imported at module load time (`requests`,
   `feedparser`, `bs4`); OCA DMS is still absent from `depends` (it must
   stay optional — see `docs/oca-dms-integration.md`).
   <br>**Cohérence du manifest** : `external_dependencies` liste encore
   chaque package Python non-core réellement importé au chargement du
   module (`requests`, `feedparser`, `bs4`) ; OCA DMS est toujours absent
   de `depends` (il doit rester optionnel — voir
   `docs/oca-dms-integration.md`).
6. **Deploy**: copy `legal_knowledge_watch/` to the target addons path,
   `pip install` the packages from `external_dependencies` (plus `PyPDF2`
   if PDF text extraction is wanted), update the apps list, install/
   upgrade the module. No database migration script exists yet — this is
   a fresh-install-or-upgrade-in-place module with no destructive schema
   changes across phases so far.
   <br>**Déploiement** : copier `legal_knowledge_watch/` vers le chemin
   d'addons cible, `pip install` les packages d'`external_dependencies`
   (plus `PyPDF2` si l'extraction de texte PDF est souhaitée), mettre à
   jour la liste des apps, installer/mettre à niveau le module. Aucun
   script de migration de base de données n'existe encore — c'est un
   module d'install neuve ou de mise à niveau sur place, sans changement
   de schéma destructif sur les phases jusqu'ici.
7. **Rollback**: uninstalling the module removes its own models/data but
   never touches `ir.attachment`/`dms.file` records it created (Odoo does
   not cascade-delete attachments on module uninstall) — source content
   already collected is not lost even if the module itself is removed. To
   roll back to a previous *version* of the module instead of uninstalling
   it, deploy the previous version's code and upgrade in place; no phase so
   far has shipped a backward-incompatible model change that would block
   this.
   <br>**Retour arrière** : désinstaller le module retire ses propres
   modèles/données mais ne touche jamais aux `ir.attachment`/`dms.file`
   qu'il a créés (Odoo ne supprime pas les pièces jointes en cascade à la
   désinstallation) — le contenu source déjà collecté n'est pas perdu
   même si le module lui-même est retiré. Pour revenir à une *version*
   antérieure du module plutôt que de le désinstaller, déployer le code
   de la version antérieure et mettre à niveau sur place ; aucune phase
   jusqu'ici n'a livré de changement de modèle rétro-incompatible qui
   bloquerait cela.
8. **Go/no-go**: all of the above pass, and every P0/P1 finding in
   `docs/security.md` for the version being released is fixed (P2 findings
   may ship as documented, deliberate residual risk).
   <br>**Go/no-go** : tout ce qui précède passe, et chaque constat P0/P1
   de `docs/security.md` pour la version publiée est corrigé (les
   constats P2 peuvent être livrés en tant que risque résiduel documenté
   et délibéré).
