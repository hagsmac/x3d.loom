// KANSEI picture side: tyre smoke (one X3D ParticleSystem per car with a moving PointEmitter, so the
// plume stays in the world while the car drives on), skid marks (a ring buffer of IndexedTriangleSet
// chunks, written in batches), sparks on wall hits, rain around the camera and wet spray. All reads of
// the sim are read-only. Free to use Math.random (never part of the sim).

const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

/** One soft, lumpy puff with alpha (the colour ramp fades it over the particle's life). */
function smokeTexture() {
  const S = 128, c = document.createElement('canvas'); c.width = c.height = S;
  const g = c.getContext('2d');
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let k = 0; k < 14; k++) {
    const ang = rnd() * 6.283, d = rnd() * S * 0.16;
    const x = S / 2 + Math.cos(ang) * d, y = S / 2 + Math.sin(ang) * d, rr = S * (0.2 + rnd() * 0.16);
    const gr = g.createRadialGradient(x, y, 0, x, y, rr);
    gr.addColorStop(0, 'rgba(255,255,255,0.34)'); gr.addColorStop(0.55, 'rgba(255,255,255,0.14)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = gr; g.beginPath(); g.arc(x, y, rr, 0, 6.283); g.fill();
  }
  return c.toDataURL('image/png');
}
function dotTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 32;
  const g = c.getContext('2d'), gr = g.createRadialGradient(16, 16, 0, 16, 16, 16);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.35, 'rgba(255,240,200,0.8)'); gr.addColorStop(1, 'rgba(255,200,120,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 32, 32);
  return c.toDataURL('image/png');
}

const SURF_TINT = { asphalt: [0.9, 0.9, 0.92], curb: [0.9, 0.9, 0.92], grass: [0.5, 0.47, 0.34], sand: [0.82, 0.72, 0.52], gravel: [0.66, 0.6, 0.5], tarmac: [0.85, 0.85, 0.87] };

export class FX {
  constructor({ X3D, browser, scene, world, track, quality, wet }) {
    this.X3D = X3D; this.browser = browser; this.scene = scene; this.W = world; this.T = track; this.q = quality; this.wet = wet;
    this.root = world.nodes.fx;
    this.ok = false;
    this.smoke = [];
    this.skid = null;
    this.t = 0;
    const tod = track.time;
    this.light = tod === 'night' ? 0.42 : tod === 'sunset' ? 0.78 : 0.95;
    this.warm = tod === 'sunset' || tod === 'golden' ? [1, 0.9, 0.8] : tod === 'night' ? [0.75, 0.75, 0.95] : [1, 1, 1];
  }

  async init(carCount) {
    const X = this.X3D, sc = this.scene;
    this.buildSkids();
    try {
      const comp = this.browser.getComponent('ParticleSystems');
      await this.browser.loadComponents(comp);
      try { if (this.scene.addComponent) this.scene.addComponent(comp); } catch { /* older X_ITE */ }
      this.smokeURL = smokeTexture(); this.dotURL = dotTexture();
      for (let i = 0; i < carCount; i++) this.smoke.push(i === 0 || this.q.aiSmoke ? this.makeSmoke(i === 0 ? this.q.smoke : Math.round(this.q.smoke * 0.5)) : null);
      this.sparks = this.makeSparks();
      if (this.wet) this.rain = this.makeRain();
      this.ok = true;
    } catch (e) { console.warn('particles unavailable', e); }
    return this;
  }

  node(type, fields = {}) {
    const n = this.scene.createNode(type);
    for (const k in fields) n[k] = fields[k];
    return n;
  }
  rampRGBA(cols) { return this.node('ColorRGBA', { color: new this.X3D.MFColorRGBA(...cols.map(c => new this.X3D.SFColorRGBA(...c))) }); }

