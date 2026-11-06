// Replay a tape headless and print the outcome as JSON (the Loom play witness calls this).
//   node tools/replay.mjs tapes/1-1-tinker-meadow.tape.json [--level levels/other.x3d]
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createGame, step, summary, ENGINE_VERSION } from '../engine/game.js';
import { decodeTape } from '../engine/tape.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const args = process.argv.slice(2);
const tapePath = args[0];
const li = args.indexOf('--level');
const tape = decodeTape(JSON.parse(readFileSync(tapePath, 'utf8')));
const levelPath = li >= 0 ? args[li + 1] : ROOT + 'levels/' + tape.level;
const text = readFileSync(levelPath, 'utf8');
const sha = createHash('sha256').update(text).digest('hex');
const t0 = performance.now();
const g = createGame(text);
let goalTick = -1;
for (let i = 0; i < tape.bits.length; i++) {
  step(g, tape.bits[i]);
  if (goalTick < 0 && g.state === 'won') goalTick = g.frame;
  g.events.length = 0;
}
const ms = performance.now() - t0;
console.log(JSON.stringify({ tape: tapePath, level: tape.level, level_sha256: sha, level_sha256_tape: tape.level_sha256,
  engine: ENGINE_VERSION, engine_tape: tape.engine, ticks: tape.ticks, goal_tick: goalTick, ...summary(g),
  expect: tape.expect, cpu_ms: +ms.toFixed(1), node: process.version }));
