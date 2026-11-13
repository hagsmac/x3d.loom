#!/usr/bin/env python3
"""x3d.mol diffusion film: renders the AlphaFold 3 diffusion illustration in Cycles, driven by the validated X3D keyframes.

  python -I -W ignore blender/diffcine.py --out cinema [--targets AF-P04637-F1,1aay] [--fps 24] [--samples 24] [--width 960] [--height 540]
                                          [--frames 0-287] [--encode-only]

The atoms come from scenes/anim/<id>.anim.x3d (src/anim.py): the TimeSensor, CoordinateInterpolator and Coordinate are read
from the file, the keys are interpolated linearly as CoordinateInterpolator is defined to, and each frame's positions are
the file's at fraction frame / (fps * cycleInterval). No position is computed here that the file does not hold. The cartoon
that fades in during the hold is the molecularnodes cartoon of the same source file (blender/molcine.py recipe).
Look, not data: point sizes, the grey-blue of unsettled atoms, the colour fade, the lights, depth of field, the camera pull-back.

Writes cinema/<id>-diffusion.mp4 (H.264), cinema/<id>-diffusion-poster.jpg and cinema/diffusion.json, which names the
X3D sha256 it consumed, every tool version, the render settings, and per frame: the fraction, the AlphaFold 3 step and the
rms distance of the drawn atoms from the file's rest pose (0 at the end, by construction and by check).
It is an illustration of how AlphaFold 3 works, not a live run; the film and its receipt say so.
"""
import argparse, hashlib, json, math, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

import bpy
import mathutils
import numpy as np
import xml.etree.ElementTree as etree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import molcine as MC  # noqa: E402  (scene reset, molecule load, studio look)

SOURCES = {"AF-P04637-F1": ("afdb/AF-P04637-F1-model_v6.cif", "plddt"), "1aay": ("pdb/pdb1aay.ent.gz", "default")}
NOISE = (0.72, 0.84, 1.0)
RADIUS_A = [0.55, 0.65, 0.6, 1.25]  # backbone, side chain, nucleic, zinc (angstrom), as on the page
SCALE = 0.1                          # molecularnodes: 1 Blender unit = 10 angstrom, uncentred


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read_anim(path: Path) -> dict:
    """The keyframes as an X3D browser would wire them: follow the ROUTEs from the TimeSensor to the Coordinate."""
    root = etree.parse(str(path)).getroot()
    f = lambda s: np.array((s or "").split(), dtype=np.float64)
    meta = {m.get("name"): m.get("value") for m in root.iter() if m.tag in ("MetadataString", "MetadataFloat", "MetadataInteger")}
    defs = {e.get("DEF"): e for e in root.iter() if e.get("DEF")}
    routes = [(r.get("fromNode"), r.get("fromField"), r.get("toNode"), r.get("toField")) for r in root.iter("ROUTE")]
    r1 = next(r for r in routes if defs.get(r[0]) is not None and defs[r[0]].tag == "TimeSensor" and r[1] == "fraction_changed" and r[3] == "set_fraction")
    interp = defs[r1[2]]
    r2 = next(r for r in routes if r[0] == r1[2] and r[1] == "value_changed" and r[3] == "set_point")
    coord = defs[r2[2]]
    assert interp.tag == "CoordinateInterpolator" and coord.tag == "Coordinate"
    key, kv, rest = f(interp.get("key")), f(interp.get("keyValue")), f(coord.get("point")).reshape(-1, 3)
    n = len(rest)
    return {"key": key, "frames": kv.reshape(len(key), n, 3), "rest": rest, "n": n, "color": f(next(ps.find("Color") for ps in root.iter("PointSet") if coord in list(ps)).get("color")).reshape(-1, 3),
            "cycle": float(defs[r1[0]].get("cycleInterval")), "cls": f(meta["atom_class"]).astype(int), "step": f(meta["step"]).astype(int),
            "denoise": float(f(meta["denoise_fraction"])[0]), "disclaimer": meta["disclaimer"].strip('"')}


def at(anim: dict, frac: float) -> np.ndarray:
    k = anim["key"]
    if frac <= k[0]:
        return anim["frames"][0].copy()
    if frac >= k[-1]:
        return anim["frames"][-1].copy()
    i = int(np.searchsorted(k, frac, side="right")) - 1
    u = (frac - k[i]) / (k[i + 1] - k[i])
    return anim["frames"][i] + (anim["frames"][i + 1] - anim["frames"][i]) * u


