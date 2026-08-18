"""OAuth2 Client Credentials against PISTE. Token hosts confirmed live
against the public PISTE API catalog (piste.gouv.fr/api-catalog-sandbox,
2026-08-19): oauth.piste.gouv.fr (production) / sandbox-oauth.piste.gouv.fr
(sandbox). The grant flow (grant_type=client_credentials, form-encoded,
scope=openid, JSON response with access_token/expires_in) was cross-checked
against the open-source pylegifrance client (github.com/rdassignies/
pylegifrance, pylegifrance/auth.py) — not the official Swagger UI directly
(that requires a PISTE account), but a real, independently working
implementation of the same flow. See docs/legifrance-piste.md.
"""
import time

import requests

PRODUCTION_TOKEN_URL = "https://oauth.piste.gouv.fr/api/oauth/token"
SANDBOX_TOKEN_URL = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
DEFAULT_TIMEOUT_SECONDS = 20
TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 30


class PisteOAuthTokenError(Exception):
    """Raised for any failure to obtain a token. Never includes the
    client_secret in its message.
    """


class PisteOAuthClient:
    def __init__(self, client_id, client_secret, environment="sandbox",
                 timeout=DEFAULT_TIMEOUT_SECONDS):
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = (
            SANDBOX_TOKEN_URL if environment == "sandbox" else PRODUCTION_TOKEN_URL
        )
        self._timeout = timeout
        # In-memory only, per connector-instance lifetime — never persisted,
        # never shared across runs (see docs/legifrance-piste.md).
        self._token = None
        self._expires_at = 0.0

    def get_token(self):
        if self._token and time.time() < self._expires_at - TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS:
            return self._token

        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "openid",
        }
        try:
            response = requests.post(self._token_url, data=data, timeout=self._timeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            raise PisteOAuthTokenError(
                f"Network error obtaining a PISTE token: {exc}"
            ) from exc

        if response.status_code in (401, 403):
            raise PisteOAuthTokenError(
                f"PISTE rejected the configured client_id/client_secret "
                f"(HTTP {response.status_code})."
            )
        if not response.ok:
            raise PisteOAuthTokenError(
                f"PISTE token request failed: HTTP {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise PisteOAuthTokenError(
                "PISTE token response was not valid JSON."
            ) from exc

        token = payload.get("access_token")
        if not token:
            raise PisteOAuthTokenError("PISTE token response has no access_token.")

        self._token = token
        self._expires_at = time.time() + int(payload.get("expires_in") or 0)
        return token
