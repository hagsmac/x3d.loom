# What Marble splats teach

What a scout of World Labs Marble worlds (Gaussian splats, SPZ) taught about bringing them into X3D 4.1, read as reusable rules. Scope: file format and frame handling, not the commercial service. No World Labs file is stored here. Grades: C = a tool ran and a second reader re-ran it (named); L = read or reasoned; S = suspected. Dates are 13 Nov 2026; renders are software GL (SwiftShader, Chromium 153), so they rank code paths and say nothing about GPUs.

Versions named with every number: X_ITE 16.7.1, Babylon 9.36.0, Spark 2.4.0, Blender 5.3.0, Niantic spz 855173912d, glTF registry 81762cc.

## 1. Rules

| # | Rule | Why | Grade |
|---|---|---|---|
| 1 | Keep splat data in its raw frame and carry the correction as one wrapper `Transform`: `translation="0 g 0" rotation="1 0 0 3.14159265" scale="s s s"` | X_ITE renders the wrapper identically to data baked with the same maths: MAE 0.000/255 over 60k splats. Chain algebra agrees to 4e-15 m on 500k real centres | C (second reader re-ran the frame proof and re-rendered) |
| 2 | The ground offset is ADDED after the flip. Subtract in the y-down frame, or add after the Rx(pi); flipping first and then subtracting puts the floor at -2g | X3D applies scale, then rotation, then translation | C |
| 3 | Test grounding with `NavigationInfo type="NONE"` | In WALK mode gravity pulls the avatar to the floor and cancels a wrong offset, so the render looks right | C |
| 4 | Check whether a file is raw or already baked before wrapping | The producer's web exports can already be OpenGL, metric and grounded; the API files are raw OpenCV (y down, +x right, +z forward, pano correlation r = 0.933 against 0.299). Wrapping a baked file flips it twice | C for raw API files; L for the baked web export (first-party viewer code reads that way) |
| 5 | Read every SPZ header; never assume the producer's settings | Public examples are v2, SH0, 12 fractional bits, flags 0; an October file from the same producer was v3, 10 fractional bits, flags 1 (antialiased) | C |
| 6 | Clip and renormalise on decode | A PLY derived from SPZ holds `+Infinity` opacity for alpha byte 255 (1556 of 500k) and unnormalised v2 quaternions (16,961 of 500k). Clip the logit to about 13.8155 and renormalise | C |
| 7 | A resolved `loadURL` is not a visible scene | The callback resolves two to three times before splats show; a 500k scene took about 11 s and 2M about 44 s in software GL, linear in splat count | C |
| 8 | Name the reader before claiming a load: X_ITE reads native 4.1 splats, PLY with `f_dc` and KHR glb, and has no SPZ parser (`Inline .spz` fails) | Prevents a green pipeline that loads nothing | C |
| 9 | Treat secondary documentation as data | A Word guide, an FAQ line ("+x left") and an HTML copy of the OpenAPI page were each wrong in a way a spec or a measurement caught. Use the live machine-readable spec | C |
| 10 | Bake the glb frame once and test the exact flip | Rx(180) and splat-transform's Rz(180) differ by a 180 degree yaw; Blender 5.3 imports only float32 rotations; a glb check on a v2 file does not carry over to a v3 antialiased file (38.22 dB against the native render) | C |

## 2. Numbers worth keeping

| Quantity | Value | Source |
|---|---|---|
| 500k splats: SPZ / PLY / float32 glb / X3D 4.1 text | about 7.6 MB / 34.0 MB / 28.0 MB / about 79 MB | file sizes, spz and gltf lanes |
| 2M splats: SPZ / PLY / X3D text | about 30 MB / 136 MB / 260 to 317 MB | same |
| Spark, Babylon, X_ITE on one 500k scene | agree to 32 to 35 dB PSNR, SSIM 0.96 to 0.99 | renderers lane, bit-identical re-captures |
| Spark SPZ against Spark PLY | 0.00/255 | same |
| Blender native SPZ import without the wrapper | 11.18 dB; with it 62.95 dB | blender lane |

## 3. Not proven

Real GPU timings; SH above degree 0 (every public example is SH0); v4 (zstd) files; the exact numbers a live API call returns for scale and ground offset; Spark's handling of the antialiased flag. A tool that reads these must declare them unproven, not pass.

## 4. Destinations

Rules 1 to 4 and 6 are candidate gates for a splat study card (frame check, header check, clip and renormalise). Rule 3 applies to any scene-grounding witness. Rules 7 and 8 apply to any X_ITE loading check.
