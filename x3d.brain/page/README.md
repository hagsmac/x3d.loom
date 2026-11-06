# Interactive page ("Neural Canvas")

A single static page that draws the Brain Loom scenes with X_ITE 16.6.0, in two tabs: the template **Brain** and a **Torso CT**. It has a HUD written in HTML (never `ScreenGroup` or `Layout`, which X_ITE cannot draw outside the Full profile): layer switches, seven camera views, a twelve-look switcher with a before/after crossfade, region picking with a facts card, an eight-step guided tour, a music switch, and a "Loom log" panel with provenance.

Not a medical device. Not for diagnosis. The tracts are SYNTHETIC, the activation glows are ILLUSTRATIVE, the region text is model-written and can be wrong, and no patient data is used.

## Run it

```sh
sh tools/fetch_xite.sh            # once: npm-packs x_ite@16.6.0 into page/vendor/x_ite (git-ignored)
python3 -m http.server -d page 8000   # then open http://localhost:8000/
```

Without `vendor/` the page asks a public CDN for the same X_ITE version (one network request, nothing else leaves the page). It must be served over http(s): browsers refuse to `fetch` scene files from `file://`.

## What is here

| path | role |
|---|---|
| `template.html`, `ui.css`, `page.css`, `app.js` | the page sources (ui.css is the HUD class contract; page.css adds layout and the rest; app.js is plain JavaScript, no build step) |
| `provenance.json` | source of the Loom log: data sources and licence grades, notices, receipt placeholder |
| `index.html`, `data/`, `scenes/`, `NOTICE-*.md` | **generated** by `tools/build_page.py --target repo` (lite scenes, no music, no style-board thumbnails) |
| `vendor/` | X_ITE, fetched, not committed |

Rebuild: `python3 -I tools/build_page.py --target repo`. The private build (full 41k scene, full torso, music, look thumbnails) is the same command with `--target private --out DIR` and the input folders; see the docstring of `tools/build_page.py`. Both print a count and sha256 for every output.

## Scene contract

The page reads the DEF names listed in `tests/check_contract.py` and adapts to what the scene really contains (a missing DEF disables its control). It adds a few nodes at run time, never to the files: two page cameras (a smooth `ANIMATE` transition between views), a pulsing marker for the selected region, and `TouchSensor`s on the aura shell, slices, activation sprites and each deep structure (the 1.03x aura shell sits in front of the cortex and would otherwise swallow every click). In the torso scene the see-through skin gets a sensor too and a click follows the camera ray inwards to the nearest visible part. The canvas is full-bleed; the page moves its box and widens the field of view so the model sits in the part of the window the HUD leaves free (between the top bar and the dock, or the open sheet on a phone), without touching the orbit.

Looks are pushed through the X_ITE API (shader fields, materials, background, lights). A look named for a layer that is off by default (neon tractography, cosmic connectome, bioluminescence, holo slices, heat map) switches that layer on and gives it back when you choose another look.

## Checks

`node tests/test_page.cjs --page page --out OUT` drives every control in headless Chromium (software GL) and writes screenshots and `report.json`. It passes only with zero console errors, zero failed requests and zero page errors.

Keys: `1`-`7` views, `T` tour, arrows step the tour, `G W D R S L A` layers, `M` music, `F` full screen, `?` help, `Esc` closes.
