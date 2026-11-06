# Collider-physics X3D demo: graded survey of tools, formats, open data, visuals

Date 2026-11-06. Free only. Written for the Loom Collider spec ([../COLLIDER.md](../COLLIDER.md)); browser renderer X_ITE (16.7.0 was npm latest at writing; the demo pins 16.5.1).
Pivot applied: proof-of-concept demo with maximum graphics fidelity; precision sections trimmed; section 7 (Visual references) added.

## 0. Legend, environment, reach

Grades: **C** = I measured or verified it here (PyPI/npm metadata, pip install, ran code, opened a downloaded file or package source). **L** = read in a source I fetched this session (GitHub page or raw file, arXiv abstract or PDF). **L(ws)** = text returned by the web-search tool only; I did not open the page (lower fidelity, treat as a lead). **S** = from memory, unverified.

Test box: 4 vCPU, 16 GB RAM, no GPU, Python 3.13.18, Node 22.23.4, single-thread timings. [C]

| Host | Result here |
|---|---|
| pypi.org JSON API, registry.npmjs.org, files.pythonhosted.org | reachable [C] |
| raw.githubusercontent.com (any public repo), github.com via WebFetch, arxiv.org abs/pdf | reachable [C] |
| api.github.com / codeload for repos other than the session repo | refused ("access not enabled") [C] |
| opendata.cern.ch, eospublic.cern.ch, root.cern, pythia.org, geant4.web.cern.ch, inspirehep.net, pdg.lbl.gov, zenodo.org, cds.cern.ch, atlas-opendata.web.cern.ch, gitlab.cern.ch, hepsoftwarefoundation.org, quarknet.org, animalicedata.github.io, physicsmasterclasses.org, export.arxiv.org | NOT reachable (resolve failure or proxy reject) [C] |

Consequence: no CERN Open Data file could be downloaded; record IDs below come from tutorials I read or from search text. Everything marked L(ws) must be re-checked at build time.

## 1. Event generators and simulation

| Tool | What it is | Install / licence / size | CPU-only feasibility (this box) | Grade |
|---|---|---|---|---|
| **Pythia 8** (`pythia8mc` 8.318.3, PyPI upload 2026-10-29) | General-purpose pp/ee generator: hard process, shower, MPI, hadronisation, decays | cp313 manylinux x86_64 wheel 30.71 MB; sdist 22.17 MB; macOS arm64 wheel 27.76 MB; GPL v2 or later; Python 3.5 to 3.15 wheels | Whole HEP python stack (below) installed in 11 s. 13.6 TeV generated fine (`Beams:eCM=13600`). See measurements table | C |
| Herwig 7 | Generator, angular-ordered shower, cluster hadronisation | Not on PyPI (name `herwig` 404); source build from herwig.hepforge.org (blocked) | Build takes tens of minutes plus; not minutes-scale | C (404) / S |
| Sherpa 3 | Generator with matrix elements (Comix/Amegic), CKKW merging | `sherpa-mc` 3.0.3 GPLv3; PyPI lists only a macOS arm64 cp313 wheel (41.3 MB), no Linux wheel | Linux needs source or conda build | C |
| MadGraph5_aMC@NLO | Matrix-element generator, writes LHE | No PyPI package under mg5amc, madgraph, madgraph5, mg5 (all 404); distributed as tarball from Launchpad | Needs download + compile of process; heavy for a free session | C (404) / S |
| **Geant4** via `geant4-pybind` 0.1.3 (upload 2026-05-08) | Full detector transport, EM + hadronic physics | cp313 manylinux wheel 28.58 MB; binding licence "Public Domain"; wheel embeds Geant4 string `geant4-11-04-patch-01`; Geant4 Software Licence v1.0 (permissive redistribution with notice) | Import prompts to download datasets (hosts blocked here, 2 min hang). Geometry-only works with stub dataset env vars (below). Real particle transport untested (needs G4EMLOW etc., size ~GB, S) | C / L |
| **Delphes** | Parametrised fast detector simulation, cards for CMS/ATLAS, reads HepMC, writes ROOT | GPL-3+ (LICENSE read), bundles FastJet GPLv2+; not on PyPI (`delphes` 404); C++ build needs ROOT | Fast per event once built; build is the cost | L / C |
| ACTS | Tracking toolkit; ships Open Data Detector (ODD) support | MPL-2.0 (LICENSE read) | Build heavy (DD4hep, ROOT optional) | L |
| Open Data Detector (ODD) | TrackML-derived generic collider tracker in DD4hep | MPL-2.0; Zenodo DOI 10.5281/zenodo.4674401 (README badge); repo acts-project/OpenDataDetector; contains realistic support/cable/cooling material (search text) | Needs DD4hep + Geant4 to simulate | L / L(ws) |
| DD4hep | Detector description toolkit | LGPL-3 (LICENSE read); not on PyPI | Build heavy | L / C |
| FastJet (`fastjet` 3.5.2.0) | Jet clustering (anti-kt etc.) | BSD-3 python wheel cp313 manylinux 2.43 MB; runtime banner says library under GPL v2 or higher | Anti-kt R=0.4 on 200 Z events: 0.06 s; 2.0 jets/event with pT>20 | C |

