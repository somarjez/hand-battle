from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import pygame

from ..models import Element, GestureFrame, REFERENCE_SIZE
from ..session import GameEvent, GameSnapshot
from .battle_view import BattleView, cover_resize
from . import art
from .effects import RGB, mix, scale_color
from .screens import ScreenDrawing


ELEMENT_COLORS = {
    Element.EARTH: (191, 132, 76),
    Element.WATER: (74, 180, 245),
    Element.AIR: (214, 238, 230),
    Element.FIRE: (255, 111, 58),
    Element.LIGHTNING: (255, 218, 92),
}

# Colour grade for each stage so the story screens feel different.
LEVEL_TINT: dict[str, RGB] = {
    "stonewake": (120, 80, 40),
    "tidelost": (30, 90, 150),
    "skyglass": (110, 150, 160),
    "cinderforge": (170, 60, 20),
    "eclipse": (90, 40, 130),
}


def surface_to_bgr(surface: pygame.Surface) -> np.ndarray:
    """pygame surface -> BGR image (only used when a caller has no OpenCV frame)."""
    rgb = pygame.surfarray.array3d(surface).transpose(1, 0, 2)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def bgr_to_surface(image: np.ndarray) -> pygame.Surface:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return pygame.image.frombuffer(rgb, (image.shape[1], image.shape[0]), "RGB")


