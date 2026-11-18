"""check_leaks.py  v1.2.0 — общая утилита для всех проектов: поиск утечек перед выдачей.

Журнал:
v1.2.0: без git (папка программы из архива) файлы пользователя узнаются и по .gitignore программы (её копия
        лежит в архиве): например smartmon_devices.json / my_sources.json с паролями — не утечка, а файл
        пользователя (в сборку не идёт); имена config / settings / cache / … — как раньше.
v1.1.0: токен бота Telegram находится и в адресе (…/bot<токен>/…); без аргументов вне git (папка программы, распакованная из архива) — проверяются только файлы
        программы; config.json, журналы, кэш и прочие файлы пользователя пропускаются, а не считаются
        утечкой (сборка build_exe.bat из такой папки больше не останавливается).
v1.0.0: первая версия: токены и ключи в файлах, секреты в JSON, лишние файлы в архиве / сборке.

Общая утилита: одинаковая во всех проектах (в архив программы попадает, в EXE — нет).
Правка — поднять версию и перенести файл ЦЕЛИКОМ во все проекты.

Запуск (из папки репозитория):
    python check_leaks.py                    # файлы репозитория (git ls-files); вне git — файлы программы
                                             # без файлов пользователя (config.json, журналы, build/, dist/)
    python check_leaks.py release/x_v1.zip   # архив: секреты + лишнее (__pycache__, config.json, логи, release/)
    python check_leaks.py dist/Prog          # папка сборки — то же, что архив
    python check_leaks.py --selftest
Итог: 0 — чисто, 1 — найдено (список с файлами и строками), 2 — ошибка запуска.

Что ищется:
- токены GitHub (github_pat_…, ghp_/gho_/ghu_/ghs_/ghr_…), ключи Anthropic / OpenAI (sk-…), AWS (AKIA…),
  Slack (xox…-), бота Telegram, закрытые ключи (BEGIN … PRIVATE KEY);
- в *.json — непустые значения у ключей password / token / secret / api_key … (не «***», не «<…>»,
  не «вставьте…»; файлы-образцы *example* / *sample* / *template* — без этой проверки);
- в архиве / папке сборки — __pycache__, *.pyc, config.json, *.log, logs/, release/, .git/, *.tmp, *.bak,
  app_icon.json, .env (разрешить — allow=[шаблоны] или "allow_in_zip" в release.json).
Строка с пометкой leak-ok не проверяется (для заведомо поддельных токенов в тестах).
"""
import fnmatch
import json
import os
import re
import subprocess
import sys
import zipfile

VERSION = "1.2.0"

