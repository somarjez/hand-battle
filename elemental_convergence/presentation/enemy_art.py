"""Procedural enemy sprites. Every kind has its own silhouette so you can tell them apart at a glance."""

from __future__ import annotations

import math
import random

import pygame

from ..combat import kind_info
from ..session import EnemySnapshot
from .effects import GlowLayer, RGB, darken, lighten, mix, scale_color

OUTLINE = (22, 12, 32)


def ease_out_back(t: float) -> float:
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def spiky(cx: float, cy: float, r: float, spikes: int, inner: float, rot: float) -> list[tuple[float, float]]:
    pts = []
    for k in range(spikes * 2):
        a = rot + k * math.pi / spikes
        rad = r if k % 2 == 0 else r * inner
        pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
    return pts


def ngon(cx: float, cy: float, r: float, n: int, rot: float = 0.0) -> list[tuple[float, float]]:
    return [(cx + math.cos(rot + k * 2 * math.pi / n) * r, cy + math.sin(rot + k * 2 * math.pi / n) * r)
            for k in range(n)]


def _poly(surface, fill: RGB, pts, outline: RGB = OUTLINE, width: int = 2) -> None:
    pygame.draw.polygon(surface, fill, pts)
    if width:
        pygame.draw.polygon(surface, outline, pts, width)


