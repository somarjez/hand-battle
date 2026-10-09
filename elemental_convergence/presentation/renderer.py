from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pygame

from ..models import Element, GestureFrame
from ..session import GameSnapshot, SessionState


ELEMENT_COLORS = {
    Element.EARTH: (191, 132, 76),
    Element.WATER: (74, 180, 245),
    Element.AIR: (214, 238, 230),
    Element.FIRE: (255, 111, 58),
    Element.LIGHTNING: (255, 218, 92),
}


class GameRenderer:
    def __init__(self, logical_size: tuple[int, int] = (1280, 720), asset_root: Path | None = None):
        self.width, self.height = logical_size
        self.asset_root = asset_root or Path(__file__).parents[1] / "assets"
        self._fonts: dict[int, pygame.font.Font] = {}
        self._backgrounds: dict[str, pygame.Surface | None] = {}

    def font(self, size: int) -> pygame.font.Font:
        if not pygame.font.get_init():
            pygame.font.init()
        if size not in self._fonts:
            self._fonts[size] = pygame.font.SysFont("segoeui", size)
        return self._fonts[size]

    def _background(self, target: pygame.Surface, name: str = "menu") -> None:
        cached = self._backgrounds.get(name)
        if name not in self._backgrounds:
            path = self.asset_root / "images" / f"{name}.png"
            if not path.exists():
                path = self.asset_root / "images" / "menu.png"
            try:
                cached = pygame.image.load(path).convert()
            except (FileNotFoundError, pygame.error):
                cached = None
            self._backgrounds[name] = cached
        if cached is not None:
            target.blit(pygame.transform.smoothscale(cached, target.get_size()), (0, 0))
            return
        top, bottom = (8, 15, 31), (26, 46, 63)
        for y in range(target.get_height()):
            ratio = y / max(1, target.get_height() - 1)
            color = tuple(int(a + (b - a) * ratio) for a, b in zip(top, bottom))
            pygame.draw.line(target, color, (0, y), (target.get_width(), y))
        for x, color in ((180, (120, 76, 42)), (460, (40, 130, 180)), (820, (190, 78, 40)), (1080, (190, 160, 55))):
            pygame.draw.circle(target, (*color, 0), (x, 160), 160, 3)

    def _text(self, target, text: str, size: int, pos, color=(238, 244, 248), center=False):
        image = self.font(size).render(text, True, color)
        rect = image.get_rect(center=pos) if center else image.get_rect(topleft=pos)
        target.blit(image, rect)
        return rect

    def _panel(self, target, rect, alpha=205):
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((8, 14, 26, alpha))
        pygame.draw.rect(panel, (110, 154, 181, 130), panel.get_rect(), 2, border_radius=16)
        target.blit(panel, rect)

    def draw_menu(self, target: pygame.Surface, items: list[str], selected: int) -> list[pygame.Rect]:
        self._background(target, "menu")
        self._text(target, "ELEMENTAL", 31, (self.width // 2, 82), (174, 207, 222), True)
        self._text(target, "CONVERGENCE", 64, (self.width // 2, 135), (248, 245, 226), True)
        self._text(target, "A gesture-controlled elemental journey", 22, (self.width // 2, 184), (160, 184, 200), True)
        rects = []
        start = 245
        for index, label in enumerate(items):
            rect = pygame.Rect(self.width // 2 - 190, start + index * 52, 380, 42)
            fill = (42, 106, 136, 230) if index == selected else (8, 18, 31, 205)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.fill(fill)
            pygame.draw.rect(panel, (118, 187, 210), panel.get_rect(), 2, border_radius=10)
            target.blit(panel, rect)
            self._text(target, label, 24, rect.center, center=True)
            rects.append(rect)
        self._text(target, "Arrow keys / mouse • Enter to select • Esc to go back", 18, (self.width // 2, 688), (144, 165, 180), True)
        return rects

    def draw_story(self, target: pygame.Surface, title: str, lines: Iterable[str], stage: str) -> None:
        self._background(target, stage)
        veil = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        veil.fill((3, 7, 15, 115))
        target.blit(veil, (0, 0))
        panel = pygame.Rect(110, 390, 1060, 245)
        self._panel(target, panel, 225)
        self._text(target, title, 38, (150, 425), (255, 221, 145))
        for index, line in enumerate(lines):
            self._text(target, line, 25, (150, 485 + index * 40))
        self._text(target, "Enter — continue", 18, (1020, 598), (165, 194, 208))

    def draw_calibration(self, target: pygame.Surface, frame: GestureFrame, missing: Iterable[Element]) -> None:
        self._background(target, "calibration")
        self._text(target, "Camera & Gesture Calibration", 42, (self.width // 2, 60), center=True)
        self._text(target, "Center both hands in good light, then hold each pose.", 22, (self.width // 2, 105), (170, 192, 206), True)
        preview = pygame.Rect(70, 145, 760, 470)
        self._panel(target, preview)
        pygame.draw.rect(target, (99, 179, 207), preview.inflate(-100, -70), 2, border_radius=100)
        status = "CAMERA READY" if frame.camera_ok else "CAMERA NOT AVAILABLE — press C to retry"
        self._text(target, status, 20, (preview.centerx, 585), (112, 221, 167) if frame.camera_ok else (255, 118, 102), True)
        missing_set = set(missing)
        for index, element in enumerate(Element):
            y = 170 + index * 76
            color = (70, 188, 122) if element not in missing_set else ELEMENT_COLORS[element]
            pygame.draw.circle(target, color, (900, y + 18), 16)
            self._text(target, element.value.title(), 25, (930, y))
            self._text(target, "Detected" if element not in missing_set else "Waiting…", 17, (930, y + 31), color)
        self._text(target, "Space — use defaults   C — retry camera   Esc — back", 18, (self.width // 2, 680), (160, 181, 196), True)

    def draw_gameplay(self, target: pygame.Surface, snapshot: GameSnapshot, camera_surface: pygame.Surface | None) -> None:
        if camera_surface is None:
            self._background(target, snapshot.level_id or "arena")
        else:
            target.blit(pygame.transform.smoothscale(camera_surface, target.get_size()), (0, 0))
        veil = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        veil.fill((3, 7, 15, 70))
        target.blit(veil, (0, 0))
        self._panel(target, pygame.Rect(18, 16, 300, 92), 190)
        self._text(target, snapshot.level_title, 21, (36, 27), (240, 226, 184))
        hp_rect = pygame.Rect(36, 62, 240, 18)
        pygame.draw.rect(target, (35, 39, 48), hp_rect, border_radius=8)
        pygame.draw.rect(target, (70, 202, 119) if snapshot.hp > 30 else (240, 79, 74), (hp_rect.x, hp_rect.y, int(hp_rect.width * snapshot.hp / 100), hp_rect.height), border_radius=8)
        self._text(target, f"HP {int(snapshot.hp)}   Lives {'●' * snapshot.lives}{'○' * (3 - snapshot.lives)}", 17, (36, 84))
        objective = "FINAL GUARDIAN" if snapshot.state is SessionState.BOSS else f"WAVE {snapshot.wave_number}/3 • {snapshot.objective.replace('_', ' ').upper()}"
        self._text(target, objective, 25, (self.width // 2, 35), (255, 228, 150), True)
        self._text(target, f"SCORE {snapshot.score:05d}", 21, (1120, 28), center=True)

        for enemy in snapshot.enemies:
            x, y = (int(enemy.position[0]), int(enemy.position[1]))
            boss = "sovereign" in enemy.kind or "guardian" in enemy.kind
            radius = 54 if boss else 30
            pygame.draw.circle(target, (69, 24, 83), (x, y), radius + 7)
            pygame.draw.circle(target, (190, 69, 155) if boss else (135, 75, 166), (x, y), radius)
            pygame.draw.circle(target, (245, 216, 253), (x, y), max(6, radius // 4))
            bar = pygame.Rect(x - radius, y + radius + 10, radius * 2, 7)
            pygame.draw.rect(target, (25, 25, 31), bar)
            pygame.draw.rect(target, (236, 83, 109), (bar.x, bar.y, int(bar.width * max(0, enemy.hp) / enemy.max_hp), bar.height))

        bar_width = 116
        total = len(snapshot.unlocked_elements) * (bar_width + 10)
        start = (self.width - total) // 2
        for index, element in enumerate(snapshot.unlocked_elements):
            x = start + index * (bar_width + 10)
            rect = pygame.Rect(x, 645, bar_width, 48)
            self._panel(target, rect, 215)
            pygame.draw.rect(target, ELEMENT_COLORS[element], (x + 8, 678, int((bar_width - 16) * snapshot.mana[element] / 100), 7), border_radius=3)
            self._text(target, element.value.upper(), 16, (rect.centerx, 660), ELEMENT_COLORS[element], True)
        conv = pygame.Rect(410, 610, 460, 14)
        pygame.draw.rect(target, (21, 27, 39), conv, border_radius=7)
        pygame.draw.rect(target, (255, 220, 120), (conv.x, conv.y, int(conv.width * snapshot.convergence / 100), conv.height), border_radius=7)
        self._text(target, "CONVERGENCE — bring hands together when full", 16, (self.width // 2, 590), (235, 225, 186), True)

    def draw_overlay(self, target: pygame.Surface, title: str, lines: Iterable[str]) -> None:
        shade = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 175))
        target.blit(shade, (0, 0))
        panel = pygame.Rect(260, 150, 760, 420)
        self._panel(target, panel, 240)
        self._text(target, title, 46, (self.width // 2, 210), (255, 224, 151), True)
        for index, line in enumerate(lines):
            self._text(target, line, 23, (self.width // 2, 300 + index * 48), center=True)

