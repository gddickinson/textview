// Docs reader: the repo's docs/*.md (the same files the desktop Help menu and the agent's read_doc tool use),
// rendered with Python-Markdown at build time.
import { route, app, api, esc } from './core.js';
import { sanitize } from './display_ctl.js';

route('docs', async (args) => {
  const name = args[0] || 'INDEX';
  const [ix, d] = await Promise.all([api('/docs'), api('/doc/' + encodeURIComponent(name))]);
  app().innerHTML = `<div class="side"><nav class="docnav panel" aria-label="Docs">${ix.groups.map(g => `<h3>${esc(g.label)}</h3>
      ${g.docs.map(x => `<a href="#/docs/${esc(x.name)}" class="${x.name === name ? 'on' : ''}">${esc(x.title)}</a>`).join('')}`).join('')}</nav>
    <article class="doc">${sanitize(d.html)}
      <p class="small mute">Source: <a href="https://github.com/gddickinson/textview/blob/main/docs/${esc(name)}.md">docs/${esc(name)}.md</a></p></article></div>`;
});
