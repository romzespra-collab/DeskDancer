"""window_frame.py  v5.15.56

Журнал:
v5.15.56: и для дополнительных окон (dialog_frame): kinds — какие кнопки ставить («✕» или «□ ✕», без «—»), меню окна — по ним же; окно постоянного размера (сообщение) за края не тянется — края только рисуют рамку и пропускают мышь
v5.15.30: развёрнутое окно восстанавливается, только когда заголовок ПОТЯНУЛИ (простой щелчок его сворачивал в обычное); убран неиспользуемый self.buttons
v5.15.0: выпуск 5.15
v5.14.0: выпуск 5.14
v5.13.32: полный анализ: меню полосы окна удаляется после показа (не копятся); убран неиспользуемый is_maximized
v5.13.18: края окна — поверх всего, что кладут в окно после показа (окно архива: список, поиск и архив переносятся в уже показанное окно и закрывали края — окно не тянулось за край)
v5.13.11: кнопки «— □ ✕» уже — 30 px вместо 46 (как у SmartPSS значки рядом, а не врозь)
v5.13.3: значки кнопок окна рисуются сами (линия, ровный квадрат, два
         квадрата, крестик — как в Windows 11; шрифтовый «□» был мелкий и
         кривой); кнопки 46 px на всю высоту полосы; on_min — своё действие
         кнопки «—» (окно архива: вернуть в главное окно вместо «Свернуть»)
v5.13.0: своя рамка окна, как в SmartPSS — без белой (или чёрной) системной
         полосы заголовка: полоса вкладок окна сама служит заголовком в цвет
         схемы; кнопки «— □ ×», перетаскивание и двойной клик по полосе,
         правый клик — меню окна, края окна тянутся мышью

Окно делается без системной рамки (Qt.FramelessWindowHint), а всё, что
давала рамка, делаем сами:
  * перетаскивание — по пустому месту полосы (ярлыки, отступы): системный
    перенос окна (QWindow.startSystemMove), окно ведёт сама Windows;
  * двойной клик по полосе — развернуть / вернуть; развернуть — на рабочую
    область экрана (без панели задач): окно без рамки, развёрнутое
    средствами Windows, закрывало бы и её;
  * края — 5-пиксельные полоски по периметру окна (startSystemResize),
    заодно рисуют тонкую рамку цветом схемы;
  * кнопки «Свернуть / Развернуть / Закрыть» справа на полосе;
  * правый клик по полосе — те же действия меню.
"""
from PySide6.QtCore import (QEvent, QObject, QPoint, QPointF, QRect, QSize,
                            Qt, QTimer)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLayout, QMenu,
                               QSizePolicy, QToolButton, QWidget)

from . import theme

GRIP = 5            # ширина краёв, за которые тянут окно
BTN_W = 30          # ★ 5.13.11: ширина кнопки окна (было 46 — как в Windows)


class _WinButton(QToolButton):
    """★ 5.13.3: кнопка окна со значком, нарисованным самим: «—» линия,
    «□» ровный квадрат 10×10, «❐» два квадрата, «✕» крестик. Фон при
    наведении — из QSS (#winBtn / #winClose)."""

    def __init__(self, kind, tip, slot):
        super().__init__()
        self.kind = kind
        self.setObjectName("winClose" if kind == "close" else "winBtn")
        self.setToolTip(tip)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedWidth(BTN_W)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.clicked.connect(slot)

    def sizeHint(self):
        return QSize(BTN_W, 32)

    def set_kind(self, kind):
        self.kind = kind
        self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)                 # фон из QSS (наведение)
        hot = self.underMouse() or self.isDown()
        if self.kind == "close" and hot:
            col = QColor("#ffffff")
        else:
            col = QColor(theme.TEXT if hot else theme.TEXT_DIM)
        p = QPainter(self)
        p.setPen(QPen(col, 1))
        p.setBrush(Qt.NoBrush)
        cx, cy = self.width() // 2, self.height() // 2
        k = self.kind
        if k == "min":
            p.drawLine(QPoint(cx - 5, cy), QPoint(cx + 4, cy))
        elif k == "max":
            p.drawRect(QRect(cx - 5, cy - 5, 9, 9))
        elif k == "restore":
            p.drawRect(QRect(cx - 5, cy - 3, 7, 7))
            p.drawLine(QPoint(cx - 3, cy - 3), QPoint(cx - 3, cy - 5))
            p.drawLine(QPoint(cx - 3, cy - 5), QPoint(cx + 4, cy - 5))
            p.drawLine(QPoint(cx + 4, cy - 5), QPoint(cx + 4, cy + 2))
            p.drawLine(QPoint(cx + 4, cy + 2), QPoint(cx + 3, cy + 2))
        elif k == "close":
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setPen(QPen(col, 1.3))     # сглаженная косая бледнее прямых
            p.drawLine(QPointF(cx - 4.5, cy - 4.5), QPointF(cx + 4.5, cy + 4.5))
            p.drawLine(QPointF(cx + 4.5, cy - 4.5), QPointF(cx - 4.5, cy + 4.5))
        p.end()


