// JS port of src/table_data.py (shared by the desktop table view and its Column statistics dialog): is_numeric,
// to_number, detect_numeric_columns, numeric_stats / string_stats (formatted with Python's "{:.4g}"), plus
// columnStats() mirroring stats_dialog.column_stats. table_engine.test.mjs checks the output against Python.
// parseDelimited() is a small CSV reader for files opened in the browser (the Python app uses csv.Sniffer).

const NUMERIC_RE = /^\s*-?(?:\d{1,3}(?:[,_]\d{3})+|\d+)(?:\.\d+)?\s*%?\s*$/;
export const NUMERIC_COLS = ['count', 'missing', 'mean', 'median', 'stddev', 'min', 'Q1', 'Q3', 'max', 'range', 'skew', 'kurt'];

export const isNumeric = s => NUMERIC_RE.test(s || '');

export function toNumber(s) {
  if (s == null) return null;
  const t = String(s).trim().replace(/%+$/, '').replace(/[,_]/g, '');
  if (!t) return null;
  // Python float(): optional sign, digits with optional fraction / exponent, inf / nan words.
  if (!/^[+-]?(\d+\.?\d*(e[+-]?\d+)?|\.\d+(e[+-]?\d+)?|inf(inity)?|nan)$/i.test(t)) return null;
  if (/inf/i.test(t)) return t.startsWith('-') ? -Infinity : Infinity;
  return /nan/i.test(t) ? NaN : Number(t);
}

export function detectNumericColumns(header, rows, sampleRows = 64) {
  const sample = rows.slice(0, sampleRows);
  return header.map((_, i) => {
    const vals = sample.filter(r => i < r.length && r[i].trim()).map(r => r[i]);
    return vals.length > 0 && vals.every(isNumeric);
  });
}

// Python format(x, ".4g"): p significant digits (round-half-even on exact ties), exponent form when exp < -4 or
// exp >= p, trailing zeros removed.
export function fmtG(x, p = 4) {
  if (x === '' || x == null || !Number.isFinite(x)) return '';
  if (x === 0) return Object.is(x, -0) ? '-0' : '0';
  const [ds, es] = Math.abs(x).toExponential(p + 16).split('e');
  const digits = ds.replace('.', '');
  let exp = Number(es), kept = BigInt(digits.slice(0, p));
  const rest = digits.slice(p);
  if (rest[0] > '5' || (rest[0] === '5' && (/[1-9]/.test(rest.slice(1)) || kept % 2n === 1n))) kept += 1n;
  if (kept === 10n ** BigInt(p)) { kept /= 10n; exp += 1; }
  const k = kept.toString(), sign = x < 0 ? '-' : '';
  const strip = s => (s.includes('.') ? s.replace(/\.?0+$/, '') : s);
  if (exp < -4 || exp >= p)
    return `${sign}${strip(k[0] + '.' + k.slice(1))}e${exp < 0 ? '-' : '+'}${String(Math.abs(exp)).padStart(2, '0')}`;
  const s = exp >= 0 ? k.slice(0, exp + 1) + (exp + 1 < p ? '.' + k.slice(exp + 1) : '') : '0.' + '0'.repeat(-exp - 1) + k;
  return sign + strip(s);
}

function quartiles(sorted) {  // statistics.quantiles(n=4), method="exclusive"
  const ld = sorted.length, m = ld + 1, out = [];
  for (let i = 1; i < 4; i++) {
    let j = Math.floor((i * m) / 4);
    j = j < 1 ? 1 : j > ld - 1 ? ld - 1 : j;
    const delta = i * m - j * 4;
    out.push((sorted[j - 1] * (4 - delta) + sorted[j] * delta) / 4);
  }
  return out;
}

