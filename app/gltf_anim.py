"""gltf_anim.py  v2.0.0 — танцы из GLB/GLTF: чтение, перенос на скелет девушки, доля в клипе

Без браузера и без движка: только numpy. Результат — Clip: повороты костей
девушки (по 30 кадров в секунду), перемещение тела, длина доли в клипе.

Перенос — через мировые повороты: у файла танца и у модели кости могут быть
повёрнуты по-разному (FBX из Mixamo, GLB из Blender, 3ds Max Biped),
переносится отклонение каждой кости от позы покоя. Тот же скелет (одинаковые
имена костей) — повороты как есть. Разная поза покоя (T / A) — поправка
направления костей.

Журнал:
v2.0.0: перенос из dancer.js (three.js) на Python — без браузера
"""
import base64
import json
import math
import re
import struct
from pathlib import Path

import numpy as np

SAMPLE_FPS = 30


# ───────────────────────── имена костей ─────────────────────────
def _key(n):
    return re.sub(r"[^a-z0-9]", "", str(n).lower())


def _aliases():
    m = {}

    def add(canon, *names):
        for n in names:
            m[_key(n)] = canon
    add("hips", "Bip01_Pelvis", "Bip01 Pelvis", "CC_Base_Hip", "pelvis", "hip", "J_Bip_C_Hips", "root_hips")
    add("spine", "Bip01_Spine", "CC_Base_Waist", "spine_01", "abdomenLower", "abdomen1", "J_Bip_C_Spine")
    add("spine1", "Bip01_Spine1", "CC_Base_Spine01", "spine_02", "abdomenUpper", "abdomen2", "J_Bip_C_Chest")
    add("spine2", "Bip01_Spine2", "CC_Base_Spine02", "spine_03", "chestLower", "chest", "J_Bip_C_UpperChest")
    add("neck", "Bip01_Neck", "CC_Base_NeckTwist01", "neck_01", "neckLower", "J_Bip_C_Neck")
    add("head", "Bip01_Head", "CC_Base_Head", "J_Bip_C_Head")
    for s, cc, ue, dz, vr in (("left", "L", "l", "l", "L"), ("right", "R", "r", "r", "R")):
        add(s + "shoulder", f"Bip01_{cc}_Clavicle", f"CC_Base_{cc}_Clavicle", f"clavicle_{ue}", f"{dz}Collar", f"J_Bip_{vr}_Shoulder")
        add(s + "arm", f"Bip01_{cc}_UpperArm", f"CC_Base_{cc}_Upperarm", f"upperarm_{ue}", f"{dz}ShldrBend", f"{dz}Shldr", f"J_Bip_{vr}_UpperArm")
        add(s + "forearm", f"Bip01_{cc}_Forearm", f"CC_Base_{cc}_Forearm", f"lowerarm_{ue}", f"{dz}ForearmBend", f"{dz}ForeArm", f"J_Bip_{vr}_LowerArm")
        add(s + "hand", f"Bip01_{cc}_Hand", f"CC_Base_{cc}_Hand", f"hand_{ue}", f"{dz}Hand", f"J_Bip_{vr}_Hand")
        add(s + "upleg", f"Bip01_{cc}_Thigh", f"CC_Base_{cc}_Thigh", f"thigh_{ue}", f"{dz}ThighBend", f"{dz}Thigh", f"J_Bip_{vr}_UpperLeg")
        add(s + "leg", f"Bip01_{cc}_Calf", f"CC_Base_{cc}_Calf", f"calf_{ue}", f"{dz}Shin", f"J_Bip_{vr}_LowerLeg")
        add(s + "foot", f"Bip01_{cc}_Foot", f"CC_Base_{cc}_Foot", f"foot_{ue}", f"{dz}Foot", f"J_Bip_{vr}_Foot")
        add(s + "toebase", f"Bip01_{cc}_Toe0", f"CC_Base_{cc}_ToeBase", f"ball_{ue}", f"{dz}Toe", f"J_Bip_{vr}_ToeBase")
    return m


ALIAS = _aliases()


def norm_bone(n):
    """«mixamorig:LeftArm», «mixamorig1LeftArm», «Armature|LeftArm», «Bip01_L_UpperArm» → leftarm."""
    s = str(n).lower()
    s = re.sub(r"^.*\|", "", s)
    s = re.sub(r"^.*mixamorig\d*[:_]?", "", s)
    k = re.sub(r"[^a-z0-9]", "", s)
    return ALIAS.get(k, k)


