"""Site scenes, look v2: the same data-true geometry as zinc_site_scene.py, with the look gains folded back from the
audit of a second model's re-render (runs/zinc-remix-review-20261106/REVIEW.md).

  python3 -I kit/examples/zinc_site_scene_v2.py CANDIDATE PDB_ID OUT.x3d

What is data and what is look (law 34). DATA, unchanged from v1 and checked by the same data-true reader: every
atom position, every bond end, the bond length printed on each label, the under-2.5 angstrom glow rule, the
backbone and nucleic tube spines, the camera rule. NEW DATA, also checked: each label now names its donor
("CYS 159 SG"), and a coordination cage is drawn only for a site whose four ligands all glow, with its vertices at
exactly those four donor atoms. LOOK, declared and not data: physically based materials, a studio environment
(EnvironmentLight over a generated cube map, X3D 4.1), three directional lights placed in the first site's camera
frame (key, fill, rim), atom and stick radii, tube thickness and colour, the label backing card, the background.
v1 gave every zinc a constant glow; v2 drops it, so the only emissive parts are the glowing bonds and the labels.
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
import zinc_site_scene as v1  # noqa: E402  (geometry rules and the camera rule are shared, not copied)
from zinc_structures import STRUCTURES  # noqa: E402

GLOW_BELOW, LABEL_BEYOND, f3, vec = v1.GLOW_BELOW, v1.LABEL_BEYOND, v1.f3, v1.vec
ENV_FACES = ("front", "back", "left", "right", "top", "bottom")
# Physically based materials per element: baseColor, metallic, roughness (look, not data).
PBR = {"C": ("0.27 0.37 0.44", 0.25, 0.30), "N": ("0.10 0.30 0.80", 0.15, 0.28), "O": ("0.85 0.18 0.14", 0.10, 0.30),
       "S": ("0.95 0.62 0.10", 0.35, 0.26), "ZN": ("0.92 0.95 0.98", 0.85, 0.18)}
RADIUS = {"C": 0.30, "N": 0.30, "O": 0.30, "S": 0.40, "ZN": 0.60}
STICK = 0.11


def basis(eye, target):
    f = v1.norm_(vec(eye, target))
    r = v1.norm_((f[1] * 0 - f[2] * 1, f[2] * 0 - f[0] * 0, f[0] * 1 - f[1] * 0))  # f x up
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    return r, u, f


def cam_to_world(d, b):
    r, u, f = b
    return v1.norm_(tuple(d[0] * r[i] + d[1] * u[i] - d[2] * f[i] for i in range(3)))


def pbr(color, metallic, roughness, transparency=0.0, emissive=None) -> str:
    e = f" emissiveColor='{emissive}'" if emissive else ""
    t = f" transparency='{transparency}'" if transparency else ""
    return f"<PhysicalMaterial baseColor='{color}' metallic='{metallic}' roughness='{roughness}'{e}{t}/>"


def donor_name(d) -> str:
    return f"{d['resname']} {d['resseq']} {d['name']}"


def build(cand: Path, pid: str, env_url: str = "env") -> tuple[str, dict]:
    v1_text, manifest = v1.build(cand, pid)  # the data: atoms, bonds, tubes and camera exactly as v1 computes them
    spec = json.loads((cand / "specs" / f"{pid}.json").read_text())
    raw = (cand / "structures" / f"pdb{pid}.ent.gz").read_bytes()
    atoms = ms.parse_pdb(ms.read_coordinates(cand / "structures" / f"pdb{pid}.ent.gz"))[0]
    what, method, _, _ = STRUCTURES[pid]
    by = {v1.atom_name(a): a for a in atoms}
    drawn = {n: by[n] for n in manifest["atoms_drawn"]}
    import xml.etree.ElementTree as ET
    root = ET.fromstring(v1_text.split("\n", 2)[2] if v1_text.startswith("<?xml") else v1_text)
    views = [(vp.get("description"), tuple(map(float, vp.get("position").split())), vp.get("orientation"),
              tuple(map(float, vp.get("centerOfRotation").split()))) for vp in root.iter("Viewpoint")]
    tubes = [(sh.get("DEF"), sh.find(".//Extrusion").get("spine")) for sh in root.iter("Shape") if sh.get("DEF", "").startswith(("Backbone_", "Nucleic_"))]
    sites = []
    for site in spec["sites"]:
        zn = ms._metals(atoms, site["metal"])[0]
        donors = sorted(ms.ligands(atoms, zn, spec["search_radius"]), key=lambda a: (a["chain"], str(a["resseq"]), a["name"]))
        sites.append((zn, donors))

    b0 = basis(views[0][1], views[0][3])
    key, fill, rim = (cam_to_world(d, b0) for d in ((0.55, -0.7, -0.45), (-0.7, 0.1, -0.6), (-0.4, -0.5, 0.8)))
    out = ["<?xml version='1.0' encoding='UTF-8'?>",
           "<X3D profile='Interchange' version='4.1' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' "
           "xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.1.xsd'>",
           "<head><component name='Shape' level='2'/><component name='Lighting' level='3'/><component name='CubeMapTexturing' level='1'/>"
           "<component name='Geometry3D' level='4'/><component name='Navigation' level='2'/><component name='Text' level='1'/>",
           f"<meta name='title' content={quoteattr(f'{pid.upper()} zinc site: {what}')}/>",
           f"<meta name='description' content={quoteattr(f'{method}. Model 1 as deposited. One unit is one angstrom. A bond to zinc glows only while it measures under {GLOW_BELOW} angstrom. Materials, lights, radii and the cage faces are look, not data.')}/>",
           f"<meta name='source' content={quoteattr(f'wwPDB snapshot 2026-01-01, pdb{pid}.ent.gz sha256 {hashlib.sha256(raw).hexdigest()}')}/>",
           f"<meta name='generator' content='x3d.loom kit/examples/zinc_site_scene_v2.py sha256 {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()} over zinc_site_scene.py sha256 {hashlib.sha256(Path(v1.__file__).read_bytes()).hexdigest()}'/>",
           "<meta name='license' content='Coordinates: wwPDB, CC0 1.0'/></head>",
           "<Scene>",
           "<WorldInfo title=" + quoteattr(f"{pid.upper()} zinc site") + "/>",
           "<NavigationInfo type='\"EXAMINE\" \"ANY\"' headlight='false'/>",
           "<Background skyColor='0.02 0.04 0.055' transparency='1'/>",
           f"<EnvironmentLight DEF='Studio' intensity='1.15' rotation='{views[0][2]}'><ComposedCubeMapTexture containerField='specularTexture'>"
           + "".join(f"<ImageTexture containerField='{f}Texture' url='\"{env_url}/studio-{f}.png\"'/>" for f in ENV_FACES)
           + "</ComposedCubeMapTexture></EnvironmentLight>",
           f"<DirectionalLight DEF='Key' direction='{' '.join(f'{c:.4f}' for c in key)}' intensity='2.2' color='1 0.95 0.87'/>",
           f"<DirectionalLight DEF='Fill' direction='{' '.join(f'{c:.4f}' for c in fill)}' intensity='1.0' color='0.42 0.79 1'/>",
           f"<DirectionalLight DEF='Rim' direction='{' '.join(f'{c:.4f}' for c in rim)}' intensity='1.4' color='1 0.74 0.36'/>"]
    for title, eye, orient, target in views:
        out.append(f"<Viewpoint description={quoteattr(title)} position='{' '.join(f3(c) for c in eye)}' "
                   f"orientation='{orient}' centerOfRotation='{' '.join(f3(c) for c in target)}' fieldOfView='0.6'/>")
    used = set()
    for name, a in sorted(drawn.items()):
        el = "ZN" if a["resname"] == "ZN" else a["element"]
        proto = f"ATOM_{el}"
        if proto in used:
            shape = f"<Shape USE='{proto}'/>"
        else:
            used.add(proto)
            c, m, r = PBR.get(el, ("0.8 0.8 0.8", 0.1, 0.4))
            shape = f"<Shape DEF='{proto}'><Appearance>{pbr(c, m, r)}</Appearance><Sphere radius='{RADIUS.get(el, 0.3)}'/></Shape>"
        out.append(f"<Transform DEF='{name}' translation='{' '.join(f3(c) for c in a['xyz'])}'>{shape}</Transform>")
    res = {}
    for a in drawn.values():
        res.setdefault((a["chain"], a["resseq"]), []).append(a)
    stick = "<Shape DEF='STICK'><Appearance>" + pbr("0.46 0.55 0.61", 0.2, 0.36) + f"</Appearance><Cylinder radius='{STICK}' height='1'/></Shape>"
    first = True
    for group in res.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                r = ms._dist(a["xyz"], b["xyz"])
                if r < 1.95:
                    mid = tuple((p + q) / 2 for p, q in zip(a["xyz"], b["xyz"]))
                    out.append(f"<Transform translation='{' '.join(f3(c) for c in mid)}' rotation='{v1.rot_y_to(vec(a['xyz'], b['xyz']))}' "
                               f"scale='1 {r:.4f} 1'>{stick if first else chr(60) + 'Shape USE=' + chr(39) + 'STICK' + chr(39) + '/>'}</Transform>")
                    first = False
    for zn, donors in sites:
        glowing = [d for d in donors if ms._dist(zn["xyz"], d["xyz"]) < GLOW_BELOW]
        for d in donors:
            r = ms._dist(zn["xyz"], d["xyz"])
            glow = r < GLOW_BELOW
            mid = tuple((p + q) / 2 for p, q in zip(zn["xyz"], d["xyz"]))
            col, emis = (("1.0 0.85 0.3", "0.9 0.62 0.12") if d["element"] == "S" else ("0.4 0.7 1.0", "0.2 0.45 1.0")) if glow \
                else ("0.35 0.35 0.38", "0 0 0")
            tag = f"Bond_{zn['chain']}{zn['resseq']}_{d['resname']}{d['resseq']}_{d['name']}"
            out.append(f"<Transform DEF='{tag}' translation='{' '.join(f3(c) for c in mid)}' rotation='{v1.rot_y_to(vec(zn['xyz'], d['xyz']))}' "
                       f"scale='1 {r:.4f} 1'><Shape><Appearance><Material diffuseColor='{col}' emissiveColor='{emis}'/></Appearance>"
                       f"<Cylinder radius='{0.09 if glow else 0.05}' height='1'/></Shape></Transform>")
            u = tuple(c / r for c in vec(zn["xyz"], d["xyz"]))
            lab = tuple(z + (r + LABEL_BEYOND) * c for z, c in zip(zn["xyz"], u))
            ink = "1 0.86 0.52" if (glow and d["element"] == "S") else ("0.62 0.8 1" if glow else "0.7 0.72 0.76")
            out.append(f"<Transform DEF='Label_{tag[5:]}' translation='{' '.join(f3(c) for c in lab)}'><Billboard axisOfRotation='0 0 0'><Transform translation='0 0 1.2'>"
                       f"<Shape><Appearance><Material diffuseColor='0 0 0' emissiveColor='{ink}'/></Appearance>"
                       f"<Text string='\"{r:.2f} Å\"'><FontStyle family='\"SANS\"' size='0.42' justify='\"MIDDLE\" \"MIDDLE\"'/></Text></Shape>"
                       f"<Transform translation='0 0.38 0'><Shape DEF='Name_{tag[5:]}'><Appearance><Material diffuseColor='0 0 0' emissiveColor='0.78 0.84 0.88'/></Appearance>"
                       f"<Text string={quoteattr(chr(34) + donor_name(d) + chr(34))}><FontStyle family='\"TYPEWRITER\"' size='0.24' justify='\"MIDDLE\" \"MIDDLE\"'/></Text></Shape></Transform>"
                       f"<Transform translation='0 0.13 -0.02'><Shape><Appearance><Material diffuseColor='0 0 0' emissiveColor='0.02 0.05 0.07' transparency='0.25'/></Appearance>"
                       f"<IndexedFaceSet coordIndex='0 1 2 3 -1' solid='false'><Coordinate point='-0.85 -0.3 0 0.85 -0.3 0 0.85 0.56 0 -0.85 0.56 0'/></IndexedFaceSet></Shape></Transform>"
                       f"</Transform></Billboard></Transform>")
        if len(donors) == 4 and len(glowing) == 4:
            pts = " ".join(" ".join(f3(c) for c in d["xyz"]) for d in donors)
            cname = f"Cage_{zn['chain']}{zn['resseq']}"
            out.append(f"<Shape DEF='{cname}'><Appearance>{pbr('0.25 0.75 0.72', 0.0, 0.5, transparency=0.88, emissive='0.02 0.08 0.08')}</Appearance>"
                       f"<IndexedFaceSet coordIndex='0 1 2 -1 0 1 3 -1 0 2 3 -1 1 2 3 -1' solid='false'><Coordinate point='{pts}'/></IndexedFaceSet></Shape>")
            out.append(f"<Shape DEF='{cname}_edges'><Appearance><Material diffuseColor='0 0 0' emissiveColor='0.3 0.75 0.72' transparency='0.55'/></Appearance>"
                       f"<IndexedLineSet coordIndex='0 1 -1 0 2 -1 0 3 -1 1 2 -1 1 3 -1 2 3 -1'><Coordinate point='{pts}'/></IndexedLineSet></Shape>")
    for name, spine in tubes:
        pts = [tuple(map(float, spine.split()[i:i + 3])) for i in range(0, len(spine.split()), 3)]
        prot = name.startswith("Backbone_")
        # v1 spines are already Catmull-Rom smoothed; pass them through unchanged (catmull of 2 points returns them as-is)
        cs_r = 0.24 if prot else 0.3
        cs = " ".join(f"{cs_r * math.cos(2 * math.pi * k / 24):.3f} {cs_r * math.sin(2 * math.pi * k / 24):.3f}" for k in range(25))
        out.append(f"<Shape DEF={quoteattr(name)}><Appearance>{pbr('0.03 0.10 0.20' if prot else '0.78 0.42 0.16', 0.2, 0.22)}</Appearance>"
                   f"<Extrusion crossSection='{cs}' spine='{spine}' creaseAngle='1.6' beginCap='true' endCap='true'/></Shape>")
    out += ["</Scene>", "</X3D>"]
    manifest = dict(manifest, look="v2", labels_name_donor=True,
                    cages=[f"{z['chain']}{z['resseq']}" for z, ds in sites if len(ds) == 4 and all(ms._dist(z["xyz"], d["xyz"]) < GLOW_BELOW for d in ds)])
    return "\n".join(out) + "\n", manifest


if __name__ == "__main__":
    cand, pid, dest = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    text, manifest = build(cand, pid)
    dest.write_text(text, encoding="utf-8")
    dest.with_suffix(".json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"scene": dest.name, "atoms": len(manifest["atoms_drawn"]), "bonds": len(manifest["bonds"]),
                      "cages": manifest["cages"], "tubes": len(manifest["tubes"])}))
