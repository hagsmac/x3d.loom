// The picture: reads the game state and writes X3D fields through X_ITE's SAI. Nothing here
// feeds back into the simulation, so frame rate never changes an outcome (the tape is the truth).
// Everything is "juice": camera, squash and stretch, scarf, particles, shadow, shake.

import { FEEL as F, DT } from './feel.js';
import { castDown } from './physics.js';

const lerp = (a, b, t) => a + (b - a) * t;
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function smooth(cur, vel, target, time, dt) {   // critically damped spring (Game Programming Gems 4)
  const omega = 2 / Math.max(1e-4, time), x = omega * dt;
  const exp = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  const change = cur - target;
  const temp = (vel + omega * change) * dt;
  const nv = (vel - omega * temp) * exp;
  return [target + (change + temp) * exp, nv];
}

export class Renderer {
  constructor(X3D, scene, game, opts = {}) {
    this.X3D = X3D; this.scene = scene; this.g = game; this.opts = opts;
    this.t = 0; this.trauma = 0; this.kick = 0;
    this.cache = new Map();
    const N = name => { try { return scene.getNamedNode(name); } catch { return null; } };
    this.N = N;
    this.cam = N('CAM');
    this.hero = { root: N('HERO'), squash: N('HERO_SQUASH'), yaw: N('HERO_YAW'), tilt: N('HERO_TILT'), pupil: N('HERO_PUPIL'),
      lid: N('HERO_LID'), key: N('HERO_KEY'), footL: N('HERO_FOOT_L'), footR: N('HERO_FOOT_R'), bulb: N('HERO_BULB') };
    this.rope = N('ROPE'); this.hilite = N('RING_HILITE'); this.shadow = N('SHADOW');
    this.scarf = []; for (let i = 0; i < 6; i++) this.scarf.push({ n: N('SCARF_' + i), x: 0, y: 0, ox: 0, oy: 0 });
    this.pools = {
      dust: this.pool('DUST_', 18), spark: this.pool('SPARK_', 28), conf: this.pool('CONF_', 40),
    };
    this.bodies = [];
    for (const b of game.world.bodies) {
      if (b.role === 'debris') { const n = N('V_' + b.name); if (n) this.bodies.push({ b, n, debris: true }); continue; }
      if (b.kind === 'static' && b.role !== 'crumble' && b.role !== 'cracked') continue;
      const n = N('V_' + b.name.replace(/^B_/, ''));
      if (n) this.bodies.push({ b, n });
    }
    this.ents = game.entities.map(e => ({ e, n: e.def ? N(e.def) : null, hidden: false,
      pad: e.kind === 'spring' ? N(e.def + '_PAD') : null, coil: e.kind === 'spring' ? N(e.def + '_COIL') : null,
      mat: e.kind === 'checkpoint' ? N('M_' + e.def) : null, anim: 0, animV: 0 }));
    // hero animation state
    this.sq = 1; this.sqV = 0; this.yawA = 0.75; this.tiltA = 0; this.walk = 0; this.keyA = 0; this.blinkT = 2.5; this.spin = 0;
    this.camX = game.hero.x; this.camY = game.hero.y + 2; this.camVX = 0; this.camVY = 0; this.look = 0; this.lookV = 0;
    this.camD = 18; this.camDV = 0; this.groundY = game.hero.y; this.pop = 1; this.windT = 0;
    this.heroVisible = true;
    for (const s of this.scarf) { s.x = s.ox = game.hero.x; s.y = s.oy = game.hero.y; }
  }

  pool(prefix, n) {
    const items = [];
    for (let i = 0; i < n; i++) { const node = this.N(prefix + i); if (node) items.push({ node, life: 0 }); }
    return { items, next: 0 };
  }

  set(node, field, value, key) {
    if (!node) return;
    const k = key || field;
    let c = this.cache.get(node);
    if (!c) { c = {}; this.cache.set(node, c); }
    const sig = value.join(',');
    if (c[k] === sig) return;
    c[k] = sig;
    const X = this.X3D;
    if (field === 'translation' || field === 'scale' || field === 'position') node[field] = new X.SFVec3f(value[0], value[1], value[2]);
    else if (field === 'rotation' || field === 'orientation') node[field] = new X.SFRotation(value[0], value[1], value[2], value[3]);
    else node[field] = new X.SFColor(value[0], value[1], value[2]);
  }
  T(node, x, y, z) { this.set(node, 'translation', [r4(x), r4(y), r4(z)]); }
  S(node, x, y, z) { this.set(node, 'scale', [r4(x), r4(y), r4(z)]); }
  R(node, ax, ay, az, a) { this.set(node, 'rotation', [ax, ay, az, r4(a)]); }

