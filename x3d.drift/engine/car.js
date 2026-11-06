// loom:sim
// KANSEI vehicle model (CONTRACT.md section 7). One car, one 1/120 s tick, four substeps.
//
// Chassis: planar rigid body (x, z, yaw, vx, vz, yawRate) on the track surface; height, pitch and
// roll come from the road under the four contact patches plus spring-damper filtered load transfer.
// Tyres: brush-type combined-slip model on normalised slip s = |(kappa/kappaPeak, tan(alpha)/tan(alphaPeak))|,
//   F = mu(Fz, T, surface) Fz f(s), f = 1-(1-s)^3 up to the peak, then a falloff to a sliding ratio;
//   the force points along the normalised slip vector, so Fx^2 + Fy^2 <= (mu Fz)^2 always holds.
//   mu falls with load (load sensitivity) and peaks at 85-95 C (temperature heats with slip power).
// Driveline: engine inertia, auto/manual 6-speed box, clutch with torque capacity, clutch-pack LSD
//   (preload + ramp), AWD centre split with a viscous coupling; engine, clutch, diffs and the four
//   wheel spins are integrated together implicitly (5x5 solve per substep, tyre slope linearised),
//   so wheel spin, lock-up and clutch slip are stable at any stiffness.
// Every function here is deterministic: no Math.sin/cos/atan2/exp/pow, fixed iteration order.
import { dsin, dcos, datan, datan2, wrapPi, clamp, smooth, ihash, DEG, PI } from './fmath.js';
import { project, surfaceAt, surfaceName, CURB_BAND, pointAtS } from './track.js';
import { CARS, resolveTune } from './cars.js';

export const SUBSTEPS = 4;
export const G = 9.81;
const RHO = 1.2;
const V_LOW = 1.5;          // m/s: slip denominators never go below this (low-speed regularisation)
const RPM = 30 / PI;        // rad/s -> rpm
const RAD = PI / 30;        // rpm -> rad/s
const K_CLUTCH = 2.0e4;     // implicit clutch lock stiffness (N*m per rad/s at the engine)
const K_LSD = 1.0e4;        // implicit LSD lock stiffness (N*m per rad/s between the half shafts)
const WALL_E = 0.25, WALL_MU = 0.35;
const T_AMB = 25;

const WHEEL_NAMES = ['FL', 'FR', 'RL', 'RR'];

function curveAt(rpmTab, nmTab, rpm) {
  const n = rpmTab.length;
  if (rpm <= rpmTab[0]) return nmTab[0];
  if (rpm >= rpmTab[n - 1]) return nmTab[n - 1];
  let i = 1;
  while (rpmTab[i] < rpm) i++;
  const t = (rpm - rpmTab[i - 1]) / (rpmTab[i] - rpmTab[i - 1]);
  return nmTab[i - 1] + (nmTab[i] - nmTab[i - 1]) * t;
}

/** Build a car at a pose. `index` is the entrant slot (used for deterministic chance). */
export function createCar(carId, tuneIn, pose, index, track, surface) {
  const spec = CARS[carId];
  if (!spec) throw new Error('unknown car ' + carId);
  const tune = resolveTune(carId, tuneIn || {});
  const L = spec.wheelbase, b = spec.cgFront * L, a = L - b;
  const ty = spec.tyre;
  let tpeak = 0;
  for (const [, nm] of spec.torque) if (nm > tpeak) tpeak = nm;
  const P = {
    spec, id: carId, L, a, b, m: spec.mass, Iz: spec.mass * spec.yawRadius * spec.yawRadius, h: spec.cgHeight,
    R: spec.wheelRadius, rpmTab: spec.torque.map(p => p[0]), nmTab: spec.torque.map(p => p[1]), tpeak,
    idle: spec.idleRpm * RAD, redline: spec.redlineRpm * RAD, limiter: spec.limiterRpm * RAD, launch: spec.launchRpm * RAD,
    fr0: 0.05 * tpeak, fr1: 0.09 * tpeak / (spec.redlineRpm * RAD),
    kpk: ty.kappaPeak, tpk: dsin(ty.alphaPeakDeg * DEG) / dcos(ty.alphaPeakDeg * DEG),
    Fz0: spec.mass * G / 4,
    awd: spec.drive === 'awd', split: spec.drive === 'awd' ? tune.awdSplit : 0,
    wet: surface === 'wet' ? 1 : 0,
    halfL: spec.length / 2, halfW: spec.width / 2,
    // body corners for wall contact: front bumper ahead of the front axle, rear behind the rear axle
    cornerF: a + (spec.length - L) * 0.52, cornerR: -(b + (spec.length - L) * 0.48),
  };
  // grip split from the balance tune: >0.5 moves grip to the front, so the car rotates more
  P.gripF = tune.grip * (1 + (tune.balance - 0.5) * 0.24);
  P.gripR = tune.grip * (1 - (tune.balance - 0.5) * 0.24);
  const lockScale = tune.diffLock >= 0.98 ? Infinity : 2 * tune.diffLock;
  P.lsdR = { preload: spec.diff.preload * lockScale, power: spec.diff.power * lockScale, coast: spec.diff.coast * lockScale };
  P.lsdF = spec.frontDiff ? { preload: spec.frontDiff.preload, power: spec.frontDiff.power, coast: spec.frontDiff.coast } : null;
  P.jw = P.awd ? [P.split / 2, P.split / 2, (1 - P.split) / 2, (1 - P.split) / 2] : [0, 0, 0.5, 0.5];
  const wheels = [];
  for (let i = 0; i < 4; i++) {
    const front = i < 2, left = (i & 1) === 0;
    const tr = front ? spec.trackF : spec.trackR;
    wheels.push({
      name: WHEEL_NAMES[i], px: left ? tr / 2 : -tr / 2, pz: front ? a : -b, front, left,
      Iw: front ? spec.wheelInertiaF : spec.wheelInertiaR, driven: P.jw[i] > 0,
      omega: 0, spin: 0, steer: 0, cs: 1, sn: 0,
      slipAngle: 0, slipRatio: 0, load: 0, temp: 80, grip: 0, surface: 'asphalt', surf: 0, skid: 0, smoke: 0, susp: 0,
      mu: 1, fx: 0, fy: 0, dfdk: 0, usage: 0, w0: 0, vref: V_LOW, kappa: 0, tana: 0, vl: 0, vt: 0, power: 0, wx: 0, wz: 0, wy: 0,
      seg: -1, lat: 0, s: 0, surfGrip: 1, surfRoll: 0, surfDrag: 0, brakeT: 0,
    });
  }
  const car = {
    P, tune, index, id: carId, name: spec.name,
    x: pose.x, y: 0, z: pose.z, yaw: pose.yaw, vx: 0, vz: 0, yawRate: 0,
    pitch: 0, roll: 0, groundPitch: 0, groundRoll: 0, bodyPitch: 0, bodyRoll: 0,
    ax: 0, ay: 0, axd: 0, ayd: 0, lateralG: 0, longG: 0,
    speed: 0, forwardSpeed: 0, lateralSpeed: 0, slip: 0, slipRate: 0, drifting: false, driftTime: 0,
    steerAngle: 0, omegaE: P.idle, rpm: spec.idleRpm, gear: 1, clutch: 0, clutchSlip: 0, driveTorque: 0,
    shiftTimer: 0, shiftTo: 1, shiftFrom: 1, shiftCooldown: 0, shiftTick: -1, cutTimer: 0, revTimer: 0, limiterTime: 0,
    boostPressure: 0, boost: 1, boostActive: false, throttleEff: 0, prevDrive: 0, prevUp: false, prevDown: false, prevReset: false,
    escMoment: 0, tcCut: 0, tcI: 0, launchOn: false,
    wheels, seg: -1, s: 0, lat: 0, onRoad: true, offTrack: false, offWheels: 0, collided: 0, impactTick: -1,
    lights: { brake: false, reverse: false, head: false }, backfire: -1, backfireKind: '', distance: 0,
    ctrl: { steer: 0, throttle: 0, brake: 0, handbrake: false, boost: false },
    resets: 0, resetTick: -1, prevS: 0, dsTick: 0, lapStart: -1, raceTime: 0, nx: 0, ny: 1, nz: 0, hw: 0, wl: 0, wr: 0,
    // race bookkeeping (engine/race.js owns these)
    cpCount: 0, lap: 0, lapsDone: 0, progress: 0, raceDist: 0, finished: false, finishTick: -1, position: 0,
  };
  car.lights.head = track && track.time !== 'noon';
  placeOnTrack(car, track, pose.x, pose.z, pose.yaw, true);
  return car;
}

