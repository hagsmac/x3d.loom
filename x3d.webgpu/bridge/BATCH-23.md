# Bridge batch 23

Reader knows **184/260** X3D 4.0 node types after this batch (109 bridged in this work so far, 75 baseline). Rig: {"chromium": "153.0.8010.12", "ours": "x3d.webgpu reader + SAI shim, headless, bundle sha f499223bf445", "xite": "X_ITE 16.6.0 (WebGL2, SwiftShader)", "babylon": "9.32.0"}.

Regression gate (all bridged event nodes in one ROUTE chain, ours + X_ITE): PASS; inside the real Babylon 9.32.0 WebGPU body on swiftshader: 13 frames, page errors 0, Switch ended on [1].

| node | component | xsd | ours | X_ITE | verdict | note |
|---|---|---|---|---|---|---|
| ExplosionEmitter | ParticleSystems | ok | pass 6/6 | pass 5/5 | PASS | particle age at the shot differs between the engines on this CPU raster (ours runs on elapsed time at about 3 frames per second under SwiftShader), so the extent is compared with a wide bound and the speed is checked from the particle list in our body; X_ITE 16.6.0 draws the particles white on this raster, ours uses the Material emissive colour (colour is not compared); the X_ITE picture also shows a swirl pattern that ours does not reproduce |
| BoundedPhysicsModel | ParticleSystems | ok | pass 5/5 | pass 4/4 | PASS | X_ITE 16.6.0 draws the particles white on this raster, ours uses the Material emissive colour (colour is not compared); the bounds are tested in ours from the particle list (a box of 3 x 2 x 2 holds every particle, which reflect at the faces); X_ITE's particle positions are not read, its picture is compared by extent |
| SurfaceEmitter | ParticleSystems | ok | pass 5/5 | pass 4/4 | PASS | particle age at the shot differs between the engines on this CPU raster (ours runs on elapsed time at about 3 frames per second under SwiftShader), so the extent is compared with a wide bound; X_ITE 16.6.0 draws the particles white on this raster, ours uses the Material emissive colour (colour is not compared); the emission point is a random point of the surface triangles, area weighted, along the face normal (a Sphere is cut into 16 x 12 facets for this) |
| CADAssembly | CADGeometry | ok | pass 15/15 | pass 15/15 | PASS |  |
| CADFace | CADGeometry | ok | pass 15/15 | pass 15/15 | PASS |  |

Visual comparison (320 x 240 picture of each engine, same scene and camera; ours = Babylon render target, X_ITE = page screenshot; CPU only, SwiftShader / llvmpipe, no real GPU). iou = overlap of the drawn silhouettes, mad = mean absolute RGB difference over the picture (0 to 255), fg = mean colour of the drawn pixels:

| node | shot | iou | mad | psnr dB | fg ours | fg X_ITE | picture (ours left, X_ITE right) |
|---|---|---|---|---|---|---|---|
| ExplosionEmitter | burst | 0.05 | 23.87 | 11.73 | [121, 73, 14] | [215, 215, 194] | receipts/shots/ExplosionEmitter.burst.png |
| BoundedPhysicsModel | boxed | 0.32 | 9.82 | 16.14 | [145, 145, 33] | [207, 207, 207] | receipts/shots/BoundedPhysicsModel.boxed.png |
| SurfaceEmitter | shell | 0.12 | 14.21 | 14.28 | [34, 155, 155] | [194, 194, 194] | receipts/shots/SurfaceEmitter.shell.png |
| CADAssembly | hidden | 0.98 | 1.68 | 38.03 | [125, 88, 111] | [123, 86, 109] | receipts/shots/CADAssembly.hidden.png |
| CADAssembly | shown | 0.98 | 1.68 | 37.83 | [109, 100, 98] | [107, 99, 96] | receipts/shots/CADAssembly.shown.png |
| CADAssembly | moved | 0.98 | 1.68 | 37.83 | [108, 100, 98] | [107, 99, 96] | receipts/shots/CADAssembly.moved.png |
| CADAssembly | subhidden | 0.98 | 1.7 | 37.98 | [161, 95, 51] | [158, 93, 50] | receipts/shots/CADAssembly.subhidden.png |
| CADFace | hidden | 0.98 | 1.68 | 38.03 | [125, 88, 111] | [123, 86, 109] | receipts/shots/CADFace.hidden.png |
| CADFace | shown | 0.98 | 1.68 | 37.83 | [109, 100, 98] | [107, 99, 96] | receipts/shots/CADFace.shown.png |
| CADFace | moved | 0.98 | 1.68 | 37.83 | [108, 100, 98] | [107, 99, 96] | receipts/shots/CADFace.moved.png |
| CADFace | subhidden | 0.98 | 1.7 | 37.98 | [161, 95, 51] | [158, 93, 50] | receipts/shots/CADFace.subhidden.png |
