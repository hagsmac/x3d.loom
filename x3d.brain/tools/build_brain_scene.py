#!/usr/bin/env python3
"""Hero brain scene (X3D 4.1, standard nodes only) from prep_meshes.py output.

    python -I build_brain_scene.py --npz meshes_41k.npz --regions ../data/regions.json --tf TEMPLATEFLOW_ROOT --out brain_hero_41k.x3d [--lite]

Writes the scene plus a `tex/` folder next to it (studio env faces, T1 slices, sprites). Prints counts and sha256 of every output.

What is in it (DEF names are the page contract):
  glass fresnel cortex (custom ComposedShader, per-vertex AO in the colour channel)   SW_CORTEX > G_CORTEX_L/R > SH_CORTEX_L/R, TS_CORTEX_L/R
  opaque wet PBR cortex alternative (same geometry node, USE)                        SW_WET > G_WET_L/R            (hidden)
  gold / bronze deep structures from the aseg meshes (PhysicalMaterial)              SW_DEEP > STRUCT_<name>, MAT_<name>
  SYNTHETIC direction-coloured tract arcs, core + two halos                           SW_TRACTS > TRACTS > TRACT_CORE/HALO1/HALO2
  translucent axial T1 slices                                                         SW_SLICES (hidden)
  billboard region labels                                                             SW_LABELS (hidden)
  ILLUSTRATIVE activation blobs                                                       SW_ACTIV (hidden)
  stage glow sprites                                                                  SW_STAGE
  Sound DEF SND / AudioClip DEF AUDIO (not started), 64 px studio EnvironmentLight ENV, KEY/FILL/RIM lights, gradient BG, seven viewpoints.

Only nodes of the X3D 4.1 XSD are used. X_ITE-only nodes (BlendMode, DepthMode, material extensions, component X_ITE) are NOT, because the
fork validator's XSD rejects them; X_ITE draws every transparent shape with depth writes off, which gives the glass and halos what they need.

AO: the Cycles per-vertex bake (npz key `ao`, bake_out_<den>.npz) when prep_meshes proved it matches the mesh vertex for vertex, else sulc as AO.
"""
import argparse, hashlib, json, math, sys, time
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

# ======================================================================================== number formatting (compact)
def num(x, nd):
    s = f"{x:.{nd}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return s

def fl(a, nd=2):
    return " ".join(num(x, nd) for x in np.round(np.asarray(a, np.float64).reshape(-1), nd).tolist())

def il(a):
    return " ".join(map(str, np.asarray(a).reshape(-1).tolist()))

def sha(b):
    return hashlib.sha256(b).hexdigest()

def vertex_normals(v, f):
    n = np.zeros_like(v, dtype=np.float64)
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    for k in range(3):
        np.add.at(n, f[:, k], fn)
    l = np.linalg.norm(n, axis=1, keepdims=True); l[l == 0] = 1
    return n / l

def concavity_ao(v, f, n, strength=0.55, scale=1.4):
    """Cheap per-vertex occlusion for the smooth deep-structure meshes: a vertex that sits below the mean of its neighbours (concave) is darkened."""
    from scipy import sparse
    m = len(v)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    A = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(m, m)).tocsr(); A = ((A + A.T) > 0).astype(np.float64)
    W = sparse.diags(1 / np.maximum(np.asarray(A.sum(1)).ravel(), 1)) @ A
    c = np.einsum("ij,ij->i", W @ v - v, n)                         # > 0: concave (neighbours lie on the outer side of the vertex)
    for _ in range(2):
        c = W @ c
    return 1.0 - strength * np.clip(c / scale, 0, 1)

def lookat(eye, target=(0, 0, 0), up=(0, 1, 0)):
    """X3D Viewpoint orientation (axis-angle) for a camera at eye looking at target (camera looks down -Z)."""
    eye, target, up = (np.asarray(x, float) for x in (eye, target, up))
    z = eye - target; z /= np.linalg.norm(z)
    x = np.cross(up, z); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z], 1)
    ang = math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2)))
    if ang < 1e-9:
        return "0 0 1 0"
    if abs(ang - math.pi) < 1e-6:
        w, V = np.linalg.eigh((R + np.eye(3)) / 2); ax = V[:, np.argmax(w)]
    else:
        ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * math.sin(ang))
    return "%.5f %.5f %.5f %.5f" % (ax[0], ax[1], ax[2], ang)

def esc(s):
    return s.replace("&", "&amp;").replace("'", "&apos;").replace("<", "&lt;")

# ======================================================================================== shaders
GLASS_VS = """#version 300 es
precision highp float;
uniform mat4 x3d_ProjectionMatrix, x3d_ModelViewMatrix; uniform mat3 x3d_NormalMatrix;
in vec4 x3d_Vertex; in vec3 x3d_Normal; in vec4 x3d_Color;
out vec3 vN; out vec3 vP; out float vAO; out float vRel;
void main(){ vec4 p = x3d_ModelViewMatrix * x3d_Vertex; vP = p.xyz; vN = x3d_NormalMatrix * x3d_Normal; vAO = clamp((x3d_Color.g - 0.17) / 0.83, 0.0, 1.0);
  vRel = p.z - (x3d_ModelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0)).z;      // view-space depth relative to the model centre: > 0 nearer than the centre, < 0 farther
  gl_Position = x3d_ProjectionMatrix * p; }
"""
# Glass: plain alpha blending (X_ITE draws transparent shapes with depth writes off). Front shell (normal faces the eye) gets the full look,
# the far wall seen through it is dimmer. Sulci (low AO) are dark and denser, crowns are light and clear, the rim is a thin-film cyan to magenta.
GLASS_FS = """#version 300 es
precision highp float;
uniform vec3 rimColor; uniform vec3 rimColor2; uniform vec3 bodyColor;
uniform float rimPower; uniform float baseAlpha; uniform float rimAlpha; uniform float aoGamma; uniform float specular; uniform float backDim; uniform float sulcAlpha; uniform vec3 sulcColor; uniform float sulcLo; uniform float sulcHi;
uniform vec3 edgeColor; uniform float edgeAlpha; uniform float edgeLo; uniform float edgeW; uniform float farDim; uniform float farR;
in vec3 vN; in vec3 vP; in float vAO; in float vRel; out vec4 fragColor;
void main(){
  vec3 N = normalize(vN); vec3 V = normalize(-vP);
  float d = dot(N, V); float fr = step(0.0, d); float ndv = abs(d);
  vec3 Nf = (d < 0.0) ? -N : N;
  float ao = pow(clamp(vAO, 0.0, 1.0), aoGamma);                // 0 in sulcal fundi, 1 on gyral crowns
  float cr = smoothstep(sulcLo, sulcHi, ao);
  float f = pow(1.0 - ndv, rimPower);
  float hue = smoothstep(-0.15, 0.95, N.x * 0.85 - N.y * 0.55 + 0.25 * sin(vP.y * 0.045 + vP.x * 0.03));
  vec3 rimc = mix(rimColor, rimColor2, hue);
  float film = 0.5 + 0.5 * cos(6.2831853 * (ndv * 1.7 + 0.35 * ao));
  rimc = mix(rimc, rimc.zxy * vec3(0.9, 1.0, 1.0) + 0.1, 0.28 * film * f);
  vec3 L1 = normalize(vec3(-0.5, 0.7, 0.55)); vec3 H1 = normalize(L1 + V);
  vec3 L2 = normalize(vec3(0.85, -0.15, 0.45)); vec3 H2 = normalize(L2 + V);
  float s1 = pow(max(dot(Nf, H1), 0.0), 90.0) * (0.2 + 0.8 * cr);
  float s2 = pow(max(dot(Nf, H2), 0.0), 30.0) * 0.30 * cr;
  float dif = 0.6 + 0.4 * dot(Nf, L1);
  vec3 body = mix(sulcColor, bodyColor * dif, cr);      // dark teal in the sulci, pale blue glass on the crowns
  float aBody = mix(sulcAlpha, baseAlpha, cr);                                // sulci are dense, crowns are thin
  float aRim = rimAlpha * f * (0.35 + 0.65 * cr);
  float k = mix(backDim, 1.0, fr);
  vec3 spec = (vec3(1.0, 0.97, 0.92) * s1 + vec3(0.45, 0.75, 1.0) * s2) * specular * fr;
  float aSp = clamp((s1 + s2) * specular, 0.0, 1.0) * fr;
  float aTot = clamp((aBody + aRim) * k, 0.0, 1.0);
  vec3 col = (body * aBody + rimc * aRim) / max(aBody + aRim, 0.001);
  // gyral outline: a thin bright band where the occlusion climbs from fundus to crown (the glass-tube look); lit side brighter
  float ridge = smoothstep(edgeLo, edgeLo + edgeW, ao) * (1.0 - smoothstep(edgeLo + edgeW, edgeLo + 2.2 * edgeW, ao));
  float aEdge = clamp(edgeAlpha * ridge * (0.5 + 0.5 * pow(max(dot(Nf, H1), 0.0), 2.0)), 0.0, 1.0) * mix(0.35, 1.0, fr);
  col = mix(col, edgeColor, aEdge / max(aTot + aEdge, 0.001)); aTot = aTot + aEdge * (1.0 - aTot);
  float depthK = mix(farDim, 1.0, smoothstep(-farR, 0.35 * farR, vRel));      // depth cue: surfaces beyond the model centre fade, so the near shell reads crisp
  aTot *= depthK; aSp *= depthK;
  float a = clamp(aTot + aSp * (1.0 - aTot), 0.0, 1.0);
  col = mix(col, spec / max(aSp, 0.001) + col * 0.0, clamp(aSp / max(a, 0.001), 0.0, 1.0));
  fragColor = vec4(clamp(col, 0.0, 1.0), a);
}
"""

