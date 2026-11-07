"""gh_update — обновление программы из приватного репозитория GitHub.

ОБЩИЙ модуль для всех наших приложений (только стандартная библиотека):
вставить файл в проект, задать UpdateTarget — и всё работает одинаково.

Откуда берётся версия. В репозитории лежит release/<имя>_vX.Y.Z.zip
(правило выдачи: внутри архива папка <имя>/ со всеми файлами проекта).
Программа спрашивает GitHub API, какой архив лежит в release/ нужной
ветки, сравнивает номер со своей версией, скачивает, сверяет контрольную
сумму (git blob sha1 из ответа GitHub), ставит поверх и перезапускается.

Доступ — токен GitHub «только чтение» (fine-grained PAT, Contents: Read)
на выбранные репозитории. Хранится в настройках программы.

Что делает install():
  * распаковывает во временную папку и проверяет, что внутри — та самая
    программа (есть главный файл и номер версии совпадает с именем архива);
  * ставит новые файлы поверх старых;
  * стирает то, что ставил сам в прошлый раз и чего в новой версии нет
    (удалённые и разбитые на части модули, их .pyc, опустевшие папки).
    Что ставил — помнит список MANIFEST в папке программы; списка ещё нет
    (первое обновление этим модулем) — старый код (CODE_EXT) в папках,
    которые есть в архиве (корень — нет: там могут лежать свои скрипты),
    мимо папок данных (KEEP_DIRS);
  * НИКОГДА не трогает и не перезаписывает настройки, журналы, записи,
    скачанное, DLL и EXE (KEEP — маски, KEEP_DIRS — папки);
  * при ошибке посреди копирования возвращает старые файлы (временная
    копия вне папки программы; папки backup/ больше нет — старая
    удаляется).

Обновляется только программа на Python (исходники). Собранный exe не
обновляется (★ 1.4.0): GitHub exe не собирает, Releases не нужны.

Перезапуск: restart() запускает программу заново с ключом
--after-update <pid> и закрывает текущую. Новая копия в самом начале зовёт
wait_previous(sys.argv) — ждёт, пока старая завершится (иначе защита от
второго запуска приняла бы её за «уже запущено»).

1.4.3: две ветки «1.4.2» сведены в одну: f-строки (Python 3.12+) и
замена файла при установке и запись MANIFEST с повтором, если файл на миг
занят (антивирус, индексатор: WinError 5 / 32) — раньше всё обновление
откатывалось с «не удалось заменить файлы»; drop_leftovers: в журнале снова
видно, что стёрто (строка склеивалась неверно); gone понимает маски
(«CHANGELOG_v*.md») — старые файлы прежних версий в корне программы.

1.4.2: только Python 3.12+ — строки на f-строках, без «# -*- coding».
Поведение не менялось. (Две ветки «1.4.1» — SmartMon и остальные
проекты — сведены в одну.)

1.4.1: свои файлы пользователя не стираются и без списка MANIFEST: папки
tools/ и modules/ — всегда свои (user_dirs по умолчанию), копия из git
(.git рядом) старый код не чистит, список, который не прочитался (занят), —
не повод для чистки «по архиву»; запрет GitHub из-за лимита запросов —
«лимит», а не «токен не видит репозиторий»; новая версия вышла, пока
окно было открыто, — понятная ошибка вместо 404; gh_update_qt: busy() —
только скачивание / установка (во время проверки версии окно закрывается).

1.4.0: убрано обновление собранного exe — только Python. Нет больше
check_exe / latest_exe / download_exe / stage_exe / launch_swap /
swap_failed / finish_exe_update и помощника .gh_update_swap.bat; GitHub
Actions exe не собирает (build_exe.yml удалён), GitHub Releases не нужны.
check() у собранного exe — понятная ошибка вместо обновления.

Раньше (1.0–1.3.3) — в истории git репозитория SmartMon.

"""
import fnmatch
import hashlib
import http.client
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field

VERSION = "1.4.3"
API = "https://api.github.com"
TIMEOUT = 30

# что не трогаем при обновлении никогда (маски путей относительно папки программы)
KEEP_DEFAULT = (
    "*.json", "*.log", "*.log.*", "*.bak*", "*.tmp*",
    "libs/*", "logs/*", ".runtime/*", "backup/*", "firmware/*",
    "cloud_history/*", "*.exe", "*.dll", "release/*", ".git/*",
)

