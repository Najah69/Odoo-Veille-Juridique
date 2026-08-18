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
