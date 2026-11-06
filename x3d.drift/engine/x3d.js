// loom:sim
// Reads a KANSEI track straight from its X3D file: the bytes the browser draws are the bytes the
// simulation drives on. No DOM is needed, so Node runs the identical loader for tapes and tests.
// Only the WorldInfo MetadataSet name='kansei:track' is read (CONTRACT.md section 3); the meshes
// are picture only. Adapted from NIB's engine/x3d.js (same minimal XML reader).

const ENT = { '&quot;': '"', '&apos;': "'", '&lt;': '<', '&gt;': '>', '&amp;': '&' };
const decode = s => s.replace(/&(quot|apos|lt|gt|amp);/g, m => ENT[m]);
const WS = c => c === ' ' || c === '\n' || c === '\t' || c === '\r';

/** Minimal XML reader for X3D's XML encoding: elements, attributes, comments, CDATA, PI, DOCTYPE. */
export function parseXML(text) {
  const root = { name: '#root', attrs: {}, children: [] };
  const stack = [root];
  let i = 0;
  const n = text.length;
  while (i < n) {
    const lt = text.indexOf('<', i);
    if (lt < 0) break;
    if (text.startsWith('<!--', lt)) { const e = text.indexOf('-->', lt + 4); if (e < 0) throw new Error('XML: unclosed comment'); i = e + 3; continue; }
    if (text.startsWith('<![CDATA[', lt)) { const e = text.indexOf(']]>', lt + 9); if (e < 0) throw new Error('XML: unclosed CDATA'); i = e + 3; continue; }
    if (text.startsWith('<?', lt)) { const e = text.indexOf('?>', lt + 2); i = e + 2; continue; }
    if (text.startsWith('<!', lt)) { const e = text.indexOf('>', lt + 2); i = e + 1; continue; }
    if (text[lt + 1] === '/') {
      const e = text.indexOf('>', lt);
      const name = text.slice(lt + 2, e).trim();
      const top = stack.pop();
      if (!top || top.name !== name) throw new Error(`XML: </${name}> closes <${top && top.name}>`);
      i = e + 1; continue;
    }
    let j = lt + 1;
    while (j < n && !WS(text[j]) && text[j] !== '/' && text[j] !== '>') j++;
    const el = { name: text.slice(lt + 1, j), attrs: {}, children: [] };
    for (;;) {
      while (j < n && WS(text[j])) j++;
      if (j >= n) throw new Error('XML: unterminated tag ' + el.name);
      if (text[j] === '/' && text[j + 1] === '>') { j += 2; stack[stack.length - 1].children.push(el); break; }
      if (text[j] === '>') { j += 1; stack[stack.length - 1].children.push(el); stack.push(el); break; }
      let k = j;
      while (k < n && !WS(text[k]) && text[k] !== '=') k++;
      const an = text.slice(j, k);
      while (k < n && text[k] !== '=') k++;
      k++;
      while (k < n && WS(text[k])) k++;
      const q = text[k];
      const end = text.indexOf(q, k + 1);
      if (end < 0) throw new Error('XML: unterminated attribute ' + an);
      el.attrs[an] = decode(text.slice(k + 1, end));
      j = end + 1;
    }
    i = j;
  }
  if (stack.length !== 1) throw new Error('XML: unclosed element ' + stack[stack.length - 1].name);
  return root;
}

export const nums = s => {
  const t = (s || '').trim();
  if (t === '') return [];
  const parts = t.split(/[\s,]+/);
  const out = new Array(parts.length);
  for (let i = 0; i < parts.length; i++) out[i] = Number(parts[i]);
  return out;
};
export const strs = s => { const out = []; const re = /"((?:[^"\\]|\\.)*)"/g; let m; while ((m = re.exec(s || ''))) out.push(m[1].replace(/\\(.)/g, '$1')); return out; };

/** Read a MetadataSet's children into a plain object. Numeric fields are always arrays here. */
export function readMeta(set) {
  const o = {};
  for (const m of set.children) {
    const key = m.attrs.name;
    if (!key) continue;
    if (m.name === 'MetadataString') o[key] = strs(m.attrs.value);
    else if (m.name === 'MetadataDouble' || m.name === 'MetadataFloat' || m.name === 'MetadataInteger') o[key] = nums(m.attrs.value);
    else if (m.name === 'MetadataBoolean') o[key] = (m.attrs.value || '').trim().split(/\s+/).map(x => x === 'true');
    else if (m.name === 'MetadataSet') o[key] = readMeta(m);
  }
  return o;
}

/** Find the slice of text holding the <MetadataSet name='setName'> element (with nesting). */
function sliceSet(text, setName) {
  const re = /<MetadataSet\b[^>]*\bname\s*=\s*(['"])([^'"]*)\1[^>]*>/g;
  let m;
  while ((m = re.exec(text))) {
    if (m[2] !== setName) continue;
    const start = m.index;
    if (m[0].endsWith('/>')) return text.slice(start, re.lastIndex);
    let depth = 1, k = re.lastIndex;
    const open = /<MetadataSet\b[^>]*?(\/?)>|<\/MetadataSet\s*>/g;
    open.lastIndex = k;
    let t;
    while ((t = open.exec(text))) {
      if (t[0].startsWith('</')) { depth--; if (depth === 0) return text.slice(start, open.lastIndex); }
      else if (t[1] !== '/') depth++;
    }
    throw new Error('XML: unclosed MetadataSet ' + setName);
  }
  return null;
}

/**
 * Read the kansei:track metadata of a track file. Returns { title, meta } where meta maps each
 * field name to an array (strings for MetadataString, numbers otherwise).
 */
export function readTrackMeta(text) {
  const part = sliceSet(text, 'kansei:track');
  if (!part) throw new Error("track: no MetadataSet name='kansei:track' in the file");
  const doc = parseXML(part);
  const set = doc.children[0];
  const meta = readMeta(set);
  let title = '';
  const wi = /<WorldInfo\b[^>]*>/.exec(text);
  if (wi) { const tm = /\btitle\s*=\s*(['"])(.*?)\1/.exec(wi[0]); if (tm) title = decode(tm[2]); }
  return { title, meta };
}
