// KANSEI picture side: camera rigs. Pure maths on interpolated car poses; render.js writes the
// result into the level's ChaseCam Viewpoint. Free to use Math.* (never part of the sim).
//   chase     drift-aware: swings between heading and velocity so a slide is framed from its side
//   close     tighter, lower chase
//   bumper    on the nose, rolls and pitches with the body
//   hood      over the bonnet
//   orbit     drag and wheel around the car (auto-turns when idle)
//   director  trackside: the nearest TrackCam viewpoint tracks the car with a zoom
// plus photo (free orbit, roll, FOV) and the replay director (cuts between all of them).

export const CAMERAS = ['chase', 'close', 'bumper', 'hood', 'orbit', 'director'];
export const CAMERA_LABEL = { chase: 'Chase', close: 'Close chase', bumper: 'Bumper', hood: 'Hood', orbit: 'Orbit', director: 'Director', photo: 'Photo', replay: 'Replay director' };

const TAU = Math.PI * 2;
const wrapPi = a => a - TAU * Math.floor((a + Math.PI) / TAU);
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

// quaternions [x, y, z, w]
export const qAxis = (ax, ay, az, a) => { const s = Math.sin(a / 2); return [ax * s, ay * s, az * s, Math.cos(a / 2)]; };
export function qMul(a, b) {
  return [a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1], a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
    a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3], a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]];
}
export function qRot(q, v) {   // rotate vector v by q
  const [x, y, z, w] = q, [vx, vy, vz] = v;
  const tx = 2 * (y * vz - z * vy), ty = 2 * (z * vx - x * vz), tz = 2 * (x * vy - y * vx);
  return [vx + w * tx + (y * tz - z * ty), vy + w * ty + (z * tx - x * tz), vz + w * tz + (x * ty - y * tx)];
}
export function qToAxisAngle(q) {
  let [x, y, z, w] = q;
  const n = Math.hypot(x, y, z, w) || 1; x /= n; y /= n; z /= n; w /= n;
  if (w < 0) { x = -x; y = -y; z = -z; w = -w; }
  const s = Math.hypot(x, y, z);
  if (s < 1e-9) return [0, 1, 0, 0];
  return [x / s, y / s, z / s, 2 * Math.atan2(s, w)];
}
export function axisAngleToQ(r) { return qAxis(r[0], r[1], r[2], r[3]); }
/** The car body orientation: yaw about +Y, then pitch about +X (nose down), then roll about +Z (left up). */
export const carQuat = (yaw, pitch, roll) => qMul(qMul(qAxis(0, 1, 0, yaw), qAxis(1, 0, 0, pitch)), qAxis(0, 0, 1, roll));
/** A viewpoint looking from eye along d (viewpoints look down -Z), with a roll about the view axis. */
export function lookQuat(d, roll = 0) {
  const l = Math.hypot(d[0], d[1], d[2]) || 1;
  const yaw = Math.atan2(-d[0], -d[2]), pitch = Math.asin(clamp(d[1] / l, -1, 1));
  let q = qMul(qAxis(0, 1, 0, yaw), qAxis(1, 0, 0, pitch));
  if (roll) q = qMul(q, qAxis(0, 0, 1, roll));
  return q;
}
export function qSlerp(a, b, t) {
  let d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3];
  let bb = b;
  if (d < 0) { d = -d; bb = [-b[0], -b[1], -b[2], -b[3]]; }
  if (d > 0.9995) { const r = a.map((v, i) => v + (bb[i] - v) * t); const n = Math.hypot(...r); return r.map(v => v / n); }
  const th = Math.acos(d), s = Math.sin(th);
  const wa = Math.sin((1 - t) * th) / s, wb = Math.sin(t * th) / s;
  return a.map((v, i) => v * wa + bb[i] * wb);
}

