// Record proof-of-play tapes: the AI drives the PLAYER entrant (it sees only the sim, like any
// controller), every tick's packed Input word is recorded, and the tape is bound to the level's
// sha256 and the engine version (CONTRACT.md section 10).
//   node tools/bot.mjs <level.x3d> [--mode attack|rush|both] [--car ronin] [--tune '{"traction":1}']
//                      [--surface dry|wet] [--skill 1] [--laps 2] [--out DIR] [--dry-run]
//         --mode race|tandem are recorded only when asked for (not by 'both').
// attack: race-line AI, two laps (the first starts rolling from the grid); the goal is a valid lap.
// rush:   drift-mode AI for the 90 s Drift Rush; the goal is the medal the tape states (gold).
// race:   race-line AI from the back of the page's default 4-car grid; the goal is the finish line.
// tandem: drift-mode AI chasing the drift-AI lead, throttle held back inside 6 m (there is no
//         chase AI in the sim, so this grades D); the goal is the finish line.
// Prints one JSON line per tape with the result and the targets it suggests for the track:
//   gold lap = bot lap x 1.02, silver x 1.08, bronze x 1.16; rush gold = score x 0.85,
//   platinum x 1.1, silver x 0.6, bronze x 0.35 (so a medal is something a good run earns).
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseTrack, createSim, step, packInput, hashSim, summary, ENGINE_VERSION } from '../engine/sim.js';
import { createDriver, driveAI } from '../engine/ai.js';
import { encodeTape, createRecorder } from '../engine/tape.js';
import { goalReached } from '../engine/goal.js';

export const LAP_FACTORS = { gold: 1.02, silver: 1.08, bronze: 1.16 };
export const RUSH_FACTORS = { bronze: 0.35, silver: 0.6, gold: 0.85, platinum: 1.1 };

/** Drive the player entrant of a fresh sim with the AI and record it. Returns { words, sim, goalTick }. */
export const RACE_GRID = [{ car: 'tempest', driver: 'ai', skill: 0.92, slot: 0, ai: 'race' }, { car: 'banshee', driver: 'ai', skill: 0.86, slot: 1, ai: 'race' },
  { car: 'koi', driver: 'ai', skill: 0.95, slot: 2, ai: 'race' }];
export const TANDEM_GAP = 6;

export function botRun({ track, mode, car = 'ronin', tune = {}, surface = 'dry', skill = 1, laps = 2, maxSeconds = 600, stateMedal = 'gold' }) {
  const me = { car, tune, driver: 'player', slot: 0 };
  const entrants = mode === 'race' ? [{ ...me, slot: 3 }, ...RACE_GRID]
    : mode === 'tandem' ? [{ car: 'ronin', driver: 'ai', skill: 1, slot: 0, ai: 'drift' }, { ...me, slot: 1 }] : [me];
  const sim = createSim({ track, mode, surface, entrants, laps: mode === 'race' || mode === 'tandem' ? laps : undefined });
  const pi = sim.playerIndex;
  const drv = createDriver(sim, pi, mode === 'attack' || mode === 'race' ? 'race' : 'drift', skill);
  const rec = createRecorder();
  const inp = {};
  let goalTick = -1;
  for (let i = 0; i < maxSeconds * 120; i++) {
    driveAI(sim, drv, inp);
    if (mode === 'tandem') {  // a chaser that lifts when it closes on the lead
      const gap = sim.cars[0].raceDist - sim.cars[pi].raceDist;
      if (gap < TANDEM_GAP) { inp.throttle = Math.round(inp.throttle * Math.max(0, (gap - 1) / (TANDEM_GAP - 1))); if (gap < 1.2) inp.brake = 4; }
    }
    const w = packInput(inp);
    rec.push(w);
    step(sim, [w]);
    const r = sim.race;
    if (goalTick < 0 && goalReached(sim, mode, stateMedal, i === maxSeconds * 120 - 1)) goalTick = sim.tick;   // engine/goal.js, as replay.mjs
    if (mode === 'attack') { if (r.lapTimes.length >= laps) break; }
    else if (r.phase === 'finished') break;
  }
  return { words: rec.words, sim, goalTick, entrants };
}

