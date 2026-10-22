"""Hand-designed creature sprites for every enemy and guardian.

Each creature is vector art drawn once at 3x resolution, with a matching coverage mask, then shrunk
with area averaging (so edges are clean and there is no dark fringe) and cached. At runtime a sprite
is just an alpha blit, so the battle view pays almost nothing per frame.

Coordinates inside a drawing function are in units of the creature's radius: (0, 0) is the centre,
x grows right, y grows down, and the creature faces the player.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

SS = 3                    # supersampling factor
PAD = 1.75                # sprite canvas half-size, in radii (room for horns, crowns, tridents)
INK = (22, 12, 30)        # outline colour (BGR)


def _bgr(c):
    return tuple(int(v) for v in c)


def shade(c, k):
    """Lighten (k > 1) or darken (k < 1) a BGR colour."""
    return tuple(int(max(0, min(255, v * k))) for v in c)


def mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


class Painter:
    """Draws shapes into a colour layer and a coverage mask at the same time."""

    def __init__(self, r: float):
        self.r = float(r)
        self.half = int(math.ceil(r * PAD))
        self.n = self.half * 2
        self.s = r * SS                          # pixels per unit at supersampled size
        self.c = np.zeros((self.n * SS, self.n * SS, 3), np.uint8)
        self.a = np.zeros((self.n * SS, self.n * SS), np.uint8)

    def p(self, x, y):
        return (int(round((self.half + x * self.r) * SS)), int(round((self.half + y * self.r) * SS)))

    def pts(self, pts):
        return np.int32([self.p(x, y) for x, y in pts])

    def lw(self, w):                             # line width given in 1/100 radius
        return max(1, int(round(w * 0.01 * self.s)))

    def poly(self, pts, fill, line=INK, w=3):
        q = self.pts(pts)
        cv2.fillPoly(self.c, [q], _bgr(fill), cv2.LINE_AA)
        cv2.fillPoly(self.a, [q], 255, cv2.LINE_AA)
        if line is not None and w:
            t = self.lw(w)
            cv2.polylines(self.c, [q], True, _bgr(line), t, cv2.LINE_AA)
            cv2.polylines(self.a, [q], True, 255, t, cv2.LINE_AA)

    def open(self, pts, col, w=4, closed=False):
        q = self.pts(pts)
        t = self.lw(w)
        cv2.polylines(self.c, [q], closed, _bgr(col), t, cv2.LINE_AA)
        cv2.polylines(self.a, [q], closed, 255, t, cv2.LINE_AA)

    def circ(self, x, y, rad, fill, line=INK, w=3):
        c, rr = self.p(x, y), max(1, int(round(rad * self.s)))
        cv2.circle(self.c, c, rr, _bgr(fill), -1, cv2.LINE_AA)
        cv2.circle(self.a, c, rr, 255, -1, cv2.LINE_AA)
        if line is not None and w:
            t = self.lw(w)
            cv2.circle(self.c, c, rr, _bgr(line), t, cv2.LINE_AA)
            cv2.circle(self.a, c, rr, 255, t, cv2.LINE_AA)

    def ell(self, x, y, rx, ry, fill, line=INK, w=3, ang=0.0, a0=0, a1=360):
        c = self.p(x, y)
        ax = (max(1, int(round(rx * self.s))), max(1, int(round(ry * self.s))))
        cv2.ellipse(self.c, c, ax, ang, a0, a1, _bgr(fill), -1, cv2.LINE_AA)
        cv2.ellipse(self.a, c, ax, ang, a0, a1, 255, -1, cv2.LINE_AA)
        if line is not None and w:
            t = self.lw(w)
            cv2.ellipse(self.c, c, ax, ang, a0, a1, _bgr(line), t, cv2.LINE_AA)
            cv2.ellipse(self.a, c, ax, ang, a0, a1, 255, t, cv2.LINE_AA)

    def line(self, a, b, col, w=4):
        self.open([a, b], col, w)

    def arc(self, x, y, rx, ry, a0, a1, col, w=4, ang=0.0):
        c = self.p(x, y)
        ax = (max(1, int(round(rx * self.s))), max(1, int(round(ry * self.s))))
        t = self.lw(w)
        cv2.ellipse(self.c, c, ax, ang, a0, a1, _bgr(col), t, cv2.LINE_AA)
        cv2.ellipse(self.a, c, ax, ang, a0, a1, 255, t, cv2.LINE_AA)

    def eye(self, x, y, rad, iris=(0, 0, 255), look=(0.0, 0.0)):
        self.circ(x, y, rad, (235, 240, 245), INK, 2)
        self.circ(x + look[0] * rad * 0.4, y + look[1] * rad * 0.4, rad * 0.62, iris, None)
        self.circ(x + look[0] * rad * 0.4, y + look[1] * rad * 0.4, rad * 0.28, (10, 5, 10), None)
        self.circ(x - rad * 0.2, y - rad * 0.25, rad * 0.16, (255, 255, 255), None)

    def glow_eye(self, x, y, rad, col=(0, 220, 255)):
        self.circ(x, y, rad * 1.35, mix(col, (20, 10, 20), 0.55), None)
        self.circ(x, y, rad, col, INK, 2)
        self.circ(x, y, rad * 0.45, (235, 250, 255), None)

    def finish(self):
        """-> (premultiplied BGR float-free uint8, alpha uint8) at final size."""
        n = self.n
        col = cv2.resize(self.c, (n, n), interpolation=cv2.INTER_AREA)
        al = cv2.resize(self.a, (n, n), interpolation=cv2.INTER_AREA)
        # the colour layer was painted over black, so after area averaging it is already premultiplied
        return col, al



# ------------------------------------------------------------------------------------------------
# folk motifs
# ------------------------------------------------------------------------------------------------
def tribal(P: Painter, y, x0, x1, n, h, col, w=4):
    """A Visayan batok-style zigzag band."""
    pts = [(x0 + (x1 - x0) * i / (n * 2), y + (h if i % 2 else 0)) for i in range(n * 2 + 1)]
    P.open(pts, col, w)


def okir(P: Painter, x, y, s, col, flip=1, w=4):
    """An okir curl: a spiral that ends in a leaf, the signature of Maranao carving."""
    pts = []
    for i in range(22):
        t = i / 21
        a = t * 4.6
        rad = s * (1.0 - 0.8 * t)
        pts.append((x + flip * math.cos(a + 3.5) * rad, y + math.sin(a + 3.5) * rad))
    P.open(pts, col, w)
    ex, ey = pts[0]
    P.poly([(ex, ey), (ex + flip * s * 0.9, ey - s * 0.35), (ex + flip * s * 0.5, ey + s * 0.3)], col, None, 0)


def flower(P: Painter, x, y, s):
    """Sampaguita: five white petals round a gold heart."""
    for k in range(5):
        a = k * 2 * math.pi / 5 - math.pi / 2
        P.circ(x + math.cos(a) * s * 0.7, y + math.sin(a) * s * 0.7, s * 0.55, (250, 250, 250), (170, 190, 170), 1)
    P.circ(x, y, s * 0.35, (60, 200, 240), None)


# ------------------------------------------------------------------------------------------------
# ordinary enemies: each is a creature from Philippine folklore
# ------------------------------------------------------------------------------------------------
def _shooter(P: Painter, rage):
    """Manananggal: the torso that detaches and flies at night. Bat wings, long hair, fangs, trailing viscera."""
    skin, wing, edge = (175, 150, 200), (105, 36, 84), (214, 120, 255)
    for sx in (-1, 1):                                                                              # bat wings
        P.poly([(sx * 0.3, -0.25), (sx * 0.8, -1.05), (sx * 1.1, -0.8), (sx * 1.35, -0.5), (sx * 1.1, -0.35),
                (sx * 1.3, 0.05), (sx * 0.98, 0.0), (sx * 1.05, 0.5), (sx * 0.5, 0.2)], wing)
        for tx, ty in ((0.8, -1.05), (1.35, -0.5), (1.3, 0.05), (1.05, 0.5)):
            P.line((sx * 0.3, -0.2), (sx * tx, ty), shade(wing, 1.9), 4)
    for sx in (-1, 1):                                                                              # trailing entrails
        P.open([(sx * 0.18, 0.5), (sx * 0.34, 0.8), (sx * 0.16, 1.0), (sx * 0.3, 1.2)], (40, 30, 150), 9)
    P.poly([(-0.42, -0.2), (-0.34, 0.52), (-0.1, 0.62), (0.0, 0.5), (0.1, 0.62), (0.34, 0.52), (0.42, -0.2)], skin)
    P.arc(0, 0.55, 0.34, 0.12, 0, 180, (50, 30, 160), 7)                                            # the torn waist
    P.poly([(-0.46, -0.5), (-0.4, -0.95), (0, -1.05), (0.4, -0.95), (0.46, -0.5), (0.58, 0.45), (0.3, 0.1),
            (-0.3, 0.1), (-0.58, 0.45)], (30, 18, 28))                                              # long black hair
    P.ell(0, -0.5, 0.3, 0.36, skin)
    for sx in (-1, 1):
        P.glow_eye(sx * 0.12, -0.54, 0.07, (60, 40, 255))
        P.line((sx * 0.22, -0.66), (sx * 0.05, -0.6), INK, 4)
    P.poly([(-0.14, -0.3), (0.14, -0.3), (0.1, -0.2), (-0.1, -0.2)], (30, 20, 120), INK, 2)
    for sx in (-1, 1):
        P.poly([(sx * 0.1, -0.28), (sx * 0.05, -0.12), (sx * 0.02, -0.28)], (250, 250, 250), None, 0)   # fangs
    P.line((0.3, 0.0), (0.7, 0.1), skin, 12)                                                         # a reaching arm
    P.circ(0.8, 0.12, 0.2, (255, 190, 255), None)
    P.circ(0.8, 0.12, 0.12, (255, 255, 255), None)


def _charger(P: Painter, rage):
    """Tikbalang: a tall horse-headed trickster of the mountain trails, wild mane and bared teeth."""
    hide, mane = (50, 62, 150), (22, 22, 60)
    for sx in (-1, 1):
        for k, (a, b) in enumerate(((0.45, -0.85), (0.7, -0.55), (0.82, -0.2), (0.8, 0.2), (0.62, 0.55))):   # wild mane
            P.poly([(sx * 0.35, b * 0.8), (sx * (a + 0.35), b - 0.3), (sx * (a + 0.05), b + 0.15)], mane, INK, 2)
        P.poly([(sx * 0.3, -0.8), (sx * 0.5, -1.55), (sx * 0.62, -0.7)], hide)                      # tall ears
        P.poly([(sx * 0.38, -0.82), (sx * 0.5, -1.3), (sx * 0.55, -0.78)], (110, 120, 220), None, 0)
    P.poly([(0, -1.0), (0.46, -0.78), (0.52, -0.2), (0.4, 0.35), (0.42, 0.85), (0.2, 1.0), (-0.2, 1.0),
            (-0.42, 0.85), (-0.4, 0.35), (-0.52, -0.2), (-0.46, -0.78)], hide)                      # long horse skull
    P.line((0, -0.95), (0, 0.4), (80, 95, 190), 3)
    P.poly([(-0.18, -1.0), (0, -1.2), (0.12, -1.0), (0.0, -0.8)], mane, INK, 2)                      # forelock
    for sx in (-1, 1):
        P.glow_eye(sx * 0.27, -0.3, 0.11, (30, 30, 255) if not rage else (255, 255, 255))
        P.line((sx * 0.46, -0.52), (sx * 0.08, -0.4), INK, 9)
        P.ell(sx * 0.2, 0.72, 0.09, 0.06, (20, 10, 30), None, 0, ang=sx * 20)                       # nostrils
    P.poly([(-0.36, 0.86), (0.36, 0.86), (0.3, 1.0), (-0.3, 1.0)], (235, 240, 240))                  # bared teeth
    for x in (-0.2, -0.07, 0.07, 0.2):
        P.line((x, 0.86), (x, 1.0), (150, 160, 170), 2)
    P.line((-0.3, 0.1), (0.3, 0.1), (80, 95, 190), 3)


def _sniper(P: Painter, rage):
    """Bungisngis: the one-eyed, ever-giggling giant. A single huge eye, tusks, a grin full of teeth."""
    skin, hair = (80, 170, 95), (35, 70, 40)
    for k in range(9):                                                                              # tangled hair
        a = -math.pi + 0.2 + k * (math.pi - 0.4) / 8
        P.poly([(math.cos(a) * 0.7, math.sin(a) * 0.7), (math.cos(a - 0.2) * 1.15, math.sin(a - 0.2) * 1.2 - 0.1),
                (math.cos(a + 0.12) * 1.05, math.sin(a + 0.12) * 1.1 - 0.15)], hair, INK, 2)
    for sx in (-1, 1):
        P.ell(sx * 0.92, 0.0, 0.14, 0.24, shade(skin, 0.85))
    P.ell(0, 0.05, 0.92, 0.88, skin)
    P.ell(0, -0.27, 0.5, 0.36, (240, 245, 240), INK, 4)                                              # the eye
    P.circ(0, -0.27, 0.27, (70, 230, 170) if not rage else (50, 50, 255), INK, 3)
    P.circ(0, -0.27, 0.13, (10, 10, 10), None)
    P.circ(-0.07, -0.34, 0.05, (255, 255, 255), None)
    P.line((-0.6, -0.65), (0.6, -0.65), hair, 13)                                                    # one thick brow
    P.poly([(-0.72, 0.14), (0.72, 0.14), (0.6, 0.62), (0.0, 0.84), (-0.6, 0.62)], (25, 20, 60), INK, 4)   # huge grin
    for k in range(7):
        x = -0.54 + k * 0.18
        P.poly([(x - 0.07, 0.14), (x + 0.07, 0.14), (x + 0.07, 0.3), (x - 0.07, 0.3)], (240, 245, 245), None, 0)
    for sx in (-1, 1):
        P.poly([(sx * 0.5, 0.58), (sx * 0.62, 0.3), (sx * 0.68, 0.62)], (225, 235, 240), INK, 2)    # tusks
    P.line((0.12, -0.27), (1.35, -0.27), (160, 255, 190), 2)                                         # sight line
    P.poly([(-0.05, -0.1), (0.05, -0.1), (0.1, 0.1), (-0.1, 0.1)], shade(skin, 0.8), None, 0)


def _gunner(P: Painter, rage):
    """Mandirigma: a carved-shield warrior with a plumed helmet and a brass lantaka cannon."""
    steel, wood, brass = (150, 155, 170), (45, 85, 140), (50, 170, 215)
    P.poly([(-1.28, -0.55), (-0.82, -0.7), (-0.7, 0.2), (-0.82, 0.95), (-1.28, 0.85)], wood)         # the kalasag
    P.line((-1.05, -0.62), (-1.05, 0.88), brass, 4)
    tribal(P, -0.35, -1.25, -0.85, 3, 0.12, brass, 3)
    tribal(P, 0.15, -1.25, -0.85, 3, 0.12, brass, 3)
    P.circ(-1.05, 0.38, 0.1, brass, INK, 2)
    P.poly([(0.72, 0.0), (1.12, -0.05), (1.14, 0.6), (0.74, 0.65)], brass)                           # lantaka barrel
    P.poly([(0.7, 0.62), (1.18, 0.62), (1.24, 0.82), (0.66, 0.82)], shade(brass, 0.8))
    P.ell(0.95, 0.83, 0.2, 0.08, (20, 20, 30), None)
    P.circ(0.95, 0.83, 0.06, (80, 200, 255), None)
    P.poly([(-0.6, -0.15), (-0.55, 0.85), (0.55, 0.85), (0.6, -0.15)], steel)                         # lamellar armour
    for y in (0.05, 0.25, 0.45, 0.65):
        P.line((-0.56, y), (0.56, y), shade(steel, 0.6), 3)
    P.line((0, -0.15), (0, 0.85), brass, 4)
    for sx in (-1, 1):
        P.ell(sx * 0.62, -0.1, 0.22, 0.2, shade(steel, 1.1))
    P.poly([(-0.36, -0.2), (-0.34, -0.55), (0.34, -0.55), (0.36, -0.2), (0.0, -0.1)], (95, 135, 185))  # painted face
    for sx in (-1, 1):
        P.line((sx * 0.3, -0.4), (sx * 0.1, -0.35), INK, 6)
        P.glow_eye(sx * 0.17, -0.34, 0.06, (0, 0, 255) if not rage else (255, 255, 255))
        P.line((sx * 0.3, -0.25), (sx * 0.18, -0.2), (60, 40, 30), 3)                              # tattoo marks
    P.poly([(-0.55, -0.5), (0, -1.15), (0.55, -0.5), (0.34, -0.58), (-0.34, -0.58)], steel)         # helmet
    P.line((0, -1.15), (0, -0.58), brass, 4)
    P.poly([(0.05, -1.1), (0.55, -1.5), (0.4, -1.05), (0.6, -0.85), (0.15, -0.9)], (40, 40, 220))   # plume


def _bomber(P: Painter, rage):
    """Duwende: pointed-hat trickster who lives in a punso (anthill), hugging a bomb with a lit fuse."""
    hat, skin = (30, 120, 230), (110, 160, 215)
    P.ell(0, 0.95, 0.95, 0.3, (45, 80, 115))                                                          # the anthill
    for x in (-0.5, 0.1, 0.55):
        P.ell(x, 0.92, 0.07, 0.04, (20, 30, 45), None)
    P.poly([(-0.45, -0.2), (0.0, -1.35), (0.45, -0.2)], hat)
    tribal(P, -0.42, -0.3, 0.3, 3, 0.1, (235, 240, 245), 3)
    P.ell(0, -0.2, 0.62, 0.14, shade(hat, 0.75))
    P.ell(0, 0.02, 0.45, 0.4, skin)
    P.circ(0.05, 0.07, 0.16, shade(skin, 1.15), INK, 2)
    for sx in (-1, 1):
        P.circ(sx * 0.2, -0.05, 0.07, (15, 15, 15), None)
        P.line((sx * 0.32, -0.17), (sx * 0.1, -0.1), (210, 220, 225), 5)
        P.ell(sx * 0.5, 0.02, 0.07, 0.14, skin)                                                       # pointed ears
    P.poly([(-0.4, 0.18), (0.4, 0.18), (0.3, 0.6), (0.0, 0.92), (-0.3, 0.6)], (235, 240, 245))
    P.circ(0.58, 0.5, 0.4, (38, 38, 46), INK, 4)
    P.circ(0.48, 0.4, 0.1, (110, 110, 125), None)
    P.open([(0.58, 0.1), (0.66, -0.04), (0.54, -0.16)], (60, 90, 120), 5)
    P.circ(0.54, -0.2, 0.1, (60, 190, 255), None)
    P.circ(0.54, -0.2, 0.05, (255, 255, 255), None)
    P.circ(-0.52, 0.5, 0.15, skin)


def _caster(P: Painter, rage):
    """Diwata: a forest spirit with a crown of sampaguita, long streaming hair and wings of light."""
    gown, hair = (190, 100, 40), (50, 30, 25)
    for sx in (-1, 1):                                                                              # wings of light
        P.poly([(sx * 0.2, -0.3), (sx * 1.2, -1.0), (sx * 1.45, -0.3), (sx * 0.5, 0.2)], (255, 235, 190), (255, 200, 130), 2)
        P.poly([(sx * 0.2, -0.1), (sx * 1.1, -0.25), (sx * 1.0, 0.5), (sx * 0.3, 0.3)], (255, 215, 150), (255, 200, 130), 2)
    P.poly([(-0.4, -0.7), (-0.75, 0.3), (-0.55, 1.1), (0.55, 1.1), (0.75, 0.3), (0.4, -0.7)], hair)       # flowing hair
    P.poly([(-0.32, -0.2), (-0.62, 1.0), (0.62, 1.0), (0.32, -0.2)], gown)
    P.poly([(-0.14, -0.2), (-0.2, 1.0), (0.2, 1.0), (0.14, -0.2)], (240, 190, 120), None, 0)
    tribal(P, 0.7, -0.55, 0.55, 5, 0.1, (250, 250, 250), 3)
    P.ell(0, -0.52, 0.28, 0.32, (185, 205, 235))
    for sx in (-1, 1):
        P.glow_eye(sx * 0.1, -0.5, 0.06, (255, 220, 120))
    P.arc(0, -0.38, 0.1, 0.05, 20, 160, (60, 60, 150), 3)
    for k, x in enumerate((-0.28, -0.14, 0.0, 0.14, 0.28)):                                           # sampaguita crown
        flower(P, x, -0.82 + abs(x) * 0.5, 0.075)
    P.arc(0, 0.05, 1.05, 0.34, 0, 360, (255, 190, 120), 3, ang=-18)
    P.circ(-0.5, 0.05, 0.12, (255, 240, 200), None)
    P.circ(0.55, 0.0, 0.12, (255, 240, 200), None)


def _spinner(P: Painter, rage):
    """Sigbin: the hind-heavy hound with ears that clap like hands, a red stare and a whipping tail."""
    fur, ear = (110, 40, 130), (170, 110, 230)
    P.open([(0.6, 0.8), (1.1, 0.7), (1.25, 0.2), (0.95, -0.1), (0.85, 0.25)], shade(fur, 0.8), 12)   # coiled tail
    P.circ(0.85, 0.28, 0.08, (60, 60, 255), None)
    for sx in (-1, 1):                                                                              # huge clapping ears
        P.poly([(sx * 0.4, -0.35), (sx * 0.85, -1.25), (sx * 1.35, -1.0), (sx * 1.2, -0.25), (sx * 0.7, 0.0)], fur)
        P.poly([(sx * 0.5, -0.35), (sx * 0.85, -1.05), (sx * 1.15, -0.9), (sx * 1.05, -0.3), (sx * 0.7, -0.1)], ear, None, 0)
    P.poly([(-0.8, 0.9), (-0.85, 0.0), (-0.55, -0.5), (0.55, -0.5), (0.85, 0.0), (0.8, 0.9)], fur)      # body
    P.ell(0, -0.05, 0.62, 0.55, shade(fur, 1.15))                                                   # head
    P.poly([(-0.3, 0.1), (0.3, 0.1), (0.24, 0.5), (-0.24, 0.5)], (70, 40, 90))                       # muzzle
    for sx in (-1, 1):
        P.glow_eye(sx * 0.26, -0.18, 0.1, (40, 40, 255) if not rage else (255, 255, 255))
        P.line((sx * 0.42, -0.36), (sx * 0.1, -0.26), INK, 7)
        P.poly([(sx * 0.18, 0.42), (sx * 0.13, 0.62), (sx * 0.08, 0.42)], (245, 250, 250), None, 0)    # fangs
    P.ell(0, 0.13, 0.08, 0.05, (15, 10, 25), None)
    for sx in (-1, 1):
        for k in range(3):
            P.line((sx * (0.45 + k * 0.1), 0.65), (sx * (0.5 + k * 0.1), 0.88), (60, 30, 80), 3)    # claws


def _sweeper(P: Painter, rage):
    """Santelmo: the ghost-fire that drifts over graves and ships' masts, with a mournful hollow face."""
    for k, (x, h, c) in enumerate(((-0.6, 0.5, (140, 150, 30)), (-0.3, 0.8, (160, 190, 40)), (0.0, 1.05, (170, 210, 60)),
                                   (0.3, 0.8, (160, 190, 40)), (0.6, 0.5, (140, 150, 30)))):          # licking flames
        P.poly([(x - 0.3, -0.1), (x + 0.02 * (k - 2), -0.6 - h), (x + 0.3, -0.1)], c, None, 0)
    P.circ(0, 0.05, 0.72, (150, 150, 30), (220, 255, 120), 3)
    P.circ(0, 0.08, 0.55, (180, 215, 60), None)
    P.circ(0, 0.12, 0.36, (225, 255, 190), None)
    for sx in (-1, 1):
        P.ell(sx * 0.2, 0.0, 0.1, 0.16, (40, 55, 25), None)
        P.circ(sx * 0.2, 0.03, 0.025, (255, 255, 255), None)
    P.ell(0, 0.3, 0.08, 0.12, (40, 55, 25), None)
    for k, x in enumerate((-0.3, 0.0, 0.3)):                                                        # a wispy tail
        P.open([(x, 0.7), (x + 0.1, 0.95), (x - 0.05, 1.15), (x + 0.04, 1.3)], (150, 190, 40), 9 - k % 2 * 3)


