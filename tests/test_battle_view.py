import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from elemental_convergence.combat import BOSS_KINDS, ENEMY_KINDS
from elemental_convergence.content import load_levels
from elemental_convergence.models import (
    Difficulty, Element, GestureFrame, HandPose, canvas_size_for, cover_transform, scale_frame,
)
from elemental_convergence.presentation.battle_view import BattleView, cover_resize
from elemental_convergence.presentation.renderer import GameRenderer
from elemental_convergence.session import GameEvent, GameEventType, GameSession, SessionState


def staged(kinds, boss=None, size=(1280, 720)):
    session = GameSession(load_levels(), seed=2)
    session.set_arena(size)
    session.start_level("eclipse", Difficulty.BALANCED)
    session.enemies.clear()
    for index, kind in enumerate(kinds):
        enemy = session._enemy(kind, 110.0, at=(150.0 + index * 130, 200.0))
        enemy.atk = 0.5 + index * 0.2
        session.enemies.append(enemy)
    if boss:
        session.wave_index, session.state = 3, SessionState.BOSS
        session._spawn_boss()
        session.enemies[-1].kind = boss
    return session


def hand(x, y, element=None):
    return HandPose("L", element, (x, y), (0, -1), 90, 1.0)


@pytest.mark.parametrize("window,expected", [
    ((1920, 1080), (1280, 720)), ((1280, 720), (1280, 720)),
    ((1920, 1200), (1280, 800)),
    ((3440, 1440), (1720, 720)), ((1024, 768), (1280, 960)),
])
def test_canvas_matches_the_window_aspect(window, expected):
    assert canvas_size_for(window) == expected
    cw, ch = canvas_size_for(window)
    assert cw / ch == pytest.approx(window[0] / window[1], rel=0.01)


def test_cover_transform_fills_the_canvas_without_distortion():
    scale, ox, oy = cover_transform((640, 480), (1280, 720))
    assert scale == 2.0 and ox == 0 and oy == -120
    scale, ox, oy = cover_transform((1920, 1080), (1280, 800))
    assert scale * 1080 == pytest.approx(800)


def test_hands_land_where_the_picture_puts_them():
    """A marker at a camera pixel must map to the same canvas pixel the picture draws it at."""
    camera = np.zeros((480, 640, 3), np.uint8)
    camera[300:310, 500:510] = 255                       # white dot at camera (505, 305)
    canvas = (1280, 800)
    covered = cover_resize(camera, canvas)
    frame = GestureFrame(1.0, (hand(505, 305),))
    mapped = scale_frame(frame, (640, 480), canvas).hands[0].center
    ys, xs = np.nonzero(covered[:, :, 0] == 255)
    assert abs(mapped[0] - xs.mean()) < 3 and abs(mapped[1] - ys.mean()) < 3


def test_cover_resize_never_stretches_and_fills_exactly():
    image = np.zeros((480, 640, 3), np.uint8)
    assert cover_resize(image, (1280, 720)).shape == (720, 1280, 3)
    assert cover_resize(image, (700, 1200)).shape == (1200, 700, 3)


def test_every_enemy_kind_and_boss_renders_through_a_fight():
    view = BattleView(seed=1)
    for boss in list(BOSS_KINDS)[::2]:
        session = staged(list(ENEMY_KINDS), boss)
        for step in range(1, 300):
            frame = GestureFrame(float(step), (hand(640 + step % 40, 560, Element.EARTH),))
            events = session.update(1 / 60, frame)
            session.hp = max(session.hp, 50)
            snap = session.snapshot()
            view.update(1 / 60, snap, events, frame)
            image = view.render(snap, frame, None, (1280, 720))
        assert image.shape == (720, 1280, 3) and image.dtype == np.uint8
        view.reset()


def test_battle_view_fills_any_canvas_shape():
    view = BattleView(seed=1)
    session = staged(["shooter", "sniper"], size=(1720, 720))
    snap = session.snapshot()
    assert view.render(snap, None, np.zeros((480, 640, 3), np.uint8), (1720, 720)).shape == (720, 1720, 3)


def test_casts_and_defeats_create_projectiles_and_bursts():
    view = BattleView(seed=1)
    session = staged(["shooter"])
    session.enemies[0].x, session.enemies[0].y = 640, 200
    frame = GestureFrame(1.0, (hand(640, 520, Element.FIRE),))
    events = session.update(0.1, frame)
    view.update(1 / 60, session.snapshot(), events, frame)
    assert view.flyers or view.bolts
    for _ in range(40):
        view.update(1 / 60, session.snapshot())
    assert view.sparks or view.fire_particles


def test_hud_and_banners_use_the_prototype_style():
    view = BattleView(seed=1)
    session = staged(["shooter"])
    view.update(1 / 60, session.snapshot(), [GameEvent(GameEventType.WAVE_STARTED, "boss")])
    assert view.banner_text == "BOSS INCOMING!" and view.banner_t > 0
    image = view.render(session.snapshot(), None, None, (1280, 720))
    assert tuple(image[20, 20]) == (70, 210, 70)         # green HP bar, exactly the prototype's colour


def test_reduced_flash_and_shake_are_respected():
    view = BattleView(seed=1)
    view.reduced_shake = True
    view.kick(1.0)
    assert view.shake == 0
    view.reduced_flash = True
    view._on_event(GameEvent(GameEventType.PLAYER_HIT, "orb", {"x": 1, "y": 1}), staged(["shooter"]).snapshot())
    assert view.hurt == 0


def test_paused_frames_never_shake():
    view = BattleView(seed=1)
    session = staged(["shooter"])
    view.shake = 1.0
    a = view.render(session.snapshot(), None, None, (640, 360))
    b = view.render(session.snapshot(), None, None, (640, 360))
    assert np.array_equal(a, b)


def test_renderer_draws_gameplay_over_the_whole_canvas():
    pygame.init()
    renderer = GameRenderer((1280, 720))
    session = staged(["shooter"], size=(1280, 800))
    target = pygame.Surface((1280, 800))
    renderer.draw_gameplay(target, session.snapshot(), None, None, np.full((480, 640, 3), 90, np.uint8))
    assert target.get_at((1279, 799))[:3] == (90, 90, 90) and target.get_at((0, 400))[:3] == (90, 90, 90)
    pygame.quit()


def test_session_arena_follows_the_canvas():
    session = staged(["shooter"], size=(1720, 720))
    session.set_arena((1720, 720))
    assert session.field.size == (1720.0, 720.0)
    session.wave_index, session.state = 3, SessionState.BOSS
    session._spawn_boss()
    assert session.enemies[-1].x == pytest.approx(860)
