// KANSEI picture side: puts the sim into the X3D scene through X_ITE's SAI. It reads sim.cars and
// sim.props after every tick, interpolates between the last two ticks (shortest-arc yaw), and writes
// only the fields that changed. Nothing here feeds back into the sim, so the frame rate never
// changes an outcome (the tape is the truth).
import { carQuat, qToAxisAngle, qMul, qAxis } from './camera.js';

const TAU = Math.PI * 2;
const wrapPi = a => a - TAU * Math.floor((a + Math.PI) / TAU);
const lerp = (a, b, t) => a + (b - a) * t;
const r4 = v => Math.round(v * 1e4) / 1e4;

export const LIVERIES = [
  { id: 'factory', name: 'Factory' },
  { id: 'kinari', name: 'Kinari white', rgb: [0.88, 0.86, 0.8] },
  { id: 'sumi', name: 'Sumi black', rgb: [0.025, 0.025, 0.03] },
  { id: 'ai', name: 'Aizome indigo', rgb: [0.04, 0.09, 0.32] },
  { id: 'tsubaki', name: 'Tsubaki crimson', rgb: [0.85, 0.16, 0.38] },
  { id: 'matcha', name: 'Matcha', rgb: [0.3, 0.42, 0.14] },
];
export const QUALITY = {
  low: { shadows: false, scale: 0.6, smoke: 70, aiSmoke: false, skidChunks: 10, spot: false, rain: 450, sparks: 40 },
  medium: { shadows: true, scale: 0.85, smoke: 150, aiSmoke: true, skidChunks: 18, spot: true, rain: 900, sparks: 70 },
  high: { shadows: true, scale: 0, smoke: 260, aiSmoke: true, skidChunks: 28, spot: true, rain: 1500, sparks: 110 },
};

/** Text transform for the ghost: every material translucent cyan, no shadows. */
export function ghostify(text) {
  return text
    .replace(/<(PhysicalMaterial|Material|UnlitMaterial)\b([^>]*?)(\/?)>/g, (m, tag, attrs, close) => {
      attrs = attrs.replace(/\s(transparency|emissiveColor)='[^']*'/g, '');
      return `<${tag}${attrs} transparency='0.68' emissiveColor='0.1 0.62 0.85'${close}>`;
    })
    .replace(/<Shape\b([^>]*?)\scastShadow='[^']*'/g, '<Shape$1')
    .replace(/<Shape\b/g, "<Shape castShadow='false'");
}

export class World {
  constructor({ X3D, browser, scene, track, manifest, quality = 'medium', base }) {
    this.X3D = X3D; this.browser = browser; this.scene = scene; this.T = track;
    this.manifest = manifest; this.base = base; this.q = QUALITY[quality] || QUALITY.medium; this.quality = quality;
    this.cache = new Map();
    this.cars = [];          // {nodes..., spec, prev, cur}
    this.ghost = null;
    const N = this.N = k => { try { return scene.getNamedNode(k); } catch { return null; } };
    this.nodes = { cars: N('Cars'), fx: N('FX'), cam: N('ChaseCam'), sun: N('Sun'), haze: N('Haze'), rain: N('Rain'), nav: N('Nav') };
    this.sunIntensity = this.nodes.sun ? this.nodes.sun.intensity : 1;
    this.night = track.time === 'night';
    // trackside cameras for the director
    this.trackCams = [];
    for (let i = 0; i < 32; i++) {
      const v = N('TrackCam' + i);
      if (!v) break;
      const p = v.position;
      this.trackCams.push({ x: p.x, y: p.y, z: p.z, desc: v.description });
    }
    // props: base height and yaw from the file
    this.props = [];
    for (let k = 0; k < track.props.length; k++) {
      const n = N('Prop' + k);
      if (!n) { this.props.push(null); continue; }
      const t0 = n.translation, r0 = n.rotation;
      this.props.push({ n, y0: t0.y, yaw0: r0.angle * Math.sign(r0.y || 1), sig: '', t0: [t0.x, t0.y, t0.z], r0: [r0.x, r0.y, r0.z, r0.angle] });
    }
    if (this.nodes.cam) { this.nodes.cam.set_bind = true; }
    this.applyQuality();
  }

