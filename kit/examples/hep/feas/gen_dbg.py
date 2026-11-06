#!/usr/bin/env python3
"""Minimal shader pipeline probes (stdlib only): which ingredient breaks the hero look? Writes site/looks/dbg_m*.x3d"""
import os, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_look as GL
VS = "#version 300 es\nprecision highp float;\nuniform mat4 x3d_ProjectionMatrix;\nuniform mat4 x3d_ModelViewMatrix;\nin vec4 x3d_Vertex;\nvoid main() { gl_Position = x3d_ProjectionMatrix * (x3d_ModelViewMatrix * x3d_Vertex); }\n"
FS = "#version 300 es\nprecision highp float;\nout vec4 fragColor;\nvoid main() { fragColor = vec4(1.0, 0.2, 0.1, 1.0); }\n"
HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n<X3D profile="Immersive" version="4.0"><head><component name="Shaders" level="1"/><component name="X_ITE" level="1"/></head><Scene>\n'
        '<NavigationInfo type=\'"NONE"\' headlight="false"/><Viewpoint DEF="VP" position="0 0 6" fieldOfView="0.8"/><Background skyColor="0 0 0.05"/>\n')
QUAD = '<IndexedFaceSet coordIndex="0 1 2 3 -1"><Coordinate point="-1 -1 0, 1 -1 0, 1 1 0, -1 1 0"/></IndexedFaceSet>'
def sh(vs=VS, fs=FS): return GL.shader_xml(vs, fs, [])
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'site', 'looks')
def w(n, body): open(os.path.join(out, n), 'w').write(HEAD + body + '</Scene></X3D>\n')
w('dbg_m1.x3d', '<Shape><Appearance>%s</Appearance>%s</Shape>' % (sh(), QUAD))
w('dbg_m2.x3d', '<Shape><Appearance>%s%s</Appearance>%s</Shape>' % (GL.ADD_BLEND, sh(), QUAD))
w('dbg_m3.x3d', '<Shape><Appearance>%s%s%s</Appearance>%s</Shape>' % (GL.ADD_BLEND, GL.NODEPTH, sh(), QUAD))
w('dbg_m5.x3d', '<Transform scale="3 2 1"><Shape><Appearance>%s%s%s</Appearance>%s</Shape></Transform>' % (GL.ADD_BLEND, GL.NODEPTH, GL.shader_xml(GL.VS_QUAD, GL.FS_HAZE, [('uTime','SFFloat','inputOutput','0.3')]), QUAD))
w('dbg_m6.x3d', '<Transform scale="2.5 2.5 1"><Shape><Appearance>%s%s%s</Appearance>%s</Shape></Transform>' % (GL.ADD_BLEND, GL.NODEPTH, GL.shader_xml(GL.VS_QUAD, GL.FS_FLASH, [('uFlash','SFFloat','inputOutput','1')]), QUAD))
