"""Two-sided controls for loomkit.hepevent (the hep-event demo witness), run under normal Python and `python -O`.

Fixtures are SYNTHETIC and labelled so: an exact two-body Z -> mu mu decay (hand-computed, kit/examples/hep/exact_events.py)
and a deterministic toy shower of 40 to 400 particles with low-pT loopers. Scenes are written by the scene builder
(kit/examples/hep/build_event_scene.py) and then damaged one way at a time with an XML edit. The builder and the witness do
not share code: the builder samples the helix itself, the witness fits a circle to what was drawn. Each negative control must
be rejected with its INTENDED diagnostic; any other exception is a broken test, not a catch (law 19). A negative that passes
raises SURVIVING_CONTROL.

  python3 -I kit/tests/test_hepevent.py      # runs both modes and writes kit/tests/hepevent-last-run.json
"""
from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(KIT / "examples/hep"))

import build_event_scene as bs  # noqa: E402
import exact_events as ee  # noqa: E402
from loomkit import hepevent  # noqa: E402
from loomkit.core import GateError  # noqa: E402

SPEC = json.loads((KIT / "examples/hep/hep-demo-spec.json").read_text())
SHA = "0" * 64


def expect(code, fn, why=None):
    try:
        fn()
    except GateError as e:
        if e.code != code:
            raise RuntimeError(f"WRONG_DIAGNOSTIC: expected {code}, got {e.code} ({e.detail})") from None
        if why is not None and why not in e.detail:
            raise RuntimeError(f"WRONG_REASON: {code} raised, but {why!r} is not in its detail: {e.detail}") from None
        return {"expected": code, "caught": e.code, "detail": e.detail}
    raise RuntimeError(f"SURVIVING_CONTROL: {code}")


def run(ev, scene=None, spec=None):
    return hepevent.check(json.dumps(ev), spec if spec is not None else SPEC, scene)


def scene_of(ev):
    return bs.build(ev, SHA)[0]


def mut(scene, fn):
    root = ET.fromstring(scene)
    fn(root)
    return ET.tostring(root, encoding="unicode")


def parents(root):
    return {c: p for p in root.iter() for c in p}


def shape(root, name):
    for el in root.iter():
        if el.get("DEF") == name:
            return el
    raise RuntimeError(f"fixture has no {name}")


def edit(spec_mut):
    s = copy.deepcopy(SPEC)
    spec_mut(s)
    return s


def with_ev(base, fn):
    ev = copy.deepcopy(base)
    fn(ev)
    return ev


EV = ee.toy_shower(40, 7)
ZMM = ee.zmumu()
BASE = scene_of(EV)
# a charged low-pT track that loops, so curvature and sense are well resolved, and a straight neutral
LOW = next(t for t in EV["tracks"] if t["charge"] != 0 and 0.5 < t["pt"] < 2.0 and abs(t["eta"]) < 1.0 and len(t.get("hits", [])) >= 3)
NEUTRAL = next(t for t in EV["tracks"] if t["charge"] == 0)
HIGH = max((t for t in EV["tracks"] if t["charge"] != 0), key=lambda t: t["pt"])


def passes(fn):
    res = fn()
    return {"passed": True, "inventory": res["inventory"], "measured": {k: v for k, v in res["measurements"].items() if k in ("bijection", "shader", "tracks", "scene_geometry")}}


def forward_event():
    """Three forward charged particles with realistic masses; the incoming is their sum (a toy, labelled)."""
    def part(pdg, m, q, pt, eta, phi):
        px, py, pz = pt * math.cos(phi), pt * math.sin(phi), pt * math.sinh(eta)
        return {"pdg": pdg, "status": 1, "charge": q, "px": round(px, 6), "py": round(py, 6), "pz": round(pz, 6),
                "E": round(math.sqrt(px * px + py * py + pz * pz + m * m), 6), "mothers": []}
    parts = [part(13, 0.10566, -1, 47.6281, 3.6115, 0.90822), part(211, 0.13957, 1, 0.887752, 6.59122, -1.18401),
             part(-211, 0.13957, -1, 0.528, -7.2, 1.9), part(211, 0.13957, 1, 3.2, 1.1, -2.2)]
    inc = {k: round(sum(q[k] for q in parts), 6) for k in ("px", "py", "pz", "E")}
    inc["charge"] = sum(q["charge"] for q in parts)
    return ee.hr.build_event("forward-toy", parts, inc, {"generator": "hand-set forward particles", "kind": "synthetic"})


