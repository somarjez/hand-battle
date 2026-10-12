"""Enemy roster and dodgeable enemy attacks.

Pure game logic: no pygame, no OpenCV. Everything is expressed in seconds and
logical pixels (1280x720 arena) so it behaves the same at any frame rate.

The player's hands are *hurt zones*. Enemies aim at them, orbs / beams / bombs
hurt them, and the player can dodge, or shoot orbs out of the air.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Sequence

Vec = tuple[float, float]
Zone = tuple[float, float, float]  # x, y, radius
RGB = tuple[int, int, int]

ARENA: tuple[float, float] = (1280.0, 720.0)

# ---- tuning knobs (seconds, pixels per second) -------------------------------
ORB_SPEED = 300.0
BOSS_ORB_SPEED = 370.0
ORB_DAMAGE = 10.0
BOSS_ORB_DAMAGE = 16.0
RING_DAMAGE = 8.0
HOMING_DAMAGE = 12.0
LASER_DAMAGE = 18.0
BOMB_DAMAGE = 16.0
DASH_DAMAGE = 14.0
CONTACT_DAMAGE = 8.0
BOSS_CONTACT_DAMAGE = 14.0
FIRE_INTERVAL = (2.4, 4.4)        # seconds between normal enemy attacks
BOSS_FIRE_INTERVAL = (1.5, 2.6)
FIRST_ATTACK_DELAY = (2.2, 4.0)   # nobody fires the instant a wave appears
ATTACK_WARNING = 0.8              # the red "about to fire" ring starts this early
DASH_WINDUP = 0.9
DASH_TIME = 0.5
DASH_SPEED = 680.0
LASER_WARN = 1.5
LASER_FIRE = 0.45
BOMB_FUSE = 1.5
BOMB_BLAST = 0.27
KNOCKBACK_SCALE = 1.0

BOSS_ATTACKS = (
    "spread", "ring", "homing", "laser", "summon", "sweep",
    "cross", "bomb", "spiral", "curtain", "burst",
)


# ---- roster ------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class KindInfo:
    title: str
    body: RGB
    accent: RGB
    attacks: tuple[str, ...]
    hp: float = 1.0
    radius: tuple[int, int] = (34, 46)
    speed: float = 1.0
    boss: bool = False
    minions: tuple[str, ...] = ()


ENEMY_KINDS: dict[str, KindInfo] = {
    "shooter": KindInfo("SHOOTER", (112, 48, 150), (214, 120, 255), ("orb", "orb", "spread")),
    "charger": KindInfo("CHARGER", (168, 44, 48), (255, 110, 90), ("dash", "dash", "orb")),
    "sniper": KindInfo("SNIPER", (52, 128, 70), (130, 255, 150), ("laser", "laser", "orb")),
    "gunner": KindInfo("GUNNER", (96, 100, 116), (200, 210, 230), ("burst", "wall", "orb"), hp=1.6, radius=(44, 54)),
    "bomber": KindInfo("BOMBER", (200, 112, 28), (255, 190, 70), ("bomb", "bomb", "orb")),
    "caster": KindInfo("CASTER", (48, 84, 178), (120, 170, 255), ("ring", "homing", "homing")),
    "spinner": KindInfo("SPINNER", (170, 48, 150), (255, 130, 225), ("spiral", "ring", "spiral")),
    "sweeper": KindInfo("SWEEPER", (30, 150, 148), (90, 255, 235), ("sweep", "cross", "laser"), hp=1.1, radius=(36, 48)),
    "blinker": KindInfo("BLINKER", (176, 176, 204), (235, 235, 255), ("blink", "blink", "burst"), hp=0.8, radius=(30, 40)),
}

BOSS_KINDS: dict[str, KindInfo] = {
    "stone_guardian": KindInfo(
        "STONE GUARDIAN", (112, 78, 52), (230, 170, 100),
        ("spread", "orb", "dash", "ring", "summon", "burst"),
        radius=(100, 100), speed=0.6, boss=True, minions=("shooter",),
    ),
    "tide_guardian": KindInfo(
        "TIDE GUARDIAN", (36, 84, 150), (110, 200, 255),
        ("spread", "laser", "bomb", "homing", "summon", "ring"),
        radius=(100, 100), speed=0.6, boss=True, minions=("sniper",),
    ),
    "gale_guardian": KindInfo(
        "GALE GUARDIAN", (110, 150, 150), (225, 255, 245),
        ("wall", "ring", "homing", "burst", "spread", "summon"),
        radius=(100, 100), speed=0.6, boss=True, minions=("caster",),
    ),
    "ember_guardian": KindInfo(
        "EMBER GUARDIAN", (156, 54, 28), (255, 150, 60),
        ("spiral", "sweep", "blink", "bomb", "cross", "summon"),
        radius=(102, 102), speed=0.6, boss=True, minions=("spinner",),
    ),
    "rift_sovereign": KindInfo(
        "RIFT SOVEREIGN", (56, 22, 98), (255, 120, 220),
        BOSS_ATTACKS, radius=(108, 108), speed=0.6, boss=True,
        minions=("shooter", "sniper", "caster"),
    ),
}

_FALLBACK_BOSS = KindInfo(
    "GUARDIAN", (70, 30, 110), (230, 120, 200), BOSS_ATTACKS,
    radius=(100, 100), speed=0.6, boss=True, minions=("shooter",),
)


def kind_info(kind: str) -> KindInfo:
    """Look up an enemy or boss kind. Unknown names degrade gracefully."""
    if kind in ENEMY_KINDS:
        return ENEMY_KINDS[kind]
    if kind in BOSS_KINDS:
        return BOSS_KINDS[kind]
    if "guardian" in kind or "sovereign" in kind or "boss" in kind:
        return _FALLBACK_BOSS
    return ENEMY_KINDS["shooter"]


def is_boss_kind(kind: str) -> bool:
    return kind_info(kind).boss


# ---- entities ----------------------------------------------------------------
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
    r: float = 38.0
    kx: float = 0.0
    ky: float = 0.0
    ph: float = 0.0
    atk: float = 3.0
    wind: float = 0.0
    dash: float = 0.0
    cdir: Vec = (0.0, 1.0)
    queue: list[list[Any]] = field(default_factory=list)
    spiral: dict[str, Any] | None = None
    flash: float = 0.0
    age: float = 0.0
    blink: float = 0.0
    boss: bool = False
    elite: bool = False
    phase: int = 1

    @property
    def enraged(self) -> bool:
        return self.boss and self.hp < self.max_hp * 0.5


@dataclass(slots=True)
class Shot:
    x: float
    y: float
    vx: float
    vy: float
    spd: float
    r: float
    dmg: float
    life: float
    home: bool = False
    wall: bool = False
    tint: RGB = (255, 80, 80)
    ph: float = 0.0


@dataclass(slots=True)
class Laser:
    owner: int | None
    tgt: Vec = (0.0, 0.0)
    fixed_origin: Vec | None = None
    fixed_dir: Vec | None = None
    off: float = 0.0          # degrees away from the aim line
    spin: float = 0.0         # degrees per second while firing
    width: float = 1.0
    t: float = 0.0
    warn: float = LASER_WARN
    fire: float = LASER_FIRE
    tint: RGB = (255, 90, 90)
    # geometry, refreshed every update
    ox: float = 0.0
    oy: float = 0.0
    dx: float = 1.0
    dy: float = 0.0

    @property
    def firing(self) -> bool:
        return self.warn <= self.t < self.warn + self.fire


@dataclass(slots=True)
class Bomb:
    x: float
    y: float
    t: float
    fuse: float
    r: float
    blown: bool = False


@dataclass(frozen=True, slots=True)
class Hit:
    """Damage that reached the player's hand this frame."""
    amount: float
    x: float
    y: float
    source: str


