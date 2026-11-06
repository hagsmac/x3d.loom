#!/usr/bin/env python3
"""Generate every x3d.platformer level as an X3D 4.0 file (Loom law 1: generator, not file).

  python3 -I build/build_levels.py            write levels/*.x3d and levels/MANIFEST.json
  python3 -I build/build_levels.py --check    rebuild in memory and fail if any byte differs

Standard library only. The output is byte-for-byte reproducible: no clock, fixed seeds,
fixed float formatting.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from x3dkit import (RNG, esc, f, gear_shape_children, helix_extrusion, material, metaset, mfstr,  # noqa: E402
                    torus_extrusion, vec)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "levels"
GRAVITY = 38.0
DEPTH = 3.2

THEMES = {
    "meadow": dict(
        sky=[(0.30, 0.52, 0.92), (0.52, 0.74, 0.98), (0.80, 0.90, 1.0), (1.0, 0.88, 0.74)], sky_angle=[0.7, 1.15, 1.45],
        ground_sky=(0.62, 0.78, 0.55), fog=(0.86, 0.90, 0.96), fog_range=240,
        key=((1.0, 0.94, 0.84), 1.05, (-0.45, -0.85, -0.42)), fill=((0.55, 0.68, 1.0), 0.38, (0.7, -0.25, -0.6)),
        top=(0.42, 0.80, 0.30), top2=(0.32, 0.66, 0.24), body=(0.84, 0.52, 0.33), body2=(0.60, 0.36, 0.24),
        hill_far=(0.56, 0.74, 0.70), hill_mid=(0.44, 0.72, 0.42), hill_near=(0.36, 0.64, 0.34),
        cloud=(1.0, 1.0, 1.0), leaf=(0.33, 0.70, 0.30), leaf2=(0.50, 0.82, 0.32), trunk=(0.55, 0.38, 0.24),
        accent=(0.95, 0.40, 0.55), stars=False),
    "gorge": dict(
        sky=[(0.16, 0.12, 0.36), (0.52, 0.26, 0.48), (0.95, 0.48, 0.42), (1.0, 0.76, 0.46)], sky_angle=[0.6, 1.05, 1.42],
        ground_sky=(0.50, 0.30, 0.30), fog=(0.98, 0.70, 0.52), fog_range=210,
        key=((1.0, 0.78, 0.55), 1.1, (0.55, -0.6, -0.55)), fill=((0.55, 0.45, 0.95), 0.42, (-0.6, -0.3, -0.6)),
        top=(0.96, 0.70, 0.42), top2=(0.86, 0.56, 0.34), body=(0.74, 0.40, 0.30), body2=(0.50, 0.26, 0.24),
        hill_far=(0.62, 0.36, 0.46), hill_mid=(0.70, 0.40, 0.36), hill_near=(0.56, 0.30, 0.28),
        cloud=(1.0, 0.86, 0.78), leaf=(0.86, 0.46, 0.30), leaf2=(0.95, 0.62, 0.30), trunk=(0.42, 0.26, 0.22),
        accent=(0.40, 0.85, 0.95), stars=False),
    "spire": dict(
        sky=[(0.02, 0.02, 0.08), (0.05, 0.06, 0.20), (0.16, 0.12, 0.36), (0.40, 0.22, 0.46)], sky_angle=[0.7, 1.15, 1.48],
        ground_sky=(0.08, 0.06, 0.16), fog=(0.16, 0.12, 0.30), fog_range=200,
        key=((0.80, 0.86, 1.0), 0.85, (-0.35, -0.8, -0.5)), fill=((1.0, 0.55, 0.35), 0.55, (0.6, -0.2, -0.7)),
        top=(0.30, 0.95, 0.95), top2=(0.20, 0.70, 0.78), body=(0.36, 0.38, 0.52), body2=(0.22, 0.22, 0.34),
        hill_far=(0.16, 0.14, 0.32), hill_mid=(0.20, 0.18, 0.38), hill_near=(0.26, 0.22, 0.44),
        cloud=(0.55, 0.50, 0.85), leaf=(0.55, 0.40, 0.95), leaf2=(0.90, 0.45, 0.85), trunk=(0.30, 0.28, 0.40),
        accent=(1.0, 0.70, 0.25), stars=True),
}


def group(name: str, items: list[str]) -> str:
    return f"<Group DEF='{name}'>" + "".join(items) + "</Group>" if items else ""


class Level:
    def __init__(self, key: str, title: str, theme: str, start, kill_y: float, par: float, seed: int, subtitle: str = ""):
        self.key, self.title, self.theme_name, self.T = key, title, theme, THEMES[theme]
        self.start, self.kill_y, self.par, self.subtitle = start, kill_y, par, subtitle
        self.rng = RNG(seed)
        self.n: dict[str, int] = {}
        self.decor: list[str] = []
        self.statics: list[str] = []
        self.dyn: list[str] = []
        self.ents: list[str] = []
        self.bodies: list[str] = []
        self.joints: list[str] = []
        self.interps: list[str] = []
        self.routes: list[str] = []
        self.counts = dict(statics=0, dynamic=0, kinematic=0, joints=0, cogs=0, stars=0)
        self.extent = [1e9, -1e9, 1e9, -1e9]
        self.cp = 0

    def uid(self, p: str) -> str:
        self.n[p] = self.n.get(p, 0) + 1
        return f"{p}_{self.n[p]}"

    def grow(self, x0, x1, y0, y1):
        e = self.extent
        e[0], e[1], e[2], e[3] = min(e[0], x0), max(e[1], x1), min(e[2], y0), max(e[3], y1)

    # --- physics contract ------------------------------------------------------------------
    def body(self, d, x, y, shape, size, fixed=True, mass=1.0, a=0.0, **meta):
        rot = f" orientation='0 0 1 {f(a)}'" if a else ""
        geom = f"<Box size='{vec(size[0], size[1], 1)}'/>" if shape == "box" else f"<Sphere radius='{f(size)}'/>"
        extra = ""
        if "w" in meta and meta.get("kinematic"):
            extra = f" angularVelocity='0 0 {f(meta.pop('w'))}'"
        self.bodies.append(
            f"<RigidBody DEF='B_{d}' fixed='{'true' if fixed else 'false'}' mass='{f(mass)}' position='{vec(x, y, 0)}'{rot}{extra}>"
            f"{metaset('nib:body', **meta)}<CollidableShape containerField='geometry'><Shape containerField='shape'>{geom}</Shape></CollidableShape></RigidBody>")
        if fixed:
            self.counts["statics"] += 1
        elif meta.get("kinematic"):
            self.counts["kinematic"] += 1
        else:
            self.counts["dynamic"] += 1

    def hinge(self, b1, b2, x, y):
        self.joints.append(f"<SingleAxisHingeJoint anchorPoint='{vec(x, y, 0)}' axis='0 0 1'>"
                           f"<RigidBody USE='B_{b1}' containerField='body1'/><RigidBody USE='B_{b2}' containerField='body2'/></SingleAxisHingeJoint>")
        self.counts["joints"] += 1

    # --- static ground ---------------------------------------------------------------------
    def block(self, x0, x1, top, bottom=None, style="grass", role=None, island=False, **meta):
        bottom = top - 0.9 if bottom is None else bottom
        w, h = x1 - x0, top - bottom
        cx, cy = (x0 + x1) / 2, (top + bottom) / 2
        d = self.uid("ground")
        self.body(d, cx, cy, "box", (w, h), fixed=True, role=role or "solid", **meta)
        self.statics.append(self.block_visual(cx, cy, w, h, style, island))
        self.grow(x0, x1, bottom, top)
        return d

    def ground(self, x0, x1, top, bottom=-16.0, style="grass"):
        return self.block(x0, x1, top, bottom, style)

    def ledge(self, x0, x1, top, thick=0.9, style="grass"):
        return self.block(x0, x1, top, top - thick, style, island=True)

    def block_visual(self, cx, cy, w, h, style, island=False) -> str:
        rng, out = self.rng, []
        out.append(f"<Transform translation='{vec(cx, cy, 0)}'>")
        body_app, top_app = ("A_body", "A_top") if style == "grass" else ("A_stone", "A_moss") if style == "stone" else ("A_iron", "A_brass")
        out.append(f"<Shape><Appearance USE='{body_app}'/><Box size='{vec(w, h, DEPTH)}'/></Shape>")
        if h > 2.2 and style != "brass":  # a darker deep band on the visible face gives the soil some depth
            band_h = h - 1.5
            out.append(f"<Transform translation='{vec(0, -h / 2 + band_h / 2, DEPTH / 2 + 0.01)}'><Shape><Appearance USE='{'A_body2' if style == 'grass' else 'A_iron'}'/>"
                       f"<Box size='{vec(w - 0.02, band_h, 0.02)}'/></Shape></Transform>")
        cap = 0.34
        out.append(f"<Transform translation='{vec(0, h / 2 - cap / 2 + 0.04, 0)}'><Shape><Appearance USE='{top_app}'/>"
                   f"<Box size='{vec(w + 0.18, cap, DEPTH + 0.18)}'/></Shape></Transform>")
        if style == "stone" and h > 5 and self.theme_name == "spire":  # machine-tower facade: brass bands, lit windows
            for k in range(int((h - 1.2) // 3.2)):
                by = h / 2 - 1.6 - k * 3.2
                out.append(f"<Transform translation='{vec(0, by, DEPTH / 2 + 0.03)}'><Shape><Appearance USE='A_brass'/><Box size='{vec(w + 0.06, 0.16, 0.08)}'/></Shape></Transform>")
                for wx in range(max(1, int(w // 1.6))):
                    if rng.r(0, 1) < 0.55:
                        px = -w / 2 + (wx + 0.5) * w / max(1, int(w // 1.6))
                        out.append(f"<Transform translation='{vec(px, by - 1.4, DEPTH / 2 + 0.03)}'><Shape><Appearance USE='A_window'/><Box size='0.42 0.62 0.04'/></Shape></Transform>")
        if style == "stone" and h > 5 and self.theme_name == "gorge":  # sandstone strata
            for k in range(int(h // 1.3)):
                out.append(f"<Transform translation='{vec(0, h / 2 - 0.9 - k * 1.3, DEPTH / 2 + 0.02)}'><Shape><Appearance USE='{'A_top' if k % 2 else 'A_body2'}'/><Box size='{vec(w + 0.02, 0.12, 0.03)}'/></Shape></Transform>")
        if style == "brass":  # neon trim on the front edge
            out.append(f"<Transform translation='{vec(0, h / 2 - 0.02, DEPTH / 2 + 0.1)}'><Shape><Appearance USE='A_glow'/>"
                       f"<Box size='{vec(w + 0.1, 0.07, 0.05)}'/></Shape></Transform>")
        # pebbles on the visible face, tufts and flowers on top (picture only)
        nface = int(min(10, w * min(h, 4) * 0.12))
        for _ in range(nface):
            px, py = rng.r(-w / 2 + 0.3, w / 2 - 0.3), rng.r(h / 2 - 1.4, h / 2 - 0.5)
            s = rng.r(0.07, 0.16)
            out.append(f"<Transform translation='{vec(px, py, DEPTH / 2)}' scale='{vec(s * 1.4, s, s * 0.5)}'><Shape USE='S_pebble'/></Transform>")
        if style == "grass":
            for _ in range(int(w * 0.9)):
                px, pz = rng.r(-w / 2 + 0.2, w / 2 - 0.2), rng.r(-DEPTH / 2 + 0.2, DEPTH / 2 - 0.1)
                kind = rng.pick(["S_tuft", "S_tuft", "S_tuft", "S_flower_a", "S_flower_b"])
                s = rng.r(0.7, 1.25)
                out.append(f"<Transform translation='{vec(px, h / 2 + 0.2, pz)}' scale='{vec(s, s, s)}'><Shape USE='{kind}'/></Transform>")
        if island:
            out.append(f"<Transform translation='{vec(0, -h / 2 - 0.55, 0)}' rotation='1 0 0 3.1416' scale='{vec(1, 1, DEPTH / max(w, 0.1))}'>"
                       f"<Shape><Appearance USE='{'A_body' if style == 'grass' else 'A_iron'}'/><Cone bottomRadius='{f(w / 2)}' height='1.1'/></Shape></Transform>")
        out.append("</Transform>")
        return "".join(out)

    def backwall(self, x0, x1, y0, y1):
        """Picture only: a dark wall behind a cave so it reads as inside the ground."""
        self.statics.append(f"<Transform translation='{vec((x0 + x1) / 2, (y0 + y1) / 2, -DEPTH / 2 + 0.05)}'>"
                            f"<Shape><Appearance USE='A_cave'/><Box size='{vec(x1 - x0, y1 - y0, 0.1)}'/></Shape></Transform>")

    # --- props -----------------------------------------------------------------------------
    def crate(self, x, y_bottom, size=1.2, mass=1.5, respawn=True, kind="crate"):
        d = self.uid(kind)
        y = y_bottom + size / 2
        self.body(d, x, y, "box", (size, size), fixed=False, mass=mass, role=kind, respawn=respawn, friction=0.65)
        s = size / 1.2
        self.dyn.append(f"<Transform DEF='V_{d}' translation='{vec(x, y, 0)}'><Transform scale='{vec(s, s, s)}'><Group USE='G_crate'/></Transform></Transform>")
        return d

    def ball(self, x, y, r=0.6, mass=2.0, respawn=True):
        d = self.uid("ball")
        self.body(d, x, y, "sphere", r, fixed=False, mass=mass, role="ball", respawn=respawn, friction=0.6, restitution=0.25)
        self.dyn.append(f"<Transform DEF='V_{d}' translation='{vec(x, y, 0)}'><Transform scale='{vec(r, r, r)}'><Group USE='G_ball'/></Transform></Transform>")
        return d

    def plank(self, x, y, length, thick=0.28, mass=0.8, a=0.0, role="plank", app="A_wood"):
        d = self.uid(role)
        self.body(d, x, y, "box", (length, thick), fixed=False, mass=mass, a=a, role=role, friction=0.8)
        rot = f" rotation='0 0 1 {f(a)}'" if a else ""
        self.dyn.append(f"<Transform DEF='V_{d}' translation='{vec(x, y, 0)}'{rot}>"
                        f"<Shape><Appearance USE='{app}'/><Box size='{vec(length, thick, 1.9)}'/></Shape>"
                        f"<Transform translation='{vec(0, 0, 0.96)}'><Shape><Appearance USE='A_wood2'/><Box size='{vec(length * 0.96, thick * 0.35, 0.04)}'/></Shape></Transform>"
                        f"</Transform>")
        return d

    def bridge(self, x0, x1, y, anchor_left, anchor_right, n):
        """A hanging bridge: n planks joined end to end, pinned to two static bodies."""
        L = (x1 - x0) / n
        prev = anchor_left
        for i in range(n):
            cx = x0 + L * (i + 0.5)
            d = self.plank(cx, y - 0.14, L * 0.98, mass=0.55)
            self.hinge(prev, d, x0 + L * i, y - 0.14)
            prev = d
        self.hinge(prev, anchor_right, x1, y - 0.14)

    def seesaw(self, x, ground_top, length=8.0, height=1.0):
        post = self.block(x - 0.35, x + 0.35, ground_top + height - 0.22, ground_top, style="stone")
        self.statics.append(f"<Transform translation='{vec(x, ground_top + height - 0.1, 0)}' rotation='1 0 0 1.5708'>"
                            f"<Shape><Appearance USE='A_brass'/><Cylinder radius='0.22' height='2.2'/></Shape></Transform>")
        d = self.plank(x, ground_top + height, length, thick=0.3, mass=1.6, role="seesaw")
        self.hinge(post, d, x, ground_top + height)
        return d

    def pendulum(self, ax, ay, length, links=5, r=0.75, mass=5.0, start_angle=0.9):
        anchor = self.block(ax - 0.4, ax + 0.4, ay + 0.4, ay - 0.4, style="brass", nowall=True)
        prev, px, py = anchor, ax, ay
        seg = length / links
        for i in range(links):
            ex, ey = ax + math.sin(start_angle) * seg * (i + 1), ay - math.cos(start_angle) * seg * (i + 1)
            cx, cy = (px + ex) / 2, (py + ey) / 2
            d = self.uid("link")
            self.body(d, cx, cy, "box", (0.16, seg * 0.9), fixed=False, mass=0.25, a=start_angle, role="link", ghost=True)
            self.dyn.append(f"<Transform DEF='V_{d}' translation='{vec(cx, cy, 0)}' rotation='0 0 1 {f(start_angle)}'>"
                            f"<Shape><Appearance USE='A_iron'/><Box size='{vec(0.14, seg * 0.95, 0.14)}'/></Shape></Transform>")
            self.hinge(prev, d, px, py)
            prev, px, py = d, ex, ey
        bx, by = ax + math.sin(start_angle) * (length + r), ay - math.cos(start_angle) * (length + r)
        b = self.uid("wrecker")
        self.body(b, bx, by, "sphere", r, fixed=False, mass=mass, role="wrecker", friction=0.4, angDamp=0.0)
        self.dyn.append(f"<Transform DEF='V_{b}' translation='{vec(bx, by, 0)}'><Transform scale='{vec(r, r, r)}'><Group USE='G_wrecker'/></Transform></Transform>")
        self.hinge(prev, b, px, py)

    def mover(self, pts, period, w=3.0, h=0.6, phase=0.0, style="brass"):
        """A kinematic platform following a closed PositionInterpolator path (keys spaced by length)."""
        d = self.uid("mover")
        path = pts + [pts[0]]
        seglen = [math.dist(path[i], path[i + 1]) for i in range(len(path) - 1)]
        tot = sum(seglen)
        keys, acc = [0.0], 0.0
        for s in seglen:
            acc += s
            keys.append(acc / tot)
        pi = f"P_{d}"
        self.interps.append(f"<PositionInterpolator DEF='{pi}' key='{vec(*keys)}' keyValue='{' '.join(vec(p[0], p[1], 0) for p in path)}'/>")
        x, y = pts[0]
        t = (phase % 1.0)
        acc = 0
        for i, s in enumerate(seglen):  # initial position at the phase
            if acc + s >= t * tot:
                u = (t * tot - acc) / s if s else 0
                x, y = path[i][0] + u * (path[i + 1][0] - path[i][0]), path[i][1] + u * (path[i + 1][1] - path[i][1])
                break
            acc += s
        self.body(d, x, y, "box", (w, h), fixed=False, mass=10, role="mover", kinematic=True, path=pi, period=period, phase=phase, friction=0.9)
        self.dyn.append(f"<Transform DEF='V_{d}' translation='{vec(x, y, 0)}'>"
                        f"<Shape><Appearance USE='A_iron'/><Box size='{vec(w, h, 2.2)}'/></Shape>"
                        f"<Transform translation='{vec(0, h / 2 - 0.05, 0)}'><Shape><Appearance USE='A_brass'/><Box size='{vec(w + 0.12, 0.14, 2.32)}'/></Shape></Transform>"
                        f"<Transform translation='{vec(0, 0, 1.14)}'><Shape><Appearance USE='A_glow'/><Box size='{vec(w * 0.8, 0.08, 0.04)}'/></Shape></Transform>"
                        f"<Transform translation='{vec(0, -h / 2 - 0.25, 0)}' scale='0.5 0.5 0.5'><Transform USE='GEAR_SPIN'/></Transform>"
                        f"</Transform>")
        self.grow(min(p[0] for p in pts) - w / 2, max(p[0] for p in pts) + w / 2, min(p[1] for p in pts), max(p[1] for p in pts))
        return d

    def spinner(self, x, y, length, omega, thick=0.5):
        d = self.uid("spinner")
        self.body(d, x, y, "box", (length, thick), fixed=False, mass=10, role="spinner", kinematic=True, w=omega, friction=0.9)
        self.dyn.append(f"<Transform DEF='V_{d}' translation='{vec(x, y, 0)}'>"
                        f"<Shape><Appearance USE='A_iron'/><Box size='{vec(length, thick, 1.8)}'/></Shape>"
                        f"<Transform translation='{vec(0, thick / 2, 0)}'><Shape><Appearance USE='A_brass'/><Box size='{vec(length + 0.1, 0.1, 1.9)}'/></Shape></Transform>"
                        f"<Transform translation='0 0 0.95'><Shape><Appearance USE='A_glow'/><Box size='{vec(length * 0.9, 0.06, 0.03)}'/></Shape></Transform>"
                        f"</Transform>")
        self.statics.append(f"<Transform translation='{vec(x, y, -1.2)}' rotation='1 0 0 1.5708'><Shape><Appearance USE='A_brass'/><Cylinder radius='0.35' height='0.6'/></Shape></Transform>")
        return d

    def crumble(self, x0, x1, top, thick=0.7):
        d = self.uid("crumble")
        w, cx, cy = x1 - x0, (x0 + x1) / 2, top - thick / 2
        self.body(d, cx, cy, "box", (w, thick), fixed=True, mass=2.5, role="crumble", friction=0.8)
        cracks = "".join(f"<Transform translation='{vec(-w / 2 + w * (i + 0.5) / 3, 0, DEPTH * 0.31 + 0.02)}' rotation='0 0 1 {f(0.5 - i * 0.45)}'>"
                         f"<Shape><Appearance USE='A_crack'/><Box size='{vec(0.06, thick * 0.8, 0.02)}'/></Shape></Transform>" for i in range(3))
        self.dyn.append(f"<Transform DEF='V_{d}' translation='{vec(cx, cy, 0)}'>"
                        f"<Shape><Appearance USE='A_sand'/><Box size='{vec(w, thick, DEPTH * 0.62)}'/></Shape>{cracks}</Transform>")
        self.grow(x0, x1, top - thick, top)
        return d

    def cracked(self, x0, x1, top, bottom):
        d = self.uid("cracked")
        w, h, cx, cy = x1 - x0, top - bottom, (x0 + x1) / 2, (top + bottom) / 2
        self.body(d, cx, cy, "box", (w, h), fixed=True, role="cracked", friction=0.7)
        cracks = "".join(f"<Transform translation='{vec(-w / 2 + w * (i + 0.5) / 4, 0, DEPTH / 2 + 0.02)}' rotation='0 0 1 {f(0.7 - i * 0.5)}'>"
                         f"<Shape><Appearance USE='A_crack'/><Box size='{vec(0.07, h * 0.9, 0.02)}'/></Shape></Transform>" for i in range(4))
        self.dyn.append(f"<Transform DEF='V_{d}' translation='{vec(cx, cy, 0)}'>"
                        f"<Shape><Appearance USE='A_stone'/><Box size='{vec(w, h, DEPTH)}'/></Shape>{cracks}"
                        f"<Transform translation='{vec(0, h / 2 + 0.02, DEPTH / 2 - 0.3)}'><Shape><Appearance USE='A_crack'/><Box size='{vec(w * 0.7, 0.03, 0.4)}'/></Shape></Transform>"
                        f"</Transform>")
        self.grow(x0, x1, bottom, top)
        return d

    # --- entities --------------------------------------------------------------------------
    def ent(self, kind, x, y, visual, prefix=None, **meta):
        d = self.uid("E_" + (prefix or kind))
        self.ents.append(f"<Transform DEF='{d}' translation='{vec(x, y, 0)}'>{metaset('nib:entity', kind=kind, **meta)}{visual}</Transform>")
        return d

    def cog(self, x, y):
        self.counts["cogs"] += 1
        return self.ent("cog", x, y, "<Transform USE='COG_SPIN'/>")

    def cogs_line(self, x0, y0, x1, y1, n):
        for i in range(n):
            t = i / (n - 1) if n > 1 else 0.5
            self.cog(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

    def cogs_arc(self, x0, x1, y, h, n):
        for i in range(n):
            t = i / (n - 1)
            self.cog(x0 + (x1 - x0) * t, y + 4 * h * t * (1 - t))

    def star(self, x, y):
        self.counts["stars"] += 1
        return self.ent("star", x, y, "<Transform USE='STAR_SPIN'/>")

    def spring(self, x, top, v=None, w=1.4):
        """A spring standing on a surface whose top is `top`; the pad's top is top + 0.45."""
        base = None  # the pad is a trigger, not a collider: walking onto a spring launches you
        pad = top + 0.45
        vis = (f"<Transform translation='0 -0.25 0'><Shape><Appearance USE='A_iron'/><Cylinder radius='{f(w / 2)}' height='0.12'/></Shape></Transform>"
               f"<Transform DEF='{{}}_COIL' translation='0 -0.22 0'><Shape><Appearance USE='A_brass'/>{helix_extrusion(w * 0.32, 0.06, 3, 0.42)}</Shape></Transform>"
               f"<Transform DEF='{{}}_PAD' translation='0 0.0 0'><Shape><Appearance USE='A_red'/><Cylinder radius='{f(w / 2)}' height='0.16'/></Shape>"
               f"<Transform translation='0 0.09 0'><Shape><Appearance USE='A_white'/><Cylinder radius='{f(w * 0.3)}' height='0.03'/></Shape></Transform></Transform>")
        d = self.uid("E_spring")
        self.n["E_spring"] -= 1
        vis = vis.replace("{}", d)
        return self.ent("spring", x, pad, vis, prefix="spring", v=v, w=w), base

    def spikes(self, x0, x1, base_y):
        w = x1 - x0
        n = max(1, int(round(w / 0.5)))
        cones = "".join(f"<Transform translation='{vec(-w / 2 + w * (i + 0.5) / n, 0.0, z)}'><Shape USE='S_spike'/></Transform>"
                        for i in range(n) for z in (-0.6, 0.0, 0.6))
        return self.ent("spikes", (x0 + x1) / 2, base_y + 0.3, f"<Transform translation='0 0 0'>{cones}</Transform>", w=w, h=0.6)

    def ring(self, x, y):
        vis = (f"<Shape><Appearance USE='A_glow'/>{torus_extrusion(0.42, 0.08)}</Shape>"
               f"<Transform translation='0 0.62 0'><Shape><Appearance USE='A_brass'/><Box size='0.12 0.4 0.12'/></Shape></Transform>"
               f"<Transform translation='0 0.86 0'><Shape><Appearance USE='A_iron'/><Sphere radius='0.14'/></Shape></Transform>")
        return self.ent("ring", x, y, vis)

    def checkpoint(self, x, top):
        self.cp += 1
        d = f"E_checkpoint_{self.cp}"
        vis = (f"<Transform translation='0 1.1 -0.6'><Shape><Appearance USE='A_wood2'/><Cylinder radius='0.09' height='2.2'/></Shape></Transform>"
               f"<Transform translation='0.32 2.1 -0.6'><Shape><Appearance USE='A_wood2'/><Box size='0.7 0.08 0.08'/></Shape></Transform>"
               f"<Transform translation='0.62 1.78 -0.6'><Shape><Appearance><Material DEF='M_{d}' diffuseColor='0.45 0.45 0.5' emissiveColor='0.05 0.05 0.08' specularColor='0.4 0.4 0.4' shininess='0.4'/></Appearance><Sphere radius='0.26'/></Shape>"
               f"<Transform translation='0 0.3 0'><Shape><Appearance USE='A_iron'/><Cone bottomRadius='0.22' height='0.18'/></Shape></Transform></Transform>")
        self.ents.append(f"<Transform DEF='{d}' translation='{vec(x, top, 0)}'>{metaset('nib:entity', kind='checkpoint', idx=self.cp)}{vis}</Transform>")
        return d

    def goal(self, x, top):
        vis = ("<Transform translation='-1.5 1.8 -0.4'><Shape><Appearance USE='A_brass'/><Cylinder radius='0.22' height='3.6'/></Shape></Transform>"
               "<Transform translation='1.5 1.8 -0.4'><Shape><Appearance USE='A_brass'/><Cylinder radius='0.22' height='3.6'/></Shape></Transform>"
               "<Transform translation='0 3.7 -0.4' rotation='0 0 1 1.5708'><Shape><Appearance USE='A_brass'/><Cylinder radius='0.25' height='3.6'/></Shape></Transform>"
               "<Transform translation='0 2.1 -0.4' scale='1.6 1.6 1.6'><Transform USE='GEAR_SPIN'/></Transform>"
               "<Transform translation='0 2.1 -0.5'><Shape><Appearance USE='A_halo'/><Sphere radius='1.7'/></Shape></Transform>"
               "<Transform translation='-1.5 3.85 -0.4'><Shape><Appearance USE='A_glow'/><Sphere radius='0.3'/></Shape></Transform>"
               "<Transform translation='1.5 3.85 -0.4'><Shape><Appearance USE='A_glow'/><Sphere radius='0.3'/></Shape></Transform>")
        return self.ent("goal", x, top, vis)

    def hint(self, x, top, text):
        vis = ("<Transform translation='0 0.6 -0.9'><Shape><Appearance USE='A_wood2'/><Cylinder radius='0.07' height='1.2'/></Shape></Transform>"
               "<Transform translation='0 1.25 -0.9' rotation='0 1 0 0.25'><Shape><Appearance USE='A_wood'/><Box size='1.0 0.6 0.08'/></Shape>"
               "<Transform translation='0 0 0.05'><Shape><Appearance USE='A_sign'/><Box size='0.6 0.08 0.02'/></Shape></Transform>"
               "<Transform translation='0 -0.14 0.05'><Shape><Appearance USE='A_sign'/><Box size='0.44 0.08 0.02'/></Shape></Transform></Transform>")
        return self.ent("hint", x, top, vis, text=text)

    def wind(self, x, bottom, w, h, accel=70, vmax=10):
        vis = (f"<Transform translation='0 0.15 0'><Shape><Appearance USE='A_iron'/><Cylinder radius='{f(w / 2)}' height='0.3'/></Shape></Transform>"
               f"<Transform translation='0 0.34 0' scale='{vec(w / 2.4, 1, w / 2.4)}'><Transform USE='FAN_SPIN'/></Transform>"
               f"<Transform translation='{vec(0, h / 2, 0)}'><Shape><Appearance USE='A_windcol'/><Cylinder radius='{f(w / 2 * 0.9)}' height='{f(h)}' bottom='false' top='false'/></Shape></Transform>")
        return self.ent("wind", x, bottom, vis, w=w, h=h, accel=accel, vmax=vmax)

    # --- picture-only scenery ----------------------------------------------------------------
    def scenery(self):
        T, rng = self.T, self.rng
        x0, x1 = self.extent[0] - 40, self.extent[1] + 40
        y0 = self.extent[2]
        n_far = int((x1 - x0) / 24) + 2
        for i in range(n_far):  # far hills / mesas / towers
            x = x0 + (x1 - x0) * i / (n_far - 1) + rng.r(-6, 6)
            sx, sy = rng.r(18, 30), rng.r(10, 22)
            if self.theme_name == "gorge":
                self.decor.append(f"<Transform translation='{vec(x, -6 + sy / 2, -70)}'><Shape><Appearance USE='A_hill_far'/><Cylinder radius='{f(sx / 2)}' height='{f(sy)}'/></Shape>"
                                  f"<Transform translation='{vec(0, sy / 2, 0)}'><Shape><Appearance USE='A_top'/><Cylinder radius='{f(sx / 2 + 0.6)}' height='0.8'/></Shape></Transform></Transform>")
            elif self.theme_name == "spire":
                hh = rng.r(20, 60)
                self.decor.append(f"<Transform translation='{vec(x, y0 - 10 + hh / 2, -75)}'><Shape><Appearance USE='A_hill_far'/><Box size='{vec(sx * 0.4, hh, 4)}'/></Shape>"
                                  f"<Transform translation='{vec(0, hh / 2 + 1.5, 0)}'><Shape><Appearance USE='A_glow'/><Sphere radius='0.6'/></Shape></Transform></Transform>")
            else:
                self.decor.append(f"<Transform translation='{vec(x, -8, -70)}' scale='{vec(sx, sy, 10)}'><Shape><Appearance USE='A_hill_far'/><Sphere radius='1'/></Shape></Transform>")
        n_mid = int((x1 - x0) / 16) + 2
        if self.theme_name == "gorge":  # a river far below, so every gap reads as a drop into the canyon
            self.decor.append(f"<Transform translation='{vec((x0 + x1) / 2, -21, -30)}'><Shape><Appearance USE='A_river'/><Box size='{vec(x1 - x0, 0.2, 26)}'/></Shape></Transform>")
        for i in range(n_mid):
            x = x0 + (x1 - x0) * i / (n_mid - 1) + rng.r(-5, 5)
            sx, sy = rng.r(10, 18), rng.r(6, 12)
            app = "A_hill_mid" if i % 2 else "A_hill_near"
            if self.theme_name == "gorge":  # mesas whose tops sit well below the play line
                top = rng.r(-16, -11)
                self.decor.append(f"<Transform translation='{vec(x, top - 8, -50)}'><Shape><Appearance USE='A_hill_far'/><Cylinder radius='{f(sx / 2)}' height='16'/></Shape>"
                                  f"<Transform translation='0 8 0'><Shape><Appearance USE='{app}'/><Cylinder radius='{f(sx / 2 + 0.4)}' height='0.6'/></Shape></Transform></Transform>")
                continue
            if self.theme_name == "spire":
                hh = rng.r(12, 34)
                self.decor.append(f"<Transform translation='{vec(x, y0 - 6 + hh / 2, -38)}'><Shape><Appearance USE='{app}'/><Box size='{vec(sx * 0.35, hh, 3)}'/></Shape>"
                                  + "".join(f"<Transform translation='{vec(rng.r(-1, 1), rng.r(-hh / 2 + 2, hh / 2 - 1), 1.55)}'><Shape><Appearance USE='A_window'/><Box size='0.5 0.7 0.05'/></Shape></Transform>" for _ in range(5))
                                  + "</Transform>")
            else:
                self.decor.append(f"<Transform translation='{vec(x, -9, -36)}' scale='{vec(sx, sy, 6)}'><Shape><Appearance USE='{app}'/><Sphere radius='1'/></Shape></Transform>")
        for i in range(int((x1 - x0) / 9)):  # trees / crystals between play and hills
            x = x0 + rng.r(0, x1 - x0)
            z = rng.r(-16, -7)
            s = rng.r(0.8, 1.6)
            ty = rng.r(-5, -2) - (7 if self.theme_name == "gorge" else 0)
            self.decor.append(f"<Transform translation='{vec(x, ty, z)}' scale='{vec(s, s, s)}'><Group USE='G_tree'/></Transform>")
        for i in range(int((x1 - x0) / 34) + 1):  # big turning gears far back, alternately mirrored to turn the other way
            x = x0 + 24 + i * 34 + rng.r(-5, 5)
            s = rng.r(2.6, 4.4)
            mirror = "-1" if i % 2 else "1"
            self.decor.append(f"<Transform translation='{vec(x, rng.r(8, 20), -52)}' scale='{mirror} 1 1'><Transform scale='{vec(s, s, s)}'><Transform USE='GEAR_SLOW'/></Transform></Transform>")
        clouds = []
        for i in range(int((x1 - x0) / 14) + 1):
            x, y, z = x0 + rng.r(0, x1 - x0), rng.r(10, 22), rng.r(-50, -30)
            puff = "".join(f"<Transform translation='{vec(rng.r(-2.5, 2.5), rng.r(-0.4, 0.6), rng.r(-0.5, 0.5))}' scale='{vec(rng.r(1.6, 2.6), rng.r(1.0, 1.6), 1.2)}'><Shape USE='S_cloud'/></Transform>" for _ in range(4))
            clouds.append(f"<Transform translation='{vec(x, y, z)}'>{puff}</Transform>")
        self.decor.append(f"<Transform DEF='CLOUDS'>{''.join(clouds)}</Transform>")
        self.interps.append("<TimeSensor DEF='T_clouds' cycleInterval='90' loop='true'/>"
                            "<PositionInterpolator DEF='PI_clouds' key='0 0.5 1' keyValue='-6 0 0 6 0 0 -6 0 0'/>")
        self.routes += ["<ROUTE fromNode='T_clouds' fromField='fraction_changed' toNode='PI_clouds' toField='set_fraction'/>",
                        "<ROUTE fromNode='PI_clouds' fromField='value_changed' toNode='CLOUDS' toField='set_translation'/>"]
        if T["stars"]:
            pts = " ".join(vec(rng.r(x0, x1), rng.r(-5, 60), rng.r(-120, -90)) for _ in range(400))
            self.decor.append(f"<Shape><Appearance><Material emissiveColor='1 1 1'/></Appearance><PointSet><Coordinate point='{pts}'/></PointSet></Shape>")
        sun_y = 26 if self.theme_name != "gorge" else 9
        self.decor.append(f"<Transform translation='{vec((x0 + x1) / 2, sun_y, -110)}'><Shape><Appearance USE='A_sun'/><Sphere radius='{f(7 if self.theme_name != 'spire' else 5)}'/></Shape>"
                          f"<Shape><Appearance USE='A_halo'/><Sphere radius='{f(11 if self.theme_name != 'spire' else 8)}'/></Shape></Transform>")

    # --- shared library ----------------------------------------------------------------------
    def library(self) -> str:
        T = self.T
        apps = {
            "A_top": material(T["top"], spec=(0.08, 0.1, 0.06)),
            "A_top2": material(T["top2"]),
            "A_body": material(T["body"], spec=(0.06, 0.05, 0.04)),
            "A_body2": material(T["body2"]),
            "A_stone": material((0.62, 0.62, 0.70) if self.theme_name != "spire" else (0.34, 0.34, 0.46), spec=(0.15, 0.15, 0.18), shin=0.3),
            "A_moss": material((0.46, 0.66, 0.42) if self.theme_name == "meadow" else T["top2"]),
            "A_sand": material((0.92, 0.78, 0.52)),
            "A_crack": material((0.16, 0.12, 0.12)),
            "A_wood": material((0.84, 0.58, 0.32), spec=(0.1, 0.08, 0.05)),
            "A_wood2": material((0.52, 0.32, 0.18)),
            "A_brass": material((0.96, 0.70, 0.28), emissive=(0.10, 0.06, 0.0), spec=(1.0, 0.86, 0.55), shin=0.55),
            "A_iron": material((0.30, 0.32, 0.38), spec=(0.6, 0.62, 0.7), shin=0.5),
            "A_red": material((0.94, 0.20, 0.22), emissive=(0.12, 0.0, 0.0), spec=(0.6, 0.5, 0.5), shin=0.6),
            "A_white": material((0.98, 0.98, 0.96), spec=(0.5, 0.5, 0.5), shin=0.6),
            "A_black": material((0.05, 0.05, 0.07), spec=(0.6, 0.6, 0.7), shin=0.8),
            "A_pink": material((1.0, 0.55, 0.62), emissive=(0.2, 0.05, 0.08)),
            "A_glow": material((0.25, 0.95, 1.0), emissive=(0.20, 0.80, 0.95)),
            "A_glow_warm": material((1.0, 0.85, 0.45), emissive=(1.0, 0.70, 0.25)),
            "A_gold": material((1.0, 0.78, 0.22), emissive=(0.38, 0.24, 0.02), spec=(1, 0.95, 0.6), shin=0.7),
            "A_star": material((1.0, 0.86, 0.30), emissive=(0.85, 0.55, 0.05), spec=(1, 1, 0.8), shin=0.8),
            "A_halo": material((1.0, 0.92, 0.6), emissive=(1.0, 0.85, 0.5), transp=0.86),
            "A_sun": material((1, 1, 0.9), emissive=(1.0, 0.95, 0.8) if self.theme_name != "spire" else (0.92, 0.92, 1.0)),
            "A_hill_far": material(T["hill_far"], spec=(0, 0, 0)),
            "A_hill_mid": material(T["hill_mid"], spec=(0, 0, 0)),
            "A_hill_near": material(T["hill_near"], spec=(0, 0, 0)),
            "A_cloud": material(T["cloud"], emissive=tuple(c * 0.55 for c in T["cloud"]), spec=(0, 0, 0)),
            "A_leaf": material(T["leaf"]),
            "A_leaf2": material(T["leaf2"]),
            "A_trunk": material(T["trunk"]),
            "A_accent": material(T["accent"], emissive=tuple(c * 0.25 for c in T["accent"])),
            "A_window": material((1.0, 0.8, 0.4), emissive=(0.9, 0.65, 0.3)),
            "A_river": material(T["accent"], emissive=tuple(c * 0.55 for c in T["accent"])),
            "A_shadow": material((0, 0, 0), spec=(0, 0, 0), transp=0.55),
            "A_dust": material((1, 0.98, 0.94), emissive=(0.5, 0.48, 0.45), transp=0.25),
            "A_spark": material((1.0, 0.85, 0.3), emissive=(1.0, 0.75, 0.2)),
            "A_rope": material((0.85, 0.75, 0.55), emissive=(0.15, 0.12, 0.05)),
            "A_sign": material((0.25, 0.16, 0.1)),
            "A_spike": material((0.85, 0.87, 0.92), spec=(1, 1, 1), shin=0.9),
            "A_windcol": material((0.8, 0.95, 1.0), emissive=(0.4, 0.6, 0.7), transp=0.82),
            "A_cave": material(tuple(c * 0.38 for c in T["body2"]), spec=(0, 0, 0)),
            "A_hilite": material((0.4, 1.0, 1.0), emissive=(0.3, 0.9, 1.0), transp=0.55),
        }
        for i, c in enumerate([(1, 0.3, 0.35), (0.3, 0.8, 1), (1, 0.85, 0.2), (0.5, 1, 0.45), (0.85, 0.45, 1)]):
            apps[f"A_conf_{i}"] = material(c, emissive=tuple(x * 0.5 for x in c))
        out = ["<Switch DEF='LIB' whichChoice='-1'>"]
        for k in sorted(apps):
            out.append(f"<Shape><Appearance DEF='{k}'>{apps[k]}</Appearance><Box size='0.01 0.01 0.01'/></Shape>")
        out.append("<Shape DEF='S_pebble'><Appearance USE='A_stone'/><Sphere radius='1'/></Shape>")
        out.append("<Shape DEF='S_tuft'><Appearance USE='A_top2'/><Cone bottomRadius='0.09' height='0.4'/></Shape>")
        out.append("<Shape DEF='S_flower_a'><Appearance USE='A_pink'/><Sphere radius='0.11'/></Shape>")
        out.append("<Shape DEF='S_flower_b'><Appearance USE='A_glow_warm'/><Sphere radius='0.09'/></Shape>")
        out.append("<Shape DEF='S_cloud'><Appearance USE='A_cloud'/><Sphere radius='1'/></Shape>")
        out.append("<Shape DEF='S_spike'><Appearance USE='A_spike'/><Cone bottomRadius='0.22' height='0.62'/></Shape>")
        out.append("<Shape DEF='S_dust'><Appearance USE='A_dust'/><Sphere radius='0.2'/></Shape>")
        out.append("<Shape DEF='S_spark'><Appearance USE='A_spark'/><Box size='0.14 0.14 0.14'/></Shape>")
        for i in range(5):
            out.append(f"<Shape DEF='S_conf_{i}'><Appearance USE='A_conf_{i}'/><Box size='0.22 0.12 0.02'/></Shape>")
        # spinning pickups: one DEF'd Transform, used by every cog, turned by one interpolator
        out.append("<Transform DEF='COG_SPIN'>" + gear_shape_children(0.3, 0.12, 8, "A_gold", "A_brass") + "</Transform>")
        out.append("<Transform DEF='STAR_SPIN'>" + gear_shape_children(0.5, 0.16, 10, "A_star", "A_white")
                   + "<Shape><Appearance USE='A_halo'/><Sphere radius='0.85'/></Shape></Transform>")
        out.append("<Transform DEF='GEAR_SPIN'>" + gear_shape_children(0.6, 0.2, 10, "A_brass", "A_iron") + "</Transform>")
        out.append("<Transform DEF='GEAR_SLOW'>" + gear_shape_children(1.0, 0.3, 14, "A_brass", "A_iron") + "</Transform>")
        out.append("<Transform DEF='FAN_SPIN'>" + "".join(f"<Transform rotation='0 1 0 {f(i * 2.0944)}'><Transform translation='0.55 0 0' rotation='1 0 0 0.5'><Shape><Appearance USE='A_brass'/><Box size='1.0 0.05 0.36'/></Shape></Transform></Transform>" for i in range(3)) + "</Transform>")
        out.append("<Group DEF='G_crate'>"
                   "<Shape><Appearance USE='A_wood'/><Box size='1.2 1.2 1.2'/></Shape>"
                   + "".join(f"<Transform translation='{vec(*t)}'><Shape><Appearance USE='A_wood2'/><Box size='{vec(*s)}'/></Shape></Transform>"
                             for t, s in [((0, 0.54, 0.61), (1.22, 0.14, 0.04)), ((0, -0.54, 0.61), (1.22, 0.14, 0.04)),
                                          ((0.54, 0, 0.61), (0.14, 1.22, 0.04)), ((-0.54, 0, 0.61), (0.14, 1.22, 0.04))])
                   + "<Transform translation='0 0 0.62' rotation='0 0 1 0.7854'><Shape><Appearance USE='A_wood2'/><Box size='1.4 0.13 0.03'/></Shape></Transform>"
                   + "".join(f"<Transform translation='{vec(x, y, 0.64)}'><Shape><Appearance USE='A_brass'/><Sphere radius='0.06'/></Shape></Transform>" for x in (-0.48, 0.48) for y in (-0.48, 0.48))
                   + "</Group>")
        out.append("<Group DEF='G_ball'><Shape><Appearance USE='A_stone'/><Sphere radius='1'/></Shape>"
                   "<Transform rotation='1 0 0 1.5708'><Shape><Appearance USE='A_brass'/><Cylinder radius='1.02' height='0.18'/></Shape></Transform></Group>")
        out.append("<Group DEF='G_wrecker'><Shape><Appearance USE='A_iron'/><Sphere radius='1'/></Shape>"
                   + "".join(f"<Transform rotation='0 0 1 {f(i * 0.7854)}'><Transform translation='0 1.0 0'><Shape><Appearance USE='A_spike'/><Cone bottomRadius='0.16' height='0.4'/></Shape></Transform></Transform>" for i in range(8))
                   + "<Transform rotation='1 0 0 1.5708'><Shape><Appearance USE='A_red'/><Cylinder radius='1.01' height='0.22'/></Shape></Transform></Group>")
        out.append("<Group DEF='G_tree'>"
                   "<Transform translation='0 1.4 0'><Shape><Appearance USE='A_trunk'/><Cylinder radius='0.22' height='2.8'/></Shape></Transform>"
                   "<Transform translation='0 3.4 0' scale='1.5 1.3 1.5'><Shape><Appearance USE='A_leaf'/><Sphere radius='1'/></Shape></Transform>"
                   "<Transform translation='0.8 2.9 0.3' scale='0.9 0.8 0.9'><Shape><Appearance USE='A_leaf2'/><Sphere radius='1'/></Shape></Transform>"
                   "<Transform translation='-0.7 3.0 -0.2' scale='0.8 0.75 0.8'><Shape><Appearance USE='A_leaf2'/><Sphere radius='1'/></Shape></Transform>"
                   "</Group>")
        out.append("</Switch>")
        return "".join(out)

    def hero_and_fx(self) -> str:
        sx, sy = self.start
        o = [f"<Transform DEF='HERO' translation='{vec(sx, sy, 0)}'><Transform DEF='HERO_SQUASH' translation='0 -0.47 0'>"
             "<Transform translation='0 0.47 0'><Transform DEF='HERO_YAW' rotation='0 1 0 0.75'><Transform DEF='HERO_TILT'>"
             "<Transform scale='1 0.92 1'><Shape><Appearance USE='A_brass'/><Sphere radius='0.5'/></Shape></Transform>"
             "<Transform translation='0 -0.08 0'><Shape><Appearance USE='A_iron'/><Cylinder radius='0.505' height='0.12'/></Shape></Transform>"
             "<Transform translation='0 0.1 0.33' scale='1 1 0.62'><Shape><Appearance USE='A_white'/><Sphere radius='0.26'/></Shape></Transform>"
             "<Transform DEF='HERO_PUPIL' translation='0 0.1 0.47'><Transform scale='1 1.15 0.6'><Shape><Appearance USE='A_black'/><Sphere radius='0.12'/></Shape></Transform>"
             "<Transform translation='0.04 0.05 0.07'><Shape><Appearance USE='A_white'/><Sphere radius='0.035'/></Shape></Transform></Transform>"
             "<Transform DEF='HERO_LID' translation='0 0.3 0.36' scale='1 0.15 0.62'><Shape><Appearance USE='A_brass'/><Sphere radius='0.27'/></Shape></Transform>"
             "<Transform translation='0.25 -0.07 0.37'><Shape><Appearance USE='A_pink'/><Sphere radius='0.065'/></Shape></Transform>"
             "<Transform translation='-0.25 -0.07 0.37'><Shape><Appearance USE='A_pink'/><Sphere radius='0.065'/></Shape></Transform>"
             "<Transform translation='0 0.58 0'><Shape><Appearance USE='A_iron'/><Cylinder radius='0.03' height='0.3'/></Shape></Transform>"
             "<Transform DEF='HERO_BULB' translation='0 0.76 0'><Shape><Appearance USE='A_glow'/><Sphere radius='0.09'/></Shape></Transform>"
             "<Transform translation='0 0.05 -0.5' rotation='1 0 0 1.5708'><Shape><Appearance USE='A_iron'/><Cylinder radius='0.04' height='0.2'/></Shape></Transform>"
             "<Transform DEF='HERO_KEY' translation='0 0.05 -0.64'>"
             "<Transform translation='0.13 0 0' scale='1 0.55 0.25'><Shape><Appearance USE='A_brass'/><Sphere radius='0.15'/></Shape></Transform>"
             "<Transform translation='-0.13 0 0' scale='1 0.55 0.25'><Shape><Appearance USE='A_brass'/><Sphere radius='0.15'/></Shape></Transform></Transform>"
             "<Transform DEF='HERO_FOOT_L' translation='-0.2 -0.44 0.05'><Transform scale='1 0.55 1.4'><Shape><Appearance USE='A_iron'/><Sphere radius='0.14'/></Shape></Transform></Transform>"
             "<Transform DEF='HERO_FOOT_R' translation='0.2 -0.44 0.05'><Transform scale='1 0.55 1.4'><Shape><Appearance USE='A_iron'/><Sphere radius='0.14'/></Shape></Transform></Transform>"
             "</Transform></Transform></Transform></Transform></Transform>"]
        for i in range(6):  # scarf: a short verlet chain the page simulates (picture only)
            s = 1 - i * 0.1
            o.append(f"<Transform DEF='SCARF_{i}' translation='{vec(sx - 0.2 * i, sy, -0.1)}'><Transform scale='{vec(s, s, s)}'>"
                     f"<Shape><Appearance USE='{'A_red' if i % 2 == 0 else 'A_accent'}'/><Box size='0.26 0.15 0.2'/></Shape></Transform></Transform>")
        o.append("<Transform DEF='ROPE' scale='0 0 0'><Shape><Appearance USE='A_rope'/><Cylinder radius='0.045' height='1'/></Shape></Transform>")
        o.append("<Transform DEF='RING_HILITE' scale='0 0 0'><Shape><Appearance USE='A_hilite'/><Sphere radius='0.75'/></Shape></Transform>")
        o.append(f"<Transform DEF='SHADOW' translation='{vec(sx, sy - 0.47, 0)}'><Shape><Appearance USE='A_shadow'/><Cylinder radius='0.42' height='0.02'/></Shape></Transform>")
        for i in range(18):
            o.append(f"<Transform DEF='DUST_{i}' scale='0 0 0'><Shape USE='S_dust'/></Transform>")
        for i in range(28):
            o.append(f"<Transform DEF='SPARK_{i}' scale='0 0 0'><Shape USE='S_spark'/></Transform>")
        for i in range(40):
            o.append(f"<Transform DEF='CONF_{i}' scale='0 0 0'><Shape USE='S_conf_{i % 5}'/></Transform>")
        for i in range(12):
            o.append(f"<Transform DEF='V_DEBRIS_{i}' scale='0 0 0'><Shape><Appearance USE='A_stone'/><Box size='0.4 0.4 0.9'/></Shape></Transform>")
        return "".join(o)

    def animations(self) -> str:
        return ("<TimeSensor DEF='T_spin' cycleInterval='2.2' loop='true'/>"
                "<OrientationInterpolator DEF='OI_spin' key='0 0.25 0.5 0.75 1' keyValue='0 1 0 0 0 1 0 1.5708 0 1 0 3.1416 0 1 0 4.7124 0 1 0 6.2832'/>"
                "<TimeSensor DEF='T_gear' cycleInterval='6' loop='true'/>"
                "<OrientationInterpolator DEF='OI_gear' key='0 0.25 0.5 0.75 1' keyValue='0 0 1 0 0 0 1 -1.5708 0 0 1 -3.1416 0 0 1 -4.7124 0 0 1 -6.2832'/>"
                "<TimeSensor DEF='T_slow' cycleInterval='40' loop='true'/>"
                "<OrientationInterpolator DEF='OI_slow' key='0 0.25 0.5 0.75 1' keyValue='0 0 1 0 0 0 1 1.5708 0 0 1 3.1416 0 0 1 4.7124 0 0 1 6.2832'/>"
                "<TimeSensor DEF='T_fan' cycleInterval='0.5' loop='true'/>"
                "<ROUTE fromNode='T_spin' fromField='fraction_changed' toNode='OI_spin' toField='set_fraction'/>"
                "<ROUTE fromNode='OI_spin' fromField='value_changed' toNode='COG_SPIN' toField='set_rotation'/>"
                "<ROUTE fromNode='OI_spin' fromField='value_changed' toNode='STAR_SPIN' toField='set_rotation'/>"
                "<ROUTE fromNode='T_gear' fromField='fraction_changed' toNode='OI_gear' toField='set_fraction'/>"
                "<ROUTE fromNode='OI_gear' fromField='value_changed' toNode='GEAR_SPIN' toField='set_rotation'/>"
                "<ROUTE fromNode='T_slow' fromField='fraction_changed' toNode='OI_slow' toField='set_fraction'/>"
                "<ROUTE fromNode='OI_slow' fromField='value_changed' toNode='GEAR_SLOW' toField='set_rotation'/>"
                "<OrientationInterpolator DEF='OI_fan' key='0 0.5 1' keyValue='0 1 0 0 0 1 0 3.1416 0 1 0 6.2832'/>"
                "<ROUTE fromNode='T_fan' fromField='fraction_changed' toNode='OI_fan' toField='set_fraction'/>"
                "<ROUTE fromNode='OI_fan' fromField='value_changed' toNode='FAN_SPIN' toField='set_rotation'/>")

    def x3d(self) -> str:
        T = self.T
        self.scenery()
        sky = " ".join(vec(*c) for c in T["sky"])
        key, fill = T["key"], T["fill"]
        params = metaset("nib:level", key=self.key, title=self.title, subtitle=self.subtitle, theme=self.theme_name,
                         start=self.start, killY=self.kill_y, par=self.par, camMinY=self.kill_y + 9,
                         extent=self.extent, cogs=self.counts["cogs"], stars=self.counts["stars"])
        head = ("<?xml version='1.0' encoding='UTF-8'?>\n"
                "<X3D profile='Immersive' version='4.0' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' "
                "xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.0.xsd'>\n<head>\n"
                "<component name='RigidBodyPhysics' level='2'/>\n"
                f"<meta name='title' content='{esc('NIB ' + self.key + ' ' + self.title)}'/>\n"
                f"<meta name='description' content='{esc('x3d.platformer level: ' + self.title + '. Colliders, joints and roles are standard RigidBodyPhysics nodes with nib metadata; the game engine plays them at 120 Hz.')}'/>\n"
                "<meta name='generator' content='x3d.platformer/build/build_levels.py'/>\n"
                "<meta name='license' content='MIT'/>\n</head>\n<Scene>\n")
        body = [
            f"<WorldInfo title='{esc('NIB ' + self.key + ' ' + self.title)}' info='{mfstr('x3d.platformer: an original physics platformer in X3D 4.0', 'Generated; edit build/build_levels.py, never this file')}'>{params}</WorldInfo>",
            "<NavigationInfo type='\"NONE\"' headlight='false' transitionType='\"TELEPORT\"'/>",
            f"<Viewpoint DEF='CAM' description='Game camera' position='{vec(self.start[0], self.start[1] + 2.2, 21)}' orientation='1 0 0 -0.06' fieldOfView='0.66'/>",
            f"<Background skyAngle='{vec(*T['sky_angle'])}' skyColor='{sky}' groundAngle='1.5708' groundColor='{vec(*T['ground_sky'])} {vec(*T['ground_sky'])}'/>",
            f"<Fog fogType='LINEAR' color='{vec(*T['fog'])}' visibilityRange='{f(T['fog_range'])}'/>",
            f"<DirectionalLight DEF='KEY' color='{vec(*key[0])}' intensity='{f(key[1])}' ambientIntensity='0.35' direction='{vec(*key[2])}' global='true'/>",
            f"<DirectionalLight DEF='FILL' color='{vec(*fill[0])}' intensity='{f(fill[1])}' direction='{vec(*fill[2])}' global='true'/>",
            "<DirectionalLight DEF='RIM' color='1 1 1' intensity='0.25' direction='0 -0.2 1' global='true'/>",
            self.library(),
            group("SCENERY", self.decor), group("LEVEL", self.statics), group("PROPS", self.dyn), group("ENTITIES", self.ents),
            self.hero_and_fx(),
            f"<RigidBodyCollection DEF='PHYSICS' enabled='false' gravity='0 {f(-GRAVITY)} 0' iterations='10' autoDisable='false'>"
            + "".join(self.bodies) + "".join(self.joints) + "</RigidBodyCollection>",
            "".join(self.interps),
            self.animations(),
            "".join(self.routes),
        ]
        return head + "\n".join(body) + "\n</Scene>\n</X3D>\n"


