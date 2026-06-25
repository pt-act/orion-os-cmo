"""Analytics-ingest façade — one typed AnalyticsSnapshot from GA4 + GSC + CWV.

Each upstream call goes through the injected transport; the adapter only sees
structured response dicts (H-3 atomic/idempotent, H-2 structured output). It never
zero-fills a gap: a disconnected or malformed upstream becomes an ``Err``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from ...common.result import Err, Ok, Result
from .types import (
    AnalyticsError,
    AnalyticsSnapshot,
    CoreWebVitals,
    ErrorSource,
    PageStat,
    Transport,
)

GA4_PATH = "/api/ga4/runReport"
GSC_PATH = "/api/gsc/searchAnalytics"
CWV_PATH = "/api/crux/query"

_DEFAULT_RANGE = {"start": "28daysAgo", "end": "yesterday"}


class AnalyticsAdapter:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def fetch_analytics(
        self, date_range: Optional[dict[str, str]] = None
    ) -> Result[AnalyticsSnapshot, AnalyticsError]:
        rng = date_range or dict(_DEFAULT_RANGE)

        ga4 = self._call(GA4_PATH, {"date_range": rng}, "ga4")
        if not ga4.ok:
            return ga4
        gsc = self._call(GSC_PATH, {"date_range": rng}, "gsc")
        if not gsc.ok:
            return gsc
        cwv = self._call(CWV_PATH, {"date_range": rng}, "crux")
        if not cwv.ok:
            return cwv

        try:
            snap = _merge(ga4.value, gsc.value, cwv.value, rng)
        except _Bad as exc:
            return Err(AnalyticsError("invalid_response", str(exc), ErrorSource(exc.api)))

        violations = validate_snapshot(snap)
        if violations:
            return Err(AnalyticsError("invalid_response", "; ".join(violations), ErrorSource("merge")))
        return Ok(snap)

    def _call(self, path: str, body: dict[str, Any], api: str) -> Result[dict, AnalyticsError]:
        try:
            raw = self._transport.post(path, body)
        except Exception as exc:
            return Err(AnalyticsError("transport", str(exc), ErrorSource(api)))
        if not isinstance(raw, dict):
            return Err(AnalyticsError("invalid_response", f"{api} response not an object", ErrorSource(api)))
        err = _classify(raw, api)
        if err is not None:
            return Err(err)
        return Ok(raw)


# ── helpers ──────────────────────────────────────────────────────────────────

class _Bad(Exception):
    def __init__(self, api: str, msg: str) -> None:
        super().__init__(msg)
        self.api = api


def _classify(raw: dict[str, Any], api: str) -> Optional[AnalyticsError]:
    """Map an upstream error envelope to a structured AnalyticsError."""
    err = raw.get("error")
    if err is None:
        return None
    code = err.get("code") if isinstance(err, dict) else None
    status = err.get("status") if isinstance(err, dict) else None
    prop = raw.get("property_id")
    if code in (401, 403) and status == "auth":
        return AnalyticsError("auth_failure", "invalid or expired token", ErrorSource(api, prop))
    if code == 403 or status in ("not_connected", "PERMISSION_DENIED"):
        return AnalyticsError("not_connected", "property not connected/verified", ErrorSource(api, prop))
    if code == 401:
        return AnalyticsError("auth_failure", "invalid or expired token", ErrorSource(api, prop))
    return AnalyticsError("invalid_response", str(err), ErrorSource(api, prop))


def _merge(ga4: dict, gsc: dict, cwv: dict, rng: dict) -> AnalyticsSnapshot:
    sessions = _int(ga4, "sessions", "ga4")
    clicks = _int(gsc, "clicks", "gsc")
    impressions = _int(gsc, "impressions", "gsc")

    ga4_pages = {_str(r.get("url")): r for r in _rows(ga4) }
    gsc_pages = {_str(r.get("url")): r for r in _rows(gsc) }
    urls = list(ga4_pages) + [u for u in gsc_pages if u not in ga4_pages]
    top_pages = [
        PageStat(
            url=u,
            sessions=_as_int(ga4_pages.get(u, {}).get("sessions")),
            clicks=_as_int(gsc_pages.get(u, {}).get("clicks")),
            impressions=_as_int(gsc_pages.get(u, {}).get("impressions")),
        )
        for u in urls if u
    ]

    vitals = CoreWebVitals(
        lcp_ms=_float(cwv, "lcp_ms", "crux"),
        inp_ms=_float(cwv, "inp_ms", "crux"),
        cls=_float(cwv, "cls", "crux"),
    )
    meta = {
        "property_id": _str(ga4.get("property_id") or gsc.get("property_id")),
        "date_range": rng,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    return AnalyticsSnapshot(sessions, clicks, impressions, top_pages, vitals, meta)


def validate_snapshot(snap: AnalyticsSnapshot) -> list[str]:
    v: list[str] = []
    for f in ("sessions", "clicks", "impressions"):
        if not isinstance(getattr(snap, f), int):
            v.append(f"{f} not an int")
    cwv = snap.core_web_vitals
    if not all(isinstance(x, float) for x in (cwv.lcp_ms, cwv.inp_ms, cwv.cls)):
        v.append("core_web_vitals not floats")
    for k in ("property_id", "date_range", "fetched_at"):
        if k not in snap.meta:
            v.append(f"_meta.{k} missing")
    return v


def _rows(d: dict) -> list[dict]:
    rows = d.get("rows")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _int(d: dict, key: str, api: str) -> int:
    if not isinstance(d.get(key), (int, float)) or isinstance(d.get(key), bool):
        raise _Bad(api, f"{api}.{key} missing or non-numeric")
    return int(d[key])


def _float(d: dict, key: str, api: str) -> float:
    if not isinstance(d.get(key), (int, float)) or isinstance(d.get(key), bool):
        raise _Bad(api, f"{api}.{key} missing or non-numeric")
    return float(d[key])


def _as_int(v: Any) -> int:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _str(v: Any) -> str:
    return v if isinstance(v, str) else ""
