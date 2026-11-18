"""int_field.py  v5.19.0

Журнал:
v5.19.0: общий модуль для всех проектов (главная копия — SmartMon). Ошибка: setValue при заглушённых
        программой сигналах (blockSignals(True)) всё равно слал valueChanged — поле само снимало заглушку;
        теперь возвращает прежнее состояние. Новое (по желанию, поведение по умолчанию прежнее):
        setWheelNeedsFocus(True) — колесо меняет число только у поля в фокусе (прокрутка страницы);
        setAutoWidth(False) — не подбирать ширину самому (ширина программы не перебивается);
        setEnterApplyOnly(True) — Enter после набора только применяет число (не нажимает кнопку диалога);
        горизонтальная прокрутка колесом больше не съедается полем; ширина учитывает отступы QSS
        программы (большой padding — цифры не обрезаются);
        IntField(buttons="around") — кнопки по бокам [−][поле][+]; DoubleEdit.setDecimalComma(True) —
        запятая вместо точки; ввод понимает «−» и неразрывный пробел; setDecimals переокругляет пределы
        и число; VERSION и selftest().
v5.16.107: value() берёт набранное без Enter / ухода фокуса (Ctrl+S, закрыли окно — сохранялось прежнее число)
v5.16.85: убран неиспользуемый _sig_type
v5.16.6: поле-число на обычном QLineEdit вместо QSpinBox (на Windows с
        Fusion + QSS QSpinBox прятал и обрезал цифры, QSS-костыли не
        помогали). IntEdit / DoubleEdit — само поле: текст по центру, колесо
        и ↑/↓ (PgUp/PgDn — ×10) меняют число, ввод применяется по Enter или
        уходу фокуса, кривой ввод откатывается; API как у QSpinBox (value,
        setValue, valueChanged, stepBy, setRange, setSuffix,
        setSpecialValueText …). IntField / DoubleField — поле и отдельные
        кнопки [−][+] (QPushButton#intStep); прочие вызовы уходят полю.
"""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QPushButton,
                               QSizePolicy, QWidget)

VERSION = "5.19.0"

_BTN_W = 22          # ширина кнопки [−] / [+]
_GAP = 2             # промежуток между полем и кнопками
_PAD = 18            # запас по ширине текста: padding 2px, рамка, курсор


