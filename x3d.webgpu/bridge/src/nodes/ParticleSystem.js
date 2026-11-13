/* ParticleSystem drawn (ParticleSystems component): the reader has long known the node and its PointEmitter, ConeEmitter, ForcePhysicsModel and WindPhysicsModel, but the stock body skipped it
   ("skipped <ParticleSystem>"). This module draws it with a Babylon 9 CPU ParticleSystem whose emitter shape is the X3D emitter and whose physics are the X3D physics models:
     emitters   PointEmitter, ConeEmitter, VolumeEmitter (coord, coordIndex: random point inside the box of the coordinates, or on the faces when internal is FALSE), PolylineEmitter (random point
                on the line), SurfaceEmitter (random point on the faces of `surface`, area weighted, emitted along the face normal), ExplosionEmitter (all particles at once from one point, any direction)
     physics    ForcePhysicsModel (force / mass), WindPhysicsModel (the particle's velocity is pulled toward the wind, with gusts and turbulence), BoundedPhysicsModel (a particle that leaves the box or
                ball of `geometry` bounces back; the bound is the geometry's box, or its radius for a Sphere)
     look       geometryType POINT (round dots a few pixels wide), LINE (stretched along the velocity), TRIANGLE, QUAD, SPRITE (camera facing quads); the Appearance's texture or the Material colour
                (emissive, else diffuse), transparency, colorKey / color ramp over the particle's life (ColorRGBA keeps its alpha), particleSize.
   One system = one Babylon ParticleSystem with isLocal = true on a hidden emitter mesh under the node's parent, so the particles follow a moving Transform. */
