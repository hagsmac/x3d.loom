#!/usr/bin/env python3
"""Generate the KANSEI world: circuits, cars, the garage and every texture (Loom law 1: generator, not file).

  python3 -I build/build_world.py            write levels/, cars/, garage.x3d, textures/ and both MANIFESTs
  python3 -I build/build_world.py --check    rebuild in memory; exit 1 unless every output is byte-identical
  python3 -I build/build_world.py --only kessel-pass   (development: build one circuit, skip the rest;
                                                       --only cars builds the cars and the garage)

Standard library + numpy + PIL. No clock, fixed seeds, fixed number formats.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True          # keep build/ free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ============================================================================================
# TARGETS: medal targets per circuit for a stock RONIN on the dry (engine/race.js medalTargets scales
# them for the other cars, the wet and the grip tune). Laps and the four circuits' rush tiers are
# calibrated from tools/bot.mjs runs (RONIN, dry, skill 1, two attack laps and one 90 s Drift Rush;
# docs/HANDLING-CARD.md lists the runs): gold lap = bot lap x 1.02, silver x 1.08, bronze x 1.16;
# rush bronze = bot score x 0.35, silver x 0.6, gold x 0.85, platinum x 1.1 (CONTRACT.md section 10).
# The Practice Pad is for learning to hold angle, and the bot's near-perfect circle (177268) is no
# measure of a person, so its rush tiers come from the keyboard driver in tests/keyboard.test.mjs
# (55-70k for the RWD cars on the dry): bronze 25k, silver 45k, gold 70k, platinum 120k.
#            goldLap silverLap bronzeLap  rushBronze rushSilver rushGold rushPlatinum
TARGETS = {
    "kessel-pass":   (80.3, 85.0, 91.3,  3650,   6250,   8850,  11500),   # bot lap 78.745, rush 10435
    "neon-overpass": (78.8, 83.5, 89.6,  9800,  16850,  23850,  30900),   # bot lap 77.277, rush 28070
    "salt-ring":     (49.8, 52.8, 56.7, 12500,  21400,  30300,  39250),   # bot lap 48.864, rush 35666
    "cliffside":     (86.6, 91.7, 98.5,  3900,   6700,   9500,  12300),   # bot lap 84.886, rush 11170
    "practice-pad":  (14.6, 15.5, 16.6, 25000,  45000,  70000, 120000),   # bot lap 14.317; keyboard rush 61k
}
# ============================================================================================

import numpy as np  # noqa: E402

import ktex  # noqa: E402
from kx3d import Looks, Mesh, RNG, col, fnum, look_rotation, mfstr, rot_str, shape, vec, x3d_doc  # noqa: E402
from ktrack import CURB_BAND, Circuit, periodic_smooth, runs, span  # noqa: E402
import kscenery as K  # noqa: E402
import kcars  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GEN = "x3d.drift/build/build_world.py"
LEVEL_TEX = ("../textures/", "textures/")   # works loaded from levels/ or as a string from the page root
COMPONENTS = [("Shape", 2), ("Texturing", 2), ("Lighting", 3), ("EnvironmentalEffects", 3), ("Navigation", 2)]


def fixed_nz(v: float, d: int) -> str:
    """Fixed decimals without a negative zero."""
    t = f"{v:.{d}f}"
    return t[1:] if t.startswith("-") and float(t) == 0.0 else t


def heights_from_poly(poly, hs):
    """Road height: periodic Catmull-Rom over the design polygon's vertex heights, by nearest edge."""
    P = np.array(poly, dtype=float)
    n = len(P)
    H = np.array(hs, dtype=float)

    def f(xz):
        out = np.zeros(len(xz))
        A = P
        B = np.roll(P, -1, 0)
        AB = B - A
        L2 = (AB ** 2).sum(1)
        for k, p in enumerate(xz):
            t = np.clip(((p - A) * AB).sum(1) / L2, 0, 1)
            proj = A + AB * t[:, None]
            d = ((proj - p) ** 2).sum(1)
            e = int(np.argmin(d))
            u = float(t[e])
            h0, h1, h2, h3 = H[(e - 1) % n], H[e], H[(e + 1) % n], H[(e + 2) % n]
            out[k] = 0.5 * ((2 * h1) + (-h0 + h2) * u + (2 * h0 - 5 * h1 + 4 * h2 - h3) * u * u + (-h0 + 3 * h1 - 3 * h2 + h3) * u ** 3)
        return out
    return f


def sky_fills(sky_col, sky_i, ground_col, ground_i, sun_dir):
    """Image-free ambient for PhysicalMaterial: a down light from the sky, two low side lights from the
    sky dome (so walls and tree backs are never black) and a bounce from the ground, opposite the sun."""
    sx, sz = sun_dir[0], sun_dir[2]
    ln = math.hypot(sx, sz) or 1.0
    sx, sz = sx / ln, sz / ln
    return [{"def": "SkyFill", "dir": (0.1, -1.0, 0.15), "color": sky_col, "intensity": sky_i},
            {"def": "SkyRingA", "dir": (-sz * 0.9, -0.45, sx * 0.9), "color": sky_col, "intensity": sky_i * 0.45},
            {"def": "SkyRingB", "dir": (sz * 0.9, -0.45, -sx * 0.9), "color": sky_col, "intensity": sky_i * 0.45},
            {"def": "Bounce", "dir": (sx * 0.8, 0.4, sz * 0.8), "color": ground_col, "intensity": ground_i}]


# --------------------------------------------------------------------------------------------
# shared looks

def base_looks(L: Looks, tint_road=(0.40, 0.40, 0.42)):
    L.add("road", tex="asphalt.png", ntex="asphalt_n.png", base=tint_road, rough=0.86, aniso="8", nscale=0.38)
    L.add("paint", tex="paint.png", base=(0.94, 0.94, 0.92), rough=0.55)
    L.add("paint_y", tex="paint.png", base=(0.96, 0.74, 0.12), rough=0.55)
    L.add("wear", tex="wear.png", base=(1, 1, 1), rough=0.6, alpha="blend")
    L.add("skids", tex="skids.png", base=(1, 1, 1), rough=0.6, alpha="blend")
    L.add("checker", tex="checker.png", base=(0.95, 0.95, 0.95), rough=0.55)
    L.add("curb_rw", tex="curb_rw.png", base=(1, 1, 1), rough=0.55)
    L.add("curb_yb", tex="curb_yb.png", base=(1, 1, 1), rough=0.55)
    L.add("curb_bw", tex="curb_bw.png", base=(1, 1, 1), rough=0.55)
    L.add("gutter", tex="concrete.png", ntex="concrete_n.png", base=(0.78, 0.77, 0.74), rough=0.9)
    L.add("guardrail", tex="guardrail.png", base=(0.95, 0.96, 0.98), metal=0.25, rough=0.42)
    L.add("post", base=(0.50, 0.52, 0.55), metal=0.6, rough=0.5)
    L.add("frame", base=(0.10, 0.10, 0.12), metal=0.5, rough=0.45)
    L.add("startlights", base=(0.2, 0.02, 0.02), emit=(0.85, 0.06, 0.03), rough=0.3)
    L.add("chevron", tex="chevron.png", emtex="chevron.png", base=(1, 1, 1), emit=(0.22, 0.2, 0.16), rough=0.5)
    L.add("cone", base=(1.0, 0.36, 0.06), rough=0.55)
    L.add("cone_band", base=(0.95, 0.95, 0.95), rough=0.4, emit=(0.15, 0.15, 0.15))
    L.add("rubber", base=(0.05, 0.05, 0.055), rough=0.8)


