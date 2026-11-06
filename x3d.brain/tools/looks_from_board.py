#!/usr/bin/env python3
"""looks_from_board.py -- derive palette-only "looks" from a folder of style-board PNGs.

For every board image (named bNN-<style>.png) it measures, on a downscaled copy:
  * a 6-colour palette (seeded k-means++ in CIE Lab, numpy only),
  * the background gradient (median colour of the top and bottom bands, subject excluded),
  * rim / body / inner colours of the subject, the brightest saturated accent, the dominant fibre/glow hues,
  * a glow strength (halo leak outside the silhouette + share of bright saturated pixels),
  * a translucency estimate, an opaque ("wet") flag, a gloss estimate and a mood string,
and writes data/looks.json (a list of looks) plus data/looks.meta.json. Only numbers and hex colours are written:
no board pixels are stored in the output. Optional --thumbs DIR writes 480 px JPEG thumbnails that are re-encoded
through Pillow from raw pixels (so no metadata, XMP, IPTC or provenance manifests survive) and verified clean.

Each look carries a `push` list of [DEF, field, value] operations in the same format as presets.json, aimed at
the DEF names of the hero scene (BG, KEY, FILL, RIM, ENV, SH_CORTEX_L/R, MAT_WET_L/R, MAT_<structure>, SW_CORTEX, SW_WET).
Tract vertex colours override a line Material's emissiveColor, so tract tints are given as `tract.colors`
(core, halo1, halo2) for the page to write into the Color node of GEO_TRACTS instead.
Mapping from measurements to scene parameters is heuristic (looks first, physical accuracy secondary).

usage: looks_from_board.py BOARD_DIR [--out data/looks.json] [--thumbs DIR] [--seed 7] [--k 6] [--width 256]
needs: numpy, Pillow.   Deterministic: same images + same flags => byte-identical output.
"""
import argparse, glob, hashlib, json, math, os, re, sys
import numpy as np
from PIL import Image

VERSION = 1

# ------------------------------------------------------------------ hand-written look metadata (names and prose only; every colour is measured)
SURFACE = {"glass-fresnel": "glass", "wet-photoreal": "solid", "tractography-neon": "glass", "bioluminescent-neurons": "glass", "holographic-slices": "glass",
           "golden-cutaway": "solid", "vascular-angiogram": "glass", "museum-engraving": "solid", "fmri-heatmap": "solid", "volume-render-ivory": "solid",
           "cosmic-connectome": "glass", "wider-medical-ct": "glass"}   # which cortex group the look uses: see-through shell or opaque wet surface (judged from the reference, not measured)
STYLE = {
    "glass-fresnel": ("Crystal Cortex", "Translucent glass cortex with an iridescent cyan-to-magenta fresnel rim and gold deep structures glowing inside, on a black studio floor."),
    "wet-photoreal": ("Wet Specimen", "Macro of a glossy wet cortex: pink-ivory gyri, hair-fine red vessels, hard specular highlights, shallow depth of field."),
    "tractography-neon": ("Neon Tractography", "Direction-coloured fibre bundles (red left-right, green front-back, blue up-down) glowing inside a ghost-glass shell."),
    "bioluminescent-neurons": ("Bioluminescence", "Teal-blue neurons with spiny dendrites and violet signal pulses on a deep sea-dark ground; a mood for tract halos, not for the cortex."),
    "holographic-slices": ("Holo Slices", "Cyan hologram brain floating over a stack of MRI slices in a dim teal laboratory."),
    "golden-cutaway": ("Golden Cutaway", "Mid-sagittal cutaway: cream cortex, bronze and gold deep structures, warm library light, brass plinth."),
    "vascular-angiogram": ("Angiogram", "Crimson-amber vessels glowing inside a smoky grey ghost brain on black."),
    "museum-engraving": ("Museum Plate", "Engraved anatomical plate on aged parchment inside a brass frame with wax seals; a light, high-key look."),
    "fmri-heatmap": ("Heat Map", "Smooth slate-grey inflated cortex with light and dark curvature and red-orange-yellow activation blooms."),
    "volume-render-ivory": ("Ivory Volume", "Volume-rendered head: ivory skull, amber cortex and rose soft tissue on a graphite vignette."),
    "cosmic-connectome": ("Cosmic Connectome", "Brain outline made of galaxies with violet and gold connection arcs on a nebula backdrop."),
    "wider-medical-ct": ("Torso CT", "Blue glass skeleton, smoky lungs and a luminous red-gold heart and great vessels on near-black; for the torso scene."),
}
# Hand-set per-look shader weights (not measured): strength of the gyral outline band on the glass shell (0 = none), and whether the look is a see-through shell at all.
EDGE = {"glass-fresnel": 0.9, "wider-medical-ct": 0.6, "cosmic-connectome": 0.5, "holographic-slices": 0.5}
GOLD_CORE = ("thalamus", "pallidum", "hippocampus", "brainstem")        # glossy, opaque, glowing in the see-through looks; the other deep structures are faint ghosts
STRUCT_ORDER = ["thalamus", "caudate", "putamen", "pallidum", "hippocampus", "amygdala", "accumbens", "ventricles", "brainstem", "cerebellum"]
# per-structure (hue shift in degrees, value multiplier, emissive share, metallic) applied to the look's `inner` colour
STRUCT_VARY = dict(thalamus=(0, 1.00), caudate=(-8, 0.90), putamen=(6, 0.95), pallidum=(10, 1.05), hippocampus=(4, 1.00),
                   amygdala=(-14, 0.95), accumbens=(14, 1.05), brainstem=(-2, 0.95), cerebellum=(-10, 0.78))

