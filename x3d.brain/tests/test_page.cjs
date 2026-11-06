// test_page.cjs: browser check of the built brain page (headless Chromium via Playwright; needs `playwright` resolvable, e.g. NODE_PATH).
//   node tests/test_page.cjs --page DIR --out DIR [--phases desktop,phone,torso,tour,audio] [--width 1280 --height 800] [--budget 240] [--quality fast|balanced|sharp]
// Serves DIR on 127.0.0.1, opens it, drives every control and writes screenshots + report.json into --out.
// Passes only with zero console errors, zero failed requests and zero page errors. The rig is software GL (SwiftShader): frame rates mean nothing, waits are frame-based.
"use strict";
const fs = require("fs"), path = require("path"), http = require("http");
let chromium;
try { ({ chromium } = require("playwright")); } catch (e) {
  console.error("test_page.cjs needs the `playwright` package: install it, or point NODE_PATH at a node_modules folder that has it (NODE_PATH=/path/to/node_modules node tests/test_page.cjs ...)");
  process.exit(2);
}

const args = {};
for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i].replace(/^--/, "")] = process.argv[i + 1];
const PAGE_DIR = path.resolve(args.page || "page"), OUT = path.resolve(args.out || "page-test-out");
const PHASES = (args.phases || "desktop,tour,audio,torso,phone").split(",");
const W = +(args.width || 1280), H = +(args.height || 800), BUDGET = +(args.budget || 240) * 1000;
fs.mkdirSync(OUT, { recursive: true });

const MIME = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg", ".x3d": "model/x3d+xml",
  ".x3dz": "model/x3d+xml", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".md": "text/markdown", ".wasm": "application/wasm", ".woff2": "font/woff2", ".ttf": "font/ttf", ".svg": "image/svg+xml" };
function serve(root) {
  return http.createServer((req, res) => {
    let u = decodeURIComponent(req.url.split("?")[0]); if (u.endsWith("/")) u += "index.html";
    const f = path.resolve(root, "." + u);
    if (!f.startsWith(root + path.sep) || !fs.existsSync(f) || !fs.statSync(f).isFile()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "content-type": MIME[path.extname(f)] || "application/octet-stream", "cache-control": "no-cache" });
    fs.createReadStream(f).pipe(res);
  });
}

const report = { rig: null, page: PAGE_DIR, viewport: [W, H], checks: [], console: [], timings: {}, screenshots: [] };
function check(name, ok, detail) { report.checks.push({ name, ok: !!ok, detail: detail === undefined ? null : detail }); console.log((ok ? "PASS " : "FAIL ") + name + (detail !== undefined ? "  " + JSON.stringify(detail).slice(0, 220) : "")); return !!ok; }
const IGNORE = /GPU stall|ReadPixels|GL Driver Message/;

async function newSession(browser, opts, tag) {
  const ctx = await browser.newContext(opts);
  const page = await ctx.newPage();
  page.on("console", m => { const t = m.text(); if (!IGNORE.test(t) && (m.type() === "error" || m.type() === "warning")) report.console.push(`[${tag} ${m.type()}] ${t.slice(0, 300)}`); });
  page.on("pageerror", e => report.console.push(`[${tag} pageerror] ${String(e).slice(0, 300)}`));
  page.on("requestfailed", r => report.console.push(`[${tag} requestfailed] ${r.url()}`));
  page.on("response", r => { if (r.status() >= 400) report.console.push(`[${tag} http ${r.status()}] ${r.url()}`); });
  return { ctx, page };
}
async function frames(page, n) { await page.evaluate(n => window.__loom.frames(n), n); }
async function state(page) { return page.evaluate(() => window.__loom.state); }
async function shot(page, name) { const p = path.join(OUT, name + ".png"); await page.screenshot({ path: p }); report.screenshots.push(p); return p; }
async function waitReady(page, ms) { await page.waitForSelector('#app[data-state="ready"]', { timeout: ms || BUDGET }); }

