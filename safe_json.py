"""safe_json.py  v1.1.1 — общий модуль для всех проектов: надёжное чтение и запись JSON
(config.json, файлы состояния).

Журнал:
v1.1.1: файл, который программа сама записала, а потом его испортили извне (вторая копия программы,
        правка руками), больше не попадает в .bak: перед копией в .bak проверяется, тот ли это файл
        (время и размер), иначе — разбор; kind=(list, dict) — кортеж типов (было AttributeError в сообщении);
        самопроверка закрывает файлы (без ResourceWarning).
v1.1.0: битый файл, который читают снова и снова, не плодит копии .bad- и не повторяет сообщение в журнале;
        запрет записи снимается, только если файл удалили (файл снова читается / исправлен — запрет
        остаётся до следующего load: иначе значения по умолчанию затёрли бы настоящие настройки);
        load_state(path) — как прочитан файл (ok / missing / bak / default / unreadable); allow_write(path) —
        снять запрет по решению пользователя (сохранить принудительно); ошибка записи — в журнал один раз,
        пока она та же; в last_error — и тип ошибки (PermissionError: …); файл занят / не читается —
        берётся .bak (если есть; запись всё равно запрещена); protect=False — для кэша: испорченный
        файл (копия .bad- остаётся) можно перезаписать.
v1.0.0: первая версия: load / save / AutoSaver / start_autosave.

Общий модуль: одинаковый во всех проектах. Правка — поднять версию в шапке и в VERSION ниже,
затем перенести файл ЦЕЛИКОМ во все проекты (свежий — с большим номером).

Правила:
- запись атомарная: <файл>.<pid>-<n>.tmp -> os.replace; повтор, если файл держат антивирус /
  OneDrive / вторая копия программы (WinError 5 / 32);
- перед заменой прежний ЦЕЛЫЙ файл копируется в <файл>.bak (тоже атомарно);
- чтение — с повтором (файл держат) и utf-8-sig (файл правили Блокнотом с BOM);
- битый JSON не читается как пустой: берётся <файл>.bak; копия битого — <файл>.bad-<время>;
  если и .bak нет / битый — настройки по умолчанию, а сам файл НЕ перезаписывается
  (save -> False), пока его не исправят или не удалят;
- файл есть, но не читается совсем (нет прав, занят) — то же: значения по умолчанию, запись запрещена.

API:
    data = safe_json.load(path, default)     # default копируется (deepcopy); тип проверяется по default
    data = safe_json.load(cache, {}, protect=False)   # кэш: испорченный можно перезаписать
    ok = safe_json.save(path, data)          # True / False; причина — safe_json.last_error(path)
    safe_json.is_protected(path)             # файл испорчен / не читался — запись запрещена
    safe_json.load_state(path)               # "ok" | "missing" | "bak" (взята копия) | "default" | "unreadable"
    safe_json.allow_write(path)              # снять запрет записи (пользователь сам решил сохранить)
    saver = safe_json.AutoSaver(path, get_data, every=10)   # пишет, только если данные изменились
    saver.mark_saved(data)                   # после load: «это уже на диске»
    saver.tick() / saver.flush()             # по таймеру / при закрытии
    timer = safe_json.start_autosave(window, saver)          # QTimer раз в every с + запись при выходе

Журнал модуля — logging.getLogger("safe_json") (app_log.setup подключает его к журналу программы).
"""
import copy
import json
import logging
import os
import shutil
import threading
import time

VERSION = "1.1.1"

log = logging.getLogger("safe_json")

_lock = threading.RLock()
_protected = {}      # ключ пути -> почему запись запрещена
_errors = {}         # ключ пути -> текст последней ошибки
_good = {}           # ключ пути -> (время, размер) целого файла, прочитанного или записанного нами
_load_state = {}     # ключ пути -> как прочитан последним load()
_reported = {}       # ключ пути -> (состояние файла, текст) последнего сообщения о битом / нечитаемом файле
_save_err = {}       # ключ пути -> текст ошибки записи, о которой уже написали в журнал
_tmp_n = 0


def _key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_busy(e):
    """Файл держит другой процесс (WinError 5 / 32) — стоит повторить."""
    return isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32, 33)