# ------------------------------------------------------------------ colour maths
def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

def rgb_to_lab(rgb):
    lin = srgb_to_lin(np.clip(rgb, 0, 1))
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)

def rgb_to_hsv(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn
    h = np.zeros_like(mx)
    nz = d > 1e-9
    rc = nz & (mx == r); gc = nz & (mx == g) & ~rc; bc = nz & ~rc & ~gc
    h[rc] = ((g - b)[rc] / d[rc]) % 6
    h[gc] = (b - r)[gc] / d[gc] + 2
    h[bc] = (r - g)[bc] / d[bc] + 4
    s = np.where(mx > 1e-9, d / np.maximum(mx, 1e-9), 0.0)
    return np.stack([h * 60.0, s, mx], -1)

def hsv_to_rgb(h, s, v):
    h = (h % 360) / 60.0; c = v * s; x = c * (1 - abs(h % 2 - 1)); m = v - c
    i = int(h) % 6
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][i]
    return np.array([r + m, g + m, b + m])

def hexs(rgb):
    return "#%02X%02X%02X" % tuple(int(round(float(np.clip(x, 0, 1)) * 255)) for x in rgb)

def fl3(rgb):
    return " ".join("%.3f" % float(np.clip(x, 0, 1)) for x in rgb)

def lightness(rgb):
    return float(rgb_to_lab(np.asarray(rgb, float))[0] / 100.0)

def with_value(rgb, v):
    h, s, _ = rgb_to_hsv(np.asarray(rgb, float)); return hsv_to_rgb(h, s, v)

def sat_floor(rgb, smin):
    """Raise HSV saturation to at least `smin` (hue and value kept). The board rims are pastel because of bloom; the shader's rim has to carry its hue after tone mapping."""
    h, sat, v = rgb_to_hsv(np.asarray(rgb, float)); return hsv_to_rgb(h, max(float(sat), smin), v)

def scale_to_lightness(rgb, target):
    """Scale linear light so CIE L*/100 matches `target` (keeps hue; used to make stage colours HUD-safe)."""
    rgb = np.asarray(rgb, float); cur = lightness(rgb)
    if cur <= target or cur <= 1e-6: return rgb
    lo, hi = 0.0, 1.0
    for _ in range(24):
        mid = (lo + hi) / 2
        if lightness(rgb * mid) > target: hi = mid
        else: lo = mid
    return rgb * lo

HUE_BANDS = [(15, "red"), (35, "orange"), (52, "amber"), (70, "yellow"), (160, "green"), (200, "cyan"), (255, "blue"), (290, "violet"), (335, "magenta"), (361, "red")]
def hue_name(h):
    h = h % 360
    for hi, n in HUE_BANDS:
        if h < hi: return n
    return "red"

def mix(a, b, t):
    return np.asarray(a, float) * (1 - t) + np.asarray(b, float) * t

# ------------------------------------------------------------------ k-means (numpy, seeded)
def kmeans(X, k, seed, iters=40, restarts=3):
    rng = np.random.default_rng(seed); best = None
    for _ in range(restarts):
        C = [X[rng.integers(len(X))]]
        for _j in range(1, k):
            d2 = np.min(((X[:, None, :] - np.array(C)[None]) ** 2).sum(-1), axis=1)
            C.append(X[rng.choice(len(X), p=d2 / d2.sum())] if d2.sum() > 0 else X[rng.integers(len(X))])
        C = np.array(C)
        for _it in range(iters):
            d = ((X[:, None, :] - C[None]) ** 2).sum(-1); lab = d.argmin(1)
            newC = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
            done = np.allclose(newC, C, atol=1e-4); C = newC
            if done: break
        d = ((X[:, None, :] - C[None]) ** 2).sum(-1); lab = d.argmin(1)
        inertia = float(d[np.arange(len(X)), lab].sum())
        if best is None or inertia < best[0]: best = (inertia, C, lab)
    return best[1], best[2]

# ------------------------------------------------------------------ binary morphology (square element, no scipy)
def _shift_or(mask, r, op):
    h, w = mask.shape; pad = np.pad(mask, r, constant_values=(op == "erode"))
    out = mask.copy() if op == "dilate" else np.ones_like(mask)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            sl = pad[r + dy:r + dy + h, r + dx:r + dx + w]
            out = (out | sl) if op == "dilate" else (out & sl)
    return out
