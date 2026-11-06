# Loom v1

The X3D Loom, consolidated: one definition, its sources, what the other model's patches taught, and a small kit that runs. Built 3 November 2026 from the Drive folder, the project zips and their PR patches, and the notes on this Mac. Local git repository; no remote.

| File | What it is |
|---|---|
| [LOOM-v1.md](LOOM-v1.md) | **The definition.** Purpose, roles, 37 laws, the ten-step loop, artefacts, gates and thresholds, measurements with grades, 108 failure modes, roadmap, open questions, decisions |
| [LESSONS-v1.0.md](LESSONS-v1.0.md) | **The v1.0 sweep.** The lessons in plain language: witnesses, limits and causes, science, the browser and X_ITE, process; what v1.0 contains and what is open before it is frozen |
| [SCIENCE-PLAYBOOK.md](SCIENCE-PLAYBOOK.md) | **For science- and maths-intensive studies.** The order of work, nine witness patterns (exact references and exact discrete identities, convergence, invariants vs events, measured claims, controls that must fail, the display chain, cross-implementation, reproducibility, units), a numerics cheat-sheet, the builder and page skeleton, and the study card (`kit/templates/SCIENCE-STUDY-CARD.md`) |
| [SOURCES.md](SOURCES.md) | Every input, what it gave, how it was read, and the 14 places sources disagree, each with its resolution |
| [LEARNINGS-from-patches.md](LEARNINGS-from-patches.md) | The seven patches and the Loomsong v1 → v4 history, turned into 25 reusable rules |
| [GLOSSARY.md](GLOSSARY.md) | The words |
| [REVIEW-loom2.md](REVIEW-loom2.md) | Review of the 4 Nov delivery: Cabinet of Worlds, Linked Observatory, Living Archive, Constellation 3 |
| [REVIEW-scientific.md](REVIEW-scientific.md) | Review of the first x3d.STEM delivery, the Scientific Loom Observatory: measurements, six findings, the hardening patch, 13 lessons |
| [ZINC-FINGER.md](ZINC-FINGER.md) | **Zinc fingers under the Loom** (6 Nov): a reference animation audited for truth, the study card, seven phases, and P0 and P1 done on CPU. The metal-site witness (`kit/loom metalsite`: coordination found by element, ligand class and residues, histidine donor, distances, geometry, intact fraction, units) with 25 negative controls; 14 deposited structures with a receipt, a second reader and a census of 32 zinc sites (5 pass as deposited, 9 red with their reasons); 14 data-true X3D Site scenes with a receipt; a review round that found the first witness blind to unnamed ligands, which 2JVX really has; and look v2 (X3D 4.1: physically based materials, a generated studio environment, cages and donor-naming labels), whose reader also checks that zinc is drawn as zinc |
| [X3D-STEM.md](X3D-STEM.md) | **x3d.STEM direction**: one case with four lenses (K-12 to researcher), three fidelity tiers, 11 wow-factor techniques, about 30 project ideas each with its reference control, a roadmap and a maturity ladder |
| [PLATFORMER.md](PLATFORMER.md) | **A game under the Loom** (6 Nov): NIB, an original physics platformer whose levels are X3D files ([x3d.platformer/](x3d.platformer/)), and what it added: the proof-of-play witness `kit/loom play`, the `sim-nonportable-math` page trap, the `x3d-game` profile and a feel card, plus a fix for `kit/loom traps` |
| [DRIFT.md](DRIFT.md) | **A racing game under the Loom** (6 Nov): KANSEI, an original drift-racing game whose circuits and cars are X3D files ([x3d.drift/](x3d.drift/)): five circuits, four cars, five modes, a deterministic tyre-and-drivetrain sim with its AI rivals inside it, and the `x3d-drift` profile (a handling card witness, race and tandem tapes replayed in the browser) |
| [COLLIDER.md](COLLIDER.md) | **The Loom Collider** (6 Nov): a collider-event demo in X3D, demo not STEM, a shader on every particle. Real generator events, the light plausibility witness `kit/loom hepevent` (v2 after an independent review: 206 negative controls, mutation pass 161 of 161), look v2 with merged ribbon tracks, muons through the calorimeter and a spiky crown from the event's own towers, a dijet hero event, X_ITE measurements, and stills up to 8,855 tracks on 9 shader programs |
| [proposals/](proposals/) | Patches proposed back to projects (Scientific Loom hardening) |
| [kit/](kit/) | `loomkit` (Python standard library), profiles, templates, examples, tests |
| [runs/](runs/) | This repo's own evidence: Data City through the kit, the fold-back survey, the traps corpus run |

## Use it on a project

1. Paste [kit/templates/KICKOFF-PRE.md](kit/templates/KICKOFF-PRE.md) and [HANDOFF-POST.md](kit/templates/HANDOFF-POST.md) as the first message, with `LOOM-v1.md` attached.
2. Run the witnesses into a run folder outside the project, then accept and write a receipt:

```bash
kit/loom grammar  PROJECT --evidence RUN/evidence --files 'path/*.x3d'
```
```bash
kit/loom traps    PROJECT --evidence RUN/evidence --files 'path/*.x3d' --host strict
```
```bash
kit/loom command  PROJECT --evidence RUN/evidence --name truth -- python3 -m your.gate args
```
```bash
kit/loom foldback PROJECT --evidence RUN/evidence --patch PROJECT/integration/your.patch
```
```bash
kit/loom play     PROJECT --evidence RUN/evidence --tapes 'tapes/*.tape.json' --levels 'levels/*.x3d' --runner tools/replay.mjs
```
```bash
kit/loom record   PROJECT --evidence RUN/evidence --name eyes --status not_run --reason "why"
```
```bash
kit/loom accept   PROJECT --evidence RUN/evidence --profile kit/profiles/x3d-static.json
```
```bash
kit/loom receipt  PROJECT --evidence RUN/evidence --profile kit/profiles/x3d-static.json --subject "name" --out RUN/receipt.json
```

Exit codes: 0 passed, 1 contract violation (a stable code is printed), 2 instrument or input error. Set `LOOM_PYFLAGS=-O` to run everything optimised; the gates still hold. Grammar and Meaning use the x3d_mcp fork at `~/Projects/x3d/x3d_mcp`, or `--fork` / `LOOM_FORK` to point elsewhere.

## Publishing (law 16)

`kit/loom sweep . DEST --rules kit/profiles/public-sweep.json` writes a public copy: model and vendor names become neutral labels, costs and Drive ids are withheld, and the copy fails if any forbidden pattern survives (`SWEEP-REPORT.json`). The rules file stays private, since it lists the names it removes.

## Check that the kit works

```bash
python3 -I kit/tests/test_gates.py
```
```bash
kit/examples/run_data_city.sh
```
```bash
python3 -I kit/tests/test_metalsite.py && kit/examples/run_zinc_site.sh
# P1 (needs a python3 with MDAnalysis on PATH, and the validator fork for the scenes):
# kit/examples/run_zinc_structures.sh runs/zinc-structures-20261106 && kit/examples/run_zinc_scenes.sh runs/zinc-scenes-20261106 && kit/examples/run_zinc_scenes_v2.sh runs/zinc-scenes-v2-20261106
```
```bash
python3 -I kit/examples/check_all_foldbacks.py
```

The first runs 56 negative controls, 11 two-sided trap rules and 7 page-trap rules (with 10 page forms) under normal Python and `-O`, including the play witness and the CLI itself. The second takes the delivered Data City Loom (copied, never edited), accepts it under `x3d-static/v1`, writes a receipt, then shows that a post-witness edit and a planted trap are both rejected. The third applies every PR patch from the project zips in an empty repo and runs its smoke test both ways.

## Where it stands (3 Nov)

- Kit: tested (C). Data City: accepted under the static profile; its browser witnesses are visibly not run. Fold-backs: 4 of 5 pass; the IFC one fails its own positive control on this Mac (platform-dependent triangulation). Both loose patches reproduce their newer versions (projects agent).
- Not done here: browser witnesses, real-GPU anything, running the rules on x3d.onto's corpus, promoting any fold-back into its target repo. These wait on your word or on the projects agent. See LOOM-v1.md §10.

## Public snapshot (5 Nov)

The public repository [hagsmac/x3d.loom](https://github.com/hagsmac/x3d.loom) holds a **leak-swept snapshot** of this repository: one commit per publication, made by `kit/loom sweep` with the rules in `kit/profiles/public-sweep.json` (the rules file itself is not published). The full working history stays private. The snapshot's `PUBLIC-SNAPSHOT.md` names the private commit it was made from and the rules' sha256, and `SWEEP-REPORT.json` lists every file the sweep changed. The companion studies are public at [hagsmac/x3d.STEM](https://github.com/hagsmac/x3d.STEM).

## On GitHub (4 Nov)

A leak-swept copy is proposed into hagopjay/x3d.onto as `loom/v1/` ([#10](https://github.com/hagopjay/x3d.onto/pull/10)), from the fork hagsmac/x3d.onto. The five project fold-backs are separate PRs, each adding one `tools/<name>/` unchanged: Gear [#11](https://github.com/hagopjay/x3d.onto/pull/11), Break-the-Loom [#12](https://github.com/hagopjay/x3d.onto/pull/12), Data City [#13](https://github.com/hagopjay/x3d.onto/pull/13), Loomsong IV fidelity [#14](https://github.com/hagopjay/x3d.onto/pull/14), IFC bridge [#15](https://github.com/hagopjay/x3d.onto/pull/15) (flagged: fails its own positive control on arm64). The 4 Nov fold-backs followed: Gobbler Cabinet [#16](https://github.com/hagopjay/x3d.onto/pull/16) and Linked Observatory [#17](https://github.com/hagopjay/x3d.onto/pull/17). None is merged; merging is yours (this machine's account has no write access).