AURA_FS = """#version 300 es
precision highp float;
uniform vec3 auraColor; uniform vec3 auraColor2; uniform float auraPower; uniform float auraAlpha;
in vec3 vN; in vec3 vP; in float vAO; in float vRel; out vec4 fragColor;
void main(){
  vec3 N = normalize(vN); vec3 V = normalize(-vP);
  float d = dot(N, V);
  float f = pow(1.0 - clamp(d, 0.0, 1.0), auraPower) * step(0.0, d);
  float hue = smoothstep(-0.55, 0.65, N.x * 0.85 - N.y * 0.55);
  fragColor = vec4(mix(auraColor, auraColor2, hue), clamp(f * auraAlpha * (0.4 + 0.6 * smoothstep(0.0, 0.8, vAO)) * mix(0.35, 1.0, smoothstep(-70.0, 25.0, vRel)), 0.0, 1.0));
}
"""

# ======================================================================================== textures
def studio_faces(out, size=64):
    """Generated studio cube map (procedural, no external image): dark cool floor, soft white/blue key boxes, warm back light."""
    FACES = {"front": ((0, 0, -1), (1, 0, 0), (0, 1, 0)), "back": ((0, 0, 1), (-1, 0, 0), (0, 1, 0)), "left": ((-1, 0, 0), (0, 0, -1), (0, 1, 0)),
             "right": ((1, 0, 0), (0, 0, 1), (0, 1, 0)), "top": ((0, 1, 0), (1, 0, 0), (0, 0, 1)), "bottom": ((0, -1, 0), (1, 0, 0), (0, 0, -1))}
    LIGHTS = [((-0.5, 0.6, 0.62), (1.0, 0.95, 0.86), 0.42, 0.22), ((0.0, 1.0, 0.1), (0.75, 0.85, 0.95), 0.5, 0.35),
              ((0.75, -0.05, 0.5), (0.35, 0.62, 0.85), 0.35, 0.3), ((0.35, 0.45, -0.82), (1.0, 0.72, 0.4), 0.18, 0.12)]
    out.mkdir(parents=True, exist_ok=True)
    for name, (fwd, right, up) in FACES.items():
        s = (np.arange(size) + 0.5) / size * 2 - 1
        u, v = np.meshgrid(s, -s)
        d = np.stack([fwd[i] + u * right[i] + v * up[i] for i in range(3)], -1); d /= np.linalg.norm(d, axis=-1, keepdims=True)
        y = d[..., 1:2]
        img = np.where(y > 0, 0.10 + 0.12 * y, 0.06 + 0.03 * y) * np.array([0.55, 0.85, 1.0])
        for ld, col, rad, soft in LIGHTS:
            ld = np.array(ld) / np.linalg.norm(ld); ang = np.arccos(np.clip(d @ ld, -1, 1))[..., None]
            img = img + np.clip((rad + soft - ang) / soft, 0, 1) ** 2 * np.array(col)
        Image.fromarray((np.clip(img, 0, 1) ** (1 / 2.2) * 255 + 0.5).astype(np.uint8), "RGB").save(out / f"studio-{name}.png", optimize=True)


def sprite_png(path, n, rgb, falloff, peak, aspect=1.0, rgb2=None):
    """Radial glow sprite, straight alpha (plain alpha blending): alpha = peak * exp(-(r*falloff)^2); colour constant, or rgb at the centre blending to rgb2 at the rim."""
    y, x = np.mgrid[0:n, 0:n]
    u = ((x + 0.5) / n * 2 - 1) / aspect; v = (y + 0.5) / n * 2 - 1
    r = np.hypot(u, v)
    a = np.exp(-(r * falloff) ** 2) * np.clip(1.6 * (1 - r), 0, 1) * peak
    img = np.zeros((n, n, 4), np.uint8)
    t = np.clip(r * 1.15, 0, 1) if rgb2 is not None else np.zeros_like(r)
    for i in range(3):
        img[..., i] = np.clip(((rgb[i] + ((rgb2[i] - rgb[i]) if rgb2 is not None else 0) * t) * 255 + 0.5), 0, 255).astype(np.uint8)
    img[..., 3] = np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(img, "RGBA").save(path, optimize=True)


def wet_ramp_png(path, n=256):
    """Wet-cortex AO ramp (u = occlusion s, 0 in sulcal fundi, 1 on gyral crowns). The PhysicalMaterial baseColor multiplies it, so every look's
    tint still applies: the crowns are white (tint unchanged), the fundi a warm dark brown. X_ITE's PBR ignores vertex colour, a texture it honours."""
    u = np.linspace(0, 1, n)[:, None]
    sm = lambda a, b, x: (lambda z: z * z * (3 - 2 * z))(np.clip((x - a) / (b - a), 0, 1))
    dark, mid = np.array([0.26, 0.14, 0.10]), np.array([0.86, 0.64, 0.54])
    c = dark + (mid - dark) * sm(0.0, 0.42, u); c = c + (1 - c) * sm(0.38, 0.72, u)
    Image.fromarray((np.repeat(c[None], 4, 0) * 255 + 0.5).astype(np.uint8), "RGB").save(path, optimize=True)


def heat_png(path, n=128):
    """ILLUSTRATIVE activation sprite: white-yellow core, orange, red skirt; alpha falls off smoothly."""
    y, x = np.mgrid[0:n, 0:n]; r = np.hypot((x + 0.5) / n * 2 - 1, (y + 0.5) / n * 2 - 1)
    a = np.clip(np.exp(-(r * 2.1) ** 2) * 1.05, 0, 1) * np.clip(2.2 * (1 - r), 0, 1)
    t = np.clip(1 - r * 1.15, 0, 1)
    img = np.zeros((n, n, 4), np.uint8)
    img[..., 0] = 255
    img[..., 1] = np.clip(60 + 195 * t ** 1.4, 0, 255)
    img[..., 2] = np.clip(20 + 200 * t ** 3.0, 0, 255)
    img[..., 3] = np.clip(a * 255, 0, 255)
    Image.fromarray(img, "RGBA").save(path, optimize=True)


