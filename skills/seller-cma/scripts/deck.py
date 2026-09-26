"""Listing presentation: slide data from compute.py's numbers, the node builder, and chart styling.

    D = deck.deck_data(R, C, homes, agent, L, footer)   # every number the slides show, already computed
    deck.build_pptx(D, "out.pptx")                       # node scripts/build_deck.js, then style_scatter()
    deck.pptx_to_pdf("out.pptx", "out.pdf")              # LibreOffice copy of the slides, or None

build_deck.js only lays out what it is given: it never computes a price, net or payment, and it has no
colors of its own (they come from shared/design, starting from the agent's brand).
"""
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta

from _shared import cma, design, finance, mls, render

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDER = os.path.join(HERE, "build_deck.js")
money, k = finance.money, lambda v: finance.money(v / 1000) + "K"

REQUIRED = {"title": str, "subtitle": str, "recommendation_why": str, "value_drivers": list, "document_items": list,
            "comp_lines": dict, "comps_takeaway": str, "scatter_takeaway": str, "market_stats": list, "market_takeaway": str,
            "competition": list, "competition_takeaway": str, "strategy_takeaway": str, "payment_takeaway": str,
            "launch_plan": list, "needs_short": list, "timeline": list}
COUNTS = {"value_drivers": (2, 4), "document_items": (0, 2), "market_stats": (2, 4), "launch_plan": (3, 6), "timeline": (2, 5),
          "competition": (1, 3), "needs_short": (1, 5)}  # (fewest, most): never pad a slide to reach a count
# Icons an item can name as its last element ("pool", "kitchen"...), so the picture matches this home, not the sample.
# Features and process only, never people (fair housing).
ICONS = {"kitchen": "FaUtensils", "renovation": "FaHammer", "repairs": "FaWrench", "tools": "FaTools", "paint": "FaPaintRoller",
         "pool": "FaSwimmingPool", "bedroom": "FaBed", "bath": "FaBath", "water": "FaWater", "waterfront": "FaUmbrellaBeach",
         "view": "FaEye", "parking": "FaCar", "garage": "FaWarehouse", "lot": "FaTree", "yard": "FaLeaf", "location": "FaMapMarkerAlt",
         "size": "FaRulerCombined", "layout": "FaDoorOpen", "building": "FaBuilding", "home": "FaHome", "roof": "FaHome",
         "solar": "FaSun", "energy": "FaBolt", "ac": "FaSnowflake", "heating": "FaThermometerHalf", "security": "FaLock",
         "insurance": "FaShieldAlt", "document": "FaFileAlt", "permit": "FaClipboardCheck", "contract": "FaFileSignature",
         "inspection": "FaSearch", "photos": "FaCamera", "marketing": "FaBullhorn", "sign": "FaSign", "showings": "FaKey",
         "staging": "FaCouch", "cleaning": "FaBroom", "price": "FaTag", "money": "FaHandHoldingUsd", "dollar": "FaDollarSign",
         "percent": "FaPercent", "time": "FaClock", "calendar": "FaCalendarCheck", "trend": "FaChartLine", "chart": "FaChartBar",
         "inventory": "FaLayerGroup", "negotiation": "FaHandshake", "star": "FaStar", "check": "FaCheckCircle"}
# (field, fields before the optional icon, icon when none is named)
ICON_FIELDS = (("value_drivers", 2, "star"), ("document_items", 2, "document"), ("market_stats", 3, "chart"), ("launch_plan", 2, "check"))
NOTE_KEYS = ("recommendation", "method", "drivers", "comps", "scatter", "market", "competition", "strategies", "nets",
             "payments", "launch", "next")


class DeckError(ValueError):
    """The deck can't be built; the message is written for the agent."""


