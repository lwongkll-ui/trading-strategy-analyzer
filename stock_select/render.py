"""Render the self-contained stock selection page.

The generated file embeds every scored row as JSON and does all filtering,
sorting, heat-mapping and CSV export client-side, so the page works offline
from the filesystem with no server and no CDN.
"""
from __future__ import annotations

import json

import config

# Palette and factor weights are injected from `config` so the page and the
# scoring model can never drift apart.
_CSS_VARS = "\n".join(f"    --{k}: {v};" for k, v in config.PALETTE.items())

_FACTOR_META = [
    ("trend", "T", "Trend",
     "Where price sits against the 10/50/200-day moving averages, and which way "
     "the 200-day is pointing."),
    ("momentum", "M", "Momentum",
     "12-1 month momentum, 3-month and 1-month return, and how close the name is "
     "to its 52-week high."),
    ("quality", "Q", "Quality",
     "Return on equity, profit margin and revenue growth, less balance-sheet "
     "leverage."),
    ("value", "V", "Value",
     "Trailing P/E, price/book, price/sales and EV/EBITDA — cheaper ranks higher. "
     "Loss-making multiples rank worst, not best."),
]


def _style() -> str:
    return """
:root {
""" + _CSS_VARS + """
  color-scheme: dark;
  --hit: 26px;
}
* { box-sizing: border-box; }
html, body { background: var(--page); }
body {
  margin: 0; padding: 28px 24px 64px;
  color: var(--text);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 14px; line-height: 1.45;
  -webkit-font-smoothing: antialiased;
}
h1, h2, h3 { margin: 0; font-weight: 600; }
a { color: var(--accent); }

.wrap { max-width: 1560px; margin: 0 auto; }

/* ── header ─────────────────────────────────────────────────────────────── */
.head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 12px 18px; margin-bottom: 6px; }
.head h1 { font-size: 24px; letter-spacing: -0.01em; }
.head .stamp { color: var(--dim); font-size: 13px; }
.chip {
  display: inline-flex; align-items: center; gap: 6px;
  background: var(--card2); border: 1px solid var(--line);
  border-radius: 999px; padding: 3px 11px; font-size: 12.5px; color: var(--dim);
}
.demo-banner {
  margin: 14px 0 0; padding: 12px 16px; border-radius: 10px;
  background: #2a1608; border: 1px solid #5a3a12; color: #f0c98a; font-size: 13.5px;
}
.demo-banner b { color: var(--gold); }

/* ── hero + stat tiles ──────────────────────────────────────────────────── */
.topgrid { display: grid; grid-template-columns: minmax(230px, 1fr) 3fr; gap: 14px; margin: 20px 0 18px; }
@media (max-width: 900px) { .topgrid { grid-template-columns: 1fr; } }
.card {
  background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; padding: 16px 18px;
}
.hero .label { color: var(--dim); font-size: 13px; }
.hero .value { font-size: 52px; font-weight: 600; line-height: 1.05; margin: 2px 0 2px; }
.hero .sub { color: var(--dim); font-size: 12.5px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; }
.tile .label { color: var(--dim); font-size: 12.5px; }
.tile .value { font-size: 27px; font-weight: 600; margin: 3px 0 1px; }
.tile .sub { color: var(--dim); font-size: 12px; }
.tile .sub .k { color: var(--text); font-variant-numeric: tabular-nums; }

/* ── filters ────────────────────────────────────────────────────────────── */
.filters {
  display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px 16px;
  background: var(--card); border: 1px solid var(--line);
  border-radius: 12px; padding: 14px 18px; margin-bottom: 18px;
}
.fgroup { display: flex; flex-direction: column; gap: 5px; }
.fgroup > span { color: var(--dim); font-size: 11.5px; letter-spacing: .07em; text-transform: uppercase; }
select, input[type="search"] {
  background: var(--card2); color: var(--text);
  border: 1px solid var(--line); border-radius: 8px;
  padding: 7px 10px; font: inherit; font-size: 13px; min-height: var(--hit);
}
input[type="search"] { min-width: 210px; }
select:focus-visible, input:focus-visible, button:focus-visible, .th:focus-visible,
.tile:focus-visible, .hm-cell:focus-visible, .fx:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.toggles { display: flex; gap: 8px; }
.toggle {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--card2); border: 1px solid var(--line);
  border-radius: 8px; padding: 6px 11px; min-height: var(--hit);
  font-size: 13px; cursor: pointer; user-select: none;
}
.toggle input { accent-color: var(--accent); width: 15px; height: 15px; }
.toggle.on { border-color: var(--accent); color: var(--text); }
.slider { display: flex; align-items: center; gap: 10px; }
.slider input[type="range"] { width: 132px; accent-color: var(--accent); }
.slider output { font-variant-numeric: tabular-nums; min-width: 22px; color: var(--text); }
button {
  background: var(--card2); color: var(--text);
  border: 1px solid var(--line); border-radius: 8px;
  padding: 7px 13px; font: inherit; font-size: 13px; min-height: var(--hit); cursor: pointer;
}
button:hover { border-color: var(--accent); }
.spacer { flex: 1 1 auto; }

/* ── section headings ───────────────────────────────────────────────────── */
.sect {
  display: flex; align-items: baseline; gap: 12px;
  color: var(--dim); letter-spacing: .12em; font-size: 11.5px;
  font-weight: 600; text-transform: uppercase; margin: 26px 0 10px;
}
.sect .note { letter-spacing: 0; text-transform: none; font-weight: 400; font-size: 12.5px; }

/* ── table ──────────────────────────────────────────────────────────────── */
.tablecard { background: var(--card); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
.tablescroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
thead th {
  position: sticky; top: 0; z-index: 2;
  background: var(--card2); color: var(--dim);
  font-weight: 600; font-size: 11.5px; letter-spacing: .05em; text-transform: uppercase;
  text-align: right; padding: 10px 10px; white-space: nowrap;
  border-bottom: 1px solid var(--line);
}
thead th.l { text-align: left; }
thead th.c { text-align: center; }
.th { cursor: pointer; user-select: none; }
.th:hover { color: var(--text); }
.th .arrow { opacity: .55; font-size: 10px; }
tbody td {
  padding: 9px 10px; text-align: right; white-space: nowrap;
  border-bottom: 1px solid var(--line); vertical-align: middle;
  font-variant-numeric: tabular-nums;
}
tbody td.l { text-align: left; font-variant-numeric: normal; }
tbody td.c { text-align: center; }
tbody tr.row { cursor: pointer; }
tbody tr.row:hover td { background: var(--card2); }
tbody tr.row.open td { background: var(--card2); }
.sym { font-weight: 600; letter-spacing: -0.01em; }
.coname { color: var(--dim); font-size: 11.5px; max-width: 210px; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.mkt { color: var(--muted); font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; }
.pos { color: var(--pos); } .neg { color: var(--neg); } .dim { color: var(--dim); }

/* badges — status reads from an icon glyph + label, never colour alone */
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  border: 1px solid var(--line); border-radius: 999px;
  padding: 2px 8px; font-size: 11px; white-space: nowrap; color: var(--dim);
}
.badge.bull { color: var(--pos); border-color: #1d5a44; }
.badge.bear { color: var(--neg); border-color: #6b2b2b; }
.badge.golden { color: var(--gold); border-color: #5a4718; }
.badge.death { color: var(--neg); border-color: #6b2b2b; }
.grade {
  display: inline-block; min-width: 30px; text-align: center;
  border: 1px solid var(--line); border-radius: 6px;
  padding: 2px 5px; font-size: 11.5px; font-weight: 600; color: var(--dim);
}
.grade.hi { color: var(--text); border-color: #2c5a8a; }

/* score meter — sequential accent fill on a lighter step of its own ramp */
.meter { display: flex; align-items: center; gap: 9px; justify-content: flex-end; }
.meter .track {
  width: 84px; height: 8px; border-radius: 4px;
  background: #1c3552;              /* lighter step of the accent ramp */
  overflow: hidden;
}
.meter .fill { height: 100%; background: var(--accent); border-radius: 0 4px 4px 0; }
.meter .num { font-weight: 600; min-width: 30px; text-align: right; }

/* factor micro-bars — one measure (percentile) across four attributes */
.fx { display: inline-flex; align-items: flex-end; gap: 3px; height: 26px; }
.fx .bar { width: 9px; background: #1c3552; border-radius: 2px 2px 0 0; position: relative; height: 100%; }
.fx .bar i { position: absolute; left: 0; right: 0; bottom: 0; background: var(--accent); border-radius: 2px 2px 0 0; }
.fx .bar.imputed i { background: repeating-linear-gradient(135deg, #3d4c5e 0 3px, #2a3644 3px 6px); }

.spark { display: block; }

/* detail panel */
tr.detail > td { background: var(--card2); padding: 0; border-bottom: 1px solid var(--line); }
.detail-inner { padding: 16px 18px 20px; display: grid;
  grid-template-columns: repeat(auto-fit, minmax(235px, 1fr)); gap: 18px 26px; }
.dgroup h4 { margin: 0 0 8px; font-size: 11.5px; letter-spacing: .08em;
  text-transform: uppercase; color: var(--dim); font-weight: 600; }
.dgroup dl { margin: 0; display: grid; grid-template-columns: 1fr auto; gap: 4px 12px; }
.dgroup dt { color: var(--dim); font-size: 12.5px; }
.dgroup dd { margin: 0; font-size: 12.5px; font-variant-numeric: tabular-nums; text-align: right; }

.empty { padding: 40px 18px; text-align: center; color: var(--dim); }

/* ── heat map ───────────────────────────────────────────────────────────── */
.hm { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px 18px 18px; }
.hm-market + .hm-market { margin-top: 22px; }
.hm-market > h3 { font-size: 13.5px; margin-bottom: 10px; }
.hm-sector { margin-top: 12px; }
.hm-sector > h4 {
  margin: 0 0 5px; font-size: 11.5px; font-weight: 600; color: var(--dim);
  letter-spacing: .05em; display: flex; gap: 8px; align-items: baseline;
}
.hm-sector > h4 .cnt { color: var(--muted); font-weight: 400; letter-spacing: 0; }
.hm-row { display: flex; gap: 2px; }   /* 2px surface gap between fills */
.hm-row + .hm-row { margin-top: 2px; }
.hm-cell {
  flex: 1 1 auto; min-width: 54px; height: 42px;
  border-radius: 3px; padding: 4px 6px; cursor: pointer;
  display: flex; flex-direction: column; justify-content: center; overflow: hidden;
}
.hm-cell:hover { filter: brightness(1.18); }
.hm-cell .t { font-size: 11px; font-weight: 600; line-height: 1.15;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hm-cell .v { font-size: 10.5px; line-height: 1.15; font-variant-numeric: tabular-nums; opacity: .9; }
.hm-legend { display: flex; align-items: center; gap: 10px; margin-top: 16px;
  color: var(--dim); font-size: 11.5px; }
.hm-legend .ramp { display: flex; height: 9px; border-radius: 4px; overflow: hidden; width: 220px; }
.hm-legend .ramp span { flex: 1; }

/* ── tooltip ────────────────────────────────────────────────────────────── */
#tip {
  position: fixed; z-index: 50; pointer-events: none; opacity: 0;
  transition: opacity .09s; max-width: 280px;
  background: #05050a; border: 1px solid var(--line); border-radius: 8px;
  padding: 9px 11px; font-size: 12.5px; box-shadow: 0 8px 24px rgba(0,0,0,.55);
}
#tip .th-l { font-weight: 600; margin-bottom: 4px; }
#tip .r { display: flex; justify-content: space-between; gap: 16px; }
#tip .r .k { color: var(--dim); }
#tip .r .v { font-weight: 600; font-variant-numeric: tabular-nums; }
#tip .key { display: inline-block; width: 10px; height: 2px; vertical-align: middle;
  margin-right: 6px; border-radius: 1px; }

/* ── methodology ────────────────────────────────────────────────────────── */
.method { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 18px; }
.method .m { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 15px 17px; }
.method h4 { margin: 0 0 6px; font-size: 13px; }
.method p { margin: 0; color: var(--dim); font-size: 12.5px; line-height: 1.5; }
.method .w { color: var(--gold); font-size: 11.5px; letter-spacing: .04em; }
.disclaimer { margin-top: 20px; color: var(--muted); font-size: 12px; line-height: 1.6; }

@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
"""


