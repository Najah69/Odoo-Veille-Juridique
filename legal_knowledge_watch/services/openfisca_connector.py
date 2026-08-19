"""OpenFisca connector — watches specific legislative *parameters*
(SMIC, plafond de la Sécurité sociale, ...) for a new dated value, not a
document feed in the RSS/Légifrance sense.

Grounding (verified live against the real API on 2026-08-19, and cross-
checked against the open-source openfisca-france parameter YAML files —
github.com/openfisca/openfisca-france — for the two default paths below,
see docs/openfisca.md for the full detail):

- Base URL `https://api.fr.openfisca.org/latest`, public, no
  authentication required.
- `GET /parameters` returns a flat dict `{"dotted.path": {"description":
  ..., "href": "https://.../parameter/slash/separated/path"}}` — the
  dict key uses dots, the href uses slashes. Not used by this connector
  at runtime (parameters to watch are configured explicitly), but this is
  how DEFAULT_PARAMETERS below were discovered and verified.
- `GET /parameter/<slash/separated/path>` returns, for a simple scalar
  parameter: `{"id", "description", "source", "values": {"YYYY-MM-DD":
  number, ...}, "metadata": {"short_label", "unit", "label_en",
  "official_journal_date": {"YYYY-MM-DD": "YYYY-MM-DD"}, "reference":
  {"YYYY-MM-DD": {"title": "...", "href": "https://legifrance..."}}}}`.
  `reference[date]["href"]` is present for some parameters (confirmed on
  the PSS one below) and absent for others (confirmed on the SMIC one
  below, only "title") — this connector handles both.
- A *scale* parameter (a progressive bracket table, e.g. the income tax
  bareme) returns `"brackets"` instead of `"values"` — a structurally
  different shape. Out of scope for this connector: detected and skipped
  as a per-parameter error, never guessed at or force-parsed.

FR : Connecteur OpenFisca — surveille des *paramètres* législatifs précis
(SMIC, plafond de la Sécurité sociale, ...) pour une nouvelle valeur
datée, pas un flux de documents au sens RSS/Légifrance.

Ancrage (vérifié en direct contre l'API réelle le 2026-08-19, et recoupé
avec les fichiers YAML de paramètres open source d'openfisca-france —
github.com/openfisca/openfisca-france — pour les deux chemins par défaut
ci-dessous ; voir docs/openfisca.md pour le détail complet) :

- URL de base `https://api.fr.openfisca.org/latest`, publique, aucune
  authentification requise.
- `GET /parameters` retourne un dict plat `{"chemin.avec.points":
  {"description": ..., "href": "https://.../parameter/chemin/avec/slashs"}}`
  — la clé du dict utilise des points, le href des slashs. Non utilisé
  par ce connecteur à l'exécution (les paramètres à surveiller sont
  configurés explicitement), mais c'est ainsi que DEFAULT_PARAMETERS
  ci-dessous ont été découverts et vérifiés.
- `GET /parameter/<chemin/avec/slashs>` retourne, pour un paramètre
  scalaire simple : `{"id", "description", "source", "values":
  {"AAAA-MM-JJ": nombre, ...}, "metadata": {"short_label", "unit",
  "label_en", "official_journal_date": {"AAAA-MM-JJ": "AAAA-MM-JJ"},
  "reference": {"AAAA-MM-JJ": {"title": "...", "href":
  "https://legifrance..."}}}}`. `reference[date]["href"]` est présent
  pour certains paramètres (confirmé sur le PSS ci-dessous) et absent
  pour d'autres (confirmé sur le SMIC ci-dessous, uniquement "title") —
  ce connecteur gère les deux cas.
- Un paramètre de type *barème* (une table de tranches progressives, ex.
  le barème de l'impôt sur le revenu) retourne `"brackets"` au lieu de
  `"values"` — une forme structurellement différente. Hors périmètre de
  ce connecteur : détecté et ignoré comme une erreur par paramètre,
  jamais deviné ni forcé.
"""
import json
from datetime import datetime

from . import http_retry
from .base_connector import (
    BaseConnector,
    CandidateItem,
    ConnectorConfigError,
    ConnectorFetchError,
    FetchResult,
)
from .connector_registry import register_connector

API_BASE_URL = "https://api.fr.openfisca.org/latest"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_MAX_ITEMS_PER_RUN = 50