MAX_SIZE = 20_000_000
TOKEN_RES = [
    ("токен GitHub", re.compile(r"github_pat_[A-Za-z0-9_]{30,}")),
    ("токен GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("ключ Anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{30,}")),
    ("ключ OpenAI", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}")),
    ("ключ AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("токен Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9]{10,}-[A-Za-z0-9\-]{10,}")),
    ("токен бота Telegram", re.compile(r"(?<!\d)\d{8,10}:AA[A-Za-z0-9_\-]{33}(?![A-Za-z0-9_\-])")),
    ("закрытый ключ", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")),
]
SECRET_KEYS = re.compile(
    r"^(password|passwd|pwd|pass|token|access_token|refresh_token|gh_token|github_token|"
    r"bot_token|tg_token|telegram_token|secret|client_secret|api_key|apikey|api-key|access_key|"
    r"secret_key|private_key|auth_token)$", re.I)
PLACEHOLDER = re.compile(r"^(\*+|<.*>|\{.*\}|x+|changeme|none|null)$|your|example|вставьте|ваш|insert|paste|placeholder", re.I)
SAMPLE_NAME = re.compile(r"example|sample|template|образец|пример", re.I)    # файлы-образцы настроек
FORBIDDEN = ["__pycache__/", "*.pyc", "*.pyo", "config.json", "*.log", "*.log.[0-9]", "logs/",
             "release/", ".git/", "*.tmp", "*.bak", "app_icon.json", "app_icon_cache.json", ".env",
             "*.bad-*"]


class Finding:
    def __init__(self, path, line, kind, sample=""):
        self.path, self.line, self.kind, self.sample = path, line, kind, sample

    def __str__(self):
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: {self.kind}" + (f" ({self.sample})" if self.sample else "")


def _short(s):
    s = s.strip()
    return (s[:8] + "…") if len(s) > 8 else s


def _is_binary(data):
    return b"\0" in data[:8192]


def scan_bytes(name, data):
    """Секреты в содержимом одного файла."""
    out = []
    if len(data) > MAX_SIZE or _is_binary(data):
        return out
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1251", errors="replace")
    for no, line in enumerate(text.splitlines(), 1):
        if "leak-ok" in line:
            continue
        for kind, rx in TOKEN_RES:
            m = rx.search(line)
            if m:
                out.append(Finding(name, no, kind, _short(m.group(0))))
    if name.lower().endswith(".json") and not SAMPLE_NAME.search(os.path.basename(name)):
        try:
            obj = json.loads(text)
        except ValueError:
            obj = None

        def walk(o, path):
            if isinstance(o, dict):
                for k, v in o.items():
                    p = f"{path}.{k}" if path else str(k)
                    if (isinstance(k, str) and SECRET_KEYS.match(k) and isinstance(v, str)
                            and v.strip() and not PLACEHOLDER.search(v.strip())):
                        out.append(Finding(name, 0, f"секрет в JSON: «{p}»", _short(v)[:3] + "…"))
                    else:
                        walk(v, p)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")
        walk(obj, "")
    return out


def _forbidden(rel, allow=()):
    """Шаблон из FORBIDDEN, которому соответствует путь (или None)."""
    rel = rel.replace("\\", "/")
    parts = rel.split("/")
    for pat in FORBIDDEN:
        if any(fnmatch.fnmatch(rel, a) or fnmatch.fnmatch(parts[-1], a) for a in allow):
            return None
        if pat.endswith("/"):
            d = pat[:-1]
            if d in parts[:-1] or (rel.endswith("/") and parts[-2:-1] == [d]):
                return pat
        elif fnmatch.fnmatch(parts[-1], pat):
            return pat
    return None


def scan_zip(path, allow=()):
    out = []
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = info.filename
            # внутри архива — папка <имя>/...; проверяем путь без неё
            rel = name.split("/", 1)[1] if "/" in name else name
            bad = _forbidden(rel, allow)
            if bad:
                out.append(Finding(name, 0, f"лишний файл в архиве ({bad})"))
            if not name.endswith("/") and info.file_size <= MAX_SIZE:
                out.extend(scan_bytes(name, z.read(info)))
    # одна находка на папку (__pycache__/ и т.п.), а не на каждый файл
    seen, res = set(), []
    for f in out:
        key = (f.kind, f.path.split("/__pycache__/")[0]) if "__pycache__" in f.path else (f.kind, f.path, f.line)
        if key not in seen:
            seen.add(key)
            res.append(f)
    return res


def scan_dir(path, allow=()):
    out = []
    for root, _dirs, files in os.walk(path):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, path).replace("\\", "/")
            bad = _forbidden(rel, allow)
            if bad:
                out.append(Finding(rel, 0, f"лишний файл в сборке ({bad})"))
            try:
                if os.path.getsize(full) <= MAX_SIZE:
                    with open(full, "rb") as f:
                        out.extend(scan_bytes(rel, f.read()))
            except OSError:
                pass
    return out


def tracked_files(root):
    r = subprocess.run(["git", "-C", root, "ls-files", "-z"], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("не репозиторий git: " + r.stderr.decode("utf-8", "replace").strip())
    return [p for p in r.stdout.decode("utf-8", "replace").split("\0") if p]


def scan_repo(root="."):
    out = []
    me = os.path.abspath(__file__)
    for rel in tracked_files(root):
        full = os.path.join(root, rel)
        if os.path.abspath(full) == me or not os.path.isfile(full):
            continue
        try:
            if os.path.getsize(full) > MAX_SIZE:
                continue
            with open(full, "rb") as f:
                out.extend(scan_bytes(rel, f.read()))
        except OSError:
            pass
    return out


def _gitignore(path):
    """Правила .gitignore папки: [(шаблон, отрицание, только_папка, с_путём)]."""
    rules = []
    try:
        with open(os.path.join(path, ".gitignore"), encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except OSError:
        return rules
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        neg = ln.startswith("!")
        if neg:
            ln = ln[1:]
        only_dir = ln.endswith("/")
        ln = ln.strip("/")
        if ln:
            rules.append((ln, neg, only_dir, "/" in ln))
    return rules


def _ignored(rel, rules, is_dir=False):
    """Путь попадает под .gitignore (последнее подходящее правило главнее)."""
    parts = rel.split("/")
    hit = False
    for pat, neg, only_dir, anchored in rules:
        if only_dir and not is_dir and not any(fnmatch.fnmatch(p, pat) for p in parts[:-1]):
            continue
        if anchored:
            ok = fnmatch.fnmatch(rel, pat) or any(fnmatch.fnmatch("/".join(parts[:i]), pat)
                                                  for i in range(1, len(parts)))
        else:
            ok = any(fnmatch.fnmatch(p, pat) for p in (parts if not only_dir or is_dir else parts[:-1]))
        if ok:
            hit = not neg
    return hit


def scan_program_dir(path):
    """Папка программы без git (распакована из архива): файлы пользователя и сборки пропускаются
    (по своему списку, по словам в имени JSON и по .gitignore программы)."""
    out = []
    skip_dirs = {"__pycache__", "logs", "release", ".git", "build", "dist", ".venv", "venv"}
    rules = _gitignore(path)
    for root, dirs, files in os.walk(path):
        rel_root = os.path.relpath(root, path).replace("\\", "/")
        rel_root = "" if rel_root == "." else rel_root + "/"
        dirs[:] = [x for x in dirs if x not in skip_dirs and not _ignored(rel_root + x, rules, True)]
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, path).replace("\\", "/")
            if _forbidden(rel) or fn.endswith(".json") and _user_json(fn) or _ignored(rel, rules):
                continue
            try:
                if os.path.getsize(full) <= MAX_SIZE:
                    with open(full, "rb") as f:
                        out.extend(scan_bytes(rel, f.read()))
            except OSError:
                pass
    return out


def _user_json(fn):
    """JSON-файлы пользователя рядом с программой (настройки, кэш, история) — не исходники."""
    return bool(re.search(r"config|settings|cache|state|history|session|token|secret|user", fn, re.I))


def scan_default(root="."):
    """Без аргументов: репозиторий git — его файлы; иначе — папка программы без файлов пользователя."""
    if os.path.isdir(os.path.join(root, ".git")) or os.path.isfile(os.path.join(root, ".git")):
        return scan_repo(root), "файлы репозитория"
    return scan_program_dir(root), "файлы программы (без файлов пользователя)"


def scan(target, allow=()):
    if os.path.isfile(target) and target.lower().endswith(".zip"):
        return scan_zip(target, allow)
    if os.path.isdir(os.path.join(target, ".git")) or os.path.isfile(os.path.join(target, ".git")):
        return scan_repo(target)
    if os.path.isdir(target):
        return scan_dir(target, allow)
    with open(target, "rb") as f:
        return scan_bytes(target, f.read())


# ----------------------------------------------------------------- самопроверка
def selftest():
    import tempfile
    errs = []

    def check(cond, text):
        if not cond:
            errs.append(text)

    fake = "ghp_" + "Z" * 36
    pat = "github_pat_" + "1" * 22 + "_" + "a" * 30
    check(scan_bytes("a.py", f"t = '{fake}'\n".encode()), "ghp_ не найден")
    check(scan_bytes("a.py", f"t = '{pat}'\n".encode()), "github_pat_ не найден")
    check(not scan_bytes("a.py", f"t = '{fake}'  # leak-ok\n".encode()), "leak-ok не учтён")
    tg = "123456789:AA" + "Bb1" * 11
    check(scan_bytes("a.py", f"u = 'https://api.telegram.org/bot{tg}/getMe'\n".encode()),
          "токен Telegram в адресе не найден")
    check(not scan_bytes("a.py", b"rx = r'github_pat_[A-Za-z0-9_]{20,}'\n"), "шаблон в коде — не утечка")
    check(scan_bytes("c.json", b'{"gh": {"token": "abc123"}}'), "токен в JSON не найден")
    check(not scan_bytes("c.json", b'{"token": "", "password": "***", "api_key": "<your key>"}'),
          "пустые / заглушки в JSON — не утечка")
    check(not scan_bytes("c.json", '{"bot_token": "123:ВСТАВЬТЕ_ТОКЕН"}'.encode()), "заглушка «вставьте»")
    check(not scan_bytes("cfg.example.json", b'{"password": "1234"}'), "файл-образец")
    check(not scan_bytes("x.bin", b"\0\0" + fake.encode()), "двоичные файлы пропускаются")
    check(_forbidden("app/__pycache__/m.cpython-313.pyc") is not None, "__pycache__")
    check(_forbidden("config.json") and _forbidden("logs/a.txt") and _forbidden("release/x.zip"),
          "config.json / logs / release")
    check(_forbidden("config.json", allow=["config.json"]) is None, "allow")
    check(_forbidden("app/config_defaults.json") is None and _forbidden("README.md") is None, "лишнее срабатывание")
    with tempfile.TemporaryDirectory() as d:
        # папка программы без git: config.json с токеном и журналы — не утечка; токен в коде — утечка
        with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
            f.write('{"upd_token": "%s"}' % fake)
        os.makedirs(os.path.join(d, "logs"))
        with open(os.path.join(d, "logs", "a.log"), "w", encoding="utf-8") as f:
            f.write(fake)
        with open(os.path.join(d, "main.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")
        found, what = scan_default(d)
        check(not found and "без файлов пользователя" in what, f"папка программы: {[str(x) for x in found]}")
        with open(os.path.join(d, "main.py"), "w", encoding="utf-8") as f:
            f.write("t = '%s'\n" % fake)
        found, _ = scan_default(d)
        check(len(found) == 1 and found[0].path == "main.py", "токен в коде папки программы")
        # .gitignore программы: её файлы пользователя с паролями — не утечка
        with open(os.path.join(d, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("smartmon_*.json\nprivate/\n!keep.json\n")
        os.makedirs(os.path.join(d, "private"))
        for name in ("smartmon_devices.json", os.path.join("private", "x.json"), "keep.json"):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write('{"password": "real1"}')
        found, _ = scan_default(d)
        check(sorted(x.path for x in found) == ["keep.json", "main.py"], f".gitignore: {[str(x) for x in found]}")
    with tempfile.TemporaryDirectory() as d:
        z = os.path.join(d, "p_v1.zip")
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("p/main.py", "print(1)\n")
            zf.writestr("p/app/__pycache__/a.pyc", b"\0")
            zf.writestr("p/app/__pycache__/b.pyc", b"\0")
            zf.writestr("p/config.json", '{"token": "real-secret"}')
        f = scan_zip(z)
        kinds = [x.kind for x in f]
        check(sum("__pycache__" in k for k in kinds) == 1, f"__pycache__ один раз: {kinds}")
        check(any("config.json" in k for k in kinds) and any("секрет в JSON" in k for k in kinds),
              f"config.json в архиве: {kinds}")
    return errs


def main(argv):
    if "--selftest" in argv:
        problems = selftest()
        print(f"check_leaks {VERSION}: " + ("OK" if not problems else "ОШИБКИ:\n  " + "\n  ".join(problems)))
        return 1 if problems else 0
    allow = []
    targets = []
    it = iter(argv)
    for a in it:
        if a == "--allow":
            allow.append(next(it, ""))
        else:
            targets.append(a)
    total = []
    try:
        if targets:
            for t in targets:
                total.extend(scan(t, allow))
        else:
            found, what = scan_default(".")
            total.extend(found)
            targets = [what]
    except (OSError, RuntimeError, zipfile.BadZipFile) as e:
        print(f"ОШИБКА: {e}")
        return 2
    if total:
        print(f"Найдено {len(total)}:")
        for f in total:
            print("  " + str(f))
        return 1
    print("Утечек нет: " + ", ".join(targets))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
