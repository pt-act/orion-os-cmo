"""The strategy_context produced by strategy-store — the five sections every
agent conditions on. Competitors and positioning differentiators carry a
`source`; brand voice, ICP, and playbook are synthesized, not sourced claims.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrandVoice:
    tone: str
    register: str
    do: list[str]
    dont: list[str]
    sample_phrases: list[str]


@dataclass(frozen=True)
class Icp:
    segments: list[str]
    pains: list[str]
    triggers: list[str]


@dataclass(frozen=True)
class Competitor:
    name: str
    url: str
    positioning: str
    source: str  # evidence URL this entry was grounded in


@dataclass(frozen=True)
class Differentiator:
    claim: str
    source: str  # evidence URL this claim was grounded in


@dataclass(frozen=True)
class Positioning:
    one_liner: str
    category: str
    differentiators: list[Differentiator]


@dataclass(frozen=True)
class GrowthPlaybook:
    channels: list[str]
    priorities: list[str]
    notes: str


@dataclass(frozen=True)
class StrategyMeta:
    version: int
    built_at: str
    source_run: str


@dataclass(frozen=True)
class StrategyContext:
    brand_voice: BrandVoice
    icp: Icp
    competitors: list[Competitor]
    positioning: Positioning
    growth_playbook: GrowthPlaybook
    meta: StrategyMeta


def validate_strategy_context(ctx: StrategyContext) -> list[str]:
    """Return a list of schema/provenance violations (empty == valid)."""
    violations: list[str] = []
    if not ctx.brand_voice.tone:
        violations.append("brand_voice.tone is empty")
    if not ctx.positioning.one_liner:
        violations.append("positioning.one_liner is empty")
    for c in ctx.competitors:
        if not c.source:
            violations.append(f"competitor '{c.name}' has no source")
    for d in ctx.positioning.differentiators:
        if not d.source:
            violations.append(f"differentiator '{d.claim}' has no source")
    return violations
