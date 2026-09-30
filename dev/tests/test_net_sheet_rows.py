"""Net sheet tables read each column's lines by key: a rider money line (rent-back, seller financing, an assessment
payoff) can be on one offer's net sheet and not on the Seller's Target, which used to raise IndexError."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

(review,) = load("seller-offer-review", "review")


class NetSheetRows(unittest.TestCase):
    def test_columns_with_different_lines(self):
        offer = {"lines": [("price", "Price", 400000), ("rent_back", "Rent-Back Credit", -1500), ("conc", "Concessions", 0)]}
        target = {"lines": [("price", "Price", 410000), ("conc", "Concessions", 0)]}
        rows = review.net_sheet_rows([("As Offered", offer), ("Target", target)])
        by_key = {r["key"]: r["values"] for r in rows}
        self.assertEqual(by_key["price"], [400000, 410000])
        self.assertEqual(by_key["rent_back"], [-1500, 0])
        self.assertEqual([r["key"] for r in rows], ["price", "rent_back", "conc"])


if __name__ == "__main__":
    unittest.main()