  emit(pool, x, y, z, vx, vy, vz, life, size, spin = 0, grav = 0) {
    const p = this.pools[pool], it = p.items[p.next];
    p.next = (p.next + 1) % p.items.length;
    if (!it) return;
    Object.assign(it, { x, y, z, vx, vy, vz, life, max: life, size, spin, a: Math.random() * 6.28, grav });
  }

  burst(type, x, y, n, speed, life, size, opts = {}) {
    for (let i = 0; i < n; i++) {
      const a = (opts.arc0 ?? 0) + (opts.arc ?? 6.2832) * Math.random();
      const s = speed * (0.4 + 0.6 * Math.random());
      this.emit(type, x, y, (Math.random() - 0.5) * (opts.zs ?? 1.2), Math.cos(a) * s, Math.sin(a) * s + (opts.up ?? 0),
        (Math.random() - 0.5) * (opts.zs ?? 1.2), life * (0.6 + 0.4 * Math.random()), size * (0.6 + 0.6 * Math.random()), (Math.random() - 0.5) * 12, opts.grav ?? 0);
    }
  }

  shake(amount) { this.trauma = Math.min(1, this.trauma + amount); }

  /** React to simulation events (picture and sound). */
  handle(ev, audio) {
    const h = this.g.hero;
    switch (ev.type) {
      case 'jump': this.sqV += 9; this.burst('dust', ev.x, ev.y + 0.1, 6, 2.5, 0.35, 0.8, { arc0: 0, arc: 3.14, up: 0.5 }); audio?.play('jump'); break;
      case 'walljump': this.sqV += 8; this.burst('dust', ev.x, ev.y, 7, 3, 0.35, 0.7); audio?.play('walljump'); break;
      case 'land': {
        const s = clamp(ev.speed / 22, 0, 1);
        this.sq = 1 - 0.3 * s - 0.08; this.sqV = 0;
        if (s > 0.25) this.burst('dust', ev.x, ev.y + 0.1, 4 + Math.round(8 * s), 2 + 4 * s, 0.4, 0.7 + s, { arc0: 0, arc: 3.14 });
        if (s > 0.7) this.shake(0.15 * s);
        audio?.play('land', { v: s }); break;
      }
      case 'cog': this.burst('spark', ev.x, ev.y, 7, 4.5, 0.4, 0.8, { grav: -6 }); audio?.play('cog', { combo: ev.combo }); break;
      case 'star': this.burst('spark', ev.x, ev.y, 26, 7, 0.9, 1.3, { grav: -4 }); this.burst('conf', ev.x, ev.y, 14, 6, 1.2, 1); this.shake(0.25); audio?.play('star'); break;
      case 'spring': {
        const en = this.nearest('spring', ev.x, ev.y); if (en) { en.anim = -0.55; en.animV = 0; }
        if (!ev.prop) { this.sq = 1.35; this.sqV = 0; this.burst('spark', ev.x, ev.y + 0.2, ev.super ? 18 : 8, ev.super ? 8 : 5, 0.5, 0.9); }
        if (ev.super) this.shake(0.3);
        audio?.play('spring', { super: ev.super }); break;
      }
      case 'poundstart': this.spin = 1; audio?.play('poundstart'); break;
      case 'pound': this.sq = 0.6; this.sqV = 0; this.shake(0.55); this.kick = 0.5;
        this.burst('dust', ev.x, ev.y + 0.15, 16, 7, 0.55, 1.2, { arc0: 0, arc: 3.14, zs: 2.5 }); audio?.play('pound'); break;
      case 'break': this.shake(0.45); this.burst('dust', ev.x, ev.y, 14, 6, 0.7, 1.4, { zs: 3 }); audio?.play('break'); break;
      case 'hook': audio?.play('hook'); this.burst('spark', ev.x, ev.y, 6, 3, 0.3, 0.6); break;
      case 'unhook': audio?.play(ev.jumped ? 'fling' : 'unhook'); if (ev.jumped) this.sqV += 6; break;
      case 'die': this.heroVisible = false; this.shake(0.5);
        this.burst('spark', ev.x, ev.y, 20, 7, 0.6, 1.1, { grav: -10 }); this.burst('dust', ev.x, ev.y, 10, 4, 0.6, 1.3); audio?.play('die'); break;
      case 'respawn': this.heroVisible = true; this.pop = 0; this.burst('spark', ev.x, ev.y, 12, 3, 0.5, 0.8, { up: 2 });
        this.camX = ev.x; this.camY = ev.y + 2; audio?.play('respawn'); break;
      case 'checkpoint': { const en = this.ents.find(o => o.e.kind === 'checkpoint' && o.e.x === ev.x);
        for (const o of this.ents) if (o.mat) { this.set(o.mat, 'emissiveColor', [0.05, 0.05, 0.08]); this.set(o.mat, 'diffuseColor', [0.45, 0.45, 0.5]); }
        if (en && en.mat) { this.set(en.mat, 'emissiveColor', [1, 0.65, 0.2]); this.set(en.mat, 'diffuseColor', [1, 0.8, 0.4]); }
        this.burst('spark', ev.x + 0.6, ev.y + 1.8, 14, 4, 0.7, 0.9, { grav: -3 }); audio?.play('checkpoint'); break; }
      case 'goal': this.burst('conf', ev.x, ev.y + 2.2, 40, 11, 2.4, 1.2, { up: 5, grav: -9, zs: 3 }); this.shake(0.3); audio?.play('goal'); break;
      case 'shake': audio?.play('creak'); break;
      case 'crumble': this.burst('dust', ev.x, ev.y, 8, 2.5, 0.6, 1.1); audio?.play('crumble'); break;
      case 'restore': this.burst('spark', ev.x, ev.y, 6, 2, 0.4, 0.6); break;
      case 'poof': this.burst('dust', ev.x, ev.y, 10, 3, 0.5, 1.2); audio?.play('poof'); break;
      case 'impact': if (ev.speed > 3) { audio?.play('thud', { v: clamp(ev.speed / 14, 0.1, 1) }); if (ev.speed > 6) this.burst('dust', ev.x, ev.y, 3, 2, 0.3, 0.6); } break;
      default: break;
    }
    void h;
  }

