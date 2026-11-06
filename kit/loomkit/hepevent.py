"""hep-event: a PLAUSIBILITY witness for collider-event visualisations (a demo witness, not a precision study).

It reads one event file (JSON, defined below) and, when the event names one, the X3D scene that draws it,
and asks the cheap questions a viewer would otherwise never ask: are the units sane, does the charge add
up, do the momenta roughly balance, does every drawn helix bend the way its pT and charge say, does
everything sit inside the detector, is every particle drawn exactly once, and does every drawn track carry
the shader and the per-track attributes that make it look like itself instead of the flat default. Every
predicate raises (need), so `python -O` cannot turn a red event green (law 18). A pass reports what it
read (law 36): particles, tracks, hits, towers, scene shapes, attribute rows.

Scope, stated up front (law 34): physics tolerances are LOOSE on purpose. This is a demo instrument. It says
an event is plausible and that the picture is bound to it; it does not say the physics is right.
Mass shells, resonance windows and calorimeter sum rules were considered and are not here (see the
docs); a precision study would add them as new codes, not by tightening these.

Thresholds live in the spec file (`loom.hep-event-spec/1`), never in this file (law 28). Physical constants
(the 0.2998 in pT = 0.2998 B R) and the six-entry mass list used only to spot a factor-1000 unit error
are constants, graded L (PDG values from memory, to confirm against the 2024 listing before quoting).

EVENT FORMAT (`loom.hep-event/1`, JSON; lengths in metres, momenta and energies in GeV, B in tesla)
  detector   {b_field_t (signed, along +z), tracker{r_max_m, half_length_m, layer_radii_m?},
              calorimeter{r_min_m, r_max_m, half_length_m}}   barrel only: no endcaps
  incoming   {px, py, pz, E, charge}   the declared total entering the event
  particles  [{pdg, status, charge, px, py, pz, E, mothers[], vertex_m?, t_prod_ns?}]   index = position; mothers earlier
             indices. status follows HepMC: 1 final state, 2 decayed or intermediate, 4 beam. vertex_m is the production
             vertex in metres (default the origin): a particle born outside the tracker owes the scene no track.
             Other keys (gen_status, the generator's own code) are carried and ignored
  tracks     [{i, particle, charge, pt, eta, phi, helix{radius_m|null, sense, vertex_m?}, t_prod_ns?, hits?}]
             one entry per DRAWN trajectory: a charged particle's helix, or a neutral particle's straight line
             (radius_m null, sense 0). phi and eta are the direction at the vertex; sense is +1 for a
             counter-clockwise bend seen from +z, -1 clockwise, 0 straight. hits are xyz in metres.
  towers     [{i, eta, phi, E, em_frac?, t_arr_ns?}]   calorimeter cells
  scene      optional relative path of the X3D file that draws this event
  SCENE CONVENTION (read by `read_scene`, no X3D fork needed): each track is a Shape DEF="trk_<i>" holding
  an IndexedLineSet with a Coordinate; each tower is a Shape DEF="twr_<i>" holding an IndexedFaceSet; Transform
  and Switch are honoured; a USE of a trk_ or twr_ shape counts as a second drawing.
  MERGED CONVENTION (look v2; read only when the spec declares scene.merged, otherwise a merged shape is rejected):
  tracks may instead live in Shapes DEF="trkset_<n>" holding one TriangleStripSet, one strip per track. A strip is a
  ribbon: a vertex pair per centreline point, the pair offset by -/+ scene.merged.offset_m (so no triangle has zero
  area; the vertex shader takes the offset off). The centreline (the pair midpoints) is the drawn path, and the strip's
  ident attribute row names its track. Muons may continue past the tracker in Shapes DEF="muext_<n>" (same strip
  form, same ident row), and only muons may. Towers may live in Shapes DEF="twrset_<n>": strips (spikes) whose
  scene.merged.tower_cell attribute row (id, E, em_frac, arrival_s) names the tower; several spikes of one tower in
  one Shape are one drawing.

Stable diagnostics: EVT_PARSE, EVT_SPEC, EVT_UNITS, EVT_CHARGE, EVT_4MOM, EVT_CURVATURE, EVT_SENSE,
EVT_CONTAINMENT, EVT_SCENE_BIJECTION, EVT_SHADER.

Limits (declared before the first real run):
- No GLSL is compiled and nothing is rendered here: EVT_SHADER proves the binding (shader present, its
  attributes supplied with the right count and per-track values, its time uniform routed), not the look.
- Curvature is judged by a least-squares circle through the xy projection of the points (three points fix a circle);
  a path of two points is judged by its sagitta only (it is a straight segment). Multi-turn loopers are fine; a track that is nearly
  straight at the drawn length cannot show its radius.
- The scene reader understands Group, Transform, Switch and the shape/shader nodes above. Script, Inline and
  PROTO nodes cannot be expanded: the spec says reject (default) or count them.
- Tracks are tested against their particle's charge and the field direction, not against energy loss,
  scattering or a real detector response.
"""
from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .core import GateError, need

EVENT_SCHEMA = "loom.hep-event/1"
SPEC_SCHEMA = "loom.hep-event-spec/1"
C_GEV_PER_TM = 0.299792458          # pT[GeV] = 0.2998 * B[T] * R[m] (L)
C_M_PER_NS = 0.299792458            # light, metres per nanosecond (L)
UNITS_MASSES = {11: 0.000511, 13: 0.105658, 211: 0.139570, 321: 0.493677, 2212: 0.938272, 2112: 0.939565}  # GeV, L
TRK, TWR = re.compile(r"^trk_(\d+)$"), re.compile(r"^twr_(\d+)$")
MTRK, MEXT, MTWR = re.compile(r"^trkset_(\d+)$"), re.compile(r"^muext_(\d+)$"), re.compile(r"^twrset_(\d+)$")
# LOD shows one level, picked by distance at run time, so this reader cannot tell which children are drawn: unreadable.
UNREADABLE = {"Inline", "Script", "ProtoDeclare", "ProtoInstance", "ExternProtoDeclare", "IMPORT", "EXPORT", "LOD"}
GROUPS = {"Group", "Transform", "Switch", "Billboard", "Collision", "Anchor", "StaticGroup", "Scene"}
# Child nodes that hold no Shape and no grouping children. Under a group they are skipped; any other node there is
# unreadable, so a grouping node this reader does not model (CADAssembly, LayoutGroup, GeoTransform, ...) fails closed.
LEAVES = {"Viewpoint", "OrthoViewpoint", "NavigationInfo", "Background", "TextureBackground", "Fog", "LocalFog", "WorldInfo",
          "TimeSensor", "TouchSensor", "PlaneSensor", "CylinderSensor", "SphereSensor", "KeySensor", "StringSensor",
          "ProximitySensor", "VisibilitySensor", "TransformSensor", "DirectionalLight", "PointLight", "SpotLight",
          "ScalarInterpolator", "PositionInterpolator", "OrientationInterpolator", "ColorInterpolator", "CoordinateInterpolator",
          "NormalInterpolator", "BooleanSequencer", "IntegerSequencer", "BooleanFilter", "BooleanToggle", "BooleanTrigger",
          "IntegerTrigger", "TimeTrigger", "ParticleSystem"}
# XML statements that are not nodes: they never count as a Switch choice.
STATEMENTS = {"ROUTE", "IS", "connect", "field", "fieldValue"}
EXPAND_LIMIT = 2_000_000   # node visits, USE expansion included: a scene that expands further is refused, not walked


def _named(n) -> bool:
    """A DEF or USE name that the bijection counts: a track, a tower or a merged set of either."""
    return n is not None and any(p.match(n) for p in (TRK, TWR, MTRK, MEXT, MTWR))


def _isnum(v) -> bool:
    return type(v) in (int, float) and math.isfinite(v)


def _isint(v) -> bool:
    return type(v) is int


def _dist(a, b) -> float:
    return math.sqrt(sum((p - q) ** 2 for p, q in zip(a, b)))


# ---------------------------------------------------------------- event

def _bad_constant(name):
    raise GateError("EVT_PARSE", f"non-finite number {name} in the event file")


def parse_event(text: str) -> dict:
    """Parse and structurally validate an event. Everything malformed is EVT_PARSE."""
    try:
        ev = json.loads(text, parse_constant=_bad_constant)
    except (ValueError, RecursionError) as e:
        raise GateError("EVT_PARSE", f"event is not JSON: {str(e)[:120]}") from None
    need(isinstance(ev, dict) and ev.get("schema") == EVENT_SCHEMA, "EVT_PARSE", f"schema must be {EVENT_SCHEMA}")
    det = ev.get("detector")
    need(isinstance(det, dict) and _isnum(det.get("b_field_t")) and det["b_field_t"] != 0, "EVT_PARSE", "detector.b_field_t")
    tr, ca = det.get("tracker"), det.get("calorimeter")
    need(isinstance(tr, dict) and all(_isnum(tr.get(k)) and tr[k] > 0 for k in ("r_max_m", "half_length_m")), "EVT_PARSE", "detector.tracker")
    need(isinstance(ca, dict) and all(_isnum(ca.get(k)) and ca[k] > 0 for k in ("r_min_m", "r_max_m", "half_length_m"))
         and ca["r_min_m"] < ca["r_max_m"], "EVT_PARSE", "detector.calorimeter")
    inc = ev.get("incoming")
    need(isinstance(inc, dict) and all(_isnum(inc.get(k)) for k in ("px", "py", "pz", "E", "charge")), "EVT_PARSE", "incoming")
    parts = ev.get("particles")
    need(isinstance(parts, list) and parts, "EVT_PARSE", "particles: at least one")
    for i, p in enumerate(parts):
        need(isinstance(p, dict) and _isint(p.get("pdg")) and _isint(p.get("status")), "EVT_PARSE", f"particle {i}: pdg/status")
        need(all(_isnum(p.get(k)) for k in ("charge", "px", "py", "pz", "E")), "EVT_PARSE", f"particle {i}: charge or four-momentum")
        m = p.get("mothers", [])
        need(isinstance(m, list) and all(_isint(j) and 0 <= j < i for j in m), "EVT_PARSE",
             f"particle {i}: mothers {m} must be earlier particle indices")
        v = p.get("vertex_m", [0.0, 0.0, 0.0])
        need(isinstance(v, list) and len(v) == 3 and all(_isnum(c) for c in v), "EVT_PARSE", f"particle {i}: vertex_m must be [x, y, z] in metres")
    tracks = ev.get("tracks", [])
    need(isinstance(tracks, list), "EVT_PARSE", "tracks")
    for pos, t in enumerate(tracks):
        need(isinstance(t, dict) and t.get("i") == pos, "EVT_PARSE", f"track at position {pos}: i must equal its position")
        need(_isint(t.get("particle")) and 0 <= t["particle"] < len(parts), "EVT_PARSE", f"track {pos}: particle index")
        need(all(_isnum(t.get(k)) for k in ("charge", "pt", "eta", "phi")) and t["pt"] > 0, "EVT_PARSE", f"track {pos}: charge, pt, eta, phi")
        h = t.get("helix")
        need(isinstance(h, dict) and (h.get("radius_m") is None or (_isnum(h["radius_m"]) and h["radius_m"] > 0))
             and h.get("sense") in (-1, 0, 1), "EVT_PARSE", f"track {pos}: helix")
        v = h.get("vertex_m", [0.0, 0.0, 0.0])
        need(isinstance(v, list) and len(v) == 3 and all(_isnum(c) for c in v), "EVT_PARSE", f"track {pos}: helix.vertex_m")
        hits = t.get("hits", [])
        need(isinstance(hits, list) and all(isinstance(x, list) and len(x) == 3 and all(_isnum(c) for c in x) for x in hits),
             "EVT_PARSE", f"track {pos}: hits must be [x, y, z] in metres")
        need(_isnum(t.get("t_prod_ns", 0.0)) and t.get("t_prod_ns", 0.0) >= 0, "EVT_PARSE", f"track {pos}: t_prod_ns")
    towers = ev.get("towers", [])
    need(isinstance(towers, list), "EVT_PARSE", "towers")
    for pos, w in enumerate(towers):
        need(isinstance(w, dict) and w.get("i") == pos and all(_isnum(w.get(k)) for k in ("eta", "phi", "E")),
             "EVT_PARSE", f"tower {pos}: i, eta, phi, E")
        need(w["E"] >= 0, "EVT_PARSE", f"tower {pos}: negative energy {w['E']}")
    need(ev.get("scene") is None or isinstance(ev["scene"], str), "EVT_PARSE", "scene must be a relative path string")
    return ev