const Q = { seg: 0, u: 0, s: 0, lat: 0, dist: 0, ex: 0, ez: 0 };
const S = { y: 0, nx: 0, ny: 1, nz: 0, hw: 0, wl: 0, wr: 0, code: 0, grip: 1, roll: 0, drag: 0 };

function wheelWorld(car, W, c, sn) {
  W.wx = car.x + W.px * c + W.pz * sn;
  W.wz = car.z - W.px * sn + W.pz * c;
}

/** Query the road under the car and its wheels; sets heights, surfaces and the gravity normal. */
function sampleSurface(car, T, env) {
  const c = dcos(car.yaw), sn = dsin(car.yaw);
  project(T, car.x, car.z, car.seg, Q);
  car.seg = Q.seg; car.s = Q.s; car.lat = Q.lat;
  surfaceAt(T, Q.seg, Q.u, Q.lat, S);
  car.nx = S.nx; car.ny = S.ny; car.nz = S.nz; car.hw = S.hw; car.wl = S.wl; car.wr = S.wr;
  let off = 0;
  for (let i = 0; i < 4; i++) {
    const W = car.wheels[i];
    wheelWorld(car, W, c, sn);
    project(T, W.wx, W.wz, car.seg, Q);
    surfaceAt(T, Q.seg, Q.u, Q.lat, S);
    W.seg = Q.seg; W.lat = Q.lat; W.s = Q.s; W.wy = S.y;
    W.surf = S.code;
    let g = S.grip;
    if (env.wet) g *= S.code === 0 ? 0.72 : S.code === 1 ? 0.62 : 0.80;
    W.surfGrip = g; W.surfRoll = S.roll; W.surfDrag = S.drag;
    if (S.code === 2) off++;
  }
  car.offWheels = off; car.onRoad = off === 0; car.offTrack = off >= 3;
}

/** Put the car on the road at (x, z, yaw), at rest. */
export function placeOnTrack(car, T, x, z, yaw, initial) {
  car.x = x; car.z = z; car.yaw = yaw; car.vx = 0; car.vz = 0; car.yawRate = 0; car.speed = 0; car.forwardSpeed = 0; car.lateralSpeed = 0;
  car.ax = 0; car.ay = 0; car.axd = 0; car.ayd = 0; car.slip = 0; car.slipRate = 0; car.drifting = false;
  car.steerAngle = 0; car.omegaE = car.P.idle; car.gear = 1; car.clutch = 0; car.shiftTimer = 0; car.cutTimer = 0;
  car.boostPressure = 0; car.revTimer = 0; car.driveTorque = 0;
  for (const W of car.wheels) { W.omega = 0; W.steer = 0; W.cs = 1; W.sn = 0; W.fx = 0; W.fy = 0; }
  if (!T) return;
  car.seg = -1;
  sampleSurface(car, T, { wet: car.P.wet });
  finishPose(car, T);
}

/** Reset to the nearest centreline point, facing along the track (input bit 20). */
const RP = { seg: 0, u: 0, x: 0, z: 0, y: 0, tx: 0, tz: 0 };
const RESET_CLEAR = 5, RESET_BACK = 6, RESET_TRIES = 6;
const clearOf = (car, others, x, z) => {
  if (others) for (const o of others) if (o !== car && (o.x - x) * (o.x - x) + (o.z - z) * (o.z - z) < RESET_CLEAR * RESET_CLEAR) return false;
  return true;
};
export function resetToTrack(car, T, events, tick, others) {
  project(T, car.x, car.z, car.seg, Q);
  let x = car.x - Q.ex, z = car.z - Q.ez;
  let yaw = T.heading[Q.seg];
  // never drop the car onto another one: slide back along the lap (never forward, so a reset gains nothing)
  if (!clearOf(car, others, x, z)) {
    const s0 = Q.s;
    for (let k = 1; k <= RESET_TRIES; k++) {
      pointAtS(T, s0 - k * RESET_BACK, RP);
      x = RP.x; z = RP.z; yaw = T.heading[RP.seg];
      if (clearOf(car, others, x, z)) break;
    }
  }
  placeOnTrack(car, T, x, z, yaw, false);
  car.resets++; car.resetTick = tick;
  if (events) events.push({ type: 'reset', car: car.index, tick });
}

function finishPose(car, T) {
  const W = car.wheels, P = car.P;
  const yf = 0.5 * (W[0].wy + W[1].wy), yr = 0.5 * (W[2].wy + W[3].wy);
  const yl = 0.5 * (W[0].wy + W[2].wy), yrr = 0.5 * (W[1].wy + W[3].wy);
  car.y = 0.25 * (W[0].wy + W[1].wy + W[2].wy + W[3].wy);
  car.groundPitch = datan((yr - yf) / P.L);
  car.groundRoll = datan((yl - yrr) / (0.5 * (P.spec.trackF + P.spec.trackR)));
  car.pitch = car.groundPitch + car.bodyPitch;
  car.roll = car.groundRoll + car.bodyRoll;
}

/**
 * The 5x5 implicit driveline solve. Unknowns: engine and four wheel angular speeds.
 * (M/dt + C) w' = M/dt w + tau, where C holds the clutch and LSD locks (stiff dampers), the AWD
 * viscous coupling, brake and rolling-resistance damping and the linearised tyre slope.
 */
const A = new Float64Array(25), Bv = new Float64Array(5), Xv = new Float64Array(5), QQ = new Float64Array(5);
const QC = Float64Array.of(0, 0.5, 0.5, -0.5, -0.5);
const LD = new Float64Array(4), PW = new Float64Array(4);
function solve5() {
  // Gaussian elimination without pivoting: A is symmetric positive definite here.
  for (let k = 0; k < 5; k++) {
    const pk = A[k * 5 + k];
    for (let i = k + 1; i < 5; i++) {
      const f = A[i * 5 + k] / pk;
      if (f === 0) continue;
      for (let j = k; j < 5; j++) A[i * 5 + j] -= f * A[k * 5 + j];
      Bv[i] -= f * Bv[k];
    }
  }
  for (let i = 4; i >= 0; i--) {
    let acc = Bv[i];
    for (let j = i + 1; j < 5; j++) acc -= A[i * 5 + j] * Xv[j];
    Xv[i] = acc / A[i * 5 + i];
  }
}

