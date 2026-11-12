// Viewers for images (brightness / contrast / saturation / gamma / auto-contrast via image_engine.js, the tested port
// of src/image_adjust.py; RGB histogram; eyedropper), PDFs (browser rendering + TextView's extracted text), audio /
// video (browser playback, as QMediaPlayer does on the desktop), notebooks and rendered markdown / DOCX / archives.
import { api, esc, slider } from './core.js';
import { themeStyle, sanitize } from './display_ctl.js';
import { adjust, histogram } from './image_engine.js';
import { renderCode } from './view_code.js';

export function renderImage(host, d) {
  const info = d.image ? `${d.image.width} × ${d.image.height} px · ${esc(d.image.mode)} · ${d.image.frames} frame${d.image.frames > 1 ? 's' : ''}` : '';
  host.innerHTML = `<div class="imgwrap"><div><canvas class="pic" aria-label="${esc(d.name)}"></canvas>
      <p class="small mute">${info} ${d.image && d.image.frames > 1 ? '· the web view shows frame 1; the desktop app steps through every frame' : ''}</p></div>
    <div class="panel"><h3>Adjust</h3><div id="ia-sl"></div>
      <label class="chk"><input type="checkbox" id="ia-auto"> Auto-contrast (min/max stretch)</label>
      <button class="alt" id="ia-reset" type="button">Reset</button>
      <h3>Histogram</h3><canvas class="hist" width="256" height="110" aria-label="RGB histogram"></canvas>
      <h3>Eyedropper</h3><p class="small" id="ia-pick">Click the image to read a pixel.</p></div></div>`;
  const pic = host.querySelector('canvas.pic'), ctx = pic.getContext('2d', { willReadFrequently: true });
  const p = { brightness: 1, contrast: 1, saturation: 1, gamma: 1, autoscale: false };
  let base = null, cur = null;
  const draw = () => {
    if (!base) return;
    cur = adjust(base.data, p);
    ctx.putImageData(new ImageData(cur, base.width, base.height), 0, 0);
    drawHist(host.querySelector('canvas.hist'), histogram(cur));
  };
  const sl = host.querySelector('#ia-sl'), inputs = [];
  for (const [k, l, min, max] of [['brightness', 'Brightness', 0, 3], ['contrast', 'Contrast', 0, 3], ['saturation', 'Saturation', 0, 3], ['gamma', 'Gamma', 0.2, 3]])
    inputs.push([k, slider(sl, { id: `ia-${k}`, label: l, min, max, step: 0.05, value: 1, fmt: v => (+v).toFixed(2) }, v => { p[k] = v; draw(); })]);
  host.querySelector('#ia-auto').onchange = e => { p.autoscale = e.target.checked; draw(); };
  host.querySelector('#ia-reset').onclick = () => { Object.assign(p, { brightness: 1, contrast: 1, saturation: 1, gamma: 1, autoscale: false });
    inputs.forEach(([, el]) => { el.value = 1; el.dispatchEvent(new Event('input')); }); host.querySelector('#ia-auto').checked = false; draw(); };
  pic.onclick = e => {
    if (!cur) return;
    const r = pic.getBoundingClientRect(), x = Math.floor((e.clientX - r.left) * pic.width / r.width), y = Math.floor((e.clientY - r.top) * pic.height / r.height);
    const i = (y * pic.width + x) * 4, hex = '#' + [0, 1, 2].map(c => cur[i + c].toString(16).padStart(2, '0')).join('');
    host.querySelector('#ia-pick').innerHTML = `<span style="display:inline-block;width:14px;height:14px;background:${hex};border:1px solid #888;vertical-align:middle"></span>
      <code>${hex}</code> at (${x}, ${y}) · rgb(${cur[i]}, ${cur[i + 1]}, ${cur[i + 2]})`;
  };
  const img = new Image();
  img.onload = () => { pic.width = img.naturalWidth; pic.height = img.naturalHeight; ctx.drawImage(img, 0, 0);
    base = ctx.getImageData(0, 0, pic.width, pic.height); draw(); };
  img.onerror = () => { host.querySelector('.imgwrap').insertAdjacentHTML('afterbegin', '<p class="err">The browser cannot decode this image format (the desktop app uses Pillow).</p>'); };
  img.src = d.raw;
}

