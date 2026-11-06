"""KANSEI cars and the showroom (CONTRACT.md section 5).

Every car is generated from a short table of body stations. The lower body is one loft with real
wheel arches cut into it (dark wheel wells, rolled lips); the greenhouse is a second loft split
into glass, pillars and roof. Details: lights carrying the contract DEFs (HeadGlow, BrakeGlow,
ReverseGlow), mirrors, splitter, diffuser, wing or ducktail, exhaust tips, number plates, livery
stripes, and wheels with tyre sidewalls, multi-spoke rims, discs and calipers.

Dimensions (wheelbase, CG split, track, wheel radius, length, width) are the numbers in
engine/cars.js, so the drawn hubs sit exactly where the simulation puts its contact points.
Car frame: +Z forward, +X left, +Y up, wheels on y = 0, origin under the centre of mass.
"""
from __future__ import annotations

import math

from kx3d import Looks, fnum, vec, col, esc, x3d_doc, shape

PI = math.pi
CAR_TEX = ("../textures/", "textures/")


# --------------------------------------------------------------------------------------------
# small helpers

def pchip(xs, ys):
    """Monotone cubic interpolant (Fritsch-Carlson), clamped outside the keys."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def f(x):
        if x <= xs[0]:
            return ys[0]
        if x >= xs[-1]:
            return ys[-1]
        lo = n - 2
        for i in range(n - 1):
            if x < xs[i + 1]:
                lo = i
                break
        t = (x - xs[lo]) / h[lo]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[lo] + (t3 - 2 * t2 + t) * h[lo] * m[lo]
                + (-2 * t3 + 3 * t2) * ys[lo + 1] + (t3 - t2) * h[lo] * m[lo + 1])
    return f


def chaikin(pts, iters=1):
    for _ in range(iters):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        out.append(pts[-1])
        pts = out
    return pts


def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


class PM:
    """Polygon mesh written as an IndexedFaceSet (the browser makes normals from creaseAngle)."""

    def __init__(self, uv: bool = False):
        self.p: list = []
        self.t: list | None = [] if uv else None
        self.f: list = []

    def v(self, p, t=None) -> int:
        self.p.append((float(p[0]), float(p[1]), float(p[2])))
        if self.t is not None:
            self.t.append(t if t is not None else (0.0, 0.0))
        return len(self.p) - 1

    def newell(self, ids):
        nx = ny = nz = 0.0
        for k in range(len(ids)):
            a, b = self.p[ids[k]], self.p[ids[(k + 1) % len(ids)]]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        return (nx, ny, nz)

    def face(self, ids, toward=None):
        """Add a polygon; with `toward` (a direction) the winding is flipped to face it."""
        ids = list(ids)
        if toward is not None and dot(self.newell(ids), toward) < 0:
            ids.reverse()
        self.f.append(ids)

    def fan(self, ids, toward):
        """Triangle fan about the centroid (safe for the slightly concave end caps)."""
        c = tuple(sum(self.p[i][k] for i in ids) / len(ids) for k in range(3))
        ci = self.v(c, (0.5, 0.5) if self.t is not None else None)
        n = len(ids)
        for k in range(n):
            self.face([ci, ids[k], ids[(k + 1) % n]], toward)

    def face_out(self, ids, centre):
        c = [sum(self.p[i][k] for i in ids) / len(ids) for k in range(3)]
        self.face(ids, sub(c, centre))

    def hexa(self, c8):
        """Convex hexahedron from 8 corners: 0-3 one end, 4-7 the other, same order."""
        ids = [self.v(q) for q in c8]
        cen = tuple(sum(q[k] for q in c8) / 8 for k in range(3))
        for f in ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.face_out([ids[i] for i in f], cen)

    def box(self, c, s):
        x0, x1 = c[0] - s[0] / 2, c[0] + s[0] / 2
        y0, y1 = c[1] - s[1] / 2, c[1] + s[1] / 2
        z0, z1 = c[2] - s[2] / 2, c[2] + s[2] / 2
        self.hexa([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                   (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])

    def disc(self, centre, r, normal_axis, segs=20, sign=1.0, uv=False):
        """Flat round polygon facing +/- axis ('x', 'y' or 'z')."""
        cx, cy, cz = centre
        ids = []
        for s in range(segs):
            a = 2 * PI * s / segs
            ca, sa = math.cos(a) * r, math.sin(a) * r
            if normal_axis == "z":
                p = (cx + ca, cy + sa, cz)
            elif normal_axis == "x":
                p = (cx, cy + sa, cz + ca)
            else:
                p = (cx + ca, cy, cz + sa)
            ids.append(self.v(p, (0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)) if uv else None))
        d = {"x": (sign, 0, 0), "y": (0, sign, 0), "z": (0, 0, sign)}[normal_axis]
        self.face(ids, d)

    def empty(self) -> bool:
        return not self.f

    def ifs(self, crease: float = 0.5, solid: bool = True, dp: int = 3, dt: int = 3) -> str:
        pts = " ".join(vec(*q, d=dp) for q in self.p)
        ci = " ".join(" ".join(map(str, f)) + " -1" for f in self.f)
        out = (f"<IndexedFaceSet solid='{'true' if solid else 'false'}' creaseAngle='{fnum(crease, 2)}' coordIndex='{ci}'>"
               f"<Coordinate point='{pts}'/>")
        if self.t is not None:
            out += "<TextureCoordinate point='" + " ".join(vec(*q, d=dt) for q in self.t) + "'/>"
        return out + "</IndexedFaceSet>"


def lathe_x(m: PM, prof, segs, a0=0.0, a1=2 * PI, uvf=None, mirror=False, cap_ends=False):
    """Revolve [(r, h)] about the X axis (h along +X). The visible side of the surface is on
    the left of travel in the (h, r) plane (r up): e.g. a tread walked toward +h faces out.
    uvf(s_frac, i, r, h) -> (u, v). mirror=True negates h (right-hand side parts)."""
    sg = -1.0 if mirror else 1.0
    rows = []
    for s in range(segs + 1):
        a = a0 + (a1 - a0) * s / segs
        ca, sa = math.cos(a), math.sin(a)
        rows.append([m.v((sg * h, r * ca, r * sa), uvf(s / segs, i, r, h) if uvf else None) for i, (r, h) in enumerate(prof)])
    for s in range(segs):
        a = a0 + (a1 - a0) * (s + 0.5) / segs
        ca, sa = math.cos(a), math.sin(a)
        for i in range(len(prof) - 1):
            (r0, h0), (r1, h1) = prof[i], prof[i + 1]
            # outward normal in (h, r): the travel direction (dh, dr) turned counter-clockwise
            dh, dr = h1 - h0, r1 - r0
            nh, nr = -dr, dh
            n = (sg * nh, nr * ca, nr * sa)
            m.face([rows[s][i], rows[s + 1][i], rows[s + 1][i + 1], rows[s][i + 1]], n)
    if cap_ends and a1 - a0 < 2 * PI - 1e-6:
        for s, a in ((0, a0), (segs, a1)):
            ids = rows[s][:-1] if prof[0] == prof[-1] else rows[s]
            t = (0.0, -math.sin(a), math.cos(a))      # angular direction at a
            m.face(ids, t if s == segs else (0.0, math.sin(a), -math.cos(a)))
    return rows


# --------------------------------------------------------------------------------------------
# the four cars (original designs). Body keys: u (0 = rear bumper, 1 = front bumper),
# yb underside, ys shoulder (fender top), yc centre top, wb max half-width, wsh shoulder
# half-width, wt top-edge half-width. Greenhouse keys: u, roof-line height, roof half-width.

CARS = [
    dict(id="koi", name="KOI", L=2.38, cgFront=0.52, cgH=0.46, tf=1.44, tr=1.44, length=3.98, width=1.70, R=0.30,
         tw=0.205, rim=0.215, fo=0.82, sill=0.10, rcf=0.30, rcr=0.26, arch_gap=0.035,
         keys=[(0.000, 0.30, 0.70, 0.72, 0.80, 0.74, 0.62), (0.04, 0.22, 0.76, 0.79, 0.83, 0.78, 0.68),
               (0.12, 0.15, 0.79, 0.81, 0.85, 0.80, 0.70), (0.20, 0.13, 0.80, 0.81, 0.85, 0.80, 0.70),
               (0.30, 0.13, 0.79, 0.80, 0.83, 0.79, 0.70), (0.45, 0.13, 0.78, 0.79, 0.82, 0.78, 0.70),
               (0.62, 0.13, 0.77, 0.80, 0.83, 0.78, 0.70), (0.78, 0.14, 0.74, 0.72, 0.85, 0.77, 0.68),
               (0.92, 0.18, 0.66, 0.64, 0.82, 0.74, 0.62), (1.000, 0.24, 0.58, 0.58, 0.76, 0.66, 0.52)],
         gh=[(0.17, 0.81, 0.55), (0.25, 0.99, 0.56), (0.33, 1.16, 0.56), (0.41, 1.22, 0.57), (0.47, 1.22, 0.57),
             (0.55, 1.10, 0.59), (0.62, 0.80, 0.62)],
         ws1=0.47, rf1=0.33, bpillar=0.44, quarter=False, crown=0.025, bulge=0.0,
         paint=(0.93, 0.36, 0.07), stripe=(0.96, 0.95, 0.92), rimcol=(0.78, 0.79, 0.80), caliper=(0.80, 0.08, 0.06),
         stripes=[("top", 0.07, 0.16, True)], side=None,
         head="popup", tail="round", wing="lip", exhaust=[(-0.36, 0.20)], tip_r=0.042, spokes=("mesh", 8),
         plate="KANSEI|K-01", extras=[]),
    dict(id="ronin", name="RONIN", L=2.56, cgFront=0.53, cgH=0.48, tf=1.52, tr=1.53, length=4.42, width=1.79, R=0.32,
         tw=0.245, rim=0.229, fo=0.95, sill=0.10, rcf=0.30, rcr=0.24, arch_gap=0.035,
         keys=[(0.000, 0.32, 0.80, 0.82, 0.84, 0.78, 0.66), (0.04, 0.22, 0.86, 0.89, 0.88, 0.84, 0.72),
               (0.13, 0.14, 0.86, 0.90, 0.895, 0.85, 0.72), (0.21, 0.12, 0.86, 0.90, 0.895, 0.85, 0.72),
               (0.30, 0.12, 0.85, 0.88, 0.86, 0.83, 0.72), (0.42, 0.12, 0.82, 0.83, 0.84, 0.81, 0.72),
               (0.60, 0.12, 0.80, 0.84, 0.85, 0.81, 0.72), (0.70, 0.12, 0.80, 0.80, 0.885, 0.82, 0.71),
               (0.785, 0.13, 0.78, 0.76, 0.895, 0.83, 0.70), (0.90, 0.17, 0.70, 0.68, 0.87, 0.80, 0.64),
               (1.000, 0.20, 0.60, 0.60, 0.80, 0.70, 0.54)],
         gh=[(0.19, 0.89, 0.60), (0.27, 1.04, 0.60), (0.36, 1.22, 0.60), (0.44, 1.28, 0.61), (0.50, 1.27, 0.61),
             (0.57, 1.10, 0.63), (0.635, 0.84, 0.66)],
         ws1=0.50, rf1=0.36, bpillar=0.45, quarter=True, crown=0.025, bulge=0.0,
         paint=(0.90, 0.90, 0.88), stripe=(0.78, 0.04, 0.06), rimcol=(0.20, 0.21, 0.23), caliper=(0.95, 0.72, 0.05),
         stripes=[("top", -0.06, 0.06, False)], side=(0.40, 0.47),
         head="slim", tail="bars", wing="gt", exhaust=[(-0.30, 0.22), (-0.42, 0.22)], tip_r=0.045, spokes=("twin", 6),
         plate="KANSEI|R-02", extras=["canards", "skirts", "vents", "tow"]),
    dict(id="tempest", name="TEMPEST", L=2.62, cgFront=0.56, cgH=0.47, tf=1.57, tr=1.57, length=4.52, width=1.86, R=0.33,
         tw=0.235, rim=0.229, fo=0.98, sill=0.12, rcf=0.28, rcr=0.18, arch_gap=0.05,
         keys=[(0.000, 0.36, 0.86, 0.88, 0.86, 0.82, 0.72), (0.03, 0.26, 0.90, 0.92, 0.90, 0.86, 0.76),
               (0.13, 0.18, 0.91, 0.93, 0.93, 0.88, 0.76), (0.20, 0.16, 0.91, 0.93, 0.93, 0.88, 0.76),
               (0.30, 0.16, 0.90, 0.91, 0.90, 0.87, 0.76), (0.45, 0.16, 0.88, 0.89, 0.89, 0.86, 0.76),
               (0.62, 0.16, 0.88, 0.91, 0.89, 0.86, 0.76), (0.70, 0.16, 0.88, 0.89, 0.92, 0.87, 0.75),
               (0.78, 0.17, 0.85, 0.84, 0.93, 0.87, 0.74), (0.90, 0.21, 0.78, 0.76, 0.90, 0.84, 0.68),
               (1.000, 0.27, 0.68, 0.68, 0.83, 0.75, 0.58)],
         gh=[(0.03, 0.93, 0.62), (0.07, 1.18, 0.64), (0.13, 1.39, 0.66), (0.30, 1.43, 0.67), (0.48, 1.42, 0.67),
             (0.56, 1.24, 0.69), (0.62, 0.92, 0.72)],
         ws1=0.49, rf1=0.13, bpillar=0.33, quarter=True, crown=0.03, bulge=0.0,
         paint=(0.05, 0.20, 0.60), stripe=(0.98, 0.80, 0.08), rimcol=(0.80, 0.62, 0.22), caliper=(0.85, 0.10, 0.08),
         stripes=[], side=(0.34, 0.50),
         head="square", tail="vertical", wing="roof", exhaust=[(0.0, 0.24)], tip_r=0.058, spokes=("five", 5),
         plate="KANSEI|T-03", extras=["rally", "scoop", "flaps", "tow"]),
    dict(id="banshee", name="BANSHEE", L=2.60, cgFront=0.47, cgH=0.46, tf=1.58, tr=1.60, length=4.62, width=1.92, R=0.34,
         tw=0.265, rim=0.241, fo=1.06, sill=0.10, rcf=0.30, rcr=0.26, arch_gap=0.035,
         keys=[(0.000, 0.30, 0.90, 0.94, 0.86, 0.80, 0.70), (0.04, 0.22, 0.88, 0.90, 0.92, 0.86, 0.74),
               (0.14, 0.13, 0.88, 0.88, 0.96, 0.89, 0.74), (0.21, 0.12, 0.88, 0.87, 0.96, 0.89, 0.74),
               (0.30, 0.12, 0.86, 0.86, 0.93, 0.87, 0.74), (0.42, 0.12, 0.83, 0.85, 0.89, 0.85, 0.74),
               (0.50, 0.12, 0.83, 0.88, 0.89, 0.85, 0.74), (0.62, 0.12, 0.82, 0.86, 0.91, 0.86, 0.74),
               (0.77, 0.13, 0.79, 0.80, 0.93, 0.86, 0.72), (0.90, 0.17, 0.72, 0.72, 0.90, 0.82, 0.66),
               (1.000, 0.22, 0.62, 0.62, 0.84, 0.72, 0.56)],
         gh=[(0.15, 0.89, 0.56), (0.21, 1.06, 0.57), (0.28, 1.22, 0.58), (0.34, 1.27, 0.58), (0.40, 1.25, 0.59),
             (0.45, 1.10, 0.62), (0.50, 0.88, 0.66)],
         ws1=0.40, rf1=0.28, bpillar=0.36, quarter=False, crown=0.02, bulge=0.035,
         paint=(0.46, 0.03, 0.05), stripe=(0.06, 0.06, 0.07), rimcol=(0.10, 0.10, 0.11), caliper=(0.85, 0.10, 0.08),
         stripes=[("top", 0.10, 0.26, False)], side=None,
         head="slim", tail="fullbar", wing="ducktail", exhaust=[(0.40, 0.21), (0.53, 0.21), (-0.40, 0.21), (-0.53, 0.21)],
         tip_r=0.04, spokes=("ten", 10), plate="KANSEI|B-04", extras=["skirts", "vents"]),
]


def plate_row(cid: str) -> int:
    return [c["id"] for c in CARS].index(cid)


# --------------------------------------------------------------------------------------------
# geometry of one car

class Body:
    def __init__(self, c):
        self.c = c
        L = c["L"]
        self.b = c["cgFront"] * L          # CG to rear axle (engine/car.js)
        self.a = L - self.b                # CG to front axle
        self.zf = self.a + c["fo"]
        self.zr = self.zf - c["length"]
        ks = c["keys"]
        us = [k[0] for k in ks]
        self.f = {name: pchip(us, [k[i] for k in ks]) for i, name in enumerate(("yb", "ys", "yc", "wb", "wsh", "wt"), start=1)}
        gus = [g[0] for g in c["gh"]]
        self.gy = pchip(gus, [g[1] for g in c["gh"]])
        self.gw = pchip(gus, [g[2] for g in c["gh"]])
        self.z_bl1 = self.z_of(c["gh"][0][0])
        self.z_ws0 = self.z_of(c["gh"][-1][0])
        self.z_ws1 = self.z_of(c["ws1"])
        self.z_rf1 = self.z_of(c["rf1"])
        self.z_bp = self.z_of(c["bpillar"])
        self.Ra = c["R"] + c["arch_gap"]
        self.hubs = [(c["tf"] / 2, c["R"], self.a), (-c["tf"] / 2, c["R"], self.a),
                     (c["tr"] / 2, c["R"], -self.b), (-c["tr"] / 2, c["R"], -self.b)]

    def z_of(self, u):
        return self.zr + u * (self.zf - self.zr)

    def u_of(self, z):
        return (z - self.zr) / (self.zf - self.zr)

    def stations(self):
        zs = []
        z = self.zr
        while z < self.zf - 1e-6:
            zs.append(z)
            edge = min(z - self.zr, self.zf - z)
            z += 0.04 if edge < 0.45 else 0.09
        zs.append(self.zf)
        extra = []
        for hz in (self.a, -self.b):
            for k in range(15):
                th = -PI / 2 + PI * k / 14
                extra.append(hz + self.Ra * 0.999 * math.sin(th))
            extra += [hz - self.Ra - 0.008, hz + self.Ra + 0.008]
        for e in extra:
            zs = [q for q in zs if abs(q - e) > 0.012 or q in (self.zr, self.zf)]
        zs = sorted(set(zs + extra))
        return [q for q in zs if self.zr <= q <= self.zf]

    def arch(self, z):
        """(in_arch, well ceiling height, track of that axle)."""
        c = self.c
        for hz, tr in ((self.a, c["tf"]), (-self.b, c["tr"])):
            dz = z - hz
            if abs(dz) < self.Ra:
                return True, c["R"] + math.sqrt(max(0.0, self.Ra * self.Ra - dz * dz)), tr
        near = c["tf"] if z > 0 else c["tr"]
        return False, 0.0, near

    def shrink(self, z):
        c = self.c
        s = 0.0
        if z > self.zf - c["rcf"]:
            t = min(1.0, (z - (self.zf - c["rcf"])) / c["rcf"])
            s = c["rcf"] * (1 - math.sqrt(max(0.0, 1 - t * t)))
        elif z < self.zr + c["rcr"]:
            t = min(1.0, ((self.zr + c["rcr"]) - z) / c["rcr"])
            s = c["rcr"] * (1 - math.sqrt(max(0.0, 1 - t * t)))
        return s

    def section(self, z):
        """Left half of the body ring, bottom centre to top centre: (points, kinds of segments)."""
        c = self.c
        u = self.u_of(z)
        yb, ys, yc = self.f["yb"](u), self.f["ys"](u), self.f["yc"](u)
        wb, wsh, wt = self.f["wb"](u), self.f["wsh"](u), self.f["wt"](u)
        bulge = c["bulge"] if self.z_ws0 - 0.05 < z < self.zf - 0.35 else 0.0
        yc += bulge
        in_arch, ya, tr = self.arch(z)
        ysill = yb + c["sill"]
        wi = tr / 2 - c["tw"] / 2 - 0.045
        wlow = wb - 0.03
        q = [(0.0, yb)]
        if in_arch:
            q += [(wi, yb), (wi, ya), (wlow - 0.02, ya)]
            ybot = ya
        else:
            q += [(wi, yb), (0.5 * (wi + wlow - 0.02), 0.5 * (yb + ysill)), (wlow - 0.02, ysill)]
            ybot = ysill
        ymid = min(max(ybot + 0.08, 0.5 * (ybot + ys)), ys - 0.05)
        yte = ys + 0.012 + max(0.0, yc - ys) * 0.25
        s = [(wlow, ybot + 0.025), (wb, ymid), (wsh, ys), (wt, yte),
             (wt * (0.45 if bulge else 0.55), yc - (0.6 * bulge if bulge else 0.3 * c["crown"])), (0.0, yc)]
        s = chaikin(s, 1)
        pts = q + s
        k = self.shrink(z)
        if k > 0:
            sc = max(0.05, (wb - k) / wb)
            pts = [(x * sc, y) for x, y in pts]
        kinds = ["under", "under", "under", "under"] + ["paint"] * (len(pts) - 5)
        return pts, kinds

    def gh_section(self, z):
        c = self.c
        u = self.u_of(z)
        ybase = self.f["ys"](u) + 0.004
        wbase = self.f["wsh"](u) - 0.035
        k = self.shrink(z)
        if k > 0:
            wbase *= max(0.05, (self.f["wb"](u) - k) / self.f["wb"](u))
        ytop = max(ybase + 0.004, self.gy(u))
        wtop = min(self.gw(u), wbase - 0.01)
        h = ytop - ybase
        rr = min(0.07, 0.35 * h)
        cr = c["crown"] * min(1.0, h / 0.2)
        pts = [(wbase, ybase), (wbase - 0.30 * (wbase - wtop), ybase + 0.50 * h),
               (wtop + 0.2 * rr, ytop - 0.8 * rr), (wtop - 0.25 * rr, ytop - 0.1 * rr), (wtop - rr, ytop + 0.1 * cr),
               (0.5 * wtop, ytop + 0.8 * cr), (0.0, ytop + cr)]
        return pts

    def gh_kind(self, z, seg):
        """seg 0-1 side, 2-3 corner, 4-5 top."""
        part = "side" if seg < 2 else ("corner" if seg < 4 else "top")
        if z > self.z_ws1:                              # windshield
            return {"side": "glass", "corner": "paint", "top": "glass"}[part]
        if z > self.z_rf1:                              # roof
            if part == "side":
                return "trim" if abs(z - self.z_bp) < 0.045 else "glass"
            return "paint"
        if part == "top":                               # backlight
            return "glass"
        if part == "side" and self.c["quarter"] and z > self.z_rf1 - 0.35 * (self.z_rf1 - self.z_bl1):
            return "glass"
        return "paint"

    # surface queries for placing details
    def top_y(self, z, x):
        pts, _ = self.section(z)
        best = None
        for (x0, y0), (x1, y1) in zip(pts[4:-1], pts[5:]):
            lo, hi = min(x0, x1), max(x0, x1)
            if lo - 1e-9 <= abs(x) <= hi + 1e-9 and hi - lo > 1e-9:
                t = (abs(x) - x0) / (x1 - x0)
                y = y0 + t * (y1 - y0)
                best = y if best is None else max(best, y)
        return best if best is not None else pts[-1][1]

    def roof_y(self, z, x):
        pts = self.gh_section(z)
        best = None
        for (x0, y0), (x1, y1) in zip(pts[2:-1], pts[3:]):
            lo, hi = min(x0, x1), max(x0, x1)
            if lo - 1e-9 <= abs(x) <= hi + 1e-9 and hi - lo > 1e-9:
                t = (abs(x) - x0) / (x1 - x0)
                y = y0 + t * (y1 - y0)
                best = y if best is None else max(best, y)
        return best if best is not None else pts[-1][1]

    def side_x(self, z, y):
        pts, _ = self.section(z)
        for (x0, y0), (x1, y1) in zip(pts[4:], pts[5:]):
            if min(y0, y1) <= y <= max(y0, y1) and abs(y1 - y0) > 1e-9:
                t = (y - y0) / (y1 - y0)
                return x0 + t * (x1 - x0)
        return None

    def cap_x(self, front: bool, y: float) -> float:
        """Half-width of the end fascia at height y (0 when y is outside it)."""
        pts, _ = self.section(self.zf if front else self.zr)
        best = 0.0
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            if min(y0, y1) <= y <= max(y0, y1) and abs(y1 - y0) > 1e-9:
                best = max(best, x0 + (y - y0) / (y1 - y0) * (x1 - x0))
        return best

    def cap(self, front: bool):
        z = self.zf if front else self.zr
        pts, _ = self.section(z)
        return dict(z=z, xmax=max(p[0] for p in pts), ymin=min(p[1] for p in pts), ymax=max(p[1] for p in pts))


def full_ring(left, closed=True):
    """Mirror a left-half polyline (x >= 0, centre points at both ends) into a ring."""
    right = [(-x, y) for x, y in reversed(left[1:-1])] if closed else [(-x, y) for x, y in reversed(left[:-1])]
    return left + right


def body_meshes(B: Body):
    zs = B.stations()
    rings, kinds = [], None
    for z in zs:
        pts, k = B.section(z)
        rings.append([(x, y, z) for x, y in full_ring(pts)])
        if kinds is None:
            nl = len(pts)
            left = k
            kinds = left + list(reversed(left))       # segments of the mirrored half, same kinds
            assert len(kinds) == 2 * (nl - 1)
    out = {"paint": PM(), "under": PM()}
    n = len(rings[0])
    idmap = {}

    def vid(mat, k, j):
        key = (mat, k, j)
        if key not in idmap:
            idmap[key] = out[mat].v(rings[k][j])
        return idmap[key]

    for k in range(len(rings) - 1):
        for j in range(n):
            mat = kinds[j]
            j2 = (j + 1) % n
            out[mat].face([vid(mat, k, j), vid(mat, k, j2), vid(mat, k + 1, j2), vid(mat, k + 1, j)])
    # end caps (front +Z, rear -Z): flat fascia panels
    for k, sign in ((len(rings) - 1, 1.0), (0, -1.0)):
        ring = rings[k]
        ids = [vid("paint", k, j) for j in range(n)]
        out["paint"].fan(ids, (0, 0, sign))
    return out, zs


def gh_meshes(B: Body, zs_body):
    zs = [z for z in zs_body if B.z_bl1 <= z <= B.z_ws0]
    # denser along the glass slopes
    extra = [B.z_bl1 + (B.z_rf1 - B.z_bl1) * t / 8 for t in range(9)] + [B.z_ws1 + (B.z_ws0 - B.z_ws1) * t / 8 for t in range(9)]
    zs = sorted(set([round(z, 4) for z in zs + extra]))
    clean = []
    for z in zs:
        if not clean or z - clean[-1] > 0.012:
            clean.append(z)
    zs = clean
    out = {"glass": PM(), "paint": PM(), "trim": PM()}
    rings = []
    for z in zs:
        left = B.gh_section(z)
        rings.append([(x, y, z) for x, y in full_ring(left, closed=False)])
    nl = len(B.gh_section(zs[0]))
    n = len(rings[0])
    idmap = {}

    def vid(mat, k, j):
        key = (mat, k, j)
        if key not in idmap:
            idmap[key] = out[mat].v(rings[k][j])
        return idmap[key]

    for k in range(len(rings) - 1):
        zm = 0.5 * (zs[k] + zs[k + 1])
        for j in range(n - 1):
            seg = j if j < nl - 1 else (n - 2 - j)
            mat = B.gh_kind(zm, seg)
            out[mat].face([vid(mat, k, j), vid(mat, k, j + 1), vid(mat, k + 1, j + 1), vid(mat, k + 1, j)])
    for k, sign in ((len(rings) - 1, 1.0), (0, -1.0)):
        ids = [vid("paint", k, j) for j in range(n)]
        out["paint"].fan(ids, (0, 0, sign))
    return out


def ribbon_top(B: Body, m: PM, x0, x1, za, zb, lift=0.004, roof=False, step=0.06):
    """A strip lying on the top surface between lateral offsets x0..x1 (left side, x >= 0)."""
    if zb - za < 0.02:
        return
    nz = max(2, int(math.ceil((zb - za) / step)) + 1)
    xs = [x0, 0.5 * (x0 + x1), x1]
    prev = None
    for i in range(nz):
        z = za + (zb - za) * i / (nz - 1)
        f = B.roof_y if roof else B.top_y
        row = [m.v((x, f(z, x) + lift, z)) for x in xs]
        if prev:
            for j in range(2):
                m.face([prev[j], prev[j + 1], row[j + 1], row[j]], (0, 1, 0))
        prev = row


def ribbon_side(B: Body, m: PM, y0, y1, za, zb, side=1.0, lift=0.004, step=0.05):
    prev = None
    z = za
    zs = []
    while z < zb:
        zs.append(z)
        z += step
    zs.append(zb)
    for z in zs:
        in_arch, ya, _ = B.arch(z)
        xa, xb = B.side_x(z, y0), B.side_x(z, y1)
        if (in_arch and ya > y0 - 0.02) or xa is None or xb is None:
            prev = None
            continue
        row = [m.v((side * (xa + lift), y0, z)), m.v((side * (xb + lift), y1, z))]
        if prev:
            m.face([prev[0], prev[1], row[1], row[0]], (side, 0, 0))
        prev = row


def quad_z(m: PM, x0, x1, y0, y1, z, facing, uv=None):
    ids = [m.v((x0, y0, z), uv[0] if uv else None), m.v((x1, y0, z), uv[1] if uv else None),
           m.v((x1, y1, z), uv[2] if uv else None), m.v((x0, y1, z), uv[3] if uv else None)]
    m.face(ids, (0, 0, facing))


def aerofoil(m: PM, span, chord, thick, z0, y0, aoa, x_c=0.0, camber=0.04):
    """Inverted (downforce) wing section extruded along X, closed at both tips."""
    prof = []
    nseg = 10
    for i in range(nseg + 1):                     # upper surface, leading edge (front, +z) to trailing
        t = i / nseg
        yt = 5 * thick * (0.2969 * math.sqrt(t) - 0.126 * t - 0.3516 * t * t + 0.2843 * t ** 3 - 0.1015 * t ** 4)
        yc = -camber * 4 * t * (1 - t) * chord
        prof.append((t, yc + yt * chord))
    for i in range(nseg - 1, 0, -1):
        t = i / nseg
        yt = 5 * thick * (0.2969 * math.sqrt(t) - 0.126 * t - 0.3516 * t * t + 0.2843 * t ** 3 - 0.1015 * t ** 4)
        yc = -camber * 4 * t * (1 - t) * chord
        prof.append((t, yc - yt * chord))
    ca, sa = math.cos(aoa), math.sin(aoa)
    pts2 = []
    for t, y in prof:
        zz = -t * chord                           # trailing edge to the rear
        # pitch the section nose-down by aoa (trailing edge up)
        pts2.append((z0 + zz * ca + y * sa, y0 + y * ca - zz * sa))
    rows = []
    for x in (x_c - span / 2, x_c + span / 2):
        rows.append([m.v((x, y, z)) for z, y in pts2])
    n = len(pts2)
    cen = (x_c, sum(p[1] for p in pts2) / n, sum(p[0] for p in pts2) / n)
    for j in range(n):
        j2 = (j + 1) % n
        m.face_out([rows[0][j], rows[0][j2], rows[1][j2], rows[1][j]], cen)
    m.fan(rows[0], (-1, 0, 0))
    m.fan(rows[1], (1, 0, 0))
    return pts2


# --------------------------------------------------------------------------------------------
# wheels

def wheel_parts(c, L: Looks):
    R, tw, Rr = c["R"], c["tw"], c["rim"]
    hw = tw / 2
    sh = 0.028
    # tread: across the tyre, outer side last (u across, v around)
    tread = PM(uv=True)
    tp = [(R - 0.004, -hw + sh), (R, -hw * 0.45), (R, hw * 0.45), (R - 0.004, hw - sh)]
    lathe_x(tread, tp, 44, uvf=lambda s, i, r, h: ((h + hw - sh) / (tw - 2 * sh), s * 22))
    side_o = PM(uv=True)
    po = [(R - 0.004, hw - sh), (R - 0.016, hw - 0.008), (R - 0.040, hw + 0.002), (0.5 * (R + Rr), hw + 0.006),
          (Rr + 0.022, hw - 0.002), (Rr + 0.006, hw - 0.010)]
    lathe_x(side_o, po, 44, uvf=lambda s, i, r, h: (s, (r - Rr) / (R - Rr)))
    side_i = PM()
    pi_ = [(Rr + 0.006, -hw + 0.010), (Rr + 0.022, -hw + 0.002), (0.5 * (R + Rr), -hw - 0.006), (R - 0.040, -hw - 0.002),
           (R - 0.016, -hw + 0.008), (R - 0.004, -hw + sh)]
    lathe_x(side_i, pi_, 28)
    # rim barrel (seen through the spokes) faces the axle
    barrel = PM()
    lathe_x(barrel, [(Rr - 0.006, hw - 0.03), (Rr - 0.006, -hw + 0.02)], 32)
    # outer lip
    rim = PM()
    lathe_x(rim, [(Rr + 0.012, hw - 0.016), (Rr + 0.010, hw - 0.006), (Rr - 0.020, hw - 0.006), (Rr - 0.030, hw - 0.016),
                  (Rr - 0.006, hw - 0.03)], 40)
    # spokes
    style, n = c["spokes"]
    h_root, h_tip = hw - 0.075, hw - 0.022
    r0, r1 = 0.062, Rr - 0.026

    def spoke(ang, w0, w1, d0, d1):
        ca, sa = math.cos(ang), math.sin(ang)
        tn = (-sa, ca)

        def at(r, w, h):
            y, z = r * ca + tn[0] * w, r * sa + tn[1] * w
            return (h, y, z)
        corners = [at(r0, -w0, h_root), at(r0, w0, h_root), at(r0, w0, h_root - d0), at(r0, -w0, h_root - d0),
                   at(r1, -w1, h_tip), at(r1, w1, h_tip), at(r1, w1, h_tip - d1), at(r1, -w1, h_tip - d1)]
        rim.hexa(corners)
    if style == "mesh":
        for k in range(n):
            a = 2 * PI * k / n
            spoke(a + 0.10, 0.011, 0.008, 0.02, 0.016)
            spoke(a - 0.10, 0.011, 0.008, 0.02, 0.016)
    elif style == "twin":
        for k in range(n):
            a = 2 * PI * k / n
            spoke(a + 0.07, 0.012, 0.010, 0.026, 0.02)
            spoke(a - 0.07, 0.012, 0.010, 0.026, 0.02)
    elif style == "five":
        for k in range(n):
            spoke(2 * PI * k / n, 0.030, 0.020, 0.03, 0.022)
    else:
        for k in range(n):
            spoke(2 * PI * k / n, 0.016, 0.011, 0.026, 0.02)
    # hub with centre cap and lug nuts
    lathe_x(rim, [(0.070, h_root - 0.02), (0.068, h_root + 0.002), (0.035, h_root + 0.012), (0.0, h_root + 0.016)], 24)
    for k in range(5):
        a = 2 * PI * k / 5 + 0.3
        y, z = 0.045 * math.cos(a), 0.045 * math.sin(a)
        rim.box((h_root + 0.018, y, z), (0.014, 0.012, 0.012))
    # brake disc and hat
    disc = PM()
    dh0, dh1 = -0.002, -0.028
    lathe_x(disc, [(0.10, dh0), (0.10, dh1), (Rr - 0.036, dh1), (Rr - 0.036, dh0), (0.10, dh0)], 36)
    hat = PM()
    lathe_x(hat, [(0.10, dh0), (0.10, h_root - 0.02), (0.0, h_root - 0.02)], 20)
    # caliper (left wheel): straddles the disc at the rear-top, does not spin
    cal = {}
    for side, mir in (("L", False), ("R", True)):
        m = PM()
        lathe_x(m, [(Rr - 0.100, 0.012), (Rr - 0.100, -0.044), (Rr - 0.026, -0.044), (Rr - 0.026, 0.012), (Rr - 0.100, 0.012)],
                8, a0=-1.35, a1=-0.55, mirror=mir, cap_ends=True)
        cal[side] = m
    return dict(tread=tread, side_o=side_o, side_i=side_i, barrel=barrel, rim=rim, disc=disc, hat=hat, cal=cal)


# --------------------------------------------------------------------------------------------
# details

def round_lamp(m: PM, x, y, z, r, facing, segs=18):
    m.disc((x, y, z), r, "z", segs, sign=facing, uv=m.t is not None)


def car_looks(c) -> Looks:
    L = Looks(CAR_TEX)
    L.add("paint", base=c["paint"], metal=0.12, rough=0.30, mdef="Paint")
    L.add("stripe", base=c["stripe"], metal=0.10, rough=0.32, mdef="Stripe")
    L.add("under", base=(0.035, 0.035, 0.04), rough=0.9)
    L.add("glass", base=(0.035, 0.045, 0.055), metal=0.0, rough=0.06)
    L.add("trim", base=(0.025, 0.025, 0.028), rough=0.55)
    L.add("carbon", tex="carbon.png", base=(0.30, 0.30, 0.32), metal=0.2, rough=0.38)
    L.add("grille", tex="grille.png", base=(1, 1, 1), rough=0.6)
    L.add("head", tex="lens.png", emtex="lens.png", base=(0.85, 0.86, 0.88), rough=0.15, emit=(0.55, 0.55, 0.50), mdef="HeadGlow")
    L.add("brake", tex="lens.png", emtex="lens.png", base=(0.55, 0.03, 0.03), rough=0.2, emit=(0.30, 0.01, 0.01), mdef="BrakeGlow")
    L.add("reverse", tex="lens.png", emtex="lens.png", base=(0.80, 0.80, 0.80), rough=0.2, emit=(0.0, 0.0, 0.0), mdef="ReverseGlow")
    L.add("bezel", base=(0.02, 0.02, 0.022), rough=0.35)
    L.add("chrome", base=(0.78, 0.78, 0.80), metal=0.75, rough=0.22)
    L.add("soot", base=(0.02, 0.02, 0.02), rough=0.95)
    L.add("plate", tex="plates.png", base=(1, 1, 1), rough=0.5)
    L.add("tread", tex="tread.png", base=(1, 1, 1), rough=0.92)
    L.add("sidewall", tex="sidewall.png", base=(1, 1, 1), rough=0.85)
    L.add("rubber", base=(0.07, 0.07, 0.075), rough=0.9)
    L.add("rim", base=c["rimcol"], metal=0.35, rough=0.32)
    L.add("rim_in", base=tuple(0.5 * v for v in c["rimcol"]), metal=0.3, rough=0.5)
    L.add("disc", base=(0.42, 0.42, 0.43), metal=0.45, rough=0.45)
    L.add("hat", base=(0.12, 0.12, 0.13), metal=0.3, rough=0.6)
    L.add("caliper", base=c["caliper"], metal=0.1, rough=0.35)
    L.add("tow", base=(0.85, 0.08, 0.06), rough=0.6)
    L.add("blob", tex="spot.png", base=(0, 0, 0), rough=1.0, alpha="blend")
    return L


def build_car(c):
    B = Body(c)
    L = car_looks(c)
    body, zs = body_meshes(B)
    gh = gh_meshes(B, zs)
    paint = body["paint"]
    paint_gh = gh["paint"]
    stripe = PM()
    trim = gh["trim"]
    carbon, grille, head, brake, rev, bezel, chrome, soot, plate = PM(), PM(uv=True), PM(uv=True), PM(uv=True), PM(uv=True), PM(), PM(), PM(), PM(uv=True)
    extra_paint = PM()
    tow = PM()
    fcap, rcap = B.cap(True), B.cap(False)
    zf, zr = B.zf, B.zr

    # ---- belt-line window trim, door shut lines and handles
    zt0 = B.z_rf1 - (0.35 * (B.z_rf1 - B.z_bl1) if c["quarter"] else 0.0)
    zt1 = B.z_ws0 - 0.06
    nzt = max(2, int((zt1 - zt0) / 0.06) + 1)
    for sgn in (1.0, -1.0):
        prev = None
        for i in range(nzt):
            z = zt0 + (zt1 - zt0) * i / (nzt - 1)
            g = B.gh_section(z)
            (x0_, y0_), (x1_, y1_) = g[0], g[1]
            dx, dy = x1_ - x0_, y1_ - y0_
            ln = math.hypot(dx, dy) or 1.0
            ux, uy = dx / ln, dy / ln
            nx_, ny_ = uy, -ux                       # outward (away from the cabin)
            if nx_ < 0:
                nx_, ny_ = -nx_, -ny_
            a_ = (x0_ + nx_ * 0.003, y0_ + ny_ * 0.003)
            b_ = (x0_ + ux * 0.028 + nx_ * 0.003, y0_ + uy * 0.028 + ny_ * 0.003)
            row = [trim.v((sgn * a_[0], a_[1], z)), trim.v((sgn * b_[0], b_[1], z))]
            if prev:
                trim.face([prev[0], prev[1], row[1], row[0]], (sgn, 0.3, 0))
            prev = row
    zd0 = B.z_ws0 - 0.04
    zd1 = B.z_bp - 0.02 if c["quarter"] else B.z_bp + 0.05
    for zd in (zd0, zd1):
        u = B.u_of(zd)
        ya_ = B.f["yb"](u) + c["sill"] + 0.04
        yb_ = B.f["ys"](u) - 0.02
        for sgn in (1.0, -1.0):
            prev = None
            for i in range(6):
                y = ya_ + (yb_ - ya_) * i / 5
                x = B.side_x(zd, y)
                if x is None:
                    prev = None
                    continue
                row = [trim.v((sgn * (x + 0.0025), y, zd - 0.003)), trim.v((sgn * (x + 0.0025), y, zd + 0.003))]
                if prev:
                    trim.face([prev[0], prev[1], row[1], row[0]], (sgn, 0, 0))
                prev = row
    zh_ = zd1 + 0.10
    yh_ = B.f["ys"](B.u_of(zh_)) - 0.075
    for sgn in (1.0, -1.0):
        xh = B.side_x(zh_, yh_)
        if xh is not None:
            ids = [trim.v((sgn * (xh + 0.006), yh_ - 0.012, zh_ - 0.06)), trim.v((sgn * (xh + 0.006), yh_ - 0.012, zh_ + 0.06)),
                   trim.v((sgn * (xh + 0.006), yh_ + 0.012, zh_ + 0.06)), trim.v((sgn * (xh + 0.006), yh_ + 0.012, zh_ - 0.06))]
            trim.face(ids, (sgn, 0, 0))

    # ---- livery stripes on hood, roof and deck
    for kind, x0, x1, pair in c["stripes"]:
        for sgn in ((1, -1) if pair else (1,)):
            xa, xb = (x0, x1) if sgn > 0 else (-x1, -x0)
            for (za, zb, roof) in ((B.z_ws0 + 0.03, zf - 0.04, False), (B.z_rf1 + 0.04, B.z_ws1 - 0.04, True),
                                   (zr + 0.05, B.z_bl1 - 0.03, False)):
                ribbon_top_signed(B, stripe, xa, xb, za, zb, roof)
    if c["side"]:
        y0, y1 = c["side"]
        for sgn in (1.0, -1.0):
            ribbon_side(B, stripe, y0, y1, zr + 0.20, zf - 0.25, sgn)

    # ---- front fascia: grille, plate, splitter, headlights
    fx, fy0, fy1 = fcap["xmax"], fcap["ymin"], fcap["ymax"]
    gy0 = fy0 + 0.05
    gy1 = gy0 + (fy1 - fy0) * 0.42
    gw = 0.70 * min(B.cap_x(True, gy0), B.cap_x(True, gy1))
    quad_z(grille, -gw, gw, gy0, gy1, zf + 0.003, 1, uv=[(0, 0), (gw * 8, 0), (gw * 8, (gy1 - gy0) * 8), (0, (gy1 - gy0) * 8)])
    row, nrow = plate_row(c["id"]), len(CARS)
    v0, v1 = 1 - (row + 1) / nrow, 1 - row / nrow
    pw, ph = 0.33, 0.165
    py = gy0 + 0.03 + ph / 2
    quad_z(plate, -pw / 2, pw / 2, py - ph / 2, py + ph / 2, zf + 0.008, 1, uv=[(0, v0), (1, v0), (1, v1), (0, v1)])
    quad_z(bezel, -pw / 2 - 0.01, pw / 2 + 0.01, py - ph / 2 - 0.01, py + ph / 2 + 0.01, zf + 0.006, 1)
    yb_f = B.f["yb"](1.0)
    carbon.box((0, yb_f - 0.012, zf - 0.20), (fx * 2 + 0.06, 0.022, 0.52))
    if c["head"] == "popup":
        th = 0.20
        for sgn in (1, -1):
            zh = zf - 0.40
            xc = sgn * (B.f["wt"](B.u_of(zh)) - 0.17)
            y_h = B.top_y(zh, abs(xc)) - 0.015
            wpod, hp, lp = 0.27, 0.105, 0.10
            cs, sn = math.cos(th), math.sin(th)

            def P(dx, dy, dz):
                return (xc + dx, y_h + dy * cs + dz * sn, zh + dz * cs - dy * sn)
            corners = [P(-wpod / 2, 0, 0), P(wpod / 2, 0, 0), P(wpod / 2, hp, 0), P(-wpod / 2, hp, 0),
                       P(-wpod / 2, 0, lp), P(wpod / 2, 0, lp), P(wpod / 2, hp, lp), P(-wpod / 2, hp, lp)]
            extra_paint.hexa(corners)
            fn = (0, sn, cs)
            a, b, cc, d = P(-wpod / 2 + 0.02, 0.012, lp + 0.004), P(wpod / 2 - 0.02, 0.012, lp + 0.004), P(wpod / 2 - 0.02, hp - 0.012, lp + 0.004), P(-wpod / 2 + 0.02, hp - 0.012, lp + 0.004)
            ids = [head.v(a, (0, 0)), head.v(b, (2, 0)), head.v(cc, (2, 1)), head.v(d, (0, 1))]
            head.face(ids, fn)
        # small indicator/fog lamps in the bumper
        for sgn in (1, -1):
            xi = B.cap_x(True, gy1 + 0.04) - 0.16
            quad_z(head, sgn * xi - 0.07, sgn * xi + 0.07, gy1 + 0.02, gy1 + 0.06, zf + 0.004, 1,
                   uv=[(0, 0), (1, 0), (1, 0.5), (0, 0.5)])
    else:
        hw_, hh = {"slim": (0.30, 0.07), "square": (0.26, 0.13)}[c["head"]]
        for sgn in (1, -1):
            y1 = fy1 - 0.03
            xe = min(B.cap_x(True, y1), B.cap_x(True, y1 - hh)) - 0.035
            x0, x1 = sgn * (xe - hw_), sgn * xe
            quad_z(bezel, min(x0, x1) - 0.012, max(x0, x1) + 0.012, y1 - hh - 0.012, y1 + 0.012, zf + 0.002, 1)
            quad_z(head, min(x0, x1), max(x0, x1), y1 - hh, y1, zf + 0.004, 1, uv=[(0, 0), (2, 0), (2, 1), (0, 1)])
            # the lens wraps over the nose top
            ribbon_top_lens(B, head, min(abs(x0), abs(x1)), max(abs(x0), abs(x1)), zf - 0.16, zf - 0.01, sgn)

    # ---- rear fascia: lights, plate, diffuser, exhaust
    ry0, ry1 = rcap["ymin"], rcap["ymax"]
    rx = min(B.cap_x(False, ry1 - 0.05), B.cap_x(False, ry1 - 0.20)) - 0.02
    zb = zr - 0.004
    if c["tail"] == "round":
        for sgn in (1, -1):
            for k, off in enumerate((0.15, 0.33)):
                x = sgn * (rx - off)
                y = ry1 - 0.11
                round_lamp(bezel, x, y, zb + 0.002, 0.078, -1)
                round_lamp(brake, x, y, zb, 0.064, -1)
        for sgn in (1, -1):
            quad_z(rev, sgn * 0.10 - 0.04, sgn * 0.10 + 0.04, ry1 - 0.15, ry1 - 0.08, zb, -1, uv=[(0, 0), (1, 0), (1, 1), (0, 1)])
    elif c["tail"] == "bars":
        for sgn in (1, -1):
            x0, x1 = sgn * 0.05, sgn * (rx - 0.03)
            lo, hi = min(x0, x1), max(x0, x1)
            quad_z(bezel, lo - 0.01, hi + 0.01, ry1 - 0.16, ry1 - 0.035, zb + 0.002, -1)
            quad_z(brake, lo, hi, ry1 - 0.085, ry1 - 0.045, zb, -1, uv=[(0, 0), (4, 0), (4, 1), (0, 1)])
            quad_z(brake, lo + 0.08 if sgn > 0 else lo, hi if sgn > 0 else hi - 0.08, ry1 - 0.15, ry1 - 0.12, zb, -1,
                   uv=[(0, 0), (4, 0), (4, 0.5), (0, 0.5)])
            quad_z(rev, sgn * 0.06 - 0.03 if sgn > 0 else sgn * 0.06 - 0.03, sgn * 0.06 + 0.03, ry1 - 0.15, ry1 - 0.12, zb, -1,
                   uv=[(0, 0), (1, 0), (1, 0.5), (0, 0.5)])
    elif c["tail"] == "vertical":
        for sgn in (1, -1):
            x0, x1 = sgn * (rx - 0.15), sgn * (rx - 0.02)
            lo, hi = min(x0, x1), max(x0, x1)
            quad_z(bezel, lo - 0.012, hi + 0.012, ry1 - 0.44, ry1 - 0.04, zb + 0.002, -1)
            quad_z(brake, lo, hi, ry1 - 0.30, ry1 - 0.05, zb, -1, uv=[(0, 0), (1, 0), (1, 3), (0, 3)])
            quad_z(rev, lo, hi, ry1 - 0.43, ry1 - 0.32, zb, -1, uv=[(0, 0), (1, 0), (1, 1), (0, 1)])
    else:  # fullbar
        quad_z(bezel, -rx + 0.03, rx - 0.03, ry1 - 0.14, ry1 - 0.05, zb + 0.002, -1)
        quad_z(brake, -rx + 0.05, rx - 0.05, ry1 - 0.10, ry1 - 0.065, zb, -1, uv=[(0, 0), (10, 0), (10, 1), (0, 1)])
        for sgn in (1, -1):
            quad_z(rev, sgn * 0.22 - 0.05, sgn * 0.22 + 0.05, ry1 - 0.135, ry1 - 0.11, zb, -1, uv=[(0, 0), (1, 0), (1, 0.5), (0, 0.5)])
    py = ry0 + 0.19 + ph / 2
    quad_z(plate, pw / 2, -pw / 2, py - ph / 2, py + ph / 2, zr - 0.008, -1, uv=[(0, v0), (1, v0), (1, v1), (0, v1)])
    quad_z(bezel, -pw / 2 - 0.01, pw / 2 + 0.01, py - ph / 2 - 0.01, py + ph / 2 + 0.01, zr - 0.006, -1)
    yb_r = B.f["yb"](0.0)
    carbon.box((0, yb_r - 0.01, zr + 0.22), (rx * 1.7, 0.02, 0.48))
    for k in range(5):
        x = -0.36 + 0.18 * k
        carbon.hexa([(x - 0.006, yb_r - 0.02, zr + 0.45), (x + 0.006, yb_r - 0.02, zr + 0.45), (x + 0.006, yb_r - 0.02, zr - 0.01), (x - 0.006, yb_r - 0.02, zr - 0.01),
                     (x - 0.006, yb_r + 0.0, zr + 0.45), (x + 0.006, yb_r + 0.0, zr + 0.45), (x + 0.006, yb_r + 0.12, zr - 0.01), (x - 0.006, yb_r + 0.12, zr - 0.01)])
    tips = []
    for (ex, ey) in c["exhaust"]:
        r = c["tip_r"]
        prof_o = [(r, -0.10), (r, 0.05), (r * 0.86, 0.056)]          # h along -Z (rearward)
        segs = 18
        rows = []
        for s in range(segs + 1):
            a = 2 * PI * s / segs
            ca, sa = math.cos(a), math.sin(a)
            rows.append([chrome.v((ex + pr * ca, ey + pr * sa, zr - ph_)) for pr, ph_ in prof_o])
        for s in range(segs):
            a = 2 * PI * (s + 0.5) / segs
            for i in range(len(prof_o) - 1):
                n = (math.cos(a), math.sin(a), -0.6 * i)
                chrome.face([rows[s][i], rows[s + 1][i], rows[s + 1][i + 1], rows[s][i + 1]], n)
        soot.disc((ex, ey, zr - 0.052), r * 0.86, "z", segs, sign=-1)
        tips.append((ex, ey, zr - 0.06))

    # ---- mirrors
    zm = B.z_ws0 - 0.13
    um = B.u_of(zm)
    ysm = B.f["ys"](um)
    xsm = B.f["wsh"](um)
    for sgn in (1, -1):
        xo = xsm + 0.12
        cx_, cy_ = sgn * xo, ysm + 0.13
        hx, hy, hz = 0.085, 0.048, 0.06
        extra_paint.hexa([(cx_ - hx, cy_ - hy, zm - hz), (cx_ + hx, cy_ - hy, zm - hz), (cx_ + hx, cy_ + hy, zm - hz), (cx_ - hx, cy_ + hy, zm - hz),
                          (cx_ - hx * 0.8, cy_ - hy * 0.7, zm + hz), (cx_ + hx * 0.8, cy_ - hy * 0.7, zm + hz), (cx_ + hx * 0.8, cy_ + hy * 0.7, zm + hz), (cx_ - hx * 0.8, cy_ + hy * 0.7, zm + hz)])
        trim.face([trim.v((cx_ - hx * 0.85, cy_ - hy * 0.8, zm - hz - 0.002)), trim.v((cx_ + hx * 0.85, cy_ - hy * 0.8, zm - hz - 0.002)),
                   trim.v((cx_ + hx * 0.85, cy_ + hy * 0.8, zm - hz - 0.002)), trim.v((cx_ - hx * 0.85, cy_ + hy * 0.8, zm - hz - 0.002))], (0, 0, -1))
        x_in = sgn * (xsm - 0.03)
        trim.hexa([(x_in, ysm + 0.005, zm - 0.03), (cx_ - sgn * hx * 0.6, cy_ - 0.02, zm - 0.02), (cx_ - sgn * hx * 0.6, cy_ - 0.0, zm - 0.02), (x_in, ysm + 0.03, zm - 0.03),
                   (x_in, ysm + 0.005, zm + 0.03), (cx_ - sgn * hx * 0.6, cy_ - 0.02, zm + 0.02), (cx_ - sgn * hx * 0.6, cy_ - 0.0, zm + 0.02), (x_in, ysm + 0.03, zm + 0.03)])

    # ---- wings
    if c["wing"] == "gt":
        span, chord = 1.60, 0.30
        zw, yw = zr + 0.30, 1.22
        aerofoil(carbon, span, chord, 0.12, zw + chord / 2, yw, 0.14)
        for sgn in (1, -1):
            xe = sgn * span / 2
            carbon.hexa([(xe, yw - 0.07, zw + 0.17), (xe + sgn * 0.008, yw - 0.07, zw + 0.17), (xe + sgn * 0.008, yw + 0.035, zw + 0.15), (xe, yw + 0.035, zw + 0.15),
                         (xe, yw - 0.05, zw - 0.19), (xe + sgn * 0.008, yw - 0.05, zw - 0.19), (xe + sgn * 0.008, yw + 0.075, zw - 0.19), (xe, yw + 0.075, zw - 0.19)])
            # swan-neck uprights to the deck
            xu = sgn * 0.42
            ydeck = B.top_y(zw - 0.02, abs(xu))
            carbon.hexa([(xu - 0.008, ydeck - 0.01, zw - 0.10), (xu + 0.008, ydeck - 0.01, zw - 0.10), (xu + 0.008, ydeck - 0.01, zw + 0.06), (xu - 0.008, ydeck - 0.01, zw + 0.06),
                         (xu - 0.008, yw - 0.01, zw - 0.06), (xu + 0.008, yw - 0.01, zw - 0.06), (xu + 0.008, yw - 0.01, zw + 0.04), (xu - 0.008, yw - 0.01, zw + 0.04)])
    elif c["wing"] == "roof":
        zt = B.z_rf1
        yt = B.roof_y(zt, 0.0)
        wr = B.gw(B.u_of(zt))
        carbon.hexa([(-wr, yt - 0.01, zt + 0.06), (wr, yt - 0.01, zt + 0.06), (wr, yt + 0.012, zt + 0.06), (-wr, yt + 0.012, zt + 0.06),
                     (-wr * 1.02, yt - 0.05, zt - 0.22), (wr * 1.02, yt - 0.05, zt - 0.22), (wr * 1.02, yt - 0.025, zt - 0.24), (-wr * 1.02, yt - 0.025, zt - 0.24)])
        for sgn in (1, -1):
            carbon.box((sgn * (wr + 0.005), yt - 0.035, zt - 0.09), (0.01, 0.07, 0.30))
    elif c["wing"] == "lip":
        zl = zr + 0.10
        yl = B.top_y(zl, 0.0)
        wl = rx * 0.92
        extra_paint.hexa([(-wl, yl - 0.01, zl + 0.10), (wl, yl - 0.01, zl + 0.10), (wl, yl + 0.004, zl + 0.10), (-wl, yl + 0.004, zl + 0.10),
                          (-wl, yl - 0.01, zr + 0.01), (wl, yl - 0.01, zr + 0.01), (wl, yl + 0.05, zr + 0.01), (-wl, yl + 0.05, zr + 0.01)])
    # ducktail comes from the body keys (banshee)

    # ---- extras
    ex = c["extras"]
    if "canards" in ex:
        for sgn in (1, -1):
            for k, dy in enumerate((0.10, 0.17)):
                x0 = sgn * (fx + 0.01)
                y = fy0 + dy
                carbon.hexa([(x0, y, zf - 0.02), (x0 + sgn * 0.09, y + 0.02, zf - 0.16), (x0 + sgn * 0.09, y + 0.026, zf - 0.16), (x0, y + 0.006, zf - 0.02),
                             (x0 - sgn * 0.02, y, zf - 0.20), (x0 + sgn * 0.02, y + 0.01, zf - 0.22), (x0 + sgn * 0.02, y + 0.016, zf - 0.22), (x0 - sgn * 0.02, y + 0.006, zf - 0.20)])
    if "skirts" in ex:
        za, zb2 = -B.b + B.Ra + 0.03, B.a - B.Ra - 0.03
        um2 = B.u_of(0.5 * (za + zb2))
        xs = B.f["wb"](um2) - 0.02
        ysl = B.f["yb"](um2) + c["sill"]
        for sgn in (1, -1):
            carbon.box((sgn * xs, ysl - 0.02, 0.5 * (za + zb2)), (0.05, 0.05, zb2 - za))
    if "vents" in ex:
        for sgn in (1, -1):
            ribbon_top_mat(B, grille, 0.20, 0.36, B.z_ws0 + 0.18, B.z_ws0 + 0.50, sgn)
    if "tow" in ex:
        tow.box((fx * 0.55, fy0 + 0.10, zf + 0.01), (0.03, 0.06, 0.03))
    if "rally" in ex:
        yl = gy1 - 0.02
        carbon.box((0, yl, zf + 0.05), (fx * 1.6, 0.03, 0.03))
        for x in (-0.46, -0.16, 0.16, 0.46):
            lathe_like_cyl(bezel, (x, yl + 0.06, zf + 0.06), 0.075, 0.06)
            round_lamp(head, x, yl + 0.06, zf + 0.092, 0.064, 1)
    if "scoop" in ex:
        z1s = B.z_ws1 - 0.06
        z0s = z1s - 0.42
        yr1 = B.roof_y(z1s, 0.0)
        yr0 = B.roof_y(z0s, 0.0)
        w = 0.17
        extra_paint.hexa([(-w, yr1 - 0.01, z1s), (w, yr1 - 0.01, z1s), (w * 0.9, yr1 + 0.075, z1s), (-w * 0.9, yr1 + 0.075, z1s),
                          (-w, yr0 - 0.01, z0s), (w, yr0 - 0.01, z0s), (w * 0.8, yr0 + 0.03, z0s), (-w * 0.8, yr0 + 0.03, z0s)])
        trim.face([trim.v((-w * 0.82, yr1 + 0.004, z1s + 0.002)), trim.v((w * 0.82, yr1 + 0.004, z1s + 0.002)),
                   trim.v((w * 0.74, yr1 + 0.065, z1s + 0.002)), trim.v((-w * 0.74, yr1 + 0.065, z1s + 0.002))], (0, 0, 1))
    if "flaps" in ex:
        for (hx_, _, hz) in B.hubs:
            sgn = 1 if hx_ > 0 else -1
            zf_ = hz - B.Ra - 0.03
            tw2 = c["tw"] / 2 + 0.02
            trim.box((hx_, 0.20, zf_), (2 * tw2, 0.26, 0.01))

    # ---- write
    parts = []
    def sh(look, m, crease=0.5):
        if not m.empty():
            parts.append(shape(L, look, m.ifs(crease=crease), shadow=True))
    sh("paint", paint, 0.62)
    sh("paint", paint_gh, 0.62)
    sh("paint", extra_paint, 0.4)
    sh("under", body["under"], 0.3)
    sh("glass", gh["glass"], 0.7)
    sh("trim", trim, 0.4)
    sh("stripe", stripe, 0.6)
    sh("carbon", carbon_uv(carbon), 0.3)
    sh("grille", grille, 0.1)
    sh("bezel", bezel, 0.3)
    sh("head", head, 0.3)
    sh("brake", brake, 0.3)
    sh("reverse", rev, 0.3)
    sh("plate", plate, 0.1)
    sh("chrome", chrome, 1.2)
    sh("soot", soot, 0.3)
    sh("tow", tow, 0.3)
    body_xml = "".join(parts)

    W = wheel_parts(c, L)
    def ws(look, m, crease):
        return shape(L, look, m.ifs(crease=crease), shadow=True)
    wheel_geo = (ws("tread", W["tread"], 1.2) + ws("sidewall", W["side_o"], 1.2) + ws("rubber", W["side_i"], 1.2)
                 + ws("rim_in", W["barrel"], 1.2) + ws("rim", W["rim"], 0.5) + ws("disc", W["disc"], 0.3) + ws("hat", W["hat"], 0.5))
    cal_l = ws("caliper", W["cal"]["L"], 0.4)
    cal_r = ws("caliper", W["cal"]["R"], 0.4)
    names = ("FL", "FR", "RL", "RR")
    wheels = []
    for k, (hx_, hy, hz) in enumerate(B.hubs):
        nm = names[k]
        left = hx_ > 0
        if k == 0:
            spin_in = f"<Group DEF='WheelGeo'>{wheel_geo}</Group>"
        else:
            spin_in = "<Group USE='WheelGeo'/>"
        if not left:
            spin_in = f"<Transform rotation='0 1 0 3.14159265'>{spin_in}</Transform>"
        if k == 0:
            cal = f"<Group DEF='CaliperL'>{cal_l}</Group>"
        elif k == 1:
            cal = f"<Group DEF='CaliperR'>{cal_r}</Group>"
        else:
            cal = "<Group USE='CaliperL'/>" if left else "<Group USE='CaliperR'/>"
        wheels.append(f"<Transform DEF='Wheel{nm}' translation='{vec(hx_, hy, hz, d=4)}'>"
                      f"<Transform DEF='Spin{nm}'>{spin_in}</Transform>{cal}</Transform>")

    blob = PM(uv=True)
    hl, hwid = c["length"] / 2 + 0.25, c["width"] / 2 + 0.22
    ids = [blob.v((-hwid, 0.012, zr - 0.25), (0, 0)), blob.v((hwid, 0.012, zr - 0.25), (1, 0)),
           blob.v((hwid, 0.012, zf + 0.25), (1, 1)), blob.v((-hwid, 0.012, zf + 0.25), (0, 1))]
    blob.face(ids, (0, 1, 0))
    blob_xml = f"<Transform DEF='ContactShadow'>{shape(L, 'blob', blob.ifs(crease=0.0))}</Transform>"
    blob_xml = blob_xml.replace("castShadow='true'", "castShadow='false'")

    hubs_v = " ".join(vec(*h, d=4) for h in B.hubs)
    ex_v = " ".join(vec(*t, d=3) for t in tips)
    roof = max(g[1] for g in c["gh"]) + c["crown"]
    meta = ("<MetadataSet name='kansei:car' containerField='metadata'>"
            f"<MetadataString name='id' value='\"{c['id']}\"' containerField='value'/>"
            f"<MetadataString name='name' value='\"{esc(c['name'])}\"' containerField='value'/>"
            f"<MetadataDouble name='hubs' value='{hubs_v}' containerField='value'/>"
            f"<MetadataDouble name='wheelRadius' value='{fnum(c['R'], 4)}' containerField='value'/>"
            f"<MetadataDouble name='track' value='{fnum(c['tf'], 4)} {fnum(c['tr'], 4)}' containerField='value'/>"
            f"<MetadataDouble name='wheelbase' value='{fnum(c['L'], 4)}' containerField='value'/>"
            f"<MetadataDouble name='cgHeight' value='{fnum(c['cgH'], 4)}' containerField='value'/>"
            f"<MetadataDouble name='exhaust' value='{ex_v}' containerField='value'/>"
            f"<MetadataDouble name='size' value='{fnum(c['length'], 3)} {fnum(c['width'], 3)} {fnum(roof, 3)}' containerField='value'/>"
            f"<MetadataDouble name='bounds' value='{vec(-c['width'] / 2, 0, zr, d=3)} {vec(c['width'] / 2, roof, zf, d=3)}' containerField='value'/>"
            "</MetadataSet>")
    scene = (f"<WorldInfo title='KANSEI {esc(c['name'])}' info='\"KANSEI car model. Faces +Z, wheels on y = 0, origin under the centre of mass.\"'/>"
             f"<Transform DEF='Car'>{meta}"
             f"<Transform DEF='Body' center='0 {fnum(c['cgH'], 3)} 0'>{body_xml}</Transform>"
             + "".join(wheels) + blob_xml + "</Transform>")
    doc = x3d_doc(f"KANSEI {c['name']}", f"KANSEI car {c['name']}: original design, lofted body with wheel arches, glass, lights (HeadGlow, BrakeGlow, ReverseGlow), multi-spoke wheels. Faces +Z, wheels on y = 0.",
                  [("Shape", 2), ("Texturing", 2)], scene, "x3d.drift/build/build_world.py")
    info = dict(id=c["id"], name=c["name"], file=f"{c['id']}.x3d", wheelRadius=c["R"], wheelbase=c["L"], track=[c["tf"], c["tr"]],
                hubs=[[round(v, 4) for v in h] for h in B.hubs], exhaust=[[round(v, 4) for v in t] for t in tips], length=c["length"], width=c["width"], height=round(roof, 3))
    return doc, info


def ribbon_top_signed(B, m, xa, xb, za, zb, roof):
    """Top strip that may sit right of the centre line (negative x)."""
    if xa >= 0:
        ribbon_top(B, m, xa, xb, za, zb, roof=roof)
        return
    if xb <= 0:
        tmp = PM()
        ribbon_top(B, tmp, -xb, -xa, za, zb, roof=roof)
        base = len(m.p)
        for p in tmp.p:
            m.v((-p[0], p[1], p[2]))
        for f in tmp.f:
            m.face([base + i for i in f], (0, 1, 0))
        return
    ribbon_top(B, m, 0.0, xb, za, zb, roof=roof)
    ribbon_top_signed(B, m, xa, 0.0, za, zb, roof)


def ribbon_top_mat(B, m, x0, x1, za, zb, sgn):
    if sgn > 0:
        ribbon_top_uv(B, m, x0, x1, za, zb, 1.0)
    else:
        ribbon_top_uv(B, m, x0, x1, za, zb, -1.0)


def ribbon_top_uv(B, m: PM, x0, x1, za, zb, sgn, lift=0.004):
    nz = max(2, int((zb - za) / 0.05) + 1)
    prev = None
    for i in range(nz):
        z = za + (zb - za) * i / (nz - 1)
        row = [m.v((sgn * x, B.top_y(z, x) + lift, z), ((x - x0) * 10, (z - za) * 10)) for x in (x0, x1)]
        if prev:
            m.face([prev[0], prev[1], row[1], row[0]], (0, 1, 0))
        prev = row


def ribbon_top_lens(B, m: PM, x0, x1, za, zb, sgn):
    nz = 4
    prev = None
    for i in range(nz):
        z = za + (zb - za) * i / (nz - 1)
        row = [m.v((sgn * x, B.top_y(z, x) + 0.004, z), ((x - x0) / (x1 - x0) * 2, i / (nz - 1))) for x in (x0, x1)]
        if prev:
            m.face([prev[0], prev[1], row[1], row[0]], (0, 1, 0))
        prev = row


def lathe_like_cyl(m: PM, centre, r, length, segs=16):
    """Short cylinder along +Z (lamp pod housings), closed at the back."""
    cx, cy, cz = centre
    rows = []
    for s in range(segs):
        a = 2 * PI * s / segs
        rows.append((m.v((cx + r * math.cos(a), cy + r * math.sin(a), cz - length / 2)),
                     m.v((cx + r * math.cos(a), cy + r * math.sin(a), cz + length / 2))))
    for s in range(segs):
        a = 2 * PI * (s + 0.5) / segs
        s2 = (s + 1) % segs
        m.face([rows[s][0], rows[s2][0], rows[s2][1], rows[s][1]], (math.cos(a), math.sin(a), 0))
    m.face([r_[1] for r_ in rows], (0, 0, 1))
    m.face([r_[0] for r_ in rows], (0, 0, -1))


def carbon_uv(m: PM) -> PM:
    """Box-project texture coordinates for the carbon parts (8 weave cells per 10 cm)."""
    out = PM(uv=True)
    for f in m.f:
        n = m.newell(f)
        ax = max(range(3), key=lambda k: abs(n[k]))
        ids = []
        for i in f:
            p = m.p[i]
            a, b = [(1, 2), (0, 2), (0, 1)][ax]
            ids.append(out.v(p, (p[a] * 12, p[b] * 12)))
        out.f.append(ids)
    return out


# --------------------------------------------------------------------------------------------
# the showroom

GARAGE_CAMS = [
    ("GarageCam0", (4.3, 1.15, 5.1), (0.0, 0.55, 0.15), "Front three-quarter"),
    ("GarageCam1", (-6.2, 0.95, 0.6), (0.0, 0.6, 0.1), "Side profile"),
    ("GarageCam2", (-4.0, 1.55, -5.2), (0.0, 0.55, -0.2), "Rear three-quarter"),
    ("GarageCam3", (2.0, 0.42, 4.6), (0.0, 0.5, 0.6), "Low front"),
    ("GarageCam4", (0.6, 5.6, 3.6), (0.0, 0.3, 0.0), "Above"),
]


def build_garage():
    from kx3d import Mesh
    L = Looks(("textures/", "../textures/"))
    L.add("floor", tex="floor.png", base=(0.20, 0.20, 0.215), metal=0.0, rough=0.62, tt=(5, 5))
    L.add("tt_top", base=(0.015, 0.016, 0.02), metal=0.0, rough=0.22, transp=0.30)
    L.add("tt_rim", base=(0.10, 0.10, 0.11), metal=0.6, rough=0.3)
    L.add("led", base=(0.6, 0.9, 1.0), emit=(0.45, 0.80, 1.0), rough=0.4)
    L.add("pit", base=(0.01, 0.01, 0.012), rough=1.0)
    L.add("wall", tex="concrete.png", base=(0.12, 0.12, 0.13), rough=0.85, tt=(10, 2))
    L.add("ceiling", base=(0.03, 0.03, 0.035), rough=0.9)
    L.add("panel", tex="strip.png", emtex="strip.png", base=(1, 1, 1), emit=(0.95, 0.93, 0.88), rough=0.5)
    L.add("strip_cool", tex="strip.png", emtex="strip.png", base=(1, 1, 1), emit=(0.35, 0.65, 1.0), rough=0.5)
    L.add("strip_warm", tex="strip.png", emtex="strip.png", base=(1, 1, 1), emit=(1.0, 0.45, 0.18), rough=0.5)
    L.add("sign", tex="gsign.png", emtex="gsign.png", base=(1, 1, 1), emit=(1, 1, 1), rough=0.5, alpha="mask", cutoff=0.3)
    L.add("pool", tex="spot.png", base=(1, 0.97, 0.9), emit=(0.10, 0.10, 0.09), rough=1.0, alpha="blend")
    L.add("tyres", tex="tyres.png", base=(1, 1, 1), rough=0.9)
    L.add("chest", base=(0.62, 0.05, 0.04), metal=0.3, rough=0.35)
    L.add("chest_dark", base=(0.05, 0.05, 0.055), metal=0.4, rough=0.4)
    L.add("paintline", base=(0.85, 0.70, 0.10), rough=0.7)
    parts = []
    # floor: annulus around the turntable pit
    m = Mesh()
    R0, R1, segs = 2.95, 26.0, 64
    rings = []
    for k, r in enumerate((R0, 4.5, 8.0, 14.0, R1)):
        row = []
        for s in range(segs):
            a = 2 * PI * s / segs
            x, z = r * math.cos(a), r * math.sin(a)
            row.append(m.v((x, 0.0, z), (0, 1, 0), (x / 4, z / 4)))
        rings.append(row)
    for k in range(len(rings) - 1):
        for s in range(segs):
            s2 = (s + 1) % segs
            m.quad(rings[k][s], rings[k][s2], rings[k + 1][s2], rings[k + 1][s])
    parts.append(shape(L, "floor", m.its(dp=3, dt=3)))
    # pit walls and floor (seen through the glossy turntable top, behind the reflection)
    pit = Mesh()
    rows = []
    for s in range(segs + 1):
        a = 2 * PI * s / segs
        ca, sa = math.cos(a), math.sin(a)
        rows.append((pit.v((R0 * ca, 0.0, R0 * sa), (-ca, 0, -sa)), pit.v((R0 * ca, -1.8, R0 * sa), (-ca, 0, -sa))))
    for s in range(segs):
        pit.quad(rows[s][0], rows[s + 1][0], rows[s + 1][1], rows[s][1])
    bot = [pit.v((R0 * math.cos(2 * PI * s / segs), -1.8, R0 * math.sin(2 * PI * s / segs)), (0, 1, 0)) for s in range(segs)]
    cb = pit.v((0, -1.8, 0), (0, 1, 0))
    for s in range(segs):
        pit.tri(cb, bot[s], bot[(s + 1) % segs])
    parts.append(shape(L, "pit", pit.its(dp=3)))
    # turntable: glossy top (semi-transparent over the reflection), metal rim, LED ring
    top = Mesh()
    rt = 2.92
    ring_ids = [top.v((rt * math.cos(2 * PI * s / segs), 0.08, rt * math.sin(2 * PI * s / segs)), (0, 1, 0)) for s in range(segs)]
    c0 = top.v((0, 0.08, 0), (0, 1, 0))
    for s in range(segs):
        top.tri(c0, ring_ids[(s + 1) % segs], ring_ids[s])
    rim = Mesh()
    rim.lathe([(2.95, -0.02), (2.95, 0.07), (2.93, 0.085), (2.90, 0.085)], segs, axis="y")
    led = Mesh()
    led.lathe([(2.955, 0.035), (2.955, 0.055)], segs, axis="y")
    parts += [shape(L, "tt_rim", rim.ifs(crease=0.6)), shape(L, "led", led.its(dp=3))]
    # room: a curved cyclorama wall, ceiling, light panels, strips
    wall = Mesh()
    wall.lathe([(14.0, 0.0), (14.0, 7.5)], 72, axis="y")
    # flip to face inward
    wall.n = [(-n[0], -n[1], -n[2]) for n in wall.n]
    wall.idx = []
    nprof = 2
    for s in range(72):
        a = s * (nprof)
        b = (s + 1) * nprof
        wall.quad(a, b, b + 1, a + 1)
    parts.append(shape(L, "wall", wall.its(dp=2, dt=3)))
    ceil = Mesh()
    ids = [ceil.v((-15, 7.5, -15), (0, -1, 0)), ceil.v((15, 7.5, -15), (0, -1, 0)), ceil.v((15, 7.5, 15), (0, -1, 0)), ceil.v((-15, 7.5, 15), (0, -1, 0))]
    ceil.quad(*ids)
    parts.append(shape(L, "ceiling", ceil.its(dp=1, dt=0)))
    pan = Mesh()
    for k in range(5):
        z = -2.4 + 1.2 * k
        ids = [pan.v((-2.6, 6.2, z - 0.18), (0, -1, 0), (0, 0)), pan.v((2.6, 6.2, z - 0.18), (0, -1, 0), (4, 0)),
               pan.v((2.6, 6.2, z + 0.18), (0, -1, 0), (4, 1)), pan.v((-2.6, 6.2, z + 0.18), (0, -1, 0), (0, 1))]
        pan.quad(*ids)
    parts.append(shape(L, "panel", pan.its(dp=2)))
    cool, warm = Mesh(), Mesh()
    for k in range(18):
        a = PI * 0.15 + (PI * 0.7) * k / 17 + PI
        ca, sa = math.cos(a), math.sin(a)
        r = 13.9
        tg = (-sa, 0, ca)
        mm = cool if k % 3 else warm
        p0 = (r * ca - tg[0] * 0.06, 0.3, r * sa - tg[2] * 0.06)
        p1 = (r * ca + tg[0] * 0.06, 0.3, r * sa + tg[2] * 0.06)
        n = (-ca, 0, -sa)
        ids = [mm.v(p0, n, (0, 0)), mm.v(p1, n, (0, 1)), mm.v((p1[0], 5.6, p1[2]), n, (6, 1)), mm.v((p0[0], 5.6, p0[2]), n, (6, 0))]
        mm.quad(*ids)
    parts += [shape(L, "strip_cool", cool.its(dp=2)), shape(L, "strip_warm", warm.its(dp=2))]
    # sign on the back wall
    sg = Mesh()
    zc = -13.6
    ids = [sg.v((-3.6, 3.1, zc), (0, 0, 1), (0, 0)), sg.v((3.6, 3.1, zc), (0, 0, 1), (1, 0)),
           sg.v((3.6, 4.9, zc), (0, 0, 1), (1, 1)), sg.v((-3.6, 4.9, zc), (0, 0, 1), (0, 1))]
    sg.quad(*ids)
    parts.append(shape(L, "sign", sg.its(dp=2)))
    # floor pools and paint lines
    pools = Mesh()
    for (x, z, s) in ((-6.5, -6.0, 4.0), (6.5, -6.0, 4.0)):
        ids = [pools.v((x - s / 2, 0.006, z - s / 2), (0, 1, 0), (0, 0)), pools.v((x + s / 2, 0.006, z - s / 2), (0, 1, 0), (1, 0)),
               pools.v((x + s / 2, 0.006, z + s / 2), (0, 1, 0), (1, 1)), pools.v((x - s / 2, 0.006, z + s / 2), (0, 1, 0), (0, 1))]
        pools.quad(*ids)
    parts.append(shape(L, "pool", pools.its(dp=3)))
    lines = Mesh()
    for r0, r1 in ((3.25, 3.31), (3.42, 3.45)):
        lines.lathe([(r1, 0.004), (r0, 0.004)], segs, axis="y")
    parts.append(shape(L, "paintline", lines.its(dp=3)))
    # props: tyre stacks and a tool chest near the walls
    props = Mesh(normals=True)
    for (x, z, h) in ((-8.5, -7.5, 1.6), (-7.6, -8.6, 1.2), (8.2, -8.0, 1.4), (9.0, -6.6, 0.9)):
        props.box((x, h / 2, z), (0.75, h, 0.75), uvscale=1.0)
    parts.append(shape(L, "tyres", props.its(dp=2)))
    ch = Mesh(normals=True)
    ch.box((-10.4, 0.55, -2.0), (0.6, 1.1, 1.6), 0.25)
    parts.append(shape(L, "chest", ch.its(dp=2, dt=2)))
    chd = Mesh(normals=True)
    for k in range(5):
        chd.box((-10.08, 0.18 + 0.2 * k, -2.0), (0.02, 0.012, 1.4), 0.25)
    parts.append(shape(L, "chest_dark", chd.its(dp=3, dt=2)))

    lights_main = ("<DirectionalLight DEF='Key' global='false' direction='-0.30 -0.86 -0.42' color='1 0.97 0.92' intensity='2.0' shadows='true' shadowIntensity='0.65'/>"
                   "<SpotLight DEF='RimCool' global='false' location='-5.5 4.5 -5.0' direction='0.62 -0.5 0.6' color='0.55 0.75 1' intensity='3.0' beamWidth='0.45' cutOffAngle='0.75' radius='30'/>"
                   "<SpotLight DEF='RimWarm' global='false' location='5.5 3.8 -4.5' direction='-0.66 -0.44 0.6' color='1 0.62 0.35' intensity='1.8' beamWidth='0.35' cutOffAngle='0.6' radius='30'/>"
                   "<DirectionalLight DEF='Fill' global='false' direction='0.3 -0.25 0.9' color='0.75 0.82 1' intensity='0.55'/>"
                   "<DirectionalLight DEF='Front' global='false' direction='-0.1 -0.35 -0.93' color='1 1 1' intensity='0.6'/>"
                   "<DirectionalLight DEF='Floor' global='false' direction='0 1 0' color='0.6 0.65 0.75' intensity='0.18'/>")
    # the reflection is lit by mirrored copies of the car lights (scoped to the mirror only)
    lights_mirror = ("<DirectionalLight global='false' direction='-0.35 -0.82 -0.45' color='1 0.97 0.92' intensity='1.2'/>"
                     "<DirectionalLight global='false' direction='0.3 -0.25 0.9' color='0.75 0.82 1' intensity='0.4'/>"
                     "<DirectionalLight global='false' direction='-0.1 -0.35 -0.93' color='1 1 1' intensity='0.4'/>")
    cams = []
    from kx3d import look_rotation, rot_str
    for name, eye, tgt, desc in GARAGE_CAMS:
        cams.append(f"<Viewpoint DEF='{name}' description='{esc(desc)}' position='{vec(*eye)}' orientation='{rot_str(look_rotation(eye, tgt))}' fieldOfView='0.62'/>")
    body = ("<WorldInfo DEF='GarageInfo' title='KANSEI showroom'><MetadataSet name='kansei:garage' containerField='metadata'>"
            "<MetadataString name='slot' value='\"CarSlot\"' containerField='value'/>"
            "<MetadataString name='turntable' value='\"Turntable\"' containerField='value'/>"
            f"<MetadataInteger name='cams' value='{len(GARAGE_CAMS)}' containerField='value'/></MetadataSet></WorldInfo>"
            "<NavigationInfo DEF='Nav' type='\"NONE\"' transitionType='\"TELEPORT\"' headlight='false' visibilityLimit='200'/>"
            + "".join(cams) +
            "<Background DEF='Sky' skyColor='0.012 0.013 0.018' groundColor='0.012 0.013 0.018'/>"
            "<Fog DEF='Haze' color='0.012 0.013 0.018' visibilityRange='42' fogType='EXPONENTIAL'/>"
            "<Group DEF='Room'>" + lights_main + "".join(parts)
            + "<Shape castShadow='false'>" + L.look("tt_top") + top.its(dp=3) + "</Shape>"
            + "<Transform DEF='Turntable' translation='0 0.08 0'><Group DEF='CarSlot'><MetadataString name='kansei:slot' value='\"car\"' containerField='metadata'/></Group></Transform>"
            "</Group>"
            "<Transform DEF='Reflection' translation='0 0.16 0' scale='1 -1 1'>" + lights_mirror + "<Transform USE='Turntable'/></Transform>")
    doc = x3d_doc("KANSEI showroom", "KANSEI menu backdrop: a dark showroom with a turntable (DEF Turntable) holding the car slot (DEF CarSlot), soft key and rim lights, a glossy floor with a mirrored reflection of the car.",
                  [("Shape", 2), ("Texturing", 2), ("Lighting", 3), ("EnvironmentalEffects", 3), ("Navigation", 2)], body, "x3d.drift/build/build_world.py")
    return doc
