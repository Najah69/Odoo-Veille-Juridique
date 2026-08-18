import unittest

from ..services import enrichment_schema


def _valid_payload(**overrides):
    payload = {
        "schema_version": "1.0",
        "summary": "Résumé factuel du texte.",
        "themes": ["social"],
        "tags": ["cotisations"],
        "legal_nature": "decret",
        "effective_date": "2026-10-01",
        "affected_audiences": ["employeurs"],
        "obligations": [
            {"label": "Obligation potentielle", "source_excerpt": "Article 2",
             "certainty": "stated"},
        ],
        "business_relevance": {"score_delta": 10, "rationale": "Justification."},
        "requires_human_review": True,
        "uncertainties": ["Portée à confirmer."],
        "citations": [{"locator": "Article 2", "quote": "Extrait bref."}],
    }
    payload.update(overrides)
    return payload


class TestEnrichmentSchemaValidation(unittest.TestCase):
    def test_valid_payload_has_no_errors(self):
        self.assertEqual(enrichment_schema.validate(_valid_payload()), [])

    def test_non_dict_root_is_rejected(self):
        self.assertTrue(enrichment_schema.validate(["not", "a", "dict"]))
        self.assertTrue(enrichment_schema.validate("a string"))
        self.assertTrue(enrichment_schema.validate(None))

    def test_wrong_schema_version_is_rejected(self):
        errors = enrichment_schema.validate(_valid_payload(schema_version="2.0"))
        self.assertTrue(any("schema_version" in e for e in errors))

    def test_missing_summary_is_rejected(self):
        payload = _valid_payload()
        del payload["summary"]
        errors = enrichment_schema.validate(payload)
        self.assertTrue(any("summary" in e for e in errors))

    def test_missing_requires_human_review_is_rejected(self):
        payload = _valid_payload()
        del payload["requires_human_review"]
        errors = enrichment_schema.validate(payload)
        self.assertTrue(any("requires_human_review" in e for e in errors))

    def test_non_string_list_field_is_rejected(self):
        errors = enrichment_schema.validate(_valid_payload(themes="not-a-list"))
        self.assertTrue(any("themes" in e for e in errors))

    def test_legal_nature_null_is_valid(self):
        self.assertEqual(enrichment_schema.validate(_valid_payload(legal_nature=None)), [])

    def test_obligation_missing_certainty_is_rejected(self):
        payload = _valid_payload(obligations=[{"label": "x"}])
        errors = enrichment_schema.validate(payload)
        self.assertTrue(any("certainty" in e for e in errors))

    def test_obligation_invalid_certainty_value_is_rejected(self):
        payload = _valid_payload(
            obligations=[{"label": "x", "certainty": "definitely"}]
        )
        errors = enrichment_schema.validate(payload)
        self.assertTrue(any("certainty" in e for e in errors))

    def test_business_relevance_missing_fields_is_rejected(self):
        errors = enrichment_schema.validate(
            _valid_payload(business_relevance={"score_delta": 5})
        )
        self.assertTrue(any("rationale" in e for e in errors))

    def test_business_relevance_score_delta_must_be_int(self):
        errors = enrichment_schema.validate(
            _valid_payload(business_relevance={"score_delta": "high", "rationale": "x"})
        )
        self.assertTrue(any("score_delta" in e for e in errors))

    def test_citation_missing_quote_is_rejected(self):
        payload = _valid_payload(citations=[{"locator": "Article 1"}])
        errors = enrichment_schema.validate(payload)
        self.assertTrue(any("quote" in e for e in errors))

    def test_missing_obligations_field_entirely_is_rejected(self):
        payload = _valid_payload()
        del payload["obligations"]
        errors = enrichment_schema.validate(payload)
        self.assertTrue(any("obligations" in e for e in errors))
