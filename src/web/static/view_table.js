// Table view for CSV / TSV / XLSX (and every other format the desktop app shows as a table): click a header to sort,
// a filter bar (column / operator / value, as TableFilterBar), and Table -> Column statistics. Sorting, filtering and
// statistics use table_engine.js, the tested port of src/table_data.py + TableModel.
import { esc } from './core.js';
import { themeStyle } from './display_ctl.js';
import { columnStats, filterRows, sortRows, NUMERIC_COLS } from './table_engine.js';

const MAX_ROWS = 2000;
const OPS = [['~', 'contains'], ['>', '>'], ['>=', '≥'], ['<', '<'], ['<=', '≤'], ['=', '='], ['!=', '≠']];

export function renderTable(host, d, th, s) {
  const t = d.table, st = { sort: null, desc: false, filter: null, stats: false };
  host.innerHTML = `<div class="row" role="group" aria-label="Filter rows">
      <div><label for="tf-col">Column</label><select id="tf-col">${t.header.map((h, i) => `<option value="${i}">${esc(h)}</option>`).join('')}</select></div>
      <div><label for="tf-op">Operator</label><select id="tf-op">${OPS.map(([v, l]) => `<option value="${v}">${l}</option>`).join('')}</select></div>
      <div><label for="tf-val">Value</label><input id="tf-val" placeholder="filter as you type"></div></div>
    <p class="small"><span id="tf-count"></span> · <button class="alt" id="tf-stats" type="button">Column statistics</button>
      <span class="mute">delimiter <code>${esc(JSON.stringify(t.delimiter))}</code> · numeric columns are right-aligned and sort by value</span></p>
    <div id="tf-statbox"></div><div class="ttable" id="tf-grid"></div>`;
  const grid = host.querySelector('#tf-grid');
  const visible = () => {
    let idx = st.filter ? filterRows(t.rows, st.filter[0], st.filter[1], st.filter[2], t.numeric[st.filter[0]]) : t.rows.map((_, i) => i);
    if (st.sort !== null) idx = sortRows(t.rows, idx, st.sort, st.desc, t.numeric[st.sort]);
    return idx;
  };
  const draw = () => {
    const idx = visible();
    host.querySelector('#tf-count').textContent = `${idx.length} of ${t.rows.length} rows`;
    const cell = `border-color:${th.line_number_fg}44;`;
    grid.innerHTML = `<table style="${themeStyle(th, s)}"><thead><tr>${t.header.map((h, i) =>
      `<th class="${t.numeric[i] ? 'num' : ''}" data-c="${i}" tabindex="0" aria-sort="${st.sort === i ? (st.desc ? 'descending' : 'ascending') : 'none'}"
        style="background:${th.line_number_bg};color:${th.fg};${cell}">${esc(h)}${st.sort === i ? (st.desc ? ' ▼' : ' ▲') : ''}</th>`).join('')}</tr></thead>
      <tbody>${idx.slice(0, MAX_ROWS).map(r => `<tr>${t.rows[r].map((v, i) => `<td class="${t.numeric[i] ? 'num' : ''}" style="${cell}">${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>
      ${idx.length > MAX_ROWS ? `<p class="small mute">First ${MAX_ROWS} rows shown.</p>` : ''}`;
    grid.querySelectorAll('th').forEach(h => {
      const go = () => { const c = +h.dataset.c; st.desc = st.sort === c ? !st.desc : false; st.sort = c; draw(); };
      h.onclick = go; h.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
    });
    if (st.stats) drawStats(idx);
  };
  const drawStats = idx => {
    const rows = idx.map(i => t.rows[i]);
    const cols = [...NUMERIC_COLS, 'unique', 'top', 'top_freq'];
    host.querySelector('#tf-statbox').innerHTML = `<div class="scroll panel"><table class="small"><thead><tr><th>column</th>${cols.map(c => `<th>${c}</th>`).join('')}</tr></thead>
      <tbody>${t.header.map((h, i) => { const r = columnStats(rows, i, t.numeric[i]); r.missing = r.__missing__;
        return `<tr><td><b>${esc(h)}</b></td>${cols.map(c => `<td>${esc(r[c] ?? '')}</td>`).join('')}</tr>`; }).join('')}</tbody></table>
      <p class="small mute">Same statistics as Table → Column statistics in the desktop app (visible rows only).</p></div>`;
  };
  const refilter = () => { const v = host.querySelector('#tf-val').value;
    st.filter = v ? [+host.querySelector('#tf-col').value, host.querySelector('#tf-op').value, v] : null; draw(); };
  ['#tf-col', '#tf-op'].forEach(id => { host.querySelector(id).onchange = refilter; });
  host.querySelector('#tf-val').oninput = refilter;
  host.querySelector('#tf-stats').onclick = () => { st.stats = !st.stats; if (!st.stats) host.querySelector('#tf-statbox').innerHTML = ''; draw(); };
  draw();
}
