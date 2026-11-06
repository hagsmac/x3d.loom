#!/usr/bin/env python3
"""Brain data -> compact scene-space meshes (npz) + mesh_report.json + data/regions.json.

Inputs (read-only, NOT copied into the repository):
  TemplateFlow tpl-fsaverage  pial surface, sulc, curv, Desikan-Killiany (aparc) labels, 10k or 41k density
  TemplateFlow tpl-MNI152NLin2009cAsym  1 mm aseg segmentation (deep structures; permissive MNI licence text, copyright notice kept in NOTICE)
  Optional: a Cycles AO bake of the same pial mesh (bake_out_<den>.npz + bake_in_<den>.npz), used only if it matches the mesh vertex for vertex.

Output coordinates are SCENE units: 1 unit = 1 mm in fsaverage space, X3D axes (x right, y superior, z toward a viewer
standing behind the head, so anterior is -z), centred on the middle of the pial bounding box. The npz and the report go to --out
(scratch, they hold the full-density surfaces); only regions.json goes to the repository data folder.

CORTEX: the template's own pial vertex set at the chosen density (10k = 10,242 and 41k = 40,962 vertices per hemisphere, as TemplateFlow
distributes them: lower-resolution versions of the 164k surface; nothing here decimates them). It is only moved rigidly (axes reordered to scene
axes, origin = pial bounding-box centre), so the cortex scale is exactly 1.000.

ALIGNMENT (SYNTHETIC / LOOK-LEVEL, not a registration): the aseg structures (and the T1 slices the scene builder cuts) live in MNI152NLin2009cAsym
space, the cortex in fsaverage. The DEEP MESHES AND SLICES are mapped with a per-axis scale + shift that makes the aseg cerebral-cortex bounding
box equal the fsaverage pial bounding box (scale about 0.95 to 0.97 per axis; the cortex itself is not scaled). That is the lead's original fit,
kept unchanged. It is good enough to put the thalamus under the right place in a glass brain; it is not an anatomical alignment of one subject's
data to another's.

Nothing in the files this tool writes to the repository (regions.json) or in the report holds an absolute path.

usage:  python -I prep_meshes.py --tf TEMPLATEFLOW_ROOT --den 41k --out OUTDIR [--data DATADIR] [--facts facts.json] [--bake xrender/t]
"""
import argparse, hashlib, json, re, sys, time
from pathlib import Path
import numpy as np
import nibabel as nib
from scipy import sparse
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes

# marching-cubes step size per structure and density (coarser step = fewer triangles; the smoothing below hides the voxel steps)
STEPS = {
    "41k": dict(thalamus=2, caudate=2, putamen=2, pallidum=2, hippocampus=2, amygdala=2, accumbens=1, ventricles=2, brainstem=2, cerebellum=3),
    "10k": dict(thalamus=3, caudate=3, putamen=3, pallidum=2, hippocampus=3, amygdala=2, accumbens=2, ventricles=3, brainstem=3, cerebellum=4),
}
# name: (aseg labels [left, right ...], gaussian sigma on the binary mask in voxels)
# the "ventricles" mesh joins aseg labels 4/43 (lateral), 5/44 (inferior lateral), 14 (third) and 15 (fourth): it is named "Ventricular system"
STRUCT = {
    "thalamus": ([10, 49], 1.0), "caudate": ([11, 50], 1.0), "putamen": ([12, 51], 1.0), "pallidum": ([13, 52], 1.0),
    "hippocampus": ([17, 53], 1.0), "amygdala": ([18, 54], 0.9), "accumbens": ([26, 58], 0.8),
    "ventricles": ([4, 43, 14, 15, 5, 44], 1.0), "brainstem": ([16], 1.2), "cerebellum": ([8, 47, 7, 46], 1.2),
}
STRUCT_NAME = dict(thalamus="Thalamus", caudate="Caudate nucleus", putamen="Putamen", pallidum="Globus pallidus", hippocampus="Hippocampus",
                   amygdala="Amygdala", accumbens="Nucleus accumbens", ventricles="Ventricular system", brainstem="Brainstem", cerebellum="Cerebellum")
FACTS_NAME = dict(thalamus="thalamus", caudate="Caudate Nucleus", putamen="Putamen", pallidum="Globus Pallidus", hippocampus="hippocampus",
                  amygdala="amygdala", accumbens="Nucleus Accumbens", ventricles=None, brainstem="Brainstem", cerebellum="Cerebellum")
