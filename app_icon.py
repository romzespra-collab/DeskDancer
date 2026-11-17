"""app_icon.py  v1.2.0 — общий модуль: значок программы (окно, панель задач, .ico, ярлыки).

Набор рисунков (QPainter, без файлов картинок) × палитра × форма, или своя картинка.
Выбор хранится в app_icon.json рядом с программой (обновление с GitHub *.json не трогает).
<имя>.ico пишется рядом с программой и переписывается при запуске, если не совпадает
с выбором (обновление могло вернуть значок из репозитория). Ярлыкам на программу
(папка программы, рабочий стол, меню «Пуск», панель задач) ставится этот .ico.
Окно выбора — app_icon_qt.py. Встроенная база значков (без интернета) — app_icon_pack.dat
рядом с модулем (собирается app_icon_pack_build.pyw); нет файла — только рисунки.

Подключение:
    import app_icon
    icons = app_icon.AppIcon("my_app", APP_ROOT, title="My App",
                             target=APP_ROOT / "my_app.pyw",          # что запускают ярлыки
                             default={"kind": "glyph", "glyph": "gear",
                                      "colors": ["#4f8cff", "#6c3fd1"], "shape": "rounded"})
    icons.ensure()                         # при запуске: .ico под выбор
    app.setWindowIcon(icons.icon())

Журнал:
v1.2.0: встроенная база ~370 значков с русскими названиями и поиском без интернета
      (Material Design Icons — Apache 2.0, бренды Simple Icons — CC0); оформление:
      заливка градиент / ровная, форма «Без фона» (рисунок — градиентом), цвет рисунка
      (авто / белый / тёмный / свой), размер рисунка 60…130 %; 24 палитры; значок сайта
      (по адресу: apple-touch-icon, manifest, favicon — самый крупный); из .ico — самый
      крупный кадр; недавние значки (16) в app_icon.json; список наборов Iconify —
      в кэше на 7 дней (нет связи — из кэша); поиск Iconify — фильтр одноцветные/цветные.
v1.1.0: своя картинка — ещё SVG (файл, буфер обмена), вставка из буфера и перетаскивание
      (картинка, файл, ссылка — скачивается, TLS проверяется); «Фон под значком» для
      своей картинки; поиск значков в интернете — Iconify (открытые наборы, категории,
      лицензия набора), одноцветные — цветом палитры.
v1.0.0: первая версия: 30 рисунков + буква, 16 палитр + свой цвет, 3 формы, своя
      картинка (PNG/JPG/ICO/BMP); .ico 16…256; ярлыки — значок через WScript.Shell.
"""
import base64
import copy
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import (QColor, QFont, QIcon, QImage, QImageReader, QLinearGradient, QPainter, QPainterPath,
                           QPainterPathStroker, QPixmap, QPolygonF, QTransform)
from PySide6.QtSvg import QSvgRenderer

VERSION = "1.2.0"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
CONFIG_NAME = "app_icon.json"

PALETTES = [
    ("Синий", "#4f8cff", "#6c3fd1"), ("Небо", "#36c2ff", "#2f6fe4"),
    ("Бирюза", "#2ec4b6", "#147a8c"), ("Зелёный", "#3ad07a", "#17804a"),
    ("Лайм", "#c6e75a", "#5cb85c"), ("Солнце", "#ffd166", "#f4a261"),
    ("Оранжевый", "#ffa94d", "#e8590c"), ("Красный", "#ff5d6c", "#c9184a"),
    ("Малина", "#ff6fa8", "#b5179e"), ("Фиолетовый", "#a77bff", "#5a2fc2"),
    ("Индиго", "#5c7cfa", "#3b2a8f"), ("Шоколад", "#c49a6c", "#7a4a24"),
    ("Графит", "#6b7280", "#2b2f38"), ("Ночь", "#2a3a4a", "#0f1720"),
    ("Smart", "#00a0e9", "#1b2733"), ("Светлый", "#f3f4f7", "#c8ccd6"),
    ("Мята", "#5eead4", "#0d9488"), ("Лес", "#74c69d", "#1b4332"),
    ("Океан", "#00b4d8", "#023e8a"), ("Закат", "#ff7e5f", "#7b2ff7"),
    ("Вишня", "#e5383b", "#660708"), ("Лаванда", "#c3b1e1", "#7b5ea7"),
    ("Песок", "#e9c46a", "#b08968"), ("Чёрный", "#3a3a3a", "#000000"),
]
SHAPES = [("rounded", "Скруглённый"), ("circle", "Круг"), ("square", "Квадрат"), ("none", "Без фона")]
FILLS = [("gradient", "Градиент"), ("solid", "Ровная")]
INKS = [("", "Авто"), ("#ffffff", "Белый"), ("#1c2230", "Тёмный")]
SCALE_MIN, SCALE_MAX = 60, 130
DEFAULT = {"kind": "glyph", "glyph": "bubble", "colors": ["#4f8cff", "#6c3fd1"],
           "shape": "rounded", "text": "A"}


# ------------------------------------------------------------------ рисунки (поле 100×100)
def _rr(x, y, w, h, r=0.0):
    p = QPainterPath()
    if r:
        p.addRoundedRect(QRectF(x, y, w, h), r, r)
    else:
        p.addRect(QRectF(x, y, w, h))
    return p


def _c(cx, cy, r):
    p = QPainterPath()
    p.addEllipse(QPointF(cx, cy), r, r)
    return p


def _ell(x, y, w, h):
    p = QPainterPath()
    p.addEllipse(QRectF(x, y, w, h))
    return p


def _poly(*pts):
    p = QPainterPath()
    p.addPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
    p.closeSubpath()
    return p


def _line(*pts):
    p = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        p.lineTo(QPointF(*pt))
    return p


def _arc(cx, cy, r, start, sweep):
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
    p = QPainterPath()
    p.arcMoveTo(rect, start)
    p.arcTo(rect, start, sweep)
    return p


def _stroke(path, w, cap=Qt.RoundCap):
    st = QPainterPathStroker()
    st.setWidth(w)
    st.setCapStyle(cap)
    st.setJoinStyle(Qt.RoundJoin)
    return st.createStroke(path)


def _u(*paths):
    r = QPainterPath()
    for x in paths:
        r = r.united(x)
    return r


