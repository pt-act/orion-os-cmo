"""SEO-audit façade — merge an on-page provider response with Lighthouse data
into one typed AuditReport. Normalization lives here, not in the agent.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from ...common.result import Err, Ok, Result
from .types import (
    AuditError,
    AuditReport,
    ErrorSource,
    Issue,
    SerpEntry,
    Transport,
)

PROVIDER_PATH = "/api/seo/onpage"
LIGHTHOUSE_PATH = "/api/lighthouse/run"

_SEVERITY_WEIGHT = {"critical": 10, "warning": 4, "info": 1}
_VALID_SEVERITY = set(_SEVERITY_WEIGHT)


class SeoAuditAdapter:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def seo_audit(self, url: str) -> Result[AuditReport, AuditError]:
        provider = self._call_provider(url)
        if not provider.ok:
            return provider
        lighthouse = self._run_lighthouse(url)
        if not lighthouse.ok:
            return lighthouse

        report = self._merge(url, provider.value, lighthouse.value)
        violations = validate_report(report)
        if violations:
            return Err(AuditError("schema_invalid", "; ".join(violations),
                                  ErrorSource(_provider_name(provider.value), url)))
        return Ok(report)

    # ── internal calls ─────────────────────────────────────────────────────────

    def _call_provider(self, url: str) -> Result[dict, AuditError]:
        try:
            raw = self._transport.post(PROVIDER_PATH, {"url": url})
        except Exception as exc:
            return Err(AuditError("transport", str(exc), ErrorSource("onpage", url)))
        if not isinstance(raw, dict) or "issues" not in raw:
            return Err(AuditError("invalid_response", "provider response missing issues[]",
                                  ErrorSource("onpage", url)))
        return Ok(raw)

    def _run_lighthouse(self, url: str) -> Result[dict, AuditError]:
        try:
            raw = self._transport.post(LIGHTHOUSE_PATH, {"url": url})
        except Exception as exc:
            return Err(AuditError("lighthouse_failure", str(exc), ErrorSource("lighthouse", url)))
        if not isinstance(raw, dict) or raw.get("error") or "performance_score" not in raw:
            return Err(AuditError("lighthouse_failure", "lighthouse returned no performance_score",
                                  ErrorSource("lighthouse", url)))
        return Ok(raw)

    # ── merge + score ──────────────────────────────────────────────────────────

    def _merge(self, url: str, provider: dict, lighthouse: dict) -> AuditReport:
        issues = [
            Issue(severity=_coerce_severity(i.get("severity")), type=_s(i.get("type")),
                  fix=_s(i.get("fix")), snippet=_s(i.get("snippet")))
            for i in _list(provider.get("issues"))
        ]
        serp = [
            SerpEntry(position=_as_int(e.get("position")), title=_s(e.get("title")), url=_s(e.get("url")))
            for e in _list(provider.get("serp_snapshot"))
        ]
        score = _normalize_score(lighthouse.get("performance_score"), issues)
        meta = {
            "provider": _provider_name(provider),
            "lighthouse_version": _s(lighthouse.get("version")) or "unknown",
            "audited_at": datetime.now(timezone.utc).isoformat(),
        }
        return AuditReport(url=url, score=score, issues=issues, serp_snapshot=serp, meta=meta)


def _normalize_score(perf: Any, issues: list[Issue]) -> int:
    base = int(round(float(perf) * 100)) if isinstance(perf, (int, float)) else 50
    penalty = sum(_SEVERITY_WEIGHT[i.severity] for i in issues)
    return max(0, min(100, base - penalty))


def validate_report(report: AuditReport) -> list[str]:
    v: list[str] = []
    if not (0 <= report.score <= 100):
        v.append("score out of range")
    for i, issue in enumerate(report.issues):
        if issue.severity not in _VALID_SEVERITY:
            v.append(f"issue[{i}].severity invalid")
        for f in ("type", "fix", "snippet"):
            if not getattr(issue, f):
                v.append(f"issue[{i}].{f} empty")
    for k in ("provider", "lighthouse_version", "audited_at"):
        if k not in report.meta:
            v.append(f"_meta.{k} missing")
    return v


def _provider_name(provider: dict) -> str:
    return _s(provider.get("provider")) or "onpage"


def _severity(v: Any) -> str:
    return v if v in _VALID_SEVERITY else "info"


def _coerce_severity(v: Any) -> Literal["critical", "warning", "info"]:
    s = _severity(v)
    if s not in ("critical", "warning", "info"):
        return "info"
    return s  # type: ignore  # narrowed by the guard above


def _list(v: Any) -> list[dict]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""


def _as_int(v: Any) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
