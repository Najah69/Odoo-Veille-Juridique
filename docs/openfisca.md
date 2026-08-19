# OpenFisca connector

# Connecteur OpenFisca

## Scope of this phase / Périmètre de cette phase

Watches specific *legislative parameters* (a scalar value with a
date-indexed history — SMIC, plafond de la Sécurité sociale, ...) for a
new dated value, not a document feed like RSS/Légifrance. A *scale*
parameter (a progressive bracket table, e.g. the income-tax bareme) is
architecturally a different response shape (`"brackets"` instead of
`"values"`) and is explicitly out of scope — detected and reported as a
per-parameter error, never force-parsed. Extending this connector to
scales is a distinct future task, not a variation of this one.

Surveille des *paramètres législatifs* précis (une valeur scalaire avec
un historique indexé par date — SMIC, plafond de la Sécurité sociale,
...) pour une nouvelle valeur datée, pas un flux de documents comme
RSS/Légifrance. Un paramètre de type *barème* (une table de tranches
progressives, ex. le barème de l'impôt sur le revenu) a une forme de
réponse structurellement différente (`"brackets"` au lieu de `"values"`)
et est explicitement hors périmètre — détecté et signalé comme une
erreur par paramètre, jamais forcé. Étendre ce connecteur aux barèmes est
une tâche future distincte, pas une variation de celle-ci.

## Grounding: what was verified, and how / Ancrage : ce qui a été vérifié, et comment

Everything below was checked live against the real, public
`api.fr.openfisca.org` API (2026-08-19, no account/authentication
required) and, for the two default parameter paths, cross-checked
against the actual YAML source files in the open-source
`openfisca-france` repository (`github.com/openfisca/openfisca-france`)
— not guessed from the API's general shape or from a plausible-looking
path.

Tout ce qui suit a été vérifié en direct contre la vraie API publique
`api.fr.openfisca.org` (2026-08-19, aucun compte/authentification
requis) et, pour les deux chemins de paramètre par défaut, recoupé avec
les vrais fichiers source YAML du dépôt open source `openfisca-france`
(`github.com/openfisca/openfisca-france`) — jamais deviné à partir de la
forme générale de l'API ou d'un chemin plausible.

- **Base URL / URL de base** : `https://api.fr.openfisca.org/latest`,
  public, no auth. / publique, sans authentification.
- **`GET /parameters`**: flat dict `{"dotted.path": {"description": ...,
  "href": "https://.../parameter/slash/separated/path"}}`. Note the dict
  key uses dots while `href` uses slashes — not used at runtime by this
  connector (parameters to watch are configured explicitly), but this is
  how the two default paths below were discovered.
  <br>Dict plat `{"chemin.avec.points": {"description": ..., "href":
  "https://.../parameter/chemin/avec/slashs"}}`. La clé du dict utilise
  des points alors que `href` utilise des slashs — non utilisé à
  l'exécution par ce connecteur (les paramètres à surveiller sont
  configurés explicitement), mais c'est ainsi que les deux chemins par
  défaut ci-dessous ont été découverts.
- **`GET /parameter/<slash/separated/path>`** (simple scalar parameter):
  ```json
  {
    "id": "...", "description": "...", "source": "...",
    "values": {"YYYY-MM-DD": <number>, "...": "..."},
    "metadata": {
      "short_label": "...", "unit": "...", "label_en": "...",
      "official_journal_date": {"YYYY-MM-DD": "YYYY-MM-DD"},
      "reference": {"YYYY-MM-DD": {"title": "...", "href": "https://legifrance.gouv.fr/..." }}
    }
  }
  ```
  `reference[date]["href"]` is present for some parameters and absent for
  others — **both confirmed live**, not assumed from one example:
  <br>`reference[date]["href"]` est présent pour certains paramètres et
  absent pour d'autres — **les deux confirmés en direct**, pas supposés à
  partir d'un seul exemple :
  - `prelevements_sociaux.pss.plafond_securite_sociale_mensuel`: has
    `href` (a real `legifrance.gouv.fr/jorf/id/...` URL). / a un `href`
    (une vraie URL `legifrance.gouv.fr/jorf/id/...`).
  - `marche_travail.salaire_minimum.smic.smic_b_horaire`: has `title`
    only, no `href`. / a uniquement `title`, pas de `href`.
  The connector handles both: `reference.href` when present, otherwise
  the OpenFisca API detail URL itself (always a real, dereferenceable
  URL) as `source_url`/`canonical_url`.
  <br>Le connecteur gère les deux cas : `reference.href` quand présent,
  sinon l'URL de détail de l'API OpenFisca elle-même (toujours une URL
  réelle et déréférençable) comme `source_url`/`canonical_url`.
