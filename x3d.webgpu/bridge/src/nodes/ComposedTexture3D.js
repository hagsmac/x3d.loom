/* ComposedTexture3D (Texturing3D level 1): ComposedTexture3D defines a 3D image-based texture map as a collection of 2D texture sources at various depths.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('ComposedTexture3D', {
  component: 'Texturing3D', level: 1,
  container: 'texture',
  defs: {
    description: ['SFString', IO, ""],
    metadata: ['SFNode', IO, null],
    repeatR: ['SFBool', INIT, false],
    repeatS: ['SFBool', INIT, false],
    repeatT: ['SFBool', INIT, false],
    texture: ['MFNode', IO, []],
    textureProperties: ['SFNode', INIT, null],
  },
  /* The slices are the 2D textures of `texture` (ImageTexture or PixelTexture), in depth order, stacked into one Babylon RawTexture3D (BR.vol, body-br.js; slices of another size are resampled to the
     first slice's). Sampled by the (s, t, r) of the 3D / 4D texture coordinates, or at r = 0 by 2D coordinates (the first slice, as X_ITE 16.6.0 does). Nearest filtering by default. */
  build() { return null; },
  changed(body, n, field) { if (field === 'texture' || field === 'repeatS' || field === 'repeatT' || field === 'repeatR') BR.vol.reload(body, n); },
});
