"""Tests for plugins/core/skills/market-profile/scripts (run against the synced _shared copy)."""
import os
import sys
import tempfile
import textwrap
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "core", "skills", "market-profile", "scripts")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

(check_market,) = load("market-profile", "check_market")

TEMPLATE = os.path.join(SCRIPTS, "..", "assets", "market-profile-template.md")

# A profile the way SKILL.md step 4 asks for it: only the agent's own values.
TEXAS = """
---
profile: market
schema: 1
name: "Austin metro"
state: "TX"
area: "Travis, Williamson"
mls: "ACTRIS"

closing_costs:
  deed_transfer_tax_rate: 0
  deed_transfer_tax_payer: seller
  owner_title:
    payer: seller
    estimate_pct: 0.0055
  seller_title_fees:
    escrow_fee: 650
  buyer_closing_cost_pct: 0.025

brokerage:
  listing_fee_pct: 0.03
  buyer_broker_fee_pct: 0.025
---

# Market profile: Austin metro

TX · Travis, Williamson · ACTRIS

## What's customized

- No deed transfer tax in Texas.
"""

FL_SPLIT_ONLY = """
---
profile: market
schema: 1
name: "Seminole County"
state: "FL"
brokerage:
  listing_fee_pct: 0.03
  buyer_broker_fee_pct: 0.02
---

# Market profile: Seminole County
"""


def write(tmp, text):
    path = os.path.join(tmp, "market-profile.md")
    with open(path, "w") as f:
        f.write(textwrap.dedent(text).lstrip())
    return path


class Builtin(unittest.TestCase):
    def test_florida_is_complete(self):
        r = check_market.check(state="FL", county="Seminole")
        self.assertTrue(r["ok"])
        self.assertEqual(r["mls"], "Stellar")
        self.assertTrue(all(g["complete"] for g in r["groups"].values()), r["groups"])
        self.assertEqual(r["groups"]["brokerage"]["values"]["brokerage.listing_fee_pct"]["source"], "state")
        self.assertIn("Sanford", r["millage_districts"])

    def test_other_state_lists_every_gap(self):
        r = check_market.check(state="TX")
        self.assertTrue(r["ok"])  # nothing wrong, just nothing known
        self.assertFalse(any(g["complete"] for g in r["groups"].values()))
        self.assertIn("closing_costs.owner_title.rate_tiers or closing_costs.owner_title.estimate_pct",
                      r["groups"]["closing costs"]["missing"])

    def test_county_exception_source(self):
        r = check_market.check(state="FL", county="Miami-Dade")
        v = r["groups"]["closing costs"]["values"]["closing_costs.deed_transfer_tax_rate"]
        self.assertEqual((v["value"], v["source"]), (0.006, "county"))
        self.assertFalse(r["groups"]["mls files"]["complete"])


class AgentProfiles(unittest.TestCase):
    def test_texas_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = check_market.check(write(tmp, TEXAS))
        self.assertTrue(r["ok"], r)
        cc = r["groups"]["closing costs"]
        self.assertEqual(cc["values"]["closing_costs.owner_title.estimate_pct"]["source"], "profile")
        self.assertEqual(cc["values"]["closing_costs.deed_transfer_tax_rate"]["value"], 0)  # zero is a value
        self.assertEqual(cc["missing"], ["closing_costs.hoa_estoppel_fee"])
        self.assertTrue(r["groups"]["brokerage"]["complete"])
        self.assertFalse(r["groups"]["contract dates"]["complete"])

    def test_florida_profile_changes_only_the_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = check_market.check(write(tmp, FL_SPLIT_ONLY), county="Seminole")
        b = r["groups"]["brokerage"]["values"]
        self.assertEqual((b["brokerage.buyer_broker_fee_pct"]["value"], b["brokerage.buyer_broker_fee_pct"]["source"]),
                         (0.02, "profile"))
        t = r["groups"]["closing costs"]["values"]["closing_costs.deed_transfer_tax_rate"]
        self.assertEqual(t["source"], "state")
        self.assertTrue(all(g["complete"] for g in r["groups"].values()))

    def test_unfilled_template_is_a_problem(self):
        r = check_market.check(TEMPLATE)
        self.assertFalse(r["ok"])

    def test_state_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = check_market.check(write(tmp, TEXAS), state="FL")
        self.assertFalse(r["ok"])
        self.assertIn("Texas", r["problems"][0])


if __name__ == "__main__":
    unittest.main()
