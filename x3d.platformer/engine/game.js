// loom:sim
// The game as a pure function of (level bytes, input tape): step(g, bits) advances one 1/120 s
// tick. Nothing here reads a clock, the DOM, or Math.random, so Node and the browser replay a
// tape to the same state hash. The renderer only reads `g` and drains `g.events`.

import { createWorld, addBody, addRevolute, addRope, removeJoint, stepWorld, contactsOf,
  pointVelocity, setKind, setTransform, setEnabled } from './physics.js';
import { readLevel } from './x3d.js';
import { FEEL as F, DT } from './feel.js';

export const BTN = { L: 1, R: 2, U: 4, D: 8, J: 16, A: 32 };
export const ENGINE_VERSION = 'nib-engine/2';  // 2: a just-released ring cannot be re-grabbed for 0.5 s (ring chains)

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export function createGame(levelText) {
  const L = readLevel(levelText);
  const P = L.params;
  const world = createWorld({ gravity: L.gravity, iterations: L.iterations });
  const g = {
    L, P, world, byDef: new Map(), frame: 0, time: 0, state: 'play', hs: 'normal',
    prevBits: 0, events: [], hitstop: 0,
    hero: null, facing: 1, ground: null, groundVel: [0, 0], groundPt: [0, 0], wall: 0, ceiling: false,
    airT: 0, coyote: 0, jumpBuf: 0, jumping: false, launched: false, wallLock: 0, hookCd: 0,
    poundT: 0, rope: null, ring: null, lastRing: null, lastRingT: 0, deadT: 0, prevVy: 0,
    cogs: 0, cogsTotal: 0, stars: [], deaths: 0, checkpoint: null, wonFrame: -1, combo: 0, comboT: 0,
    entities: [], movers: [], crumbles: [], respawnables: [], debris: [], debrisNext: 0, winds: [],
  };

  for (const d of L.bodies) {
    const m = d.meta;
    const kind = d.fixed ? 'static' : (m.kinematic ? 'kinematic' : 'dynamic');
    const ghost = !!m.ghost;
    const b = addBody(world, {
      name: d.def, role: m.role || (d.fixed ? 'solid' : 'crate'), shape: d.shape, hx: d.hx, hy: d.hy, r: d.r,
      x: d.x, y: d.y, a: d.a, vx: d.vx, vy: d.vy, w: d.w, kind, mass: d.mass,
      friction: m.friction ?? 0.7, restitution: m.restitution ?? 0, angDamp: m.angDamp ?? 0.05, linDamp: m.linDamp ?? 0,
      cat: ghost ? 0 : 1, mask: ghost ? 0 : 0xffff, data: { home: [d.x, d.y, d.a], meta: m },
    });
    g.byDef.set(d.def, b);
    if (m.path) {
      const path = L.paths[m.path];
      if (!path) throw new Error(`mover ${d.def}: no PositionInterpolator ${m.path}`);
      g.movers.push({ b, path, period: m.period || 4, phase: m.phase || 0 });
    }
    if (b.role === 'crumble') g.crumbles.push({ b, phase: 'solid', t: 0 });
    if (m.respawn) g.respawnables.push(b);
  }
  for (const j of L.joints) {
    const b1 = g.byDef.get(j.body1), b2 = g.byDef.get(j.body2);
    if (!b1 || !b2) throw new Error(`joint between ${j.body1} and ${j.body2}: body not found`);
    addRevolute(world, b1, b2, j.x, j.y, { softness: j.meta.softness ?? 0 });
  }
  const start = P.start || [0, 2];
  g.hero = addBody(world, { name: 'HERO', role: 'hero', shape: 'box', hx: F.heroHx, hy: F.heroHy,
    x: start[0], y: start[1], mass: F.heroMass, friction: 0, fixedRotation: true, gravityScale: 0, cat: 2, mask: 1 });
  g.checkpoint = { x: start[0], y: start[1], idx: -1 };

  for (const e of L.entities) {
    const ent = { ...e, px: e.x, py: e.y, taken: false, active: false, t: 0 };
    if (e.kind === 'cog') g.cogsTotal++;
    if (e.kind === 'star') { ent.starIdx = g.stars.length; g.stars.push(false); }
    if (e.kind === 'ring') ent.body = addBody(world, { name: e.def + '_anchor', role: 'anchor', shape: 'circle', r: 0.2,
      x: e.x, y: e.y, kind: 'static', cat: 0, mask: 0 });
    if (e.kind === 'wind') g.winds.push(ent);
    g.entities.push(ent);
  }
  for (let i = 0; i < 12; i++) {
    g.debris.push({ b: addBody(world, { name: 'DEBRIS_' + i, role: 'debris', shape: 'box', hx: 0.2, hy: 0.2, mass: 0.3,
      x: 0, y: -1000, enabled: false, cat: 4, mask: 1, friction: 0.8 }), life: 0 });
  }
  return g;
}

