"""SSRF hardening shared by every outbound HTTP call the module makes to
an admin-configured URL (RSS feed_url and fetch_linked_content, AI
provider base_url). See docs/security.md.

Deliberately checks the host **string** only — never resolves DNS. Two
reasons: (1) a DNS-based check only protects until the next lookup
anyway (DNS rebinding), so it buys little; (2) resolving DNS here would
make every test that fetches a fake `*.example.org` URL depend on real
network access, breaking this project's "tests never touch the network"
rule. This closes the common, blunt attack (someone pointing feed_url or
a provider's base_url directly at `127.0.0.1`, `169.254.169.254`, an
RFC1918 address, etc.) but *not* a hostname that resolves to a private
address — for RSS, the `allowed_domains` allowlist is the real control
for that; there is no equivalent for AI provider base_url in this phase.
"""
import ipaddress
from urllib.parse import urlsplit


class UnsafeUrlError(Exception):
    """Raised when a URL is unsupported or its host is a literal private/
    loopback/link-local/reserved address.
    """


def _is_private_or_reserved(ip_str):
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False  # not an IP literal at all -> nothing to flag here
    return (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    )


def assert_public_host(url):
    """Raise UnsafeUrlError if url is not http(s), or if its host is
    *literally* a private/loopback/link-local/reserved IP address. A
    hostname (anything that isn't already an IP literal) is not resolved
    and always passes this specific check — see the module docstring.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"Unsupported URL scheme: {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise UnsafeUrlError("URL has no host.")
    if _is_private_or_reserved(host):
        raise UnsafeUrlError(
            f"URL host {host!r} is a private/internal address — refusing "
            f"to fetch."
        )
