"""Which contract rules apply to which form, in one place.

    from _shared import contract_forms as cf
    form = cf.normalize("AS IS")               # 'as_is' | 'standard' | 'other' | None (not given)
    cf.inspection_walkaway(form, offer)        # True when the buyer may cancel for any reason in the period
    cf.repair_limits(price, offer)             # Standard only: {'general', 'wdo', 'permit'} in dollars

The FR/BAR AS IS and Standard contracts differ in Para. 12 and 9(a) (see
docs/audits/2026-09-23-verification.md), so their math never mixes:

- AS IS: the inspection period is a walk-away right; the seller has no repair obligation, so a seller's
  downside reserves the market's typical post-inspection credit.
- Standard: no walk-away right; the inspection period is the deadline for repair notices, and the seller owes
  repairs up to the General Repair, WDO and Permit Limits (1.5% of price each when blank). The buyer or seller
  may terminate only when repairs exceed a limit, after the seller's estimates (10 days) and the election (5 days).
- Any other contract ('other'): none of the FR/BAR figures apply; its own walk-away rule comes from the
  file (`inspection_walkaway`, true for a Texas option period or a due-diligence period).
"""

AS_IS, STANDARD, OTHER = "as_is", "standard", "other"
FRBAR = (AS_IS, STANDARD)
REPAIR_LIMIT_DEFAULT = 0.015  # Para. 9(a): 1.5% of the price for each limit when blank
REPAIR_LIMIT_KEYS = ("general", "wdo", "permit")
STANDARD_REPAIR_WINDOW_DAYS = 15  # after the repair notice: the seller's estimates (10 days), then the election (5 days)

_ALIASES = {  # compared lowercase, with "_" and "-" read as spaces
    "as is": AS_IS, "asis": AS_IS, "asis 7": AS_IS, "fr/bar as is": AS_IS,
    "as is residential contract for sale and purchase": AS_IS,
    "standard": STANDARD, "crsp": STANDARD, "fr/bar standard": STANDARD,
    "residential contract for sale and purchase": STANDARD,
}


class FormError(ValueError):
    """A contract form value that can't be read; the message is written for the agent."""


def normalize(value):
    """'as_is', 'standard' or 'other' from a data file's contract_form; None when it isn't given."""
    if value in (None, ""):
        return None
    return _ALIASES.get(" ".join(str(value).lower().replace("_", " ").replace("-", " ").split()), OTHER)


def frbar_market(forms):
    """True when a market's built-in contract rules are the FR/BAR forms' (Florida)."""
    return any(str(f).upper().startswith("FR/BAR") for f in forms or [])


def inspection_walkaway(form, item=None):
    """True when the buyer may cancel for any reason during the inspection period.

    AS IS: yes. Standard: no (repair notices only). Another contract: the file's `inspection_walkaway`, which
    defaults to true (an option or due-diligence period)."""
    if form == AS_IS:
        return True
    if form == STANDARD:
        return False
    return (item or {}).get("inspection_walkaway", True) is not False


def repair_limits(price, item=None):
    """Standard contract repair limits in dollars. `repair_limits` in the file may give each as dollars (6000)
    or a share of price (0.02); a blank one is the form's 1.5%."""
    given = (item or {}).get("repair_limits") or {}
    out = {}
    for key in REPAIR_LIMIT_KEYS:
        v = given.get(key)
        if v is None:
            v = REPAIR_LIMIT_DEFAULT
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise FormError(f"repair_limits.{key} should be dollars (6000) or a share of price (0.015 for 1.5%).")
        out[key] = round(v * price) if v < 1 else round(v)
    return out
