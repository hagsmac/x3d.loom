"""KANSEI X3D writer: deterministic text for X3D 4.0 scenes (standard library only).

Everything here returns strings. Numbers are formatted with fixed rules so a rebuild is
byte-identical: visual geometry uses short decimals, metadata uses the contract's fixed
decimals (see ktrack.py).
"""
from __future__ import annotations

import math
import re


# --------------------------------------------------------------------------------------------
# number formatting

def fnum(v: float, d: int = 3) -> str:
    """Short decimal: d places, trailing zeros removed, never '-0'."""
    s = f"{v:.{d}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", "", "-"):
        return "0"
    return s


def vec(*a: float, d: int = 3) -> str:
    return " ".join(fnum(x, d) for x in a)


def col(c, d: int = 3) -> str:
    return " ".join(fnum(min(1.0, max(0.0, x)), d) for x in c)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("'", "&apos;").replace("<", "&lt;").replace(">", "&gt;")


def mfstr(*items: str) -> str:
    return " ".join('"' + esc(x).replace('"', '\\"') + '"' for x in items)


# --------------------------------------------------------------------------------------------
# small vector maths

def v_add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def v_sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def v_mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def v_dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def v_cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def v_len(a): return math.sqrt(v_dot(a, a))


def v_norm(a):
    n = v_len(a)
    return (0.0, 1.0, 0.0) if n < 1e-12 else (a[0] / n, a[1] / n, a[2] / n)


def quat_axis_angle(q):
    w, x, y, z = q
    n = math.sqrt(x * x + y * y + z * z)
    if n < 1e-9:
        return (0.0, 1.0, 0.0, 0.0)
    ang = 2 * math.atan2(n, w)
    return (x / n, y / n, z / n, ang)


def quat_mul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def quat_from_axis(ax, ang):
    ax = v_norm(ax)
    s = math.sin(ang / 2)
    return (math.cos(ang / 2), ax[0] * s, ax[1] * s, ax[2] * s)


def look_rotation(eye, target):
    """SFRotation that turns a default Viewpoint (looking down -Z, +Y up) to look from eye at target."""
    d = v_norm(v_sub(target, eye))
    yaw = math.atan2(-d[0], -d[2])               # about +Y
    pitch = math.asin(max(-1.0, min(1.0, d[1])))  # about local +X
    q = quat_mul(quat_from_axis((0, 1, 0), yaw), quat_from_axis((1, 0, 0), pitch))
    return quat_axis_angle(q)


def rot_str(r) -> str:
    return f"{fnum(r[0], 4)} {fnum(r[1], 4)} {fnum(r[2], 4)} {fnum(r[3], 4)}"


# --------------------------------------------------------------------------------------------
# deterministic randomness (geometry placement): xorshift32, the same on every machine

class RNG:
    def __init__(self, seed: int):
        self.s = (seed * 2654435761 & 0xFFFFFFFF) or 1

    def u(self) -> float:
        s = self.s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self.s = s
        return s / 4294967296.0

    def r(self, a: float, b: float) -> float:
        return a + (b - a) * self.u()

    def i(self, n: int) -> int:
        return int(self.u() * n) % n

    def pick(self, seq):
        return seq[self.i(len(seq))]


# --------------------------------------------------------------------------------------------
# meshes

