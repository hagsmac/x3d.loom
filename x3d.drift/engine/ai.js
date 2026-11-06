// loom:sim
// AI drivers (CONTRACT.md section 9). They see only the sim state and press the same buttons a
// player does (steer, throttle, brake, handbrake), quantised exactly like a packed Input, so a bot
// run can be recorded as a tape and replayed bit for bit.
//   racing line: minimum-curvature relaxation of the centreline inside the asphalt
//   speed profile: v = sqrt(mu g / |kappa|), backward braking pass, forward acceleration pass
//   steering: pure pursuit on the line, lookahead growing with speed
//   skill 0..1: scales the profile 0.88..1.0 and adds hashed, smooth line noise (no Math.random)
//   drift mode: handbrake entry, then holds a target body slip (30-40 deg) with throttle while the
//   front wheels follow the velocity and a yaw-rate loop keeps the slide on the line.
import { dsin, dcos, datan, datan2, wrapPi, clamp, smooth, inoise, DEG, PI } from './fmath.js';
import { pointAtS } from './track.js';
import { steerInputFor, G } from './car.js';

const LINE_PASSES = [[12, 60], [8, 60], [5, 60], [3, 50], [2, 40]];
/** Drift-mode constants (tools/ and tests/ read them; the sim treats them as fixed). */
export const DRIFT = {
  wetBeta: 8, wetMargin: 0.6, wetAn: 0.56,   // the wet: deg off the held angle, m of extra margin, sliding-grip share
  awdBeta: 5,       // deg off the held angle for an AWD car (driven fronts pull it straight: it slides shallower)
  lineScale: 1,     // drift line offsets as a share of the racing line's (1 = the racing line)
  inRoad: 0,        // share of the road's own curvature (v^2 k) counted as stopping an approach to the inside edge
  margin: 2.4,      // m beyond the half width kept clear of the edges while sliding
  an: 0.56,         // share of mu*g a held 30-40 deg slide carries sideways (sets the drift speeds)
  beta: 42,         // deg, the slide angle aimed for through a corner (the line trim takes some back: it holds 30-40)
  trim: 6,          // deg, how far the angle may give or grow to keep the line
  trimK: 0.6,       // rad of angle trim per g of path error
  pathW: 0.75,      // rad/s, how briskly a slide is pulled back onto its line
  yawDecel: 2.6,    // rad/s^2 the front can take out of a slide's rotation
  kp: 1.4, ki: 0.3, kd: 0.05,   // throttle on path error (g) and on speed change
  exitR: 150,       // m, a corner opening wider than this ends the slide
  kLead: 0.2,       // s of look-ahead on the line curvature the path follows
  saveKr: 0.16, saveCap: 1.5,   // a save damps the yaw harder (a slide unwinding fast throws the car the other way)
  saveT: 0.35, saveDecel: 3.5,   // a slide is abandoned when the edge is nearer than a reaction (s) plus a lateral stop (m/s^2)
  vLo: 0.98, vHi: 1.10,          // entry speed window around the corner's drift speed
  carry: 1.03,      // cruise speed into a corner, relative to its drift speed
  tapGap: 10, tapRate: -0.05, tapK: 0.3,   // handbrake tap: angle short of target (deg), falling (rad/s), rears hooked up
  linkMax: 160, linkBeta: 22, linkMin: 16,  // linking corners: a straight shorter than linkMax m is drifted through at linkBeta deg (never under linkMin) so the chain lives
};

/** Race-AI constants (traffic, starts, skill and the pack). */
export const RACE = {
  skillLo: 0.88,    // speed-profile scale at skill 0 (skill 1 = 1.0)
  merge: 60,        // m over which a starting car merges from its grid lane onto the line
  mergeLead: 70,    // m before the first real corner where the merge is complete
  alongside: 1.0,   // m of extra length within which another car counts as alongside
  air: 0.7,         // m of air kept between the sides of two cars
  look: 32,         // m ahead the traffic logic looks
  pack: 1, packFrom: 40, packFull: 260, packSlow: 0.035, packPush: 0.025,   // race-mode pace pull toward the player
};

/** Arc distance from the start line to where the merge must be done: the first corner tighter than 1/150 m, less RACE.mergeLead. */
function startMergeAt(T, line) {
  if (line.mergeAt !== undefined) return line.mergeAt;
  const s0 = T.s[T.checkpoints[0]];
  let at = 0;
  for (let d = 0; d < T.L * 0.5; d += 2) { lineAt(T, line, s0 + d, LP); if (Math.abs(LP.k) > 1 / 150) { at = d; break; } }
  line.mergeAt = Math.max(0, at - RACE.mergeLead);
  return line.mergeAt;
}

/** Minimum-curvature racing line as lateral offsets (+ left) per sample; cached on the track. */
export function racingLine(T, margin) {
  const key = 'm' + margin.toFixed(2);
  T.lineCache = T.lineCache || {};
  if (T.lineCache[key]) return T.lineCache[key];
  const n = T.n;
  const nx = new Float64Array(n), nz = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const p = i === 0 ? n - 1 : i - 1;
    let ax = T.tz[p] + T.tz[i], az = -T.tx[p] - T.tx[i];
    const l = Math.sqrt(ax * ax + az * az) || 1;
    nx[i] = ax / l; nz[i] = az / l;
  }
  const lat = new Float64Array(n), px = new Float64Array(n), pz = new Float64Array(n), lim = new Float64Array(n);
  for (let i = 0; i < n; i++) { px[i] = T.x[i]; pz[i] = T.z[i]; lim[i] = Math.max(0.3, T.hw[i] - margin); }
  for (const [k, iters] of LINE_PASSES) {
    for (let it = 0; it < iters; it++) {
      for (let i = 0; i < n; i++) {
        const a = (i - k + n) % n, b = (i + k) % n;
        const mx = 0.5 * (px[a] + px[b]), mz = 0.5 * (pz[a] + pz[b]);
        const d = (mx - px[i]) * nx[i] + (mz - pz[i]) * nz[i];
        let l = lat[i] + 0.6 * d;
        if (l > lim[i]) l = lim[i]; else if (l < -lim[i]) l = -lim[i];
        lat[i] = l; px[i] = T.x[i] + nx[i] * l; pz[i] = T.z[i] + nz[i] * l;
      }
    }
  }
  const out = lineGeometry(T, lat, nx, nz);
  T.lineCache[key] = out;
  return out;
}

