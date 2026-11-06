"""Metal-site witness for molecular structures and trajectories (x3d.STEM "Proteins in Motion", zinc fingers).

Reads PDB-format coordinates (ATOM and HETATM records, MODEL/ENDMDL frames) with the standard library
only, and checks every declared metal site: which atoms coordinate it, at what distances, in what
geometry, with which ligand class, and in how many frames. Every predicate raises (need), so `python -O`
cannot turn a red site green (law 18). A pass reports what it read (law 36): atoms, frames, the metal atoms in
the file and which of them the spec did not select, alternate-location atoms skipped, and sites checked.

Why it exists (grade L): a molecular dynamics run can finish, conserve energy and still lose its zinc,
change its ligands or bind the wrong histidine nitrogen; energy conservation admits a run, it does not
confirm the site the captions describe (law 21). It checks the ligand class, and with an optional
"ligands" list the exact residues. A scene ten times too small (nanometres read as
angstrom) validates as X3D (law 2). This witness checks the site itself.

Thresholds live in the site spec, never in this file (law 28: fix the instrument, not the threshold).
DEFAULT_WINDOWS are typical crystallographic ranges for Zn(II), graded L (from memory of the protein and
small-molecule surveys of metal-ligand distances; confirm against a fetched survey before quoting them).
The tau4 index is Yang, Powell and Houser's four-coordinate geometry index: (360 - (a + b)) / 141, with a
and b the two largest ligand-metal-ligand angles; 0 is square planar (L). The published index divides by 141,
which is 360 - 2 x 109.5, so an ideal tetrahedron (109.47 degrees) reads 1.000408, not 1; the formula is kept as
published and the tests pin that value.

Stable diagnostics: SITE_PARSE, SITE_SPEC, SITE_NO_METAL, SITE_UNITS, SITE_COORDINATION, SITE_CLASS,
SITE_LIGANDS, SITE_DONOR, SITE_DISTANCE, SITE_GEOMETRY, SITE_INTACT_FRACTION.

Limits (declared before the first real run):
- PDB format only; mmCIF is not read (convert first). Alternate locations other than blank or A are skipped
  and counted. Every frame must list the same atoms in the same order, and with MODEL records no atom may sit
  outside one; frames separated only by END are refused (SITE_PARSE), never read as one doubled frame.
- Ligands are found by ELEMENT (N, O, S, Se, halogens) within search_radius, whatever the residue or atom is
  called, so a fifth ligand counts even when the donor table does not name it (a backbone O, a GROMACS SOL
  water, a chloride). A donor beyond the radius counts as absent (SITE_COORDINATION); one inside it but outside
  its element's window is SITE_DISTANCE. Even inside 2.5 to 3.5 A the unbound oxygen of a one-armed Asp or Glu
  can sit near 3 A and be counted, so such sites need a smaller radius.
- The units check is a gross-error check (median nearest-neighbour distance below 0.5 means nanometres);
  bonded atoms sit about 1.1 A apart with hydrogens and 1.4 A without, so it cannot catch a scale error of less
  than a factor of about 2.
- Ligand class is the one-letter code of each protein side-chain donor named in DONORS, in chain and sequence
  order; any other ligand atom of a protein residue (a backbone O) enters it as 'x'. Waters and other
  non-protein ligands count for coordination but not for the class string.
- donor_atoms names which atom must bind (for histidine, ND1 or NE2). Protonation (HID, HIE, HIP) is not
  checked: a histidine whose proton sits on the binding nitrogen still passes.
- Residue numbers that are not decimal (OpenMM's hexadecimal above 9999) are kept as text; such an atom can
  be a ligand, but cannot be named as a metal by resseq.
"""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path

from .core import GateError, need

SCHEMA = "loom.metal-site-spec/1"

