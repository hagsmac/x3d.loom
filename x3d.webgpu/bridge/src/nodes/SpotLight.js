/* SpotLight (Lighting level 2): the cone light; see PointLight.js for the shared Babylon light (BR.light), the attenuation fit and the global = FALSE scope. Here: direction, beamWidth (full
   intensity half angle) and cutOffAngle (no light beyond, half angle) map to a Babylon SpotLight whose angle is the full cone and innerAngle the full inner cone. */
BR.node('SpotLight', {
  component: 'Lighting', level: 2,
  build(body, n, parent) { BR.light.make(body, n, parent); return null; },
  changed(body, n) { if (n._light) BR.light.refresh(n._light, n); },
});