def _round(path, w=8):
    """Скруглить углы многоугольника."""
    return path.united(_stroke(path, w))


def _g_bubble(size):
    g = _u(_ell(14, 16, 72, 54), _poly((30, 60), (22, 86), (48, 66)))
    if size >= 20:
        g = g.subtracted(_u(*(_c(x, 43, 5.5) for x in (34, 50, 66))))
    return g


def _g_mic(_):
    return _u(_rr(38, 12, 24, 44, 12), _stroke(_arc(50, 46, 22, 180, 180), 6),
              _rr(47, 66, 6, 12), _rr(36, 77, 28, 6, 3))


def _g_gear(_):
    g = _c(50, 50, 27)
    for i in range(8):
        t = QTransform()
        t.translate(50, 50)
        t.rotate(i * 45)
        g = g.united(t.map(_rr(-7, -39, 14, 18, 3)))
    return g.subtracted(_c(50, 50, 11))


def _g_shield(_):
    p = QPainterPath(QPointF(50, 10))
    p.lineTo(82, 22)
    p.lineTo(82, 46)
    p.cubicTo(82, 68, 68, 82, 50, 90)
    p.cubicTo(32, 82, 18, 68, 18, 46)
    p.lineTo(18, 22)
    p.closeSubpath()
    return p.subtracted(_stroke(_line((36, 50), (46, 61), (65, 39)), 8))


def _g_folder(_):
    return _u(_rr(12, 20, 34, 16, 4), _rr(12, 28, 76, 54, 6)).subtracted(_rr(12, 36, 76, 3))


def _g_bolt(_):
    return _round(_poly((58, 10), (26, 56), (47, 56), (40, 90), (74, 42), (54, 42), (63, 10)), 4)


def _g_play(_):
    return _round(_poly((34, 20), (34, 80), (82, 50)), 10)


def _g_note(_):
    return _u(_ell(18, 62, 24, 18), _ell(54, 54, 24, 18), _rr(37, 22, 5, 50), _rr(73, 14, 5, 50),
              _poly((37, 22), (78, 12), (78, 24), (37, 34)))


def _g_camera(_):
    body = _u(_rr(12, 30, 76, 50, 9), _rr(34, 20, 30, 16, 4))
    return _u(body.subtracted(_u(_c(50, 55, 16), _c(76, 40, 3))), _c(50, 55, 9))


def _g_monitor(_):
    return _u(_rr(12, 18, 76, 50, 6).subtracted(_rr(19, 25, 62, 36, 2)),
              _rr(45, 68, 10, 10), _rr(32, 77, 36, 6, 3))


def _g_chip(_):
    g = _rr(28, 28, 44, 44, 5)
    for k in range(4):
        x = 35 + k * 10
        g = _u(g, _rr(x - 2.5, 16, 5, 14, 1.5), _rr(x - 2.5, 70, 5, 14, 1.5),
               _rr(16, x - 2.5, 14, 5, 1.5), _rr(70, x - 2.5, 14, 5, 1.5))
    return g.subtracted(_rr(40, 40, 20, 20, 3))


def _g_wifi(_):
    return _u(*(_stroke(_arc(50, 76, r, 45, 90), 9) for r in (17, 33, 49)), _c(50, 76, 7))


def _g_download(_):
    return _u(_rr(44, 10, 12, 36, 3), _round(_poly((28, 42), (72, 42), (50, 66)), 6),
              _stroke(_line((16, 62), (16, 84), (84, 84), (84, 62)), 8))


def _g_cloud(_):
    return _u(_c(36, 58, 16), _c(56, 46, 22), _c(72, 60, 14), _rr(20, 56, 66, 18, 9))


def _g_star(_):
    import math
    pts = []
    for i in range(10):
        r = 40 if i % 2 == 0 else 17
        a = math.radians(-90 + i * 36)
        pts.append((50 + r * math.cos(a), 54 + r * math.sin(a)))
    return _round(_poly(*pts), 5)


def _g_heart(_):
    p = QPainterPath(QPointF(50, 86))
    p.cubicTo(14, 62, 8, 38, 22, 24)
    p.cubicTo(34, 12, 48, 18, 50, 32)
    p.cubicTo(52, 18, 66, 12, 78, 24)
    p.cubicTo(92, 38, 86, 62, 50, 86)
    p.closeSubpath()
    return p


def _g_book(_):
    return _u(_round(_poly((12, 24), (46, 30), (46, 84), (12, 78)), 4),
              _round(_poly((54, 30), (88, 24), (88, 78), (54, 84)), 4))


def _g_pencil(_):
    t = QTransform()
    t.translate(50, 52)
    t.rotate(45)
    g = _u(_rr(-10, -42, 20, 58, 3), _poly((-10, 16), (10, 16), (0, 36))).subtracted(_rr(-10, -30, 20, 4))
    return t.map(g)


def _g_search(_):
    return _u(_c(42, 42, 25).subtracted(_c(42, 42, 15)), _stroke(_line((60, 60), (82, 82)), 13))


def _g_terminal(_):
    return _rr(10, 18, 80, 64, 9).subtracted(
        _u(_stroke(_line((26, 38), (38, 50), (26, 62)), 7), _rr(44, 58, 24, 6, 3)))


def _g_battery(_):
    return _u(_rr(12, 30, 68, 40, 7).subtracted(_rr(19, 37, 54, 26, 3)), _rr(82, 42, 7, 16, 3),
              _rr(23, 41, 30, 18, 2))


def _g_home(_):
    return _round(_poly((50, 14), (88, 48), (78, 48), (78, 86), (22, 86), (22, 48), (12, 48)),
                  4).subtracted(_rr(42, 62, 16, 26, 2))


def _g_flame(_):
    p = QPainterPath(QPointF(50, 8))
    p.cubicTo(56, 26, 80, 38, 78, 62)
    p.cubicTo(76, 80, 62, 90, 50, 90)
    p.cubicTo(38, 90, 22, 80, 22, 62)
    p.cubicTo(22, 48, 32, 40, 36, 28)
    p.cubicTo(40, 38, 44, 42, 48, 44)
    p.cubicTo(50, 32, 54, 20, 50, 8)
    p.closeSubpath()
    d = QPainterPath(QPointF(50, 56))
    d.cubicTo(58, 64, 62, 70, 60, 76)
    d.cubicTo(58, 84, 42, 84, 40, 76)
    d.cubicTo(38, 70, 44, 64, 50, 56)
    d.closeSubpath()
    return p.subtracted(d)


