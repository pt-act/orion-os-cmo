"""Video-gen façade — quote first, render only within the per-run cost cap.

The cost-metering gate is the highest-priority invariant: the provider's own
``est_cost`` is fetched before any render, and if it exceeds the cap the render
never fires (exactly one transport call — the quote). ``est_cost`` on a returned
asset is always the provider quote, never a synthesized number.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ...common.result import Err, Ok, Result
from .types import (
    SUPPORTED_ASPECTS,
    Transport,
    VideoAsset,
    VideoErrorSource,
    VideoGenError,
)

QUOTE_PATH = "/api/video/quote"
RENDER_PATH = "/api/video/render"
_PROVIDER = "video-gen"


def check_cap(est_cost: float, per_run_cap: float) -> bool:
    """True iff a render at this quote is within budget. Isolated for PBT."""
    return est_cost <= per_run_cap


class VideoGenAdapter:
    def __init__(self, transport: Transport, per_run_cap: float) -> None:
        self._transport = transport
        self._cap = per_run_cap

    def generate_video(
        self, prompt: str, aspect: str, resolution: str, audio: bool
    ) -> Result[VideoAsset, VideoGenError]:
        src = VideoErrorSource(provider=_PROVIDER, prompt_hash=_hash(prompt))
        if aspect not in SUPPORTED_ASPECTS:
            return Err(VideoGenError("invalid_input", f"unsupported aspect '{aspect}'", src))

        body = {"prompt": prompt, "aspect": aspect, "resolution": resolution, "audio": audio}

        # 1) Quote — provider-supplied cost, before any render.
        try:
            quote = self._transport.post(QUOTE_PATH, body)
        except Exception as exc:
            return Err(VideoGenError("transport", str(exc), src))
        if not isinstance(quote, dict) or not isinstance(quote.get("est_cost"), (int, float)) \
                or isinstance(quote.get("est_cost"), bool):
            return Err(VideoGenError("invalid_response", "quote missing est_cost", src))
        est_cost = float(quote["est_cost"])
        if est_cost <= 0:
            return Err(VideoGenError("invalid_response", "quote est_cost not positive", src))

        # 2) Cap gate — render only if within budget.
        if not check_cap(est_cost, self._cap):
            return Err(VideoGenError("cap_exceeded",
                                     f"est_cost {est_cost} exceeds cap {self._cap}", src))

        # 3) Render.
        try:
            rendered = self._transport.post(RENDER_PATH, body)
        except Exception as exc:
            return Err(VideoGenError("render_failure", str(exc), src))
        if not isinstance(rendered, dict) or rendered.get("error") is not None:
            return Err(VideoGenError("render_failure", "render returned an error", src))
        mp4 = _s(rendered.get("mp4_url"))
        duration = rendered.get("duration_s")
        if not mp4 or not isinstance(duration, (int, float)) or isinstance(duration, bool):
            return Err(VideoGenError("invalid_response", "render missing mp4_url/duration", src))

        return Ok(VideoAsset(
            mp4_url=mp4, duration_s=float(duration), est_cost=est_cost,  # provenance: provider quote
            meta={"provider": _s(rendered.get("provider")) or _PROVIDER,
                  "aspect": aspect, "resolution": resolution, "audio": audio},
        ))


def _hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
