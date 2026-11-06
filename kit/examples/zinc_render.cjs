// Renders the zinc finger Site scenes in X_ITE, one frame per Viewpoint (the eyes step; its reading is graded S).
//
//   node kit/examples/zinc_render.cjs CANDIDATE XITE_DIST OUT_DIR [id ...]
//
// The rig, stated with every frame (a render claim names the runtime patch AND the rig): X_ITE from XITE_DIST (an
// npm pack of x_ite), headless Chromium through Playwright, a 960x720 canvas at device scale 1, the scene's own
// Viewpoints bound one at a time through SAI (set_bind), 1.5 s after each bind so the default transition has
// finished, no page script touching the scene. Writes OUT_DIR/<id>-<k>.png and OUT_DIR/render-log.json (versions,
// GL renderer, every console message tagged with its scene, and a sha256 per frame).
"use strict";
const http = require("http"), fs = require("fs"), path = require("path"), crypto = require("crypto");
const { chromium } = require("playwright");

const [cand, xite, out, ...only] = process.argv.slice(2);
if (!cand || !xite || !out) { console.error("usage: zinc_render.cjs CANDIDATE XITE_DIST OUT_DIR [id ...]"); process.exit(2); }
const TYPES = { ".js": "text/javascript", ".mjs": "text/javascript", ".x3d": "model/x3d+xml", ".css": "text/css",
  ".json": "application/json", ".wasm": "application/wasm", ".html": "text/html" };
const PAGE = `<!doctype html><html><head><meta charset="utf-8"><script src="/xite/x_ite.min.js"></script>
<style>html,body{margin:0;background:#000}x3d-canvas{width:960px;height:720px;display:block}</style></head>
<body><x3d-canvas id="c" splashScreen="false" contextMenu="false" notifications="false"></x3d-canvas></body></html>`;

function serve() {
  const roots = { xite: path.resolve(xite), cand: path.resolve(cand) };
  return http.createServer((req, res) => {
    const url = decodeURIComponent(req.url.split("?")[0]);
    if (url === "/") { res.writeHead(200, { "content-type": "text/html" }); return res.end(PAGE); }
    const [, top, ...rest] = url.split("/");
    const base = roots[top];
    const file = base && path.resolve(base, rest.join("/"));
    if (!file || !file.startsWith(base + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
      res.writeHead(404); return res.end();
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
}

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const ids = only.length ? only : fs.readdirSync(path.join(cand, "scenes")).filter(f => f.endsWith(".x3d")).map(f => f.slice(0, -4)).sort();
  const server = serve();
  await new Promise(r => server.listen(0, "127.0.0.1", r));
  const port = server.address().port;
  const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
  const page = await browser.newPage({ viewport: { width: 960, height: 720 }, deviceScaleFactor: 1 });
  let current = "page";
  const consoleLog = [];
  page.on("console", m => consoleLog.push({ scene: current, type: m.type(), text: m.text().slice(0, 400) }));
  page.on("pageerror", e => consoleLog.push({ scene: current, type: "pageerror", text: String(e).slice(0, 400) }));
  await page.goto(`http://127.0.0.1:${port}/`);
  await page.waitForFunction(() => window.X3D && document.querySelector("#c") && X3D.getBrowser("#c"));
  const rig = await page.evaluate(() => {
    const b = X3D.getBrowser("#c");
    let gl = null;
    try {
      const ctx = b.getContext();
      const ext = ctx.getExtension("WEBGL_debug_renderer_info");
      gl = { version: ctx.getParameter(ctx.VERSION), renderer: ext ? ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL) : ctx.getParameter(ctx.RENDERER) };
    } catch (e) { gl = { error: String(e) }; }
    return { runtime: b.name, runtime_version: b.version, gl, user_agent: navigator.userAgent };
  });
  rig.chromium = browser.version();
  rig.canvas = "960x720 at device scale 1";
  rig.binding = "scene Viewpoints bound in order via SAI set_bind; frame taken 1.5 s after each bind";
  const frames = [];
  for (const id of ids) {
    current = id;
    const vps = await page.evaluate(async (url) => {
      const b = X3D.getBrowser("#c");
      await b.loadURL(new X3D.MFString(url));
      window.vps = [];
      const nodes = b.currentScene.rootNodes;
      for (let i = 0; i < nodes.length; i++) {
        const n = nodes[i];
        if (n && n.getNodeTypeName() === "Viewpoint") window.vps.push(n);
      }
      return window.vps.map(v => v.description);
    }, `/cand/scenes/${id}.x3d`);
    for (let k = 0; k < vps.length; k++) {
      await page.evaluate(k => { window.vps[k].set_bind = true; }, k);
      await page.waitForTimeout(1500);
      const file = path.join(out, `${id}-${k + 1}.png`);
      await page.locator("#c").screenshot({ path: file });
      const sha = crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
      frames.push({ scene: id, viewpoint: vps[k], file: path.basename(file), sha256: sha });
      console.log(`${id} ${k + 1}/${vps.length} ${vps[k]}`);
    }
  }
  await browser.close();
  server.close();
  fs.writeFileSync(path.join(out, "render-log.json"), JSON.stringify({ schema: "loom.zinc-render/1", rig, frames, console: consoleLog }, null, 2) + "\n");
  console.log(`${frames.length} frames; ${consoleLog.length} console messages; ${rig.runtime} ${rig.runtime_version}; ${JSON.stringify(rig.gl)}`);
})().catch(e => { console.error("INSTRUMENT_ERROR", e); process.exit(2); });
