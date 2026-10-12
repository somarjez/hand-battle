import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from pathlib import Path

import numpy as np
import pytest

from elemental_convergence.content import load_levels
from elemental_convergence.presentation import synth
from elemental_convergence.presentation.audio import AudioManager, GAINS, MIN_GAP, music_for, sfx_for_event
from elemental_convergence.session import GameEvent, GameEventType, SessionState

ASSETS = Path(__file__).parents[1] / "elemental_convergence" / "assets"


# ------------------------------------------------------------------ synthesis
@pytest.mark.parametrize("name", synth.SFX_NAMES)
def test_every_sound_effect_is_a_clean_audible_stereo_clip(name):
    clip = synth.make_sfx(name)
    assert clip.dtype == np.int16 and clip.ndim == 2 and clip.shape[1] == 2
    assert 0.03 < len(clip) / synth.SR < 3.0
    peak = np.abs(clip).max()
    assert 3000 < peak <= 32767 * 0.82, "audible but never clipping"
    assert np.sqrt((clip.astype(float) ** 2).mean()) > 150
    assert abs(int(clip[0].sum())) < 3000 and abs(int(clip[-1].sum())) < 3000, "starts and ends near silence (no clicks)"


def test_synthesis_is_deterministic():
    for name in ("cast_fire", "convergence_started", "boss_defeated"):
        assert np.array_equal(synth.make_sfx(name), synth.make_sfx(name))
    assert np.array_equal(synth.make_music("menu"), synth.make_music("menu"))


@pytest.mark.parametrize("name", synth.MUSIC_NAMES)
def test_every_music_track_is_long_audible_and_unclipped(name):
    track = synth.make_music(name)
    spec = synth.MUSIC_SPECS[name]
    assert track.dtype == np.int16 and track.shape[1] == 2
    seconds = len(track) / synth.SR
    assert (seconds >= 12.0) if spec.loop else (3.0 <= seconds <= 12.0)
    f = track.astype(float) / 32767
    assert 0.3 < np.abs(f).max() <= 0.75 and np.sqrt((f ** 2).mean()) > 0.04
    assert abs(len(track) / synth.SR - (synth.music_seconds(name) + (0 if spec.loop else 2.5))) < 0.05


@pytest.mark.parametrize("name", [n for n in synth.MUSIC_NAMES if synth.MUSIC_SPECS[n].loop])
def test_looping_tracks_have_no_click_at_the_loop_point(name):
    f = synth.make_music(name).astype(float) / 32767
    assert np.abs(f[0] - f[-1]).max() < 0.12


def test_stingers_fade_out_and_every_stage_has_its_own_theme():
    for name in ("victory", "defeat"):
        t = synth.make_music(name).astype(float) / 32767
        assert np.abs(t[-200:]).max() < 0.02
    stages = set(load_levels())
    assert stages <= set(synth.MUSIC_SPECS) and {"menu", "boss", "victory", "defeat"} <= set(synth.MUSIC_SPECS)
    tracks = [synth.make_music(n) for n in stages]
    assert len({t.tobytes() for t in tracks}) == len(tracks)
    assert len({synth.MUSIC_SPECS[n].bpm for n in stages}) >= 4, "stages should differ in tempo"


def test_building_blocks():
    assert synth.envelope(1000, 0.001, release=0.01)[0] == 0.0
    assert len(synth.tone(440, 0.1)) == int(0.1 * synth.SR)
    stereo = synth.pan(np.ones(10), -1.0)
    assert stereo[:, 0].mean() > 0.99 and abs(stereo[:, 1]).max() < 1e-9
    with pytest.raises(KeyError):
        synth.make_sfx("nope")


# ------------------------------------------------------------------ event -> sound mapping
def ev(kind, detail="", **data):
    return GameEvent(kind, detail, data or None)


