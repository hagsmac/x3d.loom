/* Bridge kit, Babylon side. Concatenated after brain/body.js and body-cam.js (Body is a class in the bundle scope). A node the kit owns is built by its own spec.build;
   a node with no build is an event or data node the reader runs, and the body stays silent about it instead of noting "skipped". Types the kit does not own go to the stock build. */
{
  const _build = Body.prototype.build;
  Body.prototype.build = function (n, parent, chain) {
    const s = R.bridge.specs.get(n && n.type);
    if (s) return s.build ? s.build(this, n, parent, chain) : null;
    return _build.call(this, n, parent, chain);
  };
  const _changed = Body.prototype.changed;
  Body.prototype.changed = function (node, field) {
    const s = R.bridge.specs.get(node.type);
    if (s && s.changed) s.changed(this, node, field);
    return _changed.call(this, node, field);
  };
}

/* pointer drag sensors: a press on a Shape starts every drag sensor (a spec with dragStart) that is a child of the Shape's nearest group that has one; the ray is expressed in that group's
   frame as it was at the press. A press that starts a drag does not orbit the camera. */
{
  const _setWorld = Body.prototype.setWorld;
  const live = {}; R.bridge.live = (k) => (live[k] ||= new Set());     // nodes of one kind in the world on screen (key sensors), emptied when the world is replaced
  Body.prototype.setWorld = function (...a) { R.bridge.body = this; for (const s of Object.values(live)) s.clear(); this.texCache.clear(); /* node ids restart in every world: a texture cached under an old id would be handed to the new world */ return _setWorld.apply(this, a); };
  const _click = Body.prototype.click;
  Body.prototype.click = function (x, y) {          // a click under an Anchor follows it, the nearest Anchor wins
    _click.call(this, x, y);
    const hit = this.pickMesh(x, y); if (!hit || !hit.hit) return;
    for (const g of (hit.pickedMesh.metadata && hit.pickedMesh.metadata.chain) || []) if (g.type === 'Anchor') { if (g.f.load !== false) R.bridge.specs.get('Anchor').activate(this, g); break; }
  };
  const _init = Body.prototype.init;
  Body.prototype.init = async function (...a) { const r = await _init.apply(this, a); R.bridge.pointerInit(this); R.bridge.keyInit(this); return r; };
  /* key sensors: the canvas takes focus (tabindex), key down and up go to every enabled KeySensor and StringSensor of the world, losing focus lets go of held modifiers */
  R.bridge.keyInit = (body) => {
    const cv = body.canvas; if (cv.tabIndex < 0) cv.tabIndex = 0; cv.style.outline = 'none';
    const each = (fn, e) => { let used = false; for (const n of live.key || []) if (R.bridge.specs.get(n.type)[fn](n, e)) used = true; return used; };
    cv.addEventListener('keydown', (e) => { if (each('keydown', e)) e.preventDefault(); });
    cv.addEventListener('keyup', (e) => { if (each('keyup', e)) e.preventDefault(); });
    cv.addEventListener('blur', () => { for (const n of live.key || []) R.bridge.specs.get(n.type).release(n); });
  };
  R.bridge.pointerInit = (body) => {
    const cv = body.canvas, V = BABYLON.Vector3; let drag = null;
    const ray = (e, inv) => {
      const r = cv.getBoundingClientRect(), sx = body.engine.getRenderWidth() / r.width, sy = body.engine.getRenderHeight() / r.height;
      const pr = body.scene.createPickingRay((e.clientX - r.left) * sx, (e.clientY - r.top) * sy, BABYLON.Matrix.IdentityReadOnly, body.scene.activeCamera);
      const o = V.TransformCoordinates(pr.origin, inv), d = V.TransformNormal(pr.direction, inv);
      return { o: [o.x, o.y, o.z], d: [d.x, d.y, d.z] };
    };
    cv.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      const hit = body.pickMesh(e.clientX, e.clientY); if (!hit || !hit.hit) return;
      for (const g of (hit.pickedMesh.metadata && hit.pickedMesh.metadata.chain) || []) {
        const sens = (g.f.children || []).filter((c) => { const s = R.bridge.specs.get(c.type); return s && s.dragStart && c.f.enabled !== false; });
        if (!sens.length) continue;
        const rec = body.rec.get(g.id), inv = (rec && rec.tn ? rec.tn.computeWorldMatrix(true) : BABYLON.Matrix.Identity()).clone().invert();
        const rl = ray(e, inv), hp = V.TransformCoordinates(hit.pickedPoint, inv);
        drag = { sens, inv }; cv.setPointerCapture(e.pointerId); e.stopImmediatePropagation();
        for (const s of sens) R.bridge.drag.start(s, { o: rl.o, d: rl.d, hit: [hp.x, hp.y, hp.z] });
        return;
      }
    }, true);
    cv.addEventListener('pointermove', (e) => { if (!drag) return; e.stopImmediatePropagation(); const rl = ray(e, drag.inv); for (const s of drag.sens) R.bridge.drag.move(s, { o: rl.o, d: rl.d }); }, true);
    const up = (e) => { if (!drag) return; e.stopImmediatePropagation(); const d = drag; drag = null; for (const s of d.sens) R.bridge.drag.end(s); };
    cv.addEventListener('pointerup', up, true); cv.addEventListener('pointercancel', up, true);
  };
}

/* geometry sets: a bridge geometry node (spec.geometry) is drawn through the same path as IndexedTriangleSet. makeMesh hands the stock code a stand-in whose type is IndexedTriangleSet and
   which remembers the real node (__src); geometryData reads the vertex data from the spec instead. The data is cached by node id, keyed on the versions of the node and its coord/normal/color/texCoord. */
{
  const specOf = (g) => { const s = R.bridge.specs.get(g.__src ? g.__src.type : g.type); return s && s.geometry ? s : null; };
  const _data = Body.prototype.geometryData;
  Body.prototype.geometryData = function (g) {
    const s = specOf(g); if (!s) return _data.call(this, g);
    const f = g.f, ver = [g, f.coord, f.normal, f.color, f.texCoord].map((x) => (x ? x.version || 0 : -1)).join('.');
    const hit = this.geoCache.get(g.id); if (hit && hit.ver === ver) return hit;
    const out = Object.assign({ ver }, s.geometry(g.__src || g, this)); this.geoCache.set(g.id, out); return out;
  };
  const _make = Body.prototype.makeMesh;
  Body.prototype.makeMesh = function (shape, g, spec, pass) {
    if (!g.__src && specOf(g)) { const gp = Object.create(g, { type: { value: 'IndexedTriangleSet' }, __src: { value: g } }); return _make.call(this, shape, gp, spec, pass); }
    return _make.call(this, shape, g, spec, pass);
  };
  Body.prototype.regeo = function (x) {            // drop the cached data and Babylon geometry of one geometry node and rebuild the shapes that use it
    this.geoCache.delete(x.id);
    for (const key of [x.id + 'c', x.id + 'n']) { const c = this.geoCache.get(key); if (c) { c.geo.dispose(); this.geoCache.delete(key); } }
    for (const r of this.rec.values()) if (r.node && r.node.type === 'Shape' && r.node.f.geometry === x && r.tn) this.rebuildShapeIn(r);
  };
  const _gc = Body.prototype.geometryChanged;
  Body.prototype.geometryChanged = function (n) {
    _gc.call(this, n);
    for (const x of this.world.nodes) if (specOf(x) && (x.f.color === n || x.f.coord === n || x.f.normal === n || x.f.texCoord === n)) this.regeo(x);
  };
}