# ---- small helpers -----------------------------------------------------------
def rotate(d: Vec, deg: float) -> Vec:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (d[0] * c - d[1] * s, d[0] * s + d[1] * c)


def normalize(v: Vec) -> Vec:
    n = math.hypot(v[0], v[1]) + 1e-6
    return (v[0] / n, v[1] / n)


def seg_dist(px: float, py: float, a: Vec, b: Vec) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / length))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def hand_zone_radius(size: float) -> float:
    """How big the hurt zone around a hand is (clamped so odd cameras stay fair)."""
    return max(34.0, min(100.0, size * 0.9))


# ---- the battlefield ---------------------------------------------------------
class CombatField:
    """Owns every hostile projectile / beam / bomb and drives enemy behaviour."""

    def __init__(self, rng: random.Random, size: tuple[float, float] = ARENA):
        self.rng = rng
        self.size = size
        self.shots: list[Shot] = []
        self.lasers: list[Laser] = []
        self.bombs: list[Bomb] = []
        self.spawn_requests: list[tuple[str, float, float]] = []
        self.notes: list[tuple[str, dict[str, Any]]] = []   # hints for sound / effects

    # -- lifecycle -------------------------------------------------------------
    def clear(self) -> None:
        self.shots.clear()
        self.lasers.clear()
        self.bombs.clear()
        self.spawn_requests.clear()

    def reset_enemy_attacks(self, enemies: Sequence[Enemy]) -> None:
        for e in enemies:
            e.queue.clear()
            e.spiral = None
            e.wind = e.dash = 0.0

    def note(self, name: str, **data: Any) -> None:
        self.notes.append((name, data))

    def drain_notes(self) -> list[tuple[str, dict[str, Any]]]:
        notes, self.notes = self.notes, []
        return notes

    def drain_spawns(self) -> list[tuple[str, float, float]]:
        spawns, self.spawn_requests = self.spawn_requests, []
        return spawns

    # -- per frame -------------------------------------------------------------
    def update(
        self,
        dt: float,
        enemies: list[Enemy],
        zones: Sequence[Zone],
        *,
        dmg_mult: float = 1.0,
        rate_mult: float = 1.0,
        tempo: float = 1.0,
    ) -> list[Hit]:
        hits: list[Hit] = []
        alive = {e.id for e in enemies}
        self._move(dt, enemies, tempo)
        self._attacks(dt, enemies, zones, dmg_mult, rate_mult, tempo)
        self._update_shots(dt, zones, hits)
        self._update_lasers(dt, enemies, alive, zones, hits, dmg_mult)
        self._update_bombs(dt, zones, hits, dmg_mult)
        self._contact(enemies, zones, hits, dmg_mult)
        return hits

    # -- movement --------------------------------------------------------------
    def _move(self, dt: float, enemies: list[Enemy], tempo: float) -> None:
        w, h = self.size
        rng = self.rng
        decay = 0.85 ** (dt * 30.0)
        for e in enemies:
            e.age += dt
            e.flash = max(0.0, e.flash - dt)
            e.blink = max(0.0, e.blink - dt)
            if e.wind > 0:                                  # charger winds up: stands still
                e.wind -= dt
                if e.wind <= 0:
                    e.wind, e.dash = 0.0, DASH_TIME
                continue
            if e.dash > 0:                                  # charger dashes along its lane
                e.dash -= dt
                m = e.r + 10
                e.x = min(max(e.x + e.cdir[0] * DASH_SPEED * dt, m), w - m)
                e.y = min(max(e.y + e.cdir[1] * DASH_SPEED * dt, m), h - m)
                continue
            info = kind_info(e.kind)
            mult = (1.7 if e.enraged else 1.0) * (1.0 + 0.15 * (tempo - 1.0))
            e.ph += 3.6 * dt
            if rng.random() < 0.9 * dt:
                e.vx = rng.uniform(-60, 60) * info.speed
                e.vy = rng.uniform(-45, 45) * info.speed
            e.x += (e.vx + e.kx) * dt * mult
            e.y += (e.vy + math.sin(e.ph) * 24.0 + e.ky) * dt * mult
            e.kx *= decay
            e.ky *= decay
            m = e.r + 10
            if not m < e.x < w - m:
                e.vx *= -1
                e.x = min(max(e.x, m), w - m)
            ymin, ymax = max(m, h * 0.40 if e.boss else 96.0), h * 0.74
            if e.y > ymax:                                   # glide back after a dash, no snapping
                e.y -= min(e.y - ymax, 320.0 * dt)
                e.vy = -abs(e.vy)
            elif e.y < ymin:
                e.y = min(ymin, e.y + 320.0 * dt)
                e.vy = abs(e.vy)

    # -- attacks ---------------------------------------------------------------
    def _attacks(self, dt: float, enemies: list[Enemy], zones: Sequence[Zone],
                 dmg_mult: float, rate_mult: float, tempo: float) -> None:
        if not zones:                                       # no hands on screen: hold fire
            for e in enemies:
                e.atk = max(e.atk, 1.3)
            return
        for e in enemies:
            if e.queue:                                     # queued follow-up shots (bursts, blink fans)
                keep = []
                for item in e.queue:
                    item[0] -= dt
                    if item[0] <= 0:
                        self._do_attack(e, item[1], enemies, zones, dmg_mult, tempo)
                    else:
                        keep.append(item)
                e.queue = keep
            sp = e.spiral
            if sp is not None:                              # running spiral stream
                sp["left"] -= dt
                sp["acc"] += dt
                while sp["acc"] >= 0.133:
                    sp["acc"] -= 0.133
                    for k in range(sp["arms"]):
                        a = sp["ang"] + k * math.pi
                        self._shoot(e, (math.cos(a), math.sin(a)), (0.0,), sp["spd"], sp["dmg"], sp["r"])
                    sp["ang"] += sp["dir"] * 0.34
                if sp["left"] <= 0:
                    e.spiral = None
            if e.wind > 0 or e.dash > 0:
                continue
            e.atk -= dt * (1.5 if e.enraged else 1.0) * (1.0 + 0.2 * (tempo - 1.0))
            if e.atk > 0:
                continue
            info = kind_info(e.kind)
            self._do_attack(e, self.rng.choice(info.attacks), enemies, zones, dmg_mult, tempo)
            if e.enraged:                                   # berserk boss double-attacks
                self._do_attack(e, self.rng.choice(("spread", "homing", "orb", "burst", "bomb")),
                                enemies, zones, dmg_mult, tempo)
            lo, hi = BOSS_FIRE_INTERVAL if e.boss else FIRE_INTERVAL
            e.atk = self.rng.uniform(lo, hi) * rate_mult

    def _shoot(self, e: Enemy, d: Vec, degs: Sequence[float], spd: float, dmg: float, r: float,
               *, home: bool = False, life: float = 8.0, wall: bool = False) -> None:
        tint = kind_info(e.kind).accent
        for deg in degs:
            dd = rotate(d, deg)
            self.shots.append(Shot(e.x, e.y, dd[0] * spd, dd[1] * spd, spd, r, dmg, life,
                                   home=home, wall=wall, tint=tint, ph=self.rng.uniform(0, 6.28)))

    def _beam(self, origin: Vec, direction: Vec, warn: float = 1.8, fire: float = LASER_FIRE) -> None:
        self.lasers.append(Laser(None, fixed_origin=origin, fixed_dir=direction, warn=warn, fire=fire,
                                 tint=(255, 90, 90)))

    def _do_attack(self, e: Enemy, attack: str, enemies: list[Enemy], zones: Sequence[Zone],
                   dmg_mult: float, tempo: float) -> None:
        w, h = self.size
        rng = self.rng
        boss = e.boss
        base = (BOSS_ORB_SPEED if boss else ORB_SPEED) * min(1.3, 1.0 + 0.15 * (tempo - 1.0))
        dmg = (BOSS_ORB_DAMAGE if boss else ORB_DAMAGE) * dmg_mult
        r = 20.0 if boss else 13.0
        # keep the screen fair: never stack the same big pattern on itself
        if attack in ("laser", "sweep") and any(L.owner == e.id for L in self.lasers):
            attack = "orb"
        elif attack in ("cross", "curtain") and any(L.owner is None for L in self.lasers):
            attack = "orb"
        elif attack == "spiral" and e.spiral is not None:
            attack = "orb"
        elif attack == "wall" and any(s.wall for s in self.shots):
            attack = "orb"
        elif attack == "bomb" and len(self.bombs) > 5:
            attack = "orb"
        elif attack == "dash" and (e.wind > 0 or e.dash > 0):
            attack = "orb"
        zx, zy, _ = rng.choice(list(zones))
        tgt = (zx, zy)
        d = normalize((tgt[0] - e.x, tgt[1] - e.y))

        if attack == "orb":
            self._shoot(e, d, (0.0,), base, dmg, r)
        elif attack == "spread":
            self._shoot(e, d, (-28, -14, 0, 14, 28) if boss else (-18, 0, 18), base * 0.9, dmg, r)
        elif attack == "burst":
            self._shoot(e, d, (0.0,), base * 1.1, dmg, r)
            e.queue.extend([[0.23, "orb"], [0.47, "orb"], [0.70, "orb"]])
        elif attack == "ring":
            n = 16 if boss else 10
            off = rng.uniform(0, 360.0 / n)
            self._shoot(e, (1.0, 0.0), [off + k * 360.0 / n for k in range(n)], base * 0.65,
                        RING_DAMAGE * dmg_mult * (1.4 if boss else 1.0), max(9.0, r - 3))
        elif attack == "homing":
            self._shoot(e, d, (-25.0, 25.0) if boss else (0.0,), base * 0.55,
                        HOMING_DAMAGE * dmg_mult, r + 2, home=True, life=10.0)
        elif attack == "spiral":
            e.spiral = {"left": 2.4 if boss else 1.6, "acc": 0.0, "ang": math.atan2(d[1], d[0]),
                        "dir": rng.choice((-1, 1)), "arms": 2 if boss else 1, "spd": base * 0.7,
                        "dmg": dmg * 0.8, "r": max(9.0, r - 3)}
        elif attack == "wall":                              # a wall of orbs with one gap to slip through
            self._make_wall(tgt, kind_info(e.kind).accent, base * 0.5, dmg_mult)
        elif attack == "laser":
            for off in ((-20.0, 0.0, 20.0) if e.enraged else (-12.0, 12.0)) if boss else (0.0,):
                self.lasers.append(Laser(e.id, tgt=tgt, off=off, warn=LASER_WARN, fire=LASER_FIRE))
        elif attack == "sweep":
            if boss:
                pairs = ((-45.0, 75.0), (45.0, -75.0))
            else:
                off = rng.choice((-45.0, 45.0))
                pairs = ((off, -off / 0.6),)
            for off, spin in pairs:
                self.lasers.append(Laser(e.id, tgt=tgt, off=off, spin=spin, width=1.2, warn=1.3, fire=1.2))
        elif attack == "cross":                             # vertical + horizontal beam through your hand NOW
            pts = [tgt]
            if boss:
                pts.append((rng.uniform(0.1 * w, 0.9 * w), rng.uniform(0.1 * h, 0.9 * h)))
            for q in pts:
                self._beam((q[0], -40.0), (0.0, 1.0))
                self._beam((-40.0, q[1]), (1.0, 0.0))
        elif attack == "curtain":                           # parallel beams across the screen: hide in a gap
            vertical = rng.random() < 0.6
            spacing = 320.0 if vertical else 300.0
            pos = (tgt[0] if vertical else tgt[1]) % spacing
            limit = w if vertical else h
            while pos < limit:
                self._beam((pos, -40.0) if vertical else (-40.0, pos),
                           (0.0, 1.0) if vertical else (1.0, 0.0), warn=2.0, fire=0.6)
                pos += spacing
        elif attack == "bomb":
            for k in range(5 if boss else 3):
                if k == 0:
                    bx, by = tgt
                else:
                    a = rng.uniform(0, 2 * math.pi)
                    dist = rng.uniform(150, 300)
                    bx, by = tgt[0] + math.cos(a) * dist, tgt[1] + math.sin(a) * dist
                self.bombs.append(Bomb(min(max(bx, 40.0), w - 40.0), min(max(by, 40.0), h - 40.0),
                                       -k * 0.27, BOMB_FUSE, 125.0 if boss else 105.0))
        elif attack == "blink":                             # teleport next to the player, then fire a fan
            ox, oy = e.x, e.y
            a = rng.uniform(0, 2 * math.pi)
            dist = rng.uniform(280, 450)
            e.x = min(max(tgt[0] + math.cos(a) * dist, 60.0), w - 60.0)
            e.y = min(max(tgt[1] + math.sin(a) * dist, 60.0), h * 0.7)
            e.kx = e.ky = 0.0
            e.blink = 0.45
            self.note("blink", x0=ox, y0=oy, x1=e.x, y1=e.y, kind=e.kind)
            e.queue.append([0.6, "spread"])
        elif attack == "dash":                              # wind up, then slam into the hand
            e.cdir, e.wind = d, DASH_WINDUP
        elif attack == "summon":                            # boss calls minions
            info = kind_info(e.kind)
            minions = info.minions or ("shooter",)
            for _ in range(2):
                if sum(1 for x in enemies if not x.boss) + len(self.spawn_requests) < 4:
                    self.spawn_requests.append((rng.choice(minions), e.x + rng.uniform(-90, 90),
                                                e.y + rng.uniform(60, 120)))
            self.note("summon", x=e.x, y=e.y, kind=e.kind)
        self.note("attack", attack=attack, x=e.x, y=e.y, kind=e.kind, id=e.id)

    def _make_wall(self, tgt: Vec, tint: RGB, spd: float, dmg_mult: float) -> None:
        w, h = self.size
        rng = self.rng
        side = rng.choice(("top", "bottom", "left", "right"))
        horiz = side in ("left", "right")
        length = h if horiz else w
        n = int(length / 64) + 2
        gap_c = (tgt[1] if horiz else tgt[0]) + rng.uniform(-120, 120)
        for k in range(n):
            pos = k * length / (n - 1)
            if abs(pos - gap_c) < 150:                      # the gap (300 px wide)
                continue
            x, y, vx, vy = {
                "top": (pos, -20.0, 0.0, spd), "bottom": (pos, h + 20.0, 0.0, -spd),
                "left": (-20.0, pos, spd, 0.0), "right": (w + 20.0, pos, -spd, 0.0),
            }[side]
            self.shots.append(Shot(x, y, vx, vy, spd, 12.0, RING_DAMAGE * dmg_mult, 14.0,
                                   wall=True, tint=tint, ph=rng.uniform(0, 6.28)))

    def hazard(self, kind: str, zones: Sequence[Zone], dmg_mult: float = 1.0) -> str:
        """A stage hazard: not tied to any enemy, always telegraphed. Returns the pattern that was used."""
        w, h = self.size
        rng = self.rng
        if kind == "eclipse":
            kind = rng.choice(("rockfall", "tide", "storm", "forge"))
        if (kind == "storm" and any(L.owner is None for L in self.lasers)) or \
                (kind == "tide" and any(s.wall for s in self.shots)) or \
                (kind in ("rockfall", "forge") and len(self.bombs) > 5):
            kind = "rockfall" if len(self.bombs) <= 5 else "tide"
        zx, zy, _ = rng.choice(list(zones))
        if kind == "rockfall":
            for k in range(3):
                bx, by = (zx, zy) if k == 0 else (rng.uniform(0.1 * w, 0.9 * w), rng.uniform(0.25 * h, 0.85 * h))
                self.bombs.append(Bomb(min(max(bx, 40.0), w - 40.0), min(max(by, 40.0), h - 40.0), -k * 0.25, 1.3, 95.0))
        elif kind == "forge":
            for k in range(5):
                a = rng.uniform(0, 2 * math.pi)
                dist = 0.0 if k == 0 else rng.uniform(90, 260)
                bx, by = zx + math.cos(a) * dist, zy + math.sin(a) * dist
                self.bombs.append(Bomb(min(max(bx, 40.0), w - 40.0), min(max(by, 40.0), h - 40.0), -k * 0.15, 1.4, 90.0))
        elif kind == "tide":
            self._make_wall((zx, zy), (110, 200, 255), 150.0, dmg_mult)
        else:                                               # storm: beams through the arena
            for x in (zx, zx + rng.choice((-1, 1)) * rng.uniform(220, 380)):
                self._beam((min(max(x, 40.0), w - 40.0), -40.0), (0.0, 1.0), warn=1.6)
            self._beam((-40.0, min(max(zy + rng.uniform(-120, 120), 60.0), h - 60.0)), (1.0, 0.0), warn=1.6)
        self.note("hazard_pattern", kind=kind)         # the session announces it (with the stage's own label)
        return kind

    # -- hostile objects -------------------------------------------------------
    def _update_shots(self, dt: float, zones: Sequence[Zone], hits: list[Hit]) -> None:
        w, h = self.size
        keep: list[Shot] = []
        for s in self.shots:
            if s.home and zones:                            # homing orbs curve toward the nearest hand
                zx, zy, _ = min(zones, key=lambda z: math.hypot(z[0] - s.x, z[1] - s.y))
                want = normalize((zx - s.x, zy - s.y))
                cur = normalize((s.vx, s.vy))
                blend = 1.0 - 0.94 ** (dt * 30.0) * 1.0
                nd = normalize((cur[0] * (1 - blend) + want[0] * blend, cur[1] * (1 - blend) + want[1] * blend))
                s.vx, s.vy = nd[0] * s.spd, nd[1] * s.spd
            s.x += s.vx * dt
            s.y += s.vy * dt
            s.life -= dt
            s.ph += 12.0 * dt
            if s.life <= 0 or not (-60 < s.x < w + 60 and -60 < s.y < h + 60):
                continue
            struck = False
            for zx, zy, zr in zones:
                if math.hypot(zx - s.x, zy - s.y) < zr + s.r:
                    hits.append(Hit(s.dmg, s.x, s.y, "homing" if s.home else "orb"))
                    self.note("shot_hit", x=s.x, y=s.y, tint=s.tint)
                    struck = True
                    break
            if not struck:
                keep.append(s)
        self.shots = keep

    def _laser_geometry(self, L: Laser, enemies_by_id: dict[int, Enemy]) -> bool:
        if L.owner is not None:
            e = enemies_by_id.get(L.owner)
            if e is None:
                return False
            L.ox, L.oy = e.x, e.y
            d = normalize((L.tgt[0] - e.x, L.tgt[1] - e.y))
            d = rotate(d, L.off + L.spin * max(0.0, L.t - L.warn))
            L.dx, L.dy = d
        else:
            assert L.fixed_origin is not None and L.fixed_dir is not None
            L.ox, L.oy = L.fixed_origin
            L.dx, L.dy = L.fixed_dir
        return True

    def _update_lasers(self, dt: float, enemies: list[Enemy], alive: set[int], zones: Sequence[Zone],
                       hits: list[Hit], dmg_mult: float) -> None:
        by_id = {e.id: e for e in enemies}
        keep: list[Laser] = []
        for L in self.lasers:
            if L.owner is not None and L.owner not in alive:
                continue
            was_firing = L.firing
            L.t += dt
            if L.owner is not None and L.t < L.warn - 0.5 and zones:      # tracks until the last half second
                L.tgt = min(((z[0], z[1]) for z in zones), key=lambda q: math.hypot(q[0] - L.tgt[0], q[1] - L.tgt[1]))
            if not self._laser_geometry(L, by_id):
                continue
            if L.t >= L.warn + L.fire:
                continue
            if L.firing and not was_firing:
                self.note("laser_fire", x=L.ox, y=L.oy)
            if L.firing:
                a = (L.ox, L.oy)
                b = (L.ox + L.dx * 2200.0, L.oy + L.dy * 2200.0)
                for zx, zy, zr in zones:
                    if seg_dist(zx, zy, a, b) < zr * 0.8 + 10 * L.width:
                        hits.append(Hit(LASER_DAMAGE * dmg_mult, zx, zy, "laser"))
            keep.append(L)
        self.lasers = keep

    def _update_bombs(self, dt: float, zones: Sequence[Zone], hits: list[Hit], dmg_mult: float) -> None:
        keep: list[Bomb] = []
        for b in self.bombs:
            b.t += dt
            if b.t < 0:
                keep.append(b)
                continue
            if b.t >= b.fuse and not b.blown:
                b.blown = True
                for zx, zy, zr in zones:
                    if math.hypot(zx - b.x, zy - b.y) < b.r + zr * 0.4:
                        hits.append(Hit(BOMB_DAMAGE * dmg_mult, zx, zy, "bomb"))
                self.note("bomb_blast", x=b.x, y=b.y, r=b.r)
            if b.t < b.fuse + BOMB_BLAST:
                keep.append(b)
        self.bombs = keep

    def _contact(self, enemies: list[Enemy], zones: Sequence[Zone], hits: list[Hit], dmg_mult: float) -> None:
        for e in enemies:
            for zx, zy, zr in zones:
                dx, dy = e.x - zx, e.y - zy
                dist = math.hypot(dx, dy)
                if dist < e.r + zr * 0.8:
                    if e.dash > 0:
                        amount, src = DASH_DAMAGE, "charge"
                    elif e.boss:
                        amount, src = BOSS_CONTACT_DAMAGE, "touch"
                    else:
                        amount, src = CONTACT_DAMAGE, "touch"
                    hits.append(Hit(amount * dmg_mult, zx, zy, src))
                    kb = 0.12 if e.boss else 1.0
                    e.kx += dx / (dist + 1e-6) * 360.0 * kb * KNOCKBACK_SCALE
                    e.ky += dy / (dist + 1e-6) * 360.0 * kb * KNOCKBACK_SCALE
                    e.dash = 0.0                           # the slam ends on impact
                    break

    # -- player side -----------------------------------------------------------
    def shoot_down(self, a: Vec, b: Vec, radius: float) -> list[Vec]:
        """Player blasts destroy hostile orbs near the line a -> b. Returns where they popped."""
        popped: list[Vec] = []
        keep: list[Shot] = []
        for s in self.shots:
            if seg_dist(s.x, s.y, a, b) < s.r + radius * 0.6:
                popped.append((s.x, s.y))
            else:
                keep.append(s)
        self.shots = keep
        return popped

    def defuse(self, a: Vec, b: Vec, radius: float) -> list[Vec]:
        """Player blasts that cross a bomb's circle defuse it before it explodes."""
        popped: list[Vec] = []
        keep: list[Bomb] = []
        for bomb in self.bombs:
            if bomb.t >= 0 and not bomb.blown and seg_dist(bomb.x, bomb.y, a, b) < bomb.r * 0.5 + radius:
                popped.append((bomb.x, bomb.y))
            else:
                keep.append(bomb)
        self.bombs = keep
        return popped

    def interrupt(self, e: Enemy) -> bool:
        """A hit while an enemy is still charging up (dash wind-up, beam warning, spiral, burst) cancels it."""
        charging_beam = any(L.owner == e.id and L.t < L.warn for L in self.lasers)
        did = e.wind > 0 or e.spiral is not None or bool(e.queue) or charging_beam
        if did:
            e.wind = 0.0
            e.spiral = None
            e.queue.clear()
            self.lasers = [L for L in self.lasers if not (L.owner == e.id and L.t < L.warn)]
            e.atk = max(e.atk, 1.6)                       # it has to start over
        return did