- **A scale parameter** (checked on
  `impot_revenu.bareme_ir_depuis_1945.bareme`, found via GitHub code
  search on the real repo, not guessed): root keys are `id`,
  `description`, `source`, `metadata`, and **`brackets`** — no `values`
  key at all. Confirmed live, not assumed.
  <br>**Un paramètre barème** (vérifié sur
  `impot_revenu.bareme_ir_depuis_1945.bareme`, trouvé via une recherche
  de code GitHub sur le vrai dépôt, pas deviné) : les clés racines sont
  `id`, `description`, `source`, `metadata`, et **`brackets`** — aucune
  clé `values`. Confirmé en direct, pas supposé.

### Default parameters / Paramètres par défaut

`DEFAULT_PARAMETERS` in `services/openfisca_connector.py` ships exactly
two paths, each individually verified live (real recent values, a real
`reference` entry) — never padded with unverified guesses just to look
more complete:

`DEFAULT_PARAMETERS` dans `services/openfisca_connector.py` embarque
exactement deux chemins, chacun vérifié individuellement en direct
(valeurs récentes réelles, entrée `reference` réelle) — jamais complété
par des suppositions non vérifiées juste pour paraître plus complet :

| Path / Chemin | What it is / Ce que c'est |
|---|---|
| `marche_travail.salaire_minimum.smic.smic_b_horaire` | SMIC horaire brut |
| `prelevements_sociaux.pss.plafond_securite_sociale_mensuel` | Plafond mensuel de la Sécurité sociale |

## Configuration / Configuration

`legal.watch.configuration_json` (connector_code = `openfisca`):

```json
{
  "parameters": ["marche_travail.salaire_minimum.smic.smic_b_horaire", "..."],
  "max_items_per_run": 50,
  "request_timeout_seconds": 20,
  "max_response_bytes": 2000000
}
```

`parameters` is optional — an empty/absent value falls back to
`DEFAULT_PARAMETERS`, and an explicit list fully **replaces** it (not
merged), exactly like RSS's `allowed_domains`. To find more paths: browse
`GET /parameters` (or `legislation.fr.openfisca.org`) for the dotted key,
convert dots to slashes for the connector's internal `GET /parameter/...`
call (handled automatically — you configure the dotted form).

`parameters` est optionnel — une valeur absente/vide retombe sur
`DEFAULT_PARAMETERS`, et une liste explicite le **remplace** entièrement
(pas de fusion), exactement comme `allowed_domains` pour RSS. Pour
trouver d'autres chemins : parcourir `GET /parameters` (ou
`legislation.fr.openfisca.org`) pour la clé à points, la conversion en
slashs pour l'appel interne `GET /parameter/...` du connecteur est
automatique (vous configurez la forme à points).

## Cursor behavior / Comportement du curseur

The cursor is a JSON dict `{parameter_path: last_seen_date}`. On the
**first** run for a given parameter (no entry in the cursor yet), only
the single most recent value in `values` is surfaced as a candidate —
the full history is never backfilled (some parameters, like the SMIC,
have 50+ years of entries; importing all of them on first activation
would be noise, not a "watch"). On every later run, only dates strictly
newer than the cursor's stored date are surfaced, and the cursor always
advances to the latest known date regardless of whether a candidate was
actually created for it.

