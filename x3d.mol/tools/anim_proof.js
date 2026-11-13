#!/usr/bin/env node
/* Proof for the diffusion player (headless Chromium, SwiftShader: correctness only, never timing).
   For each diffusion scene: opens #anim=<id>, pauses, seeks through the loop and saves a frame at each stop, and checks that
   the drawn atoms at the end ARE the file's rest coordinates, that the first frame carries the noise the file states, that
   play / pause / scrub / Follow / Exit / space answer, that the receipt shows the sha256 match and the witness, that the
   disclaimer is on screen, that the PAE map fills in (AlphaFold model), and that no panels overlap at 1280, 1024 and 390 px.

   node tools/anim_proof.js --docs docs --babylon /path/to/babylon.js --out OUTDIR */
const http = require("http"), fs = require("fs"), path = require("path");
const { chromium } = require("playwright");
const a = Object.fromEntries(process.argv.slice(2).reduce((m, v, i, arr) => (v.startsWith("--") ? m.concat([[v.slice(2), arr[i + 1]]]) : m), []));
const docs = path.resolve(a.docs || "docs"), out = path.resolve(a.out || "proof-anim");
fs.mkdirSync(out, { recursive: true });
const MIME = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".gz": "application/gzip" };
const srv = http.createServer((req, res) => {
  const u = decodeURIComponent(req.url.split("?")[0]), f = path.join(docs, u === "/" ? "index.html" : u);
  if (!f.startsWith(docs) || !fs.existsSync(f)) { res.statusCode = 404; return res.end(); }
  res.setHeader("content-type", MIME[path.extname(f)] || "application/octet-stream"); fs.createReadStream(f).pipe(res);
});
const checks = [];
const check = (name, ok, detail) => { checks.push({ name, ok: !!ok, detail }); console.log(ok ? "ok  " : "FAIL", name, detail === undefined ? "" : JSON.stringify(detail)); };

async function open(b, w, h, hash) {
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 }), p = await ctx.newPage(), errs = [];
  p.on("pageerror", (e) => errs.push(String(e.message).slice(0, 200)));
  p.on("console", (m) => { if (m.type() === "error") errs.push(m.text().slice(0, 200)); });
  if (a.babylon) await p.route("**/babylon.js", (r) => r.fulfill({ path: a.babylon, contentType: "text/javascript" }));
  await p.goto(`http://localhost:${srv.address().port}/index.html#${hash}`);
  await p.waitForFunction(() => window.__xmolAnimReady || window.__xmolError, null, { timeout: 240000 });
  await p.waitForTimeout(1500);
  return { ctx, p, errs };
}
const lit = (p) => p.evaluate(() => {
  const cv = document.getElementById("stage"), w = 160, h = Math.round(160 * cv.height / cv.width), s = document.createElement("canvas"); s.width = w; s.height = h;
  const g = s.getContext("2d"); g.drawImage(cv, 0, 0, w, h); const d = g.getImageData(0, 0, w, h).data, bg = [d[0], d[1], d[2]]; let n = 0;
  for (let i = 0; i < d.length; i += 4) if (Math.abs(d[i] - bg[0]) + Math.abs(d[i + 1] - bg[1]) + Math.abs(d[i + 2] - bg[2]) > 40) n++;
  return +(n / (w * h)).toFixed(3);
});
const overlaps = (p) => p.evaluate(() => {
  const ids = ["side", "info", "controls", "legend", "pae", "residue", "receipt", "menu", "diff"], r = {};
  for (const id of ids) { const e = document.getElementById(id); if (e && !e.hidden && getComputedStyle(e).display !== "none") { const q = e.getBoundingClientRect(); if (q.right > 0 && q.left < innerWidth && q.width > 0) r[id] = [q.left, q.top, q.right, q.bottom].map(Math.round); } }
  const bad = [], k = Object.keys(r);
  for (let i = 0; i < k.length; i++) for (let j = i + 1; j < k.length; j++) { const A = r[k[i]], B = r[k[j]]; if (A[0] < B[2] - 1 && B[0] < A[2] - 1 && A[1] < B[3] - 1 && B[1] < A[3] - 1) bad.push(k[i] + "/" + k[j]); }
  return { r, bad, hscroll: document.documentElement.scrollWidth > innerWidth };
});

