// Behaviour gate: replay every tape inside the real page (X_ITE + renderer + engine) in headless Chromium,
// at two very different ticks-per-frame settings, and require the tape's recorded finish each time.
//   node tools/check_browser.cjs            exit 0 pass, 1 a replay disagreed, 2 could not run
// It serves this folder itself on 127.0.0.1, so it needs no other server. Needs vendor/x_ite (tools/fetch_xite.sh).
const http = require('http'), fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
  '.x3d': 'model/x3d+xml', '.css': 'text/css', '.xml': 'application/xml', '.png': 'image/png' };
const CHUNKS = [200, 37];
(async () => {
  let chromium;
  try { ({ chromium } = require('playwright')); } catch (e) { console.log(JSON.stringify({ error: 'playwright missing' })); process.exit(2); }
  if (!fs.existsSync(path.join(ROOT, 'vendor/x_ite/x_ite.min.js'))) { console.log(JSON.stringify({ error: 'vendor/x_ite missing: run tools/fetch_xite.sh' })); process.exit(2); }
  const server = http.createServer((req, res) => {
    const p = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(res);
  }).listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const out = { browser: 'chromium ' + browser.version(), runs: [], pass: true };
  const tapes = fs.readdirSync(path.join(ROOT, 'tapes')).filter(f => f.endsWith('.tape.json')).sort();
  for (const t of tapes) {
    const tape = JSON.parse(fs.readFileSync(path.join(ROOT, 'tapes', t), 'utf8'));
    for (const chunk of CHUNKS) {
      const page = await browser.newPage({ viewport: { width: 960, height: 540 } });
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(`${base}index.html?tape=tapes/${t}&witness=1&chunk=${chunk}&hud=0`);
      await page.waitForFunction(() => window.__witness, null, { timeout: 600000, polling: 500 });
      const w = await page.evaluate(() => window.__witness);
      const ok = w.state === 'won' && w.hash === tape.expect.hash && w.level_sha256_ok === true && errors.length === 0;
      out.pass = out.pass && ok;
      out.runs.push({ tape: t, ticks_per_frame: chunk, ok, state: w.state, hash: w.hash, expect: tape.expect.hash,
        level_sha256_ok: w.level_sha256_ok, cogs: w.cogs, stars: w.stars, deaths: w.deaths, frames_rendered: w.frames_rendered,
        x_ite: w.x_ite, page_errors: errors });
      await page.close();
    }
  }
  await browser.close(); server.close();
  console.log(JSON.stringify(out));
  process.exit(out.pass ? 0 : 1);
})().catch(e => { console.log(JSON.stringify({ error: String(e) })); process.exit(2); });
