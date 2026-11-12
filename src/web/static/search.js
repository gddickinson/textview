// Workspace search page: the BM25 retrieval behind the agent's query_workspace tool, over this repo's docs/ and
// sample_files/. Python (local app) or bm25_engine.js (static site) rank the same chunks with the same scores.
import { route, app, api, esc, isStatic, go, $ } from './core.js';

const EXAMPLES = ['citations locator', 'pdf page', 'quarantine', 'notebook cell output', 'format handler script', 'theme font size'];

route('search', async (args, query) => {
  const c = await api('/corpus');
  const q = query.q || '';
  app().innerHTML = `<h1>Workspace search</h1>
    <p class="lead">TextView chunks a project by format-natural units (text and code by 40-line windows, PDFs by page,
      notebooks by cell, images by name) and ranks chunks with BM25. The chat agent's answers cite these
      <code>(file, locator)</code> hits; here you get the hits without the LLM.</p>
    <div class="tiles"><div class="tile"><b>${c.n_files}</b><span>files in ${c.dirs.map(esc).join(' + ')}</span></div>
      <div class="tile"><b>${c.n_chunks}</b><span>chunks</span></div>
      ${Object.entries(c.by_kind).map(([k, n]) => `<div class="tile"><b>${n}</b><span>${esc(k)} chunks</span></div>`).join('')}</div>
    <form id="sf" class="row" role="search"><div><label for="sq">Query</label><input id="sq" value="${esc(q)}" placeholder="what to look for"></div>
      <div style="flex:0"><button type="submit">Search</button></div></form>
    <p class="small">Try: ${EXAMPLES.map(e => `<a href="#/search?q=${encodeURIComponent(e)}">${esc(e)}</a>`).join(' · ')}</p>
    <div id="hits"></div>
    <p class="small mute">Ranking: ${isStatic() ? 'bm25_engine.js in your browser (scores match workspace_index.BM25Index to 1e-9)' : 'workspace_index.BM25Index in Python'};
      k1 = ${c.k1}, b = ${c.b}. Embedding re-rank and the chat answer need the desktop app. <a href="#/docs/workspace-rag">Docs →</a></p>`;
  $('#sf').onsubmit = e => { e.preventDefault(); go('#/search?q=' + encodeURIComponent($('#sq').value)); };
  if (!q.trim()) return;
  const r = await api('/search?q=' + encodeURIComponent(q) + '&k=10');
  const re = r.tokens.length ? new RegExp(`(${r.tokens.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi') : null;
  const mark = s => (re ? esc(s).replace(re, '<mark>$1</mark>') : esc(s));
  $('#hits').innerHTML = r.hits.length ? r.hits.map((h, i) => {
    const doc = h.path.startsWith('docs/') && h.path.endsWith('.md') ? `#/docs/${h.path.slice(5, -3)}` : `#/view/${encodeURIComponent(h.path.split('/').pop())}`;
    return `<div class="card hit"><b>${i + 1}. <a href="${doc}">${esc(h.path)}</a></b> <span class="tag c">${esc(h.locator || 'file')}</span>
      <span class="tag">${esc(h.kind)}</span> <span class="small mute">score ${h.score.toFixed(3)}</span><div class="snip">${mark(h.snippet)}</div></div>`;
  }).join('') : '<p class="mute">No chunk contains those terms.</p>';
});
