"""agent-reddit — find high-intent threads and draft community-native replies.

Keywords come from the operator's ICP/positioning, search is a single tool call,
and every draft is bound to a real ``Thread.url`` (no draft without a thread). A
model failure on one thread skips that thread — it never aborts the whole pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..adapters.reddit_listen.adapter import RedditAdapter
from ..adapters.reddit_listen.types import Thread
from ..common.result import Err, Ok, Result
from ..llm.principles import compose
from ..llm.types import LLMClient
from ..strategy_store.store import StrategyStore

_RETAIN = {"question", "complaint", "comparison", "recommendation"}


@dataclass(frozen=True)
class RedditDraft:
    thread_url: str
    intent: str
    draft_reply: str


@dataclass(frozen=True)
class SkippedThread:
    thread_url: str
    intent: str
    reason: str  # "low_intent" | "llm_error" | "empty_reply"


@dataclass(frozen=True)
class RedditAgentError:
    kind: Literal["strategy_missing", "search_failed"]
    message: str


class RedditAgent:
    def __init__(self, strategy_store_path: Path, reddit_adapter: RedditAdapter, llm: LLMClient) -> None:
        self._strategy_path = Path(strategy_store_path)
        self._reddit = reddit_adapter
        self._llm = llm
        # Q-10: the scored-but-skipped manifest (Req #3) — surfaced for operator
        # transparency. Populated each run; each entry is {thread_url, intent, reason}.
        self.skipped: list[SkippedThread] = []

    def run(self) -> Result[list[RedditDraft], RedditAgentError]:
        strategy = StrategyStore(self._strategy_path).load()
        if strategy is None:
            return Err(RedditAgentError("strategy_missing", "no strategy_context at path"))
        sections = strategy.get("sections", {})

        search = self._reddit.reddit_search(build_keywords(sections))
        if not search.ok:
            return Err(RedditAgentError("search_failed", search.error.message))

        self.skipped = []
        drafts: list[RedditDraft] = []
        for thread in search.value.threads:
            if not score_intent(thread):
                self.skipped.append(SkippedThread(thread.url, thread.intent, "low_intent"))
                continue
            try:
                reply = self._llm.complete(system=_SYSTEM, prompt=build_draft_prompt(thread, sections))
            except Exception:
                self.skipped.append(SkippedThread(thread.url, thread.intent, "llm_error"))
                continue  # single-thread LLM failure → skip this thread, keep the rest
            reply = reply.strip()
            if not reply:
                self.skipped.append(SkippedThread(thread.url, thread.intent, "empty_reply"))
                continue
            drafts.append(RedditDraft(thread_url=thread.url, intent=thread.intent, draft_reply=reply))
        return Ok(drafts)


# ── pure helpers ─────────────────────────────────────────────────────────────

def build_keywords(sections: dict) -> list[str]:
    icp = sections.get("icp", {})
    pos = sections.get("positioning", {})
    out: list[str] = []
    for key in ("pains", "triggers"):
        vals = icp.get(key)
        if isinstance(vals, list):
            out.extend(v for v in vals if isinstance(v, str))
    one_liner = pos.get("one_liner")
    if isinstance(one_liner, str) and one_liner:
        out.append(one_liner)
    # Stable de-dup preserving order.
    seen: set[str] = set()
    return [k for k in out if not (k in seen or seen.add(k))]


def score_intent(thread: Thread) -> bool:
    """Retain only high-intent threads, by the intent label the adapter assigned."""
    return thread.intent in _RETAIN


def build_draft_prompt(thread: Thread, sections: dict) -> str:
    bv = sections.get("brand_voice", {})
    pos = sections.get("positioning", {})
    return "\n".join([
        f"Brand voice — tone: {bv.get('tone', '')}, register: {bv.get('register', '')}.",
        f"Positioning: {pos.get('one_liner', '')}",
        f"Subreddit: r/{thread.subreddit} (write to its norms — helpful first, not salesy).",
        f"Thread ({thread.intent}): {thread.snippet}",
        "Draft a concise, genuinely useful reply. Disclose affiliation if you mention the product.",
    ])


_ROLE = (
    "Your role: a community-native contributor drafting one Reddit reply for the operator to "
    "review and post. You're given a single real thread and the brand's voice and positioning. "
    "Write a genuinely useful, subreddit-appropriate reply — helpful first, never salesy — and "
    "disclose the brand affiliation if you mention the product. If a thread doesn't warrant a "
    "genuinely helpful reply, it's fine to return nothing rather than force one."
)

_SYSTEM = compose(_ROLE, voice=True)
