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

TEXAS = """
---
profile: market
schema: 1
name: Austin (ACTRIS)
state: Texas
mls: ACTRIS
closing_costs:
  settlement_fee: 900
---
"""

FL_USER = """
---
profile: market
schema: 1
state: FL
closing_costs:
  settlement_fee: 800
  owner_title: {payer: buyer}
---
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
                p.load_agent(write(tmp, "m.md", TEXAS))


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
        self.assertIsNone(m.get("closing_costs.deed_transfer_tax_rate"))
        self.assertIsNone(m.get("county_overrides"))

    def test_mls_alias_and_explicit_mls(self):
        self.assertEqual(p.load_market(state="FL", county="Miami-Dade", mls="My Florida Regional MLS").mls, "Stellar")
        m = p.load_market(state="FL", mls="Beaches MLS")
        self.assertIsNone(m.get("mls_format"))
        self.assertTrue(any("isn't built in" in n for n in m.notes))

    def test_no_state_assumes_nothing(self):
        """CORE-8, TL-4: no silent Florida defaults."""
        m = p.load_market()
        self.assertIsNone(m.state)
        self.assertIsNone(m.get("closing_costs.deed_transfer_tax_rate"))
        self.assertTrue(any("don't assume Florida" in n for n in m.notes))

    def test_no_florida_defaults_for_other_states(self):
        m = p.load_market(state="TX")
        self.assertIsNone(m.get("closing_costs.deed_transfer_tax_rate"))
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "missing")
        self.assertEqual(m.missing(["closing_costs.settlement_fee", "state"]), ["closing_costs.settlement_fee"])
        self.assertTrue(any("No market profile for Texas" in n for n in m.notes))

    def test_other_state_profile_is_not_filled_from_florida(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = p.load_market(write(tmp, "tx.md", TEXAS), state="TX")
        self.assertEqual(m.get("closing_costs.settlement_fee"), 900)
        self.assertEqual(m.source("closing_costs.settlement_fee"), "profile")
        self.assertIsNone(m.get("closing_costs.deed_transfer_tax_rate"))
        self.assertIsNone(m.get("cma.adjustments.pool"))
        self.assertEqual(m.state, "TX")

    def test_florida_profile_overrides_state_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = p.load_market(write(tmp, "fl.md", FL_USER))
        self.assertEqual(m.get("closing_costs.settlement_fee"), 800)
        self.assertEqual(m.source("closing_costs.settlement_fee"), "profile")
        self.assertEqual(m.get("closing_costs.owner_title.payer"), "buyer")
        self.assertEqual(len(m.get("closing_costs.owner_title.rate_tiers")), 5)  # sibling kept from the layer
        self.assertEqual(m.source("closing_costs.owner_title.rate_tiers"), "state")
        self.assertEqual(m.source("closing_costs.owner_title"), "mixed")

    def test_county_override(self):
        m = p.load_market(state="FL", county="Miami-Dade County")
        self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0.006)
        self.assertEqual(m.get("closing_costs.owner_title.payer"), "buyer")
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "county")
        self.assertEqual(p.load_market(state="FL", county="Seminole").get("closing_costs.owner_title.payer"), "seller")

    def test_agent_beats_county_exception(self):
        """CORE-1: a Miami-Dade agent's own title payer wins over the built-in county custom."""
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "md.md", """
                ---
                profile: market
                state: FL
                closing_costs:
                  owner_title: {payer: seller}
                county_overrides:
                  Broward:
                    closing_costs: {hoa_estoppel_fee: 399}
                ---
                """)
            m = p.load_market(path, county="Miami-Dade")
            self.assertEqual(m.get("closing_costs.owner_title.payer"), "seller")
            self.assertEqual(m.source("closing_costs.owner_title.payer"), "profile")
            self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0.006)  # untouched county value stays
            b = p.load_market(path, county="Broward County")
            self.assertEqual(b.get("closing_costs.hoa_estoppel_fee"), 399)
            self.assertEqual(b.source("closing_costs.hoa_estoppel_fee"), "profile")

    def test_empty_section_keeps_built_in_values(self):
        """CORE-2: `closing_costs:` with nothing under it doesn't wipe the Florida group."""
        with tempfile.TemporaryDirectory() as tmp:
            m = p.load_market(write(tmp, "fl.md", "---\nprofile: market\nstate: FL\nclosing_costs:\nbrokerage:\n---\n"))
        self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0.007)
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "state")

    def test_county_spellings(self):
        """CORE-10: spelling variants match; an unknown Florida county gets a note."""
        for name in ("Miami Dade", "miami-dade county", "MIAMI-DADE"):
            self.assertEqual(p.load_market(state="FL", county=name).get("closing_costs.owner_title.payer"), "buyer", name)
        for a, b in (("St. Johns", "Saint Johns"), ("DeSoto", "De Soto County")):
            self.assertEqual(p._county_key(a), p._county_key(b))
        self.assertFalse(any("isn't a Florida county" in n for n in p.load_market(state="FL", county="St. Johns").notes))
        self.assertTrue(any("isn't a Florida county" in n for n in p.load_market(state="FL", county="Semnole").notes))

    def test_quoted_schema(self):
        """CORE-24: schema "1" reads as 1; a non-number is a ProfileError."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(p.load_market(write(tmp, "a.md", '---\nprofile: market\nschema: "1"\nstate: FL\n---\n')).state, "FL")
            with self.assertRaises(p.ProfileError):
                p.load_market(write(tmp, "b.md", "---\nprofile: market\nschema: one\nstate: FL\n---\n"))

    def test_state_mismatch_and_bad_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(p.ProfileError):
                p.load_market(write(tmp, "tx.md", TEXAS), state="FL")
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


class Find(unittest.TestCase):
    def test_finds_by_kind_one_level_deep(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "sub"))
            write(tmp, "agent-profile.md", AGENT)
            write(tmp, "sub/tx.md", TEXAS)
            write(tmp, "notes.md", "# just notes\n")
            write(tmp, "broken.md", "---\nprofile: [\n---\n")
            self.assertEqual([os.path.basename(x) for x in p.find("agent", [tmp])], ["agent-profile.md"])
            self.assertEqual([os.path.basename(x) for x in p.find("market", [tmp])], ["tx.md"])



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