# =============================================================================================
# The levels. Units are metres; Nib is 0.72 m wide and 0.94 m tall, jumps about 3.3 m high
# (jump held) and about 7 m far at full speed (tests/feel.test.mjs measures both).
# =============================================================================================

def feel_lab() -> Level:
    L = Level("0-0", "Feel Lab", "meadow", start=(0, 0.48), kill_y=-12, par=10, seed=7, subtitle="measurement level")
    L.ground(-30, 20, 0)
    L.ground(20, 30, 2.0)               # a ledge to walk off (coyote time)
    L.ground(30, 70, 0)
    L.block(50, 52, 14, 0, style="stone")   # a tall wall (wall jump)
    return L


def tinker_meadow() -> Level:
    L = Level("1-1", "Tinker Meadow", "meadow", start=(0, 0.5), kill_y=-16, par=70, seed=11,
              subtitle="Run, jump, push, bounce, pound, climb")
    # A. run and jump
    L.ground(-12, 24, 0)
    L.hint(3, 0, "Arrows or A/D to run.  SPACE to jump - hold it to jump higher!")
    L.cogs_line(5, 0.9, 9, 0.9, 5)
    L.block(11, 14, 1.4, 0, style="stone")
    L.block(16, 19.5, 2.8, 0, style="stone")
    L.cogs_arc(11.5, 19, 2.6, 1.8, 6)
    L.cogs_arc(24.5, 27.5, 1.2, 2.2, 5)
    # B. gaps
    L.ground(28, 40, 0)
    L.cogs_arc(40.5, 44.5, 1.4, 2.8, 5)
    L.ground(45, 56, 1.0)
    # C. the crate and the wall
    L.hint(47, 1.0, "Too high? PUSH the crate to the wall and climb it.")
    L.crate(50.5, 1.0)
    L.block(56, 62, 4.8, 1.0, style="stone")
    L.cogs_line(57, 5.7, 61, 5.7, 4)
    # D. springs (optional high ledge with the first star)
    L.ground(62, 82, 0)
    L.spring(68, 0)
    L.hint(65, 0, "Springs fling you up. Steer while you fly!")
    L.ledge(71, 77, 5.6)
    L.cogs_line(72, 6.4, 76, 6.4, 5)
    L.star(76.2, 7.3)
    L.cogs_arc(66.5, 70.5, 1.2, 4.5, 5)
    L.checkpoint(79.5, 0)
    # E. a hanging bridge over the pit
    left = L.ground(82, 82.01, 0, -0.5)  # tiny anchor post bodies at each end (hinges need bodies)
    right = L.ground(97.99, 98, 0, -0.5)
    L.bridge(82, 98, 0, left, right, 11)
    L.cogs_arc(84, 96, 1.4, 1.6, 9)
    # F. ground pound through the cracked stone into the cave
    L.ground(98, 112, 0)
    L.hint(107, 0, "Cracked stone? Jump, then press DOWN to GROUND POUND!")
    L.cracked(112, 114.5, 0, -1.0)
    L.block(114.5, 121, 0, -1.0, style="grass")
    L.block(121, 126, 8.5, -1.0, style="stone")
    L.ground(112, 130, -6.0, -16, style="stone")  # cave floor
    L.backwall(112, 130, -6.0, -1.0)
    L.cogs_line(114, -5.1, 124, -5.1, 9)
    L.star(116.5, -3.2)
    L.spring(127.6, -6.0, v=25)
    L.hint(124.5, -6.0, "Bounce out!")
    # G. the seesaw toy
    L.ground(130, 174, 0)
    L.checkpoint(133, 0)
    L.seesaw(142, 0, length=8.0, height=1.0)
    L.crate(145.2, 1.6, size=1.0, mass=1.2)
    L.hint(137, 0, "Pound the high end of the seesaw and watch the crate fly.")
    L.cogs_line(139, 3.3, 145, 3.3, 4)
    # H. the wall-jump chimney to the goal
    L.hint(162, 0, "Jump at a wall, then jump again off it. Climb!")
    L.block(166.6, 168.2, 11.5, 1.9, style="stone")
    L.ground(172, 196, 12.5)
    L.cogs_line(170.1, 2.5, 170.1, 10.5, 5)
    L.star(167.4, 12.6)
    L.goal(186, 12.5)
    L.cogs_line(176, 13.4, 182, 13.4, 4)
    return L