# ───────────────────────── кватернионы (x, y, z, w) ─────────────────────────
def qmul(a, b):
    ax, ay, az, aw = np.moveaxis(np.asarray(a, np.float64), -1, 0)
    bx, by, bz, bw = np.moveaxis(np.asarray(b, np.float64), -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw,
                     aw * bw - ax * bx - ay * by - az * bz], -1)


def qinv(q):
    q = np.asarray(q, np.float64)
    return q * np.array([-1, -1, -1, 1.0])


def qnorm(q):
    q = np.asarray(q, np.float64)
    n = np.linalg.norm(q, axis=-1, keepdims=True)
    return q / np.where(n < 1e-12, 1, n)


def qrot(q, v):
    """Повернуть вектор(ы) v кватернионом q."""
    v = np.asarray(v, np.float64)
    qv = np.concatenate([v, np.zeros(v.shape[:-1] + (1,))], -1)
    return qmul(qmul(q, qv), qinv(q))[..., :3]


def q_from_vectors(a, b):
    """Поворот, переводящий единичный a в единичный b."""
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    r = float(np.dot(a, b)) + 1.0
    if r < 1e-8:
        x = np.array([-a[2], 0, a[0]]) if abs(a[0]) > abs(a[2]) else np.array([0, -a[2], a[1]])
        return qnorm(np.append(x, 0.0))
    c = np.cross(a, b)
    return qnorm(np.array([c[0], c[1], c[2], r]))


def q_to_mat3(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def mat3_to_q(m):
    t = m[0, 0] + m[1, 1] + m[2, 2]
    if t > 0:
        s = math.sqrt(t + 1.0) * 2
        return qnorm(np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s]))
    i = int(np.argmax([m[0, 0], m[1, 1], m[2, 2]]))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = math.sqrt(max(1e-12, 1.0 + m[i, i] - m[j, j] - m[k, k])) * 2
    q = np.zeros(4)
    q[i] = 0.25 * s
    q[j] = (m[j, i] + m[i, j]) / s
    q[k] = (m[k, i] + m[i, k]) / s
    q[3] = (m[k, j] - m[j, k]) / s
    return qnorm(q)


def trs_mat(t, r, s):
    m = np.eye(4)
    m[:3, :3] = q_to_mat3(r) * np.asarray(s)[None, :]
    m[:3, 3] = t
    return m


# ───────────────────────── чтение GLB / GLTF ─────────────────────────
_COMP = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


class Gltf:
    def __init__(self, path):
        self.path = Path(path)
        raw = self.path.read_bytes()
        self.bins = []
        if raw[:4] == b"glTF":
            off = 12
            self.json = None
            glb_bin = b""
            while off + 8 <= len(raw):
                ln, typ = struct.unpack_from("<II", raw, off)
                chunk = raw[off + 8:off + 8 + ln]
                if typ == 0x4E4F534A:
                    self.json = json.loads(chunk.decode("utf-8"))
                elif typ == 0x004E4942:
                    glb_bin = chunk
                off += 8 + ln
            self._glb_bin = glb_bin
        else:
            self.json = json.loads(raw.decode("utf-8"))
            self._glb_bin = b""
        self._buffers = {}

    def _buffer(self, i):
        if i in self._buffers:
            return self._buffers[i]
        b = self.json["buffers"][i]
        uri = b.get("uri")
        if uri is None:
            data = self._glb_bin
        elif uri.startswith("data:"):
            data = base64.b64decode(uri.split(",", 1)[1])
        else:
            data = (self.path.parent / uri).read_bytes()
        self._buffers[i] = data
        return data

    def accessor(self, i):
        a = self.json["accessors"][i]
        n = _NCOMP[a["type"]]
        dt = np.dtype(_COMP[a["componentType"]])
        cnt = a["count"]
        if "bufferView" not in a:
            return np.zeros((cnt, n), np.float32)
        bv = self.json["bufferViews"][a["bufferView"]]
        data = self._buffer(bv["buffer"])
        start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        stride = bv.get("byteStride", 0) or dt.itemsize * n
        if stride == dt.itemsize * n:
            arr = np.frombuffer(data, dt, cnt * n, start).reshape(cnt, n)
        else:
            arr = np.stack([np.frombuffer(data, dt, n, start + k * stride) for k in range(cnt)])
        arr = arr.astype(np.float64)
        if a.get("normalized"):
            arr = arr / float(np.iinfo(dt).max)
        return arr


