"""Toy detector response for the hep-event fixtures (standard library only).

Turns a list of truth particles into the drawn-trajectory, hit and tower sections of a `loom.hep-event/1` file:
charged particles get a helix from pT, charge and the solenoid field, neutral visible particles a straight line,
hits sit where a helix crosses a tracker layer, towers are (eta, phi) cells that sum the energy of the visible
particles reaching the barrel calorimeter. This is a TRUTH-LEVEL response: no smearing, no energy loss, no
showers. Muons leave a fixed minimum-ionising deposit (MIP_GEV, a toy number). It exists to give the viewer
something plausible to draw, and the witness something to bind the scene to; it is not a detector simulation.
The scene builder does not import this file (it re-samples the helix itself), so the two do not share an assumption.
"""
from __future__ import annotations

import math

C_GEV_PER_TM = 0.299792458
C_M_PER_NS = 0.299792458
MM_PER_C_NS = 1.0 / 299.792458      # production time: 1 mm/c = 3.3356e-3 ns
MIP_GEV = 0.8
INVISIBLE = {12, 14, 16}
DETECTOR = {"b_field_t": 3.8,
            "tracker": {"r_max_m": 1.1, "half_length_m": 2.8, "layer_radii_m": [0.04, 0.07, 0.11, 0.26, 0.40, 0.60, 0.80, 1.00]},
            "calorimeter": {"r_min_m": 1.3, "r_max_m": 1.8, "half_length_m": 3.2}}
EM = {11, 22}


def helix_point(vertex, phi0, tanl, radius, sense, s):
    x0, y0, z0 = vertex
    if radius is None or sense == 0:
        return (x0 + s * math.cos(phi0), y0 + s * math.sin(phi0), z0 + s * tanl)
    a = phi0 + sense * s / radius
    return (x0 + (radius / sense) * (math.sin(a) - math.sin(phi0)), y0 - (radius / sense) * (math.cos(a) - math.cos(phi0)), z0 + s * tanl)


def layer_hits(vertex, phi0, tanl, radius, sense, tracker, max_turns=1.0):
    """Hit at the first crossing of each layer radius, walking the path in small steps until it leaves the tracker."""
    rmax, half = tracker["r_max_m"], tracker["half_length_m"]
    layers = sorted(tracker["layer_radii_m"])
    s_cap = max_turns * 2 * math.pi * radius if radius else 4.0 * (rmax + half)
    step = min(0.01, radius * 0.01) if radius else 0.01
    hits, k, s, prev = [], 0, 0.0, helix_point(vertex, phi0, tanl, radius, sense, 0.0)
    while s < s_cap and k < len(layers):
        s += step
        p = helix_point(vertex, phi0, tanl, radius, sense, s)
        if math.hypot(p[0], p[1]) > rmax or abs(p[2]) > half:
            break
        rp, rq = math.hypot(prev[0], prev[1]), math.hypot(p[0], p[1])
        while k < len(layers) and rp < layers[k] <= rq:
            f = (layers[k] - rp) / (rq - rp)
            hits.append([prev[i] + f * (p[i] - prev[i]) for i in range(3)])
            k += 1
        while k < len(layers) and layers[k] <= rp:
            k += 1                     # the vertex is already outside this layer
        prev = p
    return hits


def r5(v):
    return round(v, 5)


