"""Negative controls for the data-true witness of the zinc Site scenes (law 19: a control fails for the intended reason).

  python3 -I kit/examples/zinc_scene_truth_controls.py CANDIDATE PYTHON OUT.json

Each of the nine controls copies the candidate, makes one small edit to one scene (1RGO), runs scene_truth.py with PYTHON (a python
with MDAnalysis), and requires exit 1 with the FIRST violation carrying the intended code. A control that passes is
SURVIVING_CONTROL; one that fails with another code, or with exit 2, is a broken test and also fails this script.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCENE = "scenes/1rgo.x3d"


def once(pattern: str, repl, text: str) -> str:
    out, n = re.subn(pattern, repl, text, count=1)
    if n != 1:
        raise RuntimeError(f"CONTROL_FIXTURE: pattern not found: {pattern}")
    return out


def shift_atom(t):  # an atom moved 0.01 A for looks
    return once(r"(DEF='A_A_CYS_159_SG' translation=')(-?\d+\.\d+)", lambda m: m.group(1) + f"{float(m.group(2)) + 0.01:.3f}", t)


def drop_atom(t):  # a selected atom left out
    return once(r"<Transform DEF='A_A_CYS_159_CB'[^>]*>.*?</Transform>", "", t)


def extra_atom(t):  # an atom drawn that the rule did not select
    return t.replace("</Scene>", "<Transform DEF='A_A_SER_150_CA' translation='0.000 0.000 0.000'><Shape USE='ATOM_C'/></Transform></Scene>", 1)


def dark_glow(t):  # a short bond drawn dark
    return once(r"(DEF='Bond_A221_CYS159_SG'.*?emissiveColor=')[^']*'", lambda m: m.group(1) + "0 0 0'", t)


def bad_label(t):  # a label that rounds the wrong way
    return once(r"(DEF='Label_A221_CYS159_SG'.*?string='\")[\d.]+", lambda m: m.group(1) + "2.31", t)


def swap_labels(t):  # two labels trade places (each still prints a true length, now beside the wrong bond)
    a = re.search(r"DEF='Label_A221_CYS159_SG' translation='([^']*)'", t).group(1)
    b = re.search(r"DEF='Label_A221_CYS168_SG' translation='([^']*)'", t).group(1)
    t = once(r"(DEF='Label_A221_CYS159_SG' translation=')[^']*", lambda m: m.group(1) + b, t)
    return once(r"(DEF='Label_A221_CYS168_SG' translation=')[^']*", lambda m: m.group(1) + a, t)


def turn_bond(t):  # a bond cylinder rotated off its atoms, length and label untouched
    return once(r"(DEF='Bond_A221_CYS159_SG'[^>]*rotation='[^']* )([\d.]+)'", lambda m: m.group(1) + f"{float(m.group(2)) + 0.2:.6f}'", t)


def drop_bond(t):  # a rule bond not drawn, its label kept
    return once(r"<Transform DEF='Bond_A221_CYS159_SG'[^>]*>.*?</Transform>", "", t)


def bend_tube(t):  # a backbone control point nudged off its C-alpha
    return once(r"(spine=')(-?\d+\.\d+)", lambda m: m.group(1) + f"{float(m.group(2)) + 0.05:.3f}", t)


CONTROLS = [("atom moved 0.01 A", "ATOM_POSITION", shift_atom),
            ("selected atom left out", "ATOM_SELECTION", drop_atom),
            ("unselected atom drawn", "ATOM_SELECTION", extra_atom),
            ("short bond drawn dark", "BOND_GLOW", dark_glow),
            ("label off by 0.01", "BOND_LABEL", bad_label),
            ("two labels swap places", "LABEL_PLACE", swap_labels),
            ("bond turned off its atoms", "BOND_GEOMETRY", turn_bond),
            ("rule bond not drawn", "BOND_SET", drop_bond),
            ("tube point off its C-alpha", "TUBE_ANCHOR", bend_tube)]


def main(cand: Path, python: str, out: Path) -> int:
    rows = []
    for label, code, edit in CONTROLS:
        with tempfile.TemporaryDirectory(prefix="scene-truth-") as d:
            root = Path(d) / "cand"
            shutil.copytree(cand, root)
            p = root / SCENE
            p.write_text(edit(p.read_text(encoding="utf-8")), encoding="utf-8")
            r = subprocess.run([python, "scene_truth.py"], cwd=root, capture_output=True, text=True,
                               env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
            first = next((ln.split()[1] for ln in r.stdout.splitlines() if ln.startswith("VIOLATION")), None)
            row = {"control": label, "intended": code, "exit": r.returncode, "first_violation": first,
                   "line": next((ln for ln in r.stdout.splitlines() if ln.startswith("VIOLATION")), r.stdout.strip()[-200:])}
            if r.returncode == 0:
                row["result"] = "SURVIVING_CONTROL"
            elif r.returncode != 1 or first != code:
                row["result"] = "BROKEN_TEST"
            else:
                row["result"] = "caught"
            rows.append(row)
            print(f"{row['result']:17} {label}: {row['line'][:150]}")
    out.write_text(json.dumps({"schema": "loom.zinc-scene-truth-controls/1", "scene": SCENE, "controls": rows}, indent=2) + "\n")
    return 0 if all(r["result"] == "caught" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])))