# Donor atoms by residue name, including the Amber names for deprotonated or tautomer-fixed residues.
DONORS = {
    "CYS": ("SG",), "CYM": ("SG",), "CYX": ("SG",),
    "HIS": ("ND1", "NE2"), "HID": ("ND1", "NE2"), "HIE": ("ND1", "NE2"), "HIP": ("ND1", "NE2"),
    "HSD": ("ND1", "NE2"), "HSE": ("ND1", "NE2"), "HSP": ("ND1", "NE2"),
    "ASP": ("OD1", "OD2"), "ASH": ("OD1", "OD2"), "GLU": ("OE1", "OE2"), "GLH": ("OE1", "OE2"),
    "HOH": ("O",), "WAT": ("O",), "SOL": ("OW",), "TIP": ("OH2",), "T3P": ("O", "OW"), "SPC": ("OW",),
}
ONE_LETTER = {"CYS": "C", "CYM": "C", "CYX": "C", "HIS": "H", "HID": "H", "HIE": "H", "HIP": "H",
              "HSD": "H", "HSE": "H", "HSP": "H", "ASP": "D", "ASH": "D", "GLU": "E", "GLH": "E"}
PROTEIN = set(ONE_LETTER) | {"ALA", "ARG", "ASN", "GLN", "GLY", "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER",
                             "THR", "TRP", "TYR", "VAL", "SEC", "MSE", "LYN", "ARN", "NME", "ACE"}
CANON = {"HID": "HIS", "HIE": "HIS", "HIP": "HIS", "HSD": "HIS", "HSE": "HIS", "HSP": "HIS",
         "CYM": "CYS", "CYX": "CYS", "ASH": "ASP", "GLH": "GLU"}
LIGAND_ELEMENTS = {"N", "O", "S", "SE", "F", "CL", "BR", "I"}
METAL_NAMES = {"ZN", "FE", "CU", "NI", "CO", "MN", "CD", "HG", "PB", "CA", "MG", "FE2", "CU1"}
DEFAULT_WINDOWS = {"ZN": {"S": [2.20, 2.45], "N": [1.95, 2.20], "O": [1.90, 2.30]}}


def parse_pdb(text: str, stats: dict | None = None) -> list[list[dict]]:
    """Return frames, each a list of atoms. A file without MODEL records is one frame. stats, when given,
    receives the number of alternate-location atoms skipped per frame."""
    frames: list[list[dict]] = []
    cur: list[dict] = []
    in_model = seen_model = ended = False
    skipped = 0
    for n, line in enumerate(text.splitlines(), 1):
        rec = line[:6].strip()
        if rec == "MODEL":
            need(not in_model, "SITE_PARSE", f"line {n}: MODEL inside MODEL")
            need(not cur, "SITE_PARSE", f"line {n}: {len(cur)} atom records outside any MODEL")
            in_model, seen_model, cur = True, True, []
        elif rec == "ENDMDL":
            need(in_model, "SITE_PARSE", f"line {n}: ENDMDL without MODEL")
            frames.append(cur); in_model, cur = False, []
        elif rec == "END":
            ended = True
        elif rec in ("ATOM", "HETATM"):
            need(not (ended and not seen_model), "SITE_PARSE", f"line {n}: frames separated by END without MODEL records")
            if line[16:17] not in (" ", "A", ""):
                skipped += 1
                continue
            try:
                x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
            except ValueError:
                raise GateError("SITE_PARSE", f"line {n}: coordinates are not numbers") from None
            need(all(math.isfinite(v) for v in (x, y, z)), "SITE_PARSE", f"line {n}: nonfinite coordinate")
            name = line[12:16].strip()
            element = line[76:78].strip().upper() or "".join(c for c in name if c.isalpha())[:1].upper()
            raw = line[22:26]
            try:
                resseq = int(raw)
            except ValueError:
                need(raw.strip().isalnum(), "SITE_PARSE", f"line {n}: residue number {raw!r} is not readable")
                resseq = raw.strip()
            resname = line[17:20].strip().upper()
            cur.append({"name": name, "resname": resname, "chain": line[21:22].strip(), "resseq": resseq,
                        "element": element, "xyz": (x, y, z), "id": (name, resname, line[21:22], raw, line[26:27])})
    need(not in_model, "SITE_PARSE", "MODEL without ENDMDL")
    if seen_model:
        need(not cur, "SITE_PARSE", f"{len(cur)} atom records after the last ENDMDL")
    elif cur:
        frames.append(cur)
    need(frames and all(frames), "SITE_PARSE", "no atoms")
    need(len({len(f) for f in frames}) == 1, "SITE_PARSE", "frames hold different numbers of atoms")
    ids0 = [a["id"] for a in frames[0]]
    for k, f in enumerate(frames[1:], 1):
        need([a["id"] for a in f] == ids0, "SITE_PARSE", f"frame {k}: atom order or identity differs from frame 0")
    if stats is not None:
        stats["altloc_skipped"] = skipped // len(frames)
    return frames


