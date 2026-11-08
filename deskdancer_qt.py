"""deskdancer_qt.py  v2.3.0 — окна DeskDancer (PySide6)

Главное окно (своя рамка, шапка с чипом состояния, ☀/☾, ⋯, боковая панель)
и прозрачное окно сцены поверх рабочего стола. 3D считает Panda3D в своём
потоке (app/engine3d.py), кадр рисуется QPainter'ом — без браузера, как
скины PionerFM.

Журнал:
v2.3.0: кадры сцены — до 60 в секунду (таймер 16 мс)
v2.1.0: нет Panda3D в этом Python (3.15) — 3D в отдельном Python (ставится сам, ход —
        в журнале, на полосе и в предпросмотре)
v2.0.0: без браузера: сцена — Panda3D (видеокарта или процессор), кадры —
        в окно сцены и в «Предпросмотр» через QPainter; «Графика»: Авто /
        Видеокарта / Процессор; QtWebEngine и three.js больше не нужны
v1.5.0: режим графики «Авто / OpenGL / Программный» («Окно»); проверка
        предпросмотра: WebGL нет, кадров нет или девушки на экране не
        двигаются — предлагает перезапуск в следующем режиме; в журнал —
        видеокарта и «страница сцены не загрузилась»
v1.4.0: девушки видны прямо в окне программы — «Предпросмотр» на странице «Сцена»;
        фон сцены «Прозрачный / Тёмный» (если прозрачность не работает на ПК);
        «🎯 Найти сцену»; первый показ — рядом с окном программы; проверка
        сцены через 8 с — в журнал кадры/с или подсказка; прозрачность
        QtWebEngine на Windows — QQuickWindow.setDefaultAlphaBuffer
v1.3.0: «Сцена» — вид «Обычный / Неон», цвет неона (Огонь, Неон, Радуга), свечение %
v1.2.0: подписи — 10 танцев в комплекте
v1.1.0: «Модели» — про девушек в комплекте; новая девушка берёт танец из комплекта
v1.0.0: первая версия — страницы «Сцена», «Музыка», «Окно», «Библиотека»,
        «Журнал», «Обновление с GitHub»; пресеты сцен; до 6 девушек;
        прозрачное окно сцены: перенос, размер, «сквозь мышь», поверх всех
"""
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import deskdancer as core
from deskdancer import log

if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(core.APP_ID)
    except Exception:                                   # noqa: BLE001
        pass

from PySide6.QtCore import (QByteArray, QEvent, QObject, QPoint, QPointF, QRect,
                            QRectF, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QIcon,
                           QKeySequence, QLinearGradient, QPainter, QPainterPath,
                           QPalette, QPen, QPixmap, QRadialGradient, QShortcut,
                           QTextCharFormat, QTextCursor)
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup,
                               QComboBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSizeGrip, QSizePolicy,
                               QStackedWidget, QTableWidget, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from app import theme
from app.window_frame import WindowFrame
from app import gh_update, gh_update_qt
from app.engine3d import Engine

VERSION = core.VERSION
MAX_DANCERS = 6


# ───────────────────────── стиль ─────────────────────────
def _qss(p):
    return f"""
* {{ font-family: "Segoe UI"; font-size: 10pt; color: {p['text']}; }}
QMainWindow, QWidget#root {{ background: {p['bg']}; }}
QDialog, QMessageBox, QFileDialog, QInputDialog {{ background: {p['panel']}; }}
QMessageBox QLabel, QDialog QLabel {{ color: {p['text']}; background: transparent; }}
QWidget#titleBar {{ background: {p['side']}; border-bottom: 1px solid {p['line']}; }}
QLabel#appTitle {{ font-weight: 600; font-size: 10.5pt; }}
QLabel#appVer {{ color: {p['muted']}; font-size: 8.5pt; }}
QLabel#chip {{ border-radius: 10px; padding: 2px 10px; font-weight: 600; font-size: 9pt;
              background: {p['panel2']}; border: 1px solid {p['line']}; }}
QToolButton#winBtn, QToolButton#winClose {{ border: none; background: transparent; }}
QToolButton#winBtn:hover {{ background: {p['panel2']}; }}
QToolButton#winClose:hover {{ background: #e81123; }}
QToolButton#hdrBtn {{ border: none; border-radius: 6px; padding: 3px 8px; font-size: 12pt;
                     background: transparent; }}
QToolButton#hdrBtn:hover {{ background: {p['panel2']}; }}
QWidget#side {{ background: {p['side']}; border-right: 1px solid {p['line']}; }}
QFrame#card {{ background: {p['panel']}; border: 1px solid {p['line']}; border-radius: 10px; }}
QLabel#cardTitle {{ color: {p['muted']}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
QLabel#hint {{ color: {p['muted']}; font-size: 9pt; }}
QFrame#tile {{ background: {p['panel']}; border: 1px solid {p['line']}; border-radius: 10px; }}
QLabel#tileVal {{ font-size: 18pt; font-weight: 700; }}
QLabel#tileCap {{ color: {p['muted']}; font-size: 8pt; font-weight: 600; letter-spacing: 1px; }}
QPushButton {{ background: {p['panel2']}; color: {p['text']}; border: 1px solid {p['line']};
              border-radius: 7px; padding: 5px 12px; min-height: 18px; }}
QPushButton:hover {{ border-color: {p['accent']}; }}
QPushButton:pressed {{ background: {p['line']}; }}
QPushButton:disabled {{ color: {p['muted']}; }}
QPushButton#primary {{ background: {p['accent']}; color: #ffffff; border: none; font-weight: 700; }}
QPushButton#primary:hover {{ background: {p['accent2']}; }}
QPushButton#danger {{ background: transparent; color: #ff5d6c; border: 1px solid #ff5d6c; }}
QPushButton#chipBtn, QPushButton#seg {{ padding: 3px 10px; border-radius: 6px; }}
QPushButton#seg:checked {{ background: {p['accent']}; color: #ffffff; border-color: {p['accent']}; }}
QPushButton#pm {{ padding: 0; min-width: 24px; max-width: 24px; font-weight: 700; }}
QDialog QPushButton, QMessageBox QPushButton, QFileDialog QPushButton {{ min-width: 80px; }}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QListWidget, QTableWidget {{
    background: {p['panel2']}; color: {p['text']}; border: 1px solid {p['line']};
    border-radius: 7px; padding: 3px 6px; selection-background-color: {p['accent']};
    selection-color: #ffffff; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {p['accent']}; }}
QLineEdit#intField {{ padding: 2px; }}
QComboBox QAbstractItemView {{ background: {p['panel']}; color: {p['text']};
    border: 1px solid {p['line']}; selection-background-color: {p['accent']}; }}
QListWidget::item {{ padding: 4px 2px; }}
QListWidget::item:selected {{ background: {p['accent']}; color: #ffffff; border-radius: 4px; }}
QPlainTextEdit#log {{ background: {p['log_bg']}; color: {p['log_fg']};
    font-family: Consolas; font-size: 9pt; }}
QProgressBar {{ background: transparent; border: none; max-height: 3px; }}
QProgressBar::chunk {{ background: {p['accent']}; }}
QProgressBar#meter {{ background: {p['panel2']}; border-radius: 4px; max-height: 8px; }}
QProgressBar#meter::chunk {{ border-radius: 4px; background: {p['accent']}; }}
QMenu {{ background: {p['panel']}; color: {p['text']}; border: 1px solid {p['line']}; padding: 4px; }}
QMenu::item {{ padding: 5px 22px 5px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p['accent']}; color: #ffffff; }}
QMenu::item:disabled {{ color: {p['muted']}; }}
QMenu::separator {{ height: 1px; background: {p['line']}; margin: 4px 6px; }}
QToolTip {{ background: {p['panel2']}; color: {p['text']}; border: 1px solid {p['accent']}; padding: 4px; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {p['line']}; border-radius: 5px; min-height: 24px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {p['line']}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QGroupBox {{ background: {p['panel']}; border: 1px solid {p['line']}; border-radius: 10px;
            margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {p['muted']}; }}
QWidget#setinner {{ background: transparent; }}
"""


def _palette(p):
    pal = QPalette(QColor(p["bg"]))
    roles = {QPalette.Window: p["bg"], QPalette.WindowText: p["text"],
             QPalette.Base: p["panel2"], QPalette.AlternateBase: p["panel"],
             QPalette.Text: p["text"], QPalette.Button: p["panel2"],
             QPalette.ButtonText: p["text"], QPalette.Highlight: p["accent"],
             QPalette.HighlightedText: "#ffffff", QPalette.PlaceholderText: p["muted"],
             QPalette.ToolTipBase: p["panel2"], QPalette.ToolTipText: p["text"],
             QPalette.BrightText: "#ffffff", QPalette.Link: p["accent"]}
    for grp in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        for role, col in roles.items():
            c = col
            if grp == QPalette.Disabled and role in (QPalette.WindowText, QPalette.Text,
                                                     QPalette.ButtonText):
                c = p["muted"]
            pal.setColor(grp, role, QColor(c))
    return pal


# ───────────────────────── значки (QPainter) ─────────────────────────
def _draw_dancer(p, r, col, width=1.0):
    """Силуэт танцующей девушки в прямоугольнике r."""
    w, h = r.width(), r.height()
    x, y = r.x(), r.y()
    pen = QPen(col, max(1.2, w * 0.075 * width), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    P = lambda fx, fy: QPointF(x + fx * w, y + fy * h)    # noqa: E731
    p.setBrush(col)
    p.drawEllipse(P(0.52, 0.16), w * 0.09, w * 0.09)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath(P(0.52, 0.27))
    path.lineTo(P(0.48, 0.52))
    p.drawPath(path)
    p.drawLine(P(0.50, 0.33), P(0.78, 0.12))             # рука вверх
    p.drawLine(P(0.50, 0.34), P(0.28, 0.42))
    p.drawLine(P(0.28, 0.42), P(0.36, 0.30))
    skirt = QPainterPath(P(0.42, 0.50))
    skirt.lineTo(P(0.30, 0.68))
    skirt.lineTo(P(0.66, 0.66))
    skirt.lineTo(P(0.54, 0.50))
    skirt.closeSubpath()
    p.setBrush(col)
    p.drawPath(skirt)
    p.setBrush(Qt.NoBrush)
    p.drawLine(P(0.42, 0.67), P(0.36, 0.90))
    p.drawLine(P(0.54, 0.66), P(0.66, 0.80))
    p.drawLine(P(0.66, 0.80), P(0.60, 0.92))


def app_pixmap(size):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#ff5fa2"))
    g.setColorAt(1, QColor("#7c6cff"))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    m = size * 0.04
    p.drawRoundedRect(QRectF(m, m, size - 2 * m, size - 2 * m), size * 0.22, size * 0.22)
    # ноты
    p.setPen(QPen(QColor(255, 255, 255, 150), max(1, size * 0.035)))
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawEllipse(QPointF(size * 0.2, size * 0.78), size * 0.06, size * 0.045)
    p.drawLine(QPointF(size * 0.25, size * 0.77), QPointF(size * 0.25, size * 0.52))
    _draw_dancer(p, QRectF(size * 0.15, size * 0.08, size * 0.8, size * 0.86), QColor("#ffffff"))
    p.end()
    return pm


def app_icon():
    ic = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_pixmap(s))
    return ic


