// Handling card (CONTRACT.md section 7): measures every window for the four cars on the fixture
// tracks and fails if any falls outside. Also: left/right symmetry, wheel-load conservation and the
// held-drift proof. docs/HANDLING-CARD.md records the numbers this prints.
//   node tests/handling.test.mjs           (about 10 s)
//   node tests/handling.test.mjs --json    (also prints the card as one JSON line)
// The test drivers below are harness code (not // loom:sim), so they may use Math.* freely; the
// sim only ever sees packed inputs, exactly like a player.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseTrack, createSim, step, packInput, CAR_IDS } from '../engine/sim.js';
import { placeOnTrack, steerInputFor, G } from '../engine/car.js';
import { pointAtS } from '../engine/track.js';
import { DRIFT_SETUPS } from '../engine/cars.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const load = id => parseTrack(readFileSync(ROOT + 'tests/fixtures/' + id + '.x3d', 'utf8'));
const STRIP = load('strip'), SKID = load('skidpad');

/** Card windows, straight from the contract. */
export const WINDOWS = {
  t100: { koi: [7.0, 9.0], ronin: [4.8, 6.2], tempest: [3.3, 4.3], banshee: [3.8, 5.0] },
  top: { koi: [185, 215], ronin: [230, 265], tempest: [245, 280], banshee: [275, 315] },
  brake: { koi: [33, 42], ronin: [33, 42], tempest: [32, 40], banshee: [33, 42] },
  skid: { koi: [0.90, 1.10], ronin: [0.92, 1.12], tempest: [1.00, 1.20], banshee: [0.90, 1.12] },
  wetRatio: [0.62, 0.80],
  drift: [25, 50], driftHold: 4.0,
};
/** The launch is measured with the Traction assist at 1 (launch control); the drift cars ship with it off. */
const LAUNCH_TUNE = { traction: 1 };
/** TEMPEST holds its slide on a drift setup a player can dial in (engine/cars.js DRIFT_SETUPS): assists off, torque rearward, front grip up. */
export const DRIFT_TUNES = DRIFT_SETUPS;

// ---- shared helpers ----------------------------------------------------------------------------
const STRAIGHT_S = 1500 + Math.PI * 250 + 5;     // the start of the strip's second (3 km) straight
function onStraight(id, tune, surface = 'dry') {
  const sim = createSim({ track: STRIP, mode: 'free', surface, entrants: [{ car: id, driver: 'player', tune }] });
  const car = sim.cars[0], P = {};
  pointAtS(STRIP, STRAIGHT_S, P);
  placeOnTrack(car, STRIP, P.x, P.z, Math.atan2(P.tx, P.tz), true);
  return { sim, car, s0: car.s };
}
/** Hold the straight with a plain lateral + heading + yaw-rate law. */
function laneSteer(car, T) {
  const herr = car.yaw - T.heading[car.seg];
  return Math.max(-127, Math.min(127, Math.round(car.lat * 25 + herr * 600 + car.yawRate * 60)));
}
function rollAt(car, v) {
  const sp = car.P.spec;
  car.vx = v * Math.sin(car.yaw); car.vz = v * Math.cos(car.yaw);
  for (const w of car.wheels) w.omega = v / car.P.R;
  let g = 6;
  while (g > 1 && v / car.P.R * sp.gears[g - 1] * car.tune.finalDrive * 30 / Math.PI < sp.redlineRpm * 0.75) g--;
  car.gear = g; car.clutch = 1; car.omegaE = Math.max(car.P.idle, v / car.P.R * sp.gears[g - 1] * car.tune.finalDrive);
}
const travelled = (T, s0, s) => { let d = s - s0; if (d < -1) d += T.L; return d; };

