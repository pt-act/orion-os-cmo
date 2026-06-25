"""Typed contracts for agent-writer's article batch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..agent_geo.types import GapRef

__all__ = ["ArticleMeta", "Article", "WriterAgentConfig", "WriterAgentError"]


@dataclass(frozen=True)
class ArticleMeta:
    title_tag: str       # ≤60 chars
    meta_description: str  # ≤160 chars
    slug: str


@dataclass(frozen=True)
class Article:
    title: str
    body: str
    target_keyword: str
    geo_fix_refs: list[GapRef]
    meta: ArticleMeta

    def to_payload(self) -> dict:
        """Flatten to the dict shape the CMS adapter consumes (decoupling boundary)."""
        return {
            "title": self.title,
            "body": self.body,
            "slug": self.meta.slug,
            "meta": {"title_tag": self.meta.title_tag, "meta_description": self.meta.meta_description},
        }


@dataclass(frozen=True)
class WriterAgentConfig:
    max_articles: int = 3


WriterAgentErrorKind = Literal["strategy_missing", "llm_error", "schema_invalid"]


@dataclass(frozen=True)
class WriterAgentError:
    kind: WriterAgentErrorKind
    message: str