def _blinker(P: Painter, rage):
    """Babaeng Puti, the White Lady: long black hair, a pale gown, and arms that reach."""
    dress, hair = (240, 235, 240), (25, 18, 22)
    tail = [(0.8 - k * 0.2, 1.05 + (0.14 if k % 2 == 0 else 0.0)) for k in range(9)]
    P.poly([(-0.45, -0.1), (-0.85, 1.0), (-0.8, 1.1)] + tail[::-1][1:-1] + [(0.8, 1.1), (0.85, 1.0), (0.45, -0.1)],
           dress, (180, 165, 180), 3)
    P.poly([(-0.55, -0.75), (-0.45, -1.05), (0, -1.15), (0.45, -1.05), (0.55, -0.75), (0.7, 0.7), (0.4, 0.2),
            (-0.4, 0.2), (-0.7, 0.7)], hair)
    P.ell(0, -0.55, 0.26, 0.34, (235, 230, 245), (150, 140, 160), 2)
    for sx in (-1, 1):
        P.ell(sx * 0.11, -0.6, 0.07, 0.11, (25, 15, 25), None)
        P.circ(sx * 0.11, -0.57, 0.025, (60, 60, 255), None)
    P.ell(0, -0.34, 0.05, 0.08, (25, 15, 25), None)
    for sx in (-1, 1):                                                                              # reaching arms
        P.open([(sx * 0.4, 0.05), (sx * 0.85, 0.2), (sx * 1.2, 0.0)], dress, 12)
        for d in (-0.2, 0.0, 0.2):
            P.line((sx * 1.2, 0.0), (sx * 1.45, d - 0.1), (225, 220, 230), 3)


