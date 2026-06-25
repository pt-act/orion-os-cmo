"""reach milestone — creator-discovery, video-gen, influencer, ugc."""

import tempfile
import unittest
from pathlib import Path

from orion_os_cmo.adapters.creator_discovery import CreatorDiscoveryAdapter
from orion_os_cmo.adapters.creator_discovery.adapter import (
    DEMOGRAPHICS_PATH, EMAIL_PATH, SEARCH_PATH,
)
from orion_os_cmo.adapters.creator_discovery.types import Creator, CreatorSource
from orion_os_cmo.adapters.video_gen import VideoGenAdapter, check_cap
from orion_os_cmo.adapters.video_gen.adapter import QUOTE_PATH, RENDER_PATH
from orion_os_cmo.agent_influencer import InfluencerAgent, InfluencerAgentConfig, validate_outreach
from orion_os_cmo.agent_ugc import UGCAgent, validate_assets
from orion_os_cmo.common.result import Err, Ok
from orion_os_cmo.strategy_store.store import StrategyStore

from tests.test_strategy_store_persistence import make_ctx


def _sp(d):
    StrategyStore(Path(d)).write(make_ctx())
    return Path(d)


# ── adapter-creator-discovery ────────────────────────────────────────────────

class CreatorTransport:
    def __init__(self, creators, demo=True, email=True, raise_search=False):
        self.creators = creators
        self.demo = demo
        self.email = email
        self.raise_search = raise_search

    def post(self, path, body):
        if path == SEARCH_PATH:
            if self.raise_search:
                raise RuntimeError("down")
            return {"creators": self.creators}
        if path == EMAIL_PATH:
            if not self.email:
                raise RuntimeError("no email")
            return {"email": f"{body['handle']}@mail.test"}
        if path == DEMOGRAPHICS_PATH:
            if not self.demo:
                raise RuntimeError("no demo")
            return {"audience_fit": 0.8}
        return {}


CREATORS = [{"handle": "@alice", "url": "https://ig.com/alice", "followers": 12000},
            {"handle": "@bob", "url": "https://ig.com/bob", "followers": 8000}]


class CreatorDiscoveryT(unittest.TestCase):
    def test_ok_with_provenance(self):
        res = CreatorDiscoveryAdapter(CreatorTransport(CREATORS)).discover_creators(
            "productivity SaaS", "instagram", "micro")
        self.assertTrue(res.ok, res)
        c = res.value[0]
        self.assertEqual(c.handle, "@alice")
        self.assertEqual(c.audience_fit, 0.8)
        self.assertIsNotNone(c.source.demographics)
        self.assertEqual(c.source.profile, "stablesocial/creator_search")

    def test_demo_failure_null_fit(self):
        res = CreatorDiscoveryAdapter(CreatorTransport(CREATORS, demo=False)).discover_creators(
            "x", "instagram", "micro")
        c = res.value[0]
        self.assertIsNone(c.audience_fit)
        self.assertIsNone(c.source.demographics)  # grounding: no source without signal

    def test_transport_failure(self):
        res = CreatorDiscoveryAdapter(CreatorTransport([], raise_search=True)).discover_creators(
            "x", "instagram", "micro")
        self.assertEqual(res.error.kind, "transport")

    def test_empty_result(self):
        res = CreatorDiscoveryAdapter(CreatorTransport([])).discover_creators("x", "instagram", "micro")
        self.assertEqual(res.error.kind, "empty_result")

    def test_pbt_provenance_grounding(self):
        # audience_fit present => demographics source present, across both demo modes.
        for demo in (True, False):
            res = CreatorDiscoveryAdapter(CreatorTransport(CREATORS, demo=demo)).discover_creators(
                "x", "instagram", "micro")
            for c in res.value:
                if c.audience_fit is not None:
                    self.assertIsNotNone(c.source.demographics)


# ── adapter-video-gen ────────────────────────────────────────────────────────

