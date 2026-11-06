#!/usr/bin/env python3
"""Build the wider-medical CT torso scene (X3D) from the TotalSegmentator subject s1397 example data.

Source data (not in this repository): 117 binary segmentation volumes + the CT volume of subject s1397,
resampled to 3 mm (160 x 160 x 273 voxels), distributed as VTK ImageData (.vti, zlib, base64) with a .vtm index.
  Attribution: Wasserthal J. et al., "TotalSegmentator: robust segmentation of 104 anatomic structures in CT images",
  Radiology: Artificial Intelligence 2023, doi 10.1148/ryai.230024 (dataset v2). License: grade LIKELY CC BY 4.0 (inferred from the
  dataset's published terms; the licence record of this copy was not read). Derived outputs here are smoothed, decimated surface meshes: not for diagnosis.

Outputs
  OUT/torso_ct.x3d        full detail (not committed: large)
  OUT/torso_ct_lite.x3d   decimated (target under 3 MB), also copied to --repo-scenes
  OUT/tex/env64/studio-*.png  64 px studio cube faces for the EnvironmentLight (the same files the brain scene uses; the scene names them tex/env64/..., so one copy serves both)

Run:  python3 -I build_torso_scene.py --src <dir holding s1397_resampled.vtm> --out <dir> [--repo-scenes <dir>] [--repo-data <dir>]
        [--template-meshes <meshes_41k.npz from prep_meshes.py (scene axes) or an older RAS bundle with vL, fL, cL ...>] [--cache <dir>] [--variants lite,full]
Also writes torso_regions.json (id, group, volume, centroid, bbox per STRUCT_) and TORSO-NOTICE.md (sources, licence grades, changes).
Needs numpy, scipy, scikit-image, Pillow; fast-simplification is used for quadric decimation when installed
(pip install fast-simplification), else a vertex-clustering fallback is used.

Frame: the data are RAS (x patient-right, y anterior, z superior). Scene = (X, Y, Z) = (x - cx, z - cz, -(y - cy)) in millimetres:
a proper rotation, X patient-right, Y up, Z posterior; the anterior view is therefore looked at from -Z.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import sys
import time
import zlib
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi
from scipy import sparse
from scipy.sparse import csgraph
from skimage.measure import marching_cubes

try:  # quadric decimation (optional)
    import fast_simplification as _fs
except Exception:  # pragma: no cover
    _fs = None

# --------------------------------------------------------------------------------------------
# 1. VTK ImageData reader (no vtk needed): inline base64 + zlib blocks, header encoded separately
# --------------------------------------------------------------------------------------------
_DT = {"UInt8": "u1", "Int8": "i1", "Int16": "<i2", "UInt16": "<u2", "Float32": "<f4", "Int32": "<i4"}


def read_vti(path: Path):
    raw = Path(path).read_bytes()
    m = re.search(rb'<ImageData WholeExtent="([^"]+)" Origin="([^"]+)" Spacing="([^"]+)"', raw)
    ext = list(map(int, m.group(1).split()))
    org = list(map(float, m.group(2).split()))
    spc = list(map(float, m.group(3).split()))
    m = re.search(rb'<DataArray type="(\w+)"[^>]*format="binary"[^>]*>\s*([A-Za-z0-9+/=]+)\s*</DataArray>', raw)
    b64 = m.group(2)
    nb = struct.unpack("<I", base64.b64decode(b64[:8])[:4])[0]
    hdr_chars = ((4 * (3 + nb) + 2) // 3) * 4
    vals = struct.unpack("<%dI" % (3 + nb), base64.b64decode(b64[:hdr_chars]))
    body = base64.b64decode(b64[hdr_chars:])
    out, off = bytearray(), 0
    for c in vals[3:]:
        out += zlib.decompress(body[off:off + c])
        off += c
    nx, ny, nz = ext[1] - ext[0] + 1, ext[3] - ext[2] + 1, ext[5] - ext[4] + 1
    return np.frombuffer(bytes(out), dtype=_DT[m.group(1).decode()]).reshape(nz, ny, nx), org, spc


class Subject:
    """CT + segmentations of one subject; arrays are (z, y, x)."""

    def __init__(self, src: Path):
        self.dir = Path(src)
        vtm = (self.dir / "s1397_resampled.vtm").read_text()
        self.index = re.findall(r'<DataSet index="\d+" name="([^"]+)" file="([^"]+)"', vtm)
        self.names = [n for n, _ in self.index if n != "ct"]
        self.ct, self.origin, self.spacing = read_vti(self.dir / dict(self.index)["ct"])
        self._seg = {}

    def seg(self, name: str) -> np.ndarray:
        if name not in self._seg:
            self._seg[name] = read_vti(self.dir / dict(self.index)[name])[0] > 0
        return self._seg[name]


# --------------------------------------------------------------------------------------------
# 2. meshing: smoothed signed-distance field -> marching cubes -> Taubin -> quadric decimation
# --------------------------------------------------------------------------------------------
def vertex_normals(v, f):
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    n = np.zeros_like(v)
    for k in range(3):
        np.add.at(n, f[:, k], fn)
    l = np.linalg.norm(n, axis=1, keepdims=True)
    l[l == 0] = 1
    return n / l


def taubin(v, f, iters=10, lam=0.5, mu=-0.53):
    n = len(v)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    a = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr()
    a = ((a + a.T) > 0).astype(np.float64)
    deg = np.asarray(a.sum(1)).ravel()
    deg[deg == 0] = 1
    w = sparse.diags(1.0 / deg) @ a
    v = v.astype(np.float64).copy()
    for _ in range(iters):
        v += lam * (w @ v - v)
        v += mu * (w @ v - v)
    return v


def mesh_from_mask(mask, spacing, origin, sigma=0.8, zoom=2, smooth_iters=8):
    """mask (z,y,x) bool -> (verts mm RAS (x,y,z), faces) or None. Outward-oriented triangles."""
    idx = np.argwhere(mask)
    if len(idx) == 0:
        return None
    pad = 4
    lo = np.maximum(idx.min(0) - pad, 0)
    hi = np.minimum(idx.max(0) + pad + 1, mask.shape)
    sub = np.pad(mask[lo[0]:hi[0], lo[1]:hi[1], lo[2]:hi[2]], 3)
    sz, sy, sx = spacing[2], spacing[1], spacing[0]
    sdf = ndi.distance_transform_edt(sub) - ndi.distance_transform_edt(~sub)  # voxel units, inside positive
    sdf = ndi.gaussian_filter(sdf, sigma)
    if zoom > 1:
        sdf = ndi.zoom(sdf, zoom, order=1, grid_mode=True, mode="nearest")
    if not (sdf.max() > 0 > sdf.min()):
        return None
    v, f, _, _ = marching_cubes(sdf, 0.0, gradient_direction="ascent")  # inside is positive: ascent keeps outward winding
    f = f.astype(np.int64)
    # orientation vote against the field gradient (robust to skimage conventions)
    nrm = vertex_normals(v, f)
    probe = ndi.map_coordinates(sdf, (v + 0.7 * nrm).T, order=1, mode="nearest")
    here = ndi.map_coordinates(sdf, v.T, order=1, mode="nearest")
    if np.mean(probe - here) > 0:
        f = f[:, ::-1]
    # grid index (zoomed, padded) -> voxel index in the full volume -> mm
    vi = (v + 0.5) / zoom - 0.5 - 3 + lo
    vmm = np.stack([vi[:, 2] * sx + origin[0], vi[:, 1] * sy + origin[1], vi[:, 0] * sz + origin[2]], 1)
    if smooth_iters:
        vmm = taubin(vmm, f, smooth_iters)
    return vmm, f


def drop_small_components(v, f, min_tris):
    """Remove connected triangle components with fewer than min_tris triangles."""
    n = len(v)
    a = sparse.coo_matrix((np.ones(len(f) * 3), (np.r_[f[:, 0], f[:, 1], f[:, 2]], np.r_[f[:, 1], f[:, 2], f[:, 0]])), shape=(n, n))
    k, lab = csgraph.connected_components(a, directed=False)
    cnt = np.bincount(lab[f[:, 0]], minlength=k)
    keep = cnt[lab[f[:, 0]]] >= min_tris
    return compact(v, f[keep])


def compact(v, f):
    used = np.unique(f)
    remap = -np.ones(len(v), np.int64)
    remap[used] = np.arange(len(used))
    return v[used], remap[f]


def simplify(v, f, target_verts):
    """Reduce to about target_verts vertices (quadric decimation when available)."""
    if len(v) <= target_verts:
        return v, f
    if _fs is not None:
        red = 1.0 - target_verts / len(v)
        v2, f2 = _fs.simplify(v.astype(np.float32), f.astype(np.int32), target_reduction=min(red, 0.995), agg=6)
        return v2.astype(np.float64), f2.astype(np.int64)
    # fallback: vertex clustering on a grid sized to the target
    ext = v.max(0) - v.min(0)
    cell = (np.prod(ext) / max(target_verts, 1)) ** (1 / 3) * 1.4
    key = np.floor((v - v.min(0)) / cell).astype(np.int64)
    uniq, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    cnt = np.bincount(inv)
    nv = np.stack([np.bincount(inv, v[:, k]) / cnt for k in range(3)], 1)
    nf = inv[f]
    ok = (nf[:, 0] != nf[:, 1]) & (nf[:, 1] != nf[:, 2]) & (nf[:, 0] != nf[:, 2])
    return compact(nv, nf[ok])


def area(v, f):
    return 0.5 * np.linalg.norm(np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]]), axis=1).sum()


# --------------------------------------------------------------------------------------------
# 3. what goes where
# --------------------------------------------------------------------------------------------
def group_of(name: str):
    if name.startswith("rib_") or name in ("costal_cartilages", "sternum"):
        return "RIBCAGE"
    if name.startswith("vertebrae_") or name == "sacrum":
        return "SPINE"
    if name.split("_")[0] in ("clavicula", "scapula", "humerus", "hip", "femur"):
        return "LIMBGIRDLE"
    if name == "skull":
        return "SKULL"
    if name.startswith("lung_"):
        return "LUNGS"
    if name == "trachea":
        return "AIRWAY"
    if name in ("heart", "atrial_appendage_left"):
        return "HEART"
    if name in ("aorta", "brachiocephalic_trunk", "superior_vena_cava", "inferior_vena_cava", "pulmonary_vein",
                "portal_vein_and_splenic_vein") or name.startswith(("brachiocephalic_vein", "common_carotid", "subclavian_artery", "iliac_")):
        return "VESSELS"
    if name in ("liver", "kidney_left", "kidney_right", "spleen", "stomach", "pancreas", "urinary_bladder", "gallbladder",
                "adrenal_gland_left", "adrenal_gland_right", "thyroid_gland", "prostate", "esophagus", "spinal_cord"):
        return "ORGANS"
    if name in ("colon", "small_bowel", "duodenum"):
        return "VISCERA"
    if name == "brain":
        return "BRAIN"
    return None  # muscles etc. are not used (size, and not part of the look)


# vertex budgets as (full, lite) caps per label (a mesh smaller than the cap is kept as it is)
def budget(name: str, grp: str, quality: str) -> int:
    i = 0 if quality == "full" else 1
    if name == "__skin__":
        return (14000, 4200)[i]
    if grp == "RIBCAGE":
        return {"costal_cartilages": (2600, 650), "sternum": (900, 260)}.get(name, (700, 150))[i]
    if grp == "SPINE":
        return (1200, 260)[i] if name == "sacrum" else (900, 130)[i]
    if grp == "LIMBGIRDLE":
        return (1500, 330)[i] if name.startswith(("hip", "scapula")) else (1100, 200)[i]
    if grp == "SKULL":
        return (5500, 1800)[i]
    if grp == "LUNGS":
        return (3600, 800)[i]
    if grp == "AIRWAY":
        return (700, 200)[i]
    if grp == "HEART":
        return (500, 150)[i] if name == "atrial_appendage_left" else (5200, 1500)[i]
    if grp == "VESSELS":
        return {"aorta": (3200, 950)}.get(name, (450, 120))[i]
    if grp == "ORGANS":
        return {"liver": (2600, 650), "stomach": (1200, 300), "spinal_cord": (500, 150)}.get(name, (800, 160))[i]
    if grp == "VISCERA":
        return (1800, 500)[i]
    if grp in ("BRAIN", "BRAINCT"):
        return (5000, 1500)[i]
    if grp == "LUNGVESSELS":
        return (14000, 4200)[i]
    return 400


# --------------------------------------------------------------------------------------------
# 4. text helpers
# --------------------------------------------------------------------------------------------
def fnum(a, nd):
    a = np.asarray(a, dtype=np.float64).reshape(-1)
    s = np.char.mod("%." + str(nd) + "f", a)
    if nd > 0:  # trim trailing zeros of the fraction only (never the zeros of an integer part)
        s = np.char.rstrip(np.char.rstrip(s, "0"), ".")
    s[s == "-0"] = "0"
    s[s == ""] = "0"
    return " ".join(s.tolist())


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def lookat(eye, target, up=(0, 1, 0)):
    eye, target, up = (np.asarray(x, float) for x in (eye, target, up))
    z = eye - target
    z /= np.linalg.norm(z)
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z], 1)
    ang = np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))
    if abs(ang) < 1e-9:
        return (0, 0, 1, 0)
    if abs(ang - np.pi) < 1e-6:
        w, V = np.linalg.eigh((R + np.eye(3)) / 2)
        ax = V[:, np.argmax(w)]
    else:
        ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]]) / (2 * np.sin(ang))
    return tuple(float(t) for t in (*ax, ang))


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("'", "&apos;").replace('"', "&quot;").replace("<", "&lt;")


# --------------------------------------------------------------------------------------------
# 5. shaders (the glass family of the brain scene: same field names, same varyings)
# --------------------------------------------------------------------------------------------
GLASS_VS = """data:x-shader/x-vertex,#version 300 es
precision highp float;
uniform mat4 x3d_ProjectionMatrix, x3d_ModelViewMatrix; uniform mat3 x3d_NormalMatrix; uniform float useColor;
in vec4 x3d_Vertex; in vec3 x3d_Normal; in vec4 x3d_Color;
out vec3 vN; out vec3 vP; out vec3 vO; out vec2 vC;
void main(){ vec4 p = x3d_ModelViewMatrix * x3d_Vertex; vP = p.xyz; vO = x3d_Vertex.xyz;
  vN = normalize(x3d_NormalMatrix * x3d_Normal); vC = useColor > 0.5 ? x3d_Color.rg : vec2(1.0);
  gl_Position = x3d_ProjectionMatrix * p; }
