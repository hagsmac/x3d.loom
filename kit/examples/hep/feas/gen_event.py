#!/usr/bin/env python3
"""Load-matrix scene generator (Python stdlib only; SYNTHETIC, seeded; see evtcommon.py).

    python3 gen_event.py matrix OUTDIR      write the whole matrix + manifest.json
    python3 gen_event.py tracks 1000 out.x3d [--layout ils|shapes]
    python3 gen_event.py towers 10000 out.x3d [--mode instanced|merged]
    python3 gen_event.py points 100000 out.x3d
    python3 gen_event.py shells 16 out.x3d [--order outer-first|inner-first] [--solid 0|1] [--alpha 0.35]
    python3 gen_event.py mesh 200000 out.(x3d|gltf|glb)
"""
import base64, gzip, json, math, os, random, re, struct, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evtcommon import *  # noqa: E402,F401,F403

PALETTE = [(0.20, 0.45, 1.0), (0.10, 0.80, 1.0), (0.20, 0.95, 0.55), (0.70, 1.0, 0.25),
           (1.0, 0.90, 0.20), (1.0, 0.62, 0.15), (1.0, 0.35, 0.15), (1.0, 0.15, 0.30)]
KIND_RGB = {'jet': (1.0, 0.72, 0.18), 'soft': (0.35, 0.65, 1.0), 'muon': (1.0, 0.25, 0.25), 'electron': (0.25, 1.0, 0.45)}


def tracks_scene(n, layout='ils', npts=20, linewidth=None):
    ev, _ = make_event(n, seed=11, npts=npts)
    o = [head('tracks N=%d layout=%s' % (n, layout), comps=[('Rendering', 3)] if False else ()),
         viewpoint(), '    <Background skyColor="0.02 0.02 0.04"/>\n']
    app = '<Appearance>%s</Appearance>' % ('<LineProperties linewidthScaleFactor="%s"/>' % linewidth if linewidth else '')
    if layout == 'ils':
        pts, idx, cols = [], [], []
        for t in ev:
            base = len(pts)
            pts.extend(t['pts'])
            idx.extend(range(base, base + len(t['pts'])))
            idx.append(-1)
            cols.append(KIND_RGB[t['kind']])
        o.append('    <Shape>%s<IndexedLineSet colorPerVertex="false" coordIndex="%s">\n      <Coordinate point="%s"/>\n      <Color color="%s"/>\n    </IndexedLineSet></Shape>\n' % (
            app, ' '.join(map(str, idx)), ' '.join('%s %s %s' % (fmt(p[0]), fmt(p[1]), fmt(p[2])) for p in pts),
            ' '.join('%s %s %s' % (fmt(c[0], 2), fmt(c[1], 2), fmt(c[2], 2)) for c in cols)))
    else:
        for t in ev:
            k = len(t['pts'])
            c = KIND_RGB[t['kind']]
            o.append('    <Shape>%s<IndexedLineSet coordIndex="%s -1"><Coordinate point="%s"/><Color color="%s"/></IndexedLineSet></Shape>\n' % (
                app, ' '.join(map(str, range(k))),
                ' '.join('%s %s %s' % (fmt(p[0]), fmt(p[1]), fmt(p[2])) for p in t['pts']),
                ' '.join('%s %s %s' % (fmt(c[0], 2), fmt(c[1], 2), fmt(c[2], 2)) for _ in range(k))))
    o.append(TAIL)
    return ''.join(o)


def tower_grid(n, seed=5):
    rnd = random.Random(seed)
    nphi = max(8, int(round(math.sqrt(n * 2.5))))
    neta = max(2, int(round(n / nphi)))
    eta_max = 1.6
    jets = [(rnd.uniform(-1.2, 1.2), rnd.uniform(-math.pi, math.pi), rnd.uniform(40, 200)) for _ in range(6)]
    towers = []
    for ie in range(neta):
        eta = -eta_max + (ie + 0.5) * 2 * eta_max / neta
        for ip in range(nphi):
            phi = -math.pi + (ip + 0.5) * 2 * math.pi / nphi
            e = rnd.expovariate(1 / 0.35)
            for (je, jp, jpt) in jets:
                dphi = (phi - jp + math.pi) % (2 * math.pi) - math.pi
                e += jpt * 0.35 * math.exp(-((eta - je) ** 2 + dphi ** 2) / (2 * 0.22 ** 2))
            towers.append((eta, phi, e))
    emax = max(t[2] for t in towers)
    return towers, neta, nphi, eta_max, emax


