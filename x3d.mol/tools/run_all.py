#!/usr/bin/env python3 -I
"""Build, validate, witness and receipt the whole x3d.mol catalogue in one run.

  XMOL_FORK=/path/to/x3d_mcp  python3 -I tools/run_all.py        # python needs gemmi, numpy, lxml, pydssp

1. src/build.py writes scenes/*.x3d and catalog.json
2. the same build into a temp folder must give identical sha256 for every scene (determinism)
3. the x3d_mcp fork's validate_xml and semantic_diagnostics run over every scene, read-only, in the fork's own venv
4. src/witness.py checks every scene against its source file
5. tests/test_witness.py runs the negative and positive controls
5b. src/anim.py writes the diffusion illustrations to scenes/anim/; they get the same determinism, validator, witness
    (src/anim_witness.py) and controls (tests/test_anim_witness.py)
6. scenes/receipt.json records versions, hashes and verdicts, unsigned: it shows drift, not authorship
Exit code 0 only if everything is green.
"""
import hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORK = Path(os.environ.get("XMOL_FORK", os.environ.get("LOOM_FORK", str(ROOT.parent.parent / "x3d_mcp"))))
FORK_PY = FORK / ".venv/bin/python"
CHILD = r'''
import json, sys
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + "/src")
from validation.validate import validate_xml
from validation.semantic import semantic_diagnostics
out = {}
for p in sys.argv[2:]:
    t = open(p, encoding="utf-8").read()
    g = validate_xml(t)
    d = semantic_diagnostics(t)
    out[p] = {"xsd_valid": bool(g.get("valid")), "xsd_errors": [str(e)[:300] for e in (g.get("errors") or [])][:5], "xsd_version": g.get("version"),
              "semantic_errors": [x.__dict__ for x in d if x.level == "error"][:5], "semantic_warnings": [x.__dict__ for x in d if x.level == "warning"][:5]}
print(json.dumps(out, default=str))
'''


