/* ExplosionEmitter (ParticleSystems level 1): ExplosionEmitter generates all particles from a specific point in space at the initial time enabled.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('ExplosionEmitter', {
  component: 'ParticleSystems', level: 1,
  container: 'emitter',
  defs: {
    mass: ['SFFloat', IO, 0],
    metadata: ['SFNode', IO, null],
    on: ['SFBool', IO, true],
    position: ['SFVec3f', IO, [0, 0, 0]],
    speed: ['SFFloat', IO, 0],
    surfaceArea: ['SFFloat', IO, 0],
    variation: ['SFFloat', IO, 0.25],
  },
  // receive(n, field, value): return true when the event is handled here
  // tick(n, now): once per timestamp, before the event queue drains
  // build(body, n, parent, chain): a drawn node
});
