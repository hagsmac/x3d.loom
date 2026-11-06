"""KANSEI scenery: road surfaces, barriers, terrain, vegetation, skylines, gantries.

Everything that touches the road is built from Circuit samples (ktrack.Circuit), never from
the design polygon, so paint, kerbs, walls and the driving surface line up with the contract.
Static shapes are written with castShadow='false': the sun's shadow map then fits the cars
the page adds (X_ITE fits a directional shadow to the casters' bounding box).
"""
from __future__ import annotations

import math

import numpy as np

from kx3d import Mesh, RNG, fnum, shape, vec
from ktrack import CURB_BAND, Circuit, periodic_smooth, ribbon, runs, span, sweep_profile


# --------------------------------------------------------------------------------------------
# road surfaces

def road_surfaces(c: Circuit, L, st: dict) -> list[str]:
    """Asphalt, kerbs or gutters in the contract band, verges to the walls, paint, rubber."""
    out = []
    n = c.n
    allidx = list(range(n))
    hw = lambda i: float(c.hw[i])
    tile = st.get("asphalt_tile", 4.2)
    # asphalt: u across in metres / tile, v along
    m2 = Mesh()
    _ribbon_u(c, m2, allidx, [lambda i: -hw(i), lambda i: hw(i)], lambda i: (-hw(i) / tile, hw(i) / tile), 1.0 / tile, close=True)
    out.append(shape(L, st["asphalt"], m2.its()))

    # the contract band (halfWidth .. halfWidth + 1.2): kerbs at corners, gutter/shoulder elsewhere
    curb_mask_l = np.zeros(n, bool)
    curb_mask_r = np.zeros(n, bool)
    mode = st.get("curbs", "corners")
    if mode == "all":
        curb_mask_l[:] = True
        curb_mask_r[:] = True
    elif mode == "corners":
        for a, apex, b, sgn in c.corners(st.get("curb_k", 1 / 90.0), 5):
            ln = (b - a) % n
            pre = st.get("curb_pre", 6)
            post = st.get("curb_post", 10)
            inner = span(c, (a - pre // 2) % n, (b + 2) % n)
            outer = span(c, (apex) % n, (b + post) % n)
            for i in inner:
                (curb_mask_l if sgn > 0 else curb_mask_r)[i] = True
            if st.get("outer_curbs", True):
                for i in outer:
                    (curb_mask_r if sgn > 0 else curb_mask_l)[i] = True
    for side, mask in ((1, curb_mask_l), (-1, curb_mask_r)):
        for a, b in runs(list(mask)):
            idx = span(c, a, (b + 1) % n)
            cm = Mesh()
            prof = [lambda i, s=side: s * hw(i), lambda i, s=side: (s * (hw(i) + 0.25), 0.035),
                    lambda i, s=side: (s * (hw(i) + 0.95), 0.035), lambda i, s=side: (s * (hw(i) + CURB_BAND), 0.0)]
            _ribbon_u(c, cm, idx, prof, lambda i: (0.0, 0.2, 0.8, 1.0), 1.0 / st.get("curb_len", 2.0))
            out.append(shape(L, st["curb"], cm.ifs(crease=0.9, dp=2, dt=2)))
        for a, b in runs(list(~mask)):
            idx = span(c, a, (b + 1) % n)
            gm = Mesh()
            _ribbon_u(c, gm, idx, [lambda i, s=side: s * hw(i), lambda i, s=side: s * (hw(i) + CURB_BAND)],
                      lambda i: (0.0, CURB_BAND / 2.0), 1.0 / 2.0, dec=3)
            out.append(shape(L, st["band"], gm.ifs(crease=1.0, dp=2, dt=2)))
    # verge: band edge to the wall line (+ a little past it), the runoff surface
    vm = Mesh()
    for side, w in ((1, c.wl), (-1, c.wr)):
        past = st.get("verge_past", 1.5)
        _ribbon_u(c, vm, allidx, [lambda i, s=side: s * (hw(i) + CURB_BAND),
                                  lambda i, s=side, w=w: s * (float(w[i]) + past)],
                  lambda i, w=w: (0.0, (float(w[i]) + past - hw(i) - CURB_BAND) / 4.0), 1.0 / 4.0, close=True, dec=3)
    out.append(shape(L, st["verge"], vm.ifs(crease=1.0, dp=2, dt=2)))

    # paint: edge lines
    pm = Mesh()
    ew = st.get("edge_w", 0.15)
    ei = st.get("edge_in", 0.25)
    if st.get("edge_lines", True):
        for side in (1, -1):
            _ribbon_u(c, pm, allidx, [lambda i, s=side: s * (hw(i) - ei - ew), lambda i, s=side: s * (hw(i) - ei)],
                      lambda i: (0.0, 1.0), 1.0 / 3.0, lift=0.012, close=True, dec=3)
    # lane lines (dashed): offsets as fractions of the half width
    for frac in st.get("lane_fracs", []):
        dash, gap = st.get("dash", (2, 3))
        for i in range(0, n, dash + gap):
            idx = [i % n, (i + dash) % n]
            _ribbon_u(c, pm, idx, [lambda i, f=frac: f * hw(i) - 0.075, lambda i, f=frac: f * hw(i) + 0.075],
                      lambda i: (0.0, 1.0), 1.0 / 3.0, lift=0.012)
    if pm.idx:
        out.append(shape(L, st.get("paint", "paint"), pm.ifs(crease=1.0, dp=2, dt=2)))
    if st.get("centre") == "double":
        ym = Mesh()
        for off in (-0.16, 0.16):
            _ribbon_u(c, ym, allidx, [lambda i, o=off: o - 0.06, lambda i, o=off: o + 0.06],
                      lambda i: (0.0, 1.0), 1.0 / 3.0, lift=0.012, close=True, dec=3)
        out.append(shape(L, st.get("centre_paint", "paint_y"), ym.ifs(crease=1.0, dp=2, dt=2)))

    # racing-line rubber (alpha)
    if st.get("wear", True):
        wm = Mesh()
        half = st.get("wear_half", 1.25)
        _ribbon_u(c, wm, allidx, [lambda i: float(c.racing[i]) - half, lambda i: float(c.racing[i]) + half],
                  lambda i: (0.0, 1.0), 1.0 / 9.0, lift=0.007, close=True, dec=2)
        out.append(shape(L, "wear", wm.ifs(crease=1.0, dp=2, dt=2)))
    # old drift marks through the corners (alpha)
    if st.get("skids", True):
        sm = Mesh()
        rng = RNG(st.get("seed", 1) * 7 + 3)
        for a, apex, b, sgn in c.corners(1 / 110.0, 8):
            for rep in range(2):
                i0 = (a - 4 + rng.i(4)) % n
                ln = ((b - a) % n) + 10
                idx = [(i0 + k) % n for k in range(ln)]
                amp = rng.r(0.5, 0.8) * hw(apex)
                base = rng.r(-0.15, 0.15) * hw(apex)
                def off(i, i0=i0, ln=ln, amp=amp, base=base, sgn=sgn):
                    f = ((i - i0) % n) / max(1, ln - 1)
                    return base + sgn * amp * math.sin(math.pi * f) * 0.9 - sgn * amp * 0.35
                _ribbon_u(c, sm, idx, [lambda i, o=off: o(i) - 0.85, lambda i, o=off: o(i) + 0.85],
                          lambda i: (0.0, 1.0), 1.0 / 7.0, lift=0.009)
        if sm.idx:
            out.append(shape(L, "skids", sm.ifs(crease=1.0, dp=2, dt=2)))
    # start/finish checker band and grid boxes
    ck = Mesh()
    _ribbon_u(c, ck, [n - 1, 0, 1], [lambda i: -hw(i), lambda i: hw(i)], lambda i: (0.0, 2 * hw(i) / 2.0), 1.0 / 2.0, lift=0.014)
    out.append(shape(L, "checker", ck.its()))
    gm = Mesh()
    for (gx, gz, gyaw) in c.grid():
        _grid_box(c, gm, gx, gz, gyaw)
    out.append(shape(L, st.get("paint", "paint"), gm.its()))
    return out


def decimate(c: Circuit, idx, k_keep: float = 1 / 120.0, every: int = 3, close: bool = False):
    """Keep every sample on curves, every `every`-th on straights (endpoints always kept)."""
    if len(idx) <= 2:
        return list(idx)
    keep = []
    last = -999
    for j, i in enumerate(idx):
        if j == 0 or j == len(idx) - 1 or abs(float(c.ks[i])) > k_keep or j - last >= every:
            keep.append(i)
            last = j
    return keep


def _ribbon_u(c: Circuit, mesh: Mesh, idx, cols, ufn, v_scale, lift=0.0, close=False, dec: int = 1):
    """ribbon() with a per-sample u for each column (ufn(i) -> tuple)."""
    if dec > 1:
        idx = decimate(c, idx + ([idx[0]] if close else []), every=dec)
        close = False
    seq = idx + ([idx[0]] if close else [])
    rows = []
    prev, v = None, 0.0
    for i in seq:
        if prev is not None:
            v += math.dist((c.x[prev], c.y[prev], c.z[prev]), (c.x[i], c.y[i], c.z[i]))
        prev = i
        us = ufn(i)
        nn = c.nrm(i)
        ids = []
        for j, cf in enumerate(cols):
            r = cf(i)
            d, dy = (r if isinstance(r, tuple) else (r, 0.0))
            ids.append(mesh.v(c.pt(i, d, dy + lift), nn, (us[j], v * v_scale)))
        rows.append(ids)
    for a in range(len(rows) - 1):
        for j in range(len(rows[a]) - 1):
            mesh.quad(rows[a][j], rows[a + 1][j], rows[a + 1][j + 1], rows[a][j + 1])


def _grid_box(c: Circuit, m: Mesh, x, z, yaw):
    """Painted grid slot: a bracket in front of the slot."""
    fx, fz = math.sin(yaw), math.cos(yaw)
    lx, lz = fz, -fx
    (p, _, fi) = c.at_s(0)
    # height from the nearest sample plane
    d2 = (c.x - x) ** 2 + (c.z - z) ** 2
    i = int(np.argmin(d2))
    lat = (x - c.x[i]) * c.lx[i] + (z - c.z[i]) * c.lz[i]
    y = c.y[i] + lat * c.tanb[i] + 0.013
    nn = c.nrm(i)

    def q(a0, b0, a1, b1):
        # rectangle in slot frame: a = lateral, b = forward
        pts = [(x + lx * a + fx * b, y, z + lz * a + fz * b) for a, b in ((a0, b0), (a1, b0), (a1, b1), (a0, b1))]
        ids = [m.v(p_, nn, (0, 0)) for p_ in pts]
        m.quad(*ids)
    q(-1.4, 2.6, 1.4, 2.8)          # front bar
    q(-1.4, 1.4, -1.25, 2.8)        # left leg
    q(1.25, 1.4, 1.4, 2.8)          # right leg


# --------------------------------------------------------------------------------------------
# barriers

# barrier cross-sections (o outward from the wall line, h up); IFS creaseAngle makes the sharp edges
GUARDRAIL = [(0.04, 0.46), (0.0, 0.53), (0.045, 0.63), (0.0, 0.73), (0.04, 0.80), (0.09, 0.80), (0.09, 0.46)]
JERSEY = [(0.0, 0.0), (0.05, 0.08), (0.20, 0.30), (0.25, 0.82), (0.45, 0.82), (0.72, 0.0)]
RETAIN = [(0.0, -0.2), (0.0, 1.05), (0.35, 1.05), (0.35, -0.6)]
TYRES = [(0.0, -0.05), (0.0, 0.92), (0.62, 0.92), (0.62, 0.0)]
STONE = [(0.0, -0.1), (0.0, 0.80), (0.04, 0.88), (0.46, 0.88), (0.5, 0.80), (0.5, -0.4)]


def barriers(c: Circuit, L, kinds_l, kinds_r, styles: dict) -> list[str]:
    """kinds_l/r: per-sample barrier style names. styles[name] = dict(profile, look, u_scale, posts)."""
    out = []
    n = c.n
    for side, kinds, walls in ((1, kinds_l, c.wl), (-1, kinds_r, c.wr)):
        names = sorted(set(kinds))
        for name in names:
            if name is None or name == "none":
                continue
            stl = styles[name]
            mesh = Mesh()
            posts = Mesh()
            mask = [k == name for k in kinds]
            for a, b in runs(mask):
                idx = span(c, a, (b + 1) % n) if not all(mask) else list(range(n))
                closed = all(mask)
                didx = decimate(c, idx + ([idx[0]] if closed else []), k_keep=1 / 70.0, every=3)
                sweep_profile(c, mesh, didx, side, lambda i, w=walls: float(w[i]), stl["profile"], stl.get("u_scale", 0.25),
                              stl.get("v_scale", 1.0), close=False)
                if stl.get("posts"):
                    every = stl["posts"]
                    for i in idx[::every]:
                        wd = float(walls[i]) + stl.get("post_o", 0.16)
                        p = c.pt(i, side * wd)
                        y0 = c.y[i] + side * float(walls[i]) * c.tanb[i]
                        post_box(posts, (p[0], y0 + 0.36, p[2]), (0.1, 0.9, 0.16), c.yaw(i))
            out.append(shape(L, stl["look"], mesh.ifs(crease=stl.get("crease", 0.8), dp=2, dt=2)))
            if posts.idx:
                out.append(shape(L, stl.get("post_look", "post"), posts.ifs(crease=0.0, dp=2, dt=1)))
    return out


def post_box(m: Mesh, center, size, yaw: float):
    """Compact box (8 shared corners, no bottom) for IFS output with flat browser normals."""
    cx, cy, cz = center
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    ca, sa = math.cos(yaw), math.sin(yaw)
    ids = []
    for (x, y, z) in ((-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz), (-hx, hy, -hz), (hx, hy, -hz), (hx, hy, hz), (-hx, hy, hz)):
        n = (x, y, z)
        ids.append(m.v((cx + x * ca + z * sa, cy + y, cz - x * sa + z * ca), (n[0] * ca + n[2] * sa, n[1], -n[0] * sa + n[2] * ca), (0, 0)))
    for a, b, c_, d in ((0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)):
        m.quad(ids[a], ids[b], ids[c_], ids[d])


# --------------------------------------------------------------------------------------------
# terrain

def nearest_road(c: Circuit, px: np.ndarray, pz: np.ndarray):
    """For points, the nearest sample index, its lateral offset (signed) and the planar distance."""
    best_d = np.full(px.shape, 1e18)
    best_i = np.zeros(px.shape, dtype=np.int64)
    for i0 in range(0, c.n, 64):
        sl = slice(i0, min(c.n, i0 + 64))
        dx = px[..., None] - c.x[sl]
        dz = pz[..., None] - c.z[sl]
        d2 = dx * dx + dz * dz
        j = np.argmin(d2, axis=-1)
        dm = np.take_along_axis(d2, j[..., None], -1)[..., 0]
        better = dm < best_d
        best_d = np.where(better, dm, best_d)
        best_i = np.where(better, j + i0, best_i)
    lat = (px - c.x[best_i]) * c.lx[best_i] + (pz - c.z[best_i]) * c.lz[best_i]
    return best_i, lat, np.sqrt(best_d)


def road_clamped_height(c: Circuit, natural: np.ndarray, px, pz, extra: float = 3.0, blend: float = 14.0,
                        sink: float = 0.45):
    """Terrain that meets the road: inside the walls (+extra) it sits `sink` below the road plane,
    then blends back to the natural height over `blend` metres."""
    i, lat, dist = nearest_road(c, px, pz)
    wall = np.where(lat > 0, c.wl[i], c.wr[i])
    road_y = c.y[i] + lat * c.tanb[i] - sink
    edge = wall + extra
    t = np.clip((np.abs(lat) - edge) / blend, 0, 1)
    t = t * t * (3 - 2 * t)
    h = road_y * (1 - t) + natural * t
    return h, i, lat, dist, t


def elevation_grid(L, look: str, x0: float, z0: float, nx: int, nz: int, sp: float, H: np.ndarray, colors: np.ndarray | None,
                   crease: float = 1.2) -> str:
    hs = " ".join(fnum(v, 1) for v in H.reshape(-1))
    col = ""
    if colors is not None:
        col = "<Color color='" + " ".join(f"{fnum(r, 2)} {fnum(g, 2)} {fnum(b, 2)}" for r, g, b in colors.reshape(-1, 3)) + "'/>"
    geom = (f"<ElevationGrid xDimension='{nx}' zDimension='{nz}' xSpacing='{fnum(sp, 3)}' zSpacing='{fnum(sp, 3)}' "
            f"creaseAngle='{fnum(crease, 2)}' solid='true' height='{hs}'>{col}</ElevationGrid>")
    return f"<Transform translation='{vec(x0, 0, z0)}'>" + shape(L, look, geom) + "</Transform>"


# --------------------------------------------------------------------------------------------
# vegetation (alpha-tested crossed billboards, clustered for culling)

def billboard_trees(L, look: str, items, tile: float = 120.0) -> list[str]:
    """items: (x, y, z, height, width, yaw). Two crossed quads per tree, grouped in tiles.

    Foliage normals: each card is written with both windings (solid, so no back-face normal flip),
    and its vertex normals lean up and outward from the trunk, so the crown shades like a rounded
    volume from either side instead of one side going black."""
    tiles: dict[tuple[int, int], Mesh] = {}
    for (x, y, z, h, w, yaw) in items:
        key = (int(math.floor(x / tile)), int(math.floor(z / tile)))
        m = tiles.setdefault(key, Mesh())
        for k in range(2):
            a = yaw + k * math.pi / 2
            ca, sa = math.cos(a), math.sin(a)
            hx, hz = ca * w / 2, -sa * w / 2
            nl, nr = (-ca * 0.6, 0.8, sa * 0.6), (ca * 0.6, 0.8, -sa * 0.6)
            b = [m.v((x - hx, y - 0.3, z - hz), nl, (0, 0)), m.v((x + hx, y - 0.3, z + hz), nr, (1, 0)),
                 m.v((x + hx, y + h, z + hz), nr, (1, 1)), m.v((x - hx, y + h, z - hz), nl, (0, 1))]
            m.idx.extend((b[0], b[1], b[2], b[0], b[2], b[3], b[0], b[2], b[1], b[0], b[3], b[2]))
    out = []
    for key in sorted(tiles):
        out.append(shape(L, look, tiles[key].its(solid=True, dp=1, dn=1, dt=0)))
    return out


# --------------------------------------------------------------------------------------------
# distant ranges

def ridge_ring(L, look: str, center, r0: float, r1: float, h_lo: float, h_hi: float, seed: int, base_y: float,
               segs: int = 180, sharp: float = 1.0, arc=None, colors=None) -> str:
    """A ring of mountains between radii r0..r1 (front face, crest, back face), vertex coloured."""
    rs = np.random.RandomState(seed)
    k = np.arange(segs + 1)
    t = k / segs
    prof = np.zeros(segs + 1)
    for octave in range(5):
        f = 2 ** octave * 3
        ph = rs.random_sample() * 2 * math.pi
        prof += np.sin(t * 2 * math.pi * f + ph) / (1.6 ** octave) * (0.5 + rs.random_sample())
        prof += np.abs(np.sin(t * 2 * math.pi * f * 1.7 + ph * 2)) / (2 ** octave) * sharp
    prof = (prof - prof.min()) / (prof.max() - prof.min())
    heights = h_lo + (h_hi - h_lo) * prof
    a0, a1 = (0.0, 2 * math.pi) if arc is None else arc
    m = Mesh(normals=True, uv=False, colors=colors is not None)
    cx, cz = center
    rows = []
    for j in range(segs + 1):
        a = a0 + (a1 - a0) * j / segs
        ca, sa = math.cos(a), math.sin(a)
        rm = (r0 + r1) / 2 + (r1 - r0) * 0.25 * math.sin(j * 0.37)
        hgt = heights[j]
        pts = [(r0, base_y), (rm - hgt * 0.35, base_y + hgt * 0.75), (rm, base_y + hgt), (rm + hgt * 0.5, base_y + hgt * 0.6), (r1, base_y)]
        row = []
        for q, (rr, yy) in enumerate(pts):
            p = (cx + ca * rr, yy, cz + sa * rr)
            nrm = (-ca * 0.6, 0.8, -sa * 0.6) if q <= 2 else (ca * 0.6, 0.8, sa * 0.6)
            c = None
            if colors is not None:
                lo, hi = colors
                f = (yy - base_y) / max(1.0, h_hi)
                c = tuple(lo[u] + (hi[u] - lo[u]) * min(1, f * 1.2) for u in range(3))
            row.append(m.v(p, nrm, None, c))
        rows.append(row)
    for j in range(segs):
        for q in range(4):
            m.quad(rows[j][q], rows[j][q + 1], rows[j + 1][q + 1], rows[j + 1][q])
    return shape(L, look, m.ifs(crease=0.9, dp=1))


# --------------------------------------------------------------------------------------------
# start gantry, signs, posts

def gantry(c: Circuit, L, banner_look: str, frame_look: str, light_look: str, span_extra: float = 1.8, height: float = 6.2) -> list[str]:
    i = 0
    hw = float(c.hw[i])
    yaw = c.yaw(i)
    m = Mesh()
    lights = Mesh()
    for side in (1, -1):
        d = side * (min(float(c.wl[i]), float(c.wr[i])) + 0.4) if False else side * (float(c.wl[i] if side > 0 else c.wr[i]) + 0.45)
        p = c.pt(i, d)
        m.box((p[0], p[1] + height / 2, p[2]), (0.45, height, 0.45), yaw)
    pl = c.pt(i, float(c.wl[i]) + 0.45)
    pr = c.pt(i, -(float(c.wr[i]) + 0.45))
    cx, cz = (pl[0] + pr[0]) / 2, (pl[2] + pr[2]) / 2
    cy = (pl[1] + pr[1]) / 2 + height
    width = math.dist((pl[0], pl[2]), (pr[0], pr[2]))
    m.box((cx, cy + 0.15, cz), (width + 0.5, 0.3, 0.5), yaw)
    m.box((cx, cy - 1.75, cz), (width + 0.5, 0.2, 0.4), yaw)
    # banner (both faces), uv 0..1
    b = Mesh()
    fx, fz = math.sin(yaw), math.cos(yaw)
    lx, lz = fz, -fx
    for face in (1, -1):
        off = face * 0.21
        w2 = width / 2
        pts = [(cx - lx * w2 * face + fx * off, cy - 1.65, cz - lz * w2 * face + fz * off),
               (cx + lx * w2 * face + fx * off, cy - 1.65, cz + lz * w2 * face + fz * off),
               (cx + lx * w2 * face + fx * off, cy - 0.05, cz + lz * w2 * face + fz * off),
               (cx - lx * w2 * face + fx * off, cy - 0.05, cz - lz * w2 * face + fz * off)]
        nn = (-fx * face, 0, -fz * face)
        ids = [b.v(p, nn, uv) for p, uv in zip(pts, ((1, 0), (0, 0), (0, 1), (1, 1)) if face > 0 else ((0, 0), (1, 0), (1, 1), (0, 1)))]
        b.quad(*ids)
    # start lights: 5 lamp pods under the beam
    for k in range(5):
        a = (k - 2) * 0.9
        lights.box((cx + lx * a, cy - 2.15, cz + lz * a), (0.5, 0.5, 0.3), yaw)
    return [shape(L, frame_look, m.its()), shape(L, banner_look, b.its()), shape(L, light_look, lights.its())]


def chevrons(c: Circuit, L, look: str, post_look: str, k_min: float = 1 / 45.0, every: int = 5, h: float = 0.9) -> list[str]:
    """Chevron boards on the outside wall through tight corners, facing the driver."""
    m = Mesh()
    p = Mesh()
    for a, apex, b, sgn in c.corners(k_min, 5):
        side = -sgn  # outside
        walls = c.wr if side < 0 else c.wl
        for i in span(c, (a - 3) % c.n, (b + 3) % c.n)[::every]:
            wd = float(walls[i]) + 0.45
            base = c.pt(i, side * wd)
            y0 = c.y[i] + side * float(walls[i]) * c.tanb[i]
            yaw = c.yaw(i)
            fx, fz = math.sin(yaw), math.cos(yaw)
            lx, lz = fz, -fx
            # board faces back along -forward toward oncoming cars, slightly turned to the road
            w = 1.2
            y1, y2 = y0 + h, y0 + h + 0.6
            cxp, czp = base[0], base[2]
            dirx, dirz = lx * side, lz * side
            pts = [(cxp - fx * 0.0 + dirx * (-w / 2) * 0 - lx * 0, y1, czp), ]
            # simple: quad perpendicular to the road direction
            ax, az = lx * w / 2, lz * w / 2
            q = [(cxp - ax, y1, czp - az), (cxp + ax, y1, czp + az), (cxp + ax, y2, czp + az), (cxp - ax, y2, czp - az)]
            nn = (-fx, 0, -fz)
            uv = [(0, 0), (1, 0), (1, 1), (0, 1)] if sgn > 0 else [(1, 0), (0, 0), (0, 1), (1, 1)]
            ids = [m.v(pt, nn, t) for pt, t in zip(q, uv)]
            m.quad(*ids)
            p.box((cxp, y0 + (h + 0.3) / 2, czp), (0.08, h + 0.3, 0.08), yaw)
    out = []
    if m.idx:
        out.append(shape(L, look, m.its(solid=False)))
        out.append(shape(L, post_look, p.its()))
    return out


def viewpoints(c: Circuit, count: int, seed: int, height=(4.0, 9.0), back=(18.0, 32.0), side_out=(6.0, 14.0)) -> tuple[str, list]:
    """TrackCam0..N at the most dramatic corners: outside the corner, looking at the apex."""
    cs = c.corners(1 / 160.0, 6)
    cs = sorted(cs, key=lambda t: -abs(float(c.ks[t[1]])))
    picks = sorted(cs[:count], key=lambda t: t[1])
    rng = RNG(seed)
    xml, info = [], []
    used = []
    for k, (a, apex, b, sgn) in enumerate(picks):
        side = -sgn
        walls = c.wr if side < 0 else c.wl
        ie = (apex + int(rng.r(6, 14))) % c.n
        off = side * (float(walls[ie]) + rng.r(*side_out))
        eye = c.pt(ie, off, rng.r(*height))
        tgt = c.pt((apex - 4) % c.n, 0.0, 0.8)
        from kx3d import look_rotation, rot_str
        r = look_rotation(eye, tgt)
        desc = f"Corner at {int(c.s[apex])} m"
        xml.append(f"<Viewpoint DEF='TrackCam{k}' description='{desc}' position='{vec(*eye, d=2)}' orientation='{rot_str(r)}' fieldOfView='0.62'/>")
        info.append({"def": f"TrackCam{k}", "sample": int(apex), "s": round(float(c.s[apex]), 1)})
    return "".join(xml), info


# --------------------------------------------------------------------------------------------
# rocks

def _ico():
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
         (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    ln = math.sqrt(1 + t * t)
    return [(a / ln, b / ln, c / ln) for a, b, c in v], f


def boulders(L, look: str, items, crease: float = 0.9) -> str:
    """items: (x, y, z, size, seed). Jittered, flattened icosahedra sunk into the ground."""
    V, F = _ico()
    m = Mesh(normals=False)
    for (x, y, z, sz, seed) in items:
        rng = RNG(seed)
        sx, sy, sz_ = sz * rng.r(0.9, 1.5), sz * rng.r(0.5, 0.9), sz * rng.r(0.8, 1.3)
        yaw = rng.r(0, math.pi)
        ca, sa = math.cos(yaw), math.sin(yaw)
        ids = []
        for (a, b, c) in V:
            j = rng.r(0.78, 1.15)
            px, py, pz = a * sx * j, b * sy * j, c * sz_ * j
            wx, wz = px * ca + pz * sa, -px * sa + pz * ca
            P = (x + wx, y + py - sy * 0.25, z + wz)
            ids.append(m.v(P, (a, b, c), (P[0] / 3.0 + P[1] / 6.0, P[2] / 3.0 + P[1] / 4.0)))
        for f in F:
            m.tri(ids[f[0]], ids[f[1]], ids[f[2]])
    return shape(L, look, m.ifs(crease=crease, dp=2, dt=2))


# --------------------------------------------------------------------------------------------
# generic structures

def tex_box(m: Mesh, x0, x1, y0, y1, z0, z1, u_size: float, v_size: float, u_off: float = 0.0, v_off: float = 0.0,
            top: bool = True, bottom: bool = False):
    """Axis-aligned box with world-scale UVs on the sides (u around, v up) for facades."""
    sides = [((x0, z1), (x1, z1), (0, 0, 1)), ((x1, z1), (x1, z0), (1, 0, 0)), ((x1, z0), (x0, z0), (0, 0, -1)), ((x0, z0), (x0, z1), (-1, 0, 0))]
    u = u_off
    for (a, b, n) in sides:
        w = math.dist(a, b)
        ids = [m.v((a[0], y0, a[1]), n, (u / u_size, (y0 + v_off) / v_size)),
               m.v((b[0], y0, b[1]), n, ((u + w) / u_size, (y0 + v_off) / v_size)),
               m.v((b[0], y1, b[1]), n, ((u + w) / u_size, (y1 + v_off) / v_size)),
               m.v((a[0], y1, a[1]), n, (u / u_size, (y1 + v_off) / v_size))]
        m.quad(*ids)
        u += w
    if top:
        ids = [m.v((x0, y1, z0), (0, 1, 0), (0, 0)), m.v((x1, y1, z0), (0, 1, 0), (0.25, 0)), m.v((x1, y1, z1), (0, 1, 0), (0.25, 0.25)),
               m.v((x0, y1, z1), (0, 1, 0), (0, 0.25))]
        m.quad(*ids)


def far_point_clear(c: Circuit, x: float, z: float, margin: float) -> bool:
    d2 = (c.x - x) ** 2 + (c.z - z) ** 2
    i = int(np.argmin(d2))
    wall = max(float(c.wl[i]), float(c.wr[i]))
    return math.sqrt(float(d2[i])) > wall + margin


def rect_clear(c: Circuit, x0, x1, z0, z1, margin: float) -> bool:
    """Is an axis-aligned rectangle further than margin from the road walls?"""
    cx = np.clip(c.x, x0, x1)
    cz = np.clip(c.z, z0, z1)
    d = np.sqrt((c.x - cx) ** 2 + (c.z - cz) ** 2)
    wall = np.maximum(c.wl, c.wr)
    return bool(np.all(d > wall + margin))


def lathe_shape(L, look, profile, segs, center=(0, 0, 0), crease=1.2) -> str:
    m = Mesh(normals=False)
    m.lathe(profile, segs, center)
    return shape(L, look, m.ifs(crease=crease, dp=2, dt=2))


def ocean_plane(L, look: str, cx, cz, size: float, y: float = 0.0, tile: float = 24.0) -> str:
    m = Mesh()
    h = size / 2
    ids = [m.v((cx - h, y, cz - h), (0, 1, 0), (0, 0)), m.v((cx + h, y, cz - h), (0, 1, 0), (size / tile, 0)),
           m.v((cx + h, y, cz + h), (0, 1, 0), (size / tile, size / tile)), m.v((cx - h, y, cz + h), (0, 1, 0), (0, size / tile))]
    m.quad(*ids)
    return shape(L, look, m.its(dt=1))


def flat_ground(L, look: str, cx, cz, size: float, y: float, tile: float, rings: int = 1) -> str:
    """A big flat square ground with world-scale UVs (subdivided so fog and lighting stay smooth)."""
    m = Mesh()
    k = max(1, rings)
    h = size / 2
    rows = []
    for j in range(k + 1):
        row = []
        for i in range(k + 1):
            x = cx - h + size * i / k
            z = cz - h + size * j / k
            row.append(m.v((x, y, z), (0, 1, 0), (x / tile, z / tile)))
        rows.append(row)
    for j in range(k):
        for i in range(k):
            m.quad(rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i])
    return shape(L, look, m.its(dt=2))


def disc(L, look: str, cx, cz, r0: float, r1: float, y: float, tile: float, segs: int = 96) -> str:
    m = Mesh()
    rows = []
    for rr in (r0, r1):
        row = []
        for s in range(segs + 1):
            a = 2 * math.pi * s / segs
            x, z = cx + rr * math.cos(a), cz + rr * math.sin(a)
            row.append(m.v((x, y, z), (0, 1, 0), (x / tile, z / tile)))
        rows.append(row)
    for s in range(segs):
        m.quad(rows[0][s], rows[0][s + 1], rows[1][s + 1], rows[1][s])
    return shape(L, look, m.its(dt=2))


def street_lamps(c: Circuit, L, every: int, height: float = 9.0, arm: float = 2.6, pool_look: str | None = "lamp_pool",
                 sides=(1, -1), offset: int = 0, pool_size=(12.0, 16.0), on_barrier: float = 0.82, idx_filter=None) -> str:
    """Lamp posts on the wall line with an arm over the road; emissive heads; light pools on the asphalt."""
    poles, heads, pools = Mesh(normals=False), Mesh(), Mesh()
    k = 0
    for i in range(offset, c.n, every):
        if idx_filter is not None and not idx_filter(i):
            continue
        side = sides[k % len(sides)]
        k += 1
        w = float(c.wl[i] if side > 0 else c.wr[i])
        yaw = c.yaw(i)
        base = c.pt(i, side * (w + 0.35))
        y0 = c.y[i] + side * w * c.tanb[i] + on_barrier
        post_box(poles, (base[0], y0 + height / 2, base[2]), (0.22, height, 0.22), yaw)
        tip = c.pt(i, side * (w - arm))
        mx, mz = (base[0] + tip[0]) / 2, (base[2] + tip[2]) / 2
        post_box(poles, (mx, y0 + height - 0.1, mz), (0.12, 0.14, arm + 0.4), yaw + math.pi / 2)
        heads.box((tip[0], y0 + height - 0.28, tip[2]), (0.36, 0.14, 0.9), yaw + math.pi / 2)
        if pool_look:
            lat = side * (w - arm)
            hl, hwid = pool_size[1] / 2, pool_size[0] / 2
            (pc, _yaw) = c.lateral_pt(float(c.s[i]), lat * 0.55, 0.03)
            fx, fz = math.sin(yaw), math.cos(yaw)
            lx, lz = fz, -fx
            yb = c.y[i] + lat * 0.55 * c.tanb[i] + 0.03
            nn = c.nrm(i)
            q = [(pc[0] - lx * hwid - fx * hl, pc[1] - hwid * c.tanb[i], pc[2] - lz * hwid - fz * hl),
                 (pc[0] + lx * hwid - fx * hl, pc[1] + hwid * c.tanb[i], pc[2] + lz * hwid - fz * hl),
                 (pc[0] + lx * hwid + fx * hl, pc[1] + hwid * c.tanb[i], pc[2] + lz * hwid + fz * hl),
                 (pc[0] - lx * hwid + fx * hl, pc[1] - hwid * c.tanb[i], pc[2] - lz * hwid + fz * hl)]
            ids = [pools.v(p_, nn, t) for p_, t in zip(q, ((0, 0), (1, 0), (1, 1), (0, 1)))]
            pools.quad(*ids)
    out = shape(L, "lamp_pole", poles.ifs(crease=0.0, dp=2, dt=1)) + shape(L, "lamp_head", heads.its())
    if pool_look and pools.idx:
        out += shape(L, pool_look, pools.its())
    return out