function ev(g, type, x, y, extra) {
  g.events.push({ type, x, y, frame: g.frame, ...extra });
  if (g.events.length > 512) g.events.splice(0, g.events.length - 512);
}

// --- sensing ---------------------------------------------------------------------------------

function overlapsSolid(g, x0, y0, x1, y1) {
  for (const b of g.world.bodies) {
    if (!b.enabled || b.cat !== 1 || (b.data && b.data.meta && b.data.meta.nowall)) continue;
    let bx0, by0, bx1, by1;
    if (b.shape === 'circle') { bx0 = b.x - b.r; bx1 = b.x + b.r; by0 = b.y - b.r; by1 = b.y + b.r; }
    else {
      const ex = Math.abs(b.c) * b.hx + Math.abs(b.s) * b.hy, ey = Math.abs(b.s) * b.hx + Math.abs(b.c) * b.hy;
      bx0 = b.x - ex; bx1 = b.x + ex; by0 = b.y - ey; by1 = b.y + ey;
    }
    if (x1 > bx0 && x0 < bx1 && y1 > by0 && y0 < by1) return true;
  }
  return false;
}

function senseHero(g) {
  const h = g.hero;
  const was = g.ground;
  let best = null, bestNy = 0.55;
  g.ceiling = false;
  for (const c of contactsOf(g.world, h)) {
    if (c.ny > bestNy) { bestNy = c.ny; best = c; }
    if (c.ny < -0.7 && c.Pn > 0) g.ceiling = true;
  }
  if (best) {
    const gv = pointVelocity(best.other, best.x, best.y);
    if (h.vy - gv[1] > 1.0) best = null;   // moving away from it: this step's jump, not a landing
    else { g.groundVel = gv; g.groundPt = [best.x, best.y]; }
  }
  g.ground = best ? best.other : null;
  if (!g.ground) g.groundVel = [0, 0];
  const y0 = h.y - F.heroHy * 0.55, y1 = h.y + F.heroHy * 0.55;
  g.wall = 0;
  if (!g.ground) {
    if (overlapsSolid(g, h.x - F.heroHx - F.wallProbe, y0, h.x - F.heroHx + 0.02, y1)) g.wall = -1;
    else if (overlapsSolid(g, h.x + F.heroHx - 0.02, y0, h.x + F.heroHx + F.wallProbe, y1)) g.wall = 1;
  }
  if (g.ground && !was && g.airT > 0.08) ev(g, 'land', h.x, h.y - F.heroHy, { speed: -g.prevVy });
  g.airT = g.ground ? 0 : g.airT + DT;
}

// --- hero control ----------------------------------------------------------------------------

function nearestRing(g) {
  const h = g.hero;
  let best = null, bd = F.hookRange * F.hookRange;
  for (const e of g.entities) {
    if (e.kind !== 'ring' || e.y < h.y - 0.8 || (e === g.lastRing && g.lastRingT > 0)) continue;
    const dx = e.x - h.x, dy = e.y - h.y, d2 = dx * dx + dy * dy;
    if (d2 < bd) { bd = d2; best = e; }
  }
  return best;
}

function attach(g, ring) {
  const h = g.hero;
  const dx = h.x - ring.x, dy = h.y - ring.y;
  const len = clamp(Math.sqrt(dx * dx + dy * dy), F.hookMin, F.hookRange);
  g.rope = addRope(g.world, ring.body, h, 0, 0, 0, 0, len);
  g.ring = ring; g.hs = 'hook'; g.jumping = false; g.launched = false;
  ev(g, 'hook', ring.x, ring.y, { len });
}