def tower_xf(eta, phi, e, emax, neta, nphi, eta_max, r0=1.3):
    ch = math.cosh(eta)
    d = (math.cos(phi) / ch, math.sin(phi) / ch, math.tanh(eta))
    ephi = (-math.sin(phi), math.cos(phi), 0.0)
    eeta = (d[1] * ephi[2] - d[2] * ephi[1], d[2] * ephi[0] - d[0] * ephi[2], d[0] * ephi[1] - d[1] * ephi[0])
    # eeta = d x ephi ; check handedness: columns (ephi, eeta', d) with eeta' = d x ephi -> ephi x eeta' = d (right handed)
    wphi = r0 * 2 * math.pi / nphi * 0.92
    weta = (2 * eta_max / neta) * r0 / (ch * ch) * 0.92
    h = 0.03 + 1.1 * (e / emax) ** 0.6
    c = tuple(r0 + h / 2 for _ in range(1))
    pos = tuple(d[i] * (r0 + h / 2) for i in range(3))
    return d, ephi, eeta, wphi, weta, h, pos


def towers_scene(n, mode='instanced'):
    towers, neta, nphi, eta_max, emax = tower_grid(n)
    nb = len(PALETTE)
    o = [head('towers N=%d mode=%s' % (len(towers), mode)), viewpoint(pos=(3.4, 2.6, 4.2)),
         '    <Background skyColor="0.02 0.02 0.04"/>\n    <DirectionalLight direction="-0.4 -0.6 -0.7" intensity="0.9"/>\n']
    if mode == 'instanced':
        defined = set()
        for (eta, phi, e) in towers:
            d, ephi, eeta, wphi, weta, h, pos = tower_xf(eta, phi, e, emax, neta, nphi, eta_max)
            m = [[ephi[0], eeta[0], d[0]], [ephi[1], eeta[1], d[1]], [ephi[2], eeta[2], d[2]]]
            ax = mat_to_axis_angle(m)
            b = min(nb - 1, int((e / emax) ** 0.5 * nb))
            if b in defined:
                shp = '<Shape USE="B%d"/>' % b
            else:
                defined.add(b)
                c = PALETTE[b]
                shp = '<Shape DEF="B%d"><Appearance><Material diffuseColor="%s" emissiveColor="%s"/></Appearance><Box size="1 1 1"/></Shape>' % (
                    b, ' '.join(fmt(x, 2) for x in c), ' '.join(fmt(x * 0.25, 2) for x in c))
            o.append('    <Transform translation="%s %s %s" rotation="%s %s %s %s" scale="%s %s %s">%s</Transform>\n' % (
                fmt(pos[0]), fmt(pos[1]), fmt(pos[2]), fmt(ax[0], 4), fmt(ax[1], 4), fmt(ax[2], 4), fmt(ax[3], 4),
                fmt(wphi, 4), fmt(weta, 4), fmt(h, 3), shp))
    else:
        pts, idx, cols = [], [], []
        corners = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
        faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)]
        for (eta, phi, e) in towers:
            d, ephi, eeta, wphi, weta, h, pos = tower_xf(eta, phi, e, emax, neta, nphi, eta_max)
            base = len(pts)
            b = min(nb - 1, int((e / emax) ** 0.5 * nb))
            for (sx, sy, sz) in corners:
                p = [pos[i] + ephi[i] * sx * wphi / 2 + eeta[i] * sy * weta / 2 + d[i] * sz * h / 2 for i in range(3)]
                pts.append(p)
                cols.append(PALETTE[b])
            for f in faces:
                idx.extend(base + k for k in f)
                idx.append(-1)
        o.append('    <Shape><Appearance><Material diffuseColor="1 1 1" emissiveColor="0.12 0.12 0.12"/></Appearance>'
                 '<IndexedFaceSet solid="true" ccw="true" creaseAngle="0" coordIndex="%s">\n<Coordinate point="%s"/>\n<Color color="%s"/>\n</IndexedFaceSet></Shape>\n' % (
                     ' '.join(map(str, idx)), ' '.join('%s %s %s' % (fmt(p[0]), fmt(p[1]), fmt(p[2])) for p in pts),
                     ' '.join('%s %s %s' % (fmt(c[0], 2), fmt(c[1], 2), fmt(c[2], 2)) for c in cols)))
    o.append(TAIL)
    return ''.join(o)


