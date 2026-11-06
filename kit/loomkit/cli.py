"""loomkit command line. Exit 0 = passed; 1 = candidate contract violation (stable code on stdout);
2 = instrument or input error. Same convention as the Data City gate kit, and it survives `python -O`.

  python -m loomkit candidate ROOT
  python -m loomkit traps     ROOT --evidence DIR --files GLOB [--host strict]
  python -m loomkit grammar   ROOT --evidence DIR --files GLOB [--fork PATH]
  python -m loomkit foldback  ROOT --evidence DIR --patch FILE
  python -m loomkit sci       ROOT --evidence DIR --profile kit/profiles/x3d-stem-science.json
  python -m loomkit play      ROOT --evidence DIR --tapes GLOB --levels GLOB --runner FILE [--repeats 2]
  python -m loomkit hepevent  ROOT --evidence DIR --events GLOB --spec FILE
  python -m loomkit command   ROOT --evidence DIR --name NAME -- CMD ...
  python -m loomkit record    ROOT --evidence DIR --name NAME --status not_run --reason TEXT
  python -m loomkit accept    ROOT --evidence DIR --profile FILE
  python -m loomkit receipt   ROOT --evidence DIR --profile FILE --subject TEXT --out FILE [--outputs F ...] [--prev FILE]
  python -m loomkit verify-receipt FILE
  python -m loomkit sweep     SRC DEST --rules kit/profiles/public-sweep.json
  python -m loomkit picture   REVIEW.json --subject SHA --frames FRAMES.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from . import accept as acc
from . import foldback, grammar, hepevent, metalsite, pagetraps, picture, play, receipt, sci, sweep, traps
from .core import GateError, InstrumentError, candidate, need, portable, sha256_file, write_witness


def _files(root: Path, pattern: str) -> list[Path]:
    """One glob, or several separated by commas ('app/*.js,app/*.html'). Every pattern must match something."""
    found: set[Path] = set()
    for pat in (x.strip() for x in pattern.split(",")):
        hit = {p for p in root.glob(pat) if p.is_file()}
        need(hit, "NO_FILES_MATCHED", pat)
        found |= hit
    return sorted(found)


def cmd_traps(a) -> dict:
    root = Path(a.root)
    subject = candidate(root)["sha256"]
    rows, errors, warnings, seen = {}, 0, 0, {"scenes": 0, "bytes": 0}
    for f in _files(root, a.files):
        data = f.read_bytes()
        seen["scenes"] += 1; seen["bytes"] += len(data)
        hits = traps.check(data, {"host": a.host})
        rows[f.relative_to(root).as_posix()] = [h.__dict__ for h in hits]
        errors += sum(h.severity == "error" for h in hits)
        warnings += sum(h.severity == "warning" for h in hits)
    status = "fail" if errors else "pass"
    return write_witness(a.evidence, root, subject, "traps", status, "C",
                         {"tool": "loomkit.traps", "rules": sorted(traps.RULES),
                          "rules_sha256": sha256_file(Path(traps.__file__))},
                         measurements={"files": len(rows), "errors": errors, "warnings": warnings, "seen": seen, "hits": rows},
                         coverage={"rules": len(traps.RULES)},
                         limitations=["Portable subset of x3d.onto loom_gate.py rules; the family gate itself is not on this machine.",
                                      "Runtime-labelled rules describe the runtime they were observed on."])


def cmd_pagetraps(a) -> dict:
    """Page traps over a study's JavaScript: the X_ITE runtime contracts the Loom has paid for (law 32)."""
    root = Path(a.root)
    subject = candidate(root)["sha256"]
    rows, errors, warnings, seen = {}, 0, 0, {"field_callbacks": 0, "world_loads": 0, "inline_scripts": 0}
    for f in _files(root, a.files):
        text, rel = f.read_text(encoding="utf-8"), f.relative_to(root).as_posix()
        if f.suffix.lower() in (".html", ".htm"):
            hits, code = pagetraps.check_html(text, rel), pagetraps.scripts_view(text)
            seen["inline_scripts"] += len(pagetraps.inline_scripts(text))
        else:
            hits, code = pagetraps.check(text, rel), text
        for k, v in pagetraps.inventory(code).items():
            seen[k] += v
        rows[rel] = [h.__dict__ for h in hits]
        errors += sum(h.severity == "error" for h in hits)
        warnings += sum(h.severity == "warning" for h in hits)
    return write_witness(a.evidence, root, subject, "page-traps", "fail" if errors else "pass", "C",
                         {"tool": "loomkit.pagetraps", "rules": sorted(pagetraps.RULES), "rules_sha256": sha256_file(Path(pagetraps.__file__))},
                         measurements={"files": len(rows), "errors": errors, "warnings": warnings, "seen": seen, "hits": rows},
                         coverage={"rules": len(pagetraps.RULES)},
                         limitations=["Static pattern reading of page JavaScript; a clean result means none of these known traps is present, not that the page behaves correctly.",
                                      "Reads .js files and the inline <script> blocks of .html files listed in --files; 'seen' counts the field callbacks and world loads it read (zero means the X_ITE rules had nothing to judge).",
                                      "Rules are labelled with the runtime they were observed on (X_ITE 16.5.1 unless stated)."])