/** Critically damped spring step (value, velocity) toward target in `time` seconds. */
export function spring(cur, vel, target, time, dt) {
  const omega = 2 / Math.max(1e-4, time), x = omega * dt;
  const e = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  const change = cur - target, temp = (vel + omega * change) * dt;
  return [target + (change + temp) * e, (vel - omega * temp) * e];
}
const noise = t => Math.sin(t * 1.7) * 0.5 + Math.sin(t * 3.1 + 1.3) * 0.3 + Math.sin(t * 7.3 + 2.1) * 0.2;

export class CameraRig {
  constructor() {
    this.mode = 'chase';
    this.t = 0; this.trauma = 0; this.fovKick = 0;
    this.reset();
    this.orbit = { yaw: 2.4, pitch: 0.22, dist: 7.5, idle: 0 };
    this.photo = { yaw: 2.4, pitch: 0.12, dist: 6.5, fov: 0.75, roll: 0, height: 0.6 };
    this.cams = [];              // trackside [{x,y,z,desc}]
    this.dir = { idx: -1, hold: 0, aimQ: null, fov: 0.6 };
    this.replayCut = { kind: 'director', until: 0, seq: 0 };
  }
  reset() { this.yawS = null; this.yawV = 0; this.yS = 0; this.yV = 0; this.dS = 5.6; this.dV = 0; this.latS = 0; this.latV = 0; this.fov = 0.85; this.fovV = 0; this.dir && (this.dir.idx = -1); }
  setMode(m) { if (m !== this.mode) { this.mode = m; if (m === 'chase' || m === 'close') this.yawS = null; } }
  next() { const i = CAMERAS.indexOf(this.mode); this.setMode(CAMERAS[(i + 1) % CAMERAS.length]); return this.mode; }
  shake(amount) { this.trauma = Math.min(1, this.trauma + amount); }
  drag(dx, dy) {
    const o = this.mode === 'photo' ? this.photo : this.orbit;
    o.yaw -= dx * 0.008; o.pitch = clamp(o.pitch + dy * 0.006, -0.05, 1.35); o.idle = 0;
  }
  zoom(dz) { const o = this.mode === 'photo' ? this.photo : this.orbit; o.dist = clamp(o.dist * Math.exp(dz * 0.0012), 2.6, 40); o.idle = 0; }

  /**
   * p: interpolated player pose {x,y,z,yaw,pitch,roll,vx,vz,speed,slip,drifting,boost}
   * car: dims {length,height}; returns {pos:[x,y,z], rot:[ax,ay,az,a], fov}
   */
  update(p, car, dt, opts = {}) {
    this.t += dt;
    const mode = opts.override || this.mode;
    let eye, q, fov = 0.85;
    const speedKick = clamp(p.speed / 75, 0, 1) * 0.2 + (p.boost ? 0.07 : 0);
    [this.fovKick] = spring(this.fovKick, 0, speedKick, 0.6, dt);
    if (mode === 'chase' || mode === 'close') {
      ({ eye, q, fov } = this.chaseCore(p, car, dt, mode === 'close', opts.snap));
    } else if (mode === 'bumper' || mode === 'hood') {
      const cq = carQuat(p.yaw, p.pitch * 0.6, p.roll * 0.6);
      const off = mode === 'bumper' ? [0, 0.58, car.length / 2 - 0.15] : [0, car.height * 0.93, -0.05];
      const o = qRot(cq, off);
      eye = [p.x + o[0], p.y + o[1], p.z + o[2]];
      q = qMul(qMul(cq, qAxis(0, 1, 0, Math.PI)), qAxis(1, 0, 0, mode === 'hood' ? -0.035 : -0.02));
      fov = (mode === 'bumper' ? 1.0 : 0.95) + this.fovKick * 1.2;
    } else if (mode === 'orbit' || mode === 'photo') {
      const o = mode === 'photo' ? this.photo : this.orbit;
      if (mode === 'orbit') { o.idle += dt; if (o.idle > 2.5) o.yaw += dt * 0.18; }
      const yaw = p.yaw + o.yaw, cp = Math.cos(o.pitch);
      const tg = [p.x, p.y + (mode === 'photo' ? o.height : 0.7), p.z];
      eye = [tg[0] + Math.sin(yaw) * cp * o.dist, tg[1] + Math.sin(o.pitch) * o.dist + 0.2, tg[2] + Math.cos(yaw) * cp * o.dist];
      eye[1] = Math.max(eye[1], p.y + 0.25);
      q = lookQuat([tg[0] - eye[0], tg[1] - eye[1], tg[2] - eye[2]], mode === 'photo' ? o.roll : 0);
      fov = mode === 'photo' ? o.fov : 0.8;
    } else {   // director (live) and replay director
      const r = this.directorShot(p, car, dt, mode === 'replay');
      eye = r.eye; q = r.q; fov = r.fov;
    }
    // shake from impacts and rumble: trauma squared, decays
    this.trauma = Math.max(0, this.trauma - dt * 1.4);
    const k = this.trauma * this.trauma + (opts.rumble || 0) * 0.04;
    if (k > 1e-4 && mode !== 'photo') {
      const t = this.t * 14;
      eye = [eye[0] + noise(t) * 0.22 * k, eye[1] + noise(t + 17) * 0.16 * k, eye[2] + noise(t + 41) * 0.22 * k];
      q = qMul(q, qMul(qAxis(1, 0, 0, noise(t + 7) * 0.035 * k), qAxis(0, 0, 1, noise(t + 3) * 0.05 * k)));
    }
    return { pos: eye, rot: qToAxisAngle(q), fov: clamp(fov, 0.1, 1.6), mode };
  }

