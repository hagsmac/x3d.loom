// loom:sim
// KANSEI simulation API (CONTRACT.md section 6). The sim tick owns the game: outcomes are a pure
// function of the track bytes, the creation options and the input words; the page interpolates
// sim.cars[] and reads sim.race.events after every step(), and never writes sim state.
import { trackFromX3D } from './track.js';
import { createCar, stepCar, collideCars, carState, G } from './car.js';
import { createRace, updateRace, raceState, heldCars, HZ as RACE_HZ } from './race.js';
import { createDriver, driveAI } from './ai.js';
import { dsin, dcos, clamp } from './fmath.js';
import { CAR_IDS, CARS, resolveTune, DRIFT_SETUPS } from './cars.js';

export const ENGINE_VERSION = 'kansei-engine/4';
export const HZ = 120;
export const DT = 1 / HZ;
export const MODES = ['free', 'rush', 'attack', 'race', 'tandem'];
export { CAR_IDS, CARS, resolveTune, DRIFT_SETUPS };

/** Parse a track file's text (the same bytes the browser draws). */
export function parseTrack(x3dText) { return trackFromX3D(x3dText); }

/** Pack one tick of controls into a uint32 (bits: 0-7 steer+128, 8-11 throttle, 12-15 brake, 16 handbrake, 17 boost, 18 up, 19 down, 20 reset). */
export function packInput({ steer = 0, throttle = 0, brake = 0, handbrake = false, boost = false, shiftUp = false, shiftDown = false, reset = false } = {}) {
  const s = clamp(Math.round(steer), -127, 127) + 128;
  const t = clamp(Math.round(throttle), 0, 15), b = clamp(Math.round(brake), 0, 15);
  return (s | (t << 8) | (b << 12) | (handbrake ? 1 << 16 : 0) | (boost ? 1 << 17 : 0) | (shiftUp ? 1 << 18 : 0) |
    (shiftDown ? 1 << 19 : 0) | (reset ? 1 << 20 : 0)) >>> 0;
}

export function unpackInput(u, out) {
  const o = out || {};
  u = u >>> 0;
  const s = u & 255;
  o.steer = s === 0 ? -127 : s - 128;
  o.throttle = (u >>> 8) & 15; o.brake = (u >>> 12) & 15;
  o.handbrake = ((u >>> 16) & 1) === 1; o.boost = ((u >>> 17) & 1) === 1;
  o.shiftUp = ((u >>> 18) & 1) === 1; o.shiftDown = ((u >>> 19) & 1) === 1; o.reset = ((u >>> 20) & 1) === 1;
  return o;
}
export const NEUTRAL = packInput({});

const PROP_KINDS = { 1: { name: 'cone', mass: 4, static: false, h: 0.7 }, 2: { name: 'post', mass: 0, static: true, h: 1.1 }, 3: { name: 'barrel', mass: 70, static: false, h: 0.9 } };

/**
 * Create a session. entrants: [{ car, tune, driver: 'player'|'ai', skill, slot, ai: 'race'|'drift' }].
 * Defaults: one player in a RONIN; race mode adds three AI; tandem adds a drifting AI lead.
 */