# EN: Predefined defaults (used when configuration_json.parameters is
# absent/empty) — two RH/payroll-relevant parameters, each individually
# verified live against the real API (see the module docstring). Never
# padded with unverified guesses just to make this list longer. The
# admin can override or extend this list via configuration_json.parameters,
# exactly like RSS's allowed_domains.
# FR : Valeurs par défaut prédéfinies (utilisées quand
# configuration_json.parameters est absent/vide) — deux paramètres
# pertinents RH/paie, chacun vérifié individuellement en direct contre
# l'API réelle (voir la docstring de module). Jamais complété avec des
# suppositions non vérifiées juste pour allonger la liste. L'admin peut
# remplacer ou étendre cette liste via configuration_json.parameters,
# exactement comme allowed_domains pour RSS.
DEFAULT_PARAMETERS = [
    "marche_travail.salaire_minimum.smic.smic_b_horaire",
    "prelevements_sociaux.pss.plafond_securite_sociale_mensuel",
]

# EN: Best-effort French legal-act-type keyword -> this module's
# document_type. reference["title"] is free text (e.g. "Arrêté du
# 22/12/2025", "Décret n° ...", "Loi n° ..."); an unrecognized or absent
# title falls back to "other" rather than guessing.
# FR : Correspondance au mieux entre le mot-clé de type d'acte français
# et le document_type de ce module. reference["title"] est du texte libre
# (ex. "Arrêté du 22/12/2025", "Décret n° ...", "Loi n° ...") ; un titre
# non reconnu ou absent retombe sur "other" plutôt que d'être deviné.
_TITLE_KEYWORD_TO_DOCUMENT_TYPE = {
    "loi": "law",
    "décret": "decree",
    "decret": "decree",
    "ordonnance": "decree",
    "arrêté": "order",
    "arrete": "order",
}


def _guess_document_type(reference_title):
    if not reference_title:
        return "other"
    first_word = reference_title.strip().split(" ", 1)[0].lower()
    return _TITLE_KEYWORD_TO_DOCUMENT_TYPE.get(first_word, "other")


def _parse_iso_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


