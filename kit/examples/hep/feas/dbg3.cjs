const { chromium } = require('playwright'); const http = require('http'), fs = require('fs'), path = require('path');
const ROOT = path.join(__dirname, 'site');
(async () => {
  const server = http.createServer((req, res) => { const p = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname)); if (!fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); } res.writeHead(200, { 'content-type': p.endsWith('.html') ? 'text/html' : p.endsWith('.js') ? 'text/javascript' : p.endsWith('.css') ? 'text/css' : 'application/octet-stream' }); fs.createReadStream(p).pipe(res); }).listen(0, '127.0.0.1');
  await new Promise(r => server.once('listening', r));
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const p = await b.newPage({ viewport: { width: 960, height: 540 } });
  await p.goto(`http://127.0.0.1:${server.address().port}/${process.argv[2]}`);
  await p.waitForFunction(() => window.__ready || window.__result, null, { timeout: 60000 });
  const r = await p.evaluate(() => { const c = document.getElementById('c'); const cvs = [...(c.shadowRoot || document).querySelectorAll('canvas')].map(x => [x.width, x.height, x.clientWidth, x.clientHeight, x.getBoundingClientRect().top]);
    const gl = c.browser.getContext(); const g = gl.canvas; return { glcanvas: [g.width, g.height, g.clientWidth, g.clientHeight, g.tagName, g.className], shadowChildren: [...(c.shadowRoot ? c.shadowRoot.querySelectorAll('*') : [])].map(e => e.tagName + '.' + e.className + ':' + e.clientHeight).slice(0, 12), x3d: [c.clientWidth, c.clientHeight, c.getBoundingClientRect().height], canvases: cvs, body: [document.body.scrollHeight, document.documentElement.scrollHeight], dpr: devicePixelRatio, vp: [innerWidth, innerHeight] }; });
  console.log(JSON.stringify(r));
  await b.close(); server.close(); process.exit(0);
})();
