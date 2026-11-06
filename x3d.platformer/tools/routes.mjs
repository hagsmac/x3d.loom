// Closed-loop routes, one per level. Each is a generator: it reads ctx.g (the game) and yields
// the button bits for the next tick. Helpers keep the routes readable.
import { BTN } from '../engine/game.js';

const { L, R, U, D, J, A } = BTN;

export function* hold(c, bits, n) { for (let i = 0; i < n; i++) yield bits; }

/** Run toward x (left or right) until reaching it; `extra` is ORed into every tick. */
export function* runTo(c, x, extra = 0) {
  const h = c.g.hero, dir = x > h.x ? R : L;
  let n = 0;
  while ((dir === R ? h.x < x : h.x > x) && n++ < 2400) yield dir | extra;
}

/** Stop moving: release until horizontal speed is small. */
export function* settle(c, n = 4) {
  const h = c.g.hero;
  let k = 0;
  while ((Math.abs(h.vx - c.g.groundVel[0]) > 0.3 || !c.g.ground) && k++ < 600) yield 0;
  yield* hold(c, 0, n);
}

/** Jump from the ground: hold jump for `holdT` ticks while pressing `dir`, keep `dir` until landing. */
export function* jump(c, dir, holdT = 60, airDir = dir, waitLand = true) {
  const g = c.g;
  yield dir;                                   // a tick without jump, so the press is an edge
  let i = 0;
  while (i < holdT) { yield dir | J; i++; if (i > 8 && g.ground) return; }
  let k = 0;
  while (waitLand && !g.ground && k++ < 1200) yield airDir;
}

/** Run to `x0`, then jump toward `dir`. */
export function* jumpFrom(c, x0, dir = R, holdT = 60, airDir = dir) {
  yield* runTo(c, x0);
  yield* jump(c, dir, holdT, airDir);
}

/** While airborne, press `bits` until `cond()` holds or the hero lands. */
export function* airUntil(c, bits, cond) {
  let k = 0;
  while (!c.g.ground && !cond() && k++ < 1200) yield bits;
}

/** Ground pound now (press down once), then wait for the landing. */
export function* pound(c) {
  yield 0; yield D;
  let k = 0;
  while (c.g.hs === 'pound' && k++ < 600) yield 0;
}

/** Wall climb in a shaft between two walls until the hero's feet are above `topY`. */
export function* wallClimb(c, topY, exitDir) {
  const g = c.g, h = g.hero;
  let k = 0, lastJump = -99;
  while (h.y - 0.47 < topY && k++ < 3000) {
    if (g.ground && h.y - 0.47 < topY - 1) { yield exitDir; yield exitDir | J; lastJump = k; continue; }
    if (g.wall !== 0 && g.frame - lastJump > 6 && h.vy < 3.5) { yield 0; yield J; lastJump = g.frame; continue; }
    const toward = g.wallLock > 0 ? (h.vx > 0 ? R : L) : (h.vx > 0 ? R : L);
    yield toward | J;
  }
}

/** Hold the hook near a ring and swing; release with a jump when `releaseWhen()` is true. */
export function* swing(c, dir, releaseWhen, maxT = 600) {
  const g = c.g;
  let k = 0;
  while (g.hs !== 'hook' && k++ < 120) yield A | dir;
  k = 0;
  while (g.hs === 'hook' && !releaseWhen() && k++ < maxT) yield A | dir;
  yield A | dir | J;
  yield dir;
}

/** Airborne: hold the hook toward each ring in turn; let go (jump) once past the ring by `rel` and rising. */
export function* hookChain(c, rings, rels, dir = R) {
  const g = c.g, h = g.hero;
  for (const [i, rg] of rings.entries()) {
    let k = 0;
    while (g.ring !== rg && k++ < 240) yield A | dir;
    c.mark('hook ' + rg.def);
    k = 0;
    while (g.ring === rg && !((dir === R ? h.x > rg.x + rels[i] : h.x < rg.x - rels[i]) && h.vy > 0) && k++ < 600) yield A | dir;
    yield A | dir | J;
  }
}

/** Wait (doing nothing) until cond() holds. */
export function* waitFor(c, cond, max = 2400) { let k = 0; while (!cond() && k++ < max) yield 0; }

/** One tick of gentle air steering toward x: press only while the speed toward it is below `vmax`. */
export function steer(c, x, vmax = 2.5, tol = 0.25) {
  const h = c.g.hero, dx = x - h.x;
  if (dx > tol) return h.vx < vmax ? R : 0;
  if (dx < -tol) return h.vx > -vmax ? L : 0;
  return h.vx > 0.6 ? L : h.vx < -0.6 ? R : 0;
}

