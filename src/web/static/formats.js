// Formats page: every extension / file name TextView maps to a viewer (file_loader.FORMAT_MAP / FILENAME_MAP), a
// "what would TextView do with this name?" box (format_engine.detectFormat), and the bundled file-format database
// with the desktop ranker (format_engine.searchFormats, tested against FormatDB.search).
import { route, app, api, esc, $ } from './core.js';
import { sanitize } from './display_ctl.js';
import { detectFormat, searchFormats } from './format_engine.js';

route('formats', async (args, query) => {
  const [fm, db] = await Promise.all([api('/formats'), api('/formatdb')]);
  app().innerHTML = `<h1>Formats</h1>
    <p class="lead">${fm.n_extensions} extensions and ${fm.n_filenames} special file names map to ${fm.n_formats} format ids.
      The format decides the viewer: code (Pygments), rendered (markdown / documents), table, PDF, notebook, image or media.</p>
    <div class="panel"><label for="fname">What would TextView do with this file name?</label><input id="fname" placeholder="e.g. data.parquet, Dockerfile, report.tar.gz">
      <p id="fres" class="small"></p></div>
    <h2>File-format database</h2>
    <p class="small mute">${db.entries.length} curated entries (data/file_formats.json): Help → File formats database… in the desktop
      app, also used by the agent and the unknown-file report.</p>
    <div class="side"><div><label for="fq">Search</label><input id="fq" value="${esc(query.q || '')}" placeholder="csv, image, .npy, sql…">
      <label for="fcat">Category</label><select id="fcat"><option value="">all (${db.entries.length})</option>${Object.entries(db.categories)
        .map(([c, n]) => `<option value="${esc(c)}">${esc(c)} (${n})</option>`).join('')}</select>
      <div id="flist" class="filelist" style="margin-top:10px"></div></div><div id="fentry" class="panel doc"></div></div>
    <h2>Extension map</h2><div class="scroll"><table><thead><tr><th>format</th><th>view</th><th>extensions / names</th></tr></thead><tbody>
      ${fm.groups.map(g => `<tr class="fmtrow"><td>${esc(g.format)}</td><td>${esc(g.view)}</td><td class="exts">${esc([...g.extensions, ...g.filenames].join('  '))}</td></tr>`).join('')}
    </tbody></table></div>`;
  $('#fname').oninput = e => {
    const n = e.target.value.trim();
    if (!n) { $('#fres').textContent = ''; return; }
    const f = detectFormat(n, fm.format_map, fm.filename_map), g = fm.groups.find(x => x.format === f);
    $('#fres').innerHTML = `→ format <b>${esc(f)}</b>, ${esc(g ? g.view : 'code')} view${f === 'plain' ? ' (unknown names fall back to plain text; binary files get the unknown-file report)' : ''}.`;
  };
  const showEntry = e => { $('#fentry').innerHTML = e ? sanitize(e.html) : '<p class="mute">No entry selected.</p>';
    document.querySelectorAll('#flist a').forEach(a => a.classList.toggle('on', e && a.dataset.id === e.id)); };
  const list = () => {
    const q = $('#fq').value, cat = $('#fcat').value;
    let items = q.trim() ? searchFormats(db.entries, q, 100) : [...db.entries].sort((a, b) => a.name.localeCompare(b.name));
    if (cat) items = items.filter(e => e.category === cat);
    $('#flist').innerHTML = items.map(e => `<a href="#/formats" data-id="${esc(e.id)}"><span>${esc(e.name)}</span><small>${esc(e.extensions[0] || e.filenames[0] || '')}</small></a>`).join('')
      || '<p class="small mute" style="padding:8px">No matches.</p>';
    $('#flist').querySelectorAll('a').forEach(a => { a.onclick = ev => { ev.preventDefault(); showEntry(db.entries.find(x => x.id === a.dataset.id)); }; });
    showEntry(items[0]);
  };
  $('#fq').oninput = list; $('#fcat').onchange = list;
  list();
});
