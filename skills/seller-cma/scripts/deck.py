"""Listing presentation: slide data from compute.py's document model, the node builder, and chart styling.

    D = deck.deck_data(C, agent, footer)   # every figure the slides show, already formatted in the model
    deck.build_pptx(D, "out.pptx")          # node scripts/build_deck.js, then style_scatter()
    deck.pptx_to_pdf("out.pptx", "out.pdf") # LibreOffice copy of the slides, or None

This file computes nothing: it picks the model's figures and sentences for each slide, checks the deck wording's
shape (counts, icons, addresses), and lays out chart axes (tick values named with fmt, the one formatter).
build_deck.js only places what it's given: no price, net or payment of its own, no number formats of its own and no
colors of its own (they come from shared/design, starting from the agent's brand).
"""
import glob
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import zipfile

from _shared import cma, design, fmt, render

HERE = os.path.dirname(os.path.abspath(__file__))
BUILDER = os.path.join(HERE, "build_deck.js")
PDF_TIMEOUT = 180  # seconds for LibreOffice to convert the deck; a hung conversion gives up and the PPTX ships alone
with open(os.path.join(HERE, "..", "assets", "labels.json"), encoding="utf-8") as _f:
    L = json.load(_f)

REQUIRED = {"recommendation_why": str, "value_drivers": list, "document_items": list, "comp_lines": dict,
            "comps_takeaway": str, "market_takeaway": str, "competition": list, "competition_takeaway": str,
            "strategy_takeaway": str, "payment_takeaway": str, "needs_short": list, "timeline": list}
COUNTS = {"value_drivers": (2, 4), "document_items": (0, 2), "timeline": (1, 4), "competition": (1, 3),
          "needs_short": (1, 5)}  # (fewest, most): never pad a slide to reach a count
LAUNCH_MAX = 6  # the launch plan's cards: the first prep.items
# Icons an item can name as its last element ("pool", "kitchen"...), so the picture matches this home. Features and
# process only, never people (fair housing).
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
MARKET_ICONS = {"sale_to_list": "percent", "days": "time", "credit_share": "money", "credit_amount": "dollar",
                "comps": "chart", "sale_to_final": "percent"}
NOTE_KEYS = ("recommendation", "method", "drivers", "comps", "scatter", "market", "competition", "strategies", "nets",
             "payments", "launch", "next")
# The scatter's series: how each is drawn on the slide and keyed in its legend, from one table (markers LibreOffice
# renders: a filled shape with no reliance on an outline, so a series in the legend is always visible on the chart).
# symbol, size (pt), fill role, outline role (None: no outline), legend shape
MARKERS = {"sold": ("circle", 5, "grey_pale", None, "oval"),
           "active": ("square", 6, "muted", None, "rect"),
           "trend": (None, 0, "muted", "muted", "dash"),
           "comp": ("circle", 8, "comp", "comp", "oval"),
           "subject": ("diamond", 11, "text", "bg", "diamond")}


class DeckError(ValueError):
    """The deck can't be built; the message is written for the agent."""


def _icon(item, n, fallback):
    return ICONS[item[n]] if len(item) > n else ICONS[fallback]


