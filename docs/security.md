# Security

# Sécurité

This document is the release-candidate security audit for
`legal_knowledge_watch` (Phase 6) and the reference for how the module
handles access control, secrets, outbound network calls and deletion. It
also honestly lists what is *not* covered, rather than implying more
coverage than exists.

Ce document est l'audit sécurité de la release candidate pour
`legal_knowledge_watch` (Phase 6) et la référence sur la façon dont le
module gère le contrôle d'accès, les secrets, les appels réseau sortants
et la suppression. Il liste aussi honnêtement ce qui n'est *pas* couvert,
plutôt que de laisser croire à une couverture plus large qu'elle ne l'est.

## Access control / Contrôle d'accès

Four groups, each implying the previous (`User ⊂ Reviewer ⊂ Manager ⊂
Administrator`) — see `security/security.xml`. `security/ir.model.access.csv`
grants per-model CRUD per group; every model with a `company_id` (direct or
related) also has a multi-company `ir.rule` in `security/security.xml`
restricting rows to the current user's allowed companies.

Quatre groupes, chacun impliquant le précédent (`User ⊂ Reviewer ⊂
Manager ⊂ Administrator`) — voir `security/security.xml`.
`security/ir.model.access.csv` accorde le CRUD par modèle et par groupe ;
tout modèle avec un `company_id` (direct ou related) a aussi une
`ir.rule` multi-société dans `security/security.xml` restreignant les
lignes aux sociétés autorisées de l'utilisateur courant.

Two write paths are deliberately narrower than "own the record you can
read": / Deux chemins d'écriture sont délibérément plus étroits que « on
possède ce qu'on peut lire » :

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
  <br>**`legal.document.version`** : `User`/`Reviewer` ont
  `perm_write=0, perm_create=0` (lecture seule). Les versions ne doivent
  être créées que d'une seule façon — via
  `legal.knowledge.document.create_or_update_from_candidate()` /
  `_create_new_version()` (models/legal_knowledge_document.py), le point
  d'entrée unique atteint par l'assistant d'import manuel et chaque
  connecteur, qui calcule le hash de contenu, exécute la déduplication et
  maintient l'historique cohérent. Avant cette phase, `User` avait
  `perm_write=1, perm_create=1` ici pour que l'assistant fonctionne — ce
  qui permettait aussi à un compte de niveau `User` d'appeler
  `env["legal.document.version"].create(...)` directement via ORM/RPC et
  de forger une version (contenu arbitraire, `is_current`, hash) sans
  aucune de ces règles appliquées. Corrigé en resserrant l'ACL et en
  faisant appeler `.sudo()` par `create_or_update_from_candidate()` /
  `_create_new_version()` uniquement sur les appels create/write de
  `legal.document.version` eux-mêmes — l'assistant et les connecteurs
  continuent de fonctionner sans changement, la forgerie directe non.
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
  <br>**`ir.attachment` via `services/storage_service.py`** : écrire ce
  test de régression a révélé un second manquement, plus ancien et
  préexistant, dans la même zone — `AttachmentStorageBackend.store()`
  appelle `ir.attachment.create()` sur le document, ce qui exige côté
  cœur d'Odoo un accès en *écriture* sur l'enregistrement cible ;
  `User`/`Reviewer` n'ont jamais eu `perm_write` sur
  `legal.knowledge.document` (par conception — voir le tableau ACL),
  donc l'assistant d'import manuel était silencieusement cassé pour tout
  rôle en dessous de `Reviewer` depuis la Phase 0, jamais détecté car
  aucun test antérieur ne l'exerçait sous un utilisateur restreint.
  Corrigé de la même façon : `.sudo()` sur cet appel
  `ir.attachment.create()` (reprenant le schéma déjà utilisé par le
  backend DMS de `storage_dms.py`), plus `.sudo()` sur les deux écritures
  `legal.knowledge.document`/`legal.document.version` dans
  `_create_new_version()` qui avaient le même problème pour un *second*
  import d'un contenu déjà connu. Voir
  `test_manual_import_wizard.py::test_plain_user_can_import_but_not_create_version_directly`
  pour le test de régression prouvant les deux points.
- **`legal.knowledge.document.unlink`**: restricted to `Administrator` via
  the model's own `_check_company_domain`-independent ACL row; every other
  role uses **Archive** instead, which preserves chatter and version
  history. (Unchanged from earlier phases — noted here for completeness.)
  <br>**`legal.knowledge.document.unlink`** : restreint à `Administrator`
  via la propre ligne ACL du modèle ; tout autre rôle utilise **Archiver**
  à la place, ce qui préserve le chatter et l'historique des versions.
  (Inchangé depuis les phases précédentes — noté ici pour être complet.)

