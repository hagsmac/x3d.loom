# Physics under the Loom: the playbook

**13 November 2026.** For anything that steps a physical simulation behind an X3D scene: a rigid-body engine under X_ITE, an articulated figure, a MuJoCo model, a game's own integrator. It comes from two bridges built under the Loom, **X3D with PhysX 5** (a marble machine, then an H-Anim ragdoll; source `[PXB]`) and **X3D with MuJoCo** (phase 0; `[MJB]`). The material itself is in [x3d.physics/](x3d.physics/). The laws are 41 to 43 in [LOOM-v1.md](LOOM-v1.md), the failure modes 124 to 147, the witness is `kit/loom physics`, and the profiles are `x3d-physics/v1` and `x3d-physics-physx/v1`.

For a study whose subject is a numerical method (a field, a spectrum, a black-hole ray tracer) start from [SCIENCE-PLAYBOOK.md](SCIENCE-PLAYBOOK.md); this playbook adds what a *stepped, interactive, engine-backed* simulation needs on top. A game that only needs its tape replayed is [PLATFORMER.md](PLATFORMER.md)'s `play` witness; `physics` is its strict sibling (a hash of every step, every host).

Grades as in LOOM-v1.md: **C** measured here by the thread that built it, **L** reasoned, **S** reported and not re-run.

---

## 1. Why the scene witnesses cannot judge a physics claim

Grammar, Meaning, Traps and Behaviour read a file or run a page. None of them can tell an engine that drifts from one that does not, an old engine that is still stepping behind a new one, or a green test that went red under load and was quietly loosened. Those three were the bridges' real defects, and each is now a contract with a stable code.