def cmd_grammar(a) -> list[dict]:
    root = Path(a.root)
    subject = candidate(root)["sha256"]
    files = _files(root, a.files)
    ident, results = grammar.validate(files, Path(a.fork))
    summ = {Path(k).relative_to(root).as_posix(): grammar.summarise(v) for k, v in results.items()}
    g_status = "pass" if all(s["xsd_valid"] and s["xsd_errors"] == 0 for s in summ.values()) else "fail"
    instrument_err = [k for k, s in summ.items() if s["semantic_instrument_error"]]
    if instrument_err:
        m_status = "error"
    else:
        m_status = "pass" if all(s["semantic_errors"] == 0 for s in summ.values()) else "fail"
    lim = [f"Fork commit {ident['commit'][:7]} on branch {ident['branch']}; not the family pin unless they match."]
    out = [write_witness(a.evidence, root, subject, "grammar", g_status, "C", ident,
                         measurements={k: {x: s[x] for x in ("xsd_valid", "xsd_errors", "xsd_version")} for k, s in summ.items()},
                         coverage={"files": len(summ)}, limitations=lim),
           write_witness(a.evidence, root, subject, "meaning", m_status, "C", ident,
                         measurements={k: {x: s[x] for x in ("semantic_errors", "semantic_warnings", "semantic_instrument_error")} for k, s in summ.items()},
                         coverage={"files": len(summ)}, limitations=lim,
                         reason="semantic checker raised on: " + ", ".join(instrument_err) if instrument_err else "")]
    return out


def cmd_foldback(a) -> dict:
    root = Path(a.root)
    subject = candidate(root)["sha256"]
    res = foldback.check(Path(a.patch))
    return write_witness(a.evidence, root, subject, "foldback", res["status"], "C",
                         {"tool": "loomkit.foldback", "git_apply": "empty temporary repository", "python": portable(sys.executable)},
                         measurements=res, coverage={"modes": sorted({s["optimized"] for s in res["smoke"]})},
                         limitations=["Applied to an empty repository only; compatibility with an existing checkout is not tested."],
                         reason=res["reason"] if res["status"] != "pass" else "")


def cmd_sci(a) -> dict:
    """x3d.STEM science gates over loom.scientific-case/1 manifests; writes the 'science' witness."""
    root = Path(a.root)
    subject = candidate(root)["sha256"]
    profile = acc.load_profile(a.profile)
    need("science" in profile, "PROFILE_NOT_SCIENTIFIC", a.profile)
    try:
        res = sci.check_bank(root, profile)
        status, reason = "pass", ""
    except GateError as e:
        res, status, reason = {"rejected": e.code, "detail": e.detail}, "fail", f"{e.code}: {e.detail}"
    return write_witness(a.evidence, root, subject, "science", status, "C",
                         {"tool": "loomkit.sci (reconstructed SCI gates)", "rules_sha256": sha256_file(Path(sci.__file__)),
                          "profile": profile["name"]},
                         measurements=res, coverage={"kinds": len(res.get("kinds", []))},
                         limitations=["Reconstructed from GATES.md; the original governance patch was not delivered."],
                         reason=reason)