  makeSmoke(max) {
    const X = this.X3D;
    const ps = this.node('ParticleSystem');
    ps.geometryType = 'SPRITE'; ps.maxParticles = max; ps.particleLifetime = 1.7; ps.lifetimeVariation = 0.35;
    ps.particleSize = new X.SFVec2f(1.7, 1.7); ps.createParticles = false;
    // a wide cone, mostly sideways: smoke billows out from the tyres and lifts slowly (a point emitter with a
    // direction sends every puff straight up into a column)
    const em = this.node('ConeEmitter'); em.direction = new X.SFVec3f(0, 1, 0); em.angle = 1.2; em.speed = 1.3; em.variation = 0.6; em.mass = 0.05;
    em.position = new X.SFVec3f(0, -500, 0);
    ps.emitter = em;
    const phys = this.node('ForcePhysicsModel'); phys.force = new X.SFVec3f(0, 0.006, 0);
    ps.physics = new X.MFNode(phys);
    ps.colorKey = new X.MFFloat(0, 0.1, 0.45, 1);
    const ramp = this.rampRGBA([[1, 1, 1, 0], [1, 1, 1, 0.12], [1, 1, 1, 0.07], [1, 1, 1, 0]]);
    ps.color = ramp;
    const ap = this.node('Appearance'), m = this.node('UnlitMaterial');
    m.emissiveColor = new X.SFColor(...this.warm.map(v => v * this.light));
    ap.material = m;
    const tex = this.node('ImageTexture'); tex.url = new X.MFString(this.smokeURL);
    ap.texture = tex;
    ps.appearance = ap;
    ps.castShadow = false;
    this.root.children.push(ps);
    return { ps, em, ramp, mat: m, on: false, level: -1, tint: '', sig: '' };
  }

  makeSparks() {
    const X = this.X3D;
    const ps = this.node('ParticleSystem');
    ps.geometryType = 'LINE'; ps.maxParticles = this.q.sparks; ps.particleLifetime = 0.55; ps.lifetimeVariation = 0.5;
    ps.particleSize = new X.SFVec2f(0.02, 0.22); ps.createParticles = false;
    const em = this.node('PointEmitter'); em.direction = new X.SFVec3f(0, 0.6, 0); em.speed = 7; em.variation = 0.9; em.mass = 1;
    em.position = new X.SFVec3f(0, -500, 0);
    ps.emitter = em;
    const phys = this.node('ForcePhysicsModel'); phys.force = new X.SFVec3f(0, -9.8, 0);
    ps.physics = new X.MFNode(phys);
    ps.colorKey = new X.MFFloat(0, 0.3, 1);
    ps.color = this.rampRGBA([[1, 0.95, 0.7, 1], [1, 0.6, 0.15, 0.9], [0.9, 0.25, 0.05, 0]]);
    const ap = this.node('Appearance'), m = this.node('UnlitMaterial'); m.emissiveColor = new X.SFColor(1, 0.8, 0.4); ap.material = m;
    ps.appearance = ap; ps.castShadow = false;
    this.root.children.push(ps);
    return { ps, em, until: 0 };
  }

  makeRain() {
    const X = this.X3D, holder = this.W.nodes.rain || this.root;
    const ps = this.node('ParticleSystem');
    ps.geometryType = 'LINE'; ps.maxParticles = this.q.rain; ps.particleLifetime = 0.85; ps.lifetimeVariation = 0.1;
    ps.particleSize = new X.SFVec2f(0.015, 0.55);
    const em = this.node('PolylineEmitter');
    const co = this.node('Coordinate');
    co.point = new X.MFVec3f(new X.SFVec3f(-16, 11, -16), new X.SFVec3f(16, 11, 16), new X.SFVec3f(-16, 11, 16), new X.SFVec3f(16, 11, -16), new X.SFVec3f(0, 11, -18), new X.SFVec3f(0, 11, 18));
    em.coord = co; em.coordIndex = new X.MFInt32(0, 1, -1, 2, 3, -1, 4, 5);
    em.direction = new X.SFVec3f(0.12, -1, 0.05); em.speed = 15; em.variation = 0.08; em.mass = 1;
    ps.emitter = em;
    const ap = this.node('Appearance'), m = this.node('UnlitMaterial');
    m.emissiveColor = new X.SFColor(...(this.T.time === 'night' ? [0.55, 0.6, 0.8] : [0.78, 0.82, 0.9])); m.transparency = 0.45;
    ap.material = m; ps.appearance = ap; ps.castShadow = false;
    holder.children.push(ps);
    return { ps, holder };
  }