def make_slices(tf, align_scale, align_shift, C, levels, res_mm, out, ext):
    """Axial T1 slices of the MNI152NLin2009cAsym 1 mm brain, resampled into scene space with the SAME per-axis fit as the aseg meshes.
    Window: [p2, p99.7] of the non-zero voxels -> 0..1, gamma 0.85; alpha from intensity: smoothstep(0.07, 0.42). Returns (docs, window).
    Both ends of the window clip and both are declared: the top (>= p99.7) and the bottom (<= p2, drawn as the darkest colour), plus the share of tissue
    that falls under the alpha ramp and is fully transparent (law 23: say what a window throws away)."""
    import nibabel as nib
    from scipy.ndimage import map_coordinates
    img = nib.load(Path(tf) / "MNI152NLin2009cAsym/tpl-MNI152NLin2009cAsym_res-01_desc-brain_T1w.nii.gz")
    T = np.asarray(img.dataobj, np.float32); nz = T[T > 0]
    lo, hi = np.percentile(nz, [2, 99.7])
    inv = np.linalg.inv(img.affine)
    (x0, x1), (z0, z1) = ext
    nx = int(round((x1 - x0) / res_mm)); nzp = int(round((z1 - z0) / res_mm))
    xs = x0 + (np.arange(nx) + 0.5) * (x1 - x0) / nx
    zs = z1 - (np.arange(nzp) + 0.5) * (z1 - z0) / nzp           # row 0 = posterior-most z1?  we want row 0 = anterior (z0, most negative)
    zs = zs[::-1]                                                  # ascending z: row 0 = z0 = anterior
    X, Z = np.meshgrid(xs, zs)
    out.mkdir(parents=True, exist_ok=True); docs = []; clipped = []; clipped_lo = []; transparent = []
    for i, y in enumerate(levels):
        ras = np.stack([X + C[0], -(Z + C[2]), np.full_like(X, y + C[1])], -1)          # scene -> fsaverage RAS
        mni = (ras - align_shift) / align_scale
        vox = (inv @ np.concatenate([mni.reshape(-1, 3), np.ones((mni.size // 3, 1))], 1).T)[:3]
        val = map_coordinates(T, vox, order=1, mode="constant", cval=0).reshape(X.shape)
        nrm = np.clip((val - lo) / (hi - lo), 0, 1) ** 0.85
        tis = max(1, int((val > 0).sum()))
        clipped.append(float(((val >= hi).sum()) / tis))                      # tissue voxels at or above the window top (drawn at the top colour)
        clipped_lo.append(float((((val > 0) & (val <= lo)).sum()) / tis))     # tissue voxels at or below the window bottom (drawn at the bottom colour)
        transparent.append(float((((val > 0) & (nrm < 0.07)).sum()) / tis))  # tissue voxels whose alpha is exactly 0 (below the alpha ramp)
        t = np.clip((nrm - 0.07) / 0.35, 0, 1); alpha = t * t * (3 - 2 * t) * 0.9
        lut = np.array([[0.06, 0.20, 0.42], [0.32, 0.66, 0.92], [0.92, 0.98, 1.0]])
        c = np.where(nrm[..., None] < 0.5, lut[0] + (lut[1] - lut[0]) * (nrm[..., None] / 0.5), lut[1] + (lut[2] - lut[1]) * ((nrm[..., None] - 0.5) / 0.5))
        rgba = np.concatenate([c, alpha[..., None]], -1)
        # thin bright frame so each plane reads as a plane
        e = max(1, int(round(0.9 / res_mm))); rgba[:e, :, :] = [0.5, 0.85, 1.0, 0.55]; rgba[-e:, :, :] = [0.5, 0.85, 1.0, 0.55]
        rgba[:, :e, :] = [0.5, 0.85, 1.0, 0.55]; rgba[:, -e:, :] = [0.5, 0.85, 1.0, 0.55]
        p = out / f"slice_{i}.png"
        Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").save(p, optimize=True)
        docs.append(dict(file=f"tex/slice_{i}.png", y=float(y), size=[nx, nzp], bytes=p.stat().st_size, sha256=sha(p.read_bytes())))
    return docs, dict(low=float(lo), high=float(hi), percentiles=[2, 99.7], gamma=0.85, alpha="smoothstep(0.07,0.42)*0.9", clipped_fraction_mean=float(np.mean(clipped)),
                      clipped_low_fraction_mean=float(np.mean(clipped_lo)), transparent_fraction_mean=float(np.mean(transparent)),
                      px_mm=res_mm, source="tpl-MNI152NLin2009cAsym_res-01_desc-brain_T1w (Fonov 2009/2011, MNI licence text)")

# ======================================================================================== synthetic tracts
class Tracts:
    """SYNTHETIC white-matter arcs. Bundles connect Desikan regions (their real vertices, pulled inward) along smooth trunks through anatomically
    motivated waypoints. Nothing here is tractography of any subject; the picture is an illustration of how diffusion tractography looks."""
    def __init__(self, V, N, LAB, regions, deep, rng, npts):
        self.V, self.N, self.LAB, self.rng, self.npts = V, N, LAB, rng, npts
        self.key = {(r["hemi"], r["desikan_label"]): r["desikan_index"] for r in regions if r["desikan_label"]}
        self.cent = {(r["hemi"], r["desikan_label"]): np.array(r["centroid"]) for r in regions if r["desikan_label"]}
        self.deep = deep
        allv = np.concatenate([V["L"], V["R"]]); alln = np.concatenate([N["L"], N["R"]])
        self.tree = cKDTree(allv); self.alln = alln; self.allv = allv
        self.fibres = []; self.groups = []

    def region(self, h, names, n, depth=(4.0, 9.0)):
        pts = []
        for nm in names:
            idx = np.flatnonzero(self.LAB[h] == self.key[(h, nm)])
            if len(idx):
                pts.append(idx)
        idx = np.concatenate(pts)
        pick = self.rng.choice(idx, n, replace=len(idx) < n)
        return self.V[h][pick] - self.N[h][pick] * self.rng.uniform(*depth, (n, 1))

    def mesh_pts(self, name, n, side=None, sel=None):
        v = self.deep[name]
        m = np.ones(len(v), bool)
        if side is not None:
            m &= (v[:, 0] * side > 0)
        if sel is not None:
            m &= sel(v)
        idx = np.flatnonzero(m)
        return v[self.rng.choice(idx, n, replace=len(idx) < n)]

    @staticmethod
    def spline(pts, t):
        """Centripetal-ish Catmull-Rom through pts (k,3), t in [0,1] -> (len(t),3)."""
        P = np.asarray(pts, float)
        P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
        seg = len(P) - 3
        u = np.clip(t, 0, 1 - 1e-9) * seg; i = np.floor(u).astype(int); f = (u - i)[:, None]
        p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
        return 0.5 * ((2 * p1) + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * f ** 3)

    def bundle(self, group, A, B, way, n, spread=2.6, jitter=0.9, bright=1.0):
        """A, B: (n,3) fibre end points just under the cortex (or inside a deep structure); way: waypoints between the means."""
        rng = self.rng; t = np.linspace(0, 1, self.npts)
        A0, B0 = A.mean(0), B.mean(0)
        trunk = self.spline([A0] + list(way) + [B0], t)
        tan = np.gradient(trunk, axis=0); tan /= np.linalg.norm(tan, axis=1, keepdims=True)
        a1 = np.cross(tan, [0.31, 0.93, 0.2]); a1 /= np.linalg.norm(a1, axis=1, keepdims=True); a2 = np.cross(tan, a1)
        wA = ((1 - t) ** 3.2)[None, :, None]; wB = (t ** 3.2)[None, :, None]
        env = (np.sin(np.pi * t) ** 0.6)[None, :, None]
        r = spread * np.abs(rng.normal(0, 0.55, (n, 1, 1))); ph = rng.uniform(0, 2 * np.pi, (n, 1, 1))
        cross = env * r * (np.cos(ph) * a1[None] + np.sin(ph) * a2[None])
        # smooth per-fibre wiggle (low-frequency), zero at both ends
        wig = sum(np.sin(np.pi * (k + 1) * t)[None, :, None] / (k + 1) * rng.normal(0, 1, (n, 1, 3)) for k in range(3)) * jitter * 0.45
        fib = trunk[None] + wA * (A[:, None, :] - A0) + wB * (B[:, None, :] - B0) + cross + wig
        self.fibres.append(fib); self.groups.append((group, n, bright))

    def inside_fix(self):
        """Pull any point that left the pial surface back under it (nearest-vertex normal test, two passes)."""
        F = np.concatenate(self.fibres)
        P = F.reshape(-1, 3).copy(); t = np.tile(np.linspace(0, 1, self.npts), len(F))
        mid = (t > 0.04) & (t < 0.96); moved = 0
        for _ in range(3):
            d, j = self.tree.query(P[mid])
            dist = np.einsum("ij,ij->i", P[mid] - self.allv[j], self.alln[j])
            bad = dist > -1.2
            if not bad.any():
                break
            sub = P[mid]; sub[bad] -= self.alln[j][bad] * (dist[bad][:, None] + 3.0); P[mid] = sub; moved += int(bad.sum())
        return P.reshape(F.shape), moved

    def build(self):
        from scipy.ndimage import gaussian_filter1d
        P, moved = self.inside_fix()
        P = gaussian_filter1d(P, 1.6, axis=1, mode="nearest")                          # remove the kinks the inside test leaves behind
        tan = np.gradient(P, axis=1); tan /= np.maximum(np.linalg.norm(tan, axis=2, keepdims=True), 1e-9)
        w = np.abs(tan)[..., [0, 2, 1]]                                # weights: left-right (x), anterior-posterior (scene z), superior-inferior (scene y)
        w = (w / w.max(2, keepdims=True)) ** 1.5
        pal = np.array([[1.0, 0.16, 0.14], [0.20, 1.0, 0.26], [0.26, 0.44, 1.0]])   # luminous R, G, B so the blue reads on black
        col = np.clip(w @ pal, 0, 1)
        rng = self.rng; nf = len(P)
        pulse = np.exp(-((np.linspace(0, 1, self.npts)[None, :] - rng.uniform(0, 1, (nf, 1))) / 0.13) ** 2)
        br = np.concatenate([np.full(n, b) for (_, n, b) in self.groups])[:, None]
        bright = np.clip((0.62 + 0.38 * pulse) * br * rng.uniform(0.8, 1.0, (nf, 1)), 0, 1)
        col = np.clip(col * bright[..., None] + 0.55 * (bright[..., None] ** 6) * np.clip(1 - col, 0, 1), 0, 1)   # white-hot where pulses peak
        return P, col, moved


def build_tracts(ctx, scale, npts, rng):
    V, N, LAB, regions, deep = ctx["V"], ctx["N"], ctx["LAB"], ctx["regions"], ctx["deep"]
    T = Tracts(V, N, LAB, regions, deep, rng, npts)
    cn = lambda h, nm: T.cent[(h, nm)]
    dc = {r["id"]: r for r in regions if r["id"].startswith("deep-")}
    cen = lambda nm, side: np.array(dc["deep-" + nm]["centroid_L" if side < 0 else "centroid_R"])
    N_ = lambda k: max(3, int(round(k * scale)))
    # ---- commissural: corpus callosum, homologous regions, one coronal arch each
    cc = [("superiorfrontal", 70), ("caudalmiddlefrontal", 40), ("rostralmiddlefrontal", 42), ("precentral", 34), ("frontalpole", 12), ("lateralorbitofrontal", 10),
          ("medialorbitofrontal", 10), ("parstriangularis", 9), ("postcentral", 26), ("superiorparietal", 38), ("inferiorparietal", 30), ("precuneus", 28), ("supramarginal", 20),
          ("paracentral", 16), ("superiortemporal", 20), ("middletemporal", 16), ("inferiortemporal", 9), ("lateraloccipital", 36), ("cuneus", 14), ("lingual", 12),
          ("pericalcarine", 8), ("isthmuscingulate", 7), ("posteriorcingulate", 8), ("caudalanteriorcingulate", 7)]
    for nm, n in cc:
        n = N_(n); A = T.region("L", [nm], n, (5, 11)); B = T.region("R", [nm], n, (5, 11))
        A0, B0 = A.mean(0), B.mean(0); zm = 0.5 * (A0[2] + B0[2]); ym = 0.5 * (A0[1] + B0[1])
        za = float(np.clip(0.62 * zm - 4.0, -44, 22))                              # callosal crossing point, anterior-posterior (compressed to genu..splenium)
        apex = 17.0 - 11.0 * ((za + 8.0) / 58.0) ** 2 + 0.10 * (ym - 20)           # callosal roof (scene y) at that position
        way = [np.array([A0[0] * 0.80, apex + 0.12 * (A0[1] - apex) + 3, A0[2] + 0.5 * (za - A0[2])]), np.array([A0[0] * 0.40, apex + 2, za]), np.array([0.0, apex, za]),
               np.array([B0[0] * 0.40, apex + 2, za]), np.array([B0[0] * 0.80, apex + 0.12 * (B0[1] - apex) + 3, B0[2] + 0.5 * (za - B0[2])])]
        T.bundle("cc", A, B, way, n, spread=4.6, jitter=0.8, bright=1.0)
    for side, h in ((-1, "L"), (1, "R")):
        cap = 0.5 * (cen("putamen", side) + cen("thalamus", side)) + np.array([0, 6, 0])
        bs = deep["brainstem"]; bsc = bs.mean(0)
        # ---- projection: corticospinal tract (cortex -> internal capsule -> cerebral peduncle -> pons)
        n = N_(70); A = T.region(h, ["precentral", "paracentral", "postcentral"], n, (5, 10))
        B = T.mesh_pts("brainstem", n, side=None, sel=lambda v: (v[:, 1] < bsc[1] - 12) & (v[:, 0] * side > -4))
        A0 = A.mean(0)
        T.bundle("cst", A, B, [A0 * np.array([0.8, 0.45, 1.0]) + np.array([0, 10, 0]), cap, np.array([side * 10, bsc[1] + 4, bsc[2] - 3])], n, spread=3.0, jitter=0.8, bright=1.0)
        # ---- thalamic radiations (corona radiata fans)
        for nm, k in (("precentral", 16), ("postcentral", 14), ("superiorfrontal", 14), ("caudalmiddlefrontal", 12), ("superiorparietal", 14), ("supramarginal", 10), ("rostralmiddlefrontal", 12)):
            n = N_(k); A = T.mesh_pts("thalamus", n, side=side); B = T.region(h, [nm], n, (4, 9))
            T.bundle("thal", A, B, [0.5 * (A.mean(0) + B.mean(0)) + np.array([side * 4, 8, 0])], n, spread=2.2, jitter=0.7, bright=0.95)
        # ---- optic radiation (Meyer loop)
        n = N_(34); A = T.mesh_pts("thalamus", n, side=side, sel=lambda v: v[:, 2] > deep["thalamus"][:, 2].mean() + 2); B = T.region(h, ["pericalcarine", "cuneus", "lingual"], n, (3, 7))
        A0 = A.mean(0)
        T.bundle("optic", A, B, [A0 + np.array([side * 16, -4, 10]), A0 + np.array([side * 24, -3, 40]), A0 * np.array([1, 1, 1]) + np.array([side * 14, 0, 70])], n, spread=2.4, jitter=0.7, bright=0.95)
        # ---- association: arcuate / superior longitudinal fasciculus
        n = N_(48); A = T.region(h, ["caudalmiddlefrontal", "parsopercularis", "precentral"], n, (4, 9)); B = T.region(h, ["supramarginal", "superiortemporal", "bankssts"], n, (4, 9))
        mid = 0.5 * (A.mean(0) + B.mean(0))
        T.bundle("arcuate", A, B, [A.mean(0) * np.array([0.9, 1.0, 1.0]) + np.array([0, 14, 12]), mid + np.array([-side * 6, 22, 0]), B.mean(0) + np.array([0, 12, -10])], n, spread=2.6, jitter=0.8, bright=0.82)
        n = N_(36); A = T.region(h, ["rostralmiddlefrontal", "caudalmiddlefrontal", "superiorfrontal"], n, (4, 9)); B = T.region(h, ["inferiorparietal", "superiorparietal", "supramarginal"], n, (4, 9))
        T.bundle("slf", A, B, [0.5 * (A.mean(0) + B.mean(0)) + np.array([-side * 3, 14, 0])], n, spread=3.2, jitter=0.9, bright=0.8)
        # ---- cingulum (follows the cingulate gyrus)
        chain = [cn(h, nm) for nm in ("rostralanteriorcingulate", "caudalanteriorcingulate", "posteriorcingulate", "isthmuscingulate")]
        chain = [c + np.array([side * 7.0, 4.0, 0.0]) for c in chain]
        n = N_(34); A = T.region(h, ["rostralanteriorcingulate", "medialorbitofrontal"], n, (3, 6)); B = T.region(h, ["parahippocampal", "entorhinal"], n, (3, 6))
        T.bundle("cingulum", A, B, chain + [np.array([chain[-1][0] + side * 2, chain[-1][1] - 14, chain[-1][2] + 6])], n, spread=1.6, jitter=0.5)
        # ---- uncinate (frontal -> hook -> temporal pole), IFOF, ILF
        ins = cn(h, "insula") * np.array([0.78, 1, 1])
        n = N_(26); A = T.region(h, ["lateralorbitofrontal", "medialorbitofrontal"], n, (4, 8)); B = T.region(h, ["temporalpole"], n, (3, 7))
        T.bundle("uncinate", A, B, [A.mean(0) + np.array([side * 6, -6, 22]), ins + np.array([0, -14, -8]), B.mean(0) + np.array([-side * 4, 8, -8])], n, spread=1.8, jitter=0.6)
        n = N_(40); A = T.region(h, ["lateralorbitofrontal", "rostralmiddlefrontal", "parstriangularis"], n, (4, 8)); B = T.region(h, ["lateraloccipital", "cuneus", "lingual"], n, (4, 8))
        T.bundle("ifof", A, B, [A.mean(0) + np.array([side * -4, -6, 24]), ins + np.array([0, -3, 6]), 0.5 * (ins + B.mean(0)) + np.array([0, -2, 0])], n, spread=2.4, jitter=0.7, bright=0.82)
        n = N_(30); A = T.region(h, ["temporalpole", "middletemporal"], n, (4, 8)); B = T.region(h, ["lateraloccipital", "lingual"], n, (4, 8))
        T.bundle("ilf", A, B, [cn(h, "inferiortemporal") * np.array([0.78, 1, 1]) + np.array([0, 2, -22]), cn(h, "fusiform") * np.array([0.8, 1, 1]) + np.array([0, 3, 18])], n, spread=2.0, jitter=0.7)
        # ---- cerebellar peduncles
        n = N_(20); A = T.mesh_pts("brainstem", n, sel=lambda v: v[:, 1] < bsc[1] - 4); B = T.mesh_pts("cerebellum", n, side=side)
        T.bundle("cereb", A, B, [bsc + np.array([side * 14, -8, 12]), 0.5 * (bsc + B.mean(0)) + np.array([side * 8, -6, 6])], n, spread=2.0, jitter=0.6, bright=0.9)
    # ---- short association (U) fibres between neighbouring gyri
    Vall = np.concatenate([V["L"], V["R"]]); Nall = np.concatenate([N["L"], N["R"]]); lab_all = np.concatenate([LAB["L"], LAB["R"] + 1000])
    keep = np.flatnonzero((np.concatenate([LAB["L"], LAB["R"]]) > 4))
    tree2 = cKDTree(Vall)
    nU = N_(70); src = rng.choice(keep, nU)
    A = Vall[src] - Nall[src] * rng.uniform(3, 6, (nU, 1))
    dst = []
    for s in src:
        nb = tree2.query_ball_point(Vall[s], 34.0)
        cand = [j for j in nb if np.linalg.norm(Vall[j] - Vall[s]) > 14.0 and lab_all[j] != lab_all[s]]
        dst.append(rng.choice(cand) if cand else s)
    dst = np.array(dst); B = Vall[dst] - Nall[dst] * rng.uniform(3, 6, (nU, 1))
    good = dst != src
    for a, b in zip(A[good], B[good]):
        mid = 0.5 * (a + b); depth = 5 + 0.3 * np.linalg.norm(a - b)
        inward = -(Nall[tree2.query(mid)[1]])
        T.bundle("u", a[None], b[None], [mid + inward * depth], 1, spread=0.0, jitter=0.5, bright=0.55)
    return T

# ======================================================================================== scene writer
STRUCT_ORDER = ["thalamus", "caudate", "putamen", "pallidum", "hippocampus", "amygdala", "accumbens", "ventricles", "brainstem", "cerebellum"]
# base colour, emissive factor, metallic, roughness, transparency  (hero = glowing gold; the bronze/cutaway look is these values with metallic up, emissive down)
MAT = dict(thalamus=((1.0, 0.58, 0.10), 0.56, 0.9, 0.14, 0.0), caudate=((0.90, 0.50, 0.12), 0.32, 0.8, 0.24, 0.90), putamen=((1.0, 0.58, 0.14), 0.32, 0.8, 0.24, 0.90),
           pallidum=((1.0, 0.66, 0.20), 0.56, 0.9, 0.14, 0.0), hippocampus=((1.0, 0.62, 0.14), 0.56, 0.9, 0.14, 0.0), amygdala=((1.0, 0.45, 0.20), 0.36, 0.8, 0.22, 0.90),
           accumbens=((1.0, 0.90, 0.45), 0.38, 0.8, 0.20, 0.90), ventricles=((0.50, 0.80, 1.0), 0.30, 0.0, 0.2, 0.90), brainstem=((1.0, 0.56, 0.10), 0.56, 0.9, 0.14, 0.0),
           cerebellum=((0.30, 0.44, 0.85), 0.14, 0.0, 0.65, 0.76))
# the hero glass look shows only the thalamus, pallidum, hippocampus and brainstem as glossy gold cores; the other deep structures are faint ghosts (still pickable).
# The golden-cutaway preset restores the bronze set below (every structure opaque, metallic, warm).
BRONZE = dict(thalamus=(1.0, 0.74, 0.20), caudate=(0.90, 0.50, 0.12), putamen=(1.0, 0.58, 0.14), pallidum=(1.0, 0.84, 0.36), hippocampus=(1.0, 0.80, 0.30),
              amygdala=(1.0, 0.45, 0.20), accumbens=(1.0, 0.90, 0.45), brainstem=(1.0, 0.72, 0.24), cerebellum=(0.78, 0.44, 0.15))



# ======================================================================================== presets (what the page flips; the same operations the render checks used)
def _both(field, value):
    return [[f"SH_CORTEX_{h}", field, value] for h in "LR"]

# under an opaque (wet) cortex the cerebellum, which hangs below it, is a solid warm structure again, not the cool glass-look ghost
_WET_CEREBELLUM = [["MAT_cerebellum", "transparency", 0], ["MAT_cerebellum", "baseColor", "0.78 0.44 0.15"], ["MAT_cerebellum", "emissiveColor", "0.109 0.062 0.021"],
                   ["MAT_cerebellum", "metallic", 0.0], ["MAT_cerebellum", "roughness", 0.45]]

PRESETS = {
    "_doc": "Each preset = a view (Viewpoint DEF to bind), field operations [DEF, field, value] applied through SAI, and the X_ITE browser options used when it was checked. "
            "Operations are relative to the file as written (glass cortex, deep structures, aura and stage on; everything else hidden). Render checks used Chromium headless on SwiftShader, X_ITE 16.6.0.",
    "browser": {"ToneMapping": "KHR_PBR_NEUTRAL"},
    "glass": {"view": "VP_HOME", "ops": []},
    "tracts": {"view": "VP_HOME", "ops": [["SW_TRACTS", "whichChoice", 0], ["SW_AURA", "whichChoice", -1], ["SW_DEEP", "whichChoice", -1]]
               + _both("baseAlpha", 0.012) + _both("sulcAlpha", 0.12) + _both("rimAlpha", 0.3) + _both("specular", 0.0) + _both("edgeAlpha", 0.25)},
    "wet": {"view": "VP_HOME", "ops": [["SW_CORTEX", "whichChoice", -1], ["SW_AURA", "whichChoice", -1], ["SW_WET", "whichChoice", 0], ["ENV", "intensity", 0.95]] + _WET_CEREBELLUM},
    "golden": {"view": "VP_MEDIAL", "ops": [["SW_HEMI_L", "whichChoice", -1], ["SW_WETHEMI_L", "whichChoice", -1], ["SW_CORTEX", "whichChoice", -1], ["SW_AURA", "whichChoice", -1],
               ["SW_WET", "whichChoice", 0], ["SW_PEDESTAL", "whichChoice", 0], ["SW_STAGE", "whichChoice", -1], ["CLIP_MIDSAG", "enabled", True],
               ["BG", "skyColor", "0.02 0.012 0.008 0.05 0.03 0.016 0.1 0.06 0.03"], ["BG", "groundColor", "0.01 0.006 0.004 0.04 0.025 0.012 0.1 0.06 0.03"],
               ["KEY", "color", "1 0.86 0.64"], ["KEY", "intensity", 2.6], ["FILL", "color", "0.9 0.6 0.35"], ["FILL", "intensity", 1.0], ["RIM", "intensity", 1.6], ["ENV", "intensity", 1.2]]
               + [[f"MAT_{k}", "baseColor", fl(BRONZE[k], 3)] for k in STRUCT_ORDER if k != "ventricles"]
               + [[f"MAT_{k}", "emissiveColor", " ".join(f"{c * 0.16:.3f}" for c in BRONZE[k])] for k in STRUCT_ORDER if k != "ventricles"]
               + [[f"MAT_{k}", "metallic", 0.85] for k in STRUCT_ORDER if k != "ventricles"] + [[f"MAT_{k}", "roughness", 0.26] for k in STRUCT_ORDER if k != "ventricles"]
               + [[f"MAT_{k}", "transparency", 0] for k in STRUCT_ORDER if k != "ventricles"]},
    "slices": {"view": "VP_HOME", "ops": [["SW_SLICES", "whichChoice", 0], ["SW_AURA", "whichChoice", -1]] + _both("baseAlpha", 0.01) + _both("sulcAlpha", 0.15) + _both("rimAlpha", 0.35) + _both("edgeAlpha", 0.25)},
    "activation": {"view": "VP_LEFT", "ops": [["SW_ACTIV", "whichChoice", 0]]},
    "labels": {"view": "VP_LEFT", "ops": [["SW_LABELS", "whichChoice", 0], ["SW_CORTEX", "whichChoice", -1], ["SW_AURA", "whichChoice", -1], ["SW_WET", "whichChoice", 0], ["SW_LBL_R", "whichChoice", -1]] + _WET_CEREBELLUM},
    "inside": {"view": "VP_INSIDE", "ops": [["SW_TRACTS", "whichChoice", 0], ["SW_AURA", "whichChoice", -1]]},
}

def tri_geo(v, f, nd, n=None, color=None, defname=None, solid=False, wet_u=None):
    n = vertex_normals(v, f) if n is None else n
    d = f" DEF='{defname}'" if defname else ""
    c = f"<Color color='{fl(color, 2)}'/>" if color is not None else ""
    if wet_u is not None:                                         # u in [0.01, 0.99]: the ramp texture is clamped, but keep clear of the very ends (no wrap blend)
        c += "<TextureCoordinate point='" + " ".join(f"{0.01 + 0.98 * float(x):.3f} 0.5" for x in wet_u) + "'/>"
    return (f"<IndexedTriangleSet{d} index='{il(f)}' solid='{'true' if solid else 'false'}'><Coordinate point='{fl(v, nd)}'/><Normal vector='{fl(n, 2)}'/>{c}</IndexedTriangleSet>")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--npz", required=True); ap.add_argument("--regions", required=True); ap.add_argument("--tf", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--lite", action="store_true")
    ap.add_argument("--prep-report", help="mesh_report_<den>.json (alignment, AO provenance) to quote in WorldInfo")
    ap.add_argument("--audio", default="audio/m01-drift.ogg"); ap.add_argument("--seed", type=int, default=20261106)
    ap.add_argument("--tract-scale", type=float); ap.add_argument("--tract-points", type=int)
    ap.add_argument("--keep-medial-wall", action="store_true"); ap.add_argument("--presets", help="write the mode presets (view + SAI operations) to this json")
    a = ap.parse_args()
    t0 = time.time(); out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True); tex = out.parent / "tex"; tex.mkdir(exist_ok=True)
    rng = np.random.default_rng(a.seed)
    lite = a.lite
    nd_v = 1 if lite else 2                                       # coordinate decimals (mm)
    npz = np.load(a.npz); regions = json.load(open(a.regions))
    prep = json.load(open(a.prep_report)) if a.prep_report else {}
    V = {h: npz[f"v{h}"].astype(np.float64) for h in "LR"}; F = {h: npz[f"f{h}"].astype(np.int64) for h in "LR"}
    LAB = {h: npz[f"lab{h}"].astype(int) for h in "LR"}
    N = {h: vertex_normals(V[h], F[h]) for h in "LR"}
    deep = {k: npz[f"sv_{k}"].astype(np.float64) for k in STRUCT_ORDER}; deepf = {k: npz[f"sf_{k}"].astype(np.int64) for k in STRUCT_ORDER}
    C = npz["C"]; al_s = npz["align_scale"]; al_t = npz["align_shift"]
    # ------------------------------------------------------------------ AO
    nL = len(V["L"])
    if "ao" in npz.files:
        ao_all = npz["ao"].astype(np.float64); ao_src = "Cycles per-vertex AO bake (bake_out_%s.npz), matches mesh vertex for vertex" % ("10k" if lite else "41k")
    else:
        ao_all = np.concatenate([1 - np.clip((npz[f"sulc{h}"] + 1.2) / 2.4, 0, 1) * 0.75 for h in "LR"]); ao_src = "sulc used as AO (no matching bake)"
    sulc_all = np.concatenate([npz["sulcL"], npz["sulcR"]]).astype(np.float64)
    crown = 1 - np.clip((sulc_all + 0.9) / 1.8, 0, 1)             # 1 on gyral crowns, 0 in sulcal fundi
    ao_mix = np.clip(0.80 * ao_all + 0.20 * crown, 0, 1)
    AO = {"L": ao_mix[:nL], "R": ao_mix[nL:]}

    def occl(ao):
        s = np.clip((ao - 0.05) / 0.75, 0, 1); return s * s * (3 - 2 * s)

    def vcol(ao):
        """Vertex colour = wet-cortex tint (ivory crowns, bronze fundi); the glass shader recovers its occlusion s from the green channel: s = (g - 0.17) / 0.83."""
        s = occl(ao)
        return np.stack([0.34 + 0.66 * s ** 0.55, 0.17 + 0.83 * s, 0.06 + 0.94 * s ** 1.5], 1)

    # ------------------------------------------------------------------ cortex geometry (medial wall removed so the deep structures are visible from the medial side)
    geo = {}
    for h in "LR":
        f = F[h]
        if not a.keep_medial_wall:
            mw = np.isin(LAB[h], [0, 4])
            f = f[~mw[f].all(1)]
        geo[h] = f
    # ------------------------------------------------------------------ tracts
    scale = a.tract_scale if a.tract_scale is not None else (0.34 if lite else 0.75)
    npts = a.tract_points if a.tract_points is not None else (28 if lite else 40)
    ctx = dict(V=V, N=N, LAB=LAB, regions=regions, deep=deep)
    T = build_tracts(ctx, scale, npts, rng)
    P, TC, moved = T.build()
    nfib = len(P); tr_pts = P.reshape(-1, 3); tr_col = TC.reshape(-1, 3)
    coord_idx = np.arange(nfib * npts).reshape(nfib, npts); coord_idx = np.concatenate([coord_idx, np.full((nfib, 1), -1)], 1)
    group_counts = {}
    for g, n, _ in T.groups:
        group_counts[g] = group_counts.get(g, 0) + n
    # ------------------------------------------------------------------ slices & sprites
    levels = [-40, -22, -4, 14, 32, 50]
    ext = ((-82, 82), (-112, 92))
    sl_docs, window = make_slices(a.tf, al_s, al_t, C, levels, 1.1 if lite else 0.7, tex / "slices_tmp", ext)
    for p in (tex / "slices_tmp").glob("*.png"):
        p.replace(tex / p.name)
    (tex / "slices_tmp").rmdir()
    studio_faces(tex / "env64", 64)
    sprite_png(tex / "glow_halo.png", 256, (0.20, 0.62, 0.95), 1.9, 0.26, aspect=1.0)
    sprite_png(tex / "floor_pool.png", 256, (1.0, 0.62, 0.30), 2.1, 0.30, rgb2=(0.25, 0.65, 1.0))      # warm amber under the brainstem, cool cyan at the rim: the "ground reflection" of the hero look
    sprite_png(tex / "core_glow.png", 256, (1.0, 0.70, 0.18), 1.5, 0.80)        # warm gold bloom around the deep structures (part of the Glow option)
    heat_png(tex / "blob.png", 128)
    wet_ramp_png(tex / "wet_ramp.png")

    # ------------------------------------------------------------------ XML
    comps = ("Core", "Time", "Grouping", "Rendering", "Shape", "Geometry3D", "Text", "Sound", "Lighting", "Texturing", "CubeMapTexturing", "Navigation", "Shaders", "EnvironmentalEffects", "PointingDeviceSensor")
    levels_c = {"Shape": 2, "Lighting": 3, "Rendering": 5, "Shaders": 1, "CubeMapTexturing": 1, "Navigation": 2, "Texturing": 3, "Sound": 1, "Text": 1, "Grouping": 2,
                "EnvironmentalEffects": 1, "PointingDeviceSensor": 1, "Geometry3D": 3}
    x = []
    W = x.append
    W("<?xml version='1.0' encoding='UTF-8'?>\n<X3D profile='Immersive' version='4.1' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.1.xsd'>\n")
    W("<head>" + "".join(f"<component name='{k}' level='{v}'/>" for k, v in levels_c.items() if k in ("Shaders", "CubeMapTexturing", "Lighting", "Shape", "Sound", "Navigation", "Text", "Texturing", "Rendering", "Grouping", "EnvironmentalEffects", "PointingDeviceSensor", "Geometry3D")))
    W(f"<meta name='title' content='Brain Loom hero scene ({'lite 10k' if lite else 'full 41k'})'/><meta name='description' content='Glass, wet and golden-cutaway brain from fsaverage + MNI152 aseg, with SYNTHETIC tracts. Look-level, not a clinical image.'/>"
      "<meta name='generator' content='x3d.brain/tools/build_brain_scene.py'/><meta name='license' content='derived geometry; see WorldInfo for sources and notices'/></head>\n<Scene>\n")
    builder_sha = sha(Path(__file__).read_bytes())[:16]
    info = [
        "title: Brain Loom hero scene - glass cortex, wet cortex, golden deep structures",
        ("sources: cortex = TemplateFlow tpl-fsaverage %s pial, Desikan-Killiany labels, sulc (FreeSurfer lineage, Fischl et al. 1999; licence grade Suspected, no licence file found). "
         "Geometry is the template's own %s vertex set per hemisphere (a lower-resolution version of the 164k surface that TemplateFlow distributes; NOT decimated by us), moved rigidly "
         "(axes reordered, origin at the pial bounding-box centre) and re-encoded to 0.1 mm with the medial-wall triangles dropped; the cortex itself is not scaled (1.000)"
         % ("10k" if lite else "41k", "10,242" if lite else "40,962")),
        "sources: deep structures = marching cubes on tpl-MNI152NLin2009cAsym 1 mm aseg, T1 slices = same template brain T1w (Fonov 2009 and 2011; permissive MNI licence text, copyright notice retained; grade Confirmed)",
        "ALIGNMENT NOTICE: the deep structures and the T1 slices come from MNI152NLin2009cAsym and are carried into the fsaverage cortex frame by a per-axis scale and shift that makes the two cortex bounding boxes equal (scale %s, shift mm %s; RAS x y z). It is a look-level fit, NOT a registration." % (fl(al_s, 3), fl(al_t, 1)),
        "SYNTHETIC NOTICE: the %d tract arcs (%d points) are generated between Desikan region vertices and are not tractography of any subject or scan. Activation blobs are ILLUSTRATIVE, not measured activity." % (nfib, nfib * npts),
        "AO: " + ao_src,
        ("slice window: T1 intensity %.1f to %.1f (p2 to p99.7 of non-zero voxels), gamma 0.85, alpha smoothstep(0.07,0.42)*0.9; of the tissue voxels on the six slices %.2f%% clip at the top, "
         "%.2f%% clip at the bottom (drawn as the darkest colour) and %.2f%% fall under the alpha ramp and are fully transparent"
         % (window["low"], window["high"], 100 * window["clipped_fraction_mean"], 100 * window["clipped_low_fraction_mean"], 100 * window["transparent_fraction_mean"])),
        "units: 1 scene unit = 1 mm in fsaverage space; x right, y superior, z posterior (anterior is -z); origin at the pial bounding-box centre (RAS x y z = %s mm)" % fl([C[0], -C[2], C[1]], 1),
        "builder: build_brain_scene.py sha256 %s seed %d; mesh npz sha256 %s" % (builder_sha, a.seed, sha(Path(a.npz).read_bytes())[:16]),
        "not a medical device; for demonstration and learning only",
    ]
    W("<WorldInfo title='Brain Loom hero scene' info='" + " ".join(f'"{esc(s)}"' for s in info) + "'/>\n")
    W("<NavigationInfo DEF='NAV' type='\"EXAMINE\" \"ANY\"' headlight='false' speed='1' avatarSize='0.25 1.6 0.75'/>\n")
    W("<Background DEF='BG' skyAngle='1.1 1.571' skyColor='0.002 0.003 0.006 0.006 0.01 0.02 0.012 0.022 0.04' groundAngle='1.0 1.571' groundColor='0.002 0.003 0.006 0.006 0.01 0.02 0.012 0.022 0.04'/>\n")
    W("<DirectionalLight DEF='KEY' direction='0.6 -0.5 -0.7' intensity='1.8' color='1 0.95 0.88' ambientIntensity='0'/>"
      "<DirectionalLight DEF='FILL' direction='-0.7 -0.2 0.5' intensity='0.8' color='0.45 0.7 1' ambientIntensity='0'/>"
      "<DirectionalLight DEF='RIM' direction='0 0.4 1' intensity='1.0' color='1 0.7 0.4' ambientIntensity='0'/>\n")
    W("<EnvironmentLight DEF='ENV' intensity='0.9'><ComposedCubeMapTexture containerField='specularTexture'>" + "".join(
        f"<ImageTexture containerField='{f}Texture' url='\"tex/env64/studio-{f}.png\"'/>" for f in ["front", "back", "left", "right", "top", "bottom"]) + "</ComposedCubeMapTexture></EnvironmentLight>\n")
    # viewpoints (scene axes: anterior = -z, left = -x)
    def vp(defn, d, dist, desc, up=(0, 1, 0), fov=0.56, target=(0, 0, 0), eye=None, cor=None, hint=None):
        d = np.asarray(d, float); d /= np.linalg.norm(d)
        e = np.asarray(eye, float) if eye is not None else np.asarray(target, float) + d * dist
        c = cor if cor is not None else target
        h = f"<MetadataString containerField='metadata' name='pageHint' value='\"{hint}\"'/>" if hint else ""
        W(f"<Viewpoint DEF='{defn}' description='{esc(desc)}' position='{fl(e, 1)}' orientation='{lookat(e, target, up)}' centerOfRotation='{fl(c, 1)}' fieldOfView='{fov}'>{h}</Viewpoint>\n")
    D = 315
    vp("VP_HOME", (-0.93, 0.24, -0.27), 350, "Home: left lateral three-quarter view, slightly from above")
    vp("VP_LEFT", (-1, 0.05, 0.0), D, "Left lateral (anterior to the left of the screen)")
    vp("VP_RIGHT", (1, 0.05, 0.0), D, "Right lateral (anterior to the right of the screen)")
    vp("VP_TOP", (0, 1, 0.001), D * 1.05, "Top view, anterior up", up=(0, 0, -1))
    vp("VP_FRONT", (0.0, 0.08, -1), D * 0.95, "Front (anterior) view")
    vp("VP_MEDIAL", (-1, 0.07, 0.10), D * 0.95, "Medial view: hide the left hemisphere (SW_HEMI_L) to see the right medial wall and deep structures", hint="hide SW_HEMI_L")
    vp("VP_INSIDE", (0, 0, -1), 0, "Inside the brain, behind the thalamus, looking forward along the tracts", fov=1.05, eye=(0, 30, 62), target=(0, -4, -20), cor=(0, -6, 0))
    # ---- stage glow (behind the brain, camera facing) and a floor pool
    W("<Switch DEF='SW_STAGE' whichChoice='0'><Group DEF='G_STAGE'>"
      "<Billboard axisOfRotation='0 0 0'><Transform translation='0 -4 -150'><Shape><Appearance><ImageTexture url='\"tex/glow_halo.png\"'/></Appearance>"
      "<IndexedFaceSet solid='false' coordIndex='0 1 2 3 -1'><Coordinate point='-215 -165 0 215 -165 0 215 165 0 -215 165 0'/><TextureCoordinate point='0 0 1 0 1 1 0 1'/></IndexedFaceSet></Shape></Transform></Billboard>"
      "<Transform translation='0 -90 0'><Shape><Appearance><ImageTexture url='\"tex/floor_pool.png\"'/></Appearance><IndexedFaceSet solid='false' coordIndex='0 1 2 3 -1'>"
      "<Coordinate point='-150 0 150 150 0 150 150 0 -150 -150 0 -150'/><TextureCoordinate point='0 0 1 0 1 1 0 1'/></IndexedFaceSet></Shape></Transform>"
      "</Group></Switch>\n")
    # ---- cortex: glass
    def glass_shader(h):
        return (f"<ComposedShader DEF='SH_CORTEX_{h}' language='GLSL'>"
                "<field name='rimColor' type='SFColor' accessType='inputOutput' value='0.42 0.97 1'/><field name='rimColor2' type='SFColor' accessType='inputOutput' value='1 0.47 0.97'/>"
                "<field name='bodyColor' type='SFColor' accessType='inputOutput' value='0.55 0.78 1'/><field name='rimPower' type='SFFloat' accessType='inputOutput' value='2.2'/>"
                "<field name='baseAlpha' type='SFFloat' accessType='inputOutput' value='0.03'/><field name='rimAlpha' type='SFFloat' accessType='inputOutput' value='1'/>"
                "<field name='aoGamma' type='SFFloat' accessType='inputOutput' value='1.5'/><field name='specular' type='SFFloat' accessType='inputOutput' value='1.6'/>"
                "<field name='backDim' type='SFFloat' accessType='inputOutput' value='0.12'/><field name='sulcAlpha' type='SFFloat' accessType='inputOutput' value='0.5'/><field name='sulcColor' type='SFColor' accessType='inputOutput' value='0.004 0.03 0.06'/><field name='sulcLo' type='SFFloat' accessType='inputOutput' value='0.0'/><field name='sulcHi' type='SFFloat' accessType='inputOutput' value='0.14'/>"
                "<field name='edgeColor' type='SFColor' accessType='inputOutput' value='0.8 0.97 1'/><field name='edgeAlpha' type='SFFloat' accessType='inputOutput' value='0.9'/><field name='edgeLo' type='SFFloat' accessType='inputOutput' value='0.12'/><field name='edgeW' type='SFFloat' accessType='inputOutput' value='0.25'/><field name='farDim' type='SFFloat' accessType='inputOutput' value='0.12'/><field name='farR' type='SFFloat' accessType='inputOutput' value='50'/>"
                f"<ShaderPart type='VERTEX'><![CDATA[data:x-shader/x-vertex,{GLASS_VS}]]></ShaderPart><ShaderPart type='FRAGMENT'><![CDATA[data:x-shader/x-fragment,{GLASS_FS}]]></ShaderPart></ComposedShader>")
    def aura_shader(h):
        return (f"<ComposedShader DEF='SH_AURA_{h}' language='GLSL'>"
                "<field name='auraColor' type='SFColor' accessType='inputOutput' value='0.25 0.8 1'/><field name='auraColor2' type='SFColor' accessType='inputOutput' value='0.8 0.4 1'/>"
                "<field name='auraPower' type='SFFloat' accessType='inputOutput' value='4'/><field name='auraAlpha' type='SFFloat' accessType='inputOutput' value='0.6'/>"
                f"<ShaderPart type='VERTEX'><![CDATA[data:x-shader/x-vertex,{GLASS_VS}]]></ShaderPart><ShaderPart type='FRAGMENT'><![CDATA[data:x-shader/x-fragment,{AURA_FS}]]></ShaderPart></ComposedShader>")
    W("<Switch DEF='SW_CORTEX' whichChoice='0'><Group DEF='G_CORTEX'>\n")
    for h in "LR":
        W(f"<Switch DEF='SW_HEMI_{h}' whichChoice='0'><Group DEF='G_CORTEX_{h}'><Shape DEF='SHAPE_CORTEX_{h}'><Appearance><Material diffuseColor='0 0 0' transparency='0.01'/>{glass_shader(h)}</Appearance>"
          + tri_geo(V[h], geo[h], nd_v, N[h], vcol(AO[h]), defname=f"GEO_CORTEX_{h}", wet_u=occl(AO[h])) + f"</Shape><TouchSensor DEF='TS_CORTEX_{h}' description='cortex {h}'/></Group></Switch>\n")
    W("</Group></Switch>\n")
    # ---- aura: the same glass geometry (USE) a little larger, only its silhouette glows (fake bloom)
    W("<Switch DEF='SW_AURA' whichChoice='0'><Group DEF='G_AURA'><Transform scale='1.03 1.03 1.03'>\n")
    for h in "LR":
        W(f"<Shape DEF='SHAPE_AURA_{h}'><Appearance><Material diffuseColor='0 0 0' transparency='0.01'/>{aura_shader(h)}</Appearance><IndexedTriangleSet USE='GEO_CORTEX_{h}'/></Shape>\n")
    W("</Transform>")
    core = np.mean([deep[k].mean(0) for k in ("thalamus", "caudate", "putamen", "pallidum")], 0)
    W(f"<Billboard axisOfRotation='0 0 0'><Transform translation='{fl(core, 1)}'><Shape><Appearance><ImageTexture url='\"tex/core_glow.png\"'/></Appearance><IndexedFaceSet solid='false' coordIndex='0 1 2 3 -1'>"
      "<Coordinate point='-90 -90 0 90 -90 0 90 90 0 -90 90 0'/><TextureCoordinate point='0 0 1 0 1 1 0 1'/></IndexedFaceSet></Shape></Transform></Billboard>")
    W("</Group></Switch>\n")
    # ---- cortex: wet (same geometry nodes, USE)
    W("<Switch DEF='SW_WET' whichChoice='-1'><Group DEF='G_WET'>\n")
    for h in "LR":
        W(f"<Switch DEF='SW_WETHEMI_{h}' whichChoice='0'><Group DEF='G_WET_{h}'><Shape DEF='SHAPE_WET_{h}'><Appearance><PhysicalMaterial DEF='MAT_WET_{h}' baseColor='0.97 0.87 0.72' metallic='0' roughness='0.36'><ImageTexture containerField='baseTexture' url='\"tex/wet_ramp.png\"' repeatS='false' repeatT='false'/></PhysicalMaterial></Appearance>"
          f"<IndexedTriangleSet USE='GEO_CORTEX_{h}'/></Shape><TouchSensor DEF='TS_WET_{h}' description='wet cortex {h}'/></Group></Switch>\n")
    W("</Group></Switch>\n")
    # ---- deep structures
    W("<Switch DEF='SW_DEEP' whichChoice='0'><Group DEF='G_DEEP'><ClipPlane DEF='CLIP_MIDSAG' enabled='false' plane='1 0 0 0'/>\n")
    deep_tris = 0
    for k in STRUCT_ORDER:
        base, em, met, rough, tr = MAT[k]
        deep_tris += len(deepf[k])
        dn = vertex_normals(deep[k], deepf[k]); dao = concavity_ao(deep[k], deepf[k], dn)
        W(f"<Shape DEF='STRUCT_{k}'><Appearance DEF='APP_{k}'><PhysicalMaterial DEF='MAT_{k}' baseColor='{fl(base, 3)}' emissiveColor='{fl([c * em for c in base], 3)}' metallic='{met}' roughness='{rough}'"
          + (f" transparency='{tr}'" if tr else "") + "/></Appearance>" + tri_geo(deep[k], deepf[k], nd_v, dn, np.stack([dao, dao, dao], 1)) + "</Shape>\n")
    W("</Group></Switch>\n")
    # ---- tracts: core + two translucent halos (same geometry node, USE)
    W("<Switch DEF='SW_TRACTS' whichChoice='-1'><Group DEF='TRACTS'>"
      "<MetadataString containerField='metadata' name='SYNTHETIC' value='\"Synthetic arcs between Desikan region vertices; not tractography of any subject. Colour = direction (red left-right, green anterior-posterior, blue superior-inferior).\"'/>\n")
    W("<Shape DEF='TRACT_HALO2'><Appearance><Material DEF='MAT_TRACT_HALO2' diffuseColor='0 0 0' emissiveColor='1 1 1' transparency='0.72'/><LineProperties applied='true' linewidthScaleFactor='%s'/></Appearance>" % ("10" if lite else "12")
      + f"<IndexedLineSet DEF='GEO_TRACTS' coordIndex='{il(coord_idx)}' colorPerVertex='true'><Coordinate point='{fl(tr_pts, 1)}'/><Color color='{fl(tr_col, 2)}'/></IndexedLineSet></Shape>\n")
    W("<Shape DEF='TRACT_HALO1'><Appearance><Material DEF='MAT_TRACT_HALO1' diffuseColor='0 0 0' emissiveColor='1 1 1' transparency='0.42'/><LineProperties applied='true' linewidthScaleFactor='%s'/></Appearance><IndexedLineSet USE='GEO_TRACTS'/></Shape>\n" % ("5" if lite else "6"))
    W("<Shape DEF='TRACT_CORE'><Appearance><Material DEF='MAT_TRACT_CORE' diffuseColor='0 0 0' emissiveColor='1 1 1'/><LineProperties applied='true' linewidthScaleFactor='3.2'/></Appearance><IndexedLineSet USE='GEO_TRACTS'/></Shape>\n")
    W("</Group></Switch>\n")
    # ---- slices
    W("<Switch DEF='SW_SLICES' whichChoice='-1'><Group DEF='G_SLICES'>"
      "<MetadataString containerField='metadata' name='window' value='\"T1 %.1f-%.1f p2-p99.7 gamma 0.85; alpha smoothstep(0.07,0.42)*0.9; clip top %.2f%%, bottom %.2f%%, fully transparent %.2f%% of tissue voxels; template brain T1w, MNI licence text; scaled and shifted into the cortex frame by the look-level bbox fit\"'/>\n"
      % (window["low"], window["high"], 100 * window["clipped_fraction_mean"], 100 * window["clipped_low_fraction_mean"], 100 * window["transparent_fraction_mean"]))
    (x0, x1), (z0, z1) = ext
    for i, d in enumerate(sl_docs):
        W(f"<Shape DEF='SLICE_{i}'><Appearance><ImageTexture url='\"{d['file']}\"'/></Appearance><IndexedFaceSet solid='false' coordIndex='0 1 2 3 -1'>"
          f"<Coordinate point='{x0} {d['y']:g} {z1} {x1} {d['y']:g} {z1} {x1} {d['y']:g} {z0} {x0} {d['y']:g} {z0}'/><TextureCoordinate point='0 0 1 0 1 1 0 1'/></IndexedFaceSet></Shape>\n")
    W("</Group></Switch>\n")
    # ---- labels
    W("<Switch DEF='SW_LABELS' whichChoice='-1'><Group DEF='G_LABELS'>\n")
    def label(rid, text, pos, size, color):
        sh = "0.01 0.03 0.07"                                                                  # dark offset copy behind the text keeps it legible over pale cortex
        txt = f"<Text string='\"{esc(text)}\"'><FontStyle family='\"SANS\"' size='{size}' justify='\"MIDDLE\" \"MIDDLE\"'/></Text>"
        W(f"<Transform DEF='LBL_{rid.replace('-', '_')}' translation='{fl(pos, 1)}'><Billboard axisOfRotation='0 0 0'>"
          f"<Transform translation='0.45 -0.45 -0.4'><Shape><Appearance><Material diffuseColor='0 0 0' emissiveColor='{sh}'/></Appearance>{txt}</Shape></Transform>"
          f"<Shape><Appearance><Material diffuseColor='0 0 0' emissiveColor='{color}'/></Appearance>{txt}</Shape></Billboard></Transform>\n")
    leaders = {"L": [], "R": [], "B": []}; Vall = np.concatenate([V["L"], V["R"]])
    LSIZE = 4.2
    for hh in "LR":
        items = []
        for r in regions:
            if r["desikan_label"] and r["hemi"] == hh:
                anc = np.array(r["anchor"]); d = anc / np.linalg.norm(anc)                    # label sits outside the pial surface along the ray from the centre through the anchor
                cone = (Vall @ d) > 0.96 * np.linalg.norm(Vall, axis=1); s = float((Vall[cone] @ d).max()) if cone.any() else float(np.linalg.norm(anc))
                items.append([r, anc, d, d * (max(s, np.linalg.norm(anc)) + 13)])
        wid = np.array([len(it[0]["name"]) * LSIZE * 0.52 for it in items])                  # text width estimate, scene units
        P = np.array([it[3] for it in items])
        for _ in range(120):                                                                # de-overlap in the screen plane of the lateral views (horizontal = scene z, vertical = scene y)
            moved = False
            for i in range(len(P)):
                for j in range(i + 1, len(P)):
                    dz, dy = P[i, 2] - P[j, 2], P[i, 1] - P[j, 1]
                    if abs(dz) < 0.5 * (wid[i] + wid[j]) and abs(dy) < LSIZE * 1.7 and abs(P[i, 0] - P[j, 0]) < 60:
                        push = (LSIZE * 1.7 - abs(dy)) * 0.5 + 0.05; sg = 1.0 if dy >= 0 else -1.0
                        P[i, 1] += sg * push; P[j, 1] -= sg * push; moved = True
            if not moved:
                break
        W(f"<Switch DEF='SW_LBL_{hh}' whichChoice='0'><Group>\n")
        for it, pos in zip(items, P):
            r, anc, d = it[0], it[1], it[2]
            label(r["id"], r["name"].lower(), pos, LSIZE, "0.86 0.96 1")
            end = pos - (pos - anc) / np.linalg.norm(pos - anc) * 4.0
            leaders[hh].append((anc, end))
        W("</Group></Switch>\n")
    W("<Switch DEF='SW_LBL_DEEP' whichChoice='0'><Group>\n")
    for r in regions:
        if r["id"].startswith("deep-"):
            c = np.array(r["centroid"]) + np.array([0, 8, 0]) if r["id"] != "deep-cerebellum" else np.array(r["centroid"]) + np.array([0, -18, 18])
            label(r["id"], r["name"].lower(), c, 4.8, "1 0.82 0.45")
    W("</Group></Switch>\n")
    for hh in "LR":
        pts = np.array([q for pr in leaders[hh] for q in pr]); n = len(pts) // 2
        idx = " ".join(f"{2 * i} {2 * i + 1} -1" for i in range(n))
        W(f"<Switch DEF='SW_LBLLINES_{hh}' whichChoice='0'><Shape><Appearance><Material diffuseColor='0 0 0' emissiveColor='0.45 0.75 0.95'/></Appearance><IndexedLineSet coordIndex='{idx}'><Coordinate point='{fl(pts, 1)}'/></IndexedLineSet></Shape></Switch>\n")
    W("</Group></Switch>\n")
    # ---- activation blobs (ILLUSTRATIVE)
    # (name, (hemisphere, Desikan label), radius mm, lift): lift=True sits the glow clear of the lateral surface along the ray from the centre, so an opaque cortex does not swallow it;
    # lift=False keeps the medial / fissure glows on the surface (seen through the glass shell)
    blobs = [("V1_L", ("L", "pericalcarine"), 24, False), ("V1_R", ("R", "pericalcarine"), 24, False), ("AUDITORY_L", ("L", "transversetemporal"), 20, False), ("BROCA_L", ("L", "parsopercularis"), 21, True),
             ("MOTOR_L", ("L", "precentral"), 26, True), ("PRECUNEUS_R", ("R", "precuneus"), 23, False), ("PCC_L", ("L", "posteriorcingulate"), 20, False),
             ("PARIETAL_L", ("L", "supramarginal"), 22, True), ("TEMPORAL_R", ("R", "superiortemporal"), 20, True)]
    rmap = {(r["hemi"], r["desikan_label"]): r for r in regions if r["desikan_label"]}
    W("<Switch DEF='SW_ACTIV' whichChoice='-1'><Group DEF='G_ACTIV'>"
      "<MetadataString containerField='metadata' name='ILLUSTRATIVE' value='\"Illustrative glowing blobs placed at region anchors; not measured activity.\"'/>\n")
    for nm, key, rad, lift in blobs:
        r = rmap[key]; anc = np.array(r["anchor"])
        if lift:
            d = anc / np.linalg.norm(anc); cone = (Vall @ d) > 0.96 * np.linalg.norm(Vall, axis=1)
            pos = d * (max(float((Vall[cone] @ d).max()) if cone.any() else 0.0, float(np.linalg.norm(anc))) + 4.0)
        else:
            pos = anc + np.array(r["anchor_normal"]) * 3
        W(f"<Transform DEF='ACT_{nm}' translation='{fl(pos, 1)}'><Billboard axisOfRotation='0 0 0'><Shape><Appearance><ImageTexture url='\"tex/blob.png\"'/></Appearance>"
          f"<IndexedFaceSet solid='false' coordIndex='0 1 2 3 -1'><Coordinate point='{-rad} {-rad} 0 {rad} {-rad} 0 {rad} {rad} 0 {-rad} {rad} 0'/><TextureCoordinate point='0 0 1 0 1 1 0 1'/></IndexedFaceSet></Shape></Billboard></Transform>\n")
    W("</Group></Switch>\n")
    # ---- pedestal for the golden-cutaway look (bronze plinth and column under the brainstem; hidden by default)
    W("<Switch DEF='SW_PEDESTAL' whichChoice='-1'><Group DEF='G_PEDESTAL'>"
      "<Transform translation='0 -104 10'><Shape><Appearance><PhysicalMaterial DEF='MAT_PLINTH' baseColor='0.42 0.30 0.16' metallic='0.85' roughness='0.42'/></Appearance><Box size='190 10 150'/></Shape></Transform>"
      "<Transform translation='0 -92 8'><Shape><Appearance><PhysicalMaterial DEF='MAT_COLUMN' baseColor='0.55 0.36 0.16' metallic='0.9' roughness='0.35'/></Appearance><Cylinder radius='13' height='18'/></Shape></Transform>"
      "</Group></Switch>\n")
    # ---- sound (not started: startTime far in the future; the page sets startTime to now)
    W(f"<Sound DEF='SND' intensity='0.8' spatialize='false' location='0 0 0'><AudioClip DEF='AUDIO' containerField='source' description='music bed' url='\"{a.audio}\"' loop='true' startTime='4102444800'/></Sound>\n")
    W("</Scene></X3D>\n")
    txt = "".join(x)
    out.write_text(txt, encoding="utf-8")
    cortex_tris = sum(len(geo[h]) for h in "LR")
    rep = dict(out=out.name, bytes=len(txt.encode()), sha256=sha(txt.encode()), cortex_tris=cortex_tris, cortex_verts=sum(len(V[h]) for h in "LR"), deep_tris=deep_tris,
               tract_fibres=nfib, tract_points=nfib * npts, tract_groups=group_counts, tract_points_pulled_inward=moved, ao=ao_src, slices=sl_docs, slice_window=window,
               textures={p.name: p.stat().st_size for p in sorted(tex.glob("*.png"))}, seconds=round(time.time() - t0, 1), builder_sha16=builder_sha)
    print(json.dumps({k: rep[k] for k in ("out", "bytes", "sha256", "cortex_tris", "deep_tris", "tract_fibres", "tract_points", "tract_groups", "tract_points_pulled_inward", "ao", "seconds")}, indent=0))
    print("slices:", [(d["file"], d["bytes"]) for d in sl_docs]); print("window:", window)
    json.dump(rep, open(str(out) + ".build.json", "w"), indent=1)
    if a.presets:
        json.dump(PRESETS, open(a.presets, "w"), indent=1); print("presets ->", a.presets)


if __name__ == "__main__":
    main()
