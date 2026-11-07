"""gh_update_qt — вкладка «Обновление с GitHub» для настроек (PySide6).

ОБЩИЙ для всех наших приложений, работает поверх gh_update:
  UpdateBox  — токен (с глазиком и «?» — инструкция), ветка, «Проверять
               автоматически», «Проверить сейчас», «Обновить до X», полоса
               скачивания, «Перезапустить»;
  UpdateAnim — анимация: GitHub → ПК, проверка, «есть новая версия»,
               бегущие пакеты при скачивании (МБ, %, скорость), установка;
  UpdatePage — всё вместе + «Что нового» (из CHANGELOG в репозитории):
               готовая вкладка для настроек.

Подключение в приложении:
    page = UpdatePage(target, cfg_get, cfg_set, on_quit=self.close,
                      log=log.info)
  target  — gh_update.UpdateTarget (owner/repo/name/current/app_dir/main_file,
            changelog — путь к CHANGELOG в репозитории)
  cfg_get — () -> {"token": str, "auto": bool, "branch": str, "every_h": int}
  cfg_set — (dict) -> None, сохранить те же ключи в настройки программы
  on_quit — закрыть программу ПОЛНОСТЬЮ (новая копия уже запущена)
  page.box.available(str) — нашлась новая версия (пометить вкладку и т.п.)

★ gh_update 1.4.2: Python 3.12+, строки на f-строках.
★ gh_update 1.4.0: только Python — обновления собранного exe больше нет
(нет сборок в GitHub Releases, «GitHub собирает exe», подмены exe помощником).

★ gh_update 1.3.3: restart_ask=False — после установки перезапуск сам через
3 с, без вопроса (Smart_BMS); глазик токена — theme.add_password_eye
программы, если он есть; после установки исходников target.current = новая
версия (авто-проверка не предложит ту же версию ещё раз).

★ gh_update 1.3.2: can_install=() -> "" | причина — запрет «Обновить», пока программа
работает (UpdatePage / UpdateBox); box.busy() — идёт установка, окно не закрывать.

★ gh_update 1.3.1: UpdateBox.apply_theme — кнопка «Проверять автоматически»
перекрашивается при смене схемы; «готово» — таймер анимации останавливается.

Цвета. Если в проекте нет модуля theme (ACCENT/TEXT/TEXT_DIM/BG_PANEL/
BORDER), задать свои: gh_update_qt.set_colors(lambda: {"accent": …,
"text": …, "dim": …, "panel": …, "border": …}) — функция зовётся при
каждой перерисовке, так что смена темы подхватывается сама.
"""
import math
import os
import sys
import threading
import time

from PySide6.QtCore import QObject, QPointF, QRectF, QTimer, QUrl, Signal, Qt
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QPainter,
                           QPainterPath, QPen)
