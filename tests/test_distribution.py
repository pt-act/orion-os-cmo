"""distribution milestone — reddit-listen, social-publish, reddit, x, linkedin."""

import tempfile
import unittest
from pathlib import Path

from orion_os_cmo.adapters.reddit_listen import RedditAdapter
from orion_os_cmo.adapters.social_publish import (
    ApprovalValidator,
    IdempotencyStore,
    SocialPublishAdapter,
)
from orion_os_cmo.agent_linkedin import LinkedInAgent, build_linkedin_prompt
from orion_os_cmo.agent_reddit import RedditAgent
from orion_os_cmo.agent_x import XAgent, build_x_prompt, validate_x_drafts
from orion_os_cmo.strategy_store.store import StrategyStore

from tests.test_strategy_store_persistence import make_ctx


def _sp(d):
    StrategyStore(Path(d)).write(make_ctx())
    return Path(d)


# ── adapter-reddit-listen ────────────────────────────────────────────────────

def reddit_fixture():
    return {"threads": [
        {"url": "https://reddit.com/r/SaaS/1", "subreddit": "SaaS", "intent": "question",
         "engagement": 42, "snippet": "How do you manage projects?"},
        {"url": "https://reddit.com/r/SaaS/2", "subreddit": "SaaS", "intent": "other",
         "engagement": 3, "snippet": "Just shipped my app"},
    ]}


class RedditAdapterT(unittest.TestCase):
    def _t(self, resp, raise_it=False):
        class T:
            def post(self, path, body):
                if raise_it:
                    raise RuntimeError("down")
                return resp
        return T()

    def test_ok(self):
        res = RedditAdapter(self._t(reddit_fixture())).reddit_search(["project management"])
        self.assertTrue(res.ok, res)
        self.assertEqual(len(res.value.threads), 2)
        for t in res.value.threads:
            self.assertTrue(t.url and t.subreddit and t.snippet and t.engagement >= 0)

    def test_transport(self):
        res = RedditAdapter(self._t({}, raise_it=True)).reddit_search(["x"])
        self.assertEqual(res.error.kind, "transport")

    def test_api_error(self):
        res = RedditAdapter(self._t({"error": "rate limit"})).reddit_search(["x"])
        self.assertEqual(res.error.kind, "api_error")

    def test_no_results_not_ok_empty(self):
        res = RedditAdapter(self._t({"threads": []})).reddit_search(["x"])
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "no_results")

    def test_idempotent(self):
        a = RedditAdapter(self._t(reddit_fixture())).reddit_search(["x"], ["SaaS"])
        b = RedditAdapter(self._t(reddit_fixture())).reddit_search(["x"], ["SaaS"])
        self.assertEqual(a.value, b.value)


# ── adapter-social-publish ───────────────────────────────────────────────────

class CountingTransport:
    def __init__(self, resp=None, raise_it=False):
        self.resp = resp or {"url": "https://x.com/p/1", "id": "1"}
        self.raise_it = raise_it
        self.count = 0

    def post(self, path, body):
        self.count += 1
        if self.raise_it:
            raise RuntimeError("down")
        return self.resp


class SocialPublishT(unittest.TestCase):
    def _adapter(self, t, expected="tok"):
        return SocialPublishAdapter({"x": t, "linkedin": t}, ApprovalValidator(expected), IdempotencyStore())

    def test_valid_post(self):
        t = CountingTransport()
        res = self._adapter(t).publish_post("x", "hello world", "tok")
        self.assertTrue(res.ok, res)
        self.assertEqual(res.value.url, "https://x.com/p/1")
        self.assertEqual(t.count, 1)

    def test_no_token_no_transport(self):
        t = CountingTransport()
        res = self._adapter(t).publish_post("x", "hello", None)
        self.assertEqual(res.error.kind, "no_approval")
        self.assertEqual(t.count, 0)

    def test_empty_token_no_transport(self):
        t = CountingTransport()
        res = self._adapter(t).publish_post("x", "hello", "")
        self.assertEqual(res.error.kind, "no_approval")
        self.assertEqual(t.count, 0)

    def test_already_posted(self):
        t = CountingTransport()
        adapter = self._adapter(t)
        adapter.publish_post("x", "same content", "tok")
        res = adapter.publish_post("x", "same content", "tok")
        self.assertEqual(res.error.kind, "already_posted")
        self.assertEqual(t.count, 1)  # not called a second time

    def test_unsupported_platform(self):
        t = CountingTransport()
        res = self._adapter(t).publish_post("tiktok", "x", "tok")
        self.assertEqual(res.error.kind, "unsupported_platform")
        self.assertEqual(t.count, 0)

    def test_transport_failure(self):
        t = CountingTransport(raise_it=True)
        res = self._adapter(t).publish_post("x", "x", "tok")
        self.assertEqual(res.error.kind, "transport")

    def test_pbt_gate_absolute(self):
        for bad in (None, "", "   ", "wrong-token"):
            t = CountingTransport()
            res = self._adapter(t).publish_post("x", "content", bad)
            self.assertEqual(res.error.kind, "no_approval")
            self.assertEqual(t.count, 0)


# ── agent-reddit ─────────────────────────────────────────────────────────────

class FakeReddit:
    def __init__(self, result): self._r = result
    def reddit_search(self, keywords, subreddits=None): return self._r


class TextLLM:
    def __init__(self, text="Helpful reply here."): self.text = text
    def complete(self, *, system, prompt): return self.text


