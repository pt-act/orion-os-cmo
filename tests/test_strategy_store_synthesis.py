import unittest
from typing import Any

from orion_os_cmo.strategy_store.context import validate_strategy_context
from orion_os_cmo.strategy_store.evidence import EvidenceItem, EvidenceSet, EvidenceSource
from orion_os_cmo.strategy_store.synthesize import synthesize_strategy


def make_evidence() -> EvidenceSet:
    return EvidenceSet(built_at="t", items=[
        EvidenceItem(id="ev-0", kind="page",
                     source=EvidenceSource("firecrawl/scrape", "https://acme.test/"),
                     text="Acme PM tool", title="Acme"),
        EvidenceItem(id="ev-1", kind="search_result",
                     source=EvidenceSource("exa/search", "https://notion.so"),
                     text="Notion workspace", title="Notion"),
    ])


# One grounded + one ungrounded competitor and differentiator each.
GROUNDED_OUTPUT: dict[str, Any] = {
    "brand_voice": {"tone": "direct", "register": "casual", "do": ["be clear"], "dont": ["hype"], "sample_phrases": ["ship it"]},
    "icp": {"segments": ["startups"], "pains": ["chaos"], "triggers": ["scaling"]},
    "competitors": [
        {"name": "Notion", "url": "https://notion.so", "positioning": "all-in-one", "source": "https://notion.so"},
        {"name": "Ghost", "url": "https://ghost.example", "positioning": "invented", "source": "https://not-in-evidence.test"},
    ],
    "positioning": {"one_liner": "PM for teams", "category": "project management", "differentiators": [
        {"claim": "faster setup", "source": "https://acme.test/"},
        {"claim": "made up", "source": "https://nowhere.test"},
    ]},
    "growth_playbook": {"channels": ["seo"], "priorities": ["content"], "notes": "focus organic"},
}


class FakeLLM:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def complete_json(self, *, system: str, prompt: str) -> dict[str, Any]:
        return self._payload


class SynthesisGroup2(unittest.TestCase):
    def test_2_3_produces_all_five_sections(self) -> None:
        res = synthesize_strategy(make_evidence(), FakeLLM(GROUNDED_OUTPUT))
        self.assertTrue(res.ok)
        ctx = res.value
        self.assertTrue(ctx.brand_voice.tone)
        self.assertTrue(ctx.icp.segments)
        self.assertTrue(ctx.positioning.one_liner)
        self.assertTrue(ctx.growth_playbook.channels)
        self.assertEqual(ctx.meta.version, 1)

    def test_2_4_ungrounded_claims_are_rejected(self) -> None:
        res = synthesize_strategy(make_evidence(), FakeLLM(GROUNDED_OUTPUT))
        self.assertTrue(res.ok)
        ctx = res.value
        # The competitor + differentiator whose source is not in evidence are dropped.
        self.assertEqual([c.name for c in ctx.competitors], ["Notion"])
        self.assertEqual([d.claim for d in ctx.positioning.differentiators], ["faster setup"])
        evidence_urls = {"https://acme.test/", "https://notion.so"}
        for c in ctx.competitors:
            self.assertIn(c.source, evidence_urls)
        for d in ctx.positioning.differentiators:
            self.assertIn(d.source, evidence_urls)

    def test_2_5_schema_conformance(self) -> None:
        res = synthesize_strategy(make_evidence(), FakeLLM(GROUNDED_OUTPUT))
        self.assertTrue(res.ok)
        self.assertEqual(validate_strategy_context(res.value), [])

    def test_missing_section_is_structured_invalid_output(self) -> None:
        bad = dict(GROUNDED_OUTPUT)
        del bad["growth_playbook"]
        res = synthesize_strategy(make_evidence(), FakeLLM(bad))
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "invalid_output")

    def test_llm_failure_is_structured(self) -> None:
        class BoomLLM:
            def complete_json(self, *, system: str, prompt: str) -> dict[str, Any]:
                raise RuntimeError("model unavailable")

        res = synthesize_strategy(make_evidence(), BoomLLM())
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "llm_error")


if __name__ == "__main__":
    unittest.main()
