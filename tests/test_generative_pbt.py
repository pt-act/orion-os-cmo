"""Generative property-based tests (G-2).

The audit found several criteria labelled "PBT" were satisfied by fixed-fixture
example tests. These re-establish the precision-owning invariants as genuinely
generative properties over many randomized inputs (stdlib ``random`` — the same
standard the auditor accepted for adapter-video-gen and client-workspace). Each
plants adversarial/true-negative cases, not just happy paths.
"""

import random
import string
import tempfile
import unittest
from pathlib import Path

from orion_os_cmo.common.result import Ok
from orion_os_cmo.strategy_store.store import StrategyStore

from tests.test_strategy_store_persistence import make_ctx


def _sp(d):
    StrategyStore(Path(d)).write(make_ctx())
    return Path(d)


def _word(rng, n=6):
    return "".join(rng.choices(string.ascii_lowercase, k=rng.randint(3, n)))


# ── agent-seo: provenance + determinism (Q-5/Q-6 + spec PBT #1/#2) ───────────

class SeoGenerative(unittest.TestCase):
    def test_provenance_only_real_issue_ids_survive(self):
        from orion_os_cmo.adapters.seo_audit.types import AuditReport, Issue
        from orion_os_cmo.agent_seo import SeoAgent
        from tests.test_agent_seo import FakeAnalytics, FakeAudit, snapshot
        rng = random.Random(101)
        with tempfile.TemporaryDirectory() as d:
            sp = _sp(d)
            for _ in range(60):
                n = rng.randint(1, 6)
                issues = [Issue(rng.choice(["critical", "warning", "info"]),
                                _word(rng), _word(rng), _word(rng)) for _ in range(n)]
                report = AuditReport("u", 70, issues, [], {"provider": "p",
                                     "lighthouse_version": "1", "audited_at": "t"})
                valid_ids = [f"issue-{i}" for i in range(n)]
                # Mix real ids with fabricated ones in random order.
                raw_fixes = [{"issue_id": rng.choice(valid_ids), "fix": _word(rng)}
                             for _ in range(rng.randint(0, 5))]
                raw_fixes += [{"issue_id": f"issue-{rng.randint(100, 999)}", "fix": "FAKE"}
                              for _ in range(rng.randint(0, 4))]
                rng.shuffle(raw_fixes)

                class LLM:
                    def complete_json(self, *, system, prompt):
                        return {"ranked_fixes": raw_fixes, "keyword_gaps": []}

                agent = SeoAgent(sp, FakeAudit(Ok(report)), FakeAnalytics(Ok(snapshot())), LLM())
                res = agent.run("u", run_at="fixed")
                self.assertTrue(res.ok)
                for fix in res.value.ranked_fixes:
                    self.assertIn(fix.issue_id, set(valid_ids))   # no fabricated id ships
                    # snippet/severity grounded from the audit, never the model
                    src = issues[int(fix.issue_id.split("-")[1])]
                    self.assertEqual(fix.snippet, src.snippet)
                    self.assertEqual(fix.severity, src.severity)

    def test_determinism_full_equality(self):
        from orion_os_cmo.agent_seo import SeoAgent
        from tests.test_agent_seo import FakeAnalytics, FakeAudit, FixedLLM, GOOD_LLM, audit_report, snapshot
        with tempfile.TemporaryDirectory() as d:
            sp = _sp(d)
            agent = SeoAgent(sp, FakeAudit(Ok(audit_report())), FakeAnalytics(Ok(snapshot())),
                             FixedLLM(GOOD_LLM))
            outs = [agent.run("u", run_at="2026-06-20T00:00:00Z").value for _ in range(15)]
            self.assertTrue(all(o == outs[0] for o in outs))


# ── adapter-creator-discovery: fabricated-fit rejection ──────────────────────

