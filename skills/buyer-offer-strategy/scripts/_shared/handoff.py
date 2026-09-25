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


class HandoffError(ValueError):
    """The handoff can't be used; the message says why in plain words."""


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
    """'517 Hickorywood Ave', 'buyer' -> '517-Hickorywood-Ave.buyer.cma.json'. The side keeps a buyer and a seller CMA
    of the same address from overwriting each other (CMA-17)."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", address).strip("-")
    return f"{slug or 'property'}{'.' + side if side else ''}.cma.json"
