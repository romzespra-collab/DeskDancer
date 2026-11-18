"""qt_base.py  v1.0.0 — общий модуль для всех проектов: основа окна PySide6 (тема, палитра, полоса диалогов).

Журнал:
v1.0.0: первая версия: set_app_id, setup_app, make_palette, is_dark, TitleBars, apply_theme.

Общий модуль: одинаковый во всех проектах. Правка — поднять версию в шапке и в VERSION ниже,
затем перенести файл ЦЕЛИКОМ во все проекты (свежий — с большим номером).
Свои цвета, QSS и вид у каждой программы — свои; модуль только правильно ставит их в Qt.

Правила (как в настройках владельца):
- app.setStyle("Fusion"): нативный стиль windowsvista ломает QSS;
- QSS — на приложение (не на окно), вместе с ним всегда палитра: её берут части, которые QSS
  не красит (окна выбора файлов, стрелки, рамки);
- палитра — с нуля от цвета фона (QPalette(фон)), для Active / Inactive (те же цвета — иначе на
  каждой смене активного окна Qt перерисовывает все виджеты) и Disabled (текст — приглушённым);
- системная полоса заголовка окон и диалогов (QMessageBox, QFileDialog, свои QDialog без своей
  рамки) — в цвет темы ДО показа: DWM 20 (19 — старая Windows 10) тёмный режим, 35/36 — цвет полосы
  и текста (Windows 11); уже показанное — SetWindowPos(SWP_FRAMECHANGED). Только Windows, всё в try;
- до QApplication — свой AppUserModelID, иначе на панели задач значок python.

API:
    qt_base.set_app_id("Comic.App")                  # до QApplication
    app = QApplication(sys.argv)
    qt_base.setup_app(app)                           # Fusion (+ qt_dialogs=True — окна файлов Qt в цветах темы)
    pal = qt_base.make_palette(window=p["panel"], text=p["text"], base=p["panel"], button=p["panel2"],
                               highlight=p["accent"], muted=p["muted"], tooltip_base=p["panel2"])
    bars = qt_base.TitleBars(app)                    # фильтр событий: полосы окон — в цвет темы
    qt_base.apply_theme(app, qss=_qss(p), palette=pal, title_bars=bars,
                        caption=p["panel"], text=p["text"])        # смена темы — всё сразу
    qt_base.is_dark("#1b1d23") -> True
"""
import sys

VERSION = "1.0.0"

_WIN = sys.platform == "win32"
DWMWA_DARK, DWMWA_DARK_OLD, DWMWA_CAPTION, DWMWA_TEXT = 20, 19, 35, 36
SWP_REDRAW_FRAME = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020   # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED


# ----------------------------------------------------------------- до QApplication
def set_app_id(app_id):
    """Свой AppUserModelID процесса (Windows) — до создания QApplication. True — поставлен."""
    if not _WIN:
        return False
    try:
        import ctypes
        return ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id)) == 0
    except Exception:                                 # noqa: BLE001 — не Windows / старая Windows
        return False


# ----------------------------------------------------------------- приложение
def setup_app(app, *, fusion=True, qt_dialogs=True):
    """Fusion (QSS работает как задумано) и окна выбора файлов Qt (в цветах темы, а не белые системные)."""
    from PySide6.QtCore import Qt
    if fusion:
        app.setStyle("Fusion")
    if qt_dialogs:
        app.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    return app


# ----------------------------------------------------------------- цвета
def _rgb(color):
    from PySide6.QtGui import QColor
    c = QColor(color)
    return c.red(), c.green(), c.blue()


def is_dark(color):
    """Цвет тёмный (по яркости) — для фона: тёмная тема."""
    try:
        r, g, b = _rgb(color)
    except Exception:                                 # noqa: BLE001
        return True
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def colorref(color):
    """Цвет -> COLORREF Windows (0x00BBGGRR)."""
    r, g, b = _rgb(color)
    return (b << 16) | (g << 8) | r


_ROLES = ("Window", "WindowText", "Base", "AlternateBase", "ToolTipBase", "ToolTipText", "PlaceholderText",
          "Text", "Button", "ButtonText", "BrightText", "Light", "Midlight", "Dark", "Mid", "Shadow",
          "Highlight", "HighlightedText", "Link", "LinkVisited", "Accent")