// ---- measures ----------------------------------------------------------------------------------
/** Standing start, full throttle: seconds to 100 km/h. */
export function zeroTo100(id, tune = LAUNCH_TUNE) {
  const { sim, car } = onStraight(id, tune);
  for (let i = 0; i < 120 * 20; i++) {
    step(sim, [packInput({ throttle: 15, steer: laneSteer(car, STRIP) })]);
    if (car.speed * 3.6 >= 100) return (i + 1) / 120;
  }
  return Infinity;
}
/** Top speed: two rolling starts, one below and one above, run 3 km flat out; they meet at the top. */
export function topSpeed(id) {
  const [lo, hi] = WINDOWS.top[id];
  const out = [];
  for (const kmh0 of [lo, hi + 15]) {
    const { sim, car, s0 } = onStraight(id, LAUNCH_TUNE);
    rollAt(car, kmh0 / 3.6);
    for (let i = 0; i < 120 * 60 && travelled(STRIP, s0, car.s) < 2990; i++) step(sim, [packInput({ throttle: 15, steer: laneSteer(car, STRIP) })]);
    out.push(car.speed * 3.6);
  }
  return { kmh: 0.5 * (out[0] + out[1]), spread: Math.abs(out[1] - out[0]) };
}
/** Steady 100 km/h, then full brake pedal (ABS): metres to a stop. */
export function brake100(id, surface = 'dry') {
  const { sim, car, s0 } = onStraight(id, {}, surface);
  rollAt(car, 100 / 3.6);
  for (let i = 0; i < 120 * 12; i++) {
    step(sim, [packInput({ brake: 15, steer: laneSteer(car, STRIP) })]);
    if (car.speed < 0.05) return travelled(STRIP, s0, car.s);
  }
  return Infinity;
}
/** Constant-radius skidpad: speed creeps up 0.2 m/s each second until the car can no longer hold the
 *  circle; the card value is the best 2 s mean of v^2/r while it still held (|slip| < 5.7 deg). */
export function skidpad(id, dir, surface = 'dry', tune = {}) {
  const T = SKID;
  let cx = 0, cz = 0;
  for (let i = 0; i < T.n; i++) { cx += T.x[i]; cz += T.z[i]; }
  cx /= T.n; cz /= T.n;
  const R = Math.hypot(T.x[0] - cx, T.z[0] - cz);
  const sim = createSim({ track: T, mode: 'free', surface, entrants: [{ car: id, driver: 'player', tune }] });
  const car = sim.cars[0];
  placeOnTrack(car, T, T.x[0], T.z[0], dir > 0 ? T.heading[0] : T.heading[0] + Math.PI, false);
  rollAt(car, 11);
  car.gear = 2; car.omegaE = 11 / car.P.R * car.P.spec.gears[1] * car.tune.finalDrive;
  // which way round the circle this heading goes (+1 = the centre is on the car's left)
  const lx = (cx - car.x) * Math.cos(car.yaw) - (cz - car.z) * Math.sin(car.yaw);
  const turn = lx > 0 ? 1 : -1;
  let vt = 11, best = 0, hold = 0;
  const acc = [];
  for (let i = 0; i < 120 * 120; i++) {
    const dx = car.x - cx, dz = car.z - cz, rad = Math.hypot(dx, dz), ang = Math.atan2(dx, dz);
    const Ld = Math.max(7, car.speed * 0.45);
    const a2 = ang + turn * Ld / R;
    const nx = cx + R * Math.sin(a2), nz = cz + R * Math.cos(a2);
    const ex = nx - car.x, ez = nz - car.z, c = Math.cos(car.yaw), s = Math.sin(car.yaw);
    const fwd = ex * s + ez * c, left = ex * c - ez * s;
    const delta = Math.atan(2 * left / (fwd * fwd + left * left) * car.P.L) - turn * 0.02 * (R - rad);
    const st = steerInputFor(car, delta);
    const err = vt - car.speed;
    step(sim, [packInput({ steer: st, throttle: Math.round(Math.max(0, Math.min(1, 0.3 + err * 0.4)) * 15), brake: err < -2 ? 4 : 0 })]);
    vt += 0.2 / 120;
    acc.push(car.speed * car.speed / Math.hypot(car.x - cx, car.z - cz)); if (acc.length > 240) acc.shift();
    const re = Math.abs(Math.hypot(car.x - cx, car.z - cz) - R);
    if (re < 2.0 && Math.abs(car.slip) < 0.10 && i > 240) {
      if (++hold > 240) { const m = acc.reduce((a, b) => a + b, 0) / acc.length; if (m > best) best = m; }
    } else hold = 0;
    if (re > 4) break;
  }
  return best / G;
}
/** The drift-mode AI (a closed loop on slip angle, yaw rate and path) on the skidpad: the longest
 *  stretch held inside the window, plus walls hit. */
