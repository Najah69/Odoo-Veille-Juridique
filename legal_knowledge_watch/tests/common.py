from odoo.tests.common import TransactionCase


class LegalWatchTransactionCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = cls.env["legal.source"].create({
            "name": "Test Official Source",
            "code": "test_official_source",
            "authority_type": "official",
            "trust_level": "primary",
        })
        cls.tag_social = cls.env["legal.tag"].create({"name": "Test Social"})

    def _candidate(self, **overrides):
        candidate = {
            "source_id": self.source.id,
            "title": "Décret de test",
            "plain_text": "Contenu de test suffisamment long pour être hashé.",
            "mime_type": "text/plain",
            "document_type": "manual",
            "language": "fr_FR",
            "tag_ids": [],
        }
        candidate.update(overrides)
        return candidate