  /** Trackside director: hold the best viewpoint for the car, track it with a smoothed aim and zoom. */
  directorShot(p, car, dt, replay) {
    const D = this.dir;
    this.replayCut.until -= dt;
    if (replay && this.replayCut.until <= 0) {
      // the replay director cycles trackside, low chase and orbit shots
      const seq = ++this.replayCut.seq;
      const kinds = ['director', 'chase', 'director', 'low', 'director', 'heli'];
      this.replayCut.kind = kinds[seq % kinds.length];
      this.replayCut.until = this.replayCut.kind === 'director' ? 6 : 4.5;
      this.yawS = null; D.idx = -1;
      this.replayCut.a0 = (seq * 2.399) % TAU;
    }
    const kind = replay ? this.replayCut.kind : 'director';
    if (kind === 'chase') return this.chaseCore(p, car, dt, false, false);
    if (kind === 'low' || kind === 'heli' || !this.cams.length) {
      const heli = kind === 'heli';
      const a = p.yaw + (this.replayCut.a0 || 2.4) + this.t * (heli ? 0.08 : 0.25);
      const dist = heli ? 22 : 5.2, h = heli ? 12 : 0.55;
      const eye = [p.x + Math.sin(a) * dist, p.y + h, p.z + Math.cos(a) * dist];
      const tg = [p.x, p.y + 0.6, p.z];
      return { eye, q: lookQuat([tg[0] - eye[0], tg[1] - eye[1], tg[2] - eye[2]]), fov: heli ? 0.55 : 0.95 };
    }
    // choose the trackside camera: nearest with line of sight assumed; switch with hysteresis
    let best = -1, bd = 1e18;
    for (let i = 0; i < this.cams.length; i++) {
      const c = this.cams[i], d = (c.x - p.x) ** 2 + (c.z - p.z) ** 2 + (c.y - p.y) ** 2;
      if (d < bd) { bd = d; best = i; }
    }
    D.hold -= dt;
    if (D.idx < 0) { D.idx = best; D.aimQ = null; D.hold = 2; }
    else if (best !== D.idx && D.hold <= 0) {
      const c = this.cams[D.idx], dc = (c.x - p.x) ** 2 + (c.z - p.z) ** 2;
      if (bd < dc * 0.6 || dc > 160 * 160) { D.idx = best; D.aimQ = null; D.hold = 2.5; }
    }
    const c = this.cams[D.idx];
    const eye = [c.x, c.y + 1.6, c.z];   // a little above the file's viewpoint, to see over barriers
    const lead = 0.25;
    const tg = [p.x + p.vx * lead, p.y + 0.7, p.z + p.vz * lead];
    const dist = Math.hypot(tg[0] - eye[0], tg[1] - eye[1], tg[2] - eye[2]);
    const want = lookQuat([tg[0] - eye[0], tg[1] - eye[1], tg[2] - eye[2]]);
    D.aimQ = D.aimQ ? qSlerp(D.aimQ, want, 1 - Math.exp(-dt * 9)) : want;
    const fovT = clamp(2 * Math.atan(7.5 / Math.max(1, dist)), 0.1, 0.85);
    D.fov = D.aimQ === want ? fovT : D.fov + (fovT - D.fov) * (1 - Math.exp(-dt * 3));
    return { eye, q: D.aimQ, fov: D.fov };
  }
  chaseCore(p, car, dt, close, snap) {
    const velYaw = p.speed > 3 ? Math.atan2(p.vx, p.vz) : p.yaw;
    // swing toward the velocity: the more sideways, the more of the car's flank is shown
    const slipAbs = Math.abs(wrapPi(velYaw - p.yaw));
    const swing = p.speed > 3 ? clamp(0.25 + slipAbs * 0.9, 0.25, 0.7) : 0;
    const target = p.yaw + wrapPi(velYaw - p.yaw) * swing;
    if (this.yawS === null || snap) { this.yawS = target; this.yawV = 0; this.yS = p.y; this.dS = close ? 4.2 : 5.8; }
    const tgt = this.yawS + wrapPi(target - this.yawS);
    [this.yawS, this.yawV] = spring(this.yawS, this.yawV, tgt, close ? 0.22 : 0.3, dt);
    [this.yS, this.yV] = spring(this.yS, this.yV, p.y, 0.18, dt);
    const D = (close ? 4.0 : 5.6) + clamp(p.speed, 0, 80) * (close ? 0.012 : 0.022);
    [this.dS, this.dV] = spring(this.dS, this.dV, D, 0.5, dt);
    const H = (close ? 1.25 : 1.85) + (car.height - 1.3) * 0.6;
    const fx = Math.sin(this.yawS), fz = Math.cos(this.yawS);
    // look a little ahead along the velocity and toward the outside of the slide
    const lat = clamp(wrapPi(velYaw - p.yaw), -0.8, 0.8) * (close ? 0.6 : 1.1);
    [this.latS, this.latV] = spring(this.latS, this.latV, lat, 0.35, dt);
    const lx = Math.cos(this.yawS), lz = -Math.sin(this.yawS);
    const eye = [p.x - fx * this.dS + lx * this.latS * 0.4, this.yS + H, p.z - fz * this.dS + lz * this.latS * 0.4];
    const ahead = 2.5 + clamp(p.speed, 0, 60) * 0.05;
    const tg = [p.x + Math.sin(velYaw) * ahead - lx * this.latS * 0.5, this.yS + (close ? 0.75 : 0.9), p.z + Math.cos(velYaw) * ahead - lz * this.latS * 0.5];
    // tall (portrait) screens: aim lower (tallTan = tan of the extra pitch) so the car sits at about
    // 40% of the height, clear of the tach and pedals; the portrait frame still shows the road ahead
    if (this.tallTan) tg[1] -= Math.hypot(tg[0] - eye[0], tg[2] - eye[2]) * this.tallTan;
    const q = lookQuat([tg[0] - eye[0], tg[1] - eye[1], tg[2] - eye[2]], -clamp(this.yawV, -2, 2) * 0.012);
    return { eye, q, fov: (close ? 0.92 : 0.84) + this.fovKick };
  }
}