def _read_text(path, tries=5):
    """Текст файла. FileNotFoundError — как есть; не читается после повторов — OSError;
    не UTF-8 — ValueError (содержимое испорчено)."""
    last = None
    for i in range(tries):
        try:
            with open(path, "rb") as f:
                raw = f.read()
            try:
                return raw.decode("utf-8-sig")
            except UnicodeDecodeError as e:
                raise ValueError(f"не UTF-8: {e}") from None
        except FileNotFoundError:
            raise
        except OSError as e:
            last = e
            time.sleep(0.2 * (i + 1))
    raise last


def _kind_of(default, kind):
    if kind is not None:
        return kind
    if isinstance(default, (dict, list)):
        return type(default)
    return None


def _parse(text, kind):
    """(True, данные) или (False, причина)."""
    try:
        data = json.loads(text)
    except ValueError as e:
        return False, f"битый JSON: {e}"
    if kind is not None and not isinstance(data, kind):
        want = " / ".join(k.__name__ for k in kind) if isinstance(kind, tuple) else kind.__name__
        return False, f"ожидался {want}, а в файле {type(data).__name__}"
    return True, data


def _same_bad_copy(path):
    """Уже есть копия .bad- с тем же содержимым — её имя (чтобы не плодить копии при каждом чтении)."""
    d = os.path.dirname(os.path.abspath(path))
    base = os.path.basename(path) + ".bad-"
    try:
        size = os.path.getsize(path)
        names = [n for n in os.listdir(d) if n.startswith(base)]
    except OSError:
        return None
    data = None
    for n in sorted(names, reverse=True):
        full = os.path.join(d, n)
        try:
            if os.path.getsize(full) != size:
                continue
            if data is None:
                with open(path, "rb") as f:
                    data = f.read()
            with open(full, "rb") as f:
                if f.read() == data:
                    return full
        except OSError:
            continue
    return None


def _keep_bad_copy(path):
    """Копия испорченного файла рядом: <файл>.bad-<время> (байт в байт). Имя копии или None."""
    same = _same_bad_copy(path)
    if same:
        return same
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bad = f"{path}.bad-{stamp}"
    n = 1
    while os.path.exists(bad):
        n += 1
        bad = f"{path}.bad-{stamp}-{n}"
    try:
        shutil.copyfile(path, bad)
        return bad
    except OSError as e:
        log.error("копию испорченного %s не сделать: %s", path, e)
        return None


def _sig(p):
    try:
        st = os.stat(p)
        return st.st_mtime_ns, st.st_size
    except OSError:
        return None


def _report(k, p, level, text):
    """Сообщение о битом / нечитаемом файле — один раз на одно и то же состояние файла."""
    key = (_sig(p), text)
    if _reported.get(k) == key:
        log.debug("%s", text)
        return
    _reported[k] = key
    log.log(level, "%s", text)


def _read_bak(p, want):
    """(True, данные) из <файл>.bak или (False, причина)."""
    if not os.path.exists(p + ".bak"):
        return False, "нет .bak"
    try:
        return _parse(_read_text(p + ".bak"), want)
    except (OSError, ValueError) as e:
        return False, str(e)


