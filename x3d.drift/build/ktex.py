"""KANSEI procedural textures (numpy + PIL). Every texture is a pure function of its seed.

Noise uses numpy's legacy RandomState (a frozen stream) and FFT filtering, so tiles wrap
seamlessly. PNGs are written with fixed settings (no timestamps), so a rebuild is
byte-identical on the same library versions.
"""
from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


# --------------------------------------------------------------------------------------------
# PNG bytes

def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=False, compress_level=9)
    return buf.getvalue()


def to_img(a: np.ndarray, mode: str | None = None) -> Image.Image:
    a = np.clip(np.round(a * 255.0), 0, 255).astype(np.uint8)
    if mode is None:
        mode = {2: "L", 3: {3: "RGB", 4: "RGBA", 2: "LA"}.get(a.shape[-1], "RGB") if a.ndim == 3 else "L"}[a.ndim]
    return Image.fromarray(a, mode)


def quant(a: np.ndarray, levels: int) -> np.ndarray:
    """Quantise to fewer grey levels: smaller PNGs, invisible after tinting and filtering."""
    return np.round(a * (levels - 1)) / (levels - 1)


# --------------------------------------------------------------------------------------------
# noise

def fbm(h: int, w: int, seed: int, beta: float = 2.0, lo: float = 1.0, hi: float | None = None) -> np.ndarray:
    """Tileable fractal noise in 0..1 by spectral filtering (1/f^beta), band-limited to [lo, hi] cycles."""
    rs = np.random.RandomState(seed)
    white = rs.standard_normal((h, w))
    F = np.fft.fft2(white)
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.fftfreq(w)[None, :] * w
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    amp = 1.0 / np.power(f, beta / 2.0)
    amp[f < lo] = 0.0
    if hi is not None:
        amp[f > hi] = 0.0
    amp[0, 0] = 0.0
    r = np.real(np.fft.ifft2(F * amp))
    r -= r.min()
    m = r.max()
    return r / m if m > 0 else r


def white(h: int, w: int, seed: int) -> np.ndarray:
    return np.random.RandomState(seed).random_sample((h, w))


def blur(a: np.ndarray, r: float) -> np.ndarray:
    """Wrap-around Gaussian blur through the FFT (keeps tiles seamless)."""
    h, w = a.shape[:2]
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    g = np.exp(-2 * (math.pi ** 2) * (r ** 2) * (fx * fx + fy * fy))
    if a.ndim == 2:
        return np.real(np.fft.ifft2(np.fft.fft2(a) * g))
    return np.stack([np.real(np.fft.ifft2(np.fft.fft2(a[..., k]) * g)) for k in range(a.shape[2])], -1)


def normal_map(height: np.ndarray, strength: float) -> np.ndarray:
    """Tangent-space normal map (RGB 0..1) from a tileable height field."""
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5 * strength
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5 * strength
    nx, ny, nz = -dx, dy, np.ones_like(height)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.stack([nx / ln * 0.5 + 0.5, ny / ln * 0.5 + 0.5, nz / ln * 0.5 + 0.5], -1)


