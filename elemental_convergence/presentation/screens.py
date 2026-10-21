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
from . import art, handsigns, howto_art
from .effects import mix, scale_color

GOLD = art.GOLD
INK = art.PAPER            # text colour on the dark panels
DIM = art.CREAM_DIM
STAR_ON = art.GOLD
STAR_OFF = (70, 58, 44)
ELEMENT_RGB = {"earth": (190, 130, 70), "water": (60, 200, 255), "air": (230, 255, 255),
               "fire": (255, 150, 0), "lightning": (90, 170, 255)}


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
        art.draw_sun(target, cx, cy, r, art.GOLD, filled)

    def _title_block(self, target: pygame.Surface, title: str, subtitle: str, compact: bool, glow: float) -> None:
        cx = self.width // 2
        if compact:
            self._text(target, title, 44, (cx, 70), GOLD, True, outline=True, bold=True)
            art.draw_weave(target, pygame.Rect(cx - 150, 94, 300, 10), 14)
            if subtitle:
                self._text(target, subtitle, 20, (cx, 122), (226, 214, 188), True, outline=True)
        else:
            t = pygame.time.get_ticks() / 1000.0
            self._text(target, "SINAG", 104, (cx, 112), art.PAPER, True, outline=True, bold=True)
            for sx in (-1, 1):                                  # a slowly turning sun on each side of the wordmark
                art.draw_sun(target, cx + sx * 232, 112, 34, art.GOLD, True, t * 0.25 * sx)
            art.draw_weave(target, pygame.Rect(cx - 190, 168, 380, 12), 16)
            if subtitle:
                self._text(target, subtitle, 22, (cx, 204), (236, 224, 196), True, outline=True)

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
            art.draw_button(ui, rect, active, item.enabled, glow)
            if active and item.enabled:                                   # a turning sun marks the choice
                for sx, edge in ((-1, rect.x - 6), (1, rect.right + 6)):
                    art.draw_sun(ui, edge + sx * 6, rect.centery, 9, art.GOLD, True, self._clock * 0.8)
            color = INK if item.enabled else (110, 98, 80)
            if active and item.enabled:
                color = (255, 248, 226)
            bar_rect = None
            if item.kind == "button":
                self._text(ui, item.label, 24, rect.center, color, True)
            else:
                self._text(ui, item.label, 22, (rect.x + 20, rect.centery), color, anchor="midleft")
                if item.kind == "slider":
                    bar_rect = pygame.Rect(base_right - 320, rect.centery - 6, 220, 12)
                    value = float(item.get())
                    pygame.draw.rect(ui, (12, 9, 7), bar_rect, border_radius=6)
                    if value > 0:
                        pygame.draw.rect(ui, GOLD if active else (176, 132, 56),
                                         (bar_rect.x, bar_rect.y, max(8, int(bar_rect.w * value)), bar_rect.h), border_radius=6)
                    pygame.draw.rect(ui, (120, 96, 52), bar_rect, 1, border_radius=6)
                    knob = (bar_rect.x + int(bar_rect.w * value), bar_rect.centery)
                    pygame.draw.circle(ui, (255, 255, 255), knob, 9)
                    pygame.draw.circle(ui, (40, 80, 110), knob, 9, 2)
                    self._text(ui, item.value_text(), 20, (rect.right - 18, rect.centery), color, anchor="midright")
                else:
                    text = item.value_text()
                    value_color = (150, 214, 130) if (item.kind == "toggle" and item.get()) else color
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
        self._text(ui, "CHOOSE A PLACE", 44, (self.width // 2, 60), GOLD, True, outline=True, bold=True)
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
                rect = rect.move(0, -8)
            unlocked = card["unlocked"]
            art.draw_panel(ui, rect, 238 if unlocked else 215, band=False)
            if active:
                pygame.draw.polygon(ui, mix(art.GOLD, art.PAPER, pulse * 0.5), art.chamfer(rect, 14), 3)
            tint = card.get("tint", (118, 187, 210))
            pygame.draw.rect(ui, scale_color(tint, 0.55 if unlocked else 0.18), (rect.x + 10, rect.y + 10, rect.w - 20, 70), border_radius=10)
            self._text(ui, f"{card['number']}", 46, (rect.centerx, rect.y + 45), INK if unlocked else (90, 100, 112), True, bold=True)
            title_color = GOLD if unlocked else (100, 112, 124)
            for k, line in enumerate(self._wrap(card["title"], 24, rect.w - 24, True)[:2]):
                self._text(ui, line, 24, (rect.centerx, rect.y + 108 + k * 28), title_color, True, bold=True)
            if unlocked:
                native, _, english = card["subtitle"].partition(": ")
                self._text(ui, native, 20, (rect.centerx, rect.y + 168), GOLD, True, bold=True)
                self._text(ui, english, 16, (rect.centerx, rect.y + 190), DIM, True)
                self._text(ui, card["keeper"], 17, (rect.centerx, rect.y + 218), INK, True)
                self._text(ui, f"Hazard: {card['hazard']}", 16, (rect.centerx, rect.y + 244), (240, 170, 96), True)
                for s in range(3):
                    self._star(ui, rect.centerx + (s - 1) * 44, rect.y + 292, 17, s < card["stars"])
                best = f"Best {card['best']:,}" if card["best"] else "Not cleared"
                self._text(ui, best, 18, (rect.centerx, rect.y + 334), INK if card["best"] else DIM, True)
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
            self._text(ui, line, 19, (cx, 420 + k * 26), (226, 214, 188), True)
        return self._menu_rows(ui, menu, 4, 496, 380, 44)

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
            self._text(ui, line, 18, (self.width // 2, 228 + k * 24), (226, 214, 188), True)
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
            art.draw_button(ui, rect, active, True, glow)
            self._text(ui, item.label, 23, rect.center, (255, 248, 226) if active else INK, True)
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
            art.draw_button(ui, rect, i == tab, True, 0.4)
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
                art.draw_button(ui, rect, True, True, 0.5)
            known = entry["unlocked"]
            icon = self.sprite_surface(entry["kind"], 16, 0.0, not known, 34) if entry.get("kind") else None
            if icon is not None:
                ui.blit(icon, icon.get_rect(center=(rect.x + 26, rect.centery)))
            label = entry["name"] if known else "???"
            self._text(ui, label, 20, (rect.x + 52, rect.centery - 12), INK if known else (100, 112, 124))
            rows.append(Row(self._abs(ui, rect)))
        if entries:
            entry = entries[index]
            known = entry["unlocked"]
            portrait = pygame.Rect(right.right - 292, right.y + 14, 272, 330)
            has_art = bool(entry.get("kind"))
            self._codex_portrait(ui, portrait, entry, known)
            text_w = right.w - 56 - (290 if has_art else 0)
            self._text(ui, entry["name"] if known else "Undiscovered", 30, (right.x + 28, right.y + 22), GOLD, bold=True)
            if entry.get("subtitle"):
                self._text(ui, entry["subtitle"], 19, (right.x + 28, right.y + 64), DIM)
            body = entry["text"] if known else entry["locked_text"]
            for k, line in enumerate(self._wrap(body, 21, text_w)[:11]):
                self._text(ui, line, 21, (right.x + 28, right.y + 108 + k * 29), INK if known else DIM)
            facts = [w for line in (entry.get("facts", ()) if known else ()) for w in self._wrap(line, 18, right.w - 56)]
            for k, line in enumerate(facts):
                self._text(ui, line, 18, (right.x + 28, right.bottom - 28 - (len(facts) - k) * 25), (240, 170, 96))
        self._text(ui, "Left / Right switch tab    Up / Down choose    Esc back", 17, (self.width // 2, 702), (176, 196, 210), True, outline=True)
        return rows

    def _codex_portrait(self, ui: pygame.Surface, box: pygame.Rect, entry: dict[str, Any], known: bool) -> None:
        """The creature on a little pedestal, breathing, with chips for what it fears and what it shrugs off."""
        kind = entry.get("kind")
        if not kind:
            return
        boss = bool(entry.get("boss"))
        tint = entry.get("aura", (80, 90, 140)) if known else (50, 60, 80)
        pulse = 0.85 + 0.15 * math.sin(self._clock * 2.2)
        tint = tuple(int(c) for c in tint)
        glow = art._radial(150, tint, 0.6 * pulse, 1.6)
        ui.blit(glow, glow.get_rect(center=(box.centerx, box.y + 150)))
        pygame.draw.ellipse(ui, (10, 14, 22), (box.centerx - 90, box.y + 250, 180, 34))
        pygame.draw.ellipse(ui, mix((10, 14, 22), tint, 0.4), (box.centerx - 90, box.y + 250, 180, 34), 2)
        height = 250 if boss else 215
        radius = 100 if boss else 60
        surf = self.sprite_surface(kind, radius, self._clock * 0.9, not known, height)
        if surf is not None:
            ui.blit(surf, surf.get_rect(midbottom=(box.centerx, box.y + 262 + math.sin(self._clock * 1.8) * 3)))
        if not known:
            self._text(ui, "?", 72, (box.centerx, box.y + 150), (120, 136, 156), True, outline=True, bold=True)
            return
        chips = [("Weak to", entry.get("weak")), ("Resists", entry.get("resist"))]
        y = box.y + 296
        for label, element in chips:
            if not element:
                continue
            col = ELEMENT_RGB.get(element, (200, 200, 200))
            text = f"{label} {element.title()}"
            width = self.font(18).size(text)[0] + 46
            chip = pygame.Rect(box.centerx - width // 2, y, width, 28)
            pygame.draw.rect(ui, (14, 20, 30), chip, border_radius=14)
            pygame.draw.rect(ui, col, chip, 2, border_radius=14)
            pygame.draw.circle(ui, col, (chip.x + 18, chip.centery), 8)
            self._text(ui, text, 18, (chip.x + 34, chip.centery - 11), INK)
            y += 32

    # ------------------------------------------------------------------ gesture sandbox (a guided lesson)
    def draw_sandbox(self, target: pygame.Surface, image, tut, hands) -> list[Row]:
        from ..sandbox import GUIDED, STEPS
        self._clock = pygame.time.get_ticks() / 1000.0
        self.draw_camera_cover(target, image)
        veil = pygame.Surface(target.get_size(), pygame.SRCALPHA)
        veil.fill((4, 8, 16, 120))
        target.blit(veil, (0, 0))
        tw, th = target.get_size()
        ui = target.subsurface(pygame.Rect((tw - self.width) // 2, (th - self.height) // 2, self.width, self.height).clip(target.get_rect()))
        step = tut.step
        self._text(ui, "GESTURE SANDBOX", 36, (44, 30), GOLD, bold=True, outline=True)
        self._text(ui, "Learn the five hand-signs, one at a time", 20, (46, 76), (214, 226, 234), outline=True)

        panel = pygame.Rect(800, 56, 440, 590)
        self._panel(ui, panel, 232)
        ring_col = handsigns.ELEMENT_RGB.get(step.element or "", (255, 214, 120))
        counter = f"STEP {tut.index + 1} OF {GUIDED}" if step.kind != "free" else ("LESSON COMPLETE" if tut.finished else "PRACTICE")
        self._text(ui, counter, 17, (panel.x + 30, panel.y + 24), DIM)
        self._text(ui, step.title, 40, (panel.x + 30, panel.y + 46), GOLD, bold=True)
        if step.word != step.title:
            self._text(ui, step.word, 22, (panel.x + 32, panel.y + 98), ring_col)
        centre = (panel.centerx, panel.y + 250)
        if step.kind == "free":
            self._sandbox_free_grid(ui, panel, tut)
        else:
            self._sandbox_glyph(ui, centre, step, tut, ring_col)
        y = panel.y + 372
        for line in self._wrap(step.instruction, 23, panel.w - 60):
            self._text(ui, line, 23, (panel.x + 30, y), INK)
            y += 31
        kind, text = tut.feedback(hands)
        pill_col = {"ok": (120, 235, 150), "warn": (255, 196, 90), "idle": (170, 188, 202)}[kind]
        y += 8
        pygame.draw.circle(ui, pill_col, (panel.x + 40, y + 14), 8)
        for k, line in enumerate(self._wrap(text, 20, panel.w - 90)[:2]):
            self._text(ui, line, 20, (panel.x + 58, y + 3 + k * 25), pill_col)
        tip_y = panel.bottom - 24 - 24 * len(step.tips[:2])
        for k, tip in enumerate(step.tips[:2]):
            self._text(ui, "- " + tip, 17, (panel.x + 30, tip_y + k * 24), (176, 196, 210))
        if tut.celebrate > 0:                                           # a small cheer
            fade = min(1.0, tut.celebrate / 0.4)
            self._text(ui, "Maganda!", 64, (400, 300 - int(30 * (1 - fade))), (160, 255, 190), True, outline=True, bold=True)

        rows: list[Row] = []                                            # step tracker along the bottom
        for i, st in enumerate(STEPS):
            cx, cy = 62 + i * 90, 640
            done = st.id in tut.done
            now = i == tut.index
            col = handsigns.ELEMENT_RGB.get(st.element or "", (255, 214, 120))
            pygame.draw.circle(ui, (12, 18, 28), (cx, cy), 20)
            pygame.draw.circle(ui, (110, 235, 150) if done else (col if now else (86, 100, 116)), (cx, cy), 20, 3 if not now else 4)
            if done:
                pygame.draw.lines(ui, (110, 235, 150), False, [(cx - 8, cy), (cx - 2, cy + 7), (cx + 9, cy - 7)], 4)
            else:
                self._text(ui, str(i + 1) if st.kind != "free" else "*", 18, (cx, cy), INK if now else (130, 146, 160), True)
            self._text(ui, st.title if len(st.title) < 11 else st.title.split()[0], 15, (cx, cy + 32), INK if now else (140, 156, 170), True, outline=True)
            rows.append(Row(self._abs(ui, pygame.Rect(cx - 40, cy - 24, 80, 70))))
        self._text(ui, "Enter: next step    Left / Right: change step    R: restart    Esc: back", 17,
                   (self.width // 2 - 120, 702), (176, 196, 210), True, outline=True)
        for hand in hands:                                              # what the camera makes of each hand
            col = handsigns.ELEMENT_RGB.get(hand.gesture.value, (220, 220, 220)) if hand.gesture else (170, 170, 170)
            x, y = int(hand.center[0]), int(hand.center[1])
            r = int(max(46, hand.size * 0.95))
            pygame.draw.circle(target, col, (x, y), r, 3)
            pygame.draw.circle(target, col, (x, y), r + 8 + int(4 * math.sin(self._clock * 5)), 1)
            label = handsigns.ELEMENT_WORD[hand.gesture.value] + "  " + hand.gesture.value.title() if hand.gesture else "?"
            w = self.font(20).size(label)[0] + 24
            chip = pygame.Rect(x - w // 2, y - r - 40, w, 30)
            pygame.draw.rect(target, (10, 14, 24), chip, border_radius=15)
            pygame.draw.rect(target, col, chip, 2, border_radius=15)
            self._text(target, label, 20, chip.center, INK, True)
        return rows

    def _sandbox_glyph(self, ui, centre, step, tut, color) -> None:
        t = self._clock
        cx, cy = centre
        wobble = math.sin(t * 2.2) * 5
        if step.kind == "gesture":
            handsigns.draw_hand_sign(ui, step.element, cx, cy + wobble, 190, True, t)
        elif step.kind == "hello":
            handsigns.draw_hand_sign(ui, "air", cx + math.sin(t * 3) * 16, cy + wobble, 190, True, t)    # a friendly wave
        else:                                                                                           # kalampag: two palms meet
            gap = 46 + 40 * (1 - tut.progress) + 6 * math.sin(t * 4)
            handsigns.draw_hand_sign(ui, "air", cx - gap, cy + wobble, 150, False, t)
            handsigns.draw_hand_sign(ui, "air", cx + gap, cy + wobble, 150, True, t)
        ring = pygame.Rect(0, 0, 250, 250)
        ring.center = (cx, cy)
        pygame.draw.circle(ui, (24, 34, 48), ring.center, 125, 6)
        p = tut.progress
        if p > 0:
            done_col = (120, 240, 160) if tut.celebrate > 0 else color
            pygame.draw.arc(ui, done_col, ring, math.pi / 2 - p * math.tau, math.pi / 2, 8)

    def _sandbox_free_grid(self, ui, panel, tut) -> None:
        names = ("earth", "water", "air", "fire", "lightning")
        for i, name in enumerate(names):
            col = handsigns.ELEMENT_RGB[name]
            cell = pygame.Rect(panel.x + 28 + (i % 3) * 130, panel.y + 128 + (i // 3) * 112, 120, 102)
            lit = tut.lit.get(name, 0) > 0
            pygame.draw.rect(ui, (16, 24, 36), cell, border_radius=14)
            pygame.draw.rect(ui, col if lit else (60, 74, 90), cell, 3 if lit else 2, border_radius=14)
            handsigns.draw_hand_sign(ui, name, cell.centerx, cell.y + 40, 64 if not lit else 72, lit, self._clock)
            self._text(ui, handsigns.ELEMENT_WORD[name], 17, (cell.centerx, cell.bottom - 14), INK if lit else (130, 146, 160), True)
        if tut.finished:
            self._text(ui, "Lesson complete", 20, (panel.centerx, panel.y + 126 + 2 * 112 + 4), (120, 240, 160), True)

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

    def draw_howto(self, target: pygame.Surface, page: int, pages: int, heading: str, quote: str,
                   lines: Sequence[str], speaking: bool = False) -> None:
        """How to Play as an illustrated lesson: Lola Auring's words and rules on the left, a moving picture on the right."""
        self._clock = t = pygame.time.get_ticks() / 1000.0
        full = target
        ui = self._ui(full, "menu")
        veil = pygame.Surface(full.get_size(), pygame.SRCALPHA)
        veil.fill((3, 7, 15, 120))
        full.blit(veil, (0, 0))
        self._draw_embers(full)
        self._text(ui, "HOW TO PLAY", 44, (self.width // 2, 50), GOLD, True, outline=True, bold=True)
        left = pygame.Rect(50, 96, 640, 520)
        right = pygame.Rect(716, 96, 514, 520)
        self._panel(ui, left, 228)
        self._panel(ui, right, 228)
        self._text(ui, heading, 36, (left.x + 34, left.y + 26), GOLD, bold=True)
        art.draw_sun(ui, left.right - 52, left.y + 50, 20, GOLD, False, t * 0.3)
        y = left.y + 90
        self._text(ui, "Lola Auring says", 17, (left.x + 34, y), (240, 170, 96))
        y += 24
        for wrapped in self._wrap(quote, 23, left.w - 70):
            self._text(ui, wrapped, 23, (left.x + 34, y), (255, 226, 170))
            y += 31
        y += 14
        pygame.draw.line(ui, (90, 74, 52), (left.x + 34, y), (left.right - 34, y), 2)
        y += 18
        for line in lines:
            wrapped = self._wrap(line, 21, left.w - 104)
            pygame.draw.polygon(ui, GOLD, [(left.x + 42, y + 13), (left.x + 50, y + 5), (left.x + 58, y + 13), (left.x + 50, y + 21)])
            for w in wrapped:
                self._text(ui, w, 21, (left.x + 74, y), INK)
                y += 28
            y += 10
        picture = howto_art.PAGES[page % len(howto_art.PAGES)]
        picture(self, ui, pygame.Rect(right.x + 12, right.y + 16, right.w - 24, right.h - 32), t)
        for i in range(pages):
            pygame.draw.circle(ui, GOLD if i == page else (70, 90, 108), (self.width // 2 + (i - (pages - 1) / 2) * 26, 646), 7)
        footer = "Left / Right turn page    Esc back"
        if speaking:
            footer = "Lola is reading this page aloud    " + footer
            pygame.draw.circle(ui, (255, 190, 90), (self.width // 2 - 280, 688), 5 + int(2 * math.sin(t * 8)))
        self._text(ui, footer, 17, (self.width // 2, 688), (176, 196, 210), True, outline=True)

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
