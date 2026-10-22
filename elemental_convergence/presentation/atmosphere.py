"""Atmosphere for the battle view: each place's weather, ground marks that outlast an explosion, shadows,
creature eyes and idle effects, and the little extras that make hits and deaths feel weighty.

Everything here is a mixin for ``BattleView`` (it uses the view's ``t``, ``rng``, ``sparks`` and so on) so
the battle view itself stays readable. Ambient effects are stateless: positions come from the frame counter,
so there is nothing to update and nothing to leak.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from . import sprites

# (tint BGR, strength) of each place's edge-of-screen mood
MOOD = {
    "stonewake": ((30, 70, 40), 0.30),
    "tidelost": ((80, 46, 12), 0.36),
    "skyglass": ((70, 70, 60), 0.22),
    "cinderforge": ((14, 36, 90), 0.42),
    "eclipse": ((60, 14, 50), 0.46),
}

# where each creature's eyes sit, in radii from its centre: (x, y, size, BGR glow)
EYES = {
    "shooter": ((-0.12, -0.54, 0.07, (60, 40, 255)), (0.12, -0.54, 0.07, (60, 40, 255))),
    "charger": ((-0.27, -0.3, 0.11, (40, 40, 255)), (0.27, -0.3, 0.11, (40, 40, 255))),
    "gunner": ((-0.17, -0.34, 0.06, (40, 40, 255)), (0.17, -0.34, 0.06, (40, 40, 255))),
    "caster": ((-0.1, -0.5, 0.06, (255, 220, 120)), (0.1, -0.5, 0.06, (255, 220, 120))),
    "spinner": ((-0.26, -0.18, 0.1, (40, 40, 255)), (0.26, -0.18, 0.1, (40, 40, 255))),
    "blinker": ((-0.11, -0.57, 0.05, (60, 60, 255)), (0.11, -0.57, 0.05, (60, 60, 255))),
    "stone_guardian": ((-0.34, -0.1, 0.18, (40, 220, 255)), (0.34, -0.1, 0.18, (40, 220, 255))),
    "tide_guardian": ((-0.33, -0.2, 0.2, (30, 200, 255)), (0.33, -0.2, 0.2, (30, 200, 255))),
    "ember_guardian": ((-0.33, -0.08, 0.1, (60, 230, 255)), (0.33, -0.08, 0.1, (60, 230, 255))),
    "rift_sovereign": ((-0.42, -0.34, 0.11, (40, 230, 255)), (0.42, -0.34, 0.11, (40, 230, 255))),
    "gale_guardian": ((0.0, 0.0, 0.3, (230, 190, 70)),),
    "sniper": ((0.0, -0.27, 0.27, (70, 230, 170)),),
}
LID = (24, 18, 30)


def _rnd(i: int, salt: int = 0) -> float:
    """A fixed pseudo-random number in [0, 1) for particle ``i``."""
    return ((i * 7919 + salt * 104729 + 13) * 2654435761 % 4294967296) / 4294967296.0


def _mask(img, shape, alpha, box, draw):
    """Draw with transparency: ``draw(layer, dx, dy)`` paints on a copy of the box, which is mixed back in."""
    h, w = img.shape[:2]
    x0, y0, x1, y1 = max(0, box[0]), max(0, box[1]), min(w, box[2]), min(h, box[3])
    if x0 >= x1 or y0 >= y1 or alpha <= 0:
        return
    roi = img[y0:y1, x0:x1]
    layer = roi.copy()
    draw(layer, -x0, -y0)
    cv2.addWeighted(layer, min(1.0, alpha), roi, 1.0 - min(1.0, alpha), 0, roi)


class AtmosphereMixin:
    def _atmo_reset(self) -> None:
        self.decals: list[dict] = []
        self.pops: list[dict] = []           # quick expanding rings
        self.flash_t = 0.0
        self._seen: set = set()
        self._bosses_seen: set[int] = set()
        self._mood: dict = {}
        self._moon: dict = {}

    # ------------------------------------------------------------------ mood and weather
    def _mood_layers(self, size, stage):
        key = (size, stage)
        hit = self._mood.get(key)
        if hit is None:
            w, h = size
            tint, strength = MOOD.get(stage, ((40, 40, 40), 0.2))
            yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
            d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
            edge = np.clip((d - 0.55) / 0.9, 0.0, 1.0) ** 1.6 * strength
            mul = np.repeat((1.0 - edge * 0.75)[..., None], 3, axis=2)
            add = edge[..., None] * np.array(tint, np.float32) * 0.55
            hit = ((mul * 255).astype(np.uint8), np.clip(add, 0, 255).astype(np.uint8))
            self._mood[key] = hit
        return hit

    def _apply_mood(self, img, stage):
        mul, add = self._mood_layers((img.shape[1], img.shape[0]), stage)
        return cv2.add(cv2.multiply(img, mul, scale=1 / 255.0), add)

    def _ambient(self, img, glow, stage) -> None:
        h, w = img.shape[:2]
        t = self.t
        n = 0.5 if self.fast else 1.0
        if stage == "stonewake":                                        # dust in the light and falling balete leaves
            for i in range(int(16 * n)):
                x = (_rnd(i) * w + t * (0.3 + _rnd(i, 1) * 0.5)) % w
                y = (_rnd(i, 2) * h + t * 0.25) % h
                cv2.circle(glow, (int(x), int(y)), 2, (70, 100, 90), -1)
            for i in range(int(6 * n)):
                ph = (t * 0.012 * (0.6 + _rnd(i, 3)) + _rnd(i, 4)) % 1.0
                x = _rnd(i, 5) * w + math.sin(ph * 14 + i) * 40
                y = ph * (h + 40) - 20
                cv2.ellipse(img, (int(x), int(y)), (8, 3), math.degrees(math.sin(ph * 9 + i)) * 0.6, 0, 360, (60, 150 - (i % 3) * 25, 70), -1, cv2.LINE_AA)
        elif stage == "tidelost":                                       # bubbles and spray
            for i in range(int(14 * n)):
                ph = (t * 0.01 * (0.5 + _rnd(i)) + _rnd(i, 1)) % 1.0
                x = _rnd(i, 2) * w + math.sin(ph * 20 + i) * 12
                y = h - ph * (h + 20)
                r = 3 + int(_rnd(i, 3) * 6)
                cv2.circle(img, (int(x), int(y)), r, (255, 235, 190), 1, cv2.LINE_AA)
                cv2.circle(glow, (int(x), int(y)), r, (60, 40, 14), -1)
        elif stage == "skyglass":                                       # wind streaks
            for i in range(int(10 * n)):
                x = (_rnd(i) * (w + 300) + t * (9 + _rnd(i, 1) * 9)) % (w + 300) - 150
                y = _rnd(i, 2) * h
                L = 60 + _rnd(i, 3) * 90
                cv2.line(glow, (int(x), int(y)), (int(x + L), int(y - 6)), (90, 90, 80), 2, cv2.LINE_AA)
        elif stage == "cinderforge":                                    # embers and ash
            for i in range(int(26 * n)):
                ph = (t * 0.014 * (0.5 + _rnd(i)) + _rnd(i, 1)) % 1.0
                x = _rnd(i, 2) * w + math.sin(ph * 12 + i) * 24
                y = h - ph * h
                cv2.circle(glow, (int(x), int(y)), 3, (0, int(90 + 70 * (1 - ph)), 255), -1)
                cv2.circle(img, (int(x), int(y)), 1, (120, 220, 255), -1)
            for i in range(int(8 * n)):
                ph = (t * 0.008 * (0.5 + _rnd(i, 7)) + _rnd(i, 8)) % 1.0
                cv2.circle(img, (int(_rnd(i, 9) * w + math.sin(ph * 8) * 30), int(ph * h)), 2, (70, 70, 78), -1)
        elif stage == "eclipse":                                        # a crescent moon and drifting spirits
            key = (w, h)
            layer = self._moon.get(key)
            if layer is None:
                layer = np.zeros((h, w, 3), np.uint8)
                c = (int(w * 0.84), int(h * 0.17))
                cv2.circle(layer, c, 46, (110, 84, 140), -1, cv2.LINE_AA)
                cv2.circle(layer, (c[0] + 20, c[1] - 8), 42, (0, 0, 0), -1, cv2.LINE_AA)
                self._moon[key] = layer
            np.copyto(glow, cv2.add(glow, layer))
            for i in range(int(8 * n)):
                ph = (t * 0.006 * (0.5 + _rnd(i)) + _rnd(i, 1)) % 1.0
                x = _rnd(i, 2) * w + math.sin(ph * 10 + i) * 50
                cv2.circle(glow, (int(x), int(h - ph * h)), 10, (90, 50, 90), -1)

    # ------------------------------------------------------------------ things that outlast the moment
    def _watch_hazards(self, snap) -> None:
        """Notice a new explosion or lightning strike and leave a mark on the ground."""
        rng = self.rng
        blasting = set()
        for b in snap.bombs:
            if not b.blasting:
                continue
            key = (b.kind, int(b.x), int(b.y))
            blasting.add(key)
            if key in self._seen:
                continue
            self.decals.append({"x": b.x, "y": b.y, "kind": b.kind, "age": 0.0, "r": b.r, "seed": int(b.x * 7 + b.y)})
            self.pops.append({"x": b.x, "y": b.y, "r": b.r * 0.3, "life": 14.0, "col": (190, 215, 235) if b.kind == "rock" else (0, 150, 255)})
            if b.kind == "rock":
                self.kick(0.7)
                self.burst(b.x, b.y, (66, 78, 92), 26, 7, life=(20, 40), size=(5, 11), gravity=0.0)      # dust
                self.burst(b.x, b.y, (60, 85, 110), 14, 12, life=(14, 26), size=(3, 7), gravity=0.7)        # chunks
            elif b.kind == "lava":
                self.kick(0.4)
                self.burst(b.x, b.y, (0, 140, 255), 36, 12, life=(18, 34), size=(3, 8), gravity=0.5)
                self.burst(b.x, b.y, (90, 220, 255), 14, 8, life=(10, 20), size=(2, 5), gravity=0.4)
            else:
                self.kick(0.5)
                self.burst(b.x, b.y, (0, 170, 255), 22, 11, life=(12, 24), size=(3, 7), gravity=0.3)
        for L in snap.lasers:
            if not (L.hazard and L.firing):
                continue
            key = ("L", int(L.ox), int(L.oy), int(L.dx * 10), int(L.dy * 10))
            blasting.add(key)
            if key in self._seen:
                continue
            a = (L.ox, L.oy)
            self.decals.append({"x": L.ox, "y": L.oy, "kind": "scorch", "age": 0.0, "a": a, "b": (L.ox + L.dx * 2200, L.oy + L.dy * 2200), "seed": 0})
            if not self.reduced_flash:
                self.flash_t = 4.0
            self.kick(0.8)
            for _ in range(10):                                             # sparks where it strikes the ground
                d = rng.uniform(200, 1400)
                self.burst(L.ox + L.dx * d, L.oy + L.dy * d, (255, 230, 170), 4, 9, life=(8, 16), size=(2, 5), gravity=0.4)
        for e in snap.enemies:
            if e.boss and e.id not in self._bosses_seen:                      # a guardian arrives
                self._bosses_seen.add(e.id)
                self.pops.append({"x": e.position[0], "y": e.position[1], "r": 20.0, "life": 40.0, "col": (80, 210, 255), "speed": 16.0})
                self.kick(0.9)
        self._seen = blasting

    def _tick_atmosphere(self, f: float) -> None:
        for d in self.decals[:]:
            d["age"] += f
            if d["age"] > (160 if d["kind"] in ("rock", "lava") else 100 if d["kind"] == "bomb" else 70):
                self.decals.remove(d)
        for p in self.pops[:]:
            p["r"] += p.get("speed", 6.0) * f
            p["life"] -= f
            if p["life"] <= 0:
                self.pops.remove(p)
        self.flash_t = max(0.0, self.flash_t - f)

    def _draw_decals(self, img, glow) -> None:
        for d in self.decals:
            life = 160 if d["kind"] in ("rock", "lava") else 100 if d["kind"] == "bomb" else 70
            a = max(0.0, 1.0 - (d["age"] / life) ** 2)
            x, y, r = int(d["x"]), int(d["y"]), d.get("r", 80.0)
            kind = d["kind"]
            if kind == "scorch":
                pa, pb = d["a"], d["b"]
                lo = (int(min(pa[0], pb[0])) - 6, int(min(pa[1], pb[1])) - 6, int(max(pa[0], pb[0])) + 6, int(max(pa[1], pb[1])) + 6)
                _mask(img, None, 0.7 * a, lo, lambda lay, dx, dy: cv2.line(lay, (int(pa[0]) + dx, int(pa[1]) + dy), (int(pb[0]) + dx, int(pb[1]) + dy), (18, 20, 28), 5, cv2.LINE_AA))
                continue
            box = (x - int(r), y - int(r * 0.7), x + int(r), y + int(r * 0.7))
            if kind == "rock":
                def draw(lay, dx, dy, d=d, r=r):
                    cv2.ellipse(lay, (x + dx, y + dy), (int(r * 0.55), int(r * 0.3)), 0, 0, 360, (26, 30, 38), -1, cv2.LINE_AA)
                    for k in range(7):
                        ang = _rnd(d["seed"] + k) * math.tau
                        cv2.line(lay, (x + dx, y + dy), (x + dx + int(math.cos(ang) * r * 0.7), y + dy + int(math.sin(ang) * r * 0.38)), (14, 16, 22), 2, cv2.LINE_AA)
                    for k in range(6):
                        ang = _rnd(d["seed"], k + 9) * math.tau
                        cv2.circle(lay, (x + dx + int(math.cos(ang) * r * 0.62), y + dy + int(math.sin(ang) * r * 0.34)), 4 + k % 3, (90, 110, 130), -1, cv2.LINE_AA)
                _mask(img, None, 0.85 * a, box, draw)
            elif kind == "lava":
                glow_a = a * (0.7 + 0.3 * math.sin(self.t * 0.4 + d["seed"]))
                cv2.ellipse(glow, (x, y), (int(r * 0.7), int(r * 0.4)), 0, 0, 360, (0, int(70 * glow_a), int(200 * glow_a)), -1)
                _mask(img, None, 0.9 * a, box, lambda lay, dx, dy: (cv2.ellipse(lay, (x + dx, y + dy), (int(r * 0.5), int(r * 0.28)), 0, 0, 360, (20, 60, 190), -1, cv2.LINE_AA),
                                                                  cv2.ellipse(lay, (x + dx, y + dy), (int(r * 0.28), int(r * 0.15)), 0, 0, 360, (80, 200, 255), -1, cv2.LINE_AA)))
            else:
                _mask(img, None, 0.7 * a, box, lambda lay, dx, dy: cv2.ellipse(lay, (x + dx, y + dy), (int(r * 0.5), int(r * 0.28)), 0, 0, 360, (16, 18, 24), -1, cv2.LINE_AA))

    def _draw_pops(self, img, glow) -> None:
        for p in self.pops:
            k = max(0.0, p["life"] / 14.0 if "speed" not in p else p["life"] / 40.0)
            col = tuple(int(c * min(1.0, k)) for c in p["col"])
            c = (int(p["x"]), int(p["y"]))
            cv2.circle(glow, c, int(p["r"]), col, 8)
            cv2.circle(img, c, int(p["r"]), col, 2, cv2.LINE_AA)

    # ------------------------------------------------------------------ creatures
    def _shadow(self, img, x, y, r, boss) -> None:
        cx, cy = int(x), int(y + r * (1.02 if not boss else 1.05))
        rx, ry = int(r * 0.78), max(3, int(r * 0.2))
        _mask(img, None, 0.38, (cx - rx - 2, cy - ry - 2, cx + rx + 2, cy + ry + 2),
              lambda lay, dx, dy: cv2.ellipse(lay, (cx + dx, cy + dy), (rx, ry), 0, 0, 360, (0, 0, 0), -1, cv2.LINE_AA))

    def _eyes(self, img, glow, e, x, y, r) -> None:
        pulse = 0.75 + 0.25 * math.sin(self.t * 0.25 + e.id)
        blink = e.kind not in ("sniper",) and int(self.t + e.id * 37) % 118 < 4
        for ex, ey, er, col in EYES.get(e.kind, ()):
            px, py = int(x + ex * r), int(y + ey * r)
            size = max(2, int(er * r))
            if e.enraged:
                col = (50, 50, 255)
            cv2.circle(glow, (px, py), int(size * 2.4), tuple(int(c * 0.35 * pulse) for c in col), -1)
            if blink:
                cv2.ellipse(img, (px, py), (int(size * 1.3), max(1, int(size * 0.55))), 0, 0, 360, LID, -1, cv2.LINE_AA)
                cv2.line(img, (px - int(size * 1.2), py), (px + int(size * 1.2), py), (6, 4, 8), 2, cv2.LINE_AA)

    def _creature_effects(self, img, glow, e, x, y, r) -> None:
        """Idle magic: each creature has a little something of its own going on."""
        t, kind = self.t, e.kind
        if kind == "sweeper":                                           # ghost-fire licks upward
            for k in range(4):
                ph = (t * 0.035 + k / 4 + e.id * 0.13) % 1.0
                px, py = x + math.sin(ph * 8 + k) * 0.35 * r, y - r * (0.5 + 1.2 * ph)
                cv2.circle(glow, (int(px), int(py)), max(2, int(8 * (1 - ph))), (110, 190, 40), -1)
                cv2.circle(img, (int(px), int(py)), max(1, int(3 * (1 - ph))), (230, 255, 200), -1)
        elif kind == "ember_guardian":                                  # embers and ash rise from the crater
            for k in range(7):
                ph = (t * 0.02 + k / 7) % 1.0
                px, py = x + math.sin(ph * 10 + k * 2) * 0.35 * r, y - r * (0.9 + 1.6 * ph)
                cv2.circle(glow, (int(px), int(py)), 6, (0, int(80 + 100 * (1 - ph)), 255), -1)
                cv2.circle(img, (int(px), int(py)), 2, (150, 230, 255), -1)
        elif kind == "tide_guardian":                                   # bubbles
            for k in range(5):
                ph = (t * 0.018 + k / 5) % 1.0
                px, py = x + math.sin(k * 3.1) * r * 0.9 + math.sin(ph * 12) * 8, y + r * 0.6 - r * 1.8 * ph
                cv2.circle(img, (int(px), int(py)), 4 + k % 3, (255, 235, 190), 1, cv2.LINE_AA)
        elif kind == "gale_guardian":                                   # wind arcs spinning round the eye
            for k in range(4):
                a0 = t * 7 + k * 90
                cv2.ellipse(glow, (int(x), int(y)), (int(r * 1.3), int(r * 1.2)), 0, a0, a0 + 40, (150, 140, 90), 6, cv2.LINE_AA)
                cv2.ellipse(img, (int(x), int(y)), (int(r * 1.3), int(r * 1.2)), 0, a0, a0 + 40, (235, 245, 240), 2, cv2.LINE_AA)
            if int(t * 0.5 + e.id) % 23 == 0:
                cv2.line(glow, (int(x - r * 0.3), int(y - r * 1.4)), (int(x + r * 0.1), int(y - r * 0.6)), (120, 230, 255), 5, cv2.LINE_AA)
        elif kind == "rift_sovereign":                                  # sea mist and a glint on the moon in its jaws
            pulse = 0.6 + 0.4 * math.sin(t * 0.2)
            cv2.ellipse(glow, (int(x), int(y + r * 1.2)), (int(r * 1.6), int(r * 0.25)), 0, 0, 360, (int(70 * pulse), int(45 * pulse), 20), -1)
            cv2.circle(glow, (int(x), int(y + r * 0.42)), int(r * 0.4), (int(60 * pulse), int(120 * pulse), int(150 * pulse)), -1)
        elif kind == "bomber":                                          # the fuse spits sparks
            fx, fy = x + 0.54 * r, y - 0.2 * r
            if self.rng.random() < 0.7:
                cv2.circle(img, (int(fx + self.rng.uniform(-4, 4)), int(fy - self.rng.uniform(0, 9))), 2, (80, 230, 255), -1)
            cv2.circle(glow, (int(fx), int(fy)), int(r * 0.2), (0, 110, 230), -1)
        elif kind == "charger" and e.wind > 0:                          # snorts steam before it rushes
            for k in range(3):
                ph = (t * 0.12 + k / 3) % 1.0
                for sx in (-1, 1):
                    cv2.circle(img, (int(x + sx * 0.2 * r + sx * ph * 14), int(y + 0.75 * r - ph * 20)), int(3 + 7 * ph), (230, 230, 235), -1, cv2.LINE_AA)
        elif kind == "shooter":                                         # the orb in her hand throbs
            pulse = 0.6 + 0.4 * math.sin(t * 0.3 + e.id)
            cv2.circle(glow, (int(x + 0.8 * r), int(y + 0.12 * r)), int(r * 0.4), (int(150 * pulse), int(50 * pulse), int(150 * pulse)), -1)
        elif kind == "caster":                                          # motes orbit the staff-less hands
            for k in range(3):
                a = t * 0.12 + k * math.tau / 3
                cv2.circle(glow, (int(x + math.cos(a) * r * 1.0), int(y + 0.05 * r + math.sin(a) * r * 0.32)), 7, (190, 150, 60), -1)
                cv2.circle(img, (int(x + math.cos(a) * r * 1.0), int(y + 0.05 * r + math.sin(a) * r * 0.32)), 2, (255, 240, 200), -1)
        elif kind == "stone_guardian" and self.rng.random() < 0.08:     # a firefly drifts past
            self.sparks.append({"x": x + self.rng.uniform(-r, r), "y": y + self.rng.uniform(-r, r), "vx": self.rng.uniform(-0.4, 0.4),
                                "vy": -0.3, "life": 40, "max": 40, "r": 3, "col": (120, 255, 255), "g": 0.0})

    # ------------------------------------------------------------------ deaths and hits
    def _spirit(self, x, y, kind, boss) -> None:
        """A defeated creature's spirit rises, in its own colour."""
        base = sprites.AURA.get(kind, (140, 140, 160))
        col = tuple(min(255, int(c * 1.9) + 40) for c in base)
        for _ in range(26 if boss else 7):
            self.sparks.append({"x": x + self.rng.uniform(-30, 30) * (3 if boss else 1), "y": y + self.rng.uniform(-10, 20),
                                "vx": self.rng.uniform(-0.8, 0.8), "vy": self.rng.uniform(-3.0, -1.2), "life": 46 if boss else 34,
                                "max": 46 if boss else 34, "r": self.rng.randint(4, 8), "col": col, "g": -0.02})
        self.pops.append({"x": x, "y": y, "r": 10.0, "life": 14.0, "col": col})
        if boss and not self.reduced_flash:
            self.flash_t = 6.0