def load_content(R):
    """The deck wording: report.json's `deck` (an object, or a path to a JSON file)."""
    c = R.get("deck")
    if isinstance(c, str):
        if not os.path.exists(c):
            raise DeckError(f"The deck content file {c} doesn't exist (report.json `deck`).")
        with open(c, encoding="utf-8") as f:
            c = json.load(f)
    if not isinstance(c, dict):
        raise DeckError("report.json needs `deck` with the listing presentation's wording (see references/deck-content.md).")
    required = {k: t for k, t in REQUIRED.items() if k != "scatter_takeaway" or R.get("export")}  # no export: no scatter slide
    problems = [f"deck.{key} is missing" for key, typ in required.items() if not isinstance(c.get(key), typ)]
    problems += [f"deck.{key} needs {lo} to {hi} items" for key, (lo, hi) in COUNTS.items()
                 if isinstance(c.get(key), list) and not lo <= len(c[key]) <= hi]
    for key, n, _ in ICON_FIELDS:
        for item in c.get(key) or []:
            if not isinstance(item, list) or len(item) not in (n, n + 1):
                problems.append(f"each deck.{key} item is {n} texts plus an optional icon name")
                break
            if len(item) == n + 1 and item[n] not in ICONS:
                problems.append(f'deck.{key} uses the icon "{item[n]}"; use one of: {", ".join(sorted(ICONS))}')
    if problems:
        raise DeckError("The deck content isn't complete: " + "; ".join(problems) + ".")
    return c


def _fill(value, values):
    """Replace {list_price}-style placeholders in every string of the deck content."""
    if isinstance(value, str):
        return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), m.group(0)), value)
    if isinstance(value, list):
        return [_fill(v, values) for v in value]
    if isinstance(value, dict):
        return {key: _fill(v, values) for key, v in value.items()}
    return value


def _norm(address):
    return " ".join(str(address).upper().replace(".", "").split())


def adjustment_words(cards):
    """'size, larger corner lot, seller credits and market since the sale': the adjustments actually made (CMA-26)."""
    seen = []
    for c in cards:
        for a in c.get("adjustments") or []:
            word = str(a.get("label", "")).strip()
            word = " ".join(w if w.isupper() else w.lower() for w in word.split())
            if word and word not in seen:
                seen.append(word)
    if any(c.get("seller_concessions") for c in cards):
        seen.append("seller credits")
    if not seen:
        return ""
    return seen[0] if len(seen) == 1 else ", ".join(seen[:-1]) + " and " + seen[-1]


def period_labels(window):
    """CMA-25: labels from the actual bounds. A split on the 1st reads as whole months ("April–June", "July–September");
    a mid-month split shows the day, so no days are dropped ("April–July 14", "July 15–September")."""
    split = datetime.strptime(window["split_date"], "%Y-%m-%d")
    before = split - timedelta(days=1)
    y = _two_years(window)  # a window across New Year names the years, so "November–January" can't be misread
    first, last = _month(window["first_close"], y), _month(window["last_close"], y)
    b, a = f'{before:%B}' + (f' {before.year}' if y else ""), f'{split:%B}' + (f' {split.year}' if y else "")
    if split.day == 1:
        return [f'{first}–{b}', f'{a}–{last}']
    b, a = f'{before:%B} {before.day}' + (f', {before.year}' if y else ""), f'{split:%B} {split.day}' + (f', {split.year}' if y else "")
    return [f'{first}–{b}', f'{a}–{last}']


def _month(iso, year=False):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%B %Y" if year else "%B")


def _two_years(window):
    return window["first_close"][:4] != window["last_close"][:4]


def scatter_data(homes, R, C, L):
    """Points by category (same rules as the PDF chart), the size-only trend line, and the subject at the list price.
    `series` holds only the non-empty ones, in drawing order, so the legend never lists something the chart doesn't show."""
    s, sc = R["subject"], R.get("scatter") or {}
    homes_by_kind, _, others = cma.scatter_points(homes, sc, s["sqft"], s.get("mls_address", s["address"]),
                                                  [cd["address"] for cd in R["comps"]["cards"]])  # CMA-24
    pts = {kind: [[h["living_area"], h["close_price"] if kind != "active" else h["current_price"]] for h in hs]
           for kind, hs in homes_by_kind.items()}
    fit = mls.trend(others, s["sqft"], sc.get("fit_size_ratio", 1.6))
    xs = [p[0] for v in pts.values() for p in v] + [s["sqft"]]
    trend = []
    if fit:
        x0, x1 = min(xs), max(xs)
        trend = [[x0 + (x1 - x0) * i / 27, fit["intercept"] + fit["slope"] * (x0 + (x1 - x0) * i / 27)] for i in range(28)]
    subject = [[s["sqft"], R["recommendation"]["list_price"]]]
    series = [{"key": key, "name": L(f"deck_series_{key}"), "points": p}
              for key, p in (*pts.items(), ("trend", trend), ("subject", subject)) if p]
    return {"points": pts, "series": series,
            "trend_note": trend_note(fit, R["recommendation"]["list_price"], L),
            "axis_x": L("axis_x"), "axis_y": L("axis_y")}


