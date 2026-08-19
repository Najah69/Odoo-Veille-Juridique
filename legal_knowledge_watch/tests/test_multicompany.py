from .common import LegalWatchTransactionCase


class TestMultiCompanyIsolation(LegalWatchTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company_a = cls.env["res.company"].create({"name": "LKW Test Company A"})
        cls.company_b = cls.env["res.company"].create({"name": "LKW Test Company B"})
        watch_user_group = cls.env.ref("legal_knowledge_watch.group_legal_watch_user")
        cls.user_a = cls.env["res.users"].create({
            "name": "LKW User A",
            "login": "lkw_test_user_a",
            "company_id": cls.company_a.id,
            "company_ids": [(6, 0, [cls.company_a.id])],
            "groups_id": [(4, watch_user_group.id)],
        })
        cls.user_b = cls.env["res.users"].create({
            "name": "LKW User B",
            "login": "lkw_test_user_b",
            "company_id": cls.company_b.id,
            "company_ids": [(6, 0, [cls.company_b.id])],
            "groups_id": [(4, watch_user_group.id)],
        })
        cls.watch_a = cls.env["legal.watch"].create({
            "name": "Watch A",
            "source_id": cls.source.id,
            "company_id": cls.company_a.id,
        })

    def test_user_b_cannot_see_watch_of_company_a(self):
        watches = self.env["legal.watch"].with_user(self.user_b).search([])
        self.assertNotIn(self.watch_a.id, watches.ids)

    def test_user_a_can_see_own_company_watch(self):
        watches = self.env["legal.watch"].with_user(self.user_a).search([])
        self.assertIn(self.watch_a.id, watches.ids)

    def test_document_isolated_by_company(self):
        document = self.env["legal.knowledge.document"].create({
            "name": "Doc A",
            "source_id": self.source.id,
            "company_id": self.company_a.id,
            "external_id": "MC-001",
        })
        docs_for_b = self.env["legal.knowledge.document"].with_user(
            self.user_b
        ).search([("id", "=", document.id)])
        self.assertFalse(docs_for_b)

        docs_for_a = self.env["legal.knowledge.document"].with_user(
            self.user_a
        ).search([("id", "=", document.id)])
        self.assertTrue(docs_for_a)

    def test_ai_job_isolated_by_document_company(self):
        # company_id on legal.ai.job is a related field off document_id —
        # this confirms the record rule actually enforces it, not just
        # that the field is populated. See services/security.md P0 finding.
        document = self.env["legal.knowledge.document"].create({
            "name": "Doc A (AI job)",
            "source_id": self.source.id,
            "company_id": self.company_a.id,
            "external_id": "MC-002",
        })
        provider = self.env["legal.ai.provider"].create({
            "name": "MC Test Provider", "provider_type": "webhook",
            "base_url": "https://example.org", "auth_mode": "none",
        })
        job = self.env["legal.ai.job"].create({
            "document_id": document.id,
            "provider_id": provider.id,
            "job_type": "classify",
        })
        self.assertEqual(job.company_id, self.company_a)

        jobs_for_b = self.env["legal.ai.job"].with_user(
            self.user_b
        ).search([("id", "=", job.id)])
        self.assertFalse(jobs_for_b)

        jobs_for_a = self.env["legal.ai.job"].with_user(
            self.user_a
        ).search([("id", "=", job.id)])
        self.assertTrue(jobs_for_a)

    def test_enrichment_isolated_by_document_company(self):
        # Same rationale as above: output_json can hold excerpts of the
        # source document, so cross-company visibility here is the most
        # sensitive of the P0 gaps fixed in the security audit.
        document = self.env["legal.knowledge.document"].create({
            "name": "Doc A (enrichment)",
            "source_id": self.source.id,
            "company_id": self.company_a.id,
            "external_id": "MC-003",
        })
        enrichment = self.env["legal.document.enrichment"].create({
            "document_id": document.id,
            "kind": "summary",
            "output_json": "{}",
            "state": "success",
        })
        self.assertEqual(enrichment.company_id, self.company_a)

        enrichments_for_b = self.env["legal.document.enrichment"].with_user(
            self.user_b
        ).search([("id", "=", enrichment.id)])
        self.assertFalse(enrichments_for_b)

        enrichments_for_a = self.env["legal.document.enrichment"].with_user(
            self.user_a
        ).search([("id", "=", enrichment.id)])
        self.assertTrue(enrichments_for_a)
