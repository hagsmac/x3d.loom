#!/usr/bin/env python3
"""Visual-fidelity scene generator (Python stdlib only; SYNTHETIC physics, seeded; authored look).

The physics is NOT meant to be accurate here (demo / proof of concept): helices use rho = pT / (0.3 B)
but nothing else is modelled. Every colour, width and glow constant below is AUTHORED (a design choice),
not measured.

    python3 gen_look.py hero OUT.x3d [--n 300] [--mode S1|S2|S3|S4] [--cam endon|persp|side]
                                     [--time 0.35] [--grow 1.0] [--anim 0|1] [--flash 1.0]
                                     [--towers 1] [--shells 1] [--haze 1] [--plain 0] [--width 1.6]
    python3 gen_look.py all OUTDIR          write every look scene used in research/feasibility.md

Modes (how the per-track shader is organised):
    S1  one TriangleStripSet holding all tracks, ONE ComposedShader (variation only through vertex attributes)
    S2  one Shape per track, ONE DEF'd Appearance (shader) shared by USE; variation through attributes
    S3  one Shape per track, one ComposedShader NODE per track, IDENTICAL source, per-track uniforms
    S4  one Shape per track, one ComposedShader per track, DISTINCT source text (constants baked in)
"""
import math, os, random, struct, sys, zlib

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evtcommon import B_FIELD, fmt, lookat, mat_to_axis_angle  # noqa: E402

PAL = {'cyan': (0.15, 0.85, 1.0), 'magenta': (1.0, 0.25, 0.85), 'amber': (1.0, 0.68, 0.16),
       'emerald': (0.2, 1.0, 0.5), 'violet': (0.6, 0.35, 1.0), 'ice': (0.75, 0.9, 1.0)}

# ---------------------------------------------------------------------------------------------- GLSL
VS_RIBBON = """#version 300 es
precision highp float;
precision highp int;
uniform mat4 x3d_ProjectionMatrix;
uniform mat4 x3d_ModelViewMatrix;
uniform ivec4 x3d_Viewport;
uniform float uWidth;
in vec4 x3d_Vertex;
in vec4 x3d_Color;
in vec4 aNext;
in vec4 aMeta;
out vec4 vColor;
out vec4 vMeta;
out float vDepth;
void main() {
  vec4 e0 = x3d_ModelViewMatrix * vec4(x3d_Vertex.xyz - aMeta.x * vec3(0.004, 0.0028, 0.0012), 1.0);   // undo the anti-degeneracy offset
  vec4 e1 = x3d_ModelViewMatrix * vec4(aNext.xyz, 1.0);
  vec4 c0 = x3d_ProjectionMatrix * e0;
  vec4 c1 = x3d_ProjectionMatrix * e1;
  vec2 hv = vec2(x3d_Viewport.zw) * 0.5;
  vec2 s0 = c0.xy / c0.w * hv;
  vec2 s1 = c1.xy / c1.w * hv;
  vec2 d = s1 - s0;
  float l = length(d);
  d = l > 1.0e-5 ? d / l : vec2(1.0, 0.0);
  vec2 n = vec2(-d.y, d.x);
  float w = uWidth * (0.55 + 0.9 * aMeta.z) * 3.0;
  vec2 off = n * aMeta.x * w;
  gl_Position = c0 + vec4(off / hv * c0.w, 0.0, 0.0);
  vColor = x3d_Color;
  vMeta = aMeta;
  vDepth = -e0.z;
}
"""

FS_RIBBON = """#version 300 es
precision highp float;
uniform float uTime;
uniform float uGrow;
uniform float uExposure;
uniform float uBoost;
@@PER_TRACK@@
in vec4 vColor;
in vec4 vMeta;
in float vDepth;
out vec4 fragColor;
float hash1(float n) { return fract(sin(n * 91.3458) * 47453.5453); }
void main() {
  float v = vMeta.x;
  float s = vMeta.y;
  float seed = vMeta.w;
  float core = exp(-v * v * 14.0);
  float halo = exp(-v * v * 5.0);
  float speed = 1.0 + floor(hash1(seed) * 3.0);
  float freq = 2.0 + floor(hash1(seed + 1.0) * 3.0);
  float ph = fract(s * freq - uTime * speed + hash1(seed + 2.0));
  float pulse = pow(1.0 - ph, 5.0);
  float fadeEnd = 1.0 - 0.7 * smoothstep(0.7, 1.0, s);
  float birth = hash1(seed + 3.0) * 0.30;
  float g = clamp((uGrow - birth) / 0.70, 0.0, 1.0);
  float vis = uGrow >= 0.999 ? 1.0 : 1.0 - smoothstep(g - 0.05, g, s);
  float head = uGrow >= 0.999 ? 0.0 : exp(-pow((s - g + 0.01) / 0.025, 2.0)) * step(0.001, g);
  float base = 0.62 + 0.38 * pulse;
  vec3 col = vColor.rgb * (halo * 0.30 + core * 0.95) * base * fadeEnd * vis;
  col += vec3(1.0) * core * (pulse * 0.55 * vis + head * 1.6);
  col *= vColor.a * uExposure * (1.0 + uBoost);
  col = 1.0 - exp(-col * 1.7);
  fragColor = vec4(col, 1.0);
}
"""

