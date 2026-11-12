// node src/web/static/image_engine.test.mjs — image adjustments vs image_adjust.adjust (Pillow), within 1 level.
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { adjust } from './image_engine.js';

const { image } = JSON.parse(readFileSync(new URL('../../../tests/fixtures/web_engines.json', import.meta.url)));
const px = Uint8ClampedArray.from(image.pixels);
let worst = 0, off = 0;
for (const c of image.cases) {
  const out = adjust(px, c.params);
  out.forEach((v, i) => { const d = Math.abs(v - c.out[i]); worst = Math.max(worst, d); off += d > 0; });
  out.forEach((v, i) => assert.ok(Math.abs(v - c.out[i]) <= 1, `${JSON.stringify(c.params)} byte ${i}: ${v} vs ${c.out[i]}`));
}
console.log(`image: ${image.cases.length} adjustments match Pillow (max diff ${worst}, ${off} of ${px.length * image.cases.length} bytes differ)`);