def _icon_painter(kind):
    def scene(p, r, c):
        _draw_dancer(p, QRectF(r.x() - r.width() * 0.18, r.y(), r.width() * 0.8, r.height()), c, 0.9)
        _draw_dancer(p, QRectF(r.x() + r.width() * 0.38, r.y() + r.height() * 0.1,
                               r.width() * 0.7, r.height() * 0.9), c, 0.9)

    def music(p, r, c):
        w, h, x, y = r.width(), r.height(), r.x(), r.y()
        p.setPen(QPen(c, w * 0.09, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(x + w * .38, y + h * .78), QPointF(x + w * .38, y + h * .18))
        p.drawLine(QPointF(x + w * .82, y + h * .66), QPointF(x + w * .82, y + h * .08))
        p.drawLine(QPointF(x + w * .38, y + h * .18), QPointF(x + w * .82, y + h * .08))
        p.setBrush(c)
        p.drawEllipse(QPointF(x + w * .27, y + h * .8), w * .13, h * .1)
        p.drawEllipse(QPointF(x + w * .71, y + h * .68), w * .13, h * .1)

    def window(p, r, c):
        w, h, x, y = r.width(), r.height(), r.x(), r.y()
        p.setPen(QPen(c, w * 0.08))
        p.drawRoundedRect(QRectF(x + w * .08, y + h * .14, w * .84, h * .64), 4, 4)
        p.drawLine(QPointF(x + w * .3, y + h * .92), QPointF(x + w * .7, y + h * .92))
        p.setBrush(c)
        p.drawEllipse(QPointF(x + w * .5, y + h * .36), w * .07, w * .07)
        p.drawLine(QPointF(x + w * .5, y + h * .44), QPointF(x + w * .5, y + h * .62))

    def library(p, r, c):
        w, h, x, y = r.width(), r.height(), r.x(), r.y()
        p.setPen(QPen(c, w * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for i, fx in enumerate((.12, .34, .56)):
            p.drawRoundedRect(QRectF(x + w * fx, y + h * (.14 + .04 * (i % 2)), w * .16, h * .74), 2, 2)
        p.save()
        p.translate(x + w * .82, y + h * .5)
        p.rotate(14)
        p.drawRoundedRect(QRectF(-w * .08, -h * .36, w * .16, h * .74), 2, 2)
        p.restore()

    def logk(p, r, c):
        w, h, x, y = r.width(), r.height(), r.x(), r.y()
        p.setPen(QPen(c, w * 0.08))
        p.drawRoundedRect(QRectF(x + w * .14, y + h * .08, w * .72, h * .84), 4, 4)
        for i, f in enumerate((.3, .48, .66)):
            p.drawLine(QPointF(x + w * .3, y + h * f), QPointF(x + w * (.7 - .12 * (i == 2)), y + h * f))

    def update(p, r, c):
        w, h, x, y = r.width(), r.height(), r.x(), r.y()
        p.setPen(QPen(c, w * 0.08, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        path = QPainterPath(QPointF(x + w * .25, y + h * .7))
        path.cubicTo(QPointF(x + w * .0, y + h * .7), QPointF(x + w * .05, y + h * .35),
                     QPointF(x + w * .3, y + h * .4))
        path.cubicTo(QPointF(x + w * .35, y + h * .1), QPointF(x + w * .75, y + h * .12),
                     QPointF(x + w * .74, y + h * .38))
        path.cubicTo(QPointF(x + w * 1.0, y + h * .38), QPointF(x + w * 1.0, y + h * .7),
                     QPointF(x + w * .76, y + h * .7))
        p.drawPath(path)
        p.drawLine(QPointF(x + w * .5, y + h * .45), QPointF(x + w * .5, y + h * .92))
        p.drawLine(QPointF(x + w * .38, y + h * .8), QPointF(x + w * .5, y + h * .92))
        p.drawLine(QPointF(x + w * .62, y + h * .8), QPointF(x + w * .5, y + h * .92))

    return {"scene": scene, "music": music, "window": window, "library": library,
            "log": logk, "update": update}[kind]


# ───────────────────────── виджеты ─────────────────────────
class SideButton(QAbstractButton):
    """Кнопка боковой панели: значок (цветной контур) + подпись под ним."""

    def __init__(self, key, text, tip):
        super().__init__()
        self.key, self.text_ = key, text
        self.painter = _icon_painter(key)
        self.setCheckable(True)
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(88, 66)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor(theme.page_color(self.key))
        if self.isChecked() or self.underMouse():
            bg = QColor(col)
            bg.setAlpha(46 if self.isChecked() else 22)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(QRectF(6, 3, self.width() - 10, self.height() - 6), 9, 9)
        if self.isChecked():
            p.setBrush(col)
            p.drawRoundedRect(QRectF(0, 12, 3.5, self.height() - 24), 2, 2)
        self.painter(p, QRectF(self.width() / 2 - 13, 8, 26, 26), col)
        f = QFont("Segoe UI")
        f.setPointSizeF(8.5)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.P["text"]))
        p.drawText(QRect(0, 38, self.width(), 22), Qt.AlignCenter, self.text_)
        p.end()

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)


class IntField(QLineEdit):
    """Число на QLineEdit (не QSpinBox): колесо, ↑/↓, ввод по Enter/уходу
    фокуса, кривой ввод откатывается."""
    valueChanged = Signal(int)

    def __init__(self, lo=0, hi=100, value=0, suffix="", step=1, widest="720 мин"):
        super().__init__()
        self.setObjectName("intField")
        self._lo, self._hi, self._step = lo, hi, step
        self._suffix, self._special = suffix, ""
        self._v = max(lo, min(hi, int(value)))
        self.setAlignment(Qt.AlignCenter)
        self.setFixedWidth(self.fontMetrics().horizontalAdvance(widest) + 26)
        self.editingFinished.connect(self._commit)
        self._render()

    def value(self):
        return self._v

    def setRange(self, lo, hi):
        self._lo, self._hi = lo, hi
        self.setValue(self._v)

    def setSuffix(self, s):
        self._suffix = s
        self._render()

    def setSpecialValueText(self, s):
        self._special = s
        self._render()

    def setValue(self, v, emit=True):
        v = max(self._lo, min(self._hi, int(v)))
        changed = v != self._v
        self._v = v
        self._render()
        if changed and emit:
            self.valueChanged.emit(v)

    def stepBy(self, n):
        self.setValue(self._v + n * self._step)

    def _render(self):
        if self._special and self._v == self._lo:
            self.setText(self._special)
        else:
            self.setText(f"{self._v}{self._suffix}")

    def _commit(self):
        t = self.text().replace(self._suffix.strip(), "").strip() if self._suffix.strip() else self.text().strip()
        if self._special and t == self._special:
            self.setValue(self._lo)
            return
        try:
            self.setValue(int(t.replace(" ", "")))
        except ValueError:
            self._render()                       # кривой ввод — откат

    def wheelEvent(self, e):
        if self.hasFocus() or self.underMouse():
            self.stepBy(1 if e.angleDelta().y() > 0 else -1)
            e.accept()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Up:
            self.stepBy(1)
        elif e.key() == Qt.Key_Down:
            self.stepBy(-1)
        else:
            super().keyPressEvent(e)


def stepper(field):
    """[−] поле [+] — отдельные кнопки."""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(4)
    for txt, d in (("−", -1), (None, 0), ("+", 1)):
        if txt is None:
            h.addWidget(field)
            continue
        b = QPushButton(txt)
        b.setObjectName("pm")
        b.setAutoRepeat(True)
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(lambda _=False, dd=d: field.stepBy(dd))
        h.addWidget(b)
    return w


class Toggle(QAbstractButton):
    """Переключатель-таблетка."""

    def __init__(self, checked=False, tip=""):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 22)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        on = self.isChecked()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.P["accent"] if on else theme.P["toggle_off"]))
        p.drawRoundedRect(QRectF(0, 0, 40, 22), 11, 11)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(21 if on else 3, 3, 16, 16))
        p.end()


class Segmented(QWidget):
    changed = Signal(str)

    def __init__(self, items, current=None):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        self.group = QButtonGroup(self)
        self.btns = {}
        for key, text, tip in items:
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setToolTip(tip)
            self.group.addButton(b)
            self.btns[key] = b
            h.addWidget(b)
            b.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
        h.addStretch(1)
        self.set(current or items[0][0])

    def set(self, key):
        if key in self.btns:
            self.btns[key].setChecked(True)

    def value(self):
        for k, b in self.btns.items():
            if b.isChecked():
                return k
        return None


class BeatLamp(QWidget):
    """Вспышка на каждую долю + номер доли в такте."""

    def __init__(self):
        super().__init__()
        self.phase, self.n, self.active = 0.0, 0, False
        self.setFixedSize(120, 120)

    def set(self, phase, n, active):
        self.phase, self.n, self.active = phase, n, active
        self.update()

    def paintEvent(self, _e):
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(theme.page_color("music"))
        k = math.exp(-self.phase * 5) if self.active else 0.0
        r = 34 + 14 * k
        g = QRadialGradient(QPointF(60, 60), r + 10)
        cc = QColor(c)
        cc.setAlphaF(0.25 + 0.75 * k)
        g.setColorAt(0, cc)
        cc2 = QColor(c)
        cc2.setAlphaF(0.0)
        g.setColorAt(1, cc2)
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(60, 60), r + 10, r + 10)
        p.setPen(QPen(c, 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(60, 60), 34, 34)
        f = QFont("Segoe UI")
        f.setPointSize(20)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.P["text"]))
        p.drawText(QRect(0, 0, 120, 120), Qt.AlignCenter,
                   str(self.n % 4 + 1) if self.active else "—")
        p.end()


def card(title):
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(14, 10, 14, 12)
    v.setSpacing(8)
    t = QLabel(title.upper())
    t.setObjectName("cardTitle")
    v.addWidget(t)
    return f, v


_LINK_LABELS = []


def _link_text(text):
    return text.replace("<a href=", f"<a style='color:{theme.P['accent']}' href=")


def hint(text):
    l = QLabel(_link_text(text))
    if "<a " in text:
        l._raw = text
        _LINK_LABELS.append(l)
    l.setObjectName("hint")
    l.setWordWrap(True)
    l.setTextInteractionFlags(Qt.TextBrowserInteraction)
    l.setOpenExternalLinks(True)
    return l


