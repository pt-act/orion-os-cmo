"""WorkspaceStore — the typed read/write API over the production memory bank.

One durable store per client. Composes the section stores (strategy, metrics,
outputs, approvals, runs, config) and the StrategyStore hash-baseline so operator
edits survive refreshes. Every method returns a structured ``Ok``/``Err`` — a
caller never gets a silent empty.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..common.result import Err, Ok, Result
from ..strategy_store.context import StrategyContext
from ..strategy_store.store import RefreshDiff, StrategyStore
from . import _yaml
from .approvals import ApprovalLog
from .layout import DIRS, GITIGNORE_EXCEPTION, WorkspaceLayout
from .metrics import MetricsLog
from .outputs import OutputArchive
from .runs import RunStore
from .types import ApprovalEntry, MetricRow, OutputItem, OutputStatus, RunRecord

_DEFAULT_CONFIG: dict[str, Any] = {
    "client": "none",
    "cadence": "weekly",
    "run_day": "monday",
    "agents_enabled": ["seo", "geo", "reddit", "x", "linkedin", "writer", "coding", "influencer", "ugc"],
    "connected_accounts": {"x": False, "linkedin": False, "cms": "none", "github": "none", "ga4": False, "gsc": False},
    "approval_policy": "human-gate-all",
    "metering": {"video_clips_max_per_run": 2, "paid_calls_budget_usd": 0},
}

# Stub files written on init (path-key -> initial body). `none` for empty fields.
_STUBS: dict[str, str] = {
    "client_context": (
        "# [Client Name] — CMO Context\n\n"
        "## Status: onboarding\n## URL: none\n## Cadence: weekly\n"
        "## Positioning (1-line): none\n## Active Agents: none\n"
        "## Connected Accounts: none\n## Latest Scores: none\n"
        "## Standing Constraints: none\n"
    ),
    "brand_safety": "# Brand Safety Log\n\n_No held drafts yet._\n",
    "activity": "# Marketing Activity\n\n_No runs yet._\n",
    "current_state": (
        "# Current State\n\nNot yet run.\n\n"
        "## Next Run Will\n- none\n\n## Awaiting Operator\n- none\n"
    ),
    "open_decisions": "# Open Decisions\n\n_None open._\n",
    "approvals": "# Approvals\n\n",
}


class WorkspaceStore:
    """The per-client durable operational store."""

    def __init__(self, root: Path) -> None:
        self.layout = WorkspaceLayout(root)
        bank = self.layout.bank
        self._strategy = StrategyStore(bank)
        self._metrics = MetricsLog(self.layout.resolve("metrics"))
        self._approvals = ApprovalLog(self.layout.resolve("approvals"))
        self._outputs = OutputArchive(self.layout.resolve("outputs"), self._approvals)
        self._runs = RunStore(self.layout.runs_dir())

    # ── init ──────────────────────────────────────────────────────────────────

    @classmethod
    def init(cls, root: Path) -> Result["WorkspaceStore", str]:
        """Materialize the bank under ``root``; idempotent (writes only what's missing)."""
        store = cls(root)
        try:
            for name in DIRS:
                store.layout.dir(name).mkdir(parents=True, exist_ok=True)
            for key, body in _STUBS.items():
                path = store.layout.resolve(key)
                if not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(body, encoding="utf-8")
            store._metrics._ensure_header()
            if not store.layout.resolve("outputs").exists():
                store._outputs._write([])
            cfg_path = store.layout.resolve("config")
            if not cfg_path.exists():
                cfg_path.write_text(_yaml.dump(_DEFAULT_CONFIG), encoding="utf-8")
            store._write_gitignore_exception()
        except OSError as exc:
            return Err(f"init_failed:{exc}")
        return Ok(store)

    def _write_gitignore_exception(self) -> None:
        gi = self.layout.root / ".gitignore"
        existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
        if "!.agents/memory_bank-production/" in existing:
            return
        sep = "" if existing == "" or existing.endswith("\n") else "\n"
        gi.write_text(existing + sep + GITIGNORE_EXCEPTION, encoding="utf-8")

    # ── strategy (hash-baseline, edit-preserving) ──────────────────────────────

    def write_strategy(self, ctx: StrategyContext) -> Result[RefreshDiff, str]:
        return Ok(self._strategy.write(ctx))

    def refresh_strategy(self, ctx: StrategyContext) -> Result[RefreshDiff, str]:
        return Ok(self._strategy.refresh(ctx))

    def read_strategy(self) -> Result[dict, str]:
        loaded = self._strategy.load()
        if loaded is None:
            return Err("not_built")
        return Ok(loaded)

    # ── metrics (append-only) ──────────────────────────────────────────────────

    def append_metric(self, row: MetricRow) -> Result[None, str]:
        return self._metrics.append(row)

    def read_metrics(self) -> Result[list[MetricRow], str]:
        return self._metrics.read_all()

    # ── runs (write-once) ──────────────────────────────────────────────────────

    def write_run(self, record: RunRecord) -> Result[None, str]:
        return self._runs.write(record)

    def read_last_run(self) -> Result[Optional[RunRecord], str]:
        return self._runs.read_last()

    # ── outputs + approvals (lifecycle-gated) ──────────────────────────────────

    def create_output(self, item: OutputItem) -> Result[str, str]:
        return self._outputs.create(item)

    def advance_output(self, id: str, status: OutputStatus,
                       tool_result: str | None) -> Result[None, str]:
        return self._outputs.advance(id, status, tool_result)

    def can_advance_output(self, id: str, status: OutputStatus) -> Result[None, str]:
        """Legality check for an advance (existence + allowed transition), excluding
        the approval gate — used to order side effects safely (see PublishGate)."""
        return self._outputs.can_advance(id, status)

    def read_outputs(self) -> Result[list, str]:
        return self._outputs.read_all()

    def read_approvals(self) -> Result[list[ApprovalEntry], str]:
        try:
            return Ok(self._approvals._read())
        except Exception as exc:
            return Err(str(exc))

    def append_approval(self, entry: ApprovalEntry) -> Result[None, str]:
        return self._approvals.append(entry)

    # ── config (read/write) ────────────────────────────────────────────────────

    def read_config(self) -> Result[dict, str]:
        path = self.layout.resolve("config")
        if not path.exists():
            return Err("no_config")
        return Ok(_yaml.load(path.read_text(encoding="utf-8")))

    def write_config(self, cfg: dict) -> Result[None, str]:
        path = self.layout.resolve("config")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_yaml.dump(cfg), encoding="utf-8")
        return Ok(None)