function detach(g, jumped) {
  if (!g.rope) return;
  removeJoint(g.world, g.rope);
  const h = g.hero;
  if (jumped) { h.vy = Math.max(h.vy, 0) + F.hookBoost; h.vx *= 1.08; g.launched = true; }
  ev(g, 'unhook', h.x, h.y, { jumped: !!jumped });
  g.lastRing = g.ring; g.lastRingT = 0.5;
  g.rope = null; g.ring = null; g.hs = 'normal';
  g.hookCd = jumped ? F.hookCooldown : F.hookCooldown * 0.5;
}

function controlHero(g, bits, pressed) {
  const h = g.hero, onGround = g.ground !== null;
  const dir = ((bits & BTN.R) ? 1 : 0) - ((bits & BTN.L) ? 1 : 0);
  const held = (bits & BTN.J) !== 0;
  if (dir && g.wallLock <= 0) g.facing = dir;
  g.coyote = onGround ? F.coyote : Math.max(0, g.coyote - DT);
  g.jumpBuf = (pressed & BTN.J) ? F.buffer : Math.max(0, g.jumpBuf - DT);
  g.wallLock = Math.max(0, g.wallLock - DT);
  g.hookCd = Math.max(0, g.hookCd - DT);
  g.lastRingT = onGround ? 0 : Math.max(0, g.lastRingT - DT);

  if (g.hs === 'hook') {
    if (!(bits & BTN.A) || (pressed & BTN.J)) { detach(g, (pressed & BTN.J) !== 0); if (g.hs === 'normal') g.jumpBuf = 0; }
    else {
      const r = g.ring, dx = h.x - r.x, dy = h.y - r.y, len = Math.sqrt(dx * dx + dy * dy) || 1;
      const px = -dy / len, py = dx / len;
      if (dir) { h.vx += dir * F.hookPump * px * DT; h.vy += dir * F.hookPump * py * DT; }
      if (bits & BTN.U) g.rope.maxLen = Math.max(F.hookMin, g.rope.maxLen - F.hookReel * DT);
      if (bits & BTN.D) g.rope.maxLen = Math.min(F.hookRange, g.rope.maxLen + F.hookReel * DT);
      h.vy -= F.gravity * DT;
      h.vy = Math.max(h.vy, -F.maxFall);
      return;
    }
  }
  if (g.hs === 'pound') {
    g.poundT -= DT;
    h.vx = 0; h.vy = g.poundT > 0 ? 0 : -F.poundV;
    return;
  }
  if ((bits & BTN.A) && !onGround && g.hookCd <= 0) {
    const ring = nearestRing(g);
    if (ring) { attach(g, ring); return; }
  }

  const gv = onGround ? g.groundVel : [0, 0];
  const base = gv[0];
  const rel = h.vx - base;
  let accel;
  if (onGround) accel = dir === 0 ? F.groundDecel : (rel * dir < -0.2 ? F.turnAccel : F.groundAccel);
  else accel = dir === 0 ? F.airDrag : (rel * dir < 0 ? F.airAccel * 1.25 : F.airAccel);
  if (Math.abs(rel) > F.runMax && (dir === 0 || rel * dir > 0) && !onGround) accel = F.overspeedDrag;
  if (g.wallLock > 0) accel *= 0.2;
  h.vx += clamp(dir * F.runMax + base - h.vx, -accel * DT, accel * DT);

  if (g.jumpBuf > 0 && g.coyote > 0) {
    h.vy = F.jumpV + Math.max(0, gv[1]);
    g.coyote = 0; g.jumpBuf = 0; g.jumping = true; g.launched = false;
    ev(g, 'jump', h.x, h.y - F.heroHy);
  } else if (g.jumpBuf > 0 && !onGround && g.wall !== 0) {
    h.vx = -g.wall * F.wallJumpVx; h.vy = F.wallJumpVy;
    g.facing = -g.wall; g.wallLock = F.wallLock; g.jumpBuf = 0; g.jumping = true; g.launched = false;
    ev(g, 'walljump', h.x + g.wall * F.heroHx, h.y, { side: g.wall });
  }

  let gm = 1;
  if (h.vy < 0) { gm = F.fallMul; g.jumping = false; g.launched = false; }
  else if (g.jumping && !held) gm = F.cutMul;
  if (g.jumping && held && Math.abs(h.vy) < F.apexV) gm *= F.apexMul;
  h.vy -= F.gravity * gm * DT;
  if (onGround && gv[1] < 0 && !g.jumping) h.vy = Math.min(h.vy, gv[1]);
  if (!onGround && g.wall !== 0 && dir === g.wall && h.vy < -F.wallSlide) h.vy = Math.max(h.vy, -F.wallSlide);
  h.vy = Math.max(h.vy, -F.maxFall);

  if ((pressed & BTN.D) && !onGround) {
    g.hs = 'pound'; g.poundT = F.poundHover; h.vx = 0; h.vy = 0; g.jumping = false;
    ev(g, 'poundstart', h.x, h.y);
  }
}

