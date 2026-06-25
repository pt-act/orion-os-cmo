"""agent-writer — draft a weekly batch of on-brand, SEO-targeted articles.

Topics are real keyword gaps from ``seo_findings`` (never invented); matching GEO
fixes are overlaid into a FAQ section. The agent binds ``target_keyword`` and
``geo_fix_refs`` from the data it selected — the model writes the prose, not the
provenance. Terminal output: ``articles[]`` for human review. It never publishes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..agent_geo.types import GeoFindings, GeoFix
from ..agent_seo.types import KeywordGap, SeoFindings
from ..common.result import Err, Ok, Result
from ..llm.principles import compose
from ..llm.types import LLMClient
from ..strategy_store.store import StrategyStore
from .types import Article, ArticleMeta, WriterAgentConfig, WriterAgentError

_TITLE_MAX = 60
_META_MAX = 160


class WriterAgent:
    def __init__(
        self,
        strategy_store_path: Path,
        seo_agent_output: Optional[SeoFindings],
        geo_agent_output: Optional[GeoFindings],
        llm: LLMClient,
        config: Optional[WriterAgentConfig] = None,
    ) -> None:
        self._strategy_path = Path(strategy_store_path)
        self._seo = seo_agent_output
        self._geo = geo_agent_output
        self._llm = llm
        self._config = config or WriterAgentConfig()

    def run(self) -> Result[list[Article], WriterAgentError]:
        strategy = StrategyStore(self._strategy_path).load()
        if strategy is None:
            return Err(WriterAgentError("strategy_missing", "no strategy_context at path"))

        gaps = select_topics(self._seo, self._config.max_articles)
        geo_fixes = self._geo.fixes if self._geo else []

        articles: list[Article] = []
        for gap in gaps:
            overlay = geo_overlay(gap.query, geo_fixes)
            try:
                raw = self._llm.complete_json(
                    system=_system(strategy),
                    prompt=_build_article_prompt(gap.query, overlay),
                )
            except Exception as exc:
                return Err(WriterAgentError("llm_error", str(exc)))
            if not isinstance(raw, dict):
                return Err(WriterAgentError("schema_invalid", "model did not return a JSON object"))
            articles.append(_assemble(gap, overlay, raw))

        violations = validate_articles(articles, self._seo)
        if violations:
            return Err(WriterAgentError("schema_invalid", "; ".join(violations)))
        return Ok(articles)


# ── pure helpers ─────────────────────────────────────────────────────────────

def select_topics(seo: Optional[SeoFindings], max_articles: int) -> list[KeywordGap]:
    """Top keyword gaps by opportunity (impressions desc, stable on ties)."""
    gaps = list(seo.keyword_gaps) if seo else []
    ranked = sorted(enumerate(gaps), key=lambda iv: (-iv[1].impressions, iv[0]))
    return [g for _, g in ranked[:max(0, max_articles)]]


def geo_overlay(keyword: str, geo_fixes: list[GeoFix]) -> list[GeoFix]:
    """GEO fixes whose gap question shares a token with the keyword (no fuzzy inference)."""
    kw_tokens = _tokens(keyword)
    out: list[GeoFix] = []
    for fix in geo_fixes:
        if kw_tokens & _tokens(fix.gap_ref.question):
            out.append(fix)
    return out


def _assemble(gap: KeywordGap, overlay: list[GeoFix], raw: dict[str, Any]) -> Article:
    title = _s(raw.get("title")) or gap.query.title()
    body = _s(raw.get("body"))
    if overlay:
        faq = "\n\n## FAQ\n" + "\n\n".join(f"{f.snippet}" for f in overlay)
        body = body + faq
    slug = _s(raw.get("slug")) or _slugify(gap.query)
    return Article(
        title=title[:_TITLE_MAX],
        body=body,
        target_keyword=gap.query,                       # bound from selected gap (provenance)
        geo_fix_refs=[f.gap_ref for f in overlay],
        meta=ArticleMeta(
            title_tag=(_s(raw.get("title_tag")) or title)[:_TITLE_MAX],
            meta_description=(_s(raw.get("meta_description")) or "")[:_META_MAX],
            slug=slug,
        ),
    )


def validate_articles(articles: list[Article], seo: Optional[SeoFindings]) -> list[str]:
    v: list[str] = []
    valid_keywords = {g.query for g in (seo.keyword_gaps if seo else [])}
    for i, a in enumerate(articles):
        if a.target_keyword not in valid_keywords:
            v.append(f"articles[{i}].target_keyword not a real gap")
        if not a.title or not a.body or not a.meta.slug:
            v.append(f"articles[{i}] missing required field")
        if len(a.meta.title_tag) > _TITLE_MAX:
            v.append(f"articles[{i}].meta.title_tag too long")
        if len(a.meta.meta_description) > _META_MAX:
            v.append(f"articles[{i}].meta.meta_description too long")
    return v


def _system(strategy: dict) -> str:
    bv = strategy.get("sections", {}).get("brand_voice", {})
    do = ", ".join(bv.get("do", []) if isinstance(bv.get("do"), list) else [])
    dont = ", ".join(bv.get("dont", []) if isinstance(bv.get("dont"), list) else [])
    role = (
        "Your role: a content writer drafting one complete, original article per assigned "
        f"keyword gap, for operator review, in this brand voice — tone: {bv.get('tone','')}, "
        f"register: {bv.get('register','')}; do: {do}; don't: {dont}. The target keyword is a "
        "real gap surfaced by the SEO pass — write to genuinely serve a reader searching it, "
        "not to stuff the term. Where GEO/FAQ points are provided, weave them in naturally. "
        "If you'd reach for a statistic or study you don't have, make the point qualitatively "
        "instead. You write the draft; publishing is the operator's decision through the "
        "approval-gated CMS path — never imply it's already live."
    )
    return compose(role, voice=True)


def _build_article_prompt(keyword: str, overlay: list[GeoFix]) -> str:
    lines = [f"Target keyword: {keyword}", "Write an SEO article targeting this keyword."]
    if overlay:
        lines.append("Incorporate these GEO/FAQ points where natural:")
        for f in overlay:
            lines.append(f"- {f.snippet}")
    lines.append(
        'Return JSON: { "title", "body" (markdown), "title_tag" (<=60 chars), '
        '"meta_description" (<=160 chars), "slug" }.'
    )
    return "\n".join(lines)


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(t) > 2}


def _slugify(text: str) -> str:
    return "-".join("".join(c.lower() if c.isalnum() else " " for c in text).split())[:80]


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
