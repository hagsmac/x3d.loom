# A second model's re-render of the Site Atlas, audited (6 Nov)

**What arrived.** Another model took the private Site Atlas page and its 14 receipted X3D Site scenes and returned a single 2.2 MB HTML file. The file re-renders those scenes in three.js r170 and adds a 4K still export. The look is much better, and the owner said so: "there is always room for improvement, and with loom it gets documented."

This record is that documentation. The remix itself is not committed here, because it is the owner's file.

**How it was audited.** Three independent audits read the file:

- **Data-true:** every drawn atom, bond, label and tube, compared against our X3D scenes and against PDB model 1.
- **Render and look:** headless Chromium, all 14 structures at desktop and phone width, compared with our page.
- **Provenance and claims:** every sentence and number on the page, plus a leak sweep and a licence check.

A separate skeptic then tried to reproduce every finding. Three findings were refuted or narrowed, and the corrected wording is used below.

**Conditions.** Every measurement was taken on software GL with all network requests blocked. The remix made no network requests at all.

## The data survived intact (C)

- **Atoms.** The remix draws exactly our 554 atoms in all 14 structures: none added, none dropped and none moved. The deviation is 0.000 Å from our X3D and from PDB model 1. The only transform is one rigid shift that puts the first zinc at the origin (scale 1, no rotation).
- **Distances.** All 122 printed distances equal the distances recomputed from the PDB: two decimals in the 3D labels, three in the cards.
- **Glow.** Exactly the 115 bonds under 2.5 Å glow, and the 7 longer contacts are drawn dark. This is our rule, with our radii.
- **Hard cases.** These are shown truthfully:
  - 6DNH C302 shows 2 donors and C303 shows 3, and neither gets a cage.
  - 2JVX draws only its four model-1 donors.
  - 4AV1's ND1 donors are named.
- **Census.** All 32 census rows are unchanged.

Tables: [per_structure.csv](per_structure.csv), [per_bond.csv](per_bond.csv), [per_site.csv](per_site.csv).

## What it does better (to fold back)

| # | Gain | Grade | In X3D / X_ITE? |
|---|---|---|---|
| 1 | Physically based materials, an environment map, filmic tone mapping, and three-light key, fill and rim lighting. Spheres and tubes read as glossy solids, where ours read as flat Phong | C | Partly. PhysicalMaterial is in X3D 4.0, and X_ITE takes tone mapping and exposure as browser options. Environment reflections need EnvironmentLight from X3D 4.1 |
| 2 | Smoother, opaque, darker backbone tubes (16 radial segments, navy, clearcoat). Ours are 35 % transparent in a saturated blue that dominates the frame | S | Yes: a 16 to 24 point crossSection, a darker baseColor, transparency of about 0.15 or less |
| 3 | Label cards name their donor ("CYS 159 · SG 2.30 Å"), keep a constant size, and have a leader line. Ours print only the length, and atoms cut through them | C | Mostly. Use a two-line Text in a Billboard with a dark backing quad, and ScreenGroup for constant size. Labels that are never occluded need X_ITE's non-standard depth handling |
| 4 | A coordination tetrahedron over the selected site, built from the true donor positions | C | Yes: a transparent IndexedFaceSet over the donor coordinates |
| 5 | A per-site card: model-1 distances to three decimals against the census windows, a window bar for each donor, and a 1 Å scale bar | C | Page HTML only |
| 6 | It stands alone (law 37): one file, with fonts embedded, no network, and no eval under a strict script policy. Our page breaks when served bare: no charset (Å turns into mojibake) and no viewport | C | Page template: declare the charset and viewport ourselves |
| 7 | Scope captions: "Camera motion is presentation", "cage faces are geometric guides", "LIGHTING & ATOM RADII ARE ILLUSTRATIVE" | C | Yes, as captions and page text |
| 8 | Ambient occlusion for depth | C | Not live in X_ITE 16.7.0. Only possible as a baked occlusion texture or vertex colours |

## What it got wrong

