"""strategy-store Group 2 — synthesize the strategy_context from evidence.

The model proposes the five sections; this module enforces the contract:
- Provenance (task 2.4): every competitor and differentiator must cite a `source`
  URL that exists in the evidence set. Ungrounded claims are dropped, not shipped.
- Schema (task 2.5): the result must validate against the strategy_context shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from ..common.result import Err, Ok, Result
from ..llm.types import LLMClient
from .context import (
    BrandVoice,
    Competitor,
    Differentiator,
    GrowthPlaybook,
    Icp,
    Positioning,
    StrategyContext,
    StrategyMeta,
    validate_strategy_context,
)
from .evidence import EvidenceSet


@dataclass(frozen=True)
class StrategyError:
    kind: Literal["llm_error", "invalid_output", "schema_invalid"]
    message: str


SynthResult = Result[StrategyContext, StrategyError]


def synthesize_strategy(
    evidence: EvidenceSet,
    llm: LLMClient,
    *,
    version: int = 1,
    source_run: str = "",
) -> SynthResult:
    if not evidence.items:
        return Err(StrategyError("invalid_output", "no evidence to synthesize from"))

    evidence_urls = {item.source.url for item in evidence.items}

    try:
        raw = llm.complete_json(system=_SYSTEM, prompt=_build_prompt(evidence))
    except Exception as exc:  # any concrete-client failure → structured error
        return Err(StrategyError("llm_error", str(exc)))

    if not isinstance(raw, dict):
        return Err(StrategyError("invalid_output", "model did not return a JSON object"))

    try:
        ctx = _parse(raw, evidence_urls, version=version, source_run=source_run)
    except _ParseError as exc:
        return Err(StrategyError("invalid_output", str(exc)))

    violations = validate_strategy_context(ctx)
    if violations:
        return Err(StrategyError("schema_invalid", "; ".join(violations)))

    return Ok(ctx)


# ── parsing & grounding ──────────────────────────────────────────────────────

class _ParseError(Exception):
    pass


def _parse(
    raw: dict[str, Any],
    evidence_urls: set[str],
    *,
    version: int,
    source_run: str,
) -> StrategyContext:
    bv = _req(raw, "brand_voice")
    icp = _req(raw, "icp")
    pos = _req(raw, "positioning")
    gp = _req(raw, "growth_playbook")

    brand_voice = BrandVoice(
        tone=_s(bv.get("tone")),
        register=_s(bv.get("register")),
        do=_ls(bv.get("do")),
        dont=_ls(bv.get("dont")),
        sample_phrases=_ls(bv.get("sample_phrases")),
    )
    icp_obj = Icp(
        segments=_ls(icp.get("segments")),
        pains=_ls(icp.get("pains")),
        triggers=_ls(icp.get("triggers")),
    )

    # Provenance: keep only claims grounded in a real evidence URL. Q-9: ungrounded
    # claims are dropped silently — spec-compliant (the gate's job is to never ship an
    # unsourced claim, and a strict StrategyContext has no warnings channel). The
    # operator-visible surface for drops is BRAND_SAFETY_LOG.md when this runs through
    # the workspace, not the context object itself.
    competitors: list[Competitor] = []
    for c in _as_list(raw.get("competitors")):
        src = _s(c.get("source"))
        if src not in evidence_urls:
            continue
        competitors.append(Competitor(
            name=_s(c.get("name")), url=_s(c.get("url")),
            positioning=_s(c.get("positioning")), source=src,
        ))

    differentiators: list[Differentiator] = []
    for d in _as_list(pos.get("differentiators")):
        src = _s(d.get("source"))
        if src not in evidence_urls:
            continue
        differentiators.append(Differentiator(claim=_s(d.get("claim")), source=src))

    positioning = Positioning(
        one_liner=_s(pos.get("one_liner")),
        category=_s(pos.get("category")),
        differentiators=differentiators,
    )
    growth = GrowthPlaybook(
        channels=_ls(gp.get("channels")),
        priorities=_ls(gp.get("priorities")),
        notes=_s(gp.get("notes")),
    )
    meta = StrategyMeta(
        version=version,
        built_at=datetime.now(timezone.utc).isoformat(),
        source_run=source_run,
    )
    return StrategyContext(brand_voice, icp_obj, competitors, positioning, growth, meta)


def _req(d: dict[str, Any], key: str) -> dict[str, Any]:
    value = d.get(key)
    if not isinstance(value, dict):
        raise _ParseError(f"missing or invalid section '{key}'")
    return value


def _as_list(v: Any) -> list[dict[str, Any]]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""


def _ls(v: Any) -> list[str]:
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


_SYSTEM = (
    "You are a marketing strategist. From the supplied evidence, produce a strategy "
    "context as a single JSON object. Use ONLY the evidence provided. For every "
    "competitor and every positioning differentiator, set `source` to the exact URL "
    "of the evidence item it came from. Never invent a source."
)


def _build_prompt(evidence: EvidenceSet) -> str:
    lines = ["Evidence items (use the url as `source` when citing):"]
    for item in evidence.items:
        snippet = " ".join(item.text.split())
        if len(snippet) > 500:
            snippet = snippet[:500] + "…"
        lines.append(f"- [{item.id}] source={item.source.url} :: {snippet}")
    lines.append("")
    lines.append(
        "Return JSON with keys: brand_voice{tone,register,do[],dont[],sample_phrases[]}, "
        "icp{segments[],pains[],triggers[]}, competitors[]{name,url,positioning,source}, "
        "positioning{one_liner,category,differentiators[]{claim,source}}, "
        "growth_playbook{channels[],priorities[],notes}."
    )
    return "\n".join(lines)
