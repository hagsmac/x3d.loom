"""Site scenes for the zinc finger study (P1): one X3D world per structure, generated from its first deposited model.

  python3 -I kit/examples/zinc_site_scene.py CANDIDATE PDB_ID OUT.x3d

Data-true rules (no visual event without a data event):
- every atom drawn is a Transform named after its PDB atom (DEF A_<chain>_<resname>_<resseq>_<name>) placed at the
  deposited coordinate, written with the file's own three decimals; nothing is moved for looks;
- the atoms drawn are exactly: each declared zinc; every ligand atom within the spec's search radius of it in
  model 1, found by element (N, O, S, Se, halogens) as the metal-site witness finds them; and, for a side-chain
  donor the witness's table names, that residue's side chain from CA;
- a zinc-donor bond is drawn for each ligand atom and GLOWS only while its measured length is under 2.5 angstrom; its
  label prints that length to two decimals and sits on the bond's own line, 1 angstrom past the donor atom;
- the backbone tube runs through the C-alpha atoms of the finger (4 residues either side of its ligands), smoothed by
  Catmull-Rom interpolation between them (declared, and not an atom); the nucleic-acid tube runs through phosphorus
  atoms within 18 angstrom of a zinc, the same way;
- one X3D unit is one angstrom. Only the camera is free, and it is placed by a stated rule (choose_view): the
  direction around each zinc that leaves its donors and labels least covered and least crowded, far enough back
  that every label is in frame.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loomkit import metalsite as ms  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zinc_structures import STRUCTURES  # noqa: E402

GLOW_BELOW = 2.5
LABEL_BEYOND = 1.0  # a bond's label sits on its line, this far past the donor atom
SIDE = {"CYS": ("CA", "CB", "SG"), "HIS": ("CA", "CB", "CG", "ND1", "CD2", "CE1", "NE2"),
        "ASP": ("CA", "CB", "CG", "OD1", "OD2"), "GLU": ("CA", "CB", "CG", "CD", "OE1", "OE2")}
COLOR = {"C": "0.55 0.58 0.62", "N": "0.25 0.45 1.0", "O": "1.0 0.25 0.2", "S": "1.0 0.82 0.15", "ZN": "0.78 0.82 0.88"}
RADIUS = {"C": 0.28, "N": 0.28, "O": 0.28, "S": 0.36, "ZN": 0.52}
NUCLEIC = {"A", "C", "G", "U", "DA", "DC", "DG", "DT", "DU"}


def f3(v: float) -> str:
    s = f"{v:.3f}"
    return "0.000" if s == "-0.000" else s


def vec(a, b):
    return tuple(q - p for p, q in zip(a, b))


def norm(v):
    return math.sqrt(sum(c * c for c in v))


def rot_y_to(v) -> str:
    """Axis-angle that turns +Y onto direction v (for a unit cylinder along Y)."""
    n = norm(v); x, y, z = (c / n for c in v)
    ax = (z, 0.0, -x)  # (0,1,0) x v
    s = norm(ax)
    ang = math.acos(max(-1.0, min(1.0, y)))
    if s < 1e-9:
        return "1 0 0 0" if y > 0 else "1 0 0 3.141593"
    return f"{ax[0] / s:.6f} {ax[1] / s:.6f} {ax[2] / s:.6f} {ang:.6f}"


def look_at(eye, target) -> str:
    """Viewpoint orientation looking from eye to target with +Y kept as up where possible."""
    f = vec(eye, target); n = norm(f); f = tuple(c / n for c in f)
    up = (0.0, 1.0, 0.0)
    r = (f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0])
    if norm(r) < 1e-6:
        r = (1.0, 0.0, 0.0)
    rn = norm(r); r = tuple(c / rn for c in r)
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    # rotation matrix columns: right, up, -forward
    m = [[r[0], u[0], -f[0]], [r[1], u[1], -f[1]], [r[2], u[2], -f[2]]]
    tr = m[0][0] + m[1][1] + m[2][2]
    ang = math.acos(max(-1.0, min(1.0, (tr - 1) / 2)))
    if ang < 1e-6:
        return "0 0 1 0"
    if abs(ang - math.pi) < 1e-4:
        xx = math.sqrt(max(0.0, (m[0][0] + 1) / 2)); yy = math.sqrt(max(0.0, (m[1][1] + 1) / 2)); zz = math.sqrt(max(0.0, (m[2][2] + 1) / 2))
        if m[0][1] < 0: yy = -yy
        if m[0][2] < 0: zz = -zz
        return f"{xx:.6f} {yy:.6f} {zz:.6f} {ang:.6f}"
    s = 2 * math.sin(ang)
    return f"{(m[2][1] - m[1][2]) / s:.6f} {(m[0][2] - m[2][0]) / s:.6f} {(m[1][0] - m[0][1]) / s:.6f} {ang:.6f}"


def choose_view(zn, donors, labels, occluders, fov=0.6, n=600):
    """The camera rule (declared; the camera is the only free thing). Try n directions spread evenly over the sphere
    around the zinc (a Fibonacci lattice, skipping the poles so +Y can stay up). For each, back off until every donor
    and label fits the field of view with a margin, then score it, in perspective from that camera, by
    (1) how many drawn things (tube points, other atoms) sit between the camera and the zinc, a donor or a label and
    cover it on screen, then (2) how close any two labels, or a label and the zinc, come on screen (closer than
    1.6 angstrom at the zinc's depth costs). The lowest score wins (ties: the first direction). Deterministic: the
    same coordinates always give the same camera."""
    best = None
    t = math.tan(fov / 2)
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        if abs(y) > 0.85:
            continue
        rr = math.sqrt(1 - y * y); phi = i * math.pi * (3 - math.sqrt(5))
        v = (rr * math.cos(phi), y, rr * math.sin(phi))
        right = norm_((v[2], 0.0, -v[0]))
        up = (v[1] * right[2] - v[2] * right[1], v[2] * right[0] - v[0] * right[2], v[0] * right[1] - v[1] * right[0])

        def proj(p):
            q = vec(zn, p)
            return dot(q, right), dot(q, up), dot(q, v)
        extent = (max(math.hypot(*proj(p)[:2]) for p in donors + labels) + 1.2) if donors else 4.0
        dist = min(24.0, max(9.0, extent / t))

        def screen(p, r):  # perspective: position and radius on a screen at the zinc's depth
            x, yy, depth = proj(p)
            z = dist - depth
            return None if z <= 0.3 else (x * dist / z, yy * dist / z, r * dist / z, depth)
        keys = [screen(p, 0.6) for p in [zn] + donors] + [screen(p, 0.75) for p in labels]
        keys = [k for k in keys if k]
        covered = 0
        for p, r in occluders:
            o = screen(p, r)
            if o:  # behind the camera nothing covers anything
                covered += any(o[3] > k[3] + 0.3 and math.hypot(o[0] - k[0], o[1] - k[1]) < o[2] + k[2] for k in keys)
        pts = [screen(p, 0)[:2] for p in [zn] + labels if screen(p, 0)]
        crowd = sum(max(0.0, 1.6 - math.hypot(a[0] - b[0], a[1] - b[1])) for i2, a in enumerate(pts) for b in pts[i2 + 1:])
        score = covered + 2.0 * crowd
        if best is None or score < best[0] - 1e-9:
            best = (score, v, dist)
    _, v, dist = best
    return tuple(z + dist * c for z, c in zip(zn, v))


def dot(a, b):
    return sum(p * q for p, q in zip(a, b))


def norm_(v):
    n = norm(v) or 1.0
    return tuple(c / n for c in v)


def catmull(points, per=4):
    if len(points) < 3:
        return points
    out, p = [], [points[0]] + points + [points[-1]]
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for k in range(per):
            t = k / per; t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)
                             for a, b, c, d in zip(p0, p1, p2, p3)))
    out.append(points[-1])
    return out


def tube(points, radius, color, transparency, name) -> str:
    cs = " ".join(f"{radius * math.cos(2 * math.pi * k / 10):.3f} {radius * math.sin(2 * math.pi * k / 10):.3f}" for k in range(11))
    spine = " ".join(" ".join(f3(c) for c in p) for p in catmull(points))
    return (f"<Shape DEF={quoteattr(name)}><Appearance><Material diffuseColor='{color}' specularColor='0.6 0.7 0.9' "
            f"shininess='0.5' transparency='{transparency}'/></Appearance>"
            f"<Extrusion crossSection='{cs}' spine='{spine}' creaseAngle='1.6' solid='false'/></Shape>")


def atom_name(a) -> str:
    return f"A_{a['chain']}_{a['resname']}_{a['resseq']}_{a['name']}"


def build(cand: Path, pid: str) -> tuple[str, dict]:
    spec = json.loads((cand / "specs" / f"{pid}.json").read_text())
    raw = (cand / "structures" / f"pdb{pid}.ent.gz").read_bytes()
    atoms = ms.parse_pdb(ms.read_coordinates(cand / "structures" / f"pdb{pid}.ent.gz"))[0]
    what, method, _, _ = STRUCTURES[pid]
    drawn, bonds, tubes, views, sites = {}, [], [], [], []
    for site in spec["sites"]:
        zn = ms._metals(atoms, site["metal"])[0]
        drawn[atom_name(zn)] = zn
        donors = sorted(ms.ligands(atoms, zn, spec["search_radius"]), key=lambda a: (a["chain"], str(a["resseq"]), a["name"]))
        for d in donors:
            drawn[atom_name(d)] = d
            side = SIDE.get(ms.CANON.get(d["resname"], d["resname"])) if ms.listed(d) else None
            for a in atoms if side else ():
                if a["chain"] == d["chain"] and a["resseq"] == d["resseq"] and a["name"] in side:
                    drawn[atom_name(a)] = a
            r = ms._dist(zn["xyz"], d["xyz"])
            bonds.append((zn, d, r))
        prot = [d for d in donors if d["resname"] in ms.PROTEIN and isinstance(d["resseq"], int)]
        if prot:
            lo, hi = min(d["resseq"] for d in prot) - 4, max(d["resseq"] for d in prot) + 4
            ca = [a for a in atoms if a["name"] == "CA" and a["chain"] == prot[0]["chain"] and isinstance(a["resseq"], int)
                  and lo <= a["resseq"] <= hi]
            run = [ca[0]] if ca else []
            for a in ca[1:]:
                if a["resseq"] - run[-1]["resseq"] == 1:
                    run.append(a)
                else:
                    if len(run) > 2: tubes.append(("protein", [x["xyz"] for x in run], f"Backbone_{zn['chain']}{zn['resseq']}_{run[0]['resseq']}"))
                    run = [a]
            if len(run) > 2: tubes.append(("protein", [x["xyz"] for x in run], f"Backbone_{zn['chain']}{zn['resseq']}_{run[0]['resseq']}"))
        sites.append((zn, donors))
    zns = [a for a in drawn.values() if a["resname"] == "ZN"]
    for ch in sorted({a["chain"] for a in atoms if a["resname"].strip() in NUCLEIC}):
        ps = [a for a in atoms if a["chain"] == ch and a["name"] == "P" and a["resname"].strip() in NUCLEIC
              and min(ms._dist(a["xyz"], z["xyz"]) for z in zns) <= 18.0]
        if len(ps) > 2:
            tubes.append(("nucleic", [p["xyz"] for p in ps], f"Nucleic_{ch}"))
    clutter = [(t, 0.3) for _, pts, _ in tubes for t in catmull(pts)]
    for zn, donors in sites:
        keep = {id(zn)} | {id(d) for d in donors}
        occ = clutter + [(a["xyz"], RADIUS.get(a["element"], 0.28)) for a in drawn.values() if id(a) not in keep]
        labels = [tuple(z + (ms._dist(zn["xyz"], d["xyz"]) + LABEL_BEYOND) * c / ms._dist(zn["xyz"], d["xyz"])
                        for z, c in zip(zn["xyz"], vec(zn["xyz"], d["xyz"]))) for d in donors]
        eye = choose_view(zn["xyz"], [d["xyz"] for d in donors], labels, occ)
        views.append((f"Site {zn['chain']}{zn['resseq']}", eye, zn["xyz"]))

    out = ["<?xml version='1.0' encoding='UTF-8'?>",
           "<!DOCTYPE X3D PUBLIC 'ISO//Web3D//DTD X3D 4.0//EN' 'https://www.web3d.org/specifications/x3d-4.0.dtd'>",
           "<X3D profile='Interchange' version='4.0' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' "
           "xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.0.xsd'>",
           "<head><component name='Geometry3D' level='4'/><component name='Navigation' level='2'/><component name='Text' level='1'/>",
           f"<meta name='title' content={quoteattr(f'{pid.upper()} zinc site: {what}')}/>",
           f"<meta name='description' content={quoteattr(f'{method}. Model 1 as deposited. One unit is one angstrom. A bond to zinc glows only while it measures under {GLOW_BELOW} angstrom.')}/>",
           f"<meta name='source' content={quoteattr(f'wwPDB snapshot 2026-01-01, pdb{pid}.ent.gz sha256 {hashlib.sha256(raw).hexdigest()}')}/>",
           f"<meta name='generator' content='x3d.loom kit/examples/zinc_site_scene.py sha256 {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}'/>",
           "<meta name='license' content='Coordinates: wwPDB, CC0 1.0'/></head>",
           "<Scene>",
           "<WorldInfo title=" + quoteattr(f"{pid.upper()} zinc site") + "/>",
           "<NavigationInfo type='\"EXAMINE\" \"ANY\"' headlight='true'/>",
           "<Background skyColor='0.004 0.008 0.02'/>",
           "<DirectionalLight direction='-0.4 -0.6 -0.7' intensity='0.8' color='0.85 0.9 1.0'/>",
           "<DirectionalLight direction='0.6 0.3 0.5' intensity='0.35' color='0.5 0.6 1.0'/>"]
    for title, eye, target in views:
        out.append(f"<Viewpoint description={quoteattr(title)} position='{' '.join(f3(c) for c in eye)}' "
                   f"orientation='{look_at(eye, target)}' centerOfRotation='{' '.join(f3(c) for c in target)}' fieldOfView='0.6'/>")
    used = set()
    for name, a in sorted(drawn.items()):
        el = "ZN" if a["resname"] == "ZN" else a["element"]
        proto = f"ATOM_{el}"
        if proto in used:
            shape = f"<Shape USE='{proto}'/>"
        else:
            used.add(proto)
            emis = "0.12 0.14 0.18" if el == "ZN" else "0 0 0"
            shape = (f"<Shape DEF='{proto}'><Appearance><Material diffuseColor='{COLOR.get(el, '0.8 0.8 0.8')}' emissiveColor='{emis}' "
                     f"specularColor='1 1 1' shininess='0.8'/></Appearance><Sphere radius='{RADIUS.get(el, 0.28)}'/></Shape>")
        out.append(f"<Transform DEF='{name}' translation='{' '.join(f3(c) for c in a['xyz'])}'>{shape}</Transform>")
    res = {}
    for a in drawn.values():
        res.setdefault((a["chain"], a["resseq"]), []).append(a)
    for group in res.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                r = ms._dist(a["xyz"], b["xyz"])
                if r < 1.95:
                    mid = tuple((p + q) / 2 for p, q in zip(a["xyz"], b["xyz"]))
                    out.append(f"<Transform translation='{' '.join(f3(c) for c in mid)}' rotation='{rot_y_to(vec(a['xyz'], b['xyz']))}' "
                               f"scale='1 {r:.4f} 1'><Shape><Appearance><Material diffuseColor='0.42 0.45 0.5'/></Appearance>"
                               f"<Cylinder radius='0.11' height='1'/></Shape></Transform>")
    for zn, d, r in bonds:
        glow = r < GLOW_BELOW
        mid = tuple((p + q) / 2 for p, q in zip(zn["xyz"], d["xyz"]))
        col, emis = (("1.0 0.85 0.3", "0.9 0.65 0.15") if d["element"] == "S" else ("0.4 0.7 1.0", "0.25 0.5 1.0")) if glow \
            else ("0.35 0.35 0.38", "0 0 0")
        tag = f"Bond_{zn['chain']}{zn['resseq']}_{d['resname']}{d['resseq']}_{d['name']}"
        out.append(f"<Transform DEF='{tag}' translation='{' '.join(f3(c) for c in mid)}' rotation='{rot_y_to(vec(zn['xyz'], d['xyz']))}' "
                   f"scale='1 {r:.4f} 1'><Shape><Appearance><Material diffuseColor='{col}' emissiveColor='{emis}'/></Appearance>"
                   f"<Cylinder radius='{0.09 if glow else 0.05}' height='1'/></Shape></Transform>")
        u = tuple(c / r for c in vec(zn["xyz"], d["xyz"]))
        lab = tuple(z + (r + LABEL_BEYOND) * c for z, c in zip(zn["xyz"], u))  # on the bond's own line, past the donor
        out.append(f"<Transform DEF='Label_{tag[5:]}' translation='{' '.join(f3(c) for c in lab)}'><Billboard axisOfRotation='0 0 0'>"
                   f"<Shape><Appearance><Material diffuseColor='0 0 0' emissiveColor='0.92 0.95 1.0'/></Appearance>"
                   f"<Text string='\"{r:.2f} Å\"'><FontStyle family='\"SANS\"' size='0.42' justify='\"MIDDLE\" \"MIDDLE\"'/></Text>"
                   f"</Shape></Billboard></Transform>")
    for kind, pts, name in tubes:
        out.append(tube(pts, 0.22 if kind == "protein" else 0.3, "0.2 0.42 0.9" if kind == "protein" else "0.95 0.55 0.2",
                        0.35 if kind == "protein" else 0.25, name))
    out += ["</Scene>", "</X3D>"]
    manifest = {"pdb": pid, "atoms_drawn": sorted(drawn), "bonds": [
        {"site": f"{z['chain']}{z['resseq']}", "donor": f"{d['resname']}{d['resseq']}.{d['name']}", "angstrom": round(r, 4),
         "glow": r < GLOW_BELOW, "label": f"{r:.2f} Å"} for z, d, r in bonds], "tubes": [t[2] for t in tubes]}
    return "\n".join(out) + "\n", manifest


if __name__ == "__main__":
    cand, pid, dest = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    text, manifest = build(cand, pid)
    dest.write_text(text, encoding="utf-8")
    dest.with_suffix(".json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"scene": dest.name, "atoms": len(manifest["atoms_drawn"]), "bonds": len(manifest["bonds"]),
                      "glowing": sum(b["glow"] for b in manifest["bonds"]), "tubes": len(manifest["tubes"])}))
