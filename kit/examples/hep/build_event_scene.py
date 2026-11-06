"""Turn one hep-event JSON file into a high-fidelity X3D 4.0 scene (standard library only).

  python3 -I kit/examples/hep/build_event_scene.py EVENT.json OUTDIR [--cycle 12] [--max-turns 2.5]

Writes OUTDIR/<stem>.x3d and OUTDIR/<stem>.event.json (the event with a "scene" field naming the .x3d, so the
hep-event witness can find it). Generator, not file (law 1): never hand-edit the .x3d, change this script or the event.

LOOK (set by a reference video; see docs/HEP-EVENT-WITNESS.md): the camera looks straight down the beam axis, z
toward the viewer, onto nested translucent cylindrical shells with a cool blue rim, a white flash at the centre,
hundreds of thin glowing filaments (cyan, magenta, amber, emerald, violet), low-pT tracks curling into tight loops
near the centre, high-pT ones straight, and an outer crown of calorimeter towers glowing orange and blue. A second,
three-quarter viewpoint is provided.

WHAT IS DRAWN, AND HOW
- Tracks: one Shape DEF="trk_<i>" per drawn trajectory, an IndexedLineSet with per-vertex FloatVertexAttributes
  a_ident (id, charge, pT, birth time), a_arc (metres along the track) and a_species. Every track USEs ONE DEF'd
  ComposedShader (trkShader). Hue comes from charge and species, brightness from pT, and a pulse runs outward
  along the track. Growth: after the flash at t = FLASH_AT the head of each track advances at SPEED metres per
  second from its birth time, so the tracks grow outward over about 3 s. The clock is one TimeSensor routed to the
  shader field u_phase (fraction of the cycle); no Script, so no field callback can throw (Loom law 32).
- Towers: one Shape DEF="twr_<i>" per calorimeter cell, an IndexedFaceSet box (the FINAL geometry) with a_tower
  (E, arrival time, em fraction, outer-face flag) and a_base; the shared towerShader grows each bar from its base
  when the first particle arrives and flares it. Amber = electromagnetic, blue = hadronic.
- Detector: translucent shells (Material transparency), a ring shader with a ripple that follows the flash, rings at
  the layer radii and calorimeter rims, thin staves, and a flash sprite (PointSet, gl_PointSize) at the origin.
- Labels: Billboard Text for the highest-pT tracks (DEF lbl_<i>).
Traps honoured (Loom): GLSL in ShaderPart url is a data:x-shader/x-vertex, or data:x-shader/x-fragment, URL with no
'#', no '%', no quotes and no '//'; no GLSL identifier 'active'; float literals only (no int literal where a float is
needed); every component is declared in the head (Shaders level 3, which FloatVertexAttribute needs: L, from memory);
ROUTEs come after every DEF; metadata is not used.

Slow motion, declared: a track head advances at SPEED m/s where light moves 3.0e8 m/s. The scene says so in a meta tag.
Limits: the builder renders nothing itself. Look v2 scenes were loaded and rendered in X_ITE 16.5.1 (headless Chromium,
software GL) by kit/examples/hep/render, with 0 shader or console errors (runs/hep-demo-20261106/frames-v2); look v1 was
not. WebGL draws look v1's lines one pixel wide, so its glow is colour and density, not thickness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import random
import sys
from pathlib import Path

CYCLE_S = 12.0        # one animation cycle
FLASH_AT = 0.5        # the flash, seconds into the cycle
SPEED = 0.9           # visual head speed along a track, m/s: the median track (2.8 m of arc to the tracker end) grows in 3.1 s
C_M_PER_NS = 0.299792458
RIPPLE = 3.0          # m/s, the flash ripple through the rings
SPECIES = {"e": 1.0, "mu": 2.0, "hadron": 3.0, "proton": 4.0, "photon": 5.0, "neutral": 6.0, "other": 7.0}
NAMES = {11: "e", 13: "mu", 15: "tau", 22: "gamma", 211: "pi", 321: "K", 2212: "p", 2112: "n", 130: "K0L", 310: "K0S", 111: "pi0"}


def species_of(pdg: int, charge: float) -> float:
    a = abs(pdg)
    if a == 11:
        return SPECIES["e"]
    if a == 13:
        return SPECIES["mu"]
    if a == 22:
        return SPECIES["photon"]
    if a == 2212:
        return SPECIES["proton"]
    if charge != 0:
        return SPECIES["hadron"]
    return SPECIES["neutral"]


def fmt(v: float, nd: int = 4) -> str:
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def sig(v: float, n: int = 5) -> str:
    """n significant digits: a forward neutral can have a pT of 3 MeV, which four decimals of a GeV would round by a percent."""
    return f"{v:.{n}g}"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&apos;").replace('"', "&quot;")


def flt(v: float) -> str:
    """A GLSL float literal: always with a decimal point (an int literal where a float is needed is a GLSL ES error)."""
    s = f"{v:.5f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def glsl(src: str) -> str:
    """One line, no '#', no '%', no quotes, no '//' : safe inside a data: URL and an MFString."""
    one = " ".join(src.split())
    for bad in ("#", "%", '"', "'", "//"):
        if bad in one:
            raise ValueError(f"GLSL source contains {bad!r}, which a data: URL cannot carry safely")
    if re.search(r"\bactive\b", one):
        raise ValueError("GLSL identifier 'active' is reserved")
    return one


# ---------------------------------------------------------------- shaders (GLSL ES 1.00 style, float literals only)

def shaders() -> dict[str, tuple[str, str]]:
    cyc, t0, spd = flt(CYCLE_S), flt(FLASH_AT), flt(SPEED)
    pulse_k, pulse_v = flt(2.2), flt(0.9)
    head_matrices = "uniform mat4 x3d_ModelViewMatrix; uniform mat4 x3d_ProjectionMatrix; attribute vec4 x3d_Vertex;"
    fade = f"smoothstep(0.0, 0.5, t) * (1.0 - smoothstep({flt(CYCLE_S - 1.6)}, {flt(CYCLE_S - 0.1)}, t))"
    track_v = f"""precision highp float; {head_matrices}
      attribute vec4 a_ident; attribute float a_arc; attribute float a_species;
      varying vec4 v_ident; varying float v_arc; varying float v_species;
      void main() {{ v_ident = a_ident; v_arc = a_arc; v_species = a_species;
        gl_Position = x3d_ProjectionMatrix * x3d_ModelViewMatrix * x3d_Vertex; }}"""
    track_f = f"""precision highp float; uniform float u_phase;
      varying vec4 v_ident; varying float v_arc; varying float v_species;
      vec3 species_color(float sp, float q) {{
        vec3 c = vec3(0.35, 0.85, 1.0);
        if (q < 0.0) {{ c = vec3(1.0, 0.30, 0.85); }}
        if (sp > 3.5 && sp < 4.5) {{ c = vec3(1.0, 0.65, 0.15); }}
        if (sp > 0.5 && sp < 1.5) {{ c = vec3(0.20, 1.0, 0.50); }}
        if (sp > 1.5 && sp < 2.5) {{ c = vec3(0.65, 0.45, 1.0); }}
        if (sp > 4.5 && sp < 5.5) {{ c = vec3(1.0, 0.92, 0.55); }}
        if (sp > 5.5) {{ c = vec3(0.95, 0.60, 0.30); }}
        return c; }}
      void main() {{
        float t = u_phase * {cyc};
        float birth = v_ident.w;
        float head = (t - {t0} - birth) * {spd};
        if (v_arc > head) {{ discard; }}
        float bright = clamp(log(1.0 + v_ident.z) / log(61.0), 0.0, 1.0);
        vec3 c = species_color(v_species, v_ident.y);
        float w = fract(v_arc * {pulse_k} - (t - birth) * {pulse_v});
        float pulse = pow(w, 5.0);
        float tip = exp(-(head - v_arc) * 14.0);
        float fade = {fade};
        float gain = (0.35 + 0.9 * bright) * (0.55 + 1.1 * pulse) + 1.6 * tip;
        vec3 col = mix(c, vec3(1.0), clamp(tip * 0.9 + 0.25 * bright * pulse, 0.0, 1.0)) * gain;
        gl_FragColor = vec4(col * fade, 1.0); }}"""
    tower_v = f"""precision highp float; {head_matrices} uniform float u_phase;
      attribute vec4 a_tower; attribute vec3 a_base; varying vec4 v_tower;
      void main() {{
        float t = u_phase * {cyc};
        float k = smoothstep(a_tower.y, a_tower.y + 0.45, t);
        vec3 p = mix(a_base, x3d_Vertex.xyz, k * a_tower.w + (1.0 - a_tower.w));
        v_tower = a_tower;
        gl_Position = x3d_ProjectionMatrix * x3d_ModelViewMatrix * vec4(p, 1.0); }}"""
    tower_f = f"""precision highp float; uniform float u_phase; varying vec4 v_tower;
      void main() {{
        float t = u_phase * {cyc};
        vec3 c = mix(vec3(0.25, 0.62, 1.0), vec3(1.0, 0.56, 0.12), step(0.5, v_tower.z));
        float lit = smoothstep(v_tower.y, v_tower.y + 0.2, t);
        float flare = exp(-max(t - v_tower.y, 0.0) * 2.5) * lit;
        float e = clamp(log(1.0 + v_tower.x) / log(41.0), 0.0, 1.0);
        float fade = {fade};
        float tip = mix(0.55, 1.0, v_tower.w);
        vec3 col = c * (0.08 + lit * (0.45 + 0.9 * e) * tip) + vec3(1.0) * flare * 0.5;
        gl_FragColor = vec4(col * fade, 1.0); }}"""
    ring_v = f"""precision highp float; {head_matrices}
      attribute vec3 a_ring; varying vec3 v_ring;
      void main() {{ v_ring = a_ring; gl_Position = x3d_ProjectionMatrix * x3d_ModelViewMatrix * x3d_Vertex; }}"""
    ring_f = f"""precision highp float; uniform float u_phase; varying vec3 v_ring;
      void main() {{
        float t = u_phase * {cyc};
        float front = (t - {t0}) * {flt(RIPPLE)};
        float d = (front - v_ring.x) * 5.0;
        float ripple = exp(-d * d) * step(0.0, t - {t0});
        float shimmer = 0.5 + 0.5 * sin(v_ring.y * 62.8318 - t * 1.3);
        vec3 c = mix(vec3(0.10, 0.30, 0.65), vec3(0.55, 0.85, 1.0), v_ring.z);
        vec3 col = c * (0.35 + 0.45 * shimmer * v_ring.z) + vec3(0.6, 0.85, 1.0) * ripple * 1.2;
        gl_FragColor = vec4(col, 1.0); }}"""
    flash_v = f"""precision highp float; {head_matrices} uniform float u_phase; varying float v_flash;
      void main() {{
        float t = u_phase * {cyc};
        float s = t - {t0};
        v_flash = exp(-max(s, 0.0) * 2.2) * step(0.0, s);
        gl_PointSize = 26.0 + 330.0 * v_flash;
        gl_Position = x3d_ProjectionMatrix * x3d_ModelViewMatrix * x3d_Vertex; }}"""
    flash_f = """precision highp float; varying float v_flash;
      void main() {
        vec2 q = (gl_PointCoord - vec2(0.5)) * 2.0;
        float d = length(q);
        if (d > 1.0) { discard; }
        float core = exp(-d * d * 18.0);
        float halo = exp(-d * 3.5) * (0.15 + 0.85 * v_flash) * (1.0 - d);
        float spikes = (exp(-abs(q.x) * 30.0) + exp(-abs(q.y) * 30.0)) * (1.0 - d) * v_flash * 0.8;
        float a = core * (0.6 + 0.8 * v_flash) + halo + spikes;
        if (a < 0.03) { discard; }
        vec3 col = mix(vec3(0.35, 0.65, 1.0), vec3(1.0), clamp(core + v_flash * 0.5, 0.0, 1.0)) * a;
        gl_FragColor = vec4(col, 1.0); }"""
    return {n: (glsl(v), glsl(f)) for n, (v, f) in {"trk": (track_v, track_f), "twr": (tower_v, tower_f),
                                                      "ring": (ring_v, ring_f), "flash": (flash_v, flash_f)}.items()}


def shader_node(name: str, vsrc: str, fsrc: str, indent: str = "") -> str:
    return (f"{indent}<ComposedShader DEF='{name}' language='GLSL'>"
            f"<field name='u_phase' type='SFFloat' accessType='inputOutput' value='0'/>"
            f"<ShaderPart type='VERTEX' url='\"data:x-shader/x-vertex,{esc(vsrc)}\"'/>"
            f"<ShaderPart type='FRAGMENT' url='\"data:x-shader/x-fragment,{esc(fsrc)}\"'/></ComposedShader>")


# ---------------------------------------------------------------- geometry (independent of the witness)

def sample_track(t: dict, det: dict, max_turns: float, dphi: float) -> tuple[list, list]:
    """Points (x, y, z) and 3D arc length at each, from the vertex until the track leaves the tracker or turns enough."""
    h = t["helix"]
    x0, y0, z0 = h.get("vertex_m", [0.0, 0.0, 0.0])
    phi0, tanl = t["phi"], math.sinh(t["eta"])
    rmax, half = det["tracker"]["r_max_m"], det["tracker"]["half_length_m"]
    R, sense = h["radius_m"], h["sense"]

    def pos(s):
        if R is None or sense == 0:
            return x0 + s * math.cos(phi0), y0 + s * math.sin(phi0), z0 + s * tanl
        a = phi0 + sense * s / R
        return (x0 + (R / sense) * (math.sin(a) - math.sin(phi0)),
                y0 - (R / sense) * (math.cos(a) - math.cos(phi0)), z0 + s * tanl)

    def inside(p):
        return math.hypot(p[0], p[1]) <= rmax and abs(p[2]) <= half

    s_cap = (max_turns * 2 * math.pi * R) if R else 4.0 * (rmax + half)
    step = (R * dphi) if R else 0.25
    s, s_in = 0.0, 0.0
    exited = False
    while s < s_cap:
        s_try = min(s + step, s_cap)
        if not inside(pos(s_try)):
            lo, hi = s, s_try
            for _ in range(48):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if inside(pos(mid)) else (lo, mid)
            s_in, exited = lo, True
            break
        s = s_try
        s_in = s
        if s >= s_cap:
            break
    n = max(4 if R else 2, int(math.ceil(s_in / step)) + 1) if s_in > 0 else 2
    if R is None or sense == 0:
        n = 2
    n = min(n, 400)
    ss = [s_in * i / (n - 1) for i in range(n)]
    k3 = math.sqrt(1.0 + tanl * tanl)
    return [pos(v) for v in ss], [v * k3 for v in ss]


def look_at(eye, target=(0.0, 0.0, 0.0)):
    """X3D orientation (axis, angle) that points a default viewpoint (looking down -z, up +y) from eye to target."""
    back = [e - c for e, c in zip(eye, target)]
    n = math.sqrt(sum(c * c for c in back))
    back = [c / n for c in back]
    right = [back[2], 0.0, -back[0]]  # cross((0, 1, 0), back)
    rn = math.sqrt(sum(c * c for c in right))
    right = [c / rn for c in right]
    up = [back[1] * right[2] - back[2] * right[1], back[2] * right[0] - back[0] * right[2], back[0] * right[1] - back[1] * right[0]]
    m = [[right[0], up[0], back[0]], [right[1], up[1], back[1]], [right[2], up[2], back[2]]]
    tr = m[0][0] + m[1][1] + m[2][2]
    ang = math.acos(max(-1.0, min(1.0, (tr - 1.0) / 2.0)))
    ax = [m[2][1] - m[1][2], m[0][2] - m[2][0], m[1][0] - m[0][1]]
    an = math.sqrt(sum(c * c for c in ax))
    if an < 1e-9:
        return (0.0, 0.0, 1.0, 0.0)
    return (ax[0] / an, ax[1] / an, ax[2] / an, ang)


def circle(r, z, n=96):
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z) for i in range(n + 1)]


def birth_s(k: int, t_prod_ns: float) -> float:
    """Seconds into the growth at which this track starts: production time in slow motion plus a fixed jitter per id."""
    jitter = 0.10 * ((math.sin(k * 12.9898) * 43758.5453) % 1.0)
    return round(t_prod_ns * C_M_PER_NS / SPEED + jitter, 4)


# ---------------------------------------------------------------- the scene

def build(ev: dict, event_sha256: str, cycle: float = CYCLE_S, max_turns: float = 2.5, label_top: int = 8) -> tuple[str, dict]:
    det = ev["detector"]
    tr, ca = det["tracker"], det["calorimeter"]
    sh = shaders()
    out: list[str] = []
    w = out.append
    w("<?xml version='1.0' encoding='UTF-8'?>")
    w("<X3D profile='Immersive' version='4.0' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' "
      "xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.0.xsd'>")
    w("<head>")
    w("<component name='Shaders' level='3'/>")
    w(f"<meta name='title' content='{esc('Collider event ' + str(ev.get('id', '')))}'/>")
    w("<meta name='description' content='One generated collider event seen end-on: every particle is a shader-driven filament; towers light when particles arrive.'/>")
    w("<meta name='generator' content='kit/examples/hep/build_event_scene.py'/>")
    w(f"<meta name='event-id' content='{esc(str(ev.get('id', '')))}'/>")
    w(f"<meta name='event-sha256' content='{event_sha256}'/>")
    w(f"<meta name='slow-motion' content='track heads advance at {SPEED} m/s; light moves 2.998e8 m/s'/>")
    w(f"<meta name='units' content='metres, GeV, tesla; z is the beam axis'/>")
    w("<meta name='license' content='MIT'/>")
    w("</head>")
    w("<Scene>")
    w(f"<WorldInfo title='{esc('Collider event ' + str(ev.get('id', '')))}' info='\"Generated; edit kit/examples/hep/build_event_scene.py, never this file\"'/>")
    w("<NavigationInfo type='\"EXAMINE\" \"ANY\"' headlight='false'/>")
    w("<Background skyAngle='0.9 1.5708' skyColor='0 0.02 0.05 0.01 0.035 0.075 0.003 0.012 0.03' "
      "groundAngle='1.5708 2.4' groundColor='0.003 0.012 0.03 0 0.006 0.015 0 0 0'/>")
    eye = (0.0, 0.0, 22.0)
    w(f"<Viewpoint DEF='vp_endon' description='End-on along the beam' position='{eye[0]:g} {eye[1]:g} {eye[2]:g}' "
      f"orientation='0 0 1 0' fieldOfView='0.21' centerOfRotation='0 0 0'/>")
    e2 = (5.6, 3.3, 8.4)
    o = look_at(e2)
    w(f"<Viewpoint DEF='vp_three_quarter' description='Three-quarter' position='{e2[0]:g} {e2[1]:g} {e2[2]:g}' "
      f"orientation='{fmt(o[0], 5)} {fmt(o[1], 5)} {fmt(o[2], 5)} {fmt(o[3], 5)}' fieldOfView='0.7' centerOfRotation='0 0 0'/>")
    w(f"<TimeSensor DEF='clock' cycleInterval='{cycle:g}' loop='true'/>")
    # shader definitions live in an unselected Switch so no track owns them; every user USEs them
    w("<Switch DEF='shader_defs' whichChoice='-1'><Shape><Appearance>")
    for name in ("trk", "twr", "ring", "flash"):
        w(shader_node(f"{name}Shader", *sh[name]))
    w("</Appearance></Shape></Switch>")

    # --- detector
    w("<Group DEF='detector'>")
    for r, half, rgb, tp, nm in ((tr["r_max_m"], tr["half_length_m"], "0.15 0.45 1.0", 0.86, "tracker_shell"),
                                 (ca["r_min_m"], ca["half_length_m"], "0.2 0.5 0.9", 0.88, "calo_inner_shell"),
                                 (ca["r_max_m"], ca["half_length_m"], "0.25 0.55 1.0", 0.82, "calo_outer_shell"),
                                 (0.03, tr["half_length_m"], "0.7 0.75 0.85", 0.3, "beam_pipe")):
        w(f"<Transform DEF='{nm}' rotation='1 0 0 1.5707963'><Shape><Appearance><Material diffuseColor='0 0 0' emissiveColor='{rgb}' transparency='{tp}'/></Appearance>"
          f"<Cylinder radius='{r:g}' height='{2 * half:g}' top='false' bottom='false' solid='false'/></Shape></Transform>")
    pts, idx, a_ring, n0 = [], [], [], 0

    def add_line(points, rr, lvl, phase_fn):
        nonlocal n0
        for i, p in enumerate(points):
            pts.append(p)
            a_ring.append((rr, phase_fn(i, len(points)), lvl))
        idx.extend(range(n0, n0 + len(points)))
        idx.append(-1)
        n0 += len(points)

    layers = tr.get("layer_radii_m", [])
    for r in layers:
        for z in (-tr["half_length_m"], tr["half_length_m"]):
            add_line(circle(r, z), r, 0.35, lambda i, n: i / (n - 1))
    for r, z, lvl in ((tr["r_max_m"], tr["half_length_m"], 0.8), (tr["r_max_m"], -tr["half_length_m"], 0.8),
                      (ca["r_min_m"], ca["half_length_m"], 0.9), (ca["r_min_m"], -ca["half_length_m"], 0.9),
                      (ca["r_max_m"], ca["half_length_m"], 1.0), (ca["r_max_m"], -ca["half_length_m"], 1.0),
                      (ca["r_min_m"], 0.0, 0.45), (ca["r_max_m"], 0.0, 0.55)):
        add_line(circle(r, z), r, lvl, lambda i, n: i / (n - 1))
    for r, half, count, lvl in ((tr["r_max_m"], tr["half_length_m"], 24, 0.3), (ca["r_max_m"], ca["half_length_m"], 48, 0.4)):
        for j in range(count):
            a = 2 * math.pi * j / count
            add_line([(r * math.cos(a), r * math.sin(a), -half), (r * math.cos(a), r * math.sin(a), half)], r, lvl,
                     lambda i, n, j=j: j / count)
    ring_idx = " ".join(map(str, idx))
    ring_pts = " ".join(f"{fmt(p[0])} {fmt(p[1])} {fmt(p[2])}" for p in pts)
    ring_attr = " ".join(f"{fmt(a[0])} {fmt(a[1], 3)} {fmt(a[2], 2)}" for a in a_ring)
    w("<Shape DEF='rings'><Appearance><ComposedShader USE='ringShader'/></Appearance>"
      f"<IndexedLineSet coordIndex='{ring_idx}'><Coordinate point='{ring_pts}'/>"
      f"<FloatVertexAttribute name='a_ring' numComponents='3' value='{ring_attr}'/></IndexedLineSet></Shape>")
    w("<Shape DEF='flash'><Appearance><ComposedShader USE='flashShader'/></Appearance><PointSet><Coordinate point='0 0 0'/></PointSet></Shape>")
    w("</Group>")

    # --- tracks
    tracks = ev.get("tracks", [])
    species_count: dict[str, int] = {}
    npoints = 0
    w("<Group DEF='tracks'>")
    by_pt = sorted(range(len(tracks)), key=lambda i: -tracks[i]["pt"])
    labelled = set(by_pt[:label_top])
    labels = []
    for t in tracks:
        k = t["i"]
        p = ev["particles"][t["particle"]]
        pts3, arcs = sample_track(t, det, max_turns, math.radians(7.0))
        npoints += len(pts3)
        sp = species_of(p["pdg"], t["charge"])
        key = {v: n for n, v in SPECIES.items()}[sp]
        species_count[key] = species_count.get(key, 0) + 1
        b = birth_s(k, t.get("t_prod_ns", 0.0))
        n = len(pts3)
        ident_row = f"{k} {fmt(t['charge'], 3)} {sig(t['pt'])} {fmt(b)}"
        coords = " ".join(f"{fmt(q[0])} {fmt(q[1])} {fmt(q[2])}" for q in pts3)
        w(f"<Shape DEF='trk_{k}'><Appearance><ComposedShader USE='trkShader'/></Appearance>"
          f"<IndexedLineSet coordIndex='{' '.join(map(str, range(n)))} -1'>"
          f"<Coordinate point='{coords}'/>"
          f"<FloatVertexAttribute name='a_ident' numComponents='4' value='{' '.join([ident_row] * n)}'/>"
          f"<FloatVertexAttribute name='a_arc' numComponents='1' value='{' '.join(fmt(a) for a in arcs)}'/>"
          f"<FloatVertexAttribute name='a_species' numComponents='1' value='{' '.join([fmt(sp, 1)] * n)}'/></IndexedLineSet></Shape>")
        if t["i"] in labelled:
            nm = NAMES.get(abs(p["pdg"]), f"pdg {p['pdg']}")
            sign = "+" if t["charge"] > 0 else "-" if t["charge"] < 0 else ""
            labels.append((k, f"{nm}{sign} {t['pt']:.1f} GeV", pts3[-1]))
    w("</Group>")
    w("<Group DEF='labels'>")
    for k, text, q in labels:
        w(f"<Transform DEF='lbl_{k}' translation='{fmt(q[0] * 1.04)} {fmt(q[1] * 1.04)} {fmt(q[2])}'><Billboard axisOfRotation='0 0 0'><Shape>"
          f"<Appearance><Material diffuseColor='0 0 0' emissiveColor='0.8 0.92 1'/></Appearance>"
          f"<Text string='\"{esc(text)}\"'><FontStyle size='0.09' justify='\"MIDDLE\" \"MIDDLE\"'/></Text></Shape></Billboard></Transform>")
    w("</Group>")

    # --- towers
    towers = ev.get("towers", [])
    w("<Group DEF='towers'>")
    depth = ca["r_max_m"] - ca["r_min_m"]
    e_full = max([x["E"] for x in towers] + [20.0])
    tower_ids = []
    cosets = [(0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1), (1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1)]
    for x in towers:
        ph, eta = x["phi"], x["eta"]
        r0 = ca["r_min_m"]
        length = 0.03 + (depth - 0.06) * min(1.0, (x["E"] / e_full) ** 0.6)
        wt = r0 * 0.0873 * 0.42
        zc = r0 * math.sinh(eta)
        wz = min(0.5 * 0.8 * r0 * math.cosh(eta) * 0.0873, ca["half_length_m"] - 0.005 - abs(zc))
        wz = max(wz, 0.004)
        cp, sp_ = math.cos(ph), math.sin(ph)
        full, base = [], []
        for rr, sf, sz in cosets:
            for rad, store in ((r0 + length * rr, full), (r0, base)):
                store.append((rad * cp - (2 * sf - 1) * wt * sp_, rad * sp_ + (2 * sf - 1) * wt * cp, zc + (2 * sz - 1) * wz))
        arrive = round(x.get("t_arr_ns", r0 * math.cosh(eta) / C_M_PER_NS) * C_M_PER_NS / SPEED + FLASH_AT + 0.0, 4)
        em = x.get("em_frac", 0.5)
        tower_row = lambda flag: f"{fmt(x['E'], 3)} {fmt(arrive)} {fmt(em, 3)} {flag}"  # noqa: E731
        full_pts = " ".join(f"{fmt(q[0])} {fmt(q[1])} {fmt(q[2])}" for q in full)
        base_pts = " ".join(f"{fmt(q[0])} {fmt(q[1])} {fmt(q[2])}" for q in base)
        w(f"<Shape DEF='twr_{x['i']}'><Appearance><ComposedShader USE='twrShader'/></Appearance>"
          f"<IndexedFaceSet solid='false' coordIndex='0 1 3 2 -1 4 5 7 6 -1 0 1 5 4 -1 2 3 7 6 -1 0 2 6 4 -1 1 3 7 5 -1'>"
          f"<Coordinate point='{full_pts}'/>"
          f"<FloatVertexAttribute name='a_tower' numComponents='4' value='{' '.join(tower_row(rr) for rr, _s, _z in cosets)}'/>"
          f"<FloatVertexAttribute name='a_base' numComponents='3' value='{base_pts}'/></IndexedFaceSet></Shape>")
        tower_ids.append(x["i"])
    w("</Group>")
    # ROUTEs after every DEF (trap route-before-def)
    for n in ("trkShader", "twrShader", "ringShader", "flashShader"):
        w(f"<ROUTE fromNode='clock' fromField='fraction_changed' toNode='{n}' toField='u_phase'/>")
    w("</Scene></X3D>")
    text = "\n".join(out) + "\n"
    return text, {"tracks": len(tracks), "track_points": npoints, "towers": len(towers), "labels": len(labels), "species": species_count,
                  "bytes": len(text.encode()), "shader_nodes": 4, "route_count": 4}


# ================================================================ look v2 (--look v2)
#
# LOOK V2: the same event, drawn with the recipes measured in X_ITE 16.5.1 (headless Chromium, software GL):
# - Tracks: screen-space ribbons. All tracks live in a FEW merged Shapes DEF="trkset_<n>" (a TriangleStripSet each, at
#   most TRK_CHUNK tracks per Shape), every one USEing ONE ComposedShader (trkShader2). One strip per track: a pair of
#   vertices per centreline point, offset by side * EPS * (1, 0.7, 0.3) so no triangle has zero area (zero-area strips
#   crashed SwiftShader from about 33k vertices), the vertex shader takes the offset off again and widens the strip in
#   screen space. Per-vertex attributes: a_ident (id, charge, pT, birth s), a_arc (m), a_species, a_next (the next
#   centreline point) and a_look (side, seed, drawn arc length, kind 0 charged / 1 neutral / 2 muon extension).
#   The witness reads the merged strips through the declared convention in the spec (scene.merged).
# - Muons: only muons pass the calorimeter. Each muon that leaves the tracker continues straight along its exit
#   tangent, out through the muon stations, in one Shape DEF="muext_<n>" (same shader, same a_ident).
# - Towers: a comb of needles. Every event tower becomes 6 to 24 thin radial needles spread over its own (eta, phi)
#   cell, lengths from its real energy, merged into one Shape DEF="twrset_<n>" with a_cell (tower id, E, em fraction,
#   arrival s). Hue is energy relative to the event (blue below its median tower, amber toward its 90th percentile,
#   u_e90), electromagnetic towers lean gold and get a brighter white base; the calorimeter face glows where the energy landed.
# - Detector: Fresnel glass shells (one shared shellShader), muon stations and struts as dark steel with lit edges,
#   a billboard flash, an fbm haze drawn in screen space behind everything, native ParticleSystem sparks at the vertex.
# - Everything additive (BlendMode ONE ONE, DepthMode depthMask false: nothing writes depth, so the draw order does not
#   matter; X_ITE 16.5.1's DepthMode has no readOnly field and drops unknown attributes silently), tone-mapped inside each shader
#   (1 - exp(-k c)): X_ITE's ToneMapping option does not touch ComposedShader output. ONE TimeSensor (clock) drives
#   every shader through u_phase: growth front, travelling pulses, tower light-up, flash, ripple, haze drift.
# - Bloom: optional, a separate file per view (bloom_wrapper): the whole scene inside a RenderedTexture sampled by a
#   full-screen threshold-blur shader (X3D 4.1). The un-bloomed scene is the witnessed candidate.
# Colour = meaning: + hadron cyan, - hadron magenta, electron emerald, muon violet-white, proton coral, photon orange
# (dashed: a photon leaves no hits), neutral hadron gold (faint stitching); brightness and width from pT, steeply, so the
# hard tracks read as spokes and the soft loopers stay faint.

EPS = 0.004                         # anti-degeneracy offset, m (measured fix for the SwiftShader zero-area crash)
OFF = (EPS, EPS * 0.7, EPS * 0.3)
TRK_CHUNK = 600                     # tracks per merged Shape
MU_R_OUT, MU_Z_OUT = 3.3, 4.4       # where a muon extension stops (inside the spec's merged.extensions bounds)
STATIONS = ((2.45, 2.75), (2.85, 3.15))   # muon station radii (decoration, not in the event format)
STATION_HALF = 3.6
V2_DPHI = math.radians(4.0)
V2_VIEWS = {"endon": ("vp_endon", "End-on along the beam", (0.0, 0.0, 120.0), 0.0265),
            "three_quarter": ("vp_three_quarter", "Three-quarter", (7.2, 4.0, 10.6), 0.62),
            "side": ("vp_side", "Side", (12.6, 1.1, 0.35), 0.6)}


def _fade() -> str:
    return f"smoothstep(0.0, 0.5, t) * (1.0 - smoothstep({flt(CYCLE_S - 1.6)}, {flt(CYCLE_S - 0.1)}, t))"


def shaders_v2(look: str = "v2") -> dict[str, tuple[str, str]]:
    cyc, t0, spd = flt(CYCLE_S), flt(FLASH_AT), flt(SPEED)
    mats = "uniform mat4 x3d_ModelViewMatrix; uniform mat4 x3d_ProjectionMatrix; attribute vec4 x3d_Vertex;"
    off = f"vec3({flt(OFF[0])}, {flt(OFF[1])}, {flt(OFF[2])})"
    fade = _fade()
    tone = "col = vec3(1.0) - exp(-col * {k});"
    ribbon_dir = """vec2 hv = vec2(x3d_Viewport.zw) * 0.5;
        vec2 d = (c1.xy / c1.w - c0.xy / c0.w) * hv;
        float l = length(d);
        d = l > 0.0001 ? d / l : vec2(1.0, 0.0);"""
    trk_v = f"""precision highp float; {mats} uniform ivec4 x3d_Viewport; uniform float u_phase;
      attribute vec4 a_ident; attribute float a_arc; attribute float a_species; attribute vec3 a_next; attribute vec4 a_look;
      varying vec4 v_ident; varying float v_arc; varying float v_species; varying vec4 v_look; varying float v_rad;
      void main() {{
        vec3 c = x3d_Vertex.xyz - a_look.x * {off};
        vec4 c0 = x3d_ProjectionMatrix * (x3d_ModelViewMatrix * vec4(c, 1.0));
        vec4 c1 = x3d_ProjectionMatrix * (x3d_ModelViewMatrix * vec4(a_next, 1.0));
        {ribbon_dir}
        float bright = clamp(log(1.0 + a_ident.z) / log(41.0), 0.0, 1.0);
        float mu = step(1.5, a_species) * (1.0 - step(2.5, a_species));
        float w = 1.0 + 3.2 * pow(bright, 1.3) + 1.6 * mu;
        vec2 o = vec2(-d.y, d.x) * a_look.x * w;
        gl_Position = c0 + vec4(o / hv * c0.w, 0.0, 0.0);
        v_ident = a_ident; v_arc = a_arc; v_species = a_species; v_look = a_look; v_rad = length(c.xy); }}"""
    trk_f = f"""precision highp float; uniform float u_phase;
      varying vec4 v_ident; varying float v_arc; varying float v_species; varying vec4 v_look; varying float v_rad;
      float hash(float n) {{ return fract(sin(n * 91.3458) * 47453.5453); }}
      vec3 hue(float sp, float q) {{
        vec3 c = vec3(0.10, 0.92, 1.0);
        if (q < 0.0) {{ c = vec3(1.0, 0.14, 0.72); }}
        if (sp > 0.5 && sp < 1.5) {{ c = vec3(0.14, 1.0, 0.40); }}
        if (sp > 1.5 && sp < 2.5) {{ c = vec3(0.80, 0.62, 1.0); }}
        if (sp > 3.5 && sp < 4.5) {{ c = vec3(1.0, 0.34, 0.14); }}
        if (sp > 4.5 && sp < 5.5) {{ c = vec3(1.0, 0.52, 0.06); }}
        if (sp > 5.5 && sp < 6.5) {{ c = vec3(1.0, 0.80, 0.20); }}
        if (sp > 6.5) {{ c = vec3(0.80, 0.85, 0.90); }}
        return c; }}
      void main() {{
        float t = u_phase * {cyc};
        float age = t - {t0} - v_ident.w;
        float head = age * {spd};
        if (v_arc > head) {{ discard; }}
        float v = v_look.x;
        float core = exp(-v * v * 9.0);
        float halo = exp(-v * v * 2.2);
        float bright = clamp(log(1.0 + v_ident.z) / log(41.0), 0.0, 1.0);
        float seed = v_look.y;
        float neutral = step(0.5, v_look.w) * (1.0 - step(1.5, v_look.w));
        float freq = 1.1 + 2.2 * hash(seed * 7.13);
        float pulse = pow(1.0 - fract(v_arc * freq - age * (0.6 + 0.7 * hash(seed * 3.7)) + hash(seed)), 6.0);
        float dash = mix(1.0, 0.18 + 0.82 * step(0.4, fract(v_arc * 14.0 + seed)), neutral);
        float growing = 1.0 - smoothstep(v_look.z, v_look.z + 0.25, head);
        float tip = exp(-max(head - v_arc, 0.0) * 9.0) * growing;
        float knot = 0.0;
        if (v_look.w > 1.5) {{ float a1 = (v_rad - 2.60) * 9.0; float a2 = (v_rad - 3.00) * 9.0; knot = exp(-a1 * a1) + exp(-a2 * a2); }}
        vec3 c = hue(v_species, v_ident.y);
        float gain = (0.28 + 1.35 * bright) * (0.62 + 0.95 * pulse) * dash * (1.0 - 0.65 * neutral);
        vec3 col = c * (halo * 0.34 + core * 0.9) * gain;
        col += vec3(1.0) * core * (0.22 * pulse * bright + 1.6 * tip + 0.9 * knot);
        {tone.format(k='1.15')}
        gl_FragColor = vec4(col * {fade}, 1.0); }}"""
    twr_v = f"""precision highp float; {mats} uniform ivec4 x3d_Viewport; uniform float u_phase;
      attribute vec4 a_cell; attribute vec3 a_next; attribute vec4 a_look;
      varying vec4 v_cell; varying vec4 v_look;
      void main() {{
        float t = u_phase * {cyc};
        vec3 c = x3d_Vertex.xyz - a_look.x * {off};
        vec3 b = a_look.z > 0.5 ? 2.0 * c - a_next : c;
        float g = smoothstep(a_cell.w, a_cell.w + 0.5, t);
        vec3 p = mix(b, c, max(g, 0.02));
        vec4 c0 = x3d_ProjectionMatrix * (x3d_ModelViewMatrix * vec4(p, 1.0));
        vec4 c1 = x3d_ProjectionMatrix * (x3d_ModelViewMatrix * vec4(a_next, 1.0));
        {ribbon_dir}
        float e = clamp(log(1.0 + a_cell.y) / log(31.0), 0.0, 1.0);
        float w = 0.8 + 1.4 * e;
        vec2 o = vec2(-d.y, d.x) * a_look.x * w;
        gl_Position = c0 + vec4(o / hv * c0.w, 0.0, 0.0);
        v_cell = a_cell; v_look = a_look; }}"""
    twr_f = f"""precision highp float; uniform float u_phase; uniform float u_e90; varying vec4 v_cell; varying vec4 v_look;
      void main() {{
        float t = u_phase * {cyc};
        float e = clamp(log(1.0 + v_cell.y) / log(31.0), 0.0, 1.0);
        float eh = clamp(log(1.0 + v_cell.y) / log(1.0 + max(u_e90, 0.05)), 0.0, 1.0);
        vec3 heat = mix(vec3(0.16, 0.48, 1.0), vec3(1.0, 0.56, 0.10), smoothstep(0.25, 0.80, eh));
        vec3 c = mix(heat, vec3(1.0, 0.78, 0.30), 0.35 * v_cell.z);
        float lit = smoothstep(v_cell.w, v_cell.w + 0.15, t);
        float flare = exp(-max(t - v_cell.w, 0.0) * 2.0) * lit;
        float u = v_look.z;
        float v = v_look.x;
        float core = exp(-v * v * 8.0);
        float halo = exp(-v * v * 2.0);
        float shimmer = 0.86 + 0.14 * sin(t * 9.0 + v_look.y * 40.0);
        vec3 col = c * (core * 1.25 + halo * 0.4) * (0.4 + 1.1 * e) * (1.0 - 0.5 * u) * lit * shimmer;
        col += vec3(1.0, 0.93, 0.82) * core * exp(-u * 4.0) * (0.2 + 0.6 * e) * (0.5 + 0.5 * v_cell.z) * lit * 0.3;
        col += vec3(1.0) * core * flare * 0.7;
        {tone.format(k='0.95')}
        gl_FragColor = vec4(col * {fade}, 1.0); }}"""
    shell_v = f"""precision highp float; {mats} uniform mat3 x3d_NormalMatrix; attribute vec3 x3d_Normal;
      attribute vec4 a_shell; attribute vec4 a_geo;
      varying vec3 v_n; varying vec3 v_p; varying vec3 v_obj; varying vec4 v_shell; varying vec4 v_geo;
      void main() {{
        vec4 p = x3d_ModelViewMatrix * x3d_Vertex;
        v_p = p.xyz; v_n = x3d_NormalMatrix * x3d_Normal; v_obj = x3d_Vertex.xyz; v_shell = a_shell; v_geo = a_geo;
        gl_Position = x3d_ProjectionMatrix * p; }}"""
    shell_f = f"""precision highp float; uniform float u_phase;
      varying vec3 v_n; varying vec3 v_p; varying vec3 v_obj; varying vec4 v_shell; varying vec4 v_geo;
      void main() {{
        float t = u_phase * {cyc};
        vec3 N = normalize(v_n);
        vec3 V = normalize(-v_p);
        float fres = pow(1.0 - abs(dot(N, V)), 3.0);
        float z = v_obj.z;
        float r = v_geo.x;
        float hl = v_geo.y;
        float ang = atan(v_obj.y, v_obj.x);
        float face = abs(dot(N, V));
        float rib = smoothstep(0.88, 1.0, abs(sin(z * v_shell.y))) * smoothstep(0.12, 0.35, face);
        float pan = smoothstep(0.965, 1.0, abs(sin(ang * v_geo.z * 0.5)));
        float steel = step(1.5, v_shell.x) * (1.0 - step(2.5, v_shell.x));
        float endg = exp(-max(hl - abs(z), 0.0) * 14.0) * (1.0 - steel);
        float front = (t - {t0}) * {flt(RIPPLE)};
        float rip = exp(-(front - r) * (front - r) * 6.0) * step(0.0, t - {t0});
        float k = v_shell.x;
        vec3 c = vec3(0.34, 0.52, 0.80);
        if (k > 0.5) {{ c = vec3(0.50, 0.74, 1.0); }}
        if (k > 1.5) {{ c = vec3(0.14, 0.22, 0.36) * smoothstep(0.05, 0.30, face); }}
        if (k > 2.5) {{ c = vec3(0.24, 0.46, 0.85); }}
        float b = v_shell.w;
        float lip = smoothstep(hl - 0.12, hl, abs(z));
        vec3 col = c * (fres * 0.8 * mix(0.3, 1.0, lip) + 0.025) * b;
        col += c * (rib * 0.5 + pan * 0.3) * (0.18 + 0.82 * fres) * b * (1.0 - 0.4 * steel);
        col += vec3(0.72, 0.86, 1.0) * endg * b * 0.85;
        col += vec3(1.0, 0.52, 0.12) * v_shell.z * (0.06 + 0.94 * fres * fres) * smoothstep(2.0, 3.6, t);
        col += vec3(0.6, 0.85, 1.0) * rip * 0.7 * b;
        {tone.format(k='1.35')}
        gl_FragColor = vec4(col * (0.35 + 0.65 * {fade}), 1.0); }}"""
    flash_v = f"""precision highp float; {mats} varying vec2 v_uv;
      void main() {{ v_uv = x3d_Vertex.xy; gl_Position = x3d_ProjectionMatrix * (x3d_ModelViewMatrix * x3d_Vertex); }}"""
    flash_f = f"""precision highp float; uniform float u_phase; varying vec2 v_uv;
      void main() {{
        float t = u_phase * {cyc};
        float s = t - {t0};
        float bang = exp(-max(s, 0.0) * 1.8) * step(0.0, s);
        float level = (0.15 + 0.85 * smoothstep(0.0, 0.5, t)) * (0.35 + 2.4 * bang);
        vec2 p = v_uv;
        float r = length(p);
        float glow = exp(-r * r * 16.0) * 1.1 + 0.22 / (1.0 + r * r * 140.0);
        float st = exp(-abs(p.y) * 55.0) * exp(-abs(p.x) * 2.2) + exp(-abs(p.x) * 55.0) * exp(-abs(p.y) * 2.2);
        float dg = exp(-abs(p.x - p.y) * 60.0) * exp(-abs(p.x + p.y) * 3.5) + exp(-abs(p.x + p.y) * 60.0) * exp(-abs(p.x - p.y) * 3.5);
        float edge = 1.0 - smoothstep(0.7, 1.0, r);
        vec3 col = vec3(0.86, 0.93, 1.0) * (glow + (0.45 * st + 0.16 * dg) * (0.5 + bang)) * edge * level;
        {tone.format(k='1.6')}
        gl_FragColor = vec4(col * (1.0 - smoothstep({flt(CYCLE_S - 1.6)}, {flt(CYCLE_S - 0.1)}, t)), 1.0); }}"""
    haze_v = """precision highp float; attribute vec4 x3d_Vertex; varying vec2 v_uv;
      void main() { v_uv = x3d_Vertex.xy; gl_Position = vec4(x3d_Vertex.xy, 0.9999, 1.0); }"""
    haze_f = f"""precision highp float; uniform float u_phase; varying vec2 v_uv;
      float h(vec2 p) {{ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }}
      float n(vec2 p) {{
        vec2 i = floor(p);
        vec2 f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        return mix(mix(h(i), h(i + vec2(1.0, 0.0)), f.x), mix(h(i + vec2(0.0, 1.0)), h(i + vec2(1.0, 1.0)), f.x), f.y); }}
      float fbm(vec2 p) {{
        float a = 0.5;
        float s = 0.0;
        for (float i = 0.0; i < 4.5; i += 1.0) {{ s += a * n(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; }}
        return s; }}
      void main() {{
        float t = u_phase * {cyc};
        vec2 p = v_uv * vec2(1.78, 1.0);
        float r = length(p);
        float f = fbm(p * 1.5 + vec2(t * 0.03, -t * 0.02));
        float g = fbm(p * 4.2 - vec2(t * 0.05, 0.0));
        float smoke = smoothstep(0.38, 0.95, f) * (0.55 + 0.45 * g);
        float vign = exp(-r * r * 0.3);
        vec3 col = vec3(0.016, 0.040, 0.085) * vign + vec3(0.045, 0.090, 0.160) * smoke * (0.5 + 0.5 * r);
        col += vec3(0.05, 0.10, 0.19) * smoothstep(0.86, 0.70, r) * (0.6 + 0.4 * smoke);
        gl_FragColor = vec4(col, 1.0); }}"""
    src = {"trk2": (trk_v, trk_f), "twr2": (twr_v, twr_f), "shell2": (shell_v, shell_f), "flash2": (flash_v, flash_f), "haze2": (haze_v, haze_f)}
    if look == "v3":
        src = _v3_sources(src)
    return {n: (glsl(v), glsl(f)) for n, (v, f) in src.items()}


# LOOK V3 (2026-11-06): look v2 folded together with the best of an outside fidelity pass made on the published demo page
# (docs/COLLIDER-LOOK-V3.md lists what was taken, what was left and why). Same geometry, same attributes, same shader
# names and the same clock as v2, so the witness reads a v3 scene exactly as it reads v2. Taken from the outside pass:
# tighter ribbon cores with a soft edge and a resolution scale (u_resolutionScale, 1 = 900 rows), the machined shell
# (panel seams, ribs, readout traces, key-light glints, a lit lip), the sharper flash with a shock ring, the haze
# structure (rotated fbm, two light shafts). Kept from v2 against the outside pass: the haze level (the target's
# mid-tones are brighter than v2, so the outside pass's 6x darker haze moved away from it) and the vertex sparks.
# New in v3: a red end on the crown's energy ramp (red was 0.3% against the target's 7.5% in look v2).
def _v3_sources(src: dict) -> dict:
    cyc, t0, rip = flt(CYCLE_S), flt(FLASH_AT), flt(RIPPLE)
    fade = _fade()
    out = dict(src)
    tv, tf = src["trk2"]
    def res(v: str) -> str:
        assert v.count("uniform float u_phase;") == 1 and v.count("a_look.x * w;") == 1
        return v.replace("uniform float u_phase;", "uniform float u_phase; uniform float u_resolutionScale;").replace("a_look.x * w;", "a_look.x * w * u_resolutionScale;")
    for a, b in (("vec3 c = vec3(0.10, 0.92, 1.0);", "vec3 c = vec3(0.08, 0.78, 1.0);"),
                 ("c = vec3(1.0, 0.14, 0.72);", "c = vec3(1.0, 0.12, 0.51);"),
                 ("float core = exp(-v * v * 9.0);", "float core = exp(-v * v * 18.0);"),
                 ("float halo = exp(-v * v * 2.2);", "float halo = exp(-v * v * 3.6) * (1.0 - smoothstep(0.7, 1.0, abs(v)));"),
                 ("float gain = (0.28 + 1.35 * bright)", "float gain = (0.34 + 1.65 * bright)"),
                 ("vec3 col = c * (halo * 0.34 + core * 0.9) * gain;", "vec3 col = c * (halo * 0.33 + core * 1.28) * gain;")):
        assert tf.count(a) == 1, a
        tf = tf.replace(a, b)
    out["trk2"] = (res(tv), tf)
    wv, wf = src["twr2"]
    a = "vec3 c = mix(heat, vec3(1.0, 0.78, 0.30), 0.35 * v_cell.z);"
    assert wf.count(a) == 1
    wf = wf.replace(a, a + " c = mix(c, vec3(1.0, 0.20, 0.07), smoothstep(0.80, 1.0, eh) * (1.0 - 0.5 * v_cell.z));")
    out["twr2"] = (res(wv), wf)
    shell_f = f"""precision highp float; uniform float u_phase;
      varying vec3 v_n; varying vec3 v_p; varying vec3 v_obj; varying vec4 v_shell; varying vec4 v_geo;
      float stripe(float x, float wd) {{ float d = abs(fract(x) - 0.5); return 1.0 - smoothstep(wd, wd + 0.04, d); }}
      void main() {{
        float t = u_phase * {cyc};
        float kind = v_shell.x;
        float b = v_shell.w;
        float radius = max(v_geo.x, 0.04);
        float hl = max(v_geo.y, 0.02);
        float z = v_obj.z;
        float phi = atan(v_obj.y, v_obj.x);
        vec3 N = normalize(v_n);
        vec3 V = normalize(-v_p);
        if (dot(N, V) < 0.0) {{ N = -N; }}
        float facing = max(dot(N, V), 0.0);
        float rim = pow(1.0 - facing, 3.5);
        float calo = step(0.5, kind) * (1.0 - step(1.5, kind));
        float steel = step(1.5, kind) * (1.0 - step(2.5, kind));
        float tracker = 1.0 - step(0.5, kind);
        float ring = step(2.5, kind);
        vec3 cold = mix(vec3(0.18, 0.44, 0.67), vec3(0.21, 0.59, 0.78), tracker);
        cold = mix(cold, vec3(0.17, 0.26, 0.39), steel);
        cold = mix(cold, vec3(0.22, 0.42, 0.61), ring);
        vec3 cyan = vec3(0.39, 0.84, 1.0);
        vec3 warm = vec3(1.0, 0.50, 0.16);
        float sectors = max(v_geo.z, mix(48.0, 24.0, steel));
        float u = phi / 6.2831853 * sectors;
        float panel = floor(u);
        float alt = 0.72 + 0.28 * sin(panel * 2.39996 + floor(z * 2.0) * 1.7);
        float seam = stripe(u, 0.012);
        float ribs = stripe(z * v_shell.y / 3.14159265, 0.032);
        float fine = stripe(z * v_shell.y * 2.0 / 3.14159265, 0.012);
        float lip = exp(-max(hl - abs(z), 0.0) * 24.0);
        float band = max(exp(-max(hl - abs(z) - 0.075, 0.0) * 48.0) - lip, 0.0);
        vec3 key = normalize(vec3(-0.55, 0.65, 0.50));
        vec3 fill = normalize(vec3(0.72, -0.22, 0.50));
        float diffuse = max(dot(N, key), 0.0);
        float glint = pow(max(dot(N, normalize(key + V)), 0.0), 76.0);
        float broad = pow(max(dot(N, normalize(fill + V)), 0.0), 15.0);
        float brush = 0.85 + 0.15 * sin(z * 35.0 + sin(phi * 8.0) * 0.9);
        vec3 col = cold * b * alt * (0.026 + 0.035 * diffuse + 0.19 * rim);
        col += cold * b * ribs * (0.12 + 0.25 * rim) * (1.0 - 0.45 * steel);
        col += cyan * b * fine * (0.035 + 0.07 * rim);
        col += cold * b * seam * (0.13 + 0.19 * rim);
        col += vec3(0.65, 0.79, 0.86) * b * (0.16 * glint * brush + 0.045 * broad);
        col += cyan * b * lip * (0.45 + 0.65 * rim) * (1.0 - 0.45 * steel);
        col += warm * b * band * (0.12 + 0.25 * calo);
        float trace = stripe(u * 0.25 + 0.12, 0.009);
        float marks = stripe(z * 3.0 + 0.25, 0.045) * stripe(u, 0.09);
        col += cyan * b * trace * (0.08 + 0.22 * rim) * (1.0 - steel);
        col += cyan * b * marks * 0.19;
        col += warm * v_shell.z * smoothstep(2.0, 3.6, t) * (0.025 + 0.32 * rim * rim + 0.09 * seam);
        float front = (t - {t0}) * {rip};
        col += cyan * exp(-pow((front - radius) * 3.1, 2.0)) * step({t0}, t) * b * (0.20 + 0.40 * rim);
        col = vec3(1.0) - exp(-col * 1.32);
        gl_FragColor = vec4(col * (0.42 + 0.58 * {fade}), 1.0); }}"""
    out["shell2"] = (src["shell2"][0], shell_f)
    flash_f = f"""precision highp float; uniform float u_phase; varying vec2 v_uv;
      void main() {{
        float t = u_phase * {cyc};
        float s = t - {t0};
        float birth = step(0.0, s);
        float bang = exp(-max(s, 0.0) * 4.2) * birth;
        float after = exp(-max(s, 0.0) * 1.05) * birth;
        vec2 p = v_uv;
        float r = length(p);
        float edge = 1.0 - smoothstep(0.78, 1.0, r);
        float core = exp(-r * r * 170.0);
        float aura = exp(-r * r * 17.0);
        float hor = exp(-abs(p.y) * 155.0) * exp(-abs(p.x) * 2.5);
        float sho = exp(-abs(p.y) * 44.0) * exp(-abs(p.x) * 5.5);
        float ver = exp(-abs(p.x) * 170.0) * exp(-abs(p.y) * 6.0);
        float dg = exp(-abs(p.x - p.y) * 145.0) * exp(-abs(p.x + p.y) * 6.0) + exp(-abs(p.x + p.y) * 145.0) * exp(-abs(p.x - p.y) * 6.0);
        float wave = exp(-pow((r - max(s, 0.0) * 1.65) * 85.0, 2.0)) * exp(-max(s, 0.0) * 4.0) * birth;
        float steady = smoothstep(0.0, 0.5, t) * 0.12;
        vec3 col = vec3(0.76, 0.91, 1.0) * (core * (steady + bang * 3.5) + aura * (steady * 0.16 + after * 0.45));
        col += vec3(0.38, 0.73, 1.0) * (hor * 0.75 + sho * 0.20) * (steady + bang * 1.7);
        col += vec3(0.86, 0.87, 1.0) * (ver * 0.34 + dg * 0.13) * (steady + bang);
        col += vec3(0.33, 0.69, 1.0) * wave * 0.38;
        col += vec3(1.0, 0.65, 0.28) * exp(-r * r * 48.0) * bang * 0.50;
        col = vec3(1.0) - exp(-col * 1.35);
        gl_FragColor = vec4(col * edge * (1.0 - smoothstep({flt(CYCLE_S - 1.6)}, {flt(CYCLE_S - 0.1)}, t)), 1.0); }}"""
    out["flash2"] = (src["flash2"][0], flash_f)
    haze_f = f"""precision highp float; uniform float u_phase; varying vec2 v_uv;
      float h(vec2 p) {{ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }}
      float n(vec2 p) {{
        vec2 i = floor(p);
        vec2 f = fract(p);
        f = f * f * (3.0 - 2.0 * f);
        return mix(mix(h(i), h(i + vec2(1.0, 0.0)), f.x), mix(h(i + vec2(0.0, 1.0)), h(i + vec2(1.0, 1.0)), f.x), f.y); }}
      float fbm(vec2 p) {{
        float a = 0.5;
        float s = 0.0;
        for (int i = 0; i < 4; i++) {{ s += a * n(p); p = mat2(1.61, 1.21, -1.21, 1.61) * p + vec2(3.1, 7.2); a *= 0.48; }}
        return s; }}
      void main() {{
        float t = u_phase * {cyc};
        vec2 p = v_uv * vec2(1.7777778, 1.0);
        float r = length(p);
        vec2 drift = vec2(t * 0.012, -t * 0.008);
        float f = fbm(p * 2.1 + drift);
        float g = fbm(p * 5.3 - drift * 1.8);
        float mist = smoothstep(0.42, 0.86, f) * (0.35 + 0.65 * g);
        float centre = exp(-dot(p, p) * 0.7);
        float halo = exp(-pow((r - 0.82) * 2.5, 2.0));
        vec3 col = vec3(0.010, 0.024, 0.050) * (0.45 + 0.55 * centre);
        col += vec3(0.034, 0.068, 0.118) * mist * (0.35 + 0.65 * halo);
        col += vec3(0.036, 0.072, 0.135) * smoothstep(0.86, 0.70, r) * (0.6 + 0.4 * mist);
        float cold = exp(-pow(p.y + p.x * 0.14 - 0.15, 2.0) * 12.0) * exp(-pow(p.x + 0.65, 2.0) * 1.9);
        float warm = exp(-pow(p.y - p.x * 0.32 + 0.30, 2.0) * 9.0) * exp(-pow(p.x - 1.0, 2.0) * 2.6);
        col += vec3(0.024, 0.068, 0.108) * cold * (0.35 + 0.65 * mist);
        col += vec3(0.060, 0.030, 0.012) * warm * (0.35 + 0.65 * mist);
        gl_FragColor = vec4(col, 1.0); }}"""
    out["haze2"] = (src["haze2"][0], haze_f)
    return out


def bloom_shaders_v3() -> tuple[str, str]:
    """Look v3 bloom (from the outside pass): an edge-aware 5-tap smooth of thin bright lines, a tight and a wide ring of
    taps, a faint horizontal streak, then exposure, a soft shoulder above 0.72, a 0.94 gamma lift and a vignette."""
    v = bloom_shaders()[0]
    f = """precision highp float; uniform sampler2D u_tex; uniform vec2 u_px; uniform float u_gain; uniform float u_thr; uniform float u_sigma; uniform float u_exposure;
      varying vec2 v_uv;
      float lum(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }
      vec3 bright(vec3 c) { float l = lum(c); float k = max(l - u_thr + 0.15, 0.0); return c * (k * k / (k + 0.20)) / max(l, 0.001); }
      void main() {
        vec3 c = texture2D(u_tex, v_uv).rgb;
        vec3 n = texture2D(u_tex, v_uv + vec2(0.0, u_px.y)).rgb;
        vec3 s = texture2D(u_tex, v_uv - vec2(0.0, u_px.y)).rgb;
        vec3 e = texture2D(u_tex, v_uv + vec2(u_px.x, 0.0)).rgb;
        vec3 w = texture2D(u_tex, v_uv - vec2(u_px.x, 0.0)).rgb;
        float l = lum(c);
        float hi = max(l, max(max(lum(n), lum(s)), max(lum(e), lum(w))));
        float lo = min(l, min(min(lum(n), lum(s)), min(lum(e), lum(w))));
        c = mix(c, (c * 4.0 + n + s + e + w) / 8.0, smoothstep(0.08, 0.5, hi - lo) * 0.26);
        vec3 tight = vec3(0.0);
        vec3 wide = vec3(0.0);
        for (int i = 0; i < 12; i++) {
          float a = 6.2831853 * (float(i) + 0.5) / 12.0;
          vec2 d = vec2(cos(a), sin(a)) * u_px * u_sigma;
          tight += bright(texture2D(u_tex, v_uv + d * 0.28).rgb);
          wide += bright(texture2D(u_tex, v_uv + d).rgb);
          wide += bright(texture2D(u_tex, v_uv + d * 2.5).rgb) * 0.36; }
        vec3 glow = tight / 12.0 * 0.85 + wide / 16.32 * 0.70;
        vec3 streak = vec3(0.0);
        for (int i = 1; i < 5; i++) {
          vec2 d = vec2(u_px.x * u_sigma * float(i) * 1.8, 0.0);
          streak += (bright(texture2D(u_tex, v_uv + d).rgb) + bright(texture2D(u_tex, v_uv - d).rgb)) / float(i + 1); }
        vec3 col = (c + (glow * 1.5 + streak * 0.08) * u_gain) * u_exposure;
        float peak = max(col.r, max(col.g, col.b));
        col /= 1.0 + max(peak - 0.72, 0.0) * 0.48;
        col = pow(max(col, 0.0), vec3(0.94));
        vec2 p = v_uv * 2.0 - 1.0;
        col *= 1.0 - 0.22 * smoothstep(0.3, 1.5, length(p));
        gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0); }"""
    return v, glsl(f)


def bloom_shaders() -> tuple[str, str]:
    """Full-screen threshold blur over the RenderedTexture of the whole scene (screen blend, so highlights never dim)."""
    v = """precision highp float; attribute vec4 x3d_Vertex; varying vec2 v_uv;
      void main() { v_uv = x3d_Vertex.xy * 0.5 + 0.5; gl_Position = vec4(x3d_Vertex.xy, 0.0, 1.0); }"""
    f = """precision highp float; uniform sampler2D u_tex; uniform vec2 u_px; uniform float u_gain; uniform float u_thr; uniform float u_sigma;
      varying vec2 v_uv;
      void main() {
        vec3 c = texture2D(u_tex, v_uv).rgb;
        vec3 b = vec3(0.0);
        float ws = 0.0;
        for (float r = 1.0; r < 6.5; r += 1.0) {
          float rad = u_sigma * r / 3.0;
          float w = exp(-r * r / 4.5);
          for (float k = 0.0; k < 11.5; k += 1.0) {
            float a = 6.2831853 * (k + 0.5 * r) / 12.0;
            vec3 s = texture2D(u_tex, v_uv + vec2(cos(a), sin(a)) * rad * u_px).rgb;
            float l = dot(s, vec3(0.2126, 0.7152, 0.0722));
            float kn = max(l - u_thr, 0.0);
            b += s * (kn * kn / (kn + 0.25)) / max(l, 0.001) * w;
            ws += w; } }
        b = b / ws;
        vec3 col = c + (vec3(1.0) - c) * (vec3(1.0) - exp(-b * u_gain * 12.0));
        gl_FragColor = vec4(col, 1.0); }"""
    return glsl(v), glsl(f)


def shader_node_v2(name: str, vsrc: str, fsrc: str, extra: str = "") -> str:
    return (f"<ComposedShader DEF='{name}' language='GLSL'>"
            f"<field name='u_phase' type='SFFloat' accessType='inputOutput' value='0'/>{extra}"
            f"<ShaderPart type='VERTEX' url='\"data:x-shader/x-vertex,{esc(vsrc)}\"'/>"
            f"<ShaderPart type='FRAGMENT' url='\"data:x-shader/x-fragment,{esc(fsrc)}\"'/></ComposedShader>")


def _p3(q) -> str:
    return f"{fmt(q[0])} {fmt(q[1])} {fmt(q[2])}"


class _Strips:
    """A TriangleStripSet being filled with ribbons: one strip per path, a vertex pair per centreline point."""

    def __init__(self, attrs: list[tuple[str, int]]):
        self.counts: list[int] = []
        self.coords: list[str] = []
        self.attrs = {n: (nc, []) for n, nc in attrs}

    def add(self, centre: list, nxt: list, rows: dict[str, list]):
        """centre[i] is the drawn point, nxt[i] the point its screen direction aims at; rows[name][i] the attribute
        row of centre point i (a_look's first component, the side, is written here)."""
        self.counts.append(2 * len(centre))
        for i, c in enumerate(centre):
            for side in (-1, 1):
                self.coords.append(_p3((c[0] + side * OFF[0], c[1] + side * OFF[1], c[2] + side * OFF[2])))
                for n, (nc, out) in self.attrs.items():
                    if n == "a_next":
                        out.append(_p3(nxt[i]))
                    elif n == "a_look":
                        out.append(f"{side} {rows[n][i]}")
                    else:
                        out.append(rows[n][i])

    def xml(self) -> str:
        fva = "".join(f"<FloatVertexAttribute name='{n}' numComponents='{nc}' value='{' '.join(v)}'/>" for n, (nc, v) in self.attrs.items())
        return (f"<TriangleStripSet solid='false' stripCount='{' '.join(map(str, self.counts))}'>"
                f"<Coordinate point='{' '.join(self.coords)}'/>{fva}</TriangleStripSet>")

    def vertices(self) -> int:
        return sum(self.counts)


def _forward(pts: list) -> list:
    """The point each centreline point aims at: the next one, and past the end the last step repeated."""
    if len(pts) < 2:
        return [(p[0] + 1e-3, p[1], p[2]) for p in pts]
    out = list(pts[1:])
    a, b = pts[-2], pts[-1]
    out.append((2 * b[0] - a[0], 2 * b[1] - a[1], 2 * b[2] - a[2]))
    return out


def muon_extension(pts: list, arcs: list, det: dict):
    """Straight continuation of a muon from where it leaves the tracker, along its exit tangent, out to MU_R_OUT or
    MU_Z_OUT. None when the drawn path ends inside the tracker (a looper that never leaves) or points back inward."""
    tr = det["tracker"]
    end, prev = pts[-1], pts[-2]
    out_r = math.hypot(end[0], end[1]) >= tr["r_max_m"] - 2e-3
    out_z = abs(end[2]) >= tr["half_length_m"] - 2e-3
    if not (out_r or out_z):
        return None
    d = [end[i] - prev[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in d))
    if n == 0:
        return None
    d = [c / n for c in d]
    if out_r and end[0] * d[0] + end[1] * d[1] <= 0:
        return None
    # largest s with r <= MU_R_OUT and |z| <= MU_Z_OUT
    a = d[0] ** 2 + d[1] ** 2
    s_r = math.inf
    if a > 1e-12:
        bq = end[0] * d[0] + end[1] * d[1]
        cq = end[0] ** 2 + end[1] ** 2 - MU_R_OUT ** 2
        s_r = (-bq + math.sqrt(max(bq * bq - a * cq, 0.0))) / a
    s_z = (MU_Z_OUT - abs(end[2])) / abs(d[2]) if abs(d[2]) > 1e-12 else math.inf
    s_max = min(s_r, s_z) * 0.995
    if not (0 < s_max < math.inf):
        return None
    m = 18
    ext = [(end[0] + d[0] * s_max * i / (m - 1), end[1] + d[1] * s_max * i / (m - 1), end[2] + d[2] * s_max * i / (m - 1)) for i in range(m)]
    return ext, [arcs[-1] + s_max * i / (m - 1) for i in range(m)]


def tower_spikes(x: dict, ca: dict, e90: float = 15.0) -> list[tuple]:
    """Thin radial needles spread over one tower's own (eta, phi) cell: (base, tip, seed, length) each. Count and length
    come from the tower's energy (length relative to the event's 90th percentile tower e90); phi is stratified over the
    whole cell with a small jitter, so neighbouring cells join into one comb instead of wedges. The scatter is a fixed
    hash of the tower id, so the build is deterministic, and every needle stays inside its cell (the witness checks)."""
    rnd = random.Random(x["i"] * 7919 + 13)
    e = x["E"]
    r0 = ca["r_min_m"]
    n = min(24, 6 + int(round(5.0 * math.sqrt(max(e, 0.0)))))
    full = 0.06 + 0.42 * min(1.0, math.log(1.0 + e) / math.log(1.0 + max(e90, 0.05)))
    dph, deta = 2 * math.pi / 72, 0.0873
    out = []
    for j in range(n):
        ph = x["phi"] + ((j + 0.5) / n - 0.5) * dph + rnd.uniform(-0.25, 0.25) * dph / n
        eta = x["eta"] + rnd.uniform(-0.45, 0.45) * deta
        z = max(-ca["half_length_m"] + 0.005, min(ca["half_length_m"] - 0.005, r0 * math.sinh(eta)))
        ln = full * (0.35 + 0.65 * rnd.random())
        cp, sp = math.cos(ph), math.sin(ph)
        out.append(((r0 * cp, r0 * sp, z), ((r0 + ln) * cp, (r0 + ln) * sp, z), round(rnd.random(), 3), ln))
    return out


def _cyl(r: float, hl: float, nseg: int, row_attr: str, geo: str, pts: list, nrm: list, idx: list, sh: list, gm: list, flat=False):
    """An open cylinder along z: smooth radial normals (flat facet normals when flat), two vertex rows."""
    base = len(pts)
    if not flat:
        for i in range(nseg):
            a = 2 * math.pi * i / nseg
            c, s = math.cos(a), math.sin(a)
            for z in (-hl, hl):
                pts.append((r * c, r * s, z))
                nrm.append((c, s, 0.0))
                sh.append(row_attr)
                gm.append(geo)
        for i in range(nseg):
            a, b = base + 2 * i, base + 2 * ((i + 1) % nseg)
            idx.extend([a, b, a + 1, a + 1, b, b + 1])
        return
    for i in range(nseg):
        a0, a1 = 2 * math.pi * i / nseg, 2 * math.pi * (i + 1) / nseg
        am = 0.5 * (a0 + a1)
        nn = (math.cos(am), math.sin(am), 0.0)
        k = len(pts)
        for a in (a0, a1):
            for z in (-hl, hl):
                pts.append((r * math.cos(a), r * math.sin(a), z))
                nrm.append(nn)
                sh.append(row_attr)
                gm.append(geo)
        idx.extend([k, k + 2, k + 1, k + 1, k + 2, k + 3])


def _box(corners: list, row_attr: str, geo: str, pts: list, nrm: list, idx: list, sh: list, gm: list):
    """Six flat-shaded quads of a hexahedron given its 8 corners (x-, x+ alternating fastest, then y, then z)."""
    faces = ((0, 2, 6, 4), (1, 5, 7, 3), (0, 4, 5, 1), (2, 3, 7, 6), (0, 1, 3, 2), (4, 6, 7, 5))
    cx = [sum(c[i] for c in corners) / 8 for i in range(3)]
    for f in faces:
        q = [corners[j] for j in f]
        u = [q[1][i] - q[0][i] for i in range(3)]
        v = [q[2][i] - q[0][i] for i in range(3)]
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        fc = [sum(p[i] for p in q) / 4 for i in range(3)]
        if sum(n[i] * (fc[i] - cx[i]) for i in range(3)) < 0:
            n = [-c for c in n]
        ln = math.sqrt(sum(c * c for c in n)) or 1.0
        n = [c / ln for c in n]
        k = len(pts)
        for p in q:
            pts.append(p)
            nrm.append(n)
            sh.append(row_attr)
            gm.append(geo)
        idx.extend([k, k + 1, k + 2, k, k + 2, k + 3])


def _its(pts, nrm, idx, sh, gm) -> str:
    return (f"<IndexedTriangleSet solid='false' index='{' '.join(map(str, idx))}'><Coordinate point='{' '.join(_p3(p) for p in pts)}'/>"
            f"<Normal vector='{' '.join(f'{fmt(n[0], 3)} {fmt(n[1], 3)} {fmt(n[2], 3)}' for n in nrm)}'/>"
            f"<FloatVertexAttribute name='a_shell' numComponents='4' value='{' '.join(sh)}'/>"
            f"<FloatVertexAttribute name='a_geo' numComponents='4' value='{' '.join(gm)}'/></IndexedTriangleSet>")


ADD_APP = ("<BlendMode DEF='add' sourceColorFactor='ONE' destinationColorFactor='ONE' sourceAlphaFactor='ONE' destinationAlphaFactor='ONE'/>"
           "<DepthMode DEF='nodepth' depthMask='false'/>")
ADD_USE = "<BlendMode USE='add'/><DepthMode USE='nodepth'/>"


def build_v2(ev: dict, event_sha256: str, cycle: float = CYCLE_S, max_turns: float = 2.5, sparks: int = 160, look: str = "v2") -> tuple[str, dict]:
    det = ev["detector"]
    tr, ca = det["tracker"], det["calorimeter"]
    sh = shaders_v2(look)
    out: list[str] = []
    w = out.append
    title = esc("Collider event " + str(ev.get("id", "")))
    w("<?xml version='1.0' encoding='UTF-8'?>")
    w("<X3D profile='Immersive' version='4.0' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' "
      "xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.0.xsd'>")
    w("<head>")
    for comp, lvl in (("Shaders", 3), ("Rendering", 3), ("ParticleSystems", 2), ("X_ITE", 1)):
        w(f"<component name='{comp}' level='{lvl}'/>")
    w(f"<meta name='title' content='{title}'/>")
    if look == "v3":
        w("<meta name='description' content='One generated collider event, look v3: resolution-scaled ribbon tracks in merged strips, a calorimeter crown from the real tower energies with a red hot end, machined glass shells, a flash with a shock ring, lit haze and sparks.'/>")
    else:
        w("<meta name='description' content='One generated collider event, look v2: screen-space ribbon tracks in merged strips, a spiky calorimeter crown from the real tower energies, Fresnel shells, flash, haze and sparks.'/>")
    w(f"<meta name='generator' content='kit/examples/hep/build_event_scene.py --look {look}'/>")
    w(f"<meta name='event-id' content='{esc(str(ev.get('id', '')))}'/>")
    w(f"<meta name='event-sha256' content='{event_sha256}'/>")
    w(f"<meta name='slow-motion' content='track heads advance at {SPEED} m/s; light moves 2.998e8 m/s'/>")
    w("<meta name='units' content='metres, GeV, tesla; z is the beam axis'/>")
    w("<meta name='colour' content='tracks: + hadron cyan, - hadron magenta, electron emerald, muon violet-white, proton coral, photon orange dashed, neutral hadron gold dashed; brightness and width = pT. towers: hue = energy relative to this event (blue low, amber at its 90th percentile tower energy u_e90), EM-rich towers shifted toward gold; needle length = energy'/>")
    w("<meta name='license' content='MIT'/>")
    w("</head>")
    w("<Scene>")
    w(f"<WorldInfo title='{title}' info='\"Generated; edit kit/examples/hep/build_event_scene.py, never this file\"'/>")
    w("<NavigationInfo type='\"EXAMINE\" \"ANY\"' headlight='false'/>")
    w("<Background skyAngle='1.2 1.5708' skyColor='0.004 0.010 0.022 0.003 0.008 0.018 0.002 0.004 0.010' "
      "groundAngle='1.5708' groundColor='0.002 0.004 0.010 0.001 0.002 0.006'/>")
    for _key, (name, desc, eye, fov) in V2_VIEWS.items():
        o = look_at(eye) if eye[0] or eye[1] else (0.0, 0.0, 1.0, 0.0)
        w(f"<Viewpoint DEF='{name}' description='{desc}' position='{fmt(eye[0], 3)} {fmt(eye[1], 3)} {fmt(eye[2], 3)}' "
          f"orientation='{fmt(o[0], 5)} {fmt(o[1], 5)} {fmt(o[2], 5)} {fmt(o[3], 5)}' fieldOfView='{fov:g}' centerOfRotation='0 0 0'/>")
    w(f"<TimeSensor DEF='clock' cycleInterval='{cycle:g}' loop='true'/>")
    names = {"trk2": "trkShader2", "twr2": "twrShader2", "shell2": "shellShader2", "flash2": "flashShader2", "haze2": "hazeShader2"}
    w("<Switch DEF='shader_defs' whichChoice='-1'><Shape><Appearance>")
    es = sorted(x["E"] for x in ev.get("towers", []))
    e90 = es[min(len(es) - 1, int(0.9 * len(es)))] if es else 1.0     # the event's own 90th percentile tower energy
    for key, nm in names.items():
        extra = f"<field name='u_e90' type='SFFloat' accessType='inputOutput' value='{sig(e90)}'/>" if key == "twr2" else ""
        if look == "v3" and key in ("trk2", "twr2"):
            extra += "<field name='u_resolutionScale' type='SFFloat' accessType='inputOutput' value='1'/>"
        w(shader_node_v2(nm, *sh[key], extra))
    w(ADD_APP)
    w("</Appearance></Shape></Switch>")

    # --- haze: a screen-space quad (its shader ignores the camera); the bounding box sits at the origin, always in view
    w("<Shape DEF='haze'><Appearance>" + ADD_USE + "<ComposedShader USE='hazeShader2'/></Appearance>"
      "<IndexedFaceSet solid='false' coordIndex='0 1 2 3 -1'><Coordinate point='-1 -1 0 1 -1 0 1 1 0 -1 1 0'/></IndexedFaceSet></Shape>")

    # --- detector: glass shells, the calorimeter face glowing where the towers are, muon stations and struts in steel
    towers = ev.get("towers", [])
    nseg = 240
    glow = [0.0] * nseg
    for x in towers:
        for i in range(nseg):
            a = -math.pi + 2 * math.pi * i / nseg
            dphi = (a - x["phi"] + math.pi) % (2 * math.pi) - math.pi
            glow[i] += x["E"] * math.exp(-(dphi / 0.05) ** 2)
    glow = [min(1.0, math.log(1.0 + g) / math.log(16.0)) for g in glow]
    pts, nrm, idx, sha, gma = [], [], [], [], []
    for r in tr.get("layer_radii_m", []):
        hl = tr["half_length_m"] * (0.25 if r < 0.2 else 1.0)
        _cyl(r, hl, 96, f"3 {flt(5.0)} 0 {fmt(0.22 if r < 0.2 else 0.3, 2)}", f"{fmt(r)} {fmt(hl)} 0 0", pts, nrm, idx, sha, gma)
    _cyl(tr["r_max_m"], tr["half_length_m"], 192, "0 6 0 0.6", f"{fmt(tr['r_max_m'])} {fmt(tr['half_length_m'])} 24 0", pts, nrm, idx, sha, gma)
    # hairline glass: short rings that read as layered glass end-on and fill the barrel up to the calorimeter face
    for r_h, b_h in ((0.15, 0.12), (0.2, 0.12), (0.33, 0.14), (0.5, 0.14), (0.7, 0.16), (0.9, 0.16), (1.05, 0.18), (1.15, 0.18), (1.21, 0.2), (1.26, 0.2)):
        _cyl(r_h, 0.05, 192, f"3 {flt(5.0)} 0 {fmt(b_h, 2)}", f"{fmt(r_h)} 0.05 0 0", pts, nrm, idx, sha, gma)
    # calorimeter face: one column of vertices per glow sample, so the energy glow follows phi
    base = len(pts)
    r, hl = ca["r_min_m"], ca["half_length_m"]
    for i in range(nseg):
        a = -math.pi + 2 * math.pi * i / nseg
        c, s = math.cos(a), math.sin(a)
        for z in (-hl, hl):
            pts.append((r * c, r * s, z))
            nrm.append((c, s, 0.0))
            sha.append(f"1 4 {fmt(glow[i], 3)} 0.5")
            gma.append(f"{fmt(r)} {fmt(hl)} 72 0")
    for i in range(nseg):
        a, b = base + 2 * i, base + 2 * ((i + 1) % nseg)
        idx.extend([a, b, a + 1, a + 1, b, b + 1])
    _cyl(ca["r_max_m"], ca["half_length_m"], 192, "0 3 0 0.35", f"{fmt(ca['r_max_m'])} {fmt(ca['half_length_m'])} 48 0", pts, nrm, idx, sha, gma)
    w("<Group DEF='detector'>")
    w("<Shape DEF='shells'><Appearance>" + ADD_USE + "<ComposedShader USE='shellShader2'/></Appearance>" + _its(pts, nrm, idx, sha, gma) + "</Shape>")
    pts, nrm, idx, sha, gma = [], [], [], [], []
    for (r_in, r_out), off_a in zip(STATIONS, (0.0, math.pi / 12)):
        for j in range(12):
            a0 = off_a + 2 * math.pi * j / 12 + 0.035
            a1 = off_a + 2 * math.pi * (j + 1) / 12 - 0.035
            cs = [(rr * math.cos(a), rr * math.sin(a), z) for z in (-STATION_HALF, STATION_HALF) for rr in (r_in, r_out) for a in (a0, a1)]
            # order: x-/x+ fastest (a0, a1), then y (r_in, r_out), then z
            _box(cs, "2 2 0 0.4", f"{fmt(r_out)} {fmt(STATION_HALF)} 0 0", pts, nrm, idx, sha, gma)
    for j in range(12):
        a = 2 * math.pi * (j + 0.5) / 12
        ca_, sa_ = math.cos(a), math.sin(a)
        half_w = 0.03
        cs = []
        for z in (-STATION_HALF, STATION_HALF):
            for rr in (ca["r_max_m"] + 0.08, STATIONS[-1][1] + 0.25):
                for sgn in (-1, 1):
                    cs.append((rr * ca_ - sgn * half_w * sa_, rr * sa_ + sgn * half_w * ca_, z))
        _box(cs, "2 2 0 0.3", f"{fmt(STATIONS[-1][1] + 0.25)} {fmt(STATION_HALF)} 0 0", pts, nrm, idx, sha, gma)
    w("<Shape DEF='muon_stations'><Appearance>" + ADD_USE + "<ComposedShader USE='shellShader2'/></Appearance>" + _its(pts, nrm, idx, sha, gma) + "</Shape>")
    w("<Billboard DEF='flash' axisOfRotation='0 0 0'><Transform scale='1.1 1.1 1'><Shape><Appearance>" + ADD_USE +
      "<ComposedShader USE='flashShader2'/></Appearance><IndexedFaceSet solid='false' coordIndex='0 1 2 3 -1'>"
      "<Coordinate point='-1 -1 0 1 -1 0 1 1 0 -1 1 0'/></IndexedFaceSet></Shape></Transform></Billboard>")
    if sparks:
        # decoration, not event particles: neutral white-blue (no species colour), short-lived, so they stay near the vertex
        w(f"<ParticleSystem DEF='sparks' geometryType='LINE' maxParticles='{int(sparks)}' particleLifetime='0.45' lifetimeVariation='0.5' "
          "particleSize='0.05 0.05' colorKey='0 0.35 1'><Appearance>" + ADD_USE +
          "<Material diffuseColor='0 0 0' emissiveColor='0.75 0.88 1'/></Appearance>"
          "<ConeEmitter position='0 0 0' direction='0 0 1' angle='3.14159' speed='0.55' variation='0.7' mass='0' surfaceArea='0'/>"
          "<ColorRGBA containerField='color' color='0.85 0.93 1 1 0.3 0.5 0.9 0.6 0.1 0.15 0.35 0'/></ParticleSystem>")
    w("</Group>")

    # --- tracks (merged ribbons) and muon extensions
    tracks = ev.get("tracks", [])
    species_count: dict[str, int] = {}
    chunks: list[_Strips] = []
    mu = _Strips([("a_ident", 4), ("a_arc", 1), ("a_species", 1), ("a_next", 3), ("a_look", 4)])
    npoints = nmu = 0
    for n_t, t in enumerate(tracks):
        if n_t % TRK_CHUNK == 0:
            chunks.append(_Strips([("a_ident", 4), ("a_arc", 1), ("a_species", 1), ("a_next", 3), ("a_look", 4)]))
        k = t["i"]
        p = ev["particles"][t["particle"]]
        pts3, arcs = sample_track(t, det, max_turns, V2_DPHI)
        npoints += len(pts3)
        sp = species_of(p["pdg"], t["charge"])
        key = {v: n for n, v in SPECIES.items()}[sp]
        species_count[key] = species_count.get(key, 0) + 1
        b = birth_s(k, t.get("t_prod_ns", 0.0))
        ident_row = f"{k} {fmt(t['charge'], 3)} {sig(t['pt'])} {fmt(b)}"
        seed = fmt((k * 0.6180339887) % 1.0, 4)
        ext = muon_extension(pts3, arcs, det) if abs(p["pdg"]) == 13 and t["charge"] != 0 and len(pts3) >= 2 else None
        total = ext[1][-1] if ext else arcs[-1]
        kind = "0" if t["charge"] != 0 else "1"
        n = len(pts3)
        chunks[-1].add(pts3, _forward(pts3), {"a_ident": [ident_row] * n, "a_arc": [fmt(a) for a in arcs], "a_species": [fmt(sp, 1)] * n,
                                              "a_look": [f"{seed} {fmt(total, 3)} {kind}"] * n})
        if ext:
            e_pts, e_arcs = ext
            m = len(e_pts)
            mu.add(e_pts, _forward(e_pts), {"a_ident": [ident_row] * m, "a_arc": [fmt(a) for a in e_arcs], "a_species": [fmt(sp, 1)] * m,
                                            "a_look": [f"{seed} {fmt(total, 3)} 2"] * m})
            nmu += 1
    w("<Group DEF='tracks'>")
    for j, s in enumerate(chunks):
        w(f"<Shape DEF='trkset_{j}'><Appearance>{ADD_USE}<ComposedShader USE='trkShader2'/></Appearance>{s.xml()}</Shape>")
    if nmu:
        w(f"<Shape DEF='muext_0'><Appearance>{ADD_USE}<ComposedShader USE='trkShader2'/></Appearance>{mu.xml()}</Shape>")
    w("</Group>")

    # --- towers (merged spikes)
    tw = _Strips([("a_cell", 4), ("a_next", 3), ("a_look", 4)])
    nspikes = 0
    for x in towers:
        arrive = round(x.get("t_arr_ns", ca["r_min_m"] * math.cosh(x["eta"]) / C_M_PER_NS) * C_M_PER_NS / SPEED + FLASH_AT, 4)
        cell = f"{x['i']} {sig(x['E'])} {fmt(x.get('em_frac', 0.5), 3)} {fmt(arrive)}"
        for b0, tip, seed, ln in tower_spikes(x, ca, e90):
            beyond = (2 * tip[0] - b0[0], 2 * tip[1] - b0[1], 2 * tip[2] - b0[2])
            tw.add([b0, tip], [tip, beyond], {"a_cell": [cell, cell], "a_look": [f"{fmt(seed, 3)} 0 {fmt(ln, 3)}", f"{fmt(seed, 3)} 1 {fmt(ln, 3)}"]})
            nspikes += 1
    w("<Group DEF='towers'>")
    if towers:
        w(f"<Shape DEF='twrset_0'><Appearance>{ADD_USE}<ComposedShader USE='twrShader2'/></Appearance>{tw.xml()}</Shape>")
    w("</Group>")
    for nm in names.values():
        w(f"<ROUTE fromNode='clock' fromField='fraction_changed' toNode='{nm}' toField='u_phase'/>")
    w("</Scene></X3D>")
    text = "\n".join(out) + "\n"
    return text, {"look": look, "tracks": len(tracks), "track_points": npoints, "track_shapes": len(chunks), "track_vertices": sum(c.vertices() for c in chunks),
                  "muon_extensions": nmu, "towers": len(towers), "tower_spikes": nspikes, "species": species_count,
                  "bytes": len(text.encode()), "shader_nodes": len(names), "route_count": len(names)}


BLOOM_GAIN = {"endon": 0.55, "three_quarter": 0.22, "side": 0.22}   # the oblique views see the face wall and the glass broadside
BLOOM_GAIN_V3 = {"endon": 0.65, "three_quarter": 0.45, "side": 0.45}  # v3 adds the glow to the image instead of screening it


def bloom_wrapper(scene_text: str, view: str, w: int = 960, h: int = 540, gain: float | None = None, thr: float = 0.65, sigma: float = 11.0, look: str = "v2") -> str:
    """The un-bloomed scene inside a RenderedTexture, drawn by a full-screen threshold-blur shader (X3D 4.1; Texturing 4).
    X_ITE's RenderedTexture renders from the LAST Viewpoint among its children, so each view gets its own wrapper:
    the chosen Viewpoint is moved after the others. The ROUTEs move out of the texture, after every DEF."""
    name = V2_VIEWS[view][0]
    gain = BLOOM_GAIN[view] if gain is None else gain
    head = re.search(r"<head>(.*?)</head>", scene_text, re.S).group(1)
    body = re.search(r"<Scene>(.*)</Scene>", scene_text, re.S).group(1)
    routes = re.findall(r"<ROUTE [^>]*/>", body)
    body = re.sub(r"<ROUTE [^>]*/>\n?", "", body)
    vps = re.findall(r"<Viewpoint [^>]*/>\n?", body)
    chosen = next(v for v in vps if f"DEF='{name}'" in v)
    body = re.sub(r"<Viewpoint [^>]*/>\n?", "", body)
    body = body.replace("<TimeSensor ", "".join(v for v in vps if v is not chosen) + chosen + "<TimeSensor ", 1)
    head = head.replace("<component name='X_ITE' level='1'/>", "<component name='X_ITE' level='1'/>\n<component name='Texturing' level='4'/>")
    head = re.sub(r"<meta name='generator' content='[^']*'/>", f"<meta name='generator' content='kit/examples/hep/build_event_scene.py --look {look} --bloom (wrapper of the witnessed scene)'/>", head)
    v, f = bloom_shaders_v3() if look == "v3" else bloom_shaders()
    acc = "inputOutput" if look == "v3" else "initializeOnly"     # v3: the page tunes gain, exposure and size live
    if look == "v3" and gain is None:
        gain, thr = BLOOM_GAIN_V3[view], 0.42
    fld = lambda n, t, val: f"<field name='{n}' type='{t}' accessType='{acc}' value='{val}'/>"  # noqa: E731
    return ("<?xml version='1.0' encoding='UTF-8'?>\n<X3D profile='Immersive' version='4.1'>\n<head>" + head + "</head>\n<Scene>\n"
            "<NavigationInfo type='\"NONE\"' headlight='false'/>\n<Viewpoint DEF='vp_screen' description='screen' position='0 0 5'/>\n"
            "<Shape DEF='bloom'><Appearance><ComposedShader DEF='bloomShader' language='GLSL'>"
            f"<field name='u_tex' type='SFNode' accessType='inputOutput'><RenderedTexture DEF='scene_rt' width='{w}' height='{h}' "
            "singleFrame='false' updateInterval='0' repeatS='false' repeatT='false'>" + body + "</RenderedTexture></field>"
            + fld("u_px", "SFVec2f", f"{1.0 / w:.6g} {1.0 / h:.6g}") + fld("u_gain", "SFFloat", f"{gain:g}") + fld("u_thr", "SFFloat", f"{thr:g}")
            + fld("u_sigma", "SFFloat", f"{sigma:g}") + (fld("u_exposure", "SFFloat", "1.08") if look == "v3" else "")
            + f"<ShaderPart type='VERTEX' url='\"data:x-shader/x-vertex,{esc(v)}\"'/>"
            f"<ShaderPart type='FRAGMENT' url='\"data:x-shader/x-fragment,{esc(f)}\"'/></ComposedShader></Appearance>"
            "<IndexedFaceSet solid='false' coordIndex='0 1 2 3 -1'><Coordinate point='-1 -1 0 1 -1 0 1 1 0 -1 1 0'/></IndexedFaceSet></Shape>\n"
            + "\n".join(routes) + "\n</Scene></X3D>\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("event")
    ap.add_argument("outdir")
    ap.add_argument("--cycle", type=float, default=CYCLE_S)
    ap.add_argument("--max-turns", type=float, default=2.5)
    ap.add_argument("--labels", type=int, default=8)
    ap.add_argument("--look", choices=("v1", "v2", "v3"), default=None, help="v2: merged ribbons, spiky crown, glass shells; v3: v2 with the fidelity pass of docs/COLLIDER-LOOK-V3.md (default: v1, unchanged)")
    ap.add_argument("--bloom", action="store_true", help="v2 and v3: also write <stem>.bloom.<view>.x3d, the RenderedTexture bloom wrapper per view")
    ap.add_argument("--sparks", type=int, default=420, help="v2 and v3: ParticleSystem sparks at the vertex (0 for none)")
    a = ap.parse_args(argv)
    raw = Path(a.event).read_bytes()
    ev = json.loads(raw)
    stem = Path(a.event).name.split(".")[0]
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    if a.look in ("v2", "v3"):
        text, stats = build_v2(ev, hashlib.sha256(raw).hexdigest(), a.cycle, a.max_turns, a.sparks, a.look)
    else:
        if a.bloom:
            ap.error("--bloom needs --look v2 or v3")
        text, stats = build(ev, hashlib.sha256(raw).hexdigest(), a.cycle, a.max_turns, a.labels)
    (out / f"{stem}.x3d").write_text(text, encoding="utf-8")
    if a.bloom:
        for view in V2_VIEWS:
            (out / f"{stem}.bloom.{view}.x3d").write_text(bloom_wrapper(text, view, look=a.look), encoding="utf-8")
    ev["scene"] = f"{stem}.x3d"
    (out / f"{stem}.event.json").write_text(json.dumps(ev, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"scene": f"{stem}.x3d", **stats}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