/** The drift line: the racing line's offsets scaled toward the centre (a sliding car wants room on both sides). */
export function driftLine(T, margin, scale) {
  if (scale === 1) return racingLine(T, margin);
  const key = 'd' + margin.toFixed(2) + 'x' + scale.toFixed(3);
  T.lineCache = T.lineCache || {};
  if (T.lineCache[key]) return T.lineCache[key];
  const rl = racingLine(T, margin), n = T.n, lat = new Float64Array(n);
  for (let i = 0; i < n; i++) lat[i] = rl.lat[i] * scale;
  const out = lineGeometry(T, lat, rl.nx, rl.nz);
  T.lineCache[key] = out;
  return out;
}

/** Positions, smoothed signed curvature (+ = left) and arc lengths of a line given its offsets. */
function lineGeometry(T, lat, nx, nz) {
  const n = T.n;
  const px = new Float64Array(n), pz = new Float64Array(n);
  for (let i = 0; i < n; i++) { px[i] = T.x[i] + nx[i] * lat[i]; pz[i] = T.z[i] + nz[i] * lat[i]; }
  const kap = new Float64Array(n), ks = new Float64Array(n), hd = new Float64Array(n), len = new Float64Array(n), s = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const dx = px[j] - px[i], dz = pz[j] - pz[i];
    len[i] = Math.sqrt(dx * dx + dz * dz) || 1e-3; hd[i] = datan2(dx, dz);
  }
  for (let i = 0; i < n; i++) s[i + 1] = s[i] + len[i];
  for (let i = 0; i < n; i++) { const p = i === 0 ? n - 1 : i - 1; kap[i] = wrapPi(hd[i] - hd[p]) / (0.5 * (len[p] + len[i])); }
  for (let i = 0; i < n; i++) { let acc = 0, w = 0; for (let k = -3; k <= 3; k++) { const wk = 4 - Math.abs(k); acc += wk * kap[(i + k + n) % n]; w += wk; } ks[i] = acc / w; }
  return { lat, px, pz, nx, nz, kappa: ks, len, s, L: s[n] };
}

/** Speed profile along a line for lateral grip mu (g units), braking and accelerating limits. */
export function speedProfile(T, line, o) {
  const n = T.n, v = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const k = Math.abs(line.kappa[i]);
    // banking toward the inside of the turn adds grip (positive bank raises the left edge)
    const helps = clamp(-(line.kappa[i] > 0 ? 1 : -1) * T.tb[i], -0.15, 0.3);
    const mu = o.mu + helps;
    v[i] = k > 1e-5 ? Math.sqrt(mu * G / k) : o.vTop;
    if (v[i] > o.vTop) v[i] = o.vTop;
    if (o.vMin && v[i] < o.vMin) v[i] = o.vMin;
  }
  for (let pass = 0; pass < 2; pass++) {
    for (let c = 0; c < n; c++) {          // backward: brake in time
      const i = (n - 1 - c + n) % n, j = (i + 1) % n;
      const lim = Math.sqrt(v[j] * v[j] + 2 * o.aBrake * line.len[i]);
      if (v[i] > lim) v[i] = lim;
    }
    for (let i = 0; i < n; i++) {          // forward: can only accelerate so fast
      const j = (i + 1) % n;
      const a = Math.max(0.6, o.aAcc * (1 - v[i] / (o.vTop * 1.02)));
      const lim = Math.sqrt(v[i] * v[i] + 2 * a * line.len[i]);
      if (v[j] > lim) v[j] = lim;
    }
  }
  return v;
}

function carLimits(car, wet) {
  const sp = car.P.spec;
  const mu = sp.tyre.mu * car.tune.grip * (wet ? 0.72 : 1);
  let pk = 0;
  for (const [rpm, nm] of sp.torque) { const p = nm * rpm * PI / 30; if (p > pk) pk = p; }
  const Pe = pk * sp.efficiency * 0.82;
  // top speed where power meets drag + rolling resistance (bisection: v * F(v) is monotonic)
  let lo = 5, hi = 120;
  for (let k = 0; k < 40; k++) {
    const v = 0.5 * (lo + hi);
    if (v * (0.6125 * sp.CdA * v * v + sp.Crr * sp.mass * G) > Pe) hi = v; else lo = v;
  }
  const v = 0.5 * (lo + hi);
  return { mu, vTop: v * 0.97, aAcc: Math.min(0.5 * mu * G, Pe / (sp.mass * 18)), aBrake: 0.88 * mu * G };
}

/**
 * Create the controller for car `ci`. mode 'race' follows the racing line at the limit; mode
 * 'drift' slides every corner. skill 0..1.
 */
