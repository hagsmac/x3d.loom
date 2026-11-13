#!/usr/bin/env python3 -I
"""Negative and positive controls for src/anim_witness.py.

  /path/to/python -I tests/test_anim_witness.py      # needs scenes/anim/ built by src/anim.py

Every control edits a copy of a real diffusion scene and must be rejected with its own stable code; the unedited scenes, and
a copy whose atom order is shuffled consistently, must pass. A control that is NOT rejected fails this test.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import anim_witness as AW  # noqa: E402

ANIM = ROOT / "scenes/anim"


def fl(s: str) -> np.ndarray:
    return np.array(s.split(), dtype=np.float64)


def fmt(a, nd: int = 3) -> str:
    return " ".join(("%.*f" % (nd, x)).rstrip("0").rstrip(".") if abs(x) > 1e-12 else "0" for x in np.asarray(a).ravel())


def meta(root, name):
    for m in root.iter("MetadataString", "MetadataFloat", "MetadataInteger"):
        if m.get("name") == name:
            return m
    raise KeyError(name)


def node(root, tag):
    return next(root.iter(tag))


def frames(root):
    ci = node(root, "CoordinateInterpolator")
    k = fl(ci.get("key"))
    return ci, k, fl(ci.get("keyValue")).reshape(len(k), -1, 3)


def set_frames(ci, f):
    ci.set("keyValue", fmt(f))


def drop_disclaimer(r):
    meta(r, "disclaimer").set("value", '"Live AlphaFold 3 prediction"')


def wrong_sha(r):
    meta(r, "source_sha256").set("value", '"' + "0" * 64 + '"')


def drop_atom(r):
    c = node(r, "Coordinate"); col = node(r, "Color"); ci, k, f = frames(r)
    c.set("point", fmt(fl(c.get("point")).reshape(-1, 3)[1:]))
    col.set("color", fmt(fl(col.get("color")).reshape(-1, 3)[1:], 4))
    set_frames(ci, f[:, 1:])


def drop_zinc(r):
    cls = fl(meta(r, "atom_class").get("value")).astype(int)
    keep = cls != 3
    c = node(r, "Coordinate"); col = node(r, "Color"); ci, k, f = frames(r)
    c.set("point", fmt(fl(c.get("point")).reshape(-1, 3)[keep]))
    col.set("color", fmt(fl(col.get("color")).reshape(-1, 3)[keep], 4))
    set_frames(ci, f[:, keep])


def last_key_off(r):
    ci, k, f = frames(r)
    f[-2, 7] += [0.05, 0, 0]
    set_frames(ci, f)


def rest_shift(r):
    c = node(r, "Coordinate")
    c.set("point", fmt(fl(c.get("point")) + 0.01))


def keys_not_increasing(r):
    ci = node(r, "CoordinateInterpolator")
    k = fl(ci.get("key")); k[3], k[4] = k[4], k[3]
    ci.set("key", fmt(k, 4))


def keyvalue_short(r):
    ci = node(r, "CoordinateInterpolator")
    ci.set("keyValue", " ".join(ci.get("keyValue").split()[:-3]))


def keys_unwarped(r):
    ci = node(r, "CoordinateInterpolator")
    k = fl(ci.get("key")); k[:-1] = np.linspace(0, 0.8, len(k) - 1)
    ci.set("key", fmt(k, 4))


def rho_changed(r):
    m = meta(r, "schedule"); v = fl(m.get("value")); v[3] = 5
    m.set("value", fmt(v, 6))


def noise_halved(r):
    ci, k, f = frames(r)
    f[:-2] = f[-1] + 0.5 * (f[:-2] - f[-1])
    set_frames(ci, f)


def no_noise(r):
    ci, k, f = frames(r)
    f[:] = f[-1]
    set_frames(ci, f)


def route_early(r):
    rt = next(r.iter("ROUTE")); sc = rt.getparent(); sc.remove(rt); sc.insert(0, rt)


def route_wrong_field(r):
    rts = list(r.iter("ROUTE")); rts[1].set("toField", "set_vector")


def clock_six(r):
    node(r, "TimeSensor").set("cycleInterval", "6")


def one_colour_off(r):
    col = node(r, "Color"); c = fl(col.get("color")).reshape(-1, 3); c[11] = [1, 0, 1]
    col.set("color", fmt(c, 4))


def pdb_one_colour(r):
    col = node(r, "Color"); c = fl(col.get("color")).reshape(-1, 3); c[:] = [0.0, 0.3255, 0.8392]
    col.set("color", fmt(c, 4))


CONTROLS = [
    ("disclaimer replaced", "1aay", drop_disclaimer, "ANIM_DISCLAIMER"),
    ("source sha256 wrong", "AF-P04637-F1", wrong_sha, "ANIM_SOURCE"),
    ("one atom dropped everywhere", "AF-P04637-F1", drop_atom, "ANIM_COUNT"),
    ("zinc dropped everywhere", "1aay", drop_zinc, "ANIM_COUNT"),
    ("last key: one atom 0.05 A off", "1aay", last_key_off, "ANIM_FINAL"),
    ("rest pose shifted 0.01 A", "AF-P04637-F1", rest_shift, "ANIM_FINAL"),
    ("two keys swapped", "1aay", keys_not_increasing, "ANIM_KEYS"),
    ("keyValue one point short", "1aay", keyvalue_short, "ANIM_KEYS"),
    ("key times without the warp", "AF-P04637-F1", keys_unwarped, "ANIM_KEYS"),
    ("stated rho 5 instead of 7", "1aay", rho_changed, "ANIM_SCHEDULE"),
    ("noise halved", "AF-P04637-F1", noise_halved, "ANIM_SCHEDULE"),
    ("no noise at all", "1aay", no_noise, "ANIM_SCHEDULE"),
    ("ROUTE before the nodes", "1aay", route_early, "ANIM_ROUTE"),
    ("ROUTE to the wrong field", "AF-P04637-F1", route_wrong_field, "ANIM_ROUTE"),
    ("clock 6 s", "1aay", clock_six, "ANIM_ROUTE"),
    ("one colour off palette", "AF-P04637-F1", one_colour_off, "ANIM_COLOR"),
    ("crystal coloured as one pLDDT band", "1aay", pdb_one_colour, "ANIM_COLOR"),
]
POSITIVE = ["1aay", "AF-P04637-F1"]


def shuffled(r):
    """Same atoms in another order, consistently in rest, keys and colours: must still pass (matching is by position)."""
    c = node(r, "Coordinate"); col = node(r, "Color"); ci, k, f = frames(r)
    p = np.random.default_rng(7).permutation(f.shape[1])
    c.set("point", fmt(fl(c.get("point")).reshape(-1, 3)[p]))
    col.set("color", fmt(fl(col.get("color")).reshape(-1, 3)[p], 4))
    f = f[:, p]
    ci.set("keyValue", " ".join(fmt(x, 3) for x in f))


def main() -> int:
    rows, bad = [], 0
    tmp = Path(tempfile.mkdtemp(prefix="xmol-anim-controls-"))
    for scene in POSITIVE:
        f = AW.check(ANIM / f"{scene}.anim.x3d")
        ok = not f
        bad += not ok
        rows.append({"kind": "positive", "scene": scene, "control": "unedited", "expected": "pass", "got": "pass" if ok else [c for c, _ in f], "ok": ok})
    for scene in POSITIVE:
        tree = etree.parse(str(ANIM / f"{scene}.anim.x3d"))
        shuffled(tree.getroot())
        p = tmp / f"{scene}-shuffled.anim.x3d"
        tree.write(str(p), encoding="utf-8", xml_declaration=True)
        f = AW.check(p)
        ok = not f
        bad += not ok
        rows.append({"kind": "positive", "scene": scene, "control": "atom order shuffled", "expected": "pass", "got": "pass" if ok else [c for c, _ in f], "ok": ok})
    for name, scene, edit, code in CONTROLS:
        tree = etree.parse(str(ANIM / f"{scene}.anim.x3d"))
        edit(tree.getroot())
        p = tmp / f"{scene}-{code}.anim.x3d"
        tree.write(str(p), encoding="utf-8", xml_declaration=True)
        got = sorted({c for c, _ in AW.check(p)})
        ok = code in got
        bad += not ok
        rows.append({"kind": "negative", "scene": scene, "control": name, "expected": code, "got": got, "ok": ok})
    for r in rows:
        print(("ok   " if r["ok"] else "FAIL ") + f"{r['kind']:8} {r['scene']:13} {r['control']:36} want {r['expected']:15} got {r['got']}")
    (ROOT / "tests/last-anim-run.json").write_text(json.dumps({"witness": "x3d.mol/src/anim_witness.py", "controls": rows, "negative": len(CONTROLS),
                                                                "positive": len(rows) - len(CONTROLS), "failed": bad}, indent=1))
    print(f"\n{len(CONTROLS)} negative controls, {len(rows) - len(CONTROLS)} positive controls, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
