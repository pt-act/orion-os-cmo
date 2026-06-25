"""client-workspace — focused + property-based tests.

PBT invariants (Tier 2): round-trip durability, operator-edit preservation,
append-only metrics, publish gate. Property tests use stdlib `random` over many
generated sequences (no third-party PBT dependency).
"""

import random
import tempfile
import unittest
from pathlib import Path

from orion_os_cmo.client_workspace import (
    ApprovalEntry,
    MetricRow,
    OutputItem,
    RunRecord,
    WorkspaceStore,
)
from orion_os_cmo.client_workspace.layout import DIRS

from tests.test_strategy_store_persistence import make_ctx


def _store(d: str) -> WorkspaceStore:
    res = WorkspaceStore.init(Path(d))
    assert res.ok, res
    return res.value


class InitGroup1(unittest.TestCase):
    def test_1_3_init_creates_tree_and_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            bank = store.layout.bank
            for name in DIRS:
                self.assertTrue((bank / name).is_dir(), name)
            for key in ("client_context", "config", "metrics", "outputs",
                        "approvals", "brand_safety", "activity", "current_state",
                        "open_decisions"):
                self.assertTrue(store.layout.resolve(key).exists(), key)
            gi = (Path(d) / ".gitignore").read_text()
            self.assertIn("!.agents/memory_bank-production/", gi)

    def test_1_4_init_idempotent_preserves_edits(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            _store(d)
            cs = WorkspaceStore(Path(d)).layout.resolve("current_state")
            cs.write_text("# Current State\n\nOPERATOR EDIT\n", encoding="utf-8")
            _store(d)  # re-init
            self.assertIn("OPERATOR EDIT", cs.read_text())

    def test_6_1_partial_tree_recreated(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            import shutil
            shutil.rmtree(store.layout.dir("runs"))
            _store(d)
            self.assertTrue(store.layout.dir("runs").is_dir())


class StrategySection(unittest.TestCase):
    def test_2_3_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            store.write_strategy(make_ctx(tone="direct"))
            loaded = store.read_strategy()
            self.assertTrue(loaded.ok)
            self.assertEqual(loaded.value["sections"]["brand_voice"]["tone"], "direct")

    def test_2_4_pbt_round_trip_durability(self) -> None:
        rng = random.Random(7)
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            for _ in range(25):
                tone = "".join(rng.choices("abcdef ", k=rng.randint(1, 12))).strip() or "x"
                store.refresh_strategy(make_ctx(tone=tone))
                loaded = store.read_strategy()
                self.assertTrue(loaded.ok)
                self.assertEqual(loaded.value["sections"]["brand_voice"]["tone"], tone)

    def test_2_5_pbt_edit_preservation(self) -> None:
        import json
        rng = random.Random(11)
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            store.write_strategy(make_ctx(tone="v0"))
            bv = store.layout.bank / "strategy" / "brand_voice.json"
            data = json.loads(bv.read_text())
            data["tone"] = "OPERATOR"
            bv.write_text(json.dumps(data, indent=2))
            for _ in range(20):
                diff = store.refresh_strategy(make_ctx(tone=f"m{rng.randint(0, 9)}")).value
                status = {s.section: s.status for s in diff.sections}["brand_voice"]
                self.assertEqual(status, "kept")
                self.assertEqual(json.loads(bv.read_text())["tone"], "OPERATOR")


class MetricsSection(unittest.TestCase):
    def test_3_3_append_valid(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            before = len(store.read_metrics().value)
            res = store.append_metric(MetricRow("2026-06-20", "seo_score", 78, "tool.seo_audit#r1"))
            self.assertTrue(res.ok)
            rows = store.read_metrics().value
            self.assertEqual(len(rows), before + 1)
            self.assertEqual(rows[-1].value, 78)

    def test_3_4_append_empty_source_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            before = store.layout.resolve("metrics").read_text()
            res = store.append_metric(MetricRow("2026-06-20", "seo_score", 78, ""))
            self.assertFalse(res.ok)
            self.assertEqual(res.error, "empty_source")
            self.assertEqual(store.layout.resolve("metrics").read_text(), before)

    def test_6_2_empty_metrics_reads_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            self.assertEqual(store.read_metrics().value, [])

    def test_3_5_pbt_append_only(self) -> None:
        rng = random.Random(3)
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            metrics_path = store.layout.resolve("metrics")
            for _ in range(30):
                snapshot = metrics_path.read_text()
                store.append_metric(MetricRow(
                    f"2026-06-{rng.randint(1, 28):02d}",
                    rng.choice(["seo_score", "geo_score", "sessions"]),
                    rng.choice([rng.randint(0, 9999), round(rng.random(), 3)]),
                    f"tool.x#r{rng.randint(1, 99)}",
                ))
                # Every prior byte is still a prefix of the new file.
                self.assertTrue(metrics_path.read_text().startswith(snapshot))


class OutputsAndApprovals(unittest.TestCase):
    def test_4_4_publish_without_approval_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            oid = store.create_output(OutputItem("2026-06-20", "x", "post", "strategy v1")).value
            res = store.advance_output(oid, "published", "tool.publish#1")
            self.assertFalse(res.ok)
            self.assertEqual(res.error, "no_approval")

    def test_4_5_publish_after_approval_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            oid = store.create_output(OutputItem("2026-06-20", "x", "post", "strategy v1")).value
            store.append_approval(ApprovalEntry(oid, "approved", "riata", date="2026-06-20"))
            store.advance_output(oid, "approved", None)
            res = store.advance_output(oid, "published", "https://x.com/p/1")
            self.assertTrue(res.ok, res)
            row = next(r for r in store.read_outputs().value if r.id == oid)
            self.assertEqual(row.status, "published")
            self.assertEqual(row.link, "https://x.com/p/1")

    def test_4_6_reject_needs_no_approval(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            oid = store.create_output(OutputItem("2026-06-20", "x", "post", "strategy v1")).value
            self.assertTrue(store.advance_output(oid, "rejected", None).ok)

    def test_4_7_pbt_publish_gate(self) -> None:
        rng = random.Random(5)
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            approved_ids: set[str] = set()
            ids: list[str] = []
            for _ in range(40):
                action = rng.choice(["create", "approve", "publish"])
                if action == "create" or not ids:
                    ids.append(store.create_output(
                        OutputItem("2026-06-20", "x", "post", "strategy v1")).value)
                elif action == "approve":
                    oid = rng.choice(ids)
                    store.append_approval(ApprovalEntry(oid, "approved", "riata", date="2026-06-20"))
                    store.advance_output(oid, "approved", None)
                    approved_ids.add(oid)
                else:
                    store.advance_output(rng.choice(ids), "published", "url")
            # Invariant: every published row has an approval.
            for row in store.read_outputs().value:
                if row.status == "published":
                    self.assertIn(row.id, approved_ids)


class RunsAndConfig(unittest.TestCase):
    def test_5_4_duplicate_week_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            rec = RunRecord("2026-W25", "2026-06-15", "strategy v1", ["SEO: 3 fixes"])
            self.assertTrue(store.write_run(rec).ok)
            path = store.layout.runs_dir() / "2026-W25.md"
            before = path.read_text()
            res = store.write_run(RunRecord("2026-W25", "2026-06-15", "DIFFERENT", []))
            self.assertFalse(res.ok)
            self.assertEqual(res.error, "duplicate_week")
            self.assertEqual(path.read_text(), before)

    def test_5_5_read_last_run_latest(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            store.write_run(RunRecord("2026-W24", "2026-06-08", "v1", ["SEO: a"]))
            store.write_run(RunRecord("2026-W25", "2026-06-15", "v2", ["GEO: b", "SEO: c"]))
            last = store.read_last_run().value
            self.assertIsNotNone(last)
            self.assertEqual(last.week_key, "2026-W25")
            self.assertEqual(last.per_agent, ["GEO: b", "SEO: c"])

    def test_5_3_config_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            store = _store(d)
            cfg = store.read_config().value
            self.assertEqual(cfg["approval_policy"], "human-gate-all")
            self.assertEqual(cfg["connected_accounts"]["x"], False)
            cfg["connected_accounts"]["x"] = True
            cfg["metering"]["video_clips_max_per_run"] = 3
            store.write_config(cfg)
            reloaded = store.read_config().value
            self.assertEqual(reloaded["connected_accounts"]["x"], True)
            self.assertEqual(reloaded["metering"]["video_clips_max_per_run"], 3)
            self.assertEqual(reloaded["agents_enabled"][0], "seo")


if __name__ == "__main__":
    unittest.main()
