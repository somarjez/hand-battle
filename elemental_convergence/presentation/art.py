"""Hand-built art: stage scenes drawn in code, and the woven UI skin.

Every background is composed from layered silhouettes (like cut paper), a printed-grain texture and a
little animation, and each one depicts a real place from the story. Nothing here is a bitmap, so it
scales to any window shape without blur. Scenes are cached per (stage, size).
"""

from __future__ import annotations

import math

import numpy as np
import pygame

RGB = tuple[int, int, int]

# palette, from palay, sampaguita, sili and kape
INK: RGB = (27, 20, 16)
PAPER: RGB = (244, 235, 208)
GOLD: RGB = (232, 179, 63)
RED: RGB = (196, 64, 47)
GREEN: RGB = (62, 107, 72)
TEAL: RGB = (44, 110, 122)
CREAM_DIM: RGB = (190, 178, 150)


# ------------------------------------------------------------------ small drawing helpers
def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def _gradient(size: tuple[int, int], stops: list[tuple[float, RGB]]) -> pygame.Surface:
    w, h = size
    ys = np.linspace(0.0, 1.0, h)
    columns = np.zeros((h, 3))
    for channel in range(3):
        columns[:, channel] = np.interp(ys, [p for p, _ in stops], [c[channel] for _, c in stops])
    arr = np.repeat(columns[None, :, :], w, axis=0).astype(np.uint8)          # (w, h, 3)
    surf = pygame.Surface(size)
    pygame.surfarray.blit_array(surf, arr)
    return surf


