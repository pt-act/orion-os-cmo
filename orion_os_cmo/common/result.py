"""Shared structured-result type (H-2).

A discriminated ``Ok``/``Err`` union used across adapters and agents so failures
are always explicit, typed values — never exceptions thrown across a boundary or
silent empties.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T
    ok: Literal[True] = True


@dataclass(frozen=True)
class Err(Generic[E]):
    error: E
    ok: Literal[False] = False


Result = Union[Ok[T], Err[E]]