# ---------------------------------------------------------------- spec

def load_spec(spec: dict) -> dict:
    need(isinstance(spec, dict) and spec.get("schema") == SPEC_SCHEMA, "EVT_SPEC", f"schema must be {SPEC_SCHEMA}")

    def sect(name, keys):
        s = spec.get(name)
        need(isinstance(s, dict), "EVT_SPEC", f"missing section {name}")
        for k in keys:
            need(_isnum(s.get(k)) and s[k] >= 0, "EVT_SPEC", f"{name}.{k}: a non-negative number")
        return s

    u = sect("units", ["ratio_log10_tol"])
    need(isinstance(u.get("length_range_m"), list) and len(u["length_range_m"]) == 2 and all(_isnum(v) for v in u["length_range_m"])
         and 0 < u["length_range_m"][0] < u["length_range_m"][1], "EVT_SPEC", "units.length_range_m: [low, high]")
    need(0 < u["ratio_log10_tol"] < 1.0, "EVT_SPEC", "units.ratio_log10_tol must lie in (0, 1) decades")
    p4 = sect("p4", ["abs_tol_gev", "rel_tol"])
    need(p4["rel_tol"] <= 0.05, "EVT_SPEC", "p4.rel_tol above 5 percent is no longer a momentum balance")
    sect("charge", ["abs_tol"])
    c = sect("curvature", ["rel_tol", "abs_tol_per_m", "straight_sagitta_m", "point_resolution_m", "resolvable_sagitta_m"])
    need(0 < c["rel_tol"] <= 0.5, "EVT_SPEC", "curvature.rel_tol must lie in (0, 0.5]")
    need(0 < c["point_resolution_m"] <= 0.01, "EVT_SPEC", "curvature.point_resolution_m must lie in (0, 0.01] metres")
    need(c["resolvable_sagitta_m"] >= c["point_resolution_m"], "EVT_SPEC",
         "curvature.resolvable_sagitta_m must be at least point_resolution_m: a bend smaller than the rounding is not a measurement")
    sect("containment", ["margin_m"])
    s = spec.get("scene")
    if s is not None:
        need(isinstance(s, dict) and isinstance(s.get("required"), bool), "EVT_SPEC", "scene.required: true or false")
        need(s.get("unreadable_nodes") in ("reject", "count"), "EVT_SPEC", "scene.unreadable_nodes: reject or count")
        for k in ("draw_eta_max", "draw_min_pt_gev", "draw_min_neutral_e_gev"):
            need(_isnum(s.get(k)) and s[k] >= 0, "EVT_SPEC", f"scene.{k}")
        need(isinstance(s.get("invisible_pdg"), list) and all(_isint(v) for v in s["invisible_pdg"]), "EVT_SPEC", "scene.invisible_pdg")
        need(_isint(s.get("min_points")) and s["min_points"] >= 2, "EVT_SPEC", "scene.min_points: an integer of at least 2")
        rc = s.get("reach")
        need(isinstance(rc, dict) and all(_isnum(rc.get(k)) and rc[k] > 0 for k in ("start_tol_m", "reach_tol_m", "dir_tol_rad", "pitch_tol_rad")),
             "EVT_SPEC", "scene.reach: {start_tol_m, reach_tol_m, dir_tol_rad, pitch_tol_rad}, all positive")
        need(rc["start_tol_m"] <= 0.05 and rc["reach_tol_m"] <= 0.05 and rc["dir_tol_rad"] <= 0.35 and rc["pitch_tol_rad"] <= 0.35, "EVT_SPEC",
             "scene.reach: start and reach within 5 cm, heading and pitch within 0.35 rad: looser is not the same path")
        sh = s.get("shader")
        if sh is not None:
            need(isinstance(sh, dict) and isinstance(sh.get("time_field"), str) and sh["time_field"], "EVT_SPEC", "scene.shader.time_field")
            ident = sh.get("ident")
            need(isinstance(ident, dict) and isinstance(ident.get("name"), str)
                 and ident.get("layout") == ["id", "charge", "pt", "birth_s"], "EVT_SPEC",
                 "scene.shader.ident: {name, layout: [id, charge, pt, birth_s]}")
            need(_isnum(sh.get("pt_rel_tol")) and 0 < sh["pt_rel_tol"] <= 0.5, "EVT_SPEC", "scene.shader.pt_rel_tol")
            attrs = sh.get("attributes")
            need(isinstance(attrs, list) and attrs and all(isinstance(a, dict) and isinstance(a.get("name"), str)
                                                          and a.get("components") in (1, 2, 3, 4)
                                                          and isinstance(a.get("constant", True), bool) for a in attrs), "EVT_SPEC",
                 "scene.shader.attributes: [{name, components, constant?}]")
            need(any(a["name"] == ident["name"] and a["components"] == 4 for a in attrs), "EVT_SPEC",
                 "scene.shader.attributes must list the ident attribute with 4 components")
            bt = sh.get("birth")
            need(isinstance(bt, dict) and _isnum(bt.get("slow_motion_m_per_s")) and bt["slow_motion_m_per_s"] > 0
                 and _isnum(bt.get("jitter_s")) and 0 <= bt["jitter_s"] <= 1.0, "EVT_SPEC",
                 "scene.shader.birth: {slow_motion_m_per_s > 0, jitter_s in [0, 1]}: birth_s = t_prod * c / slow motion + jitter")
            ar = sh.get("arc")
            need(isinstance(ar, dict) and any(a["name"] == ar.get("name") and a["components"] == 1 for a in attrs)
                 and _isnum(ar.get("abs_tol_m")) and 0 < ar["abs_tol_m"] <= 0.05 and _isnum(ar.get("rel_tol")) and 0 < ar["rel_tol"] <= 0.1, "EVT_SPEC",
                 "scene.shader.arc: {name of a listed 1-component attribute, abs_tol_m in (0, 0.05], rel_tol in (0, 0.1]}")
            spc = sh.get("species")
            need(isinstance(spc, dict) and any(a["name"] == spc.get("name") and a["components"] == 1 for a in attrs)
                 and isinstance(spc.get("by_pdg"), dict) and all(k.isdigit() and _isnum(v) for k, v in spc["by_pdg"].items())
                 and _isnum(spc.get("charged")) and _isnum(spc.get("neutral")), "EVT_SPEC",
                 "scene.shader.species: {name, by_pdg {|pdg|: code}, charged, neutral}: the colour code each particle must carry")
        mg = s.get("merged")
        if mg is not None:
            need(isinstance(mg, dict) and sh is not None, "EVT_SPEC", "scene.merged needs scene.shader (the ident attribute names each strip)")
            off = mg.get("offset_m")
            need(isinstance(off, list) and len(off) == 3 and all(_isnum(v) for v in off) and any(v != 0 for v in off), "EVT_SPEC",
                 "scene.merged.offset_m: [dx, dy, dz], not all zero")
            gap = min(2 * abs(v) for v in off if v != 0)
            need(_isnum(mg.get("offset_tol_m")) and 0 < mg["offset_tol_m"] < gap / 2, "EVT_SPEC",
                 "scene.merged.offset_tol_m must lie in (0, half the smallest pair gap): a looser tolerance cannot tell a ribbon from two paths")
            tc = mg.get("tower_cell")
            need(isinstance(tc, dict) and isinstance(tc.get("name"), str) and tc["name"]
                 and tc.get("layout") == ["id", "E", "em_frac", "arrival_s"], "EVT_SPEC",
                 "scene.merged.tower_cell: {name, layout: [id, E, em_frac, arrival_s], e_rel_tol}")
            need(_isnum(tc.get("e_rel_tol")) and 0 < tc["e_rel_tol"] <= 0.5, "EVT_SPEC", "scene.merged.tower_cell.e_rel_tol must lie in (0, 0.5]")
            need(all(_isnum(tc.get(k)) and 0 < tc[k] <= 0.5 for k in ("cell_deta", "cell_dphi")) and _isnum(tc.get("cell_tol")) and 0 < tc["cell_tol"] <= 0.02,
                 "EVT_SPEC", "scene.merged.tower_cell: cell_deta and cell_dphi in (0, 0.5], cell_tol in (0, 0.02]: each spike stays in its own cell")
            lk = mg.get("look")
            need(isinstance(lk, dict) and isinstance(lk.get("name"), str) and lk.get("track_layout") == ["side", "seed", "drawn_m", "kind"]
                 and lk.get("kinds") == {"charged": 0, "neutral": 1, "extension": 2}, "EVT_SPEC",
                 "scene.merged.look: {name, track_layout [side, seed, drawn_m, kind], kinds {charged 0, neutral 1, extension 2}}")
            ex = mg.get("extensions")
            need(isinstance(ex, dict) and isinstance(ex.get("pdg"), list) and ex["pdg"] and all(_isint(v) and v > 0 for v in ex["pdg"]), "EVT_SPEC",
                 "scene.merged.extensions.pdg: the |pdg| codes that may pass the calorimeter, e.g. [13]")
            for k in ("r_max_m", "half_length_m"):
                need(_isnum(ex.get(k)) and ex[k] > 0, "EVT_SPEC", f"scene.merged.extensions.{k}: a positive number")
            need(_isnum(ex.get("join_tol_m")) and 0 < ex["join_tol_m"] <= 0.1, "EVT_SPEC", "scene.merged.extensions.join_tol_m must lie in (0, 0.1]")
            need(_isnum(ex.get("join_angle_deg")) and 0 < ex["join_angle_deg"] <= 30, "EVT_SPEC", "scene.merged.extensions.join_angle_deg must lie in (0, 30]")
    return spec