from PySide6.QtWidgets import (QComboBox, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

try:                                    # значок GitHub в облаке рисуется из SVG-контура
    from PySide6.QtCore import QByteArray
    from PySide6.QtSvg import QSvgRenderer
except ImportError:                     # нет QtSvg — облако с одной надписью, как раньше
    QSvgRenderer = None

try:                                    # пакет app/ …
    from . import gh_update
    from .gh_update_help import TOKENS_URL
except ImportError:                     # … или файлы рядом с главным .pyw
    import gh_update
    from gh_update_help import TOKENS_URL

AUTO_FIRST_MS = 30_000                 # первая автопроверка — через 30 с
AUTO_EVERY_H = 12                      # дальше — раз в 12 часов (по умолчанию)
# выбор «Каждые»: (часов, подпись)
EVERY_CHOICES = ((1, "1 ч"), (3, "3 ч"), (6, "6 ч"), (12, "12 ч"),
                 (24, "24 ч"), (72, "3 дня"), (168, "неделю"))


class _Sig(QObject):
    checked = Signal(object, bool, str, str)   # Release|None, новее, ошибка, что нового
    progress = Signal(int, int)                # скачано, всего (байт)
    done = Signal(bool, str)                   # успех, текст


def _mb(n):
    return f"{n / 1048576.0:.1f}"


_COLORS = None                         # () -> dict, см. set_colors


def set_colors(fn):
    """Свои цвета темы: fn() -> {"accent","text","dim","panel","border"}."""
    global _COLORS
    _COLORS = fn


class _Pal:
    def __init__(self, d):
        self.ACCENT = d.get("accent")
        self.TEXT = d.get("text")
        self.TEXT_DIM = d.get("dim")
        self.BG_PANEL = d.get("panel")
        self.BORDER = d.get("border")


def _theme():
    """Цвета текущей темы программы: set_colors() или модуль theme."""
    if _COLORS is not None:
        try:
            return _Pal(dict(_COLORS() or {}))
        except Exception:                              # noqa: BLE001
            return None
    try:
        from . import theme as th
        return th
    except Exception:                                  # noqa: BLE001
        return None


def _add_eye(ed):
    """Глазик «показать/скрыть» в поле токена."""
    try:                                               # ★ 1.3.3: свой глазик программы
        from . import theme
        theme.add_password_eye(ed)
        return
    except Exception:                                  # noqa: BLE001
        pass
    from PySide6.QtWidgets import QToolButton
    b = QToolButton(ed)
    b.setText("👁")
    b.setCursor(Qt.PointingHandCursor)
    b.setCheckable(True)
    b.setToolTip("Показать / скрыть токен")
    b.setStyleSheet("QToolButton{border:none;background:transparent;padding:0 4px;}")
    b.toggled.connect(lambda on: ed.setEchoMode(
        QLineEdit.Normal if on else QLineEdit.Password))
    ed.setTextMargins(0, 0, 24, 0)
    old = ed.resizeEvent

    def _rs(ev):
        old(ev)
        b.setGeometry(ed.width() - 26, 0, 24, ed.height())
    ed.resizeEvent = _rs


class UpdateBox(QGroupBox):
    available = Signal(str)                # нашлась новая версия
    # фаза для анимации: idle/checking/uptodate/available/download/
    # install/done/error; данные — dict
    phase = Signal(str, object)

    def __init__(self, target, cfg_get, cfg_set, on_quit=None, log=None,
                 parent=None, can_install=None, restart_ask=True):
        super().__init__("🔑 Доступ к GitHub", parent)
        self.t = target
        self._get, self._set = cfg_get, cfg_set
        self._quit = on_quit
        self._log = log or (lambda *_a: None)
        self.can_install = can_install         # ★ 1.3.2 (из 1.2.2): () -> "" | причина «нельзя сейчас»
        self.restart_ask = restart_ask         # ★ 1.3.3: False — перезапуск сам через 3 с
        self._rel = None
        self._busy = False
        self._installing = False       # ★ 1.4.1: скачивание / установка
        self._last_err = ""
        self.last_check = ""
        self._sig = _Sig(self)
        self._sig.checked.connect(self._on_checked)
        self._sig.progress.connect(self._on_progress)
        self._sig.done.connect(self._on_done)
        cfg = dict(cfg_get() or {})

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 6, 10, 8)
        v.setSpacing(6)
        self.setToolTip(
            f"Обновление из приватного репозитория {target.owner}/{target.repo}.\n"
            f"Программа запущена: {gh_update.run_kind_text()}.\n"
            "Берётся архив исходников из папки release нужной ветки.\nТокен "
            "GitHub — fine-grained, только этот репозиторий, Contents: "
            "Read-only. Хранится только в настройках программы.")
        row = QHBoxLayout()
        row.addWidget(QLabel("Токен:"))
        self.ed_token = QLineEdit(cfg.get("token") or "")
        self.ed_token.setEchoMode(QLineEdit.Password)
        self.ed_token.setPlaceholderText("github_pat_…")
        self.ed_token.setMinimumWidth(190)
        _add_eye(self.ed_token)
        self.ed_token.editingFinished.connect(self._save)
        self.ed_token.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ed_token.customContextMenuRequested.connect(self._token_menu)
        row.addWidget(self.ed_token, 1)
        b = QPushButton("?")
        b.setFixedSize(30, 24)
        b.setStyleSheet("padding:0; font-weight:bold;")
        b.setToolTip("Как получить токен GitHub — пошагово с картинками")
        b.clicked.connect(self.show_help)
        row.addWidget(b)
        v.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Ветка:"))
        self.ed_branch = QLineEdit(cfg.get("branch") or target.branch)
        self.ed_branch.setFixedWidth(130)
        self.ed_branch.setToolTip("Из какой ветки брать release/ (обычно main)")
        self.ed_branch.editingFinished.connect(self._save)
        row.addWidget(self.ed_branch)
        row.addSpacing(10)
        row.addWidget(QLabel("Каждые:"))
        self.cb_every = QComboBox()
        for hrs, title in EVERY_CHOICES:
            self.cb_every.addItem(title, hrs)
        try:
            cur = int(cfg.get("every_h") or AUTO_EVERY_H)
        except (TypeError, ValueError):
            cur = AUTO_EVERY_H
        i = self.cb_every.findData(cur)
        self.cb_every.setCurrentIndex(i if i >= 0 else self.cb_every.findData(AUTO_EVERY_H))
        self.cb_every.setToolTip("Как часто проверять автоматически "
                                 "(первая проверка — через 30 с после запуска)")
        self.cb_every.currentIndexChanged.connect(self._every_changed)
        row.addWidget(self.cb_every)
        row.addStretch(1)
        v.addLayout(row)
        # одна строка: «Проверить сейчас» + переключатель автопроверки
        # (кнопка: включена — зелёная, выключена — серая; надпись внутри)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.btn_check = QPushButton("🔍 Проверить сейчас")
        self.btn_check.clicked.connect(lambda: self.check(manual=True))
        row.addWidget(self.btn_check, 1)
        self.ch_auto = QPushButton()
        self.ch_auto.setCheckable(True)
        self.ch_auto.setChecked(bool(cfg.get("auto", True)))
        self.ch_auto.toggled.connect(self._auto_toggled)
        self._auto_look()
        row.addWidget(self.ch_auto, 1)
        v.addLayout(row)
        self.btn_update = QPushButton("⬇ Обновить")
        self.btn_update.clicked.connect(self.update_now)
        self.btn_update.hide()
        v.addWidget(self.btn_update)
        self.btn_restart = QPushButton("↻ Перезапустить программу")
        self.btn_restart.clicked.connect(self.restart)
        self.btn_restart.hide()
        v.addWidget(self.btn_restart)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.hide()
        v.addWidget(self.bar)
        self.lbl = QLabel(f"установлена версия {target.current} · Python")
        self.lbl.setWordWrap(True)
        self.lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.lbl)
        v.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._auto_tick)
        if self.ch_auto.isChecked():
            self._timer.start(AUTO_FIRST_MS)

    # ---------- инструкция ----------
    def show_help(self):
        try:
            from .gh_update_help import show_token_help, step_for_error
        except ImportError:
            from gh_update_help import show_token_help, step_for_error
        # была ошибка — сразу на шаг, который её чинит
        show_token_help(self, self.t.owner, self.t.repo, self.t.repo,
                        step_for_error(self._last_err), self.t)

    def _token_menu(self, pos):
        m = self.ed_token.createStandardContextMenu()
        m.addSeparator()
        m.addAction("❓ Как получить токен…", self.show_help)
        m.addAction("🌐 Открыть страницу токенов GitHub",
                    lambda: QDesktopServices.openUrl(QUrl(TOKENS_URL)))
        m.exec(self.ed_token.mapToGlobal(pos))

    # ---------- настройки ----------
    def _cfg(self):
        return {"token": self.ed_token.text().strip(),
                "auto": self.ch_auto.isChecked(),
                "branch": self.ed_branch.text().strip() or "main",
                "every_h": self._every_h()}

    def _every_h(self):
        return int(self.cb_every.currentData() or AUTO_EVERY_H)

    def _every_changed(self, *_a):
        self._save()
        self._auto_look()
        if self.ch_auto.isChecked() and self._timer.isActive():
            self._timer.start(self._every_h() * 3600 * 1000)   # отсчёт заново

    def _save(self):
        try:
            self._set(self._cfg())
        except Exception as exc:                       # noqa: BLE001
            self._log(f"обновление: настройки не сохранены: {exc}")

    def _auto_look(self):
        on = self.ch_auto.isChecked()
        self.ch_auto.setToolTip(
            f"Через 30 с после запуска и дальше каждые {self.cb_every.currentText()} (выбор «Каждые»). "
            "Ставит только по вашей кнопке.\nНажать — включить / выключить.")
        self.ch_auto.setText(("✓ " if on else "✗ ") + "Проверять автоматически")
        th = _theme()
        off = (getattr(th, "BG_PANEL", "") or "#3a3f46",
               getattr(th, "TEXT_DIM", "") or "#c9ced4",
               getattr(th, "BORDER", "") or "#4a5058")
        self.ch_auto.setStyleSheet(
            "QPushButton{background:%s;color:%s;border:1px solid %s;"
            "border-radius:3px;padding:4px 8px;}"
            % (("#1e8f4e", "#ffffff", "#25a85c") if on else off))

    def apply_theme(self):
        """★ 1.3.1: смена схемы — кнопка «Проверять автоматически» в цвета
        новой схемы (свой стиль кнопки ставится из палитры при показе)."""
        self._auto_look()

    def _auto_toggled(self, on):
        self._auto_look()
        self._save()
        if on:
            self._timer.start(AUTO_FIRST_MS)
        else:
            self._timer.stop()

    def _auto_tick(self):
        if self.ch_auto.isChecked():
            self.check(manual=False)
            self._timer.start(self._every_h() * 3600 * 1000)

    def _status(self, text, color=""):
        self.lbl.setStyleSheet(f"color:{color};" if color else "")
        self.lbl.setText(text)

    def _target(self):
        c = self._cfg()
        self.t.branch = c["branch"]
        return self.t, c["token"]

    # ---------- проверка ----------
    def check(self, manual=True):
        if self._busy:
            return
        t, token = self._target()
        if not token:
            if manual:
                self._status("впишите токен GitHub (только чтение) — "
                             "как получить: кнопка «?»", "#e0a030")
                self.phase.emit("error", {"text": "нет токена — кнопка «?»"})
            return
        self._busy = True
        self.btn_check.setEnabled(False)
        self._status(f"проверяю {t.owner}/{t.repo} ({t.branch})…")
        self.phase.emit("checking", {})

        def work():
            try:
                rel, new = gh_update.check(t, token)
                wn = ""
                if new:
                    wn = gh_update.whats_new(t, token, rel.version)
                self._sig.checked.emit(rel, new, "", wn)
            except Exception as exc:                   # noqa: BLE001
                self._sig.checked.emit(None, False, str(exc), "")
        threading.Thread(target=work, daemon=True, name="gh-check").start()

    def _on_checked(self, rel, new, err, wn):
        self._busy = False
        self.btn_check.setEnabled(True)
        self.last_check = time.strftime("%H:%M")
        self._last_err = err
        if err:
            self._log(f"обновление: {err}")
            self._status("ошибка: " + err + (" — см. «?»" if any(
                c in err for c in ("401", "403", "404", "токен")) else ""),
                "#e05555")
            self.phase.emit("error", {"text": err})
            return
        if rel is None:
            self._status(f"в release/ нет архивов {self.t.name}_v*.zip",
                         "#e0a030")
            self.phase.emit("error", {"text": "в release/ нет архивов"})
            return
        if not new:
            self.btn_update.hide()
            self._status(f"✓ последняя версия ({self.t.current})", "#3fbf6f")
            self.phase.emit("uptodate", {"at": self.last_check})
            return
        self._rel = rel
        self.btn_update.setText(f"⬇ Обновить до {rel.version}")
        self.btn_update.show()
        self._status(f"доступна версия {rel.version} (исходники, {_mb(rel.size)} МБ), у вас {self.t.current}",
                     "#4aa3ff")
        self._log(f"обновление: доступна версия {rel.version}")
        self.phase.emit("available", {"ver": rel.version, "size": rel.size,
                                      "new": wn})
        self.available.emit(rel.version)

    # ---------- скачивание и установка ----------
    def busy(self):
        """★ 1.3.2 (из 1.2.2): идёт скачивание / установка — окно не закрывать.
        ★ 1.4.1: только они — простая проверка версии закрыть не мешает
        (раньше окно не закрывалось «идёт установка», пока GitHub думал)."""
        return self._installing

    def update_now(self):
        if self._busy or self._rel is None:
            return
        why = self.can_install() if self.can_install else ""
        if why:                                # ★ 1.3.2: например, идёт заливка — старое ядро + новые файлы
            QMessageBox.information(self, "Обновление", why)
            return
        t, token = self._target()
        rel = self._rel
        self._busy = True
        self._installing = True
        self.btn_check.setEnabled(False)
        self.btn_update.setEnabled(False)
        self.bar.setValue(0)
        self.bar.setFormat("скачиваю…")
        self.bar.show()
        self._status(f"скачиваю {rel.path}…")
        self.phase.emit("download", {"got": 0, "total": rel.size,
                                     "ver": rel.version})

        def work():
            try:
                path = gh_update.download(
                    t, token, rel,
                    progress=lambda got, tot: self._sig.progress.emit(got, tot))
                self._sig.progress.emit(-1, 0)          # «устанавливаю»
                n = gh_update.install(t, path, rel.version, log=self._log)
                self._sig.done.emit(True, f"обновлено до {rel.version} (файлов: {len(n)})")
            except Exception as exc:                   # noqa: BLE001
                self._sig.done.emit(False, str(exc))
        threading.Thread(target=work, daemon=True, name="gh-update").start()

    def _on_progress(self, got, total):
        if got < 0:
            self.bar.setValue(1000)
            self.bar.setFormat("устанавливаю…")
            self.phase.emit("install", {"ver": self._rel.version})
            return
        if total > 0:
            self.bar.setValue(min(1000, got * 1000 // total))
            self.bar.setFormat(f"{_mb(got)} из {_mb(total)} МБ — {got * 100 // total}%")
        else:
            self.bar.setFormat(f"{_mb(got)} МБ")
        self.phase.emit("download", {"got": got, "total": total,
                                     "ver": self._rel.version})

    def _on_done(self, ok, text):
        self._busy = False
        self._installing = False
        self.btn_check.setEnabled(True)
        self.btn_update.setEnabled(True)
        self._log(f"обновление: {text}")
        if not ok:
            self.bar.hide()
            self._status("ошибка: " + text, "#e05555")
            self.phase.emit("error", {"text": text})
            return
        self.btn_update.hide()
        self.btn_restart.show()
        self.bar.setFormat("готово ✓")
        self.t.current = self._rel.version         # ★ 1.3.3: авто-проверка не предложит ту же версию
        self._status("✓ " + text + (". Нужен перезапуск." if self.restart_ask
                                     else ". Перезапуск через 3 с…"), "#3fbf6f")
        self.phase.emit("done", {"ver": self._rel.version})
        if not self.restart_ask:                   # ★ 1.3.3: обновили — перезапускаем сами
            QTimer.singleShot(3000, self.restart)
            return
        msg = (f"Программа обновлена до {self._rel.version}.\nПерезапустить сейчас?")
        ans = QMessageBox.question(self, "Обновление", msg)
        if ans == QMessageBox.Yes:
            self.restart()

    def restart(self):
        try:
            # ★ 5.16.85: из отдельного апдейтера (update.pyw) — запустить
            # саму программу, а не апдейтер снова
            main = os.path.abspath(os.path.join(self.t.app_dir,
                                                self.t.main_file))
            own = os.path.abspath(sys.argv[0] or "")
            gh_update.restart(
                None if os.path.normcase(own) == os.path.normcase(main)
                else [main])
        except Exception as exc:                       # noqa: BLE001
            self._status(f"не удалось перезапустить: {exc} — закройте и "
                         "откройте программу сами", "#e05555")
            return
        if self._quit:
            QTimer.singleShot(0, self._quit)


class UpdateAnim(QWidget):
    """Картинка «облако GitHub → линия → компьютер» с анимацией фазы."""

    def __init__(self, current, repo="", parent=None):
        super().__init__(parent)
        self.cur, self.repo = current, repo
        self.ph, self.d = "idle", {}
        self.t0 = time.monotonic()
        self._speed = 0.0
        self._spd_pt = None
        self.setMinimumSize(460, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._tm = QTimer(self)
        self._tm.setInterval(33)
        self._tm.timeout.connect(self._tick)

    def set_phase(self, ph, d=None):
        d = dict(d or {})
        if ph == "download":
            now = time.monotonic()
            got = d.get("got", 0)
            if self.ph != "download" or not self._spd_pt:
                self._spd_pt, self._speed = (now, got), 0.0
            elif now - self._spd_pt[0] >= 0.5:
                inst = (got - self._spd_pt[1]) / (now - self._spd_pt[0])
                self._speed = inst if not self._speed else (
                    0.6 * self._speed + 0.4 * inst)
                self._spd_pt = (now, got)
        if ph != self.ph:
            self.t0 = time.monotonic()
        self.ph, self.d = ph, d
        if ph in ("checking", "available", "download", "install", "done"):
            self._tm.start()
        else:
            self._tm.stop()
        self.update()

    def _tick(self):
        # ★ 1.3.1: «готово» дорисовано (анимация — 0.6 с) — кадры не нужны:
        # таймер 33 мс крутился до перезапуска программы
        if self.ph == "done" and time.monotonic() - self.t0 > 1.0:
            self._tm.stop()
        if self.isVisible():
            self.update()

    # ---------- рисование ----------
    def paintEvent(self, _e):
        th = _theme()
        acc = QColor(getattr(th, "ACCENT", "") or "#4aa3ff")
        txt = QColor(getattr(th, "TEXT", "") or "#e6e6e6")
        dim = QColor(getattr(th, "TEXT_DIM", "") or "#8a9099")
        pan = QColor(getattr(th, "BG_PANEL", "") or "#1b1f26")
        brd = QColor(getattr(th, "BORDER", "") or "#3a4350")
        ok, bad = QColor("#3fbf6f"), QColor("#e05555")
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        p.setPen(QPen(brd, 1))
        p.setBrush(pan)
        p.drawRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 8, 8)
        t = time.monotonic() - self.t0
        ph, d = self.ph, self.d
        cy = 92
        cx_l, cx_r = 125, W - 125
        # ---- линия между облаком и ПК ----
        x1, x2 = cx_l + 58, cx_r - 58
        path = QPainterPath(QPointF(x1, cy))
        path.cubicTo(QPointF((x1 + x2) / 2, cy - 34),
                     QPointF((x1 + x2) / 2, cy + 34), QPointF(x2, cy))
        line_c = QColor(acc) if ph in ("download", "install", "done") else QColor(dim)
        if ph == "error":
            line_c = QColor(bad)
        pen = QPen(line_c, 2.2, Qt.DashLine if ph in ("idle", "error") else Qt.SolidLine)
        line_c.setAlpha(150)
        pen.setColor(line_c)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        # ---- облако GitHub ----
        glow = ph == "available"
        self._cloud(p, QPointF(cx_l, cy), acc if glow else dim, txt, t, glow)
        # ---- компьютер ----
        self._pc(p, QPointF(cx_r, cy), txt, dim, acc, ok, t)
        # ---- что бежит по линии ----
        if ph == "checking":                       # запрос ← и ответ →
            for k in range(3):
                f = ((t * 0.9 + k / 3.0) % 1.0)
                pt = path.pointAtPercent(1 - f)
                c = QColor(acc)
                c.setAlpha(int(255 * math.sin(math.pi * f)))
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawEllipse(pt, 4, 4)
            for k in range(3):                     # «радар» вокруг облака
                r = 30 + ((t * 40 + k * 22) % 66)
                c = QColor(acc)
                c.setAlpha(max(0, int(160 * (1 - (r - 30) / 66))))
                p.setPen(QPen(c, 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx_l, cy), r, r * 0.72)
        elif ph == "download":
            tot = max(1, int(d.get("total") or 1))
            frac = min(1.0, (d.get("got") or 0) / tot)
            for k in range(7):                     # пакеты-«кирпичики»
                f = (t * 0.55 + k / 7.0) % 1.0
                pt = path.pointAtPercent(f)
                c = QColor(acc)
                c.setAlpha(int(90 + 165 * math.sin(math.pi * f)))
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(pt.x() - 6, pt.y() - 4, 12, 8), 2, 2)
            self._ring(p, QPointF(cx_r, cy - 6), frac, acc, brd)
        elif ph == "install":
            self._gear(p, QPointF(cx_r, cy - 6), t, acc)
        elif ph == "done":
            self._check(p, QPointF(cx_r, cy - 6), ok, min(1.0, t / 0.6))
        elif ph == "uptodate":
            self._check(p, QPointF(cx_r, cy - 6), ok, 1.0)
        elif ph == "error":
            mid = path.pointAtPercent(0.5)
            p.setPen(QPen(bad, 3))
            p.drawLine(mid + QPointF(-7, -7), mid + QPointF(7, 7))
            p.drawLine(mid + QPointF(-7, 7), mid + QPointF(7, -7))
        # ---- значок новой версии над облаком ----
        if ph in ("available", "download", "install") and d.get("ver"):
            pulse = 0.5 + 0.5 * math.sin(t * 4) if ph == "available" else 1
            self._font(p, 9, True)
            lab = f"НОВАЯ {d['ver']}"
            bw = p.fontMetrics().horizontalAdvance(lab) + 22
            r = QRectF(cx_l - bw / 2, cy - 74, bw, 22)
            c = QColor(acc)
            c.setAlpha(int(140 + 115 * pulse))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r, 11, 11)
            p.setPen(QColor("#ffffff"))
            p.drawText(r, Qt.AlignCenter, lab)
        # ---- подписи под картинкой ----
        self._font(p, 8)
        p.setPen(dim)
        p.drawText(QRectF(cx_l - 115, cy + 46, 230, 16), Qt.AlignCenter,
                   self.repo or "репозиторий GitHub")
        p.drawText(QRectF(cx_r - 115, cy + 46, 230, 16), Qt.AlignCenter,
                   f"этот компьютер · {self.cur} · Python")
        big, small, col = self._caption()
        self._font(p, 12, True)
        p.setPen(col or txt)
        p.drawText(QRectF(12, H - 58, W - 24, 24), Qt.AlignCenter, big)
        self._font(p, 9)
        p.setPen(dim)
        p.drawText(QRectF(12, H - 34, W - 24, 32),
                   Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, small)
        p.end()

    def _caption(self):
        ph, d = self.ph, self.d
        if ph == "checking":
            return "Проверяю, есть ли новая версия…", "спрашиваю GitHub", None
        if ph == "available":
            return (f"Доступна новая версия {d.get('ver')}",
                    f"размер {_mb(d.get('size') or 0)} МБ · у вас {self.cur} · "
                    f"нажмите «Обновить до {d.get('ver')}»",
                    QColor("#4aa3ff"))
        if ph == "download":
            tot = int(d.get("total") or 0)
            got = int(d.get("got") or 0)
            pc = (got * 100 // tot) if tot else 0
            spd = (f" · {_mb(self._speed)} МБ/с") if self._speed > 0 else ""
            return (f"Скачиваю {d.get('ver')} — {pc}%",
                    f"{_mb(got)} из {_mb(tot)} МБ{spd}", None)
        if ph == "install":
            return (f"Устанавливаю {d.get('ver')}…",
                    "старый код стираю, настройки не трогаю", None)
        if ph == "done":
            return (f"Готово: установлена {d.get('ver')}",
                    "нужен перезапуск программы", QColor("#3fbf6f"))
        if ph == "uptodate":
            return (f"У вас последняя версия {self.cur}",
                    f"проверено в {d.get('at', '')}", QColor("#3fbf6f"))
        if ph == "error":
            return "Не получилось", str(d.get("text", ""))[:240], QColor("#e05555")
        return (f"Установлена версия {self.cur} (Python)",
                "впишите токен и нажмите «Проверить сейчас»", None)

    @staticmethod
    def _font(p, pt, bold=False):
        f = QFont()
        f.setPointSizeF(pt)
        f.setBold(bold)
        p.setFont(f)

    # значок GitHub (Octicons «mark-github», 16×16)
    GITHUB_MARK = (
        "M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75"
        "-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67"
        "-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08"
        " 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33"
        "-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01"
        " 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z")

    def _mark(self, p, cx, cy, size, color):
        """Значок GitHub цветом color, по центру (cx, cy). -> False, если нарисовать нечем (нет QtSvg)."""
        if QSvgRenderer is None:
            return False
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path fill="{QColor(color).name()}" d="{self.GITHUB_MARK}"/></svg>')
        r = QSvgRenderer(QByteArray(svg.encode("ascii")))
        if not r.isValid():
            return False
        r.render(p, QRectF(cx - size / 2, cy - size / 2, size, size))
        return True

    def _cloud(self, p, c, col, txt, t, glow):
        x, y = c.x(), c.y()
        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)          # контур без внутренних дуг
        path.addEllipse(QPointF(x - 22, y + 6), 22, 18)
        path.addEllipse(QPointF(x + 2, y - 8), 26, 24)
        path.addEllipse(QPointF(x + 26, y + 6), 20, 17)
        path.addRoundedRect(QRectF(x - 42, y + 2, 86, 22), 11, 11)
        path = path.simplified()
        if glow:
            g = QColor(col)
            g.setAlpha(int(60 + 50 * math.sin(t * 4)))
            p.setPen(QPen(g, 8))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        fill = QColor(col)
        fill.setAlpha(45)
        p.setPen(QPen(col, 2))
        p.setBrush(fill)
        p.drawPath(path)
        if self._mark(p, x + 2, y - 14, 20, txt):     # значок — в «шапке» облака, надпись ниже
            self._font(p, 8, True)
            p.setPen(txt)
            p.drawText(QRectF(x - 40, y + 2, 84, 20), Qt.AlignCenter, "GitHub")
        else:
            self._font(p, 9, True)
            p.setPen(txt)
            p.drawText(QRectF(x - 40, y - 6, 84, 24), Qt.AlignCenter, "GitHub")

    def _pc(self, p, c, txt, dim, acc, ok, t):
        x, y = c.x(), c.y()
        scr = QRectF(x - 44, y - 34, 88, 56)
        p.setPen(QPen(dim, 2))
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRoundedRect(scr, 5, 5)
        p.setPen(QPen(dim, 3))
        p.drawLine(QPointF(x, y + 22), QPointF(x, y + 32))
        p.drawLine(QPointF(x - 20, y + 33), QPointF(x + 20, y + 33))
        if self.ph in ("idle", "checking", "available", "error"):
            self._font(p, 10, True)
            p.setPen(txt)
            p.drawText(scr, Qt.AlignCenter, self.cur)

    def _ring(self, p, c, frac, acc, brd):
        r = QRectF(c.x() - 20, c.y() - 20, 40, 40)
        p.setPen(QPen(brd, 4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(r)
        p.setPen(QPen(acc, 4, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 90 * 16, -int(360 * 16 * frac))
        self._font(p, 8, True)
        p.setPen(QColor("#ffffff"))
        p.drawText(r, Qt.AlignCenter, f"{int(frac * 100)}%")

    def _gear(self, p, c, t, acc):
        p.save()
        p.translate(c)
        p.rotate((t * 180) % 360)
        p.setPen(Qt.NoPen)
        p.setBrush(acc)
        for k in range(8):
            p.save()
            p.rotate(k * 45)
            p.drawRect(QRectF(-3.5, -19, 7, 8))
            p.restore()
        p.drawEllipse(QPointF(0, 0), 13, 13)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(QPointF(0, 0), 5, 5)
        p.restore()

    def _check(self, p, c, ok, k):
        p.setPen(Qt.NoPen)
        p.setBrush(ok)
        p.drawEllipse(c, 18, 18)
        pts = [c + QPointF(-9, 0), c + QPointF(-3, 7), c + QPointF(10, -7)]
        pen = QPen(QColor("#ffffff"), 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        if k < 0.5:
            a, b = pts[0], pts[0] + (pts[1] - pts[0]) * (k / 0.5)
            p.drawLine(a, b)
        else:
            p.drawLine(pts[0], pts[1])
            p.drawLine(pts[1], pts[1] + (pts[2] - pts[1]) * ((k - 0.5) / 0.5))


class UpdatePage(QWidget):
    """Готовая вкладка: слева доступ (UpdateBox), справа анимация и
    «Что нового»."""

    def __init__(self, target, cfg_get, cfg_set, on_quit=None, log=None,
                 parent=None, can_install=None, restart_ask=True):
        super().__init__(parent)
        self.setObjectName("setinner")
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(12)
        self.box = UpdateBox(target, cfg_get, cfg_set, on_quit, log,
                             can_install=can_install,
                             restart_ask=restart_ask)
        self.box.setFixedWidth(400)
        h.addWidget(self.box, 0, Qt.AlignTop)
        right = QVBoxLayout()
        right.setSpacing(8)
        self.anim = UpdateAnim(target.current, f"{target.owner}/{target.repo}")
        right.addWidget(self.anim)
        self.gb_new = QGroupBox("📝 Что нового")
        gv = QVBoxLayout(self.gb_new)
        gv.setContentsMargins(8, 6, 8, 8)
        self.txt_new = QPlainTextEdit()
        self.txt_new.setReadOnly(True)
        self.txt_new.setPlaceholderText(
            "Здесь появится список изменений новой версии, когда она найдётся.")
        gv.addWidget(self.txt_new)
        right.addWidget(self.gb_new, 1)
        h.addLayout(right, 1)
        self.box.phase.connect(self._on_phase)

    def _on_phase(self, ph, d):
        self.anim.set_phase(ph, d)
        if ph == "available":
            ver = d.get("ver")
            self.gb_new.setTitle(f"📝 Что нового в {ver}")
            self.txt_new.setPlainText(d.get("new") or
                                      f"(в CHANGELOG нет раздела про {ver})")
