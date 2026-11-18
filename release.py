"""release.py  v1.1.0 — общая утилита для всех проектов: архив версии в release/.

Журнал:
v1.1.0: check_versions вне git (программа из архива / после обновления) — только расхождения номеров:
        нет файла или старый release.json — не ошибка; описание журнала изменений: список, wrap, keep, more,
        {title}; ReleaseError — подкласс ValueError.
v1.0.0: первая версия: архив <имя>_vX.Y.Z.zip из HEAD, проверка утечек, удаление старого архива.

Общая утилита: одинаковая во всех проектах. Правка — поднять версию и перенести файл ЦЕЛИКОМ
во все проекты. Настройки проекта — в release.json (рядом), их и править.

Запуск (из папки репозитория, после commit):
    python release.py                 # единственная программа репозитория
    python release.py smartmon mini   # названные программы (имена из release.json)
    python release.py --all           # все программы репозитория
    python release.py --check         # только показать версии и проверить release.json
Что делает для каждой программы:
    1) версия — из первого файла в "files" (release.json);
    2) git archive --format=zip --prefix=<имя>/ -o release/<имя>_v<версия>.zip HEAD[:<папка>];
    3) check_leaks: нет токенов, __pycache__, config.json, логов, release/ — иначе архив удаляется;
    4) старые release/<имя>_v*.zip — git rm; новый — git add (commit и push — вручную);
    5) печатает ссылку https://github.com/<владелец>/<репо>/raw/main/release/<архив>.
Незакоммиченные правки в архив не попадут — release.py остановится (обойти: --dirty).

release.json:
{
  "repo": "romzespra-collab/Comic_project",        (необязательно — иначе из git remote)
  "programs": [
    {"name": "comic_project",                       имя архива (строчными)
     "dir": "",                                     папка программы в репозитории ("" — весь)
     "files": [["VERSION", "{v}"],                  где версия: файл и шаблон с {v};
               ["comic_project.py", "VERSION = \\"{v}\\""],      третий элемент — сколько замен
               ["README.md", "v{v}", 0]],                       (1 — первая, 0 — все);
                                                    шаблон "re:..." — регулярное выражение с {v}
     "headers": true,                               bump_version: «vX.Y.Z» в шапках изменённых файлов
     "headers_skip": ["comic_archive.py"],          (кроме общих модулей и этих — у них своя версия)
     "changelog": {"file": "CHANGELOG.txt",          журнал изменений (или список таких — и журнал в шапке):
                   "before": "re:^\\d+\\.\\d+",       вставить перед первой такой строкой (или "after": …)
                   "template": "{v}:\\n  {msg}\\n\\n", {v} {date} {msg} {title} (-t); строка с {msg} — для -m
                   "more": "  {msg}",                 (необяз.) строка для 2-го и следующих -m
                   "wrap": 88,                        (необяз.) перенос длинных строк, продолжение — под {msg}
                   "keep": 10, "entry": "re:^\\d", "tail": "Более ранние"},  (необяз.) оставить N версий:
                                                    entry — начало версии (по умолчанию before), tail — строка
                                                    после версий ("" — конец файла)
     "allow_in_zip": []}                            что разрешено в архиве из «лишнего» (шаблоны)
  ]
}
"""
import json
import os
import re
import subprocess
import sys

VERSION = "1.1.0"
ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ROOT, "release.json")
VER_RX = r"(?P<v>\d+(?:\.\d+)*)"


class ReleaseError(ValueError):
    """Ошибка утилит выпуска (ValueError — как у прежнего bump_version.py SmartView)."""