### Measured with `pythia8mc` 8.318.3 (single thread, 13.6 TeV pp, default tune)

| Sample | Events | Wall time | Final-state particles per event (mean / max) | Charged (mean / max) | Grade |
|---|---|---|---|---|---|
| Z to mumu (mHat 80-100 GeV) | 500 | 4.1 s | 400 / 891 | 192 / 422 | C |
| Z to mumu (mHat 60-120 GeV) | 1000 | 8.4 s (8.4 ms/evt) | n/a | n/a | C |
| gg to H, 25:m0=125.25, H to ZZ*, Z to ee/mumu | 200 | 1.6 s | 448 / 965 | 215 / 462 | C |
| ttbar | 200 | 1.6 s | 555 / 1053 | 265 / 504 | C |
| Minimum bias (non-diffractive) | 300 | 1.0 s | 224 / 768 | 108 / 378 | C |
| Dijets pTHatMin 200 GeV | 300 | 2.7 s | n/a | 255 / 492 | C |
| End-to-end Z to mumu, 2000 events, python object extraction | 2000 | 17.6 s | ~400 | | C |

Reading for the demo: a single generated event is naturally 200 to 1000 particles. The "300 or 3000 particles" target is a plain full event (300-1000) or a hard event plus ~10 overlaid minimum-bias collisions (~2600, derived: 400 + 10 x 224; ~4900 at 20 pile-up, derived). Thousands of events per minute (500 Z events in 4.1 s), so pre-generation is trivial; ship a fixed seed (Random:seed=42) for reproducibility.
Gotcha: rare `StringFragmentation::fragmentToJunction` error, `py.next()` returns False, just retry [C].

### Geant4 to X3D path (verified end to end here) [C]
1. `geant4-pybind` builds a world box + iron barrel, `/vis/open VRML2FILE`, `/vis/drawVolume`. Needs stub dataset env vars (G4LEDATA, G4ENSDFSTATEDATA etc. pointing to empty dirs and an empty `ENSDFSTATE.dat`) to get past the dataset prompt and the G4NuclideTable fatal.
2. Output `g4_00.wrl` (5,786 bytes): header `#VRML V2.0 utf8`, `IndexedFaceSet` solids, coordinates in mm, transparency 0.7 white, camera at z=24494.9.
3. `x3d-tidy` 3.2.2 (npm, MIT) converts to X3D 4.1 XML (5,597 bytes). **Gotcha:** under Node 22.23.4 it crashes (`Float16Array is not defined` inside x_ite.js) unless run as `node --js-float16array node_modules/x3d-tidy/bin/x3d-tidy.js -i in.wrl -o out.x3d`.
4. Source confirmation: `G4VRML2File` constructor registers graphics system "VRML2FILE" as `fileWriter` (Geant4 master `source/visualization/VRML/src/G4VRML2File.cc`, read) [L]; env vars `G4VRMLFILE_DEST_DIR`, `G4VRMLFILE_MAX_FILE_NUM`, `G4VRMLFILE_VIEWER`, `G4VRML_PV_PICKABLE` [L]. String scan of the wheel: VRML2FILE present, VRML1FILE absent, also DAWNFILE, RayTracer, ASCIITree, TSG_OFFSCREEN [C]. Geant4 `source/visualization` also lists FukuiRenderer, OpenInventor, ToolsSG, Vtk, gMocren [L].

## 2. Event data formats and pure-Python readers