def controls():
    rows = []
    ok = lambda name, fn: rows.append({"case": name, **passes(fn)})  # noqa: E731
    bad = lambda name, code, fn, why=None: rows.append({"case": name, **expect(code, fn, why)})  # noqa: E731

    # ---- positive controls
    r = passes(lambda: run(ZMM, scene_of(ZMM)))
    inv = r["inventory"]
    if (inv["tracks"], inv["towers"], inv["hits"]) != (2, 2, 16) or inv["scene"]["track_shapes"] != 2 or r["measured"]["shader"]["tracks_with_shader"] != 2:
        raise RuntimeError(f"INVENTORY: a pass must report what it read, got {inv}")
    rows.append({"case": "exact Z -> mu mu with its scene (positive control, inventory read back)", **r})
    ok("toy shower of 40 with loopers, tracks, towers and shader binding (positive control)", lambda: run(EV, BASE))
    big = ee.toy_shower(400, 11)
    ok("toy shower of 400 particles (positive control, scale)", lambda: run(big, scene_of(big)))

    def mm_scene(root):
        pm = parents(root)
        for name in ("tracks", "towers"):
            g = shape(root, name)
            for co in g.iter("Coordinate"):
                co.set("point", " ".join(f"{float(v) * 1000:.3f}" for v in co.get("point").split()))
            p, i = pm[g], list(pm[g]).index(g)
            p.remove(g)
            t = ET.Element("Transform", {"scale": "0.001 0.001 0.001"})
            t.append(g)
            p.insert(i, t)
    ok("scene points in millimetres under a Transform scale 0.001: the reader applies transforms (positive control)",
       lambda: run(EV, mut(BASE, mm_scene)))

    def in_switch(root):
        pm = parents(root)
        s = shape(root, "trk_3")
        p, i = pm[s], list(pm[s]).index(s)
        p.remove(s)
        sw = ET.Element("Switch", {"whichChoice": "0"})
        sw.append(s)
        p.insert(i, sw)
    ok("a track inside a Switch that selects it is drawn (positive control)", lambda: run(EV, mut(BASE, in_switch)))
    ev_only = copy.deepcopy(ZMM)
    nospec = edit(lambda s: s.pop("scene"))
    r = passes(lambda: run(ev_only, None, nospec))
    if r["inventory"]["scene"] is not None or r["measured"].get("shader") is not None and "shader" in r["measured"]:
        raise RuntimeError("INVENTORY: an events-only pass must say that no scene was read")
    rows.append({"case": "event alone, spec without a scene section: passes and reports scene None (positive control)", **r})
    k = LOW["i"]
    near = with_ev(EV, lambda e: e["tracks"][k]["helix"].update(radius_m=e["tracks"][k]["helix"]["radius_m"] * 1.10))
    ok("declared helix radius 10 percent off, inside the 15 percent curvature tolerance (positive control, edge)", lambda: run(near, None, edit(lambda s: s.pop("scene"))))

    # ---- regression controls from the real-event run (docs: findings 3 and 4)
    three = with_ev(EV, lambda e: e["tracks"][k].update(hits=e["tracks"][k]["hits"][-3:]))
    ok("a track with exactly 3 hits on the right circle is fitted, not called straight (regression: real displaced tracks)",
       lambda: run(three, None, edit(lambda s: s.pop("scene"))))
    bad("3 collinear hits for a track that pT says must curl", "EVT_CURVATURE",
        lambda: run(with_ev(EV, lambda e: e["tracks"][k].update(hits=[[0.6, 0.0, 0.0], [0.8, 0.0, 0.0], [1.0, 0.0, 0.0]])), None, edit(lambda s: s.pop("scene"))), 'curvature 0/m')

    def born_outside(e):
        pi = e["tracks"][k]["particle"]
        e["particles"][pi]["vertex_m"] = [2.0, 0.0, 0.0]
        del e["tracks"][k]
        for n, t in enumerate(e["tracks"]):
            t["i"] = n
    far = with_ev(EV, born_outside)
    ok("a charged particle born 2 m from the axis owes no track: its decay in flight is outside the tracker (positive control)",
       lambda: run(far, scene_of(far)))

    # ---- regression controls from the real-event run at eta up to 10 (docs: finding 6)
    fwd = forward_event()
    r = passes(lambda: run(fwd, scene_of(fwd)))
    sc_inv = r["measured"]["tracks"]
    if sc_inv["unresolved_hits"] < 1 or r["measured"]["scene_geometry"]["scene_curvature_unresolved"] < 2:
        raise RuntimeError(f"INVENTORY: a pass must say how many paths it could not resolve, got {sc_inv}")
    rows.append({"case": "forward tracks (a 47.6 GeV muon at eta 3.6, soft pions at eta +-6.6 and -7.2): paths shorter than their own bend can be fitted pass as UNRESOLVED and the pass counts them (positive control)", **r})

    def kinked_hits(e):
        t = next(t for t in e["tracks"] if t["pt"] > 40)
        t["hits"][1][1] += 0.005
    bad("an unresolved (50 GeV) track whose hits kink by 5 mm: judged as a straight line, so it is still caught", "EVT_CURVATURE",
        lambda: run(with_ev(fwd, kinked_hits), None, edit(lambda s_: s_.pop("scene"))), 'departs from a straight line')
    fk = next(t["i"] for t in fwd["tracks"] if t["charge"] != 0 and t["eta"] > 6)

    def kinked_scene(root):
        co = next(shape(root, f"trk_{fk}").iter("Coordinate"))
        v = [float(x) for x in co.get("point").split()]
        v[6] += 0.003   # an interior point: the first segment (the heading) stays on the event phi
        co.set("point", " ".join(f"{x:.4f}" for x in v))
    bad("a forward soft track (eta 6.6, 8 mm of xy path) drawn with a 3 mm kink", "EVT_CURVATURE", lambda: run(fwd, mut(scene_of(fwd), kinked_scene)), 'departs from a straight line')
    bad("spec without the point resolution of the stored coordinates", "EVT_SPEC", lambda: run(EV, BASE, edit(lambda s_: s_["curvature"].pop("point_resolution_m"))), 'point_resolution_m')
    bad("spec that resolves a bend smaller than the rounding it also declares", "EVT_SPEC",
        lambda: run(EV, BASE, edit(lambda s_: s_["curvature"].update(resolvable_sagitta_m=s_["curvature"]["point_resolution_m"] / 10))), 'must be at least point_resolution_m')

    # ---- negative controls: parse and spec
    bad("event is not JSON", "EVT_PARSE", lambda: hepevent.check("{not json", SPEC), 'event is not JSON')
    bad("a NaN energy (Python writes it, JSON forbids it)", "EVT_PARSE", lambda: run(with_ev(EV, lambda e: e["particles"][0].update(E=float("nan")))), 'non-finite number NaN')
    bad("a mother index that does not exist", "EVT_PARSE", lambda: run(with_ev(EV, lambda e: e["particles"][3].update(mothers=[99]))), 'must be earlier particle indices')
    bad("scene file truncated mid-element", "EVT_PARSE", lambda: run(EV, BASE[: len(BASE) // 2]), 'scene is not XML')
    bad("a USE before any DEF in the scene", "EVT_PARSE",
        lambda: run(EV, mut(BASE, lambda r: ET.SubElement(shape(r, "tracks"), "Shape", {"USE": "ghost"}))), 'before any DEF')
    bad("a Script node the reader cannot expand", "EVT_PARSE", lambda: run(EV, mut(BASE, lambda r: ET.SubElement(shape(r, "tracks"), "Script"))), 'cannot expand: Script')
    bad("spec without a curvature section", "EVT_SPEC", lambda: run(EV, BASE, edit(lambda s: s.pop("curvature"))), 'missing section curvature')
    bad("spec whose ident layout is not id, charge, pt, birth_s", "EVT_SPEC",
        lambda: run(EV, BASE, edit(lambda s: s["scene"]["shader"]["ident"].update(layout=["id", "pt", "charge", "birth_s"]))), 'scene.shader.ident')

    # ---- units
    def mev(e):
        for p in e["particles"] + [e["incoming"]]:
            for kk in ("px", "py", "pz", "E"):
                p[kk] *= 1000.0
        for t in e["tracks"]:
            t["pt"] *= 1000.0
            if t["helix"]["radius_m"]:
                t["helix"]["radius_m"] *= 1000.0
    bad("every momentum in MeV but read as GeV (mass of the muons comes out 105.7)", "EVT_UNITS", lambda: run(with_ev(EV, mev)), "median mass")

    def mm_det(e):
        d = e["detector"]
        d["tracker"].update(r_max_m=1100.0, half_length_m=2800.0)
        d["calorimeter"].update(r_min_m=1300.0, r_max_m=1800.0, half_length_m=3200.0)
    bad("detector radii written in millimetres", "EVT_UNITS", lambda: run(with_ev(EV, mm_det)), "millimetres read as metres")

    def mm_all(root):
        for g in ("tracks", "towers"):
            for co in shape(root, g).iter("Coordinate"):
                co.set("point", " ".join(f"{float(v) * 1000:.3f}" for v in co.get("point").split()))
    bad("scene exported in millimetres with no Transform", "EVT_UNITS", lambda: run(EV, mut(BASE, mm_all)), "scene extent")

    # ---- charge and momentum
    one = next(i for i, p in enumerate(EV["particles"]) if p["charge"] == 1)
    bad("one particle's charge flipped (sum no longer matches the incoming)", "EVT_CHARGE",
        lambda: run(with_ev(EV, lambda e: e["particles"][one].update(charge=-1))), "final-state charge")
    bad("a track whose charge disagrees with its particle (the hue and the bend would be wrong)", "EVT_CHARGE",
        lambda: run(with_ev(EV, lambda e: e["tracks"][LOW["i"]].update(charge=-LOW["charge"]))), "but its particle")
    bad("one particle's pz shifted by 5 GeV (final state no longer balances the incoming)", "EVT_4MOM",
        lambda: run(with_ev(EV, lambda e: e["particles"][one].update(pz=e["particles"][one]["pz"] + 5.0))), "final state minus declared incoming")

    # ---- curvature and sense
    bad("declared helix radius doubled against its pT", "EVT_CURVATURE",
        lambda: run(with_ev(EV, lambda e: e["tracks"][k]["helix"].update(radius_m=e["tracks"][k]["helix"]["radius_m"] * 2.0))), "declared helix radius")
    bad("declared helix radius 35 percent off, outside the 15 percent tolerance", "EVT_CURVATURE",
        lambda: run(with_ev(EV, lambda e: e["tracks"][k]["helix"].update(radius_m=e["tracks"][k]["helix"]["radius_m"] * 1.35))), "declared helix radius")

    def straight_hits(e):
        t = e["tracks"][k]
        t["hits"] = [[r * math.cos(math.radians(0)), 0.0, 0.0] for r in (0.2, 0.4, 0.6, 0.8)]
    bad("hits on a straight line for a track that pT says must curl", "EVT_CURVATURE", lambda: run(with_ev(EV, straight_hits)), "hits: curvature")
    sc_wide = scene_of(with_ev(EV, lambda e: e["tracks"][k]["helix"].update(radius_m=e["tracks"][k]["helix"]["radius_m"] * 2.0)))
    bad("the DRAWN helix has twice the radius its pT allows (event is right, scene is wrong)", "EVT_CURVATURE", lambda: run(EV, sc_wide), "scene: curvature")
    sc_line = scene_of(with_ev(EV, lambda e: e["tracks"][k]["helix"].update(radius_m=None, sense=0)))
    bad("a charged particle drawn as a straight line", "EVT_CURVATURE", lambda: run(EV, sc_line), "scene")
    bad("declared bend sense inverted against the charge", "EVT_SENSE",
        lambda: run(with_ev(EV, lambda e: e["tracks"][k]["helix"].update(sense=-e["tracks"][k]["helix"]["sense"]))), "declared sense")
    sc_flip = scene_of(with_ev(EV, lambda e: e["tracks"][k]["helix"].update(sense=-e["tracks"][k]["helix"]["sense"])))
    bad("the drawn helix bends the wrong way for its charge (same radius)", "EVT_SENSE", lambda: run(EV, sc_flip), "scene: bends")

    # ---- containment
    bad("a production vertex 2 m from the axis, outside the tracker", "EVT_CONTAINMENT",
        lambda: run(with_ev(EV, lambda e: e["tracks"][k]["helix"].update(vertex_m=[2.0, 0.0, 0.0]))), "outside the tracker")
    bad("a calorimeter tower at eta 2.0, beyond the barrel", "EVT_CONTAINMENT", lambda: run(with_ev(EV, lambda e: e["towers"][0].update(eta=2.0))), "outside the barrel calorimeter")

    def far_point(root):
        co = next(shape(root, f"trk_{k}").iter("Coordinate"))
        v = [float(x) for x in co.get("point").split()]
        v[-3], v[-2] = v[-3] * 2.0 + 0.5, v[-2] * 2.0 + 0.5
        co.set("point", " ".join(f"{x:.4f}" for x in v))
    bad("one drawn track point outside the tracker volume", "EVT_CONTAINMENT", lambda: run(EV, mut(BASE, far_point)), "outside the tracker")

    def far_tower(root):
        co = next(shape(root, "twr_0").iter("Coordinate"))
        co.set("point", " ".join(f"{float(x) * 1.5:.4f}" for x in co.get("point").split()))
    bad("a drawn tower stretched outside the calorimeter", "EVT_CONTAINMENT", lambda: run(EV, mut(BASE, far_tower)), "outside the calorimeter")

    # ---- scene bijection
    def drop(name):
        def f(root):
            s = shape(root, name)
            parents(root)[s].remove(s)
        return f
    bad("a track deleted from the scene (the negative control from the brief)", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(BASE, drop(f"trk_{k}"))), f"trk_{k}")
    bad("a tower deleted from the scene", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(BASE, drop("twr_0"))), "twr_0")

    def extra(root):
        s = copy.deepcopy(shape(root, f"trk_{k}"))
        s.set("DEF", "trk_999")
        parents(root)[shape(root, f"trk_{k}")].append(s)
    bad("a drawn track that maps to no particle (trk_999)", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(BASE, extra)), "maps to no track")

    def twice(root):
        u = ET.Element("Shape", {"USE": f"trk_{k}"})
        parents(root)[shape(root, f"trk_{k}")].append(u)
    bad("a track drawn twice (a USE of its shape)", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(BASE, twice)), "drawn 2 times")

    def hide(root):
        pm = parents(root)
        s = shape(root, f"trk_{k}")
        p, i = pm[s], list(pm[s]).index(s)
        p.remove(s)
        sw = ET.Element("Switch", {"whichChoice": "-1"})
        sw.append(s)
        p.insert(i, sw)
    bad("a track present but hidden by a Switch that selects nothing", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(BASE, hide)), "hidden")

    def no_line(root):
        s = shape(root, f"trk_{k}")
        for c in list(s):
            if c.tag == "IndexedLineSet":
                s.remove(c)
    bad("trk_ shape with no line geometry (named, but nothing drawn)", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(BASE, no_line)), "nothing is drawn")
    top = HIGH["i"]

    def drop_track(e):
        del e["tracks"][top]
        for n, t in enumerate(e["tracks"]):
            t["i"] = n
    short = with_ev(EV, drop_track)
    bad("a drawable charged particle with no track at all (event and scene agree, the particle is simply not drawn)", "EVT_SCENE_BIJECTION",
        lambda: run(short, scene_of(short)), "drawable particles have no drawn track")
    bad("two tracks mapped to one particle", "EVT_SCENE_BIJECTION",
        lambda: run(with_ev(EV, lambda e: e["tracks"][1].update(particle=e["tracks"][0]["particle"], charge=e["tracks"][0]["charge"])), BASE), "both map to particle")

    # ---- shader
    def no_shader(root):
        s = shape(root, f"trk_{k}")
        ap = next(c for c in s if c.tag == "Appearance")
        for c in list(ap):
            ap.remove(c)
        ET.SubElement(ap, "Material", {"emissiveColor": "1 1 1"})
    bad("a track whose Appearance has a Material and no shader (flat default look)", "EVT_SHADER", lambda: run(EV, mut(BASE, no_shader)), "no ComposedShader")

    def no_attr(name):
        def f(root):
            ils = next(shape(root, f"trk_{k}").iter("IndexedLineSet"))
            for c in list(ils):
                if c.get("name") == name:
                    ils.remove(c)
        return f
    bad("a track with no a_species attribute (the shader would read zeros)", "EVT_SHADER", lambda: run(EV, mut(BASE, no_attr("a_species"))), "supplies no vertex attribute a_species")

    def edit_ident(fn):
        def f(root):
            fva = next(c for c in shape(root, f"trk_{k}").iter("FloatVertexAttribute") if c.get("name") == "a_ident")
            v = [float(x) for x in fva.get("value").split()]
            fn(v)
            fva.set("value", " ".join(f"{x:g}" for x in v))
        return f

    def flip_charge(v):
        for i in range(1, len(v), 4):
            v[i] = -v[i]
    bad("a_ident charge contradicts the event (the hue would be wrong)", "EVT_SHADER", lambda: run(EV, mut(BASE, edit_ident(flip_charge))), "contradicts the event charge")

    def wrong_id(v):
        for i in range(0, len(v), 4):
            v[i] += 1
    bad("a_ident track id is not the track's index", "EVT_SHADER", lambda: run(EV, mut(BASE, edit_ident(wrong_id))), "expected")

    def wrong_pt(v):
        for i in range(2, len(v), 4):
            v[i] *= 2.0
    bad("a_ident pT is twice the event pT (the brightness would be wrong)", "EVT_SHADER", lambda: run(EV, mut(BASE, edit_ident(wrong_pt))), "differs from the event pT")

    def varies(v):
        v[4 + 2] = v[4 + 2] + 1.0
    bad("a_ident varies along one track (it must be one value per particle)", "EVT_SHADER", lambda: run(EV, mut(BASE, edit_ident(varies))), "varies along the track")

    def short_attr(root):
        fva = next(c for c in shape(root, f"trk_{k}").iter("FloatVertexAttribute") if c.get("name") == "a_arc")
        fva.set("value", " ".join(fva.get("value").split()[:-1]))
    bad("an attribute with one value too few", "EVT_SHADER", lambda: run(EV, mut(BASE, short_attr)), "expected")

    def no_route(root):
        for r_ in list(root.iter("ROUTE")):
            parents(root)[r_].remove(r_)
    bad("no ROUTE from the TimeSensor to the shader clock field", "EVT_SHADER", lambda: run(EV, mut(BASE, no_route)), "no ROUTE")

    def raw_url(root):
        for sp in root.iter("ShaderPart"):
            if sp.get("type") == "VERTEX":
                sp.set("url", '"shaders/track.vert"')
    bad("ShaderPart url points at a file instead of a data: URL", "EVT_SHADER", lambda: run(EV, mut(BASE, raw_url)), "data:x-shader/x-vertex")

    # ---- negative controls added after a mutation pass: each deletes one `need` and asks which control notices
    nospec = edit(lambda s_: s_.pop("scene"))
    structure = [
        ("schema is not loom.hep-event/1", "schema must be", lambda e: e.update(schema="loom.hep-event/0")),
        ("detector field is zero", "detector.b_field_t", lambda e: e["detector"].update(b_field_t=0)),
        ("tracker radius is zero", "detector.tracker", lambda e: e["detector"]["tracker"].update(r_max_m=0)),
        ("calorimeter inner radius beyond the outer", "detector.calorimeter", lambda e: e["detector"]["calorimeter"].update(r_min_m=2.0)),
        ("incoming without its energy", "incoming", lambda e: e["incoming"].pop("E")),
        ("no particles at all", "particles: at least one", lambda e: e.update(particles=[])),
        ("a pdg code written as a float", "pdg/status", lambda e: e["particles"][1].update(pdg=13.5)),
        ("a momentum written as a string", "charge or four-momentum", lambda e: e["particles"][1].update(px="3.0")),
        ("a vertex with two coordinates", "vertex_m must be", lambda e: e["particles"][1].update(vertex_m=[0.0, 0.0])),
        ("tracks is an object", "tracks", lambda e: e.update(tracks={})),
        ("a track whose i is not its position", "i must equal its position", lambda e: e["tracks"][1].update(i=7)),
        ("a track pointing at particle 99", "particle index", lambda e: e["tracks"][0].update(particle=99)),
        ("a track with pT zero", "charge, pt, eta, phi", lambda e: e["tracks"][0].update(pt=0)),
        ("a negative helix radius", "helix", lambda e: e["tracks"][0]["helix"].update(radius_m=-1.0)),
        ("a helix vertex with one coordinate", "helix.vertex_m", lambda e: e["tracks"][0]["helix"].update(vertex_m=[0.0])),
        ("a hit with two coordinates", "hits must be", lambda e: e["tracks"][0]["hits"].append([0.1, 0.2])),
        ("a negative production time", "t_prod_ns", lambda e: e["tracks"][0].update(t_prod_ns=-1.0)),
        ("towers is a number", "towers", lambda e: e.update(towers=5)),
        ("a tower whose i is not its position", "i, eta, phi, E", lambda e: e["towers"][0].update(i=4)),
        ("a tower with negative energy", "negative energy", lambda e: e["towers"][0].update(E=-1.0)),
        ("scene given as a number", "scene must be a relative path", lambda e: e.update(scene=5)),
    ]
    for label, why, fn in structure:
        bad(f"malformed event: {label}", "EVT_PARSE", lambda fn=fn: run(with_ev(ZMM, fn), None, nospec), why)
    spec_rows = [
        ("schema is not loom.hep-event-spec/1", "schema must be", lambda s_: s_.update(schema="x")),
        ("length range with one number", "units.length_range_m", lambda s_: s_["units"].update(length_range_m=[1.0])),
        ("unit tolerance of 1.5 decades", "must lie in (0, 1) decades", lambda s_: s_["units"].update(ratio_log10_tol=1.5)),
        ("momentum tolerance loosened to 10 percent", "no longer a momentum balance", lambda s_: s_["p4"].update(rel_tol=0.1)),
        ("curvature tolerance of 90 percent", "curvature.rel_tol must lie", lambda s_: s_["curvature"].update(rel_tol=0.9)),
        ("scene.required written as a word", "scene.required", lambda s_: s_["scene"].update(required="yes")),
        ("unreadable_nodes: ignore", "unreadable_nodes", lambda s_: s_["scene"].update(unreadable_nodes="ignore")),
        ("a negative draw_eta_max", "scene.draw_eta_max", lambda s_: s_["scene"].update(draw_eta_max=-1)),
        ("invisible_pdg holds a string", "scene.invisible_pdg", lambda s_: s_["scene"].update(invisible_pdg=["nu"])),
        ("min_points of 1", "min_points", lambda s_: s_["scene"].update(min_points=1)),
        ("an empty time_field", "time_field", lambda s_: s_["scene"]["shader"].update(time_field="")),
        ("a shader pT tolerance of 90 percent", "pt_rel_tol", lambda s_: s_["scene"]["shader"].update(pt_rel_tol=0.9)),
        ("an empty attribute list", "scene.shader.attributes:", lambda s_: s_["scene"]["shader"].update(attributes=[])),
        ("attribute list that omits the ident attribute", "must list the ident attribute",
         lambda s_: s_["scene"]["shader"]["attributes"][0].update(name="a_other")),
    ]
    for label, why, fn in spec_rows:
        bad(f"malformed spec: {label}", "EVT_SPEC", lambda fn=fn: run(EV, BASE, edit(fn)), why)
    bad("a point resolution of one metre (a rounding step that coarse judges nothing)", "EVT_SPEC",
        lambda: run(EV, BASE, edit(lambda s_: s_["curvature"].update(point_resolution_m=1.0))), "point_resolution_m must lie")
    bad("the circle fit is asked for a circle through two points", "EVT_CURVATURE", lambda: hepevent.fit_circle([(0.0, 0.0), (1.0, 0.0)]), "at least 3 points")
    bad("a scene is supplied but the spec has no scene section", "EVT_SPEC", lambda: run(EV, BASE, nospec), "a scene was supplied")
    bad("the spec requires a scene and the event brings none", "EVT_SCENE_BIJECTION", lambda: run(EV, None), "the spec requires a scene")

    # units, charge, momentum gates the first pass left unexercised
    bad("every helix radius in millimetres (pT untouched)", "EVT_UNITS",
        lambda: run(with_ev(ZMM, lambda e: [t["helix"].update(radius_m=t["helix"]["radius_m"] * 1000.0) for t in e["tracks"]]), None, nospec), "helix radius is 10^")
    bad("declared incoming charge +1 with a neutral final state", "EVT_CHARGE",
        lambda: run(with_ev(EV, lambda e: e["incoming"].update(charge=e["incoming"]["charge"] + 1)), None, nospec), "final-state charge")
    bad("every particle decayed: no final state", "EVT_4MOM",
        lambda: run(with_ev(ZMM, lambda e: [q.update(status=2) for q in e["particles"]]), None, nospec), "no final-state particles")

    def lone_beam(e):
        e["particles"].append({"pdg": 2212, "status": 4, "charge": 1, "px": 0.0, "py": 0.0, "pz": 100.0, "E": 100.0, "mothers": []})
    bad("a beam particle whose momentum is not the declared incoming", "EVT_4MOM", lambda: run(with_ev(ZMM, lone_beam), None, nospec),
        "differs from the beam particles")
    bad("a charged track declared straight (event alone)", "EVT_CURVATURE",
        lambda: run(with_ev(ZMM, lambda e: e["tracks"][0]["helix"].update(radius_m=None, sense=0)), None, nospec), "declared straight")

    # scene reader gates
    bad("scene is whitespace", "EVT_PARSE", lambda: run(EV, "   \n "), "scene: empty")
    bad("scene declares an entity", "EVT_PARSE", lambda: run(EV, '<!DOCTYPE X3D [<!ENTITY a "b">]>' + BASE), "entity declarations")
    bad("root element is not X3D", "EVT_PARSE", lambda: run(EV, mut(BASE, lambda r: setattr(r, "tag", "HTML"))), "root element is not X3D")
    bad("no Scene element", "EVT_PARSE", lambda: run(EV, mut(BASE, lambda r: [r.remove(c) for c in list(r) if c.tag == "Scene"])), "no <Scene> element")

    def first_point(root, fn):
        co = next(shape(root, f"trk_{k}").iter("Coordinate"))
        co.set("point", fn(co.get("point")))
    bad("a coordinate that is NaN", "EVT_PARSE", lambda: run(EV, mut(BASE, lambda r: first_point(r, lambda v: "nan " + v))), "non-finite number")
    bad("a coordinate that is not a number", "EVT_PARSE", lambda: run(EV, mut(BASE, lambda r: first_point(r, lambda v: "abc " + v))), "is not a number")
    bad("a Coordinate whose number count is not a multiple of 3", "EVT_PARSE",
        lambda: run(EV, mut(BASE, lambda r: first_point(r, lambda v: v + " 0.5"))), "xyz triples")

    def bad_index(root):
        ils = next(shape(root, f"trk_{k}").iter("IndexedLineSet"))
        ils.set("coordIndex", ils.get("coordIndex") + " 9999 -1")
    bad("a coordIndex past the end of its Coordinate", "EVT_PARSE", lambda: run(EV, mut(BASE, bad_index)), "points outside its Coordinate")

    def bad_nc(root):
        next(c for c in shape(root, f"trk_{k}").iter("FloatVertexAttribute")).set("numComponents", "7")
    bad("a FloatVertexAttribute with numComponents 7", "EVT_PARSE", lambda: run(EV, mut(BASE, bad_nc)), "numComponents")

    def open_mf(root):
        for sp in root.iter("ShaderPart"):
            sp.set("url", '"data:x-shader/x-vertex,void main')
    bad("a ShaderPart url whose quote is never closed", "EVT_PARSE", lambda: run(EV, mut(BASE, open_mf)), "unterminated MFString")

    def two_scale(root):
        pm = parents(root)
        g = shape(root, "towers")
        p, i = pm[g], list(pm[g]).index(g)
        p.remove(g)
        t = ET.Element("Transform", {"scale": "1 1"})
        t.append(g)
        p.insert(i, t)
    bad("a Transform whose scale has two numbers", "EVT_PARSE", lambda: run(EV, mut(BASE, two_scale)), "Transform.scale needs 3 numbers")
    bad("a DEF named trk_998 on a node that is not a Shape", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(BASE, lambda r: ET.SubElement(shape(r, "tracks"), "Group", {"DEF": "trk_998"}))), "not a Shape")

    def one_point(root):
        s_ = shape(root, f"trk_{k}")
        co = next(s_.iter("Coordinate"))
        co.set("point", " ".join(co.get("point").split()[:3]))
        next(s_.iter("IndexedLineSet")).set("coordIndex", "0 -1")
    bad("a track drawn with a single point", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(BASE, one_point)), "spec needs")

    def to_decayed(e):
        n = NEUTRAL["particle"]
        for kk in ("px", "py", "pz", "E"):
            e["incoming"][kk] -= e["particles"][n][kk]
        e["particles"][n]["status"] = 2
    bad("a track mapped to a particle that is not a final-state particle", "EVT_SCENE_BIJECTION",
        lambda: run(with_ev(EV, to_decayed), BASE), "not a final-state particle")

    # shader gates
    def raw_text(root):
        cs = next(shape(root, f"trk_{k}").iter("ComposedShader"))
        cs = root.find(".//*[@DEF='trkShader']") if cs.get("USE") else cs
        sp = ET.SubElement(cs, "ShaderPart", {"type": "VERTEX"})
        sp.text = "void main() { }"
    bad("a ShaderPart that carries raw source text with no url", "EVT_SHADER", lambda: run(EV, mut(BASE, raw_text)), "raw source")

    def no_clock_field(root):
        for cs in root.iter("ComposedShader"):
            for f in list(cs):
                if f.tag == "field" and f.get("name") == SPEC["scene"]["shader"]["time_field"]:
                    cs.remove(f)
    bad("the shader declares no clock field", "EVT_SHADER", lambda: run(EV, mut(BASE, no_clock_field)), "declares no field")

    def rename_decl(root):
        for sp in root.iter("ShaderPart"):
            if sp.get("type") == "VERTEX":
                sp.set("url", sp.get("url").replace("attribute float a_species", "attribute float a_speciez"))
    bad("the vertex shader never declares an attribute the geometry supplies", "EVT_SHADER", lambda: run(EV, mut(BASE, rename_decl)), "never declares attribute")

    def neg_birth(v):
        for i in range(3, len(v), 4):
            v[i] = -1.0
    bad("a_ident birth time is negative", "EVT_SHADER", lambda: run(EV, mut(BASE, edit_ident(neg_birth))), "birth_s")

    # the driver that resolves the scene path
    with tempfile.TemporaryDirectory(prefix="hepevent-files-") as d:
        def one(name, scene_field):
            f = Path(d) / name
            f.write_text(json.dumps({**EV, "scene": scene_field}))
            return f
        bad("no event files matched", "EVT_PARSE", lambda: hepevent.check_files([], SPEC), "no event files matched")
        bad("the event names a scene above its own directory", "EVT_PARSE", lambda: hepevent.check_files([one("up.event.json", "../x.x3d")], SPEC), "must be relative")
        bad("the event names a scene file that is not there", "EVT_PARSE", lambda: hepevent.check_files([one("gone.event.json", "nope.x3d")], SPEC), "is missing")
    rows.append({"case": "builder shader hygiene: no '#', '%', quote, '//' or 'active', and no integer literal where a float is meant (positive control)",
                 "passed": True, "detail": builder_hygiene()})
    return rows


