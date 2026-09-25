// Build the seller listing presentation: 13 slides plus a 2-slide appendix.
// Usage: node scripts/build_deck.js deck-data.json OUTPUT.pptx   (render.py runs it; see deck.py)
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

// Color roles (all from shared/design): brand_ink carries text and fills behind on_brand text; brand marks
// charts; party_both is the subject and the dark title slides; tints are brand_callout / brand_rule / brand_panel.
const BRAND = K.brand_ink, MARK = K.brand, ON = K.on_brand, NAVY = K.party_both, INK = K.text, MUTED = K.muted,
  TINT = K.brand_callout, LINE = K.brand_rule, PANEL = K.brand_panel, GRAY = K.grey,
  WHITE = K.bg, SLATE = K.party_both_bg, ON_DARK_SOFT = K.party_both_soft, ON_DARK_ACCENT = K.brand_soft;
const FONT = 'Arial';
const fmt = (s, v) => s.replace(/\{(\w+)\}/g, (m, key) => (key in v ? v[key] : m));

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

  const footer = s => {
    n += 1;
    s.addText(D.footer, { x: M, y: H - 0.38, w: 7.5, h: 0.25, fontFace: FONT, fontSize: 8, color: MUTED, margin: 0, isTextBox: true });
    s.addText(String(n), { x: W - M - 0.5, y: H - 0.38, w: 0.5, h: 0.25, fontFace: FONT, fontSize: 8, color: MUTED, align: 'right', margin: 0, isTextBox: true });
  };
  const title = (s, t, sub) => {
    s.addText(t, { x: M, y: 0.32, w: W - 2 * M, h: 0.62, fontFace: FONT, fontSize: 26, bold: true, color: INK, margin: 0, valign: 'top', isTextBox: true });
    if (sub) s.addText(sub, { x: M, y: 0.92, w: W - 2 * M, h: 0.36, fontFace: FONT, fontSize: 13, color: MUTED, margin: 0, isTextBox: true });
  };
  const circleIcon = async (s, name, x, y, d = 0.5, bg = BRAND, fg = ON) => {
    s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: bg }, line: { color: bg } });
    s.addImage({ data: await icon(name, fg), x: x + d * 0.24, y: y + d * 0.24, w: d * 0.52, h: d * 0.52 });
  };
  const content = () => { const s = pres.addSlide(); s.background = { color: WHITE }; return s; };
  const card = (s, x, y, w, h, fill, line) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, fill: { color: fill }, line: { color: line || fill }, rectRadius: 0.08 });

  // 1. Title (dark)
  {
    const s = pres.addSlide(); s.background = { color: NAVY }; n += 1;
    await circleIcon(s, 'FaHome', M, 0.9, 0.7);
    s.addText(C.title, { x: M, y: 1.8, w: 8.5, h: 1.0, fontFace: FONT, fontSize: 38, bold: true, color: ON, margin: 0, fit: 'shrink', isTextBox: true });
    s.addText(C.subtitle, { x: M, y: 2.8, w: 8.5, h: 0.45, fontFace: FONT, fontSize: 16, color: ON_DARK_ACCENT, margin: 0, isTextBox: true });
    const lines = [];
    if (D.agent.name) lines.push({ text: D.agent.name, options: { bold: true, breakLine: true } });
    D.agent.lines.forEach(t => lines.push({ text: t, options: { breakLine: true } }));
    lines.push({ text: D.prepared_date });
    s.addText(lines, { x: M, y: 3.75, w: 7, h: 1.2, fontFace: FONT, fontSize: 12, color: ON_DARK_SOFT, margin: 0, paraSpaceAfter: 2, valign: 'top', isTextBox: true });
    if (D.preliminary) s.addText(T.deck_preliminary, { x: 5.5, y: 0.95, w: 4.0, h: 0.5, fontFace: FONT, fontSize: 11, bold: true, color: ON, align: 'right', margin: 0, isTextBox: true });
    notes(s, T.deck_title_note);
  }

  // 2. Recommendation
  {
    const s = content(); title(s, T.deck_rec_title);
    s.addText(T.deck_rec_label, { x: M, y: 1.35, w: 4.6, h: 0.35, fontFace: FONT, fontSize: 14, color: MUTED, margin: 0, isTextBox: true });
    s.addText(D.rec.list_display, { x: M, y: 1.7, w: 4.8, h: 1.2, fontFace: FONT, fontSize: 64, bold: true, color: BRAND, margin: 0, isTextBox: true });
    s.addText(C.recommendation_why, { x: M, y: 3.1, w: 4.5, h: 1.2, fontFace: FONT, fontSize: 15, color: INK, margin: 0, valign: 'top', isTextBox: true });
    const cards = [[T.deck_range_card, D.rec.range_display, T.deck_range_sub], [T.deck_expected_card, D.expected_sale, T.deck_expected_sub]];
    cards.forEach((c, i) => {
      const y = 1.35 + i * 1.6;
      card(s, 5.7, y, 3.8, 1.35, TINT);
      s.addText(c[0], { x: 5.95, y: y + 0.15, w: 3.4, h: 0.3, fontFace: FONT, fontSize: 12, color: MUTED, margin: 0, isTextBox: true });
      s.addText(c[1], { x: 5.95, y: y + 0.45, w: 3.4, h: 0.5, fontFace: FONT, fontSize: c[1].length > 16 ? 19 : 24, bold: true, color: INK, margin: 0, valign: 'middle', isTextBox: true });
      s.addText(c[2], { x: 5.95, y: y + 0.95, w: 3.4, h: 0.28, fontFace: FONT, fontSize: 11, color: MUTED, margin: 0, isTextBox: true });
    });
    footer(s); notes(s, C.notes.recommendation);
  }

  // 3. How we priced it
  {
    const s = content(); title(s, T.deck_method_title, T.deck_method_sub);
    const m = D.method;
    const steps = [[String(m.n_sold), m.sold_line], [String(m.n_comps), T.deck_step_comps], [m.adj_range, T.deck_step_adjusted],
                   [m.adj_median, T.deck_step_median], [D.rec.list_display, T.deck_step_rec]];
    const bw = 1.58, gap = 0.27, y = 1.75;
    steps.forEach((st, i) => {
      const x = M + i * (bw + gap), last = i === steps.length - 1;
      card(s, x, y, bw, 2.2, last ? BRAND : TINT);
      s.addText(st[0], { x: x + 0.12, y: y + 0.3, w: bw - 0.24, h: 0.7, fontFace: FONT, fontSize: st[0].length > 6 ? 17 : 26, bold: true, color: last ? ON : BRAND, align: 'center', valign: 'middle', margin: 0, isTextBox: true });
      s.addText(st[1], { x: x + 0.12, y: y + 1.1, w: bw - 0.24, h: 0.95, fontFace: FONT, fontSize: 12, color: last ? ON : INK, align: 'center', valign: 'top', margin: 0, isTextBox: true });
      if (!last) s.addShape(pres.shapes.CHEVRON, { x: x + bw + 0.06, y: y + 0.97, w: 0.15, h: 0.26, fill: { color: GRAY }, line: { color: GRAY } });
    });
    s.addText(T.deck_method_note, { x: M, y: 4.3, w: W - 2 * M, h: 0.5, fontFace: FONT, fontSize: 12, color: MUTED, margin: 0, isTextBox: true });
    footer(s); notes(s, C.notes.method);
  }

  // 4. Value drivers
  {
    const s = content(); title(s, T.deck_drivers_title);
    const icons = ['FaHammer', 'FaSwimmingPool', 'FaBed', 'FaWater'];
    for (let i = 0; i < C.value_drivers.length; i++) {
      const y = 1.25 + i * 0.88;
      await circleIcon(s, icons[i % icons.length], M, y, 0.55);
      s.addText(C.value_drivers[i][0], { x: M + 0.75, y, w: 4.4, h: 0.3, fontFace: FONT, fontSize: 15, bold: true, color: INK, margin: 0, isTextBox: true });
      s.addText(C.value_drivers[i][1], { x: M + 0.75, y: y + 0.3, w: 4.4, h: 0.45, fontFace: FONT, fontSize: 12, color: MUTED, margin: 0, valign: 'top', isTextBox: true });
    }
    card(s, 6.0, 1.25, 3.5, 3.4, SLATE);
    s.addText(T.deck_docs_title, { x: 6.25, y: 1.45, w: 3.1, h: 0.35, fontFace: FONT, fontSize: 15, bold: true, color: NAVY, margin: 0, isTextBox: true });
    const dIcons = ['FaHome', 'FaFileAlt'];
    for (let i = 0; i < C.document_items.length; i++) {
      const y = 2.0 + i * 1.25;
      await circleIcon(s, dIcons[i % 2], 6.25, y, 0.45, NAVY, ON);
      s.addText(C.document_items[i][0], { x: 6.85, y, w: 2.5, h: 0.3, fontFace: FONT, fontSize: 13, bold: true, color: INK, margin: 0, isTextBox: true });
      s.addText(C.document_items[i][1], { x: 6.85, y: y + 0.3, w: 2.5, h: 0.8, fontFace: FONT, fontSize: 11, color: INK, margin: 0, valign: 'top', isTextBox: true });
    }
    footer(s); notes(s, C.notes.drivers);
  }

  // 5. Comps dot plot (shapes, so the supported range and the recommendation share one axis)
  {
    const s = content(); title(s, T.deck_comps_title, T.deck_comps_sub);
    const comps = [...D.comps].sort((a, b) => b.adjusted - a.adjusted);
    const lo = Math.floor((Math.min(D.rec.low, ...comps.map(c => c.adjusted)) - 10000) / 20000) * 20000;
    const hi = Math.ceil((Math.max(D.rec.high, ...comps.map(c => c.adjusted)) + 10000) / 20000) * 20000;
    const px = 4.3, pw = 5.2, top = 1.55, rowH = comps.length > 5 ? 0.42 : 0.5;
    const X = v => px + (v - lo) / (hi - lo) * pw;
    const plotH = rowH * comps.length;
    s.addShape(pres.shapes.RECTANGLE, { x: X(D.rec.low), y: top - 0.1, w: X(D.rec.high) - X(D.rec.low), h: plotH + 0.2, fill: { color: TINT }, line: { color: TINT } });
    for (let v = lo; v <= hi; v += 20000) {
      s.addShape(pres.shapes.LINE, { x: X(v), y: top - 0.1, w: 0, h: plotH + 0.2, line: { color: LINE, width: 0.75 } });
      s.addText('$' + Math.round(v / 1000) + 'K', { x: X(v) - 0.4, y: top + plotH + 0.15, w: 0.8, h: 0.25, fontFace: FONT, fontSize: 10, color: MUTED, align: 'center', margin: 0, isTextBox: true });
    }
    s.addShape(pres.shapes.LINE, { x: X(D.rec.list_price), y: top - 0.25, w: 0, h: plotH + 0.35, line: { color: NAVY, width: 2, dashType: 'dash' } });
    s.addText(fmt(T.deck_dot_rec, { price: D.rec.list_display }), { x: X(D.rec.list_price) - 1.1, y: top - 0.5, w: 2.2, h: 0.25, fontFace: FONT, fontSize: 10, bold: true, color: NAVY, align: 'center', margin: 0, isTextBox: true });
    comps.forEach((c, i) => {
      const y = top + i * rowH;
      s.addText(c.address, { x: M, y, w: 3.7, h: 0.24, fontFace: FONT, fontSize: 12, bold: true, color: INK, margin: 0, isTextBox: true });
      s.addText(c.line, { x: M, y: y + 0.22, w: 3.7, h: 0.22, fontFace: FONT, fontSize: 9.5, color: MUTED, margin: 0, isTextBox: true });
      s.addShape(pres.shapes.OVAL, { x: X(c.adjusted) - 0.09, y: y + 0.13, w: 0.18, h: 0.18, fill: { color: MARK }, line: { color: WHITE, width: 1 } });
      s.addText(c.adjusted_k, { x: X(c.adjusted) + 0.12, y: y + 0.08, w: 0.7, h: 0.26, fontFace: FONT, fontSize: 10, color: INK, margin: 0, isTextBox: true });
    });
    s.addText([{ text: fmt(T.deck_shaded, { low: D.rec.low_k, high: D.rec.high_k }), options: { bold: true, color: BRAND } }, { text: C.comps_takeaway, options: { color: INK } }],
      { x: M, y: 4.55, w: W - 2 * M, h: 0.5, fontFace: FONT, fontSize: 12, margin: 0, isTextBox: true });
    footer(s); notes(s, C.notes.comps);
  }

  // 6. Scatter (native chart; per-series markers are finished in deck.py's style_scatter)
  if (D.scatter) {
    const s = content(); title(s, T.deck_scatter_title);
    const COLOR = { comp: MARK, sold: GRAY, active: WHITE, trend: MUTED, subject: NAVY };
    const series = D.scatter.series.map(sr => [sr.name, sr.points]);
    const xs = [], cols = series.map(() => []);
    series.forEach(([, pts], si) => pts.forEach(p => { xs.push(p[0]); series.forEach((_, sj) => cols[sj].push(sj === si ? p[1] : null)); }));
    const data = [{ name: 'X', values: xs }].concat(series.map(([nm], i) => ({ name: nm, values: cols[i] })));
    const allY = series.flatMap(([, p]) => p.map(q => q[1]));
    s.addChart(pres.charts.SCATTER, data, {
      x: M, y: 1.05, w: 6.1, h: 4.1, lineSize: 0, lineDataSymbol: 'circle', lineDataSymbolSize: 7,
      chartColors: D.scatter.series.map(sr => COLOR[sr.key]),
      valAxisMinVal: Math.floor((Math.min(...allY) - 20000) / 50000) * 50000, valAxisMaxVal: Math.ceil((Math.max(...allY) + 20000) / 50000) * 50000,
      catAxisMinVal: Math.floor((Math.min(...xs) - 50) / 200) * 200, catAxisMaxVal: Math.ceil((Math.max(...xs) + 50) / 200) * 200,
      valAxisLabelFormatCode: '$#,##0,"K"', catAxisLabelFormatCode: '#,##0',
      valAxisLabelFontSize: 9, catAxisLabelFontSize: 9, valAxisLabelColor: MUTED, catAxisLabelColor: MUTED,
      showValAxisTitle: true, valAxisTitle: D.scatter.axis_y, valAxisTitleFontSize: 10, valAxisTitleColor: MUTED,
      showCatAxisTitle: true, catAxisTitle: D.scatter.axis_x, catAxisTitleFontSize: 10, catAxisTitleColor: MUTED,
      valGridLine: { color: LINE, size: 0.5 }, catGridLine: { color: LINE, size: 0.5 },
      showLegend: true, legendPos: 'b', legendFontSize: 9, legendColor: INK,
    });
    card(s, 6.85, 1.25, 2.65, 2.75, TINT);
    s.addText(C.scatter_takeaway, { x: 7.05, y: 1.45, w: 2.3, h: 1.55, fontFace: FONT, fontSize: 13, color: INK, margin: 0, valign: 'top', isTextBox: true });
    s.addText(D.scatter.trend_note, { x: 7.05, y: 3.05, w: 2.3, h: 0.85, fontFace: FONT, fontSize: 11, color: MUTED, margin: 0, valign: 'top', isTextBox: true });
    footer(s); notes(s, C.notes.scatter);
  }

  // 7. Market
  {
    const s = content(); title(s, D.market.title, D.market.subtitle);
    const icons = ['FaPercent', 'FaClock', 'FaHandHoldingUsd', 'FaChartLine'];
    const [early, now] = D.market.period_labels;
    const cw = 2.05, gap = 0.3;
    for (let i = 0; i < C.market_stats.length; i++) {
      const m = C.market_stats[i], x = M + i * (cw + gap), y = 1.55;
      card(s, x, y, cw, 2.3, TINT);
      await circleIcon(s, icons[i % icons.length], x + 0.2, y + 0.2, 0.45);
      s.addText(m[0], { x: x + 0.2, y: y + 0.75, w: cw - 0.4, h: 0.5, fontFace: FONT, fontSize: 12, color: MUTED, margin: 0, valign: 'top', isTextBox: true });
      s.addText(m[1], { x: x + 0.2, y: y + 1.3, w: cw - 0.4, h: 0.3, fontFace: FONT, fontSize: 13, color: MUTED, margin: 0, isTextBox: true });
      s.addText(early, { x: x + 0.2, y: y + 1.3, w: cw - 0.4, h: 0.3, fontFace: FONT, fontSize: 9, color: MUTED, align: 'right', margin: 0, isTextBox: true });
      s.addText(m[2], { x: x + 0.2, y: y + 1.62, w: cw - 0.4, h: 0.5, fontFace: FONT, fontSize: 26, bold: true, color: BRAND, margin: 0, isTextBox: true });
      s.addText(now, { x: x + 0.2, y: y + 1.75, w: cw - 0.4, h: 0.3, fontFace: FONT, fontSize: 9, color: MUTED, align: 'right', margin: 0, isTextBox: true });
    }
    s.addText(C.market_takeaway, { x: M, y: 4.2, w: W - 2 * M, h: 0.5, fontFace: FONT, fontSize: 14, bold: true, color: INK, margin: 0, isTextBox: true });
    footer(s); notes(s, C.notes.market);
  }

  // 8. Competition
  {
    const s = content(); title(s, T.deck_comp_title, T.deck_comp_sub);
    const cw = 2.8, gap = 0.3;
    D.competition.forEach((c, i) => {
      const x = M + i * (cw + gap), y = 1.5;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: 2.55, fill: { color: WHITE }, line: { color: LINE, width: 1 }, rectRadius: 0.08, shadow: { type: 'outer', color: INK, opacity: 0.12, blur: 6, offset: 2, angle: 90 } });
      s.addText(c[0], { x: x + 0.22, y: y + 0.2, w: cw - 0.44, h: 0.3, fontFace: FONT, fontSize: 14, bold: true, color: INK, margin: 0, isTextBox: true });
      s.addText(c[1], { x: x + 0.22, y: y + 0.52, w: cw - 0.44, h: 0.5, fontFace: FONT, fontSize: 26, bold: true, color: BRAND, margin: 0, isTextBox: true });
      s.addText(c[2], { x: x + 0.22, y: y + 1.05, w: cw - 0.44, h: 0.28, fontFace: FONT, fontSize: 11, bold: true, color: NAVY, margin: 0, isTextBox: true });
      s.addText(c[3], { x: x + 0.22, y: y + 1.4, w: cw - 0.44, h: 1.0, fontFace: FONT, fontSize: 12, color: INK, margin: 0, valign: 'top', isTextBox: true });
    });
    s.addText(C.competition_takeaway, { x: M, y: 4.35, w: W - 2 * M, h: 0.4, fontFace: FONT, fontSize: 14, bold: true, color: INK, margin: 0, isTextBox: true });
    footer(s); notes(s, C.notes.competition);
  }

  // 9. Pricing strategies
  {
    const s = content(); title(s, T.deck_strat_title);
    const k = D.strategies.length, gap = 0.3, cw = (W - 2 * M - gap * (k - 1)) / k, ri = D.recommended_index;
    D.strategies.forEach((st, i) => {
      const x = M + i * (cw + gap), y = 1.15, hl = i === ri;
      card(s, x, y, cw, 3.25, hl ? BRAND : TINT);
      if (hl) s.addText(T.deck_recommended, { x: x + 0.22, y: y + 0.15, w: cw - 0.44, h: 0.25, fontFace: FONT, fontSize: 10, bold: true, color: ON, charSpacing: 2, margin: 0, isTextBox: true });
      s.addText(st.list_display, { x: x + 0.22, y: y + 0.42, w: cw - 0.44, h: 0.6, fontFace: FONT, fontSize: 30, bold: true, color: hl ? ON : BRAND, margin: 0, isTextBox: true });
      const rows = [[T.deck_row_time, st.time], [T.deck_row_expected, st.expected_display], [T.deck_row_credit, st.credit_display]];
      rows.forEach((r, j) => {
        s.addText(r[0], { x: x + 0.22, y: y + 1.15 + j * 0.45, w: 1.4, h: 0.4, fontFace: FONT, fontSize: 11, color: hl ? ON : MUTED, margin: 0, valign: 'middle', isTextBox: true });
        s.addText(r[1], { x: x + 1.5, y: y + 1.15 + j * 0.45, w: cw - 1.72, h: 0.4, fontFace: FONT, fontSize: 13, bold: true, color: hl ? ON : INK, align: 'right', margin: 0, valign: 'middle', isTextBox: true });
      });
      s.addText(st.note, { x: x + 0.22, y: y + 2.5, w: cw - 0.44, h: 0.65, fontFace: FONT, fontSize: 11, color: hl ? ON : INK, margin: 0, valign: 'top', isTextBox: true });
    });
    s.addText(C.strategy_takeaway, { x: M, y: 4.6, w: W - 2 * M, h: 0.35, fontFace: FONT, fontSize: 14, bold: true, color: INK, margin: 0, isTextBox: true });
    footer(s); notes(s, C.notes.strategies);
  }

  // 10. Net proceeds (native column chart)
  {
    const s = content(); title(s, T.deck_net_title, D.net_sub);
    s.addChart(pres.charts.BAR, [{ name: T.deck_net_series, labels: D.strategies.map(x => x.label), values: D.strategies.map(x => x.net) }], {
      x: M, y: 1.35, w: 5.6, h: 3.5, barDir: 'col', chartColors: [MARK], showValue: true, dataLabelPosition: 'outEnd', dataLabelFormatCode: '$#,##0',
      dataLabelFontSize: 13, dataLabelFontBold: true, dataLabelColor: INK, valAxisMinVal: 0, valAxisLabelFormatCode: '$#,##0,"K"',
      valAxisLabelFontSize: 9, catAxisLabelFontSize: 11, valAxisLabelColor: MUTED, catAxisLabelColor: INK,
      valGridLine: { color: LINE, size: 0.5 }, catGridLine: { style: 'none' }, showLegend: false, barGapWidthPct: 60,
    });
    card(s, 6.5, 1.45, 3.0, 3.2, TINT);
    s.addText(D.net_spread_display, { x: 6.75, y: 1.65, w: 2.5, h: 0.6, fontFace: FONT, fontSize: 32, bold: true, color: BRAND, margin: 0, isTextBox: true });
    s.addText(T.deck_spread, { x: 6.75, y: 2.25, w: 2.5, h: 0.5, fontFace: FONT, fontSize: 11, color: MUTED, margin: 0, valign: 'top', isTextBox: true });
    s.addText(C.strategy_takeaway, { x: 6.75, y: 2.9, w: 2.5, h: 1.2, fontFace: FONT, fontSize: 13, color: INK, margin: 0, valign: 'top', isTextBox: true });
    footer(s); notes(s, C.notes.nets);
  }

  // 11. Buyer payments
  {
    const s = content(); title(s, T.deck_pay_title, T.deck_pay_sub);
    const k = D.strategies.length, gap = 0.3, cw = (W - 2 * M - gap * (k - 1)) / k, ri = D.recommended_index;
    D.strategies.forEach((st, i) => {
      const x = M + i * (cw + gap), y = 1.45, hl = i === ri;
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: 1.9, fill: { color: hl ? SLATE : WHITE }, line: { color: hl ? NAVY : LINE, width: hl ? 1.5 : 1 }, rectRadius: 0.08 });
      s.addText(st.label, { x: x + 0.22, y: y + 0.2, w: cw - 0.44, h: 0.3, fontFace: FONT, fontSize: 13, bold: true, color: INK, margin: 0, isTextBox: true });
      s.addText(st.payment_display, { x: x + 0.22, y: y + 0.6, w: cw - 0.44, h: 0.6, fontFace: FONT, fontSize: 28, bold: true, color: NAVY, margin: 0, isTextBox: true });
      s.addText(st.down_display, { x: x + 0.22, y: y + 1.3, w: cw - 0.44, h: 0.3, fontFace: FONT, fontSize: 11, color: MUTED, margin: 0, isTextBox: true });
    });
    await circleIcon(s, 'FaCalculator', M, 3.75, 0.55);
    s.addText(C.payment_takeaway, { x: M + 0.75, y: 3.75, w: 8.2, h: 0.55, fontFace: FONT, fontSize: 15, bold: true, color: INK, margin: 0, valign: 'middle', isTextBox: true });
    footer(s); notes(s, C.notes.payments);
  }

  // 12. Launch plan
  {
    const s = content(); title(s, T.deck_launch_title, T.deck_launch_sub);
    const icons = ['FaHome', 'FaSearch', 'FaFileAlt', 'FaKey', 'FaHandHoldingUsd', 'FaCalendarCheck'];
    const cw = 2.8, ch = 1.35, gx = 0.3, gy = 0.3;
    for (let i = 0; i < C.launch_plan.length; i++) {
      const c = i % 3, r = Math.floor(i / 3), x = M + c * (cw + gx), y = 1.45 + r * (ch + gy);
      card(s, x, y, cw, ch, TINT);
      await circleIcon(s, icons[i % icons.length], x + 0.2, y + 0.22, 0.45);
      s.addText(C.launch_plan[i][0], { x: x + 0.8, y: y + 0.22, w: cw - 1.0, h: 0.45, fontFace: FONT, fontSize: 13, bold: true, color: INK, margin: 0, valign: 'middle', isTextBox: true });
      s.addText(C.launch_plan[i][1], { x: x + 0.2, y: y + 0.78, w: cw - 0.4, h: 0.5, fontFace: FONT, fontSize: 11, color: MUTED, margin: 0, valign: 'top', isTextBox: true });
    }
    footer(s); notes(s, C.notes.launch);
  }

  // 13. Next steps (dark)
  {
    const s = pres.addSlide(); s.background = { color: NAVY }; n += 1;
    s.addText(T.deck_next_title, { x: M, y: 0.32, w: 9, h: 0.62, fontFace: FONT, fontSize: 26, bold: true, color: ON, margin: 0, isTextBox: true });
    s.addText(T.deck_needs, { x: M, y: 1.15, w: 4.3, h: 0.35, fontFace: FONT, fontSize: 15, bold: true, color: ON_DARK_ACCENT, margin: 0, isTextBox: true });
    s.addText(C.needs_short.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < C.needs_short.length - 1 } })),
      { x: M, y: 1.6, w: 4.3, h: 3.0, fontFace: FONT, fontSize: 12.5, color: ON, margin: 0, paraSpaceAfter: 6, valign: 'top', isTextBox: true });
    s.addText(T.deck_timeline, { x: 5.4, y: 1.15, w: 4.1, h: 0.35, fontFace: FONT, fontSize: 15, bold: true, color: ON_DARK_ACCENT, margin: 0, isTextBox: true });
    C.timeline.forEach((t, i) => {
      const y = 1.65 + i * 0.75;
      s.addShape(pres.shapes.OVAL, { x: 5.4, y, w: 0.42, h: 0.42, fill: { color: BRAND }, line: { color: BRAND } });
      s.addText(String(i + 1), { x: 5.4, y, w: 0.42, h: 0.42, fontFace: FONT, fontSize: 13, bold: true, color: ON, align: 'center', valign: 'middle', margin: 0, isTextBox: true });
      s.addText(t[0], { x: 6.0, y: y - 0.02, w: 3.5, h: 0.25, fontFace: FONT, fontSize: 12, bold: true, color: ON, margin: 0, isTextBox: true });
      s.addText(t[1], { x: 6.0, y: y + 0.22, w: 3.5, h: 0.3, fontFace: FONT, fontSize: 11, color: ON_DARK_SOFT, margin: 0, isTextBox: true });
    });
    if (D.agent.short) s.addText(D.agent.short, { x: M, y: H - 0.45, w: 7, h: 0.3, fontFace: FONT, fontSize: 10, color: ON_DARK_SOFT, margin: 0, isTextBox: true });
    notes(s, C.notes.next);
  }

  const tableOpts = cols => ({ x: M, y: 1.1, w: W - 2 * M, colW: cols, fontFace: FONT, fontSize: 11, color: INK, border: { type: 'solid', pt: 0.5, color: LINE }, rowH: 0.34, margin: 0.06 });
  const head = cells => cells.map((h, j) => ({ text: h, options: { bold: true, color: ON, fill: { color: BRAND }, align: j === 0 ? 'left' : 'right' } }));
  const rest = (W - 2 * M - 3.6);

  // Appendix A: net sheet
  {
    const s = content(); title(s, T.deck_app_net_title);
    const k = D.strategies.length;
    const rows = D.net_rows.map((r, i) => r.map((v, j) => {
      const last = i === D.net_rows.length - 1;
      return { text: v, options: { bold: last, align: j === 0 ? 'left' : 'right', fill: { color: last ? TINT : (i % 2 ? PANEL : WHITE) } } };
    }));
    s.addTable([head([D.net_head].concat(D.strategies.map(x => x.label)))].concat(rows), tableOpts([3.6].concat(Array(k).fill(rest / k))));
    const y = Math.min(1.1 + 0.34 * (rows.length + 1) + 0.2, 4.2);
    s.addText(D.net_note, { x: M, y, w: W - 2 * M, h: H - 0.5 - y, fontFace: FONT, fontSize: 9.5, color: MUTED, margin: 0, valign: 'top', fit: 'shrink', isTextBox: true });
    footer(s);
  }

  // Appendix B: comparable sales + disclaimer
  {
    const s = content(); title(s, T.deck_app_comps_title);
    const rows = D.appendix_comps.map((r, i) => r.map((v, j) => ({ text: v, options: { align: j === 0 ? 'left' : 'right', fill: { color: i % 2 ? PANEL : WHITE } } })));
    rows.push(D.subject_row.map((v, j) => ({ text: v, options: { bold: j !== 2, color: NAVY, align: j === 0 ? 'left' : 'right', fill: { color: SLATE } } })));
    s.addTable([head(D.table_head)].concat(rows), tableOpts([3.6, rest / 3, rest / 3, rest / 3]));
    const y = Math.min(1.1 + 0.34 * (rows.length + 1) + 0.25, 4.0);
    s.addText(D.appendix_note, { x: M, y, w: W - 2 * M, h: H - 0.5 - y, fontFace: FONT, fontSize: 10, color: MUTED, margin: 0, valign: 'top', fit: 'shrink', isTextBox: true });
    footer(s);
  }

  await pres.writeFile({ fileName: outPath });
  console.log('wrote ' + outPath + ' (' + n + ' slides)');
})().catch(e => { console.error(e && e.message ? e.message : String(e)); process.exit(1); });
