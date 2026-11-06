// The AI on the shipped circuits (CONTRACT.md section 9), every level in levels/MANIFEST.json:
//   node tests/circuits.test.mjs        (about 45 s)
// 1. Race-line AI, every car, Time Attack: at skill 1 both laps valid with no wall contact at all;
//    at skill 0.5 also clean, and its flying lap at least 2.5% slower.
// 2. Drift-mode AI as the Tandem lead, every car, two laps on the dry and on the wet: it finishes
//    with no wall contact and no reset, and on the dry its held slides average 30-40 deg (27-40 for
//    the AWD TEMPEST, which slides shallower by design).
// 3. Races: the player entrant (driven by the race AI at skill 0.9) against three RONINs at skill
//    1.0, 0.75 and 0.5, three laps: everyone finishes, the three AI finish within 8% of each other,
//    the skill-1 car beats the skill-0.5 car, and nobody touches in the first 15 s (no start pile-up).
//    The default race grid (four different cars) also finishes with no contact off the start.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseTrack, createSim, step, packInput, CAR_IDS } from '../engine/sim.js';
import { createDriver, driveAI } from '../engine/ai.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const DEG = Math.PI / 180;
const man = JSON.parse(readFileSync(ROOT + 'levels/MANIFEST.json', 'utf8'));
const tracks = man.levels.map(lv => [lv.id, parseTrack(readFileSync(ROOT + 'levels/' + lv.file, 'utf8'))]);
let fails = 0, count = 0;
const line = (ok, text) => { count++; if (!ok) fails++; console.log(`${ok ? 'ok  ' : 'FAIL'} ${text}`); };
const report = {};

/** Two Time Attack laps by the race-line AI driving the player entrant. */
function attack(T, car, skill) {
  const sim = createSim({ track: T, mode: 'attack', entrants: [{ car, driver: 'player' }] });
  const drv = createDriver(sim, 0, 'race', skill), inp = {};
  let walls = 0;
  while (sim.tick < 120 * 400 && sim.race.lapTimes.length < 2) {
    driveAI(sim, drv, inp); step(sim, [packInput(inp)]);
    for (const e of sim.race.events) if (e.type === 'crash' && e.wall) walls++;
  }
  const laps = sim.race.lapTimes;
  return { laps: laps.map(l => +l.time.toFixed(2)), valid: laps.length === 2 && laps.every(l => l.valid), walls, lap: laps.length ? laps[laps.length - 1].time : Infinity };
}

/** Tandem: the drift AI leads two laps; the player entrant sits parked on the grid. */
function tandemLead(T, car, surface) {
  const sim = createSim({ track: T, mode: 'tandem', surface, entrants: [{ car, driver: 'ai', ai: 'drift', skill: 1, slot: 0 }, { car: 'ronin', driver: 'player', slot: 1 }] });
  const c = sim.cars[0], d = sim.drivers[0], park = packInput({ handbrake: true });
  let walls = 0, resets = 0, holdN = 0, holdSum = 0;
  while (sim.race.phase !== 'finished' && sim.tick < 120 * 600) {
    step(sim, [park]);
    for (const e of sim.race.events) { if (e.type === 'crash' && e.wall && e.car === 0) walls++; if (e.type === 'reset' && e.car === 0) resets++; }
    if (sim.race.phase === 'running' && d.phase === 'hold') { holdN++; holdSum += Math.abs(c.slip) / DEG; }
  }
  return { finished: sim.race.phase === 'finished', laps: c.lapsDone, time: sim.race.time, walls, resets, holdS: holdN / 120, holdDeg: holdN ? holdSum / holdN : 0 };
}

/** A race to the end: every car finishes (the sim keeps running after the player is home). */
function race(T, entrants, playerSkill = 0.9) {
  const sim = createSim({ track: T, mode: 'race', laps: 3, entrants });
  const pd = createDriver(sim, sim.playerIndex, 'race', playerSkill), inp = {};
  let startContacts = 0, contacts = 0, walls = 0;
  while (sim.tick < 120 * 900 && !sim.cars.every(c => c.finished)) {
    driveAI(sim, pd, inp); step(sim, [packInput(inp)]);
    for (const e of sim.race.events) {
      if (e.type === 'crash' && !e.wall) { contacts++; if (sim.tick < 120 * 15) startContacts++; }
      if (e.type === 'crash' && e.wall) walls++;
    }
  }
  return { sim, all: sim.cars.every(c => c.finished), times: sim.cars.map(c => c.finished ? c.raceTime : Infinity), startContacts, contacts, walls };
}