# ---------------------------------------------------------------- geometry helpers

def fit_circle(pts):
    """Least-squares circle through (x, y) points (Kasa). Returns (curvature 1/m, sense +1 ccw / -1 cw / 0).
    Collinear input returns curvature 0."""
    n = len(pts)
    need(n >= 3, "EVT_CURVATURE", "a circle fit needs at least 3 points")
    mx, my = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    u = [p[0] - mx for p in pts]
    v = [p[1] - my for p in pts]
    suu, svv, suv = sum(a * a for a in u), sum(b * b for b in v), sum(a * b for a, b in zip(u, v))
    suuu, svvv = sum(a ** 3 for a in u), sum(b ** 3 for b in v)
    suvv, svuu = sum(a * b * b for a, b in zip(u, v)), sum(b * a * a for a, b in zip(u, v))
    det = suu * svv - suv * suv
    cross = sum((pts[i + 1][0] - pts[i][0]) * (pts[i + 2][1] - pts[i + 1][1]) -
                (pts[i + 1][1] - pts[i][1]) * (pts[i + 2][0] - pts[i + 1][0]) for i in range(n - 2))
    sense = 0 if cross == 0 else (1 if cross > 0 else -1)
    if abs(det) <= 1e-14 * (suu + svv) ** 2 or (suu + svv) == 0:
        return 0.0, sense
    uc = 0.5 * (svv * (suuu + suvv) - suv * (svvv + svuu)) / det
    vc = 0.5 * (suu * (svvv + svuu) - suv * (suuu + suvv)) / det
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    return (1.0 / r if r > 0 else 0.0), sense


def expected_curvature(charge: float, pt: float, b_t: float) -> float:
    return abs(charge) * C_GEV_PER_TM * abs(b_t) / pt


def expected_sense(charge: float, b_t: float) -> int:
    """Positive charge turns clockwise seen from +z when B points along +z: sense -1. Neutral: 0."""
    if charge == 0:
        return 0
    return -1 if (charge > 0) == (b_t > 0) else 1


def _helix_pos(t: dict, s: float) -> tuple:
    """The event's own helix (or line) at transverse arc length s from the vertex: phi at the vertex, eta, radius, sense."""
    h = t["helix"]
    x0, y0, z0 = h.get("vertex_m", [0.0, 0.0, 0.0])
    phi0, tanl = t["phi"], math.sinh(t["eta"])
    R, sense = h.get("radius_m"), h.get("sense", 0)
    if R is None or not sense:
        return x0 + s * math.cos(phi0), y0 + s * math.sin(phi0), z0 + s * tanl
    a = phi0 + sense * s / R
    return (x0 + (R / sense) * (math.sin(a) - math.sin(phi0)), y0 - (R / sense) * (math.cos(a) - math.cos(phi0)), z0 + s * tanl)


def _expected_reach(t: dict, det: dict) -> tuple[float, bool]:
    """How far from its vertex, in xy, the event's own helix gets inside the tracker over at most half a turn (the
    largest xy distance a circle reaches), and whether it leaves the tracker within that half turn. This is what a
    drawing must reach: it is taken from the event, never from the drawing being judged."""
    tr = det["tracker"]
    R, sense = t["helix"].get("radius_m"), t["helix"].get("sense", 0)
    straight = R is None or not sense

    def inside(p):
        return math.hypot(p[0], p[1]) <= tr["r_max_m"] and abs(p[2]) <= tr["half_length_m"]

    s_cap = 4.0 * (tr["r_max_m"] + tr["half_length_m"]) if straight else math.pi * R
    n = 400 if straight else 90
    prev, s_end, left = 0.0, s_cap, False
    for j in range(1, n + 1):
        s_ = s_cap * j / n
        if not inside(_helix_pos(t, s_)):
            lo, hi = prev, s_
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                lo, hi = (mid, hi) if inside(_helix_pos(t, mid)) else (lo, mid)
            s_end, left = lo, True
            break
        prev = s_
    if straight:
        return s_end, left
    return 2.0 * R * math.sin(min(s_end / R, math.pi) / 2.0), left


def _extent(xy):
    """Longest distance from the first point to any other, and the index of that point."""
    best, k = 0.0, 0
    for j, q in enumerate(xy):
        d = _dist(xy[0], q)
        if d > best:
            best, k = d, j
    return best, k


def _bend_noise(ext, spec_c) -> float:
    """Curvature (1/m) that rounding of the stored points can fake. A sagitta s over an extent L is kappa = 8 s / L^2;
    a point moved by at most `point_resolution_m` in each coordinate moves the sagitta by at most three times that."""
    return 24.0 * spec_c["point_resolution_m"] / (ext * ext)


def _max_deviation(xy, k):
    """Largest distance of any point from the line through the first point and point k."""
    (x0, y0), (x1, y1) = xy[0], xy[k]
    ln = math.hypot(x1 - x0, y1 - y0)
    if ln == 0:
        return 0.0
    return max(abs((x1 - x0) * (q[1] - y0) - (y1 - y0) * (q[0] - x0)) / ln for q in xy)


def _check_bend(label, pts, track, b_t, spec_c):
    """One drawn or measured path against the track's pT, charge and the field. Raises EVT_CURVATURE / EVT_SENSE.

    The expected sagitta over the path's xy extent decides what can be judged. At least `resolvable_sagitta_m` it is fitted
    (circle, Kasa) and must agree within the tolerance plus the curvature that rounding of the points can fake. Below it
    (a 50 GeV muon crossing a 10 cm tracker, a track at eta 6 that leaves the tracker after a millimetre in xy) the
    fit is noise, measured: the fitted curvature is anywhere from 0 to 1000 times the expected one. Such a path is UNRESOLVED:
    it is judged only as straight within the expected sagitta plus three rounding steps, and the result says so, so a
    pass cannot claim a curvature check it did not make."""
    kexp = expected_curvature(track["charge"], track["pt"], b_t)
    xy = [(p[0], p[1]) for p in pts]
    chord = _dist(xy[0], xy[-1]) if len(xy) >= 2 else 0.0
    if len(xy) < 3:   # two points are a straight segment; three determine a circle and are fitted below
        sag = kexp * chord * chord / 8.0
        need(sag <= spec_c["straight_sagitta_m"], "EVT_CURVATURE",
             f"track {track['i']} {label}: drawn with {len(xy)} points (straight) but pT {track['pt']:.3g} GeV bends it by {sag * 1000:.1f} mm")
        return {"kappa": 0.0, "kappa_expected": kexp, "straight": True, "unresolved": False}
    ext, far = _extent(xy)
    sag_exp = kexp * ext * ext / 8.0
    if sag_exp < spec_c["resolvable_sagitta_m"]:
        dev = _max_deviation(xy, far)
        allow = sag_exp + 3.0 * spec_c["point_resolution_m"]
        need(dev <= allow, "EVT_CURVATURE",
             f"track {track['i']} {label}: pT {track['pt']:.3g} GeV bends this {ext * 1000:.1f} mm path by at most {sag_exp * 1000:.3f} mm "
             f"(below the {spec_c['resolvable_sagitta_m'] * 1000:g} mm that can be fitted) but it departs from a straight line by {dev * 1000:.3f} mm")
        return {"kappa": None, "kappa_expected": kexp, "straight": False, "unresolved": True}
    kfit, sense = fit_circle(xy)
    noise = _bend_noise(ext, spec_c)
    tol = spec_c["rel_tol"] * kexp + spec_c["abs_tol_per_m"] + noise
    need(abs(kfit - kexp) <= tol, "EVT_CURVATURE",
         f"track {track['i']} {label}: curvature {kfit:.4g}/m, pT {track['pt']:.3g} GeV and B {abs(b_t):g} T give {kexp:.4g}/m "
         f"(tolerance {tol:.3g}, of which {noise:.3g} is point rounding)")
    want = expected_sense(track["charge"], b_t)
    if want != 0 and sag_exp > spec_c["straight_sagitta_m"]:
        need(sense == want, "EVT_SENSE", f"track {track['i']} {label}: bends {'ccw' if sense > 0 else 'cw'}, charge {track['charge']:+g} in B {b_t:+g} T bends {'ccw' if want > 0 else 'cw'}")
    return {"kappa": kfit, "kappa_expected": kexp, "straight": False, "unresolved": False}


# ---------------------------------------------------------------- scene reader

def _floats(s: str | None) -> list[float]:
    out = []
    for tok in re.split(r"[\s,]+", (s or "").strip()):
        if tok:
            try:
                v = float(tok)
            except ValueError:
                raise GateError("EVT_PARSE", f"scene: {tok[:20]!r} is not a number") from None
            need(math.isfinite(v), "EVT_PARSE", "scene: non-finite number")
            out.append(v)
    return out


def _mfstring(s: str | None) -> list[str]:
    """X3D MFString: tokens in double or single quotes with backslash escapes; an unquoted string is one token."""
    s = (s or "").strip()
    if not s:
        return []
    if s[0] not in "\"'":
        return [s]
    out, i = [], 0
    while i < len(s):
        if s[i] in "\"'":
            q, j, buf = s[i], i + 1, []
            while j < len(s) and s[j] != q:
                if s[j] == "\\" and j + 1 < len(s):
                    j += 1
                buf.append(s[j])
                j += 1
            need(j < len(s), "EVT_PARSE", "scene: unterminated MFString")
            out.append("".join(buf))
            i = j + 1
        else:
            i += 1
    return out