| Format | Role | Python access | Notes | Grade |
|---|---|---|---|---|
| HepMC3 (`.hepmc3`) | Generator event record (vertices, particles, PDG ids) | `pyhepmc` 2.16.1 (cp313 wheel 0.63 MB, licence field empty in metadata), `hepmc3` 3.3.1 (GPLv3 in PyPI metadata, wheel 3.76 MB) | Mirror COPYING file is LGPL-3 text, PyPI says GPLv3: verify before bundling. Pythia wheel has no built-in HepMC writer; go via numpy/uproot instead | C / L |
| LHE | Parton-level events from matrix-element generators | `pylhe` 2.1.0 (Apache-2.0); `lhereader` 1.0.11 (2021) | Plain XML-ish text | C |
| EDM4hep / podio | Key4hep event data model, FCC | Not on PyPI (`edm4hep`, `podio` 404); both Apache-2.0 on GitHub (LICENSE read) | Phoenix has `Edm4hepJsonLoader` (colour-by-pid built in) | C / L |
| ROOT TTree | Standard analysis files | `uproot` 5.7.7 (BSD-3, wheel 0.44 MB) reads and writes; `ROOT` PyPI 0.1a12 is a 248 MB wheel: avoid | Wrote 2000 Z events (jagged pt/eta/phi/m/pid/q) = 16.19 MB ROOT file (~8 kB/event), read back OK | C |
| CMS NanoAOD / NanoAOD-like | Flat columns: Muon_pt, Electron_eta ... | `uproot` + `awkward` 2.14.0 + `vector` 1.9.0 | Dimuon mass from 2000 events: 1499 pairs, median 90.94 GeV | C |
| ATLAS PHYSLITE / education ntuples | DAOD_PHYSLITE (research), flat ntuples (education) | `uproot`; helper `atlasopenmagic` 1.10.1 (Apache-2.0); Phoenix `PhysliteLoader` via jsroot | 2025 notebooks: `atom.set_release('2025e-13tev-beta')`, skim `'2muons'`, example file `https://opendata.cern.ch/eos/opendata/atlas/rucio/opendata/ODEO_FEB2025_v0_2muons_data15_periodD.2muons.root`; luminosity 36.6 fb-1 | C / L |
| CMS MiniAOD/AOD | Heavy; CMSSW needed | not pure-Python | Use NanoAOD-like derivatives instead | S |
| Phoenix event JSON | Browser display schema | plain `json` | Keys in section 3 | C |
| iSpy `.ig` | CMS event display archive | `zipfile` + `json` after replacing `nan` tokens | Section 4 | C |
| JiveXML | ATLAS Atlantis/VP1-Lite event XML | Phoenix `JiveXMLLoader` | | C |
| JSROOT | JS reader for ROOT files and TGeo | npm `jsroot` 7.12.0, MIT, 27.3 MB unpacked, depends on three 0.162.0 | Phoenix uses it for PHYSLITE and TGeo geometry | C |
| Analysis helpers | | `particle` 1.1.0 (BSD-3; ships PDG 2025 and 2026 tables), `hepunits` 2.4.7, `coffea` 2026.9.0, `hist` 2.12.1, `mplhep` 1.3.3 (MIT), `scikit-hep-testdata` 0.6.9, `cernopendata-client` 1.0.2, `xrootd` 6.2.1 (LGPL-3, wheel 8.86 MB) + `fsspec-xrootd` 0.5.5 | `root://` URLs need xrootd and an allowed host | C |

## 3. Event displays and existing X3D / VRML work

| Display | Stack / licence | Export or import of interest | Already X3D/VRML? | Grade |
|---|---|---|---|---|
| **Phoenix** (HSF) `phoenix-event-display` 4.2.3 + `phoenix-ui-components` 4.2.3 (Angular) | Apache-2.0; three.js `~0.184.0`, jsroot `^7.11.0`, jszip, dat.gui, tween.js; published 2026-09-12; core 6.99 MB unpacked, UI 1.48 MB | Geometry in: OBJ, glTF/glb (also zip), three.js JSON, `.phnx` scene, ROOT TGeo via jsroot. Geometry/scene out: OBJ, glTF (GLTFExporter). Event loaders: Phoenix JSON, CMS `.ig`, JiveXML, ATLAS ESD, PHYSLITE, EDM4hep JSON, TrackML, ROOT, script. VR/AR managers present | No. Source scan finds no X3D/VRML mention. Bridge: export glTF or OBJ, X_ITE imports glTF/OBJ natively | C |
| iSpy WebGL (CMS) | MIT; three.js, Vite, `2.0.0-rc` | Repo ships `geometry/{gltf,json,obj}` and `data/*.ig`; custom geometry via SketchUpCMS to OBJ/MTL | No | L / C |
| Atlantis / VP1 / VP1-Lite (ATLAS) | Desktop (Java for Atlantis, Qt + Inventor for VP1: S); JiveXML input (Phoenix loader exists: C) | VP1 exports sub-detector geometry as SGI Inventor; ATLASrift converted it to VRML 2.0 | Historic VRML route | L(ws) |
| JSROOT TGeo viewer | MIT, three.js | Draws TGeo from ROOT files in browser | No | C / S |
| CMS Fireworks | ROOT/EVE desktop, reads CMSSW files | | No | S |
| ATLASrift (Unreal Engine, Oculus Rift) | arXiv 1511.00047; no WebGL port and no open-source release found | VR tour of cavern, detector, a real event | VRML 2.0 used as geometry interchange | L / L(ws) |
| CED VR (UCLA, CMS events in VR) | Standalone-headset app (Oculus AppLab listing); "CED VR Companion" repo for custom events | | No | L(ws) |
| SketchUp CMS (arXiv 1311.4942) | Ruby API reads CMS detector XML and iSpy JSON, builds 3D models for TDR figures, art, outreach | | No | L |
| Geant4 VRML2FILE | See section 1 | `.wrl` to X3D via x3d-tidy | **Yes, verified end to end** | C |
| Historic HEP VRML | "Virtual ATLAS" (J. Hrivnac, 1995-97, hrivnac.web.cern.ch/Activities/1997/VirtualAtlas); ROOT TBuffer3D could target an X3D viewer | | VRML-era only | L(ws) |

**Finding:** there is no maintained X3D/X3D4 collider event display. All living displays are three.js (Phoenix, iSpy, JSROOT). The Loom can claim a genuine gap: first browser X3D collider display with witnessed physics. Interchange routes: three.js displays to glTF/OBJ to X_ITE; Geant4 to VRML2 to X3D; Pythia to our own generator script.

