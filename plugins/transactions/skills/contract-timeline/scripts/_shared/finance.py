"""Money math shared by the CMAs and offer skills: payments, loan programs, property tax, title, seller net.

    from _shared import finance
    p = finance.monthly_payment(474900, "conventional", 0.05, 6.95, tax_annual=7596, insurance_annual=3600)
    tax = finance.property_tax(474900, market, school_mills=5.249, total_mills=17.5683)
    net = finance.seller_net(465000, market, credit=10000, payoff=210000)

Market-specific values (transfer tax, title, fees, commissions, exemptions, millage) come from the
market profile (shared/profiles.load_market). Lending rules are national estimates: the lender's
numbers always win.
"""
import math

# Agency guidelines as planning estimates (confirm limits, fees and overlays with the lender).
LOAN_PROGRAMS = {
    "conventional": {"label": "Conventional", "min_down": 0.03, "upfront_fee": 0.0, "annual_mi": 0.005},
    "fha": {"label": "FHA", "min_down": 0.035, "upfront_fee": 0.0175, "annual_mi": 0.0055},
    "va": {"label": "VA", "min_down": 0.0, "upfront_fee": 0.0215, "annual_mi": 0.0},
    "usda": {"label": "USDA", "min_down": 0.0, "upfront_fee": 0.01, "annual_mi": 0.0035},
    "cash": {"label": "Cash", "min_down": 1.0, "upfront_fee": 0.0, "annual_mi": 0.0},
}
ALIASES = {"conv": "conventional"}


def program(name):
    key = ALIASES.get(str(name).lower(), str(name).lower())
    if key not in LOAN_PROGRAMS:
        raise ValueError(f"Unknown loan program {name!r} (use conventional, fha, va, usda or cash).")
    return key


def money(v, round_to=1):
    """$474,900. Negative amounts as −$1,200."""
    v = round(v / round_to) * round_to
    return ("−" if v < 0 else "") + f"${abs(v):,.0f}"


def concession_cap(name, down):
    """Most a seller may contribute, as a share of price. `down` is a fraction (0.05 = 5%)."""
    key = program(name)
    if key in ("fha", "usda"):
        return 0.06
    if key == "va":
        return 0.04  # concessions; normal closing costs are allowed on top
    if key == "cash":
        return None
    return 0.03 if down < 0.10 else 0.06 if down < 0.25 else 0.09


def pi_payment(loan, annual_rate_pct, years=30):
    """Monthly principal and interest. `annual_rate_pct` in percent (6.95)."""
    m = annual_rate_pct / 100 / 12
    n = years * 12
    return loan / n if m == 0 else loan * m / (1 - (1 + m) ** -n)


def loan_amount(price, name, down):
    key = program(name)
    if key == "cash":
        return 0.0
    return price * (1 - down) * (1 + LOAN_PROGRAMS[key]["upfront_fee"])


def monthly_payment(price, name, down, rate_pct, tax_annual, insurance_annual, hoa_monthly=0.0, mi_rate=None):
    """Monthly payment breakdown. Conventional mortgage insurance only below 20% down."""
    key = program(name)
    base = price * (1 - down)
    loan = loan_amount(price, key, down)
    rate_mi = LOAN_PROGRAMS[key]["annual_mi"] if mi_rate is None else mi_rate
    mi = 0.0 if key == "cash" or (key == "conventional" and down >= 0.20) else base * rate_mi / 12
    pi = 0.0 if key == "cash" else pi_payment(loan, rate_pct)
    tax, ins = tax_annual / 12, insurance_annual / 12
    return {"cash_down": price * down if key != "cash" else price, "loan": loan, "pi": pi, "tax": tax,
            "ins": ins, "mi": mi, "hoa": hoa_monthly, "total": pi + tax + ins + mi + hoa_monthly}


def buydown_2_1(loan, rate_pct):
    """Cost and payments of a temporary 2-1 buydown."""
    full, y1, y2 = pi_payment(loan, rate_pct), pi_payment(loan, rate_pct - 2), pi_payment(loan, rate_pct - 1)
    return {"cost": 12 * (full - y1) + 12 * (full - y2), "year1": y1, "year2": y2, "full": full}


# --- property tax -------------------------------------------------------------