class IntEdit(QLineEdit):
    """Целое число в обычной строке ввода (без кнопок)."""

    valueChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("intField")
        self.setAlignment(Qt.AlignCenter)
        self._min, self._max, self._step = 0, 99, 1
        self._val = 0
        self._prefix = self._suffix = self._special = ""
        self._wrap = False
        self._wheel_focus = False
        self._auto_w = True
        self._enter_only = False
        self.editingFinished.connect(self.interpretText)
        self._show()
        self._fit()

    # --- значение ---
    def _norm(self, v):
        return int(round(v))

    def _fmt(self, v):
        return str(v)

    def _parse(self, s):
        return int(s)

    def value(self):
        # ★ 5.16.107: набрали число и сразу «Сохранить» / Ctrl+S / закрыли
        # окно без Enter и ухода фокуса — берём набранное, а не прежнее
        if self.text() != self.textFromValue(self._val):
            self.interpretText()
        return self._val

    def setValue(self, v):                         # noqa: N802 (Qt)
        try:
            v = self._norm(v)
        except (TypeError, ValueError):
            v = self._min
        v = max(self._min, min(self._max, v))
        changed = v != self._val
        self._val = v
        self._show()
        if changed:
            self.valueChanged.emit(v)

    def textFromValue(self, v):                    # noqa: N802 (Qt)
        if v == self._min and self._special:
            return self._special
        return "%s%s%s" % (self._prefix, self._fmt(v), self._suffix)

    def _show(self):
        t = self.textFromValue(self._val)
        if self.text() != t:
            # editingFinished не нужен; ★ 5.19.0: прежнее состояние, а не «снять» — иначе
            # blockSignals(True) программы снимался, и setValue слал valueChanged
            old = self.blockSignals(True)
            self.setText(t)
            self.blockSignals(old)

    def cleanText(self):                           # noqa: N802 (Qt)
        s = self.text().strip()
        if self._prefix and s.startswith(self._prefix.strip()):
            s = s[len(self._prefix.strip()):]
        if self._suffix and s.endswith(self._suffix.strip()):
            s = s[:-len(self._suffix.strip())]
        for sp in (" ", "\u00a0", "\u202f"):              # пробел, неразрывные
            s = s.replace(sp, "")
        return s.strip().replace(",", ".").replace("\u2212", "-")

    def interpretText(self):                       # noqa: N802 (Qt)
        """Применить набранное; кривой ввод — откат к прежнему числу."""
        s = self.text().strip()
        if self._special and s == self._special:
            self.setValue(self._min)
            return
        try:
            v = self._parse(self.cleanText())
        except (TypeError, ValueError):
            self._show()
            return
        self.setValue(v)
        self._show()                               # обрезанное по пределам

    def stepBy(self, n):                           # noqa: N802 (Qt)
        self.interpretText()
        v = self._val + n * self._step
        if self._wrap and self._max > self._min:
            if v > self._max:
                v = self._min
            elif v < self._min:
                v = self._max
        self.setValue(v)
        if self.hasFocus():
            self.selectAll()

    def stepUp(self):                              # noqa: N802 (Qt)
        self.stepBy(1)

    def stepDown(self):                            # noqa: N802 (Qt)
        self.stepBy(-1)

    # --- пределы и вид ---
    def setRange(self, lo, hi):                    # noqa: N802 (Qt)
        lo, hi = self._norm(lo), self._norm(hi)
        self._min, self._max = lo, max(lo, hi)
        self._fit()
        self.setValue(self._val)
        self._show()

    def setMinimum(self, lo):                      # noqa: N802 (Qt)
        self.setRange(lo, max(lo, self._max))

    def setMaximum(self, hi):                      # noqa: N802 (Qt)
        self.setRange(min(self._min, hi), hi)

    def minimum(self):
        return self._min

    def maximum(self):
        return self._max

    def setSingleStep(self, s):                    # noqa: N802 (Qt)
        self._step = s

    def singleStep(self):                          # noqa: N802 (Qt)
        return self._step

    def setSuffix(self, s):                        # noqa: N802 (Qt)
        self._suffix = s or ""
        self._fit()
        self._show()

    def suffix(self):
        return self._suffix

    def setPrefix(self, s):                        # noqa: N802 (Qt)
        self._prefix = s or ""
        self._fit()
        self._show()

    def prefix(self):
        return self._prefix

    def setSpecialValueText(self, s):              # noqa: N802 (Qt)
        self._special = s or ""
        self._fit()
        self._show()

    def specialValueText(self):                    # noqa: N802 (Qt)
        return self._special

    def setWrapping(self, on):                     # noqa: N802 (Qt)
        self._wrap = bool(on)

    def setWheelNeedsFocus(self, on):              # noqa: N802 (Qt)
        """Колесо меняет число только у поля в фокусе (иначе крутит страницу)."""
        self._wheel_focus = bool(on)

    def setAutoWidth(self, on):                    # noqa: N802 (Qt)
        """False — ширину не подбирать самому (программа задаёт свою)."""
        self._auto_w = bool(on)
        if on:
            self._fit()

    def setEnterApplyOnly(self, on):               # noqa: N802 (Qt)
        """Enter после набора только применяет число и не уходит дальше (кнопка диалога по умолчанию)."""
        self._enter_only = bool(on)

    # у QSpinBox есть — здесь не нужны
    def setKeyboardTracking(self, _on):            # noqa: N802 (Qt)
        pass

    def setButtonSymbols(self, _s):                # noqa: N802 (Qt)
        pass

    def setAccelerated(self, _on):                 # noqa: N802 (Qt)
        pass

    def _style_pad(self):
        """Поля стиля вокруг текста (рамка + padding из QSS + отступы) — по самому стилю."""
        try:
            from PySide6.QtWidgets import QStyle, QStyleOptionFrame
            opt = QStyleOptionFrame()
            self.initStyleOption(opt)
            r = self.style().subElementRect(QStyle.SE_LineEditContents, opt, self)
            m = self.textMargins()
            extra = self.width() - r.width() + m.left() + m.right()
            return extra + 6 if 0 <= extra < 200 else 0          # +6: курсор и запас
        except Exception:                                       # noqa: BLE001
            return 0

    def need_width(self):
        """Ширина под самое длинное значение (с запасом; ★ 5.19.0: и с отступами QSS программы)."""
        fm = self.fontMetrics()
        texts = [self.textFromValue(self._min), self.textFromValue(self._max),
                 "%s%s%s" % (self._prefix, self._fmt(self._min), self._suffix)]
        return max(fm.horizontalAdvance(t) for t in texts) + max(_PAD, self._style_pad())

    def _fit(self):
        if getattr(self, "_auto_w", True):
            self.setMinimumWidth(self.need_width())

    # --- колесо и клавиши ---
    def wheelEvent(self, ev):                      # noqa: N802 (Qt)
        if not self.isEnabled() or self.isReadOnly() or (self._wheel_focus and not self.hasFocus()):
            ev.ignore()
            return
        dy = ev.angleDelta().y()
        if not dy:                                 # горизонтальная прокрутка — не наша
            ev.ignore()
            return
        self.stepBy(1 if dy > 0 else -1)
        ev.accept()

    def keyPressEvent(self, ev):                   # noqa: N802 (Qt)
        k = ev.key()
        steps = {Qt.Key_Up: 1, Qt.Key_Down: -1,
                 Qt.Key_PageUp: 10, Qt.Key_PageDown: -10}
        if k in steps and not self.isReadOnly():
            self.stepBy(steps[k])
            ev.accept()
            return
        if self._enter_only and k in (Qt.Key_Return, Qt.Key_Enter) and \
                self.text() != self.textFromValue(self._val):
            self.interpretText()                   # только применить набранное
            ev.accept()
            return
        if k == Qt.Key_Escape and self.text() != self.textFromValue(
                self._val):
            self._show()                           # Esc — откат набранного
            ev.accept()
            return
        super().keyPressEvent(ev)

    def changeEvent(self, ev):                     # noqa: N802 (Qt)
        super().changeEvent(ev)
        if ev.type() == ev.Type.FontChange:
            self._fit()


