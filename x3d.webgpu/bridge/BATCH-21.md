# Bridge batch 21

Reader knows **175/260** X3D 4.0 node types after this batch (100 bridged in this work so far, 75 baseline). Rig: {"chromium": "153.0.8010.12", "ours": "x3d.webgpu reader + SAI shim, headless, bundle sha 022e741d6028", "xite": "X_ITE 16.6.0 (WebGL2, SwiftShader)", "babylon": "9.32.0"}.

Regression gate (all bridged event nodes in one ROUTE chain, ours + X_ITE): PASS; inside the real Babylon 9.32.0 WebGPU body on swiftshader: 13 frames, page errors 0, Switch ended on [1].

| node | component | xsd | ours | X_ITE | verdict | note |
|---|---|---|---|---|---|---|
| TriangleFanSet | Rendering | ok | pass 27/27 | pass 25/25 | PASS | attrib is read and kept; only a shader program would consume it, and no shader language runs in the bridge (see ShaderProgram, ProgramShader) |
| QuadSet | CADGeometry | ok | pass 22/22 | pass 19/19 | PASS | attrib is read and kept; only a shader program would consume it, and no shader language runs in the bridge (see ShaderProgram, ProgramShader) |
| IndexedQuadSet | CADGeometry | ok | pass 30/30 | pass 27/27 | PASS | attrib is read and kept; only a shader program would consume it, and no shader language runs in the bridge (see ShaderProgram, ProgramShader) |
| IndexedTriangleFanSet | Rendering | ok | pass 24/24 | pass 22/22 | PASS | attrib is read and kept; only a shader program would consume it, and no shader language runs in the bridge (see ShaderProgram, ProgramShader) |
| IndexedTriangleStripSet | Rendering | ok | pass 21/21 | pass 19/19 | PASS | attrib is read and kept; only a shader program would consume it, and no shader language runs in the bridge (see ShaderProgram, ProgramShader) |

Visual comparison (320 x 240 picture of each engine, same scene and camera; ours = Babylon render target, X_ITE = page screenshot; CPU only, SwiftShader / llvmpipe, no real GPU). iou = overlap of the drawn silhouettes, mad = mean absolute RGB difference over the picture (0 to 255), fg = mean colour of the drawn pixels:

| node | shot | iou | mad | psnr dB | fg ours | fg X_ITE | picture (ours left, X_ITE right) |
|---|---|---|---|---|---|---|---|
| TriangleFanSet | main | 0.97 | 1.78 | 33.13 | [95, 113, 126] | [92, 110, 122] | receipts/shots/TriangleFanSet.main.png |
| QuadSet | main | 0.98 | 1.59 | 34.12 | [116, 50, 89] | [113, 48, 87] | receipts/shots/QuadSet.main.png |
| IndexedQuadSet | main | 0.98 | 1.61 | 34.66 | [90, 97, 113] | [88, 94, 110] | receipts/shots/IndexedQuadSet.main.png |
| IndexedTriangleFanSet | main | 0.97 | 1.8 | 32.71 | [93, 117, 131] | [90, 113, 127] | receipts/shots/IndexedTriangleFanSet.main.png |
| IndexedTriangleStripSet | main | 0.98 | 1.5 | 34.91 | [80, 119, 134] | [78, 117, 132] | receipts/shots/IndexedTriangleStripSet.main.png |