function driveline(car, dt, tauE, Gr, cap, capR, capF) {
  const P = car.P, Wh = car.wheels, R = P.R, jw = P.jw;
  const Ie = P.spec.engineInertia;
  let clutchMode = cap > 0 ? 0 : 2;     // 0 locked candidate, 1 slipping, 2 open
  let lsdR = capR > 0 ? 0 : 2, lsdF = P.awd && capF > 0 ? 0 : 2;
  let tc = 0, tr = 0, tf = 0;
  for (let iter = 0; iter < 4; iter++) {
    A.fill(0);
    A[0] = Ie / dt; Bv[0] = Ie / dt * car.omegaE + tauE;
    for (let i = 0; i < 4; i++) {
      const W = Wh[i], d = 6 * (i + 1);
      const slope = W.dfdk * R * R / W.vref;
      const cb = W.brakeT / Math.max(Math.abs(W.omega), 0.4);
      A[d] = W.Iw / dt + slope + cb;
      Bv[i + 1] = W.Iw / dt * W.omega - R * W.fx + slope * W.omega;
    }
    if (clutchMode === 0) {
      QQ[0] = 1; QQ[1] = -Gr * jw[0]; QQ[2] = -Gr * jw[1]; QQ[3] = -Gr * jw[2]; QQ[4] = -Gr * jw[3];
      for (let i = 0; i < 5; i++) for (let j = 0; j < 5; j++) A[i * 5 + j] += K_CLUTCH * QQ[i] * QQ[j];
    } else if (clutchMode === 1) {
      Bv[0] -= tc;
      for (let i = 0; i < 4; i++) Bv[i + 1] += Gr * jw[i] * tc;
    }
    if (lsdR === 0) { A[18] += K_LSD; A[24] += K_LSD; A[19] -= K_LSD; A[23] -= K_LSD; }
    else if (lsdR === 1) { Bv[3] -= tr; Bv[4] += tr; }
    if (P.awd) {
      if (lsdF === 0) { A[6] += K_LSD; A[12] += K_LSD; A[7] -= K_LSD; A[11] -= K_LSD; }
      else if (lsdF === 1) { Bv[1] -= tf; Bv[2] += tf; }
      const kv = P.spec.awd.viscous;
      for (let i = 1; i < 5; i++) for (let j = 1; j < 5; j++) A[i * 5 + j] += kv * QC[i] * QC[j];
    }
    solve5();
    let again = false;
    if (clutchMode === 0) {
      const slip = Xv[0] - Gr * (jw[0] * Xv[1] + jw[1] * Xv[2] + jw[2] * Xv[3] + jw[3] * Xv[4]);
      const t = K_CLUTCH * slip;
      if (t > cap || t < -cap) { clutchMode = 1; tc = t > 0 ? cap : -cap; again = true; }
      else tc = t;
    }
    if (lsdR === 0) {
      const t = K_LSD * (Xv[3] - Xv[4]);
      if (t > capR || t < -capR) { lsdR = 1; tr = t > 0 ? capR : -capR; again = true; }
    }
    if (P.awd && lsdF === 0) {
      const t = K_LSD * (Xv[1] - Xv[2]);
      if (t > capF || t < -capF) { lsdF = 1; tf = t > 0 ? capF : -capF; again = true; }
    }
    if (!again) break;
  }
  car.omegaE = Xv[0];
  for (let i = 0; i < 4; i++) Wh[i].omega = Xv[i + 1];
  car.driveTorque = clutchMode === 2 ? 0 : tc * Gr;
  car.clutchSlip = Xv[0] - Gr * (jw[0] * Xv[1] + jw[1] * Xv[2] + jw[2] * Xv[3] + jw[3] * Xv[4]);
}

/** Tyre forces in the wheel frame for longitudinal speed vl and lateral speed vt. */
function tyre(car, W, vl, vt) {
  const P = car.P, ty = P.spec.tyre;
  const avl = vl < 0 ? -vl : vl;
  const vref = avl > V_LOW ? avl : V_LOW;
  const kappa = (W.omega * P.R - vl) / vref;
  const tana = vt / vref;
  const sx = kappa / P.kpk, sy = tana / P.tpk;
  const s2 = sx * sx + sy * sy;
  const s = Math.sqrt(s2);
  let f, fp;
  if (s <= 1) { const q = 1 - s; f = 1 - q * q * q; fp = 3 * q * q; }
  else { const d = s - 1, den = 1 + ty.falloff * d * d; f = ty.slide + (1 - ty.slide) / den; fp = -(1 - ty.slide) * 2 * ty.falloff * d / (den * den); }
  const muFz = W.mu * W.load;
  W.kappa = kappa; W.tana = tana; W.vref = vref; W.vl = vl; W.vt = vt;
  if (s > 1e-9) {
    const g = f / s;
    W.fx = muFz * g * sx;
    W.fy = -muFz * ty.latRatio * g * sy;
    const gp = (fp * s - f) / s2;
    const dg = g + gp * sx * sx / s;
    W.dfdk = dg > 0 ? muFz * dg / P.kpk : 0;
  } else { W.fx = 0; W.fy = 0; W.dfdk = muFz * 3 / P.kpk; }
  W.usage = f;
}

function shift(car, to, tick, events) {
  if (to === car.gear) return;
  car.shiftFrom = car.gear; car.shiftTo = to;
  car.shiftTimer = car.P.spec.shiftTime * (to === -1 || car.gear === -1 ? 1.6 : 1);
  car.shiftCooldown = car.shiftTimer + 0.45;
  car.gear = to;
  car.shiftTick = tick;
  events.push({ type: 'shift', car: car.index, from: car.shiftFrom, to, tick });
  // a big rev-matched blip on a downshift often pops
  if (to > 0 && to < car.shiftFrom && car.rpm > car.P.spec.redlineRpm * 0.5 && (ihash(tick, car.index * 7 + 1) & 3) !== 0) {
    car.backfire = tick; car.backfireKind = 'downshift';
    events.push({ type: 'backfire', car: car.index, kind: 'downshift', tick });
  }
}

/** A standing start arms the launch: the clutch slips until the road speed meets the launch rpm. */
function launchPhase(car, drive, u, Gr, wLaunch) {
  const gs = car.gear === -1 ? -u : u;
  const wG = (Gr < 0 ? -Gr : Gr) * (gs > 0 ? gs : 0) / car.P.R;
  if (!car.launchOn && drive >= 0.05 && gs < 2 && car.clutch < 1) car.launchOn = true;
  if (car.launchOn && (drive < 0.05 || wG >= wLaunch * 0.95)) car.launchOn = false;
  return car.launchOn;
}

function ratio(car, g) {
  const sp = car.P.spec, fd = car.tune.finalDrive;
  if (g >= 1) return sp.gears[g - 1] * fd;
  if (g === -1) return -sp.reverse * fd;
  return 0;
}