def cmd_metalsite(a) -> dict:
    """Metal-site witness over PDB-format structures or trajectories; writes the 'metal-site' witness."""
    root = Path(a.root)
    subject = candidate(root)["sha256"]
    need(Path(a.spec).resolve().is_relative_to(root.resolve()), "SITE_SPEC",
         "the spec must be a file inside the candidate, so the candidate hash covers its thresholds")
    spec = json.loads(Path(a.spec).read_text())
    files = _files(root, a.files)
    try:
        res = metalsite.check_files(files, spec)
        res = {portable(Path(k).relative_to(root)): v for k, v in res.items()}
        status, reason = "pass", ""
    except GateError as e:
        res, status, reason = {"rejected": e.code, "detail": e.detail}, "fail", f"{e.code}: {e.detail}"
    except Exception as e:  # an instrument crash is an error record, never a pass and never a missing record (law 19)
        res, status, reason = {"error": type(e).__name__, "detail": str(e)[:600]}, "error", f"{type(e).__name__}: {e}"
    sites = sum(v["inventory"]["metals_checked"] for v in res.values() if isinstance(v, dict) and "inventory" in v)
    declared = [s for s in spec.get("sites", []) if isinstance(s, dict)] if isinstance(spec, dict) else []
    coverage = {"files": len(files), "sites": sites,
                "class_declared": sum(bool(s.get("class")) for s in declared),
                "tau4_floor_declared": sum(s.get("tau4_min") is not None for s in declared),
                "min_intact_fraction": spec.get("min_intact_fraction", 1.0) if isinstance(spec, dict) else None}
    return write_witness(a.evidence, root, subject, a.name, status, "C",
                         {"tool": "loomkit.metalsite", "rules_sha256": sha256_file(Path(metalsite.__file__)),
                          "spec_sha256": sha256_file(Path(a.spec))},
                         measurements=res, coverage=coverage,
                         limitations=["PDB format only; distance windows are typical values (L), declared in the spec."],
                         reason=reason)


def cmd_hepevent(a) -> dict:
    """Hep-event plausibility witness (a demo witness) over event JSON files and the X3D scenes they name; writes 'hep-event'."""
    root = Path(a.root)
    subject = candidate(root)["sha256"]
    spec = json.loads(Path(a.spec).read_text())
    files = _files(root, a.events)
    try:
        res = hepevent.check_files(files, spec)
        res = {portable(Path(k).relative_to(root)): v for k, v in res.items()}
        status, reason = "pass", ""
    except GateError as e:
        res, status, reason = {"rejected": e.code, "detail": e.detail}, "fail", f"{e.code}: {e.detail}"
    inv = [v["inventory"] for v in res.values() if isinstance(v, dict) and "inventory" in v]
    return write_witness(a.evidence, root, subject, "hep-event", status, "C",
                         {"tool": "loomkit.hepevent", "rules_sha256": sha256_file(Path(hepevent.__file__)),
                          "spec_sha256": sha256_file(Path(a.spec))},
                         measurements=res,
                         coverage={"events": len(files), "scenes": sum(1 for i in inv if i["scene"]),
                                   "tracks": sum(i["tracks"] for i in inv), "towers": sum(i["towers"] for i in inv)},
                         limitations=["Demo plausibility only: loose physics tolerances, declared in the spec; no mass shell, resonance or calorimeter sum rule.",
                                      "Nothing is rendered and no GLSL is compiled here: the shader check proves the binding (shader, attributes, clock route), not the look."],
                         reason=reason)


def cmd_play(a) -> dict:
    """Play witness: every listed level has a tape that replays, deterministically, to its recorded finish."""
    root = Path(a.root)
    subject = candidate(root)["sha256"]
    tapes, levels, runner = _files(root, a.tapes), _files(root, a.levels), root / a.runner
    need(runner.is_file(), "PLAY_RUNNER_MISSING", a.runner)
    try:
        res = play.check(tapes, levels, runner, a.node, a.repeats)
        status, reason = "pass", ""
    except GateError as e:
        res, status, reason = {"rejected": e.code, "detail": e.detail}, "fail", f"{e.code}: {e.detail}"
    node_v = subprocess.run([a.node, "--version"], capture_output=True, text=True).stdout.strip()
    return write_witness(a.evidence, root, subject, "play", status, "C",
                         {"tool": "loomkit.play", "rules_sha256": sha256_file(Path(play.__file__)), "runner": a.runner,
                          "runner_sha256": sha256_file(runner), "node": node_v},
                         measurements=res, coverage={"tapes": len(tapes), "levels": len(levels)},
                         limitations=["Determinism is shown on the runner's JavaScript engine only; other engines need their own replay (the browser witness).",
                                      "A tape proves one way through a level, not that the level is fair, fun or free of shortcuts."],
                         reason=reason)


