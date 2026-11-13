# Ten Minute Physics in X3D: what the ports taught the Loom

**13 November 2026.** Six batches of independent ports of the ideas in Matthias Müller's *Ten Minute Physics* series (<https://matthias-research.github.io/pages/tenMinutePhysics/>) to script-free X3D 4.0, built under the Loom's physics witness. The ports are **own code written from the published method descriptions; no code was copied**. The upstream repository (`matthias-research/pages`) showed no LICENSE file when checked on 13 Nov 2026, so nothing from it is redistributed here. This work is independent and not endorsed by the author; watch the originals.

## Where things are

| What | Where |
|---|---|
| The scenes, pages, notes, receipts, run records (`loom.physics-run/1`), screenshots | `hagopjay/x3d.demo`, `docs/demos/ten-minute-physics/v1` to `v6` (PRs #19, #20, #22, #23, #24, #25). Never overwritten: each batch is its own folder |
| What the work learned, as method | [PHYSICS-PLAYBOOK.md](../../PHYSICS-PLAYBOOK.md) patterns 11 to 19; [LOOM-v1.md](../../LOOM-v1.md) law 44 and failure modes 148 to 160 |
| The independent review of v1 to v4 | [ERRATA-v1-v4.md](ERRATA-v1-v4.md) |
| The field guides (rules ranked by pain saved, each with its number and grade) | [FIELD-GUIDE-v5.md](FIELD-GUIDE-v5.md), [FIELD-GUIDE-v6.md](FIELD-GUIDE-v6.md) |
| The generator scripts and the committed limits | [witness-scripts/](witness-scripts/) |

The scenes and records are **not copied here**: a record names its scene by sha256 and path, and the kit rejects a record whose scene is not at that path (`PHYS_MODEL_STALE`). The scripts here are the code that made them; they run from a checkout of x3d.demo, not from this folder.

## What was built

| Batch | Demos (series number) | Headline numbers (counts and measurements on one machine, numpy; validator `x3d_mcp` fork 13121b6; X_ITE 16.7.1, software GL) |
|---|---|---|
| 1 (v1) | 01 cannonball, 03 billiards, 05 bead (XPBD) | a collision-rule sign error found later by the witness (v3) |
| 2 (v2) | 10 jelly, 14 cloth, 20 height-field water | wave scheme stable only below c dt/dx = 0.7082 (checkerboard mode) |
| 3 (v3) | witness on the ports, MuJoCo 4.0.1 cross-check, fixed billiards, errata | head-on exchange test caught the billiards bug that a kinetic-energy check could not |
| 4 (v4) | 11 spatial hashing, 17 smoke tunnel, 25 double pendulum vs MuJoCo | spatial hash exact at cell size at least a diameter (0 missed, 0 false); MuJoCo against RK4 to 1.3e-7 m over 3 s |
| 5 (v5) | 15 cloth self collision, 18 FLIP water, 22 rigid bodies | FLIP slosh period 0.12% from linear theory (push-apart variant 8.6% long); XPBD box slope 0.12% from Coulomb, MuJoCo 1.4e-5; cloth 0 crossings with self collision, 91 without |
| 6 (v6) | 19 integrators, 23 sweep and prune, 24 Morton codes and a BVH | symplectic Euler order 2.0 at T = 2 pi, 1.0 at T = 1; Verlet 0.61 off position after 5 orbits against RK4 0.0022; sweep and prune 1002 tests per frame against 19,900; BVH 78.6 tests per query of 4096; 0 wrong |

Every run record passed `loom physics` with fresh-process replay and `--max-waivers 0`; v5 caught 11 of 11 and v6 11 of 11 mutation controls on its own records (v6's first run caught 9: two controls were vacuous, failure mode 157).

## What the work taught the Loom

1. **A check has to be able to fail for a wrong implementation** (law 44, pattern 11). The first kinetic-energy check read the same for the buggy and the fixed collision rule.
2. **Pre-registration is only as good as git history** (pattern 13). `limit` and `declared_limit` come from one run. In v6 the limits were committed before the run and the runner refuses to start if the file differs from its commit.
3. **A second reader finds what the author cannot** (pattern 14). 125 claims, 25 negative findings survived a skeptical second pass, 0 false alarms, mostly about checks that could not fail and untested explanations (Likely).
4. **Falsified predictions stay in the notes** (pattern 19). Two tunnelling rules failed; they are readable and are not in the witness.
5. **Integrators and spatial structures** (patterns 16, 17): order depends on the end time you read; bounded energy is not accuracy; a broad phase is verified by set equality with brute force and by counting tests, not by timing.

## Not shown

Another machine; a real GPU; wall-clock times (v6 counts tests, not seconds); a second resolution for FLIP (not convergent as built); box-box contact; an incrementally updated sweep or a refitted BVH; stiff systems; the RK4 against Verlet energy crossover (Suspected). Serious engines (PhysX, MuJoCo) are the subject of the sibling folders in x3d.physics; MuJoCo 4.0.1 was used here only as a model cross-check on the double pendulum and the rigid box.

## Re-running v6

From a checkout of `hagopjay/x3d.demo` at or after the merge of PR #25: `python3 docs/demos/ten-minute-physics/v6/witness/tmp6.py OUTDIR REPO_ROOT`, then `kit/loom physics REPO_ROOT --evidence DIR --runs 'docs/demos/ten-minute-physics/v6/witness/records/*.physics.json' --hosts numpy-fresh-process --max-waivers 0`, then `python3 -I mutate.py KIT_DIR REPO_ROOT`. The generator needs numpy and a git checkout containing `limits6.json`.