export function heldDrift(id, secs = 40, tune = DRIFT_TUNES[id]) {
  const sim = createSim({ track: SKID, mode: 'free', entrants: [{ car: id, driver: 'ai', ai: 'drift', skill: 1, tune }] });
  const car = sim.cars[0];
  let run = 0, best = 0, walls = 0, resets = 0, sum = 0, n = 0;
  const [lo, hi] = WINDOWS.drift;
  for (let i = 0; i < 120 * secs; i++) {
    step(sim, []);
    for (const e of sim.race.events) { if (e.type === 'crash' && e.wall && e.impulse > 800) walls++; if (e.type === 'reset') resets++; }
    const deg = Math.abs(car.slip) * 180 / Math.PI;
    if (deg >= lo && deg <= hi && car.speed > 25 / 3.6) { run += 1 / 120; sum += deg; n++; if (run > best) best = run; } else run = 0;
  }
  return { best, walls, resets, meanDeg: n ? sum / n : 0 };
}
/** Mirrored manoeuvre (step steer, then a handbrake flick) left and right: peak yaw rate and slip. */
export function mirrored(id) {
  const one = sign => {
    const { sim, car } = onStraight(id, {});
    rollAt(car, 70 / 3.6);
    let peakR = 0, peakB = 0;
    for (let i = 0; i < 120 * 3; i++) {
      const t = i / 120;
      const steer = t < 0.5 ? laneSteer(car, STRIP) : sign * 90;
      step(sim, [packInput({ steer, throttle: t > 1.2 ? 10 : 4, handbrake: t > 1.0 && t < 1.3 })]);
      peakR = Math.max(peakR, Math.abs(car.yawRate)); peakB = Math.max(peakB, Math.abs(car.slip));
    }
    return { peakR, peakB, yaw: car.yawRate };
  };
  const L = one(-1), R = one(1);
  return { r: Math.abs(L.peakR - R.peakR) / Math.max(L.peakR, R.peakR), b: Math.abs(L.peakB - R.peakB) / Math.max(L.peakB, R.peakB), peakR: L.peakR, peakB: L.peakB };
}
/** Sum of the four wheel loads = m g cos(theta) + downforce, every tick, every wheel >= 5%. */
export function loadConservation(trackId, id) {
  const T = load(trackId);
  const sim = createSim({ track: T, mode: 'free', entrants: [{ car: id, driver: 'ai', ai: 'drift', skill: 1 }] });
  const car = sim.cars[0];
  let worst = 0, minFrac = 1, vPrev = 0;
  for (let i = 0; i < 120 * 25; i++) {
    step(sim, []);
    let sum = 0, mn = Infinity;
    for (const w of car.wheels) { sum += w.load; mn = Math.min(mn, w.load); }
    const expect = car.P.m * G * car.ny + 0.5 * 1.2 * car.P.spec.ClA * vPrev * vPrev;   // rho = 1.2 in engine/car.js
    worst = Math.max(worst, Math.abs(sum - expect) / expect);
    minFrac = Math.min(minFrac, mn / sum);
    vPrev = car.speed;
  }
  return { worst, minFrac };
}

