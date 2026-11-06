#!/usr/bin/env python3
"""Image analysis helpers (PIL + numpy; analysis only, the generators stay stdlib).
  imgtools.py stats  a.png [b.png ...]          luminance/saturation/clipping/hue statistics
  imgtools.py diff   a.png b.png                mean/max abs difference, fraction of pixels differing > 8/255
  imgtools.py lw     lw.png x0                  vertical run lengths of bright pixels at column x0 (line thickness ladder)
  imgtools.py sbs    left.png right.png out.png [labelL labelR]   side-by-side, resized to the same height
"""
import sys
import numpy as np
from PIL import Image, ImageDraw


def load(p):
    return np.asarray(Image.open(p).convert('RGB')).astype(np.float32)


HUE_BINS = (("red", 345, 15), ("orange", 15, 45), ("yellow", 45, 70), ("green", 70, 160), ("cyan", 160, 200),
            ("blue", 200, 260), ("violet/magenta", 260, 345))


def stats(p):
    """Pixel statistics, instrument "imgtools stats v2" (2026-11-06). Hue shares count only pixels bright enough to
    carry colour (brightest channel above 0.25) AND saturated enough to have a hue (saturation above 0.2); bright
    pixels below that saturation (white, clipped highlights, grey) are reported as their own share, achromatic, and
    never given a hue. v1 gave hue 0 (red) to every grey and white pixel and had no orange bin: its red/orange and
    magenta shares are not comparable."""
    a = load(p) / 255.0
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    sat = np.where(mx > 0.0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    bright = mx > 0.25
    chroma = bright & (sat > 0.2)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    d = np.maximum(mx - mn, 1e-6)
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    tot = max(1, int(chroma.sum()))
    hist = {}
    for name, lo, hi in HUE_BINS:
        m = ((h >= lo) | (h < hi)) if lo > hi else ((h >= lo) & (h < hi))
        hist[name] = round(float(m[chroma].sum()) / tot, 3)
    return dict(instrument="imgtools stats v2", file=p, size=list(a.shape[1::-1]), mean_luma=round(float(lum.mean()), 4),
                p50=round(float(np.percentile(lum, 50)), 4), p99=round(float(np.percentile(lum, 99)), 4),
                frac_luma_gt_0_9=round(float((lum > 0.9).mean()), 5), frac_any_channel_255=round(float((mx >= 0.999).mean()), 5),
                frac_luma_gt_0_05=round(float((lum > 0.05).mean()), 4), bright_px_frac=round(float(bright.mean()), 4),
                achromatic_share_of_bright=round(float((bright & ~chroma).sum()) / max(1, int(bright.sum())), 3),
                mean_sat_bright=round(float(sat[bright].mean()) if bright.any() else 0, 3), hue_share=hist)


def diff(a, b):
    x, y = load(a), load(b)
    d = np.abs(x - y)
    return dict(a=a, b=b, mean_abs=round(float(d.mean()), 4), max_abs=float(d.max()), frac_gt8=round(float((d.max(-1) > 8).mean()), 5))


def lw(p, x0):
    a = load(p)[..., :].max(-1)
    col = a[:, int(x0)]
    runs, cur = [], 0
    for v in col:
        if v > 128:
            cur += 1
        elif cur:
            runs.append(cur); cur = 0
    if cur:
        runs.append(cur)
    return runs


def sbs(l, r, out, ll='', lr=''):
    A, B = Image.open(l).convert('RGB'), Image.open(r).convert('RGB')
    h = 540
    A = A.resize((int(A.width * h / A.height), h)); B = B.resize((int(B.width * h / B.height), h))
    im = Image.new('RGB', (A.width + B.width + 6, h + 22), (24, 24, 24))
    im.paste(A, (0, 22)); im.paste(B, (A.width + 6, 22))
    dr = ImageDraw.Draw(im); dr.text((6, 5), ll, fill=(255, 255, 255)); dr.text((A.width + 12, 5), lr, fill=(255, 255, 255))
    im.save(out)


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'stats':
        for p in sys.argv[2:]:
            print(stats(p))
    elif c == 'diff':
        print(diff(sys.argv[2], sys.argv[3]))
    elif c == 'lw':
        print(lw(sys.argv[2], sys.argv[3]))
    elif c == 'sbs':
        sbs(*sys.argv[2:])