# ---------------------------------------------------------------- look v2: the merged convention
def strips_of(root, name):
    """Decode a merged shape's TriangleStripSet into strips: [{"v": [xyz, ...], "attrs": {name: [row, ...]}}]."""
    sh = shape(root, name)
    g = next(c for c in sh if c.tag == "TriangleStripSet")
    co = next(c for c in g if c.tag == "Coordinate")
    flat = [float(v) for v in co.get("point").split()]
    pts = [tuple(flat[i:i + 3]) for i in range(0, len(flat), 3)]
    fvas = [c for c in g if c.tag == "FloatVertexAttribute"]
    cols = {f.get("name"): (int(f.get("numComponents")), [float(v) for v in f.get("value").split()]) for f in fvas}
    out, start = [], 0
    for cnt in [int(v) for v in g.get("stripCount").split()]:
        out.append({"v": pts[start:start + cnt],
                    "attrs": {n: [vals[nc * i:nc * (i + 1)] for i in range(start, start + cnt)] for n, (nc, vals) in cols.items()}})
        start += cnt
    return sh, g, out


def write_strips(g, strips):
    co = next(c for c in g if c.tag == "Coordinate")
    g.set("stripCount", " ".join(str(len(s["v"])) for s in strips))
    co.set("point", " ".join(f"{q:.6f}" for s in strips for v in s["v"] for q in v))
    for f in (c for c in g if c.tag == "FloatVertexAttribute"):
        n = f.get("name")
        f.set("value", " ".join(f"{q:.6g}" for s in strips for row in s["attrs"][n] for q in row))


