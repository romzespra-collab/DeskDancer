"""app_log.py  v1.2.0 — общий модуль для всех проектов: журнал программы.

Журнал:
v1.2.0: сообщения Qt — в отдельный журнал «qt» (только в файл), а не в <имя>.qt: окно «Журнал» программы
        ими не засоряется; qt_logger= — свой журнал для них (file=False — по умолчанию <имя>.qt);
        токен бота Telegram скрывается и в адресе (…/bot<токен>/…); скрываются ещё pass= / key= / sid= /
        session= / cookie= и user:пароль@host без схемы; mask_handlers() не заменяет формат программы, а
        дополняет его скрытием (её собственное скрытие остаётся); проверочные строки selftest() не
        попадают в журнал программы, даже если она пишет через корневой журнал; add_file() — ещё один
        журнал в свой файл (журналы отдельных функций), не трогая главный; file=False — журналы общих
        модулей (safe_json, gh_update, app_icon) идут в обработчики журнала программы; Qt не установлен
        при setup() — install_qt_handler() позже; уровень журнала, уже заданный программой (DEBUG),
        setup() не сбивает (level=None по умолчанию).
v1.1.0: setup(..., file=False) — для программ со своим журналом (файл, окно «Журнал»): только
        следы падений, сообщения Qt и скрытие секретов в их обработчиках (mask_handlers).
v1.0.0: первая версия: файл с ротацией, следы падений, сообщения Qt, скрытие паролей и токенов.

Общий модуль: одинаковый во всех проектах. Правка — поднять версию в шапке и в VERSION ниже,
затем перенести файл ЦЕЛИКОМ во все проекты (свежий — с большим номером).

Что делает setup():
- файл <папка>/<имя>.log с ротацией (по умолчанию 1 МБ × 3); если файл держит вторая копия
  программы (WinError 32), ротация не падает — запись идёт дальше, повтор через минуту;
- падения: sys.excepthook и threading.excepthook — трассировка в журнал и в <имя>_crash.log
  (файл появляется только при падении); fault=True — ещё и faulthandler туда же (нарушение
  доступа в Qt / C-модуле оставляет след; на Windows он пишет и безвредные исключения COM / C++,
  поэтому по умолчанию выключен; пустой файл при обычном выходе удаляется);
- сообщения Qt (qWarning и т.п.) — в файл журнала (журнал «qt», в окно «Журнал» программы не идут),
  от уровня qt_level;
- пароли и токены (github_pat_…, ghp_…, password=…, token=…, логин:пароль@ в адресе) в журнал не
  попадают — заменяются на ***;
- журналы общих модулей (safe_json, gh_update, app_icon) пишутся в тот же файл.

API:
    log = app_log.setup("comic", log_dir)                  # logging.Logger("comic")
    log = app_log.setup("", log_dir, file_name="app.log", shared=())   # корневой журнал (пишут все
                                                           # модули программы; общие — и так в нём)
    log = app_log.setup("comic", log_dir, file_name="comic_project.log", max_bytes=1_000_000,
                        backups=3, level=None (INFO / как задано программой), fmt=..., datefmt=..., console=False,
                        crash=True, fault=False, qt=True, qt_level=logging.WARNING)
    app_log.get("net")          # logging.getLogger("comic.net")
    app_log.log_path() / app_log.crash_path() / app_log.logs_dir()
    app_log.mask_secrets(text)
    app_log.log_exception(exc_type, exc, tb)   # для своего excepthook программы (окно с ошибкой и т.п.)
    app_log.install_qt_handler()               # если Qt подключили позже setup()
Ещё журнал в свой файл (у отдельной функции), главный не трогается:
    lg = app_log.add_file("winhub.netwatch", path_to_log, max_bytes=1_000_000, backups=2, fmt=...)
Qt (PySide6) ставится после setup() — тогда после установки: app_log.install_qt_handler().
Программа со своим журналом (свой файл / окно «Журнал» / буфер):
    app_log.setup("smartmon", logs_dir, file=False)   # без второго файла: падения + Qt
    app_log.mask_handlers(logger)                     # её обработчикам — форматтер со скрытием секретов
"""
import atexit
import faulthandler
import logging
import os
import re
import sys
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler

VERSION = "1.2.0"

