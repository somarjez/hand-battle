"""Animated pictures for the How to Play pages. Each takes (renderer, surface, rect, time)."""

from __future__ import annotations

import math

import pygame

from . import art, handsigns

ELEMENTS = ("earth", "water", "air", "fire", "lightning")
GOLD, INK, DIM = art.GOLD, art.PAPER, art.CREAM_DIM


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _badge(ui, cx, cy, r, color, active=False):
    pygame.draw.circle(ui, (12, 18, 28), (int(cx), int(cy)), r)
    pygame.draw.circle(ui, color if active else tuple(int(c * 0.45) for c in color), (int(cx), int(cy)), r, 5 if active else 2)


def page_signs(r, ui, R, t):
    active = int(t * 0.7) % 5
    spots = [(R.x + 90, R.y + 110), (R.centerx, R.y + 110), (R.right - 90, R.y + 110),
             (R.x + 175, R.y + 290), (R.right - 175, R.y + 290)]
    for i, (name, (cx, cy)) in enumerate(zip(ELEMENTS, spots)):
        col = handsigns.ELEMENT_RGB[name]
        on = i == active
        _badge(ui, cx, cy, 66 if on else 58, col, on)
        handsigns.draw_hand_sign(ui, name, cx, cy - 2, 92 if on else 76, on, t)
        r._text(ui, handsigns.ELEMENT_WORD[name], 21, (cx, cy + 82), col if on else DIM, True, bold=on)
    name = ELEMENTS[active]
    r._text(ui, handsigns.ELEMENT_SIGN[name], 22, (R.centerx, R.bottom - 74), INK, True)
    r._text(ui, f"= {name.title()}", 30, (R.centerx, R.bottom - 38), handsigns.ELEMENT_RGB[name], True, bold=True)


def page_combos(r, ui, R, t):
    rows = (("water", "lightning", "SHOCK", "extra damage and a stun", (90, 170, 255)),
            ("water", "fire", "STEAM", "a burst that hurts all nearby", (230, 240, 250)),
            ("fire", "air", "FIRESTORM", "the flames spread", (255, 130, 40)),
            ("earth", None, "SLOW", "a heavy ring weighs it down", (190, 130, 70)))
    active = int(t * 0.75) % 4
    phase = (t * 0.75) % 1.0
    for i, (a, b, word, note, col) in enumerate(rows):
        y = R.y + 56 + i * 104
        on = i == active
        box = pygame.Rect(R.x + 18, y - 44, R.w - 36, 90)
        pygame.draw.rect(ui, (16, 24, 36) if not on else (28, 36, 52), box, border_radius=14)
        pygame.draw.rect(ui, col if on else (56, 70, 86), box, 3 if on else 1, border_radius=14)
        x = R.x + 72
        handsigns.draw_hand_sign(ui, a, x, y - 4, 62, on, t)
        if b:
            r._text(ui, "+", 30, (x + 56, y), INK, True, bold=True)
            handsigns.draw_hand_sign(ui, b, x + 112, y - 4, 62, on, t)
            r._text(ui, ">", 30, (x + 170, y), INK, True, bold=True)
        else:
            r._text(ui, ">", 30, (x + 56, y), INK, True, bold=True)
        rx = x + (230 if b else 116)
        r._text(ui, word, 28, (rx, y - 20), col, bold=True)
        r._text(ui, note, 17, (rx, y + 14), DIM)
        if on:                                                          # the reaction goes off
            rad = int(10 + 36 * _ease(phase))
            fade = int(220 * (1 - phase))
            ring = pygame.Surface((rad * 2 + 8, rad * 2 + 8), pygame.SRCALPHA)
            pygame.draw.circle(ring, (*col, fade), (rad + 4, rad + 4), rad, 4)
            ui.blit(ring, ring.get_rect(center=(box.right - 46, y)))


def page_fight(r, ui, R, t):
    cycle = (t % 3.4) / 3.4
    scene = R.inflate(-30, -30)
    pygame.draw.rect(ui, (14, 20, 32), scene, border_radius=16)
    pygame.draw.rect(ui, (60, 74, 90), scene, 2, border_radius=16)
    foe = (scene.right - 130, scene.y + 130)
    me = (scene.x + 110, scene.bottom - 120)
    hit = 0.78 < cycle < 0.92
    wind = min(1.0, cycle / 0.45) if cycle < 0.78 else 0.0
    if wind > 0:                                                         # the red charge lane
        w = 6 + 26 * wind
        lane = pygame.Surface(ui.get_size(), pygame.SRCALPHA)
        dx, dy = me[0] - foe[0], me[1] - foe[1]
        n = math.hypot(dx, dy)
        nx, ny = -dy / n * w / 2, dx / n * w / 2
        pygame.draw.polygon(lane, (255, 60, 60, int(50 + 110 * wind)), [(foe[0] + nx, foe[1] + ny), (me[0] + nx, me[1] + ny), (me[0] - nx, me[1] - ny), (foe[0] - nx, foe[1] - ny)])
        ui.blit(lane, (0, 0))
    shake = math.sin(t * 40) * 5 * wind if wind > 0.2 else 0
    sprite = r.sprite_surface("charger", 60, t * 0.9, False, 190)
    if sprite is not None:
        ui.blit(sprite, sprite.get_rect(center=(foe[0] + shake, foe[1])))
    handsigns.draw_hand_sign(ui, "fire", me[0], me[1], 110, True, t)
    if 0.45 < cycle < 0.78:                                              # your blast flies
        k = _ease((cycle - 0.45) / 0.33)
        handsigns.draw_orb(ui, me[0] + (foe[0] - me[0]) * k, me[1] + (foe[1] - me[1]) * k - 20 * math.sin(k * math.pi), 14, (255, 150, 0), t)
    if cycle >= 0.78:
        pop = _ease((cycle - 0.78) / 0.12)
        r._text(ui, "INTERRUPTED!", int(30 + 10 * pop), (scene.centerx, scene.y + 44), (140, 255, 180), True, outline=True, bold=True)
        if hit:
            pygame.draw.circle(ui, (255, 230, 160), foe, int(40 + 60 * pop), 4)
    else:
        r._text(ui, "It shakes, then charges: hit it now", 21, (scene.centerx, scene.y + 44), (255, 150, 140), True, outline=True)
    r._text(ui, "Blasts cancel orbs, bombs and wind-ups", 19, (scene.centerx, scene.bottom - 22), DIM, True)


