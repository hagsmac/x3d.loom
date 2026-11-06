"""KANSEI circuits: centreline design, the contract metadata, and road meshes built from it.

A circuit is a closed polygon whose corners are filleted with circular arcs (exact radii),
lightly smoothed, then resampled about every 2 m. The samples are rounded to the contract's
fixed decimals FIRST; every road mesh below is built from those rounded numbers, so the road
the player sees is the road the simulation reads.

Frames: X3D +Y up, ground X-Z. Forward along increasing sample index t = (tx, tz),
left = (tz, -tx) (the car's +X). Lateral offset d > 0 is left. A banked road is a plane
across: y(d) = y + d * tan(bank); positive bank raises the left edge.
"""
from __future__ import annotations

import math

import numpy as np

from kx3d import Mesh, fnum

SPACING = 2.0
CURB_BAND = 1.2


# --------------------------------------------------------------------------------------------
# centreline design

def fillet_polygon(verts, radii, step: float = 0.5):
    """Dense closed polyline through a polygon whose corners are circular arcs of the given radii."""
    n = len(verts)
    P = [np.array(v, dtype=float) for v in verts]
    arcs = []
    for i in range(n):
        p0, p1, p2 = P[i - 1], P[i], P[(i + 1) % n]
        d1 = (p1 - p0) / np.linalg.norm(p1 - p0)
        d2 = (p2 - p1) / np.linalg.norm(p2 - p1)
        cr = d2[0] * d1[1] - d2[1] * d1[0]          # > 0: a left turn (toward left = (tz, -tx))
        turn = math.atan2(cr, float(d1 @ d2))
        r = radii[i]
        t = r * math.tan(abs(turn) / 2)
        a = p1 - d1 * t
        b = p1 + d2 * t
        left1 = np.array([d1[1], -d1[0]])
        sgn = 1.0 if turn > 0 else -1.0
        c = a + left1 * r * sgn
        arcs.append((a, b, c, r, turn, t))
    for i in range(n):
        t_here = arcs[i][5]
        t_next = arcs[(i + 1) % n][5]
        seg = np.linalg.norm(P[(i + 1) % n] - P[i])
        if t_here + t_next > seg + 1e-6:
            raise ValueError(f"corner {i}/{(i + 1) % n}: fillets need {t_here + t_next:.1f} m, side is {seg:.1f} m")
    pts = []
    for i in range(n):
        a, b, c, r, turn, _ = arcs[i]
        a0 = math.atan2(a[1] - c[1], a[0] - c[0])
        steps = max(2, int(abs(turn) * r / step))
        # the arc turns the heading by `turn`; in (x, z) with left = (z, -x) a left turn is clockwise
        for k in range(steps + 1):
            ang = a0 - turn * k / steps
            pts.append(c + r * np.array([math.cos(ang), math.sin(ang)]))
        nb = arcs[(i + 1) % n][0]
        seg = np.linalg.norm(nb - b)
        m = max(1, int(seg / step))
        for k in range(1, m):
            pts.append(b + (nb - b) * k / m)
    return np.array(pts)


def resample_closed(pts: np.ndarray, spacing: float):
    d = np.linalg.norm(np.roll(pts, -1, 0) - pts, axis=1)
    s = np.concatenate([[0], np.cumsum(d)])
    L = s[-1]
    n = max(8, int(round(L / spacing)))
    ts = np.arange(n) * (L / n)
    closed = np.vstack([pts, pts[:1]])
    out = np.stack([np.interp(ts, s, closed[:, k]) for k in range(pts.shape[1])], -1)
    return out, L


