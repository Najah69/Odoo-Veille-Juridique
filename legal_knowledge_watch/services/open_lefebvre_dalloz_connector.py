"""Open Lefebvre Dalloz connector — the free legal-news portal at
open.lefebvre-dalloz.fr (Droit social / Droit des affaires).

Grounding (verified live on 2026-08-19, via a plain `curl`-equivalent GET
— no browser/JS involved, exactly what this connector itself does — see
docs/open-lefebvre-dalloz.md for the full detail):

- No public API, no RSS/Atom feed exists for this site (checked the
  homepage HTML, the /actualites page HTML, and robots.txt — no
  `<link rel="alternate">`, no documented endpoint).
- The site is server-rendered Next.js. Every page's raw HTML — the exact
  bytes a plain HTTP GET receives, before any JavaScript runs — embeds a
  `<script id="__NEXT_DATA__" type="application/json">` tag containing
  the full server-side props used to render the page, including
  `props.pageProps.page.actualites`: a list of article dicts with `id`,
  `title`, `href` (site-relative), `date` (ISO 8601), `summary`, `matter`,
  `topicTitle`. This is genuinely reliable structured data — confirmed
  present in the raw server response, not something only visible after
  client-side hydration.
- This is still, fundamentally, screen-scraping an internal Next.js
  implementation detail rather than integrating against a documented
  public contract (unlike Légifrance/PISTE or OpenFisca) — a future site
  redesign could remove or reshape `__NEXT_DATA__` without notice. What
  it does NOT depend on is the Next.js build id (`buildId`), which
  changes on every deploy: this connector re-parses the embedded JSON
  fresh on every request rather than hardcoding any build-specific URL,
  so an ordinary redeploy (same page structure, new build id) does not
  break it — only an actual page/data-shape redesign would.
- No `?matter=`-style query filter was found to work: tested live,
  `/actualites?matter=droit-social` returns the exact same unfiltered
  list as `/actualites` (confirmed by inspecting the parsed
  `__NEXT_DATA__.query` and `.pageProps.matter`, both empty/None). Not
  guessed at further — this connector always fetches every matter and
  lets `legal.watch.rule` filter afterward if needed.
- `robots.txt` (checked live) disallows `*[matter]*`, `*[topic]*`,
  `*[fiche]*`, `*[ibt]*`, `*/recherche?query=*` — dynamic-route template
  patterns, not `/actualites` itself, which is not disallowed.

FR : Connecteur Open Lefebvre Dalloz — le portail juridique gratuit
open.lefebvre-dalloz.fr (Droit social / Droit des affaires).

Ancrage (vérifié en direct le 2026-08-19, via un GET HTTP brut équivalent
à `curl` — aucun navigateur/JS impliqué, exactement ce que fait ce
connecteur lui-même — voir docs/open-lefebvre-dalloz.md pour le détail
complet) :

- Aucune API publique, aucun flux RSS/Atom n'existe pour ce site
  (vérifié sur la page d'accueil, la page /actualites, et robots.txt —
  pas de `<link rel="alternate">`, pas d'endpoint documenté).
- Le site est en rendu serveur Next.js. Le HTML brut de chaque page — les
  octets exacts reçus par un simple GET HTTP, avant toute exécution
  JavaScript — intègre une balise
  `<script id="__NEXT_DATA__" type="application/json">` contenant
  l'intégralité des props côté serveur utilisées pour rendre la page, y
  compris `props.pageProps.page.actualites` : une liste de dicts
  d'articles avec `id`, `title`, `href` (relatif au site), `date` (ISO
  8601), `summary`, `matter`, `topicTitle`. C'est une vraie donnée
  structurée fiable — confirmée présente dans la réponse serveur brute,
  pas seulement visible après hydratation côté client.
- Cela reste fondamentalement du scraping d'un détail d'implémentation
  interne Next.js plutôt qu'une intégration contre un contrat public
  documenté (contrairement à Légifrance/PISTE ou OpenFisca) — une future
  refonte du site pourrait supprimer ou remodeler `__NEXT_DATA__` sans
  préavis. Ce dont ce connecteur NE dépend PAS, c'est du build id Next.js
  (`buildId`), qui change à chaque déploiement : ce connecteur reparse le
  JSON intégré à chaque requête plutôt que de coder en dur une URL liée à
  un build précis, donc un redéploiement ordinaire (même structure de
  page, nouveau build id) ne le casse pas — seule une vraie refonte de la
  page/forme des données le casserait.
- Aucun filtre par requête de type `?matter=` ne fonctionne : testé en
  direct, `/actualites?matter=droit-social` retourne exactement la même
  liste non filtrée que `/actualites` (confirmé en inspectant
  `__NEXT_DATA__.query` et `.pageProps.matter` une fois parsés, tous deux
  vides/None). Non poussé plus loin par supposition — ce connecteur
  récupère toujours toutes les matières et laisse `legal.watch.rule`
  filtrer ensuite si besoin.
- `robots.txt` (vérifié en direct) interdit `*[matter]*`, `*[topic]*`,
  `*[fiche]*`, `*[ibt]*`, `*/recherche?query=*` — des motifs de route
  dynamique, pas `/actualites` elle-même, qui n'est pas interdite.
"""
import json
import re
from datetime import datetime

