# Loom Collider: in-browser feasibility on X_ITE 16.5.1 (measured)

This is the look v1 study that look v2 was built from: see [../runs/hep-demo-20261106/frames-v2/LOOK-V2.md](../runs/hep-demo-20261106/frames-v2/LOOK-V2.md) for what the recipes became. The stills named under `shots/` are not committed (regenerate with the commands in section 10).

Instrument for every number below unless stated: X_ITE 16.5.1, headless Chromium with software GL (SwiftShader), the harness in kit/examples/hep/feas/. Load times are CPU load times, never frame rates. Grades: C confirmed by measurement, L likely, S suspected.

## 10-LINE SUMMARY
1. Merged geometry loads fast [C]: 20 000 tracks as one IndexedLineSet 2.7 s, 1M points 4.9 s, 50k merged towers 4.8 s. One node per object does not: 5 000 track Shapes 27 s, 10 000 USE-instanced towers 17 s, 50 000 took 665 s (upper bound, overlapped other jobs). X_ITE has no GPU instancing (1 draw per USE).
2. Per-particle shaders at 300 and 3000 tracks: use ONE shared ComposedShader plus per-vertex attributes. 3000 separate programs add +42 to +55 s load and 560 MB heap, and X_ITE does NOT dedupe byte-identical source (311 programs at N=300) [C].
3. Shared vs 300 distinct programs render pixel-identically (mean |d| 0.0/255) [C]. Distinct programs only pay when the GLSL logic differs (suggest at most ~8 "species").
4. New trap [C]: meshes of zero-area triangles crash this renderer from ~33k vertices (SEGV in SwiftShader frames). An offset of 0.004 m per vertex pair, undone in the vertex shader, fixes it and 3000 tracks render. Unexplained [C that it happens]: a merged shape renders differently from one-track-per-Shape (mean |d| 9/255 at N=300, 21 at N=3000).
5. `LineProperties linewidthScaleFactor` works (1,2,4,7,16,32 px measured). The best thick-track look is a screen-space ribbon shader (1 program).
6. Nested translucent shells show ordering artefacts (9.4/255 mean difference between declaration orders). `OrderIndependentTransparency` removes them (0.009). Additive read-only-depth shells are order independent (L).
7. Animation: route TimeSensor fractions into shader uniforms. A throw escaping a host `addFieldCallback` freezes all routing at the 13th event (law 32 / mode 88 reproduced on 16.5.1); a try/catch guard fixes it. A throw inside a Script node does not freeze.
8. Picking: TouchSensor on 1-px lines gets 46% exact-track hits in a dense bundle; shader ribbons need an invisible proxy (17.5% without); Anchor click navigates; PrimitivePickSensor found nothing on line targets. glTF via Inline works: 1M triangles in ~9 s with 400 MB heap, GLB and glTF pixel-identical.
9. Look: a frame in the style of the reference still (kept private) is reachable (white flash, multi-colour filaments, loopers, Fresnel shells, orange/blue crown). Missing: thin spiky crown, glassy thick rings, machinery backdrop, magenta/orange saturation. No bloom node exists, but RenderedTexture + a full-screen ComposedShader gives a real in-scene bloom [C]; a CSS page overlay is the smoother fallback.
10. Best-3 stills: `shots/best1_endon_ref.png` (plus `best1_vs_reference.png`, `best1_rtbloom.png`), `shots/best2_barrel_3000.png`, `shots/best3_side_sparks.png` (all in `feas/`). No frame rate is quoted anywhere (software GL only).

---

# X_ITE 16.5.1 collider-event demo: feasibility and look measurements

Date 2026-11-06. Synthetic data only (seeded; no physics claim: proof of concept, graphics first). Free tools only.
Grades: **C** = a named instrument ran here and produced the number or picture. **L** = read or reasoned from source/docs. **S** = suspected, from memory, not measured here.
Instruments: **I1** X_ITE 16.5.1 (npm pack, served from 127.0.0.1) in Chromium 153.0.8010.12 headless shell, Playwright 1.63.0, software GL = SwiftShader via ANGLE Vulkan, 960x540, dsf 1, 4 vCPU. **I2** `glspy.js` WebGL2 API spy (draws, triangles, programs, compiles, shader logs). **I3** CDP `JSHeapUsedSize` after GC. **I4** PIL+numpy pixel tools (`imgtools.py`). **I5** `exp.cjs` Playwright mouse/callback experiments.
**Load, parse and scene-build times are CPU wall-clock on this box. They are NOT frame rates. No frame rate is quoted: only software GL exists here.** "ms/tick" = main-thread ms inside rAF callbacks (JS plus submit; rasterisation runs off-thread), relative only.

## 1. Load matrix (I1 load, I2 draws, I3 heap; one fresh Chromium per scene; 20 points per track)
| scene | file MB (gz) | parse+build s | replaceWorld s | distinct nodes | heap MB | draws/tick | note |
|---|---|---|---|---|---|---|---|
| tracks IndexedLineSet 100 / 1k / 5k / 20k | 0.05 / 0.50 / 2.54 / 10.48 (0.02/0.17/0.83/3.31) | 0.09 / 0.14 / 0.70 / 2.69 | 0.07 / 0.08 / 0.13 / 0.13 | 8 | 7 / 10 / 25 / 68 | 2 | ceiling not reached |
| tracks, one Shape each 100 / 1k / 5k | 0.08 / 0.80 / 3.98 | 0.55 / 4.38 / 27.2 | 0.13 / 0.30 / 1.67 | 503 / 5003 / 25003 | 14 / 80 / 371 | 101 / 970 / 5001 | practical ceiling ~1k Shapes |
| towers USE-instanced Box 1k / 10k / 50k | 0.15 / 1.45 / 7.26 | 0.73 / 17.2 / 665* | 0.32 / 2.37 / 11.8 | 1036 / 9990 / n.a. | 36 / 286 / 1400 | 930 / 9955 / ~50 000 | 1 draw per USE |
| towers merged IndexedFaceSet 1k / 10k / 50k | 0.38 / 3.98 / 21.0 | 0.16 / 0.94 / 4.78 | 0.15 / 0.10 / 3.61 | 10 | 14 / 70 / 323 | 2 | 50k merged beats 1k instanced |
| points PointSet 10k / 100k / 1M | 0.30 / 2.95 / 29.5 | 0.11 / 0.68 / 4.90 | 0.08 / 0.09 / 0.08 | 9 | 8 / 15 / 98 | 2 | ceiling not reached |

