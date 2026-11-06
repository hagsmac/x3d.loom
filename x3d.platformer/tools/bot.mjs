// Route bots: closed-loop players that read the game state every tick and press buttons, like a
// person would. Each run is recorded as an open-loop tape (engine/tape.js); the tape, not the
// bot, is the proof of play the Loom checks. Usage:
//   node tools/bot.mjs 1-1            play world 1-1 and write tapes/<level>.tape.json
//   node tools/bot.mjs 1-1 --trace    also print the route's progress
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createGame, step, summary, BTN, ENGINE_VERSION } from '../engine/game.js';
import { encodeTape } from '../engine/tape.js';
import { ROUTES } from './routes.mjs';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const want = process.argv[2] || '1-1';
const trace = process.argv.includes('--trace');
const manifest = JSON.parse(readFileSync(ROOT + 'levels/MANIFEST.json', 'utf8'));
const L = manifest.levels.find(l => l.file.startsWith(want));
if (!L) { console.error('no level', want); process.exit(2); }
const text = readFileSync(ROOT + 'levels/' + L.file, 'utf8');
const sha = createHash('sha256').update(text).digest('hex');
const route = ROUTES[L.key];
if (!route) { console.error('no route for', L.key); process.exit(2); }

const g = createGame(text);
const bits = [];
const log = [];
const ctx = {
  g, BTN, t: 0,
  mark(label) { const s = { tick: g.frame, label, x: +g.hero.x.toFixed(2), y: +g.hero.y.toFixed(2), cogs: g.cogs, deaths: g.deaths }; log.push(s); if (trace) console.log(JSON.stringify(s)); },
};
const it = route(ctx);
const MAX = 120 * 60 * 5;
let res = it.next();
while (!res.done && g.frame < MAX && g.state !== 'won') {
  const b = res.value | 0;
  step(g, b); bits.push(b);
  for (const ev of g.events) if (trace && ['die', 'checkpoint', 'star', 'goal', 'break', 'spring', 'hook', 'pound'].includes(ev.type)) console.log('  ev', ev.type, ev.x.toFixed(1), ev.y.toFixed(1), ev.why || '');
  g.events.length = 0;
  res = it.next();
}
// let the finish settle for one second so the tape ends on the celebration
for (let i = 0; i < 120 && g.state === 'won'; i++) { step(g, 0); bits.push(0); g.events.length = 0; }
const out = summary(g);
console.log(JSON.stringify({ level: L.file, ...out, route_marks: log.length }));
if (g.state !== 'won') { console.error('BOT FAILED: did not reach the goal', out); process.exit(1); }
mkdirSync(ROOT + 'tapes', { recursive: true });
const tape = encodeTape({ level: L.file, level_sha256: sha, engine: ENGINE_VERSION, bits, expect: out,
  note: `recorded by tools/bot.mjs route ${L.key}; ${log.length} route marks` });
const path = ROOT + 'tapes/' + L.file.replace('.x3d', '.tape.json');
writeFileSync(path, JSON.stringify(tape) + '\n');
console.log('wrote', path.replace(ROOT, ''), `${tape.rle.length} runs, ${tape.ticks} ticks (${(tape.ticks / 120).toFixed(2)} s)`);