"""
GLASS_FS = """data:x-shader/x-fragment,#version 300 es
precision highp float;
uniform vec3 rimColor; uniform vec3 bodyColor; uniform float rimPower; uniform float baseAlpha; uniform float rimAlpha;
uniform float smoke; uniform float time;
in vec3 vN; in vec3 vP; in vec3 vO; in vec2 vC; out vec4 fragColor;
float hash(vec3 p){ p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float vnoise(vec3 x){ vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x), mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x), mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z); }
void main(){ vec3 N = normalize(vN); vec3 V = normalize(-vP); float ndv = abs(dot(N, V));
  float f = pow(1.0 - ndv, rimPower);
  float ao = vC.x; float fade = vC.y;
  vec3 col = mix(bodyColor * ao, rimColor, f);
  float a = mix(baseAlpha, rimAlpha, f) * mix(1.4, 0.8, ao);
  if (smoke > 0.0) { vec3 q = vO * 0.016 + vec3(0.0, time * 0.035, time * 0.02);
    float n = 0.55 * vnoise(q) + 0.30 * vnoise(q * 2.3 + 7.1) + 0.15 * vnoise(q * 5.1 + 3.3);
    float s = smoothstep(0.30, 0.70, n);
    a *= mix(1.0, 0.2 + 1.25 * s, smoke); col = mix(col, col * (0.6 + 0.8 * s), smoke); }
  fragColor = vec4(col, clamp(a * fade, 0.0, 1.0)); }