/**
 * Advance one car by one tick. `inp` is an unpacked Input; env = { track, wet, tick, held, dt }.
 * `held` (grid and countdown) keeps the brakes on and the clutch out so the engine can rev.
 */
export function stepCar(car, inp, env, events) {
  const P = car.P, sp = P.spec, tn = car.tune, T = env.track, dt = env.dt, tick = env.tick;
  const Wh = car.wheels;
  // ---- inputs -------------------------------------------------------------------------------
  const steerIn = inp.steer / 127;              // + = steer right
  let thrIn = inp.throttle / 15, brkIn = inp.brake / 15;
  const hb = !!inp.handbrake && !env.held;
  const resetEdge = inp.reset && !car.prevReset; car.prevReset = !!inp.reset;
  const upEdge = inp.shiftUp && !car.prevUp; car.prevUp = !!inp.shiftUp;
  const downEdge = inp.shiftDown && !car.prevDown; car.prevDown = !!inp.shiftDown;
  if (resetEdge) { resetToTrack(car, T, events, tick, env.cars); car.collided = 0; return; }
  if (env.held) brkIn = 1;
  // body-frame velocity at the start of the tick
  let c = dcos(car.yaw), sn = dsin(car.yaw);
  let u = car.vx * sn + car.vz * c, wv = car.vx * c - car.vz * sn;
  const speed = Math.sqrt(u * u + wv * wv);
  // reverse: hold the brake at a standstill to back up; in reverse the pedals swap
  if (!env.held) {
    if (car.gear >= 1 && u < 0.5 && brkIn > 0.5 && thrIn < 0.05) { car.revTimer += dt; if (car.revTimer > 0.3) { shift(car, -1, tick, events); car.revTimer = 0; } }
    else if (car.gear === -1 && u > -0.5 && thrIn > 0.3 && brkIn < 0.05) { car.revTimer += dt; if (car.revTimer > 0.08) { shift(car, 1, tick, events); car.revTimer = 0; } }
    else car.revTimer = 0;
  }
  let drive = thrIn, pedal = brkIn;
  if (car.gear === -1) { drive = brkIn; pedal = thrIn; }
  // ---- gearbox ------------------------------------------------------------------------------
  if (car.shiftTimer > 0) car.shiftTimer -= dt;
  if (car.shiftCooldown > 0) car.shiftCooldown -= dt;
  const jw = P.jw;
  const wc = jw[0] * Wh[0].omega + jw[1] * Wh[1].omega + jw[2] * Wh[2].omega + jw[3] * Wh[3].omega;
  if (car.gear >= 1 && car.shiftTimer <= 0) {
    const rpmIn = ratio(car, car.gear) * wc * RPM;
    if (tn.gearbox === 'auto') {
      if (car.shiftCooldown <= 0 && !hb) {          // (locked rears on the handbrake say nothing about road speed)
        // upshift on road speed, not on wheelspin: a slide holds its gear until it lives on the limiter
        const rpmGround = ratio(car, car.gear) * (u > 0 ? u : 0) / P.R * RPM;
        const full = drive > 0.7;
        const upRpm = full ? sp.limiterRpm * 0.975 : sp.redlineRpm * (0.5 + 0.45 * drive);
        const up = full
          ? (rpmIn > upRpm && rpmGround > sp.limiterRpm * 0.80) || rpmGround > sp.limiterRpm * 0.96 || (car.limiterTime > 0.6 && rpmGround > sp.redlineRpm * 0.5)
          : rpmIn > upRpm && rpmGround > upRpm * 0.85;
        const down = car.gear > 1 ? rpmIn * sp.gears[car.gear - 2] / sp.gears[car.gear - 1] : 1e9;
        const braking = pedal > 0.2;
        const sliding = Math.abs(car.slip) > 10 * DEG && speed > 5;
        if (sliding) {
          // in a slide the box holds its gear: up only when it lives on the limiter, down only when it bogs
          // (and only when the next gear would still pull: at road speed it must land in the torque band)
          const nextGround = car.gear < 6 ? rpmGround * sp.gears[car.gear] / sp.gears[car.gear - 1] : 0;
          const pulls = nextGround > sp.redlineRpm * 0.45 && curveAt(P.rpmTab, P.nmTab, nextGround) > 0.84 * P.tpeak &&
            (!sp.turbo || nextGround > sp.turbo.spoolStart + 0.6 * (sp.turbo.spoolFull - sp.turbo.spoolStart));
          if (car.gear < 6 && car.limiterTime > 0.5 && drive > 0.3 && pulls) shift(car, car.gear + 1, tick, events);
          else if (car.gear > 1 && rpmIn < sp.redlineRpm * 0.40 && rpmGround < sp.redlineRpm * 0.40 && down < sp.redlineRpm * 0.85) shift(car, car.gear - 1, tick, events);
        } else if (car.gear < 6 && up && drive > 0.05 && car.clutch > 0.9) shift(car, car.gear + 1, tick, events);
        else if (car.gear > 1 && down < sp.redlineRpm * (braking ? 0.88 : 0.86) &&
          rpmIn < sp.redlineRpm * (braking ? 0.62 : drive > 0.9 ? 0.55 : 0.30 + 0.25 * drive)) shift(car, car.gear - 1, tick, events);
      }
    } else {
      if (upEdge && car.gear < 6) shift(car, car.gear + 1, tick, events);
      else if (downEdge) {
        if (car.gear > 1) {
          const down = rpmIn * sp.gears[car.gear - 2] / sp.gears[car.gear - 1];
          if (down < sp.limiterRpm * 1.02) shift(car, car.gear - 1, tick, events);
        } else if (u < 1.5) shift(car, -1, tick, events);
      }
    }
  } else if (car.gear === -1 && tn.gearbox === 'manual' && upEdge && u > -1.5) shift(car, 1, tick, events);
  const Gr = ratio(car, car.gear);
  const shifting = car.shiftTimer > 0;
  // ---- clutch (automatic: slips to hold the launch rpm, out while shifting or on the handbrake) -
  const inW = Gr * wc;                       // engine speed the gearbox asks for
  const wLaunch = P.idle * 1.25 + (P.launch - P.idle * 1.25) * Math.min(1, drive / 0.6);
  let launching = false;
  if (shifting || env.held || hb || car.gear === 0) car.launchOn = false;
  if (shifting) {
    const ph = 1 - car.shiftTimer / (sp.shiftTime * (car.shiftFrom === -1 || car.shiftTo === -1 ? 1.6 : 1));
    car.clutch = ph < 0.65 ? 0 : (ph - 0.65) / 0.35;
  } else if (env.held || hb || car.gear === 0) car.clutch = Math.max(0, car.clutch - 30 * dt);
  else if (launchPhase(car, drive, u, Gr, wLaunch)) {
    // launch: a slipping clutch regulates the engine at the launch speed (PI on rpm error)
    const e = (car.omegaE - wLaunch) / wLaunch;
    car.clutch = clamp(car.clutch + clamp(10 * e, -6, 4) * dt, 0, 1);
    launching = true;
  } else if (drive < 0.05 && inW < P.idle * 1.2) car.clutch = Math.max(0, car.clutch - 30 * dt);
  else car.clutch = Math.min(1, car.clutch + 9 * dt);
  // ---- turbo, boost, limiter -----------------------------------------------------------------
  const rpm0 = car.omegaE * RPM;
  if (sp.turbo) {
    const t = sp.turbo;
    const target = drive > 0.15 ? clamp((rpm0 - t.spoolStart) / (t.spoolFull - t.spoolStart), 0, 1) * (0.25 + 0.75 * drive) : 0;
    const rate = target > car.boostPressure ? (0.35 + 0.65 * rpm0 / sp.redlineRpm) / t.lag : 7;
    const before = car.boostPressure;
    car.boostPressure += (target - car.boostPressure) * Math.min(1, rate * dt);
    if (before > 0.45 && drive < 0.1 && car.prevDrive >= 0.4) events.push({ type: 'blowoff', car: car.index, pressure: before, tick });
  }
  car.boostActive = !!inp.boost && car.boost > 0 && drive > 0.2 && car.gear !== 0 && !shifting && !env.held;
  if (car.boostActive) {
    car.boost -= sp.boost.drain * dt;
    if (car.boost <= 0) { car.boost = 0; car.boostActive = false; events.push({ type: 'boostEmpty', car: car.index, tick }); }
  } else {
    const dr = car.drifting ? clamp((Math.abs(car.slip) - 12 * DEG) / (30 * DEG), 0.3, 1) * clamp(speed / 20, 0, 1) : 0;
    car.boost = Math.min(1, car.boost + (sp.boost.recharge + sp.boost.driftRecharge * dr) * dt);
  }
  // time spent on the limiter with the clutch in (a free-revving engine never asks for a gear)
  car.limiterTime = (car.omegaE > P.limiter * 0.95 || car.cutTimer > 0) && car.clutch > 0.9 ? car.limiterTime + dt : Math.max(0, car.limiterTime - 2 * dt);
  if (car.cutTimer > 0) car.cutTimer -= dt;
  else if (car.omegaE > P.limiter) {
    car.cutTimer = 0.045;
    if ((ihash(tick, car.index * 13 + 5) & 3) === 0) { car.backfire = tick; car.backfireKind = 'limiter'; events.push({ type: 'backfire', car: car.index, kind: 'limiter', tick }); }
  }
  // lift-off pops
  if (car.prevDrive > 0.7 && drive < 0.1 && rpm0 > sp.redlineRpm * 0.55 && (ihash(tick, car.index * 3 + 11) % 5) < 3) {
    car.backfire = tick; car.backfireKind = 'lift'; events.push({ type: 'backfire', car: car.index, kind: 'lift', tick });
  }
  car.prevDrive = drive;
  // ---- assists ------------------------------------------------------------------------------
  const beta = speed > 1 ? car.slip : 0;
  const ab = beta < 0 ? -beta : beta;
  // traction control on the driven wheels' slip ratio
  let thr = drive;
  if (tn.traction > 0 && thr > 0 && car.gear !== 0) {
    let kmax = 0;
    for (let i = 0; i < 4; i++) if (Wh[i].driven && Wh[i].kappa > kmax) kmax = Wh[i].kappa;
    const kt = P.kpk * (1.15 + 2.6 * (1 - tn.traction));
    const e = clamp((kmax - kt) / kt, -1, 3);
    car.tcI = clamp(car.tcI + 2.4 * e * dt, 0, 0.9);             // PI on the driven wheels' slip ratio
    car.tcCut = clamp(car.tcI + 0.22 * e, 0, 0.9 * tn.traction);
  } else { car.tcI = Math.max(0, car.tcI - 6 * dt); car.tcCut = Math.max(0, car.tcCut - 6 * dt); }
  // traction control trims engine torque; during a launch it trims the slipping clutch instead,
  // so the engine stays on its launch speed and the two never fight
  if (!launching) thr *= 1 - car.tcCut;
  else if (car.omegaE > wLaunch * 1.06) thr *= clamp(1 - (car.omegaE / wLaunch - 1.06) * 10, 0.05, 1);  // launch control holds the revs
  // stability: damps the growth of body slip past the drift window, never a held angle
  let esc = 0;
  if (tn.stability > 0 && speed > 3) {
    const growing = beta * car.slipRate > 0;
    if (growing) {
      const w = smooth(22 * DEG, 48 * DEG, ab);
      esc += tn.stability * P.Iz * 4.2 * w * car.slipRate;
      thr *= 1 - tn.stability * 0.55 * w * clamp(Math.abs(car.slipRate) / 1.5, 0, 1);
    }
    const bmax = (72 - 20 * tn.stability) * DEG;
    if (ab > bmax) esc += (beta > 0 ? 1 : -1) * tn.stability * P.Iz * 9 * (ab - bmax);
    const lim = 0.35 * P.m * G * P.L * 0.5;
    esc = clamp(esc, -lim, lim);
  }
  car.escMoment = esc;
  car.throttleEff = thr;
  // ---- steering: speed-sensitive lock, extra countersteer range, drift assist --------------
  const lock = tn.steerLock * DEG;
  const sf = 1 / (1 + (speed / sp.steerRefSpeed) * (speed / sp.steerRefSpeed));
  let dP = -steerIn * lock * (0.28 + 0.72 * sf);         // + = left
  const cmax = sp.countersteerDeg * DEG;
  const counter = dP * beta > 0;                          // steering toward the slide
  if (counter) { const rng = Math.max(lock * (0.28 + 0.72 * sf), Math.min(cmax, ab + 12 * DEG)); dP = -steerIn * rng; }
  let target = dP;
  if (tn.driftAssist > 0 && u > 2) {
    const dv = datan2(wv + car.yawRate * P.a, u);         // front-axle velocity direction
    const wA = tn.driftAssist * smooth(3 * DEG, 11 * DEG, ab);
    if (counter) target = (dP > 0) ? Math.max(dP, wA * dv) : Math.min(dP, wA * dv);
    else target = dP + wA * dv;
  }
  target = clamp(target, -cmax, cmax);
  const rate = sp.steerRate * (target * car.steerAngle < 0 || Math.abs(target) < Math.abs(car.steerAngle) ? 1.7 : 1) / (1 + speed / 45);
  const dmax = rate * dt;
  car.steerAngle += clamp(target - car.steerAngle, -dmax, dmax);
  {
    const d = car.steerAngle, td = dsin(d) / dcos(d), L = P.L, tf = sp.trackF, ack = sp.ackermann;
    const dl = datan(L * td / (L - 0.5 * tf * td)), dr = datan(L * td / (L + 0.5 * tf * td));
    Wh[0].steer = d + ack * (dl - d); Wh[1].steer = d + ack * (dr - d);
    Wh[0].cs = dcos(Wh[0].steer); Wh[0].sn = dsin(Wh[0].steer);
    Wh[1].cs = dcos(Wh[1].steer); Wh[1].sn = dsin(Wh[1].steer);
  }
  // ---- surface and loads ---------------------------------------------------------------------
  sampleSurface(car, T, env);
  const Wt = P.m * G * car.ny;                                       // m g cos(theta)
  const v2 = speed * speed;
  const down = 0.5 * RHO * sp.ClA * v2;
  const dLong = P.m * car.ax * P.h / P.L;
  const dLatF = P.m * car.ay * P.h / sp.trackF * sp.rollDistF;
  const dLatR = P.m * car.ay * P.h / sp.trackR * (1 - sp.rollDistF);
  const wf = Wt * P.b / P.L + down * sp.aeroFront, wr = Wt * P.a / P.L + down * (1 - sp.aeroFront);
  const Ld = LD;
  Ld[0] = 0.5 * wf - 0.5 * dLong - dLatF; Ld[1] = 0.5 * wf - 0.5 * dLong + dLatF;
  Ld[2] = 0.5 * wr + 0.5 * dLong - dLatR; Ld[3] = 0.5 * wr + 0.5 * dLong + dLatR;
  const total = Wt + down, minL = 0.05 * total;
  let deficit = 0, spare = 0;
  for (let i = 0; i < 4; i++) { if (Ld[i] < minL) { deficit += minL - Ld[i]; Ld[i] = minL; } else spare += Ld[i] - minL; }
  if (deficit > 0 && spare > 0) for (let i = 0; i < 4; i++) if (Ld[i] > minL) Ld[i] -= deficit * (Ld[i] - minL) / spare;
  for (let i = 0; i < 4; i++) {
    const W = Wh[i];
    W.load = Ld[i];
    let ls = 1 - sp.tyre.loadSens * (W.load / P.Fz0 - 1);
    ls = ls < 0.6 ? 0.6 : ls > 1.25 ? 1.25 : ls;
    const td = (W.temp - 90) / 45;
    let tf = 1 - 0.10 * td * td; if (tf < 0.8) tf = 0.8;
    W.mu = sp.tyre.mu * ls * tf * W.surfGrip * (W.front ? P.gripF : P.gripR);
  }
  // ---- brakes (ABS on the pedal; the handbrake locks the rears) ------------------------------
  const bT = pedal * sp.brakeTorque, bias = tn.brakeBias;
  for (let i = 0; i < 4; i++) {
    const W = Wh[i];
    let t = bT * (W.front ? bias : 1 - bias) * 0.5;
    // ABS: never ask more torque than the tyre can return with what lateral grip leaves
    const fyUse = W.mu * W.load > 1 ? Math.abs(W.fy) / (W.mu * W.load) : 0;
    const rem = Math.sqrt(Math.max(0.04, 1 - fyUse * fyUse));
    const absCap = W.mu * W.load * P.R * rem * 0.985;
    if (t > absCap && speed > 2) t = absCap;
    if (!W.front && hb) t += sp.handbrakeTorque;
    t += (sp.Crr + W.surfRoll) * W.load * P.R;
    W.brakeT = t;
  }
  // ---- clutch, diff capacities ---------------------------------------------------------------
  const boostMul = car.boostActive ? sp.boost.torqueMul : 1;
  const turboMul = sp.turbo ? sp.turbo.naFrac + (1 - sp.turbo.naFrac) * car.boostPressure : 1;
  const cap = car.gear === 0 ? 0 : car.clutch * sp.clutchMax * (car.boostActive ? 1.4 : 1) * (launching ? 1 - car.tcCut : 1);
  const tin = Math.abs(car.driveTorque);
  const coast = car.driveTorque < 0;
  const lr = P.lsdR;
  const capR0 = lr.preload === Infinity ? Infinity : lr.preload + (coast ? lr.coast : lr.power) * tin * (1 - P.split) * 0.5;
  const lf = P.lsdF;
  const capF0 = lf ? lf.preload + (coast ? lf.coast : lf.power) * tin * P.split * 0.5 : 0;
  // ---- substeps ------------------------------------------------------------------------------
  const n = SUBSTEPS, h = dt / n;
  let sumFl = 0, sumFf = 0;
  const cutting = car.cutTimer > 0;
  const blip = shifting && car.shiftTo < car.shiftFrom && car.shiftTo > 0;
  const upCut = shifting && car.shiftTo > car.shiftFrom && car.shiftFrom > 0;   // ignition cut drops the revs to the next gear
  const fric0 = P.fr0, fric1 = P.fr1, eff = sp.efficiency;
  const kIdle = 0.012 * P.tpeak;
  const pw = PW; pw[0] = 0; pw[1] = 0; pw[2] = 0; pw[3] = 0;
  for (let k = 0; k < n; k++) {
    c = dcos(car.yaw); sn = dsin(car.yaw);
    u = car.vx * sn + car.vz * c; wv = car.vx * c - car.vz * sn;
    const r = car.yawRate;
    for (let i = 0; i < 4; i++) {
      const W = Wh[i];
      const vlat = wv + r * W.pz, vlong = u - r * W.px;
      const vl = vlong * W.cs + vlat * W.sn, vt = vlat * W.cs - vlong * W.sn;
      tyre(car, W, vl, vt);
      W.w0 = W.omega;
    }
    // engine torque at the current engine speed
    const we = car.omegaE;
    const fr = fric0 + fric1 * (we > 0 ? we : 0);
    let te;
    if (blip) {
      const tgt = Gr * wc;
      te = clamp(sp.engineInertia * 30 * (tgt - we), -fr, curveAt(P.rpmTab, P.nmTab, we * RPM) * turboMul);
    } else if (upCut) {
      te = clamp(sp.engineInertia * 30 * (Gr * wc - we), -fr - 0.3 * P.tpeak, 0);
    } else if (cutting) te = -fr;
    else te = thr * curveAt(P.rpmTab, P.nmTab, we * RPM) * turboMul * boostMul * eff - (1 - thr) * fr;
    if (we < P.idle) te += kIdle * (P.idle - we) * 4;
    driveline(car, h, te, Gr, cap, capR0, capF0);
    // the chassis feels the same linearised tyre force the implicit wheel solve used
    let Fl = 0, Ff = 0, Mz = 0;
    for (let i = 0; i < 4; i++) {
      const W = Wh[i];
      W.fx += W.dfdk * P.R * (W.omega - W.w0) / W.vref;
      const fl = W.fx * W.sn + W.fy * W.cs, ff = W.fx * W.cs - W.fy * W.sn;
      Fl += fl; Ff += ff; Mz += W.pz * fl - W.px * ff;
      const sx = W.omega * P.R - W.vl;
      pw[i] += (Math.abs(W.fx * sx) + Math.abs(W.fy * W.vt)) / n;
    }
    // aero drag, runoff drag, in-plane gravity, stability moment
    const v = Math.sqrt(u * u + wv * wv);
    const kd = 0.5 * RHO * sp.CdA * v;
    let fx = Ff - kd * u, fl2 = Fl - kd * wv;
    let rd = 0;
    for (let i = 0; i < 4; i++) rd += Wh[i].surfDrag;
    if (rd > 0 && v > 0.05) { const dd = P.m * rd * 0.25 * v / (v + 3); fx -= dd * u / v; fl2 -= dd * wv / v; }
    const gx = G * car.ny * car.nx, gz = G * car.ny * car.nz;    // in-plane gravity (world)
    fx += P.m * (gx * sn + gz * c); fl2 += P.m * (gx * c - gz * sn);
    const axw = (fx * sn + fl2 * c) / P.m, azw = (fx * c - fl2 * sn) / P.m;
    car.vx += axw * h; car.vz += azw * h;
    car.yawRate += (Mz + esc) / P.Iz * h;
    car.x += car.vx * h; car.z += car.vz * h; car.yaw += car.yawRate * h;
    sumFl += Fl; sumFf += Ff;
  }
  car.yaw = wrapPi(car.yaw);
  // ---- load transfer filter (tyre forces at the ground act h below the centre of mass) -------
  const aLong = sumFf / n / P.m, aLat = sumFl / n / P.m;
  const wn = 10.5, z2 = 2 * 0.72 * wn;
  car.axd += (wn * wn * (aLong - car.ax) - z2 * car.axd) * dt; car.ax += car.axd * dt;
  car.ayd += (wn * wn * (aLat - car.ay) - z2 * car.ayd) * dt; car.ay += car.ayd * dt;
  car.longG = car.ax / G; car.lateralG = car.ay / G;
  car.bodyRoll = sp.look.roll * car.ay;
  car.bodyPitch = -sp.look.pitch * car.ax;
  // ---- body state ----------------------------------------------------------------------------
  c = dcos(car.yaw); sn = dsin(car.yaw);
  u = car.vx * sn + car.vz * c; wv = car.vx * c - car.vz * sn;
  car.forwardSpeed = u; car.lateralSpeed = wv;
  car.speed = Math.sqrt(u * u + wv * wv);
  const nb = car.speed > 1 ? datan2(wv, u > 0.1 ? u : (u < -0.1 ? -u : 0.1)) : 0;
  car.slipRate = clamp(wrapPi(nb - car.slip) / dt, -20, 20);
  car.slip = nb;
  const drifting = Math.abs(nb) >= 12 * DEG && car.speed >= 25 / 3.6 && u > 0;
  car.driftTime = drifting ? car.driftTime + dt : 0;
  car.drifting = drifting;
  car.distance += car.speed * dt;
  car.rpm = car.omegaE * RPM;
  // ---- per-wheel outputs ---------------------------------------------------------------------
  for (let i = 0; i < 4; i++) {
    const W = Wh[i];
    W.spin += W.omega * dt;
    if (W.spin > 6.283185307179586 || W.spin < -6.283185307179586) W.spin -= 6.283185307179586 * Math.trunc(W.spin / 6.283185307179586);
    W.slipAngle = datan(W.tana);
    W.slipRatio = W.kappa;
    W.grip = W.usage > 1 ? 1 : W.usage;
    W.surface = surfaceName(T, W.surf);
    const sx = W.omega * P.R - W.vl;
    const slipV = Math.sqrt(sx * sx + W.vt * W.vt);
    const onPaved = W.surf !== 2;
    W.skid = onPaved ? clamp((slipV - 1.8) / 5, 0, 1) * clamp(W.load / P.Fz0, 0, 1.2) : 0;
    W.smoke = onPaved ? clamp((slipV - 4) / 9, 0, 1) * clamp((W.temp - 35) / 55, 0.35, 1) : clamp((slipV - 2) / 6, 0, 1);
    // tyre temperature: slip power and rolling work heat, air and speed cool
    const heat = pw[i] * 5.0e-5 + W.load * car.speed * 2.2e-5;
    const cool = (W.temp - T_AMB) * (0.012 + 0.0011 * car.speed);
    W.temp += (heat - cool) * dt;
    let sus = (W.load - P.Fz0) / (P.Fz0 / 0.045);
    if (W.surf === 1) sus += 0.007 * dsin(W.s * 11.0 + i);
    W.susp = clamp(sus, -0.09, 0.09);
  }
  // ---- walls ---------------------------------------------------------------------------------
  car.collided = 0;
  collideWalls(car, T, events, tick);
  // ---- lights and pose -----------------------------------------------------------------------
  car.lights.brake = pedal > 0.05 || hb;
  car.lights.reverse = car.gear === -1;
  car.ctrl.steer = inp.steer; car.ctrl.throttle = thrIn; car.ctrl.brake = brkIn; car.ctrl.handbrake = hb; car.ctrl.boost = car.boostActive;
  finishPose(car, T);
}