def _noise_line(w: int, seed: int, octaves: int = 4, base_freq: float = 2.0) -> np.ndarray:
    """Smooth pseudo-random curve in roughly -1..1 across width w."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 1, w)
    out = np.zeros(w)
    amp = 1.0
    for k in range(octaves):
        freq = base_freq * 2 ** k
        out += amp * np.sin(2 * np.pi * (freq * x + rng.random()))
        amp *= 0.5
    return out / (2 - 2 ** (1 - octaves))


def _ridge(surf: pygame.Surface, base: float, amp: float, color: RGB, seed: int, octaves: int = 4,
           freq: float = 1.6, rim: RGB | None = None, jag: float = 0.0, floor: float | None = None) -> None:
    w, h = surf.get_size()
    y = base - amp * (0.5 + 0.5 * _noise_line(w, seed, octaves, freq))
    if jag:
        y = y + _noise_line(w, seed + 77, 3, 28.0) * jag
    bottom = h if floor is None else floor
    pts = [(0, bottom), *[(i, float(v)) for i, v in enumerate(y)], (w, bottom)]
    pygame.draw.polygon(surf, color, pts)
    if rim:
        pygame.draw.lines(surf, rim, False, pts[1:-1], 2)


_RADIAL_CACHE: dict[tuple, pygame.Surface] = {}


def _radial(radius: int, color: RGB, strength: float = 1.0, power: float = 2.0) -> pygame.Surface:
    key = (radius, color, round(strength, 1), power)
    cached = _RADIAL_CACHE.get(key)
    if cached is not None:
        return cached
    d = radius * 2
    yy, xx = np.mgrid[0:d, 0:d]
    dist = np.hypot(xx - radius, yy - radius) / radius
    alpha = np.clip(1.0 - dist, 0, 1) ** power * 255 * strength
    surf = pygame.Surface((d, d), pygame.SRCALPHA)
    pygame.surfarray.pixels3d(surf)[:] = np.array(color, dtype=np.uint8)
    pygame.surfarray.pixels_alpha(surf)[:] = alpha.T.astype(np.uint8)
    if len(_RADIAL_CACHE) > 160:
        _RADIAL_CACHE.clear()
    _RADIAL_CACHE[key] = surf
    return surf


def _glow(surf: pygame.Surface, center: tuple[float, float], radius: int, color: RGB, strength: float = 0.8) -> None:
    g = _radial(radius, color, strength)
    surf.blit(g, (int(center[0] - radius), int(center[1] - radius)))


def _stars(surf: pygame.Surface, count: int, seed: int, ymax: float, color: RGB = PAPER) -> None:
    rng = np.random.default_rng(seed)
    w, _ = surf.get_size()
    for _ in range(count):
        x, y = int(rng.random() * w), int(rng.random() * ymax)
        b = rng.random()
        pygame.draw.circle(surf, _lerp((40, 40, 60), color, 0.3 + 0.7 * b), (x, y), 1 if b < 0.85 else 2)


def _grain(surf: pygame.Surface, amount: int, seed: int) -> None:
    """Printed-paper grain: a fixed random texture added over the whole picture."""
    rng = np.random.default_rng(seed)
    w, h = surf.get_size()
    noise = rng.integers(-amount, amount + 1, (w, h, 1)).astype(np.int16)
    arr = pygame.surfarray.pixels3d(surf)
    arr[:] = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def _vignette(surf: pygame.Surface, strength: float = 0.55) -> None:
    w, h = surf.get_size()
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
    k = 1.0 - np.clip((d - 0.55) / 0.9, 0, 1) ** 1.6 * strength
    arr = pygame.surfarray.pixels3d(surf)
    arr[:] = (arr * k.T[:, :, None]).astype(np.uint8)


def sun_rays(surf: pygame.Surface, center: tuple[float, float], count: int, length: float, color: RGB,
             alpha: int, spread: float = 0.05, start_angle: float = 0.0, span: float = 2 * math.pi) -> None:
    """Thin tapering rays fanning out from a point: the 'sinag' motif."""
    layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    for k in range(count):
        a = start_angle + span * k / count
        wide = spread * (1.6 if k % 2 == 0 else 0.8)
        p1 = (center[0] + math.cos(a - wide) * length, center[1] + math.sin(a - wide) * length)
        p2 = (center[0] + math.cos(a + wide) * length, center[1] + math.sin(a + wide) * length)
        pygame.draw.polygon(layer, (*color, alpha), [center, p1, p2])
    surf.blit(layer, (0, 0))


# ------------------------------------------------------------------ the scenes
def _scene_menu(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    horizon = h * 0.7
    s = _gradient(size, [(0.0, (12, 9, 26)), (0.42, (58, 26, 56)), (0.66, (200, 92, 58)), (0.7, (240, 170, 92)),
                         (0.71, (22, 14, 30)), (1.0, (10, 8, 18))])
    _stars(s, 90, 3, horizon * 0.7)
    sun = (w * 0.5, horizon)
    _glow(s, sun, int(h * 0.55), (255, 150, 70), 0.55)
    sun_rays(s, sun, 24, w, (255, 196, 110), 26, 0.035, math.pi, math.pi)
    pygame.draw.circle(s, (255, 220, 140), (int(sun[0]), int(sun[1])), int(h * 0.12))
    sea = _gradient((w, int(h - horizon)), [(0.0, (70, 38, 60)), (0.25, (30, 18, 40)), (1.0, (8, 6, 16))])
    s.blit(sea, (0, int(horizon)))                                              # the sea hides the lower half of the sun
    for k in range(34):                                                         # glitter on the water
        gy = horizon + 8 + k * (h - horizon) / 40
        gw = (1 - k / 44) * h * 0.2 * (0.4 + 0.6 * abs(math.sin(k * 1.7)))
        pygame.draw.line(s, _lerp((250, 190, 110), (60, 40, 70), k / 36), (w * 0.5 - gw, gy), (w * 0.5 + gw, gy), 2)
    _ridge(s, horizon + 2, h * 0.14, (30, 16, 38), 5, 4, 1.4, (80, 40, 70), floor=horizon + 10)
    _ridge(s, horizon + 6, h * 0.06, (16, 10, 24), 9, 3, 2.2, floor=horizon + 10)
    bx, by = w * 0.17, h * 0.86                                                 # a paraw: outrigger boat with butterfly sails
    dark = (10, 7, 14)
    pygame.draw.polygon(s, dark, [(bx - 70, by), (bx + 70, by), (bx + 50, by + 14), (bx - 50, by + 14)])
    pygame.draw.polygon(s, dark, [(bx - 8, by), (bx - 8, by - 110), (bx - 62, by - 6)])
    pygame.draw.polygon(s, dark, [(bx + 8, by), (bx + 8, by - 96), (bx + 58, by - 6)])
    pygame.draw.line(s, (176, 100, 66), (bx - 8, by - 110), (bx - 62, by - 6), 2)
    pygame.draw.line(s, (176, 100, 66), (bx + 8, by - 96), (bx + 58, by - 6), 2)
    for dx in (-36, 36):
        pygame.draw.line(s, dark, (bx + dx, by + 4), (bx + dx - 4, by + 40), 3)
    pygame.draw.ellipse(s, dark, (bx - 92, by + 34, 190, 12))
    _grain(s, 7, 1)
    _vignette(s, 0.5)
    return s


def _scene_makiling(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    s = _gradient(size, [(0.0, (14, 30, 38)), (0.45, (52, 92, 88)), (0.74, (228, 186, 118)), (1.0, (20, 36, 30))])
    _stars(s, 40, 11, h * 0.35)
    moon = (w * 0.78, h * 0.18)
    _glow(s, moon, int(h * 0.2), (210, 235, 220), 0.35)
    pygame.draw.circle(s, (232, 244, 228), (int(moon[0]), int(moon[1])), int(h * 0.04))
    xs = np.linspace(0, 1, w)                                                  # the twin peaks
    peaks = 0.3 * np.exp(-((xs - 0.34) / 0.16) ** 2) + 0.22 * np.exp(-((xs - 0.64) / 0.2) ** 2) + 0.08
    noise = _noise_line(w, 21, 4, 6.0) * 0.012
    y = h * 0.74 - h * peaks + noise * h
    pygame.draw.polygon(s, (26, 52, 52), [(0, h), *[(i, float(v)) for i, v in enumerate(y)], (w, h)])
    pygame.draw.lines(s, (80, 126, 110), False, [(i, float(v)) for i, v in enumerate(y)], 2)
    mist = pygame.Surface(size, pygame.SRCALPHA)
    for k in range(60):                                                         # a band of mist
        a = int(70 * (1 - abs(k - 30) / 30))
        pygame.draw.line(mist, (230, 240, 232, a), (0, h * 0.72 + k * 2), (w, h * 0.72 + k * 2), 3)
    s.blit(mist, (0, 0))
    _ridge(s, h * 0.84, h * 0.1, (18, 40, 36), 31, 4, 2.0, (60, 100, 84), jag=3.0)
    _ridge(s, h * 0.92, h * 0.08, (12, 28, 26), 41, 4, 2.6, None, jag=4.0)
    tx = w * 0.84                                                               # the old balete, roots hanging
    pygame.draw.polygon(s, (8, 16, 14), [(tx - 36, h), (tx - 22, h * 0.52), (tx + 22, h * 0.52), (tx + 40, h)])
    rng = np.random.default_rng(5)
    for _ in range(46):                                                         # a ragged crown of many small clumps
        ang, dist = rng.uniform(0, 2 * math.pi), rng.uniform(0, 1) ** 0.6
        pygame.draw.circle(s, (8, 18, 16), (int(tx + math.cos(ang) * 150 * dist - 10), int(h * 0.44 + math.sin(ang) * 90 * dist)), int(rng.uniform(26, 62)))
    for _ in range(26):
        rx = tx + rng.uniform(-150, 130)
        pygame.draw.line(s, (10, 22, 18), (rx, h * 0.5), (rx + rng.uniform(-6, 6), h * rng.uniform(0.62, 0.9)), 2)
    pygame.draw.rect(s, (8, 16, 14), (0, int(h * 0.96), w, h))
    _grain(s, 7, 2)
    _vignette(s, 0.55)
    return s


def _scene_pagsanjan(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    s = _gradient(size, [(0.0, (30, 62, 70)), (0.4, (120, 164, 150)), (1.0, (26, 60, 62))])
    cx = w * 0.5
    layers = [((60, 104, 84), 0.30, 3), ((34, 74, 62), 0.22, 7), ((14, 34, 30), 0.12, 12)]
    for col, inset, seed in layers:                                              # cliffs closing in, nearest last
        yy = np.linspace(0, h, 80)
        wob = np.sin(yy * 0.021 + seed) * 18 + np.sin(yy * 0.057 + seed * 2) * 9
        pygame.draw.polygon(s, col, [(0, 0), *[(w * inset + wo, y) for y, wo in zip(yy, wob)], (0, h)])
        pygame.draw.polygon(s, col, [(w, 0), *[(w * (1 - inset) + wo, y) for y, wo in zip(yy, wob[::-1])], (w, h)])
    fall_top = h * 0.2                                                          # the falls, far up the gorge
    pygame.draw.polygon(s, (226, 240, 236), [(cx - 22, fall_top), (cx + 22, fall_top), (cx + 30, h * 0.5), (cx - 30, h * 0.5)])
    for k in range(9):
        pygame.draw.line(s, (255, 255, 255), (cx - 18 + k * 4.5, fall_top), (cx - 24 + k * 6, h * 0.5), 1)
    _glow(s, (cx, h * 0.5), int(h * 0.2), (230, 245, 240), 0.5)
    river = [(cx - 40, h * 0.5), (cx + 40, h * 0.5), (w * 0.78, h), (w * 0.22, h)]   # the river widens towards you
    pygame.draw.polygon(s, (36, 94, 100), river)
    for k in range(26):
        t = k / 26
        y = h * 0.5 + (h * 0.5) * t ** 1.5
        half = 40 + (w * 0.28 - 40) * t ** 1.5
        pygame.draw.line(s, _lerp((70, 140, 140), (30, 80, 88), t), (cx - half * 0.9, y), (cx + half * 0.9, y), 1)
    bx, by = w * 0.46, h * 0.82                                                  # a bangka with two people
    pygame.draw.polygon(s, (10, 16, 14), [(bx - 90, by), (bx + 90, by), (bx + 64, by + 18), (bx - 64, by + 18)])
    for dx in (-30, 24):
        pygame.draw.circle(s, (10, 16, 14), (int(bx + dx), int(by - 34)), 9)
        pygame.draw.rect(s, (10, 16, 14), (bx + dx - 9, by - 26, 18, 28))
    pygame.draw.line(s, (10, 16, 14), (bx + 24, by - 20), (bx + 110, by + 22), 3)   # the paddle
    _grain(s, 7, 3)
    _vignette(s, 0.6)
    return s


def _scene_batanes(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    s = _gradient(size, [(0.0, (70, 104, 148)), (0.5, (170, 196, 214)), (0.72, (226, 232, 224)), (1.0, (50, 90, 52))])
    rng = np.random.default_rng(13)
    for _ in range(9):                                                          # clouds: clumps of soft circles
        cx, cy = rng.uniform(0, w), rng.uniform(h * 0.08, h * 0.5)
        for k in range(7):
            r = rng.uniform(34, 70)
            layer = _radial(int(r), (255, 255, 255), 0.5, 0.8)
            s.blit(layer, (int(cx + k * 38 - r), int(cy + rng.uniform(-14, 14) - r)))
    _ridge(s, h * 0.7, h * 0.18, (120, 168, 88), 17, 3, 1.2, (170, 208, 120))
    _ridge(s, h * 0.8, h * 0.16, (88, 142, 68), 23, 3, 1.5, (130, 176, 90))
    _ridge(s, h * 0.9, h * 0.12, (60, 108, 52), 29, 3, 1.9, None)
    hx, hy = w * 0.78, h * 0.64                                                   # the Basco lighthouse on its hill
    pygame.draw.polygon(s, (236, 232, 222), [(hx - 20, hy + 70), (hx + 20, hy + 70), (hx + 13, hy - 80), (hx - 13, hy - 80)])
    pygame.draw.polygon(s, RED, [(hx - 17, hy + 8), (hx + 17, hy + 8), (hx + 15, hy - 22), (hx - 15, hy - 22)])
    pygame.draw.rect(s, (40, 40, 48), (hx - 16, hy - 104, 32, 24))
    pygame.draw.polygon(s, (50, 50, 60), [(hx - 20, hy - 104), (hx + 20, hy - 104), (hx, hy - 130)])
    _ridge(s, h * 0.92, h * 0.1, (46, 90, 44), 37, 3, 2.2, None)
    hx2 = w * 0.18                                                               # a stone house with a thatch roof
    pygame.draw.rect(s, (120, 114, 104), (hx2, h * 0.77, 90, 46))
    pygame.draw.polygon(s, (196, 168, 96), [(hx2 - 10, h * 0.77), (hx2 + 100, h * 0.77), (hx2 + 78, h * 0.72), (hx2 + 12, h * 0.72)])
    _grain(s, 6, 4)
    _vignette(s, 0.4)
    return s


def _scene_taal(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    horizon = h * 0.66
    s = _gradient(size, [(0.0, (14, 8, 22)), (0.5, (74, 22, 36)), (0.66, (188, 74, 40)), (0.67, (30, 14, 24)), (1.0, (10, 6, 14))])
    _stars(s, 55, 7, horizon * 0.5, (255, 220, 200))
    cx = w * 0.5
    _ridge(s, horizon + 2, h * 0.07, (40, 18, 30), 4, 3, 2.0)                    # far shore
    cone = [(cx - w * 0.2, horizon + 4), (cx - w * 0.04, h * 0.4), (cx - w * 0.012, h * 0.38), (cx + w * 0.012, h * 0.38),
            (cx + w * 0.05, h * 0.41), (cx + w * 0.22, horizon + 4)]
    pygame.draw.polygon(s, (22, 10, 16), cone)
    _glow(s, (cx, h * 0.385), int(h * 0.3), (255, 110, 40), 0.7)
    pygame.draw.polygon(s, (255, 150, 60), [(cx - 24, h * 0.388), (cx + 24, h * 0.388), (cx + 12, h * 0.4), (cx - 12, h * 0.4)])
    rng = np.random.default_rng(9)
    for _ in range(7):                                                            # lava wandering down the slope
        x, y, drift = cx + rng.uniform(-14, 14), h * 0.4, rng.uniform(-1, 1) * 0.6
        pts = [(x, y)]
        while y < horizon - 6:
            y += 22
            half = w * 0.012 + (y - h * 0.38) / (horizon - h * 0.38) * w * 0.19
            x = min(max(x + drift * 18 + rng.uniform(-8, 8), cx - half * 0.9), cx + half * 0.9)
            pts.append((x, y))
        pygame.draw.lines(s, (255, 110, 40), False, pts, 3)
        pygame.draw.lines(s, (255, 205, 120), False, pts, 1)
    for k in range(14):                                                           # the ash column
        r = 40 + k * 16
        layer = _radial(r, (60, 50, 58), 0.5, 0.9)
        s.blit(layer, (int(cx + math.sin(k * 0.7) * 30 - r), int(h * 0.36 - k * 38 - r)))
    for k in range(30):                                                           # reflection of the glow in the lake
        t = k / 30
        gy = horizon + 6 + t * (h - horizon)
        gw = (1 - t) * 34 + 4
        pygame.draw.line(s, _lerp((220, 90, 40), (40, 16, 24), t), (cx - gw, gy), (cx + gw, gy), 2)
    _ridge(s, h * 0.99, h * 0.06, (8, 6, 12), 3, 3, 2.4)
    _grain(s, 7, 5)
    _vignette(s, 0.55)
    return s


def _scene_bakunawa(size: tuple[int, int]) -> pygame.Surface:
    w, h = size
    s = _gradient(size, [(0.0, (4, 3, 12)), (0.6, (36, 8, 30)), (0.82, (96, 22, 34)), (1.0, (10, 4, 12))])
    _stars(s, 70, 17, h * 0.6, (255, 200, 210))
    moon = (w * 0.5, h * 0.4)
    mr = int(h * 0.19)
    _glow(s, moon, int(h * 0.45), (255, 90, 70), 0.55)
    pygame.draw.circle(s, (255, 150, 90), (int(moon[0]), int(moon[1])), mr + 6)     # the eclipse corona
    pygame.draw.circle(s, (6, 3, 10), (int(moon[0]), int(moon[1])), mr)
    t = np.linspace(0, 1, 150)                                                      # the dragon: one long S across the sky
    bx = w * (-0.1 + 1.0 * t)
    by = h * (0.52 + 0.19 * np.sin(t * 2 * np.pi * 1.1 + 0.5) - 0.06 * t)
    dk = (8, 4, 12)
    for i in range(len(t) - 1):
        width = 10 + 46 * math.sin(math.pi * (0.05 + 0.9 * t[i])) ** 0.7
        pygame.draw.circle(s, dk, (int(bx[i]), int(by[i])), int(width / 2))
        if i % 5 == 0:                                                              # a fin on its back
            nx, ny = by[i + 1] - by[i], -(bx[i + 1] - bx[i])
            n = math.hypot(nx, ny) or 1
            pygame.draw.polygon(s, dk, [(bx[i] - 6, by[i]), (bx[i] + 6, by[i]), (bx[i] + nx / n * (width / 2 + 20), by[i] + ny / n * (width / 2 + 20))])
    hx, hy = bx[-1], by[-1]
    dx, dy = bx[-1] - bx[-4], by[-1] - by[-4]
    dn = math.hypot(dx, dy) or 1
    ux, uy = dx / dn, dy / dn
    pygame.draw.circle(s, dk, (int(hx), int(hy)), 40)                                # head, jaw and horns
    pygame.draw.polygon(s, dk, [(hx - uy * 26, hy + ux * 26), (hx + ux * 74 - uy * 16, hy + uy * 74 + ux * 16), (hx + ux * 70 + uy * 18, hy + uy * 70 - ux * 18), (hx + uy * 26, hy - ux * 26)])
    for sd in (-1, 1):
        pygame.draw.polygon(s, dk, [(hx - ux * 6 + sd * -uy * 20, hy - uy * 6 + sd * ux * 20), (hx - ux * 52 + sd * -uy * 48, hy - uy * 52 + sd * ux * 48), (hx - ux * 22 + sd * -uy * 34, hy - uy * 22 + sd * ux * 34)])
    eye = (int(hx + ux * 14 + uy * 14), int(hy + uy * 14 - ux * 14))
    _glow(s, eye, 20, (255, 170, 60), 0.9)
    pygame.draw.circle(s, (255, 200, 90), eye, 5)
    for k in range(4):                                                              # four rays lit, the fifth still dark
        px = w * (0.3 + 0.13 * k)
        py = h * 0.8 - 14 * math.sin(k * 1.3)
        col = [(190, 132, 76), (74, 180, 245), (214, 238, 230), (255, 111, 58)][k]
        _glow(s, (px, py), 46, col, 0.9)
        pygame.draw.circle(s, col, (int(px), int(py)), 7)
    pygame.draw.circle(s, (70, 56, 40), (int(w * 0.82), int(h * 0.8)), 7, 2)
    _ridge(s, h * 0.93, h * 0.07, (6, 3, 10), 4, 3, 2.6)
    _grain(s, 6, 6)
    _vignette(s, 0.6)
    return s


SCENES = {
    "menu": _scene_menu, "stonewake": _scene_makiling, "tidelost": _scene_pagsanjan, "skyglass": _scene_batanes,
    "cinderforge": _scene_taal, "eclipse": _scene_bakunawa, "calibration": _scene_menu,
}
_CACHE: dict[tuple[str, tuple[int, int]], pygame.Surface] = {}


def stage_scene(stage: str, size: tuple[int, int]) -> pygame.Surface:
    """The cached background for a stage (the title screen's dawn for anything unknown)."""
    key = (stage if stage in SCENES else "menu", size)
    scene = _CACHE.get(key)
    if scene is None:
        if len(_CACHE) > 12:
            _CACHE.clear()
        scene = SCENES[key[0]](size)
        _CACHE[key] = scene
    return scene


# ------------------------------------------------------------------ animated detail over a scene
def animate(stage: str, target: pygame.Surface, clock: float) -> None:
    """Fireflies, a sweeping lamp, rising embers: slow, cheap motion on top of the still scene."""
    w, h = target.get_size()
    rng = np.random.default_rng(100)
    seeds = rng.random((36, 4))
    if stage == "stonewake":                                                       # alitaptap
        for sx, sy, sp, ph in seeds:
            x = (sx * w + math.sin(clock * 0.5 * (0.5 + sp) + ph * 9) * 40) % w
            y = h * (0.45 + 0.5 * sy) + math.cos(clock * 0.4 * (0.5 + sp) + ph * 7) * 24
            on = 0.5 + 0.5 * math.sin(clock * (0.9 + sp * 1.4) + ph * 20)
            if on > 0.35:
                _glow(target, (x, y), 14, (255, 240, 130), 0.9 * on)
                pygame.draw.circle(target, (255, 252, 200), (int(x), int(y)), 2)
    elif stage == "tidelost":                                                      # moving ripples on the river
        for k in range(18):
            t = (k / 18 + clock * 0.05) % 1.0
            y = h * 0.5 + h * 0.5 * t ** 1.5
            half = 40 + (w * 0.28 - 40) * t ** 1.5
            x = w * 0.5 + math.sin(k * 2.3 + clock * 0.6) * half * 0.7
            pygame.draw.line(target, (190, 230, 226), (x - half * 0.18, y), (x + half * 0.18, y), 1 + int(t * 2))
    elif stage == "skyglass":                                                      # the lighthouse lamp sweeping
        hx, hy = w * 0.78, h * 0.64 - 92
        a = math.sin(clock * 0.5) * 0.9 + math.pi
        layer = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(layer, (255, 244, 190, 70), [(hx, hy), (hx + math.cos(a - 0.07) * w, hy + math.sin(a - 0.07) * w),
                                                          (hx + math.cos(a + 0.07) * w, hy + math.sin(a + 0.07) * w)])
        target.blit(layer, (0, 0))
        _glow(target, (hx, hy), 40, (255, 240, 170), 0.8)
    elif stage == "cinderforge":                                                   # embers climbing from the crater
        for sx, _sy, sp, ph in seeds:
            t = (clock * (0.05 + sp * 0.08) + ph) % 1.0
            x = w * 0.5 + (sx - 0.5) * w * 0.22 + math.sin(clock + ph * 8) * 18 + (t * 120 * (sx - 0.5))
            y = h * 0.4 - t * h * 0.5
            pygame.draw.circle(target, _lerp((255, 190, 90), (120, 40, 30), t), (int(x), int(y)), 2 if t < 0.6 else 1)
        _glow(target, (w * 0.5, h * 0.388), int(h * 0.12 * (1 + 0.1 * math.sin(clock * 2))), (255, 150, 60), 0.5)
    elif stage == "eclipse":                                                       # the corona breathing, ash falling
        _glow(target, (w * 0.5, h * 0.4), int(h * 0.3 * (1 + 0.05 * math.sin(clock * 1.4))), (255, 100, 70), 0.25)
        for sx, sy, sp, _ph in seeds[:24]:
            x = (sx * w + clock * 8 * (0.5 + sp)) % w
            y = (sy * h + clock * 14 * (0.5 + sp)) % h
            pygame.draw.circle(target, (150, 90, 90), (int(x), int(y)), 1)
    else:                                                                          # the title screen: drifting sparks of dawn
        for sx, sy, sp, ph in seeds:
            x = (sx * w + math.sin(clock * 0.4 + ph * 9) * 30) % w
            y = h * 0.7 - ((clock * (0.02 + sp * 0.05) + sy) % 1.0) * h * 0.6
            fade = max(0.0, 1.0 - (h * 0.7 - y) / (h * 0.6))
            pygame.draw.circle(target, _lerp((60, 40, 60), (255, 214, 140), fade), (int(x), int(y)), 1 + (sp > 0.8))


# ------------------------------------------------------------------ the woven UI skin
def chamfer(rect: pygame.Rect, cut: int) -> list[tuple[int, int]]:
    c = min(cut, rect.w // 3, rect.h // 3)
    return [(rect.x + c, rect.y), (rect.right - c, rect.y), (rect.right, rect.y + c), (rect.right, rect.bottom - c),
            (rect.right - c, rect.bottom), (rect.x + c, rect.bottom), (rect.x, rect.bottom - c), (rect.x, rect.y + c)]


def draw_weave(surf: pygame.Surface, rect: pygame.Rect, step: int = 10, colors: tuple[RGB, RGB, RGB] = (GOLD, RED, PAPER)) -> None:
    """A band of small diamonds in the manner of woven textiles."""
    n = max(1, rect.w // step)
    cy = rect.centery
    r = max(2, min(rect.h // 2, step // 2))
    for i in range(n):
        cx = rect.x + step // 2 + i * step
        col = colors[i % 3]
        pygame.draw.polygon(surf, col, [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)])


def draw_panel(surf: pygame.Surface, rect: pygame.Rect, alpha: int = 225, band: bool = True) -> None:
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    local = pygame.Rect(0, 0, rect.w - 1, rect.h - 1)
    pygame.draw.polygon(layer, (*INK, alpha), chamfer(local, 14))
    pygame.draw.polygon(layer, (*GOLD, 235), chamfer(local, 14), 2)
    pygame.draw.polygon(layer, (*GOLD, 90), chamfer(local.inflate(-12, -12), 9), 1)
    surf.blit(layer, rect)
    if band and rect.h > 60:
        draw_weave(surf, pygame.Rect(rect.x + 22, rect.y + 6, rect.w - 44, 8), 12)


def draw_button(surf: pygame.Surface, rect: pygame.Rect, active: bool, enabled: bool = True, glow: float = 0.0) -> None:
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    local = pygame.Rect(0, 0, rect.w - 1, rect.h - 1)
    if not enabled:
        fill, edge = (*INK, 150), (90, 80, 66, 200)
    elif active:
        fill, edge = (*_lerp((74, 30, 24), (110, 44, 30), glow), 240), (*_lerp(GOLD, PAPER, glow * 0.6), 255)
    else:
        fill, edge = (*INK, 205), (*_lerp(GOLD, INK, 0.45), 230)
    pygame.draw.polygon(layer, fill, chamfer(local, 9))
    pygame.draw.polygon(layer, edge, chamfer(local, 9), 3 if active else 2)
    surf.blit(layer, rect)


def draw_sun(surf: pygame.Surface, cx: float, cy: float, r: float, color: RGB = GOLD, filled: bool = True, rot: float = 0.0) -> None:
    """An eight-ray sun: the rating mark, the selection marker and the heart of the title."""
    pts = []
    for k in range(16):
        a = rot - math.pi / 2 + k * math.pi / 8
        rad = r if k % 2 == 0 else r * 0.62
        pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
    if filled:
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.circle(surf, _lerp(color, INK, 0.25), (int(cx), int(cy)), max(2, int(r * 0.3)))
    else:
        pygame.draw.polygon(surf, _lerp(color, INK, 0.55), pts, 2)
