"""Typed contracts for the video-gen façade (metered, cost-capped)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .._transport import Transport  # noqa: F401  (re-exported for callers)

__all__ = [
    "VideoAsset", "VideoGenErrorKind", "VideoErrorSource", "VideoGenError",
    "Transport", "SUPPORTED_ASPECTS",
]

SUPPORTED_ASPECTS = ("9:16", "16:9", "1:1")


@dataclass(frozen=True)
class VideoAsset:
    mp4_url: str
    duration_s: float
    est_cost: float                     # provider-quoted USD; never synthesized
    meta: dict = field(default_factory=dict)  # provider, aspect, resolution, audio


VideoGenErrorKind = Literal[
    "cap_exceeded", "transport", "invalid_response", "render_failure", "invalid_input"
]


@dataclass(frozen=True)
class VideoErrorSource:
    provider: str
    prompt_hash: str


@dataclass(frozen=True)
class VideoGenError:
    kind: VideoGenErrorKind
    message: str
    source: VideoErrorSource