/**
 * Inverse of the steering map in stepCar (ignoring the slew limit): the steer input (-127..127,
 * + = right) whose target road-wheel angle is `delta` (rad, + = left). The AI drives with it.
 */
export function steerInputFor(car, delta) {
  const P = car.P, sp = P.spec, tn = car.tune;
  const c = dcos(car.yaw), sn = dsin(car.yaw);
  const u = car.vx * sn + car.vz * c, wv = car.vx * c - car.vz * sn;
  const speed = Math.sqrt(u * u + wv * wv);
  const beta = speed > 1 ? car.slip : 0, ab = beta < 0 ? -beta : beta;
  const lock = tn.steerLock * DEG;
  const sf = 1 / (1 + (speed / sp.steerRefSpeed) * (speed / sp.steerRefSpeed));
  const base = lock * (0.28 + 0.72 * sf);
  const cmax = sp.countersteerDeg * DEG;
  let dP = delta;
  if (tn.driftAssist > 0 && u > 2) {
    const dv = datan2(wv + car.yawRate * P.a, u);
    const wA = tn.driftAssist * smooth(3 * DEG, 11 * DEG, ab);
    const a = delta - wA * dv;
    if (a * beta <= 0) dP = a;           // steering into the turn (or straight): assist adds on top
    else dP = delta;                     // countersteering beyond the assist
  }
  const counter = dP * beta > 0;
  const range = counter ? Math.max(base, Math.min(cmax, ab + 12 * DEG)) : base;
  const s = clamp(-dP / range, -1, 1);
  return Math.round(s * 127);
}