const PS = (BR.ps = {
  rnd: Math.random,
  unit(v) { const l = Math.hypot(v[0], v[1], v[2]); return l > 1e-9 ? [v[0] / l, v[1] / l, v[2] / l] : null; },
  sphereDir() { const z = 2 * PS.rnd() - 1, t = PS.rnd() * Math.PI * 2, r = Math.sqrt(1 - z * z); return [r * Math.cos(t), z, r * Math.sin(t)]; },
  /* triangles (flat xyz x 3) of a geometry node: Box, Sphere (UV tessellation), the bridge geometry sets, IndexedFaceSet / IndexedTriangleSet, ElevationGrid is not read */
  tris(body, g) {
    if (!g) return [];
    const out = [], P = (a) => a.length ? a : [];
    if (g.type === 'Box') { const [x, y, z] = g.f.size.map((v) => v / 2); const v = [[-x, -y, -z], [x, -y, -z], [x, y, -z], [-x, y, -z], [-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z]]; for (const q of [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [3, 7, 6, 2], [0, 4, 7, 3], [1, 2, 6, 5]]) out.push([v[q[0]], v[q[1]], v[q[2]]], [v[q[0]], v[q[2]], v[q[3]]]); return out; }
    if (g.type === 'Sphere') { const r = g.f.radius, N = 16, M = 12, p = (i, j) => { const t = (i / N) * Math.PI * 2, f = (j / M) * Math.PI; return [r * Math.sin(f) * Math.cos(t), r * Math.cos(f), r * Math.sin(f) * Math.sin(t)]; }; for (let i = 0; i < N; i++) for (let j = 0; j < M; j++) { const a = p(i, j), b = p(i + 1, j), c = p(i + 1, j + 1), d = p(i, j + 1); out.push([a, c, d], [a, b, c]); } return out; }
    let d = null; try { d = body.geometryData(g); } catch (e) { /* no vertex data */ }
    if (d && d.pos && d.idx) { for (let i = 0; i + 2 < d.idx.length; i += 3) { const v = [0, 1, 2].map((k) => [d.pos[d.idx[i + k] * 3], d.pos[d.idx[i + k] * 3 + 1], d.pos[d.idx[i + k] * 3 + 2]]); out.push(v); } return out; }
    return out;
  },
  area(t) { const u = [t[1][0] - t[0][0], t[1][1] - t[0][1], t[1][2] - t[0][2]], v = [t[2][0] - t[0][0], t[2][1] - t[0][1], t[2][2] - t[0][2]]; const c = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]; return { a: 0.5 * Math.hypot(...c), n: PS.unit(c) || [0, 1, 0] }; },
  faces(em) {   // triangles of a VolumeEmitter / PolylineEmitter's own coordinates
    const P = em.f.coord && em.f.coord.f.point, ci = em.f.coordIndex || [], out = []; if (!P) return out; let face = [];
    const flush = () => { for (let i = 1; i + 1 < face.length; i++) out.push([face[0], face[i], face[i + 1]].map((k) => [P[k * 3], P[k * 3 + 1], P[k * 3 + 2]])); face = []; };
    for (const k of ci) { if (k < 0) flush(); else face.push(k); } if (face.length) flush(); return out;
  },
  segs(em) { const P = em.f.coord && em.f.coord.f.point, ci = em.f.coordIndex || [], out = []; if (!P) return out; let line = []; const fl = () => { for (let i = 0; i + 1 < line.length; i++) out.push([line[i], line[i + 1]].map((k) => [P[k * 3], P[k * 3 + 1], P[k * 3 + 2]])); line = []; }; for (const k of ci) { if (k < 0) fl(); else line.push(k); } fl(); return out; },
  box(P) { const lo = [1e30, 1e30, 1e30], hi = [-1e30, -1e30, -1e30]; for (let i = 0; i + 2 < P.length; i += 3) for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], P[i + k]); hi[k] = Math.max(hi[k], P[i + k]); } return P.length ? { lo, hi } : null; },
  /* the speed of one particle: speed * (1 +- variation), the sign random */
  speedOf(em) { const s = em.f.speed || 0, v = Math.min(1, Math.max(0, em.f.variation || 0)); return s * (1 + v * (2 * PS.rnd() - 1)); },
  /* emitter shape as a Babylon IParticleEmitterType: start position and start direction (times speed) of one particle in the emitter's local space */
  shape(body, ps) {
    const em = ps.f.emitter, f = em.f; let cache = null;
    const dir0 = PS.unit(f.direction || [0, 0, 0]);
    const along = (d, sp) => (d ? [d[0] * sp, d[1] * sp, d[2] * sp] : ((e) => [e[0] * sp, e[1] * sp, e[2] * sp])(PS.sphereDir()));
    let pos = () => (f.position ? f.position.slice() : [0, 0, 0]), dir = () => along(dir0, PS.speedOf(em));
    if (em.type === 'ConeEmitter') {
      dir = () => {   // a direction inside the cone of half angle `angle` around the emitter's direction, uniform over the cap
        const ang = Math.max(0, f.angle ?? 0.7854), d = dir0 || [0, 1, 0], ct = 1 - PS.rnd() * (1 - Math.cos(ang)), st = Math.sqrt(1 - ct * ct), ph = PS.rnd() * Math.PI * 2;
        const a = Math.abs(d[1]) < 0.99 ? [0, 1, 0] : [1, 0, 0], u = PS.unit([d[1] * a[2] - d[2] * a[1], d[2] * a[0] - d[0] * a[2], d[0] * a[1] - d[1] * a[0]]), w = [d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0]], sp = PS.speedOf(em);
        return [0, 1, 2].map((k) => (d[k] * ct + st * (Math.cos(ph) * u[k] + Math.sin(ph) * w[k])) * sp);
      };
    } else if (em.type === 'ExplosionEmitter') dir = () => along(null, PS.speedOf(em));
    else if (em.type === 'VolumeEmitter') {
      const P = em.f.coord && em.f.coord.f.point, bx = P && PS.box(P), faces = PS.faces(em), cum = []; let A = 0; for (const t of faces) { A += PS.area(t).a; cum.push(A); }
      const inside = (p) => { if (!faces.length) return true; let hits = 0; const d = [0.5773, 0.5773, 0.5773]; for (const t of faces) { const e1 = [t[1][0] - t[0][0], t[1][1] - t[0][1], t[1][2] - t[0][2]], e2 = [t[2][0] - t[0][0], t[2][1] - t[0][1], t[2][2] - t[0][2]], h = [d[1] * e2[2] - d[2] * e2[1], d[2] * e2[0] - d[0] * e2[2], d[0] * e2[1] - d[1] * e2[0]], a = e1[0] * h[0] + e1[1] * h[1] + e1[2] * h[2]; if (Math.abs(a) < 1e-9) continue; const s = [p[0] - t[0][0], p[1] - t[0][1], p[2] - t[0][2]], u = (s[0] * h[0] + s[1] * h[1] + s[2] * h[2]) / a; if (u < 0 || u > 1) continue; const q = [s[1] * e1[2] - s[2] * e1[1], s[2] * e1[0] - s[0] * e1[2], s[0] * e1[1] - s[1] * e1[0]], v = (d[0] * q[0] + d[1] * q[1] + d[2] * q[2]) / a; if (v < 0 || u + v > 1) continue; if ((e2[0] * q[0] + e2[1] * q[1] + e2[2] * q[2]) / a > 1e-7) hits++; } return hits % 2 === 1; };
      pos = () => {
        if (!bx) return f.position.slice();
        if (f.internal === false && faces.length) { const r = PS.rnd() * A; let i = cum.findIndex((c) => c >= r); if (i < 0) i = faces.length - 1; return PS.onTri(faces[i]).p; }
        for (let k = 0; k < 40; k++) { const p = [0, 1, 2].map((a) => bx.lo[a] + PS.rnd() * (bx.hi[a] - bx.lo[a])); if (inside(p)) return p; }
        return [0, 1, 2].map((a) => (bx.lo[a] + bx.hi[a]) / 2);
      };
    } else if (em.type === 'PolylineEmitter') {
      const sg = PS.segs(em), len = sg.map((s) => Math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1], s[1][2] - s[0][2])), tot = len.reduce((a, b) => a + b, 0);
      pos = () => { if (!sg.length) return f.position.slice(); let r = PS.rnd() * tot, i = 0; while (i < sg.length - 1 && r > len[i]) { r -= len[i]; i++; } const t = len[i] ? r / len[i] : 0, s = sg[i]; return [0, 1, 2].map((k) => s[0][k] + (s[1][k] - s[0][k]) * t); };
    } else if (em.type === 'SurfaceEmitter') {
      const tris = (cache = PS.tris(body, f.surface)), cum = []; let A = 0; for (const t of tris) { A += PS.area(t).a; cum.push(A); }
      // Babylon asks for the start direction and the start position of a particle in either order; both must come from the same point of the surface, so the pair is made on the first call and used up on the second
      let cur = null; const fresh = () => { if (!tris.length) return { p: [0, 0, 0], n: [0, 1, 0] }; const r = PS.rnd() * A; let k = cum.findIndex((c) => c >= r); if (k < 0) k = tris.length - 1; return PS.onTri(tris[k]); };
      pos = () => { if (!cur || cur.pd) cur = Object.assign(fresh(), { pd: false, dd: false }); cur.pd = true; const o = cur.p; if (cur.dd) cur = null; return o; };
      dir = () => { if (!cur || cur.dd) cur = Object.assign(fresh(), { pd: false, dd: false }); cur.dd = true; const sp = PS.speedOf(em), n = cur.n; if (cur.pd) cur = null; return [n[0] * sp, n[1] * sp, n[2] * sp]; };
    }
    const set = (v, a) => v.copyFromFloats(a[0], a[1], a[2]);
    return {
      startPositionFunction(wm, p) { set(p, pos()); },
      startDirectionFunction(wm, d) { set(d, dir()); },
      clone() { return this; }, applyToShader() {}, buildUniformLayout() {}, getEffectDefines() { return ''; }, getClassName() { return 'X3DEmitter'; }, serialize() { return {}; }, parse() {},
    };
  },
  drop(body, r) { if (r.dotObs) body.scene.onBeforeRenderObservable.remove(r.dotObs); if (r.ps) r.ps.dispose(); if (r.anchor) r.anchor.dispose(); if (r.tn) r.tn.dispose(); },
  onTri(t) { let a = PS.rnd(), b = PS.rnd(); if (a + b > 1) { a = 1 - a; b = 1 - b; } const p = [0, 1, 2].map((k) => t[0][k] + (t[1][k] - t[0][k]) * a + (t[2][k] - t[0][k]) * b); return { p, n: PS.area(t).n }; },
  /* sprite textures: the Appearance's picture, or a drawn mask for the geometry type */
  mask(body, type) {
    const key = 'psmask:' + type; if (body.texCache.has(key)) return body.texCache.get(key);
    const S = 64, dt = new BABYLON.DynamicTexture(key, { width: S, height: S }, body.scene, true), c = dt.getContext(); c.clearRect(0, 0, S, S); c.fillStyle = '#fff';
    if (type === 'TRIANGLE') { c.beginPath(); c.moveTo(S / 2, 3); c.lineTo(S - 3, S - 3); c.lineTo(3, S - 3); c.closePath(); c.fill(); }
    else if (type === 'QUAD' || type === 'LINE') c.fillRect(0, 0, S, S);
    else { const g = c.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2); g.addColorStop(0, 'rgba(255,255,255,1)'); g.addColorStop(type === 'POINT' ? 0.85 : 0.55, 'rgba(255,255,255,1)'); g.addColorStop(1, 'rgba(255,255,255,0)'); c.fillStyle = g; c.fillRect(0, 0, S, S); }
    dt.hasAlpha = true; dt.update(); body.texCache.set(key, dt); return dt;
  },
  /* the physics of the system: runs after Babylon's own step, on the particle's direction (the velocity) and position */
  physics(body, ps, bps) {
    const models = ps.f.physics || [], em = ps.f.emitter, mass = Math.max((em && em.f.mass) || 0, 0) || 1;
    const bounds = models.filter((m) => m.type === 'BoundedPhysicsModel').map((m) => ({ m, g: m.f.geometry, box: null }));
    for (const b of bounds) { if (!b.g) continue; if (b.g.type === 'Sphere') b.r = b.g.f.radius; else if (b.g.type === 'Box') { const s = b.g.f.size; b.box = { lo: s.map((v) => -v / 2), hi: s.map((v) => v / 2) }; } else { const t = PS.tris(body, b.g); const flat = []; for (const tr of t) for (const v of tr) flat.push(...v); b.box = PS.box(flat); } }
    let t0 = 0;
    return (parts, dt) => {
      t0 += dt;
      let wind = null; const wm = models.find((m) => m.type === 'WindPhysicsModel' && m.f.enabled !== false);
      if (wm) { const d = PS.unit(wm.f.direction) || [1, 0, 0], g = 1 + (wm.f.gustiness || 0) * Math.sin(t0 * 1.7) * Math.sin(t0 * 0.43 + 1), sp = Math.max(0, wm.f.speed) * g; wind = d.map((v) => v * sp); }
      for (const p of parts) {
        if (wind) { const k = Math.min(1, 0.8 * dt / mass); p.direction.x += (wind[0] - p.direction.x) * k; p.direction.y += (wind[1] - p.direction.y) * k; p.direction.z += (wind[2] - p.direction.z) * k;
          const tb = wm.f.turbulence || 0; if (tb > 0) { p.direction.x += (PS.rnd() - 0.5) * tb * dt * 4; p.direction.y += (PS.rnd() - 0.5) * tb * dt * 4; p.direction.z += (PS.rnd() - 0.5) * tb * dt * 4; } }
        for (const b of bounds) {
          if (b.m.f.enabled === false) continue;
          if (b.r !== undefined) { const L = p.position.length(); if (L > b.r && L > 0) { const n = p.position.scale(1 / L), vn = p.direction.x * n.x + p.direction.y * n.y + p.direction.z * n.z; if (vn > 0) { p.direction.x -= 2 * vn * n.x; p.direction.y -= 2 * vn * n.y; p.direction.z -= 2 * vn * n.z; } p.position.copyFrom(n.scale(b.r)); } }
          else if (b.box) for (const [k, a] of [[0, 'x'], [1, 'y'], [2, 'z']]) { if (p.position[a] < b.box.lo[k]) { p.position[a] = b.box.lo[k]; p.direction[a] = Math.abs(p.direction[a]); } else if (p.position[a] > b.box.hi[k]) { p.position[a] = b.box.hi[k]; p.direction[a] = -Math.abs(p.direction[a]); } }
        }
      }
    };
  },
});