def test_every_gameplay_event_has_a_sound():
    cases = [
        (ev(GameEventType.CAST, "fire"), ["cast_fire"]),
        (ev(GameEventType.CAST, "earth", popped=[(1, 1)], defused=[(2, 2)], interrupted=[(3, 3)]), ["cast_earth", "orb_block", "defuse", "interrupt"]),
        (ev(GameEventType.ENEMY_DEFEATED, "shooter", boss=False), ["enemy_defeated"]),
        (ev(GameEventType.ENEMY_DEFEATED, "stone_guardian", boss=True), ["boss_defeated"]),
        (ev(GameEventType.PLAYER_HIT, "orb"), ["player_hit"]),
        (ev(GameEventType.LIFE_LOST, "2"), ["life_lost"]),
        (ev(GameEventType.WAVE_STARTED, "2"), ["wave_started"]),
        (ev(GameEventType.WAVE_STARTED, "boss"), ["boss_incoming"]),
        (ev(GameEventType.WAVE_COMPLETE, "1"), ["wave_complete"]),
        (ev(GameEventType.LEVEL_COMPLETE, "stonewake"), ["level_complete"]),
        (ev(GameEventType.LEVEL_FAILED), ["level_failed"]),
        (ev(GameEventType.CONVERGENCE_READY), ["convergence_ready"]),
        (ev(GameEventType.CONVERGENCE_STARTED), ["convergence_started"]),
        (ev(GameEventType.LOOT_COLLECTED, "heart"), ["loot_heart"]),
        (ev(GameEventType.LOOT_COLLECTED, "shield"), ["loot_shield"]),
        (ev(GameEventType.LOOT_COLLECTED, "mana:fire"), ["loot_mana"]),
        (ev(GameEventType.COMBAT_FX, "hazard"), ["hazard_warning"]),
        (ev(GameEventType.COMBAT_FX, "boss_phase"), ["boss_phase"]),
        (ev(GameEventType.COMBAT_FX, "bomb_blast"), ["bomb_blast"]),
        (ev(GameEventType.COMBAT_FX, "attack"), []),
    ]
    for event, expected in cases:
        assert sfx_for_event(event) == expected, event
        assert all(name in synth.SFX_NAMES for name in expected)
    assert set(GAINS) <= set(synth.SFX_NAMES) and set(MIN_GAP) <= set(synth.SFX_NAMES)


def test_music_follows_the_screen():
    assert music_for("menu", None) == "menu" and music_for("settings", "stonewake") == "menu"
    assert music_for("story", "tidelost") == "tidelost" and music_for("briefing", "skyglass") == "skyglass"
    assert music_for("gameplay", "cinderforge", SessionState.ACTIVE) == "cinderforge"
    assert music_for("gameplay", "cinderforge", SessionState.BOSS) == "boss"
    assert music_for("pause", "eclipse", SessionState.BOSS) == "boss"
    assert music_for("results", "eclipse", None, "complete") == "victory"
    assert music_for("results", "eclipse", None, "failed") == "defeat"
    assert music_for("gameplay", "unknown-level", SessionState.ACTIVE) == "menu"


# ------------------------------------------------------------------ the manager
class Clock:
    now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def audio():
    clock = Clock()
    manager = AudioManager(ASSETS, 0.8, 0.6, 0.8, background=True, clock=clock)
    manager.clock = clock
    yield manager
    manager.stop_music(0)


def test_manager_generates_everything_and_plays_every_effect(audio):
    assert audio.available
    assert audio.wait_until_ready(30)
    for name in synth.SFX_NAMES:
        audio.clock.now += 5
        assert audio.play(name), name


def test_fast_fire_sounds_are_throttled_but_distinct_sounds_are_not(audio):
    audio.wait_until_ready(30)
    audio.clock.now += 5
    assert audio.play("cast_fire")
    assert not audio.play("cast_fire")                     # same instant: skipped
    assert audio.play("cast_water")
    audio.clock.now += MIN_GAP["cast_fire"] + 0.01
    assert audio.play("cast_fire")


def test_unknown_sounds_never_crash(audio):
    assert audio.play("does_not_exist") is False


def test_music_crossfades_between_tracks_and_ignores_repeats(audio):
    audio.wait_until_ready(30)
    audio.play_music("menu", 10)
    assert audio.current_music == "menu"
    first = audio._active
    audio.play_music("menu", 10)
    assert audio._active == first, "asking for the same track again must not restart it"
    audio.play_music("tidelost", 10)
    assert audio.current_music == "tidelost" and audio._active != first
    audio.play_music("boss", 10)
    assert audio.current_music == "boss"
    audio.stop_music(0)
    assert audio.current_music is None


def test_music_that_is_still_being_composed_starts_as_soon_as_it_is_ready():
    manager = AudioManager(ASSETS, 0.8, 0.6, 0.8, background=False)
    assert manager.available
    manager.play_music("eclipse", 10)
    assert manager.current_music is None                    # nothing generated yet
    manager._arrays["eclipse"] = synth.make_music("eclipse")
    manager.update(10)
    assert manager.current_music == "eclipse"
    manager.stop_music(0)


def test_volumes_are_clamped_and_apply_to_music(audio):
    audio.wait_until_ready(30)
    audio.play_music("menu", 10)
    audio.set_volumes(master=5, music=-1, sfx=0.5)
    assert (audio.master, audio.music, audio.sfx) == (1.0, 0.0, 0.5)
    audio.set_volumes(master=0.5, music=0.5)
    audio.set_duck(0.4)
    assert audio._music_volume() == pytest.approx(0.1)
    assert audio._channels[audio._active].get_volume() == pytest.approx(0.1, abs=0.02)


def test_audio_is_optional(monkeypatch):
    import pygame
    monkeypatch.setattr(pygame.mixer, "init", lambda *a, **k: (_ for _ in ()).throw(pygame.error("no device")))
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)
    manager = AudioManager(ASSETS, 1, 1, 1)
    assert not manager.available
    assert manager.play("cast_fire") is False
    manager.play_music("menu")
    manager.update()
    manager.set_volumes(0.5)
    manager.stop_music()
