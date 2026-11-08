"""engine3d.py  v2.0.0 — 3D-сцена DeskDancer без браузера (Panda3D)

Panda3D рисует девушек в невидимый буфер, готовый кадр (с прозрачностью)
уходит в окно Qt — как скины PionerFM. Работает в своём потоке.

Графика — по порядку, пока не заработает: видеокарта OpenGL, DirectX 9,
программная (процессор, без видеокарты — работает на любом ПК).

Журнал:
v2.0.0: первая версия — вместо three.js в браузере
"""
import math
import queue
import threading
import time
from pathlib import Path

import numpy as np

from . import gltf_anim as ga

HEIGHT = 1.7                        # рост девушки на сцене, м
COLORS_FIRE = ((1.0, 0.86, 0.55), (1.0, 0.45, 0.12), (0.95, 0.2, 0.55), (0.55, 0.25, 1.0))
PIPES = {"auto": ("pandagl", "pandadx9", "p3tinydisplay"),
         "gpu": ("pandagl", "pandadx9"),
         "soft": ("p3tinydisplay",)}
PIPE_NAMES = {"pandagl": "видеокарта (OpenGL)", "pandadx9": "видеокарта (DirectX 9)",
              "p3tinydisplay": "программная (процессор)"}

# glTF (Y вверх) → оси суставов Panda3D: (x, y, z) → (x, −z, y)
_C = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1.0]])
_Ci = _C.T


def _frac(x):
    return x - math.floor(x)


def _wrap(x):
    return _frac(x + 0.5) - 0.5


class MusicClock:
    """Свои часы долей: плавно подстраиваются под BPM и фазу из анализа звука."""

    def __init__(self):
        self.bpm, self.beat, self.energy = 120.0, 0.0, 0.0
        self.active, self.synced, self.last = False, False, 0.0

    def feed(self, st):
        self.last = time.monotonic()
        self.energy += (float(st.get("energy", 0)) - self.energy) * 0.3
        bpm = float(st.get("bpm") or 0)
        if not st.get("active") or bpm <= 0:
            self.active = False
            return
        if abs(bpm / self.bpm - 1) > 0.06:
            self.bpm = bpm
        else:
            self.bpm += (bpm - self.bpm) * 0.2
        err = _wrap(float(st.get("phase", 0)) - _frac(self.beat))
        if not self.synced or abs(err) > 0.3:
            self.beat += err
            self.synced = True
        else:
            self.beat += err * 0.15
        self.active = True

    def step(self, dt):
        if time.monotonic() - self.last > 1.5:
            self.active = False
        if self.active:
            self.beat += dt * self.bpm / 60.0


