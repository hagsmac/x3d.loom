// Frames for a clip from a tape: advance the page's game to `start`, then step `stride` ticks per frame.
//   node tools/clip.cjs BASE TAPE OUTDIR W H DPR START COUNT STRIDE [hud]
// Writes OUTDIR/f_0000.png ...; turn them into a GIF or video with ffmpeg. The picture is the renderer's
// interpolation of the sim, so a clip shows exactly what the tape did.
const { chromium } = require('playwright');
(async () => {
  const [base, tape, outdir, w, h, dpr, start, count, stride, hud] = process.argv.slice(2);
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: +dpr });
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(`${base}index.html?tape=${tape}&frame=${start}&stride=${stride}&hud=${hud === 'hud' ? 1 : 0}`);
  await page.waitForFunction(() => window.__ready, null, { timeout: 300000, polling: 300 });
  await page.waitForTimeout(2500);
  const raf = () => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  for (let i = 0; i < +count; i++) {
    await page.evaluate(() => window.__advance());
    await raf();
    await page.screenshot({ path: `${outdir}/f_${String(i).padStart(4, '0')}.png` });
  }
  console.log(JSON.stringify({ frames: +count, start: +start, stride: +stride, errors: errs }));
  await browser.close();
})();