# ------------------------------------------------------------------------------------------------
# guardians
# ------------------------------------------------------------------------------------------------
def _kapre(P: Painter, rage):
    """Kapre of the Balete: a dark, hairy tree giant who sits in the balete tree and smokes an enormous tabako."""
    skin, hair, root = (40, 62, 100), (22, 28, 40), (50, 85, 120)
    for k in range(7):                                                                              # hanging aerial roots
        x = -1.3 + k * 0.43
        P.open([(x, -1.5), (x + 0.07, -0.5), (x - 0.05, 0.4), (x + 0.04, 1.0)], root, 6)
    for k in range(8):                                                                              # balete leaves
        a = -math.pi + 0.15 + k * (math.pi - 0.3) / 7
        P.poly([(math.cos(a) * 0.9, math.sin(a) * 0.9 - 0.25), (math.cos(a) * 1.5, math.sin(a) * 1.5 - 0.45),
                (math.cos(a + 0.25) * 1.0, math.sin(a + 0.25) * 1.0 - 0.25)], (50, 150 - (k % 2) * 40, 60), INK, 2)
    P.ell(0, 1.05, 1.25, 0.55, skin)                                                                 # shoulders
    for k in range(10):                                                                              # shaggy mane
        a = -math.pi + k * math.pi / 9
        P.poly([(math.cos(a) * 0.8, math.sin(a) * 0.85 + 0.1), (math.cos(a) * 1.18, math.sin(a) * 1.25 + 0.15),
                (math.cos(a + 0.2) * 0.85, math.sin(a + 0.2) * 0.9 + 0.1)], hair, INK, 2)
    P.ell(0, 0.0, 0.8, 0.9, skin, INK, 5)
    tribal(P, -0.82, -0.4, 0.4, 4, 0.1, (90, 130, 175), 3)
    P.poly([(-0.7, -0.4), (-0.1, -0.2), (-0.1, -0.1), (-0.7, -0.2)], hair, None, 0)
    P.poly([(0.7, -0.4), (0.1, -0.2), (0.1, -0.1), (0.7, -0.2)], hair, None, 0)
    for sx in (-1, 1):
        P.line((sx * 0.7, -0.5), (sx * 0.08, -0.26), INK, 14)
        P.circ(sx * 0.34, -0.1, 0.19, (235, 245, 245), INK, 3)
        P.circ(sx * 0.34, -0.08, 0.1, (40, 220, 255) if not rage else (50, 50, 255), None)
        P.circ(sx * 0.34, -0.08, 0.045, (10, 10, 10), None)
    P.poly([(-0.1, -0.1), (0.1, -0.1), (0.2, 0.28), (0.0, 0.34), (-0.2, 0.28)], shade(skin, 0.85), INK, 2)
    P.poly([(-0.42, 0.45), (0.42, 0.45), (0.3, 0.68), (-0.3, 0.68)], (30, 20, 50), INK, 3)           # grin
    for x in (-0.24, -0.08, 0.08, 0.24):
        P.poly([(x - 0.06, 0.45), (x + 0.06, 0.45), (x + 0.05, 0.56), (x - 0.05, 0.56)], (235, 240, 240), None, 0)
    P.poly([(0.2, 0.52), (1.15, 0.28), (1.18, 0.48), (0.28, 0.66)], (45, 85, 130), INK, 4)           # the tabako
    P.line((0.4, 0.5), (1.0, 0.36), (30, 55, 90), 3)
    P.poly([(1.08, 0.26), (1.22, 0.29), (1.24, 0.5), (1.1, 0.46)], (50, 150, 255), None, 0)
    P.circ(1.2, 0.38, 0.09, (60, 220, 255), None)
    P.circ(1.2, 0.38, 0.04, (255, 255, 255), None)
    for x, y in ((-1.1, -0.2), (1.05, -0.75), (-0.9, 0.6)):                                           # fireflies
        P.circ(x, y, 0.045, (120, 255, 255), None)