SHARED_LOGGERS = ("safe_json", "gh_update", "app_icon")
FMT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"
CRASH_MAX = 1_000_000          # след падений больше — оставить последние CRASH_KEEP байт
CRASH_KEEP = 256_000

_state = {"name": None, "logger": None, "dir": None, "path": None, "crash": None, "qt_logger": "qt",
          "handler": None, "qt_handler": None, "qt_level": logging.WARNING, "fault_file": None}
_lock = threading.RLock()

# ----------------------------------------------------------------- скрытие секретов
_TOKEN_RES = [
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"(?<!\d)\d{8,10}:AA[A-Za-z0-9_\-]{30,}"),      # токен бота Telegram (и в …/bot<токен>/)
]
_AUTH_RE = re.compile(r"(?i)(authorization\s*[:=]\s*[\"']?)(bearer|token|basic)\s+[^\s\"',;]+")
_KV_RE = re.compile(
    r"(?i)([\"']?\b(?:password|passwd|pwd|passw|pass|token|access_token|refresh_token|secret|"
    r"client_secret|api[_-]?key|apikey|access[_-]?key|key|auth|sid|session(?:_?id)?|cookie)[\"']?"
    r"\s*[:=]\s*[\"']?)([^\s\"'&;,}]+)")
_URL_RE = re.compile(r"(://[^/\s:@]+:)([^@\s/]+)(@)")
_USERPASS_RE = re.compile(r"(?<![:/\w@])([A-Za-z0-9._%+\-]+:)([^\s@/:]+)(@[A-Za-z0-9][A-Za-z0-9.\-]*)")


def mask_secrets(text):
    """Пароли и токены в строке -> ***."""
    if not text:
        return text
    s = str(text)
    for rx in _TOKEN_RES:
        s = rx.sub("***", s)
    s = _AUTH_RE.sub(r"\1\2 ***", s)
    s = _KV_RE.sub(r"\1***", s)
    s = _URL_RE.sub(r"\1***\3", s)
    s = _USERPASS_RE.sub(r"\1***\3", s)
    return s


class MaskingFormatter(logging.Formatter):
    """Форматтер, который скрывает секреты и в сообщении, и в трассировке."""

    def format(self, record):
        return mask_secrets(super().format(record))


class _MaskAround(logging.Formatter):
    """Формат программы как есть (и её скрытие) + наше скрытие поверх (mask_handlers)."""

    def __init__(self, inner):
        super().__init__()
        self.inner = inner

    def format(self, record):
        return mask_secrets(self.inner.format(record))


# ----------------------------------------------------------------- файл с ротацией
class SafeRotatingFileHandler(RotatingFileHandler):
    """Ротация не падает, если файл держит другая копия программы (Windows: WinError 32):
    пишем дальше в тот же файл и пробуем снова через минуту."""

    _retry_at = 0.0

    def shouldRollover(self, record):
        if self._retry_at > time.monotonic():
            return False
        try:
            return super().shouldRollover(record)
        except OSError:
            return False

    def doRollover(self):
        try:
            super().doRollover()
        except OSError:
            self._retry_at = time.monotonic() + 60
            if self.stream is None:
                try:
                    self.stream = self._open()
                except OSError:
                    pass


# ----------------------------------------------------------------- падения
def _trim_crash(path):
    try:
        if os.path.getsize(path) > CRASH_MAX:
            with open(path, "rb") as f:
                f.seek(-CRASH_KEEP, os.SEEK_END)
                tail = f.read()
            with open(path, "wb") as f:
                f.write("... (начало обрезано)\n".encode("utf-8") + tail)
    except OSError:
        pass


def _write_crash(text):
    path = _state["crash"]
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{mask_secrets(text)}\n")
    except OSError:
        pass


