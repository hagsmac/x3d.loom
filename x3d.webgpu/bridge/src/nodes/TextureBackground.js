/* TextureBackground (EnvironmentalEffects level 3): TextureBackground simulates ground and sky, using vertical arrays of wraparound color values, TextureBackground can also provide backdrop texture images on all six sides of the background.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */

/* ---- the bind stack, shared by Background and TextureBackground (and used by Fog, with a stack of its own) -----------------------------------------------------------------------
   X3D keeps one stack for both node types. The first one of a world is bound at load; set_bind TRUE moves a node to the top (the one under it is unbound), set_bind FALSE takes it out
   (when it was on top, the next one down is bound again; an empty stack binds nothing). Every change of isBound also sets bindTime. Same results as X_ITE 16.6.0 step for step
   (receipts/TextureBackground.json). The stock Background only knew its first node, so its isBound and bindTime are added here (extend) and its set_bind joins the same stack. */
const BG_KINDS = ['Background', 'TextureBackground'];
BR.bg = {
  now: () => (events.ts > 1e9 ? events.ts : Date.now() / 1000),
  stack: (w, n) => (w[n.type === 'Fog' ? 'fogStack' : 'bgStack'] ||= []),      // Background and TextureBackground share one stack; Fog has its own
  set(n, on) {                      // one node changes state: the output events and the body hear about it
    n.f.isBound = on; n.f.bindTime = BR.bg.now();
    events.emit(n, 'isBound', on); events.emit(n, 'bindTime', n.f.bindTime);
    if (R.bridge.body) R.bridge.body.changed(n, 'isBound');
  },
  bind(n, on) {
    const st = BR.bg.stack(n._w, n), top = st[st.length - 1], i = st.indexOf(n);
    if (on) {
      if (top === n) return;
      if (i >= 0) st.splice(i, 1);
      st.push(n); if (top) BR.bg.set(top, false);
      BR.bg.set(n, true);
    } else if (i >= 0) {
      st.splice(i, 1);
      if (top === n) { BR.bg.set(n, false); const next = st[st.length - 1]; if (next) BR.bg.set(next, true); }
    }
  },
  init(n, w) {                      // runs for every Background and TextureBackground once the world is parsed; the first one is bound
    n._w = w; const st = BR.bg.stack(w, n);
    if (!st.length) { st.push(n); n.f.isBound = true; n.f.bindTime = BR.bg.now(); }
  },
  receive(n, field, v) { if (field !== 'set_bind') return false; BR.bg.bind(n, !!v); return true; },
};
/* Background: the stock body took only the horizon colour as the clear colour, so a sky gradient, a ground and the six face pictures (backUrl ... topUrl) were never drawn. The sky sphere and the face
   squares of TextureBackground (BR.bg.make below) now draw the plain Background too: the same arithmetic, the faces from the url fields. The clear colour stays as the stock body set it
   (it only shows where the sphere is transparent). */
BR.node('Background', { component: 'EnvironmentalEffects', level: 1,
  extend: { Background: { isBound: ['SFBool', OUT, false], bindTime: ['SFTime', OUT, 0], backUrl: ['MFString', IO, []], bottomUrl: ['MFString', IO, []], frontUrl: ['MFString', IO, []], leftUrl: ['MFString', IO, []], rightUrl: ['MFString', IO, []], topUrl: ['MFString', IO, []] } },
  init: BR.bg.init, receive: BR.bg.receive,
  build(body, n) { BR.bg.make(body, n); return null; },
  changed(body, n, field) { if (field === 'isBound') BR.bg.show(n); else if (field !== 'set_bind' && field !== 'bindTime' && field !== 'metadata') BR.bg.make(body, n); } });

/* Fog (the world's own fog, EnvironmentalEffects level 2; kept here because it shares the bind code above): like Background, one stack per world, the first Fog is bound at load, set_bind moves one to the top. The stock body never drew it; the bridge
   treats it as the fog of every mesh that no LocalFog covers (a LocalFog above a mesh wins, as in X3D). isBound and bindTime are added on the stock node. */
BR.node('Fog', { component: 'EnvironmentalEffects', level: 2, extend: { Fog: { isBound: ['SFBool', OUT, false], bindTime: ['SFTime', OUT, 0] } }, init: BR.bg.init, receive: BR.bg.receive });