// --- world rules -----------------------------------------------------------------------------

function samplePath(path, t) {
  const k = path.key, p = path.pts;
  if (t <= k[0]) return p[0];
  for (let i = 1; i < k.length; i++) {
    if (t <= k[i]) { const u = (t - k[i - 1]) / (k[i] - k[i - 1]); return [p[i - 1][0] + u * (p[i][0] - p[i - 1][0]), p[i - 1][1] + u * (p[i][1] - p[i - 1][1])]; }
  }
  return p[p.length - 1];
}

function updateMovers(g) {
  for (const m of g.movers) {
    const T = m.period;
    const t = ((g.time + m.phase * T) % T) / T;
    const [tx, ty] = samplePath(m.path, t);
    m.b.vx = (tx - m.b.x) / DT; m.b.vy = (ty - m.b.y) / DT;
  }
}

function heroOverlaps(g, x, y, hx, hy) {
  const h = g.hero;
  return Math.abs(h.x - x) < hx + F.heroHx && Math.abs(h.y - y) < hy + F.heroHy;
}

function updateCrumbles(g) {
  for (const c of g.crumbles) {
    const b = c.b;
    if (c.phase === 'solid') {
      if (g.ground === b) { c.phase = 'shake'; c.t = 0.45; ev(g, 'shake', b.x, b.y, { name: b.name }); }
    } else if (c.phase === 'shake') {
      c.t -= DT;
      if (c.t <= 0) { setKind(g.world, b, 'dynamic', 2.5); b.vy = -0.5; c.phase = 'fall'; c.t = 2.0; ev(g, 'crumble', b.x, b.y, { name: b.name }); }
    } else if (c.phase === 'fall') {
      c.t -= DT;
      if (c.t <= 0 || b.y < (g.P.killY ?? -20)) { setEnabled(g.world, b, false); c.phase = 'gone'; c.t = 1.4; }
    } else if (c.phase === 'gone') {
      c.t -= DT;
      const [hx, hy, ha] = b.data.home;
      if (c.t <= 0 && !heroOverlaps(g, hx, hy, b.hx, b.hy)) {
        setKind(g.world, b, 'static'); setTransform(g.world, b, hx, hy, ha); setEnabled(g.world, b, true);
        c.phase = 'solid'; ev(g, 'restore', hx, hy, { name: b.name });
      }
    }
  }
}

function breakBlock(g, b) {
  setEnabled(g.world, b, false);
  for (let i = 0; i < 4; i++) {
    const d = g.debris[g.debrisNext]; g.debrisNext = (g.debrisNext + 1) % g.debris.length;
    const sx = i & 1 ? 1 : -1, sy = i & 2 ? 1 : -1;
    setTransform(g.world, d.b, b.x + sx * b.hx * 0.5, b.y + sy * b.hy * 0.5, 0);
    setEnabled(g.world, d.b, true);
    d.b.vx = sx * (2.5 + i * 0.4); d.b.vy = 4 + (sy > 0 ? 3 : 0); d.b.w = sx * -7;
    d.life = 2.2;
  }
  ev(g, 'break', b.x, b.y, { name: b.name });
}

function poundLand(g) {
  const h = g.hero, fx = h.x, fy = h.y - F.heroHy;
  g.hs = 'normal';
  g.hitstop = F.hitstop;
  if (g.ground && g.ground.role === 'cracked') breakBlock(g, g.ground);
  let moved = 0;
  for (const b of g.world.bodies) {
    if (!b.enabled || b.kind !== 'dynamic' || b === h || b === g.ground || b.cat !== 1) continue;
    const dx = b.x - fx, dy = b.y - fy, d = Math.sqrt(dx * dx + dy * dy);
    if (d > F.poundRadius) continue;
    const k = 1 - d / F.poundRadius;
    b.vy += F.poundKick * k; b.vx += (dx >= 0 ? 1 : -1) * F.poundKick * 0.45 * k; b.w += (dx >= 0 ? -1 : 1) * 4 * k;
    moved++;
  }
  ev(g, 'pound', fx, fy, { moved });
}

