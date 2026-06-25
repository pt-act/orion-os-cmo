"""transport-self-hosted — focused + cross-cutting property tests.

No network, no browser, no Node: the four external actions are injected as stubs.
Handlers are also composed with the REAL CrawlAdapter / SeoAuditAdapter to prove the
backend swap needs zero adapter change.
"""

import json
import random
import string
import sys
import types
import unittest

from orion_os_cmo.adapters.crawl.adapter import SCRAPE_PATH, SEARCH_PATH, CrawlAdapter
from orion_os_cmo.adapters.seo_audit.adapter import (
    LIGHTHOUSE_PATH,
    PROVIDER_PATH,
    SeoAuditAdapter,
)
from orion_os_cmo.transports import (
    SearchNotConfiguredError,
    SelfHostedTransport,
    TransportConfig,
    UnsupportedPathError,
)


# ── stubs ────────────────────────────────────────────────────────────────────

def render_ok(url, **kw):
    return {"url": url, "title": "Acme — PM tool", "content": "Acme is a project tool. " * 5}


def render_empty(url, **kw):
    return {"url": url, "title": "", "content": ""}


def render_raises(url, **kw):
    raise RuntimeError("browser crashed")


def brave_http(url, headers, **kw):
    return {"web": {"results": [
        {"title": "Notion", "url": "https://notion.so", "description": "all-in-one workspace"},
        {"title": "", "url": "", "description": "malformed (no url)"},  # must be skipped
    ]}}


LH_JSON = {"categories": {"performance": {"score": 0.9}}, "lighthouseVersion": "11.0",
           "audits": {"largest-contentful-paint": {"numericValue": 2100.0},
                      "cumulative-layout-shift": {"numericValue": 0.04}}}


def runner_ok(cmd, **kw):
    return types.SimpleNamespace(returncode=0, stdout=json.dumps(LH_JSON), stderr="")


def runner_fail(cmd, **kw):
    return types.SimpleNamespace(returncode=1, stdout="", stderr="boom")


def runner_missing(cmd, **kw):
    raise FileNotFoundError("npx")


CLEAN_HTML = ('<html><head><title>Acme PM</title>'
              '<meta name="description" content="The project tool.">'
              '<link rel="canonical" href="https://acme.test/"></head>'
              '<body><h1>Acme</h1><img src="a.png" alt="logo"></body></html>')

DIRTY_HTML = '<html><head></head><body><p>buy</p><img src="x.png"></body></html>'


def html_ok(url, **kw):
    return CLEAN_HTML


def cfg(**kw):
    base = dict(search_provider="brave", search_api_key="SECRET-KEY",
                renderer=render_ok, search_http=brave_http,
                subprocess_runner=runner_ok, html_fetcher=html_ok)
    base.update(kw)
    return TransportConfig(**base)


# ── Group 1: dispatch ────────────────────────────────────────────────────────

class Dispatch(unittest.TestCase):
    def test_unknown_path_raises(self):
        with self.assertRaises(UnsupportedPathError):
            SelfHostedTransport(cfg()).post("/api/unknown", {})

    def test_route_fidelity(self):
        t = SelfHostedTransport(cfg())
        self.assertEqual(set(t._dispatch.keys()),
                         {SCRAPE_PATH, SEARCH_PATH, PROVIDER_PATH, LIGHTHOUSE_PATH})
        # only `post` is public
        public = [m for m in dir(t) if not m.startswith("_") and callable(getattr(t, m))]
        self.assertEqual(public, ["post"])

    def test_repr_hides_key(self):
        c = cfg()
        self.assertNotIn("SECRET-KEY", repr(c))
        self.assertNotIn("SECRET-KEY", repr(SelfHostedTransport(c)))


# ── Group 2: scrape (composed with real CrawlAdapter) ────────────────────────

class Scrape(unittest.TestCase):
    def test_ok(self):
        res = CrawlAdapter(SelfHostedTransport(cfg())).scrape("https://acme.test/")
        self.assertTrue(res.ok, res)
        self.assertTrue(res.value.content)

    def test_render_failure_maps_to_transport(self):
        res = CrawlAdapter(SelfHostedTransport(cfg(renderer=render_raises))).scrape("https://acme.test/")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "transport")

    def test_empty_content_maps_to_empty(self):
        res = CrawlAdapter(SelfHostedTransport(cfg(renderer=render_empty))).scrape("https://acme.test/")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "empty")


# ── Group 3: search ──────────────────────────────────────────────────────────

class Search(unittest.TestCase):
    def test_ok_normalized_and_skips_malformed(self):
        res = CrawlAdapter(SelfHostedTransport(cfg())).search("project management")
        self.assertTrue(res.ok, res)
        self.assertEqual(len(res.value.results), 1)  # malformed (no url) skipped
        self.assertEqual(res.value.results[0].url, "https://notion.so")

    def test_no_key_raises(self):
        with self.assertRaises(SearchNotConfiguredError):
            SelfHostedTransport(cfg(search_api_key=None)).post(SEARCH_PATH, {"query": "x"})

    def test_unsupported_provider_raises(self):
        with self.assertRaises(SearchNotConfiguredError):
            SelfHostedTransport(cfg(search_provider="duckduckgo")).post(SEARCH_PATH, {"query": "x"})


