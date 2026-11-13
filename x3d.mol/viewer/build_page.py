#!/usr/bin/env python3 -I
"""Assemble docs/ for GitHub Pages: one index.html (reader, body and app inlined; Babylon.js from the CDN with an integrity hash)
and docs/scenes/ with the gzip'd X3D files and the catalog, receipt and credits JSON.

  python3 -I viewer/build_page.py --scenes scenes --out docs [--local-babylon PATH]

--local-babylon points at a copy of babylonjs@9.32.0/babylon.js for offline proof runs; the shipped page never uses it.
"""
import argparse, gzip, hashlib, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BABYLON_VERSION = "9.32.0"
BABYLON_URL = f"https://cdn.jsdelivr.net/npm/babylonjs@{BABYLON_VERSION}/babylon.js"
BABYLON_SRI = "sha384-1XDybi1454WehNQaPHwhcTlpJ6oDdq/L4KKyDu7JiWPOBUzoBC0yEcuKDzHpdXyo"   # of babylonjs@9.32.0/babylon.js as the CDN serves it
ADAPTER = ROOT.parent / "x3d.webgpu/demo/src/shared/adapter.js"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenes", default=str(ROOT / "scenes")); ap.add_argument("--out", default=str(ROOT / "docs")); ap.add_argument("--local-babylon")
    a = ap.parse_args()
    out = Path(a.out); (out / "scenes").mkdir(parents=True, exist_ok=True)
    scenes = Path(a.scenes)
    for f in scenes.glob("*.x3d"):
        data = f.read_bytes()
        (out / "scenes" / (f.name + ".gz")).write_bytes(gzip.compress(data, 9, mtime=0))
    for name in ("catalog.json", "receipt.json"):
        if (scenes / name).exists():
            shutil.copy(scenes / name, out / "scenes" / name)
    anim = scenes / "anim"
    if (anim / "anim.json").exists():  # the diffusion illustrations (src/anim.py)
        (out / "scenes/anim").mkdir(parents=True, exist_ok=True)
        for f in anim.glob("*.anim.x3d"):
            (out / "scenes/anim" / (f.name + ".gz")).write_bytes(gzip.compress(f.read_bytes(), 9, mtime=0))
        shutil.copy(anim / "anim.json", out / "scenes/anim/anim.json")
    cinema = ROOT / "cinema"
    if (cinema / "receipt.json").exists():  # the Blender cut: JPEG stills, gzip'd X3D, the stage receipt and the gate result
        (out / "cinema").mkdir(exist_ok=True)
        for f in list(cinema.glob("*-hero.jpg")) + list(cinema.glob("*.mn.x3d.gz")) + [cinema / "receipt.json", cinema / "gate.json", cinema / "diffusion.json"] + \
                list(cinema.glob("*-diffusion.mp4")) + list(cinema.glob("*-diffusion-poster.jpg")):
            if f.exists():
                shutil.copy(f, out / "cinema" / f.name)
        if not (cinema / "diffusion.json").exists():  # no film rendered yet: an empty index, so the page fetch does not 404
            (out / "cinema/diffusion.json").write_text(json.dumps({"schema": "x3d.mol.diffusion-film/1", "scenes": {}}))
    credits = ROOT / "data/credits/lab-papers.json"
    if credits.exists():
        shutil.copy(credits, out / "scenes" / "credits.json")
    parts = [ADAPTER.read_text(encoding="utf-8")] + [(HERE / n).read_text(encoding="utf-8") for n in ("reader.js", "body.js", "diffuse.js", "app.js")]
    bundle = "\n".join(parts)
    tag = hashlib.sha256(bundle.encode()).hexdigest()[:12]
    if a.local_babylon:
        babylon = f'<script src="{Path(a.local_babylon).resolve().as_uri()}"></script>'
    else:
        babylon = f'<script src="{BABYLON_URL}" integrity="{BABYLON_SRI}" crossorigin="anonymous"></script>'
    scripts = f'{babylon}\n<script>window.__xmolBuild="{tag}";</script>\n<script>\n{bundle}\n</script>'
    html = (HERE / "template.html").read_text(encoding="utf-8").replace("<!--SCRIPTS-->", scripts)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"wrote {out/'index.html'} ({len(html)//1024} KB), build {tag}, {len(list((out/'scenes').glob('*.gz')))} scenes")


if __name__ == "__main__":
    main()
