"""bump_version.py  v1.1.1 — общая утилита для всех проектов: подъём версии во всех местах сразу.

Журнал:
v1.1.1: явная версия ниже текущей (откат) — только с --force; "cont" — начало строки-продолжения при переносе
        (например "#       " для журнала в комментариях); "keep" не добавляет пустую строку перед "tail",
        если её там не было; перенос не рвёт слова по дефису («по-прежнему»); без -t пустые «({title})» /
        «[{title}]» убираются целиком.
v1.1.0: несколько программ поднимаются ВМЕСТЕ (общее место версии — у обеих, проверка до записи);
        шапки: и «vNNN» из одного числа, и «Version: X.Y.Z» / «Версия: X.Y.Z»; программа в корне ("dir": "")
        не трогает шапки других программ репозитория (их папок); -t "название" — {title} в шаблоне
        (заголовок версии «## vX — название»); журнал изменений: несколько -m — продолжение под текстом (не повтор строки версии), "more", перенос
        длинных строк ("wrap"), только N последних версий ("keep" + "tail"), несколько журналов (список —
        например, ещё журнал в шапке .pyw).
v1.0.0: первая версия (на основе bump_version.py SmartView 2.10.2): места версии — в release.json;
        проверка, что везде одна версия; шапки изменённых файлов; запись в журнал изменений.

Общая утилита: одинаковая во всех проектах. Правка — поднять версию и перенести файл ЦЕЛИКОМ
во все проекты. Где версия у проекта — в release.json (описание формата — в release.py).

Запуск (из папки репозитория):
    python bump_version.py                     # 2.0.0 -> 2.0.1 (единственная программа)
    python bump_version.py minor               # 2.0.0 -> 2.1.0
    python bump_version.py major               # 2.0.0 -> 3.0.0
    python bump_version.py 2.1.0               # задать явно
    python bump_version.py mini minor          # программа «mini» из release.json (если их несколько)
    python bump_version.py minor -m "Что сделано" -m "Ещё строка"    # + запись в журнал изменений
    python bump_version.py minor -t "Общие модули" -m "…"              # {title} — заголовок версии
    python bump_version.py --check             # версии всех программ и расхождения
Если хоть в одном файле версия не найдена или не та — ничего не меняется (обойти: --force).
Версии вида X.Y и одно число тоже понимает: patch / minor поднимают последнюю / вторую часть.
"""
import datetime
import fnmatch
import os
import re
import subprocess
import sys
import textwrap

VERSION = "1.1.1"
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import release as R          # noqa: E402 — release.json, шаблоны, чтение и запись файлов

HOW = ("patch", "minor", "major")
HEADER_RX = re.compile(r"\bv(\d+(?:\.\d+)*)\b|(?i:\b(?:version|версия)\b)\s*[:=]?\s*v?(\d+(?:\.\d+)*)\b")
HEADER_EXT = (".py", ".pyw", ".bat", ".cmd", ".spec", ".ps1")
# общие модули — со своей версией; их шапки программа не трогает (+ "headers_skip" в release.json)
SHARED = ("gh_update*.py", "test_gh_update.pyw", "app_icon*.py", "app_icon_pack_build.pyw", "safe_json.py",
          "app_log.py", "bump_version.py", "release.py", "check_leaks.py", "int_field.py",
          "window_frame.py", "dialog_frame.py", "win_frame.py")


def _older(a, b):
    """a < b по частям номера (1.9 < 1.10)."""
    pa, pb = [int(x) for x in a.split(".")], [int(x) for x in b.split(".")]
    n = max(len(pa), len(pb))
    return pa + [0] * (n - len(pa)) < pb + [0] * (n - len(pb))


