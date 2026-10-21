"""Procedural sound: every effect and every music track is synthesised from scratch with NumPy.

No audio files are needed. Everything here is deterministic (seeded), pure NumPy and independent of
pygame, so it can be generated on a background thread and unit-tested without a sound card.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np

SR = 22050


# ------------------------------------------------------------------ building blocks
def _n(seconds: float) -> int:
    return max(1, int(seconds * SR))


def _t(n: int) -> np.ndarray:
    return np.arange(n, dtype=np.float64) / SR


def envelope(n: int, attack: float = 0.005, decay: float = 0.0, sustain: float = 1.0, release: float = 0.05) -> np.ndarray:
    """Attack / decay / sustain / release shape over n samples."""
    env = np.full(n, sustain, dtype=np.float64)
    a, d, r = min(n, _n(attack)), _n(decay) if decay > 0 else 0, min(n, _n(release))
    if a > 0:
        env[:a] = np.linspace(0.0, 1.0, a)
    if d > 0 and a + d <= n:
        env[a:a + d] = np.linspace(1.0, sustain, d)
    if r > 0:
        env[n - r:] *= np.linspace(1.0, 0.0, r)
    return env


def expdecay(n: int, rate: float) -> np.ndarray:
    return np.exp(-_t(n) * rate)


def sweep(f0: float, f1: float, seconds: float, wave: str = "sine", curve: float = 1.0) -> np.ndarray:
    """Oscillator whose pitch glides from f0 to f1 (curve > 1 bends it late)."""
    n = _n(seconds)
    x = np.linspace(0.0, 1.0, n) ** curve
    freq = f0 + (f1 - f0) * x
    return _osc(np.cumsum(freq) / SR, wave)


def _osc(phase: np.ndarray, wave: str) -> np.ndarray:
    cycle = phase % 1.0
    if wave == "sine":
        return np.sin(2 * np.pi * phase)
    if wave == "tri":
        return 4.0 * np.abs(cycle - 0.5) - 1.0
    if wave == "square":
        return np.where(cycle < 0.5, 1.0, -1.0) * 0.6
    if wave == "saw":
        return (2.0 * cycle - 1.0) * 0.7
    raise ValueError(wave)


def tone(freq: float, seconds: float, wave: str = "sine", vibrato: float = 0.0) -> np.ndarray:
    n = _n(seconds)
    t = _t(n)
    phase = freq * t + (vibrato * np.sin(2 * np.pi * 5.5 * t) / 5.5 / 6.2832 if vibrato else 0.0)
    return _osc(phase, wave)


def noise(n: int, rng: np.random.Generator) -> np.ndarray:
    return rng.uniform(-1.0, 1.0, n)


def lowpass(x: np.ndarray, width: int) -> np.ndarray:
    """Cheap moving-average low-pass (width in samples)."""
    if width <= 1:
        return x
    kernel = np.ones(width) / width
    return np.convolve(x, kernel, mode="same")


def highpass(x: np.ndarray, width: int) -> np.ndarray:
    return x - lowpass(x, width)


def pan(mono: np.ndarray, position: float = 0.0) -> np.ndarray:
    """Equal-power pan, position -1 (left) .. 1 (right)."""
    angle = (position + 1.0) * np.pi / 4.0
    return np.column_stack((mono * np.cos(angle), mono * np.sin(angle)))


def to_int16(stereo: np.ndarray, peak: float = 0.85) -> np.ndarray:
    top = float(np.max(np.abs(stereo))) or 1.0
    scaled = stereo * (peak / top) if top > peak else stereo
    return np.ascontiguousarray((np.clip(scaled, -1.0, 1.0) * 32767).astype(np.int16))


def _stereo(mono: np.ndarray, position: float = 0.0, width: float = 0.0) -> np.ndarray:
    out = pan(mono, position)
    if width:
        out[:, 0] += np.roll(mono, 90) * width * 0.4
        out[:, 1] += np.roll(mono, -90) * width * 0.4
    return out


def _seed(name: str) -> int:
    return zlib.crc32(name.encode())


def _mix(*parts: np.ndarray) -> np.ndarray:
    length = max(len(p) for p in parts)
    out = np.zeros(length)
    for p in parts:
        out[:len(p)] += p
    return out


def _pitch(root: float, semitones: float) -> float:
    return root * 2.0 ** (semitones / 12.0)


# ------------------------------------------------------------------ sound effects
def _bell(freq: float, seconds: float, brightness: float = 1.0) -> np.ndarray:
    n = _n(seconds)
    t = _t(n)
    out = np.zeros(n)
    for ratio, amp, decay in ((1.0, 1.0, 5.0), (2.76, 0.5 * brightness, 8.0), (5.4, 0.25 * brightness, 12.0)):
        out += amp * np.sin(2 * np.pi * freq * ratio * t) * np.exp(-t * decay)
    return out * envelope(n, 0.002, release=0.02)


def _arp(freqs, step: float, ring: float, brightness: float = 1.0) -> np.ndarray:
    total = _n(step * (len(freqs) - 1) + ring)
    out = np.zeros(total)
    for i, f in enumerate(freqs):
        note = _bell(f, ring, brightness)
        start = _n(step * i)
        out[start:start + len(note)] += note[: total - start]
    return out


def _sfx_mono(name: str, rng: np.random.Generator) -> tuple[np.ndarray, float]:
    """(signal, pan) for a sound effect."""
    if name == "ui_move":
        n = _n(0.05)
        return tone(880, 0.05, "tri") * envelope(n, 0.002, release=0.03) * 0.5, 0.0
    if name == "ui_select":
        a = tone(660, 0.07, "tri") * envelope(_n(0.07), 0.003, release=0.04)
        b = tone(990, 0.1, "tri") * envelope(_n(0.1), 0.003, release=0.07)
        return _mix(a, np.concatenate((np.zeros(_n(0.06)), b))) * 0.6, 0.0
    if name == "ui_back":
        return sweep(520, 390, 0.1, "tri") * envelope(_n(0.1), 0.003, release=0.06) * 0.6, 0.0
    if name == "ui_error":
        return tone(150, 0.14, "square") * envelope(_n(0.14), 0.003, release=0.05) * 0.5, 0.0
    if name == "cast_earth":
        n = _n(0.26)
        thump = sweep(130, 42, 0.26, "sine", 0.6) * expdecay(n, 9)
        grit = lowpass(noise(n, rng), 18) * expdecay(n, 14) * 1.6
        return (thump + grit) * 0.9, -0.1
    if name == "cast_water":
        n = _n(0.22)
        bubble = sweep(320, 920, 0.22, "sine", 1.4) * (0.7 + 0.3 * np.sin(2 * np.pi * 22 * _t(n)))
        spray = highpass(noise(n, rng), 6) * 0.12
        return (bubble + spray) * envelope(n, 0.01, release=0.1) * 0.75, 0.1
    if name == "cast_air":
        n = _n(0.26)
        hiss = noise(n, rng)
        swell = lowpass(hiss, 6) * np.sin(np.linspace(0, np.pi, n)) ** 1.5
        return highpass(swell, 40) * 2.2 * envelope(n, 0.02, release=0.08), 0.0
    if name == "cast_fire":
        n = _n(0.24)
        roar = lowpass(noise(n, rng), 10) * np.sin(np.linspace(0, np.pi, n)) ** 0.7
        growl = sweep(210, 95, 0.24, "saw") * expdecay(n, 6) * 0.45
        crackle = (rng.random(n) > 0.995) * rng.uniform(0.4, 1.0, n)
        return (roar * 1.4 + growl + crackle) * envelope(n, 0.008, release=0.06), 0.05
    if name == "cast_lightning":
        n = _n(0.16)
        zap = sweep(1900, 260, 0.16, "square", 0.5) * expdecay(n, 7)
        crackle = (rng.random(n) > 0.985) * rng.uniform(-1.0, 1.0, n)
        return (zap * 0.55 + crackle * 0.7 + highpass(noise(n, rng), 8) * 0.12) * envelope(n, 0.001, release=0.03), 0.0
    if name == "enemy_defeated":
        n = _n(0.2)
        pop = sweep(560, 140, 0.2, "sine", 0.5) * expdecay(n, 11)
        puff = lowpass(noise(n, rng), 7) * expdecay(n, 18) * 0.9
        return (pop + puff) * envelope(n, 0.002, release=0.04) * 0.9, 0.0
    if name == "boss_defeated":
        n = _n(1.6)
        rumble = lowpass(noise(n, rng), 60) * expdecay(n, 2.2) * 2.0
        boom = sweep(95, 28, 1.6, "sine", 0.4) * expdecay(n, 2.4)
        chime = np.concatenate((np.zeros(_n(0.3)), _arp([523.25, 659.25, 783.99, 1046.5], 0.14, 1.0, 0.8)))
        return _mix(rumble, boom, chime * 0.5), 0.0
    if name == "player_hit":
        n = _n(0.22)
        thud = sweep(150, 60, 0.22, "sine", 0.5) * expdecay(n, 12)
        crunch = lowpass(noise(n, rng), 9) * expdecay(n, 22) * 0.8
        return (thud + crunch) * envelope(n, 0.002, release=0.05), 0.0
    if name == "life_lost":
        parts = [tone(f, 0.28, "tri") * envelope(_n(0.28), 0.01, release=0.2) for f in (392, 330, 262, 196)]
        out = np.concatenate([np.concatenate((np.zeros(_n(0.0)), p[: _n(0.2)])) for p in parts])
        return out * 0.7 + lowpass(noise(len(out), rng), 30) * 0.05, 0.0
    if name == "shield_block":
        n = _n(0.3)
        ping = (np.sin(2 * np.pi * 1250 * _t(n)) + 0.6 * np.sin(2 * np.pi * 1870 * _t(n))) * expdecay(n, 14)
        return ping * envelope(n, 0.001, release=0.05) * 0.55, 0.0
    if name == "orb_block":
        n = _n(0.09)
        return (tone(760, 0.09, "tri") * expdecay(n, 30) + highpass(noise(n, rng), 5) * expdecay(n, 40) * 0.2) * 0.8, 0.0
    if name == "defuse":
        a = tone(880, 0.07, "square") * envelope(_n(0.07), 0.002, release=0.03)
        b = tone(620, 0.1, "square") * envelope(_n(0.1), 0.002, release=0.06)
        return np.concatenate((a, b)) * 0.45, 0.0
    if name == "interrupt":
        n = _n(0.14)
        return (sweep(300, 1400, 0.14, "saw") * expdecay(n, 10) * 0.5 + highpass(noise(n, rng), 5) * expdecay(n, 25) * 0.3), 0.0
    if name == "bomb_blast":
        n = _n(0.5)
        boom = sweep(110, 34, 0.5, "sine", 0.5) * expdecay(n, 6)
        blast = lowpass(noise(n, rng), 22) * expdecay(n, 7) * 1.5
        return (boom + blast) * envelope(n, 0.002, release=0.1), 0.0
    if name == "laser_fire":
        n = _n(0.3)
        beam = sweep(700, 380, 0.3, "saw") * envelope(n, 0.004, release=0.12)
        return (beam * 0.45 + highpass(noise(n, rng), 6) * 0.15 * expdecay(n, 6)), 0.0
    if name == "loot_heart":
        return _arp([523.25, 659.25, 783.99], 0.07, 0.35) * 0.55, 0.0
    if name == "loot_regen":
        return _arp([659.25, 783.99, 987.77, 1318.5], 0.05, 0.3, 1.2) * 0.5, 0.0
    if name == "loot_shield":
        return _arp([392.0, 523.25, 783.99], 0.09, 0.4, 0.6) * 0.6, 0.0
    if name == "loot_boost":
        n = _n(0.4)
        rise = sweep(300, 1200, 0.3, "tri", 1.6) * envelope(_n(0.3), 0.01, release=0.1)
        return _mix(rise * 0.5, np.concatenate((np.zeros(_n(0.2)), _bell(1568, 0.3)))) * 0.7, 0.0
    if name == "loot_mana":
        return _arp([880.0, 1174.7], 0.08, 0.35, 1.3) * 0.6, 0.0
    if name == "reaction_shock":
        n = _n(0.34)
        zap = sweep(2600, 180, 0.34, "square", 0.45) * expdecay(n, 6) * 0.6
        crackle = (rng.random(n) > 0.975) * rng.uniform(-1.0, 1.0, n) * 0.9
        thump = sweep(120, 45, 0.34, "sine", 0.5) * expdecay(n, 9) * 0.9
        return zap + crackle + thump, 0.0
    if name == "reaction_steam":
        n = _n(0.55)
        hiss = highpass(noise(n, rng), 5) * np.sin(np.linspace(0, np.pi, n)) ** 0.8 * 0.8
        bubble = sweep(700, 220, 0.55, "sine", 0.7) * expdecay(n, 4) * 0.35 * (0.6 + 0.4 * np.sin(2 * np.pi * 14 * _t(n)))
        return hiss + bubble, 0.0
    if name == "reaction_firestorm":
        n = _n(0.7)
        roar = lowpass(noise(n, rng), 12) * np.sin(np.linspace(0, np.pi, n)) ** 0.6 * 1.7
        rise = sweep(110, 330, 0.7, "saw", 1.3) * np.sin(np.linspace(0, np.pi, n)) * 0.35
        return roar + rise, 0.0
    if name == "wave_started":
        a = sweep(196, 196, 0.5, "saw") * envelope(_n(0.5), 0.04, 0.1, 0.7, 0.2)
        b = sweep(294, 294, 0.5, "saw") * envelope(_n(0.5), 0.04, 0.1, 0.7, 0.2)
        return lowpass(a + np.concatenate((np.zeros(_n(0.12)), b))[: len(a)], 8) * 0.9, 0.0
    if name == "wave_complete":
        return _arp([523.25, 659.25, 783.99, 1046.5], 0.09, 0.6) * 0.7, 0.0
    if name == "boss_incoming":
        n = _n(1.4)
        horn = lowpass(sweep(98, 98, 1.4, "saw"), 9) * envelope(n, 0.15, 0.2, 0.8, 0.4)
        horn2 = lowpass(sweep(147, 147, 1.4, "saw"), 9) * envelope(n, 0.3, 0.2, 0.7, 0.4)
        rumble = lowpass(noise(n, rng), 80) * 0.8 * envelope(n, 0.3, release=0.5)
        return (horn + horn2 * 0.7) * 1.1 + rumble, 0.0
    if name == "level_complete":
        chord = sum(tone(f, 1.6, "tri") for f in (261.63, 329.63, 392.0, 523.25)) * envelope(_n(1.6), 0.05, 0.2, 0.6, 0.8) * 0.18
        arp = _arp([523.25, 659.25, 783.99, 1046.5, 1318.5], 0.11, 0.9)
        return _mix(chord, arp * 0.7), 0.0
    if name == "level_failed":
        parts = []
        for f in (293.66, 261.63, 220.0, 174.61):
            n = _n(0.38)
            parts.append(tone(f, 0.38, "tri") * envelope(n, 0.02, release=0.2))
        out = np.concatenate(parts)
        return out * 0.7, 0.0
    if name == "convergence_ready":
        return _arp([523.25, 659.25, 783.99, 987.77, 1318.5], 0.07, 0.9, 1.4) * 0.7, 0.0
    if name == "convergence_started":
        n = _n(2.0)
        rise = sweep(80, 1400, 1.0, "saw", 2.2) * envelope(_n(1.0), 0.05, release=0.05) * 0.4
        riser = np.concatenate((lowpass(noise(_n(1.0), rng), 25) * np.linspace(0.0, 1.0, _n(1.0)) * 1.2, np.zeros(n - _n(1.0))))
        boom = np.concatenate((np.zeros(_n(0.9)), sweep(120, 30, 1.1, "sine", 0.5) * expdecay(_n(1.1), 3.2) * 1.5))
        pots = np.zeros(n)                                                     # kalampag: a crowd banging pots and pans
        for _ in range(26):
            start = _n(0.85 + rng.random() ** 1.3 * 1.1)
            f = rng.uniform(420, 1500)
            hit = np.zeros(_n(0.35))
            t = _t(len(hit))
            for ratio, amp in ((1.0, 1.0), (2.32, 0.6), (3.97, 0.35)):
                hit += amp * np.sin(2 * np.pi * f * ratio * t) * np.exp(-t * rng.uniform(14, 26))
            hit += highpass(noise(len(hit), rng), 4) * np.exp(-t * 60) * 0.5
            end = min(n, start + len(hit))
            pots[start:end] += hit[: end - start] * rng.uniform(0.18, 0.4)
        shimmer = np.concatenate((np.zeros(_n(0.9)), _arp([523.25, 783.99, 1046.5, 1568.0], 0.08, 1.0, 1.2) * 0.5))
        return _mix(np.concatenate((rise, np.zeros(n - len(rise)))), riser, boom, shimmer, pots), 0.0
    if name == "hazard_warning":
        pulse = tone(440, 0.14, "square") * envelope(_n(0.14), 0.005, release=0.06)
        gap = np.zeros(_n(0.08))
        return np.concatenate((pulse, gap, pulse * 1.0, gap, tone(587, 0.2, "square") * envelope(_n(0.2), 0.005, release=0.1))) * 0.4, 0.0
    if name == "boss_phase":
        n = _n(0.8)
        return _mix(sweep(220, 55, 0.8, "saw") * expdecay(n, 3) * 0.5, lowpass(noise(n, rng), 30) * expdecay(n, 5)), 0.0
    if name == "heartbeat":
        out = np.zeros(_n(0.55))
        for start, amp in ((0.0, 1.0), (0.2, 0.7)):
            n = _n(0.16)
            beat = sweep(95, 50, 0.16, "sine") * expdecay(n, 18) * amp
            s = _n(start)
            out[s:s + n] += beat
        return out * 0.9, 0.0
    raise KeyError(name)


SFX_NAMES: tuple[str, ...] = (
    "ui_move", "ui_select", "ui_back", "ui_error",
    "cast_earth", "cast_water", "cast_air", "cast_fire", "cast_lightning",
    "enemy_defeated", "boss_defeated", "player_hit", "life_lost", "shield_block", "orb_block", "defuse",
    "interrupt", "bomb_blast", "laser_fire", "reaction_shock", "reaction_steam", "reaction_firestorm", "loot_heart", "loot_regen", "loot_shield", "loot_boost", "loot_mana",
    "wave_started", "wave_complete", "boss_incoming", "boss_phase", "level_complete", "level_failed",
    "convergence_ready", "convergence_started", "hazard_warning", "heartbeat",
)


def make_sfx(name: str) -> np.ndarray:
    """Stereo int16 samples (n, 2) for a named sound effect. Deterministic."""
    rng = np.random.default_rng(_seed(name))
    mono, position = _sfx_mono(name, rng)
    # a 2 ms fade-in and a 15 ms fade-out on every effect, so none of them can click at its edges
    mono = mono * envelope(len(mono), attack=0.002, release=0.015)
    return to_int16(_stereo(mono, position, width=0.25), peak=0.8)


# ------------------------------------------------------------------ music
MODES = {
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "harmonic": (0, 2, 3, 5, 7, 8, 11),
    "major": (0, 2, 4, 5, 7, 9, 11),
    "slendro": (0, 2, 5, 7, 9),             # five-note scales, as in the gong-ensemble music of the islands
    "pent_minor": (0, 3, 5, 7, 10),
    "pent_major": (0, 2, 4, 7, 9),
}


@dataclass(frozen=True)
class MusicSpec:
    root: float                    # tonic frequency in Hz
    mode: str
    bpm: float
    progression: tuple[int, ...]   # one scale degree (0-6) per bar
    pad: float = 0.5               # layer gains, 0 = off
    bass: float = 0.0
    arp: float = 0.0
    arp_step: int = 2              # 1 = sixteenths, 2 = eighths
    melody: float = 0.0
    drums: int = 0                 # 0 none, 1 soft, 2 steady, 3 driving
    lead_wave: str = "tri"         # tri | saw | flute | gong
    arp_voice: str = ""            # "" picks by mode; or bell | pluck | gong
    dabakan: bool = False          # hand-drum hits instead of a synth kick
    loop: bool = True
    gain: float = 0.7


MUSIC_SPECS: dict[str, MusicSpec] = {
    # the title: a flute over soft gongs, like a house at night waiting for dawn
    "menu": MusicSpec(220.0, "slendro", 66, (0, 3, 1, 4, 0, 3, 2, 4), pad=0.55, arp=0.4, arp_step=2, melody=0.6,
                      drums=0, lead_wave="flute", arp_voice="gong"),
    # Mount Makiling: low drums, a deep drone, the flute calling through trees
    "stonewake": MusicSpec(146.83, "pent_minor", 78, (0, 0, 3, 2, 0, 0, 4, 2), pad=0.6, bass=0.7, melody=0.6, drums=2,
                           lead_wave="flute", dabakan=True),
    # Pagsanjan: water-bright gongs running over a slow pulse
    "tidelost": MusicSpec(164.81, "slendro", 92, (0, 2, 4, 1, 3, 2, 4, 0), pad=0.45, bass=0.45, arp=0.55, arp_step=2, melody=0.5,
                          drums=1, lead_wave="flute", arp_voice="gong", dabakan=True),
    # Batanes: open and airy, fast shimmer, wind in the flute
    "skyglass": MusicSpec(196.0, "pent_major", 104, (0, 1, 3, 0, 4, 1, 3, 2), pad=0.4, bass=0.4, arp=0.5, arp_step=1, melody=0.55,
                          drums=2, lead_wave="flute", arp_voice="bell", dabakan=True),
    # Taal: driving drums and struck gongs
    "cinderforge": MusicSpec(130.81, "phrygian", 120, (0, 0, 1, 0, 5, 4, 1, 0), pad=0.35, bass=0.8, arp=0.3, arp_step=1,
                             melody=0.6, drums=3, lead_wave="gong", dabakan=True),
    # the dragon's mouth: slow, heavy, dark
    "eclipse": MusicSpec(92.5, "pent_minor", 90, (0, 3, 2, 4, 0, 3, 1, 4), pad=0.75, bass=0.7, arp=0.4, arp_step=2, melody=0.55,
                         drums=2, lead_wave="gong", arp_voice="gong", dabakan=True),
    "boss": MusicSpec(110.0, "harmonic", 142, (0, 0, 5, 4, 0, 0, 5, 6), pad=0.4, bass=0.9, arp=0.5, arp_step=1, melody=0.6,
                      drums=3, lead_wave="saw", dabakan=True),
    "victory": MusicSpec(261.63, "pent_major", 112, (0, 3), pad=0.6, arp=0.6, arp_step=2, melody=0.7, drums=0,
                         lead_wave="flute", arp_voice="gong", loop=False),
    "defeat": MusicSpec(196.0, "pent_minor", 76, (0, 3), pad=0.7, arp=0.0, melody=0.5, drums=0, lead_wave="flute", loop=False),
}
MUSIC_NAMES: tuple[str, ...] = tuple(MUSIC_SPECS)


def _degree_freq(spec: MusicSpec, degree: int, octave: int = 0) -> float:
    scale = MODES[spec.mode]
    n = len(scale)
    semis = scale[degree % n] + 12 * (degree // n) + 12 * octave
    return _pitch(spec.root, semis)


class _Track:
    """Float stereo buffer that wraps notes around the loop point so the loop is seamless."""

    def __init__(self, seconds: float, loop: bool, tail: float = 2.5):
        self.n = _n(seconds)
        self.loop = loop
        self.buf = np.zeros((self.n + (0 if loop else _n(tail)), 2))

    def add(self, start: float, mono: np.ndarray, position: float = 0.0) -> None:
        sig = pan(mono, position)
        s = int(start * SR) % self.n if self.loop else int(start * SR)
        if self.loop:
            first = min(len(sig), self.n - s)
            self.buf[s:s + first] += sig[:first]
            rest = len(sig) - first
            while rest > 0:                                  # wrap past the loop point
                chunk = min(rest, self.n)
                self.buf[:chunk] += sig[first:first + chunk]
                first += chunk
                rest -= chunk
        else:
            end = min(len(self.buf), s + len(sig))
            self.buf[s:end] += sig[: end - s]


def _pad_voice(freq: float, seconds: float) -> np.ndarray:
    n = _n(seconds)
    t = _t(n)
    sig = (np.sin(2 * np.pi * freq * t) + 0.5 * np.sin(2 * np.pi * freq * 1.004 * t)
           + 0.3 * _osc(freq * 0.998 * t, "tri"))
    return sig * envelope(n, min(0.7, seconds * 0.3), release=min(1.0, seconds * 0.4)) / 1.8


def _pluck(freq: float, seconds: float, wave: str = "tri") -> np.ndarray:
    n = _n(seconds)
    sig = _osc(freq * _t(n), wave) * 0.7 + np.sin(2 * np.pi * freq * 2 * _t(n)) * 0.25
    return sig * expdecay(n, 6.5) * envelope(n, 0.003, release=0.05)


def _bass_voice(freq: float, seconds: float) -> np.ndarray:
    n = _n(seconds)
    sig = lowpass(_osc(freq * _t(n), "saw"), 14) + np.sin(2 * np.pi * freq * _t(n))
    return sig * expdecay(n, 3.0) * envelope(n, 0.01, release=0.08) * 0.7


def _lead_voice(freq: float, seconds: float, wave: str) -> np.ndarray:
    n = _n(seconds)
    sig = tone(freq, seconds, wave, vibrato=1.0 if wave == "tri" else 0.0)
    if wave == "saw":
        sig = lowpass(sig, 4)
    return sig * envelope(n, 0.02, 0.1, 0.7, min(0.3, seconds * 0.5)) * 0.6


def _gong(freq: float, seconds: float, strike: float = 1.0) -> np.ndarray:
    """A struck bossed gong: inharmonic partials with a long shimmering tail."""
    n = _n(seconds)
    t = _t(n)
    out = np.zeros(n)
    for ratio, amp, decay in ((1.0, 1.0, 2.2), (1.52, 0.55, 3.0), (2.12, 0.4, 4.2), (2.74, 0.26, 5.5), (3.9, 0.12, 8.0)):
        out += amp * np.sin(2 * np.pi * freq * ratio * t + 0.4 * np.sin(2 * np.pi * 5 * t)) * np.exp(-t * decay)
    return out * envelope(n, 0.004, release=min(0.4, seconds * 0.3)) * 0.55 * strike


def _flute(freq: float, seconds: float, rng_seed: int = 0) -> np.ndarray:
    """A breathy bamboo flute: a soft sine with a little air and a gentle vibrato."""
    n = _n(seconds)
    t = _t(n)
    vib = 1.0 + 0.006 * np.sin(2 * np.pi * 5.2 * t) * np.minimum(1.0, t * 3)
    phase = np.cumsum(freq * vib) / SR
    tone_ = np.sin(2 * np.pi * phase) + 0.18 * np.sin(4 * np.pi * phase) + 0.06 * np.sin(6 * np.pi * phase)
    air = lowpass(np.random.default_rng(rng_seed + int(freq)).uniform(-1, 1, n), 5) * 0.12
    return (tone_ + air) * envelope(n, 0.05, 0.1, 0.8, min(0.35, seconds * 0.5)) * 0.55


def _dabakan(rng: np.random.Generator, low: bool = True) -> np.ndarray:
    """A skin drum: a quick pitch drop with a slap of air."""
    n = _n(0.3)
    body = sweep(210 if low else 330, 95 if low else 160, 0.3, "sine", 0.4) * expdecay(n, 9)
    slap = highpass(noise(n, rng), 6) * expdecay(n, 40) * 0.5
    return (body + slap) * 0.95 * envelope(n, 0.002, release=0.02)


def _kick() -> np.ndarray:
    n = _n(0.28)
    return sweep(140, 42, 0.28, "sine", 0.5) * expdecay(n, 11) * 1.1


def _snare(rng: np.random.Generator) -> np.ndarray:
    n = _n(0.2)
    return (highpass(noise(n, rng), 5) * expdecay(n, 22) * 0.7 + tone(190, 0.2, "tri") * expdecay(n, 25) * 0.4) * envelope(n, 0.002, release=0.02)


def _hat(rng: np.random.Generator, open_: bool = False) -> np.ndarray:
    n = _n(0.12 if open_ else 0.05)
    return highpass(noise(n, rng), 3) * expdecay(n, 14 if open_ else 55) * 0.25 * envelope(n, 0.002, release=0.01)


def _melody_notes(spec: MusicSpec, rng: np.random.Generator, bars: int) -> list[tuple[float, float, int]]:
    size = len(MODES[spec.mode])
    """A repeating two-bar motif: (beat offset, length in beats, scale degree)."""
    notes: list[tuple[float, float, int]] = []
    degree = size                                            # start an octave up
    motif_seed = int(rng.integers(1 << 30))
    for bar in range(0, bars, 2):
        motif_rng = np.random.default_rng(motif_seed)         # the same motif every two bars
        beat = 0.0
        while beat < 8.0:
            length = float(motif_rng.choice([0.5, 1.0, 1.0, 1.5, 2.0]))
            if beat + length > 8.0:
                length = 8.0 - beat
            if motif_rng.random() < 0.82:
                chord_root = spec.progression[(bar + int(beat // 4)) % len(spec.progression)]
                degree = int(np.clip(degree + motif_rng.choice([-2, -1, -1, 0, 1, 1, 2]), size - 3, size + 4))
                if motif_rng.random() < 0.35:                # land on a chord tone now and then
                    degree = int(np.clip(chord_root + size + int(motif_rng.choice([0, 2, 4])), size - 3, size + 4))
                notes.append((bar * 4 + beat, length, degree))
            beat += length
    return notes


def make_music(name: str) -> np.ndarray:
    """Stereo int16 samples for a music track. Loop tracks wrap seamlessly; stingers play once."""
    spec = MUSIC_SPECS[name]
    rng = np.random.default_rng(_seed(name))
    bars = len(spec.progression)
    beat = 60.0 / spec.bpm
    bar_len = 4 * beat
    track = _Track(bars * bar_len, spec.loop)

    for bar, root in enumerate(spec.progression):
        start = bar * bar_len
        chord = [root, root + 2, root + 4]
        if spec.pad:                                          # slow pads
            for k, degree in enumerate(chord):
                f = _degree_freq(spec, degree, 0)
                track.add(start, _pad_voice(f, bar_len * 1.05) * spec.pad * 0.35, (-0.5, 0.0, 0.5)[k])
        if spec.bass:                                         # bass line
            low = _degree_freq(spec, root, -1)
            steps = 8 if spec.drums >= 3 else 4
            for s in range(steps):
                if spec.drums >= 3 or s % 2 == 0 or spec.drums == 0:
                    f = low * (2.0 if (s % 4 == 3 and spec.drums >= 2) else 1.0)
                    track.add(start + s * bar_len / steps, _bass_voice(f, bar_len / steps * 1.6) * spec.bass * 0.55, -0.1)
        if spec.arp:                                          # arpeggio
            sixteenth = bar_len / 16
            pattern = (0, 1, 2, 1, 2, 1, 0, 1)
            for i in range(0, 16, spec.arp_step):
                degree = chord[pattern[(i // spec.arp_step) % len(pattern)] % 3] + len(MODES[spec.mode])
                f = _degree_freq(spec, degree, 0)
                kind = spec.arp_voice or ("bell" if spec.mode in ("dorian", "lydian", "major", "pent_major", "slendro") else "pluck")
                if kind == "gong":
                    note = _gong(f * 2, 0.55) * 0.9
                elif kind == "bell":
                    note = _bell(f, 0.7, 0.7) * 0.5
                else:
                    note = _pluck(f, 0.45, "tri")
                track.add(start + i * sixteenth, note * spec.arp * 0.45, -0.4 + 0.8 * ((i // spec.arp_step) % 2))
        if spec.drums:                                        # drums
            for b in range(4):
                bt = start + b * beat
                if spec.drums >= 3 or b in (0, 2) or (spec.drums == 2 and b == 3 and bar % 2 == 1):
                    hit = _dabakan(rng, True) if spec.dabakan else _kick()
                    track.add(bt, hit * (0.55 if spec.drums == 1 else 0.7), 0.0)
                if b in (1, 3) and spec.drums >= 2:
                    track.add(bt, (_dabakan(rng, False) * 0.7 if spec.dabakan else _snare(rng) * 0.55), 0.1)
                hats = 2 if spec.drums >= 2 else 1
                for h in range(hats):
                    track.add(bt + h * beat / hats, _hat(rng, open_=(h == 1 and b == 3)) * 0.6, 0.35)

    if spec.melody:                                           # a repeating two-bar motif
        for beat_pos, length, degree in _melody_notes(spec, rng, bars):
            f = _degree_freq(spec, degree, 0)
            if spec.lead_wave == "flute":
                voice = _flute(f, max(0.35, length * beat * 1.1))
            elif spec.lead_wave == "gong":
                voice = _gong(f, max(0.8, length * beat * 1.6)) * 1.3
            elif spec.mode in ("dorian", "lydian"):
                voice = _bell(f, max(0.5, length * beat), 0.8) * 0.6
            else:
                voice = _lead_voice(f, length * beat * 1.1, spec.lead_wave)
            track.add(beat_pos * beat, voice * spec.melody * 0.6, 0.25)

    out = track.buf
    peak = float(np.max(np.abs(out))) or 1.0
    out = out / peak * spec.gain
    if not spec.loop:
        fade = _n(0.6)
        out[-fade:] *= np.linspace(1.0, 0.0, fade)[:, None]
    return np.ascontiguousarray((np.clip(out, -1.0, 1.0) * 32767).astype(np.int16))


def music_seconds(name: str) -> float:
    spec = MUSIC_SPECS[name]
    return len(spec.progression) * 4 * 60.0 / spec.bpm
