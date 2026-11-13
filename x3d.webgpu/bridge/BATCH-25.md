# Bridge batch 25

Reader knows **181/260** X3D 4.0 node types after this batch (106 bridged in this work so far, 75 baseline). Rig: {"chromium": "153.0.8010.12", "ours": "x3d.webgpu reader + SAI shim, headless, bundle sha 4ba756222b5d", "xite": "X_ITE 16.6.0 (WebGL2, SwiftShader)", "babylon": "9.32.0"}.

Regression gate (all bridged event nodes in one ROUTE chain, ours + X_ITE): PASS; inside the real Babylon 9.32.0 WebGPU body on swiftshader: 13 frames, page errors 0, Switch ended on [1].

| node | component | xsd | ours | X_ITE | verdict | note |
|---|---|---|---|---|---|---|
| LineSet | Rendering | ok | pass 6/6 | pass 5/5 | PASS | normal, fogCoord and attrib are read and ignored; line colour: the drawn pixels are about 20 percent brighter than X_ITE's one pixel lines in the picture (mean colour 60,120,61 against 48,99,51), the anti-aliased ribbon covers more pixels than a raw GL line |
| TriangleSet2D | Geometry2D | ok | pass 22/22 | pass 20/20 | PASS | compared by pointer-over probes, the triangle count and the picture; X_ITE 16.6.0 culls the clockwise second triangle although solid is false, ours draws it facing +z (the 4.0 text: a 2D geometry has no back side), a deliberate difference |
| Arc2D | Geometry2D | ok | pass 7/7 | pass 7/7 | PASS | lines are not pickable, so the check is the picture (silhouette overlap and the mean colour of the drawn pixels, SwiftShader CPU raster) plus the segment count between the engines (X_ITE vertex pairs through its internal getVertices, a private API) and one line mesh in our body; line width is one pixel in both, ours is an anti-aliased ribbon |
| ArcClose2D | Geometry2D | ok | pass 18/18 | pass 18/18 | PASS | compared by pointer-over probes, the triangle count and the picture; texture mapping and lighting of ArcClose2D are not compared with X_ITE |
| Circle2D | Geometry2D | ok | pass 7/7 | pass 6/6 | PASS | lines are not pickable, so the check is the picture (silhouette overlap and the mean colour of the drawn pixels, SwiftShader CPU raster) plus the segment count between the engines (X_ITE vertex pairs through its internal getVertices, a private API) and one line mesh in our body; line width is one pixel in both, ours is an anti-aliased ribbon |

Visual comparison (320 x 240 picture of each engine, same scene and camera; ours = Babylon render target, X_ITE = page screenshot; CPU only, SwiftShader / llvmpipe, no real GPU). iou = overlap of the drawn silhouettes, mad = mean absolute RGB difference over the picture (0 to 255), fg = mean colour of the drawn pixels:

| node | shot | iou | mad | psnr dB | fg ours | fg X_ITE | picture (ours left, X_ITE right) |
|---|---|---|---|---|---|---|---|
| LineSet | main | 0.81 | 2.33 | 29.27 | [60, 120, 61] | [48, 99, 51] | receipts/shots/LineSet.main.png |
| TriangleSet2D | main | 0.97 | 1.76 | 35.86 | [51, 178, 230] | [49, 172, 222] | receipts/shots/TriangleSet2D.main.png |
| Arc2D | main | 0.84 | 2.53 | 27.16 | [151, 121, 31] | [150, 120, 30] | receipts/shots/Arc2D.main.png |
| ArcClose2D | main | 0.98 | 1.69 | 35.1 | [51, 178, 230] | [50, 175, 226] | receipts/shots/ArcClose2D.main.png |
| Circle2D | main | 0.85 | 2.7 | 26.35 | [150, 120, 31] | [150, 120, 30] | receipts/shots/Circle2D.main.png |
