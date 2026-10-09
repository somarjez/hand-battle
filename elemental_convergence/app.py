from __future__ import annotations

import argparse
from dataclasses import replace

import cv2
import pygame

from .content import load_levels
from .models import Difficulty
from .persistence import SaveRepository, SettingsRepository, user_data_dir
from .presentation.audio import AudioManager
from .presentation.renderer import GameRenderer
from .presentation.scenes import AppModel, SceneId
from .session import GameEventType, GameSession, SessionState, complete_level
from .vision import CalibrationSession, VisionService


LOGICAL_SIZE = (1280, 720)
MENU_ITEMS = ["Continue", "New Game", "Level Select", "Sandbox", "How to Play", "Settings", "Credits", "Quit"]


def camera_to_surface(image) -> pygame.Surface | None:
    if image is None:
        return None
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    return pygame.image.frombuffer(rgb.tobytes(), (rgb.shape[1], rgb.shape[0]), "RGB")


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
        self.model = AppModel(self.levels, self.save_repository.load(), settings)
        flags = pygame.FULLSCREEN if settings.fullscreen else pygame.RESIZABLE
        self.window = pygame.display.set_mode(LOGICAL_SIZE, flags)
        pygame.display.set_caption("Elemental Convergence")
        self.canvas = pygame.Surface(LOGICAL_SIZE)
        self.clock = pygame.time.Clock()
        self.renderer = GameRenderer(LOGICAL_SIZE)
        self.vision = VisionService()
        self.calibration = CalibrationSession()
        self.session = GameSession(self.levels)
        self.audio = AudioManager(self.renderer.asset_root, settings.master_volume, settings.music_volume, settings.sfx_volume)
        self.running = True
        self.selected = 0
        self.story_index = 0
        self.level_select_index = 0
        self.last_camera_surface = None
        self._start_camera(settings.camera_id if settings.camera_id is not None else 0)
        self.audio.play_music("menu")

    def _start_camera(self, camera_id: int) -> None:
        if self.vision.start(camera_id):
            self.model.settings = replace(self.model.settings, camera_id=camera_id)
        else:
            self.model.camera_unavailable()

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
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._click(event.pos)

    def _key(self, key: int) -> None:
        scene = self.model.scene
        if key == pygame.K_ESCAPE:
            if scene is SceneId.GAMEPLAY:
                self.session.set_paused(True)
                self.model.pause()
            elif scene is SceneId.PAUSE:
                self.session.set_paused(False)
                self.model.resume()
            elif scene is not SceneId.MENU:
                self.model.go(SceneId.MENU)
            else:
                self.running = False
            return
        if scene is SceneId.MENU:
            if key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(MENU_ITEMS)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % len(MENU_ITEMS)
            elif key in (pygame.K_RETURN, pygame.K_SPACE):
                self._menu_action(MENU_ITEMS[self.selected])
        elif scene is SceneId.CALIBRATION:
            if key == pygame.K_SPACE:
                self._finish_calibration()
            elif key == pygame.K_c:
                current = self.model.settings.camera_id or 0
                self._start_camera((current + 1) % 6)
        elif scene is SceneId.STORY and key in (pygame.K_RETURN, pygame.K_SPACE):
            self.model.go(SceneId.BRIEFING)
        elif scene is SceneId.BRIEFING and key in (pygame.K_RETURN, pygame.K_SPACE):
            self._begin_level()
        elif scene is SceneId.LEVEL_SELECT:
            unlocked = self.model.save.unlocked_levels
            if key in (pygame.K_LEFT, pygame.K_a):
                self.level_select_index = (self.level_select_index - 1) % len(unlocked)
            elif key in (pygame.K_RIGHT, pygame.K_d):
                self.level_select_index = (self.level_select_index + 1) % len(unlocked)
            elif key == pygame.K_RETURN:
                self.model.select_level(unlocked[self.level_select_index])
        elif scene is SceneId.PAUSE and key in (pygame.K_RETURN, pygame.K_SPACE):
            self.session.set_paused(False)
            self.model.resume()
        elif scene is SceneId.RESULTS and key in (pygame.K_RETURN, pygame.K_SPACE):
            self._after_results()
        elif scene is SceneId.SETTINGS:
            if key in (pygame.K_LEFT, pygame.K_MINUS):
                self.model.adjust_master_volume(-0.1)
            elif key in (pygame.K_RIGHT, pygame.K_EQUALS, pygame.K_PLUS):
                self.model.adjust_master_volume(0.1)
            elif key == pygame.K_x:
                self.model.toggle_reduced_flash()
            elif key == pygame.K_s:
                self.model.toggle_reduced_shake()
            elif key == pygame.K_f:
                self.model.toggle_fullscreen()
                flags = pygame.FULLSCREEN if self.model.settings.fullscreen else pygame.RESIZABLE
                self.window = pygame.display.set_mode(LOGICAL_SIZE, flags)
            elif key == pygame.K_c:
                self.model.current_level_id = None
                self.model.go(SceneId.CALIBRATION)
            elif key in (pygame.K_1, pygame.K_2, pygame.K_3):
                selected = {pygame.K_1: Difficulty.STORY, pygame.K_2: Difficulty.BALANCED, pygame.K_3: Difficulty.MASTER}[key]
                self.model.set_difficulty(selected)
            self.audio.master = self.model.settings.master_volume
            self.settings_repository.save(self.model.settings)
            self.save_repository.save(self.model.save)

    def _click(self, pos: tuple[int, int]) -> None:
        if self.model.scene is not SceneId.MENU:
            return
        sx = LOGICAL_SIZE[0] / self.window.get_width()
        sy = LOGICAL_SIZE[1] / self.window.get_height()
        logical = (int(pos[0] * sx), int(pos[1] * sy))
        for index in range(len(MENU_ITEMS)):
            if pygame.Rect(450, 245 + index * 52, 380, 42).collidepoint(logical):
                self.selected = index
                self._menu_action(MENU_ITEMS[index])
                break

    def _menu_action(self, label: str) -> None:
        if label == "Continue":
            self.model.continue_game()
        elif label == "New Game":
            self.model.new_game()
        elif label == "Level Select":
            self.model.go(SceneId.LEVEL_SELECT)
        elif label == "Sandbox":
            self.model.go(SceneId.SANDBOX)
        elif label == "How to Play":
            self.model.go(SceneId.HOW_TO_PLAY)
        elif label == "Settings":
            self.model.go(SceneId.SETTINGS)
        elif label == "Credits":
            self.model.go(SceneId.CREDITS)
        elif label == "Quit":
            self.running = False

    def _finish_calibration(self) -> None:
        camera_id = self.model.settings.camera_id if self.model.settings.camera_id is not None else 0
        self.model.finish_calibration(camera_id)
        self.settings_repository.save(self.model.settings)

    def _begin_level(self) -> None:
        level_id = self.model.current_level_id or "stonewake"
        self.session.start_level(level_id, self.model.save.difficulty)
        self.model.begin_gameplay()

    def _update(self, dt: float) -> None:
        frame = self.vision.latest()
        image = self.vision.latest_image()
        if image is not None:
            self.last_camera_surface = camera_to_surface(image)
        if self.model.scene is SceneId.CALIBRATION:
            self.calibration.observe(frame)
            if self.calibration.complete:
                self._finish_calibration()
        elif self.model.scene is SceneId.GAMEPLAY:
            for event in self.session.update(dt, frame):
                self.audio.play(event.type.value)
                if event.type is GameEventType.LEVEL_COMPLETE:
                    level = self.levels[self.model.current_level_id or "stonewake"]
                    self.model.save = complete_level(self.model.save, level, self.session.snapshot().score)
                    self.save_repository.save(self.model.save)
                    self.model.last_result = "complete"
                    self.model.go(SceneId.RESULTS)
                elif event.type is GameEventType.LEVEL_FAILED:
                    self.model.last_result = "failed"
                    self.model.go(SceneId.RESULTS)

    def _after_results(self) -> None:
        if self.model.last_result == "failed":
            self._begin_level()
            return
        current = self.levels[self.model.current_level_id or "stonewake"]
        if current.next_level:
            self.model.current_level_id = current.next_level
            self.model.go(SceneId.STORY)
        else:
            self.model.go(SceneId.CREDITS)

    def _render(self) -> None:
        scene = self.model.scene
        if scene is SceneId.MENU:
            self.renderer.draw_menu(self.canvas, MENU_ITEMS, self.selected)
        elif scene is SceneId.CALIBRATION:
            self.renderer.draw_calibration(self.canvas, self.vision.latest(), self.calibration.missing, self.last_camera_surface)
        elif scene is SceneId.STORY:
            level = self.levels[self.model.current_level_id or "stonewake"]
            self.renderer.draw_story(self.canvas, level.title, level.intro, level.id)
        elif scene is SceneId.BRIEFING:
            level = self.levels[self.model.current_level_id or "stonewake"]
            lines = [f"New power: {level.unlock.value.title()}", "Complete three waves, then defeat the guardian.", "Keep at least one hand visible. Press Esc to pause."]
            self.renderer.draw_story(self.canvas, "WARDEN BRIEFING", lines, level.id)
        elif scene is SceneId.GAMEPLAY:
            self.renderer.draw_gameplay(self.canvas, self.session.snapshot(), self.last_camera_surface)
        elif scene is SceneId.PAUSE:
            self.renderer.draw_gameplay(self.canvas, self.session.snapshot(), self.last_camera_surface)
            self.renderer.draw_overlay(self.canvas, "PAUSED", ["Enter — resume", "Esc — resume", "Combat timers are frozen"])
        elif scene is SceneId.RESULTS:
            self.renderer.draw_gameplay(self.canvas, self.session.snapshot(), self.last_camera_surface)
            title = "SEAL RESTORED" if self.model.last_result == "complete" else "THE RIFT PREVAILS"
            level = self.levels[self.model.current_level_id or "stonewake"]
            story = list(level.outro) if self.model.last_result == "complete" else []
            lines = [f"Score: {self.session.snapshot().score}", *story, "Enter — continue" if self.model.last_result == "complete" else "Enter — retry level", "Esc — main menu"]
            self.renderer.draw_overlay(self.canvas, title, lines)
        elif scene is SceneId.LEVEL_SELECT:
            unlocked = self.model.save.unlocked_levels
            level = self.levels[unlocked[self.level_select_index]]
            self.renderer.draw_story(self.canvas, "LEVEL SELECT", [level.title, f"Best score: {self.model.save.best_scores.get(level.id, 0)}", "Left/Right — choose   Enter — play"], level.id)
        elif scene is SceneId.SANDBOX:
            frame = self.vision.latest()
            self.canvas.fill((8, 14, 25))
            if self.last_camera_surface:
                self.canvas.blit(pygame.transform.smoothscale(self.last_camera_surface, LOGICAL_SIZE), (0, 0))
            labels = [hand.gesture.value.upper() for hand in frame.hands if hand.gesture]
            self.renderer.draw_overlay(self.canvas, "GESTURE SANDBOX", labels or ["Show a gesture to test recognition", "Esc — main menu"])
        elif scene is SceneId.HOW_TO_PLAY:
            self.renderer._background(self.canvas, "menu")
            self.renderer.draw_overlay(self.canvas, "HOW TO PLAY", ["Fist — Earth   Spread palm — Water", "Closed palm — Air   Two fingers — Fire", "Point — Lightning", "When Convergence is full, bring both hands together", "Esc — main menu"])
        elif scene is SceneId.SETTINGS:
            settings = self.model.settings
            self.renderer._background(self.canvas, "menu")
            self.renderer.draw_overlay(self.canvas, "SETTINGS", [f"Difficulty: {self.model.save.difficulty.value.title()}  (1 Story / 2 Balanced / 3 Master)", f"Camera: {settings.camera_id if settings.camera_id is not None else 'automatic'}  (C — recalibrate)", f"Master volume: {settings.master_volume:.0%}  (Left/Right)", f"Fullscreen: {'On' if settings.fullscreen else 'Off'}  (F)", f"Reduced flash: {'On' if settings.reduced_flash else 'Off'}  (X)", f"Reduced shake: {'On' if settings.reduced_shake else 'Off'}  (S)", "Esc — save and return"])
        else:
            self.renderer._background(self.canvas, "menu")
            self.renderer.draw_overlay(self.canvas, "CREDITS", ["Design & development — project contributors", "Vision — OpenCV, MediaPipe, cvzone", "Interface & audio — Pygame", "Thank you for restoring the seals.", "Esc — main menu"])
        scaled = pygame.transform.smoothscale(self.canvas, self.window.get_size())
        self.window.blit(scaled, (0, 0))
        pygame.display.flip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Elemental Convergence")
    parser.add_argument("--camera", type=int, default=None, help="camera index to open")
    parser.add_argument("--windowed", action="store_true", help="start in a resizable window")
    args = parser.parse_args(argv)
    return Application(args.camera, args.windowed).run()


if __name__ == "__main__":
    raise SystemExit(main())
