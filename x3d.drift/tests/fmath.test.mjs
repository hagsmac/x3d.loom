// Portable math accuracy (CONTRACT.md section 2): every engine/fmath.js function against Math.*
// on its working range, plus a few exact identities and a scan that no // loom:sim file calls
// non-portable math. Exit 1 on any failure.
//   node tests/fmath.test.mjs
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dsin, dcos, datan, datan2, dexp, dtanh, wrapPi, ihash, inoise, PI } from '../engine/fmath.js';

const ROOT = fileURLToPath(new URL('..', import.meta.url));
let fails = 0;
const rows = [];
function check(name, ok, detail) { rows.push({ name, ok, detail }); if (!ok) fails++; }

/** Max absolute error (or relative where |ref| > 1) of f vs ref over n points of [a, b]. */
function sweep(f, ref, a, b, n, rel = false) {
  let worst = 0, at = a;
  for (let i = 0; i <= n; i++) {
    const x = a + (b - a) * i / n;
    const r = ref(x), v = f(x);
    let e = Math.abs(v - r);
    if (rel && Math.abs(r) > 1) e /= Math.abs(r);
    if (e > worst) { worst = e; at = x; }
  }
  return { worst, at };
}

const TOL = 1e-9;   // the contract asks for 1e-6; the functions do far better
const cases = [
  ['dsin on [-50, 50]', dsin, Math.sin, -50, 50],
  ['dcos on [-50, 50]', dcos, Math.cos, -50, 50],
  ['datan on [-1e3, 1e3]', datan, Math.atan, -1e3, 1e3],
  ['datan on [-2, 2]', datan, Math.atan, -2, 2],
  ['dtanh on [-25, 25]', dtanh, Math.tanh, -25, 25],
];
for (const [name, f, ref, a, b] of cases) {
  const { worst, at } = sweep(f, ref, a, b, 200001);
  check(name, worst < TOL, `max err ${worst.toExponential(2)} at ${at.toFixed(4)}`);
}
{
  const { worst, at } = sweep(dexp, Math.exp, -40, 40, 200001, true);
  check('dexp on [-40, 40] (relative)', worst < TOL, `max rel err ${worst.toExponential(2)} at ${at.toFixed(4)}`);
}
{
  let worst = 0, at = [0, 0];
  for (let i = 0; i < 721; i++) for (const r of [1e-3, 0.37, 1, 25, 4e3]) {
    const t = -PI + 2 * PI * i / 720, y = r * Math.sin(t), x = r * Math.cos(t);
    const e = Math.abs(wrapPi(datan2(y, x) - Math.atan2(y, x)));
    if (e > worst) { worst = e; at = [y, x]; }
  }
  check('datan2 all quadrants and radii', worst < TOL, `max err ${worst.toExponential(2)} at (${at[0].toFixed(3)}, ${at[1].toFixed(3)})`);
  check('datan2 axes', datan2(1, 0) === PI / 2 && datan2(-1, 0) === -PI / 2 && datan2(0, 0) === 0 && Math.abs(datan2(0, -1) - PI) < 1e-15, '');
}
{
  let worst = 0;
  for (let i = -2000; i <= 2000; i++) { const a = i * 0.0731; const w = wrapPi(a); if (!(w > -PI - 1e-12 && w <= PI + 1e-12)) worst = 1; worst = Math.max(worst, Math.abs(Math.sin(w) - Math.sin(a)) + Math.abs(Math.cos(w) - Math.cos(a))); }
  check('wrapPi keeps the angle in (-pi, pi]', worst < 1e-9, `max err ${worst.toExponential(2)}`);
}
check('dsin odd, dcos even', dsin(-0.7) === -dsin(0.7) && Math.abs(dcos(-0.7) - dcos(0.7)) < 1e-15, '');
check('dexp(0) = 1, dtanh(0) = 0', dexp(0) === 1 && dtanh(0) === 0, '');
{
  const a = ihash(12345, 678), b = ihash(12345, 678), c = ihash(12346, 678);
  check('ihash is a pure function', a === b && a !== c && Number.isInteger(a) && a >= 0 && a < 2 ** 32, `${a} ${c}`);
  let lo = 1, hi = -1, sum = 0;
  for (let t = 0; t < 30000; t++) { const v = inoise(t, 99, 300); lo = Math.min(lo, v); hi = Math.max(hi, v); sum += v; }
  check('inoise stays in [-1, 1] and is centred', lo >= -1 && hi <= 1 && Math.abs(sum / 30000) < 0.35, `range ${lo.toFixed(3)}..${hi.toFixed(3)} mean ${(sum / 30000).toFixed(3)}`);
}
// determinism rule: no non-portable math in the sim files
{
  const banned = /Math\.(sin|cos|tan|asin|acos|atan|atan2|sinh|cosh|tanh|exp|expm1|log|log1p|log2|log10|pow|cbrt|hypot|random)\b|\*\*|\bDate\b|\bperformance\b/;
  const bad = [];
  for (const f of readdirSync(ROOT + 'engine').filter(f => f.endsWith('.js')).sort()) {
    let text = readFileSync(ROOT + 'engine/' + f, 'utf8');
    if (!text.startsWith('// loom:sim')) continue;
    text = text.replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' '));   // block comments, keeping lines
    text.split('\n').forEach((line, i) => {
      const code = line.replace(/\/\/.*$/, '').replace(/'(?:[^'\\]|\\.)*'/g, "''");
      if (banned.test(code)) bad.push(`${f}:${i + 1}`);
    });
  }
  check('no non-portable math in // loom:sim files', bad.length === 0, bad.join(' '));
}

for (const r of rows) console.log(`${r.ok ? 'ok  ' : 'FAIL'} ${r.name}${r.detail ? '  (' + r.detail + ')' : ''}`);
console.log(JSON.stringify({ fmath: fails === 0 ? 'pass' : 'fail', checks: rows.length, failed: fails }));
process.exit(fails ? 1 : 0);
