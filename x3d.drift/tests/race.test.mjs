// Race director, scoring, AI and determinism (CONTRACT.md sections 6, 8, 9, 10).
//   node tests/race.test.mjs            (about 20 s)
// Rules are checked two ways: in place, every tick of long bot runs (the points formula, the
// multiplier steps, the grace, transitions, zones), and by constructed situations (a crash with a
// chain pending, a cone in the way, a car driven backwards, a skipped checkpoint, a reset).
// Constructed situations poke sim state directly; that is test code, never the page.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseTrack, createSim, step, packInput, unpackInput, hashSim, CAR_IDS } from '../engine/sim.js';
import { createDriver, driveAI, DRIFT } from '../engine/ai.js';
import { RULES, GRADES, MEDALS, medalTargets } from '../engine/race.js';
import { encodeTape, decodeTape } from '../engine/tape.js';
import { readTrackMeta } from '../engine/x3d.js';
import { buildTrack, pointAtS, project, arcDelta } from '../engine/track.js';
import { placeOnTrack } from '../engine/car.js';
import { ihash } from '../engine/fmath.js';
import { DRIFT_SETUPS } from '../engine/cars.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const text = id => readFileSync(ROOT + 'tests/fixtures/' + id + '.x3d', 'utf8');
const TR = { oval: parseTrack(text('oval')), twisty: parseTrack(text('twisty')), skidpad: parseTrack(text('skidpad')), strip: parseTrack(text('strip')) };
const DEG = Math.PI / 180;

