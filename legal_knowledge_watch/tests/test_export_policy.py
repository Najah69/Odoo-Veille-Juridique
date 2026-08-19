from .common import LegalWatchTransactionCase


class TestExportPolicyResolution(LegalWatchTransactionCase):
    def _approved_candidate(self, **overrides):
        overrides.setdefault(
            "canonical_url",
            f"https://exemple.gouv.example.org/{overrides.get('external_id', 'x')}",
        )
        return self._candidate(**overrides)

    def _approved_document(self, **overrides):
        document = self.env["legal.knowledge.document"]._ingest_candidate(
            self._approved_candidate(**overrides)
        )["document"]
        document.action_set_review()
        document.action_approve()
        return document

    def test_no_policy_configured_uses_phase4_default(self):
        document = self._approved_document(external_id="EXT-POLICY-1")
        allowed, reason = document._check_export_policy()
        self.assertTrue(allowed, reason)

    def test_no_policy_default_blocks_below_high_trust(self):
        low_source = self.env["legal.source"].create({
            "name": "Low Trust Source", "code": "low_trust_policy_test",
            "trust_level": "medium",
        })
        document = self._approved_document(source_id=low_source.id, external_id="EXT-POLICY-2")
        allowed, reason = document._check_export_policy()
        self.assertFalse(allowed)
        self.assertIn("trust_level", reason)

    def test_policy_lowering_trust_threshold_allows_medium(self):
        medium_source = self.env["legal.source"].create({
            "name": "Medium Trust Source", "code": "medium_trust_policy_test",
            "trust_level": "medium",
        })
        self.env["legal.export.policy"].create({
            "name": "Allow medium", "source_id": medium_source.id,
            "min_trust_level": "medium", "require_review_cleared": False,
        })
        document = self._approved_document(source_id=medium_source.id, external_id="EXT-POLICY-3")
        allowed, reason = document._check_export_policy()
        self.assertTrue(allowed, reason)

    def test_source_specific_policy_wins_over_global(self):
        self.env["legal.export.policy"].create({
            "name": "Global strict", "min_trust_level": "primary",
        })
        self.env["legal.export.policy"].create({
            "name": "This source lenient", "source_id": self.source.id,
            "min_trust_level": "low", "require_review_cleared": False,
        })
        # EN: self.source has trust_level='primary' by default (see
        # common.py) — use a lower one to actually distinguish the two
        # policies.
        # FR : self.source a trust_level='primary' par défaut (voir
        # common.py) — on utilise une valeur plus basse pour distinguer
        # réellement les deux politiques.
        self.source.trust_level = "low"
        document = self._approved_document(external_id="EXT-POLICY-4")
        allowed, reason = document._check_export_policy()
        # EN: source-specific (low) applies, not global (primary)
        # FR : la politique spécifique à la source (low) s'applique, pas
        # la politique globale (primary)
        self.assertTrue(allowed, reason)

    def test_require_review_cleared_blocks_when_needs_review_true(self):
        self.env["legal.export.policy"].create({
            "name": "Require clean review", "source_id": self.source.id,
            "min_trust_level": "low", "require_review_cleared": True,
        })
        document = self._approved_document(external_id="EXT-POLICY-5", needs_review=True)
        allowed, reason = document._check_export_policy()
        self.assertFalse(allowed)
        self.assertIn("review", reason)

    def test_min_relevance_score_blocks_low_score(self):
        self.env["legal.export.policy"].create({
            "name": "Score gate", "source_id": self.source.id,
            "min_trust_level": "low", "min_relevance_score": 50.0,
        })
        document = self._approved_document(external_id="EXT-POLICY-6", relevance_score=10.0)
        allowed, reason = document._check_export_policy()
        self.assertFalse(allowed)
        self.assertIn("relevance_score", reason)

    def test_max_text_length_blocks_long_text(self):
        self.env["legal.export.policy"].create({
            "name": "Length gate", "source_id": self.source.id,
            "min_trust_level": "low", "max_text_length": 10,
        })
        document = self._approved_document(
            external_id="EXT-POLICY-7",
            plain_text="Ce texte est largement plus long que dix caractères.",
        )
        allowed, reason = document._check_export_policy()
        self.assertFalse(allowed)
        self.assertIn("length", reason)

    def test_missing_canonical_url_blocks_unconditionally_even_with_lenient_policy(self):
        self.env["legal.export.policy"].create({
            "name": "Very lenient", "source_id": self.source.id,
            "min_trust_level": "low", "require_review_cleared": False,
        })
        document = self._approved_document(
            external_id="EXT-POLICY-8", canonical_url=False, source_url=False,
        )
        allowed, reason = document._check_export_policy()
        self.assertFalse(allowed)
        self.assertIn("canonical_url", reason)