  nearest(kind, x, y) {
    let best = null, bd = 9;
    for (const o of this.ents) if (o.e.kind === kind) { const d = Math.abs(o.e.x - x) + Math.abs(o.e.y - y); if (d < bd) { bd = d; best = o; } }
    return best;
  }

  /** Draw one picture: alpha is the fraction of the next tick already elapsed (0..1). */
  frame(alpha, dt) {
    const g = this.g, h = g.hero;
    this.t += dt;
    // physics bodies
    for (const o of this.bodies) {
      const b = o.b;
      if (o.debris) {
        if (!b.enabled) { this.S(o.n, 0, 0, 0); continue; }
        this.S(o.n, 1, 1, 1);
      }
      let x = lerp(b.px, b.x, alpha), y = lerp(b.py, b.y, alpha);
      const a = lerp(b.pa, b.a, alpha);
      if (b.role === 'crumble') {
        const c = g.crumbles.find(q => q.b === b);
        if (c && c.phase === 'shake') x += Math.sin(this.t * 70) * 0.06;
        if (c && c.phase === 'gone') { this.S(o.n, 0, 0, 0); continue; }
        this.S(o.n, 1, 1, 1);
      }
      if (b.role === 'cracked' && !b.enabled) { this.S(o.n, 0, 0, 0); continue; }
      this.T(o.n, x, y, 0);
      this.R(o.n, 0, 0, 1, a);
    }
    // entities
    for (const o of this.ents) {
      const e = o.e;
      if ((e.kind === 'cog' || e.kind === 'star')) {
        if (e.taken) { if (!o.hidden) { this.S(o.n, 0, 0, 0); o.hidden = true; } continue; }
        if (e.x !== e.px || e.y !== e.py) this.T(o.n, lerp(e.px, e.x, alpha), lerp(e.py, e.y, alpha), 0);
        if (e.kind === 'star') this.T(o.n, e.x, e.y + Math.sin(this.t * 2.2) * 0.15, 0);
      }
      if (e.kind === 'spring' && (o.anim !== 0 || o.animV !== 0)) {
        o.animV += (-o.anim * 320 - o.animV * 14) * dt; o.anim += o.animV * dt;
        if (Math.abs(o.anim) < 0.002 && Math.abs(o.animV) < 0.02) { o.anim = 0; o.animV = 0; }
        this.S(o.coil, 1, clamp(1 + o.anim, 0.3, 2.0), 1);
        this.T(o.pad, 0, o.anim * 0.42, 0);
      }
      if (e.kind === 'wind') {
        this.windT += dt;
        if (Math.random() < dt * 14) this.emit('dust', e.x + (Math.random() - 0.5) * (e.w || 2) * 0.8, e.y + 0.4, (Math.random() - 0.5) * 1.5, 0, 6 + Math.random() * 4, 0, 0.9, 0.35);
      }
    }
    this.heroFrame(alpha, dt);
    this.particles(dt);
    this.camera(alpha, dt);
  }