def points_scene(n, fmt_='xml'):
    rnd = random.Random(3)
    ev, _ = make_event(600, seed=21, npts=64)
    P, C = [], []
    for i in range(n):
        if rnd.random() < 0.8:
            t = ev[rnd.randrange(len(ev))]
            p = t['pts'][rnd.randrange(len(t['pts']))]
            q = (p[0] + rnd.gauss(0, 0.004), p[1] + rnd.gauss(0, 0.004), p[2] + rnd.gauss(0, 0.004))
        else:
            r = 0.1 + 1.1 * math.sqrt(rnd.random())
            a = rnd.uniform(0, 2 * math.pi)
            q = (r * math.cos(a), r * math.sin(a), rnd.uniform(-2.9, 2.9))
        r = math.hypot(q[0], q[1])
        P.append(q)
        C.append(PALETTE[min(len(PALETTE) - 1, int(r / 1.25 * len(PALETTE)))])
    o = [head('points N=%d' % n), viewpoint(), '    <Background skyColor="0.02 0.02 0.04"/>\n']
    o.append('    <Shape><Appearance><PointProperties pointSizeScaleFactor="1"/></Appearance><PointSet>\n<Coordinate point="%s"/>\n<Color color="%s"/>\n</PointSet></Shape>\n' % (
        ' '.join('%s %s %s' % (fmt(p[0]), fmt(p[1]), fmt(p[2])) for p in P),
        ' '.join('%s %s %s' % (fmt(c[0], 1), fmt(c[1], 1), fmt(c[2], 1)) for c in C)))
    o.append(TAIL)
    return ''.join(o)


def shells_scene(m, order='outer-first', solid=0, alpha=0.35, rmin=0.4, rmax=2.4):
    cols = []
    for k in range(m):
        t = k / max(1, m - 1)
        cols.append((0.25 + 0.75 * t, 0.35 + 0.35 * (1 - abs(2 * t - 1)), 1.0 - 0.8 * t))
    radii = [rmin + (rmax - rmin) * k / max(1, m - 1) for k in range(m)]
    idx = list(range(m))
    if order == 'inner-first':
        pass
    elif order == 'outer-first':
        idx = idx[::-1]
    elif order == 'shuffled':
        random.Random(9).shuffle(idx)
    o = [head('shells M=%d order=%s solid=%s' % (m, order, solid)), viewpoint(pos=(1.5, 1.2, 6.5), fov=0.6),
         '    <Background skyColor="0.02 0.02 0.05"/>\n    <DirectionalLight direction="-0.3 -0.5 -0.8" intensity="0.8"/>\n']
    for k in idx:
        c = cols[k]
        o.append('    <Transform rotation="1 0 0 1.5708"><Shape><Appearance><Material diffuseColor="%s" emissiveColor="%s" transparency="%s"/></Appearance>'
                 '<Cylinder radius="%s" height="%s" top="false" bottom="false" solid="%s" subdivision="64"/></Shape></Transform>\n' % (
                     ' '.join(fmt(x, 2) for x in c), ' '.join(fmt(x * 0.3, 2) for x in c), fmt(1 - alpha, 2),
                     fmt(radii[k], 3), fmt(2.0 + 0.1 * k, 2), 'true' if solid else 'false'))
    # a bright opaque "track" bundle inside so artefacts show against a known structure
    ev, _ = make_event(60, seed=5, npts=24)
    idxs, pts = [], []
    for t in ev:
        b = len(pts)
        pts.extend(t['pts'])
        idxs.extend(list(range(b, b + len(t['pts']))) + [-1])
    o.append('    <Shape><Appearance><Material emissiveColor="1 1 0.6" diffuseColor="0 0 0"/></Appearance><IndexedLineSet coordIndex="%s"><Coordinate point="%s"/></IndexedLineSet></Shape>\n' % (
        ' '.join(map(str, idxs)), ' '.join('%s %s %s' % (fmt(p[0]), fmt(p[1]), fmt(p[2])) for p in pts)))
    o.append(TAIL)
    return ''.join(o)


