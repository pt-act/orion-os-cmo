"""GitHub-PR façade — open or update a review-ready PR. Merging is structurally
impossible: the adapter exposes only ``open_pr`` and invokes no merge path.

The transport boundary is post-only (like every other adapter); each GitHub
operation is a semantic path the concrete transport maps to the right REST verb.
The absence of any ``/merge`` path is the irreversibility gate (AGENTS.project:
"a PR is not a merge").
"""

from __future__ import annotations

from typing import Any

from ...common.result import Err, Ok, Result
from .types import ErrorSource, PRError, PRResult, Transport

ENSURE_BRANCH_PATH = "/repos/branch/ensure"
COMMIT_DIFF_PATH = "/repos/commits/apply"
FIND_PR_PATH = "/repos/pulls/find"
CREATE_PR_PATH = "/repos/pulls/create"
UPDATE_PR_PATH = "/repos/pulls/update"


class GitHubPrAdapter:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def open_pr(
        self,
        repo: str,
        branch: str,
        diff: str,
        description: str,
        base_branch: str = "main",
    ) -> Result[PRResult, PRError]:
        if not diff or not diff.strip():
            return Err(PRError("invalid_diff", "diff is empty", _src(repo, branch)))

        ensured = self._post(repo, branch, ENSURE_BRANCH_PATH,
                             {"repo": repo, "branch": branch, "base": base_branch})
        if not ensured.ok:
            return ensured

        committed = self._post(repo, branch, COMMIT_DIFF_PATH,
                              {"repo": repo, "branch": branch, "diff": diff})
        if not committed.ok:
            return committed

        return self._open_or_update_pr(repo, branch, description)

    def _open_or_update_pr(self, repo: str, branch: str, description: str) -> Result[PRResult, PRError]:
        found = self._post(repo, branch, FIND_PR_PATH, {"repo": repo, "branch": branch, "state": "open"})
        if not found.ok:
            return found
        pulls = found.value.get("pulls")
        existing = pulls[0] if isinstance(pulls, list) and pulls else None

        if existing:
            updated = self._post(repo, branch, UPDATE_PR_PATH,
                               {"repo": repo, "branch": branch, "body": description,
                                "number": existing.get("number")})
            if not updated.ok:
                return updated
            url = _s(updated.value.get("pr_url")) or _s(existing.get("pr_url"))
            if not url:
                return Err(PRError("invalid_response", "update returned no pr_url", _src(repo, branch)))
            return Ok(PRResult(pr_url=url, action="updated", branch=branch))

        created = self._post(repo, branch, CREATE_PR_PATH,
                           {"repo": repo, "branch": branch, "body": description})
        if not created.ok:
            return created
        url = _s(created.value.get("pr_url"))
        if not url:
            return Err(PRError("invalid_response", "create returned no pr_url", _src(repo, branch)))
        return Ok(PRResult(pr_url=url, action="created", branch=branch))

    def _post(self, repo: str, branch: str, path: str, body: dict[str, Any]) -> Result[dict, PRError]:
        try:
            raw = self._transport.post(path, body)
        except Exception as exc:
            return Err(PRError("transport", str(exc), _src(repo, branch)))
        if not isinstance(raw, dict):
            return Err(PRError("invalid_response", f"{path} response not an object", _src(repo, branch)))
        err = raw.get("error")
        if err is not None:
            code = err.get("code") if isinstance(err, dict) else None
            if code == 422:
                return Err(PRError("branch_conflict", str(err), _src(repo, branch)))
            return Err(PRError("api_error", str(err), _src(repo, branch)))
        return Ok(raw)


def _src(repo: str, branch: str) -> ErrorSource:
    return ErrorSource(api="github", repo=repo, branch=branch)


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
