"""Deterministic, explainable relevance rules — evaluated before any AI
involvement. See docs/connectors.md for the field/operator/effect contract.
"""
import re

_MATCHABLE_TARGET_FIELDS = ("title", "plain_text", "authority", "source_url", "canonical_url")
_MATCHABLE_RULE_TYPES = ("keyword", "regex", "source_field")


def _rule_matches(rule, candidate):
    value = str(candidate.get(rule.target_field) or "")
    pattern = rule.value or ""
    if rule.operator == "contains":
        return pattern.lower() in value.lower()
    if rule.operator == "equals":
        return value.strip().lower() == pattern.strip().lower()
    if rule.operator == "matches":
        try:
            return bool(re.search(pattern, value, re.IGNORECASE))
        except re.error:
            return False
    if rule.operator in ("in", "not_in"):
        options = [v.strip().lower() for v in pattern.split(",") if v.strip()]
        is_in = value.strip().lower() in options
        return is_in if rule.operator == "in" else not is_in
    return False


def evaluate_rules(rules, candidate):
    """rules: a legal.watch.rule recordset (already filtered to active).
    candidate: a plain dict with at least title/plain_text/authority/
    source_url/canonical_url keys.

    Returns a dict: {excluded, requires_review, score, tag_ids (list),
    triggered (list of rule names)}.
    """
    result = {
        "excluded": False,
        "included": False,
        "has_include_rules": False,
        "requires_review": False,
        "score": 0,
        "tag_ids": [],
        "triggered": [],
    }
    tag_ids = set()

    for rule in rules:
        if rule.rule_type not in _MATCHABLE_RULE_TYPES:
            continue
        if rule.target_field not in _MATCHABLE_TARGET_FIELDS:
            continue
        if rule.effect == "include":
            result["has_include_rules"] = True
        if not _rule_matches(rule, candidate):
            continue
        result["triggered"].append(rule.name)
        if rule.effect == "exclude":
            result["excluded"] = True
        elif rule.effect == "include":
            result["included"] = True
        elif rule.effect == "score":
            result["score"] += rule.score_delta
        elif rule.effect == "tag":
            if rule.tag_id:
                tag_ids.add(rule.tag_id.id)
        elif rule.effect == "requires_review":
            result["requires_review"] = True

    if result["has_include_rules"] and not result["included"]:
        result["excluded"] = True

    result["tag_ids"] = list(tag_ids)
    return result
