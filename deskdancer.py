"""deskdancer.py  v1.5.0 — ядро DeskDancer (без окон)

3D-девушки танцуют на рабочем столе Windows под музыку, в такт.
Здесь: настройки, журнал, авто-установка библиотек, определение такта
(BPM + фаза) по звуку ПК / микрофону, локальный веб-сервер для 3D-сцены
(three.js в QWebEngineView), библиотека моделей и танцев, --selftest.

Журнал:
v1.5.0: настройка «gpu» — режим графики сцены (auto / opengl / software)
v1.4.0: настройка «фон сцены» (прозрачный / тёмный); пустая ошибка звука — имя ошибки
v1.3.0: настройки сцены «Вид» (обычный / неон), палитра и сила свечения
v1.2.0: ещё 5 танцев в комплекте (Rocketbox) — всего 10; selftest ждёт 10 танцев
v1.1.0: в комплекте 10 реалистичных девушек и 5 танцев (Microsoft Rocketbox, MIT);
        сцена по умолчанию — три девушки; папки _other/ не читаются
v1.0.0: первая версия — захват звука ПК (WASAPI loopback) и микрофона,
        определение BPM и фазы такта, ручной BPM и «тап», сервер сцены,
        библиотека characters/ и dances/, скачивание примеров, selftest
"""
import importlib
import importlib.util
import json
import logging
import logging.handlers
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

VERSION = "1.5.0"
APP_NAME = "DeskDancer"
APP_ID = "DeskDancer.App"

APP_ROOT = Path(sys.executable).parent if getattr(sys, "frozen", False) \
    else Path(__file__).resolve().parent
RES_ROOT = Path(getattr(sys, "_MEIPASS", APP_ROOT))       # web/ в сборке
CHAR_DIR = APP_ROOT / "characters"
DANCE_DIR = APP_ROOT / "dances"
CONFIG_PATH = APP_ROOT / "config.json"
LOG_PATH = APP_ROOT / "deskdancer.log"
MODEL_EXT = (".glb", ".gltf", ".fbx")

# (имя импорта, pip-имя) — ставятся сами при первом запуске
REQUIRED = (("PySide6", "PySide6>=6.6"), ("numpy", "numpy>=1.24"))
# нужна только для захвата звука — ставится лениво в рабочем потоке
OPTIONAL_AUDIO = ("soundcard", "soundcard>=0.4.3")

# примеры моделей — скачиваются из репозитория three.js (MIT, модели Mixamo)
EXAMPLES_BASE = "https://raw.githubusercontent.com/mrdoob/three.js/r160/examples/models/"
EXAMPLES = (("gltf/Michelle.glb", "Michelle.glb"),
            ("fbx/Samba%20Dancing.fbx", "Samba Dancing.fbx"))


# ───────────────────────── авто-установка библиотек ─────────────────────────
def _missing(pairs):
    return [pip for mod, pip in pairs if importlib.util.find_spec(mod) is None]


def _python_exe():
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        cand = exe.with_name("python.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def pip_install(pips, console=True):
    """Ставит пакеты pip'ом. True — всё встало."""
    if not pips:
        return True
    py = _python_exe()
    flags = 0
    if sys.platform == "win32":
        flags = 0x10 if console else 0x08000000     # NEW_CONSOLE / NO_WINDOW
    base = [py, "-m", "pip", "install", "--disable-pip-version-check"]
    try:
        r = subprocess.run(base + list(pips), creationflags=flags)
        if r.returncode != 0:
            subprocess.run([py, "-m", "ensurepip", "--upgrade"],
                           creationflags=flags)
            r = subprocess.run(base + ["--user"] + list(pips),
                               creationflags=flags)
    except OSError:
        return False
    importlib.invalidate_caches()
    return r.returncode == 0


def ensure_packages():
    if getattr(sys, "frozen", False) or "--selftest" in sys.argv:
        return
    miss = _missing(REQUIRED)
    if not miss:
        return
    if pip_install(miss) and not _missing(REQUIRED):
        return
    text = ("Не удалось установить библиотеки:\n  " + "\n  ".join(miss) +
            "\n\nПоставьте вручную:\n  pip install " + " ".join(miss))
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)
    else:
        print(text, file=sys.stderr)
    sys.exit(1)