  // ---- field writes with a per-node cache ---------------------------------------------------
  put(node, field, arr) {
    if (!node) return;
    let c = this.cache.get(node);
    if (!c) { c = {}; this.cache.set(node, c); }
    const sig = arr.length === 1 ? arr[0] : arr.join(',');
    if (c[field] === sig) return;
    c[field] = sig;
    const X = this.X3D;
    switch (field) {
      case 'translation': case 'position': case 'scale': case 'center': node[field] = new X.SFVec3f(arr[0], arr[1], arr[2]); break;
      case 'rotation': case 'orientation': node[field] = new X.SFRotation(arr[0], arr[1], arr[2], arr[3]); break;
      case 'emissiveColor': case 'baseColor': case 'diffuseColor': case 'color': node[field] = new X.SFColor(arr[0], arr[1], arr[2]); break;
      default: node[field] = arr[0];
    }
  }
  T3(node, x, y, z) { this.put(node, 'translation', [r4(x), r4(y), r4(z)]); }
  R4(node, r, field = 'rotation') { this.put(node, field, [r4(r[0]), r4(r[1]), r4(r[2]), r4(r[3])]); }

  applyQuality() {
    const sun = this.nodes.sun;
    if (sun) sun.shadows = !!this.q.shadows;
    try {
      // ?cscale=N (tools only) pins the canvas resolution factor, e.g. for big stills rendered below device pixels
      const pin = +(new URLSearchParams(location.search).get('cscale') || 0);
      const scale = pin > 0 ? Math.min(2, pin) : this.q.scale || Math.min(2, window.devicePixelRatio || 1);
      this.browser.setBrowserOption('ContentScale', scale);
      this.browser.setBrowserOption('Antialiased', this.quality !== 'low');
    } catch { /* older X_ITE: keep defaults */ }
  }

  // ---- cars ---------------------------------------------------------------------------------
  async loadCarScene(carId, ghost) {
    const X = this.X3D, b = this.browser;
    const url = new URL('cars/' + carId + '.x3d', this.base).href;
    if (!ghost) return b.createX3DFromURL(new X.MFString(url));
    const text = ghostify(await (await fetch(url)).text());
    const saved = b.baseURL;
    try { b.baseURL = url; return await b.createX3DFromString(text); } finally { try { b.baseURL = saved; } catch { /* read-only in some builds */ } }
  }

  /** Add car index i (sim order) with a livery; ghost cars are translucent and never collide. */
  async addCar(i, carId, { livery = null, ghost = false, headlight = false, smoke = true } = {}) {
    const X = this.X3D, sc = await this.loadCarScene(carId, ghost);
    const G = k => { try { return sc.getNamedNode(k); } catch { return null; } };
    const spec = this.manifest.cars.find(c => c.id === carId);
    const c = {
      id: carId, spec, ghost, root: G('Car'), body: G('Body'), paint: G('Paint'),
      brake: G('BrakeGlow'), head: G('HeadGlow'), rev: G('ReverseGlow'), shadow: G('ContactShadow'),
      wheels: ['FL', 'FR', 'RL', 'RR'].map(w => ({ t: G('Wheel' + w), s: G('Spin' + w), bump: 0 })),
      prev: null, cur: null, flames: [], lastBackfire: -1, smoke,
    };
    if (c.paint && !c.factory) c.factory = [c.paint.baseColor.r, c.paint.baseColor.g, c.paint.baseColor.b];
    if (livery && c.paint && !ghost) this.setLivery(c, livery);
    if (!ghost) this.addFlames(c, headlight);
    if (this.nodes.cars && c.root) this.nodes.cars.children.push(c.root);
    if (ghost) this.ghost = c; else this.cars[i] = c;
    return c;
  }
  setLivery(c, livery) {
    const L = typeof livery === 'string' ? LIVERIES.find(l => l.id === livery) : livery;
    const rgb = L && L.rgb ? L.rgb : c.factory;
    if (rgb && c.paint) c.paint.baseColor = new this.X3D.SFColor(rgb[0], rgb[1], rgb[2]);
  }