Le curseur est un dict JSON `{chemin_paramètre: dernière_date_vue}`. À la
**première** exécution pour un paramètre donné (pas encore d'entrée dans
le curseur), seule la valeur la plus récente de `values` est remontée
comme candidat — l'historique complet n'est jamais rétro-importé
(certains paramètres, comme le SMIC, ont plus de 50 ans d'entrées ;
tout importer à la première activation serait du bruit, pas une veille).
À chaque exécution suivante, seules les dates strictement plus récentes
que la date stockée dans le curseur sont remontées, et le curseur avance
toujours vers la dernière date connue, qu'un candidat ait ou non été
créé pour elle.

## Deduplication / Déduplication

`external_id` is `"<parameter_path>#<effective_date>"` — globally unique
per parameter/date pair, so the module's own `(source_id, external_id)`
dedup order (`docs/architecture.md`) is what actually prevents a
re-fetched date from creating a duplicate document, independently of the
cursor. The cursor is an optimization (fewer API calls, no re-processing
of already-known dates), not the sole safety net.

`external_id` vaut `"<chemin_paramètre>#<date_effective>"` — unique
globalement par couple paramètre/date, donc c'est bien l'ordre de dédup
propre au module `(source_id, external_id)` (`docs/architecture.md`) qui
empêche réellement une date re-récupérée de créer un document en double,
indépendamment du curseur. Le curseur est une optimisation (moins
d'appels API, pas de retraitement de dates déjà connues), pas le seul
filet de sécurité.

## Security / Sécurité

HTTP calls go through the same shared `services/http_retry.py` used by
the AI/export providers (bounded retry, SSRF host check, no redirects
followed, response size cap) — see `docs/security.md`. `API_BASE_URL` is
a hardcoded constant, not admin-configurable free text, so the SSRF
surface here is much smaller than for RSS's `feed_url` — the hardening
is applied anyway, for consistency and because a compromised/malicious
response from a legitimate-looking host is still worth capping in size
and never redirect-following.

Les appels HTTP passent par le même `services/http_retry.py` partagé
qu'utilisent les providers IA/export (réessai borné, vérification SSRF
de l'hôte, aucune redirection suivie, plafond de taille de réponse) —
voir `docs/security.md`. `API_BASE_URL` est une constante codée en dur,
pas du texte libre configurable par un admin, donc la surface SSRF ici
est bien plus réduite que pour `feed_url` de RSS — le durcissement est
appliqué quand même, par cohérence et parce qu'une réponse
compromise/malveillante d'un hôte d'apparence légitime mérite quand même
un plafond de taille et l'absence de suivi de redirection.

## Known limitations / Limitations connues

- **Scale/bareme parameters are not supported** (see "Scope" above) —
  attempting to watch one produces a per-run item error, not a crash,
  but no document is ever created from it.
  <br>**Les paramètres barème ne sont pas supportés** (voir « Périmètre »
  ci-dessus) — surveiller l'un d'eux produit une erreur d'élément par
  exécution, pas un plantage, mais aucun document n'en est jamais créé.
- **`reference[date]` is not guaranteed to have `href`** — when it
  doesn't, `source_url`/`canonical_url` point at the OpenFisca API detail
  URL itself (a real, working URL, but not a human-readable legislative
  text page).
  <br>**`reference[date]` n'a pas toujours de `href`** — quand ce n'est
  pas le cas, `source_url`/`canonical_url` pointent vers l'URL de détail
  de l'API OpenFisca elle-même (une URL réelle et fonctionnelle, mais pas
  une page de texte législatif lisible par un humain).
- **Only one new candidate per parameter per run** — if a parameter
  somehow gained several new dates between two runs, only the latest is
  surfaced (the cursor still advances past all of them, so older
  in-between dates are never retroactively surfaced). Not expected in
  practice given this module's fetch cadence.
  <br>**Un seul nouveau candidat par paramètre et par exécution** — si un
  paramètre a d'une façon ou d'une autre gagné plusieurs nouvelles dates
  entre deux exécutions, seule la plus récente est remontée (le curseur
  avance quand même au-delà de toutes, donc les dates intermédiaires plus
  anciennes ne sont jamais remontées rétroactivement). Non attendu en
  pratique vu la cadence de récupération de ce module.
