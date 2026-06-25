"""BriefAssembler — merge agent outputs + deltas into one deterministic brief.

Determinism is a hard requirement: given the same outcomes, deltas, and draft
records, ``assemble_brief`` always returns the same brief (no wall-clock, no set
iteration). ``generated_at`` is an input, not read from the clock here.
"""

from __future__ import annotations

import logging
from typing import Any

from .types import (
    AGENT_ORDER,
    AgentOutcome,
    ApprovalQueueItem,
    Delta,
    PrioritizedItem,
    WeeklyBrief,
)

# Which agents produce items that need an explicit publish approval.
_PUBLISHABLE = {"x", "linkedin", "reddit", "writer"}
_log = logging.getLogger(__name__)


def _summarize_seo(output: Any) -> str:
    return f"{len(output.ranked_fixes)} ranked fixes; audit {output.meta.get('audit_score')}"


def _summarize_geo(output: Any) -> str:
    d = "" if output.score_delta is None else f" (Δ{output.score_delta:+})"
    return f"GEO score {output.score}{d}; {len(output.fixes)} fixes"


def _summarize_coding(output: Any) -> str:
    return f"{len(output)} PR(s): " + ", ".join(p.pr_url for p in output)


def _summarize_ugc(output: Any) -> str:
    return f"{len(output.assets)} video asset(s); cap_exceeded={output.cap_exceeded}"


def _summarize_drafts(output: Any) -> str:
    return f"{len(output)} drafts"


_SUMMARIZERS: dict[str, Any] = {
    "seo": _summarize_seo,
    "geo": _summarize_geo,
    "coding": _summarize_coding,
    "ugc": _summarize_ugc,
    "reddit": _summarize_drafts,
    "x": _summarize_drafts,
    "linkedin": _summarize_drafts,
    "writer": _summarize_drafts,
    "influencer": _summarize_drafts,
}

_ACTION = {
    "seo": "review", "geo": "review", "coding": "merge",
    "x": "approve", "linkedin": "approve", "reddit": "approve",
    "writer": "approve", "influencer": "review", "ugc": "review",
}


def assemble_brief(
    outcomes: dict[str, AgentOutcome],
    deltas: list[Delta],
    draft_records: list[ApprovalQueueItem],
    week_key: str,
    generated_at: str,
) -> WeeklyBrief:
    per_agent = {name: (outcomes[name].output if name in outcomes and outcomes[name].ok else None)
                 for name in AGENT_ORDER}

    # First draft item_id per agent, for linking prioritized items.
    first_item: dict[str, str] = {}
    for rec in draft_records:
        first_item.setdefault(rec.agent, rec.item_id)

    prioritized: list[PrioritizedItem] = []
    rank = 1
    for name in AGENT_ORDER:
        outcome = outcomes.get(name)
        if outcome is None or not outcome.ok or outcome.output is None:
            continue
        prioritized.append(PrioritizedItem(
            rank=rank, agent=name, item_id=first_item.get(name, ""),
            summary=summarize(name, outcome.output), action=_ACTION.get(name, "review"),
        ))
        rank += 1

    approval_queue = [r for r in draft_records if r.agent in _PUBLISHABLE]
    return WeeklyBrief(
        week_key=week_key,
        generated_at=generated_at,
        prioritized_items=prioritized,
        per_agent_sections=per_agent,
        week_over_week_deltas=list(deltas),
        approval_queue=approval_queue,
    )


def summarize(name: str, output: Any) -> str:
    """Deterministic one-line summary per agent output (duck-typed, decoupled)."""
    handler = _SUMMARIZERS.get(name)
    if handler is not None:
        try:
            return handler(output)
        except (AttributeError, KeyError, TypeError) as exc:
            _log.warning("brief: unexpected %s output shape: %s", name, exc)
    return f"{name} output ready"


def render_markdown(brief: WeeklyBrief) -> str:
    """Render the brief as readable markdown — the product surface (glass box)."""
    lines = [f"# Weekly Brief — {brief.week_key}", f"_Generated {brief.generated_at}_", ""]
    lines.append("## Prioritized")
    for item in brief.prioritized_items:
        link = f" ({item.item_id})" if item.item_id else ""
        lines.append(f"{item.rank}. **{item.agent}** — {item.summary} → _{item.action}_{link}")
    if not brief.prioritized_items:
        lines.append("_No agent produced output this run._")

    lines += ["", "## Week-over-week"]
    if brief.week_over_week_deltas:
        for d in brief.week_over_week_deltas:
            lines.append(f"- {d.metric}: {d.prior} → {d.current} ({d.delta:+}) · {d.source}")
    else:
        lines.append("_No prior history to compare._")

    lines += ["", "## Approval queue"]
    if brief.approval_queue:
        for q in brief.approval_queue:
            lines.append(f"- `{q.item_id}` [{q.agent}/{q.type}] {q.summary}")
    else:
        lines.append("_Nothing awaiting approval._")
    return "\n".join(lines) + "\n"