"""
HALO_FS = """data:x-shader/x-fragment,#version 300 es
precision highp float;
uniform vec3 rimColor; uniform float rimPower; uniform float intensity;
in vec3 vN; in vec3 vP; in vec3 vO; in vec2 vC; out vec4 fragColor;
void main(){ vec3 N = normalize(vN); vec3 V = normalize(-vP); float f = pow(1.0 - abs(dot(N, V)), rimPower);
  float a = clamp(f * intensity * vC.y, 0.0, 1.0); fragColor = vec4(rimColor, a); }
"""


def glass_shader(defname, rim, body, power, base_a, rim_a, smoke=None, use_color=False):
    sm = ""
    if smoke is not None:
        sm = f"<field name='smoke' type='SFFloat' accessType='inputOutput' value='{smoke}'/><field name='time' type='SFTime' accessType='inputOutput' value='0'/>"
    else:
        sm = "<field name='smoke' type='SFFloat' accessType='inputOutput' value='0'/><field name='time' type='SFTime' accessType='inputOutput' value='0'/>"
    return (f"<ComposedShader DEF='{defname}' language='GLSL'>"
            f"<field name='rimColor' type='SFColor' accessType='inputOutput' value='{rim}'/><field name='bodyColor' type='SFColor' accessType='inputOutput' value='{body}'/>"
            f"<field name='rimPower' type='SFFloat' accessType='inputOutput' value='{power}'/><field name='baseAlpha' type='SFFloat' accessType='inputOutput' value='{base_a}'/>"
            f"<field name='rimAlpha' type='SFFloat' accessType='inputOutput' value='{rim_a}'/><field name='useColor' type='SFFloat' accessType='initializeOnly' value='{1 if use_color else 0}'/>{sm}"
            f"<ShaderPart type='VERTEX'><![CDATA[{GLASS_VS}]]></ShaderPart><ShaderPart type='FRAGMENT'><![CDATA[{GLASS_FS}]]></ShaderPart></ComposedShader>")


def halo_shader(defname, rim, power, intensity):
    return (f"<ComposedShader DEF='{defname}' language='GLSL'>"
            f"<field name='rimColor' type='SFColor' accessType='inputOutput' value='{rim}'/><field name='rimPower' type='SFFloat' accessType='inputOutput' value='{power}'/>"
            f"<field name='intensity' type='SFFloat' accessType='inputOutput' value='{intensity}'/><field name='useColor' type='SFFloat' accessType='initializeOnly' value='0'/>"
            f"<ShaderPart type='VERTEX'><![CDATA[{GLASS_VS}]]></ShaderPart><ShaderPart type='FRAGMENT'><![CDATA[{HALO_FS}]]></ShaderPart></ComposedShader>")


# look table: appearance DEF -> kind and parameters (all colours linear-ish display values)
GLASS = {
    # name: (rim, body, rimPower, baseAlpha, rimAlpha, smoke)
    "SKIN": ("0.36 0.78 1.00", "0.07 0.26 0.46", 2.1, 0.045, 0.95, None),
    "BONE": ("0.58 0.88 1.00", "0.16 0.42 0.70", 2.2, 0.11, 0.92, None),
    "SKULL": ("0.66 0.92 1.00", "0.22 0.50 0.80", 2.3, 0.05, 0.72, None),
    "LUNG": ("0.60 0.80 0.96", "0.36 0.54 0.72", 2.0, 0.18, 0.30, 1.0),
    "AIRWAY": ("0.55 0.85 1.00", "0.25 0.55 0.75", 1.8, 0.14, 0.70, None),
    "LIVER": ("1.00 0.58 0.30", "0.62 0.28 0.12", 2.0, 0.065, 0.55, None),
    "KIDNEY": ("1.00 0.42 0.34", "0.50 0.16 0.14", 2.0, 0.14, 0.60, None),
    "SOFT": ("0.80 0.66 0.62", "0.36 0.26 0.26", 2.2, 0.050, 0.32, None),
    "VISCERA": ("0.62 0.72 0.82", "0.22 0.30 0.38", 2.4, 0.025, 0.20, None),
    "BRAIN": ("1.00 0.80 0.52", "0.95 0.60 0.30", 2.0, 0.17, 1.0, None),
    "BRAINCT": ("1.00 0.72 0.38", "0.95 0.48 0.18", 1.6, 0.22, 0.90, None),
    "CORD": ("1.00 0.86 0.55", "0.80 0.62 0.30", 1.6, 0.35, 0.85, None),
}

# looks whose meshes carry a Color node (r = ambient occlusion proxy, g = fade)
COLORED = {"SKIN", "BONE", "SKULL", "BRAIN"}

# PBR looks: (baseColor, emissiveColor, metallic, roughness)
PBR = {
    "HEART": ("0.88 0.14 0.07", "0.42 0.045 0.02", 0.0, 0.38),
    "AORTA": ("1.00 0.42 0.12", "0.50 0.17 0.04", 0.04, 0.32),
    "ARTERY": ("1.00 0.50 0.14", "0.55 0.20 0.05", 0.04, 0.30),
    "VEIN": ("0.72 0.12 0.12", "0.36 0.04 0.04", 0.02, 0.36),
    "LUNGVESSEL": ("0.92 0.22 0.10", "0.42 0.07 0.03", 0.02, 0.38),
}

# additive-looking rim shells drawn around a USE of the same geometry: label -> [(scale about centroid, rim colour, power, intensity)]
HALOS = {
    "heart": [(1.03, "1.0 0.55 0.22", 2.0, 0.9), (1.08, "1.0 0.42 0.14", 3.0, 0.45)],
    "cortex_left": [(1.035, "1.0 0.72 0.35", 2.2, 0.8)],
    "cortex_right": [(1.035, "1.0 0.72 0.35", 2.2, 0.8)],
}

CAMERA = dict(fov=0.55)


# --------------------------------------------------------------------------------------------
# 6. mesh bank (cached) and scene frame
# --------------------------------------------------------------------------------------------
CX, CY, CZ = 239.25, 210.0, 410.0  # scene origin in the data's mm RAS frame (mid-FOV x, mid-chest y, z)
CACHE_VERSION = "v6"
THIN = {"common_carotid_artery_left", "common_carotid_artery_right", "brachiocephalic_trunk", "subclavian_artery_left", "subclavian_artery_right",
        "brachiocephalic_vein_left", "brachiocephalic_vein_right", "esophagus", "adrenal_gland_left", "adrenal_gland_right", "thyroid_gland",
        "iliac_artery_left", "iliac_artery_right", "iliac_vena_left", "iliac_vena_right", "spinal_cord", "atrial_appendage_left",
        "pulmonary_vein", "portal_vein_and_splenic_vein", "trachea", "gallbladder", "pancreas", "duodenum"}


def to_scene(v):
    v = np.asarray(v, np.float64)
    return np.stack([v[:, 0] - CX, v[:, 2] - CZ, -(v[:, 1] - CY)], 1)


def skin_mask(ct):
    body = ct > -300
    body = ndi.binary_opening(body, iterations=2)
    lab, n = ndi.label(body)
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    body = lab == sizes.argmax()
    for k in range(body.shape[0]):  # axial hole fill: lungs, bowel gas, airway pockets
        body[k] = ndi.binary_fill_holes(body[k])
    lab, n = ndi.label(body)
    sizes = np.bincount(lab.ravel())
    sizes[0] = 0
    return lab == sizes.argmax()


class MeshBank:
    def __init__(self, subj: Subject, cache: Path):
        self.s = subj
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)

    def _path(self, key):
        return self.cache / f"{CACHE_VERSION}-{key}.npz"

    def get(self, key):
        p = self._path(key)
        if p.exists():
            d = np.load(p)
            return (d["v"].astype(np.float64), d["f"].astype(np.int64)) if d["v"].size else None
        res = self._make(key)
        if res is None:
            np.savez_compressed(p, v=np.zeros((0, 3)), f=np.zeros((0, 3)))
            return None
        np.savez_compressed(p, v=res[0].astype(np.float32), f=res[1].astype(np.int32))
        return self.get(key)  # always continue from the stored (float32) form, so a cold and a warm cache give identical output

    def _make(self, key):
        s = self.s
        if key == "__skin__":
            r = mesh_from_mask(skin_mask(s.ct), s.spacing, s.origin, sigma=1.6, zoom=1, smooth_iters=14)
            return drop_small_components(r[0], r[1], 3000)  # floating specks left by the smoothing
        if key == "__lungvessels__":
            lungs = np.zeros(s.ct.shape, bool)
            for n in s.names:
                if n.startswith("lung_"):
                    lungs |= s.seg(n)
            er = ndi.binary_erosion(lungs, iterations=1)
            f = ndi.gaussian_filter(s.ct.astype(np.float32), 0.6)
            field = np.where(er, f, -1024.0).astype(np.float32)
            field = ndi.zoom(field, 2, order=1, grid_mode=True, mode="nearest")
            v, fc, _, _ = marching_cubes(field, -470.0, gradient_direction="ascent")
            fc = fc.astype(np.int64)
            nrm = vertex_normals(v, fc)
            probe = ndi.map_coordinates(field, (v + 0.7 * nrm).T, order=1, mode="nearest")
            here = ndi.map_coordinates(field, v.T, order=1, mode="nearest")
            if np.mean(probe - here) > 0:
                fc = fc[:, ::-1]
            vi = (v + 0.5) / 2 - 0.5
            vmm = np.stack([vi[:, 2] * s.spacing[0] + s.origin[0], vi[:, 1] * s.spacing[1] + s.origin[1], vi[:, 0] * s.spacing[2] + s.origin[2]], 1)
            vmm, fc = drop_small_components(vmm, fc, 420)
            return taubin(vmm, fc, 6), fc
        thin = key in THIN or key.startswith(("rib_", "vertebrae_"))
        sig = 0.55 if thin else (1.0 if key in ("brain", "liver", "heart", "stomach", "colon", "small_bowel") else 0.8)
        return mesh_from_mask(s.seg(key), s.spacing, s.origin, sigma=sig, zoom=2, smooth_iters=8)


def fade_for_skin(v_ras, ct_shape, spacing, origin):
    """Per-vertex fade (0 at the field-of-view cut planes, 1 inside) so the truncated limbs and thighs dissolve instead of ending in caps."""
    lo = np.array(origin)
    hi = np.array(origin) + (np.array(ct_shape[::-1]) - 1) * np.array([spacing[0], spacing[1], spacing[2]])
    def ss(x):
        x = np.clip(x, 0, 1)
        return x * x * (3 - 2 * x)
    f = ss((v_ras[:, 2] - lo[2]) / 130.0) * ss((hi[2] - v_ras[:, 2]) / 40.0)
    f *= ss((v_ras[:, 0] - lo[0]) / 45.0) * ss((hi[0] - v_ras[:, 0]) / 45.0)
    # arms are raised in this scan: dissolve the lateral skin above the shoulders instead of ending in open tubes
    lat = ss((np.abs(v_ras[:, 0] - CX) - 84.0) / 30.0)
    f *= 1.0 - lat * ss((v_ras[:, 2] - 590.0) / 90.0)
    return f




# --------------------------------------------------------------------------------------------
# 6b. per-vertex ambient occlusion proxy and the template-cortex ghost
# --------------------------------------------------------------------------------------------
def occupancy_ao(v_ras, n_ras, union_mask, subj: Subject, sigma_vox=2.0, offset_mm=3.0):
    """AO proxy in [0.3, 1]: blurred occupancy of a label union sampled just outside the surface (concave places read darker)."""
    occ = ndi.gaussian_filter(union_mask.astype(np.float32), sigma_vox)
    p = v_ras + offset_mm * n_ras
    idx = np.stack([(p[:, 2] - subj.origin[2]) / subj.spacing[2], (p[:, 1] - subj.origin[1]) / subj.spacing[1], (p[:, 0] - subj.origin[0]) / subj.spacing[0]])
    o = ndi.map_coordinates(occ, idx, order=1, mode="nearest")
    return 1.0 - 0.7 * np.clip((o - 0.30) / 0.40, 0, 1)


def affine_fit(src, dst):
    a = np.c_[src, np.ones(len(src))]
    m, *_ = np.linalg.lstsq(a, dst, rcond=None)
    return m  # (4,3)


def fit_template_to_brain(tpl_pts, subj_pts, subj_axes, seed=0, iters=40, stretch=(0.85, 1.25)):
    """Affine ICP of the template brain point cloud (RAS) onto the subject brain surface.
    Start: template axes (R, A, S) map to the subject's head axes subj_axes = (R, A, S unit vectors), scaled isotropically to the same RMS radius.
    The anatomical start matters: a brain is nearly an ovoid, so surface distance alone cannot tell the orientations apart (a PCA multi-start fitted it sideways).
    Each iteration clips the principal stretches of the linear part to `stretch` times their mean. Returns (4x3 affine on row vectors, mean two-way distance mm).
    The template gyri are NOT the subject's: an illustrative fit of a template into a real brain mask."""
    from scipy.spatial import cKDTree
    rng = np.random.default_rng(seed)
    ts = tpl_pts[rng.choice(len(tpl_pts), min(5000, len(tpl_pts)), replace=False)]
    ss_ = subj_pts[rng.choice(len(subj_pts), min(5000, len(subj_pts)), replace=False)]
    tc, sc = tpl_pts.mean(0), subj_pts.mean(0)
    k = np.sqrt(((subj_pts - sc) ** 2).sum(1).mean() / ((tpl_pts - tc) ** 2).sum(1).mean())
    M = np.asarray(subj_axes, float) * k  # rows: where template R, A, S go (RAS template axes are the identity)
    A = np.vstack([M, sc - tc @ M])
    ones = np.ones((len(ts), 1))
    sub_tree = cKDTree(ss_)
    cur = np.c_[ts, ones] @ A
    for _ in range(iters):
        d1, i1 = sub_tree.query(cur)
        d2, i2 = cKDTree(cur).query(ss_)
        k1 = d1 <= np.quantile(d1, 0.9)
        k2 = d2 <= np.quantile(d2, 0.9)
        src = np.r_[ts[k1], ts[i2[k2]]]
        dst = np.r_[ss_[i1[k1]], ss_[np.nonzero(k2)[0]]]
        A = affine_fit(src, dst)
        U, S_, Vt = np.linalg.svd(A[:3])
        m = S_.mean()
        L = (U * np.clip(S_, stretch[0] * m, stretch[1] * m)) @ Vt
        # re-solve the translation for the clipped linear part
        tr = (dst - src @ L).mean(0)
        A = np.vstack([L, tr])
        cur = np.c_[ts, ones] @ A
    d1, _ = sub_tree.query(cur)
    d2, _ = cKDTree(cur).query(ss_)
    return A, 0.5 * (np.sqrt((d1 ** 2).mean()) + np.sqrt((d2 ** 2).mean()))


