#!/usr/bin/env python3
"""Two-sided controls for tools/brain_scene_truth.py, run under normal Python and `python -O` (standard library only).

The positive controls are the real lite scenes (brain and torso), which must pass with every side input present (strict). Each negative
control mutates a copy of a real scene, or of the data beside it, so that exactly one contract is broken, and must be rejected with its
INTENDED stable code and with no other code except the ones the control names as unavoidable (law 19). A negative control that passes
raises SURVIVING_CONTROL. An exception that is not a rejection is a broken test, never a catch.

    python3 -I -B tests/test_brain_truth.py            # runs a normal child and a -O child (also when started with -O) and compares; prints JSON
    python3 -I -B tests/test_brain_truth.py --child    # one mode only (used by the parent)

Writes nothing into the study folder (the run folder's candidate hash would change); it prints one JSON document to stdout and exits
0 only if every control behaved. There is no `assert` in this file or in the reader; a syntax-tree scan below proves it.
"""
from __future__ import annotations

import ast
import copy
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
TOOL = STUDY / "tools" / "brain_scene_truth.py"
sys.path.insert(0, str(STUDY / "tools"))
sys.dont_write_bytecode = True
import brain_scene_truth as T  # noqa: E402

BRAIN, TORSO = "brain_hero_lite.x3d", "torso_ct_lite.x3d"


def fail(msg: str) -> None:
    raise RuntimeError(msg)


def once(text: str, old: str, new: str) -> str:
    """Replace exactly one occurrence, or the test itself is broken."""
    if text.count(old) != 1:
        fail(f"BROKEN_TEST: {old!r} occurs {text.count(old)} times")
    return text.replace(old, new)


def png(w: int, h: int) -> bytes:
    raw = b"".join(b"\x00" + bytes((i * 7) % 256 for i in range(w * 3)) for _ in range(h))
    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


class Sandbox:
    """A throwaway copy of the study layout (scenes/, data/, tools/) that one control may break."""

    def __init__(self, root: Path):
        self.root = root
        for d in ("scenes", "data", "tools"):
            (root / d).mkdir()
        shutil.copytree(STUDY / "scenes" / "tex", root / "scenes" / "tex")           # holds tex/env64 (the studio cube faces) as the scenes name them
        for n in (BRAIN, BRAIN + ".build.json", TORSO):
            shutil.copy(STUDY / "scenes" / n, root / "scenes" / n)
        for n in ("regions.json", "torso_regions.json"):
            shutil.copy(STUDY / "data" / n, root / "data" / n)
        for n in ("build_brain_scene.py", "build_torso_scene.py"):
            shutil.copy(STUDY / "tools" / n, root / "tools" / n)
        self.pristine = {k: ET.parse(root / "scenes" / n).getroot() for k, n in (("brain", BRAIN), ("torso", TORSO))}
        self.files = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}

    def reset(self) -> None:
        for p in list(self.root.rglob("*")):
            if p.is_file() and p not in self.files:
                p.unlink()
        for p, b in self.files.items():
            if not p.exists() or p.read_bytes() != b:
                p.write_bytes(b)

    def scene(self, kind: str) -> Path:
        return self.root / "scenes" / (BRAIN if kind == "brain" else TORSO)

    def tree(self, kind: str) -> ET.Element:
        return copy.deepcopy(self.pristine[kind])

    def write(self, kind: str, root: ET.Element, restamp: bool = True) -> Path:
        path = self.scene(kind)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        side = path.with_name(path.name + ".build.json")
        if kind == "brain" and restamp and side.exists():
            j = json.loads(side.read_text())
            j["sha256"] = T.sha256_bytes(path.read_bytes())
            side.write_text(json.dumps(j))
        return path

    def json_edit(self, rel: str, fn) -> None:
        p = self.root / rel
        j = json.loads(p.read_text())
        fn(j)
        p.write_text(json.dumps(j))


def defs(root: ET.Element) -> dict:
    return {e.get("DEF"): e for e in root.iter() if e.get("DEF")}


def sub(el: ET.Element, attr: str, old: str, new: str) -> None:
    el.set(attr, once(el.get(attr), old, new))


def world(root: ET.Element) -> ET.Element:
    return root.find("Scene").find("WorldInfo")


def coord(geo: ET.Element) -> ET.Element:
    return geo.find("Coordinate")


def shift(geo: ET.Element, axis: int, delta: float) -> None:
    v = coord(geo).get("point").split()
    for i in range(axis, len(v), 3):
        v[i] = repr(float(v[i]) + delta)
    coord(geo).set("point", " ".join(v))


def struct_geo(d: dict, name: str) -> ET.Element:
    return d[name].find(".//IndexedTriangleSet")


VOLUME = ("<IsoSurfaceVolumeData dimensions='1 1 1' surfaceValues='0.35'><OpacityMapVolumeStyle containerField='renderStyle'>"
          "<ImageTexture containerField='transferFunction' url='\"tex/slice_0.png\"'>{props}</ImageTexture></OpacityMapVolumeStyle></IsoSurfaceVolumeData>")