def mesh_data(tris):
    """Procedural ribbed barrel: nu x nv quads (2 tris each), analytic normals. Returns (pos, nrm, idx)."""
    nq = tris // 2
    nu = int(math.sqrt(nq * 2.5))
    nv = max(2, nq // nu)
    pos, nrm = [], []
    for j in range(nv + 1):
        z = -3 + 6 * j / nv
        for i in range(nu + 1):
            a = 2 * math.pi * i / nu
            r = 2.0 + 0.04 * math.sin(a * 24) * math.cos(z * 9)
            pos.append((r * math.cos(a), r * math.sin(a), z))
            nrm.append((math.cos(a), math.sin(a), 0.0))
    idx = []
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i
            b = a + 1
            c = a + nu + 1
            d = c + 1
            idx.extend((a, b, d, a, d, c))
    return pos, nrm, idx


def mesh_scene(tris, kind='ifs', normals=True, gltf_name=None):
    pos, nrm, idx = mesh_data(tris)
    ntri = len(idx) // 3
    o = [head('mesh tris=%d %s' % (ntri, kind)), viewpoint(pos=(5, 3.5, 6.5), fov=0.8),
         '    <Background skyColor="0.03 0.03 0.06"/>\n    <DirectionalLight direction="-0.4 -0.5 -0.8" intensity="1"/>\n    <DirectionalLight direction="0.6 0.3 0.5" intensity="0.5" color="0.6 0.7 1"/>\n']
    if kind == 'inline':
        o.append('    <Inline url=\'"%s"\'/>\n' % gltf_name)
    else:
        nodes = '<Coordinate point="%s"/>' % ' '.join('%s %s %s' % (fmt(p[0], 4), fmt(p[1], 4), fmt(p[2], 4)) for p in pos)
        if normals:
            nodes += '<Normal vector="%s"/>' % ' '.join('%s %s %s' % (fmt(p[0], 3), fmt(p[1], 3), fmt(p[2], 3)) for p in nrm)
        o.append('    <Shape><Appearance><Material diffuseColor="0.6 0.7 0.85" specularColor="0.4 0.4 0.4" shininess="0.4"/></Appearance>'
                 '<IndexedTriangleSet solid="false" index="%s">%s</IndexedTriangleSet></Shape>\n' % (' '.join(map(str, idx)), nodes))
    o.append(TAIL)
    return ''.join(o), ntri


def gltf_bytes(tris, glb=False):
    pos, nrm, idx = mesh_data(tris)
    ntri = len(idx) // 3
    pb = b''.join(struct.pack('<3f', *p) for p in pos)
    nb = b''.join(struct.pack('<3f', *p) for p in nrm)
    ib = struct.pack('<%dI' % len(idx), *idx)
    blob = pb + nb + ib
    mn = [min(p[k] for p in pos) for k in range(3)]
    mx = [max(p[k] for p in pos) for k in range(3)]
    js = {"asset": {"version": "2.0", "generator": "feas/gen_event.py (SYNTHETIC)"},
          "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
          "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": 0}]}],
          "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [0.6, 0.7, 0.85, 1], "metallicFactor": 0.6, "roughnessFactor": 0.35}, "doubleSided": True}],
          "accessors": [{"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3", "min": mn, "max": mx},
                        {"bufferView": 1, "componentType": 5126, "count": len(nrm), "type": "VEC3"},
                        {"bufferView": 2, "componentType": 5125, "count": len(idx), "type": "SCALAR"}],
          "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pb), "target": 34962},
                          {"buffer": 0, "byteOffset": len(pb), "byteLength": len(nb), "target": 34962},
                          {"buffer": 0, "byteOffset": len(pb) + len(nb), "byteLength": len(ib), "target": 34963}],
          "buffers": [{"byteLength": len(blob)}]}
    if not glb:
        js["buffers"][0]["uri"] = "data:application/octet-stream;base64," + base64.b64encode(blob).decode()
        return json.dumps(js, separators=(',', ':')).encode(), ntri
    j = json.dumps(js, separators=(',', ':')).encode()
    j += b' ' * (-len(j) % 4)
    blob += b'\0' * (-len(blob) % 4)
    total = 12 + 8 + len(j) + 8 + len(blob)
    return (struct.pack('<III', 0x46546C67, 2, total) + struct.pack('<II', len(j), 0x4E4F534A) + j +
            struct.pack('<II', len(blob), 0x004E4942) + blob), ntri


