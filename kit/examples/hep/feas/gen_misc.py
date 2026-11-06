#!/usr/bin/env python3
"""Scene generators for the targeted experiments (Python stdlib only; SYNTHETIC, seeded).

    python3 gen_misc.py all OUTDIR      writes every experiment scene into OUTDIR (site/scenes)
Groups:
    lw_*        LineProperties linewidthScaleFactor ladder (is the width honoured?)
    tube_*      thick-track alternatives at N tracks: ils1 ils4 tube6 cross ext
    anim_*      track-growth animation: coordinterp, script_ci (Script writes coordIndex), marker (PositionInterpolator x N)
    freeze_*    field-callback exception fixture (law 32 / failure mode 88)
    pick_*      hover/pick on tracks: thin thick ribbon proxy anchor
    shellx_*    nested translucent shells: ordering x solid x alpha
    pbr_*       PhysicalMaterial / EnvironmentLight / emissive towers (tone-mapping comparison)
    part_*      ParticleSystem flash / sparks
"""
import math, os, random, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from evtcommon import make_event, fmt, lookat, viewpoint, head, TAIL  # noqa: E402
import gen_look as GL  # noqa: E402
from gen_event import shells_scene  # noqa: E402

KIND_RGB = {'jet': (1.0, 0.72, 0.18), 'soft': (0.35, 0.65, 1.0), 'muon': (1.0, 0.25, 0.25), 'electron': (0.25, 1.0, 0.45)}


def p3(p):
    return '%s %s %s' % (fmt(p[0]), fmt(p[1]), fmt(p[2]))


def wr(out, name, text):
    with open(os.path.join(out, name), 'w') as f:
        f.write(text)
    print('wrote', name, '%.2f MB' % (len(text) / 1e6), flush=True)


# ------------------------------------------------------------------ line width ladder
def lw_scene(factors=(1, 2, 4, 8, 16, 32), mode='ils'):
    o = [head('LineProperties ladder'), '    <NavigationInfo type=\'"NONE"\' headlight="false"/>\n'
         '    <Viewpoint DEF="VP" position="0 0 10" fieldOfView="0.785"/>\n    <Background skyColor="0 0 0"/>\n']
    n = len(factors)
    for i, f in enumerate(factors):
        y = 3.4 - i * (6.8 / (n - 1))
        o.append('    <Shape><Appearance><Material emissiveColor="1 1 1" diffuseColor="0 0 0"/><LineProperties linewidthScaleFactor="%s"/></Appearance>'
                 '<IndexedLineSet coordIndex="0 1 2 -1"><Coordinate point="-6 %s 0, 0 %s 0, 6 %s 0"/></IndexedLineSet></Shape>\n' % (f, fmt(y), fmt(y), fmt(y - 0.0)))
    o.append(TAIL)
    return ''.join(o)


# ------------------------------------------------------------------ tubes
def frames(P):
    T = []
    for k in range(len(P)):
        a = P[max(0, k - 1)]
        b = P[min(len(P) - 1, k + 1)]
        t = [b[i] - a[i] for i in range(3)]
        n = math.sqrt(sum(c * c for c in t)) or 1.0
        T.append([c / n for c in t])
    out = []
    for t in T:
        ref = (0.0, 0.0, 1.0) if abs(t[2]) < 0.9 else (1.0, 0.0, 0.0)
        nx = [t[1] * ref[2] - t[2] * ref[1], t[2] * ref[0] - t[0] * ref[2], t[0] * ref[1] - t[1] * ref[0]]
        l = math.sqrt(sum(c * c for c in nx))
        nx = [c / l for c in nx]
        bn = [t[1] * nx[2] - t[2] * nx[1], t[2] * nx[0] - t[0] * nx[2], t[0] * nx[1] - t[1] * nx[0]]
        out.append((t, nx, bn))
    return out