export function createDriver(sim, ci, mode, skill) {
  const car = sim.cars[ci], T = sim.track;
  const wet = sim.surface === 'wet';
  const lim = carLimits(car, wet);
  const margin = car.P.halfW + 0.55;
  const line = racingLine(T, margin);
  // skill scales the speed profile itself (0.88..1.0): corner speed goes with sqrt(mu), so mu takes sc^2
  const sc = RACE.skillLo + (1 - RACE.skillLo) * clamp(skill, 0, 1);
  const vRace = speedProfile(T, line, { mu: lim.mu * 0.80 * sc * sc, vTop: lim.vTop * sc, aAcc: lim.aAcc, aBrake: lim.aBrake * 0.8 * sc });
  // the fastest this car's driver may be pushed by the pack (race mode): its skill-1 profile
  const vMax = mode === 'race' && sc < 1 ? speedProfile(T, line, { mu: lim.mu * 0.80, vTop: lim.vTop, aAcc: lim.aAcc, aBrake: lim.aBrake * 0.8 }) : vRace;
  // drift line: further from the edges (a sliding car is wider), and a sliding-grip speed profile
  const dline = mode === 'drift' ? driftLine(T, car.P.halfW + DRIFT.margin + (wet ? DRIFT.wetMargin : 0), DRIFT.lineScale) : line;
  const vDrift = mode === 'drift' ? speedProfile(T, dline, { mu: lim.mu * (wet ? DRIFT.wetAn : DRIFT.an), vTop: Math.min(lim.vTop, 42), aAcc: lim.aAcc * 0.8, aBrake: lim.aBrake * 0.6, vMin: 11 }) : null;
  return {
    ci, mode, skill: clamp(skill, 0, 1), seed: 1009 * (ci + 1) + 17, line, vRace, vMax, vDrift, dline, lim, gf: wet ? 0.72 : 1,
    lane0: car.lat, merged: sim.cars.length < 2, pace: 1, passK: -1, passSide: 0, offLat: 0,
    // linking corners is a Drift Rush habit (the chain is the score); on the wet a straight-line slide is too much to ask
    linkOK: mode === 'drift' && sim.mode === 'rush' && !wet,
    phase: 'cruise', timer: 0, dir: 0, link: 0, stuck: 0, resetCool: 0,
    betaTarget: (DRIFT.beta - (wet ? DRIFT.wetBeta : 0) - (car.P.awd ? DRIFT.awdBeta : 0)) * DEG, bT: 0, vhPrev: 0, vhInit: false, kAct: 0, thrI: 0.6, rI: 0, bAdj: 0, rPrev: 0, rInit: false, rDotF: 0, vPrev: 0, vInit: false, accF: 0, hbTimer: 0, hbCool: 0, latPrev: 0, latInit: false, latRateF: 0,
  };
}

const PT = { seg: 0, u: 0, x: 0, z: 0, y: 0, tx: 0, tz: 0 };
function lineAt(T, line, s, out) {
  pointAtS(T, s, PT);
  const i = PT.seg, j = (i + 1) % T.n, u = PT.u;
  out.x = line.px[i] + (line.px[j] - line.px[i]) * u;
  out.z = line.pz[i] + (line.pz[j] - line.pz[i]) * u;
  out.k = line.kappa[i] + (line.kappa[j] - line.kappa[i]) * u;
  out.i = i; out.u = u;
  out.nx = line.nx[i]; out.nz = line.nz[i];
  return out;
}
const LP = { x: 0, z: 0, k: 0, i: 0, u: 0, nx: 0, nz: 0 };
const sampleV = (arr, i, u, n) => arr[i] + (arr[(i + 1) % n] - arr[i]) * u;

function quantise(out, steer, thr, brk, hb, boost) {
  out.steer = clamp(Math.round(steer), -127, 127);
  out.throttle = clamp(Math.round(thr * 15), 0, 15);
  out.brake = clamp(Math.round(brk * 15), 0, 15);
  out.handbrake = !!hb; out.boost = !!boost; out.shiftUp = false; out.shiftDown = false; out.reset = false;
  return out;
}

/** Curvature ahead: the signed peak over [s + a, s + b] along the line. */
function peakAhead(T, line, s, a, b) {
  let best = 0;
  for (let d = a; d <= b; d += 2) {
    lineAt(T, line, s + d, LP);
    if (Math.abs(LP.k) > Math.abs(best)) best = LP.k;
  }
  return best;
}

/** A driver's right foot: ease off when the driven wheels spin up (grip driving, not drifting). */
function throttleGrip(car) {
  let k = 0;
  for (let i = 0; i < 4; i++) if (car.wheels[i].driven && car.wheels[i].kappa > k) k = car.wheels[i].kappa;
  const kp = car.P.kpk;
  return clamp(1 - (k - 1.6 * kp) / (2.5 * kp), 0.25, 1);
}

/**
 * Grip steering toward a target point: pure pursuit in the velocity frame gives the path curvature
 * wanted; the front wheels follow the front axle's velocity (so a slide is caught by itself) plus
 * the slip angle that curvature needs, trimmed by a yaw-rate loop.
 */
