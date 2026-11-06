#!/usr/bin/env python3
"""Brain and torso scene truth reader (Loom `data-true` witness for the brain demo). Python standard library only.

    python3 -I -B tools/brain_scene_truth.py [--strict] [--glob 'scenes/*.x3d'] [SCENE.x3d ...]
        [--regions FILE] [--sidecar FILE] [--builder FILE] [--page FILE ...] [--list-codes]

Reads brain_hero*.x3d and torso_ct*.x3d (kind is taken from the file name or --kind) and decides, from the geometry and the
text of the file alone, whether the scene tells the truth about itself. It never renders anything: valid is not visible
(law 2), so this reader is one witness among several and says nothing about how the scene looks.

Exit codes (same convention as the Loom kit): 0 passed, 1 contract violation (stable BRAIN_* code on stdout as JSON,
first violation plus the full list), 2 instrument or input error (unreadable file, crash). Every predicate raises or records
a violation explicitly; there is no `assert` anywhere in this file, so `python -O` cannot turn a red gate green (law 18).
tests/test_brain_truth.py proves that by running the controls under both modes and by scanning this file's syntax tree.

What it decides (code in brackets):
  structure   every contract DEF exists once, with the right node type, switch default, shader fields, containment [BRAIN_DEF_*,
              BRAIN_SWITCH_DEFAULT, BRAIN_AUDIO_AUTOSTART, BRAIN_USE_UNRESOLVED]; textures exist and env faces are 64 px
              [BRAIN_TEXTURE_MISSING, BRAIN_ENV_FACE_SIZE]
  geometry    indices inside the coordinate array, multiples of three, no repeated vertex in a triangle, collapsed (zero-area)
              triangles below a declared cap, finite numbers, normals and colours as long as the coordinates
              [BRAIN_INDEX_RANGE, BRAIN_INDEX_SHAPE, BRAIN_DEGENERATE, BRAIN_NONFINITE, BRAIN_ATTRIBUTE_COUNT]
  counts      vertex and triangle counts equal what the build sidecar (sha256-bound to the scene) and WorldInfo declare, and the
              region/label data file declares [BRAIN_COUNT_MISMATCH, BRAIN_COUNT_UNDECLARED, BRAIN_SIDECAR_STALE]
  alignment   deep structures lie inside the cortex bounding box grown by DEEP_TOL_FRAC per axis (brain stem and cerebellum may
              also descend below its floor by INFRA_DESCENT_FRAC); the declared bbox-fit scale is inside ALIGN_FIT_MAX
              [BRAIN_DEEP_OUTSIDE, BRAIN_ALIGN_UNDECLARED, BRAIN_ALIGN_FIT_RANGE, BRAIN_UNITS_SCALE]
  honesty     SYNTHETIC / ILLUSTRATIVE notices on tracts and activation and in WorldInfo, units, provenance hashes, attribution
              [BRAIN_SYNTHETIC_*, BRAIN_UNITS_UNDECLARED, BRAIN_PROVENANCE_HASH, BRAIN_BUILDER_MISMATCH, BRAIN_ATTRIBUTION]
  visibility  valid is not visible: the geometry the checks measure is drawn at load, i.e. every Switch above it has whichChoice equal to
              the index of the child that holds it; no Transform (or Billboard) above a measured mesh unless it is the identity
              [BRAIN_SWITCH_DEFAULT, BRAIN_DEF_ATTR]; every PNG the scene names is a complete PNG [BRAIN_TEXTURE_MISSING]
  runtime     traps already paid for on X_ITE 16.6.0: no order-independent transparency with a custom shader, Shaders component
              declared, transparency flag Material beside every ComposedShader, clamped transfer-function textures, Layout nodes
              need profile Full, particle systems live in the Scene [BRAIN_OIT_WITH_SHADER, BRAIN_SHADER_COMPONENT,
              BRAIN_SHADER_OPAQUE_FLAG, BRAIN_TF_UNCLAMPED, BRAIN_LAYOUT_PROFILE, BRAIN_PARTICLE_PARENT]
  labels      brain: every region in regions.json has its label node, showing that region's name, and sits inside the geometry it names; torso: every STRUCT_
              shape has a label, every label has a shape, and counts and bounding boxes match [BRAIN_LABEL_*, BRAIN_REGION_OUTSIDE]

What it cannot decide (law 25, said here and in the output):
  - Parameters that make a drawn shape invisible are not read (a glass alpha of 0, lights off, a viewpoint a kilometre away); the fork's
    Grammar and Meaning witnesses cover colour and field ranges and NaN, not these. The controls pin two of them as blind spots.
  - The notice checks look for the words, not for their truth; hash binding proves which builder file the scene names, not that the
    builder made these bytes.
  - The deep-structure containment shares the builder's alignment assumption. fsaverage and MNI152 are joined by a per-axis scale and
    shift of their cortex bounding boxes (the fit is 3 to 5 percent per axis), so this check catches a gross misplacement (a structure
    tens of millimetres out) and cannot show that any position is anatomically right. A pass is a look-level consistency result, not a
    registration and not a clinical statement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SCHEMA = "brain.scene-truth/1"

# ------------------------------------------------------------------------------------------------ declared limits
# Every number this reader decides on is here and is echoed in the output under "limits".
DEEP_TOL_FRAC = 0.05          # deep structure may overshoot the cortex bbox by this fraction of its extent, per axis (the declared 3-5 % fit)
INFRA_DESCENT_FRAC = 0.20     # brain stem / cerebellum may also descend below the cortex floor (-y) by this fraction of the y extent
ALIGN_FIT_MAX = 0.05          # the declared bbox-fit scale may differ from 1 by at most this, per axis
AREA_EPS = 1e-6               # mm^2: a triangle at or under this is collapsed (the builder prints coordinates to 0.1 mm)
ZERO_AREA_FRAC_MAX = 0.001    # collapsed triangles allowed as a fraction of all triangles in a scene (reported, capped)
AUDIO_START_MIN = 2.0e9       # AudioClip.startTime must be in the future so a looping clip does not start at load (about 2033)
ENV_FACE_PX = 64              # studio cube-map faces; 128 px cost 8.9 s and 256 px 34 s to load on X_ITE 16.6.0 (RENDER-FINDINGS)
BRAIN_EXTENT_MM = (80.0, 250.0)    # plausible human cerebrum extent per axis in millimetres
TORSO_WIDTH_MM = (250.0, 600.0)    # plausible adult torso width (x) in millimetres
SLICES = (5, 7)
REGION_TOL_FRAC = 0.05        # region centroids may sit this far (fraction of the box extent) outside the box they belong to
BBOX_MM_TOL = 0.3             # torso_regions.json bounding boxes against the scene geometry

STRUCTS = ["thalamus", "caudate", "putamen", "pallidum", "hippocampus", "amygdala", "accumbens", "ventricles", "brainstem", "cerebellum"]
INFRATENTORIAL = {"brainstem", "cerebellum"}
VIEWPOINTS = ["VP_HOME", "VP_LEFT", "VP_RIGHT", "VP_TOP", "VP_FRONT", "VP_MEDIAL", "VP_INSIDE"]
SHADER_FIELDS = ["rimColor", "bodyColor", "rimPower", "baseAlpha", "rimAlpha"]
SHADER_NODES = {"ComposedShader", "PackagedShader", "ProgramShader"}
LAYOUT_NODES = {"ScreenGroup", "Layout", "LayoutGroup", "LayoutLayer", "ScreenFontStyle"}
VOLUME_STYLES = {"OpacityMapVolumeStyle"}
# Grouping nodes that move what is below them. The containment checks read raw coordinates, so a measured mesh below one of these
# (unless it is an identity Transform) would be measured in the wrong place: the reader refuses instead of guessing.
TRANSFORM_TAGS = {"Transform", "Billboard", "HAnimHumanoid", "HAnimJoint", "HAnimSegment", "HAnimSite", "GeoTransform", "ScreenGroup", "LayoutGroup"}
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB`\x82"

BRAIN_DEFS = {"NAV": "NavigationInfo", "BG": "Background", "KEY": "DirectionalLight", "FILL": "DirectionalLight", "RIM": "DirectionalLight",
              "ENV": "EnvironmentLight", "SW_CORTEX": "Switch", "G_CORTEX_L": "Group", "G_CORTEX_R": "Group",
              "SH_CORTEX_L": "ComposedShader", "SH_CORTEX_R": "ComposedShader", "TS_CORTEX_L": "TouchSensor", "TS_CORTEX_R": "TouchSensor",
              "SW_WET": "Switch", "G_WET_L": "Group", "G_WET_R": "Group", "SW_DEEP": "Switch", "SW_TRACTS": "Switch", "TRACTS": "Group",
              "TRACT_CORE": "Shape", "TRACT_HALO1": "Shape", "TRACT_HALO2": "Shape", "SW_SLICES": "Switch", "SW_LABELS": "Switch",
              "SW_ACTIV": "Switch", "SND": "Sound", "AUDIO": "AudioClip", "GEO_CORTEX_L": "IndexedTriangleSet", "GEO_CORTEX_R": "IndexedTriangleSet",
              "GEO_TRACTS": "IndexedLineSet"}
BRAIN_DEFS.update({vp: "Viewpoint" for vp in VIEWPOINTS})
BRAIN_DEFS.update({f"STRUCT_{s}": "Shape" for s in STRUCTS})
BRAIN_DEFS.update({f"MAT_{s}": "PhysicalMaterial" for s in STRUCTS})
BRAIN_SWITCH_DEFAULTS = {"SW_CORTEX": "0", "SW_WET": "-1", "SW_SLICES": "-1", "SW_LABELS": "-1", "SW_ACTIV": "-1"}
BRAIN_INSIDE = [("G_CORTEX_L", "SW_CORTEX"), ("G_CORTEX_R", "SW_CORTEX"), ("G_WET_L", "SW_WET"), ("G_WET_R", "SW_WET"),
                ("SH_CORTEX_L", "G_CORTEX_L"), ("SH_CORTEX_R", "G_CORTEX_R"), ("TS_CORTEX_L", "G_CORTEX_L"), ("TS_CORTEX_R", "G_CORTEX_R"),
                ("TRACTS", "SW_TRACTS"), ("TRACT_CORE", "TRACTS"), ("TRACT_HALO1", "TRACTS"), ("TRACT_HALO2", "TRACTS"), ("SND", None)]
BRAIN_INSIDE += [(f"STRUCT_{s}", "SW_DEEP") for s in STRUCTS]

TORSO_SWITCHES = {"SW_SKIN": "0", "SW_RIBCAGE": "0", "SW_SPINE": "0", "SW_GIRDLES": "0", "SW_SKULL": "0", "SW_BRAIN": "0", "SW_BRAIN_CT": "-1",
                  "SW_LUNGS": "0", "SW_LUNGVESSELS": "0", "SW_AIRWAY": "0", "SW_HEART": "0", "SW_VESSELS": "0", "SW_ORGANS": "0", "SW_VISCERA": "-1"}
TORSO_VIEWPOINTS = ["VP_HOME", "VP_FRONT", "VP_BACK", "VP_LEFT", "VP_RIGHT", "VP_CHEST", "VP_HEART", "VP_HEAD", "VP_TOP"]
TORSO_DEFS = {"WORLD": "WorldInfo", "NAV": "NavigationInfo", "BG": "Background", "KEY": "DirectionalLight", "FILL": "DirectionalLight",
              "RIM": "DirectionalLight", "ENV": "EnvironmentLight", "STRUCT_skin": "Shape", "STRUCT_skull": "Shape", "STRUCT_heart": "Shape",
              "STRUCT_cortex_left": "Shape", "STRUCT_cortex_right": "Shape", "STRUCT_cerebellum": "Shape", "STRUCT_brainstem": "Shape"}
TORSO_DEFS.update({k: "Switch" for k in TORSO_SWITCHES})
TORSO_DEFS.update({vp: "Viewpoint" for vp in TORSO_VIEWPOINTS})
TORSO_GHOST = ["STRUCT_cortex_left", "STRUCT_cortex_right", "STRUCT_cerebellum", "STRUCT_brainstem"]

CODES = {
    "BRAIN_NOT_X3D": "the file is not X3D XML with a head and a Scene",
    "BRAIN_DEF_DUPLICATE": "a DEF name is used twice",
    "BRAIN_USE_UNRESOLVED": "a USE names a DEF that does not exist earlier in the file",
    "BRAIN_DEF_MISSING": "a contract DEF does not exist",
    "BRAIN_DEF_TYPE": "a contract DEF is the wrong node type",
    "BRAIN_DEF_ATTR": "a contract attribute, field or containment is wrong (headlight, EXAMINE, shader fields, viewpoint text, slices, audio, nesting, a Transform above a measured mesh)",
    "BRAIN_SWITCH_DEFAULT": "a contract Switch has the wrong whichChoice default, or content that must be drawn at load sits in a Switch child that is not the selected one",
    "BRAIN_AUDIO_AUTOSTART": "a looping AudioClip would start at load (startTime not in the future)",
    "BRAIN_INDEX_RANGE": "an index points outside the coordinate array (or below -1 in a coordIndex)",
    "BRAIN_INDEX_SHAPE": "an index list is not whole triangles or holds a non-integer",
    "BRAIN_DEGENERATE": "a triangle repeats a vertex, or collapsed triangles exceed the declared cap",
    "BRAIN_NONFINITE": "a coordinate is not a finite number",
    "BRAIN_ATTRIBUTE_COUNT": "normals or colours are not as long as the coordinates, or a coordinate array is missing or not whole points",
    "BRAIN_COUNT_MISMATCH": "a vertex, triangle, arc or point count differs from what the scene, sidecar or data file declares",
    "BRAIN_COUNT_UNDECLARED": "no declaration of the counts exists to compare with",
    "BRAIN_SIDECAR_STALE": "the build sidecar's sha256 is not the scene's sha256",
    "BRAIN_UNITS_UNDECLARED": "WorldInfo does not declare 1 unit = 1 mm",
    "BRAIN_UNITS_SCALE": "the geometry's extent is not plausible in millimetres",
    "BRAIN_PROVENANCE_HASH": "WorldInfo does not record the builder and source-mesh sha256",
    "BRAIN_BUILDER_MISMATCH": "the recorded builder hash is not the builder file's hash",
    "BRAIN_OIT_WITH_SHADER": "order-independent transparency is enabled in a scene (or page) that uses a custom shader",
    "BRAIN_SHADER_COMPONENT": "a shader node is used but the Shaders component is not declared (and the profile is not Full)",
    "BRAIN_SHADER_OPAQUE_FLAG": "a ComposedShader's Appearance has no Material with 0 < transparency < 1, so X_ITE draws it opaque",
    "BRAIN_TF_UNCLAMPED": "a volume transfer-function texture is not clamped to the edge",
    "BRAIN_LAYOUT_PROFILE": "a Layout node is used but the profile is not Full",
    "BRAIN_PARTICLE_PARENT": "a ParticleSystem is not a direct child of the Scene",
    "BRAIN_ENV_FACE_SIZE": "an environment cube-map face is not 64 x 64 px",
    "BRAIN_TEXTURE_MISSING": "a texture file named by the scene does not exist next to it, or a PNG is empty, truncated or has no pixels",
    "BRAIN_SYNTHETIC_TRACTS": "the tract group carries no SYNTHETIC metadata notice",
    "BRAIN_SYNTHETIC_ACTIV": "the activation group carries no ILLUSTRATIVE metadata notice",
    "BRAIN_SYNTHETIC_WORLDINFO": "WorldInfo lacks the SYNTHETIC / ILLUSTRATIVE / not-a-medical-device notices",
    "BRAIN_ALIGN_UNDECLARED": "WorldInfo does not disclose the bbox-fit alignment (scale triple and 'NOT a registration')",
    "BRAIN_ALIGN_FIT_RANGE": "the declared per-axis alignment scale is outside the declared fit range",
    "BRAIN_DEEP_OUTSIDE": "a deep structure (or the torso's brain ghost) has a vertex outside the box it must lie in",
    "BRAIN_REGION_OUTSIDE": "a region centroid lies outside the geometry it belongs to (its own hemisphere's cortex for a cortical region)",
    "BRAIN_LABEL_MISSING": "a region or structure has no label node, a label node does not display its region's name, or a structure has no label entry",
    "BRAIN_LABEL_ORPHAN": "a label entry names a structure that does not exist",
    "BRAIN_ATTRIBUTION": "WorldInfo or the head metadata lacks a required attribution or citation",
    "BRAIN_INPUT_MISSING": "strict mode: a side input the check needs was not found",
}


class GateError(Exception):
    """A scene violated a stated contract. `code` is a stable diagnostic."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class InstrumentError(Exception):
    """The reader could not complete. Exit 2, never a pass and never a catch."""