def dilate(m, r): return _shift_or(m, r, "dilate") if r > 0 else m
def erode(m, r): return _shift_or(m, r, "erode") if r > 0 else m

def boxblur(a, r):
    k = 2 * r + 1; p = np.pad(a, r, mode="edge"); c = np.pad(np.cumsum(np.cumsum(p, 0), 1), ((1, 0), (1, 0))); h, w = a.shape
    return (c[k:k + h, k:k + w] - c[:h, k:k + w] - c[k:k + h, :w] + c[:h, :w]) / (k * k)

# ------------------------------------------------------------------ hue peaks
def hue_peaks(hsv, rgb, weights, n=3, sep_bins=5, bins=36):
    """Greedy circular hue-histogram peaks. Returns [(hue_deg, weight_share, mean_rgb)]."""
    h = hsv[:, 0]; idx = (h / (360 / bins)).astype(int) % bins
    hist = np.bincount(idx, weights=weights, minlength=bins)
    sm = hist + 0.5 * (np.roll(hist, 1) + np.roll(hist, -1)); tot = sm.sum() + 1e-12
    out = []
    for _ in range(n):
        b = int(sm.argmax())
        if sm[b] <= 0.02 * tot: break
        centre = (b + 0.5) * (360 / bins)
        dh = np.abs((h - centre + 180) % 360 - 180); near = (dh <= 22) & (weights > 0)
        if near.sum() == 0: break
        w = weights[near]; ang = np.deg2rad(h[near])
        hue = float(np.rad2deg(np.arctan2((np.sin(ang) * w).sum(), (np.cos(ang) * w).sum())) % 360)
        out.append((hue, float(sm[b] / tot), (rgb[near] * w[:, None]).sum(0) / w.sum()))
        for o in range(-sep_bins, sep_bins + 1): sm[(b + o) % bins] = 0
    return out

# ------------------------------------------------------------------ connected components (4-neighbour, small images only)
def components(mask):
    H, W = mask.shape; lab = np.zeros((H, W), int); sizes = []; n = 0
    for y0 in range(H):
        for x0 in range(W):
            if mask[y0, x0] and not lab[y0, x0]:
                n += 1; st = [(y0, x0)]; lab[y0, x0] = n; c = 0
                while st:
                    y, x = st.pop(); c += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not lab[yy, xx]:
                            lab[yy, xx] = n; st.append((yy, xx))
                sizes.append(c)
    return lab, sizes