function die(g, why) {
  if (g.state !== 'play') return;
  detach(g, false);
  g.state = 'dead'; g.deadT = F.respawn; g.deaths++; g.hs = 'normal';
  ev(g, 'die', g.hero.x, g.hero.y, { why });
  setEnabled(g.world, g.hero, false);
}

function respawn(g) {
  const h = g.hero, c = g.checkpoint;
  setTransform(g.world, h, c.x, c.y, 0);
  h.vx = 0; h.vy = 0;
  setEnabled(g.world, h, true);
  g.state = 'play'; g.hs = 'normal'; g.coyote = 0; g.jumpBuf = 0; g.jumping = false; g.launched = false;
  g.ground = null; g.airT = 0;
  ev(g, 'respawn', c.x, c.y);
}

function rules(g) {
  const h = g.hero;
  const hx0 = h.x - F.heroHx, hx1 = h.x + F.heroHx, hy0 = h.y - F.heroHy, hy1 = h.y + F.heroHy;
  if (g.comboT > 0) { g.comboT -= DT; if (g.comboT <= 0) g.combo = 0; }
  for (const e of g.entities) {
    e.px = e.x; e.py = e.y;
    switch (e.kind) {
      case 'cog': case 'star': {
        if (e.taken || g.state !== 'play') break;
        const dx = h.x - e.x, dy = h.y - e.y, d = Math.sqrt(dx * dx + dy * dy);
        if (d < F.pickR + (e.kind === 'star' ? 0.25 : 0)) {
          e.taken = true;
          if (e.kind === 'cog') { g.cogs++; g.combo++; g.comboT = 0.6; ev(g, 'cog', e.x, e.y, { combo: g.combo }); }
          else { g.stars[e.starIdx] = true; ev(g, 'star', e.x, e.y, { idx: e.starIdx }); }
        } else if (d < F.magnet && e.kind === 'cog') {
          const s = Math.min(d, F.magnetSpeed * DT) / d;
          e.x += dx * s; e.y += dy * s;
        }
        break;
      }
      case 'spring': {
        if (g.state !== 'play') break;
        const w = (e.w || 1.4) / 2;
        if (Math.abs(h.x - e.x) < w + F.heroHx * 0.4 && hy0 > e.y - 0.55 && hy0 < e.y + 0.3 && h.vy <= 0.5) {
          const sup = g.hs === 'pound';
          h.vy = (e.v || F.springV) * (sup ? F.superSpringMul : 1);
          if (sup) { g.hs = 'normal'; }
          g.jumping = false; g.launched = true; g.coyote = 0;
          ev(g, 'spring', e.x, e.y, { super: sup });
        }
        for (const b of g.respawnables) {
          if (b.enabled && Math.abs(b.x - e.x) < w && b.y - b.hy > e.y - 0.55 && b.y - b.hy < e.y + 0.3 && b.vy <= 0.5) {
            b.vy = (e.v || F.springV) * 0.8; ev(g, 'spring', e.x, e.y, { super: false, prop: true });
          }
        }
        break;
      }
      case 'spikes': {
        const w = (e.w || 1) / 2, hh = (e.h || 0.6) / 2;
        if (g.state === 'play' && hx1 - 0.12 > e.x - w && hx0 + 0.12 < e.x + w && hy1 - 0.1 > e.y - hh && hy0 + 0.12 < e.y + hh) die(g, 'spikes');
        break;
      }
      case 'checkpoint': {
        if (!e.active && g.state === 'play' && Math.abs(h.x - e.x) < 1.0 && h.y > e.y - 0.5 && h.y < e.y + 3.5) {
          for (const o of g.entities) if (o.kind === 'checkpoint') o.active = false;
          e.active = true; g.checkpoint = { x: e.x, y: e.y + F.heroHy + 0.05, idx: e.idx ?? 0 };
          ev(g, 'checkpoint', e.x, e.y);
        }
        break;
      }
      case 'goal': {
        if (g.state === 'play' && Math.abs(h.x - e.x) < 1.3 && h.y > e.y - 0.5 && h.y < e.y + 4) {
          detach(g, false);
          g.state = 'won'; g.wonFrame = g.frame; g.hs = 'normal';
          ev(g, 'goal', e.x, e.y, { time: g.time, cogs: g.cogs, deaths: g.deaths });
        }
        break;
      }
      default: break;
    }
  }
  if (g.state === 'play' && h.y < (g.P.killY ?? -20)) die(g, 'fall');
}

