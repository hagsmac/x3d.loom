# The Loom Collider: a collider-event demo in X3D

Date 2026-11-06. Status: look v2 after an independent review (witness v2, profile `hep-demo/v2`), a score and a time-dilation page, and look v3: the best of an outside fidelity pass folded into the builder and witnessed ([docs/COLLIDER-LOOK-V3.md](docs/COLLIDER-LOOK-V3.md)). **A demo, not STEM:** the physics only has to be plausible, and the effort goes into graphics. Every particle gets its own animated shader look, and the X3D file is still one an AI can be held accountable to.

Grades follow the Loom: **C** is measured here with the named instrument, **L** is read or reasoned from sources, **S** is suspected.

## The pipeline (the zinc-finger route: reference film, truth audit, X3D rebuild)

```
 look target                truth audit                 generator                     candidate                    witnesses
 hosted image and video  -> keep: end-on view,       -> Pythia 8 pp events        -> scene builder              -> hep-event (plausibility)
 models make a hero still   loopers, crown;             (13.6 TeV, committed         build_event_scene.py          traps (11 known traps)
 and an 8 s film (private)  fix: only muons pass the    fixtures, plus pile-up)      --look v1 | --look v2          receipt, acceptance under
                            calorimeter, tracks curve   + truth-level toy             (one DEF'd shader per role,   hep-demo/v2
                            by pT, crown follows the    response (hep_response.py)    per-vertex identity)         render: X_ITE stills
                            energy, colour = meaning                                                                (frames, 0 errors)  
```

The reference media and their ledger are private: they stay off this public snapshot. Only what was built from them is here.

## What is here

| path | what |
|---|---|
| [docs/HEP-EVENT-WITNESS.md](docs/HEP-EVENT-WITNESS.md) | The witness: event format `loom.hep-event/1`, spec, ten stable codes, controls, findings from real generator output, limits |
| [docs/COLLIDER-XITE-FEASIBILITY.md](docs/COLLIDER-XITE-FEASIBILITY.md) | X_ITE 16.5.1 measured: load matrix, a shader on every particle at 300 and 3,000 tracks, the zero-area crash trap, transparency, the freeze trap, picking, glTF, the look recipes (GLSL that rendered) |
| [docs/COLLIDER-SURVEY.md](docs/COLLIDER-SURVEY.md) | Survey of generators, detector toolkits, event formats, open data and event displays, each graded |
| [docs/COLLIDER-LOOK-V3.md](docs/COLLIDER-LOOK-V3.md) | Look v3: an outside fidelity pass sorted into what was kept and what was left, with evidence; the v2, outside and v3 frames and their statistics are in `runs/hep-demo-v3-20261106/frames/` |
| [runs/hep-demo-v2-20261106/frames/LOOK-V2.md](runs/hep-demo-v2-20261106/frames/LOOK-V2.md) | After review: 13 stills of the accepted scenes (dijet hero, soft QCD, Z to mu mu, pile-up 7 and 24), load times, pixel statistics v2 against the target, what still differs |
| [runs/hep-demo-20261106/frames-v2/LOOK-V2.md](runs/hep-demo-20261106/frames-v2/LOOK-V2.md) | First light, kept as history: those frames wrote depth (see the correction in the new LOOK-V2.md) |
| `kit/loomkit/hepevent.py`, `kit/loom hepevent` | The witness (standard library) |
| `kit/examples/hep/` | Scene builder (look v1, v2 and v3), exact events, Pythia converter, toy response, fixture selection, five committed fixtures (the dijet hero added), the spec |
| `kit/examples/hep/render/` | Stills harness (`fetch_xite.sh`, `shots.cjs`, `site/shot.html`) |
| `kit/examples/hep/feas/` | The feasibility harness and generators behind the measurements |
| `kit/profiles/hep-demo.json` | Acceptance profile `hep-demo/v2` |
| `kit/examples/run_hep_event.sh`, `runs/hep-demo-v2-20261106/` | The rehearsal and its receipt (`runs/hep-demo-20261106/` is the v1 run) |
| `kit/examples/run_hep_v3.sh`, `runs/hep-demo-v3-20261106/` | The look v3 witness run: hep-event and traps pass, scene hashes checked on a rerun |

## Results