def strip_mut(name, fn):
    """A scene edit: decode `name`'s strips, let fn change the list in place, encode them back."""
    def f(root):
        _sh, g, st = strips_of(root, name)
        fn(st, root)
        write_strips(g, st)
    return f


def strip_of_track(st, k):
    return next(i for i, s in enumerate(st) if int(s["attrs"]["a_ident"][0][0]) == k)


def ribbon(centre, rows):
    """Strip in the declared ribbon form around centreline points, rows copied to both vertices of a pair."""
    ox, oy, oz = 0.004, 0.0028, 0.0012
    v, a = [], {n: [] for n in rows}
    for i, c in enumerate(centre):
        for side in (-1, 1):
            v.append((c[0] + side * ox, c[1] + side * oy, c[2] + side * oz))
            for n, rr in rows.items():
                a[n].append(list(rr[i]))
    return {"v": v, "attrs": a}


def move_pair(strip, i, fn):
    """Move ribbon point i (a vertex pair) to fn(its centre), keeping the declared offset, so only the path changes."""
    a, b = strip["v"][2 * i], strip["v"][2 * i + 1]
    c = fn(tuple(0.5 * (a[q] + b[q]) for q in range(3)))
    strip["v"][2 * i] = (c[0] - 0.004, c[1] - 0.0028, c[2] - 0.0012)
    strip["v"][2 * i + 1] = (c[0] + 0.004, c[1] + 0.0028, c[2] + 0.0012)


