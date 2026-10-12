from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import math
import random
from typing import Any, Mapping

from . import combat
from .combat import CombatField, Enemy, Hit, hand_zone_radius, kind_info
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
    PLAYER_HIT = "player_hit"
    COMBAT_FX = "combat_fx"
    LOOT_COLLECTED = "loot_collected"


@dataclass(frozen=True, slots=True)
class GameEvent:
    type: GameEventType
    detail: str = ""
    data: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class EnemySnapshot:
    id: int
    kind: str
    hp: float
    max_hp: float
    position: tuple[float, float]
    radius: float = 38.0
    boss: bool = False
    enraged: bool = False
    warn: float = 0.0          # 0..1 - how close the enemy is to attacking (drives the red warning ring)
    wind: float = 0.0          # 0..1 - charger wind-up progress
    dashing: bool = False
    direction: tuple[float, float] = (0.0, 1.0)
    age: float = 9.0           # seconds since it appeared (spawn-in animation)
    blink: float = 0.0         # >0 right after a blinker teleports
    spiral: bool = False
    elite: bool = False
    phase: int = 1


@dataclass(frozen=True, slots=True)
class ShotSnapshot:
    x: float
    y: float
    r: float
    tint: tuple[int, int, int]
    home: bool = False
    wall: bool = False
    phase: float = 0.0


@dataclass(frozen=True, slots=True)
class LaserSnapshot:
    ox: float
    oy: float
    dx: float
    dy: float
    progress: float            # 0..1 through the warning, then 0..1 through the beam
    firing: bool
    width: float = 1.0
    t: float = 0.0


@dataclass(frozen=True, slots=True)
class BombSnapshot:
    x: float
    y: float
    r: float
    progress: float            # 0..1 fuse burning, then 0..1 through the blast
    blasting: bool = False


@dataclass(frozen=True, slots=True)
class LootSnapshot:
    id: int
    kind: str                  # heart | regen | shield | boost | mana:<element>
    x: float
    y: float
    r: float
    age: float
    life: float                # seconds left before it fades away


@dataclass(slots=True)
class Loot:
    id: int
    kind: str
    x: float
    y: float
    rest_y: float              # drops from defeated enemies fall to this height, then float
    age: float = 0.0
    life: float = 12.0


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
    shots: tuple[ShotSnapshot, ...] = ()
    lasers: tuple[LaserSnapshot, ...] = ()
    bombs: tuple[BombSnapshot, ...] = ()
    invulnerable: float = 0.0      # seconds of hit-protection left
    hands_visible: bool = True
    time_left: float | None = None  # survive waves only
    enemies_left: int = 0
    loot: tuple[LootSnapshot, ...] = ()
    regen: float = 0.0             # seconds of each pick-up effect still running
    shield: float = 0.0
    boost: float = 0.0
    ultimate: float = 0.0          # seconds of the Convergence ultimate still running
    convergence_hold: float = 0.0  # 0..1 while you hold both hands together on a full meter
    quota: int | None = None       # hunt waves
    quota_done: int = 0
    combo: int = 0
    combo_mult: int = 1
    combo_left: float = 0.0        # seconds left to extend the chain
    hazard_label: str = ""


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
# How far each element's blast reaches along its path when it shoots enemy orbs down.
CAST_REACH = {
    Element.EARTH: 44.0,
    Element.WATER: 40.0,
    Element.AIR: 72.0,
    Element.FIRE: 36.0,
    Element.LIGHTNING: 34.0,
}
CAST_KNOCKBACK = {
    Element.EARTH: 300.0,
    Element.WATER: 230.0,
    Element.AIR: 190.0,
    Element.FIRE: 120.0,
    Element.LIGHTNING: 40.0,
}
CHAIN_RANGE = 380.0
CHAIN_FALLOFF = 0.6

# Balance. Enemies now fight back with real, dodgeable attacks, so they live long
# enough for you to see them. Lower these to go back to one-shot enemies.
ENEMY_BASE_HP = 110.0
BOSS_BASE_HP = 900.0
MINION_HP_FRACTION = 0.45
BOSS_HEAL = 50.0           # health back for defeating a guardian
# Convergence ultimate: hits everything on screen, and everything that arrives while it lasts.
ULTIMATE_TIME = 1.8
CONVERGENCE_BOSS_FRACTION = 1.0   # share of a guardian's max HP the ultimate removes (1.0 = defeats it; try 0.5)