def _g_film(_):
    holes = [_rr(34, 18, 32, 28, 2), _rr(34, 54, 32, 28, 2)]
    for y in (15, 29, 43, 57, 71):
        holes += [_rr(25, y, 6, 8, 1.5), _rr(69, y, 6, 8, 1.5)]
    return _rr(22, 10, 56, 80, 5).subtracted(_u(*holes))


def _g_headphones(_):
    return _u(_stroke(_arc(50, 52, 34, 180, -180), 8), _rr(12, 50, 20, 32, 7), _rr(68, 50, 20, 32, 7))


def _g_sun(_):
    import math
    rays = []
    for i in range(8):
        a = math.radians(i * 45)
        rays.append(_stroke(_line((50 + 27 * math.cos(a), 50 + 27 * math.sin(a)),
                                  (50 + 39 * math.cos(a), 50 + 39 * math.sin(a))), 7))
    return _u(_c(50, 50, 17), *rays)


def _g_moon(_):
    return _c(46, 52, 34).subtracted(_c(64, 38, 29))


def _g_lock(_):
    sh = QPainterPath(QPointF(34, 46))
    sh.lineTo(34, 34)
    sh.arcTo(QRectF(34, 16, 32, 36), 180, -180)
    sh.lineTo(66, 46)
    return _u(_stroke(sh, 8), _rr(22, 44, 56, 42, 7)).subtracted(
        _u(_c(50, 61, 6), _rr(47.5, 62, 5, 12, 2)))


def _g_chart(_):
    return _u(_rr(18, 52, 15, 30, 3), _rr(42, 36, 15, 46, 3), _rr(66, 18, 15, 64, 3),
              _rr(12, 84, 76, 5, 2))


def _g_globe(_):
    return _u(_c(50, 50, 37).subtracted(_c(50, 50, 31)),
              _stroke(_ell(35, 14, 30, 72), 5), _rr(14, 47.5, 72, 5),
              _stroke(_line((25, 32), (75, 32)), 5), _stroke(_line((25, 68), (75, 68)), 5))


def _g_letter(_, text="A"):
    text = (text or "A").strip()[:2] or "A"
    f = QFont("Segoe UI")
    f.setPixelSize(100)
    f.setBold(True)
    p = QPainterPath()
    p.addText(QPointF(0, 0), f, text)
    b = p.boundingRect()
    k = min(64 / max(b.width(), 1), 60 / max(b.height(), 1))
    t = QTransform()
    t.translate(50, 50)
    t.scale(k, k)
    t.translate(-b.center().x(), -b.center().y())
    return t.map(p)


GLYPHS = [
    ("bubble", "Реплика", _g_bubble), ("mic", "Микрофон", _g_mic), ("gear", "Шестерёнка", _g_gear),
    ("shield", "Щит", _g_shield), ("folder", "Папка", _g_folder), ("bolt", "Молния", _g_bolt),
    ("play", "Плей", _g_play), ("note", "Нота", _g_note), ("camera", "Камера", _g_camera),
    ("monitor", "Монитор", _g_monitor), ("chip", "Микросхема", _g_chip), ("wifi", "Сигнал", _g_wifi),
    ("download", "Загрузка", _g_download), ("cloud", "Облако", _g_cloud), ("star", "Звезда", _g_star),
    ("heart", "Сердце", _g_heart), ("book", "Книга", _g_book), ("pencil", "Карандаш", _g_pencil),
    ("search", "Лупа", _g_search), ("terminal", "Консоль", _g_terminal), ("battery", "Батарея", _g_battery),
    ("home", "Дом", _g_home), ("flame", "Огонь", _g_flame), ("film", "Плёнка", _g_film),
    ("headphones", "Наушники", _g_headphones), ("sun", "Солнце", _g_sun), ("moon", "Луна", _g_moon),
    ("lock", "Замок", _g_lock), ("chart", "Диаграмма", _g_chart), ("globe", "Глобус", _g_globe),
    ("letter", "Буква", _g_letter),
]
_GLYPH = {k: f for k, _, f in GLYPHS}


# ------------------------------------------------------------------ выбор и картинка
def _hex(c):
    return isinstance(c, str) and QColor(c).isValid() and c.startswith("#") and len(c) == 7


def clean(spec, default=DEFAULT):
    """Проверенный выбор: всё кривое — из default."""
    d = copy.deepcopy(default)
    s = spec if isinstance(spec, dict) else {}
    out = {"kind": s.get("kind") if s.get("kind") in ("glyph", "image", "svg") else d.get("kind", "glyph"),
           "glyph": s.get("glyph") if s.get("glyph") in _GLYPH else d.get("glyph", "bubble"),
           "colors": d.get("colors", DEFAULT["colors"]),
           "shape": s.get("shape") if s.get("shape") in dict(SHAPES) else d.get("shape", "rounded"),
           "text": str(s.get("text") or d.get("text") or "A")[:2],
           "fill": s.get("fill") if s.get("fill") in dict(FILLS) else d.get("fill", "gradient"),
           "ink": s.get("ink") if _hex(s.get("ink")) else "",
           "scale": d.get("scale", 100)}
    try:
        out["scale"] = max(SCALE_MIN, min(SCALE_MAX, int(s.get("scale", out["scale"]))))
    except (TypeError, ValueError):
        pass
    cols = s.get("colors")
    if isinstance(cols, list) and len(cols) == 2 and all(_hex(c) for c in cols):
        out["colors"] = [c.lower() for c in cols]
    if out["kind"] == "image":
        png = s.get("png")
        if isinstance(png, str) and png:
            out["png"] = png
        else:
            out["kind"] = "glyph"
    if out["kind"] == "svg":
        svg = s.get("svg")
        if isinstance(svg, str) and "<svg" in svg[:400] and len(svg) < 400_000:
            out["svg"] = svg
        else:
            out["kind"] = "glyph"
    if out["kind"] in ("image", "svg"):
        out["bg"] = bool(s.get("bg", False))
        for k in ("src", "lic"):
            if isinstance(s.get(k), str) and s[k]:
                out[k] = s[k][:300]
    return out


def svg_is_mono(svg):
    """Одноцветный значок (currentColor) — красится цветом палитры."""
    return "currentcolor" in (svg or "").lower()


