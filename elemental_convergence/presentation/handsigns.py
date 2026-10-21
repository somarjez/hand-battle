"""Drawn hand-signs, pick-up icons and hazard icons for the tutorial screens.

Everything is plain pygame shapes so it needs no art files and stays crisp at any size. Sizes are the
height of the whole drawing in pixels.
"""

from __future__ import annotations

import math

import pygame

from . import art

SKIN, SKIN_SHADE, OUTLINE = (236, 196, 156), (206, 160, 120), (42, 26, 30)

ELEMENT_RGB = {"earth": (190, 130, 70), "water": (60, 200, 255), "air": (230, 255, 255),
               "fire": (255, 150, 0), "lightning": (90, 170, 255)}
ELEMENT_WORD = {"earth": "Lupa", "water": "Tubig", "air": "Hangin", "fire": "Apoy", "lightning": "Kidlat"}
ELEMENT_SIGN = {"earth": "Fist", "water": "Open palm, fingers spread", "air": "Flat palm, fingers together",
                "fire": "Two fingers up", "lightning": "Point one finger"}


def _limb(surf, a, b, width, color=SKIN, outline=OUTLINE):
    for col, w in ((outline, width + 6), (color, width)):
        pygame.draw.line(surf, col, a, b, max(1, int(w)))
        pygame.draw.circle(surf, col, (int(a[0]), int(a[1])), int(w / 2))
        pygame.draw.circle(surf, col, (int(b[0]), int(b[1])), int(w / 2))


def draw_hand_sign(surf: pygame.Surface, element: str, cx: float, cy: float, size: float,
                   glow: bool = True, t: float = 0.0) -> None:
    """A front-view hand making the sign for ``element``, with a soft glow in the element's colour."""
    u = size / 120.0
    color = ELEMENT_RGB.get(element, (230, 230, 230))
    if glow:
        halo = art._radial(int(size * 0.85), color, 0.55 + 0.15 * math.sin(t * 3.0), 1.7)
        surf.blit(halo, halo.get_rect(center=(int(cx), int(cy))))
    px, py = cx, cy + 22 * u                                             # palm centre
    palm = pygame.Rect(0, 0, 54 * u, 50 * u)
    palm.center = (px, py)
    top = palm.top + 6 * u
    xs = (-19 * u, -6.5 * u, 6.5 * u, 19 * u)
    lengths = (36 * u, 41 * u, 36 * u, 28 * u)
    width = 12 * u
    pygame.draw.rect(surf, OUTLINE, palm.inflate(6, 6), border_radius=int(14 * u))
    pygame.draw.rect(surf, SKIN, palm, border_radius=int(12 * u))

    def finger(i, angle, scale=1.0):
        a = math.radians(angle)
        base = (px + xs[i], top)
        tip = (base[0] + math.sin(a) * lengths[i] * scale, base[1] - math.cos(a) * lengths[i] * scale)
        _limb(surf, base, tip, width)

    def knuckle(i):
        pygame.draw.circle(surf, OUTLINE, (int(px + xs[i]), int(top - 1 * u)), int(9.5 * u))
        pygame.draw.circle(surf, SKIN, (int(px + xs[i]), int(top - 1 * u)), int(7 * u))
        pygame.draw.arc(surf, SKIN_SHADE, (px + xs[i] - 6 * u, top - 7 * u, 12 * u, 12 * u), 3.4, 6.0, max(1, int(2 * u)))

    if element == "earth":                                               # fist
        for i in range(4):
            knuckle(i)
        _limb(surf, (px - 24 * u, py + 6 * u), (px + 6 * u, py - 4 * u), 13 * u)
    elif element == "water":                                             # open, fingers spread
        for i, ang in enumerate((-24, -8, 8, 24)):
            finger(i, ang)
        _limb(surf, (px - 24 * u, py + 8 * u), (px - 50 * u, py - 12 * u), 13 * u)
    elif element == "air":                                               # flat, fingers together
        for i in range(4):
            finger(i, 0)
        _limb(surf, (px - 24 * u, py + 10 * u), (px - 30 * u, py - 12 * u), 12 * u)
    elif element == "fire":                                              # two fingers
        finger(1, -7)
        finger(2, 7)
        knuckle(0)
        knuckle(3)
        _limb(surf, (px - 22 * u, py + 10 * u), (px + 16 * u, py - 2 * u), 12 * u)
    elif element == "lightning":                                         # point
        finger(0, 0, 1.25)
        for i in (1, 2, 3):
            knuckle(i)
        _limb(surf, (px - 24 * u, py + 8 * u), (px - 6 * u, py - 6 * u), 12 * u)
    pygame.draw.arc(surf, SKIN_SHADE, palm.inflate(-10 * u, -10 * u), 3.6, 5.8, max(1, int(2 * u)))   # palm crease


