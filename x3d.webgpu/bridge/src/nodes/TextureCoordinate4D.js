/* TextureCoordinate4D (Texturing3D level 1): TextureCoordinate4D specifies a set of 4D (homogeneous 3D) texture coordinates used by vertex-based geometry nodes (such as IndexedFaceSet or ElevationGrid) to 
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('TextureCoordinate4D', {
  component: 'Texturing3D', level: 1,
  container: 'texCoord',
  defs: {
    mapping: ['SFString', IO, ""],
    metadata: ['SFNode', IO, null],
    point: ['MFVec4f', IO, []],
  },
  // X3DSingleTextureCoordinateNode: homogeneous coordinates (s, t, r, q); a volume texture is read at (s/q, t/q, r/q). Only a volume texture uses the third and fourth number; a 2D texture on
  // the same geometry reads s and t. Held flat like the other coordinate lists.
  flat: { 'TextureCoordinate4D.point': Float32Array },
  changed(body, n) { for (const x of body.world.nodes) if (x.f && x.f.texCoord === n) body.regeo(x); },
});