BR.node('TextureBackground', {
  component: 'EnvironmentalEffects', level: 3,
  container: 'children',
  defs: {
    backTexture: ['SFNode', IO, null],
    bindTime: ['SFTime', OUT, 0],
    bottomTexture: ['SFNode', IO, null],
    frontTexture: ['SFNode', IO, null],
    groundAngle: ['MFFloat', IO, []],
    groundColor: ['MFColor', IO, []],
    isBound: ['SFBool', OUT, false],
    leftTexture: ['SFNode', IO, null],
    metadata: ['SFNode', IO, null],
    rightTexture: ['SFNode', IO, null],
    set_bind: ['SFBool', IN, false],
    skyAngle: ['MFFloat', IO, []],
    skyColor: ['MFColor', IO, []],
    topTexture: ['SFNode', IO, null],
    transparency: ['SFFloat', IO, 0],
  },
  init: BR.bg.init,
  receive: BR.bg.receive,

  /* Babylon side. Two things are drawn around the camera (infiniteDistance, so they follow it and never come closer): a sphere of vertex colours for the sky and ground (angles from the
     zenith for the sky, from the nadir for the ground; the last colour holds to the end, the ground covers at least the lower half), and six textured squares for the cube faces, in front of the
     sphere. Both only exist visibly while the node is bound. The six faces use the corner and u-v tables of X_ITE's cube so the pictures stand the same way up. */
  build(body, n) { BR.bg.make(body, n); return null; },
  changed(body, n, field) {
    if (field === 'isBound') BR.bg.show(n);
    else if (field !== 'set_bind' && field !== 'bindTime' && field !== 'metadata') { BR.bg.make(body, n); }
  },
});

