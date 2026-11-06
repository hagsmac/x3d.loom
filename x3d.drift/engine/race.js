// loom:sim
// Race director (CONTRACT.md section 8): progress along the lap, checkpoints, sectors, laps and
// invalid laps, the five modes (free, rush, attack, race, tandem), drift chains and multipliers,
// clipping zones, positions and overtakes, tandem scoring and grades, medals. Events go into
// race.events, which sim.step() clears at the start of every tick.
import { arcDelta } from './track.js';
import { clamp, DEG, datan2, wrapPi } from './fmath.js';

export const HZ = 120;
export const MEDALS = ['none', 'bronze', 'silver', 'gold', 'platinum'];
export const RULES = {
  driftSlip: 12 * DEG, driftSpeed: 25 / 3.6, maxOffWheels: 2,
  grace: 2.0, multStep: 0.5, multEvery: 2.0, multMax: 6, transitionWindow: 1.0, continuityGap: 0.5,
  // a transition (+1) needs a real slide on the old side (>= 20 deg for 0.35 s), the new side to reach
  // 20 deg within the window, and 1.2 s since the last one; the car's course must also have turned 15 deg
  // during the old side's slide, so a wobble (manji) down a straight is not a transition
  transitionSlip: 20 * DEG, transitionHold: 0.35, transitionCooldown: 1.2, transitionStep: 1, transitionTurn: 15 * DEG,
  crashDv: 1.2,              // m/s of impulse/mass that loses a pending chain
  conePenalty: 250,
  clipDist: 2.0, perfectDist: 1.0, perfectSlip: 35 * DEG,
  offLimit: 1.0,             // s with >= 3 wheels beyond halfWidth + 1.2 that voids a lap
  rushTime: 90, countdown: 3, tandemLaps: 2,
  pointsPerTick: 3,
};
const PHASES = ['grid', 'countdown', 'running', 'finished'];
export const GRADES = ['D', 'C', 'B', 'A', 'S'];

export function createRace(sim) {
  const mode = sim.mode;
  const T = sim.track;
  const r = {
    mode, phase: 'grid', tick: 0, time: 0, countdown: 0, laps: sim.laps,
    player: sim.playerIndex,
    // timing (player car)
    lapTimes: [], sectors: [0, 0, 0], sectorDeltas: [0, 0, 0], bestLap: 0, bestLapTicks: [-1, -1], bestSectors: [0, 0, 0],
    lapStart: -1, lastLap: 0, valid: true, offTime: 0, checkpoint: -1, nextCheckpoint: 0,
    // drift scoring (player car)
    score: 0, banked: 0, chain: 0, chainActive: false, multiplier: 1, grace: 0, bestChain: 0,
    contTime: 0, multTimer: 0, lastSign: 0, lastDriftTime: -10, driftTicks: 0, cones: 0,
    sideHold: 0, sideTurn: 0, course: 0, flipOK: false, flipTime: -10, lastTransition: -10,
    zone: null, zonePass: -1, zoneClipDone: false, zonePerfectDone: false,
    timer: mode === 'rush' ? RULES.rushTime : 0, startTick: -1,
    // racing
    positions: [], finishOrder: [], raceStart: -1,
    tandem: mode === 'tandem' ? { lead: -1, distance: 0, proximity: 0, angleMatch: 0, lineMatch: 0, score: 0, leadTicks: 0, bothTicks: 0, contacts: 0, quality: 0, grade: 'D' } : null,
    medal: 'none', results: null, events: [],
  };
  const pc = sim.cars[r.player];
  r.targets = medalTargets(T.targets, pc.id, pc.tune.grip, sim.surface);
  for (let i = 0; i < sim.cars.length; i++) r.positions.push(i);
  if (mode === 'free' || mode === 'attack') { r.phase = 'running'; r.startTick = 0; }
  else if (mode === 'race' || mode === 'tandem') { r.phase = 'countdown'; r.countdown = RULES.countdown; }
  if (r.tandem) {
    for (let i = 0; i < sim.entrants.length; i++) if (sim.entrants[i].driver === 'ai') { r.tandem.lead = i; break; }
  }
  for (const car of sim.cars) { car.prevS = car.s; }
  return r;
}

