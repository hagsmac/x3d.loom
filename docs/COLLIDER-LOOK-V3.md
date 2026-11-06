# Look v3: an outside fidelity pass, sorted and folded back

Date 2026-11-06. An outside pass reworked the published demo page (the first page version, before the camera tour) and returned it as a local archive: new GLSL for five of the six shaders, a resized glow target, page tools (render quality, exposure, bloom, a 4K still, a legend, fullscreen), bundled fonts, a local server and an asset verifier. It edited the generated scenes in place with `lxml`, so its scenes were no longer the witnessed builder output, and it said so itself: the event JSON, builder and receipts were not in its archive.

This note sorts its changes into kept and left, each with the evidence. What was kept now lives in the builder as `--look v3`, and the scenes are generated and witnessed again. Look v2 output is byte-identical to before.

**Instrument for every frame and number here:** X_ITE 16.5.1, headless Chromium with software GL (SwiftShader through ANGLE), Playwright, the demo page at 1280 x 860 (stage 1068 x 601), deviceScaleFactor 1, the event held at the same moment, the camera on the page's three fixed shots. Glow on. Look v2 uses its own page settings (1600 x 900 target, gain per view). The outside pass and look v3 both use that pass's own page defaults (a 1920 x 1080 target, gain 0.45, exposure 1.08, blur 18 px, ribbon scale 1.2). Pixel statistics: `kit/examples/hep/feas/imgtools.py stats` v2 on the committed JPEGs (`runs/hep-demo-v3-20261106/frames/stats.json`). The frames include the page's title and clock overlays, so they differ slightly from the LOOK-V2 numbers, which were taken without a page. **No frame rate is quoted: only software GL ran.**

## Kept, now in the builder (`--look v3`)

| change | where | evidence |
|---|---|---|
| ribbon cores twice as tight, with a soft edge fade and a brighter gain; cyan a little less green, magenta a little pinker | track shader | the jets read as hot cores with clean edges (frames); with the other changes, cyan moves from 4.6% to 11.6% of coloured pixels against the target's 9.4% |
| ribbon and needle widths scale with the render size (`u_resolutionScale`, 1 = 900 rows) | track and tower vertex shaders, a new field | without it, a sharper target only makes the ribbons thinner. With it, the stage at 720 vs 1440 rows has 11% more edge energy and the same mean (C, harness on the v3 page) |
| a machined detector: panel seams, ribs, fine ribs, paired readout traces, a lit lip, a warm band at the calorimeter face, key-light glints, brushed shading | shell shader | the steel and muon stations now read as hardware in every view, not just end-on (compare sheets). This covers the v2 note that the oblique views were nearly all glass |
| a sharper flash: a fast bang, an afterglow, a shock ring that runs outward, a warm core | flash shader | the crossing reads as an event rather than a lamp (frames at the flash, page) |
| haze structure: rotated fbm, a halo ring, one cold and one warm light shaft | haze shader | gives the backdrop direction (frames) |
| multiscale bloom: an edge-aware smooth of thin bright lines, a tight and a wide ring, a faint horizontal streak, then exposure, a soft shoulder above 0.72, a 0.94 gamma lift and a vignette; every field live | bloom wrapper | clipped pixels (a channel at 255) in the dijet end-on frame fall from 2.9% (v2) and 2.5% (outside pass) to 1.1%, while the mean rises a little |
| page: render quality tiers (720 to 2160 rows, adaptive 1080 to 720 by the viewer's own frame rate), exposure and bloom sliders, a 3840 x 2160 still, a colour legend, a labels toggle, fullscreen, bundled fonts, loading guards on the glow and event buttons | demo page | harness: the target follows the stage (1280 x 720, then 2560 x 1440 at the Ultra tier); the sliders reach the shader (gain 0.26 and exposure 1.5); the 4K still saves at 3840 x 2160; 0 page errors |

## Left out, and why

| change | why it was left |
|---|---|
| the haze six times darker | the target's mid-tones are brighter than look v2 (median luma 0.105 against 0.061). The darker haze moved further away. Look v3 keeps the outside pass's haze structure at about v2's level: median 0.118 |
| vertex sparks turned off | no reason was given, and they render with 0 errors in the harness. They stay on, and the page still runs them only near demo speed |
| scenes edited after generation | a generated scene is never hand-edited (the Loom's rule). The same shaders now come from the builder, and the witness runs on its output |
| a slow camera drift in place of the tour | the page's auto-tour, drag, pinch and wheel are a superset. The pass started from the page version before the tour |
| the end-on and three-quarter views widened, three-quarter as the opening shot | the tour opens end-on and moves through every shot, so the fixed shots stay as they were |
| a page restyle (an observatory bar, a new deck style) | a matter of taste; the deck stays as it was. Its legend and stage footer were kept |

## New in look v3 (neither v2 nor the outside pass)

- A red hot end on the crown's energy ramp: the hottest tenth of towers (relative to the event's own 90th percentile) shift to red, less so when they are EM-rich. Red goes from 0.2% (v2) and 1.5% (outside pass) to 2.7% of coloured pixels, against the target's 7.5%.

## Numbers (dijet hero, end-on, glow; `frames/stats.json`)

| statistic | reference still | look v2 | outside pass | look v3 |
|---|---|---|---|---|
| mean luma | 0.190 | 0.162 | 0.159 | 0.170 |
| median luma | 0.105 | 0.061 | 0.078 | 0.118 |
| bright pixels | 34% | 29% | 27% | 34% |
| achromatic share of bright | 20% | 21% | 15% | 11% |
| blue | 63% | 68% | 42% | 63% |
| cyan | 9.4% | 4.6% | 24.6% | 11.6% |
| violet/magenta | 6.4% | 7.7% | 7.7% | 7.2% |
| orange | 12.5% | 11.6% | 13.9% | 11.4% |
| yellow | 0.8% | 8.3% | 10.3% | 3.8% |
| red | 7.5% | 0.2% | 1.5% | 2.7% |

Look v3 is closest to the target on mean and median luma, bright share, blue, cyan, magenta and yellow. It ties on orange and is still short on red and on white (C for the numbers; S for "more beautiful", which is a matter of eyes: see `frames/compare_dijet.jpg` and `frames/compare_zmumu.jpg`).

The oblique views are still mostly blue in every look (look v2 99%, outside pass 84 to 89%, look v3 92 to 97% of coloured pixels): the crown is seen edge-on there, and the outside pass's cyan steel breaks it up most.

## Witness

`kit/examples/run_hep_v3.sh` builds the dijet hero, the Z to mu mu and the soft-QCD fixture with `--look v3 --bloom`. It runs the hep-event and traps witnesses on the scenes: both pass. It hashes the scenes into `runs/hep-demo-v3-20261106/scenes.sha256`, and a second run must match those hashes byte for byte (it does). The self-test gained four controls: two positive (Z to mu mu and the toy shower in v3), one proving that v3 changes only shaders, never a coordinate, strip or vertex attribute, and one negative (a strip deleted in v3 fails the bijection check). Totals: 207 negative and 20 positive, normal and `-O`.

## Not done

- No profile change: the `hep-demo/v2` receipt still covers v1 and v2 only. Look v3 is witnessed by the run above, not yet accepted under a profile.
- The outside pass's 4K stills are not committed: they came from scenes outside the receipt.
- Real GPUs were never used.