def downsample(a: np.ndarray, k: int) -> np.ndarray:
    h, w = a.shape[:2]
    if a.ndim == 2:
        return a.reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    return a.reshape(h // k, k, w // k, k, a.shape[2]).mean(axis=(1, 3))


def voronoi(h: int, w: int, cells: int, seed: int):
    """Tileable jittered-grid Voronoi: returns (f1, f2, cell id) in pixel units."""
    rs = np.random.RandomState(seed)
    cy, cx = cells, cells
    jit = rs.random_sample((cy, cx, 2))
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    sy, sx = h / cy, w / cx
    gy, gx = (ys // sy).astype(int), (xs // sx).astype(int)
    f1 = np.full((h, w), 1e9)
    f2 = np.full((h, w), 1e9)
    cid = np.zeros((h, w), dtype=np.int64)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            ny, nx = gy + oy, gx + ox
            wy, wx = ny % cy, nx % cx
            py = (ny + jit[wy, wx, 0]) * sy
            px = (nx + jit[wy, wx, 1]) * sx
            d = np.sqrt((ys - py) ** 2 + (xs - px) ** 2)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            cid = np.where(closer, wy * cx + wx, cid)
            f1 = np.where(closer, d, f1)
    return f1, f2, cid


# --------------------------------------------------------------------------------------------
# a stroke font for signs, plates and banners (original, 4 x 6 grid, y up)

O_ = [(1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)]
GLYPHS = {
    "A": [[(0, 0), (0, 4), (2, 6), (4, 4), (4, 0)], [(0, 3), (4, 3)]],
    "B": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    "C": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "D": [[(0, 0), (0, 6), (2, 6), (4, 4), (4, 2), (2, 0), (0, 0)]],
    "E": [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]],
    "F": [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    "G": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (2, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(1, 6), (3, 6)], [(2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "J": [[(4, 6), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "K": [[(0, 0), (0, 6)], [(4, 6), (0, 2)], [(1, 3), (4, 0)]],
    "L": [[(0, 6), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    "N": [[(0, 0), (0, 6), (4, 0), (4, 6)]],
    "O": [O_],
    "P": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]],
    "Q": [O_, [(2, 2), (4, 0)]],
    "R": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(2, 3), (4, 0)]],
    "S": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 4), (1, 3), (3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "T": [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    "U": [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    "V": [[(0, 6), (2, 0), (4, 6)]],
    "W": [[(0, 6), (1, 0), (2, 3), (3, 0), (4, 6)]],
    "X": [[(0, 6), (4, 0)], [(4, 6), (0, 0)]],
    "Y": [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]],
    "Z": [[(0, 6), (4, 6), (0, 0), (4, 0)]],
    "0": [O_, [(0.6, 1), (3.4, 5)]],
    "1": [[(1, 5), (2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "2": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (0, 0), (4, 0)]],
    "3": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "4": [[(3, 0), (3, 6), (0, 2), (4, 2)]],
    "5": [[(4, 6), (0, 6), (0, 3), (3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    "6": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]],
    "7": [[(0, 6), (4, 6), (1, 0)]],
    "8": [[(1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1, 3), (0, 2), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3)]],
    "9": [[(4, 3), (1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)]],
    "-": [[(1, 3), (3, 3)]],
    ".": [[(2, 0), (2, 0.4)]],
    "'": [[(2, 6), (2, 5)]],
    "/": [[(0, 0), (4, 6)]],
    "+": [[(0, 3), (4, 3)], [(2, 1), (2, 5)]],
    "*": [[(2, 1.5), (2, 4.5)], [(0.7, 2.2), (3.3, 3.8)], [(0.7, 3.8), (3.3, 2.2)]],
    ">": [[(0, 6), (4, 3), (0, 0)]],
    "<": [[(4, 6), (0, 3), (4, 0)]],
    " ": [],
}


def text_strokes(text: str, x0: float, y0: float, h: float, spacing: float = 1.5, slant: float = 0.0):
    """Polylines (image coordinates, y down) for text whose cap height is h, starting at (x0, baseline y0)."""
    s = h / 6.0
    out = []
    x = x0
    for ch in text.upper():
        g = GLYPHS.get(ch, GLYPHS[" "])
        for line in g:
            out.append([(x + (gx + gy * slant) * s, y0 - gy * s) for gx, gy in line])
        x += (4 + spacing) * s
    return out


def text_width(text: str, h: float, spacing: float = 1.5) -> float:
    s = h / 6.0
    return len(text) * (4 + spacing) * s - spacing * s


def draw_text(draw: ImageDraw.ImageDraw, text: str, cx: float, cy: float, h: float, width: float, fill,
              spacing: float = 1.5, slant: float = 0.0):
    """Centred text, strokes drawn with round joints."""
    w = text_width(text, h, spacing)
    for line in text_strokes(text, cx - w / 2, cy + h / 2, h, spacing, slant):
        if len(line) == 1:
            line = line * 2
        draw.line(line, fill=fill, width=max(1, int(round(width))), joint="curve")
        r = width / 2
        for (px, py) in (line[0], line[-1]):
            draw.ellipse([px - r, py - r, px + r, py + r], fill=fill)


# --------------------------------------------------------------------------------------------
# road and roadside

def asphalt(seed: int = 11):
    n = 512
    base = 0.55 + 0.18 * (fbm(n, n, seed, 1.6, 2, 24) - 0.5)
    grit = fbm(n, n, seed + 1, 0.6, 40, None)
    stones = white(n, n, seed + 2)
    light = (stones > 0.985).astype(float)
    light = np.clip(blur(light, 0.7) * 3.0, 0, 1)
    dark = (stones < 0.02).astype(float)
    dark = np.clip(blur(dark, 0.8) * 3.0, 0, 1)
    patch = fbm(n, n, seed + 3, 2.2, 1, 6)
    a = base + (grit - 0.5) * 0.22 + light * 0.22 - dark * 0.20 - (patch > 0.72) * 0.05
    a = np.clip(a, 0, 1)
    h = grit * 0.6 + light * 0.6 - dark * 0.8
    nm = normal_map(downsample(h, 2), 3.0)
    return to_img(quant(a, 48), "L"), to_img(nm, "RGB")


def concrete(seed: int = 21):
    n = 256
    a = 0.62 + 0.16 * (fbm(n, n, seed, 2.0, 1, 30) - 0.5) + 0.10 * (fbm(n, n, seed + 1, 0.8, 30) - 0.5)
    pores = white(n, n, seed + 2) < 0.012
    a = a - blur(pores.astype(float), 0.6) * 0.5
    stain = fbm(n, n, seed + 3, 2.6, 1, 8)
    a = a - np.clip(stain - 0.62, 0, 1) * 0.5
    h = fbm(n, n, seed + 1, 0.8, 30) - pores * 0.6
    return to_img(quant(np.clip(a, 0, 1), 40), "L"), to_img(normal_map(h, 2.0), "RGB")


def terrain_detail(seed: int = 31):
    n = 256
    blades = fbm(n, n, seed, 0.4, 32)
    clumps = fbm(n, n, seed + 1, 2.0, 2, 24)
    a = 0.62 + (blades - 0.5) * 0.40 + (clumps - 0.5) * 0.16
    return to_img(quant(np.clip(a, 0, 1), 40), "L")


def rock(seed: int = 41):
    n = 256
    ys = np.arange(n)[:, None] / n
    warp = fbm(n, n, seed, 2.2, 1, 8)
    strata = 0.5 + 0.5 * np.sin((ys * 9 + warp * 1.6) * 2 * math.pi)
    detail = fbm(n, n, seed + 1, 1.2, 4)
    f1, f2, _ = voronoi(n, n, 6, seed + 2)
    cracks = np.clip((f2 - f1) / 4.0, 0, 1)
    a = 0.42 + strata * 0.16 + (detail - 0.5) * 0.45
    a = a * (0.55 + 0.45 * cracks)
    h = detail * 0.8 + strata * 0.3 + cracks * 0.6
    return to_img(quant(np.clip(a, 0, 1), 48), "L"), to_img(normal_map(h, 5.0), "RGB")


def gravel(seed: int = 51):
    n = 256
    f1, f2, cid = voronoi(n, n, 28, seed)
    shade = (np.random.RandomState(seed + 1).random_sample(28 * 28)[cid] - 0.5) * 0.5
    a = 0.55 + shade - np.clip(1.0 - f1 / 4.5, 0, 1) * 0.0 - np.clip(1.5 - (f2 - f1), 0, 1) * 0.35
    a += (fbm(n, n, seed + 2, 1.0, 20) - 0.5) * 0.2
    return to_img(quant(np.clip(a, 0, 1), 40), "L")


def sand(seed: int = 61):
    n = 256
    ys = np.arange(n)[:, None] / n
    xs = np.arange(n)[None, :] / n
    warp = fbm(n, n, seed, 2.4, 1, 6)
    ripple = 0.5 + 0.5 * np.sin((xs * 6 + ys * 2 + warp * 1.2) * 2 * math.pi)
    a = 0.70 + (ripple - 0.5) * 0.10 + (fbm(n, n, seed + 1, 0.5, 30) - 0.5) * 0.25
    return to_img(quant(np.clip(a, 0, 1), 32), "L")


def salt(seed: int = 71):
    n = 512
    f1, f2, cid = voronoi(n, n, 9, seed)
    ridge = np.clip(1.0 - (f2 - f1) / 7.0, 0, 1) ** 2
    plate = (np.random.RandomState(seed + 1).random_sample(81)[cid] - 0.5) * 0.08
    detail = fbm(n, n, seed + 2, 0.9, 12)
    a = 0.80 + plate + (detail - 0.5) * 0.18 + ridge * 0.14
    h = ridge * 1.0 + detail * 0.3
    nm = normal_map(downsample(h, 2), 4.0)
    return to_img(quant(np.clip(a, 0, 1), 48), "L"), to_img(nm, "RGB")


def stone_wall(seed: int = 81):
    """Dry stone wall: rows of rough blocks, dark joints."""
    h, w = 256, 256
    rs = np.random.RandomState(seed)
    a = np.zeros((h, w))
    hgt = np.zeros((h, w))
    rows = 6
    y = 0
    detail = fbm(h, w, seed + 1, 1.0, 8)
    for r in range(rows):
        rh = h // rows
        x = int(rs.randint(0, 40))
        while x < w + 60:
            bw = int(rs.randint(34, 72))
            tone = 0.48 + rs.random_sample() * 0.25
            x0, x1 = x, x + bw
            yy0, yy1 = y + 2, y + rh - 2
            for xx in range(x0 + 2, x1 - 2):
                xm = xx % w
                a[yy0:yy1, xm] = tone
                hgt[yy0:yy1, xm] = 1.0
            x = x1
        y += rh
    a = blur(a, 1.2)
    hgt = blur(hgt, 1.5)
    a = a * (0.7 + 0.6 * (detail - 0.5) + 0.3) - (1 - hgt) * 0.08
    return to_img(quant(np.clip(a, 0, 1), 48), "L"), to_img(normal_map(hgt * 1.5 + detail * 0.4, 4.0), "RGB")


def curb(c1, c2, seed: int = 91):
    """Kerb stripes along v (two stripes per tile), worn paint and rubber at the inner edge (u = 0)."""
    h, w = 256, 64
    v = np.arange(h)[:, None] / h
    u = np.arange(w)[None, :] / w
    stripe = (v < 0.5).astype(float) * np.ones((1, w))
    rgb = np.zeros((h, w, 3))
    for k in range(3):
        rgb[..., k] = stripe * c1[k] + (1 - stripe) * c2[k]
    wear = fbm(h, w, seed, 1.0, 8)
    rubber = np.clip((0.45 - u) * 2.2, 0, 1) * (0.4 + 0.6 * fbm(h, w, seed + 1, 1.5, 2, 30))
    grime = 0.86 + 0.14 * wear
    rgb = rgb * grime[..., None]
    rgb = rgb * (1 - rubber[..., None] * 0.55) + rubber[..., None] * 0.05
    edge = np.clip(1 - np.abs(u - 0.97) * 30, 0, 1)
    rgb = rgb * (1 - edge[..., None] * 0.5)
    return to_img(np.clip(rgb, 0, 1), "RGB")


def wear_band(seed: int = 101):
    """Racing-line rubber: two tyre bands across u, streaky along v. LA (alpha carries the rubber)."""
    h, w = 256, 64
    u = np.arange(w)[None, :] / w
    band = np.exp(-((u - 0.22) / 0.13) ** 2) + np.exp(-((u - 0.78) / 0.13) ** 2) + 0.35 * np.exp(-((u - 0.5) / 0.3) ** 2)
    streak = fbm(h, w, seed, 1.0, 1, 40)
    streak = np.clip(0.4 + 0.9 * (streak - 0.5) + 0.3 * fbm(h, w, seed + 1, 0.5, 8), 0, 1)
    alpha = np.clip(band * streak * 0.75, 0, 0.85)
    lum = np.full((h, w), 0.06)
    return to_img(np.stack([lum, alpha], -1), "LA")


def skid_band(seed: int = 111):
    """Old drift marks: four tyre tracks, broken and overlapping."""
    h, w = 256, 64
    u = np.arange(w)[None, :] / w
    a = np.zeros((h, w))
    for c, wd in ((0.12, 0.06), (0.36, 0.06), (0.64, 0.06), (0.88, 0.06)):
        a += np.exp(-((u - c) / wd) ** 2)
    brk = fbm(h, w, seed, 2.5, 1, 6)
    a = a * np.clip((brk - 0.3) * 2.5, 0, 1) * (0.6 + 0.4 * fbm(h, w, seed + 1, 0.6, 16))
    alpha = np.clip(a * 0.8, 0, 0.8)
    return to_img(np.stack([np.full((h, w), 0.04), alpha], -1), "LA")


def guardrail(seed: int = 121):
    """W-beam guardrail: u along (one post spacing per tile), v across the beam."""
    h, w = 64, 256
    v = np.arange(h)[:, None] / h
    u = np.arange(w)[None, :] / w
    ridges = 0.75 + 0.25 * np.cos(v * 2 * math.pi * 2)
    grime = fbm(h, w, seed, 1.4, 2, 40)
    streak = fbm(h, w, seed + 1, 2.0, 1, 40) * np.clip(v * 1.4, 0, 1)
    base = 0.70 * ridges * (0.9 + 0.2 * grime) - streak * 0.18
    rgb = np.stack([base * 0.98, base * 1.0, base * 1.03], -1)
    rust = np.clip((fbm(h, w, seed + 2, 2.0, 2, 32) - 0.74) * 4, 0, 1) * np.clip(v * 2 - 0.6, 0, 1)
    rgb = rgb * (1 - rust[..., None] * 0.6) + rust[..., None] * np.array([0.38, 0.2, 0.1]) * 0.6
    # bolts at the post (u = 0)
    for bx in (0.02, 0.98):
        for by in (0.32, 0.68):
            d = np.sqrt(((u - bx) * w) ** 2 + ((v - by) * h) ** 2)
            rgb = rgb * (1 - np.clip(3 - d, 0, 1)[..., None] * 0.5)
    return to_img(np.clip(rgb, 0, 1), "RGB")


def tyre_wall(seed: int = 131):
    """Stacks of flat-lying tyres seen from the track: 2 stacks x 4 tyres per tile, painted bands on alternate stacks.
    u along the wall (1 tile = 1.2 m), v up (1 tile = 0.92 m)."""
    h, w = 128, 128
    ys, xs = np.mgrid[0:h, 0:w].astype(float)
    rgb = np.zeros((h, w, 3)) + 0.02
    hgt = np.zeros((h, w))
    rows = 4
    rh = h / rows
    for c in range(2):
        cx0, cx1 = c * w / 2 + 2, (c + 1) * w / 2 - 2
        u = (xs - cx0) / (cx1 - cx0)
        inside = (u >= 0) & (u <= 1)
        bulge = np.sqrt(np.clip(1 - (2 * u - 1) ** 2, 0, 1))
        for r in range(rows):
            y0 = r * rh + 1.5
            y1 = (r + 1) * rh - 1.5
            v = (ys - y0) / (y1 - y0)
            tyre = inside & (v >= 0) & (v <= 1)
            round_ = np.sqrt(np.clip(1 - (2 * v - 1) ** 2, 0, 1))
            shade = 0.05 + 0.10 * bulge * round_
            col = np.array([0.06, 0.06, 0.065])
            if c == 1:
                col = np.array([0.80, 0.80, 0.78]) if r % 2 == 0 else np.array([0.75, 0.10, 0.08])
            band = tyre & (np.abs(v - 0.5) < 0.42)
            for k in range(3):
                rgb[..., k] = np.where(tyre, shade * (0.6 + 0.8 * round_), rgb[..., k])
                rgb[..., k] = np.where(band, col[k] * (0.45 + 0.55 * bulge * round_), rgb[..., k])
            hgt = np.where(tyre, bulge * round_, hgt)
    rgb = rgb * (0.85 + 0.3 * fbm(h, w, seed, 1.0, 8)[..., None])
    return to_img(np.clip(rgb, 0, 1), "RGB"), to_img(normal_map(blur(hgt, 0.8), 5.0), "RGB")


def _old_tyre_wall(seed: int = 131):
    """Stacked tyres seen from the side: 2 columns x 3 rows per tile, sidewall rings, tread gaps."""
    h, w = 128, 128
    ys, xs = np.mgrid[0:h, 0:w].astype(float)
    rgb = np.zeros((h, w, 3)) + 0.03
    hgt = np.zeros((h, w))
    cols, rows = 2, 3
    cw, rh = w / cols, h / rows
    noise = fbm(h, w, seed, 0.8, 16)
    for r in range(rows):
        for c in range(cols):
            cx = (c + 0.5) * cw
            cy = (r + 0.5) * rh
            dx = xs - cx
            dy = (ys - cy) * (cw / rh)
            d = np.sqrt(dx * dx + dy * dy) / (cw / 2)
            tyre = (d < 0.98).astype(float)
            ring = np.clip(1 - np.abs(d - 0.75) * 12, 0, 1)
            hole = d < 0.45
            shade = 0.08 + 0.06 * (1 - d) + ring * 0.05
            for k in range(3):
                rgb[..., k] = np.where(tyre > 0, shade, rgb[..., k])
            rgb = np.where(hole[..., None], 0.015, rgb)
            hgt = np.maximum(hgt, tyre * (1 - np.abs(d - 0.72)) * (~hole))
    rgb = rgb * (0.8 + 0.4 * noise[..., None])
    return to_img(np.clip(rgb, 0, 1), "RGB"), to_img(normal_map(blur(hgt, 1.0), 6.0), "RGB")


def chevron(seed: int = 141):
    h, w = 64, 128
    ys, xs = np.mgrid[0:h, 0:w].astype(float)
    t = ((xs + np.abs(ys - h / 2) * 1.2) / 32.0) % 1.0
    m = (t < 0.5).astype(float)
    y1 = np.array([0.98, 0.78, 0.08])
    k = np.array([0.04, 0.04, 0.05])
    rgb = m[..., None] * y1 + (1 - m[..., None]) * k
    rgb = rgb * (0.9 + 0.1 * fbm(h, w, seed, 1.0, 4)[..., None])
    border = ((ys < 3) | (ys > h - 4)).astype(float)[..., None]
    rgb = rgb * (1 - border) + border * 0.9
    return to_img(np.clip(rgb, 0, 1), "RGB")


def checker(seed: int = 151):
    h, w = 32, 128
    ys, xs = np.mgrid[0:h, 0:w]
    m = ((xs // 16 + ys // 16) % 2).astype(float)
    a = 0.12 + 0.80 * m
    a = a * (0.92 + 0.08 * fbm(h, w, seed, 1.0, 2))
    return to_img(np.clip(a, 0, 1), "L")


def paint_line(seed: int = 161):
    """Road paint: bright, with fine wear (L). u across the stripe, v along."""
    h, w = 128, 16
    a = 0.92 - np.clip(fbm(h, w, seed, 1.2, 2, 30) - 0.62, 0, 1) * 1.4 - (white(h, w, seed + 1) < 0.04) * 0.3
    return to_img(np.clip(a, 0, 1), "L")


def facade(seed: int, kind: str):
    """Building facade (base) and window emission maps; 8 x 8 windows per tile."""
    n = 256
    ys, xs = np.mgrid[0:n, 0:n].astype(float)
    cells = 16
    cs = n / cells
    fx = (xs % cs) / cs
    fy = (ys % cs) / cs
    rs = np.random.RandomState(seed)
    if kind == "glass":
        win = (fy > 0.10) & (fy < 0.94) & (fx > 0.06) & (fx < 0.94)
        frame = 0.30
        glass = 0.10
    else:
        win = (fy > 0.28) & (fy < 0.84) & (fx > 0.22) & (fx < 0.78)
        frame = 0.55
        glass = 0.12
    noise = fbm(n, n, seed + 1, 1.6, 1, 20)
    base = np.where(win, glass + 0.06 * noise, frame * (0.85 + 0.3 * noise))
    gx, gy = (xs // cs).astype(int), (ys // cs).astype(int)
    lit = rs.random_sample((cells, cells))
    floor_dark = rs.random_sample(cells) < 0.22
    lit[floor_dark, :] *= 0.4
    warm = rs.random_sample((cells, cells))
    lvl = lit[gy, gx]
    on = (lvl > 0.55) & win
    tone = warm[gy, gx]
    colA = np.array([1.0, 0.78, 0.48])
    colB = np.array([0.62, 0.82, 1.0])
    colC = np.array([0.95, 0.95, 0.88])
    c = np.where((tone < 0.5)[..., None], colA, np.where((tone < 0.8)[..., None], colC, colB))
    inten = (0.25 + 0.45 * lvl)[..., None] * (0.75 + 0.25 * fy[..., None])
    blinds = ((ys % (cs / 6)) < 1.0) & on & (tone > 0.6)
    em = np.where(on[..., None], c * inten, 0.0)
    em = np.where(blinds[..., None], em * 0.5, em)
    rgb = np.stack([base * 0.92, base * 0.95, base * 1.0], -1)
    return to_img(np.clip(rgb, 0, 1), "RGB"), to_img(np.clip(em, 0, 1), "RGB")


def ocean_normal(seed: int = 171):
    n = 256
    hgt = fbm(n, n, seed, 3.0, 2, 40) + 0.4 * fbm(n, n, seed + 1, 2.0, 8, 64)
    return to_img(normal_map(hgt, 9.0), "RGB")


def foam(seed: int = 181):
    h, w = 64, 256
    v = np.arange(h)[:, None] / h
    n = fbm(h, w, seed, 1.5, 2, 40)
    a = np.clip((n - 0.35) * 2.5, 0, 1) * np.clip(1 - v * 1.3, 0, 1) + np.clip(0.25 - v, 0, 1) * 3
    a = np.clip(a, 0, 1)
    return to_img(np.stack([np.full((h, w), 0.95), a * 0.9], -1), "LA")


# --------------------------------------------------------------------------------------------
# vegetation billboards (RGBA, alpha tested)

def pine(seed: int = 191, dark=(0.10, 0.20, 0.12), light=(0.30, 0.44, 0.22)):
    w, h = 128, 256
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rs = np.random.RandomState(seed)
    d.rectangle([w / 2 - 4, h * 0.70, w / 2 + 4, h - 1], fill=(70, 48, 34, 255))
    tiers = 11
    for t in range(tiers):
        f = t / (tiers - 1)
        y = h * (0.05 + 0.80 * f)
        half = 6 + f * (w * 0.46 - 6) * (0.85 + 0.15 * rs.random_sample())
        droop = 10 + 18 * f
        for k in range(16):
            s = (k / 15.0) * 2 - 1
            x1 = w / 2 + s * half
            y1 = y + droop * abs(s) ** 1.4 + rs.randint(-3, 4)
            shade = 0.55 + 0.45 * (1 - abs(s)) * (1 - 0.5 * f) + (0.12 if s < 0 else -0.05)
            c = [int(255 * min(1, (dark[i] + (light[i] - dark[i]) * shade) * (0.9 + 0.2 * rs.random_sample()))) for i in range(3)]
            d.line([(w / 2, y - 6), (x1, y1)], fill=(*c, 255), width=4)
            d.ellipse([x1 - 3, y1 - 3, x1 + 3, y1 + 3], fill=(*c, 255))
    a = np.asarray(img).astype(float) / 255.0
    return to_img(a, "RGBA")


def cypress(seed: int = 201, dark=(0.07, 0.15, 0.07), light=(0.34, 0.47, 0.22)):
    w, h = 64, 256
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rs = np.random.RandomState(seed)
    d.rectangle([w / 2 - 2, h * 0.88, w / 2 + 2, h - 1], fill=(64, 46, 34, 255))
    # a dark core first, then lit clumps that are brighter on the upper sun side
    for k in range(720):
        t = rs.random_sample()
        y = h * (0.03 + 0.88 * t)
        half = (w * 0.42) * math.sin(math.pi * min(1.0, 0.15 + t * 0.95)) ** 0.8
        core = k < 240
        x = w / 2 + (rs.random_sample() * 2 - 1) * half * (0.6 if core else 1.0)
        side = (x - w / 2) / max(1.0, half)
        shade = 0.0 if core else min(1.0, max(0.0, 0.55 - 0.35 * side + 0.25 * (1 - t) + 0.25 * (rs.random_sample() - 0.5)))
        c = [int(255 * (dark[i] + (light[i] - dark[i]) * shade)) for i in range(3)]
        r = (3 if core else 1.6) + rs.random_sample() * 2.4
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*c, 255))
    return to_img(np.asarray(img).astype(float) / 255.0, "RGBA")


def shrub(seed: int = 211, tint=(0.56, 0.64, 0.32)):
    w, h = 128, 64
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rs = np.random.RandomState(seed)
    for k in range(260):
        x = w * (0.08 + 0.84 * rs.random_sample())
        top = h * (0.25 + 0.5 * abs(x / w - 0.5) * 2)
        y = top + rs.random_sample() * (h - top)
        shade = 0.6 + 0.4 * (1 - (y - top) / max(1, h - top))
        c = tuple(int(255 * min(1, tint[i] * shade * (0.85 + 0.3 * rs.random_sample()))) for i in range(3)) + (255,)
        r = 2 + rs.random_sample() * 4
        d.ellipse([x - r, y - r, x + r, y + r], fill=c)
    return to_img(np.asarray(img).astype(float) / 255.0, "RGBA")


# --------------------------------------------------------------------------------------------
# signs and banners (stroke font)

def neon_atlas(words: list[tuple[str, tuple]], seed: int = 221):
    """Emissive sign atlas: 8 rows of glowing tube lettering on black, 512 x 512."""
    W, H = 512, 512
    rows = len(words)
    rh = H // rows
    base = Image.new("RGB", (W, H), (0, 0, 0))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    db, dg = ImageDraw.Draw(base), ImageDraw.Draw(glow)
    for r, (word, c) in enumerate(words):
        cy = r * rh + rh / 2
        hh = rh * 0.52
        tw = text_width(word, hh, 1.6)
        if tw > W * 0.9:
            hh *= W * 0.9 / tw
        c255 = tuple(int(255 * x) for x in c)
        draw_text(dg, word, W / 2, cy, hh, hh * 0.30, c255, 1.6)
        # tube core: near white tinted
        core = tuple(int(255 * (0.55 + 0.45 * x)) for x in c)
        draw_text(db, word, W / 2, cy, hh, hh * 0.10, core, 1.6)
        # frame line
        dg.rectangle([10, r * rh + 6, W - 10, (r + 1) * rh - 6], outline=tuple(int(v * 0.35) for v in c255), width=2)
    glow = glow.filter(ImageFilter.GaussianBlur(5))
    a = np.clip(np.asarray(glow).astype(float) / 255.0 * 1.3 + np.asarray(base).astype(float) / 255.0, 0, 1)
    return to_img(a, "RGB")


def banner(lines: list[tuple[str, tuple, tuple]], w: int = 512, h: int = 96):
    """Painted banner rows: (text, fg, bg). Returns one RGB image stacking the rows."""
    rows = len(lines)
    img = Image.new("RGB", (w, h * rows), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for r, (text, fg, bg) in enumerate(lines):
        y0 = r * h
        d.rectangle([0, y0, w, y0 + h], fill=tuple(int(255 * x) for x in bg))
        d.rectangle([0, y0 + 6, w, y0 + 10], fill=tuple(int(255 * x) for x in fg))
        d.rectangle([0, y0 + h - 10, w, y0 + h - 6], fill=tuple(int(255 * x) for x in fg))
        th = h * 0.46
        tw = text_width(text, th, 1.8)
        if tw > w * 0.92:
            th *= w * 0.92 / tw
        draw_text(d, text, w / 2, y0 + h / 2, th, th * 0.16, tuple(int(255 * x) for x in fg), 1.8, slant=0.12)
    return to_img(np.asarray(img).astype(float) / 255.0, "RGB")


def plates(items: list[str]):
    """Number plate atlas: one 256 x 128 plate per row (2:1)."""
    w, h = 256, 128
    img = Image.new("RGB", (w, h * len(items)), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for r, text in enumerate(items):
        y0 = r * h
        d.rounded_rectangle([2, y0 + 2, w - 3, y0 + h - 3], radius=10, fill=(236, 234, 226), outline=(40, 44, 52), width=5)
        top, bottom = text.split("|")
        draw_text(d, top, w / 2, y0 + 30, 22, 4, (40, 70, 60), 1.6)
        draw_text(d, bottom, w / 2, y0 + 82, 52, 8, (24, 40, 34), 1.4)
    return to_img(np.asarray(img).astype(float) / 255.0, "RGB")


def tyre_sidewall(seed: int = 231):
    """Sidewall, u around the tyre (2 repeats of the lettering), v from rim (0) to shoulder (1)."""
    w, h = 512, 64
    img = Image.new("L", (w, h), 26)
    d = ImageDraw.Draw(img)
    for k in range(2):
        cx = w * (0.25 + 0.5 * k)
        draw_text(d, "KANSEI  RS-7", cx, h * 0.52, 20, 3, 92, 1.5)
    a = np.asarray(img).astype(float) / 255.0
    v = np.arange(h)[:, None] / h
    a = a + 0.05 * np.cos(v * 2 * math.pi * 3) * (v < 0.2) - 0.03 * (v > 0.88)
    a = a * (0.9 + 0.1 * fbm(h, w, seed, 1.0, 4))
    return to_img(np.clip(a, 0, 1), "L")


def tread(seed: int = 241):
    w, h = 64, 256
    ys, xs = np.mgrid[0:h, 0:w].astype(float)
    grooves = ((np.abs(xs - w * 0.33) < 2.5) | (np.abs(xs - w * 0.67) < 2.5)).astype(float)
    sipes = ((((ys + np.abs(xs - w / 2) * 0.6) % 16) < 2) & (np.abs(xs - w / 2) > 6)).astype(float)
    a = 0.16 - grooves * 0.11 - sipes * 0.06 + 0.03 * fbm(h, w, seed, 1.0, 4)
    return to_img(np.clip(a, 0, 1), "L")


def grille(seed: int = 251):
    n = 64
    ys, xs = np.mgrid[0:n, 0:n].astype(float)
    a = ((((xs + ys) % 8) < 2) | (((xs - ys) % 8) < 2)).astype(float)
    return to_img(0.05 + a * 0.35, "L")


def lamp_lens(seed: int = 261):
    """Light lens: cells of reflector facets (L, used for both base and emissive)."""
    w, h = 128, 64
    ys, xs = np.mgrid[0:h, 0:w].astype(float)
    cx = (xs % 16) - 8
    cy = (ys % 16) - 8
    d = np.sqrt(cx * cx + cy * cy) / 8
    a = 0.55 + 0.45 * np.clip(1 - d, 0, 1)
    edge = ((xs < 3) | (xs > w - 4) | (ys < 3) | (ys > h - 4)).astype(float)
    a = a * (1 - edge * 0.6)
    return to_img(np.clip(a, 0, 1), "L")


def floor_concrete(seed: int = 271):
    """Showroom floor: polished concrete with large slabs and soft mottling (L, 512)."""
    n = 512
    mott = fbm(n, n, seed, 2.4, 1, 24)
    fine = fbm(n, n, seed + 1, 0.8, 40)
    ys, xs = np.mgrid[0:n, 0:n]
    joints = ((xs % 256) < 2) | ((ys % 256) < 2)
    a = 0.34 + (mott - 0.5) * 0.18 + (fine - 0.5) * 0.06 - joints * 0.14
    return to_img(quant(np.clip(a, 0, 1), 48), "L")


def soft_spot(seed: int = 281):
    """Radial light pool (LA) for lamp light on the road and the showroom floor."""
    n = 128
    ys, xs = np.mgrid[0:n, 0:n].astype(float)
    d = np.sqrt((xs - n / 2 + 0.5) ** 2 + (ys - n / 2 + 0.5) ** 2) / (n / 2)
    a = np.clip(1 - d, 0, 1) ** 1.8
    return to_img(np.stack([np.ones((n, n)), a], -1), "LA")


def light_strip(seed: int = 291):
    """Tunnel / showroom strip light (L): bright core, soft falloff across v."""
    h, w = 32, 128
    v = np.arange(h)[:, None] / (h - 1)
    a = np.exp(-((v - 0.5) / 0.22) ** 2) * np.ones((1, w))
    xs = np.arange(w)[None, :]
    a = a * (0.75 + 0.25 * (((xs % 32) > 3)))
    return to_img(np.clip(a, 0, 1), "L")


def carbon(seed: int = 301):
    """2x2 twill carbon weave (L, 64): alternating tows with a soft sheen across each."""
    n = 64
    ys, xs = np.mgrid[0:n, 0:n].astype(float)
    cell = 8.0
    cx, cy = np.floor(xs / cell), np.floor(ys / cell)
    horiz = ((cx + cy) % 4) < 2
    fx, fy = (xs % cell) / cell, (ys % cell) / cell
    sheen = np.where(horiz, np.sin(fy * math.pi), np.sin(fx * math.pi))
    a = 0.16 + 0.22 * sheen * np.where(horiz, 1.0, 0.75)
    return to_img(np.clip(a, 0, 1), "L")


def garage_sign(seed: int = 311):
    """Showroom wall sign (RGBA 512 x 128): glowing KANSEI wordmark over a thin rule."""
    W, H = 512, 128
    base = Image.new("RGB", (W, H), (0, 0, 0))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    db, dg = ImageDraw.Draw(base), ImageDraw.Draw(glow)
    draw_text(dg, "KANSEI", W / 2, 52, 56, 16, (255, 120, 40), 1.7)
    draw_text(db, "KANSEI", W / 2, 52, 56, 5, (255, 230, 200), 1.7)
    draw_text(dg, "DRIFT GARAGE", W / 2, 104, 16, 6, (80, 170, 255), 1.6)
    draw_text(db, "DRIFT GARAGE", W / 2, 104, 16, 2, (210, 235, 255), 1.6)
    dg.line([(60, 88), (W - 60, 88)], fill=(255, 120, 40), width=3)
    glow = glow.filter(ImageFilter.GaussianBlur(4))
    rgb = np.clip(np.asarray(glow).astype(float) / 255.0 * 1.4 + np.asarray(base).astype(float) / 255.0, 0, 1)
    alpha = np.clip(rgb.max(axis=2) * 2.2, 0, 1)
    return to_img(np.concatenate([rgb, alpha[..., None]], axis=2), "RGBA")


# --------------------------------------------------------------------------------------------
# skies: six cube faces rendered from a direction -> RGBA function (alpha over skyColor)

def cube_dirs(n: int, face: str) -> np.ndarray:
    """Unit view directions for each pixel of a Background face (X3D: front looks down -Z)."""
    t = (np.arange(n) + 0.5) / n * 2 - 1
    a = t[None, :] * np.ones((n, 1))           # image x, left -> right
    b = -t[:, None] * np.ones((1, n))          # image y, up is +
    one = np.ones((n, n))
    if face == "front":
        d = np.stack([a, b, -one], -1)
    elif face == "back":
        d = np.stack([-a, b, one], -1)
    elif face == "left":
        d = np.stack([-one, b, -a], -1)
    elif face == "right":
        d = np.stack([one, b, a], -1)
    elif face == "top":
        d = np.stack([a, one, b], -1)
    else:  # bottom
        d = np.stack([a, -one, -b], -1)
    return d / np.linalg.norm(d, axis=-1, keepdims=True)


def bilinear(tex: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    h, w = tex.shape
    x = u * w - 0.5
    y = v * h - 0.5
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    x0 %= w
    y0 %= h
    x1, y1 = (x0 + 1) % w, (y0 + 1) % h
    return (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x1] * fx * (1 - fy) + tex[y1, x0] * (1 - fx) * fy + tex[y1, x1] * fx * fy)


def pine_cluster(seed: int = 197):
    """A belt of 5 pines of different heights on one billboard (forest edges far from the road)."""
    w, h = 256, 256
    out = np.zeros((h, w, 4))
    rs = np.random.RandomState(seed)
    single = np.asarray(pine(seed + 1)).astype(float) / 255.0
    for k in range(6):
        sc = 0.55 + 0.45 * rs.random_sample()
        tw, th = int(128 * sc * 0.9), int(256 * sc)
        img = Image.fromarray((single * 255).astype(np.uint8), "RGBA").resize((tw, th), Image.BILINEAR)
        a = np.asarray(img).astype(float) / 255.0
        x0 = int(rs.randint(-20, w - tw + 20))
        y0 = h - th
        dark = 0.7 + 0.3 * rs.random_sample()
        for yy in range(th):
            ty = y0 + yy
            if ty < 0 or ty >= h:
                continue
            xs0, xs1 = max(0, x0), min(w, x0 + tw)
            if xs1 <= xs0:
                continue
            src = a[yy, xs0 - x0:xs1 - x0]
            al = src[:, 3:4]
            dst = out[ty, xs0:xs1]
            dst[:, :3] = dst[:, :3] * (1 - al) + src[:, :3] * dark * al
            dst[:, 3:4] = np.maximum(dst[:, 3:4], al)
            out[ty, xs0:xs1] = dst
    return to_img(out, "RGBA")


def sky_faces(n: int, spec: dict, seed: int) -> dict[str, Image.Image]:
    """Clouds on a flat layer, sun or moon disc and glow, stars. Alpha lets skyColor show through."""
    cloud_tex = fbm(256, 256, seed, 3.2, 1.0, 20)
    cloud_tex2 = fbm(256, 256, seed + 1, 2.4, 4, 48)
    sun = np.array(spec["sun_dir"], dtype=float)
    sun = sun / np.linalg.norm(sun)
    out = {}
    for face in ("front", "back", "left", "right", "top", "bottom"):
        d = cube_dirs(n, face)
        dy = d[..., 1]
        rgb = np.zeros((n, n, 3))
        alpha = np.zeros((n, n))
        # clouds
        if spec.get("clouds", 0) > 0:
            up = np.clip(dy, 0.035, 1.0)
            t = spec.get("cloud_h", 1.0) / up
            cu = (d[..., 0] * t * spec.get("cloud_scale", 0.18)) % 1.0
            cv = (d[..., 2] * t * spec.get("cloud_scale", 0.18)) % 1.0
            dens = bilinear(cloud_tex, cu, cv) * 0.75 + bilinear(cloud_tex2, cu * 2.0 % 1.0, cv * 2.0 % 1.0) * 0.25
            cov = spec["clouds"]
            dens = np.clip((dens - (1 - cov)) / max(0.05, cov) * 1.8, 0, 1)
            fade = np.clip((dy - 0.02) / 0.18, 0, 1)
            dens = dens * fade * (dy > 0)
            facing = np.clip((d @ sun) * 0.5 + 0.5, 0, 1)
            lit = np.array(spec["cloud_lit"])
            shade = np.array(spec["cloud_shade"])
            cc = shade[None, None, :] + (lit - shade)[None, None, :] * (facing ** 2.0)[..., None]
            rim = np.clip(1 - dens * 1.6, 0, 1) * facing ** 3
            cc = cc + rim[..., None] * np.array(spec.get("cloud_rim", (0.2, 0.1, 0.0)))
            rgb = cc
            alpha = dens * spec.get("cloud_alpha", 0.9)
        # sun / moon disc and glow
        cosang = np.clip(d @ sun, -1, 1)
        ang = np.arccos(cosang)
        disc = np.clip((spec["disc"] - ang) / 0.004, 0, 1)
        glow = np.exp(-(ang / spec["glow_w"]) ** 1.3) * spec["glow_a"]
        gcol = np.array(spec["glow_col"])
        dcol = np.array(spec["disc_col"])
        a_g = np.clip(glow, 0, 1)
        rgb = rgb * alpha[..., None] * (1 - a_g[..., None]) + gcol * a_g[..., None]
        alpha = alpha + a_g * (1 - alpha)
        rgb = np.where(alpha[..., None] > 1e-4, rgb / np.maximum(alpha[..., None], 1e-4), rgb)
        if spec.get("moon"):
            crater = 0.85 + 0.15 * cloud_tex2[(np.clip(ang * 3000, 0, 255)).astype(int) % 256, 7]
            dcol_px = dcol[None, None, :] * crater[..., None]
        else:
            dcol_px = dcol[None, None, :] * np.ones((n, n, 1))
        rgb = rgb * (1 - disc[..., None]) + dcol_px * disc[..., None]
        alpha = np.maximum(alpha, disc)
        # stars
        if spec.get("stars"):
            rs = np.random.RandomState(seed + ("front", "back", "left", "right", "top", "bottom").index(face))
            st = rs.random_sample((n, n))
            star = (st > 0.9975) * np.clip(dy * 3, 0, 1) * (0.4 + 0.6 * rs.random_sample((n, n)))
            star = star * (1 - alpha)
            rgb = rgb * (1 - star[..., None]) + star[..., None] * np.array([0.9, 0.92, 1.0])
            alpha = np.maximum(alpha, star)
        alpha = alpha * (dy > -0.02)
        out[face] = to_img(np.concatenate([np.clip(rgb, 0, 1), np.clip(alpha, 0, 1)[..., None]], -1), "RGBA")
    return out