class Engine(threading.Thread):
    """Поток со сценой. Снаружи — только потокобезопасные вызовы:
    set_scene(dict), set_size(w, h), set_beat(st), set_paused(bool), stop();
    кадр — frame() → (bytes BGRA premultiplied, w, h, номер) или None."""

    def __init__(self, app_root, gpu="auto", log=None, fps=30):
        super().__init__(daemon=True, name="scene3d")
        self.root = Path(app_root)
        self.gpu = gpu if gpu in PIPES else "auto"
        self.log = log or (lambda *a: None)
        self.fps = fps
        self.cmds = queue.Queue()
        self._frame = None
        self._lock = threading.Lock()
        self._serial = 0
        self._stop = threading.Event()
        self.paused = False
        self.size = (480, 600)
        self.beat_state = None
        self.status = {"ready": False, "pipe": "", "renderer": "", "fps": 0, "dancers": [], "error": ""}
        self.music = MusicClock()

    # ---------- снаружи ----------
    def set_scene(self, scene):
        self.cmds.put(("scene", scene))

    def set_size(self, w, h):
        w, h = max(64, int(w)), max(64, int(h))
        if (w, h) != self.size:
            self.cmds.put(("size", (w, h)))

    def set_beat(self, st):
        self.beat_state = st

    def set_paused(self, on):
        self.paused = bool(on)

    def stop(self, wait=3.0):
        self._stop.set()
        if self.is_alive():
            self.join(wait)

    def frame(self):
        with self._lock:
            return self._frame

    # ---------- поток ----------
    def run(self):
        try:
            self._init_panda()
        except Exception as e:                              # noqa: BLE001
            self.status["error"] = f"3D не запускается: {e}"
            self.log(f"✗ 3D не запускается: {e}")
            return
        last = time.monotonic()
        n, t_fps = 0, last
        while not self._stop.is_set():
            t0 = time.monotonic()
            self._commands()
            dt = min(0.1, t0 - last)
            last = t0
            st = self.beat_state
            if st is not None:
                self.beat_state = None
                self.music.feed(st)
            self.music.step(dt)
            if not self.paused:
                try:
                    for d in self.dancers:
                        d.update(dt, self.music, self.scene)
                    self._render()
                except Exception as e:                      # noqa: BLE001
                    self.log(f"✗ сцена: {e}")
                    time.sleep(0.5)
                n += 1
            if t0 - t_fps >= 1.0:
                self.status["fps"] = round(n / (t0 - t_fps))
                n, t_fps = 0, t0
            rest = 1.0 / self.fps - (time.monotonic() - t0)
            if rest > 0:
                time.sleep(rest)
        try:
            self.engine.removeAllWindows()
        except Exception:                                   # noqa: BLE001
            pass

    def _commands(self):
        scene, size = None, None
        while True:
            try:
                k, v = self.cmds.get_nowait()
            except queue.Empty:
                break
            if k == "scene":
                scene = v
            elif k == "size":
                size = v
        if size:
            self._resize(*size)
        if scene is not None:
            self._apply_scene(scene)

    # ---------- Panda3D ----------
    def _init_panda(self):
        from panda3d.core import loadPrcFileData
        loadPrcFileData("", "\n".join((
            "audio-library-name null", "notify-level error", "notify-level-display error",
            "default-directnotify-level error", "sync-video false", "textures-power-2 none",
            "window-type none", "load-display none")))
        from panda3d.core import (AmbientLight, Camera, DirectionalLight, GraphicsEngine,
                                  GraphicsPipeSelection, LColor, NodePath, PerspectiveLens)
        self.engine = GraphicsEngine.getGlobalPtr()
        self.render = NodePath("render")
        self.cam = self.render.attachNewNode(Camera("cam"))
        self.lens = PerspectiveLens()
        self.lens.setFov(28)
        self.lens.setNearFar(0.05, 100)
        self.cam.node().setLens(self.lens)
        sel = GraphicsPipeSelection.getGlobalPtr()
        tried = []
        self.pipe = self.buf = None
        for mod in PIPES[self.gpu]:
            try:
                pipe = sel.makeModulePipe(mod)
            except Exception:                               # noqa: BLE001
                pipe = None
            if pipe is None:
                tried.append(f"{mod}: нет")
                continue
            ok = self._make_buffer(pipe, *self.size)
            if ok and self._test_frame():
                self.pipe, self.pipe_mod = pipe, mod
                break
            tried.append(f"{mod}: {ok or 'не рисует'}")
            self._drop_buffer()
        if self.buf is None:
            raise RuntimeError("ни один вид графики не заработал (" + "; ".join(tried) + ")")
        self.soft = self.pipe_mod == "p3tinydisplay"
        gsg = self.buf.getGsg()
        rend = ""
        try:
            rend = f"{gsg.getDriverVendor()} {gsg.getDriverRenderer()}".strip()
        except Exception:                                   # noqa: BLE001
            pass
        self.srgb = bool(self.buf.getFbProperties().getSrgbColor())
        self.status.update(ready=True, pipe=PIPE_NAMES.get(self.pipe_mod, self.pipe_mod), renderer=rend)
        self.log(f"✓ 3D: {PIPE_NAMES.get(self.pipe_mod)} — {rend or 'без названия'}"
                 + (f" (не заработало: {'; '.join(tried)})" if tried else ""))
        if not self.soft:
            self.render.setShaderAuto()
        # свет
        self.amb = AmbientLight("amb")
        self.key = DirectionalLight("key")
        self.fill = DirectionalLight("fill")
        self.rim = DirectionalLight("rim")
        for l, hpr in ((self.amb, None), (self.key, (25, -35, 0)), (self.fill, (-50, -15, 0)),
                       (self.rim, (180, -25, 0))):
            np_ = self.render.attachNewNode(l)
            if hpr:
                np_.setHpr(*hpr)
            self.render.setLight(np_)
        self._light(70)
        self.LColor = LColor
        self.models, self.clips, self.tex_cache = {}, {}, {}
        self.dancers = []
        self.scene = {"dancers": [], "spacing": 100, "light": 70, "shadow": True,
                      "inplace": True, "mult": "auto", "style": "real", "palette": "fire", "glow": 120}
        self._shadow_tex = self._make_shadow_tex()

    def _light(self, v):
        k = (v or 70) / 70.0
        if getattr(self, "soft", False):                # без шейдеров — свет по вершинам, мягче
            amb, key, fill, rim = 0.55, 0.75, 0.3, 0.25
        else:
            amb, key, fill, rim = 0.42, 1.0, 0.35, 0.45
        self.amb.setColor((amb * k, amb * k, amb * k * 1.04, 1))
        self.key.setColor((key * k, key * k * 0.96, key * k * 0.92, 1))
        self.fill.setColor((fill * k * 0.92, fill * k * 0.96, fill * k, 1))
        self.rim.setColor((rim * k, rim * k, rim * k, 1))

    def _make_buffer(self, pipe, w, h, gsg=None):
        from panda3d.core import (FrameBufferProperties, GraphicsOutput, GraphicsPipe, LColor,
                                  Texture, WindowProperties)
        for ms in ((4, 0) if gsg is None and "tiny" not in str(pipe.getType()).lower() else (0,)):
            fbp = FrameBufferProperties()
            fbp.setRgbColor(True)
            fbp.setRgbaBits(8, 8, 8, 8)
            fbp.setDepthBits(16)
            if ms:
                fbp.setMultisamples(ms)
            if "tiny" not in str(pipe.getType()).lower():
                fbp.setSrgbColor(True)
            try:
                buf = self.engine.makeOutput(pipe, "dd", -2, fbp, WindowProperties.size(w, h),
                                             GraphicsPipe.BFRefuseWindow, gsg)
            except Exception as e:                          # noqa: BLE001
                buf = None
                err = str(e)
            if buf is None:
                err = "буфер не создаётся"
                continue
            tex = Texture()
            buf.addRenderTexture(tex, GraphicsOutput.RTMCopyRam)
            buf.setClearColorActive(True)
            buf.setClearColor(LColor(0, 0, 0, 0))
            dr = buf.makeDisplayRegion()
            dr.setCamera(self.cam)
            self.buf, self.tex = buf, tex
            self.size = (w, h)
            self._lens()
            return True
        return err

    def _lens(self):
        """Угол обзора 28° по вертикали (Panda задаёт по горизонтали — пересчёт)."""
        w, h = self.size
        asp = w / max(1, h)
        hf = math.degrees(2 * math.atan(math.tan(math.radians(14)) * asp))
        self.lens.setFov(hf, 28)

    def _drop_buffer(self):
        if self.buf is not None:
            try:
                self.engine.removeWindow(self.buf)
            except Exception:                               # noqa: BLE001
                pass
        self.buf = None

    def _test_frame(self):
        try:
            self.engine.renderFrame()
            self.engine.renderFrame()
            img = self.tex.getRamImageAs("BGRA")
            return img is not None and len(img) >= self.size[0] * self.size[1] * 4
        except Exception:                                   # noqa: BLE001
            return False

    def _resize(self, w, h):
        if self.buf is None:
            return
        gsg = self.buf.getGsg()
        self._drop_buffer()
        r = self._make_buffer(self.pipe, w, h, gsg)
        if r is not True:
            self.log(f"✗ размер сцены {w}×{h}: {r}")
            self._make_buffer(self.pipe, 480, 600, gsg)
        self._layout()

    def _make_shadow_tex(self):
        from panda3d.core import PNMImage, Texture
        n = 64
        img = PNMImage(n, n, 4)
        for y in range(n):
            for x in range(n):
                d = math.hypot(x - n / 2 + 0.5, y - n / 2 + 0.5) / (n / 2)
                a = max(0.0, 1 - d) ** 1.6 * 0.55
                img.setXelA(x, y, 0, 0, 0, a)
        t = Texture("shadow")
        t.load(img)
        return t

    # ---------- кадр ----------
    def _render(self):
        self.engine.renderFrame()
        img = self.tex.getRamImageAs("BGRA")
        w, h = self.tex.getXSize(), self.tex.getYSize()
        if img is None or w == 0:
            return
        arr = np.frombuffer(bytes(img), np.uint8).reshape(h, w, 4)[::-1]
        if self.scene.get("style") == "neon":
            from . import neon
            arr = neon.apply(arr, self.scene.get("palette", "fire"), (self.scene.get("glow") or 120) / 100,
                             self._pulse(), time.monotonic())
        h, w = arr.shape[:2]                        # неон считается в половинном размере
        data = np.ascontiguousarray(arr).tobytes()
        with self._lock:
            self._serial += 1
            self._frame = (data, w, h, self._serial)

    def _pulse(self):
        return math.exp(-_frac(self.music.beat) * 5) if self.music.active else 0.0

    # ---------- сцена ----------
    def _apply_scene(self, sc):
        old_inplace = self.scene.get("inplace")
        self.scene = dict(self.scene, **sc)
        self._light(self.scene.get("light", 70))
        want = list(self.scene.get("dancers", []))[:6]
        new = []
        for i, sp in enumerate(want):
            old = self.dancers[i] if i < len(self.dancers) else None
            if old is not None and old.spec.get("char") == sp.get("char") and old.ok:
                old.spec["scale"] = sp.get("scale", 100)
                if old.spec.get("dance") != sp.get("dance") or old_inplace != self.scene.get("inplace"):
                    old.set_dance(sp.get("dance"))
                new.append(old)
            else:
                if old is not None:
                    old.remove()
                d = Dancer(self, dict(sp), i)
                d.load()
                new.append(d)
        for d in self.dancers[len(want):]:
            d.remove()
        self.dancers = new
        self._layout()
        self.status["dancers"] = [{"char": d.spec.get("char"), "dance": d.spec.get("dance"), "ok": d.ok,
                                   "err": d.err, "beat": round(d.period, 3)} for d in self.dancers]

    def _layout(self):
        n = max(1, len(self.dancers))
        gap = 0.85 * (self.scene.get("spacing") or 100) / 100
        for i, d in enumerate(self.dancers):
            d.root.setPos((i - (n - 1) / 2) * gap, (0.15 if (i % 2 and n > 2) else 0), 0)
        ms = max([(d.spec.get("scale") or 100) / 100 for d in self.dancers] + [1])
        w = (n - 1) * gap + 0.9 * ms
        h = 1.9 * ms
        asp = self.size[0] / max(1, self.size[1])
        vf = math.radians(28) / 2
        dist = max(h / 2 / math.tan(vf), w / 2 / (math.tan(vf) * asp)) * 1.08
        self.cam.setPos(0, -dist, h * 0.5 + 0.05)
        self.cam.lookAt(0, 0, h * 0.47)

    # ---------- файлы ----------
    def model(self, rel):
        """Модель (кэш файла): gltf_mesh.Model — данные; узел Panda строится для каждой девушки."""
        if rel not in self.models:
            from . import gltf_mesh
            path = self.root / rel
            if path.suffix.lower() == ".fbx":
                raise RuntimeError("FBX пока не поддерживается — переведите в GLB (Blender: Экспорт → glTF 2.0)")
            self.models[rel] = gltf_mesh.Model(path)
        return self.models[rel]

    def clip(self, char, dance, inplace):
        key = (char, dance, bool(inplace))
        if key not in self.clips:
            m = self.model(char)
            tg, tr = m.g, m.rig
            if dance and dance.startswith("dances/"):
                src = self.root / dance
                if src.suffix.lower() == ".fbx":
                    raise RuntimeError("танец FBX пока не поддерживается — переведите в GLB")
                sg = ga.Gltf(src)
                sr = ga.Rig(sg)
            else:
                sg, sr = tg, tr
            an = ga.longest(ga.animations(sg))
            if an is None:
                raise RuntimeError("в файле нет анимации")
            c = ga.retarget(sg, an, tg, inplace, sr, tr)
            if c is None:
                raise RuntimeError("танец не подходит к скелету модели")
            self.clips[key] = c
        return self.clips[key]


