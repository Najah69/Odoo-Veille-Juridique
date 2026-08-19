# Contributing / Contribuer

Thanks for considering a contribution to `legal_knowledge_watch`. This is
an Odoo 18 Community module; the notes below are what you need to get a
change merged, not a general Odoo tutorial.

Merci d'envisager une contribution à `legal_knowledge_watch`. C'est un
module Odoo 18 Community ; les notes ci-dessous vous donnent ce qu'il
faut pour faire fusionner un changement, ce n'est pas un tutoriel Odoo
général.

## Setup / Mise en place

1. An Odoo 18.0 Community environment with this module's addons path
   pointing at `legal_knowledge_watch/`.
   <br>Un environnement Odoo 18.0 Community avec le chemin d'addons
   pointant vers `legal_knowledge_watch/`.
2. `pip install requests feedparser beautifulsoup4` — required
   (`external_dependencies` in the manifest, the module refuses to install
   without them). `PyPDF2` is optional (PDF text extraction in the manual-
   import wizard degrades gracefully without it).
   <br>`pip install requests feedparser beautifulsoup4` — requis
   (`external_dependencies` dans le manifest, le module refuse de
   s'installer sans eux). `PyPDF2` est optionnel (l'extraction de texte
   PDF dans l'assistant d'import manuel se dégrade proprement sans lui).
3. No external account is required for local development. A Légifrance/
   PISTE watch needs sandbox credentials (`docs/legifrance-piste.md`) —
   everything else (manual import, RSS, OCA DMS, `webhook`/`filesystem` AI
   providers) works with zero external services.
   <br>Aucun compte externe n'est requis pour le développement local. Une
   veille Légifrance/PISTE nécessite des identifiants sandbox (voir
   `docs/legifrance-piste.md`) — tout le reste (import manuel, RSS, OCA
   DMS, providers IA `webhook`/`filesystem`) fonctionne sans aucun service
   externe.

## Running the tests / Lancer les tests

```bash
odoo --test-enable --stop-after-init -i legal_knowledge_watch -d <test_db>
```

**The full suite must run offline.** Every test that would otherwise reach
the network mocks `requests` (or the equivalent) at the precise
module-qualified import point — see any `tests/test_*.py` file for the
pattern (`@patch("odoo.addons.legal_knowledge_watch.services.<module>.requests.<verb>")`).
A test that needs a real network call, a real DNS resolution, or a real
external service is not acceptable in this suite — see
`services/url_safety.py`'s module docstring for a concrete example of a
design choice (IP-literal SSRF checking, not DNS-resolution-based) made
specifically to keep this rule intact.

**La suite complète doit s'exécuter hors ligne.** Tout test qui aurait
sinon besoin du réseau simule (mock) `requests` (ou équivalent) au point
d'import exact du module — voir n'importe quel fichier `tests/test_*.py`
pour le motif
(`@patch("odoo.addons.legal_knowledge_watch.services.<module>.requests.<verb>")`).
Un test qui a besoin d'un vrai appel réseau, d'une vraie résolution DNS,
ou d'un vrai service externe n'est pas acceptable dans cette suite — voir
la docstring de module de `services/url_safety.py` pour un exemple concret
d'un choix de conception (vérification SSRF par IP littérale, pas par
résolution DNS) fait spécifiquement pour préserver cette règle.

New tests go in `tests/test_*.py` and must be imported from
`tests/__init__.py` (Odoo does not auto-discover test modules).

Les nouveaux tests vont dans `tests/test_*.py` et doivent être importés
depuis `tests/__init__.py` (Odoo ne découvre pas automatiquement les
modules de test).

## Code conventions / Conventions de code

- No hidden guesswork against an external API or library: if you're
  implementing something against Légifrance/PISTE, OCA DMS, or any other
  external system, ground it in real, current source (official docs,
  a live/independently-verifiable API catalog, or an actively maintained
  open-source client) and say in a comment/doc what was verified vs. what
  wasn't. See `docs/legifrance-piste.md` for the standard this project
  holds itself to.
  <br>Pas de suppositions cachées contre une API ou une bibliothèque
  externe : si vous implémentez quelque chose contre Légifrance/PISTE,
  OCA DMS, ou tout autre système externe, ancrez-le dans une source
  réelle et à jour (documentation officielle, catalogue d'API vérifiable
  en direct, ou client open source activement maintenu) et précisez dans
  un commentaire/doc ce qui a été vérifié vs. ce qui ne l'a pas été. Voir
  `docs/legifrance-piste.md` pour le standard que ce projet s'impose.