\* The 50k run (0 console errors) overlapped other Chromium jobs, so 665 s is an upper bound; two earlier attempts hung more than 10 min. Console errors are 0 in every row. "Practical ceiling" is a loading ceiling; render cost is software-GL-limited and not reported.

## 2. Per-particle shaders: 300 and 3000 tracks
Scene = haze quad, 6 shells, tower mesh, flash, plus tracks. Ribbon = TriangleStripSet, 2 vertices per point, `FloatVertexAttribute` aNext (vec4) and aMeta (side, s, pT01, seed). **S1** one merged shape, one shared shader. **S2** one Shape per track, all USE one Appearance/ComposedShader. **S3** one ComposedShader node per track, identical text. **S4** per-track text (colour and seed baked as GLSL constants).
| variant | programs N=300 (scene total) | N=300: file MB / parse+build s / replace s / first-render load s | N=3000: file MB / parse+build s / replace s / total s | heap MB 300 / 3000 | ms/tick 300 / 3000 |
|---|---|---|---|---|---|
| S1 merged | 12 (tracks: 1) | 1.90 / 0.62 / 0.07 / 0.96 | 12.5 / 2.85 / 0.92 / 3.9 | 31 / 137 | 9 / 33 |
| S2 shared program, N shapes | 12 (tracks: 1) | 1.98 / 1.77 / 0.29 / 2.01 | 13.3 / 14.5 / 1.57 / 16.2 | 50 / 339 | 21 / 174 |
| S3 N nodes, same text | 311 (tracks: 300) | 2.86 / 4.37 / 2.63 / 6.99 | 22.1 / 45.8 / 24.9 / 70.9 | 73 / 559 | 134 / 325 |
| S4 N distinct texts | 311 (tracks: 300) | 2.87 / 4.85 / 0.37 / 4.74 | 22.1 / 52.1 / 5.6 / 57.9 | 73 / 557 | 174 / 303 |

Findings (C unless marked):
- **No program dedupe.** S3 has byte-identical sources yet 311 programs; sharing happens only through one node reached by USE (S2).
- Extra overhead is ~11-18 ms per additional program (I1, (S3 or S4 total minus S2 total)/(N-1)); 3000 programs = +42 to +55 s.
- Shared shader + attributes carries colour, seed, pT, pulse speed and growth birth time at no extra program.
- S2=S3=S4 are pixel-identical (I4 mean |d| 0.0, N=300).
- Animated (4 s, TimeSensors routed to uniforms): S1 28.8 ms/tick, S2 35.6, S4 175 (600 routes), S1 at 3000 48.2.
- **Recommendation:** at most ~8 shader "species" (loop, curve, straight, muon...), each one shared ComposedShader on one merged chunk, all per-track variation in attributes; distinct programs only for genuinely different GLSL logic.
- Loom traps hit: raw GLSL must be a `data:x-shader/x-vertex,` URL in a ShaderPart (CDATA; avoid `%`, use `mod`); `active` is reserved (not used as a field name); declare components Shaders, Rendering, X_ITE (BlendMode/DepthMode need X_ITE).
- **Unexplained:** S1 (merged; 30-150 tracks per chunk and IndexedTriangleSet give the same pixels) renders differently from S2-S4 (one track per Shape): mean |d| 9.1/255 at N=300, 21.2 at N=3000, equal triangle counts submitted, not depth (DepthMode off: identical). S2 is denser and brighter; S1 shows shorter dashed rays; a 10-tracks-per-Shape chunk sits in between. Which is "right" is not established. The stills use S1. Re-test on a real GPU (S).
- **Crash trap:** a TriangleStripSet or IndexedTriangleSet whose vertex pairs coincide (zero-area triangles) crashes the browser process (SEGV in SwiftShader JIT frames) from ~33k vertices (30 316 OK, 33 050 crash; 53k and 156k crash even with a plain Material and no shader). Offsetting each pair by side*0.004*(1,0.7,0.3) and subtracting it in the vertex shader renders 3000 tracks (3.0M vertices) without error (`gen_crash_probe.py`: probes P1-P4 crash, P1e renders). Earlier "tracks-only" crashes were this trap. GPU behaviour unknown (S).

## 3. Thick tracks and transparency
| tracks | file MB 100 / 1000 | parse s | heap MB | draws/tick | rel. ms/tick | note |
|---|---|---|---|---|---|---|
| IndexedLineSet 1 px | 0.05 / 0.50 | 0.11 / 0.16 | 7 / 11 | 2 | 1.1x / 1.0x | cheapest |
| + LineProperties 4 | 0.05 / 0.50 | 0.08 / 0.16 | 7 / 11 | 3 | 1.0x / 1.3x | width honoured |
| merged 6-sided tube mesh | 0.94 / 10.0 | 0.25 / 1.98 | 19 / 135 | 2 | 1.0x / 1.3x | 20x file size |
| crossed quads | 0.25 / 2.50 | 0.14 / 0.65 | 11 / 50 | 2 | 1.0x / 1.3x | flat from the side |
| Extrusion per track | 0.07 / 0.67 | 0.58 / 4.86 | 27 / 199 | 101 / 979 | 2.9x / 16.6x | 4005 nodes |
| screen-space ribbon shader (section 6) | 1.9 / 12.5 (300 / 3000) | 0.62 / 2.85 | 31 / 137 | 18-66 | see section 2 | constant pixel width, glow profile |