{
  const PI = Math.PI, SKY_R = 900, BOX_R = 500, SEG = 48;
  const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  /* colour at an angle: angles[i] is the angle of colors[i + 1], colors[0] sits at angle 0; before the first and after the last angle the end colour holds */
  const ramp = (colors, angles, a) => {
    if (!colors.length) return [0, 0, 0];
    const A = [0, ...angles], N = Math.min(colors.length, A.length);
    if (a <= A[0] || N === 1) return colors[0];
    for (let i = 0; i < N - 1; i++) if (a <= A[i + 1]) return mix(colors[i], colors[i + 1], A[i + 1] > A[i] ? (a - A[i]) / (A[i + 1] - A[i]) : 1);
    return colors[N - 1];
  };
  BR.bg.dome = (f) => {                        // rings from the zenith (theta 0) to the nadir (theta PI)
    const sky = f.skyColor.length ? f.skyColor : [[0, 0, 0]], hasG = f.groundColor.length > 0;
    const gA = f.groundAngle, gExt = hasG ? Math.max(PI / 2, gA.length ? gA[gA.length - 1] : 0) : 0, edge = PI - gExt;
    const th = new Set([0, PI]);
    for (let i = 1; i < 32; i++) th.add(PI * i / 32);
    for (const a of f.skyAngle) if (a > 0 && a < PI) th.add(a);
    if (hasG) { for (const a of gA) if (a > 0 && a < PI) th.add(PI - a); th.add(edge); }
    const rings = [...th].sort((a, b) => a - b).flatMap((t) => {
      const sk = { t, c: ramp(sky, f.skyAngle, t) }, gd = hasG ? { t, c: ramp(f.groundColor, gA, PI - t) } : null;
      if (!hasG || t < edge - 1e-9) return [sk];
      if (t > edge + 1e-9) return [gd];
      return [sk, gd];                         // the ground's upper edge: a hard step from sky to ground at the same angle
    });
    const pos = [], col = [], idx = [];
    for (const r of rings) for (let j = 0; j <= SEG; j++) {
      const p = 2 * PI * j / SEG, s = Math.sin(r.t);
      pos.push(SKY_R * s * Math.cos(p), SKY_R * Math.cos(r.t), SKY_R * s * Math.sin(p)); col.push(r.c[0], r.c[1], r.c[2], 1);
    }
    for (let k = 0; k < rings.length - 1; k++) for (let j = 0; j < SEG; j++) { const a = k * (SEG + 1) + j, b = a + SEG + 1; idx.push(a, b, a + 1, a + 1, b, b + 1); }
    return { positions: pos, colors: col, indices: idx };
  };
  // X_ITE's cube: [name, three corners + the fourth, uv of the corners]; the corners are those of its two triangles (v0 v1 v2) (v0 v2 v5)
  const FACES = {
    frontTexture: [[1, 1, -1], [-1, 1, -1], [-1, -1, -1], [1, -1, -1]], backTexture: [[-1, 1, 1], [1, 1, 1], [1, -1, 1], [-1, -1, 1]],
    leftTexture: [[-1, 1, -1], [-1, 1, 1], [-1, -1, 1], [-1, -1, -1]], rightTexture: [[1, 1, 1], [1, 1, -1], [1, -1, -1], [1, -1, 1]],
    topTexture: [[1, 1, 1], [-1, 1, 1], [-1, 1, -1], [1, 1, -1]], bottomTexture: [[1, -1, -1], [-1, -1, -1], [-1, -1, 1], [1, -1, 1]],
  };
  const UV = [1, 1, 0, 1, 0, 0, 1, 0];
  BR.bg.make = (body, n) => {
    const st = (body._bg ||= new Map()), old = st.get(n); if (old) for (const m of old) m.dispose(false, false);
    const f = n.f, out = [], sc = body.scene;
    const dome = BR.bg.dome(f), mesh = new BABYLON.Mesh((n.def || 'TextureBackground') + '-sky', sc), vd = new BABYLON.VertexData();
    vd.positions = dome.positions; vd.colors = dome.colors; vd.indices = dome.indices; vd.applyToMesh(mesh, false);
    const raw = () => { const c = new BABYLON.ImageProcessingConfiguration(); c.isEnabled = false; return c; };   // the colours are shown as authored: no tone map, no exposure
    const mat = new BABYLON.StandardMaterial('bg-sky', sc); mat.imageProcessingConfiguration = raw();
    mat.disableLighting = true; mat.emissiveColor.set(1, 1, 1); mat.diffuseColor.set(0, 0, 0); mat.specularColor.set(0, 0, 0); mat.backFaceCulling = false; mat.fogEnabled = false;
    mesh.material = mat; mesh.useVertexColors = true; mesh.hasVertexAlpha = false; out.push(mesh);
    for (const [fld, c] of Object.entries(FACES)) {
      const urls = f[fld.replace('Texture', 'Url')], tn = f[fld] || (urls && urls.length ? { id: n.id + ':' + fld + ':' + urls.join(','), type: 'ImageTexture', f: { url: urls, repeatS: false, repeatT: false } } : null);   // Background has url lists, TextureBackground texture nodes
      const t = tn && body.tex(tn); if (!t) continue;
      const m = new BABYLON.Mesh((n.def || 'TextureBackground') + '-' + fld, sc), v = new BABYLON.VertexData();
      v.positions = c.flatMap((p) => [p[0] * BOX_R, p[1] * BOX_R, p[2] * BOX_R]); v.uvs = UV; v.indices = [0, 1, 2, 0, 2, 3]; v.applyToMesh(m, false);
      BABYLON.ShaderStore.ShadersStoreWGSL['unlitVertexShader'] = VERT_UNLIT; BABYLON.ShaderStore.ShadersStoreWGSL['unlitFragmentShader'] = FRAG_UNLIT;   // the body's own unlit textured shader
      const q = new BABYLON.ShaderMaterial('bg-' + fld, sc, { vertex: 'unlit', fragment: 'unlit' },
        { attributes: ['position', 'uv'], uniforms: ['worldViewProjection', 'opacity'], samplers: ['tex0'], shaderLanguage: BABYLON.ShaderLanguage.WGSL, needAlphaBlending: true });
      q.setTexture('tex0', t); q.setFloat('opacity', 1 - Math.min(1, Math.max(0, f.transparency || 0)));
      q.alphaMode = BABYLON.Engine.ALPHA_COMBINE; q.backFaceCulling = false; q.disableDepthWrite = true;
      m.material = q; m.alphaIndex = -1000; out.push(m);
    }
    for (const m of out) { m.infiniteDistance = true; m.isPickable = false; m.alwaysSelectAsActiveMesh = true; m.applyFog = false; if (m === mesh) m.visibility = 1 - Math.min(1, Math.max(0, f.transparency || 0)); m.metadata = { background: true }; }
    st.set(n, out); BR.bg.show(n);
  };
  BR.bg.show = (n) => {
    const body = R.bridge.body, list = body && body._bg && body._bg.get(n); if (!list) return;
    for (const m of list) m.setEnabled(!!n.f.isBound);
  };
}
