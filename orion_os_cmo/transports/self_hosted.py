"""SelfHostedTransport — the operator-owned data path behind the Transport seam.

Implements the shared ``Transport`` protocol (``post(path, body) -> Any``) and routes
each existing adapter path to a LOCAL handler — Playwright scrape, own-key search,
local Lighthouse subprocess, local on-page HTML parse — so ``crawl`` and ``seo_audit``
run with no paid aggregator and no code change (ADR #7).

The load-bearing invariant: every handler returns the documented success shape built
from REAL fetched data, or RAISES — never a well-formed-but-fabricated success. That
is what keeps the adapters' existing structured-error and grounding gates working
unchanged. Heavy deps (Playwright / Lighthouse / search HTTP) are imported lazily
INSIDE their handler, so importing this module is install-free.
"""

from __future__ import annotations

import json
from typing import Any, Callable

# Route fidelity by construction: the dispatch keys ARE the adapters' own path
# constants, imported from the adapters so they can never drift.
from ..adapters.crawl.adapter import SCRAPE_PATH, SEARCH_PATH
from ..adapters.seo_audit.adapter import LIGHTHOUSE_PATH, PROVIDER_PATH as ONPAGE_PATH
from .config import (
    SearchNotConfiguredError,
    SUPPORTED_SEARCH_PROVIDERS,
    TransportConfig,
    TransportRunError,
    UnsupportedPathError,
)
from .onpage import parse_onpage_issues

__all__ = ["SelfHostedTransport", "SCRAPE_PATH", "SEARCH_PATH", "LIGHTHOUSE_PATH", "ONPAGE_PATH"]


class SelfHostedTransport:
    def __init__(self, config: TransportConfig) -> None:
        self._config = config
        self._dispatch: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            SCRAPE_PATH: self._scrape,
            SEARCH_PATH: self._search,
            LIGHTHOUSE_PATH: self._lighthouse,
            ONPAGE_PATH: self._onpage,
        }

    # The only public surface (Transport protocol).
    def post(self, path: str, body: dict[str, Any]) -> Any:
        handler = self._dispatch.get(path)
        if handler is None:
            raise UnsupportedPathError(f"no self-hosted handler for path '{path}'")
        return handler(body or {})

    def __repr__(self) -> str:  # never leak the key
        return f"SelfHostedTransport(provider={self._config.search_provider!r})"

    # ── handlers ───────────────────────────────────────────────────────────────

    def _scrape(self, body: dict[str, Any]) -> dict[str, Any]:
        url = _require_url(body, "scrape")
        renderer = self._config.renderer or _default_renderer
        rendered = renderer(url, headless=self._config.headless, timeout_s=self._config.timeout_s)
        if not isinstance(rendered, dict):
            raise TransportRunError("scrape: renderer returned a non-dict")
        # Empty content is an honest (non-fabricated) empty result: hand it to the
        # adapter as-is so the adapter's own `empty` gate classifies it. A render
        # FAILURE raises above and the adapter maps it to `transport`.
        return {
            "url": _s(rendered.get("url")) or url,
            "title": _s(rendered.get("title")),
            "content": _s(rendered.get("content")),
        }

    def _search(self, body: dict[str, Any]) -> dict[str, Any]:
        if not self._config.has_search():
            raise SearchNotConfiguredError("search requires ORION_SEARCH_PROVIDER + ORION_SEARCH_API_KEY")
        provider = (self._config.search_provider or "").lower()
        if provider not in SUPPORTED_SEARCH_PROVIDERS:
            raise SearchNotConfiguredError(f"unsupported search provider '{provider}'")

        from . import search_providers  # local import keeps module load clean
        strategy = search_providers.STRATEGIES[provider]
        http_get = self._config.search_http or search_providers.default_http_get
        query = _s(body.get("query"))
        n = body.get("numResults") if isinstance(body.get("numResults"), int) else 5
        results = strategy(query, n, self._config.search_api_key, http_get)
        return {"results": results}

    def _lighthouse(self, body: dict[str, Any]) -> dict[str, Any]:
        url = _require_url(body, "lighthouse")
        cmd = [part.replace("{url}", url) for part in self._config.lighthouse_cmd]
        runner = self._config.subprocess_runner or _default_runner
        try:
            proc = runner(cmd, timeout_s=self._config.timeout_s)
        except FileNotFoundError as exc:  # node / npx / lighthouse not installed
            raise TransportRunError(f"lighthouse: binary not found ({exc})") from exc
        if getattr(proc, "returncode", 1) != 0:
            raise TransportRunError(f"lighthouse: nonzero exit ({getattr(proc, 'returncode', '?')})")
        try:
            data = json.loads(_proc_stdout(proc))
        except (ValueError, TypeError) as exc:
            raise TransportRunError("lighthouse: unparseable JSON output") from exc

        score = data.get("categories", {}).get("performance", {}).get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise TransportRunError("lighthouse: missing performance_score")  # never fabricate

        out: dict[str, Any] = {
            "performance_score": float(score),
            "version": _s(data.get("lighthouseVersion")) or "unknown",
        }
        audits = data.get("audits", {}) if isinstance(data.get("audits"), dict) else {}
        for key, audit_id in (("lcp_ms", "largest-contentful-paint"),
                              ("inp_ms", "interaction-to-next-paint"),
                              ("cls", "cumulative-layout-shift")):
            val = audits.get(audit_id, {}).get("numericValue") if isinstance(
                audits.get(audit_id), dict) else None
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                out[key] = float(val)
        return out

    def _onpage(self, body: dict[str, Any]) -> dict[str, Any]:
        url = _require_url(body, "onpage")
        fetcher = self._config.html_fetcher or _default_html_fetcher
        html = fetcher(url, timeout_s=self._config.timeout_s)
        if not isinstance(html, str):
            raise TransportRunError("onpage: fetcher returned non-text")
        return {
            "provider": "self-hosted",
            "issues": parse_onpage_issues(html),
            "serp_snapshot": [],
        }


# ── default (lazy) real implementations ──────────────────────────────────────

def _default_renderer(url: str, *, headless: bool, timeout_s: float) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright  # lazy: only when actually rendering
    except ImportError as exc:
        raise TransportRunError("scrape: Playwright not installed") from exc
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            page.goto(url, timeout=int(timeout_s * 1000))
            title = page.title()
            content = page.inner_text("body")
            final_url = page.url
        finally:
            browser.close()
    return {"url": final_url, "title": title, "content": content}


def _default_runner(cmd: list[str], *, timeout_s: float) -> Any:
    import subprocess  # stdlib, but kept local for symmetry with the injected stub
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)


def _default_html_fetcher(url: str, *, timeout_s: float) -> str:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "orion-os-cmo/self-hosted"})
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme.startswith("https") and parsed.scheme != "http":
        raise ValueError(f"refusing {parsed.scheme!r} URL (allowed: http/https)")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


# ── small helpers ────────────────────────────────────────────────────────────

def _require_url(body: dict[str, Any], who: str) -> str:
    url = body.get("url")
    if not isinstance(url, str) or not url:
        raise TransportRunError(f"{who}: missing url")
    return url


def _proc_stdout(proc: Any) -> str:
    out = getattr(proc, "stdout", "")
    if isinstance(out, bytes):
        return out.decode("utf-8", errors="replace")
    return out if isinstance(out, str) else ""


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
