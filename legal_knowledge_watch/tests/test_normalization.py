import unittest

from ..services import normalize_service


class TestNormalizeWhitespace(unittest.TestCase):
    def test_collapses_whitespace_and_strips(self):
        self.assertEqual(
            normalize_service.normalize_whitespace("  Hello \n\n  world  \t!  "),
            "Hello world !",
        )

    def test_empty_input(self):
        self.assertEqual(normalize_service.normalize_whitespace(""), "")
        self.assertEqual(normalize_service.normalize_whitespace(None), "")


class TestHtmlToText(unittest.TestCase):
    def test_strips_tags_scripts_and_styles(self):
        html = (
            "<html><head><style>.a{color:red}</style></head>"
            "<body><script>evil()</script>"
            "<h1>Titre</h1><p>Un   paragraphe.</p></body></html>"
        )
        text = normalize_service.html_to_text(html)
        self.assertIn("Titre", text)
        self.assertIn("Un paragraphe.", text)
        self.assertNotIn("evil", text)
        self.assertNotIn("color:red", text)


class TestContentHash(unittest.TestCase):
    def test_same_normalized_text_same_hash(self):
        hash_a = normalize_service.compute_content_hash("Hello   world")
        hash_b = normalize_service.compute_content_hash("Hello world")
        self.assertEqual(hash_a, hash_b)

    def test_different_text_different_hash(self):
        hash_a = normalize_service.compute_content_hash("Hello world")
        hash_b = normalize_service.compute_content_hash("Hello there")
        self.assertNotEqual(hash_a, hash_b)

    def test_hash_is_deterministic_sha256_hex(self):
        content_hash = normalize_service.compute_content_hash("stable content")
        self.assertEqual(len(content_hash), 64)
        int(content_hash, 16)  # raises ValueError if not valid hex


class TestCanonicalUrl(unittest.TestCase):
    def test_lowercases_scheme_and_host(self):
        self.assertEqual(
            normalize_service.normalize_canonical_url("HTTPS://Example.COM/Path"),
            "https://example.com/Path",
        )

    def test_strips_fragment_and_trailing_slash(self):
        self.assertEqual(
            normalize_service.normalize_canonical_url("https://example.com/path/#section"),
            "https://example.com/path",
        )

    def test_sorts_query_parameters(self):
        url_a = normalize_service.normalize_canonical_url("https://example.com/p?b=2&a=1")
        url_b = normalize_service.normalize_canonical_url("https://example.com/p?a=1&b=2")
        self.assertEqual(url_a, url_b)

    def test_empty_url(self):
        self.assertEqual(normalize_service.normalize_canonical_url(""), "")
        self.assertEqual(normalize_service.normalize_canonical_url(None), "")


class TestExtractPdfText(unittest.TestCase):
    def test_invalid_pdf_bytes_returns_none_not_raise(self):
        result = normalize_service.extract_pdf_text(b"not a real pdf")
        self.assertIsNone(result)