### Phoenix event JSON schema (from `dist/lib/types/event-data.d.ts`, 4.2.3) [C]
Top level: one object per event keyed by event name; each event has collection groups, each group is `{collectionName: [objects]}`.
- `Tracks`: `pos` ([[x,y,z],...]) or `dparams` [d0,z0,phi,theta,qOverP]; `phi, eta, d0, z0, pT, chi2, dof, color, linewidth`.
- `Jets`: `eta, phi, theta, energy | et, coneR, origin_X/Y/Z, color`.
- `Hits`: `[x,y,z]` or `{pos, type: Point|CircularPoint|Line|Box, color, extraInfo}`.
- `CaloClusters`: `energy, phi, eta, radius, z, side, length, color, opacity`. Also `CaloCells`, `PlanarCaloCells {plane, cells}`, `IrregularCaloCells` (8 vertices, 24 floats).
- `Muons`, `Electrons`, `Photons`: compound objects with `LinkedTracks`, `LinkedClusters`, `phi, eta, energy, pT`.
- `Vertices`: `pos|x,y,z, size, linkedTracks`. `MissingEnergy`: `etx, ety`. Event ids: `event number`, `run number`.
Phoenix has a built-in invariant-mass helper (`helpers/invariant-mass`) [C].

## 4. Open datasets

Licence: CERN Open Data Portal terms put all metadata and datasets under CC0 (opendata.cern.ch/terms-of-use) [L(ws)]; ATLAS paper states "All data are shared under a Creative Commons CC0 waiver, with unique DOI identifiers" [L, arXiv 2502.21133]; CMS records state CC0 1.0 [L(ws)]. ATLAS 2020 education release: for educational use, not for publications [L(ws)]. Software repos have their own licences.

| Dataset | ID / DOI | Size / content | <50 MB? | Grade |
|---|---|---|---|---|
| **iSpy sample events, in repo**: `Hto4l_120-130GeV.ig` | github.com/cms-outreach/ispy-webgl/tree/master/data (MIT repo; file licence not stated, data origin CMS 2012 open data) | **1,119,117 B**, 11 CMS 8 TeV events, CMSSW_5_3_36. Four-lepton mass, first four entries of GlobalMuons_V1 then GsfElectrons_V2 (PDG lepton masses, pT/eta/phi from the collections; not an analysis selection): 128.6, 125.6, 126.5, 124.9, 122.3, 129.9, 126.7, 122.5, 125.2, 125.4, 121.5 GeV, charge sum 0 in all 11 (measured here). Event 1 has 6 leptons so its value uses a 4-lepton subset. Mix: 2 x 4mu, 6 x 2e2mu, 2 x 4e, 1 six-lepton | **Yes** | C |
| Same dir, other `.ig` | `DoubleMuParked_Run2012C_0.ig` 3,012,530 B; `DoubleElectron_Run2012C_0.ig` 2,257,530 B; `BJetPlusX_Run2012C_0.ig` 3,529,192 B; `MinimumBias_Run2012C_0.ig` 1,129,918 B; also DoublePhoton_Run2012B_0, JetHT_Run2012C_0, MET_Run2012C_0, TauParked_Run2012C_0 (sizes not fetched) | **Yes** | C / L |
| ROOT tutorial df103 "skimmed" CMS 2012 NanoAOD-like | `root://eospublic.cern.ch//eos/root-eos/cms_opendata_2012_nanoaod_skimmed/`: SMHiggsToZZTo4L, ZZTo4mu, ZZTo4e, ZZTo2e2mu, Run2012B/C_DoubleMuParked, Run2012B/C_DoubleElectron. Comment: total "only 51MB" fast mode, 12 GB full. Event counts: ZZ4mu 1,499,064; ZZ4e 1,499,093; ZZ2e2mu 1,497,445; H4l 299,973; 11.6 fb-1. DOI 10.7483/OPENDATA.CMS.JKB8.RR42, record 5500 | 51 MB total over 8 files (each file under 50 MB) | **Yes (per file)**; host unreachable here | L |
| ROOT tutorial df102 dimuon | `root://eospublic.cern.ch//eos/opendata/cms/derived-data/AOD2NanoAODOutreachTool/Run2012BC_DoubleMuParked_Muons.root`, 66 million events, DOIs 10.7483/OPENDATA.CMS.YLIC.86ZZ and 10.7483/OPENDATA.CMS.M5AD.Y3V3, records 6004, 6030, 12341 | Large (size not shown) | No | L |
| CMS Higgs-to-4-lepton example records | Record 5500 (analysis, DOI 10.7483/OPENDATA.CMS.JKB8.RR42 [L]); record 5501 "Root files for H to 4l analysis example, 2011-2012", DOI 10.7483/OPENDATA.CMS.JKB8.D634, 24 files, **1.5 MiB total** | tiny | **Yes** | L / L(ws) |
| CMS record 12360 | "Analysis of Higgs boson decays to four leptons ... 2012 ... RDataFrame" | | | L(ws) |
| CMS record 300 | Higgs candidate events for education/outreach, `.ig` files for the web viewer | | likely yes | L(ws) |
| CMS record 5001 | Dimuon spectrum example, /DoubleMu/Run2011A-12Oct2013-v1/AOD, default 10,000 events (Z, J/psi peaks) | | | L(ws) |
| CMS record 230 | 2011 DoubleMu derived muon/electron collections, 35,346,886 events, 54 files | big | no | L(ws) |
| CMS 2016 NanoAODv9 e.g. record 30555 | DoubleMuon Run2016H UL: 48,912,812 events, 28 files, 42.9 GiB | big | no | L(ws) |
| CMS masterclass `.ig` | 200 files x 100 events (1-, 2-, 4-lepton mixes) | | per file small | L(ws) |
| ATLAS Open Data 8 TeV (2016) | 1 fb-1, ~6 GB | | no | L |
| ATLAS Open Data 13 TeV (2020) | 10 fb-1, ~150 GB total; per-collection ZIPs 427 MB to 24 GB (search text); DOIs e.g. 10.7483/OPENDATA.ATLAS.2Y1T.TLGL (>=4 lepton) | | no | L / L(ws) |
| ATLAS 13 TeV 2025 education | 36 fb-1 flat ROOT ntuple; skims such as `2muons`; via `atlasopenmagic` 1.10.1 | per-skim sizes not seen | unknown | L / C |
| ATLAS PHYSLITE research | "DAOD_PHYSLITE format 2015-2016 Open Data for Research", DOI 10.7483/OPENDATA.ATLAS.9HK7.P5SI | large | no | L |
| ALICE | 2021 paper: 5% of Pb-Pb and 7% of 2010 pp ESD released; AOD planned | | | L(ws) |
| LHCb | Full Run-1 dataset filtered and released (portal news item) | | | L(ws) |

