"""engine_proc.py  v2.1.0 — 3D-движок в отдельном процессе (на другом Python)

Клиент EngineProcess — то же, что engine3d.Engine (set_scene, set_size,
set_beat, set_paused, stop, frame, status), но сцена считается в дочернем
процессе: `python engine_proc.py <папка программы> <графика>`. Нужен, когда
в Python программы нет Panda3D (например, Python 3.15).

Обмен: команды — строки JSON в stdin; ответы — сообщения в stdout:
4 байта длина + 1 байт тип (L — журнал, S — состояние, F — кадр) + данные.

Журнал:
v2.1.0: первая версия
"""
import json
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ───────────────────────── дочерний процесс ─────────────────────────
def _server(root, gpu):
    sys.path.insert(0, root)
    out = sys.stdout.buffer
    lock = threading.Lock()

    def send(kind, data):
        with lock:
            out.write(struct.pack("<Ic", len(data), kind) + data)
            out.flush()

    def log(m):
        send(b"L", str(m).encode("utf-8", "replace"))

    try:
        from app.engine3d import Engine
    except Exception as e:                                  # noqa: BLE001
        log(f"✗ 3D-движок не загрузился: {e}")
        return 1
    eng = Engine(root, gpu=gpu, log=log)
    eng.start()
    stop = threading.Event()

    def reader():
        stdin = sys.stdin.buffer
        for raw in stdin:
            try:
                msg = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            c, v = msg.get("cmd"), msg.get("v")
            if c == "scene":
                eng.set_scene(v)
            elif c == "size":
                eng.set_size(*v)
            elif c == "beat":
                eng.set_beat(v)
            elif c == "paused":
                eng.set_paused(v)
            elif c == "stop":
                break
        stop.set()
    threading.Thread(target=reader, daemon=True).start()
    last, t_st = 0, 0.0
    while not stop.is_set():
        fr = eng.frame()
        if fr is not None and fr[3] != last:
            data, w, h, n = fr
            last = n
            try:
                send(b"F", struct.pack("<III", w, h, n) + data)
            except OSError:
                break
        now = time.monotonic()
        if now - t_st > 1.0:
            t_st = now
            st = dict(eng.status, soft=bool(getattr(eng, "soft", True)))
            try:
                send(b"S", json.dumps(st, ensure_ascii=False).encode("utf-8"))
            except OSError:
                break
        time.sleep(0.008)
    eng.stop()
    return 0


# ───────────────────────── клиент в программе ─────────────────────────
class EngineProcess:
    def __init__(self, app_root, python, gpu="auto", log=None):
        self.root = str(app_root)
        self.python = python
        self.gpu = gpu
        self.log = log or (lambda *a: None)
        self.status = {"ready": False, "pipe": "", "renderer": "", "fps": 0, "dancers": [], "error": ""}
        self.soft = True
        self._frame = None
        self._lock = threading.Lock()
        self._wlock = threading.Lock()
        self.proc = None
        self._size = None
        self._paused = None
        self._scene = None

    def start(self):
        script = str(Path(__file__).resolve())
        self.proc = subprocess.Popen([self.python, "-u", script, self.root, self.gpu],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, creationflags=NO_WINDOW,
                                     cwd=self.root)
        threading.Thread(target=self._read, daemon=True, name="scene3d-out").start()
        threading.Thread(target=self._read_err, daemon=True, name="scene3d-err").start()
        if self._size is not None:
            self._send("size", list(self._size))
        if self._paused is not None:
            self._send("paused", self._paused)
        if self._scene is not None:
            self._send("scene", self._scene)

    def is_alive(self):
        return self.proc is not None and self.proc.poll() is None

    def _send(self, cmd, v):
        if not self.is_alive():
            return
        line = (json.dumps({"cmd": cmd, "v": v}, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with self._wlock:
                self.proc.stdin.write(line)
                self.proc.stdin.flush()
        except OSError:
            pass

    def _read(self):
        f = self.proc.stdout
        while True:
            hdr = f.read(5)
            if len(hdr) < 5:
                break
            n, kind = struct.unpack("<Ic", hdr)
            data = f.read(n)
            if len(data) < n:
                break
            if kind == b"F":
                w, h, k = struct.unpack("<III", data[:12])
                with self._lock:
                    self._frame = (data[12:], w, h, k)
            elif kind == b"L":
                self.log(data.decode("utf-8", "replace"))
            elif kind == b"S":
                try:
                    st = json.loads(data.decode("utf-8"))
                    self.soft = bool(st.pop("soft", True))
                    self.status.update(st)
                except ValueError:
                    pass
        code = self.proc.poll()
        if not self.status.get("error"):
            self.status["error"] = f"3D-движок остановился (код {code})"

    def _read_err(self):
        tail = []
        for raw in self.proc.stderr:
            line = raw.decode("utf-8", "replace").rstrip()
            if line and "inotify" not in line and "/dev/input" not in line:
                tail = (tail + [line])[-20:]
        if self.proc.poll() not in (0, None) and tail:
            self.log("✗ 3D-движок: " + " | ".join(tail[-4:]))

    # то же, что у Engine
    def set_scene(self, scene):
        self._scene = scene
        self._send("scene", scene)

    def set_size(self, w, h):
        s = (max(64, int(w)), max(64, int(h)))
        if s != self._size:
            self._size = s
            self._send("size", list(s))

    def set_beat(self, st):
        self._send("beat", st)

    def set_paused(self, on):
        on = bool(on)
        if on != self._paused:
            self._paused = on
            self._send("paused", on)

    def frame(self):
        with self._lock:
            return self._frame

    def stop(self, wait=3.0):
        if self.proc is None:
            return
        self._send("stop", None)
        try:
            self.proc.wait(wait)
        except subprocess.TimeoutExpired:
            self.proc.kill()


if __name__ == "__main__":
    sys.exit(_server(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "auto"))
