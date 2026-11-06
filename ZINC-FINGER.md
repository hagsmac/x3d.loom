# Zinc fingers under the Loom

A Loom v1.0 plan for an x3d.STEM study of zinc finger proteins in motion, with its first instruments and its first real data. Started 6 November 2026.

- **Status:** P0 (instrument) and P1 (deposited structures and their Site scenes) are done, on CPU at no cost. No protein has been simulated.
- **What runs today:**
  - the metal-site witness (`kit/loomkit/metalsite.py`) and its tests;
  - a rehearsal receipt over synthetic sites (`runs/zinc-site-20261106/`);
  - 14 deposited structures with a receipt, an independent second reader and a census of all 32 zinc sites (`runs/zinc-structures-20261106/`);
  - 14 Site scenes in X3D with a receipt and a data-true check (`runs/zinc-scenes-20261106/`).
- **Grades** follow law 5: **C** measured here with a record, **L** read in the literature, **S** a reading or a model's output.

## 1. Findings

### F1. A beautiful reference animation fails Truth on five counts

The starting point was a 15 s animation of zinc fingers on DNA (1280 × 720, 24 fps, sha256 `58347831…b1bf3f5`; C, ffprobe). It is a strong style reference and a poor science reference. The animation itself is not in this repository.

| What it shows | What is true | Grade |
|---|---|---|
| Zinc fingers drawn as literal white fingers gripping the helix | A zinc finger is a small fold of about 30 amino acids; the classic Cys2His2 type is two short strands and a helix. The name comes from the finger-like loop in the first drawings | L |
| A silver zinc held by four identical gold ligands | Four-coordinate, roughly tetrahedral zinc is right, but the ligands depend on the class: Cys2His2 is two sulfurs and two nitrogens; a CCCH finger is three sulfurs and one nitrogen | L |
| Fingers wrap double-stranded DNA from the outside | Classic fingers set their helix into the major groove, about three base pairs per finger. The CCCH tandem fingers of the tristetraprolin family bind single-stranded RNA, not DNA | L |
| Red-blood-cell discs drift beside the DNA | Mature mammalian red cells have no nucleus and no DNA, and a cell (about 7 µm) is roughly 3,500 times wider than the helix (2 nm) | L |
| Glowing spheres, floating small molecules, a starfield | Nothing they stand for is named; the inside of a cell is crowded water, not open space | S |

The study keeps the look (deep blacks, depth of field, a cool palette, a bright metal centre) and replaces the content with coordinates from a structure or a simulation. Law 2 in a new field: beautiful is not the same as true, and a witness can say exactly where it isn't.

### F2. The simulation stack runs here, and the structures arrive through the archive's public snapshot

- An open-source molecular dynamics engine (OpenMM 8.6.1) and an analysis library (MDAnalysis 2.11.0) install and pass their own self-tests on CPU in the agent's machine (C).
- The protein structure archives' own sites refused the connection from that machine (C). The wwPDB's public snapshot of 1 January 2026 (`pdbsnapshots`, divided PDB format) is reachable, and every structure in P1 came from it (C).
- Each file is pinned by sha256 in `kit/examples/zinc_structures.py`, read as fetched (`.ent.gz`), and a from-scratch rebuild in another folder gave the same candidate hash and the same census (C).

### F3. The metal-site witness

`kit/loom metalsite ROOT --evidence EV --files 'structures/*.pdb' --spec SPEC.json` checks every declared zinc site in every file and every MODEL frame. The spec must be a file inside the candidate, so the candidate hash covers its thresholds. It fails closed (law 18) with one stable code per cause:

| Code | Catches | Why it matters for zinc |
|---|---|---|
| `SITE_COORDINATION` | The number of ligand atoms within the search radius differs from the declared number. Ligands are found by element (N, O, S, Se, halogens), whatever the residue or atom is called, and the message names any the donor table does not | The zinc is losing a ligand, or something has joined it (a water, a backbone oxygen, a chloride) |
| `SITE_CLASS` | Protein ligands in sequence order differ from the declared class (for example CCCH declared, CCHH found); a protein ligand that is not a side-chain donor enters as `x` | A parameter set built for one class used on another |
| `SITE_LIGANDS` | The ligand residues differ from an optional declared list (for example His33 in place of His29) | A neighbour takes over the site with the class unchanged |
| `SITE_DONOR` | A histidine binds through ND1 when NE2 was declared, or the reverse | A site built for the other nitrogen. The protonation itself (HID, HIE, HIP) is not checked: a histidine whose proton sits on the binding nitrogen still passes |
| `SITE_DISTANCE` | A metal–ligand distance leaves its window (defaults Zn–S 2.20–2.45 Å, Zn–N 1.95–2.20 Å, Zn–O 1.90–2.30 Å; typical values, L) | A stretched or crushed site that still counts as four-coordinate |
| `SITE_GEOMETRY` | The four-coordinate geometry index tau4 falls below the declared floor (0 is square planar); a floor on any other coordination is refused | A distorted site |
| `SITE_INTACT_FRACTION` | The site is intact in fewer frames than declared; the first failing frame and its cause are reported | The zinc escapes partway through a trajectory |
| `SITE_UNITS` | The median nearest-neighbour distance is below 0.5 (bonded atoms sit about 1.1 Å apart with hydrogens, 1.4 Å without) | Nanometres read as ångström: a scene ten times too small validates |
| `SITE_NO_METAL`, `SITE_PARSE`, `SITE_SPEC` | The declared metal is missing; the file cannot be read as one consistent set of frames (atoms outside a MODEL, frames joined only by END, atoms in a different order between frames); the spec is malformed (a search radius outside 2.5–3.5 Å, a lower-case donor key, empty windows, two entries selecting the same zinc) | Rejected fail-closed and recorded as fail; never a pass (law 19). An instrument crash is recorded as error |

Even inside 2.5–3.5 Å, the unbound oxygen of a one-armed aspartate or glutamate can sit near 3 Å and be counted, so sites with those ligands need a smaller radius. A pass names what it read (law 36): atoms, frames, every metal atom in the file and which of them the spec did not select, and alternate-location atoms skipped.

**Tests** (`python3 -I kit/tests/test_metalsite.py`, both normal and `-O`, report in `kit/tests/metalsite-last-run.json`; C):

- 25 negative controls rejected with their intended code;
- 10 positive controls pass, including the window edge (2.44 Å passes, 2.46 Å fails), a 20-frame trajectory, a gzip archive file, a CHARMM-named histidine (HSD) and a hexadecimal residue number;
- 3 CLI controls: the witness record says pass on a clean site and fail on a drifted one, and a spec outside the candidate is refused;
- reference values for tau4: an ideal tetrahedron reads 1.000408 and a square plane 0. The published index divides by 141°, which is 360° − 2 × 109.5°, while the tetrahedral angle is 109.47°, so 141.06 / 141 = 1.0004. Rounding is not the cause: exact coordinates give the same value. The formula is kept as published.

**Rehearsal receipt** (`kit/examples/run_zinc_site.sh`, profile `kit/profiles/zinc-site.json`; receipt `1c27ec0f099d`; C):

- The synthetic candidate (one static CCCH site and a 20-frame jittered copy) is accepted under `zinc-site/v0`, and the receipt verifies.
- Eight witnesses stay visibly not run, with reasons.
- Controls: an edit after the witness ran rejects with `STALE_WITNESS`; a candidate whose zinc has lost a cysteine fails the witness and acceptance rejects with `WITNESS_NOT_PASS`.

### F4. Two red results while building, both in the instrument's own code (law 26)

1. **A control expected the wrong code.** The drifted-candidate control expected `SITE_COORDINATION`. The witness answered `SITE_INTACT_FRACTION`, because the trajectory file sorts before the single-frame file, and a lost ligand in a trajectory is an intact-fraction failure whose first cause is `SITE_COORDINATION`. The witness was right. The control now asserts both the code and the first cause.
2. **A positive control caught a crash.** Making the intact-fraction message more readable built it eagerly, so it indexed an empty failure list on every intact trajectory. The 20-frame positive control failed at once. The message is now built only when there is a failure.

### F5. Fourteen deposited structures: five pass as deposited, nine stay red with their reasons