class GameRenderer(ScreenDrawing):
    def __init__(self, logical_size: tuple[int, int] = REFERENCE_SIZE, asset_root: Path | None = None):
        self.width, self.height = logical_size
        self.asset_root = asset_root or Path(__file__).parents[1] / "assets"
        self._fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self._scene_bgr: dict[tuple[str, tuple[int, int]], np.ndarray] = {}
        self._stage = "menu"
        self._backgrounds: dict[str, pygame.Surface | None] = {}
        self._scaled_bg: dict[tuple[str, tuple[int, int]], pygame.Surface] = {}
        self._text_cache: dict[tuple, pygame.Surface] = {}
        self.battle = BattleView()
        self._portraits: dict = {}
        self._embers = [(random.random(), random.random(), random.uniform(0.02, 0.07), random.uniform(1.5, 3.6), i % 3)
                        for i in range(46)]
        self._clock = 0.0

    # ---- accessibility ---------------------------------------------------------
    @property
    def reduced_flash(self) -> bool:
        return self.battle.reduced_flash

    @reduced_flash.setter
    def reduced_flash(self, value: bool) -> None:
        self.battle.reduced_flash = bool(value)

    @property
    def reduced_shake(self) -> bool:
        return self.battle.reduced_shake

    @reduced_shake.setter
    def reduced_shake(self, value: bool) -> None:
        self.battle.reduced_shake = bool(value)

    # ---- creature portraits for the menus --------------------------------------
    def sprite_surface(self, kind: str, radius: float, phase: float = 0.0, silhouette: bool = False,
                       height: int | None = None) -> pygame.Surface | None:
        """A pygame surface of a creature (animated by ``phase`` in cycles), or None for an unknown kind."""
        book = self.battle.sprites
        if not book.has(kind):
            return None
        n = int(phase * 8) % 8
        key = (kind, book.bucket(radius), n, silhouette, height)
        surf = self._portraits.get(key)
        if surf is None:
            arr = book.rgba_frame(kind, radius, phase, silhouette)
            surf = pygame.image.frombuffer(arr.tobytes(), (arr.shape[1], arr.shape[0]), "RGBA")
            if height and height != surf.get_height():
                w = max(1, int(surf.get_width() * height / surf.get_height()))
                surf = pygame.transform.smoothscale(surf, (w, height))
            self._portraits[key] = surf
        return surf

    # ---- text / fonts ----------------------------------------------------------
    def font(self, size: int, bold: bool = False) -> pygame.font.Font:
        if not pygame.font.get_init():
            pygame.font.init()
        key = (size, bold)
        if key not in self._fonts:
            fonts = self.asset_root / "fonts"
            path = fonts / ("AlegreyaSC-Bold.ttf" if bold else "Alegreya-Variable.ttf")
            try:                                          # the bundled Alegreya; Alegreya reads small, so scale it up a little
                self._fonts[key] = pygame.font.Font(str(path), int(size * 1.14))
            except (FileNotFoundError, pygame.error):
                self._fonts[key] = pygame.font.SysFont("segoeui", size, bold=bold)
        return self._fonts[key]

    def _text(self, target, text: str, size: int, pos, color=(238, 244, 248), center=False,
              outline: bool = False, bold: bool = False, anchor: str | None = None):
        key = (text, size, color, outline, bold)
        image = self._text_cache.get(key)
        if image is None:
            if len(self._text_cache) > 600:
                self._text_cache.clear()
            base = self.font(size, bold).render(text, True, color)
            if outline:
                dark = self.font(size, bold).render(text, True, (6, 8, 14))
                image = pygame.Surface((base.get_width() + 4, base.get_height() + 4), pygame.SRCALPHA)
                for ox, oy in ((0, 2), (4, 2), (2, 0), (2, 4), (0, 0), (4, 4), (0, 4), (4, 0)):
                    image.blit(dark, (ox, oy))
                image.blit(base, (2, 2))
            else:
                image = base
            self._text_cache[key] = image
        if anchor:                                           # e.g. "midleft" / "midright" for vertically centred rows
            rect = image.get_rect(**{anchor: pos})
        else:
            rect = image.get_rect(center=pos) if center else image.get_rect(topleft=pos)
        target.blit(image, rect)
        return rect

    # ---- backgrounds -----------------------------------------------------------
    def _background(self, target: pygame.Surface, name: str = "menu") -> None:
        """Paint the stage scene over the whole canvas. Drop a PNG in assets/images/override/<stage>.png to replace one."""
        self._stage = name
        size = target.get_size()
        override = self.asset_root / "images" / "override" / f"{name}.png"
        if override.exists():
            key = (name, size)
            scaled = self._scaled_bg.get(key)
            if scaled is None:
                try:
                    image = pygame.image.load(override)
                    if pygame.display.get_surface() is not None:
                        image = image.convert()
                except (pygame.error, FileNotFoundError):
                    image = None
                if image is not None:
                    k = max(size[0] / image.get_width(), size[1] / image.get_height())
                    big = pygame.transform.smoothscale(image, (max(size[0], int(image.get_width() * k)), max(size[1], int(image.get_height() * k))))
                    scaled = big.subsurface(pygame.Rect((big.get_width() - size[0]) // 2, (big.get_height() - size[1]) // 2, *size)).copy()
                    self._scaled_bg[key] = scaled
            if scaled is not None:
                target.blit(scaled, (0, 0))
                return
        target.blit(art.stage_scene(name, size), (0, 0))

    def stage_backdrop(self, stage: str, size: tuple[int, int]) -> np.ndarray:
        """The stage scene as a BGR image, for play without a camera."""
        key = (stage, size)
        image = self._scene_bgr.get(key)
        if image is None:
            image = surface_to_bgr(art.stage_scene(stage, size))
            self._scene_bgr[key] = image
        return image

    def _ui(self, target: pygame.Surface, name: str) -> pygame.Surface:
        """Paint the background over the whole canvas and return the centred 1280x720 area for UI."""
        self._background(target, name)
        tw, th = target.get_size()
        rect = pygame.Rect((tw - self.width) // 2, (th - self.height) // 2, self.width, self.height).clip(target.get_rect())
        return target.subsurface(rect)

    def _draw_embers(self, target: pygame.Surface, tint: RGB | None = None) -> None:
        """Ambient motion for the current stage: fireflies, a sweeping lamp, rising embers."""
        art.animate(self._stage, target, self._clock)

    def _panel(self, target, rect, alpha=205):
        art.draw_panel(target, rect, alpha)

    # ---- menu / story / calibration -------------------------------------------
    def draw_menu(self, target: pygame.Surface, items: list[str], selected: int) -> list[pygame.Rect]:
        self._clock = pygame.time.get_ticks() / 1000.0
        full = target
        target = self._ui(full, "menu")
        self._draw_embers(full)
        glow = 0.5 + 0.5 * math.sin(self._clock * 2.0)
        self._text(target, "ELEMENTAL", 31, (self.width // 2, 82), (174, 207, 222), True)
        self._text(target, "CONVERGENCE", 64, (self.width // 2, 135), mix((248, 245, 226), (255, 226, 160), glow), True, outline=True)
        self._text(target, "A gesture-controlled elemental journey", 22, (self.width // 2, 184), (160, 184, 200), True)
        rects = []
        start = 245
        for index, label in enumerate(items):
            rect = pygame.Rect(self.width // 2 - 190, start + index * 52, 380, 42)
            active = index == selected
            if active:
                rect = rect.inflate(int(10 + 6 * glow), 0)
            fill = (42, 106, 136, 235) if active else (8, 18, 31, 205)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.fill(fill)
            border = mix((118, 187, 210), (255, 235, 170), glow) if active else (118, 187, 210)
            pygame.draw.rect(panel, border, panel.get_rect(), 2, border_radius=10)
            target.blit(panel, rect)
            self._text(target, label, 24, rect.center, (255, 250, 235) if active else (238, 244, 248), center=True)
            if active:
                for sx in (-1, 1):
                    tip = (rect.centerx + sx * (rect.w // 2 - 16), rect.centery)
                    pygame.draw.polygon(target, (255, 226, 150), [(tip[0], tip[1] - 6), (tip[0] - sx * 10, tip[1]), (tip[0], tip[1] + 6)])
            rects.append(pygame.Rect(self.width // 2 - 190, start + index * 52, 380, 42))
        self._text(target, "Arrow keys / mouse • Enter to select • Esc to go back", 18, (self.width // 2, 688), (144, 165, 180), True)
        return rects

    def draw_story(self, target: pygame.Surface, title: str, lines: Iterable[str], stage: str) -> None:
        self._clock = pygame.time.get_ticks() / 1000.0
        full = target
        target = self._ui(full, stage)
        veil = pygame.Surface(full.get_size(), pygame.SRCALPHA)
        veil.fill((3, 7, 15, 115))
        full.blit(veil, (0, 0))
        self._draw_embers(full)
        panel = pygame.Rect(110, 390, 1060, 245)
        self._panel(target, panel, 225)
        self._text(target, title, 38, (150, 425), (255, 221, 145))
        for index, line in enumerate(lines):
            self._text(target, line, 25, (150, 485 + index * 40))
        pulse = 0.6 + 0.4 * math.sin(self._clock * 3.0)
        self._text(target, "Enter — continue", 18, (1020, 598), scale_color((165, 194, 208), 0.6 + 0.4 * pulse))

    def draw_calibration(
        self,
        target: pygame.Surface,
        frame: GestureFrame,
        missing: Iterable[Element],
        camera_surface: pygame.Surface | None = None,
    ) -> None:
        target = self._ui(target, "calibration")
        self._text(target, "Camera & Gesture Calibration", 42, (self.width // 2, 60), center=True)
        self._text(target, "Center both hands in good light, then hold each pose.", 22, (self.width // 2, 105), (170, 192, 206), True)
        preview = pygame.Rect(70, 145, 760, 470)
        self._panel(target, preview)
        if camera_surface is not None:
            inner = preview.inflate(-36, -36)
            target.blit(bgr_to_surface(cover_resize(surface_to_bgr(camera_surface), inner.size)), inner)
            shade = pygame.Surface(inner.size, pygame.SRCALPHA)
            shade.fill((3, 8, 16, 35))
            target.blit(shade, inner)
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

    def draw_camera_cover(self, target: pygame.Surface, image: np.ndarray | None) -> None:
        """Camera picture filling the whole canvas (cropped, never stretched)."""
        target.fill((8, 14, 25))
        if image is not None:
            target.blit(bgr_to_surface(cover_resize(image, target.get_size())), (0, 0))

    # ---- gameplay (OpenCV look, see battle_view.py) -----------------------------
    def reset_fx(self) -> None:
        """Call when a level starts so no particles or banners leak between runs."""
        self.battle.reset()

    def update_fx(self, dt: float, snapshot: GameSnapshot, events: Iterable[GameEvent] = (),
                  frame: GestureFrame | None = None) -> None:
        """Advance animations and react to this frame's game events. Skip while paused."""
        self._clock += dt
        self.battle.update(dt, snapshot, events, frame)

    def draw_gameplay(
        self,
        target: pygame.Surface,
        snapshot: GameSnapshot,
        camera_surface: pygame.Surface | None = None,
        frame: GestureFrame | None = None,
        camera_image: np.ndarray | None = None,
    ) -> None:
        """Draw the battle over the camera picture, filling the whole canvas.

        `camera_image` (BGR, straight from OpenCV) is preferred; a pygame surface also works.
        `frame` must use the same canvas coordinates as the session (see models.scale_frame).
        """
        if camera_image is None and camera_surface is not None:
            camera_image = surface_to_bgr(camera_surface)
        if camera_image is None:
            camera_image = self.stage_backdrop(snapshot.level_id, target.get_size())
        image = self.battle.render(snapshot, frame, camera_image, target.get_size())
        target.blit(bgr_to_surface(image), (0, 0))

    def draw_overlay(self, target: pygame.Surface, title: str, lines: Iterable[str]) -> None:
        shade = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 175))
        target.blit(shade, (0, 0))
        tw, th = target.get_size()
        target = target.subsurface(pygame.Rect((tw - self.width) // 2, (th - self.height) // 2, self.width, self.height).clip(target.get_rect()))
        panel = pygame.Rect(260, 150, 760, 420)
        self._panel(target, panel, 240)
        self._text(target, title, 46, (self.width // 2, 210), (255, 224, 151), True)
        lines = list(lines)
        spacing = min(48.0, 250.0 / max(1, len(lines) - 1))
        for index, line in enumerate(lines):
            self._text(target, line, 23, (self.width // 2, int(285 + index * spacing)), center=True)
