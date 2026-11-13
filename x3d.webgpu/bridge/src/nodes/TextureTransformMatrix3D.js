/* TextureTransformMatrix3D (Texturing3D level 1): TextureTransformMatrix3D applies a 3D transformation to texture coordinates.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('TextureTransformMatrix3D', {
  component: 'Texturing3D', level: 1,
  container: 'textureTransform',
  defs: {
    mapping: ['SFString', IO, ""],
    matrix: ['SFMatrix4f', IO, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]],
    metadata: ['SFNode', IO, null],
  },
  // X3DSingleTextureTransformNode: the 4 x 4 matrix is applied to (s, t, r, 1) as it is given (row vectors, translation in the last row), the field order of the X3D matrix types.
  changed(body, n) { BR.vol.refreshTransform(body, n); },
});
