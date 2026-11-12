// JS port of the heuristic part of src/security_scanner.py (scan_file). Byte patterns run on a latin-1 view of the
// file so each byte is one character, like Python's bytes regexes. Not ported: the macOS quarantine xattr and the
// optional ClamAV pass (both need the local machine). Tested against Python in scan_engine.test.mjs.
import { inspectBytes } from './inspect_engine.js';

export const DANGEROUS_EXTENSIONS = new Set(['.exe', '.com', '.scr', '.pif', '.cpl', '.msc', '.bat', '.cmd', '.vbs', '.vbe',
  '.jse', '.wsf', '.wsh', '.hta', '.reg', '.ps1', '.psm1', '.ps2', '.ps2xml', '.psc1', '.dmg', '.pkg', '.app', '.mpkg',
  '.apk', '.ipa', '.jar', '.msi', '.cab', '.iso', '.img', '.vhd', '.vhdx', '.vmdk', '.deb', '.rpm']);
const MACRO_BEARING = new Set(['.docm', '.dotm', '.xlsm', '.xltm', '.pptm', '.potm', '.ppam', '.sldm',
  '.docx', '.dotx', '.xlsx', '.xltx', '.pptx', '.potx', '.ppsx']);
const OFFICE_PK = new Set(['.docx', '.docm', '.xlsx', '.xlsm', '.pptx', '.pptm']);

