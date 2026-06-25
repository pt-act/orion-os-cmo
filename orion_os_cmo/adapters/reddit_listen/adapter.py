"""Reddit-listen façade — one search call, a typed sourced ``Thread[]``.

Exactly one HTTP call per invocation (cost transparency). A zero-results
response is a structured ``no_results`` error, never a silent ``Ok([])``.
"""

from __future__ import annotations

from typing import Any, Optional

from ...common.result import Err, Ok, Result
from .types import ErrorSource, RedditError, RedditSearchResult, Thread, Transport

SEARCH_PATH = "/api/reddit/search"

_VALID_INTENT = {"question", "complaint", "comparison", "recommendation", "other"}


class RedditAdapter:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def reddit_search(
        self, keywords: list[str], subreddits: Optional[list[str]] = None
    ) -> Result[RedditSearchResult, RedditError]:
        query = " ".join(keywords)
        body: dict[str, Any] = {"query": query, "keywords": keywords}
        if subreddits:
            body["subreddits"] = subreddits

        try:
            raw = self._transport.post(SEARCH_PATH, body)
        except Exception as exc:
            return Err(RedditError("transport", str(exc), ErrorSource("reddit/search", query)))

        if not isinstance(raw, dict):
            return Err(RedditError("invalid_response", "response not an object",
                                   ErrorSource("reddit/search", query)))
        if raw.get("error") is not None:
            return Err(RedditError("api_error", str(raw["error"]),
                                   ErrorSource("reddit/search", query)))
        if not isinstance(raw.get("threads"), list):
            return Err(RedditError("invalid_response", "missing threads[]",
                                   ErrorSource("reddit/search", query)))

        threads = [t for t in (_to_thread(item) for item in raw["threads"]) if t is not None]
        if not threads:
            return Err(RedditError("no_results", "no threads matched", ErrorSource("reddit/search", query)))
        return Ok(RedditSearchResult(threads=threads))


def _to_thread(item: Any) -> Optional[Thread]:
    if not isinstance(item, dict):
        return None
    url = _s(item.get("url"))
    subreddit = _s(item.get("subreddit"))
    snippet = _s(item.get("snippet")) or _s(item.get("title"))
    engagement = item.get("engagement")
    eng = int(engagement) if isinstance(engagement, (int, float)) and not isinstance(engagement, bool) else 0
    if not url or not subreddit or not snippet or eng < 0:
        return None  # never ship a malformed Thread
    intent = item.get("intent")
    intent = intent if intent in _VALID_INTENT else _infer_intent(snippet)
    return Thread(url=url, subreddit=subreddit, intent=intent, engagement=eng, snippet=snippet)


def _infer_intent(snippet: str) -> str:
    low = snippet.lower()
    if "?" in snippet or low.startswith(("how", "what", "why", "which", "anyone")):
        return "question"
    if any(w in low for w in ("vs", "versus", "compare", "alternative")):
        return "comparison"
    if any(w in low for w in ("recommend", "suggestion", "best")):
        return "recommendation"
    if any(w in low for w in ("hate", "broken", "issue", "problem", "frustrat")):
        return "complaint"
    return "other"


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