CLAMPED = "<TextureProperties containerField='textureProperties' boundaryModeS='CLAMP_TO_EDGE' boundaryModeT='CLAMP_TO_EDGE'/>"


# ------------------------------------------------------------------------------------------------ the controls
# Each mutate(sb, root) edits `root` (the parsed scene) and may edit files in the sandbox; it returns check_file keyword arguments.
def m_oit(sb, r):
    meta = ET.SubElement(r.find("head"), "meta", name="OrderIndependentTransparency", content="true")
    return {}


def m_oit_false(sb, r):
    ET.SubElement(r.find("head"), "meta", name="OrderIndependentTransparency", content="false")


def m_oit_page(sb, r):
    return {"page_texts": {"app.js": "x3dCanvas.browser.setBrowserOption('OrderIndependentTransparency', true);"}}


def m_oit_page_off(sb, r):
    return {"page_texts": {"app.js": "x3dCanvas.browser.setBrowserOption('OrderIndependentTransparency', false);"}}


def m_no_shaders_component(sb, r):
    head = r.find("head")
    comp = [c for c in head.findall("component") if c.get("name") == "Shaders"]
    if len(comp) != 1:
        fail("BROKEN_TEST: Shaders component")
    head.remove(comp[0])


def m_full_profile_no_component(sb, r):
    m_no_shaders_component(sb, r)
    r.set("profile", "Full")


def m_deep_vertex(sb, r):
    g = struct_geo(defs(r), "STRUCT_thalamus")
    v = coord(g).get("point").split()
    v[0] = "300"
    coord(g).set("point", " ".join(v))


def m_brainstem_up(sb, r):
    shift(struct_geo(defs(r), "STRUCT_brainstem"), 1, -60.0)


def m_brainstem_up_inside(sb, r):
    shift(struct_geo(defs(r), "STRUCT_brainstem"), 1, 60.0)


def m_thalamus_sideways_inside(sb, r):
    shift(struct_geo(defs(r), "STRUCT_thalamus"), 0, 20.0)


def m_cerebellum_forward(sb, r):
    shift(struct_geo(defs(r), "STRUCT_cerebellum"), 2, 70.0)


def m_index_range(sb, r):
    g = defs(r)["GEO_CORTEX_L"]
    i = g.get("index").split()
    i[5] = "99999"
    g.set("index", " ".join(i))


def m_index_negative(sb, r):
    g = defs(r)["GEO_CORTEX_L"]
    i = g.get("index").split()
    i[7] = "-1"
    g.set("index", " ".join(i))


def m_index_shape(sb, r):
    g = defs(r)["GEO_CORTEX_L"]
    g.set("index", " ".join(g.get("index").split()[:-1]))


def m_repeat_vertex(sb, r):
    g = defs(r)["GEO_CORTEX_L"]
    i = g.get("index").split()
    i[1] = i[0]
    g.set("index", " ".join(i))


def m_collapsed_flood(sb, r):
    g = defs(r)["GEO_CORTEX_R"]
    idx = [int(x) for x in g.get("index").split()]
    pts = coord(g).get("point").split()
    for t in range(300):
        a, b = idx[3 * t], idx[3 * t + 1]
        pts[3 * b:3 * b + 3] = pts[3 * a:3 * a + 3]
    coord(g).set("point", " ".join(pts))


def m_nan(sb, r):
    g = defs(r)["GEO_CORTEX_R"]
    v = coord(g).get("point").split()
    v[4] = "nan"
    coord(g).set("point", " ".join(v))


def m_normals_short(sb, r):
    n = defs(r)["GEO_CORTEX_L"].find("Normal")
    n.set("vector", " ".join(n.get("vector").split()[:-3]))


def m_tracts_notice(sb, r):
    t = defs(r)["TRACTS"]
    for md in list(t):
        if md.tag == "MetadataString":
            t.remove(md)


def m_activ_notice(sb, r):
    for p in list(defs(r)["SW_ACTIV"].iter()):
        for c in list(p):
            if c.tag == "MetadataString":
                p.remove(c)


def m_worldinfo_synthetic(sb, r):
    sub(world(r), "info", "SYNTHETIC NOTICE:", "NOTE:")


def m_def_missing(sb, r):
    defs(r)["SW_ACTIV"].set("DEF", "SW_ACTIVX")


def m_def_type(sb, r):
    defs(r)["SW_DEEP"].tag = "Group"
    defs(r)["SW_DEEP"].attrib.pop("whichChoice", None)


def m_def_duplicate(sb, r):
    defs(r)["G_PEDESTAL"].set("DEF", "BG")


def m_use_unresolved(sb, r):
    for e in r.iter("IndexedTriangleSet"):
        if e.get("USE") == "GEO_CORTEX_L":
            e.set("USE", "GEO_NOPE")
            return
    fail("BROKEN_TEST: no USE of GEO_CORTEX_L")


def m_switch_default(sb, r):
    defs(r)["SW_CORTEX"].set("whichChoice", "-1")