export function createSim({ track, mode = 'free', surface = 'dry', laps, entrants } = {}) {
  if (!track || !track.n) throw new Error('createSim: track (from parseTrack) is required');
  if (!MODES.includes(mode)) throw new Error('createSim: unknown mode ' + mode);
  let ents = (entrants && entrants.length ? entrants : defaultEntrants(mode)).map((e, k) => {
    const driver = e.driver === 'ai' ? 'ai' : 'player', car = e.car || 'ronin';
    const ai = e.ai || (mode === 'tandem' && driver === 'ai' ? 'drift' : 'race');
    // a drifting AI with no tune of its own runs the car's drift setup
    const tune = e.tune || (driver === 'ai' && ai === 'drift' && DRIFT_SETUPS[car] ? { ...DRIFT_SETUPS[car] } : {});
    return { car, tune, driver, skill: e.skill === undefined ? 0.9 : clamp(Number(e.skill), 0, 1), slot: e.slot === undefined ? k : e.slot | 0, ai };
  });
  if (ents.length > 6) throw new Error('createSim: at most 6 entrants');
  const sim = {
    engine: ENGINE_VERSION, track, mode, surface: surface === 'wet' ? 'wet' : 'dry',
    laps: laps || (mode === 'tandem' ? 2 : 3), entrants: ents, cars: [], drivers: [], props: [], tick: 0, playerIndex: 0,
    _inp: [],
  };
  const T = track;
  for (let i = 0; i < ents.length; i++) {
    const e = ents[i];
    const g = T.grid[Math.min(e.slot, T.grid.length - 1)] || T.grid[0];
    const car = createCar(e.car, e.tune, { x: g.x, z: g.z, yaw: g.yaw }, i, T, sim.surface);
    car.driver = e.driver;
    sim.cars.push(car);
    sim._inp.push({ steer: 0, throttle: 0, brake: 0, handbrake: false, boost: false, shiftUp: false, shiftDown: false, reset: false });
  }
  sim.playerIndex = Math.max(0, ents.findIndex(e => e.driver === 'player'));
  for (let i = 0; i < ents.length; i++) sim.drivers.push(ents[i].driver === 'ai' ? createDriver(sim, i, ents[i].ai, ents[i].skill) : null);
  for (let k = 0; k < T.props.length; k++) {
    const p = T.props[k], kd = PROP_KINDS[p.kind] || PROP_KINDS[1];
    sim.props.push({ index: k, kind: p.kind, name: kd.name, x: p.x, z: p.z, y: 0, r: p.r, vx: 0, vz: 0, vy: 0, angle: 0, spin: 0,
      tilt: 0, mass: kd.mass, fixed: kd.static, hit: false, hitTick: -1, h: kd.h, x0: p.x, z0: p.z });
  }
  sim.race = createRace(sim);
  return sim;
}

function defaultEntrants(mode) {
  const me = { car: 'ronin', driver: 'player', slot: mode === 'tandem' ? 1 : 0 };
  if (mode === 'race') return [{ ...me, slot: 3 }, { car: 'tempest', driver: 'ai', skill: 0.92, slot: 0 }, { car: 'banshee', driver: 'ai', skill: 0.86, slot: 1 }, { car: 'koi', driver: 'ai', skill: 0.95, slot: 2 }];
  if (mode === 'tandem') return [{ car: 'ronin', driver: 'ai', skill: 1, slot: 0, ai: 'drift' }, me];
  return [me];
}

/** Advance one tick. inputs: array of packed Input words, one per player entrant (in entrant order). */
export function step(sim, inputs) {
  const race = sim.race;
  race.events.length = 0;
  const ev = race.events;
  const held = heldCars(race);
  const env = { track: sim.track, wet: sim.surface === 'wet', tick: sim.tick, held, dt: DT, cars: sim.cars };
  // inputs first, from the state at the start of the tick (AI sees only the sim)
  let pi = 0;
  for (let i = 0; i < sim.cars.length; i++) {
    const o = sim._inp[i];
    if (sim.entrants[i].driver === 'player') unpackInput(inputs && inputs.length > pi ? inputs[pi] : NEUTRAL, o), pi++;
    else driveAI(sim, sim.drivers[i], o);
  }
  for (let i = 0; i < sim.cars.length; i++) {
    const car = sim.cars[i];
    // a finished race car coasts to a stop under AI-free neutral input... the player keeps control
    stepCar(car, sim._inp[i], env, ev);
  }
  for (let i = 0; i < sim.cars.length; i++) for (let j = i + 1; j < sim.cars.length; j++) collideCars(sim.cars[i], sim.cars[j], ev, sim.tick);
  stepProps(sim, ev);
  updateRace(sim);
  sim.tick++;
}