# Scoring: chain kills inside the window to raise the multiplier.
COMBO_WINDOW = 3.0
COMBO_STEP = 3                     # every this many chained kills raises the multiplier by one
COMBO_MAX = 5
SCORE_KILL, SCORE_ELITE, SCORE_BOSS = 100, 300, 1000
ELITE_HP = 2.4
ELITE_RADIUS = 1.25
BOSS_PHASES = (0.66, 0.33)         # health fractions that open the next phase
STAR_HIT_LIMIT = 5                 # three stars: no life lost and at most this many hits taken

# Loot you collect by touching it with a hand.
LOOT_LIFETIME = 12.0
LOOT_RADIUS = 28.0
LOOT_MAX = 4
LOOT_INTERVAL = (9.0, 14.0)       # seconds between free-floating pick-ups
LOOT_DROP_CHANCE = 0.16           # chance a defeated enemy drops one
HEART_HEAL = 25.0
REGEN_RATE = 5.0                  # HP per second ...
REGEN_TIME = 6.0                  # ... for this long
SHIELD_TIME = 8.0                 # every hit is blocked
BOOST_TIME = 10.0
BOOST_DAMAGE = 1.5                # blast damage multiplier
BOOST_COOLDOWN = 0.65             # blasts come this much faster
REINFORCE_DELAY = 0.9      # seconds before a survive wave replaces a fallen enemy
WIPE_DELAY = 0.5           # ...or sends a whole new group after the arena is cleared
REINFORCE_CUTOFF = 2.5     # no single replacements this close to the end of the wave
REINFORCE_LAST_CALL = 0.8  # (a cleared arena is refilled until almost the very end)
HIT_INVULN = 0.75          # seconds of protection after a hit
LIFE_INVULN = 2.0          # seconds of protection after losing a life
# Convergence: 10 kills fill the meter (a guardian counts as 5), then bring both hands together and hold.
CONVERGENCE_KILLS = 10
CONVERGENCE_BOSS_KILLS = 5
TOGETHER_NEAR = 1.15       # palm centres must be closer than this many hand sizes (palms touching)
TOGETHER_MIN = 0.30        # ...but not on top of each other: that is one hand detected twice
TOGETHER_SAME_LABEL = 0.70 # two detections with the same left/right label must be clearly separate hands
TOGETHER_SIZE_RATIO = (0.55, 1.8)
TOGETHER_CONFIDENCE = 0.6
TOGETHER_HOLD = 0.4        # seconds the gesture must be held, so a passing gesture can't fire it
CONVERGENCE_INVULN = 1.6   # you are untouchable while Convergence is unleashed
CAST_COOLDOWN = {
    Element.EARTH: 0.45,
    Element.WATER: 0.28,
    Element.AIR: 0.22,
    Element.FIRE: 0.32,
    Element.LIGHTNING: 0.14,
}