function winds(g) {
  for (const e of g.winds) {
    const w = (e.w || 2) / 2, hh = (e.h || 6) / 2, cy = e.y + hh;
    const apply = b => {
      if (Math.abs(b.x - e.x) < w && b.y > e.y - 0.5 && b.y < e.y + 2 * hh) {
        b.vy = Math.min(b.vy + (e.accel || 60) * DT, e.vmax || 9);
      }
    };
    if (g.state === 'play') apply(g.hero);
    for (const b of g.respawnables) if (b.enabled) apply(b);
    void cy;
  }
}

function props(g) {
  const killY = g.P.killY ?? -20;
  for (const b of g.respawnables) {
    if (b.y < killY - 3) {
      const [x, y, a] = b.data.home;
      setTransform(g.world, b, x, y, a); b.vx = 0; b.vy = 0; b.w = 0;
      ev(g, 'poof', x, y, { name: b.name });
    }
  }
  for (const d of g.debris) {
    if (d.life > 0) { d.life -= DT; if (d.life <= 0) setEnabled(g.world, d.b, false); }
  }
  let n = 0;
  for (const im of g.world.impacts) {
    if (n >= 3 || im.b1.role === 'debris' || im.b2.role === 'debris') continue;
    if (im.b1 === g.hero || im.b2 === g.hero) continue;
    ev(g, 'impact', im.x, im.y, { speed: im.speed }); n++;
  }
}

/** Advance the game by one tick with the given button bits. */
export function step(g, bits) {
  const pressed = bits & ~g.prevBits;
  g.prevBits = bits;
  g.frame++;
  if (g.hitstop > 0) {
    g.hitstop -= DT;
    for (const b of g.world.bodies) { b.px = b.x; b.py = b.y; b.pa = b.a; }
    if (pressed & BTN.J) g.jumpBuf = F.buffer;
    return;
  }
  g.time += DT;
  const h = g.hero;
  g.prevVy = h.vy;
  if (g.state === 'play') controlHero(g, bits, pressed);
  else if (g.state === 'dead') { g.deadT -= DT; if (g.deadT <= 0) respawn(g); }
  else if (g.state === 'won') { h.vx *= 0.9; h.vy = Math.max(h.vy - F.gravity * F.fallMul * DT, -F.maxFall); }
  updateMovers(g);
  updateCrumbles(g);
  winds(g);
  stepWorld(g.world, DT);
  if (g.state !== 'dead') senseHero(g);
  if (g.hs === 'pound' && g.ground) poundLand(g);
  rules(g);
  props(g);
}

const CODE = { play: 1, dead: 2, won: 3 };
/** 64-bit digest of everything that moves, as 16 hex digits (Float64 bytes, little-endian). */
export function stateHash(g) {
  const f = new Float64Array(1), u = new Uint8Array(f.buffer);
  let a = 0x811c9dc5, c = 0x9e3779b9;
  const mix = v => {
    f[0] = v;
    for (let i = 0; i < 8; i++) { a = Math.imul(a ^ u[i], 16777619); c = Math.imul(c ^ u[i], 0x5bd1e995); c ^= c >>> 15; }
  };
  for (const b of g.world.bodies) {
    if (b.kind === 'static' && b.role !== 'crumble' && b.role !== 'cracked') continue;
    mix(b.x); mix(b.y); mix(b.a); mix(b.vx); mix(b.vy); mix(b.w); mix(b.enabled ? 1 : 0);
  }
  for (const e of g.entities) if (e.kind === 'cog' || e.kind === 'star') { mix(e.x); mix(e.y); mix(e.taken ? 1 : 0); }
  mix(g.cogs); mix(g.deaths); mix(g.frame); mix(CODE[g.state]);
  return (a >>> 0).toString(16).padStart(8, '0') + (c >>> 0).toString(16).padStart(8, '0');
}

/** Summary used by tapes, bots and the HUD. */
export function summary(g) {
  return { frame: g.frame, time: +g.time.toFixed(4), state: g.state, cogs: g.cogs, cogsTotal: g.cogsTotal,
    stars: g.stars.filter(Boolean).length, starsTotal: g.stars.length, deaths: g.deaths,
    hero: [+g.hero.x.toFixed(3), +g.hero.y.toFixed(3)], hash: stateHash(g) };
}
