"""gh_update_help — окно «Как получить токен GitHub» (общее, PySide6).

Пошаговая инструкция с картинками. Картинки — схемы страниц GitHub,
нарисованные QPainter (никаких файлов: модуль переносится в любое
приложение вместе с gh_update.py и gh_update_qt.py). Нужный элемент
обведён красной рамкой с номером, как на скриншоте с пометками.

    show_token_help(parent, owner="romzespra-collab", repo="Smart_BMS",
                    app_name="Smart_BMS")
"""
import os

from PySide6.QtCore import QRectF, Qt, QUrl
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QGuiApplication,
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLayout, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

NEW_TOKEN_URL = "https://github.com/settings/personal-access-tokens/new"
TOKENS_URL = "https://github.com/settings/personal-access-tokens"

# светлая «гитхабовская» гамма — картинка похожа на то, что видно в браузере
_BG, _LINE, _TXT, _DIM = "#ffffff", "#d0d7de", "#1f2328", "#59636e"
_BLUE, _GREEN, _MARK = "#0969da", "#1f883d", "#e5383b"


class _Mock(QWidget):
    """Схема страницы: элементы сверху вниз. Элемент — кортеж
    (вид, текст, пометка[, доп]); пометка — номер в красной рамке или 0."""
    W, H = 600, 290

    def __init__(self, title, items, url="github.com/settings/…", parent=None,
                 h=None):
        super().__init__(parent)
        self.title, self.items, self.url = title, items, url
        if h:
            self.H = h
        self.setFixedSize(self.W, self.H)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # окно браузера
        p.setPen(QPen(QColor("#8c959f"), 1))
        p.setBrush(QColor("#f6f8fa"))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.W - 1, self.H - 1), 8, 8)
        for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
            p.setBrush(QColor(c))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(12 + i * 16, 10, 10, 10))
        p.setBrush(QColor(_BG))
        p.setPen(QPen(QColor(_LINE), 1))
        p.drawRoundedRect(QRectF(66, 6, self.W - 80, 18), 9, 9)
        self._font(p, 8)
        p.setPen(QColor(_DIM))
        p.drawText(QRectF(78, 6, self.W - 100, 18), Qt.AlignVCenter, "🔒 " + self.url)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(_BG))
        p.drawRect(QRectF(1, 31, self.W - 2, self.H - 33))
        x, y = 22, 42
        self._font(p, 12, True)
        p.setPen(QColor(_TXT))
        p.drawText(QRectF(x, y, self.W - 40, 22), Qt.AlignVCenter, self.title)
        y += 26
        p.setPen(QPen(QColor(_LINE), 1))
        p.drawLine(x, y, self.W - 20, y)
        y += 10
        marks = []
        self._extra = []                           # доп. пометки из элемента
        for it in self.items:
            kind, text, mark = it[0], it[1], it[2]
            extra = it[3] if len(it) > 3 else None
            r = self._item(p, kind, text, extra, x, y)
            if mark:
                marks.append((mark, r))
            if kind == "space":
                y += extra or 10
            elif kind != "popup":                  # всплывашка — поверх, без сдвига
                y = r.bottom() + 8
        for n, r in marks + self._extra:                         # пометки — поверх всего
            self._mark(p, n, r)
        p.end()

    @staticmethod
    def _font(p, pt, bold=False):
        f = QFont()
        f.setPointSizeF(pt)
        f.setBold(bold)
        p.setFont(f)

    def _item(self, p, kind, text, extra, x, y):
        """Нарисовать элемент, вернуть его прямоугольник (для пометки)."""
        if kind == "space":
            return QRectF(x, y, 0, 0)
        if kind == "popup":                        # всплывающий список прав
            # (вид, текст поиска, пометка, (x, y, [(строка, отмечено)…]))
            px, py, rows = extra
            box = QRectF(px, py, 250, 44 + 22 * len(rows))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 40))
            p.drawRoundedRect(box.translated(2, 3), 8, 8)
            p.setPen(QPen(QColor(_LINE), 1))
            p.setBrush(QColor(_BG))
            p.drawRoundedRect(box, 8, 8)
            self._font(p, 8, True)
            p.setPen(QColor(_TXT))
            p.drawText(QRectF(px + 10, py + 2, 230, 18), Qt.AlignVCenter,
                       "Select repository permissions")
            srch = QRectF(px + 8, py + 20, 234, 20)
            p.setPen(QPen(QColor(_BLUE), 1.4))
            p.drawRoundedRect(srch, 5, 5)
            self._font(p, 8)
            p.setPen(QColor(_TXT))
            p.drawText(srch.adjusted(8, 0, 0, 0), Qt.AlignVCenter, "🔍 " + text)
            hit = box
            for i, (t, on) in enumerate(rows):
                rr = QRectF(px + 8, py + 44 + i * 22, 234, 20)
                cb = QRectF(rr.left() + 4, rr.top() + 4, 12, 12)
                p.setPen(QPen(QColor(_BLUE if on else "#8c959f"), 1.2))
                p.setBrush(QColor(_BLUE if on else _BG))
                p.drawRoundedRect(cb, 2, 2)
                if on:
                    p.setPen(QPen(QColor("#ffffff"), 1.6))
                    p.drawLine(cb.left() + 3, cb.center().y(), cb.left() + 5, cb.bottom() - 3)
                    p.drawLine(cb.left() + 5, cb.bottom() - 3, cb.right() - 2, cb.top() + 3)
                    hit = rr
                p.setPen(QColor(_TXT))
                p.drawText(rr.adjusted(24, 0, 0, 0), Qt.AlignVCenter, t)
            return hit
        if kind == "pair":                         # «сообщение программы → что делать»
            self._font(p, 8)
            r = QRectF(x, y, self.W - 44, 30)
            p.setPen(QPen(QColor("#f1c1c1"), 1))
            p.setBrush(QColor("#fff5f5"))
            p.drawRoundedRect(r, 5, 5)
            p.setPen(QColor("#cf222e"))
            p.drawText(QRectF(x + 8, y, 285, 30),
                       Qt.AlignVCenter | Qt.TextWordWrap, text)
            p.setPen(QColor(_GREEN))
            p.drawText(QRectF(x + 300, y, self.W - 44 - 306, 30),
                       Qt.AlignVCenter | Qt.TextWordWrap, "→ " + extra)
            return r
        if kind == "tokenrow":                     # строка токена в списке + Delete
            r = QRectF(x, y, self.W - 44, 38)
            p.setPen(QPen(QColor(_LINE), 1))
            p.setBrush(QColor(_BG))
            p.drawRoundedRect(r, 6, 6)
            self._font(p, 9, True)
            p.setPen(QColor(_BLUE))
            p.drawText(QRectF(x + 12, y + 2, 300, 18), Qt.AlignVCenter, text)
            self._font(p, 8)
            p.setPen(QColor(_DIM))
            p.drawText(QRectF(x + 12, y + 19, 300, 16), Qt.AlignVCenter,
                       extra or "Never used")
            d = QRectF(r.right() - 70, y + 7, 60, 24)
            p.setPen(QPen(QColor("#d0d7de"), 1))
            p.setBrush(QColor("#f6f8fa"))
            p.drawRoundedRect(d, 6, 6)
            p.setPen(QColor("#cf222e"))
            p.drawText(d, Qt.AlignCenter, "Delete")
            return d
        if kind == "code":                         # дерево папок / код, моноширинно
            # extra = [(строка, цвет|None, пометка|0)…]
            lines = extra or []
            LH = 20
            box = QRectF(x, y, self.W - 44, 8 + LH * len(lines))
            p.setPen(QPen(QColor(_LINE), 1))
            p.setBrush(QColor("#f6f8fa"))
            p.drawRoundedRect(box, 6, 6)
            f = QFont("Consolas")
            f.setStyleHint(QFont.Monospace)
            f.setPointSizeF(8.5)
            p.setFont(f)
            fm = p.fontMetrics()
            for i, (t, col, mk) in enumerate(lines):
                rr = QRectF(x + 10, y + 4 + LH * i, self.W - 64, LH)
                p.setPen(QColor(col or _TXT))
                p.drawText(rr, Qt.AlignVCenter, t)
                if mk:
                    lead = len(t) - len(t.lstrip(" │├└─"))
                    x0 = rr.left() + fm.horizontalAdvance(t[:lead])
                    self._extra.append((mk, QRectF(
                        x0, rr.top() + 4, fm.horizontalAdvance(t[lead:].split("  ")[0]) + 2,
                        12)))
            return box
        if kind == "label":                        # подпись поля, жирная
            self._font(p, 9, True)
            p.setPen(QColor(_TXT))
            r = QRectF(x, y, 400, 16)
            p.drawText(r, Qt.AlignVCenter, text)
            return r
        if kind == "note":                         # мелкий серый текст
            self._font(p, 8)
            p.setPen(QColor(extra or _DIM))
            r = QRectF(x, y - 4, self.W - 50, 14)
            p.drawText(r, Qt.AlignVCenter, text)
            return r
        if kind == "h2":                           # заголовок раздела
            self._font(p, 11)
            p.setPen(QColor(_TXT))
            r = QRectF(x, y, 400, 20)
            p.drawText(r, Qt.AlignVCenter, text)
            p.setPen(QPen(QColor(_LINE), 1))
            p.drawLine(x, int(r.bottom()) + 3, self.W - 20, int(r.bottom()) + 3)
            return QRectF(x, y, 400, 24)
        if kind in ("input", "dropdown"):
            w = extra or 330
            r = QRectF(x, y, w, 24)
            p.setPen(QPen(QColor(_LINE), 1))
            p.setBrush(QColor(_BG if kind == "input" else "#f6f8fa"))
            p.drawRoundedRect(r, 5, 5)
            self._font(p, 9)
            p.setPen(QColor(_TXT))
            p.drawText(r.adjusted(9, 0, -9, 0), Qt.AlignVCenter, text)
            if kind == "dropdown":
                p.drawText(r.adjusted(0, 0, -9, 0), Qt.AlignVCenter | Qt.AlignRight, "▾")
            return r
        if kind == "radio":                        # (вид, текст, пометка, выбрано)
            self._font(p, 9, True)
            p.setPen(QPen(QColor(_BLUE if extra else "#8c959f"), 1.4))
            p.setBrush(QColor(_BG))
            p.drawEllipse(QRectF(x + 1, y + 2, 13, 13))
            if extra:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(_BLUE))
                p.drawEllipse(QRectF(x + 4.5, y + 5.5, 6, 6))
            p.setPen(QColor(_TXT))
            w = p.fontMetrics().horizontalAdvance(text) + 26
            r = QRectF(x, y, w, 17)
            p.drawText(r.adjusted(22, 0, 0, 0), Qt.AlignVCenter, text)
            return r
        if kind == "repo":                         # строка выбранного репозитория
            r = QRectF(x + 22, y, 420, 24)
            p.setPen(QPen(QColor(_LINE), 1))
            p.setBrush(QColor(_BG))
            p.drawRect(r)
            self._font(p, 9)
            p.setPen(QColor(_TXT))
            p.drawText(r.adjusted(10, 0, -10, 0), Qt.AlignVCenter, "🔒 " + text)
            p.drawText(r.adjusted(10, 0, -10, 0), Qt.AlignVCenter | Qt.AlignRight, "✕")
            return r
        if kind in ("button", "green"):            # (вид, текст, пометка, x-сдвиг)
            self._font(p, 9, kind == "green")
            w = p.fontMetrics().horizontalAdvance(text) + 26
            r = QRectF(x + (extra or 0), y, w, 26)
            p.setPen(QPen(QColor(_LINE if kind == "button" else _GREEN), 1))
            p.setBrush(QColor("#f6f8fa" if kind == "button" else _GREEN))
            p.drawRoundedRect(r, 6, 6)
            p.setPen(QColor(_TXT if kind == "button" else "#ffffff"))
            p.drawText(r, Qt.AlignCenter, text)
            return r
        if kind == "perm":                         # строка права: Contents  [Read-only ▾]
            r = QRectF(x, y, self.W - 44, 28)
            p.setPen(QPen(QColor(_LINE), 1))
            p.setBrush(QColor(_BG))
            p.drawRect(r)
            self._font(p, 9, True)
            p.setPen(QColor(_TXT))
            p.drawText(r.adjusted(10, 0, 0, 0), Qt.AlignVCenter, text)
            self._font(p, 9)
            dw = max(120, p.fontMetrics().horizontalAdvance(extra or "Read-only") + 34)
            dd = QRectF(r.right() - dw - 10, y + 3, dw, 22)
            p.setPen(QPen(QColor(_LINE), 1))
            p.setBrush(QColor("#f6f8fa"))
            p.drawRoundedRect(dd, 5, 5)
            self._font(p, 9)
            p.setPen(QColor(_TXT))
            p.drawText(dd.adjusted(8, 0, -8, 0), Qt.AlignVCenter, extra or "Read-only")
            p.drawText(dd.adjusted(8, 0, -8, 0), Qt.AlignVCenter | Qt.AlignRight, "▾")
            return dd
        if kind == "token":                        # зелёная плашка с токеном
            box = QRectF(x, y, self.W - 44, 70)
            p.setPen(QPen(QColor("#4ac26b"), 1))
            p.setBrush(QColor("#dafbe1"))
            p.drawRoundedRect(box, 6, 6)
            self._font(p, 9, True)
            p.setPen(QColor(_TXT))
            p.drawText(box.adjusted(12, 6, -10, 0), Qt.AlignTop,
                       "🔔 Make sure to copy your personal access token now…")
            fld = QRectF(x + 12, y + 32, self.W - 120, 26)
            p.setPen(QPen(QColor(_LINE), 1))
            p.setBrush(QColor(_BG))
            p.drawRoundedRect(fld, 5, 5)
            self._font(p, 9)
            p.setPen(QColor(_TXT))
            p.drawText(fld.adjusted(9, 0, 0, 0), Qt.AlignVCenter,
                       "github_pat_11AB…············…x9Z")
            cp = QRectF(fld.right() + 8, y + 32, 30, 26)
            p.setPen(QPen(QColor(_LINE), 1))
            p.setBrush(QColor("#f6f8fa"))
            p.drawRoundedRect(cp, 5, 5)
            p.setPen(QColor(_TXT))
            p.drawText(cp, Qt.AlignCenter, "⧉")
            return cp
        if kind == "app":                          # наш блок в программе (тёмный)
            box = QRectF(x, y, self.W - 44, 116)
            p.setPen(QPen(QColor("#3a4350"), 1))
            p.setBrush(QColor("#1b1f26"))
            p.drawRoundedRect(box, 5, 5)
            self._font(p, 9)
            p.setPen(QColor("#e6e6e6"))
            p.drawText(QRectF(x + 12, y + 4, 300, 18), Qt.AlignVCenter,
                       "🔄 Обновление с GitHub")
            p.drawText(QRectF(x + 12, y + 28, 60, 22), Qt.AlignVCenter, "Токен:")
            fld = QRectF(x + 70, y + 28, 300, 22)
            p.setPen(QPen(QColor("#4aa3ff"), 1))
            p.setBrush(QColor("#11141a"))
            p.drawRoundedRect(fld, 3, 3)
            p.setPen(QColor("#e6e6e6"))
            p.drawText(fld.adjusted(8, 0, 0, 0), Qt.AlignVCenter, "●●●●●●●●●●●●●●●●")
            p.drawText(QRectF(x + 12, y + 56, 300, 18), Qt.AlignVCenter,
                       "☑ Проверять автоматически")
            btn = QRectF(x + 12, y + 80, 150, 24)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#0a6fb5"))
            p.drawRoundedRect(btn, 3, 3)
            p.setPen(QColor("#ffffff"))
            p.drawText(btn, Qt.AlignCenter, "🔍 Проверить сейчас")
            self._extra.append((2, btn))
            return fld
        if kind == "menu":                         # левое меню настроек
            self._font(p, 9)
            r = QRectF(x, y, 230, 20 * len(text))
            for i, t in enumerate(text):
                rr = QRectF(x, y + i * 20, 230, 20)
                if i == extra:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor("#eaeef2"))
                    p.drawRoundedRect(rr, 4, 4)
                    p.setBrush(QColor(_BLUE))
                    p.drawRect(QRectF(x - 6, rr.top() + 3, 3, 14))
                p.setPen(QColor(_TXT))
                p.drawText(rr.adjusted(10 + (14 if t.startswith("  ") else 0), 0, 0, 0),
                           Qt.AlignVCenter, t.strip())
            return QRectF(x, y + extra * 20, 230, 20) if extra is not None else r
        return QRectF(x, y, 0, 0)

    @staticmethod
    def _mark(p, n, r):
        """Красная рамка вокруг элемента и кружок с номером."""
        thin = r.height() <= 14                    # строка дерева — тоньше, номер справа
        rr = r.adjusted(-3, -3, 3, 3) if thin else r.adjusted(-4, -4, 4, 4)
        p.setPen(QPen(QColor(_MARK), 1.8 if thin else 2.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rr, 5 if thin else 6, 5 if thin else 6)
        c = (QRectF(rr.right() + 3, rr.center().y() - 8, 16, 16) if thin
             else QRectF(rr.right() - 2, rr.top() - 11, 20, 20))
        path = QPainterPath()
        path.addEllipse(c)
        p.fillPath(path, QColor(_MARK))
        f = QFont()
        f.setPointSizeF(9)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(c, Qt.AlignCenter, str(n))


def _steps(owner, repo, app_name, target=None):
    full = f"{owner}/{repo}"
    nm = f"{app_name}_update"
    where = getattr(target, "where", "") or "Настройки → 🔄 Обновление"
    new_url = "github.com/settings/personal-access-tokens/new"
    return [
        ("Открыть страницу токенов",
         "Нажмите <b>«🌐 Открыть страницу GitHub»</b> внизу (в браузере нужно "
         "быть залогиненным в GitHub). Вручную: аватарка → <b>Settings</b> → "
         "внизу слева <b>Developer settings</b> → <b>Personal access tokens</b> "
         "→ <b>Fine-grained tokens</b> → <b>Generate new token</b>.<br>"
         "Старые неработающие токены удалите кнопкой <b>Delete</b> — чтобы не путаться.",
         _Mock("Fine-grained personal access tokens", [
             ("menu", ["GitHub Apps", "OAuth Apps", "Personal access tokens",
                       "  Fine-grained tokens", "  Tokens (classic)"], 1, 3),
             ("button", "Generate new token", 2, 400),
             ("tokenrow", "старый_токен", 3,
              "Never used • ⚠ This token has no expiration date"),
         ], url="github.com/settings/personal-access-tokens")),
        ("Имя и срок действия",
         f"<b>Token name</b> — любое, например <b>{nm}</b>. Description — можно "
         f"пусто.<br><b>Resource owner</b> — <b>{owner}</b> (уже стоит).<br>"
         "<b>Expiration</b> — <b>No expiration</b> (бессрочно) или свой срок "
         "(истечёт — сделать новый).",
         _Mock("New fine-grained personal access token", [
             ("label", "Token name *", 0),
             ("input", nm, 1),
             ("note", f"✔ '{nm}' is available.", 0, _GREEN),
             ("label", "Resource owner", 0),
             ("dropdown", "👤 " + owner, 2, 200),
             ("label", "Expiration", 0),
             ("dropdown", "📅 No expiration", 3, 200),
         ], url=new_url)),
        ("Доступ — к своему репозиторию",
         "⚠ По умолчанию отмечено <b>Public repositories</b> — с ним токен "
         "<b>НЕ видит</b> приватный репозиторий (программа скажет «токен не "
         "видит репозиторий»).<br>Отметьте <b>Only select repositories</b> → "
         f"<b>Select repositories</b> → <b>{full}</b>. Ниже должна появиться "
         "строка с 🔒 и «Selected 1 repository».",
         _Mock("Repository access", [
             ("radio", "Public repositories   ← по умолчанию, НЕ ТО", 0, False),
             ("radio", "All repositories", 0, False),
             ("radio", "Only select repositories", 1, True),
             ("dropdown", "▣ Select repositories  1", 2, 200),
             ("note", "Selected 1 repository.", 0),
             ("repo", full, 3),
         ], url=new_url)),
        ("Права — Contents: Read-only",
         "⚠ Сразу после выбора репозитория там «<b>Repositories 0</b>» — "
         "прав нет, будет ошибка.<br><b>Add permissions</b> → в списке "
         "(можно набрать в поиске «contents») отметьте <b>Contents</b> → "
         "щёлкните мимо списка → у Contents должно быть <b>Access: "
         "Read-only</b>. <b>Metadata</b> (Required) добавится сам — станет "
         "«<b>Repositories 2</b>». Больше ничего не включайте.",
         _Mock("Permissions", [
             ("note", "Choose the minimal permissions necessary for your needs.", 0),
             ("button", "Add permissions", 1, 420),
             ("popup", "contents", 2, (300, 132, [
                 ("Commit statuses", False), ("Contents", True),
                 ("Copilot agent settings", False)])),
             ("space", "", 0, 122),
             ("label", "Repositories  2        Account  0", 3),
             ("perm", "Contents", 4, "Access: Read-only"),
             ("perm", "Metadata   (Required)", 0, "Access: Read-only"),
         ], url=new_url, h=372)),
        ("Создать и скопировать токен",
         "Внизу страницы — зелёная <b>Generate token</b>. Появится токен "
         "<b>github_pat_…</b> — скопируйте кнопкой ⧉.<br><b>Он показывается "
         "ОДИН раз</b>: закрыли не скопировав — Delete и новый.<br>"
         "⚠ <b>Не делайте скриншот с токеном</b> и никому его не пересылайте.",
         _Mock("Fine-grained personal access tokens", [
             ("green", "Generate token", 1),
             ("note", "↓ после нажатия:", 0),
             ("label", nm, 0),
             ("note", "Never used • ⚠ This token has no expiration date", 0, "#9a6700"),
             ("token", "", 2),
         ], url="github.com/settings/personal-access-tokens")),
        ("Вставить в программу и проверить",
         f"<b>{where}</b> → поле <b>Токен</b> → вставить "
         "(Ctrl+V, старый текст удалить) → <b>«🔍 Проверить сейчас»</b>.<br>"
         "Получилось: «✓ последняя версия» или «доступна версия X» → "
         "<b>«⬇ Обновить до X»</b>. Один токен подходит всем программам "
         "этого репозитория.",
         _Mock(f"{app_name} → {where}", [
             ("app", "", 1),
         ], url="(это окно программы)")),
        ("Если ошибка — что сделать",
         "Программа сама выясняет причину и пишет её красным под кнопкой "
         "«Проверить сейчас». Найдите своё сообщение — справа, что сделать. "
         "Поправить токен можно без нового: страница токенов → имя токена → "
         "<b>Edit</b> → исправить → <b>Update</b> (в программе менять не надо).",
         _Mock("Сообщение программы → что делать", [
             ("pair", "токен не видит репозиторий", 0,
              f"шаг 3: Only select repositories → {repo}"),
             ("pair", "у токена нет права читать файлы", 0,
              "шаг 4: Contents → Read-only"),
             ("pair", "токен GitHub недействителен", 0,
              "удалён/истёк/вставлен не весь → новый токен"),
             ("pair", "нет ветки «…»", 0, "в поле «Ветка» — main"),
             ("pair", "нет связи с GitHub", 0, "интернет / прокси / антивирус"),
             ("pair", "нет папки release / нет архивов / версия внутри не та", 0,
              "шаг 8: как должен лежать проект"),
         ], url="(это окно программы)", h=340)),
        _layout_step(owner, repo, target),
    ]


def _layout_step(owner, repo, t):
    """Шаг «Где должен лежать проект на GitHub» — по настройкам ЭТОЙ
    программы (UpdateTarget): имя архива, главный файл, CHANGELOG."""
    name = getattr(t, "name", None) or "smart_bms"
    main = getattr(t, "main_file", None) or "Smart_BMS.pyw"
    branch = getattr(t, "branch", None) or "main"
    cl = getattr(t, "changelog", "") or ""
    src = cl.rsplit("/", 1)[0] if "/" in cl else ""
    ver = getattr(t, "current", "") or "1.0"
    vfs = tuple(getattr(t, "version_files", ()) or ())
    if vfs:
        vf = vfs[0]
    elif t is None or os.path.exists(os.path.join(getattr(t, "app_dir", "") or ".",
                                                  "app", "version.py")):
        vf = "app/version.py"
    else:
        vf = main
    nv = ".".join(ver.split(".")[:-1] + [str(int(ver.split(".")[-1]) + 1)]) \
        if ver.split(".")[-1].isdigit() else ver
    C, D, G = "#0969da", _DIM, _GREEN
    tree = [(f"{owner}/{repo}     (приватный, ветка {branch})", C, 1)]
    if src:
        tree += [(f"├─ {src}/          ← исходники программы", None, 0),
                 (f"│   ├─ {main}", None, 0),
                 (f"│   ├─ CHANGELOG.txt     ← «Что нового»: разделы «{nv}:»", None, 4),
                 (f"│   └─ {vf}    VERSION = \"{nv}\"", None, 0)]
    tree += [("└─ release/                 ← ровно так, в корне репозитория", G, 2),
             (f"    └─ {name}_v{nv}.zip     ← берётся самый новый номер", G, 3),
             (f"        └─ {name}/  {main if vf == main else main + ', ' + vf}",
              D, 0)]
    return (
        "Где должен лежать проект на GitHub",
        "Программа берёт обновление из <b>release/</b> в корне репозитория "
        f"<b>{owner}/{repo}</b>, ветка <b>{branch}</b>. Архив — <b>{name}_vX.Y.Z.zip</b> (номер "
        f"только цифрами). Внутри — папка <b>{name}/</b> с <b>{main}</b> и "
        f"номером версии в <b>{vf}</b>; он должен совпадать с номером в имени "
        "архива, иначе установка отменится. Старые архивы можно удалять.",
        _Mock("Репозиторий на GitHub", [
            ("code", "", 0, tree),
            ("note", "Собрать архив (из корня репозитория):", 0),
            ("code", "", 0, [(f"git archive --format=zip --prefix={name}/ \\",
                              None, 0),
                             (f"    -o release/{name}_v{nv}.zip HEAD:{src or '.'}", None, 0)]),
            ("note", "Несколько программ в одном репозитории — у каждой свой "
                     "префикс архива, токен один.", 0),
        ], url=f"github.com/{owner}/{repo}/tree/{branch}", h=372))


# по тексту ошибки программы — какой шаг инструкции открыть сразу
_ERR_STEP = (("не видит репозиторий", 2), ("права читать файлы", 3),
             ("Contents", 3), ("недействителен", 6), ("не подошёл", 6),
             ("нет ветки", 6), ("нет связи", 6), ("нет папки", 7),
             ("нет архивов", 7), ("внутри архива версия", 7),
             ("это не та программа", 7))


def step_for_error(err):
    """Номер шага (с 0) для текста ошибки; нет совпадения — 0."""
    for key, n in _ERR_STEP:
        if key in (err or ""):
            return n
    return 0


FOOTER = ("🔒 Токен — только для чтения и только к своему репозиторию. "
          "Вписывайте его только в программу: не пересылайте и не "
          "показывайте на скриншотах (поле в программе прячется глазиком).")


class TokenHelpDialog(QDialog):
    def __init__(self, parent=None, owner="romzespra-collab", repo="Smart_BMS",
                 app_name="Smart_BMS", step=0, target=None):
        super().__init__(parent)
        self.setWindowTitle("Обновление с GitHub — инструкция")
        self.steps = _steps(owner, repo, app_name, target)
        v = QVBoxLayout(self)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        v.setSizeConstraint(QLayout.SetFixedSize)   # картинка не обрезается
        self.lbl_head = QLabel()
        f = self.lbl_head.font()
        f.setPointSizeF(f.pointSizeF() + 3)
        f.setBold(True)
        self.lbl_head.setFont(f)
        v.addWidget(self.lbl_head)
        self.lbl_text = QLabel()
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setTextFormat(Qt.RichText)
        self.lbl_text.setFixedHeight(92)
        self.lbl_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lbl_text.setFixedWidth(_Mock.W)
        v.addWidget(self.lbl_text)
        self.stack = QStackedWidget()
        for _t, _x, mock in self.steps:
            self.stack.addWidget(mock)
        v.addWidget(self.stack, 0, Qt.AlignHCenter)
        tr = QLabel(FOOTER)
        tr.setWordWrap(True)
        tr.setTextFormat(Qt.RichText)
        tr.setFixedWidth(_Mock.W)
        tr.setStyleSheet("font-size:11px;")
        v.addWidget(tr)
        row = QHBoxLayout()
        b = QPushButton("🌐 Открыть страницу GitHub")
        b.setToolTip(NEW_TOKEN_URL)
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(NEW_TOKEN_URL)))
        row.addWidget(b)
        b = QPushButton("⧉ Ссылку в буфер")
        b.clicked.connect(lambda: QGuiApplication.clipboard().setText(NEW_TOKEN_URL))
        row.addWidget(b)
        row.addStretch(1)
        self.btn_prev = QPushButton("◀ Назад")
        self.btn_prev.clicked.connect(lambda: self.go(-1))
        row.addWidget(self.btn_prev)
        self.lbl_n = QLabel()
        row.addWidget(self.lbl_n)
        self.btn_next = QPushButton("Далее ▶")
        self.btn_next.clicked.connect(lambda: self.go(+1))
        row.addWidget(self.btn_next)
        v.addLayout(row)
        self.go(max(0, min(len(self.steps) - 1, int(step or 0))))

    def go(self, d):
        i = max(0, min(len(self.steps) - 1, self.stack.currentIndex() + d))
        self.stack.setCurrentIndex(i)
        title, text, _m = self.steps[i]
        self.lbl_head.setText(f"Шаг {i + 1}. {title}")
        self.lbl_text.setText(text)
        self.lbl_n.setText(f" {i + 1} / {len(self.steps)} ")
        self.btn_prev.setEnabled(i > 0)
        last = i == len(self.steps) - 1
        self.btn_next.setText("Готово ✓" if last else "Далее ▶")
        try:
            self.btn_next.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.btn_next.clicked.connect(self.accept if last else (lambda: self.go(+1)))

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Right, Qt.Key_PageDown):
            self.go(+1)
        elif ev.key() in (Qt.Key_Left, Qt.Key_PageUp):
            self.go(-1)
        else:
            super().keyPressEvent(ev)


def show_token_help(parent=None, owner="romzespra-collab", repo="Smart_BMS",
                    app_name="Smart_BMS", step=0, target=None):
    dlg = TokenHelpDialog(parent, owner, repo, app_name, step, target)
    dlg.exec()