def _rot(axis, angle):
    n = math.sqrt(sum(c * c for c in axis))
    if n == 0 or angle == 0:
        return [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]
    x, y, z = (c / n for c in axis)
    c, s = math.cos(angle), math.sin(angle)
    t = 1 - c
    return [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
            [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
            [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]


def _mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _mv(a, v):
    return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


def _transform(el):
    """Local affine map of a Transform as (A, t): x' = A x + t, from translation, rotation, scale, scaleOrientation, center."""
    def vec(name, default, n):
        v = _floats(el.get(name)) if el.get(name) is not None else list(default)
        need(len(v) == n, "EVT_PARSE", f"scene: Transform.{name} needs {n} numbers")
        return v
    t, c, s = vec("translation", (0, 0, 0), 3), vec("center", (0, 0, 0), 3), vec("scale", (1, 1, 1), 3)
    r, so = vec("rotation", (0, 0, 1, 0), 4), vec("scaleOrientation", (0, 0, 1, 0), 4)
    R, SO = _rot(r[:3], r[3]), _rot(so[:3], so[3])
    SOt = [[SO[j][i] for j in range(3)] for i in range(3)]
    S = [[s[0], 0, 0], [0, s[1], 0], [0, 0, s[2]]]
    A = _mm(_mm(_mm(R, SO), S), SOt)
    ac = _mv(A, c)
    return A, [t[i] + c[i] - ac[i] for i in range(3)]


def _compose(parent, local):
    (Ap, tp), (Al, tl) = parent, local
    return _mm(Ap, Al), [a + b for a, b in zip(_mv(Ap, tl), tp)]


def _apply(m, pts):
    A, t = m
    return [tuple(sum(A[i][k] * p[k] for k in range(3)) + t[i] for i in range(3)) for p in pts]


IDENT = ([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]], [0.0, 0.0, 0.0])


def read_scene(text: str, merged: dict | None = None, ident: str | None = None) -> dict:
    """Read an X3D XML scene without the X3D fork. Returns what is drawn and how it is bound.

    merged (scene.merged of the spec) and ident (the spec's ident attribute name) switch on the merged convention;
    without them a trkset_/muext_/twrset_ shape is recorded as a bad DEF, so it can never be skipped silently.

    tracks[k]  : count (DEF + USE appearances), visible, points (world, in coordIndex order), shader binding,
                 vertex attributes; towers[k]: count, visible, points. Everything else is only counted.
    Raises EVT_PARSE for XML that does not parse, a USE before its DEF, a malformed number list, or a
    coordIndex that points outside its Coordinate."""
    need(isinstance(text, str) and text.strip(), "EVT_PARSE", "scene: empty")
    need("<!ENTITY" not in text, "EVT_PARSE", "scene: entity declarations are not read")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise GateError("EVT_PARSE", f"scene is not XML: {e}") from None
    need(root.tag.rsplit("}", 1)[-1] == "X3D", "EVT_PARSE", "scene: root element is not X3D")
    defs: dict[str, ET.Element] = {}
    for el in root.iter():
        d, u = el.get("DEF"), el.get("USE")
        if u is not None:
            need(u in defs, "EVT_PARSE", f"scene: USE {u} before any DEF of that name")
        if d is not None and d not in defs:
            defs[d] = el
    scene = {"tracks": {}, "towers": {}, "extensions": {}, "merged_shapes": 0, "bad_def": [], "unreadable": {}, "shapes": 0, "routes": [], "defs": defs,
             "timesensors": {n for n, e in defs.items() if e.tag == "TimeSensor"},
             "shader_defs": {n for n, e in defs.items() if e.tag == "ComposedShader"},
             "components": [c.get("name") for c in root.iter("component")], "profile": root.get("profile"),
             "version": root.get("version"), "bytes": len(text), "transforms": 0}
    for r in root.iter("ROUTE"):
        scene["routes"].append((r.get("fromNode"), r.get("fromField"), r.get("toNode"), r.get("toField")))

    def resolve(el):
        u = el.get("USE")
        return defs[u] if u is not None else el

    def shader_info(shape):
        ap = next((resolve(c) for c in shape if c.tag == "Appearance"), None)
        cs = next((resolve(c) for c in (ap if ap is not None else []) if c.tag == "ComposedShader"), None)
        if cs is None:
            return {"bound": False, "parts": [], "fields": [], "def": None, "appearance": ap is not None}
        parts = [(p.get("type", ""), _mfstring(p.get("url")), (p.text or "").strip()) for p in cs if p.tag == "ShaderPart"]
        fields = [f.get("name") for f in cs if f.tag == "field"]
        return {"bound": True, "parts": parts, "fields": fields, "def": cs.get("DEF"), "appearance": True}

    def geometry(shape, kind):
        g = next((resolve(c) for c in shape if c.tag == kind), None)
        if g is None:
            return None
        co = next((resolve(c) for c in g if c.tag == "Coordinate"), None)
        pts_flat = _floats(co.get("point")) if co is not None else []
        need(len(pts_flat) % 3 == 0, "EVT_PARSE", f"scene: {kind} Coordinate.point is not a list of xyz triples")
        pts = [tuple(pts_flat[i:i + 3]) for i in range(0, len(pts_flat), 3)]
        idx = [int(v) for v in _floats(g.get("coordIndex"))]
        need(all(v == -1 or 0 <= v < len(pts) for v in idx), "EVT_PARSE", f"scene: {kind} coordIndex points outside its Coordinate")
        attrs = {}
        for c in g:
            if c.tag == "FloatVertexAttribute":
                nc = c.get("numComponents", "4")
                need(nc in ("1", "2", "3", "4"), "EVT_PARSE", "scene: FloatVertexAttribute.numComponents")
                attrs[c.get("name", "")] = (int(nc), _floats(c.get("value")))
        return {"points": pts, "index": idx, "attrs": attrs, "has_coordinate": co is not None}

    def strips(shape, name, row_name):
        """The ribbons of a merged shape: [(strip index, id, centre points, centre rows, odd-vertex rows)], or None
        (and a bad DEF) when the shape is not in the declared form."""
        g = next((resolve(c) for c in shape if c.tag == "TriangleStripSet"), None)
        if g is None:
            scene["bad_def"].append(f"{name} is a merged shape without a TriangleStripSet")
            return None
        co = next((resolve(c) for c in g if c.tag == "Coordinate"), None)
        flat = _floats(co.get("point")) if co is not None else []
        need(len(flat) % 3 == 0, "EVT_PARSE", f"scene: {name} Coordinate.point is not a list of xyz triples")
        pts = [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]
        counts = [int(v) for v in _floats(g.get("stripCount"))]
        need(all(c >= 0 for c in counts) and sum(counts) == len(pts), "EVT_PARSE",
             f"scene: {name} stripCount adds up to {sum(counts)} vertices, its Coordinate has {len(pts)}")
        attrs = {}
        for c in g:
            if c.tag == "FloatVertexAttribute":
                nc = c.get("numComponents", "4")
                need(nc in ("1", "2", "3", "4"), "EVT_PARSE", "scene: FloatVertexAttribute.numComponents")
                attrs[c.get("name", "")] = (int(nc), _floats(c.get("value")))
        if row_name not in attrs:
            scene["bad_def"].append(f"{name} carries no {row_name} attribute, so its strips name no track or tower")
            return None
        rnc, rvals = attrs[row_name]
        need(rnc == 4 and len(rvals) == 4 * len(pts), "EVT_SHADER",
             f"{name}: attribute {row_name} has numComponents {rnc} and {len(rvals)} values, expected 4 and {4 * len(pts)}")
        off = merged["offset_m"]
        tol = merged["offset_tol_m"]
        side_name = merged["look"]["name"]
        need(side_name in attrs and attrs[side_name][0] >= 1 and len(attrs[side_name][1]) == attrs[side_name][0] * len(pts), "EVT_SHADER",
             f"{name}: no {side_name} attribute with one row per vertex: the shader could not take the ribbon offset off")
        snc, svals = attrs[side_name]
        out, start = [], 0
        for j, cnt in enumerate(counts):
            vs = list(range(start, start + cnt))
            start += cnt
            if cnt % 2:
                scene["bad_def"].append(f"{name} strip {j} has {cnt} vertices: a ribbon has a vertex pair per point")
                continue
            if cnt < 4:
                scene["bad_def"].append(f"{name} strip {j} has {cnt} vertices: a ribbon needs two vertex pairs at least, or it draws nothing")
                continue
            rid = rvals[4 * vs[0]] if vs else -1.0
            if not (rid >= 0 and float(rid).is_integer()):
                scene["bad_def"].append(f"{name} strip {j}: {row_name}.id is {rid:g}, not a track or tower index")
                continue
            if any(rvals[4 * v] != rid for v in vs):
                scene["bad_def"].append(f"{name} strip {j}: {row_name}.id changes along the strip: one strip, one {'tower' if row_name != ident else 'track'}")
                continue
            for i, v in enumerate(vs):
                want = -1.0 if i % 2 == 0 else 1.0
                need(svals[snc * v] == want, "EVT_SHADER",
                     f"{name} strip {j} (id {int(rid)}): {side_name}.side is {svals[snc * v]:g} on vertex {i}, the convention says {want:+g} "
                     "(the shader takes side * offset_m off, so the ribbon would not sit on the drawn path)")
            centre, even_rows, odd_rows = [], {}, {}
            for i in range(0, cnt, 2):
                a, b = pts[vs[i]], pts[vs[i + 1]]
                if any(abs((b[q] - a[q]) - 2 * off[q]) > tol for q in range(3)):
                    scene["bad_def"].append(f"{name} strip {j} (id {int(rid)}): vertex pair {i // 2} is not offset by the declared "
                                            "-/+ offset_m, so the pair midpoints are not the drawn path")
                    centre = None
                    break
                centre.append(tuple(0.5 * (a[q] + b[q]) for q in range(3)))
                for an, (nc, vals) in attrs.items():
                    even_rows.setdefault(an, (nc, []))[1].extend(vals[nc * vs[i]:nc * (vs[i] + 1)])
                    odd_rows.setdefault(an, (nc, []))[1].extend(vals[nc * vs[i + 1]:nc * (vs[i + 1] + 1)])
            if centre is None:
                continue
            out.append((j, int(rid), centre, even_rows, odd_rows, [pts[v] for v in vs]))
        return out

    def merged_shape(ch, name, is_def, vis, cm):
        shape = ch if is_def else defs[name]
        if shape.tag != "Shape":
            scene["bad_def"].append(f"{name} is a {shape.tag}, not a Shape")
            return
        if merged is None or ident is None:
            scene["bad_def"].append(f"{name} is a merged shape, but the spec declares no scene.merged convention to read it by")
            return
        scene["merged_shapes"] += 1
        is_twr = MTWR.match(name) is not None
        got = strips(shape, name, merged["tower_cell"]["name"] if is_twr else ident)
        if got is None:
            return
        info = shader_info(shape)
        scene.setdefault("merged_info", {})[name] = info
        if is_twr:
            per: dict[int, list] = {}
            for j, k, centre, ev_rows, od_rows, raw in got:
                per.setdefault(k, []).append((ev_rows, od_rows, raw, centre))
            for k, parts in per.items():
                ent = scene["towers"].setdefault(k, {"def": 0, "use": 0, "visible": False, "kind": "Shape", "points": None, "merged": name})
                ent["def" if is_def else "use"] += 1
                ent["visible"] = ent["visible"] or vis
                if ent["points"] is None:
                    raw_all = [p for _e, _o, raw, _c in parts for p in raw]
                    ev_all, od_all = {}, {}
                    for ev_rows, od_rows, _raw, _c in parts:
                        for rows, acc in ((ev_rows, ev_all), (od_rows, od_all)):
                            for an, (nc, vals) in rows.items():
                                acc.setdefault(an, (nc, []))[1].extend(vals)
                    ent["points"] = _apply(cm, raw_all)
                    ent["geometry"] = {"points": raw_all, "index": [], "attrs": ev_all, "pair_attrs": od_all, "has_coordinate": True}
                    ent["spikes"] = [_apply(cm, c) for _e, _o, _r, c in parts]
                    ent["shader"] = info
            return
        store_ext = MEXT.match(name) is not None
        for j, k, centre, ev_rows, od_rows, _raw in got:
            geo = {"points": centre, "index": [], "attrs": ev_rows, "pair_attrs": od_rows, "has_coordinate": True}
            if store_ext:
                scene["extensions"].setdefault(k, []).append({"points": _apply(cm, centre), "geometry": geo, "shader": info,
                                                               "visible": vis, "shape": name, "strip": j})
                continue
            ent = scene["tracks"].setdefault(k, {"def": 0, "use": 0, "visible": False, "kind": "Shape", "points": None, "merged": name})
            ent["def" if is_def else "use"] += 1
            ent["visible"] = ent["visible"] or vis
            if ent["points"] is None:
                ent["points"] = _apply(cm, centre)
                ent["geometry"] = geo
                ent["shader"] = info

    parent = {c: p for p in root.iter() for c in p}
    owned: dict[int, str] = {}    # id(element) -> the named shape whose geometry it is part of (its Appearance is shared, not owned)
    for el in root.iter():
        if _named(el.get("DEF")):
            for c in el:
                if c.tag != "Appearance":
                    for q in c.iter():
                        owned[id(q)] = el.get("DEF")
    seen_def: set[int] = set()
    seen_use: set[int] = set()
    budget = [EXPAND_LIMIT]

    def is_meta(c):
        return c.tag.startswith("Metadata") or c.get("containerField") == "metadata"

    def walk(el, m, visible, reuse=False, stack=(), bill=False):
        """el's children. reuse: el is reached through a USE, so every named DEF below it is a further drawing.
        bill: el is inside a Billboard, which turns its children toward the viewer at run time (no fixed transform)."""
        in_shape = el.tag == "Shape"
        which, choice = None, -1
        if el.tag == "Switch":
            w_ = _floats(el.get("whichChoice", "-1"))
            which = int(w_[0]) if w_ else -1
        for ch in list(el):
            budget[0] -= 1
            need(budget[0] > 0, "EVT_PARSE", f"scene: expands to more than {EXPAND_LIMIT} nodes through USE; it is refused, not walked")
            d, u = ch.get("DEF"), ch.get("USE")
            node = defs[u] if u is not None else ch      # a USE is read through the node it names, its fields included
            tag = node.tag
            vis, cm = visible, m
            if el.tag == "Switch" and tag not in STATEMENTS and not is_meta(ch):
                choice += 1                               # choices count nodes only: metadata and ROUTEs are not choices
                vis = visible and choice == which
            if el.tag == "Collision" and ch.get("containerField") == "proxy":
                vis = False                               # a Collision proxy is used for collision and never rendered
            if tag == "Transform":
                cm = _compose(m, _transform(node))
                scene["transforms"] += 1
            if not in_shape:
                if tag in UNREADABLE:
                    scene["unreadable"][tag] = scene["unreadable"].get(tag, 0) + 1
                elif tag not in GROUPS and tag != "Shape" and tag not in LEAVES and tag not in STATEMENTS and not is_meta(ch):
                    scene["unreadable"][tag] = scene["unreadable"].get(tag, 0) + 1
            if u is not None:
                seen_use.add(id(ch))
                if id(node) in owned:
                    scene["bad_def"].append(f"a USE of {u} ({tag}) reuses the geometry of {owned[id(node)]}: it would be drawn a second time")
            if _named(d):
                seen_def.add(id(ch))
            if bill and (_named(d) or _named(u)):
                scene["bad_def"].append(f"{d or u} is inside a Billboard, which turns it toward the viewer at run time: its drawn path is not fixed")
            for name, is_def in ((d, not reuse), (u, False)):
                if name is None:
                    continue
                if MTRK.match(name) or MEXT.match(name) or MTWR.match(name):
                    merged_shape(ch if is_def else defs[name], name, is_def, vis, cm)
                    continue
                for pat, store in ((TRK, scene["tracks"]), (TWR, scene["towers"])):
                    mt = pat.match(name)
                    if not mt:
                        continue
                    k = int(mt.group(1))
                    shape = ch if is_def else defs[name]
                    ent = store.setdefault(k, {"def": 0, "use": 0, "visible": False, "kind": shape.tag, "points": None})
                    ent["def" if is_def else "use"] += 1
                    ent["visible"] = ent["visible"] or vis
                    if is_def and ent["points"] is None and tag == "Shape":
                        gk = "IndexedLineSet" if store is scene["tracks"] else "IndexedFaceSet"
                        g = geometry(ch, gk)
                        ent["geometry"] = g
                        ent["points"] = _apply(cm, g["points"]) if g else None
                        ent["shader"] = shader_info(ch)
                    if is_def and tag != "Shape":
                        scene["bad_def"].append(f"{name} is a {tag}, not a Shape")
            if tag == "Shape" and u is None and not reuse:
                scene["shapes"] += 1
            if tag in GROUPS | {"Shape"} and not in_shape:
                if u is not None:
                    need(id(node) not in stack, "EVT_PARSE", f"scene: USE {u} sits inside its own DEF (a cycle)")
                walk(node, cm, vis, reuse or u is not None, stack + (id(node),), bill or tag == "Billboard")

    sc = next((c for c in root if c.tag == "Scene"), None)
    need(sc is not None, "EVT_PARSE", "scene: no <Scene> element")
    walk(sc, IDENT, True)
    # every named DEF and every USE that could draw a named shape must have been met by the walk, or it is uncounted
    for el in root.iter():
        d, u = el.get("DEF"), el.get("USE")
        if _named(d) and id(el) not in seen_def:
            scene["bad_def"].append(f"{d} sits inside a {parent[el].tag}, where this reader does not look: it cannot be counted")
        if u is not None and id(el) not in seen_use:
            tgt = defs[u]
            if id(tgt) in owned or any(_named(q.get("DEF")) for q in tgt.iter()):
                scene["bad_def"].append(f"a USE of {u} sits inside a {parent[el].tag}, where this reader does not look: it cannot be counted")
    return scene


# ---------------------------------------------------------------- the checks

def _check_units(ev, spec, scene):
    u = spec["units"]
    lo, hi = u["length_range_m"]
    det = ev["detector"]
    need(1e-3 <= abs(det["b_field_t"]) <= 100.0, "EVT_UNITS",
         f"detector.b_field_t = {det['b_field_t']:g} T is outside 0.001 to 100 T: gauss or kilogauss read as tesla?")
    for name, v in (("tracker.r_max_m", det["tracker"]["r_max_m"]), ("tracker.half_length_m", det["tracker"]["half_length_m"]),
                    ("calorimeter.r_max_m", det["calorimeter"]["r_max_m"]), ("calorimeter.half_length_m", det["calorimeter"]["half_length_m"])):
        need(lo <= v <= hi, "EVT_UNITS", f"detector.{name} = {v} is outside {lo} to {hi} m: millimetres read as metres?")
    ratios = []
    for p in ev["particles"]:
        m0 = UNITS_MASSES.get(abs(p["pdg"]))
        if p["status"] == 1 and m0 and p["E"] > 0:
            m2 = p["E"] ** 2 - p["px"] ** 2 - p["py"] ** 2 - p["pz"] ** 2
            if m2 > 1e-8 * p["E"] ** 2:  # judge only where m/E > 1e-4: below that rounding swamps the mass
                ratios.append(math.log10(math.sqrt(m2) / m0))
    if ratios:
        med = sorted(ratios)[len(ratios) // 2]
        need(abs(abs(med) - 3.0) > u["ratio_log10_tol"], "EVT_UNITS",
             f"median mass of known final-state particles is 10^{med:+.2f} times its PDG value: MeV read as GeV, or the reverse?")
    jud = 0
    for t in ev.get("tracks", []):
        r = t["helix"].get("radius_m")
        if r is not None and t["charge"] != 0:
            jud += 1
            q = r / (t["pt"] / (C_GEV_PER_TM * abs(det["b_field_t"])))
            need(math.isfinite(q) and q > 0, "EVT_UNITS", f"track {t['i']}: helix radius {r:g} m and pT {t['pt']:g} GeV give no finite radius ratio")
            lr = math.log10(q)
            need(abs(abs(lr) - 3.0) > u["ratio_log10_tol"], "EVT_UNITS",
                 f"track {t['i']}: helix radius is 10^{lr:+.2f} times what pT and B give: metres and millimetres mixed?")
    out = {"mass_scale_judged": len(ratios), "radius_scale_judged": jud}
    if scene is not None:
        rmax = max((math.hypot(p[0], p[1]) for k, t in scene["tracks"].items() if t["points"] for p in t["points"]), default=0.0)
        if scene["tracks"]:
            need(math.isfinite(rmax) and rmax > 0, "EVT_UNITS", "scene: every drawn track point sits on the beam axis (a scale of 0?): nothing is drawn")
            lr = math.log10(rmax / det["tracker"]["r_max_m"])
            need(abs(abs(lr) - 3.0) > u["ratio_log10_tol"], "EVT_UNITS",
                 f"scene extent is 10^{lr:+.2f} times the tracker radius: the scene is in the wrong unit (mm?)")
            need(lr >= -1.0, "EVT_UNITS", f"scene extent is 10^{lr:+.2f} times the tracker radius: the drawing is shrunk, not the detector")
            out["scene_extent_ratio_log10"] = round(lr, 3)
    return out


def _check_conservation(ev, spec):
    parts, inc = ev["particles"], ev["incoming"]
    final = [p for p in parts if p["status"] == 1]
    need(final, "EVT_4MOM", "no final-state particles (status 1)")
    ctol = spec["charge"]["abs_tol"]
    qsum = sum(p["charge"] for p in final)
    need(abs(qsum - inc["charge"]) <= ctol, "EVT_CHARGE", f"final-state charge {qsum:+g}, declared incoming {inc['charge']:+g}")
    for t in ev.get("tracks", []):
        pc = parts[t["particle"]]["charge"]
        need(abs(t["charge"] - pc) <= ctol, "EVT_CHARGE", f"track {t['i']} has charge {t['charge']:+g} but its particle {t['particle']} has {pc:+g}")
    tol = spec["p4"]["abs_tol_gev"] + spec["p4"]["rel_tol"] * abs(inc["E"])
    s = {k: sum(p[k] for p in final) for k in ("px", "py", "pz", "E")}
    res = {k: s[k] - inc[k] for k in s}
    need(all(abs(v) <= tol for v in res.values()), "EVT_4MOM",
         "final state minus declared incoming: " + ", ".join(f"d{k}={v:+.4g}" for k, v in res.items()) + f" GeV (tolerance {tol:.3g})")
    beams = [p for p in parts if p["status"] == 4]
    if beams:
        for k in s:
            need(abs(sum(p[k] for p in beams) - inc[k]) <= tol, "EVT_4MOM", f"declared incoming {k} differs from the beam particles")
    return {"final_state": len(final), "charge_sum": qsum, "p4_residual_gev": {k: round(v, 9) for k, v in res.items()}, "p4_tolerance_gev": tol,
            "beams": len(beams)}


def _check_tracks(ev, spec):
    b, sc = ev["detector"]["b_field_t"], spec["curvature"]
    judged = {"declared": 0, "hits": 0, "straight_hits": 0, "unresolved_hits": 0}
    for t in ev.get("tracks", []):
        kexp = expected_curvature(t["charge"], t["pt"], b)
        r = t["helix"].get("radius_m")
        if r is None:
            need(t["charge"] == 0, "EVT_CURVATURE", f"track {t['i']}: charged ({t['charge']:+g}) but declared straight (helix.radius_m is null)")
        else:
            judged["declared"] += 1
            tol = sc["rel_tol"] * kexp + sc["abs_tol_per_m"]
            need(abs(1.0 / r - kexp) <= tol, "EVT_CURVATURE",
                 f"track {t['i']}: declared helix radius {r:.4g} m, pT {t['pt']:.3g} GeV in {abs(b):g} T gives {1 / kexp if kexp else math.inf:.4g} m")
            need(t["helix"]["sense"] == expected_sense(t["charge"], b), "EVT_SENSE",
                 f"track {t['i']}: declared sense {t['helix']['sense']:+d}, charge {t['charge']:+g} in B {b:+g} T gives {expected_sense(t['charge'], b):+d}")
        hits = t.get("hits", [])
        if len(hits) >= 3:
            res = _check_bend("hits", hits, t, b, sc)
            judged["hits"] += 1
            judged["straight_hits"] += 1 if res["straight"] else 0
            judged["unresolved_hits"] += 1 if res["unresolved"] else 0
    return judged


def _in_tracker(p, det, margin):
    return math.hypot(p[0], p[1]) <= det["tracker"]["r_max_m"] + margin and abs(p[2]) <= det["tracker"]["half_length_m"] + margin


def _check_containment(ev, spec):
    det, m = ev["detector"], spec["containment"]["margin_m"]
    n = 0
    for t in ev.get("tracks", []):
        for pt in t.get("hits", []) + [t["helix"].get("vertex_m", [0.0, 0.0, 0.0])]:
            n += 1
            need(_in_tracker(pt, det, m), "EVT_CONTAINMENT",
                 f"track {t['i']}: point ({pt[0]:.3f}, {pt[1]:.3f}, {pt[2]:.3f}) m is outside the tracker (r {det['tracker']['r_max_m']} m, |z| {det['tracker']['half_length_m']} m)")
    ca = det["calorimeter"]
    eta_max = math.asinh(ca["half_length_m"] / ca["r_min_m"])
    for w in ev.get("towers", []):
        need(abs(w["eta"]) <= eta_max and abs(w["phi"]) <= math.pi + 1e-9, "EVT_CONTAINMENT",
             f"tower {w['i']}: eta {w['eta']:.3f}, phi {w['phi']:.3f} is outside the barrel calorimeter (|eta| <= {eta_max:.3f})")
    return {"points_checked": n, "calorimeter_eta_max": round(eta_max, 4)}


def _drawable(ev, sc):
    """Particles the scene spec says must be drawn: visible final-state, produced inside the tracker, inside the eta cut
    and above its energy cut. A particle born outside the tracker volume (a decay in flight beyond it) has no trajectory
    in the volume that is drawn, so it is not owed a track."""
    out = []
    trk = ev["detector"]["tracker"]
    for i, p in enumerate(ev["particles"]):
        if p["status"] != 1 or abs(p["pdg"]) in sc["invisible_pdg"]:
            continue
        v = p.get("vertex_m", [0.0, 0.0, 0.0])
        if math.hypot(v[0], v[1]) > trk["r_max_m"] or abs(v[2]) > trk["half_length_m"]:
            continue
        pt = math.hypot(p["px"], p["py"])
        if pt <= 0:
            continue
        eta = math.asinh(p["pz"] / pt)
        if abs(eta) > sc["draw_eta_max"]:
            continue
        if (p["charge"] != 0 and pt >= sc["draw_min_pt_gev"]) or (p["charge"] == 0 and p["E"] >= sc["draw_min_neutral_e_gev"]):
            out.append(i)
    return out


def _check_bijection(ev, sc, scene):
    if scene["unreadable"]:
        need(sc["unreadable_nodes"] == "count", "EVT_PARSE",
             "scene uses nodes this reader cannot expand: " + ", ".join(f"{k} x{v}" for k, v in sorted(scene["unreadable"].items())))
    need(not scene["bad_def"], "EVT_SCENE_BIJECTION", "; ".join(scene["bad_def"][:3]))
    tracks, towers = ev.get("tracks", []), ev.get("towers", [])
    for kind, drawn, have in (("track", scene["tracks"], {t["i"] for t in tracks}), ("tower", scene["towers"], {w["i"] for w in towers})):
        pre = "trk_" if kind == "track" else "twr_"
        for k, ent in sorted(drawn.items()):
            n = ent["def"] + ent["use"]
            need(n == 1, "EVT_SCENE_BIJECTION", f"{pre}{k} is drawn {n} times ({ent['def']} DEF, {ent['use']} USE): each must appear exactly once")
            need(k in have, "EVT_SCENE_BIJECTION", f"scene draws {pre}{k}, which maps to no {kind} of the event")
            need(ent["visible"], "EVT_SCENE_BIJECTION", f"{pre}{k} is in the scene but hidden (a Switch that does not select it, or a Collision proxy)")
            need(ent["points"] is not None and ent.get("geometry") and ent["geometry"]["has_coordinate"], "EVT_SCENE_BIJECTION",
                 f"{pre}{k} has no {'IndexedLineSet' if kind == 'track' else 'IndexedFaceSet'} with a Coordinate: nothing is drawn")
        missing = sorted(have - set(drawn))
        need(not missing, "EVT_SCENE_BIJECTION", f"event {kind}s not drawn: " + ", ".join(f"{pre}{k}" for k in missing[:6]) + (" ..." if len(missing) > 6 else ""))
    for k, ent in scene["tracks"].items():
        need(len(ent["points"]) >= sc["min_points"], "EVT_SCENE_BIJECTION", f"trk_{k} has {len(ent['points'])} points, spec needs {sc['min_points']}")
    mapped: dict[int, int] = {}
    for t in tracks:
        p = ev["particles"][t["particle"]]
        need(p["status"] == 1, "EVT_SCENE_BIJECTION", f"track {t['i']} maps to particle {t['particle']}, which is not a final-state particle")
        need(t["particle"] not in mapped, "EVT_SCENE_BIJECTION",
             f"tracks {mapped.get(t['particle'])} and {t['i']} both map to particle {t['particle']}")
        mapped[t["particle"]] = t["i"]
    need_drawn = _drawable(ev, sc)
    missing = [i for i in need_drawn if i not in mapped]
    need(not missing, "EVT_SCENE_BIJECTION",
         f"{len(missing)} drawable particles have no drawn track, first: particle {missing[0] if missing else ''} "
         f"(pdg {ev['particles'][missing[0]]['pdg'] if missing else ''})")
    return {"drawable_particles": len(need_drawn), "tracks_drawn": len(scene["tracks"]), "towers_drawn": len(scene["towers"])}


def _check_extension_bijection(ev, sc, scene):
    """Muon extensions (merged convention) map to event tracks, once each, visibly, with a real path. The track itself is
    drawn inside the tracker by then: _check_bijection has already required every event track."""
    have = {t["i"] for t in ev.get("tracks", [])}
    for k, xs in sorted(scene["extensions"].items()):
        need(k in have, "EVT_SCENE_BIJECTION", f"an extension strip names trk_{k}, which maps to no track of the event")
        need(len(xs) == 1, "EVT_SCENE_BIJECTION", f"trk_{k} has {len(xs)} extensions drawn: at most one each")
        need(xs[0]["visible"], "EVT_SCENE_BIJECTION", f"trk_{k} extension is hidden (a Switch that does not select it, or a Collision proxy)")
        # (a strip of fewer than two vertex pairs is already refused by the strip reader, so no point count is needed here)
    return {"extensions": len(scene["extensions"])}


def _check_scene_geometry(ev, spec, scene):
    det, m = ev["detector"], spec["containment"]["margin_m"]
    ca, b = det["calorimeter"], det["b_field_t"]
    rc = spec["scene"]["reach"]
    by_id = {t["i"]: t for t in ev.get("tracks", [])}
    fits = straight = unresolved = 0
    npts = 0
    for k, ent in sorted(scene["tracks"].items()):
        npts += len(ent["points"])
        for p in ent["points"]:
            need(_in_tracker(p, det, m), "EVT_CONTAINMENT",
                 f"scene trk_{k}: point ({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f}) m is outside the tracker")
    for k, ent in sorted(scene["towers"].items()):
        for p in ent["points"]:
            r = math.hypot(p[0], p[1])
            need(ca["r_min_m"] - m <= r <= ca["r_max_m"] + m and abs(p[2]) <= ca["half_length_m"] + m, "EVT_CONTAINMENT",
                 f"scene twr_{k}: point ({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f}) m is outside the calorimeter")
    for k, ent in sorted(scene["tracks"].items()):
        idx = ent["geometry"]["index"]
        line, cur = [], []
        for v in idx + [-1]:
            if v == -1:
                if cur:
                    line = line or cur
                cur = []
            else:
                cur.append(ent["points"][v])
        path = line or ent["points"]
        t = by_id[k]
        v0 = t["helix"].get("vertex_m", [0.0, 0.0, 0.0])
        d0 = _dist(path[0], v0)
        need(d0 <= rc["start_tol_m"], "EVT_SCENE_BIJECTION",
             f"scene trk_{k} starts {d0:.3f} m from its vertex ({v0[0]:.3f}, {v0[1]:.3f}, {v0[2]:.3f}): it is not this track's path")
        want, _left = _expected_reach(t, det)
        got = max(math.hypot(q[0] - path[0][0], q[1] - path[0][1]) for q in path)
        need(got >= want - rc["reach_tol_m"], "EVT_SCENE_BIJECTION",
             f"scene trk_{k} reaches {got:.3f} m from its vertex in xy, its own helix reaches {want:.3f} m inside the tracker: the drawing stops short")
        nxt = next((q for q in path[1:] if math.hypot(q[0] - path[0][0], q[1] - path[0][1]) > 1e-4), None)
        if nxt is not None:
            hd = math.atan2(nxt[1] - path[0][1], nxt[0] - path[0][0]) - t["phi"]
            hd = (hd + math.pi) % (2 * math.pi) - math.pi
            need(abs(hd) <= rc["dir_tol_rad"], "EVT_SCENE_BIJECTION",
                 f"scene trk_{k} leaves its vertex heading {hd:+.3f} rad off the event phi {t['phi']:.3f}: it points the wrong way")
        lxy = sum(math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]) for i in range(len(path) - 1))
        dz = path[-1][2] - path[0][2]
        lam, lam_want = math.atan2(dz, lxy), math.atan(math.sinh(t["eta"]))   # the dip angle: well conditioned at every eta
        need(abs(lam - lam_want) <= rc["pitch_tol_rad"], "EVT_SCENE_BIJECTION",
             f"scene trk_{k} rises {dz:.3f} m in z over {lxy:.3f} m in xy (dip {lam:.3f} rad), eta {t['eta']:.3f} gives {lam_want:.3f} rad: it is not this track's path")
        res = _check_bend("scene", path, t, b, spec["curvature"])
        fits += 1
        straight += 1 if res["straight"] else 0
        unresolved += 1 if res["unresolved"] else 0
    return {"scene_points": npts, "scene_curvature_judged": fits, "scene_drawn_straight": straight, "scene_curvature_unresolved": unresolved}


