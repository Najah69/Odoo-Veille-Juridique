"""Légifrance/PISTE connector — LODA collection (Lois, Ordonnances,
Décrets, Arrêtés) only in this phase.

Grounding: no PISTE Swagger UI was directly reachable in this environment
(it requires a registered PISTE account). Everything below was verified
against two independent, real, current sources instead of being guessed —
see docs/legifrance-piste.md for the full confidence breakdown:

1. The public PISTE API catalog (piste.gouv.fr/api-catalog-sandbox,
   checked 2026-08-19, no login required): confirms the Légifrance API
   exists there, its OAuth/API hostnames, and that Swagger 2.0/3.0 specs
   are attached per-API (not directly downloadable without an account).
2. github.com/rdassignies/pylegifrance (MIT, open source, actively
   maintained): its pylegifrance/models/generated/model.py is
   *mechanically generated* by datamodel-codegen from a file named
   legifrance.json dated 2025-05-28 — i.e. a real snapshot of DILA's
   actual OpenAPI spec, not hand-written guesses. Endpoint routes, request
   DTOs (SearchRequestDTO/ChampDTO/CritereDTO/FiltreDTO), enums
   (Fond/TypeChamp/TypeRecherche/Operateur/Nature2/Sort1) and response
   models (ConsultTextResponse/ConsultArticle/ConsultSection) were read
   directly from that file.

What is NOT independently confirmed: the sandbox API base path
(SANDBOX_API_URL below follows the same path pattern as production, which
IS confirmed, but wasn't seen literally in either source) and the exact
shape of a live HTTP response (only the Pydantic schema was inspected, no
live call was made — no PISTE credentials are available in this
environment). Test this against a real sandbox account before production.
"""
import json
import logging
import time
from datetime import date, datetime, timedelta

import requests

from . import normalize_service, secrets_service
from .base_connector import (
    BaseConnector,
    CandidateItem,
    ConnectorConfigError,
    ConnectorFetchError,
    FetchResult,
)
from .connector_registry import register_connector
from .piste_oauth_client import PisteOAuthClient, PisteOAuthTokenError

_logger = logging.getLogger(__name__)

# Confirmed live (piste-gouv.fr/api-catalog-sandbox, 2026-08-19).
PRODUCTION_API_URL = "https://api.piste.gouv.fr/dila/legifrance/lf-engine-app/"
# Same path pattern as production (confirmed), sandbox- host prefix
# (confirmed to exist for OAuth) — the combination was not independently
# observed together. See module docstring.
SANDBOX_API_URL = "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app/"

DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_ITEMS_PER_RUN = 50
DEFAULT_LOOKBACK_DAYS_FIRST_RUN = 7
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1
PISTE_MAX_PAGE_SIZE = 100  # per the generated model's own field description

# Our document_type (Phase 0 selection) <- PISTE Nature2 enum value.
# ORDONNANCE has no clean single English equivalent in our coarse
# selection; mapped to "decree" (ordonnances function as decree-laws in
# French law) rather than inventing a new document_type value here.
_NATURE_TO_DOCUMENT_TYPE = {
    "LOI": "law",
    "DECRET": "decree",
    "DECRET_LOI": "decree",
    "ORDONNANCE": "decree",
    "ARRETE": "order",
}


