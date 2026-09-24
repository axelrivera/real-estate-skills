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
import re
from datetime import date

COMMISSION_NOTE = "Commissions are negotiable and not set by law."
SINGLE_FAMILY = "single_family"

# Agency guidelines as planning estimates (confirm limits, fees and overlays with the lender).
LOAN_PROGRAMS = {
    "conventional": {"label": "Conventional", "min_down": 0.03, "upfront_fee": 0.0, "annual_mi": 0.005},
    "fha": {"label": "FHA", "min_down": 0.035, "upfront_fee": 0.0175, "annual_mi": 0.0055},
    "va": {"label": "VA", "min_down": 0.0, "upfront_fee": 0.0215, "annual_mi": 0.0},
    "usda": {"label": "USDA", "min_down": 0.0, "upfront_fee": 0.01, "annual_mi": 0.0035},
    "cash": {"label": "Cash", "min_down": 1.0, "upfront_fee": 0.0, "annual_mi": 0.0},
}
ALIASES = {"conv": "conventional"}

# OFR-25: private mortgage insurance by loan-to-value, as a planning estimate (good credit; the lender's quote wins)
PMI_BY_LTV = ((0.95, 0.0075), (0.90, 0.005), (0.85, 0.0035), (0.80, 0.002))  # (LTV above, annual rate)
# VA funding fee (38 U.S.C. 3729): by down payment, first use and later use; waived for exempt veterans
VA_FEE = ((0.10, 0.0125, 0.0125), (0.05, 0.015, 0.015), (0.0, 0.0215, 0.033))  # (down at least, first, later)


def annual_mi_rate(name, down):
    """Annual mortgage insurance as a share of the base loan: PMI by loan-to-value for conventional loans."""
    key = program(name)
    if key != "conventional":
        return LOAN_PROGRAMS[key]["annual_mi"]
    ltv = 1 - down
    return next((rate for above, rate in PMI_BY_LTV if ltv > above + 1e-9), 0.0)


def upfront_fee(name, down, va_later_use=False, va_exempt=False):
    """The financed upfront fee: FHA's premium, USDA's guarantee fee, or the VA funding fee from its table."""
    key = program(name)
    if key != "va":
        return LOAN_PROGRAMS[key]["upfront_fee"]
    if va_exempt:
        return 0.0
    return next(later if va_later_use else first for at_least, first, later in VA_FEE if down >= at_least - 1e-9)


def program(name):
    key = ALIASES.get(str(name).lower(), str(name).lower())
    if key not in LOAN_PROGRAMS:
        raise ValueError(f"Unknown loan program {name!r} (use conventional, fha, va, usda or cash).")
    return key


def property_type(value):
    """'single_family', 'condo', 'townhouse', 'multifamily', 'land' or 'other' from a data file; None when not given."""
    if value in (None, ""):
        return None
    v = " ".join(str(value).lower().replace("_", " ").replace("-", " ").split())
    for key, words in (("condo", ("condo", "condominium")), ("townhouse", ("townhouse", "townhome", "villa")),
                       ("multifamily", ("duplex", "triplex", "fourplex", "multi", "multifamily")),
                       ("land", ("land", "lot", "vacant")), (SINGLE_FAMILY, ("single family", "sfr", "house", "detached"))):
        if any(w in v for w in words):
            return key
    return "other"


