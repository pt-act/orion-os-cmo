"""Creator-discovery façade — typed Creator[] with audience-fit provenance.

The grounding rule: ``audience_fit`` is set only from a real demographics lookup,
and ``source.demographics`` records which tool produced it. If the lookup fails,
``audience_fit`` is ``None`` — never synthesized. Email enrichment is best-effort.
"""

from __future__ import annotations

from typing import Any, Optional

from ...common.result import Err, Ok, Result
from .types import (
    Creator,
    CreatorDiscoveryError,
    CreatorSource,
    DiscoveryErrorSource,
    PLATFORMS,
    Transport,
)

SEARCH_PATH = "/api/creators/search"
EMAIL_PATH = "/api/creators/email"
DEMOGRAPHICS_PATH = "/api/creators/demographics"

_SEARCH_TOOL = "stablesocial/creator_search"
_EMAIL_TOOL = "creatorfinder/email"
_DEMO_TOOL = "audience/demographics"


class CreatorDiscoveryAdapter:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def discover_creators(
        self, niche: str, platform: str, follower_tier: str
    ) -> Result[list[Creator], CreatorDiscoveryError]:
        src = DiscoveryErrorSource(provider=_SEARCH_TOOL, niche=niche, platform=platform)
        if platform not in PLATFORMS:
            return Err(CreatorDiscoveryError("invalid_response", f"unsupported platform '{platform}'", src))

        try:
            raw = self._transport.post(SEARCH_PATH,
                                       {"niche": niche, "platform": platform, "follower_tier": follower_tier})
        except Exception as exc:
            return Err(CreatorDiscoveryError("transport", str(exc), src))
        if not isinstance(raw, dict) or not isinstance(raw.get("creators"), list):
            return Err(CreatorDiscoveryError("invalid_response", "missing creators[]", src))

        creators: list[Creator] = []
        for item in raw["creators"]:
            creator = self._normalize(item)
            if creator is not None:
                creators.append(creator)
        if not creators:
            return Err(CreatorDiscoveryError("empty_result", "no creators matched", src))
        return Ok(creators)

    def _normalize(self, item: Any) -> Optional[Creator]:
        if not isinstance(item, dict):
            return None
        handle = _s(item.get("handle"))
        url = _s(item.get("url"))
        followers = item.get("followers")
        if not handle or not url or not isinstance(followers, int):
            return None  # required field missing → drop, never ship malformed

        email = self._enrich_email(handle)
        audience_fit, demo_source = self._enrich_demographics(handle)
        return Creator(
            handle=handle, url=url, followers=followers, email=email,
            audience_fit=audience_fit,
            source=CreatorSource(
                profile=_SEARCH_TOOL,
                email=_EMAIL_TOOL if email is not None else None,
                demographics=demo_source,
            ),
        )

    def _enrich_email(self, handle: str) -> Optional[str]:
        try:
            raw = self._transport.post(EMAIL_PATH, {"handle": handle})
        except Exception:
            return None
        return _s(raw.get("email")) or None if isinstance(raw, dict) else None

    def _enrich_demographics(self, handle: str) -> tuple[Optional[float], Optional[str]]:
        """Returns (audience_fit, demographics_source). Both None on failure (grounding)."""
        try:
            raw = self._transport.post(DEMOGRAPHICS_PATH, {"handle": handle})
        except Exception:
            return None, None
        if not isinstance(raw, dict):
            return None, None
        fit = raw.get("audience_fit")
        if isinstance(fit, (int, float)) and not isinstance(fit, bool):
            return float(fit), _DEMO_TOOL
        return None, None


def _s(v: Any) -> str:
    return v if isinstance(v, str) else ""
