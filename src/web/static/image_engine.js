// JS port of src/image_adjust.adjust() for 8-bit RGBA pixels (canvas ImageData): optional per-channel auto-contrast
// stretch, then PIL ImageEnhance Brightness / Contrast / Color (saturation) and the power-law gamma LUT, in the same
// order and with Pillow's blend arithmetic (float32, truncation, clipping when extrapolating). Alpha is untouched.
// image_engine.test.mjs compares with Python + Pillow on the same pixels (within 1 grey level).

const f32 = Math.fround;

function blend(deg, img, alpha, out) {  // Pillow ImagingBlend on the colour channels
  const a = f32(alpha), interp = alpha >= 0 && alpha <= 1;
  for (let i = 0; i < img.length; i++) {
    if ((i & 3) === 3) { out[i] = img[i]; continue; }
    const t = f32(deg[i] + f32(a * (img[i] - deg[i])));
    out[i] = interp ? Math.trunc(t) : t <= 0 ? 0 : t >= 255 ? 255 : Math.trunc(t);
  }
  return out;
}

const luma = (r, g, b) => (r * 19595 + g * 38470 + b * 7471 + 0x8000) >> 16;  // Pillow RGB -> L

function grey(px, value) {  // degenerate image: every colour channel = value(i) (alpha copied)
  const d = new Uint8ClampedArray(px.length);
  for (let i = 0; i < px.length; i += 4) {
    const v = typeof value === 'number' ? value : value(i);
    d[i] = d[i + 1] = d[i + 2] = v; d[i + 3] = px[i + 3];
  }
  return d;
}

export function stretch(px) {  // image_adjust._stretch_8bit for RGB(A): min -> 0, max -> 255 per colour channel
  const out = Uint8ClampedArray.from(px);
  for (let c = 0; c < 3; c++) {
    let mn = 255, mx = 0;
    for (let i = c; i < px.length; i += 4) { if (px[i] < mn) mn = px[i]; if (px[i] > mx) mx = px[i]; }
    if (mx <= mn) continue;
    const k = 255 / (mx - mn);
    for (let i = c; i < px.length; i += 4) out[i] = Math.min(255, Math.max(0, Math.trunc((px[i] - mn) * k)));
  }
  return out;
}

export function gammaTable(gamma) {
  const inv = 1 / gamma, t = new Uint8Array(256);
  for (let i = 0; i < 256; i++) t[i] = Math.min(255, Math.max(0, Math.trunc((i / 255) ** inv * 255 + 0.5)));
  return t;
}

// px: Uint8ClampedArray RGBA. Returns a new array; the input is not modified.
export function adjust(px, { brightness = 1, contrast = 1, saturation = 1, gamma = 1, autoscale = false } = {}) {
  let cur = autoscale ? stretch(px) : Uint8ClampedArray.from(px);
  if (brightness !== 1) cur = blend(grey(cur, 0), cur, brightness, new Uint8ClampedArray(cur.length));
  if (contrast !== 1) {
    let sum = 0;
    for (let i = 0; i < cur.length; i += 4) sum += luma(cur[i], cur[i + 1], cur[i + 2]);
    const mean = Math.trunc(sum / (cur.length / 4) + 0.5);
    cur = blend(grey(cur, mean), cur, contrast, new Uint8ClampedArray(cur.length));
  }
  if (saturation !== 1) {
    const src = cur;
    cur = blend(grey(src, i => luma(src[i], src[i + 1], src[i + 2])), src, saturation, new Uint8ClampedArray(src.length));
  }
  if (gamma !== 1 && gamma > 0) {
    const t = gammaTable(gamma);
    for (let i = 0; i < cur.length; i++) if ((i & 3) !== 3) cur[i] = t[cur[i]];
  }
  return cur;
}

// RGB histogram (256 bins per channel), as drawn by the desktop image panel.
export function histogram(px) {
  const h = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
  for (let i = 0; i < px.length; i += 4) { h[0][px[i]]++; h[1][px[i + 1]]++; h[2][px[i + 2]]++; }
  return h;
}
