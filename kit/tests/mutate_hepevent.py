"""Mutation pass over kit/loomkit/hepevent.py: disable one need(...) site at a time, run the hepevent suite (child mode,
normal Python), count the mutants the suite catches, and say HOW each was caught.

  python3 -I kit/tests/mutate_hepevent.py . OUTDIR [workers]     # last run: kit/tests/hepevent-mutation-last-run.json

A kill is "control" when a control failed its own assertion (SURVIVING_CONTROL, WRONG_DIAGNOSTIC, WRONG_REASON,
INVENTORY, DETERMINISM: the suite noticed the missing gate), and "crash" when the witness raised some other exception
further on because the gate was gone (the suite still fails, but not for the gate's own reason; law 19 counts only the
first kind as a gate with its own control).

Limit: it disables the raising predicates only, not thresholds or the arithmetic inside them."""
import json, re, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

repo, out = Path(sys.argv[1]), Path(sys.argv[2])
workers = int(sys.argv[3]) if len(sys.argv) > 3 else 4
src = (repo / "kit/loomkit/hepevent.py").read_text()
sites = [m.start() for m in re.finditer(r"(?<![\w.])need\(", src)]
CONTROL = re.compile(r"RuntimeError: (SURVIVING_CONTROL|WRONG_DIAGNOSTIC|WRONG_REASON|INVENTORY|DETERMINISM)")


def line_of(pos):
    return src.count("\n", 0, pos) + 1


def run(i):
    pos = sites[i]
    mutant = src[:pos] + "(lambda *a, **k: None)(" + src[pos + len("need("):]
    with tempfile.TemporaryDirectory(prefix="mut-") as d:
        kit = Path(d) / "kit"
        shutil.copytree(repo / "kit", kit, ignore=shutil.ignore_patterns("__pycache__"))
        (kit / "loomkit/hepevent.py").write_text(mutant)
        try:
            p = subprocess.run([sys.executable, "-I", str(kit / "tests/test_hepevent.py"), "--child"], capture_output=True, text=True, timeout=900)
            rc, err = p.returncode, p.stderr
        except subprocess.TimeoutExpired:
            rc, err = -1, "TIMEOUT"
    why = (err.strip().splitlines() or [""])[-1][:240]
    kind = None if rc == 0 else ("control" if CONTROL.search(why) else "crash")
    return {"site": i, "line": line_of(pos), "caught": rc != 0, "by": kind, "why": why}


with ThreadPoolExecutor(workers) as ex:
    res = list(ex.map(run, range(len(sites))))
surv = [r for r in res if not r["caught"]]
by_control = sum(1 for r in res if r["by"] == "control")
by_crash = sum(1 for r in res if r["by"] == "crash")
out.mkdir(parents=True, exist_ok=True)
rec = {"instrument": f"kit/tests/mutate_hepevent.py, {workers} workers, normal Python; a mutant is caught when the suite child exits non-zero, "
                     "by 'control' when a control's own assertion failed, by 'crash' when the witness raised some other exception",
       "sites": len(sites), "caught": len(sites) - len(surv), "caught_by_control": by_control, "caught_by_crash": by_crash,
       "survivors": surv, "all": res}
(out / "mutation.json").write_text(json.dumps(rec, indent=1) + "\n")
print(json.dumps({"sites": len(sites), "caught": len(sites) - len(surv), "by_control": by_control, "by_crash": by_crash,
                  "survivors": [r["line"] for r in surv], "crash_lines": [r["line"] for r in res if r["by"] == "crash"]}))
