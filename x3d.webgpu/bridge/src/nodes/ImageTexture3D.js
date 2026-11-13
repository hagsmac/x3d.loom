/* ImageTexture3D (Texturing3D level 2): ImageTexture3D defines a 3D image-based texture map by specifying a single image file that contains complete 3D data.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('ImageTexture3D', {
  component: 'Texturing3D', level: 2,
  container: 'texture',
  defs: {
    autoRefresh: ['SFTime', IO, 0],
    autoRefreshTimeLimit: ['SFTime', IO, 3600],
    description: ['SFString', IO, ""],
    load: ['SFBool', IO, true],
    metadata: ['SFNode', IO, null],
    repeatR: ['SFBool', INIT, false],
    repeatS: ['SFBool', INIT, false],
    repeatT: ['SFBool', INIT, false],
    textureProperties: ['SFNode', INIT, null],
    url: ['MFString', IO, []],
  },
  /* A volume of 3D texture data from a file: DDS (uncompressed volume, RGBA / RGB / luminance 8 bit) and NRRD (raw, gzip or ascii; uchar, one or four values per voxel). The file is read in the page
     (fetch) and handed to the volume material (BR.vol); until it has arrived the shape is drawn with a 1 voxel transparent volume. DICOM and compressed DDS are not read. */
  changed(body, n, field) { if (field === 'url' || field === 'repeatS' || field === 'repeatT' || field === 'repeatR') BR.vol.reload(body, n); },
});

/* ---- volume textures: data in, Babylon RawTexture3D out ----------------------------------------------------------------------------------------------------------------------------------
   BR.vol.data(body, node, done): done({ w, h, d, rgba: Uint8Array (x fastest, y = 0 is the bottom row, z = slice) }) as soon as the voxels are known (at once for PixelTexture3D, after the pictures or the
   file have loaded for ComposedTexture3D and ImageTexture3D). The Babylon side (texture, material) is in body-br.js. */
