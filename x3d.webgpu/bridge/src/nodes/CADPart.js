/* CADPart (CADGeometry level 2): CADPart is an atomic part that defines both coordinate-system location and the faces that constitute a part in a Computer-Aided Design (CAD) model.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('CADPart', {
  component: 'CADGeometry', level: 2,
  container: 'children',
  defs: {
    addChildren: ['MFNode', IN, []],
    bboxCenter: ['SFVec3f', INIT, [0, 0, 0]],
    bboxDisplay: ['SFBool', IO, false],
    bboxSize: ['SFVec3f', INIT, [-1, -1, -1]],
    center: ['SFVec3f', IO, [0, 0, 0]],
    children: ['MFNode', IO, []],
    metadata: ['SFNode', IO, null],
    name: ['SFString', IO, ""],
    removeChildren: ['MFNode', IN, []],
    rotation: ['SFRotation', IO, [0, 0, 1, 0]],
    scale: ['SFVec3f', IO, [1, 1, 1]],
    scaleOrientation: ['SFRotation', IO, [0, 0, 1, 0]],
    translation: ['SFVec3f', IO, [0, 0, 0]],
    visible: ['SFBool', IO, true],
  },
  // X3DProductStructureChildNode + Transform fields: the part is a Transform (T C R SR S -SR -C) with a name; the body's applyTransform reads the fields as it does for Transform.
  receive(n, field, v) { return BR.addRemove(n, field, v); },
  build(body, n, parent, chain) {
    const r = body.buildGroup(n, parent, chain); body.applyTransform(n, r.tn); return r;
  },
  changed(body, n, field) {
    const r = body.rec.get(n.id); if (!r) return;
    if (field === 'children') body.rebuildGroup(n); else if (field === 'visible') r.tn.setEnabled(n.f.visible !== false);
    else if (['translation', 'rotation', 'scale', 'scaleOrientation', 'center'].includes(field)) body.applyTransform(n, r.tn);
  },
});