def m_wi_arcs(sb, r):
    sub(world(r), "info", "the 497 tract arcs", "the 498 tract arcs")


def m_sidecar_count(sb, r):
    sb.json_edit("scenes/" + BRAIN + ".build.json", lambda j: j.__setitem__("cortex_tris", j["cortex_tris"] + 1))


def m_tf(props: str):
    def f(sb, r):
        r.find("Scene").append(ET.fromstring(VOLUME.format(props=props)))
    return f


def m_opaque_flag(sb, r):
    for a in r.iter("Appearance"):
        if any(c.get("DEF") == "SH_CORTEX_L" for c in a):
            mat = a.find("Material")
            a.remove(mat)
            return
    fail("BROKEN_TEST: no Appearance holds SH_CORTEX_L")


def m_units_undeclared(sb, r):
    sub(world(r), "info", "1 scene unit = 1 mm", "scene units")


def stamp(r, label):
    """The 16-hex stamp the scene itself carries after `label` (read from the scene, so a rebuild cannot make the control stale)."""
    m = re.search(re.escape(label) + r" ([0-9a-f]{16})", world(r).get("info") or "")
    if not m:
        fail("BROKEN_TEST: no %r stamp in WorldInfo" % label)
    return label + " " + m.group(1)


def m_provenance(sb, r):
    sub(world(r), "info", stamp(r, "mesh npz sha256"), "mesh npz")


def m_builder_hash(sb, r):
    old = stamp(r, "build_brain_scene.py sha256")
    sub(world(r), "info", old, "build_brain_scene.py sha256 0000000000000000")


def m_sidecar_stale(sb, r):
    defs(r)["NAV"].set("speed", "2")


def m_align_undeclared(sb, r):
    sub(world(r), "info", "ALIGNMENT NOTICE", "NOTE")


def m_align_range(sb, r):
    sub(world(r), "info", "scale .963 .966 .952", "scale .8 .966 .952")


def m_audio_start(sb, r):
    defs(r)["AUDIO"].set("startTime", "0")


def m_env_face(sb, r):
    (sb.root / "scenes/tex/env64/studio-front.png").write_bytes(png(128, 128))


def m_texture_missing(sb, r):
    (sb.root / "scenes/tex/slice_0.png").unlink()


def m_layout(sb, r):
    ET.SubElement(r.find("Scene"), "ScreenGroup")


def m_particle(sb, r):
    ET.SubElement(defs(r)["G_ACTIV"], "ParticleSystem")


def m_label_node(sb, r):
    defs(r)["LBL_ctx_lh_cuneus"].set("DEF", "LBL_renamed")


def m_label_swapped(sb, r):
    for tx in defs(r)["LBL_ctx_lh_cuneus"].iter("Text"):
        tx.set("string", '"lingual"')


def m_region_outside(sb, r):
    def f(j):
        j[0]["centroid"] = [400.0, 0.0, 0.0]
    sb.json_edit("data/regions.json", f)


def m_not_xml(sb, r):
    return {"raw": b"this is not xml <<"}


def m_no_sidecar(sb, r):
    (sb.root / "scenes" / (BRAIN + ".build.json")).unlink()


def m_units_scale(sb, r):
    for c in r.iter("Coordinate"):
        if c.get("point") and not c.get("USE"):
            c.set("point", " ".join(repr(float(x) * 0.1) for x in c.get("point").split()))


def m_slices(sb, r):
    sw = defs(r)["SW_SLICES"]
    drop = sw.findall(".//Shape")[:2]
    for p in list(sw.iter()):
        for c in list(p):
            if c in drop:
                p.remove(c)


def m_headlight(sb, r):
    defs(r)["NAV"].set("headlight", "true")


def m_attribution(sb, r):
    sub(world(r), "info", "Fischl", "Someone")


def m_shader_field(sb, r):
    sh = defs(r)["SH_CORTEX_R"]
    f = [x for x in sh.findall("field") if x.get("name") == "rimPower"]
    sh.remove(f[0])


def wrap(r, name: str, tag: str = "Transform", **attrs) -> None:
    """Wrap the element DEF'd `name` in a new grouping node (in the same place in its parent)."""
    el = defs(r)[name]
    par = next(p for p in r.iter() if el in list(p))
    i = list(par).index(el)
    box = ET.Element(tag, **attrs)
    par.remove(el)
    box.append(el)
    par.insert(i, box)


def m_transform_deep(sb, r):
    wrap(r, "G_DEEP", translation="300 0 0")


def m_transform_deep_scale(sb, r):
    wrap(r, "G_DEEP", scale="0.01 0.01 0.01")


def m_transform_cortex(sb, r):
    wrap(r, "G_CORTEX_L", translation="0 0 -250")


def m_billboard_deep(sb, r):
    wrap(r, "G_DEEP", tag="Billboard", axisOfRotation="0 1 0")


def m_identity_transform(sb, r):
    wrap(r, "G_DEEP", translation="0 0 0", scale="1 1 1", rotation="0 0 1 0")


