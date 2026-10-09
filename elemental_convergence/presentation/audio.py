from __future__ import annotations

from pathlib import Path


class AudioManager:
    """Best-effort audio: absent devices or files never stop gameplay."""

    def __init__(self, asset_root: Path, master: float, music: float, sfx: float):
        self.asset_root = asset_root
        self.master = master
        self.music = music
        self.sfx = sfx
        self.available = False
        self._sounds: dict[str, object] = {}
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
                if not path.exists():
                    return
                sound = pygame.mixer.Sound(path)
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
        except Exception:
            return

