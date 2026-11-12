// Static site: open a file chosen by the user entirely in the browser. Mirrors the Python payload (samples.py
// payload_for_path) for formats a browser can read without TextView's Python loaders: text and code (no syntax
// colours: those come from Pygments), CSV / TSV tables, notebooks, images, PDF, audio and video. Anything else
// (DOCX, spreadsheets, archives, scientific data, ...) needs the local app; the Inspector page still identifies it.
import { api } from './core.js';
import { detectFormat } from './format_engine.js';
import { looksBinary, humanSize } from './inspect_engine.js';
import { parseDelimited, detectNumericColumns } from './table_engine.js';

const TEXT_TABLES = new Set(['csv']);

export async function openLocal(f) {
  const fm = await api('/formats');
  const fmt = detectFormat(f.name, fm.format_map, fm.filename_map);
  const group = fm.groups.find(g => g.format === fmt);
  let view = group ? group.view : 'code';
  const base = { id: 'upload', name: f.name, format: fmt, view, size: f.size, size_h: humanSize(f.size), encoding: 'utf-8',
    rendered: false, local: true };
  if (['image', 'media', 'pdf'].includes(view)) return { ...base, encoding: 'binary', raw: URL.createObjectURL(f) };
  if (view === 'table' && !TEXT_TABLES.has(fmt))
    throw new Error(`${f.name}: ${fmt} files are read by TextView's Python loaders. Run the local app, or use the Inspector page.`);
  if (view === 'rendered' && fmt !== 'markdown')
    throw new Error(`${f.name}: ${fmt} needs the local app (Python extractor). The Inspector page can still identify it.`);
  const bytes = new Uint8Array(await f.arrayBuffer());
  if (looksBinary(bytes.subarray(0, 4096)))
    throw new Error(`${f.name} looks binary and TextView has no viewer for it in the browser. Try the Inspector page.`);
  const text = new TextDecoder('utf-8').decode(bytes);
  if (view === 'table') {
    const t = parseDelimited(text);
    return { ...base, text, table: { ...t, numeric: detectNumericColumns(t.header, t.rows) } };
  }
  if (view === 'notebook') {
    const nb = JSON.parse(text);
    const cells = (nb.cells || []).map(c => ({ type: c.cell_type, source: [].concat(c.source || []).join(''), count: c.execution_count,
      outputs: (c.outputs || []).map(o => o.output_type === 'stream' ? { kind: 'text', text: [].concat(o.text || []).join('') }
        : o.data && o.data['image/png'] ? { kind: 'png', data: [].concat(o.data['image/png']).join('').replace(/\n/g, '') }
        : o.data && o.data['text/plain'] ? { kind: 'text', text: [].concat(o.data['text/plain']).join('') }
        : o.output_type === 'error' ? { kind: 'text', text: `${o.ename}: ${o.evalue}` } : null).filter(Boolean) }));
    return { ...base, notebook: { cells } };
  }
  view = 'code';
  return { ...base, view, text, lines: text.split('\n').length, note: fmt === 'markdown'
    ? 'Rendered markdown and syntax colours come from Python-Markdown and Pygments: run the local app for those.'
    : 'Syntax colours come from Pygments: run the local app for those.' };
}
