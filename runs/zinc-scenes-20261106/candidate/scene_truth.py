"""Data-true witness for the zinc finger Site scenes (law 21: no visual event without a data event).

  python3 scene_truth.py      # run from the candidate root (structures/, specs/, scenes/); needs MDAnalysis and numpy

An independent reader of the X3D and of the deposited files: it does not import the scene builder or loomkit. It
parses each scene with ElementTree and model 1 of the archive file with MDAnalysis, re-derives what the builder's
stated rule says must be drawn, and checks every drawn thing against it:

  ATOM_POSITION   every atom Transform (DEF A_<chain>_<res>_<seq>_<name>) sits at its deposited coordinate, 3 decimals
  ATOM_SELECTION  the atoms drawn are exactly each declared zinc, every ligand-element atom (N, O, S, Se, halogens)
                  within the spec's search radius of it, and the side chain (from CA) of each named side-chain
                  donor among them, in both directions
  BOND_SET        one zinc-donor bond per such donor, no more, no fewer
  BOND_GEOMETRY   each bond cylinder's two ends land on the zinc and on the donor atom (rotation and length together)
  BOND_GLOW       a bond glows (non-black emissive) exactly when its recomputed length is under 2.5 angstrom
  BOND_LABEL      its label prints the recomputed length to two decimals
  LABEL_PLACE     and sits on that bond's own line, 1 angstrom past the donor (so it cannot be read as another bond's)
  TUBE_ANCHOR     every control point of a backbone or nucleic-acid tube is a deposited CA or P coordinate

Shared with the builder, and stated: the side-chain donor names, the side-chain atom lists, the 2.5 angstrom glow line, the label
offset and the Catmull-Rom sampling (4 points per segment). Exit 0 when every check holds, 1 on any violation, 2 on an
instrument error. Each violation prints as VIOLATION <code> <scene> <detail>.
"""
from __future__ import annotations

import json
import math
import sys
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
import MDAnalysis as mda  # noqa: E402

DONORS = {"CYS": ("SG",), "HIS": ("ND1", "NE2"), "ASP": ("OD1", "OD2"), "GLU": ("OE1", "OE2")}
LIGAND = {"N", "O", "S", "SE", "F", "CL", "BR", "I"}
SIDE = {"CYS": ("CA", "CB", "SG"), "HIS": ("CA", "CB", "CG", "ND1", "CD2", "CE1", "NE2"),
        "ASP": ("CA", "CB", "CG", "OD1", "OD2"), "GLU": ("CA", "CB", "CG", "CD", "OE1", "OE2")}
GLOW_BELOW = 2.5
LABEL_BEYOND = 1.0
PER = 4
POS_TOL = 0.0006   # the scene writes three decimals
END_TOL = 0.003    # cylinder ends: 3-decimal midpoint, 6-decimal axis, 4-decimal length


def f3(v: float) -> str:
    s = f"{v:.3f}"
    return "0.000" if s == "-0.000" else s


def floats(s: str) -> list[float]:
    return [float(t) for t in s.replace(",", " ").split()]


def rotate(axis_angle: list[float], v: np.ndarray) -> np.ndarray:
    x, y, z, t = axis_angle
    k = np.array([x, y, z], dtype=float)
    n = np.linalg.norm(k)
    if n < 1e-12 or abs(t) < 1e-12:
        return v
    k /= n
    return v * math.cos(t) + np.cross(k, v) * math.sin(t) + k * np.dot(k, v) * (1 - math.cos(t))


def model1(path: Path):
    u = mda.Universe(str(path))
    u.trajectory[0]
    alt = getattr(u.atoms, "altLocs", None)
    keep = [a for a in u.atoms if alt is None or a.altLoc in ("", "A")]
    els = getattr(u.atoms, "elements", None)
    el = lambda a: (a.element if els is not None and a.element else "".join(c for c in a.name if c.isalpha())[:1]).upper()  # noqa: E731
    return ({(a.chainID, a.resname, int(a.resid), a.name): np.array(a.position, dtype=float) for a in keep},
            {(a.chainID, a.resname, int(a.resid), a.name): el(a) for a in keep})


def expected(atoms: dict, elements: dict, spec: dict) -> tuple[set, list]:
    want, bonds = set(), []
    for site in spec["sites"]:
        m = site["metal"]
        zk = [k for k in atoms if k[0] == m["chain"] and k[2] == int(m["resseq"]) and k[1] == m["resname"]]
        if len(zk) != 1:
            raise RuntimeError(f"metal {m} matched {len(zk)} atoms")
        zk = zk[0]
        want.add(zk)
        for k, xyz in atoms.items():
            if k != zk and elements[k] in LIGAND and np.linalg.norm(xyz - atoms[zk]) <= spec["search_radius"]:
                bonds.append((zk, k))
                want.add(k)
                if k[1] in DONORS and k[3] in DONORS[k[1]]:
                    want |= {s for s in atoms if s[0] == k[0] and s[2] == k[2] and s[3] in SIDE[k[1]]}
    return want, bonds


