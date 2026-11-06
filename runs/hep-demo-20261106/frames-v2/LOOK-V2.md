# Look v2: first light of the collider demo in X_ITE

Date 2026-11-06. A demo, not a physics study: the events are real generator output (Pythia 8.318, 13.6 TeV pp), the detector response is a truth-level toy (`kit/examples/hep/hep_response.py`), and the look is chosen for beauty under the hep-event plausibility witness.

**Instrument for every frame and number here:** X_ITE 16.5.1 (npm, fetched by `kit/examples/hep/render/fetch_xite.sh`), headless Chromium with software GL (SwiftShader through ANGLE), Playwright, 960x540 at deviceScaleFactor 1, `kit/examples/hep/render/shots.cjs` with `site/shot.html`. Load times are the CPU time of `loadURL` on a 4-vCPU box. **No frame rate is quoted: only software GL ran.** Pixel statistics come from `kit/examples/hep/feas/imgtools.py stats`.

## What changed from look v1

| part | look v1 (`build_event_scene.py`, default) | look v2 (`--look v2`) |
|---|---|---|
| tracks | one Shape per track, `IndexedLineSet`, 1 px lines | screen-space ribbons, all tracks in a few merged `TriangleStripSet` Shapes (`trkset_<n>`, at most 600 tracks each), ONE shared `ComposedShader` |
| per-track identity | attributes on each track's own Shape | the same attributes per vertex inside the merged strips: `a_ident` (id, charge, pT, birth s), `a_arc`, `a_species`, `a_next`, `a_look` (side, seed, drawn length, kind) |
| zero-area crash trap | not reached (lines) | every ribbon vertex pair is offset by -/+ (4, 2.8, 1.2) mm; the vertex shader takes it off; the spec declares the offset so the witness takes it off too |
| muons | stop at the tracker like everything else | the only particles drawn on through the calorimeter, straight along their exit tangent, out through two rings of muon stations (`muext_<n>`) |
| calorimeter | box towers | a thin spiky crown: each event tower becomes 3 to 14 radial spikes inside its own (eta, phi) cell, length and light from its real energy (`twrset_<n>`, attribute `a_cell` = id, E, em fraction, arrival s) |
| colour | species and charge | species and charge for tracks (+ hadron azure, - hadron magenta, electron emerald, muon violet-white, proton coral, photon orange dashed, neutral hadron gold dashed); crown hue is energy (blue low, orange high, so the jets run hot), EM towers lean gold |
| detector | thin shells | Fresnel glass shells with ribs and an end-edge glow, the calorimeter face glowing where the energy landed, dark steel muon stations and struts |
| light | page-level only | additive everywhere (BlendMode ONE ONE, DepthMode readOnly: order independent), tone-mapped inside every shader (X_ITE's ToneMapping option does not touch ComposedShader output), billboard flash, fbm haze, native ParticleSystem sparks |
| time | one clock | one clock (`TimeSensor DEF clock`, 12 s) drives every shader through `u_phase`: growth front at 0.9 m/s slow motion, travelling pulses, tower light-up, flash, ripple, haze drift |
| bloom | none | optional, a separate file per view: the whole scene inside a `RenderedTexture`, sampled by a full-screen threshold-blur shader (X3D 4.1). The un-bloomed scene is the witnessed candidate |

## Frames (all from scenes byte-identical to the accepted candidate in `../candidate/events-v2/`, except the pile-up rows)

| file | event | view | time in the 12 s cycle | load CPU ms | shader programs | draw calls | console errors |
|---|---|---|---|---|---|---|---|
| hero_endon.jpg | pythia-qcd-demo (497 tracks, 132 towers) | end-on | 6.5 s | 984 | 9 | 189 | 0 |
| hero_endon_bloom.jpg | same | end-on, bloom | 6.5 s | 1230 | 10 | 196 | 0 |
| hero_endon_bloom_t2.jpg | same | end-on, bloom | 2.0 s (tracks growing, crown dark) | 1021 | 10 | 211 | 0 |
| hero_endon_bloom_t35.jpg | same | end-on, bloom | 3.5 s (crown lighting) | 1027 | 10 | 212 | 0 |
| hero_three_quarter.jpg / _bloom | same | three-quarter | 6.5 s | 937 / 932 | 9 / 10 | 174 / 213 | 0 |
| hero_side.jpg / _bloom | same | side | 6.5 s | 956 / 1004 | 9 / 10 | 112 / 212 | 0 |
| zmumu_endon_bloom.jpg | pythia-zmumu (462 tracks, both muons drawn out through the muon system) | end-on, bloom | 6.5 s | 972 | 10 | 236 | 0 |
| zmumu_three_quarter_bloom.jpg | same | three-quarter, bloom | 6.5 s | 948 | 10 | 236 | 0 |
| pileup7_endon.jpg / _bloom | 7 merged collisions: 3,238 particles, 2,738 tracks, 713 towers (12.0 MB scene) | end-on | 6.5 s | 3676 / 3502 | 9 / 10 | 309 / 333 | 0 |
| pileup7_three_quarter_bloom.jpg | same | three-quarter, bloom | 6.5 s | 3287 | 10 | 334 | 0 |
| pileup24_endon.jpg | 24 merged collisions: 10,575 particles, 8,855 tracks, 1,707 towers, 11,866 spikes (35.6 MB scene, 15 merged track Shapes) | end-on | 6.5 s | 9949 | 9 | 504 | 0 |

Every frame logged 0 shader compile or link errors. `SHA256SUMS` lists the files.

**A shader on every particle, kept (C):** 8,855 tracks render with 9 linked programs in the whole page, because every track shares one ComposedShader and carries its own identity in per-vertex attributes. The measured alternative, one program per track, costs 11 to 18 ms of load each and does not dedupe (`docs/COLLIDER-XITE-FEASIBILITY.md` section 2).

The pile-up events are not committed (3.7 MB and 1.2 MB of event JSON). They pass the hep-event witness (8,855 tracks judged in 6.8 s CPU) and regenerate from the generator: `pythia_fixtures.py OUT --process qcd --events 1 --seed 31 --pileup 7` (and `--pileup 24`). Their frames are therefore not under the receipt (L for "the committed builder draws exactly this").

## Against the reference still (the look target, kept private with the film)

| statistic | reference still | look v1 best (feasibility, bloom) | look v2 hero end-on, bloom | look v2 pile-up 7 end-on, bloom |
|---|---|---|---|---|
| mean luma | 0.190 | 0.186 | 0.156 | 0.286 |
| median luma | 0.105 | 0.059 | 0.050 | 0.138 |
| p99 luma | 0.887 | 0.968 | 0.962 | 1.000 |
| hue share blue | 56% | 58% | 72% | 40% |
| hue share violet/magenta | 13% | 3% | 12% | 21% |
| hue share red/orange | 7.5% | 1.4% | 4.5% | 9.6% |
| hue share amber/yellow | 12.6% | not recorded | 8.9% | 26% |
| hue share cyan | 9.7% | 18% | 2.1% | 2.3% |

Hue shares count pixels whose brightest channel exceeds 0.25.

What closed (C, looked at every frame): end-on framing with the crown at about 0.85 of the half-height; thin spiky crown on a thin bright face ring; loopers visible; magenta back on target; orange tripled; glassy rings with rim glow; machinery at the frame edges; only muons pass the calorimeter; tracks curve by pT (the witness fits every drawn path); crown energy clusters where particles land (it is the event's own towers).

What still differs:
- The hero event is low-energy (median tower energy 0.71 GeV, 22% EM by energy), so its crown runs blue more than the reference's orange. Hue follows energy by design; the pile-up events run hot.
- Blue is over-represented (72% vs 56%) and cyan is under (2% vs 10%): the steel and glass carry blue, and the tracks are magenta-azure rather than cyan. A cyan species ramp for positive hadrons would close it.
- The reference has a dense textured machinery backdrop; v2 has dark steel slabs with lit edges (L: textured geometry or a baked Blender backdrop is the next step).
- Mean luma is low on the hero (0.156 vs 0.190) and high on pile-up 24 (the crown saturates white-gold).
- Bloom is LDR (an 8-bit RenderedTexture): highlights clip before they blur (S on whether a float texture would work in X_ITE).
- Merged ribbons are hard to pick with a TouchSensor (17.5% in the feasibility bench): per-track picking needs proxies, not built yet.
- Real GPUs were never used: every frame here is software GL.

## Reproduce

```
kit/examples/hep/render/fetch_xite.sh                       # X_ITE 16.5.1 into render/site/x_ite (not committed)
python3 -I kit/examples/hep/build_event_scene.py kit/examples/hep/fixtures/pythia-qcd-demo.event.json kit/examples/hep/render/site/scenes --look v2 --bloom
cd kit/examples/hep/render && SETTLE=3000 node shots.cjs OUT "scenes/pythia-qcd-demo.bloom.endon.x3d|hero_endon_bloom|vp=vp_endon&t=6.5"
```
