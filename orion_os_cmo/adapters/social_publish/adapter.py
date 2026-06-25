"""Social-publish façade — the single gated, irreversible posting primitive.

Two absolutes, both checked before any network call:
  1. No valid approval token → ``no_approval``; the transport is never touched.
  2. An item already posted (by content hash) → ``already_posted``; no second call.
Together they make double-posting and un-approved posting structurally impossible.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Mapping, Optional

from ...common.result import Err, Ok, Result
from .types import PLATFORMS, ErrorSource, PostResult, PublishError, Transport

POST_PATH = "/api/social/post"


class ApprovalValidator:
    """v1: validate against an optional expected token. Pluggable for signed tokens."""

    def __init__(self, expected_token: Optional[str] = None) -> None:
        self._expected = expected_token

    def is_valid(self, token: Optional[str]) -> bool:
        if not token or not str(token).strip():
            return False
        if self._expected is not None:
            return hmac.compare_digest(token, self._expected)
        return True


class IdempotencyStore:
    """v1: in-process posted-item set. Interface-abstracted for a future durable store."""

    def __init__(self) -> None:
        self._posted: set[str] = set()

    def has(self, item_id: str) -> bool:
        return item_id in self._posted

    def add(self, item_id: str) -> None:
        self._posted.add(item_id)


class SocialPublishAdapter:
    def __init__(
        self,
        transports: Mapping[str, Transport],
        approval: Optional[ApprovalValidator] = None,
        idempotency: Optional[IdempotencyStore] = None,
    ) -> None:
        self._transports = dict(transports)
        self._approval = approval or ApprovalValidator()
        self._idem = idempotency or IdempotencyStore()

    def publish_post(
        self, platform: str, content: str, approval_token: Optional[str]
    ) -> Result[PostResult, PublishError]:
        item_id = _item_id(platform, content)
        src = ErrorSource(platform=platform, item_id=item_id)

        # Gate 1: approval, before anything else.
        if not self._approval.is_valid(approval_token):
            return Err(PublishError("no_approval", "missing or invalid approval token", src))
        # Gate 2: idempotency.
        if self._idem.has(item_id):
            return Err(PublishError("already_posted", "item already posted", src))
        # Platform dispatch.
        if platform not in PLATFORMS or platform not in self._transports:
            return Err(PublishError("unsupported_platform", f"unsupported platform '{platform}'", src))

        transport = self._transports[platform]
        try:
            raw = transport.post(POST_PATH, {"platform": platform, "content": content,
                                             "approval_token": approval_token})
        except Exception as exc:
            return Err(PublishError("transport", str(exc), src))

        if not isinstance(raw, dict):
            return Err(PublishError("invalid_response", "response not an object", src))
        if raw.get("error") is not None:
            return Err(PublishError("api_error", str(raw["error"]), src))
        url = _s(raw.get("url"))
        post_id = _s(raw.get("id"))
        if not url or not post_id:
            return Err(PublishError("invalid_response", "missing url/id", src))

        self._idem.add(item_id)  # mark posted only after a confirmed success
        return Ok(PostResult(url=url, id=post_id))


def _item_id(platform: str, content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    return f"{platform}:{digest}"


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
