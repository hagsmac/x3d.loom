// The Feel Card, measured: drive Nib in the feel lab level and gate each number against
// FEEL_WINDOWS (engine/feel.js). Prints one JSON line per measurement and exits 1 on any miss.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createGame, step, BTN } from '../engine/game.js';
import { FEEL, FEEL_WINDOWS, DT } from '../engine/feel.js';

const LAB = readFileSync(fileURLToPath(new URL('../levels/0-0-feel-lab.x3d', import.meta.url)), 'utf8');

function fresh(x, y) {
  const g = createGame(LAB);
  if (x !== undefined) { g.hero.x = x; g.hero.y = y; g.hero.px = x; g.hero.py = y; }
  for (let i = 0; i < 30; i++) step(g, 0); // settle on the ground
  return g;
}

function apex(holdFrames) {
  const g = fresh();
  const y0 = g.hero.y;
  let maxY = y0, t = 0, apexT = null;
  for (let i = 0; i < 240; i++) {
    step(g, i < holdFrames ? BTN.J : 0);
    if (g.hero.y > maxY) maxY = g.hero.y;
    if (apexT === null && i > 2 && g.hero.vy <= 0) apexT = (i + 1) * DT;
    t++;
  }
  return { height: maxY - y0, timeToApex: apexT };
}

function runJump() {
  const g = fresh(-25, 0.47);
  let i = 0;
  while (g.hero.x < -10) { step(g, BTN.R); i++; }
  const x0 = g.hero.x, y0 = g.hero.y;
  step(g, BTN.R | BTN.J);
  let airborne = false;
  for (let k = 0; k < 400; k++) {
    step(g, BTN.R | BTN.J);
    if (g.ground === null) airborne = true;
    if (airborne && g.ground !== null) return g.hero.x - x0;
  }
  return NaN;
  void y0;
}

function timeToFullSpeed() {
  const g = fresh();
  for (let i = 1; i < 200; i++) { step(g, BTN.R); if (g.hero.vx >= 0.98 * FEEL.runMax) return i * DT; }
  return NaN;
}

function stopDistance() {
  const g = fresh(-25, 0.47);
  for (let i = 0; i < 90; i++) step(g, BTN.R);
  const x0 = g.hero.x;
  for (let i = 0; i < 200; i++) { step(g, 0); if (Math.abs(g.hero.vx) < 0.05) return g.hero.x - x0; }
  return NaN;
}

/** Walk off the 2 m ledge (x 20..30) and press jump k frames after leaving it. */
function coyoteFrames() {
  let best = -1;
  for (let k = 1; k < 30; k++) {   // k = ticks after the first tick with no ground under Nib
    const g = fresh(26, 2.47);
    let left = -1, jumped = false;
    for (let i = 0; i < 200; i++) {
      const sinceLeft = left < 0 ? -1 : i - left;
      const bits = BTN.R | (sinceLeft === k ? BTN.J : 0);
      step(g, bits);
      if (left < 0 && g.ground === null && g.hero.x > 30) left = i;
      if (g.events.some(e => e.type === 'jump')) { jumped = true; break; }
    }
    if (jumped) best = k; else break;
  }
  return best;
}

/** Fall from 2 m and press jump k frames before the landing frame. */
function bufferFrames() {
  // first find the landing frame with no press
  const probe = fresh(10, 6);
  probe.events.length = 0;
  let landFrame = -1;
  for (let i = 0; i < 300; i++) { step(probe, 0); if (probe.ground) { landFrame = i; break; } }
  let best = -1;
  for (let k = 1; k < 40; k++) {
    const g = fresh(10, 6);
    let jumped = false;
    for (let i = 0; i < 300; i++) {
      step(g, i === landFrame - k ? BTN.J : 0);
      if (g.events.some(e => e.type === 'jump')) { jumped = true; break; }
    }
    if (jumped) best = k; else if (best >= 0) break;
  }
  return best;
}

function wallJumpHeight() {
  const g = fresh(46, 0.47);
  // jump at the wall (x = 50), slide, then wall-jump and measure the rise
  step(g, BTN.R | BTN.J);
  let i = 0;
  while (g.wall !== 1 && i < 200) { step(g, BTN.R | BTN.J); i++; }
  for (let k = 0; k < 10; k++) step(g, BTN.R);
  const y0 = g.hero.y;
  step(g, BTN.J);
  let maxY = y0;
  for (let k = 0; k < 120; k++) { step(g, BTN.J); maxY = Math.max(maxY, g.hero.y); }
  return maxY - y0;
}

const full = apex(240), tap = apex(1);
const measured = {
  apexHeightFull: full.height, apexHeightTap: tap.height, timeToApex: full.timeToApex,
  runJumpDistance: runJump(), timeToFullSpeed: timeToFullSpeed(), stopDistance: stopDistance(),
  coyoteFrames: coyoteFrames(), bufferFrames: bufferFrames(), wallJumpHeight: wallJumpHeight(),
};
let bad = 0;
for (const [k, [lo, hi]] of Object.entries(FEEL_WINDOWS)) {
  const v = measured[k];
  const ok = Number.isFinite(v) && v >= lo && v <= hi;
  if (!ok) bad++;
  console.log(JSON.stringify({ check: 'FEEL_' + k, value: +Number(v).toFixed(4), window: [lo, hi], status: ok ? 'pass' : 'fail' }));
}
console.log(JSON.stringify({ feel: bad ? 'fail' : 'pass', failed: bad, checks: Object.keys(FEEL_WINDOWS).length }));
process.exit(bad ? 1 : 0);
