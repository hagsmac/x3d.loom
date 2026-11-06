# HEP-EVENT-WITNESS: a demo witness for collider-event scenes

Status: prototype, `hep-demo/v2` (v2, after an independent review: the scene graph is read fail-closed and every drawing is bound to its own event, section 6c; v1 added look v2 and the merged convention, section 6b; v0 covered look v1 only and was never published). This is a **demo plausibility witness**. It is not a physics validation and it makes no STEM-grade claim. It decides whether a generated collider event and the X3D scene drawn from it are *plausible enough to show*: the numbers have sane units, the charges add up, the tracks bend the way their momentum and the field say, everything sits inside the detector, every particle above the drawing cuts is drawn exactly once, and every drawn track carries the shared shader with the right per-track data. The witness itself still renders nothing and compiles no GLSL. Since 2026-11-06 the look v2 scenes have been rendered in X_ITE with 0 shader or console errors, but by the stills harness, not by this witness (see `runs/hep-demo-v2-20261106/frames/LOOK-V2.md`; behaviour and look-match stay visibly not run in the profile).

The look comes from a generated reference video (two stills: the quiet "before" frame and the "hero" frame). The workflow is: reference video sets the look, the builder writes X3D, the witness checks the binding, an eye still has to check the look.

## 1. What the witness says, and what it does not

| It checks | It does not check |
|---|---|
| event JSON parses, mothers are earlier indices, numbers are finite | that the event is a good simulation of anything |
| units: a factor-1000 slip (plus or minus 0.3 decades) in the median mass of known final-state particles, in the helix radius or in the scene extent; detector sizes inside 0.05 to 50 m | masses, resonances, invariant-mass peaks (dropped on purpose: MASS_SHELL, RESONANCE) |
| charge: final-state sum equals the declared incoming; each track equals its particle | calorimeter energy sums (dropped: CALO_SUM) |
| four-momentum: final state minus declared incoming within 0.5 GeV + 1e-4 E (loose by design) | precision momentum balance (the spec refuses `p4.rel_tol` above 5 percent, but 0.5 GeV is still loose) |
| curvature = 0.2998 B / pT on the declared helix, on the hits, and on the drawn polyline (15 percent + 0.01 /m + rounding noise) | bends smaller than the rounding of the stored points (counted as unresolved, section 8) |
| bend sense from charge and field direction | the sign of B in the scene's own camera handedness |
| containment of hits, vertices, drawn points and tower corners in the declared volumes | material, shower shape, energy loss |
| bijection: every drawable particle has one drawn track, every `trk_` and `twr_` shape maps to the event, none hidden (Switch, Collision proxy), none twice, none reused or tucked where the reader does not look | that the shape *looks* like a track |
| binding of each drawing to its own event: the drawn path starts at its vertex, leaves along its phi, dips along its eta and reaches as far as its helix goes; tower needles sit in their own cell | the exact drawn length past the tracker (extensions are judged on join, angle and containment) |
| shader binding: one ComposedShader per track with data: URLs, attributes supplied with the right count and per-track values (id, charge, pT, birth time inside its window, species from the pdg, arc length from zero along the drawn path, look rows), clock ROUTE from a TimeSensor | that the GLSL compiles, runs, or looks right |

## 2. Pipeline and files

| Step | File | Needs | Output |
|---|---|---|---|
| generate | `kit/examples/hep/pythia_fixtures.py` | `pythia8mc` (the only non-stdlib script; run used 8.318.3) | event JSON, one per event |
| response | `kit/examples/hep/hep_response.py` | stdlib | tracks, hits, towers from truth particles (truth-level toy: no smearing, no showers) |
| exact reference | `kit/examples/hep/exact_events.py` | stdlib | hand-computed Z to mu mu; deterministic toy shower (labelled synthetic) |
| select | `kit/examples/hep/select_fixtures.py` | stdlib | the committed fixtures, each under 190 KB |
| spec | `kit/examples/hep/hep-demo-spec.json` | n/a | every threshold (change it here, never in code) |
| build scene | `kit/examples/hep/build_event_scene.py` | stdlib | `<stem>.x3d` plus `<stem>.event.json` naming it; `--look v2` for merged ribbons, muon extensions and the spiky crown, `--bloom` for the RenderedTexture wrappers (look v1 output is byte-identical to before) |
| witness | `kit/loomkit/hepevent.py`, CLI `loom hepevent` | stdlib | witness record `hep-event`, grade C |
| profile | `kit/profiles/hep-demo.json` | n/a | `hep-demo/v2`: required hep-event (10 events, 10 scenes: every fixture in look v1 and look v2), traps (11 rules); visible not run: grammar, meaning, behaviour, look-match, eyes, real-gpu |
| rehearsal | `kit/examples/run_hep_event.sh` | stdlib | candidate (look v1 in `events/`, look v2 in `events-v2/`), witnesses, acceptance, receipt, three negative controls |
| tests | `kit/tests/test_hepevent.py`, `kit/tests/hepevent-last-run.json` | stdlib | 206 negative, 17 positive, 2 CLI controls in both modes |
| render | `kit/examples/hep/render/` (`fetch_xite.sh`, `shots.cjs`, `site/shot.html`, `site/glspy.js`) | Node, Playwright, X_ITE 16.5.1 fetched by npm (not committed) | stills, load CPU time, program and draw counts, shader logs, console errors |

Fixtures (`kit/examples/hep/fixtures/`, five files, each under 200 KB):