/* line geometry: a bridge node with spec.lines(g) -> { coord (flat xyz, or null for the node's own coord), coordIndex } is drawn by the body's screen-width line path, the one IndexedLineSet uses.
   The stock code gets a stand-in whose type is IndexedLineSet. */
{
  const linesSpec = (g) => { const s = R.bridge.specs.get(g.type); return s && s.lines ? s : null; };
  const standIn = (g, s) => {
    const L = s.lines(g), coord = L.coord ? { id: g.id + 'p', type: 'Coordinate', version: g.version || 0, f: { point: L.coord } } : g.f.coord;
    return Object.create(g, { type: { value: 'IndexedLineSet' }, __src: { value: g }, f: { value: Object.assign({}, g.f, { coord, coordIndex: L.coordIndex }) } });
  };
  const _mats = Body.prototype.materialsFor;
  Body.prototype.materialsFor = function (shape, g, app) { const s = linesSpec(g); return _mats.call(this, shape, s ? standIn(g, s) : g, app); };
  const _make = Body.prototype.makeMesh;
  Body.prototype.makeMesh = function (shape, g, spec, pass) { const s = linesSpec(g); return _make.call(this, shape, s ? standIn(g, s) : g, spec, pass); };
  const _gc = Body.prototype.geometryChanged;
  Body.prototype.geometryChanged = function (n) {
    _gc.call(this, n);
    for (const x of this.world.nodes) if (linesSpec(x) && (x.f.color === n || x.f.coord === n)) this.regeo(x);
  };
}

/* points: a bridge node with spec.points(g) -> flat xyz is drawn as screen-sized round points (camera-facing quads, R.bridge.pointSize px across, default 2) in the Material's emissive colour (unlit). WebGPU has no point size. */
{
  const pointsSpec = (g) => { const s = R.bridge.specs.get(g.type); return s && s.points ? s : null; };
  const _mats = Body.prototype.materialsFor;
  Body.prototype.materialsFor = function (shape, g, app) {
    if (!pointsSpec(g)) return _mats.call(this, shape, g, app);
    const mat = app && app.f.material; return [{ kind: 'points', mat, deps: [g, mat].filter(Boolean) }];
  };
  const _make = Body.prototype.makeMesh;
  Body.prototype.makeMesh = function (shape, g, spec, pass) {
    const s = pointsSpec(g); if (!s) return _make.call(this, shape, g, spec, pass);
    const P = s.points(g), n = P.length / 3, mesh = new BABYLON.Mesh((shape.def || 'points') + '-pts', this.scene), vd = new BABYLON.VertexData();
    // one camera-facing quad per point (WebGPU has no point size): 4 corners that share the point's position and differ in uv (+-1), sized in pixels in the vertex shader like the line ribbons
    const pos = new Float32Array(n * 12), uv = new Float32Array(n * 8), idx = new Uint32Array(n * 6);
    for (let i = 0; i < n; i++) for (let k = 0; k < 4; k++) {
      const o = i * 4 + k; pos.set([P[i * 3], P[i * 3 + 1], P[i * 3 + 2]], o * 3); uv[o * 2] = k & 1 ? 1 : -1; uv[o * 2 + 1] = k & 2 ? 1 : -1;
    }
    for (let i = 0; i < n; i++) idx.set([i * 4, i * 4 + 1, i * 4 + 3, i * 4, i * 4 + 3, i * 4 + 2], i * 6);
    vd.positions = pos; vd.indices = idx; vd.uvs = uv; vd.applyToMesh(mesh, false);
    BABYLON.ShaderStore.ShadersStoreWGSL['ptquadVertexShader'] = PT_VS; BABYLON.ShaderStore.ShadersStoreWGSL['ptquadFragmentShader'] = PT_FS;
    const m = new BABYLON.ShaderMaterial('pts-' + shape.id, this.scene, { vertex: 'ptquad', fragment: 'ptquad' },
      { attributes: ['position', 'uv'], uniforms: ['worldViewProjection', 'viewport', 'widthPx', 'tint', 'alpha'], shaderLanguage: BABYLON.ShaderLanguage.WGSL, needAlphaBlending: true });
    const c = spec.mat ? (spec.mat.f.emissiveColor || [1, 1, 1]) : [1, 1, 1];
    m.setVector3('tint', new BABYLON.Vector3(c[0], c[1], c[2])); m.setFloat('alpha', spec.mat ? 1 - spec.mat.f.transparency : 1); m.setVector2('viewport', new BABYLON.Vector2(320, 240));
    m.alphaMode = BABYLON.Engine.ALPHA_COMBINE; m.backFaceCulling = false; m.disableDepthWrite = true; m._lw = R.bridge.pointSize || 2; m.setFloat('widthPx', m._lw);
    mesh.material = m; mesh.alphaIndex = 5; (this.ribbons ||= []).push(m);           // the frame loop sets viewport and widthPx of every ribbon material (widthPx = _lw times the pixel ratio)
    return mesh;
  };
}
const PT_VS = `
attribute position: vec3f;
attribute uv: vec2f;
uniform worldViewProjection: mat4x4f;
uniform viewport: vec2f;
uniform widthPx: f32;
varying vUV: vec2f;
varying vD: f32;
@vertex
fn main(input: VertexInputs) -> FragmentInputs {
  let c = uniforms.worldViewProjection * vec4f(vertexInputs.position, 1.0);
  let reach = uniforms.widthPx * 0.5 + 1.0;
  vertexOutputs.position = vec4f(c.xy + vertexInputs.uv * reach * 2.0 / uniforms.viewport * c.w, c.z, c.w);
  vertexOutputs.vUV = vertexInputs.uv * reach;
  vertexOutputs.vD = uniforms.widthPx * 0.5;
}`;
const PT_FS = `
uniform tint: vec3f;
uniform alpha: f32;
varying vUV: vec2f;
varying vD: f32;
@fragment
fn main(input: FragmentInputs) -> FragmentOutputs {
  let cover = clamp(fragmentInputs.vD + 0.5 - length(fragmentInputs.vUV), 0.0, 1.0);
  fragmentOutputs.color = vec4f(uniforms.tint, uniforms.alpha * cover);
}`;

/* TextureCoordinateGenerator (19775-1 18.4.7): coordinates made from the geometry. The object-space modes (COORD, SPHERE-LOCAL, SPHERE-REFLECT-LOCAL) are computed once when the geometry is built. The
   camera-space modes (SPHERE, CAMERASPACENORMAL, CAMERASPACEPOSITION, CAMERASPACEREFLECTIONVECTOR, COORD-EYE, SPHERE-REFLECT) depend on the view: they are computed from the mesh's model-view matrix before each
   frame in which the camera or the mesh moved (BR.tcg.update), so a turning camera turns the mapping. s and t are used for a 2D texture. NOISE and NOISE-EYE are not made (uv stays 0).
   Formulas: SPHERE s,t = n.x * 0.5 + 0.5, n.y * 0.5 + 0.5 (n = unit normal in camera space); CAMERASPACENORMAL and CAMERASPACEPOSITION give n and the camera-space position as they are; the reflection
   vector r = reflect(unit position, n); SPHERE-REFLECT maps r by the sphere-map formula s,t = r.x / m + 0.5, r.y / m + 0.5 with m = 2 sqrt(r.x^2 + r.y^2 + (r.z + 1)^2). */