def _bound_source(lab, info, sh, names):
    """The binding every shaded drawing needs: a ComposedShader with data: VERTEX and FRAGMENT parts, the clock field,
    and each of `names` declared as a vertex attribute. Returns the vertex source."""
    need(info["bound"], "EVT_SHADER", f"{lab} has no ComposedShader in its Appearance: it would draw with the flat default look")
    vparts = [u for ty, urls, _t in info["parts"] if ty.upper() == "VERTEX" for u in urls]
    fparts = [u for ty, urls, _t in info["parts"] if ty.upper() == "FRAGMENT" for u in urls]
    need(any(u.startswith("data:x-shader/x-vertex,") for u in vparts) and any(u.startswith("data:x-shader/x-fragment,") for u in fparts),
         "EVT_SHADER", f"{lab}: the shader needs a VERTEX ShaderPart url data:x-shader/x-vertex, and a FRAGMENT one data:x-shader/x-fragment,")
    need(not any(t for _ty, urls, t in info["parts"] if t and not urls), "EVT_SHADER", f"{lab}: ShaderPart carries raw source instead of a data: url")
    need(sh["time_field"] in info["fields"], "EVT_SHADER", f"{lab}: the shader declares no field {sh['time_field']}")
    src = " ".join(vparts)
    for name in names:
        need(re.search(r"\battribute\s+(?:highp\s+|mediump\s+|lowp\s+)?(?:float|vec[234])\s+" + re.escape(name) + r"\b", src) is not None
             or re.search(r"\bin\s+(?:float|vec[234])\s+" + re.escape(name) + r"\b", src) is not None, "EVT_SHADER",
             f"{lab}: the vertex shader never declares attribute {name}")
    return src


