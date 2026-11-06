// Behaviour gate: replay every tape inside the real page (X_ITE + renderer + FX + the engine) in headless
// Chromium, at two very different ticks-per-frame settings (200 and 37), rendering between chunks, and
// require the tape's recorded final hash and state each time, with the level bytes matching the tape.
//   node tools/check_browser.cjs [TAPE.json | DIR ...]     default: tapes/*.tape.json
// Exit 0 pass, 1 a replay disagreed, 2 could not run (no tapes, no playwright, no vendor/x_ite).
// It serves this folder itself on 127.0.0.1 (tapes outside it are served under /__tapes/), so it needs no
// other server. Needs vendor/x_ite (tools/fetch_xite.sh) and Playwright's Chromium (software WebGL is fine).
const http = require('http'), fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
  '.x3d': 'model/x3d+xml', '.css': 'text/css', '.png': 'image/png', '.wasm': 'application/wasm' };
const CHUNKS = (process.env.KANSEI_CHUNKS || '200,37').split(',').map(Number);

function listTapes(args) {
  const out = [];
  const add = p => {
    if (fs.statSync(p).isDirectory()) for (const f of fs.readdirSync(p).sort()) { if (f.endsWith('.tape.json')) out.push(path.join(p, f)); }
    else out.push(p);
  };
  if (args.length) for (const a of args) add(path.resolve(a));
  else if (fs.existsSync(path.join(ROOT, 'tapes'))) add(path.join(ROOT, 'tapes'));
  return out;
}

(async () => {
  let chromium;
  try { ({ chromium } = require('playwright')); } catch { console.log(JSON.stringify({ error: 'playwright missing' })); process.exit(2); }
  if (!fs.existsSync(path.join(ROOT, 'vendor/x_ite/x_ite.min.js'))) { console.log(JSON.stringify({ error: 'vendor/x_ite missing: run tools/fetch_xite.sh' })); process.exit(2); }
  const tapes = listTapes(process.argv.slice(2));
  if (!tapes.length) { console.log(JSON.stringify({ error: 'no tapes to check (tapes/ is empty)', pass: false })); process.exit(2); }
  const extern = new Map();
  tapes.forEach((t, i) => { if (!t.startsWith(ROOT + path.sep)) extern.set(`/__tapes/${i}.tape.json`, t); });
  const server = http.createServer((req, res) => {
    const u = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const p = extern.get(u) || path.join(ROOT, u);
    if ((!extern.has(u) && !p.startsWith(ROOT)) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(res);
  }).listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = { browser: 'chromium ' + browser.version(), chunks: CHUNKS, runs: [], pass: true };
  for (let i = 0; i < tapes.length; i++) {
    const file = tapes[i];
    const tape = JSON.parse(fs.readFileSync(file, 'utf8'));
    const url = extern.has(`/__tapes/${i}.tape.json`) ? `__tapes/${i}.tape.json` : path.relative(ROOT, file).split(path.sep).join('/');
    for (const chunk of CHUNKS) {
      const page = await browser.newPage({ viewport: { width: 480, height: 270 } });
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      const t0 = Date.now();
      await page.goto(`${base}index.html?tape=${encodeURIComponent(url)}&witness=1&chunk=${chunk}&hud=0&quality=low`);
      let w;
      try {
        await page.waitForFunction(() => window.__witness, null, { timeout: 900000, polling: 500 });
        w = await page.evaluate(() => window.__witness);
      } catch (e) { w = { state: 'error', hash: null, error: String(e) }; }
      const ok = w.hash === tape.expect.hash && w.state === tape.expect.state && w.level_sha256_ok === true && errors.length === 0;
      out.pass = out.pass && ok;
      out.runs.push({ tape: path.basename(file), ticks: tape.ticks, ticks_per_frame: chunk, ok, state: w.state, expect_state: tape.expect.state,
        hash: w.hash, expect: tape.expect.hash, level_sha256_ok: w.level_sha256_ok, frames_rendered: w.frames_rendered,
        score: w.score, bestLap: w.bestLap, medal: w.medal, x_ite: w.x_ite, secs: Math.round((Date.now() - t0) / 1000), page_errors: errors.concat(w.page_errors || []) });
      console.error(JSON.stringify(out.runs[out.runs.length - 1]));
      await page.close();
    }
  }
  await browser.close(); server.close();
  console.log(JSON.stringify(out));
  process.exit(out.pass ? 0 : 1);
})().catch(e => { console.log(JSON.stringify({ error: String(e && e.stack || e) })); process.exit(2); });