def header_nodes(c: Circuit, meta_id: str, name: str, subtitle: str, time: str, runoff: str, checkpoints: int,
                 zones, props, sky: dict, fog: dict, sun: dict, fills: list[dict], cams_xml: str, tex_prefix=LEVEL_TEX) -> str:
    cps = c.checkpoints(checkpoints)
    sectors = (checkpoints // 3, (2 * checkpoints) // 3)
    grid = c.grid()
    tg = TARGETS[meta_id]
    zones_txt = " ".join(f"{a} {b} {s} {k}" for a, b, s, k in zones)
    props_txt = " ".join(f"{k} {fixed_nz(x, 4)} {fixed_nz(z, 4)} {fixed_nz(r, 4)}" for k, x, z, r in props)
    meta = ("<MetadataSet name='kansei:track' containerField='metadata'>"
            f"<MetadataString name='id' value='{mfstr(meta_id)}' containerField='value'/>"
            f"<MetadataString name='name' value='{mfstr(name)}' containerField='value'/>"
            f"<MetadataString name='subtitle' value='{mfstr(subtitle)}' containerField='value'/>"
            f"<MetadataString name='time' value='{mfstr(time)}' containerField='value'/>"
            f"<MetadataInteger name='samples' value='{c.n}' containerField='value'/>"
            f"<MetadataDouble name='length' value='{c.length:.4f}' containerField='value'/>"
            f"<MetadataDouble name='center' value='{c.center_text}' containerField='value'/>"
            f"<MetadataInteger name='checkpoints' value='{' '.join(map(str, cps))}' containerField='value'/>"
            f"<MetadataInteger name='sectors' value='{sectors[0]} {sectors[1]}' containerField='value'/>"
            f"<MetadataDouble name='grid' value='{' '.join(f'{fixed_nz(x, 4)} {fixed_nz(z, 4)} {fixed_nz(y, 5)}' for x, z, y in grid)}' containerField='value'/>"
            f"<MetadataDouble name='zones' value='{zones_txt}' containerField='value'/>"
            f"<MetadataDouble name='props' value='{props_txt}' containerField='value'/>"
            f"<MetadataDouble name='targets' value='{' '.join(f'{v:.1f}' if i < 3 else f'{v:.0f}' for i, v in enumerate(tg))}' containerField='value'/>"
            f"<MetadataString name='runoff' value='{mfstr(runoff)}' containerField='value'/>"
            "</MetadataSet>")
    out = [f"<WorldInfo DEF='TrackInfo' title='{name}' info='{mfstr('KANSEI circuit: ' + name, 'Generated by build/build_world.py; edit the generator, never this file')}'>{meta}</WorldInfo>"]
    out.append("<NavigationInfo DEF='Nav' type='\"NONE\"' transitionType='\"TELEPORT\"' headlight='false' avatarSize='0.5 1.6 0.75' visibilityLimit='9000'/>")
    gx, gz, gyaw = grid[0]
    i0 = int(np.argmin((c.x - gx) ** 2 + (c.z - gz) ** 2))
    fx, fz = math.sin(gyaw), math.cos(gyaw)
    eye = (gx - fx * 6.5, c.y[i0] + 2.1, gz - fz * 6.5)
    tgt = (gx + fx * 8, c.y[i0] + 0.9, gz + fz * 8)
    out.append(f"<Viewpoint DEF='ChaseCam' description='Chase camera (driven by the page)' position='{vec(*eye, d=3)}' "
               f"orientation='{rot_str(look_rotation(eye, tgt))}' fieldOfView='0.9'/>")
    out.append(cams_xml)
    # sky
    faces = "".join(f" {f}Url='{mfstr(*[p + sky['name'] + '_' + f + '.png' for p in tex_prefix])}'" for f in ("front", "back", "left", "right", "top"))
    out.append(f"<Background DEF='Sky' skyAngle='{' '.join(fnum(a, 3) for a in sky['angles'])}' skyColor='{' '.join(col(c_) for c_ in sky['colors'])}' "
               f"groundAngle='{' '.join(fnum(a, 3) for a in sky['g_angles'])}' groundColor='{' '.join(col(c_) for c_ in sky['g_colors'])}'{faces}/>")
    out.append(f"<Fog DEF='Haze' fogType='{fog.get('type', 'LINEAR')}' color='{col(fog['color'])}' visibilityRange='{fnum(fog['range'], 1)}'/>")
    d = sun["dir"]
    out.append(f"<DirectionalLight DEF='Sun' global='true' direction='{vec(*d, d=4)}' color='{col(sun['color'])}' intensity='{fnum(sun['intensity'], 3)}' "
               f"shadows='true' shadowIntensity='{fnum(sun.get('shadow', 0.75), 2)}'/>")
    for k, fl in enumerate(fills):
        out.append(f"<DirectionalLight DEF='{fl['def']}' global='true' direction='{vec(*fl['dir'], d=4)}' color='{col(fl['color'])}' intensity='{fnum(fl['intensity'], 3)}'/>")
    out.append("<Group DEF='Cars'><MetadataString name='kansei:slot' value='\"cars\"' containerField='metadata'/></Group>")
    out.append("<Group DEF='FX'><MetadataString name='kansei:slot' value='\"fx\"' containerField='metadata'/></Group>")
    out.append("<Transform DEF='Rain'><MetadataString name='kansei:slot' value='\"rain\"' containerField='metadata'/></Transform>")
    return "".join(out)


def props_nodes(L: Looks, props) -> str:
    """DEF='Props' > Transform DEF='Prop<k>' in the order of the props metadata (the page may move them)."""
    if not props:
        return ""
    cone = Mesh()
    cone.lathe([(0.0, 0.62), (0.03, 0.62), (0.075, 0.45), (0.13, 0.12), (0.15, 0.05)], 12)
    band = Mesh()
    band.lathe([(0.088, 0.40), (0.112, 0.25)], 12)
    base = Mesh()
    base.box((0, 0.025, 0), (0.38, 0.05, 0.38))
    post = Mesh()
    post.lathe([(0.0, 1.05), (0.06, 1.05), (0.06, 0.0)], 10)
    barrel = Mesh()
    barrel.lathe([(0.0, 0.9), (0.3, 0.9), (0.32, 0.85), (0.32, 0.05), (0.3, 0.0)], 14)
    defs = {}
    out = ["<Group DEF='Props'>"]
    for k, (kind, x, z, r, y, yaw) in enumerate(props):
        if kind not in defs:
            defs[kind] = True
            if kind == 1:
                inner = (f"<Group DEF='PropCone'>" + shape(L, "cone", cone.its(), shadow=False) + shape(L, "cone_band", band.its())
                         + shape(L, "rubber", base.its()) + "</Group>")
            elif kind == 2:
                inner = "<Group DEF='PropPost'>" + shape(L, "cone_band", post.its()) + "</Group>"
            else:
                inner = "<Group DEF='PropBarrel'>" + shape(L, "cone", barrel.its()) + "</Group>"
        else:
            inner = {1: "<Group USE='PropCone'/>", 2: "<Group USE='PropPost'/>", 3: "<Group USE='PropBarrel'/>"}[kind]
        out.append(f"<Transform DEF='Prop{k}' translation='{vec(x, y, z, d=3)}' rotation='0 1 0 {fnum(yaw, 3)}'>{inner}</Transform>")
    out.append("</Group>")
    return "".join(out)


def zones_for(c: Circuit, k_min: float, inner_half: int = 7, outer: tuple = (6, 22), max_zones: int = 12):
    """Clipping zones at the sharpest corners: an inner clip at the apex, an outer clip on the exit."""
    zs = []
    cs = sorted(c.corners(k_min, 6), key=lambda t: -abs(float(c.ks[t[1]])))[:max_zones // 2]
    for a, apex, b, sgn in sorted(cs, key=lambda t: t[1]):
        i0, i1 = (apex - inner_half) % c.n, (apex + inner_half) % c.n
        zs.append((i0, i1, 1 if sgn > 0 else -1, 1))
        o0, o1 = (apex + outer[0]) % c.n, (apex + outer[1]) % c.n
        zs.append((o0, o1, -1 if sgn > 0 else 1, 2))
    return zs


def zone_marks(c: Circuit, L: Looks, zones) -> list[str]:
    """Zone paint on the kerb band and light boards on the wall, so a driver can read them."""
    paint, boards = Mesh(), Mesh()
    for a, b, side, kind in zones:
        idx = span(c, a, b)
        K._ribbon_u(c, paint, idx, [lambda i, s=side: s * (float(c.hw[i]) - 0.02), lambda i, s=side: s * (float(c.hw[i]) + 0.55)],
                    lambda i: (0.0, 1.0), 0.5, lift=0.045)
        walls = c.wl if side > 0 else c.wr
        for i in idx[::3]:
            wd = float(walls[i]) - 0.05
            p = c.pt(i, side * wd)
            y0 = c.y[i] + side * float(walls[i]) * c.tanb[i]
            boards.box((p[0], y0 + 1.05, p[2]), (0.05, 0.22, 1.6), c.yaw(i))
    return [shape(L, "zone_inner", paint.its()), shape(L, "zone_board", boards.its())]


# --------------------------------------------------------------------------------------------
# KESSEL PASS: mountain touge at sunset

KESSEL = dict(
    poly=[(x * 1.07, z * 1.07) for x, z in [(-220, 0), (210, 0), (270, 170), (120, 250), (-90, 262), (-104, 298),
                                            (70, 318), (80, 354), (-60, 372), (-130, 410), (-200, 385), (-270, 430),
                                            (-380, 330), (-360, 120)]],
    radii=[55, 60, 110, 70, 17, 17, 17, 17, 60, 45, 45, 70, 170, 120],
    heights=[0.0, 1.0, 9.0, 15.0, 19.0, 25.0, 29.0, 34.0, 37.0, 39.5, 40.5, 40.0, 30.0, 11.0],
    half_width=lambda i, ks: 5.2 + 0.9 * np.clip(np.abs(ks) * 25 - 0.4, 0, 1),
    smooth=5.0, height_smooth=10.0, bank_gain=1.2, bank_max=0.05, line_gain=520.0, start_at=0.55,
)


def kessel_walls(c, idx, ks, hw):
    return hw + 2.3, hw + 2.3


def kessel_natural(c: Circuit, px, pz):
    """Mountain field: the road's own heights extended, a range rising to the north, a valley south."""
    acc = np.zeros(px.shape)
    wsum = np.zeros(px.shape)
    for i0 in range(0, c.n, 48):
        sl = slice(i0, min(c.n, i0 + 48))
        d2 = (px[..., None] - c.x[sl]) ** 2 + (pz[..., None] - c.z[sl]) ** 2
        w = 1.0 / (d2 + 900.0) ** 1.3
        acc += (w * c.y[sl]).sum(-1)
        wsum += w.sum(-1)
    base = acc / wsum
    _, _, dist = K.nearest_road(c, px, pz)
    north = np.tanh((pz - 330.0) / 140.0)
    rise = np.where(north > 0, 0.42, 0.22) * north * np.minimum(dist, 420.0)
    rs = np.random.RandomState(5)
    # smooth value noise on a coarse lattice (deterministic)
    lat = rs.random_sample((40, 40))
    gx = np.clip((px + 900.0) / 60.0, 0, 38.999)
    gz = np.clip((pz + 700.0) / 60.0, 0, 38.999)
    ix, iz = gx.astype(int), gz.astype(int)
    fx, fz = gx - ix, gz - iz
    fx, fz = fx * fx * (3 - 2 * fx), fz * fz * (3 - 2 * fz)
    v = (lat[iz, ix] * (1 - fx) * (1 - fz) + lat[iz, ix + 1] * fx * (1 - fz) + lat[iz + 1, ix] * (1 - fx) * fz + lat[iz + 1, ix + 1] * fx * fz)
    rough = (v - 0.5) * np.minimum(dist, 300.0) * 0.16
    return base + rise + rough, dist


def build_kessel():
    spec = dict(KESSEL)
    spec["height"] = heights_from_poly(spec["poly"], spec["heights"])
    spec["walls"] = kessel_walls
    spec["seed"] = 101
    c = Circuit(spec)
    L = Looks(LEVEL_TEX)
    base_looks(L, (0.40, 0.40, 0.42))
    L.add("verge", tex="grass.png", base=(0.40, 0.46, 0.24), rough=0.95)
    L.add("terrain", tex="grass.png", base=(1, 1, 1), rough=0.95, tt=(150, 120))
    L.add("retain", tex="concrete.png", ntex="concrete_n.png", base=(0.66, 0.64, 0.60), rough=0.92)
    L.add("pine", tex="pine.png", base=(0.8, 0.9, 0.8), rough=0.9, alpha="mask", cutoff=0.45)
    L.add("pines", tex="pines.png", base=(0.7, 0.8, 0.7), rough=0.9, alpha="mask", cutoff=0.45)
    L.add("rock", tex="rock.png", ntex="rock_n.png", base=(0.62, 0.58, 0.54), rough=0.9)
    L.add("ridge_near", base=(1, 1, 1), rough=1.0)
    L.add("ridge_far", base=(1, 1, 1), rough=1.0)
    L.add("farground", base=(0.10, 0.12, 0.07), rough=1.0)
    L.add("banner", tex="banner.png", emtex="banner.png", base=(1, 1, 1), emit=(0.35, 0.35, 0.35), rough=0.6)
    L.add("zone_inner", base=(0.1, 0.85, 0.95), emit=(0.05, 0.45, 0.5), rough=0.5)
    L.add("zone_board", base=(0.1, 0.85, 0.95), emit=(0.1, 0.7, 0.8), rough=0.4)
    L.add("lamp_pole", base=(0.32, 0.33, 0.35), metal=0.7, rough=0.45)
    L.add("lamp_head", mdef="LampGlow", base=(1, 0.9, 0.7), emit=(1.0, 0.78, 0.45), rough=0.3)

    # terrain
    x0, x1 = float(c.x.min()) - 260, float(c.x.max()) + 260
    z0, z1 = float(c.z.min()) - 260, float(c.z.max()) + 320
    sp = 7.0
    nx, nz = int((x1 - x0) / sp) + 1, int((z1 - z0) / sp) + 1
    gz, gx = np.mgrid[0:nz, 0:nx].astype(float)
    px, pz = x0 + gx * sp, z0 + gz * sp
    nat, dist = kessel_natural(c, px, pz)
    H, ni, lat, dist, t = K.road_clamped_height(c, nat, px, pz, extra=3.5, blend=16.0)
    # taper the grid edge down into the far ground
    edge = np.minimum.reduce([gx, nx - 1 - gx, gz, nz - 1 - gz]) * sp
    tap = np.clip(edge / 90.0, 0, 1)
    H = H * tap + (-45.0) * (1 - tap)
    # colours: slope, height, noise
    dHx = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) / (2 * sp)
    dHz = (np.roll(H, -1, 0) - np.roll(H, 1, 0)) / (2 * sp)
    slope = np.sqrt(dHx ** 2 + dHz ** 2)
    rs = np.random.RandomState(9)
    nz_ = ktex.blur(rs.random_sample(H.shape), 2.0)
    nz_ = (nz_ - nz_.min()) / (nz_.max() - nz_.min())
    grass = np.array([0.30, 0.44, 0.12])
    dry = np.array([0.50, 0.44, 0.20])
    forest = np.array([0.10, 0.17, 0.07])
    rockc = np.array([0.44, 0.41, 0.38])
    dirt = np.array([0.36, 0.28, 0.18])
    nz2 = ktex.blur(rs.random_sample(H.shape), 0.8)
    nz2 = (nz2 - nz2.min()) / (nz2.max() - nz2.min())
    colr = grass[None, None] * (1 - nz_[..., None]) + dry[None, None] * nz_[..., None]
    forest_mask = np.clip((dist - 16) / 30, 0, 1) * np.clip((nz_ - 0.25) * 3, 0, 1)
    colr = colr * (1 - forest_mask[..., None] * 0.85) + forest * forest_mask[..., None] * 0.85
    colr = colr * (0.85 + 0.3 * nz2[..., None])
    rk = np.clip((slope - 0.45) / 0.3, 0, 1)
    colr = colr * (1 - rk[..., None]) + rockc * rk[..., None]
    near = np.clip(1 - (np.abs(lat) - (np.where(lat > 0, c.wl[ni], c.wr[ni]) + 1.0)) / 4.0, 0, 1) * (t < 0.5)
    colr = colr * (1 - near[..., None] * 0.5) + dirt * near[..., None] * 0.5
    terrain = K.elevation_grid(L, "terrain", x0, z0, nx, nz, sp, H, colr)

    def terrain_h(x, z):
        fx_, fz_ = (x - x0) / sp, (z - z0) / sp
        ix, iz = int(fx_), int(fz_)
        if ix < 0 or iz < 0 or ix >= nx - 1 or iz >= nz - 1:
            return -45.0
        ax, az = fx_ - ix, fz_ - iz
        return float(H[iz, ix] * (1 - ax) * (1 - az) + H[iz, ix + 1] * ax * (1 - az) + H[iz + 1, ix] * (1 - ax) * az + H[iz + 1, ix + 1] * ax * az)

    # barrier kinds: retaining wall where the hill rises beside the road, guardrail elsewhere
    kinds_l, kinds_r = [], []
    for i in range(c.n):
        for side, kinds, w in ((1, kinds_l, c.wl), (-1, kinds_r, c.wr)):
            p = c.pt(i, side * (float(w[i]) + 10.0))
            hgt = terrain_h(p[0], p[2])
            kinds.append("retain" if hgt > c.y[i] + 2.5 else "guardrail")
    # smooth kinds: drop runs shorter than 12 samples
    for kinds in (kinds_l, kinds_r):
        for a, b in runs([k == "retain" for k in kinds]):
            if (b - a) % c.n < 12:
                for i in span(c, a, b):
                    kinds[i] = "guardrail"
    styles = {"guardrail": dict(profile=K.GUARDRAIL, look="guardrail", u_scale=1 / 6.0, posts=3, post_look="post"),
              "retain": dict(profile=K.RETAIN, look="retain", u_scale=0.25, v_scale=0.5)}
    st = dict(asphalt="road", curb="curb_rw", band="gutter", verge="verge", curbs="corners", curb_k=1 / 40.0,
              outer_curbs=False, edge_lines=True, centre="double", seed=101, verge_past=1.6)
    parts = []
    parts += K.road_surfaces(c, L, st)
    parts += K.barriers(c, L, kinds_l, kinds_r, styles)
    parts += K.chevrons(c, L, "chevron", "post", k_min=1 / 32.0, every=4)
    parts.append(terrain)
    # far ground and ranges
    parts.append("<Transform translation='0 -46 200'>" + shape(L, "farground", "<Box size='9000 1 9000'/>") + "</Transform>")
    cx, cz = float((c.x.min() + c.x.max()) / 2), float((c.z.min() + c.z.max()) / 2)
    parts.append(K.ridge_ring(L, "ridge_near", (cx, cz), 1150, 1500, 70, 240, 31, -60, segs=160,
                              colors=((0.03, 0.05, 0.04), (0.07, 0.08, 0.10))))
    parts.append(K.ridge_ring(L, "ridge_far", (cx, cz), 2300, 2900, 260, 700, 32, -60, segs=140,
                              colors=((0.06, 0.06, 0.10), (0.16, 0.14, 0.20))))
    # pines: single trees near the road, belts of pines (one billboard, several trees) further out
    rng = RNG(77)
    trees, belts, rocks = [], [], []
    step = 7.0
    for zi in range(int((z1 - z0) / step)):
        for xi in range(int((x1 - x0) / step)):
            x = x0 + (xi + rng.u()) * step
            z = z0 + (zi + rng.u()) * step
            ix, iz = int((x - x0) / sp), int((z - z0) / sp)
            if ix < 1 or iz < 1 or ix >= nx - 2 or iz >= nz - 2:
                continue
            dd = dist[iz, ix]
            if dd < 12.5 or slope[iz, ix] > 0.8 or tap[iz, ix] < 0.6:
                continue
            fm = forest_mask[iz, ix]
            y = terrain_h(x, z)
            if dd < 70:
                if rng.u() < 0.05 + 0.55 * fm and len(trees) < 1300:
                    h = rng.r(8, 16)
                    trees.append((x, y, z, h, h * rng.r(0.42, 0.52), rng.r(0, math.pi)))
            elif dd < 420 and rng.u() < 0.10 * fm and len(belts) < 650:
                h = rng.r(14, 22)
                belts.append((x, y, z, h, h * 1.05, rng.r(0, math.pi)))
            if dd < 24 and slope[iz, ix] > 0.35 and rng.u() < 0.25 and len(rocks) < 160:
                rocks.append((x, y, z, rng.r(0.8, 2.4), rng.i(1 << 30)))
    parts += K.billboard_trees(L, "pine", trees, tile=160)
    parts += K.billboard_trees(L, "pines", belts, tile=240)
    parts.append(K.boulders(L, "rock", rocks))
    # start gantry
    parts += K.gantry(c, L, "banner", "frame", "startlights")
    # zones
    zones = zones_for(c, 1 / 60.0)
    parts += zone_marks(c, L, zones)
    # lamps at the hairpins (Lamps)
    lamps = Mesh()
    heads = Mesh()
    for a, apex, b, sgn in c.corners(1 / 30.0, 5):
        side = -sgn
        w = c.wr if side < 0 else c.wl
        for i in (apex - 10, apex, apex + 10):
            i %= c.n
            p = c.pt(i, side * (float(w[i]) + 0.9))
            y0 = c.y[i] + side * float(w[i]) * c.tanb[i]
            lamps.box((p[0], y0 + 3.6, p[2]), (0.14, 7.2, 0.14), c.yaw(i))
            q = c.pt(i, side * (float(w[i]) - 0.6))
            lamps.box(((p[0] + q[0]) / 2, y0 + 7.15, (p[2] + q[2]) / 2), (1.6, 0.1, 0.12), c.yaw(i) + math.pi / 2)
            heads.box((q[0], y0 + 7.05, q[2]), (0.5, 0.12, 0.3), c.yaw(i))
    lamps_xml = "<Group DEF='Lamps'>" + shape(L, "lamp_pole", lamps.its()) + shape(L, "lamp_head", heads.its()) + "</Group>"
    cams, cam_info = K.viewpoints(c, 12, 5)
    sun_dir = (-0.78, 0.22, -0.58)
    sky = dict(name="sky_kessel", angles=[0.9, 1.25, 1.45, 1.571], colors=[(0.16, 0.20, 0.38), (0.36, 0.34, 0.52), (0.78, 0.52, 0.50), (1.0, 0.68, 0.42), (1.0, 0.76, 0.50)],
               g_angles=[1.3, 1.571], g_colors=[(0.12, 0.10, 0.12), (0.30, 0.22, 0.24), (0.85, 0.60, 0.45)],
               spec=dict(sun_dir=sun_dir, clouds=0.42, cloud_h=1.0, cloud_scale=0.22, cloud_lit=(1.0, 0.66, 0.42), cloud_shade=(0.36, 0.30, 0.42),
                         cloud_rim=(0.4, 0.2, 0.05), cloud_alpha=0.92, disc=0.022, glow_w=0.20, glow_a=0.75, glow_col=(1.0, 0.72, 0.40), disc_col=(1.0, 0.92, 0.75)))
    fog = dict(color=(0.78, 0.55, 0.50), range=6500)
    sun = dict(dir=tuple(-v for v in sun_dir), color=(1.0, 0.68, 0.42), intensity=2.7, shadow=0.7)
    fills = sky_fills((0.46, 0.52, 0.80), 0.75, (0.62, 0.42, 0.34), 0.30, sun_dir)
    head = header_nodes(c, "kessel-pass", "Kessel Pass", "Mountain touge, sunset", "sunset", "grass", 14, zones, [],
                        sky, fog, sun, fills, cams)
    body = head + lamps_xml + "<Group DEF='Track'>" + "".join(parts) + "</Group>"
    doc = x3d_doc("KANSEI Kessel Pass", "KANSEI circuit Kessel Pass: a mountain touge at sunset. Track metadata (kansei:track) is read by the game's simulation; the meshes are built from the same samples.",
                  COMPONENTS, body, GEN)
    info = dict(id="kessel-pass", name="Kessel Pass", subtitle="Mountain touge, sunset", time="sunset", runoff="grass",
                samples=c.n, length=round(c.length, 1), trackcams=len(cam_info), zones=len(zones), props=0)
    return doc, info, sky


# --------------------------------------------------------------------------------------------
# NEON OVERPASS: night city, elevated banked loops, a covered section

NEON = dict(
    poly=[(x * 1.22, z * 1.22) for x, z in [(-380, 0), (330, 0), (440, 90), (390, 220), (250, 250), (150, 190), (30, 230),
                                            (-50, 340), (-210, 350), (-270, 250), (-450, 210)]],
    radii=[95, 88, 88, 76, 60, 60, 66, 54, 54, 76, 95],
    heights=[11.0, 12.0, 16.0, 19.0, 16.0, 13.0, 11.0, 13.0, 17.0, 15.0, 12.0],
    half_width=7.0, smooth=5.0, height_smooth=16.0, bank_gain=8.0, bank_max=0.12, line_gain=900.0, start_at=0.30,
)
SIGNS = [("KANSEI", (1.0, 0.18, 0.62)), ("RAMEN 24", (1.0, 0.55, 0.10)), ("ARCADE", (0.15, 0.85, 1.0)), ("HOTEL KUMO", (0.55, 0.35, 1.0)),
         ("LOOP 7", (0.2, 1.0, 0.45)), ("NAMI BAR", (1.0, 0.25, 0.2)), ("MIDNIGHT", (0.3, 0.55, 1.0)), ("HIKARI", (1.0, 0.85, 0.2))]


def build_neon():
    spec = dict(NEON)
    spec["height"] = heights_from_poly(spec["poly"], spec["heights"])
    spec["walls"] = lambda c, idx, ks, hw: (hw + 1.5, hw + 1.5)
    c = Circuit(spec)
    L = Looks(LEVEL_TEX)
    base_looks(L, (0.30, 0.30, 0.33))
    L.add("verge", tex="concrete.png", base=(0.36, 0.36, 0.38), rough=0.85)
    L.add("band", tex="concrete.png", base=(0.42, 0.42, 0.44), rough=0.85)
    L.add("jersey", tex="concrete.png", ntex="concrete_n.png", base=(0.62, 0.62, 0.64), rough=0.8)
    L.add("deck", tex="concrete.png", ntex="concrete_n.png", base=(0.40, 0.40, 0.43), rough=0.9)
    L.add("pillar", tex="concrete.png", ntex="concrete_n.png", base=(0.50, 0.50, 0.53), rough=0.9)
    L.add("led_c", base=(0.0, 0.0, 0.0), emit=(0.05, 0.75, 1.0), rough=0.4)
    L.add("led_m", base=(0.0, 0.0, 0.0), emit=(1.0, 0.12, 0.6), rough=0.4)
    L.add("street", tex="asphalt.png", base=(0.12, 0.12, 0.14), rough=0.7)
    L.add("facade_a", tex="facade_a.png", emtex="facade_a_e.png", base=(0.55, 0.56, 0.62), emit=(1, 1, 1), rough=0.6, metal=0.1)
    L.add("facade_b", tex="facade_b.png", emtex="facade_b_e.png", base=(0.45, 0.52, 0.62), emit=(1, 1, 1), rough=0.25, metal=0.3)
    L.add("roof", base=(0.10, 0.10, 0.12), rough=0.9)
    L.add("beacon", base=(0.2, 0, 0), emit=(1.0, 0.05, 0.05), rough=0.5)
    L.add("signs", tex="neon_signs.png", emtex="neon_signs.png", base=(0.02, 0.02, 0.02), emit=(1, 1, 1), rough=0.5)
    L.add("sign_back", base=(0.05, 0.05, 0.06), rough=0.6, metal=0.4)
    L.add("tunnel", tex="concrete.png", ntex="concrete_n.png", base=(0.46, 0.46, 0.48), rough=0.85)
    L.add("tunnel_light", base=(0.1, 0.1, 0.1), emit=(1.0, 0.92, 0.78), rough=0.4)
    L.add("lamp_pole", base=(0.30, 0.31, 0.34), metal=0.6, rough=0.45)
    L.add("lamp_head", mdef="LampGlow", base=(1, 0.95, 0.85), emit=(1.0, 0.86, 0.62), rough=0.3)
    L.add("lamp_pool", mdef="LampPool", tex="spot.png", base=(1, 0.8, 0.55), emit=(0.55, 0.40, 0.24), rough=0.9, alpha="blend")
    L.add("banner", tex="banner.png", emtex="banner.png", base=(1, 1, 1), emit=(0.8, 0.8, 0.8), rough=0.6)
    L.add("zone_inner", base=(1.0, 0.1, 0.6), emit=(0.9, 0.08, 0.5), rough=0.5)
    L.add("zone_board", base=(1.0, 0.1, 0.6), emit=(1.0, 0.12, 0.6), rough=0.4)
    L.add("skyline", tex="facade_b.png", emtex="facade_b_e.png", base=(0.2, 0.22, 0.3), emit=(0.8, 0.8, 0.8), rough=0.5)
    n = c.n
    # covered section: the middle of the main straight
    tun0, tun1 = int(n * 0.06), int(n * 0.15)
    st = dict(asphalt="road", curb="curb_yb", band="band", verge="verge", curbs="corners", curb_k=1 / 70.0, outer_curbs=True,
              edge_lines=True, lane_fracs=[-0.5, 0.0, 0.5], dash=(2, 4), seed=202, verge_past=0.72, wear_half=1.3)
    parts = K.road_surfaces(c, L, st)
    styles = {"jersey": dict(profile=K.JERSEY, look="jersey", u_scale=0.25, v_scale=0.5)}
    parts += K.barriers(c, L, ["jersey"] * n, ["jersey"] * n, styles)
    # deck: fascia and underside (banked), LED lines along the fascia
    deck = Mesh(normals=False)
    leds_c, leds_m = Mesh(), Mesh()
    allidx = K.decimate(c, list(range(n)) + [0], k_keep=1 / 150.0, every=4)
    for side, w in ((1, c.wl), (-1, c.wr)):
        prof = [(0.72, 0.0), (0.72, -1.6), (0.72, -1.6), (-float(w[0]) + 0.01, -1.6)]
        sweep_profile_local(c, deck, allidx, side, lambda i, w=w: float(w[i]), prof, 0.25, banked=True)
        sweep_profile_local(c, leds_c if side > 0 else leds_m, allidx, side, lambda i, w=w: float(w[i]),
                            [(0.74, -0.25), (0.74, -0.38)], 0.25, banked=True)
    parts.append(shape(L, "deck", deck.ifs(crease=0.5, dp=2, dt=2)))
    parts.append(shape(L, "led_c", leds_c.its()))
    parts.append(shape(L, "led_m", leds_m.its()))
    # pillars and cap beams
    pil = Mesh(normals=False)
    for i in range(0, n, 16):
        if tun0 - 4 <= i <= tun1 + 4:
            continue
        p = c.pt(i, 0.0)
        top = c.y[i] - 1.6
        yaw = c.yaw(i)
        K.post_box(pil, (p[0], top / 2, p[2]), (2.4, top, 1.8), yaw)
        K.post_box(pil, (p[0], top - 0.9, p[2]), (2 * float(c.wl[i]) + 0.8, 1.8, 1.6), yaw + math.pi / 2)
    parts.append(shape(L, "pillar", pil.ifs(crease=0.0, dp=2, dt=1)))
    # the covered section: walls outside the barriers, a roof, strip lights
    tidx = list(range(tun0, tun1 + 1))
    tun = Mesh(normals=False)
    lights = Mesh()
    for side, w in ((1, c.wl), (-1, c.wr)):
        sweep_profile_local(c, tun, tidx, side, lambda i, w=w: float(w[i]),
                            [(0.75, -1.6), (0.75, 6.8), (0.75, 6.8), (-float(w[tun0]) - 0.05, 6.8)], 0.25, banked=True)
        sweep_profile_local(c, tun, tidx, side, lambda i, w=w: float(w[i]),
                            [(-float(w[tun0]) - 0.05, 7.6), (1.4, 7.6), (1.4, 7.6), (1.4, -1.6)], 0.25, banked=True)
        sweep_profile_local(c, lights, tidx, side, lambda i, w=w: float(w[i]),
                            [(-2.2, 6.75), (-3.0, 6.75)], 0.25, banked=True)
    parts.append(shape(L, "tunnel", tun.ifs(crease=0.3, dp=2, dt=2)))
    parts.append(shape(L, "tunnel_light", lights.its()))
    # portal signs
    sg = Mesh()
    for i, face in ((tun0, -1), (tun1, 1)):
        yaw = c.yaw(i)
        fx, fz = math.sin(yaw), math.cos(yaw)
        lx, lz = fz, -fx
        p = c.pt(i, 0.0)
        yb = c.y[i] + 7.7
        w2 = 7.0
        off = 0.0
        q = [(p[0] - lx * w2 * face + fx * face * 0.05, yb, p[2] - lz * w2 * face + fz * face * 0.05),
             (p[0] + lx * w2 * face + fx * face * 0.05, yb, p[2] + lz * w2 * face + fz * face * 0.05),
             (p[0] + lx * w2 * face + fx * face * 0.05, yb + 1.75, p[2] + lz * w2 * face + fz * face * 0.05),
             (p[0] - lx * w2 * face + fx * face * 0.05, yb + 1.75, p[2] - lz * w2 * face + fz * face * 0.05)]
        nn = (fx * face, 0, fz * face)
        r = 6  # "MIDNIGHT"
        ids = [sg.v(pt, nn, uv) for pt, uv in zip(q, ((0, 1 - (r + 1) / 8), (1, 1 - (r + 1) / 8), (1, 1 - r / 8), (0, 1 - r / 8)))]
        sg.quad(*ids)
    # city: ground, blocks of towers, signs facing the road
    cx, cz = float((c.x.min() + c.x.max()) / 2), float((c.z.min() + c.z.max()) / 2)
    parts.append(K.flat_ground(L, "street", cx, cz, 5000, -0.05, 14.0, rings=8))
    rng = RNG(303)
    tiles: dict = {}
    beac = Mesh(normals=False)
    pitch = 72.0
    x0, x1 = float(c.x.min()) - 430, float(c.x.max()) + 430
    z0, z1 = float(c.z.min()) - 430, float(c.z.max()) + 430
    signs_near = []
    count = 0
    for zi in range(int((z1 - z0) / pitch)):
        for xi in range(int((x1 - x0) / pitch)):
            bx0 = x0 + xi * pitch + 9
            bz0 = z0 + zi * pitch + 9
            bw = pitch - 18
            for sub in range(rng.i(3) + 1):
                if sub == 0:
                    rx0, rx1, rz0, rz1 = bx0, bx0 + bw * rng.r(0.45, 1.0), bz0, bz0 + bw * rng.r(0.45, 1.0)
                else:
                    rx1, rz1 = bx0 + bw, bz0 + bw
                    rx0, rz0 = rx1 - bw * rng.r(0.3, 0.5), rz1 - bw * rng.r(0.3, 0.5)
                if not K.rect_clear(c, rx0, rx1, rz0, rz1, 7.0):
                    continue
                dmin = float(np.min(np.hypot(c.x - (rx0 + rx1) / 2, c.z - (rz0 + rz1) / 2)))
                hmax = 40 + min(1.0, dmin / 300) * 140
                h = rng.r(16, hmax) * (1.6 if rng.u() < 0.06 else 1.0)
                kind = "facade_b" if rng.u() < 0.45 else "facade_a"
                key = (kind, int((rx0 - x0) // 360), int((rz0 - z0) // 360))
                m = tiles.setdefault(key, Mesh(normals=False))
                K.tex_box(m, rx0, rx1, 0.0, h, rz0, rz1, 40.0, 56.0, u_off=rng.r(0, 40), v_off=rng.i(16) * 3.5)
                count += 1
                if h > 110:
                    K.post_box(beac, ((rx0 + rx1) / 2, h + 0.4, (rz0 + rz1) / 2), (0.9, 0.9, 0.9), 0.0)
                if dmin < 140 and h > 22:
                    signs_near.append((rx0, rx1, rz0, rz1, h))
    for key in sorted(tiles):
        parts.append(shape(L, key[0], tiles[key].ifs(crease=0.0, dp=1, dt=2)))
    parts.append(shape(L, "beacon", beac.ifs(crease=0.0, dp=1, dt=0)))
    # neon signs: on the face of near buildings that looks at the road
    sm, sback = Mesh(), Mesh(normals=False)
    for k, (rx0, rx1, rz0, rz1, h) in enumerate(signs_near[:70]):
        bxc, bzc = (rx0 + rx1) / 2, (rz0 + rz1) / 2
        i = int(np.argmin((c.x - bxc) ** 2 + (c.z - bzc) ** 2))
        dx, dz = c.x[i] - bxc, c.z[i] - bzc
        r = k % 8
        sy = rng.r(min(h - 6, max(10, c.y[i] + 2)), max(12, h - 5)) if h > 14 else h * 0.6
        if abs(dx) > abs(dz):
            xf = rx1 + 0.3 if dx > 0 else rx0 - 0.3
            wdt = min(rz1 - rz0 - 2, 22.0)
            za, zb = bzc - wdt / 2, bzc + wdt / 2
            nn = (1 if dx > 0 else -1, 0, 0)
            hh = wdt / 8.0 * 1.6
            pts = [(xf, sy, zb), (xf, sy, za), (xf, sy + hh, za), (xf, sy + hh, zb)] if dx > 0 else [(xf, sy, za), (xf, sy, zb), (xf, sy + hh, zb), (xf, sy + hh, za)]
        else:
            zf = rz1 + 0.3 if dz > 0 else rz0 - 0.3
            wdt = min(rx1 - rx0 - 2, 22.0)
            xa, xb = bxc - wdt / 2, bxc + wdt / 2
            nn = (0, 0, 1 if dz > 0 else -1)
            hh = wdt / 8.0 * 1.6
            pts = [(xa, sy, zf), (xb, sy, zf), (xb, sy + hh, zf), (xa, sy + hh, zf)] if dz > 0 else [(xb, sy, zf), (xa, sy, zf), (xa, sy + hh, zf), (xb, sy + hh, zf)]
        v0, v1 = 1 - (r + 1) / 8, 1 - r / 8
        ids = [sm.v(pt, nn, uv) for pt, uv in zip(pts, ((0, v0), (1, v0), (1, v1), (0, v1)))]
        sm.quad(*ids)
    sm.merge(sg)
    parts.append(shape(L, "signs", sm.its(solid=False)))
    # distant skyline ring
    sky_m = Mesh(normals=False)
    for k in range(150):
        a = 2 * math.pi * k / 150 + rng.r(-0.01, 0.01)
        rr = rng.r(1500, 2400)
        bx, bz = cx + math.cos(a) * rr, cz + math.sin(a) * rr
        w = rng.r(30, 70)
        K.tex_box(sky_m, bx - w / 2, bx + w / 2, 0, rng.r(60, 260), bz - w / 2, bz + w / 2, 40.0, 56.0, u_off=rng.r(0, 40))
    parts.append(shape(L, "skyline", sky_m.ifs(crease=0.0, dp=0, dt=1)))
    parts += K.gantry(c, L, "banner", "frame", "startlights")
    zones = zones_for(c, 1 / 110.0)
    parts += zone_marks(c, L, zones)
    lamps_xml = "<Group DEF='Lamps'>" + K.street_lamps(c, L, 18, height=9.5, arm=2.8, pool_size=(11.0, 14.0),
                                                     idx_filter=lambda i: not (tun0 <= i <= tun1)) + "</Group>"
    cams, cam_info = K.viewpoints(c, 12, 7, height=(5.0, 14.0))
    moon_dir = (0.35, 0.50, -0.79)
    sky = dict(name="sky_neon", angles=[0.8, 1.2, 1.42, 1.571], colors=[(0.01, 0.012, 0.035), (0.02, 0.03, 0.09), (0.08, 0.07, 0.18), (0.30, 0.14, 0.30), (0.50, 0.26, 0.32)],
               g_angles=[1.4, 1.571], g_colors=[(0.02, 0.02, 0.04), (0.05, 0.04, 0.08), (0.20, 0.10, 0.20)],
               spec=dict(sun_dir=moon_dir, clouds=0.30, cloud_h=1.0, cloud_scale=0.25, cloud_lit=(0.26, 0.20, 0.34), cloud_shade=(0.10, 0.07, 0.16),
                         cloud_rim=(0.1, 0.05, 0.1), cloud_alpha=0.75, disc=0.016, glow_w=0.08, glow_a=0.35, glow_col=(0.6, 0.66, 0.9),
                         disc_col=(0.92, 0.94, 1.0), moon=True, stars=True))
    fog = dict(color=(0.11, 0.07, 0.16), range=2600)
    sun = dict(dir=tuple(-v for v in moon_dir), color=(0.62, 0.70, 1.0), intensity=1.1, shadow=0.6)
    fills = sky_fills((0.30, 0.26, 0.55), 0.55, (0.55, 0.30, 0.42), 0.35, moon_dir)
    head = header_nodes(c, "neon-overpass", "Neon Overpass", "Night city, banked loops", "night", "tarmac", 16, zones, [],
                        sky, fog, sun, fills, cams)
    body = head + lamps_xml + "<Group DEF='Track'>" + "".join(parts) + "</Group>"
    doc = x3d_doc("KANSEI Neon Overpass", "KANSEI circuit Neon Overpass: an elevated night expressway with banked loops and a covered section. Track metadata (kansei:track) is read by the simulation; the meshes are built from the same samples.",
                  COMPONENTS, body, GEN)
    info = dict(id="neon-overpass", name="Neon Overpass", subtitle="Night city, banked loops", time="night", runoff="tarmac",
                samples=c.n, length=round(c.length, 1), trackcams=len(cam_info), zones=len(zones), props=0, buildings=count)
    return doc, info, sky


def sweep_profile_local(c, mesh, idx, side, base_d, prof, u_scale, banked=False):
    from ktrack import sweep_profile
    sweep_profile(c, mesh, idx, side, base_d, prof, u_scale, banked=banked)


# --------------------------------------------------------------------------------------------
# SALT RING: salt-flat drift arena at golden hour

SALT = dict(
    poly=[(x * 1.05, z * 1.05) for x, z in [(-150, 0), (110, 0), (190, 70), (150, 160), (70, 120), (10, 170), (40, 250),
                                            (-60, 300), (-180, 240), (-215, 110)]],
    radii=[50, 55, 45, 32, 36, 36, 45, 55, 60, 55],
    half_width=13.0, smooth=6.0, bank_gain=0.0, bank_max=0.0, line_gain=1400.0, start_at=0.55, grip=0.96,
)


def salt_walls(c, idx, ks, hw):
    out_w = hw + 7.0 + 5.0 * np.clip(np.abs(ks) * 40, 0, 1)
    in_w = hw + 4.5
    wl = np.where(ks > 0, in_w, out_w)
    wr = np.where(ks > 0, out_w, in_w)
    return periodic_smooth(wl, 10.0), periodic_smooth(wr, 10.0)


def build_salt():
    spec = dict(SALT)
    spec["height"] = lambda xz: 0.05 + 0.25 * np.sin(xz[:, 0] / 90.0) * np.cos(xz[:, 1] / 70.0)
    spec["walls"] = salt_walls
    c = Circuit(spec)
    L = Looks(LEVEL_TEX)
    base_looks(L, (0.62, 0.58, 0.52))
    L.add("course", tex="asphalt.png", ntex="asphalt_n.png", base=(0.86, 0.82, 0.76), rough=0.75, aniso="8", nscale=0.35)
    L.add("verge", tex="salt.png", ntex="salt_n.png", base=(0.92, 0.88, 0.80), rough=0.85)
    L.add("salt", tex="salt.png", ntex="salt_n.png", base=(0.95, 0.91, 0.84), rough=0.9, tt=(1, 1))
    L.add("band", tex="salt.png", base=(0.85, 0.80, 0.72), rough=0.8)
    L.add("paint_o", tex="paint.png", base=(1.0, 0.42, 0.08), rough=0.55)
    L.add("tyres", tex="tyres.png", ntex="tyres_n.png", base=(1, 1, 1), rough=0.75)
    L.add("mesa", tex="rock.png", ntex="rock_n.png", base=(0.72, 0.42, 0.28), rough=0.95)
    L.add("mesa_far", base=(1, 1, 1), rough=1.0)
    L.add("canvas_w", base=(0.92, 0.90, 0.86), rough=0.8)
    L.add("canvas_o", base=(1.0, 0.45, 0.10), rough=0.8)
    L.add("canvas_k", base=(0.08, 0.08, 0.09), rough=0.7)
    L.add("truss", base=(0.75, 0.76, 0.78), metal=0.7, rough=0.35)
    L.add("seat", base=(0.15, 0.32, 0.62), rough=0.6)
    L.add("flag", tex="banner.png", emtex="banner.png", base=(1, 1, 1), emit=(0.2, 0.2, 0.2), rough=0.7)
    L.add("banner", tex="banner.png", emtex="banner.png", base=(1, 1, 1), emit=(0.3, 0.3, 0.3), rough=0.6)
    L.add("zone_inner", base=(1.0, 0.45, 0.05), emit=(0.6, 0.25, 0.02), rough=0.5)
    L.add("zone_board", base=(1.0, 0.45, 0.05), emit=(0.8, 0.35, 0.02), rough=0.4)
    L.add("lamp_pole", base=(0.70, 0.71, 0.74), metal=0.6, rough=0.4)
    L.add("lamp_head", mdef="LampGlow", base=(1, 1, 1), emit=(0.9, 0.9, 0.85), rough=0.3)
    n = c.n
    st = dict(asphalt="course", curb="curb_rw", band="band", verge="verge", curbs="corners", curb_k=1 / 70.0, outer_curbs=True,
              edge_lines=True, paint="paint_o", edge_w=0.25, edge_in=0.1, seed=303, verge_past=3.0, wear_half=1.6, asphalt_tile=7.0)
    parts = K.road_surfaces(c, L, st)
    styles = {"tyres": dict(profile=K.TYRES, look="tyres", u_scale=1 / 1.2, v_scale=1 / 0.92, crease=0.6)}
    parts += K.barriers(c, L, ["tyres"] * n, ["tyres"] * n, styles)
    cx, cz = float((c.x.min() + c.x.max()) / 2), float((c.z.min() + c.z.max()) / 2)
    parts.append(K.flat_ground(L, "salt", cx, cz, 9000, -0.02, 9.0, rings=10))
    # mesas: flat-topped buttes far away (near ring textured, far ring vertex coloured)
    rng = RNG(404)
    mesa = Mesh(normals=False)
    for k in range(16):
        a = 2 * math.pi * k / 16 + rng.r(-0.15, 0.15)
        rr = rng.r(900, 1500)
        mx, mz = cx + math.cos(a) * rr, cz + math.sin(a) * rr
        r0 = rng.r(60, 160)
        h = rng.r(50, 140)
        prof = [(r0 * 1.9, -1), (r0 * 1.35, h * 0.32), (r0 * 1.05, h * 0.62), (r0, h * 0.95), (r0 * 0.94, h), (0, h * 1.01)]
        mesa.lathe(prof, 14, (mx, 0, mz))
    parts.append(shape(L, "mesa", mesa.ifs(crease=0.6, dp=1, dt=2)))
    parts.append(K.ridge_ring(L, "mesa_far", (cx, cz), 2600, 3300, 60, 260, 41, -5, segs=120, sharp=0.2,
                              colors=((0.55, 0.30, 0.22), (0.62, 0.40, 0.30))))
    # paddock: tents, trucks, a grandstand and flags near the start
    i0 = 0
    yaw = c.yaw(i0)
    fx, fz = math.sin(yaw), math.cos(yaw)
    lx, lz = fz, -fx
    side = -1 if c.ks[i0] >= 0 else 1
    wbase = float(c.wr[i0] if side < 0 else c.wl[i0])
    pad = []
    tent_w, tent_o, tent_k, truss, seat = Mesh(normals=False), Mesh(normals=False), Mesh(normals=False), Mesh(normals=False), Mesh(normals=False)
    for k in range(6):
        along = -60 + k * 22
        d = side * (wbase + 14)
        px, pz = c.x[i0] + fx * along + lx * d, c.z[i0] + fz * along + lz * d
        if not K.far_point_clear(c, px, pz, 6.0):
            continue
        m = tent_w if k % 2 == 0 else tent_o
        # pop-up tent: 4 legs + a pyramid roof
        for (ax, az) in ((-2.8, -2.8), (2.8, -2.8), (2.8, 2.8), (-2.8, 2.8)):
            K.post_box(truss, (px + ax, 1.3, pz + az), (0.08, 2.6, 0.08), 0.0)
        roof = [(px - 3, 2.6, pz - 3), (px + 3, 2.6, pz - 3), (px + 3, 2.6, pz + 3), (px - 3, 2.6, pz + 3), (px, 3.6, pz)]
        ids = [m.v(q, (0, 1, 0), (0, 0)) for q in roof]
        for a_, b_ in ((0, 1), (1, 2), (2, 3), (3, 0)):
            m.tri(ids[a_], ids[b_], ids[4])
        # a support truck behind every other tent
        if k % 2 == 1:
            tk = (px + lx * side * 10, pz + lz * side * 10)
            K.post_box(tent_k, (tk[0], 1.6, tk[1]), (2.5, 2.6, 7.5), yaw)
            K.post_box(tent_w, (tk[0] + fx * 4.6, 1.3, tk[1] + fz * 4.6), (2.4, 2.0, 1.8), yaw)
    # grandstand on the outside of the first corner
    gs_i = int(n * 0.12)
    gyaw = c.yaw(gs_i)
    gfx, gfz = math.sin(gyaw), math.cos(gyaw)
    glx, glz = gfz, -gfx
    gside = -1 if c.ks[gs_i] > 0 else 1
    gw = float(c.wr[gs_i] if gside < 0 else c.wl[gs_i]) + 6
    gx, gz = c.x[gs_i] + glx * gside * gw, c.z[gs_i] + glz * gside * gw
    if K.far_point_clear(c, gx, gz, 3.0):
        for row in range(7):
            o = gside * (row * 0.9)
            K.post_box(seat, (gx + glx * o, 0.25 + row * 0.5, gz + glz * o), (0.8, 0.5, 40.0), gyaw)
        K.post_box(truss, (gx + glx * gside * 7.2, 4.0, gz + glz * gside * 7.2), (0.3, 8.0, 40.0), gyaw)
    parts += [shape(L, "canvas_w", tent_w.ifs(crease=0.0, dp=2, dt=0)), shape(L, "canvas_o", tent_o.ifs(crease=0.0, dp=2, dt=0)),
              shape(L, "canvas_k", tent_k.ifs(crease=0.0, dp=2, dt=0)), shape(L, "truss", truss.ifs(crease=0.0, dp=2, dt=0)),
              shape(L, "seat", seat.ifs(crease=0.0, dp=2, dt=0))]
    # flags along the outside walls
    flags = Mesh()
    poles = Mesh(normals=False)
    for i in range(0, n, 26):
        side_f = -1 if c.ks[i] > 0 else 1
        w = float(c.wr[i] if side_f < 0 else c.wl[i]) + 1.6
        p = c.pt(i, side_f * w)
        K.post_box(poles, (p[0], 3.0, p[2]), (0.07, 6.0, 0.07), 0.0)
        yawf = c.yaw(i)
        ffx, ffz = math.sin(yawf), math.cos(yawf)
        q = [(p[0], 3.4, p[2]), (p[0] + ffx * 2.6, 3.4, p[2] + ffz * 2.6), (p[0] + ffx * 2.6, 5.9, p[2] + ffz * 2.6), (p[0], 5.9, p[2])]
        nn = (ffz * side_f, 0, -ffx * side_f)
        ids = [flags.v(pt, nn, uv) for pt, uv in zip(q, ((0, 0), (1, 0), (1, 1), (0, 1)))]
        flags.quad(*ids)
    parts += [shape(L, "flag", flags.its(solid=False)), shape(L, "truss", poles.ifs(crease=0.0, dp=2, dt=0))]
    parts += K.gantry(c, L, "banner", "truss", "startlights", height=6.8)
    # clipping zones with cones on their edges (knockable props), barrels in the infield
    zones = zones_for(c, 1 / 75.0, inner_half=8, outer=(6, 24), max_zones=16)
    props = []
    for a, b, side_z, kind in zones:
        for i in span(c, a, b)[::4]:
            lat = side_z * (float(c.hw[i]) + CURB_BAND + 0.5)
            p = c.pt(i, lat)
            props.append((1, p[0], p[2], 0.17, p[1], c.yaw(i)))
    parts += zone_marks(c, L, zones)
    lamps_xml = "<Group DEF='Lamps'>" + K.street_lamps(c, L, 40, height=11.0, arm=1.2, pool_look=None, sides=(-1, 1)) + "</Group>"
    cams, cam_info = K.viewpoints(c, 10, 11, height=(3.0, 8.0), side_out=(8.0, 16.0))
    sun_dir = (0.70, 0.27, -0.66)
    sky = dict(name="sky_salt", angles=[0.8, 1.2, 1.45, 1.571], colors=[(0.16, 0.30, 0.56), (0.32, 0.48, 0.70), (0.66, 0.66, 0.66), (0.96, 0.78, 0.56), (1.0, 0.84, 0.62)],
               g_angles=[1.4, 1.571], g_colors=[(0.62, 0.52, 0.42), (0.80, 0.68, 0.54), (0.98, 0.84, 0.66)],
               spec=dict(sun_dir=sun_dir, clouds=0.30, cloud_h=1.0, cloud_scale=0.16, cloud_lit=(1.0, 0.84, 0.62), cloud_shade=(0.55, 0.52, 0.60),
                         cloud_rim=(0.3, 0.18, 0.05), cloud_alpha=0.85, disc=0.02, glow_w=0.24, glow_a=0.7, glow_col=(1.0, 0.84, 0.55), disc_col=(1.0, 0.96, 0.86)))
    fog = dict(color=(0.95, 0.82, 0.64), range=5200)
    sun = dict(dir=tuple(-v for v in sun_dir), color=(1.0, 0.80, 0.55), intensity=3.0, shadow=0.75)
    fills = sky_fills((0.50, 0.60, 0.85), 0.75, (0.85, 0.70, 0.55), 0.55, sun_dir)
    head = header_nodes(c, "salt-ring", "Salt Ring", "Salt-flat drift arena, golden hour", "golden", "tarmac", 12, zones,
                        [(k, x, z, r) for k, x, z, r, _y, _yw in props], sky, fog, sun, fills, cams)
    body = head + lamps_xml + props_nodes(L, props) + "<Group DEF='Track'>" + "".join(parts) + "</Group>"
    doc = x3d_doc("KANSEI Salt Ring", "KANSEI circuit Salt Ring: a drift arena marked out on a salt flat at golden hour, with clipping zones, cones and tyre walls. Track metadata (kansei:track) is read by the simulation; the meshes are built from the same samples.",
                  COMPONENTS, body, GEN)
    info = dict(id="salt-ring", name="Salt Ring", subtitle="Salt-flat drift arena, golden hour", time="golden", runoff="tarmac",
                samples=c.n, length=round(c.length, 1), trackcams=len(cam_info), zones=len(zones), props=len(props))
    return doc, info, sky


# --------------------------------------------------------------------------------------------
# CLIFFSIDE ESSES: coastal cliff road at noon

CLIFF = dict(
    poly=[(-700, 0), (-320, -50), (0, 30), (260, -40), (560, 20), (720, 160), (620, 320), (330, 340), (170, 265), (110, 320),
          (-160, 330), (-460, 300), (-730, 190)],
    radii=[110, 300, 260, 260, 150, 110, 120, 60, 20, 60, 200, 160, 90],
    heights=[44.0, 40.0, 46.0, 42.0, 48.0, 54.0, 60.0, 62.0, 61.0, 63.0, 66.0, 60.0, 50.0],
    half_width=lambda i, ks: 5.4 + 0.6 * np.clip(np.abs(ks) * 30 - 0.3, 0, 1),
    smooth=5.0, height_smooth=14.0, bank_gain=3.0, bank_max=0.06, line_gain=700.0, start_at=0.5,
)


def coast_line(c: Circuit):
    """The cliff edge: 20-38 m south of the coast road's centreline, following it in x."""
    south = c.z < 120.0
    xs, zs = c.x[south], c.z[south]
    order = np.argsort(xs)
    xs, zs = xs[order], zs[order]
    bins = np.arange(float(xs.min()), float(xs.max()) + 10, 10.0)
    zb = np.array([float(zs[np.abs(xs - b) < 12].min()) if np.any(np.abs(xs - b) < 12) else np.nan for b in bins])
    ok = ~np.isnan(zb)
    bins, zb = bins[ok], zb[ok]

    def f(x):
        x = np.asarray(x, dtype=float)
        z = np.interp(x, bins, zb)
        return z - 29.0 + 9.0 * np.sin(x / 61.0) + 5.0 * np.sin(x / 23.0 + 1.3)
    return f


def build_cliff():
    spec = dict(CLIFF)
    spec["height"] = heights_from_poly(spec["poly"], spec["heights"])
    spec["walls"] = lambda c, idx, ks, hw: (hw + 2.4, hw + 2.4)
    c = Circuit(spec)
    L = Looks(LEVEL_TEX)
    base_looks(L, (0.38, 0.38, 0.40))
    L.add("verge", tex="grass.png", base=(0.42, 0.46, 0.22), rough=0.95)
    L.add("terrain", tex="grass.png", base=(1, 1, 1), rough=0.95, tt=(260, 120))
    L.add("stonewall", tex="stone.png", ntex="stone_n.png", base=(0.86, 0.80, 0.70), rough=0.9)
    L.add("ocean", ntex="ocean_n.png", base=(0.02, 0.10, 0.16), rough=0.12, metal=0.0, nscale=0.9, tt=(1, 1))
    L.add("foam", tex="foam.png", base=(1, 1, 1), rough=0.6, alpha="blend")
    L.add("rock", tex="rock.png", ntex="rock_n.png", base=(0.70, 0.64, 0.56), rough=0.9)
    L.add("cypress", tex="cypress.png", base=(1, 1, 1), rough=0.9, alpha="mask", cutoff=0.45)
    L.add("shrub", tex="shrub.png", base=(0.9, 0.95, 0.85), rough=0.9, alpha="mask", cutoff=0.45)
    L.add("tower", base=(0.92, 0.92, 0.90), rough=0.6)
    L.add("tower_red", base=(0.75, 0.08, 0.06), rough=0.55)
    L.add("lamp_glass", base=(0.9, 0.9, 0.7), emit=(1.0, 0.92, 0.6), rough=0.1)
    L.add("ridge_near", base=(1, 1, 1), rough=1.0)
    L.add("farland", tex="grass.png", base=(0.36, 0.40, 0.16), rough=0.95)
    L.add("banner", tex="banner.png", emtex="banner.png", base=(1, 1, 1), emit=(0.25, 0.25, 0.25), rough=0.6)
    L.add("zone_inner", base=(0.1, 0.45, 1.0), emit=(0.04, 0.2, 0.5), rough=0.5)
    L.add("zone_board", base=(0.1, 0.45, 1.0), emit=(0.05, 0.3, 0.8), rough=0.4)
    L.add("lamp_pole", base=(0.50, 0.51, 0.54), metal=0.6, rough=0.45)
    L.add("lamp_head", mdef="LampGlow", base=(1, 0.95, 0.85), emit=(0.6, 0.55, 0.45), rough=0.3)
    L.add("roofs", base=(0.62, 0.26, 0.16), rough=0.7)
    L.add("walls_w", tex="concrete.png", base=(0.95, 0.92, 0.86), rough=0.85)
    n = c.n
    # terrain: road heights extended, hills inland, cliffs falling to the sea south of the coastline
    x0, x1 = float(c.x.min()) - 320, float(c.x.max()) + 320
    z0, z1 = float(c.z.min()) - 340, float(c.z.max()) + 300
    sp = 8.0
    nx, nz = int((x1 - x0) / sp) + 1, int((z1 - z0) / sp) + 1
    gz, gx = np.mgrid[0:nz, 0:nx].astype(float)
    px, pz = x0 + gx * sp, z0 + gz * sp
    acc = np.zeros(px.shape)
    wsum = np.zeros(px.shape)
    for i0 in range(0, n, 48):
        sl = slice(i0, min(n, i0 + 48))
        d2 = (px[..., None] - c.x[sl]) ** 2 + (pz[..., None] - c.z[sl]) ** 2
        w = 1.0 / (d2 + 1600.0) ** 1.3
        acc += (w * c.y[sl]).sum(-1)
        wsum += w.sum(-1)
    base = acc / wsum
    _, _, dist = K.nearest_road(c, px, pz)
    rs = np.random.RandomState(13)
    lat = ktex.blur(rs.random_sample((nz, nx)), 4.0)
    lat = (lat - lat.min()) / (lat.max() - lat.min())
    inland = np.clip((pz - 380.0) / 300.0, 0, 1)
    nat = base + inland * 60.0 + (lat - 0.5) * np.minimum(dist, 200) * 0.25
    coast_z = coast_line(c)
    cz_line = coast_z(px)
    sea = np.clip((cz_line - pz) / 16.0, 0, 1)       # 0 on land, 1 well past the cliff edge
    sea = sea * sea * (3 - 2 * sea)
    nat = nat * (1 - sea) + (-14.0) * sea
    H, ni, latr, dist, t = K.road_clamped_height(c, nat, px, pz, extra=3.0, blend=14.0)
    H = np.where(pz < cz_line - 40, np.minimum(H, -14.0), H)
    edge = np.minimum.reduce([gx, nx - 1 - gx, gz, nz - 1 - gz]) * sp
    tap = np.clip(edge / 90.0, 0, 1)
    # inland edges rise into hills; the sea edge stays low
    edge_val = np.where(pz < cz_line + 60.0, -14.0, 60.0)
    H = H * tap + edge_val * (1 - tap)
    dHx = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) / (2 * sp)
    dHz = (np.roll(H, -1, 0) - np.roll(H, 1, 0)) / (2 * sp)
    slope = np.sqrt(dHx ** 2 + dHz ** 2)
    nz_ = ktex.blur(rs.random_sample(H.shape), 2.0)
    nz_ = (nz_ - nz_.min()) / (nz_.max() - nz_.min())
    grass = np.array([0.34, 0.40, 0.14])
    dry = np.array([0.56, 0.48, 0.24])
    scrub = np.array([0.20, 0.26, 0.10])
    rockc = np.array([0.62, 0.56, 0.46])
    sand = np.array([0.80, 0.72, 0.56])
    colr = grass * (1 - nz_[..., None]) + dry * nz_[..., None]
    colr = colr * (1 - (lat[..., None] > 0.55) * 0.5) + scrub * (lat[..., None] > 0.55) * 0.5
    rk = np.clip((slope - 0.5) / 0.3, 0, 1)
    colr = colr * (1 - rk[..., None]) + rockc * rk[..., None]
    beach = np.clip(1 - np.abs(H + 12.0) / 3.0, 0, 1) * (slope < 0.4)
    colr = colr * (1 - beach[..., None]) + sand * beach[..., None]
    parts = [K.elevation_grid(L, "terrain", x0, z0, nx, nz, sp, H, colr)]

    def terrain_h(x, z):
        fx_, fz_ = (x - x0) / sp, (z - z0) / sp
        ix, iz = int(fx_), int(fz_)
        if ix < 0 or iz < 0 or ix >= nx - 1 or iz >= nz - 1:
            return -14.0
        ax, az = fx_ - ix, fz_ - iz
        return float(H[iz, ix] * (1 - ax) * (1 - az) + H[iz, ix + 1] * ax * (1 - az) + H[iz + 1, ix] * (1 - ax) * az + H[iz + 1, ix + 1] * ax * az)

    # sea side: guardrail where the ground falls away, stone walls elsewhere
    kinds_l, kinds_r = [], []
    for i in range(n):
        for side, kinds, w in ((1, kinds_l, c.wl), (-1, kinds_r, c.wr)):
            p = c.pt(i, side * (float(w[i]) + 13.0))
            kinds.append("guardrail" if terrain_h(p[0], p[2]) < c.y[i] - 3.0 else "stone")
    for kinds in (kinds_l, kinds_r):
        for a, b in runs([k == "guardrail" for k in kinds]):
            if (b - a) % n < 12:
                for i in span(c, a, b):
                    kinds[i] = "stone"
    styles = {"guardrail": dict(profile=K.GUARDRAIL, look="guardrail", u_scale=1 / 6.0, posts=3, post_look="post"),
              "stone": dict(profile=K.STONE, look="stonewall", u_scale=1 / 2.5, v_scale=1 / 1.0, crease=0.7)}
    st = dict(asphalt="road", curb="curb_bw", band="gutter", verge="verge", curbs="corners", curb_k=1 / 70.0, outer_curbs=True,
              edge_lines=True, centre="double", seed=404, verge_past=1.6)
    parts += K.road_surfaces(c, L, st)
    parts += K.barriers(c, L, kinds_l, kinds_r, styles)
    parts += K.chevrons(c, L, "chevron", "post", k_min=1 / 40.0, every=4)
    # ocean, foam at the foot of the cliffs
    cx, cz = float((c.x.min() + c.x.max()) / 2), float((c.z.min() + c.z.max()) / 2)
    parts.append("<Transform DEF='Sea'>" + K.ocean_plane(L, "ocean", cx, cz - 1800, 9000, -12.6, tile=60.0) + "</Transform>")
    foam = Mesh()
    xs = np.arange(x0 + 60, x1 - 60, 6.0)
    rows = []
    for k, x in enumerate(xs):
        zc = float(coast_z(np.array([x]))[0]) - 12.0
        row = [foam.v((x, -12.45, zc - 2.0), (0, 1, 0), (k / 8.0, 0.0)), foam.v((x, -12.45, zc + 7.0), (0, 1, 0), (k / 8.0, 1.0))]
        rows.append(row)
    for k in range(len(rows) - 1):
        foam.quad(rows[k][0], rows[k + 1][0], rows[k + 1][1], rows[k][1])
    parts.append(shape(L, "foam", foam.its(dt=2)))
    # land beyond the terrain grid, inland (a frame around the grid, north of the coast)
    zc0 = float(np.max(cz_line)) + 80.0
    fl = Mesh()
    for (a0, a1, b0, b1) in ((x0 - 4000, x0 + 1, zc0, z1 + 4000), (x1 - 1, x1 + 4000, zc0, z1 + 4000), (x0, x1, z1 - 1, z1 + 4000)):
        ids = [fl.v((a0, 59.0, b0), (0, 1, 0), (a0 / 9, b0 / 9)), fl.v((a1, 59.0, b0), (0, 1, 0), (a1 / 9, b0 / 9)),
               fl.v((a1, 59.0, b1), (0, 1, 0), (a1 / 9, b1 / 9)), fl.v((a0, 59.0, b1), (0, 1, 0), (a0 / 9, b1 / 9))]
        fl.quad(*ids)
    parts.append(shape(L, "farland", fl.its(dt=1)))
    # far headlands
    parts.append(K.ridge_ring(L, "ridge_near", (cx, cz + 600), 1800, 2300, 40, 230, 51, -14, segs=120, arc=(0.05, math.pi - 0.05),
                              colors=((0.22, 0.30, 0.20), (0.44, 0.48, 0.42))))
    # lighthouse on the headland nearest the coast road's middle
    lh_x = 120.0
    lh_z = float(coast_z(np.array([lh_x]))[0]) + 4.0
    lh_y = terrain_h(lh_x, lh_z)
    lt = []
    lt.append(K.lathe_shape(L, "tower", [(3.2, 0), (2.6, 9), (2.2, 18), (2.0, 24)], 20, (lh_x, lh_y - 0.5, lh_z)))
    lt.append(K.lathe_shape(L, "tower_red", [(2.62, 8.5), (2.5, 11.5)], 20, (lh_x, lh_y - 0.5, lh_z)))
    lt.append(K.lathe_shape(L, "tower_red", [(2.3, 16.0), (2.2, 19.0)], 20, (lh_x, lh_y - 0.5, lh_z)))
    lt.append(K.lathe_shape(L, "post", [(3.0, 24), (3.0, 24.6), (0.1, 24.7)], 20, (lh_x, lh_y - 0.5, lh_z)))
    lt.append(K.lathe_shape(L, "lamp_glass", [(1.4, 24.6), (1.4, 26.6)], 16, (lh_x, lh_y - 0.5, lh_z)))
    lt.append(K.lathe_shape(L, "tower_red", [(1.7, 26.6), (0.2, 28.4)], 16, (lh_x, lh_y - 0.5, lh_z)))
    parts += lt
    # a cluster of white houses with tile roofs inland
    rng = RNG(505)
    houses, roofs = Mesh(normals=False), Mesh(normals=False)
    for k in range(60):
        hx = rng.r(x0 + 150, x1 - 150)
        hz = rng.r(80, z1 - 150)
        if not K.rect_clear(c, hx - 8, hx + 8, hz - 8, hz + 8, 6.0):
            continue
        hy = terrain_h(hx, hz)
        w, d, h = rng.r(6, 11), rng.r(6, 10), rng.r(3.5, 7)
        K.tex_box(houses, hx - w / 2, hx + w / 2, hy - 1.0, hy + h, hz - d / 2, hz + d / 2, 6.0, 6.0, top=False)
        rp = [(hx - w / 2 - 0.3, hy + h, hz - d / 2 - 0.3), (hx + w / 2 + 0.3, hy + h, hz - d / 2 - 0.3), (hx + w / 2 + 0.3, hy + h, hz + d / 2 + 0.3),
              (hx - w / 2 - 0.3, hy + h, hz + d / 2 + 0.3), (hx, hy + h + 2.2, hz)]
        ids = [roofs.v(q, (0, 1, 0), (0, 0)) for q in rp]
        for a_, b_ in ((0, 1), (1, 2), (2, 3), (3, 0)):
            roofs.tri(ids[a_], ids[b_], ids[4])
    parts += [shape(L, "walls_w", houses.ifs(crease=0.0, dp=1, dt=1)), shape(L, "roofs", roofs.ifs(crease=0.0, dp=1, dt=0))]
    # vegetation: cypress and shrubs on land, rocks on the cliff tops
    trees, shrubs, rocks = [], [], []
    step = 9.0
    for zi in range(int((z1 - z0) / step)):
        for xi in range(int((x1 - x0) / step)):
            x = x0 + (xi + rng.u()) * step
            z = z0 + (zi + rng.u()) * step
            ix, iz = int((x - x0) / sp), int((z - z0) / sp)
            if ix < 1 or iz < 1 or ix >= nx - 2 or iz >= nz - 2:
                continue
            dd = dist[iz, ix]
            if dd < 11 or H[iz, ix] < -8 or tap[iz, ix] < 0.6:
                continue
            y = terrain_h(x, z)
            if slope[iz, ix] < 0.5 and dd < 260:
                r_ = rng.u()
                if r_ < 0.05 and len(trees) < 700:
                    h = rng.r(7, 14)
                    trees.append((x, y, z, h, h * 0.28, rng.r(0, math.pi)))
                elif r_ < 0.16 and len(shrubs) < 900:
                    h = rng.r(0.9, 2.2)
                    shrubs.append((x, y, z, h, h * 2.2, rng.r(0, math.pi)))
            if slope[iz, ix] > 0.45 and dd < 60 and rng.u() < 0.2 and len(rocks) < 160:
                rocks.append((x, y, z, rng.r(0.8, 2.6), rng.i(1 << 30)))
    parts += K.billboard_trees(L, "cypress", trees, tile=200)
    parts += K.billboard_trees(L, "shrub", shrubs, tile=200)
    parts.append(K.boulders(L, "rock", rocks))
    parts += K.gantry(c, L, "banner", "frame", "startlights")
    zones = zones_for(c, 1 / 80.0)
    parts += zone_marks(c, L, zones)
    lamps_xml = "<Group DEF='Lamps'>" + K.street_lamps(c, L, 30, height=8.0, arm=2.0, pool_look=None, sides=(1,)) + "</Group>"
    cams, cam_info = K.viewpoints(c, 12, 13, height=(4.0, 12.0))
    sun_dir = (0.25, 0.86, -0.44)
    sky = dict(name="sky_cliff", angles=[0.7, 1.15, 1.45, 1.571], colors=[(0.10, 0.28, 0.62), (0.20, 0.42, 0.78), (0.42, 0.62, 0.88), (0.68, 0.80, 0.94), (0.80, 0.88, 0.96)],
               g_angles=[1.4, 1.571], g_colors=[(0.10, 0.22, 0.30), (0.20, 0.34, 0.44), (0.62, 0.74, 0.84)],
               spec=dict(sun_dir=sun_dir, clouds=0.38, cloud_h=1.0, cloud_scale=0.12, cloud_lit=(1.0, 1.0, 0.98), cloud_shade=(0.62, 0.68, 0.78),
                         cloud_rim=(0.1, 0.1, 0.1), cloud_alpha=0.9, disc=0.02, glow_w=0.12, glow_a=0.6, glow_col=(1.0, 0.98, 0.9), disc_col=(1.0, 1.0, 0.96)))
    fog = dict(color=(0.66, 0.78, 0.90), range=7500)
    sun = dict(dir=tuple(-v for v in sun_dir), color=(1.0, 0.97, 0.90), intensity=3.3, shadow=0.75)
    fills = sky_fills((0.50, 0.64, 0.95), 0.85, (0.55, 0.50, 0.40), 0.35, sun_dir)
    head = header_nodes(c, "cliffside", "Cliffside Esses", "Coastal cliff road, noon", "noon", "gravel", 16, zones, [],
                        sky, fog, sun, fills, cams)
    body = head + lamps_xml + "<Group DEF='Track'>" + "".join(parts) + "</Group>"
    doc = x3d_doc("KANSEI Cliffside Esses", "KANSEI circuit Cliffside Esses: a coastal cliff road at noon with fast sweepers and one tight chicane. Track metadata (kansei:track) is read by the simulation; the meshes are built from the same samples.",
                  COMPONENTS, body, GEN)
    info = dict(id="cliffside", name="Cliffside Esses", subtitle="Coastal cliff road, noon", time="noon", runoff="gravel",
                samples=c.n, length=round(c.length, 1), trackcams=len(cam_info), zones=len(zones), props=0)
    return doc, info, sky


# --------------------------------------------------------------------------------------------
# PRACTICE PAD: a flat 60 m radius skidpad loop with cones

PAD = dict(
    poly=[(-60.0, -60.0), (60.0, -60.0), (60.0, 60.0), (-60.0, 60.0)],
    radii=[60.0, 60.0, 60.0, 60.0],
    half_width=13.0, smooth=0.0, bank_gain=0.0, bank_max=0.0, line_gain=0.0, start=0.0,
)
PAD_R = 60.0


def build_pad():
    spec = dict(PAD)
    spec["height"] = lambda xz: np.zeros(len(xz))
    spec["walls"] = lambda c, idx, ks, hw: (np.full(len(idx), 46.0), np.full(len(idx), 44.0))
    spec["poly"] = spec["poly"][::-1]   # counter-clockwise: the loop turns left, the island is on the left
    c = Circuit(spec)
    L = Looks(LEVEL_TEX)
    base_looks(L, (0.40, 0.40, 0.43))
    L.add("pad", tex="asphalt.png", ntex="asphalt_n.png", base=(0.42, 0.42, 0.45), rough=0.85, aniso="8", nscale=0.5)
    L.add("verge", tex="asphalt.png", base=(0.36, 0.36, 0.39), rough=0.88)
    L.add("band", tex="asphalt.png", base=(0.40, 0.40, 0.43), rough=0.85)
    L.add("grass", tex="grass.png", base=(0.30, 0.44, 0.14), rough=0.95)
    L.add("island", tex="grass.png", base=(0.26, 0.42, 0.12), rough=0.95)
    L.add("tyres", tex="tyres.png", ntex="tyres_n.png", base=(1, 1, 1), rough=0.75)
    L.add("jersey", tex="concrete.png", ntex="concrete_n.png", base=(0.70, 0.70, 0.70), rough=0.8)
    L.add("tower", tex="concrete.png", base=(0.86, 0.86, 0.84), rough=0.8)
    L.add("glass", base=(0.08, 0.12, 0.16), rough=0.08, metal=0.5)
    L.add("hangar", tex="guardrail.png", base=(0.78, 0.80, 0.84), rough=0.5, metal=0.4)
    L.add("ridge_near", base=(1, 1, 1), rough=1.0)
    L.add("sock", base=(1.0, 0.42, 0.06), rough=0.7)
    L.add("banner", tex="banner.png", emtex="banner.png", base=(1, 1, 1), emit=(0.25, 0.25, 0.25), rough=0.6)
    L.add("zone_inner", base=(0.15, 0.9, 0.35), emit=(0.06, 0.4, 0.15), rough=0.5)
    L.add("zone_board", base=(0.15, 0.9, 0.35), emit=(0.08, 0.6, 0.2), rough=0.4)
    L.add("lamp_pole", base=(0.70, 0.71, 0.74), metal=0.6, rough=0.4)
    L.add("lamp_head", mdef="LampGlow", base=(1, 1, 1), emit=(0.9, 0.9, 0.85), rough=0.3)
    n = c.n
    st = dict(asphalt="pad", curb="curb_rw", band="band", verge="verge", curbs="none", edge_lines=True, seed=505,
              verge_past=0.0, wear_half=1.6, skids=True, asphalt_tile=8.0)
    parts = K.road_surfaces(c, L, st)
    # the whole pad is asphalt: an apron disc out to the outer wall and in to the island
    parts.append(K.disc(L, "island", 0.0, 0.0, 0.0, 14.2, 0.02, 6.0, segs=64))
    parts.append(K.flat_ground(L, "grass", 0.0, 0.0, 6000, -0.08, 9.0, rings=8))
    # painted guide circles every 4 m across the loop
    rings = Mesh()
    for rr in (PAD_R - 8, PAD_R - 4, PAD_R + 4, PAD_R + 8):
        segs = 160
        row = []
        for k in range(segs + 1):
            a = 2 * math.pi * k / segs
            row.append((rings.v((math.cos(a) * (rr - 0.06), 0.011, math.sin(a) * (rr - 0.06)), (0, 1, 0), (0, k / 8)),
                        rings.v((math.cos(a) * (rr + 0.06), 0.011, math.sin(a) * (rr + 0.06)), (0, 1, 0), (1, k / 8))))
        for k in range(0, segs, 2):
            rings.quad(row[k][0], row[k + 1][0], row[k + 1][1], row[k][1])
    parts.append(shape(L, "paint", rings.ifs(crease=1.0, dp=2, dt=1)))
    styles = {"tyres": dict(profile=K.TYRES, look="tyres", u_scale=1 / 1.2, v_scale=1 / 0.92, crease=0.6),
              "jersey": dict(profile=K.JERSEY, look="jersey", u_scale=0.25, v_scale=0.5)}
    parts += K.barriers(c, L, ["tyres"] * n, ["jersey"] * n, styles)
    # control tower, hangar, windsock, light towers
    tw = []
    tw.append(K.lathe_shape(L, "tower", [(4.0, 0), (3.6, 14), (5.5, 14.2)], 8, (0, 0, 150), crease=0.2))
    tw.append(K.lathe_shape(L, "glass", [(5.4, 14.2), (6.0, 17.5)], 8, (0, 0, 150), crease=0.2))
    tw.append(K.lathe_shape(L, "post", [(6.2, 17.5), (6.2, 18.0), (0.2, 18.2)], 8, (0, 0, 150), crease=0.2))
    hg = Mesh(normals=False)
    K.tex_box(hg, -170, -110, 0, 16, 80, 140, 6.0, 1.0, top=False)
    roof = Mesh(normals=False)
    for k in range(13):
        a0 = math.pi * k / 12
        xk = -170 + 60 * k / 12
    arch = [(-170 + 60 * (1 - math.cos(math.pi * k / 12)) / 2, 16 + 9 * math.sin(math.pi * k / 12)) for k in range(13)]
    rows = []
    for zz in (80.0, 140.0):
        rows.append([roof.v((x_, y_, zz), (0, 1, 0), (x_ / 6, 0)) for x_, y_ in arch])
    for k in range(12):
        roof.quad(rows[0][k], rows[1][k], rows[1][k + 1], rows[0][k + 1])
    tw.append(shape(L, "hangar", hg.ifs(crease=0.0, dp=1, dt=1)))
    tw.append(shape(L, "hangar", roof.ifs(crease=1.0, dp=1, dt=1)))
    sock = Mesh(normals=False)
    K.post_box(sock, (120, 4.0, -120), (0.12, 8.0, 0.12), 0.0)
    sock.lathe([(0.55, 0.0), (0.25, 3.2)], 10, (120, 7.6, -120), axis="x")
    tw.append(shape(L, "sock", sock.ifs(crease=1.0, dp=2, dt=0)))
    parts += tw
    parts.append(K.ridge_ring(L, "ridge_near", (0, 0), 1400, 1900, 40, 180, 61, -5, segs=120,
                              colors=((0.20, 0.30, 0.18), (0.38, 0.46, 0.40))))
    # cones: the ring markers on both edges and a slalom gate pair at four points
    props = []
    for k in range(48):
        a = 2 * math.pi * k / 48
        for rr in (PAD_R - float(c.hw[0]) - 0.8, PAD_R + float(c.hw[0]) + 0.8):
            props.append((1, math.cos(a) * rr, math.sin(a) * rr, 0.17, 0.0, -a))
    zones = []
    for q in range(4):
        i0 = (q * n // 4 + n // 8) % n
        zones.append(((i0 - 10) % n, (i0 + 10) % n, 1, 1))
        zones.append(((i0 + 14) % n, (i0 + 30) % n, -1, 2))
    parts += zone_marks(c, L, zones)
    stp = Mesh(normals=False)
    p0 = c.pt(0, -(float(c.hw[0]) + 3.0))
    K.post_box(stp, (p0[0], 2.2, p0[2]), (0.3, 4.4, 0.3), c.yaw(0))
    lt = Mesh()
    p1 = c.pt(0, -(float(c.hw[0]) + 2.2))
    for k in range(5):
        lt.box((p1[0], 3.0 + k * 0.42, p1[2]), (0.36, 0.36, 0.3), c.yaw(0))
    parts += [shape(L, "frame", stp.ifs(crease=0.0, dp=2, dt=0)), shape(L, "startlights", lt.its())]
    lamps_xml = "<Group DEF='Lamps'>" + K.street_lamps(c, L, max(1, n // 8), height=14.0, arm=1.0, pool_look=None, sides=(-1,)) + "</Group>"
    cams, cam_info = K.viewpoints(c, 0, 17)
    # the loop is one long corner: place eight cameras evenly around the outside
    cams = []
    from kx3d import look_rotation as _lr, rot_str as _rs
    for k in range(8):
        i = (k * n // 8 + n // 16) % n
        eye = c.pt(i, -(float(c.wr[i]) - 4.0), 3.5 + (k % 3) * 2.5)
        tgt = c.pt((i + 6) % n, 0.0, 0.8)
        cams.append(f"<Viewpoint DEF='TrackCam{k}' description='Pad camera {k + 1}' position='{vec(*eye, d=2)}' orientation='{_rs(_lr(eye, tgt))}' fieldOfView='0.7'/>")
    cams = "".join(cams)
    sun_dir = (-0.35, 0.80, 0.48)
    sky = dict(name="sky_pad", angles=[0.7, 1.15, 1.45, 1.571], colors=[(0.12, 0.30, 0.64), (0.22, 0.44, 0.80), (0.46, 0.64, 0.90), (0.72, 0.82, 0.94), (0.84, 0.90, 0.96)],
               g_angles=[1.4, 1.571], g_colors=[(0.20, 0.26, 0.16), (0.30, 0.36, 0.24), (0.70, 0.78, 0.82)],
               spec=dict(sun_dir=sun_dir, clouds=0.45, cloud_h=1.0, cloud_scale=0.10, cloud_lit=(1.0, 1.0, 0.98), cloud_shade=(0.60, 0.66, 0.76),
                         cloud_rim=(0.1, 0.1, 0.1), cloud_alpha=0.92, disc=0.02, glow_w=0.12, glow_a=0.6, glow_col=(1.0, 0.98, 0.9), disc_col=(1.0, 1.0, 0.96)))
    fog = dict(color=(0.70, 0.80, 0.90), range=7000)
    sun = dict(dir=tuple(-v for v in sun_dir), color=(1.0, 0.97, 0.92), intensity=3.2, shadow=0.75)
    fills = sky_fills((0.50, 0.64, 0.95), 0.85, (0.45, 0.50, 0.38), 0.35, sun_dir)
    head = header_nodes(c, "practice-pad", "Practice Pad", "Skidpad loop for learning", "noon", "tarmac", 12, zones,
                        [(k, x, z, r) for k, x, z, r, _y, _yw in props], sky, fog, sun, fills, cams)
    body = head + lamps_xml + props_nodes(L, props) + "<Group DEF='Track'>" + "".join(parts) + "</Group>"
    doc = x3d_doc("KANSEI Practice Pad", "KANSEI circuit Practice Pad: a flat 60 m radius skidpad loop with cones, for learning and handling tests. Track metadata (kansei:track) is read by the simulation; the meshes are built from the same samples.",
                  COMPONENTS, body, GEN)
    info = dict(id="practice-pad", name="Practice Pad", subtitle="Skidpad loop for learning", time="noon", runoff="tarmac",
                samples=c.n, length=round(c.length, 1), trackcams=8, zones=len(zones), props=len(props))
    return doc, info, sky


# --------------------------------------------------------------------------------------------
# textures

def textures(skies: list[dict]) -> dict[str, bytes]:
    T = {}
    a, an = ktex.asphalt()
    T["asphalt.png"], T["asphalt_n.png"] = ktex.png(a), ktex.png(an)
    cc, cn = ktex.concrete()
    T["concrete.png"], T["concrete_n.png"] = ktex.png(cc), ktex.png(cn)
    T["grass.png"] = ktex.png(ktex.terrain_detail())
    r, rn = ktex.rock()
    T["rock.png"], T["rock_n.png"] = ktex.png(r), ktex.png(rn)
    T["paint.png"] = ktex.png(ktex.paint_line())
    T["wear.png"] = ktex.png(ktex.wear_band())
    T["skids.png"] = ktex.png(ktex.skid_band())
    T["checker.png"] = ktex.png(ktex.checker())
    T["curb_rw.png"] = ktex.png(ktex.curb((0.82, 0.10, 0.08), (0.95, 0.95, 0.93)))
    T["curb_yb.png"] = ktex.png(ktex.curb((0.95, 0.74, 0.08), (0.07, 0.07, 0.08), seed=92))
    T["curb_bw.png"] = ktex.png(ktex.curb((0.10, 0.30, 0.78), (0.95, 0.95, 0.93), seed=93))
    T["guardrail.png"] = ktex.png(ktex.guardrail())
    T["chevron.png"] = ktex.png(ktex.chevron())
    T["pine.png"] = ktex.png(ktex.pine())
    T["pines.png"] = ktex.png(ktex.pine_cluster())
    T["banner.png"] = ktex.png(ktex.banner([("KANSEI", (0.96, 0.95, 0.92), (0.06, 0.07, 0.09))]))
    fa, fae = ktex.facade(301, "concrete")
    fb, fbe = ktex.facade(302, "glass")
    T["facade_a.png"], T["facade_a_e.png"], T["facade_b.png"], T["facade_b_e.png"] = ktex.png(fa), ktex.png(fae), ktex.png(fb), ktex.png(fbe)
    T["neon_signs.png"] = ktex.png(ktex.neon_atlas(SIGNS))
    T["spot.png"] = ktex.png(ktex.soft_spot())
    sa, san = ktex.salt()
    T["salt.png"], T["salt_n.png"] = ktex.png(sa), ktex.png(san)
    stn, stnn = ktex.stone_wall()
    T["stone.png"], T["stone_n.png"] = ktex.png(stn), ktex.png(stnn)
    T["ocean_n.png"] = ktex.png(ktex.ocean_normal())
    T["foam.png"] = ktex.png(ktex.foam())
    T["cypress.png"] = ktex.png(ktex.cypress())
    T["shrub.png"] = ktex.png(ktex.shrub())
    ty, tyn = ktex.tyre_wall()
    T["tyres.png"], T["tyres_n.png"] = ktex.png(ty), ktex.png(tyn)
    # cars and showroom
    T["sidewall.png"] = ktex.png(ktex.tyre_sidewall())
    T["tread.png"] = ktex.png(ktex.tread())
    T["grille.png"] = ktex.png(ktex.grille())
    T["lens.png"] = ktex.png(ktex.lamp_lens())
    T["plates.png"] = ktex.png(ktex.plates([c["plate"] for c in kcars.CARS]))
    T["carbon.png"] = ktex.png(ktex.carbon())
    T["floor.png"] = ktex.png(ktex.floor_concrete())
    T["strip.png"] = ktex.png(ktex.light_strip())
    T["gsign.png"] = ktex.png(ktex.garage_sign())
    for sk in skies:
        faces = ktex.sky_faces(256, sk["spec"], seed=hash_seed(sk["name"]))
        for f in ("front", "back", "left", "right", "top"):
            T[f"{sk['name']}_{f}.png"] = ktex.png(faces[f])
    return T


def hash_seed(s: str) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest()[:6], 16)


# --------------------------------------------------------------------------------------------

def build(only: str | None = None) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    infos, skies = [], []
    for fid, fn in (("kessel-pass", build_kessel), ("neon-overpass", build_neon), ("salt-ring", build_salt), ("cliffside", build_cliff), ("practice-pad", build_pad)):
        if only and fid != only:
            continue
        doc, info, sky = fn()
        data = doc.encode("utf-8")
        files[f"levels/{fid}.x3d"] = data
        tg = TARGETS[fid]   # the page shows medal targets before it loads a level (scaled per car there)
        info.update(file=f"{fid}.x3d", bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                    targets=dict(zip(("goldLap", "silverLap", "bronzeLap", "rushBronze", "rushSilver", "rushGold", "rushPlatinum"), tg)))
        infos.append(info)
        skies.append(sky)
    if infos:
        man = {"schema": "kansei.levels/1", "generator": "build/build_world.py", "levels": infos}
        files["levels/MANIFEST.json"] = (json.dumps(man, indent=1, sort_keys=True) + "\n").encode()
    if only in (None, "cars"):
        cinfos = []
        for c in kcars.CARS:
            doc, info = kcars.build_car(c)
            data = doc.encode("utf-8")
            files[f"cars/{c['id']}.x3d"] = data
            info.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            cinfos.append(info)
        man = {"schema": "kansei.cars/1", "generator": "build/build_world.py",
               "frame": "+Z forward, +X left, +Y up; wheels on y = 0; origin under the centre of mass",
               "cars": cinfos}
        files["cars/MANIFEST.json"] = (json.dumps(man, indent=1, sort_keys=True) + "\n").encode()
    if only in (None, "garage", "cars"):
        files["garage.x3d"] = kcars.build_garage().encode("utf-8")
    for k, v in textures(skies).items():
        files[f"textures/{k}"] = v
    return files


def main(argv: list[str]) -> int:
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    files = build(only)
    if "--check" in argv:
        bad = [k for k, v in sorted(files.items()) if not (ROOT / k).exists() or (ROOT / k).read_bytes() != v]
        print(json.dumps({"rebuild_identical": not bad, "files": len(files), "differs": bad}))
        return 1 if bad else 0
    for k, v in sorted(files.items()):
        p = ROOT / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(v)
    tex = sum(len(v) for k, v in files.items() if k.startswith("textures/"))
    for k, v in sorted(files.items()):
        if not k.startswith("textures/"):
            print(f"{k:34s} {len(v):>9d} B  sha256 {hashlib.sha256(v).hexdigest()[:12]}")
    print(f"textures/ {sum(1 for k in files if k.startswith('textures/'))} files, {tex} B")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