def _script() -> str:
    return r"""
'use strict';

const D = window.__SELECT__;
const ROWS = D.rows;
const FACTORS = D.factors;            // [{key, letter, label, blurb}, ...]
const PAL = getComputedStyle(document.documentElement);
const COLOR = k => PAL.getPropertyValue('--' + k).trim();

/* ── formatting ───────────────────────────────────────────────────────────── */
const DASH = '—';
const nf = (v, dp = 2) => v === null || v === undefined || Number.isNaN(v)
  ? DASH : v.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
const pct = (v, dp = 1) => v === null || v === undefined || Number.isNaN(v)
  ? DASH : (v >= 0 ? '+' : '') + (v * 100).toFixed(dp) + '%';
const pctPlain = (v, dp = 1) => v === null || v === undefined || Number.isNaN(v)
  ? DASH : (v * 100).toFixed(dp) + '%';
function cap(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return DASH;
  const u = [[1e12, 'T'], [1e9, 'B'], [1e6, 'M'], [1e3, 'K']];
  for (const [s, l] of u) if (Math.abs(v) >= s) return (v / s).toFixed(v / s >= 100 ? 0 : 1) + l;
  return v.toFixed(0);
}
const signCls = v => (v === null || v === undefined || Number.isNaN(v)) ? 'dim' : (v >= 0 ? 'pos' : 'neg');

/* ── dom helpers — text is always inserted as a text node, never as HTML,
      because tickers, company names and sectors come from CSV / API data ──── */
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}
const $ = sel => document.querySelector(sel);

/* ── state ────────────────────────────────────────────────────────────────── */
const state = {
  markets: new Set(D.markets),
  stack: 'any', cross: 'any', rsi: 'any', sector: 'any',
  minScore: 0, q: '',
  sortKey: 'score', sortDir: -1,
  open: null,
};

function passes(r) {
  if (!state.markets.has(r.market)) return false;
  if (state.stack === 'above' && !r.above_sma200) return false;
  if (state.stack === 'below' && r.above_sma200) return false;
  if (state.stack === 'bull' && r.stack !== 'bull') return false;
  if (state.stack === 'bear' && r.stack !== 'bear') return false;
  if (state.cross !== 'any' && r.cross !== state.cross) return false;
  if (state.rsi === 'overbought' && !(r.rsi !== null && r.rsi >= D.rsiOverbought)) return false;
  if (state.rsi === 'oversold' && !(r.rsi !== null && r.rsi <= D.rsiOversold)) return false;
  if (state.rsi === 'neutral' && !(r.rsi !== null && r.rsi > D.rsiOversold && r.rsi < D.rsiOverbought)) return false;
  if (state.sector !== 'any' && r.sector !== state.sector) return false;
  if (r.score < state.minScore) return false;
  if (state.q) {
    const q = state.q.toLowerCase();
    if (!r.ticker.toLowerCase().includes(q) && !(r.name || '').toLowerCase().includes(q)) return false;
  }
  return true;
}

function selection() {
  const out = ROWS.filter(passes);
  const k = state.sortKey, dir = state.sortDir;
  out.sort((a, b) => {
    let x = a[k], y = b[k];
    if (typeof x === 'string' || typeof y === 'string') {
      return String(x ?? '').localeCompare(String(y ?? '')) * dir;
    }
    const xn = (x === null || x === undefined || Number.isNaN(x));
    const yn = (y === null || y === undefined || Number.isNaN(y));
    if (xn && yn) return 0;
    if (xn) return 1;                 // missing values always sink
    if (yn) return -1;
    return (x - y) * dir;
  });
  return out;
}

/* ── tooltip ──────────────────────────────────────────────────────────────── */
const tip = $('#tip');
function showTip(evt, title, rows, keyColor) {
  tip.replaceChildren();
  const h = el('div', 'th-l', title);
  if (keyColor) {
    const key = el('span', 'key');
    key.style.background = keyColor;
    h.prepend(key);
  }
  tip.append(h);
  rows.forEach(([k, v, cls]) => {
    const r = el('div', 'r');
    r.append(el('span', 'k', k), el('span', 'v ' + (cls || ''), v));
    tip.append(r);
  });
  tip.style.opacity = '1';
  moveTip(evt);
}
function moveTip(evt) {
  const pad = 14;
  const box = tip.getBoundingClientRect();
  let x = (evt.clientX ?? 0) + pad, y = (evt.clientY ?? 0) + pad;
  if (evt.type === 'focus' && evt.target.getBoundingClientRect) {
    const b = evt.target.getBoundingClientRect();
    x = b.right + 8; y = b.top;
  }
  if (x + box.width > window.innerWidth - 8) x = window.innerWidth - box.width - 8;
  if (y + box.height > window.innerHeight - 8) y = y - box.height - 2 * pad;
  tip.style.left = Math.max(8, x) + 'px';
  tip.style.top = Math.max(8, y) + 'px';
}
const hideTip = () => { tip.style.opacity = '0'; };

/* ── diverging colour scale (aqua-green ↔ neutral grey ↔ red) ─────────────── */
const hex2rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
const rgb2css = c => 'rgb(' + c.map(v => Math.round(v)).join(',') + ')';
const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);

let SCALE_BOUND = 0.1;
function divergingColor(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return COLOR('card2');
  const mid = hex2rgb(COLOR('mid'));
  const t = Math.max(-1, Math.min(1, v / SCALE_BOUND));
  const pole = hex2rgb(COLOR(t >= 0 ? 'pos' : 'neg'));
  return rgb2css(mix(mid, pole, Math.abs(t)));
}
function inkOn(cssColor) {
  const m = cssColor.match(/\d+/g).map(Number);
  const lum = (0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]) / 255;
  return lum > 0.55 ? '#0b0b0b' : '#ffffff';
}

/* ── sparkline ────────────────────────────────────────────────────────────── */
const NS = 'http://www.w3.org/2000/svg';
function sparkline(points) {
  const w = 64, h = 20, p = 2;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('class', 'spark');
  svg.setAttribute('width', w); svg.setAttribute('height', h);
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  svg.setAttribute('aria-hidden', 'true');       // values live in the return columns
  if (!points || points.length < 2) return svg;
  const step = (w - 2 * p) / (points.length - 1);
  const d = points.map((v, i) => `${(p + i * step).toFixed(1)},${(h - p - v * (h - 2 * p)).toFixed(1)}`);
  const line = document.createElementNS(NS, 'polyline');
  line.setAttribute('points', d.join(' '));
  line.setAttribute('fill', 'none');
  line.setAttribute('stroke', COLOR('muted'));   // recessive: direction is in the labelled columns
  line.setAttribute('stroke-width', '1.5');
  line.setAttribute('stroke-linejoin', 'round');
  line.setAttribute('stroke-linecap', 'round');
  svg.append(line);
  return svg;
}
"""


