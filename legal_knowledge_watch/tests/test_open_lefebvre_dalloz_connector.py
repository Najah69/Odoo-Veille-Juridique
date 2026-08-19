"""Open Lefebvre Dalloz connector tests. Every test mocks requests.get at
services.http_retry: no test in this file may reach the network.

FR : Tests du connecteur Open Lefebvre Dalloz. Chaque test mocke
requests.get au niveau de services.http_retry : aucun test de ce fichier
ne doit atteindre le réseau.
"""
import json as jsonlib
import os
from unittest.mock import patch

from ..services.base_connector import ConnectorConfigError, ConnectorFetchError
from ..services.open_lefebvre_dalloz_connector import OpenLefebvreDallozConnector
from .common import LegalWatchTransactionCase

_HTTP_GET = "odoo.addons.legal_knowledge_watch.services.http_retry.requests.get"
_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _read_fixture(name):
    with open(os.path.join(_FIXTURES_DIR, name), "r", encoding="utf-8") as handle:
        return handle.read()


class _FakeResponse:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = headers or {}


_SAMPLE_HTML = _read_fixture("open_lefebvre_dalloz_sample.html")


class TestOpenLefebvreDallozConnectorValidation(LegalWatchTransactionCase):
    def _make_watch(self, **config_overrides):
        return self.env["legal.watch"].create({
            "name": "Lefebvre Dalloz Test Watch",
            "source_id": self.source.id,
            "connector_code": "open_lefebvre_dalloz",
            "configuration_json": jsonlib.dumps(config_overrides),
        })

    def test_default_config_is_valid(self):
        watch = self._make_watch()
        OpenLefebvreDallozConnector(watch, logger=None).validate_configuration()

    def test_non_positive_max_items_raises(self):
        watch = self._make_watch(max_items_per_run=0)
        with self.assertRaises(ConnectorConfigError):
            OpenLefebvreDallozConnector(watch, logger=None).validate_configuration()


class TestOpenLefebvreDallozConnectorFetch(LegalWatchTransactionCase):
    def _make_watch(self, **config_overrides):
        return self.env["legal.watch"].create({
            "name": "Lefebvre Dalloz Test Watch",
            "source_id": self.source.id,
            "connector_code": "open_lefebvre_dalloz",
            "configuration_json": jsonlib.dumps(config_overrides),
        })

    @patch(_HTTP_GET)
    def test_first_run_returns_all_fixture_items(self, mock_get):
        mock_get.return_value = _FakeResponse(200, _SAMPLE_HTML)
        result = OpenLefebvreDallozConnector(self._make_watch(), logger=None).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 3)
        first = result.items[0]
        self.assertEqual(first.external_id, "item-1-uuid")
        self.assertEqual(first.title, "Premier item de test")
        self.assertEqual(
            first.source_url,
            "https://open.lefebvre-dalloz.fr/actualites/droit-social/premier-item-de-test_item-1-uuid",
        )
        self.assertEqual(first.plain_text, "Résumé du premier item de test.")
        self.assertEqual(first.source_metadata["matter"], "Droit social")

        # EN: Empty summary falls back to the title.
        # FR : Un résumé vide retombe sur le titre.
        second = result.items[1]
        self.assertEqual(second.plain_text, second.title)

        cursor_data = jsonlib.loads(result.next_cursor)
        self.assertEqual(cursor_data["last_seen_date"], "2026-07-31T02:00:00Z")

    @patch(_HTTP_GET)
    def test_cursor_filters_out_already_seen_items(self, mock_get):
        mock_get.return_value = _FakeResponse(200, _SAMPLE_HTML)
        cursor = jsonlib.dumps({"last_seen_date": "2026-07-27T02:00:00Z"})
        result = OpenLefebvreDallozConnector(self._make_watch(), logger=None).fetch(cursor=cursor, limit=10)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].external_id, "item-1-uuid")

    @patch(_HTTP_GET)
    def test_cursor_at_latest_date_returns_nothing_new(self, mock_get):
        mock_get.return_value = _FakeResponse(200, _SAMPLE_HTML)
        cursor = jsonlib.dumps({"last_seen_date": "2026-07-31T02:00:00Z"})
        result = OpenLefebvreDallozConnector(self._make_watch(), logger=None).fetch(cursor=cursor, limit=10)
        self.assertEqual(result.items, [])

    @patch(_HTTP_GET)
    def test_max_items_per_run_is_respected(self, mock_get):
        mock_get.return_value = _FakeResponse(200, _SAMPLE_HTML)
        result = OpenLefebvreDallozConnector(
            self._make_watch(max_items_per_run=1), logger=None,
        ).fetch(cursor=None, limit=10)
        self.assertEqual(len(result.items), 1)

    @patch(_HTTP_GET)
    def test_missing_next_data_script_raises(self, mock_get):
        mock_get.return_value = _FakeResponse(200, "<html><body>No data here.</body></html>")
        with self.assertRaises(ConnectorFetchError):
            OpenLefebvreDallozConnector(self._make_watch(), logger=None).fetch(cursor=None, limit=10)

    @patch(_HTTP_GET)
    def test_malformed_next_data_json_raises(self, mock_get):
        html = '<script id="__NEXT_DATA__" type="application/json">{not valid json</script>'
        mock_get.return_value = _FakeResponse(200, html)
        with self.assertRaises(ConnectorFetchError):
            OpenLefebvreDallozConnector(self._make_watch(), logger=None).fetch(cursor=None, limit=10)

    @patch(_HTTP_GET)
    def test_unexpected_data_shape_raises(self, mock_get):
        html = '<script id="__NEXT_DATA__" type="application/json">{"props": {"pageProps": {}}}</script>'
        mock_get.return_value = _FakeResponse(200, html)
        with self.assertRaises(ConnectorFetchError):
            OpenLefebvreDallozConnector(self._make_watch(), logger=None).fetch(cursor=None, limit=10)

    @patch(_HTTP_GET)
    def test_entry_missing_href_is_a_skipped_item_error(self, mock_get):
        html = (
            '<script id="__NEXT_DATA__" type="application/json">'
            '{"props": {"pageProps": {"page": {"actualites": ['
            '{"id": "bad-1", "title": "Sans href", "date": "2026-07-31T02:00:00Z"},'
            '{"id": "item-1-uuid", "title": "OK", "href": "/actualites/x_item-1-uuid",'
            ' "date": "2026-07-30T02:00:00Z", "summary": "ok"}'
            ']}}}}</script>'
        )
        mock_get.return_value = _FakeResponse(200, html)
        result = OpenLefebvreDallozConnector(self._make_watch(), logger=None).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(len(result.diagnostics["item_errors"]), 1)

    @patch(_HTTP_GET)
    def test_redirect_is_not_followed(self, mock_get):
        mock_get.return_value = _FakeResponse(302, "", headers={"Location": "http://127.0.0.1/internal"})
        with self.assertRaises(ConnectorFetchError):
            OpenLefebvreDallozConnector(self._make_watch(), logger=None).fetch(cursor=None, limit=10)
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["allow_redirects"], False)
