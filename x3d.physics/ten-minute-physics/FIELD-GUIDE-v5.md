# Field guide: what five batches of Ten Minute Physics ports taught

Ranked by how much pain each rule saves. Numbers come from the v1 to v5 receipts; grades are Confirmed / Likely / Suspected.

1. **Put an exact pair test in every collision code, and make it oblique.** Head-on, equal masses, elastic: velocities must swap, exactly. A sign error (impulse when the balls are separating) still conserves kinetic energy to 1e-15 (so does having no collisions at all), so an energy check cannot see it. A head-on, axis-aligned test is exact but weak: add an oblique pair (tangential unchanged, normal swapped, 90 degrees for a ball hitting one at rest).  
   *Number:* v1 billiards carried this bug through a merged batch; the witness's head-on pair caught it; the review showed the head-on test would still pass a wrong normal direction (v5 ERRATA-v1-v4.md).  
   *Grade:* Confirmed

2. **Run the schema check AND the semantic check.** The XSD accepts a ColorInterpolator routed into a Color node; the fork's semantic check does not. X3D has no interpolator for a whole colour array: animate mesh vertices with CoordinateInterpolator and colour with a static array.  
   *Number:* v4 smoke scene; all v1 to v5 scenes now pass both with 0 errors.  
   *Grade:* Confirmed

3. **More substeps beat more iterations, at equal cost.** A position-based solver converges by taking small steps, not by relaxing harder inside a big one. Compare at equal cost: 20 sweeps per frame as 20 substeps x 1 iteration gave peak cloth stretch 0.17; 10x2 0.24; 4x5 0.27; 2x10 0.39; 1x20 1.96.  
   *Number:* equal-cost test by the independent reviewer on the v2 cloth; smaller steps also lose less energy (bead 1% kept at 1 substep, 93% at 100, v3) and error (double pendulum 0.815 / 0.072 / 0.015 m at 1 s for 1 / 20 / 100 substeps, v4); this batch's 29x29 cloth peak stretch 55.2% / 23.0% / 6.8% for 4 / 8 / 20 substeps. Note the bead has one constraint and cannot show iterations vs substeps.  
   *Grade:* Confirmed

4. **Spatial hash: the cell must be at least the largest particle diameter.** Then a particle can only touch its 3x3 neighbourhood and the hash is exact, not approximate. Below that it degrades fast: cells at 0.5 / 0.75 / 0.9 diameters missed 1884 / 195 / 22 pairs in 49 checks, 0.975 and 1.0 missed none.  
   *Number:* 49 sampled substeps, 400 balls: 0 pairs missed, 0 false, 2.8% of the pairs tested (v4); the cell sweep is the independent reviewer's (v4's own control caption said 0.6 but was 0.3 of a diameter: 2997 missed).  
   *Grade:* Confirmed

5. **Incompressibility is a count of solver sweeps.** Check the worst-cell divergence against the inflow speed, not a picture.  
   *Number:* 60x30 grid: 100 sweeps leave 0.4% divergence and 0.6% flux error; 3 sweeps leave 51% and 81% (v4).  
   *Grade:* Confirmed

6. **Know your CFL number before you tune anything else, and know why it is there.** The 2D wave equation on a square grid is stable only for c dt / dx below 1/sqrt 2 = 0.7071 (1/sqrt d in d dimensions; 0.7082 on the finite 28x28 grid). The culprit is the checkerboard mode of the 5-point Laplacian under symplectic Euler, not the wave outrunning a cell: the domain-of-dependence limit of 1 is only necessary.  
   *Number:* bisected at 0.7084 on the scheme (v3); the exact limit and the cause are the reviewer's (v2 page had the wrong explanation).  
   *Grade:* Confirmed

7. **Symplectic vs explicit Euler: the shadow energy is exact, the long-run verdict is not.** Symplectic Euler conserves E - g h v / 2 and explicit Euler E + g h v / 2 (to 9e-13 in free flight); both drift by plus or minus g^2 h^2 / 2 per step in true energy. Whether the ball gains, loses or stays bounded depends on the wall rule too: with mirror walls explicit Euler saturates at about 12.9 E0 over long runs, with clamp-and-flip walls the symplectic ball decays and explicit stays bounded. Ceiling reflections remove energy, floor reflections add it.  
   *Number:* shadow numbers v3; saturation, wall-rule flip and floor/ceiling split (+30.28 over 11 floor hits, -16.17 over 10 ceiling hits) are the reviewer's. The v1 claim 'grows without limit' is retracted.  
   *Grade:* Confirmed

8. **Tilt a tank: sloshing is a free exact test for any fluid code.** Fit a damped cosine to the first-mode amplitude and compare with T = 2 pi / sqrt(g k tanh(kH)). It checks gravity, depth, boundary conditions and incompressibility in one number.  
   *Number:* FLIP 1.2290 s against 1.2275 s (0.12%); pure PIC 6.1% long and decaying 2.1x faster.  
   *Grade:* Confirmed (one grid)