// ---- run ---------------------------------------------------------------------------------------
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  let fails = 0;
  const card = {};
  const line = (ok, text) => { console.log(`${ok ? 'ok  ' : 'FAIL'} ${text}`); if (!ok) fails++; };
  const inW = (v, [a, b]) => v >= a && v <= b;
  for (const id of CAR_IDS) {
    const t100 = zeroTo100(id), t100Default = zeroTo100(id, {});
    const top = topSpeed(id);
    const br = brake100(id), brWet = brake100(id, 'wet');
    const skL = skidpad(id, 1), skR = skidpad(id, -1), skW = skidpad(id, 1, 'wet');
    const dr = heldDrift(id);
    const mir = mirrored(id);
    card[id] = { t100: +t100.toFixed(2), t100_traction_off: +t100Default.toFixed(2), top_kmh: +top.kmh.toFixed(1), brake_m: +br.toFixed(1), brake_wet_m: +brWet.toFixed(1),
      skid_g: +skL.toFixed(3), skid_right_g: +skR.toFixed(3), skid_wet_g: +skW.toFixed(3), wet_ratio: +(skW / skL).toFixed(3),
      drift_hold_s: +dr.best.toFixed(2), drift_mean_deg: +dr.meanDeg.toFixed(1), drift_walls: dr.walls, drift_tune: DRIFT_TUNES[id] };
    line(inW(t100, WINDOWS.t100[id]), `${id} 0-100 km/h ${t100.toFixed(2)} s (window ${WINDOWS.t100[id].join('-')}; traction off ${t100Default.toFixed(2)} s)`);
    line(inW(top.kmh, WINDOWS.top[id]) && top.spread < 3, `${id} top speed ${top.kmh.toFixed(1)} km/h (window ${WINDOWS.top[id].join('-')}; bracket spread ${top.spread.toFixed(1)})`);
    line(inW(br, WINDOWS.brake[id]), `${id} 100-0 km/h ${br.toFixed(1)} m (window ${WINDOWS.brake[id].join('-')}; wet ${brWet.toFixed(1)} m)`);
    line(inW(skL, WINDOWS.skid[id]), `${id} skidpad ${skL.toFixed(3)} g (window ${WINDOWS.skid[id].join('-')})`);
    line(inW(skW / skL, WINDOWS.wetRatio), `${id} wet/dry skidpad ${(skW / skL).toFixed(3)} (window ${WINDOWS.wetRatio.join('-')})`);
    line(Math.abs(skL - skR) / skL < 0.02 && mir.r < 0.02 && mir.b < 0.02, `${id} left/right symmetry: skidpad ${(100 * Math.abs(skL - skR) / skL).toFixed(2)}%, flick yaw ${(100 * mir.r).toFixed(2)}%, slip ${(100 * mir.b).toFixed(2)}%`);
    line(dr.best >= WINDOWS.driftHold && dr.walls === 0 && dr.resets === 0, `${id} held drift ${WINDOWS.drift.join('-')} deg for ${dr.best.toFixed(1)} s (mean ${dr.meanDeg.toFixed(0)} deg, ${dr.walls} wall hits${Object.keys(DRIFT_TUNES[id]).length ? ', drift setup ' + JSON.stringify(DRIFT_TUNES[id]) : ''})`);
  }
  for (const [trk, id] of [['oval', 'banshee'], ['twisty', 'koi'], ['oval', 'tempest']]) {
    const lc = loadConservation(trk, id);
    line(lc.worst < 1e-9 && lc.minFrac >= 0.05 - 1e-12, `${id} on ${trk}: wheel loads sum to m g cos(theta) + downforce (worst ${lc.worst.toExponential(1)}), lightest wheel ${(100 * lc.minFrac).toFixed(1)}%`);
  }
  // the four cars are clearly different: strictly ordered where the contract orders them
  const c = card;
  line(c.koi.t100 > c.ronin.t100 && c.ronin.t100 > c.banshee.t100 && c.banshee.t100 > c.tempest.t100, 'acceleration order KOI < RONIN < BANSHEE < TEMPEST');
  line(c.tempest.skid_g > c.ronin.skid_g && c.tempest.skid_g > c.koi.skid_g && c.tempest.skid_g > c.banshee.skid_g, 'TEMPEST has the most grip');
  line(c.banshee.top_kmh > c.tempest.top_kmh && c.tempest.top_kmh > c.ronin.top_kmh && c.ronin.top_kmh > c.koi.top_kmh, 'top speed order KOI < RONIN < TEMPEST < BANSHEE');
  if (process.argv.includes('--json')) console.log(JSON.stringify({ card }));
  console.log(JSON.stringify({ handling: fails === 0 ? 'pass' : 'fail', failed: fails }));
  process.exit(fails ? 1 : 0);
}
