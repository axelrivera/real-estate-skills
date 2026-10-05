"""cma-handoff v1: the small, stable record a CMA hands to the offer skills.

Producers (buyer-cma, seller-cma) write it as `<address>.<side>.cma.json` next to report.json, in the
conversation's temporary folder: a working file, never shown to the agent or put in the outputs.

Consumers (buyer-offer-strategy, seller-offer-review) call `load()`: the JSON file, or markdown that
carries an older fenced `cma-handoff v1` block (no longer written, still read). Without either, the skill
reads the CMA's PDF or summary, confirms the numbers with the agent and labels them as assumptions.
"""
import json
import re

KIND, VERSION = "cma", 1
FENCE = f"cma-handoff v{VERSION}"
_BLOCK = re.compile(r"```cma-handoff v(\d+)\s*\n(.*?)\n```", re.S)

REQUIRED = {
    "side": str,
    "as_of": str,
    "subject": dict,
    "value": dict,
    "comps": list,
}
VALUE_KEYS = ("low", "high", "midpoint")
# CMA-111: optional subject facts (still v1: a reader that doesn't know them ignores them). The offer skills use them when
# the offer file doesn't say: the tax the CMA computed (millage and homestead for the buyer's payment, the current bill
# for the seller's proration), the flood zone (a FEMA code only), HOA dues and the roof year. CMA-328: the listing's
# days on market (`dom`: active days since the last sale, counted on `as_of`, a number) and how many price cuts since then (`price_cuts`, an integer count), for
# the buyer's offer outlook. `hoa_frequency` (monthly, quarterly, semiannual or annual): how the association bills the
# dues, so the HOA rider shows the amount as billed.
NUMBER = (int, float)
SUBJECT_OPTIONAL = {"annual_tax": NUMBER, "school_mills": NUMBER, "total_mills": NUMBER, "homestead": bool,
                    "flood_zone": str, "hoa_monthly": NUMBER, "hoa_frequency": str, "roof_year": int, "dom": NUMBER,
                    "price_cuts": int}
_FEMA = re.compile(r"^\s*(A99|AE|AH|AO|AR|A|VE|V|X500|X|B|C|D)\b", re.I)


class HandoffError(ValueError):
    """The handoff can't be used; the message says why in plain words."""


def flood_code(text):
    """'X (lower risk)' -> 'X'; 'AE' -> 'AE'; 'To confirm (likely X)' or anything else -> None. Only a FEMA zone code goes
    in a handoff, so no reader ever takes a note for a zone."""
    m = _FEMA.match(str(text or ""))
    return m.group(1).upper() if m else None


def subject_facts(**facts):
    """The optional subject facts that are set, for build(subject=...): None, a value of the wrong kind and a zone that
    isn't a FEMA code are left out, so a producer never fails on a fact it only passes along."""
    if "flood_zone" in facts:
        facts["flood_zone"] = flood_code(facts["flood_zone"])
    typ = SUBJECT_OPTIONAL
    return {k: v for k, v in facts.items() if v is not None and k in typ and isinstance(v, typ[k])
            and (typ[k] is bool or not isinstance(v, bool))}


def build(side, as_of, subject, value, comps, market=None, offer_plan=None, recommended_list_price=None,
          market_profile=None, source=None):
    """Assemble and validate a handoff dict. Money as plain numbers; dates as YYYY-MM-DD."""
    h = {
        "handoff": KIND, "version": VERSION, "side": side, "as_of": as_of, "source": source or f"{side}-cma",
        "subject": subject, "value": value, "comps": comps, "market": market or {},
        "offer_plan": offer_plan, "recommended_list_price": recommended_list_price,
        "market_profile": market_profile or {},
    }
    validate(h)
    return h


def validate(h):
    if h.get("handoff") != KIND:
        raise HandoffError("This isn't a CMA handoff.")
    if h.get("version") != VERSION:
        raise HandoffError(f"CMA handoff version {h.get('version')} isn't supported (expected {VERSION}).")
    for key, typ in REQUIRED.items():
        if not isinstance(h.get(key), typ):
            raise HandoffError(f"The CMA handoff is missing {key}.")
    missing = [k for k in VALUE_KEYS if not isinstance(h["value"].get(k), (int, float))]
    if missing:
        raise HandoffError(f"The CMA handoff's value range is missing {', '.join(missing)}.")
    if h["value"]["low"] > h["value"]["high"]:
        raise HandoffError("The CMA handoff's value range is reversed (low above high).")
    for key, typ in SUBJECT_OPTIONAL.items():
        v = h["subject"].get(key)
        if v is None:
            continue
        if not isinstance(v, typ) or (typ is not bool and isinstance(v, bool)):
            raise HandoffError(f"The CMA handoff's subject.{key} isn't the right kind of value ({v!r}).")
        if key == "flood_zone" and flood_code(v) is None:
            raise HandoffError(f"The CMA handoff's flood zone ({v!r}) isn't a FEMA zone code.")
    return h


def to_block(h):
    """The fenced markdown block for the end of a markdown reply."""
    return f"```{FENCE}\n{json.dumps(validate(h), indent=2)}\n```"


def parse_text(text):
    """Find and validate a handoff block in markdown text; None if there isn't one."""
    m = _BLOCK.search(text or "")
    if not m:
        return None
    if int(m.group(1)) != VERSION:
        raise HandoffError(f"CMA handoff version {m.group(1)} isn't supported (expected {VERSION}).")
    try:
        return validate(json.loads(m.group(2)))
    except json.JSONDecodeError as e:
        raise HandoffError(f"The CMA handoff block isn't valid JSON: {e.msg}.") from None


CLIENT_KEYS = ("subject", "comps", "market", "offer_plan")  # what the offer skills can show a client


def linked(data, args):
    """For render.main(linked=...): the handoff named by --cma, its client-facing parts only, so its text gets the same
    wording check as the data file. A file that can't be read is left to the skill, which says why."""
    path = args.get("cma")
    if not path:
        return []
    try:
        h = load(path)
    except (OSError, ValueError):
        return []
    return [("cma", {k: h[k] for k in CLIENT_KEYS if k in h})]


def load(path):
    """A handoff from a .cma.json file, or from a markdown/text file that contains the block."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.endswith(".json"):
        try:
            return validate(json.loads(text))
        except json.JSONDecodeError as e:
            raise HandoffError(f"The CMA file isn't valid JSON: {e.msg}.") from None
    h = parse_text(text)
    if h is None:
        raise HandoffError("No cma-handoff block in this file. Read the CMA and confirm its numbers with the agent instead.")
    return h


def filename(address, side=None):
    """'1438 Buttonbush Dr', 'buyer' -> '1438-Buttonbush-Dr.buyer.cma.json'. The side keeps a buyer and a seller CMA
    of the same address from overwriting each other (CMA-17)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", address).strip("-")
    return f"{slug or 'property'}{'.' + side if side else ''}.cma.json"
