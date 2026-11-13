"""Batch 6: own-code ports of ideas from Ten Minute Physics 19 (differential equations and integrators), 23 (sweep and prune),
24 (Morton codes and a bounding volume hierarchy), under the Loom physics witness. No code copied.
Limits live in limits6.json, committed BEFORE the run; this script refuses to run if that file differs from its last commit and records the commit.
usage: tmp6.py OUTDIR ROOT | tmp6.py --replay NAME"""
import sys, json, math, hashlib, subprocess, time
import numpy as np
from pathlib import Path
def acc_h(x): return -x
def acc_k(p, mu=1.0): r = math.sqrt(p[0]*p[0]+p[1]*p[1]); return -mu*p/(r*r*r)
def step(method, acc, x, v, h):
    if method == 'euler': a = acc(x); return x+h*v, v+h*a
    if method == 'symplectic': v2 = v+h*acc(x); return x+h*v2, v2
    if method == 'midpoint':
        a = acc(x); xm = x+0.5*h*v; vm = v+0.5*h*a; return x+h*vm, v+h*acc(xm)
    if method == 'verlet': a = acc(x); x2 = x+h*v+0.5*h*h*a; return x2, v+0.5*h*(a+acc(x2))
    if method == 'rk4':
        a1 = acc(x); k1x, k1v = v, a1; x2 = x+0.5*h*k1x; k2x = v+0.5*h*k1v; k2v = acc(x2); x3 = x+0.5*h*k2x; k3x = v+0.5*h*k2v; k3v = acc(x3)
        x4 = x+h*k3x; k4x = v+h*k3v; k4v = acc(x4); return x+h/6*(k1x+2*k2x+2*k3x+k4x), v+h/6*(k1v+2*k2v+2*k3v+k4v)
    raise ValueError(method)
METHODS = ['euler', 'symplectic', 'midpoint', 'verlet', 'rk4']; ORDER = dict(euler=1, symplectic=1, midpoint=2, verlet=2, rk4=4)
def harmonic_err(method, N, T=2*math.pi):
    h = T/N; x, v = np.array(1.0), np.array(0.0)
    for _ in range(N): x, v = step(method, acc_h, x, v, h)
    return math.hypot(float(x)-math.cos(T), float(v)+math.sin(T))
def fit_order(method, Ns=(32, 64, 128, 256, 512)):
    hs = np.array([2*math.pi/n for n in Ns]); es = np.array([harmonic_err(method, n) for n in Ns]); return float(np.polyfit(np.log(hs), np.log(es), 1)[0]), es
KE = 0.6; KP0 = np.array([1-KE, 0.0]); KV0 = np.array([0.0, math.sqrt((1+KE)/(1-KE))])
def kepler_exact(t, e=KE):
    M = t % (2*math.pi); E = M if e < 0.8 else math.pi
    for _ in range(60): E -= (E-e*math.sin(E)-M)/(1-e*math.cos(E))
    return np.array([math.cos(E)-e, math.sqrt(1-e*e)*math.sin(E)])
