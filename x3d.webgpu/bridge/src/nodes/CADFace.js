/* CADFace (CADGeometry level 2): CADFace holds geometry representing one face in a Computer-Aided Design (CAD) CADPart.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('CADFace', {
  component: 'CADGeometry', level: 2,
  container: 'children',
  defs: {
    bboxCenter: ['SFVec3f', INIT, [0, 0, 0]],
    bboxDisplay: ['SFBool', IO, false],
    bboxSize: ['SFVec3f', INIT, [-1, -1, -1]],
    metadata: ['SFNode', IO, null],
    name: ['SFString', IO, ""],
    shape: ['SFNode', IO, null],
    visible: ['SFBool', IO, true],
  },
  // X3DProductStructureChildNode + X3DBoundedObject: one face of a part. Its `shape` (Shape, LOD or Transform) is drawn; `visible` hides it. A CADFace without a shape draws nothing.
  build(body, n, parent, chain) {
    const tn = new BABYLON.TransformNode(n.def || 'CADFace', body.scene); tn.parent = parent;
    const r = { node: n, tn, kids: [], chain: [n, ...chain] }; body.rec.set(n.id, r);
    if (n.f.shape) r.kids.push(body.build(n.f.shape, tn, r.chain));
    if (n.f.visible === false) tn.setEnabled(false);
    return r;
  },
  changed(body, n, field) {
    const r = body.rec.get(n.id); if (!r) return;
    if (field === 'visible') r.tn.setEnabled(n.f.visible !== false);
    else if (field === 'shape') { for (const k of r.kids) body.disposeRec(k); r.kids = []; if (n.f.shape) r.kids.push(body.build(n.f.shape, r.tn, r.chain)); }
  },
});