def row(*widgets, stretch=True):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    for x in widgets:
        if isinstance(x, str):
            l = QLabel(x)
            h.addWidget(l)
        else:
            h.addWidget(x)
    if stretch:
        h.addStretch(1)
    return w


def page_scroll(inner):
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setWidget(inner)
    return sa


# ───────────────────────── окно сцены ─────────────────────────
DARK_BG = "101118"           # «тёмный» фон сцены


class SceneView(QWidget):
    """Кадр 3D-сцены (QImage с прозрачностью) — рисуется QPainter'ом, как скины
    PionerFM. bg — цвет фона или None (прозрачно)."""

    def __init__(self, bg=None):
        super().__init__()
        self.img = None
        self.bg = bg
        self.msg = ""
        self.setAttribute(Qt.WA_TranslucentBackground, bg is None)
        self.setMinimumSize(120, 140)

    def set_image(self, img):
        self.img = img
        self.update()

    def set_bg(self, bg):
        self.bg = bg
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        if self.bg:
            p.fillRect(self.rect(), QColor(self.bg))
        if self.img is not None and not self.img.isNull():
            p.setRenderHint(QPainter.SmoothPixmapTransform, True)
            iw, ih = self.img.width(), self.img.height()
            k = min(self.width() / iw, self.height() / ih)
            w, h = int(iw * k), int(ih * k)
            p.drawImage(QRect((self.width() - w) // 2, (self.height() - h) // 2, w, h), self.img)
        if self.msg:
            p.setPen(QColor(theme.P["muted"] if self.bg else "#ffffff"))
            p.drawText(self.rect().adjusted(10, 10, -10, -10), Qt.AlignCenter | Qt.TextWordWrap, self.msg)
        p.end()


class Overlay(QWidget):
    """Прозрачное окно поверх рабочего стола с 3D-сценой."""
    geometryChanged = Signal()

    def __init__(self, cfg):
        super().__init__(None)
        self.cfg = cfg
        self.locked = False
        self.transparent = cfg.get("bg", "transparent") != "dark"
        self.setWindowTitle("DeskDancer — сцена")
        self.setWindowIcon(app_icon())
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool |
                            (Qt.WindowStaysOnTopHint if cfg["on_top"] else Qt.Widget))
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.bar = QWidget()
        self.bar.setObjectName("ovBar")
        self.bar.setFixedHeight(26)
        self.bar.setCursor(Qt.SizeAllCursor)
        self.bar.setStyleSheet("#ovBar { background: rgba(20,20,28,150); border-radius: 8px; }"
                               "QLabel { color: #fff; background: transparent; font-size: 9pt; }"
                               "QToolButton { color: #fff; border: none; background: transparent;"
                               " padding: 0 6px; font-size: 10pt; }"
                               "QToolButton:hover { background: rgba(255,255,255,40); border-radius: 5px; }")
        bh = QHBoxLayout(self.bar)
        bh.setContentsMargins(8, 0, 4, 0)
        lab = QLabel("⠿  DeskDancer — тяните, чтобы двигать")
        lab.setAttribute(Qt.WA_TransparentForMouseEvents)
        bh.addWidget(lab)
        bh.addStretch(1)
        self.btn_lock = QToolButton()
        self.btn_lock.setText("🔒")
        self.btn_lock.setToolTip("Закрепить: окно пропускает мышь насквозь\n"
                                 "(снять — в главном окне, страница «Окно»)")
        bh.addWidget(self.btn_lock)
        self.btn_hide = QToolButton()
        self.btn_hide.setText("✕")
        self.btn_hide.setToolTip("Спрятать сцену")
        bh.addWidget(self.btn_hide)
        v.addWidget(self.bar)
        self.bar.installEventFilter(self)
        self.view = SceneView(None if self.transparent else "#" + DARK_BG)
        v.addWidget(self.view, 1)
        self.grip = QSizeGrip(self)
        self.grip.setFixedSize(18, 18)
        self.grip.setToolTip("Тяните, чтобы изменить размер")
        self._place()

    def _place(self):
        g = self.cfg
        scr = QApplication.primaryScreen().availableGeometry()
        w, h = max(200, g["w"]), max(220, g["h"])
        x, y = g["x"], g["y"]
        if x < 0 or y < 0 or not any(s.availableGeometry().intersects(QRect(x, y, w, h))
                                     for s in QApplication.screens()):
            x, y = scr.right() - w - 20, scr.bottom() - h
        self.setGeometry(x, y, w, h)

    def corner(self, where):
        scr = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        w, h = self.width(), self.height()
        pos = {"center": (scr.center().x() - w // 2, scr.center().y() - h // 2),
               "br": (scr.right() - w - 20, scr.bottom() - h),
               "bl": (scr.left() + 20, scr.bottom() - h)}[where]
        self.move(*pos)

    def set_locked(self, on):
        self.locked = on
        vis = self.isVisible()
        self.setWindowFlag(Qt.WindowTransparentForInput, on)
        self.bar.setVisible(not on)
        self.grip.setVisible(not on)
        if vis:
            self.show()

    def set_on_top(self, on):
        vis = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        if vis:
            self.show()

    def resizeEvent(self, e):
        self.grip.move(self.width() - 18, self.height() - 18)
        self.grip.raise_()
        self.geometryChanged.emit()
        super().resizeEvent(e)

    def moveEvent(self, e):
        self.geometryChanged.emit()
        super().moveEvent(e)

    def eventFilter(self, obj, ev):
        if obj is self.bar and ev.type() == QEvent.MouseButtonPress and \
                ev.button() == Qt.LeftButton:
            h = self.windowHandle()
            if h is not None:
                h.startSystemMove()
            return True
        return False


# ───────────────────────── страницы ─────────────────────────
class DancerRow(QWidget):
    changed = Signal()
    removed = Signal(object)

    def __init__(self, idx, spec, chars, dances):
        super().__init__()
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        self.num = QLabel(f"{idx + 1}")
        self.num.setFixedWidth(16)
        self.num.setStyleSheet("font-weight:700;")
        h.addWidget(self.num)
        self.cb_char = QComboBox()
        self.cb_char.setToolTip("Девушка (модель из папки characters/)")
        self.cb_dance = QComboBox()
        self.cb_dance.setToolTip("Танец: свой у модели, встроенный (для манекена) или файл из dances/")
        for cb in (self.cb_char, self.cb_dance):
            cb.setMinimumWidth(180)
            cb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        h.addWidget(self.cb_char, 3)
        h.addWidget(self.cb_dance, 3)
        self.scale = IntField(40, 200, spec.get("scale", 100), " %", 5, "200 %")
        self.scale.setToolTip("Рост девушки на сцене")
        h.addWidget(stepper(self.scale))
        rm = QPushButton("🗑")
        rm.setObjectName("chipBtn")
        rm.setToolTip("Убрать девушку со сцены")
        rm.clicked.connect(lambda: self.removed.emit(self))
        h.addWidget(rm)
        self.fill(chars, dances, spec)
        self.cb_char.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.cb_dance.currentIndexChanged.connect(lambda _: self.changed.emit())
        self.scale.valueChanged.connect(lambda _: self.changed.emit())

    @staticmethod
    def _fill_cb(cb, items, cur):
        cb.blockSignals(True)
        cb.clear()
        for key, name in items:
            cb.addItem(name, key)
        i = cb.findData(cur)
        if i < 0 and cur:
            cb.addItem(f"⚠ нет файла: {cur.split('/')[-1]}", cur)
            i = cb.count() - 1
        cb.setCurrentIndex(max(0, i))
        cb.blockSignals(False)

    def fill(self, chars, dances, spec=None):
        spec = spec or self.spec()
        self._fill_cb(self.cb_char, chars, spec.get("char"))
        self._fill_cb(self.cb_dance, dances, spec.get("dance"))

    def spec(self):
        return {"char": self.cb_char.currentData(), "dance": self.cb_dance.currentData(),
                "scale": self.scale.value()}


class _PendingEngine:
    """Пока готовится отдельный Python для 3D: принимает команды, затем
    передаёт их настоящему движку (engine_proc.EngineProcess)."""

    def __init__(self, win, gpu):
        self.win, self.gpu = win, gpu
        self.status = {"ready": False, "error": "", "fps": 0, "dancers": [], "pipe": ""}
        self.soft = True
        self._scene = None
        self._stop = False

    def start(self):
        threading.Thread(target=self._prepare, daemon=True, name="runtime3d").start()

    def _prepare(self):
        from app import runtime3d
        q = core.LOG_QUEUE
        self.status["error"] = "Готовлю 3D-движок (первый запуск, нужен интернет)…"
        try:
            py = runtime3d.find_or_install(core.APP_ROOT, self.win.cfg.get("runtime_python"), log.info,
                                           progress=lambda v: q.put(lambda: self.win.progress.setValue(v)))
        except Exception as e:                              # noqa: BLE001
            self.status["error"] = f"3D-движок не подготовлен: {e}"
            log.error(f"✗ 3D-движок не подготовлен: {e}")
            return
        if self._stop:
            return
        q.put(lambda: self.win._engine_ready(py))

    def set_scene(self, scene):
        self._scene = scene

    def set_size(self, w, h):
        pass

    def set_beat(self, st):
        pass

    def set_paused(self, on):
        pass

    def frame(self):
        return None

    def stop(self, wait=0):
        self._stop = True


# ───────────────────────── главное окно ─────────────────────────
class MainWindow(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._migrate_cfg()
        self.engine = self._make_engine()
        self._frame_serial = 0
        self._frame_img = None
        self.running = False
        self.worker = None
        self.tracker = None
        self.clock = core.ManualClock(cfg["audio"]["manual_bpm"])
        self.beats = 0
        self._last_phase = 0.0
        self._saved = self._dump()
        self._audio_err = ""
        self._dl_thread = None
        self.overlay = None
        self.setObjectName("root")
        self.setWindowTitle(f"{core.APP_NAME} — v{VERSION} · Qt6")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(900, 600)
        self._build()
        self.frame = WindowFrame(self, self.title_bar, self.title_lay)
        self._restore_geometry()
        self.apply_theme()
        self._keys()
        self.t_ui = QTimer(self, interval=33, timeout=self._tick)
        self.t_ui.start()
        self.t_log = QTimer(self, interval=150, timeout=self._drain_log)
        self.t_log.start()
        self.t_save = QTimer(self, interval=10_000, timeout=self._autosave)
        self.t_save.start()
        self.refresh_library(push=False)
        log.info(f"✓ {core.APP_NAME} v{VERSION} запущен, графика: "
                 f"{dict((k, n) for k, n, _ in self.GPU_MODES)[cfg.get('gpu', 'auto')]}")
        self.engine.start()
        self.push_scene()
        self.t_frame = QTimer(self, interval=16, timeout=self._frame_tick)
        self.t_frame.setTimerType(Qt.PreciseTimer)
        self.t_frame.start()
        QTimer.singleShot(8000, self._report_engine)
        if cfg.get("running"):
            QTimer.singleShot(400, self.start)

    # ---------- построение ----------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        # шапка = полоса заголовка окна
        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        self.title_bar.setFixedHeight(40)
        tl = QHBoxLayout(self.title_bar)
        tl.setContentsMargins(10, 0, 0, 0)
        tl.setSpacing(8)
        self.title_lay = tl
        ic = QLabel()
        ic.setPixmap(app_pixmap(48).scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        t = QLabel(core.APP_NAME)
        t.setObjectName("appTitle")
        ver = QLabel(f"v{VERSION}")
        ver.setObjectName("appVer")
        for w in (ic, t, ver):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            tl.addWidget(w)
        tl.addSpacing(10)
        self.chip = QLabel("● готов")
        self.chip.setObjectName("chip")
        self.chip.setToolTip("Состояние программы")
        self.chip.setFixedHeight(22)
        tl.addWidget(self.chip, 0, Qt.AlignVCenter)
        tl.addStretch(1)
        self.btn_run = QPushButton("▶  Танцевать")
        self.btn_run.setObjectName("primary")
        self.btn_run.setToolTip("Показать сцену и слушать музыку (Esc — стоп)")
        self.btn_run.clicked.connect(self.toggle_run)
        tl.addWidget(self.btn_run, 0, Qt.AlignVCenter)
        self.btn_theme = QToolButton()
        self.btn_theme.setObjectName("hdrBtn")
        self.btn_theme.setToolTip("Светлая / тёмная тема (Ctrl+T)")
        self.btn_theme.clicked.connect(self.toggle_theme)
        tl.addWidget(self.btn_theme)
        self.btn_more = QToolButton()
        self.btn_more.setObjectName("hdrBtn")
        self.btn_more.setText("⋯")
        self.btn_more.setToolTip("Меню")
        self.btn_more.clicked.connect(lambda: self.more_menu(
            self.btn_more.mapToGlobal(QPoint(0, self.btn_more.height()))))
        tl.addWidget(self.btn_more)
        root.addWidget(self.title_bar)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(3)
        root.addWidget(self.progress)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)
        # боковая панель
        side = QWidget()
        side.setObjectName("side")
        side.setFixedWidth(88)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 8, 0, 8)
        sv.setSpacing(2)
        self.pages = QStackedWidget()
        self.side_group = QButtonGroup(self)
        self.side_btns = []
        items = (("scene", "Сцена", "Девушки, танцы и пресеты сцен", self._page_scene),
                 ("music", "Музыка", "Откуда брать такт: звук ПК, микрофон или вручную", self._page_music),
                 ("window", "Окно", "Окно сцены на рабочем столе", self._page_window),
                 ("library", "Модели", "Библиотека девушек и танцев", self._page_library),
                 ("log", "Журнал", "Журнал работы", self._page_log),
                 ("update", "Обновить", "Обновление с GitHub", self._page_update))
        for i, (key, text, tip, fn) in enumerate(items):
            b = SideButton(key, text, tip)
            self.side_group.addButton(b, i)
            self.side_btns.append(b)
            if key == "update":
                sv.addStretch(1)
            sv.addWidget(b, 0, Qt.AlignHCenter)
            self.pages.addWidget(fn())
        self.side_group.idClicked.connect(self.set_page)
        body.addWidget(side)
        right = QVBoxLayout()
        right.setContentsMargins(16, 12, 16, 12)
        right.setSpacing(12)
        right.addLayout(self._tiles())
        right.addWidget(self.pages, 1)
        body.addLayout(right, 1)
        self.set_page(min(self.cfg.get("page", 0), len(items) - 1))

    def _tiles(self):
        g = QHBoxLayout()
        g.setSpacing(10)
        self.tiles = {}
        for key, cap, tip in (("bpm", "ТЕМП, BPM", "Темп музыки — ударов в минуту"),
                              ("beat", "ДОЛЯ", "Счёт долей с начала танца"),
                              ("energy", "ГРОМКОСТЬ", "Громкость музыки — от неё размах движений"),
                              ("dancers", "ДЕВУШЕК", "Сколько девушек на сцене")):
            f = QFrame()
            f.setObjectName("tile")
            f.setToolTip(tip)
            v = QVBoxLayout(f)
            v.setContentsMargins(14, 8, 14, 8)
            v.setSpacing(0)
            val = QLabel("—")
            val.setObjectName("tileVal")
            c = QLabel(cap)
            c.setObjectName("tileCap")
            v.addWidget(val)
            v.addWidget(c)
            g.addWidget(f)
            self.tiles[key] = val
        return g

    def _page_scene(self):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)
        # слева — пресеты
        left, lv = card("Пресеты сцен")
        left.setFixedWidth(250)
        self.presets = QListWidget()
        self.presets.setToolTip("Двойной клик — загрузить сцену")
        self.presets.itemDoubleClicked.connect(lambda it: self.load_preset(it.text()))
        self.presets.setContextMenuPolicy(Qt.CustomContextMenu)
        self.presets.customContextMenuRequested.connect(self._preset_menu)
        lv.addWidget(self.presets, 1)
        b1 = QPushButton("💾 Сохранить сцену")
        b1.setToolTip("Запомнить девушек, танцы и настройки сцены под именем")
        b1.clicked.connect(self.save_preset)
        b2 = QPushButton("📂 Загрузить")
        b2.clicked.connect(lambda: self.presets.currentItem() and
                           self.load_preset(self.presets.currentItem().text()))
        b3 = QPushButton("🗑 Удалить")
        b3.clicked.connect(self.delete_preset)
        for b in (b1, b2, b3):
            lv.addWidget(b)
        sc = self.cfg["scene"]
        lv.addSpacing(6)
        lv.addWidget(QLabel("Расстояние между девушками"))
        self.f_spacing = IntField(50, 250, sc["spacing"], " %", 5, "250 %")
        lv.addWidget(stepper(self.f_spacing))
        lv.addWidget(QLabel("Свет"))
        self.f_light = IntField(10, 150, sc["light"], " %", 5, "150 %")
        lv.addWidget(stepper(self.f_light))
        self.t_shadow = Toggle(sc["shadow"], "Тень под ногами")
        lv.addWidget(row(self.t_shadow, "Тень под ногами"))
        self.t_inplace = Toggle(sc["inplace"], "Танцует на месте, не уходит из окна")
        lv.addWidget(row(self.t_inplace, "Танец на месте"))
        lv.addSpacing(4)
        lv.addWidget(QLabel("Вид"))
        self.seg_style = Segmented((("real", "Обычный", "Реалистичные девушки"),
                                    ("neon", "✨ Неон", "Светящийся контур, как неоновое видео")), sc["style"])
        lv.addWidget(self.seg_style)
        self.seg_pal = Segmented((("fire", "Огонь", "Золото сверху, пурпур снизу"),
                                  ("neon", "Неон", "Бирюза и маджента"),
                                  ("rainbow", "Радуга", "Цвета переливаются")), sc["palette"])
        lv.addWidget(self.seg_pal)
        self.f_glow = IntField(0, 200, sc["glow"], " %", 10, "200 %")
        self.f_glow.setToolTip("Сила свечения вокруг линий")
        lv.addWidget(row(QLabel("Свечение"), stepper(self.f_glow)))
        h.addWidget(left)
        # справа — девушки
        rc, rv = card("Девушки на сцене")
        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(8)
        rv.addLayout(self.rows_box)
        self.btn_add = QPushButton("➕ Добавить девушку")
        self.btn_add.setToolTip(f"До {MAX_DANCERS} девушек одновременно")
        self.btn_add.clicked.connect(self.add_dancer)
        rv.addWidget(row(self.btn_add))
        rv.addWidget(hint(
            "В комплекте 10 реалистичных девушек и 10 танцев (Microsoft Rocketbox). "
            "Свои модели GLB — в папку <b>characters/</b>, "
            "танцы — в <b>dances/</b> (страница «Модели»). Танцы Mixamo подходят к моделям "
            "Mixamo, Character Creator 4, Daz Genesis, MetaHuman и VRM — кости сопоставляются сами. "
            "Темп танца подстраивается под музыку, движения попадают в долю."))
        self.preview_box = QVBoxLayout()
        self.preview_box.setContentsMargins(0, 4, 0, 0)
        self.preview = SceneView(theme.P["panel"])
        self.preview.setMinimumHeight(220)
        self.preview.msg = "3D-сцена запускается…"
        self.preview.setToolTip("Предпросмотр сцены. На рабочий стол — кнопка «▶ Танцевать»")
        self.preview_box.addWidget(self.preview, 1)
        rv.addLayout(self.preview_box, 1)
        h.addWidget(rc, 1)
        self.dancer_rows = []
        for f in (self.f_spacing, self.f_light, self.f_glow):
            f.valueChanged.connect(lambda _: self.scene_changed())
        for sg in (self.seg_style, self.seg_pal):
            sg.changed.connect(lambda _: self.scene_changed())
        for t in (self.t_shadow, self.t_inplace):
            t.toggled.connect(lambda _: self.scene_changed())
        self._fill_presets()
        return w

    def _page_music(self):
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        a = self.cfg["audio"]
        top = QHBoxLayout()
        top.setSpacing(12)
        c1, l1 = card("Откуда брать такт")
        self.seg_src = Segmented((("loopback", "🔊 Звук ПК", "То, что играет в колонках/наушниках (любой плеер, YouTube)"),
                                  ("mic", "🎤 Микрофон", "Музыка рядом с ПК"),
                                  ("manual", "👆 Вручную", "Свой темп или «тап» в ритм")), a["source"])
        self.seg_src.changed.connect(self.set_source)
        l1.addWidget(self.seg_src)
        l1.addWidget(hint("«Звук ПК» слушает системный вывод Windows (WASAPI loopback): включите "
                          "музыку в любом плеере — девушки подхватят темп за 3–4 секунды."))
        l1.addSpacing(4)
        l1.addWidget(QLabel("Темп танца относительно музыки"))
        self.seg_mult = Segmented((("auto", "Авто", "Подбирается сам: ½, ×1 или ×2"),
                                   ("half", "×½", "Вдвое медленнее музыки"),
                                   ("normal", "×1", "Как музыка"),
                                   ("double", "×2", "Вдвое быстрее")), a.get("mult", "auto"))
        self.seg_mult.changed.connect(self._mult_changed)
        l1.addWidget(self.seg_mult)
        l1.addStretch(1)
        top.addWidget(c1, 1)
        c2, l2 = card("Сейчас")
        self.lamp = BeatLamp()
        l2.addWidget(self.lamp, 0, Qt.AlignHCenter)
        self.meter = QProgressBar()
        self.meter.setObjectName("meter")
        self.meter.setTextVisible(False)
        self.meter.setRange(0, 100)
        self.meter.setToolTip("Громкость")
        l2.addWidget(self.meter)
        self.lab_conf = hint("—")
        self.lab_conf.setAlignment(Qt.AlignCenter)
        l2.addWidget(self.lab_conf)
        c2.setFixedWidth(240)
        top.addWidget(c2)
        v.addLayout(top)
        c3, l3 = card("Ручной темп и подстройка")
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        self.f_bpm = IntField(40, 240, a["manual_bpm"], " BPM", 1, "240 BPM")
        self.f_bpm.valueChanged.connect(self._bpm_changed)
        tap = QPushButton("👆 Тап")
        tap.setToolTip("Нажимайте в ритм музыки 3–4 раза — темп подстроится")
        tap.clicked.connect(self.tap)
        g.addWidget(QLabel("Темп вручную"), 0, 0)
        g.addWidget(row(stepper(self.f_bpm), tap), 0, 1, Qt.AlignLeft)
        self.f_sens = IntField(0, 100, a["sens"], " %", 5, "240 BPM")
        self.f_sens.setToolTip("Выше — слышит тихую музыку, ниже — не реагирует на шум")
        self.f_sens.valueChanged.connect(self._sens_changed)
        g.addWidget(QLabel("Чувствительность"), 1, 0)
        g.addWidget(stepper(self.f_sens), 1, 1, Qt.AlignLeft)
        self.f_offset = IntField(-300, 300, a["offset_ms"], " мс", 10, "240 BPM")
        self.f_offset.setToolTip("Если девушки отстают от музыки — прибавьте, спешат — убавьте")
        self.f_offset.valueChanged.connect(lambda x: self._audio_set("offset_ms", x))
        g.addWidget(QLabel("Сдвиг доли"), 2, 0)
        g.addWidget(stepper(self.f_offset), 2, 1, Qt.AlignLeft)
        g.setColumnStretch(2, 1)
        l3.addLayout(g)
        v.addWidget(c3)
        v.addStretch(1)
        return page_scroll(inner)

    def _page_window(self):
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        o = self.cfg["overlay"]
        c, l = card("Окно сцены на рабочем столе")
        self.t_visible = Toggle(o["visible"], "Показать / спрятать сцену")
        self.t_visible.toggled.connect(self.set_overlay_visible)
        l.addWidget(row(self.t_visible, "Показывать сцену"))
        self.t_locked = Toggle(o["locked"], "Мышь проходит сквозь сцену к окнам под ней")
        self.t_locked.toggled.connect(self.set_locked)
        l.addWidget(row(self.t_locked, "Закрепить (клики проходят сквозь девушек)"))
        self.t_top = Toggle(o["on_top"], "Сцена поверх всех окон")
        self.t_top.toggled.connect(self.set_on_top)
        l.addWidget(row(self.t_top, "Поверх всех окон"))
        self.f_opacity = IntField(20, 100, o["opacity"], " %", 5, "100 %")
        self.f_opacity.valueChanged.connect(self.set_opacity)
        l.addWidget(row(QLabel("Непрозрачность"), stepper(self.f_opacity)))
        self.f_w = IntField(200, 3840, o["w"], " px", 20, "3840 px")
        self.f_h = IntField(220, 2160, o["h"], " px", 20, "2160 px")
        self.f_w.valueChanged.connect(self._size_changed)
        self.f_h.valueChanged.connect(self._size_changed)
        l.addWidget(row(QLabel("Размер"), stepper(self.f_w), QLabel("×"), stepper(self.f_h)))
        bc = QPushButton("⊕ По центру")
        bc.clicked.connect(lambda: self._corner("center"))
        bl = QPushButton("↙ Слева внизу")
        bl.clicked.connect(lambda: self._corner("bl"))
        br = QPushButton("↘ Справа внизу")
        br.clicked.connect(lambda: self._corner("br"))
        l.addWidget(row(bc, bl, br))
        self.seg_bg = Segmented((("transparent", "Прозрачный", "Девушки прямо на рабочем столе"),
                                 ("dark", "Тёмный", "Сцена в тёмном окне — если прозрачная не видна")),
                                o.get("bg", "transparent"))
        self.seg_bg.changed.connect(self.set_bg)
        l.addWidget(row(QLabel("Фон сцены"), self.seg_bg))
        self.seg_gpu = Segmented(self.GPU_MODES, self.cfg.get("gpu", "auto"))
        self.seg_gpu.changed.connect(self.set_gpu)
        l.addWidget(row(QLabel("Графика"), self.seg_gpu))
        bf = QPushButton("🎯 Найти сцену")
        bf.setObjectName("primary")
        bf.setToolTip("Показать окно сцены по центру экрана и снять закрепление")
        bf.clicked.connect(self.find_overlay)
        l.addWidget(row(bf))
        l.addWidget(hint("Пока сцена не закреплена, сверху у неё полоса — за неё окно двигают, "
                         "за правый нижний угол меняют размер. Закреплённая сцена не мешает "
                         "работать: клики уходят в окна под ней."))
        v.addWidget(c)
        v.addStretch(1)
        return page_scroll(inner)

    def _page_library(self):
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(12)
        self.lst_chars = QListWidget()
        self.lst_dances = QListWidget()
        for lst, title, folder, tip in (
                (self.lst_chars, "Девушки — characters/", core.CHAR_DIR,
                 "Модели GLB / GLTF (со скелетом). Свой танец внутри файла — тоже подойдёт. FBX — перевести в GLB"),
                (self.lst_dances, "Танцы — dances/", core.DANCE_DIR,
                 "Анимации GLB / GLTF (FBX из Mixamo — перевести в GLB)")):
            c, l = card(title)
            lst.setToolTip(tip)
            lst.setContextMenuPolicy(Qt.CustomContextMenu)
            lst.customContextMenuRequested.connect(
                lambda pos, w=lst, f=folder: self._lib_menu(w, f, pos))
            lst.setMinimumHeight(170)
            l.addWidget(lst, 1)
            badd = QPushButton("➕ Добавить файлы…")
            badd.clicked.connect(lambda _=False, f=folder: self.import_files(f))
            bdir = QPushButton("📂 Папка")
            bdir.clicked.connect(lambda _=False, f=folder: self.open_folder(f))
            l.addWidget(row(badd, bdir))
            top.addWidget(c, 1)
        v.addLayout(top)
        c, l = card("Где взять реалистичных девушек и танцы")
        l.addWidget(hint(
            "<b>Уже в комплекте:</b> 10 реалистичных девушек (characters/rocketbox/) и 10 танцев "
            "(dances/rocketbox/) из библиотеки <a href='https://github.com/microsoft/Microsoft-Rocketbox'>"
            "Microsoft Rocketbox</a> — лицензия MIT, можно свободно использовать.<br>"
            "<b>1. Mixamo</b> (бесплатно, нужен вход Adobe) — "
            "<a href='https://www.mixamo.com'>mixamo.com</a>: Characters → женская модель → "
            "Download <b>FBX Binary</b>; танцы: Animations → «dance» → <b>In Place</b>. "
            "FBX нужно перевести в <b>GLB</b>: бесплатный Blender → Файл → Импорт FBX → "
            "Экспорт glTF 2.0 (.glb) — девушку в characters/, танец в dances/.<br>"
            "<b>2. Character Creator 4</b> (Reallusion) — самые живые лица и кожа: экспорт GLB; "
            "скелет CC сопоставляется с танцами сам.<br>"
            "<b>3. Sketchfab</b> — <a href='https://sketchfab.com/search?features=downloadable+rigged"
            "&q=realistic+woman&type=models'>реалистичные rigged-модели</a>, качать GLB.<br>"
            "<b>4. Daz Studio</b> (Genesis 8/9) и <b>MetaHuman</b> (Unreal) — экспорт FBX → Blender → GLB; "
            "у MetaHuman поза покоя A, руки в танце могут сидеть чуть ниже.<br>"
            "Модель лучше до 100–150 тыс. полигонов и текстуры до 2K — иначе сцена тяжёлая."))
        self.btn_examples = QPushButton("⬇ Скачать пример (Michelle — из three.js)")
        self.btn_examples.setToolTip("Готовая танцующая модель Mixamo в GLB для проверки (~3 МБ)")
        self.btn_examples.clicked.connect(self.download_examples)
        l.addWidget(row(self.btn_examples))
        v.addWidget(c)
        v.addStretch(1)
        return page_scroll(inner)

    def _page_log(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        c, l = card("Журнал")
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_view.setMaximumBlockCount(3000)
        l.addWidget(self.log_view, 1)
        v.addWidget(c, 1)
        return w

    def _page_update(self):
        u = self.cfg["update"]
        tgt = gh_update.UpdateTarget(
            owner="romzespra-collab", repo="DeskDancer", name="deskdancer",
            current=VERSION, app_dir=str(core.APP_ROOT), main_file="DeskDancer.pyw",
            changelog="CHANGELOG.md", version_files=("deskdancer.py",),
            where="боковая панель → Обновить",
            user_dirs=gh_update.USER_DIRS + ("characters", "dances"))
        gh_update_qt.set_colors(lambda: {"accent": theme.P["accent"], "text": theme.P["text"],
                                         "dim": theme.P["muted"], "panel": theme.P["panel"],
                                         "border": theme.P["line"]})

        def cfg_get():
            return dict(self.cfg["update"])

        def cfg_set(d):
            self.cfg["update"].update(d)

        self.upd = gh_update_qt.UpdatePage(
            tgt, cfg_get, cfg_set, on_quit=self._quit_for_update, log=log.info,
            can_install=lambda: "сначала остановите танец (Esc)" if self.running else "")
        del u
        return self.upd

    # ---------- страницы / тема ----------
    def set_page(self, i):
        self.pages.setCurrentIndex(i)
        self.side_btns[i].setChecked(True)
        self.cfg["page"] = i
        for b in self.side_btns:
            b.update()

    def apply_theme(self):
        p = theme.apply(self.cfg.get("theme", "dark"))
        app = QApplication.instance()
        app.setStyleSheet(_qss(p))
        app.setPalette(_palette(p))
        self.btn_theme.setText("☀" if theme.NAME == "dark" else "☾")
        if getattr(self, "preview", None) is not None:
            self.preview.set_bg(p["panel"])
        for l in _LINK_LABELS:
            try:
                l.setText(_link_text(l._raw))
            except RuntimeError:
                pass
        for w in self.findChildren(QWidget):
            w.update()
        self.frame._place_grips()
        self.frame.btn_min.update()
        self.frame.btn_max.update()
        self.frame.btn_close.update()
        self._chip(self.chip.text(), self._chip_col)

    def toggle_theme(self):
        self.cfg["theme"] = "light" if theme.NAME == "dark" else "dark"
        self.apply_theme()
        log.info(f"✓ тема: {'светлая' if self.cfg['theme'] == 'light' else 'тёмная'}")

    _chip_col = None

    def _chip(self, text, col=None):
        self._chip_col = col
        self.chip.setText(text)
        c = col or theme.P["muted"]
        self.chip.setStyleSheet(f"color: {c}; border-color: {c};")

    # ---------- клавиши и меню ----------
    def _keys(self):
        QShortcut(QKeySequence("F5"), self, activated=self.refresh_library)
        QShortcut(QKeySequence("Esc"), self, activated=self.ask_stop)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_now)
        QShortcut(QKeySequence("Ctrl+T"), self, activated=self.toggle_theme)

    def more_menu(self, gpos):
        m = QMenu(self)
        acts = {
            m.addAction("🔄 Обновить библиотеку\tF5"): self.refresh_library,
            m.addAction("💾 Сохранить настройки\tCtrl+S"): self.save_now,
            m.addAction(("☾ Тёмная" if theme.NAME == "light" else "☀ Светлая") + " тема\tCtrl+T"): self.toggle_theme,
        }
        m.addSeparator()
        acts[m.addAction("📂 Папка программы")] = lambda: self.open_folder(core.APP_ROOT)
        acts[m.addAction("♻ Перезапуск")] = self.restart
        m.addSeparator()
        a_stop = m.addAction("■ Стоп\tEsc")
        a_stop.setEnabled(self.running)
        acts[a_stop] = self.ask_stop
        ch = m.exec(gpos)
        m.deleteLater()
        if ch in acts:
            acts[ch]()

    # ---------- сцена ----------
    def _rebuild_rows(self):
        while self.dancer_rows:
            r = self.dancer_rows.pop()
            r.setParent(None)
            r.deleteLater()
        for i, spec in enumerate(self.cfg["scene"]["dancers"][:MAX_DANCERS]):
            r = DancerRow(i, spec, self._chars, self._dances)
            r.changed.connect(self.scene_changed)
            r.removed.connect(self.remove_dancer)
            self.rows_box.addWidget(r)
            self.dancer_rows.append(r)
        self.btn_add.setEnabled(len(self.dancer_rows) < MAX_DANCERS)

    def add_dancer(self):
        if len(self.dancer_rows) >= MAX_DANCERS:
            return
        files = [k for k, _ in self._chars if not k.startswith("builtin:")]
        prev = self.cfg["scene"]["dancers"]
        char = files[len(prev) % len(files)] if files else ""
        kit = [k for k, _ in self._dances if k.startswith("dances/rocketbox/")]
        if files and kit:
            dance = kit[len(prev) % len(kit)]
        else:
            dance = "embedded"
        self.cfg["scene"]["dancers"].append({"char": char, "dance": dance, "scale": 100})
        self._rebuild_rows()
        self.scene_changed(from_rows=False)

    def remove_dancer(self, r):
        i = self.dancer_rows.index(r)
        del self.cfg["scene"]["dancers"][i]
        self._rebuild_rows()
        self.scene_changed(from_rows=False)

    def scene_changed(self, from_rows=True):
        sc = self.cfg["scene"]
        if from_rows:
            sc["dancers"] = [r.spec() for r in self.dancer_rows]
        sc["spacing"] = self.f_spacing.value()
        sc["light"] = self.f_light.value()
        sc["shadow"] = self.t_shadow.isChecked()
        sc["inplace"] = self.t_inplace.isChecked()
        sc["style"] = self.seg_style.value()
        sc["palette"] = self.seg_pal.value()
        sc["glow"] = self.f_glow.value()
        self.tiles["dancers"].setText(str(len(sc["dancers"])))
        self.push_scene()

    def scene_payload(self):
        sc = dict(self.cfg["scene"])
        m = self.cfg["audio"].get("mult", "auto")
        sc["mult"] = {"normal": "normal", "half": "half", "double": "double"}.get(m, "auto")
        return sc

    def push_scene(self):
        self.engine.set_scene(self.scene_payload())

    # ---------- кадры сцены ----------
    def _frame_tick(self):
        """Готовый кадр из потока сцены → окно сцены и предпросмотр; какой
        размер считать и считать ли вообще (никто не видит — пауза)."""
        ov = self.overlay
        ov_vis = ov is not None and ov.isVisible()
        pv_vis = self.preview is not None and self.preview.isVisible() and not self.isMinimized()
        self.engine.set_paused(not (ov_vis or pv_vis))
        k = 1.0 if getattr(self.engine, "soft", True) else self.devicePixelRatioF()
        if ov_vis:
            self.engine.set_size(ov.view.width() * k, ov.view.height() * k)
        elif pv_vis:
            self.engine.set_size(self.preview.width() * k, self.preview.height() * k)
        fr = self.engine.frame()
        if fr is None:
            st = self.engine.status
            if st.get("error") and self.preview is not None:
                self.preview.msg = st["error"]
                self.preview.update()
            return
        data, w, h, n = fr
        if n == self._frame_serial:
            return
        self._frame_serial = n
        from PySide6.QtGui import QImage
        img = QImage(data, w, h, w * 4, QImage.Format_ARGB32_Premultiplied).copy()
        if ov_vis:
            ov.view.set_image(img)
        if self.preview is not None:
            self.preview.msg = ""
            self.preview.set_image(img)

    def _engine_ready(self, py):
        """Отдельный Python для 3D готов — запустить движок в нём."""
        from app.engine_proc import EngineProcess
        self.cfg["runtime_python"] = py
        log.info(f"✓ 3D-движок — отдельный Python: {py}")
        old = self.engine
        self.engine = EngineProcess(core.APP_ROOT, py, gpu=self.cfg.get("gpu", "auto"), log=log.info)
        self.engine.start()
        self.engine.set_scene(old._scene or self.scene_payload())
        QTimer.singleShot(1500, lambda: self.progress.setValue(0))

    def _make_engine(self):
        """3D в этом Python (если есть Panda3D) или в отдельном (Python 3.15 и т. п.)."""
        import importlib.util
        gpu = self.cfg.get("gpu", "auto")
        if importlib.util.find_spec("panda3d") is not None:
            return Engine(core.APP_ROOT, gpu=gpu, log=log.info)
        return _PendingEngine(self, gpu)

    def _report_engine(self):
        if isinstance(self.engine, _PendingEngine):
            QTimer.singleShot(8000, self._report_engine)
            return
        st = self.engine.status
        if st.get("error"):
            log.error(f"✗ {st['error']}")
            return
        ok = sum(1 for d in st.get("dancers", []) if d.get("ok"))
        log.info(f"✓ сцена: {st.get('pipe')}, {st.get('fps')} кадров/с, девушек {ok} из {len(st.get('dancers', []))}")

    def _migrate_cfg(self):
        """Старые настройки (версии 1.x) → 2.0: манекена нет, режимы графики другие."""
        c = self.cfg
        c["gpu"] = {"opengl": "auto", "software": "soft"}.get(c.get("gpu"), c.get("gpu", "auto"))
        if c["gpu"] not in ("auto", "gpu", "soft"):
            c["gpu"] = "auto"
        kit = sorted(core.CHAR_DIR.glob("rocketbox/*.glb"))
        for i, d in enumerate(c["scene"].get("dancers", [])):
            if str(d.get("char", "")).startswith("builtin:") and kit:
                d["char"] = "characters/rocketbox/" + kit[i % len(kit)].name
            if str(d.get("dance", "")).startswith("builtin:"):
                d["dance"] = "embedded"

    def refresh_library(self, push=True):
        self._chars = core.characters()
        self._dances = core.dances()
        for lst, folder in ((self.lst_chars, core.CHAR_DIR), (self.lst_dances, core.DANCE_DIR)):
            lst.clear()
            for rel, size in core.scan_dir(folder):
                it = QListWidgetItem(f"{rel}    · {size / 1048576:.1f} МБ")
                it.setData(Qt.UserRole, rel)
                lst.addItem(it)
            if lst.count() == 0:
                it = QListWidgetItem("(пусто — добавьте файлы)")
                it.setFlags(Qt.NoItemFlags)
                lst.addItem(it)
        self._rebuild_rows()
        self.tiles["dancers"].setText(str(len(self.cfg["scene"]["dancers"])))
        nc, nd = len(self._chars), len(self._dances) - 1
        if push:
            log.info(f"✓ библиотека: девушек {nc}, танцев {nd}")
            self.push_scene()

    # ---------- пресеты ----------
    def _fill_presets(self):
        self.presets.clear()
        for name in sorted(self.cfg["presets"], key=str.lower):
            self.presets.addItem(name)

    def save_preset(self):
        cur = self.presets.currentItem()
        name, ok = QInputDialog.getText(self, "Сохранить сцену", "Имя сцены:",
                                        text=cur.text() if cur else "Моя сцена")
        name = (name or "").strip()
        if not ok or not name:
            return
        self.cfg["presets"][name] = json.loads(json.dumps(self.cfg["scene"]))
        self._fill_presets()
        log.info(f"✓ сцена «{name}» сохранена")

    def load_preset(self, name):
        sc = self.cfg["presets"].get(name)
        if not sc:
            return
        self.cfg["scene"] = core._merge(core.DEFAULT_CONFIG["scene"], sc)
        sc = self.cfg["scene"]
        for f, k in ((self.f_spacing, "spacing"), (self.f_light, "light"), (self.f_glow, "glow")):
            f.setValue(sc[k], emit=False)
        self.seg_style.set(sc["style"])
        self.seg_pal.set(sc["palette"])
        for t, k in ((self.t_shadow, "shadow"), (self.t_inplace, "inplace")):
            t.blockSignals(True)
            t.setChecked(sc[k])
            t.blockSignals(False)
        self._rebuild_rows()
        self.scene_changed(from_rows=False)
        log.info(f"✓ сцена «{name}» загружена")

    def delete_preset(self):
        cur = self.presets.currentItem()
        if not cur:
            return
        if QMessageBox.question(self, "Удалить сцену", f"Удалить пресет «{cur.text()}»?") \
                != QMessageBox.Yes:
            return
        self.cfg["presets"].pop(cur.text(), None)
        self._fill_presets()

    def _preset_menu(self, pos):
        it = self.presets.itemAt(pos)
        m = QMenu(self)
        a1 = m.addAction("📂 Загрузить")
        a2 = m.addAction("💾 Сохранить текущую сцену…")
        a3 = m.addAction("🗑 Удалить")
        a1.setEnabled(it is not None)
        a3.setEnabled(it is not None)
        ch = m.exec(self.presets.viewport().mapToGlobal(pos))
        if ch is a1 and it:
            self.load_preset(it.text())
        elif ch is a2:
            self.save_preset()
        elif ch is a3 and it:
            self.presets.setCurrentItem(it)
            self.delete_preset()

    # ---------- музыка ----------
    def _audio_set(self, k, v):
        self.cfg["audio"][k] = v

    def _bpm_changed(self, v):
        self._audio_set("manual_bpm", v)
        self.clock.set_bpm(v)

    def _sens_changed(self, v):
        self._audio_set("sens", v)
        if self.tracker is not None:
            self.tracker.sens = v

    def _mult_changed(self, k):
        self._audio_set("mult", k)
        self.push_scene()

    def tap(self):
        bpm = self.clock.tap()
        if self.cfg["audio"]["source"] != "manual":
            self.seg_src.set("manual")
            self.set_source("manual")
        self.f_bpm.setValue(round(bpm), emit=False)
        self.cfg["audio"]["manual_bpm"] = round(bpm)

    def set_source(self, src):
        self.cfg["audio"]["source"] = src
        if self.running:
            self._start_audio()
        log.info("✓ источник такта: " + {"loopback": "звук ПК", "mic": "микрофон",
                                         "manual": "вручную"}[src])

    def _start_audio(self):
        self._stop_audio()
        self._audio_err = ""
        src = self.cfg["audio"]["source"]
        if src == "manual":
            return
        self.tracker = core.BeatTracker(sens=self.cfg["audio"]["sens"])
        self.worker = core.AudioWorker(src, self.tracker, on_error=self._audio_error)
        self.worker.start()

    def _audio_error(self, text):
        core.LOG_QUEUE.put(lambda: setattr(self, "_audio_err", text))

    def _stop_audio(self):
        if self.worker is not None:
            self.worker.stop()
            self.worker = None
        self.tracker = None

    def beat_state(self):
        off = self.cfg["audio"]["offset_ms"]
        if self.cfg["audio"]["source"] == "manual":
            return self.clock.state(off)
        if self.tracker is None:
            return {"bpm": 0, "phase": 0, "conf": 0, "energy": 0, "active": False}
        return self.tracker.state(off)

    # ---------- старт / стоп ----------
    def toggle_run(self):
        if self.running:
            self.ask_stop()
        else:
            self.start()

    def start(self):
        if self.running:
            return
        self.running = True
        self.cfg["running"] = True
        self.beats = 0
        self._ensure_overlay()
        self.t_visible.setChecked(True)
        self._start_audio()
        self.btn_run.setText("■  Стоп")
        log.info("▶ танцуем")

    def ask_stop(self):
        if not self.running:
            return
        if QMessageBox.question(self, "Стоп", "Остановить танец и спрятать сцену?") \
                != QMessageBox.Yes:
            return
        self.stop()

    def stop(self):
        self.running = False
        self.cfg["running"] = False
        self._stop_audio()
        self.t_visible.setChecked(False)
        self.btn_run.setText("▶  Танцевать")
        self._chip("● готов")
        log.info("■ остановлено")

    # ---------- окно сцены ----------
    def _ensure_overlay(self):
        if self.overlay is None:
            self.overlay = Overlay(self.cfg["overlay"])
            self.overlay.btn_hide.clicked.connect(lambda: self.t_visible.setChecked(False))
            self.overlay.btn_lock.clicked.connect(lambda: self.t_locked.setChecked(True))
            self.overlay.geometryChanged.connect(self._overlay_geom)
            self.overlay.setWindowOpacity(self.cfg["overlay"]["opacity"] / 100)
            if self.cfg["overlay"]["locked"]:
                self.overlay.set_locked(True)
        return self.overlay

    def set_overlay_visible(self, on):
        self.cfg["overlay"]["visible"] = on
        if on:
            first = self.overlay is None and self.cfg["overlay"]["x"] < 0
            ov = self._ensure_overlay()
            if first:
                self._place_near_main()
            ov.show()
            ov.raise_()
            self.push_scene()
        elif self.overlay is not None:
            self.overlay.hide()

    def _place_near_main(self):
        """Сцена рядом с окном программы (справа, иначе слева, иначе по центру)."""
        ov = self.overlay
        g = self.frameGeometry()
        scr = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        w, h = ov.width(), ov.height()
        y = max(scr.top(), min(g.top(), scr.bottom() - h))
        if g.right() + 10 + w <= scr.right():
            ov.move(g.right() + 10, y)
        elif g.left() - 10 - w >= scr.left():
            ov.move(g.left() - 10 - w, y)
        else:
            ov.corner("center")

    def find_overlay(self):
        """🎯 Показать сцену по центру экрана с окном программы."""
        self.t_visible.setChecked(True)
        ov = self._ensure_overlay()
        if self.cfg["overlay"]["locked"]:
            self.t_locked.setChecked(False)
        scr = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        ov.move(scr.center().x() - ov.width() // 2, scr.center().y() - ov.height() // 2)
        ov.show()
        ov.raise_()
        ov.activateWindow()
        log.info("🎯 сцена — по центру экрана")

    # ---------- режим графики ----------
    GPU_MODES = (("auto", "Авто", "Видеокарта, а если не выйдет — процессор"),
                 ("gpu", "Видеокарта", "Только видеокарта (OpenGL, затем DirectX 9)"),
                 ("soft", "Процессор", "Без видеокарты: 3D считает процессор — работает на любом ПК"))

    def set_gpu(self, key, ask=True):
        self.cfg["gpu"] = key
        if hasattr(self, "seg_gpu"):
            self.seg_gpu.set(key)
        self.save_now(quiet=True)
        log.info(f"✓ графика: {dict((k, n) for k, n, _ in self.GPU_MODES)[key]} — после перезапуска")
        if ask and QMessageBox.question(self, "Графика", "Режим графики меняется после перезапуска.\n"
                                        "Перезапустить сейчас?") == QMessageBox.Yes:
            self.restart()

    def set_bg(self, key):
        """Фон сцены: прозрачный или тёмный — окно пересоздаётся."""
        self.cfg["overlay"]["bg"] = key
        if self.overlay is not None:
            vis = self.overlay.isVisible()
            self.overlay.close()
            self.overlay.deleteLater()
            self.overlay = None
            if vis:
                self.set_overlay_visible(True)
        log.info("✓ фон сцены: " + ("тёмный" if key == "dark" else "прозрачный"))

    def set_locked(self, on):
        self.cfg["overlay"]["locked"] = on
        if self.overlay is not None:
            self.overlay.set_locked(on)
        log.info("🔒 сцена закреплена — клики проходят сквозь неё" if on else "🔓 сцену можно двигать")

    def set_on_top(self, on):
        self.cfg["overlay"]["on_top"] = on
        if self.overlay is not None:
            self.overlay.set_on_top(on)

    def set_opacity(self, v):
        self.cfg["overlay"]["opacity"] = v
        if self.overlay is not None:
            self.overlay.setWindowOpacity(v / 100)

    def _size_changed(self, _v=None):
        o = self.cfg["overlay"]
        o["w"], o["h"] = self.f_w.value(), self.f_h.value()
        if self.overlay is not None and (self.overlay.width(), self.overlay.height()) != (o["w"], o["h"]):
            self.overlay.resize(o["w"], o["h"])

    def _corner(self, where):
        self._ensure_overlay().corner(where)

    def _overlay_geom(self):
        g = self.overlay.geometry()
        o = self.cfg["overlay"]
        o.update(x=g.x(), y=g.y(), w=g.width(), h=g.height())
        self.f_w.setValue(g.width(), emit=False)
        self.f_h.setValue(g.height(), emit=False)

    # ---------- такт: 30 раз в секунду ----------
    def _tick(self):
        if not self.running:
            return                                  # без музыки сцена сама танцует медленно
        st = self.beat_state()
        self.engine.set_beat(st)
        if st["active"] and st["phase"] < self._last_phase - 0.5:
            self.beats += 1
        self._last_phase = st["phase"]
        self.tiles["bpm"].setText(f"{st['bpm']:.0f}" if st["active"] else "—")
        self.tiles["beat"].setText(str(self.beats))
        self.tiles["energy"].setText(f"{round(st['energy'] * 100)} %")
        self.lamp.set(st["phase"], self.beats, st["active"])
        self.meter.setValue(round(st["energy"] * 100))
        src = self.cfg["audio"]["source"]
        if self._audio_err:
            self._chip("● нет звука", theme.ERR)
            self.lab_conf.setText("Звук не читается — см. журнал")
        elif st["active"]:
            self._chip("● танцуем", theme.OK)
            self.lab_conf.setText(f"уверенность такта {round(st['conf'] * 100)} %"
                                  if src != "manual" else "ручной темп")
        else:
            self._chip("● слушаю…", theme.WARN)
            self.lab_conf.setText("тишина — включите музыку")

    # ---------- библиотека ----------
    def open_folder(self, folder):
        Path(folder).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def import_files(self, folder):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Добавить модели", str(Path.home()),
            "3D-модели (*.glb *.gltf);;Все файлы (*)")
        if not files:
            return
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in files:
            src = Path(f)
            try:
                if src.suffix.lower() == ".gltf":
                    # GLTF ссылается на .bin и текстуры — берём всю папку
                    dst = folder / src.parent.name
                    if dst.exists():
                        log.warning(f"⚠ папка {dst.name} уже есть — пропуск")
                        continue
                    shutil.copytree(src.parent, dst)
                else:
                    with open(src, "rb") as fh:
                        head = fh.read(65536)
                    dst = core.unique_dest(folder, src.name, head, src.stat().st_size)
                    if dst is None:
                        log.info(f"✓ уже есть: {src.name}")
                        continue
                    shutil.copy2(src, dst)
                n += 1
                log.info(f"✓ добавлено: {dst.name}")
            except OSError as e:
                log.error(f"✗ {src.name}: {e}")
        self.refresh_library()
        if n:
            self._chip(f"● добавлено {n}", theme.OK)

    def _lib_menu(self, lst, folder, pos):
        it = lst.itemAt(pos)
        rel = it.data(Qt.UserRole) if it else None
        m = QMenu(self)
        a_dir = m.addAction("📂 Открыть папку")
        a_add = m.addAction("➕ Добавить файлы…")
        a_ref = m.addAction("🔄 Обновить\tF5")
        m.addSeparator()
        a_copy = m.addAction("📋 Копировать имя")
        a_out = m.addAction("📦 Убрать в _other/")
        a_out.setToolTip("Файл не удаляется — переносится в папку _other/")
        a_copy.setEnabled(bool(rel))
        a_out.setEnabled(bool(rel))
        ch = m.exec(lst.viewport().mapToGlobal(pos))
        if ch is a_dir:
            self.open_folder(folder)
        elif ch is a_add:
            self.import_files(folder)
        elif ch is a_ref:
            self.refresh_library()
        elif ch is a_copy and rel:
            QApplication.clipboard().setText(rel)
        elif ch is a_out and rel:
            src = Path(folder) / rel
            other = Path(folder) / "_other"
            other.mkdir(exist_ok=True)
            dst = core.unique_dest(other, src.name)
            try:
                if dst is None:
                    dst = other / f"{src.stem} ({int(time.time())}){src.suffix}"
                shutil.move(str(src), str(dst))
                log.info(f"✓ {rel} → _other/{dst.name}")
            except OSError as e:
                log.error(f"✗ {rel}: {e}")
            self.refresh_library()

    def download_examples(self):
        if self._dl_thread and self._dl_thread.is_alive():
            return
        self.btn_examples.setEnabled(False)
        self.progress.setValue(0)

        def prog(v):
            core.LOG_QUEUE.put(lambda: self.progress.setValue(v))

        def work():
            try:
                got = core.download_examples(progress=prog)
                core.LOG_QUEUE.put(lambda: self._examples_done(got))
            except Exception as e:                      # noqa: BLE001
                log.error(f"✗ примеры: {e}")
                core.LOG_QUEUE.put(lambda: self._examples_done(0))

        self._chip("● скачиваю…", theme.WARN)
        self._dl_thread = threading.Thread(target=work, daemon=True, name="examples")
        self._dl_thread.start()

    def _examples_done(self, got):
        self.btn_examples.setEnabled(True)
        self.refresh_library()
        if got:
            sc = self.cfg["scene"]["dancers"]
            if all(d["char"].startswith("builtin:") for d in sc):
                self.cfg["scene"]["dancers"] = [
                    {"char": "characters/Michelle.glb", "dance": "embedded", "scale": 100}]
                self._rebuild_rows()
                self.scene_changed(from_rows=False)
        QTimer.singleShot(1500, lambda: self.progress.setValue(0))
        self._chip("● готов" if not self.running else self.chip.text())

    # ---------- журнал ----------
    def _drain_log(self):
        bar = self.log_view.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 2
        n = 0
        while n < 300:
            try:
                item = core.LOG_QUEUE.get_nowait()
            except Exception:                               # noqa: BLE001
                break
            n += 1
            if callable(item):
                try:
                    item()
                except Exception as e:                      # noqa: BLE001
                    log.error(f"✗ {e}")
                continue
            if item is core.DONE:
                continue
            fmt = QTextCharFormat()
            if "✗" in item or "⛔" in item:
                fmt.setForeground(QColor(theme.ERR))
            elif "⚠" in item:
                fmt.setForeground(QColor(theme.WARN))
            elif "✓" in item or "✅" in item:
                fmt.setForeground(QColor(theme.OK))
            else:
                fmt.setForeground(QColor(theme.P["log_fg"]))
            cur = QTextCursor(self.log_view.document())
            cur.movePosition(QTextCursor.End)
            if not self.log_view.document().isEmpty():
                cur.insertBlock()
            cur.insertText(item, fmt)
        if n and at_end:
            bar.setValue(bar.maximum())

    # ---------- настройки ----------
    def _dump(self):
        return json.dumps({k: v for k, v in self.cfg.items() if not k.startswith("_")},
                          ensure_ascii=False, sort_keys=True)

    def _autosave(self):
        d = self._dump()
        if d != self._saved:
            self.save_now(quiet=True)

    def save_now(self, quiet=False):
        self.cfg["geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        try:
            if core.save_config(self.cfg):
                self._saved = self._dump()
                if not quiet:
                    log.info("✓ настройки сохранены")
        except OSError as e:
            log.error(f"✗ настройки не сохранились: {e}")

    def _restore_geometry(self):
        g = self.cfg.get("geometry")
        if g:
            try:
                self.restoreGeometry(QByteArray.fromBase64(g.encode()))
                return
            except Exception:                               # noqa: BLE001
                pass
        self.resize(1080, 700)

    # ---------- выход ----------
    def restart(self):
        if getattr(self.upd.box, "busy", lambda: False)():
            QMessageBox.information(self, "Перезапуск", "Идёт обновление — дождитесь конца.")
            return
        self.save_now(quiet=True)
        args = [sys.executable] + ([] if getattr(sys, "frozen", False)
                                   else [str(core.APP_ROOT / "DeskDancer.pyw")])
        try:
            subprocess.Popen(args, cwd=str(core.APP_ROOT))
        except OSError as e:
            log.error(f"✗ перезапуск: {e}")
            return
        self._force_close = True
        self.close()

    def _quit_for_update(self):
        self._force_close = True
        self.close()

    def closeEvent(self, e):
        try:
            busy = self.upd.box.busy()
        except Exception:                                   # noqa: BLE001
            busy = False
        if busy and not getattr(self, "_force_close", False):
            QMessageBox.information(self, "Закрыть", "Идёт установка обновления — дождитесь конца.")
            e.ignore()
            return
        self.save_now(quiet=True)
        self._stop_audio()                      # ждём остановки потока звука
        self.engine.stop()
        if self.overlay is not None:
            self.overlay.close()
        super().closeEvent(e)


# ───────────────────────── правый клик и полосы диалогов ─────────────────────────
class AppFilter(QObject):
    """Один фильтр на всё приложение: русское меню у полей, текстов и
    списков; на фоне главного окна — меню «⋯»; системная полоса диалогов
    — в цвет темы (Windows, DWM)."""

    def __init__(self, main):
        super().__init__()
        self.main = main

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.ContextMenu and isinstance(obj, QWidget):
            return self._context(obj, ev)
        if t == QEvent.Show and sys.platform == "win32" and isinstance(obj, QWidget) \
                and obj.isWindow() and not (obj.windowFlags() & Qt.FramelessWindowHint):
            _dwm_color(obj)
        return False

    def _context(self, obj, ev):
        w = obj
        if w.contextMenuPolicy() == Qt.CustomContextMenu:
            return False
        par = w.parentWidget()
        if isinstance(par, (QPlainTextEdit, QTextEdit, QListWidget, QTableWidget)) and \
                par.viewport() is w:
            if par.contextMenuPolicy() == Qt.CustomContextMenu:
                return False
            w = par
        gp = ev.globalPos()
        if isinstance(w, QLineEdit):
            self._edit_menu(w, gp)
            return True
        if isinstance(w, (QPlainTextEdit, QTextEdit)):
            self._text_menu(w, gp)
            return True
        if isinstance(w, (QListWidget, QTableWidget)):
            self._list_menu(w, gp)
            return True
        if w.window() is self.main and not isinstance(w, (QAbstractButton, QComboBox)):
            self.main.more_menu(gp)
            return True
        return False

    @staticmethod
    def _run(m, gp, acts):
        ch = m.exec(gp)
        m.deleteLater()
        if ch in acts:
            acts[ch]()

    def _edit_menu(self, e, gp):
        m = QMenu(e)
        ro = e.isReadOnly()
        has = e.hasSelectedText()
        acts = {}
        for text, fn, ok in (("↶ Отменить", e.undo, e.isUndoAvailable() and not ro),
                             ("↷ Повторить", e.redo, e.isRedoAvailable() and not ro),
                             (None, None, None),
                             ("✂ Вырезать", e.cut, has and not ro and e.echoMode() == QLineEdit.Normal),
                             ("📋 Копировать", e.copy, has and e.echoMode() == QLineEdit.Normal),
                             ("📥 Вставить", e.paste, not ro),
                             ("🗑 Удалить", e.del_, has and not ro),
                             (None, None, None),
                             ("Выделить всё", e.selectAll, bool(e.text()))):
            if text is None:
                m.addSeparator()
                continue
            a = m.addAction(text)
            a.setEnabled(bool(ok))
            acts[a] = fn
        self._run(m, gp, acts)

    def _text_menu(self, e, gp):
        m = QMenu(e)
        acts = {}
        has = e.textCursor().hasSelection()
        a = m.addAction("📋 Копировать")
        a.setEnabled(has)
        acts[a] = e.copy
        acts[m.addAction("📋 Копировать всё")] = \
            lambda: QApplication.clipboard().setText(e.toPlainText())
        acts[m.addAction("Выделить всё")] = e.selectAll
        if e is getattr(self.main, "log_view", None):
            m.addSeparator()
            acts[m.addAction("💾 Сохранить в файл…")] = self._save_log
            acts[m.addAction("🧹 Очистить")] = e.clear
        elif not e.isReadOnly():
            acts[m.addAction("📥 Вставить")] = e.paste
        self._run(m, gp, acts)

    def _save_log(self):
        fn, _ = QFileDialog.getSaveFileName(self.main, "Сохранить журнал",
                                            str(core.APP_ROOT / "журнал.txt"),
                                            "Текст (*.txt)")
        if fn:
            Path(fn).write_text(self.main.log_view.toPlainText(), encoding="utf-8")

    def _list_menu(self, w, gp):
        m = QMenu(w)
        acts = {}
        if isinstance(w, QListWidget):
            items = [w.item(i).text() for i in range(w.count())]
            sel = [i.text() for i in w.selectedItems()]
        else:
            items, sel = [], []
            for r in range(w.rowCount()):
                cells = [(w.item(r, c).text() if w.item(r, c) else "") for c in range(w.columnCount())]
                items.append("\t".join(cells))
            sel = sorted({i.row() for i in w.selectedItems()})
            sel = [items[r] for r in sel]
        a = m.addAction("📋 Копировать")
        a.setEnabled(bool(sel))
        acts[a] = lambda: QApplication.clipboard().setText("\n".join(sel))
        acts[m.addAction("📋 Копировать всё")] = lambda: QApplication.clipboard().setText("\n".join(items))
        self._run(m, gp, acts)


def _dwm_color(win):
    """Системная полоса окна (диалоги) — тёмная/светлая и в цвет темы."""
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = int(win.winId())
        dark = ctypes.c_int(1 if theme.NAME == "dark" else 0)
        dwm = ctypes.windll.dwmapi
        if dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 20, ctypes.byref(dark), 4) != 0:
            dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 19, ctypes.byref(dark), 4)

        def cref(hexcol):
            c = QColor(hexcol)
            return ctypes.c_int(c.red() | (c.green() << 8) | (c.blue() << 16))
        cap, txt = cref(theme.P["side"]), cref(theme.P["text"])
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 35, ctypes.byref(cap), 4)
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), 36, ctypes.byref(txt), 4)
        if win.isVisible():
            ctypes.windll.user32.SetWindowPos(wintypes.HWND(hwnd), 0, 0, 0, 0, 0,
                                              0x0001 | 0x0002 | 0x0004 | 0x0020)
    except Exception:                                       # noqa: BLE001
        pass


# ───────────────────────── запуск ─────────────────────────
def run(argv=None, offscreen_test=None):
    argv = list(argv if argv is not None else sys.argv)
    try:
        gh_update.wait_previous(argv)
    except Exception:                                       # noqa: BLE001
        pass
    cfg = core.load_config()
    QApplication.setAttribute(Qt.AA_DontUseNativeDialogs, True)
    app = QApplication.instance() or QApplication(argv)
    app.setStyle("Fusion")
    from PySide6.QtCore import QLibraryInfo, QTranslator
    tr = QTranslator(app)
    if tr.load("qtbase_ru", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(tr)
    app.setApplicationName(core.APP_NAME)
    app.setWindowIcon(app_icon())
    for d in (core.CHAR_DIR, core.DANCE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    win = MainWindow(cfg)
    filt = AppFilter(win)
    app.installEventFilter(filt)
    win._filter = filt
    if offscreen_test:
        return offscreen_test(app, win)
    win.show()
    return app.exec()
