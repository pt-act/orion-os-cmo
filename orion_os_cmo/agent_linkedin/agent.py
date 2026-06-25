"""agent-linkedin — ghostwrite founder-voice LinkedIn posts from strategy_context.

Directly parallel to agent-x: strategy-only conditioning, schema-validated output,
retry-once on a malformed model response. Each draft is a complete post speaking
to an ICP pain in the operator's voice — no invented facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from ..common.result import Err, Ok, Result
from ..llm.principles import compose
from ..llm.types import LLMClient
from ..strategy_store.store import StrategyStore


@dataclass(frozen=True)
class LinkedInDraft:
    content: str


@dataclass(frozen=True)
class LinkedInAgentError:
    kind: Literal["strategy_missing", "llm_error", "schema_invalid"]
    message: str


class _ValidationError(Exception):
    pass


class LinkedInAgent:
    def __init__(self, strategy_store_path: Path, llm: LLMClient) -> None:
        self._strategy_path = Path(strategy_store_path)
        self._llm = llm

    def run(self) -> Result[list[LinkedInDraft], LinkedInAgentError]:
        strategy = StrategyStore(self._strategy_path).load()
        if strategy is None:
            return Err(LinkedInAgentError("strategy_missing", "no strategy_context at path"))

        system, prompt = build_linkedin_prompt(strategy.get("sections", {}))
        last_err = ""
        for _ in range(2):
            try:
                raw = self._llm.complete_json(system=system, prompt=prompt)
            except Exception as exc:
                return Err(LinkedInAgentError("llm_error", str(exc)))
            try:
                return Ok(validate_linkedin_drafts(raw.get("drafts") if isinstance(raw, dict) else None))
            except _ValidationError as exc:
                last_err = str(exc)
        return Err(LinkedInAgentError("schema_invalid", last_err))


def validate_linkedin_drafts(raw: Any) -> list[LinkedInDraft]:
    if not isinstance(raw, list) or not raw:
        raise _ValidationError("drafts missing or empty")
    out: list[LinkedInDraft] = []
    for item in raw:
        if not isinstance(item, dict):
            raise _ValidationError("draft is not an object")
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            raise _ValidationError("draft content empty")
        out.append(LinkedInDraft(content=content))
    return out


def build_linkedin_prompt(sections: dict) -> tuple[str, str]:
    bv = sections.get("brand_voice", {})
    icp = sections.get("icp", {})
    gp = sections.get("growth_playbook", {})
    pains = icp.get("pains", []) if isinstance(icp.get("pains"), list) else []
    priorities = gp.get("priorities", []) if isinstance(gp.get("priorities"), list) else []
    pain = pains[0] if pains else ""
    priority = priorities[0] if priorities else ""
    samples = "; ".join(bv.get("sample_phrases", []) if isinstance(bv.get("sample_phrases"), list) else [])

    system = compose((
        "Your role: a ghostwriter producing founder-voice LinkedIn posts for operator review, "
        f"in this brand voice — tone: {bv.get('tone', '')}, register: {bv.get('register', '')}; "
        f"echo these sample phrases where natural: {samples}. Speak to a real ICP pain. "
        "Competitor mentions may name only the provided competitors. Each post carries one "
        "genuine insight — hook, insight, light call to action — and reads like a person, not "
        "a brand account."
    ), voice=True)
    prompt = "\n".join([
        f"Narrative angle — ICP pain: {pain}; this week's priority: {priority}.",
        f"ICP pains: {', '.join(p for p in pains if isinstance(p, str))}",
        "Write 2-3 complete posts, each hook -> insight -> call to action.",
        'Return JSON: { "drafts": [{ "content": str }] }.',
    ])
    return system, prompt