def trend_note(fit, price, L):
    """The slide's line under the takeaway: what size alone predicts and where the list price sits against it."""
    if not fit:
        return ""
    side, gap = cma.trend_position(price, fit["at_subject"])
    return L("deck_trend_" + side, trend=k(fit["at_subject"]), gap=k(gap))


def deck_data(R, C, homes, agent, L, footer):
    """Everything build_deck.js draws, from report.json (wording) and compute.py's output (numbers)."""
    content = load_content(R)
    rec, s = R["recommendation"], R["subject"]
    pay, net = C["payments"], C["net"]
    values = {"list_price": money(rec["list_price"]), "low": money(rec["low"]), "high": money(rec["high"]),
              "per_10k": pay["per_10k_display"] if pay else "", "median_adjusted": C["median_adjusted_display"],
              "net_spread": C["net_spread_display"], "recommended_net": C["recommended_net_display"],
              "trend_at_subject": C["trend"]["at_subject_display"] if C["trend"] else ""}
    content = _fill(content, values)
    notes = content.get("notes") or {}
    content["notes"] = {key: notes.get(key, "") for key in NOTE_KEYS}

    prices = {_norm(r[0]): r[2] for r in R["competition"]["rows"]}
    cards = []
    for c in content["competition"]:
        if len(c) != 3:
            raise DeckError("Each deck.competition card is [address, status line, why it matters]; the price comes from the report.")
        price = prices.get(_norm(c[0]))
        if price is None:
            raise DeckError(f"deck.competition lists {c[0]}, which isn't in the report's competition table.")
        cards.append([c[0], money(price), c[1], c[2]])

    theme = design.theme(agent.get("brand"), "seller")
    colors = design.pptx_colors(theme)  # the brand's shades and tints, plus black and grays; the deck uses nothing else
    colors.update(contrast_roles(colors))

    window = C.get("window") or {}
    if content.get("sold_line"):
        sold_line = content["sold_line"]
    elif window:
        month = _month(window["first_close"], _two_years(window))
        d = C.get("max_distance")
        if d:
            miles = math.ceil(d * 2) / 2
            sold_line = L("deck_sold_within", month=month, miles=L("deck_mile") if miles == 1 else L("deck_miles", n=f"{miles:g}"))
        else:
            sold_line = L("deck_sold_since", month=month)
    else:
        sold_line = L("deck_sold_reviewed")
    periods = content.get("market_periods")
    if not periods and window:
        periods = period_labels(window)

    L_deck = {key: v for key, v in L.text.items() if key.startswith("deck_")}
    words = adjustment_words(R["comps"]["cards"])
    L_deck["deck_method_note"] = L("deck_method_note", items=words) if words else L("deck_method_note_none")  # CMA-26
    basis = content.get("comps_basis")
    L_deck["deck_step_comps"] = L("deck_step_comps_basis", basis=basis) if basis else L("deck_step_comps")
    k_strats = len(C["strategies"])
    L_deck["deck_strat_title"] = L(f"deck_strat_title_{k_strats}")
    ri = C["recommended_index"]
    expected = R["pricing"]["strategies"][ri]["expected_sale"]
    L_deck["deck_expected_sub"] = content.get("expected_sub") or L(
        "deck_expected_sub" if expected < rec["list_price"] else "deck_expected_sub_at")
    if content.get("scatter_title"):
        L_deck["deck_scatter_title"] = content["scatter_title"]
    program = L("prog_" + pay["loan_type"])
    program = program if program.isupper() else program.lower()  # "FHA", "VA"; "conventional" mid-sentence
    L_deck["deck_pay_sub"] = L("deck_pay_sub", program=program, down=f'{pay["down_pct"] * 100:g}')
    icons = {key: [ICONS[item[n] if len(item) > n else fallback] for item in content.get(key) or []]
             for key, n, fallback in ICON_FIELDS}
    org = " · ".join(str(agent[f]) for f in ("team", "brokerage") if agent.get(f))
    if agent.get("license"):
        org = " · ".join(x for x in (org, f'{L("lic")} {agent["license"]}') if x)
    contact = " · ".join(str(agent[f]) for f in ("phone", "email", "website") if agent.get(f))
    cash, free = net["cash_at_closing"], net["no_mortgage"]
    left_out = [L(key) for key, out in (("deck_ex_payoff", not cash), ("deck_ex_tax", not net["has_tax"]), ("deck_ex_repairs", True)) if out]
    excluded = left_out[0] if len(left_out) == 1 else ", ".join(left_out[:-1]) + " and " + left_out[-1]
    strip = lambda t: re.sub(r"</?strong>", "", t)
    # The appendix slides show only what must be on them (the net sheet's placeholder, commission and preliminary
    # notes; the CMA disclaimer, data source and notices); the full detail goes in the speaker notes.
    net_note = strip(" ".join([L("deck_app_net_note", excluded=excluded)] + net["key_notes"]))
    net_speaker = strip(" ".join(net["notes"] + [L("deck_app_net_note", excluded=excluded)]))
    notices = cma.report_notices(C)
    comps_note = " ".join([L("deck_disclaimer"), notices[0], *render.notice_lines(agent, (), marketing=True)])
    comps_speaker = " ".join(x for x in (content.get("adjustments_summary", ""), L("deck_disclaimer"),
                                         *render.notice_lines(agent, notices, marketing=True)) if x)
    return {
        "colors": colors,
        "labels": L_deck,
        "preliminary": C["preliminary"],
        "agent": {"name": agent.get("name") or "", "lines": [x for x in (org, contact) if x],
                  "short": " · ".join(x for x in (agent.get("name"), agent.get("phone"), agent.get("email")) if x)},
        "footer": footer,
        "prepared_date": R["prepared_date"],
        "address": s["address"],
        "content": content,
        "rec": {"list_price": rec["list_price"], "low": rec["low"], "high": rec["high"],
                "list_display": money(rec["list_price"]), "range_display": f'{k(rec["low"])} – {k(rec["high"])}',
                "low_k": k(rec["low"]), "high_k": k(rec["high"])},
        "expected_sale": content.get("expected_sale") or R["summary_page"]["expected_sale"],
        "method": {"n_sold": C.get("n_sold") or len(R["comps"].get("summary_rows") or R["comps"]["cards"]),"sold_line": sold_line, "n_comps": C["n_comps"],
                   "adj_range": f'{k(C["adjusted_min"])}–{k(C["adjusted_max"])}', "adj_median": C["median_adjusted_display"]},
        "market": {"title": content.get("market_title") or L("deck_market_title"),
                   "subtitle": L("deck_market_sub", early=periods[0], recent=periods[1]) if periods else "",
                   "period_labels": content.get("market_period_labels") or [L("deck_period_early"), L("deck_period_recent")]},
        "comps": [{"address": c["address"], "adjusted": c["adjusted"], "adjusted_k": k(c["adjusted"]),
                   "line": content["comp_lines"].get(c["address"], "")} for c in R["comps"]["cards"]],
        "competition": cards,
        "scatter": scatter_data(homes, R, C, L) if homes else None,
        "strategies": [{"list_price": x["list_price"], "list_display": x["list_price_display"], "label": L("deck_list", price=x["list_price_display"]),
                        "time": x["time"], "expected_display": x["expected_sale_display"], "credit_display": x["seller_credit_display"],
                        "note": x["note"], "net": round(x["net"]), "net_display": x["net_display"],
                        "payment_display": L("deck_per_month", amount=x["payment_display"]),
                        "down_display": L("deck_down", amount=x["down_display"], pct=f'{pay["down_pct"] * 100:g}')} for x in C["strategies"]],
        "recommended_index": C["recommended_index"],
        "icons": icons,
        "net_sub": L("deck_cash_free_sub" if free else "deck_cash_sub" if cash else "deck_net_sub") + (f"; {L('standard_terms_sub')}" if net["standard_terms"] else ""),
        "net_spread_display": C["net_spread_display"],
        "net_rows": [[r["label"]] + r["display"] for r in net["rows"]],
        "net_note": net_note,
        "net_speaker": net_speaker,
        "appendix_comps": [[r[0], money(r[1]), money(r[2]), money(r[3])] for r in R["comps"]["summary_rows"]],
        "subject_row": [R["comps"].get("subject_row_label", L("subject_row")), money(rec["list_price"]), "—",
                        f'{L("range_word")} {k(rec["low"])}–{k(rec["high"])}'],
        "table_head": [L("th_sale"), L("th_sold_for"), L("th_seller_paid"), L("th_adjusted")],
        "net_head": L("th_at_closing"),
        "appendix_note": comps_note,
        "appendix_speaker": comps_speaker,
    }