def make_palette(*, window, text, highlight, base=None, alt_base=None, button=None, button_text=None,
                 highlighted_text="#ffffff", muted=None, placeholder=None, tooltip_base=None,
                 tooltip_text=None, link=None, link_visited=None, bright_text=None, disabled_base=None,
                 disabled_highlight=None, light=None, midlight=None, mid=None, dark=None, shadow=None,
                 accent=None):
    """Палитра с нуля от цвета фона (QPalette(window)): Active, Inactive (те же цвета) и Disabled
    (текст — muted). Не заданное — от фона / текста. Свои цвета программы — свои."""
    from PySide6.QtGui import QColor, QPalette
    R, G = QPalette.ColorRole, QPalette.ColorGroup
    pal = QPalette(QColor(window))
    muted = muted or text
    sets = {
        "Window": window, "WindowText": text, "Base": base or window, "AlternateBase": alt_base or base or window,
        "Text": text, "Button": button or window, "ButtonText": button_text or text,
        "ToolTipBase": tooltip_base or button or window, "ToolTipText": tooltip_text or text,
        "PlaceholderText": placeholder or muted, "Highlight": highlight, "HighlightedText": highlighted_text,
        "Link": link or highlight, "LinkVisited": link_visited or link or highlight,
        "BrightText": bright_text, "Light": light, "Midlight": midlight, "Mid": mid, "Dark": dark,
        "Shadow": shadow, "Accent": accent or highlight,
    }
    for name, col in sets.items():
        role = getattr(R, name, None)
        if role is None or col is None:
            continue
        for grp in (G.Active, G.Inactive):
            pal.setColor(grp, role, QColor(col))
    # неактивное окно — те же цвета, что активное (и для ролей, выведенных из фона)
    for name in _ROLES:
        role = getattr(R, name, None)
        if role is None:
            continue
        try:
            pal.setBrush(G.Inactive, role, pal.brush(G.Active, role))
        except Exception:                             # noqa: BLE001
            pass
    for name in _ROLES:                                # недоступное — как активное, текст приглушён
        role = getattr(R, name, None)
        if role is not None:
            pal.setBrush(G.Disabled, role, pal.brush(G.Active, role))
    for role in (R.WindowText, R.Text, R.ButtonText, R.PlaceholderText):
        pal.setColor(G.Disabled, role, QColor(muted))
    pal.setColor(G.Disabled, R.Base, QColor(disabled_base or window))
    pal.setColor(G.Disabled, R.Highlight, QColor(disabled_highlight or muted))
    return pal


# ----------------------------------------------------------------- полоса заголовка (Windows)
def _dwm_set(hwnd, attr, value):
    """DwmSetWindowAttribute(hwnd, attr, &int, 4) == S_OK."""
    import ctypes
    v = ctypes.c_uint(value) if attr in (DWMWA_CAPTION, DWMWA_TEXT) else ctypes.c_int(value)
    return ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), attr, ctypes.byref(v),
                                                      ctypes.sizeof(v)) == 0


def _redraw_frame(hwnd):
    import ctypes
    ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), None, 0, 0, 0, 0, SWP_REDRAW_FRAME)


def paint_title_bar(win, caption=None, text=None, dark=None, refresh=False):
    """Полоса заголовка окна (QWidget / QWindow верхнего уровня) — в цвет темы. True — что-то принято.
    dark=None — по яркости caption. Не Windows / старая Windows / своя рамка — False."""
    if not _WIN:
        return False
    try:
        from PySide6.QtCore import Qt
        flags = win.windowFlags() if hasattr(win, "windowFlags") else win.flags()
        if flags & Qt.FramelessWindowHint:
            return False
        hwnd = int(win.winId())
    except (RuntimeError, TypeError, ValueError, AttributeError):
        return False
    if dark is None:
        dark = is_dark(caption) if caption else True
    ok = False
    try:
        ok = _dwm_set(hwnd, DWMWA_DARK, 1 if dark else 0) or _dwm_set(hwnd, DWMWA_DARK_OLD, 1 if dark else 0)
        for attr, col in ((DWMWA_CAPTION, caption), (DWMWA_TEXT, text)):     # Windows 11
            if col:
                ok = _dwm_set(hwnd, attr, colorref(col)) or ok
        if ok and refresh:
            _redraw_frame(hwnd)
    except Exception:                                 # noqa: BLE001 — нет dwmapi и т.п.
        return False
    return ok


def _make_title_bars_class():
    from PySide6.QtCore import QEvent, QObject, Qt
    from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget

    kinds = (Qt.Window, Qt.Dialog, Qt.Tool)

    class TitleBars(QObject):
        """Фильтр событий на всём приложении: системная полоса заголовка каждого окна без своей рамки
        (QMessageBox, QFileDialog, QInputDialog, свои QDialog) — в цвет темы ДО показа. set_colors —
        сменили тему: перекрасить и уже показанные. ru_ok — «OK» -> «ОК» на кнопках диалогов."""

        def __init__(self, app, caption=None, text=None, dark=None, *, ru_ok=False):
            super().__init__(app)
            self.caption, self.text, self.dark, self.ru_ok = caption, text, dark, ru_ok
            app.installEventFilter(self)

        @staticmethod
        def needs(w):
            try:
                return (isinstance(w, QWidget) and w.isWindow() and w.windowType() in kinds
                        and not w.windowFlags() & Qt.FramelessWindowHint)
            except RuntimeError:
                return False

        def set_colors(self, caption, text=None, dark=None, refresh=True):
            self.caption, self.text, self.dark = caption, text, dark
            if refresh:
                for w in QApplication.topLevelWidgets():
                    if self.needs(w) and w.isVisible():
                        self.paint(w, refresh=True)

        def paint(self, w, refresh=False):
            if not self.caption:
                return False
            return paint_title_bar(w, self.caption, self.text, self.dark, refresh)

        def eventFilter(self, obj, ev):                # noqa: N802 (Qt)
            if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
                if self.ru_ok and isinstance(obj, QDialog):
                    for b in obj.findChildren(QPushButton):
                        if b.text().replace("&", "") == "OK":
                            b.setText("ОК")
                if self.needs(obj):
                    self.paint(obj)
            return False

    return TitleBars