const GS = { need: 0 };
function gripSteer(drv, car, v, tx, tz, kr = 0.10, cap = 1.1) {
  GS.need = 0;
  const u = car.forwardSpeed, wv = car.lateralSpeed;
  const dx = tx - car.x, dz = tz - car.z;
  if (u < 4) {
    const c = dcos(car.yaw), sn = dsin(car.yaw);
    const fwd = dx * sn + dz * c, left = dx * c - dz * sn, d2 = fwd * fwd + left * left;
    return fwd < 0 ? (left > 0 ? 0.6 : -0.6) : datan(2 * left / (d2 > 1 ? d2 : 1) * car.P.L);
  }
  const vh = datan2(car.vx, car.vz);
  const cv = dcos(vh), sv = dsin(vh);
  const fv = dx * sv + dz * cv, lv = dx * cv - dz * sv;
  const dd = fv * fv + lv * lv;
  const kDes = fv > 0 ? 2 * lv / (dd > 1 ? dd : 1) : (lv > 0 ? 0.15 : -0.15);
  const rDes = v * kDes;
  const aPk = car.P.spec.tyre.alphaPeakDeg * DEG;
  const need = clamp(v * rDes / (drv.lim.mu * G), -1, 1), an = need < 0 ? -need : need;
  GS.need = an;
  // inverse of the tyre's rise f = 1 - (1 - s)^3, by a fit good to a few percent
  const sNeed = an * (0.333 + an * (0.12 + 0.55 * an * an));
  const dvF = datan2(wv + car.yawRate * car.P.a, u);
  const corr = (need < 0 ? -sNeed : sNeed) * aPk + kr * (rDes - car.yawRate);
  return dvF + clamp(corr, -cap * aPk, cap * aPk);
}

/** Fill `out` (an unpacked Input) for this tick. */
export function driveAI(sim, drv, out) {
  const car = sim.cars[drv.ci], T = sim.track, tick = sim.tick, dt = 1 / 120;
  const v = car.speed;
  const c = dcos(car.yaw), sn = dsin(car.yaw);
  const race = sim.race;
  if (race && (race.phase === 'countdown' || (race.phase === 'grid' && race.mode !== 'rush'))) {
    // rev to the launch speed on the grid
    const launch = car.P.spec.launchRpm;
    return quantise(out, 0, car.rpm < launch * 0.92 ? 1 : 0.2, 0, false, false);
  }
  // stuck recovery: back out, then reset
  if (race && race.phase === 'running' && v < 1.0) drv.stuck += dt; else drv.stuck = 0;
  if (drv.resetCool > 0) drv.resetCool -= dt;
  if (drv.stuck > 3.0 && drv.resetCool <= 0) { drv.stuck = 0; drv.resetCool = 2; const o = quantise(out, 0, 0, 0, false, false); o.reset = true; return o; }
  const line = drv.line;
  const noise = (1 - drv.skill) * 0.9 * inoise(tick, drv.seed, 300);
  // pure pursuit target
  const Ld = clamp(5 + 0.42 * v, 7, 40);
  lineAt(T, line, car.s + Ld, LP);
  let tx = LP.x + LP.nx * noise, tz = LP.z + LP.nz * noise;
  // traffic (race AI with company): hold the grid lane into the first corner, never squeeze a car
  // that is alongside, pass a slower car on the side with room, follow when there is none
  let vCap = 1e9;
  if (sim.cars.length > 1 && drv.mode === 'race') {
    const lineLat = line.lat[LP.i] + noise, edge = car.hw - car.P.halfW - 0.3;
    let want = lineLat;
    if (!drv.merged) {
      // the start: keep the grid lane until the first corner nears, then merge onto the line over RACE.merge m
      const w = clamp((startMergeAt(T, line) - car.raceDist) / RACE.merge, 0, 1);
      if (w <= 0) drv.merged = true;
      want = lineLat + (clamp(drv.lane0, -edge, edge) - lineLat) * w;
    }
    let lo = -edge, hi = edge, pass = 0, wPass = 0, passK = -1, passSide = 0;
    // the speed this driver wants just ahead: a car in front slower than that is worth passing,
    // even while we are held behind it (our own speed then only matches its)
    const vWish = sampleV(drv.vRace, LP.i, LP.u, T.n) * drv.pace;
    // a pass is started only where the road runs straight (pulling out under braking into a bend
    // spins the car); one already under way carries on into the bend only once it is half alongside
    const kSeg = T.kappaS[car.seg];
    const straight = (LP.k < 0 ? -LP.k : LP.k) < 1 / 250 && (kSeg < 0 ? -kSeg : kSeg) < 1 / 250;
    for (let k = 0; k < sim.cars.length; k++) {
      if (k === drv.ci) continue;
      const o = sim.cars[k];
      const gap = o.raceDist - car.raceDist;
      const along = car.P.halfL + o.P.halfL + RACE.alongside;
      if (gap < -along || gap > RACE.look) continue;
      const dl = car.lat - o.lat, adl = dl < 0 ? -dl : dl;
      const need = car.P.halfW + o.P.halfW + RACE.air;
      if (gap <= along) {
        // overlapping lengthwise (or nearly): a car's width of air on its side, whoever is ahead
        if (dl >= 0) lo = Math.max(lo, o.lat + need); else hi = Math.min(hi, o.lat - need);
        // nose behind its door with no room on our side: tuck in behind it
        if (gap > 0.5 * along && (dl >= 0 ? edge - o.lat : edge + o.lat) < need) { const vf = o.speed - 1.5; if (vf < vCap) vCap = vf; }
        continue;
      }
      // ahead: in our way if our lane (want) comes within a car's width of it
      const inWay = (want - o.lat < 0 ? o.lat - want : want - o.lat) < need;
      const closing = (vWish > car.speed ? vWish : car.speed) - o.speed;
      if (!inWay) continue;
      const gapWant = car.P.halfL + o.P.halfL + 1.5 + 0.25 * v;   // the following gap
      const passing = drv.passK === k;          // already committed to passing this car: hold the decision
      if (closing > (passing ? -2 : -0.5) && gap < 22 && (straight || (passing && adl > 0.5 * need))) {
        // pass on the side we are already on (or committed to), or the one with more room
        const roomL = edge - o.lat, roomR = edge + o.lat;
        let side = passing && drv.passSide ? drv.passSide : dl > 0.3 ? 1 : dl < -0.3 ? -1 : (roomL >= roomR ? 1 : -1);
        if ((side > 0 ? roomL : roomR) < need) side = -side;
        if ((side > 0 ? roomL : roomR) >= need) {
          // fully committed to the passing lane from a little beyond the following gap (a car that
          // only half pulls out sits behind for good)
          const wk = clamp((22 - gap) / Math.max(1, 16 - gapWant), 0, 1);
          if (wk > wPass) { wPass = wk; pass = clamp(o.lat + side * need, -edge, edge); passK = k; passSide = side; }
        }
      }
      // keep a following gap behind a car we cannot pass yet
      if (adl < need) { const vf = o.speed + 0.8 * (gap - gapWant); if (vf < vCap) vCap = vf; }
    }
    if (wPass > 0) want += (pass - want) * wPass;
    drv.passK = passK; drv.passSide = passSide;
    if (lo > hi) { want = 0.5 * (lo + hi); } else want = clamp(want, lo, hi);
    drv.wantLat = want;
    const off = want - lineLat;
    drv.offLat = off;
    tx += LP.nx * off; tz += LP.nz * off;
    // the pack: race AI well clear of the player eases off, one well behind pushes (never past its
    // skill-1 profile). Deterministic: it reads only positions in the sim.
    if (sim.mode === 'race' && sim.race && sim.race.phase === 'running' && RACE.pack > 0) {
      const pc = sim.cars[sim.playerIndex];
      if (pc && pc !== car && sim.entrants[sim.playerIndex].driver === 'player') {
        const g = car.raceDist - pc.raceDist;               // + = ahead of the player
        const ag = g < 0 ? -g : g;
        const f = smooth(RACE.packFrom, RACE.packFull, ag) * RACE.pack;
        drv.pace = g > 0 ? 1 - RACE.packSlow * f : 1 + RACE.packPush * f;
      }
    }
  }
  const dx = tx - car.x, dz = tz - car.z;
  const fwd = dx * sn + dz * c, left = dx * c - dz * sn;
  const d2 = fwd * fwd + left * left;
  if (drv.mode === 'drift') return driftDrive(sim, drv, car, out, v);
  const delta = gripSteer(drv, car, v, tx, tz);
  // speed control from the profile, looking a little ahead
  const sAhead = car.s + clamp(v * 0.35, 2, 30);
  lineAt(T, line, sAhead, LP);
  // off the line (passing, or holding a lane) on the inside of a bend the radius is tighter: v ~ sqrt(R)
  const kOff = drv.offLat ? LP.k * drv.offLat : 0;
  const vProf = sampleV(drv.vRace, LP.i, LP.u, T.n) * drv.pace * (kOff > 0 ? Math.sqrt(1 - (kOff < 0.4 ? kOff : 0.4)) : 1);
  const vt = Math.max(0, Math.min(vProf, sampleV(drv.vMax, LP.i, LP.u, T.n), vCap));
  const err = vt - v;
  let thr = 0, brk = 0;
  if (err > -0.6) thr = clamp(0.55 + 0.4 * err, 0, 1);
  else brk = clamp(-(err + 0.6) * 0.28, 0, 1);
  // the rear axle sliding: feed less throttle (the steering already catches it)
  const aR = 0.5 * (car.wheels[2].slipAngle + car.wheels[3].slipAngle);
  const sR = (aR < 0 ? -aR : aR) / (car.P.spec.tyre.alphaPeakDeg * DEG);
  if (sR > 0.85 && car.forwardSpeed > 4) thr *= clamp(1 - (sR - 0.85) / 0.6, 0.15, 1);
  thr *= throttleGrip(car);
  // the friction circle: what the turn asks of the tyres is not there for driving
  const ff = GS.need;
  thr = Math.min(thr, Math.sqrt(ff < 1 ? 1 - ff * ff : 0) + 0.25);
  if (car.gear === -1) { thr = 0; brk = 0; }
  const steer = steerInputFor(car, delta);
  return quantise(out, steer, thr, brk, false, false);
}

