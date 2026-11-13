# Bridge batch 24

Reader knows **184/260** X3D 4.0 node types after this batch (109 bridged in this work so far, 75 baseline). Rig: {"chromium": "153.0.8010.12", "ours": "x3d.webgpu reader + SAI shim, headless, bundle sha 8c8aadc83f99", "xite": "X_ITE 16.6.0 (WebGL2, SwiftShader)", "babylon": "9.32.0"}.

Regression gate (all bridged event nodes in one ROUTE chain, ours + X_ITE): PASS; inside the real Babylon 9.32.0 WebGPU body on swiftshader: 13 frames, page errors 0, Switch ended on [1].

| node | component | xsd | ours | X_ITE | verdict | note |
|---|---|---|---|---|---|---|
| TextureCoordinateGenerator | Texturing | ok | pass 17/17 | pass 15/15 | PASS | the six modes of the fixture are compared in the picture (silhouette overlap 0.98) and against the formula in our body; the CAMERASPACENORMAL and CAMERASPACEREFLECTIONVECTOR spheres differ visibly from X_ITE 16.6.0 (mean RGB difference 11 of 255 over the picture): X_ITE's own scaling of the camera-space range is not reproduced; camera-space modes are recomputed on the CPU whenever the model-view matrix changes, not in a shader; NOISE and NOISE-EYE are not made |
| FillProperties | Shape | ok | pass 15/15 | pass 13/13 | PASS | a shape with filled=false and hatched=false is not drawn but still answers the pointer, as in X_ITE 16.6.0 (the 4.0 text does not say); compared by pointer-over probes (hidden fill is not hit, hatched and plain fills are) and, in our body only, the hatch overlay mesh; line pattern, thickness and screen-space scaling are not compared with X_ITE; hatchStyle 7 to 19 are drawn as style 6; the pattern follows the geometry's texture coordinates, a geometry without them shows no hatch |
| TwoSidedMaterial | Shape | ok | pass 13/13 | pass 10/10 | PASS | which side shows which colour is compared in the picture (the lower row is turned round, so it shows the back colours; a solid=TRUE pair in the middle is culled in both engines), and in our body by pass: two meshes for solid=FALSE, one for solid=TRUE; ambient and ambientIntensity are read and not shown (no ambient term in the headlight model); the specular highlight of the sphere follows Phong shininess*128 and is compared in the picture |
| ComposedTexture3D | Texturing3D | ok | pass 12/12 | pass 12/12 | PASS | XSD finding: x3d-4.0.xsd writes the texture field of a ComposedTexture3D as an xs:sequence of ImageTexture, PixelTexture, MovieTexture, ProtoInstance repeated, not an xs:choice, so the slices must come in fours in that order and two ImageTextures do not validate; the fixture is checked against the XSD with that sequence made a choice (the receipt says so); the image field of a PixelTexture3D takes decimal numbers only in the XSD (no 0x hex); Babylon side: a WGSL ShaderMaterial over a RawTexture3D, shaded by the headlight only (N dot view axis, two sided); other lights, TextureProperties anisotropy and mipmaps are not applied to volumes |
| PixelTexture3D | Texturing3D | ok | pass 19/19 | pass 19/19 | PASS | Babylon side: a WGSL ShaderMaterial over a RawTexture3D, shaded by the headlight only (N dot view axis, two sided); other lights, TextureProperties anisotropy and mipmaps are not applied to volumes |

Visual comparison (320 x 240 picture of each engine, same scene and camera; ours = Babylon render target, X_ITE = page screenshot; CPU only, SwiftShader / llvmpipe, no real GPU). iou = overlap of the drawn silhouettes, mad = mean absolute RGB difference over the picture (0 to 255), fg = mean colour of the drawn pixels:

| node | shot | iou | mad | psnr dB | fg ours | fg X_ITE | picture (ours left, X_ITE right) |
|---|---|---|---|---|---|---|---|
| TextureCoordinateGenerator | main | 0.98 | 10.99 | 16.62 | [160, 64, 101] | [152, 87, 93] | receipts/shots/TextureCoordinateGenerator.main.png |
| FillProperties | main | 0.96 | 6.07 | 19.87 | [69, 179, 199] | [92, 188, 173] | receipts/shots/FillProperties.main.png |
| TwoSidedMaterial | main | 0.98 | 1.66 | 32.13 | [59, 121, 87] | [58, 118, 85] | receipts/shots/TwoSidedMaterial.main.png |
| ComposedTexture3D | main | 0.99 | 1.42 | 30.11 | [151, 125, 103] | [149, 124, 102] | receipts/shots/ComposedTexture3D.main.png |
| PixelTexture3D | main | 0.99 | 1.64 | 30.21 | [153, 153, 145] | [152, 152, 144] | receipts/shots/PixelTexture3D.main.png |
