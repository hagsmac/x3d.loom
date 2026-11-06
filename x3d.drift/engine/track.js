// loom:sim
// The track as the simulation sees it: a closed centreline of samples (position, bank, widths,
// walls, grip) read from the kansei:track metadata (CONTRACT.md section 3), plus fast queries:
// nearest point on the centreline, lateral offset, surface height and normal, surface grip.
import { readTrackMeta } from './x3d.js';
import { dsin, dcos, datan2, wrapPi } from './fmath.js';

export const CURB_BAND = 1.2;          // painted curb band beyond the asphalt edge (m)
export const CURB_GRIP = 0.92;
export const SURF = { ASPHALT: 0, CURB: 1, RUNOFF: 2 };
export const RUNOFF = {
  grass: { grip: 0.55, drag: 0.6, roll: 0.05 },
  sand: { grip: 0.45, drag: 2.2, roll: 0.16 },
  gravel: { grip: 0.50, drag: 1.6, roll: 0.12 },
  tarmac: { grip: 0.85, drag: 0.0, roll: 0.0 },
};

const one = (m, k, d) => (m[k] && m[k].length ? m[k][0] : d);

/** Parse a track file's text into the sim's track object. */
export function trackFromX3D(text) {
  const { title, meta } = readTrackMeta(text);
  return buildTrack(meta, title);
}

export function buildTrack(meta, title = '') {
  const c = meta.center;
  if (!c || c.length < 8 * 8 || c.length % 8 !== 0) throw new Error('track: center must hold 8 numbers per sample');
  const n = c.length / 8;
  const declared = one(meta, 'samples', n);
  if (declared !== n) throw new Error(`track: samples=${declared} but center holds ${n}`);
  const T = {
    id: one(meta, 'id', 'track'), name: one(meta, 'name', title || 'Track'), subtitle: one(meta, 'subtitle', ''),
    time: one(meta, 'time', 'noon'), title, runoff: one(meta, 'runoff', 'grass'), n,
    x: new Float64Array(n), y: new Float64Array(n), z: new Float64Array(n), bank: new Float64Array(n),
    tb: new Float64Array(n), hw: new Float64Array(n), wl: new Float64Array(n), wr: new Float64Array(n),
    grip: new Float64Array(n),
    tx: new Float64Array(n), tz: new Float64Array(n), len: new Float64Array(n), s: new Float64Array(n + 1),
    grade: new Float64Array(n), heading: new Float64Array(n), kappa: new Float64Array(n), kappaS: new Float64Array(n),
    L: 0, maxWall: 0,
  };
  const ro = RUNOFF[T.runoff];
  if (!ro) throw new Error('track: unknown runoff ' + T.runoff);
  T.runoffGrip = ro.grip; T.runoffDrag = ro.drag; T.runoffRoll = ro.roll;
  for (let i = 0; i < n; i++) {
    const o = 8 * i;
    T.x[i] = c[o]; T.y[i] = c[o + 1]; T.z[i] = c[o + 2]; T.bank[i] = c[o + 3];
    T.tb[i] = dsin(c[o + 3]) / dcos(c[o + 3]);
    T.hw[i] = c[o + 4]; T.wl[i] = c[o + 5]; T.wr[i] = c[o + 6]; T.grip[i] = c[o + 7];
    if (T.wl[i] < T.hw[i] + 1 - 1e-6 || T.wr[i] < T.hw[i] + 1 - 1e-6) throw new Error(`track: sample ${i} wall closer than halfWidth + 1`);
    if (T.wl[i] > T.maxWall) T.maxWall = T.wl[i];
    if (T.wr[i] > T.maxWall) T.maxWall = T.wr[i];
  }
  let s = 0;
  for (let i = 0; i < n; i++) {
    const j = i + 1 === n ? 0 : i + 1;
    const dx = T.x[j] - T.x[i], dz = T.z[j] - T.z[i];
    const l = Math.sqrt(dx * dx + dz * dz);
    if (!(l > 1e-6)) throw new Error(`track: samples ${i} and ${j} coincide`);
    T.len[i] = l; T.tx[i] = dx / l; T.tz[i] = dz / l; T.s[i] = s; s += l;
    T.grade[i] = (T.y[j] - T.y[i]) / l;
    T.heading[i] = datan2(T.tx[i], T.tz[i]);
  }
  T.s[n] = s; T.L = s;
  for (let i = 0; i < n; i++) {
    const p = i === 0 ? n - 1 : i - 1;
    T.kappa[i] = wrapPi(T.heading[i] - T.heading[p]) / (0.5 * (T.len[p] + T.len[i]));
  }
  // smoothed curvature (+-4 samples, triangular weights) for the AI and the camera
  for (let i = 0; i < n; i++) {
    let acc = 0, w = 0;
    for (let k = -4; k <= 4; k++) { const wk = 5 - Math.abs(k); acc += wk * T.kappa[(i + k + n) % n]; w += wk; }
    T.kappaS[i] = acc / w;
  }
  // checkpoints
  const cps = (meta.checkpoints || [0]).map(v => Math.round(v));
  if (cps.length < 2) throw new Error('track: need at least 2 checkpoints');
  if (cps[0] !== 0) { /* i0 is start/finish; allowed to be any sample */ }
  for (let k = 1; k < cps.length; k++) {
    const a = (cps[k - 1] - cps[0] + n) % n, b = (cps[k] - cps[0] + n) % n;
    if (!(b > a)) throw new Error('track: checkpoints must increase along the lap');
  }
  T.checkpoints = Int32Array.from(cps);
  T.cpS = Float64Array.from(cps, i => T.s[((i % n) + n) % n]);
  const sec = meta.sectors || [Math.round(cps.length / 3), Math.round(2 * cps.length / 3)];
  T.sectors = [Math.round(sec[0]), Math.round(sec[1])];
  const g = meta.grid || [];
  T.grid = [];
  for (let k = 0; k + 2 < g.length; k += 3) T.grid.push({ x: g[k], z: g[k + 1], yaw: g[k + 2] });
  if (T.grid.length === 0) {
    const i0 = T.checkpoints[0];
    T.grid.push({ x: T.x[i0], z: T.z[i0], yaw: T.heading[i0] });
  }
  const zz = meta.zones || [];
  T.zones = [];
  for (let k = 0; k + 3 < zz.length; k += 4) {
    const i0 = Math.round(zz[k]), i1 = Math.round(zz[k + 1]);
    T.zones.push({ index: T.zones.length, i0, i1, side: zz[k + 2] >= 0 ? 1 : -1, kind: Math.round(zz[k + 3]),
      s0: T.s[((i0 % n) + n) % n], s1: T.s[((i1 % n) + n) % n] });
  }
  const pp = meta.props || [];
  T.props = [];
  for (let k = 0; k + 3 < pp.length; k += 4) T.props.push({ kind: Math.round(pp[k]), x: pp[k + 1], z: pp[k + 2], r: pp[k + 3] });
  const t = meta.targets || [];
  T.targets = { goldLap: t[0] || 0, silverLap: t[1] || 0, bronzeLap: t[2] || 0,
    rushBronze: t[3] || 0, rushSilver: t[4] || 0, rushGold: t[5] || 0, rushPlatinum: t[6] || 0 };
  T.line = null; // racing line cache (engine/ai.js)
  return T;
}

