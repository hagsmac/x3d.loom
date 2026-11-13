"""Batch 5: own-code ports of ideas from Ten Minute Physics 15 (cloth self collision), 18 (FLIP water), 22 (rigid bodies),
under the Loom physics witness. No code copied. Limits (LIM) are written before the witness run and not tuned afterwards;
development runs informed the scale of some of them, and NOTES.md says which.
usage: tmp5.py OUTDIR ROOT | tmp5.py --replay NAME"""
import sys, json, math, hashlib, subprocess, time, itertools
import numpy as np
from pathlib import Path
G = 9.81
LIM = dict(
    slosh_period_rel=0.03, slosh_flip_over_pic=2.0, slosh_level_cells=0.5,
    rigid_angle_4s_rad=0.15, rigid_L_drift=0.02, rigid_mj_vs_euler_rad=1e-5,
    incline_a_rel=0.02, incline_stick_m=0.01, incline_mj_a_rel=0.05, rest_height_m=2e-3,
    cloth_gap_over_thickness=0.9, cloth_crossings=0, cloth_stretch=0.10, tunnel_rule_violations=0,
    tunnel_safe_vht=0.9, tunnel_unsafe_vht=2.0,          # prediction 1, written before the first grid (y0 = 3.0): it FAILED, see NOTES.md
    tunnel2_safe_vht=1.0, tunnel2_violations=0, tunnel2_teeth_runs=1)   # prediction 2, written after grid 1 and tested on a fresh grid (y0 = 2.0, other substeps and thicknesses)
def h32(arr): return int(hashlib.sha256(np.asarray(arr, dtype='<f8').tobytes()).hexdigest()[:8], 16)
def trace_sha(hs): return hashlib.sha256(",".join(str(h) for h in hs).encode()).hexdigest()

def near_pairs(x, rad):
    """all pairs i<j with |xi-xj| < rad (cells of size rad, any dimension), deterministic"""
    d = x.shape[1]; c = np.floor(x/rad).astype(np.int64); c -= c.min(axis=0)-2; K = 1 << 14; mult = np.array([K**k for k in range(d)], dtype=np.int64); key = (c*mult).sum(1)
    order = np.argsort(key, kind='stable'); sk = key[order]; I = []; J = []
    for off in itertools.product((-1, 0, 1), repeat=d):
        k2 = key+int((np.array(off)*mult).sum()); lo = np.searchsorted(sk, k2, 'left'); hi = np.searchsorted(sk, k2, 'right'); cnt = hi-lo; tot = int(cnt.sum())
        if tot == 0: continue
        i = np.repeat(np.arange(len(x)), cnt); start = np.repeat(np.cumsum(cnt)-cnt, cnt); j = order[lo[i]+(np.arange(tot)-start)]
        m = i < j; I.append(i[m]); J.append(j[m])
    I = np.concatenate(I); J = np.concatenate(J); dd = x[J]-x[I]; m = (dd*dd).sum(1) < rad*rad
    return I[m], J[m]

# ======================= 18: FLIP / PIC water, staggered grid =======================
class Flip:
    def __init__(s, nx, ny, h, parts_xy, rest, flip_ratio=0.9, niter=100, over=1.9, push_iters=0, comp=4.17):
        s.nx, s.ny, s.h = nx, ny, h; s.x = np.array(parts_xy, float); s.v = np.zeros_like(s.x); s.r = 0.3*h
        s.fr, s.niter, s.over, s.push, s.comp, s.rest = flip_ratio, niter, over, push_iters, comp, rest; s.t = 0.0
        s.solid = np.zeros((nx+2, ny+2)); s.solid[0, :] = s.solid[-1, :] = s.solid[:, 0] = s.solid[:, -1] = 1   # padded ring: 1 = wall
    def _scatter(s, shape, gx, gy, val):
        nxf, nyf = shape; gx = np.clip(gx, 0, nxf-1.0001); gy = np.clip(gy, 0, nyf-1.0001); i = gx.astype(int); j = gy.astype(int); fx = gx-i; fy = gy-j
        acc = np.zeros(nxf*nyf); wt = np.zeros(nxf*nyf)
        for di, dj, w in ((0, 0, (1-fx)*(1-fy)), (1, 0, fx*(1-fy)), (0, 1, (1-fx)*fy), (1, 1, fx*fy)):
            idx = (i+di)*nyf+(j+dj); acc += np.bincount(idx, w*val, nxf*nyf); wt += np.bincount(idx, w, nxf*nyf)
        return acc.reshape(nxf, nyf), wt.reshape(nxf, nyf)
    def _gather(s, f_, gx, gy):
        nxf, nyf = f_.shape; gx = np.clip(gx, 0, nxf-1.0001); gy = np.clip(gy, 0, nyf-1.0001); i = gx.astype(int); j = gy.astype(int); fx = gx-i; fy = gy-j
        return f_[i, j]*(1-fx)*(1-fy)+f_[i+1, j]*fx*(1-fy)+f_[i, j+1]*(1-fx)*fy+f_[i+1, j+1]*fx*fy
    def step(s, dt):
        nx, ny, h = s.nx, s.ny, s.h; x, v = s.x, s.v
        v[:, 1] -= G*dt; x += v*dt
        for _ in range(s.push):   # optional push-apart of overlapping particles
            I, J = near_pairs(x, 2*s.r)
            if len(I):
                d = x[J]-x[I]; dist = np.maximum(np.sqrt((d*d).sum(1)), 1e-9); dx = d*(0.5*(2*s.r-dist)/dist)[:, None]; np.add.at(x, I, -dx); np.add.at(x, J, dx)
        lo, hi = h+s.r, np.array([(nx-1)*h-s.r, (ny-1)*h-s.r])
        for k in (0, 1):
            m = x[:, k] < lo; x[m, k] = lo; v[m, k] = 0.0; m = x[:, k] > hi[k]; x[m, k] = hi[k]; v[m, k] = 0.0
        U, WU = s._scatter((nx+1, ny), x[:, 0]/h, x[:, 1]/h-0.5, v[:, 0]); V, WV = s._scatter((nx, ny+1), x[:, 0]/h-0.5, x[:, 1]/h, v[:, 1])
        u = np.where(WU > 0, U/np.maximum(WU, 1e-12), 0.0); vv = np.where(WV > 0, V/np.maximum(WV, 1e-12), 0.0)
        _, dens = s._scatter((nx, ny), x[:, 0]/h-0.5, x[:, 1]/h-0.5, np.ones(len(x)))
        ci = np.clip((x[:, 0]/h).astype(int), 0, nx-1); cj = np.clip((x[:, 1]/h).astype(int), 0, ny-1)
        fluid = np.zeros((nx, ny), bool); fluid[ci, cj] = True; fluid &= (s.solid[1:-1, 1:-1] == 0)
        u[0, :] = u[1, :] = 0; u[-1, :] = u[-2, :] = 0; vv[:, 0] = vv[:, 1] = 0; vv[:, -1] = vv[:, -2] = 0
        u0, v0 = u.copy(), vv.copy(); sp = 1.0-s.solid
        I_, J_ = np.meshgrid(np.arange(nx), np.arange(ny), indexing='ij'); cols = [(I_[m], J_[m]) for m in [((I_+J_) % 2 == c) & fluid for c in (0, 1)]]
        comp = np.maximum(dens/s.rest-1.0, 0.0)*s.comp   # divergence (m/s) bled off per unit of excess density ratio
        for _ in range(s.niter):
            for Ii, Jj in cols:
                sxm, sxp, sym, syp = sp[Ii, Jj+1], sp[Ii+2, Jj+1], sp[Ii+1, Jj], sp[Ii+1, Jj+2]; ss = sxm+sxp+sym+syp
                d = u[Ii+1, Jj]-u[Ii, Jj]+vv[Ii, Jj+1]-vv[Ii, Jj]-comp[Ii, Jj]
                w = np.where(ss > 0, s.over*d/np.maximum(ss, 1e-12), 0.0)
                u[Ii, Jj] += w*sxm; u[Ii+1, Jj] -= w*sxp; vv[Ii, Jj] += w*sym; vv[Ii, Jj+1] -= w*syp
        gu = s._gather(u, x[:, 0]/h, x[:, 1]/h-0.5); gv = s._gather(vv, x[:, 0]/h-0.5, x[:, 1]/h)
        ou = s._gather(u0, x[:, 0]/h, x[:, 1]/h-0.5); ov = s._gather(v0, x[:, 0]/h-0.5, x[:, 1]/h)
        s.v = (1-s.fr)*np.stack([gu, gv], 1)+s.fr*(v+np.stack([gu-ou, gv-ov], 1)); s.t += dt