for (const [id, T] of tracks) {
  report[id] = { attack: {}, tandem: {}, race: {} };
  // 1. race-line AI
  for (const car of CAR_IDS) {
    const a1 = attack(T, car, 1), a5 = attack(T, car, 0.5);
    report[id].attack[car] = { skill1: a1.laps, skill05: a5.laps };
    const slower = a5.lap / a1.lap - 1;
    line(a1.valid && a1.walls === 0 && a5.valid && a5.walls === 0 && slower >= 0.025,
      `${id} ${car} race AI: skill 1 laps ${a1.laps.join(' / ')} s, skill 0.5 ${a5.laps.join(' / ')} s (${(100 * slower).toFixed(1)}% slower), wall contacts ${a1.walls} / ${a5.walls}`);
  }
  // 2. drift AI as the tandem lead
  for (const surface of ['dry', 'wet']) for (const car of CAR_IDS) {
    const r = tandemLead(T, car, surface);
    report[id].tandem[car + '_' + surface] = { time: +r.time.toFixed(1), holdS: +r.holdS.toFixed(1), holdDeg: +r.holdDeg.toFixed(1), walls: r.walls };
    const lo = car === 'tempest' ? 27 : 30;
    const angleOk = surface === 'wet' || (r.holdDeg >= lo && r.holdDeg <= 40);
    line(r.finished && r.laps >= 2 && r.walls === 0 && r.resets === 0 && angleOk,
      `${id} ${car} ${surface} tandem lead: two laps in ${r.time.toFixed(1)} s, ${r.walls} wall contacts, ${r.resets} resets, held slides ${r.holdS.toFixed(0)} s at a mean ${r.holdDeg.toFixed(1)} deg${surface === 'dry' ? ` (window ${lo}-40)` : ''}`);
  }
  // 3. races
  const mixed = race(T, [{ car: 'ronin', driver: 'player', slot: 3 }, { car: 'ronin', driver: 'ai', skill: 1.0, slot: 0 }, { car: 'ronin', driver: 'ai', skill: 0.75, slot: 1 }, { car: 'ronin', driver: 'ai', skill: 0.5, slot: 2 }]);
  const ai = mixed.times.slice(1), spread = (Math.max(...ai) - Math.min(...ai)) / Math.min(...ai);
  report[id].race.mixed = { times: mixed.times.map(t => +t.toFixed(2)), spread: +(100 * spread).toFixed(1), contacts: mixed.contacts };
  line(mixed.all && spread < 0.08 && ai[0] < ai[2] && mixed.startContacts === 0 && mixed.walls === 0,
    `${id} race, RONIN AI at skill 1 / 0.75 / 0.5 (+ player bot 0.9): ${mixed.times.map(t => t.toFixed(1)).join(' / ')} s, AI spread ${(100 * spread).toFixed(1)}%, contacts ${mixed.startContacts} in the first 15 s (${mixed.contacts} in all), wall contacts ${mixed.walls}`);
  const grid = race(T, undefined);
  report[id].race.grid = { cars: grid.sim.cars.map(c => c.id), times: grid.times.map(t => +t.toFixed(2)), contacts: grid.contacts };
  line(grid.all && grid.startContacts === 0 && grid.walls === 0,
    `${id} race, default grid ${grid.sim.cars.map((c, i) => c.id + (i === grid.sim.playerIndex ? '*' : '')).join(' ')}: ${grid.times.map(t => t.toFixed(1)).join(' / ')} s, contacts ${grid.startContacts} in the first 15 s, wall contacts ${grid.walls}`);
}
console.log(JSON.stringify({ report }));
console.log(JSON.stringify({ circuits: fails ? 'fail' : 'pass', checks: count, failed: fails }));
process.exit(fails ? 1 : 0);