Notes: `.ig` is a ZIP: `Header` (`"CMSSW_5_3_36"`), `Events/Run_<n>/Event_<n>` members. Each event is JSON-like with `Types`, `Collections`, `Associations`, but contains bare `nan` tokens so strict JSON fails; replace `nan/inf` with `null` then parse [C]. 28 collections in the first event; useful: `Tracks_V3 [pos,dir,pt,phi,eta,charge,chi2,ndof]`, `Extras_V1 [pos_1,dir_1,pos_2,dir_2]` (track end points + directions for spline drawing), `GlobalMuons_V1`, `GsfElectrons_V2`, `PFJets_V1 [et,eta,theta,phi]`, `PFMETs_V1`, `Photons_V1`, `Vertices_V1`, `MuonChambers_V1` (8-corner boxes), `EBRecHits_V2`, `EERecHits_V2`, `HBRecHits_V2`. Positions in metres. First event 914,065 bytes of JSON (rec-hit and trigger heavy) [C].

## 5. Detector geometry and headline numbers

| Item | Value | Source | Grade |
|---|---|---|---|
| CMS size | 21.6 m long, 14.6 m diameter, 12,500 t (another source says 14,000 t; CERN public page 12,500 t) | JINST 2008 as quoted in search text; public-archive.web.cern.ch CMS page | L(ws) |
| CMS solenoid | 3.8 T | memory | S |
| ATLAS size | 46 m long, 25 m diameter, 7,000 t | secondary sources only (magazine, lecture slides) | L(ws), weak |
| ATLAS magnets | toroids + 2 T solenoid | memory | S |
| LHC | circumference 26,659 m (secondary); ~27 km nominal | wikiwand; Nikhef | L(ws) |
| Run 3 energy | 13.6 TeV (6.8 TeV per beam), from July 2022 | home.cern "third run ... successfully started" | L(ws) |
| Pythia accepts 13.6 TeV | `Beams:eCM=13600` | ran it | C |

Geometry sources to reuse:
- iSpy repo `geometry/gltf`, `geometry/json`, `geometry/obj` exist (file lists not shown by the page; fetch raw files with names from the repo) [L]. CMS detector via SketchUpCMS to OBJ [L].
- Phoenix `phoenix-app/src/assets/geometry` directory exists (contents unlisted) [L]; Phoenix docs reportedly have GDML to glTF conversion guides [L(ws)].
- ODD (DD4hep, MPL-2.0, DOI 10.5281/zenodo.4674401) is the only fully open full-tracker description with a DOI [L].
- ATLAS: VP1 geometry exportable as Inventor, then VRML 2.0 (ATLASrift route) [L(ws)]. ALICE and LHCb public GDML/TGeo not located [S].
- GDML reader in Python: `pyg4ometry` 1.4.6 (GPL, 34.9 MB wheel) [C]; X_ITE reads glTF directly (npm description: "VRML, glTF and Other 3D Sources") [C].
- Simplest free route: procedural X3D detector (nested cylinders and endcap discs, from the published dimensions) plus optional glTF import of iSpy CMS geometry. Procedural needs no download.

## 6. Physics anchors (kept short)

Reference values come from the `particle` 1.1.0 package, which ships the official PDG mass tables (file headers: "2025 EDITION OF RPP", generated 22-Apr-2025; "2026 EDITION OF RPP", generated 11-May-2026; default table in the package is 2026) [C].

