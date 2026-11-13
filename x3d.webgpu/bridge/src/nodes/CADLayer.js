/* CADLayer (CADGeometry level 2): CADLayer nodes define a hierarchy that shows layer structure for a Computer-Aided Design (CAD) model.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('CADLayer', {
  component: 'CADGeometry', level: 2,
  container: 'children',
  defs: {
    addChildren: ['MFNode', IN, []],
    bboxCenter: ['SFVec3f', INIT, [0, 0, 0]],
    bboxDisplay: ['SFBool', IO, false],
    bboxSize: ['SFVec3f', INIT, [-1, -1, -1]],
    children: ['MFNode', IO, []],
    metadata: ['SFNode', IO, null],
    name: ['SFString', IO, ""],
    removeChildren: ['MFNode', IN, []],
    visible: ['SFBool', IO, true],
  },
  // X3DProductStructureChildNode grouping: a layer of the CAD model (CADAssembly, CADPart and shapes inside); `visible` shows or hides the layer's content, as a Group's does.
  receive(n, field, v) { return BR.addRemove(n, field, v); },
  build(body, n, parent, chain) { return body.buildGroup(n, parent, chain); },
  changed(body, n, field) {
    const r = body.rec.get(n.id); if (!r) return;
    if (field === 'children') body.rebuildGroup(n); else if (field === 'visible') r.tn.setEnabled(n.f.visible !== false);
  },
});