  heroFrame(alpha, dt) {
    const g = this.g, h = g.hero, H = this.hero;
    const x = lerp(h.px, h.x, alpha), y = lerp(h.py, h.y, alpha);
    const vis = this.heroVisible && g.state !== 'dead';
    this.pop = Math.min(1, this.pop + dt * 5);
    const popS = vis ? (this.pop < 1 ? 1 + Math.sin(this.pop * Math.PI) * 0.35 : 1) * Math.min(1, this.pop * 3) : 0;
    this.T(H.root, x, y, 0);
    this.S(H.root, popS, popS, popS);
    // squash and stretch: a spring toward the shape the motion asks for
    const onGround = g.ground !== null;
    const target = onGround ? 1 : 1 + clamp(h.vy * 0.012, -0.1, 0.16);
    this.sqV += ((target - this.sq) * 260 - this.sqV * 16) * dt;
    this.sq = clamp(this.sq + this.sqV * dt, 0.5, 1.5);
    const sy = this.sq, sx = 1 / Math.sqrt(sy);
    this.S(H.squash, sx, sy, sx);
    // facing and lean
    const facing = g.wall !== 0 && !onGround && h.vy < 0 ? -g.wall : g.facing;
    this.yawA += (facing * 0.75 - this.yawA) * Math.min(1, dt * 14);
    this.R(H.yaw, 0, 1, 0, this.yawA);
    let tilt = clamp(-h.vx * 0.028, -0.26, 0.26);
    if (g.hs === 'pound') { this.spin = Math.max(0, this.spin - dt / Math.max(F.poundHover, 0.05)); tilt = -g.facing * (1 - this.spin) * 6.2832; }
    if (g.hs === 'hook' && g.ring) tilt = clamp((h.x - g.ring.x) * 0.25, -0.6, 0.6);
    this.tiltA += (tilt - this.tiltA) * Math.min(1, dt * (g.hs === 'pound' ? 60 : 12));
    this.R(H.tilt, 0, 0, 1, this.tiltA);
    // feet, key, eye
    const speed = Math.abs(h.vx - g.groundVel[0]);
    if (onGround) this.walk += speed * dt * 2.6;
    const fl = onGround ? Math.max(0, Math.sin(this.walk)) * 0.13 : 0.06, fr = onGround ? Math.max(0, -Math.sin(this.walk)) * 0.13 : 0.06;
    this.T(H.footL, -0.2, -0.44 + fl, 0.05 + (onGround ? Math.cos(this.walk) * 0.1 : -0.05));
    this.T(H.footR, 0.2, -0.44 + fr, 0.05 - (onGround ? Math.cos(this.walk) * 0.1 : -0.05));
    this.keyA += dt * (2.5 + speed * 1.6);
    this.R(H.key, 0, 0, 1, this.keyA % 6.2832);
    this.blinkT -= dt;
    const blinking = this.blinkT < 0.11;
    if (this.blinkT < 0) this.blinkT = 2 + Math.random() * 3;
    this.T(H.lid, 0, blinking ? 0.13 : 0.3, 0.36);
    this.S(H.lid, 1, blinking ? 0.62 : 0.15, 0.62);
    this.T(H.pupil, clamp(h.vx * 0.008, -0.06, 0.06), 0.1 + clamp(h.vy * 0.005, -0.05, 0.05), 0.47);
    const ring = g.hs !== 'hook' && !onGround ? this.ringInRange() : null;
    const b = 1 + (ring ? 0.6 + Math.sin(this.t * 18) * 0.25 : Math.sin(this.t * 3) * 0.08);
    this.S(H.bulb, b, b, b);
    // scarf: a 6-point verlet chain hanging from the back of the head
    const ax = x - g.facing * 0.3, ay = y + 0.18;
    const s0 = this.scarf[0];
    s0.ox = s0.x; s0.oy = s0.y; s0.x = ax; s0.y = ay;
    for (let i = 1; i < this.scarf.length; i++) {
      const s = this.scarf[i];
      const vx = (s.x - s.ox) * 0.93, vy = (s.y - s.oy) * 0.93;
      s.ox = s.x; s.oy = s.y;
      s.x += vx - g.facing * 2.2 * dt * dt * 6; s.y += vy - 9 * dt * dt + Math.sin(this.t * 9 + i) * 0.004;
    }
    for (let k = 0; k < 3; k++) for (let i = 1; i < this.scarf.length; i++) {
      const a = this.scarf[i - 1], s = this.scarf[i];
      const dx = s.x - a.x, dy = s.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1e-6, want = 0.19;
      s.x = a.x + dx / d * want; s.y = a.y + dy / d * want;
    }
    for (let i = 0; i < this.scarf.length; i++) {
      const s = this.scarf[i], p = this.scarf[Math.max(0, i - 1)], q = this.scarf[Math.min(this.scarf.length - 1, i + 1)];
      this.T(s.n, s.x, s.y, -0.12);
      this.R(s.n, 0, 0, 1, Math.atan2(q.y - p.y, q.x - p.x));
      this.S(s.n, vis ? 1 : 0, vis ? 1 : 0, vis ? 1 : 0);
    }
    // rope
    if (g.rope && g.ring) {
      const rx = g.ring.x, ry = g.ring.y, dx = x - rx, dy = y - ry, len = Math.sqrt(dx * dx + dy * dy);
      this.T(this.rope, (x + rx) / 2, (y + ry) / 2, 0);
      this.R(this.rope, 0, 0, 1, Math.atan2(dy, dx) - Math.PI / 2);
      this.S(this.rope, 1, len, 1);
    } else this.S(this.rope, 0, 0, 0);
    if (ring) { this.T(this.hilite, ring.x, ring.y, 0); const s = 0.9 + Math.sin(this.t * 10) * 0.12; this.S(this.hilite, s, s, s); }
    else this.S(this.hilite, 0, 0, 0);
    // blob shadow straight below
    const d = castDown(g.world, x, y - F.heroHy + 0.05, 14, h);
    if (vis && d < 14) {
      const s = clamp(1 - d * 0.07, 0.25, 1);
      this.T(this.shadow, x, y - F.heroHy - d + 0.03, 0.05);
      this.S(this.shadow, s, 1, s);
    } else this.S(this.shadow, 0, 0, 0);
  }