VS_SHELL = """#version 300 es
precision highp float;
uniform mat4 x3d_ProjectionMatrix;
uniform mat4 x3d_ModelViewMatrix;
uniform mat3 x3d_NormalMatrix;
in vec4 x3d_Vertex;
in vec3 x3d_Normal;
out vec3 vN;
out vec3 vP;
out vec3 vObj;
void main() {
  vec4 p = x3d_ModelViewMatrix * x3d_Vertex;
  vP = p.xyz;
  vN = x3d_NormalMatrix * x3d_Normal;
  vObj = x3d_Vertex.xyz;
  gl_Position = x3d_ProjectionMatrix * p;
}
"""

FS_SHELL = """#version 300 es
precision highp float;
uniform vec3 uRim;
uniform float uPow;
uniform float uRibs;
uniform float uPanels;
uniform float uBright;
uniform float uTime;
in vec3 vN;
in vec3 vP;
in vec3 vObj;
out vec4 fragColor;
void main() {
  vec3 N = normalize(vN);
  vec3 V = normalize(-vP);
  float ndv = abs(dot(N, V));
  float fres = pow(1.0 - ndv, uPow);
  float ang = atan(vObj.z, vObj.x);
  float rib = smoothstep(0.93, 1.0, abs(sin(vObj.y * uRibs)));
  float pan = smoothstep(0.95, 1.0, abs(sin(ang * uPanels * 0.5)));
  float scan = 0.5 + 0.5 * sin(vObj.y * 9.0 - uTime * 6.2831853);
  float fade = exp(-length(vP) * 0.04);
  vec3 col = uRim * (fres * 0.85 + 0.012);
  col += uRim * 1.5 * (rib + 0.12 * pan) * (0.12 + 0.88 * fres);
  col += vec3(0.5, 0.75, 1.0) * fres * fres * scan * 0.35;
  col *= uBright * fade;
  col = 1.0 - exp(-col * 1.4);
  fragColor = vec4(col, 1.0);
}
"""

VS_TOWER = """#version 300 es
precision highp float;
uniform mat4 x3d_ProjectionMatrix;
uniform mat4 x3d_ModelViewMatrix;
in vec4 x3d_Vertex;
in vec4 aTw;
out vec3 vTw;
out float vDepth;
void main() {
  vec4 p = x3d_ModelViewMatrix * x3d_Vertex;
  vTw = aTw.xyz;
  vDepth = -p.z;
  gl_Position = x3d_ProjectionMatrix * p;
}
"""

FS_TOWER = """#version 300 es
precision highp float;
uniform float uTime;
uniform float uBright;
in vec3 vTw;
in float vDepth;
out vec4 fragColor;
void main() {
  float E = vTw.x;
  float H = vTw.y;
  vec3 cold = vec3(0.25, 0.75, 1.0);
  vec3 hot = vec3(1.0, 0.62, 0.15);
  vec3 base = mix(cold, hot, vTw.z);
  float flicker = 0.9 + 0.1 * sin(uTime * 6.2831853 * 2.0 + E * 40.0);
  vec3 col = base * (0.22 + 1.5 * E) * (0.5 + 0.5 * H) * flicker;
  col += vec3(1.0) * pow(H, 7.0) * E * 0.35;
  col *= uBright;
  col = 1.0 - exp(-col * 1.5);
  fragColor = vec4(col, 1.0);
}
"""

VS_QUAD = """#version 300 es
precision highp float;
uniform mat4 x3d_ProjectionMatrix;
uniform mat4 x3d_ModelViewMatrix;
in vec4 x3d_Vertex;
out vec2 vUV;
void main() {
  vUV = x3d_Vertex.xy;
  gl_Position = x3d_ProjectionMatrix * (x3d_ModelViewMatrix * x3d_Vertex);
}
"""

FS_FLASH = """#version 300 es
precision highp float;
uniform float uFlash;
in vec2 vUV;
out vec4 fragColor;
void main() {
  vec2 p = vUV;
  float r = length(p);
  float glow = exp(-r * r * 9.0) * 0.9 + 0.35 / (1.0 + r * r * 90.0);
  float st = exp(-abs(p.y) * 38.0) * exp(-abs(p.x) * 2.4) + exp(-abs(p.x) * 38.0) * exp(-abs(p.y) * 2.4);
  float d1 = exp(-abs(p.x - p.y) * 45.0) * exp(-abs(p.x + p.y) * 3.0);
  float d2 = exp(-abs(p.x + p.y) * 45.0) * exp(-abs(p.x - p.y) * 3.0);
  float edge = 1.0 - smoothstep(0.75, 1.0, r);
  vec3 col = vec3(0.85, 0.93, 1.0) * (glow + 0.55 * st + 0.18 * (d1 + d2)) * edge * uFlash;
  col = 1.0 - exp(-col * 1.5);
  fragColor = vec4(col, 1.0);
}
"""