/** True while cars must stay on the grid (brakes held, engine may rev). */
export function heldCars(race) { return race.phase === 'countdown' || (race.phase === 'grid' && race.mode !== 'rush'); }

/**
 * Medal targets for one run. The level's targets are for a stock RONIN on the dry; every car, the
 * wet and the grip tune move them by the pace the bots measured (tools/bot.mjs on the five circuits,
 * geometric means against RONIN), so a medal means the same drive whatever was picked:
 *   lap targets x MEDAL_PACE[car].lap x (wet ? 1.16) x gripLap(grip)
 *   rush targets x MEDAL_PACE[car].rush x (wet ? 1.3) x gripRush(grip)
 * grip fits: lap ~ grip^-0.45, rush ~ grip^-1.5 (2nd-order expansions about 1, inside 0.8..1.2).
 * Laps round to 0.1 s and scores to 50 points.
 */
export const MEDAL_PACE = {
  koi: { lap: 1.04, rush: 0.85 }, ronin: { lap: 1, rush: 1 }, tempest: { lap: 0.957, rush: 0.35 }, banshee: { lap: 0.974, rush: 1.4 },
};
export const MEDAL_WET = { lap: 1.16, rush: 1.3 };
export function medalScale(carId, grip, surface) {
  const p = MEDAL_PACE[carId] || MEDAL_PACE.ronin, wet = surface === 'wet';
  const d = (grip > 0 ? grip : 1) - 1;
  const lap = p.lap * (wet ? MEDAL_WET.lap : 1) * (1 - 0.45 * d + 0.326 * d * d);
  const rush = p.rush * (wet ? MEDAL_WET.rush : 1) * (1 - 1.5 * d + 1.875 * d * d);
  return { lap, rush };
}
export function medalTargets(base, carId, grip, surface) {
  const k = medalScale(carId, grip, surface);
  const l = v => v > 0 ? Math.round(v * k.lap * 10) / 10 : 0, r = v => v > 0 ? Math.round(v * k.rush / 50) * 50 : 0;
  return { goldLap: l(base.goldLap), silverLap: l(base.silverLap), bronzeLap: l(base.bronzeLap),
    rushBronze: r(base.rushBronze), rushSilver: r(base.rushSilver), rushGold: r(base.rushGold), rushPlatinum: r(base.rushPlatinum),
    lapScale: k.lap, rushScale: k.rush };
}

function medalRush(race, score) {
  const t = race.targets;
  if (t.rushPlatinum > 0 && score >= t.rushPlatinum) return 'platinum';
  if (t.rushGold > 0 && score >= t.rushGold) return 'gold';
  if (t.rushSilver > 0 && score >= t.rushSilver) return 'silver';
  if (t.rushBronze > 0 && score >= t.rushBronze) return 'bronze';
  return 'none';
}
function medalLap(race, lap) {
  const t = race.targets;
  if (!(lap > 0)) return 'none';
  if (t.goldLap > 0 && lap <= t.goldLap) return 'gold';
  if (t.silverLap > 0 && lap <= t.silverLap) return 'silver';
  if (t.bronzeLap > 0 && lap <= t.bronzeLap) return 'bronze';
  return 'none';
}
export const medalRank = m => MEDALS.indexOf(m);

