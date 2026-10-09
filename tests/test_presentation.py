import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import numpy as np

from elemental_convergence.app import camera_to_surface
from elemental_convergence.content import load_levels
from elemental_convergence.models import Difficulty
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


def test_first_new_game_routes_through_calibration_then_story():
    model = AppModel(load_levels(), SaveData(), Settings(camera_id=None))

    model.new_game()
    assert model.scene is SceneId.CALIBRATION

    model.finish_calibration(camera_id=1)
    assert model.scene is SceneId.STORY
    assert model.current_level_id == "stonewake"


def test_returning_player_can_continue_at_first_incomplete_level():
    save = SaveData(
        unlocked_levels=("stonewake", "tidelost", "skyglass"),
        completed_levels=("stonewake", "tidelost"),
    )
    model = AppModel(load_levels(), save, Settings(camera_id=0))

    model.continue_game()

    assert model.scene is SceneId.STORY
    assert model.current_level_id == "skyglass"


def test_pause_returns_to_the_same_gameplay_scene():
    model = AppModel(load_levels(), SaveData(), Settings(camera_id=0))
    model.select_level("stonewake")
    model.begin_gameplay()

    model.pause()
    assert model.scene is SceneId.PAUSE
    model.resume()
    assert model.scene is SceneId.GAMEPLAY


def test_renderer_draws_readable_gameplay_without_optional_assets():
    pygame.init()
    surface = pygame.Surface((1280, 720))
    renderer = GameRenderer((1280, 720), asset_root=None)
    session = GameSession(load_levels(), seed=4)
    session.start_level("stonewake", Difficulty.BALANCED)

    renderer.draw_gameplay(surface, session.snapshot(), camera_surface=None)

    assert surface.get_at((20, 20)) != pygame.Color(0, 0, 0, 255)
    pygame.quit()

