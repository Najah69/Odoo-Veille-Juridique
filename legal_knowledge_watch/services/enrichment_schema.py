"""Hand-rolled validator for the legal-enrichment-1.0 JSON Schema
(docs/legal-enrichment-schema-1.0.json) — no jsonschema dependency, to keep
external_dependencies minimal. Keep both files in sync if the schema
changes. A violation must never silently mutate document metadata: see
legal.document.enrichment / legal.ai.job for how a validation failure is
turned into a failed/needs_review state instead.

FR : Validateur maison pour le JSON Schema legal-enrichment-1.0
(docs/legal-enrichment-schema-1.0.json) — pas de dépendance jsonschema,
pour garder external_dependencies minimal. Garder les deux fichiers
synchronisés si le schéma change. Une violation ne doit jamais muter
silencieusement les métadonnées du document : voir
legal.document.enrichment / legal.ai.job pour la façon dont un échec de
validation est plutôt transformé en état failed/needs_review.
"""

SCHEMA_VERSION = "1.0"
SCHEMA_ID = "legal-enrichment-1.0"

_CERTAINTY_VALUES = {"stated", "inferred", "uncertain"}
_STRING_LIST_FIELDS = ("themes", "tags", "affected_audiences", "uncertainties")


def _is_string_list(value):
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def validate(data):
    """Return a list of human-readable errors; an empty list means valid.

    FR : Retourne une liste d'erreurs lisibles par un humain ; une liste
    vide signifie que les données sont valides.
    """
    if not isinstance(data, dict):
        return ["Root value must be a JSON object."]

    errors = []

    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {SCHEMA_VERSION!r}, got "
            f"{data.get('schema_version')!r}."
        )

    if not isinstance(data.get("summary"), str):
        errors.append("Missing or invalid field 'summary' (must be a string).")

    if not isinstance(data.get("requires_human_review"), bool):
        errors.append(
            "Missing or invalid field 'requires_human_review' (must be a boolean)."
        )

    for field_name in _STRING_LIST_FIELDS:
        if not _is_string_list(data.get(field_name)):
            errors.append(
                f"Missing or invalid field '{field_name}' (must be a list of strings)."
            )

    legal_nature = data.get("legal_nature")
    if legal_nature is not None and not isinstance(legal_nature, str):
        errors.append("Field 'legal_nature' must be a string or null.")

    effective_date = data.get("effective_date")
    if effective_date is not None and not isinstance(effective_date, str):
        errors.append("Field 'effective_date' must be a YYYY-MM-DD string or null.")

    obligations = data.get("obligations")
    if not isinstance(obligations, list):
        errors.append("Missing or invalid field 'obligations' (must be a list).")
    else:
        for index, obligation in enumerate(obligations):
            if not isinstance(obligation, dict):
                errors.append(f"obligations[{index}] must be an object.")
                continue
            if not isinstance(obligation.get("label"), str):
                errors.append(f"obligations[{index}].label must be a string.")
            if "source_excerpt" in obligation and not isinstance(
                obligation["source_excerpt"], str
            ):
                errors.append(f"obligations[{index}].source_excerpt must be a string.")
            if obligation.get("certainty") not in _CERTAINTY_VALUES:
                errors.append(
                    f"obligations[{index}].certainty must be one of "
                    f"{sorted(_CERTAINTY_VALUES)}."
                )

    business_relevance = data.get("business_relevance")
    if not isinstance(business_relevance, dict):
        errors.append("Missing or invalid field 'business_relevance' (must be an object).")
    else:
        score_delta = business_relevance.get("score_delta")
        if not isinstance(score_delta, int) or isinstance(score_delta, bool):
            errors.append("business_relevance.score_delta must be an integer.")
        if not isinstance(business_relevance.get("rationale"), str):
            errors.append("business_relevance.rationale must be a string.")

    citations = data.get("citations")
    if not isinstance(citations, list):
        errors.append("Missing or invalid field 'citations' (must be a list).")
    else:
        for index, citation in enumerate(citations):
            if not isinstance(citation, dict):
                errors.append(f"citations[{index}] must be an object.")
                continue
            if not isinstance(citation.get("locator"), str):
                errors.append(f"citations[{index}].locator must be a string.")
            if not isinstance(citation.get("quote"), str):
                errors.append(f"citations[{index}].quote must be a string.")

    return errors
