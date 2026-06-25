"""adapter-cms-publish — focused + PBT tests (approval gate, idempotency)."""

import unittest

from orion_os_cmo.adapters.cms_publish import CmsPublishAdapter
from orion_os_cmo.adapters.cms_publish.adapter import CHECK_PATH, CREATE_PATH, UPDATE_PATH


ARTICLE = {"title": "Best PM", "body": "copy", "slug": "best-pm",
           "meta": {"title_tag": "Best PM", "meta_description": "guide"}}


class FakeCms:
    """Stateful mock: tracks slugs, records every path called."""

    def __init__(self, fail=None):
        self.slugs = {}
        self.calls = []
        self.fail = fail or {}

    def post(self, path, body):
        self.calls.append((path, body))
        if path in self.fail:
            if self.fail[path] == "raise":
                raise RuntimeError("cms down")
            return {"error": self.fail[path]}
        slug = body.get("slug") or body.get("article", {}).get("slug")
        if path == CHECK_PATH:
            entry = self.slugs.get(slug)
            return {"exists": entry is not None, "existing_id": entry}
        if path == CREATE_PATH:
            new_id = f"id-{len(self.slugs) + 1}"
            self.slugs[body["article"]["slug"]] = new_id
            return {"url": f"https://cms.test/{body['article']['slug']}", "id": new_id}
        if path == UPDATE_PATH:
            slug2 = body["article"]["slug"]
            return {"url": f"https://cms.test/{slug2}", "id": body.get("id")}
        return {}


class CmsPublish(unittest.TestCase):
    def test_publish_with_token(self):
        cms = FakeCms()
        res = CmsPublishAdapter(cms).publish_article("wordpress", ARTICLE, "tok-123")
        self.assertTrue(res.ok, res)
        self.assertEqual(res.value.url, "https://cms.test/best-pm")
        self.assertIn(CREATE_PATH, [p for p, _ in cms.calls])

    def test_no_token_gated_no_transport(self):
        cms = FakeCms()
        res = CmsPublishAdapter(cms).publish_article("wordpress", ARTICLE, None)
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "approval_required")
        self.assertEqual(cms.calls, [])  # transport never touched

    def test_empty_token_gated_no_transport(self):
        cms = FakeCms()
        res = CmsPublishAdapter(cms).publish_article("wordpress", ARTICLE, "")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "approval_required")
        self.assertEqual(cms.calls, [])

    def test_unsupported_cms_no_transport(self):
        cms = FakeCms()
        res = CmsPublishAdapter(cms).publish_article("squarespace", ARTICLE, "tok")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "unsupported_cms")
        self.assertEqual(cms.calls, [])

    def test_transport_failure(self):
        cms = FakeCms(fail={CHECK_PATH: "raise"})
        res = CmsPublishAdapter(cms).publish_article("wordpress", ARTICLE, "tok")
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "transport")

    def test_pbt_idempotency_update_path(self):
        cms = FakeCms()
        adapter = CmsPublishAdapter(cms)
        first = adapter.publish_article("wordpress", ARTICLE, "tok")
        second = adapter.publish_article("wordpress", ARTICLE, "tok")
        self.assertEqual(first.value.url, second.value.url)
        paths = [p for p, _ in cms.calls]
        self.assertEqual(paths.count(CREATE_PATH), 1)  # created exactly once
        self.assertIn(UPDATE_PATH, paths)              # second went through update
        self.assertEqual(len(cms.slugs), 1)            # no duplicate

    def test_pbt_gate_absolute(self):
        for token in (None, "", "   "):
            cms = FakeCms()
            res = CmsPublishAdapter(cms).publish_article("webflow", ARTICLE, token)
            self.assertEqual(res.error.kind, "approval_required")
            self.assertEqual(cms.calls, [])


if __name__ == "__main__":
    unittest.main()