const QW = { seg: 0, u: 0, s: 0, lat: 0, dist: 0, ex: 0, ez: 0 };
/** Push the body's four corners out of the barrier lines with restitution and friction. */
function collideWalls(car, T, events, tick) {
  const P = car.P;
  const c = dcos(car.yaw), sn = dsin(car.yaw);
  let total = 0, hx = 0, hz = 0, hnx = 0, hnz = 0;
  for (let k = 0; k < 4; k++) {
    const px = (k & 1) ? -P.halfW : P.halfW;
    const pz = k < 2 ? P.cornerF : P.cornerR;
    const qx = car.x + px * c + pz * sn, qz = car.z - px * sn + pz * c;
    project(T, qx, qz, car.seg, QW);
    const j = QW.seg + 1 === T.n ? 0 : QW.seg + 1;
    const wl = T.wl[QW.seg] + (T.wl[j] - T.wl[QW.seg]) * QW.u;
    const wr = T.wr[QW.seg] + (T.wr[j] - T.wr[QW.seg]) * QW.u;
    let pen = 0;
    if (QW.lat > wl) pen = QW.lat - wl;
    else if (QW.lat < -wr) pen = -wr - QW.lat;
    if (pen <= 0 || QW.dist < 1e-6) continue;
    const nx = -QW.ex / QW.dist, nz = -QW.ez / QW.dist;     // points back toward the track
    car.x += nx * pen; car.z += nz * pen;
    const rx = qx - car.x, rz = qz - car.z;
    const vcx = car.vx + car.yawRate * rz, vcz = car.vz - car.yawRate * rx;
    const vn = vcx * nx + vcz * nz;
    if (vn >= 0) continue;
    const rn = rz * nx - rx * nz;
    const jn = -(1 + WALL_E) * vn / (1 / P.m + rn * rn / P.Iz);
    const tx = -nz, tz = nx;
    const vt = vcx * tx + vcz * tz;
    const rt = rz * tx - rx * tz;
    let jt = -vt / (1 / P.m + rt * rt / P.Iz);
    const lim = WALL_MU * jn;
    if (jt > lim) jt = lim; else if (jt < -lim) jt = -lim;
    const Jx = jn * nx + jt * tx, Jz = jn * nz + jt * tz;
    car.vx += Jx / P.m; car.vz += Jz / P.m;
    car.yawRate += (rz * Jx - rx * Jz) / P.Iz;
    total += jn; hx = qx; hz = qz; hnx = nx; hnz = nz;
  }
  if (total > 0) {
    car.collided += total;
    if (total > 250) {
      car.impactTick = tick;
      events.push({ type: 'crash', car: car.index, impulse: total, dv: total / P.m, x: hx, y: car.y + 0.4, z: hz, nx: hnx, nz: hnz, wall: true, tick });
    }
  }
}