R.bridge.tcg = {
  CAM: /^(SPHERE|CAMERASPACENORMAL|CAMERASPACEPOSITION|CAMERASPACEREFLECTIONVECTOR|COORD-EYE|SPHERE-REFLECT)$/,
  LOCAL: /^(COORD|SPHERE-LOCAL|SPHERE-REFLECT-LOCAL)$/,
  fill(mode, uv, i, p, n) {                 // p, n: position and unit normal in the space of the mode
    const reflect = () => { const l = Math.hypot(p[0], p[1], p[2]) || 1, e = [p[0] / l, p[1] / l, p[2] / l], d = e[0] * n[0] + e[1] * n[1] + e[2] * n[2]; return [e[0] - 2 * d * n[0], e[1] - 2 * d * n[1], e[2] - 2 * d * n[2]]; };
    const sphereMap = (r) => { const m = 2 * Math.sqrt(r[0] * r[0] + r[1] * r[1] + (r[2] + 1) * (r[2] + 1)) || 1; uv[i * 2] = r[0] / m + 0.5; uv[i * 2 + 1] = r[1] / m + 0.5; };
    switch (mode) {
      case 'SPHERE': case 'SPHERE-LOCAL': uv[i * 2] = n[0] * 0.5 + 0.5; uv[i * 2 + 1] = n[1] * 0.5 + 0.5; break;
      case 'CAMERASPACENORMAL': uv[i * 2] = n[0]; uv[i * 2 + 1] = n[1]; break;
      case 'CAMERASPACEPOSITION': case 'COORD-EYE': case 'COORD': uv[i * 2] = p[0]; uv[i * 2 + 1] = p[1]; break;
      case 'CAMERASPACEREFLECTIONVECTOR': { const r = reflect(); uv[i * 2] = r[0]; uv[i * 2 + 1] = r[1]; break; }
      case 'SPHERE-REFLECT': case 'SPHERE-REFLECT-LOCAL': sphereMap(reflect()); break;
      default: uv[i * 2] = 0; uv[i * 2 + 1] = 0;
    }
  },
  update(body, mesh, g) {                  // camera-space modes: one pass over the vertices with the current model-view matrix
    const T = (g.__src || g).f.texCoord, d = body.geometryData(g); if (!T || !d || !d.pos) return;
    const mode = String(T.f.mode || 'SPHERE').toUpperCase(); if (!R.bridge.tcg.CAM.test(mode)) return;
    const wv = mesh.getWorldMatrix().multiply(body.scene.activeCamera.getViewMatrix()), key = wv.m.join(',') + mode; if (mesh._tcgKey === key) return; mesh._tcgKey = key;
    const n = d.pos.length / 3, uv = new Float32Array(n * 2), m = wv.m, nrm = d.nrm || (() => { const a = new Float32Array(d.pos.length); BABYLON.VertexData.ComputeNormals(d.pos, d.idx, a); return a; })();
    for (let i = 0; i < n; i++) {
      const x = d.pos[i * 3], y = d.pos[i * 3 + 1], z = d.pos[i * 3 + 2], a = nrm[i * 3], b = nrm[i * 3 + 1], c = nrm[i * 3 + 2];
      const p = [x * m[0] + y * m[4] + z * m[8] + m[12], x * m[1] + y * m[5] + z * m[9] + m[13], x * m[2] + y * m[6] + z * m[10] + m[14]];
      let nv = [a * m[0] + b * m[4] + c * m[8], a * m[1] + b * m[5] + c * m[9], a * m[2] + b * m[6] + c * m[10]]; const l = Math.hypot(nv[0], nv[1], nv[2]) || 1; nv = [nv[0] / l, nv[1] / l, nv[2] / l];
      R.bridge.tcg.fill(mode, uv, i, p, nv);
    }
    d.uv = uv; mesh.updateVerticesData(BABYLON.VertexBuffer.UVKind, uv);
  },
};
{
  const _data = Body.prototype.geometryData;
  Body.prototype.geometryData = function (g) {
    const d = _data.call(this, g), T = (g.f || {}).texCoord;
    if (!T || T.type !== 'TextureCoordinateGenerator' || !d || !d.pos) return d;
    const mode = String(T.f.mode || 'SPHERE').toUpperCase(), key = (T.version || 0) + '/' + mode; if (d._gen === key) return d;
    let nrm = d.nrm;
    if (!nrm) { nrm = new Float32Array(d.pos.length); BABYLON.VertexData.ComputeNormals(d.pos, d.idx, nrm); }
    if (!R.bridge.tcg.CAM.test(mode) && !R.bridge.tcg.LOCAL.test(mode)) this.note('TextureCoordinateGenerator mode ' + mode + ' is not made (uv left at 0)');
    const n = d.pos.length / 3, uv = new Float32Array(n * 2);
    for (let i = 0; i < n; i++) R.bridge.tcg.fill(mode, uv, i, [d.pos[i * 3], d.pos[i * 3 + 1], d.pos[i * 3 + 2]], [nrm[i * 3], nrm[i * 3 + 1], nrm[i * 3 + 2]]);   // the first frame before the camera is read: object space
    d.uv = uv; d._gen = key; return d;
  };
  const _bg = Body.prototype.babylonGeometry;
  Body.prototype.babylonGeometry = function (g, wantColor) {          // the uv buffer of a camera-space generator is rewritten every frame the view changes: it must be updatable
    const geo = _bg.call(this, g, wantColor), T = ((g.__src || g).f || {}).texCoord;
    if (T && T.type === 'TextureCoordinateGenerator' && R.bridge.tcg.CAM.test(String(T.f.mode || 'SPHERE').toUpperCase()) && !geo._tcgUpd) { const d = this.geometryData(g); if (d.uv) geo.setVerticesData(BABYLON.VertexBuffer.UVKind, d.uv, true, 2); geo._tcgUpd = true; }
    return geo;
  };
  const _mk = Body.prototype.makeMesh;
  Body.prototype.makeMesh = function (shape, g, spec, pass) {
    const mesh = _mk.call(this, shape, g, spec, pass), T = ((g.__src || g).f || {}).texCoord;
    if (mesh && T && T.type === 'TextureCoordinateGenerator' && R.bridge.tcg.CAM.test(String(T.f.mode || 'SPHERE').toUpperCase())) {
      const obs = this.scene.onBeforeRenderObservable.add(() => { if (!mesh.isDisposed()) R.bridge.tcg.update(this, mesh, g); });
      mesh.onDisposeObservable.add(() => this.scene.onBeforeRenderObservable.remove(obs));
    }
    return mesh;
  };
}

/* MultiTexture: the textures are drawn over each other on a canvas texture; texture i meets the result so far by mode[i], moved by the TextureTransform of stage i (the Appearance's
   MultiTextureTransform, or one TextureTransform for all stages). MovieTexture: a Babylon VideoTexture on the node's <video> element. */
{
  // 3x3 affine as [a b c d e f] (x' = a x + c y + e, y' = b x + d y + f); tc' = T + C + R S (tc - C)
  const mul = (m, n) => [m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1], m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3], m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5]];
  const inv = (m) => { const d = m[0] * m[3] - m[1] * m[2]; return [m[3] / d, -m[1] / d, -m[2] / d, m[0] / d, (m[2] * m[5] - m[3] * m[4]) / d, (m[1] * m[4] - m[0] * m[5]) / d]; };
  const ttMatrix = (t) => { const f = t.f, c = f.center || [0, 0], s = f.scale || [1, 1], r = f.rotation || 0, T = f.translation || [0, 0], co = Math.cos(r), si = Math.sin(r);
    return mul(mul(mul([1, 0, 0, 1, T[0] + c[0], T[1] + c[1]], [co, si, -si, co, 0, 0]), [s[0], 0, 0, s[1], 0, 0]), [1, 0, 0, 1, -c[0], -c[1]]); };
  R.bridge.ttMatrix = ttMatrix;
  const _tex = Body.prototype.tex;
  Body.prototype.tex = function (node) {
    if (node && node.type === 'MovieTexture') {
      const hit = this.texCache.get(node.id); if (hit) return hit;
      if (!node._video) return null;
      const t = new BABYLON.VideoTexture('mov-' + node.id, node._video, this.scene, false, true, BABYLON.Texture.TRILINEAR_SAMPLINGMODE, { autoPlay: false, loop: false, muted: true });
      this.texCache.set(node.id, t); return t;
    }
    if (!node || node.type !== 'MultiTexture') return _tex.call(this, node);
    const hit = this.texCache.get(node.id); if (hit) return hit;
    const body = this, SZ = 256, dt = new BABYLON.DynamicTexture('mt-' + node.id, { width: SZ, height: SZ }, this.scene, true);
    const imgs = [], ctx = dt.getContext();
    const app = this.world.nodes.find((x) => x.type === 'Appearance' && x.f.texture === node), tt = app && app.f.textureTransform;
    const stageTT = (i) => !tt ? null : tt.type === 'MultiTextureTransform' ? (tt.f.textureTransform || [])[i] || null : tt;
    const OPS = { REPLACE: 'source-over', MODULATE: 'multiply', MODULATE2X: 'multiply', MODULATE4X: 'multiply', ADD: 'lighter' };
    const P = [SZ, 0, 0, -SZ, 0, SZ];                                   // uv -> canvas pixels (v up)
    dt.redraw = () => {
      ctx.globalCompositeOperation = 'source-over'; ctx.fillStyle = '#fff'; ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillRect(0, 0, SZ, SZ);
      imgs.forEach((im, i) => {
        if (!im.complete || !im.naturalWidth) return;
        const mode = String((node.f.mode || [])[i] || 'MODULATE').toUpperCase(), op = OPS[mode];
        if (!op && i) body.note('MultiTexture mode ' + mode + ' drawn as MODULATE');
        ctx.globalCompositeOperation = i === 0 ? 'source-over' : op || 'multiply';
        const t = stageTT(i);
        if (t) {                                                        // canvas(px) = image(Q px) with Q = P M P^-1; the image is placed by Q^-1 and tiled
          const Q = mul(mul(P, ttMatrix(t)), inv(P)), D = inv(Q), pat = ctx.createPattern(im, 'repeat');
          pat.setTransform(new DOMMatrix([D[0] * SZ / im.naturalWidth, D[1] * SZ / im.naturalWidth, D[2] * SZ / im.naturalHeight, D[3] * SZ / im.naturalHeight, D[4], D[5]]));
          ctx.fillStyle = pat; ctx.fillRect(0, 0, SZ, SZ);
        } else ctx.drawImage(im, 0, 0, SZ, SZ);
        const extra = mode === 'MODULATE2X' ? 1 : mode === 'MODULATE4X' ? 3 : 0;
        for (let k = 0; k < extra && i; k++) { ctx.globalCompositeOperation = 'lighter'; ctx.drawImage(ctx.canvas, 0, 0); }
      });
      ctx.globalCompositeOperation = 'source-over'; dt.update();
    };
    for (const t of node.f.texture || []) {
      const u = t.f.url && t.f.url[0]; if (!u) continue;
      const im = new Image(); im.crossOrigin = 'anonymous'; im.onload = dt.redraw; im.src = this.resolve(u, this.baseUrl); imgs.push(im);
    }
    dt.redraw(); this.texCache.set(node.id, dt); return dt;
  };
}

