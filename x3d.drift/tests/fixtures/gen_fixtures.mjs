// Test tracks for the simulation, in the exact kansei:track metadata format of CONTRACT.md
// section 3, so the real circuits from build/build_world.py drop in unchanged.
//   node tests/fixtures/gen_fixtures.mjs           write tests/fixtures/*.x3d
//   node tests/fixtures/gen_fixtures.mjs --check   rebuild in memory, exit 1 if any file differs
// Tracks: skidpad (60 m radius flat loop), oval (banked oval with a hill), twisty (technical
// loop with a hairpin, esses and clipping zones), strip (two 3 km straights, for top speed).
// Deterministic: plain arithmetic and fixed decimals (Math.* is fine here, this is not sim code;
// the sim reads only the printed numbers).
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const DIR = fileURLToPath(new URL('.', import.meta.url));
const f4 = v => { const s = v.toFixed(4); return s === '-0.0000' ? '0.0000' : s; };
const f5 = v => { const s = v.toFixed(5); return s === '-0.00000' ? '0.00000' : s; };
const SPACING = 2.0;

/** Turtle path: segments [kind, a, b] with kind 'S' (length) or 'A' (radius, degrees; + = left). */
function turtle(segs) {
  const pts = [];
  let x = 0, z = 0, h = 0; // heading: forward = (sin h, cos h)
  const push = () => pts.push([x, z, h]);
  for (const [kind, a, b] of segs) {
    if (kind === 'S') {
      const n = Math.max(1, Math.round(a / 0.25));
      for (let i = 0; i < n; i++) { push(); x += Math.sin(h) * a / n; z += Math.cos(h) * a / n; }
    } else {
      const R = a, ang = b * Math.PI / 180, len = R * Math.abs(ang);
      const n = Math.max(1, Math.round(len / 0.25));
      for (let i = 0; i < n; i++) {
        push();
        const dh = ang / n, hm = h + dh / 2, ds = len / n;
        x += Math.sin(hm) * ds; z += Math.cos(hm) * ds; h += dh;
      }
    }
  }
  return { pts, end: [x, z, h] };
}

/** Resample a dense closed polyline at about SPACING metres. */
function resample(pts) {
  const n = pts.length;
  const cum = [0];
  for (let i = 1; i <= n; i++) { const a = pts[i - 1], b = pts[i % n]; cum.push(cum[i - 1] + Math.hypot(b[0] - a[0], b[1] - a[1])); }
  const L = cum[n], m = Math.round(L / SPACING), out = [];
  let j = 0;
  for (let k = 0; k < m; k++) {
    const s = L * k / m;
    while (cum[j + 1] < s) j++;
    const t = (s - cum[j]) / (cum[j + 1] - cum[j]);
    const a = pts[j], b = pts[(j + 1) % n];
    out.push({ x: a[0] + (b[0] - a[0]) * t, z: a[1] + (b[1] - a[1]) * t, s });
  }
  return { samples: out, L };
}

function headingAt(S, i) {
  const n = S.length, a = S[i], b = S[(i + 1) % n];
  return Math.atan2(b.x - a.x, b.z - a.z);
}

function gridSlots(S, L) {
  // six slots behind the line, staggered left and right
  const slots = [];
  for (let k = 0; k < 6; k++) {
    const back = 9 + 7.5 * k, lat = (k % 2 === 0 ? 1 : -1) * 2.4;
    const s = L - back;
    const i = Math.floor(s / (L / S.length)) % S.length;
    const a = S[i], b = S[(i + 1) % S.length];
    const t = (s - a.s) / (L / S.length);
    const x = a.x + (b.x - a.x) * t, z = a.z + (b.z - a.z) * t;
    const h = headingAt(S, i);
    slots.push([x + Math.cos(h) * lat, z - Math.sin(h) * lat, h]);
  }
  return slots;
}