def _check_shader(ev, sh, scene):
    by_id = {t["i"]: t for t in ev.get("tracks", [])}
    ident = sh["ident"]["name"]
    attr_spec = {a["name"]: a["components"] for a in sh["attributes"]}
    attr_const = {a["name"]: a.get("constant", True) for a in sh["attributes"]}
    rows = 0
    shader_defs = set()
    drawn = [(f"trk_{k}", k, ent) for k, ent in sorted(scene["tracks"].items())]
    drawn += [(f"trk_{k} extension ({x['shape']} strip {x['strip']})", k, x) for k, xs in sorted(scene.get("extensions", {}).items()) for x in xs]
    bt, spc = sh["birth"], sh["species"]
    for lab, k, ent in drawn:
        info = ent["shader"]
        _bound_source(lab, info, sh, list(attr_spec))
        shader_defs.add(info["def"])
        attrs = ent["geometry"]["attrs"]
        npts = len(ent["points"])
        for name, comps in attr_spec.items():
            need(name in attrs, "EVT_SHADER", f"{lab} supplies no vertex attribute {name}: the shader would read zeros (flat look)")
            nc, vals = attrs[name]
            need(nc == comps and len(vals) == nc * npts, "EVT_SHADER",
                 f"{lab}: attribute {name} has numComponents {nc} and {len(vals)} values, expected {comps} and {comps * npts}")
            if attr_const[name]:
                rowset = {tuple(vals[i * nc:(i + 1) * nc]) for i in range(npts)}
                need(len(rowset) == 1, "EVT_SHADER", f"{lab}: attribute {name} varies along the track; the spec says it is one constant per particle")
            pair = ent["geometry"].get("pair_attrs")
            if pair is not None:
                need(pair.get(name, (nc, []))[1] == vals, "EVT_SHADER",
                     f"{lab}: attribute {name} differs between the two vertices of a ribbon pair: the two edges of one ribbon would disagree")
        _, v = attrs[ident]
        row = v[:4]
        t = by_id[k]
        need(row[0] == k, "EVT_SHADER", f"{lab}: {ident}.id is {row[0]:g}, expected {k}")
        need((row[1] > 0) == (t["charge"] > 0) and (row[1] < 0) == (t["charge"] < 0), "EVT_SHADER",
             f"{lab}: {ident}.charge {row[1]:+g} contradicts the event charge {t['charge']:+g}: the hue would be wrong")
        need(abs(row[2] - t["pt"]) <= sh["pt_rel_tol"] * t["pt"], "EVT_SHADER",
             f"{lab}: {ident}.pt {row[2]:.4g} differs from the event pT {t['pt']:.4g}: the brightness would be wrong")
        b0 = t.get("t_prod_ns", 0.0) * C_M_PER_NS / bt["slow_motion_m_per_s"]
        need(-1e-4 <= row[3] - b0 <= bt["jitter_s"] + 1e-4, "EVT_SHADER",
             f"{lab}: {ident}.birth_s {row[3]:g}, the production time {t.get('t_prod_ns', 0.0):g} ns in slow motion gives {b0:.4g} "
             f"(+ up to {bt['jitter_s']:g} s jitter): the track would appear at the wrong time")
        # within the tolerances above an extension could still disagree with its own track: one particle, one row
        if ent is not scene["tracks"].get(k):
            trow = scene["tracks"][k]["geometry"]["attrs"][ident][1][:4]
            need(row == trow, "EVT_SHADER", f"trk_{k} extension carries ident row {row}, its track {trow}: one particle, one row")
        p = ev["particles"][t["particle"]]
        want_sp = spc["by_pdg"].get(str(abs(p["pdg"])), spc["charged"] if t["charge"] != 0 else spc["neutral"])
        need(attrs[spc["name"]][1][0] == want_sp, "EVT_SHADER",
             f"{lab}: {spc['name']} {attrs[spc['name']][1][0]:g}, the particle (pdg {p['pdg']}) is species {want_sp:g}: the colour would be wrong")
        rows += npts
    clocked = False
    for frm, ffield, to, tfield in scene["routes"]:
        if frm in scene["timesensors"] and to in shader_defs and tfield == sh["time_field"]:
            clocked = True
    need(clocked, "EVT_SHADER", f"no ROUTE from a TimeSensor to the shader field {sh['time_field']}: the pulses and the growth would never move")
    return {"tracks_with_shader": len(scene["tracks"]), "extensions_with_shader": len(drawn) - len(scene["tracks"]),
            "shader_nodes": len(shader_defs), "attribute_rows": rows}


