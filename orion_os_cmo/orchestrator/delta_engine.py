"""DeltaEngine — week-over-week deltas from persisted history only.

A delta exists only when the metric has a prior persisted row; a first-ever
metric ships no delta (it is never invented as 0). ``prior`` is always the most
recent persisted value for that metric — provenance, not a guess.
"""

from __future__ import annotations

from ..client_workspace.types import MetricRow
from .types import Delta


def compute_deltas(prior_rows: list[MetricRow], new_rows: list[MetricRow]) -> list[Delta]:
    """Diff each new metric value against the most recent prior row for that metric."""
    latest_prior: dict[str, MetricRow] = {}
    for row in prior_rows:  # rows are append-only chronological; last wins
        latest_prior[row.metric] = row

    deltas: list[Delta] = []
    for new in new_rows:
        prior = latest_prior.get(new.metric)
        if prior is None:
            continue  # no history → no delta (never invented)
        deltas.append(Delta(
            metric=new.metric,
            prior=prior.value,
            current=new.value,
            delta=round(float(new.value) - float(prior.value), 6),
            source=new.source,
        ))
    return deltas