def tax_proration(annual_tax, closing, market=None, bill_paid=None):
    """The seller's side of the property tax proration at closing, as {'amount', 'label', 'basis'}, or None.

    FR/BAR Standard K: prorated through the day before closing, allowing the maximum early-payment discount
    (`property_tax.early_payment_discount`, Florida 4%). Taxes paid in arrears (`property_tax.paid`): while the current
    bill is unpaid, the seller credits the buyer from Jan 1 (a cost); once the seller has paid it (Florida bills go out
    in November), the buyer credits the seller from closing to Dec 31 (`amount` negative, a credit to the seller).
    """
    if not annual_tax or not closing:
        return None
    if market is not None and market.get("property_tax.paid") == "advance":
        return None
    discount = (market.get("property_tax.early_payment_discount") if market is not None else None) or 0
    year_days = (date(closing.year + 1, 1, 1) - date(closing.year, 1, 1)).days
    seller_days = (closing - date(closing.year, 1, 1)).days  # Jan 1 through the day before closing
    base = annual_tax * (1 - discount)
    basis = f"{money(annual_tax)} bill" + (f" less the {discount * 100:g}% early-payment discount" if discount else "")
    if bill_paid:
        return {"amount": -round(base * (year_days - seller_days) / year_days),
                "label": "Property Tax Proration (Credit, Closing to Dec 31)", "basis": basis}
    return {"amount": round(base * seller_days / year_days), "label": "Property Tax Proration (Jan 1 to Closing)", "basis": basis}


# CORE-19: states where one flat deed transfer rate can be wrong (graduated rates, mansion taxes, city or county
# layers on top of the state's). A full tiered model is on the roadmap; until then the net warns.
LAYERED_TRANSFER_TAX = {"CA": "city transfer taxes (Los Angeles Measure ULA, San Francisco tiers)",
                        "CT": "a tiered state conveyance tax", "DC": "graduated rates",
                        "HI": "a graduated conveyance tax", "IL": "state, county and city layers (Chicago)",
                        "MD": "state and county layers", "NJ": "a graduated realty transfer fee and mansion tax",
                        "NY": "the mansion tax and New York City's rates", "PA": "state and local layers (Philadelphia)",
                        "VT": "graduated rates for a primary residence", "WA": "graduated REET tiers"}


def transfer_tax_warning(market):
    """A sentence when the market's state has tiered or layered transfer taxes, else None."""
    st = getattr(market, "state", None)
    if st in LAYERED_TRANSFER_TAX:
        return (f"Transfer taxes here can be tiered or layered ({LAYERED_TRANSFER_TAX[st]}), and the net uses one flat "
                "rate: confirm the amount with the title or escrow company for this price.")
    return None


PAYOFF_INTEREST = 0.045  # seller's mortgage interest for holding-cost estimates (national planning figure)


def holding_monthly(price, market, payoff=0, hoa_monthly=0):
    """A seller's monthly cost of owning the home while it's for sale: loan interest, HOA, insurance and utilities
    from the market's `holding_costs`. Property tax is left out: it's in the tax proration already (OFR-13).
    Returns (monthly, [names of parts the market doesn't have])."""
    ins_rate = market.get("holding_costs.insurance_rate") if market is not None else None
    utilities = market.get("holding_costs.utilities_monthly") if market is not None else None
    parts, left_out = [hoa_monthly or 0, (payoff or 0) * PAYOFF_INTEREST / 12], []
    if ins_rate is None:
        left_out.append("insurance")
    else:
        parts.append(price * ins_rate / 12)
    if utilities is None:
        left_out.append("utilities")
    else:
        parts.append(utilities)
    return sum(parts), left_out


def months_in(text):
    """'45–90 days' -> 2.2, '3–6 weeks' -> 1.0, '2 months' -> 2.0: the midpoint of a time range, in months (None if
    there's no number)."""
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(text or ""))]
    if not nums:
        return None
    t = str(text).lower()
    per = 1 / 30.44 if "day" in t else 7 / 30.44 if "week" in t else 1.0
    return round(sum(nums[:2]) / len(nums[:2]) * per, 2)


def loan_taxes(loan, market):
    """Taxes on a buyer's loan from the market layer (`buyer_costs.loan_taxes`: [{label, rate}] on the loan amount;
    Florida: note stamps 0.35% and intangible tax 0.2%). [] for a cash purchase or a market without them."""
    rows = (market.get("buyer_costs.loan_taxes") if market is not None else None) or []
    return [{"label": r["label"], "rate": r["rate"], "amount": round(loan * r["rate"])} for r in rows if loan and r.get("rate")]


