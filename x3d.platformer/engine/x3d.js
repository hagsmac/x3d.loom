// loom:sim
// Reads a level straight from its X3D file: the same bytes the browser draws are the bytes the
// simulation plays. No DOM is needed, so Node runs the identical loader for tapes and tests.
//
// What the game reads (everything else in the file is picture only):
//   WorldInfo > MetadataSet 'nib:level'          level parameters
//   RigidBodyCollection > RigidBody (bodies)      every collider, with MetadataSet 'nib:body'
//   RigidBodyCollection > SingleAxisHingeJoint / BallJoint: revolute joints (body1, body2 by USE)
//   Transform with MetadataSet 'nib:entity'       cogs, stars, springs, spikes, rings, ...
//   PositionInterpolator (by DEF)                 paths of moving platforms

const ENT = { '&quot;': '"', '&apos;': "'", '&lt;': '<', '&gt;': '>', '&amp;': '&' };
const decode = s => s.replace(/&(quot|apos|lt|gt|amp);/g, m => ENT[m]);

/** Minimal XML reader for X3D's XML encoding: elements, attributes, comments, PI, DOCTYPE. */
export function parseXML(text) {
  const root = { name: '#root', attrs: {}, children: [] };
  const stack = [root];
  let i = 0;
  const n = text.length;
  while (i < n) {
    const lt = text.indexOf('<', i);
    if (lt < 0) break;
    if (text.startsWith('<!--', lt)) { const e = text.indexOf('-->', lt + 4); if (e < 0) throw new Error('XML: unclosed comment'); i = e + 3; continue; }
    if (text.startsWith('<?', lt)) { const e = text.indexOf('?>', lt + 2); i = e + 2; continue; }
    if (text.startsWith('<!', lt)) { const e = text.indexOf('>', lt + 2); i = e + 1; continue; }
    if (text[lt + 1] === '/') {
      const e = text.indexOf('>', lt);
      const name = text.slice(lt + 2, e).trim();
      const top = stack.pop();
      if (!top || top.name !== name) throw new Error(`XML: </${name}> closes <${top && top.name}>`);
      i = e + 1; continue;
    }
    // start tag: read name and attributes up to the unquoted '>'
    let j = lt + 1;
    while (j < n && !/[\s/>]/.test(text[j])) j++;
    const el = { name: text.slice(lt + 1, j), attrs: {}, children: [] };
    for (;;) {
      while (j < n && /\s/.test(text[j])) j++;
      if (text[j] === '/' && text[j + 1] === '>') { j += 2; stack[stack.length - 1].children.push(el); break; }
      if (text[j] === '>') { j += 1; stack[stack.length - 1].children.push(el); stack.push(el); break; }
      let k = j;
      while (k < n && !/[\s=]/.test(text[k])) k++;
      const an = text.slice(j, k);
      while (text[k] !== '=') k++;
      k++;
      while (/\s/.test(text[k])) k++;
      const q = text[k];
      const end = text.indexOf(q, k + 1);
      el.attrs[an] = decode(text.slice(k + 1, end));
      j = end + 1;
    }
    i = j;
  }
  if (stack.length !== 1) throw new Error('XML: unclosed element ' + stack[stack.length - 1].name);
  return root;
}

export const nums = s => (s || '').trim() === '' ? [] : s.trim().split(/[\s,]+/).map(Number);
export const strs = s => { const out = []; const re = /"((?:[^"\\]|\\.)*)"/g; let m; while ((m = re.exec(s || ''))) out.push(m[1].replace(/\\(.)/g, '$1')); return out; };

function walk(el, fn, parent = null) { fn(el, parent); for (const c of el.children) walk(c, fn, el); }

