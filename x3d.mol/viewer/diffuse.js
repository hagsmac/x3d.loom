/* x3d.mol diffusion player: plays a scenes/anim/*.anim.x3d file (src/anim.py) over the live scene.
   The file is X3D: a TimeSensor routed to a CoordinateInterpolator routed to a PointSet's Coordinate. This player follows those
   ROUTEs as an X3D browser would (it refuses a file whose routes do not connect), interpolates the keys linearly, as
   CoordinateInterpolator is defined to, and draws each point as a small sphere. Look, not data: sphere sizes, the grey of
   unsettled atoms, the fade-in of colours and of the cartoon, and the order in which PAE cells appear. */
(function (root) {
  "use strict";
  const B = root.BABYLON;
  const f32 = (s) => Float32Array.from((s || "").trim().split(/\s+/).filter(Boolean), Number);
  const lin = (c) => Math.pow(Math.max(0, Math.min(1, c)), 2.2);
  const NOISE = [0.72, 0.84, 1.0];    // unsettled atoms: a cool grey-blue (look)
  const RADIUS = [0.55, 0.65, 0.6, 1.25]; // backbone, side chain, nucleic, zinc (angstrom, look)

  function parse(text) {
    const doc = new DOMParser().parseFromString(text, "application/xml");
    if (doc.querySelector("parsererror")) throw new Error("diffusion file is not well-formed XML");
    const meta = {};
    for (const m of doc.querySelectorAll("WorldInfo > MetadataSet > *")) {
      const v = m.getAttribute("value") || "";
      meta[m.getAttribute("name")] = m.tagName === "MetadataString" ? root.XMolReader.mfstring(v) : f32(v);
    }
    const byDef = {}; for (const e of doc.querySelectorAll("[DEF]")) byDef[e.getAttribute("DEF")] = e;
    const routes = [...doc.querySelectorAll("ROUTE")].map((r) => [r.getAttribute("fromNode"), r.getAttribute("fromField"), r.getAttribute("toNode"), r.getAttribute("toField")]);
    const r1 = routes.find((r) => byDef[r[0]] && byDef[r[0]].tagName === "TimeSensor" && r[1] === "fraction_changed" && r[3] === "set_fraction");
    const interp = r1 && byDef[r1[2]];
    const r2 = interp && routes.find((r) => r[0] === r1[2] && r[1] === "value_changed" && r[3] === "set_point");
    const coord = r2 && byDef[r2[2]];
    if (!interp || interp.tagName !== "CoordinateInterpolator" || !coord || coord.tagName !== "Coordinate") throw new Error("the file's ROUTEs do not connect clock, interpolator and coordinates");
    const clock = byDef[r1[0]];
    const key = f32(interp.getAttribute("key")), kv = f32(interp.getAttribute("keyValue")), rest = f32(coord.getAttribute("point"));
    const n = rest.length / 3;
    if (kv.length !== key.length * n * 3) throw new Error("keyValue length does not match keys x points");
    const color = f32(coord.parentElement.querySelector("Color").getAttribute("color"));
    return { meta, key, kv, rest, n, color, cycle: +clock.getAttribute("cycleInterval"), loop: clock.getAttribute("loop") === "true",
      title: doc.querySelector("WorldInfo").getAttribute("title"), disclaimer: (meta.disclaimer || [""])[0] };
  }

  /* fraction -> (segment, local t), as CoordinateInterpolator does */
  function seg(key, f) {
    if (f <= key[0]) return [0, 0];
    if (f >= key[key.length - 1]) return [key.length - 2, 1];
    let i = 1; while (key[i] < f) i++;
    return [i - 1, (f - key[i - 1]) / (key[i] - key[i - 1])];
  }

  function create(body, anim, opts) {
    opts = opts || {};
    const scene = body.scene, n = anim.n, cls = anim.meta.atom_class, cap = anim.meta.cap[0];
    const sph = B.MeshBuilder.CreateIcoSphere("diffAtoms", { radius: 1, subdivisions: opts.low ? 1 : n < 2000 ? 3 : 2 }, scene);
    const m = new B.PBRMaterial("diffMat", scene);
    m.albedoColor = new B.Color3(1, 1, 1); m.metallic = 0; m.roughness = 0.32; m.emissiveColor = new B.Color3(0.03, 0.04, 0.07); m.environmentIntensity = 1;
    sph.material = m; sph.isPickable = false; sph.parent = body.root; sph.alwaysSelectAsActiveMesh = true;
    const mats = new Float32Array(n * 16), cols = new Float32Array(n * 4), pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) { cols[i * 4 + 3] = 1; mats[i * 16 + 15] = 1; }
    sph.thinInstanceSetBuffer("matrix", mats, 16, false);
    sph.thinInstanceSetBuffer("color", cols, 4, false);
    const fin = anim.color, fl = new Float32Array(n * 3);
    for (let i = 0; i < n * 3; i++) fl[i] = lin(fin[i]);
    const nz = NOISE.map(lin);
    const last = anim.key.length - 1, base = last * n * 3;
    const p = { pos, mesh: sph, fraction: 0, playing: true, t0: performance.now(), anim, scale: 1, onFrame: null, settled: 0 };

    p.apply = function (f) {
      p.fraction = f;
      const [k, u] = seg(anim.key, f), a = k * n * 3, b = (k + 1) * n * 3, kv = anim.kv;
      const hold = anim.meta.denoise_fraction[0], h = f <= hold ? 0 : Math.min(1, (f - hold) / ((1 - hold) * 0.5));
      const shrink = 1 - 0.45 * h; let settled = 0;
      for (let i = 0; i < n; i++) {
        const o = i * 3;
        const x = kv[a + o] + (kv[b + o] - kv[a + o]) * u, y = kv[a + o + 1] + (kv[b + o + 1] - kv[a + o + 1]) * u, z = kv[a + o + 2] + (kv[b + o + 2] - kv[a + o + 2]) * u;
        pos[o] = x; pos[o + 1] = y; pos[o + 2] = z;
        const d = Math.hypot(x - kv[base + o], y - kv[base + o + 1], z - kv[base + o + 2]);
        const s = Math.max(0, Math.min(1, 1 - d / 3.5)), e = s * s * (3 - 2 * s);   // within 3.5 A of its place the atom takes its colour
        if (d < 1) settled++;
        const r = RADIUS[cls[i]] * (cls[i] === 3 ? 1 : shrink) * (1.6 - 0.6 * e), q = i * 16;   // unsettled atoms drawn larger so the cloud reads
        mats[q] = r; mats[q + 5] = r; mats[q + 10] = r; mats[q + 12] = x; mats[q + 13] = y; mats[q + 14] = z;
        const c = i * 4;
        cols[c] = nz[0] + (fl[o] - nz[0]) * e; cols[c + 1] = nz[1] + (fl[o + 1] - nz[1]) * e; cols[c + 2] = nz[2] + (fl[o + 2] - nz[2]) * e;
      }
      sph.thinInstanceBufferUpdated("matrix"); sph.thinInstanceBufferUpdated("color");
      sph.thinInstanceRefreshBoundingInfo(false);
      p.settled = settled / n;
      const step = anim.meta.step, sig = anim.meta.sigma, shown = anim.meta.sigma_shown;
      const kk = Math.min(k + (u > 0.5 ? 1 : 0), step.length - 1);
      p.info = { fraction: f, key: kk, step: f >= hold ? step[step.length - 1] : step[kk], steps: anim.meta.steps[0], sigma: f >= hold ? 0 : sig[kk], shown: f >= hold ? 0 : shown[kk], cap, settled: p.settled, hold: h };
      if (p.onFrame) p.onFrame(p.info);
    };
    p.play = function (on) { p.playing = on; if (on) p.t0 = performance.now() - p.fraction * anim.cycle * 1000; };
    p.seek = function (f) { p.fraction = Math.max(0, Math.min(1, f)); p.t0 = performance.now() - p.fraction * anim.cycle * 1000; p.apply(p.fraction); };
    const obs = scene.onBeforeRenderObservable.add(() => {
      if (!p.playing) return;
      let f = ((performance.now() - p.t0) / 1000) / anim.cycle;
      f = anim.loop ? f - Math.floor(f) : Math.min(1, f);
      p.apply(f);
    });
    p.dispose = function () { scene.onBeforeRenderObservable.remove(obs); sph.dispose(); m.dispose(); };
    p.extent = function () {   // centre and radius of the noisiest frame, so the camera can hold the whole cloud
      let c = [0, 0, 0]; for (let i = 0; i < n; i++) for (let k = 0; k < 3; k++) c[k] += anim.rest[i * 3 + k] / n;
      const d = new Float32Array(n); for (let i = 0; i < n; i++) d[i] = Math.hypot(anim.kv[i * 3] - c[0], anim.kv[i * 3 + 1] - c[1], anim.kv[i * 3 + 2] - c[2]);
      d.sort(); return { center: c, radius: d[Math.floor(n * 0.85)] };   // 85th percentile: a few far atoms should not shrink the view
    };
    p.apply(0);
    return p;
  }

  /* PAE reveal: cells with lower error appear first, with a fixed per-cell jitter (look, not data: AlphaFold 3 computes PAE in its
     confidence head, not during diffusion). pae is the half-angstrom array the scene stores. Returns a function of progress 0..1. */
  function paeReveal(canvas, pae, N, M) {
    const g = canvas.getContext("2d"), W = canvas.width, img = g.getImageData(0, 0, W, W), src = img.data.slice(), rank = new Float32Array(N * N);
    let s = 12345; const rnd = () => ((s = (s * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
    for (let k = 0; k < N * N; k++) rank[k] = 0.8 * Math.min(1, pae[k] * 0.5 / 31) + 0.2 * rnd();
    let lastR = -1;
    const draw = function (r) {
      if (Math.abs(r - lastR) < 0.01 && r !== 1 && r !== 0) return; lastR = r;
      const d = img.data;
      for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) {
        const o = ((i + M) * W + (j + M)) * 4, on = rank[i * N + j] <= r * 1.02;
        d[o] = on ? src[o] : 14; d[o + 1] = on ? src[o + 1] : 18; d[o + 2] = on ? src[o + 2] : 26;
      }
      g.putImageData(img, 0, 0);
    };
    draw.restore = function () { img.data.set(src); g.putImageData(img, 0, 0); lastR = -1; };
    return draw;
  }

  root.XMolDiffuse = { parse, create, paeReveal, seg };
})(typeof window !== "undefined" ? window : globalThis);
