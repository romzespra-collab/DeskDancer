"""gltf_mesh.py  v2.0.0 — модель из GLB/GLTF для Panda3D: сетка, текстуры, скиннинг на numpy

Свой загрузчик вместо panda3d-gltf: тот на части моделей (Rocketbox) теряет
кости. Здесь всё в осях glTF: кадр — мировые матрицы узлов (gltf_anim.Rig),
вершины деформируются по костям (линейный скиннинг) и записываются в
готовую геометрию Panda3D. Поворот в оси сцены — на родительском узле.

Журнал:
v2.0.0: первая версия
"""
import numpy as np

from . import gltf_anim as ga


def _texture(g, tex_index, srgb_ok, srgb, cache):
    from panda3d.core import PNMImage, SamplerState, StringStream, Texture
    key = (tex_index, srgb)
    if key in cache:
        return cache[key]
    js = g.json
    tx = js["textures"][tex_index]
    src = tx.get("source")
    if src is None:
        return None
    im = js["images"][src]
    if "bufferView" in im:
        bv = js["bufferViews"][im["bufferView"]]
        data = g._buffer(bv["buffer"])[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
        name = "x.png" if "png" in im.get("mimeType", "png") else "x.jpg"
    else:
        uri = im.get("uri", "")
        if uri.startswith("data:"):
            import base64
            data = base64.b64decode(uri.split(",", 1)[1])
            name = "x.png" if "png" in uri[:30] else "x.jpg"
        else:
            p = g.path.parent / uri
            data = p.read_bytes()
            name = "x" + p.suffix.lower()
    img = PNMImage()
    if not img.read(StringStream(bytes(data)), name):
        return None
    t = Texture(f"tex{tex_index}")
    t.load(img)
    if srgb and srgb_ok:
        t.setFormat(Texture.F_srgb_alpha if img.hasAlpha() else Texture.F_srgb)
    t.setMinfilter(SamplerState.FT_linear_mipmap_linear)
    t.setMagfilter(SamplerState.FT_linear)
    cache[key] = t
    return t


class Prim:
    """Один примитив (кусок сетки с одним материалом)."""

    def __init__(self, pos, nrm, uv, idx, joints, weights, node, skin, mat):
        self.pos, self.nrm, self.uv, self.idx = pos, nrm, uv, idx
        self.joints, self.weights = joints, weights
        self.node, self.skin, self.mat = node, skin, mat
        self.vdata = None


class Model:
    """Модель glTF: Prim'ы, скелет (Rig), узел Panda3D с геометрией."""

    def __init__(self, path):
        self.g = ga.Gltf(path)
        self.rig = ga.Rig(self.g)
        js = self.g.json
        g = self.g
        self.prims = []
        self.skins = []
        for sk in js.get("skins", []):
            J = list(sk["joints"])
            if "inverseBindMatrices" in sk:
                ib = g.accessor(sk["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
            else:
                ib = np.repeat(np.eye(4)[None], len(J), 0)
            self.skins.append((np.array(J), ib))
        for i in self.rig.order:
            nd = js["nodes"][i]
            if "mesh" not in nd:
                continue
            for pr in js["meshes"][nd["mesh"]].get("primitives", []):
                if pr.get("mode", 4) != 4:
                    continue
                at = pr["attributes"]
                if "POSITION" not in at:
                    continue
                pos = g.accessor(at["POSITION"]).astype(np.float32)
                n = len(pos)
                nrm = g.accessor(at["NORMAL"]).astype(np.float32) if "NORMAL" in at else None
                uv = g.accessor(at["TEXCOORD_0"]).astype(np.float32) if "TEXCOORD_0" in at else np.zeros((n, 2), np.float32)
                if "indices" in pr:
                    idx = g.accessor(pr["indices"]).astype(np.uint32).ravel()
                else:
                    idx = np.arange(n, dtype=np.uint32)
                joints = weights = None
                skin = nd.get("skin")
                if skin is not None and "JOINTS_0" in at and "WEIGHTS_0" in at:
                    joints = g.accessor(at["JOINTS_0"]).astype(np.int64)
                    weights = g.accessor(at["WEIGHTS_0"]).astype(np.float32)
                    s = weights.sum(1, keepdims=True)
                    weights = weights / np.where(s < 1e-8, 1, s)
                mat = js.get("materials", [{}])[pr["material"]] if "material" in pr else {}
                # только свои вершины (экспорт three.js даёт каждой части весь буфер модели)
                used, inv = np.unique(idx, return_inverse=True)
                if len(used) < n:
                    pos, uv = pos[used], uv[used]
                    nrm = nrm[used] if nrm is not None else None
                    if joints is not None:
                        joints, weights = joints[used], weights[used]
                    idx = inv.astype(np.uint32)
                self.prims.append(Prim(pos, nrm, uv, idx, joints, weights, i, skin, mat))
        self.node = None

    # ---------- Panda3D ----------
    def build(self, srgb_ok, tex_cache=None):
        """Узел Panda3D с геометрией (оси glTF). Вызывать в потоке сцены."""
        from panda3d.core import (AlphaTestAttrib, CullFaceAttrib, Geom, GeomNode,
                                  GeomTriangles, GeomVertexData, GeomVertexFormat, NodePath,
                                  RenderAttrib, TransparencyAttrib)
        cache = {} if tex_cache is None else tex_cache
        root = NodePath("model")
        fmt = GeomVertexFormat.getV3n3t2()
        for k, p in enumerate(self.prims):
            n = len(p.pos)
            vd = GeomVertexData(f"p{k}", fmt, Geom.UH_dynamic)
            vd.uncleanSetNumRows(n)
            arr = np.zeros((n, 8), np.float32)
            arr[:, 0:3] = p.pos
            arr[:, 3:6] = p.nrm if p.nrm is not None else (0, 0, 1)
            arr[:, 6] = p.uv[:, 0]
            arr[:, 7] = 1.0 - p.uv[:, 1]                    # glTF: v сверху вниз
            memoryview(vd.modifyArray(0)).cast("B")[:] = arr.tobytes()
            tri = GeomTriangles(Geom.UH_static)
            tri.setIndexType(Geom.NT_uint32)
            ia = tri.modifyVertices()
            ia.uncleanSetNumRows(len(p.idx))
            memoryview(ia).cast("B")[:] = p.idx.astype(np.uint32).tobytes()
            geom = Geom(vd)
            geom.addPrimitive(tri)
            gn = GeomNode(f"prim{k}")
            gn.addGeom(geom)
            np_ = root.attachNewNode(gn)
            m = p.mat
            pbr = m.get("pbrMetallicRoughness", {})
            col = pbr.get("baseColorFactor", [1, 1, 1, 1])
            np_.setColor(*col)
            if "baseColorTexture" in pbr:
                t = _texture(self.g, pbr["baseColorTexture"]["index"], srgb_ok, True, cache)
                if t is not None:
                    np_.setTexture(t)
            mode = m.get("alphaMode", "OPAQUE")
            if mode == "MASK":
                np_.setAttrib(AlphaTestAttrib.make(RenderAttrib.M_greater_equal, m.get("alphaCutoff", 0.5)))
            elif mode == "BLEND":
                np_.setTransparency(TransparencyAttrib.M_alpha)
                np_.setDepthWrite(False)
                np_.setBin("transparent", 10)
            if m.get("doubleSided"):
                np_.setAttrib(CullFaceAttrib.make(CullFaceAttrib.M_cull_none))
                np_.setTwoSided(True)
            p.vdata = vd
            p.np = np_
        self.node = root
        return root

    def skin(self, world):
        """Деформировать сетку по мировым матрицам узлов {узел: 4×4} (оси glTF)."""
        for p in self.prims:
            if p.vdata is None:
                continue
            if p.joints is not None:
                J, ib = self.skins[p.skin]
                jm = np.stack([world[j] for j in J]) @ ib              # (K,4,4)
                jm = jm[:, :3, :].astype(np.float32)                   # (K,3,4)
                M = jm[p.joints[:, 0]] * p.weights[:, 0, None, None]
                for c in range(1, p.joints.shape[1]):
                    w = p.weights[:, c]
                    if w.any():
                        M += jm[p.joints[:, c]] * w[:, None, None]
            else:
                M = np.broadcast_to(world[p.node][:3, :].astype(np.float32), (len(p.pos), 3, 4))
            pos = (M[:, :, :3] @ p.pos[:, :, None])[:, :, 0] + M[:, :, 3]
            arr = np.frombuffer(memoryview(p.vdata.modifyArray(0)).cast("B"), np.float32).reshape(-1, 8)
            arr[:, 0:3] = pos
            if p.nrm is not None:
                nn = (M[:, :, :3] @ p.nrm[:, :, None])[:, :, 0]
                nn /= np.maximum(np.sqrt((nn * nn).sum(1, keepdims=True)), 1e-8)
                arr[:, 3:6] = nn

    def rest_positions(self):
        """Вершины в позе покоя (для рамки и ориентации)."""
        world = self.rig.world_mats()
        out = []
        for p in self.prims:
            if p.joints is not None:
                J, ib = self.skins[p.skin]
                jm = (np.stack([world[j] for j in J]) @ ib)[:, :3, :]
                M = np.einsum("nk,nkab->nab", p.weights, jm[p.joints])
            else:
                M = np.broadcast_to(world[p.node][:3, :], (len(p.pos), 3, 4))
            out.append(np.einsum("nab,nb->na", M[:, :, :3], p.pos) + M[:, :, 3])
        return np.concatenate(out) if out else np.zeros((0, 3))