FS_HAZE = """#version 300 es
precision highp float;
uniform float uTime;
uniform float uGain;
in vec2 vUV;
out vec4 fragColor;
float h(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float n(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(h(i), h(i + vec2(1.0, 0.0)), f.x), mix(h(i + vec2(0.0, 1.0)), h(i + vec2(1.0, 1.0)), f.x), f.y);
}
float fbm(vec2 p) {
  float a = 0.5;
  float s = 0.0;
  for (int i = 0; i < 5; i++) { s += a * n(p); p = p * 2.03 + vec2(1.7, 9.2); a *= 0.5; }
  return s;
}
void main() {
  vec2 p = vUV;
  float r = length(p);
  float f = fbm(p * 2.4 + vec2(uTime * 0.6, 0.0));
  float rad = exp(-r * r * 1.1);
  vec3 col = (vec3(0.020, 0.052, 0.110) * (f * 1.6) * rad * 2.6 + vec3(0.000, 0.016, 0.040) * rad) * uGain;
  fragColor = vec4(col, 1.0);
}
"""


# ---------------------------------------------------------------------------------------------- data
def helix_adaptive(pt, eta, phi, q, z0, rmax, zmax, max_turns, seg=0.11, nmin=8, nmax=110):
    rho = pt / (0.3 * B_FIELD)
    rs = q * rho
    l_end = 2 * rho * math.asin(min(1.0, rmax / (2 * rho))) if 2 * rho > rmax else max_turns * 2 * math.pi * rho
    sz = math.sinh(eta)
    if abs(sz) > 1e-9:
        l_end = min(l_end, max(0.05, (zmax - z0 * math.copysign(1.0, sz)) / abs(sz)))
    npts = max(nmin, min(nmax, int(math.ceil(l_end / rho / seg)) + 1))
    pts, ss = [], []
    for i in range(npts):
        l = l_end * i / (npts - 1)
        pts.append((rs * (math.sin(phi) - math.sin(phi - l / rs)), rs * (math.cos(phi - l / rs) - math.cos(phi)), z0 + l * sz))
        ss.append(i / (npts - 1))
    return pts, ss


def hero_tracks(n, seed=42, loop_frac=0.16, loop_scale=1.0, curve_frac=0.22):
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        u = rnd.random()
        if u < loop_frac:
            kind, pt, eta, turns, rmax = 'loop', rnd.uniform(0.14, 0.42) * loop_scale, rnd.gauss(0, 0.45), rnd.uniform(1.0, 2.8), 2.0
            col = rnd.choice(['magenta', 'violet', 'cyan', 'magenta', 'emerald'])
        elif u < loop_frac + curve_frac:
            kind, pt, eta, turns, rmax = 'curve', rnd.uniform(0.45, 2.5), rnd.gauss(0, 0.9), 1.0, 2.0
            col = rnd.choice(['cyan', 'amber', 'emerald', 'violet', 'magenta'])
        elif u < 0.95:
            kind, pt, eta, turns, rmax = 'straight', math.exp(rnd.uniform(math.log(4), math.log(140))), rnd.gauss(0, 0.9), 1.0, rnd.uniform(1.9, 2.6)
            col = rnd.choice(['cyan', 'cyan', 'cyan', 'amber', 'amber', 'emerald', 'magenta', 'violet', 'ice'])
        else:
            kind, pt, eta, turns, rmax = 'long', rnd.uniform(40, 200), rnd.uniform(-1.2, 1.2), 1.0, 2.9
            col = 'ice'
        eta = max(-2.3, min(2.3, eta))
        phi = rnd.uniform(-math.pi, math.pi)
        q = 1 if rnd.random() < 0.5 else -1
        pts, ss = helix_adaptive(pt, eta, phi, q, rnd.gauss(0, 0.03), rmax, 3.2, turns)
        pt01 = max(0.0, min(1.0, math.log10(pt / 0.09) / math.log10(2200)))
        if kind == 'loop':
            pt01 = max(pt01, 0.5)
        out.append(dict(id=i, kind=kind, pt=pt, pt01=pt01, color=PAL[col], cname=col, pts=pts, s=ss, seed=(i * 0.6180339887) % 1.0 * 97.0 + 1.0))
    return out


def tower_ring(nphi, nz, r0=2.0, zspan=3.2, seed=4, n_jets=7, e0=0.03, zfrac=0.9):
    rnd = random.Random(seed)
    jets = [(rnd.uniform(-math.pi, math.pi), rnd.uniform(-1.8, 1.8), rnd.uniform(0.5, 1.0)) for _ in range(n_jets)]
    rows = []
    for ip in range(nphi):
        phi = -math.pi + (ip + 0.5) * 2 * math.pi / nphi
        for iz in range(nz):
            zc = -zspan + (iz + 0.5) * 2 * zspan / nz
            e = rnd.expovariate(1 / e0)
            for (jp, jz, jw) in jets:
                dphi = (phi - jp + math.pi) % (2 * math.pi) - math.pi
                e += jw * 0.9 * math.exp(-(dphi ** 2) / (2 * 0.07 ** 2) - ((zc - jz) ** 2) / (2 * 0.9 ** 2))
            rows.append((phi, zc, min(1.0, e)))
    return rows, (2 * math.pi * r0 / nphi) * 0.42, (2 * zspan / nz) * zfrac