def _siyokoy(P: Painter, rage):
    """Siyokoy King: scaled merman lord with a coral crown, kelp hair, shell pauldrons and a trident."""
    skin, fin, shell = (150, 150, 60), (170, 120, 40), (210, 220, 245)
    P.line((1.2, -1.35), (1.2, 1.3), (190, 190, 120), 8)                                              # trident
    P.open([(1.0, -1.05), (1.0, -1.35)], (190, 190, 120), 7)
    P.open([(1.4, -1.05), (1.4, -1.35)], (190, 190, 120), 7)
    P.open([(1.0, -1.05), (1.2, -0.85), (1.4, -1.05)], (190, 190, 120), 7)
    P.poly([(1.2, -1.58), (1.12, -1.32), (1.28, -1.32)], (230, 230, 190), INK, 2)
    for k in range(7):                                                                              # kelp hair
        x = -0.75 + k * 0.25
        P.open([(x, -0.55), (x + 0.1, -0.1), (x - 0.08, 0.3), (x + 0.06, 0.65)], (60, 140, 50), 8)
    for sx in (-1, 1):
        P.poly([(sx * 0.8, -0.35), (sx * 1.4, -0.65), (sx * 1.34, -0.1), (sx * 1.42, 0.35), (sx * 0.85, 0.22)], fin)
        for k in range(3):
            P.line((sx * 0.9, -0.2 + k * 0.1), (sx * 1.3, -0.3 + k * 0.3), shade(fin, 1.4), 3)
    P.ell(0, 0.1, 0.88, 0.95, skin, INK, 5)
    for r_ in range(3):
        for c_ in range(5):
            P.arc(-0.5 + c_ * 0.25 + (r_ % 2) * 0.12, 0.5 + r_ * 0.17, 0.12, 0.1, 0, 180, shade(skin, 0.7), 3)
    for sx in (-1, 1):                                                                              # gills + shell pauldrons
        for k in range(3):
            P.line((sx * 0.74, 0.0 + k * 0.1), (sx * 0.62, 0.05 + k * 0.1), INK, 3)
        P.ell(sx * 0.82, 0.78, 0.3, 0.22, shell, INK, 3)
        for k in range(4):
            P.line((sx * 0.82, 0.92), (sx * (0.6 + k * 0.1), 0.62), (150, 160, 200), 2)
    P.poly([(-0.55, -0.75), (0.55, -0.75), (0.5, -0.55), (-0.5, -0.55)], (70, 120, 230), None, 0)
    for k, x in enumerate((-0.5, -0.25, 0.0, 0.25, 0.5)):
        h = 0.55 if k % 2 == 0 else 0.35
        P.poly([(x - 0.1, -0.65), (x, -0.65 - h - 0.2), (x + 0.1, -0.65)], (90, 110, 255), INK, 3)
    P.circ(0, -0.45, 0.07, (250, 250, 250), (200, 210, 200), 2)                                       # pearl
    for sx in (-1, 1):
        P.circ(sx * 0.33, -0.2, 0.22, (230, 240, 240), INK, 3)
        P.circ(sx * 0.33, -0.18, 0.12, (30, 200, 255) if not rage else (50, 50, 255), None)
        P.ell(sx * 0.33, -0.18, 0.035, 0.1, (10, 10, 10), None)
    P.ell(0, 0.35, 0.34, 0.14, (20, 20, 70), INK, 3)
    for x in (-0.2, -0.07, 0.07, 0.2):
        P.poly([(x - 0.04, 0.27), (x, 0.4), (x + 0.04, 0.27)], (240, 245, 245), None, 0)
    for sx in (-1, 1):
        P.open([(sx * 0.2, 0.55), (sx * 0.45, 0.75), (sx * 0.38, 0.95)], (230, 230, 190), 5)


