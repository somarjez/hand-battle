"""Menu-style screens, drawn on top of the renderer's helpers.

Every ``draw_*`` method that has clickable parts returns a list of ``Row`` objects holding rectangles in
*canvas* coordinates, so the app can do mouse hover / click / slider dragging without knowing the layout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import pygame

from ..menus import Menu
from .effects import mix, scale_color

GOLD = (255, 224, 151)
INK = (238, 244, 248)
DIM = (150, 170, 184)
STAR_ON = (255, 214, 90)
STAR_OFF = (60, 72, 86)


@dataclass(frozen=True)
class Row:
    rect: pygame.Rect                      # whole clickable row, canvas coordinates
    bar: pygame.Rect | None = None         # slider track (for mouse dragging)


def star_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rad = r if k % 2 == 0 else r * 0.45
        pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
    return pts


class ScreenDrawing:
    """Mixin for GameRenderer (needs _text, _panel, _ui, _draw_embers, _clock, width, height)."""

    # ------------------------------------------------------------------ helpers
    def _wrap(self, text: str, size: int, max_width: int, bold: bool = False) -> list[str]:
        font = self.font(size, bold)
        lines: list[str] = []
        for paragraph in text.split("\n"):
            line = ""
            for word in paragraph.split():
                trial = f"{line} {word}".strip()
                if font.size(trial)[0] <= max_width or not line:
                    line = trial
                else:
                    lines.append(line)
                    line = word
            lines.append(line)
        return lines

    @staticmethod
    def _abs(ui: pygame.Surface, rect: pygame.Rect) -> pygame.Rect:
        ox, oy = ui.get_abs_offset()
        return rect.move(ox, oy)

    def _star(self, target: pygame.Surface, cx: float, cy: float, r: float, filled: bool) -> None:
        pts = star_points(cx, cy, r)
        pygame.draw.polygon(target, STAR_ON if filled else STAR_OFF, pts)
        pygame.draw.polygon(target, (255, 244, 200) if filled else (90, 104, 120), pts, 2)

    def _title_block(self, target: pygame.Surface, title: str, subtitle: str, compact: bool, glow: float) -> None:
        cx = self.width // 2
        if compact:
            self._text(target, title, 44, (cx, 70), GOLD, True, outline=True, bold=True)
            if subtitle:
                self._text(target, subtitle, 20, (cx, 112), (200, 216, 226), True, outline=True)
        else:
            self._text(target, "ELEMENTAL", 31, (cx, 70), (174, 207, 222), True)
            self._text(target, "CONVERGENCE", 64, (cx, 122), mix((248, 245, 226), GOLD, glow), True, outline=True)
            if subtitle:
                self._text(target, subtitle, 22, (cx, 172), (214, 228, 238), True, outline=True)

    # ------------------------------------------------------------------ generic menu
    def draw_menu_screen(self, target: pygame.Surface, menu: Menu, title: str = "", subtitle: str = "",
                         stage: str = "menu", wide: bool = False, y0: int = 235, row_h: int = 50,
                         footer: str = "", compact: bool = False) -> list[Row]:
        """Buttons, sliders, toggles and choices, with a highlighted row, hint line and key help."""
        self._clock = pygame.time.get_ticks() / 1000.0
        full = target
        ui = self._ui(full, stage)
        self._draw_embers(full)
        glow = 0.5 + 0.5 * math.sin(self._clock * 2.0)
        self._title_block(ui, title, subtitle, compact, glow)
        width = 700 if wide else 400
        rows: list[Row] = []
        for index, item in enumerate(menu.items):
            rect = pygame.Rect((self.width - width) // 2, y0 + index * row_h, width, row_h - 8)
            base_right = rect.right
            active = index == menu.index
            if active:
                rect = rect.inflate(int(8 + 6 * glow), 0)
            alpha = 235 if active else 200
            fill = (42, 106, 136, alpha) if active else (8, 18, 31, alpha)
            if not item.enabled:
                fill = (14, 20, 28, 170)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.fill(fill)
            border = mix((118, 187, 210), (255, 235, 170), glow) if active else (86, 128, 148)
            pygame.draw.rect(panel, border if item.enabled else (60, 72, 84), panel.get_rect(), 2, border_radius=10)
            ui.blit(panel, rect)
            color = INK if item.enabled else (96, 108, 120)
            if active and item.enabled:
                color = (255, 250, 235)
            bar_rect = None
            if item.kind == "button":
                self._text(ui, item.label, 24, rect.center, color, True)
            else:
                self._text(ui, item.label, 22, (rect.x + 20, rect.centery), color, anchor="midleft")
                if item.kind == "slider":
                    bar_rect = pygame.Rect(base_right - 320, rect.centery - 6, 220, 12)
                    value = float(item.get())
                    pygame.draw.rect(ui, (18, 28, 40), bar_rect, border_radius=6)
                    if value > 0:
                        pygame.draw.rect(ui, GOLD if active else (118, 187, 210),
                                         (bar_rect.x, bar_rect.y, max(8, int(bar_rect.w * value)), bar_rect.h), border_radius=6)
                    pygame.draw.rect(ui, (150, 190, 205), bar_rect, 1, border_radius=6)
                    knob = (bar_rect.x + int(bar_rect.w * value), bar_rect.centery)
                    pygame.draw.circle(ui, (255, 255, 255), knob, 9)
                    pygame.draw.circle(ui, (40, 80, 110), knob, 9, 2)
                    self._text(ui, item.value_text(), 20, (rect.right - 18, rect.centery), color, anchor="midright")
                else:
                    text = item.value_text()
                    value_color = (110, 230, 160) if (item.kind == "toggle" and item.get()) else color
                    surf = self.font(22, True).render(f"< {text} >" if active else text, True, value_color)
                    ui.blit(surf, surf.get_rect(midright=(rect.right - 20, rect.centery)))
            rows.append(Row(self._abs(ui, rect), self._abs(ui, bar_rect) if bar_rect else None))
        current = menu.current
        hint = current.hint or footer
        if hint:
            self._text(ui, hint, 19, (self.width // 2, min(672, y0 + len(menu.items) * row_h + 14)), (214, 228, 238), True, outline=True)
        self._text(ui, "Up / Down choose    Left / Right change    Enter select    Esc back    or use the mouse", 17,
                   (self.width // 2, 702), (176, 196, 210), True, outline=True)
        return rows

    # ------------------------------------------------------------------ level select
    def draw_level_select(self, target: pygame.Surface, cards: Sequence[dict[str, Any]], selected: int) -> list[Row]:
        self._clock = pygame.time.get_ticks() / 1000.0
        full = target
        ui = self._ui(full, "menu")
        self._draw_embers(full)
        self._text(ui, "SELECT A SEAL", 44, (self.width // 2, 60), GOLD, True, outline=True, bold=True)
        n = len(cards)
        gap, card_w = 14, 232
        total = n * card_w + (n - 1) * gap
        x0 = (self.width - total) // 2
        rows: list[Row] = []
        pulse = 0.5 + 0.5 * math.sin(self._clock * 3.0)
        for i, card in enumerate(cards):
            rect = pygame.Rect(x0 + i * (card_w + gap), 120, card_w, 360)
            active = i == selected
            if active:
                rect = rect.inflate(0, 0).move(0, -8)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            unlocked = card["unlocked"]
            panel.fill((12, 24, 38, 235) if unlocked else (10, 14, 20, 225))
            border = mix((118, 187, 210), (255, 235, 170), pulse) if active else ((86, 128, 148) if unlocked else (52, 62, 72))
            pygame.draw.rect(panel, border, panel.get_rect(), 3 if active else 2, border_radius=14)
            ui.blit(panel, rect)
            tint = card.get("tint", (118, 187, 210))
            pygame.draw.rect(ui, scale_color(tint, 0.55 if unlocked else 0.18), (rect.x + 10, rect.y + 10, rect.w - 20, 70), border_radius=10)
            self._text(ui, f"{card['number']}", 46, (rect.centerx, rect.y + 45), INK if unlocked else (90, 100, 112), True, bold=True)
            title_color = GOLD if unlocked else (100, 112, 124)
            for k, line in enumerate(self._wrap(card["title"], 24, rect.w - 24, True)[:2]):
                self._text(ui, line, 24, (rect.centerx, rect.y + 108 + k * 28), title_color, True, bold=True)
            if unlocked:
                self._text(ui, card["subtitle"], 17, (rect.centerx, rect.y + 168), DIM, True)
                self._text(ui, card["keeper"], 16, (rect.centerx, rect.y + 192), (186, 202, 214), True)
                self._text(ui, f"Hazard: {card['hazard']}", 16, (rect.centerx, rect.y + 224), (255, 190, 120), True)
                for s in range(3):
                    self._star(ui, rect.centerx + (s - 1) * 44, rect.y + 278, 17, s < card["stars"])
                best = f"Best {card['best']:,}" if card["best"] else "Not cleared"
                self._text(ui, best, 18, (rect.centerx, rect.y + 322), INK if card["best"] else DIM, True)
            else:
                self._text(ui, "LOCKED", 22, (rect.centerx, rect.y + 190), (120, 132, 144), True, bold=True)
                for k, line in enumerate(self._wrap("Restore the previous seal to open this stage.", 16, rect.w - 40)):
                    self._text(ui, line, 16, (rect.centerx, rect.y + 224 + k * 22), (100, 112, 124), True)
            rows.append(Row(self._abs(ui, rect)))
        card = cards[selected]
        info = pygame.Rect(self.width // 2 - 520, 500, 1040, 150)
        self._panel(ui, info, 215)
        if card["unlocked"]:
            for k, line in enumerate(self._wrap(card["intro"], 20, info.w - 50)[:3]):
                self._text(ui, line, 20, (info.x + 25, info.y + 20 + k * 30), INK)
            self._text(ui, "Enter: play this seal", 17, (info.right - 25, info.bottom - 18), GOLD, anchor="bottomright")
        else:
            self._text(ui, "This seal is still sealed. Clear the stage before it first.", 20, (info.x + 25, info.y + 24), DIM)
        self._text(ui, "Left / Right choose    Enter play    Esc back    or click a card", 17, (self.width // 2, 702), (176, 196, 210), True, outline=True)
        return rows

    # ------------------------------------------------------------------ results & pause
    def draw_results(self, target: pygame.Surface, data: dict[str, Any], menu: Menu) -> list[Row]:
        shade = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 190))
        target.blit(shade, (0, 0))
        ui = self._ui_view(target)
        won = data["complete"]
        panel = pygame.Rect(240, 40, 800, 640)
        self._panel(ui, panel, 238)
        cx = self.width // 2
        self._text(ui, "SEAL RESTORED" if won else "THE RIFT PREVAILS", 50, (cx, 92), GOLD if won else (255, 110, 100), True, outline=True, bold=True)
        self._text(ui, data["title"], 22, (cx, 136), DIM, True)
        if won:
            for s in range(3):
                self._star(ui, cx + (s - 1) * 84, 196, 30, s < data["stars"])
            labels = {1: "Seal restored", 2: "No life lost", 3: "Flawless: few hits taken"}
            self._text(ui, labels[max(1, data["stars"])], 18, (cx, 238), (214, 226, 234), True)
        stats = [("Score", f"{data['score']:,}" + ("   NEW BEST!" if data["new_best"] else "")),
                 ("Best combo", f"x{data['max_combo']}"), ("Hits taken", str(data["hits"])), ("Time", data["time"])]
        for k, (name, value) in enumerate(stats):
            y = 282 + k * 30
            self._text(ui, name, 21, (cx - 190, y), DIM)
            self._text(ui, value, 21, (cx + 190, y), GOLD if k == 0 and data["new_best"] else INK)
        story = data["story"]
        for k, line in enumerate(self._wrap(story, 19, 660)[:3]):
            self._text(ui, line, 19, (cx, 420 + k * 26), (190, 206, 218), True)
        return self._menu_rows(ui, menu, 4, 508, 380, 46)

    def draw_pause(self, target: pygame.Surface, menu: Menu, title: str, lines: Iterable[str]) -> list[Row]:
        shade = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 175))
        target.blit(shade, (0, 0))
        ui = self._ui_view(target)
        panel = pygame.Rect(self.width // 2 - 260, 90, 520, 540)
        self._panel(ui, panel, 238)
        self._text(ui, "PAUSED", 50, (self.width // 2, 146), GOLD, True, outline=True, bold=True)
        self._text(ui, title, 21, (self.width // 2, 192), DIM, True)
        for k, line in enumerate(lines):
            self._text(ui, line, 18, (self.width // 2, 228 + k * 24), (190, 206, 218), True)
        return self._menu_rows(ui, menu, 4, 330, 360, 54)

    def _ui_view(self, target: pygame.Surface) -> pygame.Surface:
        tw, th = target.get_size()
        return target.subsurface(pygame.Rect((tw - self.width) // 2, (th - self.height) // 2, self.width, self.height).clip(target.get_rect()))

    def _menu_rows(self, ui: pygame.Surface, menu: Menu, _count: int, y0: int, width: int, row_h: int) -> list[Row]:
        rows: list[Row] = []
        glow = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 1000.0 * 2.0)
        for i, item in enumerate(menu.items):
            rect = pygame.Rect((self.width - width) // 2, y0 + i * row_h, width, row_h - 8)
            active = i == menu.index
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.fill((42, 106, 136, 235) if active else (8, 18, 31, 205))
            pygame.draw.rect(panel, mix((118, 187, 210), (255, 235, 170), glow) if active else (86, 128, 148), panel.get_rect(), 2, border_radius=10)
            ui.blit(panel, rect)
            self._text(ui, item.label, 23, rect.center, (255, 250, 235) if active else INK, True)
            rows.append(Row(self._abs(ui, rect)))
        return rows

    # ------------------------------------------------------------------ codex
    def draw_codex(self, target: pygame.Surface, tabs: Sequence[str], tab: int, entries: Sequence[dict[str, Any]],
                   index: int) -> list[Row]:
        self._clock = pygame.time.get_ticks() / 1000.0
        full = target
        ui = self._ui(full, "menu")
        self._draw_embers(full)
        self._text(ui, "CODEX", 44, (self.width // 2, 54), GOLD, True, outline=True, bold=True)
        for i, name in enumerate(tabs):
            rect = pygame.Rect(self.width // 2 - 220 + i * 230, 92, 210, 36)
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.fill((42, 106, 136, 235) if i == tab else (8, 18, 31, 205))
            pygame.draw.rect(panel, (118, 187, 210), panel.get_rect(), 2, border_radius=10)
            ui.blit(panel, rect)
            self._text(ui, name, 21, rect.center, INK, True, bold=(i == tab))
        left = pygame.Rect(60, 144, 380, 520)
        right = pygame.Rect(460, 144, 760, 520)
        self._panel(ui, left, 215)
        self._panel(ui, right, 215)
        rows: list[Row] = []
        visible = 11
        start = max(0, min(index - visible // 2, max(0, len(entries) - visible)))
        for k, entry in enumerate(entries[start:start + visible]):
            i = start + k
            rect = pygame.Rect(left.x + 12, left.y + 14 + k * 44, left.w - 24, 38)
            if i == index:
                pygame.draw.rect(ui, (42, 106, 136), rect, border_radius=8)
                pygame.draw.rect(ui, (255, 235, 170), rect, 2, border_radius=8)
            label = entry["name"] if entry["unlocked"] else "???"
            self._text(ui, label, 20, (rect.x + 14, rect.centery - 12), INK if entry["unlocked"] else (100, 112, 124))
            rows.append(Row(self._abs(ui, rect)))
        if entries:
            entry = entries[index]
            self._text(ui, entry["name"] if entry["unlocked"] else "Undiscovered", 30, (right.x + 28, right.y + 22), GOLD, bold=True)
            if entry.get("subtitle"):
                self._text(ui, entry["subtitle"], 19, (right.x + 28, right.y + 64), DIM)
            body = entry["text"] if entry["unlocked"] else entry["locked_text"]
            for k, line in enumerate(self._wrap(body, 21, right.w - 56)[:9]):
                self._text(ui, line, 21, (right.x + 28, right.y + 112 + k * 30), INK if entry["unlocked"] else DIM)
            for k, line in enumerate(entry.get("facts", ()) if entry["unlocked"] else ()):
                self._text(ui, line, 18, (right.x + 28, right.bottom - 90 + k * 26), (255, 190, 120))
        self._text(ui, "Left / Right switch tab    Up / Down choose    Esc back", 17, (self.width // 2, 702), (176, 196, 210), True, outline=True)
        return rows

    # ------------------------------------------------------------------ paged text (how to play) and story scenes
    def draw_pages(self, target: pygame.Surface, title: str, heading: str, lines: Sequence[str], page: int, pages: int) -> None:
        self._clock = pygame.time.get_ticks() / 1000.0
        full = target
        ui = self._ui(full, "menu")
        self._draw_embers(full)
        self._text(ui, title, 44, (self.width // 2, 60), GOLD, True, outline=True, bold=True)
        panel = pygame.Rect(170, 120, 940, 470)
        self._panel(ui, panel, 225)
        self._text(ui, heading, 34, (panel.x + 36, panel.y + 28), GOLD, bold=True)
        y = panel.y + 100
        for line in lines:
            for wrapped in self._wrap(line, 24, panel.w - 80):
                self._text(ui, wrapped, 24, (panel.x + 40, y), INK)
                y += 36
            y += 12
        for i in range(pages):
            pygame.draw.circle(ui, GOLD if i == page else (70, 90, 108), (self.width // 2 + (i - (pages - 1) / 2) * 26, 626), 7)
        self._text(ui, "Left / Right turn page    Esc back", 17, (self.width // 2, 702), (176, 196, 210), True, outline=True)

    def draw_text_scene(self, target: pygame.Surface, title: str, lines: Sequence[str], stage: str, revealed: float,
                        footer: str = "Enter: continue") -> bool:
        """Lines fade in one after another. Returns True once every line is fully visible."""
        self._clock = pygame.time.get_ticks() / 1000.0
        full = target
        ui = self._ui(full, stage)
        veil = pygame.Surface(full.get_size(), pygame.SRCALPHA)
        veil.fill((3, 7, 15, 150))
        full.blit(veil, (0, 0))
        self._draw_embers(full)
        self._text(ui, title, 46, (self.width // 2, 110), GOLD, True, outline=True, bold=True)
        y = 190
        for i, line in enumerate(lines):
            fade = max(0.0, min(1.0, revealed - i))
            rows = self._wrap(line, 26, 940)
            for wrapped in rows:
                if fade > 0:
                    self._text(ui, wrapped, 26, (self.width // 2, y), scale_color(INK, 0.15 + 0.85 * fade), True, outline=True)
                y += 36
            y += 18
        done = revealed >= len(lines)
        if done:
            pulse = 0.55 + 0.45 * math.sin(self._clock * 3.0)
            self._text(ui, footer, 20, (self.width // 2, 672), scale_color(GOLD, pulse), True)
        else:
            self._text(ui, "Enter: skip", 17, (self.width // 2, 702), (176, 196, 210), True, outline=True)
        return done