  ringInRange() {
    const h = this.g.hero;
    let best = null, bd = F.hookRange * F.hookRange;
    for (const e of this.g.entities) {
      if (e.kind !== 'ring' || e.y < h.y - 0.8) continue;
      const dx = e.x - h.x, dy = e.y - h.y, d2 = dx * dx + dy * dy;
      if (d2 < bd) { bd = d2; best = e; }
    }
    return best;
  }

  particles(dt) {
    for (const [name, p] of Object.entries(this.pools)) {
      for (const it of p.items) {
        if (it.life <= 0) { if (it.shown !== false) { this.S(it.node, 0, 0, 0); it.shown = false; } continue; }
        it.life -= dt;
        const k = clamp(it.life / it.max, 0, 1);
        it.vy += (it.grav || (name === 'conf' ? -6 : name === 'dust' ? 1.2 : 0)) * dt;
        const drag = name === 'conf' ? 1.8 : name === 'dust' ? 3.2 : 1.2;
        it.vx -= it.vx * drag * dt; it.vy -= it.vy * (name === 'conf' ? 0.6 : drag) * dt; it.vz -= it.vz * drag * dt;
        it.x += it.vx * dt; it.y += it.vy * dt; it.z += it.vz * dt; it.a += it.spin * dt;
        const s = it.size * (name === 'dust' ? (0.5 + (1 - k) * 0.9) * Math.min(1, k * 3) : name === 'spark' ? k : Math.min(1, k * 4));
        this.T(it.node, it.x, it.y, it.z);
        this.S(it.node, s, s, s);
        this.R(it.node, name === 'conf' ? 0.6 : 0, 0.4, 1, it.a);
        it.shown = true;
      }
    }
  }

