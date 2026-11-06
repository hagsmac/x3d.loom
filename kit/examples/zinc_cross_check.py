"""Independent reader for the zinc finger P1 run (law 25): a second library re-reads the archive files and recomputes
what each metal-site witness reported, in every model.

  python3 cross_check.py EVIDENCE_DIR      # run from the candidate root; needs MDAnalysis and numpy

What is independent: file parsing (MDAnalysis's PDB reader, not loomkit's fixed-column parser), atom selection,
distance arithmetic (numpy) and the tau4 geometry. Ligands are found by element (N, O, S, Se, halogens), never by
a name table, so a ligand the witness's table does not name is still counted. What is shared (a shared
assumption, stated): the search radius, the frame-0 metal identity, and the side-chain donor names used only to
spell the ligand class, all read from the same specs.

For a passing record: every frame-0 metal-donor distance, the per-site minimum and maximum over all models, and the
frame count must agree to 0.001 angstrom. For a failing record: the measurement its reason names (a distance, a
donor count, a tau4 or a ligand class, at the frame it names) must be reproduced. Exit 0 when everything agrees,
1 on any disagreement or on a record this reader cannot check, 2 on an instrument error.
"""
from __future__ import annotations

import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
import MDAnalysis as mda  # noqa: E402

SIDE_DONORS = {"CYS": ("SG",), "HIS": ("ND1", "NE2"), "ASP": ("OD1", "OD2"), "GLU": ("OE1", "OE2")}
ONE = {"CYS": "C", "HIS": "H", "ASP": "D", "GLU": "E"}
LIGAND = {"N", "O", "S", "SE", "F", "CL", "BR", "I"}
AMINO = set(ONE) | {"ALA", "ARG", "ASN", "GLN", "GLY", "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL"}
TOL = 0.0011  # the witness rounds to 4 decimals in its measurements and to 3 in its failure text


def tau4(metal, ligands):
    angles = []
    for i in range(len(ligands)):
        for j in range(i + 1, len(ligands)):
            u, v = ligands[i] - metal, ligands[j] - metal
            c = float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v)))
            angles.append(float(np.degrees(np.arccos(max(-1.0, min(1.0, c))))))
    a, b = sorted(angles)[-2:]
    return (360.0 - (a + b)) / 141.0


def site_frames(u, site, radius):
    m = site["metal"]
    sel = u.select_atoms(f"resname {m['resname']} and chainID {m['chain']} and resid {m['resseq']}")
    alt = getattr(u.atoms, "altLocs", None)
    keep = [a for a in sel if alt is None or a.altLoc in ("", "A")]
    if len(keep) != 1:
        raise RuntimeError(f"metal {m} matched {len(keep)} atoms")
    metal = keep[0]
    els = getattr(u.atoms, "elements", None)
    el = lambda a: (a.element if els is not None and a.element else "".join(c for c in a.name if c.isalpha())[:1]).upper()  # noqa: E731
    cands = [a for a in u.atoms if el(a) in LIGAND and a.index != metal.index and (alt is None or a.altLoc in ("", "A"))]
    idx = np.array([a.index for a in cands])
    out = []
    for ts in u.trajectory:
        pos = u.atoms.positions
        d = np.linalg.norm(pos[idx] - pos[metal.index], axis=1)
        near = [(cands[k], float(d[k])) for k in np.argsort(d) if d[k] <= radius]
        lig = [a for a, _ in near]
        prot = sorted((a for a in lig if a.resname in AMINO), key=lambda a: (a.chainID, a.resid))
        out.append({"frame": ts.frame,
                    "dist": {f"{a.resname}{a.resid}.{a.name}": r for a, r in near},
                    "class": "".join(ONE[a.resname] if a.name in SIDE_DONORS.get(a.resname, ()) else "x" for a in prot),
                    "tau4": tau4(pos[metal.index], [pos[a.index] for a in lig]) if len(lig) == 4 else None})
    return out