FNX, FNY, FH0, FA = 50, 30, 0.4, 0.04
def flip_setup(fr=0.9, push=0, comp=4.17):
    h = 1.0/(FNX-2); L = (FNX-2)*h; sp = 0.6*h; xs = np.arange(h+sp/2, (FNX-1)*h-sp/2+1e-9, sp); ys = np.arange(h+sp/2, (FNY-1)*h-sp/2, sp); pts = []; band = []
    for x in xs:
        top = h+FH0+FA*np.cos(np.pi*(x-h)/L)
        for y in ys:
            if y < top: pts.append((x, y)); band.append(min(5, int((y-h)/(FH0+FA)*6)))
    pts = np.array(pts); pts += np.random.default_rng(3).uniform(-0.05, 0.05, pts.shape)*sp
    return Flip(FNX, FNY, h, pts, rest=(h/sp)**2, flip_ratio=fr, push_iters=push, comp=comp), L, np.array(band)
def flip_mode(sim, L): return float(np.sum(sim.x[:, 1]*np.cos(np.pi/L*(sim.x[:, 0]-sim.h))))   # projection of the particle heights on the first sloshing mode
def flip_run(fr=0.9, push=0, comp=4.17, T=6.0, dt=1/120, frames=None, hashes=None, every=8):
    sim, L, band = flip_setup(fr, push, comp); out = []
    for k in range(int(round(T/dt))+1):
        if k % every == 0:
            if frames is not None: frames.append(sim.x.copy())
            if hashes is not None: hashes.append(h32(np.concatenate([sim.x.ravel(), sim.v.ravel()])))
        out.append((sim.t, flip_mode(sim, L), float(sim.x[:, 1].mean())))
        if k < int(round(T/dt)): sim.step(dt)
    return np.array(out), L, band, sim
def fit_mode(t, mu):
    """least-squares fit mu(t) = A exp(-s t) cos(w t) on a fixed grid of (w, s): deterministic"""
    best = None
    for w in np.linspace(3.0, 8.0, 2001):
        for sg in np.linspace(0.0, 1.5, 61):
            m = np.exp(-sg*t)*np.cos(w*t); amp = (m@mu)/(m@m); r = ((mu-amp*m)**2).sum()
            if best is None or r < best[0]: best = (r, w, sg, amp)
    return best

# ======================= 22: rigid box, XPBD =======================
def qmul(a, b):
    aw, ax, ay, az = a; bw, bx, by, bz = b
    return np.array([aw*bw-ax*bx-ay*by-az*bz, aw*bx+ax*bw+ay*bz-az*by, aw*by-ax*bz+ay*bw+az*bx, aw*bz+ax*by-ay*bx+az*bw])
def qconj(q): return np.array([q[0], -q[1], -q[2], -q[3]])
def qrot(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)], [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)], [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])
def qaxis(axis, ang):
    a = np.asarray(axis, float); a = a/math.sqrt(a@a); return np.array([math.cos(ang/2), *(math.sin(ang/2)*a)])
def qangle(a, b): return 2*math.acos(min(1.0, abs(float(a@b))))
def q2aa(q):
    q = q/np.linalg.norm(q); w = max(-1.0, min(1.0, q[0])); ang = 2*math.acos(w); s_ = math.sqrt(max(1-w*w, 0.0))
    return (np.array([1.0, 0, 0]), 0.0) if s_ < 1e-9 else (q[1:]/s_, ang)