/** Cones, posts and barrels: circles against each car's body box; light ones fly. */
function stepProps(sim, ev) {
  const props = sim.props;
  if (!props.length) return;
  const dt = DT;
  for (let k = 0; k < props.length; k++) {
    const p = props[k];
    for (let i = 0; i < sim.cars.length; i++) {
      const car = sim.cars[i], P = car.P;
      const dx = p.x - car.x, dz = p.z - car.z;
      const reach = P.halfL + p.r + 0.5;
      if (dx * dx + dz * dz > reach * reach) continue;
      const c = dcos(car.yaw), s = dsin(car.yaw);
      // prop centre in the car frame (x left, z forward)
      const lx = dx * c - dz * s, lz = dx * s + dz * c;
      const hx = P.halfW, hzF = P.cornerF, hzR = -P.cornerR;
      const cx = clamp(lx, -hx, hx), cz = clamp(lz, -hzR, hzF);
      const ex = lx - cx, ez = lz - cz;
      const d2 = ex * ex + ez * ez;
      let nlx, nlz, pen;
      if (d2 > 1e-12) { const d = Math.sqrt(d2); if (d >= p.r) continue; nlx = ex / d; nlz = ez / d; pen = p.r - d; }
      else {
        // centre inside the box: push out along the nearest face
        const fx = hx - Math.abs(lx), fz = lz > 0 ? hzF - lz : hzR + lz;
        if (fx < fz) { nlx = lx > 0 ? 1 : -1; nlz = 0; pen = fx + p.r; } else { nlx = 0; nlz = lz > 0 ? 1 : -1; pen = fz + p.r; }
      }
      // normal to world (from the car toward the prop)
      const nx = nlx * c + nlz * s, nz = -nlx * s + nlz * c;
      const wx = car.x + cx * c + cz * s, wz = car.z - cx * s + cz * c;   // contact point on the car
      const rx = wx - car.x, rz = wz - car.z;
      const vcx = car.vx + car.yawRate * rz, vcz = car.vz - car.yawRate * rx;
      const rvx = p.vx - vcx, rvz = p.vz - vcz;
      const vn = rvx * nx + rvz * nz;
      if (p.fixed) {
        car.x -= nx * pen; car.z -= nz * pen;
        if (vn < 0) {
          const rn = rz * nx - rx * nz;
          const jn = -(1 + 0.3) * vn / (1 / P.m + rn * rn / P.Iz);
          car.vx -= jn * nx / P.m; car.vz -= jn * nz / P.m; car.yawRate -= (rz * jn * nx - rx * jn * nz) / P.Iz;
          car.collided += jn;
          if (jn > 250) ev.push({ type: 'crash', car: i, prop: k, impulse: jn, x: wx, y: car.y + 0.4, z: wz, wall: true, tick: sim.tick });
        }
        continue;
      }
      const im = 1 / p.mass + 1 / P.m;
      p.x += nx * pen * (1 / p.mass) / im; p.z += nz * pen * (1 / p.mass) / im;
      car.x -= nx * pen * (1 / P.m) / im; car.z -= nz * pen * (1 / P.m) / im;
      if (vn < 0) {
        const rn = rz * nx - rx * nz;
        const jn = -(1 + 0.45) * vn / (im + rn * rn / P.Iz);
        p.vx += jn * nx / p.mass; p.vz += jn * nz / p.mass;
        car.vx -= jn * nx / P.m; car.vz -= jn * nz / P.m; car.yawRate -= (rz * jn * nx - rx * jn * nz) / P.Iz;
        const dv = jn / p.mass;
        p.vy = Math.max(p.vy, Math.min(6, 0.35 * dv)); p.spin += (lx > 0 ? 1 : -1) * Math.min(25, dv * 2);
        if (!p.hit) { p.hit = true; p.hitTick = sim.tick; ev.push({ type: 'cone', car: i, prop: k, kind: p.name, x: p.x, z: p.z, speed: dv, tick: sim.tick }); }
      }
    }
    // free flight and ground friction
    if (!p.fixed) {
      if (p.y > 0 || p.vy > 0) { p.vy -= G * dt; p.y += p.vy * dt; if (p.y <= 0) { p.y = 0; p.vy = p.vy < -1.5 ? -0.3 * p.vy : 0; } }
      const sp = Math.sqrt(p.vx * p.vx + p.vz * p.vz);
      if (sp > 0) {
        const dec = (p.y > 0.02 ? 0.4 : (p.kind === 3 ? 4.5 : 6.0)) * dt;
        const ns = sp > dec ? sp - dec : 0;
        p.vx *= ns / sp; p.vz *= ns / sp;
      }
      p.x += p.vx * dt; p.z += p.vz * dt;
      p.angle += p.spin * dt; p.spin *= 1 - Math.min(1, 2.5 * dt);
      if (p.hit) p.tilt = Math.min(1.5707963267948966, p.tilt + (sp > 1 ? 6 : 0) * dt);
    }
  }
}

