"""Small colour helpers shared by the menu screens."""

from __future__ import annotations

import math
import random

import pygame

RGB = tuple[int, int, int]


def mix(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(1.0, t))
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


def lighten(c: RGB, t: float) -> RGB:
    return mix(c, (255, 255, 255), t)


def darken(c: RGB, t: float) -> RGB:
    return mix(c, (0, 0, 0), t)


def scale_color(c: RGB, k: float) -> RGB:
    return (max(0, min(255, int(c[0] * k))), max(0, min(255, int(c[1] * k))), max(0, min(255, int(c[2] * k))))


class GlowLayer:
    def __init__(self, size: tuple[int, int]):
        self.surface = pygame.Surface(size, pygame.SRCALPHA)

    def clear(self) -> None:
        self.surface.fill((0, 0, 0, 0))

    def circle(self, x: float | tuple[float, float], y: float, radius: float | RGB, color: RGB | None = None) -> None:
        if isinstance(x, tuple):
            x, y, radius, color = x[0], x[1], y, radius
        assert color is not None
        pygame.draw.circle(self.surface, (*color, 255), (int(x), int(y)), int(radius))

    def compose(self, target: pygame.Surface) -> None:
        target.blit(self.surface, (0, 0), special_flags=pygame.BLEND_ADD)


class FxSystem:
    MAX_PARTICLES = 1000

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self.particles: list[dict[str, float | RGB]] = []
        self.reduced_shake = False
        self.reduced_flash = False
        self.shake = 0.0
        self.flash_alpha = 0.0

    def burst(self, x: float, y: float, color: RGB, count: int) -> None:
        for _ in range(count):
            angle = self.rng.uniform(0.0, 2 * math.pi)
            speed = self.rng.uniform(1.0, 6.0)
            life = self.rng.uniform(0.25, 0.8)
            self.particles.append({
                "x": x, "y": y, "vx": speed * math.cos(angle),
                "vy": speed * math.sin(angle), "life": life,
                "max_life": life, "color": color,
            })
        del self.particles[:-self.MAX_PARTICLES]

    def update(self, dt: float) -> None:
        alive = []
        for particle in self.particles:
            particle["x"] = float(particle["x"]) + float(particle["vx"]) * dt * 60
            particle["y"] = float(particle["y"]) + float(particle["vy"]) * dt * 60
            particle["life"] = float(particle["life"]) - dt
            if float(particle["life"]) > 0:
                alive.append(particle)
        self.particles = alive
        self.shake *= max(0.0, 1.0 - dt * 8)
        self.flash_alpha = max(0.0, self.flash_alpha - dt * 2)

    def kick(self, amount: float) -> None:
        if not self.reduced_shake:
            self.shake = max(self.shake, amount)

    def flash(self, _color: RGB, amount: float) -> None:
        self.flash_alpha = min(1.0, amount if not self.reduced_flash else min(0.25, amount))
