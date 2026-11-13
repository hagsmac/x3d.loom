/* CADAssembly (CADGeometry level 2): CADAssembly holds a set of Computer-Aided Design (CAD) assemblies or parts grouped together.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('CADAssembly', {
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
  // X3DProductStructureChildNode grouping: a Group with a name (the assembly of CAD parts and sub-assemblies). `visible` hides the subtree; addChildren / removeChildren work as on Group.
  receive(n, field, v) { return BR.addRemove(n, field, v); },
  build(body, n, parent, chain) { return body.buildGroup(n, parent, chain); },
  changed(body, n, field) {
    const r = body.rec.get(n.id); if (!r) return;
    if (field === 'children') body.rebuildGroup(n); else if (field === 'visible') r.tn.setEnabled(n.f.visible !== false);
  },
});
