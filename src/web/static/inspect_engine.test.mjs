// node src/web/static/inspect_engine.test.mjs — JS inspector + security scan vs Python (tests/fixtures/web_engines.json).
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { inspectBytes, looksBinary } from './inspect_engine.js';
import { scanBytes } from './scan_engine.js';

const fx = JSON.parse(readFileSync(new URL('../../../tests/fixtures/web_engines.json', import.meta.url)));
const sameEnc = (a, b) => a === b || (['ascii', 'utf-8'].includes(a) && ['ascii', 'utf-8'].includes(b));
let n = 0;
for (const c of fx.inspect) {
  const bytes = Uint8Array.from(Buffer.from(c.hex, 'hex'));
  const js = inspectBytes(c.name, bytes), py = c.info;
  for (const k of ['size', 'size_human', 'extension', 'detected_kind', 'detected_via', 'description', 'is_text', 'hex_preview', 'suggested_action'])
    assert.deepEqual(js[k], py[k], `${c.name}: ${k}`);
  // chardet (Python) vs TextDecoder (JS): ASCII and UTF-8 are the only encodings recognised here, and chardet
  // sometimes labels pure ASCII as utf-8.
  assert.ok(sameEnc(js.encoding, py.encoding), `${c.name}: encoding ${js.encoding} vs ${py.encoding}`);
  if (py.is_text) assert.equal(js.text_sample, py.text_sample, `${c.name}: text_sample`);
  assert.equal(looksBinary(bytes.subarray(0, 4096)), c.binary, `${c.name}: looks_binary`);
  assert.deepEqual(scanBytes(c.name, bytes).findings, c.findings, `${c.name}: scan findings`);
  n++;
}
console.log(`inspect/scan: ${n} files match Python`);
