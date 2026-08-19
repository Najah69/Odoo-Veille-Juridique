"""OpenFisca connector tests. Every test mocks requests.get at
services.http_retry (the connector delegates its HTTP calls there): no
test in this file reaches the network.

FR : Tests du connecteur OpenFisca. Chaque test mocke requests.get au
niveau de services.http_retry (le connecteur y délègue ses appels HTTP) :
aucun test de ce fichier n'atteint le réseau.
"""
import json as jsonlib
from unittest.mock import patch

from ..services.base_connector import ConnectorConfigError, ConnectorFetchError
from ..services.openfisca_connector import DEFAULT_PARAMETERS, OpenFiscaConnector
from .common import LegalWatchTransactionCase

_HTTP_GET = "odoo.addons.legal_knowledge_watch.services.http_retry.requests.get"

_SMIC_PAYLOAD = {
    "id": "marche_travail.salaire_minimum.smic.smic_b_horaire",
    "description": "Smic brut (horaire)",
    "source": "https://github.com/openfisca/openfisca-france",
    "values": {"2024-11-01": 11.88, "2026-01-01": 12.02, "2026-06-01": 12.31},
    "metadata": {
        "short_label": "Smic horaire brut",
        "unit": "currency-EUR",
        "official_journal_date": {"2026-06-01": "2026-05-22"},
        "reference": {
            "2026-06-01": {"title": "Arrêté du 22 mai 2026 relatif au relèvement du salaire minimum de croissance"},
        },
    },
}

_PSS_PAYLOAD = {
    "id": "prelevements_sociaux.pss.plafond_securite_sociale_mensuel",
    "description": "Plafond de la Sécurité sociale (mensuel)",
    "source": "https://github.com/openfisca/openfisca-france",
    "values": {"2025-01-01": 3925, "2026-01-01": 4005},
    "metadata": {
        "short_label": "PSS mensuel",
        "unit": "currency-EUR",
        "official_journal_date": {"2026-01-01": "2025-12-22"},
        "reference": {
            "2026-01-01": {
                "title": "Arrêté du 22/12/2025",
                "href": "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000053143451",
            },
        },
    },
}


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {}
        self.content = jsonlib.dumps(json_data or {}).encode("utf-8")
        self.text = self.content.decode("utf-8")

    def json(self):
        if self._json_data is None:
            raise ValueError("no JSON")
        return self._json_data


class TestOpenFiscaConnectorValidation(LegalWatchTransactionCase):
    def _make_watch(self, **config_overrides):
        config = dict(config_overrides)
        return self.env["legal.watch"].create({
            "name": "OpenFisca Test Watch",
            "source_id": self.source.id,
            "connector_code": "openfisca",
            "configuration_json": jsonlib.dumps(config),
        })

    def test_missing_parameters_falls_back_to_defaults(self):
        watch = self._make_watch()
        config = OpenFiscaConnector(watch, logger=None).validate_configuration()
        self.assertEqual(config.get("parameters") or DEFAULT_PARAMETERS, DEFAULT_PARAMETERS)

    def test_empty_parameters_list_raises(self):
        watch = self._make_watch(parameters=[])
        with self.assertRaises(ConnectorConfigError):
            OpenFiscaConnector(watch, logger=None).validate_configuration()

    def test_non_list_parameters_raises(self):
        watch = self._make_watch(parameters="not-a-list")
        with self.assertRaises(ConnectorConfigError):
            OpenFiscaConnector(watch, logger=None).validate_configuration()

    def test_non_string_entry_raises(self):
        watch = self._make_watch(parameters=["ok.path", 42])
        with self.assertRaises(ConnectorConfigError):
            OpenFiscaConnector(watch, logger=None).validate_configuration()

    def test_custom_parameters_override_defaults(self):
        watch = self._make_watch(parameters=["custom.path.only"])
        config = OpenFiscaConnector(watch, logger=None).validate_configuration()
        self.assertEqual(config["parameters"], ["custom.path.only"])