P1 ran the metal-site witness on every model of 14 deposited structures (32 zinc sites: Cys2His2 fingers on DNA, CCCH tandem fingers with and without RNA, RanBP2-type CCCC fingers, a CCHC finger, the PARP1 fingers, and three cryo-EM models of the CPSF30 fingers on the AAUAAA signal). The windows were declared before the run and were not widened after it (law 28). Receipt `0133b9e75d9e` over candidate `7e9e184ffabf`, profile `zinc-structures/v0` (C).

- **Pass as deposited, in every model:** 1UBD (YY1, four sites), 1RGO (TIS11d, both CCCH sites in all 20 NMR models: Zn–S 2.280–2.301 Å, Zn–N 2.073–2.086 Å), 1M9O, 2K1P and 3G9Y. These five can start a simulation without repairing the zinc site.
- **Small misses, kept red:** 1N0Z (one model of 20 has Cys33 SG at 2.193 Å, 0.007 Å short), 1AAY (Zif268: His129 NE2 at 1.940 Å, 0.010 Å short, and a Zn–S of 2.154 Å at site A203).
- **Outliers:** 1ZAA (the first Zif268 structure, 1991: Zn–N 1.876 Å, Zn–S 2.154 Å), 4AV1 (3.1 Å resolution: every one of its four sites has a Zn–S below 2.20 Å, down to 2.076 Å, and one Zn–N is 1.912 Å), 6NZL (every Zn–S between 1.915 and 2.112 Å in all 20 models, a compressed NMR geometry).
- **A fifth ligand in 2JVX (NEMO):** in 2 of its 10 NMR models the C-terminal Glu28 backbone oxygen joins the zinc (Zn–O 2.07 and 2.14 Å; in one model OXT too), giving five and six ligands. The first version of the witness could not see it (F8).
- **The cryo-EM CPSF30 sites need rebuilding before any simulation:** 6FUW, 6DNH and 6URO carry Zn–S up to 2.994 Å; 6DNH C302 has two ligands within 3.0 Å and C303 three; all three 6URO sites have three.
- **An independent reader agrees with all 14 records** (law 25): MDAnalysis parses the same files and recomputes every distance, finding ligands by element, not by the witness's table. It compared 63 values across 177 site-frames, and a record moved by 0.01 Å is caught (C). Shared with the witness, and stated: the search radius, the metal identity and the side-chain donor names used to spell the class.
- **The full census** (every site, every model, nothing stops at the first red) is generated, not retyped: [`runs/zinc-structures-20261106/census.md`](runs/zinc-structures-20261106/census.md).

### F6. Two set-up rules the deposited files give a simulation

- **Histidine tautomer, per site** (C): every histidine in the set binds zinc through NE2 (protonate as HID), except PARP1 in 4AV1, where His53 and His159 bind through ND1 at all four sites (protonate as HIE). A set-up that applies one rule to every histidine builds the PARP1 site wrong. OpenMM's Modeller is not metal-aware, so the tautomer is set by hand from this census.
- **Which starting structures are usable as-is** (C): the five in F5. The CPSF30 cryo-EM models need their zinc sites rebuilt and checked by the same witness first.

### F7. Fourteen Site scenes, data-true, read in a browser

`kit/examples/run_zinc_scenes.sh` builds one X3D world per structure from model 1 by a stated rule (`kit/examples/zinc_site_scene.py`): every atom a Transform named after its PDB atom at its deposited coordinate; the zinc, every ligand atom, and each named side-chain donor's side chain; a bond to each ligand that **glows only while it measures under 2.5 Å** and is labelled with its length. The 2.5 Å line is a display rule, not the witness window: a bond can glow and still fail the witness (Zn–S 2.461 Å in 6FUW). Receipt `2674de4d55a0` over candidate `979dec13377e`, profile `zinc-scenes/v0` (C):

