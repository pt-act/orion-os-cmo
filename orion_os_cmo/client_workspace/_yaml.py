"""Minimal YAML codec for config.yml — stdlib-only, no third-party dependency.

Scope is deliberately narrow: exactly the shapes the documented ``config.yml``
uses — top-level ``key: scalar``, ``key: [a, b]`` flow lists, and
``key: {a: x, b: y}`` flow maps. It is not a general YAML parser; it is a
glass-box, human-editable, round-tripping serializer for one known schema.
"""

from __future__ import annotations

from typing import Any


def dump(data: dict[str, Any]) -> str:
    return "".join(f"{key}: {_emit(value)}\n" for key, value in data.items())


def load(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = _parse(value.strip())
    return out


def _emit(value: Any) -> str:
    if isinstance(value, dict):
        inner = ", ".join(f"{k}: {_scalar(v)}" for k, v in value.items())
        return "{" + inner + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_scalar(v) for v in value) + "]"
    return _scalar(value)


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "none"
    return str(value)


def _parse(token: str) -> Any:
    if token.startswith("{") and token.endswith("}"):
        body = token[1:-1].strip()
        out: dict[str, Any] = {}
        for part in _split(body):
            k, _, v = part.partition(":")
            out[k.strip()] = _parse(v.strip())
        return out
    if token.startswith("[") and token.endswith("]"):
        body = token[1:-1].strip()
        return [_parse(p.strip()) for p in _split(body)] if body else []
    return _scalar_in(token)


def _scalar_in(token: str) -> Any:
    low = token.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("none", "null", "~", ""):
        return None
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token


def _split(body: str) -> list[str]:
    """Split a flow body on top-level commas (ignoring nested brackets/braces)."""
    parts: list[str] = []
    depth = 0
    cur = ""
    for ch in body:
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur)
    return parts
