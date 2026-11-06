"""Shared synthetic-event model for the feasibility scripts (Python stdlib only).

SYNTHETIC: helices follow the textbook relation rho[m] = pT[GeV] / (0.3 * B[T]) with B = 3.8 T,
tan(lambda) = sinh(eta). No detector response, no real event. Seeds are fixed, so every file is
reproducible byte for byte (law 4). Units: metres. Beam axis = +Z (X3D is Y-up; the viewpoint is
placed to look at the origin, nothing is rotated).
"""
import math
import random

B_FIELD = 3.8
R_TRACKER = 1.2      # tracks stop here unless they are muons
R_MUON = 6.5
Z_MAX = 2.9


def helix(pt, eta, phi, q, npts=20, z0=0.0, rmax=R_TRACKER, zmax=Z_MAX, max_turns=1.25):
    """Return [(x, y, z), ...] npts points, equally spaced in transverse arc length."""
    rho = pt / (0.3 * B_FIELD)
    rs = q * rho
    if 2 * rho > rmax:
        l_end = 2 * rho * math.asin(rmax / (2 * rho))
    else:
        l_end = max_turns * 2 * math.pi * rho
    sz = math.sinh(eta)
    if abs(sz) > 1e-9:
        l_end = min(l_end, max(0.05, (zmax - z0 * math.copysign(1.0, sz)) / abs(sz)))
    pts = []
    for i in range(npts):
        l = l_end * i / (npts - 1)
        x = rs * (math.sin(phi) - math.sin(phi - l / rs))
        y = rs * (math.cos(phi - l / rs) - math.cos(phi))
        z = z0 + l * sz
        pts.append((x, y, z))
    return pts


def make_event(n_tracks, seed=7, npts=20, n_jets=6, muon_frac=0.01):
    """A toy pp event: n_jets collimated jets + isolated leptons + soft pile-up, in one list.

    Each track: dict(pt, eta, phi, q, kind, jet, pts). kind in {jet, soft, muon, electron}.
    """
    rnd = random.Random(seed)
    jets = []
    for j in range(n_jets):
        jets.append((rnd.uniform(-2.0, 2.0), rnd.uniform(-math.pi, math.pi), rnd.uniform(60, 250)))
    out = []
    for i in range(n_tracks):
        u = rnd.random()
        if u < muon_frac:
            kind = 'muon'
            pt = rnd.uniform(25, 120)
            eta = rnd.uniform(-1.4, 1.4)
            phi = rnd.uniform(-math.pi, math.pi)
            jet = -1
        elif u < 0.55:
            kind = 'jet'
            jet = rnd.randrange(n_jets)
            je, jp, jpt = jets[jet]
            eta = je + rnd.gauss(0, 0.18)
            phi = jp + rnd.gauss(0, 0.18)
            pt = max(0.45, rnd.expovariate(1.0 / (0.06 * jpt + 1.0)))
        elif u < 0.57:
            kind = 'electron'
            pt = rnd.uniform(15, 80)
            eta = rnd.uniform(-1.8, 1.8)
            phi = rnd.uniform(-math.pi, math.pi)
            jet = -1
        else:
            kind = 'soft'
            pt = max(0.4, rnd.expovariate(1 / 0.9))
            eta = rnd.uniform(-2.2, 2.2)
            phi = rnd.uniform(-math.pi, math.pi)
            jet = -1
        pt = min(pt, 400.0)
        q = 1 if rnd.random() < 0.5 else -1
        z0 = rnd.gauss(0, 0.04)
        rmax = R_MUON if kind == 'muon' else R_TRACKER
        zmax = 6.5 if kind == 'muon' else Z_MAX
        pts = helix(pt, eta, phi, q, npts=npts, z0=z0, rmax=rmax, zmax=zmax)
        out.append(dict(pt=pt, eta=eta, phi=phi, q=q, kind=kind, jet=jet, pts=pts, id=i))
    return out, jets


def fmt(v, nd=3):
    s = ('%.' + str(nd) + 'f') % v
    if s.startswith('-0.') and float(s) == 0:
        s = s[1:]
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s or '0'


def lookat(pos, target=(0, 0, 0), up=(0, 1, 0)):
    """Axis-angle orientation (x, y, z, angle) that points -Z toward target, X3D Viewpoint convention."""
    f = [target[i] - pos[i] for i in range(3)]
    n = math.sqrt(sum(c * c for c in f))
    f = [c / n for c in f]
    # camera looks down -Z: its Z axis = -f
    z = [-c for c in f]
    x = [up[1] * z[2] - up[2] * z[1], up[2] * z[0] - up[0] * z[2], up[0] * z[1] - up[1] * z[0]]
    nx = math.sqrt(sum(c * c for c in x))
    x = [c / nx for c in x]
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    return mat_to_axis_angle([[x[0], y[0], z[0]], [x[1], y[1], z[1]], [x[2], y[2], z[2]]])


def mat_to_axis_angle(m):
    tr = m[0][0] + m[1][1] + m[2][2]
    ang = math.acos(max(-1.0, min(1.0, (tr - 1) / 2)))
    if ang < 1e-9:
        return (0, 0, 1, 0)
    if abs(ang - math.pi) < 1e-6:
        # symmetric part
        xx = math.sqrt(max(0.0, (m[0][0] + 1) / 2))
        yy = math.sqrt(max(0.0, (m[1][1] + 1) / 2))
        zz = math.sqrt(max(0.0, (m[2][2] + 1) / 2))
        if xx >= yy and xx >= zz:
            yy = math.copysign(yy, m[0][1]) if xx > 1e-9 else yy
            zz = math.copysign(zz, m[0][2]) if xx > 1e-9 else zz
        elif yy >= zz:
            xx = math.copysign(xx, m[0][1])
            zz = math.copysign(zz, m[1][2])
        else:
            xx = math.copysign(xx, m[0][2])
            yy = math.copysign(yy, m[1][2])
        return (xx, yy, zz, ang)
    s = 2 * math.sin(ang)
    return ((m[2][1] - m[1][2]) / s, (m[0][2] - m[2][0]) / s, (m[1][0] - m[0][1]) / s, ang)


def head(title, comps=(), extra_meta=(), profile='Immersive'):
    c = ''.join('    <component name="%s" level="%d"/>\n' % x for x in comps)
    m = ''.join('    <meta name="%s" content="%s"/>\n' % x for x in extra_meta)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<X3D profile="%s" version="4.0">\n  <head>\n%s%s'
            '    <meta name="title" content="%s"/>\n'
            '    <meta name="generator" content="feas/ scripts (SYNTHETIC data, seeded)"/>\n'
            '  </head>\n  <Scene>\n') % (profile, c, m, title)


TAIL = '  </Scene>\n</X3D>\n'


def viewpoint(pos=(3.2, 2.2, 5.0), target=(0, 0, 0), fov=0.9, descr='main'):
    o = lookat(pos, target)
    return ('    <NavigationInfo type=\'"EXAMINE" "ANY"\' headlight="false" transitionType=\'"TELEPORT"\'/>\n'
            '    <Viewpoint DEF="VP" description="%s" position="%s" orientation="%s" fieldOfView="%s" centerOfRotation="%s"/>\n'
            % (descr, ' '.join(fmt(c) for c in pos), ' '.join(fmt(c, 5) for c in o), fmt(fov, 3),
               ' '.join(fmt(c) for c in target)))
