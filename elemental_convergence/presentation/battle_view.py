"""The battle screen, drawn exactly like the original gesture_powers prototype.

Everything here is OpenCV drawing on a BGR image (same colours, same Hershey fonts, same additive glow,
same particles, projectiles, lightning, shake and HUD layout). The game logic lives in ``session`` and
``combat``; this module only turns snapshots and events into pixels.

Timing: the prototype counted frames at ~30 fps. ``FPS`` converts real seconds into those "frames" so the
animations look identical at any refresh rate.
"""

from __future__ import annotations

import math
import random
from typing import Iterable

import cv2
import numpy as np

from ..combat import kind_info
from . import sprites
from .atmosphere import AtmosphereMixin
from ..combat import hand_zone_radius
from ..models import Element, GestureFrame
from ..session import (
    BOOST_TIME, CAST_COST, LOOT_LIFETIME, REGEN_TIME, SHIELD_TIME, GameEvent, GameEventType, GameSnapshot, SessionState,
)

FPS = 30.0

POWER_NAMES = {"earth": "EARTH BLAST", "water": "WATER BLAST",
               "air": "AIR BLAST", "fire": "FIRE BLAST", "lightning": "LIGHTNING"}
POWER_COLORS = {"earth": (70, 130, 190), "water": (255, 200, 60),
                "air": (255, 255, 230), "fire": (0, 150, 255), "lightning": (255, 170, 90)}  # BGR
ELEMENTS = ("earth", "water", "air", "fire", "lightning")
SPEED = {"fire": 24, "air": 34, "earth": 19, "water": 27}
SIZE = {"fire": 24, "air": 46, "earth": 30, "water": 26}
FLIGHT_BOOST = 2.2     # damage lands instantly in the game, so blasts fly faster than the prototype's
BODY = {
    "shooter": (70, 28, 80), "charger": (30, 70, 170), "sniper": (60, 120, 50),
    "gunner": (110, 110, 120), "bomber": (20, 110, 200), "caster": (140, 70, 40),
    "spinner": (150, 40, 150), "sweeper": (160, 150, 30), "blinker": (190, 170, 170),
}
BOSS_BODY, BOSS_ENRAGED = (55, 15, 110), (40, 10, 140)
CONVERGENCE_FRAMES = 54      # ~1.8 s of "Avatar State" light show
AVATAR_ELEMENTS = ("earth", "water", "air", "fire")
LOOT_COLORS = {"heart": (80, 80, 255), "regen": (90, 220, 90), "shield": (255, 190, 60), "boost": (0, 220, 255)}
REACTION_STYLE = {"SHOCKED": (255, 235, 120), "STEAM": (235, 235, 235), "FIRESTORM": (0, 140, 255), "DOUSED": (255, 200, 60)}
LOOT_LABELS = {"heart": "HEART", "regen": "REGEN", "shield": "SHIELD", "boost": "BOOST"}


# ------------------------------------------------------------------------------
# helpers ported from the prototype
# ------------------------------------------------------------------------------
def shade_col(c, k):
    return tuple(int(max(0, min(255, v * k))) for v in c)


def heart_points(cx, cy, size):
    t = np.linspace(0, 2 * math.pi, 40)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    return np.stack([cx + x * size / 16, cy - y * size / 16], 1).astype(np.int32)


def bolt(rng: random.Random, p1, p2, offset, depth=6):
    """Midpoint-displacement jagged line between p1 and p2."""
    pts = [np.array(p1, float), np.array(p2, float)]
    for _ in range(depth):
        new = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            mid = (a + b) / 2
            d = b - a
            n = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-6)
            new += [mid + n * rng.uniform(-offset, offset), b]
        pts = new
        offset /= 2
    return [(int(p[0]), int(p[1])) for p in pts]