def check_content(c, C):
    """The deck wording's shape (fields, counts, icons, addresses), every problem at once, as a DeckError."""
    if c is None:
        raise DeckError("report.json needs `deck` with the listing presentation's wording (see references/deck-content.md)"
                        + (f": the file {C['deck']['path']} can't be read." if (C.get("deck") or {}).get("path") else "."))
    required = dict(REQUIRED, **({"scatter_takeaway": str} if C["scatter"] else {}))
    problems = [f"deck.{key} is missing" for key, typ in required.items() if not isinstance(c.get(key), typ)]
    problems += [f"deck.{key} needs {lo} to {hi} items" for key, (lo, hi) in COUNTS.items()
                 if isinstance(c.get(key), list) and not lo <= len(c[key]) <= hi]
    for key in ("value_drivers", "document_items"):
        for item in c.get(key) or []:
            if not isinstance(item, list) or len(item) not in (2, 3):
                problems.append(f"each deck.{key} item is [heading, line] plus an optional icon name")
                break
            if len(item) == 3 and item[2] not in ICONS:
                problems.append(f'deck.{key} uses the icon "{item[2]}"; use one of: {", ".join(sorted(ICONS))}')
    for it in C["prep"]["items"][:LAUNCH_MAX]:
        if it.get("icon") and it["icon"] not in ICONS:
            problems.append(f'prep.items uses the icon "{it["icon"]}"; use one of: {", ".join(sorted(ICONS))}')
    if len(C["prep"]["items"]) < 3:
        problems.append("prep.items needs at least 3 steps (the launch plan's cards)")
    for item in c.get("timeline") or []:
        if not (isinstance(item, list) and len(item) == 2 and str(item[0]).lower() in ("now", "before", "after")):
            problems.append('each deck.timeline item is ["now" | "before" | "after", what happens]: the script dates '
                            "the go-live step itself")
            break
    rows = {_key(r[0]): r for r in C["competition"]["rows"]}
    for item in c.get("competition") or []:
        if not isinstance(item, list) or len(item) != 2:
            problems.append("each deck.competition card is [address, why it matters]: the price, status and days come "
                            "from the report's competition table")
            break
        if _key(item[0]) not in rows:
            problems.append(f"deck.competition lists {item[0]}, which isn't in the report's competition table")
    cards = {_key(cd["address"]) for cd in C["comps"]["cards"]}
    for address in (c.get("comp_lines") or {}):
        if _key(address) not in cards:
            problems.append(f"deck.comp_lines names {address}, which isn't one of the comp cards")
    if problems:
        raise DeckError("The deck content isn't complete: " + "; ".join(dict.fromkeys(problems)) + ".")


def _key(address):
    return cma._street(cma.display_address(address))


# --- chart axes (layout only: every value named with fmt) ---------------------------------------------------------------

def ticks(lo, hi, step, f):
    out, v = [], lo
    while v <= hi + step / 1000:
        out.append([v, f(v)])
        v += step
    return out


def dot_axis(values):
    """The comps slide's price axis: bounds on a round step, each tick named with fmt.k."""
    step = cma.nice_step(max(values) - min(values) + 20000, 5)
    lo, hi = math.floor((min(values) - step / 2) / step) * step, math.ceil((max(values) + step / 2) / step) * step
    return {"lo": lo, "hi": hi, "ticks": ticks(lo, hi, step, fmt.k)}


def scatter_data(C, colors):
    """The model's chart points (the same cma.scatter_points the report draws) by series, in drawing order, with the
    marker each is drawn and keyed with; only series with points, so the legend names only what's on the chart."""
    homes, _, fit = C["_points"]
    s, rec, rw = C["subject"], C["recommendation"], L
    pts = {kind: [[h["living_area"], h["close_price"] if kind != "active" else h["current_price"]] for h in hs]
           for kind, hs in homes.items()}
    xs = [p[0] for v in pts.values() for p in v] + [s["sqft"]]
    x0, x1 = math.floor((min(xs) - 50) / 200) * 200, math.ceil((max(xs) + 50) / 200) * 200
    trend = [[x0 + (x1 - x0) * i / 27, fit["intercept"] + fit["slope"] * (x0 + (x1 - x0) * i / 27)] for i in range(28)] if fit else []
    subject = [[s["sqft"], rec["list_price"]]]
    names = {"sold": rw["deck_series_sold"], "active": rw["deck_series_active"], "trend": rw["deck_series_trend"],
             "comp": rw["deck_series_comp"], "subject": C["deck"]["series_subject"]}
    series = []
    for key, p in (("sold", pts["sold"]), ("active", pts["active"]), ("trend", trend), ("comp", pts["comp"]),
                   ("subject", subject)):
        if not p:
            continue
        symbol, size, fill, line, shape = MARKERS[key]
        series.append({"key": key, "name": names[key], "points": p,
                       "marker": {"symbol": symbol, "size": size, "fill": colors[fill], "line": colors[line] if line else None,
                                  "shape": shape}})
    ys = [p[1] for ser in series for p in ser["points"]] + [rec["low"], rec["high"]]
    step = cma.nice_step(max(ys) - min(ys) + 20000, 7)
    y0, y1 = math.floor((min(ys) - 10000) / step) * step, math.ceil((max(ys) + 10000) / step) * step
    return {"series": series, "y_min": y0, "y_max": y1, "y_step": step, "y_ticks": ticks(y0, y1, step, fmt.k),
            "x_min": x0, "x_max": x1, "band": [rec["low"], rec["high"]], "band_label": C["scatter"]["band_label"],
            "axis_x": L["axis_x"], "axis_y": L["axis_y"],
            "trend_note": (C["scatter"]["trend"] or {}).get("deck", "")}


