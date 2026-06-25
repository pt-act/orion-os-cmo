"""agent-writer — focused + PBT tests (keyword provenance, overlay, determinism)."""

import tempfile
import unittest
from pathlib import Path

from orion_os_cmo.agent_geo.types import GapRef, GeoFindings, GeoFix
from orion_os_cmo.agent_seo.types import KeywordGap, SeoFindings
from orion_os_cmo.agent_writer import WriterAgent, WriterAgentConfig, validate_articles
from orion_os_cmo.strategy_store.store import StrategyStore

from tests.test_strategy_store_persistence import make_ctx


def seo():
    return SeoFindings(ranked_fixes=[], keyword_gaps=[
        KeywordGap("project management software", 900),
        KeywordGap("team collaboration tools", 500),
        KeywordGap("remote work apps", 300),
        KeywordGap("low priority kw", 50),
    ], meta={})


def geo():
    return GeoFindings(score=0.4, score_delta=None, fixes=[
        GeoFix("FAQ for PM", "Q: What is project management software? A: ...", "faq",
               GapRef("gpt", "best project management software?")),
    ], competitor_gaps=[], meta={})


def llm_payload():
    return {"title": "The Best Project Management Software", "body": "Body copy here.",
            "title_tag": "Best PM Software 2026", "meta_description": "A guide.", "slug": "best-pm"}


class FixedLLM:
    def __init__(self, payload): self.payload = payload
    def complete_json(self, *, system, prompt): return dict(self.payload)


def _sp(d):
    StrategyStore(Path(d)).write(make_ctx())
    return Path(d)


class AgentWriter(unittest.TestCase):
    def test_count_capped_and_ranked(self):
        with tempfile.TemporaryDirectory() as d:
            agent = WriterAgent(_sp(d), seo(), geo(), FixedLLM(llm_payload()),
                                WriterAgentConfig(max_articles=2))
            res = agent.run()
            self.assertTrue(res.ok, res)
            self.assertEqual(len(res.value), 2)
            # ranked by impressions desc -> top two keywords
            self.assertEqual(res.value[0].target_keyword, "project management software")
            self.assertEqual(res.value[1].target_keyword, "team collaboration tools")

    def test_geo_overlay_in_body(self):
        with tempfile.TemporaryDirectory() as d:
            agent = WriterAgent(_sp(d), seo(), geo(), FixedLLM(llm_payload()),
                                WriterAgentConfig(max_articles=1))
            article = agent.run().value[0]
            self.assertIn("## FAQ", article.body)
            self.assertEqual(article.geo_fix_refs[0], GapRef("gpt", "best project management software?"))

    def test_meta_limits_enforced(self):
        long = {"title": "x" * 100, "body": "b", "title_tag": "y" * 100,
                "meta_description": "z" * 300, "slug": "s"}
        with tempfile.TemporaryDirectory() as d:
            agent = WriterAgent(_sp(d), seo(), geo(), FixedLLM(long), WriterAgentConfig(max_articles=1))
            a = agent.run().value[0]
            self.assertLessEqual(len(a.meta.title_tag), 60)
            self.assertLessEqual(len(a.meta.meta_description), 160)

    def test_strategy_missing(self):
        with tempfile.TemporaryDirectory() as d:
            agent = WriterAgent(Path(d), seo(), geo(), FixedLLM(llm_payload()))
            self.assertEqual(agent.run().error.kind, "strategy_missing")

    def test_llm_error(self):
        class Boom:
            def complete_json(self, *, system, prompt): raise RuntimeError("x")
        with tempfile.TemporaryDirectory() as d:
            agent = WriterAgent(_sp(d), seo(), geo(), Boom(), WriterAgentConfig(max_articles=1))
            self.assertEqual(agent.run().error.kind, "llm_error")

    def test_pbt_provenance_and_schema(self):
        with tempfile.TemporaryDirectory() as d:
            agent = WriterAgent(_sp(d), seo(), geo(), FixedLLM(llm_payload()),
                                WriterAgentConfig(max_articles=3))
            articles = agent.run().value
            self.assertEqual(validate_articles(articles, seo()), [])
            valid = {g.query for g in seo().keyword_gaps}
            for a in articles:
                self.assertIn(a.target_keyword, valid)

    def test_pbt_determinism(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            a = WriterAgent(_sp(d1), seo(), geo(), FixedLLM(llm_payload()),
                            WriterAgentConfig(max_articles=2)).run().value
            b = WriterAgent(_sp(d2), seo(), geo(), FixedLLM(llm_payload()),
                            WriterAgentConfig(max_articles=2)).run().value
            self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