async function brainPhase(browser, base, tag, opts, doInteractions) {
  const { ctx, page } = await newSession(browser, opts, tag);
  const t0 = Date.now();
  await page.goto(base + "/index.html");
  await waitReady(page);
  report.timings[tag + "_ready_s"] = (Date.now() - t0) / 1000;
  const st = await state(page);
  check(`${tag}: scene ready`, st.ready && st.kind === "brain", st);
  check(`${tag}: pointer sensors installed`, st.sensors >= 8, st.sensors);
  // (on a phone the Detail chips live in the Layers sheet, so the click is for the desktop only)
  if (args.quality && !opts.isMobile) { await page.locator(`[data-q="${args.quality}"]`).click(); check(`${tag}: detail chip ${args.quality}`, (await page.locator(`[data-q="${args.quality}"]`).getAttribute("aria-pressed")) === "true"); }
  await frames(page, 2);
  const noHoriz = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth, bw: document.body.scrollWidth }));
  check(`${tag}: no horizontal overflow`, noHoriz.sw <= noHoriz.iw && noHoriz.bw <= noHoriz.iw, noHoriz);
  await shot(page, `${tag}-01-home`);
  if (!doInteractions) return { ctx, page };

  // layers: each switch flips the Switch node it is bound to
  const layerKeys = ["glass", "wet", "deep", "tracts", "slices", "labels", "activation"];
  for (const k of layerKeys) {
    const sel = `#ly-${k}`;
    const before = await page.evaluate(k => { const cb = document.querySelector("#ly-" + k); return { on: cb.checked, def: cb.dataset.def, wc: window.__loom.node(cb.dataset.def).whichChoice }; }, k);
    await page.locator(sel).evaluate(cb => cb.click());
    const after = await page.evaluate(k => { const cb = document.querySelector("#ly-" + k); return { on: cb.checked, wc: window.__loom.node(cb.dataset.def).whichChoice }; }, k);
    check(`${tag}: layer ${k} toggles ${before.def}`, after.on !== before.on && (after.wc === 0) === after.on && before.on === (before.wc === 0), { before, after });
    await page.locator(sel).evaluate(cb => cb.click());   // back
  }
  for (const o of ["glow", "hemiL", "hemiR", "clip", "pedestal", "stage"]) {
    const b = page.locator(`[data-opt="${o}"]`);
    if (!(await b.count())) { check(`${tag}: option ${o} present`, false); continue; }
    const p0 = await b.getAttribute("aria-pressed"); await b.click(); const p1 = await b.getAttribute("aria-pressed"); await b.click();
    check(`${tag}: option ${o} toggles`, p0 !== p1, [p0, p1]);
  }
  await frames(page, 1);

  // views: all seven; the bound page camera must end at the scene viewpoint's position
  const views = ["VP_HOME", "VP_LEFT", "VP_RIGHT", "VP_TOP", "VP_FRONT", "VP_MEDIAL", "VP_INSIDE"];
  for (const v of views) {
    await page.locator(`[data-vp="${v}"]`).click();
    await page.waitForTimeout(2200);
    await frames(page, 2);
    const r = await page.evaluate(v => { const n = window.__loom.node(v), c = window.__loom.camera(); return { vp: [n.position.x, n.position.y, n.position.z], got: c && c.position, target: c && c.target, pressed: document.querySelector(`[data-vp="${v}"]`).getAttribute("aria-pressed") }; }, v);
    const dist = (p, q) => Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
    const d = r.got ? dist(r.target, r.got) : 1e9, off = dist(r.vp, r.target);   // transition finished at the page camera's target; target is the scene viewpoint lifted clear of the dock
    check(`${tag}: view ${v} reached`, d < 3 && off < 0.14 * Math.max(60, Math.hypot(...r.vp)) && r.pressed === "true", { d: +d.toFixed(2), lift: +off.toFixed(1), pressed: r.pressed });
    if (v === "VP_MEDIAL") { await shot(page, `${tag}-02-medial`); const hl = await page.evaluate(() => window.__loom.node("SW_HEMI_L").whichChoice); check(`${tag}: medial view hides the left hemisphere`, hl === -1, hl); }
  }
  await page.locator('[data-vp="VP_HOME"]').click(); await page.waitForTimeout(2200);
  const hl2 = await page.evaluate(() => window.__loom.node("SW_HEMI_L").whichChoice); check(`${tag}: leaving medial restores the left hemisphere`, hl2 === 0, hl2);

  // looks: all twelve, each pushed into the scene; compare a pushed field with looks.json
  const looks = await page.evaluate(async () => (await fetch("data/looks.json")).json());
  check(`${tag}: twelve looks`, looks.length === 12, looks.length);
  let lookFail = 0;
  for (const l of looks) {
    await page.locator(`[data-look="${l.id}"]`).click();
    await page.waitForFunction(id => window.__loom.state.lookId === id, l.id, { timeout: 60000 });
    await frames(page, 2);
    const ok = await page.evaluate(l => {
      const key = l.push.find(p => p[0] === "KEY" && p[1] === "intensity"), n = window.__loom.node("KEY");
      const sw = l.push.find(p => p[0] === "SW_CORTEX"), c = window.__loom.node("SW_CORTEX");
      return { key: key && Math.abs(n.intensity - key[2]) < 1e-3, glass: sw && c.whichChoice === sw[2], touched: window.__loom.state.touched, pressed: document.querySelector(`[data-look="${l.id}"]`).getAttribute("aria-pressed"), glassUI: document.querySelector("#ly-glass").checked === (sw[2] === 0) };
    }, l);
    if (!(ok.key && ok.glass && ok.pressed === "true" && ok.glassUI)) lookFail++;
    if (["glass-fresnel", "wet-photoreal", "tractography-neon", "golden-cutaway", "cosmic-connectome"].includes(l.id)) await shot(page, `${tag}-03-look-${l.id}`);
    if (!ok.key || !ok.glass) console.log("  look detail", l.id, JSON.stringify(ok));
  }
  check(`${tag}: all twelve looks apply (KEY intensity, glass/wet, UI in sync)`, lookFail === 0, { failed: lookFail });
  await page.locator("#btnCompare").evaluate(b => b.disabled).then(d => check(`${tag}: compare enabled after a look switch`, d === false, d));
  await page.locator("#btnLookReset").click(); await page.waitForFunction(() => window.__loom.state.lookId === null, null, { timeout: 60000 }); await frames(page, 2);
  const kd = await page.evaluate(() => ({ k: window.__loom.node("KEY").intensity, t: window.__loom.state.touched }));
  check(`${tag}: scene default restores the lights`, Math.abs(kd.k - 1.8) < 1e-3 && kd.t === 0, kd);

  // picking: a synthetic click on the model must return a region (try several points, the rig draws a frame every second or so)
  await page.locator('[data-vp="VP_HOME"]').click(); await page.waitForTimeout(2000);
  const box = await page.locator("#stage").boundingBox();
  let picked = null;
  const cands = [[0.5, 0.5], [0.46, 0.45], [0.55, 0.5], [0.5, 0.4], [0.42, 0.52], [0.58, 0.45], [0.5, 0.58]];
  await page.mouse.move(box.x + 6, box.y + box.height - 6); await frames(page, 2);
  for (const [fx, fy] of cands) {
    const x = box.x + box.width * fx, y = box.y + box.height * fy;
    await page.mouse.move(x, y, { steps: 5 }); await frames(page, 3);
    const tip = await page.evaluate(() => { const t = document.querySelector("#tip"); return t.hidden ? null : t.textContent; });
    await page.mouse.down(); await frames(page, 2); await page.mouse.up(); await frames(page, 3);
    const s = await state(page);
    if (s.region) { picked = { at: [fx, fy], tip, region: s.region }; break; }
  }
  check(`${tag}: a click on the brain returns a region`, !!picked, picked);
  if (picked) {
    const card = await page.evaluate(() => ({ name: document.querySelector("#rName").textContent, lobe: document.querySelector("#rLobe").textContent, facts: [...document.querySelectorAll("#rFacts .facts__item")].map(i => i.querySelector("dt").textContent), note: document.querySelector("#rNote").textContent, visible: !document.querySelector("#regionCard").hidden }));
    check(`${tag}: region card shows name and four facts and the generated-text notice`, card.visible && card.name.length > 3 && card.facts.length === 4 && /clinical use/i.test(card.note), card);
    await shot(page, `${tag}-04-picked`);
  }
  // nearest-centroid logic on its own (no GPU dependency)
  const nn = await page.evaluate(() => { const r = window.__loom.pick([-44, 22, -6], "L", false); return r && { id: r.region.id, d: r.distance }; });
  check(`${tag}: nearest-anchor lookup returns a left cortical region`, nn && /^ctx-lh-/.test(nn.id), nn);
  // deep structure pick (hide cortex layers so the pointer reaches the structures)
  await page.evaluate(() => { document.querySelector("#ly-glass").click(); });
  await page.waitForTimeout(300);
  let deep = null;
  await page.evaluate(() => window.__loom.select("deep-thalamus"));
  const ds = await state(page); check(`${tag}: select() by id works for a deep structure`, ds.region === "deep-thalamus", ds.region);
  await page.evaluate(() => document.querySelector("#ly-glass").click());

  // region list + filter + focus
  await page.locator("#browse > summary").click();
  await page.locator("#regionFilter").fill("hippo");
  const vis = await page.evaluate(() => [...document.querySelectorAll("#regionList .browse__item")].filter(b => !b.hidden).map(b => b.dataset.id));
  check(`${tag}: region filter narrows the list`, vis.length >= 1 && vis.length <= 3 && vis.some(i => /hippocampus/.test(i)), vis);
  await page.locator('#regionList .browse__item:not([hidden])').first().click(); await page.waitForTimeout(2300);
  const sel = await state(page); check(`${tag}: list click selects and flies to the region`, /hippocampus/.test(sel.region || ""), sel.region);
  await shot(page, `${tag}-05-list-focus`);
  await page.locator("#regionFilter").fill("");
  await page.locator("#btnClear").click();
  check(`${tag}: clear empties the card`, (await state(page)).region === null);

  // loom log dialog
  await page.locator("#btnLog").click();
  const lg = await page.evaluate(() => ({ open: !document.querySelector("#dlgBack").hidden, text: document.querySelector("#paneProv").textContent, focus: document.activeElement && document.activeElement.id }));
  check(`${tag}: Loom log opens with sources, grades, SYNTHETIC notice, receipt (hash or placeholder)`, lg.open && /Suspected/.test(lg.text) && /Confirmed/.test(lg.text) && /SYNTHETIC/.test(lg.text) && /Receipt/.test(lg.text) && (/PLACEHOLDER/.test(lg.text) || /[0-9a-f]{64}/.test(lg.text)) && /sha256/.test(lg.text), { open: lg.open, len: lg.text.length, focus: lg.focus });
  await shot(page, `${tag}-06-loomlog`);
  await page.locator("#dt-session").click();
  check(`${tag}: session log pane lists events`, (await page.locator("#paneSession .session-log__row").count()) > 3);
  await page.locator("#dt-help").click(); check(`${tag}: help pane`, (await page.locator("#paneHelp .help__row").count()) >= 8);
  await page.keyboard.press("Escape");
  check(`${tag}: Escape closes the dialog and returns focus`, await page.evaluate(() => document.querySelector("#dlgBack").hidden && document.activeElement && document.activeElement.id === "btnLog"));

  // keyboard
  await page.locator("body").click({ position: { x: 5, y: 5 } }).catch(() => {});
  await page.keyboard.press("2"); await page.waitForTimeout(1800);
  check(`${tag}: key 2 selects the left view`, (await page.evaluate(() => document.querySelector('[data-vp="VP_LEFT"]').getAttribute("aria-pressed"))) === "true");
  await page.keyboard.press("w"); const w1 = await page.evaluate(() => window.__loom.node("SW_WET").whichChoice); await page.keyboard.press("w");
  check(`${tag}: key w toggles the wet cortex`, w1 === 0, w1);
  await page.keyboard.press("h").catch(() => {});
  await page.locator('[data-vp="VP_HOME"]').click();
  return { ctx, page };
}

