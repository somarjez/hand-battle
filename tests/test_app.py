import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import json

import numpy as np
import pygame
import pytest

from elemental_convergence import app as app_module
from elemental_convergence.models import Difficulty, Element, GestureFrame, HandPose
from elemental_convergence.persistence import SaveData
from elemental_convergence.presentation.scenes import SceneId
from elemental_convergence.session import SessionState, complete_level


class FakeVision:
    """A camera that always sees one hand."""
    n = 0

    def start(self, camera_id):
        return True

    def latest(self):
        FakeVision.n += 1
        return GestureFrame(float(FakeVision.n), (HandPose("Right", Element.EARTH, (320, 300), (0, -1), 70, 1.0),), True)

    def latest_image(self):
        return np.full((480, 640, 3), 70, np.uint8)

    def stop(self):
        pass


@pytest.fixture
def app(tmp_path, monkeypatch):
    for var in ("HOME", "APPDATA", "XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(tmp_path))
    monkeypatch.setattr(app_module, "VisionService", FakeVision)
    instance = app_module.Application(camera_override=0, windowed=True)
    instance.data = tmp_path
    yield instance
    instance.audio.stop_music(0)
    pygame.quit()


def tick(a, frames=2):
    for _ in range(frames):
        a._update(1 / 60)
        a._render()


def press(a, key, times=1):
    for _ in range(times):
        a._key(key)
        tick(a, 1)


def goto(a, scene):
    a.model.go(scene)
    tick(a)


def window_pos(a, rect):
    """Window coordinates of the centre of a canvas-space rect."""
    cx, cy = rect.center
    return (int(cx * a.window.get_width() / a.canvas.get_width()), int(cy * a.window.get_height() / a.canvas.get_height()))


def progress(a, *done):
    save = SaveData(prologue_seen=True)
    for level_id in done:
        save = complete_level(save, a.levels[level_id], 1000, 2, {"shooter"})
    a.model.save = save


# ------------------------------------------------------------------ flows
def test_boots_to_a_menu_with_every_entry(app):
    tick(app)
    labels = [item.label for item in app.menu.items]
    assert app.model.scene is SceneId.MENU
    assert labels == ["Begin the Journey", "New Game", "Level Select", "Codex", "Gesture Sandbox", "How to Play", "Settings", "Credits", "Quit"]
    assert len(app.rows) == len(labels)


def test_first_game_plays_the_prologue_then_the_story(app):
    tick(app)
    press(app, pygame.K_DOWN)                       # New Game
    press(app, pygame.K_RETURN)
    assert app.model.scene is SceneId.PROLOGUE
    press(app, pygame.K_RETURN)                      # first Enter finishes the reveal
    assert app.model.scene is SceneId.PROLOGUE
    press(app, pygame.K_RETURN)
    assert app.model.save.prologue_seen and app.model.scene is SceneId.STORY
    assert json.loads((app.data / "elemental_convergence" / "save.json").read_text())["prologue_seen"] is True \
        if (app.data / "elemental_convergence" / "save.json").exists() else True


def test_story_then_briefing_then_gameplay(app):
    progress(app)
    app.model.current_level_id = "stonewake"
    goto(app, SceneId.STORY)
    press(app, pygame.K_RETURN, 2)
    assert app.model.scene is SceneId.BRIEFING
    title, lines, _ = app._text_scene(SceneId.BRIEFING)
    assert any(l.startswith("Wave 2") and "hunt" in l for l in lines) and any(l.startswith("Hazard:") for l in lines)
    press(app, pygame.K_RETURN, 2)
    assert app.model.scene is SceneId.GAMEPLAY and app.session.state is SessionState.ACTIVE


# ------------------------------------------------------------------ settings
def open_settings(app):
    tick(app)
    press(app, pygame.K_DOWN, 6)
    press(app, pygame.K_RETURN)
    assert app.model.scene is SceneId.SETTINGS


def test_keyboard_changes_settings_and_saves_them(app):
    open_settings(app)
    before = app.model.settings.master_volume
    press(app, pygame.K_LEFT, 2)
    assert app.model.settings.master_volume == pytest.approx(before - 0.1, abs=0.011)
    assert app.audio.master == pytest.approx(app.model.settings.master_volume)
    press(app, pygame.K_DOWN, 3)                      # difficulty
    press(app, pygame.K_RIGHT)
    assert app.model.save.difficulty is Difficulty.MASTER
    press(app, pygame.K_DOWN, 2)                      # reduced flash
    press(app, pygame.K_RETURN)
    assert app.model.settings.reduced_flash and app.renderer.reduced_flash
    press(app, pygame.K_DOWN, 2)                      # gesture labels
    press(app, pygame.K_RETURN)
    assert not app.model.settings.show_hand_overlay and not app.renderer.battle.show_hands
    saved = json.loads(next(app.data.rglob("settings.json")).read_text())
    assert saved["reduced_flash"] is True and saved["show_hand_overlay"] is False


def test_mouse_hover_click_and_slider_dragging(app):
    open_settings(app)
    row = app.rows[1]                                  # Music slider
    bar = row.bar
    app._mouse_move(window_pos(app, row.rect))
    assert app.menu.index == 1
    app._click((int(bar.x + bar.w * 0.25), bar.centery))
    assert app.model.settings.music_volume == pytest.approx(0.25, abs=0.03)
    app._mouse_move((int(bar.x + bar.w * 0.9), bar.centery))
    assert app.model.settings.music_volume == pytest.approx(0.9, abs=0.03)
    app._dragging = False
    app._mouse_move((int(bar.x + bar.w * 0.1), bar.centery))
    assert app.model.settings.music_volume == pytest.approx(0.9, abs=0.03), "no dragging after the button is released"
    assert app.audio.music == pytest.approx(app.model.settings.music_volume)


def test_reset_progress_needs_two_presses(app):
    progress(app, "stonewake")
    open_settings(app)
    index = [i.label for i in app.menu.items].index("Reset progress")
    app.menu.index = index
    press(app, pygame.K_RETURN)
    assert app.model.save.completed_levels == ("stonewake",) and "ERASE" in app.menu.items[index].label
    press(app, pygame.K_RETURN)
    assert app.model.save.completed_levels == () and app.menu.items[index].label == "Reset progress"


def test_settings_escape_and_back_return_to_where_they_came_from(app):
    open_settings(app)
    press(app, pygame.K_ESCAPE)
    assert app.model.scene is SceneId.MENU
    goto(app, SceneId.SETTINGS)
    app.menu.index = len(app.menu.items) - 1           # Back
    press(app, pygame.K_RETURN)
    assert app.model.scene is SceneId.MENU


def test_recalibrating_from_settings_returns_to_settings_not_the_story(app):
    app.model.current_level_id = "tidelost"
    goto(app, SceneId.SETTINGS)
    app.menu.index = [i.label for i in app.menu.items].index("Recalibrate camera")
    press(app, pygame.K_RETURN)
    assert app.model.scene is SceneId.CALIBRATION
    press(app, pygame.K_SPACE)
    assert app.model.scene is SceneId.SETTINGS


# ------------------------------------------------------------------ pause
def start_level(app, level="stonewake"):
    progress(app)
    app.model.current_level_id = level
    app._begin_level()
    tick(app, 3)
    assert app.model.scene is SceneId.GAMEPLAY


def test_pause_menu_resume_restart_settings_quit(app):
    start_level(app)
    press(app, pygame.K_ESCAPE)
    assert app.model.scene is SceneId.PAUSE and app.session.state is SessionState.PAUSED
    assert [i.label for i in app.menu.items] == ["Resume", "Restart Level", "Settings", "Quit to Menu"]
    assert app.audio.duck < 1.0
    press(app, pygame.K_RETURN)                          # Resume
    assert app.model.scene is SceneId.GAMEPLAY and app.session.state is SessionState.ACTIVE
    app.session.score = 999
    press(app, pygame.K_ESCAPE)
    press(app, pygame.K_DOWN)
    press(app, pygame.K_RETURN)                          # Restart
    assert app.model.scene is SceneId.GAMEPLAY and app.session.score == 0
    press(app, pygame.K_ESCAPE)
    press(app, pygame.K_DOWN, 2)
    press(app, pygame.K_RETURN)                          # Settings from pause
    assert app.model.scene is SceneId.SETTINGS
    press(app, pygame.K_ESCAPE)
    assert app.model.scene is SceneId.PAUSE
    press(app, pygame.K_DOWN, 3)
    press(app, pygame.K_RETURN)                          # Quit to menu
    assert app.model.scene is SceneId.MENU and app.session.state is not SessionState.PAUSED


# ------------------------------------------------------------------ results & progression
def test_winning_saves_stars_unlocks_the_next_seal_and_offers_it(app):
    start_level(app)
    app.session.score = 4000
    app._finish_run(True)
    tick(app)
    assert app.model.scene is SceneId.RESULTS and app.result["complete"] and app.result["new_best"]
    assert app.model.save.best_stars["stonewake"] == 3 and "tidelost" in app.model.save.unlocked_levels
    assert app.menu.items[0].label == "Next Seal"
    press(app, pygame.K_RETURN)
    assert app.model.scene is SceneId.STORY and app.model.current_level_id == "tidelost"


def test_losing_offers_retry_and_still_records_the_bestiary(app):
    start_level(app)
    app._finish_run(False)
    tick(app)
    assert [i.label for i in app.menu.items] == ["Retry", "Level Select", "Main Menu"]
    assert "shooter" in app.model.save.seen_enemies and not app.model.save.completed_levels
    press(app, pygame.K_RETURN)
    assert app.model.scene is SceneId.GAMEPLAY


def test_beating_the_last_seal_leads_to_the_epilogue_then_credits_then_menu(app):
    start_level(app, "eclipse")
    app._finish_run(True)
    tick(app)
    assert app.menu.items[0].label == "Finish the Journey"
    press(app, pygame.K_RETURN)
    assert app.model.scene is SceneId.EPILOGUE
    press(app, pygame.K_RETURN, 2)
    assert app.model.scene is SceneId.CREDITS
    press(app, pygame.K_RETURN, 2)
    assert app.model.scene is SceneId.MENU


# ------------------------------------------------------------------ level select, codex, how to play
def test_level_select_locks_and_unlocks(app):
    progress(app, "stonewake")
    goto(app, SceneId.LEVEL_SELECT)
    cards = app._level_cards()
    assert [c["unlocked"] for c in cards] == [True, True, False, False, False]
    press(app, pygame.K_RIGHT, 2)                       # Skyglass is locked
    press(app, pygame.K_RETURN)
    assert app.model.scene is SceneId.LEVEL_SELECT
    press(app, pygame.K_LEFT)
    press(app, pygame.K_RETURN)
    assert app.model.scene is SceneId.STORY and app.model.current_level_id == "tidelost"


def test_level_select_mouse_click_plays_a_card(app):
    progress(app, "stonewake")
    goto(app, SceneId.LEVEL_SELECT)
    app._click(window_pos(app, app.rows[1].rect))
    assert app.model.scene is SceneId.STORY and app.model.current_level_id == "tidelost"


def test_codex_tracks_what_you_have_met_and_cleared(app):
    progress(app, "stonewake")
    app.model.save = SaveData(prologue_seen=True, completed_levels=("stonewake",), seen_enemies=("shooter",))
    goto(app, SceneId.CODEX)
    seals = app._codex_entries()
    assert seals[0]["unlocked"] and not seals[1]["unlocked"] and "Orrin" in seals[0]["subtitle"]
    press(app, pygame.K_RIGHT)
    beasts = app._codex_entries()
    assert app.codex_tab == 1 and beasts[0]["unlocked"] and not beasts[1]["unlocked"]
    press(app, pygame.K_DOWN, 99)
    assert app.codex_index == len(beasts) - 1
    press(app, pygame.K_LEFT)
    assert app.codex_tab == 0 and app.codex_index == 0


def test_how_to_play_pages_wrap(app):
    goto(app, SceneId.HOW_TO_PLAY)
    press(app, pygame.K_LEFT)
    assert app.how_page == len(app_module.story.HOW_TO_PLAY) - 1
    press(app, pygame.K_RIGHT)
    assert app.how_page == 0


def test_escape_leaves_every_screen_and_the_menu_quits(app):
    for scene in (SceneId.CODEX, SceneId.HOW_TO_PLAY, SceneId.LEVEL_SELECT, SceneId.CREDITS, SceneId.SANDBOX):
        goto(app, scene)
        press(app, pygame.K_ESCAPE)
        assert app.model.scene is SceneId.MENU, scene
    press(app, pygame.K_ESCAPE)
    assert not app.running


# ------------------------------------------------------------------ the screen
def test_canvas_and_mouse_follow_a_non_16_9_window(app):
    pygame.display.set_mode((1920, 1200), pygame.RESIZABLE)
    app.window = pygame.display.get_surface()
    tick(app)
    assert app.canvas.get_size() == (1280, 800)
    app._click(window_pos(app, app.rows[5].rect))        # How to Play
    assert app.model.scene is SceneId.HOW_TO_PLAY


def test_every_screen_renders_on_wide_and_tall_windows(app):
    progress(app, "stonewake")
    for size in ((2560, 1080), (900, 1200)):
        pygame.display.set_mode(size, pygame.RESIZABLE)
        app.window = pygame.display.get_surface()
        for scene in (SceneId.MENU, SceneId.SETTINGS, SceneId.LEVEL_SELECT, SceneId.CODEX, SceneId.HOW_TO_PLAY,
                      SceneId.PROLOGUE, SceneId.EPILOGUE, SceneId.CREDITS, SceneId.STORY, SceneId.BRIEFING,
                      SceneId.CALIBRATION, SceneId.SANDBOX):
            goto(app, scene)
        start_level(app)
        press(app, pygame.K_ESCAPE)
        app._finish_run(True)
        tick(app)
        app._finish_run(False)
        tick(app)


def test_helpers():
    from elemental_convergence.content import load_levels
    assert app_module.format_time(125.9) == "2:05" and app_module.format_time(-3) == "0:00"
    assert app_module.level_order(load_levels()) == ["stonewake", "tidelost", "skyglass", "cinderforge", "eclipse"]


def test_a_crash_leaves_a_log_file(tmp_path, monkeypatch):
    for var in ("HOME", "APPDATA", "XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.setenv(var, str(tmp_path))

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(app_module, "Application", Boom)
    with pytest.raises(RuntimeError):
        app_module.main([])
    log = next(tmp_path.rglob("crash.log"))
    assert "kaboom" in log.read_text()