| File | Source | Final-state | Tracks (charged) | Hits | Towers | Bytes |
|---|---|---|---|---|---|---|
| `exact-zmumu.event.json` | hand-computed two-body decay, no generator | 2 | 2 (2) | 16 | 2 | 1,874 |
| `pythia-zmumu.event.json` | Pythia 8.318, Z to mu mu, event 027 of the seed-11 run | 542 | 462 (240) | 1018 | 124 | 177,865 |
| `pythia-qcd-demo.event.json` | Pythia 8.318, HardQCD pTHat above 30 GeV, event 014 of the seed-22 run (the hero scene) | 607 | 497 (235) | 917 | 132 | 189,695 |
| `pythia-qcd-inflight.event.json` | same, decays in flight allowed (event 002 of the seed-22 in-flight run) | 496 | 382 (194) | 756 | 118 | 157,840 |
| `pythia-dijet-hero.event.json` | Pythia 8.318, HardQCD pTHat above 400 GeV, event 026 of 30 of the seed-41 run: the most charged tracks above 5 GeV at abs(eta) below 1 (41); the look v2 hero | 512 | 456 (204) | 1100 | 168 | 179,211 |

## 3. Event format `loom.hep-event/1`

Units: metres, GeV, tesla, nanoseconds. z is the beam axis, B is signed along +z.

