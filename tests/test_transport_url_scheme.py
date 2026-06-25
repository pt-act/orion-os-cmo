"""URL scheme validation — defense-in-depth for urlopen calls."""

import unittest
import urllib.parse


def _validate_scheme(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme.startswith("https") and parsed.scheme != "http":
        raise ValueError(f"refusing {parsed.scheme!r} URL (allowed: http/https)")
    return url


class TransportUrlScheme(unittest.TestCase):
    def test_http_allowed(self):
        self.assertEqual(_validate_scheme("http://example.com/page"), "http://example.com/page")

    def test_https_allowed(self):
        self.assertEqual(_validate_scheme("https://example.com/page"), "https://example.com/page")

    def test_file_rejected(self):
        with self.assertRaises(ValueError):
            _validate_scheme("file:///etc/passwd")

    def test_ftp_rejected(self):
        with self.assertRaises(ValueError):
            _validate_scheme("ftp://example.com/file")

    def test_gopher_rejected(self):
        with self.assertRaises(ValueError):
            _validate_scheme("gopher://example.com/")
