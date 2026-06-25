"""agent-influencer — discover, vet, rank, and draft creator outreach.

``fit_score`` is grounded: it is derived from the creator's real ``audience_fit``
signal and is ``None`` whenever that signal is absent — never synthesized. The
originating Creator record is embedded unmodified so the operator can trace every
draft to its discovery source. Sending is always the operator's action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from ..adapters.creator_discovery.adapter import CreatorDiscoveryAdapter
from ..adapters.creator_discovery.types import Creator
from ..common.result import Err, Ok, Result
from ..llm.principles import compose
from ..llm.types import LLMClient
from ..strategy_store.store import StrategyStore


@dataclass(frozen=True)
class CreatorOutreach:
    creator: Creator
    fit_score: Optional[float]
    draft_message: str
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class InfluencerAgentConfig:
    top_n: int = 10
    platform: str = "instagram"
    follower_tier: str = "micro"


@dataclass(frozen=True)
class InfluencerAgentError:
    kind: Literal["strategy_missing", "discovery_failed", "schema_invalid"]
    message: str


class InfluencerAgent:
    def __init__(
        self,
        strategy_store_path: Path,
        discovery_adapter: CreatorDiscoveryAdapter,
        llm: LLMClient,
        config: Optional[InfluencerAgentConfig] = None,
    ) -> None:
        self._strategy_path = Path(strategy_store_path)
        self._discovery = discovery_adapter
        self._llm = llm
        self._config = config or InfluencerAgentConfig()

    def run(self, niche: Optional[str] = None) -> Result[list[CreatorOutreach], InfluencerAgentError]:
        strategy = StrategyStore(self._strategy_path).load()
        if strategy is None:
            return Err(InfluencerAgentError("strategy_missing", "no strategy_context at path"))
        sections = strategy.get("sections", {})
        niche = niche or _derive_niche(sections)

        discovered = self._discovery.discover_creators(
            niche, self._config.platform, self._config.follower_tier)
        if not discovered.ok:
            return Err(InfluencerAgentError("discovery_failed", discovered.error.message))

        ranked = rank(discovered.value, sections.get("icp", {}), self._config.top_n)
        outreach: list[CreatorOutreach] = []
        for creator, fit in ranked:
            message = self._llm.complete(system=_SYSTEM, prompt=_draft_prompt(creator, sections))
            outreach.append(CreatorOutreach(
                creator=creator,                       # unmodified (provenance)
                fit_score=fit,                         # None when audience_fit was None
                draft_message=message.strip(),
                meta={"drafted_at": datetime.now(timezone.utc).isoformat(), "model_hint": "llm"},
            ))
        violations = validate_outreach(outreach)
        if violations:
            return Err(InfluencerAgentError("schema_invalid", "; ".join(violations)))
        return Ok(outreach)


# ── pure helpers ─────────────────────────────────────────────────────────────

def rank(creators: list[Creator], icp: dict, top_n: int) -> list[tuple[Creator, Optional[float]]]:
    """Derive fit_score from audience_fit (grounded), sort desc, cap to top_n."""
    scored = [(c, c.audience_fit if c.audience_fit is not None else None) for c in creators]
    scored.sort(key=lambda cf: (cf[1] is not None, cf[1] or 0.0), reverse=True)
    return scored[:max(0, top_n)]


def validate_outreach(items: list[CreatorOutreach]) -> list[str]:
    v: list[str] = []
    for i, it in enumerate(items):
        if it.fit_score is not None and it.creator.audience_fit is None:
            v.append(f"outreach[{i}].fit_score set without audience_fit")
        if not it.draft_message:
            v.append(f"outreach[{i}].draft_message empty")
    return v


def _derive_niche(sections: dict) -> str:
    pos = sections.get("positioning", {})
    if isinstance(pos.get("category"), str) and pos["category"]:
        return pos["category"]
    icp = sections.get("icp", {})
    segs = icp.get("segments") if isinstance(icp.get("segments"), list) else []
    return segs[0] if segs else "general"


def _draft_prompt(creator: Creator, sections: dict) -> str:
    bv = sections.get("brand_voice", {})
    pos = sections.get("positioning", {})
    return "\n".join([
        f"Brand voice — tone: {bv.get('tone', '')}, register: {bv.get('register', '')}.",
        f"Positioning: {pos.get('one_liner', '')}",
        f"Creator handle: {creator.handle} ({creator.followers} followers, {creator.url})",
        f"Write a short, personalized outreach DM that addresses {creator.handle} by handle.",
    ])


_ROLE = (
    "Your role: a partnerships writer drafting a short, personal outreach DM to one creator, "
    "for the operator to review and send. You're given the creator's real handle and audience "
    "data. Personalize honestly to that specific creator; invent no metrics about them or the "
    "brand. Aim for a message a real person would welcome — specific, brief, no mail-merge "
    "feel. The operator decides whether to send."
)

_SYSTEM = compose(_ROLE, voice=True)