/** Distance to the first point in [s + a, s + b] where the line bends harder than 1/130 m (or -1). */
const CA = { k: 0, len: 0 };
function cornerAhead(T, line, s, a, b) {
  for (let d = a; d <= b; d += 2) {
    lineAt(T, line, s + d, LP);
    if (Math.abs(LP.k) > 1 / 130) {
      CA.k = LP.k;
      // how much of the bend is left from there (a flick into a corner's last metres is a spin)
      let len = 0;
      const sg = LP.k > 0 ? 1 : -1;
      for (let e = d; e < d + 60; e += 2) { lineAt(T, line, s + e, LP); if (LP.k * sg < 1 / 170) break; len += 2; }
      CA.len = len;
      return d;
    }
  }
  return -1;
}
/** Lowest value of a per-sample profile over [s0, s1]. */
function minAhead(T, prof, s0, s1) {
  let m = 1e9;
  for (let s = s0; s <= s1; s += 3) { pointAtS(T, s, PT); const v = prof[PT.seg]; if (v < m) m = v; }
  return m;
}

/** Signed mean curvature of the line over [s + a, s + b]. */
function meanK(T, line, s, a, b) {
  let acc = 0, n = 0;
  for (let d = a; d <= b; d += 2) { lineAt(T, line, s + d, LP); acc += LP.k; n++; }
  return n ? acc / n : 0;
}

/**
 * Drift mode. In the corner's frame (dir = +1 for a left-hander) the body slip is b = -dir * beta,
 * positive in a proper slide. Two loops:
 *   steering tracks a yaw rate r* = v * k* + dir * kb * (b* - b), where k* is the curvature that a
 *     velocity-frame pure pursuit asks of the path. The slide angle follows from
 *     db/dt = r - v * k_path, so holding r* makes b settle on b* once the path curvature is right;
 *   throttle sets the path: more wheelspin turns the rear force forward and widens the line, less
 *     tightens it (a PI on the measured path curvature against k*).
 * Corners are entered with a handbrake flick and left by ramping b* to zero.
 */
