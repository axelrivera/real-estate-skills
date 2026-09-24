"""Listing presentation: slide data from compute.py's numbers, the node builder, and chart styling.

    D = deck.deck_data(R, C, homes, agent, L, footer)   # every number the slides show, already computed
    deck.build_pptx(D, "out.pptx")                       # node scripts/build_deck.js, then style_scatter()

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
COUNTS = {"value_drivers": 4, "document_items": 2, "market_stats": 4, "launch_plan": 6, "timeline": 4}
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
    if isinstance(c.get("competition"), list) and not 1 <= len(c["competition"]) <= 3:
        problems.append("deck.competition needs 1 to 3 cards")
    problems += [f"deck.{key} needs exactly {n} items" for key, n in COUNTS.items()
                 if isinstance(c.get(key), list) and len(c[key]) != n]
    if len(c.get("needs_short") or []) > 5:
        problems.append("deck.needs_short has more than 5 items")
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


def _month(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%B")


def scatter_data(homes, R, C, L):
    """Points by category (same rules as the PDF chart), the size-only trend line, and the subject at the list price."""
    s, sc = R["subject"], R.get("scatter") or {}
    address = s.get("mls_address", s["address"])
    others = [h for h in homes if not mls.same_address(h["address"], address)]
    lo, hi = s["sqft"] * sc.get("min_size_ratio", 0.6), s["sqft"] * sc.get("max_size_ratio", 1.4)
    renovated = {_norm(a) for a in sc.get("renovated", [])}
    pts = {"ren": [], "pool": [], "nop": [], "active": []}
    for h in others:
        if not h.get("living_area") or not lo <= h["living_area"] <= hi:
            continue
        if h["status"] == "SOLD" and h.get("close_price"):
            kind = ("ren" if _norm(h["address"]) in renovated else "pool") if h["private_pool"] else "nop"
            pts[kind].append([h["living_area"], h["close_price"]])
        elif h["status"] == "ACTIVE" and h.get("current_price"):
            pts["active"].append([h["living_area"], h["current_price"]])
    fit = mls.trend(others, s["sqft"], sc.get("fit_size_ratio", 1.6))
    xs = [p[0] for v in pts.values() for p in v] + [s["sqft"]]
    trend = []
    if fit:
        x0, x1 = min(xs), max(xs)
        trend = [[x0 + (x1 - x0) * i / 27, fit["intercept"] + fit["slope"] * (x0 + (x1 - x0) * i / 27)] for i in range(28)]
    return {"points": pts, "trend": trend, "subject": [s["sqft"], R["recommendation"]["list_price"]],
            "trend_note": L("deck_trend_note", trend=k(fit["at_subject"])) if fit else "",
            "series": [L(f"deck_series_{key}") for key in ("ren", "pool", "nop", "active", "trend", "subject")],
            "axis_x": L("axis_x"), "axis_y": L("axis_y")}


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
    colors = design.pptx_colors(theme)  # includes party_both_soft / party_both_bg tints

    window = C.get("window") or {}
    if content.get("sold_line"):
        sold_line = content["sold_line"]
    elif window:
        month = _month(window["first_close"])
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
        split = datetime.strptime(window["split_date"], "%Y-%m-%d")
        before = (split.replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")
        periods = [f'{_month(window["first_close"])}–{_month(before)}', f'{_month(window["split_date"])}–{_month(window["last_close"])}']

    L_deck = {key: v for key, v in L.text.items() if key.startswith("deck_")}
    org = " · ".join(str(agent[f]) for f in ("team", "brokerage") if agent.get(f))
    if agent.get("license"):
        org = " · ".join(x for x in (org, f'{L("lic")} {agent["license"]}') if x)
    contact = " · ".join(str(agent[f]) for f in ("phone", "email", "website") if agent.get(f))
    cash = net["cash_at_closing"]
    excluded = L("deck_app_excluded" if cash else "deck_app_excluded_payoff")
    app_note = " ".join([n for n in net["notes"]] + [L("deck_app_net_note", excluded=excluded)])
    app_note = re.sub(r"</?strong>", "", app_note)
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
        "net_sub": L("deck_cash_sub" if cash else "deck_net_sub") + (f"; {L('standard_terms_sub')}" if net["standard_terms"] else ""),
        "net_spread_display": C["net_spread_display"],
        "net_rows": [[r["label"]] + r["display"] for r in net["rows"]],
        "net_note": app_note,
        "appendix_comps": [[r[0], money(r[1]), money(r[2]), money(r[3])] for r in R["comps"]["summary_rows"]],
        "subject_row": [R["comps"].get("subject_row_label", L("subject_row")), money(rec["list_price"]), "—",
                        f'{L("range_word")} {k(rec["low"])}–{k(rec["high"])}'],
        "table_head": [L("th_sale"), L("th_sold_for"), L("th_seller_paid"), L("th_adjusted")],
        "net_head": L("th_at_closing"),
        "appendix_note": " ".join(x for x in (content.get("adjustments_summary", ""), L("deck_disclaimer"),
                                              *render.notice_lines(agent, cma.report_notices(C), marketing=True)) if x),
    }


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
    style_scatter(path, D["colors"])
    return path


# --- chart styling pptxgenjs can't do ------------------------------------------

def _marker(symbol, size, fill, line, line_w=9525):
    fill_xml = "<a:noFill/>" if fill is None else f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>'
    return (f'<c:marker><c:symbol val="{symbol}"/><c:size val="{size}"/><c:spPr>{fill_xml}'
            f'<a:ln w="{line_w}"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln></c:spPr></c:marker>')


def _restyle(ser, colors):
    """One scatter series, by its position: 0 renovated, 1 other pool, 2 no pool, 3 for sale, 4 trend, 5 subject."""
    idx = re.search(r'<c:idx val="(\d+)"/>', ser)
    i = int(idx.group(1)) if idx else -1
    mk = re.compile(r"<c:marker>.*?</c:marker>", re.S)
    if i == 0:
        ser = mk.sub(_marker("circle", 8, colors["brand"], colors["brand"]), ser, 1)
    elif i == 1:
        ser = mk.sub(_marker("triangle", 8, colors["brand_accent"], colors["brand_accent"]), ser, 1)
    elif i == 2:
        ser = mk.sub(_marker("square", 6, colors["grey"], colors["grey"]), ser, 1)
    elif i == 3:
        ser = mk.sub(_marker("circle", 7, colors["bg"], colors["grey"], 15875), ser, 1)
    elif i == 4:
        ser = mk.sub('<c:marker><c:symbol val="none"/></c:marker>', ser, 1)
        ser = re.sub(r"(<c:spPr>.*?)<a:ln[^>]*>\s*<a:noFill/>\s*</a:ln>",
                     lambda m: m.group(1) + f'<a:ln w="15875"><a:solidFill><a:srgbClr val="{colors["muted"]}"/></a:solidFill>'
                                            '<a:prstDash val="dash"/></a:ln>', ser, 1, flags=re.S)
    elif i == 5:
        ser = mk.sub(_marker("diamond", 14, colors["party_both"], colors["bg"], 12700), ser, 1)
    return ser


def _x_axis(m):
    ax = m.group(0)
    if '<c:axPos val="b"/>' not in ax:
        return ax
    ax = re.sub(r"<c:numFmt [^>]*/>", '<c:numFmt formatCode="#,##0" sourceLinked="0"/>', ax, 1)
    if "<c:majorUnit" not in ax:
        ax = re.sub(r"(<c:crossBetween [^>]*/>)", r'\1<c:majorUnit val="200"/>', ax, 1)
    return ax


def style_scatter(path, colors):
    """Per-series markers (shape carries meaning, not only color), a dashed trend, sq ft axis. Chart stays editable."""
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("ppt/charts/chart") and item.filename.endswith(".xml") and b"<c:scatterChart>" in data:
                xml = data.decode("utf-8")
                xml = re.sub(r"<c:ser>.*?</c:ser>", lambda m: _restyle(m.group(0), colors), xml, flags=re.S)
                xml = re.sub(r"<c:valAx>.*?</c:valAx>", _x_axis, xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)
