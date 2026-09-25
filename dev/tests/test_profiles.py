import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import profiles as p  # noqa: E402


def write(tmp, name, text):
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write(textwrap.dedent(text).lstrip())
    return path


AGENT = """
---
profile: agent
schema: 1
name: Jane Doe
brokerage: Sunshine Realty
team: The Doe Group
brand:
  primary: "#1F3A5F"  # Navy
---

# Agent profile

## Voice
Warm, direct, no jargon.

## Disclaimers
Information deemed reliable but not guaranteed.
"""

class Parsing(unittest.TestCase):
    def test_errors_are_plain_language(self):
        for text in ("no block", "---\nname: x\n", "---\n: : :\n---\n", "---\n- a\n- b\n---\n"):
            with self.assertRaises(p.ProfileError):
                p.parse(text)

    def test_sections(self):
        data, sections = p.parse(textwrap.dedent(AGENT).lstrip())
        self.assertEqual(data["name"], "Jane Doe")
        self.assertEqual(sections["voice"], "Warm, direct, no jargon.")


class Agent(unittest.TestCase):
    def test_full_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = p.load_agent(write(tmp, "agent-profile.md", AGENT))
        self.assertEqual(a["errors"], [])
        self.assertEqual(a["warnings"], [])
        self.assertEqual(a["brand"]["primary"], "#1F3A5F")
        self.assertEqual(a["disclaimers"], "Information deemed reliable but not guaranteed.")
        self.assertEqual([f for f, _ in p.agent_lines(a)], ["name", "team", "brokerage"])

    def test_no_profile_lists_required_fields(self):
        a = p.load_agent(None)
        self.assertEqual(a["errors"], ["name", "brokerage"])
        self.assertEqual(p.agent_lines(a), [])

    def test_only_required_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = p.load_agent(write(tmp, "a.md", "---\nprofile: agent\nname: J\nbrokerage: B\n---\n"))
        self.assertEqual(a["errors"], [])
        self.assertEqual(a["brand"], {})

    def test_bad_color_warns_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = p.load_agent(write(tmp, "a.md", "---\nprofile: agent\nname: J\nbrokerage: B\nbrand: {primary: navy}\n---\n"))
        self.assertEqual(len(a["warnings"]), 1)

    def test_wrong_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(p.ProfileError):
                p.load_agent(write(tmp, "m.md", "---\nprofile: market\nstate: TX\n---\n"))