def pendulum_gorge() -> Level:
    L = Level("2-1", "Pendulum Gorge", "gorge", start=(0, 0.5), kill_y=-14, par=55, seed=23,
              subtitle="Hook, swing, ride and dodge across the sunset canyon")
    # A. learn the hook over a short chasm
    L.ground(-12, 16, 0)
    L.hint(3, 0, "Glowing ring? Jump, then HOLD SHIFT (or X) to hook on. Tap SPACE to let go!")
    L.cogs_line(6, 0.9, 12, 0.9, 4)
    L.ring(21, 5.4)
    L.cogs_arc(17.5, 24.5, 1.6, 2.2, 6)
    L.ground(26, 40, 0)
    # B. ride the lift across the canyon
    L.hint(35, 0, "Hop on the brass lift and ride it over.")
    L.mover([(43.5, -0.3), (56.5, -0.3)], period=6.0, w=3.0)
    L.cogs_line(44, 1.3, 56, 1.3, 6)
    L.ground(60, 78, 0)
    L.checkpoint(62, 0)
    # C. a crumbling bridge under a swinging wrecking ball
    L.hint(72, 0, "Crumbly bridge! Keep moving - and mind the wrecking ball.")
    L.pendulum(86.5, 10.6, 8.2, links=6, r=0.9, mass=8.0, start_angle=1.05)
    L.crumble(78, 80.5, 0); L.crumble(80.5, 83, 0); L.crumble(83, 85.5, 0)
    L.crumble(85.5, 88, 0); L.crumble(88, 90.5, 0); L.crumble(90.5, 93, 0)
    L.cogs_line(79, 0.9, 92, 0.9, 7)
    L.star(86.5, 3.3)
    L.ground(93, 112, 0)
    L.checkpoint(96, 0)
    # D. the ring chain over the great gorge
    L.hint(105, 0, "Chain the rings: keep SHIFT held and tap SPACE at the top of each swing.")
    L.ring(117, 5.6); L.ring(124.5, 6.2); L.ring(132, 5.6)
    L.cogs_arc(113.5, 120.5, 1.8, 2.2, 5)
    L.cogs_arc(121, 128, 2.4, 2.2, 5)
    L.cogs_arc(128.5, 135.5, 1.8, 2.2, 5)
    L.star(138.6, 7.8)                      # only a late, high release from the last ring reaches it
    L.ground(137, 150, 0)
    L.checkpoint(139, 0)
    # E. one more ring over the spike pit
    L.hint(146, 0, "Spikes below. One ring. You've got this.")
    L.block(150, 161, -0.6, -16, style="stone")
    L.spikes(150, 161, -0.6)
    L.ring(155, 5.6)
    L.cogs_arc(151, 160, 1.6, 2.6, 6)
    L.ground(161, 174, 0)
    L.checkpoint(164, 0)
    # F. the lift up the cliff, a last spring for the third golden gear, the goal
    L.mover([(175.6, -0.3), (175.6, 9.7)], period=7.0, w=2.6)
    L.cogs_line(175.6, 2.0, 175.6, 9.0, 4)
    L.ground(177, 202, 10.0)
    L.spring(181, 10.0, v=21)
    L.star(182.5, 14.8)
    L.goal(194, 10.0)
    L.cogs_line(185, 10.9, 190, 10.9, 4)
    return L


