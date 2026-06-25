"""strategy-store Group 3 — persist the strategy_context as hand-editable,
versioned files, with a refresh that preserves operator edits.

Each section is one JSON file. `_meta.json` records the version and the hash of
what the system last wrote per section. On refresh, if a section's on-disk hash
differs from the stored hash the operator has edited it — so it is preserved
("kept") rather than overwritten. This is the edit-preservation invariant.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from .context import StrategyContext

SECTIONS = ["brand_voice", "icp", "competitors", "positioning", "growth_playbook"]

SectionStatus = Literal["added", "updated", "unchanged", "kept"]


@dataclass(frozen=True)
class SectionDiff:
    section: str
    status: SectionStatus  # "kept" == operator edit preserved


@dataclass(frozen=True)
class RefreshDiff:
    version: int
    sections: list[SectionDiff]


class StrategyStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.dir = self.root / "strategy"
        self.meta_path = self.dir / "_meta.json"

    # ── public API ───────────────────────────────────────────────────────────

    def write(self, ctx: StrategyContext) -> RefreshDiff:
        """Initial build — write every section from scratch."""
        self.dir.mkdir(parents=True, exist_ok=True)
        hashes: dict[str, str] = {}
        for name, data in _sections(ctx).items():
            canon = _canon(data)
            self._section_path(name).write_text(canon, encoding="utf-8")
            hashes[name] = _hash(canon)
        self._write_meta(ctx.meta.version, ctx.meta.source_run, hashes)
        return RefreshDiff(ctx.meta.version, [SectionDiff(n, "added") for n in SECTIONS])

    def refresh(self, ctx: StrategyContext) -> RefreshDiff:
        """Re-synthesize: update system-owned sections, preserve operator edits."""
        if not self.meta_path.exists():
            return self.write(ctx)

        old_meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        old_hashes: dict[str, str] = old_meta.get("hashes", {})
        old_version = int(old_meta.get("version", 0))

        new_sections = _sections(ctx)
        new_hashes = dict(old_hashes)
        diffs: list[SectionDiff] = []
        changed = False

        for name in SECTIONS:
            path = self._section_path(name)
            new_canon = _canon(new_sections[name])
            new_hash = _hash(new_canon)

            if not path.exists():
                path.write_text(new_canon, encoding="utf-8")
                new_hashes[name] = new_hash
                diffs.append(SectionDiff(name, "added"))
                changed = True
                continue

            current_hash = _hash(path.read_text(encoding="utf-8"))
            stored_hash = old_hashes.get(name)

            if stored_hash is not None and current_hash != stored_hash:
                # Operator edited this section — preserve it, keep the baseline
                # hash so future refreshes keep preserving until they revert.
                diffs.append(SectionDiff(name, "kept"))
                continue

            if new_hash != current_hash:
                path.write_text(new_canon, encoding="utf-8")
                new_hashes[name] = new_hash
                diffs.append(SectionDiff(name, "updated"))
                changed = True
            else:
                diffs.append(SectionDiff(name, "unchanged"))

        new_version = old_version + 1 if changed else old_version
        self._write_meta(new_version, ctx.meta.source_run, new_hashes)
        return RefreshDiff(new_version, diffs)

    def load(self) -> Optional[dict[str, Any]]:
        """Read the stored context back, or None if nothing is built yet."""
        if not self.meta_path.exists():
            return None
        meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        sections: dict[str, Any] = {}
        for name in SECTIONS:
            path = self._section_path(name)
            if path.exists():
                sections[name] = json.loads(path.read_text(encoding="utf-8"))
        return {"meta": meta, "sections": sections}

    # ── internals ─────────────────────────────────────────────────────────────

    def _section_path(self, name: str) -> Path:
        return self.dir / f"{name}.json"

    def _write_meta(self, version: int, source_run: str, hashes: dict[str, str]) -> None:
        meta = {
            "version": version,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "source_run": source_run,
            "hashes": hashes,
        }
        self.meta_path.write_text(_canon(meta), encoding="utf-8")


def _sections(ctx: StrategyContext) -> dict[str, Any]:
    full = asdict(ctx)
    return {name: full[name] for name in SECTIONS}


def _canon(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