# ----------------------------------------------------------------- release.json
def load_config(path=CONFIG):
    try:
        with open(path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except FileNotFoundError:
        raise ReleaseError(f"нет {os.path.basename(path)} — опишите программы проекта") from None
    except ValueError as e:
        raise ReleaseError(f"{os.path.basename(path)}: битый JSON: {e}") from None
    progs = cfg.get("programs")
    if not isinstance(progs, list) or not progs:
        raise ReleaseError("release.json: нет списка programs")
    for p in progs:
        if not re.fullmatch(r"[a-z0-9_\-]+", str(p.get("name", ""))):
            raise ReleaseError(f"release.json: имя программы {p.get('name')!r} — только строчные, цифры, _ и -")
        if not p.get("files"):
            raise ReleaseError(f"release.json: у {p['name']} нет files (где версия)")
        for e in p["files"]:
            compile_pattern(e[1])
    return cfg


def pick(cfg, names, all_=False):
    progs = cfg["programs"]
    if all_:
        return progs
    if not names:
        if len(progs) == 1:
            return progs
        raise ReleaseError("в репозитории несколько программ — назовите: "
                           + ", ".join(p["name"] for p in progs) + " (или --all)")
    by = {p["name"]: p for p in progs}
    miss = [n for n in names if n not in by]
    if miss:
        raise ReleaseError("нет программы: " + ", ".join(miss) + " (есть: " + ", ".join(by) + ")")
    return [by[n] for n in names]


def compile_pattern(pat):
    """Шаблон с {v} -> регулярное выражение с группой v."""
    if pat.startswith("re:"):
        rx = pat[3:]
        if rx.count("{v}") != 1:
            raise ReleaseError(f"шаблон {pat!r}: нужно ровно одно {{v}}")
        rx = rx.replace("{v}", VER_RX)
    else:
        parts = pat.split("{v}")
        if len(parts) != 2:
            raise ReleaseError(f"шаблон {pat!r}: нужно ровно одно {{v}}")
        rx = re.escape(parts[0]) + VER_RX + re.escape(parts[1])
        if parts[1] == "" or not parts[1][0].isdigit():
            rx += r"(?![\d.]*\d)"            # «v1.2» не должно совпасть с началом «v1.23»
    return re.compile(rx, re.M)


# ----------------------------------------------------------------- файлы с версией
def read_text(path):
    """(текст, кодировка, BOM) — utf-8 (с BOM / без) или cp1251; переводы строк не трогаются."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "utf-8", True
    try:
        return raw.decode("utf-8"), "utf-8", False
    except UnicodeDecodeError:
        return raw.decode("cp1251"), "cp1251", False


def write_text(path, text, enc, bom):
    data = text.encode(enc)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write((b"\xef\xbb\xbf" if bom else b"") + data)
    os.replace(tmp, path)


def entry(e):
    path, pat = e[0], e[1]
    count = e[2] if len(e) > 2 else 1
    return path, pat, count


def current_version(prog, root=ROOT):
    path, pat, _ = entry(prog["files"][0])
    full = os.path.join(root, path)
    try:
        text = read_text(full)[0]
    except OSError as e:
        raise ReleaseError(f"{path}: {e}") from None
    m = compile_pattern(pat).search(text)
    if not m:
        raise ReleaseError(f"{path}: версия по шаблону {pat!r} не найдена")
    return m.group("v")


def is_git(root=ROOT):
    return os.path.exists(os.path.join(root, ".git"))


def check_versions(prog, root=ROOT, strict=None):
    """Список расхождений: [(файл, что не так)]; пустой — все файлы с одной версией.
    strict (по умолчанию — в репозитории git): нет файла / версия не найдена — тоже расхождение.
    Вне git (программа из архива, после обновления: release.json мог остаться старым) — только номера."""
    if strict is None:
        strict = is_git(root)
    cur = current_version(prog, root)
    bad = []
    for e in prog["files"]:
        path, pat, count = entry(e)
        full = os.path.join(root, path)
        if not os.path.exists(full):
            if strict:
                bad.append((path, "нет файла"))
            continue
        found = [m.group("v") for m in compile_pattern(pat).finditer(read_text(full)[0])]
        if not found:
            if strict:
                bad.append((path, f"версия по шаблону {pat!r} не найдена"))
            continue
        check = found if count == 0 else found[:count]
        other = sorted(set(v for v in check if v != cur))
        if other:
            bad.append((path, f"версия {', '.join(other)}, а должна быть {cur}"))
    return cur, bad


# ----------------------------------------------------------------- git
def git(*args, root=ROOT, check=True):
    r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def repo_slug(cfg, root=ROOT):
    if cfg.get("repo"):
        return cfg["repo"]
    url = git("remote", "get-url", "origin", root=root, check=False).strip()
    m = re.search(r"[/:]([^/:]+)/([^/]+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else ""


def make_archive(prog, cfg, root=ROOT, dirty=False, keep_old=False, log=print):
    name = prog["name"]
    sub = (prog.get("dir") or "").strip("/\\")
    cur, bad = check_versions(prog, root, strict=True)
    if bad:
        raise ReleaseError(f"{name}: версии не совпадают — " + "; ".join(f"{p}: {t}" for p, t in bad)
                           + " (python bump_version.py ...)")
    st = git("status", "--porcelain", "--", sub or ".", ":(exclude)release", root=root)
    if st.strip() and not dirty:
        raise ReleaseError(f"{name}: есть незакоммиченные правки — в архив они не попадут:\n"
                           + st.rstrip() + "\n(сначала commit; или --dirty)")
    attrs = os.path.join(root, ".gitattributes")
    if not sub and (not os.path.exists(attrs) or not re.search(
            r"^/?release/?\s+export-ignore", read_text(attrs)[0], re.M)):
        log("ВНИМАНИЕ: в .gitattributes нет «release export-ignore» — старые архивы попадут в новый")
    rel_dir = os.path.join(root, "release")
    os.makedirs(rel_dir, exist_ok=True)
    zip_name = f"{name}_v{cur}.zip"
    zip_path = os.path.join(rel_dir, zip_name)
    tree = f"HEAD:{sub}" if sub else "HEAD"
    git("archive", "--format=zip", f"--prefix={name}/", "-o", zip_path, tree, root=root)
    try:
        import check_leaks
    except ImportError:
        sys.path.insert(0, ROOT)
        import check_leaks
    found = check_leaks.scan_zip(zip_path, prog.get("allow_in_zip", []))
    if found:
        os.remove(zip_path)
        raise ReleaseError(f"{zip_name}: найдено лишнее — архив удалён:\n  "
                           + "\n  ".join(str(f) for f in found))
    removed = []
    if not keep_old:
        rx = re.compile(re.escape(name) + r"_v\d+(?:\.\d+)*\.zip")
        tracked = set(git("ls-files", "release", root=root).split())
        for fn in sorted(os.listdir(rel_dir)):
            if fn != zip_name and rx.fullmatch(fn):
                rel = f"release/{fn}"
                if rel in tracked:
                    git("rm", "-q", "--", rel, root=root)
                else:
                    os.remove(os.path.join(rel_dir, fn))
                removed.append(fn)
    git("add", "-f", "--", f"release/{zip_name}", root=root)
    size = os.path.getsize(zip_path)
    log(f"{zip_name}: {size / 1024:.0f} КБ, утечек нет"
        + (f"; удалён старый: {', '.join(removed)}" if removed else ""))
    slug = repo_slug(cfg, root)
    if slug:
        log(f"  https://github.com/{slug}/raw/main/release/{zip_name}")
    return zip_path


# ----------------------------------------------------------------- самопроверка
def selftest():
    import tempfile
    errs = []

    def check(cond, text):
        if not cond:
            errs.append(text)

    rx = compile_pattern("v{v}")
    check(rx.search("App v1.2.3 x").group("v") == "1.2.3", "шаблон v{v}")
    check(compile_pattern('VERSION = "{v}"').search('VERSION = "4.17.0"').group("v") == "4.17.0", "шаблон в кавычках")
    check(compile_pattern("re:^{v}$").search("2.14\n").group("v") == "2.14", "шаблон re:")
    try:
        compile_pattern("v{v} {v}")
        errs.append("два {v} — должна быть ошибка")
    except ReleaseError:
        pass
    with tempfile.TemporaryDirectory() as d:
        def run(*a):
            subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
        run("init", "-q")
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        for fn, text in {"VERSION": "1.2.0\n", "app.py": 'VERSION = "1.2.0"\n',
                         ".gitattributes": "release export-ignore\n",
                         ".gitignore": "*.zip\n!release/*.zip\nconfig.json\n__pycache__/\n"}.items():
            with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
                f.write(text)
        os.makedirs(os.path.join(d, "release"))
        with open(os.path.join(d, "release", "app_v1.1.0.zip"), "wb") as f:
            f.write(b"old")
        run("add", "-A")
        run("add", "-f", "release/app_v1.1.0.zip")
        run("commit", "-qm", "init")
        prog = {"name": "app", "dir": "", "files": [["VERSION", "{v}"], ["app.py", 'VERSION = "{v}"']]}
        cfg = {"repo": "o/r", "programs": [prog]}
        out = []
        z = make_archive(prog, cfg, root=d, log=out.append)
        check(os.path.basename(z) == "app_v1.2.0.zip" and os.path.exists(z), "архив создан")
        check(not os.path.exists(os.path.join(d, "release", "app_v1.1.0.zip")), "старый архив удалён")
        check(any("raw/main/release/app_v1.2.0.zip" in s for s in out), f"ссылка: {out}")
        import zipfile
        names = zipfile.ZipFile(z).namelist()
        check("app/VERSION" in names and not any("release" in n for n in names), f"содержимое: {names}")
        # вне git нет файла — не ошибка, а другой номер — ошибка
        prog2 = dict(prog, files=prog["files"] + [["нет.txt", "v{v}"]])
        check(check_versions(prog2, root=d, strict=False) == ("1.2.0", []), "вне git: нет файла — не ошибка")
        check(check_versions(prog2, root=d)[1], "в git: нет файла — ошибка")
        with open(os.path.join(d, "app.py"), "w", encoding="utf-8") as f:
            f.write('VERSION = "1.3.0"\n')
        check(check_versions(prog, root=d, strict=False)[1], "вне git: другой номер — ошибка")
        try:
            make_archive(prog, cfg, root=d, log=out.append)
            errs.append("разные версии — должна быть ошибка")
        except ReleaseError as e:
            check("не совпадают" in str(e), f"текст ошибки: {e}")
    return errs


def main(argv):
    if "--selftest" in argv:
        problems = selftest()
        print(f"release {VERSION}: " + ("OK" if not problems else "ОШИБКИ:\n  " + "\n  ".join(problems)))
        return 1 if problems else 0
    flags = {a for a in argv if a.startswith("--")}
    names = [a for a in argv if not a.startswith("--")]
    try:
        cfg = load_config()
        if "--check" in flags:
            rc = 0
            for p in cfg["programs"]:
                cur, bad = check_versions(p)
                print(f"{p['name']}: {cur}" + ("" if not bad else "  РАСХОЖДЕНИЯ:"))
                for path, t in bad:
                    print(f"  {path}: {t}")
                    rc = 1
            return rc
        for p in pick(cfg, names, "--all" in flags):
            make_archive(p, cfg, dirty="--dirty" in flags, keep_old="--keep-old" in flags)
    except ReleaseError as e:
        print(f"ОШИБКА: {e}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
