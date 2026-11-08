"""runtime3d.py  v2.2.0 — отдельный Python для 3D-движка (Panda3D)

Panda3D собрана для Python 3.8…3.14. Если программа запущена на более новом
Python (3.15) или Panda3D в него не ставится — 3D считается в отдельном
процессе на компактном Python 3.13 с python.org (embeddable, ~11 МБ), который
лежит в папке программы .runtime/python, туда же pip, numpy и panda3d (~70 МБ).
Всё ставится само, один раз, только рядом с программой — системные Python
не трогаются.

Журнал:
v2.2.0: только .runtime/ рядом с программой: чужие Python и pip --user не используются
v2.1.0: первая версия
"""
import io
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

FALLBACK_VER = "3.13.17"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
PKGS = ("numpy>=1.24", "panda3d>=1.10.14")


def _run(args, timeout=900):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          creationflags=NO_WINDOW, encoding="utf-8", errors="replace")


def has_panda(py):
    """В этом Python есть numpy и panda3d?"""
    try:
        r = _run([py, "-c", "import numpy, panda3d.core; print('ok')"], timeout=60)
        return r.returncode == 0 and "ok" in r.stdout
    except (OSError, subprocess.SubprocessError):
        return False


def candidates():
    """Установленные Python 3.10…3.14 (py-лаунчер), свой .runtime — первым."""
    out = []
    if sys.platform == "win32":
        try:
            r = _run(["py", "-0p"], timeout=30)
            for line in r.stdout.splitlines():
                m = re.search(r"-V:3\.(\d+)\S*\s+\*?\s*(.+python(w)?\.exe)", line, re.I) or \
                    re.search(r"-3\.(\d+)\S*\s+\*?\s*(.+python(w)?\.exe)", line, re.I)
                if m and 10 <= int(m.group(1)) <= 14:
                    p = m.group(2).strip()
                    if p.lower().endswith("pythonw.exe"):
                        p = p[:-11] + "python.exe"
                    out.append(p)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        for v in range(14, 9, -1):
            p = shutil.which(f"python3.{v}")
            if p:
                out.append(p)
    return out


def _latest_313(log):
    try:
        with urllib.request.urlopen("https://www.python.org/ftp/python/", timeout=30) as r:
            vers = sorted(set(re.findall(r'href="3\.13\.(\d+)/"', r.read().decode("utf-8", "replace"))),
                          key=int, reverse=True)
        for v in vers[:4]:
            url = f"https://www.python.org/ftp/python/3.13.{v}/python-3.13.{v}-embed-amd64.zip"
            try:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=30):
                    return f"3.13.{v}"
            except Exception:                               # noqa: BLE001
                continue
    except Exception as e:                                  # noqa: BLE001
        log(f"⚠ список версий python.org не получен ({e}) — беру {FALLBACK_VER}")
    return FALLBACK_VER


def _download(url, log, progress=None, lo=0, hi=100):
    req = urllib.request.Request(url, headers={"User-Agent": "DeskDancer"})
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                total = int(r.headers.get("Content-Length") or 0)
                buf = io.BytesIO()
                while True:
                    ch = r.read(65536)
                    if not ch:
                        break
                    buf.write(ch)
                    if progress and total:
                        progress(lo + (hi - lo) * buf.tell() // total)
                data = buf.getvalue()
                if total and len(data) != total:
                    raise OSError(f"скачано {len(data)} из {total} байт")
                return data
        except Exception as e:                              # noqa: BLE001
            last = e
    raise RuntimeError(f"не скачалось {url}: {last}")


def install_embedded(root, log, progress=None):
    """Компактный Python 3.13 в root/.runtime/python + pip + numpy + panda3d."""
    if sys.platform != "win32":
        raise RuntimeError("компактный Python с python.org — только для Windows")
    dst = Path(root) / ".runtime" / "python"
    py = dst / "python.exe"
    if not py.exists():
        ver = _latest_313(log)
        log(f"⏳ скачиваю Python {ver} для 3D-движка (~10 МБ)…")
        data = _download(f"https://www.python.org/ftp/python/{ver}/python-{ver}-embed-amd64.zip",
                         log, progress, 0, 20)
        tmp = dst.with_name("python.tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(tmp)
        for pth in tmp.glob("python3*._pth"):            # включить site-packages (нужно для pip)
            txt = pth.read_text(encoding="utf-8")
            txt = txt.replace("#import site", "import site")
            if "Lib\\site-packages" not in txt:
                txt += "\nLib\\site-packages\n"
            pth.write_text(txt, encoding="utf-8")
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        os.replace(tmp, dst)
        log(f"✓ Python {ver} распакован: {dst}")
    if _run([str(py), "-m", "pip", "--version"], timeout=120).returncode != 0:
        log("⏳ ставлю pip…")
        gp = _download("https://bootstrap.pypa.io/get-pip.py", log, progress, 20, 30)
        f = dst / "get-pip.py"
        f.write_bytes(gp)
        r = _run([str(py), str(f), "--no-warn-script-location", "--no-cache-dir"], timeout=600)
        if r.returncode != 0:
            raise RuntimeError("pip не ставится: " + (r.stderr or r.stdout)[-300:])
    if progress:
        progress(40)
    log("⏳ ставлю numpy и panda3d в Python для 3D (~70 МБ, один раз)…")
    r = _run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir",
              "--no-warn-script-location", *PKGS], timeout=1800)
    if r.returncode != 0:
        raise RuntimeError("numpy / panda3d не ставятся: " + (r.stderr or r.stdout)[-400:])
    if progress:
        progress(100)
    return str(py)


def find_or_install(root, saved, log, progress=None):
    """Путь к python.exe с panda3d — только в папке программы (.runtime/python).
    Не Windows (разработка) — подходящий Python, где panda3d уже стоит."""
    root = Path(root)
    emb = root / ".runtime" / "python" / "python.exe"
    if emb.exists() and has_panda(str(emb)):
        return str(emb)
    if sys.platform != "win32":
        for py in candidates():
            if has_panda(py):
                log(f"✓ 3D-движок (не Windows): {py}")
                return py
        raise RuntimeError("нет Python 3.10–3.14 с panda3d")
    return install_embedded(root, log, progress)
