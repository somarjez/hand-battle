import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from elemental_convergence.combat import ENEMY_KINDS, BOSS_KINDS
from elemental_convergence.content import load_levels
from elemental_convergence.models import Difficulty, Element, GestureFrame, HandPose
from elemental_convergence.presentation.effects import FxSystem, GlowLayer
from elemental_convergence.presentation.renderer import GameRenderer
from elemental_convergence.session import GameEvent, GameEventType, GameSession, SessionState


@pytest.fixture
def surface():
    pygame.init()
    yield pygame.Surface((1280, 720))
    pygame.quit()


def staged_session(kinds, boss=None):
    session = GameSession(load_levels(), seed=2)
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


def pose(x, y, element=None):
    return HandPose("L", element, (x, y), (0, -1), 90, 1.0)


def test_every_enemy_kind_and_boss_draws_through_a_full_fight(surface):
    renderer = GameRenderer((1280, 720))
    for boss in list(BOSS_KINDS)[::2]:
        session = staged_session(list(ENEMY_KINDS), boss)
        for step in range(1, 300):
            frame = GestureFrame(float(step), (pose(640 + (step % 40), 560, Element.EARTH),))
            events = session.update(1 / 60, frame)
            session.hp = max(session.hp, 50)
            renderer.update_fx(1 / 60, session.snapshot(), events)
            renderer.draw_gameplay(surface, session.snapshot(), None, frame)
        renderer.reset_fx()


def test_glow_changes_pixels_only_where_something_glows(surface):
    glow = GlowLayer((1280, 720))
    target = pygame.Surface((1280, 720))
    glow.clear()
    glow.compose(target)
    assert target.get_at((640, 360))[:3] == (0, 0, 0)
    glow.circle((640, 360), 60, (200, 100, 50))
    glow.compose(target)
    assert target.get_at((640, 360)).r > 20


def test_fx_particles_expire_and_are_capped(surface):
    fx = FxSystem(seed=1)
    for _ in range(100):
        fx.burst(100, 100, (255, 0, 0), 60)
    assert len(fx.particles) <= FxSystem.MAX_PARTICLES
    for _ in range(300):
        fx.update(1 / 60)
    assert not fx.particles


def test_reduced_flash_and_shake_settings_are_respected(surface):
    fx = FxSystem(seed=1)
    fx.reduced_shake = True
    fx.kick(1.0)
    assert fx.shake == 0
    fx.reduced_flash = True
    fx.flash((255, 255, 255), 1.0)
    assert fx.flash_alpha <= 0.25


def test_paused_frames_never_shake(surface):
    renderer = GameRenderer((1280, 720))
    session = staged_session(["shooter"])
    renderer.fx.shake = 1.0
    renderer._advanced = False
    renderer.draw_gameplay(surface, session.snapshot(), None)
    renderer.draw_gameplay(surface, session.snapshot(), None)   # would jitter if shake leaked


def test_events_spawn_banners_and_floaters(surface):
    renderer = GameRenderer((1280, 720))
    session = staged_session(["shooter"])
    events = [
        GameEvent(GameEventType.WAVE_STARTED, "2"),
        GameEvent(GameEventType.PLAYER_HIT, "orb", {"x": 600, "y": 500, "amount": 10, "source": "orb"}),
        GameEvent(GameEventType.LIFE_LOST, "2"),
        GameEvent(GameEventType.CONVERGENCE_STARTED, "", {"x": 640, "y": 360}),
    ]
    renderer.update_fx(1 / 60, session.snapshot(), events)
    assert renderer.fx.banners and renderer.fx.floaters and renderer.fx.nova > 0
