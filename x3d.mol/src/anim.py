#!/usr/bin/env python3 -I
"""Diffusion illustration: how AlphaFold 3 builds a structure, drawn as validated X3D keyframes.

  python3 -I src/anim.py --out scenes/anim            # writes <id>.anim.x3d for 1aay and AF-P04637-F1

WHAT THIS IS. AlphaFold 3 places atoms with a diffusion model: it starts from atoms scattered as random noise and removes
the noise step by step, following a fixed noise schedule, until a structure is left (Abramson et al., Nature 2024). This
script draws that idea. It takes the noise schedule written in the AlphaFold 3 paper (EDM form, sigma_data 16, s_max 160,
s_min 4e-4, rho 7) and runs it backwards onto atoms whose final places are already known, from the deposited crystal
structure 1AAY or the AlphaFold DB model of p53. It is an ILLUSTRATION, NOT A LIVE RUN: no network predicts anything here,
the intermediate frames are the final atoms plus scheduled noise, and every scene says so in its metadata.

WHAT IS EXACT. The last two keyframes and the rest pose are the source atoms to 0.001 angstrom (noisy keys keep 0.01), the noise level at each key follows the written
schedule, capped for the screen with cap * tanh(sigma / cap) (true angstroms below the cap), the random numbers come from a
fixed seed, and the file is byte-identical on every run. src/anim_witness.py checks all of this with its own parser.

TIME. Keys are equally spaced in schedule time t (each is labelled with the AlphaFold 3 step, of 200, it stands for), but
keys whose noise is still at the cap get 0.35 of the screen time, because nothing changes there except the jitter.

MOTION. Each atom's noise is an AR(1) walk across keys (phi 0.85), so atoms drift instead of flickering. In an AlphaFold
model, atoms with low pLDDT get an extra restless term, L * (1 - pLDDT/100) * (1 - u)^1.5, that still reaches zero at the
last key, so the confident core settles first and the loose tails last. The X3D stores the final colours; the page fades
them in as atoms settle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from xmol import structure as S  # noqa: E402
from xmol import x3dwrite as W  # noqa: E402
import build as B  # noqa: E402

SCHEDULE = {"sigma_data": 16.0, "s_max": 160.0, "s_min": 4e-4, "rho": 7.0}
KEYS = 40           # denoising keys, spread over the first DENOISE of the loop
DENOISE = 0.8       # fraction of the loop spent denoising; the rest holds the answer
CYCLE = 12.0        # seconds per loop
PHI = 0.85          # AR(1) correlation of each atom's noise between keys
LAG = 8.0           # angstrom: extra restless noise at pLDDT 0, AlphaFold models only
LAG_PHI = 0.55
SEED = 20261113
SATURATED, SATURATED_WEIGHT = 0.98, 0.35
STEPS = 200         # AlphaFold 3 samples with 200 denoising steps; each key is labelled with the step it stands for
ND = 2              # keyframe decimals (0.01 angstrom)
DISCLAIMER = ("Illustration of how AlphaFold 3 works, not a live run: the noise schedule from the AlphaFold 3 paper is run "
              "backwards onto the known final atoms. Noise above the cap is drawn at the cap so it fits the screen.")
TARGETS = [("1aay", "pdb"), ("AF-P04637-F1", "afdb")]
ATOM_CLASS = {"backbone": 0, "sidechain": 1, "nucleic": 2, "zinc": 3}


def sigma(t: np.ndarray, p: dict = SCHEDULE) -> np.ndarray:
    """AlphaFold 3 noise schedule in angstrom: sigma_data * (s_max^(1/rho) + t (s_min^(1/rho) - s_max^(1/rho)))^rho, t in [0, 1]."""
    r = p["rho"]
    return p["sigma_data"] * (p["s_max"] ** (1 / r) + t * (p["s_min"] ** (1 / r) - p["s_max"] ** (1 / r))) ** r


def shown(s: np.ndarray, cap: float) -> np.ndarray:
    return cap * np.tanh(s / cap)


def atoms_of(st: S.Structure, kind: str):
    """Heavy atoms in residue order, then zinc. Returns xyz, colours, class, residue index, pLDDT (or None)."""
    xyz, rgb, cls, rix, conf = [], [], [], [], []
    for r in st.residues:
        for name, el, p in r.atoms:
            xyz.append(p)
            if kind == "afdb":
                rgb.append(B.plddt_rgb(r.b))
            else:
                rgb.append(B.ELEMENT_RGB.get(el.upper(), (0.8, 0.8, 0.8)))
            cls.append(ATOM_CLASS["nucleic"] if r.kind != "protein" else ATOM_CLASS["backbone"] if name in ("N", "CA", "C", "O", "OXT") else ATOM_CLASS["sidechain"])
            rix.append(r.index)
            conf.append(r.b)
    for m in st.metals:
        xyz.append(m.xyz)
        rgb.append(B.ELEMENT_RGB["ZN"])
        cls.append(ATOM_CLASS["zinc"])
        rix.append(-1)
        conf.append(100.0)
    return (np.array(xyz, dtype=np.float64), np.array(rgb, dtype=np.float64), np.array(cls, dtype=np.int64), np.array(rix, dtype=np.int64),
            np.array(conf, dtype=np.float64) if kind == "afdb" else None)


def frames(x0: np.ndarray, plddt: np.ndarray | None, seed: int):
    """Keyframes: x0 + shown(sigma(t_k)) * eps_k (+ lag term), last key exactly x0, then a held copy at fraction 1."""
    n = len(x0)
    rng = np.random.default_rng(seed)
    rg = float(np.sqrt(((x0 - x0.mean(0)) ** 2).sum(1).mean()))
    cap = round(max(12.0, 1.2 * rg), 2)
    u = np.linspace(0.0, 1.0, KEYS)
    sig = sigma(u)
    vis = shown(sig, cap)
    vis[-1] = 0.0                                   # AlphaFold 3 returns the denoised estimate at the last step
    eps = rng.standard_normal((n, 3))
    lag = rng.standard_normal((n, 3))
    weight = LAG * (1.0 - np.clip(plddt, 0, 100) / 100.0) if plddt is not None else np.zeros(n)
    out = []
    for k in range(KEYS):
        if k:
            eps = PHI * eps + np.sqrt(1 - PHI ** 2) * rng.standard_normal((n, 3))
            lag = LAG_PHI * lag + np.sqrt(1 - LAG_PHI ** 2) * rng.standard_normal((n, 3))
        x = x0 + vis[k] * eps + (weight * (1.0 - u[k]) ** 1.5)[:, None] * lag
        out.append(x)
    out[-1] = x0.copy()
    out.append(x0.copy())
    w = np.where(vis >= SATURATED * cap, SATURATED_WEIGHT, 1.0)  # keys still at the cap pass quickly: little changes there
    c = np.concatenate([[0.0], np.cumsum(w[1:])])
    keys = np.append(DENOISE * c / c[-1], 1.0)
    return keys, u, out, sig, vis, cap, rg


def build_anim(st: S.Structure, ident: str, kind: str, title: str, src_meta: dict, builder_sha: str) -> tuple[str, dict]:
    x0, rgb, cls, rix, plddt = atoms_of(st, kind)
    keys, u, kf, sig, vis, cap, rg = frames(x0, plddt, SEED)
    rms = [float(np.sqrt(((k - x0) ** 2).sum(1).mean())) for k in kf]
    meta = [W.mstr("kind", ["diffusion-illustration"]), W.mstr("disclaimer", [DISCLAIMER]),
            W.mstr("method", ["AlphaFold 3 diffusion noise schedule (Abramson et al., Nature 2024), run backwards onto known atoms"]),
            W.mstr("source_file", [st.source_file]), W.mstr("source_sha256", [st.source_sha256]), W.mstr("source_kind", [kind]),
            W.mstr("scene", [f"scenes/{ident}.x3d"]), W.mstr("licence", [B.LICENCE[kind]]), W.mstr("builder_sha256", [builder_sha]),
            W.mflt("schedule", [SCHEDULE["sigma_data"], SCHEDULE["s_max"], SCHEDULE["s_min"], SCHEDULE["rho"]], 6),
            W.mflt("schedule_t", u, 6), W.mint("step", np.round(u * STEPS).astype(int)), W.mint("steps", [STEPS]),
            W.mflt("sigma", sig, 4), W.mflt("sigma_shown", vis, 3), W.mflt("cap", [cap], 2), W.mflt("radius_of_gyration", [rg], 2),
            W.mflt("rms_from_final", rms, 2), W.mflt("lag", [LAG if plddt is not None else 0.0, LAG_PHI], 2),
            W.mflt("phi", [PHI], 2), W.mint("seed", [SEED]), W.mflt("cycle_seconds", [CYCLE], 1), W.mflt("denoise_fraction", [DENOISE], 2),
            W.mint("atom_class", cls), W.mint("residue_index", rix), W.mstr("atom_class_names", list(ATOM_CLASS))]
    meta += [W.mstr(k, [str(v)]) for k, v in src_meta.items()]
    if plddt is not None:
        meta.append(W.mflt("plddt", plddt, 2))
    ctr = x0.mean(0)
    rad = float(np.max(np.linalg.norm(x0 - ctr, axis=1)))
    head = ("<?xml version='1.0' encoding='UTF-8'?>\n"
            "<X3D profile='Interchange' version='4.0' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' "
            "xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.0.xsd'>\n"
            f"<head><meta name='title' content='{W.esc(ident)}.anim.x3d'/><meta name='description' content='{W.esc(DISCLAIMER)}'/>"
            f"<meta name='license' content='{W.esc(B.LICENCE[kind])}'/><meta name='generator' content='x3d.mol src/anim.py'/></head>\n")
    body = ["<Scene>",
            f"<WorldInfo title='{W.esc(title)}'><MetadataSet containerField='metadata' name='xmol_anim' reference='x3d.mol/anim/1'>{''.join(meta)}</MetadataSet></WorldInfo>",
            "<NavigationInfo type='\"EXAMINE\" \"ANY\"'/>", "<Background skyColor='0.02 0.03 0.05'/>",
            f"<Viewpoint description='Overview' position='{W.nums(ctr + np.array([0, 0, (rad + cap) * 2.4]))}' centerOfRotation='{W.nums(ctr)}' fieldOfView='0.7'/>",
            f"<Shape DEF='Atoms_{W.esc(ident.replace("-", "_"))}'><Appearance><Material emissiveColor='1 1 1' diffuseColor='0 0 0'/></Appearance>"
            f"<PointSet><Color color='{W.nums(rgb, 4)}'/><Coordinate DEF='AtomPoints' point='{W.nums(x0, 3)}'/></PointSet></Shape>",
            f"<TimeSensor DEF='Clock' cycleInterval='{W.num(CYCLE, 1)}' loop='true'/>",
            f"<CoordinateInterpolator DEF='Diffusion' key='{W.nums(keys, 4)}' keyValue='{' '.join(W.nums(k, 3 if i >= len(kf) - 2 else ND) for i, k in enumerate(kf))}'/>",
            "<ROUTE fromNode='Clock' fromField='fraction_changed' toNode='Diffusion' toField='set_fraction'/>",
            "<ROUTE fromNode='Diffusion' fromField='value_changed' toNode='AtomPoints' toField='set_point'/>",
            "</Scene>", "</X3D>"]
    text = head + "\n".join(body) + "\n"
    info = {"atoms": int(len(x0)), "keys": int(len(keys)), "cap": cap, "rms_first": round(rms[0], 2), "rms_last": round(rms[-1], 3),
            "zinc": int((cls == 3).sum())}
    return text, info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    builder_sha = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(HERE.rglob("*.py")))).hexdigest()
    pins = B.load_pdb_pins()
    afpins = json.loads((ROOT / "data/afdb/PINS.json").read_text())
    index = []
    for ident, kind in TARGETS:
        if kind == "pdb":
            desc, method, sha, _ = pins[ident]
            f = ROOT / "data/pdb" / f"pdb{ident}.ent.gz"
            if hashlib.sha256(f.read_bytes()).hexdigest() != sha:
                sys.exit(f"{f.name}: sha256 differs from the pin")
            st = S.read(f, ident.upper(), confidence=False)
            title = f"{ident.upper()}: {desc}, diffusion illustration"
            extra = {"method_deposited": method}
        else:
            name = f"{ident}-model_v6.cif"
            p = afpins[name]
            f = ROOT / "data/afdb" / name
            if hashlib.sha256(f.read_bytes()).hexdigest() != p["sha256"]:
                sys.exit(f"{name}: sha256 differs from PINS.json")
            st = S.read(f, ident, confidence=True)
            title = f"{ident}: {p['description']} ({p['gene']}), diffusion illustration"
            extra = {"uniprot": p["uniprot"]}
        text, info = build_anim(st, ident, kind, title, extra, builder_sha)
        path = out / f"{ident}.anim.x3d"
        path.write_text(text, encoding="utf-8")
        index.append({"id": ident, "kind": kind, "title": title, "file": f"scenes/anim/{path.name}", "bytes": path.stat().st_size,
                      "sha256": hashlib.sha256(text.encode()).hexdigest(), "source": {"file": st.source_file, "sha256": st.source_sha256}, **info})
        print(f"{ident}: {info['atoms']} atoms, {info['keys']} keys, cap {info['cap']} A, rms {info['rms_first']} -> {info['rms_last']} A, {path.stat().st_size // 1024} KB")
    (out / "anim.json").write_text(json.dumps({"schema": "x3d.mol.anim/1", "builder_sha256": builder_sha, "disclaimer": DISCLAIMER, "scenes": index}, indent=1))


if __name__ == "__main__":
    main()