/** Per-car lap progress: checkpoints in order and forward only; sub-tick crossing time. */
function progress(sim, race, car, ci, ev, t0) {
  const T = sim.track, K = T.checkpoints.length, L = T.L;
  const ds = arcDelta(T, car.prevS, car.s);
  const jumped = car.resetTick === sim.tick || ds > 40 || ds < -40;
  let crossed = 0;
  if (!jumped && ds > 0) {
    for (let guard = 0; guard < K; guard++) {
      const next = car.cpCount % K;
      let d = T.cpS[next] - car.prevS;
      d -= L * Math.floor(d / L);
      if (d > 0 && d <= ds) {
        const at = t0 + d / ds;                 // crossing time in ticks (fractional)
        car.cpCount++;
        crossed++;
        onCheckpoint(sim, race, car, ci, next, at, ev);
      } else break;
    }
  }
  car.prevS = car.s;
  car.dsTick = jumped ? 0 : ds;
  const lapsDone = car.cpCount >= 1 ? Math.floor((car.cpCount - 1) / K) : 0;
  car.lapsDone = lapsDone;
  car.lap = lapsDone + 1;
  let p = car.s - T.cpS[0]; p -= L * Math.floor(p / L);
  car.progress = p / L;
  if (car.cpCount === 0) car.raceDist = arcDelta(T, T.cpS[0], car.s);
  else {
    const last = (car.cpCount - 1) % K, nxt = (last + 1) % K;
    let base = T.cpS[last] - T.cpS[0]; base -= L * Math.floor(base / L);
    let segLen = T.cpS[nxt] - T.cpS[last]; segLen -= L * Math.floor(segLen / L); if (segLen <= 0) segLen = L;
    const d = clamp(arcDelta(T, T.cpS[last], car.s), -segLen, segLen);
    car.raceDist = lapsDone * L + base + d;
  }
  return crossed;
}

function onCheckpoint(sim, race, car, ci, cpIndex, at, ev) {
  const T = sim.track, K = T.checkpoints.length;
  const isPlayer = ci === race.player;
  ev.push({ type: 'checkpoint', car: ci, index: cpIndex, count: car.cpCount, tick: sim.tick });
  if (cpIndex === 0) {
    // the line: the first crossing starts lap 1, every later one closes a lap
    if (car.cpCount > 1) {
      const start = car.lapStart >= 0 ? car.lapStart : 0;
      const lapTime = (at - start) / HZ;
      const lapNo = Math.floor((car.cpCount - 1) / K);
      if (isPlayer) closeLap(sim, race, car, ci, lapTime, start, at, ev, lapNo);
      else ev.push({ type: 'lap', car: ci, lap: lapNo, time: lapTime, valid: true, tick: sim.tick });
      if ((race.mode === 'race' || race.mode === 'tandem') && !car.finished && lapNo >= race.laps) finishCar(sim, race, car, ci, at, ev);
    }
    car.lapStart = race.mode === 'race' && car.cpCount === 1 && race.raceStart >= 0 ? race.raceStart : at;
    if (isPlayer) { race.lapStart = car.lapStart; race.sectors[0] = 0; race.sectors[1] = 0; race.sectors[2] = 0; race.sectorStart = car.lapStart; if (car.cpCount === 1) { race.valid = true; race.offTime = 0; } }
  } else if (isPlayer && car.cpCount > 1 && (cpIndex === T.sectors[0] || cpIndex === T.sectors[1])) {
    const sec = cpIndex === T.sectors[0] ? 0 : 1;
    const t = (at - race.sectorStart) / HZ;
    race.sectors[sec] = t; race.sectorStart = at;
    const best = race.bestSectors[sec];
    const delta = best > 0 ? splitTo(race, sec) - splitBest(race, sec) : 0;
    race.sectorDeltas[sec] = delta;
    ev.push({ type: 'sector', car: ci, sector: sec + 1, time: t, split: splitTo(race, sec), delta, best: best > 0 && t < best, tick: sim.tick });
  }
  if (isPlayer) { race.checkpoint = cpIndex; race.nextCheckpoint = (cpIndex + 1) % K; }
}
const splitTo = (race, sec) => { let s = 0; for (let k = 0; k <= sec; k++) s += race.sectors[k]; return s; };
const splitBest = (race, sec) => { let s = 0; for (let k = 0; k <= sec; k++) s += race.bestSectors[k]; return s; };

