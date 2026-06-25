"""agent-ugc — turn operator briefs into rendered video assets, under the cap.

Two guarantees: the originating ``brief`` rides along with each asset unmodified
(provenance), and a ``cap_exceeded`` signal from the adapter stops the brief loop
immediately — no further renders fire. The cap gate itself lives in the adapter;
the agent honors its signal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from ..adapters.video_gen.adapter import VideoGenAdapter
from ..adapters.video_gen.types import SUPPORTED_ASPECTS
from ..llm.principles import compose
from ..llm.types import LLMClient
from ..strategy_store.store import StrategyStore


@dataclass(frozen=True)
class VideoAssetOut:
    mp4_url: str
    brief: str                 # operator-supplied brief, unmodified
    aspect: str
    duration_s: float
    est_cost: float
    meta: dict = field(default_factory=dict)  # rendered_at, render_prompt, model_hint


@dataclass(frozen=True)
class UGCError:
    kind: Literal["missing_context", "cap_exceeded", "render_failure", "expander_error"]
    message: str


@dataclass(frozen=True)
class UGCResult:
    assets: list[VideoAssetOut]
    cap_exceeded: bool
    error: Optional[UGCError]


class UGCAgent:
    def __init__(
        self,
        strategy_store_path: Path,
        video_adapter: VideoGenAdapter,
        llm: LLMClient,
        audio: bool = True,
    ) -> None:
        self._strategy_path = Path(strategy_store_path)
        self._video = video_adapter
        self._llm = llm
        self._audio = audio

    def run(self, briefs: list[str]) -> UGCResult:
        strategy = StrategyStore(self._strategy_path).load()
        if strategy is None:
            return UGCResult([], False, UGCError("missing_context", "no strategy_context at path"))
        sections = strategy.get("sections", {})

        assets: list[VideoAssetOut] = []
        for brief in briefs:
            spec = self._expand(brief, sections)
            if spec is None:
                return UGCResult(assets, False, UGCError("expander_error", "unsupported aspect from expander"))

            result = self._video.generate_video(spec["prompt"], spec["aspect"], spec["resolution"], self._audio)
            if not result.ok:
                if result.error.kind == "cap_exceeded":
                    return UGCResult(assets, True, UGCError("cap_exceeded", result.error.message))
                return UGCResult(assets, False, UGCError("render_failure", result.error.message))

            va = result.value
            assets.append(VideoAssetOut(
                mp4_url=va.mp4_url, brief=brief, aspect=spec["aspect"],
                duration_s=va.duration_s, est_cost=va.est_cost,
                meta={"rendered_at": datetime.now(timezone.utc).isoformat(),
                      "render_prompt": spec["prompt"], "model_hint": "llm"},
            ))
        return UGCResult(assets, False, None)

    def _expand(self, brief: str, sections: dict) -> Optional[dict[str, Any]]:
        """Brief + strategy → RenderSpec; returns None if aspect is unsupported."""
        try:
            raw = self._llm.complete_json(system=_SYSTEM, prompt=_expand_prompt(brief, sections))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        aspect = raw.get("aspect")
        if aspect not in SUPPORTED_ASPECTS:
            return None
        return {
            "prompt": _s(raw.get("prompt")) or brief,
            "aspect": aspect,
            "resolution": _s(raw.get("resolution")) or "1080p",
        }


def validate_assets(assets: list[VideoAssetOut]) -> list[str]:
    v: list[str] = []
    for i, a in enumerate(assets):
        if a.est_cost <= 0:
            v.append(f"assets[{i}].est_cost not positive")
        if a.aspect not in SUPPORTED_ASPECTS:
            v.append(f"assets[{i}].aspect invalid")
        if not a.mp4_url or not a.brief:
            v.append(f"assets[{i}] missing required field")
    return v


def _expand_prompt(brief: str, sections: dict) -> str:
    bv = sections.get("brand_voice", {})
    icp = sections.get("icp", {})
    return "\n".join([
        f"Brand voice — tone: {bv.get('tone', '')}. ICP segments: "
        f"{', '.join(icp.get('segments', []) if isinstance(icp.get('segments'), list) else [])}.",
        f"Brief: {brief}",
        'Return JSON: { "prompt" (shot/script), "aspect": "9:16"|"16:9"|"1:1", "resolution" }.',
    ])


_ROLE = (
    "Your role: a short-form video director expanding one operator brief into a single render "
    "prompt, conditioned on the brand voice and ICP. Choose an aspect ratio from 9:16, 16:9, or "
    "1:1. Keep the concept on-brand and honest — put no claim, statistic, or superlative on "
    "screen or in the script that the strategy doesn't substantiate. The operator's brief is the "
    "source of truth; rendering is metered and capped upstream, so keep the concept tight."
)

_SYSTEM = compose(_ROLE, voice=True)


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
