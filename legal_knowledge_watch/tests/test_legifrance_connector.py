"""Légifrance/PISTE connector tests. Every test mocks requests.post (both
the OAuth token call and the search/consult calls): no test in this file
reaches the network. Fixtures are inline dicts shaped per
docs/legifrance-piste.md's confirmed schema, not separate files (see that
document for why).
"""
import json as jsonlib
import os
from unittest.mock import patch

import requests

from ..services.base_connector import ConnectorConfigError, ConnectorFetchError
from ..services.legifrance_connector import LegifranceConnector
from ..services.piste_oauth_client import PisteOAuthTokenError, PisteOAuthClient
from .common import LegalWatchTransactionCase

_TOKEN_URL = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
_TOKEN_PATCH = "odoo.addons.legal_knowledge_watch.services.piste_oauth_client.requests.post"
_API_PATCH = "odoo.addons.legal_knowledge_watch.services.legifrance_connector.requests.post"

SEARCH_RESPONSE_FIXTURE = {
    "results": [
        {
            "titles": [{"id": "LEGITEXT000012345678", "title": "Décret n° 2026-100 relatif aux tests"}],
            "nature": "DECRET",
        },
        {
            "titles": [{"id": "LEGITEXT000087654321", "title": "Arrêté du 1er janvier 2026"}],
            "nature": "ARRETE",
        },
    ],
    "totalResultNumber": 2,
}

CONSULT_RESPONSE_FIXTURE = {
    "id": "LEGITEXT000012345678_01-01-2026",
    "title": "Décret n° 2026-100 relatif aux tests",
    "dateParution": "2026-01-01T00:00:00.000+0000",
    "articles": [
        {"id": "LEGIARTI0001", "num": "1", "content": "<p>Contenu de l'article 1.</p>"},
    ],
    "sections": [
        {
            "id": "LEGISCTA0001", "title": "Titre I",
            "articles": [{"id": "LEGIARTI0002", "num": "2", "content": "<p>Contenu de l'article 2.</p>"}],
            "sections": [],
        },
    ],
}


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text or jsonlib.dumps(self._json_data)
        self.ok = 200 <= status_code < 300
        self.headers = headers or {}
        self.content = self.text.encode("utf-8")

    def json(self):
        return self._json_data


def _token_response(status_code=200, access_token="fake-token", expires_in=600):
    if status_code != 200:
        return _FakeResponse(status_code, text="error")
    return _FakeResponse(200, {"access_token": access_token, "expires_in": expires_in})


class TestPisteOAuthClient(LegalWatchTransactionCase):
    def test_get_token_success(self):
        with patch(_TOKEN_PATCH, return_value=_token_response()):
            client = PisteOAuthClient("id", "secret", "sandbox")
            token = client.get_token()
        self.assertEqual(token, "fake-token")

    def test_get_token_reused_before_expiry(self):
        with patch(_TOKEN_PATCH, return_value=_token_response()) as mock_post:
            client = PisteOAuthClient("id", "secret", "sandbox")
            client.get_token()
            client.get_token()
        self.assertEqual(mock_post.call_count, 1)

    def test_get_token_401_raises_without_leaking_secret(self):
        with patch(_TOKEN_PATCH, return_value=_token_response(401)):
            client = PisteOAuthClient("id", "super-secret-value", "sandbox")
            with self.assertRaises(PisteOAuthTokenError) as ctx:
                client.get_token()
        self.assertNotIn("super-secret-value", str(ctx.exception))

    def test_get_token_timeout_raises(self):
        with patch(_TOKEN_PATCH, side_effect=requests.exceptions.Timeout("slow")):
            client = PisteOAuthClient("id", "secret", "sandbox")
            with self.assertRaises(PisteOAuthTokenError):
                client.get_token()

    def test_get_token_missing_access_token_raises(self):
        with patch(_TOKEN_PATCH, return_value=_FakeResponse(200, {"expires_in": 600})):
            client = PisteOAuthClient("id", "secret", "sandbox")
            with self.assertRaises(PisteOAuthTokenError):
                client.get_token()

    def test_get_token_redirect_is_not_followed(self):
        # A followed redirect would send client_secret to whatever host it
        # points to — must be a hard failure, and allow_redirects=False
        # must actually be passed to requests.post.
        redirect_response = _FakeResponse(302, headers={"Location": "http://evil.example/"})
        with patch(_TOKEN_PATCH, return_value=redirect_response) as mock_post:
            client = PisteOAuthClient("id", "secret", "sandbox")
            with self.assertRaises(PisteOAuthTokenError):
                client.get_token()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["allow_redirects"], False)