def _typhoon(P: Painter, rage):
    """The Typhoon (bagyo): a ring of okir-carved feathers and spiral arms round a calm, watching eye."""
    cols = ((60, 60, 230), (60, 190, 250), (170, 190, 40), (230, 230, 240))
    for k in range(16):                                                                             # sarimanok-style feather ring
        a = k * 2 * math.pi / 16
        ca, sa = math.cos(a), math.sin(a)
        n = (-sa, ca)
        P.poly([(ca * 0.8 + n[0] * 0.12, sa * 0.8 + n[1] * 0.12), (ca * 1.45, sa * 1.45),
                (ca * 0.8 - n[0] * 0.12, sa * 0.8 - n[1] * 0.12)], cols[k % 4], INK, 2)
        P.line((ca * 0.85, sa * 0.85), (ca * 1.3, sa * 1.3), shade(cols[k % 4], 1.4), 3)
    for k in range(5):
        pts = []
        for i in range(30):
            t = i / 29
            a = k * 2 * math.pi / 5 + t * 3.8
            rad = 0.18 + t * 1.0
            pts.append((math.cos(a) * rad, math.sin(a) * rad * 0.92))
        P.open(pts, (150 + k * 12, 180, 175), 22 - k * 2)
        P.open(pts, (235, 250, 245), 8)
    P.circ(0, 0, 0.64, (60, 85, 80), INK, 4)
    P.circ(0, 0, 0.52, (225, 240, 235), INK, 3)
    P.circ(0, 0, 0.32, (230, 190, 70) if not rage else (60, 60, 255), None)
    P.circ(0, 0, 0.17, (10, 10, 10), None)
    P.circ(-0.07, -0.09, 0.06, (255, 255, 255), None)
    for sx in (-1, 1):
        for k in range(3):                                                                          # eyelashes
            P.line((sx * (0.2 + k * 0.17), -0.46 + k * 0.04), (sx * (0.25 + k * 0.2), -0.66 + k * 0.08), INK, 4)
        okir(P, sx * 0.55, 0.62, 0.22, (60, 60, 230), sx, 4)
    P.open([(-0.52, -0.4), (-0.2, -0.34), (0.2, -0.34), (0.52, -0.4)], INK, 7)