function drawHist(cv, h) {
  const c = cv.getContext('2d'), max = Math.max(1, ...h.flatMap(a => [...a]));
  c.clearRect(0, 0, 256, 110); c.globalCompositeOperation = 'lighter';
  ['#ff4d6a', '#3dff8f', '#4f9dff'].forEach((col, k) => { c.fillStyle = col + 'aa';
    for (let i = 0; i < 256; i++) { const v = (h[k][i] / max) * 106; c.fillRect(i, 110 - v, 1, v); } });
  c.globalCompositeOperation = 'source-over';
}

export function renderPdf(host, d, th, s) {
  host.innerHTML = `<div class="seg" role="group" aria-label="PDF mode"><button type="button" class="${s.render_markdown ? 'on' : ''}" data-m="1">Rendered</button><button type="button" class="${s.render_markdown ? '' : 'on'}" data-m="0">Extracted text</button></div>
    <div id="pdfbody" style="margin-top:10px"></div>`;
  const body = host.querySelector('#pdfbody');
  const show = r => {
    host.querySelectorAll('.seg button').forEach(b => b.classList.toggle('on', b.dataset.m === (r ? '1' : '0')));
    if (r) body.innerHTML = `<object class="pdfobj" data="${esc(d.raw)}" type="application/pdf" aria-label="${esc(d.name)}">
        <p class="small">This browser does not show PDFs inline: <a href="${esc(d.raw)}" target="_blank" rel="noopener">open ${esc(d.name)}</a>.</p></object>`;
    else if (d.text != null) renderCode(body, d, th, s);
    else body.innerHTML = '<p class="static-note">Text extraction uses pypdf in the local app.</p>';
  };
  host.querySelectorAll('.seg button').forEach(b => { b.onclick = () => show(b.dataset.m === '1'); });
  show(s.render_markdown);
}

export function renderMedia(host, d) {
  const audio = /^(audio)$/.test(d.format) || /\.(mp3|wav|flac|ogg|oga|opus|aac|m4a|aiff?|amr|midi?|wma)$/i.test(d.name);
  host.innerHTML = audio ? `<div class="panel"><p class="mono">♪ ${esc(d.name)}</p><audio controls src="${esc(d.raw)}" style="width:100%"></audio></div>`
    : `<video controls src="${esc(d.raw)}" style="width:100%;max-height:70vh;background:#000;border-radius:6px"></video>`;
  host.insertAdjacentHTML('beforeend', '<p class="small mute">Playback uses the browser\'s codecs; the desktop app uses Qt Multimedia (FFmpeg).</p>');
}

export function renderNotebook(host, d, th, s) {
  const cells = d.notebook.cells;
  host.innerHTML = `<div style="${themeStyle(th, s)}padding:10px 14px;border-radius:6px">${cells.map((c, i) => c.type === 'markdown'
    ? `<div class="nbcell md" style="font-family:var(--sans)">${c.html ? sanitize(c.html) : `<pre>${esc(c.source)}</pre>`}</div>`
    : `<div class="nbcell code"><div class="count">In [${c.count ?? ' '}]:</div><div data-cell="${i}"></div>${(c.outputs || []).map(o => o.kind === 'png'
      ? `<img alt="cell ${i} output" src="data:image/png;base64,${o.data}" style="max-width:100%">`
      : `<pre class="nbout" style="background:${th.current_line}">${esc(o.text)}</pre>`).join('')}</div>`).join('')}</div>
    <p class="small mute">Read-only here. The desktop app edits cells and runs them on a Jupyter kernel (F5).</p>`;
  host.querySelectorAll('[data-cell]').forEach(el => { const c = cells[+el.dataset.cell];
    renderCode(el, { text: c.source, tokens: c.tokens }, th, { ...s, show_line_numbers: false, highlight_current_line: false }); });
}

export async function renderRendered(host, d, th, s) {
  if (!s.render_markdown || d.local) { renderCode(host, d, th, s); return; }
  const r = d.html_by_theme ? { html: d.html_by_theme[th.name] } : await api(`/rendered/${encodeURIComponent(d.id)}/${th.slug}`);
  host.innerHTML = `<iframe class="rframe" sandbox="allow-same-origin" title="Rendered ${esc(d.name)}"></iframe>`;
  const fr = host.querySelector('iframe');
  fr.onload = () => { try { fr.style.height = Math.min(4000, fr.contentDocument.documentElement.scrollHeight + 10) + 'px'; } catch { /* ignore */ } };
  fr.srcdoc = r.html;
}