def tube_scene(n, variant, r=0.012):
    ev, _ = make_event(n, seed=11, npts=20)
    o = [head('tubes %s N=%d' % (variant, n)), viewpoint(), '    <Background skyColor="0.02 0.02 0.04"/>\n'
         '    <DirectionalLight direction="-0.4 -0.6 -0.7" intensity="1.0"/>\n    <DirectionalLight direction="0.7 0.3 0.6" intensity="0.4"/>\n']
    if variant in ('ils1', 'ils4'):
        pts, idx, cols = [], [], []
        for t in ev:
            b = len(pts)
            pts.extend(t['pts'])
            idx.extend(range(b, b + len(t['pts'])))
            idx.append(-1)
            cols.append(KIND_RGB[t['kind']])
        lp = '<LineProperties linewidthScaleFactor="4"/>' if variant == 'ils4' else ''
        o.append('    <Shape><Appearance>%s</Appearance><IndexedLineSet colorPerVertex="false" coordIndex="%s"><Coordinate point="%s"/><Color color="%s"/></IndexedLineSet></Shape>\n' % (
            lp, ' '.join(map(str, idx)), ' '.join(p3(p) for p in pts), ' '.join(p3(c) for c in cols)))
    elif variant == 'tube6':
        pts, nrm, idx, cols = [], [], [], []
        for t in ev:
            F = frames(t['pts'])
            b = len(pts)
            for k, P in enumerate(t['pts']):
                tt, nx, bn = F[k]
                for j in range(6):
                    a = 2 * math.pi * j / 6
                    d = [nx[i] * math.cos(a) + bn[i] * math.sin(a) for i in range(3)]
                    pts.append([P[i] + r * d[i] for i in range(3)])
                    nrm.append(d)
                    cols.append(KIND_RGB[t['kind']])
            for k in range(len(t['pts']) - 1):
                for j in range(6):
                    a = b + k * 6 + j
                    bq = b + k * 6 + (j + 1) % 6
                    idx.extend([a, bq, bq + 6, a, bq + 6, a + 6])
        o.append('    <Shape><Appearance><Material diffuseColor="1 1 1" emissiveColor="0.15 0.15 0.15"/></Appearance><IndexedTriangleSet solid="true" index="%s">'
                 '<Coordinate point="%s"/><Normal vector="%s"/><Color color="%s"/></IndexedTriangleSet></Shape>\n' % (
                     ' '.join(map(str, idx)), ' '.join(p3(p) for p in pts), ' '.join(fmt(c, 2) if False else p3(c) for c in nrm), ' '.join(p3(c) for c in cols)))
    elif variant == 'cross':
        pts, cnt, cols = [], [], []
        for t in ev:
            F = frames(t['pts'])
            for which in (1, 2):
                for k, P in enumerate(t['pts']):
                    d = F[k][which]
                    pts.append([P[i] - r * d[i] for i in range(3)])
                    pts.append([P[i] + r * d[i] for i in range(3)])
                    cols.extend([KIND_RGB[t['kind']]] * 2)
                cnt.append(2 * len(t['pts']))
        o.append('    <Shape><Appearance><Material diffuseColor="0 0 0" emissiveColor="1 1 1"/></Appearance><TriangleStripSet solid="false" stripCount="%s">'
                 '<Coordinate point="%s"/><Color color="%s"/></TriangleStripSet></Shape>\n' % (' '.join(map(str, cnt)), ' '.join(p3(p) for p in pts), ' '.join(p3(c) for c in cols)))
    elif variant == 'ext':
        cs = ' '.join('%s %s' % (fmt(r * math.cos(2 * math.pi * j / 6), 4), fmt(r * math.sin(2 * math.pi * j / 6), 4)) for j in range(7))
        for t in ev:
            c = KIND_RGB[t['kind']]
            o.append('    <Shape><Appearance><Material diffuseColor="%s" emissiveColor="%s"/></Appearance><Extrusion beginCap="false" endCap="false" solid="false" creaseAngle="1.5" crossSection="%s" spine="%s"/></Shape>\n' % (
                p3(c), p3([x * 0.25 for x in c]), cs, ' '.join(p3(p) for p in t['pts'])))
    o.append(TAIL)
    return ''.join(o)