def tower_mesh(nphi=288, nz=6, r0=2.0, hmax=0.42, seed=4, hot=0.55, wfac=0.42, e0=0.03, zfrac=0.9):
    rows, wphi, dz = tower_ring(nphi, nz, r0, seed=seed, e0=e0, zfrac=zfrac)
    wphi = wphi / 0.42 * wfac
    rnd = random.Random(seed + 1)
    pts, attr, idx = [], [], []
    for (phi, zc, e) in rows:
        h = 0.04 + hmax * e ** 0.8
        rh = (math.cos(phi), math.sin(phi), 0.0)
        ph = (-math.sin(phi), math.cos(phi), 0.0)
        t = 1.0 if rnd.random() < hot else 0.0
        base = len(pts)
        for (a, b, c) in [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]:
            rr = r0 + c * h
            p = (rh[0] * rr + ph[0] * a * wphi / 2, rh[1] * rr + ph[1] * a * wphi / 2, zc + b * dz / 2)
            pts.append(p)
            attr.append((e, float(c), t))
        # 5 faces (no inner base): outer, +z, -z, +phi side, -phi side
        for f in [(4, 5, 6, 7), (3, 2, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (0, 3, 7, 4)]:
            idx.extend([base + f[0], base + f[1], base + f[2], base + f[0], base + f[2], base + f[3]])
    return pts, attr, idx


def shell_mesh(r, hl, nseg=192):
    """Open cylinder along Y (axis = beam after the Transform rotation), smooth radial normals; avoids Cylinder's coarse facets."""
    pts, nrm, idx = [], [], []
    for i in range(nseg):
        a = 2 * math.pi * i / nseg
        c, s_ = math.cos(a), math.sin(a)
        for y in (-hl, hl):
            pts.append((r * c, y, r * s_))
            nrm.append((c, 0.0, s_))
    for i in range(nseg):
        a = 2 * i
        b = (2 * ((i + 1) % nseg))
        idx.extend([a, a + 1, b, a + 1, b + 1, b])
    return pts, nrm, idx


# ---------------------------------------------------------------------------------------------- xml
def f3(p):
    return '%s %s %s' % (fmt(p[0]), fmt(p[1]), fmt(p[2]))


def shader_xml(vs, fs, fields, def_name=None, per_track=''):
    fs = fs.replace('@@PER_TRACK@@', per_track)
    fl = ''.join('\n        <field name="%s" type="%s" accessType="%s" value="%s"/>' % f for f in fields)
    d = ' DEF="%s"' % def_name if def_name else ''
    return ('<ComposedShader language="GLSL"%s>%s\n'
            '        <ShaderPart type="VERTEX"><![CDATA[data:x-shader/x-vertex,%s]]></ShaderPart>\n'
            '        <ShaderPart type="FRAGMENT"><![CDATA[data:x-shader/x-fragment,%s]]></ShaderPart>\n'
            '      </ComposedShader>') % (d, fl, vs, fs)


ADD_BLEND = '<BlendMode DEF="BM_ADD" sourceColorFactor="ONE" destinationColorFactor="ONE" sourceAlphaFactor="ONE" destinationAlphaFactor="ONE"/>'
NODEPTH = '<DepthMode DEF="DM_RO" depthMask="false"/>'   # was readOnly="true", not an X_ITE 16.5.1 field (ignored): the measured runs wrote depth


def appearance(shader_xml_, use_modes=False, first=True):
    if first:
        return '<Appearance>%s%s%s</Appearance>' % (ADD_BLEND, NODEPTH, shader_xml_)
    return '<Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/>%s</Appearance>' % shader_xml_


EPS = 0.004   # ribbon vertices are offset by side*EPS*(1,.7,.3) so triangles are NOT degenerate (zero-area meshes crashed the renderer); the vertex shader subtracts it again


def strip_geom(tracks, with_def=None, eps=EPS):
    cnt, co, col, nxt, meta = [], [], [], [], []
    for t in tracks:
        P = t['pts']
        m = len(P)
        cnt.append(2 * m)
        for k in range(m):
            nx = P[k + 1] if k < m - 1 else (2 * P[k][0] - P[k - 1][0], 2 * P[k][1] - P[k - 1][1], 2 * P[k][2] - P[k - 1][2])
            for side in (-1, 1):
                co.append(f3((P[k][0] + side * eps, P[k][1] + side * eps * 0.7, P[k][2] + side * eps * 0.3)) if eps else f3(P[k]))
                col.append('%s %s %s %s' % (fmt(t['color'][0], 2), fmt(t['color'][1], 2), fmt(t['color'][2], 2), fmt(0.55 + 0.45 * t['pt01'], 2)))
                nxt.append(f3(nx) + ' 1')
                meta.append('%d %s %s %s' % (side, fmt(t['s'][k], 3), fmt(t['pt01'], 2), fmt(t['seed'], 2)))
    return ('<TriangleStripSet solid="false" stripCount="%s"><Coordinate point="%s"/><ColorRGBA color="%s"/>'
            '<FloatVertexAttribute name="aNext" numComponents="4" value="%s"/><FloatVertexAttribute name="aMeta" numComponents="4" value="%s"/>'
            '</TriangleStripSet>') % (' '.join(map(str, cnt)), ' '.join(co), ' '.join(col), ' '.join(nxt), ' '.join(meta))


def its_geom(tracks):
    co, col, nxt, meta, idx = [], [], [], [], []
    base = 0
    for t in tracks:
        P = t['pts']
        m = len(P)
        for k in range(m):
            nx = P[k + 1] if k < m - 1 else (2 * P[k][0] - P[k - 1][0], 2 * P[k][1] - P[k - 1][1], 2 * P[k][2] - P[k - 1][2])
            for side in (-1, 1):
                co.append(f3((P[k][0] + side * EPS, P[k][1] + side * EPS * 0.7, P[k][2] + side * EPS * 0.3)))
                col.append('%s %s %s %s' % (fmt(t['color'][0], 2), fmt(t['color'][1], 2), fmt(t['color'][2], 2), fmt(0.55 + 0.45 * t['pt01'], 2)))
                nxt.append(f3(nx) + ' 1')
                meta.append('%d %s %s %s' % (side, fmt(t['s'][k], 3), fmt(t['pt01'], 2), fmt(t['seed'], 2)))
        for k in range(m - 1):
            a = base + 2 * k
            idx.extend([a, a + 1, a + 2, a + 1, a + 3, a + 2])
        base += 2 * m
    return ('<IndexedTriangleSet solid="false" index="%s"><Coordinate point="%s"/><ColorRGBA color="%s"/>'
            '<FloatVertexAttribute name="aNext" numComponents="4" value="%s"/><FloatVertexAttribute name="aMeta" numComponents="4" value="%s"/>'
            '</IndexedTriangleSet>') % (' '.join(map(str, idx)), ' '.join(co), ' '.join(col), ' '.join(nxt), ' '.join(meta))


def per_track_source(t, with_consts):
    # S4: bake constants into the GLSL text so every program is textually distinct.
    if not with_consts:
        return ''
    return ('const vec3 K_BASE = vec3(%.3f, %.3f, %.3f);\nconst float K_SEED = %.3f;\nconst float K_PT = %.3f;\n'
            % (t['color'][0], t['color'][1], t['color'][2], t['seed'], t['pt01']))


def camera(cam, fov=None):
    if cam == 'endon':
        return (0.0, 0.0, 11.0), fov or 0.55
    if cam == 'side':
        return (8.5, 1.5, 1.0), fov or 0.7
    return (5.2, 3.0, 7.0), fov or 0.75


def hero(n=300, mode='S1', cam='endon', time=0.35, grow=1.0, anim=0, flash=1.0, towers=1, shells=1, haze=1, plain=0,
         width=1.15, exposure=1.35, nphi=288, nz=6, comps=('Shaders', 'X_ITE'), smooth=0, hot=0.55, wfac=0.42, flash_scale=1.5, haze_gain=1.0, tower_h=0.42, sparks=0, shell_hl=1.0, shell_bright=1.0, shell_rmin=0.0, tower_bright=1.0, tower_r0=2.0, tower_e0=0.03, loop_frac=0.16, loop_scale=1.0, zfrac=0.9, curve_frac=0.22):
    tracks = hero_tracks(n, loop_frac=loop_frac, loop_scale=loop_scale, curve_frac=curve_frac)
    pos, fov = camera(cam)
    o = ['<?xml version="1.0" encoding="UTF-8"?>\n<X3D profile="Immersive" version="4.0">\n  <head>\n'
         '    <component name="Shaders" level="1"/>\n    <component name="Rendering" level="3"/>\n    <component name="X_ITE" level="1"/>\n' + ('    <component name="ParticleSystems" level="2"/>\n' if sparks else '') +
         '    <meta name="title" content="hero look %s N=%d %s"/>\n    <meta name="generator" content="feas/gen_look.py (SYNTHETIC physics, AUTHORED look)"/>\n'
         '  </head>\n  <Scene>\n' % (mode, n, cam)]
    ori = lookat(pos)
    o.append('    <NavigationInfo type=\'"EXAMINE" "ANY"\' headlight="false" transitionType=\'"TELEPORT"\'/>\n')
    o.append('    <Viewpoint DEF="VP" description="%s" position="%s" orientation="%s" fieldOfView="%s"/>\n'
             % (cam, f3(pos), ' '.join(fmt(c, 5) for c in ori), fmt(fov, 3)))
    o.append('    <Background skyColor="0.004 0.008 0.016"/>\n')
    if anim:
        o.append('    <TimeSensor DEF="CLK" cycleInterval="6" loop="true"/>\n'
                 '    <TimeSensor DEF="GROW" cycleInterval="3.5" loop="true"/>\n'
                 '    <TimeSensor DEF="PULSE" cycleInterval="2.2" loop="true"/>\n')
    routes = []

    def tfields(extra=()):
        f = [('uTime', 'SFFloat', 'inputOutput', fmt(time, 3)), ('uGrow', 'SFFloat', 'inputOutput', fmt(grow, 3)),
             ('uExposure', 'SFFloat', 'initializeOnly', fmt(exposure, 2)), ('uWidth', 'SFFloat', 'initializeOnly', fmt(width, 2))]
        return f + list(extra)

    # --- haze (far quad), shells, towers, flash: all additive, no depth write -> order independent.
    if haze:
        sh = shader_xml(VS_QUAD, FS_HAZE, [('uTime', 'SFFloat', 'inputOutput', fmt(time, 3)), ('uGain', 'SFFloat', 'initializeOnly', fmt(haze_gain, 2))], 'SH_HAZE')
        o.append('    <Billboard axisOfRotation="0 0 0"><Transform translation="0 0 -16" scale="26 15 1"><Shape><Appearance>%s%s%s</Appearance>'
                 '<IndexedFaceSet coordIndex="0 1 2 3 -1"><Coordinate point="-1 -1 0, 1 -1 0, 1 1 0, -1 1 0"/></IndexedFaceSet></Shape></Transform></Billboard>\n' % (ADD_BLEND, NODEPTH, sh))
        if anim:
            routes.append('<ROUTE fromNode="PULSE" fromField="fraction_changed" toNode="SH_HAZE" toField="uTime"/>')
    first_app = [False]
    if shells:
        specs = [(0.55, 1.6, 'ice', 0.55, 6.0, 5, 24), (0.95, 1.9, 'cyan', 0.45, 5.0, 4, 36), (1.35, 2.2, 'cyan', 0.60, 5.0, 3, 48),
                 (1.75, 2.5, 'ice', 0.45, 4.0, 3, 72), (2.35, 2.9, 'cyan', 0.80, 5.5, 3, 40), (2.85, 3.3, 'cyan', 0.55, 4.0, 2, 24)]
        for i, (r, hl, cn, br, pw, ribs, pan) in enumerate(specs):
            if r < shell_rmin:
                continue
            hl, br = hl * shell_hl, br * shell_bright
            c = PAL[cn]
            rim = (c[0] * 0.55, c[1] * 0.75, c[2] * 1.0)
            fields = [('uRim', 'SFColor', 'initializeOnly', f3(rim)), ('uPow', 'SFFloat', 'initializeOnly', fmt(pw, 1)),
                      ('uRibs', 'SFFloat', 'initializeOnly', fmt(ribs * 3.0, 1)), ('uPanels', 'SFFloat', 'initializeOnly', fmt(pan, 1)),
                      ('uBright', 'SFFloat', 'initializeOnly', fmt(br * 0.85, 2)), ('uTime', 'SFFloat', 'inputOutput', fmt(time, 3))]
            sh = shader_xml(VS_SHELL, FS_SHELL, fields, 'SH_SHELL%d' % i)
            app = '<Appearance>%s%s%s</Appearance>' % (ADD_BLEND, NODEPTH, sh) if i == 0 else '<Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/>%s</Appearance>' % sh
            if i == 0:
                first_app[0] = True
            if plain:
                app = ('<Appearance><Material diffuseColor="%s" emissiveColor="%s" transparency="0.7"/></Appearance>' % (f3(rim), f3([x * 0.3 for x in rim])))
            if smooth:
                sp, sn, si = shell_mesh(r, hl, 192)
                o.append('    <Transform rotation="1 0 0 1.5708"><Shape>%s<IndexedTriangleSet solid="false" index="%s"><Coordinate point="%s"/><Normal vector="%s"/></IndexedTriangleSet></Shape></Transform>\n'
                         % (app, ' '.join(map(str, si)), ' '.join(f3(p) for p in sp), ' '.join(f3(p) for p in sn)))
            else:
                o.append('    <Transform rotation="1 0 0 1.5708"><Shape>%s<Cylinder radius="%s" height="%s" top="false" bottom="false" solid="false" subdivision="96"/></Shape></Transform>\n'
                         % (app, fmt(r, 3), fmt(2 * hl, 2)))
            if anim and not plain:
                routes.append('<ROUTE fromNode="PULSE" fromField="fraction_changed" toNode="SH_SHELL%d" toField="uTime"/>' % i)
    if towers:
        pts, attr, idx = tower_mesh(nphi, nz, r0=tower_r0, hmax=tower_h, hot=hot, wfac=wfac, e0=tower_e0, zfrac=zfrac)
        sh = shader_xml(VS_TOWER, FS_TOWER, [('uTime', 'SFFloat', 'inputOutput', fmt(time, 3)), ('uBright', 'SFFloat', 'initializeOnly', fmt(tower_bright, 2))], 'SH_TOWER')
        app = ('<Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/>%s</Appearance>' % sh)
        o.append('    <Shape>%s<IndexedTriangleSet solid="false" index="%s"><Coordinate point="%s"/>'
                 '<FloatVertexAttribute name="aTw" numComponents="4" value="%s"/></IndexedTriangleSet></Shape>\n'
                 % (app, ' '.join(map(str, idx)), ' '.join(f3(p) for p in pts), ' '.join('%s %s %s 0' % (fmt(a[0], 2), fmt(a[1], 0), fmt(a[2], 0)) for a in attr)))
        if anim:
            routes.append('<ROUTE fromNode="PULSE" fromField="fraction_changed" toNode="SH_TOWER" toField="uTime"/>')
    # --- tracks
    if mode in ('S1', 'S1b'):
        sh = shader_xml(VS_RIBBON, FS_RIBBON, tfields(), 'SH_TRK')
        o.append('    <Shape><Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/>%s</Appearance>%s</Shape>\n' % (sh, (its_geom if mode == 'S1b' else strip_geom)(tracks)))
        if anim:
            routes += ['<ROUTE fromNode="CLK" fromField="fraction_changed" toNode="SH_TRK" toField="uTime"/>',
                       '<ROUTE fromNode="GROW" fromField="fraction_changed" toNode="SH_TRK" toField="uGrow"/>']
    elif mode.startswith('S5'):   # S5 = ribbons merged in chunks of `chunk` tracks (S5_50 / S5_100 / S5_250), one shared Appearance
        ch = int(mode.split('_')[1]) if '_' in mode else 100
        sh = shader_xml(VS_RIBBON, FS_RIBBON, tfields(), 'SH_TRK')
        for ci in range(0, len(tracks), ch):
            app = ('<Appearance DEF="APP_TRK"><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/>%s</Appearance>' % sh) if ci == 0 else '<Appearance USE="APP_TRK"/>'
            o.append('    <Shape>%s%s</Shape>\n' % (app, strip_geom(tracks[ci:ci + ch])))
        if anim:
            routes += ['<ROUTE fromNode="CLK" fromField="fraction_changed" toNode="SH_TRK" toField="uTime"/>',
                       '<ROUTE fromNode="GROW" fromField="fraction_changed" toNode="SH_TRK" toField="uGrow"/>']
    elif mode == 'S2':
        sh = shader_xml(VS_RIBBON, FS_RIBBON, tfields(), 'SH_TRK')
        o.append('    <Shape><Appearance DEF="APP_TRK"><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/>%s</Appearance>%s</Shape>\n' % (sh, strip_geom(tracks[:1])))
        for t in tracks[1:]:
            o.append('    <Shape><Appearance USE="APP_TRK"/>%s</Shape>\n' % strip_geom([t]))
        if anim:
            routes += ['<ROUTE fromNode="CLK" fromField="fraction_changed" toNode="SH_TRK" toField="uTime"/>',
                       '<ROUTE fromNode="GROW" fromField="fraction_changed" toNode="SH_TRK" toField="uGrow"/>']
    else:
        for t in tracks:
            nm = 'SH_T%d' % t['id']
            if mode == 'S3':
                # identical source; the only per-track difference would be uniform values, so add one (uSeedBias, unused = 0)
                sh = shader_xml(VS_RIBBON, FS_RIBBON, tfields([('uBoost', 'SFFloat', 'inputOutput', '0')]), nm)
            else:
                sh = shader_xml(VS_RIBBON, FS_RIBBON.replace('void main() {', per_track_source(t, True) + 'void main() {', 1), tfields(), nm)
            o.append('    <Shape><Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/>%s</Appearance>%s</Shape>\n' % (sh, strip_geom([t])))
            if anim:
                routes += ['<ROUTE fromNode="CLK" fromField="fraction_changed" toNode="%s" toField="uTime"/>' % nm,
                           '<ROUTE fromNode="GROW" fromField="fraction_changed" toNode="%s" toField="uGrow"/>' % nm]
    if flash:
        sh = shader_xml(VS_QUAD, FS_FLASH, [('uFlash', 'SFFloat', 'inputOutput', fmt(flash, 2))], 'SH_FLASH')
        o.append('    <Billboard axisOfRotation="0 0 0"><Transform scale="%s %s 1"><Shape><Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/>%s</Appearance>'
                 '<IndexedFaceSet coordIndex="0 1 2 3 -1"><Coordinate point="-1 -1 0, 1 -1 0, 1 1 0, -1 1 0"/></IndexedFaceSet></Shape></Transform></Billboard>\n' % (fmt(flash_scale, 2), fmt(flash_scale, 2), sh))
        if anim:
            o.append('    <ScalarInterpolator DEF="FLASHI" key="0 0.04 0.12 0.4 1" keyValue="0.5 1.6 1.0 0.7 0.6"/>\n')
            routes += ['<ROUTE fromNode="PULSE" fromField="fraction_changed" toNode="FLASHI" toField="set_fraction"/>',
                       '<ROUTE fromNode="FLASHI" fromField="value_changed" toNode="SH_FLASH" toField="uFlash"/>']
    if sparks:   # native ParticleSystem: line sparks from the vertex, additive, read-only depth
        o.append('    <ParticleSystem geometryType="LINE" maxParticles="%d" particleLifetime="1.6" lifetimeVariation="0.6" particleSize="0.3 0.3" colorKey="0 0.5 1">'
                 '<Appearance><BlendMode USE="BM_ADD"/><DepthMode USE="DM_RO"/><Material emissiveColor="1 0.8 0.4" diffuseColor="0 0 0"/></Appearance>'
                 '<ConeEmitter position="0 0 0" direction="0 0 1" angle="3.14159" speed="2.2" variation="0.9" mass="0" surfaceArea="0"/>'
                 '<ColorRGBA containerField="color" color="1 0.95 0.7 0.9, 1 0.55 0.15 0.6, 0.6 0.2 0.1 0"/></ParticleSystem>\n' % int(sparks))
    o.append('    ' + '\n    '.join(routes) + '\n' if routes else '')
    o.append('  </Scene>\n</X3D>\n')
    txt = ''.join(o)
    if 'DEF="BM_ADD"' not in txt:  # the earliest user carries the DEF
        txt = txt.replace('<BlendMode USE="BM_ADD"/>', ADD_BLEND, 1).replace('<DepthMode USE="DM_RO"/>', NODEPTH, 1)
    return txt


# ---------------------------------------------------------------------------------------------- png
def png_rgba(w, h, fn):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw.extend(fn(x / (w - 1), y / (h - 1)))
    def chunk(t, d):
        c = struct.pack('>I', len(d)) + t + d
        return c + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + chunk(b'IEND', b''))