# ------------------------------------------------------------------ one board image
def analyse(path, idx, seed, k, width):
    name = os.path.basename(path); m = re.match(r"(b\d+)-(.+)\.png$", name, re.I)
    board, slug = (m.group(1).lower(), m.group(2).lower()) if m else ("b%02d" % idx, os.path.splitext(name)[0])
    img = Image.open(path).convert("RGB"); w0, h0 = img.size
    sm = img.resize((width, max(8, round(width * h0 / w0))), Image.LANCZOS)
    px = np.asarray(sm, float) / 255.0; H, W = px.shape[:2]
    flat = px.reshape(-1, 3); lab = rgb_to_lab(flat); hsv = rgb_to_hsv(flat); L = lab[:, 0] / 100.0; C = np.hypot(lab[:, 1], lab[:, 2])
    centres, lbl = kmeans(lab, k, seed + idx)
    share = np.array([(lbl == j).mean() for j in range(k)])
    pal_rgb = np.array([flat[lbl == j].mean(0) if (lbl == j).any() else np.zeros(3) for j in range(k)])
    order = np.argsort(-share)
    # background clusters: dominate the border ring, or sit mostly in the peripheral zone
    yy, xx = np.mgrid[0:H, 0:W]; edge = np.minimum(np.minimum(yy, H - 1 - yy), np.minimum(xx, W - 1 - xx))
    ringf = (edge < max(2, round(0.06 * min(H, W)))).reshape(-1); perif = (edge < 0.10 * min(H, W)).reshape(-1)
    bgc = []
    for j in range(k):
        mj = lbl == j
        if not mj.any(): continue
        rsh = (ringf & mj).sum() / ringf.sum(); pf = (perif & mj).sum() / mj.sum()
        if (rsh >= 0.08 and pf >= 0.45) or rsh >= 0.35: bgc.append(j)
    if not bgc: bgc = [int(np.argmax([(ringf & (lbl == j)).sum() for j in range(k)]))]
    bgmask = np.isin(lbl, bgc).reshape(H, W)
    subject = dilate(erode(~bgmask, 1), 1)
    lab_cc, sizes = components(subject)
    if sizes: subject = np.isin(lab_cc, [c + 1 for c, n_ in enumerate(sizes) if n_ >= 0.25 * max(sizes)])
    fullframe = subject.mean() > 0.85 or subject.mean() < 0.04
    if subject.mean() < 0.04: subject = np.ones((H, W), bool)
    # filled silhouette (closing + enclosed holes)
    rs = lambda r: max(1, int(round(r * W / 192.0)))   # morphology radii are given for a 192 px wide analysis copy
    closed = erode(dilate(subject, rs(5)), rs(5)); out_l, _ = components(~closed)
    edge_ids = set(out_l[0, :]) | set(out_l[-1, :]) | set(out_l[:, 0]) | set(out_l[:, -1]); edge_ids.discard(0)
    filled = closed | ((out_l > 0) & ~np.isin(out_l, list(edge_ids))); filled |= subject
    fg = subject.reshape(-1)
    # background gradient: median of the top / bottom bands, subject excluded when possible
    band = max(2, int(round(0.07 * H)))
    def band_median(rows):
        sel = np.zeros((H, W), bool); sel[rows] = True
        use = sel & bgmask
        if use.sum() < 0.12 * sel.sum(): use = sel
        return np.median(px[use], axis=0)
    top, bot = band_median(slice(0, band)), band_median(slice(H - band, H))
    # rim / body
    inner_mask = erode(subject, rs(2)); rim_band = subject & ~erode(subject, rs(3))
    if rim_band.sum() < 20: rim_band = subject
    if inner_mask.sum() < 50: inner_mask = subject
    rb = rim_band.reshape(-1); sel = np.where(rb)[0]
    lit = sel[(hsv[sel, 1] >= 0.18) & (hsv[sel, 2] >= 0.45)]
    if len(lit) >= 15: top_sel = lit[np.argsort(-(hsv[lit, 2] * hsv[lit, 1]))[:max(8, int(0.35 * len(lit)))]]
    else: top_sel = sel[np.argsort(-(L[sel] + 0.012 * C[sel]))[:max(8, int(0.30 * len(sel)))]]
    rim = flat[top_sel].mean(0); rim2 = None
    rp = []
    if len(lit) >= 15:   # a two-tone rim (e.g. cyan and lilac) must not average to grey: keep the strongest hue peaks of the lit rim pixels (the second one is chosen after the accent is known, below)
        rp = hue_peaks(hsv[lit], flat[lit], hsv[lit, 1] * hsv[lit, 2], n=4)
        if rp: rim = with_value(rp[0][2], max(0.75, float(rgb_to_hsv(rp[0][2])[2])))
    ib = np.where(inner_mask.reshape(-1))[0]; lo, hi = np.percentile(L[ib], [50, 95]); mid = ib[(L[ib] >= lo) & (L[ib] <= hi)]
    body = np.median(flat[mid if len(mid) > 20 else ib], axis=0)
    # accent: brightest saturated colour (weights emphasise the brightest pixels)
    fgi = np.where(fg)[0]; S, V = hsv[fgi, 1], hsv[fgi, 2]
    ok = fgi[(S >= 0.45) & (V >= 0.6)]
    if len(ok) < 30: ok = fgi[(S >= 0.30) & (V >= 0.45)]
    if len(ok) < 30: ok = fgi[np.argsort(-(hsv[fgi, 1] * hsv[fgi, 2]))[:60]]
    sc = hsv[ok, 2] ** 2 * hsv[ok, 1]; ok = ok[np.argsort(-sc)[:max(30, int(0.04 * len(ok)))]]
    pk = hue_peaks(hsv[ok], flat[ok], (hsv[ok, 2] ** 2 * hsv[ok, 1]) ** 2, n=1)
    accent = with_value(pk[0][2], max(0.85, float(rgb_to_hsv(pk[0][2])[2]))) if pk else with_value(rim, 0.9)
    # second rim hue: the next-strongest rim hue peak (share >= 2 percent) at least 40 degrees from both the first peak and the accent. The accent is excluded because on see-through
    # shells it is the glowing core showing through the rim band (gold on the glass board), not a rim colour.
    hd = lambda p, q: abs((p - q + 180) % 360 - 180)
    h_accent = float(rgb_to_hsv(accent)[0])
    for q in rp[1:]:
        if q[1] >= 0.02 and hd(q[0], rp[0][0]) >= 40 and hd(q[0], h_accent) >= 40:
            rim2 = with_value(q[2], max(0.75, float(rgb_to_hsv(q[2])[2]))); break
    # dominant glow / fibre hues over the whole subject
    wt = np.where((hsv[fgi, 1] > 0.30) & (hsv[fgi, 2] > 0.35), hsv[fgi, 1] * hsv[fgi, 2] ** 2, 0.0)
    peaks = hue_peaks(hsv[fgi], flat[fgi], wt, n=3)
    tract_hue = round(peaks[0][0]) if peaks else round(float(rgb_to_hsv(accent)[0]))
    tcols = [with_value(p[2], max(0.8, float(rgb_to_hsv(p[2])[2]))) for p in peaks]
    while len(tcols) < 3: tcols.append(mix(tcols[-1] if tcols else accent, np.ones(3), 0.25 * len(tcols)))
    # inner: most hue-distinct, chromatic, central cluster of the subject
    hb = rgb_to_hsv(body)[0]; ys, xs = np.nonzero(subject); cy, cx = ys.mean() / H, xs.mean() / W; best = (-1, None)
    for j in range(k):
        if j in bgc or share[j] < 0.012: continue
        cj = np.hypot(centres[j, 1], centres[j, 2])
        if cj < 14: continue
        hj = rgb_to_hsv(pal_rgb[j])[0]; m_j = (lbl == j).reshape(H, W) & subject
        if m_j.sum() < 12: continue
        yj, xj = np.nonzero(m_j); dist = math.hypot(yj.mean() / H - cy, xj.mean() / W - cx)
        dh = abs((hj - hb + 180) % 360 - 180) / 180.0
        s_ = min(cj / 45.0, 1.0) + dh * 0.8 + (1 - min(dist / 0.35, 1.0)) * 0.5 + min(share[j] / 0.08, 1.0) * 0.3
        if s_ > best[0]: best = (s_, pal_rgb[j])
    inner = best[1] if best[1] is not None else body * 0.75
    # glow: halo leak outside the silhouette (bloom) + a small share for bright saturated pixels
    Lh = L.reshape(H, W); ring2 = dilate(filled, rs(9)) & ~dilate(filled, rs(2)); far = ~dilate(filled, rs(22)) & bgmask
    base_L = float(np.median(Lh[far])) if far.sum() > 30 else float(np.percentile(L, 5))
    halo_L = float(Lh[ring2].mean()) if ring2.sum() > 30 and subject.mean() < 0.70 else base_L   # no silhouette halo when the subject fills the frame
    rim_L = float(L[rb].mean()) if rb.any() else 0.5
    halo_gain = max(0.0, (halo_L - base_L) / max(0.05, rim_L - base_L))
    emis = float(((hsv[fgi, 1] > 0.5) & (hsv[fgi, 2] > 0.75)).mean())
    # glow = emissive hot spots (bright saturated pixels that stand out from their surround) + a luminous saturated rim on a dark stage + bloom around the silhouette
    Vh = hsv[:, 2].reshape(H, W); Sh = hsv[:, 1].reshape(H, W); r_ = max(3, int(round(0.03 * W)))
    spots = float((((Vh - boxblur(Vh, r_)) > 0.12) & (Sh > 0.45) & (Vh > 0.7)).mean())
    rim_sv = float((hsv[top_sel, 1] * hsv[top_sel, 2]).mean()); dark_stage = float(np.clip((0.30 - base_L) / 0.15, 0, 1))
    g_spot = float(np.clip(spots / 0.06, 0, 1)); g_rim = float(np.clip((rim_sv - 0.25) / 0.35, 0, 1)) * dark_stage; g_halo = float(np.clip(halo_gain / 0.30, 0, 1))
    bright_rim = float((hsv[sel, 2] > 0.85).mean()) if len(sel) else 0.0; g_edge = float(np.clip((bright_rim - 0.10) / 0.30, 0, 1)) * dark_stage
    glow = float(np.clip(0.50 * g_spot + 0.20 * g_rim + 0.20 * g_edge + 0.10 * g_halo, 0, 1))
    # translucency proxy: a see-through shell is brighter at its rim than in its core (fresnel); solids are not
    core = erode(filled, max(3, int(0.06 * W))); core_L = float(Lh[core].mean()) if core.sum() > 20 else rim_L
    transp = float(np.clip(1.0 - core_L / max(rim_L, 0.05), 0, 1))
    ibf = erode(filled, rs(2)).reshape(-1)
    spec = float(((hsv[ibf, 2] > 0.9) & (hsv[ibf, 1] < 0.25)).mean()) if ibf.any() else 0.0
    rough = float(np.clip(0.55 - 7.0 * spec, 0.18, 0.7))
    # contrast and mood (chroma and temperature are taken over the lit pixels of the subject)
    p5, p95 = np.percentile(L, [5, 95]); contrast = float(p95 - p5)
    litf = fgi[L[fgi] > 0.30]; litf = litf if len(litf) > 30 else fgi; wl = np.maximum(C[litf], 1.0)
    fchroma = float(C[litf].mean()); temp = float(((lab[litf, 2] + 0.3 * lab[litf, 1]) * wl).sum() / wl.sum())
    keyL = float(L.mean())
    words = ["warm" if temp > 8 else "cool" if temp < -8 else "neutral",
             "low-key" if keyL < 0.25 else "high-key" if keyL > 0.60 else "mid-key",
             "vivid" if fchroma > 38 else "rich" if fchroma > 22 else "muted",
             "high-contrast" if contrast > 0.62 else "soft-contrast" if contrast < 0.35 else "medium-contrast",
             "luminous" if glow > 0.55 else "softly glowing" if glow > 0.25 else "matte"]
    hues = []
    for p in peaks[:2]:
        n = hue_name(p[0]); hues.append(n) if n not in hues else None
    mood = ", ".join(words) + ("; " + " and ".join(hues) if hues else "")
    meas = dict(glow=round(glow, 3), halo_gain=round(halo_gain, 3), emissive_share=round(emis, 3), hot_spot_share=round(spots, 4), rim_vividness=round(rim_sv, 3), bright_rim_share=round(bright_rim, 3), translucency_proxy=round(transp, 3), rim_lightness=round(rim_L, 3), core_lightness=round(core_L, 3),
                gloss_share=round(spec, 4), contrast=round(contrast, 3), key_lightness=round(keyL, 3), lit_chroma=round(fchroma, 1), temperature=round(temp, 1),
                subject_share=round(float(subject.mean()), 3), fullframe=bool(fullframe), bg_clusters=[int(j) for j in bgc])
    pal = [dict(hex=hexs(pal_rgb[j]), share=round(float(share[j]), 4)) for j in order]
    return dict(board=board, slug=slug, size=[w0, h0], top=top, bot=bot, rim=rim, rim2=rim2, body=body, inner=inner, accent=accent, tract_hue=tract_hue, tcols=tcols[:3],
                peaks=[round(p[0]) for p in peaks], glow=glow, transp=transp, rough=rough, contrast=contrast, key_lightness=keyL, mood=mood, pal=pal, meas=meas)