# ------------------------------------------------------------------ animation
def anim_scene(n, variant, npts=20, keys=10):
    ev, _ = make_event(n, seed=11, npts=npts)
    o = [head('anim %s N=%d' % (variant, n), comps=[('Scripting', 1)] if variant == 'script_ci' else ()), viewpoint(), '    <Background skyColor="0.02 0.02 0.04"/>\n',
         '    <TimeSensor DEF="TS" cycleInterval="4" loop="true"/>\n']
    allp = [t['pts'] for t in ev]
    if variant in ('coordinterp', 'script_ci'):
        flat = [p for pts in allp for p in pts]
        idx = []
        b = 0
        for pts in allp:
            idx.extend(range(b, b + len(pts)))
            idx.append(-1)
            b += len(pts)
        col = ' '.join(p3(KIND_RGB[t['kind']]) for t in ev)
        if variant == 'coordinterp':
            kv = []
            for k in range(keys):
                m = max(2, int(round(npts * (k + 1) / keys)))
                for pts in allp:
                    for i in range(npts):
                        kv.append(p3(pts[min(i, m - 1)]))
            o.append('    <Shape><IndexedLineSet colorPerVertex="false" coordIndex="%s"><Coordinate DEF="CO" point="%s"/><Color color="%s"/></IndexedLineSet></Shape>\n' % (
                ' '.join(map(str, idx)), ' '.join(p3(p) for p in flat), col))
            o.append('    <CoordinateInterpolator DEF="CI" key="%s" keyValue="%s"/>\n' % (' '.join(fmt((k) / (keys - 1), 3) for k in range(keys)), ' '.join(kv)))
            o.append('    <ROUTE fromNode="TS" fromField="fraction_changed" toNode="CI" toField="set_fraction"/>\n    <ROUTE fromNode="CI" fromField="value_changed" toNode="CO" toField="set_point"/>\n')
        else:
            o.append('    <Shape><IndexedLineSet DEF="ILS" colorPerVertex="false" coordIndex="%s"><Coordinate point="%s"/><Color color="%s"/></IndexedLineSet></Shape>\n' % (
                ' '.join(map(str, idx)), ' '.join(p3(p) for p in flat), col))
            js = ('ecmascript:\n'
                  'var NT = %d, NP = %d;\n'
                  'function set_fraction(f, t) {\n'
                  '  try {\n'
                  '    var m = Math.max(2, Math.floor(2 + f * (NP - 2)));\n'
                  '    var out = new MFInt32();\n'
                  '    var k = 0;\n'
                  '    for (var i = 0; i < NT; ++i) { for (var j = 0; j < m; ++j) out[k++] = i * NP + j; out[k++] = -1; }\n'
                  '    ci = out;\n'
                  '  } catch (e) { Browser.print("script error " + e); }\n'
                  '}\n') % (n, npts)
            o.append('    <Script DEF="SC"><field name="set_fraction" type="SFFloat" accessType="inputOnly"/><field name="ci" type="MFInt32" accessType="outputOnly"/>\n'
                     '<![CDATA[%s]]></Script>\n' % js)
            o.append('    <ROUTE fromNode="TS" fromField="fraction_changed" toNode="SC" toField="set_fraction"/>\n    <ROUTE fromNode="SC" fromField="ci" toNode="ILS" toField="set_coordIndex"/>\n')
    elif variant == 'marker':
        o.append('    <Shape><Appearance><Material emissiveColor="0.3 0.3 0.5"/></Appearance><IndexedLineSet coordIndex="%s"><Coordinate point="%s"/></IndexedLineSet></Shape>\n' % (
            ' '.join(' '.join(map(str, range(i * npts, (i + 1) * npts))) + ' -1' for i in range(n)), ' '.join(p3(p) for pts in allp for p in pts)))
        o.append('    <Shape DEF="DOT" visible="false"><Appearance><Material emissiveColor="1 0.9 0.4" diffuseColor="0 0 0"/></Appearance><Sphere radius="0.03"/></Shape>\n'.replace(' visible="false"', ''))
        for i, pts in enumerate(allp):
            o.append('    <Transform DEF="M%d"><Shape USE="DOT"/></Transform><PositionInterpolator DEF="P%d" key="%s" keyValue="%s"/>\n'
                     '    <ROUTE fromNode="TS" fromField="fraction_changed" toNode="P%d" toField="set_fraction"/><ROUTE fromNode="P%d" fromField="value_changed" toNode="M%d" toField="set_translation"/>\n' % (
                         i, i, ' '.join(fmt(k / (npts - 1), 3) for k in range(npts)), ' '.join(p3(p) for p in pts), i, i, i))
    o.append(TAIL)
    return ''.join(o)