  camera(alpha, dt) {
    const g = this.g, h = g.hero, P = g.P;
    const x = lerp(h.px, h.x, alpha), y = lerp(h.py, h.y, alpha);
    if (g.ground) this.groundY = y;
    // look ahead in the facing direction, more when running fast
    const lookT = g.facing * 2.4 + clamp(h.vx * 0.18, -2.5, 2.5);
    [this.look, this.lookV] = smooth(this.look, this.lookV, lookT, 0.55, dt);
    // vertical: follow the last ground height, but never let Nib leave a band around the centre
    let ty = this.groundY + 1.9;
    if (y > ty + 2.6) ty = y - 2.6;
    if (y < ty - 2.0) ty = y + 2.0;
    if (g.hs === 'hook') ty = (y + (g.ring ? g.ring.y : y)) / 2 + 1.0;
    // climbing (wall jumps, fans, springs): look up the shaft instead of trailing below it
    if (!g.ground && (g.wall !== 0 || g.wallLock > 0 || h.vy > 9)) ty = Math.max(ty, y + 1.6);
    ty = Math.max(ty, P.camMinY ?? -1e9);
    [this.camX, this.camVX] = smooth(this.camX, this.camVX, x + this.look, 0.22, dt);
    [this.camY, this.camVY] = smooth(this.camY, this.camVY, ty, 0.34, dt);
    const speed = Math.sqrt(h.vx * h.vx + h.vy * h.vy);
    let dist = 17.5 + clamp((speed - 6) * 0.25, 0, 3.5) + (g.hs === 'hook' ? 1.5 : 0);
    if (g.state === 'won') dist = 12;
    [this.camD, this.camDV] = smooth(this.camD, this.camDV, dist, 0.6, dt);
    // shake (trauma squared, smooth pseudo-noise)
    this.trauma = Math.max(0, this.trauma - dt * 1.7);
    this.kick = Math.max(0, this.kick - dt * 4);
    const tr = this.trauma * this.trauma, t = this.t;
    const sx = tr * 0.55 * (Math.sin(t * 47.3) * 0.6 + Math.sin(t * 91.7) * 0.4);
    const sy = tr * 0.55 * (Math.sin(t * 53.1 + 1.3) * 0.6 + Math.sin(t * 77.9) * 0.4) - this.kick * 0.25;
    const roll = tr * 0.03 * Math.sin(t * 39.7);
    const tilt = 0.085;
    const cx = this.camX + sx, cy = this.camY + sy + this.camD * Math.tan(tilt);
    this.set(this.cam, 'position', [r4(cx), r4(cy), r4(this.camD)]);
    // orientation: pitch down by `tilt`, then a little roll
    const q = axisAngleMul([1, 0, 0, -tilt], [0, 0, 1, roll]);
    this.set(this.cam, 'orientation', q.map(r4));
  }
}

function r4(v) { return Math.round(v * 1e4) / 1e4; }

function axisAngleMul(a, b) {   // rotation a then b, as axis-angle (via quaternions)
  const qa = q(a), qb = q(b);
  const w = qa[3] * qb[3] - qa[0] * qb[0] - qa[1] * qb[1] - qa[2] * qb[2];
  const x = qa[3] * qb[0] + qa[0] * qb[3] + qa[1] * qb[2] - qa[2] * qb[1];
  const y = qa[3] * qb[1] - qa[0] * qb[2] + qa[1] * qb[3] + qa[2] * qb[0];
  const z = qa[3] * qb[2] + qa[0] * qb[1] - qa[1] * qb[0] + qa[2] * qb[3];
  const s = Math.sqrt(Math.max(1e-12, 1 - w * w));
  return [x / s, y / s, z / s, 2 * Math.acos(clamp(w, -1, 1))];
}
function q([x, y, z, a]) { const s = Math.sin(a / 2), n = Math.hypot(x, y, z) || 1; return [x / n * s, y / n * s, z / n * s, Math.cos(a / 2)]; }

export { DT };
