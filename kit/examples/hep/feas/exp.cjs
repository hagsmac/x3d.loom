// Targeted experiments in headless X_ITE 16.5.1 (Chromium + SwiftShader). Usage:
//   node exp.cjs freeze | pick [variant ...] | info | lw
// Prints JSON lines. Grades: C for what ran here; software GL only (no frame rates are quoted).
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright');
const ROOT = path.join(__dirname, 'site');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.x3d': 'model/x3d+xml', '.png': 'image/png', '.css': 'text/css', '.svg': 'image/svg+xml', '.wasm': 'application/wasm', '.woff2': 'font/woff2' };
const spy = fs.readFileSync(path.join(__dirname, 'glspy.js'), 'utf8');
const W = 960, H = 540;

async function boot() {
  const server = http.createServer((req, res) => {
    const p = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname));
    if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream', 'cache-control': 'no-store' });
    fs.createReadStream(p).pipe(res);
  }).listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  return { server, base, browser };
}
async function open(env, scene, q = '') {
  const ctx = await env.browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  const page = await ctx.newPage(); await page.addInitScript(spy);
  const log = { errors: [], warnings: [], logs: [] };
  page.on('console', c => { const t = c.text().slice(0, 300); if (c.type() === 'error') log.errors.push(t); else if (c.type() === 'warning') log.warnings.push(t); else log.logs.push(t); });
  page.on('pageerror', e => log.errors.push('pageerror: ' + String(e.message).slice(0, 300)));
  await page.goto(`${env.base}shot.html?scene=${scene}${q ? '&' + q : ''}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.__ready, null, { timeout: 120000, polling: 200 });
  return { ctx, page, log };
}

// ---- law 32 / failure mode 88: an exception inside a field callback
async function freeze(env) {
  const probe = `
    (async () => {
      const B = document.getElementById('c').browser, sc = B.currentScene;
      const nodes = {}; for (const n of ['T','T2','CLK','CLK2','SC']) { try { nodes[n] = sc.getNamedNode(n); } catch (e) {} }
      const pos = () => ({ t: [...nodes.T.translation].map(x => +x.toFixed(3)), t2: [...nodes.T2.translation].map(x => +x.toFixed(3)) });
      const sleep = ms => new Promise(r => setTimeout(r, ms));
      window.__calls = 0; window.__n = 0;
      const mode = MODE;
      if (mode !== 'none') {
        nodes.CLK.addFieldCallback('probe', 'fraction_changed', v => {
          window.__n++;
          const body = () => { if (mode !== 'noop' && window.__n === 13) throw new Error('boom in field callback'); window.__calls++; };
          if (mode === 'guarded') { try { body(); } catch (e) { window.__caught = String(e); } } else body();
        });
      }
      const s0 = pos(); await sleep(900); const s1 = pos(); await sleep(1500); const s2 = pos(); const c2 = window.__calls; await sleep(1500); const s3 = pos(); const c3 = window.__calls;
      const moved = (a, b) => JSON.stringify(a) !== JSON.stringify(b);
      return { mode, n_events_seen_by_callback: window.__n, calls_ok: c3, calls_ok_at_2.4s: c2, T_moved_early: moved(s0.t, s1.t), T_moved_late: moved(s2.t, s3.t), T2_moved_late: moved(s2.t2, s3.t2),
               caught: window.__caught || null, scriptCount: nodes.SC ? 'present' : 'absent' };
    })()`.replace('calls_ok_at_2.4s', 'calls_ok_at_2_4s');
  for (const [scene, mode] of [['scenes/freeze_noscript.x3d', 'noop'], ['scenes/freeze_noscript.x3d', 'throw'], ['scenes/freeze_noscript.x3d', 'guarded'], ['scenes/freeze_fixture.x3d', 'none']]) {
    const { ctx, page, log } = await open(env, scene);
    const r = await page.evaluate(probe.replace('MODE', JSON.stringify(mode)));
    console.log(JSON.stringify({ test: 'freeze', scene, ...r, console_errors: log.errors.slice(0, 3), console_warnings: log.warnings.slice(0, 2) }));
    await ctx.close();
  }
}

// ---- hover / pick on tracks
async function pick(env, variants) {
  for (const v of variants) {
    const scene = `scenes/pick_${v}_40.x3d`;
    const { ctx, page, log } = await open(env, scene);
    const nav = []; page.on('framenavigated', f => nav.push(f.url()));
    await page.evaluate(() => {
      const B = document.getElementById('c').browser, sc = B.currentScene;
      window.__over = new Set(); window.__ev = 0; window.__hp = 0; window.__desc = [];
      for (let i = 0; i < 40; i++) {
        let ts = null; try { ts = sc.getNamedNode('TS' + i); } catch (e) {}
        if (!ts) { try { ts = sc.getNamedNode('AN' + i); } catch (e) {} }
        if (!ts) continue;
        if (ts.getNodeTypeName() === 'TouchSensor') {
          ts.addFieldCallback('p', 'isOver', v => { try { window.__ev++; if (v) { window.__over.add(i); window.__desc.push(B.description); } else window.__over.delete(i); } catch (e) {} });
          ts.addFieldCallback('p', 'hitPoint_changed', v => { try { window.__hp++; } catch (e) {} });
        }
      }
      // projection replica of the page camera
      const vp = sc.getNamedNode('VP'), o = vp.orientation, p = vp.position, fov = vp.fieldOfView;
      const [x, y, z, a] = [o[0], o[1], o[2], o[3]], c = Math.cos(a), s = Math.sin(a), t = 1 - c, n = Math.hypot(x, y, z) || 1, ux = x / n, uy = y / n, uz = z / n;
      const R = [[t*ux*ux+c, t*ux*uy-s*uz, t*ux*uz+s*uy], [t*ux*uy+s*uz, t*uy*uy+c, t*uy*uz-s*ux], [t*ux*uz-s*uy, t*uy*uz+s*ux, t*uz*uz+c]];
      window.__proj = (P) => { const d = [P[0]-p[0], P[1]-p[1], P[2]-p[2]]; const cx = R[0][0]*d[0]+R[1][0]*d[1]+R[2][0]*d[2], cy = R[0][1]*d[0]+R[1][1]*d[1]+R[2][1]*d[2], cz = R[0][2]*d[0]+R[1][2]*d[1]+R[2][2]*d[2];
        const th = Math.tan(fov / 2), asp = 960 / 540; const nx = (cx / -cz) / (th * asp), ny = (cy / -cz) / th; return [(nx * 0.5 + 0.5) * 960, (1 - (ny * 0.5 + 0.5)) * 540, -cz]; };
      window.__pt = (i, k) => { const C = sc.getNamedNode('C' + i); return [...C.point[k]]; };
    });
    let tried = 0, hit_own = 0, hit_any = 0, hit_wrong = 0, offscreen = 0;
    const samples = [];
    for (let i = 0; i < 40; i++) for (const k of [4, 8, 12, 16]) {
      const sp = await page.evaluate(([i, k]) => { try { return window.__proj(window.__pt(i, k)); } catch (e) { return null; } }, [i, k]);
      if (!sp || sp[0] < 3 || sp[0] > 957 || sp[1] < 3 || sp[1] > 537 || sp[2] < 0) { offscreen++; continue; }
      await page.mouse.move(5, 5); await page.waitForTimeout(40);
      await page.mouse.move(sp[0], sp[1], { steps: 2 }); await page.waitForTimeout(110);
      const over = await page.evaluate(() => [...window.__over]);
      tried++; if (over.includes(i)) hit_own++; if (over.length) hit_any++; if (over.length && !over.includes(i)) hit_wrong++;
      if (samples.length < 3 && over.includes(i)) samples.push(i);
    }
    const info = await page.evaluate(() => ({ events: window.__ev, hitpoint_events: window.__hp, descr_sample: window.__desc.slice(0, 2), browser_description: document.getElementById('c').browser.description }));
    let clicked = null;
    if (v === 'anchor') {
      const sp = await page.evaluate(() => window.__proj(window.__pt(3, 10)));
      const before = nav.length; await page.mouse.move(sp[0], sp[1]); await page.waitForTimeout(150); await page.mouse.click(sp[0], sp[1]); await page.waitForTimeout(800);
      clicked = { navigations: nav.length - before, urls: nav.slice(-2) };
    }
    console.log(JSON.stringify({ test: 'pick', variant: v, tried, hit_own, hit_rate: +(hit_own / Math.max(1, tried)).toFixed(3), hit_any, hit_wrong, offscreen, ...info, clicked, console_errors: log.errors.slice(0, 3) }));
    await ctx.close();
  }
}

// ---- picking component (PrimitivePickSensor against track Shapes)
async function picksensor(env, name) {
  const { ctx, page, log } = await open(env, `scenes/${name || 'pick_picksensor_40'}.x3d`, 'frames=20');
  const r = await page.evaluate(async () => {
    const B = document.getElementById('c').browser, sc = B.currentScene; const sleep = ms => new Promise(r => setTimeout(r, ms));
    const out = { found: false };
    try { const pps = sc.getNamedNode('PPS'); out.found = true; out.type = pps.getNodeTypeName(); out.isActive0 = pps.isActive; out.pickedGeometry0 = pps.pickedGeometry ? pps.pickedGeometry.length : null;
      let act = 0, pg = 0; pps.addFieldCallback('p', 'isActive', v => { try { if (v) act++; } catch (e) {} }); pps.addFieldCallback('p', 'pickedGeometry', v => { try { pg = Math.max(pg, v.length); } catch (e) {} });
      const probe = sc.getNamedNode('PROBE'); probe.translation = [0.2, 0.1, 0.1]; await sleep(600); probe.translation = [-0.3, 0.2, 0]; await sleep(600);
      out.isActive_events = act; out.max_pickedGeometry = pg; out.isActive_now = pps.isActive; } catch (e) { out.error = String(e).slice(0, 200); }
    return out;
  });
  console.log(JSON.stringify({ test: 'picksensor', scene: name || 'pick_picksensor_40', ...r, console_errors: log.errors.slice(0, 3), warnings: log.warnings.slice(0, 3) }));
  await ctx.close();
}

// ---- capabilities / environment info
async function info(env) {
  const { ctx, page, log } = await open(env, 'scenes/lw_ladder.x3d');
  const r = await page.evaluate(() => {
    const B = document.getElementById('c').browser;
    const cv = (document.getElementById('c').shadowRoot || document).querySelector('canvas');
    const gl = cv.getContext('webgl2');
    const dbg = gl.getExtension('WEBGL_debug_renderer_info');
    const o = { xite: B.version, renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null, aliased_line_width_range: [...gl.getParameter(gl.ALIASED_LINE_WIDTH_RANGE)],
      max_vertex_attribs: gl.getParameter(gl.MAX_VERTEX_ATTRIBS), max_texture_size: gl.getParameter(gl.MAX_TEXTURE_SIZE), samples: gl.getParameter(gl.SAMPLES),
      ext_color_buffer_float: !!gl.getExtension('EXT_color_buffer_float'), ext_float_blend: !!gl.getExtension('EXT_float_blend'), ext_color_buffer_half_float: !!gl.getExtension('EXT_color_buffer_half_float') };
    o.components = [...B.supportedComponents].map(c => c.name + ':' + c.level);
    const find = (n) => { for (const c of B.concreteNodes) { if (c.typeName === n) return c.componentInfo ? c.componentInfo.name + ' L' + c.componentInfo.level : '?'; } return 'absent'; };
    o.nodes = {}; for (const n of ['BlendMode', 'DepthMode', 'ComposedShader', 'FloatVertexAttribute', 'ParticleSystem', 'PhysicalMaterial', 'EnvironmentLight', 'LineProperties', 'PointProperties', 'LinePickSensor', 'PrimitivePickSensor', 'PointPickSensor', 'VolumePickSensor', 'TouchSensor', 'Anchor', 'Billboard', 'TriangleStripSet', 'IndexedTriangleSet', 'Extrusion', 'GaussianSplat', 'ToneMapping', 'Fog', 'LocalFog', 'ProjectiveTextureMapping', 'InstancedShape', 'TextureProperties']) o.nodes[n] = find(n);
    return o;
  });
  console.log(JSON.stringify({ test: 'info', ...r, console_errors: log.errors.slice(0, 3) }));
  await ctx.close();
}

(async () => {
  const [cmd, ...rest] = process.argv.slice(2);
  const env = await boot();
  try {
    if (cmd === 'freeze') await freeze(env);
    else if (cmd === 'pick') await pick(env, rest.length ? rest : ['thin', 'thick', 'anchor', 'proxy', 'ribbon']);
    else if (cmd === 'picksensor') await picksensor(env, rest[0]);
    else if (cmd === 'info') await info(env);
  } finally { await env.browser.close(); env.server.close(); }
})().catch(e => { console.error(e); process.exit(2); });
