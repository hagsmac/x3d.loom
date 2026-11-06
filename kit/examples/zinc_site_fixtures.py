"""Write the synthetic zinc-site candidate used by run_zinc_site.sh (deterministic: same bytes every run).

The geometry comes from kit/tests/test_metalsite.py, so the run and the tests exercise one fixture
definition (shared code is a shared assumption: this rehearses the instrument path, it does not
witness any real protein). Every file says SYNTHETIC in its header.

  python3 -I kit/examples/zinc_site_fixtures.py DEST [--drifted]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / "tests"))
sys.path.insert(0, str(KIT))

import test_metalsite as fx  # noqa: E402

HEADER = ("REMARK   1 SYNTHETIC FIXTURE, NOT A PDB ENTRY: ideal tetrahedral zinc site, CCCH ligand set\n"
          "REMARK   1 Zn-S 2.33 and Zn-N 2.07 angstrom, written by kit/examples/zinc_site_fixtures.py\n")


def write(dest: Path, drifted: bool = False) -> None:
    (dest / "structures").mkdir(parents=True, exist_ok=True)
    ligands = fx.with_r(fx.CCCH, 2, 3.6) if drifted else fx.CCCH
    base = fx.site_atoms(ligands)
    (dest / "structures/ccch-site.pdb").write_text(HEADER + fx.pdb([base]))
    (dest / "structures/ccch-site-20-frames.pdb").write_text(
        HEADER + "REMARK   1 20 frames, each atom moved by at most 0.035 angstrom per axis (a deterministic sine)\n"
        + fx.pdb([fx.jitter(base, k) for k in range(20)]))
    spec = fx.spec("CCCH", min_intact_fraction=0.99)
    spec["note"] = ("Synthetic rehearsal spec. Windows are the module defaults (typical values, grade L). "
                    "A real study declares its own windows from the structures it uses.")
    (dest / "metal-site-spec.json").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    (dest / "SYNTHETIC.md").write_text(
        "# Synthetic zinc-site candidate\n\n"
        "Two PDB-format files with one ideal CCCH zinc site, one static and one with 20 jittered frames, and the "
        "metal-site spec they are checked against. They exist to rehearse the instrument path (witness, accept, "
        "receipt, controls). They are not a protein structure and not a simulation.\n")


if __name__ == "__main__":
    write(Path(sys.argv[1]), drifted="--drifted" in sys.argv)