export const SCRIPT_PATTERNS = [
  [/(?:curl|wget)[^|\n]{1,200}\|\s*(?:bash|sh|zsh)\b/, 'remote-shell pipe', 'downloads + executes a script in one step'],
  [/base64\s+(?:--?d(?:ecode)?)\b[^\n]{0,80}\|\s*(?:bash|sh|zsh)\b/, 'base64-decoded shell', 'decodes content and pipes to a shell'],
  [/powershell(?:\.exe)?\s+-(?:enc(?:odedcommand)?|nop\b|w\s+hidden|exec\s+bypass)/i, 'PowerShell evasion flags', 'common in dropper / loader malware'],
  [/FromBase64String\s*\(.*?Invoke-Expression/is, 'PowerShell base64 → IEX', 'decodes base64 and executes'],
  [/\bnc\s+-[el]\w*\s/, 'netcat listener', 'potential reverse-shell pattern'],
  [/eval\s*[$(`]+\s*(?:curl|wget|fetch)\b/, 'eval-of-remote-content', 'executes whatever a remote URL returns'],
  [/(?:\\x[0-9a-fA-F]{2}){30,}/, 'hex-encoded payload', 'obfuscation trick used by shellcode loaders'],
  [/\brm\s+-[rfRF]+\s+\/+(?!tmp\b|var\b|opt\b|home\b|Users\b)/, 'destructive `rm -rf`', 'would wipe a top-level directory'],
  [/chmod\s+\+x\s+\S+\s*&&\s*[./~]/, 'stage-and-execute', 'marks a file executable then runs it'],
  [/(?:python|python3)\s+-c\s+['"][^'"]{0,80}exec\s*\(/i, 'python -c exec', 'runs arbitrary Python from an inline string'],
];
const PDF_PATTERNS = [
  [/\/JavaScript\b/, 'PDF JavaScript', 'the PDF embeds JavaScript that may run on open'],
  [/\/JS\b/, 'PDF /JS dictionary entry', 'older marker for embedded JavaScript'],
  [/\/OpenAction\b/, 'PDF OpenAction', 'PDF runs an action automatically when opened'],
  [/\/Launch\b/, 'PDF Launch action', 'PDF can launch external programs / scripts'],
  [/\/EmbeddedFile\b/, 'embedded file', 'the PDF contains another file inside it'],
  [/\/AA\b/, 'PDF additional actions', 'fires actions on focus / blur / page open'],
];
const ZIP_OK = ['.zip', '.docx', '.docm', '.dotx', '.dotm', '.xlsx', '.xlsm', '.xltx', '.xltm', '.pptx', '.pptm', '.potx',
  '.potm', '.ppsx', '.ppsm', '.odt', '.ods', '.odp', '.odg', '.odf', '.epub', '.jar', '.war', '.ear', '.apk', '.aab',
  '.ipa', '.xpi', '.crx', '.whl'];
const EXPECTED = { pdf: ['.pdf'], png: ['.png'], jpeg: ['.jpg', '.jpeg'], gif: ['.gif'], elf: ['.elf', '.so', '.out'],
  zip: ZIP_OK, macho: [''], pe: ['.exe', '.dll', '.sys', '.scr'], parquet: ['.parquet', '.pq'],
  sqlite: ['.sqlite', '.sqlite3', '.db', '.db3'], hdf5: ['.h5', '.hdf5', '.he5', '.nc', '.nc4'] };
const SCRIPT_EXTS = new Set(['.sh', '.bash', '.zsh', '.fish', '.ps1', '.psm1', '.bat', '.cmd', '.py', '.js', '.rb', '.pl', '.php']);

const latin1 = bytes => { let s = ''; for (let i = 0; i < bytes.length; i += 8192) s += String.fromCharCode(...bytes.subarray(i, i + 8192)); return s; };

// Member names from a ZIP central directory (signature PK\x01\x02; name length at +28, name at +46).
export function zipNames(bytes) {
  const names = [], dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  for (let i = 0; i + 46 <= bytes.length; i++) {
    if (bytes[i] === 0x50 && bytes[i + 1] === 0x4b && bytes[i + 2] === 1 && bytes[i + 3] === 2) {
      const n = dv.getUint16(i + 28, true);
      names.push(new TextDecoder().decode(bytes.subarray(i + 46, i + 46 + n)));
      i += 45 + n;
    }
  }
  return names;
}

export function scanBytes(name, bytes, fullBytes = 4_000_000) {
  const findings = [], add = (severity, category, description, detail = '') => findings.push({ severity, category, description, detail });
  const info = inspectBytes(name, bytes);
  const ext = info.extension, head = bytes.subarray(0, 65536);
  let body = null;
  const full = () => (body ??= latin1(bytes.subarray(0, fullBytes)));
  if (DANGEROUS_EXTENSIONS.has(ext))
    add('dangerous', 'executable_extension', `\`${ext}\` is an executable / installer / script-launcher format`,
      'opening can execute code if the user double-clicks elsewhere');
  const exp = EXPECTED[info.detected_kind] || [];
  if (exp.length && ext && !exp.includes(ext) && info.detected_via === 'magic') {
    const sev = ['pe', 'macho', 'elf'].includes(info.detected_kind) ? 'dangerous' : 'warning';
    add(sev, 'extension_mismatch', `file extension \`${ext}\` doesn't match detected kind (${info.detected_kind})`,
      'renaming an executable to a doc extension is a phishing trick');
  }
  if (MACRO_BEARING.has(ext) || (head[0] === 0x50 && head[1] === 0x4b && OFFICE_PK.has(ext))) {
    const names = zipNames(bytes);
    if (names.some(n => n.includes('vbaProject.bin')))
      add('warning', 'office_macro', 'Office document contains a VBA macro project', 'macros can execute arbitrary code; only enable for trusted senders');
    if (names.some(n => n.includes('externalLinks/')))
      add('warning', 'office_external_link', 'Office document references external links', 'external content can be a delivery vector');
  }
  if (ext === '.pdf' || latin1(head.subarray(0, 5)) === '%PDF-')
    for (const [re, label, detail] of PDF_PATTERNS) if (re.test(full())) add('warning', 'pdf_active_content', label, detail);
  if (['.html', '.htm', '.xhtml', '.svg', '.svgz'].includes(ext)) {
    if (/<script[^>]*>/i.test(full())) add(ext !== '.svg' ? 'info' : 'warning', 'embedded_script', `${ext} contains <script> tags`,
      "rendered in TextView's WebView; review before opening URLs");
    if (/\bjavascript:/i.test(full())) add('warning', 'javascript_uri', `${ext} contains \`javascript:\` URIs`);
  }
  if (SCRIPT_EXTS.has(ext) || (info.is_text && ['plain', ''].includes(info.detected_kind))) {
    for (const [re, label, detail] of SCRIPT_PATTERNS) {
      const m = re.exec(full());
      if (m) {
        const snip = full().slice(Math.max(0, m.index - 12), m.index + m[0].length + 12);
        const s = new TextDecoder().decode(Uint8Array.from(snip, c => c.charCodeAt(0))).replace(/\n/g, ' ');
        add('warning', 'suspicious_pattern', label, `${detail} — near \`${[...s].slice(0, 80).join('')}\``);
      }
    }
  }
  const sev = new Set(findings.map(f => f.severity));
  const risk = sev.has('dangerous') ? 'dangerous' : sev.has('warning') ? 'suspicious' : 'clean';
  return { info, risk, findings };
}
