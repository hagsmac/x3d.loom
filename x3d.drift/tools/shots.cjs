// README stills and a short gameplay clip, rendered by the real page in headless Chromium.
//   node tools/shots.cjs [--out DIR] [--tape FILE] [--w 1280 --h 720] [--dw 960 --dh 540] [--only menu,drive,clip,phone]
//                        [--ticks 900,2400,4200] [--live 3] [--clip-start 1500 --clip-frames 12 --clip-stride 12]
//                        [--cw 640 --ch 360] [--scale 1] [--jpeg 90] [--quality medium]
//                        [--views name@tick@cam[@photo|@clean][,...]] [--menus title,mode,car,track,setup,career]
// --w/--h size the menu stills, --dw/--dh the gameplay stills (software WebGL draws a frame in tens of seconds, so
// gameplay stills default smaller to keep every browser session short). --live draws the last N frames before a
// gameplay still one by one, so tyre smoke has some history.
// Menus come from clicking through the page; gameplay stills and the clip replay a tape (default: the
// first tapes/*.tape.json) with ?tape=..&frame=..; the clip is PNG frames plus clip.gif (built with
// python3 + PIL when available). Output: --out, else $KANSEI_SHOTS, else <os tmpdir>/kansei-shots;
// never inside the repository. Prints one JSON line per image.
// --scale is the device pixel ratio (2 with 1280x720 gives 2560x1440 images); --jpeg Q writes JPEG instead of PNG;
// --quality is the page's quality level for tape stills, --cscale pins the 3D canvas resolution factor (1 with --scale 2
// draws the 3D at half the image size and the HUD at full size, which software WebGL can afford); --views renders named stills from the tape (only with
// --only views): cam is any camera (chase close bumper hood orbit director replay), '@photo' opens photo mode,
// '@clean' hides the HUD.
const http = require('http'), fs = require('fs'), path = require('path'), os = require('os'), { spawnSync } = require('child_process');
const ROOT = path.resolve(__dirname, '..');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
  '.x3d': 'model/x3d+xml', '.css': 'text/css', '.png': 'image/png', '.wasm': 'application/wasm' };

function args() {
  const a = process.argv.slice(2), o = { out: process.env.KANSEI_SHOTS || path.join(os.tmpdir(), 'kansei-shots'), w: 1280, h: 720, dw: 960, dh: 540,
    only: 'menu,drive,clip,phone', menus: '', ticks: null, live: 3, clipStart: null, clipFrames: 12, clipStride: 12, cw: 640, ch: 360,
    scale: 1, jpeg: 0, quality: '', views: [], cscale: 0 };
  for (let i = 0; i < a.length; i++) {
    const k = a[i], v = a[i + 1];
    if (k === '--out') o.out = v, i++; else if (k === '--tape') o.tape = v, i++; else if (k === '--w') o.w = +v, i++; else if (k === '--h') o.h = +v, i++;
    else if (k === '--cw') o.cw = +v, i++; else if (k === '--ch') o.ch = +v, i++;
    else if (k === '--dw') o.dw = +v, i++; else if (k === '--dh') o.dh = +v, i++; else if (k === '--live') o.live = +v, i++;
    else if (k === '--only') o.only = v, i++; else if (k === '--ticks') o.ticks = v.split(',').map(Number), i++;
    else if (k === '--scale') o.scale = +v, i++; else if (k === '--jpeg') o.jpeg = +v, i++; else if (k === '--quality') o.quality = v, i++; else if (k === '--cscale') o.cscale = +v, i++;
    else if (k === '--menus') o.menus = v, i++;
    else if (k === '--views') o.views = v.split(',').filter(Boolean), i++;
    else if (k === '--clip-start') o.clipStart = +v, i++; else if (k === '--clip-frames') o.clipFrames = +v, i++; else if (k === '--clip-stride') o.clipStride = +v, i++;
  }
  return o;
}

