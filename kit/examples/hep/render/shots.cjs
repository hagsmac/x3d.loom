// Stills of the collider scenes in X_ITE (served from site/, fetched by fetch_xite.sh), headless Chromium, software GL.
//   node shots.cjs OUTDIR "scenes/hero.v2.x3d|hero_endon|vp=vp_endon&t=6.5" ...
// One fresh browser context per still, 960x540 at deviceScaleFactor 1 (W, H, SETTLE env override). Prints one JSON line per
// still: CPU load time of loadURL (ms, software GL: a relative cost, never a frame rate), wall time, program and compile
// counts, the first shader compile or link errors, console errors. Needs Playwright (NODE_PATH may point at a global install).
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const ROOT = path.join(__dirname, 'site');
// .css must be text/css: served as octet-stream it made the X_ITE canvas grow without bound and the stills came out blank.
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.x3d': 'model/x3d+xml',
                '.png': 'image/png', '.css': 'text/css', '.svg': 'image/svg+xml', '.wasm': 'application/wasm', '.woff2': 'font/woff2' };
(async () => {
  const [outdir, ...specs] = process.argv.slice(2);
  const W = +(process.env.W || 960), H = +(process.env.H || 540);
  fs.mkdirSync(outdir, { recursive: true });
  const server = http.createServer((req, res) => {
    const p = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream', 'cache-control': 'no-store' });
    fs.createReadStream(p).pipe(res);
  }).listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const spy = fs.readFileSync(path.join(ROOT, 'glspy.js'), 'utf8');
  for (const sp of specs) {
    const [scene, name, q] = sp.split('|');
    const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    const page = await ctx.newPage(); await page.addInitScript(spy);
    const errs = [];
    page.on('console', c => { if (c.type() === 'error') errs.push(c.text().slice(0, 400)); });
    page.on('pageerror', e => errs.push('pageerror: ' + String(e.message).slice(0, 400)));
    const t0 = Date.now();
    await page.goto(`${base}shot.html?scene=${scene}${q ? '&' + q : ''}`, { waitUntil: 'domcontentloaded' });
    try { await page.waitForFunction(() => window.__ready, null, { timeout: 600000, polling: 250 }); } catch (e) { errs.push('timeout waiting for __ready'); }
    await page.waitForTimeout(+(process.env.SETTLE || 1500));
    const r = await page.evaluate(() => window.__ready);
    await page.screenshot({ path: path.join(outdir, name + '.png') });
    console.log(JSON.stringify({ name, scene, query: q || '', wall_s: +((Date.now() - t0) / 1000).toFixed(1), load_cpu_ms: r && r.t_loadURL_ms && Math.round(r.t_loadURL_ms),
      viewpoint: r && r.viewpoint, phase: r && r.phase, phase_targets: r && r.phase_targets && r.phase_targets.length, programs: r && r.gl && r.gl.linkProgram,
      compiles: r && r.gl && r.gl.compileShader, draws: r && r.gl && r.gl.draw, shader_logs: r && r.gl && r.gl.shader_logs, page_errors: (r && r.errors) || [], console_errors: errs.length, err0: errs[0] }));
    await ctx.close();
  }
  await browser.close(); server.close();
})().catch(e => { console.error(e); process.exit(2); });