# ------------------------------------------------------------------ scene parameters (heuristic, documented in the module docstring)
def stage_safe(rgb, max_l=0.30):
    return scale_to_lightness(rgb, max_l)

def make_look(a):
    name, desc = STYLE.get(a["slug"], (a["slug"].replace("-", " ").title(), "Style board look."))
    top_s, bot_s = stage_safe(a["top"]), stage_safe(a["bot"]); mid_s = mix(top_s, bot_s, 0.5)
    glow = a["glow"]; wet = SURFACE.get(a["slug"], "glass") == "solid"
    alpha = 1.0 if wet else float(np.clip(0.5 * (1.0 - a["transp"]), 0.06, 0.40))   # surface opacity: 1 = opaque wet cortex, glass looks 0.06..0.40
    body_v = with_value(a["body"], max(0.50, float(rgb_to_hsv(a["body"])[2])))
    h_rim = float(rgb_to_hsv(a["rim"])[0]); h_acc = float(rgb_to_hsv(a["accent"])[0])
    if a.get("rim2") is not None: rim2 = a["rim2"]
    elif abs((h_acc - h_rim + 180) % 360 - 180) >= 40: rim2 = a["accent"]
    else: rim2 = with_value(hsv_to_rgb(h_rim + 45, max(0.35, float(rgb_to_hsv(a["rim"])[1])), 1.0), 1.0)
    white = np.ones(3); c = float(np.clip(a["contrast"], 0, 1))
    key_c = mix(white, body_v, 0.22); fill_c = mix(white, with_value(a["top"] if lightness(a["top"]) > 0.02 else a["rim"], 0.9), 0.55); rim_c = mix(white, a["accent"], 0.55)
    key_i = round(1.1 + 1.6 * c, 2); fill_i = round(0.45 + 0.5 * (1 - c), 2); rim_i = round(0.5 + 1.3 * glow, 2)
    base_a = round(float(np.clip(0.015 + 0.06 * alpha, 0.015, 0.1)), 3)   # shader baseAlpha (only used by see-through looks): clear glass, the rim and sulci carry the look
    rim_a = round(0.75 + 0.25 * glow, 2); rim_p = round(2.6 - 1.2 * glow, 2)
    lift = lambda c: with_value(sat_floor(c, 0.6), max(0.95, float(rgb_to_hsv(c)[2])))
    rim_s, rim2_s = (a["rim"], rim2) if wet else (lift(a["rim"]), lift(rim2))   # measured hue; saturation floor 0.6 and value floor 0.95 for the see-through rim (bloom washes the board rim out)
    sulc = mix(rim_s, np.zeros(3), 0.93) if not wet else mix(body_v, np.zeros(3), 0.88)
    push = [["SW_CORTEX", "whichChoice", -1 if wet else 0], ["SW_WET", "whichChoice", 0 if wet else -1],
            ["BG", "skyColor", " ".join([fl3(top_s), fl3(mix(top_s, mid_s, 0.5)), fl3(mid_s)])],
            ["BG", "groundColor", " ".join([fl3(bot_s), fl3(mix(bot_s, mid_s, 0.5)), fl3(mid_s)])],
            ["KEY", "color", fl3(key_c)], ["KEY", "intensity", key_i], ["FILL", "color", fl3(fill_c)], ["FILL", "intensity", fill_i],
            ["RIM", "color", fl3(rim_c)], ["RIM", "intensity", rim_i], ["ENV", "intensity", round(0.7 + 0.5 * a["key_lightness"] + (0.2 if wet else 0), 2)]]
    if wet:
        push.append(["SW_STAGE", "whichChoice", -1])      # the cool blue stage pool and halo clash with the warm opaque looks

    for h in "LR":
        push += [[f"SH_CORTEX_{h}", "rimColor", fl3(rim_s)], [f"SH_CORTEX_{h}", "rimColor2", fl3(rim2_s)], [f"SH_CORTEX_{h}", "bodyColor", fl3(body_v)],
                 [f"SH_CORTEX_{h}", "edgeColor", fl3(mix(rim_s, white, 0.55))], [f"SH_CORTEX_{h}", "edgeAlpha", EDGE.get(a["slug"], 0.3)],
                 [f"SH_AURA_{h}", "auraColor", fl3(rim_s)], [f"SH_AURA_{h}", "auraColor2", fl3(rim2_s)], [f"SH_AURA_{h}", "auraAlpha", round(0.6 + 0.4 * glow, 2)],
                 [f"SH_CORTEX_{h}", "sulcColor", fl3(sulc)], [f"SH_CORTEX_{h}", "rimPower", rim_p], [f"SH_CORTEX_{h}", "baseAlpha", base_a], [f"SH_CORTEX_{h}", "rimAlpha", rim_a],
                 [f"MAT_WET_{h}", "baseColor", fl3(body_v)], [f"MAT_WET_{h}", "roughness", round(a["rough"], 2)]]
    # see-through looks: the glowing core takes the measured saturated accent (60 percent) over the muted average of the inner pixels, which read as ivory porcelain
    inner_src = a["inner"] if wet else mix(a["inner"], a["accent"], 0.6)
    inner_c = with_value(inner_src, max(0.60, float(rgb_to_hsv(inner_src)[2])))
    if not wet: inner_c = sat_floor(inner_c, 0.8)             # a glowing core needs a saturated colour to survive tone mapping (pale gold turns cream)
    ih, isat, _iv = rgb_to_hsv(inner_c); metal = 0.85 if (name in ("Golden Cutaway",)) else (0.5 if wet else 0.9)
    emis_share = round(0.25 + 0.30 * glow, 2) if wet else round(0.45 + 0.30 * glow, 2)
    structs = {}
    for k_ in STRUCT_ORDER:
        if k_ == "ventricles":
            col = mix(rim_s, white, 0.2); structs[k_] = hexs(col)
            push += [["MAT_ventricles", "baseColor", fl3(col)], ["MAT_ventricles", "emissiveColor", fl3(col * 0.3)], ["MAT_ventricles", "transparency", 0.9]]; continue
        if k_ == "cerebellum" and not wet:                     # see-through looks: the cerebellum is a cool ghost in the rim colour, not a second gold core
            col = rim_s * 0.75; structs[k_] = hexs(col)
            push += [[f"MAT_{k_}", "baseColor", fl3(col)], [f"MAT_{k_}", "emissiveColor", fl3(col * 0.14)], [f"MAT_{k_}", "metallic", 0.0], [f"MAT_{k_}", "roughness", 0.65], [f"MAT_{k_}", "transparency", 0.76]]; continue
        dh, vm = STRUCT_VARY[k_]; col = hsv_to_rgb(ih + dh, isat, min(1.0, max(0.35, _iv * vm)))
        structs[k_] = hexs(col)
        core = wet or k_ in GOLD_CORE
        push += [[f"MAT_{k_}", "baseColor", fl3(col)], [f"MAT_{k_}", "emissiveColor", fl3(col * emis_share)], [f"MAT_{k_}", "metallic", metal],
                 [f"MAT_{k_}", "roughness", 0.3 if wet else (0.14 if core else 0.24)], [f"MAT_{k_}", "transparency", 0 if core else 0.9]]
    hex3 = lambda v: [hexs(x) for x in v]
    notes = (f"{desc} Measured on a {a['size'][0]}x{a['size'][1]} private style reference (palette only, image not shipped): "
             f"bg {hexs(a['top'])} to {hexs(a['bot'])}{' (stage colours darkened for HUD contrast)' if (hexs(top_s) != hexs(a['top']) or hexs(bot_s) != hexs(a['bot'])) else ''}; "
             f"glow {glow:.2f}, rim/core lightness {a['meas']['rim_lightness']:.2f}/{a['meas']['core_lightness']:.2f}, {'opaque wet surface' if wet else 'see-through shell'}. "
             f"Use `push` for scene fields; `tract.colors` recolours GEO_TRACTS.")
    return dict(id=a["slug"], board=a["board"], name=name, style=a["slug"], background=hex3([top_s, bot_s]), background_measured=hex3([a["top"], a["bot"]]),
                stage_light=bool(lightness(a["top"]) > 0.45 and lightness(a["bot"]) > 0.45), rim=hexs(rim_s), body=hexs(body_v), inner=hexs(inner_c), accent=hexs(a["accent"]), rim2=hexs(rim2_s),
                tract_hue=a["tract_hue"], tract=dict(hues=a["peaks"], colors=hex3(a["tcols"]), mode="direction" if a["slug"] == "tractography-neon" else "tint"),
                glow=round(glow, 3), alpha=round(alpha, 3), wet=bool(wet), roughness=round(a["rough"], 2), mood=a["mood"], structures=structs,
                palette=a["pal"], measured=a["meas"], push=push, notes=notes)

