"""agent-coding — focused + PBT tests (provenance, never-merge, schema)."""

import tempfile
import unittest
from pathlib import Path

from orion_os_cmo.adapters.github_pr import GitHubPrAdapter
from orion_os_cmo.agent_coding import CodingAgent, validate_pr_entry
from orion_os_cmo.agent_geo.types import GapRef, GeoFindings, GeoFix
from orion_os_cmo.agent_seo.types import RankedFix, SeoFindings
from orion_os_cmo.strategy_store.store import StrategyStore

from tests.test_adapter_github_pr import FakeGitHub
from tests.test_strategy_store_persistence import make_ctx


def seo_findings():
    return SeoFindings(
        ranked_fixes=[
            RankedFix("issue-0", "missing_title", "Add title", "<head>", "critical", "top priority"),
            RankedFix("issue-1", "thin_content", "Expand", "<p>", "warning", "medium"),
        ],
        keyword_gaps=[], meta={"url": "u", "audit_score": 76},
    )


def geo_findings():
    return GeoFindings(
        score=0.5, score_delta=None,
        fixes=[GeoFix("Add FAQ schema", "{...}", "json_ld", GapRef("gpt", "best?"))],
        competitor_gaps=[], meta={"run_at": "t", "probe_model_count": 1, "question_count": 1},
    )


# index 99 finding is fabricated and must be dropped.
LLM_CHANGES = {"changes": [
    {"finding_id": "issue-0", "file_path": "index.html", "change_description": "add title tag",
     "diff_fragment": "--- a/index.html\n+++ b/index.html\n@@ -1 +1 @@\n-<head>\n+<head><title>Acme</title>"},
    {"finding_id": "geo-0", "file_path": "faq.html", "change_description": "add FAQPage JSON-LD",
     "diff_fragment": "--- a/faq.html\n+++ b/faq.html\n@@ -1 +1 @@\n-x\n+<script type=ld+json>"},
    {"finding_id": "issue-404", "file_path": "evil.html", "change_description": "fabricated",
     "diff_fragment": "--- a/evil\n+++ b/evil\n@@ -1 +1 @@\n-a\n+b"},
]}


class FixedLLM:
    def __init__(self, payload): self.payload = payload
    def complete_json(self, *, system, prompt): return self.payload


def _sp(d):
    StrategyStore(Path(d)).write(make_ctx())
    return Path(d)


class AgentCoding(unittest.TestCase):
    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as d:
            gh = FakeGitHub()
            agent = CodingAgent(_sp(d), seo_findings(), geo_findings(),
                                GitHubPrAdapter(gh), FixedLLM(LLM_CHANGES))
            res = agent.run("acme/repo", run_date="2026-06-20")
            self.assertTrue(res.ok, res)
            entry = res.value[0]
            self.assertTrue(entry.pr_url.endswith("/pull/1"))
            self.assertEqual(entry.branch, "orion-cmo/weekly-2026-06-20")
            ids = [c.finding_id for c in entry.fixes_applied]
            self.assertEqual(ids, ["issue-0", "geo-0"])  # fabricated dropped

    def test_strategy_missing(self):
        with tempfile.TemporaryDirectory() as d:
            agent = CodingAgent(Path(d), seo_findings(), geo_findings(),
                                GitHubPrAdapter(FakeGitHub()), FixedLLM(LLM_CHANGES))
            self.assertEqual(agent.run("acme/repo").error.kind, "strategy_missing")

    def test_findings_missing(self):
        with tempfile.TemporaryDirectory() as d:
            empty_seo = SeoFindings([], [], {})
            empty_geo = GeoFindings(0.0, None, [], [], {})
            agent = CodingAgent(_sp(d), empty_seo, empty_geo,
                                GitHubPrAdapter(FakeGitHub()), FixedLLM(LLM_CHANGES))
            self.assertEqual(agent.run("acme/repo").error.kind, "findings_missing")

    def test_pr_failed(self):
        with tempfile.TemporaryDirectory() as d:
            gh = FakeGitHub(fail={"/repos/branch/ensure": "raise"})
            agent = CodingAgent(_sp(d), seo_findings(), geo_findings(),
                                GitHubPrAdapter(gh), FixedLLM(LLM_CHANGES))
            self.assertEqual(agent.run("acme/repo").error.kind, "pr_failed")

    def test_pbt_never_merges(self):
        with tempfile.TemporaryDirectory() as d:
            gh = FakeGitHub()
            agent = CodingAgent(_sp(d), seo_findings(), geo_findings(),
                                GitHubPrAdapter(gh), FixedLLM(LLM_CHANGES))
            agent.run("acme/repo", run_date="2026-06-20")
            for path, _ in gh.calls:
                self.assertNotIn("merge", path.lower())

    def test_pbt_provenance_and_schema(self):
        with tempfile.TemporaryDirectory() as d:
            agent = CodingAgent(_sp(d), seo_findings(), geo_findings(),
                                GitHubPrAdapter(FakeGitHub()), FixedLLM(LLM_CHANGES))
            entry = agent.run("acme/repo", run_date="2026-06-20").value[0]
            valid = {"issue-0", "issue-1", "geo-0"}
            self.assertEqual(validate_pr_entry(entry, valid), [])
            for c in entry.fixes_applied:
                self.assertIn(c.finding_id, valid)


if __name__ == "__main__":
    unittest.main()