class Box:
    def __init__(s, half, mass, x, q, v=(0, 0, 0), w=(0, 0, 0)):
        s.half = np.array(half, float); s.m = mass; a, b, c = s.half
        s.Ib = mass/3*np.array([b*b+c*c, a*a+c*c, a*a+b*b]); s.x = np.array(x, float); s.q = np.array(q, float); s.v = np.array(v, float); s.w = np.array(w, float)
        s.verts = np.array([[sx*a, sy*b, sz*c] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    def Iinv(s): R = qrot(s.q); return R@np.diag(1/s.Ib)@R.T
    def I(s): R = qrot(s.q); return R@np.diag(s.Ib)@R.T
    def L(s): return s.I()@s.w
    def energy(s, g=G): return 0.5*s.m*(s.v@s.v)+0.5*s.w@(s.I()@s.w)+s.m*g*s.x[1]
    def lowest(s): R = qrot(s.q); return float((s.x[None, :]+s.verts@R.T)[:, 1].min())
def rb_step(bx, h, nsub=1, plane=None, mu=0.0, gyro=True, gravity=True):
    hs = h/nsub
    for _ in range(nsub):
        xp, qp = bx.x.copy(), bx.q.copy()
        if gravity: bx.v = bx.v+np.array([0, -G, 0])*hs
        if gyro: Iw = bx.I()@bx.w; bx.w = bx.w+hs*bx.Iinv()@(-np.cross(bx.w, Iw))
        bx.x = bx.x+hs*bx.v; bx.q = bx.q+0.5*hs*qmul(np.array([0.0, *bx.w]), bx.q); bx.q /= np.linalg.norm(bx.q)
        if plane is not None:
            n, d = plane; Rp = qrot(qp)
            for r in bx.verts:
                R = qrot(bx.q); p = bx.x+R@r; C = d-n@p
                if C <= 0: continue
                rw = R@r; rn = np.cross(rw, n); Ii = bx.Iinv(); lam = C/(1/bx.m+rn@(Ii@rn))
                bx.x = bx.x+n*lam/bx.m; bx.q = bx.q+0.5*qmul(np.array([0.0, *(Ii@np.cross(rw, n*lam))]), bx.q); bx.q /= np.linalg.norm(bx.q)
                if mu > 0:   # friction: remove the slip of this contact point over the substep, inside the cone |lam_t| <= mu lam_n
                    R = qrot(bx.q); p = bx.x+R@r; dp = p-(xp+Rp@r); dpt = dp-n*(n@dp); lt = math.sqrt(dpt@dpt)
                    if lt > 1e-14:
                        rw = R@r; Ii = bx.Iinv(); t = dpt/lt; rt = np.cross(rw, t); lamt = min(lt/(1/bx.m+rt@(Ii@rt)), mu*lam)
                        bx.x = bx.x-t*lamt/bx.m; bx.q = bx.q+0.5*qmul(np.array([0.0, *(-(Ii@np.cross(rw, t*lamt)))]), bx.q); bx.q /= np.linalg.norm(bx.q)
        bx.v = (bx.x-xp)/hs; dq = qmul(bx.q, qconj(qp)); bx.w = 2*dq[1:]/hs*(1 if dq[0] >= 0 else -1)
FREE = dict(half=(0.45, 0.12, 0.25), mass=3.0, w0=(0.3, 0.0, 4.0))
def free_xpbd(T=6.0, nsub=20, gyro=True, fps=60, hashes=None):
    b = Box(FREE['half'], FREE['mass'], (0, 0, 0), (1, 0, 0, 0), w=FREE['w0']); L0 = b.L(); out = [(b.q.copy(), 0.0)]
    for i in range(int(round(T*fps))):
        rb_step(b, 1/fps, nsub, gravity=False, gyro=gyro); out.append((b.q.copy(), float(np.linalg.norm(b.L()-L0)/np.linalg.norm(L0))))
        if hashes is not None: hashes.append(h32(np.concatenate([b.x, b.q, b.v, b.w])))
    return out
def free_euler(T=6.0, per=16, fps=60):
    a, bb, c = FREE['half']; m = FREE['mass']; I = m/3*np.array([bb*bb+c*c, a*a+c*c, a*a+bb*bb]); h = 1/(fps*per)
    def f_(st):
        w, q = st[:3], st[3:]; dw = np.array([(I[1]-I[2])*w[1]*w[2]/I[0], (I[2]-I[0])*w[2]*w[0]/I[1], (I[0]-I[1])*w[0]*w[1]/I[2]]); return np.array([*dw, *(0.5*qmul(q, np.array([0.0, *w])))])
    s_ = np.array([*FREE['w0'], 1.0, 0, 0, 0]); out = []
    for i in range(int(round(T*fps*per))+1):
        if i % per == 0: out.append(s_[3:]/np.linalg.norm(s_[3:]))
        k1 = f_(s_); k2 = f_(s_+h/2*k1); k3 = f_(s_+h/2*k2); k4 = f_(s_+h*k3); s_ = s_+h/6*(k1+2*k2+2*k3+k4)
    return out
def free_mujoco(T=6.0, per=16, fps=60):
    import mujoco
    a, bb, c = FREE['half']; m = FREE['mass']; I = m/3*np.array([bb*bb+c*c, a*a+c*c, a*a+bb*bb])
    xml = f"""<mujoco><option timestep="{1/(fps*per)}" integrator="RK4" gravity="0 0 0"/><worldbody><body name="b"><freejoint/><inertial pos="0 0 0" mass="{m}" diaginertia="{I[0]} {I[1]} {I[2]}"/></body></worldbody></mujoco>"""
    mm = mujoco.MjModel.from_xml_string(xml); d = mujoco.MjData(mm); d.qpos[:] = [0, 0, 0, 1, 0, 0, 0]; d.qvel[:] = [0, 0, 0, *FREE['w0']]; out = []
    for i in range(int(round(T*fps*per))+1):
        if i % per == 0: out.append(d.qpos[3:7].copy())
        mujoco.mj_step(mm, d)
    return out, mujoco.__version__
INCL = dict(th=math.radians(30), half=(0.2, 0.1, 0.15), mass=2.0)
def incline_xpbd(mu, T=2.0, nsub=20, fps=60, frames=None):
    th = INCL['th']; n = np.array([math.sin(th), math.cos(th), 0.0]); b = Box(INCL['half'], INCL['mass'], n*(INCL['half'][1]+1e-4), qaxis([0, 0, 1], -th)); x0 = b.x.copy(); out = [b.x.copy()]
    for i in range(int(round(T*fps))):
        rb_step(b, 1/fps, nsub, plane=(n, 0.0), mu=mu); out.append(b.x.copy())
        if frames is not None: frames.append((b.x.copy(), b.q.copy()))
    return np.array(out), x0
def incline_mujoco(mu, T=2.0):
    import mujoco
    th = INCL['th']; a, bb, c = INCL['half']
    xml = f"""<mujoco><compiler angle="radian"/><option timestep="0.001" integrator="RK4" cone="elliptic" impratio="10"/><worldbody>
    <geom type="plane" size="5 5 .1" euler="0 {th} 0" friction="{mu} 0.005 0.0001"/>
    <body name="b" pos="{math.sin(th)*(bb+1e-4)} 0 {math.cos(th)*(bb+1e-4)}" euler="0 {th} 0"><freejoint/><geom type="box" size="{a} {c} {bb}" mass="{INCL['mass']}" friction="{mu} 0.005 0.0001"/></body></worldbody></mujoco>"""
    mm = mujoco.MjModel.from_xml_string(xml); d = mujoco.MjData(mm); p0 = d.qpos[:3].copy(); mujoco.mj_forward(mm, d); p0 = d.xpos[1].copy()
    for i in range(int(round(T/0.001))): mujoco.mj_step(mm, d)
    t_hat = np.array([math.cos(th), 0, -math.sin(th)]); s_ = float((d.xpos[1]-p0)@t_hat); return s_, mujoco.__version__
DROP = dict(half=(0.2, 0.1, 0.15), mass=2.0, x0=(0, 1.0, 0), q0=qaxis([1, 0.4, 0.2], 0.7), w0=(1.5, 0.5, 0.3), mu=0.5)
def drop_run(T=4.0, nsub=20, fps=60, frames=None, hashes=None):
    b = Box(DROP['half'], DROP['mass'], DROP['x0'], DROP['q0'], w=DROP['w0'])
    for i in range(int(round(T*fps))+1):
        if frames is not None: frames.append((b.x.copy(), b.q.copy()))
        if hashes is not None: hashes.append(h32(np.concatenate([b.x, b.q, b.v, b.w])))
        if i < int(round(T*fps)): rb_step(b, 1/fps, nsub, plane=(np.array([0, 1.0, 0]), 0.0), mu=DROP['mu'])
    return b

# ======================= 15: cloth with particle self collision =======================
def color_groups(cons, nverts):
    groups = []; used = []
    for ci, c in enumerate(cons):
        for g, u in zip(groups, used):
            if not any(v in u for v in c): g.append(ci); u.update(c); break
        else: groups.append([ci]); used.append(set(c))
    return [np.array(g) for g in groups]
class Cloth:
    def __init__(s, N, W, y0, thick_ratio, ball_r=0.22, ball_c=(0.0, 0.22, 0.0)):
        s.N = N; s.W = W; s.sp = W/(N-1); gid = lambda i, j: i*N+j
        s.P0 = np.array([[i*s.sp-W/2, 0.0, j*s.sp-W/2] for i in range(N) for j in range(N)]); cons = []; kind = []
        for i in range(N):
            for j in range(N):
                if i+1 < N: cons.append((gid(i, j), gid(i+1, j))); kind.append(0)
                if j+1 < N: cons.append((gid(i, j), gid(i, j+1))); kind.append(0)
                if i+1 < N and j+1 < N: cons.append((gid(i, j), gid(i+1, j+1))); kind.append(1); cons.append((gid(i+1, j), gid(i, j+1))); kind.append(1)
                if i+2 < N: cons.append((gid(i, j), gid(i+2, j))); kind.append(2)
                if j+2 < N: cons.append((gid(i, j), gid(i, j+2))); kind.append(2)
        s.cons = np.array(cons); s.kind = np.array(kind); s.L0 = np.linalg.norm(s.P0[s.cons[:, 0]]-s.P0[s.cons[:, 1]], axis=1)
        s.alpha = np.array([1e-8, 1e-8, 5e-3])[s.kind]; s.groups = color_groups([tuple(c) for c in s.cons], len(s.P0))
        s.x = s.P0+np.array([0, y0, 0]); s.v = np.zeros_like(s.x); s.thick = thick_ratio*s.sp; s.self_collide = thick_ratio > 0
        s.ball_r = ball_r; s.ball_c = np.array(ball_c); s.skin = 0.012
        D = np.linalg.norm(s.P0[:, None, :]-s.P0[None, :, :], axis=2); s.skip = D < max(s.thick, 1.01*s.sp*math.sqrt(2))   # sheet neighbours never collide
        tri = []
        for i in range(N-1):
            for j in range(N-1): a, b, c, d = gid(i, j), gid(i+1, j), gid(i+1, j+1), gid(i, j+1); tri += [(a, c, b), (a, d, c)]
        s.tri = np.array(tri); e = set()
        for t in s.tri:
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])): e.add((min(a, b), max(a, b)))
        s.edges = np.array(sorted(e)); s.vmax = 0.0
    def step(s, dt, nsub, fric=0.85):
        h = dt/nsub; sk = s.skin
        for _ in range(nsub):
            xp = s.x.copy(); s.v[:, 1] -= G*h; s.v *= (1-0.3*h); s.x = s.x+s.v*h
            for grp in s.groups:
                c = s.cons[grp]; d = s.x[c[:, 0]]-s.x[c[:, 1]]; l = np.linalg.norm(d, axis=1); lam = -(l-s.L0[grp])/(2+s.alpha[grp]/h**2); gr = d/np.maximum(l, 1e-9)[:, None]
                np.add.at(s.x, c[:, 0], gr*lam[:, None]); np.add.at(s.x, c[:, 1], -gr*lam[:, None])
            if s.self_collide:
                I, J = near_pairs(s.x, s.thick)
                if len(I):
                    m = ~s.skip[I, J]; I, J = I[m], J[m]
                    if len(I):
                        d = s.x[J]-s.x[I]; dist = np.maximum(np.linalg.norm(d, axis=1), 1e-9); dx = d*(0.5*(s.thick-dist)/dist)[:, None]; np.add.at(s.x, I, -dx); np.add.at(s.x, J, dx)
            dd = s.x-s.ball_c; dl = np.linalg.norm(dd, axis=1); inn = dl < s.ball_r+sk
            if inn.any():
                nn = dd[inn]/dl[inn, None]; q = s.ball_c+nn*(s.ball_r+sk); dlt = q-xp[inn]; dtn = dlt-(dlt*nn).sum(1)[:, None]*nn; s.x[inn] = q-fric*dtn
            low = s.x[:, 1] < sk
            if low.any(): s.x[low, 1] = sk; s.x[low, 0] = xp[low, 0]+(s.x[low, 0]-xp[low, 0])*(1-fric); s.x[low, 2] = xp[low, 2]+(s.x[low, 2]-xp[low, 2])*(1-fric)
            s.v = (s.x-xp)/h; s.vmax = max(s.vmax, float(np.linalg.norm(s.v, axis=1).max()))
    def min_gap(s):
        D = np.linalg.norm(s.x[:, None, :]-s.x[None, :, :], axis=2); D = np.where(s.skip, np.inf, D); np.fill_diagonal(D, np.inf); return float(D.min())
    def crossings(s, chunk=256):
        """geometric count of sheet edges that pierce a triangle they do not touch (Moller-Trumbore, brute force); independent of the particle-sphere test"""
        P = s.x; T = s.tri; A = P[T[:, 0]]; B = P[T[:, 1]]; C = P[T[:, 2]]; e1 = B-A; e2 = C-A; count = 0
        for k in range(0, len(s.edges), chunk):
            E = s.edges[k:k+chunk]; p0 = P[E[:, 0]]; dv = P[E[:, 1]]-p0; pv = np.cross(dv[:, None, :], e2[None, :, :]); det = (e1[None]*pv).sum(2)
            ok = np.abs(det) > 1e-14; inv = np.where(ok, 1.0/np.where(ok, det, 1.0), 0.0); tv = p0[:, None, :]-A[None]
            u = (tv*pv).sum(2)*inv; qv = np.cross(tv, e1[None]); v = (dv[:, None, :]*qv).sum(2)*inv; t = (e2[None]*qv).sum(2)*inv
            hit = ok & (u > 1e-9) & (v > 1e-9) & (u+v < 1-1e-9) & (t > 1e-9) & (t < 1-1e-9)
            touch = (E[:, 0, None] == T[None, :, 0]) | (E[:, 0, None] == T[None, :, 1]) | (E[:, 0, None] == T[None, :, 2]) | (E[:, 1, None] == T[None, :, 0]) | (E[:, 1, None] == T[None, :, 1]) | (E[:, 1, None] == T[None, :, 2])
            count += int((hit & ~touch).sum())
        return count
    def stretch(s): l = np.linalg.norm(s.x[s.cons[s.kind == 0, 0]]-s.x[s.cons[s.kind == 0, 1]], axis=1); return float(np.abs(l/s.L0[s.kind == 0]-1).max())