def _unit(v) -> tuple[float, float]:
    n = math.hypot(v[0], v[1])
    return (1.0, 0.0) if n < 1e-6 else (v[0] / n, v[1] / n)


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
        self.field = CombatField(self.random)
        self.arena = (1280.0, 720.0)
        self.invuln = 0.0
        self.hands_visible = True
        self.reinforce_timer = REINFORCE_DELAY
        self.together_time = 0.0
        self._reset_loot_state()
        self._reset_run_stats()
        self._next_enemy_id = 1
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
        self.together_time = 0.0
        self.mana = {element: 100.0 for element in Element}
        self.cooldowns.clear()
        self.enemies.clear()
        self.field.clear()
        self.invuln = 0.0
        self.hands_visible = True
        self._reset_loot_state()
        self._reset_run_stats()
        self._spawn_wave()
        return (self._wave_started_event("1"),)

    def set_arena(self, size: tuple[float, float]) -> None:
        """Tell the session how big the play area is (matches the window's aspect ratio)."""
        self.arena = (float(size[0]), float(size[1]))
        self.field.size = self.arena

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
        self.invuln = max(0.0, self.invuln - dt)
        self._tick_buffs(dt)
        for element in self.unlocked:
            self.mana[element] = min(100.0, self.mana[element] + 10.0 * dt)

        if self._last_frame_timestamp == frame.timestamp:
            self._stale_seconds += dt
        else:
            self._last_frame_timestamp = frame.timestamp
            self._stale_seconds = 0.0
        usable_hands = frame.hands if frame.camera_ok and self._stale_seconds <= 0.5 else ()
        self.hands_visible = bool(usable_hands)

        previous_missing = self.missing_seconds
        self.missing_seconds = 0.0 if usable_hands else self.missing_seconds + dt
        grace = DIFFICULTIES[self.difficulty].hand_grace_seconds
        exposed = max(0.0, self.missing_seconds - grace) - max(0.0, previous_missing - grace)
        if exposed > 0:
            events.extend(self._apply_damage(exposed * 10.0))
            if self.state is SessionState.FAILED:
                return tuple(events)

        ready = self.convergence >= 100.0
        pair = self._convergence_pair(usable_hands) if ready else None
        if pair is not None:                               # the pose has to be held, not just passed through
            self.together_time = min(TOGETHER_HOLD, self.together_time + dt)
        else:
            self.together_time = max(0.0, self.together_time - dt * 3.0)
        if pair is not None and self.together_time >= TOGETHER_HOLD:
            self.convergence = 0.0
            self.together_time = 0.0
            first, second = pair
            centre = ((first.center[0] + second.center[0]) / 2, (first.center[1] + second.center[1]) / 2)
            events.append(GameEvent(GameEventType.CONVERGENCE_STARTED, data={"x": centre[0], "y": centre[1]}))
            self.invuln = max(self.invuln, CONVERGENCE_INVULN)
            self.ultimate = ULTIMATE_TIME
            self._ultimate_hit = set()
            self.field.clear()
            events.extend(self._ultimate_sweep())
        elif pair is None:                                 # no stray blasts while you are clasping your hands
            for hand in usable_hands:
                if hand.gesture in self.unlocked:
                    events.extend(self._cast(hand, hand.gesture))

        if self.state not in (SessionState.ACTIVE, SessionState.BOSS):
            return tuple(events)
        events.extend(self._fight(dt, usable_hands))
        if self.state not in (SessionState.ACTIVE, SessionState.BOSS):
            return tuple(events)
        if self.ultimate > 0:                              # anything that just arrived (summons, reinforcements) is hit too
            self.field.clear()
            events.extend(self._ultimate_sweep())
        else:
            events.extend(self._update_hazard(dt, usable_hands))
        events.extend(self._boss_phases())
        events.extend(self._update_loot(dt, usable_hands))

        if self.wave_index < 3 and self.level is not None:
            wave = self.level.waves[self.wave_index]
            if wave.objective in (Objective.SURVIVE, Objective.HUNT):
                self._reinforce(dt, wave)
            if wave.objective is Objective.DEFEAT_ALL:
                done = not self.enemies
            elif wave.objective is Objective.HUNT:
                done = self.wave_kills >= (wave.quota or 0)
            else:
                done = self.wave_elapsed >= (wave.duration_seconds or 0)
            if done:
                self.enemies.clear()
                events.extend(self._advance())
        elif self.wave_index >= 3 and not self.enemies:
            self.state = SessionState.COMPLETE
            events.append(GameEvent(GameEventType.LEVEL_COMPLETE, self.level.id if self.level else "",
                                    {"stars": self.stars(), "score": self.score}))
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
        self.invuln = LIFE_INVULN
        self.field.clear()
        return [GameEvent(GameEventType.LIFE_LOST, str(self.lives))]

    def _tick_cooldowns(self, dt: float) -> None:
        for key in list(self.cooldowns):
            self.cooldowns[key] = max(0.0, self.cooldowns[key] - dt)

    def _cast(self, hand, element: Element) -> list[GameEvent]:
        key = (hand.key, element)
        if self.cooldowns.get(key, 0.0) > 0 or self.mana[element] < CAST_COST[element]:
            return []
        self.cooldowns[key] = CAST_COOLDOWN[element] * (BOOST_COOLDOWN if self.boost_time > 0 else 1.0)
        self.mana[element] -= CAST_COST[element]
        direction = _unit(hand.direction)
        origin = (hand.center[0] + direction[0] * hand.size * 1.1, hand.center[1] + direction[1] * hand.size * 1.1)
        target = self._pick_target(origin, direction)
        damage = CAST_DAMAGE[element] * (BOOST_DAMAGE if self.boost_time > 0 else 1.0)
        data: dict[str, Any] = {
            "element": element.value, "origin": origin, "dir": direction,
            "target": None, "damage": 0.0, "killed": False, "chain": [], "popped": [],
            "defused": [], "interrupted": [], "boosted": self.boost_time > 0,
        }
        end = (origin[0] + direction[0] * 1100.0, origin[1] + direction[1] * 1100.0)
        events: list[GameEvent] = []
        if target is not None:
            end = (target.x, target.y)
            data.update(target=(target.x, target.y), target_id=target.id, damage=damage, radius=target.r)
            self._hurt_enemy(target, damage, direction, CAST_KNOCKBACK[element], data)
            if element is Element.LIGHTNING:                # chain to nearby enemies
                chain_from, used = target, {target.id}
                for _ in range(2):
                    nxt = min(
                        (e for e in self.enemies if e.id not in used and e in self.enemies
                         and math.hypot(e.x - chain_from.x, e.y - chain_from.y) < CHAIN_RANGE),
                        key=lambda e: math.hypot(e.x - chain_from.x, e.y - chain_from.y),
                        default=None,
                    )
                    if nxt is None:
                        break
                    data["chain"].append((nxt.x, nxt.y))
                    used.add(nxt.id)
                    self._hurt_enemy(nxt, damage * CHAIN_FALLOFF, direction, CAST_KNOCKBACK[element], data)
                    chain_from = nxt
            data["killed"] = target.hp <= 0
        data["popped"] = self.field.shoot_down(origin, end, CAST_REACH[element])
        data["defused"] = self.field.defuse(origin, end, CAST_REACH[element])
        data["end"] = end
        events.append(GameEvent(GameEventType.CAST, element.value, data))
        events.extend(self._reap())
        return events

    def _pick_target(self, origin: tuple[float, float], direction: tuple[float, float]) -> Enemy | None:
        """The enemy best lined up with where the hand points (nearer wins a tie)."""
        best, best_score = None, -1e9
        for enemy in self.enemies:
            vx, vy = enemy.x - origin[0], enemy.y - origin[1]
            dist = math.hypot(vx, vy) + 1e-6
            score = (vx * direction[0] + vy * direction[1]) / dist - dist / 4000.0
            if score > best_score:
                best, best_score = enemy, score
        return best

    def _hurt_enemy(self, enemy: Enemy, amount: float, direction: tuple[float, float], knock: float,
                    data: dict[str, Any] | None = None) -> None:
        kb = 0.12 if enemy.boss else 1.0
        enemy.hp -= amount
        enemy.flash = 0.09
        enemy.kx += direction[0] * knock * kb
        enemy.ky += direction[1] * knock * kb
        if enemy.hp > 0 and not enemy.boss and self.field.interrupt(enemy) and data is not None:
            data["interrupted"].append((enemy.x, enemy.y))      # you broke up its attack

    def _reap(self) -> list[GameEvent]:
        """Remove every enemy whose health ran out and report the defeats."""
        events: list[GameEvent] = []
        for enemy in [e for e in self.enemies if e.hp <= 0]:
            events.extend(self._defeat(enemy))
        return events

    def _defeat(self, enemy: Enemy, charge: bool = True) -> list[GameEvent]:
        if enemy not in self.enemies:
            return []
        self.enemies.remove(enemy)
        if enemy.boss:
            self.hp = min(100.0, self.hp + BOSS_HEAL)
        self._award(enemy)
        was_ready = self.convergence >= 100.0
        if charge:                                         # the ultimate must not recharge itself
            kills = CONVERGENCE_BOSS_KILLS if enemy.boss else 1
            self.convergence = min(100.0, self.convergence + kills * 100.0 / CONVERGENCE_KILLS)
        events = [GameEvent(GameEventType.ENEMY_DEFEATED, enemy.kind, {
            "x": enemy.x, "y": enemy.y, "kind": enemy.kind, "boss": enemy.boss, "r": enemy.r, "id": enemy.id,
            "ultimate": not charge, "elite": enemy.elite,
            "line": self.level.boss_lines.get("defeat", "") if (enemy.boss and self.level is not None) else "",
        })]
        if enemy.elite or (charge and not enemy.boss and self.random.random() < LOOT_DROP_CHANCE):
            self._spawn_loot(at=(enemy.x, enemy.y))
        if not was_ready and self.convergence >= 100.0:
            events.append(GameEvent(GameEventType.CONVERGENCE_READY))
        return events

    def _advance(self) -> list[GameEvent]:
        events = [GameEvent(GameEventType.WAVE_COMPLETE, str(self.wave_index + 1))]
        self.wave_index += 1
        self.wave_elapsed = 0.0
        self.wave_kills = 0
        self.field.clear()
        self.reinforce_timer = REINFORCE_DELAY
        if self.wave_index < 3:
            self._spawn_wave()
            events.append(self._wave_started_event(str(self.wave_index + 1)))
        else:
            self.state = SessionState.BOSS
            self._spawn_boss()
            events.append(self._wave_started_event("boss"))
        return events

    # ---- stage hazards and boss phases ------------------------------------------
    def _update_hazard(self, dt: float, hands) -> list[GameEvent]:
        hazard = self.level.hazard if self.level is not None else None
        if hazard is None or not hands:
            return []
        self.hazard_timer -= dt
        if self.hazard_timer > 0:
            return []
        rules = DIFFICULTIES[self.difficulty]
        zones = [(h.center[0], h.center[1], hand_zone_radius(h.size)) for h in hands]
        used = self.field.hazard(hazard.kind, zones, rules.enemy_damage)
        boss_fight = self.state is SessionState.BOSS
        self.hazard_timer = hazard.interval * rules.attack_interval * (1.3 if boss_fight else 1.0) * self.random.uniform(0.85, 1.15)
        return [GameEvent(GameEventType.COMBAT_FX, "hazard", {"kind": used, "label": hazard.label})]

    def _boss_phases(self) -> list[GameEvent]:
        events: list[GameEvent] = []
        for boss in self.enemies:
            if not boss.boss:
                continue
            fraction = boss.hp / boss.max_hp
            phase = 1 + sum(1 for threshold in BOSS_PHASES if fraction <= threshold)
            if phase <= boss.phase:
                continue
            boss.phase = phase
            minions = kind_info(boss.kind).minions or ("shooter",)
            for _ in range(2):
                self.field.spawn_requests.append((self.random.choice(minions), boss.x + self.random.uniform(-90, 90),
                                                  boss.y + self.random.uniform(70, 130)))
            line = self.level.boss_lines.get(f"phase{phase}", "") if self.level is not None else ""
            events.append(GameEvent(GameEventType.COMBAT_FX, "boss_phase", {
                "phase": phase, "line": line, "x": boss.x, "y": boss.y,
            }))
        return events

    # ---- Convergence ultimate -------------------------------------------------
    def _award(self, enemy: Enemy) -> None:
        self.combo += 1
        self.combo_timer = COMBO_WINDOW
        multiplier = self._combo_mult()
        self.max_combo = max(self.max_combo, multiplier)
        base = SCORE_BOSS if enemy.boss else (SCORE_ELITE if enemy.elite else SCORE_KILL)
        self.score += base * multiplier
        if not enemy.boss:
            self.wave_kills += 1

    def _combo_mult(self) -> int:
        return min(COMBO_MAX, 1 + self.combo // COMBO_STEP)

    def _ultimate_sweep(self) -> list[GameEvent]:
        """Hit every enemy on the field: regular enemies and minions are defeated, guardians take heavy damage."""
        events: list[GameEvent] = []
        for enemy in list(self.enemies):
            if enemy.boss and CONVERGENCE_BOSS_FRACTION < 1.0:
                if enemy.id in self._ultimate_hit:         # a guardian only takes the blow once per ultimate
                    continue
                self._ultimate_hit.add(enemy.id)
                enemy.hp -= enemy.max_hp * CONVERGENCE_BOSS_FRACTION
                enemy.flash = 0.2
                if enemy.hp > 0:
                    continue
            events.extend(self._defeat(enemy, charge=False))
        return events

    # ---- loot & buffs ----------------------------------------------------------
    def _reset_run_stats(self) -> None:
        self.wave_kills = 0
        self.combo = 0
        self.max_combo = 0
        self.combo_timer = 0.0
        self.hits_taken = 0
        self.seen_kinds: set[str] = set()
        hazard = self.level.hazard if self.level is not None else None
        self.hazard_timer = hazard.first if hazard is not None else 1e9

    def stars(self) -> int:
        """1 for clearing the stage, +1 for losing no life, +1 for taking few hits."""
        return 1 + (1 if self.lives >= 3 else 0) + (1 if self.lives >= 3 and self.hits_taken <= STAR_HIT_LIMIT else 0)

    def _wave_started_event(self, detail: str) -> GameEvent:
        level = self.level
        data: dict[str, Any] = {}
        if level is not None:
            titles = level.wave_titles
            index = 3 if detail == "boss" else int(detail) - 1
            if index < len(titles):
                data["title"] = titles[index]
            if detail == "boss":
                data["name"] = level.boss_name
                data["line"] = level.boss_lines.get("intro", "")
        return GameEvent(GameEventType.WAVE_STARTED, detail, data)

    def _reset_loot_state(self) -> None:
        self.loot: list[Loot] = []
        self._next_loot_id = 1
        self.loot_timer = self.random.uniform(5.0, 8.0)
        self.regen_time = self.shield_time = self.boost_time = self.ultimate = 0.0
        self._ultimate_hit: set[int] = set()

    def _tick_buffs(self, dt: float) -> None:
        if self.combo_timer > 0:
            self.combo_timer = max(0.0, self.combo_timer - dt)
            if self.combo_timer == 0.0:
                self.combo = 0
        if self.regen_time > 0:
            self.hp = min(100.0, self.hp + REGEN_RATE * min(dt, self.regen_time))
            self.regen_time = max(0.0, self.regen_time - dt)
        self.shield_time = max(0.0, self.shield_time - dt)
        self.boost_time = max(0.0, self.boost_time - dt)
        self.ultimate = max(0.0, self.ultimate - dt)

    def _loot_kind(self) -> str:
        weights: dict[str, float] = {
            "heart": 3.0 if self.hp < 50 else (2.0 if self.hp < 85 else 0.6),
            "regen": 1.3 if self.hp < 100 else 0.5,
            "shield": 1.5,
            "boost": 1.5,
        }
        for element in self.unlocked:
            level = self.mana[element]
            weights[f"mana:{element.value}"] = 2.5 if level < 35 else (1.0 if level < 90 else 0.2)
        kinds = list(weights)
        return self.random.choices(kinds, weights=[weights[k] for k in kinds])[0]

    def _spawn_loot(self, at: tuple[float, float] | None = None) -> None:
        if len(self.loot) >= LOOT_MAX:
            return
        w, h = self.arena
        rest = self.random.uniform(0.5 * h, 0.78 * h)
        x, y = at if at is not None else (self.random.uniform(0.12 * w, 0.88 * w), rest)
        x = min(max(x, 0.06 * w), 0.94 * w)
        self.loot.append(Loot(self._next_loot_id, self._loot_kind(), x, y, max(rest, y), 0.0, LOOT_LIFETIME))
        self._next_loot_id += 1

    def _update_loot(self, dt: float, hands) -> list[GameEvent]:
        events: list[GameEvent] = []
        self.loot_timer -= dt
        if self.loot_timer <= 0:
            self._spawn_loot()
            self.loot_timer = self.random.uniform(*LOOT_INTERVAL)
        zones = [(h.center[0], h.center[1], hand_zone_radius(h.size)) for h in hands]
        keep: list[Loot] = []
        for item in self.loot:
            item.age += dt
            if item.y < item.rest_y:                       # dropped loot falls, then floats
                item.y = min(item.rest_y, item.y + 90.0 * dt)
            if item.age >= item.life:
                continue
            if any(math.hypot(zx - item.x, zy - item.y) < zr + LOOT_RADIUS for zx, zy, zr in zones):
                events.append(self._collect(item))
            else:
                keep.append(item)
        self.loot = keep
        return events

    def _collect(self, item: Loot) -> GameEvent:
        label = ""
        if item.kind == "heart":
            self.hp = min(100.0, self.hp + HEART_HEAL)
            label = f"+{int(HEART_HEAL)} HP"
        elif item.kind == "regen":
            self.regen_time = REGEN_TIME
            label = "REGEN"
        elif item.kind == "shield":
            self.shield_time = SHIELD_TIME
            label = "SHIELD"
        elif item.kind == "boost":
            self.boost_time = BOOST_TIME
            label = "BOOST"
        elif item.kind.startswith("mana:"):
            element = Element(item.kind.split(":", 1)[1])
            self.mana[element] = 100.0
            label = f"{element.value.upper()} MANA FULL"
        return GameEvent(GameEventType.LOOT_COLLECTED, item.kind, {"x": item.x, "y": item.y, "label": label})

    def _reinforce(self, dt: float, wave) -> None:
        """Survive waves keep the arena populated until the clock runs out.

        A fallen enemy is replaced after a short delay; if the arena is wiped completely a whole new
        group (the wave's roster) arrives after half a second.
        """
        rules = DIFFICULTIES[self.difficulty]
        want = sum(wave.enemies.values())
        remaining = (wave.duration_seconds or 0.0) - self.wave_elapsed
        if wave.objective is Objective.HUNT:               # a hunt has no clock: keep feeding enemies until the quota
            remaining = 1e9
            want = min(want, max(0, (wave.quota or 0) - self.wave_kills))
        wiped = not self.enemies
        if len(self.enemies) >= want or remaining <= (REINFORCE_LAST_CALL if wiped else REINFORCE_CUTOFF):
            self.reinforce_timer = (WIPE_DELAY if wiped else REINFORCE_DELAY) * rules.attack_interval
            return
        self.reinforce_timer -= dt
        if self.reinforce_timer > 0:
            return
        roster = [kind for kind, count in wave.enemies.items() for _ in range(count)]
        arrivals = (roster if wiped else [self.random.choice(roster)])[:max(1, want)]
        for kind in arrivals:
            self.enemies.append(self._enemy(kind, ENEMY_BASE_HP * kind_info(kind).hp * rules.enemy_health))
        self.reinforce_timer = REINFORCE_DELAY * rules.attack_interval

    def _spawn_wave(self) -> None:
        if self.level is None:
            return
        rules = DIFFICULTIES[self.difficulty]
        wave = self.level.waves[self.wave_index]
        for kind, count in wave.enemies.items():
            for _ in range(count):
                hp = ENEMY_BASE_HP * kind_info(kind).hp * rules.enemy_health
                self.enemies.append(self._enemy(kind, hp))
        for kind in wave.elite:
            elite = self._enemy(kind, ENEMY_BASE_HP * kind_info(kind).hp * rules.enemy_health * ELITE_HP)
            elite.elite = True
            elite.r *= ELITE_RADIUS
            self.enemies.append(elite)

    def _spawn_boss(self) -> None:
        if self.level is None:
            return
        hp = BOSS_BASE_HP * DIFFICULTIES[self.difficulty].enemy_health
        boss = self._enemy(self.level.boss or "guardian", hp, at=(self.arena[0] / 2, self.arena[1] * 0.44))
        boss.boss = True
        boss.atk = 2.2 * DIFFICULTIES[self.difficulty].attack_interval
        self.enemies.append(boss)

    def _enemy(self, kind: str, hp: float, at: tuple[float, float] | None = None) -> Enemy:
        info = kind_info(kind)
        rules = DIFFICULTIES[self.difficulty]
        x, y = at if at is not None else (
            self.random.uniform(0.14 * self.arena[0], 0.86 * self.arena[0]),
            self.random.uniform(0.18 * self.arena[1], 0.60 * self.arena[1]),
        )
        enemy = Enemy(
            self._next_enemy_id,
            kind,
            hp,
            hp,
            x,
            y,
            self.random.uniform(-45, 45) * info.speed,
            self.random.uniform(-30, 30) * info.speed,
            r=float(self.random.randint(*info.radius)),
            ph=self.random.uniform(0, 6.28),
            atk=self.random.uniform(*combat.FIRST_ATTACK_DELAY) * rules.attack_interval,
            boss=info.boss,
        )
        self._next_enemy_id += 1
        self.seen_kinds.add(kind)
        return enemy

    # ---- enemy offence ---------------------------------------------------------
    def _fight(self, dt: float, hands) -> list[GameEvent]:
        """Move enemies, let them attack, and apply whatever reaches the player's hands."""
        rules = DIFFICULTIES[self.difficulty]
        zones = [(h.center[0], h.center[1], hand_zone_radius(h.size)) for h in hands]
        tempo = 1.0 + 0.06 * self.wave_index
        hits = self.field.update(
            dt, self.enemies, zones,
            dmg_mult=rules.enemy_damage, rate_mult=rules.attack_interval, tempo=tempo,
        )
        events: list[GameEvent] = []
        for kind, x, y in self.field.drain_spawns():
            minion = self._enemy(kind, ENEMY_BASE_HP * MINION_HP_FRACTION * kind_info(kind).hp
                                 * rules.enemy_health, at=(x, y))
            self.enemies.append(minion)
        for name, data in self.field.drain_notes():
            events.append(GameEvent(GameEventType.COMBAT_FX, name, data))
        for hit in hits:
            events.extend(self._take_hit(hit))
            if self.state is SessionState.FAILED:
                break
        return events

    def _take_hit(self, hit: Hit) -> list[GameEvent]:
        if self.invuln > 0 or self.state not in (SessionState.ACTIVE, SessionState.BOSS):
            return []
        if self.shield_time > 0:                            # a shield pick-up blocks the hit completely
            self.invuln = 0.25
            return [GameEvent(GameEventType.COMBAT_FX, "shield_block", {"x": hit.x, "y": hit.y})]
        self.invuln = HIT_INVULN
        self.hits_taken += 1
        events = [GameEvent(GameEventType.PLAYER_HIT, hit.source, {
            "x": hit.x, "y": hit.y, "amount": hit.amount, "source": hit.source,
        })]
        events.extend(self._apply_damage(hit.amount))
        return events

    @staticmethod
    def _convergence_pair(hands):
        """The two hands that are genuinely pressed together, or None.

        Rejects the usual false positives: one hand detected twice (same spot / same label), a ghost
        detection of a different size, low-confidence detections, and hands that are merely close.
        """
        for i in range(len(hands)):
            for j in range(i + 1, len(hands)):
                a, b = hands[i], hands[j]
                if min(a.confidence, b.confidence) < TOGETHER_CONFIDENCE or min(a.size, b.size) <= 0:
                    continue
                if not TOGETHER_SIZE_RATIO[0] <= a.size / b.size <= TOGETHER_SIZE_RATIO[1]:
                    continue
                avg = (a.size + b.size) / 2
                distance = math.dist(a.center, b.center)
                if distance > TOGETHER_NEAR * avg:
                    continue
                same_label = a.key.rstrip("0123456789") == b.key.rstrip("0123456789")
                if distance < (TOGETHER_SAME_LABEL if same_label else TOGETHER_MIN) * avg:
                    continue
                return a, b
        return None

    def snapshot(self) -> GameSnapshot:
        if self.level is None:
            return GameSnapshot("", "", 0, self.state, "", self.hp, self.lives, self.score, self.elapsed, {}, (), 0, ())
        objective = "BOSS" if self.wave_index >= 3 else self.level.waves[self.wave_index].objective.value
        time_left = None
        if self.wave_index < 3:
            wave = self.level.waves[self.wave_index]
            if wave.objective is Objective.SURVIVE:
                time_left = max(0.0, (wave.duration_seconds or 0.0) - self.wave_elapsed)
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
            tuple(self._enemy_snapshot(e) for e in self.enemies),
            shots=tuple(ShotSnapshot(s.x, s.y, s.r, s.tint, s.home, s.wall, s.ph) for s in self.field.shots),
            lasers=tuple(self._laser_snapshot(L) for L in self.field.lasers),
            bombs=tuple(self._bomb_snapshot(b) for b in self.field.bombs if b.t >= 0),
            invulnerable=self.invuln,
            hands_visible=self.hands_visible,
            time_left=time_left,
            enemies_left=len(self.enemies),
            loot=tuple(LootSnapshot(l.id, l.kind, l.x, l.y, LOOT_RADIUS, l.age, max(0.0, l.life - l.age)) for l in self.loot),
            regen=self.regen_time,
            shield=self.shield_time,
            boost=self.boost_time,
            ultimate=self.ultimate,
            convergence_hold=min(1.0, self.together_time / TOGETHER_HOLD),
            quota=self._quota(),
            quota_done=self.wave_kills,
            combo=self.combo,
            combo_mult=self._combo_mult() if self.combo else 1,
            combo_left=self.combo_timer,
        )

    def _quota(self) -> int | None:
        if self.level is None or self.wave_index >= 3:
            return None
        return self.level.waves[self.wave_index].quota

    @staticmethod
    def _enemy_snapshot(e: Enemy) -> EnemySnapshot:
        warn = 0.0
        if e.wind <= 0 and e.dash <= 0 and e.atk < combat.ATTACK_WARNING:
            warn = 1.0 - max(0.0, e.atk) / combat.ATTACK_WARNING
        wind = 1.0 - e.wind / combat.DASH_WINDUP if e.wind > 0 else 0.0
        return EnemySnapshot(
            e.id, e.kind, e.hp, e.max_hp, (e.x, e.y), e.r, e.boss, e.enraged, warn, wind,
            e.dash > 0, e.cdir, e.age, e.blink, e.spiral is not None, e.elite, e.phase,
        )

    @staticmethod
    def _laser_snapshot(L) -> LaserSnapshot:
        if L.t < L.warn:
            progress, firing = L.t / L.warn, False
        else:
            progress, firing = min(1.0, (L.t - L.warn) / max(1e-6, L.fire)), True
        return LaserSnapshot(L.ox, L.oy, L.dx, L.dy, progress, firing, L.width, L.t)

    @staticmethod
    def _bomb_snapshot(b) -> BombSnapshot:
        if b.t < b.fuse:
            return BombSnapshot(b.x, b.y, b.r, max(0.0, b.t / b.fuse), False)
        return BombSnapshot(b.x, b.y, b.r, min(1.0, (b.t - b.fuse) / combat.BOMB_BLAST), True)


def record_seen(save: SaveData, kinds) -> SaveData:
    """Remember which enemies the player has met (unlocks bestiary entries)."""
    seen = tuple(dict.fromkeys((*save.seen_enemies, *sorted(kinds))))
    return replace(save, seen_enemies=seen) if seen != save.seen_enemies else save


def complete_level(save: SaveData, level: LevelDefinition, score: int, stars: int = 1, seen=()) -> SaveData:
    unlocked = list(save.unlocked_levels)
    if level.next_level and level.next_level not in unlocked:
        unlocked.append(level.next_level)
    completed = list(save.completed_levels)
    if level.id not in completed:
        completed.append(level.id)
    scores = dict(save.best_scores)
    scores[level.id] = max(score, scores.get(level.id, 0))
    best_stars = dict(save.best_stars)
    best_stars[level.id] = max(max(1, min(3, stars)), best_stars.get(level.id, 0))
    return record_seen(replace(
        save,
        unlocked_levels=tuple(unlocked),
        completed_levels=tuple(completed),
        best_scores=scores,
        best_stars=best_stars,
    ), seen)
