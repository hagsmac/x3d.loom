const { chromium } = require('playwright'); const http = require('http'), fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, 'site');
(async () => {
  const server = http.createServer((req, res) => { const p = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname)); if (!fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); } res.writeHead(200, { 'content-type': p.endsWith('.html') ? 'text/html' : p.endsWith('.js') ? 'text/javascript' : p.endsWith('.css') ? 'text/css' : 'application/octet-stream' }); fs.createReadStream(p).pipe(res); }).listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const p = await b.newPage({ viewport: { width: 960, height: 540 } });
  p.on('console', c => console.log('[console ' + c.type() + ']', c.text().slice(0, 400)));
  await p.goto(`http://127.0.0.1:${server.address().port}/shot.html?scene=${process.argv[2]}`);
  await p.waitForFunction(() => window.__ready, null, { timeout: 60000 });
  const r = await p.evaluate(() => {
    const B = document.getElementById('c').browser, sc = B.currentScene; const out = [];
    const walk = (n, d) => { if (!n || d > 6) return; const t = n.getNodeTypeName(); if (/Shader|ShaderPart/.test(t)) { const o = { t }; for (const f of ['isValid', 'language', 'type', 'url', 'loadState']) { try { o[f] = n[f] !== undefined ? (typeof n[f] === 'object' ? String(n[f]).slice(0, 80) : n[f]) : undefined; } catch (e) {} } out.push(o); }
      for (const f of n.getFieldDefinitions ? [...n.getFieldDefinitions()] : []) { try { if (f.dataType === X3D.X3DConstants.SFNode) walk(n[f.name], d + 1); else if (f.dataType === X3D.X3DConstants.MFNode) for (const c of n[f.name]) walk(c, d + 1); } catch (e) {} } };
    for (const n of sc.rootNodes) walk(n, 0); return out; });
  console.log(JSON.stringify(r, null, 1));
  await b.close(); server.close(); process.exit(0);
})();