- **Grammar and meaning:** 14 of 14 valid, 0 errors and 0 warnings, at the family validator pin (x3d_mcp fork 327c5c4).
- **Traps:** pass, and the record says what the rules judged (1,218 colour fields, 781 Materials; no ROUTE or shader, so those rules judged nothing).
- **Data-true** (`kit/examples/zinc_scene_truth.py`, an independent reader: ElementTree and MDAnalysis, no import of the builder): all 554 atoms at their coordinates, exactly the atoms the rule selects, all 122 zinc bonds ending on their two atoms, glowing exactly when under 2.5 Å, labelled with the recomputed length and placed on their own bond's line, and every tube control point a deposited Cα or P. Nine one-line edits are each caught with their own code (an atom moved 0.01 Å, an atom dropped, an atom added, a short bond drawn dark, a label off by 0.01, two labels swapped, a bond turned off its atoms, a bond removed, a tube point moved).
- **Eyes** (S, a model reading of 32 frames: X_ITE 16.7.0 in headless Chromium on SwiftShader, 960 × 720, each scene Viewpoint bound through SAI): every frame draws its site and none is blank; the long cryo-EM bonds draw dark and thin; 6DNH C302 shows its two ligands. X_ITE 16.6.0 under the same rig gives byte-identical frames (C).
- **The reading found three faults, fixed one cause at a time (law 29):** labels at the bond midpoints piled onto the zinc, so they moved onto each bond's line 1 Å past the donor; a fixed camera let the backbone tube cover the site, so each Viewpoint is now chosen by a declared rule (`choose_view`: the direction, out of 600, where the fewest drawn things cover the zinc, its ligands and labels, and the labels crowd least); that rule's first version projected flat and ignored anything near the lens, so a DNA tube filled two frames, and it now scores in perspective. Left as found: neighbouring sites crowd the background of 1ZAA C201 and 6DNH C301.

### F8. A review round found the witness blind to any ligand its table did not name

An adversarial review of P0 (each finding retried by a second reviewer told to refute it) confirmed these defects in the first version of the witness, all fixed above with a control each:

- ligands were found by name, so a fifth ligand named any other way (a GROMACS `SOL` water, a backbone oxygen, a chloride) passed as a clean four-coordinate site, and a CHARMM `HSD` histidine was a false red. **This happens in deposited data:** 2JVX (F5);
- atoms before the first MODEL were dropped without a word; frames joined only by END were misread as nanometres; atoms in a different order between frames made the witness measure the wrong zinc;
- a lower-case donor key silently skipped its rule; empty windows fell back to the defaults while the record said they were declared; a tau4 floor on a five-coordinate site was ignored; the spec could sit outside the candidate.

Run against the first version, 8 of the 10 new negative controls pass silently and the other 2 fail for the wrong reason (C). The same review found a bug in the public kit's own `kit/loom traps`: it raised `NameError` on every run (it referred to a variable from the page-traps command), and the tests never ran the command itself. Public snapshot 4 fixed it upstream and added CLI controls that drive the command end to end; this branch takes that fix and drops its own, so the scenes traps witness was run again on the upstream instrument and the scenes receipt re-issued.

### F9. A second model's re-render: the data held, the look improved, the provenance did not

Another model returned a single-file three.js re-render of the private Site Atlas, built from our 14 receipted X3D scenes. Three audits and a skeptic per audit found the following (C unless marked):

- **The data held.** All 554 atoms sit at 0.000 Å from our scenes and PDB model 1. All 122 distances and the under-2.5 Å glow rule are exact.
- **The look is genuinely better** (S for the look itself): physically based materials, tone mapping, darker opaque tubes, donor-naming label cards, a coordination cage, and a file that stands alone (law 37).
- **It also introduced new faults:**
  - zinc drawn with carbon's material (an "Zn" versus "ZN" key);
  - a provenance line naming X_ITE as its viewer;
  - a superseded receipt cited;
  - a self-graded "[ C ]";
  - 4K stills that drop the red verdict;
  - a cage drawn over two dark contacts.
- **It exposed three faults of ours, now fixed:**
  - a re-issued receipt with no back-link (now chained: scenes receipt 2674de4d55a0 points back to fc37e514b2a7);
  - a lost output entry in that receipt;
  - our witness misquoting law 21.

The full record, the fold-back list and the proposed law are in [runs/zinc-remix-review-20261106/REVIEW.md](runs/zinc-remix-review-20261106/REVIEW.md).

### F10. Look v2: the remix's gains folded back into the generator, and checked

The question asked of F9 was whether the remix's zinc bug explains why its look still felt flat. **Partly.** The zinc took the carbon slate because the material table was keyed "ZN" and the data said "Zn". Patching that key in the remix makes the zinc chrome, but the frame stays flat (S, two frames read side by side). The larger causes were elsewhere: nothing to reflect (a metal with no environment renders near black), no tone curve, and labels buried inside the atoms.