def page_pickups(r, ui, R, t):
    items = (("heart", "Heart", "+25 HP"), ("regen", "Regen", "health over time"), ("shield", "Shield", "blocks every hit"),
             ("boost", "Boost", "stronger blasts"), ("mana", "Mana", "refills an element"))
    spots = [(R.x + 90, R.y + 100), (R.centerx, R.y + 100), (R.right - 90, R.y + 100), (R.x + 175, R.y + 290), (R.right - 175, R.y + 290)]
    for (kind, name, note), (cx, cy) in zip(items, spots):
        handsigns.draw_pickup(ui, kind, cx, cy, 78, t + len(name))
        r._text(ui, name, 24, (cx, cy + 62), INK, True, bold=True)
        r._text(ui, note, 17, (cx, cy + 88), DIM, True)
    r._text(ui, "Touch them with your hand before they fade", 19, (R.centerx, R.bottom - 30), (255, 214, 120), True)


def page_kalampag(r, ui, R, t):
    cycle = (t % 4.6) / 4.6
    fill = min(10, int(cycle / 0.45 * 10)) if cycle < 0.45 else 10
    boom = cycle > 0.8
    cx = R.centerx
    sprite = r.sprite_surface("rift_sovereign", 100, t * 0.8, False, 170)
    if sprite is not None:
        ui.blit(sprite, sprite.get_rect(center=(cx + (math.sin(t * 50) * 6 if boom else 0), R.y + 110)))
    if boom:
        k = _ease((cycle - 0.8) / 0.2)
        for a in range(16):
            ang = a * math.tau / 16
            pygame.draw.line(ui, (255, 226, 150), (cx + math.cos(ang) * (60 + 80 * k), R.y + 110 + math.sin(ang) * (60 + 80 * k)),
                             (cx + math.cos(ang) * (110 + 120 * k), R.y + 110 + math.sin(ang) * (110 + 120 * k)), 4)
        r._text(ui, "KALAMPAG!", 54, (cx, R.y + 250), (255, 232, 160), True, outline=True, bold=True)
    else:
        together = _ease((cycle - 0.45) / 0.3) if cycle > 0.45 else 0.0
        gap = 150 - 105 * together
        handsigns.draw_hand_sign(ui, "air", cx - gap, R.y + 290, 130, together > 0.9, t)
        handsigns.draw_hand_sign(ui, "air", cx + gap, R.y + 290, 130, together > 0.9, t)
        if together > 0.9:
            hold = (cycle - 0.75) / 0.05
            pygame.draw.arc(ui, (255, 214, 120), pygame.Rect(cx - 70, R.y + 220, 140, 140), math.pi / 2 - max(0, min(1, hold)) * math.tau, math.pi / 2, 6)
    r._text(ui, "10 kills fill the meter, a guardian counts as 5", 18, (cx, R.bottom - 74), DIM, True)
    for i in range(10):
        seg = pygame.Rect(R.x + 40 + i * 44, R.bottom - 50, 38, 20)
        pygame.draw.rect(ui, (255, 190, 70) if i < fill else (30, 40, 54), seg, border_radius=5)
        pygame.draw.rect(ui, (96, 110, 126), seg, 1, border_radius=5)


def page_places(r, ui, R, t):
    tiles = (("rockfall", "Landslide", "Maria Makiling"), ("tide", "Rapids", "Pagsanjan"), ("storm", "Lightning", "Batanes"), ("forge", "Eruption", "Taal"))
    for i, (kind, name, place) in enumerate(tiles):
        box = pygame.Rect(R.x + 18 + (i % 2) * 238, R.y + 14 + (i // 2) * 150, 226, 138)
        pygame.draw.rect(ui, (16, 24, 36), box, border_radius=14)
        pygame.draw.rect(ui, (70, 86, 104), box, 2, border_radius=14)
        handsigns.draw_hazard(ui, kind, box.centerx, box.y + 56, 78, t)
        r._text(ui, name, 22, (box.centerx, box.bottom - 38), INK, True, bold=True)
        r._text(ui, place, 16, (box.centerx, box.bottom - 16), DIM, True)
    lit = int(t * 0.9) % 4
    for i, label in enumerate(("Clear it", "No life lost", "5 hits or fewer")):
        cx = R.x + 82 + i * 178
        r._star(ui, cx, R.bottom - 74, 24, i < lit)
        r._text(ui, label, 17, (cx, R.bottom - 36), INK if i < lit else DIM, True)


PAGES = (page_signs, page_combos, page_fight, page_pickups, page_kalampag, page_places)