class Mesh:
    """Triangle mesh accumulator. Emits IndexedTriangleSet (with normals when given) or
    IndexedFaceSet (creaseAngle, browser normals). Coordinates at 1 cm, normals at 0.01."""

    def __init__(self, normals: bool = True, uv: bool = True, colors: bool = False):
        self.p: list = []
        self.n: list | None = []          # always kept: it orients the winding
        self.write_normals = normals
        self.t: list | None = [] if uv else None
        self.c: list | None = [] if colors else None
        self.idx: list = []

    def __len__(self):
        return len(self.p)

    def v(self, p, n=None, t=None, c=None) -> int:
        self.p.append(p)
        if self.n is not None:
            self.n.append(n if n is not None else (0.0, 1.0, 0.0))
        if self.t is not None:
            self.t.append(t if t is not None else (0.0, 0.0))
        if self.c is not None:
            self.c.append(c if c is not None else (1.0, 1.0, 1.0))
        return len(self.p) - 1

    def _facing(self, a, b, c) -> bool:
        """True when a b c winds counter-clockwise about the stored vertex normals."""
        if self.n is None:
            return True
        pa, pb, pc = self.p[a], self.p[b], self.p[c]
        fn = v_cross(v_sub(pb, pa), v_sub(pc, pa))
        nn = v_add(v_add(self.n[a], self.n[b]), self.n[c])
        return v_dot(fn, nn) >= 0

    def tri(self, a, b, c):
        if self._facing(a, b, c):
            self.idx.extend((a, b, c))
        else:
            self.idx.extend((a, c, b))

    def quad(self, a, b, c, d):
        """Two triangles; winding follows the stored normals (counter-clockwise from the front)."""
        if self._facing(a, b, c) if v_len(v_cross(v_sub(self.p[b], self.p[a]), v_sub(self.p[c], self.p[a]))) > 1e-12 else self._facing(a, c, d):
            self.idx.extend((a, b, c, a, c, d))
        else:
            self.idx.extend((a, c, b, a, d, c))

    def empty(self) -> bool:
        return not self.idx

    def merge(self, other: "Mesh"):
        base = len(self.p)
        self.p.extend(other.p)
        if self.n is not None:
            self.n.extend(other.n if other.n is not None else [(0, 1, 0)] * len(other.p))
        if self.t is not None:
            self.t.extend(other.t if other.t is not None else [(0, 0)] * len(other.p))
        if self.c is not None:
            self.c.extend(other.c if other.c is not None else [(1, 1, 1)] * len(other.p))
        self.idx.extend(i + base for i in other.idx)

    # ---- primitives (all with flat-shaded split vertices) ----
    def box(self, center, size, yaw: float = 0.0, uvscale: float = 1.0, color=None, pitch: float = 0.0, roll: float = 0.0):
        cx, cy, cz = center
        hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
        cyw, syw = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cr, sr = math.cos(roll), math.sin(roll)

        def tf(x, y, z):
            # roll about Z, pitch about X, then yaw about Y
            x, y = x * cr - y * sr, x * sr + y * cr
            y, z = y * cp - z * sp, y * sp + z * cp
            return (cx + x * cyw + z * syw, cy + y, cz - x * syw + z * cyw)

        faces = [((1, 0, 0), [(hx, -hy, hz), (hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz)], (2 * hz, 2 * hy)),
                 ((-1, 0, 0), [(-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz)], (2 * hz, 2 * hy)),
                 ((0, 1, 0), [(-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz), (-hx, hy, -hz)], (2 * hx, 2 * hz)),
                 ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)], (2 * hx, 2 * hz)),
                 ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)], (2 * hx, 2 * hy)),
                 ((0, 0, -1), [(hx, -hy, -hz), (-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz)], (2 * hx, 2 * hy))]
        for nrm, pts, (su, sv) in faces:
            n = v_sub(tf(*nrm), tf(0, 0, 0))
            ids = []
            for k, q in enumerate(pts):
                uv = ((0, 0), (su * uvscale, 0), (su * uvscale, sv * uvscale), (0, sv * uvscale))[k]
                ids.append(self.v(tf(*q), v_norm(n), uv, color))
            self.quad(*ids)

    def lathe(self, profile, segs: int, center=(0, 0, 0), axis: str = "y", uv_v_scale: float = 1.0,
              color=None, a0: float = 0.0, a1: float = 2 * math.pi, smooth: bool = True):
        """Revolve profile [(r, h), ...] about an axis. Normals from the profile (smooth)."""
        cx, cy, cz = center
        rows = []
        n_prof = len(profile)
        # profile normals in (r, h) space
        pn = []
        for i in range(n_prof):
            a = profile[max(0, i - 1)]
            b = profile[min(n_prof - 1, i + 1)]
            dr, dh = b[0] - a[0], b[1] - a[1]
            ln = math.hypot(dr, dh) or 1.0
            pn.append((dh / ln, -dr / ln))
        for s in range(segs + 1):
            a = a0 + (a1 - a0) * s / segs
            ca, sa = math.cos(a), math.sin(a)
            row = []
            for i, (r, h) in enumerate(profile):
                nr, nh = pn[i]
                if axis == "y":
                    p = (cx + r * ca, cy + h, cz + r * sa)
                    n = (nr * ca, nh, nr * sa)
                elif axis == "x":
                    p = (cx + h, cy + r * ca, cz + r * sa)
                    n = (nh, nr * ca, nr * sa)
                else:
                    p = (cx + r * ca, cy + r * sa, cz + h)
                    n = (nr * ca, nr * sa, nh)
                row.append(self.v(p, n, (s / segs, i / max(1, n_prof - 1) * uv_v_scale), color))
            rows.append(row)
        for s in range(segs):
            for i in range(n_prof - 1):
                self.quad(rows[s][i], rows[s + 1][i], rows[s + 1][i + 1], rows[s][i + 1])

    # ---- output ----
    def its(self, solid: bool = True, dp: int = 2, dn: int = 2, dt: int = 3, ccw: bool = True) -> str:
        pts = " ".join(vec(*q, d=dp) for q in self.p)
        idx = " ".join(map(str, self.idx))
        parts = [f"<IndexedTriangleSet solid='{'true' if solid else 'false'}'"
                 + ("" if ccw else " ccw='false'")
                 + (" normalPerVertex='true'" if self.write_normals else "")
                 + f" index='{idx}'>",
                 f"<Coordinate point='{pts}'/>"]
        if self.write_normals:
            parts.append("<Normal vector='" + " ".join(vec(*v_norm(q), d=dn) for q in self.n) + "'/>")
        if self.t is not None:
            parts.append("<TextureCoordinate point='" + " ".join(vec(*q, d=dt) for q in self.t) + "'/>")
        if self.c is not None:
            parts.append("<Color color='" + " ".join(col(q, 2) for q in self.c) + "'/>")
        parts.append("</IndexedTriangleSet>")
        return "".join(parts)

    def ifs(self, crease: float = 0.6, solid: bool = True, dp: int = 3, dt: int = 3) -> str:
        """IndexedFaceSet of triangles; the browser computes normals with creaseAngle."""
        pts = " ".join(vec(*q, d=dp) for q in self.p)
        tris = self.idx
        ci = " ".join(f"{tris[k]} {tris[k + 1]} {tris[k + 2]} -1" for k in range(0, len(tris), 3))
        parts = [f"<IndexedFaceSet solid='{'true' if solid else 'false'}' creaseAngle='{fnum(crease, 3)}' coordIndex='{ci}'"
                 + (" colorPerVertex='true'" if self.c is not None else "") + ">",
                 f"<Coordinate point='{pts}'/>"]
        if self.t is not None:
            parts.append("<TextureCoordinate point='" + " ".join(vec(*q, d=dt) for q in self.t) + "'/>")
        if self.c is not None:
            parts.append("<Color color='" + " ".join(col(q, 2) for q in self.c) + "'/>")
        parts.append("</IndexedFaceSet>")
        return "".join(parts)