def glow_png(path, w=128):
    def px(u, v):
        r = math.hypot(u * 2 - 1, v * 2 - 1)
        a = max(0.0, 1.0 - r)
        g = int(255 * min(1.0, (a ** 2.2) * 1.4))
        return (255, 255, 255, g)
    open(path, 'wb').write(png_rgba(w, w, px))


def main(a):
    if len(a) < 2:
        print(__doc__)
        return 2
    cmd, out = a[0], a[1]
    opt = {a[i][2:]: a[i + 1] for i in range(2, len(a) - 1, 2) if a[i].startswith('--')}
    if cmd == 'hero':
        k = dict(n=int(opt.get('n', 300)), mode=opt.get('mode', 'S1'), cam=opt.get('cam', 'endon'), time=float(opt.get('time', 0.35)),
                 grow=float(opt.get('grow', 1.0)), anim=int(opt.get('anim', 0)), flash=float(opt.get('flash', 1.0)), towers=int(opt.get('towers', 1)),
                 shells=int(opt.get('shells', 1)), haze=int(opt.get('haze', 1)), plain=int(opt.get('plain', 0)), width=float(opt.get('width', 1.6)), smooth=int(opt.get('smooth', 0)), hot=float(opt.get('hot', 0.55)), wfac=float(opt.get('wfac', 0.42)),
                 flash_scale=float(opt.get('flash_scale', 1.5)), haze_gain=float(opt.get('haze_gain', 1.0)), nphi=int(opt.get('nphi', 288)), nz=int(opt.get('nz', 6)), tower_h=float(opt.get('tower_h', 0.42)), sparks=int(opt.get('sparks', 0)), shell_hl=float(opt.get('shell_hl', 1.0)), shell_bright=float(opt.get('shell_bright', 1.0)), shell_rmin=float(opt.get('shell_rmin', 0.0)), tower_bright=float(opt.get('tower_bright', 1.0)), tower_r0=float(opt.get('tower_r0', 2.0)), tower_e0=float(opt.get('tower_e0', 0.03)), loop_frac=float(opt.get('loop_frac', 0.16)), loop_scale=float(opt.get('loop_scale', 1.0)), zfrac=float(opt.get('zfrac', 0.9)), curve_frac=float(opt.get('curve_frac', 0.22)), exposure=float(opt.get('exposure', 1.35)))
        open(out, 'w').write(hero(**k))
    elif cmd == 'all':
        os.makedirs(out, exist_ok=True)
        for n in (300, 3000):
            for m in ('S1', 'S1b', 'S2', 'S3', 'S4'):
                open(os.path.join(out, 'hero_%s_%d.x3d' % (m, n)), 'w').write(hero(n, m))
                open(os.path.join(out, 'hero_%s_%d_anim.x3d' % (m, n)), 'w').write(hero(n, m, anim=1))
        open(os.path.join(out, 'hero_persp_300.x3d'), 'w').write(hero(300, 'S1', cam='persp'))
        open(os.path.join(out, 'hero_side_300.x3d'), 'w').write(hero(300, 'S1', cam='side'))
        open(os.path.join(out, 'hero_noshell_300.x3d'), 'w').write(hero(300, 'S1', shells=0, towers=0, haze=0, flash=0))
        open(os.path.join(out, 'hero_plainshell_300.x3d'), 'w').write(hero(300, 'S1', plain=1))
        glow_png(os.path.join(out, 'glow.png'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