# ------------------------------------------------------------------ thumbnails (metadata-free)
# Provenance and metadata markers a clean thumbnail must not carry, written in fragments so this source file contains none of them.
BAD = [b"c2" + b"pa", b"jum" + b"b", b"jum" + b"d", b"xm" + b"p", b"<x:xm" + b"pmeta", b"ns.ad" + b"obe.com", b"photo" + b"shop", b"ip" + b"tc", b"ex" + b"if", b"content" + b"auth", b"ca" + b"wg"]
def jpeg_segments(data):
    i = 2; segs = []
    while i + 4 <= len(data) and data[0:2] == b"\xff\xd8":
        if data[i] != 0xFF: break
        mk = data[i + 1]
        if mk == 0xDA: break
        ln = int.from_bytes(data[i + 2:i + 4], "big"); segs.append((mk, data[i + 4:i + 2 + ln][:12])); i += 2 + ln
    return segs

def write_thumb(src, dst, width=480, quality=82):
    im = Image.open(src).convert("RGB"); clean = Image.frombytes("RGB", im.size, im.tobytes())   # fresh image: nothing from info{} survives
    clean = clean.resize((width, round(width * im.size[1] / im.size[0])), Image.LANCZOS)
    clean.save(dst, "JPEG", quality=quality, optimize=True, progressive=False)
    data = open(dst, "rb").read(); low = data.lower()
    hits = [b.decode() for b in BAD if b in low]; segs = [("APP%d" % (m - 0xE0) if 0xE0 <= m <= 0xEF else "0x%02X" % m) for m, _ in jpeg_segments(data)]
    app = [s for s in segs if s.startswith("APP")]
    ok = not hits and set(app) <= {"APP0"}
    return dict(file=os.path.basename(dst), bytes=len(data), size=list(clean.size), sha256=hashlib.sha256(data).hexdigest(), markers=segs, forbidden_hits=hits, clean=ok)

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("board_dir"); ap.add_argument("--out", default="data/looks.json"); ap.add_argument("--thumbs"); ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--k", type=int, default=6); ap.add_argument("--width", type=int, default=256)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.board_dir, "b*.png")))
    if not files: sys.exit("no b*.png in " + a.board_dir)
    looks = []; thumbs = []
    for i, f in enumerate(files, 1):
        r = analyse(f, i, a.seed, a.k, a.width); looks.append(make_look(r))
        lk = looks[-1]; print("%s %-26s bg %s->%s rim %s body %s inner %s accent %s glow %.2f alpha %.2f wet %s | %s" % (lk["board"], lk["id"], lk["background"][0], lk["background"][1], lk["rim"], lk["body"], lk["inner"], lk["accent"], lk["glow"], lk["alpha"], lk["wet"], lk["mood"]))
        if a.thumbs:
            os.makedirs(a.thumbs, exist_ok=True); t = write_thumb(f, os.path.join(a.thumbs, r["board"] + ".jpg")); thumbs.append(t)
            print("   thumb", t["file"], t["bytes"], "bytes", t["size"], "markers", t["markers"], "clean" if t["clean"] else "NOT CLEAN " + str(t["forbidden_hits"]))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    txt = json.dumps(looks, indent=1, ensure_ascii=False) + "\n"
    open(a.out, "w").write(txt); sha = hashlib.sha256(txt.encode()).hexdigest()
    meta = dict(tool="looks_from_board.py", version=VERSION, seed=a.seed, k=a.k, analysis_width=a.width, looks=len(looks), looks_sha256=sha,
                notice="Palette-only data measured from a private set of style-reference images (not shipped; no image pixels in this file). Colours are hex or sRGB floats; "
                       "`push` entries are [DEF, field, value] operations for the hero scene. Illustrative styling, not measurements of any anatomy.")
    open(os.path.splitext(a.out)[0] + ".meta.json", "w").write(json.dumps(meta, indent=1) + "\n")
    print("looks", len(looks), "bytes", len(txt.encode()), "sha256", sha)
    if a.thumbs:
        bad = [t["file"] for t in thumbs if not t["clean"]]
        print("thumbs", len(thumbs), "all clean" if not bad else "NOT CLEAN: %s" % bad)
        if bad: sys.exit(2)

if __name__ == "__main__":
    main()