async function tourPhase(page, tag) {
  await page.locator("#btnTour").click();
  await page.waitForFunction(() => window.__loom.state.tour === 0, null, { timeout: 60000 });
  const steps = await page.evaluate(async () => (await fetch("data/tour.json")).json());
  const n = steps.steps.length; check(`${tag}: tour has 8 steps`, n === 8, n);
  for (let i = 0; i < n; i++) {
    const st = steps.steps[i];
    await page.waitForFunction(i => window.__loom.state.tour === i, i, { timeout: 60000 });
    await page.waitForTimeout(1700); await frames(page, 2);
    const r = await page.evaluate(() => ({ step: document.querySelector("#tourStep").textContent, title: document.querySelector("#tourTitle").textContent, text: document.querySelector("#tourText").textContent.length, region: window.__loom.state.region, sw: window.__loom.state.sw }));
    const layerOk = ["glass", "wet", "deep", "tracts", "slices", "labels", "activation"].every(k => {
      const def = { glass: "SW_CORTEX", wet: "SW_WET", deep: "SW_DEEP", tracts: "SW_TRACTS", slices: "SW_SLICES", labels: "SW_LABELS", activation: "SW_ACTIV" }[k], want = st.layers.includes(k === "glass" ? "cortex" : k);
      return (r.sw[def] === 0) === want;
    });
    check(`${tag}: tour step ${i + 1} (${st.title}) shows its caption, region and layers`, r.step === `Step ${i + 1} of ${n}` && r.title === st.title && r.text > 80 && r.region === st.region && layerOk, { r: { step: r.step, region: r.region }, layerOk });
    if (i === 0 || i === 2 || i === 4 || i === 5 || i === 6) await shot(page, `${tag}-tour-${i + 1}`);
    if (i < n - 1) await page.locator("#tourNext").click();
  }
  await page.locator("#tourNext").click();   // Finish
  await page.waitForFunction(() => window.__loom.state.tour === null, null, { timeout: 60000 });
  const ts = await state(page);
  check(`${tag}: finishing the tour restores the layers`, ts.tour === null && ts.sw.SW_CORTEX === 0 && ts.sw.SW_TRACTS === -1, ts.sw);
  // keyboard: T starts, ArrowRight advances, Escape exits
  await page.locator("body").click({ position: { x: 5, y: 5 } }).catch(() => {});
  await page.keyboard.press("t"); await page.waitForFunction(() => window.__loom.state.tour === 0, null, { timeout: 60000 });
  await page.keyboard.press("ArrowRight"); await page.waitForFunction(() => window.__loom.state.tour === 1, null, { timeout: 60000 });
  await page.keyboard.press("Escape"); await page.waitForFunction(() => window.__loom.state.tour === null, null, { timeout: 60000 });
  check(`${tag}: keyboard tour (T, ArrowRight, Escape)`, true);
}