def contrast_roles(colors):
    """The deck's contrast-checked roles, so a light, a mid and a near-black brand all work: `mark` for chart marks and
    accent bars (3:1 on white, apart from the black subject marker and the gray other sales), `comp` for the comps
    (the brand itself, darkened to 3:1 only when it's too light), `on_dark` and `on_ink` for secondary text on the dark
    fills, and `grey_pale` for the other sales."""
    hx = lambda key: "#" + colors[key]  # noqa: E731
    white, text = hx("bg"), hx("text")
    options = [design.darken_to(c, 3.0) for c in (hx("brand"), hx("brand_ink"), hx("brand_strong"), hx("brand_accent"),
                                                   design.mix_white(hx("brand"), 0.25))]
    gap = lambda c: min(design.distance(c, text), design.distance(c, hx("grey")))  # noqa: E731
    mark = next((c for c in options if gap(c) >= 0.12), max(options, key=gap))

    def first(options, against, target):
        return next((c for c in options if design.contrast(hx(c), hx(against)) >= target), "bg")
    comp = hx("brand") if design.contrast(hx("brand"), white) >= 3.0 else design.darken_to(hx("brand"), 3.0)
    return {"mark": mark.lstrip("#"), "comp": comp.lstrip("#"),
            "on_dark": colors[first(("brand_soft", "brand_rule"), "brand_deep", 7.0)],
            "on_ink": colors[first(("brand_soft", "brand_rule"), "brand_ink", 4.5)],
            "grey_pale": design.mix_white(hx("grey"), 0.6).lstrip("#")}