class AgentRedditT(unittest.TestCase):
    def test_drafts_high_intent_only(self):
        from orion_os_cmo.adapters.reddit_listen.types import RedditSearchResult, Thread
        from orion_os_cmo.common.result import Ok
        threads = RedditSearchResult([
            Thread("u1", "SaaS", "question", 10, "How to manage?"),
            Thread("u2", "SaaS", "other", 1, "random"),
        ])
        with tempfile.TemporaryDirectory() as d:
            agent = RedditAgent(_sp(d), FakeReddit(Ok(threads)), TextLLM())
            res = agent.run()
            self.assertTrue(res.ok)
            self.assertEqual(len(res.value), 1)  # "other" discarded
            self.assertEqual(res.value[0].thread_url, "u1")

    def test_search_failed(self):
        from orion_os_cmo.adapters.reddit_listen.types import ErrorSource, RedditError
        from orion_os_cmo.common.result import Err
        with tempfile.TemporaryDirectory() as d:
            agent = RedditAgent(_sp(d), FakeReddit(Err(RedditError("no_results", "x", ErrorSource("t", "q")))),
                                TextLLM())
            self.assertEqual(agent.run().error.kind, "search_failed")

    def test_skipped_manifest_surfaced(self):
        # Q-10: low-intent threads are recorded in the scored-but-skipped manifest.
        from orion_os_cmo.adapters.reddit_listen.types import RedditSearchResult, Thread
        from orion_os_cmo.common.result import Ok
        threads = RedditSearchResult([
            Thread("u1", "SaaS", "question", 10, "q1"),
            Thread("u2", "SaaS", "other", 1, "noise"),
        ])
        with tempfile.TemporaryDirectory() as d:
            agent = RedditAgent(_sp(d), FakeReddit(Ok(threads)), TextLLM())
            agent.run()
            self.assertEqual(len(agent.skipped), 1)
            self.assertEqual(agent.skipped[0].thread_url, "u2")
            self.assertEqual(agent.skipped[0].reason, "low_intent")

    def test_llm_failure_skips_thread(self):
        from orion_os_cmo.adapters.reddit_listen.types import RedditSearchResult, Thread
        from orion_os_cmo.common.result import Ok
        class FlakyLLM:
            def __init__(self): self.n = 0
            def complete(self, *, system, prompt):
                self.n += 1
                if self.n == 1:
                    raise RuntimeError("boom")
                return "second reply"
        threads = RedditSearchResult([
            Thread("u1", "SaaS", "question", 10, "q1"),
            Thread("u2", "SaaS", "complaint", 5, "q2"),
        ])
        with tempfile.TemporaryDirectory() as d:
            agent = RedditAgent(_sp(d), FakeReddit(Ok(threads)), FlakyLLM())
            res = agent.run()
            self.assertEqual(len(res.value), 1)  # first skipped, second kept
            self.assertEqual(res.value[0].thread_url, "u2")


# ── agent-x ──────────────────────────────────────────────────────────────────

class JsonLLM:
    def __init__(self, payload): self.payload = payload
    def complete_json(self, *, system, prompt): return self.payload


X_OK = {"drafts": [
    {"kind": "post", "content": "Post 1"}, {"kind": "post", "content": "Post 2"},
    {"kind": "post", "content": "Post 3"}, {"kind": "thread", "content": "1/ a\n2/ b"},
]}


class AgentXT(unittest.TestCase):
    def test_ok_counts(self):
        with tempfile.TemporaryDirectory() as d:
            res = XAgent(_sp(d), JsonLLM(X_OK)).run()
            self.assertTrue(res.ok, res)
            posts = [x for x in res.value if x.kind == "post"]
            threads = [x for x in res.value if x.kind == "thread"]
            self.assertGreaterEqual(len(posts), 3)
            self.assertGreaterEqual(len(threads), 1)

    def test_malformed_retry_then_err(self):
        with tempfile.TemporaryDirectory() as d:
            res = XAgent(_sp(d), JsonLLM({"drafts": [{"kind": "bad", "content": ""}]})).run()
            self.assertFalse(res.ok)
            self.assertEqual(res.error.kind, "schema_invalid")

    def test_prompt_has_brand_voice(self):
        system, _ = build_x_prompt({"brand_voice": {"tone": "TONEX", "register": "REGX"}})
        self.assertIn("TONEX", system)
        self.assertIn("REGX", system)

    def test_validator_rejects_bad(self):
        with self.assertRaises(Exception):
            validate_x_drafts([{"kind": "post", "content": ""}])

    def test_thread_valid_format_passes(self):
        validate_x_drafts([{"kind": "thread", "content": "1/ first\n2/ second"}])

    def test_thread_missing_numbering_fails(self):
        with self.assertRaises(Exception):
            validate_x_drafts([{"kind": "thread", "content": "first turn\nsecond turn"}])


# ── agent-linkedin ───────────────────────────────────────────────────────────

LI_OK = {"drafts": [{"content": "Post A"}, {"content": "Post B"}, {"content": "Post C"}]}


class AgentLinkedInT(unittest.TestCase):
    def test_ok(self):
        with tempfile.TemporaryDirectory() as d:
            res = LinkedInAgent(_sp(d), JsonLLM(LI_OK)).run()
            self.assertTrue(res.ok)
            self.assertEqual(len(res.value), 3)
            for draft in res.value:
                self.assertTrue(draft.content)

    def test_malformed_err(self):
        with tempfile.TemporaryDirectory() as d:
            res = LinkedInAgent(_sp(d), JsonLLM({"drafts": [{"content": ""}]})).run()
            self.assertEqual(res.error.kind, "schema_invalid")

    def test_prompt_has_brand_voice(self):
        system, _ = build_linkedin_prompt({"brand_voice": {"tone": "TLI", "register": "RLI"}})
        self.assertIn("TLI", system)
        self.assertIn("RLI", system)


if __name__ == "__main__":
    unittest.main()