function closeLap(sim, race, car, ci, lapTime, start, at, ev, lapNo) {
  const T = sim.track;
  race.sectors[2] = (at - race.sectorStart) / HZ;
  const valid = race.valid;
  const best = race.bestLap;
  const isBest = valid && (best === 0 || lapTime < best);
  if (race.bestSectors[2] > 0) race.sectorDeltas[2] = lapTime - race.bestLap;
  ev.push({ type: 'sector', car: ci, sector: 3, time: race.sectors[2], split: lapTime, delta: best > 0 ? lapTime - best : 0, best: race.bestSectors[2] > 0 && race.sectors[2] < race.bestSectors[2], tick: sim.tick });
  race.lapTimes.push({ lap: lapNo, time: lapTime, valid, sectors: race.sectors.slice() });
  race.lastLap = lapTime;
  ev.push({ type: 'lap', car: ci, lap: lapNo, time: lapTime, valid, best: isBest, delta: best > 0 ? lapTime - best : 0, tick: sim.tick });
  if (isBest) {
    race.bestLap = lapTime; race.bestLapTicks = [start, at]; race.bestSectors = race.sectors.slice();
    if (race.mode === 'attack') {
      const m = medalLap(race, lapTime);
      if (medalRank(m) > medalRank(race.medal)) { race.medal = m; ev.push({ type: 'medal', car: ci, medal: m, lapTime, tick: sim.tick }); }
      race.results = { bestLap: race.bestLap, laps: race.lapTimes.length, medal: race.medal, bestLapTicks: race.bestLapTicks };
    }
  }
  race.valid = true; race.offTime = 0;
}

function finishCar(sim, race, car, ci, at, ev) {
  car.finished = true; car.finishTick = sim.tick;
  race.finishOrder.push(ci);
  const start = race.raceStart >= 0 ? race.raceStart : 0;
  car.raceTime = (at - start) / HZ;
  ev.push({ type: 'finish', car: ci, position: race.finishOrder.length, time: car.raceTime, tick: sim.tick });
}

function bankChain(race, ev, ci, tick) {
  if (race.chain > 0) {
    race.banked += race.chain;
    if (race.chain > race.bestChain) race.bestChain = race.chain;
    ev.push({ type: 'chainBank', car: ci, points: race.chain, multiplier: race.multiplier, tick });
  }
  race.chain = 0; race.chainActive = false; race.multiplier = 1; race.contTime = 0; race.multTimer = 0; race.lastSign = 0;
  race.sideHold = 0; race.sideTurn = 0; race.flipOK = false;
}

function inZone(T, z, s) {
  let a = s - z.s0; a -= T.L * Math.floor(a / T.L);
  let w = z.s1 - z.s0; w -= T.L * Math.floor(w / T.L);
  return a <= w;
}

