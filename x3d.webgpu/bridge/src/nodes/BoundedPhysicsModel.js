/* BoundedPhysicsModel (ParticleSystems level 2): BoundedPhysicsModel provides user-defined geometrical boundaries for particle motion.
   Field table generated from X3DUOM 4.0 by driver.py scaffold; the behaviour below is hand written. */
BR.node('BoundedPhysicsModel', {
  component: 'ParticleSystems', level: 2,
  container: 'physics',
  defs: {
    enabled: ['SFBool', IO, true],
    geometry: ['SFNode', IO, null],
    metadata: ['SFNode', IO, null],
  },
  // receive(n, field, value): return true when the event is handled here
  // tick(n, now): once per timestamp, before the event queue drains
  // build(body, n, parent, chain): a drawn node
});
