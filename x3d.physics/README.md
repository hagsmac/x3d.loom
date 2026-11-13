# x3d.physics

Two physics bridges built under the Loom, collected so that what they learned stays in the Loom (13 November 2026). The method they added is in [PHYSICS-PLAYBOOK.md](../PHYSICS-PLAYBOOK.md); the witness is `kit/loom physics`; the laws are 41 to 43 and the failure modes 124 to 147 in [LOOM-v1.md](../LOOM-v1.md).

| Folder | What it is | Source commit |
|---|---|---|
| [physx-bridge/](physx-bridge/) | **X3D with PhysX 5.** Standard X3D 4.0 RigidBodyPhysics scenes run on PhysX 5.12 (WASM, in a Web Worker) under X_ITE 16.7.0, with X_ITE's own Bullet engine switched off. Seven demos and a side-by-side page: the marble machine, music box, draw-a-domino run, trebuchet vs castle, Galton board, the stairs of doom (an H-Anim ragdoll: a crash-test dummy and a cartoon person, with cannon, wrecking ball, heat map and head score) and the dummy barrage. SPEC.md (draft 1.0), SPEC-RAGDOLL.md, evidence for five phases | `9a694e9` of `x3d-physx-bridge` (local git, no remote) |
| [mujoco-bridge/](mujoco-bridge/) | **X3D with MuJoCo.** MuJoCo 3.17 (WASM) behind X3D scenes, Apache-2.0, release 0.2.0; Gate 0 (84 tests and 19 threat checks), a threat model, a licence review, an agent slice, a guided tour | `069ddd3` of `x3d-mujoco-bridge/bridge` (local git, no remote) |
| [ten-minute-physics/](ten-minute-physics/) | **Ten Minute Physics ports, six batches (own code, credit to Matthias Müller).** Errata of the independent review, two field guides, the generator scripts and committed limits. Scenes and records live in `hagopjay/x3d.demo` | |
| [notes/](notes/) | The two sibling threads' own hand-over notes | |
| [runs/](runs/) | **The two PhysX run records** (`loom.physics-run/1`), built from the bridge's evidence | |
| [tools/](tools/) | `physx_run_record.py` (evidence to records) and `physx_controls.py` (14 negative controls on the real records) | |
| [SWEEP-REPORT.json](SWEEP-REPORT.json) | The leak sweep of this folder: 7 files rewritten, 44 replacements, 0 residue | |

## What is shown, and what is not