def need(condition: object, code: str, detail: str = "") -> None:
    if not condition:
        raise GateError(code, detail)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ------------------------------------------------------------------------------------------------ small readers
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def floats(text: str) -> list[float]:
    return [float(t) for t in (text or "").replace(",", " ").split()]


def ints(text: str) -> list[int]:
    return [int(t) for t in (text or "").replace(",", " ").split()]


_MF = re.compile(r'"((?:[^"\\]|\\.)*)"')


def mfstring(text: str) -> list[str]:
    """An MFString attribute: "a" "b" with backslash escapes. A bare string is returned as one item."""
    items = [m.replace('\\"', '"').replace("\\\\", "\\") for m in _MF.findall(text or "")]
    return items if items else ([text] if text else [])


def png_size(path: Path) -> tuple[int, int] | None:
    head = path.read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def png_problem(path: Path) -> str | None:
    """None if the file is a complete PNG (signature, IHDR with a size, an IDAT chunk, the closing IEND chunk), else a short reason."""
    b = path.read_bytes()
    if len(b) < 45 or b[:8] != PNG_SIG or b[12:16] != b"IHDR":
        return f"{len(b)} bytes, not a PNG"
    w, h = struct.unpack(">II", b[16:24])
    if w < 1 or h < 1:
        return f"PNG size {w}x{h}"
    if b"IDAT" not in b:
        return "PNG without an IDAT chunk (no pixels)"
    if not b.endswith(PNG_IEND):
        return "PNG without its closing IEND chunk (truncated)"
    return None