BR.node('ParticleSystem', {
  component: 'ParticleSystems', level: 1,
  extend: { ParticleSystem: { texCoordKey: ['MFFloat', INIT, []], texCoord: ['SFNode', INIT, null], bboxCenter: ['SFVec3f', INIT, [0, 0, 0]], bboxSize: ['SFVec3f', INIT, [-1, -1, -1]] } },
  build(body, n, parent, chain) {
    const f = n.f, r = { node: n, chain: [n, ...chain], kids: [] }; body.rec.set(n.id, r);
    const tn = new BABYLON.TransformNode('ps-' + (n.def || n.id), body.scene); tn.parent = parent; r.tn = tn;
    if (f.visible === false) tn.setEnabled(false);
    if (!f.emitter) return r;
    const cap = Math.max(1, Math.min(20000, f.maxParticles | 0)), em = f.emitter, burst = em.type === 'ExplosionEmitter';
    const ps = new BABYLON.ParticleSystem('psys-' + (n.def || n.id), cap, body.scene), anchor = new BABYLON.Mesh('pse-' + n.id, body.scene);
    anchor.parent = tn; anchor.isVisible = false; anchor.isPickable = false; ps.emitter = anchor; ps.isLocal = true; ps.disposeOnStop = false;
    r.ps = ps; r.anchor = anchor; r.burst = burst;
    ps.minEmitPower = ps.maxEmitPower = 1; ps.updateSpeed = 1 / 60;
    const L = Math.max(0.05, f.particleLifetime), v = Math.min(1, Math.max(0, f.lifetimeVariation));
    ps.minLifeTime = L * (1 - v); ps.maxLifeTime = L * (1 + v); r.life = L;
    ps.particleEmitterType = PS.shape(body, n);
    // look
    const ap = f.appearance, mat = ap && ap.f.material, tex = ap && ap.f.texture, type = String(f.geometryType || 'QUAD').toUpperCase(), sz = f.particleSize || [0.02, 0.02];
    const t = tex && body.tex(tex); ps.particleTexture = t || PS.mask(body, type === 'GEOMETRY' ? 'SPRITE' : type);
    ps.minSize = ps.maxSize = 1;
    if (type === 'POINT') {          // a dot a few pixels wide whatever the distance: the size is re-set from the camera distance before each frame (applies to the particles emitted from then on)
      const px = R.bridge.pointSize || 3, wp = new BABYLON.Vector3();
      r.dotObs = body.scene.onBeforeRenderObservable.add(() => { const c = body.cam; anchor.getAbsolutePosition && wp.copyFrom(anchor.getAbsolutePosition()); const d = Math.max(0.1, BABYLON.Vector3.Distance(c.position, wp)), s = (2 * d * Math.tan(c.fov / 2) / (body.canvas.clientHeight || 240)) * px; ps.minScaleX = ps.maxScaleX = ps.minScaleY = ps.maxScaleY = s; });
      ps.minScaleX = ps.maxScaleX = ps.minScaleY = ps.maxScaleY = 0.05;
    }
    else { ps.minScaleX = ps.maxScaleX = sz[0]; ps.minScaleY = ps.maxScaleY = sz[1]; }
    if (type === 'LINE') ps.billboardMode = BABYLON.ParticleSystem.BILLBOARDMODE_STRETCHED;
    ps.blendMode = BABYLON.ParticleSystem.BLENDMODE_STANDARD;
    const tint = mat ? ((mat.f.emissiveColor && (mat.f.emissiveColor[0] || mat.f.emissiveColor[1] || mat.f.emissiveColor[2])) ? mat.f.emissiveColor : mat.f.diffuseColor || [1, 1, 1]) : [1, 1, 1], tr = mat ? 1 - (mat.f.transparency || 0) : 1;
    const ramp = f.color, keys = f.colorKey || [], cs = ramp && ramp.f.color, w = ramp && ramp.type === 'ColorRGBA' ? 4 : 3;
    ps.color1 = ps.color2 = new BABYLON.Color4(tint[0], tint[1], tint[2], tr); ps.colorDead = new BABYLON.Color4(tint[0], tint[1], tint[2], 0);
    if (cs && cs.length >= w) {
      const nC = cs.length / w;
      for (let i = 0; i < nC; i++) { const k = keys.length === nC ? keys[i] : i / Math.max(1, nC - 1); ps.addColorGradient(Math.min(1, Math.max(0, k)), new BABYLON.Color4(cs[i * w] * tint[0], cs[i * w + 1] * tint[1], cs[i * w + 2] * tint[2], (w === 4 ? cs[i * w + 3] : 1) * tr)); }
    }
    ps.renderingGroupId = 0;
    const base = ps.updateFunction, phys = PS.physics(body, n, ps);
    ps.updateFunction = function (parts) { base.call(this, parts); phys(parts, this._scaledUpdateSpeed || 1 / 60); };
    const force = new BABYLON.Vector3(0, 0, 0), mass = Math.max(em.f.mass || 0, 0) || 1;
    for (const m of f.physics || []) if (m.type === 'ForcePhysicsModel' && m.f.enabled !== false) force.addInPlace(new BABYLON.Vector3(m.f.force[0], m.f.force[1], m.f.force[2]).scale(1 / mass));
    ps.gravity = force;
    r.start = () => {
      if (n.f.enabled === false || em.f.on === false) { ps.emitRate = 0; ps.manualEmitCount = 0; return; }
      if (burst) { ps.emitRate = 0; ps.manualEmitCount = cap; } else { ps.manualEmitCount = -1; ps.emitRate = n.f.createParticles ? cap / L : 0; }
    };
    r.start(); ps.start();
    BR.emit(n, 'isActive', !!(n.f.enabled && n.f.createParticles));
    return r;
  },
  changed(body, n, field) {
    const r = body.rec.get(n.id); if (!r) return;
    if (field === 'visible') r.tn.setEnabled(n.f.visible !== false);
    else if (['enabled', 'createParticles'].includes(field) && r.ps) { r.start(); BR.emit(n, 'isActive', !!(n.f.enabled && n.f.createParticles)); }
    else if (['maxParticles', 'particleLifetime', 'lifetimeVariation', 'particleSize', 'geometryType', 'emitter', 'physics', 'colorKey', 'color', 'appearance'].includes(field)) {   // the look or the physics changed: build the system again in place
      const parent = r.tn.parent, chain = r.chain.slice(1); BR.ps.drop(body, r);
      const nr = BR.specs.get('ParticleSystem').build(body, n, parent, chain);
      for (const pr of body.rec.values()) if (pr.kids) { const i = pr.kids.indexOf(r); if (i >= 0) pr.kids[i] = nr; }
    }
  },
});