| Quantity | PDG 2025 table | PDG 2026 table | Pythia 8.318 default | Note |
|---|---|---|---|---|
| Z mass | 91.1880 GeV (+-0.0020) | 91.1879 GeV (+-0.0020) | 91.1876 | 91.1876 is the older (<=2022) PDG value, still the common reference [S for edition history] |
| Higgs mass | 125.20 GeV (+-0.11) | 125.13 GeV (+-0.11) | 125.0 | 125.25 (brief) is the PDG 2022 value [S]; set `25:m0=125.25` explicitly for the demo |
| J/psi(1S) | 3.0969 GeV (+-6e-6) | 3.0969 GeV | 3.09692 | |
| Muon | 105.6583755 MeV | same | 0.10566 GeV | |
| W / top | 2026 table: W 80.362 GeV, t 172.6 GeV | | 80.385 / 173.0 | |

Relations (all C where numeric):
- `pT[GeV] = 0.299792458 * B[T] * R[m]` (0.299792458 = c/1e9, arithmetic). R(1 GeV, 3.8 T) = 0.877 m; R(10 GeV) = 8.77 m; ATLAS 2 T: 1.67 m per GeV.
- `eta = -ln tan(theta/2)`: theta 90 deg gives 0; 10 deg gives 2.436; 1 deg gives 4.741. `vector` 1.9.0 gives eta, theta, mass directly.
- Pythia events, 1200 events over four processes: max |sum p - beams| = 0.0002 to 0.0008 GeV on 13,600 GeV; sum of final-state charge = +2 in every event (the two beam protons), not 0.
- Dimuon mass from generated final-state muons peaks at 90.85 to 90.94 GeV (median) for the Z window sample (FSR shifts it down slightly).
- Real data check: 11 sample CMS events have m4l 121.5 to 129.9 GeV (section 4). These are one-line witnesses for a "science gate".

## 7. Visual references (best-looking public collider visuals and how they are made)

### 7a. Colour conventions, as actually coded or documented

| Object | CMS iSpy WebGL defaults (read from `js/objects-config.js`, master) | Phoenix defaults (package source) | Other | Grade |
|---|---|---|---|---|
| Muons | red `rgb(100%,0,0)`, linewidth 3, opacity 1 | EDM4hep loader: magenta `ff00ff`; generic Tracks default red `0xff0000` | Masterclass doc: muons red | C / L(ws) |
| Electrons | green `rgb(10%,100%,10%)` (GSF tracks), linewidth 3, opacity 0.9 to 1 | EDM4hep loader: green `00ff00` | Masterclass doc: electrons green | C / L(ws) |
| Photons | gold `rgb(100%,80%,0)`, linewidth 2 | EDM4hep loader: red `ff0000` | | C |
| Jets | yellow `rgb(100%,100%,0)` cones, opacity 0.6 (PF jets) | blue `0x2194ce` Fresnel cone | One ATLAS display: jets as cones (b-jet in blue) | C / L(ws) |
| Missing ET | pink-magenta `rgb(100%,50%,100%)`, linewidth 2 | white `0xffffff` | Masterclass doc: light purple | C / L(ws) |
| Vertices | yellow, radius 0.001 | `0xffd166` | | C |
| ECAL / HCAL boxes | ECAL light blue `#7fccff` (opacity 0.01 to 0.75); HCAL olive-yellow `rgb(70%,70%,0)`; tracker yellow wireframe 0.5; muon chambers DT orange `rgb(80%,40%,0)`, CSC/RPC green-yellow | CaloClusters `0xffd166`, PlanarCaloCells `0xfff69a` | | C |
| Pions / protons / kaons | | `a52a2a`, `778899`, `5f9ea0` (EDM4hep loader) | | C |
| Background | black default, white optional | | design note: white background + red trajectories + grey arcs for jets (Thaler/Frankel) | L / L(ws) |

Verification of the brief's "ATLAS muons red, electrons green, jets yellow cones": **muons red / electrons green is verified only for CMS iSpy** (and the CMS masterclass guide). **Yellow jet cones is verified for iSpy**, not for ATLAS. No official ATLAS colour legend was found; one ATLAS leptoquark display shows a red muon and blue electrons, and Atlantis colours are user-configurable [L(ws)]. Do not call any scheme "the ATLAS convention".

### 7b. Reference works and the technique behind them