**linewidthScaleFactor** [I4 run lengths of `lw_ladder` at x=480]: factors 1,2,4,8,16,32 gave 1,2,4,7,16,32 px while I1 reports the GL aliased width range [1,1], so X_ITE draws wide lines as geometry (C; mechanism L). **Shell transparency**, 4/16/64 nested cylinders: draws 10/34/129, JS 0.41/0.48/0.87 ms per tick (OIT on 0.45/0.27/0.97; noise level). **Ordering artefacts: yes** (looked at `shots/sh_order_pair.png`: orange- versus blue-dominant colour balance flips with declaration order; the default Cylinder tessellation also shows facets). Pixel diff, two-sided shells: outer-first vs inner-first 9.35/255 mean (32.6% of pixels >8), shuffled 5.4 and 4.0; with back-face culling (`solid=true`) 0.15; with `OrderIndependentTransparency=true` outer vs inner 0.009. Additive ONE/ONE shells with read-only depth are order independent (L; DepthMode off gave identical pixels, C).

## 4. Animation and the freeze trap
| approach (4 s timeline, N=300 / 1000) | file MB | nodes | ms/tick | note |
|---|---|---|---|---|
| one CoordinateInterpolator for the bundle | 1.28 / 4.25 | 9 | 1.64 / 4.93 | keyValue grows with N x keys |
| Script rewriting coordIndex (growth) | 0.15 / 0.50 | 9 | 3.68 / 4.66 | needs Scripting component |
| per-track PositionInterpolator + marker | 0.38 / 1.26 | 613 / 2013 | 6.60 / 10.84 | 281 / 1002 draws per tick |
| shader uniforms uTime/uGrow via 3 TimeSensors | 1.9 / 12.5 | 88 | 28.8 / 48.2 (whole look) | N-independent routes |

**Law 32 / failure mode 88 on 16.5.1 [I5, C]:** a TimeSensor moves two Transforms. A harmless callback saw 236 events, all fine. A callback throwing at its 13th event: 12 good calls, then no more events, both Transforms stop, console shows `pageerror`: routing frozen. The same callback in try/catch: 235 good calls, error caught once, motion continues. A Script node that throws in `set_fraction`: X_ITE logs "JavaScript Error in Script" and routing continues (C), so the trap is the host-side `addFieldCallback`.
**Pattern:** `const guard = f => (...a) => { try { return f(...a); } catch (e) { console.error(e); } };` then `node.addFieldCallback('k', 'fraction_changed', guard(fn))`. Drive visuals by ROUTE into uniforms, read the clock with `browser.getCurrentTime()`, keep a deliberate-throw test (`exp.cjs freeze`) in the page checks.

## 5. Picking, glTF, detector meshes
| pick variant (40 tracks, 160 probes at 4 points each) | own-track hits | wrong-track hits | events | note |
|---|---|---|---|---|
| TouchSensor, 1 px IndexedLineSet | 74 (46%) | 13 | 173 isOver, 87 hitPoint | `browser.description` shows the hovered track text |
| + LineProperties 6 | 87 (54%) | 71 | 325 | wide lines grab neighbours |
| + invisible proxy tube (transparency 0.999, r 25 mm) | 86 (54%) | 74 | 333 | same, easier to hit |
| Anchor (LineProperties 6) | hover description shown | - | 1 navigation on click | click loads the url |
| shader ribbon + TouchSensor | 28 (17.5%) | 5 | 65 | picking sees CPU geometry, not the shader-expanded ribbon (L) |
| PrimitivePickSensor (Sphere probe vs track Shapes) | 0 picked with GEOMETRY | - | 0 isActive events | node runs; BOUNDS: 1 hit at start, no change events: inconclusive |

Recommendation: TouchSensor per track or per jet group on a proxy mesh; hits are probabilistic in a dense bundle (jet-level picking, or an id pass in a shader, S). **glTF:** `Inline` of `.gltf` and `.glb` works [I1]. Triangles 50k / 200k / 1M; glTF MB 1.6/6.4/32.0 (gz 0.39/1.6/8.3); GLB MB 1.2/4.8/24.0 (gz 0.32/1.2/7.0); total load glTF 0.66/1.93/9.28 s, GLB 0.61/1.80/8.74 s; heap 29/104/400 MB; 0 errors; I2 shows ~1.0M triangles submitted per frame at 1M. 200k GLB and glTF stills are pixel-identical and non-blank [I4]. The same meshes as X3D IndexedTriangleSet: 1.7/7.0/38.7 MB, 0.8/1.4/13.5 s. Practical limit here ~1M triangles, memory ~0.4 KB per triangle; GPU frame overhead not measurable (S).