class CreatorGenerative(unittest.TestCase):
    def test_planted_fit_in_search_record_is_ignored(self):
        from orion_os_cmo.adapters.creator_discovery import CreatorDiscoveryAdapter
        from orion_os_cmo.adapters.creator_discovery.adapter import (
            DEMOGRAPHICS_PATH, EMAIL_PATH, SEARCH_PATH)
        rng = random.Random(202)
        for _ in range(60):
            # Attacker plants audience_fit in the (untrusted) search record.
            n = rng.randint(1, 5)
            recs = [{"handle": f"@{_word(rng)}", "url": f"https://ig/{i}",
                     "followers": rng.randint(1, 1_000_000),
                     "audience_fit": round(rng.random(), 3)} for i in range(n)]
            demo_works = rng.random() < 0.5

            class T:
                def post(self, path, body):
                    if path == SEARCH_PATH:
                        return {"creators": recs}
                    if path == EMAIL_PATH:
                        raise RuntimeError("no email")
                    if path == DEMOGRAPHICS_PATH:
                        if demo_works:
                            return {"audience_fit": 0.5}
                        raise RuntimeError("no demo")
                    return {}

            res = CreatorDiscoveryAdapter(T()).discover_creators("n", "instagram", "micro")
            self.assertTrue(res.ok)
            for c in res.value:
                if demo_works:
                    self.assertEqual(c.audience_fit, 0.5)          # only from demographics tool
                    self.assertIsNotNone(c.source.demographics)
                else:
                    self.assertIsNone(c.audience_fit)              # planted value never used
                    self.assertIsNone(c.source.demographics)


# ── agent-influencer: provenance + grounding ─────────────────────────────────

class InfluencerGenerative(unittest.TestCase):
    def test_records_unmodified_and_fit_grounded(self):
        from orion_os_cmo.adapters.creator_discovery.types import Creator, CreatorSource
        from orion_os_cmo.agent_influencer import InfluencerAgent, InfluencerAgentConfig
        from tests.test_reach import FakeDiscovery, HandleLLM
        rng = random.Random(303)
        with tempfile.TemporaryDirectory() as d:
            sp = _sp(d)
            for _ in range(50):
                n = rng.randint(1, 12)
                cs = []
                for i in range(n):
                    has_fit = rng.random() < 0.5
                    fit = round(rng.random(), 3) if has_fit else None
                    cs.append(Creator(f"@{_word(rng)}", f"u{i}", rng.randint(1, 9999), None, fit,
                                      CreatorSource("s", None, "demo" if has_fit else None)))
                top_n = rng.randint(1, 15)
                agent = InfluencerAgent(sp, FakeDiscovery(Ok(cs)), HandleLLM(),
                                        InfluencerAgentConfig(top_n=top_n))
                items = agent.run().value
                self.assertLessEqual(len(items), top_n)
                by_handle = {c.handle: c for c in cs}
                for it in items:
                    self.assertEqual(it.creator, by_handle[it.creator.handle])  # unmodified
                    if it.fit_score is not None:
                        self.assertIsNotNone(it.creator.audience_fit)           # grounded
                    self.assertIn(it.creator.handle, it.draft_message)


# ── agent-ugc: cost-control + brief provenance ───────────────────────────────

class UgcGenerative(unittest.TestCase):
    def test_cap_stops_loop_briefs_unmodified(self):
        from orion_os_cmo.agent_ugc import UGCAgent
        from tests.test_reach import CapAdapter, ExpanderLLM
        rng = random.Random(404)
        with tempfile.TemporaryDirectory() as d:
            sp = _sp(d)
            for _ in range(80):
                nbriefs = rng.randint(1, 7)
                ok_count = rng.randint(0, 8)
                briefs = [f"brief {_word(rng)} {i}" for i in range(nbriefs)]
                adapter = CapAdapter(ok_count=ok_count)
                res = UGCAgent(sp, adapter, ExpanderLLM()).run(list(briefs))
                expected_assets = min(ok_count, nbriefs)
                self.assertEqual(len(res.assets), expected_assets)
                self.assertEqual(res.cap_exceeded, ok_count < nbriefs)
                # briefs ride along unmodified, in order; no brief after the cap was sent
                for asset, original in zip(res.assets, briefs):
                    self.assertEqual(asset.brief, original)
                self.assertEqual(adapter.calls, min(ok_count + 1, nbriefs)
                                 if ok_count < nbriefs else nbriefs)


# ── adapter-social-publish: absolute approval gate ───────────────────────────

