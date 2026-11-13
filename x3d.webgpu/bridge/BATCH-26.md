# Bridge batch 26

Reader knows **186/260** X3D 4.0 node types after this batch (111 bridged in this work so far, 75 baseline). Rig: {"chromium": "153.0.8010.12", "ours": "x3d.webgpu reader + SAI shim, headless, bundle sha 7c9e99d98ec7", "xite": "X_ITE 16.6.0 (WebGL2, SwiftShader)", "babylon": "9.32.0"}.

Regression gate (all bridged event nodes in one ROUTE chain, ours + X_ITE): PASS; inside the real Babylon 9.32.0 WebGPU body on swiftshader: 13 frames, page errors 0, Switch ended on [1].

| node | component | xsd | ours | X_ITE | verdict | note |
|---|---|---|---|---|---|---|
| Polyline2D | Geometry2D | ok | pass 5/5 | pass 5/5 | PASS | lines are not pickable, so the check is the picture (silhouette overlap and the mean colour of the drawn pixels, SwiftShader CPU raster) plus the segment count between the engines (X_ITE vertex pairs through its internal getVertices, a private API) and one line mesh in our body; line width is one pixel in both, ours is an anti-aliased ribbon |
| Polypoint2D | Geometry2D | ok | pass 5/5 | pass 5/5 | PASS | WebGPU has no point size: each point is a small camera-facing square drawn by a shader; X_ITE 16.6.0 draws its points much dimmer on this CPU raster (seen in the picture), colour and size are not compared; PointProperties sizing is not applied |
| CoordinateDouble | Rendering | ok | pass 32/32 | pass 32/32 | PASS | the points are kept as 32-bit floats (the geometry code reads Float32Array); doubles finer than about 7 digits or larger than 3e38 are not kept; only the triangle positions are compared with X_ITE (pointer hit and miss), not shading |
| CADLayer | CADGeometry | ok | pass 15/15 | pass 15/15 | PASS |  |
| CADPart | CADGeometry | ok | pass 15/15 | pass 15/15 | PASS |  |

Visual comparison (320 x 240 picture of each engine, same scene and camera; ours = Babylon render target, X_ITE = page screenshot; CPU only, SwiftShader / llvmpipe, no real GPU). iou = overlap of the drawn silhouettes, mad = mean absolute RGB difference over the picture (0 to 255), fg = mean colour of the drawn pixels:

| node | shot | iou | mad | psnr dB | fg ours | fg X_ITE | picture (ours left, X_ITE right) |
|---|---|---|---|---|---|---|---|
| Polyline2D | main | 0.83 | 2.29 | 28.35 | [157, 125, 32] | [135, 108, 27] | receipts/shots/Polyline2D.main.png |
| Polypoint2D | main | 1 | 1.69 | 40.03 | [202, 162, 41] | [64, 51, 13] | receipts/shots/Polypoint2D.main.png |
| CADLayer | hidden | 0.98 | 1.68 | 38.03 | [125, 88, 111] | [123, 86, 109] | receipts/shots/CADLayer.hidden.png |
| CADLayer | shown | 0.98 | 1.68 | 37.83 | [109, 100, 98] | [107, 99, 96] | receipts/shots/CADLayer.shown.png |
| CADLayer | moved | 0.98 | 1.68 | 37.83 | [108, 100, 98] | [107, 99, 96] | receipts/shots/CADLayer.moved.png |
| CADLayer | subhidden | 0.98 | 1.7 | 37.98 | [161, 95, 51] | [158, 93, 50] | receipts/shots/CADLayer.subhidden.png |
| CADPart | hidden | 0.98 | 1.68 | 38.03 | [125, 88, 111] | [123, 86, 109] | receipts/shots/CADPart.hidden.png |
| CADPart | shown | 0.98 | 1.68 | 37.83 | [109, 100, 98] | [107, 99, 96] | receipts/shots/CADPart.shown.png |
| CADPart | moved | 0.98 | 1.68 | 37.83 | [108, 100, 98] | [107, 99, 96] | receipts/shots/CADPart.moved.png |
| CADPart | subhidden | 0.98 | 1.7 | 37.98 | [161, 95, 51] | [158, 93, 50] | receipts/shots/CADPart.subhidden.png |
