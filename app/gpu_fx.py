"""gpu_fx.py  v2.3.0 — шейдеры для режима «видеокарта»

SKIN — деформация модели по костям в вершинном шейдере (вершины не
пересчитываются процессором) + свет; NEON — неон в три прохода: контур
(Собель по яркости и силуэту) → размытие (ореол) → сборка. GLSL 1.20 —
работает на любой видеокарте с OpenGL 2.1.

Журнал:
v2.3.0: первая версия — перенос из numpy (gltf_mesh.skin, neon.apply)
"""
MAX_JOINTS = 128

SKIN_VERT = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
uniform mat4 joints[%d];
attribute vec4 p3d_Vertex;
attribute vec3 p3d_Normal;
attribute vec2 p3d_MultiTexCoord0;
attribute vec4 joint;
attribute vec4 weight;
varying vec2 uv;
varying vec3 nw;
void main() {
  mat4 m = joints[int(joint.x)] * weight.x + joints[int(joint.y)] * weight.y
         + joints[int(joint.z)] * weight.z + joints[int(joint.w)] * weight.w;
  vec4 p = m * vec4(p3d_Vertex.xyz, 1.0);
  gl_Position = p3d_ModelViewProjectionMatrix * p;
  nw = mat3(p3d_ModelMatrix) * (mat3(m) * p3d_Normal);
  uv = p3d_MultiTexCoord0;
}
""" % MAX_JOINTS

SKIN_FRAG = """#version 120
uniform sampler2D p3d_Texture0;
uniform vec4 base;
uniform float cutoff;
uniform float blend;
uniform vec3 amb;
uniform vec3 k_dir, k_col, f_dir, f_col, r_dir, r_col;
varying vec2 uv;
varying vec3 nw;
void main() {
  vec4 c = texture2D(p3d_Texture0, uv) * base;
  if (c.a < cutoff) discard;
  vec3 n = normalize(nw);
  if (!gl_FrontFacing) n = -n;
  vec3 l = amb + k_col * max(dot(n, -k_dir), 0.0) + f_col * max(dot(n, -f_dir), 0.0)
         + r_col * max(dot(n, -r_dir), 0.0);
  float a = blend > 0.5 ? c.a : 1.0;
  gl_FragColor = vec4(c.rgb * l * a, a);
}
"""

QUAD_VERT = """#version 120
uniform mat4 p3d_ModelViewProjectionMatrix;
attribute vec4 p3d_Vertex;
attribute vec2 p3d_MultiTexCoord0;
varying vec2 uv;
void main() { gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex; uv = p3d_MultiTexCoord0; }
"""

EDGE_FRAG = """#version 120
uniform sampler2D tColor;
uniform vec2 texel;
uniform float width, t, cycle;
uniform vec3 pal0, pal1, pal2, pal3;
varying vec2 uv;
float L(vec2 o) { vec4 c = texture2D(tColor, uv + o * texel * width); return sqrt(dot(c.rgb, vec3(0.299, 0.587, 0.114))); }
float A(vec2 o) { return texture2D(tColor, uv + o * texel * width).a; }
vec3 palette(float x) {
  x = fract(x) * 4.0; float f = smoothstep(0.0, 1.0, fract(x));
  if (x < 1.0) return mix(pal0, pal1, f);
  if (x < 2.0) return mix(pal1, pal2, f);
  if (x < 3.0) return mix(pal2, pal3, f);
  return mix(pal3, pal0, f);
}
void main() {
  float gx = -L(vec2(-1,-1)) - 2.0*L(vec2(-1,0)) - L(vec2(-1,1)) + L(vec2(1,-1)) + 2.0*L(vec2(1,0)) + L(vec2(1,1));
  float gy = -L(vec2(-1,-1)) - 2.0*L(vec2(0,-1)) - L(vec2(1,-1)) + L(vec2(-1,1)) + 2.0*L(vec2(0,1)) + L(vec2(1,1));
  float ax = -A(vec2(-1,-1)) - 2.0*A(vec2(-1,0)) - A(vec2(-1,1)) + A(vec2(1,-1)) + 2.0*A(vec2(1,0)) + A(vec2(1,1));
  float ay = -A(vec2(-1,-1)) - 2.0*A(vec2(0,-1)) - A(vec2(1,-1)) + A(vec2(-1,1)) + 2.0*A(vec2(0,1)) + A(vec2(1,1));
  float inner = smoothstep(0.14, 0.55, length(vec2(gx, gy))) * 0.75;
  float sil = clamp(length(vec2(ax, ay)) * 0.9, 0.0, 1.0);
  float e = max(sil, inner);
  vec3 col = palette((1.0 - uv.y) * 0.62 + cycle);
  gl_FragColor = vec4(col * e, e);
}
"""

BLUR_FRAG = """#version 120
uniform sampler2D tSrc;
uniform vec2 dir;
varying vec2 uv;
void main() {
  vec4 s = texture2D(tSrc, uv) * 0.2270270270;
  s += (texture2D(tSrc, uv + dir * 1.3846153846) + texture2D(tSrc, uv - dir * 1.3846153846)) * 0.3162162162;
  s += (texture2D(tSrc, uv + dir * 3.2307692308) + texture2D(tSrc, uv - dir * 3.2307692308)) * 0.0702702703;
  gl_FragColor = s;
}
"""

COMP_FRAG = """#version 120
uniform sampler2D tColor, tEdge, tGlow, tGlow2;
uniform float glow, pulse;
uniform vec3 fill;
varying vec2 uv;
void main() {
  vec4 E = texture2D(tEdge, uv);
  vec4 G = texture2D(tGlow2, uv) * 0.7 + texture2D(tGlow, uv) * 0.5;
  float cov = texture2D(tColor, uv).a;
  float k = 1.0 + 0.45 * pulse;
  vec3 rgb = E.rgb * 1.25 * k + vec3(E.a * 0.10 * k) + G.rgb * glow * 1.5 * k
           + fill * cov * (0.18 + 0.25 * pulse);
  float a = clamp(max(E.a * k, G.a * glow * 1.2 * k) + cov * 0.15, 0.0, 1.0);
  rgb = min(rgb, vec3(a));
  gl_FragColor = vec4(rgb, a);
}
"""
