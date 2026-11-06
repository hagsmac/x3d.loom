"""Negative controls for the look-v2 data-true witness (law 19: a control fails for the intended reason).

  python3 -I kit/examples/zinc_scene_truth_v2_controls.py CANDIDATE PYTHON OUT.json

Runs the nine v1 controls against scene_truth_v2.py (it keeps every v1 check), then six controls for the checks v2
adds. Each copies the candidate, makes one small edit to one scene (1RGO), runs scene_truth_v2.py with PYTHON (a
python with MDAnalysis), and requires exit 1 with the FIRST violation carrying the intended code. The first v2
control is the remix's own bug: the zinc drawn with the carbon material.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import zinc_scene_truth_controls as c1  # noqa: E402

once = c1.once


def zinc_as_carbon(t):  # a zinc drawn with carbon's material (the remix bug), position untouched
    return once(r"(<Transform DEF='A_A_ZN_222_ZN'[^>]*>)<Shape USE='ATOM_ZN'/>", lambda m: m.group(1) + "<Shape USE='ATOM_C'/>", t)


def same_colour(t):  # sulfur painted the carbon colour (two elements no longer distinguishable)
    return once(r"(<Shape DEF='ATOM_S'><Appearance><PhysicalMaterial baseColor=')[^']*", lambda m: m.group(1) + "0.27 0.37 0.44", t)


def drop_cage(t):  # a due cage left out
    t = once(r"<Shape DEF='Cage_A221'>.*?</Shape>", "", t)
    return once(r"<Shape DEF='Cage_A221_edges'>.*?</Shape>", "", t)


def bend_cage(t):  # a cage vertex nudged 0.05 A off its donor
    return once(r"(DEF='Cage_A221'>.*?point=')(-?\d+\.\d+)", lambda m: m.group(1) + f"{float(m.group(2)) + 0.05:.3f}", t)


def bend_edges(t):  # the edge lines drawn off the donors while the faces stay true
    return once(r"(DEF='Cage_A221_edges'>.*?point=')(-?\d+\.\d+)", lambda m: m.group(1) + f"{float(m.group(2)) + 0.05:.3f}", t)


def wrong_name(t):  # a label names the wrong cysteine
    return once(r"(DEF='Name_A221_CYS159_SG'>.*?string='\")CYS 159", lambda m: m.group(1) + "CYS 162", t)


V2 = [("zinc drawn with carbon's material", "ATOM_COLOUR", zinc_as_carbon),
      ("sulfur painted carbon's colour", "ATOM_COLOUR", same_colour),
      ("due cage left out", "CAGE", drop_cage),
      ("cage vertex off its donor", "CAGE", bend_cage),
      ("cage edges off the donors", "CAGE", bend_edges),
      ("label names the wrong cysteine", "DONOR_NAME", wrong_name)]


if __name__ == "__main__":
    src = Path(c1.__file__).read_text()
    assert "scene_truth.py" in src
    c1.CONTROLS = c1.CONTROLS + V2
    orig = c1.subprocess.run
    c1.subprocess.run = lambda cmd, **kw: orig([cmd[0], "scene_truth_v2.py"] + cmd[2:], **kw)
    sys.exit(c1.main(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])))
