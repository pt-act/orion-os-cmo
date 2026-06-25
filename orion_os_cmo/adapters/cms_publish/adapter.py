"""CMS-publish façade — the irreversible, human-gated write surface.

The approval gate is absolute and checked first: with no token, the adapter
returns ``approval_required`` and touches no transport. This is the boundary the
whole system's "never auto-publish" guarantee rests on (AGENTS.project hard rule).
Re-publishing the same slug updates in place — never a duplicate.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from ...common.result import Err, Ok, Result
from .types import (
    SUPPORTED_CMS,
    PublishError,
    PublishErrorSource,
    PublishResult,
    Transport,
)

CHECK_PATH = "/api/cms/slug/check"
CREATE_PATH = "/api/cms/article/create"
UPDATE_PATH = "/api/cms/article/update"


class CmsPublishAdapter:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def publish_article(
        self,
        cms: str,
        article: Mapping[str, Any],
        approval_token: Optional[str],
    ) -> Result[PublishResult, PublishError]:
        slug = _s(article.get("slug"))
        src = PublishErrorSource(cms=cms, slug=slug)

        # Gate first — before any routing or network call.
        if not approval_token or not str(approval_token).strip():
            return Err(PublishError("approval_required", "missing approval token", src))
        if cms not in SUPPORTED_CMS:
            return Err(PublishError("unsupported_cms", f"unsupported cms '{cms}'", src))
        if not slug:
            return Err(PublishError("cms_error", "article has no slug", src))

        check = self._post(cms, slug, CHECK_PATH,
                           {"cms": cms, "slug": slug, "approval_token": approval_token})
        if not check.ok:
            return check
        exists = bool(check.value.get("exists"))
        existing_id = check.value.get("existing_id")

        if exists:
            res = self._post(cms, slug, UPDATE_PATH,
                            {"cms": cms, "id": existing_id, "article": dict(article),
                             "approval_token": approval_token})
        else:
            res = self._post(cms, slug, CREATE_PATH,
                            {"cms": cms, "article": dict(article), "approval_token": approval_token})
        if not res.ok:
            return res

        url = _s(res.value.get("url"))
        if not url:
            return Err(PublishError("cms_error", "CMS returned no url", src))
        return Ok(PublishResult(url=url))

    def _post(self, cms: str, slug: str, path: str, body: dict[str, Any]) -> Result[dict, PublishError]:
        try:
            raw = self._transport.post(path, body)
        except Exception as exc:
            return Err(PublishError("transport", str(exc), PublishErrorSource(cms, slug)))
        if not isinstance(raw, dict):
            return Err(PublishError("cms_error", f"{path} response not an object",
                                    PublishErrorSource(cms, slug)))
        if raw.get("error") is not None:
            return Err(PublishError("cms_error", str(raw["error"]), PublishErrorSource(cms, slug)))
        return Ok(raw)


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
