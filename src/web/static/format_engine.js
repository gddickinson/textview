// JS ports of format lookup: file_loader.detect_format() (which viewer TextView would use for a file name) and
// format_db.FormatDB.search() (the Help -> File formats database ranker). format_engine.test.mjs checks both against
// Python. The maps themselves come from the API (/formats, /formatdb), so they are never copied by hand.

export function detectFormat(name, formatMap, filenameMap) {
  const base = name.split('/').pop();
  const byName = filenameMap[base.toLowerCase()];
  if (byName) return byName;
  const low = base.toLowerCase();
  if (['.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst'].some(c => low.endsWith(c))) return 'archive';
  const i = base.lastIndexOf('.');
  const suffix = i > 0 && i < base.length - 1 ? base.slice(i) : '';
  return formatMap[suffix] ?? formatMap[suffix.toLowerCase()] ?? 'plain';
}

export function searchFormats(entries, query, limit = 20) {
  const q = query.toLowerCase().trim();
  if (!q) return [];
  const scored = [];
  for (const e of entries) {
    let s = 0;
    if (q === e.id) s += 100;
    if (e.id.includes(q)) s += 30;
    if (e.name.toLowerCase().includes(q)) s += 25;
    for (const x of e.extensions) { if (q === x || q === x.replace(/^\.+/, '')) s += 60; else if (x.includes(q)) s += 15; }
    for (const f of e.filenames) { if (q === f) s += 50; else if (f.includes(q)) s += 12; }
    for (const t of e.tags) { if (q === t) s += 20; else if (t.includes(q)) s += 8; }
    if (e.description.toLowerCase().includes(q)) s += 5;
    if (e.category.toLowerCase().includes(q)) s += 4;
    if (s > 0) scored.push([s, e]);
  }
  scored.sort((a, b) => b[0] - a[0] || (a[1].id < b[1].id ? -1 : a[1].id > b[1].id ? 1 : 0));
  return scored.slice(0, limit).map(x => x[1]);
}
