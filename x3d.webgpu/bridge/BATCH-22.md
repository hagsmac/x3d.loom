# Bridge batch 22

Reader knows **179/260** X3D 4.0 node types after this batch (104 bridged in this work so far, 75 baseline). Rig: {"chromium": "153.0.8010.12", "ours": "x3d.webgpu reader + SAI shim, headless, bundle sha fbf130ec58bf", "xite": "X_ITE 16.6.0 (WebGL2, SwiftShader)", "babylon": "9.32.0"}.

Regression gate (all bridged event nodes in one ROUTE chain, ours + X_ITE): PASS; inside the real Babylon 9.32.0 WebGPU body on swiftshader: 13 frames, page errors 0, Switch ended on [1].

| node | component | xsd | ours | X_ITE | verdict | note |
|---|---|---|---|---|---|---|
| StaticGroup | Grouping | ok | pass 18/18 | pass 17/17 | PASS | the static children are drawn as a Group and are not merged into one mesh as X_ITE does at load; the merge is an optimisation, it changes no field and no picture (compared below) |
| TextureCoordinate4D | Texturing3D | ok | pass 2/2 | pass 2/2 | PASS |  |
| TextureTransform3D | Texturing3D | ok | pass 5/5 | pass 4/4 | PASS | the moved strip (left) is compared by its matrix in our body only: X_ITE 16.6.0 draws it as a mostly flat colour, while its own TextureTransformMatrix3D with the same matrix (fixture TextureTransformMatrix3D) agrees with ours, so X_ITE's TextureTransform3D field handling differs from the 4.0 text (tc' = T C R S -C tc), Likely; the picture comparison covers the unmoved strip |
| TextureTransformMatrix3D | Texturing3D | ok | pass 3/3 | pass 3/3 | PASS |  |
| ImageTexture3D | Texturing3D | ok | pass 5/5 | pass 5/5 | PASS | the DDS volume (right) is drawn by ours and shown white by X_ITE 16.6.0 on this raster (Suspected: its DDS 3D reader does not take this uncompressed RGBA header); the picture comparison covers the NRRD volume (left); ImageTexture3D reads uncompressed DDS volumes and uchar NRRD (raw, gzip, ascii); DICOM and compressed DDS are not read |

Visual comparison (320 x 240 picture of each engine, same scene and camera; ours = Babylon render target, X_ITE = page screenshot; CPU only, SwiftShader / llvmpipe, no real GPU). iou = overlap of the drawn silhouettes, mad = mean absolute RGB difference over the picture (0 to 255), fg = mean colour of the drawn pixels:

| node | shot | iou | mad | psnr dB | fg ours | fg X_ITE | picture (ours left, X_ITE right) |
|---|---|---|---|---|---|---|---|
| StaticGroup | before | 0.98 | 1.71 | 36.58 | [45, 158, 204] | [44, 154, 199] | receipts/shots/StaticGroup.before.png |
| StaticGroup | after | 0.98 | 1.72 | 36.03 | [77, 130, 157] | [75, 128, 154] | receipts/shots/StaticGroup.after.png |
| TextureCoordinate4D | main | 0.99 | 1.63 | 35.98 | [128, 128, 73] | [125, 125, 72] | receipts/shots/TextureCoordinate4D.main.png |
| TextureTransform3D | main | 0.99 | 1.57 | 36.63 | [126, 128, 73] | [125, 125, 72] | receipts/shots/TextureTransform3D.main.png |
| TextureTransformMatrix3D | main | 0.99 | 1.66 | 35.3 | [127, 128, 128] | [125, 125, 125] | receipts/shots/TextureTransformMatrix3D.main.png |
| ImageTexture3D | main | 0.99 | 1.66 | 33.85 | [129, 128, 73] | [126, 125, 72] | receipts/shots/ImageTexture3D.main.png |