  addFlames(c, headlight) {
    const X = this.X3D, sc = this.scene, ex = c.spec.exhaust || [];
    const mk = (len, rad, col, tr) => {
      const sw = sc.createNode('Switch'); sw.whichChoice = -1;
      const rot = sc.createNode('Transform'); rot.rotation = new X.SFRotation(1, 0, 0, -Math.PI / 2);
      const off = sc.createNode('Transform'); off.translation = new X.SFVec3f(0, len / 2, 0);
      const sh = sc.createNode('Shape'); sh.castShadow = false;
      const ap = sc.createNode('Appearance'), m = sc.createNode('UnlitMaterial');
      m.emissiveColor = new X.SFColor(col[0], col[1], col[2]); m.transparency = tr; ap.material = m;
      const cone = sc.createNode('Cone'); cone.height = len; cone.bottomRadius = rad; cone.bottom = false;
      sh.appearance = ap; sh.geometry = cone; off.children.push(sh); rot.children.push(off); sw.children.push(rot);
      return { sw, rot, m };
    };
    for (const e of ex) {
      const t = sc.createNode('Transform'); t.translation = new X.SFVec3f(e[0], e[1], e[2] - 0.02);
      const pop = mk(0.36, 0.085, [1, 0.62, 0.18], 0.15), boost = mk(0.62, 0.07, [0.45, 0.6, 1], 0.25);
      t.children.push(pop.sw); t.children.push(boost.sw);
      c.root.children.push(t);
      c.flames.push({ t, pop, boost });
    }
    if (headlight && this.q.spot) {
      const sl = sc.createNode('SpotLight');
      sl.location = new X.SFVec3f(0, 0.72, c.spec.length / 2 - 0.1);
      sl.direction = new X.SFVec3f(0, -0.13, 1); sl.cutOffAngle = 0.62; sl.beamWidth = 0.4;
      sl.intensity = this.night ? 5 : 2.2; sl.radius = 70; sl.color = new X.SFColor(1, 0.95, 0.86); sl.global = true;
      c.root.children.push(sl);
      c.spot = sl;
    }
  }

  removeGhost() {
    if (!this.ghost) return;
    try { this.ghost.root.translation = new this.X3D.SFVec3f(0, -500, 0); } catch { /* */ }
    this.ghost = null;
  }

  // ---- interpolation --------------------------------------------------------------------------
  static pose(car, out = {}) {
    out.x = car.x; out.y = car.y; out.z = car.z; out.yaw = car.yaw;
    out.gp = car.groundPitch; out.gr = car.groundRoll; out.bp = car.bodyPitch; out.br = car.bodyRoll;
    out.pitch = car.pitch; out.roll = car.roll;
    out.vx = car.vx; out.vz = car.vz; out.speed = car.speed; out.slip = car.slip;
    out.st0 = car.wheels[0].steer; out.st1 = car.wheels[1].steer;
    out.sp = out.sp || [0, 0, 0, 0];
    for (let k = 0; k < 4; k++) out.sp[k] = car.wheels[k].spin;
    out.boost = car.boostActive; out.drifting = car.drifting;
    return out;
  }
  /** Call before each sim tick: the current pose becomes the previous one. */
  beforeTick(sim) {
    for (let i = 0; i < sim.cars.length; i++) {
      const c = this.cars[i]; if (!c) continue;
      if (!c.cur) c.cur = World.pose(sim.cars[i]);
      c.prev = World.pose(sim.cars[i], c.prev || {});
    }
  }
  afterTick(sim) {
    for (let i = 0; i < sim.cars.length; i++) { const c = this.cars[i]; if (c) c.cur = World.pose(sim.cars[i], c.cur || {}); }
  }
  /** Snap both poses to the sim (after a reset, a load or a scrub). */
  snap(sim) {
    for (let i = 0; i < sim.cars.length; i++) { const c = this.cars[i]; if (c) { c.prev = World.pose(sim.cars[i], c.prev || {}); c.cur = World.pose(sim.cars[i], c.cur || {}); } }
  }
  interp(c, a, out = {}) {
    const p = c.prev || c.cur, q = c.cur;
    if (!q) return null;
    // a reset or teleport: do not smear across it
    const jump = Math.abs(q.x - p.x) + Math.abs(q.z - p.z) > 6;
    const t = jump ? 1 : a;
    out.x = lerp(p.x, q.x, t); out.y = lerp(p.y, q.y, t); out.z = lerp(p.z, q.z, t);
    out.yaw = p.yaw + wrapPi(q.yaw - p.yaw) * t;
    out.gp = lerp(p.gp, q.gp, t); out.gr = lerp(p.gr, q.gr, t); out.bp = lerp(p.bp, q.bp, t); out.br = lerp(p.br, q.br, t);
    out.pitch = out.gp + out.bp; out.roll = out.gr + out.br;
    out.vx = lerp(p.vx, q.vx, t); out.vz = lerp(p.vz, q.vz, t); out.speed = lerp(p.speed, q.speed, t); out.slip = q.slip;
    out.st0 = lerp(p.st0, q.st0, t); out.st1 = lerp(p.st1, q.st1, t);
    out.sp = out.sp || [0, 0, 0, 0];
    for (let k = 0; k < 4; k++) out.sp[k] = p.sp[k] + wrapPi(q.sp[k] - p.sp[k]) * t;
    out.boost = q.boost; out.drifting = q.drifting;
    return out;
  }

