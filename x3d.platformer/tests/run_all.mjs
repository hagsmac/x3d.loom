// Every fast check, in order: the levels rebuild byte-identical, the feel card holds, and every tape
// replays to its recorded finish. Exit 0 only if all pass. (The browser check is tools/check_browser.cjs.)
import { execFileSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const ROOT = fileURLToPath(new URL('..', import.meta.url));
const run = (cmd, args) => execFileSync(cmd, args, { cwd: ROOT, encoding: 'utf8' });
let ok = true;
const rebuild = JSON.parse(run('python3', ['-I', 'build/build_levels.py', '--check']).trim());
console.log('rebuild', JSON.stringify(rebuild)); ok &&= rebuild.rebuild_identical;
try { run('node', ['tests/feel.test.mjs']); console.log('feel card: all windows hold'); } catch (e) { console.log(e.stdout); ok = false; }
for (const t of readdirSync(ROOT + 'tapes').filter(f => f.endsWith('.tape.json')).sort()) {
  const r = JSON.parse(run('node', ['tools/replay.mjs', 'tapes/' + t]).trim());
  const pass = r.state === 'won' && r.hash === r.expect.hash && r.level_sha256 === r.level_sha256_tape && r.engine === r.engine_tape;
  console.log(pass ? 'PASS' : 'FAIL', t, r.hash, `goal tick ${r.goal_tick}`, `${r.cogs}/${r.cogsTotal} cogs`, `${r.stars}/${r.starsTotal} stars`, `${r.deaths} deaths`);
  ok &&= pass;
}
process.exit(ok ? 0 : 1);