## 6. Visual fidelity
Best 3 (all in `feas/shots/`, 960x540 dsf 1; I looked at each):
| # | file | what it is | reads as beautiful | reads as flat or weak |
|---|---|---|---|---|
| 1 | `best1_endon_ref.png` (+ `_nobloom`, `best1_rtbloom.png`) | end-on; 300 shader ribbons, 5 Fresnel shells, tower bars, flash, fbm haze, page bloom | white-cyan vertex flash with ray spikes; multi-colour hair-thin filaments on near-black navy; orange and blue crown; soft glow on bright cores | crown is a dense comb band, shells faint, loopers few, no machinery backdrop |
| 2 | `best2_barrel_3000.png` | perspective barrel; 3000 ribbons (one program), 8 tower rings, translucent shells, bloom | depth: glowing cyan shell rims, orange cells, a fan of 3000 filaments | filaments thin at this exposure; tower cells uniform |
| 3 | `best3_side_sparks.png` | side view; 300 ribbons + native ParticleSystem sparks + flash, bloom | burst of coloured rays from a white core inside a glass-like barrel, orange sparks outside | tower plates read as stacked slabs; centre saturates |

Without bloom the frames are dimmer and harder (mean luma 0.149 vs 0.186 for #1). Native-only attempts (looked at: `tm_dir_quad.png`, `tm_env_trio.png`): emissive PhysicalMaterial towers over metal rings look **flat** (grey metal, flat yellow bars; EnvironmentLight washes the rings pale). Tone mapping on that scene [I4]: NONE clips 6.5% of pixels to 255 (EnvironmentLight view) and 7.3% sit above luma 0.9; ACES_NARKOWICZ 0% clipped, p99 luma 0.94; KHR_PBR_NEUTRAL 0% clipped, p99 0.89, only 0.35% above luma 0.9 and saturation kept best; ACES_HILL darkest (mean luma 0.076 vs 0.120 NONE, directional view). **ToneMapping does not touch custom ComposedShader output** (all-shader hero, NONE vs ACES: max difference 2/255): tone-map inside the shader (`1.0 - exp(-col*k)`).
Note: #2 and #3 files carry the tower-shader white term 0.9; #1 and the recipe below carry 0.35.

**Side by side with the target** (left the private reference still, right #1; the side-by-side is not published)
| aspect | reference | X_ITE #1 | match |
|---|---|---|---|
| view, palette | end-on, black/navy, haze | same; navy fbm haze via additive quad | yes |
| centre | white flash, radial spikes | white-cyan flash + cross/diagonal spikes (Billboard quad) | yes |
| filaments | hundreds; cyan/magenta/amber/emerald/violet; long rays plus curls | 300; same five colours; pulses and growth front available | mostly (fewer, less saturated) |
| helical loopers | ~12 tight circles at the centre | ~90 small helices, circles visible but lost in the flash | partly |
| shells | thick glassy blue-white rings with rim glow | 5 thin Fresnel rings | weaker |
| crown | thin orange/blue spikes, bright ring | bars in orange and blue, too wide and regular | partly |
| backdrop | dark machinery, dust | none (would need textured geometry; not attempted) | missing |
| bloom | soft film-like glow | threshold blur (CSS page overlay, or RenderedTexture pass) | approximate |

Pixel statistics [I4]: mean luma 0.190 vs 0.186; p50 0.105 vs 0.059 (mine darker mid-tones); p99 0.887 vs 0.968; channel-clipped 0.5% vs 2.3%; hue share blue 56% vs 58%, violet/magenta 13% vs 3%, red/orange 7.5% vs 1.4%, cyan 9.7% vs 18%. Magenta and orange are under-represented, cyan over.

**Native toolbox in X_ITE 16.5.1**
| effect | native? | best in-scene substitute / result | grade |
|---|---|---|---|
| additive glow | yes: `BlendMode` ONE/ONE + `DepthMode depthMask='false'` (component `X_ITE`) | used everywhere | C for the blend; **corrected 2026-11-06:** these measurements used `readOnly='true'`, which is not an X_ITE 16.5.1 DepthMode field (its fields are polygonOffset, depthRange, depthTest, depthFunction, depthMask) and is dropped silently, so depth writes were ON here and the result was not order independent (an independent review found it; the generators now write `depthMask='false'`, not re-measured) |
| per-fragment glow, energy pulses | yes: ComposedShader + uniform routed from TimeSensor | ribbon recipe | C |
| Fresnel rim shells | yes: shader with N.V | shell recipe | C |
| tone mapping | browser option `ToneMapping` (NONE, ACES_NARKOWICZ, ACES_HILL, ACES_HILL_EXPOSURE_BOOST, KHR_PBR_NEUTRAL), built-in shaders only | in-shader soft clip | C |
| ParticleSystem sparks | yes (X3D 4.0 field is `color`, not `colorRamp`); sparks look good | QUAD flash sprites show dark square edges: use the shader Billboard flash | C |
| **post-process bloom** | **no node** (0 hits for Bloom/PostProcess/FrameBuffer in the bundle) | **RenderedTexture (X3D 4.1, Texturing L4) + full-screen ComposedShader**: works, LDR, 72 taps, slight fringe on 1-px bars; or the page-level CSS overlay (not X3D) | C |
| HDR float target, DoF, lens flare, SSAO | no node | fake in shader / billboards | S |
| MSAA | option `Multisampling`; I1 context reports 0 samples, so thin-line aliasing in stills is instrument-limited | - | C/S |

## 7. Look recipes (copy-paste; the GLSL is printed from `gen_look.py` / `gen_bloom_rt.py`, so it is what rendered)
**Head and additive state** (X3D 4.0 file; the `X_ITE` component makes BlendMode/DepthMode known; DEF once, USE elsewhere):
```xml
<component name="Shaders" level="1"/><component name="Rendering" level="3"/><component name="X_ITE" level="1"/>
<BlendMode DEF="BM_ADD" sourceColorFactor="ONE" destinationColorFactor="ONE" sourceAlphaFactor="ONE" destinationAlphaFactor="ONE"/>
<DepthMode DEF="DM_RO" depthMask="false"/>   <!-- readOnly is not an X_ITE 16.5.1 field and was ignored in the measured runs -->
```
**Track ribbon shape** (one shared shader; each centre-line point appears twice with side -1/+1, shifted by side*0.004*(1,0.7,0.3) to avoid zero-area triangles; aNext = next point, the last one extrapolated; uBoost is optional and defaults to 0):
```xml
<Shape><Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/>
 <ComposedShader language="GLSL" DEF="SH_TRK">
  <field name="uTime" type="SFFloat" accessType="inputOutput" value="0.35"/><field name="uGrow" type="SFFloat" accessType="inputOutput" value="1"/>
  <field name="uExposure" type="SFFloat" accessType="initializeOnly" value="1.35"/><field name="uWidth" type="SFFloat" accessType="initializeOnly" value="0.7"/>
  <ShaderPart type="VERTEX"><![CDATA[data:x-shader/x-vertex,#version 300 es
precision highp float;
precision highp int;
...VS below...]]></ShaderPart>
  <ShaderPart type="FRAGMENT"><![CDATA[data:x-shader/x-fragment,#version 300 es
precision highp float;
...FS below...]]></ShaderPart>
 </ComposedShader></Appearance>
 <TriangleStripSet solid="false" stripCount="40 40 ..."><Coordinate point="..."/><ColorRGBA color="r g b a, ..."/>
  <FloatVertexAttribute name="aNext" numComponents="4" value="nx ny nz 1, ..."/><FloatVertexAttribute name="aMeta" numComponents="4" value="side s pT01 seed, ..."/></TriangleStripSet></Shape>
<TimeSensor DEF="CLK" cycleInterval="6" loop="true"/><TimeSensor DEF="GROW" cycleInterval="3.5" loop="true"/>
<ROUTE fromNode="CLK" fromField="fraction_changed" toNode="SH_TRK" toField="uTime"/><ROUTE fromNode="GROW" fromField="fraction_changed" toNode="SH_TRK" toField="uGrow"/>
```
Vertex stage (constant-pixel-width ribbon; `x3d_Viewport`, `x3d_*Matrix`, `x3d_Vertex`, `x3d_Color` are X_ITE built-ins):
```glsl
uniform mat4 x3d_ProjectionMatrix;
uniform mat4 x3d_ModelViewMatrix;
uniform ivec4 x3d_Viewport;
uniform float uWidth;
in vec4 x3d_Vertex;
in vec4 x3d_Color;
in vec4 aNext;
in vec4 aMeta;
out vec4 vColor;
out vec4 vMeta;
out float vDepth;
void main() {
  vec4 e0 = x3d_ModelViewMatrix * vec4(x3d_Vertex.xyz - aMeta.x * vec3(0.004, 0.0028, 0.0012), 1.0);   // undo the anti-degeneracy offset
  vec4 e1 = x3d_ModelViewMatrix * vec4(aNext.xyz, 1.0);
  vec4 c0 = x3d_ProjectionMatrix * e0;
  vec4 c1 = x3d_ProjectionMatrix * e1;
  vec2 hv = vec2(x3d_Viewport.zw) * 0.5;
  vec2 s0 = c0.xy / c0.w * hv;
  vec2 s1 = c1.xy / c1.w * hv;
  vec2 d = s1 - s0;
  float l = length(d);
  d = l > 1.0e-5 ? d / l : vec2(1.0, 0.0);
  vec2 n = vec2(-d.y, d.x);
  float w = uWidth * (0.55 + 0.9 * aMeta.z) * 3.0;
  vec2 off = n * aMeta.x * w;
  gl_Position = c0 + vec4(off / hv * c0.w, 0.0, 0.0);
  vColor = x3d_Color;
  vMeta = aMeta;
  vDepth = -e0.z;
}
```
Fragment stage (core + halo Gaussian, travelling pulses, growth front, soft-clip tone map, additive output):
```glsl
uniform float uTime;
uniform float uGrow;
uniform float uExposure;
uniform float uBoost;
in vec4 vColor;
in vec4 vMeta;
in float vDepth;
out vec4 fragColor;
float hash1(float n) { return fract(sin(n * 91.3458) * 47453.5453); }
void main() {
  float v = vMeta.x;
  float s = vMeta.y;
  float seed = vMeta.w;
  float core = exp(-v * v * 14.0);
  float halo = exp(-v * v * 5.0);
  float speed = 1.0 + floor(hash1(seed) * 3.0);
  float freq = 2.0 + floor(hash1(seed + 1.0) * 3.0);
  float ph = fract(s * freq - uTime * speed + hash1(seed + 2.0));
  float pulse = pow(1.0 - ph, 5.0);
  float fadeEnd = 1.0 - 0.7 * smoothstep(0.7, 1.0, s);
  float birth = hash1(seed + 3.0) * 0.30;
  float g = clamp((uGrow - birth) / 0.70, 0.0, 1.0);
  float vis = uGrow >= 0.999 ? 1.0 : 1.0 - smoothstep(g - 0.05, g, s);
  float head = uGrow >= 0.999 ? 0.0 : exp(-pow((s - g + 0.01) / 0.025, 2.0)) * step(0.001, g);
  float base = 0.62 + 0.38 * pulse;
  vec3 col = vColor.rgb * (halo * 0.30 + core * 0.95) * base * fadeEnd * vis;
  col += vec3(1.0) * core * (pulse * 0.55 * vis + head * 1.6);
  col *= vColor.a * uExposure * (1.0 + uBoost);
  col = 1.0 - exp(-col * 1.7);
  fragColor = vec4(col, 1.0);
}
```
**Fresnel translucent shell**: additive state as above; geometry = generated open cylinder (192 segments, radial normals) as `IndexedTriangleSet solid="false"` + `Normal`, inside `<Transform rotation="1 0 0 1.5708">` so the axis is the beam (the built-in Cylinder showed facets). Fields uRim (SFColor), uPow, uRibs, uPanels, uBright, uTime. Vertex stage: `vP = (x3d_ModelViewMatrix*x3d_Vertex).xyz; vN = x3d_NormalMatrix*x3d_Normal; vObj = x3d_Vertex.xyz; gl_Position = x3d_ProjectionMatrix*(x3d_ModelViewMatrix*x3d_Vertex);` Fragment:
```glsl
uniform vec3 uRim;
uniform float uPow;
uniform float uRibs;
uniform float uPanels;
uniform float uBright;
uniform float uTime;
in vec3 vN;
in vec3 vP;
in vec3 vObj;
out vec4 fragColor;
void main() {
  vec3 N = normalize(vN);
  vec3 V = normalize(-vP);
  float ndv = abs(dot(N, V));
  float fres = pow(1.0 - ndv, uPow);
  float ang = atan(vObj.z, vObj.x);
  float rib = smoothstep(0.93, 1.0, abs(sin(vObj.y * uRibs)));
  float pan = smoothstep(0.95, 1.0, abs(sin(ang * uPanels * 0.5)));
  float scan = 0.5 + 0.5 * sin(vObj.y * 9.0 - uTime * 6.2831853);
  float fade = exp(-length(vP) * 0.04);
  vec3 col = uRim * (fres * 0.85 + 0.012);
  col += uRim * 1.5 * (rib + 0.12 * pan) * (0.12 + 0.88 * fres);
  col += vec3(0.5, 0.75, 1.0) * fres * fres * scan * 0.35;
  col *= uBright * fade;
  col = 1.0 - exp(-col * 1.4);
  fragColor = vec4(col, 1.0);
}
```
**Calorimeter towers**: one IndexedTriangleSet of 5-face boxes with `FloatVertexAttribute aTw` (numComponents 4: energy, height-in-box 0/1, hot flag, 0); vertex stage `vTw = aTw.xyz; vDepth = -(x3d_ModelViewMatrix*x3d_Vertex).z; gl_Position = x3d_ProjectionMatrix*(x3d_ModelViewMatrix*x3d_Vertex);`. Fragment:
```glsl
uniform float uTime;
uniform float uBright;
in vec3 vTw;
in float vDepth;
out vec4 fragColor;
void main() {
  float E = vTw.x;
  float H = vTw.y;
  vec3 cold = vec3(0.25, 0.75, 1.0);
  vec3 hot = vec3(1.0, 0.62, 0.15);
  vec3 base = mix(cold, hot, vTw.z);
  float flicker = 0.9 + 0.1 * sin(uTime * 6.2831853 * 2.0 + E * 40.0);
  vec3 col = base * (0.22 + 1.5 * E) * (0.5 + 0.5 * H) * flicker;
  col += vec3(1.0) * pow(H, 7.0) * E * 0.35;
  col *= uBright;
  col = 1.0 - exp(-col * 1.5);
  fragColor = vec4(col, 1.0);
}
```
**Collision flash** (Billboard so it faces the camera; additive quad; vertex stage `vUV = x3d_Vertex.xy; gl_Position = x3d_ProjectionMatrix*(x3d_ModelViewMatrix*x3d_Vertex);`; field uFlash, animate with a ScalarInterpolator keys `0 0.04 0.12 0.4 1` values `0.5 1.6 1.0 0.7 0.6` routed from a TimeSensor):
```xml
<Billboard axisOfRotation="0 0 0"><Transform scale="1 1 1"><Shape><Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/><ComposedShader .../></Appearance>
 <IndexedFaceSet coordIndex="0 1 2 3 -1"><Coordinate point="-1 -1 0, 1 -1 0, 1 1 0, -1 1 0"/></IndexedFaceSet></Shape></Transform></Billboard>
```
```glsl
uniform float uFlash;
in vec2 vUV;
out vec4 fragColor;
void main() {
  vec2 p = vUV;
  float r = length(p);
  float glow = exp(-r * r * 9.0) * 0.9 + 0.35 / (1.0 + r * r * 90.0);
  float st = exp(-abs(p.y) * 38.0) * exp(-abs(p.x) * 2.4) + exp(-abs(p.x) * 38.0) * exp(-abs(p.y) * 2.4);
  float d1 = exp(-abs(p.x - p.y) * 45.0) * exp(-abs(p.x + p.y) * 3.0);
  float d2 = exp(-abs(p.x + p.y) * 45.0) * exp(-abs(p.x - p.y) * 3.0);
  float edge = 1.0 - smoothstep(0.75, 1.0, r);
  vec3 col = vec3(0.85, 0.93, 1.0) * (glow + 0.55 * st + 0.18 * (d1 + d2)) * edge * uFlash;
  col = 1.0 - exp(-col * 1.5);
  fragColor = vec4(col, 1.0);
}
```
**Haze**: a far quad inside a Billboard (`Transform translation="0 0 -16" scale="26 15 1"`), same quad and vertex stage as the flash, additive; fields uTime, uGain (about 0.4 for near-black navy):
```glsl
uniform float uTime;
uniform float uGain;
in vec2 vUV;
out vec4 fragColor;
float h(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(h(i), h(i + vec2(1.0, 0.0)), f.x), mix(h(i + vec2(0.0, 1.0)), h(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p) {
  float a = 0.5;
  float s = 0.0;
  for (int i = 0; i < 5; i++) { s += a * n(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; }
  return s;
}
void main() {
  vec2 p = vUV;
  float r = length(p);
  float f = fbm(p * 2.4 + vec2(uTime * 0.6, 0.0));
  float rad = exp(-r * r * 1.1);
  vec3 col = (vec3(0.020, 0.052, 0.110) * (f * 1.6) * rad * 2.6 + vec3(0.000, 0.016, 0.040) * rad) * uGain;
  fragColor = vec4(col, 1.0);
}
```
**Shower sparks** (native ParticleSystem; component `ParticleSystems` level 2; worked in 16.5.1):
```xml
<ParticleSystem geometryType="LINE" maxParticles="700" particleLifetime="1.6" lifetimeVariation="0.6" particleSize="0.3 0.3" colorKey="0 0.5 1">
 <Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/><Material emissiveColor="1 0.8 0.4" diffuseColor="0 0 0"/></Appearance>
 <ConeEmitter position="0 0 0" direction="0 0 1" angle="3.14159" speed="2.2" variation="0.9" mass="0" surfaceArea="0"/>
 <ColorRGBA containerField="color" color="1 0.95 0.7 0.9, 1 0.55 0.15 0.6, 0.6 0.2 0.1 0"/></ParticleSystem>
```
**In-scene bloom** (X3D **4.1** file; components Shaders, X_ITE, Texturing 4; the whole event scene with its own NavigationInfo/Viewpoint/Background goes inside `RenderedTexture`; `singleFrame="false" updateInterval="0"` gives continuous update; `gen_bloom_rt.py IN.x3d OUT.x3d --gain 0.6 --thr 0.4 --sigma 11` wraps any scene):
```xml
<NavigationInfo type='"NONE"' headlight="false"/><Viewpoint position="0 0 5"/>
<Shape><Appearance><ComposedShader language="GLSL">
 <field name="uTex" type="SFNode" accessType="inputOutput"><RenderedTexture width="960" height="540" singleFrame="false" updateInterval="0" repeatS="false" repeatT="false"> ...event scene... </RenderedTexture></field>
 <field name="uPx" type="SFVec2f" accessType="initializeOnly" value="0.00104 0.00185"/><field name="uGain" type="SFFloat" accessType="initializeOnly" value="0.6"/>
 <field name="uThr" type="SFFloat" accessType="initializeOnly" value="0.4"/><field name="uSigma" type="SFFloat" accessType="initializeOnly" value="11"/> ...ShaderParts...
</ComposedShader></Appearance><IndexedFaceSet coordIndex="0 1 2 3 -1"><Coordinate point="-1 -1 0, 1 -1 0, 1 1 0, -1 1 0"/></IndexedFaceSet></Shape>
```
Vertex stage: `in vec4 x3d_Vertex; out vec2 vUV; void main() { vUV = x3d_Vertex.xy * 0.5 + 0.5; gl_Position = vec4(x3d_Vertex.xy, 0.0, 1.0); }`. Fragment:
```glsl
uniform sampler2D uTex;
uniform vec2 uPx;
uniform float uGain;
uniform float uThr;
uniform float uSigma;
in vec2 vUV;
out vec4 fragColor;
void main() {
  vec3 c = texture(uTex, vUV).rgb;
  vec3 b = vec3(0.0);
  float ws = 0.0;
  for (int r = 1; r <= 6; r++) {
    float rad = uSigma * float(r) / 3.0;
    float w = exp(-float(r * r) / 4.5);
    for (int k = 0; k < 12; k++) {
      float a = 6.2831853 * (float(k) + 0.5 * float(r)) / 12.0;
      vec3 s = texture(uTex, vUV + vec2(cos(a), sin(a)) * rad * uPx).rgb;
      b += max(s - vec3(uThr), vec3(0.0)) * w;
      ws += w;
    }
  }
  b /= ws;
  vec3 col = c + b * uGain * 12.0;
  col = 1.0 - exp(-col * 1.25);
  fragColor = vec4(col, 1.0);
}
```
Untested: navigation and picking through the RenderedTexture, resize handling, cost on a GPU (S).
**Page-level bloom fallback** (not X3D; a 2D canvas fed from the WebGL canvas in the same task as the render, CSS does the blur; my harness hooked it after each rAF callback that issued draws, a production hook is untested, S):
```js
const src = canvas.shadowRoot.querySelector('canvas'), ov = document.createElement('canvas'); ov.width = W >> 1; ov.height = H >> 1;
ov.style.cssText = `position:fixed;left:0;top:0;width:${W}px;height:${H}px;pointer-events:none;mix-blend-mode:screen;filter:brightness(0.72) contrast(2.6) blur(9px) brightness(1.7) saturate(1.25)`;
document.body.appendChild(ov); const cx = ov.getContext('2d'); /* after each render: */ cx.drawImage(src, 0, 0, ov.width, ov.height);
```

## 8. Three.js display (Phoenix class) vs X3D with X_ITE (all S: from memory, not installed or run)
| topic | three.js event display (e.g. Phoenix) | X3D with X_ITE, as measured above | verdict |
|---|---|---|---|
| format and standard | JSON event files plus glTF/OBJ geometry, app-specific | ISO X3D 4.x file, schema-validated, glTF via Inline | X3D adds a standard, archivable file |
| validation | tests and review | Loom witnesses (grades, laws, fixtures) + schema | X3D adds (the point of the demo) |
| instancing | InstancedMesh, 1e5+ objects | none: 1 draw per USE (C); merge into one mesh | X3D loses |
| custom shaders | ShaderMaterial, onBeforeCompile | ComposedShader works (C) | parity |
| post-process bloom | EffectComposer / UnrealBloomPass | RenderedTexture + shader (C) or page overlay | three.js easier, X3D possible |
| HDR, MSAA, SSAO, DoF | available | tone-mapping option, no HDR target | X3D loses |
| picking | Raycaster, line threshold | TouchSensor/Anchor, proxy needed for ribbons (C) | parity, X3D declarative |
| animation | tween libs, render loop | TimeSensor + ROUTE, uniform routing (C), law-32 trap | X3D declarative, needs the guard |
| big data | typed arrays direct to GPU, streaming | XML parse: 12 MB 3000-track file 2.9 s (C) | X3D loses (binary/gz may help, S) |
| community | large, HEP-specific tooling | small | X3D loses |

## 9. Failed, unmeasured, honest limits
- Never measured: frame rates, GPU memory, real-GPU behaviour of any trap (software GL only). Hover/pick tested by synthetic mouse moves only.
- Programs linked at N=3000 for S3/S4 not captured directly (the 3000-scene screenshot timed out after load); ~3011 is inferred (L) from 311 at N=300. Times in the table come from the bench.
- The S1-vs-S2 rendering difference, the crash mechanism, and why `Cylinder subdivision="96"` still looked faceted are all unexplained.
- The 50k instanced-tower time (665 s) overlapped other jobs: upper bound.
- ParticleSystem QUAD flash has dark square sprite edges (not fixed). The native PBR look is flat (not improved). The reference's machinery backdrop was not attempted. Animated looks were judged from stills only.
- Harness traps found: the Node static server must serve `.css` as text/css (octet-stream made the canvas grow unbounded and stills blank); per-frame camera jitter or continuous redraw blanks `screenshot()`; `readPixels` on the MSAA framebuffer gave a meaningless probe (dropped); the component probe lists BlendMode/DepthMode/ParticleSystem as "absent" because components load lazily (the nodes work once declared). Fixture bugs fixed on the way: cube-map faces are `frontTexture` etc., PrimitivePickSensor geometry is `pickingGeometry`, Anchor url resolves relative to the scene.
- Components reported by I1 include Shaders 1, Rendering 5, Texturing 4, ParticleSystems 3, Picking 3, Lighting 3, Interpolation 5, Scripting 1, GaussianSplats 1, X_ITE 1 (`log_exp_info.txt`).

## 10. Scripts and files (all in `kit/examples/hep/feas/`)
- Generators: `evtcommon.py` (synthetic helices), `gen_event.py` (load matrix; `python3 gen_event.py matrix site/scenes`), `gen_misc.py` (ladder, tubes, anim, freeze, pick, shells, PBR, particles), `gen_look.py` (hero looks and all GLSL; `all`, `hero`), `gen_bloom_rt.py` (RenderedTexture bloom wrapper), `gen_crash_probe.py` (degenerate-triangle probes), `gen_dbg.py` (shader probes).
- Harness: `glspy.js` (WebGL spy), `bench.cjs` + `site/bench.html` (load bench), `shots.cjs` + `site/shot.html` (stills), `exp.cjs` (freeze, pick, picksensor, info), `imgtools.py` (pixel stats), `summarize.py` (result tables), `run_matrix.sh`, `run_rest.sh`, `serve.sh`, `dbg2.cjs`, `dbg3.cjs`.
- Data: `results_*.json`, `log_*.txt` (including `log_exp_*.txt`, `log_shader_compile.txt`), stills in `shots/` (best3 plus `best1_vs_reference.png`, `sh_order_pair.png`, `tm_*.png`, `lw_ladder.png`, `part_sparks.png`, `rtbloom_*.png`, `hero_v1-v4`), look scenes in `site/looks/` (`best1_endon_ref.x3d`, `best1_rtbloom.x3d`, `best2_barrel_3000.x3d`, `best3_side_sparks.x3d`). X_ITE came from `npm pack x_ite@16.5.1`, unpacked to `site/x_ite/`.
- Regenerate #1: `python3 gen_look.py hero site/looks/best1_endon_ref.x3d --smooth 1 --nz 2 --nphi 210 --wfac 0.3 --hot 0.9 --flash_scale 1.0 --haze_gain 0.4 --width 0.7 --n 300 --shell_hl 0.4 --shell_bright 0.75 --shell_rmin 0.9 --tower_bright 1.1 --tower_h 0.34 --tower_r0 2.2 --tower_e0 0.07 --loop_frac 0.3 --curve_frac 0.1 --loop_scale 0.75`.
- #2: `--cam persp --n 3000 --width 0.38 --exposure 0.6 --smooth 1 --nz 8 --zfrac 0.5 --nphi 160 --wfac 0.4 --hot 0.8 --flash_scale 0.8 --haze_gain 0.8 --shell_hl 1.0 --shell_bright 0.7 --tower_bright 0.7 --tower_h 0.3 --tower_e0 0.04 --loop_frac 0.25 --loop_scale 0.6`.
- #3: `--cam side --n 300 --sparks 700 --width 0.8` with the #2 flags except `--flash_scale 1.0 --tower_bright 0.5` (#2 and #3 were generated before the tower white term changed from 0.9 to 0.35; the saved `.x3d` files are authoritative).
- Stills: `SETTLE=2500 node shots.cjs shots "looks/best1_endon_ref.x3d|best1_endon_ref|bloom=9&bpre=brightness(0.72) contrast(2.6)&bgain=1.7"`; in-scene bloom: `python3 gen_bloom_rt.py site/looks/best1_endon_ref.x3d site/looks/best1_rtbloom.x3d --gain 0.6 --thr 0.4 --sigma 11`.