  // ---- per frame ------------------------------------------------------------------------------
  /** Write every car's pose (interpolated by alpha) and lights; returns the poses (sim order). */
  frame(sim, alpha, dt, tick) {
    const poses = this._poses || (this._poses = []);
    for (let i = 0; i < sim.cars.length; i++) {
      const c = this.cars[i];
      if (!c) { poses[i] = null; continue; }
      const p = poses[i] = this.interp(c, alpha, poses[i] || {});
      if (!p) continue;
      this.writeCar(c, p, sim.cars[i], tick);
    }
    poses.length = sim.cars.length;
    this.frameProps(sim);
    return poses;
  }

  writeCar(c, p, car, tick) {
    this.T3(c.root, p.x, p.y, p.z);
    this.R4(c.root, qToAxisAngle(carQuat(p.yaw, p.gp, p.gr)));
    if (c.body) this.R4(c.body, qToAxisAngle(qMul(qAxis(1, 0, 0, p.bp), qAxis(0, 0, 1, p.br))));
    const W = c.wheels, hubs = c.spec.hubs;
    for (let k = 0; k < 4; k++) {
      const w = W[k];
      if (k < 2) this.put(w.t, 'rotation', [0, 1, 0, r4(k === 0 ? p.st0 : p.st1)]);
      if (w.s) this.put(w.s, 'rotation', [1, 0, 0, Math.round(p.sp[k] * 500) / 500]);
      if (car) {
        // suspension: the curb and bump part of the sim's susp signal (the load part is the body roll)
        const s = car.wheels[k].susp;
        w.bump += (s - w.bump) * 0.15;
        const h = Math.max(-0.03, Math.min(0.03, (s - w.bump) * 0.9));
        this.T3(w.t, hubs[k][0], hubs[k][1] + Math.round(h * 300) / 300, hubs[k][2]);
      }
    }
    if (!car || c.ghost) return;
    // lights
    const night = this.night || this.T.time === 'sunset';
    const brake = car.lights.brake ? [1, 0.07, 0.04] : night ? [0.5, 0.02, 0.02] : [0.3, 0.01, 0.01];
    this.put(c.brake, 'emissiveColor', brake);
    this.put(c.rev, 'emissiveColor', car.lights.reverse ? [0.9, 0.9, 0.86] : [0, 0, 0]);
    this.put(c.head, 'emissiveColor', car.lights.head ? (this.night ? [1, 0.97, 0.9] : [0.8, 0.8, 0.74]) : [0.55, 0.55, 0.5]);
    // exhaust flames: pops for ~70 ms after a backfire tick, the nitrous flame while boosting
    const pop = car.backfire >= 0 && tick - car.backfire < 9;
    const boosting = car.boostActive;
    for (const f of c.flames) {
      this.put(f.pop.sw, 'whichChoice', [pop ? 0 : -1]);
      this.put(f.boost.sw, 'whichChoice', [boosting ? 0 : -1]);
      if (pop) this.put(f.pop.rot, 'scale', [1, Math.round((0.7 + Math.random() * 0.6) * 10) / 10, 1]);
      if (boosting) this.put(f.boost.rot, 'scale', [1, Math.round((0.8 + Math.random() * 0.5) * 10) / 10, 1]);
    }
  }

