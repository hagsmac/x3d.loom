// loom:sim
// The four KANSEI cars. Fictional machines with game-tuned numbers (CONTRACT.md section 7);
// the measured handling card is docs/HANDLING-CARD.md, checked by tests/handling.test.mjs.
//
// Frames: car local +Z forward, +X left, +Y up. Torque curves are crank torque in N*m at the
// listed rpm (turbo cars: at full boost). Tyre: brush-type combined-slip model, see engine/car.js.

const KOI = {
  id: 'koi', name: 'KOI', blurb: 'Light, flickable, honest. The car that teaches you to drift.',
  drive: 'rwd', aspiration: 'na', display: { hp: 210, nm: 230, kg: 1020, layout: 'FR, naturally aspirated I4' },
  mass: 1020, yawRadius: 1.13, wheelbase: 2.38, cgFront: 0.52, cgHeight: 0.46, trackF: 1.44, trackR: 1.44,
  length: 3.98, width: 1.70, wheelRadius: 0.30, wheelInertiaF: 0.85, wheelInertiaR: 0.95,
  engineInertia: 0.13, idleRpm: 950, redlineRpm: 8000, limiterRpm: 8300,
  torque: [[800, 78], [2000, 102], [3000, 124], [4000, 150], [5000, 186], [6000, 219], [6500, 230], [7000, 222], [7500, 205], [8000, 184], [8500, 158]],
  turbo: null,
  gears: [3.35, 2.25, 1.66, 1.30, 1.06, 0.88], reverse: 3.30, finalDrive: 4.30, efficiency: 0.78,
  shiftTime: 0.24, launchRpm: 3000, clutchMax: 380,
  diff: { preload: 50, power: 0.45, coast: 0.25 }, frontDiff: null, awd: null,
  brakeTorque: 4600, handbrakeTorque: 1500, brakeBias: 0.64,
  tyre: { mu: 1.12, latRatio: 0.97, loadSens: 0.11, alphaPeakDeg: 8.6, kappaPeak: 0.11, slide: 0.72, falloff: 0.40 },
  CdA: 1.00, ClA: 0.12, aeroFront: 0.45, Crr: 0.013, rollDistF: 0.56,
  steerLockDeg: 38, steerRefSpeed: 27, countersteerDeg: 58, ackermann: 0.45, steerRate: 4.6,
  boost: { torqueMul: 1.35, drain: 0.20, recharge: 0.025, driftRecharge: 0.11 },
  look: { roll: 0.0085, pitch: 0.0065 },
  defaults: { grip: 1, steerLock: 38, finalDrive: 4.30, brakeBias: 0.64, diffLock: 0.7, balance: 0.54, stability: 0.5, driftAssist: 0.6, traction: 0, gearbox: 'auto', awdSplit: 0 },
};

const RONIN = {
  id: 'ronin', name: 'RONIN', blurb: 'Turbocharged all-rounder. Balanced, loyal, quick.',
  drive: 'rwd', aspiration: 'turbo', display: { hp: 380, nm: 470, kg: 1290, layout: 'FR, turbocharged I6' },
  mass: 1290, yawRadius: 1.24, wheelbase: 2.56, cgFront: 0.53, cgHeight: 0.48, trackF: 1.52, trackR: 1.53,
  length: 4.42, width: 1.79, wheelRadius: 0.32, wheelInertiaF: 1.05, wheelInertiaR: 1.15,
  engineInertia: 0.17, idleRpm: 850, redlineRpm: 7200, limiterRpm: 7500,
  torque: [[800, 200], [2000, 330], [3000, 440], [3500, 470], [4500, 470], [5500, 455], [6000, 440], [6500, 415], [7000, 380], [7500, 335]],
  turbo: { naFrac: 0.56, spoolStart: 2300, spoolFull: 4300, lag: 0.50 },
  gears: [3.25, 2.10, 1.52, 1.18, 0.96, 0.80], reverse: 3.20, finalDrive: 3.90, efficiency: 0.87,
  shiftTime: 0.17, launchRpm: 3800, clutchMax: 820,
  diff: { preload: 90, power: 0.50, coast: 0.30 }, frontDiff: null, awd: null,
  brakeTorque: 6200, handbrakeTorque: 1900, brakeBias: 0.63,
  tyre: { mu: 1.14, latRatio: 0.97, loadSens: 0.11, alphaPeakDeg: 8.2, kappaPeak: 0.10, slide: 0.79, falloff: 0.30 },
  CdA: 1.10, ClA: 0.25, aeroFront: 0.45, Crr: 0.013, rollDistF: 0.56,
  steerLockDeg: 37, steerRefSpeed: 28, countersteerDeg: 57, ackermann: 0.45, steerRate: 4.3,
  boost: { torqueMul: 1.35, drain: 0.20, recharge: 0.025, driftRecharge: 0.11 },
  look: { roll: 0.0075, pitch: 0.006 },
  defaults: { grip: 1, steerLock: 37, finalDrive: 3.90, brakeBias: 0.63, diffLock: 0.6, balance: 0.5, stability: 0.5, driftAssist: 0.5, traction: 0, gearbox: 'auto', awdSplit: 0 },
};

