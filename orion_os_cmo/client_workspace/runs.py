"""Per-run records — one file per weekly pass, write-once.

A weekly run is the unit of work. Its record is immutable once written: a second
write for the same ISO week key is an error, not an overwrite. ``read_last``
returns the lexicographically latest (= most recent) week.
"""

from __future__ import annotations

from pathlib import Path

from ..common.result import Err, Ok, Result
from .types import RunRecord


class RunStore:
    def __init__(self, runs_dir: Path) -> None:
        self.dir = Path(runs_dir)

    def write(self, record: RunRecord) -> Result[None, str]:
        path = self._path(record.week_key)
        if path.exists():
            return Err("duplicate_week")
        self.dir.mkdir(parents=True, exist_ok=True)
        path.write_text(_render(record), encoding="utf-8")
        return Ok(None)

    def read_last(self) -> Result[RunRecord | None, str]:
        if not self.dir.exists():
            return Ok(None)
        files = sorted(p for p in self.dir.glob("*.md") if p.is_file())
        if not files:
            return Ok(None)
        return Ok(_parse(files[-1]))

    def _path(self, week_key: str) -> Path:
        return self.dir / f"{week_key}.md"


def _render(r: RunRecord) -> str:
    agents = "\n".join(f"- {line}" for line in r.per_agent) or "- none"
    return (
        f"# Run {r.week_key} (week of {r.week_of})\n\n"
        f"## Inputs: {r.inputs}\n"
        f"## Per-agent\n{agents}\n"
        f"## Deltas vs last run: {r.deltas}\n"
        f"## Queued for approval: {r.queued_for_approval}\n"
        f"## Published this run: {r.published}\n"
    )


def _parse(path: Path) -> RunRecord:
    week_key = path.stem
    week_of = ""
    inputs = "none"
    per_agent: list[str] = []
    deltas = queued = published = "none"
    in_agents = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# Run ") and "week of " in line:
            week_of = line.split("week of ", 1)[1].rstrip(")").strip()
        elif line.startswith("## Inputs:"):
            inputs = line.split(":", 1)[1].strip()
            in_agents = False
        elif line.startswith("## Per-agent"):
            in_agents = True
        elif line.startswith("## Deltas vs last run:"):
            deltas = line.split(":", 1)[1].strip()
            in_agents = False
        elif line.startswith("## Queued for approval:"):
            queued = line.split(":", 1)[1].strip()
        elif line.startswith("## Published this run:"):
            published = line.split(":", 1)[1].strip()
        elif in_agents and line.startswith("- "):
            entry = line[2:].strip()
            if entry != "none":
                per_agent.append(entry)
    return RunRecord(week_key=week_key, week_of=week_of, inputs=inputs,
                     per_agent=per_agent, deltas=deltas,
                     queued_for_approval=queued, published=published)
