# The X3D Loom, version 1.0

**v1.0, 5 November 2026.** Laws 26 to 35 and failure modes 64 to 92 come from building six x3d.STEM flagships under the Loom and from the loom4 delivery (the X_ITE repository teardown and the Tether assessment). Law 36, the Authored label and failure modes 93 to 101 come from checking the Mashtots2 delivery (two standalones, 5 Nov) under the Loom; law 37 and failure modes 102 to 108 from recreating Manifold of Emotion in X3D (x3d.STEM study 7, 6 Nov). Laws 41 to 43 and failure modes 124 to 147 come from two physics bridges built under the Loom, X3D with PhysX 5 (a marble machine and an H-Anim ragdoll) and X3D with MuJoCo (13 Nov, [PXB], [MJB]); they added the physics witness and the profiles `x3d-physics/v1` and `x3d-physics-physx/v1`. The plain-language sweep is [LESSONS-v1.0.md](LESSONS-v1.0.md); for science- and maths-intensive work, start from [SCIENCE-PLAYBOOK.md](SCIENCE-PLAYBOOK.md) and the study card in `kit/templates/SCIENCE-STUDY-CARD.md`; for a stepped physical simulation, from [PHYSICS-PLAYBOOK.md](PHYSICS-PLAYBOOK.md) and `kit/templates/PHYSICS-STUDY-CARD.md`.

The single authoritative definition, consolidated on 3 November 2026 from the Drive folder, the other model's project zips and PR patches, and the notes on this Mac. It replaces no source: every source stays where it is, and this file says which one each statement comes from.

**How to read it.**
- **Citations** look like `[DEF §Laws]`: a source ID (defined in [SOURCES.md](SOURCES.md)) and a section. `[KIT …]` means this repository's own runs, under `runs/`.
- **Grades** stay C / L / S, as every source and the code use them (user decision, 3 Nov):

| Grade | Means | Who may give it | Brief's word |
|---|---|---|---|
| **C** | A named tool ran and showed it; the tool and version are named | A witness run | Measured |
| **L** | Read in code or a document, or reasoned, not run | Any agent, naming file and line | Established (read) or Estimate (reasoned number) |
| **S** | Suspected; a hunch; **anything a model wrote**; any creative judgment | Anyone; every model output starts here | Conjecture |

