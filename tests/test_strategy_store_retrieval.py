import unittest
from typing import Any, Callable

from orion_os_cmo.adapters.crawl.adapter import CrawlAdapter
from orion_os_cmo.strategy_store.retrieval import retrieve_evidence


class FakeTransport:
    def __init__(self, handler: Callable[[str, dict[str, Any]], Any]) -> None:
        self._handler = handler

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._handler(path, body)


SCRAPE = {"url": "https://acme.test/", "title": "Acme", "content": "# Acme\nProject management for teams."}
SEARCH = {"results": [
    {"title": "Notion", "url": "https://notion.so", "text": "All-in-one workspace", "summary": "workspace", "score": 0.9},
    {"title": "Empty", "url": "https://empty.test", "text": "", "summary": "", "score": 0.1},
]}


class RetrievalGroup1(unittest.TestCase):
    def test_1_3_returns_nonempty_source_tagged_set(self) -> None:
        adapter = CrawlAdapter(FakeTransport(
            lambda path, body: SCRAPE if "firecrawl/scrape" in path else SEARCH))

        res = retrieve_evidence(adapter, "https://acme.test", ["notion alternative"])

        self.assertTrue(res.ok)
        items = res.value.items
        self.assertGreater(len(items), 0)

        # Provenance invariant: every item carries source.tool + source.url and real text.
        for item in items:
            self.assertTrue(item.source.tool)
            self.assertTrue(item.source.url)
            self.assertTrue(item.text.strip())

        # A page and exactly one search result (empty-text hit dropped).
        self.assertTrue(any(i.kind == "page" for i in items))
        self.assertEqual(len([i for i in items if i.kind == "search_result"]), 1)

        # Ids unique.
        self.assertEqual(len({i.id for i in items}), len(items))

    def test_1_4_transport_failure_is_structured_not_empty(self) -> None:
        def handler(path: str, body: dict[str, Any]) -> Any:
            if "firecrawl/scrape" in path:
                raise RuntimeError("network down")
            return SEARCH

        res = retrieve_evidence(CrawlAdapter(FakeTransport(handler)), "https://acme.test")

        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "transport")
        self.assertEqual(res.error.source.tool, "firecrawl/scrape")
        self.assertTrue(res.error.message)

    def test_empty_content_yields_empty_error(self) -> None:
        adapter = CrawlAdapter(FakeTransport(
            lambda path, body: {"url": "https://acme.test/", "title": "", "content": "   "}
            if "firecrawl/scrape" in path else SEARCH))

        res = retrieve_evidence(adapter, "https://acme.test")

        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "empty")


if __name__ == "__main__":
    unittest.main()