def log_exception(exc_type, exc, tb, where=""):
    """Трассировку — в журнал и в след падений. Для своего excepthook программы."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    lg = _state["logger"] or logging.getLogger()
    lg.critical("Необработанная ошибка%s:\n%s", f" ({where})" if where else "", text.rstrip())
    _write_crash(text)


def _close_fault_file():
    """При обычном выходе: faulthandler выключить, пустой след падений удалить."""
    f = _state.get("fault_file")
    if f is None:
        return
    try:
        faulthandler.disable()
        f.close()
        if os.path.getsize(f.name) == 0:
            os.remove(f.name)
    except Exception:                                 # noqa: BLE001
        pass
    _state["fault_file"] = None


def _install_crash_hooks(fault=False):
    prev = sys.excepthook

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return prev(exc_type, exc, tb)
        try:
            log_exception(exc_type, exc, tb)
        except Exception:                             # noqa: BLE001 — журнал не должен ронять
            pass
        try:
            if prev not in (sys.__excepthook__, None) or sys.stderr is not None:
                prev(exc_type, exc, tb)
        except Exception:                             # noqa: BLE001
            pass

    hook._app_log = True
    if not getattr(sys.excepthook, "_app_log", False):
        sys.excepthook = hook

    prev_t = threading.excepthook

    def thook(args):
        if args.exc_type is SystemExit:
            return
        try:
            name = getattr(args.thread, "name", "?")
            log_exception(args.exc_type, args.exc_value, args.exc_traceback, f"поток {name}")
        except Exception:                             # noqa: BLE001
            pass
        try:
            if prev_t is not threading.__excepthook__ or sys.stderr is not None:
                prev_t(args)
        except Exception:                             # noqa: BLE001
            pass

    thook._app_log = True
    if not getattr(threading.excepthook, "_app_log", False):
        threading.excepthook = thook

    # нарушение доступа и т.п. — след от faulthandler в тот же файл (по желанию)
    if fault and _state["fault_file"] is None and _state["crash"]:
        try:
            f = open(_state["crash"], "a", encoding="utf-8")
            faulthandler.enable(f, all_threads=True)
            _state["fault_file"] = f
            atexit.register(_close_fault_file)
        except (OSError, RuntimeError, ValueError):
            pass


# ----------------------------------------------------------------- Qt
_QT_LEVELS = {}


def _qt_log(lvl, msg):
    if lvl < _state["qt_level"]:
        return
    try:
        logging.getLogger(_state.get("qt_logger") or "qt").log(lvl, "%s", msg)
    except Exception:                                 # noqa: BLE001
        pass


def install_qt_handler(level=None):
    """Сообщения Qt -> журнал (<имя>.qt). True — поставлен."""
    if level is not None:
        _state["qt_level"] = level
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception:                                 # noqa: BLE001 — без Qt
        return False
    if not _QT_LEVELS:
        _QT_LEVELS.update({
            QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
            QtMsgType.QtFatalMsg: logging.CRITICAL})

    def handler(mode, ctx, msg):
        _qt_log(_QT_LEVELS.get(mode, logging.WARNING), msg)

    _state["qt_handler"] = handler
    qInstallMessageHandler(handler)
    return True


# ----------------------------------------------------------------- настройка
def setup(name, log_dir, *, file_name=None, level=None, max_bytes=1_000_000, backups=3,
          fmt=FMT, datefmt=DATEFMT, console=False, crash=True, fault=False, qt=True,
          qt_level=logging.WARNING, shared=SHARED_LOGGERS, file=True, qt_logger=None):
    """Журнал программы. Повторный вызов не плодит обработчики. Папку не создать — журнал без файла.
    level — уровень журнала (по умолчанию INFO, но уже заданный программой не меняется).
    file=False — свой файл не заводить (у программы свой журнал): следы падений, сообщения Qt.
    qt_logger — журнал для сообщений Qt: по умолчанию «qt» (только файл) или <имя>.qt при file=False."""
    with _lock:
        logger = logging.getLogger(name)
        if level is not None:
            logger.setLevel(level)
        elif logger.level == logging.NOTSET:
            logger.setLevel(logging.INFO)            # уровень, уже заданный программой, не трогаем
        level = logger.level
        _state["name"] = name
        _state["logger"] = logger
        _state["qt_level"] = qt_level
        log_dir = os.path.abspath(os.fspath(log_dir))
        _state["dir"] = log_dir
        path = os.path.join(log_dir, file_name or f"{name}.log")
        _state["path"] = path
        stem = os.path.splitext(os.path.basename(path))[0]
        _state["crash"] = os.path.join(log_dir, f"{stem}_crash.log") if crash else None

        formatter = MaskingFormatter(fmt, datefmt)
        h = _state["handler"]
        if not file:
            if h is not None:
                for lg in (logger, *(logging.getLogger(n) for n in shared)):
                    lg.removeHandler(h)
                h.close()
            h = _state["handler"] = None
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError:
                pass
            if name:                      # общие модули — в обработчики журнала программы
                for n in shared:
                    lg = logging.getLogger(n)
                    if n != name and not lg.handlers:
                        lg.addHandler(_Forward(logger))
                        lg.propagate = False
                        if lg.level == logging.NOTSET or lg.level > level:
                            lg.setLevel(level)
        elif h is None or getattr(h, "baseFilename", None) != os.path.abspath(path):
            if h is not None:
                for lg in (logger, *(logging.getLogger(n) for n in shared)):
                    lg.removeHandler(h)
                h.close()
            try:
                os.makedirs(log_dir, exist_ok=True)
                h = SafeRotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups,
                                            encoding="utf-8", delay=True)
            except OSError:
                h = None
            _state["handler"] = h
        _state["qt_logger"] = qt_logger or ("qt" if h is not None or not name else f"{name}.qt")
        if h is not None:
            h.setFormatter(formatter)
            if h not in logger.handlers:
                logger.addHandler(h)
            for n in (*shared, _state["qt_logger"]):
                lg = logging.getLogger(n)
                if n != name and not lg.handlers:
                    lg.addHandler(h)
                    lg.propagate = False
                    if lg.level == logging.NOTSET or lg.level > level:
                        lg.setLevel(level)
        if console and sys.stderr is not None and not any(
                getattr(x, "_app_log_console", False) for x in logger.handlers):
            ch = logging.StreamHandler()
            ch.setFormatter(formatter)
            ch._app_log_console = True
            logger.addHandler(ch)
        if crash and _state["crash"] and (h is not None or not file):
            _trim_crash(_state["crash"])
            _install_crash_hooks(fault)
        if qt and _state["qt_handler"] is None:
            install_qt_handler()
        return logger


def mask_handlers(logger, fmt=None, datefmt=None):
    """Обработчикам logger — скрытие паролей и токенов поверх их формата (свой формат и своё скрытие
    программы остаются). fmt / datefmt — только для обработчиков без формата. Возвращает, скольким."""
    n = 0
    for h in list(getattr(logger, "handlers", ())):
        f = h.formatter
        if isinstance(f, (MaskingFormatter, _MaskAround)):
            continue
        h.setFormatter(_MaskAround(f) if f is not None else MaskingFormatter(fmt or FMT, datefmt or DATEFMT))
        n += 1
    return n


def add_file(logger_name, path, *, max_bytes=1_000_000, backups=3, fmt=FMT, datefmt=DATEFMT,
             level=None, propagate=None):
    """Ещё один журнал в свой файл (ротация, скрытие секретов), главный журнал (setup) не трогается.
    Повторный вызов с тем же файлом не плодит обработчики. Папку не создать — журнал без файла."""
    lg = logging.getLogger(logger_name)
    full = os.path.abspath(os.fspath(path))
    if level is not None:
        lg.setLevel(level)
    if propagate is not None:
        lg.propagate = propagate
    for h in lg.handlers:
        if getattr(h, "baseFilename", None) == full:
            return lg
    try:
        os.makedirs(os.path.dirname(full), exist_ok=True)
        h = SafeRotatingFileHandler(full, maxBytes=max_bytes, backupCount=backups, encoding="utf-8", delay=True)
    except OSError:
        return lg
    h.setFormatter(MaskingFormatter(fmt, datefmt))
    lg.addHandler(h)
    return lg


class _Forward(logging.Handler):
    """Записи общих модулей -> обработчики журнала программы (file=False)."""

    def __init__(self, target):
        super().__init__()
        self.target = target

    def emit(self, record):
        try:
            for h in self.target.handlers:
                if record.levelno >= h.level:
                    h.handle(record)
        except Exception:                             # noqa: BLE001
            pass


def get(sub=""):
    base = _state["logger"] or logging.getLogger()
    return base.getChild(sub) if sub else base


def log_path():
    return _state["path"]


def crash_path():
    return _state["crash"]


def logs_dir():
    return _state["dir"]


# ----------------------------------------------------------------- самопроверка
def selftest():
    """Пустой список — всё в порядке, иначе — тексты ошибок."""
    import io
    import tempfile
    errs = []

    def check(cond, text):
        if not cond:
            errs.append(text)

    tok = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    pat = "github_pat_" + "11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz"
    tg = "123456789:AA" + "Bb1" * 11
    m = mask_secrets(f"t={tok} p={pat} password=qwerty url=rtsp://admin:12345@10.0.0.1/ "
                     f"Authorization: Bearer abc.def \"token\": \"xyz123\" "
                     f"https://api.telegram.org/bot{tg}/sendMessage")
    for bad in (tok, pat, "qwerty", "12345", "abc.def", "xyz123", tg[10:]):
        check(bad not in m, f"секрет не скрыт: {bad[:8]}… -> {m}")
    check("rtsp://admin:***@10.0.0.1" in m, f"адрес с паролем: {m}")
    check(mask_secrets("pass 3 of 5, timeout=10, hotkey=F5") == "pass 3 of 5, timeout=10, hotkey=F5", "лишнее скрыто")
    m2 = mask_secrets("pass=p1 key=k2 sid=s3 cookie=c4 proxy admin:pw5@10.0.0.2:8080 mail a@b.ru")
    for bad in ("p1", "k2", "s3", "c4", "pw5"):
        check(bad not in m2, f"не скрыто {bad}: {m2}")
    check("admin:***@10.0.0.2" in m2 and "a@b.ru" in m2, f"user:пароль@host: {m2}")

    # проверка не мешает журналу самой программы: своё состояние, свой «общий» журнал
    saved_hooks = (sys.excepthook, threading.excepthook)
    saved_state = dict(_state)
    fault_was = faulthandler.is_enabled()
    _state.update(name=None, logger=None, dir=None, path=None, crash=None, handler=None, fault_file=None)
    shared = ("app_log_test_shared",)
    test_names = ("app_log_test", "app_log_test_own", "app_log_test_qt", "app_log_test_sh2", "app_log_test_extra",
                  *shared)
    for n in test_names:               # проверочные строки — не в корневой журнал программы
        logging.getLogger(n).propagate = False
    with tempfile.TemporaryDirectory() as d:
        try:
            kw = dict(max_bytes=2000, backups=2, qt=False, shared=shared, qt_logger="app_log_test_qt")
            lg = setup("app_log_test", os.path.join(d, "logs"), **kw)
            lg2 = setup("app_log_test", os.path.join(d, "logs"), **kw)
            check(lg is lg2 and sum(isinstance(x, SafeRotatingFileHandler) for x in lg.handlers) == 1,
                  "повторный setup — один обработчик")
            lg.info("пароль: password=secret1 и токен %s", tok)
            for i in range(200):
                get("sub").info("строка %d %s", i, "x" * 40)
            logging.getLogger(shared[0]).warning("сообщение общего модуля")
            try:
                raise RuntimeError("проверка token=abc999")
            except RuntimeError:
                log_exception(*sys.exc_info())
            for x in lg.handlers:
                x.flush()
            files = sorted(os.listdir(os.path.join(d, "logs")))
            check("app_log_test.log" in files and "app_log_test.log.1" in files, f"ротация: {files}")
            check(len([f for f in files if f.startswith("app_log_test.log")]) <= 3, f"копий не больше 2: {files}")
            text = "".join(open(os.path.join(d, "logs", f), encoding="utf-8").read()
                           for f in files if f.startswith("app_log_test.log"))
            check("secret1" not in text and tok not in text and "abc999" not in text, "секреты в файле журнала")
            check("app_log_test.sub" in text, "дочерний журнал в файле")
            check("сообщение общего модуля" in text, "журнал общего модуля — в файле программы")
            crash = open(crash_path(), encoding="utf-8").read()
            check("RuntimeError" in crash and "abc999" not in crash, "след падения")
            check(getattr(sys.excepthook, "_app_log", False), "sys.excepthook поставлен")
            check(getattr(threading.excepthook, "_app_log", False), "threading.excepthook поставлен")
            err, sys.stderr = sys.stderr, None          # без вывода трассировки в консоль
            try:
                t = threading.Thread(target=lambda: 1 / 0, name="проба")
                t.start()
                t.join()
            finally:
                sys.stderr = err
            crash = open(crash_path(), encoding="utf-8").read()
            check("ZeroDivisionError" in crash, "падение в потоке")
            check(lg.level == logging.INFO, "уровень по умолчанию INFO")
            dbg = logging.getLogger("app_log_test_sh2")
            dbg.setLevel(logging.DEBUG)
            setup("app_log_test_sh2", os.path.join(d, "dbg"), file=False, crash=False, qt=False, shared=())
            check(dbg.level == logging.DEBUG, "уровень, заданный программой, не сбит")
            dbg.setLevel(logging.NOTSET)
            setup("app_log_test", os.path.join(d, "logs"), **kw)      # вернуть проверочное состояние
            # сообщения Qt — в файл, но не в обработчики программы
            seen = []
            spy = logging.Handler()
            spy.emit = lambda r: seen.append(r.getMessage())
            lg.addHandler(spy)
            try:
                _qt_log(logging.WARNING, "qt-проба")
            finally:
                lg.removeHandler(spy)
            for x in logging.getLogger("app_log_test_qt").handlers:
                x.flush()
            text = open(os.path.join(d, "logs", "app_log_test.log"), encoding="utf-8").read()
            check("qt-проба" in text and "qt-проба" not in seen, "Qt: в файл, мимо окна программы")
            # своя программа со своим журналом: file=False + mask_handlers
            own = logging.getLogger("app_log_test_own")
            sh = logging.StreamHandler(io.StringIO())
            sh.setFormatter(logging.Formatter("%(message)s"))
            own.addHandler(sh)
            try:
                setup("app_log_test_own", os.path.join(d, "own"), file=False, qt=False, shared=())
                sh.setFormatter(logging.Formatter("[своё] %(message)s"))
                check(mask_handlers(own) == 1, "mask_handlers")
                own.warning("token=zzz777")
                out = sh.stream.getvalue()
                check("zzz777" not in out and "[своё]" in out, f"mask_handlers: скрыто и формат свой: {out!r}")
                check(not os.path.exists(os.path.join(d, "own", "app_log_test_own.log")), "file=False — файла нет")
                try:
                    raise ValueError("own")
                except ValueError:
                    log_exception(*sys.exc_info())
                check("ValueError" in open(crash_path(), encoding="utf-8").read(), "file=False — след падения есть")
                check(_state["handler"] is None, "file=False — без своего обработчика")
                setup("app_log_test_own", os.path.join(d, "own"), file=False, qt=False, shared=("app_log_test_sh2",))
                logging.getLogger("app_log_test_sh2").warning("общий модуль при file=False")
                check("общий модуль при file=False" in sh.stream.getvalue(), "file=False — общие модули в журнал программы")
                for x in logging.getLogger("app_log_test_sh2").handlers[:]:
                    logging.getLogger("app_log_test_sh2").removeHandler(x)
                extra = add_file("app_log_test_extra", os.path.join(d, "extra", "f.log"), propagate=False)
                add_file("app_log_test_extra", os.path.join(d, "extra", "f.log"))
                extra.warning("доп password=pp9")
                for x in extra.handlers:
                    x.flush()
                t2 = open(os.path.join(d, "extra", "f.log"), encoding="utf-8").read()
                check(len(extra.handlers) == 1 and "доп" in t2 and "pp9" not in t2, "add_file")
                for x in extra.handlers[:]:
                    extra.removeHandler(x)
                    x.close()
            finally:
                own.removeHandler(sh)
        finally:
            for n in test_names:          # проверочные журналы — пустые, как были
                x = logging.getLogger(n)
                for h in x.handlers[:]:
                    x.removeHandler(h)
                    try:
                        h.close()
                    except Exception:                 # noqa: BLE001
                        pass
                x.propagate = True
            if _state["fault_file"] is not None:
                try:
                    faulthandler.disable()
                    _state["fault_file"].close()
                except Exception:                     # noqa: BLE001
                    pass
            sys.excepthook, threading.excepthook = saved_hooks
            _state.clear()
            _state.update(saved_state)
            try:
                if saved_state["fault_file"] is not None:
                    faulthandler.enable(saved_state["fault_file"], all_threads=True)
                elif fault_was:
                    faulthandler.enable()
            except Exception:                         # noqa: BLE001
                pass
    return errs


if __name__ == "__main__":
    problems = selftest()
    print(f"app_log {VERSION}: " + ("OK" if not problems else "ОШИБКИ:\n  " + "\n  ".join(problems)))
    sys.exit(1 if problems else 0)