class Market(unittest.TestCase):
    def test_florida_gets_state_layer(self):
        m = p.load_market(state="Florida", county="Seminole")
        self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0.007)
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "state")
        self.assertEqual(m.state, "FL")

    def test_mls_assumed_only_inside_coverage(self):
        m = p.load_market(state="FL", county="Seminole County")
        self.assertEqual(m.mls, "Stellar")
        self.assertEqual(m.source("mls_format.cma_export_columns"), "mls")
        self.assertTrue(any("Stellar MLS was assumed" in n for n in m.notes))
        m = p.load_market(state="FL", county="Miami-Dade")
        self.assertIsNone(m.mls)
        self.assertIsNone(m.get("mls_format"))
        self.assertTrue(any("MLS wasn't given" in n for n in m.notes))

    def test_puerto_rico_gets_stellar_but_no_florida_costs(self):
        m = p.load_market(state="PR")
        self.assertEqual(m.mls, "Stellar")
        self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0.004)  # the national estimate, not Florida's 0.7%
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "estimate")
        self.assertIsNone(m.get("county_overrides"))

    def test_mls_alias_and_explicit_mls(self):
        self.assertEqual(p.load_market(state="FL", county="Miami-Dade", mls="My Florida Regional MLS").mls, "Stellar")
        m = p.load_market(state="FL", mls="Beaches MLS")
        self.assertIsNone(m.get("mls_format"))
        self.assertTrue(any("isn't built in" in n for n in m.notes))

    def test_no_state_assumes_nothing_from_florida(self):
        """CORE-8, TL-4: no silent Florida defaults; national estimates only."""
        m = p.load_market()
        self.assertIsNone(m.state)
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "estimate")
        self.assertIsNone(m.get("contract.day_count"))
        self.assertTrue(any("don't assume Florida" in n for n in m.notes))

    def test_other_states_get_national_estimates(self):
        m = p.load_market(state="GA")
        self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0.004)
        self.assertEqual(m.get("closing_costs.seller_title_fees"), {"settlement_and_title_fees": 1200})
        self.assertEqual((m.get("brokerage.listing_fee_pct"), m.get("brokerage.buyer_broker_fee_pct")), (0.025, 0.025))
        self.assertEqual(m.source("brokerage.listing_fee_pct"), "estimate")
        self.assertIsNone(m.get("contract.day_count"))  # time rules come from the contract, never estimated
        self.assertIsNone(m.get("cma.adjustments.pool"))
        self.assertTrue(any("national estimates" in n for n in m.notes))

    def test_no_state_transfer_tax_states(self):
        for st in ("TX", "AZ", "OR", "AK"):
            m = p.load_market(state=st)
            self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0, st)
            self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "national")
            self.assertTrue(any("no state transfer tax" in n for n in m.notes))
        self.assertEqual(p.load_market(state="FL").get("closing_costs.deed_transfer_tax_rate"), 0.007)  # its own
        self.assertEqual(p.load_market(state="TX").with_deal({"transfer_tax_rate": 0.002})
                         .get("closing_costs.deed_transfer_tax_rate"), 0.002)  # the deal's number still wins

    def test_estimates_never_mix_into_florida_values(self):
        """A section key is filled whole: Florida's fee list gets no estimated fee, its title table no estimate."""
        m = p.load_market(state="FL", county="Seminole")
        self.assertNotIn("settlement_and_title_fees", m.get("closing_costs.seller_title_fees"))
        self.assertEqual(m.source("closing_costs.seller_title_fees"), "state")
        self.assertIsNone(m.get("closing_costs.owner_title.estimate_pct"))
        self.assertEqual(m.source("brokerage.listing_fee_pct"), "estimate")  # no commission built in for Florida
        self.assertEqual(m.get("property_tax.fallback_rate"), 0.018)

    def test_county_override(self):
        m = p.load_market(state="FL", county="Miami-Dade County")
        self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0.006)
        self.assertEqual(m.get("closing_costs.owner_title.payer"), "buyer")
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "county")
        self.assertEqual(p.load_market(state="FL", county="Seminole").get("closing_costs.owner_title.payer"), "seller")

    def test_county_spellings(self):
        """CORE-10: spelling variants match; an unknown Florida county gets a note."""
        for name in ("Miami Dade", "miami-dade county", "MIAMI-DADE"):
            self.assertEqual(p.load_market(state="FL", county=name).get("closing_costs.owner_title.payer"), "buyer", name)
        for a, b in (("St. Johns", "Saint Johns"), ("DeSoto", "De Soto County")):
            self.assertEqual(p._county_key(a), p._county_key(b))
        self.assertFalse(any("isn't a Florida county" in n for n in p.load_market(state="FL", county="St. Johns").notes))
        self.assertTrue(any("isn't a Florida county" in n for n in p.load_market(state="FL", county="Semnole").notes))

    def test_bad_state(self):
        with self.assertRaises(p.ProfileError):
            p.load_market(state="Atlantis")

    def test_builtin_layers_are_valid(self):
        states, mlss = p._layers("state"), p._layers("mls")
        self.assertEqual(set(states), {"FL"})
        self.assertEqual(states["FL"]["layer"], "state")
        self.assertIsNone(states["FL"].get("mls_format"))
        self.assertEqual({l["mls"] for l in mlss.values()}, {"Stellar"})
        self.assertEqual(set(mlss["stellar"]["coverage"]), {"FL", "PR"})
        self.assertIsNone(mlss["stellar"].get("closing_costs"))


class Millage(unittest.TestCase):
    def test_entries_are_complete_and_sourced(self):
        m = p.load_market(state="FL")
        rows, sources = m.get("property_tax.millage"), m.get("property_tax.millage_sources")
        self.assertGreater(len(rows), 50)
        for r in rows:
            self.assertTrue({"county", "district", "year", "school", "total"} <= set(r), r)
            self.assertLess(r["school"], r["total"], r)
            self.assertTrue(8 < r["total"] < 25, r)  # plausible Florida aggregate millage
            self.assertIn(r["county"], sources, r)
        self.assertEqual(len({(r["county"], r["district"]) for r in rows}), len(rows))


class AuditMarketData(unittest.TestCase):
    """CORE-7 (verified: docs/audits/2026-09-23-verification.md)."""

    def test_no_mls_without_a_county(self):
        m = p.load_market(state="FL")
        self.assertIsNone(m.mls)  # Florida has several MLSs: ask
        self.assertTrue(any("MLS wasn't given" in n for n in m.notes))

    def test_pinellas_is_stellar_brevard_is_not(self):
        self.assertEqual(p.load_market(state="FL", county="Pinellas").mls, "Stellar")
        self.assertIsNone(p.load_market(state="FL", county="Brevard").mls)

    def test_title_payer_by_county(self):
        payer = lambda c: p.load_market(state="FL", county=c).get("closing_costs.owner_title.payer")  # noqa: E731
        self.assertEqual([payer(c) for c in ("Collier", "Broward", "Lee", "Charlotte", "Seminole")],
                         ["buyer", "buyer", "seller", "seller", "seller"])
        m = p.load_market(state="FL", county="Monroe")
        self.assertIsNone(m.get("closing_costs.owner_title.payer"))  # varies by area: ask
        self.assertTrue(any("owner_title.payer varies by area" in n for n in m.notes))
        self.assertFalse(any("varies by area" in n for n in p.load_market(state="FL", county="Seminole").notes))


if __name__ == "__main__":
    unittest.main()