def is_identity(el: ET.Element) -> bool:
    """An identity Transform moves nothing; any other grouping node in TRANSFORM_TAGS is treated as moving what it holds."""
    if _local(el.tag) != "Transform":
        return False
    try:
        t, s = floats(el.get("translation", "0 0 0")), floats(el.get("scale", "1 1 1"))
        r = floats(el.get("rotation", "0 0 1 0"))
    except ValueError:
        return False
    return len(t) == 3 and len(s) == 3 and len(r) == 4 and all(x == 0.0 for x in t) and all(x == 1.0 for x in s) and r[3] == 0.0


def truthy(value: str | None) -> bool:
    return (value or "").strip().strip("\"'").lower() in ("true", "1", "yes", "on")


class Mesh:
    __slots__ = ("name", "el", "pts", "idx", "ntri", "kind")

    def __init__(self, name: str, el: ET.Element, pts: list[tuple[float, float, float]], idx: list[int], kind: str):
        self.name, self.el, self.pts, self.idx, self.kind = name, el, pts, idx, kind
        self.ntri = len(idx) // 3 if kind == "tri" else 0


class Scene:
    """One parsed file plus the findings against it."""

    def __init__(self, path: Path, kind: str, strict: bool):
        self.path, self.kind, self.strict = path, kind, strict
        self.data = path.read_bytes()
        self.sha = sha256_bytes(self.data)
        self.violations: list[dict] = []
        self.m: dict = {}
        self.skipped: list[dict] = []
        self.checks_run: list[str] = []
        try:
            self.root = ET.fromstring(self.data)
        except ET.ParseError as e:
            self.root = None
            self.add("BRAIN_NOT_X3D", f"not well-formed XML: {e}")
            return
        self.head = self.root.find("head")
        self.scene = self.root.find("Scene")
        if _local(self.root.tag) != "X3D" or self.scene is None or self.head is None:
            self.add("BRAIN_NOT_X3D", f"root <{_local(self.root.tag)}> head={self.head is not None} Scene={self.scene is not None}")
            self.root = None
            return
        self.order = {el: i for i, el in enumerate(self.root.iter())}
        self.parent = {c: p for p in self.root.iter() for c in p}
        self.defs: dict[str, ET.Element] = {}
        self.meshes: dict[str, Mesh] = {}
        self._wi: list[str] | None = None

    def add(self, code: str, detail: str) -> None:
        if code not in CODES:
            raise InstrumentError(f"unknown code {code}")
        self.violations.append({"code": code, "detail": detail[:400]})

    def skip(self, check: str, reason: str) -> None:
        self.skipped.append({"check": check, "reason": reason})

    def missing_input(self, what: str) -> None:
        if self.strict:
            self.add("BRAIN_INPUT_MISSING", what)
        else:
            self.skip(what, "input not found (not strict)")

    def resolve(self, el: ET.Element | None) -> ET.Element | None:
        if el is not None and el.get("USE"):
            return self.defs.get(el.get("USE"))
        return el

    def inside(self, el: ET.Element, ancestor: ET.Element) -> bool:
        cur = el
        while cur is not None:
            if cur is ancestor:
                return True
            cur = self.parent.get(cur)
        return False

    @property
    def world_info(self) -> list[str]:
        if self._wi is None:
            wi = self.scene.find("WorldInfo")
            self._wi = mfstring(wi.get("info", "")) if wi is not None else []
            self.m["world_info_items"] = len(self._wi)
        return self._wi

    @property
    def world_text(self) -> str:
        return "\n".join(self.world_info)


# ------------------------------------------------------------------------------------------------ checks: structure
def check_defs(S: Scene) -> None:
    """DEF names unique, USE resolvable, every contract DEF present with the right type."""
    for el in S.root.iter():
        d, u = el.get("DEF"), el.get("USE")
        if d:
            if d in S.defs:
                S.add("BRAIN_DEF_DUPLICATE", d)
            else:
                S.defs[d] = el
        if u and (u not in S.defs or S.order[S.defs[u]] > S.order[el]):
            S.add("BRAIN_USE_UNRESOLVED", f"USE={u} on <{_local(el.tag)}>")
    contract = BRAIN_DEFS if S.kind == "brain" else TORSO_DEFS
    for name, tag in contract.items():
        el = S.defs.get(name)
        if el is None:
            S.add("BRAIN_DEF_MISSING", name)
        elif _local(el.tag) != tag:
            S.add("BRAIN_DEF_TYPE", f"{name} is <{_local(el.tag)}>, expected <{tag}>")
    wanted = BRAIN_SWITCH_DEFAULTS if S.kind == "brain" else TORSO_SWITCHES
    for name, choice in wanted.items():
        el = S.defs.get(name)
        if el is not None and el.get("whichChoice") != choice:
            S.add("BRAIN_SWITCH_DEFAULT", f"{name}.whichChoice={el.get('whichChoice')!r}, expected {choice}")
    S.m["defs"] = len(S.defs)
    S.m["contract_defs"] = len(contract)


def _attr(S: Scene, name: str, **want: str) -> None:
    el = S.defs.get(name)
    if el is None:
        return
    for k, v in want.items():
        if el.get(k) != v:
            S.add("BRAIN_DEF_ATTR", f"{name}.{k}={el.get(k)!r}, expected {v!r}")


def check_contract_brain(S: Scene) -> None:
    nav = S.defs.get("NAV")
    _attr(S, "NAV", headlight="false")
    if nav is not None and "EXAMINE" not in (nav.get("type") or ""):
        S.add("BRAIN_DEF_ATTR", "NAV.type lacks EXAMINE")
    for vp in VIEWPOINTS:
        el = S.defs.get(vp)
        if el is not None and not (el.get("description") or "").strip():
            S.add("BRAIN_DEF_ATTR", f"{vp} has no description")
    for h in "LR":
        sh = S.defs.get(f"SH_CORTEX_{h}")
        if sh is not None:
            have = {f.get("name") for f in sh.findall("field")}
            miss = [f for f in SHADER_FIELDS if f not in have]
            if miss:
                S.add("BRAIN_DEF_ATTR", f"SH_CORTEX_{h} lacks fields {miss}")
    for child, anc in BRAIN_INSIDE:
        c = S.defs.get(child)
        if c is None:
            continue
        if anc is None:
            continue
        a = S.defs.get(anc)
        if a is not None and not S.inside(c, a):
            S.add("BRAIN_DEF_ATTR", f"{child} is not inside {anc}")
    sl = S.defs.get("SW_SLICES")
    if sl is not None:
        n = len(sl.findall(".//Shape"))
        S.m["slices"] = n
        if not SLICES[0] <= n <= SLICES[1]:
            S.add("BRAIN_DEF_ATTR", f"SW_SLICES holds {n} slices, expected {SLICES[0]} to {SLICES[1]}")
    au = S.defs.get("AUDIO")
    if au is not None:
        if au.get("loop") != "true":
            S.add("BRAIN_DEF_ATTR", "AUDIO.loop is not true")
        if "m01-drift.ogg" not in (au.get("url") or ""):
            S.add("BRAIN_DEF_ATTR", "AUDIO.url is not audio/m01-drift.ogg")
        try:
            start = float(au.get("startTime", "0"))
        except ValueError:
            start = 0.0
        if not start >= AUDIO_START_MIN:
            S.add("BRAIN_AUDIO_AUTOSTART", f"AUDIO.startTime={au.get('startTime')!r} (a looping clip with startTime in the past plays at load)")


