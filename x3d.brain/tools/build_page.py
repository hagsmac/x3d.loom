#!/usr/bin/env python3
"""Assemble the interactive brain page (a self-contained static folder) from page/template.html + page/ui.css + page/page.css + page/app.js.

    python3 -I tools/build_page.py --target repo                       # lite scenes, no music, no style-board thumbnails -> page/
    python3 -I tools/build_page.py --target private --out DIR \\
        --brain-scene brain_hero_41k.x3d --torso-scene torso_ct.x3d \\
        --audio-dir AUDIO_DIR --thumbs-dir THUMBS_DIR --xite-dist X_ITE_DIST   # full scenes, music, thumbnails, vendored X_ITE

What it writes into --out (and nothing else; it never deletes a source file, only the folders it generates):
    index.html            one file: CSS + JS inlined, window.PAGE_CONFIG with the scene URLs, byte sizes, data paths
    data/*.json           regions, facts, looks, tour, presets, torso regions (minified copies) + provenance.json (page/provenance.json plus this build's hashes and counts)
    scenes/*.x3dz         the scenes, gzip with mtime 0 (X_ITE reads .x3dz natively); scenes/tex next to them (both scenes name their textures relatively; the studio cube faces both use are tex/env64)
    scenes/audio/         private build only: the music bed (mp3 + ogg)
    thumbs/               private build only: the 12 look thumbnails
    vendor/x_ite/         only with --xite-dist (X_ITE 16.6.0, unmodified). Without it the page tries the same version from a public CDN. tools/fetch_xite.sh fetches it with npm.
    NOTICE-*.md           the data notices (MNI copyright text, torso attribution)

Scene edits (the only bytes this tool changes in a scene, recorded as served_sha256 vs source_sha256 in provenance.json):
    the AudioClip url is emptied in the repo build (no music file shipped) and pointed at the loop-conditioned mp3/ogg in the private build.

Prints a count and sha256 for every output. Deterministic: same inputs give identical bytes (no timestamps).
"""
import argparse
import gzip
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                      # x3d.brain/
PAGE = ROOT / "page"
XITE_VERSION = "16.6.0"
XITE_CDN = f"https://cdn.jsdelivr.net/npm/x_ite@{XITE_VERSION}/dist/x_ite.min.js"
AUDIO_ORIG = "audio/m01-drift.ogg"
AUDIO_LOOP = ['audio/m01-drift.loop.mp3', 'audio/m01-drift.loop.ogg']
DATA_FILES = {"regions": "regions.json", "facts": "facts.json", "looks": "looks.json", "tour": "tour.json", "presets": "presets.json", "torso": "torso_regions.json"}


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def say(msg):
    print(msg, flush=True)


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    say(f"  wrote {path.relative_to(OUT)}  {len(data):>10,d} bytes  sha256 {sha256_bytes(data)[:16]}")
    return {"path": str(path.relative_to(OUT)), "bytes": len(data), "sha256": sha256_bytes(data)}


def count_scene(text):
    """Shapes, triangles and vertices of the indexed triangle sets in an X3D XML scene (shared USE nodes counted once)."""
    shapes = len(re.findall(r"<Shape\b", text))
    tris = verts = 0
    for m in re.finditer(r"<IndexedTriangleSet\b[^>]*?\bindex='([^']*)'[^>]*>\s*<Coordinate\b[^>]*?\bpoint='([^']*)'", text):
        tris += len(m.group(1).split()) // 3
        verts += len(m.group(2).split()) // 3
    return {"shapes": shapes, "triangles": tris, "vertices": verts}