/** Car-to-car contact: two circles per car along its axis, impulses with restitution and friction. */
export function collideCars(A, B, events, tick) {
  const pa = A.P, pb = B.P;
  const dx0 = B.x - A.x, dz0 = B.z - A.z;
  const reach = pa.halfL + pb.halfL;
  if (dx0 * dx0 + dz0 * dz0 > reach * reach) return 0;
  const ca = dcos(A.yaw), sa = dsin(A.yaw), cb = dcos(B.yaw), sb = dsin(B.yaw);
  const ra = pa.halfW * 1.02, rb = pb.halfW * 1.02;
  const oa = pa.halfL - pa.halfW, ob = pb.halfL - pb.halfW;
  let total = 0, hx = 0, hz = 0;
  // Deep overlap (centres closer than 3/4 of the two widths, e.g. two cars crossed over each other):
  // the four circle pairs push in directions that cancel, so first separate along the line between
  // the centres (A's lateral axis when they coincide) and stop the closing speed along it.
  const dc2 = dx0 * dx0 + dz0 * dz0, deep = 0.75 * (ra + rb);
  if (dc2 < deep * deep) {
    let nx = ca, nz = -sa;
    const dc = Math.sqrt(dc2);
    if (dc > 1e-6) { nx = dx0 / dc; nz = dz0 / dc; }
    const pen = (ra + rb) - dc, im = 1 / pa.m + 1 / pb.m;
    A.x -= nx * pen * (1 / pa.m) / im; A.z -= nz * pen * (1 / pa.m) / im;
    B.x += nx * pen * (1 / pb.m) / im; B.z += nz * pen * (1 / pb.m) / im;
    const vn = (B.vx - A.vx) * nx + (B.vz - A.vz) * nz;
    if (vn < 0) {
      const jn = -(1 + 0.2) * vn / im;
      A.vx -= jn * nx / pa.m; A.vz -= jn * nz / pa.m; B.vx += jn * nx / pb.m; B.vz += jn * nz / pb.m;
      total += jn;
    }
    hx = 0.5 * (A.x + B.x); hz = 0.5 * (A.z + B.z);
  }
  for (let i = 0; i < 2; i++) {
    const fa = i === 0 ? oa : -oa;
    const ax = A.x + fa * sa, az = A.z + fa * ca;
    for (let j = 0; j < 2; j++) {
      const fb = j === 0 ? ob : -ob;
      const bx = B.x + fb * sb, bz = B.z + fb * cb;
      const dx = bx - ax, dz = bz - az;
      const d2 = dx * dx + dz * dz, rr = ra + rb;
      if (d2 >= rr * rr || d2 < 1e-9) continue;
      const d = Math.sqrt(d2), nx = dx / d, nz = dz / d, pen = rr - d;
      // contact point halfway along the overlap
      const cx = ax + nx * (ra - pen * 0.5), cz = az + nz * (ra - pen * 0.5);
      const im = 1 / pa.m + 1 / pb.m;
      A.x -= nx * pen * (1 / pa.m) / im; A.z -= nz * pen * (1 / pa.m) / im;
      B.x += nx * pen * (1 / pb.m) / im; B.z += nz * pen * (1 / pb.m) / im;
      const rax = cx - A.x, raz = cz - A.z, rbx = cx - B.x, rbz = cz - B.z;
      const vax = A.vx + A.yawRate * raz, vaz = A.vz - A.yawRate * rax;
      const vbx = B.vx + B.yawRate * rbz, vbz = B.vz - B.yawRate * rbx;
      const rvx = vbx - vax, rvz = vbz - vaz;
      const vn = rvx * nx + rvz * nz;
      if (vn >= 0) continue;
      const rna = raz * nx - rax * nz, rnb = rbz * nx - rbx * nz;
      const jn = -(1 + 0.2) * vn / (im + rna * rna / pa.Iz + rnb * rnb / pb.Iz);
      const tx = -nz, tz = nx;
      const vt = rvx * tx + rvz * tz;
      const rta = raz * tx - rax * tz, rtb = rbz * tx - rbx * tz;
      let jt = -vt / (im + rta * rta / pa.Iz + rtb * rtb / pb.Iz);
      const lim = 0.3 * jn;
      if (jt > lim) jt = lim; else if (jt < -lim) jt = -lim;
      const Jx = jn * nx + jt * tx, Jz = jn * nz + jt * tz;
      A.vx -= Jx / pa.m; A.vz -= Jz / pa.m; A.yawRate -= (raz * Jx - rax * Jz) / pa.Iz;
      B.vx += Jx / pb.m; B.vz += Jz / pb.m; B.yawRate += (rbz * Jx - rbx * Jz) / pb.Iz;
      total += jn; hx = cx; hz = cz;
    }
  }
  if (total > 0) {
    A.collided += total; B.collided += total;
    if (total > 150) {
      A.impactTick = tick; B.impactTick = tick;
      events.push({ type: 'crash', car: A.index, other: B.index, impulse: total, x: hx, y: 0.5 * (A.y + B.y) + 0.4, z: hz, wall: false, tick });
    }
  }
  return total;
}