def check_contract_torso(S: Scene) -> None:
    for vp in TORSO_VIEWPOINTS:
        el = S.defs.get(vp)
        if el is not None and not (el.get("description") or "").strip():
            S.add("BRAIN_DEF_ATTR", f"{vp} has no description")
    _attr(S, "NAV", headlight="false")
    for name, el in S.defs.items():
        if name.startswith("STRUCT_") and _local(el.tag) != "Shape":
            S.add("BRAIN_DEF_TYPE", f"{name} is <{_local(el.tag)}>, expected <Shape>")
        elif name.startswith("STRUCT_"):
            sw = S.parent.get(S.parent.get(el))
            if sw is None or _local(sw.tag) != "Switch":
                S.add("BRAIN_DEF_ATTR", f"{name} is not inside a Group inside a Switch")


def check_visibility(S: Scene) -> None:
    """Valid is not visible. (1) Everything the checks measure and the page shows at load must be drawn: for every Switch above it,
    whichChoice is the index of the child that holds it (a missing whichChoice is -1, which draws nothing). (2) No grouping node that
    moves, scales or rotates sits above a measured mesh: the containment checks read raw coordinates and would measure the wrong place."""
    if S.kind == "brain":
        shown = ["G_CORTEX_L", "G_CORTEX_R", "SH_CORTEX_L", "SH_CORTEX_R", "TS_CORTEX_L", "TS_CORTEX_R"] + [f"STRUCT_{s}" for s in STRUCTS]
        measured = ["GEO_CORTEX_L", "GEO_CORTEX_R"] + [f"STRUCT_{s}" for s in STRUCTS]
    else:
        shown, measured = [], []
        for name in sorted(S.defs):
            if not (name.startswith("STRUCT_") and _local(S.defs[name].tag) == "Shape"):
                continue
            measured.append(name)
            cur, hidden = S.parent.get(S.defs[name]), False
            while cur is not None:
                hidden = hidden or TORSO_SWITCHES.get(cur.get("DEF") or "") == "-1"
                cur = S.parent.get(cur)
            if not hidden:
                shown.append(name)
    for name in shown:
        child = S.defs.get(name)
        while child is not None and S.parent.get(child) is not None:
            sw = S.parent[child]
            if _local(sw.tag) == "Switch":
                try:
                    which = int(sw.get("whichChoice", "-1"))
                except ValueError:
                    which = -1
                idx = list(sw).index(child)
                if which != idx:
                    S.add("BRAIN_SWITCH_DEFAULT", f"{name} sits in child {idx} of Switch {sw.get('DEF') or '(unnamed)'} whose whichChoice is {which}: it is not drawn at load")
                    break
            child = sw
    for name in measured:
        cur = S.parent.get(S.defs.get(name)) if name in S.defs else None
        while cur is not None:
            if _local(cur.tag) in TRANSFORM_TAGS and not is_identity(cur):
                S.add("BRAIN_DEF_ATTR", f"{name} sits under <{_local(cur.tag)}{' DEF=' + cur.get('DEF') if cur.get('DEF') else ''}> that moves it; the containment checks read raw coordinates and cannot see through it")
                break
            cur = S.parent.get(cur)


def check_textures(S: Scene) -> None:
    base = S.path.parent
    n = 0
    for el in S.root.iter():
        tag = _local(el.tag)
        if tag not in ("ImageTexture", "MovieTexture") or el.get("USE"):
            continue
        for u in mfstring(el.get("url", "")):
            if re.match(r"^[a-z]+:", u):
                continue
            n += 1
            if not (base / u).is_file():
                S.add("BRAIN_TEXTURE_MISSING", u)
            elif u.lower().endswith(".png"):
                why = png_problem(base / u)
                if why:
                    S.add("BRAIN_TEXTURE_MISSING", f"{u}: {why}")
    S.m["texture_files"] = n
    faces = 0
    for cube in S.root.iter("ComposedCubeMapTexture"):
        for f in cube:
            for u in mfstring(f.get("url", "")):
                p = base / u
                if not p.is_file():
                    continue
                faces += 1
                size = png_size(p)
                if size != (ENV_FACE_PX, ENV_FACE_PX):
                    S.add("BRAIN_ENV_FACE_SIZE", f"{u} is {size}, expected {ENV_FACE_PX}x{ENV_FACE_PX}")
    S.m["env_faces"] = faces


# ------------------------------------------------------------------------------------------------ checks: geometry
def _coordinate(S: Scene, geo: ET.Element) -> ET.Element | None:
    for tag in ("Coordinate", "CoordinateDouble"):
        c = geo.find(tag)
        if c is not None:
            return S.resolve(c)
    return None


def _points(S: Scene, geo: ET.Element, label: str) -> list[tuple[float, float, float]] | None:
    c = _coordinate(S, geo)
    if c is None:
        S.add("BRAIN_ATTRIBUTE_COUNT", f"{label}: no Coordinate")
        return None
    try:
        v = floats(c.get("point", ""))
    except ValueError:
        S.add("BRAIN_NONFINITE", f"{label}: non-numeric coordinate token")
        return None
    if len(v) % 3:
        S.add("BRAIN_ATTRIBUTE_COUNT", f"{label}: {len(v)} coordinate numbers is not whole points")
        return None
    if not all(math.isfinite(x) for x in v):
        S.add("BRAIN_NONFINITE", f"{label}: NaN or infinity in coordinates")
        return None
    return [(v[i], v[i + 1], v[i + 2]) for i in range(0, len(v), 3)]


def _owner_name(S: Scene, geo: ET.Element) -> str:
    p = S.parent.get(geo)
    if p is not None and p.get("DEF"):
        return p.get("DEF")
    return geo.get("DEF") or f"{_local(geo.tag)}@{S.order[geo]}"


def check_geometry(S: Scene) -> None:
    """Index range, whole triangles, repeated vertices, collapsed triangles, attribute lengths, finite numbers."""
    tris = verts = collapsed = repeated = 0
    per: dict[str, dict] = {}
    for geo in S.root.iter():
        tag = _local(geo.tag)
        if tag not in ("IndexedTriangleSet", "IndexedFaceSet", "IndexedLineSet") or geo.get("USE"):
            continue
        name = _owner_name(S, geo)
        pts = _points(S, geo, name)
        if pts is None:
            continue
        n = len(pts)
        if tag == "IndexedTriangleSet":
            try:
                idx = ints(geo.get("index", ""))
            except ValueError:
                S.add("BRAIN_INDEX_SHAPE", f"{name}: non-integer in index")
                continue
            if len(idx) % 3:
                S.add("BRAIN_INDEX_SHAPE", f"{name}: {len(idx)} indices is not whole triangles")
                continue
            if idx and (min(idx) < 0 or max(idx) >= n):
                S.add("BRAIN_INDEX_RANGE", f"{name}: index range {min(idx)}..{max(idx)} against {n} vertices")
                continue
            m = Mesh(name, geo, pts, idx, "tri")
            S.meshes[name] = m
            rep = col = 0
            for i in range(0, len(idx), 3):
                a, b, c = idx[i], idx[i + 1], idx[i + 2]
                if a == b or b == c or a == c:
                    rep += 1
                    continue
                pa, pb, pc = pts[a], pts[b], pts[c]
                ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
                vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
                cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                if 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz) <= AREA_EPS:
                    col += 1
            if rep:
                S.add("BRAIN_DEGENERATE", f"{name}: {rep} triangles repeat a vertex index")
            for attr_tag, attr_name in (("Normal", "vector"), ("Color", "color"), ("ColorRGBA", "color")):
                a = geo.find(attr_tag)
                a = S.resolve(a) if a is not None else None
                if a is not None:
                    try:
                        k = len(floats(a.get(attr_name, "")))
                    except ValueError:
                        S.add("BRAIN_NONFINITE", f"{name}: non-numeric {attr_tag}")
                        continue
                    per_vertex = 4 if attr_tag == "ColorRGBA" else 3
                    if k != n * per_vertex:
                        S.add("BRAIN_ATTRIBUTE_COUNT", f"{name}: {attr_tag} holds {k / per_vertex:g} values for {n} vertices")
            tris += m.ntri
            verts += n
            collapsed += col
            repeated += rep
            per[name] = {"vertices": n, "triangles": m.ntri, "collapsed": col}
        else:
            try:
                ci = ints(geo.get("coordIndex", ""))
            except ValueError:
                S.add("BRAIN_INDEX_SHAPE", f"{name}: non-integer in coordIndex")
                continue
            if ci and (min(ci) < -1 or max(ci) >= n):
                S.add("BRAIN_INDEX_RANGE", f"{name}: coordIndex range {min(ci)}..{max(ci)} against {n} vertices")
                continue
            need_n = 3 if tag == "IndexedFaceSet" else 2
            loops, cur = [], []
            for i in ci:
                if i == -1:
                    loops.append(cur)
                    cur = []
                else:
                    cur.append(i)
            if cur:
                loops.append(cur)
            bad = sum(1 for lp in loops if len(set(lp)) < need_n)
            if bad:
                S.add("BRAIN_DEGENERATE", f"{name}: {bad} of {len(loops)} {'faces' if tag == 'IndexedFaceSet' else 'polylines'} have fewer than {need_n} distinct vertices")
            S.meshes[name] = Mesh(name, geo, pts, ci, "face" if tag == "IndexedFaceSet" else "line")
            per[name] = {"vertices": n, "loops": len(loops)}
    frac = collapsed / tris if tris else 0.0
    if frac > ZERO_AREA_FRAC_MAX:
        worst = sorted(((v["collapsed"], k) for k, v in per.items() if v.get("collapsed")), reverse=True)[:3]
        S.add("BRAIN_DEGENERATE", f"{collapsed} of {tris} triangles are collapsed (area <= {AREA_EPS} mm2), {frac:.4%} > cap {ZERO_AREA_FRAC_MAX:.2%}; worst {worst}")
    S.m["geometry"] = {"vertices": verts, "triangles": tris, "shapes": len(per), "collapsed_triangles": collapsed,
                       "collapsed_fraction": round(frac, 6), "collapsed_by_shape": {k: v["collapsed"] for k, v in per.items() if v.get("collapsed")}}


