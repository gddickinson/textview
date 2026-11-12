// Live display settings for the viewer, mirroring DisplaySettings in src/settings.py (defaults come from /api/display,
// which reads that dataclass). Every change re-renders immediately, like the desktop Config panel. The viewer's
// choices are remembered in this browser (localStorage) when it is available.
import { esc } from './core.js';

const KEY = 'textview.display';
export function loadSettings(defaults) {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch { saved = {}; }
  return { ...defaults, ...saved };
}
function save(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch { /* private mode */ } }

export const themeOf = (themes, name) => themes.find(t => t.name === name) || themes[0];

// CSS custom properties + inline style for a themed view container.
export function themeStyle(th, s) {
  return `--curline:${th.current_line};background:${th.bg};color:${th.fg};font-family:${esc(s.font_family)},ui-monospace,Menlo,monospace;`
    + `font-size:${s.font_size}px;line-height:${s.line_height};letter-spacing:${s.letter_spacing}px;tab-size:${s.tab_width};`
    + `font-weight:${s.font_weight === 'bold' ? 700 : 400};`;
}

export function controls(host, themes, s, onChange) {
  const opt = themes.map(t => `<option ${t.name === s.theme ? 'selected' : ''}>${esc(t.name)}</option>`).join('');
  host.innerHTML = `<div class="ctlbox panel">
    <h3>Display (live)</h3>
    <label for="ds-theme">Theme</label><select id="ds-theme">${opt}</select>
    <div class="row"><div><label for="ds-size">Font size <b id="ds-size-v">${s.font_size}</b></label>
      <input id="ds-size" type="range" min="9" max="28" value="${s.font_size}"></div>
      <div><label for="ds-lh">Line height <b id="ds-lh-v">${s.line_height}</b></label>
      <input id="ds-lh" type="range" min="1" max="2.4" step="0.1" value="${s.line_height}"></div></div>
    ${[['show_line_numbers', 'Line numbers'], ['word_wrap', 'Word wrap'], ['syntax_highlight', 'Syntax highlighting'],
      ['highlight_current_line', 'Highlight current line'], ['render_markdown', 'Render markdown / documents (Ctrl+T)']]
      .map(([k, l]) => `<label class="chk"><input type="checkbox" data-k="${k}" ${s[k] ? 'checked' : ''}> ${l}</label>`).join('')}
    <button class="alt" id="ds-reset" type="button">Reset to defaults</button></div>`;
  const fire = () => { save(s); onChange(s); };
  host.querySelector('#ds-theme').onchange = e => { s.theme = e.target.value; fire(); };
  host.querySelector('#ds-size').oninput = e => { s.font_size = +e.target.value; host.querySelector('#ds-size-v').textContent = s.font_size; fire(); };
  host.querySelector('#ds-lh').oninput = e => { s.line_height = +e.target.value; host.querySelector('#ds-lh-v').textContent = s.line_height; fire(); };
  host.querySelectorAll('input[data-k]').forEach(c => { c.onchange = () => { s[c.dataset.k] = c.checked; fire(); }; });
  host.querySelector('#ds-reset').onclick = () => { try { localStorage.removeItem(KEY); } catch { /* ignore */ } onChange(null); };
}

// Remove active content from HTML rendered out of user files before it goes into the page.
export function sanitize(html) {
  const doc = new DOMParser().parseFromString(`<div>${html}</div>`, 'text/html');
  doc.querySelectorAll('script,iframe,object,embed,style,link,meta,form').forEach(n => n.remove());
  doc.querySelectorAll('*').forEach(n => [...n.attributes].forEach(a => {
    if (/^on/i.test(a.name) || (/^(href|src|xlink:href)$/i.test(a.name) && /^\s*javascript:/i.test(a.value))) n.removeAttribute(a.name);
  }));
  return doc.body.firstChild.innerHTML;
}
