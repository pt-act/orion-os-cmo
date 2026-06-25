"""Canonical paths for the production memory bank.

A single place that knows where every section lives. If the layout shifts, it
shifts here — callers resolve by section name, never by hard-coded path.
Mirrors the tree in ``MEMORY_FORMATS-production.md``.
"""

from __future__ import annotations

from pathlib import Path

# The .gitignore exception that keeps the production bank durable (it is the only
# part of .agents/ that must persist — it powers week-over-week deltas + audit).
GITIGNORE_EXCEPTION = ".agents/\n!.agents/memory_bank-production/\n"

# Directories that make up the bank.
DIRS = ["strategy", "metrics", "runs", "outputs", "approvals", "active"]

# Section name -> path relative to the bank root.
_FILES = {
    "client_context": "CLIENT_CONTEXT.md",
    "config": "config.yml",
    "metrics": "metrics/metrics.md",
    "outputs": "outputs/outputs.md",
    "approvals": "approvals/approvals.md",
    "brand_safety": "BRAND_SAFETY_LOG.md",
    "activity": "active/ACTIVITY.md",
    "current_state": "active/current_state.md",
    "open_decisions": "active/open_decisions.md",
}


class WorkspaceLayout:
    """Resolves section names to absolute paths under a single bank root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def bank(self) -> Path:
        """The memory_bank-production directory itself."""
        return self.root / ".agents" / "memory_bank-production"

    def resolve(self, section: str) -> Path:
        """Absolute path for a named section file."""
        try:
            rel = _FILES[section]
        except KeyError as exc:
            raise KeyError(f"unknown workspace section '{section}'") from exc
        return self.bank / rel

    def dir(self, name: str) -> Path:
        """Absolute path for a named subdirectory."""
        return self.bank / name

    def runs_dir(self) -> Path:
        return self.bank / "runs"

    def strategy_dir(self) -> Path:
        return self.bank / "strategy"