def cmd_command(a) -> dict:
    """Adapter for a project's own gate: exit 0 pass, 1 fail, anything else error."""
    root = Path(a.root)
    subject = candidate(root)["sha256"]
    cmd = a.cmd
    need(cmd, "NO_COMMAND", "give the project command after --")
    p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=1800)
    status = {0: "pass", 1: "fail"}.get(p.returncode, "error")
    log = (p.stdout + "\n--- stderr ---\n" + p.stderr).encode()
    log_name = f"{a.name}.log"
    Path(a.evidence).mkdir(parents=True, exist_ok=True)
    (Path(a.evidence) / log_name).write_bytes(log)
    return write_witness(a.evidence, root, subject, a.name, status, "C",
                         {"tool": "project gate (adapter)", "command": cmd},
                         measurements={"exit_code": p.returncode, "stdout_tail": p.stdout.strip()[-600:]},
                         evidence=[{"path": log_name, "sha256": hashlib.sha256(log).hexdigest()}],
                         reason="" if status == "pass" else f"exit {p.returncode}")


def cmd_record(a) -> dict:
    root = Path(a.root)
    return write_witness(a.evidence, root, candidate(root)["sha256"], a.name, a.status, a.grade,
                         {"tool": "declared", "by": a.by}, reason=a.reason)


def cmd_accept(a) -> dict:
    return acc.accept(a.root, a.evidence, acc.load_profile(a.profile))


