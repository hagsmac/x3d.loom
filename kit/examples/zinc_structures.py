"""P1 of the zinc finger study: the deposited structures, as fetched, and one metal-site spec per structure.

  python3 -I kit/examples/zinc_structures.py DEST            # verify DEST/structures against the pins, write specs
  python3 -I kit/examples/zinc_structures.py DEST --fetch    # fetch missing files from the archive snapshot first

Source: the wwPDB archive snapshot of 1 January 2026, served by the RCSB's public snapshot bucket
(https://pdbsnapshots.s3.us-west-2.amazonaws.com/20260101/pub/pdb/data/structures/divided/pdb/). Each file is
kept byte for byte as fetched (.ent.gz) and pinned by sha256 below, so the candidate hash is the archive's own.

What each spec declares, and where the declaration comes from (written before the witness ran on these files):
- the zinc residues: chain and residue number as deposited (identity, not a measured property);
- coordination 4 and the ligand class in sequence order, from the protein family's literature (grade L);
- tau4 at least 0.7 (roughly tetrahedral), the default distance windows and the 3.0 angstrom search radius,
  all exactly as declared for the synthetic rehearsal in runs/zinc-site-20261106 (not tuned to these files);
- for NMR ensembles, the site must hold in at least 0.99 of the deposited models (all of them, for 10 to 23 models).
Histidine donor atoms are NOT declared: P1 measures them, because the simulation set-up must copy them.

Structures looked at and left out (no zinc site to check, or not in the snapshot):
- 6FBS and 6BLL are obsolete: 6FUW superseded 6FBS (21 March 2018) and 6DNH superseded 6BLL (27 June 2018).
- 6BLY and 6BM0 are CPSF-160-WDR33 complexes with no CPSF30 chain and no zinc.
- 4J8S is a TTP peptide bound to CNOT1, with no zinc finger.
"""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

SNAPSHOT = "https://pdbsnapshots.s3.us-west-2.amazonaws.com/20260101/pub/pdb/data/structures/divided/pdb"