def template_brain(bank: "MeshBank", subj: Subject, path: Path, log):
    """Template cortex (fsaverage pial; this builder decimates it to about 7,000 (full) or 3,000 (lite) vertices per hemisphere) + cerebellum + brainstem, affinely fitted into the subject's brain mask.
    Returns dict name -> (verts RAS mm, faces, per-vertex curvature or None)."""
    d = np.load(path)
    if "curvL" in d.files:
        # prep_meshes.py bundle (meshes_41k.npz): scene axes (x right, y up, z posterior), origin at the pial bounding-box centre C -> RAS (x right, y anterior, z superior)
        C = d["C"].astype(np.float64)
        ras = lambda v: np.stack([v[:, 0] + C[0], -(v[:, 2] + C[2]), v[:, 1] + C[1]], 1)
        cL_, cR_ = d["curvL"], d["curvR"]
    else:                                    # older bundle written in RAS by the first prep script
        ras = lambda v: v
        cL_, cR_ = d["cL"], d["cR"]
    tpl = {"cortex_left": (ras(d["vL"].astype(np.float64)), d["fL"].astype(np.int64), cL_.astype(np.float64)),
           "cortex_right": (ras(d["vR"].astype(np.float64)), d["fR"].astype(np.int64), cR_.astype(np.float64)),
           "cerebellum": (ras(d["sv_cerebellum"].astype(np.float64)), d["sf_cerebellum"].astype(np.int64), None),
           "brainstem": (ras(d["sv_brainstem"].astype(np.float64)), d["sf_brainstem"].astype(np.int64), None)}
    tpl_pts = np.concatenate([v for v, _, _ in tpl.values()])
    sv, sf = bank.get("brain")
    # subject head axes: right = data +x; up = away from the first cervical vertebra (the head is flexed forward in this scan), made orthogonal to right
    c1 = np.argwhere(subj.seg("vertebrae_C1")).mean(0)  # (z, y, x) voxel
    c1 = np.array([c1[2] * subj.spacing[0] + subj.origin[0], c1[1] * subj.spacing[1] + subj.origin[1], c1[0] * subj.spacing[2] + subj.origin[2]])
    Rs = np.array([1.0, 0.0, 0.0])
    Ss = sv.mean(0) - c1
    Ss = Ss - Rs * (Ss @ Rs)
    Ss /= np.linalg.norm(Ss)
    As = np.cross(Ss, Rs)  # RAS: R x A = S, so A = S x R
    log(f"template brain fit: head-up axis (data RAS) {Ss.round(3).tolist()}, flexion from vertical {np.degrees(np.arccos(Ss[2])):.1f} deg")
    A, score = fit_template_to_brain(tpl_pts, sv, (Rs, As, Ss))
    sv_ = np.linalg.svd(A[:3], compute_uv=False)
    log(f"template brain fit: affine ICP, mean two-way surface distance {score:.2f} mm; principal stretches {sv_.round(3).tolist()}, volume scale {abs(np.linalg.det(A[:3])):.3f}")
    out = {}
    for k, (v, f, c) in tpl.items():
        out[k] = (np.c_[v, np.ones(len(v))] @ A, f, c)
    return out, dict(icp_mean_two_way_mm=round(float(score), 2), affine_principal_stretches=sv_.round(3).tolist(), affine_volume_scale=round(float(abs(np.linalg.det(A[:3]))), 3))


