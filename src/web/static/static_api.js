// Static-site data layer: answers api() calls without the Python server.
// GET paths are the JSON exported by scripts/build_static.py (made by TextView's Python code at build time).
// The rest runs in the browser on JS ports tested against Python (see *_engine.test.mjs):
//   /search?q=  -> bm25_engine.js over the exported demo chunks
//   POST /open  -> local_open.js (text, code, CSV/TSV, JSON, notebooks, images, PDF); other formats need the app
//   POST /inspect -> inspect_engine.js + scan_engine.js + format_engine.js
import { buildIndex, tokenize } from './bm25_engine.js';
import { scanBytes } from './scan_engine.js';
import { detectFormat } from './format_engine.js';

const files = new Map();
function file(rel) {
  if (!files.has(rel)) files.set(rel, fetch('api/' + rel + '.json').then(r => { if (!r.ok) throw new Error(`${r.status} ${rel}`); return r.json(); }));
  return files.get(rel);
}

let index = null;
async function search(q, k) {
  const corpus = await file('corpus');
  index ??= buildIndex(corpus.chunks, corpus.k1, corpus.b);
  const hits = index.search(tokenize(q), k);
  return { query: q, tokens: tokenize(q), hits: hits.map(([score, i]) => { const c = corpus.chunks[i];
    return { score, index: i, path: c.path, kind: c.kind, locator: c.locator, title: c.title, snippet: c.text.slice(0, 240) }; }) };
}

async function inspect(f) {
  const bytes = new Uint8Array(await f.arrayBuffer());
  const { info, risk, findings } = scanBytes(f.name, bytes);
  const fm = await file('formats'), db = await file('formatdb');
  const low = f.name.toLowerCase(), ext = info.extension;
  const known = fm.filename_map[low] || fm.format_map[ext] || fm.format_map[ext.toLowerCase()]
    || ['.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst'].some(c => low.endsWith(c));
  const fmt = known ? detectFormat(f.name, fm.format_map, fm.filename_map) : null;
  const entry = db.entries.find(e => ext && e.extensions.includes(ext)) || db.entries.find(e => e.filenames.includes(low))
    || db.entries.find(e => e.id === info.detected_kind);
  const group = fmt ? fm.groups.find(g => g.format === fmt) : null;
  return { name: f.name, info, binary: (await import('./inspect_engine.js')).looksBinary(bytes.subarray(0, 4096)),
    native_format: fmt, native_view: group ? group.view : null, scan: { risk, findings }, db_entry: entry ? entry.id : null };
}

export async function staticApi(path, body) {
  const [clean, qs] = path.replace(/^\/+/, '').split('?');
  const q = new URLSearchParams(qs || '');
  if (clean === 'search') return search(q.get('q') || '', Math.max(1, Math.min(+q.get('k') || 8, 50)));
  if (clean === 'inspect') return inspect(body.get('file'));
  if (clean === 'open') return (await import('./local_open.js')).openLocal(body.get('file'));
  return file(clean);
}