| Field | Type, unit | Meaning |
|---|---|---|
| `schema` | string | must equal `loom.hep-event/1` |
| `id`, `provenance` | string, object | name; `generator`, `kind` (`generator` or `synthetic`), `settings`, `source` |
| `detector.b_field_t` | number, T, non-zero | solenoid field along +z (negative reverses every bend) |
| `detector.tracker` | `r_max_m`, `half_length_m`, `layer_radii_m[]` | cylinder the tracks live in; layers place the hits |
| `detector.calorimeter` | `r_min_m`, `r_max_m`, `half_length_m` | barrel only; towers sit between the radii (endcaps are not modelled) |
| `incoming` | `px, py, pz, E` GeV, `charge` | declared initial state (the two beams for Pythia) |
| `particles[]` | `pdg`, `status`, `charge`, `px, py, pz, E`, `mothers[]` | HepMC status: 1 final state, 2 decayed, 4 beam. `mothers` are earlier indices (at most 2 kept). Optional `vertex_m` (production point), `t_prod_ns`, `gen_status` (the generator's own code) |
| `tracks[]` | `i` (equals position), `particle`, `charge`, `pt`, `eta`, `phi` | one per drawn trajectory |
| `tracks[].helix` | `radius_m` (null if straight), `sense` (-1 clockwise, 0, +1), optional `vertex_m` | radius = pT / (0.2998 B) |
| `tracks[].hits[]` | `[x, y, z]` m, optional | first crossing of each tracker layer |
| `tracks[].t_prod_ns` | ns, optional | production time; becomes the shader birth time |
| `towers[]` | `i`, `eta`, `phi`, `E`, optional `em_frac`, `t_arr_ns` | calorimeter cells (72 phi bins, 0.0873 in eta) |
| `scene` | relative path, optional | the X3D scene for this event; no `..`, not absolute |

## 4. Spec `loom.hep-event-spec/1` (all thresholds live here)

| Key | Value | Used by |
|---|---|---|
| `units.length_range_m` | [0.05, 50] | detector sizes outside this are millimetres read as metres |
| `units.ratio_log10_tol` | 0.3 | a scale error of 3 decades (+-0.3) is a unit slip |
| `p4.abs_tol_gev`, `p4.rel_tol` | 0.5, 1e-4 | loose balance of final state against incoming; `rel_tol` above 0.05 is refused |
| `charge.abs_tol` | 1e-6 | charge sums |
| `curvature.rel_tol`, `abs_tol_per_m` | 0.15, 0.01 | generous curvature tolerance |
| `curvature.straight_sagitta_m` | 0.002 | below this a bend is called straight (also the floor for the sense check) |
| `curvature.point_resolution_m` | 0.0001 | worst-case coordinate error of a stored point (rounding to 4 decimals is 5e-5; the spec takes twice that) |
| `curvature.resolvable_sagitta_m` | 0.0003 | smallest expected bend that is fitted; must be at least `point_resolution_m` |
| `containment.margin_m` | 0.02 | slack on the tracker and calorimeter volumes |
| `scene.required` | true | an event without a scene is `EVT_SCENE_BIJECTION` |
| `scene.unreadable_nodes` | reject | Script, Inline, PROTO the reader cannot expand are `EVT_PARSE` |
| `scene.draw_eta_max`, `draw_min_pt_gev`, `draw_min_neutral_e_gev` | 10.0, 0.15, 0.3 | which particles owe a track; the converter reads the same file |
| `scene.invisible_pdg` | 12, 14, 16 | neutrinos owe nothing |
| `scene.min_points` | 2 | points per drawn track |
| `scene.shader` | `time_field u_phase`, `pt_rel_tol 0.01`, `ident a_ident [id, charge, pt, birth_s]`, attributes `a_ident` (4), `a_arc` (1, varies), `a_species` (1) | EVT_SHADER |

## 5. Codes, check order, and why each matters

Order (the first broken rule raises, with its code): units, charge, four-momentum, declared helix and hits (tracks), event containment, scene-required, then for the scene: bijection, geometry (containment, curvature, sense), shader. One stable code per cause.

| Code | Raised when | Why it matters for a demo | Negative controls |
|---|---|---|---|
| `EVT_PARSE` | not JSON, NaN/Infinity, wrong schema, missing or mistyped field, dangling mother, scene not XML, entity declarations, USE before DEF, a USE cycle or a reuse that expands past the budget, unreadable or unknown node, LOD, bad coordIndex, scene path escapes or is missing; merged strips whose stripCount, Coordinate or numComponents do not add up | a malformed event must stop here, not draw half a scene or throw inside the viewer | 48 |
| `EVT_SPEC` | threshold file malformed or inconsistent (including `scene.merged`: an offset tolerance as wide as the ribbon is refused; reach, birth, arc, species, tower-cell, look and join-angle sections bounded) | the thresholds are the contract; a typo in the spec must not loosen a check silently | 36 |
| `EVT_UNITS` | MeV read as GeV, millimetres read as metres (detector, helix radius, scene extent) | the failure that silently shrinks or blows up a scene by 1000; also a field outside 1 mT to 100 T, a scene scaled to nothing or onto the axis | 8 |
| `EVT_CHARGE` | final-state charge differs from incoming, or a track differs from its particle | the hue (magenta or cyan) and the bend direction come from the charge | 3 |
| `EVT_4MOM` | final-state four-momentum differs from incoming by more than 0.5 GeV + 1e-4 E, beams differ from incoming, or no final state | catches a dropped or duplicated particle and a wrong pz; loose on purpose | 3 |
| `EVT_CURVATURE` | declared, measured or drawn bend disagrees with pT, charge and B (fitted circle, or straight-line departure for unresolved paths) | the one visual cue a viewer can check by eye: soft tracks curl, stiff tracks run straight | 10 |
| `EVT_SENSE` | bends clockwise where counter-clockwise is required | a mirrored detector is a plausible-looking wrong picture | 2 |
| `EVT_CONTAINMENT` | hit, vertex, drawn track point or tower corner outside its volume; tower beyond the barrel; a non-muon drawn on past the tracker; a muon extension outside the declared muon system | tracks poking through the calorimeter crown break the picture; only muons pass it; a tower needle drawn outside its own cell | 12 |
| `EVT_SCENE_BIJECTION` | a drawable particle with no track, a `trk_`/`twr_` shape (or merged strip) with no event row, a shape or strip drawn twice or hidden by a Switch, a non-Shape DEF, fewer points than `min_points`, a track on a non-final-state particle, two tracks on one particle, scene required but absent; a merged shape with no declared convention, a strip that is not the declared ribbon (odd count, pair not offset by the declared amount, id not an index), a muon that leaves the tracker without its extension, an extension not joined to its track, or joined inside the tracker, or turning more than the declared angle, or running back in; a track hidden as a Collision proxy, inside a Billboard, reused by USE, or in a place the reader does not look; **a drawn path that does not start at its vertex, points or dips the wrong way, or stops short of its own helix (it is not this track's path)** | "all 300 or 3000 particles" is a claim about count, and each drawing must be the particle it counts for | 46 |
| `EVT_SHADER` | a track without the shared ComposedShader, raw shader text instead of a data: URL, missing clock field or ROUTE, missing or short vertex attribute, attribute not declared in the vertex source, `a_ident` id, charge, pT or birth wrong, `a_ident` varying along a track; the two edges of a ribbon disagreeing; a tower's `a_cell` energy, em fraction or arrival wrong or varying between its spikes; an extension whose ident row is not its track's; a birth time outside its production window, a species code that is not the particle's, an arc length that runs backwards, starts off zero or spans more than the drawn path; a strip without its look attribute or whose side or id changes along it; a tower set without the crown clock | the flat default look is what a missing shader draws, with no error; wrong data draws a wrong colour or a wrong time with no error either | 38 |
| total | | | 206 (17 positive, 2 CLI) |

## 6. The look: reference still to builder to witness

| Reference property | Builder (`build_event_scene.py`) | Witness |
|---|---|---|
| end-on view down the beam axis, z toward the viewer | `Viewpoint vp_endon` at (0, 0, 22), orientation 0 0 1 0, fieldOfView 0.21 (default) | none; look-match not run |
| second three-quarter view | `Viewpoint vp_three_quarter` at (5.6, 3.3, 8.4) looking at the origin, fieldOfView 0.7 | none |
| deep navy-to-black background | `Background` sky and ground gradient; no Fog node, so no haze (not done) | none |
| nested translucent cylindrical shells, cool blue rim | `Cylinder` shells (tracker 1.1 m, calorimeter 1.3 and 1.8 m, beam pipe 0.03 m) with emissive blue and `transparency` 0.82 to 0.88; layer rings and staves in the ring shader (rim brightness by level, flash ripple through the rings at 3 m/s) | tower and track containment against the same radii |
| white central flash | `PointSet` at the origin with `flashShader` (`gl_PointSize` 26 to 356 px, decays with exp(-2.2 s), cross spikes) | none |
| hundreds of thin glowing filaments, hues cyan, magenta, amber, emerald, violet | one `IndexedLineSet` per track, all USE `trkShader`; hue from charge and species | EVT_SHADER binds it; EVT_SCENE_BIJECTION counts it |
| low-pT tracks in tight helical loops, high-pT straight | sampled helix (7 degrees per step, at most 2.5 turns, until it leaves the tracker) | EVT_CURVATURE and EVT_SENSE on the drawn polyline |
| outer crown of orange and blue tower bars | `IndexedFaceSet` box per tower, final geometry stored, `twrShader` grows it from its base; amber is electromagnetic, blue hadronic | EVT_CONTAINMENT on tower corners; EVT_SCENE_BIJECTION |
| tracks grow outward over about 3 s after a flash | `TimeSensor clock` (12 s loop) ROUTEd to `u_phase`; head = (t - 0.5 s - birth) x 0.9 m/s | EVT_SHADER requires the ROUTE and per-track birth |
| towers light up when their track arrives | tower arrival = calorimeter path length / 0.9 m/s + 0.5 s, smoothstep light-up and a flare | arrival is data in the scene; not checked against tracks |
| labels | `Billboard` + `Text` for the eight highest-pT tracks (`lbl_<i>`) | none |

Shader data (one ComposedShader per role, DEF'd once in an unselected `Switch`, USE'd everywhere):

| Shader | Attribute | Components | Meaning | Constant per track |
|---|---|---|---|---|
| `trkShader` | `a_ident` | 4 | id, charge, pT (GeV), birth (s) | yes (checked) |
| | `a_arc` | 1 | metres of 3D arc length at the vertex | no (drives growth and the outward pulse) |
| | `a_species` | 1 | 1 e, 2 mu, 3 hadron, 4 proton, 5 photon, 6 neutral, 7 other | yes |
| `twrShader` | `a_tower` | 4 | E (GeV), arrival (s), em fraction, outer-face flag | per corner |
| | `a_base` | 3 | bar base corner | per corner |
| `ringShader` | `a_ring` | 3 | radius, phase, level | per vertex |
| `flashShader` | none | | point sprite | |

Brightness is log(1 + pT) / log(61) (saturates near 60 GeV). The hue is by species with charge as the tie-break (positive cyan, negative magenta, electron emerald, muon violet, proton amber, photon pale yellow, neutral warm orange).

Animation timeline (cycle 12 s, SPEED 0.9 m/s, a declared slow motion; light moves 2.998e8 m/s and the scene says so in a meta tag):

| t (s) | Event |
|---|---|
| 0 to 0.5 | fade in; towers dim |
| 0.5 | flash (sprite at its largest), ripple runs through the rings at 3 m/s |
| 0.5 + birth | each track starts growing; birth = production time in slow motion + up to 0.1 s of fixed per-id jitter |
| median track | 2.8 m of arc to the tracker end: finished at 3.1 s of growth (p90 3.3 s, p99 5.4 s, longest loop 7.4 s) in the hero fixture |
| tower arrival | the calorimeter path length / 0.9 m/s after the flash; the bar grows and flares over 0.45 s |
| 10.4 to 11.9 | fade out; at 12 the cycle repeats |

Loom traps honoured by the builder (the repository `traps` witness reads the scenes too and finds none of its 11):

| Trap | How |
|---|---|
| shader source must be a data: URL | `url='"data:x-shader/x-vertex,..."'`, fragment likewise; raw text in a ShaderPart is `EVT_SHADER` |
| `active` is a reserved GLSL word | builder refuses it; test checks the text |
| every component declared in the head | `<component name='Shaders' level='3'/>` (level taken from memory: grade L) |
| no int literal where a float is needed, no `#`, `%`, quotes, `//` | `glsl()` refuses them; `builder_hygiene()` re-checks |
| ROUTE before DEF | every ROUTE written after every DEF |
| exceptions inside X_ITE callbacks | no Script node at all; the clock is a TimeSensor routed straight to the shader field |
| one shader per role, not per track | `shader_defs` Switch with `whichChoice='-1'`; tracks USE |

## 6b. Look v2 and the merged convention (added 2026-11-06)

Look v2 draws the same events with the recipes measured in X_ITE (`docs/COLLIDER-XITE-FEASIBILITY.md`): screen-space ribbon tracks in a few merged Shapes sharing ONE ComposedShader, muons drawn on through the calorimeter, a thin spiky crown from the real tower energies. One Shape per track would cost 27 s of load at 5,000 tracks; one program per track would cost about 15 ms each with no dedupe. Merging made the old scene convention (one `trk_<i>` Shape per track) impossible, so the witness learned to read the merged form, and only when the spec declares it:

| spec `scene.merged` | value | what the witness does with it |
|---|---|---|
| `offset_m` | (0.004, 0.0028, 0.0012) | every ribbon vertex pair must sit at -/+ this offset (the builder's guard against the zero-area crash); the pair midpoints are taken as the drawn path, so curvature, sense and containment are judged on what the shader draws |
| `offset_tol_m` | 0.0002 | must be under half the smallest pair gap, or the spec is refused (a looser tolerance could not tell a ribbon from two paths) |
| `tower_cell` | `a_cell` = (id, E, em_frac, arrival_s), `e_rel_tol` 0.01 | each tower's spikes must carry one row, its energy within 1 percent of the event's |
| `extensions` | pdg [13], r_max 3.4 m, half-length 4.5 m, join 0.01 m | only muons may continue past the tracker, joined to where their track ends, inside the muon system; every muon whose drawn path leaves the tracker must continue |

Names: `trkset_<n>` (tracks), `muext_<n>` (muon extensions), `twrset_<n>` (towers), each a Shape holding one `TriangleStripSet`, one strip per track or per spike, named by its ident row. Without `scene.merged` such a shape is a bad DEF (EVT_SCENE_BIJECTION), so a merged scene can never be read as "nothing to check". Look v1 scenes are read exactly as before (the v1 builder output is byte-identical to the v0 run).

What a pass reports for look v2 (from the rehearsal record): hero 497 tracks in 1 merged Shape with 497 strips, 132 towers in 1 merged Shape; pythia-zmumu 462 tracks and both muons extended; every drawn path judged (`scene_curvature_judged` equals the track count).

## 6c. After review: fail-closed reading and binding to the event (v2, added 2026-11-06)

An independent three-lens review of v1 (witness, look, hygiene; its 32 crafted attacks are now all refused with a fitting reason) found that a pass could be bought. The fixes, each with its own controls in `review_controls()` of `kit/tests/test_hepevent.py` (51 negatives, 2 positives):

| v1 hole | v2 rule | spec |
|---|---|---|
| a `<Group USE='tracks'/>` drew every track twice and passed; LOD, unknown grouping nodes and a Collision proxy were read as drawn | every USE is followed into its DEF (cycle check, expansion budget 2,000,000 nodes); a USE of track geometry is a bad DEF; LOD and unknown nodes outside a Shape are unreadable; a Collision proxy and a Switch that does not select a child hide it (metadata children are not choices); a named shape inside a Billboard, ParticleSystem or any node the reader does not walk is refused | none |
| curvature was graded against the drawing's own fit, so any circle of the right radius passed: a 1 mm stub, a shifted, rotated or squashed copy | each drawn path must start within `start_tol_m` of its vertex, leave within `dir_tol_rad` of its phi, rise with the dip angle of its eta within `pitch_tol_rad` (well conditioned at every eta), and reach at least its own helix's extent inside the tracker minus `reach_tol_m` | `scene.reach` |
| shader data was checked for presence: a late birth, a pion coloured as an electron, an arc that ran backwards all passed | birth time inside its production window, species code from the pdg, arc from zero (or from where the track ends, for an extension), monotone, spanning the drawn path | `shader.birth`, `shader.species`, `shader.arc` |
| tower spikes were checked for energy only | each spike pair carries one `a_cell` row; its base sits in its own (eta, phi) cell and its tip in its phi cell at the same z | `merged.tower_cell` |
| an extension was joined by distance only | it must start on the tracker boundary heading out, turn less than `join_angle_deg` where it joins, stay in the muon system and never run back inside the tracker | `merged.extensions.join_angle_deg` |
| strips were read without their look | `a_look` (side, seed, drawn_m, kind) must exist, alternate sides, keep its id along the strip, match the kind of the particle and the length it fades along | `merged.look` |

## 7. Controls and results

Run (both modes, real output):

```
$ python3 -I kit/tests/test_hepevent.py
optimized=False: 206 negative controls caught with the intended code, 17 positive controls pass, 2 CLI controls
optimized=True: 206 negative controls caught with the intended code, 17 positive controls pass, 2 CLI controls
```

Each negative control names the code it must raise and a distinctive phrase of the diagnostic it must carry (`WRONG_DIAGNOSTIC` and `WRONG_REASON` are test failures, a surviving negative is `SURVIVING_CONTROL`). Negatives by code: EVT_PARSE 48, EVT_SCENE_BIJECTION 46, EVT_SHADER 38, EVT_SPEC 36, EVT_CONTAINMENT 12, EVT_CURVATURE 10, EVT_UNITS 8, EVT_CHARGE 3, EVT_4MOM 3, EVT_SENSE 2. 51 of them came from the review (section 6c); every control that existed before v2 also names a phrase of its reason.

Positive controls (17): exact Z to mu mu with its scene and the inventory read back; toy shower of 40 with loopers; toy shower of 400 (scale); scene in millimetres under `Transform scale 0.001` (the reader applies transforms); a track inside a Switch that selects it; event alone with a spec lacking a scene section (reports `scene: None`); declared radius 10 percent off (inside 15 percent); a particle born 2 m from the axis owes no track (finding 6); forward tracks whose bend is below the rounding are passed as unresolved and the pass counts them (finding 7); builder shader hygiene; look v2: exact Z to mu mu with both muons extended, toy shower of 40, toy shower of 400, two builds byte-identical; a Switch whose first child is metadata selects the tracks with whichChoice 0; a looping muon that never leaves the tracker is drawn with no extension.

CLI controls (2): `loom hepevent` writes `status pass` on the clean candidate and `status fail`, `EVT_SCENE_BIJECTION: event tracks not drawn: trk_1`, when a track is deleted from the scene.

Mutation pass (`kit/tests/mutate_hepevent.py`: disable one `need(...)` at a time and re-run the suite; last run `kit/tests/hepevent-mutation-last-run.json`): 161 `need` sites, 161 caught: 126 by a control failing its own assertion, 35 by the witness crashing further on because the gate was gone (the suite still fails, but law 19 counts only the first kind as a gate with its own control; the 35 are mostly parse-stage guards whose absence makes a later read throw). History: v2 (after review) added gates for the scene graph and the event binding, and one more survivor was removed as dead (a birth-time sign check that the birth window subsumes); the v0 pass caught 33 of 102 at first, and the controls were added until all 102 were caught; the look v2 extension added 25 sites, the first pass over them left 14 uncaught, and 13 new controls plus one dead gate removed (an extension on a track the bijection had already required) closed them. Limit: it mutates the raising predicates only, not thresholds or the arithmetic inside them.

Rehearsal on the committed fixtures (`kit/examples/run_hep_event.sh`, run in both modes; the second with `LOOM_PYFLAGS=-O` into a scratch directory). Real output of the last lines of the first run (JSON objects compacted onto one line each, absolute paths shortened to `.../`):

```
{
  "status": "accepted",
  "profile": "hep-demo/v2",
  "subject_sha256": "9685212a2e9367604eeccc06ce1fe8de9aa959354f67805d4021588f87e27542",
  "witnesses": [
    {"witness": "hep-event", "status": "pass", "grade": "C", "record_sha256": "71b4b89f655766aa70505f1bbb3c87f3648615998f0a721d6d1e09d410bb9579"},
    {"witness": "traps",     "status": "pass", "grade": "C", ...}
  ],
  "visible_not_run": ["grammar", "meaning", "behaviour", "look-match", "eyes", "real-gpu"]
}
{
  "receipt": ".../runs/hep-demo-v2-20261106/receipt.json",
  "sha256": "fb0ae36a15c55b39d682b6253d2e680235ecc7fe4fd103c640a87ec65e9c072a",
  "candidate_sha256": "9685212a2e9367604eeccc06ce1fe8de9aa959354f67805d4021588f87e27542",
  "evidence_files": 8
}
{ "receipt": "intact", "sha256": "fb0ae36a15c55b39d682b6253d2e680235ecc7fe4fd103c640a87ec65e9c072a" }
--- control: edit a scene after the witness ran -> STALE_WITNESS
{"rejected": "STALE_WITNESS", "detail": "hep-event"}
--- control: one track deleted from the hero scene -> EVT_SCENE_BIJECTION, acceptance rejects
{'status': 'fail', 'reason': 'EVT_SCENE_BIJECTION: event tracks not drawn: trk_7'}
{"rejected": "WITNESS_NOT_PASS", "detail": "hep-event: fail"}
--- control (look v2): one track's strip deleted from the merged hero set -> EVT_SCENE_BIJECTION, acceptance rejects
{'status': 'fail', 'reason': 'EVT_SCENE_BIJECTION: event tracks not drawn: trk_7'}
{"rejected": "WITNESS_NOT_PASS", "detail": "hep-event: fail"}
```

(The full record is `runs/hep-demo-v2-20261106/evidence/hep-event.json`, with coverage `{"events": 10, "scenes": 10, "towers": 1088, "tracks": 3598}`: each fixture counted once per look.)

What a pass reports it read (per fixture, from the witness record):

| Fixture | Particles | Final | Tracks | Charged | Hits | Towers | Scene KB | Scene points | Scene paths fitted / unresolved / 2-point | Hit sets unresolved | p4 residual (GeV, max) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| exact-zmumu | 3 | 2 | 2 | 2 | 16 | 2 | 105 | 8 | 2 / 0 / 0 | 0 | 0 |
| pythia-zmumu | 545 | 542 | 462 | 240 | 1018 | 124 | 668 | 5659 | 462 judged, 32 unresolved, 222 two-point | 2 | 1.2e-05 |
| pythia-qcd-demo | 609 | 607 | 497 | 235 | 917 | 132 | 684 | 5614 | 497 judged, 36 unresolved, 262 two-point | 3 | 1.6e-05 |
| pythia-qcd-inflight | 498 | 496 | 382 | 194 | 756 | 118 | 589 | 4772 | 382 judged, 31 unresolved, 188 two-point | 0 | 6e-06 |
| pythia-dijet-hero | 514 | 512 | 456 | 204 | 1100 | 168 | 568 | 3126 | 456 judged, 25 unresolved, 252 two-point | 1 | 4e-06 |

(Two-point paths are the neutrals, drawn as straight segments and checked against the straight rule. Witness time is 0.6 s for the first four; the look v1 numbers are shown.)

## 8. Findings from real generator output (Pythia 8.318, 300 events plus a pile-up stress)

The control was: convert Pythia events, run the witness, report what goes red. By law 26 every red was investigated as an instrument fault first. Bulk sets: 50 Z to mu mu, 200 QCD, 50 QCD with decays in flight, 3 events of 7 merged collisions (2344 to 3050 final-state particles).

| # | Finding | Cause | Fix | Where it lives now |
|---|---|---|---|---|
| 1 | Pythia's native status codes are not HepMC's (for example 21 to 29 hard process, 81 to 89 primary hadrons, 91 to 99 decay products; ranges quoted from memory) | the converter had to choose what the witness's `status` means | beams to 4, every `isFinal()` to 1, a Z/W/H/top/tau that really decays to 2; everything else dropped; native code kept as `gen_status`; mothers re-pointed to the nearest kept ancestor (at most 2) | `pythia_fixtures.py` docstring |
| 2 | Pythia gives hard-process incoming partons no mother | the beams point to them as daughters | converter restores the beam-to-parton link | `beam_of` |
| 3 | qcd-118 final state differs from the beams by -6.874 MeV in E and pz (next worst event: 0.128 MeV; median over 300: 8 microGeV, rounding) | Pythia itself printed "energy-momentum not quite conserved" for that event | none; the witness is right. The loose 0.5 GeV demo tolerance passes it by design; a precision spec at 1 MeV would fail it | spec `p4.abs_tol_gev` |
| 4 | 21 of 50 decays-in-flight events were `EVT_CURVATURE` ("drawn with 3 points (straight)") | **instrument fault**: the straight branch was `len(points) < 4`, but three points determine a circle | branch is now `< 3`; regression positive (3 hits on the right circle) and negative (3 collinear hits) controls | `hepevent._check_bend` |
| 5 | all 300 events were `EVT_SCENE_BIJECTION` for neutrals | **spec/converter mismatch**: the converter drew neutrals above one energy and the spec owed neutrals above another; a 0.98 fudge hid it | the converter now reads the drawing cuts from the spec file; the fudge is gone | `pythia_fixtures.py --spec` |
| 6 | decays in flight beyond the tracker: 329 of 22,785 final-state particles (1.44 percent) in the 50 in-flight events; 3 of the 50 events were red | the particle is born outside the volume the tracks live in, so no trajectory inside it exists to draw | optional particle `vertex_m`; a particle born outside the tracker owes no track (`_drawable`); positive control; negative control that a vertex outside the tracker is still `EVT_CONTAINMENT` | `_drawable`, `build_event` |
| 7 | after widening `draw_eta_max` from 2.5 to 10 (to draw "all" the visible particles) every one of the 303 events went `EVT_CURVATURE` | **instrument fault**, not physics. Stored points have 4 decimals (about 1e-4 m). A 47.6 GeV muon at eta 3.6 bends by 0.015 mm over its 70 mm of hits, and a track at eta 6.6 leaves the tracker after 8 mm of xy path and bends by 0.009 mm: the sagitta is 1 to 100 times smaller than the rounding, so the circle fit returned 0 to 1000 times the true curvature (measured; table below) | the spec gained `point_resolution_m` and `resolvable_sagitta_m`; below the resolvable sagitta the path is judged only as straight within the expected sagitta plus three rounding steps and **counted as unresolved**; above it the tolerance includes the curvature that rounding can fake (24 x resolution / extent squared) | `_check_bend`, regression controls |
| 8 | after that, 7 of 303 events were `EVT_SHADER`: `a_ident.pt 0.0035` versus event pT `0.003465` | **builder fault**: pT written to 4 decimals; forward neutrals have pT of a few MeV, so the rounding was 1 percent | the builder writes pT with 5 significant digits | `build_event_scene.sig` |
| 9 | final result | | all 303 pass: zmumu 50/50, qcd 200/200, in-flight 50/50, pile-up 3/3 | table below |

Measured fit quality (Kasa circle fit on the drawn points, 12 QCD events, 2,546 charged paths) against the expected sagitta over the path extent, in units of the point resolution:

| Expected sagitta / resolution | Paths | Fitted / expected curvature (min, median, max) | Judged as |
|---|---|---|---|
| below 0.1 | 67 | 0.00, 230, 1369 | unresolved |
| 0.1 to 0.3 | 58 | 0.00, 15, 297 | unresolved |
| 0.3 to 1 | 104 | 0.00, 1.6, 171 | unresolved |
| 1 to 3 | 125 | 0.66, 1.05, 1.47 | unresolved (the floor is 3, kept above the point where the fit is already usable) |
| 3 to 10 | 182 | 0.79, 1.00, 1.24 | fitted |
| 10 to 30 | 220 | 0.95, 1.00, 1.06 | fitted |
| 30 to 100 | 258 | 0.98, 1.00, 1.02 | fitted |
| above 100 | 1532 | 0.99, 1.00, 1.00 | fitted |

The resolvable floor (0.3 mm = 3 resolutions) sits a little above the point (about 1 resolution) where the fit stops being noise; with the 15 percent tolerance plus the rounding term it accepts every fitted path in the table.

Final bulk run with the shipped instrument and builder:

| Set | Events | Pass | Final-state particles | Drawn | Charged paths unresolved (scene) | Hit sets unresolved | Scene KB (min / median / max) | Witness s (max per event) |
|---|---|---|---|---|---|---|---|---|
| Z to mu mu | 50 | 50 | 18,896 | 15,899 | 1,306 of 7,769 | 37 of 5,288 | 146 / 432 / 926 | 0.32 |
| QCD | 200 | 200 | 91,656 | 77,711 | 5,517 of 37,399 | 260 of 26,425 | 222 / 554 / 1,075 | 0.38 |
| QCD, decays in flight | 50 | 50 | 22,785 | 18,729 | 1,382 of 9,431 | 51 of 6,710 | 228 / 559 / 1,058 | 0.37 |
| Pile-up stress (7 collisions) | 3 | 3 | 8,150 | 6,973 | 523 of 3,301 | 13 of 2,368 | 2,243 / 2,834 / 3,178 | 1.27 |

Why a final-state particle is not drawn (the other 14 to 18 percent of the table above; all by the declared cuts, never by accident):

| Reason | Z to mu mu | QCD | QCD in flight | Pile-up |
|---|---|---|---|---|
| neutral below 0.3 GeV | 1,973 | 9,034 | 2,373 | 738 |
| charged below 0.15 GeV pT | 998 | 4,776 | 1,327 | 419 |
| born outside the tracker (decay in flight) | 0 | 0 | 329 | 0 |
| neutrino | 11 | 82 | 13 | 11 |
| eta above 10 | 15 | 53 | 14 | 9 |
| anything else | 0 | 0 | 0 | 0 |

So "all 300 or 3000 particles" is true of the visible, above-threshold ones: 84.1 percent of the final state is drawn for Z to mu mu, 84.8 for QCD, 82.2 with decays in flight, 85.6 for the pile-up stress. The rest is soft or invisible by the cuts above, and the witness checks that exactly those, and no others, are missing.

## 9. Limits (read these before relying on a pass)

| Limit | Consequence |
|---|---|
| The witness renders nothing and compiles nothing | inside the acceptance the GLSL is checked lexically only (no `#`, `%`, quote, `//`, `active`, int literal; balanced brackets). X_ITE 16.5.1 stills of the same look v2 scenes, 0 shader or console errors under software GL, are recorded beside the receipt (`runs/hep-demo-v2-20261106/frames/`), not inside it; behaviour, look-match and eyes stay visibly not run |
| `<component name='Shaders' level='3'/>` | the level was taken from memory (grade L); the grammar and meaning witnesses (X3D fork) were not run |
| WebGL draws lines one pixel wide (look v1) | look v1's filaments are 1 px; look v2 draws screen-space ribbons instead |
| no backdrop | look v2 has a faint shader haze; the reference's lit machinery backdrop is not built |
| truth-level response | tracks, hits and towers are placed from the generator's particles: no smearing, no energy loss, no showers; muons deposit a fixed 0.8 GeV; the calorimeter is a barrel only |
| plausibility physics | momentum balance is 0.5 GeV loose; no mass shell, no resonance peak, no calorimeter sum rule; qcd-118's 6.9 MeV residual passes by design |
| unresolved bends | 15 to 17 percent of the charged tracks in the real events (mostly very forward ones, whose xy path in the tracker is millimetres long) draw a bend below the rounding of their coordinates. They are checked only as straight lines within the expected sagitta, and the sense is not checked. The pass says how many |
| sense floor | the sense is checked only when the expected sagitta exceeds 2 mm, so a central track above about 70 GeV is not sense-checked |
| two-point rule | a two-point path is a straight segment; it is accepted if the expected sagitta over its chord is at most 2 mm |
| direction is checked at the start only | since v2 the first drawn segment must point along the track's phi and dip along its eta, and the path must reach its helix's extent; a path that starts right and then wanders inside the tolerance of the bend fit is still judged by curvature only |
| slow motion | the head advances at 0.9 m/s; the scene says so in a meta tag; towers light by that same speed, so the arrival order is right and the magnitudes are not |
| tower arrival is not cross-checked against the tracks | `a_tower.arrival` is data in the scene; the witness requires the shader to be bound, not that the arrival times are consistent |
| mutation pass | deletes `need` calls only; thresholds and the arithmetic inside predicates are covered by controls, not by mutation |
| mixed generators | the only non-stdlib script is `pythia_fixtures.py`; it needs `pythia8mc` and is not run by the tests (the committed fixtures are its output) |
| unsigned receipt | the receipt shows drift; it does not authenticate authorship |
| the repository's other docs sit at the repository root | this file is under `docs/` as asked; move it beside `X3D-STEM.md` if the layout should match |

## 10. Reproduce

```
# fixtures (needs pythia8mc; the committed fixtures are already the output)
python kit/examples/hep/pythia_fixtures.py OUT/zmumu --process zmumu --events 50 --seed 11
python kit/examples/hep/pythia_fixtures.py OUT/qcd --process qcd --events 200 --seed 22
python kit/examples/hep/pythia_fixtures.py OUT/qcd-inflight --process qcd --events 50 --seed 22 --decays-in-flight
python kit/examples/hep/pythia_fixtures.py OUT/stress --process qcd --events 3 --pileup 7
python3 -I kit/examples/hep/select_fixtures.py OUT kit/examples/hep/fixtures

# one scene, then the witness on it
python3 -I kit/examples/hep/build_event_scene.py kit/examples/hep/fixtures/pythia-qcd-demo.event.json /tmp/hero
kit/loom hepevent /tmp/hero --evidence /tmp/hero-ev --events '*.event.json' --spec kit/examples/hep/hep-demo-spec.json

# negative control: delete one track and the witness fails with EVT_SCENE_BIJECTION
# (done by kit/examples/run_hep_event.sh against trk_7 of the hero scene)

# everything
python3 -I kit/tests/test_hepevent.py            # both modes
kit/examples/run_hep_event.sh                    # candidate, witnesses, acceptance, receipt, controls
LOOM_PYFLAGS=-O kit/examples/run_hep_event.sh /tmp/hep-run-O
```

## 11. Fold-back

| File | New or changed |
|---|---|
| `kit/loomkit/hepevent.py` | new: the witness (stdlib only) |
| `kit/loomkit/cli.py` | changed, additive: `hepevent` import, `cmd_hepevent`, subparser, dispatch entry, docstring line |
| `kit/profiles/hep-demo.json` | new: acceptance profile `hep-demo/v2` (v1 was the first push of the PR) |
| `kit/tests/test_hepevent.py`, `kit/tests/hepevent-last-run.json`, `kit/tests/mutate_hepevent.py`, `kit/tests/hepevent-mutation-last-run.json` | new |
| `kit/examples/hep/render/`, `kit/examples/hep/feas/` | new: stills harness, feasibility harness (X_ITE itself is fetched, not committed) |
| `COLLIDER.md`, `docs/COLLIDER-XITE-FEASIBILITY.md`, `docs/COLLIDER-SURVEY.md`, `runs/hep-demo-20261106/frames-v2/`, `runs/hep-demo-v2-20261106/frames/` | new: the demo's entry point, the X_ITE measurements, the survey, first light, the frames after review |
| `kit/examples/run_hep_event.sh` | new |
| `kit/examples/hep/` : `hep-demo-spec.json`, `hep_response.py`, `exact_events.py`, `build_event_scene.py`, `pythia_fixtures.py`, `select_fixtures.py`, `fixtures/` (5 files) | new |
| `docs/HEP-EVENT-WITNESS.md` | new (this file) |
| `runs/hep-demo-20261106/` | new: the v1 rehearsal (8 events), kept as history |
| `runs/hep-demo-v2-20261106/` | new: the v2 rehearsal's evidence, receipt and candidate (regenerate with the script) |
| `kit/loomkit/receipt.py`, `kit/tests/test_gates.py` | changed: receipt output keys stay unique when two outputs share a basename (`RECEIPT_OUTPUTS` for a file listed twice), with two controls |