def load(path, default=None, *, bak=True, kind=None, protect=True):
    """Прочитать JSON. Нет файла — копия default. Испорчен — .bak, иначе default и запрет записи.
    Не читается (занят, нет прав) — .bak (или default), запись запрещена до следующего load.
    kind — нужный тип (dict / list); по умолчанию — тип default, если это dict / list.
    protect=False (кэш, который можно собрать заново) — испорченный файл можно перезаписать."""
    p = os.fspath(path)
    k = _key(p)
    want = _kind_of(default, kind)
    with _lock:
        _protected.pop(k, None)
        _errors.pop(k, None)
        _good.pop(k, None)
        try:
            text = _read_text(p)
        except FileNotFoundError:
            _load_state[k] = "missing"
            return copy.deepcopy(default)
        except ValueError as e:          # не UTF-8 — как битый JSON
            reason = str(e)
        except OSError as e:
            _protected[k] = f"файл не читается: {type(e).__name__}: {e}"
            _errors[k] = _protected[k]
            _load_state[k] = "unreadable"
            ok, res = _read_bak(p, want) if bak else (False, "")
            _report(k, p, logging.ERROR, f"{p} не читается ({e}) — "
                    + ("взята резервная копия .bak" if ok else "значения по умолчанию")
                    + ", файл не перезаписываю")
            return res if ok else copy.deepcopy(default)
        else:
            ok, res = _parse(text, want)
            if ok:
                _good[k] = _sig(p)
                _load_state[k] = "ok"
                _reported.pop(k, None)
                return res
            reason = res
        # файл испорчен
        bad_copy = _keep_bad_copy(p)
        if bak and os.path.exists(p + ".bak"):
            ok, res = _read_bak(p, want)
            if ok:
                _load_state[k] = "bak"
                _report(k, p, logging.WARNING, f"{p} испорчен ({reason}) — взята резервная копия .bak"
                        + (f"; испорченный сохранён: {os.path.basename(bad_copy)}" if bad_copy else ""))
                if not bad_copy:
                    # копию испорченного не сделать — его не затираем
                    _protected[k] = "испорченный файл не удалось сохранить в копию — не перезаписываю"
                    _errors[k] = _protected[k]
                return res
        _load_state[k] = "default"
        if not protect and bad_copy:     # кэш: копия есть — можно собрать и записать заново
            _report(k, p, logging.WARNING, f"{p} испорчен ({reason}) — значения по умолчанию"
                    f" (копия: {os.path.basename(bad_copy)})")
            return copy.deepcopy(default)
        _protected[k] = (f"файл испорчен ({reason}); исправьте или удалите его"
                         + (f" (копия: {os.path.basename(bad_copy)})" if bad_copy else ""))
        _errors[k] = _protected[k]
        _report(k, p, logging.ERROR, f"{p}: {_protected[k]} — значения по умолчанию, файл не перезаписываю")
        return copy.deepcopy(default)


def is_protected(path):
    return _key(path) in _protected


def last_error(path):
    return _errors.get(_key(path), "")


def allow_write(path):
    """Снять запрет записи (пользователь сам решил сохранить поверх испорченного / нечитаемого файла)."""
    k = _key(path)
    with _lock:
        _protected.pop(k, None)
        _errors.pop(k, None)


def load_state(path):
    """Как прочитан файл последним load(): "ok", "missing" (нет файла — значения по умолчанию),
    "bak" (файл испорчен — взята резервная копия), "default" (испорчен, копии нет — значения по
    умолчанию, запись запрещена), "unreadable" (не читается — то же). "" — load() не вызывали."""
    return _load_state.get(_key(path), "")


def _still_protected(p, k):
    """Запрет снимается, только если файл удалили (пользователь сбросил настройки). Снова читается /
    исправлен — запрет остаётся: в памяти программы значения по умолчанию, запись затёрла бы настоящие
    настройки; их подхватит следующий load() (перезапуск программы)."""
    if not os.path.exists(p):
        return False
    try:
        ok, _ = _parse(_read_text(p, tries=1), None)
    except (OSError, ValueError):
        ok = False
    if ok:
        _errors[k] = ("файл снова читается — перечитайте настройки (перезапуск программы); запись "
                      "запрещена, чтобы не затереть их значениями по умолчанию")
    return True


def dumps(data, indent=2):
    return json.dumps(data, ensure_ascii=False, indent=indent)


def _replace(src, dst, tries=8):
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except OSError as e:
            if not _is_busy(e) or i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))


def _backup(p, k):
    """Прежний целый файл -> <файл>.bak (через .tmp и replace). Ошибка копии не мешает записи."""
    if not os.path.exists(p):
        return
    if _good.get(k) is None or _good.get(k) != _sig(p):     # файл меняли не мы — проверить, целый ли
        try:
            ok, _ = _parse(_read_text(p, tries=2), None)
        except (OSError, ValueError):
            ok = False
        if not ok:
            return                      # испорченный файл в .bak не кладём
    tmp = _tmp_name(p + ".bak")
    try:
        shutil.copyfile(p, tmp)
        _replace(tmp, p + ".bak")
    except OSError as e:
        log.warning("резервная копия %s.bak не сделана: %s", p, e)
        try:
            os.remove(tmp)
        except OSError:
            pass


