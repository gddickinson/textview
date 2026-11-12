// JS port of src/file_inspector.py (unknown-file inspector): magic-byte table, extension hints, kind detection,
// binary heuristic, text sniff, hex dump, human size and suggested action. Tested against the Python module in
// inspect_engine.test.mjs (fixtures from scripts/make_web_fixtures.py). Text sniffing differs on purpose: Python uses
// chardet; here only ASCII / UTF-8 are recognised (other encodings report as not text).

const b = s => Array.from(s, c => c.charCodeAt(0));
// [offset, bytes, kind, description] — same order as _MAGIC (first match wins).
export const MAGIC = [
  [0, b('\x1f\x8b\x08'), 'gzip', 'Gzip-compressed data'],
  [0, b('\x42\x5a\x68'), 'bzip2', 'Bzip2-compressed data'],
  [0, b('\xfd7zXZ\x00'), 'xz', 'XZ-compressed data'],
  [0, b('\x28\xb5\x2f\xfd'), 'zstd', 'Zstandard-compressed data'],
  [0, b('\x52\x61\x72\x21\x1a\x07'), 'rar', 'RAR archive'],
  [0, b('7z\xbc\xaf\x27\x1c'), '7z', '7-Zip archive'],
  [0, b('PK\x03\x04'), 'zip', 'ZIP archive (could also be jar/docx/xlsx/odf)'],
  [0, b('PK\x05\x06'), 'zip-empty', 'Empty ZIP archive'],
  [0, b('%PDF-'), 'pdf', 'Portable Document Format'],
  [0, b('\x89PNG\r\n\x1a\n'), 'png', 'PNG image'],
  [0, b('\xff\xd8\xff'), 'jpeg', 'JPEG image'],
  [0, b('GIF8'), 'gif', 'GIF image'],
  [0, b('BM'), 'bmp', 'BMP image'],
  [0, b('RIFF'), 'riff', 'RIFF container (WAV / WebP / AVI)'],
  [4, b('ftyp'), 'mp4', 'MP4 / QuickTime / M4A container'],
  [0, b('OggS'), 'ogg', 'Ogg container'],
  [0, b('fLaC'), 'flac', 'FLAC audio'],
  [0, b('ID3'), 'mp3', 'MP3 audio (ID3v2)'],
  [0, b('PAR1'), 'parquet', 'Apache Parquet columnar storage'],
  [0, b('ARROW1'), 'arrow', 'Apache Arrow IPC'],
  [0, b('\x89HDF\r\n\x1a\n'), 'hdf5', 'HDF5 hierarchical data'],
  [0, b('\x93NUMPY'), 'npy', 'NumPy array (.npy)'],
  [0, b('PK\x03\x04'), 'npz', 'NumPy archive (.npz, ZIP)'],
  [0, b('SQLite format 3\x00'), 'sqlite', 'SQLite database'],
  [0, b('\x80\x04'), 'pickle4', 'Python pickle (protocol 4)'],
  [0, b('\x80\x05'), 'pickle5', 'Python pickle (protocol 5)'],
  [0, b('MATLAB '), 'mat', 'MATLAB MAT-file (v5+)'],
  [0, b('SIMPLE  ='), 'fits', 'FITS astronomy data'],
  [0, b('\x00\x00\x27\x0a'), 'shp', 'ESRI shapefile'],
  [0, b('PCAP'), 'pcap', 'Network packet capture'],
  [0, b('\xd4\xc3\xb2\xa1'), 'pcap', 'Network packet capture (libpcap)'],
  [0, b('\x0a\x0d\x0d\x0a'), 'pcapng', 'Network packet capture (PCAP-NG)'],
  [0, b('\x7fELF'), 'elf', 'ELF executable / shared object'],
  [0, b('\xfe\xed\xfa\xce'), 'macho32', 'Mach-O executable (32-bit)'],
  [0, b('\xfe\xed\xfa\xcf'), 'macho64', 'Mach-O executable (64-bit)'],
  [0, b('\xca\xfe\xba\xbe'), 'macho-fat', 'Mach-O universal binary'],
  [0, b('\xcf\xfa\xed\xfe'), 'macho64-le', 'Mach-O 64-bit (little endian)'],
  [0, b('MZ'), 'pe', 'Windows PE / DOS executable'],
  [0, b('\x00asm'), 'wasm', 'WebAssembly module'],
  [0, b('\xca\xfe\xba\xbe\x00\x00\x00'), 'java-class', 'Java class file'],
  [0, b('\x00\x01\x00\x00'), 'ttf', 'TrueType font'],
  [0, b('OTTO'), 'otf', 'OpenType font'],
  [0, b('wOFF'), 'woff', 'Web Open Font Format'],
  [0, b('wOF2'), 'woff2', 'Web Open Font Format 2'],
  [0, b('<?xml'), 'xml', 'XML document'],
  [0, b('<!DOC'), 'html', 'HTML document'],
  [0, b('BC\xc0\xde'), 'bitcode', 'LLVM bitcode'],
  [0, b('#!/'), 'script', 'Shebang script'],
  [0, b('\x42\x52'), 'br', 'Brotli stream (heuristic)'],
];