STRUCT_LOBE = dict(thalamus="Diencephalon", caudate="Basal ganglia", putamen="Basal ganglia", pallidum="Basal ganglia", hippocampus="Limbic / medial temporal",
                   amygdala="Limbic / medial temporal", accumbens="Ventral striatum", ventricles="Ventricular system (CSF)", brainstem="Brainstem", cerebellum="Hindbrain")
# Desikan region -> (display name, lobe)
DESIKAN = {
    "bankssts": ("banks of the superior temporal sulcus", "temporal"), "caudalanteriorcingulate": ("caudal anterior cingulate", "cingulate"),
    "caudalmiddlefrontal": ("caudal middle frontal", "frontal"), "cuneus": ("cuneus", "occipital"), "entorhinal": ("entorhinal", "temporal"),
    "fusiform": ("fusiform", "temporal"), "inferiorparietal": ("inferior parietal", "parietal"), "inferiortemporal": ("inferior temporal", "temporal"),
    "isthmuscingulate": ("isthmus cingulate", "cingulate"), "lateraloccipital": ("lateral occipital", "occipital"),
    "lateralorbitofrontal": ("lateral orbitofrontal", "frontal"), "lingual": ("lingual", "occipital"), "medialorbitofrontal": ("medial orbitofrontal", "frontal"),
    "middletemporal": ("middle temporal", "temporal"), "parahippocampal": ("parahippocampal", "temporal"), "paracentral": ("paracentral lobule", "frontal"),
    "parsopercularis": ("pars opercularis", "frontal"), "parsorbitalis": ("pars orbitalis", "frontal"), "parstriangularis": ("pars triangularis", "frontal"),
    "pericalcarine": ("pericalcarine", "occipital"), "postcentral": ("postcentral", "parietal"), "posteriorcingulate": ("posterior cingulate", "cingulate"),
    "precentral": ("precentral", "frontal"), "precuneus": ("precuneus", "parietal"), "rostralanteriorcingulate": ("rostral anterior cingulate", "cingulate"),
    "rostralmiddlefrontal": ("rostral middle frontal", "frontal"), "superiorfrontal": ("superior frontal", "frontal"), "superiorparietal": ("superior parietal", "parietal"),
    "superiortemporal": ("superior temporal", "temporal"), "supramarginal": ("supramarginal", "parietal"), "frontalpole": ("frontal pole", "frontal"),
    "temporalpole": ("temporal pole", "temporal"), "transversetemporal": ("transverse temporal", "temporal"), "insula": ("insula", "insula"),
}
LOBE_ACCENT = dict(frontal="#4A90E2", parietal="#8B5CF6", temporal="#10B981", occipital="#FF922B", cingulate="#E63946", insula="#845EF7",
                   deep="#F4A261")
# facts.json uses a few different spellings; map a Desikan key to the name that file uses (None = no entry)
FACTS_ALIAS = {"parsopercularis": "pars opercularis (Broca)", "superiortemporal": "Superior temporal (auditory, Wernicke)", "transversetemporal": "transverse temporal (Heschl)",
               "pericalcarine": "Pericalcarine (V1)", "bankssts": None, "paracentral": "paracentral"}      # paracentral: display name "Paracentral lobule", facts key unchanged


def slug(name):
    """facts.json name -> key: lowercase, parenthetical dropped, non-alphanumerics to '_'."""
    return re.sub(r"[^a-z0-9]+", "_", re.sub(r"\(.*?\)", "", name).lower()).strip("_")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def to_scene(ras):
    """fsaverage RAS (x right, y anterior, z superior) -> X3D (x right, y up, z toward the viewer behind the head). Proper rotation (det +1)."""
    ras = np.asarray(ras, np.float64)
    return np.stack([ras[..., 0], ras[..., 2], -ras[..., 1]], -1)


def vertex_normals(v, f):
    n = np.zeros_like(v)
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    for k in range(3):
        np.add.at(n, f[:, k], fn)
    l = np.linalg.norm(n, axis=1, keepdims=True); l[l == 0] = 1
    return n / l


def taubin(v, f, iters=14, lam=0.52, mu=-0.55):
    """Volume-preserving smoothing (Taubin lambda|mu) of a triangle mesh."""
    n = len(v)
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    A = sparse.coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)).tocsr()
    A = ((A + A.T) > 0).astype(np.float64)
    d = np.asarray(A.sum(1)).ravel(); d[d == 0] = 1
    W = sparse.diags(1 / d) @ A
    v = v.astype(np.float64).copy()
    for _ in range(iters):
        v += lam * (W @ v - v)
        v += mu * (W @ v - v)
    return v


