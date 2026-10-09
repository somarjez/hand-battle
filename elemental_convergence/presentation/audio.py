from __future__ import annotations

from pathlib import Path

import numpy as np


def synthesize_tone(
    frequencies: tuple[float, ...], duration: float, sample_rate: int = 22050
) -> np.ndarray:
    """Create a short, softly faded stereo chord for asset-free audio."""
    count = max(1, int(duration * sample_rate))
    time_axis = np.arange(count, dtype=np.float64) / sample_rate
    wave = sum(np.sin(2 * np.pi * frequency * time_axis) for frequency in frequencies)
    wave /= max(1, len(frequencies))
    fade_count = min(count // 2, max(1, int(sample_rate * 0.03)))
    envelope = np.ones(count)
    envelope[:fade_count] = np.linspace(0.0, 1.0, fade_count)
    envelope[-fade_count:] = np.linspace(1.0, 0.0, fade_count)
    mono = (wave * envelope * 9000).astype(np.int16)
    return np.ascontiguousarray(np.column_stack((mono, mono)))


class AudioManager:
    """Best-effort audio: absent devices or files never stop gameplay."""

    def __init__(self, asset_root: Path, master: float, music: float, sfx: float):
        self.asset_root = asset_root
        self.master = master
        self.music = music
        self.sfx = sfx
        self.available = False
        self._sounds: dict[str, object] = {}
        self._music = None
        try:
            import pygame

            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self.available = True
        except Exception:
            self.available = False

    def play(self, name: str) -> None:
        if not self.available:
            return
        try:
            import pygame

            sound = self._sounds.get(name)
            if sound is None:
                path = self.asset_root / "audio" / f"{name}.ogg"
                if path.exists():
                    sound = pygame.mixer.Sound(path)
                else:
                    tones = {
                        "cast": (440.0, 660.0),
                        "enemy_defeated": (330.0, 494.0),
                        "life_lost": (165.0, 130.0),
                        "wave_complete": (392.0, 523.0),
                        "level_complete": (262.0, 392.0, 523.0),
                        "convergence_started": (220.0, 440.0, 880.0),
                    }
                    frequencies = tones.get(name, (300.0,))
                    sound = pygame.sndarray.make_sound(synthesize_tone(frequencies, 0.18))
                self._sounds[name] = sound
            sound.set_volume(self.master * self.sfx)
            sound.play()
        except Exception:
            return

    def play_music(self, name: str) -> None:
        if not self.available:
            return
        try:
            import pygame

            path = self.asset_root / "audio" / f"{name}.ogg"
            if path.exists():
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(self.master * self.music)
                pygame.mixer.music.play(-1)
            else:
                self._music = pygame.sndarray.make_sound(
                    synthesize_tone((110.0, 164.81, 220.0), 3.0)
                )
                self._music.set_volume(self.master * self.music * 0.35)
                self._music.play(-1)
        except Exception:
            return

