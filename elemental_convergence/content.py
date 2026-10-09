from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .models import Element


class ContentError(ValueError):
    pass


class Objective(StrEnum):
    DEFEAT_ALL = "defeat_all"
    SURVIVE = "survive"
    BOSS = "boss"


@dataclass(frozen=True, slots=True)
class WaveDefinition:
    objective: Objective
    enemies: dict[str, int]
    duration_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class LevelDefinition:
    id: str
    title: str
    unlock: Element
    intro: tuple[str, ...]
    outro: tuple[str, ...]
    waves: tuple[WaveDefinition, ...]
    boss: str | None
    next_level: str | None


DEFAULT_LEVELS_PATH = Path(__file__).with_name("data") / "levels.json"


def _wave(raw: dict[str, Any], level_id: str) -> WaveDefinition:
    try:
        objective = Objective(raw["objective"])
    except (KeyError, ValueError) as exc:
        raise ContentError(f"level {level_id}: invalid objective") from exc
    enemies = raw.get("enemies")
    if not isinstance(enemies, dict) or any(not isinstance(v, int) or v < 0 for v in enemies.values()):
        raise ContentError(f"level {level_id}: enemies must contain non-negative counts")
    duration = raw.get("duration_seconds")
    if objective is Objective.SURVIVE and (not isinstance(duration, (int, float)) or duration <= 0):
        raise ContentError(f"level {level_id}: survive objective needs duration_seconds")
    return WaveDefinition(objective, dict(enemies), float(duration) if duration is not None else None)


def load_levels(path: Path | None = None) -> dict[str, LevelDefinition]:
    source = path or DEFAULT_LEVELS_PATH
    try:
        raw_levels = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentError(f"could not load level content: {source}") from exc
    if not isinstance(raw_levels, list) or not raw_levels:
        raise ContentError("level content must be a non-empty list")
    levels: dict[str, LevelDefinition] = {}
    for raw in raw_levels:
        try:
            level_id = str(raw["id"])
            waves = tuple(_wave(item, level_id) for item in raw["waves"])
            if len(waves) != 3:
                raise ContentError(f"level {level_id}: exactly three waves are required")
            level = LevelDefinition(
                id=level_id,
                title=str(raw["title"]),
                unlock=Element(raw["unlock"]),
                intro=tuple(str(line) for line in raw["intro"]),
                outro=tuple(str(line) for line in raw["outro"]),
                waves=waves,
                boss=str(raw["boss"]) if raw.get("boss") else None,
                next_level=str(raw["next_level"]) if raw.get("next_level") else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ContentError):
                raise
            raise ContentError(f"invalid level definition: {raw!r}") from exc
        if not level.id or level.id in levels:
            raise ContentError(f"duplicate or empty level id: {level.id}")
        levels[level.id] = level
    for level in levels.values():
        if level.next_level is not None and level.next_level not in levels:
            raise ContentError(f"level {level.id}: unknown next level {level.next_level}")
    return levels
