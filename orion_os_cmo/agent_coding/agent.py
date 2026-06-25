"""agent-coding — turn ranked SEO/GEO findings into one review-ready PR.

Every code change is traceable to the finding that motivated it; a change citing
an unknown finding is dropped, never shipped. The only external write is
``tool.open_pr`` — merging is structurally impossible at the adapter, so nothing
ships to production without the operator's review and merge.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Optional

from ..adapters.github_pr.adapter import GitHubPrAdapter
from ..agent_geo.types import GeoFindings
from ..agent_seo.types import SeoFindings
from ..common.result import Err, Ok, Result
from ..llm.principles import compose
from ..llm.types import LLMClient
from ..strategy_store.store import StrategyStore
from .types import CodeChange, CodingAgentConfig, CodingAgentError, PREntry


class CodingAgent:
    def __init__(
        self,
        strategy_store_path: Path,
        seo_agent_output: Optional[SeoFindings],
        geo_agent_output: Optional[GeoFindings],
        github_pr_adapter: GitHubPrAdapter,
        llm: LLMClient,
        config: Optional[CodingAgentConfig] = None,
    ) -> None:
        self._strategy_path = Path(strategy_store_path)
        self._seo = seo_agent_output
        self._geo = geo_agent_output
        self._pr = github_pr_adapter
        self._llm = llm
        self._config = config or CodingAgentConfig()

    def run(self, repo: str, run_date: Optional[str] = None) -> Result[list[PREntry], CodingAgentError]:
        strategy = StrategyStore(self._strategy_path).load()
        if strategy is None:
            return Err(CodingAgentError("strategy_missing", "no strategy_context at path"))

        seo_fixes = list(self._seo.ranked_fixes) if self._seo else []
        geo_fixes = list(self._geo.fixes) if self._geo else []
        if not seo_fixes and not geo_fixes:
            return Err(CodingAgentError("findings_missing", "no SEO or GEO findings to act on"))

        # The provenance keyset: SEO issue_ids + synthesized geo ids.
        valid_ids = {f.issue_id for f in seo_fixes}
        geo_by_id = {f"geo-{i}": gf for i, gf in enumerate(geo_fixes)}
        valid_ids |= set(geo_by_id)

        cap = self._config.cap_per_source
        try:
            raw = self._llm.complete_json(
                system=_SYSTEM,
                prompt=_build_codegen_prompt(strategy, seo_fixes[:cap], list(geo_by_id.items())[:cap]),
            )
        except Exception as exc:
            return Err(CodingAgentError("llm_error", str(exc)))

        changes = _filter_changes(raw, valid_ids)
        diff = _bundle_diff(changes)
        if not diff.strip():
            return Err(CodingAgentError("findings_missing", "no valid code changes were produced"))

        description = _build_pr_description(changes, seo_fixes, geo_by_id)
        branch = f"orion-cmo/weekly-{run_date or date.today().isoformat()}"

        pr = self._pr.open_pr(repo, branch, diff, description, base_branch=self._config.base_branch)
        if not pr.ok:
            return Err(CodingAgentError("pr_failed", pr.error.message,
                                        extra={"kind": pr.error.kind}))

        entry = PREntry(
            pr_url=pr.value.pr_url,
            branch=pr.value.branch,
            fixes_applied=[CodeChange(c.finding_id, c.file_path, c.change_description) for c in changes],
        )
        violations = validate_pr_entry(entry, valid_ids)
        if violations:
            return Err(CodingAgentError("schema_invalid", "; ".join(violations)))
        return Ok([entry])


# ── pure helpers ─────────────────────────────────────────────────────────────

class _Change:
    __slots__ = ("finding_id", "file_path", "change_description", "diff_fragment")

    def __init__(self, finding_id: str, file_path: str, change_description: str, diff_fragment: str):
        self.finding_id = finding_id
        self.file_path = file_path
        self.change_description = change_description
        self.diff_fragment = diff_fragment


def _filter_changes(raw: Any, valid_ids: set[str]) -> list[_Change]:
    out: list[_Change] = []
    items = raw.get("changes") if isinstance(raw, dict) else None
    for item in items or []:
        if not isinstance(item, dict):
            continue
        fid = item.get("finding_id")
        if not isinstance(fid, str) or fid not in valid_ids:
            continue  # fabricated finding_id — dropped, never shipped
        frag = _s(item.get("diff_fragment"))
        if not frag.strip():
            continue
        out.append(_Change(fid, _s(item.get("file_path")), _s(item.get("change_description")), frag))
    return out


def _bundle_diff(changes: list[_Change]) -> str:
    return "\n".join(c.diff_fragment.rstrip("\n") for c in changes) + ("\n" if changes else "")


def _build_pr_description(changes: list[_Change], seo_fixes, geo_by_id) -> str:
    lines = ["## Orion-CMO weekly fixes", "",
             "Each change below is traceable to the SEO/GEO finding that motivated it.", ""]
    for c in changes:
        lines.append(f"- **{c.finding_id}** · `{c.file_path}` — {c.change_description}")
    lines += ["", "_This PR is for review. Nothing merges without operator approval._"]
    return "\n".join(lines)


def validate_pr_entry(entry: PREntry, valid_ids: set[str]) -> list[str]:
    v: list[str] = []
    if not entry.pr_url:
        v.append("pr_url empty")
    for i, c in enumerate(entry.fixes_applied):
        if c.finding_id not in valid_ids:
            v.append(f"fixes_applied[{i}].finding_id not traceable")
    return v


def _build_codegen_prompt(strategy: dict, seo_fixes, geo_items) -> str:
    lines = ["Generate minimal code changes for these findings. Reference each by its exact id.", ""]
    if seo_fixes:
        lines.append("SEO findings:")
        for f in seo_fixes:
            lines.append(f"- {f.issue_id} [{f.severity}] {f.issue}: {f.fix}")
    if geo_items:
        lines.append("GEO findings (JSON-LD / schema work):")
        for gid, gf in geo_items:
            lines.append(f"- {gid} [{gf.fix_type}] {gf.fix}")
    lines += [
        "",
        'Return JSON: { "changes": [{ "finding_id", "file_path", "change_description", '
        '"diff_fragment" (unified diff) }] } — use only the finding ids listed above.',
    ]
    return "\n".join(lines)


_ROLE = (
    "Your role: a senior engineer translating ranked SEO/GEO findings into the smallest correct "
    "change for each. You are given findings, each with an exact id; produce a minimal unified "
    "diff per finding and reference it by that id — never invent a finding or touch code "
    "unrelated to one. Your output is a single pull request for the operator to review. "
    "Prefer the least invasive change that resolves the finding."
)

_SYSTEM = compose(_ROLE)


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