| Claim | What can break it | Contract | Law |
|---|---|---|---|
| "The new engine runs the scene" | the old engine also steps (X_ITE's Bullet took one step after `loadURL()`) | takeover proof, every host, leaks listed | 41 |
| "It is deterministic" | one host replayed; a hash of the end only; state left out of the hash | a hash per step, replayed in every named host, first differing step reported | 42 |
| "It matches the physics" | judged against the wrong answer (the continuum one for a stepped scheme) | an exact reference per run, limits declared before it | 19, 28 |
| "It passes" | a limit widened, a number that fails marked green, a failure with no name | tolerances, waivers with owner and date, a profile cap | 43 |
| "It supports the scene" | authored fields dropped without a word | loss report | 40 |

## 2. The order of work

1. **Fill the card** ([kit/templates/PHYSICS-STUDY-CARD.md](kit/templates/PHYSICS-STUDY-CARD.md)): the engine and its pinned build, the hosts you will claim, the references that exist, the limits (write them down *now*), the takeover if there is one, the fields the engine cannot honour.
2. **Exact references first, before the first scene.** A closed form, or the scheme's own discrete solution (section 3, pattern 1). If the physics has none (a ragdoll, a drum), say so on the card: it will have self-consistency only.
3. **Build the bridge, then the analytic ladder** (pattern 2), in Node, before any browser. Node is the fastest host and the one a hash can be replayed in from every other.
4. **Prove the takeover** (pattern 5) the day the new engine first moves a body, not at the end.
5. **Record and replay** (pattern 3) as soon as there is a run worth keeping: hash every step, replay in each browser and Node.
6. **Scenes through Grammar and Meaning.** Every exported scene, every piece.
7. **Write the run record and run `kit/loom physics`** (section 4). Put the controls that must fail in the same run (pattern 7).
8. **Waive in writing, never silently** (pattern 6). Browser suites that fail under load are re-run unloaded; if they still fail, they stay waivers.
9. **Open the PR.** A thread's last step is its fold-back (LOOM-v1 step 9), numbered from upstream's tip that day.

## 3. Witness patterns (each was paid for)

**1. The scheme's own answer is the reference.** Under semi-implicit Euler, free fall is y0 − g·h²·n(n+1)/2, not y0 − ½·g·t². PhysX 5.12 matched the discrete solution to 1.5e-6 m at t = 1 s; the continuum answer is 0.0204 m away, which is exactly ½·g·h·t. Use the discrete solution as the reference and report the continuum gap as a *known number*. (Failure mode 124; evidence `p1-analytic.json`.)

**2. The analytic ladder.** One small test per law the engine must obey, each with a limit declared in the SPEC before it ran:

| Test | Reference | Limit | Measured (PhysX 5.12, Node) |
|---|---|---|---|
| free fall, 1 s | discrete semi-implicit Euler | 1e-4 m | 1.5e-6 m |
| pendulum (ball joint, hinge), L = 0.5 m | 2π√(I/(m g L))·(1 + θ0²/16) | 0.5 % | 1.4e-5 relative |
| restitution, e = 0.6 | rebound = e·(v + g·h), because PhysX applies e to the pre-solver velocity | 1e-3 | 7.2e-8 worst of 5 bounces |
| incline 30°, μ = 0.3 / 0.7 | a = g(sin θ − μ cos θ); μ = 0.7 holds | 2 % / 1 mm | 0.98 % / 0.30 mm |
| tunnelling, 5 m/s marble, 5 mm wall, 40 start phases | CCD on never crosses | 0 of 40 | 0 of 40 |

The restitution test found a limit cycle (failure mode 125): below minBounceSpeed ≈ e·g·h/(1 − e) a ball never rests. The bridge raises the threshold to 2·e·g·h/(1 − e) and says so in the loss report.

**3. Hash every step; replay in every host.** The bridge keeps an FNV-1a hash per step over every moving body's float32 pose and velocities. A run recorded in Chromium (1918 steps, 335 command batches, 21 teleports) was replayed in Chromium (same page, fresh page), Firefox 146, WebKit 26 and Node 24 with 0 differing hashes; a run recorded in Firefox (969 steps) likewise. Record the *host*, not the browser family alone: "same page" replay is a weaker claim and is kept apart (`chromium-same-page`). The hash must cover everything the physics depends on; a hash that leaves state out cannot fail. The trace is stamped with a sha256 of the comma-joined decimal hashes, so an edited step is `PHYS_TRACE_TAMPERED`. (Law 42.)

**4. Compare the reader's model with the Node model, in the browser.** When a machine ran 20 of 20 in Node and 0 of 20 in the browser, the cause was an import sanitiser that snapped authored rotations (−8° to −15°). The round-trip probe (the browser reader's model against the generator's own: 36 bodies, 0 differences) showed reader and generator agreed, which pointed at the sanitiser before anyone chased the physics. For the ragdoll the same comparison (18 links, 53 shapes, 0 differences at 1e-5) found the H-Anim equal-limits reading (failure modes 129, 134).

**5. The takeover proof.** When page code replaces an engine the runtime brings, show, for every host that has it: (a) the old engine moves nothing when disabled (0 position events in 120 frames); (b) a write made while disabled sticks and routes on; (c) disabling mid-flight freezes it; (d) re-enabling resumes from the written pose; (e) the one step it took *before* the switch is a **leak**, listed and handled (here `createX3DFromURL`, disable, `replaceWorld`, which leaks none). Evidence `p1-enabled-probe-{chromium,firefox,webkit}.json`. Node has no page engine, so the record's `takeover.applies_to` names the browsers. (Law 41.)

**6. Tolerance, then waiver.** The owner's rule was to state tolerances, log mismatches and move on; the Loom keeps that and makes the excursion visible. The limit is written before the run (`declared_limit`); a limit later than the declared one is `PHYS_LIMIT_WIDENED`; a number that fails its limit but is marked pass is `PHYS_FALSE_GREEN`. A real excursion is `accepted_failure` with a `waiver` {owner, date, reason, observed, limit}; the waiver must restate the measurement's own numbers; the profile's `physics.coverage.max_waivers` caps the count, and the witness records the cap it ran with, so a looser run is not accepted. A self-check that misses its closed form (the Gravitron: 2.97 against 2.22 rad/s, 34 %) is logged with its probable cause and **not tuned**; until a limit is declared it has no pass or fail, so it is not put in the record. (Law 43; failure modes 133, 137.)

**7. Controls that must fail.** Each record carries at least one: with CCD off the 5 m/s marble crossed the wall in 10 of 40 start phases, and that is the control *succeeding*. On top, `x3d.physics/tools/physx_controls.py` mutates the real records (an edited step hash, a missing WebKit replay, a widened limit, a lowered cap, a removed waiver, ...) and requires the intended code each time: 14 of 14 here. (Law 19.)

**8. Derived scores get a hand-checkable unit test.** The ragdoll's head score (HIC-style, window ≤ 36 ms) reads 619 for a 50 g, 36 ms square pulse at 1 ms sampling against 636 by hand (−3 %, the sampling edges). The heat map reads the segment's *own* change of velocity, because contact impulse over mass read 141 m/s on a 7.5 kg thigh (failure mode 136). Peaks depend on sample spacing; log it (failure mode 138). "Not an injury verdict" goes on the page.

**9. A build check is not a model check.** MuJoCo's native build replayed its own WASM trials to 6e-16 rad. That tests the build. For the model, use a closed form or another engine (failure mode 142).

**10. A threat model with measured gaps.** MuJoCo's Gate 0 ran 84 tests and 19 threat checks: 16 defences hold, 3 gaps were *measured* and listed (one, XML entity resolution in the validator server, is a follow-up). A gate that reports its gaps is worth more than one that reports none.

**11. Every check ships its wrong twin (law 44).** Before a reference goes into a record, run it against an implementation you know is wrong. The kinetic-energy check on a billiards port read 1.33e-15 with the buggy rule, 2.0e-15 with the fixed one and 0 with no collisions: it could not fail, so it said nothing (failure mode 148). The exchange test did fail on the bug (head-on elastic: velocities swap; oblique: tangential part kept, outgoing velocities perpendicular, dot -2e-16). Add the oblique case, because a head-on axis-aligned test makes every dot product exact (failure mode 151).

**12. Read each quantity where nothing has just enforced it.** A constraint residual after its own projection is zero by construction (a bead's "< 2e-16" was 2.4e-2 before the projection at 1 substep, 2.9e-6 at 100); an engine's derived energy may be one stage stale (MuJoCo under RK4: 3.4e-6 as read, 8.86e-9 after `mj_forward`); a scan that stops at a threshold reports the value at the stop. Say when the number was read (failure modes 149, 152).

**13. Commit the limits first, and let the runner check.** In the Ten Minute Physics batch 6 the limits are a JSON file committed and pushed before the first run; `tmp6.py` refuses to start if the file differs from its last commit and writes the commit and the file's sha256 into each record (`limits` block, outside the schema the kit checks today). That is provable from history, which `limit` and `declared_limit` written by one run are not (failure mode 156). A development run still informs the scale of some limits; the notes say which. Open: have `loom physics` read and verify a `limits.commit`.

**14. A second reader breaks the numbers before they are Confirmed.** Four reviewers recomputed v1 to v4 of the ports and a skeptical agent tried to knock down each negative finding: 125 claims checked, 25 negative findings survived, 0 false alarms. They were mostly checks that could not fail and explanations nobody had tested, less often wrong arithmetic (Likely; a count of the 25 by kind was not made). The corrections live in `x3d.demo` v5 `ERRATA-v1-v4.md`; earlier folders are not edited.

**15. An explanation is a claim with its own test.** "The wave outruns a cell per step" was refuted by its own number (c dt/dx = 0.83); the cause was the checkerboard mode, stable only below 0.7082 on the 28 x 28 grid (1/sqrt 2 in the infinite grid, 1/sqrt d in d dimensions). "The late error is chaos" holds only with a horizon: ln(tolerance / initial difference) / lambda, about 8.9 s for a 1e-9 difference at lambda = 2 per second (failure modes 153, 154).

**16. Orders are slopes read at an end time; energy is not position.** Symplectic Euler measures order 2.0 at T = 2 pi and 1.0 at T = 1 (the leading error cancels over a period). On a Kepler orbit (e = 0.6, 200 steps per orbit, 50 orbits) velocity Verlet keeps energy within 0.74% with no growth yet sits 0.61 from the true position after 5 orbits, against 0.0022 for RK4 (283 times), whose energy error drifted from 6.9e-5 to 3.3e-4. The crossover where a symplectic method wins on energy was not measured (Suspected). Counts and numbers: x3d.demo v6 (failure mode 159).

**17. A spatial structure is checked by set equality, and cost is counted.** Sweep and prune over 200 boxes: 0 pairs missed or false against brute force in 180 frames; 1002 tests per frame along the long axis, 4133 along the short, 19,900 brute; cost grows as n^1.50 at fixed density, not n. Morton codes: 0 mismatches against the bit loop over 100,008 inputs. A BVH from one sort: 78.6 tests per query of 4096, 0 wrong of 1000 queries. The wrong-structure controls (sort by centre: 905 pairs missed; node boxes shrunk by 0.02: 2466 hits lost) are what make the equality meaningful (failure mode 160).

**18. Count caught controls, and make each one change something.** In batch 6 the first run of the 11 mutations caught 9: two scaled a reference whose limit was 0 and changed nothing. After choosing a reference with a nonzero limit, 11 of 11 (failure mode 157).

**19. Keep falsified predictions in the notes and out of the witness.** Two written rules about cloth tunnelling failed (failure mode 158). They stay readable in NOTES.md and are not references, because a reference that fails would turn the record red for a reason that is not a defect of the code.

## 4. The run record: `loom.physics-run/1`

One JSON file per run. `kit/loom physics ROOT --evidence DIR --runs 'runs/*.physics.json' [--hosts a,b,c] [--max-waivers N] [--require-takeover]`. Exit 0 pass, 1 a contract violation with its code, 2 an unreadable record. Standard library only; every gate raises, none asserts, so it holds under `python -O` (law 18).

| Field | Meaning |
|---|---|
| `schema`, `id` | `loom.physics-run/1`; a name for the run |
| `engine` | `{name, version, build?}`; every replay with an `engine_version` must equal it (`PHYS_ENGINE_DRIFT`) |
| `model` | `{sha256, path?}`; with `path`, the file on disk must still hash to `sha256` (`PHYS_MODEL_STALE`); without it the hash is of the model the run embedded |
| `recorded` | `{host, steps, hashes?, trace_sha256}`; `hashes` must hash to `trace_sha256` (`PHYS_TRACE_TAMPERED`) |
| `replays` | `[{host, steps, mismatches, first_mismatch, engine_version?, trace_sha256?}]` |
| `required_hosts` | every one needs a replay (`PHYS_REPLAY_MISSING`); the CLI's `--hosts` overrides |
| `references` | `[{id, observed, limit, rule?, declared_limit?, status}]`; at least one (`PHYS_NO_REFERENCE`) |
| `tolerances` | the same shape, plus `status: "accepted_failure"` and `waiver` |
| `controls` | `[{id, expect: "fail", observed_failed}]` |
| `takeover` | `{replaces, applies_to?, engine_off_hosts, leaks: [{what, handled}]}` |
| `losses` | `{authored_fields_dropped, reported}` (`PHYS_LOSS_UNREPORTED`) |

Any other field (sources, notes, `not_shown`) is carried and ignored. The 18 codes, in the order they are checked, are listed at the top of [kit/loomkit/physics.py](kit/loomkit/physics.py), each with a two-sided test in `kit/tests/test_gates.py` (the clean fixture passes, each mutation is caught with its own code, normal Python and `-O`).

**How the real records are made.** `x3d.physics/tools/physx_run_record.py` reads the PhysX bridge's own JSON evidence and writes two records into `x3d.physics/runs/`. It measures nothing; every number comes from `p4-run-*.json`, `p4-determinism-*.json`, `p1-analytic.json`, `p1-enabled-probe-*.json`, `p5-smoke.json` and the loss count in `PHASE-2.md`. Then `kit/loom physics` judges them (evidence in `runs/physics-20261113/`).

## 5. What a pass means, and what it does not

A pass says: these hashes replayed unchanged in these hosts on this machine; this run answered to these references within limits written first; the old engine was off here, with these leaks; these excursions are waived by these owners. It does **not** say: the same on another machine (all replays here ran on one Mac; this is `visible_not_run: cross-machine`); the model is right where no exact reference exists (the ragdoll, the Gravitron, a 300-body machine); the engine build is the only one that behaves so; a real GPU, listening, or that anyone enjoys it.

## 6. The trap cheat-sheet (read before you build)

**X_ITE 16.7 RigidBodyPhysics** (C, `[PXB]`; failure mode 140): Bullet uses a variable step (a moving average from 0); `frictionCoefficients.y` is rolling friction; inertia is ignored; joints need both bodies; anchors are in world coordinates; `CollisionSensor` ignores `enabled` until its collider is re-assigned; joints write outputs unless `forceOutput` is NONE; there is no `UniversalJoint` or `MotorJoint`; `TimeSensor.pauseTime` is ignored before the scene is live; `enabled` false-then-true coalesces in one turn; SAI cannot write `outputOnly` fields (`getField(name).setValue` works, with a deprecation warning); `EnvironmentLight` is X3D 4.1, so add it at runtime only; after switching Bullet off the Bullet-versus-PhysX gap is only partly explained by X_ITE's step warm-up (35 to 61 mm RMS left).

**PhysX 5.12 through physx-js-webidl 2.9.1** (C): restitution applies to the pre-solver velocity that already holds this step's g·h; the default 2 cm contact offset hides thin walls (size offsets per shape); D6 drive velocity has the inverted sign; `forceLimit` is an impulse per step; threshold-force contact reports never fire under TGS; an articulation teleport moves only the root until the next step (update every link); spherical limits beyond 1.9 rad go to NaN (cap them), as do links crushed under many bodies (cap push-out at 3 m/s; joint speed is capped at 40 rad/s); the npm package is a web-only Emscripten build (Node needs a shim) and carries no LICENSE file (ship the BSD-3 text and notices).

**H-Anim** (C): `llimit` and `ulimit` default to `0 0 0`, so equal limits mean *free*, not locked; a range under 0.01 rad is locked; the dummy locks with ±0.002 rad; X-Y-Z angle readings of an H-Anim joint differ from PhysX's twist/swing coordinates by up to 2 rad on large swings (visuals use quaternions, so they are unaffected); a ragdoll started with limbs inside the floor goes to NaN.

**Browsers** (C): WebKit's `createX3DFromString` can stall (watchdog and one retry); headless Firefox ran at about a third of real time on the barrage and at 4 fps in the worst scene; headless WebKit drew the ragdoll page at 17 fps; Chromium's headless shell has no WebGL (use the `chromium` channel); a Playwright Firefox context without a `locale` has `navigator.language` undefined and X_ITE throws "invalid language tag"; a source edit during a run reloads the page under the dev server.

**Process** (C): `Object.assign` of functions onto page state overwrote the page's own methods, twice (guard `expose()`); an import sanitiser can change the model; clocks must follow physics when it lags; a 60 fps claim needs a measurement (52.6 median under load).

## 7. Where each pattern runs in [x3d.physics/](x3d.physics/)

| Pattern | Where |
|---|---|
| Analytic ladder (2) | `physx-bridge/tests/analytic.test.ts`; `evidence/p1-analytic.json` |
| Hash, record, replay (3) | `physx-bridge/src/bridge/world.ts` (FNV-1a), `probes/determinism.mjs`, `tools/replay-node.ts`; `evidence/p4-run-*.json`, `p4-determinism-*.json` |
| Model comparison (4) | `physx-bridge/probes/roundtrip.mjs` (`evidence/p3-roundtrip.json`), `probes/run-ragdoll.mjs` (`sameModel` in `evidence/ragdoll-p1-*.json`); `evidence/PHASE-3.md` |
| Takeover (5) | `physx-bridge/probes/enabled.html`, `run-probe.mjs`; `evidence/p1-enabled-probe-*.json` |
| Loss report (law 40) | `physx-bridge/tests/mapping.test.ts`; `scenes/experiments/ode-only-fields.x3d`; `evidence/PHASE-2.md` |
| Waivers (6) | `evidence/p5-smoke.json`, `p5-smoke-log.txt`; `x3d.physics/runs/*.physics.json` |
| Derived-score tests (8) | `physx-bridge/tests/crashtest.test.ts` (HIC of a square pulse within 5 % of the textbook value); `evidence/crashtest-*.json` |
| Gate 0 (10) | `mujoco-bridge/GATE-0.md`, `THREAT-MODEL.md` |
| Checks that can fail, limits by commit, second-reader review (11 to 14, 18) | `x3d.physics/ten-minute-physics/` (README, `ERRATA-v1-v4.md`, `witness-scripts/`); the scenes and records are in `hagopjay/x3d.demo` `docs/demos/ten-minute-physics/v1` to `v6` |
| Integrators, broad phase, BVH (16, 17) | `witness-scripts/tmp6.py`, `limits6.json`; x3d.demo v6 |
| The records and controls | `x3d.physics/runs/`, `x3d.physics/tools/`, `runs/physics-20261113/` |

## 8. Content boundaries that were set along the way

The ragdoll is a crash-test dummy and a cartoon person; effects are cartoon (stars, words, grunts), with no gore. A character that would mock real addiction (an "opioid" character) was declined; the same random rigid-or-floppy mechanic shipped as the dummy's power flicker. The head score and heat map say "not an injury verdict". These were the thread's decisions; they are recorded so a later thread does not have to rediscover them.

## 9. Open

- **A second machine.** Every replay ran on one Mac. The record format already lets a second machine's replay be added as another host (`chromium@machine-b`) with its own steps and mismatches.
- **The ragdoll has no run record.** Its per-step hashes were not persisted; its replays (604, 623 and 610 steps, 0 hash differences each, in their own browser) are in the evidence but cannot be judged by the witness. Next ragdoll phase: persist the hash list and add the run. Its limit overshoot (0.43 rad against 0.2) and the Gravitron gap belong in that record.
- **MuJoCo has no run record.** Its phase 1 plans checkpoint replay with `mj_getState`. Until then, only the Gate 0 pattern and the failure modes carry over.
- **Waiver ownership of the three smoke failures** is reconstructed from the thread's note ("user accepted"); the owner should confirm (LOOM-v1 §10, question 16).
- **Real-GPU, listening and a paired visual review** stay `visible_not_run`.
- **`loom physics` does not yet check a `limits.commit`.** The Ten Minute Physics batch 6 records carry one (`limits.path`, `limits.commit`, `limits.sha256`) and the generator verifies it; the kit ignores the block (pattern 13). A check that the file at that commit has the sha256 the record names is small.
