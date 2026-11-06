// A keyboard player can drift every car (CONTRACT.md section 7, assists). The driver here presses
// only what a keyboard has: steer -127 / 0 / +127, throttle 0 or full, a handbrake tap. Its rules
// are the ones a person uses: flick in with the handbrake, hold the gas, tap into the corner when
// the angle fades, tap out (and lift) when it grows too far, lift when the car runs wide. It
// decides every 10 ticks (a key is held at least ~80 ms) on the angle a quarter second ahead.
//   node tests/keyboard.test.mjs        (about 6 s)
// Checks, on the Practice Pad with each car's shipped assists, dry and wet, 95 s of Drift Rush:
// the car is drifting for most of the run, never spins (|slip| > 80 deg), never hits a wall;
// with Stability and Drift assist off the pro car (BANSHEE) spins, with them on it does not.
// This is a test harness, not sim code: it may use Math.* freely.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseTrack, createSim, step, packInput, CAR_IDS } from '../engine/sim.js';
import { pointAtS } from '../engine/track.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const DEG = Math.PI / 180;
const PAD = parseTrack(readFileSync(ROOT + 'levels/practice-pad.x3d', 'utf8'));
const wrap = a => { while (a > Math.PI) a -= 2 * Math.PI; while (a < -Math.PI) a += 2 * Math.PI; return a; };

/** Drive one car with keys for `secs`; returns drift share, mean drift angle, spins, wall hits, score. */
export function keyboardRun(car, { track = PAD, surface = 'dry', tune = {}, secs = 95, lo = 22, hi = 42 } = {}) {
  const T = track, P = {};
  const sim = createSim({ track: T, mode: 'rush', surface, entrants: [{ car, driver: 'player', tune }] });
  const c = sim.cars[0];
  const kAhead = (s, d) => { let m = 0; for (let x = 4; x <= d; x += 4) { pointAtS(T, s + x, P); const k = T.kappaS[P.seg]; if (Math.abs(k) > Math.abs(m)) m = k; } return m; };
  let held = { steer: 0, thr: 0 }, bPrev = 0, bDot = 0, hb = 0, cool = 0;
  let drift = 0, sum = 0, spins = 0, spinning = false, walls = 0, presses = 0, prevSteer = 0;
  const N = 120 * secs;
  for (let i = 0; i < N; i++) {
    const kA = kAhead(c.s, 30), k = Math.abs(kA) > 1 / 300 ? kA : T.kappaS[c.seg];
    const dir = k > 0 ? 1 : -1, corner = Math.abs(k) > 1 / 250;
    const b = -dir * c.slip / DEG;                         // slide angle in the corner's frame (+ = a proper slide)
    bDot = 0.8 * bDot + 0.2 * (b - bPrev) * 120; bPrev = b;
    const outside = -dir * c.lat;                          // m toward the outside of the corner
    pointAtS(T, c.s + 12 + c.speed * 0.4, P);
    const want = Math.atan2(P.x - c.x, P.z - c.z);
    const he = wrap(want - c.yaw), ve = wrap(want - Math.atan2(c.vx, c.vz));
    let steer = 0, thr = 15;
    if (c.speed < 10 || (Math.abs(c.slip) < 10 * DEG && !(corner && c.speed > 14))) {
      steer = he > 0.03 ? -127 : he < -0.03 ? 127 : 0;     // grip driving toward the road ahead
      thr = c.speed < 22 ? 15 : 0;
    } else if (Math.abs(c.slip) < 10 * DEG) {
      steer = -dir * 127;                                  // initiation: steer in, tap the handbrake
      if (cool <= 0 && c.speed > 12) { hb = 0.22; cool = 1.2; }
    } else {
      const bp = b + bDot * 0.3;                           // where the angle is heading
      if (b < -5) { steer = -dir * 127; thr = 0; }         // swung the wrong way: steer into it, lift
      else if (bp > hi) { steer = dir * 127; thr = bp > hi + 15 ? 0 : 15; }
      else if (bp < lo) steer = -dir * 127;
      if (outside > c.hw - 2.5 && bp < hi) steer = -dir * 127;
      const wide = ve * dir;                               // the road bends away from where the car goes
      if (b >= -5 && bp < hi + 15) { if (wide > 0.12 + 0.02 * (c.hw - outside)) thr = 0; else if (wide < -0.12 && bp > lo) steer = dir * 127; }
      if (!corner && Math.abs(c.slip) < 25 * DEG) { steer = he > 0.04 ? -127 : he < -0.04 ? 127 : 0; thr = Math.abs(c.slip) > 15 * DEG ? 0 : 15; }
    }
    if (i % 10 === 0) held = { steer, thr }; else { steer = held.steer; thr = held.thr; }
    const hand = hb > 0; if (hb > 0) hb -= 1 / 120; if (cool > 0) cool -= 1 / 120;
    if (steer !== prevSteer && steer !== 0) presses++; prevSteer = steer;
    step(sim, [packInput({ steer, throttle: thr, handbrake: hand })]);
    for (const e of sim.race.events) if (e.type === 'crash' && e.wall && e.impulse > 800) walls++;
    const ab = Math.abs(c.slip) / DEG;
    if (ab > 80 && !spinning) { spins++; spinning = true; } else if (ab < 30) spinning = false;
    if (c.drifting) { drift++; sum += ab; }
  }
  return { drift: drift / N, meanDeg: drift ? sum / drift : 0, spins, walls, presses: presses / secs, score: Math.round(sim.race.score), medal: sim.race.medal };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  let fails = 0, count = 0;
  const line = (ok, text) => { count++; if (!ok) fails++; console.log(`${ok ? 'ok  ' : 'FAIL'} ${text}`); };
  const fmt = r => `drifting ${(100 * r.drift).toFixed(0)}% at ${r.meanDeg.toFixed(1)} deg, ${r.spins} spins, ${r.walls} walls, ${r.presses.toFixed(1)} steer presses/s, rush ${r.score} (${r.medal})`;
  const card = {};
  for (const surface of ['dry', 'wet']) for (const id of CAR_IDS) {
    const r = keyboardRun(id, { surface });
    card[id + '_' + surface] = { drift: +r.drift.toFixed(3), meanDeg: +r.meanDeg.toFixed(1), spins: r.spins, walls: r.walls, score: r.score, medal: r.medal };
    // TEMPEST is the grip car (AWD, Traction and Stability on): it slides, but less of the time
    const need = id === 'tempest' ? 0.35 : 0.5;
    line(r.drift >= need && r.spins === 0 && r.walls === 0, `${id} ${surface}, shipped assists, keys only: ${fmt(r)} (needs ${100 * need}% drifting, no spin, no wall)`);
  }
  const off = keyboardRun('banshee', { tune: { stability: 0, driftAssist: 0 } });
  const on = keyboardRun('banshee');
  card.banshee_assists_off = { drift: +off.drift.toFixed(3), meanDeg: +off.meanDeg.toFixed(1), spins: off.spins };
  line(off.spins > on.spins, `banshee with Stability and Drift assist off spins (${off.spins}) where the shipped assists do not (${on.spins}): ${fmt(off)}`);
  console.log(JSON.stringify({ card }));
  console.log(JSON.stringify({ keyboard: fails ? 'fail' : 'pass', checks: count, failed: fails }));
  process.exit(fails ? 1 : 0);
}
