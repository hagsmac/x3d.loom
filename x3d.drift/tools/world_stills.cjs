// World stills: render views of a KANSEI X3D file (circuit, car or garage) with X_ITE in headless
// Chromium and write PNGs outside the repository.
//
//   node tools/world_stills.cjs FILE.x3d [options] VIEW [VIEW ...]
//
// VIEW is one of
//   TrackCam3                      bind a trackside Viewpoint by DEF (any Viewpoint DEF works, e.g. GarageCam0)
//   chase:S[:H[:B[:LAT]]]          ChaseCam behind centre sample S, H m above the road (default 1.6), B m back (6.5), LAT m left
//   low:S                          a bumper-height chase (H 0.7, B 4)
//   orbit:S:D:H:DEG                orbit sample S at distance D, height H, angle DEG from the forward direction
//   top                            the whole circuit from high above
//   turn:DEG[:CAM]                 garage: rotate DEF Turntable to DEG and bind CAM (default GarageCam0)
// Options
//   --out DIR        output folder (default: $KANSEI_STILLS, else <os tmpdir>/kansei-stills; never the repo)
//   --name PREFIX    file name prefix (default: the X3D file's base name)
//   --w W --h H      viewport (default 960 x 540)
//   --car FILE.x3d   put a car on the road (circuits: at the chase sample, or --at S; garage: into CarSlot)
//   --at S           sample for --car
//   --tone NAME      X_ITE ToneMapping (default ACES_NARKOWICZ), --exposure X (default 1)
//   --wait MS        extra settle time after load (default 4000)
//   --shadows 0|1    turn the Sun's shadows off or on (default: as in the file)
// Prints one JSON line per still. Exit 0 ok, 2 could not run.
const http = require('http'), fs = require('fs'), path = require('path'), os = require('os');
const ROOT = path.resolve(__dirname, '..');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
  '.x3d': 'model/x3d+xml', '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg', '.wasm': 'application/wasm' };
const DEFAULT_OUT = process.env.KANSEI_STILLS || path.join(os.tmpdir(), 'kansei-stills');

function args() {
  const a = process.argv.slice(2), o = { views: [], w: 960, h: 540, tone: 'ACES_NARKOWICZ', exposure: 1, wait: 4000, out: DEFAULT_OUT };
  for (let i = 0; i < a.length; i++) {
    const k = a[i];
    if (k === '--out') o.out = a[++i]; else if (k === '--name') o.name = a[++i];
    else if (k === '--w') o.w = +a[++i]; else if (k === '--h') o.h = +a[++i];
    else if (k === '--car') o.car = a[++i]; else if (k === '--at') o.at = +a[++i];
    else if (k === '--tone') o.tone = a[++i]; else if (k === '--exposure') o.exposure = +a[++i];
    else if (k === '--wait') o.wait = +a[++i]; else if (k === '--shadows') o.shadows = a[++i];
    else if (!o.file) o.file = k; else o.views.push(k);
  }
  return o;
}

