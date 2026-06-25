"""agent-seo — a thin, strategy-conditioned worker.

Pulls grounded audit + analytics through the two SEO adapters, asks the LLM to
*rank* (not to invent facts), and ships ``seo_findings``. The provenance gate is
the spine: every shipped fix must reference a real audit issue, and the issue's
snippet/severity are taken from the audit — never from the model. The model
contributes prioritization and fix phrasing only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..adapters.analytics_ingest.adapter import AnalyticsAdapter
from ..adapters.analytics_ingest.types import AnalyticsSnapshot
from ..adapters.seo_audit.adapter import SeoAuditAdapter
from ..adapters.seo_audit.types import AuditReport, Issue
from ..common.result import Err, Ok, Result
from ..llm.principles import compose
from ..llm.types import LLMClient
from ..strategy_store.store import StrategyStore
from .types import KeywordGap, RankedFix, SeoAgentError, SeoFindings

_VALID_SEVERITY = {"critical", "warning", "info"}


class SeoAgent:
    def __init__(
        self,
        strategy_store_path: Path,
        seo_audit_adapter: SeoAuditAdapter,
        analytics_adapter: AnalyticsAdapter,
        llm: LLMClient,
    ) -> None:
        self._strategy_path = Path(strategy_store_path)
        self._audit = seo_audit_adapter
        self._analytics = analytics_adapter
        self._llm = llm

    def run(self, url: str, run_at: Optional[str] = None) -> Result[SeoFindings, SeoAgentError]:
        strategy = StrategyStore(self._strategy_path).load()
        if strategy is None:
            return Err(SeoAgentError("strategy_missing", "no strategy_context at path"))

        audit = self._audit.seo_audit(url)
        if not audit.ok:
            return Err(SeoAgentError("audit_failed", audit.error.message))
        analytics = self._analytics.fetch_analytics()
        if not analytics.ok:
            return Err(SeoAgentError("analytics_failed", analytics.error.message))

        report: AuditReport = audit.value
        snapshot: AnalyticsSnapshot = analytics.value
        # Stable index-based id for each audit issue — the provenance keyset.
        issues_by_id = {f"issue-{i}": issue for i, issue in enumerate(report.issues)}

        try:
            raw = self._llm.complete_json(
                system=_SYSTEM,
                prompt=_build_ranking_prompt(strategy, report, snapshot, issues_by_id),
            )
        except Exception as exc:
            return Err(SeoAgentError("llm_error", str(exc)))
        if not isinstance(raw, dict):
            return Err(SeoAgentError("schema_invalid", "model did not return a JSON object"))

        ranked = _filter_ranked_fixes(raw.get("ranked_fixes"), issues_by_id)
        gaps = _parse_keyword_gaps(raw.get("keyword_gaps"))
        findings = SeoFindings(
            ranked_fixes=ranked,
            keyword_gaps=gaps,
            meta={
                "url": url,
                "audit_score": report.score,
                "analytics_period": snapshot.meta.get("date_range", {}),
                # Injectable so the output is structurally deterministic given identical
                # inputs (Q-6 / spec PBT #2: "no time-dependent variation"). The clock is
                # an input, not a hidden source of variation.
                "run_at": run_at or datetime.now(timezone.utc).isoformat(),
            },
        )
        violations = validate_findings(findings)
        if violations:
            return Err(SeoAgentError("schema_invalid", "; ".join(violations)))
        return Ok(findings)


# ── pure helpers ─────────────────────────────────────────────────────────────

def _filter_ranked_fixes(raw: Any, issues_by_id: dict[str, Issue]) -> list[RankedFix]:
    """Keep only fixes that reference a real audit issue; ground facts from the audit."""
    out: list[RankedFix] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        issue_id = item.get("issue_id")
        if not isinstance(issue_id, str):
            continue  # fabricated issue_id — dropped, never shipped
        issue = issues_by_id.get(issue_id)
        if issue is None:
            continue  # fabricated issue_id — dropped, never shipped
        out.append(RankedFix(
            issue_id=issue_id,
            issue=issue.type,                         # grounded
            fix=_s(item.get("fix")) or issue.fix,     # model ranking/phrasing, audit fallback
            snippet=issue.snippet,                    # grounded — never model-supplied
            severity=issue.severity,                  # grounded
            rationale=_s(item.get("rationale")),      # model's ranking explanation (glass-box)
        ))
    return out


def _parse_keyword_gaps(raw: Any) -> list[KeywordGap]:
    out: list[KeywordGap] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        query = _s(item.get("query"))
        if not query:
            continue
        out.append(KeywordGap(query=query, impressions=_as_int(item.get("impressions")), source="gsc"))
    return out


def validate_findings(f: SeoFindings) -> list[str]:
    v: list[str] = []
    for i, fix in enumerate(f.ranked_fixes):
        if not fix.issue_id:
            v.append(f"ranked_fixes[{i}].issue_id empty")
        if fix.severity not in _VALID_SEVERITY:
            v.append(f"ranked_fixes[{i}].severity invalid")
    for k in ("url", "audit_score"):
        if k not in f.meta:
            v.append(f"_meta.{k} missing")
    return v


def _build_ranking_prompt(
    strategy: dict, report: AuditReport, snapshot: AnalyticsSnapshot, issues_by_id: dict[str, Issue]
) -> str:
    pos = strategy.get("sections", {}).get("positioning", {})
    icp = strategy.get("sections", {}).get("icp", {})
    lines = [
        "Strategy positioning (one_liner): " + str(pos.get("one_liner", "")),
        "ICP segments: " + ", ".join(icp.get("segments", []) if isinstance(icp.get("segments"), list) else []),
        f"Audit score: {report.score}. Sessions: {snapshot.sessions}, impressions: {snapshot.impressions}.",
        "",
        "Audit issues (reference these exact issue_id values, never invent one):",
    ]
    for issue_id, issue in issues_by_id.items():
        lines.append(f"- {issue_id} [{issue.severity}] {issue.type}: {issue.snippet[:160]}")
    lines += [
        "",
        "Return JSON: { ranked_fixes: [{ issue_id, fix, rationale }] ordered by impact (highest first), "
        "keyword_gaps: [{ query, impressions }] } — use only issue_id values listed above.",
    ]
    return "\n".join(lines)


_ROLE = (
    "Your role: SEO analyst. You are given a grounded audit (issues, each with an exact id, "
    "severity, and snippet) and analytics. Rank the existing issues by business impact for "
    "this product's positioning and ICP, and surface the keyword gaps the analytics reveal. "
    "You may sharpen a fix's wording, but you may not create issues, change a severity, or "
    "cite a metric that isn't in the audit — reference issues only by the exact ids provided. "
    "Make the prioritization legible: briefly say why the top items rank where they do, so the "
    "operator can audit the call. You rank and explain; writing the copy is agent-writer's job "
    "and the code is agent-coding's."
)

_SYSTEM = compose(_ROLE)


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""


def _as_int(v: Any) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