/** Drift scoring for one car (the player's) in free, rush and tandem. */
function driftScore(sim, race, car, ci, ev, dt) {
  const T = sim.track;
  const tick = sim.tick;
  const ab = car.slip < 0 ? -car.slip : car.slip;
  const forward = car.dsTick > 0.02;
  const scoring = race.phase === 'running' && car.drifting && forward && car.offWheels <= RULES.maxOffWheels;
  // a crash or a reset loses the pending chain (banked points stay): R is not a way to save a chain
  if (race.chainActive && (car.collided / car.P.m > RULES.crashDv || car.resetTick === tick)) {
    ev.push({ type: 'chainLost', car: ci, points: race.chain, tick });
    race.chain = 0; race.chainActive = false; race.multiplier = 1; race.contTime = 0; race.multTimer = 0; race.lastSign = 0;
    race.sideHold = 0; race.sideTurn = 0; race.flipOK = false;
  }
  // course (velocity heading) change this tick, for the transition rule
  const course = car.speed > 0.5 ? datan2(car.vx, car.vz) : race.course;
  const dCourse = wrapPi(course - race.course);
  race.course = course;
  // zones
  let zmul = 1;
  race.zone = null;
  let found = -1;
  for (let k = 0; k < T.zones.length; k++) if (inZone(T, T.zones[k], car.s)) { found = k; break; }
  if (found !== race.zonePass) { race.zonePass = found; race.zoneClipDone = false; race.zonePerfectDone = false; }
  if (found >= 0) {
    const z = T.zones[found];
    const edge = z.side * car.hw;
    const d2 = Math.abs(edge - car.wheels[2].lat), d3 = Math.abs(edge - car.wheels[3].lat);
    const dist = d2 < d3 ? d2 : d3;
    const clip = scoring && dist <= RULES.clipDist;
    const perfect = clip && dist <= RULES.perfectDist && ab >= RULES.perfectSlip;
    race.zone = { index: found, kind: z.kind, side: z.side, dist, clip, perfect };
    if (clip) zmul = 2;
    if (perfect) zmul = 3;
    if (clip && !race.zoneClipDone) { race.zoneClipDone = true; ev.push({ type: 'zoneClip', car: ci, zone: found, dist, tick }); }
    if (perfect && !race.zonePerfectDone) { race.zonePerfectDone = true; ev.push({ type: 'zonePerfect', car: ci, zone: found, dist, tick }); }
  }
  if (scoring) {
    race.driftTicks++;
    const sign = car.slip > 0 ? 1 : -1;
    const sinceLast = race.time - race.lastDriftTime;
    if (!race.chainActive) {
      race.chainActive = true; race.chain = 0; race.multiplier = 1; race.contTime = 0; race.multTimer = 0;
      race.sideHold = 0; race.sideTurn = 0; race.flipOK = false;
      ev.push({ type: 'chainStart', car: ci, tick });
    } else if (race.lastSign !== 0 && sign !== race.lastSign && sinceLast <= RULES.transitionWindow) {
      // the slide changed sides: it may count once the new side is a real slide too
      race.flipOK = race.sideHold >= RULES.transitionHold && (race.sideTurn < 0 ? -race.sideTurn : race.sideTurn) >= RULES.transitionTurn;
      race.flipTime = race.time; race.sideHold = 0; race.sideTurn = 0;
    }
    race.sideTurn += dCourse;
    if (ab >= RULES.transitionSlip) {
      race.sideHold += dt;
      if (race.flipOK) {
        race.flipOK = false;
        if (race.time - race.flipTime <= RULES.transitionWindow && race.time - race.lastTransition >= RULES.transitionCooldown) {
          race.lastTransition = race.time;
          race.multiplier = Math.min(RULES.multMax, race.multiplier + RULES.transitionStep);
          ev.push({ type: 'transition', car: ci, multiplier: race.multiplier, tick });
        }
      }
    }
    if (sinceLast > RULES.continuityGap) { race.contTime = 0; race.multTimer = 0; }
    race.contTime += dt; race.multTimer += dt;
    if (race.multTimer >= RULES.multEvery) {
      race.multTimer -= RULES.multEvery;
      if (race.multiplier < RULES.multMax) { race.multiplier = Math.min(RULES.multMax, race.multiplier + RULES.multStep); ev.push({ type: 'multiplier', car: ci, multiplier: race.multiplier, tick }); }
    }
    race.lastSign = sign; race.lastDriftTime = race.time + dt; race.grace = RULES.grace;
    const angleF = (ab < 60 * DEG ? ab : 60 * DEG) / (30 * DEG);
    const kmh = car.speed * 3.6;
    const speedF = (kmh < 180 ? kmh : 180) / 80;
    race.chain += RULES.pointsPerTick * angleF * speedF * race.multiplier * zmul;
  } else if (race.chainActive) {
    race.grace -= dt;
    if (race.grace <= 0) bankChain(race, ev, ci, tick);
  }
  race.score = race.banked;
}