def loan_limit_note(loan, name, limits, state=None, county=None):
    """OFR-11: a sentence when the loan is over (or may be over) its program's limit, else None. `limits` is
    profiles.loan_limits(); county limits above the baseline come from its `counties` table."""
    key = program(name)
    if not loan or key not in ("conventional", "fha") or not limits:
        return None
    year = limits.get("year", "")
    own = ((limits.get("counties") or {}).get(state or "") or {}).get(str(county or "").removesuffix(" County"), {})
    if key == "conventional":
        cap = own.get("conforming") or limits["conforming"]["baseline"]
        if loan <= cap:
            return None
        if loan > limits["conforming"]["ceiling"] or own.get("conforming") or state == "FL":
            return (f"The {money(loan)} loan is above the {year} conforming limit here ({money(cap)}): a jumbo loan, with "
                    "its own rates, down payment and reserves. Confirm with the lender.")
        return (f"The {money(loan)} loan is above the {year} baseline conforming limit ({money(cap)}): jumbo unless the "
                "county is high-cost. Confirm the county limit with the lender.")
    cap = own.get("fha")
    if cap and loan > cap or loan > limits["fha"]["ceiling"]:
        return f"The {money(loan)} FHA loan is above the {year} FHA limit here ({money(cap or limits['fha']['ceiling'])}): it can't be FHA."
    if not cap and loan > limits["fha"]["floor"]:
        return (f"The {money(loan)} FHA loan is above the {year} FHA floor ({money(limits['fha']['floor'])}): confirm the "
                "county's FHA limit with the lender.")
    return None


def buyer_broker_shortfall(price, agreement_pct, seller_pays_pct):
    """What the buyer owes their own broker when the seller pays less than the buyer-broker agreement (after the 2024
    NAR settlement): (agreement − seller-paid) × price, never below 0. None when the agreement isn't known."""
    if agreement_pct is None:
        return None
    return max(0, round((agreement_pct - (seller_pays_pct or 0)) * price))


def money(v, round_to=1):
    """$474,900. Negative amounts as −$1,200."""
    v = round(v / round_to) * round_to
    return ("−" if v < 0 else "") + f"${abs(v):,.0f}"


def fraction(value, name, default=None, whole=False):
    """A share of price from a data file, as a fraction: 0.025 means 2.5%.

    Every `*_pct` field in the skills' data files is a fraction (like the market profile). A value of 1 or more
    is almost always a percent written the other way (2.5 for 2.5%), so it's refused with a plain message
    instead of silently becoming 250%. `whole=True` also accepts exactly 1 (a cash buyer's 100% down).
    """
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} should be a share of price like 0.025 (for 2.5%).")
    if whole and value == 1:
        return value
    if value >= 1:
        raise ValueError(f"{name} is {value:g}: write it as a fraction, {value / 100:g} for {value:g}%.")
    return value


def concession_cap(name, down):
    """Most a seller may contribute, as a share of price. `down` is a fraction (0.05 = 5%)."""
    key = program(name)
    if key in ("fha", "usda"):
        return 0.06
    if key == "va":
        return 0.04  # concessions; normal closing costs are allowed on top
    if key == "cash":
        return None
    # Conventional limits go by LTV: over 90% → 3%, 75.01–90% → 6%, 75% or less → 9% (so exactly 25% down is 9%).
    return 0.03 if down < 0.10 else 0.06 if down < 0.25 else 0.09


def pi_payment(loan, annual_rate_pct, years=30):
    """Monthly principal and interest. `annual_rate_pct` in percent (6.95)."""
    m = annual_rate_pct / 100 / 12
    n = years * 12
    return loan / n if m == 0 else loan * m / (1 - (1 + m) ** -n)


def loan_amount(price, name, down, va_later_use=False, va_exempt=False):
    key = program(name)
    if key == "cash":
        return 0.0
    return price * (1 - down) * (1 + upfront_fee(key, down, va_later_use, va_exempt))


