"""Typed contracts for the cms-publish façade (human-gated, irreversible)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .._transport import Transport  # noqa: F401  (re-exported for callers)

__all__ = ["PublishResult", "PublishErrorKind", "PublishErrorSource", "PublishError", "Transport", "SUPPORTED_CMS"]

SUPPORTED_CMS = ("wordpress", "webflow", "framer")


@dataclass(frozen=True)
class PublishResult:
    url: str


PublishErrorKind = Literal[
    "approval_required", "unsupported_cms", "transport", "cms_error", "duplicate_slug"
]


@dataclass(frozen=True)
class PublishErrorSource:
    cms: str
    slug: str


@dataclass(frozen=True)
class PublishError:
    kind: PublishErrorKind
    message: str
    source: PublishErrorSource
