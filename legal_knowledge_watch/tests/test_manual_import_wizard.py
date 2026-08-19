import base64

from odoo.exceptions import AccessError, UserError

from .common import LegalWatchTransactionCase


class TestManualImportWizard(LegalWatchTransactionCase):
    def test_plain_user_can_import_but_not_create_version_directly(self):
        # Phase 7 security audit: legal.document.version write/create was
        # removed from the User group ACL (a plain user could otherwise
        # forge a version via raw ORM/RPC, bypassing hashing/dedup/history
        # rules). The wizard keeps working because
        # create_or_update_from_candidate() now sudo()s the version
        # create/write — this test proves both halves actually hold.
        user = self.env["res.users"].create({
            "name": "LKW Plain User",
            "login": "lkw_test_plain_user",
            "groups_id": [(4, self.env.ref("legal_knowledge_watch.group_legal_watch_user").id)],
        })

        wizard = self.env["legal.manual.import.wizard"].with_user(user).create({
            "import_mode": "text",
            "title": "Import par utilisateur restreint",
            "source_id": self.source.id,
            "plain_text_input": "Texte saisi par un utilisateur non privilégié.",
        })
        action = wizard.action_import()
        document = self.env["legal.knowledge.document"].browse(action["res_id"])
        self.assertEqual(document.version_count, 1)

        with self.assertRaises(AccessError):
            self.env["legal.document.version"].with_user(user).create({
                "document_id": document.id,
                "sequence": 99,
                "content_hash": "forged",
                "plain_text": "Contenu forgé directement via l'ORM.",
                "is_current": True,
            })

    def test_import_pasted_text_creates_document(self):
        wizard = self.env["legal.manual.import.wizard"].create({
            "import_mode": "text",
            "title": "Note interne de test",
            "source_id": self.source.id,
            "plain_text_input": "Texte saisi manuellement pour le test.",
        })
        action = wizard.action_import()
        document = self.env["legal.knowledge.document"].browse(action["res_id"])

        self.assertEqual(document.status, "review")  # default review_state_choice
        self.assertEqual(document.version_count, 1)
        self.assertTrue(document.current_version_id.attachment_id)

    def test_import_html_file_strips_tags(self):
        html = "<html><body><h1>Titre</h1><p>Contenu HTML de test.</p></body></html>"
        wizard = self.env["legal.manual.import.wizard"].create({
            "import_mode": "file",
            "title": "Fichier HTML",
            "source_id": self.source.id,
            "attachment_data": base64.b64encode(html.encode("utf-8")),
            "attachment_filename": "test.html",
        })
        action = wizard.action_import()
        document = self.env["legal.knowledge.document"].browse(action["res_id"])

        self.assertIn("Titre", document.current_version_text)
        self.assertIn("Contenu HTML de test.", document.current_version_text)
        self.assertNotIn("<h1>", document.current_version_text)

    def test_reimporting_same_text_is_flagged_duplicate(self):
        vals = {
            "import_mode": "text",
            "title": "Doublon",
            "source_id": self.source.id,
            "plain_text_input": "Contenu identique importé deux fois.",
        }
        wizard_one = self.env["legal.manual.import.wizard"].create(vals)
        action_one = wizard_one.action_import()

        wizard_two = self.env["legal.manual.import.wizard"].create(vals)
        action_two = wizard_two.action_import()

        self.assertEqual(action_one["res_id"], action_two["res_id"])
        document = self.env["legal.knowledge.document"].browse(action_one["res_id"])
        self.assertEqual(document.version_count, 1)

    def test_unsupported_extension_raises_user_error(self):
        wizard = self.env["legal.manual.import.wizard"].create({
            "import_mode": "file",
            "title": "Mauvais format",
            "source_id": self.source.id,
            "attachment_data": base64.b64encode(b"binary junk"),
            "attachment_filename": "test.exe",
        })
        with self.assertRaises(UserError):
            wizard.action_import()

    def test_empty_text_mode_raises_user_error(self):
        wizard = self.env["legal.manual.import.wizard"].create({
            "import_mode": "text",
            "title": "Vide",
            "source_id": self.source.id,
            "plain_text_input": "   ",
        })
        with self.assertRaises(UserError):
            wizard.action_import()