def contrast_roles(colors):
    """The deck's contrast-checked roles, so a light brand (yellow), a mid one (orange) and a near-black one all work:
    `mark` for chart marks and accent bars (3:1 on white, WCAG for graphics, and apart
    from the black subject marker and the gray other sales), `on_dark` for secondary text on brand_deep (7:1), `on_ink` for secondary text on brand_ink
    fills (4.5:1), and `grey_pale` for the "for sale now" markers."""
    hx = lambda key: "#" + colors[key]
    white, text = hx("bg"), hx("text")
    # The brand itself when it's distinct from the black subject marker and the gray "other sales"; else the first
    # shade or tint of it that is (a gray or near-black brand), else the most distinct one: the marker shapes still differ.
    options = [design.darken_to(c, 3.0) for c in (hx("brand"), hx("brand_ink"), hx("brand_strong"), hx("brand_accent"),
                                                   design.mix_white(hx("brand"), 0.25))]
    gap = lambda c: min(design.distance(c, text), design.distance(c, hx("grey")))
    mark = next((c for c in options if gap(c) >= 0.12), max(options, key=gap))
    def first(options, against, target):
        return next((c for c in options if design.contrast(hx(c), hx(against)) >= target), "bg")
    return {"mark": mark.lstrip("#"),
            "on_dark": colors[first(("brand_soft", "brand_rule"), "brand_deep", 7.0)],
            "on_ink": colors[first(("brand_soft", "brand_rule"), "brand_ink", 4.5)],
            "grey_pale": design.mix_white(hx("grey"), 0.6).lstrip("#")}