def atoms_object(n: int):
    """A mesh of n vertices turned into Cycles points by geometry nodes; radius and colour are per-vertex attributes."""
    me = bpy.data.meshes.new("diffusion_atoms")
    me.vertices.add(n)
    me.attributes.new("radius", "FLOAT", "POINT")
    me.attributes.new("col", "FLOAT_COLOR", "POINT")
    ob = bpy.data.objects.new("diffusion_atoms", me)
    bpy.context.scene.collection.objects.link(ob)
    mat = bpy.data.materials.new("diffusion_atom")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    attr = nt.nodes.new("ShaderNodeAttribute"); attr.attribute_name = "col"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.35
    try:
        bsdf.inputs["Coat Weight"].default_value = 0.3
    except Exception:
        pass
    g = bpy.data.node_groups.new("atoms_to_points", "GeometryNodeTree")
    g.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    g.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi, go = g.nodes.new("NodeGroupInput"), g.nodes.new("NodeGroupOutput")
    m2p = g.nodes.new("GeometryNodeMeshToPoints")
    rad = g.nodes.new("GeometryNodeInputNamedAttribute"); rad.data_type = "FLOAT"; rad.inputs["Name"].default_value = "radius"
    sm = g.nodes.new("GeometryNodeSetMaterial"); sm.inputs["Material"].default_value = mat
    g.links.new(gi.outputs[0], m2p.inputs["Mesh"])
    g.links.new(rad.outputs["Attribute"], m2p.inputs["Radius"])
    g.links.new(m2p.outputs["Points"], sm.inputs["Geometry"])
    g.links.new(sm.outputs["Geometry"], go.inputs[0])
    mod = ob.modifiers.new("points", "NODES"); mod.node_group = g
    return ob