def _taal(P: Painter, rage):
    """Blaze of Taal: the volcano that sits in a lake, given a face. Lava veins, a crater of fire, an ash plume."""
    rock, lava = (40, 50, 110), (30, 140, 255)
    for k, (x, y, r_) in enumerate(((-0.35, -1.12, 0.3), (0.0, -1.3, 0.38), (0.38, -1.08, 0.3), (0.1, -0.95, 0.28))):   # ash plume
        P.circ(x, y, r_, (70 - k * 6, 70 - k * 6, 85 - k * 6), None)
    P.open([(-0.1, -1.1), (0.05, -1.25), (-0.05, -1.4)], (120, 230, 255), 5)                         # volcanic lightning
    P.poly([(-1.2, 0.95), (-0.78, 0.0), (-0.45, -0.6), (-0.3, -0.85), (0.3, -0.85), (0.45, -0.6),
            (0.78, 0.0), (1.2, 0.95)], rock, INK, 5)
    for sx in (-1, 1):
        pts = [(sx * 0.35, -0.8), (sx * 0.5, -0.3), (sx * 0.4, 0.2), (sx * 0.75, 0.6), (sx * 0.9, 0.9)]
        P.open(pts, lava, 7)
        P.open(pts, (120, 230, 255), 2)
    tribal(P, 0.62, -0.7, 0.7, 6, 0.1, (60, 100, 170), 3)
    P.ell(0, -0.85, 0.34, 0.14, (20, 90, 220), INK, 3)
    P.ell(0, -0.86, 0.26, 0.09, (60, 210, 255), None)
    for k, (x, h) in enumerate(((-0.2, 0.5), (0.0, 0.8), (0.2, 0.45))):
        P.poly([(x - 0.12, -0.84), (x + 0.03, -0.84 - h), (x + 0.12, -0.84)], (40, 160, 255) if k != 1 else (90, 220, 255), None, 0)
    for sx in (-1, 1):
        P.poly([(sx * 0.62, -0.05), (sx * 0.14, 0.1), (sx * 0.2, -0.22), (sx * 0.6, -0.28)], (10, 20, 60), INK, 3)
        P.glow_eye(sx * 0.33, -0.08, 0.1, (60, 230, 255) if not rage else (255, 255, 255))
    P.poly([(-0.55, 0.3), (-0.3, 0.22), (-0.1, 0.34), (0.1, 0.22), (0.3, 0.34), (0.55, 0.22), (0.45, 0.5),
            (0.0, 0.64), (-0.45, 0.5)], (30, 120, 255), INK, 4)
    P.poly([(-0.3, 0.32), (0.3, 0.32), (0.2, 0.5), (-0.2, 0.5)], (150, 240, 255), None, 0)
    P.ell(0, 1.0, 1.35, 0.22, (150, 100, 30), INK, 3)                                                 # Taal Lake
    for x in (-0.8, -0.3, 0.4, 0.9):
        P.arc(x, 1.02, 0.14, 0.05, 0, 180, (230, 190, 120), 3)