def bump(cur, how, force=False):
    if re.fullmatch(r"\d+(?:\.\d+)*", how):
        if _older(how, cur) and not force:
            raise R.ReleaseError(f"{how} ниже текущей {cur} — это откат? (если да — --force)")
        return how
    if how not in HOW:
        # опечатка («mnior», «2.11.») не должна молча поднимать patch и править файлы
        raise R.ReleaseError(f"непонятно, как поднять версию: {how!r} (patch | minor | major | X.Y.Z)")
    parts = [int(x) for x in cur.split(".")]
    if how == "major" or len(parts) == 1:
        i = 0 if how == "major" else len(parts) - 1
    elif how == "minor":
        i = 1
    else:
        i = len(parts) - 1
    parts[i] += 1
    for j in range(i + 1, len(parts)):
        parts[j] = 0
    return ".".join(str(x) for x in parts)


def changed_files(prog, root=R.ROOT, others=()):
    """Изменённые (и новые, не в .gitignore) файлы программы — для шапок. others — папки других программ
    репозитория (программа в корне их файлы не берёт)."""
    sub = (prog.get("dir") or "").strip("/\\") or "."
    out = R.git("diff", "--name-only", "HEAD", "--", sub, root=root, check=False).split("\n")
    out += R.git("ls-files", "--others", "--exclude-standard", "--", sub, root=root, check=False).split("\n")
    mine = (prog.get("dir") or "").strip("/\\")
    skip = [o.strip("/\\") + "/" for o in others if o and o.strip("/\\") and o.strip("/\\") != mine]
    return sorted({p for p in out if p.strip() and p.lower().endswith(HEADER_EXT)
                   and not any(p.startswith(o) for o in skip)})


def update_header(text, new):
    """В первых 3 строках — первое «vX.Y…» -> v<new>. (новый текст, было ли что менять)"""
    lines = text.split("\n")
    for i in range(min(3, len(lines))):
        m = HEADER_RX.search(lines[i])
        if m:
            g = 1 if m.group(1) else 2
            if m.group(g) == new:
                return text, False
            lines[i] = lines[i][:m.start(g)] + new + lines[i][m.end(g):]
            return "\n".join(lines), True
    return text, False


def _fill(t, new, today, title):
    if not title:                      # нет названия — убрать его скобки или разделитель перед ним
        t = re.sub(r"\s*[(\[]\{title\}[)\]]", "", t)
        t = re.sub(r"\s*[—–:-]?\s*\{title\}", "", t)
    return t.replace("{v}", new).replace("{date}", today).replace("{title}", title or "")


def _entry_lines(line, msgs, more, wrap, new, today, title="", cont=None):
    """Строки записи: шаблонная строка с {msg} — для первого сообщения, для остальных — more
    (по умолчанию: та же строка, если в ней нет {v} / {date}, иначе — отступ под {msg});
    wrap — перенос длинных сообщений, продолжение — под {msg}."""
    def fill(t):
        return _fill(t, new, today, title)
    if more is None:
        more = line if not re.search(r"\{(v|date|title)\}", line) else \
            " " * fill(line).index("{msg}") + "{msg}"
    out = []
    for i, m in enumerate(msgs):
        tpl = fill(line if i == 0 else more)
        c = tpl.index("{msg}")
        parts = textwrap.wrap(m, width=max(20, wrap - c), break_on_hyphens=False) if wrap else [m]
        parts = parts or [""]
        out.append(tpl.replace("{msg}", parts[0]))
        out.extend((" " * c if cont is None else cont) + p for p in parts[1:])
    return out


def _find(lines, spec, start=0):
    rx = re.compile(spec[3:]) if spec.startswith("re:") else None
    for i in range(start, len(lines)):
        if (rx.search(lines[i]) if rx else spec in lines[i]):
            return i
    return None


