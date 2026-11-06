#!/usr/bin/env python3
"""Crash-threshold probes (SwiftShader renderer SEGV with large custom-shader ribbon meshes). stdlib only.
   python3 gen_crash_probe.py site/looks   -> probe_P1..P4_<N>.x3d
P1 built-in Material, no custom attribs; P2 custom shader, NO vertex attribs; P3 custom shader + FloatVertexAttribute (aNext,aMeta); P4 = P3 but 3 shapes (chunks)"""
import sys, os
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_look as g

VS_MIN = """#version 300 es
precision highp float;
uniform mat4 x3d_ProjectionMatrix; uniform mat4 x3d_ModelViewMatrix;
in vec4 x3d_Vertex; in vec4 x3d_Color; out vec4 vC;
void main(){ vC = x3d_Color; gl_Position = x3d_ProjectionMatrix * (x3d_ModelViewMatrix * x3d_Vertex); }
"""
FS_MIN = """#version 300 es
precision highp float;
in vec4 vC; out vec4 o;
void main(){ o = vec4(vC.rgb * 0.5, 1.0); }
"""
VS_ATT = VS_MIN.replace('in vec4 x3d_Vertex;', 'in vec4 x3d_Vertex; in vec4 aNext; in vec4 aMeta;').replace('vC = x3d_Color;', 'vC = x3d_Color * (0.5 + 0.5 * aMeta.z) + 0.0 * aNext;')

def scene(n, kind, eps=0.0):
    tr = g.hero_tracks(n)
    pos, fov = g.camera('endon')
    o = ['<?xml version="1.0" encoding="UTF-8"?>\n<X3D profile="Immersive" version="4.0"><head><component name="Shaders" level="1"/></head><Scene>\n',
         '<NavigationInfo headlight="false"/><Viewpoint DEF="VP" position="%s" orientation="%s" fieldOfView="%s"/>\n' % (g.f3(pos), ' '.join(g.fmt(c, 5) for c in g.lookat(pos)), g.fmt(fov, 3))]
    chunks = [tr] if kind != 'P4' else [tr[i::3] for i in range(3)]
    for ch in chunks:
        geo = g.strip_geom(ch, eps=eps)
        if kind == 'P1' or kind == 'P2':
            import re
            geo = re.sub(r'<FloatVertexAttribute[^>]*/>', '', geo)
        if kind == 'P1':
            app = '<Appearance><Material emissiveColor="0.2 0.6 1"/></Appearance>'
        elif kind == 'P2':
            app = '<Appearance>%s</Appearance>' % g.shader_xml(VS_MIN, FS_MIN, [])
        else:
            app = '<Appearance>%s</Appearance>' % g.shader_xml(VS_ATT, FS_MIN, [])
        o.append('<Shape>%s%s</Shape>\n' % (app, geo))
    o.append('</Scene></X3D>\n')
    return ''.join(o)

if __name__ == '__main__':
    out = sys.argv[1]
    for n in (560, 1000, 3000):
        for k in ('P1', 'P2', 'P3', 'P4'):
            open(os.path.join(out, 'probe_%s_%d.x3d' % (k, n)), 'w').write(scene(n, k))
        open(os.path.join(out, 'probe_P1e_%d.x3d' % n), 'w').write(scene(n, 'P1', eps=0.004))   # non-degenerate triangles
