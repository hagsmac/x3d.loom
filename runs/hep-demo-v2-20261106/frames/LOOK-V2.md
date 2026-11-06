# Look v2, after review: the collider demo in X_ITE

Date 2026-11-06. A demo, not a physics study: the events are real generator output (Pythia 8.318, 13.6 TeV pp), the detector response is a truth-level toy (`kit/examples/hep/hep_response.py`), and the look is chosen for beauty under the hep-event plausibility witness. This replaces nothing: the first-light frames and their notes stay in `runs/hep-demo-20261106/frames-v2/` as history, with the corrections listed below.

**Instrument for every frame and number here:** X_ITE 16.5.1 (npm, fetched by `kit/examples/hep/render/fetch_xite.sh`), headless Chromium with software GL (SwiftShader through ANGLE), Playwright, 960x540 at deviceScaleFactor 1, `kit/examples/hep/render/shots.cjs` with `site/shot.html`, settle 2.5 s. Load times are the CPU time of `loadURL` on a 4-vCPU box. **No frame rate is quoted: only software GL ran.** Pixel statistics come from `kit/examples/hep/feas/imgtools.py stats` **v2** (hue only for pixels that are bright and saturated; white and grey reported as their own "achromatic" share), run on the committed JPEGs (`stats.json`).

## What changed since first light

| change | why |
|---|---|
| `DepthMode depthMask='false'` on every additive Appearance (was `readOnly='true'`) | an independent review found that `readOnly` is not an X_ITE 16.5.1 DepthMode field (its fields are polygonOffset, depthRange, depthTest, depthFunction, depthMask) and X_ITE drops unknown attributes silently. Every first-light frame wrote depth, so near glass hid far tracks and the result depended on draw order. First light's "order independent" was wrong (C, found by reading the X_ITE source and re-rendering) |
| hue statistics v2 | v1 gave hue 0 (red) to every white and grey pixel and had no orange bin; first light's "orange tripled" and "magenta back on target" rested on it and are withdrawn |
| a new hero event: `pythia-dijet-hero` (HardQCD, partonic pT above 400 GeV, seed 41, event 26 of 30) | 41 charged tracks above 5 GeV at abs(eta) below 1, so two hot jets cross the end-on view; the old hero (`pythia-qcd-demo`) is kept as the soft-QCD frame |
| tracks: positive hadrons cyan, width and brightness from log pT, photons and neutral hadrons dashed | cyan was under the target (2% vs 9%) |
| crown: hue from the tower energy relative to the event's own 90th percentile (`u_e90`), 6 to 24 needles per tower stratified across its cell, lengths from log E | a fixed energy scale ran every soft event blue |
| shells: the face-on rib and steel terms fade with the viewing angle; hairline glass rings fill the barrel; luminance soft-knee bloom, gain per view | the side and three-quarter views were washed out by face-on glass |

## Frames (scenes byte-identical to the accepted candidate `../candidate/events-v2/`, except the pile-up rows; bloom files are wrappers of those exact texts)

| file | event | view | time in the 12 s cycle | load CPU ms | programs | draws | errors |
|---|---|---|---|---|---|---|---|
| hero_endon.jpg | pythia-dijet-hero (456 tracks, 168 towers, 2,399 needles) | end-on | 6.5 s | 1020 | 9 | 188 | 0 |
| hero_endon_bloom.jpg | same | end-on, bloom | 6.5 s | 1094 | 10 | 230 | 0 |
| hero_endon_bloom_t2.jpg | same | end-on, bloom | 2.0 s (tracks grown, crown dark) | 984 | 10 | 195 | 0 |
| hero_endon_bloom_t35.jpg | same | end-on, bloom | 3.5 s (crown lit) | 1023 | 10 | 195 | 0 |
| hero_three_quarter.jpg / _bloom | same | three-quarter | 6.5 s | 879 / 972 | 9 / 10 | 174 / 212 | 0 |
| hero_side_bloom.jpg | same | side, bloom | 6.5 s | 1015 | 10 | 229 | 0 |
| softqcd_endon_bloom.jpg | pythia-qcd-demo (497 tracks, 132 towers) | end-on, bloom | 6.5 s | 1307 | 10 | 212 | 0 |
| zmumu_endon_bloom.jpg | pythia-zmumu (462 tracks, both muons drawn out through the muon system) | end-on, bloom | 6.5 s | 1238 | 10 | 236 | 0 |
| zmumu_three_quarter_bloom.jpg | same | three-quarter, bloom | 6.5 s | 1239 | 10 | 237 | 0 |
| pileup7_endon_bloom.jpg | 7 merged collisions (2,738 tracks, 713 towers) | end-on, bloom | 6.5 s | 3473 | 10 | 334 | 0 |
| pileup7_three_quarter_bloom.jpg | same | three-quarter, bloom | 6.5 s | 3494 | 10 | 334 | 0 |
| pileup24_endon.jpg | 24 merged collisions (8,855 tracks, 1,707 towers) | end-on | 6.5 s | 10144 | 9 | 595 | 0 |

