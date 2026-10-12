import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import numpy as np
import pytest

from elemental_convergence.app import camera_to_surface
from elemental_convergence.content import load_levels
from elemental_convergence.models import Difficulty, Element, GestureFrame
from elemental_convergence.persistence import SaveData, Settings
from elemental_convergence.presentation.renderer import GameRenderer
from elemental_convergence.presentation.audio import synthesize_tone
from elemental_convergence.presentation.scenes import AppModel, SceneId
from elemental_convergence.session import GameSession


def test_camera_frame_adapter_accepts_no_frame():
    assert camera_to_surface(None) is None


def test_procedural_audio_fallback_is_stereo_and_audible():
    samples = synthesize_tone((220.0, 330.0), duration=0.1, sample_rate=1000)

    assert samples.shape == (100, 2)
    assert samples.dtype == np.int16
    assert np.max(np.abs(samples)) > 0


def test_first_new_game_routes_through_prologue_then_calibration_then_story():
    model = AppModel(load_levels(), SaveData(), Settings(camera_id=None))

    model.new_game()
    assert model.scene is SceneId.PROLOGUE
    model.finish_prologue()
    assert model.save.prologue_seen and model.scene is SceneId.CALIBRATION

    model.finish_calibration(camera_id=1)
    assert model.scene is SceneId.STORY
    assert model.current_level_id == "stonewake"


def test_failed_saved_camera_forces_recalibration_on_next_game():
    model = AppModel(load_levels(), SaveData(prologue_seen=True), Settings(camera_id=5))

    model.camera_unavailable()
    model.new_game()

    assert model.settings.camera_id is None
    assert model.scene is SceneId.CALIBRATION


def test_returning_player_can_continue_at_first_incomplete_level():
    save = SaveData(
        unlocked_levels=("stonewake", "tidelost", "skyglass"),
        completed_levels=("stonewake", "tidelost"),
    )
    model = AppModel(load_levels(), save, Settings(camera_id=0))

    model.continue_game()

    assert model.scene is SceneId.STORY
    assert model.current_level_id == "skyglass"


def test_fresh_player_cannot_bypass_calibration_with_continue():
    model = AppModel(load_levels(), SaveData(), Settings(camera_id=None))

    model.continue_game()

    assert model.scene is SceneId.CALIBRATION


def test_pause_returns_to_the_same_gameplay_scene():
    model = AppModel(load_levels(), SaveData(), Settings(camera_id=0))
    model.select_level("stonewake")
    model.begin_gameplay()

    model.pause()
    assert model.scene is SceneId.PAUSE
    model.resume()
    assert model.scene is SceneId.GAMEPLAY


def test_accessibility_settings_are_changeable_and_volume_is_clamped():
    model = AppModel(load_levels(), SaveData(), Settings(master_volume=0.95))

    model.adjust_master_volume(0.2)
    model.toggle_reduced_flash()
    model.toggle_reduced_shake()

    assert model.settings.master_volume == 1.0
    assert model.settings.reduced_flash is True
    assert model.settings.reduced_shake is True


def test_difficulty_can_be_selected_in_app():
    model = AppModel(load_levels(), SaveData(), Settings())

    model.set_difficulty(Difficulty.STORY)

    assert model.save.difficulty is Difficulty.STORY


def test_renderer_draws_readable_gameplay_without_optional_assets():
    pygame.init()
    surface = pygame.Surface((1280, 720))
    renderer = GameRenderer((1280, 720), asset_root=None)
    session = GameSession(load_levels(), seed=4)
    session.start_level("stonewake", Difficulty.BALANCED)

    renderer.draw_gameplay(surface, session.snapshot(), camera_surface=None)

    assert surface.get_at((20, 20)) != pygame.Color(0, 0, 0, 255)
    pygame.quit()


def test_calibration_renderer_places_live_preview_inside_frame():
    pygame.init()
    target = pygame.Surface((1280, 720))
    preview = pygame.Surface((320, 240))
    preview.fill((12, 220, 34))
    renderer = GameRenderer((1280, 720), asset_root=None)

    renderer.draw_calibration(target, GestureFrame(1.0, (), True), Element, preview)

    green_pixels = sum(1 for x in range(150, 750, 50) for y in range(200, 550, 50) if target.get_at((x, y)).g > 180)
    assert green_pixels > 5
    pygame.quit()


def test_the_prologue_is_only_shown_once():
    model = AppModel(load_levels(), SaveData(), Settings(camera_id=3))
    model.new_game()
    assert model.scene is SceneId.PROLOGUE
    model.finish_prologue()
    assert model.scene is SceneId.STORY
    model.go(SceneId.MENU)
    model.new_game()
    assert model.scene is SceneId.STORY


def test_settings_return_to_where_they_were_opened_from():
    model = AppModel(load_levels(), SaveData(), Settings())
    model.open_settings()
    assert model.scene is SceneId.SETTINGS
    model.close_settings()
    assert model.scene is SceneId.MENU
    model.go(SceneId.PAUSE)
    model.open_settings()
    model.close_settings()
    assert model.scene is SceneId.PAUSE


def test_set_setting_validates_names_and_clamps_volumes():
    model = AppModel(load_levels(), SaveData(), Settings())
    model.set_setting(music_volume=7, sfx_volume=-3, show_hand_overlay=False)
    assert (model.settings.music_volume, model.settings.sfx_volume, model.settings.show_hand_overlay) == (1.0, 0.0, False)
    with pytest.raises(KeyError):
        model.set_setting(not_a_setting=1)
    with pytest.raises(KeyError):
        model.set_setting(version=9)