def m_deep_hidden(sb, r):
    defs(r)["SW_DEEP"].set("whichChoice", "-1")


def m_deep_nochoice(sb, r):
    defs(r)["SW_DEEP"].attrib.pop("whichChoice")


def m_hemi_hidden(sb, r):
    defs(r)["SW_HEMI_R"].set("whichChoice", "-1")


def m_hemi_second_child(sb, r):
    d = defs(r)
    d["G_CORTEX"].remove(d["SW_HEMI_R"])
    d["SW_CORTEX"].append(d["SW_HEMI_R"])


def m_png_empty(sb, r):
    (sb.root / "scenes/tex/slice_0.png").write_bytes(b"")


def m_png_truncated(sb, r):
    p = sb.root / "scenes/tex/slice_1.png"
    p.write_bytes(p.read_bytes()[:-40])


def m_hemispheres_mirrored(sb, r):
    for n in ("GEO_CORTEX_L", "GEO_CORTEX_R"):
        v = coord(defs(r)[n]).get("point").split()
        for i in range(0, len(v), 3):
            v[i] = repr(-float(v[i]))
        coord(defs(r)[n]).set("point", " ".join(v))


def m_oit_script(sb, r):
    el = ET.SubElement(r.find("Scene"), "Script", DEF="S_OIT")
    el.text = "ecmascript: function initialize() { Browser.setBrowserOption('OrderIndependentTransparency', true); }"


def m_glass_alpha_zero(sb, r):
    for f in defs(r)["SH_CORTEX_L"].findall("field"):
        if f.get("name") in ("baseAlpha", "rimAlpha", "sulcAlpha"):
            f.set("value", "0")


def m_extra_line_shape(sb, r):
    r.find("Scene").append(ET.fromstring("<Shape><Appearance><Material emissiveColor='1 0 0'/></Appearance><IndexedLineSet coordIndex='0 1 -1'><Coordinate point='0 0 0 50 50 50'/></IndexedLineSet></Shape>"))


def m_viewpoint_far(sb, r):
    defs(r)["VP_HOME"].set("position", "0 0 1000000")


# torso
def t_skull_transform(sb, r):
    wrap(r, "SW_SKULL", translation="0 400 0")