def merged_controls():
    rows = []
    ok = lambda name, fn: rows.append({"case": name, **passes(fn)})  # noqa: E731
    bad = lambda name, code, fn, why=None: rows.append({"case": name, **expect(code, fn, why)})  # noqa: E731
    v2 = lambda ev: bs.build_v2(ev, SHA)[0]  # noqa: E731
    B2, Z2 = v2(EV), v2(ZMM)

    # ---- positive controls: the same events drawn with look v2 (ribbons merged into strips, muon extensions, tower spikes)
    r = passes(lambda: run(ZMM, Z2))
    if r["inventory"]["scene"]["track_shapes"] != 2 or r["measured"]["shader"]["extensions_with_shader"] != 2:
        raise RuntimeError(f"INVENTORY: a v2 pass must report both muons and both extensions, got {r['inventory']['scene']} {r['measured']['shader']}")
    rows.append({"case": "look v2: exact Z -> mu mu, both muons merged into one strip set and drawn on through the calorimeter (positive control)", **r})
    ok("look v2: toy shower of 40, merged ribbons, muon extensions, tower spikes (positive control)", lambda: run(EV, B2))
    big = ee.toy_shower(400, 11)
    ok("look v2: toy shower of 400 (positive control, scale)", lambda: run(big, v2(big)))
    if v2(EV) != B2:
        raise RuntimeError("DETERMINISM: two v2 builds of one event differ")
    rows.append({"case": "look v2 build is deterministic (two builds byte-identical; positive control)", "passed": True})
    k = LOW["i"]

    # ---- look v3 (the fidelity pass): new shaders over the SAME geometry and attributes, so it must read exactly as v2
    v3 = lambda ev: bs.build_v2(ev, SHA, look="v3")[0]  # noqa: E731
    B3, Z3 = v3(EV), v3(ZMM)
    ok("look v3: exact Z -> mu mu (positive control)", lambda: run(ZMM, Z3))
    ok("look v3: toy shower of 40 (positive control)", lambda: run(EV, B3))
    geo = lambda txt: [(e.tag, sorted(e.attrib.items())) for e in ET.fromstring(txt.split("?>", 1)[1]).iter()  # noqa: E731
                       if e.tag in ("Coordinate", "FloatVertexAttribute", "TriangleStripSet", "IndexedTriangleSet", "Normal")]
    if geo(B3) != geo(B2) or geo(Z3) != geo(Z2) or B3 == B2:
        raise RuntimeError("LOOK V3: v3 must change only shaders, never coordinates, strips or attributes")
    rows.append({"case": "look v3 keeps every coordinate, strip and vertex attribute of v2 and changes the shaders (positive control)", "passed": True})
    bad("look v3: one track's strip deleted from the merged set", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(B3, strip_mut("trkset_0", lambda st, _r: st.pop(strip_of_track(st, k))))), f"trk_{k}")

    k = LOW["i"]
    # ---- the convention must be declared, or a merged shape is never read
    bad("a merged shape read with a spec that declares no scene.merged", "EVT_SCENE_BIJECTION",
        lambda: run(EV, B2, edit(lambda s: s["scene"].pop("merged"))), "declares no scene.merged")
    bad("scene.merged.offset_tol_m as wide as the ribbon itself", "EVT_SPEC",
        lambda: run(EV, B2, edit(lambda s: s["scene"]["merged"].__setitem__("offset_tol_m", 0.01))), "offset_tol_m")
    bad("scene.merged without scene.shader", "EVT_SPEC",
        lambda: run(EV, B2, edit(lambda s: s["scene"].pop("shader"))), "needs scene.shader")
    bad("scene.merged.extensions.pdg missing", "EVT_SPEC",
        lambda: run(EV, B2, edit(lambda s: s["scene"]["merged"]["extensions"].pop("pdg"))), "extensions.pdg")

    # ---- bijection through the merged strips
    bad("look v2: one track's strip deleted from the merged set", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", lambda st, _r: st.pop(strip_of_track(st, k))))), f"trk_{k}")
    bad("look v2: one track's strip copied, so it is drawn twice", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", lambda st, _r: st.append(copy.deepcopy(st[strip_of_track(st, k)]))))), "drawn 2 times")

    def use_set(root):
        parents(root)[shape(root, "trkset_0")].append(ET.Element("Shape", {"USE": "trkset_0"}))
    bad("look v2: a USE of the whole merged track set", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(B2, use_set)), "drawn 2 times")

    def hide_set(root):
        s = shape(root, "trkset_0")
        pm = parents(root)[s]
        i = list(pm).index(s)
        pm.remove(s)
        sw = ET.Element("Switch", {"whichChoice": "-1"})
        sw.append(s)
        pm.insert(i, sw)
    bad("look v2: the merged track set inside a Switch that selects nothing", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(B2, hide_set)), "hidden")

    def ident_id(new):
        def f(st, _r):
            s = st[strip_of_track(st, k)]
            for row in s["attrs"]["a_ident"]:
                row[0] = new
        return f
    bad("look v2: a strip whose a_ident names track 999", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(B2, strip_mut("trkset_0", ident_id(999)))), "maps to no track")
    bad("look v2: a strip whose a_ident id is 1.5, not an index", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(B2, strip_mut("trkset_0", ident_id(1.5)))), "not a track or tower index")

    def odd(st, _r):
        s = st[strip_of_track(st, k)]
        s["v"].pop()
        for n in s["attrs"]:
            s["attrs"][n].pop()
    bad("look v2: a strip with an odd vertex count", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(B2, strip_mut("trkset_0", odd))), "vertex pair per point")

    def collapse(st, _r):
        s = st[strip_of_track(st, k)]
        s["v"][1] = s["v"][0]
    bad("look v2: a vertex pair collapsed to one point (the zero-area crash trap, and no longer the declared ribbon)", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", collapse))), "not offset by the declared")

    def no_tss(root):
        s = shape(root, "trkset_0")
        g = next(c for c in s if c.tag == "TriangleStripSet")
        s.remove(g)
        s.append(ET.Element("IndexedLineSet", {"coordIndex": "0 1 -1"}))
    bad("look v2: a merged track set with no TriangleStripSet", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(B2, no_tss)), "without a TriangleStripSet")

    def count_off(root):
        g = next(c for c in shape(root, "trkset_0") if c.tag == "TriangleStripSet")
        c = g.get("stripCount").split()
        c[0] = str(int(c[0]) + 2)
        g.set("stripCount", " ".join(c))
    bad("look v2: stripCount adds up to more vertices than the Coordinate holds", "EVT_PARSE", lambda: run(EV, mut(B2, count_off)), "stripCount adds up")

    # ---- geometry and binding through the strips
    def far(st, _r):
        s = st[strip_of_track(st, k)]
        move_pair(s, len(s["v"]) // 2 - 1, lambda c: tuple(q * 4 for q in c))
    bad("look v2: a ribbon's last pair moved outside the tracker", "EVT_CONTAINMENT", lambda: run(EV, mut(B2, strip_mut("trkset_0", far))), "outside the tracker")

    def charge(st, _r):
        for row in st[strip_of_track(st, k)]["attrs"]["a_ident"]:
            row[1] = -row[1]
    bad("look v2: a_ident charge flipped on one strip (the hue would be wrong)", "EVT_SHADER", lambda: run(EV, mut(B2, strip_mut("trkset_0", charge))), "contradicts the event charge")

    def pair_pt(st, _r):
        rws = st[strip_of_track(st, k)]["attrs"]["a_ident"]
        for i in range(1, len(rws), 2):
            rws[i][2] = rws[i][2] * 2
    bad("look v2: a_ident differs between the two edges of a ribbon", "EVT_SHADER", lambda: run(EV, mut(B2, strip_mut("trkset_0", pair_pt))), "differs between the two vertices")

    def flat_set(root):
        ap = next(c for c in shape(root, "trkset_0") if c.tag == "Appearance")
        for c in list(ap):
            if c.tag == "ComposedShader":
                ap.remove(c)
        ap.append(ET.Element("Material", {"emissiveColor": "1 1 1"}))
    bad("look v2: the merged track set drawn with a Material and no shader", "EVT_SHADER", lambda: run(EV, mut(B2, flat_set)), "no ComposedShader")

    # ---- muons, and only muons, pass the calorimeter
    mu_k = next(t["i"] for t in ZMM["tracks"])
    bad("look v2: the muon extensions deleted, so muons stop at the tracker", "EVT_SCENE_BIJECTION",
        lambda: run(ZMM, mut(Z2, lambda root: parents(root)[shape(root, "muext_0")].remove(shape(root, "muext_0")))), "leaves the tracker but is not drawn on")

    def shift_ext(st, _r):
        s = st[0]
        s["v"] = [(v[0] + 0.1, v[1], v[2]) for v in s["v"]]
    bad("look v2: a muon extension shifted 10 cm off its track's exit point", "EVT_SCENE_BIJECTION",
        lambda: run(ZMM, mut(Z2, strip_mut("muext_0", shift_ext))), "it is not the same trajectory")

    def stretch_ext(st, _r):
        move_pair(st[0], len(st[0]["v"]) // 2 - 1, lambda c: tuple(q * 3 for q in c))
    bad("look v2: a muon extension running out past the muon system", "EVT_CONTAINMENT",
        lambda: run(ZMM, mut(Z2, strip_mut("muext_0", stretch_ext))), "outside the muon system")
    bad("look v2: a muon drawn with two extensions", "EVT_SCENE_BIJECTION",
        lambda: run(ZMM, mut(Z2, strip_mut("muext_0", lambda st, _r: st.append(copy.deepcopy(st[0]))))), "extensions drawn")

    def ext_pt(st, _r):
        for row in st[0]["attrs"]["a_ident"]:
            row[2] = row[2] * 1.5
    bad("look v2: a muon extension whose a_ident pT is not its track's", "EVT_SHADER",
        lambda: run(ZMM, mut(Z2, strip_mut("muext_0", ext_pt))), "differs from the event pT")

    # a charged hadron that leaves the tracker, given an extension in exactly the muon form: only its pdg is wrong
    det = EV["detector"]
    hadron = None
    for t in EV["tracks"]:
        p = EV["particles"][t["particle"]]
        if t["charge"] != 0 and abs(p["pdg"]) not in (11, 13):
            pts, arcs = bs.sample_track(t, det, 2.5, bs.V2_DPHI)
            ext = bs.muon_extension(pts, arcs, det) if len(pts) >= 2 else None
            if ext:
                hadron = (t, ext)
                break
    if hadron is None:
        raise RuntimeError("FIXTURE: the toy shower has no charged hadron that leaves the tracker")

    def hadron_ext(st, root):
        t, (e_pts, e_arcs) = hadron
        _sh, _g, trk = strips_of(root, "trkset_0")
        row = trk[strip_of_track(trk, t["i"])]["attrs"]["a_ident"][0]
        sp = trk[strip_of_track(trk, t["i"])]["attrs"]["a_species"][0]
        n = len(e_pts)
        st.append(ribbon(e_pts, {"a_ident": [row] * n, "a_arc": [[a] for a in e_arcs], "a_species": [sp] * n,
                                 "a_next": [list(q) for q in bs._forward(e_pts)], "a_look": [[0, 0.5, 1.0, 2]] * n}))
        for row_ in st[-1]["attrs"]["a_look"][0::2]:
            row_[0] = -1
        for row_ in st[-1]["attrs"]["a_look"][1::2]:
            row_[0] = 1
    bad("look v2: a charged hadron drawn on through the calorimeter like a muon", "EVT_CONTAINMENT",
        lambda: run(EV, mut(B2, strip_mut("muext_0", hadron_ext))), "only [13] may pass the calorimeter")

    # ---- the spiky crown: towers through the merged spikes
    def drop_tower(st, _r):
        st[:] = [s for s in st if int(s["attrs"]["a_cell"][0][0]) != 0]
    bad("look v2: every spike of tower 0 deleted", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(B2, strip_mut("twrset_0", drop_tower))), "twr_0")

    def tower_e(st, _r):
        for s in st:
            if int(s["attrs"]["a_cell"][0][0]) == 0:
                for row in s["attrs"]["a_cell"]:
                    row[1] = row[1] * 2
    bad("look v2: tower 0's a_cell energy doubled (the spikes would lie)", "EVT_SHADER", lambda: run(EV, mut(B2, strip_mut("twrset_0", tower_e))), "differs from the event tower energy")

    def tower_vary(st, _r):
        s = next(s for s in st if int(s["attrs"]["a_cell"][0][0]) == 0)
        for row in s["attrs"]["a_cell"]:
            row[2] = 0.123
    bad("look v2: one spike of tower 0 carries a different a_cell row", "EVT_SHADER", lambda: run(EV, mut(B2, strip_mut("twrset_0", tower_vary))), "varies between its spikes")

    def tower_twice(root):
        s = copy.deepcopy(shape(root, "twrset_0"))
        s.set("DEF", "twrset_1")
        parents(root)[shape(root, "twrset_0")].append(s)
    bad("look v2: the whole tower set copied into a second merged shape", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(B2, tower_twice)), "drawn 2 times")

    def tower_far(st, _r):
        s = next(s for s in st if int(s["attrs"]["a_cell"][0][0]) == 0)
        move_pair(s, len(s["v"]) // 2 - 1, lambda c: tuple(q * 2.5 for q in c))
    bad("look v2: a spike of tower 0 stretched outside the calorimeter", "EVT_CONTAINMENT", lambda: run(EV, mut(B2, strip_mut("twrset_0", tower_far))), "outside the calorimeter")

    def no_cell(root):
        g = next(c for c in shape(root, "twrset_0") if c.tag == "TriangleStripSet")
        for c in list(g):
            if c.tag == "FloatVertexAttribute" and c.get("name") == "a_cell":
                g.remove(c)
    bad("look v2: the tower set carries no a_cell attribute", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(B2, no_cell)), "carries no a_cell")

    # ---- controls added after the mutation pass found these gates unexercised (each must fail for its own reason)
    def tower_em(st, _r):
        for s in st:
            if int(s["attrs"]["a_cell"][0][0]) == 0:
                for row in s["attrs"]["a_cell"]:
                    row[2] = 1.5
    bad("look v2: tower 0's em fraction is 1.5", "EVT_SHADER", lambda: run(EV, mut(B2, strip_mut("twrset_0", tower_em))), "em_frac or arrival_s")

    def ext_pt_close(st, _r):
        for row in st[0]["attrs"]["a_ident"]:
            row[2] = row[2] * 1.005
    bad("look v2: a muon extension whose pT is 0.5 percent off its track's (inside the pT tolerance, so only the one-row rule sees it)", "EVT_SHADER",
        lambda: run(ZMM, mut(Z2, strip_mut("muext_0", ext_pt_close))), "one particle, one row")

    def ext_one(st, _r):
        s = st[0]
        s["v"] = s["v"][:2]
        for n in s["attrs"]:
            s["attrs"][n] = s["attrs"][n][:2]
    bad("look v2: a muon extension of a single point (one vertex pair draws nothing)", "EVT_SCENE_BIJECTION", lambda: run(ZMM, mut(Z2, strip_mut("muext_0", ext_one))), "two vertex pairs at least")

    def hide_ext(root):
        s = shape(root, "muext_0")
        pm = parents(root)[s]
        i = list(pm).index(s)
        pm.remove(s)
        sw = ET.Element("Switch", {"whichChoice": "-1"})
        sw.append(s)
        pm.insert(i, sw)
    bad("look v2: the muon extensions inside a Switch that selects nothing", "EVT_SCENE_BIJECTION", lambda: run(ZMM, mut(Z2, hide_ext)), "extension is hidden")

    def ext_unknown(st, _r):
        for row in st[0]["attrs"]["a_ident"]:
            row[0] = 999
    bad("look v2: an extension strip naming track 999", "EVT_SCENE_BIJECTION", lambda: run(ZMM, mut(Z2, strip_mut("muext_0", ext_unknown))), "maps to no track of the event")

    def ragged(root):
        co = next(c for c in next(c for c in shape(root, "trkset_0") if c.tag == "TriangleStripSet") if c.tag == "Coordinate")
        co.set("point", " ".join(co.get("point").split()[:-1]))
    bad("look v2: the merged Coordinate is not a list of xyz triples", "EVT_PARSE", lambda: run(EV, mut(B2, ragged)), "not a list of xyz triples")

    def nc5(root):
        g = next(c for c in shape(root, "trkset_0") if c.tag == "TriangleStripSet")
        next(c for c in g if c.get("name") == "a_species").set("numComponents", "5")
    bad("look v2: a merged attribute with numComponents 5", "EVT_PARSE", lambda: run(EV, mut(B2, nc5)), "numComponents")

    def short_ident(root):
        f = next(c for c in next(c for c in shape(root, "trkset_0") if c.tag == "TriangleStripSet") if c.get("name") == "a_ident")
        f.set("value", " ".join(f.get("value").split()[:-1]))
    bad("look v2: the merged a_ident one value short", "EVT_SHADER", lambda: run(EV, mut(B2, short_ident)), "expected 4 and")

    for label, fn, why in (
            ("scene.merged.offset_m with two components", lambda m: m.__setitem__("offset_m", [0.004, 0.0028]), "offset_m"),
            ("scene.merged.tower_cell with the wrong layout", lambda m: m["tower_cell"].__setitem__("layout", ["id", "E"]), "tower_cell"),
            ("scene.merged.tower_cell.e_rel_tol of 0.9", lambda m: m["tower_cell"].__setitem__("e_rel_tol", 0.9), "e_rel_tol"),
            ("scene.merged.extensions.r_max_m of 0", lambda m: m["extensions"].__setitem__("r_max_m", 0), "r_max_m"),
            ("scene.merged.extensions.join_tol_m of half a metre", lambda m: m["extensions"].__setitem__("join_tol_m", 0.5), "join_tol_m")):
        bad(label, "EVT_SPEC", lambda fn=fn: run(EV, B2, edit(lambda s: fn(s["scene"]["merged"]))), why)
    return rows