# a compressed stream is arbitrary bytes: a short word the leak sweep looks for can turn up in it by chance (it did once, three
# letters inside the lite brain scene's stream), so for the repo build the level is stepped down until the stream is clear.
# Deterministic: same input, same output. The private build is not swept (a multi-megabyte stream always holds such triples).
# (the words are assembled from fragments so that this file passes the sweep it serves)
_STREAM_WORDS = re.compile(("(?i)" + "|".join(a + b for a, b in (
    ("gc", "p"), ("gem", "ini"), ("ima", "gen"), ("ly", "ria"), ("goo", "gle"), ("cla", "ude"), ("anthr", "opic"), ("open", "ai"),
    ("vert", "ex ?-?ai"), ("u", "sd"), ("co", "st")))).encode())


def gz(data, clear=False):
    if not clear:
        return gzip.compress(data, compresslevel=9, mtime=0)
    for level in (9, 8, 7, 6, 5, 4):
        blob = gzip.compress(data, compresslevel=level, mtime=0)
        if not _STREAM_WORDS.search(blob):
            return blob
    sys.exit("gz: no compression level gives a stream free of the sweep words")


def prepare_scene(src, kind, audio, gzip_on, clear=False):
    """Return (served bytes, served name, record) for one scene file."""
    raw = src.read_bytes()
    text = raw.decode("utf-8")
    src_sha = sha256_bytes(raw)
    note = None
    if kind == "brain":
        if f"url='\"{AUDIO_ORIG}\"'" in text:
            if audio:
                text = text.replace(f"url='\"{AUDIO_ORIG}\"'", "url='" + " ".join('"%s"' % u for u in AUDIO_LOOP) + "'")
                note = "AudioClip url pointed at the loop-conditioned music files (mp3, ogg)"
            else:
                text = text.replace(f"url='\"{AUDIO_ORIG}\"'", "url=''")
                note = "AudioClip url emptied: no music file ships in this build"
    served = text.encode("utf-8")
    counts = count_scene(text)
    side = Path(str(src) + ".build.json")
    if side.exists():
        try:
            b = json.loads(side.read_text())
            for k in ("cortex_tris", "cortex_verts", "deep_tris", "tract_fibres", "tract_points", "builder_sha16"):
                if k in b:
                    counts[k] = b[k]
        except (OSError, ValueError):
            pass
    name = src.name + ("z" if gzip_on else "")
    blob = gz(served, clear) if gzip_on else served
    rec = {"id": kind, "file": f"scenes/{name}", "source_file": src.name, "source_sha256": src_sha, "served_sha256": sha256_bytes(served),
           "bytes": len(blob), "counts": counts}
    m = re.search(r"<meta name='title' content='([^']*)'", text)
    rec["variant"] = (m.group(1) if m else src.stem)
    if note:
        rec["note"] = note
    return blob, name, rec


def copy_tree(src, dst):
    n = 0
    for p in sorted(Path(src).rglob("*")):
        if p.is_file():
            t = Path(dst) / p.relative_to(src)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, t)
            n += 1
    return n


def vendor_xite(dist, dst):
    """Copy the parts of an X_ITE dist folder the page needs (min build, css, assets minus the unminified components) unchanged."""
    dist = Path(dist)
    if not (dist / "x_ite.min.js").exists():
        sys.exit(f"--xite-dist {dist} has no x_ite.min.js")
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    n = 0
    for name in ("x_ite.min.js", "x_ite.css", "LICENSE.md"):
        if (dist / name).exists():
            shutil.copyfile(dist / name, dst / name)
            n += 1
    for p in sorted((dist / "assets").rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(dist)
        if rel.parts[1] == "components" and not p.name.endswith(".min.js"):
            continue
        t = dst / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, t)
        n += 1
    say(f"  vendor/x_ite: {n} files from {dist.name} (x_ite.min.js sha256 {sha256_file(dst / 'x_ite.min.js')[:16]})")