def clockwork_spire() -> Level:
    L = Level("3-1", "Clockwork Spire", "spire", start=(0, 0.5), kill_y=-12, par=35, seed=37,
              subtitle="Ride the wind, the gears and the walls to the top")
    # A. the fan
    L.ground(-10, 28, 0)
    L.hint(4, 0, "Fans blow you UP. Drift right at the top!")
    L.cogs_line(5, 0.9, 11, 0.9, 4)
    L.wind(17, 0, 2.4, 9.0, accel=70, vmax=10)
    L.cogs_line(17, 3.0, 17, 8.0, 4)
    L.star(15.3, 10.4)                       # drift left off the top of the column
    L.ledge(19.6, 28, 7.0, style="brass")
    L.checkpoint(22, 7.0)
    # B. two turning gear-arms over the spikes
    L.hint(26, 7.0, "Turning arms: hop on when they are flat!")
    L.block(28, 43.5, -0.6, -12, style="stone")
    L.spikes(28, 43.5, -0.6)
    L.spinner(32.5, 7.6, 4.4, 0.8)
    L.spinner(39.4, 9.4, 4.4, -0.8)
    L.cogs_arc(29, 42.5, 9.4, 2.4, 7)
    L.ledge(43.5, 50.5, 10.0, style="brass")
    L.checkpoint(45, 10.0)
    # C. a ladder of crumbling steps (a fan below brings you back if you fall)
    L.hint(48.5, 10.0, "These steps crumble. Don't stop!")
    L.ground(43.5, 50.5, 0, -12, style="stone")
    L.wind(48.2, 0, 2.0, 9.6, accel=70, vmax=10)
    L.ground(50.5, 70, 0, -12, style="stone")
    L.crumble(51.0, 53.5, 12.6)
    L.crumble(55.0, 57.5, 15.2)
    L.crumble(59.0, 61.5, 17.8)
    L.cogs_line(52.2, 13.5, 60.2, 18.7, 4)
    # D. the wall-jump shaft
    L.block(63, 69.4, 20.4, 19.2, style="brass")
    L.block(65.0, 66.4, 32.5, 22.0, style="stone")
    L.block(69.4, 78, 32.5, 19.2, style="stone")
    L.hint(63.8, 20.4, "Wall-jump up the shaft!")
    L.cogs_line(67.9, 23.5, 67.9, 30.5, 5)
    L.star(65.7, 33.6)                        # on top of the column: hop back left for it
    L.checkpoint(72, 32.5)
    # E. one ring across the last gap to the goal
    L.ring(83, 37.9)
    L.cogs_arc(79, 87, 34.1, 2.2, 6)
    L.star(88.5, 37.7)                        # only a late release from the ring reaches it
    L.ledge(88, 102, 32.5, thick=1.4, style="brass")
    L.goal(97, 32.5)
    L.cogs_line(90, 33.4, 94, 33.4, 4)
    return L


