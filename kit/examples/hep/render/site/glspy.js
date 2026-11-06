// Injected before any page script. Counts WebGL2 API calls (draw calls, program links, shader compiles) and keeps the
// first compile or link error logs. API-level counters only: no GPU timing, no frame rate.
(() => {
  const C = { draw: 0, verts: 0, linkProgram: 0, compileShader: 0 };
  window.__shaderLogs = [];
  window.__glstats = () => Object.assign({ shader_logs: window.__shaderLogs.slice(0, 6) }, C);
  const P = WebGL2RenderingContext.prototype;
  const wrap = (name, fn) => { const o = P[name]; P[name] = function (...a) { fn(a); return o.apply(this, a); }; };
  wrap('drawElements', a => { C.draw++; C.verts += a[1]; });
  wrap('drawArrays', a => { C.draw++; C.verts += a[2]; });
  wrap('drawElementsInstanced', a => { C.draw++; C.verts += a[1] * a[4]; });
  wrap('drawArraysInstanced', a => { C.draw++; C.verts += a[2] * a[3]; });
  { const ol = P.linkProgram; P.linkProgram = function (p) { C.linkProgram++; ol.call(this, p); try { if (!this.getProgramParameter(p, this.LINK_STATUS)) window.__shaderLogs.push('LINK: ' + this.getProgramInfoLog(p).slice(0, 400)); } catch (e) {} }; }
  { const oc = P.compileShader; P.compileShader = function (s) { C.compileShader++; oc.call(this, s); try { if (!this.getShaderParameter(s, this.COMPILE_STATUS)) window.__shaderLogs.push('COMPILE: ' + this.getShaderInfoLog(s).slice(0, 500)); } catch (e) {} }; }
})();
