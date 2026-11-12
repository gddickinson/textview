// Inspector page: TextView's unknown-file report and open-time security scan for a file you choose. The local app runs
// file_inspector.py + security_scanner.py; the static site runs their JS ports in your browser (nothing is uploaded).
import { route, app, api, esc, isStatic, $ } from './core.js';
import { sanitize } from './display_ctl.js';

const SEV = { dangerous: '⛔', warning: '⚠', info: 'ℹ' };

route('inspect', async () => {
  app().innerHTML = `<h1>Unknown-file inspector</h1>
    <p class="lead">When TextView opens a file it does not recognise, it identifies it from magic bytes and extension
      hints, shows a hex preview and a suggested next step, and scans it before loading: dangerous extensions, renamed
      executables, Office macros, PDF JavaScript / launch actions, scripts in HTML / SVG and shell-dropper patterns.</p>
    <div class="drop" id="drop"><label for="ifile">Choose or drop any file</label><input type="file" id="ifile">
      <p class="small mute">${isStatic() ? 'Read in your browser only, nothing is uploaded.' : 'Sent to this local app (127.0.0.1) only.'}</p></div>
    <div id="iout"></div>
    <div class="callout small">In the desktop app the report also offers the chat agent, which can search the web, write a
      format-handler script or a plugin for the new format (each behind its own safety switch). That part needs an LLM
      and is not run here. <a href="#/docs/unknown-files">How it works →</a></div>`;
  const run = async f => {
    const fd = new FormData(); fd.append('file', f);
    $('#iout').innerHTML = '<p class="mute">Inspecting…</p>';
    try { show(await api('/inspect', { body: fd })); } catch (e) { $('#iout').innerHTML = `<p class="err">${esc(e.message)}</p>`; }
  };
  $('#ifile').onchange = e => e.target.files[0] && run(e.target.files[0]);
  const drop = $('#drop');
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) run(e.dataTransfer.files[0]); };
});

async function show(r) {
  const i = r.info, s = r.scan;
  let entry = '';
  if (r.db_entry) {
    const db = await api('/formatdb'), e = db.entries.find(x => x.id === r.db_entry);
    if (e) entry = `<h2>From the file-format database</h2><div class="panel doc">${sanitize(e.html)}</div>`;
  }
  $('#iout').innerHTML = `<h2>${esc(r.name)}</h2><p><i>${esc(i.description)}</i></p>
    <div class="tiles"><div class="tile"><b>${esc(i.detected_kind)}</b><span>detected via ${esc(i.detected_via)}</span></div>
      <div class="tile"><b>${esc(i.size_human)}</b><span>${i.size.toLocaleString()} bytes</span></div>
      <div class="tile"><b>${i.is_text ? esc(i.encoding || 'text') : 'binary'}</b><span>${i.is_text ? 'text encoding' : 'not text'}</span></div>
      <div class="tile"><b class="risk sev-${s.risk === 'clean' ? 'info' : s.risk === 'dangerous' ? 'dangerous' : 'warning'}">${esc(s.risk)}</b><span>security scan</span></div></div>
    <p>${r.native_format ? `TextView opens <code>${esc(i.extension || r.name)}</code> natively as <b>${esc(r.native_format)}</b> in the ${esc(r.native_view)} view.`
      : 'TextView has no built-in viewer for this file name, so the desktop app shows this report instead.'}</p>
    <h3>Suggested action</h3><p>${esc(i.suggested_action).replace(/`([^`]+)`/g, '<code>$1</code>')}</p>
    <h3>Security findings (${s.findings.length})</h3>${s.findings.length ? `<ul>${s.findings.map(f => `<li class="sev-${f.severity}">${SEV[f.severity] || '·'}
      [${esc(f.category)}] ${esc(f.description).replace(/`([^`]+)`/g, '<code>$1</code>')}${f.detail ? `<br><span class="small mute">${esc(f.detail)}</span>` : ''}</li>`).join('')}</ul>`
      : '<p class="ok">No notable findings.</p>'}
    ${i.is_text && i.text_sample ? `<h3>Text preview</h3><pre>${esc(i.text_sample)}</pre>` : ''}
    <h3>Hex preview (first bytes)</h3><pre>${esc(i.hex_preview) || '(empty file)'}</pre>${entry}`;
}