def draw_orb(surf, cx, cy, r, color, t=0.0):
    halo = art._radial(int(r * 2.2), color, 0.7, 1.8)
    surf.blit(halo, halo.get_rect(center=(int(cx), int(cy))))
    pygame.draw.circle(surf, tuple(int(c * 0.55) for c in color), (int(cx), int(cy)), int(r))
    pygame.draw.circle(surf, color, (int(cx), int(cy)), int(r * 0.72))
    pygame.draw.circle(surf, (255, 255, 255), (int(cx - r * 0.2), int(cy - r * 0.25)), max(2, int(r * 0.25)))


def draw_pickup(surf: pygame.Surface, kind: str, cx: float, cy: float, size: float, t: float = 0.0) -> None:
    """Pick-up icons: heart, regen, shield, boost, mana."""
    s = size / 2
    bob = math.sin(t * 2.4 + len(kind)) * 3
    cy += bob
    colors = {"heart": (255, 80, 96), "regen": (96, 230, 120), "shield": (110, 190, 255),
              "boost": (255, 190, 70), "mana": (120, 230, 255)}
    col = colors.get(kind, (255, 255, 255))
    halo = art._radial(int(size), col, 0.5, 1.7)
    surf.blit(halo, halo.get_rect(center=(int(cx), int(cy))))
    if kind == "heart":
        pts = [(cx + math.sin(a) ** 3 * s * 0.9, cy - (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) / 16 * s * 0.95 + s * 0.05)
               for a in [i * math.tau / 60 for i in range(60)]]
        pygame.draw.polygon(surf, (60, 12, 24), [(x, y) for x, y in pts], 0)
        pygame.draw.polygon(surf, col, [(cx + (x - cx) * 0.86, cy + (y - cy) * 0.86) for x, y in pts])
    elif kind == "regen":
        pygame.draw.circle(surf, (14, 50, 28), (int(cx), int(cy)), int(s * 0.95))
        pygame.draw.circle(surf, col, (int(cx), int(cy)), int(s * 0.82), max(2, int(s * 0.14)))
        pygame.draw.rect(surf, col, (cx - s * 0.12, cy - s * 0.5, s * 0.24, s), border_radius=3)
        pygame.draw.rect(surf, col, (cx - s * 0.5, cy - s * 0.12, s, s * 0.24), border_radius=3)
    elif kind == "shield":
        pts = [(cx - s * 0.8, cy - s * 0.8), (cx + s * 0.8, cy - s * 0.8), (cx + s * 0.75, cy + s * 0.1),
               (cx, cy + s * 0.95), (cx - s * 0.75, cy + s * 0.1)]
        pygame.draw.polygon(surf, (16, 34, 70), pts)
        pygame.draw.polygon(surf, col, [(cx + (x - cx) * 0.84, cy + (y - cy) * 0.84) for x, y in pts])
        pygame.draw.line(surf, (235, 248, 255), (cx, cy - s * 0.6), (cx, cy + s * 0.6), max(2, int(s * 0.12)))
    elif kind == "boost":
        for k in range(3):
            y = cy + (k - 1) * s * 0.55
            pygame.draw.lines(surf, (60, 34, 8), False, [(cx - s * 0.7, y + s * 0.3), (cx, y - s * 0.3), (cx + s * 0.7, y + s * 0.3)], max(4, int(s * 0.34)))
            pygame.draw.lines(surf, col, False, [(cx - s * 0.7, y + s * 0.3), (cx, y - s * 0.3), (cx + s * 0.7, y + s * 0.3)], max(2, int(s * 0.2)))
    else:                                                                # mana: a drop
        pts = [(cx, cy - s * 0.95), (cx + s * 0.6, cy + s * 0.1), (cx + s * 0.45, cy + s * 0.65), (cx, cy + s * 0.9),
               (cx - s * 0.45, cy + s * 0.65), (cx - s * 0.6, cy + s * 0.1)]
        pygame.draw.polygon(surf, (10, 46, 62), pts)
        pygame.draw.polygon(surf, col, [(cx + (x - cx) * 0.82, cy + (y - cy) * 0.82) for x, y in pts])
        pygame.draw.circle(surf, (255, 255, 255), (int(cx - s * 0.18), int(cy + s * 0.1)), max(2, int(s * 0.14)))