# --- node --------------------------------------------------------------------

def node_env():
    """NODE_PATH with any existing value plus the global modules folder, so pptxgenjs, react-icons and sharp resolve."""
    env = dict(os.environ)
    paths = [p for p in env.get("NODE_PATH", "").split(os.pathsep) if p]
    npm = shutil.which("npm")
    if npm:
        try:
            root = subprocess.run([npm, "root", "-g"], capture_output=True, text=True, timeout=30).stdout.strip()
            if root and root not in paths:
                paths.append(root)
        except (OSError, subprocess.SubprocessError):
            pass
    env["NODE_PATH"] = os.pathsep.join(paths)
    return env


def build_pptx(D, path):
    """Write the deck; returns the builder's layout checks (text that doesn't fit its box), one line each."""
    node = shutil.which("node")
    if not node:
        raise DeckError("Node isn't available, so the deck can't be built here. The PDF is unaffected.")
    with tempfile.TemporaryDirectory() as tmp:
        data = os.path.join(tmp, "deck-data.json")
        with open(data, "w", encoding="utf-8") as f:
            json.dump(D, f, ensure_ascii=False)
        r = subprocess.run([node, BUILDER, data, path], capture_output=True, text=True, env=node_env(), timeout=300)
    if r.returncode != 0:
        lines = r.stderr.strip().splitlines() or ["no output"]
        missing = next((re.search(r"Cannot find module '([^']+)'", l) for l in lines if "Cannot find module" in l), None)
        if missing:
            raise DeckError(f"The deck needs the Node module {missing.group(1)}, which isn't available here "
                            "(pptxgenjs, react, react-dom, react-icons and sharp). The PDF is unaffected.")
        raise DeckError("The deck builder failed: " + next((l for l in lines if "Error" in l), lines[-1]).strip())
    if D.get("scatter"):
        style_scatter(path, D["colors"], [ser["key"] for ser in D["scatter"]["series"]])
    return [l[len("Check: "):] for l in r.stderr.splitlines() if l.startswith("Check: ")]