/* TwoSidedMaterial: two passes of the same geometry, front faces then back faces, each with its own colours */
{
  const _mats = Body.prototype.materialsFor;
  Body.prototype.materialsFor = function (shape, g, app) {
    const mat = app && app.f.material;
    if (!mat || mat.type !== 'TwoSidedMaterial') return _mats.call(this, shape, g, app);
    return (g.f.solid === true ? [false] : [false, true]).map((back) => ({ kind: 'twosided', mat, back, deps: [mat] }));   // solid = TRUE: the back faces are culled (X_ITE 16.6.0 does the same with a TwoSidedMaterial)
  };
  const _mm = Body.prototype.makeMaterial;
  Body.prototype.makeMaterial = function (shape, g, spec, mesh) {
    if (spec.kind !== 'twosided') return _mm.call(this, shape, g, spec, mesh);
    const f = spec.mat.f, sep = f.separateBackColor, B = spec.back && sep;
    const src = { f: { diffuseColor: B ? f.backDiffuseColor : f.diffuseColor, emissiveColor: B ? f.backEmissiveColor : f.emissiveColor, transparency: B ? f.backTransparency : f.transparency, specularColor: B ? f.backSpecularColor : f.specularColor, shininess: B ? f.backShininess : f.shininess } };
    const m = new BABYLON.StandardMaterial('two-' + (spec.back ? 'back-' : 'front-') + shape.id, this.scene);
    m.specularColor.set(0, 0, 0); m.backFaceCulling = true;
    let gd = null; try { gd = this.geometryData(g); } catch (e) { /* a primitive has no vertex data */ }
    // data geometry is wound counter-clockwise (X3D); Babylon's own Box, Sphere and Cylinder are wound the other way in this right-handed scene. Both passes cull the back faces of their own mesh: the back
    // pass draws a copy whose winding and normals are reversed (Babylon applies two sided lighting only to a material that does not cull, which would draw both sides).
    m.sideOrientation = gd && gd.pos ? BABYLON.Material.CounterClockWiseSideOrientation : BABYLON.Material.ClockWiseSideOrientation;
    this.refreshPhong(m, src); m._two = spec.back ? 'back' : 'front';
    return m;
  };
  const _mk2 = Body.prototype.makeMesh;
  Body.prototype.makeMesh = function (shape, g, spec, pass) {
    const mesh = _mk2.call(this, shape, g, spec, pass);
    if (mesh && spec.kind === 'twosided' && spec.back && mesh.getTotalVertices() && mesh.getIndices()) {
      mesh.makeGeometryUnique();
      const ix = Array.from(mesh.getIndices()), nr = mesh.getVerticesData(BABYLON.VertexBuffer.NormalKind);
      for (let k = 0; k + 2 < ix.length; k += 3) { const t = ix[k + 1]; ix[k + 1] = ix[k + 2]; ix[k + 2] = t; }
      mesh.setIndices(ix, mesh.getTotalVertices(), true);
      if (nr) mesh.setVerticesData(BABYLON.VertexBuffer.NormalKind, Float32Array.from(nr, (v) => -v), false, 3);
    }
    return mesh;
  };
}

/* FillProperties: filled=false hides the fill; hatched=true lays a line pattern over the surface (the geometry's own texture coordinates) */
{
  const _bs = Body.prototype.buildShape;
  Body.prototype.buildShape = function (n, parent, chain) {
    const r = _bs.call(this, n, parent, chain), fp = n.f.appearance && n.f.appearance.f.fillProperties;
    if (fp && r.meshes && r.meshes.length) this.applyFill(r, fp);
    return r;
  };
  Body.prototype.applyFill = function (r, fp) {
    const f = fp.f, extra = [];
    for (const m of r.meshes) {
      if (f.filled === false) m.visibility = 0;          // not drawn but still picked, as X_ITE 16.6.0 does
      if (f.hatched !== false) {
        const SZ = 32, dt = new BABYLON.DynamicTexture('hatch-' + fp.id, { width: SZ, height: SZ }, this.scene, true), c = dt.getContext(), col = f.hatchColor || [1, 1, 1];
        const style = Math.max(1, Math.min(19, f.hatchStyle | 0)); if (style > 6) this.note('FillProperties hatchStyle ' + style + ' drawn as style 6');
        c.clearRect(0, 0, SZ, SZ); c.strokeStyle = `rgb(${Math.round(col[0] * 255)},${Math.round(col[1] * 255)},${Math.round(col[2] * 255)})`; c.lineWidth = 3;
        const line = (x0, y0, x1, y1) => { c.beginPath(); c.moveTo(x0, y0); c.lineTo(x1, y1); c.stroke(); };
        const H = style === 1 || style === 5, V = style === 2 || style === 5, U = style === 3 || style >= 6, D = style === 4 || style >= 6;
        if (H) line(0, SZ / 2, SZ, SZ / 2); if (V) line(SZ / 2, 0, SZ / 2, SZ);
        if (U) { line(0, SZ, SZ, 0); line(-SZ / 2, SZ / 2, SZ / 2, -SZ / 2); line(SZ / 2, SZ * 1.5, SZ * 1.5, SZ / 2); }
        if (D) { line(0, 0, SZ, SZ); line(SZ / 2, -SZ / 2, SZ * 1.5, SZ / 2); line(-SZ / 2, SZ / 2, SZ / 2, SZ * 1.5); }
        dt.hasAlpha = true; dt.update(); dt.wrapU = dt.wrapV = BABYLON.Texture.WRAP_ADDRESSMODE; dt.uScale = dt.vScale = 6;
        const o = m.clone(m.name + '-hatch'); o.parent = m.parent; o.isPickable = false;
        const hm = new BABYLON.StandardMaterial('hatchmat-' + fp.id, this.scene);
        hm.diffuseTexture = dt; hm.useAlphaFromDiffuseTexture = true; hm.disableLighting = true; hm.emissiveColor.set(1, 1, 1); hm.backFaceCulling = false; hm.zOffset = -2; hm.transparencyMode = BABYLON.Material.MATERIAL_ALPHABLEND;
        o.material = hm; o.metadata = { hatch: true }; o.isVisible = true; extra.push(o);
      }
    }
    r.hatch = extra;
  };
}

/* FogCoordinate: a shape whose geometry has a fogCoord gets its fog overlay (BR.fog.coord) */
{
  const _bs = Body.prototype.buildShape;
  Body.prototype.buildShape = function (n, parent, chain) { const r = _bs.call(this, n, parent, chain); BR.fog.coord(this, n, r); return r; };
}

{ // a rebuilt Shape also drops its hatch overlay meshes
  const _rb = Body.prototype.rebuildShapeIn;
  Body.prototype.rebuildShapeIn = function (r) { (r.hatch || []).forEach((m) => m.dispose(false, true)); r.hatch = []; return _rb.call(this, r); };
}