/** Read a MetadataSet's children into a plain object (numbers stay arrays only when long). */
export function readMeta(set) {
  const o = {};
  for (const m of set.children) {
    const key = m.attrs.name;
    if (!key) continue;
    if (m.name === 'MetadataString') { const v = strs(m.attrs.value); o[key] = v.length === 1 ? v[0] : v; }
    else if (m.name === 'MetadataDouble' || m.name === 'MetadataFloat' || m.name === 'MetadataInteger') {
      const v = nums(m.attrs.value); o[key] = v.length === 1 ? v[0] : v;
    } else if (m.name === 'MetadataBoolean') { const v = (m.attrs.value || '').trim().split(/\s+/).map(x => x === 'true'); o[key] = v.length === 1 ? v[0] : v; }
    else if (m.name === 'MetadataSet') o[key] = readMeta(m);
  }
  return o;
}

function metaOf(el, setName) {
  const m = el.children.find(c => c.name === 'MetadataSet' && c.attrs.name === setName);
  return m ? readMeta(m) : null;
}

function angleZ(orient) {
  const r = nums(orient);
  if (r.length < 4 || r[3] === 0) return 0;
  // only rotations about the Z axis are meaningful in the play plane
  return r[2] < 0 ? -r[3] : r[3];
}

/** Turn an X3D level file into a plain level description the game can build. */
export function readLevel(text) {
  const doc = parseXML(text);
  const defs = new Map();
  walk(doc, el => { if (el.attrs.DEF) defs.set(el.attrs.DEF, el); });
  const level = { params: {}, bodies: [], joints: [], entities: [], paths: {}, gravity: -38, iterations: 10 };
  walk(doc, (el, parent) => {
    if (el.name === 'WorldInfo') { const m = metaOf(el, 'nib:level'); if (m) level.params = m; level.title = el.attrs.title || ''; }
    else if (el.name === 'RigidBodyCollection') {
      const g = nums(el.attrs.gravity || '0 -9.8 0'); level.gravity = g[1];
      level.iterations = Number(el.attrs.iterations || 10);
    } else if (el.name === 'RigidBody' && !el.attrs.USE) {
      const meta = metaOf(el, 'nib:body') || {};
      const cs = el.children.find(c => c.name === 'CollidableShape');
      const shape = cs && cs.children.find(c => c.name === 'Shape');
      const geom = shape && shape.children.find(c => c.name === 'Box' || c.name === 'Sphere');
      if (!geom) throw new Error(`RigidBody ${el.attrs.DEF} has no Box or Sphere collidable`);
      const p = nums(el.attrs.position || '0 0 0');
      const lv = nums(el.attrs.linearVelocity || '0 0 0'), av = nums(el.attrs.angularVelocity || '0 0 0');
      const b = { def: el.attrs.DEF, x: p[0], y: p[1], a: angleZ(el.attrs.orientation),
        fixed: el.attrs.fixed === 'true', mass: Number(el.attrs.mass || 1), vx: lv[0], vy: lv[1], w: av[2], meta };
      if (geom.name === 'Box') { const s = nums(geom.attrs.size || '2 2 2'); b.shape = 'box'; b.hx = s[0] / 2; b.hy = s[1] / 2; }
      else { b.shape = 'circle'; b.r = Number(geom.attrs.radius || 1); }
      level.bodies.push(b);
    } else if ((el.name === 'SingleAxisHingeJoint' || el.name === 'BallJoint') && !el.attrs.USE) {
      const ref = f => { const c = el.children.find(x => x.attrs.containerField === f); return c && (c.attrs.USE || c.attrs.DEF); };
      const a = nums(el.attrs.anchorPoint || '0 0 0');
      level.joints.push({ type: 'revolute', body1: ref('body1'), body2: ref('body2'), x: a[0], y: a[1], meta: metaOf(el, 'nib:joint') || {} });
    } else if (el.name === 'Transform') {
      const m = metaOf(el, 'nib:entity');
      if (m) { const t = nums(el.attrs.translation || '0 0 0'); level.entities.push({ def: el.attrs.DEF, x: t[0], y: t[1], ...m }); }
    } else if (el.name === 'PositionInterpolator' && el.attrs.DEF) {
      const k = nums(el.attrs.key), v = nums(el.attrs.keyValue);
      const pts = []; for (let i = 0; i < k.length; i++) pts.push([v[3 * i], v[3 * i + 1]]);
      level.paths[el.attrs.DEF] = { key: k, pts };
    }
  });
  return level;
}
