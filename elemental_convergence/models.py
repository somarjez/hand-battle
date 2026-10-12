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


REFERENCE_SIZE = (1280, 720)


def canvas_size_for(window: tuple[int, int], reference: tuple[int, int] = REFERENCE_SIZE) -> tuple[int, int]:
    """Logical canvas that has the window's aspect ratio and is at least as big as the 1280x720 reference.

    Because the canvas and the window share an aspect ratio, scaling canvas -> window never stretches
    anything and never leaves black bars.
    """
    ww, wh = max(1, window[0]), max(1, window[1])
    aspect = ww / wh
    rw, rh = reference
    if aspect >= rw / rh:
        return (int(round(rh * aspect)), rh)
    return (rw, int(round(rw / aspect)))


def cover_transform(source: tuple[int, int], target: tuple[int, int]) -> tuple[float, float, float]:
    """(scale, offset_x, offset_y) that fills `target` with `source`, cropping the overflow (no distortion)."""
    scale = max(target[0] / source[0], target[1] / source[1])
    return scale, (target[0] - source[0] * scale) / 2.0, (target[1] - source[1] * scale) / 2.0


def scale_frame(frame: GestureFrame, source: tuple[int, int], target: tuple[int, int]) -> GestureFrame:
    """Map hand positions from camera pixels to the game canvas using the same crop the picture uses."""
    if source == target or not frame.hands or source[0] <= 0 or source[1] <= 0:
        return frame
    scale, ox, oy = cover_transform(source, target)
    scaled = tuple(
        HandPose(
            hand.key,
            hand.gesture,
            (hand.center[0] * scale + ox, hand.center[1] * scale + oy),
            hand.direction,
            hand.size * scale,
            hand.confidence,
        )
        for hand in frame.hands
    )
    return GestureFrame(frame.timestamp, scaled, frame.camera_ok)
