"""Generate pp events with Pythia 8 and convert them to `loom.hep-event/1` files (needs the `pythia8mc` package).

  venv/bin/python kit/examples/hep/pythia_fixtures.py OUTDIR --process zmumu --events 50 --seed 11
  venv/bin/python kit/examples/hep/pythia_fixtures.py OUTDIR --process qcd --events 200 --seed 22 [--decays-in-flight]

This is the ONE script in the kit that is not standard-library: it imports pythia8mc (pip install pythia8mc; the run
recorded in docs/HEP-EVENT-WITNESS.md used 8.318.3). The witness, the scene builder and the tests never import it; the
fixtures it wrote are committed, so nobody else needs the package.

Conversion (what a reader must know about the record):
- Pythia's native status codes are not HepMC's. The converter maps them: beams (entries 1 and 2) -> 4; every
  isFinal() particle -> 1; a resonance in {Z, W, H, top, tau} that really decays (a daughter has another id) -> 2.
  Everything else (partons, hadrons that decayed, shower copies) is dropped, and the mothers of what is kept are
  re-pointed to the nearest kept ancestor (at most two). The native status is kept as `gen_status`.
- Entry 0 of the Pythia record ("system") is skipped. Positions are mm in Pythia and metres here; times are mm/c and ns here.
- By default tau0 above 10 mm is treated as stable (ParticleDecays:limitTau0), the usual detector-level setting, so
  pions, kaons and K0L reach the detector. --decays-in-flight turns that off, the Pythia default.
- The declared incoming is the sum of the two beam entries (E = 13600, pz = 0 to rounding); a beam proton has E = 6800
  and pz = 6799.999935. Pythia gives the hard-process incoming partons no mother: the beam points to them as daughters,
  so the converter adds that link back.
- Tracks, hits and towers come from hep_response.py: a truth-level toy response, not a detector simulation. What is
  drawn (charged pT, neutral energy, eta) is read from hep-demo-spec.json, so the witness and the converter cannot disagree.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hep_response as hr  # noqa: E402

RESONANCES = {23, 24, 25, 6, 15}


def settings(process: str, seed: int, decays_in_flight: bool, ecm: float, pthat: float) -> list[str]:
    s = [f"Beams:eCM = {ecm}", "Next:numberCount = 0", "Next:numberShowEvent = 0", "Next:numberShowInfo = 0",
         "Next:numberShowProcess = 0", "Random:setSeed = on", f"Random:seed = {seed}"]
    if process == "zmumu":
        s += ["WeakSingleBoson:ffbar2gmZ = on", "23:onMode = off", "23:onIfAny = 13", "PhaseSpace:mHatMin = 66.", "PhaseSpace:mHatMax = 116."]
    elif process == "qcd":
        s += ["HardQCD:all = on", f"PhaseSpace:pTHatMin = {pthat}"]
    else:
        raise SystemExit(f"unknown process {process}")
    if not decays_in_flight:
        s += ["ParticleDecays:limitTau0 = on", "ParticleDecays:tau0Max = 10."]
    return s


def num(v: float):
    return int(v) if float(v).is_integer() else round(float(v), 4)


def particles_of(ev) -> list[dict]:
    """The kept particles of one Pythia event (beams, resonances that decay, final state), mothers local to the list."""
    n = ev.size()
    keep: dict[int, int] = {}
    parts: list[dict] = []
    status_of: dict[int, int] = {}
    for i in range(1, n):
        q = ev[i]
        if i in (1, 2):
            st = 4
        elif q.isFinal():
            st = 1
        elif abs(q.id()) in RESONANCES and any(ev[d].id() != q.id() for d in q.daughterList()):
            st = 2
        else:
            continue
        status_of[i] = st
        keep[i] = len(parts)
        parts.append({"_src": i, "pdg": q.id(), "status": st, "gen_status": q.status(), "charge": num(q.charge())})
    anc: dict[int, list[int]] = {}
    beam_of = {d: b for b in (1, 2) for d in ev[b].daughterList()}

    def nearest(i: int) -> list[int]:
        """Nearest kept ancestors of Pythia entry i (not counting i itself), at most two, in index order."""
        if i in anc:
            return anc[i]
        out: list[int] = []
        for m in (ev[i].motherList() or ([beam_of[i]] if i in beam_of else [])):
            if m <= 0 or m >= i:
                continue
            for a in ([m] if m in keep else nearest(m)):
                if a not in out:
                    out.append(a)
        anc[i] = out[:2]
        return anc[i]

    for p in parts:
        i, q = p.pop("_src"), None
        q = ev[i]
        p.update(px=round(q.px(), 6), py=round(q.py(), 6), pz=round(q.pz(), 6), E=round(q.e(), 6))
        p["mothers"] = sorted(keep[a] for a in nearest(i) if keep[a] < keep[i])
        v = [q.xProd() / 1000.0, q.yProd() / 1000.0, q.zProd() / 1000.0]
        if any(abs(c) > 1e-9 for c in v):
            p["vertex_m"] = [round(c, 6) for c in v]
        if round(q.tProd() * hr.MM_PER_C_NS, 6) > 0:
            p["t_prod_ns"] = round(q.tProd() * hr.MM_PER_C_NS, 6)
    return parts


def merge(subs: list[list[dict]], dz_step: float) -> list[dict]:
    """Pile-up: several collisions in one event, primary vertices spaced dz_step metres apart along z."""
    out: list[dict] = []
    for k, parts in enumerate(subs):
        dz, base = (k - (len(subs) - 1) / 2.0) * dz_step, len(out)
        for p in parts:
            q = dict(p)
            q["mothers"] = [m + base for m in p["mothers"]]
            v = list(p.get("vertex_m", [0.0, 0.0, 0.0]))
            v[2] = round(v[2] + dz, 6)
            if any(abs(c) > 1e-9 for c in v):
                q["vertex_m"] = v
            out.append(q)
    return out


def declared_incoming(parts: list[dict]) -> dict:
    beams = [p for p in parts if p["status"] == 4]
    inc = {k: round(sum(p[k] for p in beams), 6) for k in ("px", "py", "pz", "E")}
    inc["charge"] = num(sum(p["charge"] for p in beams))
    return inc


def convert(ev, event_id: str, provenance: dict, **resp) -> dict:
    parts = particles_of(ev)
    return hr.build_event(event_id, parts, declared_incoming(parts), provenance, **resp)


def main(argv=None) -> int:
    import pythia8mc as pythia8  # noqa: PLC0415

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outdir")
    ap.add_argument("--process", choices=("zmumu", "qcd"), required=True)
    ap.add_argument("--events", type=int, default=50)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--ecm", type=float, default=13600.0)
    ap.add_argument("--pthat", type=float, default=30.0)
    ap.add_argument("--decays-in-flight", action="store_true")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--spec", default=str(Path(__file__).resolve().parent / "hep-demo-spec.json"),
                    help="the drawing cuts (pT, neutral energy, eta) are read from this spec, the same file the witness uses")
    ap.add_argument("--no-hits", action="store_true")
    ap.add_argument("--pileup", type=int, default=1, help="collisions merged into one event (primary vertices 4 cm apart along z)")
    a = ap.parse_args(argv)
    sc = json.loads(Path(a.spec).read_text())["scene"]
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    cfg = settings(a.process, a.seed, a.decays_in_flight, a.ecm, a.pthat)
    py = pythia8.Pythia("", False)
    for line in cfg:
        py.readString(line)
    if not py.init():
        raise SystemExit("Pythia init failed")
    prov = {"generator": f"Pythia {py.settings.parm('Pythia:versionNumber'):.3f}", "kind": "generator", "process": a.process,
            "settings": cfg, "package": "pythia8mc"}
    written = 0
    while written < a.events:
        subs = []
        while len(subs) < a.pileup:
            if py.next():
                subs.append(particles_of(py.event))
        parts = merge(subs, 0.04) if a.pileup > 1 else subs[0]
        name = f"{a.prefix}{a.process}-{written:03d}"
        ev = hr.build_event(name, parts, declared_incoming(parts), {**prov, **({"pileup": a.pileup} if a.pileup > 1 else {})},
                            min_pt=sc["draw_min_pt_gev"], neutral_min_e=sc["draw_min_neutral_e_gev"],
                            eta_max=sc["draw_eta_max"], with_hits=not a.no_hits)
        (out / f"{name}.event.json").write_text(hr.dump(ev))
        written += 1
    print(json.dumps({"written": written, "dir": str(out), "settings": cfg}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