function tandemScore(sim, race, ev) {
  const td = race.tandem;
  if (td.lead < 0 || race.phase !== 'running') return;
  const lead = sim.cars[td.lead], chase = sim.cars[race.player];
  const gap = lead.raceDist - chase.raceDist;
  td.distance = gap;
  let prox = 0;
  if (gap >= 1.5 && gap <= 4) prox = 1;
  else if (gap > 4 && gap < 12) prox = (12 - gap) / 8;
  else if (gap >= 0 && gap < 1.5) prox = 0.4 + 0.6 * gap / 1.5;
  td.proximity = prox;
  const dA = Math.abs(chase.slip - lead.slip);
  td.angleMatch = Math.max(0, 1 - dA / (25 * DEG));
  td.lineMatch = Math.max(0, 1 - Math.abs(chase.lat - lead.lat) / 3);
  if (lead.drifting) td.leadTicks++;
  if (lead.drifting && chase.drifting && chase.dsTick > 0) {
    td.bothTicks++;
    td.score += 10 * prox * (0.4 + 0.6 * td.angleMatch) * (0.5 + 0.5 * td.lineMatch);
  }
  for (let k = 0; k < ev.length; k++) {
    const e = ev[k];
    if (e.type === 'crash' && !e.wall && ((e.car === td.lead && e.other === race.player) || (e.car === race.player && e.other === td.lead)) && e.impulse > 300) {
      td.contacts++; td.score -= 200;
    }
  }
  td.quality = td.leadTicks > 0 ? Math.max(0, td.score) / (10 * td.leadTicks) : 0;
  const q = td.quality;
  td.grade = q >= 0.75 ? 'S' : q >= 0.6 ? 'A' : q >= 0.45 ? 'B' : q >= 0.3 ? 'C' : 'D';
}