(async () => {
  await new Promise((r) => srv.listen(0, r));
  const b = await chromium.launch({ args: ["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const idx = JSON.parse(fs.readFileSync(path.join(docs, "scenes/anim/anim.json")));
  for (const s of idx.scenes) {
    const { ctx, p, errs } = await open(b, 1280, 800, `anim=${s.id}&q=low&gpu=0`);
    const ready = await p.evaluate(() => window.__xmolAnimReady || { error: window.__xmolError });
    check(`${s.id}: player ready, sha256 matches anim.json`, ready && ready.shaOk && ready.atoms === s.atoms && ready.keys === s.keys, ready);
    await p.click("#dPlay");
    const paused = await p.evaluate(() => !window.__xmolState.player.playing && document.getElementById("dPlay").textContent === "Play");
    check(`${s.id}: Pause stops the clock`, paused);
    const frames = [];
    for (const f of [0, 0.15, 0.3, 0.45, 0.6, 0.7, 0.8, 0.95]) {
      await p.evaluate((f) => { const el = document.getElementById("dScrub"); el.value = String(Math.round(f * 1000)); el.dispatchEvent(new Event("input")); }, f);
      await p.waitForTimeout(f === 0.95 ? 1600 : 900);
      const png = `${s.id}-diffusion-${String(Math.round(f * 100)).padStart(3, "0")}.png`;
      await p.screenshot({ path: path.join(out, png) });
      const st = await p.evaluate(() => { const pl = window.__xmolState.player, i = pl.info, a = pl.anim; let mx = 0, ss = 0;
        for (let k = 0; k < a.n * 3; k++) { const d = pl.pos[k] - a.rest[k]; mx = Math.max(mx, Math.abs(d)); }
        for (let k = 0; k < a.n; k++) ss += (pl.pos[k * 3] - a.rest[k * 3]) ** 2 + (pl.pos[k * 3 + 1] - a.rest[k * 3 + 1]) ** 2 + (pl.pos[k * 3 + 2] - a.rest[k * 3 + 2]) ** 2;
        return { fraction: i.fraction, step: i.step, sigma: +i.sigma.toFixed(2), shown: +i.shown.toFixed(2), settled: +i.settled.toFixed(3), maxDev: +mx.toFixed(4), rms: +Math.sqrt(ss / a.n).toFixed(2),
          text: document.getElementById("dRead").innerText, cartoon: window.__xmolState.body.meshes.map((m) => +m.visibility.toFixed(2))[0] }; });
      st.lit = await lit(p); st.png = png; frames.push(st);
    }
    const first = frames[0], end = frames[frames.length - 1];
    const meta0 = await p.evaluate(() => window.__xmolState.player.anim.meta.rms_from_final[0]);
    check(`${s.id}: first frame carries the stated noise (rms ${first.rms} vs file ${meta0} A)`, Math.abs(first.rms - meta0) < 0.02, { rms: first.rms, file: meta0 });
    check(`${s.id}: at 95% every drawn atom is on the file's rest coordinates (max ${end.maxDev} A)`, end.maxDev <= 0.001 && end.settled === 1, end);
    check(`${s.id}: noise shrinks along the loop`, frames.slice(0, 7).every((f, i, arr) => i === 0 || f.rms <= arr[i - 1].rms + 1.0) && frames[6].rms < 1, frames.map((f) => f.rms));
    check(`${s.id}: cartoon hidden while denoising, shown in the hold`, frames[3].cartoon === 0 && end.cartoon === 1, frames.map((f) => f.cartoon));
    check(`${s.id}: every frame draws something`, frames.every((f) => f.lit >= 0.01), frames.map((f) => f.lit));
    check(`${s.id}: the read-out names the step and noise`, /step \d+ of 200/.test(frames[2].text) && /σ/.test(frames[2].text) && /noise 0/.test(end.text), [frames[2].text, end.text]);
    const ui = await p.evaluate(() => ({ note: document.getElementById("dNote").innerText, receipt: document.getElementById("receipt").innerText,
      pae: (() => { const c = document.getElementById("paeCanvas"); if (document.getElementById("pae").hidden) return null; const g = c.getContext("2d"), d = g.getImageData(0, 0, c.width, c.height).data; let dark = 0; for (let i = 0; i < d.length; i += 4) if (d[i] === 14 && d[i + 1] === 18 && d[i + 2] === 26) dark++; return dark / (d.length / 4); })() }));
    check(`${s.id}: disclaimer on screen`, /not a live run/.test(ui.note), ui.note.slice(0, 80));
    check(`${s.id}: receipt shows the diffusion file, sha256 match and witness pass`, /diffusion/.test(ui.receipt) && /matches the file served/.test(ui.receipt) && /witness pass/.test(ui.receipt), ui.receipt.split("\n").filter((l) => /diffusion|witness|sha/.test(l)).slice(0, 4));
    if (s.kind === "afdb") {
      await p.evaluate(() => { const el = document.getElementById("dScrub"); el.value = "300"; el.dispatchEvent(new Event("input")); });
      await p.waitForTimeout(400);
      const mid = await p.evaluate(() => { const c = document.getElementById("paeCanvas"), d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data; let dark = 0; for (let i = 0; i < d.length; i += 4) if (d[i] === 14 && d[i + 1] === 18 && d[i + 2] === 26) dark++; return dark / (d.length / 4); });
      check(`${s.id}: PAE map part-filled mid-way, complete at the end`, mid > 0.1 && ui.pae < 0.001, { mid: +mid.toFixed(3), end: ui.pae });
    }
    await p.click("#dPlay");
    const f0 = await p.evaluate(() => window.__xmolState.player.fraction); await p.waitForTimeout(1500);
    const f1 = await p.evaluate(() => window.__xmolState.player.fraction);
    check(`${s.id}: Play resumes the clock`, f1 !== f0, { f0, f1 });
    await p.focus("#stage"); await p.keyboard.press(" ");
    check(`${s.id}: space pauses`, await p.evaluate(() => !window.__xmolState.player.playing));
    await p.mouse.move(640, 400); await p.mouse.down(); await p.mouse.move(700, 420); await p.mouse.up();
    check(`${s.id}: dragging the view turns Follow off`, await p.evaluate(() => !window.__xmolState.follow && !document.getElementById("dFollow").classList.contains("on")));
    const ov = await overlaps(p);
    check(`${s.id}: 1280 px, no overlapping panels`, !ov.bad.length && !ov.hscroll, ov.bad);
    await p.click("#dExit"); await p.waitForTimeout(1500);
    const ex = await p.evaluate(() => ({ player: !!window.__xmolState.player, diff: document.getElementById("diff").hidden, vis: window.__xmolState.body.meshes.every((m) => m.visibility === 1), hash: location.hash }));
    check(`${s.id}: Exit removes the player and restores the cartoon`, !ex.player && ex.diff && ex.vis && /scene=/.test(ex.hash), ex);
    check(`${s.id}: no console errors`, !errs.length, errs.slice(0, 3));
    s.frames = frames;
    await ctx.close();
  }
  for (const [w, h] of [[1024, 768], [390, 844]]) {
    const { ctx, p, errs } = await open(b, w, h, `anim=AF-P04637-F1&q=low&gpu=0`);
    await p.click("#dPlay"); await p.waitForTimeout(500);
    const ov = await overlaps(p);
    await p.screenshot({ path: path.join(out, `layout-${w}.png`) });
    check(`${w} px: no overlapping panels, no horizontal scroll`, !ov.bad.length && !ov.hscroll, { bad: ov.bad, r: ov.r });
    const tap = await p.evaluate(() => { const e = document.getElementById("dPlay").getBoundingClientRect(); return e.width >= 40 && e.height >= 28; });
    check(`${w} px: Play button is a usable size`, tap);
    check(`${w} px: no console errors`, !errs.length, errs.slice(0, 3));
    await ctx.close();
  }
  await b.close(); srv.close();
  const failed = checks.filter((c) => !c.ok).length;
  fs.writeFileSync(path.join(out, "anim-proof.json"), JSON.stringify({ harness: "headless Chromium, SwiftShader WebGL2 (correctness only, never timing)", checks, scenes: idx.scenes.map((s) => ({ id: s.id, frames: s.frames })), failed }, null, 1));
  console.log(`\n${checks.length - failed} of ${checks.length} checks passed`);
  process.exit(failed ? 1 : 0);
})();
