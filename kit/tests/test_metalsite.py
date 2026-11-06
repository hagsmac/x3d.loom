"""Two-sided controls for loomkit.metalsite, run under normal Python and `python -O`.

Fixtures are SYNTHETIC and labelled so: ideal tetrahedral zinc sites built from typical bond lengths
(Zn-S 2.33, Zn-N 2.07 angstrom), one CCCH site with the spacing of a tristetraprolin-type finger
(C-X8-C-X5-C-X3-H) and one Cys2His2 site with classic spacing. They exercise the real predicates; they are
not a structure from the PDB. Each negative control must be rejected with its INTENDED diagnostic; any
other exception is a broken test, not a catch (law 19). A negative that passes raises SURVIVING_CONTROL.

  python3 -I kit/tests/test_metalsite.py      # runs both modes and writes kit/tests/metalsite-last-run.json
"""
from __future__ import annotations

import copy
import gzip
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))

from loomkit import metalsite  # noqa: E402
from loomkit.core import GateError  # noqa: E402

TETRA = [(1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]
PLANAR = [(1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0)]


def unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


def site_atoms(ligands, directions=TETRA, metal=(0.0, 0.0, 0.0)):
    """ligands: (resname, resseq, donor_name, element, r). Each donor gets two heavy atoms behind it."""
    atoms = [{"name": "ZN", "resname": "ZN", "chain": "A", "resseq": 101, "element": "ZN", "xyz": metal, "het": True}]
    for (resname, resseq, donor, el, r), d in zip(ligands, directions):
        u = unit(d)
        at = lambda k: tuple(m + c * k for m, c in zip(metal, u))  # noqa: E731
        if resname == "HIS":
            other = "ND1" if donor == "NE2" else "NE2"
            chain = [(donor, "N", r), ("CE1", "C", r + 1.33), (other, "N", r + 2.66)]
        elif resname == "HOH":
            chain = [("O", "O", r)]
        else:
            chain = [(donor, el, r), ("CB", "C", r + 1.81), ("CA", "C", r + 3.34)]
        for name, e, k in chain:
            atoms.append({"name": name, "resname": resname, "chain": "A", "resseq": resseq, "element": e,
                          "xyz": at(k), "het": resname == "HOH"})
    return atoms


def pdb_line(i, a):
    name = a["name"] if len(a["name"]) == 4 or len(a["element"]) == 2 else " " + a["name"]
    x, y, z = a["xyz"]
    return (f"{'HETATM' if a.get('het') else 'ATOM':<6}{i:>5} {name:<4} {a['resname']:>3} {a['chain']:1}{a['resseq']:>4}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}{1.0:6.2f}{0.0:6.2f}          {a['element']:>2}")


def pdb(frames):
    if len(frames) == 1:
        return "\n".join(pdb_line(i + 1, a) for i, a in enumerate(frames[0])) + "\nEND\n"
    out = []
    for k, atoms in enumerate(frames, 1):
        out.append(f"MODEL     {k:>4}")
        out += [pdb_line(i + 1, a) for i, a in enumerate(atoms)]
        out.append("ENDMDL")
    return "\n".join(out) + "\nEND\n"


CCCH = [("CYS", 10, "SG", "S", 2.33), ("CYS", 19, "SG", "S", 2.33), ("CYS", 25, "SG", "S", 2.33), ("HIS", 29, "NE2", "N", 2.07)]
CCHH = [("CYS", 5, "SG", "S", 2.33), ("CYS", 8, "SG", "S", 2.33), ("HIS", 21, "NE2", "N", 2.07), ("HIS", 25, "NE2", "N", 2.07)]


def spec(klass="CCCH", **extra):
    s = {"schema": metalsite.SCHEMA, "search_radius": 3.0,
         "sites": [{"metal": {"resname": "ZN", "chain": "A", "resseq": 101}, "coordination": 4, "class": klass,
                    "tau4_min": 0.7, "donor_atoms": {"HIS": "NE2"}}]}
    s.update(extra)
    return s


def with_r(ligands, k, r):
    lig = list(ligands); lig[k] = lig[k][:4] + (r,); return lig


def jitter(atoms, frame, amp=0.02):
    out = copy.deepcopy(atoms)
    for i, a in enumerate(out):
        a["xyz"] = tuple(c + amp * math.sin(1.7 * frame + 2.3 * i + 0.9 * j) for j, c in enumerate(a["xyz"]))
    return out


def expect(code, fn):
    try:
        fn()
    except GateError as e:
        if e.code != code:
            raise RuntimeError(f"WRONG_DIAGNOSTIC: expected {code}, got {e.code} ({e.detail})") from None
        return {"expected": code, "caught": e.code, "detail": e.detail}
    raise RuntimeError(f"SURVIVING_CONTROL: {code}")


def passes(fn):
    res = fn()
    return {"passed": True, "inventory": next(iter([res]))["inventory"], "site": res["sites"][0]["first_frame"]}


def controls():
    rows = []
    ok = lambda name, text, s: rows.append({"case": name, **passes(lambda: metalsite.check(text, s))})  # noqa: E731
    bad = lambda name, code, text, s: rows.append({"case": name, **expect(code, lambda: metalsite.check(text, s))})  # noqa: E731

    ccch, cchh = pdb([site_atoms(CCCH)]), pdb([site_atoms(CCHH)])
    ok("CCCH site, ideal tetrahedral (positive control)", ccch, spec("CCCH"))
    ok("Cys2His2 site, ideal tetrahedral (positive control)", cchh, spec("CCHH"))
    ok("Zn-S just inside its window (2.44 of 2.45)", pdb([site_atoms(with_r(CCCH, 0, 2.44))]), spec())
    bad("Zn-S just outside its window (2.46)", "SITE_DISTANCE", pdb([site_atoms(with_r(CCCH, 0, 2.46))]), spec())
    bad("Zn-S stretched to 2.90, still inside the search radius", "SITE_DISTANCE", pdb([site_atoms(with_r(CCCH, 1, 2.90))]), spec())
    bad("one cysteine drifted to 3.6 (zinc losing a ligand)", "SITE_COORDINATION", pdb([site_atoms(with_r(CCCH, 2, 3.6))]), spec())
    five = site_atoms(CCCH) + [a for a in site_atoms([("HOH", 301, "O", "O", 2.10)], directions=[(0, 0, 1)])[1:]]
    bad("a water joins at 2.10 (five-coordinate)", "SITE_COORDINATION", pdb([five]), spec())
    bad("declared Cys2His2, structure is CCCH", "SITE_CLASS", ccch, spec("CCHH"))
    taut = [lig if lig[0] != "HIS" else ("HIS", 29, "ND1", "N", 2.07) for lig in CCCH]
    bad("histidine binds through ND1, declared NE2 (wrong tautomer)", "SITE_DONOR", pdb([site_atoms(taut)]), spec())
    bad("square-planar site (tau4 0)", "SITE_GEOMETRY", pdb([site_atoms(CCCH, directions=PLANAR)]), spec())
    nm = site_atoms(CCCH)
    for a in nm:
        a["xyz"] = tuple(c / 10.0 for c in a["xyz"])
    bad("coordinates in nanometres read as angstrom", "SITE_UNITS", pdb([nm]), spec())
    bad("no zinc in the file", "SITE_NO_METAL", pdb([site_atoms(CCCH)[1:]]), spec())
    lines = ccch.splitlines(); lines[2] = lines[2][:30] + "   abc.x" + lines[2][38:]
    bad("a coordinate that is not a number", "SITE_PARSE", "\n".join(lines) + "\n", spec())
    bad("a window written backwards", "SITE_SPEC", ccch,
        {**spec(), "sites": [{**spec()["sites"][0], "windows": {"S": [2.45, 2.20], "N": [1.95, 2.20]}}]})
    bad("a search radius of 5 angstrom (would sweep in second-shell atoms)", "SITE_SPEC", ccch, spec(search_radius=5.0))

    base = site_atoms(CCCH)
    traj = [jitter(base, k) for k in range(20)]
    ok("20-frame trajectory, site intact throughout", pdb(traj), spec())
    escape = [jitter(base, k) if k < 14 else jitter(site_atoms(with_r(CCCH, 0, 3.8)), k) for k in range(20)]
    bad("zinc loses a cysteine in 6 of 20 frames, declared 0.99", "SITE_INTACT_FRACTION", pdb(escape), spec(min_intact_fraction=0.99))
    ok("the same trajectory under a declared 0.6 (the fraction is a declared limit, measured)", pdb(escape), spec(min_intact_fraction=0.6))

    # Archive files ship gzipped (.ent.gz): read as fetched, so the candidate hash is the archive's own bytes.
    with tempfile.TemporaryDirectory(prefix="metalsite-gz-") as d:
        good, broken = Path(d) / "site.ent.gz", Path(d) / "broken.ent.gz"
        good.write_bytes(gzip.compress(ccch.encode("latin-1"), mtime=0))
        broken.write_bytes(b"\x1f\x8b not really gzip")
        rows.append({"case": "a gzip archive file is read as fetched (positive control)",
                     **passes(lambda: metalsite.check_files([good], spec())[good.as_posix()])})
        rows.append({"case": "a corrupt gzip file", **expect("SITE_PARSE", lambda: metalsite.check_files([broken], spec()))})

    # Review round (6 Nov): each control below reproduces a confirmed defect of the first version.
    def extra(atom):
        return pdb([site_atoms(CCCH) + [atom]])
    def atom(name, resname, resseq, el, xyz, het=True):
        return {"name": name, "resname": resname, "chain": "A", "resseq": resseq, "element": el, "xyz": xyz, "het": het}
    bad("a GROMACS water (SOL OW) joins at 2.10", "SITE_COORDINATION", extra(atom("OW", "SOL", 301, "O", (0, 0, 2.1))), spec())
    bad("a backbone carbonyl O joins at 2.10 (not in the donor table)", "SITE_COORDINATION",
        extra(atom("O", "GLY", 40, "O", (0, 0, 2.1), het=False)), spec())
    bad("a chloride joins at 2.30", "SITE_COORDINATION", extra(atom("CL", "CL", 401, "CL", (0, 0, 2.3))), spec())
    hsd = [dict(a, resname="HSD") if a["resseq"] == 29 else a for a in site_atoms(CCCH)]
    ok("a CHARMM file names the histidine HSD (positive control)", pdb([hsd]), spec())
    base2 = site_atoms(CCCH); swapped = copy.deepcopy(base2); swapped[1], swapped[2] = swapped[2], swapped[1]
    bad("atom order differs between frames", "SITE_PARSE", pdb([base2, swapped]), spec())
    broken_first = "\n".join(pdb_line(i + 1, a) for i, a in enumerate(site_atoms(with_r(CCCH, 0, 3.8)))) + "\n"
    bad("a broken site written before the first MODEL", "SITE_PARSE", broken_first + pdb([base2, base2]), spec())
    bad("frames separated by END without MODEL records", "SITE_PARSE", ccch + ccch, spec())
    bad("a donor_atoms key in lower case ('his')", "SITE_SPEC", pdb([site_atoms(taut)]),
        {**spec(), "sites": [{**spec()["sites"][0], "donor_atoms": {"his": "NE2"}}]})
    bad("a tau4 floor on a five-coordinate site", "SITE_SPEC", ccch,
        {**spec(), "sites": [{**spec()["sites"][0], "coordination": 5}]})
    bad("windows given but empty", "SITE_SPEC", ccch, {**spec(), "sites": [{**spec()["sites"][0], "windows": {}}]})
    bad("two site entries select the same zinc", "SITE_SPEC", ccch, {**spec(), "sites": [spec()["sites"][0]] * 2})
    bad("declared ligand residues differ (His33 for His29)", "SITE_LIGANDS", ccch,
        {**spec(), "sites": [{**spec()["sites"][0], "ligands": ["A10", "A19", "A25", "A33"]}]})
    ok("declared ligand residues match (positive control)", ccch,
       {**spec(), "sites": [{**spec()["sites"][0], "ligands": ["A10", "A19", "A25", "A29"]}]})
    far = [atom("O", "HOH", "A000", "O", (30.0, 0, 0)), atom("ZN", "ZN", 102, "ZN", (40.0, 0, 0))]
    res = metalsite.check(pdb([site_atoms(CCCH) + far]), spec())
    if res["inventory"]["undeclared_metals"] != ["ZN A102"]:
        raise RuntimeError(f"INVENTORY: {res['inventory']}")
    rows.append({"case": "a hexadecimal residue number and an undeclared zinc far away (positive; inventory names it)",
                 "passed": True, "inventory": res["inventory"], "site": res["sites"][0]["first_frame"]})
    t_tet = metalsite.tau4((0, 0, 0), [unit(d) for d in TETRA]); t_pl = metalsite.tau4((0, 0, 0), PLANAR)
    if abs(t_tet - 1.000408) > 1e-5 or abs(t_pl) > 1e-12:
        raise RuntimeError(f"TAU4_REFERENCE: tetrahedron {t_tet}, plane {t_pl}")
    rows.append({"case": "tau4 reference values (published /141 form): ideal tetrahedron 1.000408, square plane 0",
                 "passed": True, "inventory": {}, "site": {"tau4_tetrahedron": round(t_tet, 6), "tau4_plane": t_pl}})
    return rows


def cli_controls():
    """The CLI writes a witness record: pass on the clean site, fail with the intended code on the bad one."""
    rows = []
    for label, atoms, want in (("clean", site_atoms(CCCH), ("pass", "")),
                               ("drifted", site_atoms(with_r(CCCH, 2, 3.6)), ("fail", "SITE_COORDINATION"))):
        with tempfile.TemporaryDirectory(prefix="metalsite-") as d:
            root, ev = Path(d) / "cand", Path(d) / "evidence"
            (root / "pdb").mkdir(parents=True)
            (root / "pdb/site.pdb").write_text(pdb([atoms]))
            (root / "spec.json").write_text(json.dumps(spec()))
            name = "metal-site" if label == "clean" else "metal-site-drifted"  # --name: one witness per structure
            p = subprocess.run([str(KIT / "loom"), "metalsite", str(root), "--evidence", str(ev), "--files", "pdb/*.pdb",
                                "--spec", str(root / "spec.json")] + ([] if name == "metal-site" else ["--name", name]),
                               capture_output=True, text=True)
            rec = json.loads((ev / f"{name}.json").read_text())
            if rec["witness"] != name:
                raise RuntimeError(f"CLI_CONTROL: {label}: witness named {rec['witness']!r}, expected {name!r}")
            if rec["status"] != want[0] or not rec["reason"].startswith(want[1]):
                raise RuntimeError(f"CLI_CONTROL: {label}: status {rec['status']}, reason {rec['reason']!r}, stdout {p.stdout}")
            rows.append({"case": f"CLI writes the metal-site witness ({label})", "status": rec["status"], "reason": rec["reason"],
                         "coverage": rec["coverage"]})
    with tempfile.TemporaryDirectory(prefix="metalsite-") as d:  # thresholds must sit inside the candidate hash
        root, ev = Path(d) / "cand", Path(d) / "evidence"
        (root / "pdb").mkdir(parents=True)
        (root / "pdb/site.pdb").write_text(pdb([site_atoms(CCCH)]))
        (Path(d) / "spec.json").write_text(json.dumps(spec()))
        p = subprocess.run([str(KIT / "loom"), "metalsite", str(root), "--evidence", str(ev), "--files", "pdb/*.pdb",
                            "--spec", str(Path(d) / "spec.json")], capture_output=True, text=True)
        out = json.loads(p.stdout or "{}")
        if p.returncode != 1 or out.get("rejected") != "SITE_SPEC" or (ev / "metal-site.json").exists():
            raise RuntimeError(f"CLI_CONTROL: spec outside the candidate: exit {p.returncode}, {p.stdout[-200:]}")
        rows.append({"case": "CLI refuses a spec outside the candidate", "status": "rejected", "reason": out["rejected"]})
    return rows


if __name__ == "__main__":
    if "--child" in sys.argv:
        print(json.dumps({"controls": controls(), "cli": cli_controls(), "optimized": bool(sys.flags.optimize)}))
        sys.exit(0)
    report = {"schema": "loomkit.self-test/1", "suite": "metalsite",
              "scope": "Synthetic zinc sites exercising the real predicates; not a structure from the PDB and not a simulation.",
              "modes": []}
    for flags in ([], ["-O"]):
        p = subprocess.run([sys.executable, "-I", *flags, __file__, "--child"], capture_output=True, text=True)
        if p.returncode != 0:
            print(p.stdout, p.stderr, file=sys.stderr)
            sys.exit(1)
        res = json.loads(p.stdout)
        report["modes"].append({"optimized": res["optimized"],
                                "negative_controls_caught": sum(1 for r in res["controls"] if "caught" in r),
                                "positive_controls_passed": sum(1 for r in res["controls"] if r.get("passed")),
                                "cli_controls": len(res["cli"]), "detail": res})
    (KIT / "tests/metalsite-last-run.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for m in report["modes"]:
        print(f"optimized={m['optimized']}: {m['negative_controls_caught']} negative controls caught with the intended code, "
              f"{m['positive_controls_passed']} positive controls pass, {m['cli_controls']} CLI controls")