def _bbox(pts: list[tuple[float, float, float]]) -> tuple[list[float], list[float]]:
    return ([min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)])


def _shape_mesh(S: Scene, shape: ET.Element) -> Mesh | None:
    for geo in shape.iter():
        if _local(geo.tag) == "IndexedTriangleSet":
            geo = S.resolve(geo) if geo.get("USE") else geo
            for m in S.meshes.values():
                if m.el is geo:
                    return m
    return None


# ------------------------------------------------------------------------------------------------ checks: alignment
def check_alignment_brain(S: Scene) -> None:
    left, right = _geo_mesh(S, "GEO_CORTEX_L"), _geo_mesh(S, "GEO_CORTEX_R")
    if left is None or right is None:
        return  # the missing DEF or geometry was already reported
    lo, hi = _bbox(left.pts + right.pts)
    ext = [hi[i] - lo[i] for i in range(3)]
    S.m["cortex_bbox"] = {"min": [round(x, 2) for x in lo], "max": [round(x, 2) for x in hi], "extent": [round(x, 2) for x in ext]}
    for i, a in enumerate("xyz"):
        if not BRAIN_EXTENT_MM[0] <= ext[i] <= BRAIN_EXTENT_MM[1]:
            S.add("BRAIN_UNITS_SCALE", f"cortex extent along {a} is {ext[i]:.1f}, plausible millimetres {BRAIN_EXTENT_MM[0]:.0f} to {BRAIN_EXTENT_MM[1]:.0f}")
    tol = [DEEP_TOL_FRAC * e for e in ext]
    table = {}
    for s in STRUCTS:
        shape = S.defs.get(f"STRUCT_{s}")
        m = _shape_mesh(S, shape) if shape is not None else None
        if m is None:
            continue
        slo, shi = _bbox(m.pts)
        over = [max(lo[i] - slo[i], shi[i] - hi[i], 0.0) for i in range(3)]
        allow = list(tol)
        floor_allow = tol[1] + (INFRA_DESCENT_FRAC * ext[1] if s in INFRATENTORIAL else 0.0)
        bad = []
        for i, a in enumerate("xyz"):
            if slo[i] < lo[i] - (floor_allow if i == 1 else allow[i]):
                bad.append(f"{a} min {slo[i]:.1f} < {lo[i] - (floor_allow if i == 1 else allow[i]):.1f}")
            if shi[i] > hi[i] + allow[i]:
                bad.append(f"{a} max {shi[i]:.1f} > {hi[i] + allow[i]:.1f}")
        table[s] = {"overshoot_frac": [round(over[i] / ext[i], 4) for i in range(3)], "ok": not bad}
        if bad:
            S.add("BRAIN_DEEP_OUTSIDE", f"{s}: {'; '.join(bad)} (cortex bbox {[round(x, 1) for x in lo]}..{[round(x, 1) for x in hi]}, tolerance {DEEP_TOL_FRAC:.0%} per axis)")
    S.m["deep_containment"] = {"tolerance_frac": DEEP_TOL_FRAC, "infratentorial_descent_frac": INFRA_DESCENT_FRAC, "structures": table}


def _geo_mesh(S: Scene, def_name: str) -> Mesh | None:
    el = S.defs.get(def_name)
    if el is None:
        return None
    for m in S.meshes.values():
        if m.el is el:
            return m
    return None


def check_alignment_notice(S: Scene) -> None:
    items = [i for i in S.world_info if "ALIGNMENT" in i]
    if not items:
        S.add("BRAIN_ALIGN_UNDECLARED", "no WorldInfo item with ALIGNMENT")
        return
    text = " ".join(items)
    m = re.search(r"scale\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)", text)
    if not m or "NOT a registration" not in text:
        S.add("BRAIN_ALIGN_UNDECLARED", "ALIGNMENT item lacks a scale triple or the words 'NOT a registration'")
        return
    scale = [float(g) for g in m.groups()]
    S.m["alignment_scale"] = scale
    dev = [abs(1 - s) for s in scale]
    S.m["alignment_fit_percent"] = [round(100 * d, 1) for d in dev]
    for a, d in zip("xyz", dev):
        if d > ALIGN_FIT_MAX:
            S.add("BRAIN_ALIGN_FIT_RANGE", f"declared scale along {a} deviates {d:.1%} > {ALIGN_FIT_MAX:.0%}")


def check_alignment_torso(S: Scene) -> None:
    skin = S.defs.get("STRUCT_skin")
    ms = _shape_mesh(S, skin) if skin is not None else None
    if ms is not None:
        lo, hi = _bbox(ms.pts)
        ext = [hi[i] - lo[i] for i in range(3)]
        S.m["skin_extent"] = [round(x, 1) for x in ext]
        if not TORSO_WIDTH_MM[0] <= ext[0] <= TORSO_WIDTH_MM[1]:
            S.add("BRAIN_UNITS_SCALE", f"skin width {ext[0]:.1f} not in {TORSO_WIDTH_MM} millimetres")
    skull = S.defs.get("STRUCT_skull")
    mk = _shape_mesh(S, skull) if skull is not None else None
    if mk is None:
        return
    lo, hi = _bbox(mk.pts)
    ext = [hi[i] - lo[i] for i in range(3)]
    table = {}
    for name in TORSO_GHOST:
        el = S.defs.get(name)
        m = _shape_mesh(S, el) if el is not None else None
        if m is None:
            continue
        slo, shi = _bbox(m.pts)
        bad = []
        for i, a in enumerate("xyz"):
            t = DEEP_TOL_FRAC * ext[i]
            # the brain stem leaves the skull through the foramen magnum, so only the floor (-y) of the stem is free
            free_floor = INFRA_DESCENT_FRAC * ext[1] if (i == 1 and name in ("STRUCT_brainstem",)) else 0.0
            if slo[i] < lo[i] - t - free_floor:
                bad.append(f"{a} min {slo[i]:.1f} < {lo[i] - t - free_floor:.1f}")
            if shi[i] > hi[i] + t:
                bad.append(f"{a} max {shi[i]:.1f} > {hi[i] + t:.1f}")
        table[name] = {"ok": not bad}
        if bad:
            S.add("BRAIN_DEEP_OUTSIDE", f"{name}: {'; '.join(bad)} (skull bbox, tolerance {DEEP_TOL_FRAC:.0%} per axis)")
    S.m["ghost_containment"] = {"tolerance_frac": DEEP_TOL_FRAC, "structures": table}


# ------------------------------------------------------------------------------------------------ checks: honesty
def _metadata(el: ET.Element | None, name: str) -> str | None:
    if el is None:
        return None
    for md in el.iter():
        if _local(md.tag).startswith("Metadata") and md.get("name") == name:
            return " ".join(mfstring(md.get("value", ""))) or md.get("value", "")
    return None