# ───────────────────────── скелет ─────────────────────────
class Rig:
    """Узлы сцены в порядке обхода (родитель раньше детей), поза покоя,
    кости по нормированным именам, бёдра и «носитель перемещения»."""

    def __init__(self, g):
        js = g.json
        nodes = js.get("nodes", [])
        sc = js.get("scenes", [{}])[js.get("scene", 0)] if js.get("scenes") else {"nodes": list(range(len(nodes)))}
        self.order, self.parent = [], {}
        stack = [(r, -1) for r in reversed(sc.get("nodes", []))]
        while stack:
            i, p = stack.pop()
            self.order.append(i)
            self.parent[i] = p
            for c in reversed(nodes[i].get("children", [])):
                stack.append((c, i))
        self.name, self.T, self.R, self.S = {}, {}, {}, {}
        for i in self.order:
            nd = nodes[i]
            self.name[i] = nd.get("name", "")
            if "matrix" in nd:
                m = np.array(nd["matrix"], np.float64).reshape(4, 4).T
                t = m[:3, 3].copy()
                s = np.linalg.norm(m[:3, :3], axis=0)
                r = mat3_to_q(m[:3, :3] / np.where(s < 1e-12, 1, s)[None, :])
            else:
                t = np.array(nd.get("translation", [0, 0, 0]), np.float64)
                r = qnorm(np.array(nd.get("rotation", [0, 0, 0, 1]), np.float64))
                s = np.array(nd.get("scale", [1, 1, 1]), np.float64)
            self.T[i], self.R[i], self.S[i] = t, r, s
        joints = set()
        for sk in js.get("skins", []):
            joints.update(sk.get("joints", []))
        self.by_name, hips = {}, None
        for i in self.order:
            nm = self.name[i]
            if not nm:
                continue
            n = norm_bone(nm)
            if n not in self.by_name or (i in joints and self.by_name[n] not in joints):
                self.by_name[n] = i
            if n == "hips" and (hips is None or (i in joints and hips not in joints)):
                hips = i
        self.hips = hips
        p = self.parent.get(hips, -1) if hips is not None else -1
        self.mover = p if p >= 0 and norm_bone(self.name[p]) == "bip01" else hips
        self.children = {i: [] for i in self.order}
        for i in self.order:
            if self.parent[i] >= 0:
                self.children[self.parent[i]].append(i)
        self._wm = None

    def world_mats(self):
        if self._wm is None:
            wm = {}
            for i in self.order:
                m = trs_mat(self.T[i], self.R[i], self.S[i])
                p = self.parent[i]
                wm[i] = wm[p] @ m if p >= 0 else m
            self._wm = wm
        return self._wm

    def world_with(self, rot, pos):
        """Мировые матрицы с подменой: rot {узел: xyzw}, pos {узел: xyz}."""
        wm = {}
        for i in self.order:
            m = trs_mat(pos.get(i, self.T[i]), rot.get(i, self.R[i]), self.S[i])
            p = self.parent[i]
            wm[i] = wm[p] @ m if p >= 0 else m
        return wm

    def parent_mat(self, i):
        if i is None or self.parent.get(i, -1) < 0:
            return np.eye(4)
        return self.world_mats()[self.parent[i]]

    def world_q(self, local):
        """local: {узел: (N,4) или (4,)} → мировые повороты (относительно корня сцены)."""
        W = {}
        for i in self.order:
            q = local[i] if i in local else self.R[i]
            p = self.parent[i]
            W[i] = qmul(W[p], q) if p >= 0 else np.asarray(q, np.float64)
        return W


# ───────────────────────── отрезок анимации ─────────────────────────
class Track:
    def __init__(self, times, values, interp):
        self.t = np.asarray(times, np.float64).ravel()
        self.v = np.asarray(values, np.float64)
        if interp == "CUBICSPLINE":                  # тройки (вход, значение, выход) — берём значение
            self.v = self.v.reshape(len(self.t), 3, -1)[:, 1, :]
        self.step = interp == "STEP"

    def sample(self, ts):
        t, v = self.t, self.v
        if len(t) == 1:
            return np.repeat(v[:1], len(ts), 0)
        ts = np.clip(ts, t[0], t[-1])
        i = np.clip(np.searchsorted(t, ts, side="right") - 1, 0, len(t) - 2)
        if self.step:
            return v[i]
        f = ((ts - t[i]) / np.maximum(t[i + 1] - t[i], 1e-9))[:, None]
        a, b = v[i], v[i + 1]
        if v.shape[1] == 4:                          # повороты — по короткой дуге
            b = np.where((np.sum(a * b, 1) < 0)[:, None], -b, b)
            return qnorm(a * (1 - f) + b * f)
        return a * (1 - f) + b * f