def periodic_smooth(a: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return a.copy()
    n = len(a)
    k = np.arange(n)
    k = np.minimum(k, n - k)
    g = np.exp(-0.5 * (k / sigma) ** 2)
    g /= g.sum()
    G = np.fft.rfft(g)
    if a.ndim == 1:
        return np.fft.irfft(np.fft.rfft(a) * G, n)
    return np.stack([np.fft.irfft(np.fft.rfft(a[:, j]) * G, n) for j in range(a.shape[1])], -1)


def curvature(xz: np.ndarray) -> np.ndarray:
    """Signed curvature per sample (1/m), > 0 for a left turn."""
    nxt = np.roll(xz, -1, 0)
    prv = np.roll(xz, 1, 0)
    t1 = xz - prv
    t2 = nxt - xz
    h1 = np.arctan2(t1[:, 0], t1[:, 1])
    h2 = np.arctan2(t2[:, 0], t2[:, 1])
    dh = (h2 - h1 + math.pi) % (2 * math.pi) - math.pi      # yaw change (yaw grows turning left)
    ds = 0.5 * (np.linalg.norm(t1, axis=1) + np.linalg.norm(t2, axis=1))
    return dh / ds


# --------------------------------------------------------------------------------------------
# the circuit

class Circuit:
    """Holds the rounded samples (the contract) and everything derived from them."""

    def __init__(self, spec: dict):
        self.spec = spec
        dense = fillet_polygon(spec["poly"], spec["radii"])
        xz, _ = resample_closed(dense, 0.5)
        xz = periodic_smooth(xz, spec.get("smooth", 6.0))
        xz, L = resample_closed(xz, SPACING)
        # choose sample 0: the given start fraction along the loop (or the middle of the longest straight)
        n = len(xz)
        k = curvature(xz)
        start = spec.get("start")
        if start is None:
            ks = periodic_smooth(np.abs(k), 3.0)
            straight = ks < spec.get("straight_k", 0.004)
            best, best_len, run, run_start = 0, 0, 0, 0
            for i in range(2 * n):
                if straight[i % n]:
                    if run == 0:
                        run_start = i
                    run += 1
                    if run > best_len and run <= n:
                        best_len, best = run, run_start
                else:
                    run = 0
            start = (best + int(best_len * spec.get("start_at", 0.62))) % n
        else:
            start = int(start * n) % n
        xz = np.roll(xz, -start, 0)
        if spec.get("reverse"):
            xz = xz[::-1].copy()
            xz = np.roll(xz, 1, 0)
        self.n = n
        self.L = L
        k = curvature(xz)
        self.k_raw = k
        ks = periodic_smooth(k, 4.0)
        # elevation
        y = spec["height"](xz) if callable(spec.get("height")) else np.zeros(n)
        y = periodic_smooth(np.asarray(y, dtype=float), spec.get("height_smooth", 14.0))
        # bank: proper banking raises the outside edge (left turn -> right edge up -> negative bank)
        bank = -np.clip(ks * spec.get("bank_gain", 0.0), -spec.get("bank_max", 0.0), spec.get("bank_max", 0.0))
        bank = periodic_smooth(bank, 6.0)
        hw = spec["half_width"](np.arange(n), ks) if callable(spec["half_width"]) else np.full(n, float(spec["half_width"]))
        hw = periodic_smooth(hw, 8.0)
        wl, wr = spec["walls"](self, np.arange(n), ks, hw)
        R = 1.0 / np.maximum(np.abs(ks), 1e-6)
        inside_left = ks > 0
        cap = 0.82 * R
        wl = np.where(inside_left, np.minimum(wl, cap), wl)
        wr = np.where(~inside_left, np.minimum(wr, cap), wr)
        wl = np.maximum(wl, hw + 1.05)
        wr = np.maximum(wr, hw + 1.05)
        grip = np.full(n, float(spec.get("grip", 1.0)))
        # ---- round to the contract's fixed decimals; everything below uses these numbers ----
        def r4(a): return np.array([float(f"{v:.4f}") + 0.0 for v in a])      # + 0.0 folds -0.0 into 0.0
        def r5(a): return np.array([float(f"{v:.5f}") + 0.0 for v in a])
        self.x, self.y, self.z = r4(xz[:, 0]), r4(y), r4(xz[:, 1])
        self.bank, self.hw, self.wl, self.wr, self.grip = r5(bank), r4(hw), r4(wl), r4(wr), r4(grip)
        self.center_text = " ".join(
            f"{self.x[i]:.4f} {self.y[i]:.4f} {self.z[i]:.4f} {self.bank[i]:.5f} {self.hw[i]:.4f} {self.wl[i]:.4f} {self.wr[i]:.4f} {self.grip[i]:.4f}"
            for i in range(n))
        # frames from the rounded samples (central differences)
        X = np.stack([self.x, self.z], -1)
        t = np.roll(X, -1, 0) - np.roll(X, 1, 0)
        t /= np.linalg.norm(t, axis=1, keepdims=True)
        self.tx, self.tz = t[:, 0], t[:, 1]
        self.lx, self.lz = self.tz, -self.tx
        self.tanb = np.tan(self.bank)
        seg = np.sqrt(np.diff(np.append(self.x, self.x[0])) ** 2 + np.diff(np.append(self.z, self.z[0])) ** 2
                      + np.diff(np.append(self.y, self.y[0])) ** 2)
        self.s = np.concatenate([[0], np.cumsum(seg)[:-1]])
        self.length = float(np.sum(seg))
        self.k = curvature(X)
        self.ks = periodic_smooth(self.k, 4.0)
        # 3D tangent and road normal
        P = np.stack([self.x, self.y, self.z], -1)
        T3 = np.roll(P, -1, 0) - np.roll(P, 1, 0)
        T3 /= np.linalg.norm(T3, axis=1, keepdims=True)
        Lb = np.stack([self.lx, self.tanb, self.lz], -1)
        N = np.cross(T3, Lb)
        self.N = N / np.linalg.norm(N, axis=1, keepdims=True)
        self.racing = self._racing_line()

    # ---- frames ----
    def pt(self, i: int, d: float, lift: float = 0.0):
        i %= self.n
        return (self.x[i] + self.lx[i] * d, self.y[i] + d * self.tanb[i] + lift, self.z[i] + self.lz[i] * d)

    def nrm(self, i: int):
        i %= self.n
        return tuple(self.N[i])

    def yaw(self, i: int) -> float:
        i %= self.n
        return math.atan2(self.tx[i], self.tz[i])

    def at_s(self, s: float):
        """Interpolated centre (x, y, z), yaw and fractional index at arc length s (wraps)."""
        s %= self.length
        i = int(np.searchsorted(self.s, s, side="right") - 1)
        j = (i + 1) % self.n
        seg = (self.s[j] if j else self.length) - self.s[i]
        f = (s - self.s[i]) / seg if seg > 0 else 0.0
        x = self.x[i] + (self.x[j] - self.x[i]) * f
        y = self.y[i] + (self.y[j] - self.y[i]) * f
        z = self.z[i] + (self.z[j] - self.z[i]) * f
        tx = self.tx[i] + (self.tx[j] - self.tx[i]) * f
        tz = self.tz[i] + (self.tz[j] - self.tz[i]) * f
        return (x, y, z), math.atan2(tx, tz), i + f

    def lateral_pt(self, s: float, d: float, lift: float = 0.0):
        (x, y, z), yaw, fi = self.at_s(s)
        i = int(fi) % self.n
        lx, lz = math.cos(yaw), -math.sin(yaw)
        return (x + lx * d, y + d * self.tanb[i] + lift, z + lz * d), yaw

    def _racing_line(self) -> np.ndarray:
        a = periodic_smooth(self.k, 5.0)
        b = periodic_smooth(self.k, 22.0)
        o = (a - 0.75 * b) * self.spec.get("line_gain", 600.0)
        o = periodic_smooth(o, 4.0)
        lim = self.hw * 0.62
        return np.clip(o, -lim, lim)

    # ---- the contract pieces ----
    def checkpoints(self, count: int) -> list[int]:
        return [int(round(k * self.n / count)) % self.n for k in range(count)]

    def grid(self) -> list[tuple[float, float, float]]:
        out = []
        for k in range(6):
            row, colm = k // 2, k % 2
            back = 9.0 + 8.0 * row + (3.5 if colm else 0.0)
            side = (1 if colm == 0 else -1) * float(self.hw[0]) * 0.36
            (p, yaw) = self.lateral_pt(self.length - back, side)
            out.append((p[0], p[2], yaw))
        return out

    def corners(self, k_min: float = 1 / 140.0, min_len: int = 6):
        """Corners: runs of |smoothed curvature| above k_min. Returns (start, apex, end, sign)."""
        ks = periodic_smooth(self.k, 6.0)
        hot = np.abs(ks) > k_min
        n = self.n
        if hot.all():
            return [(0, 0, n - 1, 1 if ks[0] > 0 else -1)]
        # rotate to begin outside a corner
        off = int(np.argmin(hot))
        runs = []
        i = 0
        while i < n:
            j = (i + off) % n
            if hot[j] and (i == 0 or not hot[(j - 1) % n]):
                a = i
                sgn = np.sign(ks[j])
                while i < n and hot[(i + off) % n] and np.sign(ks[(i + off) % n]) == sgn:
                    i += 1
                b = i - 1
                if b - a + 1 >= min_len:
                    idx = [(t + off) % n for t in range(a, b + 1)]
                    apex = idx[int(np.argmax(np.abs(ks[idx])))]
                    runs.append(((a + off) % n, apex, (b + off) % n, int(sgn)))
                continue
            i += 1
        return runs


# --------------------------------------------------------------------------------------------
# road meshes (all from the rounded samples)

def span(c: Circuit, i0: int, i1: int):
    """Sample indices from i0 to i1 inclusive, wrapping."""
    n = c.n
    m = (i1 - i0) % n
    return [(i0 + k) % n for k in range(m + 1)]


def ribbon(c: Circuit, mesh: Mesh, idx: list[int], cols, v_scale: float, u_cols=None, lift=0.0,
           close: bool = False, color=None, v0: float = 0.0):
    """Sweep a surface on the banked road plane along samples.

    cols: functions (i) -> lateral offset d, or (d, dy) for a raised profile (dy added straight up).
    u_cols: texture u per column; v runs along with arc length * v_scale. Normals: the road plane.
    """
    rows = []
    seq = idx + ([idx[0]] if close else [])
    s_prev, v_acc = None, v0
    for i in seq:
        if s_prev is not None:
            v_acc += math.dist((c.x[s_prev], c.y[s_prev], c.z[s_prev]), (c.x[i], c.y[i], c.z[i]))
        s_prev = i
        ids = []
        n = c.nrm(i)
        for j, cf in enumerate(cols):
            r = cf(i)
            d, dy = (r if isinstance(r, tuple) else (r, 0.0))
            p = c.pt(i, d, dy + lift)
            u = u_cols[j] if u_cols is not None else j / max(1, len(cols) - 1)
            ids.append(mesh.v(p, n, (u, v_acc * v_scale), color))
        rows.append(ids)
    for a in range(len(rows) - 1):
        for j in range(len(rows[a]) - 1):
            mesh.quad(rows[a][j], rows[a + 1][j], rows[a + 1][j + 1], rows[a][j + 1])
    return mesh


def _profile_normals(prof):
    out = []
    m = len(prof)
    for j in range(m):
        p = prof[j]
        a = prof[j - 1] if j > 0 else None
        b = prof[j + 1] if j < m - 1 else None
        segs = []
        if a is not None and a != p and not (b is not None and b == p):
            segs.append((p[0] - a[0], p[1] - a[1]))
        if b is not None and b != p and not (a is not None and a == p):
            segs.append((b[0] - p[0], b[1] - p[1]))
        if not segs:  # duplicated point: use the side that is not duplicated
            if a is not None and a == p and b is not None:
                segs.append((b[0] - p[0], b[1] - p[1]))
            elif a is not None:
                segs.append((p[0] - a[0], p[1] - a[1]))
        no, nh = 0.0, 0.0
        for dx, dh in segs:
            ln = math.hypot(dx, dh) or 1.0
            no += -dh / ln
            nh += dx / ln
        ln = math.hypot(no, nh) or 1.0
        out.append((no / ln, nh / ln))
    return out


def sweep_profile(c: Circuit, mesh: Mesh, idx: list[int], side: int, base_d, prof, u_scale: float,
                  v_scale: float = 1.0, close: bool = False, color=None, banked: bool = False):
    """Sweep a barrier cross-section along the wall line.

    side: +1 left wall, -1 right wall. base_d(i): distance of the wall line from the centre.
    prof: [(o, h)], o outward from the wall line (away from the road), h up from the road plane
          at the wall line; ordered so the solid lies to the right (face toward the road first).
    Texture: u along (arc length * u_scale), v along the profile length * v_scale.
    """
    pn = _profile_normals(prof)
    plen = [0.0]
    for j in range(1, len(prof)):
        plen.append(plen[-1] + math.hypot(prof[j][0] - prof[j - 1][0], prof[j][1] - prof[j - 1][1]))
    rows = []
    seq = idx + ([idx[0]] if close else [])
    s_prev, u_acc = None, 0.0
    for i in seq:
        if s_prev is not None:
            u_acc += math.dist((c.x[s_prev], c.z[s_prev]), (c.x[i], c.z[i]))
        s_prev = i
        wd = base_d(i)
        y0 = c.y[i] + side * wd * c.tanb[i]
        ox, oz = side * c.lx[i], side * c.lz[i]
        ids = []
        for j, (o, h) in enumerate(prof):
            d = wd + o
            yy = (c.y[i] + side * d * c.tanb[i] + h) if banked else (y0 + h)
            p = (c.x[i] + ox * d, yy, c.z[i] + oz * d)
            no, nh = pn[j]
            n = (ox * no, nh, oz * no)
            ids.append(mesh.v(p, n, (u_acc * u_scale, plen[j] * v_scale), color))
        rows.append(ids)
    for a in range(len(rows) - 1):
        for j in range(len(prof) - 1):
            if prof[j] == prof[j + 1]:
                continue
            mesh.quad(rows[a][j], rows[a + 1][j], rows[a + 1][j + 1], rows[a][j + 1])
    return mesh


def runs(mask) -> list[tuple[int, int]]:
    """Contiguous True runs of a per-sample mask on a closed loop, as (start, end) inclusive."""
    n = len(mask)
    if all(mask):
        return [(0, n - 1)]
    if not any(mask):
        return []
    off = next(i for i in range(n) if not mask[i])
    out = []
    k = 0
    while k < n:
        i = (k + off) % n
        if mask[i]:
            a = k
            while k < n and mask[(k + off) % n]:
                k += 1
            out.append(((a + off) % n, (k - 1 + off) % n))
        else:
            k += 1
    return out