| Reference | URL | Technique (one line) | Grade |
|---|---|---|---|
| Phoenix jet shader | github.com/HSF/phoenix, npm `phoenix-event-display/dist/loaders/objects/phoenix-objects.js` | Cone mesh with a Fresnel `ShaderMaterial`: alpha = mix(0.15, 0.7, pow(1-abs(N.V), 1.5)), transparent, depthWrite off, so jets read as glowing shells, overlaps stay legible | C |
| Phoenix tracks and cells | same package, `loaders/objects/tracks.js` | Track lines merged into one mesh with per-vertex `linewidth` attribute (camera-facing quads); calo cells as one `InstancedMesh` ("187K draw calls to 1" per source comment); `MeshToonMaterial` for propagated tracks; amber `OutlinePass` (0xffcc44) for selection through an `EffectComposer` | C |
| iSpy WebGL | github.com/cms-outreach/ispy-webgl | `Line2`/`LineMaterial` fat lines (optional), transparent boxes for calorimeter towers sized by energy, black background, CMS logo overlaid in 2D. No bloom or glow code found (grep) | C / L |
| ATLASrift (ATLAS VR) | arxiv.org/abs/1511.00047 | Unreal Engine + Oculus Rift; geometry via VP1 Inventor export to VRML 2.0; first-person walk-through plus a real event. Game-engine shading, not open source | L / L(ws) |
| CED VR (UCLA) | vr.physics.ucla.edu/cedvr.html | CMS events in a standalone headset app (Unity-style pipeline suggested by sibling VRSPY report) | L(ws) |
| ALICE Blender animations | github.com/AnimALICEData/ALICE-Blender-Animation; samples animalicedata.github.io/sampleanimations; talk indico.cern.ch/event/944917/contributions/4098878 | Python classes build Blender scenes from particle kinematic lists; analytic helices for the near-uniform field; Pb-Pb 2.76 TeV and pp 7 TeV clips; media CC-BY | L(ws) |
| SketchUp CMS models | arxiv.org/abs/1311.4942 | Ruby API turns CMS detector XML and iSpy JSON into clean illustrative 3D models used in TDRs and art projects | L |
| Neon / art pieces | pdg.lbl.gov/artarticle/3.html (neon rendering of a real LHC event, apparent H to 4mu); CMS Art@CMS residency | Hand-designed glow-tube look from real event data | L(ws) |
| Design note on event pictures | jthaler.net/pdfs/jthaler_frankel_picturing_science.pdf | Simplify: few colours, grey arcs for secondary jets, clear hierarchy | L(ws) |
| Official event images | cds.cern.ch/images/ATLAS-PHO-EVENTS-2012-007-1 (4-muon candidate); CERN video CERN-MOVIE-2011-192-001 (CMS four muons); CDS "ATLAS Photos: Events and Plots" collection | Press stills from Atlantis/VP1 and iSpy; check each record's licence (not verified) | L(ws) |
| Fermilab / CERN animations | news.fnal.gov accelerator animations | No openly licensed collision animation confirmed; stock-video sites sell LHC animations (commercial, do not reuse) | L(ws) |

### 7c. Shader / post-processing toolbox

| Capability | three.js 0.187.0 (npm tarball listing, MIT) | X_ITE 16.7.0 (bundle string scan) | Grade |
|---|---|---|---|
| Bloom | `UnrealBloomPass` (mip-chain blur; params strength, radius, threshold; docs example 1.5/0.4/0.85), TSL `BloomNode`; selective bloom only via forks or layer tricks | **No bloom string at all** (Bloom: 0 hits). Must fake glow | C / L(ws) |
| Depth of field | `BokehPass`, TSL `DepthOfFieldNode` | none (0 hits) | C |
| Trails / persistence | `AfterimagePass`, `AfterImageNode`, `MotionBlur`, `TRAANode` | none | C |
| Ambient occlusion / reflections | `GTAOPass`, `SSAOPass`, `SSRPass` | none | C |
| Fat lines | `Line2`, `LineMaterial`, `LineSegments2`, `Wireframe` | `LineProperties` with `linewidthScaleFactor` (Line2 path present) | C |
| Lens flare | `Lensflare`, `LensflareNode` | none | C |
| Outline | `OutlinePass` | none | C |
| Tone mapping | `OutputPass` | `ToneMapping` options incl. `TONEMAP_ACES_HILL`, `ACES_HILL_EXPOSURE_BOOST`, `ACES_NARKOWICZ`, `KHR_PBR_NEUTRAL` | C |
| HDR emissive | via bloom | glTF `KHR_materials_emissive_strength`, `KHR_materials_volume`, `transmission`, `iridescence`, `dispersion` handled; `SpecularGlossiness` | C |
| Custom shaders | ShaderMaterial / TSL | `ComposedShader` + `ShaderPart` strings present; `FloatVertexAttribute` present | C |
| Particles | Points / InstancedMesh | `ParticleSystem` (geometryType includes POINT, GEOMETRY), `InstancedShape`, `EXT_mesh_gpu_instancing`, `PointProperties`, `Billboard`, `Layer/LayerSet` | C |
| Blending | custom | `BlendMode` node, `blendFunc` calls present, so additive halos are possible | C |
| Loaders | `VRMLLoader`, `GLTFLoader`, `GLTFExporter`; **no `X3DLoader` in 0.187.0** | native VRML/X3D/glTF/OBJ; bundle 1.31 MB minified (282 KB gzip) | C |

Technique list for the X3D demo (design suggestions, S): additive-blended halo ribbons around each track (billboard strip with soft alpha); emissive core + ACES tone mapping; per-particle `ComposedShader` driven by PDG class (muon, electron, hadron, photon) with a time uniform for a "travelling pulse" along the helix; Fresnel cone jets (port the Phoenix recipe); instanced calorimeter towers sized by energy; ParticleSystem sparks at the vertex; if true bloom is wanted, composite it outside X3D (canvas overlay) and record that as a Loom page-level effect, because X_ITE has no bloom node.

## 8. What works today in a free container (verified recipe)