def write(path, text):
    mode = 'wb' if isinstance(text, bytes) else 'w'
    with open(path, mode) as f:
        f.write(text)
    raw = text if isinstance(text, bytes) else text.encode()
    return len(raw), len(gzip.compress(raw, 6))


def elem_count(text):
    return len(re.findall(r'<[A-Za-z]', text)) if isinstance(text, str) else 0


def build_matrix(out):
    os.makedirs(out, exist_ok=True)
    man = []

    def add(name, cat, text, **kw):
        p = os.path.join(out, name)
        b, gz = write(p, text)
        man.append(dict(name=name, cat=cat, bytes=b, gz_bytes=gz, xml_elements=elem_count(text), **kw))
        print('wrote %-34s %9.2f MB  gz %7.2f MB  elems %d' % (name, b / 1e6, gz / 1e6, elem_count(text)), flush=True)

    for n in (100, 1000, 5000, 20000):
        add('tracks_ils_%d.x3d' % n, 'tracks', tracks_scene(n, 'ils'), n=n, layout='ils', pts=20)
    for n in (100, 1000, 5000):
        add('tracks_shapes_%d.x3d' % n, 'tracks', tracks_scene(n, 'shapes'), n=n, layout='shapes', pts=20)
    for n in (1000, 10000, 50000):
        add('towers_inst_%d.x3d' % n, 'towers', towers_scene(n, 'instanced'), n=n, mode='instanced')
        add('towers_merged_%d.x3d' % n, 'towers', towers_scene(n, 'merged'), n=n, mode='merged')
    for n in (10000, 100000, 1000000):
        add('points_%d.x3d' % n, 'points', points_scene(n), n=n)
    for m in (4, 16, 64):
        add('shells_%d.x3d' % m, 'shells', shells_scene(m), n=m)
    for t in (50000, 200000, 1000000):
        text, nt = mesh_scene(t, 'ifs')
        add('mesh_its_%d.x3d' % t, 'mesh', text, tris=nt, kind='IndexedTriangleSet+Normal')
        text, nt = mesh_scene(t, 'ifs', normals=False)
        add('mesh_its_nonormal_%d.x3d' % t, 'mesh', text, tris=nt, kind='IndexedTriangleSet, no Normal')
    for t in (50000, 200000, 1000000):
        for ext, glb in (('gltf', False), ('glb', True)):
            data, nt = gltf_bytes(t, glb)
            fn = 'mesh_%d.%s' % (t, ext)
            add(fn, 'mesh', data, tris=nt, kind=ext + ' (data only)', skip_bench=True)
            text, _ = mesh_scene(t, 'inline', gltf_name='scenes/' + fn)
            add('mesh_inline_%s_%d.x3d' % (ext, t), 'mesh', text, tris=nt, kind='Inline ' + ext, sidecar=fn)
    with open(os.path.join(out, 'manifest.json'), 'w') as f:
        json.dump(man, f, indent=1)


def main(a):
    if not a:
        print(__doc__)
        return 2
    cmd = a[0]
    opt = {}
    pos = []
    i = 1
    while i < len(a):
        if a[i].startswith('--'):
            opt[a[i][2:]] = a[i + 1]
            i += 2
        else:
            pos.append(a[i])
            i += 1
    if cmd == 'matrix':
        build_matrix(pos[0])
    elif cmd == 'tracks':
        write(pos[1], tracks_scene(int(pos[0]), opt.get('layout', 'ils')))
    elif cmd == 'towers':
        write(pos[1], towers_scene(int(pos[0]), opt.get('mode', 'instanced')))
    elif cmd == 'points':
        write(pos[1], points_scene(int(pos[0])))
    elif cmd == 'shells':
        write(pos[1], shells_scene(int(pos[0]), opt.get('order', 'outer-first'), int(opt.get('solid', 0)), float(opt.get('alpha', 0.35))))
    elif cmd == 'mesh':
        t = int(pos[0])
        ext = os.path.splitext(pos[1])[1]
        if ext in ('.gltf', '.glb'):
            write(pos[1], gltf_bytes(t, ext == '.glb')[0])
        else:
            write(pos[1], mesh_scene(t)[0])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
