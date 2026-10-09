"""
Gesture Powers

AVATAR MODE (default)
  Fist                          -> EARTH BLAST
  Point with index finger       -> LIGHTNING (chains between enemies)
  Open palm, fingers apart      -> WATER BLAST
  Open palm, fingers together   -> AIR BLAST
  Two fingers (index + middle) -> FIRE BLAST
  BOTH HANDS TOGETHER           -> AVATAR STATE (needs 10 kills, lasts only a few seconds,
                                   all elements at once, much more powerful, you are invincible)

  SURVIVAL
    You have HP and 3 lives. Enemies shoot dark orbs at your HANDS and hurt you if they touch them.
    Dodge with your hands, or shoot the orbs down with your own blasts.
    KEEP YOUR HANDS ON SCREEN: if no hand is visible (or only at the very edge of the screen),
    your HP drains after a short grace period.
    ENEMY TYPES (new kinds unlock as your kill count grows, and they all get tougher and faster):
      purple SHOOTER  aimed orbs, 3-orb fans             red CHARGER   winds up, then body-slams your hand
      green SNIPER    tracking laser beam                grey GUNNER   tanky; rapid bursts and a WALL of orbs with a gap
      orange BOMBER   bombs that blow up under your hand  blue CASTER  rings of orbs and HOMING orbs
      pink SPINNER    spiral orb streams                 teal SWEEPER  sweeping beam, and a cross of beams
      pale BLINKER    teleports next to you and fires
      SHADOW LORD (boss): all of the above + curtains of beams + minions, and goes berserk at half HP

CLASSIC MODE (press 'a')
  Open palm -> Fire | Fist -> Ice | Peace sign -> Love | Pointing -> Lightning

Run:      python gesture_powers.py            (pick a camera from a list)
          python gesture_powers.py --camera 1  (go straight to camera 1)

Install:  pip install opencv-python cvzone mediapipe numpy
Keys:     'f' toggle fullscreen, 'm' fill/fit screen, 'c' next camera, 'a' avatar/classic mode,
          'e' enemies on/off, 'r' restart (after GAME OVER), 'q' or ESC to quit
Each hand is read independently, so two hands can cast two different powers.
"""
import argparse
from collections import Counter, deque
import math
import os
import random

import cv2
import numpy as np
from cvzone.HandTrackingModule import HandDetector

# --------------------------------------------------------------------------
# Gesture recognition
# --------------------------------------------------------------------------
def classify(fingers):
    """fingers = [thumb, index, middle, ring, pinky] (1 = up).
    The thumb is ignored because it is the least reliable finger."""
    _, index, middle, ring, pinky = fingers
    if index and middle and ring and pinky:
        return "fire"       # open palm
    if not (index or middle or ring or pinky):
        return "ice"        # fist
    if index and middle and not ring and not pinky:
        return "love"       # peace sign
    if index and not (middle or ring or pinky):
        return "lightning"  # pointing
    return None


# --------------------------------------------------------------------------
# FIRE
# --------------------------------------------------------------------------
fire_particles = []


def spawn_fire(hand):
    pts = [hand["center"]] + [tuple(hand["lmList"][i][:2]) for i in (4, 8, 12, 16, 20)]
    for (x, y) in pts:
        for _ in range(5):
            fire_particles.append({
                "x": x + random.uniform(-12, 12), "y": y + random.uniform(-8, 8),
                "vx": random.uniform(-2, 2), "vy": random.uniform(-9, -3),
                "life": random.randint(18, 35), "max": 35,
                "r": random.randint(8, 20),
            })


def draw_fire(img, hands_active, glow=None):
    h, w = img.shape[:2]
    layer = glow if glow is not None else np.zeros_like(img)
    for p in fire_particles[:]:
        p["x"] += p["vx"] + random.uniform(-1, 1)
        p["y"] += p["vy"]
        p["life"] -= 1
        if p["life"] <= 0:
            fire_particles.remove(p)
            continue
        t = p["life"] / p["max"]                      # 1 = fresh, 0 = dying
        color = (0, int(60 + 195 * t), 255)           # BGR: red -> yellow
        cv2.circle(layer, (int(p["x"]), int(p["y"])), max(1, int(p["r"] * t)), color, -1)
    if glow is None:
        img = add_glow(img, layer, 9)
    if hands_active:  # warm orange screen tint
        tint = np.full_like(img, (0, 70, 200))
        img = cv2.addWeighted(img, 0.85, tint, 0.15, 0)
    return img


# --------------------------------------------------------------------------
# ICE
# --------------------------------------------------------------------------
frost_cache = {}
ice_level = 0.0


def make_frost(w, h):
    rng = np.random.default_rng(1)
    noise = rng.random((h, w)).astype(np.float32)
    noise = cv2.GaussianBlur(noise, (0, 0), 3)
    noise = (noise - noise.min()) / (noise.max() - noise.min())
    frost = np.zeros((h, w, 3), np.float32)
    # crystal lines growing in from the screen edges
    canvas = np.zeros((h, w), np.uint8)
    for _ in range(140):
        side = random.choice("tblr")
        x = random.randint(0, w) if side in "tb" else (0 if side == "l" else w)
        y = random.randint(0, h) if side in "lr" else (0 if side == "t" else h)
        ang = math.atan2(h / 2 - y, w / 2 - x) + random.uniform(-0.6, 0.6)
        for _ in range(random.randint(4, 9)):
            step = random.randint(15, 45)
            nx, ny = int(x + math.cos(ang) * step), int(y + math.sin(ang) * step)
            cv2.line(canvas, (x, y), (nx, ny), 255, random.randint(1, 3))
            if random.random() < 0.4:  # side branch
                bang = ang + random.choice([-1, 1]) * 0.9
                cv2.line(canvas, (nx, ny),
                         (int(nx + math.cos(bang) * step * .6), int(ny + math.sin(bang) * step * .6)), 255, 1)
            x, y, ang = nx, ny, ang + random.uniform(-0.3, 0.3)
    canvas = cv2.GaussianBlur(canvas, (0, 0), 1.2).astype(np.float32) / 255
    # frost is thickest at the edges
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    edge = np.clip((d - 0.3) / 0.9, 0, 1)
    amount = np.clip(noise * 0.5 * edge + canvas * 0.9 + edge * 0.35, 0, 1)
    frost[:] = amount[..., None] * np.array([255, 245, 220], np.float32)  # icy white-blue (BGR)
    return frost


