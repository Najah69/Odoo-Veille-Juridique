"""Unit tests for services.url_safety. Pure string/ipaddress logic —
touches no network by construction, so no mocking is needed.
"""
import unittest

from ..services.url_safety import UnsafeUrlError, assert_public_host


class TestAssertPublicHost(unittest.TestCase):
    def test_non_http_scheme_raises(self):
        with self.assertRaises(UnsafeUrlError):
            assert_public_host("ftp://example.org/feed")

    def test_no_host_raises(self):
        with self.assertRaises(UnsafeUrlError):
            assert_public_host("https:///feed")

    def test_ordinary_hostname_passes(self):
        assert_public_host("https://exemple.gouv.example.org/feed.rss")

    def test_loopback_ip_raises(self):
        with self.assertRaises(UnsafeUrlError):
            assert_public_host("http://127.0.0.1/feed")

    def test_ipv6_loopback_raises(self):
        with self.assertRaises(UnsafeUrlError):
            assert_public_host("http://[::1]/feed")

    def test_link_local_metadata_ip_raises(self):
        with self.assertRaises(UnsafeUrlError):
            assert_public_host("http://169.254.169.254/latest/meta-data/")

    def test_rfc1918_private_ip_raises(self):
        with self.assertRaises(UnsafeUrlError):
            assert_public_host("http://10.0.0.5/feed")
        with self.assertRaises(UnsafeUrlError):
            assert_public_host("http://192.168.1.1/feed")

    def test_public_ip_literal_passes(self):
        assert_public_host("http://93.184.216.34/feed")