const F64 = new Float64Array(1), U8 = new Uint8Array(F64.buffer);
/** 64-bit FNV-style hash over every car, the race and the props, in a fixed order: 16 hex chars. */
const PHASE_CODE = { cruise: 0, entry: 1, hold: 2, exit: 3, save: 4 };
const strCode = t => { if (!t) return 0; let h = 0; for (let i = 0; i < t.length; i++) h = (Math.imul(h, 31) + t.charCodeAt(i)) | 0; return h; };
export function hashSim(sim) {
  let a = 0x811c9dc5, c = 0x9e3779b9;
  const mix = v => {
    F64[0] = v === 0 ? 0 : v;   // fold -0 into 0
    for (let i = 0; i < 8; i++) { a = Math.imul(a ^ U8[i], 16777619); c = Math.imul(c ^ U8[i], 0x5bd1e995); c ^= c >>> 15; }
  };
  mix(sim.tick);
  for (const car of sim.cars) carState(car, mix);
  raceState(sim.race, mix);
  for (const p of sim.props) { mix(p.x); mix(p.z); mix(p.y); mix(p.vx); mix(p.vz); mix(p.vy); mix(p.angle); mix(p.spin); mix(p.hit ? 1 : 0); }
  for (const d of sim.drivers) if (d) {
    mix(d.timer); mix(d.stuck); mix(d.resetCool); mix(PHASE_CODE[d.phase] ?? 9); mix(d.dir);
    mix(d.bT); mix(d.vhPrev); mix(d.kAct); mix(d.thrI); mix(d.rI); mix(d.bAdj); mix(d.rPrev); mix(d.rDotF); mix(d.vPrev); mix(d.accF); mix(d.hbTimer); mix(d.hbCool); mix(d.latPrev); mix(d.latRateF);
    mix((d.vhInit ? 1 : 0) + (d.rInit ? 2 : 0) + (d.vInit ? 4 : 0) + (d.latInit ? 8 : 0)); mix(d.betaTarget);
    // race traffic and corner linking also carry forward from tick to tick
    mix(d.link); mix(d.merged ? 1 : 0); mix(d.pace); mix(d.passK); mix(d.passSide); mix(d.offLat); mix(d.wantLat === undefined ? 0 : d.wantLat);
    mix((d.mode === 'drift' ? 1 : 0) + (d.linkOK ? 2 : 0)); mix(strCode(d.saveWhy));
  }
  return (a >>> 0).toString(16).padStart(8, '0') + (c >>> 0).toString(16).padStart(8, '0');
}

/** A compact summary for tapes, bots and tests. */
export function summary(sim) {
  const r = sim.race, pc = sim.cars[sim.playerIndex];
  return {
    frame: sim.tick, mode: sim.mode, phase: r.phase, bestLap: r.bestLap, laps: r.lapTimes.length,
    validLaps: r.lapTimes.filter(l => l.valid).length, score: Math.round(r.score), medal: r.medal,
    position: pc.position, results: r.results, hash: hashSim(sim),
  };
}