# ------------------------------------------------------------------ freeze fixture
def freeze_scene(script=True):
    sc = ''
    if script:
        sc = ('    <Script DEF="SC"><field name="set_fraction" type="SFFloat" accessType="inputOnly"/><field name="count" type="SFInt32" accessType="outputOnly"/>\n'
              '<![CDATA[ecmascript:\nvar n = 0;\nfunction set_fraction(f, t) { n++; if (n === 13) { throw new Error("script boom"); } count = n; }\n]]></Script>\n'
              '    <ROUTE fromNode="CLK" fromField="fraction_changed" toNode="SC" toField="set_fraction"/>\n')
    return (head('field-callback exception fixture', comps=[('Scripting', 1)]) +
            '    <Viewpoint DEF="VP" position="0 0 6"/>\n'
            '    <TimeSensor DEF="CLK" cycleInterval="2" loop="true"/>\n'
            '    <TimeSensor DEF="CLK2" cycleInterval="3" loop="true"/>\n'
            '    <PositionInterpolator DEF="PI" key="0 0.5 1" keyValue="-2 0 0, 2 1 0, -2 0 0"/>\n'
            '    <PositionInterpolator DEF="PI2" key="0 1" keyValue="0 -2 0, 0 2 0"/>\n'
            '    <Transform DEF="T"><Shape><Appearance><Material diffuseColor="1 0.5 0"/></Appearance><Box size="0.5 0.5 0.5"/></Shape></Transform>\n'
            '    <Transform DEF="T2"><Shape><Appearance><Material diffuseColor="0 0.5 1"/></Appearance><Sphere radius="0.3"/></Shape></Transform>\n' + sc +
            '    <ROUTE fromNode="CLK" fromField="fraction_changed" toNode="PI" toField="set_fraction"/>\n'
            '    <ROUTE fromNode="PI" fromField="value_changed" toNode="T" toField="set_translation"/>\n'
            '    <ROUTE fromNode="CLK2" fromField="fraction_changed" toNode="PI2" toField="set_fraction"/>\n'
            '    <ROUTE fromNode="PI2" fromField="value_changed" toNode="T2" toField="set_translation"/>\n' + TAIL)