class VideoTransport:
    def __init__(self, est_cost=0.11, raise_render=False, render_error=False):
        self.est_cost = est_cost
        self.raise_render = raise_render
        self.render_error = render_error
        self.calls = []

    def post(self, path, body):
        self.calls.append(path)
        if path == QUOTE_PATH:
            return {"est_cost": self.est_cost}
        if path == RENDER_PATH:
            if self.raise_render:
                raise RuntimeError("render down")
            if self.render_error:
                return {"error": "model failed"}
            return {"mp4_url": "https://cdn.test/v.mp4", "duration_s": 8.0, "provider": "runway"}
        return {}


class VideoGenT(unittest.TestCase):
    def test_within_cap_ok(self):
        t = VideoTransport(est_cost=0.11)
        res = VideoGenAdapter(t, per_run_cap=1.0).generate_video("a dog", "9:16", "1080p", True)
        self.assertTrue(res.ok, res)
        self.assertEqual(res.value.est_cost, 0.11)
        self.assertEqual(t.calls, [QUOTE_PATH, RENDER_PATH])

    def test_cap_exceeded_no_render(self):
        t = VideoTransport(est_cost=5.0)
        res = VideoGenAdapter(t, per_run_cap=1.0).generate_video("x", "9:16", "1080p", True)
        self.assertEqual(res.error.kind, "cap_exceeded")
        self.assertEqual(t.calls, [QUOTE_PATH])  # render never fired

    def test_invalid_aspect_no_call(self):
        t = VideoTransport()
        res = VideoGenAdapter(t, per_run_cap=1.0).generate_video("x", "4:5", "1080p", True)
        self.assertEqual(res.error.kind, "invalid_input")
        self.assertEqual(t.calls, [])

    def test_render_failure(self):
        t = VideoTransport(raise_render=True)
        res = VideoGenAdapter(t, per_run_cap=1.0).generate_video("x", "16:9", "1080p", True)
        self.assertEqual(res.error.kind, "render_failure")

    def test_pbt_cost_gate(self):
        import random
        rng = random.Random(9)
        for _ in range(200):
            cost = round(rng.uniform(0, 3), 3)
            cap = round(rng.uniform(0, 3), 3)
            t = VideoTransport(est_cost=max(cost, 0.001))
            res = VideoGenAdapter(t, per_run_cap=cap).generate_video("x", "1:1", "1080p", True)
            if max(cost, 0.001) > cap:
                self.assertEqual(res.error.kind, "cap_exceeded")
                self.assertNotIn(RENDER_PATH, t.calls)  # render never fired over-cap
            self.assertEqual(check_cap(0.5, 1.0), True)


# ── agent-influencer ─────────────────────────────────────────────────────────

class FakeDiscovery:
    def __init__(self, result): self._r = result
    def discover_creators(self, niche, platform, follower_tier): return self._r


class HandleLLM:
    def complete(self, *, system, prompt):
        # echo the handle from the prompt so personalization is verifiable
        for line in prompt.splitlines():
            if line.startswith("Creator handle:"):
                handle = line.split(":", 1)[1].strip().split(" ", 1)[0]
                return f"Hi {handle}, loved your work!"
        return "hello"


def creators(n=5, fit=0.8):
    out = []
    for i in range(n):
        out.append(Creator(f"@c{i}", f"https://ig/{i}", 1000 + i, None,
                           fit if i % 2 == 0 else None,
                           CreatorSource("search", None, "demo" if i % 2 == 0 else None)))
    return out


