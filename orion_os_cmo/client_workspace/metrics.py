"""Append-only metrics log — the delta engine.

Every weekly run appends rows; nothing here mutates or deletes a past row. Each
row must carry a non-empty ``source`` pointing at the tool call that produced the
value (AGENTS.project: no invented metrics).
"""

from __future__ import annotations

from pathlib import Path

from ..common.result import Err, Ok, Result
from .types import MetricRow, Number

_HEADER = "| date | metric | value | source |\n|------|--------|-------|--------|\n"


class MetricsLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, row: MetricRow) -> Result[None, str]:
        """Append one row. Refuses a row whose source is empty."""
        if not row.source or not row.source.strip():
            return Err("empty_source")
        if not row.metric or not row.metric.strip():
            return Err("empty_metric")
        self._ensure_header()
        line = f"| {row.date} | {row.metric} | {_fmt(row.value)} | {row.source} |\n"
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        return Ok(None)

    def read_all(self) -> Result[list[MetricRow], str]:
        """Parse every data row. An empty/absent log is ``Ok([])``, not an error."""
        if not self.path.exists():
            return Ok([])
        rows: list[MetricRow] = []
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            cells = _cells(raw)
            if cells is None:
                continue
            if cells[:1] == ["date"] or set(cells[0]) <= {"-"}:
                continue  # header / separator
            if len(cells) < 4:
                continue
            rows.append(MetricRow(date=cells[0], metric=cells[1],
                                  value=_num(cells[2]), source=cells[3]))
        return Ok(rows)

    def _ensure_header(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.read_text(encoding="utf-8").strip() == "":
            self.path.write_text(_HEADER, encoding="utf-8")


def _fmt(value: Number) -> str:
    if isinstance(value, bool):  # bool is a subclass of int — keep it explicit
        return str(value)
    if isinstance(value, int):
        return str(value)
    return repr(value)


def _num(text: str) -> Number:
    try:
        if "." not in text and "e" not in text.lower():
            return int(text)
        return float(text)
    except ValueError:
        return 0


def _cells(line: str) -> list[str] | None:
    line = line.strip()
    if not line.startswith("|"):
        return None
    return [c.strip() for c in line.strip("|").split("|")]