(async () => {
  const o = args();
  let chromium;
  try { ({ chromium } = require('playwright')); } catch { console.log(JSON.stringify({ error: 'playwright missing' })); process.exit(2); }
  const out = path.resolve(o.out);
  if (out === ROOT || out.startsWith(ROOT + path.sep)) { console.log(JSON.stringify({ error: 'refusing to write inside the repository' })); process.exit(2); }
  fs.mkdirSync(out, { recursive: true });
  let tapeFile = o.tape ? path.resolve(o.tape) : null;
  if (!tapeFile && fs.existsSync(path.join(ROOT, 'tapes'))) { const t = fs.readdirSync(path.join(ROOT, 'tapes')).filter(f => f.endsWith('.tape.json')).sort()[0]; if (t) tapeFile = path.join(ROOT, 'tapes', t); }
  const tape = tapeFile ? JSON.parse(fs.readFileSync(tapeFile, 'utf8')) : null;
  const server = http.createServer((req, res) => {
    const u = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    const p = u === '/__tape.json' && tapeFile ? tapeFile : path.join(ROOT, u);
    if ((p !== tapeFile && !p.startsWith(ROOT)) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(res);
  }).listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const only = new Set(o.only.split(','));
  const settle = page => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  const open = async (url, view = { width: o.w, height: o.h }, mobile = false) => {
    const ctx = await browser.newContext({ viewport: view, deviceScaleFactor: mobile ? 1 : o.scale, isMobile: mobile, hasTouch: mobile });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + url);
    return { page, ctx, errors };
  };
  const snap = async (page, name, errors, extra = {}) => {
    await settle(page);
    const file = path.join(out, name + (o.jpeg ? '.jpg' : '.png'));
    // stop the X3D render loop while the page is captured, so the capture waits for one compositor frame only
    await page.evaluate(() => { const b = document.querySelector('x3d-canvas').browser; if (b.endUpdate) b.endUpdate(); });
    await page.screenshot({ path: file, timeout: 240000, ...(o.jpeg ? { type: 'jpeg', quality: o.jpeg } : {}) });
    await page.evaluate(() => { const b = document.querySelector('x3d-canvas').browser; if (b.beginUpdate) b.beginUpdate(); });
    console.log(JSON.stringify({ file, ...extra, errors: errors.splice(0) }));
  };

  if (only.has('menu')) {
    // three short page sessions, two stills each (software WebGL is slow; each session stays under three minutes)
    const groups = [[['title', 'menu-title'], ['mode', 'menu-mode']], [['car', 'menu-car'], ['track', 'menu-track']], [['setup', 'menu-setup'], ['career', 'menu-career']]];
    const want = o.menus ? new Set(o.menus.split(',')) : null;   // --menus title,car keeps only those screens
    for (const g0 of groups) {
      const g = want ? g0.filter(([sc]) => want.has(sc)) : g0;
      if (!g.length) continue;
      const { page, ctx, errors } = await open('index.html?noanim=1' + (o.cscale ? `&cscale=${o.cscale}` : ''));
      await page.waitForFunction(() => window.KANSEI && window.KANSEI.state().screen === 'title', null, { timeout: 150000 });
      await page.waitForTimeout(2000);
      for (const [screen, name] of g) {
        // instant: the garage camera jumps to its pose (software WebGL frames are slow, the eased move would take minutes)
        await page.evaluate(s => window.KANSEI.go(s, { instant: true }), screen);
        await page.waitForTimeout(screen === 'track' ? 4000 : 1500);
        await snap(page, name, errors);
      }
      await ctx.close();
    }
  }
  if (only.has('drive') && tape) {
    const L = tape.ticks;
    const ticks = o.ticks || [Math.round(L * 0.18), Math.round(L * 0.42), Math.round(L * 0.7)];
    const cams = ['chase', 'director', 'close'];
    for (let i = 0; i < ticks.length; i++) {
      const { page, ctx, errors } = await open(`index.html?tape=__tape.json&frame=${ticks[i]}&hud=1&cam=${cams[i % cams.length]}&noanim=1&live=${o.live}`, { width: o.dw, height: o.dh });
      await page.waitForFunction(() => window.__ready, null, { timeout: 170000, polling: 300 });
      await page.waitForTimeout(1500);
      const st = await page.evaluate(() => window.KANSEI.state());
      await snap(page, `drive-${i + 1}-${cams[i % cams.length]}`, errors, { tick: ticks[i], camera: st.camera, kmh: st.kmh, chain: st.chain, score: st.score });
      await ctx.close();
    }
  }
  if (only.has('views') && tape) {
    for (const v of o.views) {
      const [name, tick, cam = 'chase', ...flags] = v.split('@');
      const clean = flags.includes('clean') || flags.includes('photo');
      const q = (o.quality ? `&quality=${o.quality}` : '') + (o.cscale ? `&cscale=${o.cscale}` : '');
      const { page, ctx, errors } = await open(`index.html?tape=__tape.json&frame=${+tick}&hud=${clean ? 0 : 1}&cam=${cam}&noanim=1&live=${o.live}${q}`, { width: o.dw, height: o.dh });
      await page.waitForFunction(() => window.__ready, null, { timeout: 600000, polling: 500 });
      if (flags.includes('photo')) await page.evaluate(() => { window.KANSEI.photo(true); window.__advance(1); });
      await page.waitForTimeout(1500);
      const st = await page.evaluate(() => window.KANSEI.state());
      await snap(page, name, errors, { tick: +tick, camera: st.camera, kmh: st.kmh, slip: st.slipDeg, chain: st.chain, x: st.multiplier, score: st.score, position: st.position });
      await ctx.close();
    }
  }
  if (only.has('clip') && tape) {
    const start = o.clipStart ?? Math.round(tape.ticks * 0.3);
    const { page, ctx, errors } = await open(`index.html?tape=__tape.json&frame=${start}&stride=${o.clipStride}&hud=1&cam=chase&live=0${o.quality ? `&quality=${o.quality}` : ''}${o.cscale ? `&cscale=${o.cscale}` : ''}`, { width: o.cw, height: o.ch });
    await page.waitForFunction(() => window.__ready, null, { timeout: 170000, polling: 300 });
    await page.waitForTimeout(1000);
    const dir = path.join(out, 'clip'); fs.mkdirSync(dir, { recursive: true });
    for (let i = 0; i < o.clipFrames; i++) {
      await page.evaluate(() => window.__advance());
      await settle(page);
      await page.screenshot({ path: path.join(dir, `f_${String(i).padStart(4, '0')}.png`), timeout: 120000 });
      if (i % 6 === 5) process.stderr.write(`clip frame ${i + 1}/${o.clipFrames}\n`);
    }
    console.log(JSON.stringify({ clip: dir, frames: o.clipFrames, start, stride: o.clipStride, errors: errors.splice(0) }));
    await ctx.close();
    const py = spawnSync('python3', ['-I', '-c', `
import sys, glob
from PIL import Image
fs = sorted(glob.glob(sys.argv[1] + '/f_*.png'))
ims = [Image.open(f).convert('RGB').resize((640, 360), Image.LANCZOS) for f in fs]  # GIF stays small
pal = [im.quantize(colors=200, method=Image.MEDIANCUT) for im in ims]
pal[0].save(sys.argv[2], save_all=True, append_images=pal[1:], duration=${Math.round(1000 * o.clipStride / 120)}, loop=0, optimize=True)
print(len(fs))`, dir, path.join(out, 'clip.gif')], { encoding: 'utf8' });
    console.log(JSON.stringify({ gif: path.join(out, 'clip.gif'), ok: py.status === 0, note: (py.stderr || '').slice(0, 200) }));
  }
  if (only.has('phone')) {
    const { page, ctx, errors } = await open('index.html?touch=1', { width: 390, height: 844 }, true);
    await page.waitForFunction(() => window.KANSEI && window.KANSEI.state().screen === 'title', null, { timeout: 150000 });
    await page.waitForTimeout(2500);
    await snap(page, 'phone-title', errors);
    await page.click('#go-play'); await page.waitForTimeout(800); await page.click('[data-mode=rush]'); await page.waitForTimeout(2000);
    await snap(page, 'phone-car', errors);
    await ctx.close();
    if (tape) {
      const r = await open(`index.html?tape=__tape.json&frame=${Math.round(tape.ticks * 0.4)}&hud=1&touch=1&live=0`, { width: 390, height: 844 }, true);
      await r.page.waitForFunction(() => window.__ready, null, { timeout: 170000, polling: 300 });
      await r.page.waitForTimeout(1200);
      await snap(r.page, 'phone-drive', r.errors);
      await r.ctx.close();
    }
  }
  await browser.close(); server.close();
})().catch(e => { console.log(JSON.stringify({ error: String(e && e.stack || e) })); process.exit(2); });