# id: (what it is, method, pinned sha256 of pdbXXXX.ent.gz, [(chain, resseq, class)])
STRUCTURES = {
    "1aay": ("Zif268 (Egr-1) three fingers on DNA", "X-ray 1.60 A",
             "f6977b2f743d3d8f923237a80e0833846dc62f10c8bbed6ab5d35812738b2326",
             [("A", 201, "CCHH"), ("A", 202, "CCHH"), ("A", 203, "CCHH")]),
    "1zaa": ("Zif268 three fingers on DNA, the first structure (1991)", "X-ray 2.10 A",
             "51471d5b00c9a8e44b1ea378959c57a3c22afaa084fde83626bcac7fb820048c",
             [("C", 201, "CCHH"), ("C", 202, "CCHH"), ("C", 203, "CCHH")]),
    "1ubd": ("YY1 four fingers on DNA", "X-ray 2.50 A",
             "2ee9603eeeb492e359ede1652ba440f41a631c423343f55e60b8ba3381d08bfe",
             [("C", 501, "CCHH"), ("C", 502, "CCHH"), ("C", 503, "CCHH"), ("C", 504, "CCHH")]),
    "1rgo": ("TIS11d (ZFP36L2) tandem fingers on UUAUUUAUU RNA", "NMR, 20 models",
             "22ae0f0320731e1ac71848c16b7760e3bbdc2931bf2926e43db96f274ef3893f",
             [("A", 221, "CCCH"), ("A", 222, "CCCH")]),
    "1m9o": ("TTP-family (Nup475) first finger, no RNA", "NMR, 23 models",
             "da2c0fa3c298ad3ab08f359a1136643284d5ee0f34c7a0646547c4cf1cb4cf33",
             [("A", 78, "CCCH")]),
    "6nzl": ("POS-1 tandem fingers (worm), no RNA", "NMR, 20 models",
             "5e09df86d69f4cfabaa79bd32fc38db918263cfd065e4203a55fec6dce8de2a0",
             [("A", 201, "CCCH"), ("A", 202, "CCCH")]),
    "1n0z": ("ZRANB2 first finger (RanBP2 type)", "NMR, 20 models",
             "708e3c4a8e0fa42d487b230c541de8c59d21e580cc25eb9a1661e420d3563071",
             [("A", 46, "CCCC")]),
    "2k1p": ("ZRANB2 second finger", "NMR, 20 models",
             "dfde0879f152038886662445174f99f2112f4bcf8a966605fbea6d07ccf51447",
             [("A", 96, "CCCC")]),
    "3g9y": ("ZRANB2 second finger on AGGUAA RNA", "X-ray 1.40 A",
             "752b0db7185abae2a39ce095af982c2b2147aec353de63d0c9a58158aa381efa",
             [("A", 1, "CCCC")]),
    "2jvx": ("NEMO zinc finger", "NMR, 10 models",
             "e82dc25b1c1d16890e142f3a2be2504dc1fe69632d5eb0065e9847f1f9bc60e0",
             [("A", 29, "CCHC")]),
    "4av1": ("PARP1 first and second fingers on DNA, two copies", "X-ray 3.10 A",
             "d3aeebbe5e02da7b8516c6e3293505718122ee21c7b3e182bba99ecde31de8e1",
             [("A", 1600, "CCHC"), ("B", 1600, "CCHC"), ("C", 1600, "CCHC"), ("D", 1600, "CCHC")]),
    "6fuw": ("CPSF30 fingers 1-3 on the AAUAAA signal (supersedes 6FBS)", "cryo-EM 3.07 A",
             "e71ce2b915bc46848e40c7386c7a290c2a722f829b81172c50009ad091eb941a",
             [("C", 201, "CCCH"), ("C", 202, "CCCH"), ("C", 203, "CCCH")]),
    "6dnh": ("CPSF30 fingers 1-3 on the AAUAAA signal (supersedes 6BLL)", "cryo-EM 3.40 A",
             "e6947fccd845faf757e2a2371c652cdffd76023d84a14c4f354b96af780f744b",
             [("C", 301, "CCCH"), ("C", 302, "CCCH"), ("C", 303, "CCCH")]),
    "6uro": ("CPSF30 fingers 1-3 on AAUAAA, with CstF77", "cryo-EM 3.60 A",
             "31e6894a45ca4b0534b93da2da1b10ac7e054f62aed77afe6631ad2869ba0af4",
             [("C", 301, "CCCH"), ("C", 302, "CCCH"), ("C", 303, "CCCH")]),
}


def spec_for(pdb_id: str) -> dict:
    what, method, _, sites = STRUCTURES[pdb_id]
    return {"schema": "loom.metal-site-spec/1", "search_radius": 3.0, "min_intact_fraction": 0.99,
            "note": f"{pdb_id.upper()}: {what} ({method}). Ligand classes from the family's literature (L); "
                    "tau4, windows and radius as declared for the synthetic rehearsal.",
            "sites": [{"metal": {"resname": "ZN", "chain": c, "resseq": r}, "coordination": 4, "class": k, "tau4_min": 0.7}
                      for c, r, k in sites]}


def write(dest: Path, fetch: bool = False) -> list[str]:
    (dest / "structures").mkdir(parents=True, exist_ok=True)
    (dest / "specs").mkdir(parents=True, exist_ok=True)
    for pdb_id, (_, _, pin, _) in STRUCTURES.items():
        path = dest / "structures" / f"pdb{pdb_id}.ent.gz"
        if not path.exists():
            if not fetch:
                raise SystemExit(f"missing {path.name}: run with --fetch")
            with urllib.request.urlopen(f"{SNAPSHOT}/{pdb_id[1:3]}/pdb{pdb_id}.ent.gz", timeout=60) as r:
                path.write_bytes(r.read())
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != pin:
            raise SystemExit(f"PIN_MISMATCH {path.name}: {got} != {pin}")
        (dest / "specs" / f"{pdb_id}.json").write_text(json.dumps(spec_for(pdb_id), indent=2, sort_keys=True) + "\n")
    return list(STRUCTURES)


if __name__ == "__main__":
    print(" ".join(write(Path(sys.argv[1]), fetch="--fetch" in sys.argv)))
