"""Own-key search provider strategies.

Each strategy hits one provider directly with the operator's own key and normalizes
the response to the common ``results[]`` shape the crawl adapter already parses:
``{title, url, text, summary?, score?}``. Malformed items are skipped, never
fabricated. The HTTP call is injected (``http_get``) so tests need no network and
no provider SDK is imported at module load.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Callable


def _validate_url_scheme(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme.startswith("https") and parsed.scheme != "http":
        raise ValueError(f"refusing {parsed.scheme!r} URL (allowed: http/https)")
    return url

__all__ = ["STRATEGIES", "default_http_get", "brave", "bing", "serpapi"]

HttpGet = Callable[..., Any]


def default_http_get(url: str, headers: dict[str, str], *, timeout_s: float = 30.0) -> Any:
    """Real GET → parsed JSON. Imported lazily by callers; uses only stdlib urllib."""
    req = urllib.request.Request(_validate_url_scheme(url), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def brave(query: str, n: int, key: str, http_get: HttpGet) -> list[dict[str, Any]]:
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(
        {"q": query, "count": n})
    data = http_get(url, {"X-Subscription-Token": key, "Accept": "application/json"})
    web = (data or {}).get("web", {}) if isinstance(data, dict) else {}
    return _normalize(web.get("results"), title="title", url="url", text="description")


def bing(query: str, n: int, key: str, http_get: HttpGet) -> list[dict[str, Any]]:
    url = "https://api.bing.microsoft.com/v7.0/search?" + urllib.parse.urlencode(
        {"q": query, "count": n})
    data = http_get(url, {"Ocp-Apim-Subscription-Key": key})
    pages = (data or {}).get("webPages", {}) if isinstance(data, dict) else {}
    return _normalize(pages.get("value"), title="name", url="url", text="snippet")


def serpapi(query: str, n: int, key: str, http_get: HttpGet) -> list[dict[str, Any]]:
    # NOTE (verdict minor): SerpAPI accepts the key only as an `api_key` query param, not a
    # header (unlike brave/bing). It stays behind the Transport boundary and never appears in a
    # return value or repr, so secrets-never-leak holds — but a transport-level HTTP logger that
    # records full URLs could surface it. Redact query strings in any such logging.
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(
        {"q": query, "num": n, "api_key": key, "engine": "google"})
    data = http_get(url, {})
    organic = (data or {}).get("organic_results") if isinstance(data, dict) else None
    return _normalize(organic, title="title", url="link", text="snippet")


def _normalize(items: Any, *, title: str, url: str, text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return out
    for item in items:
        if not isinstance(item, dict):
            continue
        u = item.get(url)
        if not isinstance(u, str) or not u:
            continue  # a result without a URL is unusable — skip, don't fabricate
        entry: dict[str, Any] = {
            "title": _s(item.get(title)),
            "url": u,
            "text": _s(item.get(text)),
        }
        if isinstance(item.get("summary"), str):
            entry["summary"] = item["summary"]
        score = item.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            entry["score"] = float(score)
        out.append(entry)
    return out


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""


STRATEGIES: dict[str, Callable[..., list[dict[str, Any]]]] = {
    "brave": brave,
    "bing": bing,
    "serpapi": serpapi,
}