def check_notices(S: Scene) -> None:
    text = S.world_text
    low = text.lower()
    miss = []
    if S.kind == "brain":
        if "SYNTHETIC" not in text:
            miss.append("SYNTHETIC")
        if "ILLUSTRATIVE" not in text:
            miss.append("ILLUSTRATIVE")
        if "not tractography" not in low:
            miss.append("'not tractography'")
    else:
        if "ILLUSTRATIVE" not in text:
            miss.append("ILLUSTRATIVE")
        if "not this subject" not in low:
            miss.append("'not this subject' (the template folds are not the subject's)")
        if "not for diagnosis" not in low:
            miss.append("'not for diagnosis'")
    if S.kind == "brain" and "not a medical device" not in low:
        miss.append("'not a medical device'")
    if miss:
        S.add("BRAIN_SYNTHETIC_WORLDINFO", "WorldInfo lacks " + ", ".join(miss))
    if S.kind != "brain":
        meta = {m.get("name"): (m.get("content") or "") for m in S.head.findall("meta")}
        if "ILLUSTRATIVE" not in meta.get("synthetic", ""):
            S.add("BRAIN_SYNTHETIC_WORLDINFO", "head meta 'synthetic' lacks ILLUSTRATIVE")
        return
    tr = S.defs.get("TRACTS")
    if tr is not None:
        v = _metadata(tr, "SYNTHETIC")
        if v is None or "not tractography" not in v.lower():
            S.add("BRAIN_SYNTHETIC_TRACTS", f"TRACTS metadata SYNTHETIC={v!r}")
    ac = S.defs.get("SW_ACTIV")
    if ac is not None:
        v = _metadata(ac, "ILLUSTRATIVE")
        if v is None or "not measured" not in v.lower():
            S.add("BRAIN_SYNTHETIC_ACTIV", f"SW_ACTIV metadata ILLUSTRATIVE={v!r}")


def check_units_provenance(S: Scene) -> None:
    text = S.world_text
    if not re.search(r"1\s+(?:scene\s+)?unit\s*=\s*1\s*mm", text, re.I):
        S.add("BRAIN_UNITS_UNDECLARED", "WorldInfo has no '1 unit = 1 mm' statement")
    if S.kind == "brain":
        b = re.search(r"builder[^;]*?sha256\s+([0-9a-f]{16,64})", text)
        d = re.search(r"mesh npz sha256\s+([0-9a-f]{16,64})", text)
        miss = [n for n, g in (("builder sha256", b), ("source mesh sha256", d)) if not g]
        if miss:
            S.add("BRAIN_PROVENANCE_HASH", "WorldInfo does not record " + " and ".join(miss))
        S.m["builder_sha"] = b.group(1) if b else None
        S.m["mesh_sha"] = d.group(1) if d else None
    else:
        b = re.search(r"builder sha256\s+([0-9a-f]{16,64})", text, re.I)
        if not b:
            S.add("BRAIN_PROVENANCE_HASH", "WorldInfo does not record the builder sha256")
        S.m["builder_sha"] = b.group(1) if b else None


def check_attribution(S: Scene) -> None:
    text = S.world_text
    if S.kind == "brain":
        need_tokens = ["Fischl", "Fonov", "FreeSurfer", "licence grade", "grade Confirmed"]
        meta_ok = True
    else:
        need_tokens = ["Wasserthal", "10.1148/ryai.230024", "CC BY 4.0", "Changes were made", "s1397", "Fischl", "Fonov", "Apache-2.0"]
        meta = {m.get("name"): (m.get("content") or "") for m in S.head.findall("meta")}
        meta_ok = "Wasserthal" in meta.get("rights", "") and "10.1148/ryai.230024" in meta.get("rights", "")
    missing = [t for t in need_tokens if t.lower() not in text.lower()]
    if missing or not meta_ok:
        S.add("BRAIN_ATTRIBUTION", f"WorldInfo lacks {missing}" + ("" if meta_ok else "; head meta 'rights' lacks the data attribution"))


# ------------------------------------------------------------------------------------------------ checks: runtime traps
def _oit_in_scene(S: Scene) -> list[str]:
    hits = []
    for el in S.root.iter():
        tag = _local(el.tag)
        for k, v in el.attrib.items():
            if "orderindependenttransparency" in k.lower() and truthy(v):
                hits.append(f"<{tag} {k}={v!r}>")
        if tag == "meta" and "orderindependenttransparency" in (el.get("name") or "").lower() and truthy(el.get("content")):
            hits.append(f"<meta name={el.get('name')!r} content={el.get('content')!r}>")
        if tag.startswith("Metadata") and "orderindependenttransparency" in (el.get("name") or "").lower():
            if truthy(el.get("value")) or "true" in (el.get("value") or "").lower():
                hits.append(f"<{tag} name={el.get('name')!r}>")
        if el.text and _OIT_TEXT.search(el.text):
            hits.append(f"<{tag}> text switches it on")
    return hits


_OIT_TEXT = re.compile(r"OrderIndependentTransparency[\"']?\s*[,:=]\s*[\"']?(true|1)\b", re.I)


def check_runtime_traps(S: Scene, page_texts: dict[str, str]) -> None:
    shaders = [el for el in S.root.iter() if _local(el.tag) in SHADER_NODES and not el.get("USE")]
    S.m["shader_nodes"] = len(shaders)
    oit = _oit_in_scene(S)
    for name, text in page_texts.items():
        if _OIT_TEXT.search(text):
            oit.append(f"page {name}")
    S.m["oit_enabled"] = bool(oit)
    if oit and shaders:
        S.add("BRAIN_OIT_WITH_SHADER", f"OIT enabled ({'; '.join(oit[:3])}) with {len(shaders)} custom shader node(s): glass vanishes on X_ITE 16.6.0 (GL_INVALID_OPERATION)")
    if shaders:
        comps = {c.get("name"): c.get("level") for c in S.head.findall("component")}
        profile = S.root.get("profile", "")
        try:
            level = int(comps.get("Shaders", "0"))
        except ValueError:
            level = 0
        if level < 1 and profile != "Full":
            S.add("BRAIN_SHADER_COMPONENT", f"{len(shaders)} shader node(s), no <component name='Shaders' level='1'/>, profile={profile!r}: X_ITE ignores the shader silently")
    for sh in shaders:
        app = S.parent.get(sh)
        name = sh.get("DEF") or f"{_local(sh.tag)}@{S.order[sh]}"
        if app is None or _local(app.tag) != "Appearance":
            S.add("BRAIN_SHADER_OPAQUE_FLAG", f"{name}: parent is not an Appearance")
            continue
        mat = S.resolve(app.find("Material")) if app.find("Material") is not None else None
        try:
            t = float(mat.get("transparency", "0")) if mat is not None else 0.0
        except ValueError:
            t = 0.0
        if not 0.0 < t < 1.0:
            S.add("BRAIN_SHADER_OPAQUE_FLAG", f"{name}: Appearance has no Material with 0 < transparency < 1 (X_ITE draws it opaque)")
    volumes = 0
    for style in S.root.iter():
        if _local(style.tag) not in VOLUME_STYLES or style.get("USE"):
            continue
        for tf in style:
            if tf.get("containerField") != "transferFunction":
                continue
            volumes += 1
            tf = S.resolve(tf) if tf.get("USE") else tf
            props = tf.find("TextureProperties") if tf is not None else None
            ok = props is not None and all((props.get(k) or "") in ("CLAMP_TO_EDGE", "CLAMP") for k in ("boundaryModeS", "boundaryModeT"))
            if not ok:
                S.add("BRAIN_TF_UNCLAMPED", f"transfer-function texture under <{_local(style.tag)}> is not CLAMP_TO_EDGE in S and T (unclamped: opaque cube, nonblack .4143 vs .1107)")
    S.m["transfer_functions"] = volumes
    profile = S.root.get("profile", "")
    lay = [el for el in S.root.iter() if _local(el.tag) in LAYOUT_NODES]
    if lay and profile != "Full":
        S.add("BRAIN_LAYOUT_PROFILE", f"<{_local(lay[0].tag)}> used under profile {profile!r}; X_ITE needs Full (use Billboard + Text)")
    for ps in S.root.iter("ParticleSystem"):
        if S.parent.get(ps) is not S.scene:
            S.add("BRAIN_PARTICLE_PARENT", "ParticleSystem is not a child of the Scene")


# ------------------------------------------------------------------------------------------------ checks: counts and data files
def _tract_counts(S: Scene) -> tuple[int, int] | None:
    m = _geo_mesh(S, "GEO_TRACTS")
    if m is None:
        return None
    arcs, cur = 0, 0
    for i in m.idx:
        if i == -1:
            arcs += 1 if cur else 0
            cur = 0
        else:
            cur += 1
    arcs += 1 if cur else 0
    return arcs, len(m.pts)


