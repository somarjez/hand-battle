import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import json

import numpy as np
import pygame
import pytest

from elemental_convergence import app as app_module
from elemental_convergence.content import load_levels
from elemental_convergence.models import Difficulty
from elemental_convergence.persistence import Settings, SettingsRepository
from elemental_convergence.presentation.battle_view import BattleView
from elemental_convergence.presentation.scenes import SceneId
from elemental_convergence.quality import GRAPHICS_MODES, QualityGovernor, use_fast_path
from elemental_convergence.session import GameSession
from tests.test_app import FakeVision, goto, press, start_level, tick  # noqa: F401  (fixtures reused)


def feed(governor, seconds, frames):
    for _ in range(frames):
        governor.record(seconds)
    return governor.fast


def test_a_few_slow_frames_do_not_switch_but_a_sustained_run_does():
    g = QualityGovernor()
    assert not feed(g, 0.040, 30), "a hitch is not a trend"
    g = QualityGovernor()
    assert feed(g, 0.030, 200)


def test_a_single_long_frame_among_good_ones_is_ignored():
    g = QualityGovernor()
    for i in range(600):
        g.record(0.045 if i % 120 == 0 else 0.008)
    assert not g.fast


def test_it_only_switches_back_after_a_long_calm_stretch():
    g = QualityGovernor()
    assert feed(g, 0.030, 200)
    assert feed(g, 0.012, 2000), "borderline frames keep the fast path"
    assert feed(g, 0.006, 500)
    assert not feed(g, 0.006, 600)


def test_it_does_not_flicker_when_frame_times_hover_around_the_limit():
    g = QualityGovernor()
    changes = 0
    previous = g.fast
    for i in range(3000):
        g.record(0.017 + 0.004 * ((i // 7) % 2))
        changes += g.fast != previous
        previous = g.fast
    assert changes <= 2


def test_fixed_choices_ignore_the_governor():
    g = QualityGovernor()
    feed(g, 0.05, 300)
    assert use_fast_path("fast", QualityGovernor()) and not use_fast_path("high", g) and use_fast_path("auto", g)
    assert GRAPHICS_MODES == ("auto", "high", "fast")


def test_settings_gain_graphics_and_old_files_still_load(tmp_path):
    old = {"version": 1, "camera_id": 2, "fullscreen": False, "master_volume": 0.5}
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(old))
    loaded = SettingsRepository(path).load()
    assert loaded.graphics == "auto" and loaded.camera_id == 2 and loaded.master_volume == 0.5
    path.write_text(json.dumps({**old, "graphics": "ultra"}))
    assert SettingsRepository(path).load().graphics == "auto", "an unknown value falls back safely"
    path.write_text(json.dumps({**old, "graphics": "fast"}))
    assert Settings.from_dict(json.loads(path.read_text())).graphics == "fast"


def test_the_fast_render_path_gives_the_same_picture_shape():
    session = GameSession(load_levels(), seed=2)
    session.start_level("tidelost", Difficulty.BALANCED)
    view = BattleView(seed=1)
    snap = session.snapshot()
    normal = view.render(snap, None, None, (640, 360))
    view.fast = True
    quick = view.render(snap, None, None, (640, 360))
    assert normal.shape == quick.shape == (360, 640, 3)
    assert np.abs(normal.astype(int) - quick.astype(int)).mean() < 12, "same scene, only the glow is softer"
    for _ in range(3000):
        view.burst(10, 10, (255, 255, 255), 5)
    assert len(view.sparks) <= 600


@pytest.fixture
def app(tmp_path, monkeypatch):
    for var in ("HOME", "APPDATA", "XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(tmp_path))
    monkeypatch.setattr(app_module, "VisionService", FakeVision)
    instance = app_module.Application(camera_override=0, windowed=True)
    yield instance
    instance.audio.stop_music(0)
    pygame.quit()


def test_graphics_is_a_setting_and_a_fixed_choice_overrides_auto(app):
    goto(app, SceneId.SETTINGS)
    labels = [i.label for i in app.menu.items]
    app.menu.index = labels.index("Graphics")
    assert app.menu.current.value_text() == "Auto"
    press(app, pygame.K_RIGHT)
    assert app.model.settings.graphics == "high"
    press(app, pygame.K_RIGHT)
    assert app.model.settings.graphics == "fast" and app.renderer.battle.fast is False
    app._track_quality(0.005)
    assert app.renderer.battle.fast is True
    press(app, pygame.K_RIGHT)
    assert app.model.settings.graphics == "auto"


def test_only_fights_feed_the_governor_so_menus_never_trigger_the_fast_path(app):
    tick(app)
    for _ in range(500):
        app._track_quality(0.080)
    assert not app.renderer.battle.fast and app.governor.average == 0.0
    start_level(app)
    for _ in range(200):
        app._track_quality(0.040)
    assert app.renderer.battle.fast, "a slow fight switches Auto to the fast path"
    goto(app, SceneId.SETTINGS)
    press(app, pygame.K_ESCAPE)
    app.model.set_setting(graphics="high")
    app._track_quality(0.040)
    assert not app.renderer.battle.fast


def test_a_fast_frame_renders_and_scales_without_error(app):
    start_level(app)
    app.model.set_setting(graphics="fast")
    pygame.display.set_mode((1920, 1080), pygame.RESIZABLE)
    app.window = pygame.display.get_surface()
    for _ in range(5):
        app._update(1 / 60)
        app._track_quality(0.01)
        app._render()
    assert app.renderer.battle.fast