def _tmp_name(p):
    global _tmp_n
    _tmp_n += 1
    return f"{p}.{os.getpid()}-{_tmp_n}.tmp"


def save_text(path, text, *, bak=True):
    """Записать готовый текст JSON атомарно. True / False (причина — last_error)."""
    p = os.fspath(path)
    k = _key(p)
    with _lock:
        if k in _protected:
            _errors[k] = _protected[k]
            if _still_protected(p, k):
                return False
            log.info("%s исправлен или удалён — запись снова разрешена", p)
            _protected.pop(k, None)
        d = os.path.dirname(os.path.abspath(p))
        tmp = _tmp_name(p)
        try:
            os.makedirs(d, exist_ok=True)
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            if bak:
                _backup(p, k)
            _replace(tmp, p)
        except OSError as e:
            err = f"{type(e).__name__}: {e}"
            _errors[k] = err
            _good.pop(k, None)
            if _save_err.get(k) != err:             # та же ошибка снова — в журнал не повторять
                _save_err[k] = err
                log.error("%s НЕ сохранён: %s", p, err)
            else:
                log.debug("%s НЕ сохранён: %s", p, err)
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False
        _errors.pop(k, None)
        _save_err.pop(k, None)
        _good[k] = _sig(p)
        return True


def save(path, data, *, bak=True, indent=2):
    """Записать данные атомарно. Не сериализуется — False, файл не тронут."""
    try:
        text = dumps(data, indent)
    except (TypeError, ValueError) as e:
        _errors[_key(path)] = f"данные не записать в JSON: {e}"
        log.error("%s НЕ сохранён: %s", os.fspath(path), _errors[_key(path)])
        return False
    return save_text(path, text, bak=bak)


class AutoSaver:
    """Автосохранение: tick() пишет файл, только если данные изменились (и не чаще every с)."""

    def __init__(self, path, get_data, every=10.0, *, bak=True, indent=2):
        self.path = path
        self.get_data = get_data
        self.every = float(every)
        self.bak = bak
        self.indent = indent
        self._last = None
        self._next = 0.0

    def mark_saved(self, data=None):
        """Данные уже на диске (сразу после load) — первый tick не пишет без изменений."""
        try:
            self._last = dumps(self.get_data() if data is None else data, self.indent)
        except (TypeError, ValueError):
            self._last = None

    def changed(self):
        try:
            return dumps(self.get_data(), self.indent) != self._last
        except (TypeError, ValueError):
            return True

    def tick(self, force=False):
        """None — писать нечего / рано; True / False — итог записи."""
        now = time.monotonic()
        if not force and now < self._next:
            return None
        self._next = now + self.every
        try:
            text = dumps(self.get_data(), self.indent)
        except Exception as e:                      # noqa: BLE001 — данные программы
            log.error("%s: данные не собрать для записи: %s", os.fspath(self.path), e)
            return False
        if text == self._last:
            return None
        ok = save_text(self.path, text, bak=self.bak)
        if ok:
            self._last = text
        return ok

    def flush(self):
        return self.tick(force=True)


