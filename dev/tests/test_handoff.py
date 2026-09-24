import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import handoff as h  # noqa: E402

SAMPLE = dict(
    side="buyer", as_of="2026-09-22",
    subject={"address": "517 Hickorywood Ave", "state": "FL", "county": "Seminole", "sqft": 1849, "list_price": 474900},
    value={"low": 455000, "high": 480000, "midpoint": 467500, "median_adjusted": 469800},
    comps=[{"address": "622 Spring Oaks Blvd", "sold_price": 505500, "close_date": "2026-04-24", "sqft": 1824,
            "seller_paid": 0, "adjusted": 492300}],
    market={"sale_to_original_list_recent": 0.965, "median_days_recent": 18, "months_supply": 4.1},
    offer_plan={"opening": 455000, "target_low": 460000, "target_high": 465000, "walk_away": 470000},
    market_profile={"state": "FL", "mls": "Stellar"},
)


class Handoff(unittest.TestCase):
    def test_round_trip_through_markdown(self):
        record = h.build(**SAMPLE)
        text = "## Buyer CMA\n\nSome summary.\n\n" + h.to_block(record) + "\n"
        self.assertEqual(h.parse_text(text), record)

    def test_json_and_markdown_files(self):
        record = h.build(**SAMPLE)
        with tempfile.TemporaryDirectory() as tmp:
            jp = os.path.join(tmp, h.filename("517 Hickorywood Ave"))
            with open(jp, "w") as f:
                json.dump(record, f)
            mp = os.path.join(tmp, "cma.md")
            with open(mp, "w") as f:
                f.write("notes\n" + h.to_block(record))
            self.assertEqual(h.load(jp), record)
            self.assertEqual(h.load(mp), record)
            other = os.path.join(tmp, "other.md")
            with open(other, "w") as f:
                f.write("A CMA from another tool with no block.")
            with self.assertRaises(h.HandoffError):
                h.load(other)

    def test_validation(self):
        bad = dict(SAMPLE, value={"low": 480000, "high": 455000, "midpoint": 467500})
        with self.assertRaises(h.HandoffError):
            h.build(**bad)
        with self.assertRaises(h.HandoffError):
            h.build(**dict(SAMPLE, value={"low": 1}))
        self.assertIsNone(h.parse_text("no block here"))
        with self.assertRaises(h.HandoffError):
            h.parse_text("```cma-handoff v2\n{}\n```")
        with self.assertRaises(h.HandoffError):
            h.parse_text("```cma-handoff v1\n{not json\n```")

    def test_filename(self):
        self.assertEqual(h.filename("517 Hickorywood Ave"), "517-Hickorywood-Ave.cma.json")
        # CMA-17: a buyer and a seller CMA of the same address don't overwrite each other
        self.assertEqual(h.filename("517 Hickorywood Ave", "buyer"), "517-Hickorywood-Ave.buyer.cma.json")
        self.assertEqual(h.filename("517 Hickorywood Ave", "seller"), "517-Hickorywood-Ave.seller.cma.json")


if __name__ == "__main__":
    unittest.main()
