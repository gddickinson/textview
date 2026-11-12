// Code / text view: Pygments tokens (from the Python app) coloured with the theme's Pygments style, line-number
// gutter, word wrap, current-line highlight (click a line). Mirrors CodeViewer + apply_pygments in the desktop app.
import { esc } from './core.js';
import { themeStyle } from './display_ctl.js';

const MAX_LINES = 20000;

function styleFor(cls, th, cache) {
  if (cache.has(cls)) return cache.get(cls);
  let t = th.tokens[cls], c = cls;
  while (!t && c.length > 1) { c = c.slice(0, -1); t = th.tokens[c]; }  // nearest parent class (k -> kd ...)
  const css = t ? [t.c && `color:${t.c}`, t.bg && `background:${t.bg}`, t.b && 'font-weight:700', t.i && 'font-style:italic']
    .filter(Boolean).join(';') : '';
  cache.set(cls, css);
  return css;
}

export function linesFrom(d, th, highlight) {
  const lines = [[]], cache = new Map();
  const toks = highlight && d.tokens ? d.tokens : [['', d.text || '']];
  for (const [cls, val] of toks) {
    const css = styleFor(cls, th, cache), parts = val.split('\n');
    parts.forEach((p, i) => {
      if (i > 0) lines.push([]);
      if (p) lines[lines.length - 1].push(css ? `<span style="${css}">${esc(p)}</span>` : esc(p));
    });
  }
  if (lines.length > 1 && !lines[lines.length - 1].length) lines.pop();
  return lines;
}

export function renderCode(host, d, th, s) {
  const lines = linesFrom(d, th, s.syntax_highlight);
  const shown = lines.slice(0, MAX_LINES);
  const gut = `background:${th.line_number_bg};color:${th.line_number_fg};`;
  host.innerHTML = `<div class="code${s.word_wrap ? ' wrap' : ''}" style="${themeStyle(th, s)}padding:${Math.round(s.padding / 2)}px 0">
    <table role="presentation"><tbody>${shown.map((l, i) => `<tr data-i="${i}">${s.show_line_numbers
      ? `<td class="ln" style="${gut}">${i + 1}</td>` : ''}<td class="src">${l.join('') || ' '}</td></tr>`).join('')}</tbody></table></div>
    ${lines.length > MAX_LINES ? `<p class="small mute">Showing the first ${MAX_LINES} of ${lines.length} lines.</p>` : ''}
    ${d.truncated ? '<p class="small mute">The file is longer than the web viewer shows; the desktop app opens all of it.</p>' : ''}`;
  if (s.highlight_current_line) {
    const tb = host.querySelector('tbody');
    tb.addEventListener('click', e => { const tr = e.target.closest('tr'); if (!tr) return;
      tb.querySelector('tr.cur')?.classList.remove('cur'); tr.classList.add('cur'); });
  }
}
