"""Data-true witness for the look-v2 Site scenes: every v1 check, plus the three the remix audit asked for.

  python3 scene_truth_v2.py   # run from the candidate root, beside scene_truth.py (the v1 reader, imported, not copied)

v1 checks positions, selection, bonds, glow, labels and tube anchors, so a zinc drawn with the carbon material
would pass it (it did, in a second model's re-render). v2 adds:

  ATOM_COLOUR   every atom Transform draws the shape for its own element as the deposited file names it
                (DEF or USE ATOM_<element>, zinc as ATOM_ZN), and the element shapes' colours are pairwise distinct
  CAGE          a coordination cage is drawn for a zinc exactly when it has four ligands and all four glow, and its
                face and edge vertices are exactly those four donor coordinates (3 decimals)
  DONOR_NAME    each label's name line reads the donor's residue, number and atom as deposited

It does not import the scene builder. Exit 0 when every check holds, 1 on any violation, 2 on an instrument error.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scene_truth as v1  # noqa: E402

COLOUR_ATTRS = ("baseColor", "diffuseColor")


def colour_of(shape) -> str | None:
    for m in shape.iter():
        if m.tag in ("PhysicalMaterial", "Material"):
            for a in COLOUR_ATTRS:
                if m.get(a):
                    return " ".join(v1.f3(c) for c in v1.floats(m.get(a)))
    return None


def check_v2(pid: str) -> tuple[list[str], dict]:
    bad = []
    spec = v1.json.loads(Path(f"specs/{pid}.json").read_text())
    atoms, elements = v1.model1(Path(f"structures/pdb{pid}.ent.gz"))
    root = ET.parse(f"scenes/{pid}.x3d").getroot()
    defs = {el.get("DEF"): el for el in root.iter() if el.get("DEF")}
    protos = {}
    for name, el in defs.items():
        if name.startswith("A_") and el.tag == "Transform":
            _, ch, res, seq, at = name.split("_", 4)
            k = (ch, res, int(seq), at)
            want = "ATOM_ZN" if res == "ZN" else f"ATOM_{elements.get(k, '?')}"
            sh = el.find("Shape")
            got = sh.get("DEF") or sh.get("USE") if sh is not None else None
            if got != want:
                bad.append(f"ATOM_COLOUR {pid} {name}: draws {got}, its element in the file gives {want}")
            if sh is not None and sh.get("DEF"):
                protos[sh.get("DEF")] = colour_of(sh)
    cols = [c for c in protos.values()]
    if None in cols or len(set(cols)) != len(cols):
        bad.append(f"ATOM_COLOUR {pid}: element colours not pairwise distinct {protos}")
    _, bonds = v1.expected(atoms, elements, spec)
    sites = {}
    for z, d in bonds:
        sites.setdefault(z, []).append(d)
    cages = 0
    for z, ds in sites.items():
        cname = f"Cage_{z[0]}{z[2]}"
        due = len(ds) == 4 and all(np.linalg.norm(atoms[d] - atoms[z]) < v1.GLOW_BELOW for d in ds)
        have = cname in defs
        cages += have
        if have != due:
            bad.append(f"CAGE {pid} {cname}: drawn={have}, due={due} ({len(ds)} ligands)")
        if have:
            want_pts = sorted(" ".join(v1.f3(c) for c in atoms[d]) for d in ds)
            for part in (cname, cname + "_edges"):
                c = defs.get(part)
                co = c.find(".//Coordinate") if c is not None else None
                v = v1.floats(co.get("point", "")) if co is not None else []
                got = sorted(" ".join(v1.f3(x) for x in v[i:i + 3]) for i in range(0, len(v), 3))
                if got != want_pts:
                    bad.append(f"CAGE {pid} {part}: vertices {got} are not the donors {want_pts}")
    names = 0
    for z, ds in sites.items():
        for d in ds:
            tag = f"{z[0]}{z[2]}_{d[1]}{d[2]}_{d[3]}"
            n = defs.get("Name_" + tag)
            t = n.find(".//Text") if n is not None else None
            names += t is not None
            if t is None or t.get("string", "").strip('"') != f"{d[1]} {d[2]} {d[3]}":
                bad.append(f"DONOR_NAME {pid} Label_{tag}: name {t.get('string') if t is not None else None}, donor {d[1]} {d[2]} {d[3]}")
    return bad, {"cages": cages, "names": names, "element_shapes": len(protos)}


def main() -> int:
    code = v1.main()
    if code == 2:
        return 2
    problems = []
    for s in sorted(Path("scenes").glob("*.x3d")):
        bad, t = check_v2(s.stem)
        problems += bad
        print(f"{s.stem}: v2 {'ok' if not bad else 'VIOLATED'} cages {t['cages']} donor names {t['names']} element shapes {t['element_shapes']}")
    for p in problems:
        print("VIOLATION", p)
    return 1 if (problems or code) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # an instrument crash is an error, never a pass or a fail (law 19)
        print("INSTRUMENT_ERROR", repr(e)); sys.exit(2)
