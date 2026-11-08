"""neon.py  v2.0.0 — эффект «Неон» на процессоре (numpy): светящийся контур девушек

Контур фигуры (по прозрачности) и складок одежды (по яркости), цвет —
палитра сверху вниз, ореол — размытие в уменьшенном виде, вспышка на долю.
Работает с любой графикой, даже программной.

Журнал:
v2.0.0: перенос шейдера из dancer.js на numpy
"""
import numpy as np

PALETTES = {
    "fire": ((1.0, 0.86, 0.55), (1.0, 0.45, 0.12), (0.95, 0.2, 0.55), (0.55, 0.25, 1.0)),
    "neon": ((0.3, 0.95, 1.0), (0.25, 0.55, 1.0), (0.85, 0.3, 1.0), (1.0, 0.25, 0.7)),
    "rainbow": ((1.0, 0.3, 0.3), (1.0, 0.85, 0.2), (0.3, 1.0, 0.5), (0.35, 0.5, 1.0)),
}


def _sobel(a):
    p = np.pad(a, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    return np.sqrt(gx * gx + gy * gy)


def _smooth(x, lo, hi):
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def _palette(name, h, t):
    pal = np.array(PALETTES.get(name, PALETTES["fire"]), np.float32)
    u = np.linspace(0, 0.62, h, dtype=np.float32) + (t * 0.08 if name == "rainbow" else 0.0)
    u = (u % 1.0) * 4
    i = u.astype(int) % 4
    f = (u - np.floor(u))[:, None]
    f = f * f * (3 - 2 * f)
    return pal[i] * (1 - f) + pal[(i + 1) % 4] * f          # (h, 3)


def _box(img, r, axis):
    """Скользящее среднее радиуса r вдоль оси (через накопленные суммы)."""
    n = img.shape[axis]
    c = np.cumsum(img, axis=axis, dtype=np.float32)
    pad = [(0, 0)] * img.ndim
    pad[axis] = (1, 0)
    c = np.pad(c, pad)
    i = np.arange(n)
    hi = np.minimum(i + r + 1, n)
    lo = np.maximum(i - r, 0)
    take_hi = np.take(c, hi, axis=axis)
    take_lo = np.take(c, lo, axis=axis)
    shape = [1] * img.ndim
    shape[axis] = n
    return (take_hi - take_lo) / (hi - lo).reshape(shape).astype(np.float32)


def _blur(img, r):
    """Плавное размытие: бокс-фильтр дважды по каждой оси (почти гаусс)."""
    for _ in range(2):
        img = _box(_box(img, r, 0), r, 1)
    return img


def apply(bgra, palette="fire", glow=1.2, pulse=0.0, t=0.0):
    """bgra: (h, w, 4) uint8, premultiplied → тот же формат с неоном.
    Большой кадр считается в половинном размере (окно растянет его само)."""
    f = bgra.astype(np.float32) / 255.0
    h, w = f.shape[:2]
    if w * h > 160_000:
        h, w = h // 2, w // 2
        f = f[:h * 2, :w * 2].reshape(h, 2, w, 2, 4).mean((1, 3))
    a = f[..., 3]
    lum = np.sqrt(np.clip(f[..., 2] * 0.299 + f[..., 1] * 0.587 + f[..., 0] * 0.114, 0, 1))
    sil = np.clip(_sobel(a) * 0.9, 0, 1)
    inner = _smooth(_sobel(lum), 0.14, 0.55) * 0.75
    e = np.maximum(sil, inner)
    col = _palette(palette, h, t)[:, None, :]               # (h,1,3) RGB
    edge = np.concatenate([col * e[..., None], e[..., None]], -1)   # RGB + A, premultiplied
    k = 1.0 + 0.45 * pulse
    r = max(2, int(min(h, w) / 90))
    g1 = _blur(edge, r)
    g = _blur(g1, r * 3) * 0.7 + g1 * 0.5
    pal = PALETTES.get(palette, PALETTES["fire"])
    fill = np.array([pal[3][0] * 0.5, pal[3][1] * 0.3, pal[3][2] * 0.6], np.float32)
    rgb = edge[..., :3] * 1.25 * k + e[..., None] * 0.10 * k + g[..., :3] * glow * 1.5 * k \
        + fill * (a * (0.18 + 0.25 * pulse))[..., None]
    alpha = np.clip(np.maximum(e * k, g[..., 3] * glow * 1.2 * k) + a * 0.15, 0, 1)
    rgb = np.minimum(rgb, alpha[..., None] * 1.6)          # свечение — светлее фона, но без «дыр»
    out = np.empty((h, w, 4), np.uint8)
    out[..., 0] = np.clip(rgb[..., 2] * 255, 0, 255)
    out[..., 1] = np.clip(rgb[..., 1] * 255, 0, 255)
    out[..., 2] = np.clip(rgb[..., 0] * 255, 0, 255)
    out[..., 3] = np.clip(alpha * 255, 0, 255)
    np.minimum(out[..., :3], out[..., 3:4], out=out[..., :3])  # premultiplied: цвет ≤ альфа
    return out