  // ---- skid marks: ring buffer of chunks ------------------------------------------------------
  buildSkids() {
    const X = this.X3D, n = this.q.skidChunks, QUADS = 96;
    const chunks = [];
    const ap = this.node('Appearance'), m = this.node('UnlitMaterial');
    m.emissiveColor = new X.SFColor(0.02, 0.02, 0.025); ap.material = m;
    for (let k = 0; k < n; k++) {
      const sh = this.node('Shape'); sh.castShadow = false;
      const g = this.node('IndexedTriangleSet'); g.solid = false; g.colorPerVertex = true;
      const co = this.node('Coordinate'), col = this.node('ColorRGBA');
      g.coord = co; g.color = col;
      sh.appearance = ap; sh.geometry = g;
      this.root.children.push(sh);
      chunks.push({ g, co, col, pts: [], cols: [], quads: 0, dirty: false, lift: 0.022 + (k % 4) * 0.0015 });
    }
    this.skid = { chunks, QUADS, active: 0, last: [], flushT: 0 };
  }
  addQuad(a, b, hw, alpha) {
    const S = this.skid;
    let ch = S.chunks[S.active];
    if (ch.quads >= S.QUADS) {
      this.flushChunk(ch);
      S.active = (S.active + 1) % S.chunks.length;
      ch = S.chunks[S.active];
      ch.pts.length = 0; ch.cols.length = 0; ch.quads = 0; ch.dirty = true;
    }
    let dx = b.x - a.x, dz = b.z - a.z;
    const l = Math.hypot(dx, dz) || 1; dx /= l; dz /= l;
    const lx = dz * hw, lz = -dx * hw, y0 = a.y + ch.lift, y1 = b.y + ch.lift;
    ch.pts.push(a.x + lx, y0, a.z + lz, a.x - lx, y0, a.z - lz, b.x - lx, y1, b.z - lz, b.x + lx, y1, b.z + lz);
    const c = this.wet ? 0.05 : 0.012, a0 = a.alpha, a1 = alpha;
    ch.cols.push(c, c, c, a0, c, c, c, a0, c, c, c, a1, c, c, c, a1);
    ch.quads++; ch.dirty = true;
  }
  flushChunk(ch) {
    if (!ch.dirty) return;
    ch.dirty = false;
    const X = this.X3D, P = ch.pts, C = ch.cols, pts = [], cols = [], idx = [];
    for (let i = 0; i < P.length; i += 3) pts.push(new X.SFVec3f(P[i], P[i + 1], P[i + 2]));
    for (let i = 0; i < C.length; i += 4) cols.push(new X.SFColorRGBA(C[i], C[i + 1], C[i + 2], C[i + 3]));
    for (let q = 0; q < ch.quads; q++) { const o = q * 4; idx.push(o, o + 1, o + 2, o, o + 2, o + 3); }
    ch.co.point = new X.MFVec3f(...pts);
    ch.col.color = new X.MFColorRGBA(...cols);
    ch.g.index = new X.MFInt32(...idx);
  }
  clearSkids() {
    if (!this.skid) return;
    for (const ch of this.skid.chunks) { ch.pts.length = 0; ch.cols.length = 0; ch.quads = 0; ch.dirty = true; this.flushChunk(ch); }
    this.skid.last = [];
  }