# --------------------------------------------------------------------------------------------
# 7. composition
# --------------------------------------------------------------------------------------------
GROUPS = [  # (SW name, group key, description shown by the page, default whichChoice)
    ("SW_SKIN", "SKIN", "Body surface (threshold of the CT, faint glass)", 0),
    ("SW_RIBCAGE", "RIBCAGE", "Ribs, costal cartilages, sternum", 0),
    ("SW_SPINE", "SPINE", "Vertebrae C1 to S1 and sacrum", 0),
    ("SW_GIRDLES", "LIMBGIRDLE", "Clavicles, scapulae, humeri, hips, femurs", 0),
    ("SW_SKULL", "SKULL", "Skull", 0),
    ("SW_BRAIN", "BRAIN", "Brain ghost: template cortex (fsaverage), cerebellum and brainstem, affinely fitted into this subject's brain mask. ILLUSTRATIVE: the folds are the template's, not the subject's", 0),
    ("SW_BRAIN_CT", "BRAINCT", "Brain as segmented in this subject's CT (3 mm voxels; no folds)", -1),
    ("SW_LUNGS", "LUNGS", "Lungs, five lobes", 0),
    ("SW_LUNGVESSELS", "LUNGVESSELS", "Lung vessels and airway walls: iso-surface of the CT inside the lung masks (threshold, not a segmentation)", 0),
    ("SW_AIRWAY", "AIRWAY", "Trachea", 0),
    ("SW_HEART", "HEART", "Heart and left atrial appendage", 0),
    ("SW_VESSELS", "VESSELS", "Aorta, great vessels, carotids, subclavian, venae cavae, pulmonary vein, portal, iliac", 0),
    ("SW_ORGANS", "ORGANS", "Liver, kidneys, spleen, stomach, pancreas, bladder, spinal cord and others", 0),
    ("SW_VISCERA", "VISCERA", "Colon, small bowel, duodenum (hidden by default)", -1),
]


def look_of(label: str, grp: str):
    """(kind, appearance name) for a label."""
    if grp in ("RIBCAGE", "SPINE", "LIMBGIRDLE"):
        return "glass", "BONE"
    if grp == "SKULL":
        return "glass", "SKULL"
    if grp == "LUNGS":
        return "glass", "LUNG"
    if grp == "AIRWAY":
        return "glass", "AIRWAY"
    if grp == "SKIN":
        return "glass", "SKIN"
    if grp == "BRAIN":
        return "glass", "BRAIN"
    if grp == "BRAINCT":
        return "glass", "BRAINCT"
    if grp == "VISCERA":
        return "glass", "VISCERA"
    if grp == "HEART":
        return "pbr", "HEART"
    if grp == "LUNGVESSELS":
        return "pbr", "LUNGVESSEL"
    if grp == "VESSELS":
        if label == "aorta":
            return "pbr", "AORTA"
        if "vena" in label or "vein" in label:
            return "pbr", "VEIN"
        return "pbr", "ARTERY"
    if grp == "ORGANS":
        if label == "liver":
            return "glass", "LIVER"
        if label.startswith("kidney"):
            return "glass", "KIDNEY"
        if label == "spinal_cord":
            return "glass", "CORD"
        return "glass", "SOFT"
    return "glass", "SOFT"


class Composer:
    def __init__(self):
        self.defs = set()
        self.dedup = {}

    def appearance(self, kind, name):
        key = f"APP_{name}"
        if key in self.defs:
            return f"<Appearance USE='{key}'/>"
        self.defs.add(key)
        if kind == "pbr":
            base, emis, met, rough = PBR[name]
            return (f"<Appearance DEF='{key}'><PhysicalMaterial baseColor='{base}' emissiveColor='{emis}' metallic='{met}' roughness='{rough}'/></Appearance>")
        rim, body, power, ba, ra, smoke = GLASS[name]
        sh = glass_shader(f"SH_{name}", rim, body, power, ba, ra, smoke, use_color=name in COLORED)
        return f"<Appearance DEF='{key}'><Material diffuseColor='0 0 0' transparency='0.01'/>{sh}</Appearance>"

    def halo_appearance(self, name, rim, power, intensity):
        key = f"APP_HALO_{name}"
        if key in self.defs:
            return f"<Appearance USE='{key}'/>"
        self.defs.add(key)
        return f"<Appearance DEF='{key}'><Material diffuseColor='0 0 0' transparency='0.01'/>{halo_shader(f'SH_HALO_{name}', rim, power, intensity)}</Appearance>"


def geometry_xml(geo_def, v, f, n, color=None):
    d = f" DEF='{geo_def}'" if geo_def else ""
    s = (f"<IndexedTriangleSet{d} index='{fnum(f.reshape(-1), 0)}' solid='false'>"
         f"<Coordinate point='{fnum(v, 1)}'/><Normal vector='{fnum(n, 2)}'/>")
    if color is not None:
        s += f"<Color color='{fnum(color, 2)}'/>"
    return s + "</IndexedTriangleSet>"