| # | Defect | Grade | Severity |
|---|---|---|---|
| 1 | **Zinc is drawn with the carbon material.** The data spells the element "Zn" but the renderer looks it up as "ZN", so all 32 zinc spheres get carbon's slate colour and low metalness. In the 4K still, the zinc is told apart only by its size and its tag | C | high |
| 2 | **The provenance panel says "Viewer: X_ITE 16.7.0, served from this page"**, which is false: X_ITE never loads in this edition. Nowhere does the page say that the view and the still are a three.js re-render. Every validity statement it shows ("14 of 14 valid", "Traps: pass", the eyes reading) is about X3D drawn by X_ITE. The view actually on screen went through no witness (law 2) | C | high |
| 3 | **The 4K export drops the verdict.** A still of a red site (6DNH C302, 6NZL A202) looks like a pass. The page's own principle says "A flag remains visible" (law 37: an export that stands alone is tested alone) | C | high |
| 4 | **The page grades itself:** "[ C ] Measured geometry" and "An atlas with receipts". No witness ever read this page, and it has no receipt of its own (laws 5, 6, 17) | L | medium |
| 5 | **It cites the superseded scenes receipt fc37e514b2a7**, and its "sourceSha256" values are the hashes of our DOCTYPE-stripped viewer copies, not of the receipted candidate. The source link calls them "Deposited X3D scene", but we generated those scenes; they were not deposited | C | medium |
| 6 | **The cage overstates two sites.** At 6DNH C301 and 6FUW C201, two of the four cage vertices are contacts of 2.5 Å or more that the glow rule draws dark. A teal tetrahedron then asserts a four-coordinate site that the bonds and both red verdicts deny | C | medium |
| 7 | **Cards on red structures misattribute the reason.** 14 of 23 such cards print a reason that names another site, without saying "first red at". For example, 1AAY A202 is inside every window but shows A201's His129 reason | C | medium |
| 8 | **Glow is no longer only a data event.** Screen-wide bloom is on by default: with every coordination bond hidden, 75 to 91 % of the halo remains. A warm rim light puts orange glints on the tube edges | C | low |
| 9 | **The camera is backed off to 1.14 times our distance after our occlusion scoring ran.** In 2JVX this puts a tube across the top of the frame | C | medium |
| 10 | **Label cards can cover the donor they name** (a 110 px card offset by 49 px). The "Zn²⁺" tag sits inside the zinc disc, and the charge is an assumption, not deposited data | C | low |
| 11 | **Text and controls are too small for comfortable reading.** Much of the text is 9 px or smaller at desktop and 6 to 8 px at phone, many greys fall below 4.5:1 contrast, and phone touch targets are under 24 px | C | medium |
| 12 | **Radii are not declared on the live page.** "Space filling" uses invented radii (C 1.25, N 1.15, S 1.35 Å; van der Waals is about 1.70, 1.55 and 1.80) | C | low |
| 13 | **It cannot be rebuilt.** The converter, the bundle step and the font and library sources are not shipped. The gains came back as a 2.2 MB replacement rather than small fold-backs (laws 1, 4, 20) | L | medium |

**Clean areas:**

- The leak sweep found no personal, lab, vendor or cloud names, no private links and no local paths.
- The file contains no eval and no remote fetch.
- three.js is MIT, and its notice is included.
- The fonts are PT Sans and Ubuntu Mono, under open font licences.

## Defects of ours it exposed

- **The re-issued scenes receipt was incomplete.** Receipt a6092f4eb0f5 dropped the eyes render log from its outputs and had no back-link, so the old id fc37e514b2a7 that the remix cites could not be traced.
  - The superseded receipt is now kept as `runs/zinc-scenes-20261106/receipt-fc37e514b2a7.json`.
  - The scenes receipt is re-issued as **2674de4d55a0**, with the render log in its outputs and `prev` pointing at the old one.
- **The data-true witness misquoted the Loom.** `zinc_scene_truth.py` called "no visual event without a data event" law 21, but law 21 is "Invariants admit; they do not confirm intent". The phrase is the study's own data-true rule, not a numbered law. The docstring is corrected. The copy inside the candidate keeps the wording it ran with.
- **Our witness never checks colour.** It checks positions, so a zinc-drawn-as-carbon bug would pass it. To add: an atom-colour check, and a check that cage vertices are exactly the glowing donors.
- **Our scenes give every zinc a constant emissive glow,** the same class of non-data glow as the remix's bloom. Drop it or declare it.
- **Our camera rule misses near tubes.** It ignores occluders within 0.3 Å of the camera plane, and both pages show a near-camera nucleic tube as a wedge in 1UBD C501.
- **Our phone view has an overlap.** The legend covers a distance label at phone width.

## The lesson for the Loom (graded L, proposed)

A remix by another model is a new candidate, not an upgrade of the old one. It inherits no receipt, and its claims enter as S until a witness reads its own bytes.

This one kept every number exactly and made the picture far better. But it named a viewer it does not use, cited a superseded receipt, graded itself C, and exported stills that drop the verdict. Its gains should come back as small fold-backs, each with the failing fixture that proves it.

Proposed failure mode and law, for the owner's call: a derived edition gets its own candidate digest and receipt. Its provenance lines are generated from that receipt and never copied, and every superseded receipt stays reachable from its successor.