class TestLegifranceConnectorValidation(LegalWatchTransactionCase):
    def _make_watch(self, configuration_json):
        return self.env["legal.watch"].create({
            "name": "Legifrance Test Watch",
            "source_id": self.source.id,
            "connector_code": "legifrance",
            "configuration_json": jsonlib.dumps(configuration_json),
        })

    def test_missing_keywords_raises(self):
        watch = self._make_watch({"environment": "sandbox"})
        with self.assertRaises(ConnectorConfigError):
            LegifranceConnector(watch, logger=None).validate_configuration()

    def test_invalid_environment_raises(self):
        watch = self._make_watch({"environment": "prod", "keywords": ["test"]})
        with self.assertRaises(ConnectorConfigError):
            LegifranceConnector(watch, logger=None).validate_configuration()

    def test_unknown_nature_raises(self):
        watch = self._make_watch({"keywords": ["test"], "natures": ["NOT_A_NATURE"]})
        with self.assertRaises(ConnectorConfigError):
            LegifranceConnector(watch, logger=None).validate_configuration()

    def test_missing_credentials_raises_without_revealing_config(self):
        watch = self._make_watch({"keywords": ["test"]})
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LKW_LEGIFRANCE_CLIENT_ID", None)
            os.environ.pop("LKW_LEGIFRANCE_CLIENT_SECRET", None)
            with self.assertRaises(ConnectorConfigError):
                LegifranceConnector(watch, logger=None).validate_configuration()

    def test_valid_configuration_with_env_credentials_passes(self):
        watch = self._make_watch({"keywords": ["cotisations"]})
        with patch.dict(os.environ, {
            "LKW_LEGIFRANCE_CLIENT_ID": "id", "LKW_LEGIFRANCE_CLIENT_SECRET": "secret",
        }):
            LegifranceConnector(watch, logger=None).validate_configuration()


