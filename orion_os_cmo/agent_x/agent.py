"""agent-x — draft a weekly batch of X posts and threads.

Conditions only on the operator-owned ``strategy_context`` (no retrieval, no
invented metrics — any statistic must come from ``growth_playbook.notes``). The
schema validator is the gate: a malformed draft is never shipped, and a malformed
model response is retried once before failing structurally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..common.result import Err, Ok, Result
from ..llm.principles import compose
from ..llm.types import LLMClient
from ..strategy_store.store import StrategyStore

_KINDS = {"post", "thread"}


@dataclass(frozen=True)
class XDraft:
    kind: Literal["post", "thread"]
    content: str


@dataclass(frozen=True)
class XAgentError:
    kind: Literal["strategy_missing", "llm_error", "schema_invalid"]
    message: str


class _ValidationError(Exception):
    pass


class XAgent:
    def __init__(self, strategy_store_path: Path, llm: LLMClient) -> None:
        self._strategy_path = Path(strategy_store_path)
        self._llm = llm

    def run(self) -> Result[list[XDraft], XAgentError]:
        strategy = StrategyStore(self._strategy_path).load()
        if strategy is None:
            return Err(XAgentError("strategy_missing", "no strategy_context at path"))

        system, prompt = build_x_prompt(strategy.get("sections", {}))
        last_err = ""
        for _ in range(2):  # one retry on malformed output
            try:
                raw = self._llm.complete_json(system=system, prompt=prompt)
            except Exception as exc:
                return Err(XAgentError("llm_error", str(exc)))
            try:
                return Ok(validate_x_drafts(raw.get("drafts") if isinstance(raw, dict) else None))
            except _ValidationError as exc:
                last_err = str(exc)
        return Err(XAgentError("schema_invalid", last_err))


def _validate_thread_format(content: str) -> None:
    """Raise ``_ValidationError`` if thread content does not follow ``N/ turn`` format."""
    for lineno, line in enumerate(content.split("\n"), 1):
        stripped = line.strip()
        if not stripped:
            continue
        if not re.match(r"^\d+/", stripped):
            raise _ValidationError(f"thread line {lineno}: missing numbered turn (expected N/ format)")


def validate_x_drafts(raw: Any) -> list[XDraft]:
    if not isinstance(raw, list) or not raw:
        raise _ValidationError("drafts missing or empty")
    out: list[XDraft] = []
    for item in raw:
        if not isinstance(item, dict):
            raise _ValidationError("draft is not an object")
        kind = item.get("kind")
        content = item.get("content")
        if kind not in _KINDS or not isinstance(content, str) or not content.strip():
            raise _ValidationError("draft has invalid kind or empty content")
        if kind == "thread":
            _validate_thread_format(content)
        out.append(XDraft(kind=kind, content=content))  # type: ignore[arg-type]
    return out


def build_x_prompt(sections: dict) -> tuple[str, str]:
    bv = sections.get("brand_voice", {})
    pos = sections.get("positioning", {})
    gp = sections.get("growth_playbook", {})
    priorities = gp.get("priorities", []) if isinstance(gp.get("priorities"), list) else []
    angle = priorities[0] if priorities else (pos.get("one_liner", "") or "")
    diffs = pos.get("differentiators", []) if isinstance(pos.get("differentiators"), list) else []
    diff_lines = "; ".join(d.get("claim", "") for d in diffs if isinstance(d, dict))

    system = compose((
        "Your role: an X writer drafting a week's posts and threads for operator review, in "
        f"this brand voice — tone: {bv.get('tone', '')}, register: {bv.get('register', '')}; "
        f"do: {', '.join(bv.get('do', []))}; don't: {', '.join(bv.get('dont', []))}. Every "
        "statistic must come from the growth-playbook notes provided — invent none. Posts "
        "should earn attention on the strength of the idea, not manufactured urgency or hype. "
        "Produce a focused set — a few strong single posts and one or two threads — not a "
        "flood; format threads as numbered turns (1/, 2/ ...)."
    ), voice=True)
    prompt = "\n".join([
        f"Weekly angle: {angle}",
        f"Differentiators: {diff_lines}",
        f"Playbook notes: {gp.get('notes', '')}",
        "Produce 3-5 single posts and 1-2 threads. Threads are newline-delimited numbered turns (1/, 2/...).",
        'Return JSON: { "drafts": [{ "kind": "post"|"thread", "content": str }] }.',
    ])
    return system, prompt
