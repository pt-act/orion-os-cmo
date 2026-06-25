"""Append-only human-decision log — audit trail + liability shield.

The model never self-approves. Publishing checks this log for a matching
``approved`` entry before an output may advance to ``published``.
"""

from __future__ import annotations

from pathlib import Path

from ..common.result import Err, Ok, Result
from .types import ApprovalEntry


class ApprovalLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, entry: ApprovalEntry) -> Result[None, str]:
        if not entry.output_id.strip():
            return Err("empty_output_id")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        block = (
            f"## [{entry.date}] {entry.output_id}\n"
            f"- **Decision:** {entry.decision}\n"
            f"- **By:** {entry.by}\n"
            f"- **Note:** {entry.note}\n"
            f"- **Tool result:** {entry.tool_result}\n\n"
        )
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(block)
        return Ok(None)

    def is_approved(self, output_id: str) -> bool:
        """True iff an ``approved`` decision exists for this output id."""
        for entry in self._read():
            if entry.output_id == output_id and entry.decision == "approved":
                return True
        return False

    def _read(self) -> list[ApprovalEntry]:
        if not self.path.exists():
            return []
        entries: list[ApprovalEntry] = []
        cur: dict[str, str] = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                if cur:
                    entries.append(_to_entry(cur))
                cur = _parse_header(line)
            elif line.startswith("- **") and cur:
                key, _, val = line[len("- **"):].partition(":**")
                cur[key.strip().lower()] = val.strip()
        if cur:
            entries.append(_to_entry(cur))
        return entries


def _parse_header(line: str) -> dict[str, str]:
    # "## [date] output_id — label"
    body = line[3:].strip()
    date = ""
    if body.startswith("[") and "]" in body:
        date = body[1:body.index("]")]
        body = body[body.index("]") + 1:].strip()
    output_id = body.split(" ", 1)[0].split("—", 1)[0].strip()
    return {"_started": "1", "date": date, "output_id": output_id}


def _to_entry(cur: dict[str, str]) -> ApprovalEntry:
    decision = cur.get("decision", "rejected")
    decision = "approved" if decision == "approved" else "rejected"
    return ApprovalEntry(
        output_id=cur.get("output_id", ""),
        decision=decision,  # type: ignore[arg-type]
        by=cur.get("by", "none"),
        note=cur.get("note", "none"),
        tool_result=cur.get("tool result", "none"),
        date=cur.get("date", ""),
    )
