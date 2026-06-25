"""agent-seo — focused + PBT tests (provenance, determinism, schema)."""

import tempfile
import unittest
from pathlib import Path

from orion_os_cmo.adapters.analytics_ingest.types import (
    AnalyticsError, AnalyticsSnapshot, CoreWebVitals, ErrorSource, PageStat,
)
from orion_os_cmo.adapters.seo_audit.types import AuditError, AuditReport, Issue
from orion_os_cmo.adapters.seo_audit.types import ErrorSource as AuditSource
from orion_os_cmo.agent_seo import SeoAgent, validate_findings
from orion_os_cmo.common.result import Err, Ok
from orion_os_cmo.strategy_store.store import StrategyStore

from tests.test_strategy_store_persistence import make_ctx


def audit_report():
    return AuditReport(
        url="https://acme.test/", score=76,
        issues=[
            Issue("critical", "missing_title", "Add a <title>", "<head>…"),
            Issue("warning", "thin_content", "Expand copy", "<p>buy</p>"),
        ],
        serp_snapshot=[], meta={"provider": "p", "lighthouse_version": "11", "audited_at": "t"},
    )


def snapshot():
    return AnalyticsSnapshot(1240, 95, 5300, [PageStat("https://acme.test/", 800, 95, 5300)],
                             CoreWebVitals(2100.0, 180.0, 0.04),
                             {"property_id": "x", "date_range": {"start": "a", "end": "b"}, "fetched_at": "t"})


class FakeAudit:
    def __init__(self, result): self._r = result
    def seo_audit(self, url): return self._r


class FakeAnalytics:
    def __init__(self, result): self._r = result
    def fetch_analytics(self, date_range=None): return self._r


class FixedLLM:
    def __init__(self, payload): self.payload = payload
    def complete_json(self, *, system, prompt): return self.payload


def _strategy_path(d):
    StrategyStore(Path(d)).write(make_ctx())
    return Path(d)


GOOD_LLM = {
    "ranked_fixes": [
        {"issue_id": "issue-0", "fix": "Add a concise <title> with the brand"},
        {"issue_id": "issue-1", "fix": "Expand the page copy to 300+ words"},
    ],
    "keyword_gaps": [{"query": "project management", "impressions": 800}],
}


class AgentSeo(unittest.TestCase):
    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as d:
            agent = SeoAgent(_strategy_path(d), FakeAudit(Ok(audit_report())),
                             FakeAnalytics(Ok(snapshot())), FixedLLM(GOOD_LLM))
            res = agent.run("https://acme.test/")
            self.assertTrue(res.ok, res)
            self.assertEqual(len(res.value.ranked_fixes), 2)
            self.assertEqual(res.value.ranked_fixes[0].snippet, "<head>…")  # grounded from audit
            self.assertEqual(res.value.keyword_gaps[0].query, "project management")

    def test_strategy_missing(self):
        with tempfile.TemporaryDirectory() as d:
            agent = SeoAgent(Path(d), FakeAudit(Ok(audit_report())),
                             FakeAnalytics(Ok(snapshot())), FixedLLM(GOOD_LLM))
            res = agent.run("https://acme.test/")
            self.assertFalse(res.ok)
            self.assertEqual(res.error.kind, "strategy_missing")

    def test_audit_failed(self):
        with tempfile.TemporaryDirectory() as d:
            err = Err(AuditError("transport", "boom", AuditSource("p", "u")))
            agent = SeoAgent(_strategy_path(d), FakeAudit(err),
                             FakeAnalytics(Ok(snapshot())), FixedLLM(GOOD_LLM))
            self.assertEqual(agent.run("u").error.kind, "audit_failed")

    def test_analytics_failed(self):
        with tempfile.TemporaryDirectory() as d:
            err = Err(AnalyticsError("not_connected", "no gsc", ErrorSource("gsc")))
            agent = SeoAgent(_strategy_path(d), FakeAudit(Ok(audit_report())),
                             FakeAnalytics(err), FixedLLM(GOOD_LLM))
            self.assertEqual(agent.run("u").error.kind, "analytics_failed")

    def test_llm_error(self):
        class Boom:
            def complete_json(self, *, system, prompt): raise RuntimeError("x")
        with tempfile.TemporaryDirectory() as d:
            agent = SeoAgent(_strategy_path(d), FakeAudit(Ok(audit_report())),
                             FakeAnalytics(Ok(snapshot())), Boom())
            self.assertEqual(agent.run("u").error.kind, "llm_error")

    def test_provenance_drops_fabricated(self):
        payload = {"ranked_fixes": [
            {"issue_id": "issue-0", "fix": "real"},
            {"issue_id": "issue-99", "fix": "fabricated"},
        ], "keyword_gaps": []}
        with tempfile.TemporaryDirectory() as d:
            agent = SeoAgent(_strategy_path(d), FakeAudit(Ok(audit_report())),
                             FakeAnalytics(Ok(snapshot())), FixedLLM(payload))
            res = agent.run("u")
            self.assertTrue(res.ok)
            ids = [f.issue_id for f in res.value.ranked_fixes]
            self.assertEqual(ids, ["issue-0"])  # fabricated dropped

    def test_rationale_flows_through(self):
        payload = {"ranked_fixes": [
            {"issue_id": "issue-0", "fix": "Add title", "rationale": "highest traffic impact"},
        ], "keyword_gaps": []}
        with tempfile.TemporaryDirectory() as d:
            agent = SeoAgent(_strategy_path(d), FakeAudit(Ok(audit_report())),
                             FakeAnalytics(Ok(snapshot())), FixedLLM(payload))
            res = agent.run("u", run_at="t")
            self.assertTrue(res.ok)
            self.assertEqual(res.value.ranked_fixes[0].rationale, "highest traffic impact")

    def test_pbt_determinism(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _strategy_path(d)
            agent = SeoAgent(sp, FakeAudit(Ok(audit_report())),
                             FakeAnalytics(Ok(snapshot())), FixedLLM(GOOD_LLM))
            # Q-6: with run_at injected, two calls are STRUCTURALLY identical (full equality),
            # satisfying spec PBT #2 "no time-dependent variation" — not just a field subset.
            a = agent.run("u", run_at="2026-06-20T00:00:00Z").value
            b = agent.run("u", run_at="2026-06-20T00:00:00Z").value
            self.assertEqual(a, b)

    def test_pbt_schema_and_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            agent = SeoAgent(_strategy_path(d), FakeAudit(Ok(audit_report())),
                             FakeAnalytics(Ok(snapshot())), FixedLLM(GOOD_LLM))
            findings = agent.run("u").value
            self.assertEqual(validate_findings(findings), [])
            valid_ids = {"issue-0", "issue-1"}
            for fix in findings.ranked_fixes:
                self.assertIn(fix.issue_id, valid_ids)


if __name__ == "__main__":
    unittest.main()
