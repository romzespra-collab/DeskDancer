"""theme.py  v1.0.0 — палитры DeskDancer и текущие цвета для общих модулей

window_frame (из SmartMon) берёт отсюда TEXT / TEXT_DIM / BORDER,
gh_update_qt — ACCENT / TEXT / TEXT_DIM / BG_PANEL / BORDER.
apply(name) переставляет эти значения при смене темы.

Журнал:
v1.0.0: первая версия — тёмная и светлая палитры, цвета страниц
"""
THEMES = {
    "dark": {"bg": "#16171d", "side": "#121318", "panel": "#1f2129", "panel2": "#272a35",
             "line": "#343846", "text": "#e8e9f0", "muted": "#8b90a3", "log_bg": "#0f1015",
             "log_fg": "#d5d8e0", "accent": "#ff5fa2", "accent2": "#7c6cff",
             "toggle_off": "#454b59"},
    "light": {"bg": "#f3f3f7", "side": "#e9e9f0", "panel": "#ffffff", "panel2": "#f1f2f7",
              "line": "#dcdee7", "text": "#1c1f2b", "muted": "#6b7085", "log_bg": "#fbfbfd",
              "log_fg": "#1c1f2b", "accent": "#d81b72", "accent2": "#5a48e0",
              "toggle_off": "#c3c8d2"},
}
OK, ERR, WARN = "#3ecf8e", "#ff5d6c", "#f5b545"

# цвет каждой страницы: (тёмная тема, светлая — темнее)
PAGE_COLORS = {
    "scene": ("#ff5fa2", "#c2185b"),
    "music": ("#35c6f4", "#0277a8"),
    "window": ("#ffb547", "#b26a00"),
    "library": ("#3ecf8e", "#14864f"),
    "log": ("#a58bff", "#5e3fd0"),
    "update": ("#4f8cff", "#1f5fd6"),
}

NAME = "dark"
P = dict(THEMES["dark"])
ACCENT = P["accent"]
TEXT = P["text"]
TEXT_DIM = P["muted"]
BG_PANEL = P["panel"]
BORDER = P["line"]


def apply(name):
    global NAME, P, ACCENT, TEXT, TEXT_DIM, BG_PANEL, BORDER
    NAME = name if name in THEMES else "dark"
    P = dict(THEMES[NAME])
    ACCENT, TEXT, TEXT_DIM = P["accent"], P["text"], P["muted"]
    BG_PANEL, BORDER = P["panel"], P["line"]
    return P


def page_color(key):
    d, l = PAGE_COLORS.get(key, ("#4f8cff", "#1f5fd6"))
    return d if NAME == "dark" else l