# --------------------------------------------------------------------------------------------
# appearances (DEF on first use, USE afterwards)

class Looks:
    """Registry of named PhysicalMaterial appearances. look(name) returns the Appearance XML,
    DEF'd the first time and USE'd after, so each material is written once per file."""

    def __init__(self, tex_prefixes: tuple[str, ...]):
        self.defs: dict[str, dict] = {}
        self.used: set[str] = set()
        self.tex_prefixes = tex_prefixes
        self.tex_used: set[str] = set()

    def add(self, name: str, **kw):
        self.defs[name] = kw

    def url(self, png: str) -> str:
        return mfstr(*[p + png for p in self.tex_prefixes])

    def _tex(self, png: str, field: str, props: str | None) -> str:
        key = f"T_{png.replace('.png', '').replace('-', '_')}"
        if key in self.tex_used:
            return f"<ImageTexture USE='{key}' containerField='{field}'/>"
        self.tex_used.add(key)
        tp = ""
        if props:
            tp = (f"<TextureProperties anisotropicDegree='{props}' generateMipMaps='true' minificationFilter='AVG_PIXEL_AVG_MIPMAP'"
                  f" magnificationFilter='AVG_PIXEL' boundaryModeS='REPEAT' boundaryModeT='REPEAT'/>")
        return f"<ImageTexture DEF='{key}' containerField='{field}' url='{self.url(png)}'>{tp}</ImageTexture>"

    def look(self, name: str) -> str:
        if name in self.used:
            return f"<Appearance USE='A_{name}'/>"
        self.used.add(name)
        k = self.defs[name]
        attrs = [f"baseColor='{col(k.get('base', (0.8, 0.8, 0.8)))}'",
                 f"metallic='{fnum(k.get('metal', 0.0), 3)}'", f"roughness='{fnum(k.get('rough', 0.8), 3)}'"]
        if k.get("emit"):
            attrs.append(f"emissiveColor='{col(k['emit'])}'")
        if k.get("transp"):
            attrs.append(f"transparency='{fnum(k['transp'], 3)}'")
        if k.get("nscale") is not None:
            attrs.append(f"normalScale='{fnum(k['nscale'], 3)}'")
        if k.get("occ") is not None:
            attrs.append(f"occlusionStrength='{fnum(k['occ'], 3)}'")
        mdef = f" DEF='{k['mdef']}'" if k.get("mdef") else ""
        inner = []
        aniso = k.get("aniso")
        if k.get("tex"):
            inner.append(self._tex(k["tex"], "baseTexture", aniso))
        if k.get("emtex"):
            inner.append(self._tex(k["emtex"], "emissiveTexture", aniso))
        if k.get("ntex"):
            inner.append(self._tex(k["ntex"], "normalTexture", aniso))
        if k.get("mrtex"):
            inner.append(self._tex(k["mrtex"], "metallicRoughnessTexture", aniso))
        mat = f"<PhysicalMaterial{mdef} " + " ".join(attrs) + (">" + "".join(inner) + "</PhysicalMaterial>" if inner else "/>")
        extra = ""
        if k.get("tt"):
            sx, sy = k["tt"]
            extra = f"<TextureTransform scale='{fnum(sx, 4)} {fnum(sy, 4)}'/>"
        amode = ""
        if k.get("alpha") == "mask":
            amode = f" alphaMode='MASK' alphaCutoff='{fnum(k.get('cutoff', 0.5), 2)}'"
        elif k.get("alpha") == "blend" or k.get("transp"):
            amode = " alphaMode='BLEND'"
        return f"<Appearance DEF='A_{name}'{amode}>{mat}{extra}</Appearance>"


