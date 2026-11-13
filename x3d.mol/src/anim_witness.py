#!/usr/bin/env python3 -I
"""Witness for the diffusion illustrations: does each keyframe scene end on the source atoms and follow its stated schedule?

  python3 -I src/anim_witness.py scenes/anim/1aay.anim.x3d [more ...]   # exit 0 only if every scene passes

Independence: imports neither gemmi nor the xmol package nor src/anim.py. It reads the source with witness.py's own line
parser, matches atoms by position (not by order), and recomputes the AlphaFold 3 noise schedule from the four numbers the
scene states. What it shares with the generator, by design, is the written rules: the schedule formula, the tanh cap, the
element and pLDDT palettes, and the 0.35 screen-time weight for keys still at the cap.

One stable code per cause:
  ANIM_DISCLAIMER  the scene does not say it is an illustration and not a live run
  ANIM_SOURCE      the source file's sha256 differs from the one written in the scene
  ANIM_COUNT       the number of points differs from the source's polymer heavy atoms plus zinc
  ANIM_FINAL       the last key, the held key or the rest Coordinate is not the source atoms one-to-one (0.002 angstrom)
  ANIM_KEYS        keys not 0 .. 1 and increasing, wrong keyValue length, or key times not the stated warp
  ANIM_SCHEDULE    stated sigma differs from the formula, shown noise not cap * tanh(sigma / cap), or the measured spread
                   of a key is not within 0.7 .. 1.3 of the shown noise (plus the stated lag bound)
  ANIM_ROUTE       clock, interpolator and coordinate are not wired fraction -> set_fraction -> set_point after the nodes,
                   or the clock is not a 12 s loop
  ANIM_COLOR       a point's colour is not the palette colour of its matched source atom
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
from lxml import etree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import witness as WT  # noqa: E402  (its parser only: no gemmi, no xmol)

ELEMENT = {"C": (0.55, 0.62, 0.68), "N": (0.25, 0.45, 1.0), "O": (1.0, 0.28, 0.25), "S": (1.0, 0.85, 0.25), "P": (1.0, 0.55, 0.1),
           "SE": (0.9, 0.6, 0.2), "ZN": (0.70, 0.80, 0.92)}
FINAL_TOL, COLOR_TOL = 0.002, 0.002


def source_atoms(path: Path, kind: str):
    """Polymer heavy atoms (residues with a guide atom) plus zinc: xyz, expected colour."""
    res, zn = WT.residues_of(WT.parse_source(path))
    xyz, rgb = [], []
    for r in res:
        for a in r["atoms"]:
            xyz.append(a["xyz"])
            rgb.append(WT.band_rgb(r["b"]) if kind == "afdb" else ELEMENT.get(a["el"], (0.8, 0.8, 0.8)))
    for a in zn:
        xyz.append(a["xyz"]); rgb.append(ELEMENT["ZN"])
    return np.array(xyz), np.array(rgb)


def match(points: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, float]:
    """For each point, the index of the nearest reference atom and the worst distance. Chunked brute force."""
    idx, worst = np.empty(len(points), dtype=np.int64), 0.0
    for i in range(0, len(points), 512):
        d = np.linalg.norm(points[i:i + 512, None, :] - ref[None, :, :], axis=2)
        j = d.argmin(1)
        idx[i:i + 512] = j
        worst = max(worst, float(d[np.arange(len(j)), j].max()))
    return idx, worst


def check(path: Path) -> list[tuple[str, str]]:
    fails: list[tuple[str, str]] = []
    root = etree.parse(str(path)).getroot()
    meta = {m.get("name"): m.get("value") for m in root.iter("MetadataString", "MetadataFloat", "MetadataInteger")}
    mf = lambda k: WT.floats(meta.get(k, ""))
    ms = lambda k: (meta.get(k) or "").strip().strip('"')
    if "not a live run" not in (meta.get("disclaimer") or "") or "Illustration" not in (meta.get("disclaimer") or ""):
        fails.append(("ANIM_DISCLAIMER", "no illustration disclaimer"))
    kind = ms("source_kind")
    src = ROOT / "data" / ("afdb" if kind == "afdb" else "pdb") / ms("source_file")
    if not src.exists() or hashlib.sha256(src.read_bytes()).hexdigest() != ms("source_sha256"):
        return fails + [("ANIM_SOURCE", f"{src.name}: missing or sha256 differs")]
    ref, ref_rgb = source_atoms(src, kind)

    coord = next(root.iter("Coordinate"), None)
    interp = next(root.iter("CoordinateInterpolator"), None)
    clock = next(root.iter("TimeSensor"), None)
    color = next(root.iter("Color"), None)
    if coord is None or interp is None or clock is None or color is None:
        return fails + [("ANIM_ROUTE", "Coordinate, CoordinateInterpolator, TimeSensor or Color missing")]
    rest = WT.floats(coord.get("point", "")).reshape(-1, 3)
    n = len(rest)
    if n != len(ref):
        fails.append(("ANIM_COUNT", f"{n} points, source has {len(ref)}"))
    keys = WT.floats(interp.get("key", ""))
    kv = WT.floats(interp.get("keyValue", ""))
    if len(kv) != len(keys) * n * 3 or n == 0:
        return fails + [("ANIM_KEYS", f"keyValue has {len(kv)} numbers, expected {len(keys)} x {n} x 3")]
    frames = kv.reshape(len(keys), n, 3)
    if keys[0] != 0 or keys[-1] != 1 or np.any(np.diff(keys) <= 0):
        fails.append(("ANIM_KEYS", "keys not 0 .. 1 strictly increasing"))

    # final: rest, last denoise key and held key are the source atoms, one to one
    for label, pts in (("rest", rest), ("last key", frames[-2]), ("held key", frames[-1])):
        if len(pts) != len(ref):
            continue
        j, worst = match(pts, ref)
        if worst > FINAL_TOL or len(set(j.tolist())) != len(ref):
            fails.append(("ANIM_FINAL", f"{label}: worst {worst:.4f} A, {len(ref) - len(set(j.tolist()))} source atoms unmatched"))
            break
    else:
        j, _ = match(rest, ref)
        col = WT.floats(color.get("color", "")).reshape(-1, 3)
        if len(col) != n or np.abs(col - ref_rgb[j]).max() > COLOR_TOL:
            bad = int((np.abs(col - ref_rgb[j]).max(1) > COLOR_TOL).sum()) if len(col) == n else n
            fails.append(("ANIM_COLOR", f"{bad} points off palette"))

    # schedule: sigma from the stated parameters, shown = cap tanh(sigma/cap), measured spread follows it
    sd, smax, smin, rho = mf("schedule")
    u = mf("schedule_t")
    cap = float(mf("cap")[0])
    want = sd * (smax ** (1 / rho) + u * (smin ** (1 / rho) - smax ** (1 / rho))) ** rho
    shown = cap * np.tanh(want / cap)
    shown[-1] = 0.0
    if len(u) != len(keys) - 1 or np.abs(mf("sigma") - want).max() > 1e-3 * np.maximum(want, 1).max() or np.abs(mf("sigma_shown") - shown).max() > 2e-3:
        fails.append(("ANIM_SCHEDULE", "stated sigma or shown noise differs from the formula"))
    else:
        w = np.where(shown >= 0.98 * cap, 0.35, 1.0)
        c = np.concatenate([[0.0], np.cumsum(w[1:])])
        if np.abs(keys[:-1] - float(mf("denoise_fraction")[0]) * c / c[-1]).max() > 2e-4:
            fails.append(("ANIM_KEYS", "key times are not the stated warp of schedule time"))
        lag = float(mf("lag")[0])
        conf = mf("plddt") if lag else np.zeros(n)
        bound = lag * np.sqrt(np.mean((1 - np.clip(conf, 0, 100) / 100) ** 2)) * np.sqrt(3) if lag else 0.0
        spread = np.sqrt(((frames[:-1] - frames[-1][None]) ** 2).sum(2).mean(1))   # rms distance, includes sqrt(3) for 3 axes
        for k in range(len(u) - 1):
            s3 = shown[k] * np.sqrt(3)
            lo, hi = 0.7 * s3, 1.3 * s3 + 1.3 * bound * (1 - u[k]) ** 1.5 + 0.02
            if not lo <= spread[k] <= hi:
                fails.append(("ANIM_SCHEDULE", f"key {k}: spread {spread[k]:.2f} A outside {lo:.2f} .. {hi:.2f}"))
                break
        if spread[0] < 10:
            fails.append(("ANIM_SCHEDULE", f"first key spread {spread[0]:.2f} A: no visible noise"))

    # wiring
    if clock.get("loop") != "true" or abs(float(clock.get("cycleInterval", "0")) - 12) > 1e-6:
        fails.append(("ANIM_ROUTE", "clock is not a 12 s loop"))
    order = list(root.iter())
    pos = {id(e): i for i, e in enumerate(order)}
    routes = [(r.get("fromNode"), r.get("fromField"), r.get("toNode"), r.get("toField"), pos[id(r)]) for r in root.iter("ROUTE")]
    need = [(clock.get("DEF"), "fraction_changed", interp.get("DEF"), "set_fraction"), (interp.get("DEF"), "value_changed", coord.get("DEF"), "set_point")]
    last_node = max(pos[id(clock)], pos[id(interp)], pos[id(coord)])
    for nd in need:
        hit = [r for r in routes if r[:4] == nd]
        if not hit or hit[0][4] < last_node or None in nd:
            fails.append(("ANIM_ROUTE", f"missing or early ROUTE {nd}"))
    return fails


def main(argv: list[str]) -> int:
    bad = 0
    for p in argv:
        f = check(Path(p))
        print(("ok  " if not f else "FAIL"), p, "; ".join(f"{c}: {m}" for c, m in f))
        bad += bool(f)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