Every frame logged 0 shader compile or link errors and 0 console errors (`frames.jsonl`). `scenes.sha256` hashes the scene files that rendered; `SHA256SUMS` hashes everything here.

The pile-up events are not committed (3.7 MB and 1.2 MB of event JSON); they regenerate with `pythia_fixtures.py OUT --process qcd --events 1 --seed 31 --pileup 7` (and `--pileup 24`) and were built by the same builder. They are not under the receipt (L for "the committed builder draws exactly this").

## Against the reference still (the look target, kept private with the film)

| statistic (imgtools stats v2) | reference still | dijet hero end-on, bloom | soft QCD end-on, bloom | pile-up 7 end-on, bloom |
|---|---|---|---|---|
| mean luma | 0.190 | 0.179 | 0.130 | 0.295 |
| median luma | 0.105 | 0.058 | 0.058 | 0.087 |
| bright pixels (brightest channel above 0.25) | 34% | 29% | 26% | 42% |
| achromatic share of the bright pixels | 20% | 25% | 12% | 37% |
| hue share blue | 63% | 63% | 65% | 44% |
| hue share violet/magenta | 6.4% | 11.9% | 5.4% | 14.2% |
| hue share orange | 12.5% | 8.4% | 22.1% | 21.2% |
| hue share yellow | 0.8% | 9.0% | 2.4% | 12.4% |
| hue share cyan | 9.4% | 7.1% | 4.4% | 8.3% |
| hue share red | 7.5% | 0.3% | 0.3% | 0.3% |

What is close (C for the numbers, looked at on every frame): the hero end-on matches the target's brightness (0.179 vs 0.190), its blue share (63% vs 63%) and its white share (25% vs 20%); cyan is near (7% vs 9%); the warm crown is there, split between orange and yellow where the target is orange and red.

What still differs:
- Red is missing (0.3% vs 7.5%): the hottest needles go yellow-white, not red. A red end on the energy ramp would close it.
- Mid-tones are dark (median 0.058 vs 0.105): the target has a lit haze and machinery backdrop, v2 has dark steel and a faint haze (L: a baked Blender backdrop is the next step).
- The oblique views are almost all blue (96 to 99% of the coloured pixels): the crown needles are seen edge-on and the glass dominates.
- Bloom is LDR (an 8-bit RenderedTexture): highlights clip before they blur (S on whether a float texture would work in X_ITE).
- Merged ribbons are hard to pick with a TouchSensor (17.5% in the feasibility bench): per-track picking needs proxies, not built yet.
- Real GPUs were never used: every frame here is software GL.

## Reproduce

```
kit/examples/hep/render/fetch_xite.sh                       # X_ITE 16.5.1 into render/site/x_ite (not committed)
kit/examples/run_hep_event.sh                               # the accepted candidate in runs/hep-demo-v2-<date>/candidate
mkdir -p kit/examples/hep/render/site/scenes/final && cp runs/hep-demo-v2-20261106/candidate/events-v2/pythia-dijet-hero.x3d kit/examples/hep/render/site/scenes/final/
python3 -I -c "import sys; sys.path.insert(0,'kit/examples/hep'); import build_event_scene as b; d='kit/examples/hep/render/site/scenes/final/'; open(d+'pythia-dijet-hero.bloom.endon.x3d','w').write(b.bloom_wrapper(open(d+'pythia-dijet-hero.x3d').read(),'endon'))"
cd kit/examples/hep/render && SETTLE=2500 node shots.cjs OUT "scenes/final/pythia-dijet-hero.bloom.endon.x3d|hero_endon_bloom|vp=vp_endon&t=6.5"
```
