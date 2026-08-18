import unittest
from types import SimpleNamespace

from ..services import relevance_service


def _rule(**overrides):
    defaults = dict(
        name="rule", rule_type="keyword", target_field="title",
        operator="contains", value="", effect="score", score_delta=0,
        tag_id=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


_CANDIDATE = {
    "title": "Décret relatif aux cotisations sociales",
    "plain_text": "Texte complet sur les cotisations sociales et la paie.",
    "authority": "DILA",
    "source_url": "https://exemple.gouv.example.org/decret-1",
    "canonical_url": "https://exemple.gouv.example.org/decret-1",
}


class TestEvaluateRules(unittest.TestCase):
    def test_score_rule_accumulates(self):
        rules = [
            _rule(effect="score", score_delta=15, value="cotisations"),
            _rule(effect="score", score_delta=20, value="Décret"),
        ]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertEqual(result["score"], 35)
        self.assertEqual(len(result["triggered"]), 2)

    def test_non_matching_score_rule_does_not_add(self):
        rules = [_rule(effect="score", score_delta=15, value="TVA")]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["triggered"], [])

    def test_tag_rule_collects_tag_id(self):
        rules = [_rule(effect="tag", value="cotisations", tag_id=SimpleNamespace(id=42))]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertEqual(result["tag_ids"], [42])

    def test_requires_review_rule_sets_flag(self):
        rules = [_rule(effect="requires_review", value="cotisations")]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertTrue(result["requires_review"])

    def test_exclude_rule_wins_over_include(self):
        rules = [
            _rule(effect="include", value="Décret"),
            _rule(effect="exclude", value="cotisations"),
        ]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertTrue(result["excluded"])

    def test_include_rule_excludes_when_none_match(self):
        rules = [_rule(effect="include", value="TVA")]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertTrue(result["excluded"])

    def test_include_rule_passes_when_matched(self):
        rules = [_rule(effect="include", value="cotisations")]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertFalse(result["excluded"])

    def test_no_rules_means_not_excluded(self):
        result = relevance_service.evaluate_rules([], _CANDIDATE)
        self.assertFalse(result["excluded"])
        self.assertEqual(result["score"], 0)

    def test_regex_operator(self):
        rules = [_rule(effect="score", score_delta=10, operator="matches",
                        target_field="title", value=r"^Décret.*sociales$")]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertEqual(result["score"], 10)

    def test_in_operator(self):
        rules = [_rule(effect="tag", operator="in", target_field="authority",
                        value="DILA, CNIL", tag_id=SimpleNamespace(id=7))]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertEqual(result["tag_ids"], [7])

    def test_not_in_operator(self):
        rules = [_rule(effect="score", score_delta=5, operator="not_in",
                        target_field="authority", value="URSSAF, CNIL")]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertEqual(result["score"], 5)

    def test_inactive_rule_type_ignored_gracefully(self):
        rules = [_rule(effect="score", rule_type="unsupported_type", score_delta=99)]
        result = relevance_service.evaluate_rules(rules, _CANDIDATE)
        self.assertEqual(result["score"], 0)