def _script_b() -> str:
    return r"""
/* ── table ────────────────────────────────────────────────────────────────── */
const COLUMNS = [
  { key: 'rank',   label: '#',      cls: '',  sort: 'score',  dir: -1, title: 'Rank within its own index' },
  { key: 'ticker', label: 'Symbol', cls: 'l', sort: 'ticker', dir: 1 },
  { key: 'sector', label: 'Sector', cls: 'l', sort: 'sector', dir: 1 },
  { key: 'price',  label: 'Price',  cls: '',  sort: 'price',  dir: -1 },
  { key: 'trend',  label: 'Trend',  cls: 'c', sort: 'px_vs_sma200', dir: -1, title: 'MA stack and any cross in the last 60 sessions' },
  { key: 'spark',  label: '60d',    cls: 'c', sort: null },
  { key: 'ret_1m', label: '1M',     cls: '',  sort: 'ret_1m', dir: -1 },
  { key: 'ret_3m', label: '3M',     cls: '',  sort: 'ret_3m', dir: -1 },
  { key: 'ret_12m',label: '12M',    cls: '',  sort: 'ret_12m', dir: -1 },
  { key: 'rsi',    label: 'RSI',    cls: '',  sort: 'rsi',    dir: -1 },
  { key: 'fx',     label: null,     cls: 'c', sort: null, title: 'Factor percentiles' },
  { key: 'score',  label: 'Score',  cls: '',  sort: 'score',  dir: -1, title: 'Composite percentile within its index' },
];

function setSort(key, dir) {
  if (state.sortKey === key) state.sortDir = -state.sortDir;
  else { state.sortKey = key; state.sortDir = dir; }
  render();
}

function buildHead() {
  const tr = el('tr');
  COLUMNS.forEach(c => {
    const th = el('th', c.cls);
    if (c.title) th.title = c.title;
    if (c.key === 'fx') {
      // The four letters double as the legend for the micro-bars and as
      // per-factor sort controls.
      const box = el('span', 'fxhead');
      FACTORS.forEach((f, i) => {
        const b = el('span', 'th', f.letter);
        b.tabIndex = 0;
        b.title = f.label + ' — click to sort';
        b.style.padding = '0 4px';
        b.setAttribute('role', 'button');
        const go = () => setSort(f.key + '_score', -1);
        b.addEventListener('click', go);
        b.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
        box.append(b);
        if (i < FACTORS.length - 1) box.append(document.createTextNode(''));
      });
      th.append(box);
    } else if (c.sort) {
      th.classList.add('th');
      th.tabIndex = 0;
      th.setAttribute('role', 'button');
      th.append(document.createTextNode(c.label));
      if (state.sortKey === c.sort) {
        th.append(' ', el('span', 'arrow', state.sortDir < 0 ? '▼' : '▲'));
      }
      const go = () => setSort(c.sort, c.dir);
      th.addEventListener('click', go);
      th.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    } else {
      th.append(document.createTextNode(c.label || ''));
    }
    tr.append(th);
  });
  return tr;
}

function factorBars(r) {
  const box = el('span', 'fx');
  box.tabIndex = 0;
  box.setAttribute('role', 'img');
  box.setAttribute('aria-label', FACTORS.map(f =>
    `${f.label} ${nf(r[f.key + '_score'], 0)}`).join(', '));
  FACTORS.forEach(f => {
    const v = r[f.key + '_score'];
    const bar = el('span', 'bar' + (r[f.key + '_imputed'] ? ' imputed' : ''));
    const fill = el('i');
    fill.style.height = Math.max(2, (v ?? 0)) + '%';
    bar.append(fill);
    box.append(bar);
  });
  const rows = FACTORS.map(f => [
    f.label, nf(r[f.key + '_score'], 0) + (r[f.key + '_imputed'] ? ' (neutral)' : ''),
  ]);
  rows.push(['Composite', nf(r.score, 0)]);
  const show = e => showTip(e, r.ticker + ' · factors', rows, COLOR('accent'));
  box.addEventListener('pointerenter', show);
  box.addEventListener('pointermove', moveTip);
  box.addEventListener('pointerleave', hideTip);
  box.addEventListener('focus', show);
  box.addEventListener('blur', hideTip);
  return box;
}

const STACK_BADGE = {
  bull:  ['bull', '▲', 'Bull stack'],
  bear:  ['bear', '▼', 'Bear stack'],
  mixed: ['', '◆', 'Mixed'],
  unknown: ['', '·', 'n/a'],
};
const CROSS_BADGE = {
  golden: ['golden', '✦', 'Golden'],
  death:  ['death', '✧', 'Death'],
};

function trendCell(r) {
  const wrap = el('span');
  const [cls, glyph, label] = STACK_BADGE[r.stack] || STACK_BADGE.unknown;
  const b = el('span', 'badge ' + cls);
  b.append(el('span', '', glyph), el('span', '', label));
  b.title = `SMA10 ${r.stack === 'bull' ? '>' : r.stack === 'bear' ? '<' : 'vs'} SMA50 vs SMA200`;
  wrap.append(b);
  const x = CROSS_BADGE[r.cross];
  if (x) {
    const c = el('span', 'badge ' + x[0]);
    c.style.marginLeft = '5px';
    c.append(el('span', '', x[1]), el('span', '', x[2]));
    c.title = 'SMA50 crossed the SMA200 within the last 60 sessions';
    wrap.append(c);
  }
  return wrap;
}

function scoreCell(r) {
  const wrap = el('span', 'meter');
  const track = el('span', 'track');
  const fill = el('i');
  fill.style.display = 'block';
  fill.style.height = '100%';
  fill.style.width = Math.max(1, r.score) + '%';
  fill.style.background = COLOR('accent');
  fill.style.borderRadius = '0 4px 4px 0';
  track.append(fill);
  const grade = el('span', 'grade' + (r.score >= 70 ? ' hi' : ''), r.grade);
  wrap.append(el('span', 'num', nf(r.score, 0)), track, grade);
  return wrap;
}

function moneyCell(r) {
  return r.currency + nf(r.price, r.price >= 100 ? 1 : 2);
}

function buildRow(r) {
  const tr = el('tr', 'row');
  tr.tabIndex = 0;
  tr.setAttribute('role', 'button');
  tr.setAttribute('aria-expanded', String(state.open === r.ticker));
  if (state.open === r.ticker) tr.classList.add('open');

  tr.append(el('td', 'dim', r.rank));

  const sym = el('td', 'l');
  const line = el('div');
  line.append(el('span', 'sym', r.ticker), ' ', el('span', 'mkt', r.market_label));
  sym.append(line, el('div', 'coname', r.name));
  tr.append(sym);

  tr.append(el('td', 'l dim', r.sector));
  tr.append(el('td', '', moneyCell(r)));

  const trend = el('td', 'c'); trend.append(trendCell(r)); tr.append(trend);
  const sp = el('td', 'c'); sp.append(sparkline(r.spark)); tr.append(sp);

  ['ret_1m', 'ret_3m', 'ret_12m'].forEach(k => tr.append(el('td', signCls(r[k]), pct(r[k]))));

  const rsiTd = el('td', '', nf(r.rsi, 1));
  if (r.rsi !== null) {
    if (r.rsi >= D.rsiOverbought) rsiTd.classList.add('neg');
    else if (r.rsi <= D.rsiOversold) rsiTd.classList.add('pos');
  }
  tr.append(rsiTd);

  const fx = el('td', 'c'); fx.append(factorBars(r)); tr.append(fx);
  const sc = el('td'); sc.append(scoreCell(r)); tr.append(sc);

  const toggle = () => { state.open = state.open === r.ticker ? null : r.ticker; render(); };
  tr.addEventListener('click', toggle);
  tr.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
  });
  return tr;
}

/* ── detail panel — the table view for every value the row compresses ─────── */
function group(title, pairs) {
  const g = el('div', 'dgroup');
  g.append(el('h4', null, title));
  const dl = el('dl');
  pairs.forEach(([k, v, cls]) => {
    dl.append(el('dt', null, k), el('dd', cls || '', v));
  });
  g.append(dl);
  return g;
}

function detailRow(r) {
  const tr = el('tr', 'detail');
  const td = el('td');
  td.colSpan = COLUMNS.length;
  const inner = el('div', 'detail-inner');

  inner.append(group('Trend', [
    ['Price vs SMA200', pct(r.px_vs_sma200), signCls(r.px_vs_sma200)],
    ['SMA50 vs SMA200', pct(r.sma50_vs_sma200), signCls(r.sma50_vs_sma200)],
    ['SMA10 vs SMA50', pct(r.sma10_vs_sma50), signCls(r.sma10_vs_sma50)],
    ['SMA200 slope (20d)', pct(r.sma200_slope), signCls(r.sma200_slope)],
    ['SMA10 / 50 / 200', [r.sma10, r.sma50, r.sma200].map(v => nf(v, 1)).join(' / ')],
  ]));

  inner.append(group('Momentum', [
    ['1M / 3M / 6M', [r.ret_1m, r.ret_3m, r.ret_6m].map(v => pct(v, 0)).join(' / ')],
    ['12M return', pct(r.ret_12m), signCls(r.ret_12m)],
    ['12-1 momentum', pct(r.mom_12_1), signCls(r.mom_12_1)],
    ['52w high / low', [r.high_52w, r.low_52w].map(v => nf(v, 1)).join(' / ')],
    ['From 52w high', pct(r.dist_52w_high), signCls(r.dist_52w_high)],
    ['Above 52w low', pct(r.dist_52w_low), signCls(r.dist_52w_low)],
  ]));

  inner.append(group('Quality', [
    ['Return on equity', pctPlain(r.return_on_equity)],
    ['Profit margin', pctPlain(r.profit_margin)],
    ['Revenue growth', pct(r.revenue_growth)],
    ['Earnings growth', pct(r.earnings_growth)],
    ['Debt / equity', nf(r.debt_to_equity, 1)],
    ['Dividend yield', pctPlain(r.dividend_yield, 2)],
  ]));

  inner.append(group('Valuation', [
    ['Market cap', cap(r.market_cap)],
    ['Trailing P/E', nf(r.trailing_pe, 1)],
    ['Forward P/E', nf(r.forward_pe, 1)],
    ['Price / book', nf(r.price_to_book, 2)],
    ['Price / sales', nf(r.price_to_sales, 2)],
    ['EV / EBITDA', nf(r.ev_to_ebitda, 1)],
  ]));

  inner.append(group('Risk & liquidity', [
    ['RSI (14)', nf(r.rsi, 1)],
    ['ATR (14) % of price', pctPlain(r.atr_pct)],
    ['Volatility (3m, ann.)', pctPlain(r.volatility)],
    ['Avg daily turnover', r.currency + cap(r.dollar_volume)],
    ['Industry', r.industry || DASH],
  ]));

  inner.append(group('Factor scores', FACTORS.map(f => [
    f.label, nf(r[f.key + '_score'], 0) + (r[f.key + '_imputed'] ? '  (neutral — no data)' : ''),
  ]).concat([
    ['Composite', nf(r.score, 0)],
    ['Grade', r.grade],
    ['Rank in ' + r.market_label, '#' + r.rank],
  ])));

  td.append(inner);
  tr.append(td);
  return tr;
}
"""