export function numericStats(values) {
  const n = values.length;
  if (!n) return Object.fromEntries(NUMERIC_COLS.map(k => [k, '']));
  const mean = values.reduce((a, c) => a + c, 0) / n;
  const sd = n > 1 ? Math.sqrt(values.reduce((a, c) => a + (c - mean) ** 2, 0) / n) : 0;
  const s = [...values].sort((a, c) => a - c);
  let q1 = '', q3 = '';
  if (n >= 4) [q1, , q3] = quartiles(s);
  let skew = '', kurt = '';
  if (sd > 0 && n > 2) {
    skew = values.reduce((a, c) => a + (c - mean) ** 3, 0) / (n * sd ** 3);
    kurt = values.reduce((a, c) => a + (c - mean) ** 4, 0) / (n * sd ** 4) - 3;
  }
  const median = n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
  return { count: String(n), mean: fmtG(mean), median: fmtG(median), stddev: fmtG(sd), min: fmtG(s[0]), max: fmtG(s[n - 1]),
    Q1: fmtG(q1), Q3: fmtG(q3), range: fmtG(s[n - 1] - s[0]), skew: fmtG(skew), kurt: fmtG(kurt) };
}

export function stringStats(values) {
  const counts = new Map();
  for (const v of values) if (v !== '') counts.set(v, (counts.get(v) || 0) + 1);
  const n = values.length;
  if (!counts.size) return { count: String(n), unique: '0', top: '', top_freq: '' };
  let top = null, f = 0;
  for (const [k, c] of counts) if (c > f) { top = k; f = c; }
  return { count: String(n), unique: String(counts.size), top: [...String(top)].slice(0, 40).join(''), top_freq: String(f) };
}

// One row of the statistics grid for column `col` of the visible rows.
export function columnStats(rows, col, isNum) {
  const raw = rows.map(r => r[col]);
  const missing = raw.filter(v => v == null || v === '').length;
  const s = isNum ? numericStats(raw.map(toNumber).filter(v => v !== null)) : stringStats(raw.filter(v => v != null));
  return { ...s, __missing__: String(missing), __numeric__: isNum };
}

// Minimal CSV/TSV reader for in-browser files: delimiter = most common of , \t ; | in the first line; quotes honoured;
// blank lines dropped; rows padded / cut to the header width (as parse_delimited does).
export function parseDelimited(text) {
  const first = text.split(/\r?\n/, 1)[0] || '';
  const delim = [',', '\t', ';', '|'].map(d => [d, first.split(d).length]).sort((a, b) => b[1] - a[1])[0][0];
  const rows = []; let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += ch; continue; }
    if (ch === '"') q = true;
    else if (ch === delim) { row.push(cell); cell = ''; }
    else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = ''; }
    else cell += ch;
  }
  if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
  const body = rows.filter(r => !(r.length === 1 && r[0] === ''));
  if (!body.length) return { header: [], rows: [], delimiter: delim };
  const header = body[0], w = header.length;
  const out = body.slice(1).map(r => (r.length < w ? [...r, ...Array(w - r.length).fill('')] : r.slice(0, w)));
  return { header, rows: out, delimiter: delim };
}

// TableModel._apply_filter: indices of rows matching `<col> <op> <value>` (ops ~ > >= < <= = != ; numeric compare on
// numeric columns, lower-case string compare otherwise; unparseable cells are excluded).
export function filterRows(rows, col, op, value, isNum) {
  const refNum = isNum ? toNumber(value) : null, refStr = (value || '').toLowerCase(), out = [];
  rows.forEach((row, i) => {
    const cell = col < row.length ? row[col] : '';
    if (op === '~') { if ((cell || '').toLowerCase().includes(refStr)) out.push(i); return; }
    let a, b;
    if (isNum) { if (refNum === null) return; const n = toNumber(cell); if (n === null) return; a = n; b = refNum; }
    else { a = (cell || '').toLowerCase(); b = refStr; }
    if ((op === '>' && a > b) || (op === '>=' && a >= b) || (op === '<' && a < b) || (op === '<=' && a <= b)
      || ((op === '=' || op === '==') && a === b) || (op === '!=' && a !== b)) out.push(i);
  });
  return out;
}

// TableModel.sort: numeric columns by value (unparseable = -inf), others by lower-cased text; stable.
export function sortRows(rows, idx, col, desc, isNum) {
  const key = u => { const r = rows[u]; if (col >= r.length) return isNum ? -Infinity : '';
    if (!isNum) return r[col].toLowerCase(); const n = toNumber(r[col]); return n ?? -Infinity; };
  const cmp = (x, y) => (x < y ? -1 : x > y ? 1 : 0);
  return [...idx].sort((u, v) => (desc ? -1 : 1) * cmp(key(u), key(v)));
}