def svg_image(svg, size, color=None, pad=0.0):
    """SVG → QImage size×size (пропорции сохраняются); currentColor → color."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    data = re.sub("currentcolor", color, svg, flags=re.I) if color else svg
    r = QSvgRenderer(QByteArray(data.encode("utf-8")))
    if not r.isValid():
        return img
    vb = r.viewBoxF()
    w, h = (vb.width(), vb.height()) if vb.width() > 0 and vb.height() > 0 else (1.0, 1.0)
    room = size * (1 - 2 * pad)
    k = room / max(w, h)
    rect = QRectF((size - w * k) / 2, (size - h * k) / 2, w * k, h * k)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p, rect)
    p.end()
    return img


def ink_for(colors, fill="gradient"):
    """Цвет рисунка: на светлом фоне — тёмный, иначе белый."""
    cs = [QColor(colors[0])] if fill == "solid" else [QColor(colors[0]), QColor(colors[1])]
    lum = sum(0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue() for c in cs) / len(cs)
    return QColor("#1c2230") if lum > 170 else QColor("#ffffff")


def _shape_path(shape, s):
    p = QPainterPath()
    r = QRectF(0, 0, s, s)
    if shape == "circle":
        p.addEllipse(r)
    elif shape == "square":
        p.addRoundedRect(r, s * 0.06, s * 0.06)
    else:
        p.addRoundedRect(r, s * 0.22, s * 0.22)
    return p


def _decode_png(b64):
    img = QImage()
    try:
        img.loadFromData(QByteArray(base64.b64decode(b64)), "PNG")
    except Exception:
        pass
    return img


def _brush(spec, size):
    """Заливка фона (или рисунка «без фона»): градиент или ровный цвет."""
    if spec.get("fill") == "solid":
        return QColor(spec["colors"][0])
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor(spec["colors"][0]))
    g.setColorAt(1, QColor(spec["colors"][1]))
    return g


def _glyph_layer(spec, size, room):
    """Рисунок (белый) в квадрате size: занимает долю room по центру."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    if spec["kind"] == "glyph":
        f = _GLYPH[spec["glyph"]]
        path = f(size, spec["text"]) if spec["glyph"] == "letter" else f(size)
        k = size / 100.0 * room
        p.translate(size * (1 - room) / 2, size * (1 - room) / 2)
        p.scale(k, k)
        p.fillPath(path, QColor("#ffffff"))
    else:
        mono = svg_is_mono(spec["svg"])
        p.drawImage(0, 0, svg_image(spec["svg"], size, "#ffffff" if mono else None, (1 - room) / 2))
    p.end()
    return img


def _tint(img, brush, size):
    """Покрасить непрозрачное в img кистью (цвет или градиент)."""
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(QRectF(0, 0, size, size), brush)
    p.end()
    return img


def render(spec, size):
    """QPixmap size×size с прозрачным фоном."""
    spec = clean(spec)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    kind, shape_key = spec["kind"], spec["shape"]
    shape = _shape_path(shape_key, size)
    brush = _brush(spec, size)
    has_bg = shape_key != "none" and (kind == "glyph" or spec.get("bg"))
    scale = spec["scale"] / 100.0
    if has_bg:
        p.setPen(Qt.NoPen)
        p.setBrush(brush)
        p.drawPath(shape)
    if kind == "image":
        img = _decode_png(spec["png"])
        if not img.isNull():
            if not has_bg and shape_key != "none":
                p.setClipPath(shape)
            base = (0.68 if shape_key == "circle" else 0.72) if has_bg else 1.0
            side = size * min(base * scale, 1.3)
            m = (size - side) / 2
            p.drawImage(QRectF(m, m, side, side), img)
        p.end()
        return pm
    # рисунок или SVG: доля поля под рисунок
    if kind == "glyph":
        base = 0.86 if shape_key == "circle" else 1.0
    else:
        base = (0.6 if shape_key == "circle" else 0.68) if has_bg else 0.92
    layer = _glyph_layer(spec, size, min(base * scale, 1.25))
    mono = kind == "glyph" or svg_is_mono(spec["svg"])
    if mono:
        if has_bg:
            _tint(layer, QColor(spec["ink"]) if spec["ink"] else ink_for(spec["colors"], spec["fill"]), size)
        else:
            _tint(layer, QColor(spec["ink"]) if spec["ink"] else brush, size)
    p.drawImage(0, 0, layer)
    p.end()
    return pm


