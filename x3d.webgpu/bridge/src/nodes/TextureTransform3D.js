/* TextureTransform3D (Texturing3D level 1): TextureTransform3D applies a 3D transformation to texture coordinates.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('TextureTransform3D', {
  component: 'Texturing3D', level: 1,
  container: 'textureTransform',
  defs: {
    center: ['SFVec3f', IO, [0, 0, 0]],
    mapping: ['SFString', IO, ""],
    metadata: ['SFNode', IO, null],
    rotation: ['SFRotation', IO, [0, 0, 1, 0]],
    scale: ['SFVec3f', IO, [1, 1, 1]],
    translation: ['SFVec3f', IO, [0, 0, 0]],
  },
  // X3DSingleTextureTransformNode: tc' = T C R S -C applied to the 3D texture coordinate (the Transform arithmetic, scaleOrientation is not a field of this node). Read by the volume material
  // (BR.vol.matrix); a 2D texture is not moved by it.
  changed(body, n) { BR.vol.refreshTransform(body, n); },
});