def kepler_energy(p, v): return 0.5*float(v@v)-1.0/math.hypot(p[0], p[1])
def kepler_run(method, N_per_orbit, orbits, record=None):
    h = 2*math.pi/N_per_orbit; p, v = KP0.copy(), KV0.copy(); E0 = kepler_energy(p, v); dE = []; traj = [p.copy()]
    for k in range(N_per_orbit*orbits):
        p, v = step(method, acc_k, p, v, h); traj.append(p.copy())
        if (k+1) % (N_per_orbit//4 or 1) == 0 or True: dE.append(abs(kepler_energy(p, v)-E0)/abs(E0))
    return np.array(traj), np.array(dE), h
# ---------------------------- 23: sweep and prune ----------------------------
def sap_pairs(lo, hi, axis, key='left', count=None):
    """lo, hi: (n,2) box corners. sort by left edge on `axis`; each box tests following boxes while their left edge <= its right edge."""
    order = np.argsort(lo[:, axis] if key == 'left' else 0.5*(lo[:, axis]+hi[:, axis]), kind='stable'); pairs = set(); tests = 0; n = len(order); other = 1-axis
    L = lo[order]; H = hi[order]
    for i in range(n):
        for j in range(i+1, n):
            if L[j, axis] > H[i, axis]: break
            tests += 1
            if L[j, other] <= H[i, other] and L[i, other] <= H[j, other]:
                a, b = order[i], order[j]; pairs.add((min(a, b), max(a, b)))
    return pairs, tests
def brute_pairs_boxes(lo, hi):
    ov = (lo[:, None, :] <= hi[None, :, :]).all(-1) & (lo[None, :, :] <= hi[:, None, :]).all(-1); iu = np.triu_indices(len(lo), 1); m = ov[iu]
    return set(zip(iu[0][m].tolist(), iu[1][m].tolist()))
class Field:
    def __init__(s, n, W, Hh, seed=5, size=(0.06, 0.14)):
        rng = np.random.default_rng(seed); s.n, s.W, s.H = n, W, Hh; s.half = rng.uniform(size[0], size[1], (n, 2))/2; s.c = rng.uniform([0, 0], [W, Hh], (n, 2)); a = rng.uniform(0, 2*math.pi, n); s.v = np.stack([np.cos(a), np.sin(a)], 1)*rng.uniform(0.2, 0.6, (n, 1))
    def step(s, dt):
        s.c += s.v*dt; lo = s.half; hi = np.array([s.W, s.H])[None, :]-s.half
        for k in (0, 1):
            m = s.c[:, k] < lo[:, k]; s.c[m, k] = 2*lo[m, k]-s.c[m, k]; s.v[m, k] *= -1; m = s.c[:, k] > hi[:, k]; s.c[m, k] = 2*hi[m, k]-s.c[m, k]; s.v[m, k] *= -1
    def boxes(s): return s.c-s.half, s.c+s.half
# ---------------------------- 24: Morton codes and an LBVH ----------------------------
def part1by1(x):
    x = x.astype(np.uint64) & np.uint64(0xFFFF); x = (x | (x << np.uint64(8))) & np.uint64(0x00FF00FF); x = (x | (x << np.uint64(4))) & np.uint64(0x0F0F0F0F)
    x = (x | (x << np.uint64(2))) & np.uint64(0x33333333); x = (x | (x << np.uint64(1))) & np.uint64(0x55555555); return x
def morton2(ix, iy): return part1by1(ix) | (part1by1(iy) << np.uint64(1))
def morton_naive(ix, iy, bits=16):
    code = 0
    for b in range(bits): code |= ((ix >> b) & 1) << (2*b); code |= ((iy >> b) & 1) << (2*b+1)
    return code
class LBVH:
    """objects = boxes; one sort of Morton codes of the centres, then an implicit binary tree over the sorted array (median splits), bounds bottom up"""
    def __init__(s, lo, hi, bits=10, leaf=1):
        c = 0.5*(lo+hi); mn, mx = lo.min(0), hi.max(0); g = ((c-mn)/(mx-mn+1e-12)*((1 << bits)-1)).astype(np.int64)
        s.code = morton2(g[:, 0], g[:, 1]); s.order = np.argsort(s.code, kind='stable'); s.lo = lo[s.order]; s.hi = hi[s.order]; s.n = len(lo); s.leaf = leaf
        s.nodes = []   # (start, end, lo, hi, left, right)
        def build(a, b):
            idx = len(s.nodes); s.nodes.append(None); nlo = s.lo[a:b].min(0); nhi = s.hi[a:b].max(0)
            if b-a <= leaf: s.nodes[idx] = (a, b, nlo, nhi, -1, -1); return idx
            m = (a+b)//2; l = build(a, m); r = build(m, b); s.nodes[idx] = (a, b, nlo, nhi, l, r); return idx
        build(0, s.n)
    def query(s, qlo, qhi, shrink=0.0):
        hits = []; tests = 0; stack = [0]
        while stack:
            a, b, nlo, nhi, l, r = s.nodes[stack.pop()]; tests += 1
            if (nlo+shrink > qhi).any() or (nhi-shrink < qlo).any(): continue
            if l < 0:
                for k in range(a, b):
                    tests += 1
                    if (s.lo[k] <= qhi).all() and (s.hi[k] >= qlo).all(): hits.append(int(s.order[k]))
            else: stack.append(r); stack.append(l)
        return sorted(hits), tests
def h32(arr): return int(hashlib.sha256(np.asarray(arr, dtype='<f8').tobytes()).hexdigest()[:8], 16)
def trace_sha(hs): return hashlib.sha256(",".join(str(h) for h in hs).encode()).hexdigest()
def hash_ints(a): return int(hashlib.sha256(np.asarray(a, dtype='<i8').tobytes()).hexdigest()[:8], 16)
SAP_N, SAP_W, SAP_H, SAP_FRAMES = 200, 4.0, 1.0, 180
def sap_hashes(T=2.0):
    f = Field(SAP_N, SAP_W, SAP_H); hs = []
    for k in range(int(T*30)):
        f.step(1/30); lo, hi = f.boxes(); p, t = sap_pairs(lo, hi, 0); hs.append(h32(np.concatenate([f.c.ravel(), [len(p), t]])))
    return hs
def ode_hashes():
    tr, dE, h = kepler_run('rk4', 200, 2); return [h32(np.concatenate([tr[k], [dE[k]]])) for k in range(0, len(tr)-1, 8)]
def bvh_hashes():
    rng = np.random.default_rng(1); f = Field(1024, 4.0, 4.0, seed=9, size=(0.03, 0.06)); lo, hi = f.boxes(); T = LBVH(lo, hi); hs = [hash_ints(T.order)]
    for q in range(60):
        c = rng.uniform(0, 4, 2); h_, t_ = T.query(c-0.05, c+0.05); hs.append(hash_ints(np.array(h_+[t_], dtype=np.int64)))
    return hs
HASHERS = {'sap': sap_hashes, 'ode': ode_hashes, 'bvh': bvh_hashes}
if len(sys.argv) > 2 and sys.argv[1] == '--replay':
    print(json.dumps(HASHERS[sys.argv[2]]())); sys.exit(0)

OUT, ROOT = Path(sys.argv[1]), Path(sys.argv[2]); (OUT/'records').mkdir(parents=True, exist_ok=True)
LIMF = Path(__file__).with_name('limits6.json'); LIM = json.loads(LIMF.read_text())
def git(*a): return subprocess.run(['git', '-C', str(ROOT), *a], capture_output=True, text=True).stdout.strip()
rel = str(LIMF.resolve().relative_to(Path(ROOT).resolve()))
assert subprocess.run(['git', '-C', str(ROOT), 'diff', '--quiet', 'HEAD', '--', rel]).returncode == 0, "limits6.json differs from its commit: commit the limits before the run"
LIM_COMMIT = git('log', '-1', '--format=%H', '--', rel); assert LIM_COMMIT, "limits6.json is not committed"
def sha_file(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def replay_fresh(name): return json.loads(subprocess.run([sys.executable, '-I', __file__, '--replay', name], capture_output=True, text=True, check=True).stdout)
def replay_block(host, ref, other):
    mism = [i for i, (a, b) in enumerate(zip(ref, other)) if a != b]
    return dict(host=host, steps=len(other), mismatches=len(mism)+abs(len(ref)-len(other)), first_mismatch=(mism[0] if mism else None), trace_sha256=trace_sha(other))
PYV, NPV = sys.version.split()[0], np.__version__; HOST_REC = f"cpython-{PYV}-numpy-{NPV}"; HOST_FRESH = "numpy-fresh-process"
def ref_item(id_, observed, limit, source, rule="at most"):
    ok = observed <= limit if rule == "at most" else observed >= limit
    return dict(id=id_, observed=float(observed), limit=limit, declared_limit=limit, rule=rule, status="pass" if ok else "fail", source=source)
V6 = "docs/demos/ten-minute-physics/v6/"; PENDING = []
def record(*a): PENDING.append(a)
def write_record(rid, model_path, hashes, replays, refs, controls, not_shown, note):
    rec = dict(schema="loom.physics-run/1", id=rid, engine=dict(name="tmp-ports (numpy)", version=f"numpy-{NPV}", build=f"tmp6.py sha256 {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]}, python {PYV}"),
        model=dict(sha256=sha_file(OUT/Path(model_path).name), path=model_path, what="the X3D scene the port produced; parameters live in tmp6.py"),
        recorded=dict(host=HOST_REC, steps=len(hashes), hashes=hashes, trace_sha256=trace_sha(hashes)), replays=replays, references=refs, controls=controls, not_shown=not_shown, note=note,
        limits=dict(path=V6+"witness/limits6.json", commit=LIM_COMMIT, sha256=sha_file(LIMF)))
    (OUT/'records'/(rid.split('/')[-1]+'.physics.json')).write_text(json.dumps(rec, indent=1))
N = {}; t0 = time.time()
def f(a, p=3): return " ".join(("%.*f" % (p, x)).rstrip("0").rstrip(".") if abs(x) > 10**-p else "0" for x in np.ravel(a))
HEAD = lambda title, desc: f"""<?xml version="1.0" encoding="UTF-8"?>
<X3D profile='Full' version='4.0' xmlns:xsd='http://www.w3.org/2001/XMLSchema-instance' xsd:noNamespaceSchemaLocation='https://www.web3d.org/specifications/x3d-4.0.xsd'>
<head><meta name='title' content='{title}'/><meta name='description' content='{desc}'/><meta name='creator' content='x3d.io project; ports written from the published method of Matthias Mueller, Ten Minute Physics'/><meta name='reference' content='https://matthias-research.github.io/pages/tenMinutePhysics/'/></head>
<Scene><NavigationInfo type='"EXAMINE" "ANY"' headlight='false'/>
<Background skyColor='0.02 0.03 0.06 0.08 0.1 0.18' skyAngle='1.5708' groundColor='0.02 0.02 0.03 0.05 0.05 0.07' groundAngle='1.5708'/>
<DirectionalLight direction='-0.4 -1 -0.5' intensity='1.1' color='1 0.96 0.9'/><DirectionalLight direction='0.6 -0.3 0.7' intensity='0.4' color='0.6 0.7 1'/>
"""
def pm(base, rough=0.25, emis=None): return f"<Appearance><PhysicalMaterial baseColor='{base}' roughness='{rough}' metallic='0'" + (f" emissiveColor='{emis}'" if emis else "") + "/></Appearance>"
def line(pts, col, closed=False):
    idx = list(range(len(pts))) + ([0] if closed else []); return f"<Shape><Appearance><Material emissiveColor='{col}'/></Appearance><IndexedLineSet coordIndex='{' '.join(map(str, idx))} -1'><Coordinate point='{f(pts)}'/></IndexedLineSet></Shape>\n"
def rect(lo, hi, z=0.0): return [(lo[0], lo[1], z), (hi[0], lo[1], z), (hi[0], hi[1], z), (lo[0], hi[1], z)]
def mover(name, inner, pos, clk='CLK'):
    key = f(np.linspace(0, 1, len(pos)), 5); b = f"<Transform DEF='{name}' translation='{f(pos[0])}'>{inner}</Transform>\n"
    b += f"<PositionInterpolator DEF='{name}_P' key='{key}' keyValue='{' '.join(f(p) for p in pos)}'/><ROUTE fromNode='{clk}' fromField='fraction_changed' toNode='{name}_P' toField='set_fraction'/><ROUTE fromNode='{name}_P' fromField='value_changed' toNode='{name}' toField='set_translation'/>\n"
    return b
COL = dict(euler='1 0.3 0.25', symplectic='1 0.75 0.2', midpoint='0.4 0.9 0.4', verlet='0.3 0.8 1', rk4='0.75 0.5 1', exact='1 1 1')

# ---------------------------- 19: integrators ----------------------------
tol = LIM['order_tol']; ords = {}
for T_, key in ((1.0, 'T1'), (2*math.pi, 'T2pi')):
    for m in METHODS:
        Ns = (32, 64, 128, 256, 512); es = []
        for n in Ns:
            h = T_/n; x, v = np.array(1.0), np.array(0.0)
            for _ in range(n): x, v = step(m, acc_h, x, v, h)
            es.append(math.hypot(float(x)-math.cos(T_), float(v)+math.sin(T_)))
        ords[(key, m)] = (float(np.polyfit(np.log(T_/np.array(Ns)), np.log(es), 1)[0]), es)
KOUT = {}
for m in METHODS:
    tr, dE, h = kepler_run(m, LIM['kepler_steps_per_orbit'], LIM['kepler_orbits']); spo = LIM['kepler_steps_per_orbit']; ex5 = kepler_exact(5*2*math.pi)
    KOUT[m] = dict(dE_max=float(dE.max()), first10=float(dE[:10*spo].max()), last10=float(dE[-10*spo:].max()), pos5=float(np.linalg.norm(tr[5*spo]-ex5)))
growth = KOUT['verlet']['last10']/KOUT['verlet']['first10']; ratio_vr = KOUT['verlet']['pos5']/KOUT['rk4']['pos5']
N['ode'] = dict(orders={f"{k[0]}:{k[1]}": dict(order=v[0], errors=v[1]) for k, v in ords.items()}, kepler=KOUT, kepler_e=KE, kepler_steps_per_orbit=LIM['kepler_steps_per_orbit'], kepler_orbits=LIM['kepler_orbits'], verlet_growth=growth, verlet_over_rk4_pos5=ratio_vr)
hs = ode_hashes(); fr_ = replay_fresh('ode')
refs = []
for key, T_ in (('T1', 'T = 1'), ('T2pi', 'T = 2 pi')):
    for m in METHODS:
        want = LIM['orders_'+key][m]; refs.append(ref_item(f"harmonic oscillator, {m}: measured order of the end-point error (5 step sizes, {T_}) against {want}, absolute difference", abs(ords[(key, m)][0]-want), tol, "x'' = -x, exact solution cos t"))
refs += [ref_item("Kepler e = 0.6, velocity Verlet, 200 steps per orbit, 50 orbits: worst relative energy error", KOUT['verlet']['dE_max'], LIM['verlet_energy_max_rel'], "energy is conserved exactly by the continuous system"),
         ref_item("Kepler, velocity Verlet: worst energy error of the last 10 orbits over the first 10 (no secular growth)", growth, LIM['verlet_energy_growth_ratio_max'], "bounded energy error of a symplectic method"),
         ref_item("Kepler, RK4: position error after 5 orbits (m, a = 1)", KOUT['rk4']['pos5'], LIM['rk4_pos_err_5_orbits_max'], "Kepler's equation solved by Newton iteration, exact position"),
         ref_item("Kepler: Verlet position error over RK4's after 5 orbits (bounded energy is not accuracy)", ratio_vr, LIM['verlet_over_rk4_pos_err_5_orbits_min'], "same exact orbit", rule="at least")]
record("tmp-ports/19-ode-integrators", V6+"19-ode-integrators.x3d", hs, [replay_block(HOST_FRESH, hs, fr_)], refs,
       [dict(id="the Verlet energy test applied to explicit Euler must fail", expect="fail", observed_failed=bool(KOUT['euler']['dE_max'] > LIM['verlet_energy_max_rel']), observed=KOUT['euler']['dE_max']),
        dict(id="the order test for a claimed order 2 applied to explicit Euler must fail", expect="fail", observed_failed=bool(abs(ords[('T1', 'euler')][0]-2) > tol), observed=abs(ords[('T1', 'euler')][0]-2))],
       ["another machine", "stiff systems", "adaptive step sizes", "other eccentricities or step sizes"], "exact references: the harmonic oscillator's closed form and Kepler's equation")
SPO = 100; ORB = 3; kv = {m: kepler_run(m, SPO, ORB)[0] for m in METHODS}; exv = np.array([kepler_exact(k*2*math.pi/SPO) for k in range(SPO*ORB+1)])
s = HEAD("TMP 19 Integrators: five methods on one orbit", "Euler, symplectic Euler, midpoint, Verlet and RK4 on a Kepler orbit (e = 0.6) with 100 steps per orbit, against the exact orbit; plus the error-against-step-size chart. Idea of Ten Minute Physics 19.") + f"<TimeSensor DEF='CLK' cycleInterval='{4*ORB}' loop='true'/>\n"
cen = np.array([-KE, 0.0, 0.0]); z3 = lambda a: np.concatenate([a, np.zeros((len(a), 1))], 1)
s += f"<Transform translation='0 0 0'><Shape>{pm('1 0.9 0.4', 0.3, '0.8 0.6 0.1')}<Sphere radius='0.07'/></Shape></Transform>\n"
for m in ['exact']+METHODS:
    pts = exv if m == 'exact' else kv[m]; pts = np.clip(pts, -2.6, 2.6); col = COL[m]; s += line(z3(pts), col)
    s += mover("B_"+m.upper(), f"<Shape>{pm(col, 0.2, ' '.join(f'{float(c)*0.4:.2f}' for c in col.split()))}<Sphere radius='{0.06 if m == 'exact' else 0.045}'/></Shape>", z3(pts))
# chart: log10 error against log10 h (harmonic, T = 2 pi)
ox, oy, cw, ch = 3.0, -1.5, 2.8, 3.0; xs0, xs1, ys0, ys1 = -2.4, -0.7, -13.0, 0.5
s += line([(ox, oy, 0), (ox+cw, oy, 0), (ox+cw, oy+ch, 0), (ox, oy+ch, 0)], "0.5 0.55 0.65", True)
for m in METHODS:
    hs_ = np.log10(2*math.pi/np.array((32, 64, 128, 256, 512))); es_ = np.log10(np.array(ords[('T2pi', m)][1])); px = ox+(hs_-xs0)/(xs1-xs0)*cw; py = oy+(np.clip(es_, ys0, ys1)-ys0)/(ys1-ys0)*ch
    s += line(np.stack([px, py, np.zeros_like(px)], 1), COL[m])
s += "<!-- paths are clipped to a 5.2 box, so the Euler path is cut where it leaves; orbit (left): white exact, red Euler, gold symplectic Euler, green midpoint, blue Verlet, violet RK4; chart (right): log10 end-point error against log10 step size for the harmonic oscillator over one period; slopes are the orders -->\n"
s += "<Viewpoint description='orbit and chart' position='1.6 0 10.6' fieldOfView='0.9'/></Scene></X3D>\n"
(OUT/"19-ode-integrators.x3d").write_text(s); print('ode done', round(time.time()-t0), flush=True)

# ---------------------------- 23: sweep and prune ----------------------------
fld = Field(SAP_N, SAP_W, SAP_H); frames = []; ovl = []; tx = []; ty = []; miss = false = 0; cmiss = 0
for k in range(SAP_FRAMES):
    fld.step(1/30); lo, hi = fld.boxes(); b = brute_pairs_boxes(lo, hi); px, t1 = sap_pairs(lo, hi, 0); py, t2 = sap_pairs(lo, hi, 1); pc, _ = sap_pairs(lo, hi, 0, 'center')
    miss += len(b-px)+len(b-py); false += len(px-b)+len(py-b); cmiss += len(b-pc); tx.append(t1); ty.append(t2)
    inov = np.zeros(SAP_N, bool)
    for a, c in b: inov[a] = inov[c] = True
    frames.append((fld.c.copy(), inov)); ovl.append(len(b))
brute = SAP_N*(SAP_N-1)//2; scaling = {}
for nn in (100, 200, 400, 800):
    f2 = Field(nn, SAP_W*math.sqrt(nn/SAP_N), SAP_H*math.sqrt(nn/SAP_N)*1.0, seed=5); tot = 0
    for k in range(20): f2.step(1/30); lo, hi = f2.boxes(); tot += sap_pairs(lo, hi, 0)[1]
    scaling[nn] = tot/20
N['sap'] = dict(boxes=SAP_N, frames=SAP_FRAMES, field=[SAP_W, SAP_H], missed=miss, false=false, brute_pairs=brute, tests_x_mean=float(np.mean(tx)), tests_y_mean=float(np.mean(ty)), axis_ratio=float(np.mean(ty)/np.mean(tx)), x_over_brute=float(np.mean(tx)/brute),
                 overlaps_mean=float(np.mean(ovl)), center_sort_missed=cmiss, tests_by_n=scaling)
hs = sap_hashes(); fr_ = replay_fresh('sap')
record("tmp-ports/23-sweep-and-prune", V6+"23-sweep-and-prune.x3d", hs, [replay_block(HOST_FRESH, hs, fr_)],
       [ref_item("sweep and prune (either axis) pair set against the brute-force pair set: pairs missed over 180 frames", miss, LIM['sap_pairs_missed'], "set equality with O(n^2) search"),
        ref_item("sweep and prune pair set against the brute-force pair set: false pairs", false, LIM['sap_pairs_false'], "set equality with O(n^2) search"),
        ref_item("tests along the short axis over tests along the long axis of the field (choose the longest axis)", N['sap']['axis_ratio'], LIM['sap_axis_ratio_min'], "counted box tests, field 4 x 1", rule="at least"),
        ref_item("box tests along the long axis over all n(n-1)/2 pairs", N['sap']['x_over_brute'], LIM['sap_tests_over_brute_max'], "counted box tests")],
       [dict(id="the same check with the list sorted by box centre instead of left edge must miss pairs", expect="fail", observed_failed=bool(cmiss > 0), observed=cmiss)],
       ["a real broad phase with updating insertion sort", "3D", "timing (counts only, no clock)", "another machine"], "hash replay covers the first 2 s")
key = np.linspace(0, 1, SAP_FRAMES//2+1); sel = list(range(0, SAP_FRAMES, 2)); sel = sel+[SAP_FRAMES-1] if len(sel) < len(key) else sel[:len(key)]
s = HEAD("TMP 23 Sweep and prune: 200 boxes", "200 boxes drifting in a 4 by 1 field; the ones that overlap turn red. Sorted by left edge, each box tests only its right-hand neighbours. Idea of Ten Minute Physics 23.") + f"<TimeSensor DEF='CLK' cycleInterval='{SAP_FRAMES/30}' loop='true'/>\n"
s += f"<Transform translation='{SAP_W/2} {SAP_H/2} -0.1'><Shape>{pm('0.05 0.07 0.1',0.9)}<Box size='{SAP_W+0.1} {SAP_H+0.1} 0.02'/></Shape></Transform>\n"
hf = fld.half; k0 = f(np.linspace(0, 1, len(sel)), 5)
for i in range(SAP_N):
    s += f"<Transform DEF='X{i}' translation='{f(np.array([*frames[sel[0]][0][i], 0.0]))}'><Shape><Appearance><Material DEF='M{i}' diffuseColor='0.2 0.6 0.9' emissiveColor='0.03 0.1 0.2'/></Appearance><Box size='{2*hf[i,0]:.4f} {2*hf[i,1]:.4f} 0.05'/></Shape></Transform>"
    s += f"<PositionInterpolator DEF='X{i}_P' key='{k0}' keyValue='{' '.join(f(np.array([*frames[j][0][i], 0.0])) for j in sel)}'/><ROUTE fromNode='CLK' fromField='fraction_changed' toNode='X{i}_P' toField='set_fraction'/><ROUTE fromNode='X{i}_P' fromField='value_changed' toNode='X{i}' toField='set_translation'/>"
    s += f"<ColorInterpolator DEF='X{i}_C' key='{k0}' keyValue='{' '.join('1 0.25 0.2' if frames[j][1][i] else '0.2 0.6 0.9' for j in sel)}'/><ROUTE fromNode='CLK' fromField='fraction_changed' toNode='X{i}_C' toField='set_fraction'/><ROUTE fromNode='X{i}_C' fromField='value_changed' toNode='M{i}' toField='set_diffuseColor'/>\n"
cx0, cy0, cw, chh = 0.0, 1.25, SAP_W, 0.45
def ser(v, vmax): v = np.array(v)[sel]; return np.stack([cx0+np.linspace(0, cw, len(v)), cy0+np.minimum(v/vmax,1.0)*chh, np.zeros(len(v))], 1)
s += line([(cx0, cy0, 0), (cx0+cw, cy0, 0), (cx0+cw, cy0+chh, 0), (cx0, cy0+chh, 0)], "0.5 0.55 0.65", True) + line(ser(tx, brute*0.3), "0.3 0.85 1") + line(ser(ty, brute*0.3), "1 0.6 0.2") + line(ser([brute]*SAP_FRAMES, brute*0.3), "0.6 0.6 0.65")
s += "<!-- chart: box tests per frame (clipped at 30% of all pairs): cyan sweep along x (the long axis), orange sweep along y, grey all n(n-1)/2 pairs -->\n"
s += f"<Viewpoint description='front' position='{SAP_W/2} 0.9 4.6' fieldOfView='0.95'/></Scene></X3D>\n"
(OUT/"23-sweep-and-prune.x3d").write_text(s); print('sap done', round(time.time()-t0), flush=True)

# ---------------------------- 24: Morton codes and a BVH ----------------------------
rng = np.random.default_rng(1); ix = rng.integers(0, 1 << 16, 100000); iy = rng.integers(0, 1 << 16, 100000)
ix = np.concatenate([ix, [0, (1 << 16)-1, 0, (1 << 16)-1, 1, 2, 0xAAAA, 0x5555]]); iy = np.concatenate([iy, [0, (1 << 16)-1, (1 << 16)-1, 0, 0, 0, 0x5555, 0xAAAA]])
mm = int(sum(int(a) != morton_naive(int(x), int(y)) for a, x, y in zip(morton2(ix, iy), ix, iy)))
bf = Field(4096, 4.0, 4.0, seed=9, size=(0.03, 0.06)); blo, bhi = bf.boxes(); BT = LBVH(blo, bhi); wrong = 0; tt = 0; QN = 1000; ms = 0; hits_n = 0; rq = np.random.default_rng(2)
for q in range(QN):
    c = rq.uniform(0, 4, 2); ql, qh = c-0.05, c+0.05; h_, t_ = BT.query(ql, qh); br = sorted(np.where(((blo <= qh) & (bhi >= ql)).all(1))[0].tolist()); wrong += h_ != br; tt += t_; hits_n += len(br)
    ms += len(set(br)-set(BT.query(ql, qh, shrink=0.02)[0]))
N['bvh'] = dict(objects=4096, queries=QN, bits=10, morton_cases=int(len(ix)), morton_mismatches=mm, wrong_queries=int(wrong), tests_per_query=tt/QN, brute_per_query=4096, tests_over_brute=tt/QN/4096, hits_per_query=hits_n/QN, log2n=12, shrunk_bounds_missed=int(ms), tree_nodes=len(BT.nodes))
hs = bvh_hashes(); fr_ = replay_fresh('bvh')
record("tmp-ports/24-morton-bvh", V6+"24-morton-bvh.x3d", hs, [replay_block(HOST_FRESH, hs, fr_)],
       [ref_item("Morton code (bit trick) against the bit-by-bit loop over 100,008 inputs including the corners and the alternating patterns: mismatches", mm, LIM['morton_mismatches'], "naive interleave loop, 16 bits per axis"),
        ref_item("BVH built with one sort of Morton codes: queries whose hit set differs from brute force, of 1000 random boxes over 4096 objects", wrong, LIM['bvh_queries_wrong'], "set equality with O(n) search"),
        ref_item("BVH node and object tests per query over the brute-force test count", tt/QN/4096, LIM['bvh_tests_over_brute_max'], "counted tests")],
       [dict(id="the query check with every node box shrunk by 0.02 must miss hits", expect="fail", observed_failed=bool(ms > 0), observed=int(ms))],
       ["moving objects (the tree is rebuilt, not refit)", "construction speed (counts only, no clock)", "3D (2D here)", "another machine"], "hash replay covers the sort order and 60 queries")
sf = Field(1024, 4.0, 4.0, seed=9, size=(0.03, 0.06)); slo, shi = sf.boxes(); ST = LBVH(slo, shi); cc = 0.5*(slo+shi)[ST.order]; NF = 120; ang = np.linspace(0, 2*math.pi, NF+1)
qc = np.stack([2.0+1.2*np.cos(ang), 2.0+1.2*np.sin(2*ang)], 1); qh_ = 0.35; hit_frames = [ST.query(c-qh_, c+qh_)[0] for c in qc]; M = max(len(h) for h in hit_frames); ctr = 0.5*(slo+shi)
s = HEAD("TMP 24 Morton codes and a BVH: 1024 boxes, one sort", "A tree over 1024 boxes built from one sort of Morton codes; the Z-order curve, the first levels of the tree and a moving query box with its hits. Idea of Ten Minute Physics 24.") + "<TimeSensor DEF='CLK' cycleInterval='8' loop='true'/>\n"
s += f"<Transform translation='2 2 -0.1'><Shape>{pm('0.05 0.07 0.1',0.9)}<Box size='4.1 4.1 0.02'/></Shape></Transform>\n"
s += line(np.concatenate([cc, np.zeros((len(cc), 1))], 1), "0.25 0.45 0.7")
dcol = ['1 1 1', '1 0.8 0.3', '0.4 0.9 0.5', '0.3 0.8 1', '0.75 0.5 1']
for d in range(1, 6):
    for (a, b, nlo, nhi, l, r) in ST.nodes:
        pass
def level_nodes(depth):
    out = []
    def walk(i, d):
        a, b, nlo, nhi, l, r = ST.nodes[i]
        if d == depth or l < 0: out.append((nlo, nhi)); return
        walk(l, d+1); walk(r, d+1)
    walk(0, 0); return out
for d in range(1, 6):
    for nlo, nhi in level_nodes(d): s += line(rect(nlo, nhi, 0.01*d), dcol[d-1], True)
s += f"<Shape><Appearance><PointProperties pointSizeScaleFactor='2' pointSizeMinValue='1' pointSizeMaxValue='3' attenuation='1 0 0'/><Material emissiveColor='0.55 0.6 0.7'/></Appearance><PointSet><Coordinate point='{f(np.concatenate([ctr, np.zeros((len(ctr), 1))], 1))}'/></PointSet></Shape>\n"
hitpts = np.array([np.concatenate([np.array([ctr[k] for k in h]).reshape(-1, 2), np.full((len(h), 1), 0.05)], 1).tolist()+[[0, -50, 0]]*(M-len(h)) for h in hit_frames])
kk = f(np.linspace(0, 1, NF+1), 5)
s += f"<Shape><Appearance><PointProperties pointSizeScaleFactor='5' pointSizeMinValue='4' pointSizeMaxValue='9' attenuation='1 0 0'/><Material emissiveColor='1 0.3 0.25'/></Appearance><PointSet><Coordinate DEF='HITS' point='{f(hitpts[0])}'/></PointSet></Shape>\n"
s += f"<CoordinateInterpolator DEF='HITS_I' key='{kk}' keyValue='{' '.join(f(h) for h in hitpts)}'/><ROUTE fromNode='CLK' fromField='fraction_changed' toNode='HITS_I' toField='set_fraction'/><ROUTE fromNode='HITS_I' fromField='value_changed' toNode='HITS' toField='set_point'/>\n"
s += mover("QB", f"<Shape><Appearance><Material emissiveColor='1 1 1'/></Appearance><IndexedLineSet coordIndex='0 1 2 3 0 -1'><Coordinate point='{f(np.array([[-qh_, -qh_, 0.06], [qh_, -qh_, 0.06], [qh_, qh_, 0.06], [-qh_, qh_, 0.06]]))}'/></IndexedLineSet></Shape>", np.concatenate([qc, np.zeros((len(qc), 1))], 1))
s += "<!-- grey points: object centres; blue line: the Z-order curve through them (the one sort); coloured boxes: tree nodes at depths 1 (white) to 5 (violet); white square: query; red: the objects it hits -->\n<Viewpoint description='front' position='2 2 7.2' fieldOfView='0.9'/></Scene></X3D>\n"
(OUT/"24-morton-bvh.x3d").write_text(s); print('bvh done', round(time.time()-t0), flush=True)
for a in PENDING: write_record(*a)
N['limits_commit'] = LIM_COMMIT; N['seconds'] = round(time.time()-t0, 1)
(OUT/'numbers6.json').write_text(json.dumps(N, indent=1, default=float)); print(json.dumps(N, indent=1, default=float)[:3000])