def changelog_insert(text, cl, new, msgs, title=""):
    nl = "\r\n" if "\r\n" in text else "\n"
    today = datetime.date.today().isoformat()
    body = []
    for line in cl.get("template", "{v}:\n- {msg}\n").split("\n"):
        if "{msg}" in line:
            body.extend(_entry_lines(line, msgs, cl.get("more"), int(cl.get("wrap") or 0), new, today, title,
                                     cl.get("cont")))
        else:
            body.append(_fill(line, new, today, title))
    block = body
    lines = text.split(nl)
    if cl.get("before"):
        pos = _find(lines, cl["before"])
        if pos is None:
            raise R.ReleaseError(f"{cl['file']}: строка {cl['before']!r} не найдена")
    elif cl.get("after"):
        i = _find(lines, cl["after"])
        if i is None:
            raise R.ReleaseError(f"{cl['file']}: строка {cl['after']!r} не найдена")
        pos = i + 1
    else:
        pos = 0
    # шаблон кончается переводом строки — последняя пустая часть не нужна
    if block and block[-1] == "":
        block = block[:-1]
    lines[pos:pos] = block
    keep = int(cl.get("keep") or 0)
    if keep:
        entry = cl.get("entry") or (cl["before"] if str(cl.get("before", "")).startswith("re:") else None)
        if not entry:
            raise R.ReleaseError(f"{cl['file']}: keep — нужен \"entry\" (строка начала версии, re:…)")
        if "tail" not in cl:
            raise R.ReleaseError(f"{cl['file']}: keep — нужен \"tail\" (строка после версий; \"\" — конец файла)")
        rx = re.compile(entry[3:] if entry.startswith("re:") else re.escape(entry))
        starts = [i for i, ln in enumerate(lines) if i >= pos and rx.search(ln)]
        if len(starts) > keep:
            cut = starts[keep]
            end = _find(lines, cl["tail"], cut) if cl["tail"] else None
            if cl["tail"] and end is None:
                raise R.ReleaseError(f"{cl['file']}: строка {cl['tail']!r} не найдена — версии не обрезаю")
            end = len(lines) if end is None else end
            to_eof = end == len(lines)
            blank_before_tail = not to_eof and end > 0 and lines[end - 1].strip() == ""
            del lines[cut:end]
            if blank_before_tail and cut > 0 and lines[cut - 1].strip() != "":
                lines.insert(cut, "")            # пустая строка перед tail — была, пусть и останется
            if to_eof:
                while lines and lines[-1] == "":
                    lines.pop()
                if text.endswith(nl):
                    lines.append("")
    return nl.join(lines)


def plan(prog, how, msgs, root=R.ROOT, force=False, title="", edits=None, others=()):
    """Все правки заранее: {путь: [текст, кодировка, BOM]}, старая и новая версия, заметки.
    edits — общий словарь правок (несколько программ вместе: общее место версии правится один раз)."""
    cur, bad = R.check_versions(prog, root, strict=True)
    new = bump(cur, how, force)
    if new == cur:
        raise R.ReleaseError(f"версия уже {cur}")
    if bad and not force:
        raise R.ReleaseError(f"{prog['name']}: версии не совпадают — ничего не меняю (обойти: --force):\n  "
                             + "\n  ".join(f"{p}: {t}" for p, t in bad))
    edits = {} if edits is None else edits
    notes = []

    def get(path):
        full = os.path.join(root, path)
        if path not in edits:
            edits[path] = list(R.read_text(full))
        return edits[path]

    for e in prog["files"]:
        path, pat, count = R.entry(e)
        if not os.path.exists(os.path.join(root, path)):
            notes.append(f"{path}: нет файла — пропущен")
            continue
        rec = get(path)
        rx = R.compile_pattern(pat)
        rec[0], n = rx.subn(lambda m: m.group(0)[:m.start("v") - m.start()] + new
                            + m.group(0)[m.end("v") - m.start():], rec[0], count=count)
        notes.append(f"{path}: {'обновлён' if n else 'версия не найдена'}")
    if prog.get("headers"):
        skip = SHARED + tuple(prog.get("headers_skip", ()))
        for path in changed_files(prog, root, others):
            if any(fnmatch.fnmatch(os.path.basename(path), g) or fnmatch.fnmatch(path, g) for g in skip):
                continue
            full = os.path.join(root, path)
            if not os.path.isfile(full):
                continue
            rec = get(path)
            rec[0], ch = update_header(rec[0], new)
            if ch:
                notes.append(f"{path}: шапка -> v{new}")
    cls = prog.get("changelog") or []
    for cl in ([cls] if isinstance(cls, dict) else cls):
        if msgs:
            rec = get(cl["file"])
            rec[0] = changelog_insert(rec[0], cl, new, msgs, title)
            notes.append(f"{cl['file']}: запись о {new}")
        else:
            notes.append(f"{cl['file']}: запись о {new} — допишите (или -m \"текст\")")
    return cur, new, edits, notes


