"""Audio engine: synthesised music with crossfades, throttled sound effects and per-channel volumes.

Everything is best-effort: a missing sound device never stops the game. Optional ``assets/audio/<name>.ogg``
files override a synthesised sound or track of the same name.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

from ..session import GameEvent, GameEventType, SessionState
from . import synth


def synthesize_tone(
    frequencies: tuple[float, ...], duration: float, sample_rate: int = 22050
) -> np.ndarray:
    """Create a short, softly faded stereo chord (kept for simple callers and tests)."""
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


# ------------------------------------------------------------------ what plays when
LOOT_SOUNDS = {"heart": "loot_heart", "regen": "loot_regen", "shield": "loot_shield", "boost": "loot_boost"}
REACTION_SOUNDS = {"SHOCKED": "reaction_shock", "STEAM": "reaction_steam", "DOUSED": "reaction_steam", "FIRESTORM": "reaction_firestorm"}
NOTE_SOUNDS = {
    "hazard": "hazard_warning",
    "boss_phase": "boss_phase",
    "shield_block": "shield_block",
    "bomb_blast": "bomb_blast",
    "laser_fire": "laser_fire",
}
# volume of each effect relative to the SFX slider
GAINS = {
    "cast_earth": 0.5, "cast_water": 0.45, "cast_air": 0.4, "cast_fire": 0.45, "cast_lightning": 0.45,
    "orb_block": 0.5, "enemy_defeated": 0.7, "ui_move": 0.5, "ui_select": 0.7, "ui_back": 0.6, "heartbeat": 0.8,
    "laser_fire": 0.6, "bomb_blast": 0.8, "reaction_shock": 0.8, "reaction_steam": 0.7, "reaction_firestorm": 0.8, "shield_block": 0.6, "defuse": 0.6, "interrupt": 0.6,
}
# minimum seconds between two plays of the same effect (stops fast-fire spam)
MIN_GAP = {
    "cast_earth": 0.12, "cast_water": 0.09, "cast_air": 0.08, "cast_fire": 0.09, "cast_lightning": 0.11,
    "enemy_defeated": 0.05, "orb_block": 0.08, "shield_block": 0.2, "bomb_blast": 0.1, "player_hit": 0.12,
    "defuse": 0.1, "interrupt": 0.1, "ui_move": 0.03,
}


def sfx_for_event(event: GameEvent) -> list[str]:
    """Sound effect names that a game event should trigger (pure, so it is easy to test)."""
    kind, data = event.type, dict(event.data or {})
    if kind is GameEventType.CAST:
        names = [f"cast_{event.detail}"] if event.detail in ("earth", "water", "air", "fire", "lightning") else []
        if data.get("popped"):
            names.append("orb_block")
        if data.get("defused"):
            names.append("defuse")
        if data.get("interrupted"):
            names.append("interrupt")
        for reaction in data.get("reactions", []):
            sound = REACTION_SOUNDS.get(reaction["name"])
            if sound and sound not in names:
                names.append(sound)
        return names
    if kind is GameEventType.ENEMY_DEFEATED:
        return ["boss_defeated" if data.get("boss") else "enemy_defeated"]
    if kind is GameEventType.PLAYER_HIT:
        return ["player_hit"]
    if kind is GameEventType.LIFE_LOST:
        return ["life_lost"]
    if kind is GameEventType.WAVE_STARTED:
        return ["boss_incoming" if event.detail == "boss" else "wave_started"]
    if kind is GameEventType.WAVE_COMPLETE:
        return ["wave_complete"]
    if kind is GameEventType.LEVEL_COMPLETE:
        return ["level_complete"]
    if kind is GameEventType.LEVEL_FAILED:
        return ["level_failed"]
    if kind is GameEventType.CONVERGENCE_READY:
        return ["convergence_ready"]
    if kind is GameEventType.CONVERGENCE_STARTED:
        return ["convergence_started"]
    if kind is GameEventType.LOOT_COLLECTED:
        return ["loot_mana" if event.detail.startswith("mana") else LOOT_SOUNDS.get(event.detail, "loot_heart")]
    if kind is GameEventType.COMBAT_FX:
        name = NOTE_SOUNDS.get(event.detail)
        return [name] if name else []
    return []


def music_for(scene: str, level_id: str | None, state: SessionState | None = None, result: str | None = None) -> str:
    """Which music track belongs to the current screen."""
    stage = level_id if level_id in synth.MUSIC_SPECS else "menu"
    if scene in ("gameplay", "pause"):
        return "boss" if state is SessionState.BOSS else stage
    if scene in ("story", "briefing"):
        return stage
    if scene == "results":
        return "victory" if result == "complete" else "defeat"
    return "menu"


# ------------------------------------------------------------------ the manager
class AudioManager:
    """Best-effort audio: absent devices or files never stop gameplay."""

    CHANNELS = 32
    RESERVED = 2                     # channels 0 and 1 are the music crossfade pair

    def __init__(self, asset_root: Path, master: float, music: float, sfx: float,
                 background: bool = True, clock: Callable[[], float] = time.monotonic):
        self.asset_root = asset_root
        self.master, self.music, self.sfx = master, music, sfx
        self.available = False
        self.current_music: str | None = None
        self.wanted_music: str | None = None
        self.duck = 1.0                              # 0..1, lowered while paused
        self._clock = clock
        self._sounds: dict[str, object] = {}
        self._arrays: dict[str, np.ndarray] = {}     # generated off the main thread, turned into Sounds here
        self._lock = threading.Lock()
        self._last_played: dict[str, float] = {}
        self._channels: list[object] = []
        self._active = 0
        self._pygame = None
        self._thread: threading.Thread | None = None
        try:
            import pygame

            self._pygame = pygame
            if not pygame.mixer.get_init():
                pygame.mixer.pre_init(synth.SR, -16, 2, 512)
                pygame.mixer.init()
            pygame.mixer.set_num_channels(self.CHANNELS)
            pygame.mixer.set_reserved(self.RESERVED)
            self._channels = [pygame.mixer.Channel(i) for i in range(self.RESERVED)]
            self.available = True
        except Exception:
            self.available = False
        if self.available and background:
            self._thread = threading.Thread(target=self._generate_all, name="audio-synth", daemon=True)
            self._thread.start()

    # -- generation ---------------------------------------------------------
    def _generate_all(self) -> None:
        for name in ("menu", *[n for n in synth.MUSIC_NAMES if n != "menu"], *synth.SFX_NAMES):
            try:
                samples = synth.make_music(name) if name in synth.MUSIC_SPECS else synth.make_sfx(name)
            except Exception:
                continue
            with self._lock:
                self._arrays[name] = samples

    def wait_until_ready(self, timeout: float = 10.0) -> bool:
        """Block until background generation finished (used by tests)."""
        if self._thread is not None:
            self._thread.join(timeout)
        self.update()
        return self._thread is None or not self._thread.is_alive()

    def _sound(self, name: str):
        """The Sound for a name, turning generated arrays into mixer sounds on the calling thread."""
        sound = self._sounds.get(name)
        if sound is not None or not self.available:
            return sound
        pygame = self._pygame
        try:
            override = self.asset_root / "audio" / f"{name}.ogg"
            if override.exists():
                sound = pygame.mixer.Sound(str(override))
            else:
                with self._lock:
                    samples = self._arrays.pop(name, None)
                if samples is None:
                    if name in synth.MUSIC_SPECS:
                        return None                        # still being composed: try again later
                    samples = synth.make_sfx(name)         # effects are tiny, so make them on demand
                sound = pygame.sndarray.make_sound(samples)
            self._sounds[name] = sound
            return sound
        except Exception:
            return None

    # -- volumes --------------------------------------------------------------
    def set_volumes(self, master: float | None = None, music: float | None = None, sfx: float | None = None) -> None:
        if master is not None:
            self.master = max(0.0, min(1.0, master))
        if music is not None:
            self.music = max(0.0, min(1.0, music))
        if sfx is not None:
            self.sfx = max(0.0, min(1.0, sfx))
        self._apply_music_volume()

    def _music_volume(self) -> float:
        return self.master * self.music * self.duck

    def _apply_music_volume(self) -> None:
        if self.available and self._channels:
            try:
                self._channels[self._active].set_volume(self._music_volume())
            except Exception:
                pass

    def set_duck(self, level: float) -> None:
        """Quieter music while paused."""
        self.duck = max(0.0, min(1.0, level))
        self._apply_music_volume()

    # -- sound effects ------------------------------------------------------------
    def play(self, name: str) -> bool:
        """Play a sound effect. Returns False when it was skipped (no audio, unknown name, throttled)."""
        if not self.available:
            return False
        now = self._clock()
        gap = MIN_GAP.get(name, 0.0)
        if gap and now - self._last_played.get(name, -1e9) < gap:
            return False
        sound = self._sound(name)
        if sound is None:
            return False
        try:
            sound.set_volume(max(0.0, min(1.0, self.master * self.sfx * GAINS.get(name, 1.0))))
            sound.play()
            self._last_played[name] = now
            return True
        except Exception:
            return False

    def play_event(self, event: GameEvent) -> None:
        for name in sfx_for_event(event):
            self.play(name)

    # -- music ---------------------------------------------------------------------
    def play_music(self, name: str, fade_ms: int = 1400) -> None:
        """Ask for a track; it crossfades in as soon as it is composed. Cheap to call every frame."""
        self.wanted_music = name
        self.update(fade_ms)

    def update(self, fade_ms: int = 1400) -> None:
        """Start the wanted track once it is ready (call once per frame)."""
        name = self.wanted_music
        if not self.available or name is None or name == self.current_music:
            return
        sound = self._sound(name)
        if sound is None:
            return
        try:
            spec = synth.MUSIC_SPECS.get(name)
            incoming = 1 - self._active if self.current_music is not None else self._active
            old, new = self._channels[self._active], self._channels[incoming]
            if self.current_music is not None:
                old.fadeout(fade_ms)
            new.set_volume(self._music_volume())
            new.play(sound, loops=-1 if (spec is None or spec.loop) else 0, fade_ms=fade_ms)
            self._active = incoming
            self.current_music = name
        except Exception:
            return

    def stop_music(self, fade_ms: int = 800) -> None:
        self.wanted_music = None
        if self.available:
            try:
                for channel in self._channels:
                    channel.fadeout(fade_ms)
            except Exception:
                pass
        self.current_music = None
