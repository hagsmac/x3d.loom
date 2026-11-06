"""Pick the committed fixtures from a bulk Pythia run and write them (standard library only).

  python3 -I kit/examples/hep/select_fixtures.py BULK_DIR DEST_DIR
  BULK_DIR holds zmumu/ (50 events, seed 11), qcd/ (200, seed 22) and qcd-inflight/ (50, seed 22) written by
  pythia_fixtures.py with the commands in docs/HEP-EVENT-WITNESS.md.

Writes four files, each under 200 KB (checked): exact-zmumu (hand-computed, no generator), pythia-zmumu (the largest
clean Z -> mu mu: both muons above 20 GeV pT and eta below 2, dimuon mass 80 to 100, file under 190 KB), pythia-qcd-demo (the
largest HardQCD event under 190 KB, the hero scene) and pythia-qcd-inflight (decays in flight allowed: the event with the
most final-state particles born outside the tracker, under 190 KB). Each carries its source index in provenance.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exact_events as ee  # noqa: E402
import hep_response as hr  # noqa: E402

LIMIT = 190_000


def load(d: Path):
    for f in sorted(d.glob("*.event.json")):
        yield f, json.loads(f.read_text()), f.stat().st_size


def dimuon(ev):
    mus = [p for p in ev["particles"] if p["status"] == 1 and abs(p["pdg"]) == 13]
    pt = lambda p: math.hypot(p["px"], p["py"])  # noqa: E731
    pos, neg = [p for p in mus if p["pdg"] < 0], [p for p in mus if p["pdg"] > 0]
    if not pos or not neg:
        return None
    a, b = max(pos, key=pt), max(neg, key=pt)
    s = {k: a[k] + b[k] for k in ("px", "py", "pz", "E")}
    m = math.sqrt(max(s["E"] ** 2 - s["px"] ** 2 - s["py"] ** 2 - s["pz"] ** 2, 0.0))
    eta = max(abs(math.asinh(p["pz"] / pt(p))) for p in (a, b))
    return m, min(pt(a), pt(b)), eta


def finals(ev):
    return sum(1 for p in ev["particles"] if p["status"] == 1)


def outside(ev):
    t = ev["detector"]["tracker"]
    return sum(1 for p in ev["particles"] if p["status"] == 1 and (math.hypot(*p.get("vertex_m", [0, 0, 0])[:2]) > t["r_max_m"]
                                                                      or abs(p.get("vertex_m", [0, 0, 0])[2]) > t["half_length_m"]))


def write(dest: Path, name: str, ev: dict, source: str):
    ev["id"] = name
    ev["provenance"] = {**ev["provenance"], "source": source}
    text = hr.dump(ev)
    if len(text.encode()) >= 200_000:
        raise SystemExit(f"{name} is {len(text)} bytes: a fixture must stay under 200 KB")
    (dest / f"{name}.event.json").write_text(text)
    print(f"{name}.event.json  {len(text.encode()):>7} bytes  final-state {finals(ev)}  tracks {len(ev['tracks'])}  towers {len(ev['towers'])}  {source}")


def main(bulk: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    write(dest, "exact-zmumu", ee.zmumu(), "hand-computed")
    z = [(finals(e), f, e) for f, e, sz in load(bulk / "zmumu")
         if sz < LIMIT and (d := dimuon(e)) and d[1] > 20 and d[2] < 2.0 and 80 < d[0] < 100]
    n, f, e = max(z, key=lambda r: r[0])
    write(dest, "pythia-zmumu", e, f"{f.name} of the seed-11 zmumu run")
    q = [(finals(e), f, e) for f, e, sz in load(bulk / "qcd") if sz < LIMIT]
    n, f, e = max(q, key=lambda r: r[0])
    write(dest, "pythia-qcd-demo", e, f"{f.name} of the seed-22 qcd run")
    i = [(outside(e), f, e) for f, e, sz in load(bulk / "qcd-inflight") if sz < LIMIT]
    n, f, e = max(i, key=lambda r: r[0])
    write(dest, "pythia-qcd-inflight", e, f"{f.name} of the seed-22 qcd-inflight run ({n} final-state particles born outside the tracker)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