def check_scene(pid: str) -> tuple[list[str], dict]:
    bad = []
    spec = json.loads(Path(f"specs/{pid}.json").read_text())
    atoms, elements = model1(Path(f"structures/pdb{pid}.ent.gz"))
    root = ET.parse(f"scenes/{pid}.x3d").getroot()
    defs = {el.get("DEF"): el for el in root.iter() if el.get("DEF")}
    drawn = {}
    for name, el in defs.items():
        if name.startswith("A_") and el.tag == "Transform":
            _, ch, res, seq, at = name.split("_", 4)
            drawn[(ch, res, int(seq), at)] = el.get("translation", "")
    want, bonds = expected(atoms, elements, spec)
    for k in sorted(set(drawn) - want):
        bad.append(f"ATOM_SELECTION {pid} drawn but not selected by the rule: {'_'.join(map(str, k))}")
    for k in sorted(want - set(drawn)):
        bad.append(f"ATOM_SELECTION {pid} selected by the rule but not drawn: {'_'.join(map(str, k))}")
    for k, tr in drawn.items():
        if k in atoms:
            got = floats(tr)
            if len(got) != 3 or max(abs(g - c) for g, c in zip(got, atoms[k])) > POS_TOL:
                bad.append(f"ATOM_POSITION {pid} {'_'.join(map(str, k))} at {tr}, deposited {' '.join(f3(c) for c in atoms[k])}")
    seen_bonds, glowing = set(), 0
    for name, el in defs.items():
        if not name.startswith("Bond_"):
            continue
        site, donor, dname = name[5:].split("_", 2)
        hit = [(z, d) for z, d in bonds if f"{z[0]}{z[2]}" == site and f"{d[1]}{d[2]}" == donor and d[3] == dname]
        if len(hit) != 1:
            bad.append(f"BOND_SET {pid} {name}: not one rule bond ({len(hit)})"); continue
        z, d = hit[0]
        seen_bonds.add(hit[0])
        r = float(np.linalg.norm(atoms[d] - atoms[z]))
        mid, rot, sc = np.array(floats(el.get("translation"))), floats(el.get("rotation", "0 0 1 0")), floats(el.get("scale", "1 1 1"))
        half = rotate(rot, np.array([0.0, sc[1] / 2, 0.0]))
        ends = (mid - half, mid + half)
        if np.linalg.norm(ends[0] - atoms[z]) > END_TOL or np.linalg.norm(ends[1] - atoms[d]) > END_TOL:
            bad.append(f"BOND_GEOMETRY {pid} {name}: ends {np.round(ends[0], 3)} {np.round(ends[1], 3)} vs zinc and donor")
        mat = el.find(".//Material")
        lit = mat is not None and any(v > 0 for v in floats(mat.get("emissiveColor", "0 0 0")))
        glowing += lit
        if lit != (r < GLOW_BELOW):
            bad.append(f"BOND_GLOW {pid} {name}: glows={lit} at {r:.4f} A (line {GLOW_BELOW})")
        lab = defs.get("Label_" + name[5:])
        txt = lab.find(".//Text") if lab is not None else None
        if txt is None or txt.get("string", "").strip('"') != f"{r:.2f} Å":
            bad.append(f"BOND_LABEL {pid} {name}: label {txt.get('string') if txt is not None else None}, length {r:.2f} Å")
        if lab is not None:
            want_at = atoms[z] + (r + LABEL_BEYOND) * (atoms[d] - atoms[z]) / r
            at = np.array(floats(lab.get("translation", "0 0 0")))
            if np.linalg.norm(at - want_at) > END_TOL:
                bad.append(f"LABEL_PLACE {pid} Label_{name[5:]} at {lab.get('translation')}, its bond's line puts it at {' '.join(f3(c) for c in want_at)}")
    for b in sorted(set(bonds) - seen_bonds):
        bad.append(f"BOND_SET {pid} rule bond not drawn: {b[0][1]}{b[0][2]} to {b[1][1]}{b[1][2]}.{b[1][3]}")
    anchors = {" ".join(f3(c) for c in xyz) for k, xyz in atoms.items() if k[3] in ("CA", "P")}
    tubes = 0
    for name, el in defs.items():
        if name.startswith(("Backbone_", "Nucleic_")):
            ex = el.find(".//Extrusion")
            v = floats(ex.get("spine", "")) if ex is not None else []
            pts = [" ".join(f3(c) for c in v[i:i + 3]) for i in range(0, len(v), 3)]
            ctrl = pts[::PER] + pts[-1:]
            tubes += 1
            for p in ctrl:
                if p not in anchors:
                    bad.append(f"TUBE_ANCHOR {pid} {name}: control point {p} is not a deposited CA or P"); break
    return bad, {"atoms": len(drawn), "bonds": len(seen_bonds), "glowing": glowing, "tubes": tubes}


def main() -> int:
    scenes = sorted(Path("scenes").glob("*.x3d"))
    if not scenes:
        print("no scenes"); return 2
    problems, tally = [], {}
    for s in scenes:
        bad, t = check_scene(s.stem)
        problems += bad
        tally[s.stem] = t
        print(f"{s.stem}: {'ok' if not bad else 'VIOLATED'} atoms {t['atoms']} bonds {t['bonds']} glowing {t['glowing']} tubes {t['tubes']}")
    total = {k: sum(t[k] for t in tally.values()) for k in ("atoms", "bonds", "glowing", "tubes")}
    print(f"checked {len(scenes)} scenes: {total['atoms']} atoms, {total['bonds']} bonds ({total['glowing']} glowing), {total['tubes']} tubes")
    for p in problems:
        print("VIOLATION", p)
    return 1 if problems else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # an instrument error is not a violation and not a pass
        print(f"INSTRUMENT_ERROR {type(e).__name__}: {e}")
        sys.exit(2)