def smooth_scalar_on_mesh(f, val, iters=6):
    n = len(val)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    a = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr()
    a = ((a + a.T) > 0).astype(np.float64)
    deg = np.asarray(a.sum(1)).ravel()
    deg[deg == 0] = 1
    w = sparse.diags(1.0 / deg) @ a
    for _ in range(iters):
        val = 0.5 * val + 0.5 * (w @ val)
    return val


def prepare(bank: MeshBank, subj: Subject, quality: str, log, template=None):
    """Return list of items: dict(label, grp, v (scene), f, n, color). template: output of template_brain() or None."""
    items = []
    unions = {}

    def union(names):
        key = ",".join(names)
        if key not in unions:
            m = np.zeros(subj.ct.shape, bool)
            for nme in names:
                m |= subj.seg(nme)
            unions[key] = m
        return unions[key]

    bones = [n for n in subj.names if group_of(n) in ("RIBCAGE", "SPINE", "LIMBGIRDLE", "SKULL")]
    cardio = [n for n in subj.names if group_of(n) in ("HEART", "VESSELS")]
    labels = [("__skin__", "SKIN")]
    for n in subj.names:
        g = group_of(n)
        if g and subj.seg(n).any():
            labels.append((n, "BRAINCT" if (g == "BRAIN" and template is not None) else g))
    labels.append(("__lungvessels__", "LUNGVESSELS"))
    for key, grp in labels:
        res = bank.get(key)
        if res is None:
            continue
        v, f = res
        v_ras, f = simplify(v, f, budget(key, grp, quality))
        n_ras = vertex_normals(v_ras, f)
        color = None
        if key == "__skin__":
            fd = fade_for_skin(v_ras, subj.ct.shape, subj.spacing, subj.origin)
            color = np.stack([np.ones(len(v_ras)), fd, np.zeros(len(v_ras))], 1)
        elif grp in ("RIBCAGE", "SPINE", "LIMBGIRDLE", "SKULL"):
            ao = 0.55 + 0.45 * occupancy_ao(v_ras, n_ras, union(bones), subj, 1.6, 3.0)
            color = np.stack([ao, np.ones(len(ao)), np.zeros(len(ao))], 1)
        elif grp in ("HEART", "VESSELS"):
            ao = occupancy_ao(v_ras, n_ras, union(cardio), subj, 2.0, 3.0)
            ao = 0.45 + 0.55 * ao
            color = np.stack([ao, ao, ao], 1)  # PBR multiplies base colour by this
        elif grp == "LUNGVESSELS":
            ao = 0.5 + 0.5 * occupancy_ao(v_ras, n_ras, union([n for n in subj.names if n.startswith("lung_")]), subj, 2.0, 3.0)
            color = np.stack([ao, ao, ao], 1)
        vs = to_scene(v_ras)
        vol = float(subj.seg(key).sum() * subj.spacing[0] * subj.spacing[1] * subj.spacing[2] / 1000.0) if key in subj.names else None
        items.append(dict(label=key.strip("_") if key.startswith("__") else key, grp=grp, v=vs, f=f, n=vertex_normals(vs, f), color=color, vol_ml=vol,
                          source="segmentation" if vol is not None else ("CT threshold" if key.startswith("__") else "?")))
        log(f"  [{quality}] {key:34s} {grp:11s} verts {len(vs):6d} tris {len(f):6d}")
    if template is not None:
        for key, (v, f, curv) in template.items():
            tgt = {"cortex_left": (7000, 3000), "cortex_right": (7000, 3000), "cerebellum": (1500, 450), "brainstem": (400, 150)}[key][0 if quality == "full" else 1]
            v2, f2 = simplify(v, f, tgt)
            color = None
            if curv is not None:
                from scipy.spatial import cKDTree
                cs = smooth_scalar_on_mesh(f, curv, 10)
                _, nn = cKDTree(v).query(v2)
                ao = np.clip(0.74 - 0.32 * np.tanh(3.0 * cs[nn]), 0.35, 1.0)
                color = np.stack([ao, np.ones(len(ao)), np.zeros(len(ao))], 1)
            vs = to_scene(v2)
            items.append(dict(label=key, grp="BRAIN", v=vs, f=f2, n=vertex_normals(vs, f2), color=color, vol_ml=None, source="template fitted (ILLUSTRATIVE)"))
            log(f"  [{quality}] template {key:26s} BRAIN       verts {len(vs):6d} tris {len(f2):6d}")
    return items


def build_scene(items, quality, meta):
    C = Composer()
    out = []
    ctr = {}
    by_grp = {}
    for it in items:
        by_grp.setdefault(it["grp"], []).append(it)
    allv = np.concatenate([it["v"] for it in items if it["grp"] == "SKIN"] or [items[0]["v"]])
    bmin, bmax = allv.min(0), allv.max(0)
    for sw, grp, desc, choice in GROUPS:
        its = by_grp.get(grp, [])
        if not its:
            continue
        shapes = []
        for it in its:
            kind, name = look_of(it["label"], grp)
            halo_on = it["label"] in HALOS
            geo_def = f"GEO_{it['label']}" if halo_on else None
            shapes.append(f"<Shape DEF='STRUCT_{it['label']}'>{C.appearance(kind, name)}{geometry_xml(geo_def, it['v'], it['f'], it['n'], it['color'])}</Shape>")
            if halo_on:
                c = it["v"].mean(0)
                for k, (sc, rim, pw, inten) in enumerate(HALOS[it["label"]]):
                    shapes.append(f"<Transform DEF='HALO{k}_{it['label']}' center='{fnum(c, 1)}' scale='{sc} {sc} {sc}'><Shape>"
                                  f"{C.halo_appearance(it['label'].upper() + str(k), rim, pw, inten)}<IndexedTriangleSet USE='{geo_def}'/></Shape></Transform>")
        gdef = "G_" + sw[3:]
        # the skin shell is not pickable: X3D picking returns the nearest surface, so a pickable skin would swallow every interior pick
        ts = "" if grp == "SKIN" else f"<TouchSensor DEF='TS_{sw[3:]}' description='{esc(desc)}'/>"
        out.append(f"<Switch DEF='{sw}' whichChoice='{choice}'><Group DEF='{gdef}'>" + "\n".join(shapes) + ts + "</Group></Switch>")
    return "\n".join(out), (bmin, bmax)


ENV_FACES = ("front", "back", "left", "right", "top", "bottom")


def env_xml(prefix="tex/env64"):
    tex = "".join(f"<ImageTexture containerField='{f}Texture' url='\"{prefix}/studio-{f}.png\"'/>" for f in ENV_FACES)
    return f"<EnvironmentLight DEF='ENV' intensity='0.55'><ComposedCubeMapTexture containerField='specularTexture'>{tex}</ComposedCubeMapTexture></EnvironmentLight>"