def _bakunawa(P: Painter, rage):
    """Bakunawa: the moon-eating sea serpent. Gaping jaws close on the crescent moon; the coils rise from the sea."""
    scale, belly = (120, 55, 70), (150, 200, 235)
    for sx in (-1, 1):                                                                              # coils
        P.open([(sx * 0.7, 1.2), (sx * 1.25, 0.8), (sx * 1.3, 0.0), (sx * 1.05, -0.55)], shade(scale, 0.75), 46)
        P.open([(sx * 0.7, 1.2), (sx * 1.25, 0.8), (sx * 1.3, 0.0), (sx * 1.05, -0.55)], belly, 6)
        for k in range(5):
            P.poly([(sx * (1.5 - 0.04 * k), 0.95 - k * 0.3), (sx * (1.78 - 0.04 * k), 0.8 - k * 0.3),
                    (sx * (1.5 - 0.04 * k), 0.7 - k * 0.3)], (200, 120, 255), INK, 2)                 # back fins
    for sx in (-1, 1):                                                                              # horns
        P.poly([(sx * 0.4, -0.7), (sx * 0.5, -1.3), (sx * 0.95, -1.55), (sx * 0.76, -1.1), (sx * 0.68, -0.6)], (200, 220, 240))
        P.poly([(sx * 0.7, -0.5), (sx * 1.2, -0.7), (sx * 1.05, -0.3)], (200, 220, 240))
    P.poly([(-0.9, -0.15), (-0.7, -0.75), (0.0, -0.95), (0.7, -0.75), (0.9, -0.15), (0.8, 0.5), (0.35, 0.95),
            (-0.35, 0.95), (-0.8, 0.5)], scale)
    for r_ in range(3):
        for c_ in range(5):
            P.arc(-0.4 + c_ * 0.2 + (r_ % 2) * 0.1, -0.6 + r_ * 0.15, 0.09, 0.08, 0, 180, (180, 100, 230), 2)
    P.poly([(-0.78, 0.3), (-0.5, 0.05), (0.5, 0.05), (0.78, 0.3), (0.62, 0.78), (0.0, 1.0), (-0.62, 0.78)], (45, 15, 80), INK, 4)  # open maw
    P.circ(0.0, 0.42, 0.42, (120, 225, 255), None)                                                     # the crescent moon
    P.circ(0.17, 0.35, 0.37, (45, 15, 80), None)
    for x in (-0.6, -0.4, 0.4, 0.6):                                                                  # fangs, top and bottom
        P.poly([(x - 0.07, 0.07), (x, 0.4), (x + 0.07, 0.07)], (245, 250, 250), None, 0)
    for x in (-0.45, 0.45):
        P.poly([(x - 0.07, 0.92), (x, 0.62), (x + 0.07, 0.92)], (245, 250, 250), None, 0)
    for sx in (-1, 1):
        P.poly([(sx * 0.7, -0.4), (sx * 0.2, -0.2), (sx * 0.24, -0.45), (sx * 0.66, -0.57)], (20, 10, 40), INK, 3)
        P.glow_eye(sx * 0.42, -0.34, 0.11, (60, 60, 255) if rage else (40, 230, 255))
        P.open([(sx * 0.85, -0.05), (sx * 1.3, 0.1), (sx * 1.5, -0.1), (sx * 1.7, 0.1)], (255, 210, 120), 4)   # whiskers
    P.arc(0, 1.35, 1.7, 0.18, 0, 180, (230, 170, 80), 5)                                               # sea waves
    P.arc(0, 1.5, 1.4, 0.14, 0, 180, (200, 140, 60), 4)


DRAWERS = {
    "shooter": _shooter, "charger": _charger, "sniper": _sniper, "gunner": _gunner, "bomber": _bomber,
    "caster": _caster, "spinner": _spinner, "sweeper": _sweeper, "blinker": _blinker,
    "stone_guardian": _kapre, "tide_guardian": _siyokoy, "gale_guardian": _typhoon,
    "ember_guardian": _taal, "rift_sovereign": _bakunawa,
}

# the creature each kind is drawn as
FOLK_NAMES = {
    "shooter": "MANANANGGAL", "charger": "TIKBALANG", "sniper": "BUNGISNGIS", "gunner": "MANDIRIGMA",
    "bomber": "DUWENDE", "caster": "DIWATA", "spinner": "SIGBIN", "sweeper": "SANTELMO", "blinker": "BABAENG PUTI",
}

# a soft aura colour (BGR) for each creature, used for the glow layer
AURA = {
    "shooter": (140, 40, 160), "charger": (30, 30, 170), "sniper": (40, 150, 60), "gunner": (120, 120, 140),
    "bomber": (20, 100, 220), "caster": (170, 90, 30), "spinner": (170, 50, 160), "sweeper": (150, 170, 30),
    "blinker": (150, 140, 160), "stone_guardian": (40, 90, 60), "tide_guardian": (160, 110, 30),
    "gale_guardian": (150, 170, 130), "ember_guardian": (20, 90, 240), "rift_sovereign": (150, 40, 150),
}


