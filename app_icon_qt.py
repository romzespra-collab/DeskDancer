"""app_icon_qt.py  v1.2.0 — окно «Значок программы» к общему модулю app_icon.

    import app_icon_qt
    app_icon_qt.IconDialog(icons, parent, on_apply=lambda qicon: ...).exec()

Вкладки:
- «Встроенные» — без интернета: ★ недавние, рисунки, база ~370 значков по разделам,
  поиск по-русски;
- «🌐 Поиск в интернете» — Iconify: слово, категория, набор, одноцветные / цветные;
- «🖼 Своя картинка» — файл (и значок из .exe / .dll / ярлыка), Ctrl+V, перетаскивание,
  значок сайта по адресу, сайт со значками в браузере.
Ниже — оформление: цвет (24 палитры и свой), форма (и «Без фона»), заливка, цвет рисунка,
размер рисунка, «Фон под значком». Справа — просмотр, «Как было», «По умолчанию»,
«Сохранить как…» (.ico / .png), «Ярлык на рабочий стол», путь к .ico.
«Применить» — окно и .ico сразу, ярлыки — в фоне. Цвета окна — из QSS приложения.

Журнал:
v1.2.0: вкладка «Встроенные» (недавние, рисунки, база по разделам, поиск по-русски);
      оформление: «Без фона», заливка, цвет рисунка, размер; 24 палитры; значок сайта;
      значок из .exe / .dll / ярлыка; фильтр одноцветные / цветные в поиске Iconify;
      «Как было», «Сохранить как…»; сетки — по ширине окна.
v1.1.0: вкладки; поиск значков в интернете (Iconify) по слову, категории и набору;
      вставка из буфера (Ctrl+V: картинка, SVG, ссылка, файл) и перетаскивание;
      «🌐 Найти на сайте…»; «Фон под значком».
v1.0.0: первая версия.
"""
import threading
import urllib.parse

from PySide6.QtCore import Qt, QFileInfo, QSize, QTimer, QUrl
from PySide6.QtGui import (QColor, QDesktopServices, QGuiApplication, QIcon, QKeySequence, QLinearGradient,
                           QPainter, QPalette, QPixmap, QShortcut)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog,
                               QFileDialog, QFileIconProvider, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QPushButton, QScrollArea, QTabWidget, QToolButton, QVBoxLayout,
                               QWidget)

import app_icon as ai

VERSION = "1.2.0"
SITE_SEARCH = "https://icon-icons.com/ru/search?q={q}"      # «🌐 Найти на сайте…»
PAGE = 96                                                  # значков за раз в поиске
CELL = 44                                                  # кнопка значка в сетке
STYLE_KEYS = ("colors", "shape", "fill", "ink", "scale", "text")


def _title(text):
    lab = QLabel(text)
    f = lab.font()
    f.setBold(True)
    lab.setFont(f)
    return lab


def _swatch(c1, c2, n=22):
    pm = QPixmap(n, n)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, n, n)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    p.setPen(QColor(127, 127, 127, 120))
    p.setBrush(g)
    p.drawRoundedRect(0.5, 0.5, n - 1, n - 1, 5, 5)
    p.end()
    return QIcon(pm)


