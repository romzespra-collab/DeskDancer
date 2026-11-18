"""int_field.py  v5.16.107

Журнал:
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
            self.blockSignals(True)                # editingFinished не нужен
            self.setText(t)
            self.blockSignals(False)

    def cleanText(self):                           # noqa: N802 (Qt)
        s = self.text().strip()
        if self._prefix and s.startswith(self._prefix.strip()):
            s = s[len(self._prefix.strip()):]
        if self._suffix and s.endswith(self._suffix.strip()):
            s = s[:-len(self._suffix.strip())]
        return s.strip().replace(" ", "").replace(",", ".")

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

    # у QSpinBox есть — здесь не нужны
    def setKeyboardTracking(self, _on):            # noqa: N802 (Qt)
        pass

    def setButtonSymbols(self, _s):                # noqa: N802 (Qt)
        pass

    def setAccelerated(self, _on):                 # noqa: N802 (Qt)
        pass

    def need_width(self):
        """Ширина под самое длинное значение (с запасом)."""
        fm = self.fontMetrics()
        texts = [self.textFromValue(self._min), self.textFromValue(self._max),
                 "%s%s%s" % (self._prefix, self._fmt(self._min), self._suffix)]
        return max(fm.horizontalAdvance(t) for t in texts) + _PAD

    def _fit(self):
        self.setMinimumWidth(self.need_width())

    # --- колесо и клавиши ---
    def wheelEvent(self, ev):                      # noqa: N802 (Qt)
        if not self.isEnabled() or self.isReadOnly():
            ev.ignore()
            return
        dy = ev.angleDelta().y()
        if dy:
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

    def _norm(self, v):
        return round(float(v), self._dec)

    def _fmt(self, v):
        return "%.*f" % (self._dec, v)

    def _parse(self, s):
        return float(s)

    def setDecimals(self, n):                      # noqa: N802 (Qt)
        self._dec = max(0, int(n))
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.edit = self._edit_cls(self)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(_GAP)
        h.addWidget(self.edit, 1)
        self.btn_minus = self._btn("−", -1, "Меньше (колесо, ↓)")
        self.btn_plus = self._btn("+", 1, "Больше (колесо, ↑)")
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
