"""PublishGate — the only path to the irreversible publish tools.

No approval token, no call: a publish attempted without a token returns
``no_approval_token`` and the tool is never invoked. On success it records the
approval entry *before* advancing the output to ``published`` — so the workspace
publish gate (which requires an approval entry) is satisfied by construction.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from ..client_workspace.store import WorkspaceStore
from ..client_workspace.types import ApprovalEntry
from ..common.result import Err, Ok, Result


class PublishGate:
    def __init__(
        self,
        workspace: WorkspaceStore,
        post_adapter: Any = None,
        article_adapter: Any = None,
        operator: str = "operator",
    ) -> None:
        self._ws = workspace
        self._post = post_adapter
        self._article = article_adapter
        self._operator = operator

    def publish_post(
        self, item_id: str, platform: str, content: str, approval_token: Optional[str]
    ) -> Result[str, str]:
        if not approval_token or not str(approval_token).strip():
            return Err("no_approval_token")
        if self._post is None:
            return Err("no_post_adapter")
        # W-1: confirm the output can legally publish BEFORE the irreversible post,
        # so we never fire a brand-visible action we cannot then record.
        legal = self._ws.can_advance_output(item_id, "published")
        if not legal.ok:
            return Err(legal.error)
        result = self._post.publish_post(platform, content, approval_token)
        if not result.ok:
            return Err(result.error.kind)
        return self._record(item_id, "X post", result.value.url)

    def publish_article(
        self, item_id: str, cms: str, article: Mapping[str, Any], approval_token: Optional[str]
    ) -> Result[str, str]:
        if not approval_token or not str(approval_token).strip():
            return Err("no_approval_token")
        if self._article is None:
            return Err("no_article_adapter")
        legal = self._ws.can_advance_output(item_id, "published")  # W-1, see publish_post
        if not legal.ok:
            return Err(legal.error)
        result = self._article.publish_article(cms, article, approval_token)
        if not result.ok:
            return Err(result.error.kind)
        return self._record(item_id, "article", result.value.url)

    def _record(self, item_id: str, label: str, url: str) -> Result[str, str]:
        # W-1: verify the advance is legal (output exists, transition allowed) BEFORE
        # writing the approval. The workspace publish gate requires an approval entry to
        # exist, so the approval must precede the advance — but if the transition were
        # illegal we would otherwise orphan an "approved" record with no published output.
        # Guarding first means the approval is persisted only when the advance will succeed.
        legal = self._ws.can_advance_output(item_id, "published")
        if not legal.ok:
            return Err(legal.error)
        self._ws.append_approval(ApprovalEntry(
            output_id=item_id, decision="approved", by=self._operator,
            note=f"published {label}", tool_result=url, date=date.today().isoformat(),
        ))
        advanced = self._ws.advance_output(item_id, "published", url)
        if not advanced.ok:
            return Err(advanced.error)
        return Ok(url)