const TEMPEST = {
  id: 'tempest', name: 'TEMPEST', blurb: 'All-wheel-drive grip monster. Fastest lap, hardest to slide.',
  drive: 'awd', aspiration: 'turbo', display: { hp: 520, nm: 620, kg: 1480, layout: 'F4, twin-turbo V6, AWD' },
  mass: 1480, yawRadius: 1.27, wheelbase: 2.62, cgFront: 0.56, cgHeight: 0.47, trackF: 1.57, trackR: 1.57,
  length: 4.52, width: 1.86, wheelRadius: 0.33, wheelInertiaF: 1.15, wheelInertiaR: 1.20,
  engineInertia: 0.20, idleRpm: 900, redlineRpm: 7000, limiterRpm: 7300,
  torque: [[800, 230], [2000, 380], [3000, 560], [3500, 620], [5000, 620], [6000, 585], [6500, 570], [7000, 525], [7500, 470]],
  turbo: { naFrac: 0.52, spoolStart: 2600, spoolFull: 4400, lag: 0.55 },
  gears: [3.10, 2.05, 1.50, 1.18, 0.97, 0.81], reverse: 3.00, finalDrive: 3.70, efficiency: 0.84,
  shiftTime: 0.09, launchRpm: 4600, clutchMax: 1250,
  diff: { preload: 80, power: 0.45, coast: 0.25 }, frontDiff: { preload: 25, power: 0.12, coast: 0.05 },
  awd: { split: 0.34, viscous: 18 },
  brakeTorque: 8200, handbrakeTorque: 2300, brakeBias: 0.62,
  tyre: { mu: 1.24, latRatio: 0.98, loadSens: 0.10, alphaPeakDeg: 7.6, kappaPeak: 0.10, slide: 0.76, falloff: 0.34 },
  CdA: 1.26, ClA: 0.55, aeroFront: 0.44, Crr: 0.013, rollDistF: 0.55,
  steerLockDeg: 35, steerRefSpeed: 29, countersteerDeg: 52, ackermann: 0.55, steerRate: 4.2,
  boost: { torqueMul: 1.35, drain: 0.20, recharge: 0.025, driftRecharge: 0.11 },
  look: { roll: 0.006, pitch: 0.005 },
  defaults: { grip: 1, steerLock: 35, finalDrive: 3.70, brakeBias: 0.62, diffLock: 0.5, balance: 0.5, stability: 0.6, driftAssist: 0.5, traction: 0.4, gearbox: 'auto', awdSplit: 0.34 },
};

