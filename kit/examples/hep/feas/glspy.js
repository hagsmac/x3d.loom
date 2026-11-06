// Injected before any page script. Counts WebGL2 API calls (draw calls, program links, buffer bytes) and
// the main-thread time spent inside rAF callbacks. These are API-level counters, not GPU timings.
(() => {
  const C = { draw: 0, drawInst: 0, tris: 0, verts: 0, createProgram: 0, linkProgram: 0, compileShader: 0, bufferBytes: 0, texImage: 0, clear: 0, useProgram: 0 };
  const ctxs = [];
  let rafBusy = 0, rafN = 0;
  window.__glreset = () => { for (const k in C) C[k] = 0; rafBusy = 0; rafN = 0; };
  window.__glstats = () => Object.assign({ shader_logs: window.__shaderLogs.slice(0, 5) }, C, { raf_callbacks: rafN, raf_main_thread_ms_total: rafBusy, raf_main_thread_ms_mean: rafN ? rafBusy / rafN : null });
  const P = WebGL2RenderingContext.prototype;
  window.__shaderLogs = []; window.__glerrs = []; window.__glcheck = false;
  const prim = (mode, n) => { switch (mode) { case 4: return n / 3; case 5: case 6: return Math.max(0, n - 2); default: return 0; } };
  const wrap = (name, fn) => { const o = P[name]; P[name] = function (...a) { fn(a, this); return o.apply(this, a); }; };
  wrap('drawElements', (a, g) => { C.draw++; C.verts += a[1]; C.tris += prim(a[0], a[1]); if (window.__glcheck) setTimeout(() => {}, 0); });
  wrap('drawArrays', a => { C.draw++; C.verts += a[2]; C.tris += prim(a[0], a[2]); });
  wrap('drawElementsInstanced', a => { C.draw++; C.drawInst++; C.verts += a[1] * a[4]; C.tris += prim(a[0], a[1]) * a[4]; });
  wrap('drawArraysInstanced', a => { C.draw++; C.drawInst++; C.verts += a[2] * a[3]; C.tris += prim(a[0], a[2]) * a[3]; });
  wrap('createProgram', () => C.createProgram++);
  { const ol = P.linkProgram; P.linkProgram = function (p) { C.linkProgram++; ol.call(this, p); try { if (!this.getProgramParameter(p, this.LINK_STATUS)) window.__shaderLogs.push('LINK: ' + this.getProgramInfoLog(p).slice(0, 400)); } catch (e) {} }; }
  { const oc = P.compileShader; P.compileShader = function (s) { C.compileShader++; oc.call(this, s); try { if (!this.getShaderParameter(s, this.COMPILE_STATUS)) window.__shaderLogs.push('COMPILE: ' + this.getShaderInfoLog(s).slice(0, 500)); } catch (e) {} }; }
  wrap('useProgram', () => C.useProgram++);
  wrap('clear', () => C.clear++);
  wrap('bufferData', a => { const s = a[1]; C.bufferBytes += (s && s.byteLength) || (typeof s === 'number' ? s : 0); });
  wrap('texImage2D', () => C.texImage++);
  const oraf = window.requestAnimationFrame.bind(window);
  let lastDraw = 0; window.__onRendered = null;
  window.requestAnimationFrame = (cb) => oraf((t) => {
    const s = performance.now();
    try { cb(t); } finally {
      rafBusy += performance.now() - s; rafN++;
      // runs right after the callback that issued draw calls (still before compositing): lets a page copy the WebGL canvas
      if (C.draw !== lastDraw) { lastDraw = C.draw; if (window.__onRendered) { try { window.__onRendered(); } catch (e) {} } }
    }
  });
})();
