"""Read agent and market profiles: markdown files with a YAML front block.

    from _shared import profiles
    agent = profiles.load_agent(path)                     # path may be None
    market = profiles.load_market(path, state="FL", county="Seminole", mls=None)
    rate = market.get("closing_costs.deed_transfer_tax_rate")
    market.source("closing_costs.deed_transfer_tax_rate")  # 'profile' | 'state' | 'mls' | 'county'
    market.missing(["closing_costs.settlement_fee", ...])  # paths the skill still has to ask for

Skills never require a profile. When one is only in the conversation (not a file), Claude writes
it to a file verbatim and passes the path. See docs/architecture.md#profiles-core-plugin.
"""
import copy
import glob
import os

import yaml

from . import design

SCHEMA = 1
MARKETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "markets")
AGENT_REQUIRED = ("name", "brokerage")
AGENT_FIELDS = ("name", "team", "brokerage", "license", "phone", "email", "website")  # display order

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
_BY_NAME = {v.lower(): k for k, v in STATES.items()}


class ProfileError(ValueError):
    """A profile file that can't be read. The message is written for the user."""


# --- files ------------------------------------------------------------------

def parse(text):
    """Split a profile into (data, sections). Sections are '## Heading' blocks keyed by lowercase heading."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ProfileError("The profile doesn't start with a settings block (a line with ---).")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ProfileError("The profile's settings block isn't closed (missing the second --- line).") from None
    try:
        data = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError as e:
        raise ProfileError(f"The profile's settings block has a formatting problem: {e}") from None
    if not isinstance(data, dict):
        raise ProfileError("The profile's settings block should be a list of 'name: value' lines.")

    sections, current = {}, None
    for line in lines[end + 1:]:
        if line.startswith("## "):
            current = line[3:].strip().lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return data, {k: "\n".join(v).strip() for k, v in sections.items()}


def read(path):
    with open(path, encoding="utf-8") as f:
        data, sections = parse(f.read())
    return data, sections


def search_dirs():
    """Where profiles are looked for, in order."""
    dirs = [os.environ.get("OUTPUT_DIR"), "/mnt/user-data/uploads", "/mnt/user-data/outputs", os.getcwd()]
    return [d for d in dict.fromkeys(dirs) if d and os.path.isdir(d)]


def find(kind, dirs=None):
    """Paths of profile files of `kind` ('agent' or 'market') in the search dirs (and one level below)."""
    found = []
    for d in dirs or search_dirs():
        for path in sorted(glob.glob(os.path.join(d, "*.md")) + glob.glob(os.path.join(d, "*", "*.md"))):
            try:
                with open(path, encoding="utf-8") as f:
                    head = f.read(2000)
                if head.lstrip("﻿").startswith("---") and read(path)[0].get("profile") == kind:
                    found.append(path)
            except (OSError, ProfileError, UnicodeDecodeError):
                continue
    return found


# --- agent ------------------------------------------------------------------

def load_agent(path=None):
    """Agent profile as a dict with 'errors' (missing required fields) and 'warnings' (plain language).

    With no path, returns an empty profile whose errors list the required fields, so the skill asks
    for them only when its output shows them.
    """
    data, sections = read(path) if path else ({}, {})
    if path and data.get("profile") != "agent":
        raise ProfileError("This file isn't an agent profile.")
    errors = [f for f in AGENT_REQUIRED if not str(data.get(f) or "").strip()]
    warnings = []
    brand = data.get("brand")
    if brand is not None and not isinstance(brand, dict):
        warnings.append("Brand colors should be listed under 'brand' as primary, buyer_primary or seller_primary.")
        brand = None
    for side in ("buyer", "seller"):
        for w in design.resolve(brand, side)[2]:
            if w not in warnings:
                warnings.append(w)
    return {
        **{f: data.get(f) for f in AGENT_FIELDS},
        "brand": brand or {},
        "voice": sections.get("voice", ""),
        "disclaimers": sections.get("disclaimers", ""),
        "errors": errors,
        "warnings": warnings,
        "path": path,
    }


def agent_lines(agent):
    """Set fields only, in display order, as (field, value). Never placeholders for missing ones."""
    return [(f, str(agent[f]).strip()) for f in AGENT_FIELDS if agent.get(f) not in (None, "")]


# --- market -----------------------------------------------------------------

def state_code(value):
    """'FL', 'fl', 'Florida' -> 'FL'. None if it isn't a US state."""
    if not value:
        return None
    v = str(value).strip()
    return v.upper() if v.upper() in STATES else _BY_NAME.get(v.lower())


def _leaves(d, prefix=""):
    for k, v in d.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict) and v:
            yield from _leaves(v, path + ".")
        else:
            yield path, v


def _merge(base, over, sources, source, prefix=""):
    """Deep-merge `over` into `base` in place, recording the source of every leaf it sets."""
    for k, v in over.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v, sources, source, path + ".")
        else:
            base[k] = copy.deepcopy(v)
            if isinstance(v, dict):
                for leaf, _ in _leaves(v, path + "."):
                    sources[leaf] = source
            else:
                sources[path] = source