def draw_hazard(surf: pygame.Surface, kind: str, cx: float, cy: float, size: float, t: float = 0.0) -> None:
    """Little portraits of the four place hazards."""
    s = size / 2
    if kind == "rockfall":
        pygame.draw.ellipse(surf, (90, 22, 26), (cx - s * 0.8, cy + s * 0.35, s * 1.6, s * 0.5))
        for k in range(8):
            a = k * math.tau / 8 + t * 0.5
            pygame.draw.line(surf, (255, 90, 90), (cx + math.cos(a) * s * 0.85, cy + s * 0.6 + math.sin(a) * s * 0.28),
                             (cx + math.cos(a + 0.3) * s * 0.85, cy + s * 0.6 + math.sin(a + 0.3) * s * 0.28), 3)
        ry = cy - s * 0.2 - abs(math.sin(t * 1.6)) * s * 0.5
        pts = [(cx + math.cos(k * math.tau / 9) * s * (0.55 + 0.1 * math.sin(k * 2.3)), ry + math.sin(k * math.tau / 9) * s * 0.5) for k in range(9)]
        pygame.draw.polygon(surf, (30, 36, 46), pts)
        pygame.draw.polygon(surf, (120, 140, 160), [(cx + (x - cx) * 0.85, ry + (y - ry) * 0.85) for x, y in pts])
    elif kind == "tide":
        for k in range(3):
            pts = [(cx - s + i * s / 6, cy + (k - 1) * s * 0.4 + math.sin(i * 0.9 + t * 3 + k) * s * 0.14) for i in range(13)]
            pygame.draw.lines(surf, (60, 150, 235), False, pts, max(3, int(s * 0.2)))
            pygame.draw.lines(surf, (200, 240, 255), False, pts, max(1, int(s * 0.06)))
    elif kind == "storm":
        pygame.draw.ellipse(surf, (80, 90, 112), (cx - s * 0.9, cy - s * 0.95, s * 1.8, s * 0.7))
        pygame.draw.ellipse(surf, (110, 122, 146), (cx - s * 0.6, cy - s * 1.05, s * 1.2, s * 0.6))
        bolt = [(cx + s * 0.1, cy - s * 0.35), (cx - s * 0.3, cy + s * 0.15), (cx + s * 0.02, cy + s * 0.15), (cx - s * 0.2, cy + s * 0.9),
                (cx + s * 0.4, cy - s * 0.1), (cx + s * 0.08, cy - s * 0.1)]
        pygame.draw.polygon(surf, (255, 240, 150) if int(t * 6) % 2 else (255, 255, 255), bolt)
    else:                                                                # forge / eruption
        pygame.draw.polygon(surf, (50, 36, 40), [(cx - s * 0.9, cy + s * 0.9), (cx - s * 0.3, cy - s * 0.2), (cx + s * 0.3, cy - s * 0.2), (cx + s * 0.9, cy + s * 0.9)])
        pygame.draw.ellipse(surf, (255, 160, 40), (cx - s * 0.32, cy - s * 0.3, s * 0.64, s * 0.2))
        for k in range(3):
            a = -math.pi / 2 + (k - 1) * 0.6
            d = (t * 1.2 + k * 0.33) % 1.0
            pygame.draw.circle(surf, (255, 150 + k * 20, 40), (int(cx + math.cos(a) * s * d * 1.1), int(cy - s * 0.3 + math.sin(a) * s * d * 1.3 + d * d * s * 0.6)), int(s * 0.16))