def sh(*a, **k):
    return subprocess.run(a, capture_output=True, text=True, **k)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    py = sys.executable
    steps = {}
    r = sh(py, "-I", str(ROOT / "src/build.py"), "--out", str(ROOT / "scenes"))
    steps["build"] = r.returncode == 0
    print(r.stdout[-400:], r.stderr[-400:])
    if r.returncode:
        return 1
    catalog = json.loads((ROOT / "scenes/catalog.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        r2 = sh(py, "-I", str(ROOT / "src/build.py"), "--out", tmp)
        same = r2.returncode == 0 and all(sha(Path(tmp) / f"{s['id']}.x3d") == s["sha256"] for s in catalog["scenes"])
    steps["deterministic"] = same
    print("determinism: second build identical for", len(catalog["scenes"]), "scenes" if same else "scenes FAILED")
    files = [str(ROOT / "scenes" / f"{s['id']}.x3d") for s in catalog["scenes"]]
    if not FORK_PY.exists():
        print("fork venv missing:", FORK_PY); return 1
    v = sh(str(FORK_PY), "-I", "-c", CHILD, str(FORK), *files)
    if v.returncode:
        print(v.stderr[-800:]); return 1
    val = json.loads(v.stdout)
    git = lambda *a: sh("git", "-C", str(FORK), *a).stdout.strip()
    validator = {"tool": "x3d_mcp fork (validate_xml + semantic_diagnostics)", "commit": git("rev-parse", "HEAD"),
                 "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}
    sys.path.insert(0, str(ROOT / "src"))
    import witness as WT
    scenes, ok = {}, steps["deterministic"]
    for s in catalog["scenes"]:
        path = ROOT / "scenes" / f"{s['id']}.x3d"
        g = val[str(path)]
        fails = WT.check(path)
        scenes[s["id"]] = {"sha256": s["sha256"], "bytes": s["bytes"], "xsd_valid": g["xsd_valid"], "xsd_errors": len(g["xsd_errors"]),
                           "semantic_errors": len(g["semantic_errors"]), "semantic_warnings": len(g["semantic_warnings"]),
                           "witness": "pass" if not fails else "; ".join(f"{c}" for c, _ in fails)}
        ok &= g["xsd_valid"] and not g["semantic_errors"] and not fails
        print(("ok  " if g["xsd_valid"] and not g["semantic_errors"] and not fails else "FAIL"), s["id"], scenes[s["id"]]["witness"], g["xsd_errors"][:1], g["semantic_errors"][:1])
    t = sh(py, "-I", str(ROOT / "tests/test_witness.py"))
    print(t.stdout.splitlines()[-1])
    ctl = json.loads((ROOT / "tests/last-run.json").read_text())
    ok &= ctl["failed"] == 0
    # diffusion illustrations (src/anim.py): build twice, validate, witness, controls
    anim_dir = ROOT / "scenes/anim"
    r = sh(py, "-I", str(ROOT / "src/anim.py"), "--out", str(anim_dir))
    steps["anim_build"] = r.returncode == 0
    print(r.stdout[-400:], r.stderr[-400:])
    anim = json.loads((anim_dir / "anim.json").read_text()) if r.returncode == 0 else {"scenes": []}
    with tempfile.TemporaryDirectory() as tmp:
        r2 = sh(py, "-I", str(ROOT / "src/anim.py"), "--out", tmp)
        same = r2.returncode == 0 and all(sha(Path(tmp) / Path(s["file"]).name) == s["sha256"] for s in anim["scenes"])
    steps["anim_deterministic"] = same
    ok &= steps["anim_build"] and same
    afiles = [str(ROOT / s["file"]) for s in anim["scenes"]]
    v = sh(str(FORK_PY), "-I", "-c", CHILD, str(FORK), *afiles)
    aval = json.loads(v.stdout) if v.returncode == 0 else {}
    import anim_witness as AW
    anim_scenes = {}
    for s, f in zip(anim["scenes"], afiles):
        g = aval.get(f, {"xsd_valid": False, "xsd_errors": ["validator failed"], "semantic_errors": [], "semantic_warnings": []})
        fails = AW.check(Path(f))
        anim_scenes[s["id"]] = {"sha256": s["sha256"], "bytes": s["bytes"], "atoms": s["atoms"], "keys": s["keys"], "xsd_valid": g["xsd_valid"],
                                "xsd_errors": len(g["xsd_errors"]), "semantic_errors": len(g["semantic_errors"]), "semantic_warnings": len(g["semantic_warnings"]),
                                "witness": "pass" if not fails else "; ".join(c for c, _ in fails)}
        good = g["xsd_valid"] and not g["semantic_errors"] and not fails
        ok &= good
        print(("ok  " if good else "FAIL"), "anim", s["id"], anim_scenes[s["id"]]["witness"], g["xsd_errors"][:1], g["semantic_errors"][:1])
    t = sh(py, "-I", str(ROOT / "tests/test_anim_witness.py"))
    print(t.stdout.splitlines()[-1] if t.stdout else t.stderr[-400:])
    actl = json.loads((ROOT / "tests/last-anim-run.json").read_text())
    ok &= actl["failed"] == 0 and t.returncode == 0
    receipt = {"schema": "x3d.mol.receipt/1", "unsigned": True, "builder_sha256": catalog["builder_sha256"], "validator": validator, "steps": steps,
               "controls": {"negative": ctl["negative"], "positive": ctl["positive"], "failed": ctl["failed"]}, "scenes": scenes,
               "anim": {"disclaimer": anim.get("disclaimer"), "scenes": anim_scenes, "controls": {"negative": actl["negative"], "positive": actl["positive"], "failed": actl["failed"]}},
               "tools": {"python": sys.version.split()[0], "gemmi": __import__("gemmi").__version__, "numpy": __import__("numpy").__version__,
                         "pydssp": sh(py, "-I", "-c", "import importlib.metadata as m;print(m.version('pydssp'))").stdout.strip()},
               "note": "A pass names what it read. The witness shares written rules with the generator (guide smoothing, ring layout, palette, 2.5 and 3.0 angstrom zinc rules, the 800 residue focus rule) and is independent in parsing and arithmetic."}
    (ROOT / "scenes/receipt.json").write_text(json.dumps(receipt, indent=1))
    print("RECEIPT", "green" if ok else "RED", "validator", validator["commit"][:12])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