/** Suggested targets from a bot's best lap and rush score, in the metadata order. */
export function suggestTargets(lap, score) {
  const r1 = x => Math.round(x * 10) / 10, r50 = x => Math.round(x / 50) * 50;
  return [r1(lap * LAP_FACTORS.gold), r1(lap * LAP_FACTORS.silver), r1(lap * LAP_FACTORS.bronze),
    r50(score * RUSH_FACTORS.bronze), r50(score * RUSH_FACTORS.silver), r50(score * RUSH_FACTORS.gold), r50(score * RUSH_FACTORS.platinum)];
}

function main() {
  const args = process.argv.slice(2);
  const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : d; };
  const levelPath = args[0];
  if (!levelPath || levelPath.startsWith('--')) { console.error('usage: node tools/bot.mjs <level.x3d> [--mode attack|rush|both] [--car id] [--out DIR]'); process.exit(2); }
  const text = readFileSync(levelPath, 'utf8');
  const sha = createHash('sha256').update(text).digest('hex');
  const track = parseTrack(text);
  const level = basename(levelPath);
  const modes = opt('mode', 'both') === 'both' ? ['attack', 'rush'] : [opt('mode')];
  const car = opt('car', 'ronin'), tune = JSON.parse(opt('tune', '{}')), surface = opt('surface', 'dry');
  const skill = Number(opt('skill', '1')), laps = Number(opt('laps', '2'));
  const out = resolve(opt('out', dirname(fileURLToPath(import.meta.url)) + '/../tapes'));
  const dry = args.includes('--dry-run');
  const res = {};
  for (const mode of modes) {
    const t0 = Date.now();
    const { words, sim, goalTick, entrants } = botRun({ track, mode, car, tune, surface, skill, laps });
    const s = summary(sim), r = sim.race;
    const expect = { hash: hashSim(sim), state: goalTick >= 0 ? 'won' : 'lost', frame: sim.tick };
    if (mode === 'attack') { expect.lapTime = +r.bestLap.toFixed(4); expect.medal = r.medal; expect.validLaps = s.validLaps; }
    else if (mode === 'rush') { expect.score = s.score; expect.medal = 'gold'; expect.medalReached = r.medal; }
    else { expect.position = s.position; expect.results = s.results; }
    const tape = encodeTape({ level, level_sha256: sha, engine: ENGINE_VERSION, mode, car, tune, surface, laps: sim.laps, entrants, words, expect,
      note: mode === 'attack' ? `bot: race-line AI, ${laps} laps, best valid lap ${r.bestLap.toFixed(3)} s`
        : mode === 'rush' ? `bot: drift-mode AI, Drift Rush score ${s.score}`
          : mode === 'race' ? `bot: race-line AI from the back of a 4-car grid, ${laps} laps, finished P${s.position}`
            : `bot: drift-mode AI chasing the drift-AI lead, ${laps} laps, tandem grade ${s.results && s.results.grade}` });
    const name = level.replace(/\.x3d$/, '') + '-' + mode + '.tape.json';
    if (!dry) { mkdirSync(out, { recursive: true }); writeFileSync(out + '/' + name, JSON.stringify(tape) + '\n'); }
    res[mode] = { lap: r.bestLap, score: s.score };
    console.log(JSON.stringify({ tape: dry ? null : out + '/' + name, level, mode, car, state: expect.state, ticks: words.length, rle: tape.rle.length,
      lapTime: expect.lapTime, score: expect.score, medal: r.medal, laps: r.lapTimes.map(l => [+l.time.toFixed(3), l.valid]), hash: expect.hash, cpu_ms: Date.now() - t0 }));
  }
  if (res.attack && res.rush) console.log(JSON.stringify({ level, suggested_targets: suggestTargets(res.attack.lap, res.rush.score) }));
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) main();
