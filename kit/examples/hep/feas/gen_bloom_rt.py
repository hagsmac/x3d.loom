#!/usr/bin/env python3
"""IN-SCENE bloom attempt: the event scene is rendered by X_ITE's RenderedTexture node into an offscreen texture, and a full-screen quad
with a ComposedShader samples it (scene + bright-pass blur) -> real post-process bloom inside plain X3D (no page code). stdlib only.
   python3 gen_bloom_rt.py IN.x3d OUT.x3d [--w 960 --h 540 --gain 1.4 --thr 0.35 --sigma 14]"""
import re, sys
sys.dont_write_bytecode = True

VS = """#version 300 es
precision highp float;
in vec4 x3d_Vertex;
out vec2 vUV;
void main() { vUV = x3d_Vertex.xy * 0.5 + 0.5; gl_Position = vec4(x3d_Vertex.xy, 0.0, 1.0); }
"""
FS = """#version 300 es
precision highp float;
uniform sampler2D uTex;
uniform vec2 uPx;
uniform float uGain;
uniform float uThr;
uniform float uSigma;
in vec2 vUV;
out vec4 fragColor;
void main() {
  vec3 c = texture(uTex, vUV).rgb;
  vec3 b = vec3(0.0);
  float ws = 0.0;
  for (int r = 1; r <= 6; r++) {
    float rad = uSigma * float(r) / 3.0;
    float w = exp(-float(r * r) / 4.5);
    for (int k = 0; k < 12; k++) {
      float a = 6.2831853 * (float(k) + 0.5 * float(r)) / 12.0;
      vec3 s = texture(uTex, vUV + vec2(cos(a), sin(a)) * rad * uPx).rgb;
      b += max(s - vec3(uThr), vec3(0.0)) * w;
      ws += w;
    }
  }
  b /= ws;
  vec3 col = c + b * uGain * 12.0;
  col = 1.0 - exp(-col * 1.25);
  fragColor = vec4(col, 1.0);
}
"""

def build(src, w=960, h=540, gain=1.4, thr=0.35, sigma=14.0):
    body = re.search(r'<Scene>(.*)</Scene>', src, re.S).group(1)
    head = re.search(r'<head>(.*?)</head>', src, re.S).group(1)
    head = head.replace('<component name="X_ITE" level="1"/>', '<component name="X_ITE" level="1"/>\n    <component name="Texturing" level="4"/>')
    fld = lambda n, t, v: '<field name="%s" type="%s" accessType="initializeOnly" value="%s"/>' % (n, t, v)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<X3D profile="Immersive" version="4.1">\n  <head>%s</head>\n  <Scene>\n'
            '    <NavigationInfo type=\'"NONE"\' headlight="false"/>\n    <Viewpoint position="0 0 5" description="screen"/>\n'
            '    <Shape><Appearance><ComposedShader language="GLSL">\n'
            '      <field name="uTex" type="SFNode" accessType="inputOutput"><RenderedTexture DEF="RT" width="%d" height="%d" singleFrame="false" updateInterval="0" repeatS="false" repeatT="false">%s</RenderedTexture></field>\n'
            '      %s %s %s %s\n'
            '      <ShaderPart type="VERTEX"><![CDATA[data:x-shader/x-vertex,%s]]></ShaderPart>\n'
            '      <ShaderPart type="FRAGMENT"><![CDATA[data:x-shader/x-fragment,%s]]></ShaderPart>\n'
            '    </ComposedShader></Appearance>\n'
            '    <IndexedFaceSet coordIndex="0 1 2 3 -1"><Coordinate point="-1 -1 0, 1 -1 0, 1 1 0, -1 1 0"/></IndexedFaceSet></Shape>\n  </Scene>\n</X3D>\n'
            % (head, w, h, body, fld('uPx', 'SFVec2f', '%g %g' % (1.0 / w, 1.0 / h)), fld('uGain', 'SFFloat', gain), fld('uThr', 'SFFloat', thr), fld('uSigma', 'SFFloat', sigma), VS, FS))

if __name__ == '__main__':
    a = sys.argv[1:]
    opt = {a[i][2:]: float(a[i + 1]) for i in range(2, len(a) - 1, 2)}
    open(a[1], 'w').write(build(open(a[0]).read(), int(opt.get('w', 960)), int(opt.get('h', 540)), opt.get('gain', 1.4), opt.get('thr', 0.35), opt.get('sigma', 14.0)))