_TB = None


def TitleBars(app, caption=None, text=None, dark=None, *, ru_ok=False):    # noqa: N802 — как класс
    """Фильтр полос заголовка (см. класс выше): ставится на приложение, возвращается объект."""
    global _TB
    if _TB is None:
        _TB = _make_title_bars_class()
    return _TB(app, caption, text, dark, ru_ok=ru_ok)


def apply_theme(app, *, qss=None, palette=None, title_bars=None, caption=None, text=None, dark=None):
    """Тема — всё сразу: QSS на приложение, палитра, полосы заголовка (и уже показанных окон)."""
    if palette is not None:
        app.setPalette(palette)
    if qss is not None:
        app.setStyleSheet(qss)
    if title_bars is not None and caption:
        title_bars.set_colors(caption, text, dark)


# ----------------------------------------------------------------- самопроверка
def selftest():
    """Пустой список — всё в порядке, иначе — тексты ошибок. Нужен QApplication (offscreen подходит)."""
    global _WIN, _dwm_set, _redraw_frame
    errs = []

    def check(cond, text):
        if not cond:
            errs.append(text)

    from PySide6.QtGui import QColor, QPalette
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    app = QApplication.instance()
    if app is None:
        return ["нет QApplication"]
    widgets = isinstance(app, QApplication)      # QGuiApplication (без окон) — только палитра
    check(is_dark("#1b1d23") and not is_dark("#f3f4f7"), "is_dark")
    check(colorref("#102030") == 0x302010, "colorref")
    pal = make_palette(window="#23262e", text="#e6e8ee", highlight="#4f8cff", base="#1b1d23", muted="#8a8f9c")
    R, G = QPalette.ColorRole, QPalette.ColorGroup
    check(pal.color(G.Active, R.Window) == QColor("#23262e"), "Window")
    check(pal.color(G.Active, R.Base) == QColor("#1b1d23"), "Base")
    check(pal.color(G.Inactive, R.Highlight) == pal.color(G.Active, R.Highlight), "Inactive = Active")
    check(pal.color(G.Inactive, R.Mid) == pal.color(G.Active, R.Mid), "Inactive = Active (выведенные роли)")
    check(pal.color(G.Disabled, R.Text) == QColor("#8a8f9c"), "Disabled текст — muted")
    check(pal.color(G.Disabled, R.Window) == QColor("#23262e"), "Disabled фон")
    check(pal.color(G.Active, R.PlaceholderText) == QColor("#8a8f9c"), "PlaceholderText")
    if not widgets:
        return errs
    # полосы заголовка: поддельный DWM — что и в каком порядке красится
    calls = []
    saved = (_WIN, _dwm_set, _redraw_frame)
    try:
        _WIN = True
        _dwm_set = lambda h, a, v: calls.append((a, v)) or True          # noqa: E731
        _redraw_frame = lambda h: calls.append(("redraw",))               # noqa: E731
        bars = TitleBars(app, "#23262e", "#e6e8ee", ru_ok=True)
        dlg = QMessageBox(QMessageBox.Information, "проба", "текст", QMessageBox.Ok)
        dlg.show()
        app.processEvents()
        check((DWMWA_DARK, 1) in calls and (DWMWA_CAPTION, colorref("#23262e")) in calls
              and (DWMWA_TEXT, colorref("#e6e8ee")) in calls, f"Show диалога -> DWM: {calls}")
        check(any(b.text() == "ОК" for b in dlg.findChildren(type(dlg.buttons()[0]))), "«OK» -> «ОК»")
        calls.clear()
        apply_theme(app, palette=make_palette(window="#ffffff", text="#1c2230", highlight="#2f6fe4"),
                    title_bars=bars, caption="#ffffff", text="#1c2230")
        check((DWMWA_DARK, 0) in calls and ("redraw",) in calls, f"смена темы -> показанные перекрашены: {calls}")
        dlg.close()
        from PySide6.QtCore import Qt
        calls.clear()
        own = QDialog(None, Qt.Dialog | Qt.FramelessWindowHint)
        own.show()
        app.processEvents()
        check(not calls, "своя рамка — системную полосу не трогаем")
        own.close()
        app.removeEventFilter(bars)
        bars.deleteLater()
    finally:
        _WIN, _dwm_set, _redraw_frame = saved
    check(not paint_title_bar(dlg, "#000000") or _WIN, "не Windows — ничего")
    return errs


if __name__ == "__main__":
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication(sys.argv)
    setup_app(_app)
    problems = selftest()
    print(f"qt_base {VERSION}: " + ("OK" if not problems else "ОШИБКИ:\n  " + "\n  ".join(problems)))
    sys.exit(1 if problems else 0)
