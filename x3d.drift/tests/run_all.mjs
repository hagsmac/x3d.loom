// Every fast check, in order. Exit 0 only if all pass. (The browser check is tools/check_browser.cjs.)
//   node tests/run_all.mjs
//  1. the fixture tracks rebuild byte-identical (tests/fixtures/gen_fixtures.mjs --check)
//  2. the world rebuilds byte-identical (build/build_world.py --check), when the builder is present
//  3. portable math, the shipped circuits against the track contract, the handling card, keyboard
//     driving, the race director / scoring / AI / determinism suites, the AI on the shipped circuits,
//     adversarial scoring (wobbles, spinners, wall leaners, cars, tunes and the wet)
//  4. every tape (tapes/ and tests/fixtures/tapes/) replays to its recorded finish and hash
import { execFileSync } from 'node:child_process';
import { readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
const run = (cmd, args) => execFileSync(cmd, args, { cwd: ROOT, encoding: 'utf8', maxBuffer: 1 << 26 });
const last = out => { const l = out.trim().split('\n').filter(x => x.trim()); return l[l.length - 1] || ''; };
let ok = true;
function step(name, cmd, args, judge) {
  const t0 = Date.now();
  let out = '', pass = false;
  try { out = run(cmd, args); pass = judge ? judge(out) : true; } catch (e) { out = (e.stdout || '') + (e.stderr || ''); pass = false; }
  console.log(`${pass ? 'PASS' : 'FAIL'} ${name}  ${last(out).slice(0, 220)}  (${((Date.now() - t0) / 1000).toFixed(1)} s)`);
  if (!pass) console.log(out.split('\n').filter(l => l.startsWith('FAIL')).join('\n'));
  ok &&= pass;
}

step('fixtures rebuild identical', 'node', ['tests/fixtures/gen_fixtures.mjs', '--check'], o => JSON.parse(last(o)).fixtures_identical === true);
if (existsSync(ROOT + 'build/build_world.py')) step('world rebuilds identical', 'python3', ['-I', 'build/build_world.py', '--check']);
step('portable math', 'node', ['tests/fmath.test.mjs'], o => JSON.parse(last(o)).fmath === 'pass');
step('shipped circuits against the track contract', 'node', ['tests/levels.test.mjs'], o => JSON.parse(last(o)).levels === 'pass');
step('handling card', 'node', ['tests/handling.test.mjs'], o => JSON.parse(last(o)).handling === 'pass');
step('a keyboard player can drift every car', 'node', ['tests/keyboard.test.mjs'], o => JSON.parse(last(o)).keyboard === 'pass');
step('race, scoring, AI, determinism', 'node', ['tests/race.test.mjs'], o => JSON.parse(last(o)).race === 'pass');
step('the AI on the shipped circuits', 'node', ['tests/circuits.test.mjs'], o => JSON.parse(last(o)).circuits === 'pass');
step('drivers that farm points earn no medal', 'node', ['tests/exploits.test.mjs'], o => JSON.parse(last(o)).exploits === 'pass');

const tapes = [];
for (const dir of ['tapes/', 'tests/fixtures/tapes/']) if (existsSync(ROOT + dir)) for (const f of readdirSync(ROOT + dir).filter(f => f.endsWith('.tape.json')).sort()) tapes.push(dir + f);
if (!tapes.length) { console.log('FAIL no tapes found'); ok = false; }
for (const t of tapes) {
  let r = null;
  try { r = JSON.parse(last(run('node', ['tools/replay.mjs', t]))); } catch (e) { r = null; }
  const pass = !!r && r.state === 'won' && r.hash === r.expect.hash && r.level_sha256 === r.level_sha256_tape && r.engine === r.engine_tape;
  const what = !r ? 'no output' : r.mode === 'attack' ? `lap ${r.lapTime} s (${r.medal})` : r.mode === 'rush' ? `score ${r.score} (${r.medal})`
    : r.mode === 'race' ? `finished P${r.position}` : r.mode === 'tandem' ? `grade ${r.results && r.results.grade} (quality ${r.results ? r.results.quality.toFixed(2) : '-'})` : `frame ${r.frame}`;
  console.log(`${pass ? 'PASS' : 'FAIL'} tape ${t}  ${r ? r.hash : ''}  ${what}  goal tick ${r ? r.goal_tick : '-'}`);
  ok &&= pass;
}
console.log(JSON.stringify({ run_all: ok ? 'pass' : 'fail', tapes: tapes.length }));
process.exit(ok ? 0 : 1);