class SocialGenerative(unittest.TestCase):
    def test_gate_never_calls_transport_without_valid_token(self):
        from orion_os_cmo.adapters.social_publish import (
            ApprovalValidator, IdempotencyStore, SocialPublishAdapter)
        from tests.test_distribution import CountingTransport
        rng = random.Random(505)
        for _ in range(150):
            expected = "secret-" + _word(rng)
            bad = rng.choice([None, "", "   ", "\t", expected + "x", _word(rng)])
            platform = rng.choice(["x", "linkedin", "tiktok", "fb"])
            content = _word(rng, 20)
            t = CountingTransport()
            adapter = SocialPublishAdapter({"x": t, "linkedin": t},
                                           ApprovalValidator(expected), IdempotencyStore())
            res = adapter.publish_post(platform, content, bad)
            self.assertFalse(res.ok)
            # any invalid token → no_approval and zero transport calls (gate is first)
            if res.error.kind != "unsupported_platform":
                self.assertEqual(res.error.kind, "no_approval")
            self.assertEqual(t.count, 0)


# ── agent-reddit: url provenance ─────────────────────────────────────────────

class RedditGenerative(unittest.TestCase):
    def test_every_draft_url_in_fixture(self):
        from orion_os_cmo.adapters.reddit_listen.types import RedditSearchResult, Thread
        from orion_os_cmo.agent_reddit import RedditAgent
        from tests.test_distribution import FakeReddit, TextLLM
        intents = ["question", "complaint", "comparison", "recommendation", "other"]
        rng = random.Random(606)
        with tempfile.TemporaryDirectory() as d:
            sp = _sp(d)
            for _ in range(60):
                n = rng.randint(1, 8)
                threads = [Thread(f"https://r/{_word(rng)}/{i}", _word(rng),
                                  rng.choice(intents), rng.randint(0, 999), _word(rng, 12))
                           for i in range(n)]
                urls = {t.url for t in threads}
                agent = RedditAgent(sp, FakeReddit(Ok(RedditSearchResult(threads))), TextLLM())
                res = agent.run()
                self.assertTrue(res.ok)
                for draft in res.value:
                    self.assertIn(draft.thread_url, urls)            # never fabricated
                    self.assertIn(draft.intent, {"question", "complaint",
                                                 "comparison", "recommendation"})


# ── agent-x / agent-linkedin: schema validator ───────────────────────────────

class SocialAgentSchemaGenerative(unittest.TestCase):
    def test_x_validator_rejects_any_malformed_member(self):
        from orion_os_cmo.agent_x import validate_x_drafts
        from orion_os_cmo.agent_x.agent import _ValidationError
        rng = random.Random(707)
        for _ in range(120):
            good = [{"kind": k, "content": f"1/ {_word(rng, 30)}" if k == "thread" else _word(rng, 30)}
                    for k in (rng.choice(["post", "thread"]) for _ in range(rng.randint(1, 6)))]
            self.assertEqual(len(validate_x_drafts(good)), len(good))
            # inject one malformed member at a random position → must raise
            bad = list(good)
            bad.insert(rng.randint(0, len(bad)),
                       rng.choice([{"kind": "bad", "content": "x"},
                                    {"kind": "post", "content": ""},
                                    {"kind": "thread", "content": "no numbering"},
                                    {"content": "no kind"}]))
            with self.assertRaises(_ValidationError):
                validate_x_drafts(bad)

    def test_linkedin_validator_rejects_empty_content(self):
        from orion_os_cmo.agent_linkedin import validate_linkedin_drafts
        from orion_os_cmo.agent_linkedin.agent import _ValidationError
        rng = random.Random(808)
        for _ in range(120):
            good = [{"content": _word(rng, 40)} for _ in range(rng.randint(1, 5))]
            self.assertEqual(len(validate_linkedin_drafts(good)), len(good))
            bad = list(good)
            bad.insert(rng.randint(0, len(bad)), rng.choice([{"content": ""}, {"content": "   "}, {}]))
            with self.assertRaises(_ValidationError):
                validate_linkedin_drafts(bad)


if __name__ == "__main__":
    unittest.main()