def monthly_payment(price, name, down, rate_pct, tax_annual, insurance_annual, hoa_monthly=0.0, mi_rate=None,
                    flood_annual=None, va_later_use=False, va_exempt=False):
    """Monthly payment breakdown. Conventional mortgage insurance only below 20% down.

    `flood_annual` is a flood insurance quote; without one `flood` is None and the total leaves it out (the report
    says "get a quote", never $0: see flood_insurance)."""
    key = program(name)
    base = price * (1 - down)
    loan = loan_amount(price, key, down, va_later_use, va_exempt)
    rate_mi = annual_mi_rate(key, down) if mi_rate is None else mi_rate
    mi = 0.0 if key == "cash" or (key == "conventional" and down >= 0.20) else base * rate_mi / 12
    pi = 0.0 if key == "cash" else pi_payment(loan, rate_pct)
    tax, ins = tax_annual / 12, insurance_annual / 12
    flood = flood_annual / 12 if flood_annual is not None else None
    return {"cash_down": price * down if key != "cash" else price, "loan": loan, "pi": pi, "tax": tax,
            "ins": ins, "mi": mi, "hoa": hoa_monthly, "flood": flood, "total": pi + tax + ins + mi + hoa_monthly + (flood or 0)}


SFHA = ("A", "V")  # FEMA Special Flood Hazard Areas: A, AE, AH, AO, AR, A99, V, VE


def flood_insurance(zone, quote=None, market=None, as_of=None, condo_unit=False):
    """The flood insurance line of a buyer's payment: {"annual", "sfha", "required", "note"}.

    `annual` is the quote or None (never 0: a missing quote reads "get a quote"). `required` is "lender" in a
    Special Flood Hazard Area, "citizens" when the market's Citizens rule reaches every policy on `as_of`, "citizens_value"
    when it applies above a replacement cost, else None. The note is one or two sentences for the report."""
    m = re.match(r"(?:ZONE\s+)?([A-Z]{1,2}\d{0,3})\b", str(zone or "").strip().upper())  # "X (lower risk)" -> X
    z = m.group(1) if m else ""
    known = bool(z) and z not in ("TBD", "D", "UNK")  # D: undetermined risk
    sfha = known and z[:1] in SFHA
    annual = quote if quote not in (None, "", 0) else None
    tail = "" if annual is not None else " Get a quote; the total leaves it out until then."
    if sfha:
        return {"annual": annual, "sfha": True, "required": "lender",
                "note": f"Flood zone {z} is a Special Flood Hazard Area: the lender will require flood insurance.{tail}"}
    rule = (market.get("flood.citizens_requirement") if market is not None else None) or {}
    day = (as_of or date.today()).isoformat()
    tiers = [t for t in rule.get("schedule") or [] if str(t.get("from")) <= day]
    tier = max(tiers, key=lambda t: str(t["from"])) if tiers else None
    where = f"Flood zone {z}" if known else "The flood zone isn't confirmed (check the FEMA flood map)"
    if tier is None or condo_unit:
        extra = " A condo unit (HO-6) policy is exempt from the Citizens flood requirement." if tier and condo_unit else ""
        return {"annual": annual, "sfha": False, "required": None,
                "note": f"{where}: a lender doesn't require flood insurance{' here' if known else ' outside a high-risk zone'}.{extra}{tail}"}
    cite = rule.get("statute", "state law")
    if not tier.get("min_replacement_cost"):
        need, required = "every Citizens policy must carry flood insurance", "citizens"
    else:
        later = [t for t in rule["schedule"] if str(t.get("from")) > day and not t.get("min_replacement_cost")]
        need = (f"a Citizens policy on a home with a dwelling replacement cost of {money(tier['min_replacement_cost'])} or "
                f"more must carry flood insurance" + (f", and every Citizens policy from {_long_date(later[0]['from'])}" if later else ""))
        required = "citizens_value"
    return {"annual": annual, "sfha": False, "required": required,
            "note": f"{where}: a lender may not require flood insurance, but {need} ({cite}).{tail}"}


def _long_date(iso):
    d = date.fromisoformat(str(iso))
    return f"{d:%B} {d.day}, {d.year}"