# ★ 1.2.0: список файлов, поставленных обновлением (по нему в следующий раз
# стирается то, чего в новой версии нет)
MANIFEST = ".gh_update_files.txt"

# ★ 1.2.0: без списка (первое обновление этим модулем) — что из старых
# файлов стирается, если его нет в новой версии, —
# только код (настройки, журналы, записи, DLL — никогда)
CODE_EXT = (".py", ".pyw", ".pyc", ".pyo", ".bat", ".cmd", ".spec", ".md",
            ".qss")
# папки данных и чужого кода: туда чистка не заходит ни на каком уровне
KEEP_DIRS = frozenset((
    "logs", "libs", "rec", "archive", "bin", "sdk", ".runtime", "firmware",
    "cloud_history", "release", "backup", ".git", ".smartmon_parts", "build",
    "dist", "venv", ".venv", "env", "site-packages", "lib", "scripts",
    "node_modules", "downloads", "download", ".gh_update_new",
    ".gh_update_old"))


# ★ 1.4.1: свои папки пользователя — без списка MANIFEST их не чистим никогда
USER_DIRS = ("modules", "tools")


class UpdateError(Exception):
    """Ошибка обновления; текст — по-русски, для пользователя.
    code — HTTP-код ответа GitHub (0 — не HTTP)."""

    def __init__(self, text, code=0):
        super().__init__(text)
        self.code = code


@dataclass
class UpdateTarget:
    """Что и откуда обновлять — своё у каждого приложения."""
    owner: str                    # romzespra-collab
    repo: str                     # Smart_BMS
    name: str                     # smart_bms — префикс архива и папка внутри
    current: str                  # текущая версия программы, «4.88»
    app_dir: str                  # куда ставить (папка программы)
    main_file: str                # главный файл внутри архива: Smart_BMS.pyw
    subdir: str = ""              # если в репозитории проект лежит в подпапке
    branch: str = "main"
    changelog: str = ""           # путь к CHANGELOG в репозитории — «Что нового»
    keep: tuple = field(default_factory=lambda: KEEP_DEFAULT)
    version_files: tuple = ()     # где ещё искать VERSION = "…" в архиве
    where: str = "Настройки → 🔄 Обновление"   # где вкладка (для инструкции)
    removed: list = field(default_factory=list)  # ★ 1.2.0: что стёрла install()
    # ★ 1.2.1/1.3.2: свои файлы пользователя (modules/ …) — без списка не
    # чистить; ★ 1.4.1: tools/ и modules/ — по умолчанию у всех
    user_dirs: tuple = USER_DIRS
    own: tuple = ()               # ★ 1.3.3 (из WinHub 1.2.1): маски своих файлов — ставим, но не стираем


@dataclass
class Release:
    version: str
    path: str                     # release/smart_bms_v4.89.zip
    sha: str                      # git blob sha1 (сверка после скачивания)
    size: int
    url: str = ""                 # download_url (raw.githubusercontent.com)
    kind: str = "src"             # всегда src — архив исходников (★ 1.4.0: exe нет)


# ---------------- версии ----------------

def vtuple(v):
    """«4.88» / «v6.63.44» -> (4, 88) / (6, 63, 44); мусор -> ()."""
    nums = re.findall(r"\d+", str(v or ""))
    return tuple(int(x) for x in nums)


def newer(a, b):
    """a новее b? (сравнение по числам; «4.9» < «4.10»)."""
    ta, tb = vtuple(a), vtuple(b)
    n = max(len(ta), len(tb))
    return ta + (0,) * (n - len(ta)) > tb + (0,) * (n - len(tb))


# ---------------- GitHub ----------------

def _ctx():
    if os.environ.get("SSL_CERT_FILE"):           # свой корневой (прокси/фирма)
        return ssl.create_default_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:                                  # noqa: BLE001
        return ssl.create_default_context()