def cmd_receipt(a) -> dict:
    profile = acc.load_profile(a.profile)
    result = acc.accept(a.root, a.evidence, profile)
    cand = candidate(a.root)
    not_run = []
    for name in profile.get("visible_not_run", []):
        p = Path(a.evidence) / f"{name}.json"
        rec = json.loads(p.read_text()) if p.exists() else {"status": "not_run", "reason": "no record"}
        not_run.append({"witness": name, "status": rec["status"], "reason": rec.get("reason", "")})
    tools = {}
    for row in result["witnesses"]:
        rec = json.loads((Path(a.evidence) / f"{row['witness']}.json").read_text())
        tools[row["witness"]] = {k: rec["instrument"][k] for k in ("tool", "commit") if k in rec["instrument"]}
    r = receipt.build(a.subject, result, cand["files"], [Path(o) for o in a.outputs], tools,
                      inputs={"candidate_sha256": cand["sha256"]}, not_run=not_run, model_calls=[],
                      budget={"paid_calls": 0, "cloud_resources": 0}, prev=Path(a.prev) if a.prev else None,
                      limitations=profile.get("limitations", []))
    dest = receipt.write(r, Path(a.out), force=a.force)
    ev = Path(a.evidence)
    roles = {".json": "witness-record", ".log": "log", ".png": "frame", ".jpg": "frame", ".wav": "audio"}
    manifest = {"schema": "loom.evidence-manifest/1", "subject": a.subject, "candidate_sha256": cand["sha256"],
                "profile": profile["name"], "receipt": {"path": dest.name, "sha256": sha256_file(dest)},
                "files": [{"path": p.relative_to(ev).as_posix(), "sha256": sha256_file(p), "bytes": p.stat().st_size,
                           "role": roles.get(p.suffix, "other")} for p in sorted(ev.rglob("*")) if p.is_file()],
                "not_run": [n for n in not_run if n["status"] != "pass"]}
    mpath = dest.parent / "evidence-manifest.json"
    need(a.force or not mpath.exists(), "RECEIPT_EXISTS", str(mpath))
    mpath.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return {"receipt": str(dest), "sha256": r["sha256"], "candidate_sha256": r["candidate_sha256"],
            "evidence_manifest": str(mpath), "evidence_files": len(manifest["files"])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="loomkit")
    sub = ap.add_subparsers(dest="cmd_name", required=True)

    def common(name):
        p = sub.add_parser(name)
        p.add_argument("root")
        p.add_argument("--evidence", required=True)
        return p

    sub.add_parser("candidate").add_argument("root")
    p = common("traps"); p.add_argument("--files", required=True); p.add_argument("--host", default="")
    p = common("pagetraps"); p.add_argument("--files", required=True)
    p = common("grammar"); p.add_argument("--files", required=True); p.add_argument("--fork", default=str(grammar.DEFAULT_FORK))
    p = common("foldback"); p.add_argument("--patch", required=True)
    p = common("sci"); p.add_argument("--profile", required=True)
    p = common("metalsite"); p.add_argument("--files", required=True); p.add_argument("--spec", required=True)
    p.add_argument("--name", default="metal-site")
    p = common("hepevent"); p.add_argument("--events", required=True); p.add_argument("--spec", required=True)
    p = common("play"); p.add_argument("--tapes", required=True); p.add_argument("--levels", required=True)
    p.add_argument("--runner", required=True); p.add_argument("--node", default="node"); p.add_argument("--repeats", type=int, default=2)
    p = common("command"); p.add_argument("--name", required=True)
    p = common("record"); p.add_argument("--name", required=True); p.add_argument("--status", required=True)
    p.add_argument("--grade", default="L"); p.add_argument("--reason", required=True); p.add_argument("--by", default="operator")
    p = common("accept"); p.add_argument("--profile", required=True)
    p = common("receipt"); p.add_argument("--profile", required=True); p.add_argument("--subject", required=True)
    p.add_argument("--out", required=True); p.add_argument("--outputs", nargs="*", default=[])
    p.add_argument("--prev"); p.add_argument("--force", action="store_true")
    sub.add_parser("verify-receipt").add_argument("file")
    p = sub.add_parser("sweep"); p.add_argument("src"); p.add_argument("dest"); p.add_argument("--rules", required=True)
    p.add_argument("--exclude", nargs="*", default=[".git", ".scratch", ".work", "__pycache__", "public-sweep.json"])
    p = sub.add_parser("picture"); p.add_argument("review"); p.add_argument("--subject", required=True); p.add_argument("--frames", required=True)

    argv = list(sys.argv[1:] if argv is None else argv)
    tail = []
    if "--" in argv:  # everything after "--" is the project command for `command`
        i = argv.index("--"); argv, tail = argv[:i], argv[i + 1:]
    a = ap.parse_args(argv)
    a.cmd = tail
    try:
        if a.cmd_name == "candidate":
            c = candidate(a.root); out = {"sha256": c["sha256"], "files": len(c["files"])}
        elif a.cmd_name == "verify-receipt":
            r = receipt.verify(Path(a.file)); out = {"receipt": "intact", "sha256": r["sha256"]}
        elif a.cmd_name == "sweep":
            rules = sweep.load_rules(Path(a.rules)); rules["_path"] = a.rules
            out = sweep.sweep(Path(a.src), Path(a.dest), rules, set(a.exclude))
            (Path(a.dest) / "SWEEP-REPORT.json").write_text(json.dumps({k: v for k, v in out.items()}, indent=2, sort_keys=True) + "\n")
            need(out["status"] == "pass", "LEAK_RESIDUE", json.dumps(out["residue"][:5]))
        elif a.cmd_name == "picture":
            out = picture.validate(json.loads(Path(a.review).read_text()), a.subject, json.loads(Path(a.frames).read_text()))
        else:
            out = {"sci": cmd_sci, "metalsite": cmd_metalsite, "hepevent": cmd_hepevent, "play": cmd_play, "pagetraps": cmd_pagetraps, "traps": cmd_traps, "grammar": cmd_grammar, "foldback": cmd_foldback, "command": cmd_command,
                   "record": cmd_record, "accept": cmd_accept, "receipt": cmd_receipt}[a.cmd_name](a)
    except GateError as e:
        print(json.dumps({"rejected": e.code, "detail": e.detail}))
        return 1
    except (InstrumentError, OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        print(json.dumps({"error": type(e).__name__, "detail": str(e)[:600]}))
        return 2
    except Exception as e:  # a bug in a witness is an instrument error (exit 2), never a violation (exit 1, law 19)
        print(json.dumps({"error": "INSTRUMENT_CRASH", "detail": f"{type(e).__name__}: {e}"[:600]}))
        return 2
    def brief(o):  # a witness record prints as its name and status; anything else prints whole
        return {"witness": o["witness"], "status": o["status"], "reason": o["reason"]} if "schema" in o and "witness" in o else o
    print(json.dumps([brief(o) for o in out] if isinstance(out, list) else brief(out), indent=2, default=str))
    return 0
