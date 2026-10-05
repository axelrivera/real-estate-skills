"""Named categories the model picks and the script turns into numbers (a pricing stance, an offer posture, a counter
stance, a priority). One check for all of them, so an unknown value always stops the run the same way.

    from _shared import choices
    stance, problems = choices.pick(data.get("stance"), ("draw_offers", "market", "premium"), "pricing.stance",
                                    default="market")

A missing value (None or "") takes the default. Spaces, hyphens and letter case are forgiven ("Draw offers" is
draw_offers). Anything else is a problem in the skills' `field: problem → fix` form naming every allowed value, and
the default is returned so the caller can collect every problem before stopping.
"""


def norm(value):
    """A category as typed, normalized: lower case, spaces and hyphens as underscores."""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def pick(value, allowed, field, default=None):
    """(value, problems): the allowed category `value` names, or `default` when it's missing. `allowed` keeps its
    order in the fix message. A value that isn't allowed returns the default and one problem."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default, []
    if isinstance(value, bool):
        key = None
    elif isinstance(value, int) and value in allowed:
        return value, []
    else:
        key = norm(value)
    by_key = {norm(a): a for a in allowed}
    if key in by_key:
        return by_key[key], []
    options = ", ".join(str(a) for a in allowed)
    tail = f" (or leave it out for {default})" if default is not None else ""
    return default, [f"{field}: {value!r} isn't one of the choices → use one of {options}{tail}."]