/** Index arithmetic on the closed loop. */
export const wrapI = (T, i) => (i % T.n + T.n) % T.n;

function segDist2(T, i, x, z, out) {
  const px = T.x[i], pz = T.z[i], l = T.len[i], tx = T.tx[i], tz = T.tz[i];
  const dx = x - px, dz = z - pz;
  let along = dx * tx + dz * tz;
  if (along < 0) along = 0; else if (along > l) along = l;
  const cx = px + tx * along, cz = pz + tz * along;
  const ex = x - cx, ez = z - cz;
  out.u = along / l; out.cx = cx; out.cz = cz; out.ex = ex; out.ez = ez;
  return ex * ex + ez * ez;
}

const tmp = { u: 0, cx: 0, cz: 0, ex: 0, ez: 0 };

/**
 * Nearest point on the centreline polyline. `hint` is the segment found last time (or -1 for a
 * global search). Writes {seg, u, s, lat (signed, + = left of the driving direction), dist} to out.
 */
export function project(T, x, z, hint, out) {
  const n = T.n;
  let best = -1, bd = Infinity, bu = 0, bex = 0, bez = 0;
  if (hint >= 0) {
    for (let k = -3; k <= 6; k++) {
      const i = (hint + k + n) % n;
      const d = segDist2(T, i, x, z, tmp);
      if (d < bd) { bd = d; best = i; bu = tmp.u; bex = tmp.ex; bez = tmp.ez; }
    }
    // walk on while the window edge is still the best (fast cars, long jumps)
    let off = (best - hint + n) % n; if (off > n / 2) off -= n;
    let dir = off >= 6 ? 1 : off <= -3 ? -1 : 0, cur = best, guard = 0;
    while (dir !== 0 && guard++ < 64) {
      const i = (cur + dir + n) % n;
      const d = segDist2(T, i, x, z, tmp);
      if (d < bd) { bd = d; best = i; bu = tmp.u; bex = tmp.ex; bez = tmp.ez; cur = i; } else break;
    }
    const lim = T.maxWall + 8;
    if (bd > lim * lim) hint = -1; // lost: fall back to a global search
  }
  if (hint < 0) {
    bd = Infinity;
    for (let i = 0; i < n; i++) {
      const d = segDist2(T, i, x, z, tmp);
      if (d < bd) { bd = d; best = i; bu = tmp.u; bex = tmp.ex; bez = tmp.ez; }
    }
  }
  const dist = Math.sqrt(bd);
  const side = bex * T.tz[best] - bez * T.tx[best];
  out.seg = best; out.u = bu; out.s = T.s[best] + bu * T.len[best];
  out.lat = side >= 0 ? dist : -dist; out.dist = dist;
  out.ex = bex; out.ez = bez;
  return out;
}