export const EXT_HINTS = {
  '.parquet': ['parquet', 'Apache Parquet columnar storage'], '.feather': ['feather', 'Apache Arrow Feather columnar storage'],
  '.arrow': ['arrow', 'Apache Arrow IPC'], '.h5': ['hdf5', 'HDF5 hierarchical data'], '.hdf5': ['hdf5', 'HDF5 hierarchical data'],
  '.nc': ['netcdf', 'NetCDF scientific data (HDF5-based)'], '.sqlite': ['sqlite', 'SQLite database'],
  '.db': ['sqlite?', 'Database file (likely SQLite or similar)'], '.npy': ['npy', 'NumPy array'],
  '.npz': ['npz', 'NumPy zipped archive of arrays'],
  '.pkl': ['pickle', 'Python pickle (NEVER load from untrusted sources)'],
  '.pickle': ['pickle', 'Python pickle (NEVER load from untrusted sources)'], '.mat': ['mat', 'MATLAB MAT-file'],
  '.fits': ['fits', 'FITS astronomy data'], '.fit': ['fits', 'FITS astronomy data'],
  '.shp': ['shp', 'ESRI shapefile (geometry; needs .dbf + .shx siblings)'], '.geojson': ['geojson', 'GeoJSON geographic features'],
  '.kml': ['kml', 'Keyhole Markup Language (geographic)'], '.gpx': ['gpx', 'GPS Exchange Format'],
  '.dwg': ['dwg', 'AutoCAD drawing'], '.dxf': ['dxf', 'Drawing Exchange Format (CAD)'],
  '.dbc': ['dbc', 'CAN bus database (Vector format)'], '.pcap': ['pcap', 'Network packet capture'],
  '.pcapng': ['pcapng', 'Network packet capture (PCAP-NG)'], '.wasm': ['wasm', 'WebAssembly module'],
  '.jar': ['jar', 'Java archive (ZIP-based)'], '.war': ['war', 'Java web archive (ZIP-based)'],
  '.whl': ['whl', 'Python wheel (ZIP-based)'], '.egg': ['egg', 'Python egg (ZIP-based)'], '.dmg': ['dmg', 'macOS disk image'],
  '.iso': ['iso', 'Optical disc image'], '.deb': ['deb', 'Debian package'], '.rpm': ['rpm', 'Red Hat package'],
  '.bin': ['binary', 'Generic binary file'], '.dat': ['data', 'Generic data file'], '.pb': ['protobuf', 'Protocol Buffer (probably binary)'],
};

const pickle = 'WARNING: pickle is unsafe for untrusted files. Inspect bytes only.';
const otool = 'Use `otool -h` (macOS) or `objdump`.';
const ACTIONS = {
  parquet: 'Use `pyarrow` or `pandas.read_parquet` to inspect rows.', arrow: 'Use `pyarrow` or `polars` to inspect rows.',
  feather: 'Use `pyarrow.feather.read_table` or `pandas.read_feather`.',
  hdf5: 'Use `h5py` to walk groups; `xarray` for labelled NetCDF-style data.', netcdf: 'Use `netCDF4` or `xarray.open_dataset`.',
  sqlite: 'Open with `sqlite3` (Python stdlib) or any SQLite browser.', npy: 'Load with `numpy.load`.',
  npz: 'Load with `numpy.load` (returns a dict-like archive).', pickle, pickle4: pickle, pickle5: pickle,
  mat: 'Use `scipy.io.loadmat` (or `h5py` for v7.3+ files).', fits: 'Use `astropy.io.fits` to inspect headers and image/table data.',
  shp: 'Use `geopandas` or `pyshp` (also needs .dbf and .shx siblings).', geojson: "Plain JSON — TextView's JSON view should handle it.",
  pcap: 'Use `scapy` or open in Wireshark.', pcapng: 'Use `scapy` or open in Wireshark.',
  wasm: "Use `wasmtime` to run; `wabt`'s `wasm-objdump` to inspect.", elf: 'Use `readelf -a` or `objdump -d` to disassemble.',
  macho32: otool, macho64: otool, 'macho64-le': otool, 'macho-fat': 'Use `lipo -info` to list architectures.',
  pe: 'Use `pefile` (Python) or `objdump`.', dwg: 'Convert with LibreCAD / `libredwg-converter`.', dxf: 'Use `ezdxf` (Python).',
  dbc: 'Use `cantools` (Python) to decode CAN messages.', zip: 'Use `unzip -l` or open ZIP-based document with its real handler.',
  jar: 'Java archive — `jar tf` to list entries.', whl: 'Python wheel — `unzip -l` to list contents.',
  gzip: 'Decompress with `gunzip` or `gzip -d` first.', bzip2: 'Decompress with `bunzip2` first.', xz: 'Decompress with `xz -d` first.',
  zstd: 'Decompress with `zstd -d` first.', rar: 'Decompress with `unrar`.',
  'sqlite?': 'Try opening with `sqlite3` — file extension is ambiguous.',
};

