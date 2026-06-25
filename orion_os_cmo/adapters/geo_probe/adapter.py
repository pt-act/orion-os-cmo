"""GEO-probe façade — query AI-answer engines and ground every mention flag in
literal response text.

The grounding is the whole point: ``mentioned: true`` is set only when the brand
string actually appears in the response, and the proof (a snippet containing it)
travels with the result. A failed engine does not crash the pass — surviving
engines' results are kept; total failure surfaces a structured ``ProbeError``.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from ...common.result import Err, Ok, Result
from .types import GeoReport, ModelResult, ProbeError, ProbeErrorSource, Transport

ENGINE_PATH = "/api/geo/answer"

_POSITIVE = {"best", "great", "leading", "love", "excellent", "recommended", "top", "powerful"}
_NEGATIVE = {"worst", "bad", "lacks", "limited", "expensive", "poor", "avoid", "buggy"}
_SENTENCE = re.compile(r"[.!?]+\s+")


class GeoProbeAdapter:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def probe(
        self,
        brand: str,
        questions: list[str],
        models: list[str],
        competitors: Optional[list[str]] = None,
    ) -> Result[GeoReport, ProbeError]:
        per_model: list[ModelResult] = []
        unmentioned_texts: list[str] = []
        first_error: Optional[ProbeError] = None

        for model in models:
            for question in questions:
                got = self._query(model, question, brand)
                if not got.ok:
                    first_error = first_error or got.error
                    continue  # partial results preserved — other engines not suppressed
                text = got.value
                parsed = parse_response(text, brand)
                per_model.append(ModelResult(model=model, question=question, **parsed))
                if not parsed["mentioned"]:
                    unmentioned_texts.append(text)

        if not per_model:  # every pair failed
            err = first_error or ProbeError("engine_unavailable", "no engine returned a response",
                                            ProbeErrorSource("none", ""))
            return Err(err)

        mentioned = sum(1 for r in per_model if r.mentioned)
        score = mentioned / len(per_model)
        gaps = extract_competitor_gaps(unmentioned_texts, competitors or [])
        return Ok(GeoReport(score=round(score, 6), per_model=per_model, competitor_gaps=gaps))

    def _query(self, model: str, question: str, brand: str) -> Result[str, ProbeError]:
        try:
            raw = self._transport.post(ENGINE_PATH, {"model": model, "question": question, "brand": brand})
        except Exception as exc:
            return Err(ProbeError("transport", str(exc), ProbeErrorSource(model, question)))
        text = _extract_text(raw)
        if text is None:
            return Err(ProbeError("invalid_response", "engine response had no text",
                                  ProbeErrorSource(model, question)))
        return Ok(text)


# ── pure helpers (ResponseParser / CompetitorExtractor) ──────────────────────

def _brand_index(text_low: str, brand_low: str) -> int:
    """Index of the first whole-word brand occurrence, or -1.

    Q-1: word-boundary match — a brand 'acme' must NOT match inside 'macme' or
    'acmex'. Boundaries are non-word chars (or string edges) on both sides; this
    handles multi-word brands too (the edges of the whole phrase are checked).
    """
    if not brand_low:
        return -1
    pattern = r"(?<![0-9a-z])" + re.escape(brand_low) + r"(?![0-9a-z])"
    match = re.search(pattern, text_low)
    return match.start() if match else -1


def brand_in(text: str, brand: str) -> bool:
    """Public boundary-aware membership test (reused by the validator)."""
    return _brand_index(text.lower(), brand.lower()) >= 0


def parse_response(text: str, brand: str) -> dict[str, Any]:
    """Ground a mention flag in literal text. Never flags a mention without proof."""
    low = text.lower()
    blow = brand.lower()
    idx = _brand_index(low, blow)
    if idx < 0:
        return {"mentioned": False, "position": None, "sentiment": "none",
                "response_snippet": text[:500]}

    # Ordinal sentence position of the first mention (boundary-aware).
    sentences = _SENTENCE.split(text)
    position = next((i for i, s in enumerate(sentences) if _brand_index(s.lower(), blow) >= 0), 0)
    # Snippet centered on the mention so the brand is always present (provenance).
    start = max(0, idx - 200)
    snippet = text[start:start + 500]
    if _brand_index(snippet.lower(), blow) < 0:  # safety: guarantee the invariant
        snippet = text[idx:idx + 500]
    return {"mentioned": True, "position": position,
            "sentiment": _sentiment(low, idx, len(blow)), "response_snippet": snippet}


def _sentiment(low: str, idx: int, blen: int) -> str:
    window = low[max(0, idx - 80): idx + blen + 80]
    pos = any(w in window for w in _POSITIVE)
    neg = any(w in window for w in _NEGATIVE)
    if pos and not neg:
        return "positive"
    if neg and not pos:
        return "negative"
    return "neutral"


def extract_competitor_gaps(unmentioned_texts: list[str], competitors: list[str]) -> list[str]:
    """Competitors named in responses where the brand was absent (sorted, unique)."""
    found: set[str] = set()
    for text in unmentioned_texts:
        low = text.lower()
        for comp in competitors:
            if comp and comp.lower() in low:
                found.add(comp)
    return sorted(found)


def validate_report(report: GeoReport, brand: str) -> list[str]:
    """Schema + provenance validation. Q-2: the provenance invariant is enforced here,
    not only at parse time — a ``mentioned: true`` row MUST carry the brand (whole-word)
    in its snippet, so a hand-built or tampered row that violates it is rejected.
    ``brand`` is required because the row does not carry it.
    """
    v: list[str] = []
    if not (0.0 <= report.score <= 1.0):
        v.append("score out of [0,1]")
    for i, r in enumerate(report.per_model):
        if r.mentioned:
            if r.position is None:
                v.append(f"per_model[{i}] mentioned but null position")
            if not brand_in(r.response_snippet, brand):
                v.append(f"per_model[{i}] mentioned=true but brand absent from snippet (provenance)")
        if r.sentiment not in ("positive", "neutral", "negative", "none"):
            v.append(f"per_model[{i}].sentiment invalid")
    return v


def _extract_text(raw: Any) -> Optional[str]:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        for key in ("text", "response", "answer", "content"):
            if isinstance(raw.get(key), str):
                return raw[key]
    return None
