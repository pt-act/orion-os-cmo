import json
import tempfile
import unittest
from pathlib import Path

from orion_os_cmo.strategy_store.context import (
    BrandVoice,
    Competitor,
    Differentiator,
    GrowthPlaybook,
    Icp,
    Positioning,
    StrategyContext,
    StrategyMeta,
)
from orion_os_cmo.strategy_store.evidence import EvidenceSet
from orion_os_cmo.strategy_store.store import SECTIONS, StrategyStore
from orion_os_cmo.strategy_store.synthesize import synthesize_strategy


def make_ctx(tone: str = "direct", version: int = 1) -> StrategyContext:
    return StrategyContext(
        brand_voice=BrandVoice(tone=tone, register="casual", do=["x"], dont=["y"], sample_phrases=["z"]),
        icp=Icp(segments=["startups"], pains=["chaos"], triggers=["scaling"]),
        competitors=[Competitor("Notion", "https://notion.so", "all-in-one", "https://notion.so")],
        positioning=Positioning("PM for teams", "project management",
                                [Differentiator("faster", "https://acme.test/")]),
        growth_playbook=GrowthPlaybook(["seo"], ["content"], "organic"),
        meta=StrategyMeta(version=version, built_at="t", source_run="run-1"),
    )


class PersistenceGroup3(unittest.TestCase):
    def test_3_1_write_creates_section_files_and_meta(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            diff = StrategyStore(Path(d)).write(make_ctx())
            for name in SECTIONS:
                self.assertTrue((Path(d) / "strategy" / f"{name}.json").exists())
            self.assertTrue((Path(d) / "strategy" / "_meta.json").exists())
            self.assertEqual({s.status for s in diff.sections}, {"added"})
            self.assertEqual(diff.version, 1)

    def test_3_3_refresh_emits_diff(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = StrategyStore(Path(d))
            store.write(make_ctx(tone="direct"))
            diff = store.refresh(make_ctx(tone="bold"))  # brand_voice changed
            statuses = {s.section: s.status for s in diff.sections}
            self.assertEqual(statuses["brand_voice"], "updated")
            self.assertEqual(statuses["icp"], "unchanged")
            self.assertEqual(diff.version, 2)

    def test_3_4_operator_edit_survives_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = StrategyStore(Path(d))
            store.write(make_ctx(tone="direct"))

            # Operator hand-edits brand_voice.json.
            bv_path = Path(d) / "strategy" / "brand_voice.json"
            edited = json.loads(bv_path.read_text())
            edited["tone"] = "operator-tuned"
            bv_path.write_text(json.dumps(edited, indent=2))

            # Refresh with a different synthesized brand_voice.
            diff = store.refresh(make_ctx(tone="model-new"))
            statuses = {s.section: s.status for s in diff.sections}
            self.assertEqual(statuses["brand_voice"], "kept")
            self.assertEqual(json.loads(bv_path.read_text())["tone"], "operator-tuned")

            # A second refresh still preserves the operator's edit.
            store.refresh(make_ctx(tone="model-newer"))
            self.assertEqual(json.loads(bv_path.read_text())["tone"], "operator-tuned")

    def test_4_2_idempotent_refresh_no_duplicate_or_bump(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = StrategyStore(Path(d))
            store.write(make_ctx())
            diff = store.refresh(make_ctx())  # identical input
            self.assertTrue(all(s.status == "unchanged" for s in diff.sections))
            self.assertEqual(diff.version, 1)  # no-op refresh does not bump
            loaded = store.load()
            assert loaded is not None
            self.assertEqual(loaded["sections"]["brand_voice"]["tone"], "direct")

    def test_4_1_empty_evidence_is_graceful_not_crash(self) -> None:
        class NeverLLM:
            def complete_json(self, *, system: str, prompt: str) -> dict:
                raise AssertionError("LLM should not be called for empty evidence")

        res = synthesize_strategy(EvidenceSet(built_at="t", items=[]), NeverLLM())
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "invalid_output")


if __name__ == "__main__":
    unittest.main()