class DoubleEdit(IntEdit):
    """Дробное число (setDecimals) в обычной строке ввода."""

    valueChanged = Signal(float)
    _dec = 2                     # знаков после запятой (setDecimals)
    _comma = False               # запятая вместо точки (setDecimalComma)

    def _norm(self, v):
        return round(float(v), self._dec)

    def _fmt(self, v):
        s = "%.*f" % (self._dec, v)
        return s.replace(".", ",") if self._comma else s

    def _parse(self, s):
        return float(s)

    def setDecimals(self, n):                      # noqa: N802 (Qt)
        self._dec = max(0, int(n))
        # ★ 5.19.0: пределы и число — с новым числом знаков
        self._min, self._max = self._norm(self._min), self._norm(self._max)
        self._val = max(self._min, min(self._max, self._norm(self._val)))
        self._fit()
        self._show()

    def setDecimalComma(self, on):                 # noqa: N802 (Qt)
        """Показывать запятую вместо точки (ввод понимает обе)."""
        self._comma = bool(on)
        self._fit()
        self._show()

    def decimals(self):
        return self._dec


class _StepBtn(QPushButton):
    """Кнопка [−] / [+]: ширина своя, высота — как у поля рядом."""

    def __init__(self, text, edit, parent=None):
        super().__init__(text, parent)
        self._edit = edit

    def sizeHint(self):                            # noqa: N802 (Qt)
        return QSize(_BTN_W, self._edit.sizeHint().height())

    def minimumSizeHint(self):                     # noqa: N802 (Qt)
        return self.sizeHint()


class IntField(QWidget):
    """Поле-число [   10 px ][−][+]: IntEdit и отдельные кнопки.

    Сигналы valueChanged / editingFinished — свои (blockSignals на поле
    глушит и их). Остальные методы QSpinBox уходят полю (__getattr__)."""

    valueChanged = Signal(int)
    editingFinished = Signal()
    _edit_cls = IntEdit

    def __init__(self, parent=None, buttons="right"):
        """buttons: "right" — [поле][−][+] (как было), "around" — [−][поле][+]."""
        super().__init__(parent)
        self.edit = self._edit_cls(self)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(_GAP)
        self.btn_minus = self._btn("−", -1, "Меньше (колесо, ↓)")
        self.btn_plus = self._btn("+", 1, "Больше (колесо, ↑)")
        if buttons == "around":
            h.addWidget(self.btn_minus)
            h.addWidget(self.edit, 1)
            h.addWidget(self.btn_plus)
        else:
            h.addWidget(self.edit, 1)
            h.addWidget(self.btn_minus)
            h.addWidget(self.btn_plus)
        self.setFocusProxy(self.edit)
        self.edit.valueChanged.connect(self.valueChanged.emit)
        self.edit.valueChanged.connect(self._sync_buttons)
        self.edit.editingFinished.connect(self.editingFinished.emit)
        self._sync_buttons()

    def _btn(self, text, n, tip):
        b = _StepBtn(text, self.edit, self)
        b.setObjectName("intStep")
        b.setFixedWidth(_BTN_W)
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        b.setFocusPolicy(Qt.NoFocus)
        b.setAutoRepeat(True)                      # держать — листает
        b.setAutoRepeatDelay(400)
        b.setAutoRepeatInterval(60)
        b.setToolTip(tip)
        b.clicked.connect(lambda: self.edit.stepBy(n))
        return b

    def _sync_buttons(self, *_a):
        e = self.edit
        wrap = getattr(e, "_wrap", False)
        self.btn_minus.setEnabled(wrap or e.value() > e.minimum())
        self.btn_plus.setEnabled(wrap or e.value() < e.maximum())

    def __getattr__(self, name):
        # вызывается только для того, чего нет у самого QWidget
        edit = self.__dict__.get("edit")
        if edit is None:
            raise AttributeError(name)
        return getattr(edit, name)

    # то, что есть и у QWidget, — явно полю
    def setAlignment(self, a):                     # noqa: N802 (Qt)
        self.edit.setAlignment(a)

    def setToolTip(self, t):                       # noqa: N802 (Qt)
        super().setToolTip(t)
        self.edit.setToolTip(t)

    def setFocusPolicy(self, p):                   # noqa: N802 (Qt)
        super().setFocusPolicy(p)
        self.edit.setFocusPolicy(p)

    def setRange(self, lo, hi):                    # noqa: N802 (Qt)
        self.edit.setRange(lo, hi)
        self._sync_buttons()

    def setMinimum(self, lo):                      # noqa: N802 (Qt)
        self.edit.setMinimum(lo)
        self._sync_buttons()

    def setMaximum(self, hi):                      # noqa: N802 (Qt)
        self.edit.setMaximum(hi)
        self._sync_buttons()

    def setWrapping(self, on):                     # noqa: N802 (Qt)
        self.edit.setWrapping(on)
        self._sync_buttons()

    def setFixedWidth(self, w):                    # noqa: N802 (Qt)
        """Ширина целиком (поле + кнопки), но не уже самого длинного
        значения — цифры не обрезаются."""
        need = self.edit.need_width() + 2 * (_BTN_W + _GAP)
        super().setFixedWidth(max(int(w), need))

    def setMinimumWidth(self, w):                  # noqa: N802 (Qt)
        need = self.edit.need_width() + 2 * (_BTN_W + _GAP)
        super().setMinimumWidth(max(int(w), need))