let fails = 0, count = 0;
function check(name, ok, detail = '') { count++; if (!ok) fails++; console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? '  (' + detail + ')' : ''}`); }

/** A sim whose player entrant is driven by the AI (exactly what tools/bot.mjs records). */
function botSim(track, mode, { car = 'ronin', ai = mode === 'attack' ? 'race' : 'drift', tune = {}, entrants, laps, surface } = {}) {
  const ents = entrants || [{ car, tune, driver: 'player' }];
  const sim = createSim({ track, mode, entrants: ents, laps, surface });
  const drv = createDriver(sim, sim.playerIndex, ai, 1);
  const inp = {};
  return { sim, drv, car: sim.cars[sim.playerIndex], next(override) { driveAI(sim, drv, inp); if (override) override(inp); const w = packInput(inp); step(sim, [w]); return w; } };
}
const evs = (sim, type) => sim.race.events.filter(e => e.type === type);
const PQ = { seg: 0, u: 0, s: 0, lat: 0, dist: 0, ex: 0, ez: 0 };
const arcDeltaS = (T, from, to) => { project(T, from.x, from.z, -1, PQ); const a = PQ.s; project(T, to.x, to.z, -1, PQ); return arcDelta(T, a, PQ.s); };

// ---- 1. determinism ------------------------------------------------------------------------------
{
  const mk = T => createSim({ track: T, mode: 'race', laps: 2, entrants: [
    { car: 'ronin', driver: 'player', tune: { gearbox: 'manual', traction: 0.3 } },
    { car: 'tempest', driver: 'ai', skill: 0.9 }, { car: 'banshee', driver: 'ai', skill: 0.8 }, { car: 'koi', driver: 'ai', ai: 'drift', skill: 1 }] });
  // a random-walk player: every control, including handbrake, boost, both shift paddles and reset
  const input = t => {
    const h = ihash(t >> 3, 77), h2 = ihash(t >> 5, 91);
    return packInput({ steer: ((h & 255) - 128) * ((h2 & 1) ? 1 : 0.4), throttle: (h >>> 8) & 15, brake: ((h >>> 12) & 7) < 2 ? (h >>> 16) & 15 : 0,
      handbrake: ((h >>> 20) & 15) === 0, boost: ((h >>> 24) & 7) === 0, shiftUp: (t % 240) === 100, shiftDown: (t % 360) === 300, reset: t === 1500 });
  };
  for (const id of ['twisty', 'oval']) {
    const A = mk(parseTrack(text(id))), B = mk(parseTrack(text(id))), C = mk(TR[id]);
    let first = -1;
    for (let t = 0; t < 120 * 20; t++) {
      const w = [input(t)];
      step(A, w); step(B, w); step(C, w);
      const ha = hashSim(A);
      if (first < 0 && (ha !== hashSim(B) || ha !== hashSim(C))) first = t;
    }
    check(`determinism on ${id}: 4 cars (player + 2 race AI + drift AI), 20 s, identical hashSim every tick`, first < 0, first >= 0 ? 'first mismatch at tick ' + first : `final ${hashSim(A)}`);
  }
}
// ---- 2. tapes round-trip ---------------------------------------------------------------------------
{
  const b = botSim(TR.oval, 'rush', { car: 'banshee' });
  const words = [];
  for (let t = 0; t < 120 * 15; t++) words.push(b.next());
  const tape = decodeTape(JSON.parse(JSON.stringify(encodeTape({ level: 'oval.x3d', level_sha256: 'x', engine: b.sim.engine, mode: 'rush', car: 'banshee', entrants: b.sim.entrants, words, expect: { hash: hashSim(b.sim) } }))));
  const sim = createSim({ track: TR.oval, mode: tape.mode, entrants: tape.entrants });
  for (let t = 0; t < tape.ticks; t++) step(sim, [tape.words[t]]);
  check('tape round trip: 15 s of a bot replays to the same hash', hashSim(sim) === tape.expect.hash, `${tape.rle.length} runs for ${tape.ticks} ticks`);
  const u = unpackInput(packInput({ steer: -127, throttle: 15, brake: 9, handbrake: true, boost: true, shiftUp: true, shiftDown: false, reset: true }));
  check('packInput / unpackInput round trip', u.steer === -127 && u.throttle === 15 && u.brake === 9 && u.handbrake && u.boost && u.shiftUp && !u.shiftDown && u.reset);
}

// ---- 3. drift scoring rules, in place ------------------------------------------------------------------
function scoringAudit(track, car, mode, secs) {
  const b = botSim(track, mode, { car });
  const r = b.sim.race, c = b.car;
  const bad = { formula: 0, noCond: 0, mult: 0, trans: 0, grace: 0, bank: 0 };
  let scoredTicks = 0, lastScoreTick = -1, transitions = 0, banks = 0, multEvents = 0, zoneTicks = 0;
  let prevChain = 0, prevMult = 1, prevSign = 0, prevBanked = 0, prevActive = false;
  // an independent model of the transition rule: old side held >= 20 deg for 0.35 s while the course
  // turned >= 15 deg, new side reaches 20 deg within 1.0 s of the flip, 1.2 s since the last one
  const wrapA = a => { while (a > Math.PI) a -= 2 * Math.PI; while (a < -Math.PI) a += 2 * Math.PI; return a; };
  let course = 0, hold = 0, turn = 0, flipOK = false, flipAt = -10, lastTr = -10, lastDrift = -10;
  for (let t = 0; t < 120 * secs && r.phase !== 'finished'; t++) {
    const timeBefore = r.time;
    b.next();
    const crs = c.speed > 0.5 ? Math.atan2(c.vx, c.vz) : course, dC = wrapA(crs - course); course = crs;
    const ev = r.events, has = ty => ev.some(e => e.type === ty);
    const ab = Math.abs(c.slip);
    const cond = r.phase === 'running' && c.drifting && c.dsTick > 0.02 && c.offWheels <= RULES.maxOffWheels;
    const condRaw = ab >= RULES.driftSlip && c.speed >= RULES.driftSpeed && c.forwardSpeed > 0 && c.dsTick > 0.02 && c.offWheels <= 2;
    if (cond !== condRaw && r.phase === 'running') bad.noCond++;
    if (cond) {
      scoredTicks++;
      const zm = r.zone && r.zone.perfect ? 3 : r.zone && r.zone.clip ? 2 : 1;
      if (zm > 1) zoneTicks++;
      const pts = RULES.pointsPerTick * Math.min(ab, 60 * DEG) / (30 * DEG) * Math.min(c.speed * 3.6, 180) / 80 * r.multiplier * zm;
      const base = has('chainStart') || has('chainLost') ? 0 : prevChain;
      if (Math.abs(r.chain - (base + pts)) > 1e-9 * Math.max(1, r.chain)) bad.formula++;
      const s = c.slip > 0 ? 1 : -1;
      if (has('chainStart') || !prevActive) { hold = 0; turn = 0; flipOK = false; }
      else if (prevSign !== 0 && s !== prevSign && timeBefore - lastDrift <= RULES.transitionWindow) { flipOK = hold >= RULES.transitionHold && Math.abs(turn) >= RULES.transitionTurn; flipAt = timeBefore; hold = 0; turn = 0; }
      turn += dC;
      let expectTr = false;
      if (ab >= RULES.transitionSlip) {
        hold += 1 / 120;
        if (flipOK) { flipOK = false; if (timeBefore - flipAt <= RULES.transitionWindow && timeBefore - lastTr >= RULES.transitionCooldown) { expectTr = true; lastTr = timeBefore; } }
      }
      if (has('transition') !== expectTr) bad.trans++;
      if (has('transition')) {
        transitions++;
        if (!(r.multiplier === Math.min(RULES.multMax, prevMult + RULES.transitionStep + (has('multiplier') ? RULES.multStep : 0)))) bad.trans++;
      }
      lastDrift = timeBefore + 1 / 120;
      lastScoreTick = b.sim.tick;
    } else if (!has('chainStart') && !has('chainBank') && !has('chainLost') && r.chain !== prevChain) bad.formula++;
    if (has('chainLost') || has('chainBank')) { hold = 0; turn = 0; flipOK = false; }
    for (const e of ev) if (e.type === 'multiplier') { multEvents++; if (!(e.multiplier <= RULES.multMax)) bad.mult++; }
    if (has('chainBank')) {
      banks++;
      const gap = b.sim.tick - lastScoreTick;
      if (!has('finish') && (gap < 239 || gap > 242)) bad.grace++;
      const pts = ev.filter(e => e.type === 'chainBank').reduce((x, e) => x + e.points, 0);
      if (Math.abs(r.banked - (prevBanked + pts)) > 1e-6 && !has('cone')) bad.bank++;
      if (pts < prevChain - 1e-9) bad.bank++;
    }
    if (r.multiplier > RULES.multMax) bad.mult++;
    prevChain = r.chain; prevMult = r.multiplier; prevBanked = r.banked; prevActive = r.chainActive;
    if (cond) prevSign = c.slip > 0 ? 1 : -1;
    if (!r.chainActive) prevSign = 0;
  }
  return { bad, scoredTicks, transitions, banks, multEvents, zoneTicks, score: r.score };
}
{
  let allTr = 0;
  for (const [trk, car] of [['oval', 'banshee'], ['twisty', 'ronin'], ['oval', 'koi'], ['twisty', 'banshee']]) {
    const a = scoringAudit(TR[trk], car, 'rush', 95);
    const nb = Object.values(a.bad).reduce((x, y) => x + y, 0);
    allTr += a.transitions;
    check(`scoring in place, ${car} Drift Rush on ${trk}: points = 3 x angle/30deg x km/h/80 x multiplier x zone each drifting tick; ` +
      'drifting = slip >= 12 deg, >= 25 km/h, forward, <= 2 wheels off; transitions +1 (20 deg held 0.35 s, course turned 15 deg, 1.2 s apart); 2.0 s grace; banks keep the chain',
      nb === 0 && a.scoredTicks > 600 && a.banks > 0, `${a.scoredTicks} scoring ticks, ${a.transitions} transitions, ${a.banks} banks, score ${a.score.toFixed(0)}, violations ${JSON.stringify(a.bad)}`);
  }
  check('real transitions still count (the drift AI linking bends on the fixtures)', allTr > 0, `${allTr} transitions over the four audits`);
}
{
  // the multiplier on a continuous slide: +0.5 every 2.0 s, capped at x6
  const b = botSim(TR.skidpad, 'free', { car: 'ronin' });
  const r = b.sim.race, marks = [];
  let start = -1;
  for (let t = 0; t < 120 * 40; t++) { b.next(); for (const e of r.events) { if (e.type === 'chainStart' && start < 0) start = b.sim.tick; if (e.type === 'multiplier') marks.push([b.sim.tick, e.multiplier]); } }
  const gaps = marks.map((m, i) => m[0] - (i ? marks[i - 1][0] : start));
  check('multiplier +0.5 every 2.0 s of continuous drift, max x6 (skidpad, 40 s)', marks.length === 10 && gaps.every(g => g >= 239 && g <= 241) && marks[9][1] === 6 && r.multiplier === 6,
    `${marks.length} steps, gaps ${[...new Set(gaps)].join('/')} ticks, last x${marks.length ? marks[marks.length - 1][1] : 0}`);
}
// ---- 4. constructed rules ---------------------------------------------------------------------------
{
  // a wall hit with a chain pending loses it; the banked points stay
  const b = botSim(TR.oval, 'free', { car: 'banshee' });
  const r = b.sim.race, c = b.car;
  let t = 0;
  while (t++ < 120 * 120 && !(r.banked > 500 && r.chainActive && r.chain > 300 && c.drifting)) b.next();
  const banked = r.banked, chain = r.chain;
  // fling it at the nearer wall
  const side = c.lat > 0 ? 1 : -1, h = TR.oval.heading[c.seg];
  const lx = Math.cos(h), lz = -Math.sin(h), v = 22;
  c.vx = side * lx * v * 0.8 + Math.sin(h) * v * 0.6; c.vz = side * lz * v * 0.8 + Math.cos(h) * v * 0.6;
  let lost = null;
  for (let k = 0; k < 240 && !lost; k++) { b.next(); lost = evs(b.sim, 'chainLost')[0] || null; if (evs(b.sim, 'chainBank').length) break; }
  check('a crash loses the pending chain, banked points stay', !!lost && Math.abs(lost.points - chain) < chain * 0.5 + 50 && r.banked === banked && r.chain === 0,
    lost ? `lost ${Math.round(lost.points)} pending, banked ${Math.round(r.banked)} kept` : 'no chainLost');
}
{
  // a reset (R) with a chain pending loses it too: the chain is not banked after the grace
  const b = botSim(TR.oval, 'free', { car: 'banshee' });
  const r = b.sim.race;
  let t = 0;
  while (t++ < 120 * 120 && !(r.banked > 500 && r.chainActive && r.chain > 300 && b.car.drifting)) b.next();
  const banked = r.banked, chain = r.chain;
  b.next(inp => { inp.reset = true; });
  const lost = evs(b.sim, 'chainLost')[0] || null;
  let banks = 0;
  for (let k = 0; k < 240; k++) { b.next(inp => { inp.throttle = 0; inp.steer = 0; }); banks += evs(b.sim, 'chainBank').length; }
  check('a reset loses the pending chain, banked points stay', !!lost && banks === 0 && r.banked === banked && Math.abs(lost.points - chain) < chain * 0.1 + 50,
    lost ? `lost ${Math.round(lost.points)} pending on the reset tick, banked ${Math.round(r.banked)} kept, ${banks} banks after` : 'no chainLost on reset');
}
{
  // a knocked cone costs 250 in the drift modes and nothing in Time Attack
  const run = mode => {
    const b = botSim(TR.oval, mode, { car: 'ronin' });
    const r = b.sim.race, c = b.car;
    let t = 0;
    while (t++ < 120 * 120 && !(mode === 'attack' ? c.speed > 20 : r.banked > 600 && !r.chainActive && c.speed > 10)) b.next();
    const before = r.banked, cone = b.sim.props.find(p => p.kind === 1);
    const fwdX = Math.sin(c.yaw), fwdZ = Math.cos(c.yaw);
    cone.x = c.x + fwdX * 6; cone.z = c.z + fwdZ * 6;
    let hit = null;
    for (let k = 0; k < 120 && !hit; k++) { b.next(); hit = evs(b.sim, 'cone')[0] || null; }
    return { hit, before, after: r.banked, cones: r.cones };
  };
  const f = run('free'), a = run('attack');
  check('a knocked cone costs 250 points (free roam / Drift Rush)', !!f.hit && f.hit.penalty === RULES.conePenalty && Math.abs(f.before - RULES.conePenalty - f.after) < 1e-6 && f.cones === 1, f.hit ? `${Math.round(f.before)} -> ${Math.round(f.after)}` : 'no cone event');
  check('a knocked cone costs nothing in Time Attack', !!a.hit && !a.hit.penalty && a.after === 0, a.hit ? 'cone event, no penalty' : 'no cone event');
}
{
  // clipping zones: a skidpad copy with an inner-clip zone on the inside edge; the drift line is
  // pulled close to it (DRIFT.margin, restored after) so the rear wheels pass within the clip band
  const { meta } = readTrackMeta(text('skidpad'));
  const n = meta.center.length / 8;
  const m2 = { ...meta, zones: [Math.round(n * 0.1), Math.round(n * 0.6), 1, 1] };
  const T = buildTrack(m2, 'zone test');
  const keep = DRIFT.margin; DRIFT.margin = 0.35;
  const b = botSim(T, 'free', { car: 'ronin' });
  DRIFT.margin = keep;
  const r = b.sim.race;
  let clips = 0, perfects = 0, clipTicks = 0, perfectTicks = 0, badZone = 0;
  for (let t = 0; t < 120 * 40; t++) {
    b.next();
    clips += evs(b.sim, 'zoneClip').length; perfects += evs(b.sim, 'zonePerfect').length;
    const z = r.zone;
    if (z) {
      const scoring = b.car.drifting && b.car.dsTick > 0.02 && b.car.offWheels <= 2;
      if (z.clip !== (scoring && z.dist <= RULES.clipDist)) badZone++;
      if (z.perfect !== (z.clip && z.dist <= RULES.perfectDist && Math.abs(b.car.slip) >= RULES.perfectSlip)) badZone++;
      if (z.clip) clipTicks++; if (z.perfect) perfectTicks++;
    }
  }
  check('clipping zones: zoneClip within 2.0 m (x2), zonePerfect within 1.0 m at >= 35 deg (x3), once per pass', clips > 0 && badZone === 0 && clips <= 8,
    `${clips} clips, ${perfects} perfects, ${clipTicks} clip ticks, ${perfectTicks} perfect ticks`);
}
// ---- 5. laps, checkpoints, sectors, invalid laps, reset -------------------------------------------------
{
  const b = botSim(TR.twisty, 'attack', { car: 'tempest' });
  const r = b.sim.race, K = TR.twisty.checkpoints.length;
  let order = true, lastIdx = -1, lastCount = 0, sectorRows = [], cur = [];
  while (r.lapTimes.length < 2 && b.sim.tick < 120 * 200) {
    b.next();
    for (const e of r.events) {
      if (e.type === 'checkpoint' && e.car === 0) { if (lastIdx >= 0 && e.index !== (lastIdx + 1) % K) order = false; if (e.count !== lastCount + 1) order = false; lastIdx = e.index; lastCount = e.count; }
      if (e.type === 'sector') { cur.push(e); if (e.sector === 3) { sectorRows.push(cur); cur = []; } }
    }
  }
  check('checkpoints in order, one at a time, from the start line', order && lastCount === 2 * K + 1, `${lastCount} crossings, ${K} checkpoints`);
  const laps = r.lapTimes;
  const sectorsOk = sectorRows.length === 2 && sectorRows.every((row, k) => row.length === 3 && row.map(e => e.sector).join() === '1,2,3' &&
    Math.abs(row[0].time + row[1].time + row[2].time - laps[k].time) < 1e-9 && Math.abs(row[2].split - laps[k].time) < 1e-12);
  const deltaOk = sectorRows.length === 2 && Math.abs(sectorRows[1][0].delta - (sectorRows[1][0].time - sectorRows[0][0].time)) < 1e-9;
  check('three sectors per lap: splits add up to the lap, deltas against the best', sectorsOk && deltaOk, laps.map(l => l.sectors.map(x => x.toFixed(2)).join('+') + '=' + l.time.toFixed(3)).join('  '));
  // TEMPEST's targets: the track's (written for RONIN) x its measured pace, rounded to 0.1 s
  const T = medalTargets(TR.twisty.targets, 'tempest', 1, 'dry');
  check('TEMPEST medal targets are the track targets x 0.957 (its pace against RONIN)', T.goldLap === Math.round(TR.twisty.targets.goldLap * 0.957 * 10) / 10 &&
    r.targets.goldLap === T.goldLap && r.targets.rushGold === Math.round(TR.twisty.targets.rushGold * 0.35 / 50) * 50, `gold ${TR.twisty.targets.goldLap} -> ${T.goldLap}`);
  const best = Math.min(...laps.filter(l => l.valid).map(l => l.time));
  const want = best <= T.goldLap ? 'gold' : best <= T.silverLap ? 'silver' : best <= T.bronzeLap ? 'bronze' : 'none';
  check('Time Attack medal from the scaled targets', laps.every(l => l.valid) && want !== 'none' && r.medal === want,
    `best ${best.toFixed(3)} s vs gold ${T.goldLap} -> expected ${want}, got ${r.medal}`);
}
{
  // backwards: turn the car round on the grid and drive the wrong way; nothing counts
  const sim = createSim({ track: TR.oval, mode: 'attack', entrants: [{ car: 'ronin', driver: 'player' }] });
  const c = sim.cars[0], T = TR.oval;
  placeOnTrack(c, T, c.x, c.z, c.yaw + Math.PI, false);
  let cps = 0;
  for (let t = 0; t < 120 * 25; t++) {
    const P = {}; pointAtS(T, c.s - 15, P);
    const dx = P.x - c.x, dz = P.z - c.z, left = dx * Math.cos(c.yaw) - dz * Math.sin(c.yaw), fwd = dx * Math.sin(c.yaw) + dz * Math.cos(c.yaw);
    step(sim, [packInput({ throttle: c.speed < 18 ? 12 : 0, steer: Math.max(-127, Math.min(127, -Math.round(Math.atan2(left, fwd) * 200))) })]);
    cps += evs(sim, 'checkpoint').length;
  }
  check('driving the wrong way crosses no checkpoints', cps === 0 && sim.race.lapTimes.length === 0 && c.cpCount === 0, `${(c.distance / 1).toFixed(0)} m driven backwards`);
}
{
  // a skipped checkpoint: teleport 120 m up the road mid-lap; the lap cannot close until it is crossed
  const b = botSim(TR.oval, 'attack', { car: 'ronin' });
  const r = b.sim.race, c = b.car, T = TR.oval;
  while (c.cpCount < 3) b.next();
  const before = c.cpCount, P = {};
  pointAtS(T, c.s + 120, P);
  const v = c.speed, yaw = Math.atan2(P.tx, P.tz);
  placeOnTrack(c, T, P.x, P.z, yaw, false);
  c.vx = v * Math.sin(yaw); c.vz = v * Math.cos(yaw);
  for (const w of c.wheels) w.omega = v / c.P.R;
  c.gear = 3; c.clutch = 1;
  const t0 = b.sim.tick;
  while (b.sim.tick < t0 + 120 * 30) b.next();
  check('a skipped checkpoint is never credited out of order', c.cpCount === before && r.lapTimes.length === 0, `count ${before} before, ${c.cpCount} after 30 s`);
}
{
  // off the road for more than 1.0 s voids the lap; the next lap is valid again
  const b = botSim(TR.strip, 'attack', { car: 'ronin' });
  const r = b.sim.race, c = b.car;
  let inval = null;
  while (r.lapTimes.length < 2 && b.sim.tick < 120 * 300) {
    const t = b.sim.tick / 120;
    b.next(t > 10 && t < 12.5 ? (o => { o.steer = c.lat < 15 ? -50 : 0; o.brake = 0; }) : null);
    inval = inval || evs(b.sim, 'lapInvalid')[0] || null;
  }
  check('more than 1.0 s with 3+ wheels off the asphalt voids the lap, the next lap counts', !!inval && inval.reason === 'off' && r.lapTimes.length === 2 && !r.lapTimes[0].valid && r.lapTimes[1].valid,
    `laps ${r.lapTimes.map(l => l.time.toFixed(1) + (l.valid ? '' : ' (invalid)')).join(', ')}`);
}
{
  // reset to track: from the runoff, sideways and moving, onto the centreline facing the road
  const b = botSim(TR.twisty, 'attack', { car: 'koi' });
  const r = b.sim.race, c = b.car, T = TR.twisty;
  while (b.sim.tick < 120 * 12) b.next();
  const h = T.heading[c.seg];
  c.x += Math.cos(h) * 8.6; c.z -= Math.sin(h) * 8.6; c.yaw += 2.0; c.vx = 3; c.vz = -2;
  const sBefore = c.s;
  step(b.sim, [packInput({ reset: true })]);
  const ev = evs(b.sim, 'reset'), inv = evs(b.sim, 'lapInvalid');
  const yawErr = Math.abs(Math.atan2(Math.sin(c.yaw - T.heading[c.seg]), Math.cos(c.yaw - T.heading[c.seg])));
  const okPose = ev.length === 1 && Math.abs(c.lat) < 0.05 && c.speed === 0 && yawErr < 1e-9 && Math.abs(c.s - sBefore) < 3;
  step(b.sim, [packInput({ reset: true })]);
  const again = evs(b.sim, 'reset').length;
  check('reset puts the car on the centreline facing the road, stopped; it voids the lap; holding the key resets once', okPose && inv.length === 1 && inv[0].reason === 'reset' && again === 0,
    `lat ${c.lat.toFixed(3)}, yaw err ${yawErr.toExponential(1)}, ds ${(c.s - sBefore).toFixed(2)} m`);
}
// ---- 6. race: countdown, grid hold, positions, overtakes, finish ---------------------------------------------
{
  const entrants = [{ car: 'koi', driver: 'player', slot: 0 }, { car: 'tempest', driver: 'ai', skill: 1, slot: 3 }, { car: 'banshee', driver: 'ai', skill: 0.95, slot: 2 }, { car: 'ronin', driver: 'ai', skill: 0.9, slot: 1 }];
  const b = botSim(TR.oval, 'race', { entrants, ai: 'race', laps: 2 });
  const r = b.sim.race, cars = b.sim.cars;
  const counts = [];
  let goTick = -1, moved = false, posOk = true, overtakes = 0, overtakeOk = true, finishes = [];
  while (r.phase !== 'finished' && b.sim.tick < 120 * 240) {
    const prev = cars.map(c => c.position);
    b.next();
    for (const e of r.events) {
      if (e.type === 'countdown') counts.push(e.n);
      if (e.type === 'go') goTick = e.tick;
      if (e.type === 'overtake') { overtakes++; if (!(cars[e.car].position < prev[e.car] || prev[e.car] === 0)) overtakeOk = false; }
      if (e.type === 'finish') finishes.push(e);
    }
    if (r.phase === 'countdown' && cars.some(c => c.speed > 0.3)) moved = true;
    const pos = r.positions.slice().sort((x, y) => x - y).join();
    if (pos !== '0,1,2,3') posOk = false;
    const open = r.positions.filter(i => !cars[i].finished);
    for (let k = 1; k < open.length; k++) if (cars[open[k - 1]].raceDist < cars[open[k]].raceDist) posOk = false;
  }
  check('countdown 3-2-1 then go at 3.0 s; cars held on the grid', counts.join() === '3,2,1' && goTick === 359 && !moved, `countdown ${counts.join('-')}, go at tick ${goTick}`);
  check('positions by laps + progress every tick; overtakes improve the passer', posOk && overtakeOk, `${overtakes} overtakes`);
  const fo = r.results ? r.results.finishOrder : [];
  check('finish order, times and results', finishes.length >= 1 && finishes.every((e, k) => e.position === k + 1 && (k === 0 || e.time >= finishes[k - 1].time)) && fo.join() === finishes.map(e => e.car).join() && r.phase === 'finished',
    finishes.map(e => `P${e.position} car${e.car} ${e.time.toFixed(2)}s`).join(', '));
  // the race AI raced cleanly
  const crashes = [];
  const b2 = botSim(TR.twisty, 'race', { entrants: [{ car: 'ronin', driver: 'player' }, { car: 'tempest', driver: 'ai', skill: 1 }, { car: 'banshee', driver: 'ai', skill: 0.95 }, { car: 'koi', driver: 'ai', skill: 0.9 }], ai: 'race', laps: 2 });
  while (b2.sim.race.phase !== 'finished' && b2.sim.tick < 120 * 300) { b2.next(); for (const e of evs(b2.sim, 'crash')) if (e.impulse > 1500) crashes.push(e); }
  check('a 4-car AI race on the twisty fixture finishes without a heavy hit', b2.sim.race.phase === 'finished' && crashes.length === 0, `${b2.sim.race.finishOrder.length} finished, ${crashes.length} hits over 1500 N s`);
}
// ---- 7. tandem -------------------------------------------------------------------------------------
{
  const grade = q => q >= 0.75 ? 'S' : q >= 0.6 ? 'A' : q >= 0.45 ? 'B' : q >= 0.3 ? 'C' : 'D';
  const entrants = [{ car: 'ronin', driver: 'ai', ai: 'drift', skill: 1, slot: 0 }, { car: 'ronin', driver: 'player', slot: 1 }];
  const b = botSim(TR.oval, 'tandem', { entrants, ai: 'drift' });
  const r = b.sim.race;
  let gradeOk = true;
  while (r.phase !== 'finished' && b.sim.tick < 120 * 300) { b.next(); if (r.tandem.grade !== grade(r.tandem.quality)) gradeOk = false; }
  const parked = createSim({ track: TR.oval, mode: 'tandem', entrants });
  while (parked.race.phase !== 'finished' && parked.tick < 120 * 300) step(parked, [packInput({ brake: 15 })]);
  check('tandem: an AI lead drifts two laps; grade from quality (S >= 0.75, A >= 0.6, B >= 0.45, C >= 0.3)',
    r.phase === 'finished' && gradeOk && GRADES.includes(r.results.grade) && r.results.score > 0 && parked.race.phase === 'finished' && parked.race.results.grade === 'D' && parked.race.results.score === 0,
    `chasing bot: score ${r.results.score}, quality ${r.results.quality.toFixed(2)}, grade ${r.results.grade}; parked chaser: grade ${parked.race.results.grade}`);
}
// ---- 8. AI ----------------------------------------------------------------------------------------
{
  const rows = [];
  let ok = true;
  for (const trk of ['skidpad', 'oval', 'twisty']) for (const id of CAR_IDS) {
    const b = botSim(TR[trk], 'attack', { car: id });
    let hits = 0;
    while (b.sim.race.lapTimes.length < 2 && b.sim.tick < 120 * 200) { b.next(); for (const e of evs(b.sim, 'crash')) if (e.wall) hits++; }
    const L = b.sim.race.lapTimes;
    const good = L.length === 2 && L.every(l => l.valid) && hits === 0;
    ok = ok && good;
    rows.push(`${trk}/${id} ${L.length === 2 ? L[1].time.toFixed(2) : 'DNF'}${good ? '' : '!'}`);
  }
  check('race AI: two valid Time Attack laps, no wall contact, every car on every fixture', ok, rows.join(' '));
}
{
  const rows = [];
  let ok = true;
  for (const trk of ['oval', 'twisty']) for (const id of CAR_IDS) {
    const sim = createSim({ track: TR[trk], mode: 'free', entrants: [{ car: id, driver: 'ai', ai: 'drift', skill: 1, tune: DRIFT_SETUPS[id] }] });
    const c = sim.cars[0];
    let walls = 0, resets = 0, driftT = 0, sum = 0;
    for (let t = 0; t < 120 * 60; t++) {
      step(sim, []);
      for (const e of sim.race.events) { if (e.type === 'crash' && e.wall && e.impulse > 800) walls++; if (e.type === 'reset') resets++; }
      if (c.drifting) { driftT += 1 / 120; sum += Math.abs(c.slip); }
    }
    const mean = driftT > 0 ? sum / (driftT * 120) / DEG : 0;
    const good = walls === 0 && resets === 0 && driftT > 6;
    ok = ok && good;
    rows.push(`${trk}/${id} ${driftT.toFixed(0)}s@${mean.toFixed(0)}deg${good ? '' : ' walls ' + walls + ' resets ' + resets}`);
  }
  check('drift AI: 60 s on the oval and twisty fixtures with no wall hit and no reset, every car', ok, rows.join(' '));
}
{
  // the wet: the AI reads the surface (speed profiles on wet grip, smaller drift budgets)
  const rows = [];
  let ok = true;
  for (const trk of ['oval', 'twisty']) for (const id of CAR_IDS) {
    const b = botSim(TR[trk], 'attack', { car: id, surface: 'wet' });
    let hits = 0;
    while (b.sim.race.lapTimes.length < 2 && b.sim.tick < 120 * 200) { b.next(); for (const e of evs(b.sim, 'crash')) if (e.wall) hits++; }
    const L = b.sim.race.lapTimes;
    const sim = createSim({ track: TR[trk], mode: 'free', surface: 'wet', entrants: [{ car: id, driver: 'ai', ai: 'drift', skill: 1, tune: DRIFT_SETUPS[id] }] });
    let walls = 0, resets = 0, driftT = 0;
    for (let t = 0; t < 120 * 60; t++) {
      step(sim, []);
      for (const e of sim.race.events) { if (e.type === 'crash' && e.wall && e.impulse > 800) walls++; if (e.type === 'reset') resets++; }
      if (sim.cars[0].drifting) driftT += 1 / 120;
    }
    const good = L.length === 2 && L.every(l => l.valid) && hits === 0 && walls === 0 && resets === 0 && driftT > 6;
    ok = ok && good;
    rows.push(`${trk}/${id} lap ${L.length === 2 ? L[1].time.toFixed(1) : 'DNF'} drift ${driftT.toFixed(0)}s${good ? '' : '! hits ' + hits + ' walls ' + walls + ' resets ' + resets}`);
  }
  check('wet: race AI valid laps with no wall contact and drift AI 60 s with no wall hit, every car on the oval and twisty', ok, rows.join(' '));
}
// ---- 8b. every circuit the world builder ships (levels/MANIFEST.json), when there are any ---------------------
{
  let man = null;
  try { man = JSON.parse(readFileSync(ROOT + 'levels/MANIFEST.json', 'utf8')); } catch { man = null; }
  const files = man && man.levels ? man.levels.map(l => l.file) : [];
  if (!files.length) console.log('skip circuits: no levels/MANIFEST.json yet');
  for (const f of files) {
    const T = parseTrack(readFileSync(ROOT + 'levels/' + f, 'utf8'));
    const rows = [];
    let ok = true;
    for (const id of CAR_IDS) {
      const b = botSim(T, 'attack', { car: id });
      let hits = 0;
      while (b.sim.race.lapTimes.length < 2 && b.sim.tick < 120 * 300) { b.next(); for (const e of evs(b.sim, 'crash')) if (e.wall) hits++; }
      const L = b.sim.race.lapTimes;
      const lapOk = L.length === 2 && L[1].valid && hits === 0;
      const sim = createSim({ track: T, mode: 'free', entrants: [{ car: id, driver: 'ai', ai: 'drift', skill: 1, tune: DRIFT_SETUPS[id] }] });
      let walls = 0, resets = 0, driftT = 0;
      for (let t = 0; t < 120 * 60; t++) {
        step(sim, []);
        for (const e of sim.race.events) { if (e.type === 'crash' && e.wall && e.impulse > 800) walls++; if (e.type === 'reset') resets++; }
        if (sim.cars[0].drifting) driftT += 1 / 120;
      }
      const driftOk = walls === 0 && resets === 0 && driftT > 5;
      ok = ok && lapOk && driftOk;
      rows.push(`${id} lap ${L.length === 2 ? L[1].time.toFixed(1) : 'DNF'}${lapOk ? '' : '!'} drift ${driftT.toFixed(0)}s${driftOk ? '' : ' walls ' + walls + ' resets ' + resets}`);
    }
    check(`${f}: race AI laps valid with no wall contact, drift AI 60 s with no wall hit, every car`, ok, rows.join(', '));
  }
}
// ---- 8b. contact edge cases ------------------------------------------------------------------------
{
  // two cars dropped onto each other, crossed at 1.5 rad: they must come apart, not lock together
  const rows = [];
  let ok = true;
  for (const off of [0, 0.2, 0.58, 1.0]) {
    const sim = createSim({ track: TR.oval, mode: 'free', entrants: [{ car: 'koi', driver: 'player' }, { car: 'tempest', driver: 'player', slot: 1 }] });
    const a = sim.cars[0], b = sim.cars[1], T = TR.oval, i = 40;
    placeOnTrack(a, T, T.x[i], T.z[i], T.heading[i], false); placeOnTrack(b, T, T.x[i] + off, T.z[i] + 0.3, T.heading[i] + 1.5, false);
    a.vx = 40 * Math.sin(a.yaw); a.vz = 40 * Math.cos(a.yaw);
    let locked = 0;
    for (let t = 0; t < 360; t++) { step(sim, [packInput({}), packInput({})]); if (Math.hypot(a.x - b.x, a.z - b.z) < 1.2) locked++; }
    const sep = Math.hypot(a.x - b.x, a.z - b.z);
    ok = ok && sep > 2 && locked < 30;
    rows.push(`${off} m: ${sep.toFixed(1)} m apart after 3 s, ${locked} ticks overlapped`);
  }
  check('cars dropped deep into each other separate (no locked pair)', ok, rows.join(', '));
}
{
  // a reset beside a stopped car never lands on it: it slides back along the lap
  const sim = createSim({ track: TR.oval, mode: 'free', entrants: [{ car: 'ronin', driver: 'player' }, { car: 'koi', driver: 'player', slot: 1 }] });
  const A = sim.cars[0], B = sim.cars[1], T = TR.oval, i = 60, h = T.heading[i];
  placeOnTrack(B, T, T.x[i], T.z[i], h, false);
  placeOnTrack(A, T, T.x[i] + 3 * Math.cos(h), T.z[i] - 3 * Math.sin(h), h + 2, false);
  step(sim, [packInput({ reset: true }), packInput({})]);
  const sep = Math.hypot(A.x - B.x, A.z - B.z), ds = arcDeltaS(T, B, A);
  check('reset next to another car places at least 5 m clear, behind it', sep >= 5 && ds < 0, `${sep.toFixed(2)} m from the other car, ${ds.toFixed(1)} m along the lap`);
}
{
  // a reset in Race voids the lap too (as in Time Attack), and loses nothing else
  const sim = createSim({ track: TR.oval, mode: 'race', laps: 2, entrants: [{ car: 'ronin', driver: 'player' }] });
  const drv = createDriver(sim, 0, 'race', 1), inp = {};
  let inval = null;
  for (let t = 0; t < 120 * 30 && !inval; t++) {
    driveAI(sim, drv, inp);
    if (sim.cars[0].cpCount >= 2 && sim.race.phase === 'running') inp.reset = true;
    step(sim, [packInput(inp)]); inp.reset = false;
    inval = evs(sim, 'lapInvalid')[0] || null;
  }
  check('a reset in Race voids the lap', !!inval && inval.reason === 'reset', inval ? 'lapInvalid reason ' + inval.reason : 'no lapInvalid event');
}
// ---- 9. performance --------------------------------------------------------------------------------
{
  const entrants = [{ car: 'ronin', driver: 'ai', skill: 1 }, { car: 'tempest', driver: 'ai', skill: 0.95 }, { car: 'banshee', driver: 'ai', skill: 0.9 }, { car: 'koi', driver: 'ai', skill: 0.92 },
    { car: 'ronin', driver: 'ai', ai: 'drift', skill: 1 }, { car: 'banshee', driver: 'ai', ai: 'drift', skill: 1 }];
  const sim = createSim({ track: TR.twisty, mode: 'race', entrants, laps: 3 });
  for (let t = 0; t < 600; t++) step(sim, []);           // warm up
  const N = 120 * 30, t0 = process.hrtime.bigint();
  for (let t = 0; t < N; t++) step(sim, []);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6 / N;
  check('performance: 6 cars (all AI) at 120 Hz cost under 1 ms per tick in Node', ms < 1.0, `${(ms * 1000).toFixed(0)} us per tick, ${(ms * 120).toFixed(1)} ms per simulated second`);
}

console.log(JSON.stringify({ race: fails === 0 ? 'pass' : 'fail', checks: count, failed: fails }));
process.exit(fails ? 1 : 0);
