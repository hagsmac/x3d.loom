// Browser witness: play a tape inside the real page (X_ITE + renderer + the same engine modules)
// in headless Chromium, at a chosen number of ticks per rendered frame, and print the outcome.
//   node tools/browser_witness.cjs http://127.0.0.1:8765/ tapes/1-1-tinker-meadow.tape.json 200 37
// Each extra number is another ticks-per-frame setting; the hash must not depend on it.
const { chromium } = require('playwright');
(async () => {
  const [base, tape, ...chunks] = process.argv.slice(2);
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--autoplay-policy=no-user-gesture-required'] });
  const out = { browser: 'chromium ' + browser.version(), runs: [] };
  for (const chunk of (chunks.length ? chunks : ['200'])) {
    const page = await browser.newPage({ viewport: { width: 960, height: 540 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    const t0 = Date.now();
    await page.goto(`${base}index.html?tape=${tape}&witness=1&chunk=${chunk}&hud=0`);
    await page.waitForFunction(() => window.__witness, null, { timeout: 600000, polling: 500 });
    const w = await page.evaluate(() => window.__witness);
    out.runs.push({ ticks_per_frame: +chunk, ...w, page_errors: errors, total_ms: Date.now() - t0 });
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(out));
})();