**Shown** (read from the bridge's own evidence; `runs/physx-grand-cascade-*.physics.json`):

- **Determinism.** A 1918-step run recorded in Chromium and a 969-step run recorded in Firefox each replay with 0 differing state hashes in Chromium, Firefox 146, WebKit 26 and Node 24. Trace sha256: `c8b3cc3f…` (Chromium) and its Firefox twin in the record.
- **Exact references** on PhysX 5.12 in Node: free fall 1.5e-6 m from the discrete solution (limit 1e-4), pendulum 1.4e-5 relative (0.5 %), restitution 7.2e-8 (1e-3), incline 0.98 % (2 %), CCD tunnelling 0 of 40 phases; the control, CCD off, tunnels in 10 of 40.
- **The takeover.** X_ITE's Bullet is off in Chromium, Firefox and WebKit; one leak (`loadURL()` runs one step) is handled.
- **11 ODE-only fields** reported as lost, not dropped.
- **3 waivers**, the smoke tests that failed under load (Galton 220 and 223 of 240 beads against 225; the music box in WebKit, 15 of 18 pegs in the worse turn).

**Not shown, on purpose:**

- Another machine (every replay ran on this Mac), a real GPU, listening, a paired visual review.
- **The ragdoll has no run record**: its per-step hashes were not persisted. Its limit overshoot (0.43 rad against 0.2) and the Gravitron gap (2.97 against 2.22 rad/s, 34 %) are in the evidence and the playbook, and in no record.
- **MuJoCo has no run record**: its checkpoint replay is a phase-1 item in its PLAN. Only Gate 0 and the failure modes carry over.
- The profile `x3d-physics-physx/v1` was **not run to acceptance**: only its `physics` witness ran here (`runs/physics-20261113/`). Grammar, Meaning, Traps, Page traps and Behaviour on these scenes need the x3d_mcp fork checkout and a browser; the bridges' own validation (all 16 generated scenes 0 errors, 0 warnings) and browser suites are cited, not repeated.

## Reproduce

```bash
python3 -I x3d.physics/tools/physx_run_record.py
```
```bash
kit/loom physics x3d.physics --evidence runs/physics-20261113/evidence --runs 'runs/*.physics.json' --hosts chromium,firefox,webkit,node --max-waivers 3 --require-takeover
```
```bash
python3 -I x3d.physics/tools/physx_controls.py
```
```bash
python3 -I kit/tests/test_gates.py
```

The first rewrites the records from `physx-bridge/evidence/`; it reads, it does not measure. The second is the witness. The third attacks the real records (an edited step hash, a missing replay, a widened limit, a lowered waiver cap, ...) and requires each intended code. The fourth is the kit's own self-test (82 controls, normal Python and `-O`).

To run the bridges themselves, see [physx-bridge/README.md](physx-bridge/README.md) and [mujoco-bridge/README.md](mujoco-bridge/README.md) (Node 24; `npm install`; Playwright for the browser suites). `tools/validate_one.py` reads the x3d_mcp checkout from `X3D_MCP`.

## What was left out, and what was changed to publish this

Law 16: this folder went through `kit/loom sweep` (rules kept private) before it was put here.

| Left out | Why |
|---|---|
| `node_modules/`, `dist/`, test results, caches | rebuilt by `npm install` and `npm run build` |
| MuJoCo `docs/X3DUOM-4.0.xml` and `docs/schemas/` | large third-party standard files, reproducible from the X3D standard |
| the MuJoCo release archives (`X3D-MuJoCo-Bridge-0.2.0.zip`, 14.2 MB, and the source zip) | rebuilt by `scripts/package-release.py`; `release/SHA256SUMS.txt` is kept |
| `evidence/agent-demo/transcript.jsonl` | it exposed local plugin configuration and cannot be swept safely; `calls.json`, `prompt.txt` and `mcp-config.json` are kept with local paths replaced by `<project>`, `<x3d_mcp-agents-slice>`, `<x3d_mcp>` |
| the MuJoCo brief as a PDF | a binary the sweep cannot scan; the HTML brief is kept |

| Changed | Why |
|---|---|
| personal and local paths, account names, cost figures and vendor names in 7 files and in text-like logs, notebooks and `.ts` files | the sweep's replace-and-forbid rules (44 replacements, 0 residue) |
| `physx-bridge/THIRD_PARTY_NOTICES.txt`: one third-party copyright holder's e-mail address replaced with `[email withheld]` | the sweep forbids addresses; the rest of the notice and the licence texts in `physx-bridge/licenses/` are verbatim (checked byte for byte against the source) |
| debug probe imports made relative; `tools/validate_one.py` takes `X3D_MCP` | the originals pointed into a local checkout |

## Licences

- PhysX 5 is BSD-3-Clause (`physx-bridge/licenses/NVIDIA-PhysX-BSD-3-Clause.md`, verbatim); `physx-js-webidl` is MIT, X_ITE is MIT, ammo.js is zlib.
- `mujoco-bridge/` is Apache-2.0 (`LICENSE`, `NOTICE`; `LICENSE-REVIEW.md` records that the owner confirmed they hold the rights to the two archives and the generated code and chose Apache-2.0).
- `physx-bridge/` is Apache-2.0 too (`LICENSE`, and `"license"` in its `package.json`), added at the owner's word when it was collected here; the third-party texts above stay verbatim. No copyright line was added (the MuJoCo bridge's `NOTICE` names the owner; add the same to `physx-bridge/` if wanted).

## Decisions carried over from the threads

Tolerance over precision ("some error and sloppiness tolerance"); a character that would mock real addiction was declined and the ragdoll stays cartoon, with no gore; both phase-1 defaults of the PhysX bridge were kept by the user (inertia from shapes; `minBounceSpeed` raised); the MuJoCo bridge was licensed Apache-2.0 on the user's confirmation. The threads are the sources; this folder does not decide any of it again.