class IconGrid(QScrollArea):
    """Сетка кнопок-значков: колонок — сколько влезает, прокрутка только вниз."""

    def __init__(self, on_pick, parent=None):
        super().__init__(parent)
        self.on_pick = on_pick
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.StyledPanel)
        self.box = QWidget()
        self.grid = QGridLayout(self.box)
        self.grid.setSpacing(4)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setWidget(self.box)
        self.grp = QButtonGroup(self)
        self.items = []                  # [(ключ, данные)]
        self.cols = 8

    def _calc_cols(self):
        """Сколько кнопок влезает в ряд: ширина без рамки, полосы прокрутки и полей сетки."""
        m = self.grid.contentsMargins()
        room = (self.width() - 2 * self.frameWidth() - self.verticalScrollBar().sizeHint().width()
                - m.left() - m.right())
        step = CELL + self.grid.spacing()
        return max(5, (room + self.grid.spacing()) // step)

    def clear(self):
        for b in self.grp.buttons():
            self.grp.removeButton(b)
            self.grid.removeWidget(b)
            b.hide()                          # сразу, не дожидаясь удаления
            b.deleteLater()
        self.items = []
        self.cols = self._calc_cols()
        self.verticalScrollBar().setValue(0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cols = self._calc_cols()
        if cols != self.cols:                 # ширина изменилась — переложить кнопки
            self.cols = cols
            for i in range(len(self.items)):
                b = self.grp.button(i)
                if b:
                    self.grid.removeWidget(b)
                    self.grid.addWidget(b, i // cols, i % cols)

    def add(self, key, data, icon, tip):
        b = QToolButton()
        b.setObjectName("aiGlyph")
        b.setCheckable(True)
        b.setIconSize(QSize(CELL - 10, CELL - 10))
        b.setFixedSize(CELL, CELL)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setIcon(icon)
        n = len(self.items)
        b.clicked.connect(lambda _=False, i=n: self.on_pick(*self.items[i]))
        self.grp.addButton(b, n)
        self.grid.addWidget(b, n // self.cols, n % self.cols)
        b.show()
        self.items.append((key, data))
        return b

    def set_icon(self, i, icon):
        b = self.grp.button(i)
        if b:
            b.setIcon(icon)

    def mark(self, key):
        """Отметить кнопку с ключом key (или снять отметку со всех)."""
        self.grp.setExclusive(False)
        for i, (k, _) in enumerate(self.items):
            b = self.grp.button(i)
            if b:
                b.setChecked(k == key)
        self.grp.setExclusive(True)


class IconDialog(QDialog):
    def __init__(self, icons, parent=None, on_apply=None):
        super().__init__(parent)
        self.icons, self.on_apply = icons, on_apply
        self.spec = ai.clean(icons.spec, icons.default)
        self.pack = ai.load_pack(icons.root)
        self._shortcut_job = None             # поток ярлыков: (thread, result) — закрытие ждёт
        self._jobs = []                       # фоновые задачи: (thread, result, done, token)
        self._token = 0                       # новый поиск — старые ответы не показывать
        self._cols = None                     # наборы Iconify {prefix: info}
        self._found, self._shown = [], 0      # найденные имена и сколько показано
        self._res_svgs = {}
        self.setWindowTitle("Значок программы")
        self.setAcceptDrops(True)
        # отметка выбранного — цветом выделения темы (palette(highlight)), без своих цветов
        self.setStyleSheet("QToolButton#aiGlyph:checked, QPushButton#aiSeg:checked {"
                           "border: 2px solid palette(highlight); background: rgba(127,127,127,70);}")
        root = QVBoxLayout(self)
        root.setSpacing(8)
        body = QHBoxLayout()
        body.setSpacing(16)
        root.addLayout(body, 1)

        left = QVBoxLayout()
        left.setSpacing(6)
        body.addLayout(left, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_builtin(), "Встроенные")
        self.tabs.addTab(self._tab_search(), "🌐 Поиск в интернете")
        self.tabs.addTab(self._tab_picture(), "🖼 Своя картинка")
        self.tabs.currentChanged.connect(self._tab_changed)
        left.addWidget(self.tabs, 1)
        left.addLayout(self._style_block())

        body.addLayout(self._right_block())

        # ---------- низ
        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setWordWrap(True)
        bottom.addWidget(self.status, 1)
        self.apply_btn = self._btn("✓ Применить", "Окно, панель задач, .ico и ярлыки", self._apply)
        self.apply_btn.setObjectName("primary")
        bottom.addWidget(self.apply_btn)
        bottom.addWidget(self._btn("Закрыть", "", self.close))
        root.addLayout(bottom)

        QShortcut(QKeySequence.Paste, self, activated=self._paste)
        self._poll = QTimer(self, interval=120, timeout=self._check_jobs)
        self._redraw = QTimer(self, singleShot=True, interval=120, timeout=self._redraw_builtin)
        self.resize(820, 720)
        QTimer.singleShot(0, self._fill_builtin)      # после раскладки — колонки по ширине
        self._refresh()

    # ================================================================== части окна
    def _btn(self, text, tip, fn):
        b = QPushButton(text)
        b.setToolTip(tip)
        b.setCursor(Qt.PointingHandCursor)
        b.setAutoDefault(False)
        b.clicked.connect(lambda _=False: fn())
        return b

    def _seg(self, row, options, fn, tip=""):
        """Ряд кнопок-переключателей: {значение: кнопка}."""
        grp = QButtonGroup(self)
        out = {}
        for val, name in options:
            b = QPushButton(name)
            b.setObjectName("aiSeg")
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setCursor(Qt.PointingHandCursor)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(lambda _=False, v=val: fn(v))
            grp.addButton(b)
            row.addWidget(b)
            out[val] = b
        return out

    def _tab_builtin(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.cat_in = QComboBox()
        self.cat_in.setToolTip("Раздел встроенных значков")
        self.cat_in.addItem("★ Недавние", "recent")
        self.cat_in.addItem(f"Рисунки  ({len(ai.GLYPHS)})", "glyphs")
        total = len(ai.GLYPHS)
        for i, c in enumerate(self.pack.get("categories", [])):
            self.cat_in.addItem(f"{c['name']}  ({len(c['icons'])})", i)
            total += len(c["icons"])
        self.cat_in.addItem(f"Все  ({total})", "all")
        self.cat_in.setCurrentIndex(1 if not self.icons.recent else 0)
        self.cat_in.currentIndexChanged.connect(lambda _: self._fill_builtin())
        row.addWidget(self.cat_in, 1)
        self.find_in = QLineEdit()
        self.find_in.setPlaceholderText("Найти: микрофон, ютуб, папка…")
        self.find_in.setToolTip("Поиск по встроенным значкам — по-русски или по-английски")
        self.find_in.setClearButtonEnabled(True)
        self.find_in.textChanged.connect(lambda _: self._fill_builtin())
        row.addWidget(self.find_in, 1)
        lay.addLayout(row)
        self.grid_in = IconGrid(self._pick_builtin)
        lay.addWidget(self.grid_in, 1)
        row = QHBoxLayout()
        self.info_in = QLabel("")
        row.addWidget(self.info_in, 1)
        row.addWidget(QLabel("Буква:"))
        self.letter = QLineEdit(self.spec.get("text", "A"))
        self.letter.setMaxLength(2)
        self.letter.setFixedWidth(60)
        self.letter.setAlignment(Qt.AlignCenter)
        self.letter.setToolTip("Одна-две буквы для рисунка «Буква»")
        self.letter.textEdited.connect(lambda t: self._set(kind="glyph", glyph="letter", text=t or "A"))
        row.addWidget(self.letter)
        lay.addLayout(row)
        if not self.pack.get("categories"):
            self.info_in.setText(f"Нет файла {ai.PACK_NAME} — только рисунки.")
        return w

    def _tab_search(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.q_edit = QLineEdit()
        self.q_edit.setPlaceholderText("Слово: youtube, микрофон, camera, fan…")
        self.q_edit.setToolTip("Поиск идёт по-английски; русские слова переводятся сами (словарь и названия базы)")
        self.q_edit.setClearButtonEnabled(True)
        self.q_edit.returnPressed.connect(self._search)
        row.addWidget(self.q_edit, 1)
        row.addWidget(self._btn("🔎 Найти", "Искать значки (Enter)", self._search))
        lay.addLayout(row)
        row = QHBoxLayout()
        self.cat_cb = QComboBox()
        self.cat_cb.setToolTip("Направление: интерфейс, логотипы, эмодзи, флаги…")
        self.cat_cb.addItem("Все категории", None)
        self.cat_cb.currentIndexChanged.connect(self._cat_changed)
        row.addWidget(self.cat_cb, 2)
        self.set_cb = QComboBox()
        self.set_cb.setToolTip("Набор значков; без слова — показать весь набор")
        self.set_cb.addItem("Все наборы", None)
        self.set_cb.activated.connect(lambda _: self._search())
        row.addWidget(self.set_cb, 2)
        self.col_cb = QComboBox()
        self.col_cb.setToolTip("Одноцветные красятся цветом палитры; цветные — как есть")
        for name, val in (("Любые", None), ("Одноцветные", False), ("Цветные", True)):
            self.col_cb.addItem(name, val)
        self.col_cb.activated.connect(lambda _: self._search() if self._found or self.q_edit.text() else None)
        row.addWidget(self.col_cb, 1)
        lay.addLayout(row)
        self.grid_net = IconGrid(lambda key, svg: self._pick_found(key))
        self.grid_net.setMinimumHeight(200)
        lay.addWidget(self.grid_net, 1)
        row = QHBoxLayout()
        self.res_lbl = QLabel("Значки из открытых наборов (Iconify). Нужен интернет.")
        self.res_lbl.setWordWrap(True)
        row.addWidget(self.res_lbl, 1)
        self.more_btn = self._btn("Ещё ▸", "Показать следующие", self._more)
        self.more_btn.setVisible(False)
        row.addWidget(self.more_btn)
        lay.addLayout(row)
        return w

    def _tab_picture(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self._btn("🖼 Выбрать файл…", "Картинка (PNG, JPG, ICO, BMP, SVG) или значок программы "
                                "(.exe, .dll, ярлык)", self._own_image))
        lay.addWidget(self._btn("📋 Вставить из буфера (Ctrl+V)", "Картинка, SVG, ссылка на картинку или файл",
                                self._paste))
        row = QHBoxLayout()
        self.site_edit = QLineEdit()
        self.site_edit.setPlaceholderText("Адрес сайта: youtube.com, github.com…")
        self.site_edit.setClearButtonEnabled(True)
        self.site_edit.returnPressed.connect(self._site_icon)
        row.addWidget(self.site_edit, 1)
        row.addWidget(self._btn("🌐 Значок сайта", "Взять значок сайта — самый крупный (SVG, apple-touch-icon, "
                                "manifest, favicon)", self._site_icon))
        lay.addLayout(row)
        lay.addWidget(self._btn("🔎 Найти на icon-icons.com…", "Открыть поиск значков в браузере", self._site))
        hint = QLabel("На сайте со значками нажмите «копировать» (⧉) у значка и потом Ctrl+V здесь — "
                      "или перетащите картинку, файл или ссылку прямо в это окно.\n\n"
                      "«Фон под значком» ниже — подложить фон цветом палитры (для значков без своего фона).")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        lay.addStretch(1)
        return w

    def _style_block(self):
        g = QGridLayout()
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(5)
        g.addWidget(_title("Цвет"), 0, 0, Qt.AlignTop)
        pal = QGridLayout()
        pal.setSpacing(3)
        for i, (name, c1, c2) in enumerate(ai.PALETTES):
            b = QToolButton()
            b.setIcon(_swatch(c1, c2))
            b.setIconSize(QSize(20, 20))
            b.setFixedSize(28, 28)
            b.setToolTip(name)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, a=c1, z=c2: self._set(colors=[a, z]))
            pal.addWidget(b, i // 12, i % 12)
        own = self._btn("🎨 Свой…", "Свой цвет фона — второй (для градиента) рассчитается темнее", self._own_color)
        pal.addWidget(own, 0, 12, 2, 1)
        pal.setColumnStretch(13, 1)
        g.addLayout(pal, 0, 1)

        g.addWidget(_title("Форма"), 1, 0)
        row = QHBoxLayout()
        self.shape_btns = self._seg(row, ai.SHAPES, lambda v: self._set(shape=v))
        self.shape_btns["none"].setToolTip("Без фона: рисунок сам залит цветом палитры")
        row.addStretch(1)
        g.addLayout(row, 1, 1)

        g.addWidget(_title("Заливка"), 2, 0)
        row = QHBoxLayout()
        self.fill_btns = self._seg(row, ai.FILLS, lambda v: self._set(fill=v))
        row.addSpacing(12)
        row.addWidget(_title("Рисунок"))
        self.ink_btns = self._seg(row, ai.INKS, lambda v: self._set(ink=v),
                                  "Цвет рисунка на фоне (авто — белый или тёмный по фону)")
        self.ink_own = QPushButton("Свой…")
        self.ink_own.setObjectName("aiSeg")
        self.ink_own.setCheckable(True)
        self.ink_own.setAutoDefault(False)
        self.ink_own.setCursor(Qt.PointingHandCursor)
        self.ink_own.setToolTip("Свой цвет рисунка")
        self.ink_own.clicked.connect(self._own_ink)
        row.addWidget(self.ink_own)
        row.addStretch(1)
        g.addLayout(row, 2, 1)

        g.addWidget(_title("Размер"), 3, 0)
        row = QHBoxLayout()
        minus = self._btn("−", "Рисунок меньше", lambda: self._set(scale=self.spec["scale"] - 10))
        plus = self._btn("+", "Рисунок больше", lambda: self._set(scale=self.spec["scale"] + 10))
        for b in (minus, plus):
            b.setFixedWidth(34)
        self.scale_lbl = QLabel("100 %")
        self.scale_lbl.setAlignment(Qt.AlignCenter)
        self.scale_lbl.setMinimumWidth(self.scale_lbl.fontMetrics().horizontalAdvance("130 %") + 12)
        self.scale_lbl.setToolTip("Размер рисунка внутри значка, 60…130 %")
        row.addWidget(minus)
        row.addWidget(self.scale_lbl)
        row.addWidget(plus)
        row.addSpacing(16)
        self.bg_chk = QCheckBox("Фон под значком")
        self.bg_chk.setToolTip("Для своей картинки и значков из базы и интернета: фон цветом палитры,\n"
                               "одноцветный значок — цветом рисунка")
        self.bg_chk.clicked.connect(lambda on: self._set(bg=on))
        row.addWidget(self.bg_chk)
        row.addStretch(1)
        g.addLayout(row, 3, 1)
        g.setColumnStretch(1, 1)
        return g

    def _right_block(self):
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(_title("Просмотр"))
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)
        bl = QVBoxLayout(box)
        self.big = QLabel()
        self.big.setFixedSize(128, 128)
        bl.addWidget(self.big, 0, Qt.AlignHCenter)
        small = QHBoxLayout()
        self.smalls = []
        for n in (48, 32, 24, 16):
            lab = QLabel()
            lab.setFixedSize(n, n)
            small.addWidget(lab, 0, Qt.AlignBottom)
            self.smalls.append((n, lab))
        bl.addLayout(small)
        right.addWidget(box)
        self.src_lbl = QLabel("")
        self.src_lbl.setWordWrap(True)
        self.src_lbl.setMaximumWidth(230)
        self.src_lbl.setOpenExternalLinks(True)
        self.src_lbl.setTextInteractionFlags(Qt.TextBrowserInteraction)
        lp = self.src_lbl.palette()                      # ссылка — цветом выделения темы (видна и на тёмной)
        lp.setColor(QPalette.Link, lp.color(QPalette.Highlight))
        self.src_lbl.setPalette(lp)
        right.addWidget(self.src_lbl)
        right.addWidget(self._btn("↶ Как было", "Вернуть значок, который сейчас у программы",
                                  lambda: self._set(replace=True, **self.icons.spec)))
        right.addWidget(self._btn("↺ По умолчанию", "Значок, с которым программа пришла",
                                  lambda: self._set(replace=True, **self.icons.default)))
        right.addWidget(self._btn("💾 Сохранить как…", "Записать этот значок в файл .ico или .png (256×256)",
                                  self._save_as))
        self.desk_btn = self._btn("🔗 Ярлык на рабочий стол",
                                  "Создать ярлык с этим значком (если его там нет) и обновить остальные",
                                  lambda: self._apply(create_desktop=True))
        right.addWidget(self.desk_btn)
        path = QLabel(f"Файл значка:\n{self.icons.ico_path}")
        path.setWordWrap(True)
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path.setToolTip("Для кнопки Total Commander: «Файл значка» → этот файл.\n"
                        "Путь не меняется — новый значок подхватится сам.")
        path.setMaximumWidth(230)
        right.addWidget(path)
        right.addStretch(1)
        return right

    # ================================================================== выбор
    def _set(self, replace=False, **kw):
        if replace:
            new = dict(kw)
        else:
            new = {**self.spec, **kw}
            if kw.get("kind"):                            # новый значок — прежняя картинка не нужна
                for k in ("png", "svg", "src", "lic"):
                    if k not in kw:
                        new.pop(k, None)
        old_style = tuple(str(self.spec.get(k)) for k in STYLE_KEYS + ("bg",))
        self.spec = ai.clean(new, self.icons.default)
        self._refresh()
        if tuple(str(self.spec.get(k)) for k in STYLE_KEYS + ("bg",)) != old_style:
            self._redraw.start()                          # сетка встроенных — в новом цвете

    def _style(self):
        return {k: self.spec[k] for k in STYLE_KEYS}

    def _own_color(self):
        c = QColorDialog.getColor(QColor(self.spec["colors"][0]), self, "Цвет значка")
        if c.isValid():
            self._set(colors=[c.lighter(115).name(), c.darker(150).name()])

    def _own_ink(self):
        c = QColorDialog.getColor(QColor(self.spec["ink"] or "#ffffff"), self, "Цвет рисунка")
        if c.isValid():
            self._set(ink=c.name())
        else:
            self._refresh()                               # вернуть отметку кнопок

    def _own_image(self):
        fn, _ = QFileDialog.getOpenFileName(
            self, "Своя картинка для значка", "",
            "Картинки и программы (*.png *.jpg *.jpeg *.ico *.bmp *.svg *.exe *.dll *.lnk);;"
            "Картинки (*.png *.jpg *.jpeg *.ico *.bmp *.svg);;Программы (*.exe *.dll *.lnk);;Все файлы (*.*)")
        if not fn:
            return
        if fn.lower().endswith((".exe", ".dll", ".lnk")):
            self._picture(lambda: self._exe_icon(fn), fn)
        else:
            self._picture(lambda: ai.picture_from_file(fn), fn)

    @staticmethod
    def _exe_icon(fn):
        """Значок программы (.exe / .dll / ярлык) — самый крупный, что отдаёт система."""
        ic = QFileIconProvider().icon(QFileInfo(fn))
        sizes = sorted(ic.availableSizes(), key=lambda s: s.width() * s.height())
        side = sizes[-1].width() if sizes else 256
        img = ic.pixmap(max(side, 32)).toImage()
        if img.isNull():
            raise ValueError("У этого файла значка нет.")
        return {"kind": "image", "png": ai.image_to_png(img), "bg": False}

    def _picture(self, make, src=""):
        try:
            part = make()
        except Exception as e:
            self.status.setText(f"✗ {e}")
            return
        self._set(**{**part, "src": (part.get("src") or src or "")[:300], "lic": ""})
        self.status.setText("✓ Значок взят (SVG)." if part.get("kind") == "svg" else
                            "✓ Картинка взята: квадрат по центру; форма — обрезка углов.")

    def _site(self):
        q, ok = QInputDialog.getText(self, "Найти на сайте", "Что искать (например: ютуб, микрофон):",
                                     text=self.q_edit.text() or self.find_in.text())
        if ok and q.strip():
            QDesktopServices.openUrl(QUrl(SITE_SEARCH.format(q=urllib.parse.quote(q.strip()))))
            self.status.setText("Скопируйте значок на сайте (⧉) и нажмите здесь Ctrl+V.")

    def _site_icon(self):
        text = self.site_edit.text().strip()
        if not text:
            self.status.setText("Введите адрес сайта, например youtube.com")
            return
        self.status.setText(f"Ищу значок сайта {text}…")

        def done(res, err):
            if err:
                self.status.setText(f"✗ {err}")
            else:
                self._picture(lambda: res)
        self._run(lambda: ai.site_icon(text), done, keep_token=True)

    def _save_as(self):
        fn, flt = QFileDialog.getSaveFileName(self, "Сохранить значок", f"{self.icons.name}.ico",
                                              "Значок (*.ico);;Картинка PNG 256×256 (*.png)")
        if not fn:
            return
        try:
            if fn.lower().endswith(".png") or ("png" in flt.lower() and not fn.lower().endswith(".ico")):
                if not fn.lower().endswith(".png"):
                    fn += ".png"
                ai._write(fn, ai._png_bytes(ai.render(self.spec, 256).toImage()))
            else:
                if not fn.lower().endswith(".ico"):
                    fn += ".ico"
                ai._write(fn, ai.ico_bytes(self.spec))
            self.status.setText(f"✓ Сохранено: {fn}")
        except Exception as e:
            self.status.setText(f"✗ Не сохранилось: {e}")

    # ---------- буфер и перетаскивание
    def _paste(self):
        fw = QApplication.focusWidget()
        md = QGuiApplication.clipboard().mimeData()
        if isinstance(fw, QLineEdit) and not (md and md.hasImage()):
            text = QGuiApplication.clipboard().text().strip()
            if not (text.startswith(("http://", "https://", "<svg", "<?xml")) and len(text) > 20):
                fw.paste()
                return
        if not self._take_mime(md):
            self.status.setText("В буфере нет картинки. На сайте нажмите «копировать» (⧉) у значка.")

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasImage() or md.hasUrls() or md.hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        if self._take_mime(e.mimeData()):
            e.acceptProposedAction()
        else:
            self.status.setText("Это не картинка.")

    def _take_mime(self, md):
        """Картинка из буфера / перетаскивания: изображение, SVG, файл, ссылка. True — взято."""
        if md is None:
            return False
        if md.hasImage():
            img = md.imageData()
            if img is not None and not img.isNull():
                self._picture(lambda: {"kind": "image", "png": ai.image_to_png(img), "bg": False})
                return True
        for u in md.urls() if md.hasUrls() else []:
            if u.isLocalFile():
                p = u.toLocalFile()
                if p.lower().endswith((".exe", ".dll", ".lnk")):
                    self._picture(lambda: self._exe_icon(p), p)
                else:
                    self._picture(lambda: ai.picture_from_file(p), p)
                return True
            if u.scheme() in ("http", "https"):
                self._download(u.toString())
                return True
        text = md.text().strip() if md.hasText() else ""
        if "<svg" in text[:400]:
            self._picture(lambda: ai.picture_spec(text.encode("utf-8")))
            return True
        if text.startswith(("http://", "https://")) and "\n" not in text:
            self._download(text)
            return True
        return False

    def _download(self, url):
        self.status.setText("Скачиваю картинку…")

        def done(res, err):
            if err:
                self.status.setText(f"✗ Не скачалась: {err}")
            else:
                self._picture(lambda: ai.picture_spec(res, urllib.parse.urlparse(url).path), url)
        self._run(lambda: ai.fetch_url(url), done, keep_token=True)

    # ================================================================== встроенные
    def _builtin_items(self):
        """[(ключ, данные, подсказка)]; данные: ("glyph", key) | ("pack", id, svg) | ("recent", spec)."""
        q = self.find_in.text().strip()
        cats = self.pack.get("categories", [])
        if q:
            ql = q.lower().replace("ё", "е")
            out = [(f"glyph:{k}", ("glyph", k), name) for k, name, _ in ai.GLYPHS
                   if ql in name.lower().replace("ё", "е") or ql in k]
            out += [(i, ("pack", i, svg), f"{ru}\n{i}") for i, ru, svg in ai.pack_find(q, self.pack)]
            return out
        cat = self.cat_in.currentData()
        if cat == "recent":
            return [(f"recent:{n}", ("recent", s), "Недавний") for n, s in enumerate(self.icons.recent)]
        out = []
        if cat in ("glyphs", "all"):
            out += [(f"glyph:{k}", ("glyph", k), name) for k, name, _ in ai.GLYPHS]
        for i, c in enumerate(cats):
            if cat == i or cat == "all":
                out += [(icon_id, ("pack", icon_id, svg), f"{ru}\n{icon_id}") for icon_id, ru, _, svg in c["icons"]]
        return out

    def _item_spec(self, data):
        if data[0] == "glyph":
            return {**self._style(), "kind": "glyph", "glyph": data[1]}
        if data[0] == "pack":
            return {**self._style(), "kind": "svg", "svg": data[2], "bg": True, "src": data[1]}
        return data[1]

    def _fill_builtin(self):
        self.grid_in.clear()
        items = self._builtin_items()
        for key, data, tip in items:
            self.grid_in.add(key, data, QIcon(ai.render(self._item_spec(data), 68)), tip)
        self._mark_builtin()
        if self.find_in.text().strip():
            self.info_in.setText(f"Найдено: {len(items)}" if items else
                                 "Не нашлось — попробуйте «🌐 Поиск в интернете».")
        elif self.cat_in.currentData() == "recent" and not items:
            self.info_in.setText("Недавних пока нет — они появятся после «Применить».")
        elif self.pack.get("categories"):
            self.info_in.setText(f"Значков: {len(items)}")

    def _redraw_builtin(self):
        for i, (key, data) in enumerate(self.grid_in.items):
            if data[0] != "recent":
                self.grid_in.set_icon(i, QIcon(ai.render(self._item_spec(data), 68)))

    def _mark_builtin(self):
        s = self.spec
        key = (f"glyph:{s['glyph']}" if s["kind"] == "glyph" else s.get("src", "")) or None
        self.grid_in.mark(key)

    def _pick_builtin(self, key, data):
        if data[0] == "recent":
            self._set(replace=True, **data[1])
        elif data[0] == "glyph":
            self._set(kind="glyph", glyph=data[1])
        else:
            keep_bg = self.spec.get("bg", True) if self.spec["kind"] == "svg" else True
            self._set(kind="svg", svg=data[2], bg=keep_bg, src=data[1], lic=ai.pack_license(data[1], self.pack))

    # ================================================================== поиск (Iconify)
    def _tab_changed(self, i):
        if self.tabs.tabText(i).startswith("🌐") and self._cols is None:
            self._cols = {}
            self.res_lbl.setText("Загружаю список наборов…")

            def done(res, err):
                if err:
                    self._cols = None
                    self.res_lbl.setText(f"✗ {err}")
                    return
                self._cols = {k: v for k, v in res.items() if not v.get("hidden")}
                self._fill_categories()
                self.res_lbl.setText(f"Наборов: {len(self._cols)}. Введите слово или выберите набор.")
                self.q_edit.setFocus()
            self._run(lambda: ai.iconify_collections(self.icons.cache_dir), done, keep_token=True)

    def _fill_categories(self):
        cnt = {}
        for v in self._cols.values():
            c = v.get("category") or "Другое"
            cnt[c] = cnt.get(c, 0) + 1
        order = sorted(cnt, key=lambda c: (c == "Archive / Unmaintained", -cnt[c]))
        self.cat_cb.blockSignals(True)
        self.cat_cb.clear()
        self.cat_cb.addItem("Все категории", None)
        for c in order:
            self.cat_cb.addItem(f"{ai.CATEGORY_RU.get(c, c)}  ({cnt[c]})", c)
        self.cat_cb.blockSignals(False)
        self._cat_changed()

    def _cat_changed(self, *_):
        cat = self.cat_cb.currentData()
        self.set_cb.clear()
        self.set_cb.addItem("Все наборы", None)
        for pre, v in sorted((self._cols or {}).items(), key=lambda kv: kv[1].get("name", kv[0]).lower()):
            if cat is None or (v.get("category") or "Другое") == cat:
                self.set_cb.addItem(f"{v.get('name', pre)}  ({v.get('total', '?')})", pre)

    def _search(self):
        q = self.q_edit.text().strip()
        cat, pre = self.cat_cb.currentData(), self.set_cb.currentData()
        if not q and not pre:
            self.res_lbl.setText("Введите слово или выберите набор.")
            return
        self._token += 1
        self._clear_results()
        self.res_lbl.setText("Ищу…")
        cat_api = None if cat in (None, "Другое") else cat
        if q:
            fn = (lambda: ai.iconify_search(q, limit=999, category=cat_api, prefixes=[pre] if pre else None))
        else:
            fn = (lambda: ai.iconify_set_icons(pre))
        want = self.col_cb.currentData()

        def done(res, err):
            if err:
                self.res_lbl.setText(f"✗ {err}")
                return
            if want is not None and self._cols:           # одноцветные / цветные — по свойству набора
                res = [n for n in res if bool(self._cols.get(n.split(":", 1)[0], {}).get("palette")) == want]
            self._found, self._shown = res, 0
            if not res:
                hint = " Поиск — по-английски." if any("а" <= ch <= "я" for ch in q.lower()) else ""
                self.res_lbl.setText("Ничего не нашлось." + hint)
                return
            self._more()
        self._run(fn, done)

    def _more(self):
        part = self._found[self._shown:self._shown + PAGE]
        if not part:
            return
        self.more_btn.setEnabled(False)
        self.res_lbl.setText("Загружаю значки…")

        def done(res, err):
            self.more_btn.setEnabled(True)
            if err:
                self.res_lbl.setText(f"✗ {err}")
                return
            self._add_results(part, res)
        self._run(lambda: ai.iconify_svgs(part), done)

    def _clear_results(self):
        self.grid_net.clear()
        self._res_svgs = {}
        self._found, self._shown = [], 0
        self.more_btn.setVisible(False)

    def _add_results(self, names, svgs):
        ink = self.palette().color(QPalette.WindowText).name()
        for full in names:
            svg = svgs.get(full)
            if not svg:
                continue
            pm = QPixmap.fromImage(ai.svg_image(svg, 60, ink if ai.svg_is_mono(svg) else None))
            self.grid_net.add(full, svg, QIcon(pm), full)
            self._res_svgs[full] = svg
        self._shown += len(names)
        left = len(self._found) - self._shown
        self.more_btn.setVisible(left > 0)
        self.res_lbl.setText(f"Показано {len(self.grid_net.items)} из {len(self._found)}. Щёлкните значок."
                             + (" «Ещё ▸» — следующие." if left > 0 else ""))
        self.grid_net.mark(self.spec.get("src"))

    def _pick_found(self, full):
        svg = self._res_svgs.get(full)
        if not svg:
            return
        pre = full.split(":", 1)[0]
        info = (self._cols or {}).get(pre, {})
        lic = info.get("license") or {}
        lic_txt = lic.get("title") or lic.get("spdx") or "?"
        if lic.get("url"):
            lic_txt = f'<a href="{lic["url"]}">{lic_txt}</a>'
        self._set(kind="svg", svg=svg, bg=ai.svg_is_mono(svg), src=full,
                  lic=f"{info.get('name', pre)} · {lic_txt}")

    # ---------- фоновые задачи (сеть): результат — в окне через таймер
    def _run(self, fn, done, keep_token=False):
        res = {}
        token = None if keep_token else self._token

        def work():
            try:
                res["v"] = fn()
            except Exception as e:
                res["e"] = str(e) or type(e).__name__
        th = threading.Thread(target=work, daemon=True)
        self._jobs.append((th, res, done, token))
        th.start()
        self._poll.start()

    def _check_jobs(self):
        for job in list(self._jobs):
            th, res, done, token = job
            if th.is_alive():
                continue
            self._jobs.remove(job)
            if token is not None and token != self._token:
                continue                      # ответ на старый поиск
            done(res.get("v"), res.get("e"))
        if self._shortcut_job and not self._shortcut_job[0].is_alive():
            self._shortcut_done()
        if not self._jobs and not self._shortcut_job:
            self._poll.stop()

    # ================================================================== вид
    def _refresh(self):
        s = self.spec
        self._mark_builtin()
        self.grid_net.mark(s.get("src") if s["kind"] == "svg" else None)
        for key, b in self.shape_btns.items():
            b.setChecked(s["shape"] == key)
        for key, b in self.fill_btns.items():
            b.setChecked(s["fill"] == key)
        for key, b in self.ink_btns.items():
            b.setChecked(s["ink"] == key)
        self.ink_own.setChecked(bool(s["ink"]) and s["ink"] not in self.ink_btns)
        self.scale_lbl.setText(f"{s['scale']} %")
        pic = s["kind"] in ("image", "svg")
        self.bg_chk.setEnabled(pic and s["shape"] != "none")
        self.bg_chk.setChecked(bool(s.get("bg")) and pic)
        if self.letter.text() != s.get("text") and not self.letter.hasFocus():
            self.letter.setText(s.get("text", "A"))
        src = s.get("src", "") if pic else ""
        lic = s.get("lic", "") if pic else ""
        if not lic and src and ":" in src and not src.startswith(("/", "http")):
            lic = ai.pack_license(src, self.pack) if src.split(":", 1)[0] in self.pack.get("sets", {}) else ""
        name = src if src and ":" in src and not src.startswith(("/", "http")) and "\\" not in src else ""
        self.src_lbl.setText((f"<b>{name}</b><br>" if name else "") + (f"Набор: {lic}" if lic else ""))
        dpr = self.devicePixelRatioF()
        big = ai.render(s, int(128 * dpr))
        big.setDevicePixelRatio(dpr)
        self.big.setPixmap(big)
        for n, lab in self.smalls:
            lab.setPixmap(ai.render(s, n))

    # ================================================================== применить
    def _busy(self, on):
        for b in (self.apply_btn, self.desk_btn):
            b.setEnabled(not on)

    def _apply(self, create_desktop=False):
        if self._shortcut_job:
            return
        try:
            qicon = self.icons.apply(self.spec)
        except Exception as e:
            self.status.setText(f"✗ Не сохранилось: {e}")
            return
        if self.on_apply:
            self.on_apply(qicon)
        if self.cat_in.currentData() == "recent":
            self._fill_builtin()
        res = {}

        def work():
            try:
                res["done"] = self.icons.fix_shortcuts(create_desktop)
            except Exception as e:
                res["error"] = str(e)
        th = threading.Thread(target=work, daemon=True)
        self._shortcut_job = (th, res)
        self._busy(True)
        self.status.setText("✓ Окно и .ico обновлены. Меняю значок ярлыкам…")
        th.start()
        self._poll.start()

    def _shortcut_done(self):
        th, res = self._shortcut_job
        self._shortcut_job = None
        self._busy(False)
        if "error" in res:
            self.status.setText(f"✓ Окно и .ico обновлены. ✗ Ярлыки: {res['error']}")
            return
        done = res.get("done", [])
        ok = [p for k, p, _ in done if k == "ok"]
        new = [p for k, p, _ in done if k == "new"]
        bad = [(p, e) for k, p, e in done if k == "err"]
        parts = ["✓ Значок применён."]
        if ok:
            parts.append(f"Ярлыков обновлено: {len(ok)}.")
        if new:
            parts.append("Создан ярлык на рабочем столе.")
        if not ok and not new and not bad:
            parts.append("Ярлыков на программу не нашлось — «🔗 Ярлык на рабочий стол».")
        if bad:
            parts.append(f"✗ Не вышло: {len(bad)}.")
        self.status.setText(" ".join(parts))
        self.status.setToolTip("\n".join(ok + new + [f"✗ {p}: {e}" for p, e in bad]))

    def closeEvent(self, e):
        if self._shortcut_job:               # ярлыки ещё меняются — дождаться
            self.status.setText("Подождите — меняю значок ярлыкам…")
            e.ignore()
            return
        self._token += 1                     # сетевые ответы после закрытия не нужны
        super().closeEvent(e)

    def reject(self):                        # Esc — как «Закрыть», с тем же ожиданием
        if self._shortcut_job:
            self.status.setText("Подождите — меняю значок ярлыкам…")
            return
        self._token += 1
        super().reject()


def apply_everywhere(qicon):
    """Новый значок: приложению и всем открытым окнам (полоса своей рамки — сама)."""
    QApplication.setWindowIcon(qicon)
    for w in QApplication.topLevelWidgets():
        if w.isWindow():
            w.setWindowIcon(qicon)
    QGuiApplication.processEvents()