/* OrthoViewpoint: the camera goes orthographic while one is bound. The pose gets an `ortho` record ({ f: fieldOfView, near, far, scale }), applyCamera sets the Babylon camera's mode and its
   left/right/top/bottom from it, and the user's zoom changes the record's scale (moving along the view axis changes nothing in an orthographic view). */
{
  const B = Body.prototype, ORTHO = (v) => v && v.type === 'OrthoViewpoint';
  const _pose = B.vpPose;
  B.vpPose = function (vp) { const p = _pose.call(this, vp); if (ORTHO(vp)) { p.fov = 0.7854; p.ortho = { f: Array.from(vp.f.fieldOfView), near: vp.f.nearDistance, far: vp.f.farDistance, scale: 1 }; } return p; };
  const _bind = B.bindViewpoint;
  B.bindViewpoint = function (vp, on) {
    const prev = this.bound; _bind.call(this, vp, on);
    if (on && (ORTHO(vp) || ORTHO(prev))) { this.tr = null; this.pose = this.vpPose(vp); this.started = true; this.applyCamera(); }
  };
  const _apply = B.applyCamera;
  B.applyCamera = function () {
    _apply.call(this);
    const c = this.cam, o = this.pose && this.pose.ortho, C = BABYLON.Camera;
    if (!o) { if (c.mode !== C.PERSPECTIVE_CAMERA) c.mode = C.PERSPECTIVE_CAMERA; return; }
    const w = this.canvas.clientWidth || 1, h = this.canvas.clientHeight || 1, ratio = (w * c.viewport.width) / (h * c.viewport.height), f = o.f, s = o.scale || 1;
    const x0 = (f[0] ?? -1) * s, y0 = (f[1] ?? -1) * s, x1 = (f[2] ?? 1) * s, y1 = (f[3] ?? 1) * s, sx = x1 - x0, sy = y1 - y0;
    c.mode = C.ORTHOGRAPHIC_CAMERA;
    if (ratio > sx / sy) { const cx = (x0 + x1) / 2, hw = sy * ratio / 2; c.orthoLeft = cx - hw; c.orthoRight = cx + hw; c.orthoBottom = y0; c.orthoTop = y1; }
    else { const cy = (y0 + y1) / 2, hh = sx / ratio / 2; c.orthoLeft = x0; c.orthoRight = x1; c.orthoBottom = cy - hh; c.orthoTop = cy + hh; }
    c.minZ = o.near > 0 ? o.near : 0.1; c.maxZ = o.far > 0 ? o.far : 1e4;
  };
  const _zoom = B.zoom;
  B.zoom = function (k) { const o = this.pose && this.pose.ortho; if (!o) return _zoom.call(this, k); o.scale = Math.min(50, Math.max(0.02, (o.scale || 1) * k)); this.applyCamera(); };
  const _pan = B.pan;
  B.pan = function (dx, dy) {
    const p = this.pose, c = this.cam, o = p && p.ortho; if (!o) return _pan.call(this, dx, dy);
    const u = (c.orthoTop - c.orthoBottom) / (this.canvas.clientHeight || 1), up = R.quat.rotate(p.q, [0, 1, 0]), right = R.quat.rotate(p.q, [1, 0, 0]);
    const t = R.v3.add(R.v3.scale(right, -dx * u), R.v3.scale(up, dy * u)); p.pos = R.v3.add(p.pos, t); p.center = R.v3.add(p.center, t); this.applyCamera();
  };
  const _sw = B.setWorld;
  B.setWorld = function (...a) {          // an OrthoViewpoint that comes first in the file is bound at load (the stock body binds nothing at load; a first Viewpoint stays as it was)
    const r = _sw.apply(this, a), w = this.world, first = w && w.nodes.find((n) => n.type === 'Viewpoint' || n.type === 'OrthoViewpoint');
    if (ORTHO(first)) this.bindViewpoint(first, true);
    return r;
  };
}

/* the page's viewpoint list: body.viewpointList() -> [{ node, path, text }] for the loaded world, with the viewer where the camera is (ViewpointGroup proximity) */
Body.prototype.viewpointList = function () { return this.world ? R.bridge.viewpoints(this.world, this.pose ? this.pose.pos : null) : []; };

/* Layers: a world that goes away takes its layer cameras with it */
{
  const _cw = Body.prototype.clearWorld;
  Body.prototype.clearWorld = function () { if (this._layers) { for (const it of this._layers.items) if (it) it.cam.dispose(); this._layers = null; this.scene.activeCameras = []; } return _cw.call(this); };
}

/* Textures that are not a plain picture. PixelTexture (2D) and PixelTexture3D / ComposedTexture3D (their first slice, since the geometry has 2D texture coordinates only) are drawn as pictures; an
   ImageCubeMapTexture or GeneratedCubeMapTexture on an Appearance makes the Shape an environment mirror: the cube sampled with the reflection of the view (Babylon reflectionTexture in cube mode). */
{
  const CUBE = { ImageCubeMapTexture: 1, GeneratedCubeMapTexture: 1 };
  const _t = Body.prototype.tex;
  Body.prototype.tex = function (node) {
    if (node) {
      if (CUBE[node.type]) return null;                 // never a flat picture
      if (node.type === 'PixelTexture' || node.type === 'PixelTexture3D') { let t = this.texCache.get(node.id); if (!t) { t = BR.tex3.make(this, node); this.texCache.set(node.id, t); } return t; }
      if (node.type === 'ComposedTexture3D') { const first = (node.f.texture || [])[0]; if (!first) return null; const t = this.tex(first); if (t && t.updateSamplingMode) t.updateSamplingMode(BABYLON.Texture.NEAREST_SAMPLINGMODE); return t; }   // a volume is read without smoothing, as X_ITE does

    }
    return _t.call(this, node);
  };
  const _mf = Body.prototype.materialsFor;
  Body.prototype.materialsFor = function (shape, g, app) {
    const t = app && app.f.texture;
    if (t && CUBE[t.type] && !(app.f.material && app.f.material.type === 'TwoSidedMaterial') && g.type !== 'Text') {
      const mat = app.f.material && app.f.material.type === 'Material' ? app.f.material : null;
      return [{ kind: 'cube', mat, tex: t, deps: [t, mat].filter(Boolean) }];
    }
    return _mf.call(this, shape, g, app);
  };
  const _mm = Body.prototype.makeMaterial;
  Body.prototype.makeMaterial = function (shape, g, spec, mesh) {
    if (spec.kind !== 'cube') return _mm.call(this, shape, g, spec, mesh);
    const m = new BABYLON.StandardMaterial('cube-' + shape.id, this.scene);
    m.specularColor.set(0, 0, 0); m.backFaceCulling = false;
    if (spec.mat) this.refreshPhong(m, spec.mat); else { m.disableLighting = true; m.diffuseColor.set(0, 0, 0); m.emissiveColor.set(0, 0, 0); }
    BR.cube.apply(this, m, spec.tex, mesh);
    if (!this._gcmHook) { this._gcmHook = true; this.scene.onBeforeRenderObservable.add(() => BR.cube.generatedFrame(this)); }
    return m;
  };
  const _cw2 = Body.prototype.clearWorld;
  Body.prototype.clearWorld = function () {
    if (this._gcm) { for (const e of this._gcm) { try { e.probe.dispose(); } catch (x) { /* already gone */ } } this._gcm.clear(); }
    for (const [k, e] of this.texCache) if (typeof k === 'string' && k.startsWith('cube:') && e.tex && !e.probe) { try { e.tex.dispose(); } catch (x) { /* already gone */ } }
    return _cw2.call(this);
  };
}

/* Headlight (Navigation, 19775-1 section 21.4.1): NavigationInfo.headlight (default TRUE, also when the world has no NavigationInfo) is a directional light that points where the camera
   looks, white, intensity 1, no ambient term. The stock body had none, so a Material shape in a world without a light was drawn black. The first NavigationInfo of the world decides
   (the bind stack of NavigationInfo is not kept by the body); a page that sets R.bridge.headlight = false keeps the older unlit look. */
