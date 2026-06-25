"""Outputs archive with a lifecycle gate.

Status flows ``drafted → approved → published`` or ``drafted → rejected``. The
one hard rule: a row may only reach ``published`` if a matching ``approved``
entry exists in the approval log. The archive never self-approves.
"""

from __future__ import annotations

from pathlib import Path

from ..common.result import Err, Ok, Result
from .approvals import ApprovalLog
from .types import OutputItem, OutputRow, OutputStatus

_HEADER = (
    "| id | date | agent | type | status | provenance | link |\n"
    "|----|------|-------|------|--------|-----------|------|\n"
)

_ADVANCE: dict[OutputStatus, set[OutputStatus]] = {
    "drafted": {"approved", "rejected", "published"},
    "approved": {"published", "rejected"},
    "published": set(),
    "rejected": set(),
}


class OutputArchive:
    def __init__(self, path: Path, approvals: ApprovalLog) -> None:
        self.path = Path(path)
        self._approvals = approvals

    def create(self, item: OutputItem) -> Result[str, str]:
        """Append a new ``drafted`` row; return its assigned ``o-NNN`` id."""
        rows = self._read()
        new_id = f"o-{len(rows) + 1:03d}"
        rows.append(OutputRow(
            id=new_id, date=item.date, agent=item.agent, type=item.type,
            status="drafted", provenance=item.provenance, link=item.link,
        ))
        self._write(rows)
        return Ok(new_id)

    def advance(self, id: str, status: OutputStatus, tool_result: str | None) -> Result[None, str]:
        rows = self._read()
        idx = next((i for i, r in enumerate(rows) if r.id == id), None)
        if idx is None:
            return Err("not_found")

        current = rows[idx].status
        if status not in _ADVANCE.get(current, set()):
            return Err(f"illegal_transition:{current}->{status}")

        if status == "published" and not self._approvals.is_approved(id):
            return Err("no_approval")

        link = rows[idx].link
        if status == "published" and tool_result:
            link = tool_result
        rows[idx] = OutputRow(
            id=rows[idx].id, date=rows[idx].date, agent=rows[idx].agent,
            type=rows[idx].type, status=status, provenance=rows[idx].provenance,
            link=link,
        )
        self._write(rows)
        return Ok(None)

    def read_all(self) -> Result[list[OutputRow], str]:
        return Ok(self._read())

    def can_advance(self, id: str, status: OutputStatus) -> Result[None, str]:
        """Whether ``advance(id, status, ...)`` would be legal *ignoring* the approval
        check — i.e. the output exists and the transition is allowed. Lets a caller
        verify legality before taking an irreversible/ordered side effect (W-1)."""
        row = next((r for r in self._read() if r.id == id), None)
        if row is None:
            return Err("not_found")
        if status not in _ADVANCE.get(row.status, set()):
            return Err(f"illegal_transition:{row.status}->{status}")
        return Ok(None)

    # ── internals ─────────────────────────────────────────────────────────────

    def _read(self) -> list[OutputRow]:
        if not self.path.exists():
            return []
        rows: list[OutputRow] = []
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            cells = _cells(raw)
            if cells is None or len(cells) < 7:
                continue
            if cells[0] == "id" or set(cells[0]) <= {"-"}:
                continue
            rows.append(OutputRow(
                id=cells[0], date=cells[1], agent=cells[2], type=cells[3],
                status=_status(cells[4]), provenance=cells[5], link=cells[6],
            ))
        return rows

    def _write(self, rows: list[OutputRow]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = "".join(
            f"| {r.id} | {r.date} | {r.agent} | {r.type} | {r.status} | {r.provenance} | {r.link} |\n"
            for r in rows
        )
        self.path.write_text(_HEADER + body, encoding="utf-8")


def _status(text: str) -> OutputStatus:
    return text if text in _ADVANCE else "drafted"  # type: ignore[return-value]


def _cells(line: str) -> list[str] | None:
    line = line.strip()
    if not line.startswith("|"):
        return None
    return [c.strip() for c in line.strip("|").split("|")]
