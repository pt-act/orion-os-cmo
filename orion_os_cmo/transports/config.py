"""Configuration + error types for the self-hosted data Transport.

Secrets (the search API key) are read from explicit args first, then env, and live
ONLY inside this object behind the Transport boundary (H-1). The key is excluded
from ``repr`` so it cannot leak into logs.

The heavy external actions (browser render, search HTTP, Lighthouse subprocess,
HTML fetch) are injectable hooks. In production they default to lazily-built real
implementations; tests inject stubs so importing this module and running the suite
needs no Playwright / Node / network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

__all__ = [
    "TransportConfig",
    "UnsupportedPathError",
    "SearchNotConfiguredError",
    "TransportRunError",
    "DEFAULT_LIGHTHOUSE_CMD",
    "SUPPORTED_SEARCH_PROVIDERS",
]


class UnsupportedPathError(Exception):
    """Raised when ``post`` is called with a path outside the dispatch table."""


class SearchNotConfiguredError(Exception):
    """Raised by the search handler when no provider/key is configured."""


class TransportRunError(Exception):
    """Raised on a handler runtime failure (render/lighthouse/onpage/scrape)."""


SUPPORTED_SEARCH_PROVIDERS = ("brave", "bing", "serpapi")

# `{url}` is substituted at call time. Subprocess form keeps Lighthouse local + free.
DEFAULT_LIGHTHOUSE_CMD = [
    "npx", "lighthouse", "{url}", "--output=json", "--quiet",
    "--chrome-flags=--headless",
]

# Injectable hook signatures (documentation only):
#   Renderer:   (url: str, *, headless: bool, timeout_s: float) -> {url,title,content}
#   SearchHttp: (url: str, headers: dict) -> dict   (parsed JSON)
#   Runner:     (cmd: list[str], *, timeout_s: float) -> object{returncode,stdout,stderr}
#   HtmlFetch:  (url: str, *, timeout_s: float) -> str   (raw HTML)
Renderer = Callable[..., dict]
SearchHttp = Callable[..., Any]
Runner = Callable[..., Any]
HtmlFetch = Callable[..., str]


@dataclass
class TransportConfig:
    search_provider: Optional[str] = None
    search_api_key: Optional[str] = field(default=None, repr=False)  # never in repr (H-1)
    lighthouse_cmd: list[str] = field(default_factory=lambda: list(DEFAULT_LIGHTHOUSE_CMD))
    headless: bool = True
    timeout_s: float = 60.0

    # Injectable hooks — None means "build the real one lazily inside the handler".
    renderer: Optional[Renderer] = field(default=None, repr=False)
    search_http: Optional[SearchHttp] = field(default=None, repr=False)
    subprocess_runner: Optional[Runner] = field(default=None, repr=False)
    html_fetcher: Optional[HtmlFetch] = field(default=None, repr=False)

    @classmethod
    def from_env(cls, **overrides: Any) -> "TransportConfig":
        """Build from env, with explicit overrides taking precedence."""
        cmd_env = os.environ.get("ORION_LIGHTHOUSE_CMD")
        cfg = cls(
            search_provider=os.environ.get("ORION_SEARCH_PROVIDER"),
            search_api_key=os.environ.get("ORION_SEARCH_API_KEY"),
            lighthouse_cmd=cmd_env.split() if cmd_env else list(DEFAULT_LIGHTHOUSE_CMD),
            headless=os.environ.get("ORION_HEADLESS", "1") != "0",
        )
        for key, value in overrides.items():
            setattr(cfg, key, value)
        return cfg

    def has_search(self) -> bool:
        return bool(self.search_provider) and bool(self.search_api_key)
