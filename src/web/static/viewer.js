// Viewer page (#/view/<id>): the sample files, Save-As outputs and starter templates, opened by TextView's Python
// loaders (pre-rendered on the static site), with live display settings. "Open a file" sends your own file to the
// local app's loaders, or reads it in the browser on the static site (local_open.js).
import { route, app, api, esc, isStatic, go, $ } from './core.js';
import { loadSettings, controls, themeOf } from './display_ctl.js';
import { renderCode } from './view_code.js';
import { renderTable } from './view_table.js';
import { renderImage, renderPdf, renderMedia, renderNotebook, renderRendered } from './view_media.js';

let uploaded = null;  // payload of the last opened local file (kept while you change settings)

route('view', async (args) => {
  const [disp, list] = await Promise.all([api('/display'), api('/files')]);
  const id = args[0] || 'example.md';
  let s = loadSettings(disp.defaults);
  const groups = {};
  for (const it of list.items) (groups[it.group] ||= []).push(it);
  app().innerHTML = `<h1>Viewer</h1>
    <p class="lead">Every file below is opened by TextView's own code: format detection, encoding probing, document and
      spreadsheet extraction, Pygments highlighting and themed markdown. Change the display settings and the view
      re-renders live, like the desktop Config panel.</p>
    <div class="viewer"><aside><div class="filelist" role="navigation" aria-label="Demo files">${Object.entries(groups).map(([g, items]) =>
      `<h3>${esc(g)}</h3>${items.map(it => `<a href="#/view/${encodeURIComponent(it.id)}" data-id="${esc(it.id)}"
        class="${it.id === id ? 'on' : ''}"><span>${esc(it.name)}</span><small>${esc(it.format)}</small></a>`).join('')}`).join('')}</div>
      <div class="panel"><label for="own">Open your own file</label><input type="file" id="own">
        <p class="small mute">${isStatic() ? 'Read in your browser only, nothing is uploaded. Text, code, CSV/TSV, notebooks, images, PDF, audio and video work here; DOCX, spreadsheets, archives and data formats need the local app.'
          : 'Sent to this local app (127.0.0.1) and opened with TextView\'s Python loaders; nothing leaves your machine.'}</p></div>
      <div id="dsbox"></div></aside>
    <section><div class="vhead" id="vhead"></div><div id="vbody"><p class="mute">Loading…</p></div></section></div>`;
  let d = null;
  const draw = async () => {
    if (!d) return;
    const th = themeOf(disp.themes, s.theme), body = $('#vbody');
    $('#vhead').innerHTML = `<h2>${esc(d.title || d.name)}</h2><span class="tag a">${esc(d.format)}</span><span class="tag b">${esc(d.view)} view</span>
      <span class="tag">${esc(d.encoding || '')}</span><span class="tag">${esc(d.size_h)}</span>${d.lexer ? `<span class="tag c">lexer: ${esc(d.lexer)}</span>` : ''}
      ${d.raw && !d.local ? `<a class="small" href="${esc(d.raw)}" download="${esc(d.name)}">download</a>` : ''}`;
    const note = d.description ? `<p class="small mute">${esc(d.description)} (File → New from template… in the desktop app.)</p>` : '';
    body.innerHTML = note + '<div id="vinner"></div>' + (d.note ? `<p class="small mute">${esc(d.note)}</p>` : '');
    const inner = $('#vinner');
    if (d.view === 'table' && d.table) renderTable(inner, d, th, s);
    else if (d.view === 'image') renderImage(inner, d);
    else if (d.view === 'pdf') renderPdf(inner, d, th, s);
    else if (d.view === 'media') renderMedia(inner, d);
    else if (d.view === 'notebook' && d.notebook) renderNotebook(inner, d, th, s);
    else if (d.view === 'rendered' && d.rendered) await renderRendered(inner, d, th, s);
    else renderCode(inner, d, th, s);
  };
  const ctl = () => controls($('#dsbox'), disp.themes, s, ns => { if (!ns) { s = loadSettings(disp.defaults); ctl(); } draw(); });
  ctl();
  document.onkeydown = e => { if (location.hash.startsWith('#/view') && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 't') {
    e.preventDefault(); s.render_markdown = !s.render_markdown; ctl(); draw(); } };
  $('#own').onchange = async e => {
    const f = e.target.files[0];
    if (!f) return;
    const fd = new FormData(); fd.append('file', f);
    $('#vbody').innerHTML = '<p class="mute">Opening…</p>';
    try {
      uploaded = await api('/open', { body: fd });
      if (['image', 'pdf', 'media'].includes(uploaded.view) && !uploaded.raw) uploaded.raw = URL.createObjectURL(f);
      if (location.hash !== '#/view/upload') go('#/view/upload'); else { d = uploaded; draw(); }
    } catch (err) {
      $('#vhead').innerHTML = `<h2>${esc(f.name)}</h2>`;
      $('#vbody').innerHTML = `<p class="err">${esc(err.message)}</p><p><a href="#/inspect">Identify it with the Inspector →</a></p>`;
    }
  };
  if (id === 'upload') {
    if (!uploaded) { $('#vbody').innerHTML = '<p class="mute">Choose a file with "Open your own file".</p>'; return; }
    d = uploaded;
  } else {
    d = await api('/file/' + encodeURIComponent(id));
  }
  await draw();
});