class Dancer:
    def __init__(self, eng, spec, idx):
        self.e, self.spec, self.idx = eng, spec, idx
        self.root = eng.render.attachNewNode(f"dancer{idx}")
        self.user = self.root.attachNewNode("user")         # рост из настроек
        self.fit = self.user.attachNewNode("fit")
        self.orient = self.fit.attachNewNode("orient")      # оси glTF → сцена, лицом к зрителю
        self.model = None
        self.ok, self.err = False, ""
        self.clip = None
        self.period, self.t0 = 0.5, 0.0
        self.mult, self.ts, self.t = 1.0, 1.0, 0.0
        from panda3d.core import CardMaker, TransparencyAttrib
        cm = CardMaker("shadow")
        cm.setFrame(-0.4, 0.4, -0.25, 0.25)
        self.shadow = self.user.attachNewNode(cm.generate())
        self.shadow.setP(-90)
        self.shadow.setZ(0.003)
        self.shadow.setTexture(eng._shadow_tex)
        self.shadow.setTransparency(TransparencyAttrib.MAlpha)
        self.shadow.setDepthWrite(False)
        self.shadow.setLightOff()
        self.shadow.setBin("fixed", 0)

    def load(self):
        from . import gltf_mesh
        char = self.spec.get("char") or ""
        try:
            if not char or char.startswith("builtin:"):
                raise RuntimeError("встроенного манекена в версии 2 нет — выберите девушку")
            src = self.e.model(char)
            # своя копия сетки — у каждой девушки своя поза
            self.model = gltf_mesh.Model.__new__(gltf_mesh.Model)
            self.model.__dict__.update(src.__dict__)
            self.model.prims = [gltf_mesh.Prim(p.pos, p.nrm, p.uv, p.idx, p.joints, p.weights,
                                               p.node, p.skin, p.mat) for p in src.prims]
            self.rig = src.rig
            node = self.model.build(self.e.srgb, self.e.tex_cache.setdefault(char, {}))
            node.reparentTo(self.orient)
            self._orient_fit()
            self.name_idx = {self.rig.name[i]: i for i in self.rig.order if self.rig.name[i]}
            self.set_dance(self.spec.get("dance"))
            self.ok = True
        except Exception as e:                              # noqa: BLE001
            self.err = str(e)
            self.e.log(f"✗ девушка {Path(char).stem or '?'}: {e}")

    def _orient_fit(self):
        """Поставить девушку на ноги лицом к зрителю (по голове, ступням, плечам) и в рост."""
        from panda3d.core import LMatrix4f
        R = self.rig
        wm = R.world_mats()

        def pos(canon):
            i = R.by_name.get(canon)
            return wm[i][:3, 3] if i is not None else None
        head, lf, rf, la, ra = (pos(k) for k in ("head", "leftfoot", "rightfoot", "leftarm", "rightarm"))
        if head is not None and lf is not None and rf is not None and la is not None and ra is not None:
            up = head - (lf + rf) / 2
            up = up / max(1e-9, np.linalg.norm(up))
            right = ra - la                             # к правой руке девушки
            right = right - up * (right @ up)
            right = right / max(1e-9, np.linalg.norm(right))
        else:                                           # без скелета: glTF — Y вверх, лицом к +Z
            up, right = np.array([0, 1.0, 0]), np.array([-1.0, 0, 0])
        fwd = np.cross(up, right)
        A = np.array([right, up, fwd])
        B = np.array([[-1, 0, 0], [0, 0, 1], [0, -1, 0.0]])  # правая → −X, верх → +Z, лицо → −Y (к камере)
        Rm = A.T @ B                                    # строки-векторы Panda: v·R
        pts = self.model.rest_positions() @ Rm
        if len(pts) == 0:
            return
        mn, mx = pts.min(0), pts.max(0)
        h = mx[2] - mn[2]
        k = HEIGHT / h if h > 1e-6 else 1.0
        c = (mn + mx) / 2
        Rk = Rm * k
        self.orient.setMat(LMatrix4f(Rk[0, 0], Rk[0, 1], Rk[0, 2], 0, Rk[1, 0], Rk[1, 1], Rk[1, 2], 0,
                                     Rk[2, 0], Rk[2, 1], Rk[2, 2], 0,
                                     -c[0] * k, -c[1] * k, -mn[2] * k, 1))

    def set_dance(self, dance):
        self.spec["dance"] = dance
        char = self.spec.get("char")
        inplace = self.e.scene.get("inplace", True)
        try:
            try:
                self.clip = self.e.clip(char, dance if (dance or "").startswith("dances/") else "embedded", inplace)
            except RuntimeError:
                if (dance or "").startswith("dances/"):
                    raise
                kit = sorted((self.e.root / "dances" / "rocketbox").glob("*.glb"))
                if not kit:
                    raise
                self.clip = self.e.clip(char, "dances/rocketbox/" + kit[self.idx % len(kit)].name, inplace)
            self.err = ""
        except Exception as e:                              # noqa: BLE001
            self.clip = None
            self.err = str(e)
            self.e.log(f"✗ танец {Path(dance or '').stem or '?'}: {e}")
            self.model.skin(self.rig.world_mats())
            return
        c = self.clip
        self.period, self.t0 = c.period, c.t0
        self.rot_idx = {self.name_idx[n]: n for n in c.rot if n in self.name_idx}
        self.mover_idx = self.name_idx.get(c.mover) if c.mover else None
        self.e.log(f"   танец «{Path(dance or c.name).stem}» → {Path(char).stem}: костей {len(self.rot_idx)}, "
                   f"доля клипа {c.period:.3f} с{'' if c.auto else ' (по умолчанию)'}")

    def update(self, dt, music, scene):
        s = (self.spec.get("scale") or 100) / 100
        self.user.setScale(s)
        self.shadow.show() if scene.get("shadow", True) and scene.get("style") != "neon" else self.shadow.hide()
        if self.clip is None:
            return
        c = self.clip
        if music.active:
            base = self.period * music.bpm / 60.0
            m = self.mult
            mode = scene.get("mult", "auto")
            if mode == "half":
                m = 0.5
            elif mode == "double":
                m = 2.0
            elif mode == "normal":
                m = 1.0
            else:
                best = min((0.5, 1.0, 2.0), key=lambda x: abs(math.log2(base * x)))
                if abs(math.log2(base * best)) + 0.2 < abs(math.log2(base * m)):
                    m = best
            self.mult = m
            mp = _frac(music.beat * m)
            cp = _frac((self.t - self.t0) / self.period)
            target = min(3.0, max(0.25, base * m * (1 + 0.8 * _wrap(mp - cp))))
        else:
            target = 0.35
        self.ts += (target - self.ts) * min(1.0, dt * 6)
        self.t = (self.t + dt * self.ts) % max(c.duration, 1e-6)
        rot, pos = c.frame(self.t)
        r = {i: rot[n] for i, n in self.rot_idx.items()}
        p = {self.mover_idx: pos} if (pos is not None and self.mover_idx is not None) else {}
        self.model.skin(self.rig.world_with(r, p))

    def remove(self):
        try:
            self.root.removeNode()
        except Exception:                                   # noqa: BLE001
            pass