def _script_c() -> str:
    return r"""
/* ── heat map — sector-grouped, sized by market cap, coloured by 1M return ── */
function quantile(sorted, q) {
  if (!sorted.length) return 0;
  const i = (sorted.length - 1) * q;
  const lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

/* Split a sector into rows of roughly equal total weight. Every row is the same
   height and the same total width, so a tile's area ends up proportional to its
   weight across the whole sector — which plain flex-wrap does not give you
   (there the first row's tiles all collapse to the same min-width). */
const MAX_PER_ROW = 14;
function packRows(list, weightOf) {
  const n = list.length;
  if (n <= 1) return [list];
  const rowCount = Math.max(1, Math.ceil(n / MAX_PER_ROW));
  if (rowCount === 1) return [list];

  const total = list.reduce((a, r) => a + weightOf(r), 0);
  const target = total / rowCount;
  const rows = [];
  let current = [], acc = 0;

  list.forEach((r, i) => {
    current.push(r);
    acc += weightOf(r);
    const rowsLeft = rowCount - rows.length;
    const itemsLeft = n - i - 1;
    // Close the row on reaching the weight target, or early if the remaining
    // rows would otherwise be left with nothing to hold.
    if ((acc >= target && rowsLeft > 1 && itemsLeft >= rowsLeft - 1)
        || itemsLeft === rowsLeft - 1) {
      rows.push(current);
      current = []; acc = 0;
    }
  });
  if (current.length) rows.push(current);
  return rows;
}

function buildHeatmap(rows) {
  const host = $('#heatmap');
  host.replaceChildren();

  const mags = rows.map(r => Math.abs(r.ret_1m)).filter(v => Number.isFinite(v)).sort((a, b) => a - b);
  SCALE_BOUND = Math.min(0.25, Math.max(0.02, quantile(mags, 0.9) || 0.05));

  if (!rows.length) { host.append(el('div', 'empty', 'No names match the current filters.')); return; }

  const byMarket = new Map();
  rows.forEach(r => {
    if (!byMarket.has(r.market)) byMarket.set(r.market, new Map());
    const sectors = byMarket.get(r.market);
    if (!sectors.has(r.sector)) sectors.set(r.sector, []);
    sectors.get(r.sector).push(r);
  });

  const cells = [];
  D.markets.forEach(mk => {
    const sectors = byMarket.get(mk);
    if (!sectors) return;
    const block = el('div', 'hm-market');
    block.append(el('h3', null, D.marketLabels[mk]));

    // Biggest sector first, so the eye lands on the weightiest group.
    const ordered = [...sectors.entries()].sort((a, b) => b[1].length - a[1].length);
    ordered.forEach(([sector, list]) => {
      const sec = el('div', 'hm-sector');
      const h = el('h4');
      h.append(document.createTextNode(sector), el('span', 'cnt', list.length));
      sec.append(h);
      list.sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0));
      // sqrt keeps mega-caps from swallowing the group while still ranking by size
      const weightOf = r => Math.sqrt(Math.max(r.market_cap || r.dollar_volume || 1, 1));
      packRows(list, weightOf).forEach(bucket => {
      const row = el('div', 'hm-row');
      bucket.forEach(r => {
        const weight = weightOf(r);
        const bg = divergingColor(r.ret_1m);
        const cell = el('div', 'hm-cell');
        cell.style.flexGrow = String(weight);
        cell.style.flexBasis = '54px';
        cell.style.background = bg;
        cell.style.color = inkOn(bg);
        cell.tabIndex = 0;
        cell.append(el('div', 't', r.ticker));
        const v = el('div', 'v', pct(r.ret_1m, 1));
        cell.append(v);
        const show = e => showTip(e, r.ticker + ' · ' + r.name, [
          ['1M return', pct(r.ret_1m), signCls(r.ret_1m)],
          ['3M return', pct(r.ret_3m), signCls(r.ret_3m)],
          ['Score', nf(r.score, 0) + ' (' + r.grade + ')'],
          ['Market cap', cap(r.market_cap)],
          ['Sector', r.sector],
        ], bg);
        cell.addEventListener('pointerenter', show);
        cell.addEventListener('pointermove', moveTip);
        cell.addEventListener('pointerleave', hideTip);
        cell.addEventListener('focus', show);
        cell.addEventListener('blur', hideTip);
        cell.addEventListener('click', () => {
          state.open = r.ticker;
          state.q = r.ticker;
          $('#f-q').value = r.ticker;
          render();
          $('#table-top').scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
        row.append(cell);
        cells.push([cell, v]);
      });
      sec.append(row);
      });
      block.append(sec);
    });
    host.append(block);
  });

  // Legend for the continuous scale.
  const lg = el('div', 'hm-legend');
  lg.append(el('span', null, pct(-SCALE_BOUND, 0)));
  const ramp = el('div', 'ramp');
  for (let i = 0; i <= 20; i++) {
    const s = el('span');
    s.style.background = divergingColor(-SCALE_BOUND + (2 * SCALE_BOUND) * (i / 20));
    ramp.append(s);
  }
  lg.append(ramp, el('span', null, pct(SCALE_BOUND, 0)),
            el('span', null, '· 1-month return · tile size = market cap'));
  host.append(lg);

  // A label that will not fit is dropped rather than clipped; the tooltip and
  // the table above still carry the value.
  requestAnimationFrame(() => {
    cells.forEach(([cell, v]) => { if (cell.offsetWidth < 68) v.style.display = 'none'; });
  });
}

/* ── stats ────────────────────────────────────────────────────────────────── */
function median(values) {
  const v = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}

function renderStats(rows) {
  $('#hero-value').textContent = rows.length.toLocaleString('en-US');
  $('#hero-sub').textContent = `of ${D.total.toLocaleString('en-US')} scanned · ` +
    (rows.length ? `top score ${nf(Math.max(...rows.map(r => r.score)), 0)}` : 'no matches');

  const host = $('#selstats');
  host.replaceChildren();
  const above = rows.filter(r => r.above_sma200).length;
  const tiles = [
    ['Above SMA200', rows.length ? (100 * above / rows.length).toFixed(0) + '%' : DASH,
     `${above} of ${rows.length} in the selection`],
    ['Median score', rows.length ? nf(median(rows.map(r => r.score)), 0) : DASH,
     'composite percentile'],
    ['Median 1M return', rows.length ? pct(median(rows.map(r => r.ret_1m))) : DASH,
     'across the selection'],
    ['Bull stacks', String(rows.filter(r => r.stack === 'bull').length),
     'SMA10 > SMA50 > SMA200'],
  ];
  tiles.forEach(([label, value, sub]) => {
    const c = el('div', 'card tile');
    c.append(el('div', 'label', label), el('div', 'value', value), el('div', 'sub', sub));
    host.append(c);
  });
}

function renderUniverseTiles() {
  const host = $('#universe');
  host.replaceChildren();
  D.summary.forEach(s => {
    const c = el('div', 'card tile');
    c.append(el('div', 'label', s.label + ' breadth'));
    c.append(el('div', 'value', s.breadth.toFixed(0) + '%'));
    const sub = el('div', 'sub');
    sub.append(
      el('span', 'k', s.above_sma200), document.createTextNode(` of ${s.count} above SMA200 · `),
      el('span', 'k', s.bull_stack), document.createTextNode(' bull stacks · '),
      el('span', 'k', s.golden), document.createTextNode(' golden / '),
      el('span', 'k', s.death), document.createTextNode(' death crosses'),
    );
    c.append(sub);
    host.append(c);
  });
}

/* ── CSV export ───────────────────────────────────────────────────────────── */
const CSV_COLUMNS = [
  'rank', 'ticker', 'name', 'market_label', 'sector', 'price', 'score', 'grade',
  'trend_score', 'momentum_score', 'quality_score', 'value_score',
  'stack', 'cross', 'above_sma200', 'rsi',
  'ret_1m', 'ret_3m', 'ret_6m', 'ret_12m', 'mom_12_1', 'dist_52w_high',
  'market_cap', 'trailing_pe', 'price_to_book', 'price_to_sales', 'ev_to_ebitda',
  'return_on_equity', 'profit_margin', 'revenue_growth', 'debt_to_equity',
  'atr_pct', 'volatility', 'dollar_volume',
];
function exportCsv(rows) {
  const esc = v => {
    if (v === null || v === undefined) return '';
    const s = String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const lines = [CSV_COLUMNS.join(',')];
  rows.forEach(r => lines.push(CSV_COLUMNS.map(k => esc(r[k])).join(',')));
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `stock_select_${D.stamp.replace(/[^0-9]/g, '').slice(0, 8)}.csv`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* ── main render ──────────────────────────────────────────────────────────── */
function render() {
  const rows = selection();

  const thead = $('#thead');
  thead.replaceChildren(buildHead());

  const tbody = $('#tbody');
  tbody.replaceChildren();
  if (!rows.length) {
    const tr = el('tr');
    const td = el('td', 'empty', 'No names match the current filters. Try lowering the minimum score or clearing the search.');
    td.colSpan = COLUMNS.length;
    tr.append(td);
    tbody.append(tr);
  } else {
    rows.forEach(r => {
      tbody.append(buildRow(r));
      if (state.open === r.ticker) tbody.append(detailRow(r));
    });
  }

  renderStats(rows);
  buildHeatmap(rows);
  $('#count').textContent = `${rows.length} shown`;
}

/* ── filter wiring ────────────────────────────────────────────────────────── */
function wire() {
  D.markets.forEach(mk => {
    const lab = $(`#mk-${mk}`);
    if (!lab) return;
    const box = lab.querySelector('input');
    box.addEventListener('change', () => {
      if (box.checked) state.markets.add(mk); else state.markets.delete(mk);
      lab.classList.toggle('on', box.checked);
      render();
    });
  });

  const bind = (id, key) => $(id).addEventListener('change', e => { state[key] = e.target.value; render(); });
  bind('#f-stack', 'stack');
  bind('#f-cross', 'cross');
  bind('#f-rsi', 'rsi');
  bind('#f-sector', 'sector');

  const score = $('#f-score');
  score.addEventListener('input', e => {
    state.minScore = Number(e.target.value);
    $('#f-score-out').textContent = state.minScore;
    render();
  });

  let t = null;
  $('#f-q').addEventListener('input', e => {
    clearTimeout(t);
    const v = e.target.value.trim();
    t = setTimeout(() => { state.q = v; render(); }, 120);
  });

  $('#reset').addEventListener('click', () => {
    state.markets = new Set(D.markets);
    Object.assign(state, { stack: 'any', cross: 'any', rsi: 'any', sector: 'any', minScore: 0, q: '', open: null });
    D.markets.forEach(mk => {
      const lab = $(`#mk-${mk}`);
      if (lab) { lab.querySelector('input').checked = true; lab.classList.add('on'); }
    });
    ['#f-stack', '#f-cross', '#f-rsi', '#f-sector'].forEach(s => { $(s).value = 'any'; });
    score.value = 0; $('#f-score-out').textContent = '0'; $('#f-q').value = '';
    render();
  });

  $('#export').addEventListener('click', () => exportCsv(selection()));
  window.addEventListener('scroll', hideTip, { passive: true });
}

renderUniverseTiles();
wire();
render();
"""


