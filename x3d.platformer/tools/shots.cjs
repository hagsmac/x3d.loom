// Stills from a tape: advance the page's game to each tick, settle the camera, screenshot.
//   node tools/shots.cjs BASE TAPE OUTDIR W H DPR tick:name [tick:name ...]
const { chromium } = require('playwright');
(async () => {
  const [base, tape, outdir, w, h, dpr, ...shots] = process.argv.slice(2);
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  for (const s of shots) {
    const [tick, name, hud] = s.split(':');
    const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: +dpr });
    const errs = [];
    page.on('pageerror', e => errs.push(e.message));
    await page.goto(`${base}index.html?tape=${tape}&frame=${tick}&hud=${hud === 'hud' ? 1 : 0}`);
    await page.waitForFunction(() => window.__ready, null, { timeout: 300000, polling: 300 });
    await page.waitForTimeout(2500);
    const st = await page.evaluate(() => window.__ready);
    await page.screenshot({ path: `${outdir}/${name}.png` });
    console.log(JSON.stringify({ name, tick: +tick, hero: st.hero, cogs: st.cogs, errors: errs }));
    await page.close();
  }
  await browser.close();
})();
