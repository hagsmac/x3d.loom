"""Small X3D 4.0 writer for x3d.platformer levels (standard library only, deterministic bytes).

Conventions the game engine reads (engine/x3d.js):
  WorldInfo > MetadataSet name='nib:level'                     level parameters
  RigidBodyCollection > RigidBody + MetadataSet 'nib:body'     every collider
  RigidBodyCollection > SingleAxisHingeJoint (body1/body2 USE)  revolute joints
  Transform + MetadataSet 'nib:entity'                         pickups, springs, hazards ...
  PositionInterpolator DEF referenced by nib:body 'path'       moving platform paths
The collection is declared enabled='false': the browser draws the level, our fixed-step engine
plays it, so the X3D file is a standard, validated contract for both.
"""
from __future__ import annotations

import math


def f(v: float) -> str:
    if abs(v) < 5e-5:
        return "0"
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def vec(*a: float) -> str:
    return " ".join(f(x) for x in a)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("'", "&apos;").replace("<", "&lt;").replace(">", "&gt;")


def mfstr(*items: str) -> str:
    return " ".join('"' + esc(x).replace('"', '\\"') + '"' for x in items)


def metaset(set_name: str, **kv) -> str:
    out = [f"<MetadataSet name='{set_name}' containerField='metadata'>"]
    for k in sorted(kv):
        v = kv[k]
        if v is None:
            continue
        if isinstance(v, bool):
            out.append(f"<MetadataBoolean name='{k}' value='{'true' if v else 'false'}' containerField='value'/>")
        elif isinstance(v, str):
            out.append(f"<MetadataString name='{k}' value='{mfstr(v)}' containerField='value'/>")
        elif isinstance(v, (list, tuple)):
            out.append(f"<MetadataDouble name='{k}' value='{vec(*v)}' containerField='value'/>")
        else:
            out.append(f"<MetadataDouble name='{k}' value='{f(v)}' containerField='value'/>")
    out.append("</MetadataSet>")
    return "".join(out)


class RNG:
    """xorshift32: the same numbers on every machine (law 4: declare every input, seeds included)."""

    def __init__(self, seed: int):
        self.s = (seed & 0xFFFFFFFF) or 1

    def u(self) -> float:
        s = self.s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self.s = s
        return s / 4294967296.0

    def r(self, a: float, b: float) -> float:
        return a + (b - a) * self.u()

    def pick(self, seq):
        return seq[int(self.u() * len(seq)) % len(seq)]


def material(diffuse, emissive=(0, 0, 0), spec=(0.12, 0.12, 0.12), shin=0.2, transp=0.0, amb=0.25) -> str:
    t = f" transparency='{f(transp)}'" if transp else ""
    return (f"<Material diffuseColor='{vec(*diffuse)}' emissiveColor='{vec(*emissive)}' specularColor='{vec(*spec)}' "
            f"shininess='{f(shin)}' ambientIntensity='{f(amb)}'{t}/>")


def torus_extrusion(R: float, r: float, seg: int = 20, cs: int = 8) -> str:
    spine = [(R * math.cos(2 * math.pi * i / seg), R * math.sin(2 * math.pi * i / seg), 0) for i in range(seg + 1)]
    cross = [(r * math.cos(2 * math.pi * i / cs), r * math.sin(2 * math.pi * i / cs)) for i in range(cs + 1)]
    sp = " ".join(vec(*p) for p in spine)
    cr = " ".join(vec(*p) for p in cross)
    return f"<Extrusion spine='{sp}' crossSection='{cr}' creaseAngle='3.1416' beginCap='false' endCap='false' solid='true'/>"


def helix_extrusion(R: float, r: float, turns: float, height: float, seg_per_turn: int = 14, cs: int = 6) -> str:
    n = int(turns * seg_per_turn)
    spine = [(R * math.cos(2 * math.pi * turns * i / n), height * i / n, R * math.sin(2 * math.pi * turns * i / n)) for i in range(n + 1)]
    cross = [(r * math.cos(2 * math.pi * i / cs), r * math.sin(2 * math.pi * i / cs)) for i in range(cs + 1)]
    sp = " ".join(vec(*p) for p in spine)
    cr = " ".join(vec(*p) for p in cross)
    return f"<Extrusion spine='{sp}' crossSection='{cr}' creaseAngle='3.1416' solid='true'/>"


def gear_shape_children(radius: float, thick: float, teeth: int, app_use: str, hole_app: str | None = None) -> str:
    """A gear facing +Z built from a disc and teeth (boxes): Cylinder axis is turned to Z."""
    out = [f"<Transform rotation='1 0 0 1.5708'><Shape><Appearance USE='{app_use}'/><Cylinder radius='{f(radius)}' height='{f(thick)}'/></Shape></Transform>"]
    tw = 2 * math.pi * radius / teeth * 0.5
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        out.append(f"<Transform translation='{vec(math.cos(a) * radius, math.sin(a) * radius, 0)}' rotation='0 0 1 {f(a)}'>"
                   f"<Shape><Appearance USE='{app_use}'/><Box size='{vec(radius * 0.36, tw, thick * 0.9)}'/></Shape></Transform>")
    if hole_app:
        out.append(f"<Transform rotation='1 0 0 1.5708'><Shape><Appearance USE='{hole_app}'/><Cylinder radius='{f(radius * 0.32)}' height='{f(thick * 1.15)}'/></Shape></Transform>")
    return "".join(out)