async function audioPhase(page, tag, expectAudio) {
  const has = await page.locator("#btnSound").isVisible();
  check(`${tag}: music control ${expectAudio ? "present" : "absent"} in this build`, has === expectAudio, has);
  if (!expectAudio) return;
  await page.locator("#btnSound").click();
  let active = false;
  for (let i = 0; i < 30 && !active; i++) { await page.waitForTimeout(500); active = await page.evaluate(() => !!window.__loom.node("AUDIO").isActive); }
  check(`${tag}: AudioClip becomes active after the click`, active);
  check(`${tag}: music button reports on`, (await page.locator("#btnSound").getAttribute("aria-pressed")) === "true");
  await page.locator("#vol").fill("30");
  const iv = await page.evaluate(() => window.__loom.node("SND").intensity); check(`${tag}: volume slider sets SND.intensity`, Math.abs(iv - 0.3) < 0.02, iv);
  await page.locator("#btnSound2").click(); await page.waitForTimeout(800);
  const act2 = await page.evaluate(() => !!window.__loom.node("AUDIO").isActive); check(`${tag}: stop button stops the clip`, !act2, act2);
}

async function torsoPhase(page, tag) {
  await page.locator('#tab-torso').click();
  await page.waitForFunction(() => window.__loom.state.kind === "torso" && window.__loom.state.ready, null, { timeout: BUDGET });
  await frames(page, 2);
  const st = await state(page); check(`${tag}: torso scene loaded in the second tab`, st.kind === "torso" && st.sensors >= 10, st);
  await shot(page, `${tag}-torso-01`);
  const n = await page.locator("#layerList input").count(); check(`${tag}: torso layer switches built from the scene`, n >= 12, n);
  const first = page.locator("#layerList input").nth(7); const def = await first.getAttribute("data-def");
  const w0 = await page.evaluate(d => window.__loom.node(d).whichChoice, def); await first.evaluate(c => c.click());
  const w1 = await page.evaluate(d => window.__loom.node(d).whichChoice, def); check(`${tag}: torso layer ${def} toggles`, w0 !== w1, [w0, w1]); await first.evaluate(c => c.click());
  const vws = await page.locator("#views .chip").count(); check(`${tag}: torso views listed`, vws >= 8, vws);
  await page.locator('#views [data-vp="VP_HEART"]').click(); await page.waitForTimeout(2200); await frames(page, 2);
  await shot(page, `${tag}-torso-02-heart`);
  // pick
  const box = await page.locator("#stage").boundingBox();
  let got = null;
  await page.locator('#views [data-vp="VP_CHEST"]').click(); await page.waitForTimeout(2200);
  await page.mouse.move(box.x + 6, box.y + box.height - 6); await frames(page, 2);
  for (const [fx, fy] of [[0.5, 0.5], [0.5, 0.42], [0.45, 0.55], [0.55, 0.5], [0.5, 0.62], [0.4, 0.45]]) {
    await page.mouse.move(box.x + box.width * fx, box.y + box.height * fy, { steps: 5 }); await frames(page, 3);
    await page.mouse.down(); await frames(page, 2); await page.mouse.up(); await frames(page, 3);
    const s = await state(page); if (s.region) { got = { at: [fx, fy], region: s.region }; break; }
  }
  check(`${tag}: a click on the torso returns a part`, !!got, got);
  if (got) { await shot(page, `${tag}-torso-03-picked`); const c = await page.evaluate(() => ({ n: document.querySelector("#rName").textContent, f: document.querySelectorAll("#rFacts .facts__item").length })); check(`${tag}: torso card lists source/volume/centre`, c.f >= 3 && c.n.length > 2, c); }
  // back to the brain
  await page.locator('#tab-brain').click();
  await page.waitForFunction(() => window.__loom.state.kind === "brain" && window.__loom.state.ready, null, { timeout: BUDGET });
  check(`${tag}: back to the brain tab`, (await state(page)).kind === "brain");
}