def shape(looks: Looks, look: str, geom: str, shadow: bool = False, def_name: str | None = None) -> str:
    d = f" DEF='{def_name}'" if def_name else ""
    return f"<Shape{d} castShadow='{'true' if shadow else 'false'}'>{looks.look(look)}{geom}</Shape>"


_APP_DEF = re.compile(r"<Appearance DEF='([^']+)'[^>]*>.*?</Appearance>", re.S)
_TEX_DEF = re.compile(r"<ImageTexture DEF='([^']+)' containerField='([^']+)'.*?</ImageTexture>", re.S)


def fix_def_order(body: str) -> str:
    """Shapes are generated in a different order from the one they are written in, so a USE can land
    before its DEF. Swap each such pair so the first occurrence in document order is the DEF
    (appearances first, then textures, keeping each position's containerField)."""
    for _ in range(500):
        moved = False
        for m in list(_APP_DEF.finditer(body)):
            use = f"<Appearance USE='{m.group(1)}'/>"
            u = body.find(use)
            if 0 <= u < m.start():
                full = m.group(0)
                body = body[:u] + full + body[u + len(use):m.start()] + use + body[m.end():]
                moved = True
                break
        if moved:
            continue
        for m in list(_TEX_DEF.finditer(body)):
            key, field = m.group(1), m.group(2)
            um = re.search(rf"<ImageTexture USE='{re.escape(key)}' containerField='([^']+)'/>", body)
            if um and um.start() < m.start():
                ufield = um.group(1)
                full = m.group(0).replace(f"containerField='{field}'", f"containerField='{ufield}'", 1)
                use = f"<ImageTexture USE='{key}' containerField='{field}'/>"
                body = body[:um.start()] + full + body[um.end():m.start()] + use + body[m.end():]
                moved = True
                break
        if not moved:
            break
    return body


def x3d_doc(title: str, description: str, components: list[tuple[str, int]], body: str, generator: str) -> str:
    body = fix_def_order(body)
    comps = "".join(f"<component name='{n}' level='{l}'/>\n" for n, l in components)
    return ("<?xml version='1.0' encoding='UTF-8'?>\n"
            "<X3D profile='Immersive' version='4.0' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' "
            "xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.0.xsd'>\n"
            "<head>\n" + comps +
            f"<meta name='title' content='{esc(title)}'/>\n"
            f"<meta name='description' content='{esc(description)}'/>\n"
            f"<meta name='generator' content='{esc(generator)}'/>\n"
            "<meta name='license' content='MIT'/>\n"
            "</head>\n<Scene>\n" + body + "\n</Scene>\n</X3D>\n")
