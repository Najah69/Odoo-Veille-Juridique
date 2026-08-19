# Open Lefebvre Dalloz connector

# Connecteur Open Lefebvre Dalloz

## What this is / Ce que c'est

`open.lefebvre-dalloz.fr` is Éditions Lefebvre Dalloz's free legal-news
portal (Droit social / Droit des affaires — fiches, actualités, tools).
This connector watches its `/actualites` listing for new articles.

`open.lefebvre-dalloz.fr` est le portail juridique gratuit des Éditions
Lefebvre Dalloz (Droit social / Droit des affaires — fiches, actualités,
outils). Ce connecteur surveille son listing `/actualites` pour les
nouveaux articles.

## Grounding: what was verified, and how / Ancrage : ce qui a été vérifié, et comment

No documented public API and no RSS/Atom feed exist for this site — this
was checked directly, not assumed from the absence of a mention on the
homepage:

Aucune API publique documentée ni aucun flux RSS/Atom n'existe pour ce
site — vérifié directement, pas supposé faute de mention sur la page
d'accueil :

- Fetched the homepage and `/actualites` HTML directly (2026-08-19) and
  searched for `<link rel="alternate" type="application/rss+xml">` and
  any API/data-portal link in the navigation and footer: none found.
  <br>Récupération directe du HTML de la page d'accueil et de
  `/actualites` (2026-08-19), recherche de
  `<link rel="alternate" type="application/rss+xml">` et de tout lien
  API/portail de données dans la navigation et le pied de page : aucun
  trouvé.
- Checked `robots.txt` live: `Disallow: *[matter]*`, `*[topic]*`,
  `*[fiche]*`, `*[ibt]*`, `*/recherche?query=*` — dynamic-route template
  patterns, not `/actualites` itself. `Sitemap:
  https://open.lefebvre-dalloz.fr/sitemaps.xml` is declared.
  <br>`robots.txt` vérifié en direct : `Disallow: *[matter]*`,
  `*[topic]*`, `*[fiche]*`, `*[ibt]*`, `*/recherche?query=*` — des motifs
  de route dynamique, pas `/actualites` elle-même. Un `Sitemap:
  https://open.lefebvre-dalloz.fr/sitemaps.xml` est déclaré.

What *is* real, structured, and reliably usable — confirmed with a plain
HTTP GET (`curl`-equivalent, no browser/JavaScript, exactly what this
connector does):

Ce qui *est* réel, structuré, et exploitable de façon fiable — confirmé
avec un simple GET HTTP (équivalent `curl`, aucun navigateur/JavaScript,
exactement ce que fait ce connecteur) :

- The site is server-rendered Next.js. Every page's raw HTML embeds a
  `<script id="__NEXT_DATA__" type="application/json">` tag with the
  full server-side props, before any client JS runs. For `/actualites`:
  `props.pageProps.page.actualites` is a list of dicts with `id`, `title`,
  `href` (site-relative), `date` (ISO 8601), `summary` (often empty),
  `matter`, `topicTitle`, `thematic`.
  <br>Le site est en rendu serveur Next.js. Le HTML brut de chaque page
  intègre une balise `<script id="__NEXT_DATA__" type="application/json">`
  avec l'intégralité des props côté serveur, avant toute exécution JS
  client. Pour `/actualites` : `props.pageProps.page.actualites` est une
  liste de dicts avec `id`, `title`, `href` (relatif au site), `date`
  (ISO 8601), `summary` (souvent vide), `matter`, `topicTitle`,
  `thematic`.
- `?matter=droit-social`-style query filtering was tested live and does
  **not** filter server-side (the parsed `__NEXT_DATA__.query` was empty
  and `.pageProps.matter` stayed `None`) — not guessed at further; this
  connector always fetches every matter.
  <br>Le filtrage par requête `?matter=droit-social` a été testé en
  direct et ne filtre **pas** côté serveur (`__NEXT_DATA__.query` parsé
  était vide et `.pageProps.matter` restait `None`) — non poussé plus
  loin par supposition ; ce connecteur récupère toujours toutes les
  matières.

## Why this is different from Légifrance/OpenFisca / En quoi c'est différent de Légifrance/OpenFisca

Légifrance and OpenFisca are documented public contracts (OAuth2 API
catalog; a public REST API respectively) — a stable promise this
connector's data won't just disappear. `__NEXT_DATA__` is an internal
Next.js implementation detail, not a contract: a future page redesign
could remove or reshape it without notice, and this connector would
start failing loudly (`ConnectorFetchError`, never silently) rather than
returning wrong data. What it does *not* depend on is the Next.js build
id (`buildId`), which changes on every deploy — this connector re-parses
the embedded JSON fresh on every request instead of hardcoding any
build-specific URL, so an ordinary redeploy does not break it.