async function phonePhase(browser, base, tag) {
  const { ctx, page } = await brainPhase(browser, base, tag, { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true }, false);
  const sheets = ["layers", "look", "region"];
  for (const s of sheets) {
    await page.locator(`.phone-nav__btn[data-sheet="${s}"]`).tap();
    await page.waitForTimeout(400);
    const m = await page.evaluate(s => {
      const p = document.querySelector(`.panel[data-sheet="${s}"]`), r = p.getBoundingClientRect();
      const vis = [...document.querySelectorAll(".panel[data-sheet]")].filter(x => !x.hidden).map(x => x.dataset.sheet);
      return { visible: vis, top: Math.round(r.top), bottom: Math.round(r.bottom), left: Math.round(r.left), right: Math.round(r.right), width: Math.round(r.width), sw: document.documentElement.scrollWidth, iw: innerWidth };
    }, s);
    check(`${tag}: phone sheet ${s} opens alone, inside the viewport`, m.visible.length === 1 && m.visible[0] === s && m.left >= 0 && m.right <= m.iw && m.sw <= m.iw && m.width >= m.iw - 40, m);
    await shot(page, `${tag}-sheet-${s}`);
  }
  await page.locator(`.phone-nav__btn[data-sheet="tour"]`).tap();
  await page.waitForFunction(() => window.__loom.state.tour === 0, null, { timeout: 60000 });
  await page.waitForTimeout(1500);
  const tm = await page.evaluate(() => { const r = document.querySelector("#tour").getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), h: innerHeight, sw: document.documentElement.scrollWidth, iw: innerWidth }; });
  check(`${tag}: phone tour card fits the viewport`, tm.bottom <= tm.h && tm.sw <= tm.iw, tm);
  await shot(page, `${tag}-tour`);
  await page.locator("#tourExit").tap();
  // tap-target sizes on the controls a thumb needs
  const small = await page.evaluate(() => [...document.querySelectorAll(".phone-nav__btn, .tour__dot, #btnLog, #btnHelp, .tabs--top .tab")].filter(b => b.offsetParent).map(b => { const r = b.getBoundingClientRect(); return { id: b.id || b.className, w: Math.round(r.width), h: Math.round(r.height) }; }).filter(x => x.h < 32 || x.w < 24));
  check(`${tag}: thumb targets are at least 32 px tall`, small.length === 0, small);
  await ctx.close();
}

