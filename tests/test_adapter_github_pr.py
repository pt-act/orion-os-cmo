"""adapter-github-pr — focused + PBT tests (idempotency, no-merge gate)."""

import unittest

from orion_os_cmo.adapters.github_pr import GitHubPrAdapter
from orion_os_cmo.adapters.github_pr.adapter import (
    CREATE_PR_PATH,
    ENSURE_BRANCH_PATH,
    FIND_PR_PATH,
    UPDATE_PR_PATH,
)


class FakeGitHub:
    """Stateful mock: tracks branches + one PR per branch, records every path."""

    def __init__(self, fail=None):
        self.branches = set()
        self.prs = {}            # branch -> {number, pr_url}
        self.calls = []
        self.fail = fail or {}   # path -> error envelope

    def post(self, path, body):
        self.calls.append((path, body))
        if path in self.fail:
            if self.fail[path] == "raise":
                raise RuntimeError("network down")
            return {"error": self.fail[path]}
        branch = body.get("branch")
        if path == ENSURE_BRANCH_PATH:
            created = branch not in self.branches
            self.branches.add(branch)
            return {"branch": branch, "created": created}
        if path == FIND_PR_PATH:
            pr = self.prs.get(branch)
            return {"pulls": [pr] if pr else []}
        if path == CREATE_PR_PATH:
            number = len(self.prs) + 1
            pr = {"number": number, "pr_url": f"https://github.com/acme/repo/pull/{number}"}
            self.prs[branch] = pr
            return pr
        if path == UPDATE_PR_PATH:
            return {"pr_url": self.prs[branch]["pr_url"]}
        return {}


DIFF = "--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n"


class GitHubPr(unittest.TestCase):
    def test_created(self):
        gh = FakeGitHub()
        res = GitHubPrAdapter(gh).open_pr("acme/repo", "orion-cmo/weekly-2026-06-20", DIFF, "desc")
        self.assertTrue(res.ok, res)
        self.assertEqual(res.value.action, "created")
        self.assertTrue(res.value.pr_url.endswith("/pull/1"))

    def test_updated_idempotent(self):
        gh = FakeGitHub()
        adapter = GitHubPrAdapter(gh)
        first = adapter.open_pr("acme/repo", "b1", DIFF, "v1")
        second = adapter.open_pr("acme/repo", "b1", DIFF, "v2")
        self.assertEqual(first.value.action, "created")
        self.assertEqual(second.value.action, "updated")
        self.assertEqual(first.value.pr_url, second.value.pr_url)
        self.assertEqual(len(gh.prs), 1)  # exactly one PR

    def test_transport_failure(self):
        gh = FakeGitHub(fail={ENSURE_BRANCH_PATH: "raise"})
        res = GitHubPrAdapter(gh).open_pr("acme/repo", "b1", DIFF, "d")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "transport")

    def test_branch_conflict(self):
        gh = FakeGitHub(fail={ENSURE_BRANCH_PATH: {"code": 422, "message": "conflict"}})
        res = GitHubPrAdapter(gh).open_pr("acme/repo", "b1", DIFF, "d")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "branch_conflict")

    def test_empty_diff(self):
        res = GitHubPrAdapter(FakeGitHub()).open_pr("acme/repo", "b1", "   ", "d")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "invalid_diff")

    def test_pbt_idempotency_one_pr(self):
        gh = FakeGitHub()
        adapter = GitHubPrAdapter(gh)
        actions = [adapter.open_pr("acme/repo", "b1", DIFF, f"v{i}").value.action for i in range(5)]
        self.assertEqual(actions[0], "created")
        self.assertTrue(all(a == "updated" for a in actions[1:]))
        self.assertEqual(len(gh.prs), 1)

    def test_pbt_never_merges(self):
        gh = FakeGitHub()
        adapter = GitHubPrAdapter(gh)
        for i in range(3):
            adapter.open_pr("acme/repo", "b1", DIFF, f"v{i}")
        for path, _ in gh.calls:
            self.assertNotIn("merge", path.lower())


if __name__ == "__main__":
    unittest.main()
