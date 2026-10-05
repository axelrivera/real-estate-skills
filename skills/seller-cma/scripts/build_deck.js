// Build the seller listing presentation: 13 slides plus a 2-slide appendix.
// Usage: node scripts/build_deck.js deck-data.json OUTPUT.pptx   (render.py runs it; see deck.py)
// Text that still overflows at its smallest size is printed to stderr as "Check: slide N ..." lines.
// Every number, label and color comes from deck-data.json (deck.py, from compute.py and shared/design).
// This file only lays them out: it never calculates a price, net or payment, and has no colors of its own.
const fs = require('fs');
const pptxgen = require('pptxgenjs');
const React = require('react');
const ReactDOMServer = require('react-dom/server');
const sharp = require('sharp');
const fa = require('react-icons/fa');

const [, , dataPath, outPath] = process.argv;
const D = JSON.parse(fs.readFileSync(dataPath, 'utf8'));
const C = D.content;
const T = D.labels;
const K = D.colors;

// Color roles, all from the agent's one brand color (shared/design) plus black and grays: no second hue.
// Every role that carries text or marks is contrast-checked, so light, mid and near-black brands all work:
// brand_ink (4.5:1 on white) carries large brand text and fills behind white text; brand_strong (7:1) carries small
// brand text, also on the tints; mark (3:1) is chart marks and accent bars; brand_deep (10:1) is the dark slides, with
// on_dark text; on_ink is secondary text on brand_ink fills (deck.py contrast_roles). The tints are brand_callout
// (cards, the scatter's range band) and brand_rule (lines, table rules, stronger panels); tables have no fills. The
// subject home and the reference lines are black (text), never a color of their own; the grays are true grays.
const BRAND = K.brand_ink, MARK = K.mark, COMP = K.comp, ON = K.on_brand, DEEP = K.brand_deep, STRONG = K.brand_strong, INK = K.text,
  MUTED = K.muted, TINT = K.brand_callout, LINE = K.brand_rule, WHITE = K.bg,
  ON_DARK = K.on_dark, ON_INK = K.on_ink;
const FONT = 'Arial';
const fmt = (s, v) => s.replace(/\{(\w+)\}/g, (m, key) => (key in v ? v[key] : m));

// Text fitting. Boxes are fixed, so every text is measured before it's placed: Arial advance widths (the same as
// Helvetica's AFM metrics, per 1000 em, for ' ' to '~'), wrapped by words. fit() returns the largest size from
// `size` down to `min` at which the text fits in `lines` lines and the box height; when even `min` doesn't fit, it
// records a check the agent reads on stderr ("shorten it in deck") and returns `min`.
const AW = { r: [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584],
  b: [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584] };
const WIDE = { '–': 556, '—': 1000, '·': 278, '’': 222, '‘': 222, '“': 333, '”': 333, '★': 1000, '…': 1000, '•': 350 };
const textW = (t, size, bold) => {  // inches, with a small margin for renderer differences
  let u = 0;
  for (const ch of String(t)) { const c = ch.codePointAt(0); u += c >= 32 && c <= 126 ? AW[bold ? 'b' : 'r'][c - 32] : (WIDE[ch] || 600); }
  return u / 1000 * size / 72 * 1.04;
};
const lineCount = (t, size, w, bold) => {  // Infinity when one word is wider than the box (it would break mid-word)
  let total = 0;
  for (const para of String(t).split('\n')) {
    let n = 1, cur = 0;
    const sp = textW(' ', size, bold);
    for (const word of para.split(/ +/).filter(Boolean)) {
      const ww = textW(word, size, bold);
      if (ww > w) return Infinity;
      if (cur === 0) cur = ww; else if (cur + sp + ww <= w) cur += sp + ww; else { n += 1; cur = ww; }
    }
    total += n;
  }
  return total;
};
const LEAD = 1.2;  // line height / font size
const checks = [];
let slideNo = 0, where = '';
function fit(text, w, h, { size, min = size, lines = 1, bold = false, oneLineMin, what }) {
  const ok = (sz, ln) => { const k = lineCount(text, sz, w, bold); return k <= ln && k * sz * LEAD / 72 <= h + 0.02; };
  if (oneLineMin) for (let sz = size; sz >= oneLineMin - 1e-9; sz -= 0.5) if (ok(sz, 1)) return sz;
  for (let sz = size; sz >= min - 1e-9; sz -= 0.5) if (ok(sz, lines)) return sz;
  const most = fitChars(text, t => { const k = lineCount(t, min, w, bold); return k <= lines && k * min * LEAD / 72 <= h + 0.02; });
  checks.push(`slide ${slideNo} (${where}): ${what || 'text'} "${String(text).slice(0, 60)}" doesn't fit its box: ${tooLong(most, text)} in deck and rebuild.`);
  return min;
}
// Iteration 12: a text-fit check says how much fits. fitChars() is the length of the longest run of whole words, from
// the start, for which `fits` holds (0 when even the first word doesn't); tooLong() words the fix with both lengths.
function fitChars(text, fits) {
  const words = String(text).split(/ +/).filter(Boolean);
  let best = 0;
  for (let k = 1; k <= words.length; k++) {
    const part = words.slice(0, k).join(' ');
    if (!fits(part)) break;
    best = part.length;
  }
  return best;
}
function tooLong(most, text, name = 'it') {
  const has = String(text).length;
  return most > 0 ? `at most about ${most} characters fit and ${name} has ${has}; shorten ${name} to ${most} characters or fewer`
    : `its first word is wider than the box (${name} has ${has} characters); use shorter words`;
}

