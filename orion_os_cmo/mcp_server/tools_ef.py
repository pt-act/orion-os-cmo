"""Group E (agent tools) + Group F (orchestrator tools).

Client-agnostic MCP tools that run agents and the weekly orchestrator using
an ``HttpLLMClient`` configured from environment variables (no Claude-specific
code).  Each tool constructs the agent lazily with shared adapters and LLM
client from ``_shared``.
"""

from __future__ import annotations

from typing import Any

from ..agent_coding.agent import CodingAgent as _CodingAgent
from ..agent_geo.agent import GeoAgent as _GeoAgent
from ..agent_influencer.agent import InfluencerAgent as _InfluencerAgent
from ..agent_linkedin.agent import LinkedInAgent as _LinkedInAgent
from ..agent_reddit.agent import RedditAgent as _RedditAgent
from ..agent_seo.agent import SeoAgent as _SeoAgent
from ..agent_ugc.agent import UGCAgent as _UGCAgent
from ..agent_writer.agent import WriterAgent as _WriterAgent
from ..agent_x.agent import XAgent as _XAgent
from ..orchestrator.coordinator import RunCoordinator
from ._shared import adapters, llm, ok, strategy_path, unwrap, ws
from .server import mcp

# ── Group E — agent tools ────────────────────────────────────────────────────


@mcp.tool()
def agent_run_seo(url: str, run_at: str | None = None) -> dict:
    """Run the SEO agent: audit the site and surface ranked on-page fixes."""
    agent = _SeoAgent(strategy_path(), adapters.seo, adapters.analytics, llm())
    return ok(unwrap(agent.run(url, run_at)))


@mcp.tool()
def agent_run_geo(brand: str) -> dict:
    """Run the GEO agent: probe brand visibility across AI answer engines."""
    agent = _GeoAgent(strategy_path(), adapters.geo, llm())
    return ok(unwrap(agent.run(brand)))


@mcp.tool()
def agent_run_reddit() -> dict:
    """Run the Reddit agent: find high-intent threads and draft replies."""
    agent = _RedditAgent(strategy_path(), adapters.reddit, llm())
    return ok(unwrap(agent.run()))


@mcp.tool()
def agent_run_x() -> dict:
    """Run the X/Twitter agent: draft posts and threads in brand voice."""
    agent = _XAgent(strategy_path(), llm())
    return ok(unwrap(agent.run()))


@mcp.tool()
def agent_run_linkedin() -> dict:
    """Run the LinkedIn agent: ghostwrite founder-voice posts."""
    agent = _LinkedInAgent(strategy_path(), llm())
    return ok(unwrap(agent.run()))


@mcp.tool()
def agent_run_writer() -> dict:
    """Run the Writer agent: draft SEO articles from strategy data."""
    agent = _WriterAgent(strategy_path(), None, None, llm())
    return ok(unwrap(agent.run()))


@mcp.tool()
def agent_run_coding(repo: str) -> dict:
    """Run the Coding agent: turn SEO/GEO findings into a GitHub PR."""
    agent = _CodingAgent(strategy_path(), None, None, adapters.github, llm())
    return ok(unwrap(agent.run(repo)))


@mcp.tool()
def agent_run_influencer(niche: str | None = None) -> dict:
    """Run the Influencer agent: discover creators and draft outreach."""
    agent = _InfluencerAgent(strategy_path(), adapters.creators, llm())
    return ok(unwrap(agent.run(niche)))


@mcp.tool()
def agent_run_ugc(briefs: list[str]) -> dict:
    """Run the UGC agent: render video clips from operator briefs."""
    agent = _UGCAgent(strategy_path(), adapters.video, llm())
    result = agent.run(briefs)
    if result.error is not None:
        raise ValueError(result.error.message)
    return ok(result)


# ── Group F — orchestrator tool ──────────────────────────────────────────────


@mcp.tool()
def orchestrator_run(
    week_key: str,
    week_of: str,
    url: str = "",
    brand: str = "",
    repo: str = "",
    agents_enabled: list[str] | None = None,
    briefs: list[str] | None = None,
) -> dict:
    """Run the weekly orchestration pass in a client-agnostic way.

    Fires all enabled agents in fixed order, computes week-over-week deltas,
    assembles a single prioritized brief, and persists everything to the
    workspace.  Accepts per-agent parameters; agents not supplied with their
    required parameters will use defaults from the workspace strategy.

    Parameters
    ----------
    week_key : str
        ISO week identifier (e.g. "2026-W26").
    week_of : str
        ISO date of the week's Monday.
    url : str, optional
        Product URL for the SEO agent.
    brand : str, optional
        Brand name for the GEO agent.
    repo : str, optional
        GitHub repo slug for the Coding agent.
    agents_enabled : list[str], optional
        Subset of agents to run (default: all nine).
    briefs : list[str], optional
        Video briefs for the UGC agent.
    """
    _llm = llm()
    _sp = strategy_path()
    agents: dict[str, Any] = {}
    enabled = set(agents_enabled or [])

    def _maybe(name: str, fn: Any) -> None:
        if not agents_enabled or name in enabled:
            agents[name] = fn

    _maybe("seo", lambda u=url: _SeoAgent(
        _sp, adapters.seo, adapters.analytics, _llm).run(u))
    _maybe("geo", lambda b=brand: _GeoAgent(
        _sp, adapters.geo, _llm).run(b))
    _maybe("reddit", lambda: _RedditAgent(
        _sp, adapters.reddit, _llm).run())
    _maybe("x", lambda: _XAgent(_sp, _llm).run())
    _maybe("linkedin", lambda: _LinkedInAgent(_sp, _llm).run())
    _maybe("writer", lambda: _WriterAgent(_sp, None, None, _llm).run())
    _maybe("coding", lambda r=repo: _CodingAgent(
        _sp, None, None, adapters.github, _llm).run(r))
    _maybe("influencer", lambda: _InfluencerAgent(
        _sp, adapters.creators, _llm).run())
    if not agents_enabled or "ugc" in enabled:
        _b = briefs or []
        agents["ugc"] = lambda: _ugc_wrapper(_UGCAgent(_sp, adapters.video, _llm), _b)

    coordinator = RunCoordinator(ws(), agents)
    return ok(unwrap(coordinator.run(week_key, week_of)))


def _ugc_wrapper(agent: Any, briefs: list[str]) -> Any:
    result = agent.run(briefs)
    if result.error is not None:
        raise ValueError(result.error.message)
    return result.assets