R.bridge.headlight = (body) => {
  if (body._head) { body.scene.onBeforeRenderObservable.remove(body._headObs); try { body._head.dispose(); } catch (e) { /* already gone with the scene */ } body._head = null; }
  if (R.bridge.headlight.off || !body.world) return;
  const ni = body.world.nodes.find((x) => x.type === 'NavigationInfo'), l = new BABYLON.DirectionalLight('x3d-headlight', new BABYLON.Vector3(0, 0, -1), body.scene);
  l.diffuse = new BABYLON.Color3(1, 1, 1); l.specular = new BABYLON.Color3(1, 1, 1); l.intensity = 1; l.setEnabled(!ni || ni.f.headlight !== false);
  body._headObs = body.scene.onBeforeRenderObservable.add(() => { l.direction.copyFrom(body.cam.getForwardRay(1).direction); });
  body._head = l; body._headNode = ni;
};
{
  const _sw = Body.prototype.setWorld;
  Body.prototype.setWorld = function (...a) {
    for (const l of this._x3dLights || []) { try { l.dispose(); } catch (e) { /* gone with the scene */ } }
    this._x3dLights = [];
    const r = _sw.apply(this, a); R.bridge.headlight(this);
    this.scene.materials.forEach((m) => { if (m.maxSimultaneousLights !== undefined) m.maxSimultaneousLights = 8; });
    if (R.bridge.light) R.bridge.light.scope(this);
    return r;
  };
  const _ch = Body.prototype.changed;
  Body.prototype.changed = function (node, field) {
    if (node.type === 'NavigationInfo' && field === 'headlight' && this._head && node === this._headNode) this._head.setEnabled(node.f.headlight !== false);
    return _ch.call(this, node, field);
  };
  const _cw = Body.prototype.clearWorld;
  Body.prototype.clearWorld = function () { if (this._head) { this.scene.onBeforeRenderObservable.remove(this._headObs); try { this._head.dispose(); } catch (e) { /* gone with the scene */ } this._head = null; } return _cw.call(this); };
}

/* Material + texture (19775-1 17.2.2, 17.2.3). The stock body drew a picture only on shapes without a Material (unlit) or through a PhysicalMaterial; a plain Material shape ignored its texture.
   Now the Material's StandardMaterial takes the Appearance texture as its diffuse picture, multiplied with diffuseColor (X3D 4.0 and X_ITE 16.6.0: a white image leaves the colour, measured), the headlight and any other
   light shade it, emissiveColor is added. A TextureTransform (also each stage of a MultiTextureTransform on its own MultiTexture, done in the canvas) becomes the texture's matrix. The image's own alpha makes the shape see-through
   (PNG, WebP, GIF decoded once; a PixelTexture by its component count), as X_ITE does. */
{
  const _mm = Body.prototype.makeMaterial;
  const alphaOn = (m, t) => { t.hasAlpha = true; m.useAlphaFromDiffuseTexture = true; m.transparencyMode = BABYLON.Material.MATERIAL_ALPHABLEND; m.disableDepthWrite = false; };
  const alphaOf = (body, node, m, t) => {     // an image file is probed once for a channel that is not all 255; a pixel texture is known by its component count
    if (node._alphaProbe === undefined) {
      if (node.type === 'PixelTexture') { const c = (node.f.image || [0, 0, 0])[2]; node._alphaProbe = c === 2 || c === 4; }
      else {
        const u = node.f.url && node.f.url[0]; node._alphaProbe = false;
        if (u && /\.(png|webp|gif|avif)(\?|$)/i.test(u)) {
          const im = new Image(); im.crossOrigin = 'anonymous';
          im.onload = () => { try { const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight; const g = c.getContext('2d'); g.drawImage(im, 0, 0); const d = g.getImageData(0, 0, c.width, c.height).data; for (let i = 3; i < d.length; i += 4) if (d[i] < 255) { node._alphaProbe = true; break; } if (node._alphaProbe) for (const mm of body.meshesOf.get(node.id) || []) if (mm.material && mm.material._x3dTex) alphaOn(mm.material, t); } catch (e) { /* tainted or unreadable: stays opaque */ } };
          im.src = body.resolve(u, body.baseUrl);
        }
      }
    }
    return node._alphaProbe;
  };
  const apply = (body, m, tn, shape) => {
    const t = body.tex(tn); if (!t) return;
    m.diffuseTexture = t; m._x3dTex = true;
    if (alphaOf(body, tn, m, t)) alphaOn(m, t); else { t.hasAlpha = false; m.useAlphaFromDiffuseTexture = false; }
    const app = shape.f.appearance, tt = app && app.f.textureTransform;
    if (tt && tt.type === 'TextureTransform' && tn.type !== 'MultiTexture') {
      const a = R.bridge.ttMatrix(tt); const M = BABYLON.Matrix.FromArray([a[0], a[1], 0, 0, a[2], a[3], 0, 0, 0, 0, 1, 0, a[4], a[5], 0, 1]);
      t.getTextureMatrix = () => M;
      (body._ttUsers ||= new Map()).set(tt.id, tt);
    }
  };
  Body.prototype.makeMaterial = function (shape, g, spec, mesh) {
    const m = _mm.call(this, shape, g, spec, mesh);
    if ((spec.kind === 'phong') && m instanceof BABYLON.StandardMaterial && g.type !== 'Text' && g.type !== 'IndexedLineSet') {   // a Color node replaces diffuseColor (19775-1 17.2.2.1), Babylon multiplies the two: the colours are the whole diffuse
      let d = null; try { d = this.geometryData(g); } catch (e) { /* geometry without vertex data */ }
      if (d && d.col) { m._vcol = true; m.diffuseColor.set(1, 1, 1); }
    }
    if ((spec.kind === 'phong') && m instanceof BABYLON.StandardMaterial) { const a = shape.f.appearance, tn = a && a.f.texture; if (tn && g.type !== 'Text') { apply(this, m, tn, shape); const l = this.meshesOf.get(tn.id) || []; if (mesh) { l.push(mesh); this.meshesOf.set(tn.id, l); } } }
    return m;
  };
  const _rp = Body.prototype.refreshPhong;
  Body.prototype.refreshPhong = function (m, mat) {
    const r = _rp.call(this, m, mat); if (m._vcol) m.diffuseColor.set(1, 1, 1);
    const f = mat.f;   // Phong specular (19775-1 17.2.2.4): specularColor * (N . H) ^ (shininess * 128); the stock body drew none
    const sc = f.specularColor, sh = f.shininess;
    if (sc) { m.specularColor.set(sc[0], sc[1], sc[2]); m.specularPower = Math.max(1, (sh === undefined ? 0.2 : sh) * 128); }
    return r;
  };
  const _ch = Body.prototype.changed;
  Body.prototype.changed = function (node, field) {
    if (node.type === 'TextureTransform') { for (const r of Array.from(this.rec.values())) { const a = r.node && r.node.type === 'Shape' && r.node.f.appearance; if (a && a.f.textureTransform === node && r.tn) this.rebuildShapeIn(r); } return; }
    return _ch.call(this, node, field);
  };
}

/* The first Viewpoint of a world is bound at load (19775-1 23.4.1: the first Viewpoint node found in the file). The stock body kept its default pose (0 0 10) and bound nothing until a script or a
   ViewpointGroup asked, so a world whose Viewpoint is at z = 12 was drawn from z = 10. An OrthoViewpoint that comes first is bound by its own code above. R.bridge.bindFirstViewpoint = false keeps the
   older behaviour for a page built against it. */
{
  const _sw = Body.prototype.setWorld;
  Body.prototype.setWorld = function (...a) {
    const r = _sw.apply(this, a), w = this.world;
    if (R.bridge.bindFirstViewpoint !== false && w) { const first = w.nodes.find((n) => n.type === 'Viewpoint' || n.type === 'OrthoViewpoint'); if (first && first.type === 'Viewpoint' && !first.f.isBound) { this.started = false; this.bindViewpoint(first, true); } }
    return r;
  };
}