### Multi-company coverage (P0 finding, fixed this phase) / Couverture multi-société (constat P0, corrigé cette phase)

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

`legal.ai.job` et `legal.document.enrichment` portent un `company_id`
related à leur document mais, avant cette phase, n'avaient aucune
`ir.rule` pour l'appliquer — un vrai manquement d'exposition
inter-société, et le plus sensible des deux :
`legal.document.enrichment.output_json` peut contenir un résumé/extrait
du document d'une autre société. `legal.dms.directory.route`,
`legal.export.policy` et `legal.retention.policy` avaient le même
manquement (de la configuration plutôt que du contenu, mais une fuite
inter-société de routage/politique interne quand même). Corrigé en
ajoutant le champ `company_id` manquant (les deux modèles de contenu) et
les cinq enregistrements `ir.rule` — voir `security/security.xml`. Tests
de régression :
`tests/test_multicompany.py::test_ai_job_isolated_by_document_company` et
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

`legal.ai.job.company_id`/`legal.document.enrichment.company_id` sont
`related` mais délibérément **pas** `store=True` — une première tentative
les avait stockés tous les deux et cassait le contrôle de blocage de
`_reconcile_stuck_jobs()` basé sur write_date (un champ related stocké
peut être flush paresseusement par l'ORM juste avant un `search()` sans
rapport, ce qui réécrit silencieusement write_date) ; détecté par
`test_stuck_running_ai_job_is_reset_to_retry` lors de la propre passe de
test de cette phase. Un champ related non stocké fonctionne quand même
pleinement dans un domaine `ir.rule`/recherche (Odoo fait la jointure au
travers), il n'a simplement pas sa propre colonne indexée en base — un
compromis acceptable à la taille de cette table.

## Secrets

`services/secrets_service.get_secret()` is the only way any connector or
AI provider reads a credential: environment variable first (derived name,
e.g. `legal_knowledge_watch.ai_brain.token` → `LKW_AI_BRAIN_TOKEN`), then
`ir.config_parameter` as a fallback. A secret is:

`services/secrets_service.get_secret()` est le seul moyen pour un
connecteur ou un provider IA de lire un identifiant : variable
d'environnement d'abord (nom dérivé, ex.
`legal_knowledge_watch.ai_brain.token` → `LKW_AI_BRAIN_TOKEN`), puis
`ir.config_parameter` en repli. Un secret est :