class TestLegifranceConnectorFetch(LegalWatchTransactionCase):
    def _make_watch(self, **config_overrides):
        config = {"environment": "sandbox", "keywords": ["cotisations"]}
        config.update(config_overrides)
        return self.env["legal.watch"].create({
            "name": "Legifrance Test Watch",
            "source_id": self.source.id,
            "connector_code": "legifrance",
            "configuration_json": jsonlib.dumps(config),
        })

    def _env(self):
        return patch.dict(os.environ, {
            "LKW_LEGIFRANCE_CLIENT_ID": "id", "LKW_LEGIFRANCE_CLIENT_SECRET": "secret",
        })

    def test_fetch_returns_candidates_with_full_text_and_document_type(self):
        watch = self._make_watch()

        def fake_post(url, headers=None, json=None, data=None, timeout=None, allow_redirects=None):
            if url == _TOKEN_URL:
                return _token_response()
            if url.endswith("/search"):
                return _FakeResponse(200, SEARCH_RESPONSE_FIXTURE)
            if url.endswith("/consult/lawDecree"):
                return _FakeResponse(200, CONSULT_RESPONSE_FIXTURE)
            raise AssertionError(f"Unexpected URL {url}")

        with self._env(), patch(_TOKEN_PATCH, side_effect=fake_post), \
             patch(_API_PATCH, side_effect=fake_post):
            result = LegifranceConnector(watch, logger=None).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 2)
        decree = next(i for i in result.items if i.external_id == "LEGITEXT000012345678")
        self.assertIn("Contenu de l'article 1", decree.plain_text)
        self.assertIn("Contenu de l'article 2", decree.plain_text)
        self.assertEqual(decree.source_metadata["document_type"], "decree")
        self.assertIsNotNone(decree.published_at)

        order = next(i for i in result.items if i.external_id == "LEGITEXT000087654321")
        self.assertEqual(order.source_metadata["document_type"], "order")

    def test_fetch_falls_back_to_title_when_consult_fails(self):
        watch = self._make_watch()

        def fake_post(url, headers=None, json=None, data=None, timeout=None, allow_redirects=None):
            if url == _TOKEN_URL:
                return _token_response()
            if url.endswith("/search"):
                return _FakeResponse(200, SEARCH_RESPONSE_FIXTURE)
            if url.endswith("/consult/lawDecree"):
                return _FakeResponse(500, text="server error")
            raise AssertionError(f"Unexpected URL {url}")

        with self._env(), patch(_TOKEN_PATCH, side_effect=fake_post), \
             patch(_API_PATCH, side_effect=fake_post), \
             patch("odoo.addons.legal_knowledge_watch.services.legifrance_connector.time.sleep"):
            result = LegifranceConnector(watch, logger=None).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 2)
        for item in result.items:
            self.assertEqual(item.plain_text, item.title)
            self.assertIsNotNone(item.source_metadata["consult_error"])

    def test_fetch_search_redirect_raises(self):
        watch = self._make_watch()

        def fake_post(url, headers=None, json=None, data=None, timeout=None, allow_redirects=None):
            if url == _TOKEN_URL:
                return _token_response()
            if url.endswith("/search"):
                return _FakeResponse(302, headers={"Location": "http://evil.example/"})
            raise AssertionError(f"Unexpected URL {url}")

        with self._env(), patch(_TOKEN_PATCH, side_effect=fake_post), \
             patch(_API_PATCH, side_effect=fake_post):
            with self.assertRaises(ConnectorFetchError):
                LegifranceConnector(watch, logger=None).fetch(cursor=None, limit=10)

    def test_fetch_search_over_size_limit_raises(self):
        watch = self._make_watch()
        big_fixture = {"results": [], "totalResultNumber": 0, "padding": "x" * 6_000_000}

        def fake_post(url, headers=None, json=None, data=None, timeout=None, allow_redirects=None):
            if url == _TOKEN_URL:
                return _token_response()
            if url.endswith("/search"):
                return _FakeResponse(200, big_fixture)
            raise AssertionError(f"Unexpected URL {url}")

        with self._env(), patch(_TOKEN_PATCH, side_effect=fake_post), \
             patch(_API_PATCH, side_effect=fake_post):
            with self.assertRaises(ConnectorFetchError):
                LegifranceConnector(watch, logger=None).fetch(cursor=None, limit=10)

    def test_fetch_search_401_raises_connector_fetch_error(self):
        watch = self._make_watch()

        def fake_post(url, headers=None, json=None, data=None, timeout=None, allow_redirects=None):
            if url == _TOKEN_URL:
                return _token_response()
            if url.endswith("/search"):
                return _FakeResponse(401, text="unauthorized")
            raise AssertionError(f"Unexpected URL {url}")

        with self._env(), patch(_TOKEN_PATCH, side_effect=fake_post), \
             patch(_API_PATCH, side_effect=fake_post):
            with self.assertRaises(ConnectorFetchError):
                LegifranceConnector(watch, logger=None).fetch(cursor=None, limit=10)

    def test_fetch_429_is_retried_then_succeeds(self):
        watch = self._make_watch()
        call_count = {"search": 0}

        def fake_post(url, headers=None, json=None, data=None, timeout=None, allow_redirects=None):
            if url == _TOKEN_URL:
                return _token_response()
            if url.endswith("/search"):
                call_count["search"] += 1
                if call_count["search"] < 2:
                    return _FakeResponse(429, text="rate limited")
                return _FakeResponse(200, SEARCH_RESPONSE_FIXTURE)
            if url.endswith("/consult/lawDecree"):
                return _FakeResponse(200, CONSULT_RESPONSE_FIXTURE)
            raise AssertionError(f"Unexpected URL {url}")

        with self._env(), patch(_TOKEN_PATCH, side_effect=fake_post), \
             patch(_API_PATCH, side_effect=fake_post), \
             patch("odoo.addons.legal_knowledge_watch.services.legifrance_connector.time.sleep"):
            result = LegifranceConnector(watch, logger=None).fetch(cursor=None, limit=10)

        self.assertEqual(call_count["search"], 2)
        self.assertEqual(len(result.items), 2)

    def test_fetch_500_exhausts_retries_and_raises(self):
        watch = self._make_watch()

        def fake_post(url, headers=None, json=None, data=None, timeout=None, allow_redirects=None):
            if url == _TOKEN_URL:
                return _token_response()
            if url.endswith("/search"):
                return _FakeResponse(500, text="server error")
            raise AssertionError(f"Unexpected URL {url}")

        with self._env(), patch(_TOKEN_PATCH, side_effect=fake_post), \
             patch(_API_PATCH, side_effect=fake_post), \
             patch("odoo.addons.legal_knowledge_watch.services.legifrance_connector.time.sleep"):
            with self.assertRaises(ConnectorFetchError):
                LegifranceConnector(watch, logger=None).fetch(cursor=None, limit=10)

    def test_fetch_respects_max_items_per_run(self):
        watch = self._make_watch(max_items_per_run=1)

        def fake_post(url, headers=None, json=None, data=None, timeout=None, allow_redirects=None):
            if url == _TOKEN_URL:
                return _token_response()
            if url.endswith("/search"):
                return _FakeResponse(200, SEARCH_RESPONSE_FIXTURE)
            if url.endswith("/consult/lawDecree"):
                return _FakeResponse(200, CONSULT_RESPONSE_FIXTURE)
            raise AssertionError(f"Unexpected URL {url}")

        with self._env(), patch(_TOKEN_PATCH, side_effect=fake_post), \
             patch(_API_PATCH, side_effect=fake_post):
            result = LegifranceConnector(watch, logger=None).fetch(cursor=None, limit=10)

        self.assertEqual(len(result.items), 1)

    def test_fetch_uses_cursor_as_start_date(self):
        watch = self._make_watch()
        captured_payloads = []

        def fake_post(url, headers=None, json=None, data=None, timeout=None, allow_redirects=None):
            if url == _TOKEN_URL:
                return _token_response()
            if url.endswith("/search"):
                captured_payloads.append(json)
                return _FakeResponse(200, {"results": [], "totalResultNumber": 0})
            raise AssertionError(f"Unexpected URL {url}")

        cursor = jsonlib.dumps({"since": "2026-01-15"})
        with self._env(), patch(_TOKEN_PATCH, side_effect=fake_post), \
             patch(_API_PATCH, side_effect=fake_post):
            LegifranceConnector(watch, logger=None).fetch(cursor=cursor, limit=10)

        filtres = captured_payloads[0]["recherche"]["filtres"]
        date_filter = next(f for f in filtres if f["facette"] == "DATE_PUBLICATION")
        self.assertEqual(date_filter["dates"]["start"], "2026-01-15")