/** Linear interpolation of a per-sample array at (seg, u). */
export function at(T, arr, seg, u) {
  const j = seg + 1 === T.n ? 0 : seg + 1;
  return arr[seg] + (arr[j] - arr[seg]) * u;
}

/**
 * Surface under a point already projected (seg, u, lat). Writes y (height), nx ny nz (unit normal),
 * grip (dry surface multiplier), code (SURF), hw, wl, wr, roll (extra rolling resistance) and drag.
 */
export function surfaceAt(T, seg, u, lat, out) {
  const j = seg + 1 === T.n ? 0 : seg + 1;
  const tb = T.tb[seg] + (T.tb[j] - T.tb[seg]) * u;
  const hw = T.hw[seg] + (T.hw[j] - T.hw[seg]) * u;
  const yc = T.y[seg] + (T.y[j] - T.y[seg]) * u;
  out.y = yc + lat * tb;
  const g = T.grade[seg], tx = T.tx[seg], tz = T.tz[seg];
  const gx = g * tx + tb * tz, gz = g * tz - tb * tx;
  const inv = 1 / Math.sqrt(gx * gx + 1 + gz * gz);
  out.nx = -gx * inv; out.ny = inv; out.nz = -gz * inv;
  out.hw = hw;
  out.wl = T.wl[seg] + (T.wl[j] - T.wl[seg]) * u;
  out.wr = T.wr[seg] + (T.wr[j] - T.wr[seg]) * u;
  const a = lat < 0 ? -lat : lat;
  if (a <= hw) { out.code = 0; out.grip = T.grip[seg] + (T.grip[j] - T.grip[seg]) * u; out.roll = 0; out.drag = 0; }
  else if (a <= hw + CURB_BAND) { out.code = 1; out.grip = CURB_GRIP * (T.grip[seg] + (T.grip[j] - T.grip[seg]) * u); out.roll = 0.004; out.drag = 0; }
  else { out.code = 2; out.grip = T.runoffGrip; out.roll = T.runoffRoll; out.drag = T.runoffDrag; }
  return out;
}

export const SURFACE_NAMES = ['asphalt', 'curb', 'runoff'];
export function surfaceName(T, code) { return code === 2 ? T.runoff : SURFACE_NAMES[code]; }

/** Signed forward arc distance from a to b along the loop, wrapped to (-L/2, L/2]. */
export function arcDelta(T, a, b) {
  let d = b - a;
  const L = T.L;
  if (d > L / 2) d -= L; else if (d <= -L / 2) d += L;
  return d;
}

/** Point on the centreline at arc length s, plus the left normal; writes x z y tx tz seg u. */
export function pointAtS(T, s, out) {
  const L = T.L;
  s = s - L * Math.floor(s / L);
  // binary search on T.s
  let lo = 0, hi = T.n - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (T.s[mid] <= s) lo = mid; else hi = mid - 1; }
  const i = lo, u = (s - T.s[i]) / T.len[i];
  const j = i + 1 === T.n ? 0 : i + 1;
  out.seg = i; out.u = u;
  out.x = T.x[i] + (T.x[j] - T.x[i]) * u; out.z = T.z[i] + (T.z[j] - T.z[i]) * u; out.y = T.y[i] + (T.y[j] - T.y[i]) * u;
  out.tx = T.tx[i]; out.tz = T.tz[i];
  return out;
}