/** Every number that carries the car's future, in a fixed order, for the state hash. */
export function carState(car, mix) {
  mix(car.x); mix(car.z); mix(car.yaw); mix(car.vx); mix(car.vz); mix(car.yawRate);
  mix(car.ax); mix(car.ay); mix(car.axd); mix(car.ayd); mix(car.slip); mix(car.slipRate); mix(car.driftTime);
  mix(car.steerAngle); mix(car.omegaE); mix(car.gear); mix(car.clutch); mix(car.driveTorque);
  mix(car.shiftTimer); mix(car.shiftTo); mix(car.shiftFrom); mix(car.shiftCooldown); mix(car.cutTimer); mix(car.revTimer); mix(car.limiterTime);
  mix(car.boostPressure); mix(car.boost); mix(car.boostActive ? 1 : 0); mix(car.prevDrive); mix(car.tcCut); mix(car.tcI); mix(car.launchOn ? 1 : 0);
  mix(car.prevUp ? 1 : 0); mix(car.prevDown ? 1 : 0); mix(car.prevReset ? 1 : 0);
  mix(car.seg); mix(car.distance); mix(car.resets);
  for (let i = 0; i < 4; i++) {
    const W = car.wheels[i];
    mix(W.omega); mix(W.spin); mix(W.temp); mix(W.fx); mix(W.fy); mix(W.kappa);
  }
  mix(car.cpCount); mix(car.finished ? 1 : 0); mix(car.finishTick);
}
