"""Local on-page SEO analysis — stdlib HTML parsing, no third party.

Derives ``issues[]`` only from the real page HTML (missing/short title, missing meta
description, missing H1, images without alt, missing canonical). Every issue carries
a grounding ``snippet``. Pure and deterministic: the same HTML always yields the same
issues, in a fixed rule order.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any

_TITLE_MAX = 60


class _OnPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self._in_title = False
        self.has_meta_description = False
        self.has_h1 = False
        self.has_canonical = False
        self.imgs_without_alt: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
            if self.title is None:
                self.title = ""
        elif tag == "meta" and a.get("name", "").lower() == "description":
            if a.get("content", "").strip():
                self.has_meta_description = True
        elif tag == "h1":
            self.has_h1 = True
        elif tag == "link" and "canonical" in a.get("rel", "").lower():
            self.has_canonical = True
        elif tag == "img":
            if not a.get("alt", "").strip():
                src = a.get("src", "")
                self.imgs_without_alt.append(f'<img src="{src}">')

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and self.title is not None:
            self.title += data


def parse_onpage_issues(html: str) -> list[dict[str, Any]]:
    parser = _OnPageParser()
    parser.feed(html)
    title = (parser.title or "").strip()

    issues: list[dict[str, Any]] = []

    if not title:
        issues.append(_issue("critical", "missing_title",
                             "Add a descriptive <title> (≤60 chars) with the primary keyword.",
                             "<head> has no non-empty <title>"))
    elif len(title) > _TITLE_MAX:
        issues.append(_issue("warning", "long_title",
                             f"Shorten the <title> to ≤{_TITLE_MAX} chars to avoid SERP truncation.",
                             f"<title>{title}</title> ({len(title)} chars)"))

    if not parser.has_meta_description:
        issues.append(_issue("warning", "missing_meta_description",
                             "Add a <meta name=\"description\"> (≤160 chars) summarizing the page.",
                             '<head> has no non-empty <meta name="description">'))

    if not parser.has_h1:
        issues.append(_issue("warning", "missing_h1",
                             "Add a single <h1> stating the page's main topic.",
                             "document has no <h1>"))

    for img_snippet in parser.imgs_without_alt:
        issues.append(_issue("info", "img_missing_alt",
                             "Add descriptive alt text for accessibility and image SEO.",
                             img_snippet))

    if not parser.has_canonical:
        issues.append(_issue("info", "missing_canonical",
                             "Add <link rel=\"canonical\"> to consolidate duplicate URLs.",
                             '<head> has no <link rel="canonical">'))

    return issues


def _issue(severity: str, type_: str, fix: str, snippet: str) -> dict[str, Any]:
    return {"severity": severity, "type": type_, "fix": fix, "snippet": snippet}
