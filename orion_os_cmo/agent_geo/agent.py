"""agent-geo — score AI-answer visibility, draft grounded GEO fixes, track delta.

Every fix is bound to a real ``mentioned: false`` probe gap by the agent itself
(not by the model), so provenance holds by construction. A failed probe degrades
to a partial finding with a note, never an exception. Prior-week score is read
from a versioned snapshot for the week-over-week delta.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from ..adapters.geo_probe.adapter import GeoProbeAdapter
from ..adapters.geo_probe.types import GeoReport, ProbeError
from ..common.result import Err, Ok, Result
from ..llm.principles import compose
from ..llm.types import LLMClient
from ..strategy_store.store import StrategyStore
from .types import GapRef, GeoAgentError, GeoFindings, GeoFix

_DEFAULT_MODELS = ["perplexity", "grok", "claude", "gpt", "gemini"]
_VALID_FIX_TYPE = {"faq", "json_ld", "entity_paragraph"}


class GeoAgent:
    def __init__(
        self,
        strategy_store_path: Path,
        geo_probe_adapter: GeoProbeAdapter,
        llm: LLMClient,
        snapshot_path: Optional[Path] = None,
        models: Optional[list[str]] = None,
    ) -> None:
        self._strategy_path = Path(strategy_store_path)
        self._probe = geo_probe_adapter
        self._llm = llm
        self._snapshot = SnapshotStore(snapshot_path or self._strategy_path / "geo_snapshot.json")
        self._models = models or _DEFAULT_MODELS

    def run(self, brand: str) -> Result[GeoFindings, GeoAgentError]:
        strategy = StrategyStore(self._strategy_path).load()
        if strategy is None:
            return Err(GeoAgentError("strategy_missing", "no strategy_context at path"))
        sections = strategy.get("sections", {})

        questions = build_question_battery(sections)
        competitors = [c.get("name", "") for c in sections.get("competitors", []) if isinstance(c, dict)]

        probe = self._probe.probe(brand, questions, self._models, competitors)
        if not probe.ok:
            return Ok(self._partial(probe.error, len(questions)))

        report: GeoReport = probe.value
        gaps = [(r.model, r.question) for r in report.per_model if not r.mentioned]

        try:
            fixes = self._draft_fixes(strategy, gaps)
        except Exception as exc:
            return Err(GeoAgentError("llm_error", str(exc)))

        prior = self._snapshot.read_score()
        delta = None if prior is None else round(report.score - prior, 6)
        self._snapshot.write(report)

        findings = GeoFindings(
            score=report.score,
            score_delta=delta,
            fixes=fixes,
            competitor_gaps=report.competitor_gaps,
            meta={
                "run_at": datetime.now(timezone.utc).isoformat(),
                "probe_model_count": len(self._models),
                "question_count": len(questions),
            },
        )
        violations = validate_findings(findings, gaps)
        if violations:
            return Err(GeoAgentError("schema_invalid", "; ".join(violations)))
        return Ok(findings)

    def _draft_fixes(self, strategy: dict, gaps: list[tuple[str, str]]) -> list[GeoFix]:
        if not gaps:
            return []
        raw = self._llm.complete_json(system=_SYSTEM, prompt=_build_fix_prompt(strategy, gaps))
        out: list[GeoFix] = []
        for item in (raw.get("fixes") if isinstance(raw, dict) else None) or []:
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if not isinstance(idx, int) or not (0 <= idx < len(gaps)):
                continue  # gap_ref bound by the agent; an invalid index is dropped
            model, question = gaps[idx]
            out.append(GeoFix(
                fix=_s(item.get("fix")),
                snippet=_s(item.get("snippet")),
                fix_type=_coerce_fix_type(item.get("fix_type")),
                gap_ref=GapRef(model=model, question=question),
            ))
        return out

    def _partial(self, error: ProbeError, question_count: int) -> GeoFindings:
        return GeoFindings(
            score=0.0, score_delta=None, fixes=[], competitor_gaps=[],
            meta={"run_at": datetime.now(timezone.utc).isoformat(),
                  "probe_model_count": len(self._models), "question_count": question_count,
                  "note": f"probe failed ({error.kind}): {error.message}"},
        )


# ── SnapshotStore (versioned-file pattern) ───────────────────────────────────

class SnapshotStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def read_score(self) -> Optional[float]:
        if not self.path.exists():
            return None
        try:
            return float(json.loads(self.path.read_text(encoding="utf-8"))["score"])
        except (ValueError, KeyError, json.JSONDecodeError):
            return None

    def write(self, report: GeoReport) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "score": report.score,
            "per_model": [
                {"model": r.model, "question": r.question, "mentioned": r.mentioned}
                for r in report.per_model
            ],
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


# ── pure helpers ─────────────────────────────────────────────────────────────

def build_question_battery(sections: dict) -> list[str]:
    """Buyer-intent questions conditioned on ICP pains + playbook channels (deterministic)."""
    icp = sections.get("icp", {})
    pos = sections.get("positioning", {})
    category = pos.get("category", "this category") or "this category"
    pains = icp.get("pains", []) if isinstance(icp.get("pains"), list) else []
    questions = [
        f"What is the best {category} tool?",
        f"What are the top {category} options?",
    ]
    for pain in pains[:3]:
        questions.append(f"What software helps with {pain}?")
    # Stable de-dup preserving order.
    seen: set[str] = set()
    return [q for q in questions if not (q in seen or seen.add(q))]


def validate_findings(f: GeoFindings, gaps: list[tuple[str, str]]) -> list[str]:
    v: list[str] = []
    if not (0.0 <= f.score <= 1.0):
        v.append("score out of [0,1]")
    gapset = {(m, q) for m, q in gaps}
    for i, fix in enumerate(f.fixes):
        if (fix.gap_ref.model, fix.gap_ref.question) not in gapset:
            v.append(f"fixes[{i}].gap_ref not a real probe gap")
        if fix.fix_type not in _VALID_FIX_TYPE:
            v.append(f"fixes[{i}].fix_type invalid")
    for k in ("run_at", "probe_model_count", "question_count"):
        if k not in f.meta:
            v.append(f"_meta.{k} missing")
    return v


def _coerce_fix_type(v: Any) -> Literal["faq", "json_ld", "entity_paragraph"]:
    return v if v in _VALID_FIX_TYPE else "faq"


def _build_fix_prompt(strategy: dict, gaps: list[tuple[str, str]]) -> str:
    bv = strategy.get("sections", {}).get("brand_voice", {})
    lines = [
        f"Brand voice tone: {bv.get('tone', '')}, register: {bv.get('register', '')}.",
        "Draft one GEO fix per gap below. A gap is an AI-engine question where the brand was NOT mentioned.",
        "",
    ]
    for i, (model, question) in enumerate(gaps):
        lines.append(f"- index {i}: [{model}] {question}")
    lines += [
        "",
        'Return JSON: { "fixes": [{ "index": <gap index>, "fix": <what to add>, '
        '"snippet": <FAQ entry / JSON-LD / entity paragraph>, '
        '"fix_type": "faq"|"json_ld"|"entity_paragraph" }] }.',
    ]
    return "\n".join(lines)


_ROLE = (
    "Your role: generative-engine-optimization strategist. You are given the specific AI-engine "
    "questions where the brand was not mentioned in the answer. For each such gap, draft one "
    "concise, on-voice asset the brand could publish — an FAQ entry, a JSON-LD block, or an "
    "entity paragraph — that would earn the mention honestly, on the merits of real product "
    "facts. Reference each gap only by its provided index; never claim a mention the probe "
    "didn't find. You draft the asset; deciding to publish it, and any code to ship schema, "
    "belong to the operator and agent-coding."
)

_SYSTEM = compose(_ROLE)


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