BR.vol = {
  is3D: (t) => !!t && (t.type === 'PixelTexture3D' || t.type === 'ComposedTexture3D' || t.type === 'ImageTexture3D'),
  data(body, node, done) {
    if (node.type === 'PixelTexture3D') {
      const im = node.f.image || [], c = im[0], w = im[1], h = im[2], d = im[3];
      if (!(w > 0 && h > 0 && d > 0 && c >= 1 && c <= 4) || im.length < 4 + w * h * d) return done(null);
      const rgba = new Uint8Array(w * h * d * 4);
      for (let i = 0; i < w * h * d; i++) {
        const p = im[4 + i] >>> 0; let r, g, b, a = 255;
        if (c === 1) r = g = b = p & 255; else if (c === 2) { r = g = b = (p >>> 8) & 255; a = p & 255; } else if (c === 3) { r = (p >>> 16) & 255; g = (p >>> 8) & 255; b = p & 255; } else { r = (p >>> 24) & 255; g = (p >>> 16) & 255; b = (p >>> 8) & 255; a = p & 255; }
        rgba.set([r, g, b, a], i * 4);
      }
      return done({ w, h, d, rgba });
    }
    if (node.type === 'ComposedTexture3D') {
      const slices = (node.f.texture || []).filter((t) => t.type === 'PixelTexture' || t.type === 'ImageTexture'); if (!slices.length) return done(null);
      const pics = new Array(slices.length); let left = slices.length;
      const finish = () => {
        const w = pics[0].w, h = pics[0].h, d = pics.length, rgba = new Uint8Array(w * h * d * 4);
        pics.forEach((p, k) => rgba.set(p.w === w && p.h === h ? p.rgba : BR.vol.resample(p, w, h), k * w * h * 4)); done({ w, h, d, rgba });
      };
      slices.forEach((t, k) => {
        if (t.type === 'PixelTexture') { const px = BR.tex3.decode(t); pics[k] = px ? { w: px.w, h: px.h, rgba: new Uint8Array(px.data.buffer, px.data.byteOffset, px.data.length) } : { w: 1, h: 1, rgba: new Uint8Array(4) }; if (!--left) finish(); return; }
        const u = t.f.url && t.f.url[0], im = new Image(); im.crossOrigin = 'anonymous';
        im.onload = () => { const c = document.createElement('canvas'); c.width = im.naturalWidth; c.height = im.naturalHeight; const g = c.getContext('2d'); g.drawImage(im, 0, 0); const px = g.getImageData(0, 0, c.width, c.height).data, o = new Uint8Array(px.length), row = c.width * 4;
          for (let y = 0; y < c.height; y++) o.set(px.subarray(y * row, (y + 1) * row), (c.height - 1 - y) * row); pics[k] = { w: c.width, h: c.height, rgba: o }; if (!--left) finish(); };
        im.onerror = () => { pics[k] = { w: 1, h: 1, rgba: new Uint8Array(4) }; if (!--left) finish(); };
        im.src = u ? BR.resolveUrl(u) : '';
      });
      return;
    }
    if (node.type === 'ImageTexture3D') {
      const u = (node.f.url || [])[0]; if (!u || node.f.load === false) return done(null);
      fetch(BR.resolveUrl(u)).then((r) => r.arrayBuffer()).then((b) => BR.vol.parse(new Uint8Array(b), u)).then(done, () => done(null));
    }
  },
  resample(p, w, h) { const o = new Uint8Array(w * h * 4); for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const sx = Math.min(p.w - 1, Math.floor((x + 0.5) * p.w / w)), sy = Math.min(p.h - 1, Math.floor((y + 0.5) * p.h / h)); o.set(p.rgba.subarray((sy * p.w + sx) * 4, (sy * p.w + sx) * 4 + 4), (y * w + x) * 4); } return o; },
  async parse(bytes, url) {
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    if (bytes[0] === 0x44 && bytes[1] === 0x44 && bytes[2] === 0x53 && bytes[3] === 0x20) {                       // DDS: height, width, depth, then the pixel format
      const h = dv.getUint32(12, true), w = dv.getUint32(16, true), d = Math.max(1, dv.getUint32(24, true)), flags = dv.getUint32(80, true), bits = dv.getUint32(88, true), rgba = new Uint8Array(w * h * d * 4);
      const m = [dv.getUint32(92, true), dv.getUint32(96, true), dv.getUint32(100, true), dv.getUint32(104, true)], lum = (flags & 0x20000) !== 0, bpp = bits / 8, base = 128;
      const shift = (mask) => (mask ? Math.log2(mask & -mask) : 0);
      for (let i = 0; i < w * h * d; i++) {
        let v = 0; for (let k = 0; k < bpp; k++) v |= bytes[base + i * bpp + k] << (8 * k);
        v >>>= 0;
        if (lum) rgba.set([v & 255, v & 255, v & 255, 255], i * 4);
        else rgba.set([(v & m[0]) >>> shift(m[0]), (v & m[1]) >>> shift(m[1]), (v & m[2]) >>> shift(m[2]), (flags & 1) ? (v & m[3]) >>> shift(m[3]) : 255], i * 4);
      }
      return { w, h, d, rgba };
    }
    if (bytes[0] === 0x4e && bytes[1] === 0x52 && bytes[2] === 0x52 && bytes[3] === 0x44) {                       // NRRD: a text header, an empty line, the data
      let end = 0; while (end < bytes.length - 1 && !(bytes[end] === 10 && bytes[end + 1] === 10)) end++;
      const head = new TextDecoder().decode(bytes.subarray(0, end)), field = (k) => { const m = head.match(new RegExp('^' + k + ':\\s*(.*)$', 'mi')); return m ? m[1].trim() : ''; };
      const sizes = field('sizes').split(/\s+/).map(Number), enc = field('encoding').toLowerCase(), type = field('type').toLowerCase();
      if (!/^(uchar|uint8|unsigned char)/.test(type)) throw new Error('NRRD type ' + type + ' is not read (uchar only)');
      let body = bytes.subarray(end + 2);
      if (/gz/.test(enc)) body = new Uint8Array(await new Response(new Blob([body]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
      else if (/ascii|text/.test(enc)) body = Uint8Array.from(new TextDecoder().decode(body).trim().split(/\s+/).map(Number));
      const comps = sizes.length === 4 ? sizes[0] : 1, [w, h, d] = sizes.length === 4 ? sizes.slice(1) : sizes, rgba = new Uint8Array(w * h * d * 4);
      for (let i = 0; i < w * h * d; i++) { if (comps === 1) rgba.set([body[i], body[i], body[i], 255], i * 4); else if (comps === 2) rgba.set([body[i * 2], body[i * 2], body[i * 2], body[i * 2 + 1]], i * 4); else rgba.set([body[i * comps], body[i * comps + 1], body[i * comps + 2], comps > 3 ? body[i * comps + 3] : 255], i * 4); }
      return { w, h, d, rgba };
    }
    throw new Error('ImageTexture3D: ' + url + ' is neither a DDS nor an NRRD volume');
  },
  /* tc' = T C R S -C (TextureTransform3D) or the given matrix (TextureTransformMatrix3D), as a row-vector 4 x 4 (translation in elements 12 to 14), the layout both X3D and Babylon use */
  matrix(tt) {
    const f = tt && tt.f; if (!f) return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
    if (tt.type === 'TextureTransformMatrix3D') return Array.from(f.matrix);
    const mul = (a, b) => { const o = new Array(16).fill(0); for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) for (let k = 0; k < 4; k++) o[r * 4 + c] += a[r * 4 + k] * b[k * 4 + c]; return o; };
    const T = (v) => [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, v[0], v[1], v[2], 1], S = (v) => [v[0], 0, 0, 0, 0, v[1], 0, 0, 0, 0, v[2], 0, 0, 0, 0, 1];
    const q = R.quat.fromAxisAngle(f.rotation, f.rotation[3]), [x, y, z, w] = q, Rm = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0, 2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0, 2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0, 0, 0, 0, 1];
    // row vectors: p' = p * (T(-C) * S * R * T(C) * T(t)) is the X3D order t C R S -C read for column vectors
    return mul(mul(mul(mul(T(f.center.map((v) => -v)), S(f.scale)), Rm), T(f.center)), T(f.translation));
  },
  refreshTransform(body, n) { for (const m of body.rec.values()) { const a = m.node && m.node.type === 'Shape' && m.node.f.appearance; if (a && a.f.textureTransform === n && R.bridge.vol && m.meshes) for (const mesh of m.meshes) if (mesh.material && mesh.material._vol) mesh.material.setMatrix('texMat', BABYLON.Matrix.FromArray(BR.vol.matrix(n))); } },
  reload() {},
};
