"""weekly-orchestrator — integration: fan-out, deltas, brief, publish gate."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orion_os_cmo.agent_geo.types import GapRef, GeoFindings, GeoFix
from orion_os_cmo.agent_seo.types import KeywordGap, RankedFix, SeoFindings
from orion_os_cmo.agent_x.agent import XDraft
from orion_os_cmo.client_workspace import MetricRow, OutputItem, WorkspaceStore
from orion_os_cmo.common.result import Err, Ok
from orion_os_cmo.orchestrator.agent_runner import run_agent
from orion_os_cmo.orchestrator import PublishGate, RunCoordinator, assemble_brief
from orion_os_cmo.orchestrator.types import AGENT_ORDER, AgentOutcome
from orion_os_cmo.strategy_store.store import StrategyStore

from tests.test_strategy_store_persistence import make_ctx


def _ws(d):
    StrategyStore(Path(d)).write(make_ctx())
    store = WorkspaceStore.init(Path(d)).value
    return store


def seo_out():
    return SeoFindings(
        ranked_fixes=[RankedFix("issue-0", "missing_title", "Add title", "<head>", "critical", "top")],
        keyword_gaps=[KeywordGap("pm software", 900)], meta={"url": "u", "audit_score": 80})


def geo_out():
    return GeoFindings(score=0.4, score_delta=None,
                       fixes=[GeoFix("FAQ", "...", "faq", GapRef("gpt", "best?"))],
                       competitor_gaps=[], meta={})


def x_out():
    return [XDraft("post", "Hello world"), XDraft("thread", "1/ a\n2/ b")]


def agents_all_ok():
    return {
        "seo": lambda: Ok(seo_out()),
        "geo": lambda: Ok(geo_out()),
        "x": lambda: Ok(x_out()),
    }


class FakeSocial:
    def __init__(self):
        self.calls = 0
    def publish_post(self, platform, content, approval_token):
        self.calls += 1
        from orion_os_cmo.adapters.social_publish.types import PostResult
        return Ok(PostResult(url="https://x.com/p/9", id="9"))


class Orchestrator(unittest.TestCase):
    def test_all_nine_sections_present(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            brief = RunCoordinator(ws, agents_all_ok()).run("2026-W25", "2026-06-15").value
            self.assertEqual(set(brief.per_agent_sections.keys()), set(AGENT_ORDER))
            # disabled agents are null, not missing
            self.assertIsNone(brief.per_agent_sections["reddit"])
            self.assertIsNotNone(brief.per_agent_sections["seo"])

    def test_delta_from_history_only(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            ws.append_metric(MetricRow("2026-06-08", "seo_score", 78, "tool.seo_audit#W24"))
            brief = RunCoordinator(ws, agents_all_ok()).run("2026-W25", "2026-06-15").value
            metrics = {m.metric: m for m in brief.week_over_week_deltas}
            self.assertIn("seo_score", metrics)
            self.assertEqual(metrics["seo_score"].prior, 78)
            self.assertEqual(metrics["seo_score"].current, 80)
            self.assertEqual(metrics["seo_score"].delta, 2.0)
            self.assertNotIn("geo_score", metrics)  # no prior history → no delta

    def test_failed_agent_recorded_run_continues(self):
        def boom():
            raise RuntimeError("seo crashed")
        agents = {"seo": boom, "geo": lambda: Ok(geo_out()), "x": lambda: Ok(x_out())}
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            brief = RunCoordinator(ws, agents).run("2026-W25", "2026-06-15").value
            self.assertIsNone(brief.per_agent_sections["seo"])      # failed → null
            self.assertIsNotNone(brief.per_agent_sections["geo"])   # others continue
            run = (ws.layout.runs_dir() / "2026-W25.md").read_text()
            self.assertIn("seo: ERROR", run)

    def test_new_metric_rows_have_source(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            RunCoordinator(ws, agents_all_ok()).run("2026-W25", "2026-06-15")
            rows = ws.read_metrics().value
            self.assertTrue(rows)
            for r in rows:
                self.assertTrue(r.source)

    def test_run_record_written(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            RunCoordinator(ws, agents_all_ok()).run("2026-W25", "2026-06-15")
            self.assertTrue((ws.layout.runs_dir() / "2026-W25.md").exists())

    def test_w2_all_agents_fail_all_null_sections(self):
        # task 7.1: every agent fails → all sections null, every error captured, run completes.
        def boom():
            raise RuntimeError("down")
        agents = {name: boom for name in AGENT_ORDER}
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            brief = RunCoordinator(ws, agents).run("2026-W25", "2026-06-15").value
            self.assertEqual(set(brief.per_agent_sections.keys()), set(AGENT_ORDER))
            self.assertTrue(all(v is None for v in brief.per_agent_sections.values()))
            self.assertEqual(brief.prioritized_items, [])
            run = (ws.layout.runs_dir() / "2026-W25.md").read_text()
            for name in AGENT_ORDER:
                self.assertIn(f"{name}: ERROR", run)

    def test_w2_empty_metrics_first_run_no_deltas(self):
        # task 7.2: first run, no prior history → deltas empty (never invented as 0).
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            brief = RunCoordinator(ws, agents_all_ok()).run("2026-W25", "2026-06-15").value
            self.assertEqual(brief.week_over_week_deltas, [])

    def test_w2_advance_published_without_approval_errs(self):
        # cross-layer negative: the workspace publish gate refuses 'published' with no approval.
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            oid = ws.create_output(OutputItem("2026-06-15", "x", "post", "strategy")).value
            res = ws.advance_output(oid, "published", "https://x.com/p/1")
            self.assertFalse(res.ok)
            self.assertEqual(res.error, "no_approval")

    # ── publish gate ──────────────────────────────────────────────────────────

    def test_publish_without_token_no_call(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            social = FakeSocial()
            gate = PublishGate(ws, post_adapter=social)
            oid = ws.create_output(OutputItem("2026-06-15", "x", "post", "strategy")).value
            res = gate.publish_post(oid, "x", "Hello world", None)
            self.assertFalse(res.ok)
            self.assertEqual(res.error, "no_approval_token")
            self.assertEqual(social.calls, 0)

    def test_publish_with_token_records_and_advances(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            social = FakeSocial()
            gate = PublishGate(ws, post_adapter=social)
            oid = ws.create_output(OutputItem("2026-06-15", "x", "post", "strategy")).value
            res = gate.publish_post(oid, "x", "Hello world", "tok-123")
            self.assertTrue(res.ok, res)
            self.assertEqual(social.calls, 1)
            row = next(r for r in ws.read_outputs().value if r.id == oid)
            self.assertEqual(row.status, "published")
            self.assertEqual(row.link, "https://x.com/p/9")

    # ── H-2: publish_article coverage ─────────────────────────────────────

    def test_publish_article_happy_path(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)

            class FakeArticle:
                def publish_article(self, cms, article, token):
                    from orion_os_cmo.adapters.cms_publish.types import PublishResult
                    return Ok(PublishResult(url="https://blog/p/1"))

            gate = PublishGate(ws, article_adapter=FakeArticle())
            oid = ws.create_output(OutputItem("2026-06-15", "writer", "article", "drafts")).value
            res = gate.publish_article(oid, "wordpress", {"slug": "x"}, "tok-123")
            self.assertTrue(res.ok, res)
            row = next(r for r in ws.read_outputs().value if r.id == oid)
            self.assertEqual(row.status, "published")
            self.assertEqual(row.link, "https://blog/p/1")

    def test_publish_article_illegal_transition(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            gate = PublishGate(ws, article_adapter=object())
            oid = ws.create_output(OutputItem("2026-06-15", "writer", "article", "drafts")).value
            ws.advance_output(oid, "rejected", None)
            res = gate.publish_article(oid, "wordpress", {"slug": "x"}, "tok-123")
            self.assertFalse(res.ok)

    def test_record_rejects_can_advance_output_failure(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            social = FakeSocial()
            gate = PublishGate(ws, post_adapter=social)
            oid = ws.create_output(OutputItem("2026-06-15", "x", "post", "strategy")).value
            with patch.object(ws, "can_advance_output") as mock_can:
                mock_can.side_effect = [Ok(None), Err("illegal_transition: rejected")]
                res = gate.publish_post(oid, "x", "Hello", "tok-123")
                self.assertFalse(res.ok)
                self.assertEqual(social.calls, 1)

    def test_advance_output_failure_after_approval(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            social = FakeSocial()
            gate = PublishGate(ws, post_adapter=social)
            oid = ws.create_output(OutputItem("2026-06-15", "x", "post", "strategy")).value
            with patch.object(ws, "advance_output") as mock_adv:
                mock_adv.return_value = Err("workspace_error")
                res = gate.publish_post(oid, "x", "Hello", "tok-123")
                self.assertFalse(res.ok)

    # ── H-2: agent_runner coverage ───────────────────────────────────────

    def test_agent_returns_err(self):
        outcome = run_agent("seo", lambda: Err("fail"))
        self.assertEqual(outcome.name, "seo")
        self.assertIn("fail", outcome.error or "")

    def test_agent_returns_plain_value(self):
        outcome = run_agent("geo", lambda: {"score": 0.5})
        self.assertEqual(outcome.name, "geo")
        self.assertEqual(outcome.output, {"score": 0.5})

    def test_w1_illegal_transition_no_post_no_orphan(self):
        # W-1: an item that cannot legally publish (already rejected) must not fire the
        # irreversible post and must not leave an orphan approval entry.
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            social = FakeSocial()
            gate = PublishGate(ws, post_adapter=social)
            oid = ws.create_output(OutputItem("2026-06-15", "x", "post", "strategy")).value
            ws.advance_output(oid, "rejected", None)  # now illegal to publish
            res = gate.publish_post(oid, "x", "content", "tok-123")
            self.assertFalse(res.ok)
            self.assertIn("illegal_transition", res.error)
            self.assertEqual(social.calls, 0)            # tool never fired
            self.assertFalse(ws._approvals.is_approved(oid))  # no orphan approval

    # ── PBT ─────────────────────────────────────────────────────────────────────

    def test_pbt_brief_determinism(self):
        outcomes = {
            "seo": AgentOutcome("seo", output=seo_out()),
            "geo": AgentOutcome("geo", output=geo_out()),
            "x": AgentOutcome("x", output=x_out()),
        }
        a = assemble_brief(outcomes, [], [], "2026-W25", "2026-06-20T00:00:00Z")
        b = assemble_brief(outcomes, [], [], "2026-W25", "2026-06-20T00:00:00Z")
        self.assertEqual(a, b)

    def test_pbt_publish_gate_needs_token_and_approval(self):
        with tempfile.TemporaryDirectory() as d:
            ws = _ws(d)
            social = FakeSocial()
            gate = PublishGate(ws, post_adapter=social)
            oid = ws.create_output(OutputItem("2026-06-15", "x", "post", "strategy")).value
            # bad tokens never reach the tool
            for bad in (None, "", "   "):
                self.assertEqual(gate.publish_post(oid, "x", "c", bad).error, "no_approval_token")
            self.assertEqual(social.calls, 0)
            # a published row always has a matching approval entry
            gate.publish_post(oid, "x", "c", "tok")
            row = next(r for r in ws.read_outputs().value if r.id == oid)
            self.assertEqual(row.status, "published")
            self.assertTrue(ws._approvals.is_approved(oid))


if __name__ == "__main__":
    unittest.main()