def property_tax(value, market=None, school_mills=None, total_mills=None, homestead=True):
    """Annual tax for a buyer at `value`: {'annual', 'basis', 'estimated'}.

    With millage, exemptions come from the market profile (`levies: all` lowers every levy,
    `non_school` lowers all but school). Without millage, the market's fallback rate is used and
    marked `estimated`. With neither, `annual` is None.
    """
    if total_mills is not None:
        school = school_mills or 0.0
        all_ex = non_school_ex = 0.0
        if homestead and market is not None:
            for ex in market.get("property_tax.primary_residence_exemptions") or []:
                if ex.get("levies") == "all":
                    all_ex += ex["amount"]
                elif ex.get("levies") == "non_school":
                    non_school_ex += ex["amount"]
        school_taxable = max(value - all_ex, 0)
        other_taxable = max(value - all_ex - non_school_ex, 0)
        annual = (school_taxable * school + other_taxable * (total_mills - school)) / 1000
        basis = f"{total_mills:.4f} mills" + (", with homestead" if homestead and (all_ex or non_school_ex) else "")
        return {"annual": annual, "basis": basis, "estimated": False}
    rate = market.get("property_tax.fallback_rate") if market is not None else None
    if rate:
        return {"annual": value * rate, "basis": f"about {rate * 100:.1f}% of price", "estimated": True}
    return {"annual": None, "basis": "no millage or tax rate for this market", "estimated": True}


def millage(market, county=None, district=None):
    """Millage entries from the market profile, filtered by county and/or a district name fragment."""
    rows = market.get("property_tax.millage") or []
    if county:
        c = county.strip().lower().removesuffix(" county")
        rows = [r for r in rows if str(r.get("county", "")).lower() == c]
    if district:
        rows = [r for r in rows if district.lower() in str(r.get("district", "")).lower()]
    return rows


# --- seller side --------------------------------------------------------------

def title_premium(price, tiers):
    """Promulgated-style tiered premium: [{up_to, per_1000}], last up_to None."""
    premium, lower = 0.0, 0
    for tier in tiers:
        upper = tier.get("up_to") or math.inf
        if price > lower:
            premium += (min(price, upper) - lower) * tier["per_1000"] / 1000
        lower = upper
    return round(premium)


def seller_net(price, market, credit=0, payoff=None, listing_fee_pct=None, buyer_broker_fee_pct=None,
               has_hoa=False, other_costs=0):
    """Seller's estimated net at `price`, itemized, with the source of every assumption.

    Returns {'items': [(label, amount)], 'total_costs', 'net_before_payoff', 'net', 'missing', 'assumed'}.
    `missing` lists market values that weren't available (the output should be marked Preliminary);
    `assumed` lists defaults taken from the market profile rather than the agent.
    """
    items, missing, assumed = [], [], []

    def market_value(path, label):
        v = market.get(path) if market is not None else None
        if v is None:
            missing.append(label)
        return v

    lf = listing_fee_pct if listing_fee_pct is not None else market_value("brokerage.listing_fee_pct", "listing fee")
    bf = buyer_broker_fee_pct if buyer_broker_fee_pct is not None else market_value("brokerage.buyer_broker_fee_pct", "buyer's agent fee")
    if listing_fee_pct is None and lf is not None:
        assumed.append(f"listing fee {lf * 100:g}%")
    if buyer_broker_fee_pct is None and bf is not None:
        assumed.append(f"buyer's agent fee {bf * 100:g}%")
    if lf:
        items.append((f"Listing brokerage ({lf * 100:g}%)", price * lf))
    if bf:
        items.append((f"Buyer's agent ({bf * 100:g}%)", price * bf))

    rate = market_value("closing_costs.deed_transfer_tax_rate", "deed transfer tax")
    payer = market.get("closing_costs.deed_transfer_tax_payer") if market is not None else None
    if rate and payer in (None, "seller"):
        items.append(("Deed transfer tax", price * rate))
    elif rate and payer == "split":
        items.append(("Deed transfer tax (half)", price * rate / 2))

    title_payer = market_value("closing_costs.owner_title.payer", "who pays owner's title")
    if title_payer == "seller":
        tiers = market.get("closing_costs.owner_title.rate_tiers")
        pct = market.get("closing_costs.owner_title.estimate_pct")
        if tiers:
            items.append(("Owner's title insurance", title_premium(price, tiers)))
        elif pct:
            items.append(("Owner's title insurance (estimate)", price * pct))
        else:
            missing.append("owner's title rate")

    fees = market.get("closing_costs.seller_title_fees") if market is not None else None
    if fees:
        items.append(("Title company fees", sum(fees.values())))
    else:
        missing.append("title company fees")
    if has_hoa:
        estoppel = market_value("closing_costs.hoa_estoppel_fee", "HOA estoppel fee")
        if estoppel:
            items.append(("HOA estoppel letter", estoppel))
    if credit:
        items.append(("Seller credit to buyer", credit))
    if other_costs:
        items.append(("Other costs", other_costs))

    total = sum(a for _, a in items)
    net_before = price - total
    return {"items": items, "total_costs": total, "net_before_payoff": net_before,
            "net": None if payoff is None else net_before - payoff,
            "missing": missing, "assumed": assumed}