# ------------------------------------------------------------------ picking
def pick_scene(n, variant):
    ev, _ = make_event(n * 3, seed=31, npts=24)
    ev = [t for t in ev if t['kind'] != 'muon'][:n]
    comps = [('Shaders', 1), ('Rendering', 3), ('X_ITE', 1)] if variant == 'ribbon' else [('Picking', 1)] if variant == 'picksensor' else []
    o = [head('pick %s N=%d' % (variant, n), comps=comps), viewpoint(pos=(0.3, 0.2, 5.4), fov=0.85), '    <Background skyColor="0.02 0.02 0.04"/>\n']
    if variant == 'ribbon':
        o.append('    <!-- shared appearance; per-track data in attributes -->\n')
    for i, t in enumerate(ev):
        c = KIND_RGB[t['kind']]
        pts = t['pts']
        tag = '<MetadataString name="track" value=\'"id=%d kind=%s pT=%.2f q=%+d"\'/>' % (i, t['kind'], t['pt'], t['q'])
        coord = '<Coordinate DEF="C%d" point="%s"/>' % (i, ' '.join(p3(p) for p in pts))
        ils = '<IndexedLineSet coordIndex="%s -1">%s<Color color="%s"/></IndexedLineSet>' % (' '.join(map(str, range(len(pts)))), coord, ' '.join(p3(c) for _ in pts))
        sensor = '<TouchSensor DEF="TS%d" description="track %d  %s  pT=%.2f GeV  q=%+d"/>' % (i, i, t['kind'], t['pt'], t['q'])
        if variant == 'thin':
            o.append('    <Group>%s<Shape><Appearance/>%s</Shape></Group>\n' % (sensor, ils))
        elif variant == 'thick':
            o.append('    <Group>%s<Shape><Appearance><LineProperties linewidthScaleFactor="6"/></Appearance>%s</Shape></Group>\n' % (sensor, ils))
        elif variant == 'anchor':
            o.append('    <Anchor DEF="AN%d" description="track %d %s pT=%.2f" url=\'"anchor_hit.html?i=%d"\'><Shape><Appearance><LineProperties linewidthScaleFactor="6"/></Appearance>%s</Shape></Anchor>\n' % (i, i, t['kind'], t['pt'], i, ils))
        elif variant == 'proxy':
            F = frames(pts)
            vs, nr, idx = [], [], []
            for k, P in enumerate(pts):
                tt, nx, bn = F[k]
                for j in range(4):
                    a = 2 * math.pi * j / 4
                    d = [nx[m] * math.cos(a) + bn[m] * math.sin(a) for m in range(3)]
                    vs.append([P[m] + 0.025 * d[m] for m in range(3)])
            for k in range(len(pts) - 1):
                for j in range(4):
                    a = k * 4 + j
                    bq = k * 4 + (j + 1) % 4
                    idx.extend([a, bq, bq + 4, a, bq + 4, a + 4])
            proxy = '<Shape><Appearance><Material transparency="0.999"/></Appearance><IndexedTriangleSet solid="false" index="%s"><Coordinate point="%s"/></IndexedTriangleSet></Shape>' % (
                ' '.join(map(str, idx)), ' '.join(p3(p) for p in vs))
            o.append('    <Group>%s<Shape><Appearance/>%s</Shape>%s</Group>\n' % (sensor, ils, proxy))
        elif variant == 'ribbon':
            tr = dict(id=i, pts=pts, s=[k / (len(pts) - 1) for k in range(len(pts))], color=c, pt01=0.5, seed=i * 0.7 + 1.0)
            sh = GL.shader_xml(GL.VS_RIBBON, GL.FS_RIBBON, [('uTime', 'SFFloat', 'initializeOnly', '0.3'), ('uGrow', 'SFFloat', 'initializeOnly', '1'),
                                                           ('uExposure', 'SFFloat', 'initializeOnly', '1'), ('uWidth', 'SFFloat', 'initializeOnly', '2')], None)
            o.append('    <Group>%s<Shape><Appearance>%s%s%s</Appearance>%s</Shape>%s</Group>\n' % (
                sensor.replace('<TouchSensor', '<TouchSensor'), GL.ADD_BLEND.replace(' DEF="BM_ADD"', ''), GL.NODEPTH.replace(' DEF="DM_RO"', ''), sh, GL.strip_geom([tr]),
                '<Shape><Appearance/><IndexedLineSet coordIndex="0 -1">%s</IndexedLineSet></Shape>' % coord if False else '<!-- c%d -->' % i))
            o.append('    <Group><Shape><Appearance><Material transparency="1"/></Appearance><IndexedLineSet coordIndex="%s -1">%s</IndexedLineSet></Shape></Group>\n' % (' '.join(map(str, range(len(pts)))), coord))
        elif variant == 'picksensor':
            o.append('    <Shape DEF="SH%d"><Appearance/>%s</Shape>\n' % (i, ils))
    if variant == 'picksensor':
        # a sphere sweeping through the bundle; LinePickSensor / PrimitivePickSensor against the track shapes
        o.append('    <Transform DEF="PROBE" translation="0 0 0"><PrimitivePickSensor DEF="PPS" intersectionType="GEOMETRY" objectType=\'"ALL"\'>'
                 '<Sphere radius="0.6" containerField="pickingGeometry"/>' + ''.join('<Shape USE="SH%d" containerField="pickTarget"/>' % i for i in range(n)) + '</PrimitivePickSensor>'
                 '<Shape><Appearance><Material transparency="0.8" diffuseColor="1 1 0"/></Appearance><Sphere radius="0.6"/></Shape></Transform>\n')
    o.append(TAIL)
    return ''.join(o)


