from __future__ import annotations

import argparse
import traceback
from dataclasses import replace

import cv2
import pygame

from . import story
from .combat import kind_info
from .content import LevelDefinition, load_levels
from .menus import Item, Menu, clamp_index
from .models import Difficulty, GestureFrame, canvas_size_for, scale_frame
from .persistence import SaveData, SaveRepository, SettingsRepository, user_data_dir
from .presentation.audio import AudioManager, music_for
from .presentation.renderer import GameRenderer
from .presentation.scenes import AppModel, SceneId
from .session import GameEventType, GameSession, SessionState, complete_level, record_seen
from .vision import CalibrationSession, VisionService


LOGICAL_SIZE = (1280, 720)
DIFFICULTIES = (Difficulty.STORY, Difficulty.BALANCED, Difficulty.MASTER)
CAMERA_SLOTS = 6
TEXT_SECONDS_PER_LINE = 1.6          # story scenes reveal one line this often
MENU_SCENES = (SceneId.MENU, SceneId.SETTINGS, SceneId.PAUSE, SceneId.RESULTS)
TEXT_SCENES = (SceneId.PROLOGUE, SceneId.EPILOGUE, SceneId.CREDITS, SceneId.STORY, SceneId.BRIEFING)
LEVEL_TINTS = {
    "stonewake": (190, 130, 70), "tidelost": (60, 150, 220), "skyglass": (170, 220, 220),
    "cinderforge": (230, 100, 40), "eclipse": (150, 70, 200),
}


def camera_to_surface(image) -> pygame.Surface | None:
    if image is None:
        return None
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), "RGB")


def level_order(levels: dict[str, LevelDefinition]) -> list[str]:
    """Stages in play order: follow next_level from the first stage, then any stragglers."""
    order: list[str] = []
    current = "stonewake" if "stonewake" in levels else next(iter(levels))
    while current and current in levels and current not in order:
        order.append(current)
        current = levels[current].next_level
    order.extend(level_id for level_id in levels if level_id not in order)
    return order


