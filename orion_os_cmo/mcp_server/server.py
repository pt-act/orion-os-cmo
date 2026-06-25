"""MCP server exposing Orion OS CMO capabilities as client-agnostic tools/resources.

Every tool wraps exactly one adapter method (H-3). The server starts on stdio
using the FastMCP framework.  Credentials are injected via ``SelfHostedTransport``
built from env vars.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

from fastmcp import FastMCP

from ..adapters.video_gen.types import SUPPORTED_ASPECTS
from ..client_workspace.store import WorkspaceStore
from ..client_workspace.types import MetricRow, OutputItem, OutputStatus
from ._shared import adapters, ok, unwrap, ws

# ── app ──────────────────────────────────────────────────────────────────────

mcp = FastMCP("orion-os-cmo")

# ── workspace resources (Group D) ────────────────────────────────────────────


@mcp.resource("workspace://strategy")
def workspace_strategy() -> dict:
    return cast(dict, unwrap(ws().read_strategy()))


@mcp.resource("workspace://metrics")
def workspace_metrics() -> dict:
    return ok(unwrap(ws().read_metrics()))


@mcp.resource("workspace://outputs")
def workspace_outputs() -> dict:
    return ok(unwrap(ws().read_outputs()))


@mcp.resource("workspace://approvals")
def workspace_approvals() -> dict:
    return ok(unwrap(ws().read_approvals()))


@mcp.resource("workspace://runs")
def workspace_runs() -> dict | None:
    record = unwrap(ws().read_last_run())
    if record is None:
        return None
    return ok(record)


# ── workspace management tools (Group C) ─────────────────────────────────────


@mcp.tool()
def workspace_init(root: str) -> dict:
    store = unwrap(WorkspaceStore.init(Path(root)))
    return cast(dict, unwrap(store.read_config()))


@mcp.tool()
def workspace_read_strategy() -> dict:
    return cast(dict, unwrap(ws().read_strategy()))


@mcp.tool()
def workspace_write_strategy(ctx: dict) -> dict:
    from ..strategy_store.context import StrategyContext
    sc = StrategyContext(**ctx)
    return cast(dict, unwrap(ws().write_strategy(sc)))


@mcp.tool()
def workspace_create_output(
    date: str, agent: str, type: str, provenance: str, link: str = "none"
) -> dict:
    item = OutputItem(date=date, agent=agent, type=type, provenance=provenance, link=link)
    return {"output_id": unwrap(ws().create_output(item))}


@mcp.tool()
def workspace_advance_output(id: str, status: str, tool_result: str = "") -> dict:
    st: OutputStatus = cast(OutputStatus, status)
    unwrap(ws().advance_output(id, st, tool_result or None))
    return {"id": id, "status": status}


@mcp.tool()
def workspace_read_metrics() -> dict:
    return ok(unwrap(ws().read_metrics()))


@mcp.tool()
def workspace_append_metric(date: str, metric: str, value: float, source: str) -> dict:
    row = MetricRow(date=date, metric=metric, value=value, source=source)
    unwrap(ws().append_metric(row))
    return ok(unwrap(ws().read_metrics()))


@mcp.tool()
def workspace_read_outputs() -> dict:
    return ok(unwrap(ws().read_outputs()))


@mcp.tool()
def workspace_read_approvals() -> dict:
    return ok(unwrap(ws().read_approvals()))


@mcp.tool()
def workspace_read_runs() -> dict | None:
    record = unwrap(ws().read_last_run())
    if record is None:
        return None
    return ok(record)


# ── data-collection adapter tools (Group A) ──────────────────────────────────


@mcp.tool()
def seo_audit(url: str) -> dict:
    return ok(unwrap(adapters.seo.seo_audit(url)))


@mcp.tool()
def fetch_analytics() -> dict:
    return ok(unwrap(adapters.analytics.fetch_analytics()))


@mcp.tool()
def geo_probe(
    brand: str,
    questions: list[str],
    models: list[str] | None = None,
    competitors: list[str] | None = None,
) -> dict:
    return ok(unwrap(adapters.geo.probe(brand, questions, models or [], competitors)))


@mcp.tool()
def crawl_page(url: str) -> dict:
    return ok(unwrap(adapters.crawl.scrape(url)))


@mcp.tool()
def reddit_search(keywords: list[str], subreddits: list[str] | None = None) -> dict:
    return ok(unwrap(adapters.reddit.reddit_search(keywords, subreddits)))


@mcp.tool()
def discover_creators(niche: str, platform: str, follower_tier: str = "micro") -> dict:
    return ok(unwrap(adapters.creators.discover_creators(niche, platform, follower_tier)))


# ── side-effect adapter tools (Group B) ──────────────────────────────────────


@mcp.tool()
def open_pr(
    repo: str, branch: str, diff: str, description: str, base_branch: str = "main"
) -> dict:
    return ok(unwrap(adapters.github.open_pr(repo, branch, diff, description, base_branch)))


@mcp.tool()
def quote_video(prompt: str, aspect: str = "9:16", resolution: str = "1080p") -> dict:
    if aspect not in SUPPORTED_ASPECTS:
        raise ValueError(f"unsupported aspect '{aspect}'; supported: {SUPPORTED_ASPECTS}")
    body = {"prompt": prompt, "aspect": aspect, "resolution": resolution, "audio": False}
    try:
        raw = adapters.transport.post("/quote", body)
    except Exception as exc:
        raise ValueError(f"quote failed: {exc}")
    if not isinstance(raw, dict) or not isinstance(raw.get("est_cost"), float | int):
        raise ValueError("quote: missing or invalid est_cost")
    return {"prompt": prompt, "aspect": aspect, "resolution": resolution, "est_cost": float(raw["est_cost"])}


@mcp.tool()
def render_video(
    prompt: str, aspect: str = "9:16", resolution: str = "1080p", audio: bool = True
) -> dict:
    return ok(unwrap(adapters.video.generate_video(prompt, aspect, resolution, audio)))


# ── entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    from . import tools_ef  # noqa: F401 — register Group E+F tools
    mcp.run()


if __name__ == "__main__":
    main()