def _req(url, token, accept="application/vnd.github+json", headers=None):
    h = {"Accept": accept, "User-Agent": "gh_update/" + VERSION,
         "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = "Bearer " + token.strip()
    if headers:
        h.update(headers)
    return urllib.request.Request(url, headers=h)


def _open(url, token, accept="application/vnd.github+json", timeout=TIMEOUT,
          headers=None):
    try:
        return urllib.request.urlopen(_req(url, token, accept, headers),
                                      timeout=timeout, context=_ctx())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise UpdateError("токен GitHub не подошёл (401): проверь, что он "
                              "вставлен целиком и не истёк", 401) from e
        if e.code == 403 and (e.headers or {}).get(
                "X-RateLimit-Remaining") == "0":
            # ★ 1.4.1: лимит запросов — не «нет доступа» (без разбора токена)
            raise UpdateError("GitHub: исчерпан лимит запросов — попробуй "
                              "через час", 429) from e
        if e.code == 403:
            raise UpdateError("GitHub не дал доступ (403): у токена нет права "
                              "Contents: Read на этот репозиторий, или лимит "
                              "запросов — попробуй позже", 403) from e
        if e.code == 404:
            raise UpdateError("не найдено (404): репозиторий/ветка/папка release "
                              "не те, или токен не видит приватный репозиторий",
                              404) from e
        raise UpdateError(f"GitHub ответил {e.code}", e.code) from e
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"нет связи с GitHub ({getattr(e, 'reason', e)})") from e


def latest(t, token):
    """Последний архив в release/ ветки -> Release или None (архивов нет)."""
    folder = (t.subdir.strip("/") + "/release") if t.subdir else "release"
    url = f"{API}/repos/{t.owner}/{t.repo}/contents/{urllib.parse.quote(folder)}?ref={urllib.parse.quote(t.branch)}"
    try:
        with _open(url, token) as r:
            items = json.loads(r.read().decode("utf-8"))
    except UpdateError as e:
        if e.code in (403, 404):
            raise UpdateError(diagnose(t, token, folder), e.code) from e
        raise
    except (OSError, ValueError, http.client.HTTPException) as e:    # ★ 1.3.3: обрыв при чтении ответа
        raise UpdateError(f"ответ GitHub не дочитан: {e}") from e
    if not isinstance(items, list):
        raise UpdateError("GitHub вернул не список файлов папки release")
    pat = re.compile(rf"^{re.escape(t.name)}_v?(\d+(?:\.\d+)*)\.zip$", re.I)
    best = None
    for it in items:
        m = pat.match(str(it.get("name") or ""))
        if not m or it.get("type") != "file":
            continue
        rel = Release(m.group(1), it["path"], it.get("sha") or "",
                      int(it.get("size") or 0), it.get("download_url") or "")
        if best is None or newer(rel.version, best.version):
            best = rel
    return best


def _code(url, token):
    """HTTP-код запроса (200/401/403/404…), 0 — нет связи."""
    try:
        with _open(url, token):
            return 200
    except UpdateError as e:
        return e.code


def diagnose(t, token, folder="release"):
    """После 403/404: по шагам выяснить, ЧТО не так, и сказать, как
    исправить (GitHub на приватный репозиторий без доступа отвечает 404 —
    по одному коду не понять)."""
    q = urllib.parse.quote
    full = f"{t.owner}/{t.repo}"
    c = _code(f"{API}/user", token)
    if c == 401:
        return ("токен GitHub недействителен (удалён, истёк или вставлен не "
                "целиком) — сделайте новый, кнопка «?»")
    c = _code(f"{API}/repos/{full}", token)
    if c in (403, 404):
        return (f"токен не видит репозиторий {full}. На GitHub: токен → Edit → "
                f"Repository access → Only select repositories → добавьте {full} "
                f"(и Resource owner — {t.owner})")
    if c != 200:
        return f"GitHub не отвечает на запрос репозитория (код {c})"
    c = _code(f"{API}/repos/{full}/branches/{q(t.branch)}", token)
    if c == 404:
        return (f"в репозитории {full} нет ветки «{t.branch}» — впишите в поле «Ветка» "
                "правильную (обычно main)")
    c = _code(f"{API}/repos/{full}/contents/?ref={q(t.branch)}", token)
    if c in (403, 404):
        return ("у токена нет права читать файлы. На GitHub: токен → Edit → "
                "Permissions → Repositories → Add permissions → Contents → "
                "Read-only → Update")
    return (f"в ветке «{t.branch}» нет папки {folder} с архивами программы")