def animations(g):
    """Список (имя, длительность, {узел: {'rotation'|'translation': Track}})."""
    out = []
    for k, an in enumerate(g.json.get("animations", [])):
        ch = {}
        dur = 0.0
        for c in an.get("channels", []):
            tgt = c.get("target", {})
            node, path = tgt.get("node"), tgt.get("path")
            if node is None or path not in ("rotation", "translation"):
                continue
            s = an["samplers"][c["sampler"]]
            times = g.accessor(s["input"])[:, 0]
            vals = g.accessor(s["output"])
            tr = Track(times, vals, s.get("interpolation", "LINEAR"))
            ch.setdefault(node, {})[path] = tr
            dur = max(dur, float(times[-1]) if len(times) else 0.0)
        if ch:
            out.append((an.get("name") or f"anim{k}", dur, ch))
    return out


class Clip:
    """Танец, перенесённый на девушку: повороты костей по кадрам (SAMPLE_FPS)."""

    def __init__(self, name, duration, times, rot, mover, mover_pos, hips_y, same):
        self.name, self.duration, self.times = name, duration, times
        self.rot = rot                    # {имя кости девушки: (N,4) xyzw}
        self.mover, self.mover_pos = mover, mover_pos
        self.hips_y, self.same = hips_y, same
        self.period, self.t0, self.auto = analyze(hips_y, duration)

    @property
    def tracks(self):
        return len(self.rot) + (1 if self.mover_pos is not None else 0)

    def frame(self, t):
        """Повороты и позиция носителя в момент t (секунды клипа, по кругу)."""
        n = len(self.times)
        f = (t % max(self.duration, 1e-6)) * SAMPLE_FPS
        i0 = int(f) % n
        i1 = min(i0 + 1, n - 1)
        k = f - int(f)
        rot = {}
        for nm, arr in self.rot.items():
            q = arr[i0] * (1 - k) + arr[i1] * k
            rot[nm] = q / max(1e-9, math.sqrt(float(q @ q)))
        pos = None
        if self.mover_pos is not None:
            pos = self.mover_pos[i0] * (1 - k) + self.mover_pos[i1] * k
        return rot, pos


def _rest_align(S, T, pairs):
    """Поворот, который направляет кость модели так же, как кость танца в покое."""
    Ps = {i: m[:3, 3] for i, m in S.world_mats().items()}
    Pt = {i: m[:3, 3] for i, m in T.world_mats().items()}

    def child_of(o):
        q = list(T.children[o])
        while q:
            c = q.pop(0)
            if c in pairs:
                return c
            q.extend(T.children[c])
        return None

    res = {}
    for o in T.order:
        if o not in pairs:
            continue
        a = None
        c = child_of(o)
        if c is not None and norm_bone(T.name[o]) != "hips":
            dT = Pt[c] - Pt[o]
            dS = Ps[pairs[c]] - Ps[pairs[o]]
            if dT @ dT > 1e-10 and dS @ dS > 1e-10:
                a = q_from_vectors(dT / np.linalg.norm(dT), dS / np.linalg.norm(dS))
        if a is None:
            p = T.parent[o]
            while p >= 0 and p not in res:
                p = T.parent[p]
            a = res[p].copy() if p >= 0 else np.array([0, 0, 0, 1.0])
        res[o] = a
    return res