def t_second_child(sb, r):
    d = defs(r)
    g = d["G_ORGANS"]
    g2 = ET.Element("Group")
    for k in list(g)[len(g) // 2:]:
        g.remove(k)
        g2.append(k)
    d["SW_ORGANS"].append(g2)


def t_label_missing(sb, r):
    sb.json_edit("data/torso_regions.json", lambda j: j["regions"].pop(5))


def t_label_empty(sb, r):
    sb.json_edit("data/torso_regions.json", lambda j: j["regions"][3].__setitem__("label", " "))


def t_orphan(sb, r):
    sb.json_edit("data/torso_regions.json", lambda j: j["regions"].append(dict(j["regions"][0], id="STRUCT_ghost")))


def t_attribution(sb, r):
    sub(world(r), "info", "Wasserthal J. et al.", "Someone et al.")


def t_oit(sb, r):
    ET.SubElement(r.find("head"), "meta", name="OrderIndependentTransparency", content="true")


def t_index(sb, r):
    g = defs(r)["GEO_heart"]
    i = g.get("index").split()
    i[2] = "999999"
    g.set("index", " ".join(i))


def t_counts(sb, r):
    sb.json_edit("data/torso_regions.json", lambda j: j["regions"][2].__setitem__("lite_triangles", j["regions"][2]["lite_triangles"] + 1))


def t_ghost(sb, r):
    shift(defs(r)["GEO_cortex_left"], 1, 200.0)


def t_notice(sb, r):
    sub(world(r), "info", "not this subject", "this subject")


def t_no_shaders(sb, r):
    m_no_shaders_component(sb, r)


def t_builder(sb, r):
    sb.json_edit("data/torso_regions.json", lambda j: j.__setitem__("builder_sha256", "0" * 64))


def t_switch(sb, r):
    defs(r)["SW_BRAIN_CT"].set("whichChoice", "0")


def t_units(sb, r):
    sub(world(r), "info", "1 unit = 1 mm", "units unknown")


# (name, kind, mutate, expected code or None for a positive twin, codes that may also appear, extra options)
CONTROLS = [
    ("oit enabled together with the glass ComposedShader", "brain", m_oit, "BRAIN_OIT_WITH_SHADER", (), {}),
    ("oit switched on by the page JavaScript", "brain", m_oit_page, "BRAIN_OIT_WITH_SHADER", (), {}),
    ("shader used without the Shaders component", "brain", m_no_shaders_component, "BRAIN_SHADER_COMPONENT", (), {}),
    ("subcortical vertex outside the cortex bounding box", "brain", m_deep_vertex, "BRAIN_DEEP_OUTSIDE", (), {}),
    ("brain stem shifted 60 mm down", "brain", m_brainstem_up, "BRAIN_DEEP_OUTSIDE", ("BRAIN_REGION_OUTSIDE",), {}),
    ("brain stem shifted 60 mm up (inside the box; caught by its region centroid)", "brain", m_brainstem_up_inside, "BRAIN_REGION_OUTSIDE", (), {}),
    ("cerebellum shifted 70 mm backwards", "brain", m_cerebellum_forward, "BRAIN_DEEP_OUTSIDE", ("BRAIN_REGION_OUTSIDE",), {}),
    ("triangle index past the last vertex", "brain", m_index_range, "BRAIN_INDEX_RANGE", (), {}),
    ("negative triangle index", "brain", m_index_negative, "BRAIN_INDEX_RANGE", (), {}),
    ("index list is not whole triangles", "brain", m_index_shape, "BRAIN_INDEX_SHAPE", (), {}),
    ("triangle repeats a vertex", "brain", m_repeat_vertex, "BRAIN_DEGENERATE", (), {}),
    ("collapsed triangles above the cap", "brain", m_collapsed_flood, "BRAIN_DEGENERATE", (), {}),
    ("NaN coordinate", "brain", m_nan, "BRAIN_NONFINITE", (), {}),
    ("normals shorter than the coordinates", "brain", m_normals_short, "BRAIN_ATTRIBUTE_COUNT", (), {}),
    ("tracts without the SYNTHETIC metadata", "brain", m_tracts_notice, "BRAIN_SYNTHETIC_TRACTS", (), {}),
    ("activation without the ILLUSTRATIVE metadata", "brain", m_activ_notice, "BRAIN_SYNTHETIC_ACTIV", (), {}),
    ("WorldInfo without the SYNTHETIC notice", "brain", m_worldinfo_synthetic, "BRAIN_SYNTHETIC_WORLDINFO", (), {}),
    ("a contract DEF is missing", "brain", m_def_missing, "BRAIN_DEF_MISSING", (), {}),
    ("a contract DEF is the wrong node type", "brain", m_def_type, "BRAIN_DEF_TYPE", (), {}),
    ("a DEF used twice", "brain", m_def_duplicate, "BRAIN_DEF_DUPLICATE", (), {}),
    ("USE of a DEF that does not exist", "brain", m_use_unresolved, "BRAIN_USE_UNRESOLVED", (), {}),
    ("cortex switch default changed", "brain", m_switch_default, "BRAIN_SWITCH_DEFAULT", (), {}),
    ("WorldInfo tract arc count differs from the geometry", "brain", m_wi_arcs, "BRAIN_COUNT_MISMATCH", (), {}),
    ("sidecar triangle count differs from the geometry", "brain", m_sidecar_count, "BRAIN_COUNT_MISMATCH", (), {}),
    ("no declaration of the counts (sidecar gone, not strict)", "brain", m_no_sidecar, "BRAIN_COUNT_UNDECLARED", (), {"strict": False}),
    ("strict mode and the sidecar is gone", "brain", m_no_sidecar, "BRAIN_INPUT_MISSING", ("BRAIN_COUNT_UNDECLARED",), {}),
    ("sidecar written for another scene hash", "brain", m_sidecar_stale, "BRAIN_SIDECAR_STALE", (), {"restamp": False}),
    ("unclamped transfer-function texture", "brain", m_tf(""), "BRAIN_TF_UNCLAMPED", (), {}),
    ("Appearance of a ComposedShader without the transparency flag", "brain", m_opaque_flag, "BRAIN_SHADER_OPAQUE_FLAG", (), {}),
    ("units not declared", "brain", m_units_undeclared, "BRAIN_UNITS_UNDECLARED", (), {}),
    ("geometry in centimetres (scaled 0.1)", "brain", m_units_scale, "BRAIN_UNITS_SCALE", ("BRAIN_REGION_OUTSIDE",), {}),
    ("source-mesh provenance hash not recorded", "brain", m_provenance, "BRAIN_PROVENANCE_HASH", (), {}),
    ("builder hash is not the builder file", "brain", m_builder_hash, "BRAIN_BUILDER_MISMATCH", (), {}),
    ("alignment not disclosed", "brain", m_align_undeclared, "BRAIN_ALIGN_UNDECLARED", (), {}),
    ("declared alignment scale outside the fit range", "brain", m_align_range, "BRAIN_ALIGN_FIT_RANGE", (), {}),
    ("looping audio that starts at load", "brain", m_audio_start, "BRAIN_AUDIO_AUTOSTART", (), {}),
    ("environment face is 128 px", "brain", m_env_face, "BRAIN_ENV_FACE_SIZE", (), {}),
    ("texture file missing", "brain", m_texture_missing, "BRAIN_TEXTURE_MISSING", (), {}),
    ("Layout node under profile Immersive", "brain", m_layout, "BRAIN_LAYOUT_PROFILE", (), {}),
    ("particle system inside a group", "brain", m_particle, "BRAIN_PARTICLE_PARENT", (), {}),
    ("a region has no label node", "brain", m_label_node, "BRAIN_LABEL_MISSING", (), {}),
    ("a label shows another region's name", "brain", m_label_swapped, "BRAIN_LABEL_MISSING", (), {}),
    ("a region centroid outside the cortex", "brain", m_region_outside, "BRAIN_REGION_OUTSIDE", (), {}),
    ("not XML", "brain", m_not_xml, "BRAIN_NOT_X3D", (), {}),
    ("slices reduced below the contract", "brain", m_slices, "BRAIN_DEF_ATTR", (), {}),
    ("headlight on", "brain", m_headlight, "BRAIN_DEF_ATTR", (), {}),
    ("glass shader field missing", "brain", m_shader_field, "BRAIN_DEF_ATTR", (), {}),
    ("attribution removed from WorldInfo", "brain", m_attribution, "BRAIN_ATTRIBUTION", (), {}),
    ("torso: a structure has no label", "torso", t_label_missing, "BRAIN_LABEL_MISSING", (), {}),
    ("torso: a label is blank", "torso", t_label_empty, "BRAIN_LABEL_MISSING", (), {}),
    ("torso: a label names a structure that does not exist", "torso", t_orphan, "BRAIN_LABEL_ORPHAN", (), {}),
    ("torso: attribution removed", "torso", t_attribution, "BRAIN_ATTRIBUTION", (), {}),
    ("torso: oit enabled with the shaders", "torso", t_oit, "BRAIN_OIT_WITH_SHADER", (), {}),
    ("torso: index out of range", "torso", t_index, "BRAIN_INDEX_RANGE", (), {}),
    ("torso: triangle count differs from the label data", "torso", t_counts, "BRAIN_COUNT_MISMATCH", (), {}),
    ("torso: brain ghost moved out of the skull", "torso", t_ghost, "BRAIN_DEEP_OUTSIDE", ("BRAIN_COUNT_MISMATCH",), {}),
    ("torso: ILLUSTRATIVE ghost notice removed", "torso", t_notice, "BRAIN_SYNTHETIC_WORLDINFO", (), {}),
    ("torso: Shaders component removed", "torso", t_no_shaders, "BRAIN_SHADER_COMPONENT", (), {}),
    ("torso: builder hash differs between scene and label data", "torso", t_builder, "BRAIN_BUILDER_MISMATCH", (), {}),
    ("torso: switch default changed", "torso", t_switch, "BRAIN_SWITCH_DEFAULT", (), {}),
    ("torso: units not declared", "torso", t_units, "BRAIN_UNITS_UNDECLARED", (), {}),
    # added by the correctness review (6 Nov 2026): scenes that were valid and passed but were wrong or not visible
    ("a Transform above the deep structures moves them 300 mm", "brain", m_transform_deep, "BRAIN_DEF_ATTR", (), {}),
    ("a Transform above the deep structures shrinks them to 1 percent", "brain", m_transform_deep_scale, "BRAIN_DEF_ATTR", (), {}),
    ("a Transform above the left cortex moves it 250 mm", "brain", m_transform_cortex, "BRAIN_DEF_ATTR", (), {}),
    ("a Billboard above the deep structures", "brain", m_billboard_deep, "BRAIN_DEF_ATTR", (), {}),
    ("deep structures hidden at load (whichChoice -1)", "brain", m_deep_hidden, "BRAIN_SWITCH_DEFAULT", (), {}),
    ("deep structures hidden at load (whichChoice missing, X3D default -1)", "brain", m_deep_nochoice, "BRAIN_SWITCH_DEFAULT", (), {}),
    ("right cortex hemisphere hidden at load", "brain", m_hemi_hidden, "BRAIN_SWITCH_DEFAULT", (), {}),
    ("right cortex hemisphere is the second child of a Switch that draws child 0", "brain", m_hemi_second_child, "BRAIN_SWITCH_DEFAULT", (), {}),
    ("a slice texture is an empty file", "brain", m_png_empty, "BRAIN_TEXTURE_MISSING", (), {}),
    ("a slice texture is a truncated PNG", "brain", m_png_truncated, "BRAIN_TEXTURE_MISSING", (), {}),
    ("hemispheres mirrored: the left cortex is on the right", "brain", m_hemispheres_mirrored, "BRAIN_REGION_OUTSIDE", (), {}),
    ("order-independent transparency switched on by a Script node", "brain", m_oit_script, "BRAIN_OIT_WITH_SHADER", (), {}),
    ("torso: a Transform above the skull's Switch", "torso", t_skull_transform, "BRAIN_DEF_ATTR", (), {}),
    ("torso: half of the organs in a second Switch child", "torso", t_second_child, "BRAIN_SWITCH_DEFAULT", (), {}),
]

# Positive twins: one-edit variants that must still pass, so a negative is never rejected by a rule that is simply too eager.
TWINS = [
    ("oit declared off", "brain", m_oit_false, {}),
    ("oit switched off by the page JavaScript", "brain", m_oit_page_off, {}),
    ("profile Full without the Shaders component", "brain", m_full_profile_no_component, {}),
    ("clamped transfer-function texture", "brain", m_tf(CLAMPED), {}),
    ("identity Transform above the deep structures", "brain", m_identity_transform, {}),
]


# Documented blind spots of a bounding-box containment check (law 25). These are SUPPOSED to pass: they pin down what the reader cannot see,
# so that tightening it later is a deliberate change. They are listed in the output as blind spots, never counted as controls.
BLIND = [
    ("thalamus moved 20 mm sideways but still inside the cortex box", "brain", m_thalamus_sideways_inside, {}),
    ("glass opacity fields of the left hemisphere set to 0 (a valid shader that draws nothing)", "brain", m_glass_alpha_zero, {}),
    ("an unlabelled extra line shape outside the TRACTS group", "brain", m_extra_line_shape, {}),
    ("home viewpoint a thousand kilometres from the brain", "brain", m_viewpoint_far, {}),
]


def run_one(sb: Sandbox, kind: str, mutate, opts: dict) -> dict:
    sb.reset()
    root = sb.tree(kind)
    extra = mutate(sb, root) or {}
    raw = extra.pop("raw", None)
    path = sb.scene(kind)
    if raw is not None:
        path.write_bytes(raw)
    else:
        sb.write(kind, root, restamp=opts.get("restamp", True))
    return T.check_file(path, strict=opts.get("strict", True), **extra)


def positive(sb: Sandbox) -> list[dict]:
    rows = []
    for kind in ("brain", "torso"):
        sb.reset()
        rep = T.check_file(sb.scene(kind), strict=True)
        if rep["status"] != "pass" or rep["violations"] or rep["skipped"]:
            fail(f"POSITIVE_FAILED {kind}: {rep['violations'][:3]} {rep['skipped']}")
        m = rep["measurements"]
        if kind == "brain":
            side = json.loads((sb.root / "scenes" / (BRAIN + ".build.json")).read_text())
            for k in ("cortex_verts", "cortex_tris", "deep_tris", "tract_fibres", "tract_points"):
                if m["counts"][k] != side[k]:
                    fail(f"POSITIVE_FAILED counts {k}: {m['counts'][k]} != {side[k]}")
            if not (m["deep_containment"]["structures"]["brainstem"]["ok"] and m["geometry"]["collapsed_fraction"] <= T.ZERO_AREA_FRAC_MAX):
                fail("POSITIVE_FAILED brain measurements")
        else:
            if m["labels"]["shapes"] != m["labels"]["entries"] or m["labels"]["lite_triangles"] != m["geometry"]["triangles"]:
                fail("POSITIVE_FAILED torso labels")
        rows.append({"case": f"{kind} lite scene (real file, strict)", "result": "pass", "checks": rep["checks_run"],
                     "triangles": m["geometry"]["triangles"], "collapsed": m["geometry"]["collapsed_triangles"]})
    for name, kind, mutate, opts in TWINS:
        rep = run_one(sb, kind, mutate, opts)
        if rep["status"] != "pass":
            fail(f"TWIN_REJECTED {name}: {rep['violations'][:2]}")
        rows.append({"case": f"twin: {name}", "result": "pass"})
    return rows


def blind_spots(sb: Sandbox) -> list[dict]:
    rows = []
    for name, kind, mutate, opts in BLIND:
        rep = run_one(sb, kind, mutate, opts)
        if rep["status"] != "pass":
            fail(f"BLIND_SPOT_CLOSED: {name} is now rejected ({rep['violations'][0]['code']}); update the profile limitations")
        rows.append({"case": name, "result": "not detected (known blind spot)"})
    return rows


def negatives(sb: Sandbox) -> list[dict]:
    rows = []
    for name, kind, mutate, expect, also, opts in CONTROLS:
        rep = run_one(sb, kind, mutate, opts)
        if rep["status"] == "pass":
            fail(f"SURVIVING_CONTROL: {name}")
        codes = [v["code"] for v in rep["violations"]]
        if codes[0] != expect:
            fail(f"WRONG_DIAGNOSTIC: {name}: first {codes[0]} ({rep['violations'][0]['detail']}), expected {expect}; all {sorted(set(codes))}")
        extra = set(codes) - {expect} - set(also)
        if extra:
            fail(f"EXTRA_DIAGNOSTIC: {name}: {sorted(extra)} besides {expect}")
        rows.append({"case": name, "expected": expect, "caught": codes[0], "codes": sorted(set(codes)), "detail": rep["violations"][0]["detail"][:160]})
    covered = {r["expected"] for r in rows}
    missing = sorted(set(T.CODES) - covered)
    if missing:
        fail(f"UNCOVERED_CODES: {missing}")
    return rows


def cli(sb: Sandbox, optimized: bool) -> list[dict]:
    flags = ["-I", "-B"] + (["-O"] if optimized else [])
    def go(args: list[str]) -> tuple[int, dict]:
        p = subprocess.run([sys.executable, *flags, str(TOOL), *args], capture_output=True, text=True, timeout=300, cwd=str(sb.root))
        try:
            return p.returncode, json.loads(p.stdout) if p.stdout.strip() else {}
        except ValueError:
            fail(f"CLI_NOT_JSON: {p.stdout[:200]} {p.stderr[-300:]}")
    rows = []
    sb.reset()
    rc, out = go(["--strict", "--glob", "scenes/*.x3d"])
    if rc != 0 or out.get("status") != "pass" or out.get("scenes") != 2:
        fail(f"CLI_POSITIVE: exit {rc} {out.get('detail')}")
    rows.append({"case": "cli: real scenes, strict", "exit": rc, "scenes": out["scenes"]})
    root = sb.tree("brain")
    m_oit(sb, root)
    sb.write("brain", root)
    rc, out = go(["--strict", "--glob", "scenes/brain_hero_lite.x3d"])
    if rc != 1 or out.get("rejected") != "BRAIN_OIT_WITH_SHADER":
        fail(f"CLI_NEGATIVE: exit {rc} {out.get('rejected')}")
    rows.append({"case": "cli: oit with shader", "exit": rc, "rejected": out["rejected"]})
    sb.reset()
    rc, out = go(["scenes/does_not_exist.x3d"])
    if rc != 2 or out.get("error") != "INSTRUMENT_ERROR":
        fail(f"CLI_MISSING: exit {rc} {out}")
    rows.append({"case": "cli: missing file is an instrument error", "exit": rc})
    (sb.root / "scenes" / "unknown_kind.x3d").write_bytes(b"<X3D/>")
    rc, out = go(["scenes/unknown_kind.x3d"])
    if rc != 2:
        fail(f"CLI_UNKNOWN_KIND: exit {rc} {out}")
    rows.append({"case": "cli: unknown scene kind is an instrument error", "exit": rc})
    rc, out = go(["--glob", "scenes/nothing_*.x3d"])
    if rc != 2:
        fail(f"CLI_GLOB: exit {rc}")
    rows.append({"case": "cli: a glob that matches nothing is an instrument error", "exit": rc})
    rc, out = go(["--list-codes"])
    if rc != 0 or set(out.get("codes", {})) != set(T.CODES):
        fail("CLI_CODES")
    rows.append({"case": "cli: --list-codes", "exit": rc, "codes": len(out["codes"])})
    sb.reset()
    return rows


def no_asserts() -> list[dict]:
    rows = []
    for p in (TOOL, Path(__file__).resolve()):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        n = sum(isinstance(node, ast.Assert) for node in ast.walk(tree))
        if n:
            fail(f"ASSERT_IN_GATE: {p.name} has {n} assert statements, which `python -O` removes")
        rows.append({"case": f"no assert statement in {p.name}", "asserts": 0})
    return rows


def child() -> dict:
    with tempfile.TemporaryDirectory(prefix="brain-truth-") as d:
        sb = Sandbox(Path(d))
        res = {"optimized": not __debug__, "python": sys.version.split()[0]}
        res["positive"] = positive(sb)
        res["negative"] = negatives(sb)
        res["blind_spots"] = blind_spots(sb)
        res["cli"] = cli(sb, optimized=not __debug__)
        res["syntax"] = no_asserts()
    return res


def spawn(optimized: bool) -> dict:
    """One child run in a fresh interpreter, with or without -O, whatever flags this parent was started with."""
    flags = ["-I", "-B"] + (["-O"] if optimized else [])
    p = subprocess.run([sys.executable, *flags, str(Path(__file__).resolve()), "--child"], capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        fail(f"{'OPTIMIZED' if optimized else 'NORMAL'}_RUN_FAILED: {(p.stdout[-400:] + p.stderr[-800:])[-900:]}")
    try:
        res = json.loads(p.stdout)
    except ValueError:
        fail(f"CHILD_NOT_JSON ({'-O' if optimized else 'normal'}): {p.stdout[:200]} {p.stderr[-300:]}")
    if res["optimized"] != optimized:
        fail(f"OPTIMIZED_FLAG: the {'-O' if optimized else 'normal'} child ran with optimized={res['optimized']}")
    return res


def main() -> int:
    if "--child" in sys.argv:
        print(json.dumps(child(), sort_keys=True))
        return 0
    normal = spawn(False)       # the parent may itself be running under -O (python -O tests/test_brain_truth.py): it never trusts its own mode
    opt = spawn(True)
    same = [(r["case"], r["caught"]) for r in normal["negative"]] == [(r["case"], r["caught"]) for r in opt["negative"]] and \
        [(r["case"], r["result"]) for r in normal["positive"]] == [(r["case"], r["result"]) for r in opt["positive"]]
    if not same:
        fail("MODES_DISAGREE: normal and -O runs gave different verdicts")
    out = {"schema": "brain.truth-controls/1", "positive": len(normal["positive"]), "negative": len(normal["negative"]),
           "codes_covered": len({r["expected"] for r in normal["negative"]}), "codes_total": len(T.CODES), "cli": len(normal["cli"]),
           "blind_spots": len(normal["blind_spots"]),
           "optimized_run_agrees": True, "python": normal["python"], "result": normal}
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as e:
        print(json.dumps({"schema": "brain.truth-controls/1", "failed": str(e)[:1200]}))
        sys.exit(1)