def buydown_2_1(loan, rate_pct):
    """Cost and payments of a temporary 2-1 buydown."""
    full, y1, y2 = pi_payment(loan, rate_pct), pi_payment(loan, rate_pct - 2), pi_payment(loan, rate_pct - 1)
    return {"cost": 12 * (full - y1) + 12 * (full - y2), "year1": y1, "year2": y2, "full": full}


# --- property tax -------------------------------------------------------------

def property_tax(value, market=None, school_mills=None, total_mills=None, homestead=True):
    """Annual tax for a buyer at `value`: {'annual', 'basis', 'estimated'}.

    With millage, exemptions come from the market profile: each is an `amount` or a `percent` of value
    (0.20 = 20%), optionally only on value `above` a threshold, and `levies` says what it lowers: `all`, `non_school` (all but school) or `school` (school
    only, as in Texas). Without millage, the market's fallback rate is used and marked `estimated`.
    With neither, `annual` is None.
    """
    if total_mills is not None:
        school = school_mills or 0.0
        off = {"school": 0.0, "other": 0.0}
        if homestead and market is not None:
            for ex in market.get("property_tax.primary_residence_exemptions") or []:
                amount = ex["amount"] if ex.get("amount") is not None else value * (ex.get("percent") or 0)
                if ex.get("above"):  # applies only to value above a threshold (Florida's second $25,000, indexed)
                    amount = min(amount, max(0, value - ex["above"]))
                levies = ex.get("levies", "all")
                if levies in ("all", "school"):
                    off["school"] += amount
                if levies in ("all", "non_school"):
                    off["other"] += amount
        school_taxable = max(value - off["school"], 0)
        other_taxable = max(value - off["other"], 0)
        annual = (school_taxable * school + other_taxable * (total_mills - school)) / 1000
        basis = f"{total_mills:.4f} mills" + (", with homestead" if homestead and any(off.values()) else "")
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
               has_hoa=False, other_costs=0, title_fees=None, annual_tax=None, closing=None, bill_paid=None,
               prop_type=None):
    """Seller's estimated net at `price`, itemized, with the source of every assumption.

    Returns {'items': [(label, amount)], 'lines': [{'key', 'label', 'amount', 'rate'}], 'total_costs',
    'net_before_payoff', 'net', 'missing', 'assumed'}. `lines` carries stable keys (listing_fee, buyer_broker_fee,
    transfer_tax, owner_title, title_fees, estoppel, credit, other) so reports can use their own wording.
    `missing` lists market values that weren't available (the output should be marked Preliminary);
    `assumed` lists defaults taken from the market profile rather than the agent, as
    {'key', 'value', 'text'} (key: listing_fee, buyer_broker_fee, title_fees). `warnings` are sentences to show the
    agent (a title quote below the published rate).
    A saved owner's title quote (`closing_costs.owner_title.quote`: {price, premium}) wins over the rate table.
    `title_fees` (a total, or {name: amount} from a title company quote) replaces the market's seller_title_fees.
    `annual_tax` with `closing` (a date) adds the tax proration (see tax_proration; `bill_paid` once the seller paid
    this year's bill). `prop_type` decides a transfer surtax that skips some property types (Miami-Dade: every type
    but single-family homes); without it, that surtax is missing.
    """
    items, lines, missing, assumed, warnings = [], [], [], [], []

    def add(key, label, amount, rate=None):
        items.append((label, amount))
        lines.append({"key": key, "label": label, "amount": amount, "rate": rate})

    def market_value(path, label):
        v = market.get(path) if market is not None else None
        if v is None:
            missing.append(label)
        return v

    lf = listing_fee_pct if listing_fee_pct is not None else market_value("brokerage.listing_fee_pct", "listing fee")
    bf = buyer_broker_fee_pct if buyer_broker_fee_pct is not None else market_value("brokerage.buyer_broker_fee_pct", "buyer's agent fee")
    if listing_fee_pct is None and lf is not None:
        assumed.append({"key": "listing_fee", "value": lf, "text": f"listing fee {lf * 100:g}%"})
    if buyer_broker_fee_pct is None and bf is not None:
        assumed.append({"key": "buyer_broker_fee", "value": bf, "text": f"buyer's agent fee {bf * 100:g}%"})
    if lf:
        add("listing_fee", f"Listing Brokerage ({lf * 100:g}%)", price * lf, lf)
    if bf:
        add("buyer_broker_fee", f"Buyer's Agent ({bf * 100:g}%)", price * bf, bf)

    rate = market_value("closing_costs.deed_transfer_tax_rate", "deed transfer tax")
    if transfer_tax_warning(market):
        warnings.append(transfer_tax_warning(market))
    payer = market.get("closing_costs.deed_transfer_tax_payer") if market is not None else None
    tax_label = (market.get("closing_costs.deed_transfer_tax_label") if market is not None else None) or "Deed Transfer Tax"
    if rate and payer in (None, "seller"):
        add("transfer_tax", f"{tax_label} ({rate * 100:.2f}%)", price * rate, rate)
    elif rate and payer == "split":
        add("transfer_tax", f"{tax_label} (Half of {rate * 100:.2f}%)", price * rate / 2, rate / 2)
    surtax = market.get("closing_costs.deed_transfer_surtax") if market is not None else None
    if surtax and surtax.get("rate") and payer in (None, "seller"):
        kind = property_type(prop_type)
        if kind is None:
            missing.append("property type (for the " + (surtax.get("label") or "deed surtax") + ")")
        elif kind != surtax.get("applies_unless"):
            add("transfer_surtax", f"{surtax.get('label') or 'Deed Surtax'} ({surtax['rate'] * 100:.2f}%)",
                price * surtax["rate"], surtax["rate"])

    title_payer = market_value("closing_costs.owner_title.payer", "who pays owner's title")
    if title_payer == "seller":
        tiers = market.get("closing_costs.owner_title.rate_tiers")
        pct = market.get("closing_costs.owner_title.estimate_pct")
        quote = market.get("closing_costs.owner_title.quote")  # {price, premium} from a title company
        if quote and quote.get("price") and quote.get("premium"):  # CORE-9: a quote wins over the table
            amount = round(quote["premium"] * price / quote["price"]) if quote["price"] != price else quote["premium"]
            add("owner_title", "Owner's Title Insurance (Quote)", amount)
            floor = title_premium(price, tiers) if tiers else None
            if floor and amount < floor - 1:  # a promulgated rate is the legal premium: a lower quote is a misread
                warnings.append(f"The owner's title quote ({money(amount)} at this price) is below the published rate "
                                f"({money(floor)}): check the quote with the title company.")
        elif tiers:  # the published rate table
            add("owner_title", "Owner's Title Insurance", title_premium(price, tiers))
        elif pct:
            add("owner_title", "Owner's Title Insurance (Estimate)", price * pct, pct)
        else:
            missing.append("owner's title rate")

    if title_fees is not None:
        add("title_fees", "Title Company Fees", sum(title_fees.values()) if isinstance(title_fees, dict) else title_fees)
    else:
        fees = market.get("closing_costs.seller_title_fees") if market is not None else None
        if fees:
            add("title_fees", "Title Company Fees", sum(fees.values()))
            if market.source("closing_costs.seller_title_fees") not in ("profile", "deal"):  # a built-in default
                assumed.append({"key": "title_fees", "value": sum(fees.values()), "text": "typical title company fees"})
        else:
            missing.append("title company fees")
    if has_hoa:
        estoppel = market_value("closing_costs.hoa_estoppel_fee", "HOA estoppel fee")
        if estoppel:
            add("estoppel", "HOA Estoppel Letter", estoppel)
    if credit:
        add("credit", "Seller Credit to Buyer", credit)
    if other_costs:
        add("other", "Other Costs", other_costs)
    pr = tax_proration(annual_tax, closing, market, bill_paid)
    if pr:
        add("tax_proration", pr["label"], pr["amount"])

    total = sum(a for _, a in items)
    net_before = price - total
    return {"items": items, "lines": lines, "total_costs": total, "net_before_payoff": net_before,
            "net": None if payoff is None else net_before - payoff,
            "missing": missing, "assumed": assumed, "warnings": warnings}