class TestOpenFiscaConnectorFetch(LegalWatchTransactionCase):
    def _make_watch(self, **config_overrides):
        config = {"parameters": [
            "marche_travail.salaire_minimum.smic.smic_b_horaire",
            "prelevements_sociaux.pss.plafond_securite_sociale_mensuel",
        ]}
        config.update(config_overrides)
        return self.env["legal.watch"].create({
            "name": "OpenFisca Test Watch",
            "source_id": self.source.id,
            "connector_code": "openfisca",
            "configuration_json": jsonlib.dumps(config),
        })

    @patch(_HTTP_GET)
    def test_first_run_returns_only_latest_value_per_parameter(self, mock_get):
        mock_get.side_effect = [
            _FakeResponse(200, _SMIC_PAYLOAD),
            _FakeResponse(200, _PSS_PAYLOAD),
        ]
        result = OpenFiscaConnector(self._make_watch(), logger=None).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 2)
        smic_item = next(i for i in result.items if "smic" in i.external_id)
        self.assertEqual(smic_item.external_id, "marche_travail.salaire_minimum.smic.smic_b_horaire#2026-06-01")
        self.assertIn("Arrêté du 22 mai 2026", smic_item.title)
        # EN: SMIC's reference has no href -> falls back to the API URL.
        # FR : La référence du SMIC n'a pas de href -> repli sur l'URL de l'API.
        self.assertTrue(smic_item.source_url.startswith("https://api.fr.openfisca.org/latest/parameter/"))
        self.assertEqual(smic_item.source_metadata["document_type"], "order")

        pss_item = next(i for i in result.items if "pss" in i.external_id)
        # EN: PSS's reference has a real href -> used directly.
        # FR : La référence du PSS a un vrai href -> utilisé directement.
        self.assertEqual(pss_item.source_url, "https://www.legifrance.gouv.fr/jorf/id/JORFTEXT000053143451")

        cursor_data = jsonlib.loads(result.next_cursor)
        self.assertEqual(cursor_data["marche_travail.salaire_minimum.smic.smic_b_horaire"], "2026-06-01")
        self.assertEqual(cursor_data["prelevements_sociaux.pss.plafond_securite_sociale_mensuel"], "2026-01-01")

    @patch(_HTTP_GET)
    def test_rerun_with_up_to_date_cursor_returns_nothing_new(self, mock_get):
        mock_get.side_effect = [
            _FakeResponse(200, _SMIC_PAYLOAD),
            _FakeResponse(200, _PSS_PAYLOAD),
        ]
        cursor = jsonlib.dumps({
            "marche_travail.salaire_minimum.smic.smic_b_horaire": "2026-06-01",
            "prelevements_sociaux.pss.plafond_securite_sociale_mensuel": "2026-01-01",
        })
        result = OpenFiscaConnector(self._make_watch(), logger=None).fetch(cursor=cursor, limit=10)
        self.assertEqual(result.items, [])

    @patch(_HTTP_GET)
    def test_rerun_with_stale_cursor_returns_only_the_new_date(self, mock_get):
        mock_get.side_effect = [
            _FakeResponse(200, _SMIC_PAYLOAD),
            _FakeResponse(200, _PSS_PAYLOAD),
        ]
        cursor = jsonlib.dumps({
            "marche_travail.salaire_minimum.smic.smic_b_horaire": "2024-11-01",
            "prelevements_sociaux.pss.plafond_securite_sociale_mensuel": "2026-01-01",
        })
        result = OpenFiscaConnector(self._make_watch(), logger=None).fetch(cursor=cursor, limit=10)
        self.assertEqual(len(result.items), 1)
        self.assertIn("smic", result.items[0].external_id)
        self.assertEqual(result.items[0].source_metadata["openfisca_effective_date"], "2026-06-01")

    @patch(_HTTP_GET)
    def test_bracket_shaped_parameter_is_a_skipped_item_error(self, mock_get):
        bareme_payload = {"id": "impot_revenu.bareme", "brackets": [{"2026-01-01": {}}]}
        mock_get.side_effect = [
            _FakeResponse(200, bareme_payload),
            _FakeResponse(200, _PSS_PAYLOAD),
        ]
        watch = self._make_watch(parameters=[
            "impot_revenu.bareme_ir_depuis_1945.bareme",
            "prelevements_sociaux.pss.plafond_securite_sociale_mensuel",
        ])
        result = OpenFiscaConnector(watch, logger=None).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(result.diagnostics["item_errors"]), 1)
        self.assertIn("impot_revenu.bareme_ir_depuis_1945.bareme", result.diagnostics["item_errors"][0]["title"])

    @patch(_HTTP_GET)
    def test_404_on_one_parameter_does_not_abort_the_others(self, mock_get):
        mock_get.side_effect = [
            _FakeResponse(404),
            _FakeResponse(200, _PSS_PAYLOAD),
        ]
        result = OpenFiscaConnector(self._make_watch(), logger=None).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(result.diagnostics["item_errors"]), 1)

    @patch(_HTTP_GET)
    def test_max_items_per_run_is_respected(self, mock_get):
        mock_get.side_effect = [
            _FakeResponse(200, _SMIC_PAYLOAD),
            _FakeResponse(200, _PSS_PAYLOAD),
        ]
        result = OpenFiscaConnector(
            self._make_watch(max_items_per_run=1), logger=None,
        ).fetch(cursor=None, limit=10)
        self.assertEqual(len(result.items), 1)
