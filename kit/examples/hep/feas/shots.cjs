// node shots.cjs OUTDIR "looks/hero_S1_300.x3d|hero_S1_300|ToneMapping=NONE&bloom=8" ...
// Stills at deviceScaleFactor 1, Chromium + SwiftShader (software GL). Prints console errors and GL API counters.
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const ROOT = path.join(__dirname, 'site');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.x3d': 'model/x3d+xml', '.gltf': 'model/gltf+json', '.glb': 'model/gltf-binary', '.png': 'image/png', '.css': 'text/css', '.svg': 'image/svg+xml', '.wasm': 'application/wasm', '.woff2': 'font/woff2' };
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
  const spy = fs.readFileSync(path.join(__dirname, 'glspy.js'), 'utf8');
  for (const sp of specs) {
    const [scene, name, q] = sp.split('|');
    const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
    const page = await ctx.newPage(); await page.addInitScript(spy);
    const errs = [], warns = [], logs = [];
    page.on('console', c => { if (c.type() === 'error') errs.push(c.text().slice(0, 400)); else if (c.type() === 'warning') warns.push(c.text().slice(0, 200)); else logs.push(c.text().slice(0, 300)); });
    page.on('pageerror', e => errs.push('pageerror: ' + String(e.message).slice(0, 400)));
    const t0 = Date.now();
    await page.goto(`${base}shot.html?scene=${scene}${q ? '&' + q : ''}`, { waitUntil: 'domcontentloaded' });
    try { await page.waitForFunction(() => window.__ready, null, { timeout: 300000, polling: 250 }); } catch (e) { errs.push('timeout waiting for __ready'); }
    await page.waitForTimeout(+(process.env.SETTLE || 800));
    const r = await page.evaluate(() => window.__ready);
    await page.screenshot({ path: path.join(outdir, name + '.png') });
    console.log(JSON.stringify({ name, wall_s: +((Date.now() - t0) / 1000).toFixed(1), loadURL_ms: r && r.t_loadURL_ms && Math.round(r.t_loadURL_ms), draws: r && r.gl && r.gl.draw, tris: r && r.gl && Math.round(r.gl.tris), verts: r && r.gl && r.gl.verts, programs: r && r.gl && r.gl.linkProgram, probe: r && r.probe, shader_logs: r && r.gl && r.gl.shader_logs, compiles: r && r.gl && r.gl.compileShader, errors: errs.length, err0: errs[0], warns: warns.length, warn0: warns[0], log0: logs.filter(l => /shader|error|fail|warn/i.test(l)).slice(0, 4), bloom: r && r.bloom_src_found }));
    await ctx.close();
  }
  await browser.close(); server.close();
})().catch(e => { console.error(e); process.exit(2); });
