"""Shared bounded-retry HTTP helper for AI/export providers. Timeout,
retry-with-backoff on 429/5xx/network errors, no retry on other 4xx —
mirrors the same policy already used by the RSS and Légifrance connectors.
Also the single SSRF/redirect/size choke point for both AI providers,
since their base_url is entirely admin-configured (see url_safety.py).
"""
import time

import requests

from .url_safety import UnsafeUrlError, assert_public_host

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1
DEFAULT_MAX_RESPONSE_BYTES = 5_000_000


def request_with_retries(method, url, error_cls, max_response_bytes=DEFAULT_MAX_RESPONSE_BYTES, **kwargs):
    """method: 'get', 'post', 'put' or 'delete'. error_cls: exception class
    to raise on failure — never put a token or full request/response body
    in its message beyond a short excerpt.
    """
    try:
        assert_public_host(url)
    except UnsafeUrlError as exc:
        # Config error, not a transient call failure: never retried.
        raise error_cls(str(exc)) from exc

    kwargs.setdefault("allow_redirects", False)
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

        if 300 <= response.status_code < 400:
            # Never silently follow a redirect: it would bypass the SSRF
            # host check above, which only ever validates the URL we were
            # asked to call — not wherever a redirect points.
            raise error_cls(
                f"HTTP {response.status_code} redirect from {url} was not "
                f"followed (redirects are disabled for safety). Point "
                f"base_url at the final URL directly."
            )
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
        content_length = response.headers.get("Content-Length")
        if content_length is not None and content_length.isdigit() and int(content_length) > max_response_bytes:
            raise error_cls(
                f"Response from {url} declares {content_length} bytes, "
                f"exceeding the {max_response_bytes} bytes limit."
            )
        if len(response.content) > max_response_bytes:
            raise error_cls(
                f"Response from {url} exceeds the {max_response_bytes} bytes limit."
            )
        return response
    raise last_exc or error_cls(f"Failed to call {url}")