class DoubleField(IntField):
    """Дробное поле [ 48.7200 ][−][+]."""

    valueChanged = Signal(float)
    _edit_cls = DoubleEdit


# ----------------------------------------------------------------- самопроверка
def selftest():
    """Пустой список — всё в порядке. Нужен QApplication (offscreen подходит)."""
    from PySide6.QtWidgets import QApplication
    errs = []

    def check(cond, text):
        if not cond:
            errs.append(text)

    if not isinstance(QApplication.instance(), QApplication):
        return errs                                 # без окон — нечего проверять
    got = []
    e = IntEdit()
    e.valueChanged.connect(got.append)
    e.setRange(0, 720)
    e.setSuffix(" мин")
    e.setValue(15)
    check(e.value() == 15 and e.text() == "15 мин", f"setValue / суффикс: {e.text()!r}")
    e.stepBy(2)
    check(e.value() == 17 and got[-1] == 17, "stepBy")
    e.setValue(9999)
    check(e.value() == 720, "предел")
    e.setText("абв")
    e.interpretText()
    check(e.value() == 720 and e.text() == "720 мин", "кривой ввод — откат")
    e.setText("30")
    check(e.value() == 30, "value() без Enter")
    n = len(got)
    e.blockSignals(True)
    e.setValue(40)
    e.blockSignals(False)
    check(len(got) == n and e.value() == 40, "blockSignals программы не снимается")
    e.setSpecialValueText("авто")
    e.setValue(0)
    check(e.text() == "авто", "особое значение")
    d = DoubleEdit()
    d.setRange(-10, 10)
    d.setDecimals(1)
    d.setDecimalComma(True)
    d.setValue(1.25)
    check(d.text() in ("1,2", "1,3"), f"запятая: {d.text()!r}")
    d.setText("\u22122,5")
    d.interpretText()
    check(d.value() == -2.5, f"«−» и запятая: {d.value()}")
    d.setDecimals(0)
    check(d.value() == -2.0 or d.value() == -3.0, "setDecimals переокругляет")
    wp = IntEdit()
    wp.setStyleSheet("QLineEdit { padding: 0 12px; }")
    wp.setRange(0, 2026)
    plain = IntEdit()
    plain.setRange(0, 2026)
    check(wp.need_width() > plain.need_width(), "ширина учитывает padding QSS")
    wp.deleteLater()
    plain.deleteLater()
    w0 = IntEdit()
    w0.setAutoWidth(False)
    w0.setMinimumWidth(10)
    w0.setRange(0, 10 ** 9)
    check(w0.minimumWidth() == 10, "setAutoWidth(False) — ширина программы")
    w0.deleteLater()
    f = IntField(buttons="around")
    lay = f.layout()
    check(lay.itemAt(0).widget() is f.btn_minus and lay.itemAt(1).widget() is f.edit, "кнопки по бокам")
    f.setRange(0, 5)
    f.setValue(0)
    check(not f.btn_minus.isEnabled() and f.btn_plus.isEnabled(), "кнопки на краю")
    for w in (e, d, f):
        w.deleteLater()
    return errs