def add_glow(img, layer, sigma, crisp=False, div=4):
    """Additive glow, blurred at 1/4 resolution (1/8 on the fast path) so it stays fast."""
    h, w = img.shape[:2]
    small = cv2.resize(layer, (max(1, w // div), max(1, h // div)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), max(0.5, sigma / div))
    img = cv2.add(img, cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR))
    return cv2.add(img, layer) if crisp else img


def seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0 if length == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def rot(d, deg):
    a = math.radians(deg)
    c, s_ = math.cos(a), math.sin(a)
    return np.array([d[0] * c - d[1] * s_, d[0] * s_ + d[1] * c])


def cover_resize(image: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Fill `size` with `image` keeping its aspect ratio; the overflow is cropped (never stretched)."""
    w, h = size
    ih, iw = image.shape[:2]
    scale = max(w / iw, h / ih)
    nw, nh = max(w, int(round(iw * scale))), max(h, int(round(ih * scale)))
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x, y = (nw - w) // 2, (nh - h) // 2
    return np.ascontiguousarray(resized[y:y + h, x:x + w])


def backdrop(size: tuple[int, int]) -> np.ndarray:
    """Plain arena used when no camera frame is available."""
    w, h = size
    column = np.linspace((46, 28, 12), (82, 58, 34), h).astype(np.uint8)
    return np.ascontiguousarray(np.repeat(column[:, None, :], w, axis=1))


class BattleView(AtmosphereMixin):
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)
        self.reduced_flash = False
        self.reduced_shake = False
        self.fast = False                  # cheaper glow and fewer particles on slow machines
        self.sprites = sprites.SpriteBook()
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        self.t = 0.0                       # frames (30 per second)
        self.sparks: list[dict] = []
        self.fire_particles: list[dict] = []
        self.flyers: list[dict] = []       # player blasts in flight
        self.bolts: list[dict] = []        # lightning currently on screen
        self.rings: list[dict] = []        # convergence shockwaves
        self.enemy_flash: dict[int, float] = {}
        self.banner_text, self.banner_t, self.banner_col = "", 0.0, (60, 60, 255)
        self.shake = 0.0
        self.hurt = 0.0                    # frames of red hurt flash
        self.nova = 0.0                    # frames left of the convergence light show
        self.nova_center = (0.0, 0.0)
        self.nova_dir = (0.0, -1.0)
        self.nova_targets: list[tuple[float, float]] = []
        self.nomana = {el: 0.0 for el in ELEMENTS}
        self.floaters: list[dict] = []
        self._float_cd = 0.0
        self.caption_text, self.caption_t = "", 0.0
        self.show_hands = True
        self.last_color = POWER_COLORS["fire"]
        self._advanced = False
        self._flat: dict = {}
        self._atmo_reset()

    def _add(self, img, bgr):
        """Saturating add of a constant colour. A cached flat image is ~10x faster than cv2.add(img, scalar)."""
        key = (img.shape, bgr)
        flat = self._flat.get(key)
        if flat is None:
            if len(self._flat) > 16:
                self._flat.clear()
            flat = np.full(img.shape, bgr[:3], np.uint8)
            self._flat[key] = flat
        return cv2.add(img, flat)

    def banner(self, text: str, frames: float, col=(60, 60, 255)) -> None:
        self.banner_text, self.banner_t, self.banner_col = text, frames, col

    def burst(self, x, y, col, n=20, speed=10, life=(15, 30), size=(3, 8), gravity=0.0) -> None:
        rng = self.rng
        for _ in range(n):
            a, sp, l = rng.uniform(0, 2 * math.pi), rng.uniform(speed * 0.3, speed), rng.randint(*life)
            self.sparks.append({"x": x, "y": y, "vx": math.cos(a) * sp, "vy": math.sin(a) * sp, "life": l,
                                "max": l, "r": rng.randint(*size), "col": col, "g": gravity})
        del self.sparks[:-(600 if self.fast else 1400)]

    def caption(self, text: str, frames: float = 150.0) -> None:
        """Story line shown under the banner (wave names, guardian dialogue)."""
        self.caption_text, self.caption_t = text, frames

    def floater(self, x, y, text, col=(255, 255, 255), throttle=False) -> None:
        """Short text that rises and fades (BLOCKED, +25 HP ...)."""
        if throttle:
            if self._float_cd > 0:
                return
            self._float_cd = 8.0
        self.floaters.append({"x": float(x), "y": float(y), "text": text, "col": col, "life": 36.0, "max": 36.0})
        del self.floaters[:-14]

    def kick(self, amount: float) -> None:
        if not self.reduced_shake:
            self.shake = max(self.shake, amount)

    # ----------------------------------------------------------------- events
    def _on_event(self, ev: GameEvent, snap: GameSnapshot) -> None:
        kind, data = ev.type, dict(ev.data or {})
        if kind is GameEventType.CAST:
            self._cast(data)
        elif kind is GameEventType.ENEMY_DEFEATED:
            x, y, col = data.get("x", 0), data.get("y", 0), self.last_color
            if data.get("ultimate") or self.nova > CONVERGENCE_FRAMES - 4:
                self.nova_targets.append((x, y))
            if data.get("elite"):
                self.floater(x, y - 40, "ELITE DOWN", (0, 215, 255))
            if data.get("boss"):
                self.banner("BOSS DEFEATED!", 130, (80, 230, 255))
                if data.get("line"):
                    self.caption(data["line"], 200)
                self.kick(1.0)
                self.burst(x, y, col, 160, 24, life=(25, 50), size=(5, 14))
                self.burst(x, y, (255, 255, 255), 80, 18, life=(20, 40))
                self.burst(x, y, (0, 160, 255), 80, 14, life=(25, 45), size=(6, 12))
            else:
                self.burst(x, y, col, 60, 16, size=(4, 10))
                self.burst(x, y, (255, 255, 255), 25, 12)
            self._spirit(x, y, ev.detail, bool(data.get("boss")))
        elif kind is GameEventType.PLAYER_HIT:
            if not self.reduced_flash:
                self.hurt = 10.0
            self.kick(0.6)
        elif kind is GameEventType.LIFE_LOST:
            self.banner("LIFE LOST!", 90)
        elif kind is GameEventType.WAVE_STARTED:
            if ev.detail == "boss":
                self.banner("BOSS INCOMING!", 110)
                if data.get("line"):
                    self.caption(data["line"], 210)
            else:
                self.banner(f"WAVE {ev.detail}", 70, (80, 230, 255))
                if data.get("title"):
                    self.caption(data["title"], 120)
        elif kind is GameEventType.WAVE_COMPLETE:
            self.banner("WAVE CLEARED!", 60, (80, 230, 255))
        elif kind is GameEventType.LEVEL_COMPLETE:
            self.banner("SEAL RESTORED!", 130, (80, 230, 255))
        elif kind is GameEventType.CONVERGENCE_READY:
            self.banner("KALAMPAG READY!", 60, (255, 200, 90))
        elif kind is GameEventType.CONVERGENCE_STARTED:
            self.nova = float(CONVERGENCE_FRAMES)
            self.nova_center = (data.get("x", 0.0), data.get("y", 0.0))
            self.nova_targets = []
            self.rings = [{"x": int(self.nova_center[0]), "y": int(self.nova_center[1]), "r": 30.0}]
            self.kick(1.0)
            self.banner("KALAMPAG!", 100, (80, 230, 255))
            kinds = AVATAR_ELEMENTS                      # 360-degree elemental nova
            for k in range(16):
                ang = k * 2 * math.pi / 16
                self._launch(kinds[k % 4], self.nova_center, (math.cos(ang), math.sin(ang)), None, 900.0, 2.4)
        elif kind is GameEventType.LOOT_COLLECTED:
            col = self._loot_color(ev.detail)
            x, y = data.get("x", 0), data.get("y", 0)
            self.burst(x, y, col, 34, 12, life=(12, 26), size=(3, 8))
            self.burst(x, y, (255, 255, 255), 12, 9)
            self.floater(x, y - 30, data.get("label", ""), col)
        elif kind is GameEventType.COMBAT_FX:
            self._note(ev.detail, data)

    def _note(self, name: str, d: dict) -> None:
        if name == "attack":
            self.burst(d["x"], d["y"], (60, 60, 255), 10, 8, life=(8, 14), size=(3, 6))
        elif name == "shot_hit":
            self.burst(d["x"], d["y"], (60, 60, 255), 25, 11, size=(3, 8))
        elif name == "bomb_blast":
            self.burst(d["x"], d["y"], (0, 170, 255), 50, 15, size=(4, 10))
            self.burst(d["x"], d["y"], (255, 255, 255), 20, 10)
            self.kick(0.6)
        elif name == "laser_fire":
            self.kick(0.5)
        elif name == "hazard":
            self.banner(d.get("label", "HAZARD!"), 55, (0, 170, 255))
        elif name == "boss_phase":
            self.banner(f"PHASE {d['phase']}", 70, (60, 60, 255))
            self.burst(d["x"], d["y"], (60, 60, 255), 60, 16, life=(15, 30), size=(4, 10))
            self.kick(0.9)
            if d.get("line"):
                self.caption(d["line"], 190)
        elif name == "shield_block":
            self.burst(d["x"], d["y"], (255, 200, 80), 22, 10, size=(3, 7))
            self.floater(d["x"], d["y"] - 40, "BLOCKED", (255, 200, 80), throttle=True)
        elif name == "blink":
            self.burst(d["x0"], d["y0"], (255, 210, 210), 25, 10)
            self.burst(d["x1"], d["y1"], (255, 210, 210), 25, 10)
        elif name == "summon":
            self.burst(d["x"], d["y"], (200, 60, 120), 30, 12)

    def _cast(self, d: dict) -> None:
        el = d["element"]
        self.last_color = POWER_COLORS.get(el, self.last_color)
        ox, oy = d["origin"]
        for i, (px, py) in enumerate(d.get("popped", [])):    # your blast shot an enemy orb down
            self.burst(px, py, (80, 80, 255), 18, 9, life=(8, 18), size=(2, 6))
            self.burst(px, py, (255, 255, 255), 6, 7, life=(6, 12), size=(2, 4))
            if i == 0:
                self.floater(px, py - 24, "BLOCKED", (255, 255, 255), throttle=True)
        for px, py in d.get("defused", []):                 # ...or defused a bomb before it blew
            self.burst(px, py, (0, 170, 255), 26, 9, life=(10, 22), size=(3, 8))
            self.floater(px, py - 20, "DEFUSED", (0, 220, 255), throttle=True)
        for px, py in d.get("interrupted", []):             # ...or broke up an attack that was charging
            self.burst(px, py, (255, 255, 255), 22, 12, life=(8, 18), size=(2, 6))
            self.floater(px, py - 60, "INTERRUPTED", (255, 255, 255), throttle=True)
        target = d.get("target")
        if target and d.get("effect"):                       # weak / resisted hit
            weak = d["effect"] == "weak"
            self.floater(target[0], target[1] - d.get("radius", 40) - 26, "WEAK!" if weak else "RESIST",
                         POWER_COLORS.get(el, (255, 255, 255)) if weak else (150, 150, 150), throttle=True)
        for r in d.get("reactions", []):
            style = REACTION_STYLE.get(r["name"], (255, 255, 255))
            self.burst(r["x"], r["y"], style, 40, 14, life=(10, 26), size=(3, 9))
            self.floater(r["x"], r["y"] - 70, r["name"] + "!", style)
            if r["name"] in ("STEAM", "FIRESTORM"):
                self.burst(r["x"], r["y"], (255, 255, 255), 24, 10, life=(14, 30), size=(5, 12))
            self.kick(0.35)
        if el == "lightning":
            legs = [((ox, oy), tuple(d["end"]))]
            prev = tuple(d["end"])
            for c in d.get("chain", []):
                legs.append((prev, tuple(c)))
                prev = tuple(c)
            self.bolts.append({"legs": legs, "ttl": 5.0})
            del self.bolts[:-8]
            for hx, hy in ([target] if target else []) + list(d.get("chain", [])):
                self.burst(hx, hy, (255, 235, 190), 3, 8, life=(6, 12), size=(2, 4))
            if target and d.get("target_id") is not None:
                self.enemy_flash[d["target_id"]] = 3.0
            return
        end = tuple(d["end"])
        direction = d.get("dir", (0.0, -1.0))
        dist = math.hypot(end[0] - ox, end[1] - oy)
        self._launch(el, (ox, oy), direction, end if target else None, dist, 1.0, target_id=d.get("target_id"))

    def _launch(self, kind, origin, d, end, dist, pw=1.0, target_id=None) -> None:
        d = np.asarray(d, float)
        d = d / (np.linalg.norm(d) + 1e-6)
        if end is None and dist is None:
            dist = 900.0
        self.flyers.append({"kind": kind, "x": float(origin[0]), "y": float(origin[1]), "d": d,
                            "speed": SPEED[kind] * FLIGHT_BOOST, "travel": 0.0, "dist": max(1.0, float(dist)),
                            "size": int(SIZE[kind] * (1 + (pw - 1) * 0.8)), "pow": pw, "hit": end is not None,
                            "end": end, "id": target_id, "rot": self.rng.uniform(0, 6.28)})
        self.burst(origin[0], origin[1], POWER_COLORS[kind], 8, 7, life=(8, 14))     # muzzle flash
        del self.flyers[:-80]

    # ----------------------------------------------------------------- update
    def update(self, dt: float, snap: GameSnapshot, events: Iterable[GameEvent] = (),
               frame: GestureFrame | None = None) -> None:
        """Advance every animation by dt seconds (call once per game frame; skip while paused)."""
        f = dt * FPS
        self.t += f
        self._advanced = True
        for ev in events:
            self._on_event(ev, snap)
        for k in list(self.enemy_flash):
            self.enemy_flash[k] -= f
            if self.enemy_flash[k] <= 0:
                del self.enemy_flash[k]
        self.banner_t = max(0.0, self.banner_t - f)
        self.caption_t = max(0.0, self.caption_t - f)
        self._float_cd = max(0.0, self._float_cd - f)
        for fl in self.floaters[:]:
            fl["y"] -= 1.6 * f
            fl["life"] -= f
            if fl["life"] <= 0:
                self.floaters.remove(fl)
        for e in snap.enemies:                                 # status effects shed particles
            if "burning" in e.status and self.rng.random() < 0.7 * f:
                self.sparks.append({"x": e.position[0] + self.rng.uniform(-e.radius, e.radius) * 0.7,
                                    "y": e.position[1] - e.radius * 0.3, "vx": self.rng.uniform(-0.6, 0.6), "vy": -2.6,
                                    "life": 16, "max": 16, "r": self.rng.randint(3, 6), "col": (0, 140, 255), "g": 0.0})
            if "soaked" in e.status and self.rng.random() < 0.4 * f:
                self.sparks.append({"x": e.position[0] + self.rng.uniform(-e.radius, e.radius) * 0.8,
                                    "y": e.position[1] + e.radius * 0.2, "vx": 0.0, "vy": 0.8,
                                    "life": 14, "max": 14, "r": 3, "col": (255, 200, 60), "g": 0.35})
        if frame is not None and snap.regen > 0:             # green motes rise off your hands while regenerating
            for hand in frame.hands:
                if self.rng.random() < 0.5 * f:
                    self.sparks.append({"x": hand.center[0] + self.rng.uniform(-hand.size, hand.size),
                                        "y": hand.center[1] + self.rng.uniform(-10, hand.size * 0.6),
                                        "vx": 0.0, "vy": -2.4, "life": 18, "max": 18, "r": self.rng.randint(3, 5),
                                        "col": (90, 220, 90), "g": 0.0})
        self.hurt = max(0.0, self.hurt - f)
        self._watch_hazards(snap)
        self._tick_atmosphere(f)
        self.shake *= 0.8 ** f
        for k in self.nomana:
            self.nomana[k] = max(0.0, self.nomana[k] - f)
        if frame is not None:                                # blink an empty mana bar while you hold its pose
            for hand in frame.hands:
                g = hand.gesture
                if g in snap.unlocked_elements and snap.mana.get(g, 0.0) < CAST_COST[g]:
                    self.nomana[g.value] = 8.0
        for p in self.flyers[:]:                             # blasts in flight
            step = p["speed"] * f
            p["x"] += p["d"][0] * step
            p["y"] += p["d"][1] * step
            p["travel"] += step
            p["rot"] += 0.25 * f
            self._trail(p, f)
            if p["travel"] >= p["dist"]:
                self.flyers.remove(p)
                if p["hit"] and p["end"] is not None:
                    self._impact(p)
        for b in self.bolts[:]:
            b["ttl"] -= f
            if b["ttl"] <= 0:
                self.bolts.remove(b)
        for s in self.sparks[:]:
            s["x"] += s["vx"] * f
            s["y"] += s["vy"] * f
            s["vy"] += s["g"] * f
            s["vx"] *= 0.97 ** f
            s["life"] -= f
            if s["life"] <= 0:
                self.sparks.remove(s)
        for p in self.fire_particles[:]:
            p["x"] += (p["vx"] + self.rng.uniform(-1, 1)) * f
            p["y"] += p["vy"] * f
            p["life"] -= f
            if p["life"] <= 0:
                self.fire_particles.remove(p)
        if self.nova > 0:
            self.nova -= f
            if int(self.nova) == CONVERGENCE_FRAMES - 30:
                self.rings.append({"x": int(self.nova_center[0]), "y": int(self.nova_center[1]), "r": 30.0})
            self.kick(0.4)
        for r in self.rings[:]:
            r["r"] += 36 * f
            if r["r"] > 1900:
                self.rings.remove(r)

    def _trail(self, p: dict, f: float) -> None:
        if self.rng.random() > min(1.0, f):
            return
        rng, x, y, d, kind = self.rng, p["x"], p["y"], p["d"], p["kind"]
        if kind == "fire":
            self.fire_particles.append({"x": x, "y": y, "vx": rng.uniform(-2, 2), "vy": rng.uniform(-2, 2),
                                        "life": rng.randint(10, 18), "max": 35, "r": rng.randint(10, 18)})
        elif kind == "air":
            self.burst(x - d[0] * 20, y - d[1] * 20, (255, 255, 235), 2, 4, life=(6, 10), size=(2, 4))
        elif kind == "water":
            for _ in range(2):
                self.sparks.append({"x": x + rng.uniform(-10, 10), "y": y + rng.uniform(-10, 10),
                                    "vx": rng.uniform(-2, 2), "vy": rng.uniform(-1, 2), "life": 14, "max": 14,
                                    "r": rng.randint(2, 4), "col": (255, 225, 150), "g": 0.6})
        else:
            self.burst(x, y, (70, 110, 150), 2, 3, life=(8, 14), size=(3, 6))

    def _impact(self, p: dict) -> None:
        x, y = p["end"]
        kind = p["kind"]
        if p["id"] is not None:
            self.enemy_flash[p["id"]] = 3.0
        rng = self.rng
        self.pops.append({"x": x, "y": y, "r": 8.0, "life": 10.0, "col": POWER_COLORS[kind]})
        if kind == "fire":
            self.burst(x, y, (0, 170, 255), 40, 14)
            for _ in range(12):
                a = rng.uniform(0, 6.28)
                self.fire_particles.append({"x": x, "y": y, "vx": math.cos(a) * 8, "vy": math.sin(a) * 8,
                                            "life": rng.randint(15, 30), "max": 35, "r": rng.randint(14, 26)})
        elif kind == "air":
            self.burst(x, y, (255, 255, 235), 14, 9)
        elif kind == "water":
            self.burst(x, y, (255, 215, 130), 45, 13, size=(3, 7), gravity=0.5)
            self.burst(x, y, (255, 255, 235), 15, 9, size=(2, 4), gravity=0.5)
        else:
            self.burst(x, y, (70, 120, 170), 35, 12, size=(4, 9), gravity=0.6)
            self.kick(1.0)

    # ------------------------------------------------------------------ draw
    def render(self, snap: GameSnapshot, frame: GestureFrame | None, camera: np.ndarray | None,
               size: tuple[int, int]) -> np.ndarray:
        w, h = size
        img = cover_resize(camera, size) if camera is not None else backdrop(size)
        glow = np.zeros_like(img)
        rng = self.rng
        shaken = self._advanced
        self._advanced = False
        playing = snap.state in (SessionState.ACTIVE, SessionState.BOSS)

        self._ambient(img, glow, snap.level_id)
        self._draw_decals(img, glow)
        if snap.loot:
            self._draw_loot(img, glow, snap)
        if snap.enemies:
            self._draw_enemies(img, glow, snap)
        if snap.bombs:
            self._draw_bombs(img, glow, snap)
        if snap.shots:
            self._draw_shots(img, glow, snap)
        if snap.lasers:
            self._draw_lasers(img, glow, snap)
        if self.nova > 0:
            img = self._draw_convergence(img, glow, snap, frame)
        for b in self.bolts:
            self._draw_lightning(img, glow, b)
        if self.bolts and rng.random() < 0.12 and not self.reduced_flash:        # occasional flash
            img = self._add(img, (60, 50, 40))
        self._draw_fire(glow)
        self._draw_pops(img, glow)
        self._draw_flyers(img, glow)
        self._draw_sparks(img, glow)
        if frame is not None and playing and self.nova <= 0:
            self._draw_charge(glow, snap, frame)
        if frame is not None and playing:
            self._draw_buff_rings(img, glow, snap, frame)
            self._draw_hold(img, glow, snap, frame)
        img = add_glow(img, glow, 10, div=8 if self.fast else 4)
        img = self._apply_mood(img, snap.level_id)
        if self.flash_t > 0 and not self.reduced_flash:
            img = self._add(img, (70, 70, 80))

        if frame is not None and playing and self.nova <= 0:                    # element screen tints
            held = {hand.gesture for hand in frame.hands if hand.gesture in snap.unlocked_elements}
            if Element.WATER in held:
                img = self._add(img, (25, 12, 0))
            if Element.FIRE in held:
                img = self._add(img, (0, 8, 25))
            if Element.AIR in held:
                img = self._add(img, (14, 14, 12))
        if self.hurt > 0:                                                       # got hit: red flash
            img = self._add(img, (0, 0, 70))
        if shaken and self.shake > 0.05:                                        # screen shake
            amp = self.shake * 16
            dx, dy = int(rng.uniform(-amp, amp)), int(rng.uniform(-amp, amp))      # a pure shift: cheaper than a warp
            pad = int(amp) + 2
            framed = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_REFLECT)
            img = np.ascontiguousarray(framed[pad - dy:pad - dy + h, pad - dx:pad - dx + w])

        if frame is not None and playing and self.show_hands:
            self._draw_labels(img, snap, frame)
        self._draw_floaters(img)
        self._draw_hud(img, snap)
        return img

    # -- loot -------------------------------------------------------------------
    @staticmethod
    def _loot_color(kind: str):
        if kind.startswith("mana:"):
            return POWER_COLORS[kind.split(":", 1)[1]]
        return LOOT_COLORS.get(kind, (255, 255, 255))

    def _draw_loot(self, img, glow, snap: GameSnapshot) -> None:
        for l in snap.loot:
            if l.life < 3.0 and int(self.t // 3) % 2 == 0:               # about to vanish: blink
                continue
            col = self._loot_color(l.kind)
            x, y = l.x, l.y + 4 * math.sin(self.t * 0.25 + l.id)
            c = (int(x), int(y))
            r = int(l.r * (1 + 0.06 * math.sin(self.t * 0.4 + l.id)))
            cv2.circle(glow, c, int(r * 1.8), tuple(int(v * 0.45) for v in col), -1)
            cv2.circle(img, c, r + 3, (20, 10, 30), -1)
            cv2.circle(img, c, r, tuple(int(v * 0.4) for v in col), -1)
            cv2.circle(img, c, r, col, 2, cv2.LINE_AA)
            cv2.ellipse(img, c, (r + 8, r + 8), -90, 0, 360 * max(0.0, min(1.0, l.life / LOOT_LIFETIME)),
                        (255, 255, 255), 2, cv2.LINE_AA)                   # time left before it fades
            if l.kind == "heart":
                pts = heart_points(x, y + 2, 28)
                cv2.fillPoly(img, [pts], (80, 80, 255))
                cv2.polylines(img, [pts], True, (255, 255, 255), 1, cv2.LINE_AA)
            elif l.kind == "regen":
                k = int(r * 0.55)
                cv2.line(img, (c[0] - k, c[1]), (c[0] + k, c[1]), (255, 255, 255), 5, cv2.LINE_AA)
                cv2.line(img, (c[0], c[1] - k), (c[0], c[1] + k), (255, 255, 255), 5, cv2.LINE_AA)
            elif l.kind == "shield":
                pts = np.int32([(x - r * 0.55, y - r * 0.6), (x + r * 0.55, y - r * 0.6), (x + r * 0.55, y + r * 0.1),
                                (x, y + r * 0.72), (x - r * 0.55, y + r * 0.1)])
                cv2.fillPoly(img, [pts], (255, 230, 150))
                cv2.polylines(img, [pts], True, (255, 255, 255), 2, cv2.LINE_AA)
            elif l.kind == "boost":
                for dy in (-7, 7):
                    pts = np.int32([(x - r * 0.5, y + r * 0.2 + dy), (x, y - r * 0.35 + dy), (x + r * 0.5, y + r * 0.2 + dy)])
                    cv2.polylines(img, [pts], False, (255, 255, 255), 4, cv2.LINE_AA)
            else:
                letter = l.kind.split(":", 1)[1][0].upper()
                (tw, th), _ = cv2.getTextSize(letter, cv2.FONT_HERSHEY_DUPLEX, 0.9, 2)
                cv2.putText(img, letter, (c[0] - tw // 2, c[1] + th // 2), cv2.FONT_HERSHEY_DUPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
            label = LOOT_LABELS.get(l.kind) or f"{l.kind.split(':', 1)[1].upper()} MANA"
            (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_PLAIN, 1.0, 1)
            cv2.putText(img, label, (c[0] - tw // 2, c[1] + r + 24), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_buff_rings(self, img, glow, snap: GameSnapshot, frame: GestureFrame) -> None:
        for hand in frame.hands:
            c = (int(hand.center[0]), int(hand.center[1]))
            radius = int(hand_zone_radius(hand.size))
            if snap.shield > 0 and not (snap.shield < 2.0 and int(self.t // 3) % 2 == 0):
                cv2.circle(glow, c, radius, (120, 80, 20), 16)
                cv2.circle(img, c, radius, (255, 200, 80), 3, cv2.LINE_AA)
                for k in range(6):
                    a = self.t * 0.12 + k * math.pi / 3
                    p1 = (int(c[0] + math.cos(a) * (radius - 6)), int(c[1] + math.sin(a) * (radius - 6)))
                    p2 = (int(c[0] + math.cos(a) * (radius + 6)), int(c[1] + math.sin(a) * (radius + 6)))
                    cv2.line(img, p1, p2, (255, 230, 150), 2, cv2.LINE_AA)
            if snap.boost > 0:
                cv2.circle(glow, c, radius + 10, (0, 90, 120), 12)
                cv2.circle(img, c, radius + 10, (0, 220, 255), 2, cv2.LINE_AA)

    def _draw_hold(self, img, glow, snap: GameSnapshot, frame: GestureFrame) -> None:
        """A ring fills between your hands while you hold them together, so you can see it charging."""
        if snap.convergence_hold <= 0 or len(frame.hands) < 2:
            return
        a, b = min(((a, b) for i, a in enumerate(frame.hands) for b in frame.hands[i + 1:]),
                   key=lambda p: math.dist(p[0].center, p[1].center))
        c = (int((a.center[0] + b.center[0]) / 2), int((a.center[1] + b.center[1]) / 2))
        r = int(max(a.size, b.size) * 1.1)
        sweep = 360 * snap.convergence_hold
        cv2.ellipse(glow, c, (r, r), -90, 0, sweep, (255, 200, 90), 16)
        cv2.circle(img, c, r, (60, 60, 60), 2, cv2.LINE_AA)
        cv2.ellipse(img, c, (r, r), -90, 0, sweep, (80, 230, 255), 5, cv2.LINE_AA)

    def _draw_floaters(self, img) -> None:
        for fl in self.floaters:
            fade = min(1.0, fl["life"] / 12.0)
            col = tuple(int(v * (0.4 + 0.6 * fade)) for v in fl["col"])
            (tw, _), _ = cv2.getTextSize(fl["text"], cv2.FONT_HERSHEY_DUPLEX, 0.7, 2)
            pos = (int(fl["x"] - tw / 2), int(fl["y"]))
            cv2.putText(img, fl["text"], pos, cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 0, 0), 5, cv2.LINE_AA)
            cv2.putText(img, fl["text"], pos, cv2.FONT_HERSHEY_DUPLEX, 0.7, col, 2, cv2.LINE_AA)

    # -- enemies --------------------------------------------------------------
    def _draw_enemies(self, img, glow, snap: GameSnapshot) -> None:
        for e in snap.enemies:
            aura = sprites.AURA.get(e.kind, (60, 20, 90))
            col = (30, 30, 190) if e.enraged else aura
            cv2.circle(glow, (int(e.position[0]), int(e.position[1])), int(e.radius * (1.6 if e.boss else 1.35)),
                       shade_col(col, 0.32), -1)
        for e in snap.enemies:
            x, y = e.position
            r, boss = e.radius, e.boss
            flash = self.enemy_flash.get(e.id, 0) > 0
            bob = math.sin(self.t * 0.1 + e.id * 0.9) * r * (0.03 if boss else 0.06)
            r_eff = r * (1.0 if boss else 1.3)
            if self.sprites.has(e.kind):
                self._shadow(img, x, y, r_eff, boss)
                angry = e.enraged or (e.warn > 0 and not e.wind and (int(self.t / 4) + e.id) % 2 == 0)   # eyes flare as it winds up
                scol, sal = self.sprites.frame(e.kind, r_eff, self.t * 0.03 * (1.5 if e.enraged else 1.0) + e.id * 0.37,
                                               angry, flash)
                if e.age < 0.35:                                       # pop in
                    scol, sal = sprites.scaled(scol, sal, 0.4 + 0.6 * max(0.0, e.age) / 0.35)
                if e.kind == "blinker":                                # the White Lady flickers
                    scol, sal = sprites.fade(scol, sal, 0.8 + 0.2 * math.sin(self.t * 0.12 + e.id))
                if e.dashing:                                          # afterimages while it rushes
                    for k, a in ((1, 0.35), (2, 0.2), (3, 0.1)):
                        gcol, gal = sprites.fade(scol, sal, a)
                        sprites.blit(img, gcol, gal, x - e.direction[0] * r * 0.55 * k, y + bob - e.direction[1] * r * 0.55 * k)
                sprites.blit(img, scol, sal, x, y + bob)
                if e.age >= 0.35:
                    self._eyes(img, glow, e, x, y + bob, r_eff)
                    self._creature_effects(img, glow, e, x, y + bob, r_eff)
            else:                                                      # unknown kind: plain disc
                cv2.circle(img, (int(x), int(y)), int(r), (255, 255, 255) if flash else (60, 40, 120), -1, cv2.LINE_AA)
            if e.kind == "sweeper":                                    # santelmo's ghost-fire
                cv2.circle(glow, (int(x), int(y - r * 0.1)), int(r * 1.1), (120, 150, 60), -1)
            elif e.kind == "stone_guardian":                           # cigar smoke
                for k in range(4):
                    ph = (self.t * 0.04 + k * 0.25) % 1.0
                    cv2.circle(img, (int(x + r * (1.12 + 0.3 * math.sin(ph * 6 + k))), int(y + r * 0.4 - ph * r * 1.1)),
                               int(r * (0.07 + 0.14 * ph)), (int(150 - 60 * ph),) * 3, -1, cv2.LINE_AA)
            elif e.kind == "ember_guardian":
                cv2.circle(glow, (int(x), int(y - r * 0.9)), int(r * 0.5), (0, 110, 255), -1)
            if "soaked" in e.status:                                   # wet: droplets circle the enemy
                for k in range(4):
                    a = self.t * 0.2 + k * math.pi / 2
                    cv2.circle(img, (int(x + math.cos(a) * r * 1.15), int(y + math.sin(a) * r * 1.15)), 4, (255, 200, 60), -1, cv2.LINE_AA)
            if "stun" in e.status:                                     # stunned: stars wheel overhead
                for k in range(3):
                    a = self.t * 0.35 + k * 2 * math.pi / 3
                    cv2.drawMarker(img, (int(x + math.cos(a) * r * 0.7), int(y - r * 1.15 + math.sin(a) * 8)),
                                   (0, 230, 255), cv2.MARKER_STAR, 14, 2, cv2.LINE_AA)
            if "slow" in e.status:                                     # earth-bound: a heavy ring
                cv2.circle(img, (int(x), int(y)), int(r * 1.25), (70, 130, 190), 3, cv2.LINE_AA)
            if e.elite:                                                # elites wear a gold ring
                cv2.circle(img, (int(x), int(y)), int(r * 1.18), (0, 215, 255), 3, cv2.LINE_AA)
                cv2.circle(glow, (int(x), int(y)), int(r * 1.5), (0, 90, 120), 14)
            if e.wind > 0:                                             # charger telegraph: a red lane toward your hand
                tip = (int(x + e.direction[0] * 1400), int(y + e.direction[1] * 1400))
                cv2.line(img, (int(x), int(y)), tip, (60, 60, 255), 2 + int(28 * e.wind) // 8, cv2.LINE_AA)
            if e.warn > 0 and not e.wind and not e.dashing:
                ring = int(r * (1.9 - 0.7 * (1.0 - e.warn)))           # attack warning ring
                cv2.circle(img, (int(x), int(y)), ring, (60, 60, 255), 2, cv2.LINE_AA)
            if boss:                                                   # big health bar across the top
                big_w = img.shape[1]
                x0, x1, y0 = int(big_w * 0.25), int(big_w * 0.75), 62
                cv2.rectangle(img, (x0 - 3, y0 - 3), (x1 + 3, y0 + 21), (0, 0, 0), -1)
                cv2.rectangle(img, (x0, y0), (x1, y0 + 18), (40, 40, 40), -1)
                frac = max(0, e.hp) / e.max_hp
                cv2.rectangle(img, (x0, y0), (x0 + int((x1 - x0) * frac), y0 + 18),
                              (0, 60, 255) if e.enraged else (40, 40, 230), -1)
                cv2.putText(img, kind_info(e.kind).title, (x0, y0 - 10), cv2.FONT_HERSHEY_DUPLEX, 0.8,
                            (255, 255, 255), 2, cv2.LINE_AA)
                if e.weak:
                    (tw, _), _ = cv2.getTextSize(kind_info(e.kind).title, cv2.FONT_HERSHEY_DUPLEX, 0.8, 2)
                    cv2.circle(img, (x0 + tw + 18, y0 - 18), 8, POWER_COLORS[e.weak], -1, cv2.LINE_AA)
                    cv2.circle(img, (x0 + tw + 18, y0 - 18), 8, (255, 255, 255), 2, cv2.LINE_AA)
            else:
                bw = int(r * 1.6)                                      # small health bar
                x0, y0 = int(x - bw / 2), int(y - r * 1.35 - 18)
                cv2.rectangle(img, (x0, y0), (x0 + bw, y0 + 7), (30, 30, 30), -1)
                cv2.rectangle(img, (x0, y0), (x0 + int(bw * max(0, e.hp) / e.max_hp), y0 + 7), (60, 220, 60), -1)
                label = ("ELITE " if e.elite else "") + sprites.FOLK_NAMES.get(e.kind, e.kind.upper())
                cv2.putText(img, label, (x0, y0 - 4), cv2.FONT_HERSHEY_PLAIN, 0.9,
                            (0, 215, 255) if e.elite else (255, 255, 255), 1, cv2.LINE_AA)
                if e.weak:                                             # a coloured pip shows which element it fears
                    (lw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_PLAIN, 0.9, 1)
                    cv2.circle(img, (x0 + lw + 9, y0 - 9), 5, POWER_COLORS[e.weak], -1, cv2.LINE_AA)
                    cv2.circle(img, (x0 + lw + 9, y0 - 9), 5, (255, 255, 255), 1, cv2.LINE_AA)

    def _draw_shots(self, img, glow, snap: GameSnapshot) -> None:
        walls = [s for s in snap.shots if s.wall]
        if walls:
            self._draw_walls(img, glow, walls)
        for s in snap.shots:
            if s.wall:
                continue
            c = (int(s.x), int(s.y))
            r = max(4, int(s.r * (1 + 0.12 * math.sin(s.phase))))
            if s.home:                                                 # homing = orange, so you can tell them apart
                cols = ((0, 90, 255), (0, 40, 160), (0, 150, 255), (200, 240, 255))
            else:
                cols = ((40, 20, 200), (60, 20, 150), (80, 80, 255), (220, 230, 255))
            cv2.circle(glow, c, int(r * 2.2), cols[0], -1)
            cv2.circle(img, c, r, cols[1], -1)
            cv2.circle(img, c, int(r * 0.65), cols[2], -1)
            cv2.circle(img, c, max(2, int(r * 0.3)), cols[3], -1)

    def _draw_walls(self, img, glow, walls) -> None:
        """Walls of fire from gunners / the Typhoon, or the river's water wall. The gap is marked clearly."""
        h, w = img.shape[:2]
        groups: dict[tuple, list] = {}
        for s in walls:
            vert = abs(s.vy) >= abs(s.vx)
            sign = (s.vy if vert else s.vx) >= 0
            groups.setdefault((vert, sign, s.style), []).append(s)
        for (vert, sign, style), grp in groups.items():
            ax = (lambda s: s.x) if vert else (lambda s: s.y)          # position along the wall
            grp.sort(key=ax)
            tide = style == "tide"
            d = (0, 1 if sign else -1) if vert else (1 if sign else -1, 0)
            for a, b in zip(grp, grp[1:]):                             # water forms a continuous band
                if tide and ax(b) - ax(a) < 90:
                    cv2.line(img, (int(a.x), int(a.y)), (int(b.x), int(b.y)), (200, 120, 30), 20, cv2.LINE_AA)
                    cv2.line(glow, (int(a.x), int(a.y)), (int(b.x), int(b.y)), (120, 70, 10), 30)
            for s in grp:
                c = (int(s.x), int(s.y))
                if tide:
                    cv2.circle(img, c, 14, (235, 160, 50), -1, cv2.LINE_AA)
                    cv2.circle(img, c, 8, (255, 215, 130), -1, cv2.LINE_AA)
                    lead = (int(s.x + d[0] * 9), int(s.y + d[1] * 9))
                    cv2.circle(img, lead, 6, (255, 255, 255), -1, cv2.LINE_AA)           # foam on the leading edge
                    for _ in range(2):                                                    # and spray flung off the crest
                        cv2.circle(img, (int(s.x + self.rng.uniform(-14, 14) + d[0] * 14), int(s.y + self.rng.uniform(-14, 14) + d[1] * 14)),
                                   self.rng.randint(1, 3), (255, 245, 225), -1)
                else:
                    tail = (int(s.x - d[0] * 22), int(s.y - d[1] * 22))
                    cv2.line(glow, tail, c, shade_col(s.tint, 0.5), 26)
                    cv2.line(img, tail, c, shade_col(s.tint, 0.55), 15, cv2.LINE_AA)       # a streaking slug
                    cv2.circle(img, c, 9, s.tint, -1, cv2.LINE_AA)
                    cv2.circle(img, c, 4, (255, 255, 255), -1, cv2.LINE_AA)
            length = w if vert else h
            pos = [0.0] + [float(ax(s)) for s in grp] + [float(length)]
            if len(grp) < 4:
                continue
            gi = max(range(len(pos) - 1), key=lambda i: pos[i + 1] - pos[i])
            lo, hi = pos[gi], pos[gi + 1]
            if hi - lo < 130:
                continue
            lead = grp[0]
            wx, wy = lead.x, lead.y
            for k in range(3):                                         # green chevrons through the gap
                off = 70 + k * 70
                px = (lo + hi) / 2 if vert else wx + d[0] * off
                py = wy + d[1] * off if vert else (lo + hi) / 2
                tip = (px + d[0] * 18, py + d[1] * 18)
                n = (-d[1], d[0])
                pts = np.int32([(tip[0], tip[1]), (px - d[0] * 8 + n[0] * 26, py - d[1] * 8 + n[1] * 26),
                                (px - d[0] * 8 - n[0] * 26, py - d[1] * 8 - n[1] * 26)])
                cv2.polylines(img, [pts[[1, 0, 2]]], False, (110, 255, 140), 4, cv2.LINE_AA)
            for edge in (lo + 8, hi - 8):                              # lane edges
                a = (int(edge), int(wy)) if vert else (int(wx), int(edge))
                b = (int(edge), int(wy + d[1] * 320)) if vert else (int(wx + d[0] * 320), int(edge))
                cv2.line(img, a, b, (90, 220, 120), 1, cv2.LINE_AA)
            mid = ((lo + hi) / 2, wy + d[1] * 40) if vert else (wx + d[0] * 40, (lo + hi) / 2)
            cv2.circle(glow, (int(mid[0]), int(mid[1])), 40, (30, 90, 30), -1)

    def _draw_lasers(self, img, glow, snap: GameSnapshot) -> None:
        h, w = img.shape[:2]
        for L in snap.lasers:
            o = np.array([L.ox, L.oy])
            end = o + np.array([L.dx, L.dy]) * 2200
            a, b = (int(o[0]), int(o[1])), (int(end[0]), int(end[1]))
            if L.hazard:
                self._draw_strike(img, glow, L, a, b, w, h)
                continue
            if not L.firing:
                f = L.progress
                cv2.line(img, a, b, (60, 60, int(120 + 135 * f)), 1 if f < 0.7 else 3, cv2.LINE_AA)
            else:
                wd = L.width
                cv2.line(glow, a, b, (60, 40, 255), int(34 * wd))
                cv2.line(img, a, b, (120, 120, 255), int(14 * wd), cv2.LINE_AA)
                cv2.line(img, a, b, (255, 255, 255), max(2, int(6 * wd)), cv2.LINE_AA)

    def _draw_strike(self, img, glow, L, a, b, w, h) -> None:
        """Lightning strike: a storm cloud gathers at the screen edge, then a forked bolt tears across."""
        cx = int(min(max(L.ox, 30), w - 30)) if abs(L.dy) > abs(L.dx) else 34
        cy = 34 if abs(L.dy) > abs(L.dx) else int(min(max(L.oy, 30), h - 30))
        f = L.progress
        if not L.firing:
            for k in range(4):                                         # the thundercloud
                cv2.circle(img, (int(cx + (k - 1.5) * 22), cy + (k % 2) * 8), 24 - (k % 2) * 6,
                           (70 + k * 8,) * 3, -1, cv2.LINE_AA)
            flick = self.rng.random() < 0.3 + 0.5 * f
            cv2.line(glow, a, b, (40, 20, 5), int(18 + 40 * f))        # danger lane
            if flick:
                cv2.line(img, a, b, (255, 240, 200), 1 + int(2 * f), cv2.LINE_AA)
            else:
                pts = bolt(self.rng, a, b, 10, 5)
                cv2.polylines(img, [np.int32(pts)], False, (230, 170, 120), 1, cv2.LINE_AA)
            cv2.circle(glow, (cx, cy), int(30 + 20 * f), (90, 50, 20), -1)
        else:
            main = bolt(self.rng, a, b, 46, 6)
            cv2.polylines(glow, [np.int32(main)], False, (255, 120, 40), 40)
            cv2.polylines(img, [np.int32(main)], False, (255, 200, 140), 12, cv2.LINE_AA)
            cv2.polylines(img, [np.int32(main)], False, (255, 255, 255), 4, cv2.LINE_AA)
            for _ in range(4):                                          # forks
                i = self.rng.randrange(8, len(main) - 12)
                tip = (main[i][0] + self.rng.randint(-160, 160), main[i][1] + self.rng.randint(-160, 160))
                fork = bolt(self.rng, main[i], tip, 20, 4)
                cv2.polylines(img, [np.int32(fork)], False, (255, 230, 190), 3, cv2.LINE_AA)
                cv2.polylines(glow, [np.int32(fork)], False, (200, 100, 40), 14)

    def _draw_bombs(self, img, glow, snap: GameSnapshot) -> None:
        for b in snap.bombs:
            c = (int(b.x), int(b.y))
            seed = int(b.x * 7 + b.y * 13) % 1000
            if b.kind == "rock":
                self._rock(img, glow, b, c, seed)
            elif b.kind == "lava":
                self._lava(img, glow, b, c, seed)
            else:
                self._fuse_bomb(img, glow, b, c)

    def _ground_ring(self, img, glow, b, c, col, fill) -> None:
        f = b.progress
        cv2.circle(glow, c, max(1, int(b.r * f)), fill, -1)
        for k in range(16):                                            # dashed danger circle
            if k % 2 == 0:
                a0 = k * 22.5 + self.t * 2
                cv2.ellipse(img, c, (int(b.r), int(b.r)), 0, a0, a0 + 14, col, 3, cv2.LINE_AA)

    def _fuse_bomb(self, img, glow, b, c) -> None:
        if not b.blasting:
            f = b.progress
            self._ground_ring(img, glow, b, c, (60, 60, 255), (0, 0, 110))
            cv2.circle(img, c, 15, (40, 38, 46), -1, cv2.LINE_AA)       # an iron bomb with a burning fuse
            cv2.circle(img, c, 15, (20, 10, 30), 2, cv2.LINE_AA)
            cv2.circle(img, (c[0] - 5, c[1] - 5), 4, (120, 120, 135), -1, cv2.LINE_AA)
            tip = (c[0] + 9, int(c[1] - 17 - 10 * (1 - f)))
            cv2.line(img, (c[0] + 3, c[1] - 13), tip, (70, 100, 130), 3, cv2.LINE_AA)
            cv2.circle(glow, tip, 14, (0, 140, 255), -1)
            cv2.circle(img, tip, 4, (80, 230, 255), -1, cv2.LINE_AA)
        else:
            self._blast(img, glow, b, c, (0, 170, 255))

    def _blast(self, img, glow, b, c, col) -> None:
        k = b.progress
        cv2.circle(glow, c, int(b.r * (1 + 0.25 * k)), col, -1)
        cv2.circle(img, c, max(2, int(b.r * 0.8 * (1 - 0.3 * k))), (255, 255, 255), -1)
        cv2.circle(img, c, int(b.r * (0.6 + 0.6 * k)), col, 4, cv2.LINE_AA)

    def _rock(self, img, glow, b, c, seed) -> None:
        if b.blasting:
            k = b.progress
            cv2.circle(glow, c, int(b.r), (60, 90, 120), -1)
            for i in range(6):                                          # dust and flying chunks
                a = i * 1.05 + seed
                p = (int(c[0] + math.cos(a) * b.r * (0.5 + k)), int(c[1] + math.sin(a) * b.r * (0.35 + 0.5 * k)))
                cv2.circle(img, p, int(b.r * (0.22 + 0.2 * k)), (110, 130, 150), -1, cv2.LINE_AA)
                cv2.circle(img, (p[0] + 6, p[1] - 10 - int(30 * k)), 7, (60, 85, 110), -1, cv2.LINE_AA)
            cv2.circle(img, c, int(b.r * (0.5 + 0.7 * k)), (200, 215, 230), 3, cv2.LINE_AA)
            return
        f = b.progress
        self._ground_ring(img, glow, b, c, (60, 60, 255), (0, 0, 90))
        cv2.ellipse(img, (c[0], c[1] + 4), (int(b.r * 0.9 * f), int(b.r * 0.45 * f)), 0, 0, 360, (25, 25, 35), -1, cv2.LINE_AA)
        drop = (1 - f) ** 2 * 520                                       # the boulder falls and speeds up
        size = b.r * (0.32 + 0.22 * f)
        cy = c[1] - drop - 6
        pts = []
        for k in range(10):
            a = k * math.tau / 10
            rad = size * (0.82 + 0.22 * math.sin(k * 2.3 + seed))
            pts.append((c[0] + math.cos(a) * rad, cy + math.sin(a) * rad * 0.92))
        pts = np.int32(pts)
        cv2.fillPoly(img, [pts], (84, 104, 128), cv2.LINE_AA)
        cv2.fillPoly(img, [np.int32([(c[0] - size * 0.5, cy - size * 0.1), (c[0] - size * 0.1, cy - size * 0.65),
                                     (c[0] + size * 0.3, cy - size * 0.45), (c[0], cy)])], (140, 160, 180), cv2.LINE_AA)
        cv2.polylines(img, [pts], True, (25, 30, 40), 3, cv2.LINE_AA)
        cv2.line(img, (int(c[0] + size * 0.1), int(cy)), (int(c[0] + size * 0.5), int(cy + size * 0.5)), (30, 35, 45), 2, cv2.LINE_AA)
        if drop > 30:                                                   # speed streaks
            for dx in (-0.4, 0.0, 0.4):
                x = int(c[0] + dx * size)
                cv2.line(img, (x, int(cy - size - 40)), (x, int(cy - size - 6)), (190, 205, 220), 1, cv2.LINE_AA)

    def _lava(self, img, glow, b, c, seed) -> None:
        if b.blasting:
            k = b.progress
            self._blast(img, glow, b, c, (0, 120, 255))
            for i in range(9):                                          # molten spray
                a = -math.pi / 2 + (i - 4) * 0.28
                d = b.r * (0.5 + 1.4 * k)
                p = (int(c[0] + math.cos(a) * d * 0.6), int(c[1] + math.sin(a) * d - 60 * k * (1 - k) * 4))
                cv2.circle(img, p, 6, (40, 160, 255), -1, cv2.LINE_AA)
                cv2.circle(glow, p, 14, (0, 100, 255), -1)
            return
        f = b.progress
        self._ground_ring(img, glow, b, c, (40, 120, 255), (0, 60, 160))
        pulse = 1 + 0.12 * math.sin(self.t * 0.5 + seed)
        cv2.ellipse(img, c, (int(b.r * 0.6 * f * pulse), int(b.r * 0.4 * f * pulse)), 0, 0, 360, (20, 70, 200), -1, cv2.LINE_AA)
        cv2.ellipse(img, c, (int(b.r * 0.35 * f), int(b.r * 0.22 * f)), 0, 0, 360, (80, 200, 255), -1, cv2.LINE_AA)
        t = (1 - f)                                                     # a glob lobbed in a high arc
        gx, gy = c[0] + 140 * t * (1 if seed % 2 else -1), c[1] - 4 * 300 * t * (1 - t) - 20 * t
        for k in range(1, 5):                                           # fiery trail
            tt = min(1.0, t + k * 0.05)
            px, py = c[0] + 140 * tt * (1 if seed % 2 else -1), c[1] - 4 * 300 * tt * (1 - tt) - 20 * tt
            cv2.circle(img, (int(px), int(py)), max(2, 14 - k * 3), (30, 110, 255), -1, cv2.LINE_AA)
        cv2.circle(glow, (int(gx), int(gy)), 34, (0, 110, 255), -1)
        cv2.circle(img, (int(gx), int(gy)), 17, (20, 90, 230), -1, cv2.LINE_AA)
        cv2.circle(img, (int(gx), int(gy)), 10, (60, 200, 255), -1, cv2.LINE_AA)

    # -- player powers --------------------------------------------------------
    def _draw_fire(self, glow) -> None:
        for p in self.fire_particles:
            t = max(0.0, p["life"]) / p["max"]
            color = (0, int(60 + 195 * t), 255)                        # BGR: red -> yellow
            cv2.circle(glow, (int(p["x"]), int(p["y"])), max(1, int(p["r"] * t)), color, -1)

    def _draw_sparks(self, img, glow) -> None:
        for s in self.sparks:
            t = max(0.0, s["life"]) / s["max"]
            col = tuple(int(c * (0.35 + 0.65 * t)) for c in s["col"])
            c, r = (int(s["x"]), int(s["y"])), max(1, int(s["r"] * (0.4 + 0.6 * t)))
            cv2.circle(img, c, r, col, -1)
            cv2.circle(glow, c, r * 2, col, -1)

    def _draw_flyers(self, img, glow) -> None:
        boulders = []
        for p in self.flyers:
            x, y, d, kind, s = p["x"], p["y"], p["d"], p["kind"], p["size"]
            c = (int(x), int(y))
            if kind == "fire":
                cv2.circle(glow, c, int(s * 1.8), (0, 120, 255), -1)
                cv2.circle(img, c, s, (100, 210, 255), -1)
                cv2.circle(img, c, int(s * 0.55), (235, 255, 255), -1)
            elif kind == "air":
                ang = math.degrees(math.atan2(d[1], d[0])) + 90         # long axis across travel direction
                for k, (scale, th) in enumerate(((1.0, 4), (0.8, 3), (0.6, 2))):
                    ctr = (int(x - d[0] * k * 9), int(y - d[1] * k * 9))
                    ax = (int(s * 1.5 * scale), int(s * 0.55 * scale))
                    cv2.ellipse(glow, ctr, ax, ang, 195, 345, (255, 240, 200), th + 10)
                    cv2.ellipse(img, ctr, ax, ang, 195, 345, (255, 255, 250), th)
            elif kind == "water":
                ang = math.degrees(math.atan2(d[1], d[0]))
                cv2.circle(glow, c, int(s * 1.7), (255, 170, 40), -1)
                for k in (3, 2, 1):                                     # tail
                    cv2.circle(img, (int(x - d[0] * s * k * 0.9), int(y - d[1] * s * k * 0.9)),
                               max(3, int(s * (0.75 - 0.15 * k))), (255, 205, 90), -1)
                cv2.ellipse(img, c, (int(s * 1.5), int(s * 0.85)), ang, 0, 360, (255, 205, 90), -1)
                cv2.ellipse(img, c, (int(s * 0.9), int(s * 0.45)), ang, 0, 360, (255, 255, 235), -1)
            else:
                boulders.append(p)
        for p in boulders:                                              # solid spinning rock
            pts = []
            for k in range(7):
                a = p["rot"] + k * 2 * math.pi / 7
                rad = p["size"] * (0.75 + 0.25 * ((k * 53 + p["size"]) % 3) / 2)
                pts.append((p["x"] + math.cos(a) * rad, p["y"] + math.sin(a) * rad))
            pts = np.int32(pts)
            cv2.fillPoly(img, [pts], (70, 105, 150))
            cv2.fillPoly(img, [np.int32((pts - pts.mean(0)) * 0.55 + pts.mean(0) - 4)], (105, 140, 185))
            cv2.polylines(img, [pts], True, (20, 30, 45), 2)

    def _draw_lightning(self, img, glow, b: dict) -> None:
        rng = self.rng
        for a, c in b["legs"]:
            length = float(np.linalg.norm(np.asarray(c, float) - np.asarray(a, float)))
            pts = bolt(rng, a, c, offset=min(60, length * 0.12))
            for p1, p2 in zip(pts[:-1], pts[1:]):
                cv2.line(glow, p1, p2, (255, 140, 60), 10)
                cv2.line(img, p1, p2, (255, 255, 255), 2, cv2.LINE_AA)
            for _ in range(2):                                          # little side branches
                i = rng.randint(3, max(3, len(pts) - 4))
                end = np.array(pts[i], float) + np.array([rng.uniform(-110, 110), rng.uniform(-110, 110)])
                side = bolt(rng, pts[i], end, 20, 4)
                for p1, p2 in zip(side[:-1], side[1:]):
                    cv2.line(glow, p1, p2, (255, 140, 60), 5)
                    cv2.line(img, p1, p2, (255, 235, 200), 1)

    def _draw_charge(self, glow, snap: GameSnapshot, frame: GestureFrame) -> None:
        for hand in frame.hands:
            g = hand.gesture
            if g not in snap.unlocked_elements or snap.mana.get(g, 0.0) < CAST_COST[g]:
                continue
            if g is Element.LIGHTNING:
                tip = (int(hand.center[0] + hand.direction[0] * hand.size * 1.2),
                       int(hand.center[1] + hand.direction[1] * hand.size * 1.2))
                cv2.circle(glow, tip, 22, POWER_COLORS["lightning"], -1)
                continue
            c = (int(hand.center[0]), int(hand.center[1]))
            r = int(hand.size * (0.5 + 0.08 * math.sin(self.t * 0.5)))
            cv2.circle(glow, c, r, POWER_COLORS[g.value], -1)

    def _draw_convergence(self, img, glow, snap: GameSnapshot, frame: GestureFrame | None):
        """The prototype's Avatar State light show: aura, spinning rays, four orbiting element orbs, shockwaves."""
        c = np.asarray(self.nova_center, float)
        t = self.t
        ci = (int(c[0]), int(c[1]))
        pulse = 1 + 0.15 * math.sin(t * 0.3)
        cv2.circle(glow, ci, int(260 * pulse), (140, 110, 60), -1)
        cv2.circle(glow, ci, int(120 * pulse), (255, 230, 170), -1)
        for k in range(18):
            ang = t * 0.07 + k * math.pi / 9
            cv2.line(glow, ci, (int(c[0] + math.cos(ang) * 600), int(c[1] + math.sin(ang) * 600)), (255, 220, 150), 10)
        for i, g in enumerate(AVATAR_ELEMENTS):
            ang = t * 0.2 + i * math.pi / 2
            rad = 150 + 18 * math.sin(t * 0.2)
            pos = (int(c[0] + math.cos(ang) * rad), int(c[1] + math.sin(ang) * rad))
            cv2.circle(glow, pos, 55, POWER_COLORS[g], -1)
            cv2.circle(img, pos, 24, POWER_COLORS[g], -1)
            cv2.circle(img, pos, 10, (255, 255, 255), -1)
        cv2.circle(img, ci, 40, (255, 255, 255), -1)
        if self.nova_targets:                                           # a bolt to every enemy that fell
            for target in self.nova_targets[:8]:
                self._draw_bolt_to(img, glow, c, target, 14)
        else:
            for _ in range(8):
                d = rot(self.nova_dir, self.rng.uniform(-70, 70)) * self.rng.uniform(500, 1000)
                self._draw_bolt_to(img, glow, c, c + d, 14)
        for r in self.rings:
            cv2.circle(glow, (r["x"], r["y"]), int(r["r"]), (255, 220, 160), 22)
            cv2.circle(img, (r["x"], r["y"]), int(r["r"]), (255, 255, 255), 4, cv2.LINE_AA)
        return img if self.reduced_flash else self._add(img, (40, 35, 25))     # brighter white-blue screen flood

    def _draw_bolt_to(self, img, glow, a, b, width=10) -> None:
        length = float(np.linalg.norm(np.asarray(b, float) - np.asarray(a, float)))
        pts = bolt(self.rng, a, b, offset=min(60, length * 0.12))
        for p1, p2 in zip(pts[:-1], pts[1:]):
            cv2.line(glow, p1, p2, (255, 150, 70), width)
            cv2.line(img, p1, p2, (255, 255, 255), 2, cv2.LINE_AA)

    # -- labels + HUD (same layout as the prototype) -----------------------------
    def _draw_labels(self, img, snap: GameSnapshot, frame: GestureFrame) -> None:
        if self.nova > 0:
            return
        for hand in frame.hands:
            g = hand.gesture
            if g not in snap.unlocked_elements:
                continue
            text = POWER_NAMES[g.value]
            x = int(hand.center[0] - hand.size)
            y = int(hand.center[1] - hand.size * 2.2)
            pos = (x, max(35, y - 15))
            cv2.putText(img, text, pos, cv2.FONT_HERSHEY_DUPLEX, 1.1, (0, 0, 0), 5, cv2.LINE_AA)
            cv2.putText(img, text, pos, cv2.FONT_HERSHEY_DUPLEX, 1.1, POWER_COLORS[g.value], 2, cv2.LINE_AA)

    def _draw_hud(self, img, snap: GameSnapshot) -> None:
        """HP + lives (top left), mana bars (bottom left), Convergence meter (bottom centre)."""
        H, W = img.shape[:2]
        font = cv2.FONT_HERSHEY_PLAIN
        clock = int(self.t)
        playing = snap.state in (SessionState.ACTIVE, SessionState.BOSS)

        # --- HP bar
        bw, bh, x0, y0 = 250, 18, 15, 15
        cv2.rectangle(img, (x0 - 2, y0 - 2), (x0 + bw + 2, y0 + bh + 2), (0, 0, 0), -1)
        frac = max(0.0, min(1.0, snap.hp / 100.0))
        hp_col = (60, 60, 255) if frac < 0.3 else (70, 210, 70)
        if snap.invulnerable > 0 and (clock // 3) % 2 == 0:
            hp_col = (255, 255, 255)                                    # blink while invincible
        cv2.rectangle(img, (x0, y0), (x0 + int(bw * frac), y0 + bh), hp_col, -1)
        cv2.putText(img, f"HP {int(max(0, snap.hp))}", (x0 + 6, y0 + 14), font, 1.1, (255, 255, 255), 1, cv2.LINE_AA)

        # --- lives (hearts)
        for i in range(3):
            pts = heart_points(x0 + 14 + i * 38, y0 + 52, 24)
            if i < snap.lives:
                cv2.fillPoly(img, [pts], (60, 60, 255))
                cv2.polylines(img, [pts], True, (255, 255, 255), 1, cv2.LINE_AA)
            else:
                cv2.polylines(img, [pts], True, (110, 110, 110), 1, cv2.LINE_AA)

        # --- active pick-up effects, under the hearts
        buffs = [("SHIELD", snap.shield, SHIELD_TIME, (255, 200, 80)), ("BOOST", snap.boost, BOOST_TIME, (0, 220, 255)),
                 ("REGEN", snap.regen, REGEN_TIME, (90, 220, 90))]
        row = 0
        for name, left, total, col in buffs:
            if left <= 0:
                continue
            y = 100 + row * 22
            cv2.putText(img, f"{name} {int(math.ceil(left))}s", (15, y + 10), font, 1.1, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.rectangle(img, (124, y), (224, y + 10), (0, 0, 0), -1)
            cv2.rectangle(img, (125, y + 1), (125 + int(98 * left / total), y + 9), col, -1)
            row += 1

        # --- mana bars, one per unlocked element
        elements = [e.value for e in snap.unlocked_elements]
        my = H - 50 - max(1, len(elements)) * 20
        for i, el in enumerate(elements):
            y = my + i * 20
            col = POWER_COLORS[el]
            if snap.mana.get(Element(el), 0.0) < CAST_COST[Element(el)]:
                col = tuple(int(c * 0.45) for c in col)                 # too low to cast
            cv2.putText(img, el.upper(), (15, y + 10), font, 1.0, (255, 255, 255), 1, cv2.LINE_AA)
            bx, bwid = 95, 150
            cv2.rectangle(img, (bx - 1, y - 1), (bx + bwid + 1, y + 12), (0, 0, 0), -1)
            cv2.rectangle(img, (bx, y), (bx + int(bwid * snap.mana.get(Element(el), 0.0) / 100.0), y + 11), col, -1)
            if self.nomana[el] > 0:
                cv2.rectangle(img, (bx - 1, y - 1), (bx + bwid + 1, y + 12), (0, 0, 255), 2)

        # --- Convergence meter (the prototype's Avatar State meter)
        bw, bh = 320, 14
        x0, y0 = (W - bw) // 2, H - 40
        cv2.rectangle(img, (x0 - 2, y0 - 2), (x0 + bw + 2, y0 + bh + 2), (0, 0, 0), -1)
        if self.nova > 0:
            frac, col, label = self.nova / CONVERGENCE_FRAMES, (80, 230, 255), "KALAMPAG!"
        elif snap.convergence >= 100:
            frac, col, label = 1.0, (255, 200, 90), "KALAMPAG READY - clap your palms together!"
        else:
            frac, col = snap.convergence / 100.0, (120, 120, 120)
            label = f"Kalampag: {int(round(snap.convergence / 10))}/10 kills"
        cv2.rectangle(img, (x0, y0), (x0 + int(bw * max(0.0, min(1.0, frac))), y0 + bh), col, -1)
        cv2.putText(img, label, (x0, y0 - 8), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

        # --- wave / score text (top right) and stage name (bottom left)
        if snap.objective == "BOSS":
            head = "BOSS FIGHT!"
        else:
            head = f"WAVE {snap.wave_number}/3  {snap.objective.replace('_', ' ').upper()}"
            if snap.quota is not None:
                head = f"WAVE {snap.wave_number}/3  HUNT {min(snap.quota_done, snap.quota)}/{snap.quota}"
            if snap.time_left is not None:
                head += f" {int(math.ceil(snap.time_left))}s"
        text = f"{head}   SCORE: {snap.score:05d}"
        (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 0.7, 2)
        cv2.putText(img, text, (W - tw - 20, 35), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        if snap.combo >= 2:                                             # combo chain with a draining timer bar
            ctext = f"COMBO x{snap.combo_mult}  ({snap.combo})"
            (cw, _), _ = cv2.getTextSize(ctext, cv2.FONT_HERSHEY_DUPLEX, 0.7, 2)
            hot = (0, 215, 255) if snap.combo_mult < 4 else (60, 60, 255)
            cv2.putText(img, ctext, (W - cw - 20, 68), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 0, 0), 5, cv2.LINE_AA)
            cv2.putText(img, ctext, (W - cw - 20, 68), cv2.FONT_HERSHEY_DUPLEX, 0.7, hot, 2, cv2.LINE_AA)
            cv2.rectangle(img, (W - cw - 20, 76), (W - 20, 82), (0, 0, 0), -1)
            cv2.rectangle(img, (W - cw - 20, 76), (W - cw - 20 + int(cw * min(1.0, snap.combo_left / 3.0)), 82), hot, -1)
        cv2.putText(img, f"{snap.level_title.upper()}  (ESC = pause)", (15, H - 15), cv2.FONT_HERSHEY_PLAIN, 1.2,
                    (255, 255, 255), 1, cv2.LINE_AA)
        if playing and not snap.hands_visible and (clock // 6) % 2 == 0:
            msg = "SHOW YOUR HANDS!"
            (mw, _), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_DUPLEX, 1.0, 3)
            pos = ((W - mw) // 2, 130)
            cv2.putText(img, msg, pos, cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 0, 0), 7, cv2.LINE_AA)
            cv2.putText(img, msg, pos, cv2.FONT_HERSHEY_DUPLEX, 1.0, (60, 60, 255), 3, cv2.LINE_AA)

        if self.banner_t > 0:                                           # big centre banner
            txt = self.banner_text
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_DUPLEX, 2.0, 4)
            pos = ((W - tw) // 2, H // 2)
            cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, 2.0, (0, 0, 0), 9, cv2.LINE_AA)
            cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, 2.0, self.banner_col, 4, cv2.LINE_AA)

        if self.caption_t > 0 and self.caption_text:                    # story caption under the banner
            fade = min(1.0, self.caption_t / 20.0)
            words, lines, line = self.caption_text.split(), [], ""
            for word in words:
                if len(line) + len(word) + 1 > 62:
                    lines.append(line)
                    line = word
                else:
                    line = f"{line} {word}".strip()
            lines.append(line)
            for i, text in enumerate(lines[:3]):
                (tw, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, 0.8, 2)
                pos = ((W - tw) // 2, H // 2 + 62 + i * 34)
                cv2.putText(img, text, pos, cv2.FONT_HERSHEY_DUPLEX, 0.8, (0, 0, 0), 6, cv2.LINE_AA)
                cv2.putText(img, text, pos, cv2.FONT_HERSHEY_DUPLEX, 0.8, tuple(int(235 * fade) for _ in range(3)), 2, cv2.LINE_AA)

        if snap.state is SessionState.FAILED:                           # the prototype's GAME OVER look
            img[:] = cv2.addWeighted(img, 0.45, np.zeros_like(img), 0.55, 0)
            for txt, scale, yoff, col in (("GAME OVER", 2.6, -30, (60, 60, 255)),
                                          (f"Score: {snap.score}", 1.1, 30, (255, 255, 255))):
                (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_DUPLEX, scale, 3)
                pos = ((W - tw) // 2, H // 2 + yoff)
                cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, scale, (0, 0, 0), 8, cv2.LINE_AA)
                cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, scale, col, 3, cv2.LINE_AA)