def retarget(src_g, anim, tgt_g, inplace=True, src_rig=None, tgt_rig=None):
    """Перенос анимации anim (из animations(src_g)) на скелет файла tgt_g → Clip."""
    name, duration, chans = anim
    S = src_rig or Rig(src_g)
    T = tgt_rig or Rig(tgt_g)
    q_tr, pos_tr = {}, None
    for node, paths in chans.items():
        if node not in S.parent:
            continue
        o = S.by_name.get(norm_bone(S.name[node]))
        if o is None:
            continue
        if "rotation" in paths:
            q_tr[o] = paths["rotation"]
        if "translation" in paths and o == S.mover:
            pos_tr = paths["translation"]
    pairs = {}
    for o in T.order:
        nm = T.name[o]
        if not nm or T.by_name.get(norm_bone(nm)) != o:
            continue
        s = S.by_name.get(norm_bone(nm))
        if s is not None and s in q_tr:
            pairs[o] = s
    if not pairs:
        return None
    same = all(T.name[o] == S.name[s] for o, s in pairs.items())
    n = max(2, int(math.ceil(duration * SAMPLE_FPS)) + 1)
    times = np.minimum(np.arange(n) / SAMPLE_FPS, duration)
    local_s = {o: tr.sample(times) for o, tr in q_tr.items()}
    rot = {}
    if same:
        for o, s in pairs.items():
            rot[T.name[o]] = qnorm(local_s[s])
    else:
        align = _rest_align(S, T, pairs)
        Ws0 = S.world_q({})
        Wt0 = T.world_q({})
        Ws = S.world_q(local_s)
        Wt = {}
        for o in T.order:
            p = T.parent[o]
            pw = Wt[p] if p >= 0 else np.array([0, 0, 0, 1.0])
            if o in pairs:
                s = pairs[o]
                w = qmul(qmul(qmul(Ws[s], qinv(Ws0[s])), align[o]), Wt0[o])
                Wt[o] = w
                rot[T.name[o]] = qnorm(qmul(qinv(pw), w))
            else:
                Wt[o] = qmul(pw, T.R[o])
    for k, arr in rot.items():                     # соседние кадры — по короткой дуге
        arr = np.array(np.broadcast_to(arr, (n, 4)))
        d = np.sum(arr[1:] * arr[:-1], 1)
        flip = np.cumprod(np.where(d < 0, -1.0, 1.0))
        arr[1:] *= flip[:, None]
        rot[k] = arr
    # перемещение тела
    mover_pos, hips_y = None, None
    if pos_tr is not None and S.mover is not None and T.mover is not None:
        Mps, Mpt = S.parent_mat(S.mover), T.parent_mat(T.mover)
        Mpti = np.linalg.inv(Mpt)
        rest_s = (Mps @ np.append(S.T[S.mover], 1))[:3]
        rest_t = (Mpt @ np.append(T.T[T.mover], 1))[:3]
        hs = S.world_mats()[S.hips][1, 3] if S.hips is not None else 0
        ht = T.world_mats()[T.hips][1, 3] if T.hips is not None else 0
        ratio = ht / hs if abs(hs) > 1e-6 and abs(ht) > 1e-6 else 1.0
        p = pos_tr.sample(times)
        pw = (np.c_[p, np.ones(n)] @ Mps.T)[:, :3]
        if np.linalg.norm(pw[0]) >= 0.3 * max(np.linalg.norm(rest_s), abs(hs)):   # не аддитивный
            hips_y = pw[:, 1].copy()
            v = pw.copy()
            v[:, 1] = rest_t[1] + (pw[:, 1] - rest_s[1]) * ratio
            if inplace:
                v[:, 0], v[:, 2] = rest_t[0], rest_t[2]
            else:
                v[:, 0] = rest_t[0] + (pw[:, 0] - pw[0, 0]) * ratio
                v[:, 2] = rest_t[2] + (pw[:, 2] - pw[0, 2]) * ratio
            mover_pos = (np.c_[v, np.ones(n)] @ Mpti.T)[:, :3]
    return Clip(name, duration, times, rot, T.name[T.mover] if mover_pos is not None else None,
                mover_pos, hips_y, same)


def analyze(y0, duration):
    """Доля в клипе: период «пружинки» бёдер (автокорреляция высоты бёдер)."""
    res = (0.5, 0.0, False)
    if y0 is None or duration < 1.0:
        return res
    fps = SAMPLE_FPS
    y = np.asarray(y0, np.float64) - np.mean(y0)
    n = len(y)
    e0 = float(y @ y)
    if e0 < 1e-12:
        return res

    def ac(lag):
        return float(y[:n - lag] @ y[lag:]) / e0 * (n / (n - lag))
    lo, hi = round(0.25 * fps), min(round(1.6 * fps), n // 2)
    best, best_lag = 0.0, 0
    for l in range(lo, hi + 1):
        a = ac(l)
        if a > best and ac(l - 1) <= a and ac(l + 1) <= a:
            best, best_lag = a, l
    if not best_lag or best < 0.15:
        return res
    lag = float(best_lag)
    a0, a1, a2 = ac(best_lag - 1), ac(best_lag), ac(best_lag + 1)
    den = a0 - 2 * a1 + a2
    if abs(den) > 1e-12:
        lag += 0.5 * (a0 - a2) / den
    period = lag / fps
    while period > 0.8:
        period /= 2
    while period < 0.35:
        period *= 2
    m = min(n, round(period * fps))
    t0 = float(np.argmin(y[:m])) / fps
    return period, t0, True


def longest(anims):
    return max(anims, key=lambda a: a[1]) if anims else None
