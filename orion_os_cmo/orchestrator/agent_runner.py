"""AgentRunner — invoke one agent and capture its typed output or a structured error.

An agent failure is never fatal to the pass: it becomes an ``AgentOutcome`` with
an ``error`` string, and the run continues with the remaining agents.
"""

from __future__ import annotations

from typing import Any, Callable

from .types import AgentOutcome


def run_agent(name: str, fn: Callable[[], Any]) -> AgentOutcome:
    """Call ``fn`` (a zero-arg agent invocation returning ``Ok``/``Err``).

    Accepts either a ``Result``-returning callable or one that returns a plain
    value. Any raised exception is captured as a structured error.
    """
    try:
        result = fn()
    except Exception as exc:
        return AgentOutcome(name=name, error=f"exception: {exc}")

    # Result-shaped (has .ok)?
    ok = getattr(result, "ok", None)
    if ok is True:
        return AgentOutcome(name=name, output=getattr(result, "value", result))
    if ok is False:
        err = getattr(result, "error", "agent returned Err")
        message = getattr(err, "message", None) or _err_str(err)
        return AgentOutcome(name=name, error=message)

    # Plain value (e.g. UGCResult) — treat as output.
    return AgentOutcome(name=name, output=result)


def _err_str(err: Any) -> str:
    kind = getattr(err, "kind", None)
    return f"{kind}: {err}" if kind else str(err)
