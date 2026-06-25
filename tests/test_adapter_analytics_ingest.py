"""adapter-analytics-ingest — focused + PBT tests."""

import unittest
from dataclasses import replace

from orion_os_cmo.adapters.analytics_ingest import AnalyticsAdapter, validate_snapshot
from orion_os_cmo.adapters.analytics_ingest.adapter import CWV_PATH, GA4_PATH, GSC_PATH


def ga4_ok():
    return {"property_id": "ga4:123", "sessions": 1240,
            "rows": [{"url": "https://acme.test/", "sessions": 800}]}


def gsc_ok():
    return {"clicks": 95, "impressions": 5300,
            "rows": [{"url": "https://acme.test/", "clicks": 95, "impressions": 5300}]}


def crux_ok():
    return {"lcp_ms": 2100.0, "inp_ms": 180.0, "cls": 0.04}


class MockTransport:
    def __init__(self, responses, raise_on=None):
        self.responses = responses
        self.raise_on = raise_on or set()
        self.calls = []

    def post(self, path, body):
        self.calls.append((path, body))
        if path in self.raise_on:
            raise RuntimeError("boom")
        return self.responses[path]


def _all_ok():
    return MockTransport({GA4_PATH: ga4_ok(), GSC_PATH: gsc_ok(), CWV_PATH: crux_ok()})


class AnalyticsIngest(unittest.TestCase):
    def test_valid_snapshot(self):
        res = AnalyticsAdapter(_all_ok()).fetch_analytics()
        self.assertTrue(res.ok, res)
        snap = res.value
        self.assertEqual(snap.sessions, 1240)
        self.assertEqual(snap.clicks, 95)
        self.assertEqual(snap.impressions, 5300)
        self.assertEqual(snap.top_pages[0].url, "https://acme.test/")
        self.assertEqual(snap.core_web_vitals.lcp_ms, 2100.0)
        self.assertEqual(validate_snapshot(snap), [])

    def test_transport_failure_structured(self):
        t = MockTransport({GA4_PATH: ga4_ok(), GSC_PATH: gsc_ok(), CWV_PATH: crux_ok()},
                          raise_on={GA4_PATH})
        res = AnalyticsAdapter(t).fetch_analytics()
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "transport")

    def test_invalid_response_missing_fields(self):
        t = MockTransport({GA4_PATH: {"property_id": "x"}, GSC_PATH: gsc_ok(), CWV_PATH: crux_ok()})
        res = AnalyticsAdapter(t).fetch_analytics()
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "invalid_response")

    def test_not_connected_structured(self):
        t = MockTransport({GA4_PATH: ga4_ok(),
                           GSC_PATH: {"error": {"code": 403, "status": "PERMISSION_DENIED"}},
                           CWV_PATH: crux_ok()})
        res = AnalyticsAdapter(t).fetch_analytics()
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "not_connected")

    def test_auth_failure_structured(self):
        t = MockTransport({GA4_PATH: {"error": {"code": 401, "status": "auth"}},
                           GSC_PATH: gsc_ok(), CWV_PATH: crux_ok()})
        res = AnalyticsAdapter(t).fetch_analytics()
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "auth_failure")

    def test_pbt_idempotency(self):
        # Same deterministic transport responses -> structurally equal data (ignore fetched_at).
        a = AnalyticsAdapter(_all_ok()).fetch_analytics().value
        b = AnalyticsAdapter(_all_ok()).fetch_analytics().value
        self.assertEqual(replace(a, meta={}), replace(b, meta={}))

    def test_pbt_schema_conformance(self):
        for sessions in (0, 1, 99999):
            t = MockTransport({GA4_PATH: {**ga4_ok(), "sessions": sessions},
                               GSC_PATH: gsc_ok(), CWV_PATH: crux_ok()})
            res = AnalyticsAdapter(t).fetch_analytics()
            self.assertTrue(res.ok)
            self.assertEqual(validate_snapshot(res.value), [])


if __name__ == "__main__":
    unittest.main()