def check(t, token):
    """-> (Release, есть_новее). Release=None — архивов в release/ нет.
    ★ 1.4.0: обновляется только Python; собранный exe — не обновляется."""
    if is_frozen():
        raise UpdateError("собранный exe не обновляется — обновление только "
                          "для программы на Python (запуск .pyw)")
    rel = latest(t, token)
    return rel, bool(rel and newer(rel.version, t.current))


# ---------------- как запущена программа ----------------

def run_kind():
    """★ 1.4.0: обновляется только Python (исходники) — всегда "python"."""
    return "python"


def run_kind_text():
    return "Python (исходники) — обновляется архивом исходников"


def whats_new(t, token, upto=None, limit=6000):
    """Разделы CHANGELOG новее установленной версии (до upto включительно).
    Раздел начинается строкой «4.90:» или «6.63.45 (= полная 4.90):».
    -> текст или "" (нет файла/разделов — не ошибка)."""
    if not t.changelog:
        return ""
    url = f"{API}/repos/{t.owner}/{t.repo}/contents/{urllib.parse.quote(t.changelog)}?ref={urllib.parse.quote(t.branch)}"
    try:
        with _open(url, token, accept="application/vnd.github.raw") as r:
            text = r.read().decode("utf-8", errors="replace")
    except (UpdateError, OSError, http.client.HTTPException):    # ★ 1.3.3: журнал — не повод для ошибки
        return ""
    return changelog_since(text, t.current, upto, limit)


def changelog_since(text, current, upto=None, limit=6000):
    # «4.90:», «6.63.45 (= полная 4.90):», «v1.2.3: текст», «## v1.2.3 — …»,
    # «# v1.2.3: …» (журнал в шапке .pyw), «Версия 1.2.3 — …»
    # одно число («v436:») — только с «v»/«Версия» впереди
    head = re.compile(r"^(?:#{1,4}\s*|\[)?(?:(?:[vV]|(?:[Вв]ерсия|[Ии]зменения(?:\s+в)?)\s+v?)(\d+(?:\.\d+)*)|"
                      r"(\d+(?:\.\d+)+))\b"
                      r"(?:[^\n]*:\s*$|\]?\s*(?:[:—–(-]|\s*$))")
    out, take = [], False
    stop = re.compile(r'^\s*("""|\'\'\'|import |from \S+ import |def |class )')
    for line in text.splitlines():
        if take and stop.match(line):          # журнал в шапке .pyw — дальше код
            break
        m = head.match(line)
        if m:
            v = m.group(1) or m.group(2)
            take = newer(v, current) and (upto is None or not newer(v, upto))
        if take:
            out.append(line.rstrip())
    res = "\n".join(out).strip()
    return res[:limit] + ("\n…" if len(res) > limit else "")