def review_controls():
    """Controls for the holes an independent review of look v2 found (2026-11-06). Each attack it made passed the
    witness then; each is now refused for its own reason. Scene graph first, then the path bound to the event, then the
    shader data that decides whether and how a track shows, then towers and muon extensions, then the spec."""
    rows = []
    ok = lambda name, fn: rows.append({"case": name, **passes(fn)})  # noqa: E731
    bad = lambda name, code, fn, why=None: rows.append({"case": name, **expect(code, fn, why)})  # noqa: E731
    v2 = lambda ev: bs.build_v2(ev, SHA)[0]  # noqa: E731
    B2, Z2 = v2(EV), v2(ZMM)
    k = LOW["i"]
    pion = next(t["i"] for t in EV["tracks"] if abs(EV["particles"][t["particle"]]["pdg"]) == 211)

    def scene_el(root):
        return next(c for c in root if c.tag == "Scene")

    def wrap(name, tag, attrs=None, first=None, child_attrs=None):
        """Move DEF `name` into a new `tag` element at its place; `first` is put inside before it."""
        def f(root):
            el = shape(root, name)
            p = parents(root)[el]
            i = list(p).index(el)
            p.remove(el)
            w = ET.Element(tag, attrs or {})
            for c in first or []:
                w.append(c)
            for a, v in (child_attrs or {}).items():
                el.set(a, v)
            w.append(el)
            p.insert(i, w)
        return f

    def add(xml):
        return lambda root: scene_el(root).append(ET.fromstring(xml))

    # ---- scene graph: what a browser would draw twice, not at all, or somewhere unknown
    bad("look v1: a rotated Group USE='tracks' draws every track a second time", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(BASE, add("<Transform rotation='0 0 1 1'><Group USE='tracks'/></Transform>"))), "drawn 2 times")
    bad("look v2: Group USE='tracks' draws every ribbon and muon extension a second time", "EVT_SCENE_BIJECTION",
        lambda: run(ZMM, mut(Z2, add("<Transform scale='3 3 3'><Group USE='tracks'/></Transform>"))), "drawn 2 times")
    bad("the tracks inside an LOD, which shows one level picked at run time", "EVT_PARSE",
        lambda: run(EV, mut(BASE, wrap("tracks", "LOD", {"range": "1e6"}, [ET.Element("Group")]))), "cannot expand: LOD")
    bad("the tracks inside a grouping node this reader does not model (CADAssembly)", "EVT_PARSE",
        lambda: run(ZMM, mut(Z2, wrap("tracks", "CADAssembly"))), "cannot expand: CADAssembly")
    bad("the tracks as a Collision proxy, which is never rendered", "EVT_SCENE_BIJECTION",
        lambda: run(ZMM, mut(Z2, wrap("tracks", "Collision", child_attrs={"containerField": "proxy"}))), "or a Collision proxy")
    meta = lambda: ET.Element("MetadataString", {"name": "note", "value": '"x"'})  # noqa: E731
    bad("a Switch whose first XML child is metadata: whichChoice 1 selects nothing, the tracks are choice 0", "EVT_SCENE_BIJECTION",
        lambda: run(ZMM, mut(Z2, wrap("tracks", "Switch", {"whichChoice": "1"}, [meta()]))), "hidden")
    ok("a Switch whose first XML child is metadata selects the tracks with whichChoice 0 (positive control: metadata is not a choice)",
       lambda: run(ZMM, mut(Z2, wrap("tracks", "Switch", {"whichChoice": "0"}, [meta()]))))
    bad("a track inside a Billboard, which turns it toward the viewer at run time", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(BASE, wrap("trk_3", "Billboard"))), "inside a Billboard")

    def reuse_geometry(root):
        g = next(c for c in shape(root, f"trk_{k}") if c.tag == "IndexedLineSet")
        g.set("DEF", "lineK")
        scene_el(root).append(ET.fromstring("<Shape><IndexedLineSet USE='lineK'/></Shape>"))
    bad("a second Shape that USEs one track's IndexedLineSet", "EVT_SCENE_BIJECTION", lambda: run(EV, mut(BASE, reuse_geometry)), "reuses the geometry of trk_")
    bad("a track Shape tucked inside a ParticleSystem, where the reader does not look", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(BASE, wrap("trk_3", "ParticleSystem"))), "where this reader does not look")
    bad("a Group USE='tracks' tucked inside a ParticleSystem", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(BASE, add("<ParticleSystem><Group USE='tracks'/></ParticleSystem>"))), "a USE of tracks sits inside")
    bad("a Group that USEs itself (a cycle)", "EVT_PARSE",
        lambda: run(EV, mut(BASE, add("<Group DEF='loopG'><Group USE='loopG'/></Group>"))), "a cycle")

    def laughs(root):
        sc = scene_el(root)
        sc.append(ET.fromstring("<Group DEF='lg0'><Shape/></Group>"))
        for lv in range(1, 7):
            sc.append(ET.fromstring(f"<Group DEF='lg{lv}'>" + f"<Group USE='lg{lv - 1}'/>" * 20 + "</Group>"))
    bad("USE nested six deep, twenty wide (64 million node visits)", "EVT_PARSE", lambda: run(EV, mut(BASE, laughs)), "expands to more than")

    # ---- the drawn path is bound to the event's own track
    def stub(st, _r):
        s = st[strip_of_track(st, k)]
        for i in range(len(s["v"]) // 2):
            move_pair(s, i, lambda c: tuple(q * 1e-3 for q in c))
    bad("look v2: one looping track drawn as a 1 mm stub at the vertex", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", stub))), "the drawing stops short")

    def shift(st, _r):
        s = st[strip_of_track(st, k)]
        for i in range(len(s["v"]) // 2):
            move_pair(s, i, lambda c: (c[0] + 0.015, c[1], c[2]))
    bad("look v2: one track's ribbon moved 15 mm off its vertex", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", shift))), "from its vertex")
    bad("look v2: the tracks rotated 0.5 rad about the beam (they no longer point at their towers)", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(B2, wrap("tracks", "Transform", {"rotation": "0 0 1 0.5"}))), "points the wrong way")
    bad("look v2: the tracks squashed to half their z (every dip angle wrong)", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(B2, wrap("tracks", "Transform", {"scale": "1 1 0.5"}))), "it is not this track's path")
    bad("look v1: the tracks shrunk a million times (every track below what can be fitted)", "EVT_UNITS",
        lambda: run(EV, mut(BASE, wrap("tracks", "Transform", {"scale": "1e-6 1e-6 1e-6"}))), "the drawing is shrunk")
    bad("look v1: the tracks scaled to 0 (every point on the beam axis)", "EVT_UNITS",
        lambda: run(EV, mut(BASE, wrap("tracks", "Transform", {"scale": "0 0 0"}))), "on the beam axis")
    bad("a field of 1 microtesla (gauss read as tesla)", "EVT_UNITS",
        lambda: run(with_ev(EV, lambda e: e["detector"].update(b_field_t=1e-6))), "outside 0.001 to 100 T")
    bad("a declared helix radius of 1e300 m for a track of pT 1e-300 GeV (no finite radius ratio)", "EVT_UNITS",
        lambda: run(with_ev(EV, lambda e: (e["tracks"][k]["helix"].update(radius_m=1e300), e["tracks"][k].update(pt=1e-300)))), "no finite radius ratio")

    # ---- shader data that decides when, whether and in what colour a track shows
    def birth_late(st, _r):
        for row in st[strip_of_track(st, k)]["attrs"]["a_ident"]:
            row[3] += 1.0
    bad("look v2: a track born one second late (its production time says now)", "EVT_SHADER",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", birth_late))), "appear at the wrong time")

    def electron(st, _r):
        for row in st[strip_of_track(st, pion)]["attrs"]["a_species"]:
            row[0] = 1.0
    bad("look v2: a pion coloured as an electron", "EVT_SHADER", lambda: run(EV, mut(B2, strip_mut("trkset_0", electron))), "the colour would be wrong")

    def arc_swap(st, _r):
        a = st[strip_of_track(st, k)]["attrs"]["a_arc"]
        a[2], a[3], a[4], a[5] = a[4], a[5], a[2], a[3]
    bad("look v2: two interior points' a_arc swapped (the growth front would jump back)", "EVT_SHADER",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", arc_swap))), "runs backwards")

    def v1_arc(fn):
        def f(root):
            fva = next(c for c in shape(root, f"trk_{k}").iter("FloatVertexAttribute") if c.get("name") == "a_arc")
            fva.set("value", " ".join(f"{fn(float(x)):g}" for x in fva.get("value").split()))
        return f
    bad("look v1: a_arc starts 5 cm along instead of at the vertex", "EVT_SHADER", lambda: run(EV, mut(BASE, v1_arc(lambda a: a + 0.05))), "starts at")
    bad("look v1: a_arc runs twice as long as the drawn path (the pulses would outrun it)", "EVT_SHADER",
        lambda: run(EV, mut(BASE, v1_arc(lambda a: 2 * a))), "the drawn path is")

    def ext_arc(root):
        for name in ("trkset_0", "muext_0"):
            _s, g, st = strips_of(root, name)
            for s in st:
                if int(s["attrs"]["a_ident"][0][0]) != 0:
                    continue
                for row in s["attrs"]["a_look"]:
                    row[2] += 0.05
                if name == "muext_0":
                    for row in s["attrs"]["a_arc"]:
                        row[0] += 0.05
            write_strips(g, st)
    bad("look v2: a muon extension's a_arc starts 5 cm past where its track ends", "EVT_SHADER", lambda: run(ZMM, mut(Z2, ext_arc)), "where its track ends")

    # ---- every vertex of a merged strip is read
    def no_look(root):
        g = next(c for c in shape(root, "twrset_0") if c.tag == "TriangleStripSet")
        g.remove(next(c for c in g if c.tag == "FloatVertexAttribute" and c.get("name") == "a_look"))
    bad("look v2: the tower set without a_look (the shader could not take the offset off)", "EVT_SHADER", lambda: run(EV, mut(B2, no_look)), "take the ribbon offset off")

    def side_swap(st, _r):
        s = st[strip_of_track(st, k)]
        s["attrs"]["a_look"][0][0], s["attrs"]["a_look"][1][0] = 1.0, -1.0
    bad("look v2: a_look side signs swapped on one ribbon pair", "EVT_SHADER", lambda: run(EV, mut(B2, strip_mut("trkset_0", side_swap))), "a_look.side is")

    def id_change(st, _r):
        s = st[strip_of_track(st, k)]
        other = next(int(q["attrs"]["a_ident"][0][0]) for q in st if int(q["attrs"]["a_ident"][0][0]) != k)
        s["attrs"]["a_ident"][-1][0] = s["attrs"]["a_ident"][-2][0] = float(other)
    bad("look v2: the last pair of one strip names another track", "EVT_SCENE_BIJECTION",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", id_change))), "changes along the strip")

    # ---- towers: both vertices, their own cell, their own shader and clock
    def tower0(fn):
        def f(st, _r):
            for s in st:
                if int(s["attrs"]["a_cell"][0][0]) == 0:
                    fn(s)
        return f

    def odd_e(s):
        for i in range(1, len(s["v"]), 2):
            s["attrs"]["a_cell"][i][1] *= 1.005
    bad("look v2: tower 0's odd vertices carry 0.5 percent more energy (inside the energy tolerance)", "EVT_SHADER",
        lambda: run(EV, mut(B2, strip_mut("twrset_0", tower0(odd_e)))), "two vertices of a spike pair")

    def turn(s):
        for i in range(len(s["v"]) // 2):
            move_pair(s, i, lambda c: (c[0] * math.cos(0.2) - c[1] * math.sin(0.2), c[0] * math.sin(0.2) + c[1] * math.cos(0.2), c[2]))
    bad("look v2: tower 0's spikes turned 0.2 rad into another phi cell", "EVT_CONTAINMENT",
        lambda: run(EV, mut(B2, strip_mut("twrset_0", tower0(turn)))), "drawn in another cell")

    def tip_up(s):
        move_pair(s, len(s["v"]) // 2 - 1, lambda c: (c[0], c[1], c[2] + 0.03))
    bad("look v2: a spike of tower 0 tilted 3 cm in z (no longer radial in its cell)", "EVT_CONTAINMENT",
        lambda: run(EV, mut(B2, strip_mut("twrset_0", tower0(tip_up)))), "m in z off")

    def tower_app(xml):
        def f(root):
            s = shape(root, "twrset_0")
            ap = next(c for c in s if c.tag == "Appearance")
            s.remove(ap)
            s.insert(0, ET.fromstring(xml))
        return f
    bad("look v2: the tower set drawn with a Material, no shader", "EVT_SHADER",
        lambda: run(EV, mut(B2, tower_app("<Appearance><Material emissiveColor='1 0.5 0'/></Appearance>"))), "twrset_0 has no ComposedShader")
    bad("look v2: the tower set bound to the haze shader, which declares no a_cell", "EVT_SHADER",
        lambda: run(EV, mut(B2, tower_app("<Appearance><ComposedShader USE='hazeShader2'/></Appearance>"))), "never declares attribute a_cell")

    def unclock(root):
        for r in list(root.iter("ROUTE")):
            if r.get("toNode") == "twrShader2":
                parents(root)[r].remove(r)
    bad("look v2: the tower shader's clock ROUTE removed", "EVT_SHADER", lambda: run(EV, mut(B2, unclock)), "the crown would never light")

    # ---- a_look: one row per particle, the right kind, the right fade length
    def look3(root):
        g = next(c for c in shape(root, "trkset_0") if c.tag == "TriangleStripSet")
        f = next(c for c in g if c.tag == "FloatVertexAttribute" and c.get("name") == "a_look")
        v = f.get("value").split()
        f.set("value", " ".join(x for i, x in enumerate(v) if i % 4 != 3))
        f.set("numComponents", "3")
    bad("look v2: a_look with 3 components (the kind is gone)", "EVT_SHADER", lambda: run(EV, mut(B2, look3)), "has 3 components")

    def seed_change(st, _r):
        s = st[strip_of_track(st, k)]
        s["attrs"]["a_look"][2][1] = s["attrs"]["a_look"][3][1] = 0.999
    bad("look v2: a_look seed changes at one point of a ribbon", "EVT_SHADER",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", seed_change))), "differ along the strip")

    def neutral_as_charged(st, _r):
        for row in st[strip_of_track(st, NEUTRAL["i"])]["attrs"]["a_look"]:
            row[3] = 0.0
    bad("look v2: a neutral drawn with the charged kind (solid, not dashed)", "EVT_SHADER",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", neutral_as_charged))), "drawn as another kind")

    def drawn_long(st, _r):
        for row in st[strip_of_track(st, k)]["attrs"]["a_look"]:
            row[2] += 1.0
    bad("look v2: a_look.drawn_m one metre longer than the path", "EVT_SHADER",
        lambda: run(EV, mut(B2, strip_mut("trkset_0", drawn_long))), "the path it fades along ends at")

    # ---- muon extensions: only for muons that leave, starting on the boundary, straight on, outward
    lev = copy.deepcopy(EV)
    det = lev["detector"]
    loop = next(t for t in lev["tracks"] if t["charge"] != 0
                and math.hypot(*bs.sample_track(t, det, 2.5, bs.V2_DPHI)[0][-1][:2]) < det["tracker"]["r_max_m"] - 0.1
                and abs(bs.sample_track(t, det, 2.5, bs.V2_DPHI)[0][-1][2]) < det["tracker"]["half_length_m"] - 0.1)
    lev["particles"][loop["particle"]]["pdg"] = -13 if loop["charge"] > 0 else 13
    LS = v2(lev)
    ok("a looping muon that never leaves the tracker, drawn with no extension (positive control)", lambda: run(lev, LS))

    def looper_ext(root):
        _sh, _g, trk = strips_of(root, "trkset_0")
        s = trk[strip_of_track(trk, loop["i"])]
        a, b = s["v"][-2], s["v"][-1]
        end = tuple(0.5 * (a[q] + b[q]) for q in range(3))
        r = math.hypot(end[0], end[1])
        u = (end[0] / r, end[1] / r)
        centre = [(end[0] + u[0] * d, end[1] + u[1] * d, end[2]) for d in (0.0, 0.5, 1.0, 1.5, 2.0)]
        n = len(centre)
        st = ribbon(centre, {"a_ident": [s["attrs"]["a_ident"][0]] * n, "a_arc": [[s["attrs"]["a_arc"][-1][0] + 0.5 * i] for i in range(n)],
                             "a_species": [s["attrs"]["a_species"][0]] * n, "a_next": [list(q) for q in bs._forward(centre)],
                             "a_look": [list(s["attrs"]["a_look"][0][:3]) + [2.0]] * n})
        for i, rr in enumerate(st["attrs"]["a_look"]):
            rr[0] = -1.0 if i % 2 == 0 else 1.0
        ext = ET.fromstring(ET.tostring(shape(root, "trkset_0")))
        ext.set("DEF", "muext_9")
        write_strips(next(c for c in ext if c.tag == "TriangleStripSet"), [st])
        parents(root)[shape(root, "trkset_0")].append(ext)
    bad("look v2: that looping muon given an extension straight out from its looping end", "EVT_CONTAINMENT",
        lambda: run(lev, mut(LS, looper_ext)), "never leaves the tracker")

    fwd = forward_event()
    F2 = v2(fwd)
    mu = next(t["i"] for t in fwd["tracks"] if abs(fwd["particles"][t["particle"]]["pdg"]) == 13)

    def pull_back(root):
        # the forward muon's last point and its extension's first point moved 3 cm back along the line, together:
        # the xy reach barely changes (eta 3.6), the join still holds, but the extension now starts inside the tracker
        for name in ("trkset_0", "muext_0"):
            _s, g, st = strips_of(root, name)
            for s in st:
                if int(s["attrs"]["a_ident"][0][0]) != mu:
                    continue
                i = len(s["v"]) // 2 - 1 if name == "trkset_0" else 0
                move_pair(s, i, lambda c: tuple(q * (1 - 0.03 / 2.8) for q in c))
            write_strips(g, st)
    bad("look v2: a forward muon's extension starting 3 cm inside the endcap face", "EVT_SCENE_BIJECTION",
        lambda: run(fwd, mut(F2, pull_back)), "not on its boundary")

    def ext_turn(st, _r):
        s = st[0]
        o = [0.5 * (s["v"][0][q] + s["v"][1][q]) for q in range(3)]
        c, sn = math.cos(0.35), math.sin(0.35)
        for i in range(1, len(s["v"]) // 2):
            move_pair(s, i, lambda p: (o[0] + c * (p[0] - o[0]) - sn * (p[1] - o[1]), o[1] + sn * (p[0] - o[0]) + c * (p[1] - o[1]), p[2]))
    bad("look v2: a muon extension turned 20 degrees where it joins its track", "EVT_SCENE_BIJECTION",
        lambda: run(ZMM, mut(Z2, strip_mut("muext_0", ext_turn))), "degrees where it joins")

    def ext_back(st, _r):
        s = st[0]
        move_pair(s, len(s["v"]) // 2 - 1, lambda p: (0.5, 0.0, 0.0))
    bad("look v2: a muon extension whose last point is back inside the tracker", "EVT_CONTAINMENT",
        lambda: run(ZMM, mut(Z2, strip_mut("muext_0", ext_back))), "back inside the tracker")

    # ---- the spec must declare what binds a drawing to its event
    bad("spec without scene.reach", "EVT_SPEC", lambda: run(EV, BASE, edit(lambda s: s["scene"].pop("reach"))), "scene.reach")
    bad("spec whose reach start tolerance is half a metre", "EVT_SPEC",
        lambda: run(EV, BASE, edit(lambda s: s["scene"]["reach"].update(start_tol_m=0.5))), "looser is not the same path")
    bad("spec without scene.shader.birth", "EVT_SPEC", lambda: run(EV, BASE, edit(lambda s: s["scene"]["shader"].pop("birth"))), "scene.shader.birth")
    bad("spec whose arc attribute is not one it lists", "EVT_SPEC",
        lambda: run(EV, BASE, edit(lambda s: s["scene"]["shader"]["arc"].update(name="a_nowhere"))), "scene.shader.arc")
    bad("spec without scene.shader.species", "EVT_SPEC", lambda: run(EV, BASE, edit(lambda s: s["scene"]["shader"].pop("species"))), "scene.shader.species")
    bad("spec whose a_look layout is reordered", "EVT_SPEC",
        lambda: run(EV, B2, edit(lambda s: s["scene"]["merged"]["look"].update(track_layout=["seed", "side", "drawn_m", "kind"]))), "scene.merged.look")
    bad("spec without the tower cell size", "EVT_SPEC",
        lambda: run(EV, B2, edit(lambda s: s["scene"]["merged"]["tower_cell"].pop("cell_dphi"))), "cell_deta and cell_dphi")
    bad("spec without the extension join angle", "EVT_SPEC",
        lambda: run(EV, B2, edit(lambda s: s["scene"]["merged"]["extensions"].pop("join_angle_deg"))), "join_angle_deg")
    return rows


def builder_hygiene():
    """The traps the Loom has paid for, applied to the shader text the builder writes (the builder also refuses them itself)."""
    import re
    out = {}
    for name, (v, f) in {**bs.shaders(), **bs.shaders_v2()}.items():
        for part, src in (("vertex", v), ("fragment", f)):
            for bad_ in ("#", "%", '"', "'", "//"):
                if bad_ in src:
                    raise RuntimeError(f"HYGIENE: {name} {part} shader contains {bad_!r}")
            if re.search(r"\bactive\b", src):
                raise RuntimeError(f"HYGIENE: {name} {part} shader uses the reserved word 'active'")
            ints = re.findall(r"(?<![\w.])\d+(?![\w.])", src)
            if ints:
                raise RuntimeError(f"HYGIENE: {name} {part} shader has integer literals {ints[:5]}")
            if src.count("{") != src.count("}") or src.count("(") != src.count(")"):
                raise RuntimeError(f"HYGIENE: {name} {part} shader has unbalanced brackets")
            if "void main" not in src or "gl_Position" not in src and part == "vertex" or "gl_FragColor" not in src and part == "fragment":
                raise RuntimeError(f"HYGIENE: {name} {part} shader lacks its entry or output")
        out[name] = {"vertex_chars": len(v), "fragment_chars": len(f)}
    return out


def cli_controls():
    """The CLI writes a witness record: pass on the clean candidate, fail with the intended code when a track is deleted."""
    rows = []

    def drop_trk(root):
        s = shape(root, f"trk_{LOW['i']}")
        parents(root)[s].remove(s)
    for label, scene, want in (("clean", BASE, ("pass", "")), ("a track deleted from the scene", mut(BASE, drop_trk), ("fail", "EVT_SCENE_BIJECTION"))):
        with tempfile.TemporaryDirectory(prefix="hepevent-") as d:
            root, ev_dir = Path(d) / "cand", Path(d) / "cand/events"
            ev_dir.mkdir(parents=True)
            (ev_dir / "shower.x3d").write_text(scene)
            (ev_dir / "shower.event.json").write_text(json.dumps({**EV, "scene": "shower.x3d"}))
            (Path(d) / "spec.json").write_text(json.dumps(SPEC))
            p = subprocess.run([str(KIT / "loom"), "hepevent", str(root), "--evidence", str(Path(d) / "evidence"), "--events", "events/*.event.json",
                                "--spec", str(Path(d) / "spec.json")], capture_output=True, text=True)
            rec = json.loads((Path(d) / "evidence/hep-event.json").read_text())
            if rec["status"] != want[0] or not rec["reason"].startswith(want[1]):
                raise RuntimeError(f"CLI_CONTROL: {label}: status {rec['status']}, reason {rec['reason']!r}, stdout {p.stdout}")
            rows.append({"case": f"CLI writes the hep-event witness ({label})", "status": rec["status"], "reason": rec["reason"], "coverage": rec["coverage"]})
    return rows


if __name__ == "__main__":
    if "--child" in sys.argv:
        print(json.dumps({"controls": controls() + merged_controls() + review_controls(), "cli": cli_controls(), "optimized": bool(sys.flags.optimize)}))
        sys.exit(0)
    report = {"schema": "loomkit.self-test/1", "suite": "hepevent",
              "scope": "Synthetic events (an exact two-body decay and a deterministic toy shower) and scenes written by the scene builder, then damaged one way at a time; not generator output and not rendered.",
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
    (KIT / "tests/hepevent-last-run.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    for m in report["modes"]:
        print(f"optimized={m['optimized']}: {m['negative_controls_caught']} negative controls caught with the intended code, "
              f"{m['positive_controls_passed']} positive controls pass, {m['cli_controls']} CLI controls")