CN, CW = 29, 1.9
def cloth_run(ratio, y0=0.9, nsub=20, T=5.0, fps=60, frames=None, hashes=None, probe=False, key_every=3):
    c = Cloth(CN, CW, y0, ratio); gaps = []; cr = []; st = []
    for fi in range(int(round(T*fps))+1):
        if frames is not None and fi % key_every == 0: frames.append(c.x.copy())
        if hashes is not None: hashes.append(h32(np.concatenate([c.x.ravel(), c.v.ravel()])))
        if probe and fi % 6 == 0 and ratio > 0: gaps.append(c.min_gap())
        if probe and fi % 30 == 0 and fi > 0: cr.append(c.crossings()); st.append(c.stretch())
        if fi < int(round(T*fps)): c.step(1/fps, nsub)
    return c, gaps, cr, st

HASHERS = {
 'flip': lambda: (lambda hs: (flip_run(T=2.0, hashes=hs, every=8), hs)[1])([]),
 'rigid': lambda: (lambda hs: (free_xpbd(T=2.0, hashes=hs), hs)[1])([]),
 'cloth': lambda: (lambda hs: (cloth_run(0.6, T=2.0, hashes=hs), hs)[1])([]),
}
if len(sys.argv) > 2 and sys.argv[1] == '--replay':
    print(json.dumps(HASHERS[sys.argv[2]]())); sys.exit(0)

