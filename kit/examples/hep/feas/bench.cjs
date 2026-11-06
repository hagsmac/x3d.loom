// node bench.cjs [--scenes a,b,c|--all|--cat tracks] [--window 4] [--out results.json] [--w 960 --h 540] [--flags ...]
// Serves feas/site itself on 127.0.0.1. Chromium + SwiftShader (software GL). Times are CPU wall-clock, NOT frame rates.
const http = require('http'), fs = require('fs'), path = require('path'), zlib = require('zlib');
const { chromium } = require('playwright');
const ROOT = path.join(__dirname, 'site');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.x3d': 'model/x3d+xml', '.gltf': 'model/gltf+json', '.glb': 'model/gltf-binary', '.png': 'image/png', '.css': 'text/css' };
const arg = (k, d) => { const i = process.argv.indexOf('--' + k); return i < 0 ? d : (process.argv[i + 1] || true); };
(async () => {
  const server = http.createServer((req, res) => {
    const p = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream', 'cache-control': 'no-store' });
    fs.createReadStream(p).pipe(res);
  }).listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const DIR = arg('dir', 'scenes');
  const man = JSON.parse(fs.readFileSync(path.join(ROOT, 'scenes/manifest.json')));
  let list;
  if (arg('scenes')) list = arg('scenes').split(',').map(n => man.find(m => m.name === n) || { name: n, cat: 'adhoc', bytes: fs.statSync(path.join(ROOT, DIR, n)).size });
  else if (arg('cat')) list = man.filter(m => m.cat === arg('cat') && !m.skip_bench);
  else list = man.filter(m => !m.skip_bench);
  const flags = ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--js-flags=--expose-gc'];
  let browser = await chromium.launch({ args: flags });
  const out = { instrument: { xite: '16.5.1', chromium: browser.version(), renderer: 'SwiftShader software GL (ANGLE)', viewport: `${arg('w', 960)}x${arg('h', 540)} dsf 1`,
    note: 'load/parse/scene-build times are CPU wall-clock; render figures are RELATIVE cost only (software GL), never frame rates' }, rows: [] };
  const spy = fs.readFileSync(path.join(__dirname, 'glspy.js'), 'utf8');
  const outFile = arg('out', path.join(__dirname, 'results_' + (arg('cat', 'all')) + '.json'));
  for (const m of list) {
    if (!browser.isConnected()) browser = await chromium.launch({ args: flags });
    const ctx = await browser.newContext({ viewport: { width: +arg('w', 960), height: +arg('h', 540) }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page.addInitScript(spy);
    const consoleErr = [], consoleWarn = [];
    page.on('console', c => { if (c.type() === 'error') consoleErr.push(c.text().slice(0, 300)); else if (c.type() === 'warning') consoleWarn.push(c.text().slice(0, 300)); });
    page.on('pageerror', e => consoleErr.push('pageerror: ' + String(e.message).slice(0, 300)));
    const cdp = await ctx.newCDPSession(page);
    await cdp.send('Performance.enable');
    const url = `${base}bench.html?scene=${DIR}/${m.name}&window=${arg('window', 4)}` + (arg('count') === '0' ? '&count=0' : '') + (arg('extra') ? '&' + arg('extra') : '');
    const t0 = Date.now();
    let row = { name: m.name, cat: m.cat, file_mb: +(m.bytes / 1e6).toFixed(3), gz_mb: m.gz_bytes ? +(m.gz_bytes / 1e6).toFixed(3) : null, xml_elements: m.xml_elements };
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded' });
      const tmo = +arg('timeout', 240000);
      await Promise.race([page.waitForFunction(() => window.__result, null, { timeout: tmo, polling: 250 }),
        new Promise((_, rej) => setTimeout(() => rej(new Error('watchdog ' + tmo + ' ms: page did not finish')), tmo + 5000))]);
      const r = await Promise.race([page.evaluate(() => window.__result), new Promise((_, rej) => setTimeout(() => rej(new Error('evaluate hung')), 20000))]);
      await Promise.race([cdp.send('HeapProfiler.collectGarbage').catch(() => {}), new Promise(r => setTimeout(r, 15000))]);
      const met = await cdp.send('Performance.getMetrics');
      const heap = met.metrics.find(x => x.name === 'JSHeapUsedSize');
      row = Object.assign(row, r, { js_heap_mb: heap ? +(heap.value / 1e6).toFixed(1) : null });
    } catch (e) { row.timeout_or_fail = String(e.message).split('\n')[0]; try { browser.process().kill('SIGKILL'); } catch (e2) {} }
    row.wall_s = +((Date.now() - t0) / 1000).toFixed(1);
    row.console_errors = consoleErr.length; row.console_error_samples = consoleErr.slice(0, 3);
    row.console_warnings = consoleWarn.length; row.console_warning_samples = consoleWarn.slice(0, 2);
    if (row.node_hist) { const h = row.node_hist; row.node_hist = Object.fromEntries(Object.entries(h).sort((a, b) => b[1] - a[1]).slice(0, 6)); }
    out.rows.push(row);
    console.log(JSON.stringify({ n: row.name, mb: row.file_mb, parse: row.t_parse_build_ms && +row.t_parse_build_ms.toFixed(0), repl: row.t_replace_ms && +row.t_replace_ms.toFixed(0), nodes: row.nodes_distinct, heap: row.js_heap_mb, draws: row.gl && row.gl.draw, err: row.console_errors, fail: row.timeout_or_fail }));
    if (browser.isConnected()) { await Promise.race([ctx.close().catch(() => {}), new Promise(r => setTimeout(r, 10000))]); }
    fs.writeFileSync(outFile, JSON.stringify(out, null, 1));
  }
  try { await browser.close(); } catch (e) {}
  server.close();
  fs.writeFileSync(outFile, JSON.stringify(out, null, 1));
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