const PAGE = (o) => `<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;height:100%;background:#000;overflow:hidden}x3d-canvas{width:100%;height:100%;display:block}</style>
<script src="/vendor/x_ite/x_ite.min.js"></script></head><body>
<x3d-canvas id="c" splashScreen="false" contextMenu="false" notifications="false" timings="false" antialiased="true"
 toneMapping="${o.tone}" exposure="${o.exposure}" logarithmicDepthBuffer="true"></x3d-canvas>
<script>
const frames = n => new Promise(r => { let k = 0; const f = () => (++k >= n ? r() : requestAnimationFrame(f)); requestAnimationFrame(f); });
function quat(yaw, pitch) {           // yaw about +Y, then pitch about local +X
  const cy = Math.cos(yaw / 2), sy = Math.sin(yaw / 2), cp = Math.cos(pitch / 2), sp = Math.sin(pitch / 2);
  const w = cy * cp, x = cy * sp, y = sy * cp, z = -sy * sp;
  const n = Math.hypot(x, y, z); if (n < 1e-9) return [0, 1, 0, 0];
  return [x / n, y / n, z / n, 2 * Math.atan2(n, w)];
}
function lookAt(eye, tgt) {
  const d = [tgt[0] - eye[0], tgt[1] - eye[1], tgt[2] - eye[2]], l = Math.hypot(...d);
  return quat(Math.atan2(-d[0], -d[2]), Math.asin(d[1] / l));
}
window.__api = {
  async load(url, carUrl, at, shadows) {
    const X3D = window.X3D, canvas = document.getElementById('c'), browser = canvas.browser;
    const text = await (await fetch(url)).text();
    const m = /name='center' value='([^']*)'/.exec(text);
    const c = m ? m[1].trim().split(/\\s+/).map(Number) : null;
    this.c = c; this.n = c ? c.length / 8 : 0; this.browser = browser; this.X3D = X3D;
    await browser.loadURL(new X3D.MFString(url));
    const scene = browser.currentScene;
    this.scene = scene;
    const N = k => { try { return scene.getNamedNode(k); } catch { return null; } };
    this.N = N;
    if (shadows !== undefined && N('Sun')) N('Sun').shadows = shadows === '1';
    if (carUrl) {
      const slot = N('CarSlot') || N('Cars');
      const t = scene.createNode('Transform'), inl = scene.createNode('Inline');
      inl.url = new X3D.MFString(carUrl); t.children.push(inl);
      if (!N('CarSlot') && c) {
        const i = ((at | 0) % this.n + this.n) % this.n, j = (i + 1) % this.n, k = (i - 1 + this.n) % this.n;
        const tx = c[8 * j] - c[8 * k], tz = c[8 * j + 2] - c[8 * k + 2];
        t.translation = new X3D.SFVec3f(c[8 * i], c[8 * i + 1], c[8 * i + 2]);
        t.rotation = new X3D.SFRotation(0, 1, 0, Math.atan2(tx, tz));
      }
      slot.children.push(t);
      this.car = t;
    }
    return { n: this.n, hasCars: !!N('Cars'), hasSlot: !!N('CarSlot'), title: (N('TrackInfo') || {}).title || '' };
  },
  frame(i) {
    const c = this.c, n = this.n; i = ((i | 0) % n + n) % n;
    const j = (i + 1) % n, k = (i - 1 + n) % n;
    let tx = c[8 * j] - c[8 * k], tz = c[8 * j + 2] - c[8 * k + 2]; const l = Math.hypot(tx, tz); tx /= l; tz /= l;
    return { p: [c[8 * i], c[8 * i + 1], c[8 * i + 2]], t: [tx, tz], left: [tz, -tx], hw: c[8 * i + 4] };
  },
  async view(spec) {
    const X3D = this.X3D, N = this.N, parts = spec.split(':');
    if (this.browser.beginUpdate) this.browser.beginUpdate();
    let vp = null, eye, tgt;
    if (parts[0] === 'chase' || parts[0] === 'low') {
      const s = +parts[1], low = parts[0] === 'low';
      const H = parts[2] !== undefined ? +parts[2] : (low ? 0.7 : 1.6), B = parts[3] !== undefined ? +parts[3] : (low ? 4.0 : 6.5);
      const lat = parts[4] !== undefined ? +parts[4] : 0;
      const f = this.frame(s), ahead = this.frame(s + Math.round(14 / 2));
      eye = [f.p[0] - f.t[0] * B + f.left[0] * lat, f.p[1] + H, f.p[2] - f.t[1] * B + f.left[1] * lat];
      tgt = [ahead.p[0], ahead.p[1] + (low ? 0.5 : 0.6), ahead.p[2]];
      vp = N('ChaseCam');
    } else if (parts[0] === 'orbit') {
      const f = this.frame(+parts[1]), D = +parts[2], H = +parts[3], a = (+parts[4]) * Math.PI / 180;
      const dx = f.t[0] * Math.cos(a) + f.left[0] * Math.sin(a), dz = f.t[1] * Math.cos(a) + f.left[1] * Math.sin(a);
      eye = [f.p[0] + dx * D, f.p[1] + H, f.p[2] + dz * D]; tgt = [f.p[0], f.p[1] + 0.6, f.p[2]];
      vp = N('ChaseCam');
    } else if (parts[0] === 'top') {
      const c = this.c; let x0 = 1e9, x1 = -1e9, z0 = 1e9, z1 = -1e9, y = 0;
      for (let i = 0; i < this.n; i++) { x0 = Math.min(x0, c[8*i]); x1 = Math.max(x1, c[8*i]); z0 = Math.min(z0, c[8*i+2]); z1 = Math.max(z1, c[8*i+2]); y += c[8*i+1] / this.n; }
      const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2, R = Math.max(x1 - x0, z1 - z0);
      eye = [cx, y + R * 0.75, cz - R * 0.75]; tgt = [cx, y, cz];
      vp = N('ChaseCam');
    } else if (parts[0] === 'turn') {
      const tt = N('Turntable'); if (tt) tt.rotation = new X3D.SFRotation(0, 1, 0, (+parts[1]) * Math.PI / 180);
      vp = N(parts[2] || 'GarageCam0');
    } else {
      vp = N(parts[0]);
    }
    if (!vp) return { error: 'no viewpoint for ' + spec };
    if (eye) {
      const r = lookAt(eye, tgt);
      vp.position = new X3D.SFVec3f(...eye); vp.orientation = new X3D.SFRotation(...r);
    }
    vp.set_bind = true;
    await frames(4);
    await new Promise(r => setTimeout(r, 300));
    await frames(2);
    const act = this.browser.getActiveViewpoint ? this.browser.getActiveViewpoint() : null;
    // pause the event loop so looping clocks (sea swell, signs) do not keep redrawing during capture
    if (this.browser.endUpdate) this.browser.endUpdate();
    return { ok: true, eye, active: act && act._description ? act._description.getValue() : null };
  }
};
window.__ready = true;
</script></body></html>`;