export function extOf(name) {  // Path(name).suffix.lower()
  const base = name.split('/').pop();
  const i = base.lastIndexOf('.');
  return i > 0 && i < base.length - 1 ? base.slice(i).toLowerCase() : '';
}

// Generic containers an extension hint may refine (file_inspector._REFINES); other hints lose to magic bytes.
const REFINES = { zip: ['npz', 'jar', 'war', 'whl', 'egg'], hdf5: ['netcdf'], arrow: ['feather'], pickle4: ['pickle'], pickle5: ['pickle'] };

export function detectKind(head, ext) {
  for (const [off, sig, kind, desc] of MAGIC) {
    if (head.length >= off + sig.length && sig.every((v, i) => head[off + i] === v)) {
      const hint = EXT_HINTS[ext];
      if (hint && (REFINES[kind] || []).includes(hint[0])) return [hint[0], hint[1], 'extension+magic'];
      return [kind, desc, 'magic'];
    }
  }
  if (EXT_HINTS[ext]) return [EXT_HINTS[ext][0], EXT_HINTS[ext][1], 'extension'];
  return ['unknown', 'Unrecognized file format', 'heuristic'];
}

export function looksBinary(head) {
  if (!head.length) return false;
  if (head.includes(0)) return true;
  let printable = 0;
  for (const v of head) if ((v >= 32 && v < 127) || v === 9 || v === 10 || v === 13) printable++;
  return printable / head.length < 0.85;
}

export function sniffText(head) {
  if (!head.length || head.subarray(0, 1024).includes(0)) return [false, '', ''];
  const ascii = head.every(v => v < 128);
  try {
    const s = new TextDecoder('utf-8', { fatal: true }).decode(head);
    return [true, ascii ? 'ascii' : 'utf-8', [...s].slice(0, 500).join('')];
  } catch { return [false, '', '']; }
}

export function hexDump(data, width = 16) {
  const out = [];
  for (let i = 0; i < data.length; i += width) {
    const chunk = [...data.subarray(i, i + width)];
    const hex = chunk.map(v => v.toString(16).padStart(2, '0')).join(' ').padEnd(width * 3 - 1);
    const asc = chunk.map(v => (v >= 32 && v < 127 ? String.fromCharCode(v) : '.')).join('');
    out.push(`${i.toString(16).padStart(8, '0')}  ${hex}  ${asc}`);
  }
  return out.join('\n');
}

export function humanSize(n) {
  for (const u of ['B', 'KB', 'MB', 'GB', 'TB']) {
    if (n < 1024) return u === 'B' ? `${n} B` : `${n.toFixed(1)} ${u}`;
    n /= 1024;
  }
  return `${n.toFixed(1)} PB`;
}

export function suggestAction(kind, ext) {
  if (ACTIONS[kind]) return ACTIONS[kind];
  if (['.bin', '.dat', '.raw'].includes(ext))
    return 'Generic binary container — context-dependent. Ask the chat agent for likely interpretations, or open in a hex editor.';
  return "TextView doesn't natively handle this format. Ask the chat agent (Ctrl+J) — it can identify likely tools and write a TextView script to handle this extension going forward.";
}

// inspect_file() minus path / mtime: bytes is a Uint8Array of the whole file (only the first 4096 are examined).
export function inspectBytes(name, bytes) {
  const head = bytes.subarray(0, 4096), ext = extOf(name);
  const [kind, desc, via] = detectKind(head, ext);
  const [isText, enc, sample] = sniffText(head);
  return { size: bytes.length, size_human: humanSize(bytes.length), extension: ext, detected_kind: kind,
    detected_via: via, description: desc, is_text: isText, encoding: enc, text_sample: sample,
    hex_preview: hexDump(head.subarray(0, 256)), suggested_action: suggestAction(kind, ext) };
}