| Step | Command / package | Time | Grade |
|---|---|---|---|
| Install stack | `pip install pythia8mc==8.318.3 uproot==5.7.7 awkward==2.14.0 vector==1.9.0 particle==1.1.0 hepunits==2.4.7 pyhepmc==2.16.1 pylhe==2.1.0 fastjet==3.5.2.0` | 11 s | C |
| Generate | Pythia Z to mumu / H to ZZ* to 4l / ttbar, 13.6 TeV | 1.6 to 8 s per 200-1000 events | C |
| Persist | uproot ROOT file (8 kB/event) or Phoenix-style JSON (1 event, 54 charged tracks pT>0.5 GeV, 24-point helices: 26.9 kB raw, 10.2 kB gzip) | instant | C |
| Detector solids to X3D | `geant4-pybind` VRML2FILE then `node --js-float16array x3d-tidy` | <1 s after dataset stubs | C |
| Real events | download `Hto4l_120-130GeV.ig` (1.1 MB) from raw GitHub, `zipfile` + `nan` fix | instant | C |
| Renderer | X_ITE 16.7.0 from npm/CDN | | C |
Not tested: real Geant4 showers, Delphes, ACTS (builds/datasets unreachable), any browser render of the generated scene.

## 9. Could not reach / unverified

- Not reachable (resolution or proxy refusal): opendata.cern.ch and eospublic.cern.ch (so no portal record page, file list, size or licence page was opened), root.cern, pythia.org, geant4.web.cern.ch and Geant4 dataset hosts, inspirehep.net, pdg.lbl.gov (PDG values come from the `particle` package tables instead), zenodo.org, cds.cern.ch, atlas-opendata.web.cern.ch, gitlab.cern.ch (ODD GitLab, HepMC3 upstream), hepsoftwarefoundation.org, quarknet.org, animalicedata.github.io, physicsmasterclasses.org, export.arxiv.org. api.github.com and codeload refused for non-session repos; file sizes inside repos therefore mostly unknown except raw downloads.
- All record IDs and sizes tagged L(ws) (5001, 5501, 12360, 300, 230, 30555, ATLAS 2020 per-collection sizes, ALICE and LHCb figures) are search-tool text, not opened pages.
- Unverified (S): CMS 3.8 T, ATLAS 2 T and toroid figures; Herwig/MadGraph build effort; Geant4 dataset size; Delphes and ACTS runtime; Fireworks, VP1 details; the per-file CC0 status of the iSpy sample `.ig` files; PDG edition history (91.1876 and 125.25 as older editions); ALICE and LHCb public geometry files.
- Phoenix 4.2.3 depends on three `~0.184.0` while npm latest is 0.187.0 (version skew if reusing its code). `pyhepmc` metadata lacks a licence field; HepMC3 licence differs between PyPI (GPLv3) and a mirror COPYING (LGPL-3).
- Not tested: GPU/WebGL rendering of anything; X_ITE behaviour on the Geant4-derived X3D.

## 10. Ranked recommendation (free flagship, graphics-first)

**Top 3 data sources**
1. **Self-generated Pythia 8.318 events** (13.6 TeV; Z to mumu, H(125.25) to ZZ* to 4l, ttbar, dijets, plus optional pile-up). Unlimited, deterministic by seed, full truth (PDG ids, 4-momenta), 200-1000 particles per event (3000 with pile-up), 1.6-8 s per batch, no network. [C]
2. **iSpy sample `.ig` files from the cms-outreach/ispy-webgl repo** (`Hto4l_120-130GeV.ig` 1.1 MB, 11 real CMS H to 4l candidates with m4l 121.5-129.9 GeV, plus Z/dimuon/jet samples 1-3.5 MB each). Real data, ready tracks (`Tracks_V3`, `Extras_V1`), jets, calo hits, muon chambers; reachable via raw GitHub today. Check the file licence (origin: CMS Open Data, CC0 per portal). [C]
3. **CMS 2012 skimmed NanoAOD-like set (51 MB for 8 files, ROOT tutorial df103) with record 5500/5501 (DOI 10.7483/OPENDATA.CMS.JKB8.RR42, .D634)**, fallback ATLAS 2025 `2muons` skim via `atlasopenmagic`. Gives true Z/H mass spectra for a validation panel; fetch at build time from a network that allows `eospublic.cern.ch` (blocked here). [L]

**Top 3 tools**
1. **Pythia 8 `pythia8mc` + uproot/awkward/vector/particle/fastjet** (all pip, 11 s install, no compiler). [C]
2. **X_ITE 16.7.0 (MIT) + `x3d-tidy` 3.2.2 (MIT, run with `--js-float16array` on Node 22)**, with Geant4 VRML2FILE via `geant4-pybind` as the detector-solid exporter. Biggest caveat: X_ITE has no bloom/DoF, so glow must be built from additive halos, emissive materials, ACES tone mapping and `ComposedShader`. [C]
3. **Phoenix (Apache-2.0) as design and schema donor**: reuse its event JSON schema, loaders (`.ig`, JiveXML, EDM4hep, TrackML), Fresnel jet shader, merged-line track approach and instanced calo cells, and its glTF/OBJ geometry; three.js addons (UnrealBloomPass, Line2, BokehPass) as the look reference if a bloom post-pass is composited outside X3D. [C]