/* ColorRGBA on the geometry sets: the alpha of the vertex colours becomes Babylon vertex alpha (the mesh is blended, sorted with the other transparent shapes), times 1 - the Material's transparency. */
{
  const _bg = Body.prototype.babylonGeometry;
  Body.prototype.babylonGeometry = function (g, wantColor) {
    const geo = _bg.call(this, g, wantColor), d = this.geometryData(g);
    if (d && d.alpha && d.col) { const rgba = geo.getVerticesData(BABYLON.VertexBuffer.ColorKind); if (rgba) { const c = Float32Array.from(rgba); for (let i = 0; i < d.alpha.length; i++) c[i * 4 + 3] = d.alpha[i]; geo.setVerticesData(BABYLON.VertexBuffer.ColorKind, c, true, 4); } }
    return geo;
  };
  const _mk = Body.prototype.makeMesh;
  Body.prototype.makeMesh = function (shape, g, spec, pass) {
    const mesh = _mk.call(this, shape, g, spec, pass);
    if (mesh && spec.kind === 'phong') { let d = null; try { d = this.geometryData(g); } catch (e) { /* no vertex data */ } if (d && d.alpha) { mesh.hasVertexAlpha = true; if (mesh.material) { mesh.material.transparencyMode = BABYLON.Material.MATERIAL_ALPHABLEND; mesh.material.disableDepthWrite = true; } mesh.alphaIndex = 1; } }
    return mesh;
  };
}

/* Line quality. The stock ribbon (the screen-width line behind IndexedLineSet, LineSet, Arc2D, Circle2D, Polyline2D) is a quad exactly widthPx wide with no edge, so a 1 px line missed pixel
   centres and drew as dashes on the CPU rasteriser. This version widens the quad by one pixel each side and fades the coverage over the outer pixel (distance to the line centre against half
   the width, in pixels), which is what the MSAA lines of X_ITE show; width, colour, tint and alpha are the stock uniforms, so every existing caller keeps working. The shader sources are swapped
   in under the stock names (the stock makeRibbon writes them on every call, the accessor below ignores that write). */
{
  const VS = `
attribute position: vec3f;
attribute other: vec3f;
attribute color: vec4f;
attribute uv: vec2f;
uniform worldViewProjection: mat4x4f;
uniform viewport: vec2f;
uniform widthPx: f32;
uniform tint: vec3f;
varying vC: vec4f;
varying vEdge: f32;
varying vHalf: f32;
@vertex
fn main(input: VertexInputs) -> FragmentInputs {
  let a = uniforms.worldViewProjection * vec4f(vertexInputs.position, 1.0);
  let b = uniforms.worldViewProjection * vec4f(vertexInputs.other, 1.0);
  let sa = a.xy / a.w * uniforms.viewport * 0.5;
  let sb = b.xy / max(b.w, 1e-5) * uniforms.viewport * 0.5;
  var dir = sb - sa;
  let l = length(dir);
  dir = select(vec2f(1.0, 0.0), dir / l, l > 1e-6);
  let nrm = vec2f(-dir.y, dir.x);
  let half = max(uniforms.widthPx, 1.0) * 0.5;
  let reach = half + 1.0;
  let off = nrm * vertexInputs.uv.y * reach * 2.0 / uniforms.viewport;
  vertexOutputs.position = vec4f(a.xy + off * a.w, a.z, a.w);
  vertexOutputs.vC = vec4f(vertexInputs.color.rgb * uniforms.tint, vertexInputs.color.a);
  vertexOutputs.vEdge = vertexInputs.uv.y * reach;
  vertexOutputs.vHalf = half;
}`;
  const FS = `
uniform alpha: f32;
varying vC: vec4f;
varying vEdge: f32;
varying vHalf: f32;
@fragment
fn main(input: FragmentInputs) -> FragmentOutputs {
  let cover = clamp(fragmentInputs.vHalf + 0.5 - abs(fragmentInputs.vEdge), 0.0, 1.0);
  fragmentOutputs.color = vec4f(fragmentInputs.vC.rgb, uniforms.alpha * cover);
}`;
  const store = BABYLON.ShaderStore.ShadersStoreWGSL;
  for (const [k, src] of [['ribbonVertexShader', VS], ['ribbonFragmentShader', FS]]) Object.defineProperty(store, k, { get: () => src, set: () => {}, configurable: true, enumerable: true });
}

/* Particle systems are not meshes: a world that goes away takes its Babylon particle systems and dot observers with it. */
{
  const _cw = Body.prototype.clearWorld;
  Body.prototype.clearWorld = function () {
    for (const r of this.rec.values()) if (r.dotObs) this.scene.onBeforeRenderObservable.remove(r.dotObs);
    this.scene.particleSystems.slice().forEach((p) => p.dispose());
    return _cw.call(this);
  };
}

