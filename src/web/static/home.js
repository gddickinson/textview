// Home page: hero, real counts from the repo, the README's "Why TextView" list, screenshots, and links to the pages.
import { route, app, api, esc, isStatic } from './core.js';
import { sanitize } from './display_ctl.js';

route('home', async () => {
  const info = await api('/info'), c = info.counts;
  app().innerHTML = `<section class="hero"><p class="kicker">PyQt6 file viewer · AI agent · workspace RAG</p>
    <h1 class="glow">TextView</h1>
    <p class="lead">${esc(info.description)} Open code in dozens of languages, markdown, LaTeX, PDF, DOCX, notebooks,
      spreadsheets, SQLite, archives, scientific data, images, audio and video, with live themes. This site runs the
      viewer, the unknown-file inspector, the format database and the workspace search on TextView's own code.</p>
    <a class="btn" href="#/view/example.md">Open the viewer</a><a class="btn alt" href="#/inspect">Inspect a file</a>
    <a class="btn alt" href="#/search">Try workspace search</a></section>
    <div class="tiles">
      <div class="tile"><b>${c.extensions}</b><span>file extensions mapped to a viewer</span></div>
      <div class="tile"><b>${c.formats}</b><span>distinct format ids</span></div>
      <div class="tile"><b>${c.themes}</b><span>live colour themes</span></div>
      <div class="tile"><b>${c.templates}</b><span>new-file templates</span></div>
      <div class="tile"><b>${c.format_db}</b><span>entries in the format database</span></div>
      <div class="tile"><b>${c.docs}</b><span>docs pages</span></div></div>
    <div class="grid">
      <a class="card" href="#/view"><b>Viewer</b><span>${c.samples} sample files plus every template: code, markdown, CSV/XLSX tables with
        filters and column statistics, DOCX, PDF, notebook, image adjustments, archive listing. Or open your own file.</span></a>
      <a class="card" href="#/inspect"><b>Unknown-file inspector</b><span>Magic-byte identification, hex preview and the open-time
        security scan (macros, PDF JavaScript, script droppers, renamed executables).</span></a>
      <a class="card" href="#/formats"><b>Formats</b><span>Every extension TextView opens and the viewer it uses, plus the searchable
        file-format reference.</span></a>
      <a class="card" href="#/search"><b>Workspace search</b><span>The BM25 index behind the agent's citations, over this repo's docs and
        samples: the retrieval half of workspace RAG, without an LLM.</span></a>
      <a class="card" href="#/docs/workspace-rag"><b>AI features</b><span>Chat, workspace RAG, the agent that writes format handlers:
        desktop-only (they need an API key). Read how they work in the docs.</span></a>
      <a class="card" href="#/about"><b>About</b><span>Run the desktop app or this web app, what the web version leaves out, credits.</span></a></div>
    <h2>Why TextView</h2><p class="small mute">From the README.</p>
    <div class="why">${info.why.items.map(i => `<div class="card"><b>${esc(i.title)}</b>${sanitize(i.html)}</div>`).join('')}</div>
    <h2>The desktop app</h2><p class="small mute">Screenshots from the repo (docs/screenshots).</p>
    <div class="shots">${info.why.shots.map(s => `<figure><img loading="lazy" src="api/shot/${esc(s.file)}" alt="${esc(s.alt)}"><figcaption>${esc(s.alt)}</figcaption></figure>`).join('')}</div>
    ${isStatic() ? '<p class="small mute">Static site: Python-only steps were run when the site was built; the chat agent needs the desktop app.</p>' : ''}`;
});
