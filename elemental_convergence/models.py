from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping


class Element(StrEnum):
    EARTH = "earth"
    WATER = "water"
    AIR = "air"
    FIRE = "fire"
    LIGHTNING = "lightning"


class Difficulty(StrEnum):
    STORY = "story"
    BALANCED = "balanced"
    MASTER = "master"


@dataclass(frozen=True, slots=True)
class DifficultyRules:
    enemy_health: float
    enemy_damage: float
    attack_interval: float
    hand_grace_seconds: float
    aim_assist: float


DIFFICULTIES: Mapping[Difficulty, DifficultyRules] = {
    Difficulty.STORY: DifficultyRules(0.75, 0.65, 1.25, 2.0, 0.8),
    Difficulty.BALANCED: DifficultyRules(1.0, 1.0, 1.0, 1.25, 0.6),
    Difficulty.MASTER: DifficultyRules(1.25, 1.25, 0.8, 0.8, 0.35),
}


@dataclass(frozen=True, slots=True)
class HandPose:
    key: str
    gesture: Element | None
    center: tuple[float, float]
    direction: tuple[float, float]
    size: float
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class GestureFrame:
    timestamp: float
    hands: tuple[HandPose, ...] = ()
    camera_ok: bool = True