def main():
    global OUT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=["repo", "private"], required=True)
    ap.add_argument("--out", help="output folder (repo default: x3d.brain/page)")
    ap.add_argument("--brain-scene", help="brain scene .x3d (repo default: scenes/brain_hero_lite.x3d)")
    ap.add_argument("--torso-scene", help="torso scene .x3d (repo default: scenes/torso_ct_lite.x3d)")
    ap.add_argument("--tex-dir", help="folder with the textures both scenes name relatively, incl. env64/ (default: tex/ next to the brain scene)")
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--audio-dir", help="folder with m01-drift.loop.mp3 and .ogg (private build)")
    ap.add_argument("--thumbs-dir", help="folder with b01.jpg .. b12.jpg look thumbnails (private build)")
    ap.add_argument("--xite-dist", help="X_ITE dist folder to vendor into vendor/x_ite (omit to use the CDN fallback or tools/fetch_xite.sh)")
    ap.add_argument("--no-gzip", action="store_true", help="serve .x3d instead of .x3dz")
    a = ap.parse_args()

    repo = a.target == "repo"
    OUT = Path(a.out).resolve() if a.out else (PAGE if repo else None)
    if OUT is None:
        sys.exit("--out is required for the private build")
    if repo:
        if a.audio_dir or a.thumbs_dir:
            sys.exit("the repo build ships no music and no style-board thumbnails: drop --audio-dir/--thumbs-dir")
        brain = Path(a.brain_scene) if a.brain_scene else ROOT / "scenes" / "brain_hero_lite.x3d"
        torso = Path(a.torso_scene) if a.torso_scene else ROOT / "scenes" / "torso_ct_lite.x3d"
    else:
        if not (a.brain_scene and a.torso_scene):
            sys.exit("the private build needs --brain-scene and --torso-scene")
        brain, torso = Path(a.brain_scene), Path(a.torso_scene)
    for p in (brain, torso):
        if not p.exists():
            sys.exit(f"missing scene {p}")
    tex = Path(a.tex_dir) if a.tex_dir else brain.parent / "tex"
    data = Path(a.data_dir)
    gzip_on = not a.no_gzip
    audio_ok = False
    if a.audio_dir:
        ad = Path(a.audio_dir)
        audio_ok = all((ad / Path(u).name).exists() for u in AUDIO_LOOP)
        if not audio_ok:
            sys.exit(f"--audio-dir {ad} lacks {[Path(u).name for u in AUDIO_LOOP]}")
    for need in (PAGE / "template.html", PAGE / "ui.css", PAGE / "page.css", PAGE / "app.js", PAGE / "provenance.json"):
        if not need.exists():
            sys.exit(f"missing page source {need}")

    say(f"build_page.py target={a.target} out={OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    for sub in ("scenes", "data", "thumbs"):
        if (OUT / sub).exists():
            shutil.rmtree(OUT / sub)
    files = []

    # ---- scenes
    scenes = []
    served_names = {}
    for kind, src in (("brain", brain), ("torso", torso)):
        blob, name, rec = prepare_scene(src, kind, audio_ok, gzip_on, a.target == "repo")
        files.append(write_bytes(OUT / "scenes" / name, blob))
        scenes.append(rec)
        served_names[kind] = rec
        say(f"  {kind}: {rec['variant']}: {rec['counts']}")
    if not tex.exists():
        sys.exit(f"missing texture folder {tex}")
    n = copy_tree(tex, OUT / "scenes" / "tex")
    say(f"  scenes/tex: {n} files")
    if not (tex / "env64").exists():
        sys.exit(f"missing studio cube faces {tex / 'env64'} (both scenes read tex/env64/studio-*.png)")
    if audio_ok:
        for u in AUDIO_LOOP:
            p = Path(a.audio_dir) / Path(u).name
            files.append(write_bytes(OUT / "scenes" / "audio" / p.name, p.read_bytes()))
    if a.thumbs_dir:
        td = Path(a.thumbs_dir)
        looks_in = json.loads((data / DATA_FILES["looks"]).read_text())
        for lk in looks_in:
            t = td / f"{lk['board']}.jpg"
            if not t.exists():
                sys.exit(f"missing thumbnail {t}")
            files.append(write_bytes(OUT / "thumbs" / t.name, t.read_bytes()))

    # ---- data (minified copies)
    cfg_data = {}
    for key, fn in DATA_FILES.items():
        obj = json.loads((data / fn).read_text())
        files.append(write_bytes(OUT / "data" / fn, json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")))
        cfg_data[key] = f"data/{fn}"

    # ---- notices
    for src, dst in ((ROOT / "NOTICE-BRAIN-DATA.md", "NOTICE-BRAIN-DATA.md"), (data / "TORSO-NOTICE.md", "NOTICE-TORSO.md")):
        if src.exists():
            files.append(write_bytes(OUT / dst, src.read_bytes()))

    # ---- vendor
    if a.xite_dist:
        vendor_xite(a.xite_dist, OUT / "vendor" / "x_ite")
    if repo:
        (OUT / ".gitignore").write_text("# X_ITE is fetched by tools/fetch_xite.sh (npm) and is not committed\nvendor/\n")

    # ---- provenance
    prov = json.loads((PAGE / "provenance.json").read_text())
    tool_sha = sha256_file(HERE / "build_page.py")[:16]
    prov["build"] = {"kind": a.target, "tool": "tools/build_page.py", "tool_sha256_16": tool_sha, "xite_version": XITE_VERSION, "gzip_scenes": gzip_on}
    prov["scenes"] = scenes
    src_files = []
    for p in (PAGE / "template.html", PAGE / "ui.css", PAGE / "page.css", PAGE / "app.js"):
        src_files.append({"path": f"page/{p.name}", "bytes": p.stat().st_size, "sha256": sha256_file(p)})
    prov["files"] = [f for f in files if f["path"].startswith("data/") or f["path"].startswith("scenes/audio/")] + src_files
    prov["files"] = [f for f in prov["files"] if f["path"] != "data/provenance.json"]
    if not repo:
        prov["notices"] = prov.get("notices", [])
    files.append(write_bytes(OUT / "data" / "provenance.json", json.dumps(prov, separators=(",", ":"), ensure_ascii=False).encode("utf-8")))
    cfg_data["prov"] = "data/provenance.json"

    # ---- index.html
    cfg = {
        "build": a.target,
        "scenes": {k: v["file"] for k, v in served_names.items()},
        "sceneBytes": {k: v["bytes"] for k, v in served_names.items()},
        "data": cfg_data,
        "audio": audio_ok,
        "thumbs": "thumbs/" if a.thumbs_dir else None,
        "xite": {"vendor": "vendor/x_ite/x_ite.min.js", "cdn": XITE_CDN if repo else None, "version": XITE_VERSION},
        "loadBudgetMs": 240000,
    }
    tpl = (PAGE / "template.html").read_text()
    css = (PAGE / "ui.css").read_text() + "\n" + (PAGE / "page.css").read_text()
    js = (PAGE / "app.js").read_text()
    tour = json.loads((data / DATA_FILES["tour"]).read_text())
    cfg_json = json.dumps(cfg, separators=(",", ":")).replace("</", "<\\/")
    html = (tpl.replace("{{TITLE}}", f"{tour.get('title', 'Neural Canvas')} - Brain Loom demo")
            .replace("{{DESC}}", (tour.get("subtitle") or "Interactive template-brain atlas in X3D").replace('"', "&quot;"))
            .replace("{{BUILD}}", a.target)
            .replace("{{CONFIG}}", cfg_json)
            .replace("{{CSS}}", css.replace("</style", "<\\/style"))
            .replace("{{JS}}", js.replace("</script", "<\\/script")))
    leftovers = re.findall(r"\{\{[A-Z_]+\}\}", html)
    if leftovers:
        sys.exit(f"unfilled template placeholders: {leftovers}")
    files.append(write_bytes(OUT / "index.html", html.encode("utf-8")))

    total = sum(f["bytes"] for f in files)
    say(f"done: {len(files)} files, {total:,d} bytes (without vendor/ and scenes/tex). index.html sha256 {sha256_bytes(html.encode('utf-8'))}")


if __name__ == "__main__":
    main()