def _check_arcs(ev, sh, scene):
    """a_arc is metres along the drawn path: 0 at the vertex (an extension starts where its track ends), never falling,
    and spanning the drawn length. The growth front and the pulses read it, so a lie here hides or moves a track.
    Run after the geometry and merged checks, so a path that is wrong is named for that first."""
    ar = sh["arc"]
    drawn = [(f"trk_{k}", k, ent, 0.0) for k, ent in sorted(scene["tracks"].items())]
    drawn += [(f"trk_{k} extension ({x['shape']} strip {x['strip']})", k, x, scene["tracks"][k]["geometry"]["attrs"][ar["name"]][1][-1])
              for k, xs in sorted(scene.get("extensions", {}).items()) for x in xs]
    for lab, _k, ent, start in drawn:
        av = ent["geometry"]["attrs"][ar["name"]][1]
        need(all(av[i + 1] >= av[i] - 1e-4 for i in range(len(av) - 1)), "EVT_SHADER",
             f"{lab}: {ar['name']} runs backwards along the path: the growth front would jump")
        need(abs(av[0] - start) <= ar["abs_tol_m"], "EVT_SHADER",
             f"{lab}: {ar['name']} starts at {av[0]:g} m, expected {start:g} m (0 at the vertex, or where its track ends)")
        pts3 = ent["points"]
        plen = sum(_dist(pts3[i], pts3[i + 1]) for i in range(len(pts3) - 1))
        need(abs((av[-1] - av[0]) - plen) <= ar["abs_tol_m"] + ar["rel_tol"] * plen, "EVT_SHADER",
             f"{lab}: {ar['name']} spans {av[-1] - av[0]:.4g} m, the drawn path is {plen:.4g} m long: the growth and pulses would not follow it")
    return {"arcs_checked": len(drawn)}