# ── Group 4: lighthouse (composed with real SeoAuditAdapter) ─────────────────

class Lighthouse(unittest.TestCase):
    def test_ok_audit(self):
        res = SeoAuditAdapter(SelfHostedTransport(cfg())).seo_audit("https://acme.test/")
        self.assertTrue(res.ok, res)
        self.assertEqual(res.value.meta["lighthouse_version"], "11.0")

    def test_missing_binary_maps_to_lighthouse_failure(self):
        res = SeoAuditAdapter(SelfHostedTransport(cfg(subprocess_runner=runner_missing))).seo_audit("u")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "lighthouse_failure")

    def test_nonzero_exit_maps_to_lighthouse_failure(self):
        res = SeoAuditAdapter(SelfHostedTransport(cfg(subprocess_runner=runner_fail))).seo_audit("u")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "lighthouse_failure")


# ── Group 5: onpage ──────────────────────────────────────────────────────────

class OnPage(unittest.TestCase):
    def test_missing_title_critical(self):
        out = SelfHostedTransport(cfg(html_fetcher=lambda u, **k: DIRTY_HTML)).post(PROVIDER_PATH, {"url": "u"})
        types_seen = {i["type"]: i for i in out["issues"]}
        self.assertIn("missing_title", types_seen)
        self.assertEqual(types_seen["missing_title"]["severity"], "critical")
        self.assertTrue(types_seen["missing_title"]["snippet"])
        self.assertIn("img_missing_alt", types_seen)

    def test_clean_page_no_issues_full_audit(self):
        out = SelfHostedTransport(cfg()).post(PROVIDER_PATH, {"url": "u"})
        self.assertEqual(out["issues"], [])
        # composed with stub lighthouse → Ok(AuditReport), perf 0.9, no penalties → score 90
        res = SeoAuditAdapter(SelfHostedTransport(cfg())).seo_audit("https://acme.test/")
        self.assertTrue(res.ok)
        self.assertEqual(res.value.score, 90)

    def test_determinism(self):
        t = SelfHostedTransport(cfg(html_fetcher=lambda u, **k: DIRTY_HTML))
        a = t.post(PROVIDER_PATH, {"url": "u"})["issues"]
        b = t.post(PROVIDER_PATH, {"url": "u"})["issues"]
        self.assertEqual(a, b)


# ── Group 6: cross-cutting properties ────────────────────────────────────────

class Properties(unittest.TestCase):
    def test_pbt_no_fabrication_on_failure(self):
        # Every handler whose tool fails → post RAISES (never an Ok-shaped dict).
        failing = [
            (SCRAPE_PATH, {"url": "u"}, cfg(renderer=render_raises)),
            (SEARCH_PATH, {"query": "q"}, cfg(search_http=lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))),
            (SEARCH_PATH, {"query": "q"}, cfg(search_api_key=None)),
            (LIGHTHOUSE_PATH, {"url": "u"}, cfg(subprocess_runner=runner_fail)),
            (LIGHTHOUSE_PATH, {"url": "u"}, cfg(subprocess_runner=runner_missing)),
            (PROVIDER_PATH, {"url": "u"}, cfg(html_fetcher=lambda *a, **k: (_ for _ in ()).throw(IOError()))),
        ]
        for path, body, c in failing:
            with self.assertRaises(Exception):
                SelfHostedTransport(c).post(path, body)

    def test_pbt_secrets_never_leak(self):
        rng = random.Random(11)
        for _ in range(100):
            key = "".join(rng.choices(string.ascii_letters + string.digits, k=rng.randint(8, 40)))
            c = cfg(search_api_key=key)
            t = SelfHostedTransport(c)
            self.assertNotIn(key, repr(c))
            self.assertNotIn(key, repr(t))
            # key never appears in a handler return value
            out = t.post(SEARCH_PATH, {"query": "q"})
            self.assertNotIn(key, json.dumps(out))

    def test_pbt_route_fidelity_no_extra_route(self):
        t = SelfHostedTransport(cfg())
        self.assertEqual(set(t._dispatch), {SCRAPE_PATH, SEARCH_PATH, PROVIDER_PATH, LIGHTHOUSE_PATH})

    def test_adapter_immutability_one_directional(self):
        # The adapters must not depend on the transports package (the swap is behind
        # the seam, one-directional).
        import inspect
        import orion_os_cmo.adapters.crawl.adapter as crawl_a
        import orion_os_cmo.adapters.seo_audit.adapter as seo_a
        for mod in (crawl_a, seo_a):
            self.assertNotIn("transports", inspect.getsource(mod))

    def test_module_import_is_lazy(self):
        # Importing the transport pulls in no Playwright at module load.
        import orion_os_cmo.transports.self_hosted  # noqa: F401
        self.assertNotIn("playwright", sys.modules)


if __name__ == "__main__":
    unittest.main()
