from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import math
import random
from typing import Mapping

from .content import LevelDefinition, Objective
from .models import DIFFICULTIES, Difficulty, Element, GestureFrame
from .persistence import SaveData


class SessionState(StrEnum):
    IDLE = "idle"
    ACTIVE = "active"
    PAUSED = "paused"
    BOSS = "boss"
    COMPLETE = "complete"
    FAILED = "failed"


class GameEventType(StrEnum):
    CAST = "cast"
    ENEMY_DEFEATED = "enemy_defeated"
    WAVE_STARTED = "wave_started"
    WAVE_COMPLETE = "wave_complete"
    LIFE_LOST = "life_lost"
    LEVEL_COMPLETE = "level_complete"
    LEVEL_FAILED = "level_failed"
    CONVERGENCE_READY = "convergence_ready"
    CONVERGENCE_STARTED = "convergence_started"


@dataclass(frozen=True, slots=True)
class GameEvent:
    type: GameEventType
    detail: str = ""


@dataclass(slots=True)
class Enemy:
    id: int
    kind: str
    hp: float
    max_hp: float
    x: float
    y: float
    vx: float
    vy: float


@dataclass(frozen=True, slots=True)
class EnemySnapshot:
    id: int
    kind: str
    hp: float
    max_hp: float
    position: tuple[float, float]


@dataclass(frozen=True, slots=True)
class GameSnapshot:
    level_id: str
    level_title: str
    wave_number: int
    state: SessionState
    objective: str
    hp: float
    lives: int
    score: int
    elapsed_seconds: float
    mana: dict[Element, float]
    unlocked_elements: tuple[Element, ...]
    convergence: float
    enemies: tuple[EnemySnapshot, ...]


CAST_DAMAGE = {
    Element.EARTH: 55.0,
    Element.WATER: 35.0,
    Element.AIR: 30.0,
    Element.FIRE: 42.0,
    Element.LIGHTNING: 22.0,
}
CAST_COST = {
    Element.EARTH: 18.0,
    Element.WATER: 8.0,
    Element.AIR: 6.0,
    Element.FIRE: 10.0,
    Element.LIGHTNING: 4.0,
}
CAST_COOLDOWN = {
    Element.EARTH: 0.45,
    Element.WATER: 0.28,
    Element.AIR: 0.22,
    Element.FIRE: 0.32,
    Element.LIGHTNING: 0.14,
}


