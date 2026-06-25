"""Shared server state: adapters, workspace, LLM, and small helpers.

Separated from ``server.py`` so that ``tools_ef.py`` can import the same
singletons without creating circular imports.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any, cast

from ..adapters.analytics_ingest.adapter import AnalyticsAdapter
from ..adapters.crawl.adapter import CrawlAdapter
from ..adapters.creator_discovery.adapter import CreatorDiscoveryAdapter
from ..adapters.geo_probe.adapter import GeoProbeAdapter
from ..adapters.github_pr.adapter import GitHubPrAdapter
from ..adapters.reddit_listen.adapter import RedditAdapter
from ..adapters.seo_audit.adapter import SeoAuditAdapter
from ..adapters.video_gen.adapter import VideoGenAdapter
from ..client_workspace.store import WorkspaceStore
from ..transports.config import TransportConfig
from ..transports.self_hosted import SelfHostedTransport


class _Adapters:
    def __init__(self) -> None:
        self._transport: SelfHostedTransport | None = None
        self._seo: SeoAuditAdapter | None = None
        self._analytics: AnalyticsAdapter | None = None
        self._geo: GeoProbeAdapter | None = None
        self._crawl: CrawlAdapter | None = None
        self._reddit: RedditAdapter | None = None
        self._creators: CreatorDiscoveryAdapter | None = None
        self._github: GitHubPrAdapter | None = None
        self._video: VideoGenAdapter | None = None

    @property
    def transport(self) -> SelfHostedTransport:
        if self._transport is None:
            self._transport = SelfHostedTransport(TransportConfig.from_env())
        return self._transport

    @property
    def seo(self) -> SeoAuditAdapter:
        if self._seo is None:
            self._seo = SeoAuditAdapter(self.transport)
        return self._seo

    @property
    def analytics(self) -> AnalyticsAdapter:
        if self._analytics is None:
            self._analytics = AnalyticsAdapter(self.transport)
        return self._analytics

    @property
    def geo(self) -> GeoProbeAdapter:
        if self._geo is None:
            self._geo = GeoProbeAdapter(self.transport)
        return self._geo

    @property
    def crawl(self) -> CrawlAdapter:
        if self._crawl is None:
            self._crawl = CrawlAdapter(self.transport)
        return self._crawl

    @property
    def reddit(self) -> RedditAdapter:
        if self._reddit is None:
            self._reddit = RedditAdapter(self.transport)
        return self._reddit

    @property
    def creators(self) -> CreatorDiscoveryAdapter:
        if self._creators is None:
            self._creators = CreatorDiscoveryAdapter(self.transport)
        return self._creators

    @property
    def github(self) -> GitHubPrAdapter:
        if self._github is None:
            self._github = GitHubPrAdapter(self.transport)
        return self._github

    @property
    def video(self) -> VideoGenAdapter:
        if self._video is None:
            cap = float(os.environ.get("CMO_VIDEO_CAP", "50"))
            self._video = VideoGenAdapter(self.transport, per_run_cap=cap)
        return self._video


adapters = _Adapters()


def ws() -> WorkspaceStore:
    root = os.environ.get("CMO_WORKSPACE_ROOT", ".agents/memory_bank-production/")
    return WorkspaceStore(Path(root))


def strategy_path() -> Path:
    return ws().layout.bank


def llm() -> Any:
    from ..llm.config import LLMConfig
    from ..llm.http_client import HttpLLMClient
    return HttpLLMClient(LLMConfig.from_env())


def ok(value: Any) -> dict:
    if isinstance(value, list):
        return {"data": [dataclasses.asdict(v) for v in value]}
    if dataclasses.is_dataclass(type(value)):
        return dataclasses.asdict(value)
    if isinstance(value, dict):
        return cast(dict, value)
    return cast(dict, value)


def unwrap(result: Any) -> Any:
    if not result.ok:
        raise ValueError(str(result.error))
    return result.value
