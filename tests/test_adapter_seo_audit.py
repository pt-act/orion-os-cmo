"""adapter-seo-audit — focused + PBT tests."""

import unittest
from dataclasses import replace

from orion_os_cmo.adapters.seo_audit import SeoAuditAdapter, validate_report
from orion_os_cmo.adapters.seo_audit.adapter import LIGHTHOUSE_PATH, PROVIDER_PATH


def provider_ok():
    return {
        "provider": "seo-analyzer",
        "issues": [
            {"severity": "critical", "type": "missing_title", "fix": "Add a <title>", "snippet": "<head>…"},
            {"severity": "warning", "type": "thin_content", "fix": "Expand copy", "snippet": "<p>buy</p>"},
        ],
        "serp_snapshot": [{"position": 3, "title": "Acme", "url": "https://acme.test/"}],
    }


def lighthouse_ok():
    return {"performance_score": 0.9, "lcp_ms": 2100, "inp_ms": 180, "cls": 0.04, "version": "11.0"}


class MockTransport:
    def __init__(self, responses, raise_on=None):
        self.responses = responses
        self.raise_on = raise_on or set()

    def post(self, path, body):
        if path in self.raise_on:
            raise RuntimeError("boom")
        return self.responses[path]


def _ok():
    return MockTransport({PROVIDER_PATH: provider_ok(), LIGHTHOUSE_PATH: lighthouse_ok()})


class SeoAudit(unittest.TestCase):
    def test_valid_report(self):
        res = SeoAuditAdapter(_ok()).seo_audit("https://acme.test/")
        self.assertTrue(res.ok, res)
        rep = res.value
        # 0.9*100 - (critical10 + warning4) = 76
        self.assertEqual(rep.score, 76)
        self.assertEqual(len(rep.issues), 2)
        self.assertEqual(rep.serp_snapshot[0].position, 3)
        for issue in rep.issues:
            self.assertTrue(issue.severity and issue.type and issue.fix and issue.snippet)

    def test_transport_failure(self):
        t = MockTransport({PROVIDER_PATH: provider_ok(), LIGHTHOUSE_PATH: lighthouse_ok()},
                          raise_on={PROVIDER_PATH})
        res = SeoAuditAdapter(t).seo_audit("https://acme.test/")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "transport")

    def test_provider_missing_issues(self):
        t = MockTransport({PROVIDER_PATH: {"provider": "x"}, LIGHTHOUSE_PATH: lighthouse_ok()})
        res = SeoAuditAdapter(t).seo_audit("https://acme.test/")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "invalid_response")

    def test_lighthouse_failure(self):
        t = MockTransport({PROVIDER_PATH: provider_ok(), LIGHTHOUSE_PATH: {"error": "timeout"}})
        res = SeoAuditAdapter(t).seo_audit("https://acme.test/")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "lighthouse_failure")

    def test_no_serp_is_ok_empty(self):
        prov = provider_ok()
        del prov["serp_snapshot"]
        t = MockTransport({PROVIDER_PATH: prov, LIGHTHOUSE_PATH: lighthouse_ok()})
        res = SeoAuditAdapter(t).seo_audit("https://acme.test/")
        self.assertTrue(res.ok)
        self.assertEqual(res.value.serp_snapshot, [])

    def test_pbt_idempotency(self):
        a = SeoAuditAdapter(_ok()).seo_audit("https://acme.test/").value
        b = SeoAuditAdapter(_ok()).seo_audit("https://acme.test/").value
        self.assertEqual(replace(a, meta={}), replace(b, meta={}))

    def test_pbt_schema_conformance(self):
        for perf in (0.0, 0.5, 1.0):
            t = MockTransport({PROVIDER_PATH: provider_ok(),
                               LIGHTHOUSE_PATH: {**lighthouse_ok(), "performance_score": perf}})
            res = SeoAuditAdapter(t).seo_audit("https://acme.test/")
            self.assertTrue(res.ok)
            self.assertEqual(validate_report(res.value), [])
            self.assertTrue(0 <= res.value.score <= 100)

    def test_q4_score_clamped_to_zero_floor(self):
        # Low perf + many critical issues drives base-penalty negative → clamp to 0,
        # never a negative score (true-negative for the clamp).
        many_critical = {"provider": "p", "issues": [
            {"severity": "critical", "type": f"c{i}", "fix": "f", "snippet": "s"} for i in range(20)
        ]}
        t = MockTransport({PROVIDER_PATH: many_critical,
                           LIGHTHOUSE_PATH: {**lighthouse_ok(), "performance_score": 0.1}})
        res = SeoAuditAdapter(t).seo_audit("https://acme.test/")
        self.assertTrue(res.ok)
        self.assertEqual(res.value.score, 0)  # clamped, not negative

    def test_q3_unknown_severity_coerced_to_info(self):
        # Q-3: an unknown provider severity is coerced to "info" — pinned so the
        # behavior is explicit and tested rather than silent.
        odd = {"provider": "p", "issues": [
            {"severity": "blocker", "type": "x", "fix": "f", "snippet": "s"}]}
        t = MockTransport({PROVIDER_PATH: odd, LIGHTHOUSE_PATH: lighthouse_ok()})
        res = SeoAuditAdapter(t).seo_audit("https://acme.test/")
        self.assertTrue(res.ok)
        self.assertEqual(res.value.issues[0].severity, "info")


if __name__ == "__main__":
    unittest.main()