def deck_data(C, agent, footer):
    """Everything build_deck.js draws, from the document model: its figures, its sentences and the deck wording."""
    dm = C.get("deck") or {}
    c = dm.get("content")
    check_content(c, C)
    rec, pay, net, sm = C["recommendation"], C["payments"], C["net"], C["summary"]
    theme = design.theme(agent.get("brand"), "seller")
    colors = design.pptx_colors(theme)  # the brand's shades and tints, plus black and grays; the deck uses nothing else
    colors.update(contrast_roles(colors))
    notes = c.get("notes") or {}
    org = " · ".join(str(agent[f]) for f in ("team", "brokerage") if agent.get(f))
    if agent.get("license"):
        org = " · ".join(x for x in (org, f'{L["lic"]} {agent["license"]}') if x)
    contact = " · ".join(str(agent[f]) for f in ("phone", "email", "website") if agent.get(f))
    steps = ([[fmt.num(C["n_sold"]), dm["sold_line"]]] if dm.get("sold_line") else []) + [
        [fmt.num(C["n_comps"]), dm["step_comps"]], [dm["adjusted_range"], L["deck_step_adjusted"]],
        [C["median_adjusted_display"], L["deck_step_median"]]]
    rows = {_key(r[0]): r for r in C["competition"]["rows"]}
    competition = []
    for address, why in c["competition"]:
        r = rows[_key(address)]
        status = t("deck_comp_status", status=r[1], days=r[5]) if r[5] else r[1]
        competition.append([r[0], r[2], status, why])
    lines = {_key(a): v for a, v in (c.get("comp_lines") or {}).items()}
    comps = [{"address": cd["address"], "adjusted": cd["adjusted"], "adjusted_k": cd["adjusted_k"],
              "line": (L["deck_strongest"] + (" · " + lines.get(_key(cd["address"]), "") if lines.get(_key(cd["address"])) else ""))
              if cd["strongest"] else lines.get(_key(cd["address"]), "")}
             for cd in C["comps"]["cards"]]
    axis = dot_axis([x["adjusted"] for x in comps] + [rec["low"], rec["high"], rec["list_price"]])
    one = dm["market_one_period"]
    mcards = [[m["label"], *m["values"], ICONS[MARKET_ICONS.get(m["key"], "chart")]] for m in C["market_cards"]]
    strategies = [{"label": x["label"], "list_display": x["list_price_display"], "time": x["time"],
                   "expected_display": x["expected_sale_display"], "credit_display": x["seller_credit_display"],
                   "note": x["note"], "net": x["net_after_holding"], "net_display": x["net_after_holding_display"],
                   "payment_display": t("deck_per_month", amount=x["payment_display"]),
                   "down_display": t("deck_down", amount=x["down_display"], pct=pay["down_display"])}
                  for x in C["strategies"]]
    head = [L["th_sale"], L["th_sold_for"], L["th_seller_paid"], L["th_adjusted"]]
    labels = {k: v for k, v in L.items() if k.startswith("deck_")}
    labels.update(deck_rec_title=dm["rec_title"], deck_rec_label=dm["rec_label"], deck_launch_title=dm["launch_title"],
                  deck_strat_title=dm["strat_title"], deck_net_sub=C["options_summary"]["net_sub"], deck_pay_sub=dm["pay_sub"],
                  deck_dot_rec=dm["dot_rec"], deck_shaded=t("deck_shaded", range=rec["range_k"]),
                  deck_method_note=C["comps"]["method"] or L["deck_method_note_none"],
                  deck_expected_sub=rec["expected_sub"], deck_scatter_title=c.get("scatter_title") or L["deck_scatter_title"])
    return {
        "colors": colors,
        "labels": labels,
        "preliminary": t("deck_preliminary", why=C["preliminary_short"]) if C["preliminary"] else "",
        "agent": {"name": agent.get("name") or "", "lines": [x for x in (org, contact) if x],
                  "short": " · ".join(x for x in (agent.get("name"), agent.get("phone"), agent.get("email")) if x)},
        "footer": footer,
        "prepared_date": C["prepared_date"],
        "cover": {"title": dm["title"], "subtitle": dm["subtitle"], "tagline": dm["tagline"]},
        "rec": {"list_display": rec["list_price_display"], "range_display": rec["range_k"],
                "expected_display": rec["expected_sale_display"], "why": c["recommendation_why"],
                "history": C["price_history"] or C["history_line"]},
        "method": {"steps": steps},
        "drivers": [[d[0], d[1], _icon(d, 2, "star")] for d in c["value_drivers"]],
        "documents": [[d[0], d[1], _icon(d, 2, "document")] for d in c["document_items"]],
        "comps": comps, "dot": {**axis, "low": rec["low"], "high": rec["high"], "price": rec["list_price"]},
        "comps_takeaway": c["comps_takeaway"],
        "scatter": scatter_data(C, colors) if C["scatter"] else None,
        "scatter_takeaway": c.get("scatter_takeaway", ""),
        "market": {"title": c.get("market_title") or L["deck_market_title"], "subtitle": dm["market_subtitle"],
                   "one_period": one, "cards": mcards, "takeaway": c["market_takeaway"],
                   "period_labels": [L["deck_period_early"], L["deck_period_recent"]]},
        "competition": competition, "competition_takeaway": c["competition_takeaway"],
        "strategies": strategies, "recommended_index": C["recommended_index"],
        "strategy_takeaway": c["strategy_takeaway"],
        "net_spread_display": C["net_spread_display"],
        "pay": {"per_10k_line": dm["per_10k_line"], "takeaway": c["payment_takeaway"]},
        "launch": [[it["heading"], it["short"], ICONS[it["icon"] if it.get("icon") in ICONS else "check"]]
                   for it in C["prep"]["items"][:LAUNCH_MAX]],
        "needs_short": c["needs_short"], "timeline": dm["timeline"],
        "net_head": [L["th_at_closing"]] + net["header"],
        "net_rows": [[r["label"]] + r["display"] for r in net["rows"]],
        "net_total_rows": [i for i, r in enumerate(net["rows"]) if r["kind"] == "total"],
        "net_note": " ".join(C["deck_notes"]),
        "net_speaker": " ".join(C["notes"]),
        "comps_head": head,
        "comps_rows": C["comps"]["table"] + [C["comps"]["subject_row"]],
        "comps_note": " ".join(render.notice_lines(agent, C["notices"], marketing=True)),
        "comps_speaker": " ".join(x for x in (C["comps"]["method"], C["comps"]["count_line"]) if x),
        "notes": {key: str(notes.get(key) or "") for key in NOTE_KEYS},
    }


def t(key, **kw):
    return L[key].format(**kw) if kw else L[key]


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
        missing = next((re.search(r"Cannot find module '([^']+)'", ln) for ln in lines if "Cannot find module" in ln), None)
        if missing:
            raise DeckError(f"The deck needs the Node module {missing.group(1)}, which isn't available here "
                            "(pptxgenjs, react, react-dom, react-icons and sharp). The PDF is unaffected.")
        raise DeckError("The deck builder failed: " + next((ln for ln in lines if "Error" in ln), lines[-1]).strip())
    if D.get("scatter"):
        style_scatter(path, D["colors"], D["scatter"]["series"])
    return [ln[len("Check: "):] for ln in r.stderr.splitlines() if ln.startswith("Check: ")]