def polish(col: np.ndarray, al: np.ndarray, r: float):
    """Give flat vector art some volume: top-left light, a soft shaded rim and a bright upper edge."""
    h, w = al.shape
    a = al.astype(np.float32) / 255.0
    safe = np.maximum(a, 1e-3)[..., None]
    c = col.astype(np.float32) / safe                                  # straight (un-premultiplied) colour
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    light = 1.14 - 0.34 * ((xx / w) * 0.45 + (yy / h) * 0.55)          # lit from the top left
    k = max(2, int(r / 13))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1))
    inner = cv2.GaussianBlur(cv2.erode(al, kernel), (0, 0), max(1.0, k * 0.6)).astype(np.float32) / 255.0
    rim = np.clip(a - inner, 0.0, 1.0)                                  # darker band just inside the outline
    dx = max(1, k // 2)
    shifted = np.roll(np.roll(inner, dx, axis=1), dx, axis=0)
    glint = np.clip(inner - shifted, 0.0, 1.0)                          # bright edge facing the light
    c = c * light[..., None] * (1.0 - 0.28 * rim[..., None]) + 70.0 * glint[..., None]
    out = np.clip(c, 0, 255) * a[..., None]
    return out.astype(np.uint8), al


def _to_rgba(col: np.ndarray, al: np.ndarray, silhouette: bool) -> np.ndarray:
    out = np.zeros(al.shape + (4,), np.uint8)
    if silhouette:
        out[..., :3] = (38, 50, 66)
        out[..., 3] = (al.astype(np.float32) * 0.9).astype(np.uint8)
    else:
        f = al.astype(np.float32)[..., None] / 255.0
        out[..., :3] = np.clip(col.astype(np.float32) / np.maximum(f, 1e-3), 0, 255)[..., ::-1].astype(np.uint8)
        out[..., 3] = al
    return out


SWAY = {"blinker": 4.0, "sweeper": 5.0, "shooter": 3.0, "caster": 2.5, "gale_guardian": 0.0, "rift_sovereign": 1.5}
FRAMES = 8


class SpriteBook:
    """Renders each creature once per size and hands out cached sprites and idle-animation frames."""

    def __init__(self) -> None:
        self._cache: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
        self._frames: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
        self._rgba: dict[tuple, np.ndarray] = {}

    @staticmethod
    def has(kind: str) -> bool:
        return kind in DRAWERS

    @staticmethod
    def bucket(radius: float) -> int:
        return max(12, int(round(radius / 4.0)) * 4)

    def get(self, kind: str, radius: float, rage: bool = False, flash: bool = False):
        """-> (premultiplied BGR, alpha) for the creature. Radius is bucketed to keep the cache small."""
        r = self.bucket(radius)
        key = (kind, r, rage, flash)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        if flash:
            _, al = self.get(kind, radius, rage, False)
            out = (cv2.merge([al, al, al]), al)
        else:
            P = Painter(r)
            DRAWERS[kind](P, rage)
            col, al = P.finish()
            if rage:                                                   # enraged: hotter, redder skin
                f = col.astype(np.float32)
                f[..., 2] = np.minimum(255.0, f[..., 2] * 1.25 + al * 0.12)
                f[..., 0] *= 0.82
                col = f.astype(np.uint8)
            out = polish(col, al, r)
        self._cache[key] = out
        return out

    def frame(self, kind: str, radius: float, phase: float, rage: bool = False, flash: bool = False):
        """An idle-animation frame: the creature breathes (squash and stretch) and some of them sway.

        ``phase`` is in cycles; one of ``FRAMES`` cached frames is chosen, so nothing is resized per frame.
        """
        r = self.bucket(radius)
        n = int(phase * FRAMES) % FRAMES
        key = (kind, r, rage, flash, n)
        hit = self._frames.get(key)
        if hit is not None:
            return hit
        col, al = self.get(kind, radius, rage, flash)
        t = n / FRAMES * 2 * math.pi
        sx, sy = 1.0 - 0.022 * math.sin(t), 1.0 + 0.032 * math.sin(t)
        h, w = al.shape
        m = np.float32([[sx, 0, w * (1 - sx) / 2], [0, sy, h * (1 - sy) * 0.8]])           # anchored near the feet
        sway = SWAY.get(kind, 0.0) * math.sin(t + 1.0)
        if sway:
            rot = cv2.getRotationMatrix2D((w / 2, h / 2), sway, 1.0)
            m = (np.vstack([rot, [0, 0, 1]]) @ np.vstack([m, [0, 0, 1]]))[:2].astype(np.float32)
        out = (cv2.warpAffine(col, m, (w, h), flags=cv2.INTER_LINEAR),
               cv2.warpAffine(al, m, (w, h), flags=cv2.INTER_LINEAR))
        self._frames[key] = out
        return out

    def rgba(self, kind: str, radius: float, rage: bool = False, silhouette: bool = False) -> np.ndarray:
        """Straight RGBA pixels (H, W, 4) for a UI surface; ``silhouette`` gives a dark unknown-creature shape."""
        r = self.bucket(radius)
        key = (kind, r, rage, silhouette)
        hit = self._rgba.get(key)
        if hit is not None:
            return hit
        out = _to_rgba(*self.get(kind, radius, rage, False), silhouette)
        self._rgba[key] = out
        return out

    def rgba_frame(self, kind: str, radius: float, phase: float, silhouette: bool = False) -> np.ndarray:
        """Like ``rgba`` but for an idle-animation frame (used by the Codex)."""
        key = (kind, self.bucket(radius), "f", int(phase * FRAMES) % FRAMES, silhouette)
        hit = self._rgba.get(key)
        if hit is None:
            hit = self._rgba[key] = _to_rgba(*self.frame(kind, radius, phase), silhouette)
        return hit


def blit(img: np.ndarray, col: np.ndarray, al: np.ndarray, cx: float, cy: float) -> None:
    """Alpha-composite a premultiplied sprite onto ``img`` centred at (cx, cy), clipped to the image."""
    h, w = img.shape[:2]
    sh, sw = al.shape[:2]
    x0, y0 = int(round(cx - sw / 2)), int(round(cy - sh / 2))
    ix0, iy0, ix1, iy1 = max(0, x0), max(0, y0), min(w, x0 + sw), min(h, y0 + sh)
    if ix0 >= ix1 or iy0 >= iy1:
        return
    sx0, sy0 = ix0 - x0, iy0 - y0
    sx1, sy1 = sx0 + (ix1 - ix0), sy0 + (iy1 - iy0)
    a = al[sy0:sy1, sx0:sx1].astype(np.uint16)
    inv = (255 - a)[..., None]
    dst = img[iy0:iy1, ix0:ix1].astype(np.uint16)
    out = col[sy0:sy1, sx0:sx1].astype(np.uint16) + (dst * inv + 127) // 255
    img[iy0:iy1, ix0:ix1] = np.minimum(out, 255).astype(np.uint8)


def fade(col: np.ndarray, al: np.ndarray, k: float):
    """A see-through copy of a sprite (both layers scaled, since the colour is premultiplied)."""
    return (col.astype(np.float32) * k).astype(np.uint8), (al.astype(np.float32) * k).astype(np.uint8)


def scaled(col: np.ndarray, al: np.ndarray, k: float):
    """A resized copy of a sprite (used for the spawn-in pop)."""
    n = max(4, int(round(al.shape[0] * k)))
    return (cv2.resize(col, (n, n), interpolation=cv2.INTER_AREA),
            cv2.resize(al, (n, n), interpolation=cv2.INTER_AREA))