async function icon(name, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(fa[name], { color: '#' + color, size: String(size) }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return 'image/png;base64,' + buf.toString('base64');
}

(async () => {
  const pres = new pptxgen();
  pres.layout = 'LAYOUT_16x9'; // 10 x 5.625 in
  pres.title = C.title;
  if (D.agent.name) pres.author = D.agent.name;
  const W = 10, H = 5.625, M = 0.5;
  let n = 0;
  const notes = (s, text) => { if (text) s.addNotes(text); };
  const addSlide = name => { slideNo += 1; where = name; return pres.addSlide(); };
  // Text at the size fit() chose; o takes fit's options (size, min, lines, oneLineMin, what) and pptxgenjs's.
  const tx = (s, text, o) => {
    const { size, min, lines, oneLineMin, what, ...rest } = o;
    const fontSize = fit(text, o.w, o.h, { size, min, lines, bold: o.bold, oneLineMin, what });
    s.addText(text, { fontFace: FONT, margin: 0, isTextBox: true, ...rest, fontSize });
    return fontSize;
  };

  const footer = s => {
    n += 1;
    s.addText(D.footer, { x: M, y: H - 0.38, w: 7.5, h: 0.25, fontFace: FONT, fontSize: 8, color: MUTED, margin: 0, isTextBox: true });
    s.addText(String(n), { x: W - M - 0.5, y: H - 0.38, w: 0.5, h: 0.25, fontFace: FONT, fontSize: 8, color: MUTED, align: 'right', margin: 0, isTextBox: true });
  };
  const title = (s, t, sub) => {
    tx(s, t, { x: M, y: 0.32, w: W - 2 * M, h: 0.62, size: 26, min: 20, bold: true, color: INK, valign: 'top', what: 'slide title' });
    if (sub) tx(s, sub, { x: M, y: 0.92, w: W - 2 * M, h: 0.36, size: 13, min: 11, color: MUTED, what: 'subtitle' });
  };
  const circleIcon = async (s, name, x, y, d = 0.5, bg = BRAND, fg = ON) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg }, line: { color: bg } });
    s.addImage({ data: await icon(name, fg), x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52 });
  };
  const content = name => { const s = addSlide(name); s.background = { color: WHITE }; return s; };
  const card = (s, x, y, w, h, fill, line) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: line || fill }, rectRadius: 0.08 });

  // 1. Title (dark)
  {
    const s = addSlide('title'); s.background = { color: DEEP }; n += 1;
    await circleIcon(s, 'FaHome', M, 0.9, 0.7, ON_DARK, DEEP);  // light on the dark slides: 7:1 for any brand
    tx(s, C.title, { x: M, y: 1.8, w: 8.5, h: 1.0, size: 38, min: 26, lines: 2, bold: true, color: ON, valign: 'bottom', what: 'deck.title' });
    tx(s, C.subtitle, { x: M, y: 2.85, w: 8.5, h: 0.45, size: 16, min: 12, color: ON_DARK, what: 'deck.subtitle' });
    const lines = [];
    if (D.agent.name) lines.push({ text: D.agent.name, options: { bold: true, breakLine: true } });
    D.agent.lines.forEach(t => lines.push({ text: t, options: { breakLine: true } }));
    lines.push({ text: D.prepared_date });
    const longest = Math.max(...[D.agent.name, ...D.agent.lines, D.prepared_date].filter(Boolean).map(t => textW(t, 12)));
    const size = longest > 8.5 ? Math.max(9, 12 * 8.5 / longest) : 12;
    s.addText(lines, { x: M, y: 3.75, w: 8.5, h: 1.2, fontFace: FONT, fontSize: size, color: ON_DARK, margin: 0, paraSpaceAfter: 2, valign: 'top', isTextBox: true });
    if (D.preliminary) s.addText(D.preliminary, { x: 5.5, y: 0.95, w: 4.0, h: 0.5, fontFace: FONT, fontSize: 11, bold: true, color: ON, align: 'right', margin: 0, isTextBox: true });
    notes(s, T.deck_title_note);
  }

  // 2. Recommendation
  {
    const s = content('recommendation'); title(s, T.deck_rec_title);
    s.addText(T.deck_rec_label, { x: M, y: 1.35, w: 4.6, h: 0.35, fontFace: FONT, fontSize: 14, color: MUTED, margin: 0, isTextBox: true });
    tx(s, D.rec.list_display, { x: M, y: 1.7, w: 4.8, h: 1.2, size: 64, min: 44, bold: true, color: BRAND });
    const hist = D.history;  // Results_v4 case 02: the home's listings that ended unsold, with dates and first prices
    tx(s, C.recommendation_why, { x: M, y: 3.1, w: 4.6, h: hist ? 1.0 : 1.4, size: 15, min: 12, lines: hist ? 3 : 5, color: INK, valign: 'top', what: 'deck.recommendation_why' });
    if (hist) {
      const lead = T.deck_history + ': ', hs = fit(lead + hist, 4.6, 0.62, { size: 11, min: 9, lines: 3, what: 'the listing history (listing_history)' });
      s.addText([{ text: lead, options: { bold: true, color: STRONG } }, { text: hist, options: { color: MUTED } }],
        { x: M, y: 4.2, w: 4.6, h: 0.62, fontFace: FONT, fontSize: hs, margin: 0, valign: 'top', isTextBox: true });
    }
    const cards = [[T.deck_range_card, D.rec.range_display, T.deck_range_sub], [T.deck_expected_card, D.expected_sale, T.deck_expected_sub]];
    cards.forEach((c, i) => {
      const y = 1.35 + i * 1.6;
      card(s, 5.7, y, 3.8, 1.35, TINT);
      tx(s, c[0], { x: 5.95, y: y + 0.15, w: 3.3, h: 0.3, size: 12, min: 10, color: MUTED });
      tx(s, c[1], { x: 5.95, y: y + 0.45, w: 3.3, h: 0.5, size: 24, min: 15, bold: true, color: INK, valign: 'middle', what: i ? 'the expected sale (deck.expected_sale or summary_page.expected_sale)' : 'value range' });
      tx(s, c[2], { x: 5.95, y: y + 0.95, w: 3.3, h: 0.28, size: 11, min: 9, color: MUTED });
    });
    footer(s); notes(s, C.notes.recommendation);
  }

  // 3. How we priced it: four numbered steps down the left (each value with what it is right under it), joined by a
  // line, and the answer in one card on the right
  {
    const s = content('how we priced it'); title(s, T.deck_method_title, T.deck_method_sub);
    const m = D.method;
    const steps = [[String(m.n_sold), m.sold_line], [String(m.n_comps), T.deck_step_comps],
                   [m.adj_range, T.deck_step_adjusted], [m.adj_median, T.deck_step_median]].slice(m.n_sold == null ? 1 : 0);
    const top = 1.45, pitch = 0.74, d = 0.34, vx = M + 0.55, vw = 5.75 - vx;
    const size = Math.min(...steps.map(st => fit(st[0], vw, 0.38, { size: 22, min: 16, bold: true, what: 'step value' })));
    s.addShape(pres.shapes.LINE, { x: M + d / 2, y: top + d / 2, w: 0, h: pitch * (steps.length - 1), line: { color: LINE, width: 1.5 } });
    steps.forEach((st, i) => {
      const y = top + i * pitch;
      s.addShape(pres.shapes.OVAL, { x: M, y, w: d, h: d, fill: { color: TINT }, line: { color: MARK, width: 1 } });
      s.addText(String(i + 1), { x: M, y, w: d, h: d, fontFace: FONT, fontSize: 11, bold: true, color: STRONG, align: 'center', valign: 'middle', margin: 0, isTextBox: true });
      s.addText(st[0], { x: vx, y: y - 0.04, w: vw, h: 0.38, fontFace: FONT, fontSize: size, bold: true, color: BRAND, valign: 'middle', margin: 0, isTextBox: true });
      tx(s, st[1], { x: vx, y: y + 0.34, w: vw, h: 0.24, size: 12, min: 10, color: INK, valign: 'top', what: i === 0 && m.n_sold != null ? 'the sold line (deck.sold_line)' : 'step caption' });
    });
    const rx = 6.2, rw = W - M - rx, ry = top - 0.05, rh = pitch * 3 + 0.68;  // the card keeps its height with three steps (no export)
    card(s, rx, ry, rw, rh, BRAND);
    tx(s, T.deck_rec_label, { x: rx + 0.3, y: ry + 0.3, w: rw - 0.6, h: 0.3, size: 13, min: 11, color: ON });
    tx(s, D.rec.list_display, { x: rx + 0.3, y: ry + 0.65, w: rw - 0.6, h: 0.8, size: 40, min: 28, bold: true, color: ON, valign: 'middle' });
    tx(s, T.deck_range_card, { x: rx + 0.3, y: ry + rh - 0.85, w: rw - 0.6, h: 0.25, size: 11, min: 9, color: ON_INK });
    tx(s, D.rec.range_display, { x: rx + 0.3, y: ry + rh - 0.6, w: rw - 0.6, h: 0.35, size: 18, min: 13, bold: true, color: ON });
    tx(s, T.deck_method_note, { x: M, y: 4.55, w: W - 2 * M, h: 0.55, size: 11, min: 9.5, lines: 3, color: MUTED, valign: 'top', what: 'the adjustments note' });
    footer(s); notes(s, C.notes.method);
  }

  // 4. Value drivers
  {
    const s = content('what buyers will pay for'); title(s, T.deck_drivers_title);
    const docs = C.document_items.length > 0, dw = docs ? 4.5 : W - 2 * M - 0.75;  // no paperwork box: the drivers take the width
    for (let i = 0; i < C.value_drivers.length; i++) {
      const y = 1.25 + i * 0.88;
      await circleIcon(s, D.icons.value_drivers[i], M, y, 0.55);
      tx(s, C.value_drivers[i][0], { x: M + 0.75, y, w: dw, h: 0.3, size: 15, min: 12, bold: true, color: INK, what: 'deck.value_drivers heading' });
      tx(s, C.value_drivers[i][1], { x: M + 0.75, y: y + 0.31, w: dw, h: 0.46, size: 12, min: 10, lines: 2, color: MUTED, valign: 'top', what: 'deck.value_drivers line' });
    }
    if (docs) card(s, 6.0, 1.25, 3.5, 3.45, LINE);
    if (docs) tx(s, T.deck_docs_title, { x: 6.25, y: 1.45, w: 3.05, h: 0.35, size: 15, min: 12, bold: true, color: STRONG });
    for (let i = 0; i < C.document_items.length; i++) {
      const y = 2.0 + i * 1.3;
      await circleIcon(s, D.icons.document_items[i], 6.25, y, 0.45, DEEP, ON);
      tx(s, C.document_items[i][0], { x: 6.85, y, w: 2.5, h: 0.3, size: 13, min: 11, bold: true, color: INK, what: 'deck.document_items heading' });
      tx(s, C.document_items[i][1], { x: 6.85, y: y + 0.32, w: 2.5, h: 0.85, size: 11, min: 9.5, lines: 5, color: INK, valign: 'top', what: 'deck.document_items line' });
    }
    footer(s); notes(s, C.notes.drivers);
  }

  // 5. Comps dot plot (shapes, so the supported range and the recommendation share one axis)
  {
    const s = content('comparable sales'); title(s, T.deck_comps_title, T.deck_comps_sub);
    const comps = [...D.comps].sort((a, b) => b.adjusted - a.adjusted);
    const lo = Math.floor((Math.min(D.rec.low, ...comps.map(c => c.adjusted)) - 10000) / 20000) * 20000;
    const hi = Math.ceil((Math.max(D.rec.high, ...comps.map(c => c.adjusted)) + 10000) / 20000) * 20000;
    const px = 4.3, pw = 5.0, top = 1.55, rowH = comps.length > 5 ? 0.42 : 0.5;
    const X = v => px + (v - lo) / (hi - lo) * pw;
    const plotH = rowH * comps.length;
    s.addShape(pres.shapes.RECTANGLE, { x: X(D.rec.low), y: top - 0.1, w: X(D.rec.high) - X(D.rec.low), h: plotH + 0.2, fill: { color: TINT }, line: { color: TINT } });
    for (let v = lo; v <= hi; v += 20000) {
      s.addShape(pres.shapes.LINE, { x: X(v), y: top - 0.1, w: 0, h: plotH + 0.2, line: { color: LINE, width: 0.75 } });
      s.addText('$' + Math.round(v / 1000) + 'K', { x: X(v) - 0.4, y: top + plotH + 0.15, w: 0.8, h: 0.25, fontFace: FONT, fontSize: 10, color: MUTED, align: 'center', margin: 0, isTextBox: true });
    }
    s.addShape(pres.shapes.LINE, { x: X(D.rec.list_price), y: top - 0.25, w: 0, h: plotH + 0.35, line: { color: INK, width: 2, dashType: 'dash' } });
    s.addText(fmt(T.deck_dot_rec, { price: D.rec.list_display }), { x: X(D.rec.list_price) - 1.1, y: top - 0.5, w: 2.2, h: 0.25, fontFace: FONT, fontSize: 10, bold: true, color: INK, align: 'center', margin: 0, isTextBox: true });
    comps.forEach((c, i) => {
      const y = top + i * rowH;
      tx(s, c.address, { x: M, y, w: 3.6, h: 0.24, size: 12, min: 10, bold: true, color: INK });
      tx(s, c.line, { x: M, y: y + 0.22, w: 3.6, h: 0.22, size: 9.5, min: 8.5, color: MUTED, what: 'deck.comp_lines' });
      s.addShape(pres.shapes.OVAL, { x: X(c.adjusted) - 0.09, y: y + 0.13, w: 0.18, h: 0.18, fill: { color: COMP }, line: { color: WHITE, width: 1 } });
      // CMA-253: a value the recommended-price line would strike through goes on the dot's left
      const xr = X(D.rec.list_price), struck = xr >= X(c.adjusted) + 0.08 && xr <= X(c.adjusted) + 0.55;
      s.addText(c.adjusted_k, { x: struck ? X(c.adjusted) - 0.82 : X(c.adjusted) + 0.12, y: y + 0.08, w: 0.7, h: 0.26, fontFace: FONT, fontSize: 10,
        color: INK, margin: 0, align: struck ? 'right' : 'left', isTextBox: true });
    });
    const shaded = fmt(T.deck_shaded, { low: D.rec.low_k, high: D.rec.high_k });
    const size = fit(shaded + C.comps_takeaway, W - 2 * M, 0.55, { size: 12, min: 10, lines: 2, what: 'deck.comps_takeaway' });
    s.addText([{ text: shaded, options: { bold: true, color: BRAND } }, { text: C.comps_takeaway, options: { color: INK } }],
      { x: M, y: 4.5, w: W - 2 * M, h: 0.55, fontFace: FONT, fontSize: size, margin: 0, valign: 'top', isTextBox: true });
    footer(s); notes(s, C.notes.comps);
  }

  // 6. Scatter (native chart; per-series markers are finished in deck.py's style_scatter). The chart takes most of
  // the slide; the takeaway is a narrow column beside it, marked by a thin accent bar.
  if (D.scatter) {
    const s = content('scatter'); title(s, T.deck_scatter_title);
    const SC = D.scatter;
    // Brand shades and true grays only (deck.py style_scatter sets the markers), as the PDF's chart (Results_v5): comps
    // in the brand itself, other sales a pale gray dot, listings an open gray ring, the trend a dashed gray line, the
    // subject a black diamond
    const COLOR = { comp: COMP, sold: K.grey_pale, active: MUTED, trend: MUTED, subject: INK };
    const series = SC.series.map(sr => [sr.name, sr.points]);
    const xs = [], cols = series.map(() => []);
    series.forEach(([, pts], si) => pts.forEach(p => { xs.push(p[0]); series.forEach((_, sj) => cols[sj].push(sj === si ? p[1] : null)); }));
    const data = [{ name: 'X', values: xs }].concat(series.map(([nm], i) => ({ name: nm, values: cols[i] })));
    // The plot area is placed by hand (fractions of the chart box), so the supported range band drawn behind the
    // chart lines up with the price axis, as on the PDF's chart (Results_v4 case 02)
    const ch = { x: M - 0.1, y: 0.95, w: 7.15, h: 3.75 }, lay = { x: 0.12, y: 0.03, w: 0.85, h: 0.8 };
    const plot = { x: ch.x + lay.x * ch.w, y: ch.y + lay.y * ch.h, w: lay.w * ch.w, h: lay.h * ch.h };
    const Y = v => plot.y + (SC.y_max - v) / (SC.y_max - SC.y_min) * plot.h;
    const [bl, bh] = SC.band.map(v => Math.min(Math.max(v, SC.y_min), SC.y_max));
    s.addShape(pres.shapes.RECTANGLE, { x: plot.x, y: Y(bh), w: plot.w, h: Y(bl) - Y(bh), fill: { color: TINT }, line: { color: TINT, width: 0 } });
    s.addChart(pres.charts.SCATTER, data, {
      ...ch, layout: lay, lineSize: 0, lineDataSymbol: 'circle', lineDataSymbolSize: 7,
      chartColors: SC.series.map(sr => COLOR[sr.key]),
      valAxisMinVal: SC.y_min, valAxisMaxVal: SC.y_max, valAxisMajorUnit: SC.y_step,
      catAxisMinVal: SC.x_min, catAxisMaxVal: SC.x_max,
      valAxisLabelFormatCode: '$#,##0,"K"', catAxisLabelFormatCode: '#,##0',
      valAxisLabelFontSize: 10, catAxisLabelFontSize: 10, valAxisLabelColor: MUTED, catAxisLabelColor: MUTED,
      showValAxisTitle: true, valAxisTitle: SC.axis_y, valAxisTitleFontSize: 10, valAxisTitleColor: MUTED,
      showCatAxisTitle: true, catAxisTitle: SC.axis_x, catAxisTitleFontSize: 10, catAxisTitleColor: MUTED,
      valGridLine: { color: LINE, size: 0.5 }, catGridLine: { color: LINE, size: 0.5 },
      showLegend: false,  // drawn below as shapes, so each key is the marker's own shape in every viewer
    });
    // Results_v5 case 02: the range's label sits on a tinted box of its own, drawn over the chart so no gridline runs
    // through it, in the first corner of the band (inside it, top then bottom; left then right) clear of every point
    const X = v => plot.x + (v - SC.x_min) / (SC.x_max - SC.x_min) * plot.w;
    const lw = textW(SC.band_label, 9, true) + 0.12, lh = 0.2;
    const pts = SC.series.filter(sr => sr.key !== 'trend').flatMap(sr => sr.points.map(p => [X(p[0]), Y(p[1])]));
    const clear = (x, y) => !pts.some(([px, py]) => px > x - 0.08 && px < x + lw + 0.08 && py > y - 0.08 && py < y + lh + 0.08);
    const spots = [[plot.x + 0.06, Y(bh) + 0.03], [plot.x + plot.w - lw - 0.06, Y(bh) + 0.03],
                   [plot.x + 0.06, Y(bl) - lh - 0.03], [plot.x + plot.w - lw - 0.06, Y(bl) - lh - 0.03]];
    const [bx, by] = spots.find(([x, y]) => clear(x, y)) || spots[0];
    s.addText(SC.band_label, { x: bx, y: by, w: lw, h: lh, fontFace: FONT, fontSize: 9, bold: true, color: STRONG, margin: [0, 0.06, 0, 0.06],
      fill: { color: TINT }, valign: 'middle', isTextBox: true });
    // the legend: each entry the same shape as its marker (no renderer's default legend symbols)
    const LG = { comp: ['oval', COMP, COMP], sold: ['oval', K.grey_pale, K.grey_pale], active: ['oval', WHITE, MUTED], subject: ['diamond', INK, INK] };
    let lx = M + 0.1;
    const ly = ch.y + ch.h + 0.12;
    SC.series.forEach(sr => {
      if (sr.key === 'trend') {
        s.addShape(pres.shapes.LINE, { x: lx, y: ly + 0.08, w: 0.26, h: 0, line: { color: MUTED, width: 1.25, dashType: 'dash' } });
      } else {
        const [shape, fill, line] = LG[sr.key], d = shape === 'diamond' ? 0.16 : sr.key === 'sold' ? 0.1 : 0.13;
        s.addShape(shape === 'diamond' ? pres.shapes.DIAMOND : pres.shapes.OVAL, { x: lx + (0.26 - d) / 2, y: ly + 0.08 - d / 2, w: d, h: d,
          fill: { color: fill }, line: { color: line, width: sr.key === 'active' ? 1.25 : 0.5 } });
      }
      const w = textW(sr.name, 9) + 0.05;
      s.addText(sr.name, { x: lx + 0.32, y: ly, w, h: 0.18, fontFace: FONT, fontSize: 9, color: INK, margin: 0, valign: 'middle', isTextBox: true });
      lx += 0.32 + w + 0.2;
    });
    const cx = 7.75, cw = W - M - cx;
    s.addShape(pres.shapes.RECTANGLE, { x: cx - 0.15, y: 1.25, w: 0.05, h: 3.3, fill: { color: MARK }, line: { color: MARK } });
    const size = tx(s, C.scatter_takeaway, { x: cx, y: 1.25, w: cw, h: 2.2, size: 13, min: 10.5, lines: 11, color: INK, valign: 'top', what: 'deck.scatter_takeaway' });
    const used = lineCount(C.scatter_takeaway, size, cw) * size * LEAD / 72;
    tx(s, D.scatter.trend_note, { x: cx, y: 1.25 + used + 0.2, w: cw, h: 3.3 - used - 0.2, size: 11, min: 9, lines: 9, color: MUTED, valign: 'top', what: 'the size-only trend note' });
    footer(s); notes(s, C.notes.scatter);
  }

  // 7. Market: each card reads top to bottom as label, earlier value, recent value, each tag right above its value
  {
    const s = content('market'); title(s, D.market.title, D.market.subtitle);
    const [early, now] = D.market.period_labels;
    const k = C.market_stats.length, gap = 0.25, cw = (W - 2 * M - gap * (k - 1)) / k, y = 1.45, iw = cw - 0.4;
    const big = Math.min(...C.market_stats.map(m => fit(D.market.one_period ? m[1] : m[2], iw, 0.5, { size: 28, min: 18, bold: true, what: 'deck.market_stats recent value' })));
    for (let i = 0; i < k; i++) {
      const m = C.market_stats[i], x = M + i * (cw + gap);
      card(s, x, y, cw, 2.65, TINT);
      await circleIcon(s, D.icons.market_stats[i], x + 0.2, y + 0.2, 0.45);
      tx(s, m[0], { x: x + 0.2, y: y + 0.75, w: iw, h: 0.42, size: 12, min: 10, lines: 2, bold: true, color: INK, valign: 'top', what: 'deck.market_stats label' });
      if (D.market.one_period) {  // CMA-261: no export, one value per card (no earlier period to compare)
        s.addText(m[1], { x: x + 0.2, y: y + 1.5, w: iw, h: 0.7, fontFace: FONT, fontSize: big, bold: true, color: BRAND, margin: 0, valign: 'middle', isTextBox: true });
        continue;
      }
      s.addText(early, { x: x + 0.2, y: y + 1.27, w: iw, h: 0.2, fontFace: FONT, fontSize: 9, color: MUTED, margin: 0, isTextBox: true });
      tx(s, m[1], { x: x + 0.2, y: y + 1.46, w: iw, h: 0.3, size: 15, min: 11, color: MUTED, what: 'deck.market_stats earlier value' });
      s.addText(now, { x: x + 0.2, y: y + 1.86, w: iw, h: 0.2, fontFace: FONT, fontSize: 9, bold: true, color: STRONG, margin: 0, isTextBox: true });
      s.addText(m[2], { x: x + 0.2, y: y + 2.04, w: iw, h: 0.48, fontFace: FONT, fontSize: big, bold: true, color: BRAND, margin: 0, valign: 'middle', isTextBox: true });
    }
    tx(s, C.market_takeaway, { x: M, y: 4.38, w: W - 2 * M, h: 0.6, size: 14, min: 11, lines: 2, bold: true, color: INK, valign: 'top', what: 'deck.market_takeaway' });
    footer(s); notes(s, C.notes.market);
  }

  // 8. Competition
  {
    const s = content('competition'); title(s, T.deck_comp_title, T.deck_comp_sub);
    const k = D.competition.length, gap = 0.3, cw = k === 3 ? 2.8 : (W - 2 * M - gap) / 2, iw = cw - 0.44;  // one card: the takeaway sits beside it
    D.competition.forEach((c, i) => {
      const x = M + i * (cw + gap), y = 1.5;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: 2.6, fill: { color: WHITE }, line: { color: LINE, width: 1 }, rectRadius: 0.08, shadow: { type: 'outer', color: INK, opacity: 0.12, blur: 6, offset: 2, angle: 90 } });
      tx(s, c[0], { x: x + 0.22, y: y + 0.2, w: iw, h: 0.3, size: 14, min: 11, bold: true, color: INK, what: 'deck.competition address' });
      tx(s, c[1], { x: x + 0.22, y: y + 0.52, w: iw, h: 0.5, size: 26, min: 18, bold: true, color: BRAND });
      tx(s, c[2], { x: x + 0.22, y: y + 1.05, w: iw, h: 0.28, size: 11, min: 9, bold: true, color: STRONG, what: 'deck.competition status line' });
      tx(s, c[3], { x: x + 0.22, y: y + 1.4, w: iw, h: 1.05, size: 12, min: 10, lines: 5, color: INK, valign: 'top', what: 'deck.competition line' });
    });
    const ty = k === 1 ? { x: M + cw + gap, y: 1.7, w: W - 2 * M - cw - gap, h: 2.2, lines: 6 } : { x: M, y: 4.35, w: W - 2 * M, h: 0.55, lines: 2 };
    tx(s, C.competition_takeaway, { ...ty, size: 14, min: 11, bold: true, color: INK, valign: 'top', what: 'deck.competition_takeaway' });
    footer(s); notes(s, C.notes.competition);
  }

  // 9. Pricing strategies: each row's value is measured and its label takes the rest of the card
  {
    const s = content('pricing strategies'); title(s, T.deck_strat_title);
    const k = D.strategies.length, gap = 0.3, cw = Math.min(3.6, (W - 2 * M - gap * (k - 1)) / k), ri = D.recommended_index, iw = cw - 0.44;
    const x0 = (W - k * cw - gap * (k - 1)) / 2;  // fewer than three options: narrower row, centered
    D.strategies.forEach((st, i) => {
      const x = x0 + i * (cw + gap), y = 1.15, hl = i === ri;
      card(s, x, y, cw, 3.3, hl ? BRAND : TINT);
      if (hl) s.addText(T.deck_recommended, { x: x + 0.22, y: y + 0.15, w: iw, h: 0.25, fontFace: FONT, fontSize: 10, bold: true, color: ON, charSpacing: 2, margin: 0, isTextBox: true });
      tx(s, st.list_display, { x: x + 0.22, y: y + 0.42, w: iw, h: 0.6, size: 30, min: 22, bold: true, color: hl ? ON : BRAND });
      const rows = [[T.deck_row_time, st.time], [T.deck_row_expected, st.expected_display], [T.deck_row_credit, st.credit_display]];
      rows.forEach((r, j) => {
        const ry = y + 1.12 + j * 0.42;
        const vs = fit(r[1], iw * 0.6, 0.38, { size: 13, min: 10, bold: true, what: 'strategy value' });
        const vw = Math.min(iw * 0.6, textW(r[1], vs, true) + 0.04);
        tx(s, r[0], { x: x + 0.22, y: ry, w: iw - vw - 0.1, h: 0.38, size: 11, min: 9, color: hl ? ON : MUTED, valign: 'middle', what: 'strategy row label' });
        s.addText(r[1], { x: x + 0.22 + iw - vw, y: ry, w: vw, h: 0.38, fontFace: FONT, fontSize: vs, bold: true, color: hl ? ON : INK, align: 'right', margin: 0, valign: 'middle', isTextBox: true });
      });
      tx(s, st.note, { x: x + 0.22, y: y + 2.45, w: iw, h: 0.75, size: 11, min: 9, lines: 4, color: hl ? ON : INK, valign: 'top', what: 'the strategy note (pricing.strategies note)' });
    });
    tx(s, C.strategy_takeaway, { x: M, y: 4.6, w: W - 2 * M, h: 0.4, size: 14, min: 11, bold: true, color: INK, what: 'deck.strategy_takeaway' });
    footer(s); notes(s, C.notes.strategies);
  }

  // 10. Net proceeds (native column chart)
  {
    const s = content('net proceeds'); title(s, T.deck_net_title, D.net_sub);
    s.addChart(pres.charts.BAR, [{ name: T.deck_net_series, labels: D.strategies.map(x => x.label), values: D.strategies.map(x => x.net) }], {
      x: M, y: 1.35, w: 5.6, h: 3.5, barDir: 'col', chartColors: [MARK], showValue: true, dataLabelPosition: 'outEnd', dataLabelFormatCode: '$#,##0',
      dataLabelFontSize: 13, dataLabelFontBold: true, dataLabelColor: INK, valAxisMinVal: 0, valAxisLabelFormatCode: '$#,##0,"K"',
      valAxisLabelFontSize: 9, catAxisLabelFontSize: 11, valAxisLabelColor: MUTED, catAxisLabelColor: INK,
      valGridLine: { color: LINE, size: 0.5 }, catGridLine: { style: 'none' }, showLegend: false, barGapWidthPct: 60,
    });
    card(s, 6.5, 1.45, 3.0, 3.2, TINT);
    const spread = D.strategies.length > 1, ty = spread ? 2.9 : 1.7;  // one option: no spread to show
    if (spread) tx(s, D.net_spread_display, { x: 6.75, y: 1.65, w: 2.5, h: 0.6, size: 32, min: 22, bold: true, color: BRAND });
    if (spread) tx(s, T.deck_spread, { x: 6.75, y: 2.25, w: 2.5, h: 0.5, size: 11, min: 9, lines: 2, color: MUTED, valign: 'top' });
    tx(s, C.strategy_takeaway, { x: 6.75, y: ty, w: 2.5, h: 4.5 - ty, size: 13, min: 10.5, lines: 7, color: INK, valign: 'top', what: 'deck.strategy_takeaway' });
    footer(s); notes(s, C.notes.nets);
  }

  // 11. Buyer payments
  {
    const s = content('buyer payments'); title(s, T.deck_pay_title, T.deck_pay_sub);
    const k = D.strategies.length, gap = 0.3, cw = Math.min(3.6, (W - 2 * M - gap * (k - 1)) / k), ri = D.recommended_index, iw = cw - 0.44;
    const x0 = (W - k * cw - gap * (k - 1)) / 2;  // fewer than three options: narrower row, centered
    const big = Math.min(...D.strategies.map(st => fit(st.payment_display, iw, 0.6, { size: 28, min: 20, bold: true })));
    D.strategies.forEach((st, i) => {
      const x = x0 + i * (cw + gap), y = 1.45, hl = i === ri;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: 1.9, fill: { color: hl ? TINT : WHITE }, line: { color: hl ? MARK : LINE, width: hl ? 1.5 : 1 }, rectRadius: 0.08 });
      tx(s, st.label, { x: x + 0.22, y: y + 0.2, w: iw, h: 0.3, size: 13, min: 11, bold: true, color: INK });
      s.addText(st.payment_display, { x: x + 0.22, y: y + 0.6, w: iw, h: 0.6, fontFace: FONT, fontSize: big, bold: true, color: BRAND, margin: 0, isTextBox: true });
      tx(s, st.down_display, { x: x + 0.22, y: y + 1.3, w: iw, h: 0.3, size: 11, min: 9, color: MUTED });
    });
    await circleIcon(s, 'FaCalculator', M, 3.75, 0.55);
    tx(s, C.payment_takeaway, { x: M + 0.75, y: 3.7, w: 8.25, h: 0.65, size: 15, min: 12, lines: 2, bold: true, color: INK, valign: 'middle', what: 'deck.payment_takeaway' });
    footer(s); notes(s, C.notes.payments);
  }

  // 12. Launch plan
  {
    const s = content('launch plan'); title(s, T.deck_launch_title, T.deck_launch_sub);
    const cols = C.launch_plan.length === 4 ? 2 : 3, gx = 0.3, gy = 0.25, cw = (W - 2 * M - gx * (cols - 1)) / cols, ch = 1.4;
    for (let i = 0; i < C.launch_plan.length; i++) {
      const c = i % cols, r = Math.floor(i / cols), x = M + c * (cw + gx), y = 1.45 + r * (ch + gy);
      card(s, x, y, cw, ch, TINT);
      await circleIcon(s, D.icons.launch_plan[i], x + 0.18, y + 0.2, 0.45);
      tx(s, C.launch_plan[i][0], { x: x + 0.75, y: y + 0.17, w: cw - 0.9, h: 0.5, size: 13, oneLineMin: 11.5, min: 11, lines: 2, bold: true, color: INK, valign: 'middle', what: 'deck.launch_plan heading' });
      tx(s, C.launch_plan[i][1], { x: x + 0.2, y: y + 0.8, w: cw - 0.4, h: 0.52, size: 11, min: 9.5, lines: 3, color: MUTED, valign: 'top', what: 'deck.launch_plan line' });
    }
    footer(s); notes(s, C.notes.launch);
  }

  // 13. Next steps (dark)
  {
    const s = addSlide('next steps'); s.background = { color: DEEP }; n += 1;
    s.addText(T.deck_next_title, { x: M, y: 0.32, w: 9, h: 0.62, fontFace: FONT, fontSize: 26, bold: true, color: ON, margin: 0, isTextBox: true });
    s.addText(T.deck_needs, { x: M, y: 1.15, w: 4.3, h: 0.35, fontFace: FONT, fontSize: 15, bold: true, color: ON_DARK, margin: 0, isTextBox: true });
    let size = 12.5;  // the list as a whole fits its 3.1" box (bullet indent ~0.3", 6 pt after each item)
    const listH = sz => C.needs_short.reduce((a, t) => a + lineCount(t, sz, 4.0) * sz * LEAD / 72 + 6 / 72, 0);
    while (size > 10 && listH(size) > 3.1) size -= 0.5;
    if (listH(size) > 3.1) {
      const has = C.needs_short.reduce((a, t) => a + String(t).length, 0);
      const most = Math.floor(has * 3.1 / listH(size));  // the same items, scaled to the box at the smallest size
      checks.push(`slide ${slideNo} (${where}): deck.needs_short doesn't fit: at most about ${most} characters fit across the ${C.needs_short.length} items and they have ${has}; shorten the items (or drop one) to ${most} characters or fewer in all and rebuild.`);
    }
    s.addText(C.needs_short.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < C.needs_short.length - 1 } })),
      { x: M, y: 1.6, w: 4.3, h: 3.1, fontFace: FONT, fontSize: size, color: ON, margin: 0, paraSpaceAfter: 6, valign: 'top', isTextBox: true });
    s.addText(T.deck_timeline, { x: 5.4, y: 1.15, w: 4.1, h: 0.35, fontFace: FONT, fontSize: 15, bold: true, color: ON_DARK, margin: 0, isTextBox: true });
    C.timeline.forEach((t, i) => {
      const y = 1.65 + i * (C.timeline.length > 4 ? 0.64 : 0.75);
      s.addShape(pres.shapes.OVAL, { x: 5.4, y, w: 0.42, h: 0.42, fill: { color: ON_DARK }, line: { color: ON_DARK } });
      s.addText(String(i + 1), { x: 5.4, y, w: 0.42, h: 0.42, fontFace: FONT, fontSize: 13, bold: true, color: DEEP, align: 'center', valign: 'middle', margin: 0, isTextBox: true });
      tx(s, t[0], { x: 6.0, y: y - 0.02, w: 3.5, h: 0.25, size: 12, min: 10, bold: true, color: ON, what: 'deck.timeline when' });
      tx(s, t[1], { x: 6.0, y: y + 0.22, w: 3.5, h: 0.42, size: 11, min: 9.5, lines: 2, color: ON_DARK, valign: 'top', what: 'deck.timeline what' });
    });
    if (D.agent.short) s.addText(D.agent.short, { x: M, y: H - 0.45, w: 7, h: 0.3, fontFace: FONT, fontSize: 10, color: ON_DARK, margin: 0, isTextBox: true });
    notes(s, C.notes.next);
  }

  // Appendix tables: row height and font follow the row count and the note under the table, so the note always
  // starts below the last row (renderers grow a row to fit its text: keep the cell margins small). Print-light, as
  // the PDF (Results_v4 case 02): no filled header or banded rows; the header is brand type over a brand rule, rows
  // are split by thin tinted rules, and totals are bold over a brand rule.
  const TY = 1.1, BOTTOM = H - 0.45;
  const NONE = { type: 'none' }, rule = (color, pt) => ({ type: 'solid', pt, color });
  const cell = (text, j, o = {}) => ({ text, options: { align: j === 0 ? 'left' : 'right', fill: { color: WHITE }, ...o } });
  const head = cells => cells.map((h, j) => cell(h, j, { bold: true, color: STRONG, border: [NONE, NONE, rule(MARK, 1.5), NONE] }));
  const body = (cells, total) => cells.map((v, j) => cell(v, j, { bold: total,
    border: [total ? rule(MARK, 1.25) : NONE, NONE, rule(LINE, 0.5), NONE] }));
  const rest = (W - 2 * M - 3.6);
  const appendix = (s, table, cols, note, speaker) => {
    const nRows = table.length;
    // Results_v5 case 02: a label that wraps makes its row taller in every renderer, so count each row's lines (at
    // 10pt, the smaller table size) and leave room for them, or the note lands on the footer
    const lines = table.map(r => Math.max(1, ...r.map((c, j) => Math.min(4, lineCount(String(c.text), 10, cols[j] - 0.14, !!c.options.bold)))));
    const extra = lines.reduce((a, n) => a + (n - 1), 0);
    const tableH = rh => lines.reduce((a, n) => a + Math.max(rh, n * 10 * LEAD / 72 + 0.06), 0);
    let noteSize = 10, noteH = 0;
    const need = sz => lineCount(note, sz, W - 2 * M) * sz * LEAD / 72;
    for (; noteSize >= 8; noteSize -= 0.5) { noteH = need(noteSize); if (TY + tableH(0.24) + 0.15 + noteH <= BOTTOM) break; }
    noteSize = Math.max(noteSize, 8);
    const rowH = Math.max(0.24, Math.min(0.32, (BOTTOM - TY - 0.15 - noteH - extra * 10 * LEAD / 72) / nRows));
    const fontSize = rowH >= 0.28 && !extra ? 11 : 10;
    s.addTable(table, { x: M, y: TY, w: W - 2 * M, colW: cols, rowH, fontFace: FONT, fontSize, color: INK, valign: 'middle',
                        margin: [0.02, 0.06, 0.02, 0.06] });
    const y = TY + tableH(rowH) + 0.15;
    if (y + noteH > BOTTOM + 0.02) {
      const room = BOTTOM + 0.02 - y;
      const most = fitChars(note, t => lineCount(t, noteSize, W - 2 * M) * noteSize * LEAD / 72 <= room);
      checks.push(`slide ${slideNo} (${where}): the table and its note don't fit together: ${tooLong(most, note, 'the note')} and rebuild.`);
    }
    s.addText(note, { x: M, y, w: W - 2 * M, h: Math.max(0.2, BOTTOM - y), fontFace: FONT, fontSize: noteSize, color: MUTED, margin: 0, valign: 'top', isTextBox: true });
    notes(s, speaker || note);
  };

  // Appendix A: net sheet
  {
    const s = content('appendix: net sheet'); title(s, T.deck_app_net_title);
    const k = D.strategies.length, totals = new Set(D.net_total_rows || [D.net_rows.length - 1]);
    const rows = D.net_rows.map((r, i) => body(r, totals.has(i)));
    appendix(s, [head([D.net_head].concat(D.strategies.map(x => x.label)))].concat(rows), [3.6].concat(Array(k).fill(rest / k)), D.net_note, D.net_speaker);
    footer(s);
  }

  // Appendix B: comparable sales + disclaimer; the home's own row bold over a rule, as on the PDF
  {
    const s = content('appendix: comparable sales'); title(s, T.deck_app_comps_title);
    const rows = D.appendix_comps.map(r => body(r, false));
    rows.push(body(D.subject_row, true));
    appendix(s, [head(D.table_head)].concat(rows), [3.6, rest / 3, rest / 3, rest / 3], D.appendix_note, D.appendix_speaker);
    footer(s);
  }

  await pres.writeFile({ fileName: outPath });
  checks.forEach(c => console.error('Check: ' + c));
  console.log('wrote ' + outPath + ' (' + n + ' slides)');
})().catch(e => { console.error(e && e.message ? e.message : String(e)); process.exit(1); });