def main(ev: Path) -> int:
    problems, compared, frames_seen, sites_seen = [], 0, 0, 0
    specs = sorted(Path("specs").glob("*.json"))
    if not specs:
        print("no specs"); return 2
    for sp in specs:
        pid, spec = sp.stem, json.loads(sp.read_text())
        rec = json.loads((ev / f"metal-site-{pid}.json").read_text())
        u = mda.Universe(f"structures/pdb{pid}.ent.gz")
        per_site = {f"ZN {s['metal']['chain']}{s['metal']['resseq']}": site_frames(u, s, spec["search_radius"])
                    for s in spec["sites"]}
        sites_seen += len(per_site)
        frames_seen += u.trajectory.n_frames * len(per_site)
        if rec["status"] == "pass":
            meas = rec["measurements"][f"structures/pdb{pid}.ent.gz"]
            if meas["inventory"]["frames"] != u.trajectory.n_frames:
                problems.append(f"{pid}: frames {meas['inventory']['frames']} vs {u.trajectory.n_frames}")
            for s in meas["sites"]:
                fr = per_site[s["site"]]
                want = {d["donor"]: d["angstrom"] for d in s["first_frame"]["distances"]}
                if set(want) != set(fr[0]["dist"]):
                    problems.append(f"{pid} {s['site']}: donors {sorted(want)} vs {sorted(fr[0]['dist'])}")
                for k, v in want.items():
                    compared += 1
                    if k in fr[0]["dist"] and abs(fr[0]["dist"][k] - v) > TOL:
                        problems.append(f"{pid} {s['site']} {k}: {v} vs {fr[0]['dist'][k]:.4f}")
                allv = [r for f in fr for r in f["dist"].values()]
                compared += 2
                if abs(min(allv) - s["distance_min"]) > TOL or abs(max(allv) - s["distance_max"]) > TOL:
                    problems.append(f"{pid} {s['site']}: range {s['distance_min']}-{s['distance_max']} vs {min(allv):.4f}-{max(allv):.4f}")
            print(f"{pid}: pass, agrees ({len(meas['sites'])} sites, {u.trajectory.n_frames} models)")
            continue
        reason = rec["reason"]
        tag = re.search(r"(ZN [A-Za-z0-9]-?\d+)", reason)
        frame = re.search(r"first failure at frame (\d+)", reason)
        k = int(frame.group(1)) if frame else 0
        if not tag or tag.group(1) not in per_site:
            problems.append(f"{pid}: cannot place the failure: {reason[:120]}"); continue
        f = per_site[tag.group(1)][k]
        inner = reason.split("first failure at frame", 1)[-1]
        if (m := re.search(r"([A-Z]{3}) (-?\d+) (\w+) at ([\d.]+) A", inner)):
            key = f"{m.group(1)}{m.group(2)}.{m.group(3)}"
            got = f["dist"].get(key)
            compared += 1
            ok = got is not None and abs(got - float(m.group(4))) <= TOL
            print(f"{pid}: fail reproduced={ok}: {tag.group(1)} frame {k} {key} witness {m.group(4)} A, reader {got if got is None else round(got, 4)}")
        elif (m := re.search(r"(\d+) donors within ([\d.]+) A", inner)):
            compared += 1
            ok = len(f["dist"]) == int(m.group(1))
            print(f"{pid}: fail reproduced={ok}: {tag.group(1)} frame {k} donors witness {m.group(1)}, reader {len(f['dist'])} {sorted(f['dist'])}")
        elif (m := re.search(r"tau4 ([\d.]+) below", inner)):
            compared += 1
            ok = f["tau4"] is not None and abs(f["tau4"] - float(m.group(1))) <= 0.002
            print(f"{pid}: fail reproduced={ok}: {tag.group(1)} frame {k} tau4 witness {m.group(1)}, reader {f['tau4']}")
        elif (m := re.search(r"ligands (\w+), declared", inner)):
            compared += 1
            ok = f["class"] == m.group(1)
            print(f"{pid}: fail reproduced={ok}: {tag.group(1)} frame {k} class witness {m.group(1)}, reader {f['class']}")
        else:
            ok = False
        if not ok:
            problems.append(f"{pid}: not reproduced: {reason[:160]}")
    print(f"compared {compared} values across {frames_seen} site-frames in {sites_seen} sites of {len(specs)} structures")
    for p in problems:
        print("DISAGREE", p)
    return 1 if problems or compared == 0 else 0


if __name__ == "__main__":
    try:
        sys.exit(main(Path(sys.argv[1])))
    except Exception as e:  # an instrument error is not a disagreement and not a pass
        print(f"INSTRUMENT_ERROR {type(e).__name__}: {e}")
        sys.exit(2)