LEVELS = [feel_lab, tinker_meadow, pendulum_gorge, clockwork_spire]


def build() -> dict[str, bytes]:
    files = {}
    for make in LEVELS:
        L = make()
        name = f"{L.key}-{L.title.lower().replace(' ', '-')}.x3d"
        files[name] = L.x3d().encode("utf-8")
        files[name + ".counts"] = json.dumps(L.counts, sort_keys=True).encode()
        files[name + ".info"] = json.dumps({"key": L.key, "title": L.title, "subtitle": L.subtitle, "theme": L.theme_name, "par": L.par}).encode()
    return files


def main(argv: list[str]) -> int:
    files = build()
    levels = {k: v for k, v in files.items() if k.endswith(".x3d")}
    manifest = {"schema": "x3d.platformer.levels/1", "generator": "build/build_levels.py",
                "levels": [{"file": k, "bytes": len(v), "sha256": hashlib.sha256(v).hexdigest(),
                            **json.loads(files[k + ".info"]),
                            "counts": json.loads(files[k + ".counts"])} for k, v in sorted(levels.items())]}
    mbytes = (json.dumps(manifest, indent=1, sort_keys=True) + "\n").encode()
    if "--check" in argv:
        bad = [k for k, v in levels.items() if not (OUT / k).exists() or (OUT / k).read_bytes() != v]
        if not (OUT / "MANIFEST.json").exists() or (OUT / "MANIFEST.json").read_bytes() != mbytes:
            bad.append("MANIFEST.json")
        print(json.dumps({"rebuild_identical": not bad, "differs": bad}))
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for k, v in levels.items():
        (OUT / k).write_bytes(v)
    (OUT / "MANIFEST.json").write_bytes(mbytes)
    for lv in manifest["levels"]:
        print(f"{lv['file']:40s} {lv['bytes']:>8d} B  sha256 {lv['sha256'][:12]}  {lv['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