- New connectors register via `services/connector_registry.py`; new AI/
  export providers via `services/ai_provider_registry.py`. The core
  models never import a concrete connector/provider class directly.
  <br>Les nouveaux connecteurs s'enregistrent via
  `services/connector_registry.py` ; les nouveaux providers IA/export via
  `services/ai_provider_registry.py`. Les modèles cœur n'importent jamais
  directement une classe concrète de connecteur/provider.
- OCA DMS stays strictly optional: never add it to the manifest's
  `depends`, never import `dms.*` models at module load time outside
  `services/storage_dms.py`'s own availability check.
  <br>OCA DMS reste strictement optionnel : ne jamais l'ajouter aux
  `depends` du manifest, ne jamais importer les modèles `dms.*` au
  chargement du module en dehors de la propre vérification de
  disponibilité de `services/storage_dms.py`.
- AI/export providers stay agnostic: no provider-specific behavior in
  `legal.ai.job`/`legal.knowledge.document` — only `BaseAIProvider`'s
  interface.
  <br>Les providers IA/export restent agnostiques : aucun comportement
  spécifique à un provider dans `legal.ai.job`/`legal.knowledge.document`
  — uniquement l'interface de `BaseAIProvider`.
- Fail closed on ambiguous or unsafe state: see the export-policy
  unconditional floor (`docs/ai-providers.md`) and the SSRF/redirect/size
  checks (`docs/security.md`) for the pattern — an error or an
  unrecognized state blocks the action, it never falls through to
  "probably fine."
  <br>Échouer de façon fermée (fail closed) sur un état ambigu ou
  dangereux : voir le plancher non négociable de la politique d'export
  (`docs/ai-providers.md`) et les vérifications SSRF/redirection/taille
  (`docs/security.md`) pour le modèle à suivre — une erreur ou un état
  non reconnu bloque toujours l'action, il ne bascule jamais vers un
  « ça doit probablement aller ».
- Never commit a secret. `services/secrets_service.py` is the only
  sanctioned way to read one (environment variable first, then
  `ir.config_parameter`) — never hardcode a token/key, even a test one
  that looks obviously fake (use `patch.dict(os.environ, ...)` in tests).
  <br>Ne jamais committer un secret. `services/secrets_service.py` est le
  seul moyen sanctionné d'en lire un (variable d'environnement d'abord,
  puis `ir.config_parameter`) — ne jamais coder en dur un jeton/une clé,
  même une clé de test manifestement factice (utilisez
  `patch.dict(os.environ, ...)` dans les tests).
- Multi-company: any new model with a `company_id` (direct or related)
  needs a matching `ir.rule` in `security/security.xml` — see
  `docs/security.md` for the P0 gap this project shipped once already and
  had to fix.
  <br>Multi-société : tout nouveau modèle avec un `company_id` (direct ou
  related) a besoin d'une `ir.rule` correspondante dans
  `security/security.xml` — voir `docs/security.md` pour le manquement P0
  que ce projet a déjà livré une fois et a dû corriger.

## Commit / PR conventions / Conventions de commit et de PR

- One logical change per commit; this repo's history uses `feat:`, `fix:`,
  `chore:`, `docs:` prefixes (see `git log`).
  <br>Un changement logique par commit ; l'historique de ce dépôt utilise
  les préfixes `feat:`, `fix:`, `chore:`, `docs:` (voir `git log`).
- Update `CHANGELOG.md` (Keep a Changelog format) under a new `[Unreleased]`
  or versioned section for any user-visible change, and bump
  `__manifest__.py`'s `version` for anything beyond a docs-only change.
  <br>Mettez à jour `CHANGELOG.md` (format Keep a Changelog) sous une
  nouvelle section `[Unreleased]` ou versionnée pour tout changement
  visible par l'utilisateur, et incrémentez le `version` de
  `__manifest__.py` pour tout changement au-delà d'une simple mise à jour
  de documentation.
- If your change touches security-relevant behavior (access control,
  secrets, outbound network calls, deletion), update `docs/security.md` in
  the same PR — don't leave the audit document stale.
  <br>Si votre changement touche un comportement pertinent pour la
  sécurité (contrôle d'accès, secrets, appels réseau sortants,
  suppression), mettez à jour `docs/security.md` dans la même PR — ne
  laissez pas le document d'audit devenir obsolète.

## Versioning / Versionnage

`MAJOR.MINOR.PATCH` follows Odoo's `18.0.X.Y.Z` convention: `X` bumps per
phase/feature addition, `Y`/`Z` for smaller fixes on top of a released `X`.
See `CHANGELOG.md` for the phase-by-phase history.

`MAJOR.MINOR.PATCH` suit la convention Odoo `18.0.X.Y.Z` : `X` s'incrémente
par phase/ajout de fonctionnalité, `Y`/`Z` pour des correctifs plus
mineurs sur un `X` déjà publié. Voir `CHANGELOG.md` pour l'historique
phase par phase.