def _dist(a, b) -> float:
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(a, b)))


def _angle(m, a, b) -> float:
    u = [p - q for p, q in zip(a, m)]; v = [p - q for p, q in zip(b, m)]
    nu, nv = math.sqrt(sum(c * c for c in u)), math.sqrt(sum(c * c for c in v))
    c = sum(p * q for p, q in zip(u, v)) / (nu * nv)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def tau4(metal, ligands) -> float:
    """Yang-Powell-Houser tau4 for a four-coordinate site: 1 tetrahedral, 0 square planar."""
    need(len(ligands) == 4, "SITE_GEOMETRY", f"tau4 needs 4 ligands, got {len(ligands)}")
    angles = sorted((_angle(metal, ligands[i], ligands[j]) for i in range(4) for j in range(i + 1, 4)), reverse=True)
    return (360.0 - (angles[0] + angles[1])) / 141.0


def median_nearest_neighbour(atoms: list[dict], limit: int = 400) -> float:
    pts = [a["xyz"] for a in atoms[:limit]]
    need(len(pts) >= 2, "SITE_UNITS", "too few atoms to check units")
    nn = sorted(min(_dist(p, q) for j, q in enumerate(pts) if j != i) for i, p in enumerate(pts))
    return nn[len(nn) // 2]


def load_spec(spec: dict) -> dict:
    need(isinstance(spec, dict) and spec.get("schema") == SCHEMA, "SITE_SPEC", f"schema must be {SCHEMA}")
    need(isinstance(spec.get("sites"), list) and spec["sites"], "SITE_SPEC", "sites: at least one")
    r = spec.get("search_radius", 3.0)
    need(type(r) in (int, float) and 2.5 <= r <= 3.5, "SITE_SPEC", "search_radius must lie in 2.5 to 3.5 angstrom")
    f = spec.get("min_intact_fraction", 1.0)
    need(type(f) in (int, float) and 0.0 < f <= 1.0, "SITE_SPEC", "min_intact_fraction in (0, 1]")
    for s in spec["sites"]:
        need(isinstance(s, dict), "SITE_SPEC", "each site must be an object")
        m = s.get("metal")
        need(isinstance(m, dict), "SITE_SPEC", "site.metal must be an object")
        need(isinstance(m.get("resname"), str) and m["resname"], "SITE_SPEC", "site.metal.resname")
        need(type(s.get("coordination")) is int and 2 <= s["coordination"] <= 8, "SITE_SPEC", "site.coordination")
        need(s.get("class") is None or (isinstance(s["class"], str) and s["class"].isalpha()), "SITE_SPEC", "site.class")
        t = s.get("tau4_min")
        need(t is None or (type(t) in (int, float) and 0.0 <= t <= 1.0), "SITE_SPEC", "site.tau4_min in [0, 1]")
        need(t is None or s["coordination"] == 4, "SITE_SPEC", "site.tau4_min applies only to coordination 4")
        da = s.get("donor_atoms")
        need(da is None or (isinstance(da, dict) and all(k in ONE_LETTER and isinstance(v, str) and v in DONORS[k]
                                                         for k, v in da.items())),
             "SITE_SPEC", "site.donor_atoms: {RESNAME: ATOM}, both upper case and from DONORS")
        lig = s.get("ligands")
        need(lig is None or (isinstance(lig, list) and lig and all(isinstance(x, str) and x for x in lig)),
             "SITE_SPEC", "site.ligands: a list of chain+residue strings such as 'A29'")
        need("windows" not in s or (isinstance(s["windows"], dict) and s["windows"]), "SITE_SPEC",
             "site.windows, when given, must be a non-empty object")
        windows = s.get("windows") or DEFAULT_WINDOWS.get(m["resname"].upper())
        need(isinstance(windows, dict) and windows, "SITE_SPEC", f"no distance windows for {m['resname']}")
        for el, w in windows.items():
            need(isinstance(w, list) and len(w) == 2 and all(type(v) in (int, float) for v in w) and 0 < w[0] < w[1],
                 "SITE_SPEC", f"window {el}")
    return spec


def _metals(atoms: list[dict], m: dict) -> list[dict]:
    hits = [a for a in atoms if a["resname"] == m["resname"].upper()
            and ("chain" not in m or a["chain"] == m["chain"]) and ("resseq" not in m or a["resseq"] == m["resseq"])]
    need(hits, "SITE_NO_METAL", json.dumps(m, sort_keys=True))
    return hits


def listed(a: dict) -> bool:
    """A donor the table names (a side-chain donor atom or a named water oxygen)."""
    return a["name"] in DONORS.get(a["resname"], ())


def ligands(atoms: list[dict], metal: dict, radius: float) -> list[dict]:
    """Every ligand-element atom within radius of the metal, whatever it is called (sorted by distance)."""
    near = [a for a in atoms if a is not metal and a["element"] in LIGAND_ELEMENTS and _dist(a["xyz"], metal["xyz"]) <= radius]
    return sorted(near, key=lambda a: _dist(a["xyz"], metal["xyz"]))


def ligand_class(donors: list[dict]) -> str:
    order = lambda d: (d["chain"], (0, d["resseq"], "") if isinstance(d["resseq"], int) else (1, 0, d["resseq"]))  # noqa: E731
    protein = sorted((d for d in donors if d["resname"] in PROTEIN), key=order)
    return "".join(ONE_LETTER[d["resname"]] if d["resname"] in ONE_LETTER and listed(d) else "x" for d in protein)


def check_site(atoms: list[dict], metal: dict, site: dict, radius: float) -> dict:
    """One metal in one frame. Raises on the first broken rule; returns the measured site otherwise."""
    windows = site.get("windows") or DEFAULT_WINDOWS[site["metal"]["resname"].upper()]
    donors = ligands(atoms, metal, radius)
    tag = f"{metal['resname']} {metal['chain']}{metal['resseq']}"
    unlisted = [f"{d['resname']}{d['resseq']}.{d['name']}" for d in donors if not listed(d)]
    need(len(donors) == site["coordination"], "SITE_COORDINATION",
         f"{tag}: {len(donors)} donors within {radius} A, declared {site['coordination']}"
         + (f" (not in the donor table: {', '.join(unlisted)})" if unlisted else ""))
    klass = ligand_class(donors)
    if site.get("class"):
        need(klass == site["class"].upper(), "SITE_CLASS", f"{tag}: ligands {klass}, declared {site['class']}")
    if site.get("ligands"):
        got = sorted({f"{d['chain']}{d['resseq']}" for d in donors if d["resname"] in PROTEIN})
        need(got == sorted(site["ligands"]), "SITE_LIGANDS", f"{tag}: ligand residues {got}, declared {sorted(site['ligands'])}")
    da = site.get("donor_atoms") or {}
    for d in donors:
        want = da.get(d["resname"], da.get(CANON.get(d["resname"], "")))
        if want is not None and listed(d):
            need(d["name"] == want, "SITE_DONOR", f"{tag}: {d['resname']} {d['resseq']} binds through {d['name']}, declared {want}")
    dists = []
    for d in donors:
        r = _dist(d["xyz"], metal["xyz"])
        w = windows.get(d["element"])
        need(w is not None, "SITE_DISTANCE", f"{tag}: no window for donor element {d['element']}")
        need(w[0] <= r <= w[1], "SITE_DISTANCE", f"{tag}: {d['resname']} {d['resseq']} {d['name']} at {r:.3f} A, window {w}")
        dists.append({"donor": f"{d['resname']}{d['resseq']}.{d['name']}", "element": d["element"], "angstrom": round(r, 4)})
    out = {"site": tag, "class": klass, "coordination": len(donors), "distances": dists}
    if len(donors) == 4:
        t = tau4(metal["xyz"], [d["xyz"] for d in donors])
        out["tau4"] = round(t, 4)
        if site.get("tau4_min") is not None:
            need(t >= site["tau4_min"], "SITE_GEOMETRY", f"{tag}: tau4 {t:.3f} below {site['tau4_min']}")
    return out


def check(text: str, spec: dict) -> dict:
    """Check every declared site in every frame. Returns measurements; raises on the first broken rule."""
    spec = load_spec(spec)
    stats: dict = {}
    frames = parse_pdb(text, stats)
    nn = median_nearest_neighbour(frames[0])
    need(nn >= 0.5, "SITE_UNITS", f"median nearest-neighbour distance {nn:.3f}: nanometres read as angstrom?")
    radius, need_fraction = float(spec.get("search_radius", 3.0)), float(spec.get("min_intact_fraction", 1.0))
    sites_out, selected = [], set()
    for site in spec["sites"]:
        for metal0 in _metals(frames[0], site["metal"]):
            idx = frames[0].index(metal0)
            need(idx not in selected, "SITE_SPEC", f"two site entries select {metal0['resname']} {metal0['chain']}{metal0['resseq']}")
            selected.add(idx)
            per_frame, failures = [], []
            for i, atoms in enumerate(frames):
                try:
                    per_frame.append(check_site(atoms, atoms[idx], site, radius))
                except GateError as e:
                    if len(frames) == 1:
                        raise
                    failures.append({"frame": i, "code": e.code, "detail": e.detail})
            intact = len(per_frame) / len(frames)
            first = (f"; first failure at frame {failures[0]['frame']}: {failures[0]['code']} ({failures[0]['detail']})"
                     if failures else "")
            need(intact >= need_fraction, "SITE_INTACT_FRACTION",
                 f"{metal0['resname']} {metal0['chain']}{metal0['resseq']}: intact in {len(per_frame)} of {len(frames)} frames, "
                 f"declared at least {need_fraction}{first}")
            all_d = [d["angstrom"] for f in per_frame for d in f["distances"]]
            taus = [f["tau4"] for f in per_frame if "tau4" in f]
            sites_out.append({"site": per_frame[0]["site"], "class": per_frame[0]["class"],
                              "frames_intact": len(per_frame), "frames": len(frames),
                              "distance_min": min(all_d), "distance_max": max(all_d),
                              "tau4_min": min(taus) if taus else None, "failures": failures[:5],
                              "first_frame": per_frame[0]})
    metals = [i for i, a in enumerate(frames[0]) if a["resname"] in METAL_NAMES or a["element"] in METAL_NAMES]
    tagof = lambda a: f"{a['resname']} {a['chain']}{a['resseq']}"  # noqa: E731
    return {"inventory": {"atoms_per_frame": len(frames[0]), "frames": len(frames),
                          "metals_checked": len(sites_out), "median_nn_angstrom": round(nn, 4),
                          "metal_atoms_in_file": [tagof(frames[0][i]) for i in metals],
                          "undeclared_metals": [tagof(frames[0][i]) for i in metals if i not in selected],
                          "altloc_skipped": stats["altloc_skipped"]},
            "sites": sites_out}


def read_coordinates(path: Path) -> str:
    """PDB text from a plain or gzip file (archive files ship as .ent.gz). Latin-1 keeps every byte in its column."""
    data = Path(path).read_bytes()
    if Path(path).suffix == ".gz":
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError) as e:
            raise GateError("SITE_PARSE", f"{Path(path).name}: not a readable gzip file ({e})") from None
    return data.decode("latin-1")


def check_files(paths: list[Path], spec: dict) -> dict:
    need(paths, "SITE_PARSE", "no coordinate files matched")
    return {p.as_posix(): check(read_coordinates(p), spec) for p in paths}