# ------------------------------------------------------------------ PBR / tone mapping
def pbr_scene(env=False):
    """Emissive PBR towers + metallic detector rings + glassy shell, lit by directional lights (or EnvironmentLight)."""
    rnd = random.Random(8)
    o = ['<?xml version="1.0" encoding="UTF-8"?>\n<X3D profile="Full" version="4.0">\n  <head>\n    <component name="Lighting" level="3"/>\n    <component name="Shape" level="2"/>\n'
         '    <component name="CubeMapTexturing" level="3"/>\n    <meta name="title" content="PBR look"/>\n  </head>\n  <Scene>\n']
    pos = (3.4, 2.4, 6.4)
    ori = lookat(pos)
    o.append('    <NavigationInfo type=\'"EXAMINE"\' headlight="false" transitionType=\'"TELEPORT"\'/>\n    <Viewpoint DEF="VP" position="%s" orientation="%s" fieldOfView="0.8"/>\n' % (p3(pos), ' '.join(fmt(c, 5) for c in ori)))
    o.append('    <Background skyColor="0.01 0.015 0.03"/>\n')
    if env:
        o.append('    <EnvironmentLight intensity="1.0"><ComposedCubeMapTexture containerField="diffuseTexture">'
                 + ''.join('<ImageTexture containerField="%sTexture" url=\'"env_%s.png"\'/>' % (f, f) for f in ('front', 'back', 'left', 'right', 'top', 'bottom'))
                 + '</ComposedCubeMapTexture></EnvironmentLight>\n')
    o.append('    <DirectionalLight direction="-0.5 -0.6 -0.6" intensity="1.6" color="1 0.95 0.9"/>\n    <DirectionalLight direction="0.7 0.2 0.5" intensity="0.8" color="0.4 0.6 1"/>\n')
    # metallic barrel rings
    for i, (r, h) in enumerate([(1.0, 3.0), (1.6, 3.4), (2.2, 3.8)]):
        o.append('    <Transform rotation="1 0 0 1.5708"><Shape><Appearance><PhysicalMaterial baseColor="0.55 0.62 0.75" metallic="0.9" roughness="0.28" emissiveColor="0 0 0" '
                 'transparency="0.0"/></Appearance><Cylinder radius="%s" height="%s" top="false" bottom="false" solid="false" subdivision="96"/></Shape></Transform>\n' % (r, h))
    # emissive towers (instanced Box)
    for i in range(96):
        a = 2 * math.pi * i / 96
        h = 0.1 + 0.9 * rnd.random() ** 2
        r0 = 2.3
        shp = ('<Shape DEF="TW_HOT"><Appearance><PhysicalMaterial baseColor="1 0.5 0.1" emissiveColor="3 1.3 0.2" metallic="0" roughness="0.5"/></Appearance><Box size="1 1 1"/></Shape>'
               if i == 0 else '<Shape USE="TW_HOT"/>')
        o.append('    <Transform translation="%s %s 0" rotation="0 0 1 %s" scale="0.12 %s 0.5">%s</Transform>\n' % (
            fmt((r0 + h / 2) * math.cos(a)), fmt((r0 + h / 2) * math.sin(a)), fmt(a - math.pi / 2), fmt(h), shp))
    o.append(TAIL)
    return ''.join(o)


def write_env_pngs(out):
    def mk(face):
        def px(u, v):
            # warm top light, cool horizon band, dark floor; strong bright softbox on 'top'
            y = 1 - v
            if face == 'top':
                r = math.hypot(u - 0.5, v - 0.5)
                g = 255 if r < 0.2 else int(255 * max(0.0, 1 - (r - 0.2) * 3))
                return (g, g, g, 255)
            if face == 'bottom':
                return (6, 8, 14, 255)
            band = math.exp(-((y - 0.55) ** 2) / 0.02)
            return (int(30 + 40 * band), int(50 + 80 * band), int(90 + 150 * band), 255)
        return px
    for f in ('front', 'back', 'left', 'right', 'top', 'bottom'):
        open(os.path.join(out, 'env_%s.png' % f), 'wb').write(GL.png_rgba(64, 64, mk(f)))