# CMA-256: where LibreOffice installs when `soffice` isn't on PATH (macOS app bundle, Linux packages and snaps)
OFFICE_PATHS = ("/Applications/LibreOffice.app/Contents/MacOS/soffice", "/usr/bin/soffice", "/usr/bin/libreoffice",
                "/usr/lib/libreoffice/program/soffice", "/opt/libreoffice/program/soffice", "/usr/local/bin/soffice",
                "/snap/bin/libreoffice")


def find_office():
    """The LibreOffice command: on PATH first, then the usual install paths. None when there isn't one."""
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    extra = sorted(glob.glob("/opt/libreoffice*/program/soffice"))  # versioned installs (/opt/libreoffice24.8)
    return next((p for p in (*OFFICE_PATHS, *extra) if os.path.isfile(p) and os.access(p, os.X_OK)), None)


def pptx_to_pdf(pptx, pdf):
    """A PDF copy of the slides through LibreOffice (headless, its own profile). None when it isn't available."""
    office = find_office()
    if not office:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            subprocess.run([office, "--headless", "--norestore", f"-env:UserInstallation=file://{tmp}/profile",
                            "--convert-to", "pdf", "--outdir", tmp, pptx], capture_output=True, timeout=PDF_TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            return None
        made = os.path.join(tmp, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")
        if not os.path.exists(made):
            return None
        shutil.move(made, pdf)
    return pdf


# --- chart styling pptxgenjs can't do ------------------------------------------

def _marker(m):
    """A series marker from MARKERS' style (filled; the outline only where the style has one)."""
    if not m["symbol"]:
        return '<c:marker><c:symbol val="none"/></c:marker>'
    ln = "<a:ln><a:noFill/></a:ln>" if m["line"] is None else \
        f'<a:ln w="19050"><a:solidFill><a:srgbClr val="{m["line"]}"/></a:solidFill></a:ln>'
    return (f'<c:marker><c:symbol val="{m["symbol"]}"/><c:size val="{m["size"]}"/><c:spPr>'
            f'<a:solidFill><a:srgbClr val="{m["fill"]}"/></a:solidFill>{ln}</c:spPr></c:marker>')


def _restyle(ser, colors, series):
    """One scatter series, by its position in the drawn series (deck_data's, empty ones left out)."""
    idx = re.search(r'<c:idx val="(\d+)"/>', ser)
    i = int(idx.group(1)) if idx else -1
    if not 0 <= i < len(series):
        return ser
    s = series[i]
    mk = re.compile(r"<c:marker>.*?</c:marker>", re.S)
    ser = mk.sub(_marker(s["marker"]), ser, 1)
    if s["key"] == "trend":
        ser = re.sub(r"(<c:spPr>.*?)<a:ln[^>]*>\s*<a:noFill/>\s*</a:ln>",
                     lambda m: m.group(1) + f'<a:ln w="15875"><a:solidFill><a:srgbClr val="{colors["muted"]}"/></a:solidFill>'
                                            '<a:prstDash val="dash"/></a:ln>', ser, 1, flags=re.S)
    return ser


def _x_axis(m):
    ax = m.group(0)
    if '<c:axPos val="b"/>' not in ax:
        return ax
    ax = re.sub(r"<c:numFmt [^>]*/>", '<c:numFmt formatCode="#,##0" sourceLinked="0"/>', ax, 1)
    if "<c:majorUnit" not in ax:
        ax = re.sub(r"(<c:crossBetween [^>]*/>)", r'\1<c:majorUnit val="200"/>', ax, 1)
    return ax


def style_scatter(path, colors, series):
    """Per-series markers (shape carries meaning, not only color), a dashed trend, sq ft axis. Chart stays editable."""
    tmp = path + ".tmp"
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("ppt/charts/chart") and item.filename.endswith(".xml") and b"<c:scatterChart>" in data:
                xml = data.decode("utf-8")
                xml = re.sub(r"<c:ser>.*?</c:ser>", lambda m: _restyle(m.group(0), colors, series), xml, flags=re.S)
                xml = re.sub(r"<c:valAx>.*?</c:valAx>", _x_axis, xml, flags=re.S)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)