from . import http_retry, normalize_service
from .base_connector import (
    BaseConnector,
    CandidateItem,
    ConnectorConfigError,
    ConnectorFetchError,
    FetchResult,
)
from .connector_registry import register_connector

BASE_URL = "https://open.lefebvre-dalloz.fr"
ACTUALITES_URL = f"{BASE_URL}/actualites"
DEFAULT_USER_AGENT = "legal-knowledge-watch/1.0 (+https://github.com/Najah69/Odoo-Veille-Juridique)"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESPONSE_BYTES = 5_000_000
DEFAULT_MAX_ITEMS_PER_RUN = 20

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
    re.DOTALL,
)


def _extract_next_data(html_text):
    match = _NEXT_DATA_RE.search(html_text)
    if not match:
        # EN: The page no longer embeds __NEXT_DATA__ the way it did when
        # this connector was written — a site redesign, not a transient
        # error. Never guessed at a replacement pattern.
        # FR : La page n'intègre plus __NEXT_DATA__ comme au moment de
        # l'écriture de ce connecteur — une refonte du site, pas une
        # erreur transitoire. Aucun motif de remplacement deviné.
        raise ConnectorFetchError(
            f"{ACTUALITES_URL} no longer embeds a __NEXT_DATA__ script "
            f"tag — the site's structure has likely changed; this "
            f"connector needs updating, not retrying."
        )
    try:
        return json.loads(match.group(1))
    except ValueError as exc:
        raise ConnectorFetchError(
            f"__NEXT_DATA__ on {ACTUALITES_URL} was not valid JSON."
        ) from exc


@register_connector
class OpenLefebvreDallozConnector(BaseConnector):
    code = "open_lefebvre_dalloz"

    def _config(self):
        raw = self.watch.configuration_json or "{}"
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigError(
                f"configuration_json is not valid JSON: {exc}"
            ) from exc

    def validate_configuration(self):
        config = self._config()
        max_items = config.get("max_items_per_run", DEFAULT_MAX_ITEMS_PER_RUN)
        if not isinstance(max_items, int) or max_items <= 0:
            raise ConnectorConfigError("max_items_per_run must be a positive integer.")
        return config

    def fetch(self, cursor, limit=100):
        config = self.validate_configuration()
        timeout = config.get("request_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        max_response_bytes = config.get("max_response_bytes", DEFAULT_MAX_RESPONSE_BYTES)
        max_items = min(limit or DEFAULT_MAX_ITEMS_PER_RUN,
                         config.get("max_items_per_run", DEFAULT_MAX_ITEMS_PER_RUN))

        cursor_data = {}
        if cursor:
            try:
                cursor_data = json.loads(cursor)
            except (TypeError, ValueError):
                cursor_data = {}
        last_seen_date = cursor_data.get("last_seen_date")

        response = http_retry.request_with_retries(
            "get", ACTUALITES_URL, ConnectorFetchError,
            max_response_bytes=max_response_bytes, timeout=timeout,
            headers={"User-Agent": config.get("user_agent") or DEFAULT_USER_AGENT},
        )
        next_data = _extract_next_data(response.text)

        try:
            actualites = next_data["props"]["pageProps"]["page"]["actualites"]
        except (KeyError, TypeError) as exc:
            raise ConnectorFetchError(
                f"__NEXT_DATA__ on {ACTUALITES_URL} no longer has the "
                f"expected props.pageProps.page.actualites path — the "
                f"site's data shape has likely changed."
            ) from exc

        items = []
        item_errors = []
        newest_date_seen = last_seen_date
        for entry in actualites:
            try:
                candidate, entry_date = self._entry_to_candidate(entry)
            except Exception as exc:  # noqa: BLE001 - one bad item must not break the run
                item_errors.append({
                    "title": entry.get("title") or entry.get("id") or "(unknown)",
                    "error": str(exc),
                })
                continue
            if entry_date and (newest_date_seen is None or entry_date > newest_date_seen):
                newest_date_seen = entry_date
            if last_seen_date and entry_date and entry_date <= last_seen_date:
                continue
            items.append(candidate)

        items = items[:max_items]
        next_cursor_data = dict(cursor_data)
        if newest_date_seen:
            next_cursor_data["last_seen_date"] = newest_date_seen

        diagnostics = {
            "status": "ok",
            "raw_item_count": len(actualites),
            "returned_item_count": len(items),
            "item_errors": item_errors,
        }
        return FetchResult(
            items=items, next_cursor=json.dumps(next_cursor_data),
            diagnostics=diagnostics,
        )

    def _entry_to_candidate(self, entry):
        href = entry.get("href") or ""
        if not href:
            raise ValueError("actualité entry has no 'href'.")
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        title = normalize_service.normalize_whitespace(entry.get("title") or "(untitled)")
        summary = normalize_service.normalize_whitespace(entry.get("summary") or "")
        plain_text = summary or title
        date_str = entry.get("date")

        return CandidateItem(
            source_url=url,
            canonical_url=url,
            title=title,
            external_id=entry.get("id") or None,
            plain_text=plain_text,
            published_at=_parse_iso_datetime(date_str),
            content_type="text/plain",
            language="fr_FR",
            source_metadata={
                "matter": entry.get("matter"),
                "topic_title": entry.get("topicTitle"),
                "thematic": entry.get("thematic"),
            },
        ), date_str


def _parse_iso_datetime(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