def _esc(text) -> str:
    from html import escape
    return escape(str(text), quote=True)


def _filters_html(sectors: list[str], markets: list[str]) -> str:
    market_toggles = "".join(
        f'<label class="toggle on" id="mk-{_esc(m)}">'
        f'<input type="checkbox" checked>{_esc(config.UNIVERSES[m]["label"])}</label>'
        for m in markets
    )
    sector_options = "".join(
        f'<option value="{_esc(s)}">{_esc(s)}</option>' for s in sectors
    )
    return f"""
<div class="filters" role="group" aria-label="Selection filters">
  <div class="fgroup"><span>Market</span><div class="toggles">{market_toggles}</div></div>

  <div class="fgroup"><span>Trend</span>
    <select id="f-stack" aria-label="Trend filter">
      <option value="any">Any trend</option>
      <option value="above">Above SMA200</option>
      <option value="below">Below SMA200</option>
      <option value="bull">Bull stack (10 &gt; 50 &gt; 200)</option>
      <option value="bear">Bear stack (10 &lt; 50 &lt; 200)</option>
    </select>
  </div>

  <div class="fgroup"><span>MA cross</span>
    <select id="f-cross" aria-label="Moving average cross filter">
      <option value="any">Any</option>
      <option value="golden">Golden cross (60d)</option>
      <option value="death">Death cross (60d)</option>
      <option value="none">No recent cross</option>
    </select>
  </div>

  <div class="fgroup"><span>RSI</span>
    <select id="f-rsi" aria-label="RSI filter">
      <option value="any">Any</option>
      <option value="overbought">Overbought (&ge; {int(config.RSI_OVERBOUGHT)})</option>
      <option value="oversold">Oversold (&le; {int(config.RSI_OVERSOLD)})</option>
      <option value="neutral">Neutral band</option>
    </select>
  </div>

  <div class="fgroup"><span>Sector</span>
    <select id="f-sector" aria-label="Sector filter">
      <option value="any">All sectors</option>{sector_options}
    </select>
  </div>

  <div class="fgroup"><span>Min score</span>
    <div class="slider">
      <input type="range" id="f-score" min="0" max="95" step="5" value="0" aria-label="Minimum composite score">
      <output id="f-score-out">0</output>
    </div>
  </div>

  <div class="fgroup"><span>Search</span>
    <input type="search" id="f-q" placeholder="Ticker or company name" aria-label="Search ticker or name">
  </div>

  <div class="spacer"></div>
  <div class="fgroup"><span>&nbsp;</span>
    <div class="toggles">
      <button id="reset" type="button">Reset</button>
      <button id="export" type="button">Export CSV</button>
    </div>
  </div>
</div>"""