Légifrance et OpenFisca sont des contrats publics documentés (catalogue
d'API OAuth2 ; API REST publique respectivement) — une promesse stable
que la donnée de ce connecteur ne va pas simplement disparaître.
`__NEXT_DATA__` est un détail d'implémentation interne de Next.js, pas un
contrat : une future refonte de page pourrait le supprimer ou le
remodeler sans préavis, et ce connecteur se mettrait alors à échouer
bruyamment (`ConnectorFetchError`, jamais silencieusement) plutôt que de
retourner une donnée fausse. Ce dont il ne dépend *pas*, c'est du build
id Next.js (`buildId`), qui change à chaque déploiement — ce connecteur
reparse le JSON intégré à chaque requête plutôt que de coder en dur une
URL liée à un build précis, donc un redéploiement ordinaire ne le casse
pas.

## Configuration / Configuration

`legal.watch.configuration_json` (connector_code = `open_lefebvre_dalloz`):

```json
{
  "max_items_per_run": 20,
  "request_timeout_seconds": 20,
  "max_response_bytes": 5000000,
  "user_agent": "optional override"
}
```

No required fields — the target URL (`/actualites`) is fixed, not
admin-configured, since no working filter parameter was found.

Aucun champ requis — l'URL cible (`/actualites`) est fixe, non
configurable par l'admin, faute de paramètre de filtre fonctionnel
trouvé.

## Cursor and deduplication / Curseur et déduplication

The cursor stores `last_seen_date` (the max article `date` seen so far,
compared as ISO 8601 strings — safe since the format is fixed-width).
`external_id` is the article's own `id` (a stable UUID from the site),
so the module's own `(source_id, external_id)` dedup order
(`docs/architecture.md`) is the real safety net against duplicates —
the cursor is an optimization, not the sole guarantee.

Le curseur stocke `last_seen_date` (la `date` maximale d'article vue
jusqu'ici, comparée comme des chaînes ISO 8601 — sûr car le format est à
largeur fixe). `external_id` est l'`id` propre de l'article (un UUID
stable fourni par le site), donc c'est bien l'ordre de dédup propre au
module `(source_id, external_id)` (`docs/architecture.md`) qui est le
vrai filet de sécurité contre les doublons — le curseur est une
optimisation, pas la seule garantie.

## Security / Sécurité

Same shared `services/http_retry.py` as every other connector/provider
(bounded retry, SSRF host check, no redirects followed, response size
cap — see `docs/security.md`). `ACTUALITES_URL` is a hardcoded constant,
not admin-configurable free text.

Même `services/http_retry.py` partagé que tout autre connecteur/provider
(réessai borné, vérification SSRF de l'hôte, aucune redirection suivie,
plafond de taille de réponse — voir `docs/security.md`). `ACTUALITES_URL`
est une constante codée en dur, pas du texte libre configurable par un
admin.

## Known limitations / Limitations connues

- **Screen-scraping, not a documented API** (see "Why this is different"
  above) — the single biggest residual risk of this connector.
  <br>**Du scraping, pas une API documentée** (voir « En quoi c'est
  différent » ci-dessus) — le plus gros risque résiduel de ce connecteur.
- **No matter/topic filtering** — every run fetches all matières; use
  `legal.watch.rule` to filter/tag afterward if only one matter is
  wanted.
  <br>**Pas de filtrage par matière/thème** — chaque exécution récupère
  toutes les matières ; utilisez `legal.watch.rule` pour filtrer/étiqueter
  ensuite si une seule matière est voulue.
- **Only the listing's own summary is used** — this connector never
  fetches an individual article's full page (matching RSS's
  `fetch_linked_content=false` default philosophy: never scrape a linked
  page beyond the listing without an explicit, separate decision to do
  so). `summary` is frequently empty in practice, in which case
  `plain_text` falls back to the title alone.
  <br>**Seul le résumé du listing est utilisé** — ce connecteur ne
  récupère jamais la page complète d'un article individuel (même
  philosophie par défaut que `fetch_linked_content=false` de RSS : ne
  jamais scraper une page liée au-delà du listing sans une décision
  explicite et séparée de le faire). `summary` est fréquemment vide en
  pratique, auquel cas `plain_text` retombe sur le seul titre.