function x3dDoc(id, name, subtitle, time, S, fields, hw) {
  const n = S.length;
  const center = S.map(p => `${f4(p.x)} ${f4(p.y)} ${f4(p.z)} ${f5(p.bank)} ${f4(p.hw)} ${f4(p.wl)} ${f4(p.wr)} ${f4(p.grip)}`).join(' ');
  // a plain asphalt ribbon so the fixture also opens in an X3D browser
  // (every RIB-th sample: the picture needs far fewer points than the sim's centreline)
  const coord = [], idx = [], RIB = 4, m = Math.ceil(n / RIB);
  for (let k = 0; k < m; k++) {
    const i = Math.min(n - 1, k * RIB), p = S[i], h = headingAt(S, i), lx = Math.cos(h), lz = -Math.sin(h), tb = Math.tan(p.bank);
    coord.push(`${(p.x + lx * p.hw).toFixed(2)} ${(p.y + p.hw * tb).toFixed(2)} ${(p.z + lz * p.hw).toFixed(2)}`);
    coord.push(`${(p.x - lx * p.hw).toFixed(2)} ${(p.y - p.hw * tb).toFixed(2)} ${(p.z - lz * p.hw).toFixed(2)}`);
    const j = (k + 1) % m;
    idx.push(`${2 * k} ${2 * k + 1} ${2 * j}`, `${2 * j} ${2 * k + 1} ${2 * j + 1}`);
  }
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE X3D PUBLIC "ISO//Web3D//DTD X3D 4.0//EN" "https://www.web3d.org/specifications/x3d-4.0.dtd">
<X3D profile='Interchange' version='4.0' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.0.xsd'>
<head>
<meta name='title' content='KANSEI test fixture ${name}'/>
<meta name='description' content='Simulation test track for KANSEI (tests/fixtures/gen_fixtures.mjs). The kansei:track metadata is what the vehicle simulation reads.'/>
<meta name='generator' content='tests/fixtures/gen_fixtures.mjs'/>
</head>
<Scene>
<WorldInfo DEF='TrackInfo' title='${name}'>
<MetadataSet name='kansei:track' containerField='metadata'>
<MetadataString name='id' value='"${id}"' containerField='value'/>
<MetadataString name='name' value='"${name}"' containerField='value'/>
<MetadataString name='subtitle' value='"${subtitle}"' containerField='value'/>
<MetadataString name='time' value='"${time}"' containerField='value'/>
<MetadataInteger name='samples' value='${n}' containerField='value'/>
<MetadataDouble name='center' value='${center}' containerField='value'/>
<MetadataInteger name='checkpoints' value='${fields.checkpoints.join(' ')}' containerField='value'/>
<MetadataInteger name='sectors' value='${fields.sectors.join(' ')}' containerField='value'/>
<MetadataDouble name='grid' value='${fields.grid.map(g => `${f4(g[0])} ${f4(g[1])} ${f5(g[2])}`).join(' ')}' containerField='value'/>
<MetadataDouble name='zones' value='${fields.zones.map(z => z.join(' ')).join(' ')}' containerField='value'/>
<MetadataDouble name='props' value='${fields.props.map(p => `${p[0]} ${f4(p[1])} ${f4(p[2])} ${f4(p[3])}`).join(' ')}' containerField='value'/>
<MetadataDouble name='targets' value='${fields.targets.join(' ')}' containerField='value'/>
<MetadataString name='runoff' value='"${fields.runoff}"' containerField='value'/>
</MetadataSet>
</WorldInfo>
<NavigationInfo DEF='Nav' type='"NONE"' transitionType='"TELEPORT"'/>
<Viewpoint DEF='ChaseCam' description='Chase' position='0 3 -8'/>
<Background DEF='Sky' skyColor='0.55 0.7 0.9'/>
<DirectionalLight DEF='Sun' direction='-0.4 -1 -0.3' intensity='1'/>
<Group DEF='Cars'/>
<Group DEF='FX'/>
<Shape DEF='Road'>
<Appearance><Material diffuseColor='0.18 0.18 0.2'/></Appearance>
<IndexedTriangleSet solid='false' index='${idx.join(' ')}'><Coordinate point='${coord.join(' ')}'/></IndexedTriangleSet>
</Shape>
</Scene>
</X3D>
`;
}

function evenCheckpoints(n, k) { const out = []; for (let i = 0; i < k; i++) out.push(Math.round(i * n / k)); return out; }

/** Index of the sample nearest an arc length. */
const idxAt = (S, L, s) => Math.round(((s % L) + L) % L / (L / S.length)) % S.length;

/** Prop placed at arc length s and lateral offset lat (+ left). */
function propAt(S, L, kind, s, lat, r) {
  const i = idxAt(S, L, s), p = S[i], h = headingAt(S, i);
  return [kind, p.x + Math.cos(h) * lat, p.z - Math.sin(h) * lat, r];
}

// ------------------------------------------------------------------------------------------------
const TRACKS = {};

TRACKS.skidpad = () => {
  const R = 60;
  const { pts } = turtle([['A', R, 360]]);
  const { samples: S, L } = resample(pts);
  for (const p of S) Object.assign(p, { y: 0, bank: 0, hw: 12, wl: 26, wr: 26, grip: 1 });
  const n = S.length;
  return { id: 'fx-skidpad', name: 'Fixture Skidpad', subtitle: '60 m radius, flat', time: 'noon', S,
    checkpoints: evenCheckpoints(n, 12), sectors: [4, 8], grid: gridSlots(S, L),
    zones: [[idxAt(S, L, 0.25 * L), idxAt(S, L, 0.45 * L), -1, 2]],
    props: [propAt(S, L, 1, 0.6 * L, -13.5, 0.22), propAt(S, L, 1, 0.62 * L, -13.5, 0.22), propAt(S, L, 2, 0.8 * L, 20, 0.15)],
    targets: [30.0, 32.0, 34.0, 20000, 40000, 60000, 80000], runoff: 'tarmac' };
};

TRACKS.oval = () => {
  const R = 90, straight = 420;
  const { pts } = turtle([['S', straight / 2], ['A', R, 180], ['S', straight], ['A', R, 180], ['S', straight / 2]]);
  const { samples: S, L } = resample(pts);
  const turn1 = [straight / 2, straight / 2 + Math.PI * R], turn2 = [1.5 * straight + Math.PI * R, 1.5 * straight + 2 * Math.PI * R];
  const backA = turn1[1], backB = turn2[0];
  const ramp = (s, a, b, w) => Math.min(1, Math.max(0, Math.min((s - a + w) / (2 * w), (b + w - s) / (2 * w))));
  for (const p of S) {
    const bk = Math.max(ramp(p.s, turn1[0], turn1[1], 35), ramp(p.s, turn2[0], turn2[1], 35));
    // hill: a 12 m crest over 360 m in the middle of the back straight
    const mid = 0.5 * (backA + backB), hs = 360;
    const t = (p.s - (mid - hs / 2)) / hs;
    const y = t > 0 && t < 1 ? 12 * 0.5 * (1 - Math.cos(2 * Math.PI * t)) : 0;
    Object.assign(p, { y, bank: -0.12 * bk, hw: 8, wl: 12.5, wr: 12.5, grip: 1 });
  }
  const n = S.length;
  return { id: 'fx-oval', name: 'Fixture Oval', subtitle: 'Banked oval with a hill', time: 'golden', S,
    checkpoints: evenCheckpoints(n, 14), sectors: [5, 10], grid: gridSlots(S, L),
    zones: [[idxAt(S, L, turn1[0] + 40), idxAt(S, L, turn1[1] - 40), -1, 2], [idxAt(S, L, turn2[0] + 40), idxAt(S, L, turn2[1] - 40), -1, 2]],
    props: [propAt(S, L, 1, turn1[0] + 0.5 * Math.PI * R, 9.6, 0.22), propAt(S, L, 3, backA + 30, -11, 0.32)],
    targets: [40.0, 43.0, 46.0, 20000, 40000, 60000, 80000], runoff: 'grass' };
};

/** Closed centripetal Catmull-Rom spline through control points, densely sampled. */
function spline(P, per = 200) {
  const d = (a, b) => Math.sqrt(Math.hypot(b[0] - a[0], b[1] - a[1])) || 1e-6;
  const n = P.length, pts = [];
  for (let i = 0; i < n; i++) {
    const p0 = P[(i - 1 + n) % n], p1 = P[i], p2 = P[(i + 1) % n], p3 = P[(i + 2) % n];
    const t1 = d(p0, p1), t2 = t1 + d(p1, p2), t3 = t2 + d(p2, p3);
    for (let k = 0; k < per; k++) {
      const tt = t1 + (t2 - t1) * k / per;
      const L = (a, b, ta, tb) => [((tb - tt) * a[0] + (tt - ta) * b[0]) / (tb - ta), ((tb - tt) * a[1] + (tt - ta) * b[1]) / (tb - ta)];
      const A1 = L(p0, p1, 0, t1), A2 = L(p1, p2, t1, t2), A3 = L(p2, p3, t2, t3);
      const B1 = L(A1, A2, 0, t2), B2 = L(A2, A3, t1, t3);
      pts.push(L(B1, B2, t1, t2));
    }
  }
  return pts;
}

/** Corners of a resampled loop: runs of smoothed curvature above 1/70 m, biggest turning first. */
function corners(S) {
  const n = S.length, k = new Array(n).fill(0), ks = new Array(n).fill(0);
  for (let i = 0; i < n; i++) {
    const h1 = headingAt(S, (i - 1 + n) % n), h2 = headingAt(S, i);
    let dd = h2 - h1; while (dd > Math.PI) dd -= 2 * Math.PI; while (dd < -Math.PI) dd += 2 * Math.PI;
    k[i] = dd / SPACING;
  }
  for (let i = 0; i < n; i++) { let a = 0; for (let j = -4; j <= 4; j++) a += k[(i + j + n) % n]; ks[i] = a / 9; }
  const out = [];
  let i = 0;
  while (i < n && Math.abs(ks[i]) > 1 / 70) i++;
  for (let c = 0; c < n; c++) {
    const idx = (i + c) % n;
    if (Math.abs(ks[idx]) > 1 / 70) {
      const sign = Math.sign(ks[idx]); let j = c, turn = 0, peak = 0, at = idx;
      while (j < n && Math.abs(ks[(i + j) % n]) > 1 / 70 && Math.sign(ks[(i + j) % n]) === sign) { const q = ks[(i + j) % n]; turn += q * SPACING; if (Math.abs(q) > peak) { peak = Math.abs(q); at = (i + j) % n; } j++; }
      out.push({ i0: idx, i1: (i + j - 1) % n, sign, turn: Math.abs(turn), radius: 1 / peak, apex: at });
      c = j;
    }
  }
  return out.sort((a, b) => b.turn - a.turn);
}

TRACKS.twisty = () => {
  // A technical loop: long start straight, fast sweeper, hairpin, esses, a long right, back straight.
  const ctrl = [[0, -120], [0, 120], [30, 190], [100, 215], [180, 205], [228, 180], [240, 135], [205, 106], [165, 92],
    [140, 56], [150, 12], [128, -34], [142, -84], [205, -104], [285, -112], [335, -142], [345, -200], [302, -242],
    [200, -246], [80, -232], [22, -200]];
  const { samples: S, L } = resample(spline(ctrl));
  for (const p of S) Object.assign(p, { y: 3 * Math.sin(2 * Math.PI * p.s / L) + 1.2 * Math.sin(6 * Math.PI * p.s / L), bank: 0, hw: 6.5, wl: 10, wr: 10, grip: 1 });
  const n = S.length;
  const cs = corners(S);
  const zones = [], props = [];
  const span = (c, a, b) => { const len = (c.i1 - c.i0 + n) % n; return [(c.i0 + Math.round(a * len)) % n, (c.i0 + Math.round(b * len)) % n]; };
  // the two biggest sweepers get outer clips, the tightest corner an inner clip with cones at its apex
  for (const c of cs.slice(0, 2)) { const [a, b] = span(c, 0.2, 0.8); zones.push([a, b, -c.sign, 2]); }
  const tight = cs.slice().sort((a, b) => a.radius - b.radius)[0];
  { const [a, b] = span(tight, 0.25, 0.75); zones.push([a, b, tight.sign, 1]); }
  const apexS = S[tight.apex].s;
  props.push(propAt(S, L, 1, apexS - 3, tight.sign * 7.5, 0.22), propAt(S, L, 1, apexS + 3, tight.sign * 7.5, 0.22));
  props.push(propAt(S, L, 2, S[cs[0].apex].s, -cs[0].sign * 9.0, 0.15));
  props.push(propAt(S, L, 3, S[cs[1].apex].s + 25, cs[1].sign * 8.8, 0.32));
  return { id: 'fx-twisty', name: 'Fixture Twisty', subtitle: 'Hairpin, esses and clipping zones', time: 'sunset', S,
    checkpoints: evenCheckpoints(n, 16), sectors: [5, 11], grid: gridSlots(S, L), zones, props,
    targets: [60.0, 64.0, 68.0, 20000, 40000, 60000, 80000], runoff: 'sand' };
};

TRACKS.strip = () => {
  const R = 250, straight = 3000;
  const { pts } = turtle([['S', straight / 2], ['A', R, 180], ['S', straight], ['A', R, 180], ['S', straight / 2]]);
  const { samples: S, L } = resample(pts);
  for (const p of S) Object.assign(p, { y: 0, bank: 0, hw: 10, wl: 20, wr: 20, grip: 1 });
  const n = S.length;
  return { id: 'fx-strip', name: 'Fixture Strip', subtitle: 'Two 3 km straights', time: 'noon', S,
    checkpoints: evenCheckpoints(n, 12), sectors: [4, 8], grid: gridSlots(S, L), zones: [], props: [],
    targets: [200.0, 210.0, 220.0, 20000, 40000, 60000, 80000], runoff: 'grass' };
};

// targets measured by tools/bot.mjs on these fixtures (see tests/fixtures/targets.json)
const TFILE = DIR + 'targets.json';
const measured = existsSync(TFILE) ? JSON.parse(readFileSync(TFILE, 'utf8')) : {};

const check = process.argv.includes('--check');
let same = true;
for (const key of Object.keys(TRACKS)) {
  const t = TRACKS[key]();
  if (measured[key]) t.targets = measured[key];
  const text = x3dDoc(t.id, t.name, t.subtitle, t.time, t.S, t, 0);
  const path = DIR + key + '.x3d';
  if (check) { const old = existsSync(path) ? readFileSync(path, 'utf8') : ''; if (old !== text) { same = false; console.log('differs', key); } }
  else { writeFileSync(path, text); console.log('wrote', key + '.x3d', t.S.length, 'samples', (text.length / 1024).toFixed(0) + ' KB'); }
}
if (check) { console.log(JSON.stringify({ fixtures_identical: same })); process.exit(same ? 0 : 1); }
