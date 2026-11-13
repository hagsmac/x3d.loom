# x3d.mol

Public protein structures written as X3D 4.0, checked by a validator and by a second, independent reader, and drawn in the browser by Babylon.js on WebGPU (WebGL2 when WebGPU is missing). It extends the zinc-finger study ([../ZINC-FINGER.md](../ZINC-FINGER.md)) from 14 deposited structures to AlphaFold models with their confidence (pLDDT) and predicted aligned error (PAE), and adds a Blender stage whose cartoons come back as validated X3D.

X3D is the only output format here. "Valid is not the same as visible": every scene also passes a witness that reads the source structure and checks the drawing against it.

## What is in it

| Path | What it is |
|---|---|
| `src/build.py` | Builder: pinned PDB and AlphaFold DB files to `scenes/*.x3d` and `scenes/catalog.json`. Cartoon by Catmull-Rom spline and superellipse sections, secondary structure by DSSP (pydssp), zinc sites with donor bonds, labels and cages, pLDDT and B-factor per residue, PAE as half-angstrom integers, all in `WorldInfo` metadata |
| `src/witness.py` | Independent checker with its own PDB/mmCIF line parser (no gemmi): residues, C-alpha path, trace, units, pLDDT, colours, secondary-structure format, zinc sites, donors, bonds, labels, cages, PAE. Stable fail codes |
| `tests/test_witness.py` | 18 negative controls (each must be refused) and 6 positive controls |
| `tools/run_all.py` | Build, rebuild for determinism, fork validator, witness, controls, then `scenes/receipt.json` |
| `viewer/` | `reader.js` (X3D to a plain model), `body.js` (Babylon.js body), `app.js` (catalogue, colour schemes, residue picking, zinc labels, PAE map, receipt card, Blender tab), `template.html`, `build_page.py` |
| `docs/` | The page, ready for GitHub Pages: `index.html`, gzip'd scenes, catalog, receipt, credits, and the Blender cut in `docs/cinema/` |
| `blender/molcine.py` | Blender stage: molecularnodes cartoon in headless Blender, Cycles CPU still, the evaluated mesh written as X3D by x3d-blender-io, `cinema/receipt.json` |
| `blender/gate_export.py` | Gate for the Blender X3D: fork validator plus a data-true witness (C-alpha and C4' within 4 angstrom of the mesh, no stray geometry, zinc present, pLDDT colours match the nearest residue) and four altered copies that must be refused |
| `src/anim.py` | AlphaFold 3 diffusion illustration: the AlphaFold 3 noise schedule (EDM form, sigma_data 16, s_max 160, s_min 4e-4, rho 7) run backwards onto the known atoms of 1AAY and the p53 AlphaFold model, written as X3D keyframes (`TimeSensor` 12 s loop, `CoordinateInterpolator`, `PointSet`) in `scenes/anim/`. An illustration, not a live run; every file says so |
| `src/anim_witness.py`, `tests/test_anim_witness.py` | Witness for the keyframes (last key and rest pose equal the source atoms within 0.002 angstrom, matched by position; noise follows the stated schedule; routes wired after the nodes; palette) and 17 refusal controls plus 4 passes |
| `viewer/diffuse.js` | The diffusion player: follows the file's ROUTEs, interpolates as `CoordinateInterpolator` does, draws atoms as instanced spheres; play, pause, scrub, follow camera; the cartoon fades in at the end and the PAE map fills in |
| `blender/diffcine.py` | Cycles film of the same keyframes (`cinema/<id>-diffusion.mp4`), with a per-frame log in `cinema/diffusion.json` |
| `tools/proof.js`, `tools/interact.js`, `tools/anim_proof.js` | Headless Chromium proof frames and interaction checks (SwiftShader: correctness only, never timing) |
| `data/` | Pinned inputs with their hashes: `pdb/` (14 entries, `CITATIONS.json`), `afdb/` (5 models and PAE files, `PINS.json`), `credits/lab-papers.json` |

## Run it

```bash
# builder, witness, controls, receipt  (python with gemmi, numpy, lxml, pydssp; the x3d_mcp fork with its own .venv)
XMOL_FORK=/path/to/x3d_mcp python3 -I tools/run_all.py
python3 -I viewer/build_page.py                       # docs/index.html and docs/scenes, docs/cinema

# Blender stage  (Python 3.13 venv: pip install bpy==5.3.0 molecularnodes==520.2.0 nodebpy==520.25.0)
python -I -W ignore blender/molcine.py --out cinema --targets AF-P04637-F1,AF-P25490-F1,1aay,1ubd --samples 96
XMOL_FORK=/path/to/x3d_mcp python3 -I blender/gate_export.py cinema/receipt.json

# proofs  (Node with Playwright; a local copy of babylonjs@9.32.0/babylon.js for offline runs)
node tools/proof.js --docs docs --babylon /path/to/babylon.js --out proof --q low
node tools/interact.js --docs docs --babylon /path/to/babylon.js --out proof-interact
node tools/anim_proof.js --docs docs --babylon /path/to/babylon.js --out proof-anim

# diffusion film  (same Blender venv; ffmpeg on PATH)
python -I -W ignore blender/diffcine.py --out cinema --targets AF-P04637-F1,1aay
```

`scenes/*.x3d` is not committed: the build is deterministic and `scenes/receipt.json` names each file's sha256; the page carries the same files gzip'd. Likewise the Blender stage's PNGs and plain X3D stay local and the repository keeps the JPEG stills and `.mn.x3d.gz`, whose uncompressed sha256 is in `cinema/receipt.json`.

## Measured, 12 November 2026

Every number names its instrument. Rig for the browser checks: headless Chromium 153, SwiftShader (software). No GPU timing is claimed anywhere.

| Check | Instrument | Result |
|---|---|---|
| 19 scenes, XSD and semantic | x3d_mcp fork `validate_xml` + `semantic_diagnostics`, commit 13121b68e6d9 | 19 of 19 valid, 0 semantic errors |
| 19 scenes, data-true | `src/witness.py` | 19 of 19 pass |
| Witness controls | `tests/test_witness.py` | 18 negative refused, 6 positive passed |
| Determinism | `tools/run_all.py` (second build) | identical sha256 for 19 scenes |
| Page, WebGL2 | `tools/proof.js` | 19 of 19 scenes drawn, no console errors |
| Page, WebGPU | `tools/proof.js --gpu 1` (offscreen texture) | boots on WebGPU for 2 scenes with no errors; pixels not judged headless |
| Interaction and layout | `tools/interact.js` | 29 of 29: PAE hover, lock and Escape, residue hover and pin, colour schemes, no overlap at 1280, 1024 and 390 px, the Blender tab and its download |
| Blender X3D, 4 files | same fork commit + `blender/gate_export.py` | 4 of 4 XSD valid, 0 semantic errors, witness pass; C-alpha within 1.68 angstrom of the mesh (median 0.4); pLDDT colour agreement 98.3% and 98.6%; zinc within 1.11 angstrom; 16 of 16 controls behaved |

## Measured, 13 November 2026: the AlphaFold 3 diffusion illustration

| Check | Instrument | Result |
|---|---|---|
| 2 keyframe scenes, XSD and semantic | x3d_mcp fork, commit 13121b68e6d9 | 2 of 2 valid, 0 semantic errors, 0 warnings |
| Keyframes, data-true | `src/anim_witness.py` | 2 of 2 pass: 1AAY 1,160 atoms (3 zinc), p53 3,060 atoms, 41 keys each; last key on the source atoms within 0.002 angstrom |
| Witness controls | `tests/test_anim_witness.py` | 17 negative refused, 4 positive passed (including a shuffled atom order) |
| Determinism | `tools/run_all.py` | identical sha256 on a second build |
| Player | `tools/anim_proof.js` | 39 of 39: drawn atoms at the end equal the file's rest pose (0 angstrom), the first frame carries the stated noise (33.24 and 70.12 angstrom rms), play, pause, scrub, space, follow, exit, receipt, disclaimer, PAE fill-in, no overlap at 1280, 1024 and 390 px |

What the illustration is and is not: AlphaFold 3 builds coordinates with a diffusion module that starts from noise and denoises in about 200 steps on this schedule. Here no network runs: each frame is the final atoms plus scheduled, seeded noise (AR(1) in time, so atoms drift), capped at `cap * tanh(sigma / cap)` so it fits the screen. In the p53 model, atoms with low pLDDT carry extra restless noise that still ends at zero, so the confident core settles first. A real run is the OpenFold3 item under Future development.

## Known gaps

- The live viewer reads only what `src/build.py` writes. The Blender X3D is offered as a download beside its still, not drawn live yet.
- WebGPU frames are not judged headless, and nothing has been timed on a real GPU. On Windows Chrome with an older Intel GPU, `chrome://flags/#enable-unsafe-webgpu` may be needed.
- x3d-blender-io (commit in `cinema/receipt.json`) writes vertex colours unclamped, and the molecularnodes pLDDT palette has channels of 1.000169, which the X3D 4.0 XSD refuses. The stage clamps them and counts how many in the receipt; the exporter fix is a one-line clamp where `ColorRGBA` is emitted.
- The Blender X3D keeps `ColorRGBA` with alpha 1 everywhere; converting it to `Color` would shrink it.
- The Cycles film (`blender/diffcine.py`) is written and tested on single frames, but the full 2 x 288-frame render has not been run yet, so no `.mp4` ships; the page shows the film card only when `cinema/diffusion.json` exists.
- The diffusion frames are an illustration on known coordinates, not a prediction; a live OpenFold3 run needs a GPU and the owner's yes.
- The AlphaFold 3 output reader and a finder for candidate zinc sites in predicted models are not built.
- The witness shares written rules with the builder (guide smoothing, ring layout, palette, the 2.5 and 3.0 angstrom zinc rules, the 800-residue focus rule); it is independent in parsing and arithmetic only.

## Credit and licences

See [NOTICE.md](NOTICE.md). This project is independent: the laboratories and databases credited there did not review or endorse it.
