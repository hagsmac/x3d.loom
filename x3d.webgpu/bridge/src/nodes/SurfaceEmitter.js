/* SurfaceEmitter (ParticleSystems level 2): SurfaceEmitter generates particles from the surface of an object.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('SurfaceEmitter', {
  component: 'ParticleSystems', level: 2,
  container: 'emitter',
  defs: {
    mass: ['SFFloat', IO, 0],
    metadata: ['SFNode', IO, null],
    on: ['SFBool', IO, true],
    speed: ['SFFloat', IO, 0],
    surface: ['SFNode', INIT, null],
    surfaceArea: ['SFFloat', IO, 0],
    variation: ['SFFloat', IO, 0.25],
  },
  // receive(n, field, value): return true when the event is handled here
  // tick(n, now): once per timestamp, before the event queue drains
  // build(body, n, parent, chain): a drawn node
});
