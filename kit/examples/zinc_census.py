"""Census of every declared zinc site in every deposited model (P1 of the zinc finger study).

The metal-site witness stops at the first broken rule; this census reports everything, so the prose can quote
generated numbers instead of retyping them (playbook §4). It gates nothing.

  python3 -I kit/examples/zinc_census.py CANDIDATE OUT_DIR    # writes census.json and census.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from loomkit import metalsite as ms  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zinc_structures import STRUCTURES  # noqa: E402


def census(cand: Path) -> list[dict]:
    rows = []
    for pid, (what, method, _, _) in STRUCTURES.items():
        spec = json.loads((cand / "specs" / f"{pid}.json").read_text())
        frames = ms.parse_pdb(ms.read_coordinates(cand / "structures" / f"pdb{pid}.ent.gz"))
        radius = spec["search_radius"]
        win = ms.DEFAULT_WINDOWS["ZN"]
        for site in spec["sites"]:
            metal0 = ms._metals(frames[0], site["metal"])[0]
            idx = frames[0].index(metal0)
            by_el, his, classes, taus, counts, out_models, unlisted, unlisted_models = {}, set(), set(), [], set(), 0, set(), 0
            for atoms in frames:
                m = atoms[idx]
                don = ms.ligands(atoms, m, radius)  # by element, the witness's own search
                counts.add(len(don))
                classes.add(ms.ligand_class(don))
                unlisted |= {f"{d['resname']}{d['resseq']}.{d['name']}" for d in don if not ms.listed(d)}
                unlisted_models += any(not ms.listed(d) for d in don)
                bad = False
                for d in don:
                    r = ms._dist(m["xyz"], d["xyz"])
                    by_el.setdefault(d["element"], []).append(r)
                    lo, hi = win.get(d["element"], (0, 99))
                    bad = bad or not (lo <= r <= hi)
                    if d["resname"] in ("HIS", "HID", "HIE", "HIP"):
                        his.add(d["name"])
                out_models += bad
                if len(don) == 4:
                    taus.append(ms.tau4(m["xyz"], [d["xyz"] for d in don]))
            rows.append({"pdb": pid.upper(), "what": what, "method": method, "models": len(frames),
                         "site": f"{site['metal']['chain']}{site['metal']['resseq']}", "declared": site["class"],
                         "measured": "/".join(sorted(classes)), "donors": sorted(counts),
                         "his_donor": "/".join(sorted(his)) or "none",
                         "zn_s": [round(min(by_el["S"]), 3), round(max(by_el["S"]), 3)] if "S" in by_el else None,
                         "zn_n": [round(min(by_el["N"]), 3), round(max(by_el["N"]), 3)] if "N" in by_el else None,
                         "tau4_min": round(min(taus), 3) if taus else None,
                         "models_outside_windows": out_models,
                         "ligands_not_in_donor_table": sorted(unlisted), "models_with_such_ligands": unlisted_models})
    return rows


def unlisted_col(r: dict) -> str:
    if not r["ligands_not_in_donor_table"]:
        return "–"
    return f"{', '.join(r['ligands_not_in_donor_table'])} ({r['models_with_such_ligands']} of {r['models']} models)"


def markdown(rows: list[dict]) -> str:
    head = ("| PDB | Method | Site | Declared | Measured | Donors | His binds via | Zn–S (Å) | Zn–N (Å) | tau4 min | "
            "Models outside the windows | Ligands not in the donor table |\n|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    fmt = lambda v: "–" if v is None else f"{v[0]:.3f}–{v[1]:.3f}"  # noqa: E731
    return head + "".join(
        f"| {r['pdb']} | {r['method']} | {r['site']} | {r['declared']} | {r['measured']} | {'/'.join(map(str, r['donors']))} | "
        f"{r['his_donor']} | {fmt(r['zn_s'])} | {fmt(r['zn_n'])} | {r['tau4_min'] if r['tau4_min'] is not None else '–'} | "
        f"{r['models_outside_windows']} of {r['models']} | "
        f"{unlisted_col(r)} |\n" for r in rows)


if __name__ == "__main__":
    cand, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = census(cand)
    (out / "census.json").write_text(json.dumps({"schema": "loom.zinc-census/1", "windows": ms.DEFAULT_WINDOWS,
                                                 "rows": rows}, indent=2, sort_keys=True) + "\n")
    (out / "census.md").write_text(markdown(rows))
    print(markdown(rows))