class Market:
    """Merged market values with the source of each one.

    Sources: 'profile' (user's market profile), 'state' (built-in state layer, that state only),
    'mls' (built-in MLS layer, that MLS only), 'county' (county override), 'input' (given by the skill).
    A path with no value is missing: ask for it, or use a labeled assumption and mark the output Preliminary.
    """

    def __init__(self, data, sources, notes):
        self.data, self.sources, self.notes = data, sources, notes

    @property
    def state(self):
        return state_code(self.data.get("state"))

    @property
    def mls(self):
        return self.data.get("mls")

    def get(self, path, default=None):
        node = self.data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def source(self, path):
        if path in self.sources:
            return self.sources[path]
        hits = {s for p, s in self.sources.items() if p.startswith(path + ".")}
        return hits.pop() if len(hits) == 1 else ("mixed" if hits else "missing")

    def missing(self, paths):
        return [p for p in paths if self.get(p) is None]


def _layers(kind):
    """Built-in layers: {'FL': data} for states, {'stellar': data} (name and aliases) for MLSs."""
    out = {}
    for path in sorted(glob.glob(os.path.join(MARKETS, "states" if kind == "state" else "mls", "*.md"))):
        data, _ = read(path)
        if kind == "state":
            out[state_code(data["state"])] = data
        else:
            for name in [data["mls"], *data.get("aliases", [])]:
                out[_mls_key(name)] = data
    return out


def _mls_key(name):
    return " ".join(str(name).lower().replace("mls", " ").split())


def _covers(layer, state, county):
    """True when the MLS layer covers the state, and the county too when one is given."""
    area = (layer.get("coverage") or {}).get(state)
    if not area:
        return False
    if area == "all" or not county:
        return True
    return _county_key(county) in {_county_key(c) for c in area}


def _county_key(county):
    return county.strip().lower().removesuffix(" county")


def _strip_layer_keys(layer):
    return {k: v for k, v in layer.items() if k not in ("layer", "name", "aliases", "as_of", "schema", "profile")}


def load_market(path=None, state=None, county=None, mls=None):
    """Market values for a property, merged from built-in layers, the user's profile and county overrides.

    - State layer (costs, taxes, contract rules): only when the property's state has one (Florida).
    - MLS layer (export formats, coverage): only for that MLS, in any state it serves. Without a
      profile or an `mls`, an MLS is assumed only when exactly one built-in MLS covers the county.
    - The user's profile wins over both. `county` then applies that county's overrides.
    Nothing from another state is ever filled in; `notes` explains every assumption in plain language.
    """
    want = state_code(state)
    if state and not want:
        raise ProfileError(f"{state!r} isn't a US state or territory.")

    user = {}
    if path:
        user, _ = read(path)
        if user.get("profile") != "market":
            raise ProfileError("This file isn't a market profile.")
        user_state = state_code(user.get("state"))
        if not user_state:
            raise ProfileError("The market profile needs a state (for example FL or Texas).")
        if want and want != user_state:
            raise ProfileError(f"The market profile is for {STATES[user_state]}, but the property is in {STATES[want]}.")
        want = user_state

    data, sources, notes = {}, {}, []
    if user.get("schema", SCHEMA) > SCHEMA:
        notes.append("This market profile was made by a newer version; some settings may be ignored.")
    states, mlss = _layers("state"), _layers("mls")
    if want is None:
        want = "FL"
        notes.append("The property's state wasn't given, so Florida was assumed.")

    if want in states:
        _merge(data, _strip_layer_keys(states[want]), sources, "state")
    elif not path:
        notes.append(f"No market profile for {STATES[want]}: local costs and rules have to be provided.")

    mls_name = user.get("mls") or mls
    layer = None
    if mls_name:
        layer = mlss.get(_mls_key(mls_name))
        if not layer:
            notes.append(f"{mls_name} isn't built in: its export columns and history codes have to be provided.")
    else:
        candidates = {id(l): l for l in mlss.values() if _covers(l, want, county)}
        if len(candidates) == 1:
            layer = next(iter(candidates.values()))
            notes.append(f"The MLS wasn't given, so {layer['name']} was assumed"
                         f"{' for ' + county if county else ''}.")
        else:
            notes.append(f"The MLS wasn't given{' for ' + county if county else ''}: "
                         "its export columns and history codes have to be provided if an MLS file is used.")
    if layer:
        _merge(data, _strip_layer_keys(layer), sources, "mls")

    _merge(data, {k: v for k, v in user.items() if k not in ("profile", "schema")}, sources, "profile")
    if mls_name and not data.get("mls"):
        data["mls"], sources["mls"] = mls_name, "input"  # an MLS that isn't built in is still the one in use
    data["state"] = want
    sources["state"] = "profile" if path else "state" if want in states else "input"

    if county:
        overrides = {_county_key(k): v for k, v in (data.get("county_overrides") or {}).items()}
        if _county_key(county) in overrides:
            _merge(data, overrides[_county_key(county)], sources, "county")
    return Market(data, sources, notes)