- **Synthetic** is a separate label, never a grade. It marks fixtures, seeded mutants and teaching data (for example Data City's 64 records, Break-the-Loom's 24 specimens, loomkit's test fixtures). A C result on a synthetic fixture is a fact about the instrument, not about the world.
- **Authored** is a second label, never a grade [MASH2]. It marks a value chosen by design rather than found in the world: a deck's attention heads, a camera plan, a palette, a mix. A C result about an authored structure is a fact about the design. Where a measured counterpart exists, show it beside the authored one and measure how far they agree. The Mashtots slide show does this: it sets the deck's authored letter graph (almost flat, 2.8 % per letter) beside the graph it measured from 342,533 letters of Grabar (led by Ա at 14.5 %), and reports that the two agree on nothing (Spearman +0.02; the delivery's numbers, not re-measured here).
- A number carried over from a source keeps that source's grade. Only a witness run raises a grade; anyone may lower one; grade changes are appended with a reason, never edited in place [DEF §Grades].
- **Status** is a second axis, orthogonal to grade: `pass`, `fail`, `error`, `not_run`, `not_applicable`, `deferred` [LS1 §12]. A C-graded fail is valuable evidence; an S-graded design choice cannot satisfy a required measured witness.

---

## 1. Purpose

**What the Loom is.** The Loom is how this project makes 3D worlds an AI can be held accountable to. A generator weaves each world from cards (data, spec, code); independent witnesses inspect it from every side; a receipt proves how it was made; and every failure becomes a rule, so no project pays for the same mistake twice [DEF §What the Loom is].

**The tether line** (grade L, proposed by the 29 Oct grand review): "X3D is the 3D format an AI can be held accountable to for structure and behaviour. For appearance, accountability takes a browser and an eye, and the Loom keeps all three in one loop" [DEF §What the Loom is].

**Why X3D: the loom heuristic.** X3D's rules are published as machine-readable XML (the XSD schema and the X3D Unified Object Model, X3DUOM), so software can check a scene an AI writes and say exactly what to fix. The generate, validate and repair loop is what makes X3D a natural spec for AI building in 3D [SITE thesis; MEAS §Headline].

**Three words, three jobs** (HagopJay's split, 30 Oct) [LEC 6; DEF §What the Loom is]:

| Word | Its one job | Scope |
|---|---|---|
| **Loom** | Make one thing right: generator, witnesses, receipt | One artifact |
| **Flywheel** | Turn a failure anywhere into a rule everywhere | All artifacts, over time |
| **Knowledge graph** | Store the flywheel's momentum so it turns when no agent is running | Everything ever learned |

Selection is what makes the graph evolve rather than hoard: grades decide how far a memory can be trusted, and two-sided tests decide whether a rule survives real files [LEC 6].

**The founding image.** Jacquard's 1804 loom wove from punched cards: to change the cloth you punched a new card, you never took scissors to the cloth. That is law 1 [LEC 2].

---

## 2. Roles

### 2.1 The human (HagopJay)

| Role | What only the human does | Source |
|---|---|---|
| Curator | Decides what is woven; models only propose | [DEF §Who does what] |
| Judge of record, eye and ear | His look and his listen decide taste. Picture judges and audio critics flag; he picks, and each pick is logged as a gold label | [DEF §Witnesses, Eyes; SPEC §Gobblering] |
| The "send" | Nothing leaves (upstream PRs, emails, public pushes, publication) without his explicit "send" | [DEF law 16; KICK §PRE 5] |
| The "yes" | Typed yes before any new cloud resource, quota or role, any delete, anything public, any paid model, going past the budget cap | [KICK §PRE 5; DEF §Decisions] |
| Decision maker | Answers the decision table; answers are quoted verbatim and dated | [DEF §Decisions for HagopJay] |

### 2.2 The models

| Role | Who has played it | Rule | Source |
|---|---|---|---|
| Builder agent: plans, writes generators, runs witnesses, repairs, debriefs | the builder model (Dynasty Loom, demiurge, a hosted model measurements); the other model, a second vendor's, by its own receipts (Loomsong Study 01 to v4, Gear, Break, Data City, IFC studio); a hosted model as writer in the measurements | Writes S; acts only through generators and witnesses; at most 3 agents at once | [DEF §Agent architecture; LS1 §16 "<vendor> session usage is excluded"; DEF law 12] |
| Judge (picture, audio, adjudication) | model F and model P; blinded model reviewers for labels | **Flags only**: located, image-bound, state `suspected`; never a number in a release (user decision, 3 Nov) | [MEAS; LS4 picture.py; IFC release_contract.py] |
| Optimiser | DSPy GEPA against the lawful metric | Runs offline, on his yes; the metric's escape hatches are closed first | [DEF §Toolchain; LEC 8] |

### 2.3 The tools (the Loom's organs)

| Tool | Organ | Accountability rule | State | Source |
|---|---|---|---|---|
| **x3d_mcp fork** (hagopjay) | Grammar and Meaning witnesses, repair, exact-fix hints | Every verdict names its commit | 103 commits ahead, 0 behind; 23 semantic checks (upstream 10); 48 tools (34); 1,047 test functions (284), C | [MC §1-2; DEF §Repo map] |
| **loom_gate.py** (x3d.onto) | Traps witness | Rules with tests on both sides, corpus re-run | 11 rules, 18 test functions, C (1 Nov) | [DEF §Witnesses] |
| **X_ITE 16.5.1** | Behaviour, Host, Eyes | Version and rig named with every render claim; shipped as the page's own files, never from a CDN | All Loom gates run on it | [DEF §Toolchain; KICK §PRE 2] |
| **Headless Chromium + Playwright** | Behaviour and Eyes instruments | Renderer named; SwiftShader is not a GPU | Chromium 131/153, Playwright 1.62/1.63 in use | [LS1 §16; DEF §Witnesses] |
| **Strict host-policy copy** | Host witness | C under the copy, L on the real host | Built | [DEF §Grades] |
| **Blender 5.2 + blenderizer** (x3d-blender-io) | The hand: generator for modelled, baked, rigged assets | Never mocked; every Blender scene also exports validated X3D; one receipt per asset | 194-case export suite | [DEF §Toolchain; MC §5] |
| **loom_receipt.py, x3dprov** (x3d.onto, x3d.ML) | Receipts | Refuses to overwrite; hash chain in the X3D head; unsigned in 0.1 | Built | [DEF §Receipts] |
| **DSPy** | Flywheel optimiser | Lawful metric, few-shot first | Measured on a hosted model | [DEF §Toolchain; MEAS] |
| **hosted model API** | Judges; cards (style, imagery, video, music) | Flags, never grades; cached by prompt hash; paid calls on his yes | Measured, [cost withheld] upper bound | [MEAS §Cost] |
| **loomkit** (this repo, `kit/`) | Portable acceptance, traps subset, fold-back and receipt tools for a machine without x3d.onto | Stdlib only; tested two-sided in normal and `-O` | C, this repo | [KIT tests/last-run.json] |

**Repo map** [DEF §Repo map; MC §5]: x3d_mcp (validator), x3d.onto (rulebook FACTS, Traps, receipts, lawful metric, Dynasty Loom, demiurge), x3d.ML (provenance: x3dprov, PROV-O, CI tether, verdict drift), x3d-blender-io (Blender weaver), x3d.xray (read path: memory compiled into a flyable scene), x3d.poc (public showcase), x3d_ai (private workbench). There never was a repo named x3d_prov: lineage lives in x3d.ML as `x3dprov` (decision 3, 1 Nov) [DEF §What happened to x3d_prov].

---

## 3. The laws

Forty-four laws bind every Loom project; each was paid for by a real failure [DEF §The laws]. Laws 17 to 20 are new in v1, drawn from incidents the other model hit and fixed across several projects; laws 21 to 25 come from the first x3d.STEM delivery (4 Nov) and its review; laws 26 to 35 from building six flagships and the loom4 delivery; law 36 from the Mashtots2 delivery (5 Nov); law 37 from the Manifold of Emotion recreation (6 Nov); laws 38 to 40 from reviewing another model's rebuilds of two private study scenes, and its notes on a third study (7 Nov, [RB1], [RB2], [PCS]); laws 41 to 43 from the PhysX and MuJoCo bridges (13 Nov, [PXB], [MJB]). Their grade is L: each generalises C-graded incidents. Sources: [LEARNINGS-from-patches.md](LEARNINGS-from-patches.md), [REVIEW-scientific.md](REVIEW-scientific.md).

| # | Law | Forbids | Paid for by (grade, source) |
|---|---|---|---|
| 1 | **Generator, not file.** Fix the card or the generator, then weave again | Hand-editing generated output | Dynasty Loom v3: 87 of 87 files rebuilt byte for byte (C, [LEC 2]) |
| 2 | **Valid is not visible.** Grammar passing starts the inspection, never ends it | Shipping on "0 errors" | 3 of 3 pocket worlds valid and white (C, [LEC 1]); 13 of 16 wrong scenes pass strict validation (C) |
| 3 | **Many witnesses, blind spots that don't overlap** | One clever test for all | Labels vanished only under the host policy (C under the copy, [LEC 3]) |
| 4 | **If you can't make it again, you don't know what it is.** Declare every input, the date included | Undeclared clock, time zone, file order, seeds, versions | Clock moved 3 days, rebuild differed (C, [LEC 4]) |
| 5 | **Say how sure you are.** C, L or S on every claim, with its instrument | Upgrading a grade in translation | "Upstream is broken" split into C and L (C/L, [LEC 5]) |
| 6 | **Models speak in S.** Model output enters as S, labelled as generated; judges flag, never grade | A model's sentence entering the record as fact | HOOKS.md 7b [DEF] |
| 7 | **Every mistake pays rent once.** Incident, fact, rule with tests, fork check, upstream | Fixing a trap in one project only | shader-raw-source: white sphere to gate rule in a day (C, [LEC 6]) |
| 8 | **Gates are fixed like code**, tests on both sides and a corpus re-run | Silencing a noisy rule | glsl-int-literal: 62 findings over 859 files, all one false line (C, [DEF]) |
| 9 | **The metric will be attacked.** Close escape hatches before optimising | Rewarding "valid" alone | 67 of 67 optimised valid scenes declared Full (L, [LEC 8]) |
| 10 | **Truth gates when the world is real.** No invented person, face, date or note | Guessed likenesses, unlabelled AI images | 20 errors and 26 warnings in shipped family data (C, [DEF]) |
| 11 | **Ask once, cache forever.** Every paid call keyed by its prompt hash and capped | Re-requesting the same picture | Portrait cache: 2 calls per person, 60 total (C, [LEC 7]) |
| 12 | **Budget is a witness.** Two or three agents at a time; partial results on disk | Wide fan-outs | 22 agents emptied the usage window in ~25 min; 4 h stop (C, [LEC 10]) |
| 13 | **Unknown is not zero; no witness, no tie** | An edge or number nobody measured | x3d.xray ledger (L, [BLUE §2]); Data City null semantics (C, [CITY]) |
| 14 | **Add layers, never replace.** Version everything | Overwriting a demo or a receipt | loom_receipt.py refuses to overwrite (C, [DEF]); every Loomsong version kept its predecessor's receipt (C, [LS2 §5; LS3 §9]) |
| 15 | **Name the instrument behind every number** | Software-GL frame rates; unpinned verdicts | "7 to 10 of 10 repairs" holds only at upstream 74da0ec, 3 to 6 at 020221e (C, [DEF]) |
| 16 | **Nothing leaves without "send".** Public pages pass a leak sweep first | Outbound PRs, emails, pushes on assumption | 33 upstream PRs drafted, 0 sent (C, [MC §9]) |
| 17 | **Evidence is bound to the exact candidate.** A witness record names the sha256 of the full candidate inventory (runtime, generators, **test code**, data, docs, vendored runtime); any change makes it stale | Packaging changed code with an old pass | Study 01 packaged a changed shader against a stale browser pass, exit 0 (C, [LS1 §9 A01]); fixed in v2 and kept in v3, v4, Gear, Data City, IFC (C) |
| 18 | **A gate is code that cannot be switched off.** Explicit raising predicates, never `assert`; tested under `python -O`; refuse an environment you cannot gate | Gates that vanish under optimisation | Red Score packaged under `-O` (C, [LS1 §9 A02]); IfcOpenShell asserts forced the IFC studio to refuse `-O` (C, [IFC]) |
| 19 | **A control must fail for the intended reason.** Every negative control expects one stable diagnostic; an instrument crash is `error`, not a catch; a missing witness, unknown status or empty profile never passes | "Some failure happened" counted as a catch | IndexError mistaken for rejection (L, [LS1 §12]); Break-the-Loom requires the exact diagnostic (C, [BREAK]) |
| 20 | **Fold back small, with the counterexample.** A lesson returns as an additions-only patch carrying the minimal failing fixture, the repaired control, its scope and its blind spots; promote only after the target corpus re-runs | Grand universal rules; browser facts promoted to X3D prohibitions | All five project PR patches have this shape (C, [KIT runs/foldbacks-20261104]); "Turn observed misses into portable counterexamples before naming a grand universal rule" [LS4] |
| 21 | **Invariants admit; they do not confirm intent.** A conserved quantity rules a run in as admissible; a separate witness must test the event the study promises | Accepting a simulation because energy and mass are conserved | Reversed vortex circulation conserved every invariant while turning approach into separation; measured low-density positions caught it (C as reported, [SCI §useful failures]) |
| 22 | **Certify the space, not the number.** Where results are degenerate or basis-dependent (eigenmodes, PCA, clustering), witness orthogonality and the invariant subspace, not eigenvalues and residuals alone | Animating an arbitrary basis vector as "the mode" | Sparse solver: good eigenvalues and residuals, non-orthogonal degenerate modes; mass whitening + Rayleigh–Ritz repaired it (C as reported, [SCI §04]) |
| 23 | **Display precision is part of the scientific budget.** Fixed declared transfer ranges, counted clipping, and an encoding precision sized to the question (thresholds, seams, cores) | Relabelling clipped values; buying pixels to recover discarded bits | 8-bit encoding moved the early zero-isosurface; 16-bit concentration fixed it (C as reported, [SCI §03]) |
| 24 | **Open what you hash.** Admission decodes every payload and archive before its hash enters a receipt | Receipts that certify broken bytes | Living Archive zip truncated yet receipted (C, [REVIEW-loom2]); a re-hashed truncated PNG passes the shipped Scientific audit (C, [REVIEW-scientific F2]) |
| 25 | **Independent witnesses need independent assumptions.** A second implementation in another language is not independent if it shares the coordinate convention, encoding or reference being tested | Calling a CPU probe that copies the shader's assumptions a witness | Shader and CPU probe agreed on a wrong L/(N−1) spacing; a double Y flip made a false surface (C as reported, [SCI GATES.md]) |
| 26 | **Suspect the witness first.** A red, or a surprise, is first a question about what the witness measured. The same value across unrelated inputs, or no change when its supposed cause changes, means it measures something else | Debugging the subject before the instrument | Kerr 2's 'GPU error' was a capture of the wrong view; the Turing Garden's quantization check returned 0.31 cells in every case at 8 and 16 bits (C, failure modes 64, 70) |
| 27 | **Like with like.** Compare quantities over the same window, state and conditions; where the construction allows, state the witness exactly | A windowed estimate against a point value; a paced beat against a beat into rested tissue | Chirp's pitch check, red twice on correct audio; the paced sheet 4.1 % 'slow' (C, failure mode 79) |
| 28 | **Explore the worst case before declaring a limit; then fix the instrument, not the threshold.** Show a resolution effect by refinement, measure the cause where it lives, keep the red run in history | Limits set on easy cases; widened limits | Electron Cloud 3s normalization 8.2e-4, resolved by refinement to a check grid (C, failure mode 76) |
| 29 | **One cause at a time.** Change only the suspected variable; a correction fitted this way is grade L; a quantity that depends on the analyst's window is reported, not gated | Writing a correction for an untested cause | A fast vortex ring blamed on the boundary, really the periodic images, with the correction's sign wrong (C, failure modes 86, 87) |
| 30 | **Nothing transfers across dimension or geometry unmeasured.** Seeds, starts and regime names are tested in the target setting; a name in a caption is a measured claim | Borrowing a 2D recipe or label for 3D or a curved domain | A 2D seed died in 3D; labyrinths became sheets; a spiral start died on a ventricle (C, failure modes 67 to 69, 82) |
| 31 | **One clock, one owner.** When sound, simulation and picture run together, one clock is master and the evidence compares the clocks, not only that each runs | Two clocks 'started together' | Chirp picture and audio 0.8 to 1.5 s apart until the audio drove the picture (C, failure mode 80) |
| 32 | **The runtime's contracts are part of the build.** No exception escapes an X_ITE field callback; navigation waits for the scene; the clock is getCurrentTime(); every component is declared | Page code written against assumed runtime behaviour | One escaping callback exception froze all routing in X_ITE 16.5.1 (C, failure mode 88); hash change before the scene loaded (C, 78) |
| 33 | **Read your own checklist.** The kickoff's trap list is read before page code, by the operator as well as the models | Rediscovering a recorded trap | The X_ITE clock trap was in KICKOFF-PRE and was hit anyway (C, failure mode 72) |
| 34 | **Every result states its scope and its reproduction level.** Say what it is not (CPU physics only, not frame rate); within grade C, say whether it was reproduced in isolation (L2), in a real browser (L3) or with a comparative measurement (L4); keep confidence in a source fact apart from confidence in its consequence | A pass whose reach is unstated | The X_ITE teardown's evidence levels and its F01/F02 records (L, [XTD §1, §9]); loom4 benchmarks scoped 'physics CPU only' (L, [LOOM4]) |
| 35 | **A signature proves a key, not an author.** Receipts stay unsigned until signing binds the validator build, canonicalization, report hash and scene hash, under an independently pinned key | Treating an HMAC with its key in the source, or a key carried in its own envelope, as proof of authorship | Tether's demo seal was forgeable from its own source (L, [TETH]) |
| 36 | **A pass names what it saw.** A witness reports an inventory of what it read (files, inline scripts, field callbacks, world loads), and its file list reaches every page that runs code; a pass over nothing relevant is visible as such | A clean result from a witness that never met the code it judges | Page traps passed the Mashtots slide show over six .js files with 0 field callbacks seen; its X_ITE driver was inline in stage.html, and reading it found an unguarded callback whose freeze was then reproduced (C, failure modes 93, 94) |
| 37 | **An artefact that claims to stand alone is tested alone.** A saved scene, export or bundle is loaded with nothing of the app around it and compared with the live view | Testing an export only inside the app that made it | The Manifold's saved moment drew opaque sheets once its page was gone; fixed, it redraws the live frame at SSIM 0.9987 (C, failure mode 103) |
| 38 | **One master, many renderers.** A second renderer reads the validated X3D itself, never a converted copy. Parity between renderers is the same sha256, the reader's coverage manifest (every node and ROUTE read, or named as skipped) and a shape witness per beat (a mask's IoU); never a pixel hash across renderers | A second renderer fed from an export that can drift from the master; renderer-only geometry | Both rebuilds drew from converted copies: one 50 % larger than the gzipped X3D, one carrying geometry and a moon the scene did not hold and a miswired reveal. The merged build reads 48 of 48 ROUTEs from the X3D, cloth mask IoU 0.976 to 0.992 at 10 beats (C, failure modes 115, 123; [RB1]) |
| 39 | **A look may add, never assert.** Decoration, generated fill and display exaggeration are labelled where they are seen and travel with the pixels (an ART mark burned into exports and filenames, a 1× switch next to any exaggeration). A defect is fixed at its source, not hidden by the tone curve | Generated detail leaving the page unlabelled; clipping hidden by tone mapping | The face-relief rebuild burned ART into every generated-fill export and added a source-1× depth switch (adopted, L); the tomb's clipping went 88.4 % to 0 % by changing the light values, not the tone curve (C, X_ITE 16.5.1, failure mode 114; [RB1], [RB2]) |
| 40 | **A fallback must say so.** When the host refuses an asset, a stylesheet or a capability, the page shows that it runs on a fallback, and a review made on a fallback is not a review of the thing | A page that looks finished while showing a stand-in | A shader study's reviewer judged the procedural stand-in, because the host blocked the real image without a word (as reported, [PCS]); X_ITE drew black under the hosted page policy because its stylesheet was blocked and its surface stayed hidden (C, failure modes 116, 122) |
| 41 | **A replaced engine is shown off, in every host that has it, and its leaks are listed.** When page code takes over from a runtime's own implementation (here a physics engine), the record shows the old one stepping nothing in each host, that writes made while it is disabled stick, that re-enabling resumes from them, and every step it took before the switch | Assuming "disabled" means off; a takeover proved in one browser | X_ITE 16.7's Bullet stepped once after `loadURL()` resolved (y 0.32 to 0.319974 to 0.319989); loading with `createX3DFromURL`, disabling, then `replaceWorld` leaks none, shown in Chromium 145, Firefox 146 and WebKit 26 (C, failure mode 127; [PXB]) |
| 42 | **Determinism is claimed per step and per host.** A simulation run records a hash of every step's state and is replayed in each host it names, Node included; the first step that differs is reported. A claim in one host is not a claim in another, and a claim on one machine is not a claim on a second | A final-state hash alone; "deterministic" said of a run replayed in one place; a hash that leaves out state | PhysX 5.12 replayed 1918 steps recorded in Chromium and 969 recorded in Firefox with 0 differing hashes in Chromium, Firefox, WebKit and Node; across machines was not run (C, failure modes 128, 129; [PXB]). The play witness (6 Nov) already compared a final-state hash on one JavaScript engine |
| 43 | **A tolerance is written before the run; an excursion is a waiver, not a pass.** Limits are declared first and may not be widened afterwards. A measure beyond its limit is recorded as an accepted failure with its owner, date, reason and its own numbers; the profile caps how many; a receipt lists them. A self-check that misses its closed form is logged with its probable cause and is never tuned to fit. *Scope: physics profiles only, for now (13 Nov decision); if it proves wrong it is marked a false positive in this table, not deleted* | Loosening a threshold to turn red green; a green label on a failing number; a failure with no name on it | 3 of 33 browser smoke tests failed under load (Galton 220 and 223 of 240 beads against 225; a music box turn 15 of 18 pegs) and the owner accepted them: three waivers under the PhysX profile's cap of three. A ragdoll's limit overshoot reached 0.43 rad against 0.2, and its Gravitron check missed its closed form by 34 % (2.97 against 2.22 rad/s): logged, not tuned (C, failure modes 133, 137; [PXB]) |
| 44 | **A check is shown able to fail, and a number is not Confirmed until a second reader has tried to break it.** Every reference ships with a wrong implementation it must reject (a control that fails when the code is right is a bug in the control too); a mutation control that changes nothing is counted as missing; a limit file is committed before the run and the runner refuses to start if it differs from its commit; a number the author reads is graded Likely until someone who did not write it has recomputed it. *Scope: physics profiles first, like law 43* | A check that passes for a wrong implementation; a quantity read after the step that enforces it; a limit that cannot be shown to precede the run; a self-graded Confirmed | The Ten Minute Physics ports' own review (13 Nov): 4 reviewers recomputed v1 to v4, 125 claims checked, 25 negative findings survived a second skeptical agent, 0 false alarms. The kinetic-energy check read 1.33e-15 with the buggy collision rule, 2.0e-15 with the fixed one and 0 with no collisions. In batch 6, 2 of 11 mutation controls scaled a limit of 0 and changed nothing (C, failure modes 148 to 160; PHYSICS-PLAYBOOK patterns 11 to 19) |

---

## 4. The loop, step by step

Every Loom build runs three rows: **weave, inspect, remember** [DEF §Anatomy]. Version 1 spells the loop out as ten steps. A red witness at any step sends work back to the card or the generator, never to the artifact [DEF §Witnesses].

```
 0 Card ─► 1 Kickoff (PRE) ─► 2 Weave ─► 3 Witness ─► 4 Gate ─► 5 Stump ─► 6 Judge ─► 7 Receipt ─► 8 Debrief ─► 9 Fold-back ─► 10 Handoff (POST)
              ▲                  ▲           │fail        │reject     │survivor    │flag                                │
              │                  └───────────┴────────────┴───────────┴────────────┘ fix the card or generator, weave again
              └───────────── the knowledge graph (FACTS, rules, memories) feeds the next kickoff's trap list ◄──────────┘
```

### Step 0: the card
Name the idea, its **source of truth** (`repo/path @ commit`), and a measurable **better** (for example "wins a blind A/B against v1", "real-GPU fps ≥ 60", "0 errors on the new pin"), plus what must not change. Leaving "better" vague is how an agent polishes forever or reports "valid" while nothing shows [KICK §Why each part is there]. For music: the score is the card; visual and audio are woven from the same card [DEF §Before the music].

### Step 1: kickoff (what to paste **before**)
Paste **PRE** as the first message of a new Loom project, with this definition attached. Use [kit/templates/KICKOFF-PRE.md](kit/templates/KICKOFF-PRE.md), the kickoff doc's text updated for v1 [KICK §PRE]. Its seven blocks:
1. **Target**: idea, source of truth, better, must-not-change, visibility.
2. **Tool pins**: fork tag `loom-pin-2026-11-01` (until it exists, fork main at a named commit), loom_gate sha, X3D version and profile, X_ITE 16.5.1 as the page's own files, Blender and blenderizer sha, Chromium and Playwright, host-policy copy, model ids. Every receipt records these [KICK §PRE 2; DEF decision 5].
3. **Traps to read before coding**: FACTS sections, the lessons table, and the trap list in §8 of this file.
4. **Generator first**: never hand-edit; deterministic bytes (SOURCE_DATE_EPOCH, seeds, sorted keys); one data file holds every number the scene shows; a red witness stops the build.
5. **Guardrails**: budget cap and ledger; typed yes for cloud, delete, public, over-cap; C/L/S on every claim; AI-made media labelled; no real faces; stop-and-show points; at most 3 agents.
6. **Witness plan** with thresholds (§6), naming the **acceptance profile** (§6.2). New in v1.
7. **Where outputs land**: one PR per behaviour change; `runs/<run-id>/witness.json`; receipts beside the artifact; heavy evidence by sha256; spend ledger private [KICK §PRE 7].

**The first-reply check:** the agent restates target and "better" in its own words, lists the witnesses, and names its first three steps with cost estimates. Only then does it start [KICK §PRE]. This catches a wrong reading of "better" before work is spent on it.

### Step 2: weave
Write or extend the generator, never the output [DEF law 1]. Practices that every project proved:
- **One event model** feeds audio, geometry and UI, so they cannot drift apart [LS1 §2].
- **Declared inputs only**: seed (Loomsong 61429), SOURCE_DATE_EPOCH, pinned library versions; same-environment byte-equal regeneration (Loomsong 10, 12, 15, 22 outputs across v1 to v4, C) [LS1; LS2; LS3; LS4].
- **Bake what is spatially expensive and temporally stable; keep score time and camera live** [LS4 §Practical wisdom].
- **Bundle the full pinned runtime**: the loader alone was not enough; ship CSS and dynamically loaded components, and expect zero external requests [CITY lesson 1].
- **Build atomically, or refuse to serve while building**: a preview that mixed new JavaScript with the old scene failed; v4 added a build marker that makes the server refuse requests [LS3 §1; LS4].

### Step 3: witness
Run the witnesses, cheapest first: file-reading witnesses (Grammar, Meaning, Traps) before browser and human ones (Behaviour, Host, Eyes last) [DEF §Witnesses]. Each witness writes one **witness record** (`loom.witness/1`, §5) bound to the candidate's sha256. If the candidate changes while it runs, it refuses: `CANDIDATE_CHANGED_DURING_WITNESS` [LS3 §1]. The eleven witnesses are in §6.1, and each project adds domain witnesses to its profile.

### Step 4: gate
A witness observes; a **gate decides** [LS1 §7]. v1 has one acceptance function (`kit/loomkit/accept.py`). A named **profile** lists the required witnesses, and acceptance is "a closed set of current-candidate witnesses, not a score" [IFC release_contract.py]. Algorithm [LS1 §14, tightened in LS2-LS4 and IFC]:
1. Freeze the candidate inventory; compute its sha256 (evidence, caches, VCS and archives excluded, so the digest is never self-referential).
2. Resolve the profile's required set. An empty set rejects (`EMPTY_PROFILE`).
3. For each required witness, require one well-formed record: present (`MISSING_WITNESS`), right schema and name, bound to this candidate (`STALE_WITNESS`), not a development run (`DEVELOPMENT_WITNESS`), status `pass` (`WITNESS_NOT_PASS`) or an allowed `deferred` / `not_applicable` with a written reason (`STATUS_NEEDS_REASON`), grade C for a pass (`UNMEASURED_REQUIRED_WITNESS`), coverage fields present (`COVERAGE_REQUIRED`), evidence files unchanged (`EVIDENCE_DRIFT`).
4. Only then write the receipt.

All predicates raise explicit errors and are tested under normal Python and `-O` [law 18]. Exit codes: 0 accepted, 1 contract violation with a stable code, 2 instrument or input error [CITY README].

**Reuse the acceptance code, do not rewrite it.** The first x3d.STEM project wrote its own gates and lost two of the hardest-won rules: its admission gate is an `assert` (red passes under `-O`), and its browser evidence names no candidate (C, [REVIEW-scientific F1, F3]). Both were fixed in Loomsong v2. Kickoffs should hand the builder `kit/loomkit` (or the family's shared acceptance module) and require its profile, not describe the rules again in prose.

### Step 5: stump (attack the Loom)
Accepted evidence is only as strong as the controls that tried to break it. Stumping is the Loom's attack step (user decision, 3 Nov). It has two halves:
- **Attack the candidate (Break-the-Loom).** Generate single-fault mutants with a repaired control for each. Every mutant must be schema-valid ("valid syntax should stay valid"), and the assigned witness must reject it with its exact diagnostic while the control passes. Read the matrix cell by cell: Caught, Clear, XSD-valid, Outside scope, Error. A **clear** cell is a coverage question for a named owner before it is a request for a new rule [BREAK TECHNICAL].
- **Attack the model (stumping rubrics).** When the Loom is used to test a model, write criteria where models actually slip: numbers hidden inside creative work, version traps the grader runs, specs given as images, the solver's own outputs checked against each other, and shortcut-killers. Put 80% or more of the points on 20 to 30 criteria, each ending "If …, this item fails", and keep files and naming at 5% or less. Aim each trigger at the slip, not at a blunder; prove feasibility headless; rerun 2 to 4 times [STUMP §Bottom line, §Final insights, App. A, D]. The graded references showed partial credit is the default: with no trigger, 11 partial misses still scored 0.739; one well-placed trigger zeroed Boston's heaviest item (L, as reported in [STUMP §What the graded references proved]).
- **Test the observer as deliberately as the object.** Use a displaced marker, a 1% wrong-speed rotor, an induced stall that must appear in the recorded frame gaps, a corrupted asset that must stop startup [GEAR §5-6; LS4].

### Step 6: judge
Taste stays with the human; machines raise flags.
- **Eyes and Ear**: HagopJay's eye and ear are the judge of record [DEF §Witnesses; SPEC]. Nobody has yet heard the Gobbler's music (gap, [DEF §Known gaps 1]).
- **Model judges flag only**: a located, image-bound, `suspected` observation (view, normalised region, concern of more than 15 characters), bound to the candidate and to each frame's sha256. Any score, rating, "n/10" or `confirmed` state rejects (`PICTURE_GRADING`, `MODEL_TRUTH_PROMOTION`) [LS4 picture.py; IFC]. Implemented in `kit/loomkit/picture.py`.
- **Numeric judge scores only in labelled experiments** (user decision, 3 Nov), for example ranking variants in a Gobblering round (§9.3). They never gate a release. Why: re-judging the same frame moved the judge's score by sd 0.12 to 0.25 (C, [MEAS]); a black still once scored 2.33 (C, [DEF lesson 18]); the judge is not calibrated against people [MEAS §Vision judge].
- **Separate three questions** for every visual change: did the change reach the renderer; is the candidate still technically sound; is it artistically better? The first two are witnessed; the third is his [LS2 §The strongest lesson].

### Step 7: receipt
Write one **Loom Receipt v1** per accepted artifact (`loom.receipt/1`, §5), only after acceptance. It names the candidate sha256 (the subject; the receipt is never hashed into it), each required witness record's hash, the unrun witnesses (visible, never hidden), tool pins, outputs with bytes and sha256, model calls by prompt hash with a cached flag, budget, limitations, and `prev`, the receipt it replaces. It refuses to overwrite [DEF §Receipts; LS1 §14; LS4 package.py]. Receipts are unsigned: they make drift visible; they do not authenticate authorship [LS2 §2; IFC].

### Step 8: debrief
Fill [kit/templates/DEBRIEF-FORM.md](kit/templates/DEBRIEF-FORM.md). The shape is the one the other model's debriefs converged on [LS1; LS2; LS3; LS4; IFC; GEAR; BREAK; CITY]:
- outcome and scope (what was retained, reduced, deferred);
- a witness inventory with **actual status and its boundary** ("what a pass does not establish");
- the gates that actually controlled the work;
- the receipt lineage (candidate, previous receipt, archive);
- incidents, each with repair, evidence and **learning maturity**: implemented locally, reproduced, proposed, or inconclusive;
- lessons to fold back, with their destination;
- what should stay local (creative decisions become scoped art-direction memory, never universal rules, never promoted from S to C because tests passed) [LS3 §10];
- reproduction commands.

### Step 9: fold-back (what the Loom learned returns to the Loom)
Every lesson travels as a **PR-style fold-back patch**. Five of the project zips carry one (C, [KIT runs/foldbacks-20261104]):
- additions-only, under `tools/<name>/`;
- a README with `git apply --check`, `git apply`, then `python3 tools/<name>/smoke.py` and `python3 -O tools/<name>/smoke.py`;
- production predicates plus the minimal fixtures and negative controls;
- tested in an empty temporary git repository, with no compatibility claimed against an unseen checkout;
- a destinations table: x3d.onto for facts and traps, the fork for standard-level semantics, x3d.ML for lineage, shared acceptance code for release rules;
- no CI activated and nothing pushed.

Check one with `kit/loom foldback`. Fill [kit/templates/FOLDBACK-FORM.md](kit/templates/FOLDBACK-FORM.md).

The **flywheel** a fold-back feeds has five stages [DEF §The flywheel; LEC 6]: (1) incident, with a minimal reproducer saved; (2) fact, a graded FACTS entry; (3) rule, a gate rule with tests on both sides, re-run over the whole corpus (798 to 883 files so far); (4) fork check, when the lesson is about meaning rather than one browser; (5) upstream, a rebuilt, trailer-free PR to the Consortium, **only on "send"**. A rule that proves wrong goes back to stage 3. Four loops have been traced commit by commit; none has reached stage 5 (C, [MC §6]). Break-the-Loom writes the same wheel at a finer grain: observed incident, scoped fact, executable predicate, two-sided controls, wider corpus, reviewed promotion [BREAK].

**A project thread folds back by PR, and numbers from upstream** (13 Nov, failure modes 146, 147). The Loom is edited by many cloud threads and by this Mac's consolidation; a thread that built under the Loom ends with a PR to `hagopjay/x3d.loom` whose laws and failure modes are numbered from upstream's tip that day, and a local copy names its base commit. Two physics threads finished without one; [PHYSICS-PLAYBOOK.md](PHYSICS-PLAYBOOK.md) is their return.

**A rebuild by another model is reviewed like a fold-back** (7 Nov, [RB1], [RB2]). Fill [kit/templates/REBUILD-REVIEW.md](kit/templates/REBUILD-REVIEW.md): confirm the master's sha256 survived; find whether the rebuild reads the master or a copy; test every critique it makes, and every one of ours it answers, and mark each held or fell with the instrument that decided it; check everything it adds to the picture against what the scene holds; run it under the host's page policy. Then fold: scene fixes go into the generator; renderer facts become runtime-labelled traps (`kit/loomkit/traps.py`); page facts become page traps (`pagetraps.py`); taste stays a local record. The first such review retracted one of our own claims (an "X_ITE shared-Coordinate bug" that a minimal repro did not show, law 26).

### Step 10: handoff (what to paste **after**)
Paste **POST** in the same first message as PRE. It is the done-when; a missing item means not done [KICK §POST]. Use [kit/templates/HANDOFF-POST.md](kit/templates/HANDOFF-POST.md). It has eight items: receipts, witness table (red rows stay red, with reason and fix plan), numbers (each with witness, commit and grade), frames (fixed-time stills, a host-copy run, a contact sheet, before and after), lessons (FACTS entry with symptom, cause, fix, test; a proposed rule with one passing and one failing test; upstream yes or no, held for "send"), spend, versions, next. v1 adds a ninth: **the fold-back patch** and its `loom foldback` result.

An agent working elsewhere reports in with the 8-part shape in [kit/templates/REPORT-IN.md](kit/templates/REPORT-IN.md) [DEF §Brief for the agent still out].

---

## 5. Artefacts and their formats

| Artefact | Format (schema) | Written by | Lives | Source |
|---|---|---|---|---|
| Card | Data file(s): score, CSV, IFC, recipe JSON, style board | Human or agent, then frozen by hash | Project repo `sources/` or `cards/` | [DEF; LS1; GEAR; CITY] |
| Generator | Code that emits the X3D and a manifest | Agent | Project repo `gen/` | [DEF law 1] |
| Build manifest | `outputs: {path: {bytes, sha256}}`, seed, versions | Generator | `assets/build-manifest.json` | [LS1 §8] |
| Candidate inventory | `loom.candidate/1`: `{files: {path: sha256}, sha256}` | `loomkit candidate` | Recomputed, never stored inside itself | [LS2 §2; core.py] |
| Witness record | `loom.witness/1`: witness, status, grade, subject_sha256, instrument, measurements, coverage, limitations, evidence[{path, sha256}], development, reason, environment{python, optimized} | Each witness | `runs/<run-id>/evidence/<witness>.json` | [LS1 §14 proposal; LS2-LS4 contract.py; core.py] |
| Acceptance profile | `loom.profile/1`: name, required[{witness, allow, coverage}], visible_not_run, limitations | Kickoff | `kit/profiles/*.json` | [LS1 §11 required_witness_set; this repo] |
| Picture review | `loom.picture-review/1`: subject_sha256, reviewer, state=suspected, images{view: sha256}, flags[{id, view, region, concern, state}], scope | Model judge | Beside the frames | [LS4 picture.py] |
| Loom Receipt v1 | `loom.receipt/1`: kind=artifact, subject, candidate_sha256, profile, inputs, tools, outputs, witnesses[{witness, status, grade, record_sha256}], not_run, model_calls, budget, limitations, prev, signed=false, sha256 | `loomkit receipt`, after acceptance | `receipts/<artifact>.json` beside the artifact | [DEF §Receipts proposal; KICK §POST 1] |
| x3dprov chain | Hash-chained steps in the X3D `<head><meta>` | x3dprov 0.1 | Inside the scene | [DEF §Receipts] |
| FACTS entry | Symptom, cause, fix, test, grade, instrument, scope, reproducer path | Agent at incident time | x3d.onto `FACTS.md` (sections A to Q exist) | [KICK §POST 5; DEF §Flywheel] |
| Fold-back patch | Additions-only unified diff under `tools/<name>/` + README + smoke.py + fixtures | Agent | `integration/*.patch` in the project | [LEARNINGS §The PR shape] |
| Debrief | Form in `kit/templates/DEBRIEF-FORM.md` | Agent | Beside the release | [LS1-LS4] |
| Evidence manifest | `loom.evidence-manifest/1` (`kit/templates/evidence-manifest.schema.json`) | Release step | Beside the archive | [LS1 §8; LS4 check_release.py] |
| Spend ledger | One line per paid call: model, units, list price, prompt hash, cached | Every paid call | Private project files only | [KICK §PRE 5; MEAS §Cost] |
| MemoryRecord (planned) | One line per write: kind = claim, session, tie, artifact, coverage, note, petition, answer | Scribe | The knowledge graph | [BLUE §3.2; DEF §Knowledge graph] |

---

## 6. Quality gates and rubrics

### 6.1 The witnesses
Eleven Loom witnesses [DEF §The witnesses], with the domain witnesses projects added. "Blind to" is why there are many.

| # | Witness | Asks | Instrument today | Blind to | State |
|---|---|---|---|---|---|
| 1 | Grammar | Tags and attributes legal for the declared version? | X3D 4.0/4.1 XSD via the fork | Meaning, behaviour, looks | Built |
| 2 | Meaning | ROUTE types and order, DEF before USE, profile and components, containerField, colour range, H-Anim names | Fork: 23 semantic checks | One browser's quirks | Built |
| 3 | Traps | Has this exact trap already cost us once? | loom_gate.py (11 rules + `--fork`); loomkit.traps (11-rule portable subset) | Traps nobody has paid for | Built |
| 3b | Page traps | Has this page code already cost us once? Syntax, guarded X_ITE field callbacks, getCurrentTime, navigation after the scene, window-global names, budgeted world loads | loomkit.pagetraps (6 rules and 6 reading forms, two-sided tests, `node --check`). Reads .js files and the inline `<script>` blocks of HTML, resolves callbacks passed by name, skips window-name checks in module code, and reports what it saw (law 36). Required by every x3d.STEM profile since 5 Nov | Page behaviour (the browser evidence and its resilience probe are the behaviour witness) | Built |
| 3c | Physics | Does the run carry its own proof: a hash of every step replayed unchanged in every named host, exact references with limits declared first, a takeover shown off with its leaks, a loss report, and every excursion a capped waiver? | loomkit.physics (`kit/loom physics`; record format `loom.physics-run/1`; 18 PHYS_* codes, each with a two-sided test; reads the record a project's own harness wrote) | Whether the model is right where no exact reference exists; another machine, engine build or GPU; whether the harness replayed what it says | Built (13 Nov) |
| 4 | Behaviour | Does the real browser load, compile and route it, console clean? | X_ITE 16.5.1 headless, Chromium, Playwright | Taste; real-GPU speed | Built |
| 5 | Eyes | Lit, framed, unclipped, beautiful? | Frames at every stop, luminance measures, flag-only judge, **his eye** | Off camera | Built |
| 6 | Host | Does it work where it will live? | Strict copy of the hosted-page Artifact policy | Real-host differences (L) | Built |
| 7 | Receipts | Can we make it again, byte for byte? | loom_receipt.py; rebuild and compare sha256 | Whether the thing is right | Built |
| 8 | Truth | Does content match the real world and the project's rules? | Per project (dynasty data gates, Data City truth gate, score fixture) | Anything not yet a rule | Built per project |
| 9 | Budget | Over the cap, or a repeated paid call? | Prompt-hash cache, caps, spend log | Quality | Partly built |
| 10 | Ear | Right sound, loudness, sync? | Loudness and peak; onsets vs score | Taste in sound | Partly built (Loomsong) |
| 11 | Score | Does every drawn event come from a note, and every note get drawn? | Event to geometry bijection | Interpretation | Built for one source (Loomsong) |

Domain witnesses that projects added and that v1 adopts as named, optional profile entries: **Sync**, **Flash**, **Fps**, **Pose**, **Fidelity** [SPEC]; **Optics**, **Motion** (camera cards), **Onsets**, **Picture protocol**, **Profiler** [LS3; LS4]; **Rendered pose** and **Observation window** [GEAR]; **Integration (fold-back)** [GEAR; IFC; LS4]; **Protocol** (revision CAS, idempotency) [IFC].

**Science witnesses (x3d.STEM, 4 Nov).** From the Scientific Loom's GATES.md, reconstructed in `kit/loomkit/sci.py` and the profile `x3d-stem-science/v1` [SCI; REVIEW-scientific]: SCI-MODEL-SCOPE (equation, domain, units, parameters, stated limits), SCI-INVARIANTS, SCI-REFERENCE-CONTROL (an analytic limiting case), SCI-REFINEMENT (named norm, resolution sequence), SCI-DEGENERACY (orthogonality, not eigenvalues alone), SCI-DOMAIN-MAP, SCI-RECONSTRUCTION (independent decode vs rendered diagnostic pixels), SCI-SURFACE-PROXY (unquantised vs decoded contours), SCI-DISPLAY-RANGE, SCI-CASE-DOMAIN (only computed cases are selectable), SCI-FRAME-COHERENCE, SCI-DEFORMATION, SCI-PUBLICATION, SCI-FAIL-CLOSED, SCI-GPU-LOCATION; still open in the source: SCI-PAIRED-VISUAL-REVIEW, SCI-TOPOLOGY-CONVERGENCE, SCI-FULL-BZ-GAP. Loomkit adds two of its own to the static set: false-green detection (a recorded pass must follow from observed vs limit) and builder binding (the shipped builder produced the bank).

Why many: each "blind to" is covered by another row. Order matters: cheap file readers first, browser and person last, and only on files that passed [DEF §The witnesses].

### 6.2 Acceptance profiles
A profile names which witnesses must be present, current and green for one kind of delivery. It keeps deferred, not-applicable, blocked and failed distinct [LS1 §1 "acceptance profile"]. Profiles seen so far:

| Profile | Required set | Source |
|---|---|---|
| `x3d-static/v1` (this repo) | grammar, meaning, traps, truth, foldback; behaviour, eyes, host visible as not_run | [KIT kit/profiles/x3d-static.json] |
| `x3d-stem-science/v1` (this repo) | grammar, meaning, traps, science (9 cases, 4 kinds, required reference/invariant/refinement/degeneracy witnesses per kind); browser, GPU, paired visual review, topology convergence and full-BZ gap visible as not_run | [KIT kit/profiles/x3d-stem-science.json] |
| `x3d-physics/v1` (this repo) | grammar, meaning, traps, page-traps, physics (waiver cap 0), behaviour; eyes, cross-machine, host, listening and paired visual review visible as not_run | [KIT kit/profiles/x3d-physics.json] |
| `x3d-physics-physx/v1` (this repo) | the same, with the physics witness bound to 2 runs, at most 3 waivers and the takeover required | [KIT kit/profiles/x3d-physics-physx.json] |
| Scientific Loom pass 1 (its own) | audit (numerical gates, payload hashes, time, clipping, quantisation) + browser + transitions; release reads their JSON | [SCI tools/release.py] |
| Loomsong local interactive study (v2) | local (8 named checks), browser (full playback), loudness, rebuild, gates | [LS2 §2] |
| Loomsong v3 | + optics, motion, onsets | [LS3 §7] |
| Loomsong v4 | + fidelity, integration, profiler, picture-protocol; 9 browser coverage flags; 21 sampler probes | [LS4 contract.py] |
| IFC bridge studio | core, optimized-safety, static, protocol, rebuild, integration, browser, gates + picture observation | [IFC release_contract.py] |
| Data City | local, browser, rebuild, release_gates | [CITY TECHNICAL] |
| Loomsong full production (spec, not built) | 16 witnesses: the 11 + Sync, Flash, Fps, Pose, Fidelity | [SPEC §Witnesses and gates] |

### 6.3 Thresholds the sources set
Thresholds belong to a profile. Hard boundaries need just-inside and just-outside fixtures [LS1 §11].

| Measure | Threshold | Status | Source |
|---|---|---|---|
| Integrated loudness | −14 LUFS ±1 (spec, full production); −18 to −12 LUFS enforced in the local study profile | Spec vs enforced differ, see SOURCES §Disagreements | [SPEC; LS2 §3] |
| True peak | ≤ −1.0 dBTP | Enforced v2+ | [SPEC; LS2] |
| Onsets vs score | median ≤ 5 ms, p95 ≤ 15 ms (spec); max ≤ 25 ms on the isolated silver stem (v3, enforced) | Partly built | [SPEC; LS3 §5] |
| A/V sync | page clock within 16.7 ms of audio clock; broadcast window 45 ms ahead / 125 ms behind (L, check ITU-R BT.1359 before quoting) | Not built | [SPEC; DEF M3] |
| Rendered notes | precision and recall ≥ 0.99 at 50 random times (spec); 199 of 218 eligible IDs decoded at 35 s (v3) | Partial | [SPEC; LS3 §5] |
| Flash | 0 WCAG 2.3.1 violations (≤ 3 flashes/s, L) | Not run anywhere | [SPEC; DEF M8] |
| Fps | Real GPU, 1080p: median ≥ 60, 1% low ≥ 45 | Not measured anywhere | [SPEC] |
| Eyes nonblank | mean luminance > 2/255; > 2% of region > 5/255; < 15% > 250/255; region central 60% × 15-80% | Enforced v2+ | [LS2 §4] |
| Effect presence | unchanged-frame control < 0.001/255; changed > 0.005 or > 0.02 | Enforced v2+ | [LS2 §4] |
| Eyes (spec) | no black frame; 95th luminance percentile < 0.98 | Spec | [SPEC] |
| Camera motion | lens 0.25-1.25 rad; eye-target > 2 units; < 4 units/s; < 20°/s; endpoint < 0.01 | Enforced v3+ | [LS3 §4] |
| Gear clearance | strictly positive certified lower bound over a complete angular cover; unresolved at depth 18 fails | Enforced | [GEAR §4] |
| Gear motion | ≥ 30 frames over ≥ 2 s; slope error ≤ max(1e-5 rad/s, 0.02%); residual < 1e-4 rad | Enforced | [GEAR §5] |
| IFC geometry | one-to-one winding-sensitive triangle match within 20 µm | Enforced | [IFC] |
| Judge noise | re-judging moves a mean by 0.09; differences under 0.2 are noise | Measured | [DEF §Toolchain; lesson 18] |

### 6.4 Stumping rubric rules
For prompts that test models [STUMP; STUMPB; TIDE]:
- Every criterion uses the form `R## · points · class` / title / quoted brief words / check / "If …, this item fails." Trigger kinds: tolerance, counted sample, frame window, shortcut named as an outcome, direction or sign, run gate, repeatability, two outputs agree, stress at extreme inputs [STUMP App. A].
- 80% or more of the points go on criteria worth 14 to 25 points; files and naming at 5% or less [STUMP].
- Fairness, checked by script: every quote appears word for word in the brief; every expected number is recomputed; unstated norms total 5% or less; no requirement is impossible at the corners of its own ranges [STUMP App. D].
- Version traps bite only when code runs: name the version, never the new API [STUMP App. C].
- Template: [kit/templates/STUMP-CRITERION.md](kit/templates/STUMP-CRITERION.md).

---

## 7. Measurements so far

Grades as carried from the source; **synthetic** marks fixtures and teaching data. Nothing here has been replicated outside the project [SITE caveats].

### 7.1 X3D on a hosted model (30 Oct) [MEAS; SITE]
| Question | Result | Grade |
|---|---|---|
| Do XSD + X3DUOM excerpts make an AI judge better? | model P: 99 vs 87 of 115 fuzzer findings right (p 0.017); invented evidence 9 vs 29. model F: 86 vs 75 (p 0.027). Grounded Flash matched bare model P at under half the cost ([cost withheld] vs [cost withheld]) | C |
| Does the lawful metric give DSPy something to optimise? | GEPA on model L, 50 unseen prompts: 31.3 → 58.3 and 32.6 → 60.2 (two runs, p < 0.001); with 3 repair rounds 39.6 → 70.3 (perfect scenes 2 → 13); no help on model L2 (92.6 → 93.6, ns); model F had nothing to tune (99.6) | C |
| Do exact-fix hints beat plain errors? | model L, 540 broken scenes (**synthetic** mutants): first repair valid 507 vs 489 (31 gained, 13 lost, p 0.0096); round 2: 530 vs 524 (ns). Gains concentrated on ROUTE-before-node (32 → 45 of 45). Hints alone, no model: 522 of 540, of which 12 only by deleting a node; the original restored in 257 | C |
| Is a vision judge usable on X_ITE frames? | model F on 35 frames, judged twice: re-judging sd 0.12-0.25 while frames span 4.7-6.7; Flash and Pro agree in rank (Spearman 0.66); not calibrated against people | C |
| Spend | [cost withheld] of [cost withheld] approved, upper bound from token counts at assumed prices, 4,180 calls | C (ledger), price basis L |
| Labels | 7 blinded model reviewers; 2 adversarial reviewers re-checked 47 contested findings and upheld 46; reviewers saw the same files as the grounded arm | C, with that bias |
| Stack findings from the labels | 55 XSD content-model errors; 28 X_ITE bugs (profile check ignores component levels, x_ite.js:52514); 16 X3DUOM errors (PhysicalMaterial missing from profile lists); 5 fork/fuzzer bugs; none reported upstream | C (as labelled) |

### 7.2 Metrics and gates (x3d.onto) [LEC 1, 8; DEF]
| Measure | Result | Grade |
|---|---|---|
| Lawful metric vs strict validity | AUC 0.997 on 383 recorded scenes, model-free | C |
| Wrong-but-valid scenes | 13 of 16 (**synthetic**) pass strict validation; lawful catches 16 | C |
| DSPy with Full open | 67 of 67 valid scenes declared profile Full | L |
| Hard-prompt failure | plain 84%, DSPy Full open 64%, Full barred 30%, five plain examples 6% (100 trials per arm) | L |
| Valid scenes that draw nothing | 203 of 1,058 | C [DEF lesson 1] |
| Gate false positives | glsl-int-literal: 62 findings over 859 files, all one false line; fixed and re-run | C |

### 7.3 Projects (the other model's runs, local renderer = SwiftShader unless stated)
| Project | Key measured results | Grade | Source |
|---|---|---|---|
| Dynasty Loom v3 | 87 of 87 files rebuilt byte for byte; 1 hidden input (the date) found; 302 people pass the publish gate; 20 errors and 26 warnings in shipped data; portrait cache ≤ 2 per person, 60 total | C | [LEC 2, 4, 7; DEF] |
| Loomsong Study 01 v1 | 60.931 s, 450 events (94 composer, 356 arrangement), 58,500 ribbon vertices; 10 outputs byte-identical on rebuild; master −14.92 LUFS, −1.97 dBTP; audit: 156 member hashes verified; A01 and A02 reproduced | C | [LS1] |
| Cinematic v2 | 14 release controls (7 cases × normal/-O); 12 outputs byte-identical; full 62.94 s playback; 8 shots | C | [LS2] |
| Cinematic v3 | 22 gate executions; 15 outputs; 95/95 silver attacks, max 11.17 ms; 199 rendered IDs at 35 s; 9 interruption paths | C | [LS3] |
| Cinematic v4 | 40 gate executions (20 cases × 2); 22 outputs; 21 GPU texel probes; 25 BRDF reference probes within 0.0021 | C | [LS4] |
| Gear Loom | min certified clearance 0.0448 mm (six recipe) vs sampled 0.150 mm; 64 intervals per tooth pitch; 1% speed mutant and 180 ms stall caught | C (floating-point certificate, not exact arithmetic) | [GEAR] |
| Break the Loom | 12 mutants rejected with their exact diagnostic, 12 controls accepted, all XSD-valid (**synthetic** corpus) | C | [BREAK] |
| Data City | 64 records (**synthetic** teaching data); null/zero/negative semantics; checksum-ID pixels; 19 diagnostics | C | [CITY] |
| Confluence IFC studio | 111 IFC products; 31 core defect controls; 20 GPU texel probes; 14 browser checks; max extent error 5.3e-9 m | C | [IFC] |
| Gobbler Cabinet, Linked Observatory, Living Archive, Constellation 3 (4 Nov) | 2,476-node graph, 50,058 Pantheon splats kept; 103 canonical class joins; arrival bound to an observed fresh frame; receipts match the files, but the Living Archive zip was truncated before upload | C (receipts, my checks); L (debrief numbers) | [REVIEW-loom2] |
| Scientific Loom pass 1 (x3d.STEM, 4 Nov) | 9 computed cases (GPE 80³ ×2, Kerr 1,600×1,000 ×3, Cahn–Hilliard 72³ ×2, Bloch FEM ×2); 57 declared numerical checks; Kerr constraint residual < 7×10⁻⁹; GPE temporal refinement ratio ≈ 0.25; 24 ParaView exports | C (shipped audit reproduced byte-identical here); L (solver figures as reported) | [SCI; REVIEW-scientific] |
| Every project | Dedicated-GPU frame rate, physical A/V latency, formal flash analysis, human approval | **not measured** | [LS1-LS4; SPEC] |

### 7.4 This repository's own runs (3-4 Nov UTC, Python 3.13.2, macOS arm64)
| Run | Result | Grade |
|---|---|---|
| loomkit self-test, normal and `-O` | 41 negative controls rejected with the intended code; 11 trap rules pass their clean fixture and catch their failing one (**synthetic** fixtures). A deliberately weakened copy (stale check removed) fails the suite with SURVIVING_CONTROL | C [KIT tests/last-run.json] |
| Fold-back survey, 5 distinct patches (10 copies) | 4 pass (Break, Data City, Gear, Loomsong v4: clean apply, additions-only, smoke green normal and `-O`). IFC bridge, rerun with the studio's own venv (IfcOpenShell 0.8.5, arm64): node protocol check passes (3 positive, 6 negative), but the Python smoke **fails its positive control** with WORLD_TRIANGLE_MISMATCH: 2 of 111 products (boxes, 12 triangles each, same count) have 4 triangles whose centroids sit 11.7 mm off, consistent with the other diagonal of each quad face. Same surface, different triangulation; the author's receipt shows a pass on its own platform | C counts; L diagonal explanation [KIT runs/foldbacks-20261104/report.json, interpreter = the studio venv] |
| Patch reproduction (projects agent) | `Loomsong-v3-to-v4.patch` on v3: every source file equals v4; after `gen/build.py` (40 s, 22 outputs) X3D, JSON and WAVs are byte-identical, all 9 PNGs pixel-identical but not byte-identical, two floats differ in the last bit (≤ 3.6e-15). `IFC-X3D-Bridge-upgrade.patch` reverse/forward-applies to exactly the Studio zip | C [CAT §Patch results] |
| Data City through `x3d-static/v1` | Accepted: grammar and meaning pass on 2 scenes (fork fa0b389, branch fix/physics-findings, not the family pin); traps 0 errors; project truth gate exit 0; fold-back pass; behaviour, eyes, host visibly not_run. Controls on the real project: a hand edit gave STALE_WITNESS; a planted colour gave 73 trap errors | C [KIT runs/data-city-20261104] |
| Traps over 48 unique real X3D files | Error rules hit only Break-the-Loom mutants (route-before-def on 01-route/mutant, shader-raw-source on 02-raw-shader/mutant); 0 error hits on any control or project scene. Warning rule metadata-containerfield fires 23 times on Break 09 and 12 (controls and mutants): the pattern Gear and IFC saw X_ITE warn on, unconfirmed in a browser here (L) | C counts, L meaning [KIT runs/traps-corpus-20261103] |
| Scientific Loom through `x3d-stem-science/v1` (4 Nov) | As delivered: **rejected**, Meaning 3 errors per scene (Shaders and Texturing level 2 undeclared). With `proposals/scientific-loom-hardening.patch`: **accepted**, normal and `-O`; receipt verified. loomkit `sci` rejects four seeded defects under `-O` (corrupt payload, rehashed truncated PNG, false green, dropped reference control); the shipped audit lets the first through under `-O` and the second through in both modes | C [KIT runs/scientific-loom-20261104*] |

---

## 8. Known failure modes and their fixes

Each row is a trap someone paid for. The fix is the v1 rule; LEARNINGS-from-patches.md has the longer account.

| # | Failure | Fix (rule) | Source |
|---|---|---|---|
| 1 | Valid X3D draws white: raw GLSL in a ShaderPart is read as a URL | `data:x-shader/x-fragment,` prefix; trap shader-raw-source | [LEC 1; FACTS P via DEF] |
| 2 | Valid X3D, invalid GLSL (`active` reserved) | Runtime `isValid` check + compile witness; lexical guard | [LS1 F01] |
| 3 | ROUTE before its node: fork passes, X_ITE drops | trap route-before-def; fork 788041c | [DEF; MC FW2] |
| 4 | Colour above 1: XSD error blames something else | trap color-range | [KICK] |
| 5 | White emissive washes out coloured faces | trap color-emissive-white | [FACTS Q via DEF] |
| 6 | WOFF2 fonts need eval: labels vanish under host policy | Ship TTF; Host witness | [LEC 3] |
| 7 | X_ITE has no public scene clock | The page (audio clock) owns time | [DEF lesson 9; KICK] |
| 8 | Still PNG in MovieTexture hangs the world | trap movie-not-still | [KICK] |
| 9 | GaussianSplats culled never sorts, loading never ends | bboxSize/bboxCenter on every node; trap splat-bbox | [DEF §Video to world] |
| 10 | Build date leaked into output | SOURCE_DATE_EPOCH; rebuild with the clock moved | [LEC 4; BREAK] |
| 11 | Optimiser declares profile Full | Lawful metric charges for every step above the smallest profile | [LEC 8] |
| 12 | Old browser pass authorises changed code | Witness records bound to the candidate digest, test code included | [LS1 A01; LS2] |
| 13 | `python -O` strips asserts; red gate packages | Explicit raising predicates; tests in both modes; refuse `-O` if a dependency asserts | [LS1 A02; IFC] |
| 14 | Packager checks values present, not a required set | Named required set; empty set rejects | [LS1 §9] |
| 15 | "pass" without a threshold | Numeric predicates with units, window and just-inside/outside fixtures | [LS1 §6, §11] |
| 16 | Preview mixed new code with an old scene | Sequence build before witnesses; refuse to serve while building | [LS3; LS4] |
| 17 | Shader assumed local position was world | Declare coordinate spaces; use the runtime's matrices | [LS3 §2] |
| 18 | Smoothing failed: unshared vertices | Weld, orient; topology witness with a reversed-face control | [LS3 §2] |
| 19 | Diagnostic colours contaminated by overlays | Overlay-free path, flat attributes, checksum, corrupted-ID control | [LS3 §5] |
| 20 | Image difference came from UI, not the scene | Hide UI, freeze CSS animation, unchanged-twice control first | [LS2 §4] |
| 21 | Shaders compiled while bakes 404'd | Asset preflight: verify bytes and sha256 before scene creation; corrupted-asset control | [LS4] |
| 22 | Atlas V convention swapped materials | GPU texel probes at declared coordinates | [LS4] |
| 23 | One ImageTexture per binding | One DEF owner, USE references, no mips on data maps | [LS4] |
| 24 | CPU time renamed GPU time; idle frames called fps | Four clocks kept apart; forced-redraw workload; nulls for unavailable | [LS4; IFC] |
| 25 | Interrupted benchmark exported as complete | Condition change cancels and erases the export | [LS2 §4; LS3 §8] |
| 26 | "No camera jumps" rejects intended cuts | Director card declares cuts; motion checked within shots | [LS2 §4] |
| 27 | Metadata valid but unattached | Explicit containerField; runtime warnings reject; read the live node | [GEAR §8; IFC] |
| 28 | Correct rate, wrong phase (half-pitch collision) | Check state, not only derivatives | [GEAR §5, §9] |
| 29 | Sampled gap reported as guaranteed | Certified lower bound; unresolved fails | [GEAR §4] |
| 30 | Loading overlay made an empty frame look full | Disable splash, exclude status strip; camera-negative control | [BREAK] |
| 31 | Duplicate paid call hid under the cap | Separate duplicate-key and over-cap fixtures | [BREAK] |
| 32 | Count passed while identity was wrong | Match identities, not counts | [BREAK] |
| 33 | Missing value became zero | Null semantics end to end; never COALESCE to 0 | [CITY] |
| 34 | Default Decimal context rounded > 28 digits | Explicit local context; long-tail fixture | [CITY] |
| 35 | Rejection caught but its insertion kept | Savepoint rollback; inject failure after insertion | [IFC] |
| 36 | Stable GUIDs but bytes changed (set order) | Sort; compare bytes on regeneration | [IFC] |
| 37 | Quantisation used as tolerance | Spatial search + one-to-one match within a tolerance | [IFC] |
| 38 | Load "ended cleanly" at 88.6% of a table | Rename output only after the whole pipeline succeeds and counts reconcile | [WD] |
| 39 | Expected total double-counted | Two-route rule: show the derivation and a second route | [WD] |
| 40 | "Byte for byte" claimed after comparing sizes only | Say what was compared | [WD] |
| 41 | 22 agents emptied the usage window | ≤ 3 agents; partial results on disk | [LEC 10] |
| 42 | Validator pins spread over five fork commits | One tagged pin for the family | [MC §1; DEF decision 5] |
| 43 | A smoke test run with `-I` could not import its own package | Run patch smoke tests as their README says (`-E -s`); the result was `error`, correctly not `fail` | [KIT, 3 Nov] |
| 44 | Rebuild on another platform: PNG bytes and last-bit floats differ while content is identical | Cross-platform reproduction compares decoded pixels and tolerance-checked floats; byte identity is claimed only on the original platform | [CAT §Patch results] |
| 45 | A geometry witness's own positive control fails on another platform: the kernel split quads along the other diagonal | Compare surfaces (or canonicalise triangulation), not triangle lists; run every fold-back's smoke on a second platform before promotion | [KIT runs/foldbacks-20261104/report.json] |
| 46 | A delivery receipt hashed a truncated zip | Admission opens every archive (`unzip -t`) before hashing (law 24) | [REVIEW-loom2] |
| 47 | Stale "valid X3D" badge shown on changed bytes | Rebind claims to current bytes or show them as historical (CLAIM-SCOPE) | [REVIEW-loom2 L2] |
| 48 | Arrival witness compared a stale expected pose with a stale observed pose | Intent serial + an applied frame after the intent + observed pose within tolerance (ARRIVAL-EPOCH) | [REVIEW-loom2 L1] |
| 49 | Textures resolved against the HTML page, not the scene URL: 39 silently missing | Resolve against the scene URL; observe actual load state (URL-SCOPE, DEPENDENCY-CLOSURE) | [REVIEW-loom2 L4] |
| 50 | `log(sqrt(1+b²)−b)` cancels to log(0) at astronomical zoom | Stable algebra (−asinh b); finite-path and endpoint tests (ZOOM-RANGE) | [REVIEW-loom2 L5] |
| 51 | Invariants held while the simulated event went the wrong way | A witness of the promised event (law 21) | [REVIEW-scientific S1] |
| 52 | Good eigenvalues, non-orthogonal degenerate modes | Orthogonality / subspace witness (law 22) | [REVIEW-scientific S2] |
| 53 | 8-bit display encoding moved a scientific isosurface | Precision budget per question; 16-bit where thresholds matter (law 23) | [REVIEW-scientific S3] |
| 54 | Shader and CPU probe shared the wrong periodic spacing | Independent assumptions, not independent code (law 25) | [REVIEW-scientific S5] |
| 55 | Admission gate written as `assert`: red passes under `-O` (recurred in a new project) | Reuse shared acceptance code; `need()` predicates; `-O` controls | [REVIEW-scientific F1] |
| 56 | Browser evidence without a candidate digest | Bind every witness record to the candidate (law 17) | [REVIEW-scientific F3] |
| 57 | Component declared by name only; X_ITE ignores levels, so TextureProperties (Texturing 2) passed the browser | Run the fork's Meaning witness; the browser is not a validator | [REVIEW-scientific F4] |
| 58 | `python -I` dropped the builder's own directory from `sys.path` (a second time, after #43) | Launch builders with `-E -s`, or let the kit launch them; lessons that live only in prose recur | [KIT; Kerr 2 build, 4 Nov] |
| 59 | An analytic approximation (CIE colour matching) failed its declared gate in the red tail | Replace the approximation with the official dataset, checksum verified against the publisher; never widen the threshold after the run | [Kerr 2 color.py; evidence/history] |
| 60 | A local server without a cache policy let the browser test a stale stylesheet | Dev servers send `Cache-Control: no-cache`; tests reload | [Kerr 2 serve.py] |
| 61 | CSS `display` overrode the `hidden` attribute, so a loading veil dimmed every frame | `[hidden]{display:none}` for every element given a display; check computed style, not the attribute | [Kerr 2 app.css] |
| 62 | A bisection edge finder took the first noisy transition where the quantity hovers at its threshold (photon orbit ≈ disk edge), giving inner edge > outer edge | Use the exact analytic boundary to decide whether an edge exists; search only inside the valid interval; assert ordering | [Kerr 2 subring_edges; refinement gate caught it] |
| 63 | A passive variable (azimuth φ) in the adaptive error norm collapsed the step near a coordinate singularity (the spin axis); rays ran out of steps | Control error only on variables that drive the dynamics; integrate passive ones without letting them set the step | [Kerr 2 trace; unresolved-ray gate caught it] |
| 64 | A browser-vs-offline witness compared a frame of the wrong view: the page was still in its unrolled mode from an earlier test, a hash navigation kept that state, and the mismatch was first read as a GPU-path bug | The page reports the view it drew (case, mode, zoom, pan, mask, loading) and the witness rejects a capture whose report differs from what the reference renders; deep links set the whole view | [Kerr 2 reconstruction, 4 Nov; C] |
| 65 | A comparison witness can pass on a dark or flat frame, which correlates with almost anything | Declare a signal floor (here: reference luminance standard deviation at least 0.02) before measuring; a view below it counts as no evidence | [Kerr 2 reconstruction; C] |
| 66 | A negative control that cannot fail proves nothing: at a mirror-symmetric view (an edge-on disk) the vertically flipped capture still correlated 0.981, so the witness could not see an orientation error there | Keep the control required to fail, and choose evidence views that make it bite (asymmetric framing); never relax the control to get a pass | [Kerr 2 reconstruction; C] |
| 67 | An initial condition borrowed from the 2D literature (Pearson's 6-cell seed) died within t = 100 in 3D: diffusion drains it in three directions | Test the seed itself in the target dimension before building on it; record its size as a parameter | [Turing Garden exploration, 4 Nov; C] |
| 68 | Noise only inside a symmetric seed let the seed's cubic symmetry echo outward as nested squares, which looked like a pattern but was an artifact | Follow the reference method's symmetry breaking (noise over the whole domain); look at slices before naming anything | [Turing Garden; C] |
| 69 | Regime names carried over from 2D (labyrinth, sponge, worms, bubbles) did not hold in 3D | A name in a caption is a claim: measure it (components, holes, Euler characteristic, curvature, activity) against thresholds declared before the build | [Turing Garden; C] |
| 70 | One witness measured two causes: the 'display quantization' check went red with the same value in every case and at 8 and 16 bits, because it also measured the mesher's non-convergence at a step | When a witness returns the same number for unrelated inputs, or does not move when its cause is removed, it is measuring something else; split it so each witness has one cause | [Turing Garden build 2; C] |
| 71 | A display precision fixed in advance failed one case (shallow gradients) and wasted bytes on the others | Choose the precision per case to meet the declared witness, record the choice in the manifest, keep the red first run in history | [Turing Garden; C] |
| 72 | X_ITE 16.5.1 has no `Browser.currentTime`; a NaN `startTime` left a TimeSensor 'active' with no events, so playback froze silently. **A repeat:** kit/templates/KICKOFF-PRE.md already listed this trap, and the build skipped reading its own kickoff | Read the kickoff's trap list before writing page code (step 1 is not optional for the operator either); use `getCurrentTime()`; refuse a non-finite start; test playback by sampling the routed field (Switch.whichChoice), not the button state | [Turing Garden; C] |
| 73 | A node outside the profile (PhysicalMaterial needs Shape level 2) loaded in X_ITE but would be refused by header-enforcing browsers | Declare every component the scene uses; the Meaning witness on the fork catches it (second occurrence after the Scientific Loom's Shaders/Texturing) | [Turing Garden acceptance; C] |
| 74 | The candidate excludes any folder named `evidence` (so the Loom's own records do not hash themselves); a study's own browser evidence, judged by a command witness, was therefore not bound by the receipt | Checkers print the sha256 of every evidence file they judge, so the witness record pins those bytes; open question 14: exclude the Loom's evidence directory by path, not by name | [x3d.STEM acceptance, 4 Nov; L, then C] |
| 75 | A helper named `tools/numbers.py` shadowed the standard library's `numbers` for every script in `tools/` (the script directory is `sys.path[0]`), and NumPy failed to import | Never name a module after a standard-library module; stemkit's tests now refuse any study tool or library module whose name is in `sys.stdlib_module_names` | [Kerr 2 close-out, 4 Nov; C] |
| 76 | Limits declared from an exploration that skipped the hardest cases: the 3D normalization limit was measured on 1s, 2p, 3d, 4f, 5g, and the first build went red on 3s and the superposition (the s-state cusp at the nucleus, coarsely sampled in a large box) | Explore the worst case before declaring a limit; when a red is resolution, show it by refinement (observed order, extrapolated value), then measure the cause on a finer check grid with the same limit and report the display-grid number; keep the red run in history | [Electron Cloud first build, 4 Nov; C] |
| 77 | A top-level `const top` in a classic page script collides with the browser's `window.top`; the script threw before anything ran | Never name page globals after window properties (top, name, status, parent, length, origin); prefer modules or a single namespace object | [Electron Cloud; C] |
| 78 | A hash change that arrived while the X3D scene was loading reached the case loader before the scene existed | Register navigation listeners only after the scene is ready, and route once more if the hash changed meanwhile; the Turing Garden page carries the same latent race | [Electron Cloud; C] |
| 79 | A witness compared a windowed estimate with a point value: audio pitch counted over 100 ms against the instantaneous frequency at the window centre; true for a slow sweep, false for an eccentric orbit that sweeps within every orbit (31 % 'error' in correct audio). The repair compared crossings with the wrong span (first to last crossing, not the window): 11 % | Compare like with like (both quantities over the same window), and where the construction allows, state the witness exactly (h = A cos Phi crosses zero Delta Phi / pi times) with a negative control that must fail | [Chirp, 4 Nov; C] |
| 80 | Picture and sound drifted 0.8 to 1.5 s apart: audio starts after decoding and the X3D browser's frame clock can lag wall time, so two clocks started 'together' are not together | Make one clock the master (in Hear mode the audio's currentTime draws the picture) and let the browser evidence compare the two clocks, not just that both run | [Chirp browser evidence; C] |
| 81 | A sign convention emptied a witness: the strain phase ran backwards, every frequency was negative, the 'above 20 Hz' set was empty | Fail closed on an empty sample (the reduction raised instead of passing vacuously); take magnitudes where the sign is a convention and say so in the code | [Chirp first build; C] |
| 82 | An initial condition that works in 2D failed on a curved 3D domain: a broken wave in a ventricle shell escaped round the apex (where the band shrinks to nothing) and annihilated itself | Seed the 3D case from the computed 2D state mapped by surface coordinates, keep the core away from degenerate geometry, and state the seeding in the manifest | [Living Heart, 4 Nov; C] |
| 83 | Frames scheduled from a time before the recording run began were silently missed (29 of 36); the builder's own count check refused to publish | Schedule frames by exact step number, after the run starts, and always check the frame count before publishing | [Living Heart; C] |
| 84 | Screenshots taken right after a viewpoint change caught X_ITE's default one-second glide | Set NavigationInfo transitionType TELEPORT (or wait for the transition) before capturing evidence | [Living Heart; C] |
| 85 | A detector with the wrong geometry: the vortex-cell marker flagged neighbours in a face's own plane instead of the two cells either side of it, which can leave gaps along a line and count one loop as two | Test a topology instrument on a case with a known answer (one ring = one loop) before trusting its counts | [Vortex Reconnection exploration, 5 Nov; C] |
| 86 | A plausible cause, tested and rejected: a ring 7 to 14 % fast was blamed on the non-periodic initial phase; making it periodic changed nothing. Two box sizes showed the real cause, the periodic images, which speed rings up (the backflow correction had the right size and the wrong sign) | Test each suspected cause by changing only that (resolution, then box size) before writing a correction; grade a correction measured this way L, not C | [Vortex Reconnection exploration; C] |
| 87 | A planned witness that the data could not support: the strand separation near reconnection (expected ~ |t - t_r|^1/2) gave exponents from 0.46 to 0.84 depending on the fitting window at this resolution | Demote it to a reported measurement rather than gate on a number that depends on the analyst's window | [Vortex Reconnection exploration; C] |
| 88 | One exception escaping an X_ITE field callback leaves the routing guard set and freezes every route in the scene (TimeSensor -> IntegerSequencer -> Switch stopped at frame 13; the callback never ran again) | Wrap every field-callback body in try/catch; test a page's routes after a deliberate throw | [X_ITE teardown F02, L2 in 16.6.1; reproduced C (L3) in 16.5.1 on the Turing Garden page, 5 Nov] |
| 89 | X_ITE's replaceWorld can leave the caller's promise pending when an internal wait rejects (loadURL never settles) | Put a time budget on every await of a world load and report non-settlement as an error | [X_ITE teardown F01, L2; not reproduced here] |
| 90 | Evidence corrupted by ordinary code habits: a JSON.stringify key allowlist deleted nested fields; a cache keyed on item count missed same-size edits; report prose said one disagreement where the data had two | Serialize with explicit recursive schemas; key caches on content revision; generate report numbers from the data | [TETH, L] |
| 91 | Valid and visible are independent in both directions: 17 of 91 'valid' scenes rendered blank, 10 invalid scenes drew something | Keep grammar, meaning and eyes as separate witnesses (law 2) and report both directions | [TETH cohort, L] |
| 92 | My own hardening script left '}););' in the vortex page: the page never ran, yet every page-trap pattern rule passed it (a page that does not parse avoids every other trap). The browser evidence caught it | Page traps run `node --check` first (rule js-syntax) and fail closed without Node; every edit to page code is followed by a syntax check and a browser run | [x3d.STEM hardening, 5 Nov; C] |
| 93 | A witness passed while reading nothing relevant: page traps over the Mashtots slide show's `app/*.js` passed (6 files, 0 hits, 0 field callbacks seen), because the X_ITE driver is an inline module script in stage.html and passes its callback by name (`clock.addFieldCallback("stage", "elapsedTime", onFrame)`) | Page traps read the inline `<script>` blocks of HTML files, resolve a callback passed by name to its definition in the same source, and report `seen` (field callbacks, world loads, inline scripts); `--files` takes several globs, and the list covers every page outside vendor/ (law 36) | [MASH2; this repository, 5 Nov; C] |
| 94 | The X_ITE freeze (failure mode 88) on a second delivery, one not built under the Loom: one exception from the slide show's conductor stopped the piece for good. The clock advanced 1.5 s in 1.5 s before the throw and 0 s in 2 s after; the scene's TimeSensor stopped; a callback added afterwards was never called; seeking moved the playhead, which then stood still. The delivered feature checks and a clean console never exercise this path, and the earlier director page has the same callback | A guard in both pages, as a fold-back patch (`runs/mashtots2-20261105/foldback/stage-onframe-guard.patch`), applied to the demo copy (`projects/mashtots-slideshow`) on 5 Nov at the user's word; and committed to the source repo (`~/Projects/x3d/work/mashtots-standalones/slideshow`, eae4235). With it, the clock advanced 2.0 s in 2.0 s past the same throw, the feature checks pass 150 of 150, and page traps pass. The resilience probe belongs in every X_ITE page's evidence, not only in the Loom's own studies | [MASH2; C (L3): headless Chromium through Playwright, X_ITE 16.5.1] |
| 95 | Widening a witness's reading made a false positive: the first inline-script run flagged a module script's top-level `let frames` as shadowing `window.frames`, but a module's top-level names never reach window (the page passes 150 of 150 checks) | The window-name rule skips module code (`type="module"`, and .js files with a top-level import or export), with a two-sided form for each. Re-run the change on the six studies and both deliveries before trusting it (law 8) | [this repository, 5 Nov; C] |
| 96 | An output field that no control checked was wrong from the day it shipped: js-syntax reported line '?' on macOS for every syntax error, because Node prints the temp file's real path (/private/var/…) and the rule matched the /var/… name | Match either path; the controls now check the reported location, not only that the rule fired | [this repository, 5 Nov; C] |
| 97 | A bug kept on purpose is a control: the constellation's "MSAA 4x (diagnostic)" switch turns the stage black and back. Mean brightness went 61.4 → 3.9 → 61.7 here, and 55.2 → 1.1 → 54.6 in the delivery's run | Keep a known-bad switch beside the fix, and use it as the negative control for any brightness or eyes witness: a check that cannot see the black stage cannot vouch for the lit one (law 19) | [MASH2; reproduced here, C (L3)] |
| 98 | Evidence shipped with the code but older than it: the slide show's result file (3 Nov) says 148 of 148, while the delivered code runs 150 of 150 here (its own note says links were added after that run) | A shipped result names the hash of the code it ran against (law 17), and the receiver re-runs it rather than reading it | [MASH2; C] |
| 99 | Provenance that lives in .git did not travel: the report and README rest provenance on local commits ("the first commit is the verbatim copy; `git diff` shows every change"), and neither zip contains .git. The repos happen to be on this Mac (`~/Projects/x3d/work/mashtots-standalones/`): they carry the named commits, and their working trees match the delivery file for file, logs aside (slide show: 205 tracked files, `git diff d148f8f HEAD` = 31 files, +1245 −16). A receiver anywhere else could not check it | Ship the diff or a git bundle with the delivery. The receiver checks every provenance claim against what arrived and says where the check was possible. My first reading called the claim uncheckable before looking for the repos (law 26) | [MASH2; C, checked here against the local repos] |
| 100 | Spend and keys in the wrong place: a daily cap held in memory reset on restart, and a browser-side key mode put the key in the page (both fixed in the delivery) | Rebuild the cap at start from an append-only ledger (`.spend/spend.jsonl`; the delivery's check: two lines summing to the cap mark it reached, and a line from 2020 is ignored). The key stays on the server. Recorded mode is the default, and the demo launcher strips any key from the environment so the demo page cannot make a paid call (law 11) | [MASH2 report, L; recorded mode, 0 paid calls and the launcher checked here, C] |
| 101 | A hidden page does not run: X_ITE does not start in a hidden pane or tab, where animation frames are throttled, and the slide show's scene wait (a setInterval poll for its Clock node) has no time budget, so the page says "loading" indefinitely | Browser evidence runs in a visible or headless page. A scene wait has a budget and a message: failure mode 89's rule applies to polls as well as loadURL | [MASH2 report and README, L; the unbudgeted poll read here, L] |
| 102 | The X3D 4.0 schema gives PointSet no vertex attributes, though X_ITE accepts and draws them: valid at runtime, invalid in the standard | Carry per-point data in the Coordinate and a Color (values within [0, 1]); validate every generated scene against the XSD before the browser | [MANI; C] |
| 103 | A saved X3D moment depended on its page: the light layers' blending lived in a BlendMode the page added at run time, so the file alone drew opaque sheets (SSIM 0.74 against the live frame) | Light layers write (g / max g, max g) for standard alpha; test the artefact alone (law 37): it then redrew the live frame at 0.9987 and validated as X3D 4.0 | [MANI; C] |
| 104 | Two animation-frame loops raced: a post pass read X_ITE's canvas between a clear and a draw, so 1 frame in 8 was black | Read X_ITE's frame in a microtask queued from its own frame callback (events and draw share one callback); evidence waits for drawn frames, never for seconds | [MANI; C] |
| 105 | Synthetic change events that do not bubble left a paused page unrendered: four captures with different layers switched off were one frame (same luma to four digits) | Dispatch with bubbles; check that a capture changed when its cause changed (law 26) | [MANI; C] |
| 106 | A look parameter tuned on one mood broke the declared budget in the worst one: occlusion tuned on Reverie put Catharsis 2.1 % too dark | Tune on the worst case first (law 28); the limit stays | [MANI; C] |
| 107 | Replace-all edits hit a second occurrence twice in one night: the kit's cmd_traps gained an undefined name, and the page's X3D export an undefined variable; library tests and the live view passed | Replace exactly one occurrence and assert the count; test the commands and the export paths themselves (cli_controls; the evidence run's Save X3D) | [this repository and MANI, 6 Nov; C] |
| 108 | Witnesses that measured their sampling or their renderer: curve agreement by vertex distance (9.7e-3, against 9.6e-9 measured to segments); resilience by frames per wall-clock second in software GL | Measure curves to segments; judge resilience by the clocks advancing, not by a frame rate | [MANI; C] |
| 109 | One file, two renderers, different night skies: X_ITE blends ColorInterpolator keys in HSV as the standard says, a three.js reader in RGB, so the colours between sparse keys differ | Densify the keys until the HSV and RGB midpoints agree; trap color-keys-sparse (flags the v1 sky, not the v3 sky) | [RB1; C, X_ITE 16.5.1 + three r170] |
| 110 | A light faded to intensity 0 kept its ambient term to the end, then vanished: X_ITE drops a light at 0 and its ambient term ignores intensity | Drive ambientIntensity down with intensity; trap xite-light-zero-pop (4 lights in v1, 0 in v3) | [RB1; C, X_ITE 16.5.1] |
| 111 | A fully transparent shape cast a shadow: X_ITE draws it into the shadow map | castShadow='false' on shapes that reach transparency 1; trap xite-transparent-shadow | [RB1; C, X_ITE 16.5.1] |
| 112 | The picture jumped at every loop: interpolators on a looping clock ended away from their first values | Close the loop, or hide the reset in the dark and say so on the card; trap loop-seam (3 in v1; in v3 only the ray reset, which sits in the fade) | [RB1; C] |
| 113 | A 4K still button rendered the image and saved nothing: the hosting sandbox ignores a link's download attribute (both rebuilds) | Use the host's save capability on the viewer's click and handle a refusal; page trap anchor-download-hosted (also flags x3d.platformer's replay save, which works on its own site) | [RB1; RB2; C] |
| 114 | X_ITE's tone mapping, a canvas option, crushed the Phong darks; ACES there hid clipped cloth instead of fixing it | Reference view with toneMapping NONE; fix clipping in the light values (88.4 % clipped to 0 %) | [RB1; C, X_ITE 16.5.1] |
| 115 | Cloth outline overlap between renderers fell to 0.855 and 0.778 at two beats with the geometry identical: X_ITE blends translucency in display space, three in linear (black at transparency 0.5: about 128 against 188) | Compare shapes with translucent parts hidden (0.99 at both beats); never compare pixels across renderers (law 38) | [RB1; C] |
| 116 | X_ITE drew black on a hosted page: the policy blocked its CDN stylesheet and X_ITE keeps its surface hidden until that loads | Inline the stylesheet into the canvas's shadow root and unhide the surface; test under the host's policy (law 40) | [RB1; C, X_ITE 16.5.1] |
| 117 | After switching renderers and back, the view stayed black: the old canvas's context-lost event flagged the new one | A context handler acts only on its own current canvas | [RB1; C] |
| 118 | Tearing X_ITE down to free memory threw inside X_ITE ("reading '0'" of null) | Keep it alive and hidden after first use (beginUpdate/endUpdate) | [RB1; C, X_ITE 16.5.1] |
| 119 | Ambient occlusion turned translucent relief, points and lines into false dark geometry | Exclude translucent shapes, points, lines and decoration from the normal/depth pass | [RB2; as reported] |
| 120 | Depth attachments kept their old size after a resize (quality change, phone, 4K export) | Recreate them on every size change, rebind every sampler, check framebuffer completeness afterwards; set the export's 16:9 projection before resizing targets; restore in finally | [RB2; as reported] |
| 121 | We reported an X_ITE bug that was ours (shared Coordinate) | Minimal repro before any upstream claim (law 26); the claim is retracted in the record | [RB1; C] |
| 122 | A study's review was made on a procedural stand-in: the host blocked the real image without a message | Every fallback announces itself (law 40) | [PCS; as reported] |
| 123 | The page described a draped cloth simulation while the live scene drew a flat cloth: the drape lives in the generator and the stills only | Say which parts the live file holds and which only the stills show (CLAIM-SCOPE) | [RB2; C, read from the X3D] |
| 124 | A stepped engine was judged against the continuum answer and looked wrong by 1/2 g h t (0.0204 m after 1 s of free fall) | Judge against the scheme's own discrete solution (here within 1.5e-6 m) and state the continuum gap as a known number | [PXB; C] |
| 125 | PhysX applies restitution to the pre-solver velocity, which already holds this step's g h: below minBounceSpeed of about e g h / (1 - e) a ball hops forever (a limit cycle) | Raise the threshold to 2 e g h / (1 - e) and put the raised value in the loss report; test rebound = e (v + g h) to 1e-7 | [PXB; C] |
| 126 | The default 2 cm contact offset hid a 5 mm wall from a 5 m/s marble, so a CCD-on test alone proved nothing | Size contact offsets per shape (25 % of the smallest dimension); keep CCD off as a control that must tunnel (10 of 40 start phases) and CCD on as the run that never does | [PXB; C] |
| 127 | "Disabled" was taken for "off": X_ITE's Bullet stepped once after `loadURL()` resolved (y 0.32 to 0.319974 to 0.319989) | Prove the old engine off in every browser (0 position events in 120 frames, a write while disabled sticks, re-enabling resumes from it); load with `createX3DFromURL`, disable, `replaceWorld`, which leaks none (law 41) | [PXB; C] |
| 128 | `Object.assign` of functions onto the page's state overwrote the page's own methods (hit twice) | `expose()` guards names already in use; test that a second page cannot replace the first's methods | [PXB; C] |
| 129 | The import sanitiser snapped authored rotations (-8 and -15 degrees): the machine ran 20 of 20 in Node and 0 of 20 in the browser | When Node and a browser disagree, compare the reader's model with the Node model first (zero differences at 1e-5), then the physics | [PXB; C] |
| 130 | WebKit's `createX3DFromString` stalls without a word | A watchdog with one retry; report the retries in the evidence | [PXB; C] |
| 131 | Scene clocks ran ahead while physics lagged under load, and 60 fps was claimed before it was measured (52.6 median) | Clocks follow physics when it lags; the record states the measured number, not the target | [PXB; C] |
| 132 | Authored fields the engine cannot honour were dropped in silence (11 ODE-only fields, including errorCorrection and constantForceMix) | A loss report lists every one; a test that its count equals the authored fields (law 40) | [PXB; C] |
| 133 | Smoke thresholds failed under load (3 of 33) and the numbers moved with the machine, with no record of who accepted them | Waivers: owner, date, reason, observed and limit, capped by the profile (law 43); re-run unloaded | [PXB; C] |
| 134 | H-Anim `llimit` and `ulimit` default to `0 0 0`; reading equal limits as locked froze every figure that authors no limits | Equal limits are a free axis, a range under 0.01 rad is locked, anything else is limited; found by comparing the reader's model with the Node model | [PXB; C] |
| 135 | An unbounded input sent an articulation to NaN, three ways: a teleport that moved only the root (NaN within 4 steps), spherical limits beyond 1.9 rad, links crushed under 331 stones | Update every link on a teleport; cap limits, joint speed (40 rad/s) and push-out speed (3 m/s); list each cap in the loss report; detect NaN and reset | [PXB; C] |
| 136 | A safety score built on contact impulse over segment mass read 141 m/s on a 7.5 kg thigh: in an articulation one contact stops the whole body | Score what the segment itself felt (its own change of velocity); unit-test a pulse of known value (50 g for 36 ms reads 619 against 636 by hand, -3 %) | [PXB; C] |
| 137 | A closed-form self-check of a ride missed by 34 % (Gravitron, 2.97 against 2.22 rad/s) and the pull was to tune friction until it matched | Log the gap with its probable cause (a limp body is not a point mass; PhysX friction approximates Coulomb's law) and give it no pass until a limit was declared (law 43) | [PXB; C] |
| 138 | Peaks read at frame-rate sampling depend on the spacing: a headless Firefox ran at a third of real time and read a head score of 92 where WebKit read 1,189 | Log the sample spacing with every peak; sample per step in the worker | [PXB; C] |
| 139 | A source edit during a browser run reloaded the page and cost the run its state (`window.__rag` lost) | Run probes against a production build or a frozen tree; re-run, and keep the clean one | [PXB; C] |
| 140 | X_ITE's RigidBodyPhysics differs from the standard in ways scenes silently depend on (variable step, ignored inertia, no UniversalJoint or MotorJoint, CollisionSensor ignoring `enabled`, others) | The list is in PHYSICS-PLAYBOOK.md section 6; a scene that must agree across engines does not lean on any of them | [PXB; C, X_ITE 16.7.0] |
| 141 | The XSD passed while the semantic validator found 5 errors per scene: Metadata nodes without `containerField="metadata"` | Grammar and Meaning both run on every generated scene; this answers open question 4 with a measurement | [MJB; C] |
| 142 | An engine was cross-checked against itself: native MuJoCo replayed the browser WASM trials to 6e-16 rad, which checks the build, not the model | Label it a build check; the model needs an independent reference (a closed form, or another engine) | [MJB; C] |
| 143 | A notices file missed a bundled dependency tree (JSZip), and the licence stayed blocked until the owner confirmed rights to two archives and the generated code | Generate notices from the lock file and test that every bundled package appears; record the owner's rights confirmation | [MJB; C] |
| 144 | Behaviour ran on browser defaults that cannot run the page: headless Chromium's shell has no WebGL, and a Firefox context with no locale has `navigator.language` undefined (X_ITE throws "invalid language tag") | Use the `chromium` channel and set a locale; the witness says which browser build it used | [MJB; C] |
| 145 | Parsers in the validator server use lxml defaults, so internal entities resolve | Open follow-up: parse with entity resolution off; add the threat check (Gate 0 measured 16 defences holding and 3 gaps) | [MJB; C] |
| 146 | A fold-back was assumed while two physics threads built bridges with no PR, no remote and no use of the Loom's method; the owner and the Loom's model both believed the lessons had returned | A thread's last step is its PR to `hagopjay/x3d.loom` (step 9); the PR opens with the numbers claimed, checked against upstream that day | [this PR; C] |
| 147 | A private consolidation was treated as the Loom while cloud threads kept editing upstream (private v1 at law 37 and failure mode 108, upstream at law 40 and 123) | Fetch upstream and number from it just before any PR; a local copy says its base commit | [this PR; C] |
| 148 | A check that passes for a wrong implementation: "collisions conserve energy to 1.3e-15" read 1.33e-15 with the buggy rule, 2.0e-15 with the fixed rule and 0 with no collisions at all | Run the check against the wrong implementation as a control; if it still passes it is not a check (law 44). Use a test the bug breaks: a head-on elastic pair must swap velocities, an oblique one must leave the tangential part and make the outgoing velocities perpendicular (dot -2e-16) | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 149 | A quantity was read after the step that enforces it: a bead's constraint drift "< 2e-16" was measured after the projection (pre-projection violation 2.4e-2 at 1 substep, 2.9e-6 at 100) | Read the violation before the projection, or say which state was read | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 150 | A second "reference" was the first one again: with closed top and bottom the flux check is an identity of the same arrays as the divergence (difference 7e-16); a bead control had no passing twin | List what each reference could not see; give a control its passing twin (100 substeps keep 93% of the energy) | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 151 | The only exact collision test was head-on and axis-aligned, so a wrong normal or a missing tangential term would pass; `np.linalg.norm` and `@` differ from scalar arithmetic by 1 ulp and 19 of 300 oblique pairs had differing per-step hashes | Add an oblique exact reference and write the sqrt out when a trace must replay bit for bit | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 152 | A receipt number was read at the wrong state: MuJoCo's RK4 energy drift read 3.4e-6 because the stored energy is the last stage (8.86e-9 after `mj_forward`); a stability scan's 1.2e6 was the value at the first crossing of 1e6, not after 3 s (1e30) | Say when a number was read and what the engine had computed by then; call the forward pass before reading derived energies | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 153 | A chaos horizon was credited to the integrator: both were accurate (RK4 9.4e-9 m at 3 s) and the 9.8 s horizon came from a 1e-9 model difference (body inertia) amplified at about 2 per second | Horizon = ln(tolerance / initial difference) / lambda (8.9 s for 1e-9, 5.5 s for 1e-6, 2.0 s for 1e-3 here); run a twin shifted by the difference before blaming a method | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 154 | An explanation was written without a test that could tell it from the alternatives: "the wave outruns a cell per step" (c dt/dx was 0.83; the cause is the checkerboard mode, 0.7082), a float line that agreed with theory by two errors cancelling, a cannonball that "grows without limit" (it saturates near 12.9 times E0) | Grade an explanation Suspected until an experiment separates it from the next-best one; state what would refute it | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 155 | A control's caption disagreed with the code: the spatial-hash control cell was 0.30 of a ball diameter, the page said 0.6 (2997 missed pairs against 1057) | Generate captions and numbers from the variables the code ran with | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 156 | "Limits written before the run" could not be shown: `limit` and `declared_limit` are written by the same run from the same value | Commit the limits file first; the runner refuses to start if it differs from its commit and writes the commit and the file's sha256 into every record (x3d.demo v6 `tmp6.py`). Git history can still be rewritten by its owner; say so. Open: let the physics witness carry and check `limits.commit` | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 157 | Two of eleven mutation controls were vacuous: they scaled a reference whose limit was 0 (pairs missed, mismatches), changed nothing, and the checker rightly accepted the record | Choose a reference with a nonzero limit and require each control to change the record; report caught of total (11 of 11 after the fix) | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 158 | Two written predictions about cloth tunnelling were falsified (rule 1, written before the first grid: no crossings under 0.9 thickness of motion per substep, some over 2; the safe half held but a thickness of 0.2 spacing with 4 substeps and one of 0.1 with 16 moved over 2 thicknesses per substep and crossed nothing. Rule 2 broke at 0.72 thickness with 7 crossings) | Write the prediction down before the grid, keep it in the notes when it fails, never wire it into the witness as a reference, and claim no replacement rule | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 159 | An integrator was judged from one measurement: symplectic Euler shows order 2.0 at T = 2 pi (a full period) and 1.0 at T = 1; velocity Verlet's energy error is bounded (0.74% over 50 orbits) while its position after 5 orbits is 0.61 off against 0.0022 for RK4 (283 times) | Fit the order at two end times that are not both multiples of the period; report energy and position error as two numbers | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |
| 160 | A spatial structure was verified by speed: sorting a sweep-and-prune list by centre instead of left edge missed 905 pairs in 180 frames; shrinking every BVH node box by 0.02 lost 2466 hits in 1000 queries; neither fails a timing | Check set equality with brute force on every frame or query, count tests (not seconds), and keep the wrong-structure variant as the control | [x3d.demo PRs #19 to #25, v5/ERRATA-v1-v4.md; C] |

---

## 9. Planned, not yet run (roadmap)

Scope decision, 3 Nov: v1 defines what has run. Everything below is defined in the sources but has not run, and is S or L until witnessed.

### 9.1 The Gobbler and the Village Voice [DEF §Agent architecture]
The Gobbler is the agent that operates the Loom: it plans, weaves, calls the witnesses and answers the village. It is simulated today as the ten demiurge wing roles. Inside it the Village Voice talks with villagers and writes structured, schema-checked **petitions** (graded S). The Gobbler answers (weave, defer, decline), and a woven petition adds one layer, never a replacement. The validator role is always code, never a model; the curator is always HagopJay. Decided 1 Nov: the Voice runs on a strong hosted model behind a response cache keyed by prompt hash, plays from a recorded tape inside a published page, and goes live later.

### 9.2 Before the music (M1 to M12) and Loomsong full production [DEF §Before the music; SPEC]
Score card loader; audio synthesised from the score; Ear, Score and Sync witnesses; a sound probe in X_ITE under the host copy; one clock; camera grammar as rules; motion and flash safety; a real-GPU lane (yes given, the existing spot L4, [cost withheld] total cap for API and GPU); Loom Receipt v1 for music; one fork pin; style and budget cards. Loomsong Study 01 to v4 implemented a local subset (C, §7.3). Full production remains: two pieces, splat worlds, animated stills, a Blender film.

### 9.3 Gobblering [SPEC §Gobblering]
The improvement loop on a project: a champion, four variants changing one to three knobs, a witness veto, blind pairwise model votes in both orders (a win needs 2 of 3 judges in both orders), and **his pick overrides and is a gold label**. Stop after three rounds without a win or five since he last looked. Numeric judge votes are allowed here only as a labelled experiment, never as a release gate (decision, 3 Nov).

### 9.4 Video to world: the 8-second stage [DEF §Video to world]
A generated video as a card, then frames, masks and depth, poses, Gaussian splats (gsplat), clean-up, X3D 4.1 GaussianSplats. New witnesses: Pose (reject a video before any GPU time) and Fidelity (PSNR/SSIM/LPIPS on held-out frames only, GPU named). Each video generation and any GPU needs his yes.

### 9.5 Infrastructure

- **X_ITE fixture catalogue** from the teardown [XTD §7]: EVT01 to EVT03 (event order, callback mutation, an exception mid-dispatch; EVT03 done here as failure mode 88), LOAD01 and LOAD02 (world replacement and failed loads), OWN01 (resource lifetimes), REND01, SHDR01, GS01 and GS02 (Gaussian splats), PROTO01, INPUT01. Each with a stable ID, hashed assets, expected observations and cleanup, reported at L3.
- Loom Receipt v1 as a MemoryRecord; one way into the graph (overview, query, traverse, how_built, 32 KB caps) [DEF §Knowledge graph; BLUE §3].
- x3dprov 0.2 with C2PA-shaped signing [DEF gap 11].
- LangGraph runs of the Gobbler's roles and a BigQuery spine [DEF §Toolchain].
- Dependency-aware witness invalidation, replacing today's conservative "any change invalidates all" [LS1 §12; LS2 §2].
- A PROV-O / OpenLineage adapter with conformance tests before claiming conformance [CITY].

### 9.6 x3d.STEM
The first scientific delivery arrived on 4 Nov; the direction, project ideas, fidelity tiers and wow factors are in [X3D-STEM.md](X3D-STEM.md). Decided 4 Nov: a new repo `x3d.STEM`, all four audiences (leaning researchers, never excluding K-12), and three fidelity tiers (any browser, streamed GPU workstation, offline hero renders) from the same verified cases.

---

## 10. Open questions (for HagopJay)

1. **Promote the five fold-back patches?** Four pass `loom foldback` here. Applying them to x3d.onto, the fork or x3d.ML is a PR into your repos, so it waits for your word, and those repos are not checked out on this Mac. Which first? Break-the-Loom's own table suggests Traps and shared acceptance code [BREAK].
2. **The IFC bridge fold-back fails its positive control on this Mac** (triangulation differs by platform, §7.4). Fix the witness upstream of promotion (surface comparison), or pin the platform in its profile?
3. **The family pin.** Local x3d_mcp is at fa0b389 on `fix/physics-findings` (17 Oct), not `loom-pin-2026-11-01` (decision 5, 1 Nov). Has the tag been created, and should every receipt be re-scored on it [DEF M11]?
4. **The metadata-containerfield warning** fires on Break-the-Loom controls 09 and 12. Should the projects agent confirm it in X_ITE (is a `MetadataSet` directly under `Shape` attached), and if so raise it to an error rule? New evidence (13 Nov, failure mode 141): the MuJoCo bridge's `x3d_mcp` semantic validator reported it as 5 errors per scene while the XSD passed.
5. **Ear thresholds.** −14 ±1 LUFS (spec) or −18 to −12 (local study, enforced)? v1 keeps both, tied to their profiles, until you choose a production profile.
6. **The C/L/S scale has no "Contested" and no "Question".** Only the Shroud ledger uses those [DEF §Grades]. Add them to the Loom?
7. **Where does stumping's golden-examples log live**, and should stump runs write Loom receipts [STUMP §Practical playbook]?
8. **Two FACTS sections named P** will collide on merge; rename one to P2 [DEF gap 12].
9. **x3d.ML main still serves a private build graph** with internal identifiers: remove, or leave [DEF gap 13]?
10. **The 33 drafted upstream PRs**: when to "send" the first three (304 tests passing together) [MC §9]?
11. **The Scientific Loom governance patch** (sha256 `5e0aac32…`, 4 files, 8 tests) was not delivered. Upload it when found; `kit/loomkit/sci.py` is a reconstruction until then.
12. **Create `hagopjay/x3d.STEM`** (this Mac's account cannot create repos under hagopjay); then the Scientific Loom, `sci.py`, the profile and X3D-STEM.md can move there by PR.
13. **Send the hardening patch to the Scientific Loom's next pass?** It fixes the component declarations and four of the seven `assert` gates; candidate binding for browser evidence still needs their harness.
14. **Exclude the Loom's evidence directory by path, not by name?** Today any folder called `evidence` is outside the candidate, so a project's own evidence is unbound unless a witness pins its hashes (failure mode 74). Changing the rule changes the candidate hash of every project that ships an `evidence/` folder, including past runs, so it is a versioned decision (loomkit 1.1), not a quiet fix.
15. ~~A waiver status (law 43) is new to the Loom.~~ **Decided 13 Nov:** physics profiles only, for now. The owner is undecided about the concept, and prefers that, if it proves wrong, it is noted here as a false positive rather than deleted. Today's statuses are pass, fail, deferred, not_applicable, blocked and error; the waiver cap lives in the physics witness's coverage and binds no other profile.
16. ~~The three PhysX waivers are reconstructed~~ **Answered 13 Nov:** the owner owns all three. They were still reconstructed from the marble thread's note ("user accepted") by `x3d.physics/tools/physx_run_record.py`.
17. **Cross-machine determinism** is the one claim every record leaves `visible_not_run`. Which second machine, and who runs the replay?
18. **MuJoCo has no run record yet.** Its phase-1 checkpoint replay (`mj_getState`) is planned; until it lands the physics witness cannot judge a MuJoCo run. Hold the MuJoCo profile until then, or accept a tolerance-style replay row (`max_abs_diff` against a limit) in `loom.physics-run/2`?

## 11. Decisions

| Date | Decision | His words or choice | Source |
|---|---|---|---|
| 1 Nov 22:17Z | Village Voice model | "use a good [hosted model] for the voice and make sure to cache a lot and to re-use instead of fresh calls" | [DEF §Decisions 1] |
| 1 Nov | Where the Voice runs | "default whichever is easiest" → recorded tape in the page | [DEF 2] |
| 1 Nov | Home of lineage | "i guess it was in ML the whole time" → x3dprov stays in x3d.ML | [DEF 3] |
| 1 Nov | Music audio | Synthesise both from the score at a *Thriller*-grade master | [DEF 4] |
| 1 Nov | One fork pin | "yes fork" → tag loom-pin-2026-11-01 on fork main | [DEF 5] |
| 1 Nov | Real GPU | Yes: the existing spot L4, [cost withheld] total cap for API and GPU together | [DEF 6] |
| 1 Nov | DSPy in the music build | Longer-term; log judge calls DSPy-ready | [DEF 7] |
| 3 Nov | Grade scale | Keep C/L/S, with a mapping to Measured / Established / Estimate / Conjecture | This consolidation |
| 3 Nov | Model judges | Flags only in a release; numbers only in labelled experiments | This consolidation |
| 3 Nov | Scope of v1 | Method core plus a "Planned, not yet run" roadmap | This consolidation |
| 3 Nov | Stumping | A Loom stage (the attack step); the Wikipedia and MuJoCo docs are context only | This consolidation |
| 3 Nov | PR patches | Every project zip's PR patch is the record of what the Loom taught it (user's note); verified for 5 projects | This consolidation |
| 4 Nov | Missing science governance patch | Reconstruct now (labelled L); compare against the original by sha256 if it arrives | This consolidation |
| 4 Nov | x3d.STEM audience | All four (researchers, university, museum, K-12), leaning researchers, "dont want to exclude elementary either" | User, 4 Nov |
| 4 Nov | x3d.STEM home | New repo x3d.STEM | User, 4 Nov |
| 4 Nov | Fidelity target | All three tiers: any browser, streamed GPU workstation, offline hero renders | User, 4 Nov |
| 12 to 13 Nov | Tolerance over precision in the physics bridges | "some error and sloppiness tolerance": state tolerances, log mismatches, no exactness gates; a smoke run of 30 of 33 under load was accepted. The Loom records such excursions as waivers (law 43) | User, relayed in the ragdoll notes [PXB] |
| 12 Nov | Ragdoll content | An "opioid" character was declined because it would mock real addiction; the crash-test dummy and a cartoon person stay, with no gore | The marble-machine thread [PXB] |
| 13 Nov | Physics learnings continue in the Loom | "ensure they continue and build upon themselves in x3d.loom", then "create the most thorough gh PR as well as including all the relevant docs and information collected, in toto" | User, 13 Nov |
| 13 Nov | Waivers are physics-only for now | "physics-only for now, i prefer to note it as a false positive in future than just delete it"; "i own the three" | User, 13 Nov |