@register_connector
class OpenFiscaConnector(BaseConnector):
    code = "openfisca"

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
        # EN: `parameters is None` (key absent) is the only case that
        # falls back to DEFAULT_PARAMETERS — an explicitly configured
        # empty list must still fail validation below, not be silently
        # swallowed by an `or DEFAULT_PARAMETERS` fallback (an empty list
        # is falsy in Python, so that pattern would have treated "[]" and
        # "absent" identically).
        # FR : `parameters is None` (clé absente) est le seul cas qui
        # retombe sur DEFAULT_PARAMETERS — une liste vide explicitement
        # configurée doit quand même échouer la validation ci-dessous, et
        # non être silencieusement absorbée par un repli `or
        # DEFAULT_PARAMETERS` (une liste vide est fausse en Python, ce
        # motif aurait traité "[]" et "absent" de façon identique).
        parameters = config.get("parameters")
        if parameters is None:
            parameters = DEFAULT_PARAMETERS
        if not isinstance(parameters, list) or not parameters:
            raise ConnectorConfigError(
                "configuration_json.parameters must be a non-empty list "
                "of OpenFisca parameter paths (e.g. "
                "'marche_travail.salaire_minimum.smic.smic_b_horaire')."
            )
        if not all(isinstance(path, str) and path for path in parameters):
            raise ConnectorConfigError(
                "configuration_json.parameters must contain only "
                "non-empty strings."
            )
        max_items = config.get("max_items_per_run", DEFAULT_MAX_ITEMS_PER_RUN)
        if not isinstance(max_items, int) or max_items <= 0:
            raise ConnectorConfigError("max_items_per_run must be a positive integer.")
        config["parameters"] = parameters
        return config

    def _parameter_url(self, path):
        return f"{API_BASE_URL}/parameter/{path.replace('.', '/')}"

    def _fetch_parameter(self, path, timeout, max_response_bytes):
        response = http_retry.request_with_retries(
            "get", self._parameter_url(path), ConnectorFetchError,
            max_response_bytes=max_response_bytes, timeout=timeout,
        )
        try:
            return response.json()
        except ValueError as exc:
            raise ConnectorFetchError(
                f"OpenFisca response for {path!r} was not valid JSON."
            ) from exc

    def fetch(self, cursor, limit=100):
        config = self.validate_configuration()
        # EN: config["parameters"] is already resolved (default applied
        # if the key was absent) by validate_configuration() — no need to
        # repeat that fallback here.
        # FR : config["parameters"] est déjà résolu (valeur par défaut
        # appliquée si la clé était absente) par validate_configuration()
        # — inutile de répéter ce repli ici.
        parameters = config["parameters"]
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
        next_cursor_data = dict(cursor_data)

        items = []
        item_errors = []
        for path in parameters:
            try:
                item = self._process_parameter(
                    path, cursor_data.get(path), timeout, max_response_bytes,
                    next_cursor_data,
                )
                if item is not None:
                    items.append(item)
            except Exception as exc:  # noqa: BLE001 - one bad parameter must not break the run
                item_errors.append({"title": path, "error": str(exc)})

        items = items[:max_items]

        diagnostics = {
            "status": "ok",
            "watched_parameter_count": len(parameters),
            "returned_item_count": len(items),
            "item_errors": item_errors,
        }
        return FetchResult(
            items=items, next_cursor=json.dumps(next_cursor_data),
            diagnostics=diagnostics,
        )

    def _process_parameter(self, path, last_seen_date, timeout, max_response_bytes,
                            next_cursor_data):
        payload = self._fetch_parameter(path, timeout, max_response_bytes)
        values = payload.get("values")
        if not isinstance(values, dict):
            # EN: A "brackets" (scale/bareme) parameter, or an unexpected
            # shape — never force-parsed, see the module docstring.
            # FR : Un paramètre "brackets" (barème), ou une forme
            # inattendue — jamais forcé, voir la docstring de module.
            raise ConnectorFetchError(
                f"{path!r} has no 'values' key (likely a scale/bareme "
                f"parameter, not a simple scalar) — skipped."
            )

        sorted_dates = sorted(values)
        if not sorted_dates:
            return None

        if last_seen_date is None:
            # EN: First run for this parameter: establish a baseline with
            # only the current (most recent) value — never backfill the
            # full history (some parameters have 50+ years of entries).
            # FR : Première exécution pour ce paramètre : établit une
            # base avec uniquement la valeur actuelle (la plus récente) —
            # ne rétro-importe jamais l'historique complet (certains
            # paramètres ont plus de 50 ans d'entrées).
            new_dates = [sorted_dates[-1]]
        else:
            new_dates = [d for d in sorted_dates if d > last_seen_date]

        next_cursor_data[path] = sorted_dates[-1]
        if not new_dates:
            return None

        # EN: Only ever surface the latest new date as one candidate per
        # run — a burst of several historical changes in one run is not
        # expected in practice (this cursor logic runs at most once per
        # scheduled fetch), and keeping it to one avoids ambiguity about
        # which date's title becomes the document title.
        # FR : Ne fait remonter que la date la plus récente comme un seul
        # candidat par exécution — une rafale de plusieurs changements
        # historiques en une seule exécution n'est pas attendue en
        # pratique (cette logique de curseur tourne au plus une fois par
        # récupération planifiée), et s'en tenir à une seule évite toute
        # ambiguïté sur le titre du document à retenir.
        effective_date = new_dates[-1]
        value = values[effective_date]
        metadata = payload.get("metadata") or {}
        reference = (metadata.get("reference") or {}).get(effective_date) or {}
        official_journal_date = (metadata.get("official_journal_date") or {}).get(effective_date)
        short_label = metadata.get("short_label") or payload.get("description") or path
        unit = metadata.get("unit") or ""
        reference_title = reference.get("title")
        reference_href = reference.get("href")

        url = reference_href or self._parameter_url(path)
        title = reference_title or f"{short_label} — nouvelle valeur au {effective_date}"
        plain_text = (
            f"Le paramètre « {short_label} » (OpenFisca : {path}) passe à "
            f"{value} {unit} à compter du {effective_date}."
        )
        if reference_title:
            plain_text += f" Référence : {reference_title}."

        return CandidateItem(
            source_url=url,
            canonical_url=url,
            title=title,
            external_id=f"{path}#{effective_date}",
            plain_text=plain_text,
            published_at=_parse_iso_date(official_journal_date or effective_date),
            content_type="text/plain",
            language="fr_FR",
            source_metadata={
                "document_type": _guess_document_type(reference_title),
                "openfisca_parameter_path": path,
                "openfisca_value": value,
                "openfisca_unit": unit,
                "openfisca_effective_date": effective_date,
            },
        )
