from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from typing import Mapping

from ..content import LevelDefinition
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
        self.go(SceneId.CALIBRATION if self.settings.camera_id is None else SceneId.STORY)

    def continue_game(self) -> None:
        incomplete = [item for item in self.save.unlocked_levels if item not in self.save.completed_levels]
        self.current_level_id = incomplete[0] if incomplete else self.save.unlocked_levels[-1]
        self.go(SceneId.STORY)

    def finish_calibration(self, camera_id: int) -> None:
        self.settings = replace(self.settings, camera_id=camera_id)
        self.go(SceneId.STORY if self.current_level_id else SceneId.MENU)

    def select_level(self, level_id: str) -> None:
        if level_id not in self.save.unlocked_levels:
            raise ValueError(f"level is locked: {level_id}")
        self.current_level_id = level_id
        self.go(SceneId.STORY)

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