- never logged (error messages are truncated and never interpolate a raw
  token — see e.g. `piste_oauth_client.py`'s
  `test_get_token_401_raises_without_leaking_secret` and
  `test_ai_providers.py`'s `test_failure_message_never_contains_the_token`);
  <br>jamais journalisé (les messages d'erreur sont tronqués et
  n'interpolent jamais un jeton brut — voir par ex.
  `test_get_token_401_raises_without_leaking_secret` de
  `piste_oauth_client.py` et
  `test_failure_message_never_contains_the_token` de
  `test_ai_providers.py`) ;
- never displayed in a view (`secret_parameter_key` stores the *name* of
  the parameter, not its value);
  <br>jamais affiché dans une vue (`secret_parameter_key` stocke le
  *nom* du paramètre, pas sa valeur) ;
- never committed — confirmed by a `git log -p` + working-tree scan across
  the full history at audit time, clean.
  <br>jamais committé — confirmé par un `git log -p` + un scan de
  l'arbre de travail sur tout l'historique au moment de l'audit, propre.

## Outbound network hardening / Durcissement du réseau sortant

Three admin-configurable URL surfaces exist: RSS `feed_url` /
`fetch_linked_content`, and every AI/export provider's `base_url`.
Légifrance/PISTE's own API and OAuth hosts are hardcoded constants, not
admin input, so they carry a much smaller version of the same risk
(mainly: never leak the client_secret to a redirect target).

Trois surfaces d'URL configurables par un administrateur existent : le
`feed_url`/`fetch_linked_content` RSS, et le `base_url` de chaque
provider IA/export. Les hôtes API et OAuth propres à Légifrance/PISTE
sont des constantes codées en dur, pas une saisie admin, donc ils portent
une version bien plus réduite du même risque (principalement : ne jamais
laisser fuir client_secret vers une cible de redirection).

### SSRF: `services/url_safety.py`

`assert_public_host(url)` is called before every request to an admin-
configured URL (`rss_connector.py._get_with_retries`,
`http_retry.request_with_retries` — shared by both AI providers). It
rejects:

`assert_public_host(url)` est appelée avant chaque requête vers une URL
configurée par un admin (`rss_connector.py._get_with_retries`,
`http_retry.request_with_retries` — partagé par les deux providers IA).
Elle rejette :

- any scheme other than `http`/`https`;
  <br>tout schéma autre que `http`/`https` ;
- a URL whose host is **literally** a private/loopback/link-local/
  multicast/reserved/unspecified IP address (`127.0.0.1`, `10.x`,
  `172.16-31.x`, `192.168.x`, `169.254.169.254`, `::1`, etc.), via
  Python's `ipaddress` module.
  <br>une URL dont l'hôte est **littéralement** une adresse IP privée/
  loopback/link-local/multicast/réservée/non spécifiée (`127.0.0.1`,
  `10.x`, `172.16-31.x`, `192.168.x`, `169.254.169.254`, `::1`, etc.),
  via le module Python `ipaddress`.

**What this does not cover, on purpose:** a *hostname* that resolves (now
or later, via DNS rebinding) to a private address. Resolving DNS to check
this was tried and reverted — it would make `assert_public_host` a real
network call, which breaks this project's hard rule that the test suite
never touches the network (every RSS/Légifrance/AI-provider test uses fake
`*.example.org` hostnames), and a resolve-then-connect check is
rebinding-vulnerable anyway unless the resolved IP is pinned for the
actual connection (a custom transport adapter — out of scope for this
phase). The mitigations that *do* apply to a malicious hostname:

**Ce que cela ne couvre pas, volontairement :** un *nom d'hôte* qui se
résout (maintenant ou plus tard, via du DNS rebinding) vers une adresse
privée. Résoudre le DNS pour vérifier cela a été essayé puis abandonné —
cela ferait de `assert_public_host` un vrai appel réseau, ce qui casse la
règle stricte de ce projet selon laquelle la suite de tests ne touche
jamais au réseau (chaque test RSS/Légifrance/provider IA utilise des
noms d'hôte factices `*.example.org`), et une vérification
résoudre-puis-connecter reste de toute façon vulnérable au rebinding sauf
si l'IP résolue est épinglée pour la connexion réelle (un adaptateur de
transport sur mesure — hors périmètre de cette phase). Les mitigations
qui *s'appliquent* réellement à un nom d'hôte malveillant :

- RSS: the `allowed_domains` allowlist, when configured, is checked in
  `validate_configuration()`/`_host_allowed()` independently of
  `assert_public_host` — this is the real control for RSS.
  <br>RSS : la liste blanche `allowed_domains`, quand elle est
  configurée, est vérifiée dans
  `validate_configuration()`/`_host_allowed()` indépendamment de
  `assert_public_host` — c'est le vrai contrôle pour RSS.
- AI providers: **no equivalent allowlist exists yet.** A `base_url`
  pointing at an attacker-controlled hostname that itself resolves to a
  private address is not caught by this phase's hardening. `base_url` is
  Administrator-only to configure (`access_legal_ai_provider_admin`), which
  bounds who could set this, but it is a real residual gap — tracked as a
  P2 follow-up (a per-provider domain allowlist mirroring RSS's).
  <br>Providers IA : **aucune liste blanche équivalente n'existe
  encore.** Un `base_url` pointant vers un nom d'hôte contrôlé par un
  attaquant et se résolvant lui-même vers une adresse privée n'est pas
  intercepté par le durcissement de cette phase. `base_url` n'est
  configurable que par un Administrateur
  (`access_legal_ai_provider_admin`), ce qui borne qui pourrait le
  positionner, mais c'est un vrai manquement résiduel — suivi comme un
  suivi P2 (une liste blanche de domaines par provider, sur le modèle de
  celle de RSS).

### Redirects / Redirections

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

Chaque appel sortant de ce module passe désormais `allow_redirects=False`
et traite toute réponse `3xx` comme un échec dur (`rss_connector.py`,
`legifrance_connector.py`, `piste_oauth_client.py`, `http_retry.py`).
Une redirection suivie atteindrait silencieusement une URL jamais
vérifiée par `assert_public_host` ou la liste blanche RSS — pire, pour
`piste_oauth_client.py`, une redirection suivie sur la requête de token
enverrait `client_secret` vers l'hôte pointé par cette redirection.
Aucun des quatre points d'appel ne le fait plus désormais ; des tests de
régression existent pour chacun.

### Response size caps / Plafonds de taille de réponse

RSS already capped response size (`max_response_bytes`, default 5 MB,
streamed and checked incrementally). This phase adds the same 5 MB default
cap, checked via `Content-Length` when present and the actual body length
otherwise, to `legifrance_connector.py` and `http_retry.py` (both AI
providers) — an admin-configured or compromised endpoint can no longer
exhaust memory with an oversized response. See
`test_legifrance_connector.py::test_fetch_search_over_size_limit_raises`
and `test_ai_providers.py::test_oversized_response_is_rejected`.

RSS plafonnait déjà la taille de réponse (`max_response_bytes`, 5 Mo par
défaut, en flux et vérifiée de façon incrémentale). Cette phase ajoute le
même plafond de 5 Mo par défaut, vérifié via `Content-Length` quand
présent et sinon la taille réelle du corps, à `legifrance_connector.py`
et `http_retry.py` (les deux providers IA) — un endpoint configuré par
un admin ou compromis ne peut plus épuiser la mémoire avec une réponse
surdimensionnée.

### TLS

`legal.ai.provider.verify_tls` defaults to `True` and is passed straight
through to `requests` (`verify=...`) by both AI providers. There is no way
to disable it for RSS or Légifrance/PISTE (both always verify — `requests`
verifies by default and neither connector overrides that).

`legal.ai.provider.verify_tls` vaut `True` par défaut et est transmis
tel quel à `requests` (`verify=...`) par les deux providers IA. Il n'y a
aucun moyen de le désactiver pour RSS ou Légifrance/PISTE (les deux
vérifient toujours — `requests` vérifie par défaut et aucun des deux
connecteurs ne le désactive).

## Deletion and audit trail / Suppression et traçabilité

- `legal.knowledge.document.unlink()` is Administrator-only; every other
  role archives instead, keeping chatter and `legal.document.version`
  history intact.
  <br>`legal.knowledge.document.unlink()` est réservé à
  l'Administrateur ; tout autre rôle archive à la place, ce qui préserve
  le chatter et l'historique `legal.document.version` intacts.
- Retention (`docs/operations.md`) purges only the *binary content* of
  *non-current* versions, only after archiving plus a separate explicit
  grace period, and never touches the current version's content or any
  metadata row (hash, dates, provenance) on any version. Dry-run by
  default; a real run is always an explicit action (wizard, or a manual
  `dry_run=False` call) — the scheduled cron, even if enabled, only ever
  runs `dry_run=True`.
  <br>La rétention (`docs/operations.md`) ne purge que le *contenu
  binaire* des versions *non courantes*, seulement après archivage plus
  une période de grâce explicite séparée, et ne touche jamais le contenu
  de la version courante ni aucune ligne de métadonnées (hash, dates,
  provenance) sur aucune version. Dry-run par défaut ; une exécution
  réelle est toujours une action explicite (assistant, ou appel manuel
  `dry_run=False`) — le cron planifié, même activé, ne s'exécute jamais
  qu'avec `dry_run=True`.
- `legal.document.enrichment` is append-only in practice (no UI or code
  path updates an existing enrichment row) — a new classify/export attempt
  always creates a new row, preserving the full history of what an AI
  provider was asked and returned, including failed/rejected attempts.
  <br>`legal.document.enrichment` est en pratique en ajout seul (aucune
  UI ni chemin de code ne met à jour une ligne d'enrichment existante) —
  une nouvelle tentative de classification/export crée toujours une
  nouvelle ligne, préservant l'historique complet de ce qui a été demandé
  et renvoyé par un provider IA, y compris les tentatives échouées/
  rejetées.

## AI data handling / Traitement des données par l'IA

- Only `plain_text` (normalized) plus non-sensitive metadata is sent to a
  classify/export call — never the raw uploaded file, never internal Odoo
  IDs beyond `local_id`/`reference` used for round-tripping (see
  `docs/ai-providers.md`'s payload shapes).
  <br>Seul `plain_text` (normalisé) plus des métadonnées non sensibles
  sont envoyés à un appel de classification/export — jamais le fichier
  brut téléversé, jamais d'ID Odoo interne au-delà de `local_id`/
  `reference` utilisés pour l'aller-retour (voir les formes de payload de
  `docs/ai-providers.md`).
- A classify response is validated against `legal-enrichment-1.0`
  (`services/enrichment_schema.py`) before anything is trusted; on
  failure, the raw (attacker- or bug-influenced) response is stored **as
  the enrichment record's own audit content**, never merged into the
  document. AI output can only ever set `needs_review=True` — it never
  changes `status`, never touches document content or metadata fields.
  <br>Une réponse de classification est validée contre
  `legal-enrichment-1.0` (`services/enrichment_schema.py`) avant d'être
  faite confiance ; en cas d'échec, la réponse brute (influencée par un
  attaquant ou un bug) est stockée **comme le propre contenu d'audit de
  l'enregistrement d'enrichissement**, jamais fusionnée dans le document.
  Le résultat de l'IA ne peut jamais que positionner `needs_review=True`
  — il ne change jamais `status`, ne touche jamais au contenu du document
  ni à ses champs de métadonnées.
- Export is fail-closed: an unconditional floor (approved, current,
  `canonical_url`/`content_hash` set, non-empty text) that no
  `legal.export.policy` can loosen, re-checked on every job attempt, not
  cached from approval time (`docs/ai-providers.md`).
  <br>L'export est fail-closed : un plancher inconditionnel (approuvé,
  courant, `canonical_url`/`content_hash` renseignés, texte non vide)
  qu'aucune `legal.export.policy` ne peut assouplir, revérifié à chaque
  tentative de job, jamais mis en cache depuis le moment de
  l'approbation (`docs/ai-providers.md`).

## Known, deliberately deferred (P2) / Connu, volontairement différé (P2)

Not fixed in this phase — tracked here rather than silently left
undocumented:

Non corrigé à cette phase — suivi ici plutôt que laissé silencieusement
non documenté :

- **Retry/backoff code duplication**: `rss_connector.py`,
  `legifrance_connector.py`, `piste_oauth_client.py` and `http_retry.py`
  each implement their own bounded-retry loop with slightly different
  status-code handling (Légifrance treats 401/403 specially; RSS handles
  304; the OAuth client has no size cap since token responses are tiny).
  A shared retry helper across all four would remove duplication, but the
  four call sites have different-enough semantics (streaming vs. not,
  different terminal-error sets) that unifying them was judged riskier
  than valuable for a first release candidate.
  <br>**Duplication de code retry/backoff** : `rss_connector.py`,
  `legifrance_connector.py`, `piste_oauth_client.py` et `http_retry.py`
  implémentent chacun leur propre boucle de réessai bornée avec une
  gestion de code de statut légèrement différente. Une aide de réessai
  partagée entre les quatre supprimerait la duplication, mais les quatre
  points d'appel ont des sémantiques suffisamment différentes pour que
  les unifier ait été jugé plus risqué que bénéfique pour une première
  release candidate.
- **No lint tooling configured** in this repository (no
  `pyproject.toml`/`flake8`/`ruff` config) — `.github/workflows/tests.yml`
  (added in the Prompt 8/9 publish-prep pass, confirmed green on its
  first real run, 2026-08-19) now runs the test suite on push/PR, but
  there is still no automated style/lint check.
  <br>**Aucun outillage de lint configuré** dans ce dépôt (pas de
  `pyproject.toml`/`flake8`/`ruff`) — `.github/workflows/tests.yml`
  (ajouté lors de la passe de préparation publication Prompt 8/9,
  confirmé vert dès sa première exécution réelle, 2026-08-19) lance
  désormais la suite de tests sur push/PR, mais il n'y a toujours aucune
  vérification automatique de style/lint.
- **AI provider `base_url` has no domain allowlist** equivalent to RSS's
  `allowed_domains` — see the SSRF section above. `base_url` is
  Administrator-only to set, which bounds but does not close this.
  <br>**Le `base_url` des providers IA n'a pas de liste blanche de
  domaines** équivalente à `allowed_domains` de RSS — voir la section
  SSRF plus haut. `base_url` n'est configurable que par un Administrateur,
  ce qui borne sans fermer complètement ce risque.

## Secrets scan / Recherche de secrets

`git log -p` across the full history plus a working-tree grep for common
credential patterns (API keys, bearer tokens, private key headers,
`client_secret=`) was run at audit time: clean. No secret has ever been
committed to this repository.

Un `git log -p` sur tout l'historique plus un grep de l'arbre de travail
pour des motifs d'identifiants courants (clés API, jetons bearer,
en-têtes de clé privée, `client_secret=`) a été exécuté au moment de
l'audit : propre. Aucun secret n'a jamais été committé dans ce dépôt.
