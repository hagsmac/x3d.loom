// Replay a tape headless and print the outcome as one JSON line (the Loom play witness runs this).
//   node tools/replay.mjs <tape.json> [--level path/to/level.x3d]
// The level is found by the tape's file name in levels/, then tests/fixtures/ (the one whose
// sha256 matches the tape wins). state is "won" when the recorded goal is met: a valid lap for an
// attack tape, the stated medal or better for a rush tape (CONTRACT.md section 10), the finish of
// a race or tandem tape (the player crossed the line; AI rivals and contact replay inside the sim),
// the last tick of a free tape. The rule lives in engine/goal.js (the page uses the same one).
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseTrack, createSim, step, hashSim, summary, ENGINE_VERSION } from '../engine/sim.js';
import { decodeTape, simOptionsFromTape } from '../engine/tape.js';
import { goalReached, goalState } from '../engine/goal.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));

/** Replay decoded tape `tape` on level text; returns the runner's JSON object. */
export function replay(tape, text) {
  const sha = createHash('sha256').update(text).digest('hex');
  const t0 = process.hrtime.bigint();
  const sim = createSim({ ...simOptionsFromTape(tape, parseTrack(text)) });
  const words = tape.words, one = [0];
  let goalTick = -1;
  const want = tape.expect && tape.expect.medal ? tape.expect.medal : 'gold';
  for (let i = 0; i < words.length; i++) {
    one[0] = words[i];
    step(sim, one);
    if (goalTick < 0 && goalReached(sim, tape.mode, want, i === words.length - 1)) goalTick = sim.tick;
  }
  const s = summary(sim), r = sim.race;
  const cpu = Number(process.hrtime.bigint() - t0) / 1e6;
  const out = { tape: tape.level.replace(/\.x3d$/, '') + '-' + tape.mode, level: tape.level, level_sha256: sha, level_sha256_tape: tape.level_sha256,
    engine: ENGINE_VERSION, engine_tape: tape.engine, mode: tape.mode, car: tape.car, ticks: words.length,
    state: goalState(goalTick, sim), hash: hashSim(sim), frame: sim.tick, goal_tick: goalTick };
  if (tape.mode === 'attack') { out.lapTime = r.bestLap > 0 ? +r.bestLap.toFixed(4) : null; out.validLaps = s.validLaps; out.medal = r.medal; }
  else if (tape.mode === 'rush') { out.score = s.score; out.medal = r.medal; out.medal_stated = want; }
  else if (tape.mode === 'race' || tape.mode === 'tandem') { out.position = s.position; out.results = s.results; }
  out.expect = tape.expect; out.cpu_ms = +cpu.toFixed(1); out.node = process.version;
  return out;
}

/** Find the level file a tape names: levels/ then tests/fixtures/, preferring a sha match. */
export function findLevel(tape) {
  const cands = [ROOT + 'levels/' + tape.level, ROOT + 'tests/fixtures/' + tape.level].filter(p => existsSync(p));
  for (const p of cands) {
    const text = readFileSync(p, 'utf8');
    if (createHash('sha256').update(text).digest('hex') === tape.level_sha256) return { path: p, text };
  }
  if (!cands.length) throw new Error('level not found: ' + tape.level);
  return { path: cands[0], text: readFileSync(cands[0], 'utf8') };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const args = process.argv.slice(2);
  const li = args.indexOf('--level');
  const tape = decodeTape(JSON.parse(readFileSync(args[0], 'utf8')));
  const text = li >= 0 ? readFileSync(args[li + 1], 'utf8') : findLevel(tape).text;
  console.log(JSON.stringify(replay(tape, text)));
}
