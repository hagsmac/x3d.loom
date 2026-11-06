// The shipped circuits against the track contract (CONTRACT.md section 3), read exactly as the sim
// reads them (engine/sim.js parseTrack on the level bytes), plus the geometry the sim relies on:
//   node tests/levels.test.mjs           (about 2 s)
// Per level in levels/MANIFEST.json: manifest sha256, sample count and medal targets match the file; samples about
// 2 m apart on a closed loop with no kinks; half widths and walls sane; at least 12 checkpoints in
// order; sectors inside the checkpoint list; a 6-slot grid behind the line on the asphalt, facing
// along the road with room between cars; zones and props well formed and inside the walls; the
// targets ordered; and the wall corridor never overlapping another part of the lap (the sim's
// nearest-centreline query must be unambiguous everywhere a car can be).
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseTrack } from '../engine/sim.js';
import { project, surfaceAt, wrapI } from '../engine/track.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const man = JSON.parse(readFileSync(ROOT + 'levels/MANIFEST.json', 'utf8'));
let fails = 0, count = 0;
function check(name, ok, detail = '') { count++; if (!ok) fails++; console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? '  (' + detail + ')' : ''}`); }
const wrapPi = a => { while (a > Math.PI) a -= 2 * Math.PI; while (a <= -Math.PI) a += 2 * Math.PI; return a; };

for (const lv of man.levels) {
  const text = readFileSync(ROOT + 'levels/' + lv.file, 'utf8');
  const sha = createHash('sha256').update(text).digest('hex');
  const T = parseTrack(text), n = T.n, id = lv.id;
  check(`${id}: manifest sha256, bytes and samples match the file`, sha === lv.sha256 && Buffer.byteLength(text) === lv.bytes && n === lv.samples && T.id === id,
    `n ${n}, L ${T.L.toFixed(1)} m`);
  const mt = lv.targets || {};
  check(`${id}: manifest medal targets (what the page shows before loading) equal the level's metadata`,
    Object.keys(T.targets).every(k => mt[k] === T.targets[k]), JSON.stringify(mt));
  // spacing, closure, kinks
  let lo = 1e9, hi = 0, kink = 0, kinkAt = -1;
  for (let i = 0; i < n; i++) {
    lo = Math.min(lo, T.len[i]); hi = Math.max(hi, T.len[i]);
    const d = Math.abs(wrapPi(T.heading[i] - T.heading[(i - 1 + n) % n]));
    if (d > kink) { kink = d; kinkAt = i; }
  }
  check(`${id}: samples 1.5-2.5 m apart on a closed loop (closing segment included)`, lo >= 1.5 && hi <= 2.5 && T.len[n - 1] >= 1.5 && T.len[n - 1] <= 2.5,
    `min ${lo.toFixed(3)} max ${hi.toFixed(3)} closing ${T.len[n - 1].toFixed(3)}`);
  check(`${id}: no kink sharper than 8 deg between neighbouring segments`, kink < 8 * Math.PI / 180, `max ${(kink * 180 / Math.PI).toFixed(2)} deg at ${kinkAt}`);
  // the manifest length is along the road in 3D (climbs included); the sim measures the plan length
  let L3 = 0, rMin = 1e9, rAt = -1, foldBad = 0;
  for (let i = 0; i < n; i++) { const dy = T.y[(i + 1) % n] - T.y[i]; L3 += Math.sqrt(T.len[i] * T.len[i] + dy * dy); }
  check(`${id}: track length matches the manifest (3D length along the road)`, Math.abs(L3 - lv.length) < 0.5, `3D ${L3.toFixed(2)} vs ${lv.length}; plan ${T.L.toFixed(2)}`);
  // the inside wall line must not fold over itself: radius of curvature beyond the inside wall
  for (let i = 0; i < n; i++) {
    const k = T.kappaS[i], ak = Math.abs(k);
    if (ak < 1e-6) continue;
    const r = 1 / ak, inside = k > 0 ? T.wl[i] : T.wr[i];
    if (r < rMin) { rMin = r; rAt = i; }
    if (r < inside + 1.5) foldBad++;
  }
  check(`${id}: every corner radius clears its inside wall by 1.5 m (no folded wall lines)`, foldBad === 0, `tightest radius ${rMin.toFixed(1)} m at sample ${rAt}`);
  // widths, walls, grip, banks, grades
  let hwLo = 1e9, hwHi = 0, wallBad = 0, gripBad = 0, bankHi = 0, gradeHi = 0, wallHi = 0;
  for (let i = 0; i < n; i++) {
    hwLo = Math.min(hwLo, T.hw[i]); hwHi = Math.max(hwHi, T.hw[i]);
    if (T.wl[i] < T.hw[i] + 1 || T.wr[i] < T.hw[i] + 1) wallBad++;
    wallHi = Math.max(wallHi, T.wl[i], T.wr[i]);
    if (!(T.grip[i] >= 0.5 && T.grip[i] <= 1.2)) gripBad++;
    bankHi = Math.max(bankHi, Math.abs(T.bank[i])); gradeHi = Math.max(gradeHi, Math.abs(T.grade[i]));
  }
  check(`${id}: half width 4-16 m, walls at least halfWidth + 1, grip 0.5-1.2`, hwLo >= 4 && hwHi <= 16 && !wallBad && !gripBad,
    `hw ${hwLo.toFixed(2)}-${hwHi.toFixed(2)}, max wall ${wallHi.toFixed(2)}, bad walls ${wallBad}, bad grip ${gripBad}`);
  check(`${id}: bank under 0.3 rad and grade under 15%`, bankHi < 0.3 && gradeHi < 0.15, `bank ${bankHi.toFixed(3)} rad, grade ${(100 * gradeHi).toFixed(1)}%`);
  // the corridor out to the walls must not reach another part of the lap: sample points across the
  // corridor (centre to each wall face) must project back to their own neighbourhood
  const Q = {};
  let amb = 0, ambAt = -1, ambGap = 0;
  for (let i = 0; i < n; i += 1) {
    const nx = T.tz[i], nz = -T.tx[i];    // left normal
    for (const f of [-1, -0.75, -0.5, 0.5, 0.75, 1]) {
      const w = f > 0 ? T.wl[i] * f : T.wr[i] * f;
      const x = T.x[i] + nx * w, z = T.z[i] + nz * w;
      project(T, x, z, -1, Q);
      let d = Q.seg - i; d = ((d % n) + n) % n; if (d > n / 2) d -= n;
      if (Math.abs(d) > 12) { amb++; if (ambAt < 0) { ambAt = i; ambGap = d; } }
    }
  }
  check(`${id}: wall corridor never overlaps another part of the lap`, amb === 0, amb ? `${amb} points, first at sample ${ambAt} (projects ${ambGap} samples away)` : 'global nearest-point query is unambiguous inside the walls');
  // checkpoints and sectors
  const K = T.checkpoints.length;
  let cpOk = true, gapLo = 1e9, gapHi = 0;
  for (let k = 0; k < K; k++) {
    const a = T.cpS[k], b = T.cpS[(k + 1) % K];
    let g = b - a; if (g <= 0) g += T.L;
    gapLo = Math.min(gapLo, g); gapHi = Math.max(gapHi, g);
    if (T.checkpoints[k] < 0 || T.checkpoints[k] >= n) cpOk = false;
  }
  check(`${id}: at least 12 checkpoints, in order, spread along the lap`, K >= 12 && cpOk && gapLo > 0.03 * T.L && gapHi < 0.2 * T.L,
    `${K} checkpoints, gaps ${gapLo.toFixed(0)}-${gapHi.toFixed(0)} m`);
  check(`${id}: sectors are checkpoint ordinals 0 < a < b < K`, T.sectors[0] > 0 && T.sectors[0] < T.sectors[1] && T.sectors[1] < K, `${T.sectors.join(', ')} of ${K}`);
  // grid: 6 slots behind the line, on the asphalt, facing along the road, room between them
  const i0 = T.checkpoints[0], S = {};
  let gridBad = [], minSep = 1e9;
  for (let g = 0; g < T.grid.length; g++) {
    const G = T.grid[g];
    project(T, G.x, G.z, -1, Q);
    surfaceAt(T, Q.seg, Q.u, Q.lat, S);
    let behind = T.s[i0] - Q.s; behind -= T.L * Math.floor(behind / T.L);
    const yawErr = Math.abs(wrapPi(G.yaw - T.heading[Q.seg]));
    if (!(behind > 2 && behind < 60)) gridBad.push(`slot ${g} ${behind.toFixed(1)} m behind`);
    if (Math.abs(Q.lat) > T.hw[Q.seg] - 1.2) gridBad.push(`slot ${g} lat ${Q.lat.toFixed(2)}`);
    if (yawErr > 0.1) gridBad.push(`slot ${g} yaw off ${yawErr.toFixed(3)}`);
    for (let h = 0; h < g; h++) { const H = T.grid[h]; minSep = Math.min(minSep, Math.hypot(G.x - H.x, G.z - H.z)); }
  }
  check(`${id}: 6 grid slots behind the line on the asphalt, facing along the road, at least 5 m apart`, T.grid.length === 6 && !gridBad.length && minSep >= 5,
    gridBad.length ? gridBad.join('; ') : `min separation ${minSep.toFixed(2)} m`);
  // zones
  let zBad = 0;
  for (const z of T.zones) {
    let w = z.s1 - z.s0; if (w <= 0) w += T.L;
    if (!(z.i0 >= 0 && z.i0 < n && z.i1 >= 0 && z.i1 < n) || (z.side !== 1 && z.side !== -1) || (z.kind !== 1 && z.kind !== 2) || w < 8 || w > 0.3 * T.L) zBad++;
  }
  check(`${id}: clipping zones well formed (indices, side +-1, kind 1|2, 8 m to 30% of the lap)`, zBad === 0 && T.zones.length === lv.zones, `${T.zones.length} zones`);
  // props: inside the walls, clear of the grid, cones out of the asphalt middle where cars race
  let pBad = [], onLine = 0;
  for (const p of T.props) {
    project(T, p.x, p.z, -1, Q);
    const j = (Q.seg + 1) % n;
    const wl = T.wl[Q.seg] + (T.wl[j] - T.wl[Q.seg]) * Q.u, wr = T.wr[Q.seg] + (T.wr[j] - T.wr[Q.seg]) * Q.u;
    if (!(p.kind >= 1 && p.kind <= 3) || !(p.r > 0.05 && p.r < 1.5)) pBad.push('kind/r');
    if (Q.lat > wl - p.r || Q.lat < -wr + p.r) pBad.push(`prop outside walls at s ${Q.s.toFixed(0)}`);
    for (const G of T.grid) if (Math.hypot(G.x - p.x, G.z - p.z) < 4) pBad.push('prop on the grid');
    if (Math.abs(Q.lat) < T.hw[Q.seg] - 3) onLine++;
  }
  check(`${id}: props well formed, inside the walls and off the grid`, pBad.length === 0 && T.props.length === lv.props, pBad.length ? pBad.slice(0, 3).join('; ') : `${T.props.length} props, ${onLine} more than 3 m inside the asphalt edge`);
  // targets
  const t = T.targets;
  check(`${id}: targets ordered (gold < silver < bronze lap; bronze < silver < gold < platinum score)`,
    t.goldLap > 0 && t.goldLap < t.silverLap && t.silverLap < t.bronzeLap && t.rushBronze > 0 && t.rushBronze < t.rushSilver && t.rushSilver < t.rushGold && t.rushGold < t.rushPlatinum,
    [t.goldLap, t.silverLap, t.bronzeLap, t.rushBronze, t.rushSilver, t.rushGold, t.rushPlatinum].join(' '));
  check(`${id}: runoff is one of grass | sand | gravel | tarmac and matches the manifest`, ['grass', 'sand', 'gravel', 'tarmac'].includes(T.runoff) && T.runoff === lv.runoff, T.runoff);
}
console.log(JSON.stringify({ levels: fails ? 'fail' : 'pass', checks: count, failed: fails }));
process.exit(fails ? 1 : 0);
