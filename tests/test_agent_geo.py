"""agent-geo — focused + PBT tests (provenance, delta, determinism, schema)."""

import tempfile
import unittest
from pathlib import Path

from orion_os_cmo.adapters.geo_probe.types import GeoReport, ModelResult, ProbeError, ProbeErrorSource
from orion_os_cmo.agent_geo import GeoAgent, validate_findings
from orion_os_cmo.common.result import Err, Ok
from orion_os_cmo.strategy_store.store import StrategyStore

from tests.test_strategy_store_persistence import make_ctx


def report(score, rows):
    return GeoReport(score=score, per_model=rows, competitor_gaps=["Notion"])


def rows_mixed():
    return [
        ModelResult("gpt", "best pm tool?", True, 0, "positive", "Acme is best"),
        ModelResult("claude", "top pm options?", False, None, "none", "Notion and others"),
        ModelResult("gemini", "pm software?", False, None, "none", "Asana leads"),
    ]


class FakeProbe:
    def __init__(self, result):
        self._r = result
    def probe(self, brand, questions, models, competitors=None):
        return self._r


class FixedLLM:
    def __init__(self, payload):
        self.payload = payload
    def complete_json(self, *, system, prompt):
        return self.payload


# Two fixes: one valid index, one out-of-range (must be dropped).
LLM_FIXES = {"fixes": [
    {"index": 0, "fix": "Add FAQ", "snippet": "Q: ... A: ...", "fix_type": "faq"},
    {"index": 1, "fix": "Add schema", "snippet": "{...}", "fix_type": "json_ld"},
    {"index": 99, "fix": "fabricated", "snippet": "x", "fix_type": "faq"},
]}


def _sp(d):
    StrategyStore(Path(d)).write(make_ctx())
    return Path(d)


class AgentGeo(unittest.TestCase):
    def test_happy_path(self):
        with tempfile.TemporaryDirectory() as d:
            agent = GeoAgent(_sp(d), FakeProbe(Ok(report(0.33, rows_mixed()))),
                             FixedLLM(LLM_FIXES), models=["gpt", "claude", "gemini"])
            res = agent.run("Acme")
            self.assertTrue(res.ok, res)
            f = res.value
            self.assertEqual(f.score, 0.33)
            self.assertEqual(len(f.fixes), 2)  # 2 gaps -> 2 valid fixes; index 99 dropped
            self.assertEqual(f.competitor_gaps, ["Notion"])
            self.assertIsNone(f.score_delta)  # first run

    def test_fix_count_matches_gaps(self):
        with tempfile.TemporaryDirectory() as d:
            agent = GeoAgent(_sp(d), FakeProbe(Ok(report(0.33, rows_mixed()))),
                             FixedLLM(LLM_FIXES), models=["gpt", "claude", "gemini"])
            f = agent.run("Acme").value
            gap_refs = {(x.gap_ref.model, x.gap_ref.question) for x in f.fixes}
            self.assertEqual(gap_refs, {("claude", "top pm options?"), ("gemini", "pm software?")})

    def test_delta_second_run(self):
        with tempfile.TemporaryDirectory() as d:
            sp = _sp(d)
            GeoAgent(sp, FakeProbe(Ok(report(0.20, rows_mixed()))),
                     FixedLLM(LLM_FIXES), models=["gpt"]).run("Acme")
            res2 = GeoAgent(sp, FakeProbe(Ok(report(0.50, rows_mixed()))),
                            FixedLLM(LLM_FIXES), models=["gpt"]).run("Acme")
            self.assertAlmostEqual(res2.value.score_delta, 0.30, places=6)

    def test_strategy_missing(self):
        with tempfile.TemporaryDirectory() as d:
            agent = GeoAgent(Path(d), FakeProbe(Ok(report(0.5, rows_mixed()))), FixedLLM(LLM_FIXES))
            self.assertEqual(agent.run("Acme").error.kind, "strategy_missing")

    def test_probe_error_is_partial_not_crash(self):
        with tempfile.TemporaryDirectory() as d:
            err = Err(ProbeError("engine_unavailable", "all down", ProbeErrorSource("gpt", "q")))
            agent = GeoAgent(_sp(d), FakeProbe(err), FixedLLM(LLM_FIXES))
            res = agent.run("Acme")
            self.assertTrue(res.ok)  # partial, not an error
            self.assertEqual(res.value.fixes, [])
            self.assertIn("note", res.value.meta)

    def test_pbt_provenance_and_schema(self):
        with tempfile.TemporaryDirectory() as d:
            agent = GeoAgent(_sp(d), FakeProbe(Ok(report(0.33, rows_mixed()))),
                             FixedLLM(LLM_FIXES), models=["gpt", "claude", "gemini"])
            f = agent.run("Acme").value
            gaps = [("claude", "top pm options?"), ("gemini", "pm software?")]
            self.assertEqual(validate_findings(f, gaps), [])

    def test_pbt_determinism(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = GeoAgent(_sp(d1), FakeProbe(Ok(report(0.33, rows_mixed()))),
                         FixedLLM(LLM_FIXES), models=["gpt", "claude", "gemini"]).run("Acme").value
            b = GeoAgent(_sp(d2), FakeProbe(Ok(report(0.33, rows_mixed()))),
                         FixedLLM(LLM_FIXES), models=["gpt", "claude", "gemini"]).run("Acme").value
            self.assertEqual(a.fixes, b.fixes)
            self.assertEqual(a.score, b.score)
            self.assertEqual(a.competitor_gaps, b.competitor_gaps)


if __name__ == "__main__":
    unittest.main()