# ───────────────────────── настройки ─────────────────────────
DEFAULT_CONFIG = {
    "theme": "dark",
    "page": 0,
    "geometry": "",
    "overlay": {"x": -1, "y": -1, "w": 520, "h": 620, "visible": False,
                "locked": False, "on_top": True, "opacity": 100, "bg": "transparent"},
    "audio": {"source": "loopback", "manual_bpm": 120, "sens": 50,
              "offset_ms": 60, "mult": "auto"},
    "scene": {"dancers": [
        {"char": "characters/rocketbox/Алина.glb", "dance": "dances/rocketbox/Весёлый.glb", "scale": 100},
        {"char": "characters/rocketbox/Елена.glb", "dance": "dances/rocketbox/Крутой.glb", "scale": 100},
        {"char": "characters/rocketbox/Карина.glb", "dance": "dances/rocketbox/Энергичный.glb", "scale": 100}],
              "spacing": 100, "light": 70, "shadow": True, "inplace": True,
              "style": "real", "palette": "fire", "glow": 120},
    "gpu": "auto",
    "presets": {},
    "update": {"token": "", "auto": True, "branch": "main", "every_h": 12},
}


def _merge(base, add):
    out = dict(base)
    for k, v in (add or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k != "presets":
            out[k] = _merge(base[k], v)
        else:
            out[k] = v
    return out


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config(path=CONFIG_PATH):
    """Битый JSON не читается как пустой: берём .bak; нет — по умолчанию
    и запись запрещена (флаг _readonly), чтобы не затереть файл."""
    path = Path(path)
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if not path.exists():
        return cfg
    try:
        return _merge(cfg, _read_json(path))
    except (OSError, ValueError) as e:
        logging.getLogger("dd").warning(f"⚠ config.json не читается ({e}) — беру копию .bak")
    bak = path.with_suffix(".json.bak")
    try:
        return _merge(cfg, _read_json(bak))
    except (OSError, ValueError):
        cfg["_readonly"] = True
        logging.getLogger("dd").error("✗ и копия .bak не читается — настройки не будут записаны")
        return cfg


def _replace(src, dst, tries=8):
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:          # WinError 5/32 — файл на миг занят
            if i == tries - 1:
                raise
            time.sleep(0.15 * (i + 1))


def save_config(cfg, path=CONFIG_PATH):
    if cfg.get("_readonly"):
        return False
    path = Path(path)
    data = {k: v for k, v in cfg.items() if not k.startswith("_")}
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                json.load(f)                        # копия — только целого
            _replace_copy(path, path.with_suffix(".json.bak"))
        except (OSError, ValueError):
            pass
    _replace(tmp, path)
    return True


def _replace_copy(src, dst):
    tmp = Path(str(dst) + ".tmp")
    tmp.write_bytes(Path(src).read_bytes())
    _replace(tmp, dst)


# ───────────────────────── журнал ─────────────────────────
LOG_QUEUE = queue.Queue()
DONE = object()                     # конец фоновой работы


class _QueueHandler(logging.Handler):
    def emit(self, record):
        try:
            LOG_QUEUE.put(self.format(record))
        except Exception:            # noqa: BLE001
            pass


def setup_logging():
    log = logging.getLogger("dd")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    qh = _QueueHandler()
    qh.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    log.addHandler(qh)
    try:
        fh = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
        log.addHandler(fh)
    except OSError:
        pass
    return log


log = logging.getLogger("dd")


# ───────────────────────── определение такта ─────────────────────────
class BeatTracker:
    """BPM и фаза такта по звуку. feed(samples) — моно float32 блоки.
    state() → {"bpm", "phase", "conf", "energy", "active", "beats"}.
    Огибающая начала нот: спектральный поток (низы весомее), темп —
    автокорреляция огибающей с поправкой на кратные (½, 2×) и мягким
    предпочтением 90…140 BPM, фаза — гребёнка по последним 4 с."""

    def __init__(self, sr=44100, hop=512, sens=50):
        import numpy as np
        self.np = np
        self.sr, self.hop = sr, hop
        self.fps = sr / hop
        self.n_fft = 2048
        self.win = np.hanning(self.n_fft).astype(np.float32)
        self.buf = np.zeros(self.n_fft, np.float32)
        freqs = np.fft.rfftfreq(self.n_fft, 1.0 / sr)
        self.wts = np.where(freqs < 180, 2.5, np.where(freqs < 2500, 1.0, 0.5)) \
            .astype(np.float32)
        self.wts[freqs > 12000] = 0
        self.prev = None
        self.env_len = int(self.fps * 8)
        self.env = np.zeros(self.env_len, np.float32)
        self.env_low = np.zeros(self.env_len, np.float32)   # только низы — для фазы
        self.low = freqs < 180
        self.frames = 0
        self.bpm = 0.0
        self.cand, self.cand_n = 0.0, 0
        self.conf = 0.0
        self.last_beat_frame = None          # кадр последней доли
        self.energy = 0.0
        self.peak = 1e-4
        self.silence = 0.0
        self.sens = sens
        self._next_tempo = 0
        self.lock = threading.Lock()

    # --- поток звука ---
    def feed(self, x):
        np = self.np
        x = np.asarray(x, np.float32).ravel()
        for i in range(0, len(x) - self.hop + 1, self.hop):
            self._frame(x[i:i + self.hop])

    def _frame(self, blk):
        np = self.np
        self.buf = np.concatenate((self.buf[self.hop:], blk))
        rms = float(np.sqrt(np.mean(blk * blk)) + 1e-12)
        self.peak = max(rms, self.peak * 0.9995, 1e-4)
        e = min(1.0, rms / self.peak)
        gate = 10 ** (-(3.0 + self.sens / 25.0))       # чувствительность
        if rms < gate:
            self.silence += self.hop / self.sr
            e = 0.0
        else:
            self.silence = 0.0
        self.energy = self.energy * 0.8 + e * 0.2
        mag = np.abs(np.fft.rfft(self.buf * self.win))
        lm = np.log1p(mag * 100.0)
        flux = low = 0.0
        if self.prev is not None:
            d = np.maximum(lm - self.prev, 0)
            flux = float(np.sum(d * self.wts))
            low = float(np.sum(d[self.low]))
        self.prev = lm
        self.env = np.roll(self.env, -1)
        self.env[-1] = flux
        self.env_low = np.roll(self.env_low, -1)
        self.env_low[-1] = low
        self.frames += 1
        if self.frames >= self._next_tempo:
            self._next_tempo = self.frames + int(self.fps * 0.5)
            self._estimate()

    # --- темп и фаза ---
    def _estimate(self):
        np = self.np
        n = min(self.frames, self.env_len)
        if n < self.fps * 3 or self.silence > 1.5:
            self.conf *= 0.5
            return
        env = self.env[-n:].astype(np.float64)
        # убрать медленный тренд, оставить всплески
        k = max(3, int(self.fps * 0.4))
        trend = np.convolve(env, np.ones(k) / k, mode="same")
        o = np.maximum(env - trend, 0)
        if o.max() <= 1e-9:
            self.conf *= 0.5
            return
        o = o - o.mean()
        acf = np.correlate(o, o, mode="full")[n - 1:]
        if acf[0] <= 0:
            return
        acf = acf / acf[0]
        lo = int(self.fps * 60 / 200)
        hi = min(int(self.fps * 60 / 60), n // 2)
        lags = np.arange(lo, hi)
        if len(lags) < 3:
            return

        def a(l):
            l = np.clip(l, 0, len(acf) - 1)
            return np.interp(l, np.arange(len(acf)), acf)

        def prior(b):
            return np.exp(-0.5 * (np.log2(np.asarray(b) / 118.0) / 0.7) ** 2)

        bpms = 60.0 * self.fps / lags
        s = (a(lags) + 0.5 * a(lags * 2.0)) * (0.5 + 0.5 * prior(bpms))
        i = int(np.argmax(s))
        lag = float(lags[i])
        if 0 < i < len(s) - 1:                         # уточнение параболой
            y0, y1, y2 = s[i - 1], s[i], s[i + 1]
            den = y0 - 2 * y1 + y2
            if abs(den) > 1e-12:
                lag += 0.5 * (y0 - y2) / den
        # октавная ошибка: вдвое быстрее держится почти так же — берём её
        b0 = 60.0 * self.fps / lag
        if b0 * 2 <= 200 and a(lag / 2.0) * (0.5 + 0.5 * prior(b0 * 2)) > \
                0.85 * a(lag) * (0.5 + 0.5 * prior(b0)):
            lag /= 2.0
        bpm = 60.0 * self.fps / lag
        self.conf = float(max(0.0, min(1.0, a(lag))))
        with self.lock:
            if self.bpm <= 0 or abs(bpm / self.bpm - 1) < 0.04:
                self.bpm = bpm if self.bpm <= 0 else self.bpm * 0.7 + bpm * 0.3
                self.cand_n = 0
            else:
                if self.cand and abs(bpm / self.cand - 1) < 0.04:
                    self.cand_n += 1
                else:
                    self.cand, self.cand_n = bpm, 1
                if self.cand_n >= 3:                   # новый темп подтверждён
                    self.bpm, self.cand_n = self.cand, 0
            period = 60.0 * self.fps / self.bpm
            # фаза — гребёнка по последним 4 с
            m = int(min(n, self.fps * 4))
            lo_env = self.env_low[-n:].astype(np.float64)
            lo_o = np.maximum(lo_env - np.convolve(lo_env, np.ones(k) / k, mode="same"), 0)
            # низы есть — фаза по бочке, иначе по всему спектру
            seg = (lo_o if lo_o[-m:].sum() > 0.05 * max(1e-9, o.clip(0).sum() * m / n)
                   else np.maximum(o, 0))[-m:]
            best, best_off = -1e18, 0.0
            steps = max(8, int(period))
            for j in range(steps):
                off = j * period / steps
                idx = (m - 1 - off - np.arange(0, m, period)).astype(int)
                idx = idx[idx >= 0]
                v = float(seg[idx].sum())
                if v > best:
                    best, best_off = v, off
            self.last_beat_frame = self.frames - 1 - best_off

    def state(self, offset_ms=0):
        with self.lock:
            bpm = self.bpm
            lb = self.last_beat_frame
        active = bpm > 0 and self.silence < 1.5 and self.conf > 0.05
        phase = 0.0
        if bpm > 0 and lb is not None:
            period = 60.0 * self.fps / bpm
            now = self.frames + offset_ms / 1000.0 * self.fps
            phase = ((now - lb) / period) % 1.0
        return {"bpm": round(float(bpm), 2), "phase": round(float(phase), 4),
                "conf": round(float(self.conf), 3), "energy": round(float(self.energy), 3),
                "active": bool(active)}


class ManualClock:
    """Метроном: ручной BPM и «тап» (средний интервал последних касаний)."""

    def __init__(self, bpm=120):
        self.bpm = float(bpm)
        self.t0 = time.monotonic()
        self.taps = []

    def set_bpm(self, bpm):
        now = time.monotonic()
        ph = self.phase(now)
        self.bpm = float(max(40, min(240, bpm)))
        self.t0 = now - ph * 60.0 / self.bpm

    def tap(self):
        now = time.monotonic()
        self.taps = [t for t in self.taps if now - t < 3.0] + [now]
        if len(self.taps) >= 3:
            d = [b - a for a, b in zip(self.taps, self.taps[1:])]
            self.bpm = max(40.0, min(240.0, 60.0 / (sum(d) / len(d))))
        self.t0 = now                         # касание — начало доли
        return self.bpm

    def phase(self, now=None):
        now = time.monotonic() if now is None else now
        return ((now - self.t0) * self.bpm / 60.0) % 1.0

    def state(self, offset_ms=0):
        ph = self.phase(time.monotonic() + offset_ms / 1000.0)
        return {"bpm": round(self.bpm, 2), "phase": round(ph, 4), "conf": 1.0,
                "energy": 0.7, "active": True}


class AudioWorker(threading.Thread):
    """Читает звук ПК (loopback) или микрофон в BeatTracker. Одна работа за
    раз; stop() — остановить и дождаться. Ошибка — понятной строкой в журнал,
    источник остаётся «на паузе», программа работает дальше."""

    def __init__(self, source, tracker, on_error=None):
        super().__init__(daemon=True, name="audio")
        self.source = source
        self.tracker = tracker
        self.on_error = on_error
        self._stop = threading.Event()
        self.ok = False

    def stop(self, wait=2.0):
        self._stop.set()
        if self.is_alive():
            self.join(wait)

    def run(self):
        try:
            sc = self._import_soundcard()
            if sc is None:
                return
            import warnings
            warnings.filterwarnings("ignore", module="soundcard")
            if self.source == "mic":
                dev = sc.default_microphone()
                name = f"микрофон «{dev.name}»"
            else:
                spk = sc.default_speaker()
                dev = sc.get_microphone(id=str(spk.name), include_loopback=True)
                name = f"звук ПК «{spk.name}»"
            log.info(f"✓ слушаю {name}")
            hop = self.tracker.hop
            with dev.recorder(samplerate=self.tracker.sr, blocksize=hop * 2) as rec:
                self.ok = True
                while not self._stop.is_set():
                    data = rec.record(numframes=hop * 2)
                    if data is None or len(data) == 0:
                        continue
                    if data.ndim == 2:
                        data = data.mean(axis=1)
                    self.tracker.feed(data)
        except Exception as e:                          # noqa: BLE001
            msg = f"✗ звук не читается: {e or type(e).__name__}. Переключитесь на «Вручную» или выберите другой источник"
            log.error(msg)
            if self.on_error:
                self.on_error(str(e))
        finally:
            self.ok = False

    @staticmethod
    def _import_soundcard():
        mod, pip = OPTIONAL_AUDIO
        if importlib.util.find_spec(mod) is None:
            if getattr(sys, "frozen", False):
                log.error("✗ в сборке нет библиотеки soundcard")
                return None
            log.info(f"⏳ ставлю {pip} (захват звука)…")
            if not pip_install([pip], console=False) or \
                    importlib.util.find_spec(mod) is None:
                log.error(f"✗ не удалось поставить {pip}: pip install {pip}")
                return None
            log.info(f"✓ {pip} установлена")
        return importlib.import_module(mod)


# ───────────────────────── сервер сцены ─────────────────────────
class SceneServer:
    """Отдаёт web/, characters/, dances/ на 127.0.0.1:<свободный порт>.
    ES-модули three.js с file:// не грузятся — нужен http."""

    ALLOWED = ("web", "characters", "dances")

    def __init__(self):
        import http.server
        import socketserver
        import urllib.parse
        roots = {"web": RES_ROOT / "web", "characters": CHAR_DIR,
                 "dances": DANCE_DIR}

        class H(http.server.SimpleHTTPRequestHandler):
            extensions_map = {
                ".html": "text/html; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
                ".mjs": "text/javascript; charset=utf-8",
                ".json": "application/json", ".css": "text/css",
                ".glb": "model/gltf-binary", ".gltf": "model/gltf+json",
                ".fbx": "application/octet-stream", ".png": "image/png",
                ".jpg": "image/jpeg", ".bin": "application/octet-stream",
                "": "application/octet-stream"}

            def translate_path(self, path):
                p = urllib.parse.unquote(urllib.parse.urlsplit(path).path)
                parts = [x for x in p.split("/") if x and x not in (".", "..")]
                if not parts or parts[0] not in roots:
                    return str(RES_ROOT / "web" / "__nope__")
                base = roots[parts[0]].resolve()
                full = base.joinpath(*parts[1:]).resolve()
                if base != full and base not in full.parents:
                    return str(base / "__nope__")
                return str(full)

            def end_headers(self):
                self.send_header("Cache-Control", "no-store")
                super().end_headers()

            def log_message(self, *a):
                pass

        class S(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        self.httpd = S(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever,
                                       daemon=True, name="scene-http")
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/web/index.html"

    def stop(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:                               # noqa: BLE001
            pass


# ───────────────────────── библиотека ─────────────────────────
BUILTIN_CHARS = (("builtin:mannequin", "Манекен (встроенный)"),)
BUILTIN_DANCES = (("builtin:groove", "Грув (встроенный)"),
                  ("builtin:disco", "Диско (встроенный)"),
                  ("builtin:hiphop", "Хип-хоп (встроенный)"),
                  ("builtin:sway", "Покачивание (встроенный)"))
EMBEDDED = ("embedded", "Танец из файла девушки")


def scan_dir(d):
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(d.rglob("*"), key=lambda x: str(x).lower()):
        if "_other" in p.relative_to(d).parts:          # убранные пользователем
            continue
        if p.is_file() and p.suffix.lower() in MODEL_EXT:
            rel = p.relative_to(d).as_posix()
            out.append((rel, p.stat().st_size))
    return out


def characters():
    return list(BUILTIN_CHARS) + [(f"characters/{r}", Path(r).stem)
                                  for r, _ in scan_dir(CHAR_DIR)]


def dances():
    return [EMBEDDED] + list(BUILTIN_DANCES) + [(f"dances/{r}", Path(r).stem)
                                                for r, _ in scan_dir(DANCE_DIR)]


def unique_dest(folder, name, data_head=b"", size=-1):
    """Куда положить файл: одноимённый с тем же размером и началом — тот же
    (None), разный — рядом с номером (оба остаются)."""
    folder = Path(folder)
    dst = folder / name
    if not dst.exists():
        return dst
    try:
        if size == dst.stat().st_size and data_head and \
                dst.read_bytes()[:len(data_head)] == data_head:
            return None
    except OSError:
        pass
    stem, ext = dst.stem, dst.suffix
    i = 2
    while (folder / f"{stem} ({i}){ext}").exists():
        i += 1
    return folder / f"{stem} ({i}){ext}"


def download_examples(progress=None, stop=None):
    """Скачивает примеры (Michelle — самба) в characters/. TLS проверяется."""
    CHAR_DIR.mkdir(parents=True, exist_ok=True)
    got = 0
    for i, (src, name) in enumerate(EXAMPLES):
        if stop and stop():
            break
        dst = CHAR_DIR / name
        if dst.exists() and dst.stat().st_size > 100_000:
            log.info(f"✓ уже есть: {name}")
            got += 1
            continue
        url = EXAMPLES_BASE + src
        log.info(f"⏳ скачиваю {name}…")
        req = urllib.request.Request(url, headers={"User-Agent": "DeskDancer"})
        last = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    total = int(r.headers.get("Content-Length") or 0)
                    tmp = dst.with_suffix(dst.suffix + ".part")
                    n = 0
                    with open(tmp, "wb") as f:
                        while True:
                            chunk = r.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            n += len(chunk)
                            if progress and total:
                                progress(int(100 * (i + n / total) / len(EXAMPLES)))
                    if total and n != total:
                        raise OSError(f"скачано {n} из {total} байт")
                    _replace(tmp, dst)
                log.info(f"✓ {name}: {n / 1048576:.1f} МБ")
                got += 1
                last = None
                break
            except Exception as e:                      # noqa: BLE001
                last = e
                time.sleep(2 * (attempt + 1))
        if last is not None:
            log.error(f"✗ {name} не скачался: {last}")
    if progress:
        progress(100)
    return got


# ───────────────────────── selftest ─────────────────────────
def synth_clicks(bpm=128.0, seconds=10.0, sr=44100, seed=1):
    """Тестовый трек: бочка на каждую долю + шум."""
    import numpy as np
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    x = rng.normal(0, 0.01, n).astype(np.float32)
    period = 60.0 / bpm
    t = np.arange(int(0.12 * sr)) / sr
    kick = (np.sin(2 * np.pi * 60 * t) * np.exp(-t * 30)).astype(np.float32)
    k = 0
    while True:
        s = int(k * period * sr)
        if s >= n:
            break
        e = min(n, s + len(kick))
        x[s:e] += 0.8 * kick[:e - s]
        k += 1
    return x


def selftest():
    lines, ok = [], True

    def rep(flag, text):
        nonlocal ok
        ok = ok and flag
        lines.append(("✓ " if flag else "✗ ") + text)

    rep(True, f"{APP_NAME} v{VERSION}, Python {sys.version.split()[0]}")
    for mod in ("numpy", "PySide6", "PySide6.QtWebEngineWidgets",
                "app.gh_update", "app.window_frame", "deskdancer_qt"):
        try:
            importlib.import_module(mod)
            rep(True, f"импорт {mod}")
        except Exception as e:                          # noqa: BLE001
            rep(False, f"импорт {mod}: {e}")
    try:
        for bpm in (96.0, 128.0, 140.0):
            tr = BeatTracker()
            tr.feed(synth_clicks(bpm, 10.0))
            st = tr.state()
            # фаза: трек кончается через (n % period) после последней доли
            period = 60.0 / bpm
            exp = ((10.0 % period) / period) % 1.0
            dph = abs((st["phase"] - exp + 0.5) % 1.0 - 0.5)
            rep(abs(st["bpm"] - bpm) < 2.5 and dph < 0.12,
                f"такт {bpm:.0f} BPM → {st['bpm']:.1f}, фаза {st['phase']:.2f} (ждём {exp:.2f})")
    except Exception as e:                              # noqa: BLE001
        rep(False, f"определение такта: {e}")
    try:
        srv = SceneServer()
        with urllib.request.urlopen(srv.url, timeout=5) as r:
            body = r.read()
        rep(b"importmap" in body, f"сервер сцены {srv.url}")
        bad = f"http://127.0.0.1:{srv.port}/web/../deskdancer.py"
        try:
            urllib.request.urlopen(bad, timeout=5)
            rep(False, "сервер отдал файл вне разрешённых папок")
        except urllib.error.HTTPError:
            rep(True, "сервер не отдаёт файлы вне web/characters/dances")
        srv.stop()
    except Exception as e:                              # noqa: BLE001
        rep(False, f"сервер сцены: {e}")
    rep((RES_ROOT / "web" / "vendor" / "three" / "build" / "three.module.min.js").exists(),
        "three.js на месте")
    nc = len(list((CHAR_DIR / "rocketbox").glob("*.glb")))
    nd = len(list((DANCE_DIR / "rocketbox").glob("*.glb")))
    rep(nc >= 10 and nd >= 10, f"в комплекте девушек {nc}, танцев {nd}")
    text = "\n".join(lines) + f"\nИТОГ: {'OK' if ok else 'ОШИБКИ'}\n"
    print(text)
    try:
        (APP_ROOT / "selftest.txt").write_text(text, encoding="utf-8")
    except OSError:
        pass
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.path.insert(0, str(APP_ROOT))
        sys.exit(selftest())
    ensure_packages()
    setup_logging()
    from deskdancer_qt import run
    sys.exit(run())


if __name__ == "__main__":
    main()