def apply(edits, root=R.ROOT):
    for path, (text, enc, bom) in edits.items():
        R.write_text(os.path.join(root, path), text, enc, bom)


# ----------------------------------------------------------------- самопроверка
def selftest():
    import tempfile
    errs = []

    def check(cond, text):
        if not cond:
            errs.append(text)

    for cur, how, want in (("1.2.3", "patch", "1.2.4"), ("1.2.3", "minor", "1.3.0"), ("1.2.3", "major", "2.0.0"),
                           ("2.13", "patch", "2.14"), ("2.13", "minor", "2.14"), ("516", "minor", "517"),
                           ("5.65", "major", "6.0"), ("1.2.3", "4.0.0", "4.0.0")):
        got = bump(cur, how)
        check(got == want, f"bump({cur}, {how}) = {got}, а нужно {want}")
    try:
        bump("1.2.3", "mnior")
        errs.append("опечатка — должна быть ошибка")
    except R.ReleaseError:
        pass
    with tempfile.TemporaryDirectory() as d:
        def run(*a):
            subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
        files = {"VERSION": "1.2.0\n", "app.py": '"""app.py  v1.1.0\nЖурнал:\nv1.1.0: было\n"""\nVERSION = "1.2.0"\n',
                 "lib.py": '"""lib.py  v1.0.5 — модуль\n"""\nx = 1\n',
                 "safe_json.py": '"""safe_json.py  v1.0.0 — общий\n"""\n',
                 "build.bat": "@echo off\r\nchcp 65001\r\necho App v1.2.0\r\n",
                 "CHANGELOG.txt": "История\n=======\n\n1.2.0:\n- старое\n"}
        for fn, text in files.items():
            with open(os.path.join(d, fn), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        run("init", "-q")
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        run("add", "-A")
        run("commit", "-qm", "init")
        for fn in ("app.py", "safe_json.py"):
            with open(os.path.join(d, fn), "a", encoding="utf-8") as f:
                f.write("# правка\n")
        prog = {"name": "app", "files": [["VERSION", "{v}"], ["app.py", 'VERSION = "{v}"'], ["build.bat", "App v{v}"]],
                "headers": True, "changelog": {"file": "CHANGELOG.txt", "before": "re:^\\d+\\.\\d+",
                                               "template": "{v}:\n- {msg}\n"}}
        cur, new, edits, notes = plan(prog, "minor", ["новое", "ещё"], root=d)
        apply(edits, root=d)
        def rd(fn):
            with open(os.path.join(d, fn), encoding="utf-8", newline="") as f:
                return f.read()
        check(cur == "1.2.0" and new == "1.3.0", f"{cur} -> {new}")
        check(rd("VERSION") == "1.3.0\n", "VERSION")
        check('VERSION = "1.3.0"' in rd("app.py") and rd("app.py").startswith('"""app.py  v1.3.0\n'),
              "app.py: константа и шапка")
        check("v1.1.0: было" in rd("app.py"), "строка журнала в шапке не тронута")
        check(rd("lib.py").startswith('"""lib.py  v1.0.5'), "шапка НЕизменённого файла не тронута")
        check(rd("safe_json.py").startswith('"""safe_json.py  v1.0.0'), "шапка общего модуля не тронута")
        check(rd("build.bat") == "@echo off\r\nchcp 65001\r\necho App v1.3.0\r\n", "bat: CRLF сохранён")
        check(rd("CHANGELOG.txt") == "История\n=======\n\n1.3.0:\n- новое\n- ещё\n1.2.0:\n- старое\n",
              "журнал изменений: " + repr(rd("CHANGELOG.txt")))
        # журнал «v{v} — {msg}»: продолжение под текстом, перенос, только 2 версии; второй журнал — в шапке
        with open(os.path.join(d, "NEWS.txt"), "w", encoding="utf-8", newline="") as f:
            f.write("Что нового\n\nv1.3.0 — было 3\nv1.2.0 — было 2\nv1.1.0 — было 1\n\nБолее ранние — в git.\n")
        news = {"file": "NEWS.txt", "before": "re:^v\\d", "template": "v{v} — {msg}\n", "wrap": 30,
                "keep": 2, "tail": "Более ранние"}
        head = {"file": "app.py", "after": "Журнал:", "template": "v{v}: {msg}\n"}
        prog3 = dict(prog, headers=False, changelog=[news, head])
        cur, new, edits, notes = plan(prog3, "patch", ["первая строка довольно длинная", "вторая"], root=d)
        apply(edits, root=d)
        check(rd("NEWS.txt") == "Что нового\n\nv1.3.1 — первая строка\n         довольно длинная\n"
              "         вторая\nv1.3.0 — было 3\n\nБолее ранние — в git.\n", "журнал v{v} — {msg}: " + repr(rd("NEWS.txt")))
        check("Журнал:\nv1.3.1: первая строка довольно длинная\n        вторая\nv1.1.0: было" in rd("app.py"),
              "журнал в шапке: " + repr(rd("app.py")[:120]))
        # шапка «Version: X» и заголовок с названием
        check(update_header("# app.py\n# Version: 1.2.0\n", "1.3.0") == ("# app.py\n# Version: 1.3.0\n", True),
              "шапка Version:")
        check(update_header("Модуль. Версия 2.0\n", "2.1")[0] == "Модуль. Версия 2.1\n", "шапка Версия")
        t = changelog_insert("# Журнал\n\n## v1.0 — старое\n", {"file": "x", "before": "re:^## v",
                             "template": "## v{v} — {title}\n- {msg}\n\n"}, "1.1", ["а"], "Новое")
        check(t == "# Журнал\n\n## v1.1 — Новое\n- а\n\n## v1.0 — старое\n", "заголовок {title}: " + repr(t))
        t = changelog_insert("## v1.0\n", {"file": "x", "template": "## v{v} — {title}\n- {msg}\n\n"}, "1.1", ["а"])
        check(t.startswith("## v1.1\n- а\n"), "без названия — без «— »: " + repr(t))
        # одно число в шапке, программа в корне не трогает папку другой программы
        check(update_header("# dash v236\n", "237")[0] == "# dash v237\n", "шапка vNNN")
        os.makedirs(os.path.join(d, "mini"))
        with open(os.path.join(d, "mini", "m.py"), "w", encoding="utf-8") as f:
            f.write('"""m.py  v7.9.0"""\n')
        check("mini/m.py" not in changed_files({"dir": ""}, d, others=["", "mini"]), "чужая папка — не наша шапка")
        check("mini/m.py" in changed_files({"dir": "mini"}, d, others=["", "mini"]), "своя папка — наша шапка")
        # две программы с общим местом версии — вместе
        with open(os.path.join(d, "shared.bat"), "w", encoding="utf-8", newline="") as f:
            f.write("rem A v3.1.0\r\n")
        with open(os.path.join(d, "B_VERSION"), "w", encoding="utf-8") as f:
            f.write("3.1.0\n")
        with open(os.path.join(d, "A_VERSION"), "w", encoding="utf-8") as f:
            f.write("3.1.0\n")
        pa = {"name": "a", "files": [["A_VERSION", "{v}"], ["shared.bat", "A v{v}"]]}
        pb = {"name": "b", "files": [["B_VERSION", "{v}"], ["shared.bat", "A v{v}"]]}
        ed = {}
        plan(pa, "minor", [], root=d, edits=ed)
        plan(pb, "minor", [], root=d, edits=ed)
        apply(ed, root=d)
        check(rd("shared.bat") == "rem A v3.2.0\r\n" and rd("A_VERSION") == rd("B_VERSION") == "3.2.0\n",
              "общее место версии у двух программ")
        # откат — только с --force; "cont"; keep без лишней пустой строки перед tail
        try:
            bump("1.10.0", "1.9.0")
            errs.append("откат без --force — должна быть ошибка")
        except R.ReleaseError:
            pass
        check(bump("1.10.0", "1.9.0", force=True) == "1.9.0" and bump("1.9.0", "1.10.0") == "1.10.0", "откат с --force")
        t = changelog_insert("# Журнал:\n# v1.0: а\n", {"file": "x", "after": "# Журнал:", "template": "# v{v}: {msg}\n",
                             "wrap": 24, "cont": "#       "}, "1.1", ["слово слово слово слово"])
        check(t == "# Журнал:\n# v1.1: слово слово слово\n#       слово\n# v1.0: а\n", "cont: " + repr(t))
        t = changelog_insert("Журнал:\nv3: c\nv2: b\nv1: a\nРанее — в git.\n", {"file": "x", "before": "re:^v\\d",
                             "template": "v{v}: {msg}\n", "keep": 2, "tail": "Ранее"}, "4", ["d"])
        check(t == "Журнал:\nv4: d\nv3: c\nРанее — в git.\n", "keep без лишней пустой строки: " + repr(t))
        # без -t — без пустых скобок; перенос не по дефису
        t = changelog_insert("5.65:\n", {"file": "x", "template": "{v} ({title}):\n- {msg}\n"}, "5.66", ["а"])
        check(t.startswith("5.66:\n- а\n"), "пустые скобки ({title}): " + repr(t))
        t = changelog_insert("", {"file": "x", "template": "{v}: {msg}\n", "wrap": 26}, "1", ["аааа бббб по-прежнему"])
        check("по-\n" not in t and "по-прежнему" in t, "перенос по дефису: " + repr(t))
        # keep до конца файла (tail "")
        t = changelog_insert("H\n\n2.0:\n- b\n\n1.0:\n- a\n", {"file": "x", "before": "re:^\\d", "keep": 2,
                             "tail": "", "template": "{v}:\n- {msg}\n\n"}, "3.0", ["c"])
        check(t == "H\n\n3.0:\n- c\n\n2.0:\n- b\n", "keep до конца файла: " + repr(t))
        # расхождение — ничего не меняется
        with open(os.path.join(d, "build.bat"), "w", encoding="utf-8", newline="") as f:
            f.write("echo App v1.0.0\r\n")
        try:
            plan(prog, "patch", [], root=d)
            errs.append("расхождение версий — должна быть ошибка")
        except R.ReleaseError as e:
            check("build.bat" in str(e), f"в ошибке нет файла: {e}")
        check(rd("VERSION") == "1.3.1\n", "при ошибке файлы не тронуты")
    return errs


def main(argv):
    if "--selftest" in argv:
        problems = selftest()
        print(f"bump_version {VERSION}: " + ("OK" if not problems else "ОШИБКИ:\n  " + "\n  ".join(problems)))
        return 1 if problems else 0
    if "--check" in argv:
        return R.main(["--check"])
    msgs, rest, force, title = [], [], False, ""
    it = iter(argv)
    for a in it:
        if a == "-m":
            msgs.append(next(it, ""))
        elif a == "-t":
            title = next(it, "")
        elif a == "--force":
            force = True
        else:
            rest.append(a)
    try:
        cfg = R.load_config()
        names = {p["name"] for p in cfg["programs"]}
        prog_names = [a for a in rest if a in names]
        hows = [a for a in rest if a not in names]
        if len(hows) > 1:
            raise R.ReleaseError("лишние аргументы: " + " ".join(hows))
        how = hows[0] if hows else "patch"
        progs = R.pick(cfg, prog_names)
        dirs = [p.get("dir") or "" for p in cfg["programs"]]
        edits, report = {}, []
        for p in progs:                      # сначала все планы (ошибка — ничего не записано), потом запись
            cur, new, _, notes = plan(p, how, msgs, force=force, title=title, edits=edits, others=dirs)
            report.append((p["name"], cur, new, notes))
        apply(edits)
        for name, cur, new, notes in report:
            print(f"{name}: {cur} -> {new}")
            for n in notes:
                print("  " + n)
        print("Шапки остальных изменённых файлов и описание — проверьте вручную; потом commit и"
              " python release.py")
    except R.ReleaseError as e:
        print(f"ОШИБКА: {e} — файлы не тронуты")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