/** Advance the race director one tick (after the cars moved). */
export function updateRace(sim) {
  const race = sim.race, ev = race.events, T = sim.track, dt = 1 / HZ;
  const t0 = sim.tick;  // ticks completed before this step
  // phase clock
  if (race.phase === 'countdown') {
    const before = race.countdown;
    race.countdown -= dt;
    const n0 = Math.ceil(before - 1e-9), n1 = Math.ceil(race.countdown - 1e-9);
    if (t0 === 0) ev.push({ type: 'countdown', n: RULES.countdown, tick: t0 });
    else if (n1 !== n0 && n1 > 0) ev.push({ type: 'countdown', n: n1, tick: t0 });
    if (race.countdown <= 1e-9) {
      race.countdown = 0; race.phase = 'running'; race.raceStart = t0 + 1; race.startTick = t0 + 1;
      ev.push({ type: 'go', tick: t0 });
    }
  } else if (race.phase === 'grid' && race.mode === 'rush') {
    const pc = sim.cars[race.player];
    if (pc.speed > 1.0) { race.phase = 'running'; race.startTick = t0; ev.push({ type: 'go', tick: t0 }); }
  }
  // per-car progress (all cars, fixed order)
  for (let i = 0; i < sim.cars.length; i++) progress(sim, race, sim.cars[i], i, ev, t0);
  const pc = sim.cars[race.player];
  // invalid laps (time attack and race): >= 3 wheels on the runoff for over a second, or a reset
  if (race.phase === 'running') {
    if (pc.offWheels >= 3) {
      race.offTime += dt;
      if (race.offTime > RULES.offLimit && race.valid && pc.cpCount >= 1) { race.valid = false; ev.push({ type: 'lapInvalid', car: race.player, reason: 'off', tick: t0 }); }
    }
    if (pc.resetTick === sim.tick && race.valid && pc.cpCount >= 1 && (race.mode === 'attack' || race.mode === 'race')) { race.valid = false; ev.push({ type: 'lapInvalid', car: race.player, reason: 'reset', tick: t0 }); }
  }
  if (race.phase === 'running') race.time += dt;
  // drift scoring
  if (race.mode === 'free' || race.mode === 'rush' || race.mode === 'tandem') driftScore(sim, race, pc, race.player, ev, dt);
  // cones cost points in the drift modes
  for (let k = 0; k < ev.length; k++) {
    const e = ev[k];
    if (e.type === 'cone' && e.car === race.player && !e.scored) {
      e.scored = true; race.cones++;
      if (race.mode === 'rush' || race.mode === 'free') { race.banked = Math.max(0, race.banked - RULES.conePenalty); e.penalty = RULES.conePenalty; race.score = race.banked; }
    }
  }
  if (race.mode === 'rush' && race.phase === 'running') {
    race.timer = Math.max(0, RULES.rushTime - (t0 + 1 - race.startTick) / HZ);
    if (race.timer <= 0) {
      bankChain(race, ev, race.player, t0);
      race.score = race.banked;
      race.phase = 'finished';
      race.medal = medalRush(race, race.score);
      race.results = { score: race.score, medal: race.medal, bestChain: race.bestChain, cones: race.cones };
      ev.push({ type: 'finish', car: race.player, score: race.score, tick: t0 });
      ev.push({ type: 'medal', car: race.player, medal: race.medal, score: race.score, tick: t0 });
    }
  }
  if (race.mode === 'tandem') {
    tandemScore(sim, race, ev);
    const lead = race.tandem.lead >= 0 ? sim.cars[race.tandem.lead] : null;
    if (race.phase === 'running' && lead && lead.lapsDone >= race.laps) {
      if (race.chainActive) bankChain(race, ev, race.player, t0);
      race.phase = 'finished';
      const td = race.tandem;
      race.results = { score: Math.round(td.score), quality: td.quality, grade: td.grade, contacts: td.contacts, drift: race.banked };
      ev.push({ type: 'finish', car: race.player, grade: td.grade, score: Math.round(td.score), tick: t0 });
    }
  }
  // positions and overtakes
  if (race.mode === 'race' || race.mode === 'tandem') {
    const prev = race.positions.slice();
    const order = sim.cars.map((c, i) => i);
    order.sort((a, b) => {
      const ca = sim.cars[a], cb = sim.cars[b];
      const fa = ca.finished ? race.finishOrder.indexOf(a) : 1e9, fb = cb.finished ? race.finishOrder.indexOf(b) : 1e9;
      if (fa !== fb) return fa - fb;
      if (ca.raceDist !== cb.raceDist) return cb.raceDist - ca.raceDist;
      return a - b;
    });
    race.positions = order;
    for (let k = 0; k < order.length; k++) sim.cars[order[k]].position = k + 1;
    if (race.phase === 'running') {
      for (let k = 0; k < order.length; k++) {
        const i = order[k];
        const was = prev.indexOf(i);
        if (was > k && !sim.cars[i].finished) {
          for (let m = k + 1; m < order.length; m++) {
            const j = order[m];
            if (prev.indexOf(j) < was && !sim.cars[j].finished) ev.push({ type: 'overtake', car: i, passed: j, position: k + 1, tick: t0 });
          }
        }
      }
    }
    if (race.mode === 'race' && race.phase === 'running') {
      const leaderDone = race.finishOrder.length > 0;
      const winner = leaderDone ? sim.cars[race.finishOrder[0]] : null;
      const timeout = winner && (sim.tick - winner.finishTick) > 60 * HZ;
      if (pc.finished || timeout || race.finishOrder.length === sim.cars.length) {
        race.phase = 'finished';
        race.results = { position: pc.position, finishOrder: race.finishOrder.slice(), times: race.finishOrder.map(i => sim.cars[i].raceTime),
          bestLap: race.bestLap, dnf: !pc.finished };
      }
    }
  }
  for (let i = 0; i < sim.cars.length; i++) if (sim.cars[i].position === 0) sim.cars[i].position = i + 1;
  race.tick = sim.tick + 1;
}

/** Everything in the race state that carries the future, in a fixed order. */
export function raceState(race, mix) {
  mix(PHASES.indexOf(race.phase)); mix(race.tick); mix(race.time); mix(race.countdown);
  mix(race.lapStart); mix(race.bestLap); mix(race.valid ? 1 : 0); mix(race.offTime); mix(race.lapTimes.length);
  mix(race.score); mix(race.banked); mix(race.chain); mix(race.chainActive ? 1 : 0); mix(race.multiplier); mix(race.grace);
  mix(race.bestChain); mix(race.contTime); mix(race.multTimer); mix(race.lastSign); mix(race.lastDriftTime); mix(race.cones);
  mix(race.sideHold); mix(race.sideTurn); mix(race.course); mix(race.flipOK ? 1 : 0); mix(race.flipTime); mix(race.lastTransition);
  mix(race.zonePass); mix(race.timer); mix(race.startTick); mix(race.raceStart); mix(race.finishOrder.length);
  for (let k = 0; k < race.positions.length; k++) mix(race.positions[k]);
  if (race.tandem) { mix(race.tandem.score); mix(race.tandem.leadTicks); mix(race.tandem.bothTicks); mix(race.tandem.contacts); }
}