`kit/examples/zinc_site_scene_v2.py` builds the same geometry as v1 (it calls v1's builder, so it repeats no rules) and changes only the look. Each item is declared as look, not data (law 34):

- **Format:** X3D 4.1.
- **Materials:** PhysicalMaterial per element, with zinc a metal (metallic 0.85, roughness 0.18).
- **Light:** an EnvironmentLight over a generated studio cube map (`zinc_studio_env.py`, 32 px faces so software GL can render it), plus key, fill and rim lights placed in the first site's camera frame. The headlight is off.
- **Tubes:** thicker, dark and glossy, with caps.
- **Labels:** each label moves 1.2 Å toward the eye inside its Billboard, so its anchor on the bond line stays where the data puts it. Each label gains a donor name ("CYS 159 SG") and a backing card.
- **Cage:** a translucent tetrahedron joins the four donors only where all four bonds glow. The remix drew one over two dark contacts.
- **Viewer:** the renderer (`zinc_render_v2.cjs`) sets X_ITE's KHR_PBR_NEUTRAL tone mapping and records it in the rig.

The new parts that carry data are checked. `zinc_scene_truth_v2.py` keeps every v1 check and adds three:

- **ATOM_COLOUR:** every atom draws its own element's shape (zinc as zinc), and the element colours are pairwise distinct.
- **CAGE:** a cage appears exactly where it is due, and its face and edge vertices are the donors to 3 decimals.
- **DONOR_NAME:** every name line reads its donor as deposited.

Fifteen negative controls (nine from v1, six new) are each caught with their own code. The first of the new controls is the remix's own bug: a zinc drawn with carbon's material.

The run `runs/zinc-scenes-v2-20261106` (C) passes on all 14 scenes and 32 sites:

- grammar (14 of 14 valid against the X3D 4.1 XSD, fork pin);
- meaning;
- traps;
- data-true v2: 25 cages on 32 sites and 122 donor names;
- 15 of 15 controls.

The eyes record (S) reads all 32 frames: every zinc reads as metal, every label sits in front and names its donor, and the long cryo-EM sites draw dark with no cage. The receipt is bb6c79667bc9, under the profile `kit/profiles/zinc-scenes-v2.json`; it points back to 1922186dac97, issued before the eyes record. The v1 run is untouched.

## 2. The study card

The template is `kit/templates/SCIENCE-STUDY-CARD.md`. Empty fields are decisions not yet made.

### 1. Question and audience
- **The one sentence:** a zinc finger is a small protein fold held together by one zinc ion, and which four atoms hold that zinc decides whether the finger keeps its shape and what it can grip.
- **Explorer:** the site, with bonds that glow only while their measured length is short, and the length printed on each.
- **Lab:** tables of intact fraction, RMSD, contacts and per-residue flexibility, each with its run.
- **Instrument:** the witnesses, receipts and the red runs kept.
- **Theatre:** a film rendered in Blender from the same trajectory as the page.

### 2. Model
- **Equations and units:** classical molecular dynamics with a fixed-charge protein and nucleic-acid force field, explicit water, particle-mesh Ewald electrostatics, 300 K and 1 bar. Files are in ångström; the engine works in nanometres.
- **Zinc:** bonded (a parameterised site) for structure and contact questions. Nonbonded (a 12-6-4 ion model) only for questions about metal exchange. The model is named on every number.
- **Method:** Verlet integration with hydrogen constraints, 2 fs; 4 fs only with hydrogen-mass repartitioning. OpenMM's `VerletIntegrator` is the leapfrog form; both forms are second order, so the expected error in the total energy is order 2 in the timestep.
- **Stated limits:**
  - no bond can form or break, so a chemical modification of a ligand is modelled as before and after states, with the reaction itself left to quantum chemistry on a small cluster;
  - hundreds of nanoseconds, not RNA binding kinetics;
  - a bonded zinc can never leave and a nonbonded zinc can leave for the wrong reason.

### 3. Exact references
| Reference | Closed form or exact identity | Where it is computed | Declared limit |
|---|---|---|---|
| Ideal tetrahedron and square plane | tau4 = (360 − 2 × 109.47)/141 = 1.000408 and 0 exactly | `kit/tests/test_metalsite.py` | 1e-5 |
| Units round trip | nm × 10 = Å; a structure written and re-read reproduces its coordinates | Set-up step (P2) | 0.001 Å |
| Deposited structure | Frame 0 reproduces the deposited site distances | Metal-site witness on the prepared system (P2) | 0.001 Å |
| Energy error against the timestep | Verlet (leapfrog or velocity form): halving dt cuts the RMS fluctuation of the total energy by about 4 | Short constant-energy runs at 2, 1 and 0.5 fs, and 4 fs with repartitioning (P2) | observed order 2 ± 0.1, to confirm in P2: constraint and Ewald tolerances can bend it |

### 4. Claims the captions will make
| Word or number in a caption | Measured how | Threshold (declared now) |
|---|---|---|
| "zinc held" | Metal-site intact fraction | ≥ 0.99 of frames, windows as in F3 |
| "the finger keeps its fold" | Backbone RMSD to the experimental structure after equilibration, per finger | < 2 Å in ≥ 90 % of frames; never claimed for a finger the experiment finds disordered (§5) |
| "contact" | Heavy-atom distance between protein and RNA or DNA | < 4.0 Å in ≥ 50 % of frames |
| "flexible" | Per-residue RMSF, colour bar in Å | fixed transfer range 0–3 Å, clipping counted |
| "binds tighter" or "weaker" | Not from simulation alone | needs the Experiment witness (law 10) |

### 5. Exploration (before declaring limits)
- **Easy case:** the synthetic ideal sites (F3), then the five structures that pass as deposited (F5).
- **Published precedent** (L, read in the papers):
  - an earlier MD study of TIS11d free and bound to RNA (from 1RGO) found that a fixed-charge nonbonded zinc did not keep tetrahedral geometry. That is the failure `SITE_COORDINATION` and `SITE_GEOMETRY` exist to catch;
  - with a polarizable charge-transfer zinc model, a homology model of free human TTP lost the zinc at its second finger in 1 of 3 100-ns runs, after the ligand histidine turned to a rotamer that cannot bind zinc. The authors read this as agreeing with experiment, not as a model failure: free TTP holds zinc stably only in its first finger. There, a `SITE_INTACT_FRACTION` failure may be the right answer, so the second finger of free TTP never gets a "zinc held" caption.
- **A measured fact the Fold witness must respect** (L): by NMR, the second finger of free human TTP is molten-globule-like and folds only on RNA, while both fingers of its relative TIS11d fold without RNA. A run that folds free TTP's second finger is a red result, however stable it looks.
- **Worst cases named, not yet run:** a nonbonded zinc with a neutral cysteine (expected to lose the zinc: the negative control for the whole simulation chain); the spread across the models of an NMR ensemble (measured for the deposited files in the census); a metal swap to another first-row transition metal, where a bonded site would have to be built and checked here.

### 6. Witnesses
| Witness | Pattern | Limit | Negative control that must fail |
|---|---|---|---|
| Metal-site (runs today) | A, E | windows, coordination by element, class, ligand residues, donor, tau4, intact fraction | the 25 controls in F3 |
| Second reader (runs today) | E | agrees with every metal-site record to 0.0011 Å | a record moved by 0.01 Å |
| Fold | D | RMSD and secondary structure per finger | a run from a scrambled or unfolded start |
| Repeat | B, H | three or more seeds agree within block-averaged error | a single run quoted alone |
| Energy error | A, B | observed order 2 ± 0.1; drift per ns declared | a 4 fs step without repartitioning |
| Units | I | the gross check in F3, then the exact round trip | coordinates divided by 10 (`SITE_UNITS`) |
| Data-true (runs today, for static scenes) | G | every atom, bond, glow, label and tube traced to the coordinates (F7); for trajectories, the page recomputes zinc–ligand distances from its own frames and matches the analysis to 0.002 Å | the nine edits in F7 |
| Experiment | D | contacts present in the deposited structure are kept | a contact list from the wrong structure |

### 7. Display chain
- **Encoding:** coordinates in Å with three decimals: at most 0.0005 Å on each coordinate, so up to √3 × 0.001 = 0.0017 Å on a distance. The quantization witness is the change in each zinc–ligand distance between analysis and scene.
- **Glow rule:** a bond to zinc glows only while its measured length is under 2.5 Å. It is a display line, not the witness window, and the label always prints the length.
- **Transfer ranges:** fixed and declared; clipped values counted.
- **Recomputed in the browser:** atom counts exactly; zinc–ligand distances to 0.002 Å.

### 8. Page contract (law 32)
The static Site scenes exist (F7); the trajectory page is not built yet. It will follow the playbook skeleton:
- trajectory frames verified by sha256 before use;
- playback through `TimeSensor → IntegerSequencer → Switch`, never blending frames; a `CoordinateInterpolator` may hold the frames only if its fraction is stepped to key values, so no in-between pose is drawn; started with `getCurrentTime()`;
- guarded callbacks;
- page traps given every file that runs page code.

### 9. Acceptance
- **Now:** `zinc-site/v0` (the rehearsal), `zinc-structures/v0` (the five deposited structures that pass, plus the second reader; the full set is a control that must reject) and `zinc-scenes/v0` (grammar, meaning, traps, data-true; eyes visible and graded S).
- **Next:** `zinc-finger-md/v0` adds simulation, fold, repeat, energy error, grammar, meaning, traps, page traps and behaviour.
- **Visibly not run until it exists:** paired visual review, and Experiment, which needs measured binding data.

## 3. Phases

| Phase | What | Done when | Compute |
|---|---|---|---|
| P0 | Instrument: metal-site witness, tests, rehearsal receipt | done 6 Nov, revised after the review round (F8) | CPU |
| P1 | Real structures in: 14 deposited structures, the metal-site witness on every model, a second reader, the census, and the Site scenes | done 6 Nov: every site passes or its failure is explained (F5 to F7) | CPU |
| P2 | Short runs of one finger from a structure that passes as deposited: the energy-error order, the units round trip, and the worst case (the nonbonded zinc that should escape) | the worst case fails for the intended reason | CPU |
| P3 | Production runs, three seeds per system, bonded zinc | fold, site and repeat witnesses pass | GPU, needs the operator's yes |
| P4 | Metal swaps and cysteine modifications as before and after states; any reaction itself on a small quantum cluster | each comparison names its model and grade | GPU or CPU, needs the operator's yes |
| P5 | X3D scenes from one generator (Site done; Complex, Compare) and the page | grammar, meaning, traps, page traps, behaviour | CPU |
| P6 | The film in Blender from the same trajectory | the operator's eye, paired with the page | GPU |

Each phase stops and shows its pictures before the next starts, because the biggest risk is a convincing wrong picture, not a crash.

## 4. Fold back

This repository is a public snapshot of a private working repository, and the next snapshot replaces it. Before that, fold these files into the private repository, or the next snapshot will drop them (law 20):

- `kit/loomkit/metalsite.py`; the `metalsite` subcommand in `kit/loomkit/cli.py`;
- `kit/tests/test_metalsite.py`, the traps CLI controls in `kit/tests/test_gates.py`;
- `kit/profiles/zinc-site.json`, `zinc-structures.json`, `zinc-structures-full.json`, `zinc-scenes.json`, `zinc-scenes-v2.json`;
- `kit/examples/`: `zinc_site_fixtures.py`, `run_zinc_site.sh`, `zinc_structures.py`, `zinc_cross_check.py`, `zinc_census.py`, `run_zinc_structures.sh`, `zinc_site_scene.py`, `zinc_scene_truth.py`, `zinc_scene_truth_controls.py`, `zinc_render.cjs`, `run_zinc_scenes.sh`, and for look v2 `zinc_site_scene_v2.py`, `zinc_studio_env.py`, `zinc_scene_truth_v2.py`, `zinc_scene_truth_v2_controls.py`, `zinc_render_v2.cjs`, `run_zinc_scenes_v2.sh`;
- `runs/zinc-site-20261106/`, `runs/zinc-structures-20261106/`, `runs/zinc-scenes-20261106/`, `runs/zinc-scenes-v2-20261106/`, `runs/zinc-remix-review-20261106/`, this page and its README row.