def resizable(win):
    """★ 5.15.56: окно можно тянуть за края (у сообщения размер постоянный)."""
    try:
        if win.minimumSize() == win.maximumSize():
            return False
        lay = win.layout()
        return lay is None or \
            lay.sizeConstraint() != QLayout.SizeConstraint.SetFixedSize
    except RuntimeError:
        return False


class _Grip(QWidget):
    """Край окна: тянут — меняется размер (системно). Рисует 1 px рамки."""

    def __init__(self, win, edges, cursor):
        super().__init__(win)
        self.edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            if not resizable(self.window()):
                ev.accept()
                return
            h = self.window().windowHandle()
            if h is not None:
                h.startSystemResize(self.edges)
            ev.accept()
            return
        super().mousePressEvent(ev)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setPen(QColor(theme.BORDER))
        r = self.rect()
        e = self.edges
        if e & Qt.LeftEdge:
            p.drawLine(r.left(), r.top(), r.left(), r.bottom())
        if e & Qt.RightEdge:
            p.drawLine(r.right(), r.top(), r.right(), r.bottom())
        if e & Qt.TopEdge:
            p.drawLine(r.left(), r.top(), r.right(), r.top())
        if e & Qt.BottomEdge:
            p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        p.end()


class WindowFrame(QObject):
    """Своя рамка для окна верхнего уровня. title — виджет-полоса, за пустое
    место которой окно тянут; buttons_layout — куда (в конец) поставить
    кнопки «— □ ×». Звать ДО первого show(): смена флагов у показанного окна
    пересоздала бы его HWND (и поверхности видео внутри). ★ 5.13.3: on_min —
    своё действие кнопки «—» вместо «Свернуть» (подсказка min_tip; в меню
    окна «Свернуть» тогда нет), close_tip — подсказка крестика."""

    def __init__(self, win, title, buttons_layout=None, own_menu=True,
                 on_min=None, min_tip=None, close_tip=None,
                 kinds=("min", "max", "close")):
        super().__init__(win)
        self.win = win
        self.title = title
        self.kinds = tuple(kinds)          # ★ 5.15.56: какие кнопки окна
        self._maxed = False
        self._normal = None
        self._own_min = on_min is None and "min" in self.kinds
        self._grips = []
        self._raise_due = False
        flags = win.windowFlags() | Qt.FramelessWindowHint \
            | Qt.WindowSystemMenuHint
        if "min" in self.kinds:
            flags |= Qt.WindowMinMaxButtonsHint
        win.setWindowFlags(flags)
        title.installEventFilter(self)
        if own_menu:          # иначе меню полосы — у окна (add_menu_items)
            title.setContextMenuPolicy(Qt.CustomContextMenu)
            title.customContextMenuRequested.connect(
                lambda p: self.menu(title.mapToGlobal(p)))
        win.installEventFilter(self)
        # кнопки окна
        box = QWidget()
        box.setObjectName("winButtons")
        hl = QHBoxLayout(box)
        hl.setContentsMargins(6, 0, 0, 0)
        hl.setSpacing(0)
        box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.btn_min = _WinButton("min", min_tip or "Свернуть",
                                  on_min or win.showMinimized)
        self.btn_max = _WinButton("max", "Развернуть", self.toggle_max)
        self.btn_close = _WinButton("close", close_tip or "Закрыть",
                                    win.close)
        for b, k in ((self.btn_min, "min"), (self.btn_max, "max"),
                     (self.btn_close, "close")):
            if k in self.kinds:
                hl.addWidget(b)
            else:
                b.hide()
        self._press_at = None          # ★ 5.15.30: щелчок по заголовку
        if buttons_layout is not None:
            buttons_layout.addWidget(box)
        # края
        L, R, T, B = Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge
        self._grips = [
            _Grip(win, L, Qt.SizeHorCursor), _Grip(win, R, Qt.SizeHorCursor),
            _Grip(win, T, Qt.SizeVerCursor), _Grip(win, B, Qt.SizeVerCursor),
            _Grip(win, T | L, Qt.SizeFDiagCursor),
            _Grip(win, B | R, Qt.SizeFDiagCursor),
            _Grip(win, T | R, Qt.SizeBDiagCursor),
            _Grip(win, B | L, Qt.SizeBDiagCursor)]
        self._place_grips()

    # --- развернуть / вернуть ---
    def toggle_max(self):
        if self._maxed:
            self.restore()
        else:
            self.maximize()

    def maximize(self):
        """На рабочую область экрана, где окно (панель задач остаётся)."""
        if self._maxed or "max" not in self.kinds:
            return
        scr = self.win.screen()
        if scr is None:
            return
        self._normal = self.win.geometry()
        self._maxed = True
        self.win.setGeometry(scr.availableGeometry())
        self._sync()

    def restore(self, under=None):
        """Вернуть прежний размер. under — точка экрана, которая должна
        остаться под мышью (окно тянут из развёрнутого)."""
        if not self._maxed:
            return
        self._maxed = False
        g = QRect(self._normal) if self._normal is not None \
            else QRect(self.win.geometry().adjusted(60, 60, -60, -60))
        if under is not None:
            # мышь остаётся на той же доле ширины полосы, верх — где был
            cur = self.win.geometry()
            fx = (under.x() - cur.x()) / max(1, cur.width())
            g.moveLeft(int(under.x() - fx * g.width()))
            g.moveTop(cur.y())
        self.win.setGeometry(g)
        self._sync()

    def _sync(self):
        self.btn_max.set_kind("restore" if self._maxed else "max")
        self.btn_max.setToolTip("Восстановить" if self._maxed else "Развернуть")
        self._place_grips()

    # --- края ---
    def _place_grips(self):
        w, h = self.win.width(), self.win.height()
        g = GRIP
        rects = [QRect(0, g, g, h - 2 * g), QRect(w - g, g, g, h - 2 * g),
                 QRect(g, 0, w - 2 * g, g), QRect(g, h - g, w - 2 * g, g),
                 QRect(0, 0, g, g), QRect(w - g, h - g, g, g),
                 QRect(w - g, 0, g, g), QRect(0, h - g, g, g)]
        show = not self._maxed
        # ★ 5.15.56: окно постоянного размера — края мышь пропускают (к
        # кнопке «✕» под ними), только рисуют рамку
        through = not resizable(self.win)
        for grip, r in zip(self._grips, rects):
            try:
                grip.setGeometry(r)
                grip.setAttribute(Qt.WA_TransparentForMouseEvents, through)
                grip.setVisible(show)
                if show:
                    grip.raise_()
            except RuntimeError:
                pass

    def _raise_grips(self):
        """★ 5.13.18: края — снова поверх всего в окне."""
        self._raise_due = False
        try:
            self._place_grips()
        except RuntimeError:          # окно уже удалено
            pass

    # --- меню окна (правый клик по полосе) ---
    def add_menu_items(self, m):
        acts = {}
        if self._own_min:      # ★ 5.13.3: у «—» своё действие — не «Свернуть»
            acts[m.addAction("— Свернуть")] = self.win.showMinimized
        if "max" in self.kinds:
            acts[m.addAction("❐ Восстановить" if self._maxed
                             else "□ Развернуть")] = self.toggle_max
            m.addSeparator()
        acts[m.addAction("✕ Закрыть")] = self.win.close
        return acts

    def menu(self, gpos):
        m = QMenu(self.win)
        acts = self.add_menu_items(m)
        chosen = m.exec(gpos)
        m.deleteLater()            # ★ 5.13.32: меню не копятся
        fn = acts.get(chosen)
        if fn is not None:
            fn()

    # --- события ---
    def eventFilter(self, obj, ev):
        t = ev.type()
        if obj is self.title:
            if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                gp = ev.globalPosition().toPoint()
                if self._maxed:
                    # ★ 5.15.30: развёрнутое — восстанавливать только когда
                    # ПОТЯНУЛИ (простой щелчок по заголовку его сворачивал
                    # в обычное, двойной — разворачивал обратно)
                    self._press_at = gp
                    return True
                h = self.win.windowHandle()
                if h is not None:
                    h.startSystemMove()
                return True
            if t == QEvent.MouseMove and self._press_at is not None:
                gp = ev.globalPosition().toPoint()
                if (gp - self._press_at).manhattanLength() >= \
                        QApplication.startDragDistance():
                    self._press_at = None
                    if self._maxed:
                        self.restore(under=gp)
                    h = self.win.windowHandle()
                    if h is not None:
                        h.startSystemMove()
                return True
            if t == QEvent.MouseButtonRelease:
                self._press_at = None
            if t == QEvent.MouseButtonDblClick and \
                    ev.button() == Qt.LeftButton:
                self.toggle_max()
                return True
        elif obj is self.win:
            if t in (QEvent.Resize, QEvent.Show):
                self._place_grips()
            elif t == QEvent.ChildAdded and not self._raise_due:
                # ★ 5.13.18: новый ребёнок окна ложится ПОВЕРХ краёв — и
                # ловит мышь вместо них. Окно архива показывается раньше, чем
                # в него переносят список, поиск и сам архив, — края слева,
                # справа и снизу были закрыты, окно не тянулось за край
                self._raise_due = True
                QTimer.singleShot(0, self._raise_grips)
            elif t == QEvent.WindowStateChange and \
                    self.win.windowState() & Qt.WindowMaximized:
                # развернули не нашей кнопкой (Win+↑, двойной клик системы) —
                # по-своему: на рабочую область, без панели задач
                self.win.setWindowState(Qt.WindowNoState)
                self.maximize()
        return False