(async () => {
  const server = serve(PAGE_DIR); await new Promise(r => server.listen(0, "127.0.0.1", r));
  const base = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch();
  report.rig = { chromium: browser.version(), playwright: require("playwright/package.json").version };
  const t0 = Date.now();
  try {
    const wantAudio = fs.existsSync(path.join(PAGE_DIR, "scenes", "audio"));
    let desk = null;
    if (PHASES.includes("smoke") || PHASES.includes("desktop") || PHASES.includes("tour") || PHASES.includes("audio") || PHASES.includes("torso")) {
      desk = await brainPhase(browser, base, "desk", { viewport: { width: W, height: H } }, PHASES.includes("desktop"));
      const g = await desk.page.evaluate(() => ({ x: window.X3D && X3D.getBrowser("#stage").version, opt: X3D.getBrowser("#stage").getBrowserOption("ToneMapping"), oit: X3D.getBrowser("#stage").getBrowserOption("OrderIndependentTransparency") }));
      report.rig.xite = g; check("X_ITE 16.6.0, ToneMapping KHR_PBR_NEUTRAL, OIT off", g.x === "16.6.0" && g.opt === "KHR_PBR_NEUTRAL" && g.oit === false, g);
      if (PHASES.includes("audio")) await audioPhase(desk.page, "desk", wantAudio);
      if (PHASES.includes("tour")) await tourPhase(desk.page, "desk");
      if (PHASES.includes("torso") && fs.existsSync(path.join(PAGE_DIR, "scenes"))) await torsoPhase(desk.page, "desk");
      await desk.ctx.close();
    }
    if (PHASES.includes("phone")) await phonePhase(browser, base, "phone");
  } catch (e) {
    check("test run completed", false, String(e && e.stack || e).slice(0, 500));
  }
  const errs = report.console;
  check("no console errors, warnings, failed requests or page errors", errs.length === 0, errs.slice(0, 8));
  report.seconds = (Date.now() - t0) / 1000;
  report.pass = report.checks.every(c => c.ok);
  fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 1));
  console.log(`\n${report.checks.filter(c => c.ok).length}/${report.checks.length} checks passed in ${report.seconds.toFixed(0)} s -> ${path.join(OUT, "report.json")}`);
  await browser.close(); server.close();
  process.exit(report.pass ? 0 : 1);
})();