def _method_html() -> str:
    cards = "".join(
        f'<div class="m"><h4>{_esc(label)}</h4>'
        f'<div class="w">weight {config.FACTOR_WEIGHTS[key]:.0%}</div>'
        f'<p>{_esc(blurb)}</p></div>'
        for key, _letter, label, blurb in _FACTOR_META
    )
    return f"""
<div class="sect">Methodology</div>
<div class="method">{cards}
  <div class="m"><h4>Composite score</h4>
    <div class="w">0 – 100 percentile</div>
    <p>Every sub-metric is ranked into a percentile against the other members of
    the <em>same index</em>, blended into its factor, then the weighted factor
    blend is re-percentiled. A score of 80 means the name sits in the top 20 % of
    its own index — Hang Seng names are never ranked against S&amp;P 500 names, so
    differing multiple regimes and currencies never cross-contaminate.
    A factor with more than half its inputs missing scores a neutral 50 and its
    micro-bar is drawn hatched.</p>
  </div>
</div>
<p class="disclaimer">
  All figures are objective calculations from end-of-day price history and
  publicly reported fundamentals. Scores are relative rankings within an index,
  not forecasts. Fundamental fields are only as good as the upstream data feed
  and may be stale or missing. Nothing here is investment advice.
</p>"""


def build_page(result: dict) -> str:
    """Return the complete self-contained HTML document."""
    rows = result["rows"]
    sectors = sorted({r["sector"] for r in rows if r.get("sector")})
    markets = [m for m in result["markets"]
               if any(r["market"] == m for r in rows)] or result["markets"]

    payload = {
        "rows": rows,
        "summary": result["summary"],
        "markets": markets,
        "marketLabels": {m: config.UNIVERSES[m]["label"] for m in markets},
        "factors": [{"key": k, "letter": l, "label": lab, "blurb": b}
                    for k, l, lab, b in _FACTOR_META],
        "weights": config.FACTOR_WEIGHTS,
        "rsiOverbought": config.RSI_OVERBOUGHT,
        "rsiOversold": config.RSI_OVERSOLD,
        "total": len(rows),
        "stamp": result["generated_at"],
        "demo": result["demo"],
    }
    # </script> inside the JSON would end the block early; < is safe in JSON.
    data_json = json.dumps(payload, allow_nan=False).replace("<", "\\u003c")

    demo_banner = ""
    if result["demo"]:
        demo_banner = (
            '<div class="demo-banner"><b>Demo data.</b> This page was generated with '
            '<code>--demo</code>: prices and fundamentals are synthetic, deterministic '
            'placeholders, not market data. Re-run without <code>--demo</code> for a '
            'live scan.</div>'
        )

    chips = "".join(
        f'<span class="chip">{_esc(config.UNIVERSES[m]["label"])}</span>' for m in markets
    )
    if not result["fundamentals"]:
        chips += ('<span class="chip">no fundamentals — quality &amp; value neutral</span>')
    if result.get("skipped"):
        chips += (f'<span class="chip">{result["skipped"]} skipped '
                  f'(&lt; {config.MIN_BARS} sessions of history)</span>')

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stock Selection — {_esc(result['generated_at'])}</title>
<style>{_style()}</style>
</head>
<body>
<div class="wrap">

  <div class="head">
    <h1>Stock Selection</h1>
    <span class="stamp">Generated {_esc(result['generated_at'])}</span>
    {chips}
  </div>
  {demo_banner}

  <div class="sect">Universe breadth<span class="note">the whole index, before any filter</span></div>
  <div class="tiles" id="universe"></div>

  <div class="sect">Filters<span class="note">every stat, table row and heat-map tile below reflects this slice</span></div>
  {_filters_html(sectors, markets)}

  <div class="topgrid">
    <div class="card hero">
      <div class="label">Names matching</div>
      <div class="value" id="hero-value">0</div>
      <div class="sub" id="hero-sub"></div>
    </div>
    <div class="tiles" id="selstats"></div>
  </div>

  <div class="sect" id="table-top">Ranked selection
    <span class="note">click a row for the full metric breakdown · <span id="count"></span></span>
  </div>
  <div class="tablecard"><div class="tablescroll">
    <table>
      <thead id="thead"></thead>
      <tbody id="tbody"></tbody>
    </table>
  </div></div>

  <div class="sect">Market heat map
    <span class="note">tile size = market cap · colour = 1-month return · click a tile to open its row</span>
  </div>
  <div class="hm" id="heatmap"></div>

  {_method_html()}
</div>

<div id="tip" role="tooltip" aria-live="polite"></div>
<script>window.__SELECT__ = {data_json};</script>
<script>{_script()}{_script_b()}{_script_c()}</script>
</body>
</html>
"""