def pptx_to_pdf(pptx, pdf):
    """A PDF copy of the slides through LibreOffice (headless, its own profile). None when it isn't available."""
    office = shutil.which("soffice") or shutil.which("libreoffice")
    if not office:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run([office, "--headless", "--norestore", f"-env:UserInstallation=file://{tmp}/profile",
                            "--convert-to", "pdf", "--outdir", tmp, pptx], capture_output=True, timeout=180)
        except (OSError, subprocess.SubprocessError):
            return None
        made = os.path.join(tmp, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")
        if not os.path.exists(made):
            return None
        shutil.move(made, pdf)
    return pdf


# --- chart styling pptxgenjs can't do ------------------------------------------

def _marker(symbol, size, fill, line, line_w=9525):
    fill_xml = "<a:noFill/>" if fill is None else f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
    return (f'<c:marker><c:symbol val="{symbol}"/><c:size val="{size}"/><c:spPr>{fill_xml}'
            f'<a:ln w="{line_w}"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln></c:spPr></c:marker>')


def _restyle(ser, colors, keys):
    """One scatter series, by its position in `keys` (comp, sold, active, trend, subject; empty ones left out)."""
    idx = re.search(r'<c:idx val="(\d+)"/>', ser)
    i = int(idx.group(1)) if idx else -1
    kind = keys[i] if 0 <= i < len(keys) else None
    mk = re.compile(r"<c:marker>.*?</c:marker>", re.S)
    if kind == "comp":
        ser = mk.sub(_marker("circle", 8, colors["mark"], colors["mark"]), ser, 1)
    elif kind == "sold":
        ser = mk.sub(_marker("square", 6, colors["grey"], colors["grey"]), ser, 1)
    elif kind == "active":
        ser = mk.sub(_marker("circle", 7, colors["grey_pale"], colors["grey"], 15875), ser, 1)  # a pale fill: visible where the outline isn't drawn
    elif kind == "trend":
        ser = mk.sub('<c:marker><c:symbol val="none"/></c:marker>', ser, 1)
        ser = re.sub(r"(<c:spPr>.*?)<a:ln[^>]*>\s*<a:noFill/>\s*</a:ln>",
                     lambda m: m.group(1) + f'<a:ln w="15875"><a:solidFill><a:srgbClr val="{colors["muted"]}"/></a:solidFill>'
                                            '<a:prstDash val="dash"/></a:ln>', ser, 1, flags=re.S)
    elif kind == "subject":
        ser = mk.sub(_marker("diamond", 14, colors["text"], colors["bg"], 12700), ser, 1)
    return ser


def _x_axis(m):
    ax = m.group(0)
    if '<c:axPos val="b"/>' not in ax:
        return ax
    ax = re.sub(r"<c:numFmt [^>]*/>", '<c:numFmt formatCode="#,##0" sourceLinked="0"/>', ax, 1)
    if "<c:majorUnit" not in ax:
        ax = re.sub(r"(<c:crossBetween [^>]*/>)", r'\1<c:majorUnit val="200"/>', ax, 1)
    return ax


def style_scatter(path, colors, keys):
    """Per-series markers (shape carries meaning, not only color), a dashed trend, sq ft axis. Chart stays editable."""
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("ppt/charts/chart") and item.filename.endswith(".xml") and b"<c:scatterChart>" in data:
                xml = data.decode("utf-8")
                xml = re.sub(r"<c:ser>.*?</c:ser>", lambda m: _restyle(m.group(0), colors, keys), xml, flags=re.S)
                xml = re.sub(r"<c:valAx>.*?</c:valAx>", _x_axis, xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)
