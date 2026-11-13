/* PointLight and SpotLight in the world (Lighting component). The reader knows both; the stock body skipped them ("skipped <PointLight>") and drew a DirectionalLight in world space only.
   Each is now a Babylon light under the TransformNode of its parent, so the Transform chain above moves and turns it:
     PointLight   location, color, intensity, radius (no light past it), attenuation (a0 a1 a2)
     SpotLight    the same plus direction, beamWidth (full intensity cone) and cutOffAngle (no light outside), both half angles as X3D gives them
   attenuation 1 0 0 (the default) is a light with no fall-off up to its radius. Otherwise the Babylon light range is set where 1 / (a0 + a1 d + a2 d^2) drops under 1/32, which is a close fit,
   not X_ITE's per pixel polynomial (logged as a difference). global = FALSE lights only the meshes below the parent group (BR.light.scope, run after each build). on = FALSE switches it off.
   ambientIntensity is not used. DirectionalLight stays with the stock body. */
BR.light = {
  make(body, n, parent) {
    const f = n.f, sc = body.scene, name = (n.def || n.type) + '-light', V = BABYLON.Vector3;
    const l = n.type === 'SpotLight'
      ? new BABYLON.SpotLight(name, new V(...f.location), new V(...f.direction), Math.min(Math.PI, 2 * f.cutOffAngle), 1, sc)
      : new BABYLON.PointLight(name, new V(...f.location), sc);
    l.parent = parent; l.node = n; n._light = l; (body._x3dLights ||= []).push(l);
    sc.materials.forEach((m) => { if (m.maxSimultaneousLights !== undefined) m.maxSimultaneousLights = 8; });
    BR.light.refresh(l, n); return l;
  },
  refresh(l, n) {
    const f = n.f, c = f.color, a = f.attenuation || [1, 0, 0], R_ = f.radius > 0 ? f.radius : 1e4;
    l.diffuse = new BABYLON.Color3(c[0], c[1], c[2]); l.specular = l.diffuse.clone(); l.intensity = f.intensity; l.setEnabled(f.on !== false);
    l.position.set(f.location[0], f.location[1], f.location[2]);
    if (a[1] === 0 && a[2] === 0) l.range = R_; else { let d = 0.01; while (d < R_ && 1 / (a[0] + a[1] * d + a[2] * d * d) > 1 / 32) d *= 1.25; l.range = Math.min(R_, d); }
    if (n.type === 'SpotLight') {
      l.direction.set(f.direction[0], f.direction[1], f.direction[2]); l.angle = Math.min(Math.PI, 2 * f.cutOffAngle); l.innerAngle = Math.min(l.angle, 2 * f.beamWidth); l.exponent = 1;
    }
  },
  scope(body) {
    for (const l of body._x3dLights || []) l.includedOnlyMeshes = l.node.f.global === false && l.parent ? l.parent.getChildMeshes(false) : [];
  },
};
BR.node('PointLight', {
  component: 'Lighting', level: 2,
  build(body, n, parent) { BR.light.make(body, n, parent); return null; },
  changed(body, n) { if (n._light) BR.light.refresh(n._light, n); },
});