  /** Per frame: sim (read only), interpolated poses, the camera eye, dt (wall seconds, scaled for slow motion). */
  update(sim, poses, eye, dt, { paused = false } = {}) {
    this.t += dt;
    const S = this.skid;
    // skid marks from each wheel's contact point
    if (!paused && S) {
      for (let i = 0; i < sim.cars.length; i++) {
        const car = sim.cars[i];
        const last = S.last[i] || (S.last[i] = [null, null, null, null]);
        const c = Math.cos(car.yaw), s = Math.sin(car.yaw);
        for (let k = 0; k < 4; k++) {
          const w = car.wheels[k];
          const mark = w.skid > 0.12 && car.speed > 1.5;
          if (!mark) { last[k] = null; continue; }
          const x = car.x + w.px * c + w.pz * s, z = car.z - w.px * s + w.pz * c;
          const pt = { x, y: w.wy, z, alpha: clamp(w.skid * (this.wet ? 0.45 : 0.7), 0.08, 0.72) };
          const L = last[k];
          if (!L) { last[k] = pt; continue; }
          const d = Math.hypot(x - L.x, z - L.z);
          if (d < 0.55) continue;
          if (d < 6) this.addQuad(L, pt, 0.12 + (k >= 2 ? 0.02 : 0), pt.alpha);
          last[k] = pt;
        }
      }
      S.flushT -= dt;
      if (S.flushT <= 0) { S.flushT = 0.18; this.flushChunk(S.chunks[S.active]); }
    }
    if (!this.ok) return;
    // tyre smoke: one emitter per car, placed between the rear wheels weighted by their smoke
    for (let i = 0; i < sim.cars.length; i++) {
      const sm = this.smoke[i], car = sim.cars[i], p = poses[i];
      if (!sm || !p) continue;
      const wl = car.wheels[2], wr = car.wheels[3], wf = Math.max(car.wheels[0].smoke, car.wheels[1].smoke) * 0.5;
      let amt = Math.max(wl.smoke, wr.smoke, wf);
      const spray = this.wet && car.speed > 12 ? clamp((car.speed - 12) / 30, 0, 0.8) : 0;
      if (spray > amt) amt = spray;
      const on = !paused && amt > 0.12;
      const level = on ? Math.min(3, Math.floor(amt * 4)) : -1;
      if (on !== sm.on) { sm.on = on; sm.ps.createParticles = on; }
      if (on) {
        const bal = (wl.smoke + 0.01) / (wl.smoke + wr.smoke + 0.02);
        const lx = (bal - 0.5) * 1.2;
        const c = Math.cos(p.yaw), s = Math.sin(p.yaw), rz = -1.25;
        const x = p.x + lx * c + rz * s, z = p.z - lx * s + rz * c;
        sm.em.position = new this.X3D.SFVec3f(+x.toFixed(3), +(p.y + 0.35).toFixed(3), +z.toFixed(3));
        const surf = wl.surface || 'asphalt';
        const tint = spray > Math.max(wl.smoke, wr.smoke) ? 'spray' : surf;
        if (level !== sm.level || tint !== sm.tint) {
          sm.level = level; sm.tint = tint;
          const t = tint === 'spray' ? [0.82, 0.86, 0.92] : (SURF_TINT[tint] || SURF_TINT.asphalt);
          const a = [0.08, 0.12, 0.17, 0.22][level] * (tint === 'spray' ? 0.6 : 1);
          sm.ramp.color = new this.X3D.MFColorRGBA(...[[...t, 0], [...t, a], [...t, a * 0.55], [...t, 0]].map(v => new this.X3D.SFColorRGBA(...v)));
        }
      }
    }
    // sparks burst
    if (this.sparks && this.sparks.until > 0) { this.sparks.until -= dt; if (this.sparks.until <= 0) this.sparks.ps.createParticles = false; }
    // rain follows the camera
    if (this.rain && eye && this.rain.holder !== this.root) {
      const h = this.rain.holder, k = Math.round(eye[0]) + ',' + Math.round(eye[1]) + ',' + Math.round(eye[2]);
      if (k !== this.rain.k) { this.rain.k = k; h.translation = new this.X3D.SFVec3f(Math.round(eye[0]), Math.round(eye[1]) - 3, Math.round(eye[2])); }
    }
  }

  spark(x, y, z, strength) {
    if (!this.sparks) return;
    const sp = this.sparks;
    sp.em.position = new this.X3D.SFVec3f(x, y, z);
    sp.em.speed = 4 + Math.min(8, strength * 6);
    sp.ps.createParticles = true;
    sp.until = 0.12 + Math.min(0.2, strength * 0.1);
  }

  setPaused(p) {
    if (!this.ok) return;
    for (const sm of this.smoke) if (sm && p && sm.on) { sm.on = false; sm.ps.createParticles = false; }
  }
}