# ------------------------------------------------------------------ particles
def part_scene(kind='flash'):
    o = ['<?xml version="1.0" encoding="UTF-8"?>\n<X3D profile="Full" version="4.0">\n  <head>\n    <component name="ParticleSystems" level="2"/>\n    <component name="X_ITE" level="1"/>\n    <meta name="title" content="particles %s"/>\n  </head>\n  <Scene>\n' % kind]
    pos = (0, 0, 6)
    o.append('    <NavigationInfo type=\'"NONE"\' headlight="false"/>\n    <Viewpoint DEF="VP" position="0 0 6" fieldOfView="0.8"/>\n    <Background skyColor="0.005 0.01 0.02"/>\n')
    o.append('    <TimeSensor DEF="TS" cycleInterval="2" loop="true"/>\n')
    app = ('<Appearance><BlendMode sourceColorFactor="SRC_ALPHA" destinationColorFactor="ONE"/><DepthMode depthMask="false"/>'
           '<Material emissiveColor="1 1 1" diffuseColor="0 0 0"/><ImageTexture url=\'"glow.png"\'/></Appearance>')
    if kind == 'flash':
        o.append('    <ParticleSystem geometryType="QUAD" maxParticles="1500" particleLifetime="1.4" lifetimeVariation="0.4" particleSize="0.22 0.22" colorKey="0 0.3 0.7 1">'
                 + app +
                 '<ExplosionEmitter position="0 0 0" speed="2.4" variation="0.6" mass="0" surfaceArea="0"/>'
                 '<ColorRGBA containerField="color" color="1 1 1 1, 1 0.8 0.3 0.9, 0.9 0.35 0.1 0.5, 0.2 0.1 0.3 0"/>'
                 '</ParticleSystem>\n')
    else:
        o.append('    <ParticleSystem geometryType="LINE" maxParticles="600" particleLifetime="1.1" lifetimeVariation="0.5" particleSize="0.3 0.3" colorKey="0 1">'
                 '<Appearance><BlendMode sourceColorFactor="SRC_ALPHA" destinationColorFactor="ONE"/><DepthMode depthMask="false"/><Material emissiveColor="1 0.8 0.4" diffuseColor="0 0 0"/><LineProperties linewidthScaleFactor="2"/></Appearance>'
                 '<ConeEmitter position="0 0 0" direction="1 0 0" angle="3.14" speed="3.0" variation="0.8" mass="0" surfaceArea="0"/>'
                 '<ColorRGBA containerField="color" color="1 0.9 0.5 1, 1 0.4 0.1 0"/></ParticleSystem>\n')
    o.append(TAIL)
    return ''.join(o)


def main(a):
    out = a[1] if len(a) > 1 else 'site/scenes'
    os.makedirs(out, exist_ok=True)
    wr(out, 'lw_ladder.x3d', lw_scene())
    for n in (100, 1000):
        for v in ('ils1', 'ils4', 'tube6', 'cross', 'ext'):
            wr(out, 'tube_%s_%d.x3d' % (v, n), tube_scene(n, v))
    for n in (300, 1000):
        for v in ('coordinterp', 'script_ci', 'marker'):
            wr(out, 'anim_%s_%d.x3d' % (v, n), anim_scene(n, v))
    wr(out, 'freeze_fixture.x3d', freeze_scene(True))
    wr(out, 'freeze_noscript.x3d', freeze_scene(False))
    for v in ('thin', 'thick', 'anchor', 'proxy', 'ribbon', 'picksensor'):
        wr(out, 'pick_%s_40.x3d' % v, pick_scene(40, v))
    for m in (16,):
        for order in ('outer-first', 'inner-first', 'shuffled'):
            for solid in (0, 1):
                wr(out, 'shellx_%d_%s_s%d.x3d' % (m, order, solid), shells_scene(m, order, solid, 0.45))
    for m in (4, 16, 64):
        wr(out, 'shellx_cost_%d.x3d' % m, shells_scene(m, 'outer-first', 0, 0.35))
    wr(out, 'pbr_dir.x3d', pbr_scene(False))
    wr(out, 'pbr_env.x3d', pbr_scene(True))
    write_env_pngs(out)
    GL.glow_png(os.path.join(out, 'glow.png'))
    wr(out, 'part_flash.x3d', part_scene('flash'))
    wr(out, 'part_sparks.x3d', part_scene('sparks'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
