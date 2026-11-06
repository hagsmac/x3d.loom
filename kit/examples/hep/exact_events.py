"""Hand-computed and toy events for the hep-event instrument (standard library only, SYNTHETIC and labelled so).

zmumu(): an exact two-body decay Z -> mu- mu+, boosted. The Z is given mass 91.1876 GeV, pT 25 GeV, rapidity 0.4,
azimuth 0.6; in its rest frame each muon has E* = M/2 and p* = sqrt(M^2/4 - m_mu^2) along (theta*, phi*) =
(1.0, 2.0) and the opposite direction; the boost is the closed form E = g (E* + b.p*), p = p* + [(g-1)(p*.n) + g E*|b|] n.
The final-state four-momentum then equals the Z four-momentum to rounding, so this is an EXACT reference for the
conservation check, not a generator output.

toy_shower(n, seed): n charged and neutral particles with deterministic pseudo-random momenta (low-pT loopers and
a few straight high-pT tracks) whose declared incoming is, by construction, their sum. It exercises the scene builder
and the curvature predicates; it is not physics.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hep_response as hr  # noqa: E402

M_Z, M_MU = 91.1876, 0.1056583755


def zmumu() -> dict:
    pt, y, phi = 25.0, 0.4, 0.6
    mt = math.sqrt(M_Z ** 2 + pt ** 2)
    z = {"px": pt * math.cos(phi), "py": pt * math.sin(phi), "pz": mt * math.sinh(y), "E": mt * math.cosh(y)}
    beta = [z[k] / z["E"] for k in ("px", "py", "pz")]
    b2 = sum(c * c for c in beta)
    g = z["E"] / M_Z
    ps = math.sqrt(M_Z ** 2 / 4 - M_MU ** 2)
    th, ph = 1.0, 2.0
    n = [math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)]

    def boost(sign):
        p = [sign * ps * c for c in n]
        bp = sum(a * c for a, c in zip(beta, p))
        e = g * (M_Z / 2 + bp)
        f = (g - 1) * bp / b2 + g * M_Z / 2
        return [p[i] + f * beta[i] for i in range(3)], e

    pm, em = boost(+1)
    pp, ep = boost(-1)
    parts = [
        {"pdg": 23, "status": 2, "charge": 0, "px": z["px"], "py": z["py"], "pz": z["pz"], "E": z["E"], "mothers": []},
        {"pdg": 13, "status": 1, "charge": -1, "px": pm[0], "py": pm[1], "pz": pm[2], "E": em, "mothers": [0]},
        {"pdg": -13, "status": 1, "charge": 1, "px": pp[0], "py": pp[1], "pz": pp[2], "E": ep, "mothers": [0]},
    ]
    inc = {"px": z["px"], "py": z["py"], "pz": z["pz"], "E": z["E"], "charge": 0}
    return hr.build_event("exact-zmumu", parts, inc,
                          {"generator": "hand-computed two-body decay", "kind": "synthetic",
                           "note": "Z at pT 25 GeV, y 0.4, phi 0.6; rest-frame decay angles theta* 1.0, phi* 2.0; M 91.1876, m_mu 0.1056583755"})


def _lcg(seed):
    x = seed & 0xFFFFFFFF
    while True:
        x = (1664525 * x + 1013904223) & 0xFFFFFFFF
        yield x / 4294967296.0


def toy_shower(n: int = 60, seed: int = 7) -> dict:
    """n visible final-state particles around the origin; incoming is declared as their sum (a toy, labelled)."""
    r = _lcg(seed)
    kinds = [(211, 0.13957, 1), (-211, 0.13957, -1), (321, 0.4937, 1), (-321, 0.4937, -1), (2212, 0.9383, 1), (22, 0.0, 0),
             (22, 0.0, 0), (11, 0.000511, -1), (-11, 0.000511, 1), (13, 0.10566, -1), (-13, 0.10566, 1), (2112, 0.9396, 0)]
    parts = []
    for i in range(n):
        pdg, m, q = kinds[int(next(r) * len(kinds))]
        pt = 0.15 + (-math.log(1.0 - next(r) * 0.999)) * (0.6 if i % 9 else 6.0)   # mostly soft, one in nine hard
        eta, phi = (next(r) * 2 - 1) * 2.2, (next(r) * 2 - 1) * math.pi
        px, py, pz = pt * math.cos(phi), pt * math.sin(phi), pt * math.sinh(eta)
        parts.append({"pdg": pdg, "status": 1, "charge": q, "px": round(px, 6), "py": round(py, 6), "pz": round(pz, 6),
                      "E": round(math.sqrt(px * px + py * py + pz * pz + m * m), 6), "mothers": []})
    inc = {k: round(sum(p[k] for p in parts), 6) for k in ("px", "py", "pz", "E")}
    inc["charge"] = sum(p["charge"] for p in parts)
    return hr.build_event(f"toy-shower-{n}-{seed}", parts, inc,
                          {"generator": "deterministic toy (linear congruential)", "kind": "synthetic",
                           "note": "momenta are random; the declared incoming is their sum by construction"},
                          min_pt=0.15, neutral_min_e=0.3)


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.write_text(hr.dump(zmumu()))
    print(out, out.stat().st_size, "bytes")
