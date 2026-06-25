"""RunCoordinator — drive one weekly CMO pass end to end.

Reads the workspace, invokes each enabled agent (failures are captured, not
fatal), computes deltas from persisted history *before* appending the new rows,
creates draftable outputs, assembles the deterministic brief, and writes the run
record + active files. Publishing stays behind the PublishGate, post-approval.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from ..client_workspace.store import WorkspaceStore
from ..client_workspace.types import MetricRow, OutputItem, RunRecord
from ..common.result import Err, Ok, Result
from .agent_runner import run_agent
from .assembler import assemble_brief, render_markdown, summarize
from .delta_engine import compute_deltas
from .types import AGENT_ORDER, AgentOutcome, ApprovalQueueItem, WeeklyBrief

_log = logging.getLogger(__name__)


def _enum_ugc(output: Any) -> list[str]:
    return [f"{a.aspect} video: {a.brief[:48]}" for a in output.assets]


def _enum_coding(output: Any) -> list[str]:
    return [f"PR {p.pr_url}" for p in output]


def _enum_writer(output: Any) -> list[str]:
    return [f"article: {a.title[:48]}" for a in output]


def _enum_x(output: Any) -> list[str]:
    return [f"{d.kind}: {d.content[:48]}" for d in output]


def _enum_linkedin(output: Any) -> list[str]:
    return [f"post: {d.content[:48]}" for d in output]


def _enum_reddit(output: Any) -> list[str]:
    return [f"reply: {d.thread_url}" for d in output]


def _enum_influencer(output: Any) -> list[str]:
    return [f"outreach: {o.creator.handle}" for o in output]


_ENUMERATORS: dict[str, Any] = {
    "ugc": _enum_ugc,
    "coding": _enum_coding,
    "writer": _enum_writer,
    "x": _enum_x,
    "linkedin": _enum_linkedin,
    "reddit": _enum_reddit,
    "influencer": _enum_influencer,
}

# Agent → (output_type label, how to enumerate draftable items from the output).
_DRAFT_TYPE = {
    "x": "post", "linkedin": "post", "reddit": "reply",
    "writer": "article", "influencer": "outreach", "coding": "pr", "ugc": "video",
}


class RunCoordinator:
    def __init__(
        self,
        workspace: WorkspaceStore,
        agents: dict[str, Callable[[], Any]],
        publish_gate: Any = None,
    ) -> None:
        self._ws = workspace
        self._agents = agents
        self._gate = publish_gate

    def run(self, week_key: str, week_of: str, generated_at: Optional[str] = None) -> Result[WeeklyBrief, str]:
        generated_at = generated_at or datetime.now(timezone.utc).isoformat()

        cfg = self._ws.read_config()
        if not cfg.ok:
            return Err(f"config_unreadable: {cfg.error}")

        prior_metrics = self._ws.read_metrics()
        prior_rows = prior_metrics.value if prior_metrics.ok else []

        # 1) Invoke enabled agents (those provided), in fixed order.
        outcomes: dict[str, AgentOutcome] = {}
        for name in AGENT_ORDER:
            fn = self._agents.get(name)
            if fn is not None:
                outcomes[name] = run_agent(name, fn)

        # 2) Extract + persist new metric rows; compute deltas against history.
        new_rows = _extract_metrics(outcomes, week_key, week_of)
        for row in new_rows:
            self._ws.append_metric(row)
        deltas = compute_deltas(prior_rows, new_rows)

        # 3) Create a draftable output per artifact; build the approval queue.
        draft_records = self._create_outputs(outcomes, week_of)

        # 4) Assemble the deterministic brief.
        brief = assemble_brief(outcomes, deltas, draft_records, week_key, generated_at)

        # 5) Persist the run record + active files (run-end checkpoint).
        self._write_run(brief, outcomes, week_key, week_of)
        self._write_active(brief)
        return Ok(brief)

    # ── persistence helpers ────────────────────────────────────────────────────

    def _create_outputs(self, outcomes: dict[str, AgentOutcome], week_of: str) -> list[ApprovalQueueItem]:
        records: list[ApprovalQueueItem] = []
        for name in AGENT_ORDER:
            outcome = outcomes.get(name)
            if outcome is None or not outcome.ok or outcome.output is None:
                continue
            otype = _DRAFT_TYPE.get(name)
            if otype is None:
                continue  # seo/geo are findings, not draftable artifacts
            for summary in _enumerate_items(name, outcome.output):
                created = self._ws.create_output(OutputItem(
                    date=week_of, agent=name, type=otype, provenance="strategy"))
                if created.ok:
                    records.append(ApprovalQueueItem(
                        item_id=created.value, agent=name, type=otype, summary=summary))
        return records

    def _write_run(self, brief: WeeklyBrief, outcomes: dict[str, AgentOutcome],
                   week_key: str, week_of: str) -> None:
        per_agent: list[str] = []
        for name in AGENT_ORDER:
            outcome = outcomes.get(name)
            if outcome is None:
                per_agent.append(f"{name}: disabled")
            elif not outcome.ok:
                per_agent.append(f"{name}: ERROR {outcome.error}")
            else:
                per_agent.append(f"{name}: {summarize(name, outcome.output)}")
        deltas = "; ".join(f"{d.metric} {d.delta:+}" for d in brief.week_over_week_deltas) or "none"
        self._ws.write_run(RunRecord(
            week_key=week_key, week_of=week_of,
            inputs="strategy_context + metrics history",
            per_agent=per_agent, deltas=deltas,
            queued_for_approval=str(len(brief.approval_queue)),
            published="none",
        ))

    def _write_active(self, brief: WeeklyBrief) -> None:
        layout = self._ws.layout
        n_items = len(brief.prioritized_items)
        n_queue = len(brief.approval_queue)
        layout.resolve("current_state").write_text(
            f"# Current State\n\nRun {brief.week_key}: {n_items} agent outputs, "
            f"{n_queue} awaiting approval.\n\n## Next Run Will\n- re-run enabled agents\n\n"
            f"## Awaiting Operator\n- {n_queue} item(s) in the approval queue\n",
            encoding="utf-8")
        activity = layout.resolve("activity")
        prior = activity.read_text(encoding="utf-8") if activity.exists() else "# Marketing Activity\n"
        moved = "; ".join(f"{d.metric} {d.delta:+}" for d in brief.week_over_week_deltas) or "none"
        activity.write_text(
            prior + f"\n## {brief.week_key}\n- **Did:** {n_items} agent outputs drafted\n"
            f"- **Moved:** {moved}\n- **Pending:** {n_queue} awaiting approval\n- **Next:** review queue\n",
            encoding="utf-8")
        queue = "\n".join(f"- `{q.item_id}` [{q.agent}/{q.type}] {q.summary}" for q in brief.approval_queue)
        layout.resolve("open_decisions").write_text(
            f"# Open Decisions\n\n## {brief.week_key} — approval queue\n"
            f"- **Needs:** approve/reject the items below before publishing\n"
            f"{queue or '- none'}\n", encoding="utf-8")


# ── pure extraction helpers ──────────────────────────────────────────────────

def _extract_metrics(outcomes: dict[str, AgentOutcome], week_key: str, week_of: str) -> list[MetricRow]:
    rows: list[MetricRow] = []
    seo = outcomes.get("seo")
    if seo and seo.ok and seo.output is not None:
        score = getattr(seo.output, "meta", {}).get("audit_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            rows.append(MetricRow(week_of, "seo_score", score, f"tool.seo_audit#{week_key}"))
    geo = outcomes.get("geo")
    if geo and geo.ok and geo.output is not None:
        score = getattr(geo.output, "score", None)
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            rows.append(MetricRow(week_of, "geo_score", score, f"tool.geo_probe#{week_key}"))
    return rows


def _enumerate_items(name: str, output: Any) -> list[str]:
    """One summary string per draftable artifact in an agent output."""
    handler = _ENUMERATORS.get(name)
    if handler is not None:
        try:
            return handler(output)
        except (AttributeError, KeyError, TypeError) as exc:
            _log.warning("coordinator: malformed %s output: %s", name, exc)
    return []


__all__ = ["RunCoordinator", "render_markdown"]