def _check_merged(ev, spec, scene):
    """The merged convention's own promises: tower cell rows match the event, only muons pass the calorimeter and each
    one that leaves the tracker is drawn through it, joined to its track."""
    mg = spec["scene"]["merged"]
    sh = spec["scene"]["shader"]
    det = ev["detector"]
    tr, m = det["tracker"], spec["containment"]["margin_m"]
    ex, tc, lk = mg["extensions"], mg["tower_cell"], mg["look"]
    by_tower = {w["i"]: w for w in ev.get("towers", [])}
    clocked = {to for frm, _ff, to, tf in scene["routes"] if frm in scene["timesensors"] and tf == sh["time_field"]}
    for name, info in sorted(scene.get("merged_info", {}).items()):
        if MTWR.match(name):
            _bound_source(name, info, sh, [tc["name"], lk["name"]])
            need(info["def"] in clocked, "EVT_SHADER", f"{name}: its shader {info['def']} gets no ROUTE from a TimeSensor to {sh['time_field']}: the crown would never light")
    cells = 0
    for k, ent in sorted(scene["towers"].items()):
        if not ent.get("merged"):
            continue
        nc, vals = ent["geometry"]["attrs"][tc["name"]]
        need(ent["geometry"]["pair_attrs"].get(tc["name"], (nc, []))[1] == vals, "EVT_SHADER",
             f"twr_{k}: {tc['name']} differs between the two vertices of a spike pair: the two edges of one spike would disagree")
        rowset = {tuple(vals[i:i + 4]) for i in range(0, len(vals), 4)}
        need(len(rowset) == 1, "EVT_SHADER", f"twr_{k}: {tc['name']} varies between its spikes; it is one row per tower")
        row = next(iter(rowset))
        w = by_tower[k]
        need(math.isfinite(row[1]) and abs(row[1] - w["E"]) <= tc["e_rel_tol"] * max(w["E"], 1e-9), "EVT_SHADER",
             f"twr_{k}: {tc['name']}.E {row[1]:.4g} differs from the event tower energy {w['E']:.4g}: the spike length and light would be wrong")
        need(0.0 <= row[2] <= 1.0 and math.isfinite(row[3]) and row[3] >= 0, "EVT_SHADER", f"twr_{k}: {tc['name']} em_frac or arrival_s out of range")
        for spike in ent["spikes"]:
            # a spike stands on the calorimeter face inside its own cell (eta and phi of its base) and runs radially out
            # in xy at constant z, so its tip keeps the cell's phi and the base's z
            (bx, by_, bz), tip = spike[0], spike[-1]
            rb = math.hypot(bx, by_)
            deta = math.asinh(bz / rb) - w["eta"] if rb > 0 else math.inf
            for q in (spike[0], tip):
                dph = (math.atan2(q[1], q[0]) - w["phi"] + math.pi) % (2 * math.pi) - math.pi
                need(abs(dph) <= tc["cell_dphi"] / 2 + tc["cell_tol"] and abs(deta) <= tc["cell_deta"] / 2 + tc["cell_tol"]
                     and abs(q[2] - bz) <= tc["cell_tol"] and math.hypot(q[0], q[1]) >= rb - tc["cell_tol"], "EVT_CONTAINMENT",
                     f"twr_{k}: a spike point sits {dph:+.3f} rad, {deta:+.3f} in eta and {q[2] - bz:+.3f} m in z off its tower's cell: it is drawn in another cell")
        cells += 1
    by_id = {t["i"]: t for t in ev.get("tracks", [])}
    pdgs = {abs(v) for v in ex["pdg"]}
    ln, kinds = lk["name"], lk["kinds"]
    arc_name = sh["arc"]["name"]

    def look_rows(lab, geo, kind, drawn_m):
        nc, vals = geo["attrs"][ln]
        need(nc == 4, "EVT_SHADER", f"{lab}: {ln} has {nc} components, the convention has 4 (side, seed, drawn_m, kind)")
        rows = {tuple(vals[i + 1:i + 4]) for i in range(0, len(vals), 4)}
        od = geo["pair_attrs"][ln][1]
        need(rows == {tuple(od[i + 1:i + 4]) for i in range(0, len(od), 4)} and len(rows) == 1, "EVT_SHADER",
             f"{lab}: {ln} seed, drawn_m or kind differ along the strip or between a ribbon pair: they are one per particle")
        seed, dm, kd = next(iter(rows))
        need(kd == kind, "EVT_SHADER", f"{lab}: {ln}.kind is {kd:g}, a {[n for n, v in kinds.items() if v == kind][0]} path is {kind}: it would be drawn as another kind")
        need(abs(dm - drawn_m) <= sh["arc"]["abs_tol_m"], "EVT_SHADER",
             f"{lab}: {ln}.drawn_m is {dm:g}, the path it fades along ends at {drawn_m:g} m of arc")


    def exits(k):
        """Whether muon track k leaves the tracker: its own helix leaves within half a turn, or its drawing (already
        bound to that helix) ends on the boundary heading out."""
        ent = scene["tracks"][k]
        if _expected_reach(by_id[k], det)[1]:
            return True
        if len(ent["points"]) < 2:
            return False
        a, b = ent["points"][-2], ent["points"][-1]
        out_r = math.hypot(b[0], b[1]) >= tr["r_max_m"] - m and (b[0] * (b[0] - a[0]) + b[1] * (b[1] - a[1])) > 0
        out_z = abs(b[2]) >= tr["half_length_m"] - m and b[2] * (b[2] - a[2]) > 0
        return out_r or out_z

    for k, xs in sorted(scene["extensions"].items()):
        x = xs[0]
        pdg = ev["particles"][by_id[k]["particle"]]["pdg"]
        need(abs(pdg) in pdgs, "EVT_CONTAINMENT",
             f"trk_{k} is drawn on past the tracker, but its particle is pdg {pdg}: only {sorted(pdgs)} may pass the calorimeter")
        need(exits(k), "EVT_CONTAINMENT", f"trk_{k} is drawn on past the tracker, but its track never leaves the tracker")
        tp = scene["tracks"][k]["points"]
        end = tp[-1]
        need(_dist(x["points"][0], end) <= ex["join_tol_m"], "EVT_SCENE_BIJECTION",
             f"trk_{k} extension starts {_dist(x['points'][0], end):.3f} m from where its track ends: it is not the same trajectory")
        q0 = x["points"][0]
        need(math.hypot(q0[0], q0[1]) >= tr["r_max_m"] - m or abs(q0[2]) >= tr["half_length_m"] - m, "EVT_SCENE_BIJECTION",
             f"trk_{k} extension starts at r {math.hypot(q0[0], q0[1]):.3f} m, z {q0[2]:.3f} m: inside the tracker, not on its boundary")
        if len(tp) >= 2 and len(x["points"]) >= 2:
            u_ = [end[i] - tp[-2][i] for i in range(3)]
            v_ = [x["points"][1][i] - q0[i] for i in range(3)]
            nu, nv = math.sqrt(sum(c * c for c in u_)), math.sqrt(sum(c * c for c in v_))
            ang = math.degrees(math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(u_, v_)) / (nu * nv))))) if nu > 0 and nv > 0 else 180.0
            need(ang <= ex["join_angle_deg"], "EVT_SCENE_BIJECTION",
                 f"trk_{k} extension turns {ang:.1f} degrees where it joins its track (spec {ex['join_angle_deg']:g}): it is not the same trajectory")
        for q in x["points"]:
            need(math.hypot(q[0], q[1]) <= ex["r_max_m"] + m and abs(q[2]) <= ex["half_length_m"] + m, "EVT_CONTAINMENT",
                 f"trk_{k} extension point ({q[0]:.3f}, {q[1]:.3f}, {q[2]:.3f}) m is outside the muon system")
            need(not _in_tracker(q, det, -m), "EVT_CONTAINMENT",
                 f"trk_{k} extension point ({q[0]:.3f}, {q[1]:.3f}, {q[2]:.3f}) m is back inside the tracker: an extension only runs outward")
    exiting = 0
    for k, ent in sorted(scene["tracks"].items()):
        t = by_id.get(k)
        if t is None or t["charge"] == 0 or abs(ev["particles"][t["particle"]]["pdg"]) not in pdgs:
            continue
        if exits(k):
            exiting += 1
            need(k in scene["extensions"], "EVT_SCENE_BIJECTION",
                 f"muon trk_{k} leaves the tracker but is not drawn on through the calorimeter: a muon is the one particle that passes")
    for k, ent in sorted(scene["tracks"].items()):
        if not ent.get("merged"):
            continue
        t = by_id[k]
        xs = scene["extensions"].get(k)
        end_arc = (xs[0] if xs else ent)["geometry"]["attrs"][arc_name][1][-1]
        look_rows(f"trk_{k}", ent["geometry"], kinds["charged"] if t["charge"] != 0 else kinds["neutral"], end_arc)
        if xs:
            look_rows(f"trk_{k} extension", xs[0]["geometry"], kinds["extension"], end_arc)
    return {"merged_shapes": scene["merged_shapes"], "merged_tower_cells": cells, "extensions": len(scene["extensions"]), "exiting_muons": exiting}


def check(event_text: str, spec: dict, scene_text: str | None = None) -> dict:
    """Check one event (and its scene). Returns measurements; raises on the first broken rule."""
    spec = load_spec(spec)
    ev = parse_event(event_text)
    sc = spec.get("scene")
    mg = sc.get("merged") if sc else None
    scene = (read_scene(scene_text, mg, sc["shader"]["ident"]["name"] if mg else None) if scene_text is not None else None)
    need(scene is None or sc is not None, "EVT_SPEC", "a scene was supplied but the spec has no scene section")
    meas = {"units": _check_units(ev, spec, scene), "conservation": _check_conservation(ev, spec)}
    meas["containment"] = _check_containment(ev, spec)
    meas["tracks"] = _check_tracks(ev, spec)
    need(not (sc and sc["required"] and scene is None), "EVT_SCENE_BIJECTION", "the spec requires a scene and the event names none: nothing is drawn")
    inv = {"particles": len(ev["particles"]), "final_state": meas["conservation"]["final_state"], "tracks": len(ev.get("tracks", [])),
           "charged_tracks": sum(1 for t in ev.get("tracks", []) if t["charge"] != 0),
           "hits": sum(len(t.get("hits", [])) for t in ev.get("tracks", [])), "towers": len(ev.get("towers", [])), "scene": None}
    if scene is not None:
        meas["bijection"] = _check_bijection(ev, sc, scene)
        meas["extension_bijection"] = _check_extension_bijection(ev, sc, scene) if scene["extensions"] else None
        meas["scene_geometry"] = _check_scene_geometry(ev, spec, scene)
        meas["shader"] = _check_shader(ev, sc["shader"], scene) if sc.get("shader") else None
        meas["merged"] = _check_merged(ev, spec, scene) if scene["merged_shapes"] else None
        meas["arcs"] = _check_arcs(ev, sc["shader"], scene) if sc.get("shader") else None
        inv["scene"] = {"bytes": scene["bytes"], "shapes": scene["shapes"], "track_shapes": len(scene["tracks"]), "tower_shapes": len(scene["towers"]),
                        "transforms": scene["transforms"], "routes": len(scene["routes"]), "components": scene["components"],
                        "unreadable_nodes": dict(scene["unreadable"]), "profile": scene["profile"], "version": scene["version"]}
    return {"inventory": inv, "measurements": meas}


def check_files(paths: list[Path], spec: dict) -> dict:
    need(paths, "EVT_PARSE", "no event files matched")
    out = {}
    for p in paths:
        text = p.read_text(encoding="utf-8")
        ev = parse_event(text)
        scene_text = None
        if ev.get("scene") is not None:
            rel = Path(ev["scene"])
            need(not rel.is_absolute() and ".." not in rel.parts, "EVT_PARSE", f"scene path {ev['scene']!r} must be relative and stay below the event file")
            sp = p.parent / rel
            need(sp.is_file(), "EVT_PARSE", f"scene file {ev['scene']} named by the event is missing")
            scene_text = sp.read_text(encoding="utf-8")
        out[p.as_posix()] = check(text, spec, scene_text)
    return out