| claim | number | instrument | grade |
|---|---|---|---|
| the witness catches what it should | 207 negative controls, each with its intended code and reason; 20 positive (3 for look v3); 2 CLI | `python3 -I kit/tests/test_hepevent.py`, normal and `-O` | C |
| a pass cannot be bought | an independent review's 32 crafted attacks (a USE of the track group, an LOD, a Collision proxy, a 1 mm stub with the right curvature, a rotated or squashed copy, a late birth, a pion coloured as an electron, a needle in the wrong cell, and more) all refused with a fitting reason; 51 controls added for them | the reviewer's attack tools, then `review_controls()` | C |
| every gate has a control | 161 of 161 `need(...)` sites caught when disabled one at a time: 126 by a control failing its own assertion, 35 by a later crash | `kit/tests/mutate_hepevent.py` | C |
| the rehearsal accepts and the gates bite | accepted under `hep-demo/v2` with 10 events and 10 scenes (5 fixtures, look v1 and v2; 3,598 tracks, 1,088 towers); a stale edit, a track deleted in v1 and a strip deleted in v2 all reject; same result under `-O` | `kit/examples/run_hep_event.sh` | C |
| a shader on every particle | 8,855 tracks of a 24-collision pile-up drawn with 9 shader programs in the page, 0 errors, load 10.1 s CPU | X_ITE 16.5.1, headless Chromium, software GL | C |
| the hero event loads fast | dijet hero, 456 tracks, 168 towers, 2,399 needles: about 1 s CPU, 9 programs (10 with bloom) | same | C |
| it looks like the target | dijet hero end-on with bloom: mean luma 0.179 vs 0.190, blue 63% vs 63%, white 25% vs 20%, cyan 7% vs 9%; red missing (0.3% vs 7.5%), mid-tones dark | `imgtools.py stats` v2, and eyes on every frame | C for the numbers, S for "beautiful" |
| first light was not order independent | its `DepthMode readOnly` is not an X_ITE 16.5.1 field and was dropped, so those frames wrote depth; fixed with `depthMask='false'` | X_ITE source and re-render, after review | C |
| look v3 is closer to the target | dijet hero end-on with glow, on the page: mean luma 0.170 vs 0.190 (v2 0.162), median 0.118 vs 0.105 (v2 0.061), blue 63% vs 63%, cyan 12% vs 9%, red 2.7% vs 7.5% (v2 0.2%) | `imgtools.py stats` v2 on `runs/hep-demo-v3-20261106/frames/` | C for the numbers, S for "beautiful" |
| frame rate | not measured | only software GL ran | none |

## Rules this demo keeps

- One DEF'd ComposedShader per role (tracks, towers, shells, flash, haze), USE'd everywhere; per-particle variation in `FloatVertexAttribute`. X_ITE does not dedupe identical programs, so per-track programs would cost about 15 ms of load each (C).
- Merge geometry: one Shape per track costs 27 s at 5,000 tracks; one merged set costs under 4 s at 3,000 (C).
- Offset ribbon vertex pairs: zero-area strips crash the software renderer from about 33,000 vertices (C).
- Tone-map in the shader; X_ITE's ToneMapping option does not reach ComposedShader output (C).
- Guard every host field callback with try/catch (law 32, reproduced on 16.5.1: routing froze at the 13th event) (C).
- Additive glow without depth writes is `DepthMode depthMask='false'`; X_ITE drops unknown fields such as `readOnly` silently, so check a field against the X_ITE source before trusting it (C, found by review).
- Never quote a software-GL frame rate.

## Phases

| phase | what | state |
|---|---|---|
| P0 | survey, feasibility, witness, spec, reference media and truth audit | done |
| P1 | look v2 from real events, witnessed, rendered | done after review (this branch) |
| P2 | the page: the page owns the clock and writes it into the shaders, a time-dilation dial from 1/1000 to 4 times demo speed that runs through zero into reverse, a score generated by a hosted music model that follows the clock like a tape (slows, drops in pitch, plays backwards), three views with a camera fly, bloom on or off, two events page v3: look v3, auto-tour with drag, pinch and wheel, render quality tiers, exposure and bloom, a 4K still, legend, fullscreen, bundled fonts (built; the public copy goes to its own repository); still to do: guided camera from the film's moves, per-track hover data (proxies for picking) |
| P3 | Blender theatre: a baked machinery backdrop exported to X3D, the event inside it | planned |
| P4 | a short film rendered from the X3D scene and set beside the reference film | planned |
| P5 | real GPU measurements, then a public demo page | planned |

## Reproduce

```
python3 -I kit/tests/test_hepevent.py            # both modes
bash kit/examples/run_hep_event.sh               # candidate, witnesses, acceptance, receipt, three controls
kit/loom verify-receipt runs/hep-demo-v2-20261106/receipt.json
```