def draw_ice(img, active):
    global ice_level
    ice_level = min(1, ice_level + 0.08) if active else max(0, ice_level - 0.06)
    if ice_level <= 0:
        return img
    h, w = img.shape[:2]
    if (w, h) not in frost_cache:
        frost_cache[(w, h)] = make_frost(w, h)
    a = ice_level
    blue = np.full_like(img, (255, 190, 90))
    frozen = cv2.addWeighted(img, 0.55, blue, 0.45, 0)
    frozen = cv2.GaussianBlur(frozen, (0, 0), 2 + 4 * a)
    out = img.astype(np.float32) * (1 - a * 0.85) + frozen.astype(np.float32) * (a * 0.85)
    out += frost_cache[(w, h)] * a * 0.8
    return np.clip(out, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------
# LOVE
# --------------------------------------------------------------------------
hearts = []


def heart_points(cx, cy, size):
    t = np.linspace(0, 2 * math.pi, 40)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    return np.stack([cx + x * size / 16, cy - y * size / 16], 1).astype(np.int32)


def draw_love(img, active):
    h, w = img.shape[:2]
    if active:
        for _ in range(2):
            hearts.append({"x": random.randint(0, w), "y": h + 20,
                           "vy": random.uniform(2, 6), "size": random.randint(12, 45),
                           "phase": random.uniform(0, 6.28),
                           "col": random.choice([(180, 105, 255), (147, 20, 255), (203, 192, 255)])})
    layer = img.copy()
    for hr in hearts[:]:
        hr["y"] -= hr["vy"]
        hr["phase"] += 0.1
        if hr["y"] < -50:
            hearts.remove(hr)
            continue
        pts = heart_points(hr["x"] + math.sin(hr["phase"]) * 20, hr["y"], hr["size"])
        cv2.fillPoly(layer, [pts], hr["col"])
        cv2.polylines(layer, [pts], True, (255, 255, 255), 1)
    img = cv2.addWeighted(img, 0.4, layer, 0.6, 0) if hearts else img
    if active:  # pink glow + soft vignette
        pink = np.full_like(img, (200, 80, 255))
        img = cv2.addWeighted(img, 0.82, pink, 0.18, 0)
        img = cv2.addWeighted(img, 1.0, cv2.GaussianBlur(img, (0, 0), 15), 0.25, 0)
    return img


# --------------------------------------------------------------------------
# LIGHTNING
# --------------------------------------------------------------------------
def bolt(p1, p2, offset, depth=6):
    """Midpoint-displacement jagged line between p1 and p2."""
    pts = [np.array(p1, float), np.array(p2, float)]
    for _ in range(depth):
        new = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            mid = (a + b) / 2
            d = b - a
            n = np.array([-d[1], d[0]]) / (np.linalg.norm(d) + 1e-6)
            new += [mid + n * random.uniform(-offset, offset), b]
        pts = new
        offset /= 2
    return [tuple(p.astype(int)) for p in pts]


def draw_lightning(img, hand):
    h, w = img.shape[:2]
    tip = np.array(hand["lmList"][8][:2], float)
    base = np.array(hand["lmList"][5][:2], float)
    direction = tip - base
    direction /= (np.linalg.norm(direction) + 1e-6)

    glow = np.zeros_like(img)
    core = np.zeros_like(img)
    for _ in range(3):
        ang = random.uniform(-0.25, 0.25)
        c, s = math.cos(ang), math.sin(ang)
        d = np.array([direction[0] * c - direction[1] * s, direction[0] * s + direction[1] * c])
        end = tip + d * random.uniform(350, 900)
        pts = bolt(tip, end, offset=60)
        for a, b in zip(pts[:-1], pts[1:]):
            cv2.line(glow, a, b, (255, 120, 60), 9)
            cv2.line(core, a, b, (255, 255, 255), 2)
        for _ in range(3):  # little branches
            i = random.randint(2, len(pts) - 3)
            bend = np.array(pts[i], float) + d * 150 + np.random.uniform(-120, 120, 2)
            for a, b in zip(*(lambda p: (p[:-1], p[1:]))(bolt(pts[i], bend, 30, 4))):
                cv2.line(glow, a, b, (255, 120, 60), 5)
                cv2.line(core, a, b, (255, 255, 255), 1)
    glow = cv2.GaussianBlur(glow, (0, 0), 10)
    img = cv2.add(img, glow)
    img = cv2.add(img, core)
    if random.random() < 0.15:  # occasional screen flash
        img = cv2.addWeighted(img, 0.6, np.full_like(img, 255), 0.4, 0)
    return img


# --------------------------------------------------------------------------
# AVATAR MODE  (Earth / Water / Air / Fire) - battle version
#   Earth: fist                      -> EARTH BLAST  (throws a boulder)
#   Water: open palm, fingers apart  -> WATER BLAST   (shoots a water blast where you point)
#   Air:   open palm, fingers close  -> AIR BLAST    (fires a cutting wind blade)
#   Fire:  two fingers (index+middle) or OK sign -> FIRE BLAST (throws fireballs)
#   Lightning: point with index finger -> LIGHTNING   (chain lightning from your fingertip)
# A BIG BOSS appears every 10 kills.
# Every attack goes in the direction your hand is facing (wrist -> fingers),
# and hits the enemies that float around the screen.
# --------------------------------------------------------------------------
POWER_NAMES = {"earth": "EARTH BLAST", "water": "WATER BLAST",
               "air": "AIR BLAST", "fire": "FIRE BLAST", "lightning": "LIGHTNING"}
POWER_COLORS = {"earth": (70, 130, 190), "water": (255, 200, 60),
                "air": (255, 255, 230), "fire": (0, 150, 255), "lightning": (255, 170, 90)}  # BGR
ELEMENTS = ("earth", "water", "air", "fire", "lightning")

# ---- tuning knobs ----------------------------------------------------------
SPREAD_DEG = 12        # avg angle between neighbouring fingers. Above = Water, below = Air.
                       # Air read as Water? raise it. Water read as Air? lower it.
VOTE_FRAMES = 7        # a gesture must win this many of the last frames ...
VOTE_NEEDED = 4        # ... at least this many times, so it can't flicker.
AIM_ASSIST = 0.6       # 0 = off, 1 = snap to the enemy nearest to where you point
AIM_CONE_DEG = 22      # how close to an enemy you must point for aim assist to kick in
MAX_ENEMIES = 7
COOLDOWN = {"fire": 9, "air": 7, "earth": 16, "water": 8}      # frames between shots while held
SPEED = {"fire": 24, "air": 34, "earth": 19, "water": 27}
SIZE = {"fire": 24, "air": 46, "earth": 30, "water": 26}

# ---- MANA (every element has its own bar) ----------------------------------
MANA_MAX = 100.0
MANA_COST = {"fire": 8.0, "air": 5.0, "earth": 18.0, "water": 8.0}   # spent per shot
LIGHTNING_COST = 1.6      # spent every frame while you hold the lightning pose
MANA_REGEN = 0.5          # refilled per frame while you are NOT using that element
MANA_REGEN_DELAY = 25     # frames you must wait after casting before it starts refilling

# ---- PLAYER HEALTH / LIVES / ENEMY ATTACKS ---------------------------------
PLAYER_HP = 100.0
PLAYER_LIVES = 3
HIT_INVULN = 45           # frames of invincibility after you get hit
ENEMY_SHOT_DMG = 12.0     # damage of a normal enemy orb
BOSS_SHOT_DMG = 20.0      # damage of a boss orb
ENEMY_SHOT_SPEED = 12.5   # px per frame (lower = easier to dodge)
BOSS_SHOT_SPEED = 15.0
ENEMY_FIRE_RATE = (40, 80)     # frames between enemy attacks (min, max)
BOSS_FIRE_RATE = (28, 50)
CONTACT_DMG = 8.0         # enemy body touching your hand
BOSS_CONTACT_DMG = 15.0
DASH_DMG = 16.0           # charger body-slam
DASH_SPEED = 28.0         # px per frame while dashing
WIND_UP = 20              # charger wind-up frames (lower = less warning)
LASER_DMG = 20.0          # sniper / boss beam
RING_DMG = 8.0            # each orb of a ring / wall
BOMB_DMG = 18.0           # standing in a bomb blast
HOMING_DMG = 12.0         # homing orb
RAMP = 0.06               # enemies get faster / tougher with every kill (0 = off)
RAMP_CAP = 3.5            # ...up to this multiplier
BOSS_HEAL = 50.0          # HP you get back for defeating a boss

# ---- HANDS OUT OF VIEW PENALTY ---------------------------------------------
NO_HAND_GRACE = 25        # frames with no hands before HP starts draining (~0.8 s)
NO_HAND_DRAIN = 0.6       # HP lost per frame after that (~18 HP/sec at 30 fps)
EDGE_MARGIN = 30          # a palm this close to the screen edge counts as "out of scope"

# ---- AVATAR STATE (hands together) ----------------------------------------
AVATAR_KILLS = 10         # kills needed to unlock it (and again after every use)
AVATAR_ENTER = 1.6        # hands closer than this (in "hand sizes") = together
AVATAR_EXIT = 2.6         # hands further apart than this = state ends
AVATAR_HOLD = 5           # frames you must hold them together to trigger it
AVATAR_DURATION = 180     # frames the state lasts (~6 s at 30 fps). Short on purpose!
AVATAR_POWER = 3.0        # damage / size multiplier for every projectile (lower = weaker, e.g. 2.5)

clock = {"t": 0}
shake_level = 0.0
enemies, projectiles, sparks = [], [], []
enemy_shots = []          # dark orbs the enemies throw at your hands
lasers = []               # sniper / boss beams (warning line, then a hit)
bombs = []                # delayed explosions on the ground (warning circle, then boom)
hand_zones = []           # where your hands are this frame: {"pos", "r"}
cooldowns = {}
score = {"kills": 0}
boss_state = {"since": 0, "pending": False, "text": "", "t": 0, "col": (60, 60, 255)}


def banner(text, frames, col=(60, 60, 255)):
    boss_state["text"], boss_state["t"], boss_state["col"] = text, frames, col
BOSS_EVERY = 10
BOSS_HP = 1000.0
enemies_on = {"v": True}
avatar = {"on": False, "count": 0, "lost": 0, "center": None, "dir": None, "charge": 0, "time": 0,
          "cd": {}, "rings": [], "shock": 0}
player = {"hp": PLAYER_HP, "lives": PLAYER_LIVES, "inv": 0, "flash": 0, "over": False,
          "missing": 0, "started": False}
mana = {el: MANA_MAX for el in ELEMENTS}
mana_wait = {el: 0 for el in ELEMENTS}
nomana = {el: 0 for el in ELEMENTS}      # frames the "out of mana" warning blinks


def _d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def add_glow(img, layer, sigma, crisp=False):
    """Additive glow, blurred at 1/4 resolution so it stays fast."""
    h, w = img.shape[:2]
    small = cv2.resize(layer, (max(1, w // 4), max(1, h // 4)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), max(0.5, sigma / 4))
    img = cv2.add(img, cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR))
    return cv2.add(img, layer) if crisp else img


# ---- mana ------------------------------------------------------------------
def can_cast(el):
    return mana[el] >= (LIGHTNING_COST if el == "lightning" else MANA_COST[el])


def spend(el, amount):
    """Spend mana if there is enough. Casting also pauses that element's refill."""
    if mana[el] >= amount:
        mana[el] -= amount
        mana_wait[el] = MANA_REGEN_DELAY
        return True
    nomana[el] = 8
    return False


def regen_mana():
    for el in ELEMENTS:
        nomana[el] = max(0, nomana[el] - 1)
        if mana_wait[el] > 0:
            mana_wait[el] -= 1
        else:
            mana[el] = min(MANA_MAX, mana[el] + MANA_REGEN)


# ---- player health ---------------------------------------------------------
def _lose_hp(dmg):
    """Subtract HP, handle life loss / game over."""
    player["hp"] -= dmg
    if player["hp"] <= 0:
        player["lives"] -= 1
        enemy_shots.clear()
        lasers.clear()
        bombs.clear()
        if player["lives"] <= 0:
            player["hp"], player["over"] = 0.0, True
        else:
            player["hp"], player["inv"], player["missing"] = PLAYER_HP, 120, 0
            banner("LIFE LOST!", 90)


def hurt_player(dmg):
    global shake_level
    if player["over"] or player["inv"] > 0 or avatar["on"]:    # Avatar State = invincible
        return
    player["inv"] = HIT_INVULN
    player["flash"] = 10
    shake_level = max(shake_level, 0.6)
    _lose_hp(dmg)


def check_hands_present(w, h):
    """No hands on screen (or only at the very edge) -> HP drains after a short grace period."""
    visible = [z for z in hand_zones
               if EDGE_MARGIN < z["pos"][0] < w - EDGE_MARGIN and EDGE_MARGIN < z["pos"][1] < h - EDGE_MARGIN]
    if visible:
        player["started"] = True                 # no penalty before your first hand appears
    if not player["started"] or player["over"] or avatar["on"] or not enemies_on["v"]:
        player["missing"] = 0
        return
    if visible:
        player["missing"] = max(0, player["missing"] - 3)
        return
    player["missing"] += 1
    if player["missing"] > NO_HAND_GRACE:
        _lose_hp(NO_HAND_DRAIN)                  # ignores hit-invulnerability on purpose
        player["flash"] = max(player["flash"], 2)


# ---- gesture accuracy ------------------------------------------------------
def finger_states(hd):
    """[thumb, index, middle, ring, pinky] -> 1 if extended. Works at any hand rotation
    (it compares distances to the wrist instead of assuming the hand is upright)."""
    lm = hd["lmList"]
    size = _d(lm[0], lm[9]) + 1e-6
    out = [1 if _d(lm[4], lm[9]) > 0.95 * size else 0]
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        dt, dp = _d(lm[tip], lm[0]), _d(lm[pip], lm[0])
        out.append(1 if (dt > dp * 1.12 and dt > 1.3 * size) else 0)
    return out


def spread_deg(lm):
    """Average angle between neighbouring fingers (scale and rotation independent)."""
    vecs = [(lm[t][0] - lm[m][0], lm[t][1] - lm[m][1]) for m, t in ((5, 8), (9, 12), (13, 16), (17, 20))]
    angs = []
    for a, b in zip(vecs[:-1], vecs[1:]):
        c = (a[0] * b[0] + a[1] * b[1]) / (math.hypot(*a) * math.hypot(*b) + 1e-6)
        angs.append(math.degrees(math.acos(max(-1.0, min(1.0, c)))))
    return sum(angs) / len(angs)


def classify_avatar(hd, fingers):
    lm = hd["lmList"]
    size = _d(lm[0], lm[9]) + 1e-6
    _, index, middle, ring, pinky = fingers
    # FIRE: OK sign (thumb touches index, other three fingers up)
    if _d(lm[4], lm[8]) < 0.4 * size and middle and ring and pinky:
        return "fire"
    # FIRE: two fingers (index + middle) pointing, ring and pinky folded
    if index and middle and not (ring or pinky):
        return "fire"
    # EARTH: fist (thumbs up counts as a fist now)
    if not (index or middle or ring or pinky):
        return "earth"
    # LIGHTNING: pointing with the index finger only
    if index and not (middle or ring or pinky):
        return "lightning"
    # WATER / AIR: open palm, decided by finger spread
    if index and middle and ring and pinky:
        return "water" if spread_deg(lm) > SPREAD_DEG else "air"
    return None


def enrich(hd, st, key):
    """Adds a smoothed 'facing' direction, palm centre and hand size to a hand."""
    lm = hd["lmList"]
    size = _d(lm[0], lm[9]) + 1e-6
    mid_up = _d(lm[12], lm[0]) > 1.3 * size
    idx_up = _d(lm[8], lm[0]) > 1.3 * size
    tip = lm[12] if mid_up else (lm[8] if idx_up else lm[9])      # pointing -> aim along the index finger
    v = np.array([tip[0] - lm[0][0], tip[1] - lm[0][1]], float)
    v /= np.linalg.norm(v) + 1e-6
    if st["dir"] is not None:               # smooth out jitter
        v = st["dir"] * 0.6 + v * 0.4
        v /= np.linalg.norm(v) + 1e-6
    st["dir"] = v
    hd["dir"], hd["size"], hd["key"] = v, size, key
    hd["palm"] = np.mean([[lm[i][0], lm[i][1]] for i in (0, 5, 9, 13, 17)], axis=0)


# ---- enemies ---------------------------------------------------------------
def level():
    """Difficulty multiplier: grows with every kill."""
    return min(RAMP_CAP, 1 + RAMP * score["kills"])


# every kind: body colour, attacks it uses, kills needed before it shows up, spawn weight, hp multiplier, size
ENEMY_KINDS = {
    "shooter": {"body": (70, 28, 80),    "attacks": ("orb", "orb", "spread"),   "unlock": 0,  "w": 4, "hp": 1.0, "r": (34, 48)},
    "charger": {"body": (30, 70, 170),   "attacks": ("dash", "dash", "orb"),    "unlock": 3,  "w": 2, "hp": 1.0, "r": (34, 48)},
    "sniper":  {"body": (60, 120, 50),   "attacks": ("laser", "laser", "orb"),  "unlock": 3,  "w": 2, "hp": 1.0, "r": (34, 48)},
    "gunner":  {"body": (110, 110, 120), "attacks": ("burst", "wall", "orb"),   "unlock": 5,  "w": 2, "hp": 1.6, "r": (46, 56)},
    "bomber":  {"body": (20, 110, 200),  "attacks": ("bomb", "bomb", "orb"),    "unlock": 7,  "w": 2, "hp": 1.0, "r": (34, 48)},
    "caster":  {"body": (140, 70, 40),   "attacks": ("ring", "homing", "homing"), "unlock": 8, "w": 2, "hp": 1.0, "r": (34, 48)},
    "spinner": {"body": (150, 40, 150),  "attacks": ("spiral", "ring", "spiral"), "unlock": 11, "w": 2, "hp": 1.0, "r": (34, 48)},
    "sweeper": {"body": (160, 150, 30),  "attacks": ("sweep", "cross", "laser"),  "unlock": 14, "w": 2, "hp": 1.1, "r": (36, 50)},
    "blinker": {"body": (190, 170, 170), "attacks": ("blink", "blink", "burst"),  "unlock": 17, "w": 2, "hp": 0.8, "r": (30, 42)},
}
BOSS_ATTACKS = ("spread", "ring", "homing", "laser", "summon", "sweep", "cross", "bomb", "spiral", "curtain", "burst")


def spawn_enemy(w, h, at=None, kind=None):
    k = score["kills"]
    if kind is None:
        avail = [n for n, v in ENEMY_KINDS.items() if v["unlock"] <= k]
        kind = random.choices(avail, weights=[ENEMY_KINDS[n]["w"] for n in avail])[0]
    info = ENEMY_KINDS[kind]
    hp = 100.0 * info["hp"] * (1 + min(1.0, k / 50))             # tougher as you kill more
    x, y = at if at else (random.uniform(0.15 * w, 0.85 * w), random.uniform(0.12 * h, 0.55 * h))
    enemies.append({"x": float(x), "y": float(y),
                    "vx": random.uniform(-1.5, 1.5), "vy": random.uniform(-1, 1),
                    "kx": 0.0, "ky": 0.0, "hp": hp, "max": hp, "kind": kind,
                    "r": random.randint(*info["r"]), "flash": 0, "ph": random.uniform(0, 6.28),
                    "atk": random.randint(*ENEMY_FIRE_RATE)})


def spawn_boss(w, h):
    enemies.append({"x": w / 2, "y": h * 0.32, "vx": 1.2, "vy": 0.4, "kx": 0.0, "ky": 0.0,
                    "hp": BOSS_HP, "max": BOSS_HP, "r": 105, "flash": 0, "ph": 0.0,
                    "boss": True, "kind": "boss", "kb": 0.12, "atk": 80})
    banner("BOSS INCOMING!", 110)


def boss_alive():
    return any(e.get("boss") for e in enemies)


def update_enemies(w, h):
    for e in enemies:
        boss = e.get("boss")
        if e.get("wind", 0) > 0:                       # charger is winding up: stands still, red lane shown
            e["wind"] -= 1
            if e["wind"] == 0:
                e["dashing"] = 16
            e["flash"] = max(0, e["flash"] - 1)
            continue
        if e.get("dashing", 0) > 0:                    # charger is dashing along the lane
            e["dashing"] -= 1
            m = e["r"] + 10
            e["x"] = min(max(e["x"] + e["cdir"][0] * DASH_SPEED, m), w - m)
            e["y"] = min(max(e["y"] + e["cdir"][1] * DASH_SPEED, m), h - m)
            e["flash"] = max(0, e["flash"] - 1)
            continue
        mult = 1.8 if boss and e["hp"] < e["max"] * 0.5 else 1.0      # boss enrages at half health
        mult *= 1 + 0.15 * (level() - 1)                              # everyone speeds up with your kills
        sc = 0.6 if boss else 1.0
        e["ph"] += 0.12
        if random.random() < 0.03:
            e["vx"], e["vy"] = random.uniform(-2, 2) * sc, random.uniform(-1.5, 1.5) * sc
        e["x"] += (e["vx"] + e["kx"]) * mult
        e["y"] += (e["vy"] + math.sin(e["ph"]) * 0.8 + e["ky"]) * mult
        e["kx"] *= 0.85
        e["ky"] *= 0.85
        e["flash"] = max(0, e["flash"] - 1)
        m = e["r"] + 10
        if not m < e["x"] < w - m:
            e["vx"] *= -1
            e["x"] = min(max(e["x"], m), w - m)
        if not m < e["y"] < h - m:
            e["vy"] *= -1
            e["y"] = min(max(e["y"], m), h - m)


def _alive(lst, obj):
    return any(o is obj for o in lst)


def _rm(lst, obj):
    for i, o in enumerate(lst):
        if o is obj:
            del lst[i]
            return


def enemy_shoot(e, d, degs, spd, dmg, r, home=False, life=240):
    """Fire one orb per angle in `degs` (rotated off direction d)."""
    for deg in degs:
        dd = rot(d, deg)
        enemy_shots.append({"x": e["x"], "y": e["y"], "vx": dd[0] * spd, "vy": dd[1] * spd, "spd": spd,
                            "r": r, "dmg": dmg, "life": life, "home": home, "ph": random.uniform(0, 6.28)})


def fixed_beam(origin, direction, warn=40, fire=14):
    """A beam that is not attached to an enemy (cross / curtain)."""
    lasers.append({"e": None, "o": np.array(origin, float), "dir": np.array(direction, float),
                   "t": 0, "warn": warn, "fire": fire, "off": 0, "w": 1.0})


def do_attack(e, attack, w, h):
    boss = e.get("boss")
    enraged = boss and e["hp"] < e["max"] * 0.5
    lv = level()
    base = (BOSS_SHOT_SPEED if boss else ENEMY_SHOT_SPEED) * min(1.35, 1 + 0.2 * (lv - 1))
    dmg = BOSS_SHOT_DMG if boss else ENEMY_SHOT_DMG
    r = 20 if boss else 13
    # keep the screen fair: never stack the same big pattern on top of itself
    if attack in ("laser", "sweep") and any(L["e"] is e for L in lasers):
        attack = "orb"
    elif attack in ("cross", "curtain") and any(L["e"] is None for L in lasers):
        attack = "orb"
    elif attack == "spiral" and e.get("spiral"):
        attack = "orb"
    elif attack == "wall" and any(s.get("wall") for s in enemy_shots):
        attack = "orb"
    elif attack == "bomb" and len(bombs) > 5:
        attack = "orb"
    tgt = random.choice(hand_zones)["pos"]
    v = tgt - np.array([e["x"], e["y"]], float)
    d = v / (np.linalg.norm(v) + 1e-6)

    if attack == "orb":                                  # single aimed orb
        enemy_shoot(e, d, (0,), base, dmg, r)
    elif attack == "spread":                             # fan of orbs
        enemy_shoot(e, d, (-28, -14, 0, 14, 28) if boss else (-18, 0, 18), base * 0.9, dmg, r)
    elif attack == "burst":                              # 5 fast orbs in a row, each re-aimed at your hand
        enemy_shoot(e, d, (0,), base * 1.1, dmg, r)
        e.setdefault("queue", []).extend([[5, "orb"], [10, "orb"], [15, "orb"], [20, "orb"]])
    elif attack == "ring":                               # ring of orbs in every direction, find the gap
        n = 16 if boss else 10
        off = random.uniform(0, 360.0 / n)
        enemy_shoot(e, np.array([1.0, 0.0]), [off + k * 360.0 / n for k in range(n)], base * 0.65,
                    RING_DMG * (1.4 if boss else 1.0), max(9, r - 3))
    elif attack == "homing":                             # slow orbs that curve after your hand (shoot them!)
        enemy_shoot(e, d, (-25, 25) if boss else (0,), base * 0.55, HOMING_DMG, r + 2, home=True, life=320)
    elif attack == "spiral":                             # a long spinning stream of orbs
        e["spiral"] = {"left": 72 if boss else 48, "ang": math.atan2(d[1], d[0]), "dir": random.choice((-1, 1)),
                       "arms": 2 if boss else 1, "spd": base * 0.7, "dmg": dmg * 0.8, "r": max(9, r - 3)}
    elif attack == "wall":                               # a wall of orbs sweeps across the screen, one gap
        side = random.choice(("top", "bottom", "left", "right"))
        horiz = side in ("left", "right")
        length = h if horiz else w
        n = int(length / 64) + 2
        gap_c = (tgt[1] if horiz else tgt[0]) + random.uniform(-120, 120)
        spd = base * 0.5
        for k in range(n):
            pos = k * length / (n - 1)
            if abs(pos - gap_c) < 150:                   # the gap (300 px wide)
                continue
            x, y, vx, vy = {"top": (pos, -20, 0, spd), "bottom": (pos, h + 20, 0, -spd),
                            "left": (-20, pos, spd, 0), "right": (w + 20, pos, -spd, 0)}[side]
            enemy_shots.append({"x": float(x), "y": float(y), "vx": vx, "vy": vy, "spd": spd, "r": 12,
                                "dmg": RING_DMG, "life": 400, "home": False, "wall": True,
                                "ph": random.uniform(0, 6.28)})
    elif attack == "laser":                              # tracking beam: warning line -> beam
        for off in ((-20, 0, 20) if enraged else (-12, 12)) if boss else (0,):
            lasers.append({"e": e, "tgt": tgt.copy(), "off": off, "t": 0, "warn": 36, "fire": 14})
    elif attack == "sweep":                              # a thick beam that swings across the screen
        for off, spin in ((-45, 2.5), (45, -2.5)) if boss else ((random.choice((-45, 45)), 0),):
            if not boss:
                spin = -off / 18.0                       # swings 90 degrees towards the other side
            lasers.append({"e": e, "tgt": tgt.copy(), "off": off, "spin": spin, "w": 1.2,
                           "t": 0, "warn": 30, "fire": 36})
    elif attack == "cross":                              # a vertical + horizontal beam through where your hand is NOW
        pts = [tgt] + ([np.array([random.uniform(0.1 * w, 0.9 * w), random.uniform(0.1 * h, 0.9 * h)])] if boss else [])
        for q in pts:
            fixed_beam((q[0], -40.0), (0.0, 1.0))
            fixed_beam((-40.0, q[1]), (1.0, 0.0))
    elif attack == "curtain":                            # parallel beams across the whole screen, hide in a gap
        vertical = random.random() < 0.6
        sp = 320 if vertical else 300
        pos = (tgt[0] if vertical else tgt[1]) % sp
        limit = w if vertical else h
        while pos < limit:
            fixed_beam((pos, -40.0) if vertical else (-40.0, pos), (0.0, 1.0) if vertical else (1.0, 0.0),
                       warn=45, fire=18)
            pos += sp
    elif attack == "bomb":                               # warning circles; they explode a moment later
        for k in range(5 if boss else 3):
            if k == 0:
                bx, by = tgt
            else:
                a = random.uniform(0, 2 * math.pi)
                dist = random.uniform(150, 300)
                bx, by = tgt[0] + math.cos(a) * dist, tgt[1] + math.sin(a) * dist
            bombs.append({"x": min(max(bx, 40), w - 40), "y": min(max(by, 40), h - 40),
                          "t": -k * 6, "fuse": 32, "r": 125 if boss else 105})
    elif attack == "blink":                              # teleports next to your hands, then fires a fan
        burst(e["x"], e["y"], (255, 210, 210), 25, 10)
        a = random.uniform(0, 2 * math.pi)
        dist = random.uniform(280, 450)
        e["x"] = min(max(tgt[0] + math.cos(a) * dist, 60), w - 60)
        e["y"] = min(max(tgt[1] + math.sin(a) * dist, 60), h * 0.7)
        e["kx"] = e["ky"] = 0.0
        burst(e["x"], e["y"], (255, 210, 210), 25, 10)
        e.setdefault("queue", []).append([18, "spread"])
    elif attack == "dash":                               # wind up, then slam into your hand
        e["cdir"], e["wind"] = d, WIND_UP
    elif attack == "summon":                             # boss calls minions
        for _ in range(2):
            if sum(1 for x in enemies if not x.get("boss")) < 4:
                spawn_enemy(w, h, at=(e["x"] + random.uniform(-90, 90), e["y"] + random.uniform(60, 120)))
        burst(e["x"], e["y"], (200, 60, 120), 30, 12)
    burst(e["x"], e["y"], (60, 60, 255), 10, 8, life=(8, 14), size=(3, 6))


def update_enemy_attacks(w, h):
    """Every enemy kind has its own attacks. They attack faster as your kill count grows."""
    if player["over"] or avatar["on"]:
        for e in enemies:
            e["atk"] = max(e["atk"], 40)
            e["queue"] = []
            e.pop("spiral", None)
        return
    for e in enemies:                           # queued follow-up shots and running spirals
        q = e.get("queue")
        if q:
            keep = []
            for it in q:
                it[0] -= 1
                if it[0] <= 0:
                    if hand_zones:
                        do_attack(e, it[1], w, h)
                else:
                    keep.append(it)
            e["queue"] = keep
        sp = e.get("spiral")
        if sp:
            sp["left"] -= 1
            if sp["left"] % 4 == 0:
                for k in range(sp["arms"]):
                    a = sp["ang"] + k * math.pi
                    enemy_shoot(e, np.array([math.cos(a), math.sin(a)]), (0,), sp["spd"], sp["dmg"], sp["r"])
                sp["ang"] += sp["dir"] * 0.34
            if sp["left"] <= 0:
                e.pop("spiral", None)
    if not hand_zones:
        for e in enemies:                       # no hands on screen: hold fire
            e["atk"] = max(e["atk"], 40)
        return
    lv = level()
    for e in enemies:
        if e.get("wind", 0) > 0 or e.get("dashing", 0) > 0:
            continue
        boss = e.get("boss")
        enraged = boss and e["hp"] < e["max"] * 0.5
        e["atk"] -= (1.5 if enraged else 1) * (1 + 0.25 * (lv - 1))
        if e["atk"] > 0:
            continue
        pool = BOSS_ATTACKS if boss else ENEMY_KINDS[e["kind"]]["attacks"]
        do_attack(e, random.choice(pool), w, h)
        if enraged:                             # berserk boss double-attacks
            do_attack(e, random.choice(("spread", "homing", "orb", "burst", "bomb")), w, h)
        e["atk"] = random.randint(*(BOSS_FIRE_RATE if boss else ENEMY_FIRE_RATE))


def enemy_contact():
    """Enemy bodies hurt you if they touch your hand (dashing chargers hurt more)."""
    if player["over"] or avatar["on"]:
        return
    for e in enemies:
        for z in hand_zones:
            dx, dy = e["x"] - z["pos"][0], e["y"] - z["pos"][1]
            dist = math.hypot(dx, dy)
            if dist < e["r"] + z["r"] * 0.8:
                hurt_player(DASH_DMG if e.get("dashing") else (BOSS_CONTACT_DMG if e.get("boss") else CONTACT_DMG))
                kb = e.get("kb", 1.0)
                e["kx"] += dx / (dist + 1e-6) * 12 * kb
                e["ky"] += dy / (dist + 1e-6) * 12 * kb
                if e.get("dashing"):
                    e["dashing"] = 0            # the slam ends on impact
                break


def draw_enemy_shots(img, glow):
    h, w = img.shape[:2]
    for s in enemy_shots[:]:
        if not _alive(enemy_shots, s):          # wiped by a life loss earlier this frame
            continue
        if s["home"] and hand_zones:            # homing orbs curve toward the nearest hand
            pos = np.array([s["x"], s["y"]])
            z = min(hand_zones, key=lambda zz: np.linalg.norm(zz["pos"] - pos))
            want = z["pos"] - pos
            want /= (np.linalg.norm(want) + 1e-6)
            cur = np.array([s["vx"], s["vy"]])
            cur /= (np.linalg.norm(cur) + 1e-6)
            nd = cur * 0.94 + want * 0.06
            nd /= (np.linalg.norm(nd) + 1e-6)
            s["vx"], s["vy"] = nd[0] * s["spd"], nd[1] * s["spd"]
        s["x"] += s["vx"]
        s["y"] += s["vy"]
        s["life"] -= 1
        s["ph"] += 0.4
        if s["life"] <= 0 or not (-60 < s["x"] < w + 60 and -60 < s["y"] < h + 60):
            _rm(enemy_shots, s)
            continue
        killed = False
        for p in projectiles:                    # your blasts can shoot the orbs down
            if math.hypot(p["x"] - s["x"], p["y"] - s["y"]) < s["r"] + p["size"] * 0.6:
                burst(s["x"], s["y"], (80, 80, 255), 14, 8, life=(8, 16), size=(2, 5))
                killed = True
                break
        if not killed:
            for z in hand_zones:                 # ...or they hit your hand
                if math.hypot(z["pos"][0] - s["x"], z["pos"][1] - s["y"]) < z["r"] + s["r"]:
                    hurt_player(s["dmg"])
                    burst(s["x"], s["y"], (60, 60, 255), 25, 11, size=(3, 8))
                    killed = True
                    break
        if killed:
            _rm(enemy_shots, s)
            continue
        c = (int(s["x"]), int(s["y"]))
        r = max(4, int(s["r"] * (1 + 0.12 * math.sin(s["ph"]))))
        if s["home"]:                            # homing = orange, so you can tell them apart
            cols = ((0, 90, 255), (0, 40, 160), (0, 150, 255), (200, 240, 255))
        else:
            cols = ((40, 20, 200), (60, 20, 150), (80, 80, 255), (220, 230, 255))
        cv2.circle(glow, c, int(r * 2.2), cols[0], -1)
        cv2.circle(img, c, r, cols[1], -1)
        cv2.circle(img, c, int(r * 0.65), cols[2], -1)
        cv2.circle(img, c, max(2, int(r * 0.3)), cols[3], -1)
    return img


def draw_lasers(img, glow):
    """Beams: thin red warning line that tightens (and, for enemy beams, locks on), then a short hit.
    Sweep beams swing while firing; cross / curtain beams are fixed in place."""
    global shake_level
    for L in lasers[:]:
        if not _alive(lasers, L):
            continue
        e = L["e"]
        if (e is not None and not _alive(enemies, e)) or player["over"] or avatar["on"]:
            _rm(lasers, L)
            continue
        L["t"] += 1
        if e is not None:
            o = np.array([e["x"], e["y"]], float)
            if L["t"] < L["warn"] - 15 and hand_zones:        # keeps tracking until the last 15 frames
                L["tgt"] = min((z["pos"] for z in hand_zones), key=lambda q: np.linalg.norm(q - L["tgt"])).copy()
            d = L["tgt"] - o
            d = d / (np.linalg.norm(d) + 1e-6)
            d = rot(d, L["off"] + L.get("spin", 0.0) * max(0, L["t"] - L["warn"]))
        else:
            o, d = L["o"], L["dir"]
        wd = L.get("w", 1.0)
        end = o + d * 2200
        a, b = (int(o[0]), int(o[1])), (int(end[0]), int(end[1]))
        if L["t"] < L["warn"]:
            f = L["t"] / L["warn"]
            cv2.line(img, a, b, (60, 60, int(120 + 135 * f)), 1 if f < 0.7 else 3, cv2.LINE_AA)
        elif L["t"] < L["warn"] + L["fire"]:
            if L["t"] == L["warn"]:
                shake_level = max(shake_level, 0.5)
            cv2.line(glow, a, b, (60, 40, 255), int(34 * wd))
            cv2.line(img, a, b, (120, 120, 255), int(14 * wd), cv2.LINE_AA)
            cv2.line(img, a, b, (255, 255, 255), max(2, int(6 * wd)), cv2.LINE_AA)
            for z in hand_zones:
                if seg_dist(z["pos"][0], z["pos"][1], o, end) < z["r"] * 0.8 + 10 * wd:
                    hurt_player(LASER_DMG)
        else:
            _rm(lasers, L)
    return img


def draw_bombs(img, glow):
    """A red circle fills up on the ground, then it explodes. Get your hand out of the circle!"""
    global shake_level
    for b in bombs[:]:
        if not _alive(bombs, b):
            continue
        if player["over"] or avatar["on"]:
            _rm(bombs, b)
            continue
        b["t"] += 1
        if b["t"] < 0:
            continue
        c = (int(b["x"]), int(b["y"]))
        if b["t"] < b["fuse"]:
            f = b["t"] / b["fuse"]
            cv2.circle(glow, c, max(1, int(b["r"] * f)), (0, 0, 110), -1)
            cv2.circle(img, c, b["r"], (60, 60, 255), 2, cv2.LINE_AA)
            cv2.circle(img, c, max(2, int(b["r"] * f)), (80, 80, 255), 1, cv2.LINE_AA)
        elif b["t"] < b["fuse"] + 8:
            if b["t"] == b["fuse"]:
                for z in hand_zones:
                    if math.hypot(z["pos"][0] - b["x"], z["pos"][1] - b["y"]) < b["r"] + z["r"] * 0.4:
                        hurt_player(BOMB_DMG)
                burst(b["x"], b["y"], (0, 170, 255), 50, 15, size=(4, 10))
                burst(b["x"], b["y"], (255, 255, 255), 20, 10)
                shake_level = max(shake_level, 0.6)
            k = (b["t"] - b["fuse"]) / 8
            cv2.circle(glow, c, int(b["r"] * (1 + 0.25 * k)), (0, 170, 255), -1)
            cv2.circle(img, c, max(2, int(b["r"] * 0.8 * (1 - 0.3 * k))), (255, 255, 255), -1)
        else:
            _rm(bombs, b)
    return img


def draw_enemies(img, glow):
    for e in enemies:
        enraged = e.get("boss") and e["hp"] < e["max"] * 0.5
        cv2.circle(glow, (int(e["x"]), int(e["y"])), int(e["r"] * (1.7 if e.get("boss") else 1.5)),
                   (15, 30, 150) if enraged else ((30, 8, 90) if e.get("boss") else (20, 8, 70)), -1)
    for e in enemies:
        x, y, r = e["x"], e["y"], e["r"]
        boss = e.get("boss")
        spikes = 24 if boss else 16
        pts = []
        for k in range(spikes):                              # spiky body
            a = e["ph"] * 0.3 + k * 2 * math.pi / spikes
            rad = r * (1.0 if k % 2 == 0 else (0.8 if boss else 0.72))
            pts.append((x + math.cos(a) * rad, y + math.sin(a) * rad))
        pts = np.int32(pts)
        enraged = boss and e["hp"] < e["max"] * 0.5
        body = (40, 10, 140) if enraged else ((55, 15, 110) if boss else ENEMY_KINDS.get(e.get("kind"), ENEMY_KINDS["shooter"])["body"])
        cv2.fillPoly(img, [pts], (255, 255, 255) if e["flash"] else body)
        cv2.polylines(img, [pts], True, (20, 10, 30), 3 if boss else 2)
        if boss:                                             # horns
            for sx in (-1, 1):
                horn = np.int32([(x + sx * r * 0.35, y - r * 0.85), (x + sx * r * 0.95, y - r * 1.55),
                                 (x + sx * r * 0.75, y - r * 0.6)])
                cv2.fillPoly(img, [horn], (30, 20, 70))
                cv2.polylines(img, [horn], True, (20, 10, 30), 2)
            eyes = [(-0.38, -0.12, 0.2), (0.38, -0.12, 0.2), (0.0, -0.38, 0.14)]
        else:
            eyes = [(-0.35, -0.15, 0.17), (0.35, -0.15, 0.17)]
        for ex, ey, er in eyes:                              # glowing eyes
            c = (int(x + ex * r), int(y + ey * r))
            cv2.circle(img, c, max(3, int(r * er)), (0, 200, 255) if boss else (0, 0, 255), -1)
            cv2.circle(img, c, max(1, int(r * er * 0.4)), (200, 230, 255), -1)
        cv2.line(img, (int(x - r * 0.3), int(y + r * 0.3)), (int(x + r * 0.3), int(y + r * 0.3)), (20, 10, 30), 4 if boss else 3)
        if e.get("wind", 0) > 0:                             # charger telegraph: a red lane toward your hand
            tip = (int(x + e["cdir"][0] * 1400), int(y + e["cdir"][1] * 1400))
            cv2.line(img, (int(x), int(y)), tip, (60, 60, 255), 2 + (WIND_UP - e["wind"]) // 6, cv2.LINE_AA)
        if e["atk"] < 25 and hand_zones and not player["over"] and not avatar["on"] \
                and not e.get("wind") and not e.get("dashing"):
            # attack warning: a red ring shrinks onto the enemy right before it fires
            ring = int(r * (1.9 - 0.7 * e["atk"] / 25))
            cv2.circle(img, (int(x), int(y)), ring, (60, 60, 255), 2, cv2.LINE_AA)
        if boss:                                             # big health bar across the top
            W = img.shape[1]
            x0, x1, y0 = int(W * 0.25), int(W * 0.75), 62
            cv2.rectangle(img, (x0 - 3, y0 - 3), (x1 + 3, y0 + 21), (0, 0, 0), -1)
            cv2.rectangle(img, (x0, y0), (x1, y0 + 18), (40, 40, 40), -1)
            frac = max(0, e["hp"]) / e["max"]
            cv2.rectangle(img, (x0, y0), (x0 + int((x1 - x0) * frac), y0 + 18),
                          (0, 60, 255) if enraged else (40, 40, 230), -1)
            cv2.putText(img, "SHADOW LORD", (x0, y0 - 10), cv2.FONT_HERSHEY_DUPLEX, 0.8,
                        (255, 255, 255), 2, cv2.LINE_AA)
        else:
            bw = int(r * 1.6)                                # small health bar
            x0, y0 = int(x - bw / 2), int(y - r - 18)
            cv2.rectangle(img, (x0, y0), (x0 + bw, y0 + 7), (30, 30, 30), -1)
            cv2.rectangle(img, (x0, y0), (x0 + int(bw * max(0, e["hp"]) / e["max"]), y0 + 7), (60, 220, 60), -1)
            cv2.putText(img, e.get("kind", "").upper(), (x0, y0 - 4), cv2.FONT_HERSHEY_PLAIN, 0.9,
                        (255, 255, 255), 1, cv2.LINE_AA)
    return img


def burst(x, y, col, n=20, speed=10, life=(15, 30), size=(3, 8), gravity=0.0):
    for _ in range(n):
        a, sp, l = random.uniform(0, 2 * math.pi), random.uniform(speed * 0.3, speed), random.randint(*life)
        sparks.append({"x": x, "y": y, "vx": math.cos(a) * sp, "vy": math.sin(a) * sp, "life": l, "max": l,
                       "r": random.randint(*size), "col": col, "g": gravity})


def draw_sparks(img, glow):
    for s in sparks[:]:
        s["x"] += s["vx"]
        s["y"] += s["vy"]
        s["vy"] += s["g"]
        s["vx"] *= 0.97
        s["life"] -= 1
        if s["life"] <= 0:
            sparks.remove(s)
            continue
        t = s["life"] / s["max"]
        col = tuple(int(c * (0.35 + 0.65 * t)) for c in s["col"])
        c, r = (int(s["x"]), int(s["y"])), max(1, int(s["r"] * (0.4 + 0.6 * t)))
        cv2.circle(img, c, r, col, -1)
        cv2.circle(glow, c, r * 2, col, -1)
    return img


def add_avatar_charge(n):
    """Kills fill the Avatar State meter (not while the state is already running)."""
    if not avatar["on"]:
        avatar["charge"] = min(AVATAR_KILLS, avatar["charge"] + n)


def damage_enemy(e, dmg, d, knock, col):
    global shake_level
    kb = e.get("kb", 1.0)
    e["hp"] -= dmg
    e["flash"] = 3
    e["kx"] += d[0] * knock * kb
    e["ky"] += d[1] * knock * kb
    if e["hp"] <= 0 and e in enemies:
        enemies.remove(e)
        if e.get("boss"):
            score["kills"] += 5
            add_avatar_charge(5)
            if not player["over"]:
                player["hp"] = min(PLAYER_HP, player["hp"] + BOSS_HEAL)
            enemy_shots.clear()
            banner("BOSS DEFEATED!", 130, (80, 230, 255))
            shake_level = 1.0
            burst(e["x"], e["y"], col, 160, 24, life=(25, 50), size=(5, 14))
            burst(e["x"], e["y"], (255, 255, 255), 80, 18, life=(20, 40))
            burst(e["x"], e["y"], (0, 160, 255), 80, 14, life=(25, 45), size=(6, 12))
        else:
            score["kills"] += 1
            add_avatar_charge(1)
            boss_state["since"] += 1
            if boss_state["since"] >= BOSS_EVERY:
                boss_state["pending"], boss_state["since"] = True, 0
            burst(e["x"], e["y"], col, 60, 16, size=(4, 10))
            burst(e["x"], e["y"], (255, 255, 255), 25, 12)


def aim(origin, d):
    """Aim assist: if an enemy is near where you're pointing, bend the shot toward it."""
    best, best_cos = None, math.cos(math.radians(AIM_CONE_DEG))
    for e in enemies:
        v = np.array([e["x"] - origin[0], e["y"] - origin[1]])
        dist = np.linalg.norm(v)
        if dist < 1:
            continue
        c = float(np.dot(v / dist, d))
        if c > best_cos:
            best_cos, best = c, v / dist
    if best is None or AIM_ASSIST <= 0:
        return d
    nd = d * (1 - AIM_ASSIST) + best * AIM_ASSIST
    return nd / (np.linalg.norm(nd) + 1e-6)


# ---- projectiles (fire / air / earth / water) ------------------------------
def launch_at(kind, origin, d, pw=1.0):
    d = np.asarray(d, float)
    projectiles.append({"kind": kind, "x": float(origin[0]), "y": float(origin[1]),
                        "vx": d[0] * SPEED[kind], "vy": d[1] * SPEED[kind], "d": d, "life": 70,
                        "size": int(SIZE[kind] * (1 + (pw - 1) * 0.8)), "pow": pw,
                        "hit": set(), "rot": random.uniform(0, 6.28)})
    burst(origin[0], origin[1], POWER_COLORS[kind], 8, 7, life=(8, 14))   # muzzle flash


def launch(kind, hd):
    origin = hd["palm"] + hd["dir"] * hd["size"] * 1.1
    lm = hd["lmList"]
    if kind == "fire" and _d(lm[8], lm[0]) > 1.3 * hd["size"] and _d(lm[12], lm[0]) > 1.3 * hd["size"]:
        origin = np.array([(lm[8][0] + lm[12][0]) / 2, (lm[8][1] + lm[12][1]) / 2], float)  # from the two fingertips
    launch_at(kind, origin, aim(origin, hd["dir"]))


def draw_projectiles(img, glow):
    global shake_level
    h, w = img.shape[:2]
    boulders = []
    for p in projectiles[:]:
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["life"] -= 1
        p["rot"] += 0.25
        x, y, d, kind = p["x"], p["y"], p["d"], p["kind"]
        pw = p.get("pow", 1.0)
        if p["life"] <= 0 or not (-120 < x < w + 120 and -120 < y < h + 120):
            projectiles.remove(p)
            continue
        # trails
        if kind == "fire":
            fire_particles.append({"x": x, "y": y, "vx": random.uniform(-2, 2), "vy": random.uniform(-2, 2),
                                   "life": random.randint(10, 18), "max": 35, "r": random.randint(10, 18)})
        elif kind == "air":
            burst(x - d[0] * 20, y - d[1] * 20, (255, 255, 235), 2, 4, life=(6, 10), size=(2, 4))
        elif kind == "water":
            for _ in range(2):                                  # droplets fall off the stream
                sparks.append({"x": x + random.uniform(-10, 10), "y": y + random.uniform(-10, 10),
                               "vx": random.uniform(-2, 2), "vy": random.uniform(-1, 2), "life": 14, "max": 14,
                               "r": random.randint(2, 4), "col": (255, 225, 150), "g": 0.6})
        else:
            burst(x, y, (70, 110, 150), 2, 3, life=(8, 14), size=(3, 6))
        # collisions
        dead = False
        for e in enemies[:]:
            if id(e) in p["hit"]:
                continue
            if math.hypot(e["x"] - x, e["y"] - y) < e["r"] + p["size"] * (0.9 if kind == "air" else 0.7):
                p["hit"].add(id(e))
                if kind == "fire":
                    damage_enemy(e, 35 * pw, d, 10 * pw, (0, 160, 255))
                    burst(x, y, (0, 170, 255), 40, 14)
                    for _ in range(12):
                        a = random.uniform(0, 6.28)
                        fire_particles.append({"x": x, "y": y, "vx": math.cos(a) * 8, "vy": math.sin(a) * 8,
                                               "life": random.randint(15, 30), "max": 35, "r": random.randint(14, 26)})
                    dead = True
                elif kind == "air":                     # pierces, hits each enemy once
                    damage_enemy(e, 14 * pw, d, 18 * pw, (255, 255, 235))
                    burst(e["x"], e["y"], (255, 255, 235), 14, 9)
                elif kind == "water":                   # heavy hit: big knockback + splash
                    damage_enemy(e, 28 * pw, d, 24 * pw, (255, 210, 120))
                    burst(x, y, (255, 215, 130), 45, 13, size=(3, 7), gravity=0.5)
                    burst(x, y, (255, 255, 235), 15, 9, size=(2, 4), gravity=0.5)
                    dead = True
                else:
                    damage_enemy(e, 45 * pw, d, 16 * pw, (70, 120, 170))
                    burst(x, y, (70, 120, 170), 35, 12, size=(4, 9), gravity=0.6)
                    shake_level = 1.0
                    dead = True
                if dead:
                    break
        if dead:
            projectiles.remove(p)
            continue
        # drawing
        c = (int(x), int(y))
        s = p["size"]
        if kind == "fire":
            cv2.circle(glow, c, int(s * 1.8), (0, 120, 255), -1)
            cv2.circle(img, c, s, (100, 210, 255), -1)
            cv2.circle(img, c, int(s * 0.55), (235, 255, 255), -1)
        elif kind == "air":
            ang = math.degrees(math.atan2(d[1], d[0])) + 90   # long axis across travel direction
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
    for p in boulders:                                   # solid spinning rock
        pts = []
        for k in range(7):
            a = p["rot"] + k * 2 * math.pi / 7
            rad = p["size"] * (0.75 + 0.25 * ((k * 53 + p["size"]) % 3) / 2)
            pts.append((p["x"] + math.cos(a) * rad, p["y"] + math.sin(a) * rad))
        pts = np.int32(pts)
        cv2.fillPoly(img, [pts], (70, 105, 150))
        cv2.fillPoly(img, [np.int32((pts - pts.mean(0)) * 0.55 + pts.mean(0) - 4)], (105, 140, 185))
        cv2.polylines(img, [pts], True, (20, 30, 45), 2)
    return img


def seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def draw_lightning_battle(img, hd, glow):
    """Bolt from the index fingertip. Locks onto an enemy you point near, then chains to 2 more."""
    origin = np.array(hd["lmList"][8][:2], float)
    d = aim(origin, hd["dir"])
    target, best = None, math.cos(math.radians(AIM_CONE_DEG))
    for e in enemies:
        v = np.array([e["x"], e["y"]]) - origin
        dist = np.linalg.norm(v)
        if dist > 1 and float(np.dot(v / dist, d)) > best:
            best, target = float(np.dot(v / dist, d)), e
    legs = []
    if target is None:
        legs.append((origin, origin + d * 1100))
    else:
        cur = target
        legs.append((origin, np.array([cur["x"], cur["y"]])))
        used = {id(cur)}
        for _ in range(2):                                   # chain to nearby enemies
            nxt, nd = None, 380
            for e in enemies:
                dd = math.hypot(e["x"] - cur["x"], e["y"] - cur["y"])
                if id(e) not in used and dd < nd:
                    nd, nxt = dd, e
            if nxt is None:
                break
            legs.append((np.array([cur["x"], cur["y"]]), np.array([nxt["x"], nxt["y"]])))
            used.add(id(nxt))
            cur = nxt
    for a, b in legs:
        length = float(np.linalg.norm(b - a))
        pts = bolt(a, b, offset=min(60, length * 0.12))
        for p1, p2 in zip(pts[:-1], pts[1:]):
            cv2.line(glow, p1, p2, (255, 140, 60), 10)
            cv2.line(img, p1, p2, (255, 255, 255), 2, cv2.LINE_AA)
        for _ in range(2):                                   # little side branches
            i = random.randint(3, len(pts) - 4)
            side = bolt(pts[i], np.array(pts[i], float) + np.random.uniform(-110, 110, 2), 20, 4)
            for p1, p2 in zip(side[:-1], side[1:]):
                cv2.line(glow, p1, p2, (255, 140, 60), 5)
                cv2.line(img, p1, p2, (255, 235, 200), 1)
    for e in enemies[:]:                                     # zap everything touching the bolt
        if min(seg_dist(e["x"], e["y"], a, b) for a, b in legs) < e["r"] + 12:
            damage_enemy(e, 4.0, d, 2, (255, 220, 160))
            burst(e["x"] + random.uniform(-e["r"], e["r"]) * 0.5, e["y"] + random.uniform(-e["r"], e["r"]) * 0.5,
                  (255, 235, 190), 2, 8, life=(6, 12), size=(2, 4))
    if random.random() < 0.12:                               # occasional flash
        img = cv2.add(img, (60, 50, 40, 0))
    return img


def draw_charge(glow, by):
    for g, hands_ in by.items():
        for hd in hands_:
            if g == "lightning":
                cv2.circle(glow, tuple(int(v) for v in hd["lmList"][8][:2]), 22, POWER_COLORS[g], -1)
                continue
            c = tuple(int(v) for v in hd["palm"])
            r = int(hd["size"] * (0.5 + 0.08 * math.sin(clock["t"] * 0.5)))
            cv2.circle(glow, c, r, POWER_COLORS[g], -1)


def rot(d, deg):
    a = math.radians(deg)
    c, s_ = math.cos(a), math.sin(a)
    return np.array([d[0] * c - d[1] * s_, d[0] * s_ + d[1] * c])


def update_avatar_state(hands_):
    """Hands together -> Avatar State (needs a full kill meter, lasts AVATAR_DURATION frames).
    Call once per frame with this frame's enriched hands."""
    a = avatar
    if player["over"]:
        a["on"], a["count"] = False, 0
        return
    close = far = False
    if len(hands_) >= 2:
        best = None
        for i in range(len(hands_)):
            for j in range(i + 1, len(hands_)):
                h1, h2 = hands_[i], hands_[j]
                r = _d(h1["palm"], h2["palm"]) / ((h1["size"] + h2["size"]) / 2)
                if best is None or r < best[0]:
                    best = (r, h1, h2)
        r, h1, h2 = best
        close, far = r < AVATAR_ENTER, r > AVATAR_EXIT
        center = (h1["palm"] + h2["palm"]) / 2
        d = h1["dir"] + h2["dir"]
        d = d / (np.linalg.norm(d) + 1e-6)
    elif len(hands_) == 1:                   # touching hands often merge into one detection
        center, d = hands_[0]["palm"], hands_[0]["dir"]
    else:
        center = d = None

    if not a["on"]:
        ready = a["charge"] >= AVATAR_KILLS
        a["count"] = a["count"] + 1 if (close and ready) else 0
        if a["count"] >= AVATAR_HOLD:
            a.update(on=True, count=0, lost=0, center=center, dir=d, cd={}, rings=[], shock=0,
                     time=AVATAR_DURATION, charge=0)
            enemy_shots.clear()
            lasers.clear()
            bombs.clear()
            banner("AVATAR STATE!", 100, (80, 230, 255))
        return
    # active
    a["time"] -= 1
    if center is not None:
        a["lost"] = 0
        a["center"] = center if a["center"] is None else a["center"] * 0.6 + center * 0.4   # smooth
        a["dir"] = d
    else:
        a["lost"] += 1
    if a["lost"] > 15 or (len(hands_) >= 2 and far) or a["time"] <= 0:
        a["on"] = False
        a["count"] = 0


def draw_bolt_to(img, glow, a, b, width=10):
    length = float(np.linalg.norm(np.asarray(b, float) - np.asarray(a, float)))
    pts = bolt(a, b, offset=min(60, length * 0.12))
    for p1, p2 in zip(pts[:-1], pts[1:]):
        cv2.line(glow, p1, p2, (255, 150, 70), width)
        cv2.line(img, p1, p2, (255, 255, 255), 2, cv2.LINE_AA)


def run_avatar_state(img, glow):
    """ALL elements at once, from between your hands, massively boosted. No mana needed."""
    global shake_level
    a = avatar
    c = np.asarray(a["center"], float)
    d = np.asarray(a["dir"], float)
    t = clock["t"]
    ci = (int(c[0]), int(c[1]))
    origin = c + d * 70

    # --- visuals: huge aura, 18 spinning light rays, four orbiting element orbs
    pulse = 1 + 0.15 * math.sin(t * 0.3)
    cv2.circle(glow, ci, int(260 * pulse), (140, 110, 60), -1)
    cv2.circle(glow, ci, int(120 * pulse), (255, 230, 170), -1)
    for k in range(18):
        ang = t * 0.07 + k * math.pi / 9
        cv2.line(glow, ci, (int(c[0] + math.cos(ang) * 600), int(c[1] + math.sin(ang) * 600)), (255, 220, 150), 10)
    for i, g in enumerate(("earth", "water", "air", "fire")):
        ang = t * 0.2 + i * math.pi / 2
        rad = 150 + 18 * math.sin(t * 0.2)
        pos = (int(c[0] + math.cos(ang) * rad), int(c[1] + math.sin(ang) * rad))
        cv2.circle(glow, pos, 55, POWER_COLORS[g], -1)
        cv2.circle(img, pos, 24, POWER_COLORS[g], -1)
        cv2.circle(img, pos, 10, (255, 255, 255), -1)
    cv2.circle(img, ci, 40, (255, 255, 255), -1)

    # --- every element fires a wide fan, much faster, each one boosted
    for kind, fan, cd in (("fire", (-24, -12, 0, 12, 24), 5), ("earth", (-16, -8, 8, 16), 10),
                          ("air", (-18, -9, 0, 9, 18), 4), ("water", (-20, -10, 0, 10, 20), 5)):
        a["cd"][kind] = a["cd"].get(kind, 0) - 1
        if a["cd"][kind] <= 0:
            base = aim(origin, d)
            for deg in fan:
                launch_at(kind, origin, rot(base, deg), AVATAR_POWER)
            a["cd"][kind] = cd

    # --- lightning storm: a bolt to EVERY enemy (up to 8), heavy damage
    targets = sorted(enemies, key=lambda e: math.hypot(e["x"] - c[0], e["y"] - c[1]))[:8]
    if targets:
        for e in targets:
            draw_bolt_to(img, glow, c, (e["x"], e["y"]), 14)
        for e in targets:
            damage_enemy(e, 14.0, d, 3, (255, 220, 160))
            burst(e["x"], e["y"], (255, 235, 190), 3, 10, life=(6, 12), size=(2, 5))
    else:
        for _ in range(8):
            draw_bolt_to(img, glow, c, c + rot(d, random.uniform(-70, 70)) * random.uniform(500, 1000), 14)

    # --- shockwave + 360-degree elemental nova every 30 frames
    a["shock"] += 1
    if a["shock"] % 30 == 1:
        a["rings"].append({"x": ci[0], "y": ci[1], "r": 30})
        shake_level = max(shake_level, 1.0)
        for e in enemies[:]:
            v = np.array([e["x"] - c[0], e["y"] - c[1]])
            damage_enemy(e, 60, v / (np.linalg.norm(v) + 1e-6), 25, (255, 255, 255))
        kinds = ("fire", "earth", "air", "water")
        for k in range(16):                          # ring of projectiles in every direction
            ang = k * 2 * math.pi / 16
            launch_at(kinds[k % 4], c, (math.cos(ang), math.sin(ang)), AVATAR_POWER)
    for r in a["rings"][:]:
        r["r"] += 36
        if r["r"] > 1900:
            a["rings"].remove(r)
            continue
        cv2.circle(glow, (r["x"], r["y"]), r["r"], (255, 220, 160), 22)
        cv2.circle(img, (r["x"], r["y"]), r["r"], (255, 255, 255), 4, cv2.LINE_AA)
    shake_level = max(shake_level, 0.4)
    return cv2.add(img, (40, 35, 25, 0))             # brighter white-blue screen flood


def run_avatar(img, reading):
    global shake_level
    h, w = img.shape[:2]
    over = player["over"]

    # where your hands are this frame (enemies aim at them, orbs and bodies hurt them)
    hand_zones.clear()
    for _, hd in reading:
        hand_zones.append({"pos": np.asarray(hd["palm"], float), "r": hd["size"] * 0.9})
    check_hands_present(w, h)                    # hands out of view -> HP drains

    if enemies_on["v"]:
        alive = boss_alive()
        if boss_state["pending"] and not alive:
            spawn_boss(w, h)
            boss_state["pending"] = False
        elif (sum(1 for e in enemies if not e.get("boss")) < (2 if alive else MAX_ENEMIES + min(3, score["kills"] // 10))
              and clock["t"] % max(15, 35 - score["kills"]) == 0):
            spawn_enemy(w, h)
        update_enemies(w, h)
        update_enemy_attacks(w, h)
        enemy_contact()
    elif enemies:
        enemies.clear()
        enemy_shots.clear()
        lasers.clear()
        bombs.clear()

    regen_mana()
    by = {el: [] for el in ELEMENTS}
    if not over:
        for g, hd in reading:
            if g in by and not avatar["on"]:                 # in Avatar State, single powers are replaced
                if can_cast(g):
                    by[g].append(hd)
                else:
                    nomana[g] = 8                            # blink the empty mana bar

    glow = np.zeros_like(img)                               # one shared bloom layer per frame
    if enemies:
        img = draw_enemies(img, glow)
    if bombs:
        img = draw_bombs(img, glow)
    if enemy_shots:
        img = draw_enemy_shots(img, glow)
    if lasers:
        img = draw_lasers(img, glow)
    if avatar["on"]:
        img = run_avatar_state(img, glow)
    for hd in by["lightning"]:
        if spend("lightning", LIGHTNING_COST):              # lightning drains mana every frame
            img = draw_lightning_battle(img, hd, glow)
    for g in ("fire", "air", "earth", "water"):             # auto-fire while the gesture is held
        for hd in by[g]:
            k = (hd["key"], g)
            cd = cooldowns.get(k, 0) - 1
            if cd <= 0 and spend(g, MANA_COST[g]):
                launch(g, hd)
                cd = COOLDOWN[g]
            cooldowns[k] = cd
    if fire_particles:
        img = draw_fire(img, False, glow)
    img = draw_projectiles(img, glow)
    img = draw_sparks(img, glow)
    draw_charge(glow, by)
    img = add_glow(img, glow, 10)
    if by["water"]:
        img = cv2.add(img, (25, 12, 0, 0))                 # cool blue tint
    if by["fire"]:
        img = cv2.add(img, (0, 8, 25, 0))                  # warm tint
    if by["air"]:
        img = cv2.add(img, (14, 14, 12, 0))                # airy brighten
    if player["flash"] > 0:                                # got hit: red flash
        img = cv2.add(img, (0, 0, 70, 0))
    player["flash"] = max(0, player["flash"] - 1)
    player["inv"] = max(0, player["inv"] - 1)
    boss_state["t"] = max(0, boss_state["t"] - 1)
    # screen shake (boulder impacts)
    shake_level *= 0.8
    if shake_level > 0.05:
        amp = shake_level * 16
        M = np.float32([[1, 0, random.uniform(-amp, amp)], [0, 1, random.uniform(-amp, amp)]])
        img = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    return img


def reset_battle():
    for lst in (enemies, projectiles, sparks, fire_particles, enemy_shots, lasers, bombs, hand_zones):
        lst.clear()
    cooldowns.clear()
    score["kills"] = 0
    boss_state.update({"since": 0, "pending": False, "text": "", "t": 0})
    avatar.update(on=False, count=0, lost=0, center=None, dir=None, charge=0, time=0,
                  cd={}, rings=[], shock=0)
    player.update(hp=PLAYER_HP, lives=PLAYER_LIVES, inv=0, flash=0, over=False, missing=0, started=False)
    for el in ELEMENTS:
        mana[el], mana_wait[el], nomana[el] = MANA_MAX, 0, 0


# --------------------------------------------------------------------------
# CLASSIC MODE effects + labels
# --------------------------------------------------------------------------
def run_classic(img, reading):
    active = {g for g, _ in reading if g}
    for g, hd in reading:
        if g == "fire":
            spawn_fire(hd)
    if fire_particles:
        img = draw_fire(img, "fire" in active)
    img = draw_ice(img, "ice" in active)
    if "love" in active or hearts:
        img = draw_love(img, "love" in active)
    for g, hd in reading:
        if g == "lightning":
            img = draw_lightning(img, hd)
    return img


def draw_hud(img):
    """HP + lives (top left), mana bars (bottom left), Avatar State meter (bottom centre)."""
    H, W = img.shape[:2]
    font = cv2.FONT_HERSHEY_PLAIN

    # --- HP bar
    bw, bh, x0, y0 = 250, 18, 15, 15
    cv2.rectangle(img, (x0 - 2, y0 - 2), (x0 + bw + 2, y0 + bh + 2), (0, 0, 0), -1)
    frac = max(0.0, min(1.0, player["hp"] / PLAYER_HP))
    low = frac < 0.3
    hp_col = (60, 60, 255) if low else (70, 210, 70)
    if player["inv"] > 0 and (clock["t"] // 3) % 2 == 0:
        hp_col = (255, 255, 255)                             # blink while invincible
    cv2.rectangle(img, (x0, y0), (x0 + int(bw * frac), y0 + bh), hp_col, -1)
    cv2.putText(img, f"HP {int(max(0, player['hp']))}", (x0 + 6, y0 + 14), font, 1.1, (255, 255, 255), 1, cv2.LINE_AA)

    # --- lives (hearts)
    for i in range(PLAYER_LIVES):
        pts = heart_points(x0 + 14 + i * 38, y0 + 52, 24)
        if i < player["lives"]:
            cv2.fillPoly(img, [pts], (60, 60, 255))
            cv2.polylines(img, [pts], True, (255, 255, 255), 1, cv2.LINE_AA)
        else:
            cv2.polylines(img, [pts], True, (110, 110, 110), 1, cv2.LINE_AA)

    # --- mana bars, one per element
    rows = len(ELEMENTS)
    my = H - 50 - rows * 20
    for i, el in enumerate(ELEMENTS):
        y = my + i * 20
        need = LIGHTNING_COST if el == "lightning" else MANA_COST[el]
        col = POWER_COLORS[el]
        if mana[el] < need:
            col = tuple(int(c * 0.45) for c in col)          # too low to cast
        cv2.putText(img, el.upper(), (15, y + 10), font, 1.0, (255, 255, 255), 1, cv2.LINE_AA)
        bx, bwid = 95, 150
        cv2.rectangle(img, (bx - 1, y - 1), (bx + bwid + 1, y + 12), (0, 0, 0), -1)
        cv2.rectangle(img, (bx, y), (bx + int(bwid * mana[el] / MANA_MAX), y + 11), col, -1)
        if nomana[el] > 0:
            cv2.rectangle(img, (bx - 1, y - 1), (bx + bwid + 1, y + 12), (0, 0, 255), 2)

    # --- Avatar State meter
    a = avatar
    bw, bh = 320, 14
    x0, y0 = (W - bw) // 2, H - 40
    cv2.rectangle(img, (x0 - 2, y0 - 2), (x0 + bw + 2, y0 + bh + 2), (0, 0, 0), -1)
    if a["on"]:
        frac, col, label = a["time"] / AVATAR_DURATION, (80, 230, 255), "AVATAR STATE!"
    elif a["charge"] >= AVATAR_KILLS:
        frac, col, label = 1.0, (255, 200, 90), "AVATAR READY - put your hands together!"
    else:
        frac, col = a["charge"] / AVATAR_KILLS, (120, 120, 120)
        label = f"Avatar State: {a['charge']}/{AVATAR_KILLS} kills"
    cv2.rectangle(img, (x0, y0), (x0 + int(bw * max(0.0, min(1.0, frac))), y0 + bh), col, -1)
    cv2.putText(img, label, (x0, y0 - 8), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

    # --- hands-out-of-view warning
    if player["missing"] > 0 and not player["over"]:
        left = max(0, NO_HAND_GRACE - player["missing"])
        txt = "SHOW YOUR HANDS!" if left > 0 else "HAND LOST - LOSING HP!"
        (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_DUPLEX, 1.4, 3)
        pos = ((W - tw) // 2, 110)
        cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, 1.4, (0, 0, 0), 8, cv2.LINE_AA)
        cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, 1.4, (60, 60, 255), 3, cv2.LINE_AA)
        cv2.rectangle(img, (0, 0), (W - 1, H - 1), (0, 0, 255), 6)


def draw_labels(img, reading, mode):
    for g, hd in reading:
        if not g or (mode == "avatar" and avatar["on"]):
            continue
        text = POWER_NAMES.get(g, g.upper()) if mode == "avatar" else g.upper()
        color = POWER_COLORS.get(g, (255, 255, 255)) if mode == "avatar" else (255, 255, 255)
        x, y, _, _ = hd["bbox"]
        pos = (x, max(35, y - 15))
        cv2.putText(img, text, pos, cv2.FONT_HERSHEY_DUPLEX, 1.1, (0, 0, 0), 5, cv2.LINE_AA)
        cv2.putText(img, text, pos, cv2.FONT_HERSHEY_DUPLEX, 1.1, color, 2, cv2.LINE_AA)
    if mode == "avatar":
        nxt = "BOSS FIGHT!" if (boss_alive() or boss_state["pending"]) else f"BOSS IN {BOSS_EVERY - boss_state['since']}"
        cv2.putText(img, f"KILLS: {score['kills']}   {nxt}   (E = enemies {'ON' if enemies_on['v'] else 'OFF'})",
                    (img.shape[1] - 560, 35), cv2.FONT_HERSHEY_DUPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        if boss_state["t"] > 0 and not player["over"]:       # big centre banner
            txt = boss_state["text"]
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_DUPLEX, 2.0, 4)
            pos = ((img.shape[1] - tw) // 2, img.shape[0] // 2)
            cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, 2.0, (0, 0, 0), 9, cv2.LINE_AA)
            cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, 2.0, boss_state["col"], 4, cv2.LINE_AA)
        draw_hud(img)
        if player["over"]:                                   # game over overlay
            img[:] = cv2.addWeighted(img, 0.45, np.zeros_like(img), 0.55, 0)
            for txt, scale, yoff, col in (("GAME OVER", 2.6, -30, (60, 60, 255)),
                                          (f"Kills: {score['kills']}", 1.1, 30, (255, 255, 255)),
                                          ("Press R to restart", 1.0, 80, (255, 255, 255))):
                (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_DUPLEX, scale, 3)
                pos = ((img.shape[1] - tw) // 2, img.shape[0] // 2 + yoff)
                cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, scale, (0, 0, 0), 8, cv2.LINE_AA)
                cv2.putText(img, txt, pos, cv2.FONT_HERSHEY_DUPLEX, scale, col, 3, cv2.LINE_AA)
    cv2.putText(img, f"{mode.upper()} MODE  (A = switch)", (15, img.shape[0] - 15),
                cv2.FONT_HERSHEY_PLAIN, 1.2, (255, 255, 255), 1, cv2.LINE_AA)


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
WINDOW = "Gesture Powers"


def open_camera(index):
    """Open a camera by index. Returns the capture, or None if it can't deliver frames."""
    backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY  # DirectShow finds Iriun on Windows
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    for _ in range(10):  # some virtual cameras need a few tries to deliver the first frame
        ok, _frame = cap.read()
        if ok:
            return cap
    cap.release()
    return None


def find_cameras(max_index=6):
    found = []
    for i in range(max_index):
        cap = open_camera(i)
        if cap is not None:
            w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            found.append((i, w, h))
            cap.release()
    return found


def choose_camera(requested):
    if requested is not None:
        return requested
    print("Looking for cameras...")
    cams = find_cameras()
    if not cams:
        raise SystemExit("No camera found. Is Iriun Webcam running on your PC and phone?")
    for i, w, h in cams:
        print(f"  [{i}] {w}x{h}")
    if len(cams) == 1:
        return cams[0][0]
    raw = input("Pick a camera number (Iriun is usually the one that is not your built-in cam): ").strip()
    return int(raw) if raw.isdigit() else cams[-1][0]


def screen_size():
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        size = root.winfo_screenwidth(), root.winfo_screenheight()
        root.destroy()
        return size
    except Exception:
        return 1920, 1080


def fit_to_screen(img, sw, sh, fill=True):
    """Scale the frame to the screen without distortion.
    fill=True crops the edges to cover the whole screen; fill=False adds black bars."""
    h, w = img.shape[:2]
    scale = max(sw / w, sh / h) if fill else min(sw / w, sh / h)
    nw, nh = int(w * scale), int(h * scale)
    img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    if fill:
        x, y = (nw - sw) // 2, (nh - sh) // 2
        return img[y:y + sh, x:x + sw]
    canvas = np.zeros((sh, sw, 3), np.uint8)
    x, y = (sw - nw) // 2, (sh - nh) // 2
    canvas[y:y + nh, x:x + nw] = img
    return canvas


def set_fullscreen(on):
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN,
                          cv2.WINDOW_FULLSCREEN if on else cv2.WINDOW_NORMAL)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=None,
                        help="camera index (e.g. 1 for Iriun). Omit to pick from a list.")
    args = parser.parse_args()

    cam_index = choose_camera(args.camera)
    cap = open_camera(cam_index)
    if cap is None:
        raise SystemExit(f"Could not open camera {cam_index}.")
    try:
        detector = HandDetector(maxHands=4, detectionCon=0.8, minTrackCon=0.6)
    except TypeError:                      # older cvzone without minTrackCon
        detector = HandDetector(maxHands=4, detectionCon=0.8)

    sw, sh = screen_size()
    cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
    fullscreen, fill, first = True, True, True

    mode = "avatar"      # "avatar" (4 elements) or "classic" (fire/ice/love/lightning)
    states = {}  # per-hand debounce: key -> {"hist", "cur", "dir"}

    while True:
        ok, img = cap.read()
        if not ok:
            continue
        img = cv2.flip(img, 1)  # mirror view
        hands, _ = detector.findHands(img, draw=False, flipType=False)

        # read every hand on its own
        seen, reading = set(), []
        for i, hd in enumerate(hands):
            key = hd["type"]
            if key in seen:          # two hands reported with the same label
                key += str(i)
            seen.add(key)
            st = states.setdefault(key, {"hist": deque(maxlen=VOTE_FRAMES), "cur": None, "dir": None})
            enrich(hd, st, key)
            fingers = finger_states(hd)
            raw = classify_avatar(hd, fingers) if mode == "avatar" else classify(fingers)
            st["hist"].append(raw)                                  # majority vote over recent frames
            top, votes = Counter(st["hist"]).most_common(1)[0]
            if votes >= VOTE_NEEDED:
                st["cur"] = top
            reading.append((st["cur"], hd))
        for k in list(states):       # forget hands that left the frame
            if k not in seen:
                del states[k]

        clock["t"] += 1
        if mode == "avatar":
            update_avatar_state([hd for _, hd in reading])
        else:
            avatar["on"] = False
        img = run_avatar(img, reading) if mode == "avatar" else run_classic(img, reading)
        draw_labels(img, reading, mode)

        if fullscreen:
            img = fit_to_screen(img, sw, sh, fill)
        cv2.imshow(WINDOW, img)
        if first:  # fullscreen must be requested after the window has been shown once
            set_fullscreen(fullscreen)
            first = False
        k = cv2.waitKey(1) & 0xFF
        if k in (ord("q"), 27):
            break
        if k == ord("f"):
            fullscreen = not fullscreen
            set_fullscreen(fullscreen)
        if k == ord("a"):  # switch between Avatar and Classic modes
            mode = "classic" if mode == "avatar" else "avatar"
            states.clear()
            reset_battle()
        if k == ord("r"):  # restart after GAME OVER (or any time)
            reset_battle()
        if k == ord("e"):  # enemies on/off
            enemies_on["v"] = not enemies_on["v"]
        if k == ord("m"):
            fill = not fill
        if k == ord("c"):  # cycle to the next camera
            for step in range(1, 7):
                nxt = (cam_index + step) % 7
                new_cap = open_camera(nxt)
                if new_cap is not None:
                    cap.release()
                    cap, cam_index = new_cap, nxt
                    states.clear()
                    break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()