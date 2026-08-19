"""RSS/Atom connector tests. Every test mocks requests.get: no test in this
file may reach the network.

FR : Tests du connecteur RSS/Atom. Chaque test mocke requests.get : aucun
test de ce fichier ne doit atteindre le réseau.
"""
import os
import unittest
from unittest.mock import patch

import requests

from ..services.base_connector import ConnectorConfigError, ConnectorFetchError
from ..services.rss_connector import RSSConnector

_FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _read_fixture(name):
    with open(os.path.join(_FIXTURES_DIR, name), "rb") as handle:
        return handle.read()


class _FakeWatch:
    def __init__(self, configuration_json):
        self.configuration_json = configuration_json


class _FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self._content = content
        self.headers = headers or {}

    def iter_content(self, chunk_size=65536):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def close(self):
        pass


def _connector(config_dict):
    import json
    return RSSConnector(_FakeWatch(json.dumps(config_dict)), logger=None)


class TestRSSConnectorValidation(unittest.TestCase):
    def test_missing_feed_url_raises(self):
        with self.assertRaises(ConnectorConfigError):
            _connector({}).validate_configuration()

    def test_non_http_feed_url_raises(self):
        with self.assertRaises(ConnectorConfigError):
            _connector({"feed_url": "ftp://example.org/feed"}).validate_configuration()

    def test_domain_not_allowed_raises(self):
        with self.assertRaises(ConnectorConfigError):
            _connector({
                "feed_url": "https://exemple.gouv.example.org/feed.rss",
                "allowed_domains": ["other-domain.example.org"],
            }).validate_configuration()

    def test_domain_allowed_passes(self):
        _connector({
            "feed_url": "https://exemple.gouv.example.org/feed.rss",
            "allowed_domains": ["exemple.gouv.example.org"],
        }).validate_configuration()

    def test_invalid_json_raises(self):
        connector = RSSConnector(_FakeWatch("not json"), logger=None)
        with self.assertRaises(ConnectorConfigError):
            connector.validate_configuration()


class TestRSSConnectorFetch(unittest.TestCase):
    def setUp(self):
        self.config = {"feed_url": "https://exemple.gouv.example.org/feed.rss"}

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_parses_rss_feed_and_skips_malformed_item(self, mock_get):
        mock_get.return_value = _FakeResponse(
            200, _read_fixture("rss_sample.xml"), headers={"ETag": "abc123"},
        )
        result = _connector(self.config).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 2)  # the 3rd item has no <link>
        self.assertEqual(result.diagnostics["raw_item_count"], 3)
        self.assertEqual(len(result.diagnostics["item_errors"]), 1)

        titles = [item.title for item in result.items]
        self.assertIn("Décret n° 2026-100 relatif aux tests", titles)

        with_date = next(i for i in result.items if "Décret" in i.title)
        self.assertIsNotNone(with_date.published_at)

        without_date = next(i for i in result.items if "Arrêté" in i.title)
        self.assertIsNone(without_date.published_at)

        self.assertIn('"etag": "abc123"', result.next_cursor)

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_parses_atom_feed(self, mock_get):
        mock_get.return_value = _FakeResponse(200, _read_fixture("atom_sample.xml"))
        result = _connector(self.config).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].title, "Circulaire de test Atom")
        self.assertEqual(
            result.items[0].source_url,
            "https://exemple.gouv.example.org/circulaire-atom-1",
        )

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_not_modified_returns_empty_result(self, mock_get):
        mock_get.return_value = _FakeResponse(304)
        import json
        cursor = json.dumps({"etag": "abc123", "last_modified": None})

        result = _connector(self.config).fetch(cursor=cursor, limit=10)

        self.assertEqual(result.items, [])
        self.assertEqual(result.next_cursor, cursor)
        self.assertEqual(result.diagnostics["status"], "not_modified")

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_sends_conditional_headers_from_cursor(self, mock_get):
        mock_get.return_value = _FakeResponse(200, _read_fixture("rss_sample.xml"))
        import json
        cursor = json.dumps({"etag": "cached-etag", "last_modified": "Mon, 01 Jan 2026 00:00:00 GMT"})

        _connector(self.config).fetch(cursor=cursor, limit=10)

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["headers"]["If-None-Match"], "cached-etag")
        self.assertEqual(
            kwargs["headers"]["If-Modified-Since"], "Mon, 01 Jan 2026 00:00:00 GMT",
        )

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_timeout_is_retried_then_succeeds(self, mock_get):
        mock_get.side_effect = [
            requests.exceptions.Timeout("slow"),
            _FakeResponse(200, _read_fixture("rss_sample.xml")),
        ]
        with patch("odoo.addons.legal_knowledge_watch.services.rss_connector.time.sleep"):
            result = _connector(self.config).fetch(cursor=None, limit=10)

        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(len(result.items), 2)

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_timeout_exhausts_retries_and_raises(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("always slow")
        with patch("odoo.addons.legal_knowledge_watch.services.rss_connector.time.sleep"):
            with self.assertRaises(ConnectorFetchError):
                _connector(self.config).fetch(cursor=None, limit=10)
        self.assertEqual(mock_get.call_count, 3)

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_http_500_is_retried_then_raises(self, mock_get):
        mock_get.return_value = _FakeResponse(500, b"error")
        with patch("odoo.addons.legal_knowledge_watch.services.rss_connector.time.sleep"):
            with self.assertRaises(ConnectorFetchError):
                _connector(self.config).fetch(cursor=None, limit=10)
        self.assertEqual(mock_get.call_count, 3)

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_http_404_is_not_retried(self, mock_get):
        mock_get.return_value = _FakeResponse(404, b"not found")
        with self.assertRaises(ConnectorFetchError):
            _connector(self.config).fetch(cursor=None, limit=10)
        self.assertEqual(mock_get.call_count, 1)

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_response_over_size_limit_raises(self, mock_get):
        big_content = b"x" * 1000
        mock_get.return_value = _FakeResponse(200, big_content)
        config = dict(self.config, max_response_bytes=100)
        with self.assertRaises(ConnectorFetchError):
            _connector(config).fetch(cursor=None, limit=10)

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_feed_url_pointing_at_loopback_ip_is_rejected(self, mock_get):
        # EN: No network call must happen at all: assert_public_host()
        # rejects the literal loopback IP before requests.get is ever
        # called.
        # FR : Aucun appel réseau ne doit avoir lieu : assert_public_host()
        # rejette l'IP loopback littérale avant même que requests.get ne
        # soit appelé.
        config = {"feed_url": "http://127.0.0.1/feed.rss"}
        with self.assertRaises(ConnectorFetchError):
            _connector(config).fetch(cursor=None, limit=10)
        mock_get.assert_not_called()

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_feed_url_pointing_at_link_local_metadata_ip_is_rejected(self, mock_get):
        config = {"feed_url": "http://169.254.169.254/feed.rss"}
        with self.assertRaises(ConnectorFetchError):
            _connector(config).fetch(cursor=None, limit=10)
        mock_get.assert_not_called()

    @patch("odoo.addons.legal_knowledge_watch.services.rss_connector.requests.get")
    def test_redirect_is_not_followed(self, mock_get):
        mock_get.return_value = _FakeResponse(
            302, headers={"Location": "http://127.0.0.1/internal"},
        )
        with self.assertRaises(ConnectorFetchError):
            _connector(self.config).fetch(cursor=None, limit=10)
        # EN: A single attempt: a redirect is a hard failure, never
        # retried.
        # FR : Une seule tentative : une redirection est un échec dur,
        # jamais réessayée.
        self.assertEqual(mock_get.call_count, 1)
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["allow_redirects"], False)
