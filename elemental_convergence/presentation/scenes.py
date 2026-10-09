from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from typing import Mapping

from ..content import LevelDefinition
from ..models import Difficulty
from ..persistence import SaveData, Settings


class SceneId(StrEnum):
    MENU = "menu"
    CALIBRATION = "calibration"
    STORY = "story"
    BRIEFING = "briefing"
    LEVEL_SELECT = "level_select"
    GAMEPLAY = "gameplay"
    PAUSE = "pause"
    RESULTS = "results"
    SETTINGS = "settings"
    HOW_TO_PLAY = "how_to_play"
    SANDBOX = "sandbox"
    CREDITS = "credits"


class AppModel:
    """Pure screen-flow state; rendering and hardware stay outside this model."""

    def __init__(self, levels: Mapping[str, LevelDefinition], save: SaveData, settings: Settings):
        self.levels = dict(levels)
        self.save = save
        self.settings = settings
        self.scene = SceneId.MENU
        self.current_level_id: str | None = None
        self.previous_scene = SceneId.MENU
        self.last_result: str | None = None

    def go(self, scene: SceneId) -> None:
        self.previous_scene = self.scene
        self.scene = scene

    def new_game(self) -> None:
        self.current_level_id = "stonewake"
        self._go_to_campaign()

    def continue_game(self) -> None:
        incomplete = [item for item in self.save.unlocked_levels if item not in self.save.completed_levels]
        self.current_level_id = incomplete[0] if incomplete else self.save.unlocked_levels[-1]
        self._go_to_campaign()

    def _go_to_campaign(self) -> None:
        self.go(SceneId.CALIBRATION if self.settings.camera_id is None else SceneId.STORY)

    def finish_calibration(self, camera_id: int) -> None:
        self.settings = replace(self.settings, camera_id=camera_id)
        self.go(SceneId.STORY if self.current_level_id else SceneId.MENU)

    def camera_unavailable(self) -> None:
        self.settings = replace(self.settings, camera_id=None)

    def adjust_master_volume(self, delta: float) -> None:
        volume = min(1.0, max(0.0, self.settings.master_volume + delta))
        self.settings = replace(self.settings, master_volume=round(volume, 2))

    def toggle_reduced_flash(self) -> None:
        self.settings = replace(self.settings, reduced_flash=not self.settings.reduced_flash)

    def toggle_reduced_shake(self) -> None:
        self.settings = replace(self.settings, reduced_shake=not self.settings.reduced_shake)

    def toggle_fullscreen(self) -> None:
        self.settings = replace(self.settings, fullscreen=not self.settings.fullscreen)

    def set_difficulty(self, difficulty: Difficulty) -> None:
        self.save = replace(self.save, difficulty=difficulty)

    def select_level(self, level_id: str) -> None:
        if level_id not in self.save.unlocked_levels:
            raise ValueError(f"level is locked: {level_id}")
        self.current_level_id = level_id
        self._go_to_campaign()

    def begin_gameplay(self) -> None:
        if self.current_level_id is None:
            raise RuntimeError("select a level before gameplay")
        self.go(SceneId.GAMEPLAY)

    def pause(self) -> None:
        if self.scene is SceneId.GAMEPLAY:
            self.go(SceneId.PAUSE)

    def resume(self) -> None:
        if self.scene is SceneId.PAUSE:
            self.go(SceneId.GAMEPLAY)