def viewpoints(bmin, bmax):
    h = bmax[1] - bmin[1]
    mid = (bmin + bmax) / 2
    vps = []
    def vp(name, desc, eye, tgt, fov=0.62):
        o = lookat(eye, tgt)
        vps.append(f"<Viewpoint DEF='{name}' description='{esc(desc)}' position='{fnum(eye, 1)}' orientation='{fnum(o, 5)}' centerOfRotation='{fnum(tgt, 1)}' fieldOfView='{fov}'/>")
    chest = np.array([0.0, -10.0, 0.0])
    head = np.array([0.0, 330.0, -60.0])
    vp("VP_HOME", "Whole body, anterior three-quarter", np.array([-520.0, 190.0, -1560.0]), np.array([0.0, 20.0, 0.0]), 0.52)
    vp("VP_FRONT", "Anterior (front) view", np.array([0.0, 20.0, -1650.0]), np.array([0.0, 20.0, 0.0]))
    vp("VP_BACK", "Posterior view", np.array([0.0, 20.0, 1650.0]), np.array([0.0, 20.0, 0.0]))
    vp("VP_LEFT", "Patient left side", np.array([1650.0, 20.0, 0.0]), np.array([0.0, 20.0, 0.0]))
    vp("VP_RIGHT", "Patient right side", np.array([-1650.0, 20.0, 0.0]), np.array([0.0, 20.0, 0.0]))
    vp("VP_CHEST", "Chest: heart and great vessels", np.array([0.0, 20.0, -620.0]), chest, 0.6)
    vp("VP_HEART", "Heart close-up (anterior, slightly left)", np.array([220.0, 0.0, -430.0]), np.array([-5.0, -15.0, -30.0]), 0.6)
    vp("VP_HEAD", "Head: brain ghost inside the skull", np.array([-330.0, 340.0, -380.0]), head, 0.6)
    vp("VP_TOP", "From above", np.array([0.0, 1500.0, -80.0]), np.array([0.0, 0.0, 0.0]), 0.7)
    return "\n".join(vps)


def world_info(meta):
    info = [
        meta["title"],
        "Subject: TotalSegmentator example subject s1397 (whole-body CT, 117 binary segmentations), resampled to 3 mm voxels, distributed with the pyvista example data (Apache-2.0 repository).",
        "Data attribution: Wasserthal J. et al., TotalSegmentator, Radiology: Artificial Intelligence 2023, doi 10.1148/ryai.230024. License grade LIKELY, not Confirmed: CC BY 4.0, inferred from the dataset's published terms; the licence record of this copy was not read.",
        "Derived content: smoothed and decimated surface meshes (signed-distance field, marching cubes, Taubin smoothing, quadric decimation). Changes were made. No raw CT or segmentation volumes are included.",
        "Skin = threshold of the subject CT (HU above -300, largest component, holes filled). Lung vessels = iso-surface of the CT (smoothed, 0.6 voxel) inside the lung masks (HU above -470): threshold-derived, includes airway walls; not a vessel segmentation.",
        ("Brain ghost: template cortex (fsaverage, FreeSurfer lineage, license grade SUSPECTED, decimated here to about 3,000 vertices per hemisphere in the lite scene; Fischl et al. 1999) plus aseg cerebellum and brainstem (MNI152NLin2009cAsym, Fonov et al. 2011), affinely fitted into this subject's brain mask "
         f"(ICP, mean two-way surface distance {meta['icp']} mm). ILLUSTRATIVE: the folds are the template's, not this subject's. The subject's own brain segmentation (3 mm, no folds) is in SW_BRAIN_CT, hidden by default."
         if meta.get("template") else "The brain ghost is the segmentation of this subject at 3 mm, not a cortical surface model."),
        "The subject has a pronounced forward head posture and raised arms; shown as recorded. Skin above the shoulders fades out on the lateral arms for clarity.",
        "Glow, halos, colours and the translucent look are artistic rendering choices, not tissue properties. ILLUSTRATIVE; not for diagnosis.",
        f"Frame: X patient-right, Y up, Z posterior; 1 unit = 1 mm; origin at x={CX} y={CY} z={CZ} mm of the data frame.",
        f"Builder: build_torso_scene.py, variant {meta['variant']}, builder sha256 {meta['builder_sha'][:16]}",
    ]
    return "<WorldInfo DEF='WORLD' title='" + esc(meta["title"]) + "' info='" + " ".join('"' + esc(s).replace('"', "'") + '"' for s in info) + "'/>"


def compose_document(body, bounds, meta, env_prefix="tex/env64"):
    bmin, bmax = bounds
    heads = [("title", meta["title"]), ("description", "Whole-body CT of one subject as translucent glass anatomy with a glowing heart, vessels and brain. ILLUSTRATIVE rendering of real segmentation data."),
             ("creator", "x3d.brain torso builder"), ("rights", "Derived from TotalSegmentator example subject s1397; attribution Wasserthal et al. 2023 (doi 10.1148/ryai.230024); license grade Likely (not Confirmed): CC BY 4.0, inferred from the dataset's published terms, licence record of this copy not read"),
             ("variant", meta["variant"]), ("synthetic", "Look (glow, halos, colours) is ILLUSTRATIVE; geometry is derived from real CT segmentation of one subject")]
    mt = "".join(f"<meta name='{k}' content='{esc(v)}'/>" for k, v in heads)
    comps = "<component name='Shape' level='5'/><component name='Lighting' level='3'/><component name='Rendering' level='3'/><component name='Shaders' level='1'/><component name='CubeMapTexturing' level='1'/><component name='PointingDeviceSensor' level='1'/><component name='Grouping' level='2'/>"
    bg = ("<Background DEF='BG' skyAngle='0.9 1.4 1.571' skyColor='0.004 0.012 0.024 0.012 0.035 0.062 0.022 0.062 0.105 0.026 0.07 0.115' "
          "groundAngle='1.0 1.571' groundColor='0.004 0.01 0.02 0.01 0.03 0.055 0.022 0.062 0.105'/>")
    lights = ("<DirectionalLight DEF='KEY' direction='0.45 -0.5 0.75' intensity='1.35' color='1 0.95 0.88'/>"
              "<DirectionalLight DEF='FILL' direction='-0.7 -0.15 0.55' intensity='0.55' color='0.45 0.7 1'/>"
              "<DirectionalLight DEF='RIM' direction='0.1 -0.4 -1' intensity='0.9' color='1 0.7 0.4'/>")
    nav = "<NavigationInfo DEF='NAV' type='\"EXAMINE\" \"ANY\"' headlight='false' speed='400'/>"
    clock = "<TimeSensor DEF='CLOCK' loop='true' cycleInterval='3600'/>"
    routes = "<ROUTE fromNode='CLOCK' fromField='elapsedTime' toNode='SH_LUNG' toField='time'/>"
    return ("<?xml version='1.0' encoding='UTF-8'?>\n"
            "<X3D profile='Interchange' version='4.1' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.1.xsd'>\n"
            f"<head>{comps}{mt}</head>\n<Scene>\n{world_info(meta)}\n{nav}\n{bg}\n{lights}\n{env_xml(env_prefix)}\n{viewpoints(bmin, bmax)}\n{clock}\n{body}\n{routes}\n</Scene></X3D>\n")



NOTICE = """# Torso CT scene: sources, licences, changes

Scenes `torso_ct.x3d` (full) and `torso_ct_lite.x3d` (lite) are derived surface meshes. No raw CT or segmentation volume is included, and no full-resolution template surface: the template cortex appears only as a decimated (about 3,000 vertices per hemisphere in the lite scene), affinely fitted mesh.

| Part | Source | Licence grade | What was done |
|---|---|---|---|
| Skeleton, lungs, heart, vessels, organs, brain mask, skin, lung vessels | TotalSegmentator example subject s1397, whole-body CT with 117 segmentations at 3 mm, distributed with the pyvista example data (Apache-2.0 repository). Wasserthal J. et al., Radiology: Artificial Intelligence 2023, doi 10.1148/ryai.230024 | LIKELY, not Confirmed: CC BY 4.0, inferred from the dataset's published terms; the licence record of this copy was not read | binary masks to signed-distance fields, marching cubes, Taubin smoothing, quadric decimation. Skin: CT threshold (HU above -300, largest component, holes filled). Lung vessels: CT iso-surface (HU above -470) inside the eroded lung masks, small pieces removed. **Changes were made.** |
| Brain ghost (cortex, cerebellum, brainstem) | Template cortex (fsaverage, FreeSurfer lineage; Fischl et al. 1999, doi 10.1002/(sici)1097-0193(1999)8:4<272::aid-hbm10>3.0.co;2-4) and MNI152NLin2009cAsym aseg (Fonov et al. 2011, doi 10.1016/j.neuroimage.2010.07.033), decimated here (cortex about 3,000 vertices per hemisphere in the lite scene) | fsaverage: Suspected (no licence file found); MNI: Confirmed permissive text | affine ICP fit of the template into the subject's brain mask. **ILLUSTRATIVE: the folds are the template's, not this subject's.** The subject's own brain segmentation (no folds) is in `SW_BRAIN_CT`, hidden by default. |
| Look | glow, halos, colours, translucency, smoke | none | artistic rendering choices; not tissue properties |

The subject has a pronounced forward head posture and raised arms; this is shown as recorded. Not for diagnosis.
Builder: `tools/build_torso_scene.py` (sha256 prefix {builder_sha}).
"""