def outward(v, f):
    """Flip winding if the signed volume is negative so normals point out of the structure."""
    vol = np.einsum("ij,ij->i", v[f[:, 0]], np.cross(v[f[:, 1]], v[f[:, 2]])).sum() / 6
    return f if vol > 0 else f[:, ::-1].copy()


def save_npz(path, arrays):
    """np.savez_compressed with fixed zip timestamps and member order, so that the same inputs give the same bytes (the scene names this file's sha256)."""
    import zipfile
    from numpy.lib import format as npf
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for k in sorted(arrays):
            zi = zipfile.ZipInfo(k + ".npy", date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_DEFLATED; zi.external_attr = 0o600 << 16
            with z.open(zi, "w", force_zip64=True) as f:
                npf.write_array(f, np.asanyarray(arrays[k]), allow_pickle=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tf", required=True, help="TemplateFlow root holding fsaverage/ and MNI152NLin2009cAsym/")
    ap.add_argument("--den", choices=["10k", "41k"], default="41k")
    ap.add_argument("--out", required=True, help="scratch output dir for meshes_<den>.npz and mesh_report_<den>.json")
    ap.add_argument("--data", help="repository data dir: writes regions.json there")
    ap.add_argument("--facts", help="data/facts.json ({facts, by_fact_key}) or a plain list of {name,accent,...}; used for accent / has_fact")
    ap.add_argument("--bake", help="dir holding bake_in_<den>.npz and bake_out_<den>.npz (Cycles per-vertex AO)")
    a = ap.parse_args()
    t0 = time.time(); TF = Path(a.tf); OUT = Path(a.out); OUT.mkdir(parents=True, exist_ok=True)
    den = a.den

    # ---------------------------------------------------------------- cortex (pial) in scene coordinates
    H = {}
    for h in "LR":
        g = nib.load(TF / f"fsaverage/tpl-fsaverage_hemi-{h}_den-{den}_pial.surf.gii")
        v, f = g.agg_data("pointset").astype(np.float64), g.agg_data("triangle").astype(np.int64)
        sulc = nib.load(TF / f"fsaverage/tpl-fsaverage_hemi-{h}_den-{den}_sulc.shape.gii").agg_data().astype(np.float32)
        curv = nib.load(TF / f"fsaverage/tpl-fsaverage_hemi-{h}_den-{den}_curv.shape.gii").agg_data().astype(np.float32)
        lab = nib.load(TF / f"fsaverage/tpl-fsaverage_hemi-{h}_den-{den}_atlas-Desikan2006_seg-aparc_dseg.label.gii")
        names = {k.key: k.label for k in lab.labeltable.labels}
        H[h] = dict(ras=v, f=f, sulc=sulc, curv=curv, lab=lab.darrays[0].data.astype(np.int16), names=names)
    sc = {h: to_scene(H[h]["ras"]) for h in "LR"}
    allv = np.concatenate([sc["L"], sc["R"]])
    C = (allv.max(0) + allv.min(0)) / 2                       # scene centre = pial bbox centre (matches the AO bake input)
    for h in "LR":
        sc[h] = sc[h] - C
    pial_lo_ras = np.minimum(H["L"]["ras"].min(0), H["R"]["ras"].min(0)); pial_hi_ras = np.maximum(H["L"]["ras"].max(0), H["R"]["ras"].max(0))

    # ---------------------------------------------------------------- alignment fit MNI2009c(aseg) -> fsaverage (per-axis scale + shift)
    aseg_p = TF / "MNI152NLin2009cAsym/tpl-MNI152NLin2009cAsym_res-01_seg-aseg_dseg.nii.gz"
    img = nib.load(aseg_p); d = np.asarray(img.dataobj).astype(np.int16)
    ctx = np.argwhere((d == 3) | (d == 42)); w = nib.affines.apply_affine(img.affine, ctx); a_lo, a_hi = w.min(0), w.max(0)
    s_ax = (pial_hi_ras - pial_lo_ras) / (a_hi - a_lo); t_ax = pial_lo_ras - s_ax * a_lo
    align = dict(kind="per-axis scale+shift, aseg cerebral-cortex bbox -> fsaverage pial bbox (RAS mm)", pial_bbox_ras=[pial_lo_ras.tolist(), pial_hi_ras.tolist()],
                 aseg_cortex_bbox_ras=[a_lo.tolist(), a_hi.tolist()], scale=s_ax.tolist(), shift=t_ax.tolist(), scene_centre_C=C.tolist(),
                 note="LOOK-LEVEL fit, not a registration; applies to the deep meshes and the T1 slices (scale 3-5 percent off unity); the cortex is not scaled (1.000); grade Suspected")

    # ---------------------------------------------------------------- deep structures: marching cubes on the aseg, smooth, fit, to scene coords
    sub = {}; srep = {}
    for nme, (labs, sg) in STRUCT.items():
        m = gaussian_filter(np.isin(d, labs).astype(np.float32), sg)
        step = STEPS[den][nme]
        vv, ff, _, _ = marching_cubes(m, 0.5, step_size=step)
        vv = nib.affines.apply_affine(img.affine, vv)
        ff = ff.astype(np.int64)
        vv = taubin(vv, ff)
        ras = vv * s_ax + t_ax
        vs = to_scene(ras) - C
        ff = outward(vs, ff)
        sub[nme] = (vs.astype(np.float32), ff.astype(np.int32))
        left = vs[:, 0] < 0
        srep[nme] = dict(labels=labs, step=step, sigma=sg, verts=len(vs), tris=len(ff), centroid=vs.mean(0).round(2).tolist(),
                         centroid_L=vs[left].mean(0).round(2).tolist() if left.any() else None, centroid_R=vs[~left].mean(0).round(2).tolist() if (~left).any() else None)

    # ---------------------------------------------------------------- optional AO bake: use only if it matches this mesh vertex for vertex
    ao = None; ao_rep = dict(source="none")
    if a.bake:
        bi, bo = Path(a.bake) / f"bake_in_{den}.npz", Path(a.bake) / f"bake_out_{den}.npz"
        if bi.exists() and bo.exists():
            bin_ = np.load(bi); bout = np.load(bo)
            mine = np.concatenate([sc["L"], sc["R"]]); myf = np.concatenate([H["L"]["f"], H["R"]["f"] + len(sc["L"])])
            err = float(np.abs(bin_["v"] - mine).max()); same_f = bool(np.array_equal(bin_["f"], myf))
            ao_rep = dict(source="blender cycles AO bake (bpy %s)" % str(bout["bpy_version"]), max_vertex_error_mm=round(err, 5), faces_identical=same_f,
                          n=int(len(bout["ao"])), mean=round(float(bout["ao"].mean()), 4), p5=round(float(np.percentile(bout["ao"], 5)), 4),
                          p95=round(float(np.percentile(bout["ao"], 95)), 4), sha256_bake_out=sha(bo), sha256_bake_in=sha(bi))
            if err < 1e-3 and same_f and len(bout["ao"]) == len(mine):
                ao = bout["ao"].astype(np.float32); ao_rep["matches_mesh"] = True
            else:
                ao_rep["matches_mesh"] = False; ao_rep["source"] = "bake present but does NOT match this mesh; not used"

    # ---------------------------------------------------------------- npz
    pack = {}
    for h in "LR":
        pack[f"v{h}"] = sc[h].astype(np.float32); pack[f"f{h}"] = H[h]["f"].astype(np.int32)
        pack[f"sulc{h}"] = H[h]["sulc"]; pack[f"curv{h}"] = H[h]["curv"]; pack[f"lab{h}"] = H[h]["lab"]
    for k, (vv, ff) in sub.items():
        pack[f"sv_{k}"] = vv; pack[f"sf_{k}"] = ff
    pack["C"] = C.astype(np.float64); pack["align_scale"] = s_ax; pack["align_shift"] = t_ax
    if ao is not None:
        pack["ao"] = ao
    npz = OUT / f"meshes_{den}.npz"
    save_npz(npz, pack)

    # ---------------------------------------------------------------- regions (Desikan x 2 hemispheres + 10 deep structures)
    facts = {}
    if a.facts:
        raw = json.load(open(a.facts))
        if isinstance(raw, dict) and "facts" in raw:                       # data/facts.json: facts[key] + by_fact_key[region fact_key] -> key
            for fk, k in raw["by_fact_key"].items():
                facts[fk] = raw["facts"][k]
        else:                                                              # legacy draft: a list of {name, accent, ...}
            for e in raw:
                facts[slug(e["name"])] = e
    regions = []; cent_report = {}
    for h in "LR":
        hn = H[h]["names"]
        for key, nm in sorted(hn.items()):
            if nm not in DESIKAN:
                continue                                       # unknown (0) and corpuscallosum (4) = medial wall, not regions
            disp, lobe = DESIKAN[nm]
            m = H[h]["lab"] == key
            if not m.any():
                continue
            vv = sc[h][m]; cen = vv.mean(0)
            nn = vertex_normals(sc[h], H[h]["f"])[m]
            near = np.argmin(((vv - cen) ** 2).sum(1)); anchor = vv[near]                    # a real surface vertex nearest the centroid
            fname = FACTS_ALIAS.get(nm, disp)
            fkey = slug(fname) if fname else slug(disp)
            hit = fkey in facts or (nm in FACTS_ALIAS and FACTS_ALIAS[nm] and slug(FACTS_ALIAS[nm]) in facts)
            e = facts.get(fkey)
            regions.append(dict(id=f"ctx-{h.lower()}h-{nm}", name=disp.capitalize() if disp[0].islower() else disp, desikan_label=nm, desikan_index=int(key), hemi=h,
                                centroid=[round(float(x), 1) for x in cen], anchor=[round(float(x), 1) for x in anchor], anchor_normal=[round(float(x), 2) for x in nn[near]],
                                lobe=lobe, accent=(e or {}).get("accent", LOBE_ACCENT[lobe]), fact_key=fkey, has_fact=bool(e), vertices=int(m.sum())))
            cent_report[f"{h}:{key}:{nm}"] = [round(float(x), 2) for x in cen]
    for nme, r in srep.items():
        fname = FACTS_NAME[nme]; fkey = slug(fname) if fname else nme
        e = facts.get(fkey)
        regions.append(dict(id=f"deep-{nme}", name=STRUCT_NAME[nme], desikan_label=None, aseg_labels=r["labels"], hemi="B", centroid=r["centroid"],
                            centroid_L=r["centroid_L"], centroid_R=r["centroid_R"], lobe=STRUCT_LOBE[nme], accent=(e or {}).get("accent", LOBE_ACCENT["deep"]),
                            fact_key=fkey, has_fact=bool(e), shape=f"STRUCT_{nme}"))
    rep = dict(tool="prep_meshes.py", density=den, seconds=round(time.time() - t0, 1), numpy=np.__version__, nibabel=nib.__version__,
               cortex=dict(verts_per_hemi=int(len(sc["L"])), tris_per_hemi=int(len(H["L"]["f"])), medial_wall_vertices=dict((h, int(np.isin(H[h]["lab"], [0, 4]).sum())) for h in "LR")),
               align=align, struct=srep, ao=ao_rep, regions=len(regions), regions_without_fact=[r["id"] for r in regions if not r["has_fact"]],
               inputs={k: sha(p) for k, p in dict(aseg=aseg_p, **{f"pial_{h}": TF / f"fsaverage/tpl-fsaverage_hemi-{h}_den-{den}_pial.surf.gii" for h in "LR"}).items()},
               desikan_centroids=cent_report, npz=dict(file=npz.name, bytes=npz.stat().st_size, sha256=sha(npz)),
               notice="Derived geometry. Cortex: the fsaverage template's own %s pial vertex set (not decimated by us), moved rigidly; FreeSurfer lineage, licence grade Suspected. Deep meshes and slices: MNI152NLin2009cAsym (Fonov 2009/2011), permissive MNI licence text, copyright notice retained, scaled and shifted into the cortex frame." % den)
    json.dump(rep, open(OUT / f"mesh_report_{den}.json", "w"), indent=1)
    if a.data:
        Path(a.data).mkdir(parents=True, exist_ok=True)
        rp = Path(a.data) / "regions.json"
        json.dump(regions, open(rp, "w"), indent=1)
        print("regions.json", len(regions), "entries", sha(rp)[:16], rp)
    print(f"den={den} cortex tris/hemi={len(H['L']['f'])} deep tris={sum(r['tris'] for r in srep.values())} AO={ao_rep.get('source')} (match={ao_rep.get('matches_mesh')}) "
          f"npz={npz.stat().st_size // 1024} KB sha256={sha(npz)[:16]} {rep['seconds']} s")
    print("align scale", np.round(s_ax, 4).tolist(), "shift", np.round(t_ax, 2).tolist(), "C", C.round(2).tolist())
    print({k: (v["verts"], v["tris"]) for k, v in srep.items()})


if __name__ == "__main__":
    main()
