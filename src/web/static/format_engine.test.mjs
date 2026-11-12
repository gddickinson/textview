// node src/web/static/format_engine.test.mjs — detect_format and FormatDB.search vs Python.
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { detectFormat, searchFormats } from './format_engine.js';

const root = new URL('../../../', import.meta.url);
const { formats } = JSON.parse(readFileSync(new URL('tests/fixtures/web_engines.json', root)));
const maps = formats;
for (const [name, fmt] of Object.entries(formats.detect))
  assert.equal(detectFormat(name, maps.format_map, maps.filename_map), fmt, name);
const entries = JSON.parse(readFileSync(new URL('data/file_formats.json', root))).formats.map(e => ({
  id: e.id, name: e.name, extensions: (e.extensions || []).map(x => x.toLowerCase()),
  filenames: (e.filenames || []).map(x => x.toLowerCase()), tags: e.tags || [], description: e.description || '',
  category: e.category || 'other' }));
for (const [q, ids] of Object.entries(formats.search)) assert.deepEqual(searchFormats(entries, q).map(e => e.id), ids, q);
console.log(`formats: ${Object.keys(formats.detect).length} names + ${Object.keys(formats.search).length} queries match Python`);