const BANSHEE = {
  id: 'banshee', name: 'BANSHEE', blurb: 'Big-block V8 drift weapon. Wants a light foot and a quick hand.',
  drive: 'rwd', aspiration: 'na', display: { hp: 690, nm: 780, kg: 1420, layout: 'FR, naturally aspirated V8' },
  mass: 1420, yawRadius: 1.26, wheelbase: 2.60, cgFront: 0.47, cgHeight: 0.46, trackF: 1.58, trackR: 1.60,
  length: 4.62, width: 1.92, wheelRadius: 0.34, wheelInertiaF: 1.25, wheelInertiaR: 1.40,
  engineInertia: 0.24, idleRpm: 800, redlineRpm: 7400, limiterRpm: 7700,
  torque: [[800, 400], [2000, 560], [3000, 680], [4000, 760], [5000, 780], [5500, 780], [6000, 765], [6500, 742], [7000, 702], [7500, 650], [8000, 590]],
  turbo: null,
  gears: [2.95, 2.00, 1.48, 1.17, 0.96, 0.80], reverse: 2.90, finalDrive: 3.55, efficiency: 0.88,
  shiftTime: 0.13, launchRpm: 3300, clutchMax: 1350,
  diff: { preload: 150, power: 0.60, coast: 0.40 }, frontDiff: null, awd: null,
  brakeTorque: 7600, handbrakeTorque: 2300, brakeBias: 0.62,
  tyre: { mu: 1.18, latRatio: 0.96, loadSens: 0.11, alphaPeakDeg: 8.8, kappaPeak: 0.11, slide: 0.81, falloff: 0.26 },
  CdA: 1.22, ClA: 0.45, aeroFront: 0.44, Crr: 0.013, rollDistF: 0.57,
  steerLockDeg: 37, steerRefSpeed: 29, countersteerDeg: 60, ackermann: 0.40, steerRate: 4.5,
  boost: { torqueMul: 1.35, drain: 0.20, recharge: 0.025, driftRecharge: 0.11 },
  look: { roll: 0.007, pitch: 0.0055 },
  defaults: { grip: 1, steerLock: 37, finalDrive: 3.55, brakeBias: 0.62, diffLock: 0.7, balance: 0.5, stability: 0.4, driftAssist: 0.5, traction: 0, gearbox: 'auto', awdSplit: 0 },
};

export const CARS = { koi: KOI, ronin: RONIN, tempest: TEMPEST, banshee: BANSHEE };
export const CAR_IDS = ['koi', 'ronin', 'tempest', 'banshee'];

/** A one-press "drift setup" per car for the setup menu (partial tunes over the defaults). The RWD
 *  cars ship ready to slide; TEMPEST needs its assists off, torque sent rearward and front grip up.
 *  tests/handling.test.mjs proves the held drift on exactly these. */
export const DRIFT_SETUPS = {
  koi: {}, ronin: {}, banshee: {},
  tempest: { traction: 0, stability: 0, awdSplit: 0.2, balance: 0.8 },
};

/** Tune keys in a fixed order (hashing, UI) with their ranges. */
export const TUNE_KEYS = ['grip', 'steerLock', 'finalDrive', 'brakeBias', 'diffLock', 'balance', 'stability', 'driftAssist', 'traction', 'awdSplit'];
export const TUNE_RANGE = {
  grip: [0.8, 1.2], steerLock: [25, 50], finalDrive: [2.8, 5.2], brakeBias: [0.5, 0.75], diffLock: [0, 1],
  balance: [0, 1], stability: [0, 1], driftAssist: [0, 1], traction: [0, 1], awdSplit: [0.2, 0.6],
};

/** Merge a partial tune over the car's defaults, clamped to the ranges. */
export function resolveTune(carId, tune = {}) {
  const spec = CARS[carId];
  if (!spec) throw new Error('unknown car ' + carId);
  const out = { gearbox: tune.gearbox === 'manual' ? 'manual' : (tune.gearbox === 'auto' ? 'auto' : spec.defaults.gearbox) };
  for (const k of TUNE_KEYS) {
    let v = tune[k] !== undefined && tune[k] !== null ? Number(tune[k]) : spec.defaults[k];
    if (!(v === v)) v = spec.defaults[k];
    const [lo, hi] = TUNE_RANGE[k];
    out[k] = v < lo ? lo : v > hi ? hi : v;
  }
  if (spec.drive !== 'awd') out.awdSplit = 0;
  return out;
}