function driftDrive(sim, drv, car, out, v) {
  const T = sim.track, line = drv.dline, dt = 1 / 120, n = T.n;
  const u = car.forwardSpeed, wv = car.lateralSpeed;
  const beta = car.slip, ab = beta < 0 ? -beta : beta;
  // measured path curvature from the velocity heading
  const vh = v > 0.5 ? datan2(car.vx, car.vz) : car.yaw;
  const kMeas = drv.vhInit && v > 2 ? wrapPi(vh - drv.vhPrev) / (v * dt) : 0;
  drv.vhPrev = vh; drv.vhInit = true;
  drv.kAct += (kMeas - drv.kAct) * 0.12;
  // velocity-frame pure pursuit on the drift line
  const Ld = clamp(5 + 0.45 * v, 8, 32);
  lineAt(T, line, car.s + Ld, LP);
  const cv = dcos(vh), sv = dsin(vh);
  const dx = LP.x - car.x, dz = LP.z - car.z;
  const fv = dx * sv + dz * cv, lv = dx * cv - dz * sv;
  const dd = fv * fv + lv * lv;
  let kDes = fv > 0 ? 2 * lv / (dd > 1 ? dd : 1) : (lv > 0 ? 0.1 : -0.1);
  // the corner here (next ~0.9 s) and ahead
  const kHere = meanK(T, line, car.s, 0, clamp(v * 0.9, 8, 30));
  const kAhead = peakAhead(T, line, car.s, 4, clamp(10 + v * 1.4, 16, 60));
  lineAt(T, line, car.s + clamp(v * 0.5, 3, 30), LP);
  const vt = sampleV(drv.vDrift, LP.i, LP.u, n);
  const cornerHere = Math.abs(kHere) > 1 / 220;
  let thr = 0, brk = 0, hb = false, delta = 0;
  // ---- phase machine: cruise -> entry -> hold -> exit -> cruise -----------------------------
  if (drv.phase === 'cruise' || drv.phase === 'exit') {
    // flick in just before the corner, and only near the speed its slide can carry
    const dC = cornerAhead(T, line, car.s, 0, clamp(0.6 * v, 8, 28));
    const vC = dC >= 0 ? minAhead(T, drv.vDrift, car.s + dC, car.s + dC + 24) : 0;
    if (dC >= 0 && CA.len >= Math.max(14, 0.6 * v) && v > 11 && v > DRIFT.vLo * vC && v < DRIFT.vHi * vC + 0.5 && (drv.phase === 'cruise' || CA.k * drv.dir < 0 || ab < 12 * DEG)) {
      const d = CA.k > 0 ? 1 : -1;
      // a slide already going the right way is simply held; otherwise flick into it
      if (ab > 12 * DEG && -d * beta > 0) { drv.phase = 'hold'; drv.dir = d; }
      else { drv.phase = 'entry'; drv.dir = d; drv.timer = 0; }
    }
  }
  // save: about to meet an edge, or spinning. Straighten up and drive out; drifting resumes later
  const latRate = drv.latInit ? (car.lat - drv.latPrev) / dt : 0;
  drv.latPrev = car.lat; drv.latInit = true;
  drv.latRateF += (latRate - drv.latRateF) * 0.2;
  // room toward the side it is drifting to: to the asphalt edge (plus the curb), and to the barrier
  // less the slid car's half extent (a car at an angle is wider)
  const toLeft = drv.latRateF > 0;
  const cb = dcos(beta), sb = dsin(beta);
  const extent = car.P.halfW * (cb < 0 ? -cb : cb) + car.P.halfL * (sb < 0 ? -sb : sb);
  const edgeRoom = toLeft ? car.hw + 0.8 - car.lat : car.hw + 0.8 + car.lat;
  const wallRoom = (toLeft ? car.wl - car.lat : car.wr + car.lat) - extent - 0.3;
  const room = edgeRoom < wallRoom ? edgeRoom : wallRoom;
  // the room a slide needs to stop drifting sideways: a reaction, then about DRIFT.saveDecel of lateral braking
  const lr = drv.latRateF < 0 ? -drv.latRateF : drv.latRateF;
  // toward the inside of the corner the road itself curves away at v^2 k, which stops the approach too
  const inward = drv.phase !== 'cruise' && toLeft === ((drv.dir || 1) > 0);
  const dec = DRIFT.saveDecel * drv.gf + (inward ? DRIFT.inRoad * v * v * (kHere < 0 ? -kHere : kHere) : 0);
  const need = DRIFT.saveT * lr + lr * lr / (2 * dec) + 0.4;
  if (drv.phase !== 'cruise' && drv.phase !== 'save' && (room < need || ab > 62 * DEG)) { drv.saveWhy = (ab > 62 * DEG ? 'angle' : edgeRoom < wallRoom ? 'edge' : 'wall') + ':' + drv.phase + ':' + (toLeft === (drv.dir > 0) ? 'in' : 'out'); drv.phase = 'save'; drv.timer = 0; }
  if (drv.phase === 'save') {
    drv.timer += dt;
    if (drv.timer > 0.6 && ab < 14 * DEG && room > 2 * need + 1 && Math.abs(car.slipRate) < 1.0) drv.phase = 'cruise';   // not while the angle still swings
  }
  if (drv.phase === 'hold' && Math.abs(kHere) < 1 / DRIFT.exitR && Math.abs(kAhead) < 1 / 130) {
    // the bend is over: link to the next one if it is near (keep a shallower slide down the straight), else ease out
    let dN = -1;
    if (drv.linkOK && DRIFT.linkMax > 0 && -drv.dir * beta > DRIFT.linkMin * DEG) {
      let d0 = 0;                       // past the tail of this bend first
      for (; d0 < 60; d0 += 2) { lineAt(T, line, car.s + d0, LP); if (LP.k * drv.dir < 1 / 170) break; }
      dN = cornerAhead(T, line, car.s, d0, DRIFT.linkMax);
    }
    if (dN >= 0 && CA.len >= 14) {
      drv.link = 1;
      if (CA.k * drv.dir < 0 && dN < clamp(1.2 * v, 10, 40)) drv.dir = -drv.dir;   // the next bend turns the other way: swing across
    } else { drv.phase = 'exit'; drv.timer = 0; drv.link = 0; }
  } else if (drv.phase !== 'hold' || Math.abs(kHere) >= 1 / DRIFT.exitR) drv.link = 0;
  if (drv.phase === 'hold' && kAhead * drv.dir < 0 && Math.abs(kAhead) > 1 / 100 && Math.abs(kHere) < 1 / 160) {
    drv.dir = -drv.dir;                 // transition: swing the slide the other way
  }
  const dir = drv.dir || 1;
  const b = -dir * beta;                // slide angle in the corner's frame
  // a slide already swung the wrong way (a transition) is steered through by the hold loops, not
  // flicked: full throttle and lock against it only grow the wrong-way angle
  if (drv.phase === 'entry' && b < -12 * DEG) { drv.phase = 'hold'; drv.timer = 0; drv.thrI = 0.65; drv.rI = 0; }
  if (drv.phase === 'entry') {
    drv.timer += dt;
    drv.bT = drv.betaTarget;
    // turn in and pull the handbrake until the rear steps out
    const lock = car.tune.steerLock * DEG;
    delta = dir * lock * 0.75;
    const rEnough = Math.min(1.5, Math.sqrt(2 * DRIFT.yawDecel * drv.gf * clamp(drv.betaTarget - b, 0, 1)) * 0.8);
    // a slide already swinging the other way (a transition) needs no handbrake: its own yaw carries it
    hb = drv.timer < 0.5 && b < 13 * DEG && b > -6 * DEG && dir * car.yawRate < rEnough;
    thr = 1;
    if (v > vt + 4) brk = 0.4;
    if (b > 12 * DEG || dir * car.yawRate > rEnough + 0.2 || drv.timer > 0.9) { drv.phase = 'hold'; drv.timer = 0; drv.thrI = 0.65; drv.rI = 0; }
    return quantise(out, steerInputFor(car, delta), thr, brk, hb, false);
  }
  if (drv.phase === 'cruise' || drv.phase === 'save') {
    // grip driving on the drift line at the drift speed (and the way out of a save); the grip
    // steering follows the velocity, so a slide left over from the corner is caught by itself
    delta = drv.phase === 'save' ? gripSteer(drv, car, v, car.x + dx, car.z + dz, DRIFT.saveKr, DRIFT.saveCap) : gripSteer(drv, car, v, car.x + dx, car.z + dz);
    const err = vt * DRIFT.carry - v;          // arrive a little quick: the flick scrubs speed
    if (err > -0.6) thr = clamp(0.55 + 0.4 * err, 0, 1); else brk = clamp(-(err + 0.6) * 0.25, 0, 0.8);
    if (ab > 8 * DEG && v > 8) thr *= 0.5;
    thr *= throttleGrip(car);
    if (drv.phase === 'save') {
      // unwind the slide on a steady throttle (a lift snaps the rear round); brake once it is straight
      const outward = drv.latRateF * car.lat > 0;          // heading for the edge it is nearer to
      thr = ab > 40 * DEG ? 0.25 : ab > 10 * DEG ? 0.45 : outward ? 0.15 : 0.6;
      brk = outward && v > 8 && ab < 6 * DEG ? 0.35 : 0;
    }
    if (car.gear === -1) { thr = 0; brk = 0; }
    return quantise(out, steerInputFor(car, delta), thr, brk, false, false);
  }
  // a hold that lost its slide flicks again
  if (drv.link && b < DRIFT.linkMin * DEG - 2 * DEG) { drv.phase = 'exit'; drv.timer = 0; drv.link = 0; }   // a link that lost its slide just ends
  if (drv.phase === 'hold' && !drv.link && b < 10 * DEG && b > -12 * DEG && drv.bT > 20 * DEG && v > 0.8 * vt && dir * car.yawRate < 0.6) { drv.phase = 'entry'; drv.timer = 0; return driftDrive(sim, drv, car, out, v); }
  // ---- hold and exit share the two loops ------------------------------------------------------
  const target = drv.phase === 'hold' ? (drv.link ? Math.min(drv.betaTarget, DRIFT.linkBeta * DEG) : drv.betaTarget) : 0;
  drv.bT += clamp(target - drv.bT, -0.9 * dt, 0.9 * dt);   // ramp the target (rad/s)
  if (drv.phase === 'exit') { drv.timer += dt; if (ab < 6 * DEG && drv.bT < 4 * DEG) { drv.phase = 'cruise'; } }
  // path: the velocity heading should turn at v*k_line, corrected toward the line (2nd-order,
  // natural frequency DRIFT.pathW, damping ~0.8), so the slide converges on the line without lurching
  pointAtS(T, car.s, PT);
  const i0 = PT.seg, i1 = (i0 + 1) % n, uu = PT.u;
  const latL = line.lat[i0] + (line.lat[i1] - line.lat[i0]) * uu;
  const hL = datan2(line.px[i1] - line.px[i0], line.pz[i1] - line.pz[i0]);
  const kL = meanK(T, line, car.s, clamp(v * DRIFT.kLead, 0, 12), clamp(v * (DRIFT.kLead + 0.3), 2, 22));
  const vs = v > 6 ? v : 6;
  const eY = clamp(latL - car.lat, -6, 6), eH = clamp(wrapPi(hL - vh), -0.6, 0.6);
  const pw = DRIFT.pathW;
  const wDes = v * kL + (2 * 0.8 * pw) * eH + (pw * pw / vs) * eY;   // desired d(heading)/dt
  // measured velocity-heading rate
  const wMeas = drv.kAct * v;
  const eK = dir * (wMeas - wDes) * v / G;                // + = turning tighter than the line wants (in g)
  // the slide angle gives way when the path is too tight (less angle = the thrust points along the
  // path) and grows when it runs wide; the throttle loop then restores speed and angle together
  // far inside the line (or near the inside edge) the angle may give a lot more: a shallower slide
  // beats the wall. Near the outside edge it may grow more, and the throttle backs off below.
  const inside = dir * (car.lat - latL);                  // m inside the line (toward the apex)
  const edgeIn = car.hw - dir * car.lat, edgeOut = car.hw + dir * car.lat;   // m to each edge
  const giveMax = DRIFT.trim + clamp(inside - 2, 0, 4) * 4 + clamp(2.5 - edgeIn, 0, 2.5) * 8;
  drv.bAdj += (clamp(-DRIFT.trimK * eK, -giveMax * DEG, DRIFT.trim * DEG) - drv.bAdj) * 0.03;
  const bT = drv.bT > 15 * DEG ? clamp(drv.bT + drv.bAdj, 12 * DEG, 46 * DEG) : drv.bT;
  // steering: yaw-rate PI; the slide angle settles because db/dt = dir * (r - w)
  const dv = u > 1 ? datan2(wv + car.yawRate * car.P.a, u) : 0;
  const bDot = -dir * car.slipRate;
  const bP = b + 0.22 * bDot;                           // where the angle is heading
  // yaw rate asked of the slide: proportional near the target, never more than the front can
  // brake again before the angle arrives (a constant-deceleration profile)
  const eb = bT - b, aeb = eb < 0 ? -eb : eb;
  const rAdd = Math.min(1.6 * aeb, Math.sqrt(2 * DRIFT.yawDecel * drv.gf * aeb));
  const rDes = wDes + dir * (eb < 0 ? -rAdd : rAdd);
  // the steering lags; act on where the yaw rate will be a moment from now
  const rDot = drv.rInit ? (car.yawRate - drv.rPrev) / dt : 0;
  drv.rPrev = car.yawRate; drv.rInit = true;
  drv.rDotF += (rDot - drv.rDotF) * 0.25;
  const er = rDes - (car.yawRate + 0.12 * drv.rDotF);
  // the front can only pull so hard: past its peak slip angle more lock only scrubs, so the
  // correction is capped there (and the integrator stops winding into the cap)
  const aCap = 1.25 * car.P.spec.tyre.alphaPeakDeg * DEG;
  const corr = 0.16 * er + drv.rI;
  if ((corr < aCap || er < 0) && (corr > -aCap || er > 0)) drv.rI = clamp(drv.rI + 0.35 * er * dt, -0.06, 0.06);
  delta = dv + clamp(corr, -aCap, aCap);
  // throttle: path curvature (turning tighter than wanted = more throttle, the slide widens)
  // (speed is the integrator in this loop, so it gets damping of its own)
  const aF = drv.vInit ? (v - drv.vPrev) / dt : 0;
  drv.vPrev = v; drv.vInit = true;
  drv.accF += (aF - drv.accF) * 0.08;
  drv.thrI = clamp(drv.thrI + DRIFT.ki * eK * dt, 0.05, 1);
  thr = clamp(drv.thrI + DRIFT.kp * eK - DRIFT.kd * drv.accF + 2.0 * clamp(bT - b - 8 * DEG, 0, 0.4), 0, 1);
  if (bP > bT + 12 * DEG) thr *= clamp(1 - (bP - bT - 12 * DEG) / (12 * DEG), 0, 1);   // over-rotating
  if (b < 0 && ab > 8 * DEG) thr = 0.3;                // sliding the wrong way: steer through it
  if (drv.phase === 'exit') thr = clamp(0.6 - 2 * (ab - 8 * DEG), 0.2, 1);
  if (v > vt + 6) brk = 0.2;
  if (edgeOut < 2) { thr *= clamp(edgeOut / 2, 0.2, 1); if (edgeOut < 1 && v > 0.9 * vt) brk = 0.3; }   // running out of road
  if (edgeIn < 1.5) thr = Math.max(thr, 0.8);
  if (v < 8) thr = Math.max(thr, 0.7);
  if (car.gear === -1) { thr = 0; brk = 0; }
  // a slide dying on grip (rear wheels hooking up, angle falling) gets a handbrake tap
  let hbTap = false;
  if (drv.hbCool > 0) drv.hbCool -= dt;
  if (drv.phase === 'hold') {
    const kR = 0.5 * (car.wheels[2].kappa + car.wheels[3].kappa);
    if (drv.hbTimer > 0) { drv.hbTimer -= dt; hbTap = true; }
    else if (drv.hbCool <= 0 && b > 8 * DEG && b < bT - DRIFT.tapGap * DEG && bDot < DRIFT.tapRate && kR < DRIFT.tapK) { drv.hbTimer = 0.14; drv.hbCool = 0.7; hbTap = true; }
  } else drv.hbTimer = 0;
  return quantise(out, steerInputFor(car, delta), thr, brk, hbTap, false);
}
