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
    def test_builtin_for_florida(self):
        m = p.load_market(state="Florida")
        self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0.007)
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "builtin")
        self.assertEqual(m.notes, [])

    def test_unknown_state_assumes_builtin_and_says_so(self):
        m = p.load_market()
        self.assertEqual(m.state, "FL")
        self.assertEqual(len(m.notes), 1)

    def test_no_florida_defaults_for_other_states(self):
        m = p.load_market(state="TX")
        self.assertIsNone(m.get("closing_costs.deed_transfer_tax_rate"))
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "missing")
        self.assertEqual(m.missing(["closing_costs.settlement_fee", "state"]), ["closing_costs.settlement_fee"])
        self.assertTrue(m.notes)

    def test_other_state_profile_is_not_filled_from_florida(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = p.load_market(write(tmp, "tx.md", TEXAS), state="TX")
        self.assertEqual(m.get("closing_costs.settlement_fee"), 900)
        self.assertEqual(m.source("closing_costs.settlement_fee"), "profile")
        self.assertIsNone(m.get("closing_costs.deed_transfer_tax_rate"))
        self.assertIsNone(m.get("cma.adjustments.pool"))

    def test_florida_profile_overrides_builtin(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = p.load_market(write(tmp, "fl.md", FL_USER))
        self.assertEqual(m.get("closing_costs.settlement_fee"), 800)
        self.assertEqual(m.source("closing_costs.settlement_fee"), "profile")
        self.assertEqual(m.get("closing_costs.owner_title.payer"), "buyer")
        self.assertEqual(len(m.get("closing_costs.owner_title.rate_tiers")), 5)  # sibling kept from builtin
        self.assertEqual(m.source("closing_costs.owner_title.rate_tiers"), "builtin")
        self.assertEqual(m.source("closing_costs.owner_title"), "mixed")

    def test_county_override(self):
        m = p.load_market(state="FL", county="Miami-Dade County")
        self.assertEqual(m.get("closing_costs.deed_transfer_tax_rate"), 0.006)
        self.assertEqual(m.get("closing_costs.owner_title.payer"), "buyer")
        self.assertEqual(m.source("closing_costs.deed_transfer_tax_rate"), "county")
        self.assertEqual(p.load_market(state="FL", county="Seminole").get("closing_costs.owner_title.payer"), "seller")

    def test_state_mismatch_and_bad_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(p.ProfileError):
                p.load_market(write(tmp, "tx.md", TEXAS), state="FL")
        with self.assertRaises(p.ProfileError):
            p.load_market(state="Atlantis")

    def test_builtin_is_valid_market_profile(self):
        data, sections = p.read(p.BUILTIN_MARKET)
        self.assertEqual((data["profile"], data["schema"], data["state"]), ("market", 1, "FL"))
        self.assertIn("notes", sections)


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


if __name__ == "__main__":
    unittest.main()