(async () => {
  const o = args();
  if (!o.file || !o.views.length) { console.log(JSON.stringify({ error: 'usage: node tools/world_stills.cjs FILE.x3d [options] VIEW ...' })); process.exit(2); }
  let chromium;
  try { ({ chromium } = require('playwright')); } catch { console.log(JSON.stringify({ error: 'playwright missing' })); process.exit(2); }
  if (!fs.existsSync(path.join(ROOT, 'vendor/x_ite/x_ite.min.js'))) { console.log(JSON.stringify({ error: 'vendor/x_ite missing' })); process.exit(2); }
  const outDir = path.resolve(o.out);
  if (outDir.startsWith(ROOT + path.sep) || outDir === ROOT) { console.log(JSON.stringify({ error: 'refusing to write stills inside the repository' })); process.exit(2); }
  fs.mkdirSync(outDir, { recursive: true });
  const server = http.createServer((req, res) => {
    const u = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (u === '/__stills.html') { res.writeHead(200, { 'content-type': 'text/html' }); return res.end(PAGE(o)); }
    const p = path.join(ROOT, u);
    if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(res);
  }).listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: o.w, height: o.h } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/ERR_ABORTED|tangent/i.test(m.text())) errors.push(m.text().slice(0, 300)); });
  const t0 = Date.now();
  await page.goto(base + '__stills.html');
  await page.waitForFunction(() => window.__ready && window.X3D && document.getElementById('c').browser, null, { timeout: 60000 });
  const rel = path.relative(ROOT, path.resolve(o.file)).split(path.sep).join('/');
  const carRel = o.car ? path.relative(ROOT, path.resolve(o.car)).split(path.sep).join('/') : null;
  let at = o.at;
  if (at === undefined) { const v = o.views.find(v => /^(chase|low|orbit):/.test(v)); at = v ? +v.split(':')[1] : 0; }
  const info = await page.evaluate(([u, cu, a, sh]) => window.__api.load(u, cu, a, sh), [base + rel, carRel ? base + carRel : null, at, o.shadows]);
  await page.waitForTimeout(o.wait);
  const name = o.name || path.basename(o.file, '.x3d');
  for (const v of o.views) {
    const t1 = Date.now();
    const r = await page.evaluate(s => window.__api.view(s), v);
    const file = path.join(outDir, `${name}__${v.replace(/[^A-Za-z0-9.-]+/g, '_')}.png`);
    await page.screenshot({ path: file });
    console.log(JSON.stringify({ file, view: v, ms: Date.now() - t1, ...r, info, errors: errors.splice(0) }));
  }
  await browser.close(); server.close();
  console.log(JSON.stringify({ done: true, total_ms: Date.now() - t0 }));
})().catch(e => { console.log(JSON.stringify({ error: String(e && e.stack || e) })); process.exit(2); });
