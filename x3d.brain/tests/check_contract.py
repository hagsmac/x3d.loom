#!/usr/bin/env python3
"""Brain hero scene: the DEF contract the page builder and tests rely on (standard library only).

    python3 -I check_contract.py SCENE.x3d [SCENE2.x3d ...]

Checks DEF names, node types, whichChoice defaults, the glass shader fields, the PhysicalMaterial structure materials, the SYNTHETIC / alignment
notices in WorldInfo, the 64 px studio faces and that every texture the scene names exists next to it. Exit 0 when all pass, 1 otherwise.
"""
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

STRUCTS = ["thalamus", "caudate", "putamen", "pallidum", "hippocampus", "amygdala", "accumbens", "ventricles", "brainstem", "cerebellum"]
VPS = ["VP_HOME", "VP_LEFT", "VP_RIGHT", "VP_TOP", "VP_FRONT", "VP_MEDIAL", "VP_INSIDE"]
SHADER_FIELDS = ["rimColor", "bodyColor", "rimPower", "baseAlpha", "rimAlpha"]


def png_size(p):
    b = Path(p).read_bytes()[:24]
    return struct.unpack(">II", b[16:24]) if b[:8] == b"\x89PNG\r\n\x1a\n" else None


def check(path):
    path = Path(path)
    errs = []
    root = ET.parse(path).getroot()
    defs = {}
    for el in root.iter():
        d = el.get("DEF")
        if d:
            if d in defs:
                errs.append(f"duplicate DEF {d}")
            defs[d] = el

    def need(name, tag=None, **attrs):
        el = defs.get(name)
        if el is None:
            errs.append(f"missing DEF {name}")
            return None
        if tag and el.tag != tag:
            errs.append(f"{name} is <{el.tag}>, expected <{tag}>")
        for k, v in attrs.items():
            if el.get(k) != str(v):
                errs.append(f"{name}.{k} = {el.get(k)!r}, expected {v!r}")
        return el

    nav = need("NAV", "NavigationInfo", headlight="false")
    if nav is not None and "EXAMINE" not in (nav.get("type") or ""):
        errs.append("NAV type lacks EXAMINE")
    need("BG", "Background")
    for l in ("KEY", "FILL", "RIM"):
        need(l, "DirectionalLight")
    env = need("ENV", "EnvironmentLight")
    for vp in VPS:
        v = need(vp, "Viewpoint")
        if v is not None and not v.get("description"):
            errs.append(f"{vp} has no description")
    need("SW_CORTEX", "Switch", whichChoice=0)
    for h in "LR":
        g = need(f"G_CORTEX_{h}", "Group")
        sh = need(f"SH_CORTEX_{h}", "ComposedShader")
        need(f"TS_CORTEX_{h}", "TouchSensor")
        if sh is not None:
            names = {f.get("name") for f in sh.findall("field")}
            miss = [f for f in SHADER_FIELDS if f not in names]
            if miss:
                errs.append(f"SH_CORTEX_{h} lacks fields {miss}")
        if g is not None and g.find("Shape") is None:
            errs.append(f"G_CORTEX_{h} has no Shape")
        need(f"G_WET_{h}", "Group")
    need("SW_WET", "Switch", whichChoice=-1)
    sw = need("SW_DEEP", "Switch")
    for s in STRUCTS:
        sh = need(f"STRUCT_{s}", "Shape")
        m = need(f"MAT_{s}", "PhysicalMaterial")
        if sh is not None and sh.find(".//IndexedTriangleSet") is None:
            errs.append(f"STRUCT_{s} has no IndexedTriangleSet")
        if sw is not None and sh is not None and sh not in list(sw.iter()):
            errs.append(f"STRUCT_{s} is not inside SW_DEEP")
    need("SW_TRACTS", "Switch")
    need("TRACTS", "Group")
    for t in ("TRACT_CORE", "TRACT_HALO1", "TRACT_HALO2"):
        need(t, "Shape")
    sl = need("SW_SLICES", "Switch", whichChoice=-1)
    if sl is not None:
        n = len(sl.findall(".//Shape"))
        if not 5 <= n <= 7:
            errs.append(f"SW_SLICES has {n} slices, expected 5 to 7")
    need("SW_LABELS", "Switch", whichChoice=-1)
    need("SW_ACTIV", "Switch", whichChoice=-1)
    need("SND", "Sound")
    au = need("AUDIO", "AudioClip", loop="true")
    if au is not None and "m01-drift.ogg" not in (au.get("url") or ""):
        errs.append("AUDIO url is not audio/m01-drift.ogg")
    wi = root.find(".//WorldInfo")
    info = (wi.get("info") or "") if wi is not None else ""
    for word in ("SYNTHETIC", "ALIGNMENT", "sha256"):
        if word not in info:
            errs.append(f"WorldInfo info lacks {word}")
    if not (wi is not None and wi.get("title")):
        errs.append("WorldInfo has no title")
    # textures next to the scene
    txt = path.read_text(encoding="utf-8")
    urls = sorted(set(re.findall(r"url='\"([^\"]+)\"'", txt)))
    for u in urls:
        if u.startswith("audio/"):
            continue
        if not (path.parent / u).exists():
            errs.append(f"missing file {u}")
    for f in ("front", "back", "left", "right", "top", "bottom"):
        p = path.parent / f"tex/env64/studio-{f}.png"
        if p.exists() and png_size(p) != (64, 64):
            errs.append(f"{p.name} is {png_size(p)}, expected 64x64")
    if "OrderIndependentTransparency" in txt:
        errs.append("scene mentions OrderIndependentTransparency")
    for bad in ("<BlendMode", "<DepthMode", "MaterialExtension", "name='X_ITE'"):
        if bad in txt:
            errs.append(f"X_ITE-only construct {bad} (not in the 4.1 XSD)")
    return errs, len(defs)


if __name__ == "__main__":
    rc = 0
    for f in sys.argv[1:]:
        errs, n = check(f)
        print(f"{f}: {'PASS' if not errs else 'FAIL'} ({n} DEF names)")
        for e in errs:
            print("   -", e)
        rc |= bool(errs)
    sys.exit(rc)
