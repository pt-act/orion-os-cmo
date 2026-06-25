"""adapter-geo-probe — focused + PBT tests (provenance, schema, idempotency)."""

import unittest

from orion_os_cmo.adapters.geo_probe import (
    GeoProbeAdapter,
    brand_in,
    parse_response,
    validate_report,
)
from orion_os_cmo.adapters.geo_probe.types import GeoReport, ModelResult


class MapTransport:
    """Returns a fixed response per (model, question); optionally raises."""

    def __init__(self, table, raise_all=False):
        self.table = table
        self.raise_all = raise_all

    def post(self, path, body):
        if self.raise_all:
            raise RuntimeError("engine down")
        return {"text": self.table[(body["model"], body["question"])]}


class GeoProbe(unittest.TestCase):
    def test_mention_grounded(self):
        t = MapTransport({("gpt", "best crm?"): "Acme is the best CRM, widely recommended."})
        res = GeoProbeAdapter(t).probe("Acme", ["best crm?"], ["gpt"])
        self.assertTrue(res.ok, res)
        row = res.value.per_model[0]
        self.assertTrue(row.mentioned)
        self.assertIn("acme", row.response_snippet.lower())
        self.assertEqual(row.sentiment, "positive")
        self.assertEqual(res.value.score, 1.0)

    def test_absent_brand(self):
        t = MapTransport({("gpt", "best crm?"): "Salesforce and HubSpot lead the market."})
        res = GeoProbeAdapter(t).probe("Acme", ["best crm?"], ["gpt"],
                                       competitors=["Salesforce", "HubSpot"])
        row = res.value.per_model[0]
        self.assertFalse(row.mentioned)
        self.assertIsNone(row.position)
        self.assertEqual(row.sentiment, "none")
        self.assertEqual(res.value.competitor_gaps, ["HubSpot", "Salesforce"])
        self.assertEqual(res.value.score, 0.0)

    def test_engine_failure_structured(self):
        res = GeoProbeAdapter(MapTransport({}, raise_all=True)).probe("Acme", ["q"], ["gpt"])
        self.assertFalse(res.ok)
        self.assertEqual(res.error.kind, "transport")

    def test_partial_results_not_suppressed(self):
        class Partial:
            def post(self, path, body):
                if body["model"] == "down":
                    raise RuntimeError("x")
                return {"text": "Acme is great."}
        res = GeoProbeAdapter(Partial()).probe("Acme", ["q"], ["down", "gpt"])
        self.assertTrue(res.ok)  # one engine failed, the other survived
        self.assertEqual(len(res.value.per_model), 1)

    def test_pbt_provenance_parser(self):
        # A true mention always carries the brand in its snippet.
        for text in ["Acme leads.", "I think acme is fine.", "...long...Acme...long..." * 30]:
            parsed = parse_response(text, "Acme")
            if parsed["mentioned"]:
                self.assertIn("acme", parsed["response_snippet"].lower())
        # No false positives: brand absent => not mentioned.
        self.assertFalse(parse_response("nothing here", "Acme")["mentioned"])

    def test_pbt_idempotency_and_schema(self):
        table = {("gpt", "q1"): "Acme wins.", ("gpt", "q2"): "Others win."}
        a = GeoProbeAdapter(MapTransport(table)).probe("Acme", ["q1", "q2"], ["gpt"])
        b = GeoProbeAdapter(MapTransport(table)).probe("Acme", ["q1", "q2"], ["gpt"])
        self.assertEqual(a.value, b.value)
        self.assertEqual(validate_report(a.value, "Acme"), [])

    def test_q1_word_boundary_no_false_positive(self):
        # "Macme" / "Acmex" must NOT count as a mention of "Acme".
        t = MapTransport({("gpt", "q"): "Macme and Acmex are unrelated products."})
        res = GeoProbeAdapter(t).probe("Acme", ["q"], ["gpt"])
        self.assertFalse(res.value.per_model[0].mentioned)
        self.assertEqual(res.value.score, 0.0)
        self.assertFalse(brand_in("talk about Macme here", "Acme"))
        self.assertTrue(brand_in("we love Acme!", "Acme"))

    def test_q2_validate_report_enforces_provenance(self):
        # A tampered row claiming a mention without the brand in its snippet is rejected.
        tampered = GeoReport(score=1.0, per_model=[
            ModelResult("gpt", "q", True, 0, "positive", "no brand here at all")])
        violations = validate_report(tampered, "Acme")
        self.assertTrue(any("provenance" in v for v in violations))
        # A genuine row passes.
        genuine = GeoReport(score=1.0, per_model=[
            ModelResult("gpt", "q", True, 0, "positive", "Acme is great")])
        self.assertEqual(validate_report(genuine, "Acme"), [])


if __name__ == "__main__":
    unittest.main()