def _iso_date(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _parse_piste_datetime(value):
    """Best-effort parse of a PISTE datetime string (seen format:
    '2021-04-15T16:49:47.707+0000', per ChronolegiResponse.datePublication
    in the generated model). Never raises: returns None on any unexpected
    format so a date-parsing quirk never drops a candidate.
    """
    if not value or not isinstance(value, str):
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        pass
    if len(candidate) >= 5 and candidate[-5] in "+-" and candidate[-3] != ":":
        try:
            return datetime.fromisoformat(candidate[:-2] + ":" + candidate[-2:])
        except ValueError:
            pass
    return None


@register_connector
class LegifranceConnector(BaseConnector):
    code = "legifrance"

    def _config(self):
        raw = self.watch.configuration_json or "{}"
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigError(
                f"configuration_json is not valid JSON: {exc}"
            ) from exc

    def _get_credentials(self):
        env = self.watch.env
        client_id = secrets_service.get_secret(
            env, "legal_knowledge_watch.legifrance.client_id",
            "LKW_LEGIFRANCE_CLIENT_ID",
        )
        client_secret = secrets_service.get_secret(
            env, "legal_knowledge_watch.legifrance.client_secret",
            "LKW_LEGIFRANCE_CLIENT_SECRET",
        )
        return client_id, client_secret

    def validate_configuration(self):
        config = self._config()

        environment = config.get("environment", "sandbox")
        if environment not in ("sandbox", "production"):
            raise ConnectorConfigError(
                "configuration_json.environment must be 'sandbox' or 'production'."
            )

        keywords = config.get("keywords") or []
        if not isinstance(keywords, list) or not keywords:
            raise ConnectorConfigError(
                "configuration_json.keywords must be a non-empty list."
            )

        natures = config.get("natures") or []
        if not isinstance(natures, list):
            raise ConnectorConfigError("configuration_json.natures must be a list.")
        unknown_natures = set(natures) - set(_NATURE_TO_DOCUMENT_TYPE)
        if unknown_natures:
            raise ConnectorConfigError(
                f"configuration_json.natures has unsupported values: "
                f"{sorted(unknown_natures)}. Supported: "
                f"{sorted(_NATURE_TO_DOCUMENT_TYPE)}."
            )

        max_items = config.get("max_items_per_run", DEFAULT_MAX_ITEMS_PER_RUN)
        if not isinstance(max_items, int) or max_items <= 0:
            raise ConnectorConfigError("max_items_per_run must be a positive integer.")

        client_id, client_secret = self._get_credentials()
        if not client_id or not client_secret:
            raise ConnectorConfigError(
                "Légifrance/PISTE credentials are not configured. Set the "
                "LKW_LEGIFRANCE_CLIENT_ID/LKW_LEGIFRANCE_CLIENT_SECRET "
                "environment variables, or the "
                "legal_knowledge_watch.legifrance.client_id/client_secret "
                "system parameters. See docs/legifrance-piste.md."
            )

        return config

    def _build_search_payload(self, config, start_date, end_date, page_size):
        keywords = config.get("keywords") or []
        champs = [
            {
                "typeChamp": "ALL",
                "operateur": "ET" if index == 0 else "OU",
                "criteres": [{
                    "valeur": keyword,
                    "typeRecherche": "TOUS_LES_MOTS_DANS_UN_CHAMP",
                    "operateur": "ET",
                    "proximite": None,
                    "criteres": None,
                }],
            }
            for index, keyword in enumerate(keywords)
        ]

        filtres = [{
            "facette": "DATE_PUBLICATION",
            "dates": {"start": start_date, "end": end_date},
            "valeurs": None, "singleDate": None, "multiValeurs": None,
        }]
        natures = config.get("natures") or []
        if natures:
            filtres.append({
                "facette": "NATURE", "valeurs": natures,
                "dates": None, "singleDate": None, "multiValeurs": None,
            })

        recherche = {
            "champs": champs,
            "filtres": filtres,
            "pageNumber": 1,
            "pageSize": page_size,
            "sort": "PUBLICATION_DATE_DESC",
            "operateur": "ET",
            "typePagination": "DEFAUT",
        }
        return {"fond": config.get("fond", "LODA_DATE"), "recherche": recherche}

    def _post_with_retries(self, url, token, payload, timeout):
        last_exc = None
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_exc = ConnectorFetchError(f"Network error calling {url}: {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                    continue
                raise last_exc from exc

            if response.status_code in (401, 403):
                raise ConnectorFetchError(
                    f"PISTE rejected the request (HTTP {response.status_code}) "
                    f"calling {url}."
                )
            if response.status_code == 429 or response.status_code >= 500:
                last_exc = ConnectorFetchError(
                    f"HTTP {response.status_code} calling {url}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                    continue
                raise last_exc
            if response.status_code >= 400:
                raise ConnectorFetchError(
                    f"HTTP {response.status_code} calling {url}: {response.text[:500]}"
                )
            return response
        raise last_exc or ConnectorFetchError(f"Failed to call {url}")

    def fetch(self, cursor, limit=100):
        config = self.validate_configuration()
        environment = config.get("environment", "sandbox")
        api_url = SANDBOX_API_URL if environment == "sandbox" else PRODUCTION_API_URL
        timeout = config.get("request_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)

        client_id, client_secret = self._get_credentials()
        oauth_client = PisteOAuthClient(client_id, client_secret, environment, timeout)
        try:
            token = oauth_client.get_token()
        except PisteOAuthTokenError as exc:
            raise ConnectorFetchError(str(exc)) from exc

        cursor_data = {}
        if cursor:
            try:
                cursor_data = json.loads(cursor)
            except (TypeError, ValueError):
                cursor_data = {}

        lookback_days = config.get(
            "lookback_days_first_run", DEFAULT_LOOKBACK_DAYS_FIRST_RUN
        )
        start_date = cursor_data.get("since") or _iso_date(
            date.today() - timedelta(days=lookback_days)
        )
        end_date = _iso_date(date.today())

        max_items = min(
            limit or DEFAULT_MAX_ITEMS_PER_RUN,
            config.get("max_items_per_run", DEFAULT_MAX_ITEMS_PER_RUN),
        )
        page_size = min(max_items, PISTE_MAX_PAGE_SIZE)

        payload = self._build_search_payload(config, start_date, end_date, page_size)
        search_response = self._post_with_retries(
            f"{api_url}search", token, payload, timeout
        )
        search_data = search_response.json()
        raw_results = search_data.get("results") or []

        items = []
        item_errors = []
        for result in raw_results[:max_items]:
            try:
                item = self._result_to_candidate(
                    result, api_url, token, config, timeout
                )
                items.append(item)
            except Exception as exc:  # noqa: BLE001 - one bad item must not break the run
                item_errors.append({
                    "title": result.get("title") or "(no title)",
                    "error": str(exc),
                })

        next_cursor = json.dumps({"since": end_date})
        diagnostics = {
            "status": "ok",
            "http_status": search_response.status_code,
            "raw_item_count": len(raw_results),
            "returned_item_count": len(items),
            "item_errors": item_errors,
            "total_results": search_data.get("totalResultNumber"),
        }
        return FetchResult(items=items, next_cursor=next_cursor, diagnostics=diagnostics)

    def _result_to_candidate(self, result, api_url, token, config, timeout):
        titles = result.get("titles") or []
        if not titles:
            raise ValueError("Search result has no 'titles' entry.")
        title_entry = titles[0]
        text_id = title_entry.get("id")
        title = title_entry.get("title")
        if not text_id or not title:
            raise ValueError("Search result title entry is missing id/title.")

        nature = result.get("nature")
        canonical_url = f"https://www.legifrance.gouv.fr/loda/id/{text_id}"

        plain_text = title
        published_at = None
        consult_error = None
        try:
            consult_response = self._post_with_retries(
                f"{api_url}consult/lawDecree", token,
                {"textId": text_id, "date": _iso_date(date.today())}, timeout,
            ).json()
            extracted = self._extract_plain_text(consult_response)
            if extracted:
                plain_text = extracted
            published_at = _parse_piste_datetime(consult_response.get("dateParution"))
        except ConnectorFetchError as exc:
            # Full-text retrieval failing must not drop the candidate: keep
            # the title-only version and flag it for review downstream via
            # source_metadata, matching the PDF-extraction fallback pattern
            # used by the manual-import wizard.
            consult_error = str(exc)
            _logger.warning("Légifrance consult/lawDecree failed for %s: %s", text_id, exc)

        return CandidateItem(
            source_url=canonical_url,
            canonical_url=canonical_url,
            title=normalize_service.normalize_whitespace(title),
            external_id=text_id,
            raw_content=None,
            plain_text=plain_text,
            published_at=published_at,
            updated_at=None,
            content_type="text/html",
            language="fr_FR",
            source_metadata={
                "nature": nature,
                "cid": text_id,
                "consult_error": consult_error,
                "document_type": _NATURE_TO_DOCUMENT_TYPE.get(nature, "law"),
            },
        )

    def _extract_plain_text(self, consult_response):
        """Walk articles/sections recursively, concatenating
        ConsultArticle.content (HTML). Field names confirmed against the
        real generated Pydantic models — see module docstring. Never
        raises: returns None on any unexpected shape so the caller falls
        back to the title.
        """
        try:
            html_parts = []

            def walk_articles(articles):
                for article in articles or []:
                    content = article.get("content")
                    if content:
                        html_parts.append(content)

            def walk_sections(sections):
                for section in sections or []:
                    walk_articles(section.get("articles"))
                    walk_sections(section.get("sections"))

            walk_articles(consult_response.get("articles"))
            walk_sections(consult_response.get("sections"))

            if not html_parts:
                return None
            return normalize_service.html_to_text(" ".join(html_parts))
        except Exception:  # noqa: BLE001 - extraction is always best-effort
            return None