def fadeable(obj):
    """Insert a Transparent mix before every material output of the cartoon; returns the Value nodes that drive opacity."""
    knobs = []
    for slot in obj.material_slots:
        m = slot.material
        if m is None or not m.use_nodes:
            continue
        nt = m.node_tree
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
        if out is None or not out.inputs["Surface"].links:
            continue
        src = out.inputs["Surface"].links[0].from_socket
        mix, tr, val = nt.nodes.new("ShaderNodeMixShader"), nt.nodes.new("ShaderNodeBsdfTransparent"), nt.nodes.new("ShaderNodeValue")
        nt.links.new(val.outputs[0], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(src, mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs["Surface"])
        knobs.append(val)
    return knobs


def lin(c):
    return np.clip(c, 0, 1) ** 2.2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "cinema"))
    ap.add_argument("--targets", default="AF-P04637-F1,1aay")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--frames", default="")
    ap.add_argument("--work", default=str(ROOT / "runs/diffcine"))
    ap.add_argument("--encode-only", action="store_true")
    a = ap.parse_args()
    out, work = Path(a.out), Path(a.work)
    out.mkdir(parents=True, exist_ok=True)
    import importlib.metadata as md
    rpath = out / "diffusion.json"
    receipt = json.loads(rpath.read_text()) if rpath.exists() else {}
    receipt.update({"schema": "x3d.mol.diffusion-film/1", "unsigned": True, "illustration": True,
                    "tools": {"blender": bpy.app.version_string, "bpy": md.version("bpy"), "molecularnodes": md.version("molecularnodes"), "python": sys.version.split()[0],
                              "ffmpeg": subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.split("\n")[0][:60]},
                    "script_sha256": sha256(Path(__file__)), "units": "1 Blender unit = 10 angstrom (source x 0.1, uncentred)",
                    "render": {"engine": "Cycles", "device": "CPU", "samples": a.samples, "seed": 7, "size": [a.width, a.height], "fps": a.fps}})
    receipt.setdefault("scenes", {})
    tmp = Path(tempfile.mkdtemp())
    for tid in a.targets.split(","):
        x3d = ROOT / "scenes/anim" / f"{tid}.anim.x3d"
        anim = read_anim(x3d)
        nfr = int(round(anim["cycle"] * a.fps))
        frames_dir = work / tid
        frames_dir.mkdir(parents=True, exist_ok=True)
        lo, hi = (int(x) for x in a.frames.split("-")) if a.frames else (0, nfr - 1)
        entry = receipt["scenes"].get(tid, {})
        log = {int(k): v for k, v in entry.get("frames_log", {}).items()}
        if not a.encode_only:
            rel, scheme = SOURCES[tid]
            MC.clean_scene()
            mol, src, notes = MC.load_molecule(rel, scheme, tmp)
            info = MC.look_setup(mol.object, a.width, a.height, a.samples, core_min=70 if scheme == "plddt" else None, fit=1.1 if scheme == "plddt" else 0.9)
            sc = bpy.context.scene
            sc.cycles.use_adaptive_sampling = True
            # realise the cartoon once as a plain mesh (keeps its materials): the geometry nodes are not re-evaluated every frame
            bpy.ops.object.select_all(action="DESELECT"); mol.object.select_set(True); bpy.context.view_layer.objects.active = mol.object
            bpy.ops.object.convert(target="MESH")
            knobs = fadeable(mol.object)
            ob = atoms_object(anim["n"])
            me = ob.data
            cam = sc.camera
            focus = cam.constraints[0].target
            target = focus.location.copy()
            home = cam.location.copy()
            rest = anim["rest"]
            ctr = rest.mean(0)
            far0 = np.sort(np.linalg.norm(anim["frames"][0] - ctr, axis=1))[int(anim["n"] * 0.85)] * SCALE
            near = info["radius_bu"]
            fl, nz = lin(anim["color"]), lin(np.array(NOISE))
            for fi in range(lo, hi + 1):
                frac = fi / nfr
                pos = at(anim, frac)
                d = np.linalg.norm(pos - anim["frames"][-1], axis=1)
                s = np.clip(1 - d / 3.5, 0, 1); e = s * s * (3 - 2 * s)
                h = 0.0 if frac <= anim["denoise"] else min(1.0, (frac - anim["denoise"]) / ((1 - anim["denoise"]) * 0.5))
                shrink = 1 - 0.45 * h
                r = np.array(RADIUS_A)[anim["cls"]] * np.where(anim["cls"] == 3, 1.0, shrink) * (1.6 - 0.6 * e) * SCALE
                col = nz[None] + (fl - nz[None]) * e[:, None]
                me.vertices.foreach_set("co", (pos * SCALE).astype(np.float32).ravel())
                me.attributes["radius"].data.foreach_set("value", r.astype(np.float32))
                me.attributes["col"].data.foreach_set("color", np.concatenate([col, np.ones((len(col), 1))], 1).astype(np.float32).ravel())
                me.update()
                for k in knobs:
                    k.outputs[0].default_value = h
                mol.object.hide_render = h <= 0
                # camera pulls back to hold the cloud, then returns (look): distance follows the drawn noise
                spread = float(np.sort(np.linalg.norm(pos - ctr, axis=1))[int(anim["n"] * 0.85)]) * SCALE
                kz = max(1.0, spread / max(near, 1e-6)) ** 0.85
                kz = min(kz, far0 / max(near, 1e-6))
                w = (kz - 1) / max(far0 / max(near, 1e-6) - 1, 1e-6)          # 1 in the full cloud, 0 at the answer
                aim = target + (mathutils.Vector((ctr * SCALE).tolist()) - target) * w
                focus.location = aim
                cam.location = aim + (home - target) * kz
                sc.render.filepath = str(frames_dir / f"f{fi:04d}.png")
                t1 = time.time()
                bpy.ops.render.render(write_still=True)
                rms = float(np.sqrt(((pos - rest) ** 2).sum(1).mean()))
                ki = int(np.searchsorted(anim["key"], frac, side="right")) - 1
                log[fi] = {"fraction": round(frac, 5), "step": int(anim["step"][min(ki, len(anim["step"]) - 1)]) if frac < anim["denoise"] else int(anim["step"][-1]),
                           "rms_from_rest_A": round(rms, 4), "cartoon": round(h, 3)}
                print(tid, fi, "/", nfr, "rms", round(rms, 2), "render", round(time.time() - t1, 1), "s", flush=True)  # operator only; no timing is kept
            entry.update({"anim_x3d": f"scenes/anim/{x3d.name}", "anim_sha256": sha256(x3d), "source": rel, "source_sha256": sha256(src), "frames": nfr,
                          "cycle_seconds": anim["cycle"], "atoms": anim["n"], "notes": notes, "camera": info["camera"], "view_transform": info["view_transform"], "denoise": info["denoise"]})
        entry["frames_log"] = {str(k): log[k] for k in sorted(log)}
        receipt["scenes"][tid] = entry
        rpath.write_text(json.dumps(receipt, indent=1))
        have = sorted(int(p.stem[1:]) for p in frames_dir.glob("f*.png"))
        if have == list(range(nfr)):
            mp4 = out / f"{tid}-diffusion.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(a.fps), "-i", str(frames_dir / "f%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            "-crf", "21", "-preset", "slow", "-movflags", "+faststart", "-metadata", "comment=" + anim["disclaimer"], str(mp4)], check=True)
            from PIL import Image
            poster = out / f"{tid}-diffusion-poster.jpg"
            Image.open(frames_dir / f"f{int(nfr * 0.55):04d}.png").convert("RGB").save(poster, quality=86, optimize=True, progressive=True)
            ends = entry["frames_log"].get(str(nfr - 1), {})
            entry.update({"mp4": {"file": mp4.name, "sha256": sha256(mp4), "bytes": mp4.stat().st_size}, "poster": {"file": poster.name, "sha256": sha256(poster)},
                          "check": {"last_frame_rms_from_rest_A": ends.get("rms_from_rest_A"), "first_frame_rms_A": entry["frames_log"]["0"]["rms_from_rest_A"],
                                    "all_frames_rendered": True}})
            receipt["scenes"][tid] = entry
            rpath.write_text(json.dumps(receipt, indent=1))
            print(tid, "encoded", mp4.name, mp4.stat().st_size // 1024, "KB", flush=True)
        else:
            print(tid, f"{len(have)} of {nfr} frames rendered; encode waits for all", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
