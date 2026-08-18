"""Shared bounded-retry HTTP helper for AI/export providers. Timeout,
retry-with-backoff on 429/5xx/network errors, no retry on other 4xx —
mirrors the same policy already used by the RSS and Légifrance connectors.
"""
import time

import requests

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1


def request_with_retries(method, url, error_cls, **kwargs):
    """method: 'get', 'post', 'put' or 'delete'. error_cls: exception class
    to raise on failure — never put a token or full request/response body
    in its message beyond a short excerpt.
    """
    last_exc = None
    request_fn = getattr(requests, method)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = request_fn(url, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            last_exc = error_cls(f"Network error calling {url}: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                continue
            raise last_exc from exc

        if response.status_code == 429 or response.status_code >= 500:
            last_exc = error_cls(f"HTTP {response.status_code} calling {url}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                continue
            raise last_exc
        if response.status_code >= 400:
            raise error_cls(
                f"HTTP {response.status_code} calling {url}: {response.text[:300]}"
            )
        return response
    raise last_exc or error_cls(f"Failed to call {url}")
