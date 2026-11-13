# x3d-physx-bridge

Standard X3D 4.0 RigidBodyPhysics scenes running on NVIDIA PhysX 5 (WASM, in a Web Worker) in the browser, and six demos built on it.
The bridge switches off X_ITE's built-in engine, reads the scene through SAI, builds it in PhysX, and writes the results back as ordinary
X3D events. Every demo exports a standard `.x3d` file that validates (XSD and semantic, 0 errors and 0 warnings).

**Status:** phases 1–4 done; phase 5 (verification) under way, with four more demos added on the way. See `SPEC.md` (draft 0.6) and
`evidence/` (`PHASE-1.md` to `PHASE-4.md`, `DEMOS.md`).

| page | what |
|---|---|
| `index.html` | the hub: every demo with a screenshot |
| `machine.html` | **Marble Machine**: build on a pegboard, run, race X_ITE's Bullet, record and replay (bit-exact across Chromium, Firefox, WebKit and Node) |
| `musicbox.html` | **Physics music box**: pegs on a turning drum lift hammers onto tuned bars; edit the pegs live |
| `dominoes.html` | **Draw-a-domino run**: draw rows, push, time the wave against real dominoes |
| `trebuchet.html` | **Trebuchet vs castle**: counterweight, sling and release angle; knock the castle down |
| `galton.html` | **Galton board**: beads through pins into bins, a live histogram against the binomial, tilt and shake |
| `sidebyside.html` | one file on PhysX and on Bullet side by side |

Every control is a button with its keyboard shortcut printed on it; `?` on a demo page lists them all.

Run it (Node 24; on this Mac `export PATH=/opt/homebrew/opt/node@24/bin:$PATH`):

```
npm install && npm run vendor
npm test            # analytic, joint and mapping tests (PhysX WASM in Node)
npm run dev         # http://127.0.0.1:5181/
npm run build       # dist/, with licences and notices in dist/legal
npm run validate    # export every scene and validate it with the x3d_mcp server
npm run sounds      # resynthesise public/sounds/*.wav and measure their tuning
```

Node tools (each simulates a page's scene in the same PhysX world the browser uses):

```
node tools/musicbox-sim.ts twinkle 120 3       # notes per peg, wrong bars, timing
node tools/domino-sim.ts 40 --save              # wave speed for a sweep of gaps and frictions
node tools/trebuchet-sim.ts 2000 37 5 40       # counterweight kg, stone kg, sling m, release angle
node tools/galton-sim.ts 240 12 0.1 0 0.019 --shake   # beads, rows, bounce, tilt, pin pitch
node tools/machine-sim.ts scenes/machines/grand-cascade.json 20 10
node tools/replay-node.ts run.json             # replay a run saved from a page and compare every step's hash
```

| path | what |
|---|---|
| `SPEC.md` | decisions, architecture, contract, node mapping, demos, verification, plan |
| `src/bridge/` | the bridge: reader, PhysX world (builder, stepper, contacts, impacts), joints, worker, writers, clocks, mapping table |
| `src/machine/` | the Marble Machine's pieces and the IR → X3D emitter shared by every demo |
| `src/demo/` | the Marble Machine page, side by side, sound, looks |
| `src/demos/` | the demo shell and the four new demos (a pure `*-scene.ts` per demo, the page beside it) |
| `scenes/` | standard X3D scenes; `scenes/demos/` holds each demo's export |
| `tests/`, `probes/`, `tools/` | unit tests; browser and Node probes; simulators, exporters, the validator wrapper |
| `evidence/` | measured results and screenshots |
| `THIRD_PARTY_NOTICES.md`, `licenses/` | PhysX (BSD-3-Clause), physx-js-webidl (MIT), X_ITE (MIT), ammo.js (zlib) |

The domino chart shows measurements of real dominoes from Larham, "DEMONic Dominoes" (arXiv:1302.3311), read from the paper, not
measured here.

## Licence

Apache License 2.0 (`LICENSE`), added on 13 Nov 2026 when the bridge was collected into x3d.physics. Third-party components keep their own licences: PhysX 5 (BSD-3-Clause), physx-js-webidl (MIT), X_ITE (MIT), ammo.js (zlib); see `THIRD_PARTY_NOTICES.md` and `licenses/`.
