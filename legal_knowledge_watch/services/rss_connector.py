"""RSS/Atom connector. Never scrapes a linked article by default: only the
feed itself is fetched unless fetch_linked_content is explicitly enabled
for a whitelisted domain.
"""
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from . import normalize_service
from .base_connector import (
    BaseConnector,
    CandidateItem,
    ConnectorConfigError,
    ConnectorFetchError,
    FetchResult,
)
from .connector_registry import register_connector
from .url_safety import UnsafeUrlError, assert_public_host

try:
    import feedparser
except ImportError:  # pragma: no cover - exercised via ImportError path in tests
    feedparser = None

DEFAULT_USER_AGENT = "legal-knowledge-watch/1.0 (+https://github.com/Najah69/odoo-legal-knowledge-watch)"
DEFAULT_MAX_ITEMS_PER_RUN = 50
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_RESPONSE_BYTES = 5_000_000
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1


def _host_allowed(url, allowed_domains):
    if not allowed_domains:
        return True
    host = (urlsplit(url).netloc or "").lower()
    for domain in allowed_domains:
        domain = domain.lower().strip()
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _struct_time_to_datetime(struct_time):
    if not struct_time:
        return None
    try:
        return datetime(*struct_time[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


@register_connector
class RSSConnector(BaseConnector):
    code = "rss"

    def _config(self):
        raw = self.watch.configuration_json or "{}"
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ConnectorConfigError(
                f"configuration_json is not valid JSON: {exc}"
            ) from exc

    def validate_configuration(self):
        if feedparser is None:
            raise ConnectorConfigError(
                "The 'feedparser' Python package is required for the RSS "
                "connector but is not installed."
            )
        config = self._config()
        feed_url = config.get("feed_url")
        if not feed_url or not isinstance(feed_url, str):
            raise ConnectorConfigError("configuration_json.feed_url is required.")
        if not feed_url.lower().startswith("https://") and not feed_url.lower().startswith("http://"):
            raise ConnectorConfigError("feed_url must be an http(s) URL.")
        allowed_domains = config.get("allowed_domains") or []
        if not isinstance(allowed_domains, list):
            raise ConnectorConfigError("configuration_json.allowed_domains must be a list.")
        if not _host_allowed(feed_url, allowed_domains):
            raise ConnectorConfigError(
                f"feed_url host is not in allowed_domains: {feed_url}"
            )
        max_items = config.get("max_items_per_run", DEFAULT_MAX_ITEMS_PER_RUN)
        if not isinstance(max_items, int) or max_items <= 0:
            raise ConnectorConfigError("max_items_per_run must be a positive integer.")
        return config

    def _get_with_retries(self, url, headers, timeout, max_bytes):
        try:
            assert_public_host(url)
        except UnsafeUrlError as exc:
            # Config error, not a transient fetch failure: never retried.
            raise ConnectorFetchError(str(exc)) from exc

        last_exc = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = requests.get(
                    url, headers=headers, timeout=timeout, stream=True,
                    allow_redirects=False,
                )
                if response.status_code == 304:
                    return response
                if 300 <= response.status_code < 400:
                    # Never silently follow a redirect: it would bypass
                    # both the domain allowlist and the SSRF host check
                    # above, which only ever validate the URL we were
                    # asked to fetch — not wherever a redirect points.
                    response.close()
                    raise ConnectorFetchError(
                        f"HTTP {response.status_code} redirect from {url} "
                        f"was not followed (redirects are disabled for "
                        f"safety). Point the configuration at the final "
                        f"URL directly."
                    )
                if response.status_code in (429,) or response.status_code >= 500:
                    response.close()
                    last_exc = ConnectorFetchError(
                        f"HTTP {response.status_code} fetching {url}"
                    )
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                        continue
                    raise last_exc
                if response.status_code >= 400:
                    # Permanent client error: do not retry.
                    response.close()
                    raise ConnectorFetchError(
                        f"HTTP {response.status_code} fetching {url}"
                    )
                content = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    content.extend(chunk)
                    if len(content) > max_bytes:
                        response.close()
                        raise ConnectorFetchError(
                            f"Response from {url} exceeds the {max_bytes} bytes limit."
                        )
                response._legal_watch_content = bytes(content)
                return response
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
                last_exc = ConnectorFetchError(f"Network error fetching {url}: {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                    continue
                raise last_exc from exc
        raise last_exc or ConnectorFetchError(f"Failed to fetch {url}")

    def fetch(self, cursor, limit=100):
        config = self.validate_configuration()
        feed_url = config["feed_url"]
        allowed_domains = config.get("allowed_domains") or []
        fetch_linked_content = bool(config.get("fetch_linked_content", False))
        max_items = min(limit or DEFAULT_MAX_ITEMS_PER_RUN,
                         config.get("max_items_per_run", DEFAULT_MAX_ITEMS_PER_RUN))
        timeout = config.get("request_timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        max_bytes = config.get("max_response_bytes", DEFAULT_MAX_RESPONSE_BYTES)
        user_agent = config.get("user_agent") or DEFAULT_USER_AGENT

        cursor_data = {}
        if cursor:
            try:
                cursor_data = json.loads(cursor)
            except (TypeError, ValueError):
                cursor_data = {}

        headers = {"User-Agent": user_agent}
        if cursor_data.get("etag"):
            headers["If-None-Match"] = cursor_data["etag"]
        if cursor_data.get("last_modified"):
            headers["If-Modified-Since"] = cursor_data["last_modified"]

        response = self._get_with_retries(feed_url, headers, timeout, max_bytes)

        if response.status_code == 304:
            return FetchResult(
                items=[], next_cursor=cursor,
                diagnostics={"status": "not_modified", "http_status": 304},
            )

        parsed = feedparser.parse(response._legal_watch_content)

        items = []
        item_errors = []
        for entry in parsed.entries[:max_items]:
            try:
                item = self._entry_to_candidate(
                    entry, allowed_domains, fetch_linked_content, timeout, max_bytes, user_agent,
                )
                if item is not None:
                    items.append(item)
            except Exception as exc:  # noqa: BLE001 - one bad item must not break the run
                item_errors.append({
                    "title": getattr(entry, "title", None) or "(no title)",
                    "error": str(exc),
                })

        next_cursor = json.dumps({
            "etag": response.headers.get("ETag") or cursor_data.get("etag"),
            "last_modified": response.headers.get("Last-Modified") or cursor_data.get("last_modified"),
        })

        diagnostics = {
            "status": "ok",
            "http_status": response.status_code,
            "raw_item_count": len(parsed.entries),
            "returned_item_count": len(items),
            "bozo": bool(getattr(parsed, "bozo", False)),
            "item_errors": item_errors,
        }
        return FetchResult(items=items, next_cursor=next_cursor, diagnostics=diagnostics)

    def _entry_to_candidate(self, entry, allowed_domains, fetch_linked_content,
                             timeout, max_bytes, user_agent):
        link = entry.get("link")
        if not link:
            raise ValueError("RSS/Atom entry has no <link>.")
        title = normalize_service.normalize_whitespace(entry.get("title") or "(untitled)")
        external_id = entry.get("id") or entry.get("guid") or None
        canonical_url = normalize_service.normalize_canonical_url(link)
        published_at = _struct_time_to_datetime(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )

        summary_html = entry.get("summary") or ""
        raw_content = None
        content_type = "text/html"
        plain_text = normalize_service.html_to_text(summary_html) if summary_html else ""

        if fetch_linked_content and _host_allowed(link, allowed_domains):
            article_response = self._get_with_retries(
                link, {"User-Agent": user_agent}, timeout, max_bytes,
            )
            if article_response.status_code < 400:
                raw_content = article_response._legal_watch_content
                plain_text = normalize_service.html_to_text(
                    normalize_service.decode_bytes(raw_content)
                )

        if not plain_text:
            plain_text = title

        return CandidateItem(
            source_url=link,
            canonical_url=canonical_url,
            title=title,
            external_id=external_id,
            raw_content=raw_content,
            plain_text=plain_text,
            published_at=published_at,
            updated_at=_struct_time_to_datetime(entry.get("updated_parsed")),
            content_type=content_type,
            language="fr_FR",
            source_metadata={
                "feed_entry_id": external_id,
                "author": entry.get("author"),
            },
        )