  /** The ghost from a pose record (Float32 rows: x y z yaw gp gr bp br st0 st1 sp0..3). */
  ghostFrame(rec, row, alpha) {
    if (!this.ghost || !rec) return null;
    const S = 14, n = rec.length / S;
    if (row < 0 || row >= n - 1) { this.put(this.ghost.root, 'translation', [0, -500, 0]); return null; }
    const a = row * S, b = a + S, t = alpha;
    const p = this._gp || (this._gp = { sp: [0, 0, 0, 0] });
    p.x = lerp(rec[a], rec[b], t); p.y = lerp(rec[a + 1], rec[b + 1], t); p.z = lerp(rec[a + 2], rec[b + 2], t);
    p.yaw = rec[a + 3] + wrapPi(rec[b + 3] - rec[a + 3]) * t;
    p.gp = rec[a + 4]; p.gr = rec[a + 5]; p.bp = rec[a + 6]; p.br = rec[a + 7]; p.st0 = rec[a + 8]; p.st1 = rec[a + 9];
    for (let k = 0; k < 4; k++) p.sp[k] = rec[a + 10 + k];
    this.writeCar(this.ghost, p, null, 0);
    return p;
  }

  frameProps(sim) {
    for (let k = 0; k < sim.props.length; k++) {
      const pr = sim.props[k], v = this.props[k];
      if (!v || !pr.hit) continue;
      const sig = r4(pr.x) + ',' + r4(pr.z) + ',' + r4(pr.y) + ',' + r4(pr.angle) + ',' + r4(pr.tilt);
      if (sig === v.sig) continue;
      v.sig = sig;
      this.T3(v.n, pr.x, v.y0 + pr.y + Math.sin(pr.tilt) * 0.12, pr.z);
      this.R4(v.n, qToAxisAngle(qMul(qAxis(0, 1, 0, v.yaw0 + pr.angle), qAxis(1, 0, 0, pr.tilt))));
    }
  }

  /** Put every prop back where the file has it (a new sim, a replay, a scrub). */
  resetProps() {
    for (const v of this.props) {
      if (!v || !v.sig) continue;
      v.sig = '';
      this.put(v.n, 'translation', v.t0); this.put(v.n, 'rotation', v.r0);
    }
  }

  /** Drive the level's ChaseCam viewpoint. */
  camera(view) {
    const vp = this.nodes.cam;
    if (!vp) return;
    this.put(vp, 'position', [r4(view.pos[0]), r4(view.pos[1]), r4(view.pos[2])]);
    this.R4(vp, view.rot, 'orientation');
    this.put(vp, 'fieldOfView', [Math.round(view.fov * 1000) / 1000]);
  }

  /** Wet look: darker, glossier road and paint lines, dimmer sun, closer grey haze. */
  setWet(wet) {
    const N = this.N;
    for (const def of ['A_road', 'A_course', 'A_pad', 'A_curb_rw', 'A_curb_bw', 'A_curb_yb', 'A_paint', 'A_paint_o', 'A_paint_y', 'A_band', 'A_wear', 'A_street', 'A_deck']) {
      const ap = N(def);
      if (!ap || !ap.material) continue;
      const m = ap.material;
      const dry = this._dry || (this._dry = {});
      if (!dry[def]) dry[def] = { rough: m.roughness, col: m.baseColor ? [m.baseColor.r, m.baseColor.g, m.baseColor.b] : null };
      const d = dry[def], k = def.startsWith('A_road') || def === 'A_course' || def === 'A_pad' || def === 'A_street' || def === 'A_deck' ? 0.55 : 0.75;
      if (d.rough !== undefined) m.roughness = wet ? Math.min(d.rough, 0.18) : d.rough;
      if (d.col) m.baseColor = new this.X3D.SFColor(...(wet ? d.col.map(v => v * k) : d.col));
    }
    const sun = this.nodes.sun;
    if (sun) sun.intensity = wet ? this.sunIntensity * 0.55 : this.sunIntensity;
    const hz = this.nodes.haze;
    if (hz) {
      if (!this._hz) this._hz = { range: hz.visibilityRange, col: [hz.color.r, hz.color.g, hz.color.b] };
      hz.visibilityRange = wet ? Math.min(this._hz.range, this.night ? 900 : 1400) : this._hz.range;
      const c = this._hz.col, g = (c[0] + c[1] + c[2]) / 3;
      hz.color = new this.X3D.SFColor(...(wet ? c.map(v => v * 0.45 + g * 0.45) : c));
    }
  }
}
