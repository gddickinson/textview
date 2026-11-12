// node src/web/static/bm25_engine.test.mjs — JS BM25 vs workspace_index.BM25Index on the same chunks.
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { tokenize, buildIndex } from './bm25_engine.js';

const { bm25 } = JSON.parse(readFileSync(new URL('../../../tests/fixtures/web_engines.json', import.meta.url)));
const ix = buildIndex(bm25.chunks.map(text => ({ text })));
for (const q of bm25.queries) {
  assert.deepEqual(tokenize(q.q), q.tokens, `tokens for "${q.q}"`);
  const hits = ix.search(tokenize(q.q), 10);
  assert.deepEqual(hits.map(h => h[1]), q.hits.map(h => h[1]), `order for "${q.q}"`);
  hits.forEach((h, i) => assert.ok(Math.abs(h[0] - q.hits[i][0]) <= 1e-9 * Math.abs(q.hits[i][0]), `score ${q.q} #${i}`));
}
console.log(`bm25: ${bm25.queries.length} queries match Python over ${bm25.chunks.length} chunks`);