OUT, ROOT = Path(sys.argv[1]), Path(sys.argv[2]); (OUT/'records').mkdir(parents=True, exist_ok=True)
def sha_file(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def replay_fresh(name): return json.loads(subprocess.run([sys.executable, '-I', __file__, '--replay', name], capture_output=True, text=True, check=True).stdout)
def replay_block(host, ref, other):
    mism = [i for i, (a, b) in enumerate(zip(ref, other)) if a != b]
    return dict(host=host, steps=len(other), mismatches=len(mism)+abs(len(ref)-len(other)), first_mismatch=(mism[0] if mism else None), trace_sha256=trace_sha(other))
PYV, NPV = sys.version.split()[0], np.__version__; HOST_REC = f"cpython-{PYV}-numpy-{NPV}"; HOST_FRESH = "numpy-fresh-process"
def ref_item(id_, observed, limit, source, rule="at most"):
    ok = observed <= limit if rule == "at most" else observed >= limit
    return dict(id=id_, observed=float(observed), limit=limit, declared_limit=limit, rule=rule, status="pass" if ok else "fail", source=source)
V5 = "docs/demos/ten-minute-physics/v5/"; PENDING = []
def record(*a): PENDING.append(a)
def write_record(rid, model_path, hashes, replays, refs, controls, not_shown, note):
    rec = dict(schema="loom.physics-run/1", id=rid, engine=dict(name="tmp-ports (numpy)", version=f"numpy-{NPV}", build=f"tmp5.py sha256 {hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:12]}, python {PYV}"),
        model=dict(sha256=sha_file(OUT/Path(model_path).name), path=model_path, what="the X3D scene the port produced; parameters live in tmp5.py"),
        recorded=dict(host=HOST_REC, steps=len(hashes), hashes=hashes, trace_sha256=trace_sha(hashes)), replays=replays, references=refs, controls=controls, not_shown=not_shown, note=note)
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
def pm(base, rough=0.25, emis=None, transp=None, metal=0): return f"<Appearance><PhysicalMaterial baseColor='{base}' roughness='{rough}' metallic='{metal}'" + (f" emissiveColor='{emis}'" if emis else "") + (f" transparency='{transp}'" if transp is not None else "") + "/></Appearance>"
def line(pts, col): return f"<Shape><Appearance><Material emissiveColor='{col}'/></Appearance><IndexedLineSet coordIndex='{' '.join(map(str, range(len(pts))))} -1'><Coordinate point='{f(pts)}'/></IndexedLineSet></Shape>\n"
def chart(series, colors, origin, size, ymin, ymax):
    ox, oy, oz = origin; w, h = size; out = line([(ox, oy, oz), (ox+w, oy, oz), (ox+w, oy+h, oz), (ox, oy+h, oz), (ox, oy, oz)], "0.5 0.55 0.65")
    out += line([(ox, oy+(0-ymin)/(ymax-ymin)*h, oz), (ox+w, oy+(0-ymin)/(ymax-ymin)*h, oz)], "0.25 0.28 0.35")
    for s_, c in zip(series, colors):
        s_ = np.clip(np.asarray(s_), ymin, ymax); xs = np.linspace(0, w, len(s_)); ys = (s_-ymin)/(ymax-ymin)*h; out += line(np.stack([ox+xs, oy+ys, np.full_like(xs, oz)], 1), c)
    return out
def deform(name, frames, ifs_attrs, tail="", app="", clk='CLK'):
    key = np.linspace(0, 1, frames.shape[0]); attrs = " ".join(f"{k}='{v}'" for k, v in ifs_attrs.items())
    s = f"<Shape>{app}<IndexedFaceSet DEF='{name}_F' {attrs}><Coordinate DEF='{name}_C' point='{f(frames[0])}'/>{tail}</IndexedFaceSet></Shape>\n"
    s += f"<CoordinateInterpolator DEF='{name}_I' key='{f(key, 5)}' keyValue='{' '.join(f(fr) for fr in frames)}'/>\n"
    s += f"<ROUTE fromNode='{clk}' fromField='fraction_changed' toNode='{name}_I' toField='set_fraction'/><ROUTE fromNode='{name}_I' fromField='value_changed' toNode='{name}_C' toField='set_point'/>\n"
    return s
def mover(name, inner, pos=None, quat=None, clk='CLK', base_pos=(0, 0, 0)):
    """a Transform driven by a PositionInterpolator and/or an OrientationInterpolator (keys evenly spaced over the clock cycle)"""
    n = len(pos) if pos is not None else len(quat); key = f(np.linspace(0, 1, n), 5); b = f"<Transform DEF='{name}' translation='{f(np.array(base_pos if pos is None else pos[0]))}'>{inner}</Transform>\n"
    if pos is not None: b += f"<PositionInterpolator DEF='{name}_P' key='{key}' keyValue='{' '.join(f(p) for p in pos)}'/><ROUTE fromNode='{clk}' fromField='fraction_changed' toNode='{name}_P' toField='set_fraction'/><ROUTE fromNode='{name}_P' fromField='value_changed' toNode='{name}' toField='set_translation'/>\n"
    if quat is not None:
        qs = []; prev = None
        for q in quat:
            q = q/np.linalg.norm(q)
            if prev is not None and q@prev < 0: q = -q
            prev = q; ax, ang = q2aa(q); qs.append((*ax, ang))
        b += f"<OrientationInterpolator DEF='{name}_O' key='{key}' keyValue='{' '.join(f(np.array(r), 5) for r in qs)}'/><ROUTE fromNode='{clk}' fromField='fraction_changed' toNode='{name}_O' toField='set_fraction'/><ROUTE fromNode='{name}_O' fromField='value_changed' toNode='{name}' toField='set_rotation'/>\n"
    return b

# ---------------------------- 18: FLIP ----------------------------
FR = []; main, L, band, sim = flip_run(0.9, 0, T=6.0, frames=FR); pic, _, _, _ = flip_run(0.0, 0, T=6.0); ctl, _, _, _ = flip_run(0.9, 2, T=3.7)
k_ = math.pi/L; w_lin = math.sqrt(G*k_*math.tanh(k_*FH0)); T_lin = 2*math.pi/w_lin; hh = sim.h
def mu_of(o): return o[:, 1]/o[0, 1]
def fit_of(o, tmax=3.7): sel = o[:, 0] <= tmax+1e-9; return fit_mode(o[sel, 0], mu_of(o)[sel])
fm, fp, fc = fit_of(main), fit_of(pic), fit_of(ctl)
per = lambda fit: abs((2*math.pi/fit[1])/T_lin-1)
late = lambda o: float(np.abs(mu_of(o)[(o[:, 0] >= 2*T_lin) & (o[:, 0] < 4*T_lin)]).max())
lev = abs(float(main[(main[:, 0] >= 2.0), 2].mean())-float(main[0, 2]))/hh
N['flip'] = dict(grid=f"{FNX}x{FNY}", particles=int(len(sim.x)), h=hh, flip_ratio=0.9, comp_mps=4.17, pressure_sweeps=100, dt=1/120, tank_L=L, depth=FH0, tilt=FA, T_linear=T_lin,
    T_flip=2*math.pi/fm[1], err_flip=per(fm), sigma_flip=fm[2], T_pic=2*math.pi/fp[1], err_pic=per(fp), sigma_pic=fp[2], T_pushapart=2*math.pi/fc[1], err_pushapart=per(fc),
    late_flip=late(main), late_pic=late(pic), late_ratio=late(main)/max(late(pic), 1e-9), level_drift_cells=lev, ycm0=float(main[0, 2]), ycm_min=float(main[:, 2].min()), ycm_max=float(main[:, 2].max()), frames=len(FR))
hs = []; flip_run(T=2.0, hashes=hs); fr_ = replay_fresh('flip')
record("tmp-ports/18-flip-slosh", V5+"18-flip-slosh.x3d", hs, [replay_block(HOST_FRESH, hs, fr_)],
    [ref_item("slosh period of the first mode (fit over 3 periods) against linear wave theory T = 2 pi / sqrt(g k tanh(k H)), relative error", N['flip']['err_flip'], LIM['slosh_period_rel'], "linear water-wave dispersion, k = pi/L, H = 0.4 m"),
     ref_item("late-time wave amplitude, FLIP 0.9 over pure PIC (periods 2 to 4)", N['flip']['late_ratio'], LIM['slosh_flip_over_pic'], "same scene, same grid, only the blend differs", rule="at least"),
     ref_item("water level drift: mean height of the particles after 2 s against the start, in cells", lev, LIM['slosh_level_cells'], "particle count is conserved, so the level must be")],
    [dict(id="the period test applied to the same sim with particle push-apart switched on must fail", expect="fail", observed_failed=bool(N['flip']['err_pushapart'] > LIM['slosh_period_rel']), observed=N['flip']['err_pushapart'])],
    ["a real GPU / timing", "3D (the sim is 2D; the z spread in the scene is decoration)", "breaking waves and splashes (no reference)", "resolution convergence (one grid only)", "another machine"], "hash replay covers the first 2 s")
cols6 = ['0.12 0.25 0.85', '0.1 0.55 0.95', '0.15 0.8 0.85', '0.85 0.9 0.3', '0.95 0.55 0.2', '0.9 0.25 0.3']; zdec = np.random.default_rng(11).uniform(-0.06, 0.06, len(sim.x)).round(2)
Fr = np.array(FR); P3 = np.concatenate([Fr, np.broadcast_to(zdec[None, :, None], (len(Fr), len(sim.x), 1))], 2)
s = HEAD("TMP 18 FLIP water: sloshing in a tank", "2560 particles, a staggered grid and a pressure projection, a tilted surface set free; period against linear wave theory. Idea of Ten Minute Physics 18.") + "<TimeSensor DEF='CLK' cycleInterval='6' loop='true'/>\n"
wall = pm('0.10 0.12 0.18', 0.6, None, 0.35); ww = 0.03
s += f"<Transform translation='{(hh+(FNX-1)*hh)/2} {hh-ww/2} 0'><Shape>{wall}<Box size='{L+0.12} {ww} 0.2'/></Shape></Transform>\n"
for sx in (hh-ww/2, (FNX-1)*hh+ww/2): s += f"<Transform translation='{sx} 0.35 0'><Shape>{wall}<Box size='{ww} 0.7 0.2'/></Shape></Transform>\n"
cols_arr = np.array([[float(c) for c in cols6[b].split()] for b in band])
s += f"<Shape><Appearance><PointProperties pointSizeScaleFactor='9' pointSizeMinValue='5' pointSizeMaxValue='14' attenuation='1 0 0'/></Appearance><PointSet><Coordinate DEF='WATER' point='{f(P3[0])}'/><Color color='{f(cols_arr, 2)}'/></PointSet></Shape>\n"
s += f"<CoordinateInterpolator DEF='WATER_I' key='{f(np.linspace(0, 1, len(P3)), 5)}' keyValue='{' '.join(f(p_) for p_ in P3)}'/><ROUTE fromNode='CLK' fromField='fraction_changed' toNode='WATER_I' toField='set_fraction'/><ROUTE fromNode='WATER_I' fromField='value_changed' toNode='WATER' toField='set_point'/>\n"
tt = np.linspace(0, 6, 241); sel = np.searchsorted(main[:, 0], tt-1e-9).clip(0, len(main)-1)
cx0, cy0, cw, ch = hh, 0.82, L, 0.30
s += chart([mu_of(main)[sel], mu_of(pic)[sel], np.cos(w_lin*tt)], ["0.3 0.85 1", "1 0.6 0.2", "0.85 0.85 0.9"], (cx0, cy0, 0.0), (cw, ch), -1.25, 1.25)
s += f"<Transform DEF='CUR' translation='{cx0} {cy0+ch/2} 0.01'><Shape><Appearance><Material emissiveColor='1 1 1'/></Appearance><IndexedLineSet coordIndex='0 1 -1'><Coordinate point='0 {-ch/2} 0 0 {ch/2} 0'/></IndexedLineSet></Shape></Transform>\n"
s += f"<PositionInterpolator DEF='CUR_P' key='0 1' keyValue='{cx0} {cy0+ch/2} 0.01 {cx0+cw} {cy0+ch/2} 0.01'/><ROUTE fromNode='CLK' fromField='fraction_changed' toNode='CUR_P' toField='set_fraction'/><ROUTE fromNode='CUR_P' fromField='value_changed' toNode='CUR' toField='set_translation'/>\n"
s += "<!-- chart: first-mode amplitude of the free surface over 6 s. white: linear theory (undamped), cyan: FLIP 0.9, orange: pure PIC. particle colour = height band at t = 0 -->\n"
s += f"<Viewpoint description='front' position='{(hh+(FNX-1)*hh)/2} 0.57 1.5' fieldOfView='0.9'/></Scene></X3D>\n"
(OUT/"18-flip-slosh.x3d").write_text(s); print('flip done', round(time.time()-t0), N['flip'], flush=True)

# ---------------------------- 22: rigid bodies ----------------------------
ref_q = free_euler(); xq = free_xpbd(); mjq, mjv = free_mujoco(); xq_off = free_xpbd(gyro=False)
ang_x = [qangle(a[0], b) for a, b in zip(xq, ref_q)]; ang_off = [qangle(a[0], b) for a, b in zip(xq_off, ref_q)]; ang_mj = [qangle(a, b) for a, b in zip(mjq, ref_q)]
th = INCL['th']; tvec = np.array([math.cos(th), -math.sin(th), 0.0]); a_ex = lambda mu: max(0.0, G*(math.sin(th)-mu*math.cos(th)))
inc = {}
for mu in (0.3, 0.7, 0.0): o, x0 = incline_xpbd(mu); inc[mu] = ((o-x0)@tvec, o)
mj_s = {mu: incline_mujoco(mu)[0] for mu in (0.3, 0.7)}; a_x = lambda mu: 2*inc[mu][0][-1]/4.0
bd = drop_run(); hf = DROP['half']; face_err = min(abs(bd.x[1]-hv) for hv in hf)
N['rigid'] = dict(mujoco=mjv, free_half=FREE['half'], free_w0=FREE['w0'], xpbd_substeps=20, fps=60, xpbd_vs_euler_rad_4s=ang_x[240], xpbd_vs_euler_rad_6s=ang_x[-1], xpbd_L_drift_max=max(r[1] for r in xq),
    gyro_off_vs_euler_rad_4s=ang_off[240], gyro_off_L_drift_max=max(r[1] for r in xq_off), mujoco_vs_euler_rad_max=max(ang_mj),
    incline_deg=30, a_exact_mu03=a_ex(0.3), a_xpbd_mu03=a_x(0.3), a_rel_mu03=abs(a_x(0.3)/a_ex(0.3)-1), a_mujoco_mu03=2*mj_s[0.3]/4.0, a_mujoco_rel_mu03=abs(2*mj_s[0.3]/4.0/a_ex(0.3)-1),
    stick_mu07_xpbd_m_2s=float(abs(inc[0.7][0][-1])), stick_mu07_mujoco_m_2s=float(abs(mj_s[0.7])), a_frictionless_rel=abs(a_x(0.0)/a_ex(0.3)-1),
    drop_rest_lowest_vertex_m=bd.lowest(), drop_rest_centre_height_m=float(bd.x[1]), drop_face_height_err_m=float(face_err), drop_rest_speed=float(np.linalg.norm(bd.v)), drop_rest_spin=float(np.linalg.norm(bd.w)))
hs = []; free_xpbd(T=2.0, hashes=hs); fr_ = replay_fresh('rigid')
record("tmp-ports/22-rigid-bodies", V5+"22-rigid-lab.x3d", hs, [replay_block(HOST_FRESH, hs, fr_)],
    [ref_item("tumbling box (intermediate axis) XPBD against Euler's equations (RK4): angle between the orientations at t = 4 s (rad)", ang_x[240], LIM['rigid_angle_4s_rad'], "Euler torque-free equations, RK4 at 960 Hz"),
     ref_item("angular momentum drift of the free XPBD box over 6 s (relative)", N['rigid']['xpbd_L_drift_max'], LIM['rigid_L_drift'], "angular momentum is conserved exactly in free flight"),
     ref_item("MuJoCo 4.0.1 RK4 against the same Euler reference: worst orientation angle over 6 s (rad)", max(ang_mj), LIM['rigid_mj_vs_euler_rad'], f"mujoco {mjv}, dt 1/960"),
     ref_item("box sliding on a 30 degree slope, mu 0.3: acceleration against g(sin t - mu cos t), relative error", N['rigid']['a_rel_mu03'], LIM['incline_a_rel'], "Coulomb friction, closed form"),
     ref_item("box on the same slope with mu 0.7 > tan 30: distance crept in 2 s (m)", N['rigid']['stick_mu07_xpbd_m_2s'], LIM['incline_stick_m'], "static friction holds when mu > tan(theta)"),
     ref_item("MuJoCo 4.0.1 on the sliding slope: acceleration against the closed form, relative error", N['rigid']['a_mujoco_rel_mu03'], LIM['incline_mj_a_rel'], f"mujoco {mjv}, elliptic cone"),
     ref_item("dropped box at rest: centre height against the nearest half-extent (m), i.e. lying flat on a face", face_err, LIM['rest_height_m'], "a box at rest on a plane sits on a face")],
    [dict(id="the Euler-angle test applied to the XPBD box with the gyroscopic term removed must fail", expect="fail", observed_failed=bool(ang_off[240] > LIM['rigid_angle_4s_rad']), observed=ang_off[240]),
     dict(id="the sliding acceleration test applied to the frictionless box must fail", expect="fail", observed_failed=bool(N['rigid']['a_frictionless_rel'] > LIM['incline_a_rel']), observed=N['rigid']['a_frictionless_rel'])],
    ["box-box contact (stacks and piles are not in this batch)", "restitution", "friction anisotropy", "another machine"], "the first exact references for XPBD rigid bodies: free rotation and Coulomb friction")
# scene: three stations, three clocks
nA = len(xq); qA = [r[0] for r in xq]; hf0 = FREE['half']
def boxshape(hf_, col, emis=None, transp=None): return f"<Shape>{pm(col, 0.25, emis, transp, 0.1)}<Box size='{2*hf_[0]} {2*hf_[1]} {2*hf_[2]}'/></Shape>"
def tagged(hf_, col): return boxshape(hf_, col, ' '.join(f'{float(c)*0.25:.2f}' for c in col.split()))+f"<Transform translation='0 0 {hf_[2]+0.04}'><Shape>{pm('1 0.2 0.2',0.3,'0.6 0.1 0.1')}<Sphere radius='0.06'/></Shape></Transform><Transform translation='{hf_[0]+0.04} 0 0'><Shape>{pm('0.2 1 0.3',0.3,'0.1 0.5 0.15')}<Sphere radius='0.06'/></Shape></Transform>"
s = HEAD("TMP 22 Rigid bodies: spin, slide and settle", "A tumbling box (intermediate-axis spin) in three engines, a box on a slope against the Coulomb formula, and a box dropped to rest. Idea of Ten Minute Physics 22.")
s += f"<TimeSensor DEF='CLKA' cycleInterval='6' loop='true'/><TimeSensor DEF='CLKB' cycleInterval='2' loop='true'/><TimeSensor DEF='CLKC' cycleInterval='4' loop='true'/>\n"
for i, (name, qs, col) in enumerate((("XPBD", qA, '0.2 0.8 1'), ("EULER", ref_q, '0.95 0.95 0.95'), ("MUJOCO", mjq, '1 0.75 0.2'))):
    s += mover(f"FA{i}", tagged(hf0, col), quat=qs, clk='CLKA', base_pos=(-4.6+1.5*i, 1.5, 0))
s += f"<Transform translation='-3.1 0.5 0'><Shape>{pm('0.1 0.11 0.15',0.7)}<Box size='5.0 0.04 1.2'/></Shape></Transform>\n"
# station B: slope
oB = np.array([0.2, 1.4, 0.0]); n_ = np.array([math.sin(th), math.cos(th), 0.0]); lanes = [-0.9, -0.3, 0.3, 0.9]; fps_ = 60; nfr = 121
hb = INCL['half']; cB = np.array([oB[0], oB[1], 0.0])+tvec*1.9-n_*0.03
s += f"<Transform translation='{f(cB)}' rotation='0 0 1 {-th}'><Shape>{pm('0.12 0.13 0.17',0.7)}<Box size='5.6 0.06 2.5'/></Shape></Transform>\n"
def lane_path(sv, z): return np.array([oB+n_*(hb[1]+1e-4)+tvec*sv_+np.array([0, 0, z]) for sv_ in sv])
sv_x3 = inc[0.3][0][:nfr]; sv_x7 = inc[0.7][0][:nfr]
mjtraj = {}
for mu in (0.3,):
    import mujoco
    xml = f"""<mujoco><compiler angle="radian"/><option timestep="0.001" integrator="RK4" cone="elliptic" impratio="10"/><worldbody><geom type="plane" size="5 5 .1" euler="0 {th} 0" friction="{mu} 0.005 0.0001"/><body name="b" pos="{math.sin(th)*(hb[1]+1e-4)} 0 {math.cos(th)*(hb[1]+1e-4)}" euler="0 {th} 0"><freejoint/><geom type="box" size="{hb[0]} {hb[2]} {hb[1]}" mass="{INCL['mass']}" friction="{mu} 0.005 0.0001"/></body></worldbody></mujoco>"""
    mm = mujoco.MjModel.from_xml_string(xml); dd = mujoco.MjData(mm); mujoco.mj_forward(mm, dd); p0 = dd.xpos[1].copy(); sv_mj = [0.0]
    for i in range(int(round(2.0/0.001))):
        mujoco.mj_step(mm, dd)
        if (i+1) % 16 == 0 and len(sv_mj) < nfr+0: sv_mj.append(float((dd.xpos[1]-p0)@np.array([math.cos(th), 0, -math.sin(th)])))
    sv_mj = np.array(sv_mj)
tms = np.arange(nfr)/fps_*1.0; sv_ex = 0.5*a_ex(0.3)*(np.arange(len(sv_mj))*16/1000)**2
nB = min(len(sv_x3), len(sv_mj), len(sv_ex)); orB = qaxis([0, 0, 1], -th)
for name, sv, z, col, transp in (("B_X3", sv_x3, lanes[0], '0.2 0.8 1', None), ("B_MJ", sv_mj, lanes[1], '1 0.75 0.2', None), ("B_EX", sv_ex, lanes[2], '1 1 1', 0.55), ("B_X7", sv_x7, lanes[3], '0.15 0.35 0.75', None)):
    sv = np.asarray(sv)[:nB]; inner = f"<Transform rotation='0 0 1 {-th}'>{boxshape((hb[0], hb[1], hb[2]*0.9), col, ' '.join(f'{float(c)*0.2:.2f}' for c in col.split()), transp)}</Transform>"
    s += mover(name, inner, pos=lane_path(sv, z), clk='CLKB')
# station C: drop
frames_d = []; drop_run(T=4.0, frames=frames_d); oC = np.array([5.2, 0.5, 0.0])
s += f"<Transform translation='{oC[0]} {oC[1]-0.02} 0'><Shape>{pm('0.1 0.11 0.15',0.7)}<Box size='3.2 0.04 2.0'/></Shape></Transform>\n"
s += mover("DROP", boxshape(DROP['half'], '0.9 0.45 0.3', '0.25 0.12 0.08'), pos=np.array([fr[0]+oC for fr in frames_d]), quat=[fr[1] for fr in frames_d], clk='CLKC')
s += line(np.array([fr[0]+oC for fr in frames_d])[::2], "0.6 0.35 0.25")
s += "<Viewpoint description='above' position='1.0 4.4 8.6' orientation='1 0 0 -0.42' fieldOfView='0.85'/><Viewpoint description='front' position='0.8 1.6 10.5' fieldOfView='0.9'/></Scene></X3D>\n"
(OUT/"22-rigid-lab.x3d").write_text(s); print('rigid done', round(time.time()-t0), flush=True)

# ---------------------------- 15: cloth self collision ----------------------------
RATIO = 0.6
FON = []; con, gaps_on, cr_on, st_on = cloth_run(RATIO, frames=FON, probe=True); FOFF = []; coff, _, cr_off, st_off = cloth_run(0.0, frames=FOFF, probe=True)
gap_ratio = min(gaps_on)/con.thick
def grid(y0, ratios, nsubs):
    out = []
    for r_ in ratios:
        for ns in nsubs:
            c_, _, cr_, _ = cloth_run(r_, y0=y0, nsub=ns, T=5.0, probe=True); out.append(dict(ratio=r_, nsub=ns, vmax=c_.vmax, vh_over_t=c_.vmax/(60*ns)/c_.thick, crossings_max=int(max(cr_)), crossings=cr_))
    return out
tun = grid(3.0, (0.1, 0.2, 0.3, 0.5), (4, 8, 16))   # grid 1: prediction 1
unsafe = [t for t in tun if t['vh_over_t'] >= LIM['tunnel_unsafe_vht']]; safe = [t for t in tun if t['vh_over_t'] <= LIM['tunnel_safe_vht']]
viol = sum(1 for t in safe if t['crossings_max'] > 0)+sum(1 for t in unsafe if t['crossings_max'] == 0)
tun2 = grid(2.0, (0.15, 0.3, 0.45), (5, 10, 20))     # grid 2: prediction 2, fresh data
viol2 = sum(1 for t in tun2 if t['vh_over_t'] <= LIM['tunnel2_safe_vht'] and t['crossings_max'] > 0); teeth = sum(1 for t in tun2 if t['crossings_max'] > 0)
stv = {}
for ns in (4, 8, 20):
    c_, _, cr_, st_ = (con, None, cr_on, st_on) if ns == 20 else cloth_run(RATIO, nsub=ns, probe=True); stv[ns] = dict(peak=float(max(st_)), rest=float(st_[-1]))
N['cloth'] = dict(grid=f"{CN}x{CN}", width=CW, spacing=con.sp, thickness_ratio=RATIO, thickness=con.thick, substeps=20, fps=60, min_gap_over_thickness=gap_ratio, crossings_on=cr_on, crossings_off=cr_off, crossings_off_max=int(max(cr_off)), stretch_on_max=float(max(st_on)), stretch_off_max=float(max(st_off)),
    vmax_main=con.vmax, stretch_vs_substeps={str(k): v for k, v in stv.items()},
    prediction1=dict(rule="no crossing when vmax*h/t <= 0.9; some crossing when >= 2 (written before grid 1)", y0=3.0, runs=tun, safe_cases=len(safe), unsafe_cases=len(unsafe), violations=viol, verdict="falsified" if viol else "held"),
    prediction2=dict(rule="no crossing in any run with vmax*h/t <= 1.0; at least one crossing somewhere in the grid (written after grid 1, tested on fresh runs)", y0=2.0, runs=tun2, violations=viol2, runs_with_crossings=teeth, verdict="held" if (viol2 == 0 and teeth >= LIM['tunnel2_teeth_runs']) else "falsified"), frames=len(FON))
hs = []; cloth_run(RATIO, T=2.0, hashes=hs); fr_ = replay_fresh('cloth')
record("tmp-ports/15-cloth-selfcollision", V5+"15-cloth-selfcollision.x3d", hs, [replay_block(HOST_FRESH, hs, fr_)],
    [ref_item("closest pair of non-neighbour particles over the run, over the collision thickness (brute force, independent of the hash)", gap_ratio, LIM['cloth_gap_over_thickness'], "pair distances, all n^2 pairs", rule="at least"),
     ref_item("edge/triangle crossings between sheet parts that do not touch, worst of 10 samples in 5 s (geometric, Moller-Trumbore brute force)", max(cr_on), LIM['cloth_crossings'], "exact segment-triangle test, independent of the particle-sphere collision"),
     ref_item("worst stretch-edge strain over the run", N['cloth']['stretch_on_max'], LIM['cloth_stretch'], "rest lengths of the sheet")],
    [dict(id="the crossing test applied to the same cloth with self collision off must fail", expect="fail", observed_failed=bool(max(cr_off) > LIM['cloth_crossings']), observed=int(max(cr_off)))],
    ["a predictor of tunnelling (two written predictions were falsified, see NOTES.md)", "cloth against rigid bodies other than a ball and a floor", "real fabric parameters", "friction between cloth layers (a single friction constant)", "another machine"], "particle-sphere collision with a geometric crossing check")
chk = lambda c1, c2: "".join("%02x%02x%02x " % (c1[0], c1[1], c1[2]) for _ in range(0))
S = 16; img = lambda c2: " ".join("0x%06x" % (0xf2f2f2 if ((x//4)+(y//4)) % 2 == 0 else c2) for y in range(S) for x in range(S))
tex = lambda c2: f"<PixelTexture containerField='baseTexture' image='{S} {S} 3 {img(c2)}' repeatS='true' repeatT='true'/>"
tc = " ".join(f"{i/(CN-1)*4:.3f} {j/(CN-1)*4:.3f}" for i in range(CN) for j in range(CN))
cs = Cloth(CN, CW, 0.9, 0.0); tri_idx = " ".join(f"{a} {b} {c} -1" for a, b, c in cs.tri)
s = HEAD("TMP 15 Cloth self collision: on and off", "The same 29 by 29 cloth dropped on a ball, left with self collision off and right with particle-sphere self collision on. Idea of Ten Minute Physics 15.") + "<TimeSensor DEF='CLK' cycleInterval='5' loop='true'/>\n"
s += f"<Transform translation='0 -0.03 0'><Shape>{pm('0.1 0.11 0.15',0.7)}<Box size='5.4 0.06 2.6'/></Shape></Transform>\n"
for ci, (fr_list, c2, offx) in enumerate(((FOFF, 0xb8532a, -1.4), (FON, 0x2a6f8f, 1.4))):
    off = np.array([offx, 0, 0]); s += f"<Transform translation='{offx} {con.ball_c[1]} 0'><Shape>{pm('0.75 0.78 0.85',0.25,None,None,0.15)}<Sphere radius='{con.ball_r}'/></Shape></Transform>\n"
    s += deform(f"CL{ci}", np.array(fr_list)+off, dict(coordIndex=tri_idx, solid="false", creaseAngle="1.2"), tail=f"<TextureCoordinate point='{tc}'/>", app=f"<Appearance><PhysicalMaterial baseColor='1 1 1' roughness='0.7' metallic='0'>{tex(c2)}</PhysicalMaterial></Appearance>")
s += "<!-- left, orange checker: self collision off. right, blue checker: on (thickness 0.6 of the particle spacing) -->\n<Viewpoint description='front' position='0 2.2 4.6' orientation='1 0 0 -0.38' fieldOfView='0.95'/><Viewpoint description='high' position='0 4.4 1.8' orientation='1 0 0 -1.2'/></Scene></X3D>\n"
(OUT/"15-cloth-selfcollision.x3d").write_text(s); print('cloth done', round(time.time()-t0), flush=True)
for a in PENDING: write_record(*a)
N['seconds'] = round(time.time()-t0, 1)
(OUT/'numbers5.json').write_text(json.dumps(N, indent=1, default=float)); print(json.dumps(N, indent=1, default=float))