class GameSession:
    def __init__(self, levels: Mapping[str, LevelDefinition], seed: int | None = None):
        self.levels = dict(levels)
        self.random = random.Random(seed)
        self.level: LevelDefinition | None = None
        self.difficulty = Difficulty.BALANCED
        self.state = SessionState.IDLE
        self.wave_index = 0
        self.hp = 100.0
        self.lives = 3
        self.score = 0
        self.elapsed = 0.0
        self.wave_elapsed = 0.0
        self.missing_seconds = 0.0
        self.convergence = 0.0
        self.unlocked: tuple[Element, ...] = ()
        self.mana = {element: 100.0 for element in Element}
        self.cooldowns: dict[tuple[str, Element], float] = {}
        self.enemies: list[Enemy] = []
        self._next_enemy_id = 1
        self._enemy_attack_remaining = 4.0
        self._last_frame_timestamp: float | None = None
        self._stale_seconds = 0.0

    def start_level(self, level_id: str, difficulty: Difficulty) -> tuple[GameEvent, ...]:
        if level_id not in self.levels:
            raise KeyError(f"unknown level: {level_id}")
        self.level = self.levels[level_id]
        self.difficulty = difficulty
        ids = list(self.levels)
        index = ids.index(level_id)
        self.unlocked = tuple(self.levels[item].unlock for item in ids[: index + 1])
        self.state = SessionState.ACTIVE
        self.wave_index = 0
        self.hp = 100.0
        self.lives = 3
        self.score = 0
        self.elapsed = 0.0
        self.wave_elapsed = 0.0
        self.missing_seconds = 0.0
        self.convergence = 0.0
        self.mana = {element: 100.0 for element in Element}
        self.cooldowns.clear()
        self.enemies.clear()
        self._enemy_attack_remaining = 4.0
        self._spawn_wave()
        return (GameEvent(GameEventType.WAVE_STARTED, "1"),)

    def set_paused(self, paused: bool) -> None:
        if paused and self.state in (SessionState.ACTIVE, SessionState.BOSS):
            self.state = SessionState.PAUSED
        elif not paused and self.state is SessionState.PAUSED:
            self.state = SessionState.BOSS if self.wave_index >= 3 else SessionState.ACTIVE

    def update(self, dt: float, frame: GestureFrame) -> tuple[GameEvent, ...]:
        if dt < 0:
            raise ValueError("dt must not be negative")
        if self.state not in (SessionState.ACTIVE, SessionState.BOSS):
            return ()
        dt = min(dt, 0.5)
        events: list[GameEvent] = []
        self.elapsed += dt
        self.wave_elapsed += dt
        self._tick_cooldowns(dt)
        self._move_enemies(dt)
        for element in self.unlocked:
            self.mana[element] = min(100.0, self.mana[element] + 10.0 * dt)

        if self._last_frame_timestamp == frame.timestamp:
            self._stale_seconds += dt
        else:
            self._last_frame_timestamp = frame.timestamp
            self._stale_seconds = 0.0
        usable_hands = frame.hands if frame.camera_ok and self._stale_seconds <= 0.5 else ()

        previous_missing = self.missing_seconds
        self.missing_seconds = 0.0 if usable_hands else self.missing_seconds + dt
        grace = DIFFICULTIES[self.difficulty].hand_grace_seconds
        exposed = max(0.0, self.missing_seconds - grace) - max(0.0, previous_missing - grace)
        if exposed > 0:
            events.extend(self._apply_damage(exposed * 10.0))
            if self.state is SessionState.FAILED:
                return tuple(events)

        if len(usable_hands) >= 2 and self.convergence >= 100.0 and self._hands_together(usable_hands):
            self.convergence = 0.0
            events.append(GameEvent(GameEventType.CONVERGENCE_STARTED))
            for enemy in list(self.enemies):
                events.extend(self._defeat(enemy))
        else:
            for hand in usable_hands:
                if hand.gesture in self.unlocked:
                    events.extend(self._cast(hand.key, hand.gesture))

        if self.state not in (SessionState.ACTIVE, SessionState.BOSS):
            return tuple(events)
        self._enemy_attack_remaining -= dt
        if self.enemies and self._enemy_attack_remaining <= 0:
            damage = 6.0 * DIFFICULTIES[self.difficulty].enemy_damage
            events.extend(self._apply_damage(damage))
            self._enemy_attack_remaining = 4.0 * DIFFICULTIES[self.difficulty].attack_interval

        if self.wave_index < 3 and self.level is not None:
            wave = self.level.waves[self.wave_index]
            done = not self.enemies if wave.objective is Objective.DEFEAT_ALL else (
                wave.objective is Objective.SURVIVE and self.wave_elapsed >= (wave.duration_seconds or 0)
            )
            if done:
                self.enemies.clear()
                events.extend(self._advance())
        elif self.wave_index >= 3 and not self.enemies:
            self.state = SessionState.COMPLETE
            events.append(GameEvent(GameEventType.LEVEL_COMPLETE, self.level.id if self.level else ""))
        return tuple(events)

    def hurt(self, amount: float) -> tuple[GameEvent, ...]:
        return tuple(self._apply_damage(amount))

    def _apply_damage(self, amount: float) -> list[GameEvent]:
        if self.state in (SessionState.COMPLETE, SessionState.FAILED, SessionState.IDLE):
            return []
        self.hp -= max(0.0, amount)
        if self.hp > 0:
            return []
        self.lives -= 1
        if self.lives <= 0:
            self.hp = 0.0
            self.state = SessionState.FAILED
            return [GameEvent(GameEventType.LEVEL_FAILED)]
        self.hp = 100.0
        self.missing_seconds = 0.0
        return [GameEvent(GameEventType.LIFE_LOST, str(self.lives))]

    def _tick_cooldowns(self, dt: float) -> None:
        for key in list(self.cooldowns):
            self.cooldowns[key] = max(0.0, self.cooldowns[key] - dt)

    def _cast(self, hand_key: str, element: Element) -> list[GameEvent]:
        key = (hand_key, element)
        if self.cooldowns.get(key, 0.0) > 0 or self.mana[element] < CAST_COST[element]:
            return []
        self.cooldowns[key] = CAST_COOLDOWN[element]
        self.mana[element] -= CAST_COST[element]
        events = [GameEvent(GameEventType.CAST, element.value)]
        if self.enemies:
            target = self.enemies[0]
            target.hp -= CAST_DAMAGE[element]
            if target.hp <= 0:
                events.extend(self._defeat(target))
        return events

    def _defeat(self, enemy: Enemy) -> list[GameEvent]:
        if enemy not in self.enemies:
            return []
        self.enemies.remove(enemy)
        self.score += 100
        was_ready = self.convergence >= 100.0
        self.convergence = min(100.0, self.convergence + 25.0)
        events = [GameEvent(GameEventType.ENEMY_DEFEATED, enemy.kind)]
        if not was_ready and self.convergence >= 100.0:
            events.append(GameEvent(GameEventType.CONVERGENCE_READY))
        return events

    def _advance(self) -> list[GameEvent]:
        events = [GameEvent(GameEventType.WAVE_COMPLETE, str(self.wave_index + 1))]
        self.wave_index += 1
        self.wave_elapsed = 0.0
        if self.wave_index < 3:
            self._spawn_wave()
            events.append(GameEvent(GameEventType.WAVE_STARTED, str(self.wave_index + 1)))
        else:
            self.state = SessionState.BOSS
            self._spawn_boss()
            events.append(GameEvent(GameEventType.WAVE_STARTED, "boss"))
        return events

    def _spawn_wave(self) -> None:
        if self.level is None:
            return
        rules = DIFFICULTIES[self.difficulty]
        for kind, count in self.level.waves[self.wave_index].enemies.items():
            for _ in range(count):
                hp = 60.0 * rules.enemy_health
                self.enemies.append(self._enemy(kind, hp))

    def _spawn_boss(self) -> None:
        if self.level is None:
            return
        hp = 300.0 * DIFFICULTIES[self.difficulty].enemy_health
        self.enemies.append(self._enemy(self.level.boss or "guardian", hp))

    def _enemy(self, kind: str, hp: float) -> Enemy:
        enemy = Enemy(
            self._next_enemy_id,
            kind,
            hp,
            hp,
            self.random.uniform(180, 1100),
            self.random.uniform(120, 440),
            self.random.uniform(-45, 45),
            self.random.uniform(-30, 30),
        )
        self._next_enemy_id += 1
        return enemy

    def _move_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            enemy.x += enemy.vx * dt
            enemy.y += enemy.vy * dt
            if not 80 <= enemy.x <= 1200:
                enemy.vx *= -1
                enemy.x = min(1200, max(80, enemy.x))
            if not 90 <= enemy.y <= 520:
                enemy.vy *= -1
                enemy.y = min(520, max(90, enemy.y))

    @staticmethod
    def _hands_together(hands) -> bool:
        first, second = hands[:2]
        distance = math.dist(first.center, second.center)
        return distance < 0.8 * (first.size + second.size)

    def snapshot(self) -> GameSnapshot:
        if self.level is None:
            return GameSnapshot("", "", 0, self.state, "", self.hp, self.lives, self.score, self.elapsed, {}, (), 0, ())
        objective = "BOSS" if self.wave_index >= 3 else self.level.waves[self.wave_index].objective.value
        return GameSnapshot(
            self.level.id,
            self.level.title,
            min(4, self.wave_index + 1),
            self.state,
            objective,
            round(self.hp, 4),
            self.lives,
            self.score,
            round(self.elapsed, 4),
            dict(self.mana),
            self.unlocked,
            self.convergence,
            tuple(EnemySnapshot(e.id, e.kind, e.hp, e.max_hp, (e.x, e.y)) for e in self.enemies),
        )


def complete_level(save: SaveData, level: LevelDefinition, score: int) -> SaveData:
    unlocked = list(save.unlocked_levels)
    if level.next_level and level.next_level not in unlocked:
        unlocked.append(level.next_level)
    completed = list(save.completed_levels)
    if level.id not in completed:
        completed.append(level.id)
    scores = dict(save.best_scores)
    scores[level.id] = max(score, scores.get(level.id, 0))
    return replace(
        save,
        unlocked_levels=tuple(unlocked),
        completed_levels=tuple(completed),
        best_scores=scores,
    )