# --------------------------------------------------------------------------------------------
# 8. main
# --------------------------------------------------------------------------------------------
def write_env(dst: Path, size=64):
    """Studio cube faces: the recipe of xscripts/studio_env.py (four soft lights over a dark blue-grey sky)."""
    from PIL import Image
    faces = {"front": ((0, 0, -1), (1, 0, 0), (0, 1, 0)), "back": ((0, 0, 1), (-1, 0, 0), (0, 1, 0)), "left": ((-1, 0, 0), (0, 0, -1), (0, 1, 0)),
             "right": ((1, 0, 0), (0, 0, 1), (0, 1, 0)), "top": ((0, 1, 0), (1, 0, 0), (0, 0, 1)), "bottom": ((0, -1, 0), (1, 0, 0), (0, 0, -1))}
    lights = [((-0.5, 0.6, 0.62), (1.0, 0.95, 0.86), 0.42, 0.22), ((0.0, 1.0, 0.1), (0.75, 0.85, 0.95), 0.5, 0.35),
              ((0.75, -0.05, 0.5), (0.35, 0.62, 0.85), 0.35, 0.3), ((0.35, 0.45, -0.82), (1.0, 0.72, 0.4), 0.18, 0.12)]
    dst.mkdir(parents=True, exist_ok=True)
    for name, (fwd, right, up) in faces.items():
        s = (np.arange(size) + 0.5) / size * 2 - 1
        u, v = np.meshgrid(s, -s)
        d = np.stack([fwd[i] + u * right[i] + v * up[i] for i in range(3)], -1)
        d /= np.linalg.norm(d, axis=-1, keepdims=True)
        y = d[..., 1:2]
        img = np.where(y > 0, 0.10 + 0.12 * y, 0.06 + 0.03 * y) * np.array([0.55, 0.85, 1.0])
        for ld, col, rad, soft in lights:
            ld = np.array(ld) / np.linalg.norm(ld)
            ang = np.arccos(np.clip(d @ ld, -1, 1))[..., None]
            img = img + np.clip((rad + soft - ang) / soft, 0, 1) ** 2 * np.array(col)
        Image.fromarray((np.clip(img, 0, 1) ** (1 / 2.2) * 255 + 0.5).astype(np.uint8), "RGB").save(dst / f"studio-{name}.png", optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", required=True, help="folder holding s1397_resampled.vtm and s1397_resampled/*.vti")
    ap.add_argument("--out", required=True, help="output folder for torso_ct.x3d, torso_ct_lite.x3d, tex/env64/")
    ap.add_argument("--repo-scenes", default=None, help="also write torso_ct_lite.x3d and tex/env64/ here (the repository scenes folder)")
    ap.add_argument("--repo-data", default=None, help="also write torso_regions.json and TORSO-NOTICE.md here (the repository data folder)")
    ap.add_argument("--cache", default=None, help="mesh cache folder (default OUT/mesh-cache)")
    ap.add_argument("--variants", default="lite,full")
    ap.add_argument("--template-meshes", default=None, help="optional npz with the template cortex meshes (vL,fL,cL,vR,fR,cR,sv_/sf_cerebellum,brainstem; the builder decimates them for the scene) for the brain ghost; "
                    "without it the brain is the subject's segmentation")
    a = ap.parse_args()
    t0 = time.time()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    log = lambda s: print(s, flush=True)
    me = Path(__file__).read_bytes()
    builder_sha = sha256_bytes(me)
    subj = Subject(Path(a.src))
    log(f"subject: ct {subj.ct.shape} spacing {subj.spacing} origin {subj.origin}; {len(subj.names)} segmentations; quadric decimation: {'fast_simplification' if _fs else 'vertex clustering fallback'}")
    bank = MeshBank(subj, Path(a.cache) if a.cache else out / "mesh-cache")
    write_env(out / "tex" / "env64")
    report = {}
    template, tinfo = None, None
    if a.template_meshes:
        template, tinfo = template_brain(bank, subj, Path(a.template_meshes), log)
    for q in a.variants.split(","):
        items = prepare(bank, subj, q, log, template)
        meta = dict(title="Torso CT (full)" if q == "full" else "Torso CT (lite)", variant=q, builder_sha=builder_sha,
                    template=template is not None, icp=(tinfo or {}).get("icp_mean_two_way_mm"))
        body, bounds = build_scene(items, q, meta)
        doc = compose_document(body, bounds, meta)
        name = "torso_ct.x3d" if q == "full" else "torso_ct_lite.x3d"
        data = doc.encode("utf-8")
        (out / name).write_bytes(data)
        nv = sum(len(i["v"]) for i in items)
        nt = sum(len(i["f"]) for i in items)
        report[q] = dict(template_fit=tinfo, file=name, bytes=len(data), sha256=sha256_bytes(data), shapes=len(items), vertices=nv, triangles=nt,
                         bounds_min=bounds[0].round(1).tolist(), bounds_max=bounds[1].round(1).tolist())
        log(f"{name}: {len(data) / 1e6:.2f} MB, {len(items)} shapes, {nv} vertices, {nt} triangles, sha256 {sha256_bytes(data)}")
        if q == "lite":
            sw_of = {g: sw for sw, g, _, _ in GROUPS}
            regions = [dict(id=f"STRUCT_{i['label']}", label=i["label"], group=i["grp"], switch=sw_of.get(i["grp"]), source=i["source"], volume_ml=None if i["vol_ml"] is None else round(i["vol_ml"], 1),
                            centroid_mm=i["v"].mean(0).round(1).tolist(), bbox_min_mm=i["v"].min(0).round(1).tolist(), bbox_max_mm=i["v"].max(0).round(1).tolist(),
                            lite_vertices=len(i["v"]), lite_triangles=len(i["f"])) for i in items]
            regions_json = json.dumps(dict(note="Scene units are mm; X patient-right, Y up, Z posterior. Volumes are voxel counts of the TotalSegmentator segmentation at 3 mm (subject s1397). "
                                                "Centroids/bboxes are of the lite mesh. Template brain parts are an ILLUSTRATIVE fit, skin and lung vessels are CT thresholds.",
                                           builder_sha256=builder_sha, regions=regions), indent=1)
            (out / "torso_regions.json").write_text(regions_json)
            report[q]["regions_json_sha256"] = sha256_bytes(regions_json.encode())
            notice = NOTICE.format(builder_sha=builder_sha[:16])
            (out / "TORSO-NOTICE.md").write_text(notice)
            if a.repo_data:
                rd = Path(a.repo_data)
                rd.mkdir(parents=True, exist_ok=True)
                (rd / "torso_regions.json").write_text(regions_json)
                (rd / "TORSO-NOTICE.md").write_text(notice)
        if q == "lite" and a.repo_scenes:
            rs = Path(a.repo_scenes)
            rs.mkdir(parents=True, exist_ok=True)
            (rs / name).write_bytes(data)
            write_env(rs / "tex" / "env64")
            log(f"copied {name} and tex/env64/ to {rs}")
    (out / "torso_build_report.json").write_text(json.dumps(dict(builder_sha256=builder_sha, report=report), indent=1))
    log(f"done in {time.time() - t0:.1f} s; builder sha256 {builder_sha}")


if __name__ == "__main__":
    main()