def check_counts_brain(S: Scene, sidecar: Path | None) -> None:
    geo = S.m.get("geometry", {})
    cl, cr = _geo_mesh(S, "GEO_CORTEX_L"), _geo_mesh(S, "GEO_CORTEX_R")
    have = {}
    if cl is not None and cr is not None:
        have["cortex_verts"] = len(cl.pts) + len(cr.pts)
        have["cortex_tris"] = cl.ntri + cr.ntri
    deep = 0
    for s in STRUCTS:
        shape = S.defs.get(f"STRUCT_{s}")
        m = _shape_mesh(S, shape) if shape is not None else None
        deep += m.ntri if m is not None else 0
    have["deep_tris"] = deep
    tc = _tract_counts(S)
    if tc:
        have["tract_fibres"], have["tract_points"] = tc
    S.m["counts"] = have
    declared_cortex = False
    wi = re.search(r"the\s+(\d+)\s+tract arcs\s+\((\d+)\s+points\)", S.world_text)
    if wi and tc:
        if (int(wi.group(1)), int(wi.group(2))) != tc:
            S.add("BRAIN_COUNT_MISMATCH", f"WorldInfo declares {wi.group(1)} tract arcs ({wi.group(2)} points); GEO_TRACTS has {tc[0]} ({tc[1]})")
    elif tc:
        S.add("BRAIN_COUNT_UNDECLARED", "WorldInfo does not declare the tract arc and point counts")
    wc = re.search(r"counts:[^\"]*?cortex\s+(\d+)\s+vertices\s+(\d+)\s+triangles", S.world_text)
    if wc and "cortex_verts" in have:
        declared_cortex = True
        if (int(wc.group(1)), int(wc.group(2))) != (have["cortex_verts"], have["cortex_tris"]):
            S.add("BRAIN_COUNT_MISMATCH", f"WorldInfo counts line declares cortex {wc.group(1)} vertices {wc.group(2)} triangles; geometry has {have['cortex_verts']} and {have['cortex_tris']}")
    if sidecar is None:
        S.missing_input("build sidecar (<scene>.build.json)")
        if not declared_cortex:
            S.add("BRAIN_COUNT_UNDECLARED", "neither WorldInfo nor a sidecar declares the cortex and deep counts")
        return
    try:
        side = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InstrumentError(f"cannot read sidecar {sidecar.name}: {e}") from None
    S.m["sidecar_sha256"] = sha256_bytes(sidecar.read_bytes())
    if side.get("sha256") != S.sha:
        S.add("BRAIN_SIDECAR_STALE", f"sidecar {sidecar.name} records scene sha256 {str(side.get('sha256'))[:12]}, the file is {S.sha[:12]}")
    for key in ("cortex_verts", "cortex_tris", "deep_tris", "tract_fibres", "tract_points"):
        if key not in side:
            S.add("BRAIN_COUNT_UNDECLARED", f"sidecar lacks {key}")
        elif key in have and side[key] != have[key]:
            S.add("BRAIN_COUNT_MISMATCH", f"sidecar declares {key}={side[key]}, geometry has {have[key]}")
    bsha = S.m.get("builder_sha")
    if bsha and side.get("builder_sha16") and not bsha.startswith(side["builder_sha16"]) and not side["builder_sha16"].startswith(bsha[:16]):
        S.add("BRAIN_BUILDER_MISMATCH", f"WorldInfo builder sha {bsha[:16]} differs from sidecar builder_sha16 {side['builder_sha16']}")


def check_builder(S: Scene, builder: Path | None) -> None:
    bsha = S.m.get("builder_sha")
    if builder is None:
        S.missing_input("builder file")
        return
    actual = sha256_bytes(builder.read_bytes())
    S.m["builder_file"] = {"name": builder.name, "sha256": actual}
    if bsha and not actual.startswith(bsha[:16]):
        S.add("BRAIN_BUILDER_MISMATCH", f"WorldInfo records builder sha {bsha[:16]}, {builder.name} is {actual[:16]}: the scene was not made by the shipped builder")


def check_regions_brain(S: Scene, regions: Path | None) -> None:
    if regions is None:
        S.missing_input("regions.json")
        return
    try:
        data = json.loads(regions.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise InstrumentError(f"cannot read {regions.name}: {e}") from None
    S.m["regions_sha256"] = sha256_bytes(regions.read_bytes())
    cl, cr = _geo_mesh(S, "GEO_CORTEX_L"), _geo_mesh(S, "GEO_CORTEX_R")
    box = _bbox(cl.pts + cr.pts) if cl is not None and cr is not None else None
    hemi_box = {"L": _bbox(cl.pts), "R": _bbox(cr.pts)} if cl is not None and cr is not None else {}
    deep_boxes = {}
    for s in STRUCTS:
        shape = S.defs.get(f"STRUCT_{s}")
        m = _shape_mesh(S, shape) if shape is not None else None
        if m is not None:
            deep_boxes[s] = _bbox(m.pts)
    checked = 0
    for r in data:
        rid = r.get("id", "")
        lbl = "LBL_" + rid.replace("-", "_")
        c = r.get("centroid")
        if lbl not in S.defs:
            S.add("BRAIN_LABEL_MISSING", f"region {rid} has no label node {lbl}")
        else:
            shown = [x.strip().lower() for tx in S.defs[lbl].iter("Text") for x in mfstring(tx.get("string", ""))]
            if str(r.get("name", "")).strip().lower() not in shown:
                S.add("BRAIN_LABEL_MISSING", f"label {lbl} does not display the region name {r.get('name')!r} (it shows {shown[:2]})")
        if not (isinstance(c, list) and len(c) == 3 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in c)):
            S.add("BRAIN_REGION_OUTSIDE", f"region {rid}: centroid {c!r} is not three finite numbers")
            continue
        checked += 1
        if rid.startswith("deep-"):
            b = deep_boxes.get(rid[5:])
        else:
            b = hemi_box.get(r.get("hemi")) or box
        if b is None:
            continue
        lo, hi = b
        ext = [hi[i] - lo[i] for i in range(3)]
        tol = [REGION_TOL_FRAC * e for e in ext]
        if any(c[i] < lo[i] - tol[i] or c[i] > hi[i] + tol[i] for i in range(3)):
            S.add("BRAIN_REGION_OUTSIDE", f"region {rid}: centroid {c} outside {'its structure' if rid.startswith('deep-') else 'its hemisphere'} bbox")
    S.m["regions"] = {"entries": len(data), "centroids_checked": checked}


def check_labels_torso(S: Scene, regions: Path | None) -> None:
    if regions is None:
        S.missing_input("torso_regions.json")
        return
    try:
        data = json.loads(regions.read_text(encoding="utf-8"))
        entries = data["regions"]
    except (OSError, ValueError, KeyError) as e:
        raise InstrumentError(f"cannot read {regions.name}: {e}") from None
    S.m["regions_sha256"] = sha256_bytes(regions.read_bytes())
    bsha = S.m.get("builder_sha")
    if bsha and data.get("builder_sha256") and not data["builder_sha256"].startswith(bsha[:16]):
        S.add("BRAIN_BUILDER_MISMATCH", f"WorldInfo builder sha {bsha[:16]} differs from torso_regions.json builder_sha256 {data['builder_sha256'][:16]}")
    variant = next((m.get("content") for m in S.head.findall("meta") if m.get("name") == "variant"), "")
    by_id = {e.get("id"): e for e in entries}
    shapes = {n: el for n, el in S.defs.items() if n.startswith("STRUCT_") and _local(el.tag) == "Shape"}
    for n in sorted(shapes):
        e = by_id.get(n)
        if e is None or not str(e.get("label", "")).strip():
            S.add("BRAIN_LABEL_MISSING", f"{n} has no label entry in {regions.name}")
    for rid in sorted(by_id):
        if rid not in shapes:
            S.add("BRAIN_LABEL_ORPHAN", f"{regions.name} labels {rid}, the scene has no such Shape")
    vtot = ttot = 0
    for n, el in shapes.items():
        e = by_id.get(n)
        m = _shape_mesh(S, el)
        if e is None or m is None:
            continue
        sw = S.defs.get(e.get("switch", ""))
        if sw is None or not S.inside(el, sw):
            S.add("BRAIN_LABEL_MISSING", f"{n}: label entry names switch {e.get('switch')!r} which does not contain it")
        if variant == "lite":
            if (len(m.pts), m.ntri) != (e.get("lite_vertices"), e.get("lite_triangles")):
                S.add("BRAIN_COUNT_MISMATCH", f"{n}: {len(m.pts)} vertices {m.ntri} triangles; {regions.name} declares {e.get('lite_vertices')} and {e.get('lite_triangles')}")
            lo, hi = _bbox(m.pts)
            for i in range(3):
                if abs(lo[i] - e["bbox_min_mm"][i]) > BBOX_MM_TOL or abs(hi[i] - e["bbox_max_mm"][i]) > BBOX_MM_TOL:
                    S.add("BRAIN_COUNT_MISMATCH", f"{n}: bounding box differs from {regions.name} by more than {BBOX_MM_TOL} mm")
                    break
            vtot += len(m.pts)
            ttot += m.ntri
    if variant != "lite":
        S.skip("torso counts and bounding boxes", f"variant {variant!r}: {regions.name} carries lite counts only")
    S.m["labels"] = {"shapes": len(shapes), "entries": len(entries), "variant": variant, "lite_vertices": vtot, "lite_triangles": ttot}