def _blob_sha1(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


DL_TRIES = 12          # попыток на источник; 3 подряд без прибавки — следующий


def _fetch(url, token, accept, buf, total, progress):
    """Одна попытка: дочитать url в buf с места len(buf) (Range).
    -> (total, прибавилось байт). Обрыв посреди — не ошибка: вызывающий
    докачает следующей попыткой."""
    got0 = len(buf)
    hdr = {"Range": f"bytes={got0}-"} if got0 else None
    with _open(url, token, accept=accept, timeout=120, headers=hdr) as r:
        st = int(getattr(r, "status", 0) or getattr(r, "code", 0) or 200)
        if got0 and st != 206:
            del buf[:]                         # Range не понят — с начала
            got0 = 0
        if not total:
            n = int(r.headers.get("Content-Length") or 0)
            total = n + got0 if n else 0
        try:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                buf += chunk
                if progress:
                    progress(len(buf), total)
        except (OSError, ValueError, http.client.HTTPException):
            pass                               # обрыв посреди — докачаем
    return total, len(buf) - got0


def download(t, token, rel, progress=None):
    """Скачать архив во временный файл, сверить размер и sha. -> путь.
    ★ 1.1.2: по ссылке на файл (у API ответ рвётся через ~10 с), обрыв —
    докачка с места обрыва."""
    api = f"{API}/repos/{t.owner}/{t.repo}/contents/{urllib.parse.quote(rel.path)}?ref={urllib.parse.quote(t.branch)}"
    url = rel.url
    fresh = None
    try:                                       # ссылка живёт минуты — свежая
        fresh = latest(t, token)
        if fresh is not None and fresh.path == rel.path and fresh.url:
            url = fresh.url
    except Exception:                          # noqa: BLE001
        pass
    if fresh is not None and fresh.path != rel.path \
            and newer(fresh.version, rel.version):
        # ★ 1.4.1: пока окно было открыто, вышла ещё новее — прежнего архива
        # в release/ уже нет (лежит только последний): было 404 и совет
        # про токен
        raise UpdateError(f"на GitHub уже версия {fresh.version} — нажми «Проверить "
                          "сейчас»")
    srcs = [(url, "application/octet-stream")] if url else []
    srcs.append((api, "application/vnd.github.raw"))
    buf = bytearray()
    total = rel.size or 0
    last = None
    for src, accept in srcs:
        idle = 0
        for _ in range(DL_TRIES):
            try:
                total, add = _fetch(src, token, accept, buf, total, progress)
            except UpdateError as e:
                last = e
                if len(buf) == 0 and e.code:   # ссылка не открылась вовсе
                    break
                add = 0
            except (OSError, ValueError, http.client.HTTPException) as e:
                last = UpdateError(f"нет связи с GitHub ({e})")
                add = 0
            if total and len(buf) >= total:
                break
            idle = 0 if add > 0 else idle + 1
            if idle >= 3:
                break
            time.sleep(1.0)
        if total and len(buf) >= total:
            break
    data = bytes(buf)
    if rel.size and len(data) != rel.size:
        if not data and last is not None:
            raise last
        raise UpdateError(f"архив скачался не целиком ({len(data)} из {rel.size} байт)")
    if rel.sha and _blob_sha1(data) != rel.sha:
        raise UpdateError("контрольная сумма архива не совпала — "
                          "скачивание испорчено, обновление отменено")
    fd, path = tempfile.mkstemp(prefix=t.name + "_", suffix=".zip")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path


# ---------------- установка ----------------

def _kept(rel_path, keep):
    p = rel_path.replace("\\", "/")
    return any(fnmatch.fnmatch(p, k) for k in keep)


def _safe(root, rel):
    dst = os.path.normpath(os.path.join(root, rel))
    if not (dst == root or dst.startswith(root + os.sep)):
        raise UpdateError(f"в архиве опасный путь: {rel}")
    return dst


def _keep_dir(name):
    return name.lower() in KEEP_DIRS


def stale_files(app_dir, new_files, keep=KEEP_DEFAULT, user_dirs=()):
    """★ 1.2.0: старые файлы кода, которых нет в новой версии -> список
    путей (относительно app_dir, через «/»). Только когда списка MANIFEST
    ещё нет. Смотрим только папки, которые есть в архиве (app/, tests/ …):
    корень (свои скрипты рядом с программой), папки данных (KEEP_DIRS) и
    виртуальные окружения (pyvenv.cfg) — мимо."""
    mine = set(d.strip("/\\").replace("\\", "/").lower()
               for d in tuple(user_dirs) + USER_DIRS)
    app_dir = os.path.abspath(app_dir)
    # ★ 1.4.1: копия из git — тут свои незакоммиченные модули, не чистим
    if os.path.exists(os.path.join(app_dir, ".git")):
        return []
    new = set(f.replace("\\", "/") for f in new_files)
    new_nc = set(os.path.normcase(f) for f in new)
    out = []
    tops = sorted(set(f.split("/", 1)[0] for f in new if "/" in f))
    for top in tops:
        root = os.path.join(app_dir, top)
        if _keep_dir(top) or top.lower() in mine or not os.path.isdir(root):
            continue
        for dp, dns, fns in os.walk(root):
            if "pyvenv.cfg" in fns:
                dns[:] = []
                continue
            dns[:] = [d for d in dns if not _keep_dir(d)]
            for fn in fns:
                rel = os.path.relpath(os.path.join(dp, fn),
                                      app_dir).replace(os.sep, "/")
                if rel in new or os.path.normcase(rel) in new_nc or _kept(rel, keep):
                    continue
                if os.path.splitext(fn)[1].lower() in CODE_EXT:
                    out.append(rel)
    return out


def _replace(src, dst, tries=6):
    """★ 1.4.3: os.replace с повтором: файл на миг держит антивирус."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.1 * (i + 1))


def read_manifest(app_dir):
    """Что поставило прошлое обновление -> set или None (списка нет).
    ★ 1.4.1: список есть, но не читается (занят антивирусом) — пустой set:
    чистить нечего (раньше None — и чистка шла «по архиву»)."""
    try:
        with open(os.path.join(app_dir, MANIFEST), encoding="utf-8") as fh:
            return set(x.strip().replace("\\", "/") for x in fh
                       if x.strip() and not x.startswith("#"))
    except FileNotFoundError:
        return None
    except OSError:
        return set()


def write_manifest(app_dir, files):
    tmp = os.path.join(app_dir, MANIFEST + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("# gh_update: файлы, поставленные обновлением (не править)\n")
        fh.write("\n".join(sorted(files)) + "\n")
    _replace(tmp, os.path.join(app_dir, MANIFEST))


_UNREAD = object()


def _drop_stale(app_dir, files, installed, keep, log, user_dirs=(), prev=_UNREAD):
    """Стереть старое -> список стёртого. Затем — новый список MANIFEST."""
    if prev is _UNREAD:                       # ★ 1.3.3: prev — свой список, прочитан до установки
        prev = read_manifest(app_dir)
    new = set(f.replace("\\", "/") for f in files)
    if prev is None:
        cand = stale_files(app_dir, files, keep, user_dirs)
    else:
        new_nc = set(os.path.normcase(r) for r in new)
        cand = sorted(r for r in prev - new
                      if os.path.normcase(r) not in new_nc and not _kept(r, keep))
    removed, dirs = [], set()
    for rel in cand:
        try:
            dst = _safe(app_dir, rel)
            if not os.path.isfile(dst):
                continue
            os.remove(dst)
        except (OSError, UpdateError) as exc:
            log(f"обновление: не стёр {rel}: {exc}")
            continue
        removed.append(rel)
        dirs.add(os.path.dirname(dst))
        # .pyc стёртого модуля
        stem, ext = os.path.splitext(os.path.basename(rel))
        pyc = os.path.join(os.path.dirname(dst), "__pycache__")
        if ext.lower() in (".py", ".pyw") and os.path.isdir(pyc):
            for x in os.listdir(pyc):
                if x.split(".", 1)[0] == stem and x.endswith(".pyc"):
                    try:
                        os.remove(os.path.join(pyc, x))
                        dirs.add(pyc)
                    except OSError:
                        pass
    # опустевшие папки — снизу вверх, до папки программы
    for d in sorted(dirs, key=len, reverse=True):
        while d != app_dir and d.startswith(app_dir + os.sep):
            try:
                os.rmdir(d)                        # только пустую
            except OSError:
                break
            d = os.path.dirname(d)
    try:
        write_manifest(app_dir, installed)
    except OSError as exc:
        log(f"обновление: список файлов не записан: {exc}")
    return removed


def drop_old_backup(app_dir, log=None):
    """★ 1.2.0: папка backup/ прежних обновлений (backup/v<версия>/…) —
    удалить. Только если в ней одни папки «v…» (чужое — не трогаем)."""
    b = os.path.join(os.path.abspath(app_dir), "backup")
    if not os.path.isdir(b):
        return False
    try:
        items = os.listdir(b)
        if any(not (re.fullmatch(r"v\d+(?:\.\d+)*", x, re.I)      # ★ 1.3.3: только v<цифры>
                    and os.path.isdir(os.path.join(b, x))) for x in items):
            return False
        shutil.rmtree(b)
    except OSError as e:
        if log:
            log(f"обновление: старую папку backup не удалить: {e}")
        return False
    if log:
        log("обновление: старая папка backup удалена (резервных копий "
            "больше нет)")
    return True


def _is_mask(fn):
    return any(ch in fn for ch in "*?[")


def _gone_files(app_dir, d, fn):
    """★ 1.4.3: файл из gone -> пути. Маска («CHANGELOG_v*.md») — только файлы
    этой папки (без подпапок), не меньше 3 обычных букв, мимо KEEP_DEFAULT
    (настройки, журналы, exe, dll — никогда)."""
    folder = os.path.join(app_dir, d)
    if not _is_mask(fn):
        return [os.path.join(folder, fn)]
    if len(re.sub(r"[*?\[\]]", "", fn)) < 3 or not os.path.isdir(folder):
        return []
    out = []
    for x in sorted(os.listdir(folder)):
        rel = os.path.join(d, x).replace(os.sep, "/")
        if (fnmatch.fnmatch(x.lower(), fn.lower()) and not _kept(rel, KEEP_DEFAULT)
                and os.path.isfile(os.path.join(folder, x))):
            out.append(os.path.join(folder, x))
    return out


def drop_leftovers(app_dir, gone=(), log=None):
    """★ 1.2.0: разово при запуске — то, что оставили обновления до 1.2.0:
    папка backup/ и модули, удалённые из программы (gone — пути вида
    «app/quick_fill.py»; заодно их .pyc в __pycache__; ★ 1.4.3 — и маски
    «CHANGELOG_v*.md», «README.txt»). -> что стёрто."""
    app_dir = os.path.abspath(app_dir)
    out = []
    for rel in gone:
        d, fn = os.path.split(rel.replace("/", os.sep))
        stem = os.path.splitext(fn)[0]
        cands = _gone_files(app_dir, d, fn)
        pyc = os.path.join(app_dir, d, "__pycache__")
        if os.path.isdir(pyc) and not _is_mask(fn):
            cands += [os.path.join(pyc, x) for x in os.listdir(pyc)
                      if x.split(".", 1)[0] == stem and x.endswith(".pyc")]
        for c in cands:
            if os.path.isfile(c):
                try:
                    os.remove(c)
                    out.append(os.path.relpath(c, app_dir))
                except OSError:
                    pass
    if out and log:
        log("обновление: стёрт старый код, оставшийся от прежних версий: "
            + ", ".join(x for x in out if not x.endswith(".pyc")))
    if drop_old_backup(app_dir, log):
        out.append("backup")
    return out


def install(t, zip_path, rel_version, log=None):
    """Поставить архив поверх t.app_dir. -> список заменённых файлов.
    ★ 1.2.0: старый код, которого нет в архиве, стирается (stale_files);
    t.removed — что стёрто."""
    log = log or (lambda *_a: None)
    app_dir = os.path.abspath(t.app_dir)
    stage = tempfile.mkdtemp(prefix=t.name + "_upd_")
    bdir = None
    try:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            if bad:
                raise UpdateError(f"архив повреждён: {bad}")
            names = [n for n in z.namelist() if not n.endswith("/")]
            prefix = t.name + "/"
            if names and all(n.startswith(prefix) for n in names):
                strip = len(prefix)
            else:
                strip = 0
            files = []
            for n in names:
                rel = n[strip:]
                if not rel or "__pycache__" in rel:
                    continue
                dst = _safe(stage, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(n) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)
                files.append(rel)
        if t.main_file not in files:
            raise UpdateError(f"в архиве нет {t.main_file} — это не та программа")
        # номер версии внутри архива должен совпасть с именем архива
        found = ""
        for cand in tuple(t.version_files) + ("app/version.py", "version.py",
                                               "VERSION", t.main_file):
            pth = os.path.join(stage, cand)
            if os.path.exists(pth):
                with open(pth, encoding="utf-8", errors="replace") as fh:
                    txt = fh.read()
                if os.path.basename(cand) == "VERSION":
                    m = re.match(r"\s*v?(\d+(?:\.\d+)*)\s*$", txt)
                else:
                    m = re.search(r'(?:APP_)?(?:VERSION|__version__)\s*=\s*'
                                  r'["\']v?(\d+(?:\.\d+)*)', txt)
                if m:
                    found = m.group(1)
                    break
        if found and vtuple(found) != vtuple(rel_version):
            raise UpdateError(f"внутри архива версия {found}, а не {rel_version} — обновление "
                              "отменено")
        # ★ 1.2.0: копия заменяемого — только на случай отката, во временной
        # папке (не в папке программы), после установки удаляется
        bdir = tempfile.mkdtemp(prefix=t.name + "_old_")
        # ★ 1.3.3: MANIFEST из архива не ставится (он — для модуля 1.2.0);
        # свой список читаем до установки
        prev = read_manifest(app_dir)
        todo = [f for f in files if not _kept(f, t.keep) and f != MANIFEST]
        replaced = []
        try:
            for rel in todo:
                dst = _safe(app_dir, rel)
                if os.path.exists(dst):
                    b = _safe(bdir, rel)
                    os.makedirs(os.path.dirname(b), exist_ok=True)
                    shutil.copy2(dst, b)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                tmp = dst + ".upd"
                shutil.copy2(os.path.join(stage, rel), tmp)
                _replace(tmp, dst)
                replaced.append(rel)
        except Exception as exc:                       # noqa: BLE001
            log(f"обновление: ошибка ({exc}) — возвращаю старые файлы")
            try:
                os.remove(tmp)                         # ★ 1.3.3: недокопированный *.upd не оставлять
            except (OSError, NameError):
                pass
            failed = []
            for rel in replaced:
                b = os.path.join(bdir, rel)
                dst = os.path.join(app_dir, rel)
                try:
                    if os.path.exists(b):
                        shutil.copy2(b, dst)
                    else:
                        os.remove(dst)
                except OSError:
                    failed.append(rel)
            if failed:
                raise UpdateError(f"не удалось заменить файлы ({exc}), и не вернулись "
                                  f"старые: {', '.join(failed)}") from exc
            raise UpdateError(f"не удалось заменить файлы ({exc}) — оставлена "
                              "прежняя версия") from exc
        # ★ 1.2.0: то, что ставили в прошлый раз и чего в новой версии нет,
        # — стереть (без списка — старый код по stale_files)
        removed = _drop_stale(app_dir, files, todo,
                              tuple(t.keep) + tuple(t.own), log, t.user_dirs, prev)
        drop_old_backup(app_dir, log)
        t.removed = removed
        code = [r for r in removed if not r.endswith((".pyc", ".pyo"))]
        tail = f" ({', '.join(code)[:400]})" if code else ""
        log(f"обновление: заменено файлов {len(replaced)}, стёрто старых {len(removed)}{tail}")
        return replaced
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if bdir:
            shutil.rmtree(bdir, ignore_errors=True)
        try:
            os.remove(zip_path)
        except OSError:
            pass


# ---------------- перезапуск ----------------

def is_frozen():
    return bool(getattr(sys, "frozen", False))


def restart(argv=None):
    """Запустить программу заново (с --after-update <pid>). Закрыть текущую
    — дело вызывающего (обычно QApplication.quit() сразу после)."""
    argv = list(sys.argv if argv is None else argv)
    clean, skip = [], False
    for a in argv[1:]:
        if skip:
            skip = False
            continue
        if a == "--after-update":
            skip = True
            continue
        clean.append(a)
    exe = sys.executable
    if os.name == "nt" and exe.lower().endswith("python.exe"):
        w = exe[:-len("python.exe")] + "pythonw.exe"
        if os.path.exists(w):
            exe = w
    cmd = [exe] + ([] if is_frozen() else [os.path.abspath(argv[0])]) + clean \
        + ["--after-update", str(os.getpid())]
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200        # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen(cmd, cwd=os.path.dirname(os.path.abspath(argv[0])),
                     creationflags=flags, close_fds=True)
    return cmd


def wait_previous(argv=None, timeout=20.0):
    """Звать В САМОМ НАЧАЛЕ программы: если запущены после обновления —
    подождать, пока старая копия завершится. -> True, если ждали."""
    argv = sys.argv if argv is None else argv
    if "--after-update" not in argv:
        return False
    try:
        pid = int(argv[argv.index("--after-update") + 1])
    except (ValueError, IndexError):
        return False
    end = time.monotonic() + timeout
    while time.monotonic() < end and _alive(pid):
        time.sleep(0.25)
    return True


def _alive(pid):
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x00100000 | 0x1000, False, pid)   # SYNCHRONIZE | QUERY_LIMITED
        if not h:
            return False
        try:
            return k32.WaitForSingleObject(h, 0) == 0x102            # WAIT_TIMEOUT
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