/** Jump now and steer through the air to land near x = tx (no running start needed). */
export function* hop(c, tx, holdT = 40) {
  const g = c.g;
  yield 0;
  let i = 0;
  while (i < holdT) { yield J | steer(c, tx, 9); i++; if (i > 8 && g.ground) return; }
  let k = 0;
  while (!g.ground && k++ < 600) yield steer(c, tx, 9);
}

export const ROUTES = {
  '0-0': function* (c) { yield* runTo(c, 60); },

  '1-1': function* (c) {
    const g = c.g, h = g.hero;
    c.mark('start');
    yield* hold(c, 0, 20);
    yield* jumpFrom(c, 9.0, R, 40);              // onto the first stone step
    c.mark('step 1');
    yield* jumpFrom(c, 14.2, R, 40);             // second step
    c.mark('step 2');
    yield* jumpFrom(c, 22.6, R, 60);             // first gap
    c.mark('gap 1');
    yield* jumpFrom(c, 38.6, R, 60);             // second gap, up onto the crate meadow
    c.mark('gap 2');
    const crate = g.world.bodies.find(b => b.role === 'crate');
    let k = 0;
    while (crate.x < 55.3 && k++ < 1200) yield R;  // push the crate to the wall
    c.mark('crate at wall ' + crate.x.toFixed(2));
    yield* hold(c, R, 6);
    yield* jump(c, R, 50);                        // onto the crate
    c.mark('on crate');
    yield* settle(c, 2);
    yield* jump(c, R, 60);                        // onto the wall top
    c.mark('wall top');
    yield* runTo(c, 66.4);                        // the spring flings Nib up to the star ledge
    yield* airUntil(c, R, () => false);
    c.mark('star ledge');
    yield* runTo(c, 75.6);
    yield* settle(c, 1);
    yield* jump(c, R, 60, 0);                     // jump for the first golden gear
    c.mark('star 1 ' + g.stars[0]);
    yield* runTo(c, 80);                          // drop off, checkpoint
    yield* runTo(c, 99);                          // over the hanging bridge
    c.mark('bridge crossed');
    yield* runTo(c, 110.6);
    yield* jump(c, R, 12, R, false);
    yield* airUntil(c, R, () => h.x > 113.0);
    yield* pound(c);                              // through the cracked stone
    c.mark('pounded, cave');
    let j = 0;
    while (!g.ground && j++ < 600) yield 0;
    yield* runTo(c, 116.2);
    yield* settle(c, 1);
    yield* jump(c, 0, 60, 0);                     // second golden gear, in the cave
    c.mark('star 2 ' + g.stars[1]);
    yield* runTo(c, 126.3);                       // the spring out of the cave
    yield* airUntil(c, R, () => false);
    c.mark('out of cave');
    yield* runTo(c, 136.6);                       // up onto the seesaw's high end
    yield* jump(c, R, 40);
    c.mark('on seesaw');
    yield* runTo(c, 144.0);
    yield* jump(c, R, 60);                        // over the crate
    c.mark('past seesaw');
    yield* runTo(c, 169.4);                       // into the chimney
    c.mark('chimney');
    yield* jump(c, R, 30);
    yield* wallClimb(c, 12.8, R);
    c.mark('climbed');
    yield* airUntil(c, R, () => false);
    yield* runTo(c, 186);
    c.mark('goal');
    k = 0;
    while (g.state !== 'won' && k++ < 600) yield R;
  },

  '2-1': function* (c) {
    const g = c.g, h = g.hero;
    const movers = g.world.bodies.filter(b => b.role === 'mover').sort((a, b) => a.x - b.x);
    const wrecker = g.world.bodies.find(b => b.role === 'wrecker');
    const rings = g.entities.filter(e => e.kind === 'ring').sort((a, b) => a.x - b.x);
    c.mark('start');
    yield* hold(c, 0, 20);
    yield* runTo(c, 15.3);                        // A. the first ring
    yield* jump(c, R, 24, R, false);
    yield* hookChain(c, [rings[0]], [3.0]);
    yield* airUntil(c, R, () => false);
    c.mark('chasm 1');
    yield* runTo(c, 39.2); yield* settle(c, 1);   // B. ride the lift: jump as it comes back
    yield* waitFor(c, () => movers[0].x < 46.3 && movers[0].vx < 0);
    yield* jump(c, R, 16, R); yield* settle(c, 1);
    c.mark('on lift');
    yield* waitFor(c, () => movers[0].x > 56.2);
    yield* jump(c, R, 40, R);
    c.mark('off lift');
    yield* runTo(c, 75.5); yield* settle(c, 1);   // C. go just after the wrecking ball swings past
    yield* waitFor(c, () => wrecker.vx > 0 && wrecker.x > 80);
    yield* runTo(c, 83.0);
    yield* jump(c, R, 60, R);                     // over the crumbling middle, through the golden gear
    c.mark('bridge, star 1 ' + g.stars[0]);
    yield* runTo(c, 111.2);                       // D. the ring chain; a late release from the last ring
    yield* jump(c, R, 24, R, false);
    yield* hookChain(c, rings.slice(1, 4), [2.0, 2.0, 3.0]);
    yield* airUntil(c, R, () => false);
    c.mark('chain, star 2 ' + g.stars[1]);
    yield* runTo(c, 149.3);                       // E. the ring over the spike pit
    yield* jump(c, R, 24, R, false);
    yield* hookChain(c, [rings[4]], [3.0]);
    yield* airUntil(c, R, () => false);
    c.mark('spike pit');
    const lift = movers[1];                       // F. the cliff lift: hop on as it comes down
    yield* runTo(c, 173.0); yield* settle(c, 1);
    yield* waitFor(c, () => lift.vy < 0 && lift.y < 1.6 && lift.y > 1.0);
    yield* jump(c, R, 10, R); yield* settle(c, 1);
    c.mark('on lift 2');
    yield* waitFor(c, () => lift.y > 9.5);
    yield* runTo(c, 180.4);                       // the spring to the third golden gear
    yield* airUntil(c, R, () => false);
    c.mark('star 3 ' + g.stars[2]);
    yield* runTo(c, 194);
    let k = 0;
    while (g.state !== 'won' && k++ < 600) yield R;
  },
  '3-1': function* (c) {
    const g = c.g, h = g.hero;
    const spin = g.world.bodies.filter(b => b.role === 'spinner').sort((a, b) => a.x - b.x);
    const flat = b => ((b.a % Math.PI) + Math.PI) % Math.PI;   // 0 when the arm is level
    const ring = g.entities.find(e => e.kind === 'ring');
    let k;
    c.mark('start');
    yield* hold(c, 0, 20);
    yield* runTo(c, 16.0);                                      // A. ride the fan up
    k = 0; while (k++ < 400 && h.y < 9.6) yield steer(c, 17);
    k = 0; while (k++ < 300 && !g.stars[0] && h.y > 7) yield steer(c, 15.0, 4);   // drift off the top for star 1
    c.mark('star 1 ' + g.stars[0]);
    k = 0; while (k++ < 400 && !(h.y > 9.6 && h.x > 17.7)) yield steer(c, 18.0, 3);
    k = 0; while (!g.ground && k++ < 900) yield steer(c, 23, 7);
    c.mark('first ledge');
    yield* runTo(c, 27.3); yield* settle(c, 1);                 // B. hop the turning arms in rhythm
    yield* waitFor(c, () => Math.abs(flat(spin[0]) - (Math.PI - 0.9)) < 0.02);
    yield* hop(c, 32.5); c.mark('arm 1');
    yield* hop(c, 39.4); c.mark('arm 2');
    yield* hop(c, 45.5); c.mark('arms crossed');
    yield* runTo(c, 49.9); yield* settle(c, 1);                 // C. the crumbling ladder, no stopping
    yield* hop(c, 52.2); yield* hop(c, 56.2); yield* hop(c, 60.2); yield* hop(c, 64.0);
    c.mark('ladder');
    yield* runTo(c, 68.0);                                      // D. the wall-jump shaft
    yield* jump(c, R, 30);
    yield* wallClimb(c, 32.8, R);
    k = 0; while (!g.ground && k++ < 600) yield steer(c, h.x < 67.9 ? 65.7 : 71, 6);
    if (h.x > 67.9) { yield* runTo(c, 70.0); yield* settle(c, 1); yield* hop(c, 65.7); }
    c.mark('star 2 ' + g.stars[1]);
    yield* settle(c, 1);
    yield* hop(c, 71);
    yield* runTo(c, 77.3);                                      // E. the last ring: a late release for star 3
    yield* jump(c, R, 24, R, false);
    yield* hookChain(c, [ring], [4.3]);
    yield* airUntil(c, R, () => false);
    c.mark('star 3 ' + g.stars[2]);
    yield* runTo(c, 97);
    k = 0;
    while (g.state !== 'won' && k++ < 600) yield R;
  },
};