# ------------------------------------------------------------------------------------------------ driver
def kind_of(path: Path, forced: str | None) -> str:
    if forced:
        if forced not in ("brain", "torso"):
            raise InstrumentError(f"--kind must be brain or torso, not {forced!r}")
        return forced
    n = path.name
    if n.startswith("brain_hero") and n.endswith(".x3d"):
        return "brain"
    if n.startswith("torso_ct") and n.endswith(".x3d"):
        return "torso"
    raise InstrumentError(f"cannot tell the scene kind of {n}: expected brain_hero*.x3d or torso_ct*.x3d (or --kind)")


def discover(path: Path, kind: str, regions: Path | None, sidecar: Path | None, builder: Path | None) -> tuple[Path | None, Path | None, Path | None]:
    here = path.parent
    if regions is None:
        for c in ([here.parent / "data" / "regions.json"] if kind == "brain" else [here.parent / "data" / "torso_regions.json", here / "torso_regions.json"]):
            if c.is_file():
                regions = c
                break
    if sidecar is None and kind == "brain":
        c = path.with_name(path.name + ".build.json")
        sidecar = c if c.is_file() else None
    if builder is None:
        c = here.parent / "tools" / ("build_brain_scene.py" if kind == "brain" else "build_torso_scene.py")
        builder = c if c.is_file() else None
    return regions, sidecar, builder


def check_file(path: Path | str, *, kind: str | None = None, strict: bool = False, regions: Path | None = None, sidecar: Path | None = None,
               builder: Path | None = None, page_texts: dict[str, str] | None = None) -> dict:
    """Run every check on one file. Returns the report; a violation never raises, it is listed (and the CLI exits 1)."""
    path = Path(path)
    if not path.is_file():
        raise InstrumentError(f"not a file: {path}")
    k = kind_of(path, kind)
    regions, sidecar, builder = discover(path, k, regions, sidecar, builder)
    S = Scene(path, k, strict)
    if S.root is not None:
        pipeline = [("defs", check_defs), ("textures", check_textures), ("geometry", check_geometry), ("visibility", check_visibility)]
        if k == "brain":
            pipeline += [("contract", check_contract_brain), ("alignment", check_alignment_brain), ("alignment-notice", check_alignment_notice),
                         ("notices", check_notices), ("units-provenance", check_units_provenance), ("attribution", check_attribution),
                         ("runtime-traps", lambda s: check_runtime_traps(s, page_texts or {})),
                         ("counts", lambda s: check_counts_brain(s, sidecar)), ("builder", lambda s: check_builder(s, builder)),
                         ("regions", lambda s: check_regions_brain(s, regions))]
        else:
            pipeline += [("contract", check_contract_torso), ("alignment", check_alignment_torso), ("notices", check_notices),
                         ("units-provenance", check_units_provenance), ("attribution", check_attribution),
                         ("runtime-traps", lambda s: check_runtime_traps(s, page_texts or {})),
                         ("builder", lambda s: check_builder(s, builder)), ("labels", lambda s: check_labels_torso(s, regions))]
        for name, fn in pipeline:
            fn(S)
            S.checks_run.append(name)
    return {"kind": k, "bytes": len(S.data), "sha256": S.sha, "status": "fail" if S.violations else "pass", "violations": S.violations,
            "checks_run": S.checks_run, "skipped": S.skipped, "measurements": S.m,
            "inputs": {"regions": regions.name if regions else None, "sidecar": sidecar.name if sidecar else None, "builder": builder.name if builder else None}}


def disclosure() -> dict:
    return {"alignment": "fsaverage and MNI152NLin2009cAsym are joined by a per-axis scale and shift of their cortex bounding boxes (a 3 to 5 percent "
                         "per-axis fit). Deep-structure containment shares that assumption (law 25): it catches a gross misplacement, it cannot show "
                         "that any position is anatomically right.",
            "scope": "geometry and text of the file only; nothing was rendered; not a registration; not a clinical statement"}


def limits() -> dict:
    return {"deep_tol_frac": DEEP_TOL_FRAC, "infra_descent_frac": INFRA_DESCENT_FRAC, "align_fit_max": ALIGN_FIT_MAX, "area_eps_mm2": AREA_EPS,
            "zero_area_frac_max": ZERO_AREA_FRAC_MAX, "audio_start_min": AUDIO_START_MIN, "env_face_px": ENV_FACE_PX,
            "brain_extent_mm": list(BRAIN_EXTENT_MM), "torso_width_mm": list(TORSO_WIDTH_MM), "region_tol_frac": REGION_TOL_FRAC}


def run(argv: list[str]) -> tuple[int, dict]:
    ap = argparse.ArgumentParser(prog="brain_scene_truth", description=__doc__.split("\n")[0])
    ap.add_argument("scenes", nargs="*")
    ap.add_argument("--glob", action="append", default=[], help="pattern relative to the current directory; must match something")
    ap.add_argument("--kind", choices=["brain", "torso"])
    ap.add_argument("--regions")
    ap.add_argument("--sidecar")
    ap.add_argument("--builder")
    ap.add_argument("--page", nargs="*", default=[], help="page files scanned for an OrderIndependentTransparency switch")
    ap.add_argument("--strict", action="store_true", help="a side input that is not found is a violation, not a skip")
    ap.add_argument("--list-codes", action="store_true")
    a = ap.parse_args(argv)
    if a.list_codes:
        return 0, {"schema": SCHEMA, "codes": CODES}
    files = [Path(p) for p in a.scenes]
    for pat in a.glob:
        hit = sorted(p.relative_to(Path.cwd()) for p in Path.cwd().glob(pat) if p.is_file())
        if not hit:
            raise InstrumentError(f"--glob {pat!r} matched nothing")
        files += hit
    if not files:
        raise InstrumentError("no scene given")
    pages = {}
    for p in a.page:
        try:
            pages[Path(p).name] = Path(p).read_text(encoding="utf-8")
        except OSError as e:
            raise InstrumentError(f"cannot read page file {p}: {e}") from None
    out: dict = {"schema": SCHEMA, "limits": limits(), "disclosure": disclosure(), "strict": a.strict, "page_files": sorted(pages), "files": {}}
    first = None
    for f in sorted(set(files), key=lambda p: str(p)):
        rep = check_file(f, kind=a.kind, strict=a.strict, regions=Path(a.regions) if a.regions else None,
                         sidecar=Path(a.sidecar) if a.sidecar else None, builder=Path(a.builder) if a.builder else None, page_texts=pages)
        out["files"][f.as_posix()] = rep
        if rep["violations"] and first is None:
            first = (f.as_posix(), rep["violations"][0])
    out["scenes"] = len(out["files"])
    if first is None:
        out["status"] = "pass"
        return 0, out
    out["status"] = "fail"
    out["rejected"] = first[1]["code"]
    out["detail"] = f"{first[0]}: {first[1]['detail']}"
    out["codes"] = sorted({v["code"] for r in out["files"].values() for v in r["violations"]})
    return 1, out


def main(argv: list[str] | None = None) -> int:
    try:
        code, out = run(list(sys.argv[1:] if argv is None else argv))
    except InstrumentError as e:
        print(json.dumps({"error": "INSTRUMENT_ERROR", "detail": str(e)[:600]}))
        return 2
    except SystemExit as e:  # argparse usage errors and --help
        return e.code if isinstance(e.code, int) else 2
    except (OSError, ValueError, KeyError) as e:
        print(json.dumps({"error": type(e).__name__, "detail": str(e)[:600]}))
        return 2
    except Exception as e:  # a bug in the reader is an instrument error (exit 2), never a violation and never a pass (law 19)
        print(json.dumps({"error": "INSTRUMENT_CRASH", "detail": f"{type(e).__name__}: {e}"[:600]}))
        return 2
    print(json.dumps(out, indent=1, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