9. **Volume error is depth error, and depth sets the wave speed.** omega^2 = g k tanh(k H): a FLIP tank that slowly loses 5% of its volume slows its own waves. Watch the mean particle height, not just the picture.  
   *Number:* level drift 0.33 cell over 6 s with the density-excess term on; in development runs without it the water sank to about a quarter of its depth.  
   *Grade:* Confirmed (dev runs) / Likely (mechanism)

10. **Particle push-apart is not free in FLIP.** Moving particles without changing their momentum lets the surface layer behave like a spring. It lengthened the slosh period here by 8.6% against 0.1% with it off.  
   *Number:* one grid, one scene; why is Suspected.  
   *Grade:* Confirmed that it does / Suspected why

11. **The density-compensation constant is a velocity scale, not a resolution-free knob.** It must beat the wave speed (about 2 sqrt(g H) worked) and it did not carry to a finer grid in my development runs (82x50: the water sank 14% of its depth).  
   *Number:* development runs only; not in the witness.  
   *Grade:* Likely

12. **Rigid bodies: keep the gyroscopic term.** Without it the torque-free spin about the intermediate axis is wrong by 3 rad within 4 s. With an explicit term angular momentum still drifts 0.7% in 6 s: use more substeps or an implicit step if that matters.  
   *Number:* 0.041 rad vs 3.0 rad at 4 s; MuJoCo 9.4e-08 rad from the same reference.  
   *Grade:* Confirmed

13. **Friction cones compare multipliers, not lengths.** lambda_t <= mu lambda_n, or slips and corrections of the same kind. Mixing a length with an impulse-like multiplier gave 3.00 instead of 2.36 m/s^2 and a box that slid at mu 0.7.  
   *Number:* slope formula a = g(sin t - mu cos t): XPBD 0.12% off, MuJoCo 1.4e-05; the incline is the cheapest friction test there is.  
   *Grade:* Confirmed

14. **Cloth self collision: grade it with geometry, not with itself.** Count sheet edges that pierce a triangle they do not touch. The particle-sphere test can pass while layers still cross, and cannot grade itself.  
   *Number:* 0 crossings with collision on (10 samples), 91 with it off.  
   *Grade:* Confirmed

15. **Cloth tunnelling: measure it, do not predict it from speed.** Two written rules based on the fastest substep displacement against the collision thickness were falsified: tunnelling happened at 0.72 t and did not happen at 2.8 t. Thin collision spheres plus few substeps tunnelled most, but the geometric crossing count is the only trustworthy judge.  
   *Number:* rule 1: 2 violations in 12 runs; rule 2 on 9 fresh drops: 1 violation, 5 runs tunnel; demo setting (0.6 spacing, 20 substeps) 0 crossings.  
   *Grade:* Suspected (as an explanation); Confirmed (that the rules fail)

16. **A second engine is a model check, not a build check, and the chaos horizon is a number you can compute.** MuJoCo agreeing with an independent integrator to 1e-7 says the physics model (inertia, axes, signs) is right; it says nothing about your build. A chaotic system separates two accurate runs at the horizon ln(tolerance / initial difference) / lambda (lambda about 2 per second for the double pendulum): 1e-9 buys 8.9 s to 5 cm, 1e-3 only 2 s. Under RK4 call mj_forward before reading MuJoCo's energy, or you read the last stage (3e-6 instead of 9e-9).  
   *Number:* double pendulum 1.3e-7 m over 3 s (v4; the 9.8 s to 5 cm is set by a 1e-9 model difference, not by integrator quality: reviewer's twin run, v4 errata); free rotation 9.4e-8 rad over 6 s, slope 1.4e-5 relative (this batch).  
   *Grade:* Confirmed

17. **np.linalg.norm is not scalar sqrt.** It differs by 1 ulp, which breaks a cross-host per-step hash. Write the sqrt out when a trace must replay bit for bit.  
   *Number:* found on the bead replay (v3).  
   *Grade:* Confirmed

18. **Write the limit before the run, fix the code and never the limit, keep falsified predictions, and be honest about what 'before' proves.** A limit moved after the run is a decoration. The witness stores limit and declared_limit from the same run, so pre-registration is only as good as your git history: commit the limits first. This batch has one stretch limit that failed (fixed with more substeps) and two predictions that were falsified (both reported, neither in the witness). The independent review of v1 to v4 found 25 real problems in claims I had graded Confirmed: ask a second reader to try to break your numbers before you publish them.  
   *Number:* NOTES.md, ERRATA-v1-v4.md.  
   *Grade:* Process