/* Volume textures (Texturing3D): a PixelTexture3D, ComposedTexture3D or ImageTexture3D on an Appearance is a Babylon RawTexture3D sampled by (s, t, r) from the geometry's 3D or 4D texture
   coordinates (TextureCoordinate3D, TextureCoordinate4D), moved by a TextureTransform3D / TextureTransformMatrix3D. Without texture coordinates the box of the geometry maps to the volume (the longest
   side is s, then t, then r, all divided by the longest side, 19775-1 18.2.2). 2D coordinates read the volume at r = 0, as before. The shader is a WGSL ShaderMaterial: texel times diffuseColor shaded by
   the headlight (N dot view axis, two sided), plus emissiveColor; alpha from the voxel and Material transparency. Other lights do not reach it (gap). */
{
  const VS = `
attribute position: vec3f;
attribute normal: vec3f;
attribute uv: vec2f;
attribute uv2: vec2f;
uniform worldViewProjection: mat4x4f;
uniform worldView: mat4x4f;
varying vN: vec3f;
varying vW: vec4f;
@vertex
fn main(input: VertexInputs) -> FragmentInputs {
  vertexOutputs.position = uniforms.worldViewProjection * vec4f(vertexInputs.position, 1.0);
  vertexOutputs.vN = (uniforms.worldView * vec4f(vertexInputs.normal, 0.0)).xyz;
  vertexOutputs.vW = vec4f(vertexInputs.uv, vertexInputs.uv2);
}`;
  const FS = `
var volSampler: sampler;
var vol: texture_3d<f32>;
uniform texMat: mat4x4f;
uniform diffuse: vec3f;
uniform emissive: vec3f;
uniform alpha: f32;
uniform headlight: f32;
uniform flipT: f32;
varying vN: vec3f;
varying vW: vec4f;
@fragment
fn main(input: FragmentInputs) -> FragmentOutputs {
  let q = select(1.0, fragmentInputs.vW.w, abs(fragmentInputs.vW.w) > 1e-6);
  let tt = select(fragmentInputs.vW.y, 1.0 - fragmentInputs.vW.y, uniforms.flipT > 0.5);
  let p = (uniforms.texMat * vec4f(fragmentInputs.vW.x / q, tt / q, fragmentInputs.vW.z / q, 1.0)).xyz;
  let t = textureSample(vol, volSampler, p);
  let n = normalize(fragmentInputs.vN);
  let lit = select(1.0, abs(n.z), uniforms.headlight > 0.5);
  fragmentOutputs.color = vec4f(t.rgb * uniforms.diffuse * lit + uniforms.emissive, t.a * uniforms.alpha);
}`;
  BABYLON.ShaderStore.ShadersStoreWGSL['vol3dVertexShader'] = VS; BABYLON.ShaderStore.ShadersStoreWGSL['vol3dFragmentShader'] = FS;

  const upload = (body, node, entry, v) => {
    const old = entry.tex, tp = node.f.textureProperties, smooth = !!tp && /NICEST|AVG|LINEAR/i.test(String(tp.f.magnificationFilter || ''));   // 19775-1 18.4: the default filter is FASTEST (nearest), as X_ITE 16.6.0 draws a volume
    const t = new BABYLON.RawTexture3D(v ? v.rgba : new Uint8Array(4), v ? v.w : 1, v ? v.h : 1, v ? v.d : 1, BABYLON.Constants.TEXTUREFORMAT_RGBA, body.scene, false, false, smooth ? BABYLON.Texture.BILINEAR_SAMPLINGMODE : BABYLON.Texture.NEAREST_SAMPLINGMODE);
    t.wrapU = node.f.repeatS ? BABYLON.Texture.WRAP_ADDRESSMODE : BABYLON.Texture.CLAMP_ADDRESSMODE; t.wrapV = node.f.repeatT ? BABYLON.Texture.WRAP_ADDRESSMODE : BABYLON.Texture.CLAMP_ADDRESSMODE; t.wrapR = node.f.repeatR ? BABYLON.Texture.WRAP_ADDRESSMODE : BABYLON.Texture.CLAMP_ADDRESSMODE;
    entry.tex = t; entry.ready = !!v; entry.alpha = !!v && (() => { for (let i = 3; i < v.rgba.length; i += 4) if (v.rgba[i] < 255) return true; return false; })();
    for (const m of entry.mats) { m.setTexture('vol', t); m._blend = entry.alpha || m._tr; }
    if (old) setTimeout(() => { try { old.dispose(); } catch (e) { /* gone */ } }, 100);
  };
  Body.prototype.volTexture = function (node, mat) {
    const key = 'vol:' + node.id; let e = this.texCache.get(key);
    if (!e) {
      e = { tex: null, mats: new Set(), ready: false }; this.texCache.set(key, e); upload(this, node, e, null);
      BR.vol.data(this, node, (v) => { if (this.texCache.get(key) === e) upload(this, node, e, v); });
    }
    e.mats.add(mat); mat.setTexture('vol', e.tex); return e;
  };
  BR.vol.reload = (body, node) => { const e = body.texCache.get('vol:' + node.id); if (!e) return; BR.vol.data(body, node, (v) => upload(body, node, e, v)); };
  const _mf = Body.prototype.materialsFor;
  Body.prototype.materialsFor = function (shape, g, app) {
    const t = app && app.f.texture;
    if (t && BR.vol.is3D(t) && !['Text', 'IndexedLineSet'].includes(g.type) && !(R.bridge.specs.get(g.type) || {}).points && !(R.bridge.specs.get(g.type) || {}).lines) {
      const mat = app.f.material && /^(Material|PhysicalMaterial|UnlitMaterial)$/.test(app.f.material.type) ? app.f.material : null;
      return [{ kind: 'vol', mat, tex: t, tt: app.f.textureTransform, deps: [t, mat, app.f.textureTransform].filter(Boolean) }];
    }
    return _mf.call(this, shape, g, app);
  };
  const _mm = Body.prototype.makeMaterial;
  Body.prototype.makeMaterial = function (shape, g, spec, mesh) {
    if (spec.kind !== 'vol') return _mm.call(this, shape, g, spec, mesh);
    const m = new BABYLON.ShaderMaterial('vol-' + shape.id, this.scene, { vertex: 'vol3d', fragment: 'vol3d' },
      { attributes: ['position', 'normal', 'uv', 'uv2'], uniforms: ['worldViewProjection', 'worldView', 'texMat', 'diffuse', 'emissive', 'alpha', 'headlight', 'flipT'], samplers: ['vol'], shaderLanguage: BABYLON.ShaderLanguage.WGSL, needAlphaBlending: true });
    const f = spec.mat ? spec.mat.f : null, dc = f ? (f.diffuseColor || f.baseColor || f.unlitColor || [1, 1, 1]) : [1, 1, 1], ec = f && f.emissiveColor && spec.mat.type !== 'PhysicalMaterial' ? f.emissiveColor : [0, 0, 0];
    m.setVector3('diffuse', new BABYLON.Vector3(spec.mat ? dc[0] : 1, spec.mat ? dc[1] : 1, spec.mat ? dc[2] : 1)); m.setVector3('emissive', new BABYLON.Vector3(ec[0], ec[1], ec[2]));
    m.setFloat('alpha', f ? 1 - (f.transparency || 0) : 1); m.setFloat('headlight', spec.mat && spec.mat.type !== 'UnlitMaterial' ? 1 : 0);
    let gd = null; try { gd = this.geometryData(g); } catch (e) { /* a primitive has no vertex data */ }
    m.setFloat('flipT', gd && gd.pos ? 0 : 1);       // Box, Sphere and Cylinder keep Babylon's own uv, whose v runs the other way from the pixel rows of a volume
    m.setMatrix('texMat', BABYLON.Matrix.FromArray(BR.vol.matrix(spec.tt)));
    m.alphaMode = BABYLON.Engine.ALPHA_COMBINE; m.backFaceCulling = false; m._vol = true; m._tr = !!f && (f.transparency || 0) > 0; m._blend = m._tr;
    m.needAlphaBlending = () => !!m._blend;     // an opaque volume writes depth (Babylon draws a blended mesh without), so the far faces of a box do not paint over the near one
    this.volTexture(spec.tex, m);
    return m;
  };
  /* texture coordinates: 3D / 4D lists read with their own stride (the stock reader code reads two numbers per coordinate), default box mapping, and a second UV set for r and q */
  const _gd = Body.prototype.geometryData;
  Body.prototype.geometryData = function (g) {
    const d = _gd.call(this, g); if (!d || !d.pos) return d;
    const f = (g.__src || g).f || {}, T = f.texCoord, tcw = BR.tcWidth(T);
    if (d._uvw !== undefined || d.uvw) return d;
    const need = BR.vol && (this._volAny ||= this.world.nodes.some((x) => x.type === 'Appearance' && BR.vol.is3D(x.f.texture)));
    if (!need && tcw === 2) return d;
    const n = d.pos.length / 3, uvw = new Float32Array(n * 4), uv = new Float32Array(n * 2);
    if (tcw > 2) {
      const P = T.f.point, src = g.__src || g; let ix = null;
      if (src.type === 'IndexedFaceSet') { ix = []; const ci = f.coordIndex, TI = f.texCoordIndex && f.texCoordIndex.length ? f.texCoordIndex : ci; let face = []; const fl = () => { if (face.length >= 3) ix.push(...face); face = []; }; for (let i = 0; i < ci.length; i++) { if (ci[i] < 0) fl(); else face.push(TI[i]); } fl(); }
      for (let i = 0; i < n; i++) { const k = (ix ? ix[i] : i) * tcw; uv[i * 2] = P[k]; uv[i * 2 + 1] = P[k + 1]; uvw.set([P[k], P[k + 1], P[k + 2], tcw > 3 ? P[k + 3] : 1], i * 4); }
    } else if (!T && !(d.uv && ['Box', 'Sphere', 'Cylinder', 'Cone'].includes((g.__src || g).type)) && !(g.__src && g.__src.type !== 'IndexedFaceSet' && R.bridge.specs.get(g.__src.type))) {      // no texture coordinates: the box of the geometry
      const lo = [1e30, 1e30, 1e30], hi = [-1e30, -1e30, -1e30]; for (let i = 0; i < n; i++) for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], d.pos[i * 3 + k]); hi[k] = Math.max(hi[k], d.pos[i * 3 + k]); }
      const size = [0, 1, 2].map((k) => hi[k] - lo[k]), ord = [0, 1, 2].sort((a, b) => size[b] - size[a]), L = size[ord[0]] || 1;
      for (let i = 0; i < n; i++) { const c = [0, 1, 2].map((k) => (d.pos[i * 3 + k] - lo[k]) / L); uv[i * 2] = c[ord[0]]; uv[i * 2 + 1] = c[ord[1]]; uvw.set([c[ord[0]], c[ord[1]], c[ord[2]], 1], i * 4); }
    } else if (d.uv) { for (let i = 0; i < n; i++) uvw.set([d.uv[i * 2], d.uv[i * 2 + 1], 0, 1], i * 4); }
    if (tcw > 2 || !T) d.uv = uv;
    d.uvw = uvw; d._uvw = true; return d;
  };
  const _bg = Body.prototype.babylonGeometry;
  Body.prototype.babylonGeometry = function (g, wantColor) {
    const geo = _bg.call(this, g, wantColor), d = this.geometryData(g);
    if (d && d.pos && d.idx && !d.nrm && !geo._rhn) {      // normals the stock code made with Babylon's left-handed rule point away from the front of a counter-clockwise face of this right-handed scene
      const nrm = new Float32Array(d.pos.length); BABYLON.VertexData.ComputeNormals(d.pos, d.idx, nrm, { useRightHandedSystem: true }); geo.setVerticesData(BABYLON.VertexBuffer.NormalKind, nrm, false, 3); geo._rhn = true;
    }
    if (d && d.uvw && !geo._uv2) { const uv2 = new Float32Array(d.uvw.length / 2); for (let i = 0; i < d.uvw.length / 4; i++) { uv2[i * 2] = d.uvw[i * 4 + 2]; uv2[i * 2 + 1] = d.uvw[i * 4 + 3]; } geo.setVerticesData(BABYLON.VertexBuffer.UV2Kind, uv2, false, 2); geo._uv2 = true; }
    return geo;
  };
}