def image_to_png(path, max_side=256):
    """Своя картинка (файл или QImage) → квадрат по центру, 256×256, PNG в base64."""
    img = path if isinstance(path, QImage) else QImage(str(path))
    if img.isNull():
        raise ValueError("Не удалось прочитать картинку (PNG, JPG, ICO, BMP, SVG).")
    side = min(img.width(), img.height())
    img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
    img = img.scaled(max_side, max_side, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return base64.b64encode(_png_bytes(img)).decode()


def picture_spec(data, name=""):
    """Байты картинки (файл, буфер, скачанное) → часть выбора: {"kind": "svg"|"image", …}."""
    head = data[:2000].lstrip().lower()
    if b"<svg" in head or name.lower().endswith(".svg"):
        svg = data.decode("utf-8", "replace")
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        if not r.isValid():
            raise ValueError("SVG не читается.")
        return {"kind": "svg", "svg": svg, "bg": svg_is_mono(svg)}
    img = largest_frame(data)
    if img.isNull():
        raise ValueError("Это не картинка (PNG, JPG, ICO, BMP, SVG).")
    return {"kind": "image", "png": image_to_png(img), "bg": False}


def largest_frame(data):
    """Картинка из байтов; у .ico и подобных — самый крупный кадр."""
    buf = QBuffer()
    buf.setData(QByteArray(data))
    buf.open(QIODevice.ReadOnly)
    rd = QImageReader(buf)
    best = QImage()
    for _ in range(max(1, rd.imageCount())):
        img = rd.read()
        if not img.isNull() and img.width() * img.height() > best.width() * best.height():
            best = img
        if not rd.jumpToNextImage():
            break
    buf.close()
    if best.isNull():
        best.loadFromData(QByteArray(data))
    return best


def picture_from_file(path):
    with open(path, "rb") as f:
        return picture_spec(f.read(20_000_001)[:20_000_000], str(path))


MAX_DOWNLOAD = 8_000_000


def fetch_url(url, timeout=20):
    """Скачать картинку по ссылке (http/https, TLS проверяется). bytes."""
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Ссылка должна начинаться с http:// или https://")
    req = urllib.request.Request(url, headers={"User-Agent": f"app_icon/{VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("Файл больше 8 МБ — это не значок.")
    return data


def _site_url(text):
    t = (text or "").strip()
    if not t:
        raise ValueError("Введите адрес сайта, например youtube.com")
    if "://" not in t:
        t = "https://" + t
    u = urllib.parse.urlparse(t)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise ValueError("Адрес сайта не похож на сайт.")
    return f"{u.scheme}://{u.netloc}/"


def site_icon_candidates(html, base):
    """Ссылки на значки сайта из HTML: [(оценка, url)] — крупнее и SVG выше."""
    out = []
    for tag in re.findall(r"<link\b[^>]*>", html or "", flags=re.I):
        attrs = dict((k.lower(), v) for k, _, v in re.findall(r'([\w:-]+)\s*=\s*(["\'])(.*?)\2', tag))
        rel = attrs.get("rel", "").lower()
        href = attrs.get("href")
        if not href or not any(x in rel for x in ("icon", "apple-touch-icon", "manifest", "mask-icon")):
            continue
        url = urllib.parse.urljoin(base, href.strip())
        if "manifest" in rel:
            out.append((5000, url))            # manifest — разобрать отдельно
            continue
        size = 0
        for m in re.findall(r"(\d+)x(\d+)", attrs.get("sizes", "")):
            size = max(size, int(m[0]))
        if "apple-touch-icon" in rel:
            size = size or 180
        if url.lower().split("?")[0].endswith(".svg") or "svg" in attrs.get("type", ""):
            size = 1000
        if "mask-icon" in rel:
            size = 1                           # одноцветный силуэт Safari — на крайний случай
        out.append((size or 32, url))
    return sorted(out, key=lambda x: -x[0])


def site_icon(text, timeout=15):
    """Значок сайта по адресу: SVG / apple-touch-icon / manifest / favicon — самый крупный.
    → часть выбора (picture_spec)."""
    base = _site_url(text)
    try:
        html = fetch_url(base, timeout).decode("utf-8", "replace")
    except Exception:
        html = ""
    cands = site_icon_candidates(html, base)
    urls = []
    for score, url in cands:
        if score == 5000:                       # manifest.json → icons[]
            try:
                man = json.loads(fetch_url(url, timeout))
                icons = [i for i in (man.get("icons") or [])           # «monochrome» — силуэт, не он
                         if "monochrome" not in str(i.get("purpose", ""))]
                icons = sorted(icons, key=lambda i: -max(
                    [int(x.split("x")[0]) for x in str(i.get("sizes", "0x0")).split() if "x" in x] or [0]))
                urls += [urllib.parse.urljoin(url, i["src"]) for i in icons[:2] if i.get("src")]
            except Exception:
                pass
        else:
            urls.append(url)
    urls += [base + "apple-touch-icon.png", base + "favicon.ico"]
    seen, last = set(), None
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        try:
            part = picture_spec(fetch_url(url, timeout), urllib.parse.urlparse(url).path)
            if part["kind"] == "image":
                img = _decode_png(part["png"])
                if img.isNull():
                    continue
            part["src"] = url
            return part
        except Exception as e:
            last = e
    raise ValueError(f"Значок сайта не найден ({last})" if last else "Значок сайта не найден.")


# ------------------------------------------------------------------ встроенная база (без интернета)
PACK_NAME = "app_icon_pack.dat"     # JSON; не .json — обновление с GitHub *.json не ставит (настройки)
_PACK = {}


def load_pack(*dirs):
    """Встроенная база: {"sets", "categories": [{"name", "icons": [[id, ru, слова, svg]]}]}.
    Ищется рядом с модулем и в dirs; нет — пустая база."""
    if "data" in _PACK:
        return _PACK["data"]
    data = {"sets": {}, "categories": []}
    for d in (Path(__file__).resolve().parent, *map(Path, dirs)):
        fn = d / PACK_NAME
        try:
            with open(fn, encoding="utf-8") as f:
                got = json.load(f)
            if isinstance(got, dict) and isinstance(got.get("categories"), list):
                data = got
                break
        except (OSError, ValueError):
            continue
    _PACK["data"] = data
    return data


def pack_license(icon_id, pack=None):
    pack = pack or load_pack()
    info = (pack.get("sets") or {}).get(icon_id.split(":", 1)[0], {})
    if not info:
        return ""
    lic = info.get("license", "")
    if info.get("url"):
        lic = f'<a href="{info["url"]}">{lic}</a>'
    return f"{info.get('name', '')} · {lic}" + (f" · {info['note']}" if info.get("note") else "")


def pack_find(query, pack=None):
    """Поиск по встроенной базе: русское название, слова, английское имя. [(id, ru, svg)]"""
    pack = pack or load_pack()
    words = [w for w in (query or "").lower().replace("ё", "е").split() if w]
    if not words:
        return []
    out = []
    for c in pack.get("categories", []):
        for icon_id, ru, extra, svg in c["icons"]:
            hay = f"{ru} {extra} {icon_id.split(':', 1)[-1].replace('-', ' ')}".lower().replace("ё", "е")
            if all(w in hay for w in words):
                out.append((icon_id, ru, svg))
    return out


def svg_compact(svg):
    """SVG для базы: без width/height (размер задаёт viewBox)."""
    return re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)


# ------------------------------------------------------------------ Iconify: открытые наборы значков
API_HOSTS = ("https://api.iconify.design", "https://api.simplesvg.com", "https://api.unisvg.com")
CATEGORY_RU = {
    "Material": "Material", "UI 24px": "Интерфейс 24px", "UI 16px / 32px": "Интерфейс 16 / 32px",
    "UI Other / Mixed Grid": "Интерфейс — разное", "UI Multicolor": "Интерфейс цветной",
    "Logos": "Логотипы", "Emoji": "Эмодзи", "Flags": "Флаги", "Location": "Карты и места",
    "Thematic": "Тематические", "Programming": "Программирование", "Holiday / Seasonal": "Праздники",
    "High Detail": "Детальные", "High Detail Multicolor": "Детальные цветные", "Apps": "Приложения",
    "Archive / Unmaintained": "Архив",
}
# поиск у Iconify — по-английски; частые слова переводятся сами
RU_EN = {
    "ютуб": "youtube", "ютюб": "youtube", "телеграм": "telegram", "гитхаб": "github", "виндовс": "windows",
    "микрофон": "microphone", "камера": "camera", "видео": "video", "фото": "photo", "музыка": "music",
    "нота": "music note", "звук": "sound", "наушники": "headphones", "динамик": "speaker", "радио": "radio",
    "дом": "home", "папка": "folder", "файл": "file", "документ": "document", "книга": "book",
    "комикс": "comic", "облако": "cloud", "загрузка": "download", "скачать": "download", "обновление": "update",
    "настройки": "settings", "шестеренка": "gear", "шестерёнка": "gear", "щит": "shield", "замок": "lock",
    "ключ": "key", "антивирус": "shield virus", "сеть": "network", "интернет": "internet", "вайфай": "wifi",
    "антенна": "antenna", "сигнал": "signal", "батарея": "battery", "аккумулятор": "battery",
    "молния": "lightning", "энергия": "energy", "солнце": "sun", "луна": "moon", "звезда": "star",
    "сердце": "heart", "огонь": "fire", "вентилятор": "fan", "кулер": "fan", "термометр": "thermometer",
    "монитор": "monitor", "компьютер": "computer", "ноутбук": "laptop", "телефон": "phone",
    "чип": "chip", "плата": "circuit board", "процессор": "cpu", "консоль": "terminal", "код": "code",
    "поиск": "search", "лупа": "magnifier", "карандаш": "pencil", "кисть": "brush", "палитра": "palette",
    "часы": "clock", "календарь": "calendar", "почта": "mail", "чат": "chat", "сообщение": "message",
    "пользователь": "user", "человек": "person", "робот": "robot", "игра": "game", "джойстик": "gamepad",
    "деньги": "money", "корзина": "cart", "график": "chart", "диаграмма": "chart", "карта": "map",
    "машина": "car", "самолет": "airplane", "самолёт": "airplane", "ракета": "rocket", "глобус": "globe",
    "фильм": "film", "плеер": "player", "плей": "play", "запись": "record", "эфир": "broadcast",
    "трансляция": "stream", "экран": "screen", "принтер": "printer", "мусор": "trash", "корзинка": "basket",
}


def query_en(q):
    """Русские слова → английские (поиск Iconify — по-английски): словарь, потом названия
    встроенной базы («Вентилятор» → fan)."""
    out = []
    for w in (q or "").lower().replace("ё", "е").split():
        if w in RU_EN:
            out.append(RU_EN[w])
            continue
        if re.search("[а-я]", w):
            for c in load_pack().get("categories", []):
                hit = next((i for i, ru, _, _ in c["icons"] if ru.lower().replace("ё", "е") == w), None)
                if hit:
                    w = hit.split(":", 1)[-1].replace("-", " ")
                    break
        out.append(w)
    return " ".join(out).strip()


def _api(path, timeout=15):
    """GET к Iconify; нет связи — следующее зеркало. bytes."""
    last = None
    for host in API_HOSTS:
        req = urllib.request.Request(host + path, headers={"User-Agent": f"app_icon/{VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(MAX_DOWNLOAD)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ValueError("Не найдено.") from e
            last = e
        except (urllib.error.URLError, OSError) as e:
            last = e
    raise ConnectionError(f"Нет связи с сервисом значков: {last}")


CACHE_NAME = "app_icon_cache.json"
CACHE_DAYS = 7


def iconify_collections(cache_dir=None):
    """{prefix: {name, total, category, license, author, palette, hidden?}}; кэш на 7 дней
    в cache_dir/app_icon_cache.json; нет связи — из кэша, даже старого."""
    fn = Path(cache_dir) / CACHE_NAME if cache_dir else None
    cached = None
    if fn and fn.exists():
        try:
            with open(fn, encoding="utf-8") as f:
                cached = json.load(f)
            if time.time() - cached.get("time", 0) < CACHE_DAYS * 86400 and cached.get("collections"):
                return cached["collections"]
        except (OSError, ValueError):
            cached = None
    try:
        cols = json.loads(_api("/collections"))
    except Exception:
        if cached and cached.get("collections"):
            return cached["collections"]
        raise
    if fn:
        try:
            _write(fn, json.dumps({"time": time.time(), "collections": cols}, ensure_ascii=False).encode("utf-8"))
        except OSError:
            pass
    return cols


def iconify_search(query, start=0, limit=96, category=None, prefixes=None):
    """Имена «набор:значок» по запросу."""
    q = {"query": query_en(query), "limit": max(32, min(limit, 999)), "start": start}
    if category:
        q["category"] = category
    if prefixes:
        q["prefixes"] = ",".join(prefixes)
    d = json.loads(_api("/search?" + urllib.parse.urlencode(q)))
    return list(d.get("icons") or [])


def iconify_set_icons(prefix):
    """Все имена набора («набор:значок»), без скрытых."""
    d = json.loads(_api("/collection?" + urllib.parse.urlencode({"prefix": prefix})))
    names = list(d.get("uncategorized") or [])
    for lst in (d.get("categories") or {}).values():
        names += lst
    hidden = set(d.get("hidden") or [])
    seen, out = set(), []
    for n in names:
        if n not in seen and n not in hidden:
            seen.add(n)
            out.append(f"{prefix}:{n}")
    return out


def svg_from_data(data, name):
    """SVG значка из ответа Iconify (/набор.json?icons=…)."""
    icons, aliases = data.get("icons") or {}, data.get("aliases") or {}
    extra = {}
    for _ in range(5):                       # псевдоним → исходный значок
        if name in icons:
            break
        a = aliases.get(name)
        if not a:
            return None
        extra = {**a, **extra}
        name = a.get("parent")
    ic = {**icons.get(name, {}), **{k: v for k, v in extra.items() if k != "parent"}}
    if "body" not in ic:
        return None
    w, h = ic.get("width", data.get("width", 16)), ic.get("height", data.get("height", 16))
    left, top = ic.get("left", data.get("left", 0)), ic.get("top", data.get("top", 0))
    body = ic["body"]
    tr = []
    if ic.get("hFlip"):
        tr.append(f"translate({w + 2 * left} 0) scale(-1 1)")
    if ic.get("vFlip"):
        tr.append(f"translate(0 {h + 2 * top}) scale(1 -1)")
    if ic.get("rotate"):
        tr.append(f"rotate({90 * int(ic['rotate'])} {left + w / 2} {top + h / 2})")
    if tr:
        body = f'<g transform="{" ".join(tr)}">{body}</g>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{left} {top} {w} {h}" '
            f'width="{w}" height="{h}">{body}</svg>')


def iconify_svgs(names):
    """{«набор:значок»: svg}; запросы пачками по наборам, параллельно."""
    groups = {}
    for full in names:
        if ":" in full:
            pre, n = full.split(":", 1)
            groups.setdefault(pre, []).append(n)
    jobs = []
    for pre, lst in groups.items():
        for i in range(0, len(lst), 80):
            jobs.append((pre, lst[i:i + 80]))

    def one(job):
        pre, lst = job
        q = urllib.parse.urlencode({"icons": ",".join(lst)})
        data = json.loads(_api(f"/{urllib.parse.quote(pre)}.json?{q}"))
        return {f"{pre}:{n}": svg_from_data(data, n) for n in lst}
    out = {}
    with ThreadPoolExecutor(6) as ex:
        for part in ex.map(one, jobs):
            out.update({k: v for k, v in part.items() if v})
    return out


def _png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def icon(spec):
    ic = QIcon()
    for n in SIZES:
        ic.addPixmap(render(spec, n))
    return ic


def ico_bytes(spec):
    """Файл .ico: все размеры SIZES, PNG внутри (Windows Vista+)."""
    import struct
    pngs = [_png_bytes(render(spec, n).toImage()) for n in SIZES]
    out = struct.pack("<HHH", 0, 1, len(SIZES))
    off = 6 + 16 * len(SIZES)
    for n, data in zip(SIZES, pngs):
        out += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), off)
        off += len(data)
    return out + b"".join(pngs)


# ------------------------------------------------------------------ файлы
def _replace(tmp, dst):
    """os.replace с повтором при WinError 5/32 (файл занят антивирусом или Проводником)."""
    for i in range(10):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError:
            if i == 9:
                raise
            time.sleep(0.2)


def _write(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    _replace(tmp, path)


RECENT_MAX = 16


def _same_key(spec):
    """Что считать «тем же значком» в недавних: рисунок (с буквой), SVG, картинка."""
    if spec.get("kind") == "glyph":
        return ("glyph", spec.get("glyph"), spec.get("text") if spec.get("glyph") == "letter" else "")
    return (spec.get("kind"), spec.get("src") or spec.get("svg", "")[:200] or spec.get("png", "")[:200])


class AppIcon:
    """Значок одной программы: выбор, .ico, ярлыки."""

    def __init__(self, name, root, title=None, target=None, default=None):
        self.name = name
        self.root = Path(root)
        self.title = title or name
        self.target = Path(target) if target else (Path(sys.executable) if getattr(sys, "frozen", False)
                                                   else self.root / f"{name}.pyw")
        self.default = clean(default or DEFAULT)
        self.cfg_file = self.root / CONFIG_NAME
        self.readonly = False              # битый app_icon.json без .bak — не перезаписывать
        self.recent = []                   # недавние значки (выборы), новые — первыми
        self.spec = self.load()

    @property
    def ico_path(self):
        return self.root / f"{self.name}.ico"

    # ---- выбор
    def load(self):
        for fn in (self.cfg_file, self.cfg_file.with_name(self.cfg_file.name + ".bak")):
            if not fn.exists():
                continue
            try:
                with open(fn, encoding="utf-8") as f:
                    data = json.load(f)
                self.recent = [clean(x, self.default) for x in (data.get("recent") or [])
                               if isinstance(x, dict)][:RECENT_MAX]
                return clean(data.get("spec"), self.default)
            except Exception:
                continue
        if self.cfg_file.exists():
            self.readonly = True
        return copy.deepcopy(self.default)

    def save(self, spec):
        self.spec = clean(spec, self.default)
        if self.readonly:
            raise OSError(f"{CONFIG_NAME} повреждён — не перезаписываю (исправьте или удалите его).")
        self._remember(self.spec)
        data = json.dumps({"version": 1, "spec": self.spec, "recent": self.recent},
                          ensure_ascii=False, indent=1).encode("utf-8")
        if self.cfg_file.exists():
            try:
                _write(self.cfg_file.with_name(self.cfg_file.name + ".bak"), self.cfg_file.read_bytes())
            except OSError:
                pass
        _write(self.cfg_file, data)

    def _remember(self, spec):
        """В недавние: тот же рисунок / картинка — одна запись, свежая — первой."""
        if len(spec.get("png", "")) > 200_000:
            return
        key = _same_key(spec)
        self.recent = [spec] + [x for x in self.recent if _same_key(x) != key]
        del self.recent[RECENT_MAX:]

    @property
    def cache_dir(self):
        return self.root

    def icon(self, spec=None):
        return icon(spec or self.spec)

    def pixmap(self, size, spec=None):
        return render(spec or self.spec, size)

    # ---- .ico
    def write_ico(self, spec=None):
        """Записать <имя>.ico, если он отличается. True — файл изменился."""
        data = ico_bytes(spec or self.spec)
        try:
            if self.ico_path.read_bytes() == data:
                return False
        except OSError:
            pass
        _write(self.ico_path, data)
        return True

    def ensure(self):
        """При запуске: .ico под выбор; изменился — Проводнику перечитать значки."""
        try:
            changed = self.write_ico()
        except OSError:
            return False
        if changed:
            refresh_shell()
        return changed

    def apply(self, spec):
        """Сохранить выбор и .ico (быстро, в окне). Ярлыки — fix_shortcuts() в потоке."""
        self.save(spec)
        self.write_ico()
        return self.icon()

    # ---- ярлыки (Windows)
    def fix_shortcuts(self, create_desktop=False):
        """Значок ярлыкам на программу. [(«ok»/«new»/«err», путь, текст ошибки)]."""
        if sys.platform != "win32":
            return []
        env = dict(os.environ, AI_TARGET=str(self.target), AI_ICO=str(self.ico_path),
                   AI_DIR=str(self.root), AI_TITLE=self.title, AI_NEWDESK="1" if create_desktop else "0")
        cmd = base64.b64encode(_PS.encode("utf-16-le")).decode()
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", cmd], env=env, capture_output=True, timeout=90,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode:
            raise RuntimeError(r.stderr.decode("utf-8", "replace").strip() or f"PowerShell: код {r.returncode}")
        done = []
        for line in r.stdout.decode("utf-8", "replace").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[0] in ("ok", "new", "err"):
                done.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
        refresh_shell([p for k, p, _ in done if k != "err"])
        return done


def refresh_shell(paths=()):
    """Проводнику: перечитать значки (ярлыки и кэш)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        sh = ctypes.windll.shell32
        for p in paths:
            sh.SHChangeNotify(0x00002000, 0x0005, ctypes.c_wchar_p(p), None)   # UPDATEITEM, PATHW
        sh.SHChangeNotify(0x08000000, 0x1000, None, None)                     # ASSOCCHANGED, FLUSH
    except Exception:
        pass
    try:                                    # Windows 10/11: сбросить кэш значков
        subprocess.Popen(["ie4uinit.exe", "-show"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


_PS = r"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$sh = New-Object -ComObject WScript.Shell
$app = $env:AI_TARGET; $ico = $env:AI_ICO; $dir = $env:AI_DIR
$desk = [Environment]::GetFolderPath('Desktop')
$start = [Environment]::GetFolderPath('Programs')
$pin = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
$seen = @{}; $onDesk = $false
foreach ($x in @(@($dir, $false), @($desk, $false), @($start, $true), @($pin, $false))) {
  $d = $x[0]
  if (-not $d -or -not (Test-Path -LiteralPath $d)) { continue }
  if ($x[1]) { $files = @(Get-ChildItem -LiteralPath $d -Filter *.lnk -Recurse -Depth 2 -ErrorAction SilentlyContinue) }
  else { $files = @(Get-ChildItem -LiteralPath $d -Filter *.lnk -ErrorAction SilentlyContinue) }
  foreach ($f in $files) {
    if ($seen.ContainsKey($f.FullName)) { continue }
    $seen[$f.FullName] = 1
    try {
      $l = $sh.CreateShortcut($f.FullName)
      $hit = ($l.TargetPath -ieq $app) -or ($l.Arguments -and $l.Arguments.ToLower().Contains($app.ToLower()))
      if ($hit) {
        $l.IconLocation = "$ico,0"; $l.Save()
        Write-Output ("ok`t" + $f.FullName)
        if ($d -eq $desk) { $onDesk = $true }
      }
    } catch { Write-Output ("err`t" + $f.FullName + "`t" + $_.Exception.Message) }
  }
}
if ($env:AI_NEWDESK -eq '1' -and -not $onDesk) {
  $p = Join-Path $desk ($env:AI_TITLE + '.lnk')
  $l = $sh.CreateShortcut($p)
  $l.TargetPath = $app; $l.WorkingDirectory = $dir
  $l.IconLocation = "$ico,0"; $l.Description = $env:AI_TITLE
  $l.Save()
  Write-Output ("new`t" + $p)
}
"""


_KEEP = []


def selftest():
    """Все рисунки и формы рисуются, .ico собирается. Возвращает список ошибок."""
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    errs = []
    for key, _, _ in GLYPHS:
        for shape, _ in SHAPES:
            try:
                pm = render({"kind": "glyph", "glyph": key, "shape": shape, "colors": PALETTES[0][1:]}, 32)
                if pm.isNull():
                    errs.append(f"{key}/{shape}: пусто")
            except Exception as e:
                errs.append(f"{key}/{shape}: {e}")
    data = ico_bytes(DEFAULT)
    if data[:4] != b"\0\0\1\0" or int.from_bytes(data[4:6], "little") != len(SIZES):
        errs.append(".ico: неверный заголовок")
    svg = svg_from_data({"width": 24, "height": 24, "icons": {"home": {"body": '<path fill="currentColor" d="M10 20v-6h4v6h5v-8h3L12 3L2 12h3v8z"/>'}},
                         "aliases": {"house": {"parent": "home", "hFlip": True}}}, "house")
    if not svg or not svg_is_mono(svg) or render({"kind": "svg", "svg": svg, "bg": True}, 32).isNull():
        errs.append("SVG (Iconify) не рисуется")
    try:
        if picture_spec(svg.encode())["kind"] != "svg":
            errs.append("SVG из буфера не распознан")
    except Exception as e:
        errs.append(f"SVG из буфера: {e}")
    if query_en("ютуб микрофон") != "youtube microphone":
        errs.append("перевод запроса")
    for extra in ({"shape": "none"}, {"fill": "solid", "ink": "#ff0000"}, {"scale": 130},
                  {"shape": "none", "kind": "svg", "svg": svg}, {"kind": "svg", "svg": svg, "bg": True, "scale": 60}):
        try:
            if render({**DEFAULT, **extra}, 24).isNull():
                errs.append(f"оформление {extra}: пусто")
        except Exception as e:
            errs.append(f"оформление {extra}: {e}")
    html = ('<link rel="icon" href="/f.ico"><link rel="apple-touch-icon" sizes="180x180" href="a.png">'
            '<link rel="icon" type="image/svg+xml" href="/i.svg">')
    c = [u for _, u in site_icon_candidates(html, "https://x.org/")]
    if c[:3] != ["https://x.org/i.svg", "https://x.org/a.png", "https://x.org/f.ico"]:
        errs.append(f"значок сайта: порядок {c}")
    pack = load_pack()
    for cat in pack.get("categories", [])[:1]:
        for icon_id, _, _, s in cat["icons"][:3]:
            if render({"kind": "svg", "svg": s, "bg": True}, 16).isNull():
                errs.append(f"база: {icon_id}")
    img = QImage(8, 4, QImage.Format_ARGB32)
    img.fill(QColor("#ff0000"))
    if render({"kind": "image", "png": base64.b64encode(_png_bytes(img)).decode()}, 16).isNull():
        errs.append("своя картинка не рисуется")
    _KEEP.append(app)                       # приложение живёт до выхода
    return errs


if __name__ == "__main__":
    if sys.platform != "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    e = selftest()
    print("\n".join(e) if e else f"app_icon {VERSION}: OK")
    sys.exit(1 if e else 0)
