"""Brief renderer — the product surface (glass box)."""

import unittest

from orion_os_cmo.orchestrator import assemble_brief, render_markdown
from orion_os_cmo.orchestrator.types import AgentOutcome, ApprovalQueueItem, Delta, PrioritizedItem, WeeklyBrief


def _brief(
    items: list[PrioritizedItem] | None = None,
    deltas: list[Delta] | None = None,
    queue: list[ApprovalQueueItem] | None = None,
) -> WeeklyBrief:
    return WeeklyBrief(
        week_key="2026-W25",
        generated_at="2026-06-25T00:00:00Z",
        prioritized_items=items or [],
        per_agent_sections={},
        week_over_week_deltas=deltas or [],
        approval_queue=queue or [],
    )


class BriefRenderer(unittest.TestCase):
    def test_populated_items(self):
        brief = _brief(items=[
            PrioritizedItem(rank=1, agent="seo", item_id="i-1",
                            summary="5 ranked fixes", action="review"),
            PrioritizedItem(rank=2, agent="x", item_id="i-2",
                            summary="3 X drafts", action="approve"),
        ])
        md = render_markdown(brief)
        self.assertIn("1. **seo**", md)
        self.assertIn("2. **x**", md)
        self.assertIn("i-1", md)
        self.assertIn("i-2", md)

    def test_items_without_item_id(self):
        brief = _brief(items=[
            PrioritizedItem(rank=1, agent="geo", item_id="",
                            summary="GEO score 0.6", action="review"),
        ])
        md = render_markdown(brief)
        self.assertIn("**geo**", md)
        self.assertNotIn("()", md)  # no empty link

    def test_empty_items_fallback(self):
        md = render_markdown(_brief(items=[]))
        self.assertIn("No agent produced output", md)

    def test_deltas_rendered(self):
        brief = _brief(deltas=[
            Delta(metric="seo_score", prior=80.0, current=85.0, delta=5.0, source="tool.seo_audit"),
        ])
        md = render_markdown(brief)
        self.assertIn("seo_score", md)
        self.assertIn("+5", md)

    def test_empty_deltas_fallback(self):
        md = render_markdown(_brief(deltas=[]))
        self.assertIn("No prior history", md)

    def test_approval_queue_rendered(self):
        brief = _brief(queue=[
            ApprovalQueueItem(item_id="i-1", agent="x", type="post", summary="Hello world"),
        ])
        md = render_markdown(brief)
        self.assertIn("i-1", md)
        self.assertIn("x/post", md)

    def test_empty_approval_queue_fallback(self):
        md = render_markdown(_brief(queue=[]))
        self.assertIn("Nothing awaiting approval", md)

    def test_integration_with_assemble(self):
        """Smoke test: assemble_brief → render_markdown end-to-end."""
        outcomes = {
            "seo": AgentOutcome(name="seo", output=type("Fake", (), {"ranked_fixes": [], "meta": {"audit_score": 80}})()),
            "geo": AgentOutcome(name="geo", output=type("Fake", (), {"score": 0.5, "score_delta": None, "fixes": []})()),
        }
        brief = assemble_brief(outcomes, [], [], "2026-W25", "2026-06-25T00:00:00Z")
        md = render_markdown(brief)
        self.assertIn("2026-W25", md)
        self.assertIn("seo", md)
        self.assertIn("geo", md)