def format_time(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class Application:
    def __init__(self, camera_override: int | None = None, windowed: bool = False):
        pygame.init()
        self.data_dir = user_data_dir()
        self.save_repository = SaveRepository(self.data_dir / "save.json")
        self.settings_repository = SettingsRepository(self.data_dir / "settings.json")
        settings = self.settings_repository.load()
        if camera_override is not None:
            settings = replace(settings, camera_id=camera_override)
        if windowed:
            settings = replace(settings, fullscreen=False)
        self.levels = load_levels()
        self.order = level_order(self.levels)
        self.model = AppModel(self.levels, self.save_repository.load(), settings)
        self.window = self._open_window(settings.fullscreen)
        pygame.display.set_caption("Elemental Convergence")
        self.canvas = pygame.Surface(canvas_size_for(self.window.get_size()))
        self.clock = pygame.time.Clock()
        self.renderer = GameRenderer(LOGICAL_SIZE)
        self.vision = VisionService()
        self.calibration = CalibrationSession()
        self.session = GameSession(self.levels)
        self.audio = AudioManager(self.renderer.asset_root, settings.master_volume, settings.music_volume, settings.sfx_volume)
        self.running = True
        self.level_select_index = 0
        self.codex_tab = 0
        self.codex_index = 0
        self.how_page = 0
        self.last_camera_surface = None
        self.last_camera_image = None
        self.game_frame = GestureFrame(0.0, (), False)
        self._heartbeat = 0.0
        self.menu: Menu | None = None
        self.rows: list = []                  # clickable rectangles of the last drawn screen (canvas coordinates)
        self.result: dict = {}
        self.scene_time = 0.0
        self._shown_scene: SceneId | None = None
        self._dragging = False
        self._reset_armed = False
        self._calibrating_from_settings = False
        self._apply_settings(save=False)
        self._start_camera(settings.camera_id if settings.camera_id is not None else 0)

    # ------------------------------------------------------------------ window / camera / settings
    @staticmethod
    def _open_window(fullscreen: bool) -> pygame.Surface:
        """Fullscreen uses the monitor's own resolution; the canvas then matches its aspect ratio."""
        if fullscreen:
            return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        return pygame.display.set_mode(LOGICAL_SIZE, pygame.RESIZABLE)

    def _fit_canvas(self) -> None:
        """Keep the canvas the same shape as the window so the picture fills it without bars or stretching."""
        size = canvas_size_for(self.window.get_size())
        if size != self.canvas.get_size():
            self.canvas = pygame.Surface(size)
        self.session.set_arena(size)

    def _camera_surface(self):
        if self.last_camera_surface is None and self.last_camera_image is not None:
            self.last_camera_surface = camera_to_surface(self.last_camera_image)
        return self.last_camera_surface

    def _apply_settings(self, save: bool = True) -> None:
        s = self.model.settings
        self.renderer.reduced_flash = s.reduced_flash
        self.renderer.reduced_shake = s.reduced_shake
        self.renderer.battle.show_hands = s.show_hand_overlay
        self.audio.set_volumes(s.master_volume, s.music_volume, s.sfx_volume)
        if save:
            self.settings_repository.save(s)

    _sync_accessibility = _apply_settings

    def _set_setting(self, **changes) -> None:
        self.model.set_setting(**changes)
        self._apply_settings()

    def _set_fullscreen(self, on: bool) -> None:
        self._set_setting(fullscreen=bool(on))
        self.window = self._open_window(self.model.settings.fullscreen)

    def _set_difficulty(self, index: int) -> None:
        self.model.set_difficulty(DIFFICULTIES[index % len(DIFFICULTIES)])
        self.save_repository.save(self.model.save)

    def _start_camera(self, camera_id: int) -> None:
        if self.vision.start(camera_id):
            self.model.settings = replace(self.model.settings, camera_id=camera_id)
        else:
            self.model.camera_unavailable()

    def _change_camera(self, index: int) -> None:
        self._start_camera(index % CAMERA_SLOTS)
        self._apply_settings()

    # ------------------------------------------------------------------ menus
    def _ui_sound(self, name: str) -> None:
        self.audio.play(name)

    def _build_menu(self, scene: SceneId) -> Menu | None:
        m = self.model
        if scene is SceneId.MENU:
            has_progress = bool(m.save.completed_levels)
            return Menu([
                Item("Continue" if has_progress else "Begin the Journey", action=self._continue),
                Item("New Game", action=self._new_game, hint="Start again from the first seal (your stars and scores are kept)"),
                Item("Level Select", action=lambda: m.go(SceneId.LEVEL_SELECT), hint="Replay any seal you have restored"),
                Item("Codex", action=lambda: m.go(SceneId.CODEX), hint="Lore of the seals and the creatures of the Rift"),
                Item("Gesture Sandbox", action=lambda: m.go(SceneId.SANDBOX), hint="Practice your hand gestures"),
                Item("How to Play", action=lambda: m.go(SceneId.HOW_TO_PLAY)),
                Item("Settings", action=m.open_settings),
                Item("Credits", action=lambda: m.go(SceneId.CREDITS)),
                Item("Quit", action=self._quit),
            ])
        if scene is SceneId.SETTINGS:

            def volume(label, name, hint):
                return Item(label, "slider", get=lambda: getattr(m.settings, name),
                            set=lambda v: self._set_setting(**{name: v}), hint=hint)

            def toggle(label, name, hint):
                return Item(label, "toggle", get=lambda: getattr(m.settings, name),
                            set=lambda v: self._set_setting(**{name: bool(v)}), hint=hint)

            reset = Item("Reset progress", hint="Erase all scores, stars and unlocked seals (asks to confirm)")

            def confirm_reset() -> None:
                if self._reset_armed:
                    self._reset_armed = False
                    reset.label = "Reset progress"
                    m.save = SaveData(difficulty=m.save.difficulty)
                    self.save_repository.save(m.save)
                else:
                    self._reset_armed = True
                    reset.label = "Press again to ERASE all progress"

            reset.action = confirm_reset
            return Menu([
                volume("Master volume", "master_volume", "Overall loudness"),
                volume("Music", "music_volume", "Background music"),
                volume("Sound effects", "sfx_volume", "Spells, hits and pick-ups"),
                Item("Difficulty", "choice", get=lambda: DIFFICULTIES.index(m.save.difficulty), set=self._set_difficulty,
                     options=("Story", "Balanced", "Master"),
                     hint="Story: forgiving. Balanced: as intended. Master: relentless."),
                toggle("Fullscreen", "fullscreen", "Fill the whole screen (F11 also works)"),
                toggle("Reduced flash", "reduced_flash", "Fewer bright flashes and screen floods"),
                toggle("Reduced shake", "reduced_shake", "No screen shake"),
                toggle("Gesture labels", "show_hand_overlay", "Show the element name above each hand"),
                Item("Camera", "choice", get=lambda: (m.settings.camera_id or 0) % CAMERA_SLOTS, set=self._change_camera,
                     options=tuple(f"Camera {i}" for i in range(CAMERA_SLOTS)), hint="Pick the camera that sees your hands"),
                Item("Recalibrate camera", action=lambda: m.go(SceneId.CALIBRATION), hint="Re-run camera and gesture setup"),
                reset,
                Item("Back", action=m.close_settings),
            ])
        if scene is SceneId.PAUSE:
            return Menu([
                Item("Resume", action=self._resume),
                Item("Restart Level", action=self._restart_level),
                Item("Settings", action=m.open_settings),
                Item("Quit to Menu", action=self._quit_to_menu),
            ])
        if scene is SceneId.RESULTS:
            level = self.levels[m.current_level_id or "stonewake"]
            won = m.last_result == "complete"
            items = []
            if won:
                items.append(Item("Next Seal" if level.next_level else "Finish the Journey", action=self._after_results))
            items.append(Item("Retry", action=self._begin_level))
            items.append(Item("Level Select", action=lambda: m.go(SceneId.LEVEL_SELECT)))
            items.append(Item("Main Menu", action=lambda: m.go(SceneId.MENU)))
            return Menu(items)
        return None

    def _enter_scene(self, scene: SceneId) -> None:
        self.scene_time = 0.0
        self.menu = self._build_menu(scene)
        self.rows = []
        self._reset_armed = False
        if scene is SceneId.CALIBRATION:
            self._calibrating_from_settings = self.model.previous_scene is SceneId.SETTINGS
        if scene is SceneId.LEVEL_SELECT:
            current = self.model.current_level_id
            self.level_select_index = self.order.index(current) if current in self.order else 0
            if self.order[self.level_select_index] not in self.model.save.unlocked_levels:
                self.level_select_index = 0
        elif scene is SceneId.CODEX:
            self.codex_index = 0
        elif scene is SceneId.HOW_TO_PLAY:
            self.how_page = 0

    # ------------------------------------------------------------------ actions
    def _continue(self) -> None:
        self.model.continue_game()

    def _new_game(self) -> None:
        self.model.new_game()

    def _quit(self) -> None:
        self.running = False

    def _resume(self) -> None:
        self.session.set_paused(False)
        self.model.resume()

    def _restart_level(self) -> None:
        self.session.set_paused(False)
        self._begin_level()

    def _quit_to_menu(self) -> None:
        self.session.set_paused(False)
        self.model.go(SceneId.MENU)

    def _finish_calibration(self) -> None:
        camera_id = self.model.settings.camera_id if self.model.settings.camera_id is not None else 0
        if self._calibrating_from_settings or self.model.current_level_id is None:   # opened from Settings: go back
            self.model.settings = replace(self.model.settings, camera_id=camera_id)
            self.model.go(SceneId.SETTINGS)
        else:
            self.model.finish_calibration(camera_id)
        self.settings_repository.save(self.model.settings)

    def _begin_level(self) -> None:
        level_id = self.model.current_level_id or "stonewake"
        self.renderer.reset_fx()
        self._apply_settings(save=False)
        self.session.start_level(level_id, self.model.save.difficulty)
        self.model.begin_gameplay()

    def _after_results(self) -> None:
        if self.model.last_result == "failed":
            self._begin_level()
            return
        current = self.levels[self.model.current_level_id or "stonewake"]
        if current.next_level:
            self.model.current_level_id = current.next_level
            self.model.go(SceneId.STORY)
        else:
            self.model.go(SceneId.EPILOGUE)

    def _finish_run(self, complete: bool) -> None:
        """Save progress and prepare the results screen."""
        level = self.levels[self.model.current_level_id or "stonewake"]
        snap = self.session.snapshot()
        previous_best = self.model.save.best_scores.get(level.id, 0)
        if complete:
            self.model.save = complete_level(self.model.save, level, snap.score, self.session.stars(), self.session.seen_kinds)
        else:
            self.model.save = record_seen(self.model.save, self.session.seen_kinds)
        self.save_repository.save(self.model.save)
        self.model.last_result = "complete" if complete else "failed"
        self.result = {
            "complete": complete, "title": f"{level.title}   {level.subtitle}", "stars": self.session.stars(),
            "score": snap.score, "new_best": complete and snap.score > previous_best,
            "max_combo": max(1, self.session.max_combo), "hits": self.session.hits_taken,
            "time": format_time(snap.elapsed_seconds),
            "story": " ".join(level.outro) if complete else
            "The Rift is patient. Learn its patterns (the red warnings always come first) and try again.",
        }
        self.model.go(SceneId.RESULTS)

    # ------------------------------------------------------------------ run loop / input
    def run(self) -> int:
        try:
            while self.running:
                dt = self.clock.tick(60) / 1000.0
                self._events()
                self._update(dt)
                self._render()
        finally:
            self.vision.stop()
            pygame.quit()
        return 0

    def _events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._key(event.key)
            elif event.type == pygame.MOUSEMOTION:
                self._mouse_move(event.pos)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._click(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self._dragging = False

    def _to_canvas(self, pos: tuple[int, int]) -> tuple[int, int]:
        sx = self.canvas.get_width() / max(1, self.window.get_width())
        sy = self.canvas.get_height() / max(1, self.window.get_height())
        return int(pos[0] * sx), int(pos[1] * sy)

    def _key(self, key: int) -> None:
        scene = self.model.scene
        if key == pygame.K_F11:
            self._set_fullscreen(not self.model.settings.fullscreen)
            return
        if key == pygame.K_ESCAPE:
            self._back(scene)
            return
        accept = key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER)
        left, right = key in (pygame.K_LEFT, pygame.K_a), key in (pygame.K_RIGHT, pygame.K_d)
        up, down = key in (pygame.K_UP, pygame.K_w), key in (pygame.K_DOWN, pygame.K_s)
        if scene in MENU_SCENES and self.menu is not None:
            if up or down:
                if self.menu.move(-1 if up else 1):
                    self._ui_sound("ui_move")
            elif left or right:
                if self.menu.adjust(1 if right else -1):
                    self._ui_sound("ui_move")
            elif accept:
                self._ui_sound("ui_select" if self.menu.activate() else "ui_error")
        elif scene is SceneId.LEVEL_SELECT:
            if left or right:
                self.level_select_index = (self.level_select_index + (1 if right else -1)) % len(self.order)
                self._ui_sound("ui_move")
            elif accept:
                self._play_level_card(self.level_select_index)
        elif scene is SceneId.CODEX:
            entries = self._codex_entries()
            if left or right:
                self.codex_tab = (self.codex_tab + (1 if right else -1)) % 2
                self.codex_index = 0
                self._ui_sound("ui_move")
            elif up or down:
                self.codex_index = clamp_index(self.codex_index + (1 if down else -1), len(entries))
                self._ui_sound("ui_move")
        elif scene is SceneId.HOW_TO_PLAY:
            if left or right:
                self.how_page = (self.how_page + (1 if right else -1)) % len(story.HOW_TO_PLAY)
                self._ui_sound("ui_move")
        elif scene in TEXT_SCENES and accept:
            self._advance_text()
        elif scene is SceneId.CALIBRATION:
            if key == pygame.K_SPACE:
                self._finish_calibration()
            elif key == pygame.K_c:
                self._start_camera(((self.model.settings.camera_id or 0) + 1) % CAMERA_SLOTS)

    def _back(self, scene: SceneId) -> None:
        if scene is SceneId.GAMEPLAY:
            self.session.set_paused(True)
            self.model.pause()
        elif scene is SceneId.PAUSE:
            self._resume()
        elif scene is SceneId.SETTINGS:
            self._ui_sound("ui_back")
            self.model.close_settings()
        elif scene is SceneId.MENU:
            self.running = False
        elif scene is SceneId.PROLOGUE:
            self.model.finish_prologue()
            self.settings_repository.save(self.model.settings)
            self.save_repository.save(self.model.save)
        elif scene is SceneId.EPILOGUE:
            self.model.go(SceneId.CREDITS)
        elif scene is SceneId.CALIBRATION and self._calibrating_from_settings:
            self.model.go(SceneId.SETTINGS)
        else:
            self._ui_sound("ui_back")
            self.model.go(SceneId.MENU)

    def _advance_text(self) -> None:
        """Enter on a story scene: finish the reveal first, then move on."""
        scene = self.model.scene
        lines = self._text_scene(scene)[1]
        if self.scene_time < len(lines) * TEXT_SECONDS_PER_LINE:
            self.scene_time = len(lines) * TEXT_SECONDS_PER_LINE + 0.01
            return
        self._ui_sound("ui_select")
        if scene is SceneId.PROLOGUE:
            self.model.finish_prologue()
            self.save_repository.save(self.model.save)
        elif scene is SceneId.EPILOGUE:
            self.model.go(SceneId.CREDITS)
        elif scene is SceneId.CREDITS:
            self.model.go(SceneId.MENU)
        elif scene is SceneId.STORY:
            self.model.go(SceneId.BRIEFING)
        elif scene is SceneId.BRIEFING:
            self._begin_level()

    def _play_level_card(self, index: int) -> None:
        level_id = self.order[index]
        if level_id in self.model.save.unlocked_levels:
            self._ui_sound("ui_select")
            self.model.select_level(level_id)
        else:
            self._ui_sound("ui_error")

    def _row_index(self, pos) -> int | None:
        for i, row in enumerate(self.rows):
            if row.rect.collidepoint(pos):
                return i
        return None

    def _mouse_move(self, pos) -> None:
        pos = self._to_canvas(pos)
        scene = self.model.scene
        if scene in MENU_SCENES and self.menu is not None:
            if self._dragging:
                self._drag_slider(pos)
                return
            index = self._row_index(pos)
            if index is not None and index < len(self.menu.items) and self.menu.hover(index):
                self._ui_sound("ui_move")
        elif scene is SceneId.LEVEL_SELECT:
            index = self._row_index(pos)
            if index is not None and index != self.level_select_index:
                self.level_select_index = index
                self._ui_sound("ui_move")

    def _drag_slider(self, pos) -> None:
        index = self.menu.index if self.menu else 0
        if self.menu is None or index >= len(self.rows) or self.rows[index].bar is None:
            return
        bar = self.rows[index].bar
        self.menu.set_fraction(index, (pos[0] - bar.x) / max(1, bar.w))

    def _click(self, pos) -> None:
        pos = self._to_canvas(pos)
        scene = self.model.scene
        if scene in MENU_SCENES and self.menu is not None:
            index = self._row_index(pos)
            if index is None or index >= len(self.menu.items):
                return
            self.menu.hover(index)
            row = self.rows[index]
            if row.bar is not None and self.menu.items[index].kind == "slider":
                self._dragging = True
                self.menu.set_fraction(index, (pos[0] - row.bar.x) / max(1, row.bar.w))
                self._ui_sound("ui_move")
            else:
                self._ui_sound("ui_select" if self.menu.activate() else "ui_error")
        elif scene is SceneId.LEVEL_SELECT:
            index = self._row_index(pos)
            if index is not None:
                self.level_select_index = index
                self._play_level_card(index)
        elif scene is SceneId.CODEX:
            index = self._row_index(pos)
            if index is not None:
                visible = 11
                start = max(0, min(self.codex_index - visible // 2, max(0, len(self._codex_entries()) - visible)))
                self.codex_index = start + index
                self._ui_sound("ui_move")
        elif scene is SceneId.HOW_TO_PLAY:
            step = 1 if pos[0] > self.canvas.get_width() // 2 else -1
            self.how_page = (self.how_page + step) % len(story.HOW_TO_PLAY)
            self._ui_sound("ui_move")
        elif scene in TEXT_SCENES:
            self._advance_text()

    # ------------------------------------------------------------------ per-frame update
    def _update_audio(self, dt: float) -> None:
        scene = self.model.scene
        snap = self.session.snapshot()
        self.audio.play_music(music_for(scene.value, self.model.current_level_id, snap.state, self.model.last_result))
        self.audio.set_duck(0.4 if scene is SceneId.PAUSE else 1.0)
        self.audio.update()
        playing = scene is SceneId.GAMEPLAY and snap.state in (SessionState.ACTIVE, SessionState.BOSS)
        self._heartbeat -= dt
        if playing and snap.hp < 30 and self._heartbeat <= 0:       # low health: a heartbeat that speeds up
            self.audio.play("heartbeat")
            self._heartbeat = 0.55 + 0.6 * (snap.hp / 30.0)

    def _update(self, dt: float) -> None:
        if self._shown_scene is not self.model.scene:
            self._shown_scene = self.model.scene
            self._enter_scene(self.model.scene)
        self.scene_time += dt
        self._update_audio(dt)
        frame = self.vision.latest()
        image = self.vision.latest_image()
        if image is not None:
            self.last_camera_image = image
            self.last_camera_surface = None              # converted lazily, only calibration / sandbox need it
        self._fit_canvas()
        # Hands arrive in camera pixels. Map them with the same crop the picture gets, so a hand on screen
        # is exactly where the game thinks it is.
        if self.last_camera_image is not None:
            camera_size = (self.last_camera_image.shape[1], self.last_camera_image.shape[0])
        else:
            camera_size = self.canvas.get_size()
        self.game_frame = scale_frame(frame, camera_size, self.canvas.get_size())
        scene = self.model.scene
        if scene is SceneId.CALIBRATION:
            self.calibration.observe(frame)
            if self.calibration.complete:
                self._finish_calibration()
        elif scene is SceneId.GAMEPLAY:
            events = self.session.update(dt, self.game_frame)
            self.renderer.update_fx(dt, self.session.snapshot(), events, self.game_frame)
            for event in events:
                self.audio.play_event(event)
                if event.type is GameEventType.LEVEL_COMPLETE:
                    self._finish_run(True)
                elif event.type is GameEventType.LEVEL_FAILED:
                    self._finish_run(False)
        elif scene is SceneId.RESULTS:
            self.renderer.update_fx(dt, self.session.snapshot())     # let the last explosions finish

    # ------------------------------------------------------------------ screen data
    def _level_cards(self) -> list[dict]:
        save = self.model.save
        cards = []
        for number, level_id in enumerate(self.order, 1):
            level = self.levels[level_id]
            cards.append({
                "number": number, "title": level.title, "subtitle": level.subtitle, "keeper": level.keeper,
                "hazard": (level.hazard.label.title().rstrip("!") if level.hazard else "None"),
                "unlocked": level_id in save.unlocked_levels, "stars": save.best_stars.get(level_id, 0),
                "best": save.best_scores.get(level_id, 0), "intro": " ".join(level.intro[:2]),
                "tint": LEVEL_TINTS.get(level_id, (118, 187, 210)),
            })
        return cards

    def _codex_entries(self) -> list[dict]:
        save = self.model.save
        entries: list[dict] = []
        if self.codex_tab == 0:
            for level_id in self.order:
                level = self.levels[level_id]
                done = level_id in save.completed_levels
                entries.append({
                    "name": level.title, "unlocked": done, "subtitle": f"{level.subtitle}  -  {level.keeper}",
                    "text": "\n".join(level.lore) + "\n\n" + (story.HAZARD_LORE.get(level.hazard.kind, "") if level.hazard else ""),
                    "locked_text": "Restore this seal to read its history.",
                    "facts": [f"Guardian: {level.boss_name}"],
                })
        else:
            for kind, (name, text) in story.ENEMY_LORE.items():
                seen = kind in save.seen_enemies
                info = kind_info(kind)
                entries.append({
                    "name": name, "unlocked": seen, "subtitle": "Guardian" if info.boss else "Creature of the Rift",
                    "text": text, "locked_text": "Meet this enemy in battle to record it here.",
                    "facts": ["Attacks: " + ", ".join(sorted(set(info.attacks)))] if seen else [],
                })
        return entries

    def _text_scene(self, scene: SceneId) -> tuple[str, list[str], str]:
        """(title, lines, background stage) for the story-style scenes."""
        level = self.levels[self.model.current_level_id or "stonewake"]
        if scene is SceneId.PROLOGUE:
            return "THE HOLLOW DAWN", list(story.PROLOGUE), "menu"
        if scene is SceneId.EPILOGUE:
            return "DAWN", list(story.EPILOGUE), "eclipse"
        if scene is SceneId.CREDITS:
            return "CREDITS", list(story.CREDITS), "menu"
        if scene is SceneId.STORY:
            return level.title, [f"{level.subtitle}   -   {level.keeper}", *level.intro], level.id
        waves = []
        for i, wave in enumerate(level.waves, 1):
            title = level.wave_titles[i - 1] if i - 1 < len(level.wave_titles) else ""
            if wave.objective.value == "defeat_all":
                goal = "defeat every enemy"
            elif wave.objective.value == "hunt":
                goal = f"hunt {wave.quota} enemies"
            else:
                goal = f"survive {int(wave.duration_seconds or 0)} seconds"
            elite = "  (an elite joins the fight)" if wave.elite else ""
            waves.append(f"Wave {i}" + (f", {title}" if title else "") + f": {goal}{elite}")
        hazard = ""
        if level.hazard:
            hazard = f"Hazard: {level.hazard.label.title().rstrip('!')}. {story.HAZARD_LORE.get(level.hazard.kind, '')}"
        lines = [f"New power: {level.unlock.value.title()}", hazard, *waves, f"Guardian: {level.boss_name}",
                 "Keep a hand in view. Blast orbs to block them. Press Esc to pause."]
        return "WARDEN BRIEFING", [line for line in lines if line], level.id

    # ------------------------------------------------------------------ drawing
    def _render(self) -> None:
        scene = self.model.scene
        r = self.renderer
        canvas = self.canvas
        if scene in (SceneId.PROLOGUE, SceneId.EPILOGUE, SceneId.CREDITS, SceneId.STORY, SceneId.BRIEFING):
            title, lines, stage = self._text_scene(scene)
            footer = {"Credits": "Enter: main menu"}.get(title.title(), "Enter: continue")
            r.draw_text_scene(canvas, title, lines, stage, self.scene_time / TEXT_SECONDS_PER_LINE, footer)
            self.rows = []
        elif scene is SceneId.MENU and self.menu is not None:
            self.rows = r.draw_menu_screen(canvas, self.menu, subtitle=story.TAGLINE, y0=218, row_h=47)
        elif scene is SceneId.SETTINGS and self.menu is not None:
            self.rows = r.draw_menu_screen(canvas, self.menu, "SETTINGS", "Changes are saved as you make them", wide=True,
                                           y0=138, row_h=42, compact=True)
        elif scene is SceneId.CALIBRATION:
            r.draw_calibration(canvas, self.vision.latest(), self.calibration.missing, self._camera_surface())
            self.rows = []
        elif scene is SceneId.GAMEPLAY:
            r.draw_gameplay(canvas, self.session.snapshot(), None, self.game_frame, self.last_camera_image)
        elif scene is SceneId.PAUSE and self.menu is not None:
            snap = self.session.snapshot()
            r.draw_gameplay(canvas, snap, None, self.game_frame, self.last_camera_image)
            info = [f"Wave {snap.wave_number}/3   Score {snap.score:,}", "Combat is frozen"]
            self.rows = r.draw_pause(canvas, self.menu, snap.level_title, info)
        elif scene is SceneId.RESULTS and self.menu is not None:
            r.draw_gameplay(canvas, self.session.snapshot(), None, self.game_frame, self.last_camera_image)
            self.rows = r.draw_results(canvas, self.result, self.menu)
        elif scene is SceneId.LEVEL_SELECT:
            self.rows = r.draw_level_select(canvas, self._level_cards(), self.level_select_index)
        elif scene is SceneId.CODEX:
            entries = self._codex_entries()
            self.codex_index = clamp_index(self.codex_index, len(entries))
            self.rows = r.draw_codex(canvas, ("Seals", "Bestiary"), self.codex_tab, entries, self.codex_index)
        elif scene is SceneId.HOW_TO_PLAY:
            heading, lines = story.HOW_TO_PLAY[self.how_page]
            r.draw_pages(canvas, "HOW TO PLAY", heading, lines, self.how_page, len(story.HOW_TO_PLAY))
            self.rows = []
        elif scene is SceneId.SANDBOX:
            frame = self.vision.latest()
            r.draw_camera_cover(canvas, self.last_camera_image)
            labels = [hand.gesture.value.upper() for hand in frame.hands if hand.gesture]
            r.draw_overlay(canvas, "GESTURE SANDBOX", labels or ["Show a gesture to test recognition", "Esc: main menu"])
            self.rows = []
        if canvas.get_size() == self.window.get_size():
            self.window.blit(canvas, (0, 0))              # no rescale needed
        else:
            pygame.transform.smoothscale(canvas, self.window.get_size(), self.window)
        pygame.display.flip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Elemental Convergence")
    parser.add_argument("--camera", type=int, default=None, help="camera index to open")
    parser.add_argument("--windowed", action="store_true", help="start in a resizable window")
    args = parser.parse_args(argv)
    try:
        return Application(args.camera, args.windowed).run()
    except Exception:
        log = user_data_dir() / "crash.log"             # keep a trace so a bug report is possible
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(traceback.format_exc(), encoding="utf-8")
            print(f"Elemental Convergence crashed. Details were saved to {log}")
        except OSError:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