class InfluencerT(unittest.TestCase):
    def test_top_n_cap_and_fields(self):
        with tempfile.TemporaryDirectory() as d:
            agent = InfluencerAgent(_sp(d), FakeDiscovery(Ok(creators(8))), HandleLLM(),
                                    InfluencerAgentConfig(top_n=3))
            res = agent.run()
            self.assertTrue(res.ok)
            self.assertEqual(len(res.value), 3)
            for item in res.value:
                self.assertIn(item.creator.handle, item.draft_message)  # personalization

    def test_null_fit_passthrough(self):
        with tempfile.TemporaryDirectory() as d:
            c = [Creator("@x", "u", 100, None, None, CreatorSource("s", None, None))]
            agent = InfluencerAgent(_sp(d), FakeDiscovery(Ok(c)), HandleLLM())
            self.assertIsNone(agent.run().value[0].fit_score)

    def test_discovery_failed(self):
        from orion_os_cmo.adapters.creator_discovery.types import CreatorDiscoveryError, DiscoveryErrorSource
        with tempfile.TemporaryDirectory() as d:
            err = Err(CreatorDiscoveryError("empty_result", "none", DiscoveryErrorSource("p", "n", "ig")))
            agent = InfluencerAgent(_sp(d), FakeDiscovery(err), HandleLLM())
            self.assertEqual(agent.run().error.kind, "discovery_failed")

    def test_pbt_provenance_and_grounding(self):
        with tempfile.TemporaryDirectory() as d:
            cs = creators(5)
            agent = InfluencerAgent(_sp(d), FakeDiscovery(Ok(cs)), HandleLLM(),
                                    InfluencerAgentConfig(top_n=10))
            items = agent.run().value
            self.assertEqual(validate_outreach(items), [])
            returned = {it.creator.handle: it.creator for it in items}
            for c in cs:
                self.assertEqual(returned[c.handle], c)  # unmodified record


# ── agent-ugc ────────────────────────────────────────────────────────────────

class ExpanderLLM:
    def __init__(self, aspect="9:16"): self.aspect = aspect
    def complete_json(self, *, system, prompt):
        return {"prompt": "a cinematic shot", "aspect": self.aspect, "resolution": "1080p"}


class CapAdapter:
    """Returns Ok for the first `ok_count` briefs, then cap_exceeded."""
    def __init__(self, ok_count):
        self.ok_count = ok_count
        self.calls = 0
    def generate_video(self, prompt, aspect, resolution, audio):
        from orion_os_cmo.adapters.video_gen.types import VideoAsset, VideoErrorSource, VideoGenError
        self.calls += 1
        if self.calls <= self.ok_count:
            return Ok(VideoAsset("https://cdn/v.mp4", 8.0, 0.11, {"aspect": aspect}))
        return Err(VideoGenError("cap_exceeded", "over budget", VideoErrorSource("p", "h")))


class UGCT(unittest.TestCase):
    def test_within_cap(self):
        with tempfile.TemporaryDirectory() as d:
            agent = UGCAgent(_sp(d), CapAdapter(ok_count=5), ExpanderLLM())
            res = agent.run(["brief one", "brief two"])
            self.assertEqual(len(res.assets), 2)
            self.assertFalse(res.cap_exceeded)
            self.assertEqual(res.assets[0].brief, "brief one")  # unmodified
            self.assertEqual(validate_assets(res.assets), [])

    def test_cap_stops_loop(self):
        with tempfile.TemporaryDirectory() as d:
            adapter = CapAdapter(ok_count=1)
            agent = UGCAgent(_sp(d), adapter, ExpanderLLM())
            res = agent.run(["b1", "b2", "b3"])
            self.assertEqual(len(res.assets), 1)
            self.assertTrue(res.cap_exceeded)
            self.assertEqual(adapter.calls, 2)  # 1 ok + 1 cap; b3 never sent

    def test_missing_context(self):
        with tempfile.TemporaryDirectory() as d:
            agent = UGCAgent(Path(d), CapAdapter(5), ExpanderLLM())
            res = agent.run(["b1"])
            self.assertEqual(res.error.kind, "missing_context")

    def test_expander_bad_aspect(self):
        with tempfile.TemporaryDirectory() as d:
            adapter = CapAdapter(5)
            agent = UGCAgent(_sp(d), adapter, ExpanderLLM(aspect="4:5"))
            res = agent.run(["b1"])
            self.assertEqual(res.error.kind, "expander_error")
            self.assertEqual(adapter.calls, 0)  # adapter never called


if __name__ == "__main__":
    unittest.main()