def start_autosave(parent, saver):
    """QTimer (PySide6) раз в saver.every с + запись при выходе из программы. Возвращает таймер."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    t = QTimer(parent)
    t.setInterval(max(1000, int(saver.every * 1000)))
    t.timeout.connect(lambda: saver.tick(force=True))
    t.start()
    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(saver.flush)
    return t


# ----------------------------------------------------------------- самопроверка
def selftest():
    """Пустой список — всё в порядке, иначе — тексты ошибок."""
    errs = []

    def check(cond, text):
        if not cond:
            errs.append(text)

    was = log.disabled
    log.disabled = True              # проверочные «ошибки» — не в журнал программы
    try:
        _selftest_body(check)
    finally:
        log.disabled = was
    return errs


def _selftest_body(check):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "sub", "config.json")
        dflt = {"a": 1, "list": [1]}
        x = load(p, dflt)
        check(x == dflt and x is not dflt and x["list"] is not dflt["list"], "нет файла -> копия default")
        check(load_state(p) == "missing", "load_state missing")
        check(save(p, {"a": 2, "т": "я"}), "первая запись")
        check(load(p, dflt) == {"a": 2, "т": "я"} and load_state(p) == "ok", "чтение записанного")
        check(not os.path.exists(p + ".bak"), "нет .bak до второй записи")
        check(save(p, {"a": 3}), "вторая запись")
        check(load(p + ".bak", {}) == {"a": 2, "т": "я"}, ".bak — прежняя версия")
        check(not [f for f in os.listdir(os.path.dirname(p)) if f.endswith(".tmp")], "нет .tmp после записи")
        # BOM (Блокнот)
        with open(p, "w", encoding="utf-8-sig") as f:
            f.write('{"a": 4}')
        check(load(p, dflt) == {"a": 4}, "utf-8-sig")
        check(save(p, {"a": 5}), "запись после BOM")
        # битый -> .bak
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"a": 6,')
        x = load(p, dflt)
        check(x == {"a": 4} and load_state(p) == "bak", f"битый -> .bak (получено {x})")
        check(any(".bad-" in f for f in os.listdir(os.path.dirname(p))), "копия битого .bad-")
        n_bad = len([f for f in os.listdir(os.path.dirname(p)) if ".bad-" in f])
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"a": 6,')
        load(p, dflt)
        load(p, dflt)
        check(len([f for f in os.listdir(os.path.dirname(p)) if ".bad-" in f]) == n_bad,
              "тот же битый файл — новая копия .bad- не появляется")
        check(not is_protected(p), "с целым .bak запись разрешена")
        check(save(p, {"a": 7}) and load(p, dflt) == {"a": 7}, "запись после восстановления из .bak")
        # битый и .bak битый -> default + запрет записи
        with open(p, "w", encoding="utf-8") as f:
            f.write("мусор")
        with open(p + ".bak", "w", encoding="utf-8") as f:
            f.write("[")
        x = load(p, dflt)
        check(x == dflt, "битый без .bak -> default")
        check(is_protected(p) and not save(p, {"a": 8}), "битый без .bak -> запись запрещена")
        check(load_state(p) == "default", "load_state default")
        with open(p, encoding="utf-8") as f:
            check(f.read() == "мусор", "испорченный файл не затёрт")
        check("испорчен" in last_error(p), "причина в last_error")
        # пользователь исправил файл, пока программа работает с умолчаниями — не затирать
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"a": "исправлено"}')
        check(not save(p, {"a": 8}) and "перечитайте" in last_error(p), "исправленный файл — запись всё ещё запрещена")
        with open(p, encoding="utf-8") as f:
            check(f.read() == '{"a": "исправлено"}', "исправленный файл не затёрт умолчаниями")
        check(load(p, dflt) == {"a": "исправлено"} and not is_protected(p), "load снимает запрет")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{")
        os.replace(p + ".bak", p + ".bak.keep")
        load(p, dflt)
        allow_write(p)
        check(save(p, {"a": "сам"}) and load(p, dflt) == {"a": "сам"}, "allow_write — запись по решению пользователя")
        os.replace(p + ".bak.keep", p + ".bak")
        with open(p, "w", encoding="utf-8") as f:
            f.write("мусор2")
        os.remove(p + ".bak")
        load(p, dflt)
        # сообщение о том же битом файле — один раз
        seen = []
        h = logging.Handler(logging.WARNING)
        h.emit = lambda r: seen.append(r.getMessage())
        own_handlers = log.handlers[:]
        log.handlers = [h]               # только проверочный обработчик — не файл журнала программы
        was, log.disabled = log.disabled, False
        lvl, prop = log.level, log.propagate
        log.setLevel(logging.DEBUG)
        log.propagate = False            # проверочные сообщения — не в журнал программы
        try:
            _reported.clear()
            load(p, dflt)
            load(p, dflt)
            load(p, dflt)
        finally:
            log.disabled = was
            log.setLevel(lvl)
            log.propagate = prop
            log.handlers = own_handlers
        check(len(seen) == 1, f"сообщение о битом файле — один раз (было {len(seen)})")
        os.remove(p)
        check(save(p, {"a": 9}) and not is_protected(p), "файл удалён -> запись снова можно")
        # не тот тип
        with open(p, "w", encoding="utf-8") as f:
            f.write("[1, 2]")
        x = load(p, dflt)
        check(x == {"a": 9} or x == dflt, "список вместо словаря -> .bak / default")
        # записали сами, потом испортили извне — испорченный не должен попасть в .bak
        e1 = os.path.join(d, "ext.json")
        check(save(e1, {"v": 1}) and save(e1, {"v": 2}), "две записи перед порчей извне")
        time.sleep(0.01)
        with open(e1, "w", encoding="utf-8") as f:
            f.write("{битый")
        check(save(e1, {"v": 3}), "запись после порчи извне")
        with open(e1 + ".bak", encoding="utf-8") as f:
            check(f.read().startswith('{\n  "v": 1'), "испорченный извне файл не попал в .bak (там прежняя целая)")
        # кэш (protect=False): испорченный без .bak — можно перезаписать
        c = os.path.join(d, "cache.json")
        with open(c, "w", encoding="utf-8") as f:
            f.write("{")
        check(load(c, {}, protect=False) == {} and not is_protected(c) and save(c, {"x": 1}),
              "кэш: испорченный перезаписывается")
        # файл не читается (занят) — .bak, запись запрещена
        q2 = os.path.join(d, "busy.json")
        check(save(q2, {"n": 1}) and save(q2, {"n": 2}), "две записи перед «занят»")
        real = _read_text
        try:
            def busy(path, tries=5):
                if os.fspath(path) == q2:
                    raise PermissionError(13, "занят")
                return real(path, tries)
            globals()["_read_text"] = busy
            x = load(q2, {})
        finally:
            globals()["_read_text"] = real
        check(x == {"n": 1} and load_state(q2) == "unreadable" and is_protected(q2), f"занят -> .bak ({x})")
        check(not save(q2, {"n": 0}) and load(q2, {}) == {"n": 2}, "занят -> настоящий файл не затёрт")
        # не UTF-8 -> как битый: копия байт в байт, .bak
        os.remove(p)                     # «пользователь удалил» — запись снова разрешена
        check(save(p, {"a": 10}) and save(p, {"a": 11}), "две записи перед не-UTF-8")
        with open(p, "wb") as f:
            f.write(b'{"a": "\xff"}')
        check(load(p, dflt) == {"a": 10}, "не UTF-8 -> .bak")
        bads = [f for f in os.listdir(os.path.dirname(p)) if ".bad-" in f]
        def raw(name):
            with open(os.path.join(os.path.dirname(p), name), "rb") as f:
                return f.read()
        check(any(raw(f) == b'{"a": "\xff"}' for f in bads), "копия не-UTF-8 байт в байт")
        # kind — кортеж типов
        kt = os.path.join(d, "kt.json")
        with open(kt, "w", encoding="utf-8") as f:
            f.write('"строка"')
        check(load(kt, [], kind=(list, dict)) == [] and "list / dict" in last_error(kt), "kind=(list, dict)")
        os.remove(kt)
        # не сериализуется
        check(not save(os.path.join(d, "b.json"), {"x": object()}), "несериализуемое -> False")
        check(not os.path.exists(os.path.join(d, "b.json")), "несериализуемое -> файла нет")
        # AutoSaver
        state = {"n": 1}
        q = os.path.join(d, "state.json")
        s = AutoSaver(q, lambda: state, every=100)
        s.mark_saved()
        check(s.tick(force=True) is None and not os.path.exists(q), "AutoSaver: без изменений не пишет")
        state["n"] = 2
        check(s.changed(), "AutoSaver.changed")
        check(s.tick(force=True) is True and load(q, {}) == {"n": 2}, "AutoSaver пишет изменения")
        check(s.tick() is None, "AutoSaver: не чаще every")
        state["n"] = 3
        check(s.flush() is True and load(q, {}) == {"n": 3}, "AutoSaver.flush")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.CRITICAL)
    problems = selftest()
    print(f"safe_json {VERSION}: " + ("OK" if not problems else "ОШИБКИ:\n  " + "\n  ".join(problems)))
    sys.exit(1 if problems else 0)