def _eye(surface, x: float, y: float, r: float, color: RGB, pupil: RGB = (255, 240, 235), slit: bool = False) -> None:
    c = (int(x), int(y))
    r = max(2, int(r))
    pygame.draw.circle(surface, (20, 10, 20), c, r + 1)
    pygame.draw.circle(surface, color, c, r)
    if slit:
        pygame.draw.ellipse(surface, (15, 8, 15), (c[0] - max(1, r // 4), c[1] - r + 1, max(2, r // 2), max(2, 2 * r - 2)))
    else:
        pygame.draw.circle(surface, pupil, c, max(1, int(r * 0.4)))


def draw_enemy(surface: pygame.Surface, glow: GlowLayer, e: EnemySnapshot, t: float, flash: bool) -> None:
    info = kind_info(e.kind)
    x, y = e.position
    grow = ease_out_back(e.age / 0.55)
    r = e.radius * grow
    if r < 3:
        return
    y += math.sin(t * 3.0 + e.id) * 3.0
    body: RGB = info.body
    accent: RGB = info.accent
    if e.enraged:
        body = mix(body, (190, 24, 24), 0.45)
        accent = mix(accent, (255, 70, 50), 0.5)
    if flash:
        body = (255, 255, 255)
    glow.circle((x, y), r * (1.35 if e.boss else 1.55), scale_color(accent, (0.07 if e.boss else 0.16) + 0.22 * e.warn + (0.08 if e.enraged else 0)))
    painter = _KIND_PAINTERS.get(e.kind) if not e.boss else _paint_boss
    (painter or _paint_shooter)(surface, glow, e, x, y, r, t, body, accent, flash)
    if e.warn > 0 and not e.dashing:                 # red ring shrinks onto the enemy right before it fires
        ring = int(r * (1.95 - 0.75 * e.warn))
        pygame.draw.circle(surface, (255, 70, 70), (int(x), int(y)), ring, 3 if e.warn > 0.6 else 2)
        glow.circle((x, y), ring, (110, 20, 20), width=12)


# ---- regular enemies -----------------------------------------------------------
def _paint_shooter(surface, glow, e, x, y, r, t, body, accent, flash):
    _poly(surface, body, spiky(x, y, r, 16, 0.74, t * 0.3))
    pygame.draw.circle(surface, lighten(body, 0.14) if not flash else body, (int(x), int(y - r * 0.08)), int(r * 0.6))
    for sx in (-1, 1):
        _eye(surface, x + sx * r * 0.33, y - r * 0.16, r * 0.17, accent)
    mouth = (int(x), int(y + r * 0.4))
    pygame.draw.circle(surface, (24, 10, 30), mouth, max(3, int(r * 0.17)))
    if e.warn > 0:                                    # the cannon charges up
        pygame.draw.circle(surface, lighten(accent, 0.3), mouth, max(2, int(r * 0.16 * (0.4 + e.warn))))
        glow.circle(mouth, r * 0.7 * e.warn + 6, accent)


def _paint_charger(surface, glow, e, x, y, r, t, body, accent, flash):
    heat = e.wind
    if not flash:
        body = mix(body, (255, 60, 40), heat * 0.6)
    ox = oy = 0.0
    if e.wind > 0:                                    # trembles while winding up
        rng = random.Random(int(t * 40))
        ox, oy = rng.uniform(-1, 1) * 5 * heat, rng.uniform(-1, 1) * 5 * heat
    x, y = x + ox, y + oy
    face = math.atan2(e.direction[1], e.direction[0]) if (e.wind > 0 or e.dashing) else math.pi / 2
    _poly(surface, body, spiky(x, y, r, 9, 0.62, face + t * 0.2 * (0 if e.wind > 0 else 1)))
    pygame.draw.circle(surface, lighten(body, 0.12) if not flash else body, (int(x), int(y)), int(r * 0.62))
    for sx in (-1, 1):                                # horns
        horn = [(x + sx * r * 0.28, y - r * 0.62), (x + sx * r * 0.78, y - r * 1.25), (x + sx * r * 0.62, y - r * 0.5)]
        _poly(surface, lighten(body, 0.25) if not flash else body, horn)
    for sx in (-1, 1):                                # angry slit eyes + brows
        _eye(surface, x + sx * r * 0.3, y - r * 0.05, r * 0.15, accent, slit=True)
        pygame.draw.line(surface, OUTLINE, (x + sx * r * 0.52, y - r * 0.3), (x + sx * r * 0.1, y - r * 0.18), 3)
    if e.dashing:
        glow.circle((x, y), r * 2.3, (255, 70, 40))
        for k in range(1, 5):                         # speed lines behind the charger
            bx, by = x - e.direction[0] * r * (0.9 + k * 0.45), y - e.direction[1] * r * (0.9 + k * 0.45)
            pygame.draw.circle(surface, scale_color(accent, 0.9 - k * 0.18), (int(bx), int(by)), max(2, int(r * (0.55 - k * 0.09))))


def _paint_sniper(surface, glow, e, x, y, r, t, body, accent, flash):
    c = (int(x), int(y))
    pygame.draw.circle(surface, OUTLINE, c, int(r) + 2)
    pygame.draw.circle(surface, body, c, int(r))
    pygame.draw.circle(surface, lighten(body, 0.12) if not flash else body, c, int(r * 0.78), 3)
    pygame.draw.circle(surface, (235, 245, 235), c, int(r * 0.52))
    hot = e.warn > 0.2
    iris = (255, 60, 60) if hot else accent
    pygame.draw.circle(surface, iris, c, int(r * 0.34))
    pygame.draw.ellipse(surface, (12, 8, 12), (c[0] - int(r * 0.07), c[1] - int(r * 0.3), int(r * 0.14), int(r * 0.6)))
    if hot:
        glow.circle((x, y), r * 1.2, (200, 30, 30))
    for k in range(4):                                # slow rotating crosshair
        a = t * 0.9 + k * math.pi / 2
        p1 = (x + math.cos(a) * r * 1.12, y + math.sin(a) * r * 1.12)
        p2 = (x + math.cos(a) * r * 1.42, y + math.sin(a) * r * 1.42)
        pygame.draw.line(surface, accent, p1, p2, 3)


def _paint_gunner(surface, glow, e, x, y, r, t, body, accent, flash):
    for sx in (-1, 1):                                # twin barrels
        barrel = pygame.Rect(0, 0, int(r * 0.62), int(r * 0.26))
        barrel.center = (int(x + sx * r * 1.0), int(y + r * 0.22))
        pygame.draw.rect(surface, darken(body, 0.35) if not flash else body, barrel, border_radius=4)
        pygame.draw.rect(surface, OUTLINE, barrel, 2, border_radius=4)
        if e.warn > 0:
            glow.circle((barrel.centerx + sx * barrel.w // 2, barrel.centery), 16 + 18 * e.warn, accent)
    hexa = ngon(x, y, r, 6, math.pi / 6)
    _poly(surface, body, hexa, width=3)
    _poly(surface, lighten(body, 0.1) if not flash else body, ngon(x, y, r * 0.72, 6, math.pi / 6), width=1)
    for p in ngon(x, y, r * 0.86, 6, math.pi / 6):
        pygame.draw.circle(surface, (230, 235, 245), (int(p[0]), int(p[1])), max(2, int(r * 0.05)))
    visor = pygame.Rect(0, 0, int(r * 1.15), int(r * 0.3))
    visor.center = (int(x), int(y - r * 0.08))
    pygame.draw.rect(surface, (14, 10, 20), visor, border_radius=8)
    for sx in (-1, 1):
        pygame.draw.circle(surface, accent, (int(x + sx * r * 0.28), visor.centery), max(3, int(r * 0.08)))


def _paint_bomber(surface, glow, e, x, y, r, t, body, accent, flash):
    c = (int(x), int(y))
    pygame.draw.circle(surface, OUTLINE, c, int(r) + 2)
    pygame.draw.circle(surface, body, c, int(r))
    pygame.draw.circle(surface, lighten(body, 0.2) if not flash else body, (int(x - r * 0.28), int(y - r * 0.3)), int(r * 0.42))
    for sx in (-1, 1):
        _eye(surface, x + sx * r * 0.3, y + r * 0.05, r * 0.15, (30, 12, 6), pupil=accent)
    mouth = [(x - r * 0.3, y + r * 0.42), (x - r * 0.1, y + r * 0.34), (x + r * 0.1, y + r * 0.42), (x + r * 0.3, y + r * 0.34)]
    pygame.draw.lines(surface, OUTLINE, False, mouth, 3)
    fuse_a, fuse_b = (x, y - r), (x + r * 0.28, y - r * 1.32)       # burning fuse
    pygame.draw.line(surface, (70, 50, 30), fuse_a, fuse_b, 4)
    flick = 0.7 + 0.3 * math.sin(t * 30)
    spark = (int(fuse_b[0]), int(fuse_b[1]))
    glow.circle(spark, 22 * flick + 10 * e.warn, (255, 160, 40))
    pygame.draw.circle(surface, (255, 220, 120), spark, int(5 * flick) + 1)
    if e.warn > 0:                                    # glowing cracks right before it throws
        for k in range(3):
            a = -0.6 + k * 0.7
            p1 = (x + math.cos(a) * r * 0.25, y + math.sin(a) * r * 0.25 + r * 0.2)
            p2 = (x + math.cos(a) * r * 0.95, y + math.sin(a) * r * 0.95 + r * 0.2)
            pygame.draw.line(surface, (255, 230, 130), p1, p2, 2)


def _paint_caster(surface, glow, e, x, y, r, t, body, accent, flash):
    star_r = r * 1.3                                  # rotating hexagram
    for k, rot in enumerate((t * 0.7, t * 0.7 + math.pi)):
        pygame.draw.polygon(surface, scale_color(accent, 0.85), ngon(x, y, star_r, 3, rot), 2)
    glow.circle((x, y), star_r, scale_color(accent, 0.2))
    c = (int(x), int(y))
    pygame.draw.circle(surface, OUTLINE, c, int(r) + 2)
    pygame.draw.circle(surface, body, c, int(r))
    hood = [(x - r * 0.85, y - r * 0.1), (x, y - r * 1.35), (x + r * 0.85, y - r * 0.1)]
    _poly(surface, darken(body, 0.25) if not flash else body, hood)
    for sx in (-1, 1):
        pygame.draw.circle(surface, accent, (int(x + sx * r * 0.28), int(y - r * 0.12)), max(3, int(r * 0.12)))
    for k in range(3):                                # orbiting mana orbs
        a = t * 2.0 + k * 2 * math.pi / 3
        px, py = x + math.cos(a) * r * 1.5, y + math.sin(a) * r * 0.6 + math.sin(a * 0.5) * 4
        glow.circle((px, py), 20, accent)
        pygame.draw.circle(surface, lighten(accent, 0.4), (int(px), int(py)), max(3, int(r * 0.13)))


def _paint_spinner(surface, glow, e, x, y, r, t, body, accent, flash):
    speed = 9.0 if e.spiral else 3.2
    for k in range(3):
        a = t * speed + k * 2 * math.pi / 3
        tip = (x + math.cos(a) * r * 1.12, y + math.sin(a) * r * 1.12)
        l = (x + math.cos(a + 1.6) * r * 0.34, y + math.sin(a + 1.6) * r * 0.34)
        rr = (x + math.cos(a - 1.0) * r * 0.5, y + math.sin(a - 1.0) * r * 0.5)
        _poly(surface, lighten(body, 0.15) if not flash else body, [l, tip, rr])
        glow.circle(tip, 16, scale_color(accent, 0.7 if e.spiral else 0.35))
    c = (int(x), int(y))
    pygame.draw.circle(surface, OUTLINE, c, int(r * 0.62) + 2)
    pygame.draw.circle(surface, body, c, int(r * 0.62))
    _eye(surface, x, y, r * 0.3, accent)


def _paint_sweeper(surface, glow, e, x, y, r, t, body, accent, flash):
    for k in range(4):
        a = t * 0.8 + k * math.pi / 2
        base = (x + math.cos(a) * r * 0.6, y + math.sin(a) * r * 0.6)
        tip = (x + math.cos(a) * r * 1.25, y + math.sin(a) * r * 1.25)
        perp = (-math.sin(a) * r * 0.18, math.cos(a) * r * 0.18)
        _poly(surface, darken(body, 0.2) if not flash else body,
              [(base[0] + perp[0], base[1] + perp[1]), tip, (base[0] - perp[0], base[1] - perp[1])])
        pygame.draw.circle(surface, accent, (int(tip[0]), int(tip[1])), max(2, int(r * 0.07)))
    c = (int(x), int(y))
    pygame.draw.circle(surface, OUTLINE, c, int(r * 0.78) + 2)
    pygame.draw.circle(surface, body, c, int(r * 0.78))
    slit = pygame.Rect(0, 0, int(r * 0.9), int(r * (0.16 + 0.22 * e.warn)))
    slit.center = c
    pygame.draw.ellipse(surface, (10, 20, 22), slit.inflate(6, 6))
    pygame.draw.ellipse(surface, accent if e.warn < 0.5 else (255, 255, 255), slit)
    if e.warn > 0:
        glow.circle((x, y), r * (0.9 + e.warn), accent)


def _paint_blinker(surface, glow, e, x, y, r, t, body, accent, flash):
    size = int(r * 3)
    layer = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    flicker = 0.5 + 0.5 * math.sin(t * 22) if e.blink > 0 else 1.0
    alpha = int(190 * (0.35 + 0.65 * flicker))
    col = (*body, alpha)
    pygame.draw.circle(layer, col, (cx, int(cy - r * 0.2)), int(r * 0.9))
    tail = [(cx - r * 0.9, cy - r * 0.2)]
    for k in range(7):                                # wavy ghost hem
        tail.append((cx - r * 0.9 + k * r * 0.3, cy + r * 0.85 + (math.sin(t * 6 + k) * r * 0.15) * (1 if k % 2 else -1)))
    tail.append((cx + r * 0.9, cy - r * 0.2))
    pygame.draw.polygon(layer, col, tail)
    for sx in (-1, 1):
        pygame.draw.circle(layer, (255, 255, 255, 235), (int(cx + sx * r * 0.32), int(cy - r * 0.28)), max(3, int(r * 0.2)))
        pygame.draw.circle(layer, (40, 30, 70, 255), (int(cx + sx * r * 0.32), int(cy - r * 0.25)), max(2, int(r * 0.09)))
    pygame.draw.circle(layer, (*accent, 120), (cx, int(cy - r * 0.2)), int(r * 0.9), 3)
    surface.blit(layer, (x - cx, y - cy))
    glow.circle((x, y), r * 1.2, scale_color(accent, 0.3))


_KIND_PAINTERS = {
    "shooter": _paint_shooter,
    "charger": _paint_charger,
    "sniper": _paint_sniper,
    "gunner": _paint_gunner,
    "bomber": _paint_bomber,
    "caster": _paint_caster,
    "spinner": _paint_spinner,
    "sweeper": _paint_sweeper,
    "blinker": _paint_blinker,
}


# ---- bosses --------------------------------------------------------------------
def _paint_boss(surface, glow, e, x, y, r, t, body, accent, flash):
    # rotating rune ring
    for k in range(12):
        a = t * (0.9 if e.enraged else 0.45) + k * math.pi / 6
        px, py = x + math.cos(a) * r * 1.38, y + math.sin(a) * r * 1.38
        d = r * 0.07
        diamond = [(px, py - d * 1.6), (px + d, py), (px, py + d * 1.6), (px - d, py)]
        pygame.draw.polygon(surface, accent, diamond)
        glow.circle((px, py), 12, scale_color(accent, 0.22))
    pygame.draw.circle(surface, scale_color(accent, 0.55), (int(x), int(y)), int(r * 1.38), 1)
    for sx in (-1, 1):                                # horns
        horn = [(x + sx * r * 0.35, y - r * 0.85), (x + sx * r * 1.0, y - r * 1.62), (x + sx * r * 0.78, y - r * 0.55)]
        _poly(surface, darken(accent, 0.35) if not flash else body, horn, width=3)
    _poly(surface, body, spiky(x, y, r, 24, 0.82, t * 0.25), width=3)
    pygame.draw.circle(surface, lighten(body, 0.12) if not flash else body, (int(x), int(y)), int(r * 0.74))
    pygame.draw.circle(surface, scale_color(accent, 0.8), (int(x), int(y)), int(r * 0.74), 3)
    _boss_decor(surface, glow, e, x, y, r, t, body, accent)
    for ex, ey, er in ((-0.38, -0.14, 0.2), (0.38, -0.14, 0.2), (0.0, -0.42, 0.14)):
        _eye(surface, x + ex * r, y + ey * r, r * er, (255, 215, 90) if not e.enraged else (255, 70, 50), (255, 245, 220))
    pygame.draw.line(surface, OUTLINE, (x - r * 0.32, y + r * 0.34), (x + r * 0.32, y + r * 0.34), 5)
    if e.warn > 0:
        glow.circle((x, y), r * (1.25 + e.warn * 0.4), scale_color(accent, 0.35), width=r * 0.25)


def _boss_decor(surface, glow, e, x, y, r, t, body, accent) -> None:
    kind = e.kind
    if kind == "stone_guardian":                      # cracked stone with glowing fissures
        for a0, l in ((0.5, 0.55), (2.2, 0.6), (3.6, 0.5), (5.2, 0.58)):
            pts = [(x + math.cos(a0) * r * 0.2, y + math.sin(a0) * r * 0.2)]
            for k in range(1, 4):
                pts.append((x + math.cos(a0 + 0.2 * (-1) ** k) * r * (0.2 + l * k / 3), y + math.sin(a0 + 0.2 * (-1) ** k) * r * (0.2 + l * k / 3)))
            pygame.draw.lines(surface, accent, False, pts, 2)
    elif kind == "tide_guardian":                     # rolling waves
        for k in range(3):
            pts = [(x - r * 0.6 + i * r * 0.15, y + r * (0.18 + k * 0.17) + math.sin(t * 3 + i + k) * r * 0.04) for i in range(9)]
            pygame.draw.lines(surface, accent, False, pts, 2)
    elif kind == "gale_guardian":                     # spiralling wind
        for s in (0, math.pi):
            pts = [(x + math.cos(t * 2 + s + i * 0.45) * r * (0.1 + i * 0.045),
                    y + math.sin(t * 2 + s + i * 0.45) * r * (0.1 + i * 0.045)) for i in range(14)]
            pygame.draw.lines(surface, accent, False, pts, 2)
    elif kind == "ember_guardian":                    # molten core
        glow.circle((x, y + r * 0.3), r * 0.7, (255, 110, 30))
        pygame.draw.circle(surface, (255, 190, 90), (int(x), int(y + r * 0.34)), int(r * 0.2 + 3 * math.sin(t * 6)))
    elif kind == "rift_sovereign":                    # crown and a void core
        for k in range(5):
            bx = x + (k - 2) * r * 0.32
            _poly(surface, accent, [(bx - r * 0.12, y - r * 0.8), (bx, y - r * (1.25 - 0.1 * abs(k - 2))), (bx + r * 0.12, y - r * 0.8)], width=2)
        pygame.draw.circle(surface, (14, 6, 30), (int(x), int(y + r * 0.28)), int(r * 0.3))
        pygame.draw.circle(surface, accent, (int(x), int(y + r * 0.28)), int(r * 0.3), 2)
        glow.circle((x, y + r * 0.28), r * 0.5, (120, 30, 140))