def build_event(event_id: str, particles: list[dict], incoming: dict, provenance: dict, *,
                min_pt=0.15, eta_max=10.0, neutral_min_e=1.0, with_hits=True, detector=None, hit_pt_min=0.0) -> dict:
    """particles: dicts with pdg, status, charge, px, py, pz, E, mothers, and optionally vertex_m (metres) and t_prod_ns."""
    det = detector or DETECTOR
    b = det["b_field_t"]
    tr, ca = det["tracker"], det["calorimeter"]
    vertices = {i: tuple(p["vertex_m"]) for i, p in enumerate(particles) if "vertex_m" in p}
    t_prod_ns = {i: p["t_prod_ns"] for i, p in enumerate(particles) if "t_prod_ns" in p}
    tracks = []
    for i, p in enumerate(particles):
        if p["status"] != 1 or abs(p["pdg"]) in INVISIBLE:
            continue
        pt = math.hypot(p["px"], p["py"])
        if pt <= 0:
            continue
        eta, phi = math.asinh(p["pz"] / pt), math.atan2(p["py"], p["px"])
        if abs(eta) > eta_max:
            continue
        charged = p["charge"] != 0
        if charged and pt < min_pt:
            continue
        if not charged and p["E"] < neutral_min_e:
            continue
        v = vertices.get(i, (0.0, 0.0, 0.0))
        if math.hypot(v[0], v[1]) > tr["r_max_m"] or abs(v[2]) > tr["half_length_m"]:
            continue                    # born outside the tracker volume: no trajectory inside it to draw
        if charged:
            sense = -1 if (p["charge"] > 0) == (b > 0) else 1
            radius = pt / (C_GEV_PER_TM * abs(b) * abs(p["charge"]))
        else:
            sense, radius = 0, None
        t = {"i": len(tracks), "particle": i, "charge": p["charge"], "pt": float(f"{pt:.6g}"), "eta": round(eta, 5), "phi": round(phi, 5),
             "helix": {"radius_m": None if radius is None else round(radius, 5), "sense": sense}, "t_prod_ns": round(t_prod_ns.get(i, 0.0), 5)}
        if v != (0.0, 0.0, 0.0):
            t["helix"]["vertex_m"] = [r5(c) for c in v]
        if charged and with_hits and pt >= hit_pt_min:
            h = layer_hits(v, math.atan2(p["py"], p["px"]), p["pz"] / pt, radius, sense, tr)
            if h:
                t["hits"] = [[round(c, 4) for c in x] for x in h]
        tracks.append(t)
    # towers: 72 phi bins, eta bins of 0.0873 inside the barrel acceptance
    eta_cal = math.asinh(ca["half_length_m"] / ca["r_min_m"])
    d = 0.0873
    cells: dict[tuple[int, int], dict] = {}
    for i, p in enumerate(particles):
        a = abs(p["pdg"])
        if p["status"] != 1 or a in INVISIBLE:
            continue
        pt = math.hypot(p["px"], p["py"])
        if pt <= 0:
            continue
        eta, phi = math.asinh(p["pz"] / pt), math.atan2(p["py"], p["px"])
        if abs(eta) >= eta_cal - d / 2:
            continue
        e = MIP_GEV if a == 13 else p["E"]
        key = (int(math.floor(eta / d)), int(math.floor((phi + math.pi) / (2 * math.pi / 72))))
        c = cells.setdefault(key, {"E": 0.0, "em": 0.0, "t": 1e9})
        c["E"] += e
        c["em"] += e if a in EM else 0.0
        c["t"] = min(c["t"], t_prod_ns.get(i, 0.0) + ca["r_min_m"] * math.cosh(eta) / C_M_PER_NS)
    towers = []
    for (ie, ip), c in sorted(cells.items()):
        if c["E"] < 0.2:
            continue
        towers.append({"i": len(towers), "eta": round((ie + 0.5) * d, 5), "phi": round(-math.pi + (ip + 0.5) * 2 * math.pi / 72, 5),
                       "E": round(c["E"], 4), "em_frac": round(c["em"] / c["E"], 3), "t_arr_ns": round(c["t"], 4)})
    return {"schema": "loom.hep-event/1", "id": event_id, "provenance": provenance, "detector": det, "incoming": incoming,
            "particles": particles, "tracks": tracks, "towers": towers}


def dump(ev: dict) -> str:
    """Compact JSON, one top-level section per line so a diff of a fixture stays readable."""
    import json
    parts = [f'"{k}":{json.dumps(v, separators=(",", ":"))}' for k, v in ev.items() if k not in ("particles", "tracks", "towers")]
    for k in ("particles", "tracks", "towers"):
        rows = ",\n".join(json.dumps(r, separators=(",", ":")) for r in ev[k])
        parts.append(f'"{k}":[\n{rows}\n]')
    return "{" + ",\n".join(parts) + "}\n"
