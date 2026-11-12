// JS port of the lexical workspace index in src/workspace_index.py: tokenize() and BM25Index (k1 = 1.5, b = 0.75).
// The static site ranks the exported demo chunks in the browser with this; bm25_engine.test.mjs checks scores and
// order against Python on the same chunks.

export function tokenize(text) {  // [t for t in re.findall(r"[a-z0-9_]+", text.lower()) if len(t) > 1]
  return (text.toLowerCase().match(/[a-z0-9_]+/g) || []).filter(t => t.length > 1);
}

export class BM25Index {
  constructor(k1 = 1.5, b = 0.75) { this.k1 = k1; this.b = b; this.docs = []; this.df = new Map(); this.lengths = []; this.avg = 0; }
  add(tokens) {
    const tf = new Map();
    for (const t of tokens) tf.set(t, (tf.get(t) || 0) + 1);
    this.docs.push(tf); this.lengths.push(tokens.length);
    for (const t of tf.keys()) this.df.set(t, (this.df.get(t) || 0) + 1);
  }
  finalize() { this.avg = this.lengths.length ? this.lengths.reduce((a, c) => a + c, 0) / this.lengths.length : 0; }
  search(q, k = 10) {
    const N = this.docs.length;
    if (!N || !q.length) return [];
    const avg = this.avg || 1, idf = new Map();
    for (const t of new Set(q)) { const df = this.df.get(t) || 0; idf.set(t, Math.log((N - df + 0.5) / (df + 0.5) + 1)); }
    const scored = [];
    this.docs.forEach((tf, i) => {
      if (!this.lengths[i]) return;
      let s = 0;
      for (const t of q) {  // query terms in order, repeats counted (as in Python)
        const f = tf.get(t) || 0;
        if (!f) continue;
        s += idf.get(t) * ((f * (this.k1 + 1)) / (f + this.k1 * (1 - this.b + this.b * this.lengths[i] / avg)));
      }
      if (s > 0) scored.push([s, i]);
    });
    scored.sort((a, c) => c[0] - a[0] || a[1] - c[1]);  // Python's sort is stable on index order
    return scored.slice(0, k);
  }
}

export function buildIndex(chunks, k1, b) {
  const ix = new BM25Index(k1, b);
  for (const c of chunks) ix.add(tokenize(c.text));
  ix.finalize();
  return ix;
}
