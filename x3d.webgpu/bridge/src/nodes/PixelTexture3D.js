/* PixelTexture3D (Texturing3D level 1): PixelTexture3D defines a 3D image-based texture map as an explicit array of pixel values (image field).
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('PixelTexture3D', {
  component: 'Texturing3D', level: 1,
  container: 'texture',
  defs: {
    description: ['SFString', IO, ""],
    image: ['MFInt32', IO, []],                       // components width height depth, then width*height*depth pixels (the first slice first)
    metadata: ['SFNode', IO, null],
    repeatR: ['SFBool', INIT, false],
    repeatS: ['SFBool', INIT, false],
    repeatT: ['SFBool', INIT, false],
    textureProperties: ['SFNode', INIT, null],
  },
  /* The volume is a Babylon RawTexture3D (BR.vol, body-br.js): sampled by the (s, t, r) of the geometry's 3D or 4D texture coordinates, or r = 0 for the 2D coordinates of a Box and the like (the first
     slice, as X_ITE 16.6.0 does). Nearest filtering unless a TextureProperties asks for more (19775-1 18.4 default FASTEST). A change of `image` uploads the volume again. */
  build() { return null; },
  changed(body, n, field) { if (field === 'image' || field === 'repeatS' || field === 'repeatT' || field === 'repeatR') BR.vol.reload(body, n); },
});
/* pixel arrays -> a Babylon texture: components 1 grey, 2 grey+alpha, 3 RGB, 4 RGBA; one integer per pixel, the first byte is the first component; the first row is the bottom row */
BR.tex3 = {
  decode(node) {                                      // -> { w, h, c, data (RGBA bytes, row 0 = bottom) } or null
    const im = node.f.image || [], d3 = node.type === 'PixelTexture3D';
    const c = d3 ? im[0] : im[2], w = d3 ? im[1] : im[0], h = d3 ? im[2] : im[1], off = d3 ? 4 : 3;
    if (!(w > 0 && h > 0 && c >= 1 && c <= 4) || im.length < off + w * h) return null;
    const data = new Uint8ClampedArray(w * h * 4);
    for (let i = 0; i < w * h; i++) {
      const p = im[off + i] >>> 0; let r, g, b, a = 255;
      if (c === 1) r = g = b = p & 255;
      else if (c === 2) { r = g = b = (p >>> 8) & 255; a = p & 255; }
      else if (c === 3) { r = (p >>> 16) & 255; g = (p >>> 8) & 255; b = p & 255; }
      else { r = (p >>> 24) & 255; g = (p >>> 16) & 255; b = (p >>> 8) & 255; a = p & 255; }
      data.set([r, g, b, a], i * 4);
    }
    return { w, h, c, data };
  },
  paint(tex, node) {                                  // draws the first slice into a DynamicTexture
    const px = BR.tex3.decode(node), ctx = tex.getContext(), cv = ctx.canvas;
    if (!px) { ctx.clearRect(0, 0, cv.width, cv.height); tex.update(); return; }
    cv.width = px.w; cv.height = px.h;
    const img = new ImageData(new Uint8ClampedArray(px.data.length), px.w, px.h);
    for (let y = 0; y < px.h; y++) for (let x = 0; x < px.w; x++) img.data.set(px.data.subarray((y * px.w + x) * 4, (y * px.w + x) * 4 + 4), (y * px.w + x) * 4);
    ctx.putImageData(img, 0, 0); tex.hasAlpha = px.c === 2 || px.c === 4; tex.update(false);
  },
  make(body, node) {
    const px = BR.tex3.decode(node), w = px ? px.w : 1, h = px ? px.h : 1;
    const t = new BABYLON.DynamicTexture('px-' + node.id, { width: w, height: h }, body.scene, false, BABYLON.Texture.NEAREST_SAMPLINGMODE);
    t.wrapU = node.f.repeatS === false ? BABYLON.Texture.CLAMP_ADDRESSMODE : BABYLON.Texture.WRAP_ADDRESSMODE;
    t.wrapV = node.f.repeatT === false ? BABYLON.Texture.CLAMP_ADDRESSMODE : BABYLON.Texture.WRAP_ADDRESSMODE;
    BR.tex3.paint(t, node); return t;
  },
  refresh(body, node) {                               // a field changed: paint again, shapes keep their material
    const t = body.texCache.get(node.id); if (!t || !t.getContext) return;
    BR.tex3.paint(t, node);
  },
};
