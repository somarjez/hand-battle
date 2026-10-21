import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from pathlib import Path

import numpy as np
import pygame
import pytest

from elemental_convergence.content import load_levels
from elemental_convergence.presentation import art
from elemental_convergence.presentation.renderer import GameRenderer

ASSETS = Path(__file__).parents[1] / "elemental_convergence" / "assets"


@pytest.fixture(autouse=True)
def pg():
    pygame.init()
    art._CACHE.clear()
    yield
    pygame.quit()


@pytest.mark.parametrize("stage", ["menu", "stonewake", "tidelost", "skyglass", "cinderforge", "eclipse"])
@pytest.mark.parametrize("size", [(1280, 720), (900, 1200), (1720, 720)])
def test_every_stage_scene_draws_at_any_window_shape(stage, size):
    scene = art.stage_scene(stage, size)
    assert scene.get_size() == size
    frame = scene.copy()
    for clock in (0.0, 1.3, 9.9):
        art.animate(stage, frame, clock)
    arr = pygame.surfarray.array3d(scene)
    assert arr.std() > 18, "a real picture, not a flat fill"
    assert 15 < arr.mean() < 200


def test_every_scene_is_different_and_scenes_are_cached():
    scenes = {n: pygame.image.tostring(art.stage_scene(n, (640, 360)), "RGB") for n in ("menu", "stonewake", "tidelost", "skyglass", "cinderforge", "eclipse")}
    assert len(set(scenes.values())) == 6
    assert art.stage_scene("stonewake", (640, 360)) is art.stage_scene("stonewake", (640, 360))
    assert art.stage_scene("no-such-stage", (640, 360)) is art.stage_scene("menu", (640, 360))


def test_every_campaign_stage_has_its_own_scene():
    for level_id in load_levels():
        assert level_id in art.SCENES


def test_scenes_are_deterministic():
    a = pygame.image.tostring(art.stage_scene("cinderforge", (480, 270)), "RGB")
    art._CACHE.clear()
    assert a == pygame.image.tostring(art.stage_scene("cinderforge", (480, 270)), "RGB")


def test_ui_skin_pieces_draw_inside_their_rectangles():
    surf = pygame.Surface((400, 200))
    surf.fill((0, 0, 0))
    art.draw_panel(surf, pygame.Rect(20, 20, 360, 160))
    art.draw_button(surf, pygame.Rect(60, 70, 280, 40), True, True, 0.5)
    art.draw_sun(surf, 200, 150, 14)
    art.draw_sun(surf, 240, 150, 14, filled=False)
    art.draw_weave(surf, pygame.Rect(40, 30, 320, 10))
    assert surf.get_at((5, 5))[:3] == (0, 0, 0), "nothing is drawn outside the panel"
    assert surf.get_at((200, 100))[:3] != (0, 0, 0)
    points = art.chamfer(pygame.Rect(0, 0, 100, 50), 10)
    assert len(points) == 8 and min(x for x, _ in points) == 0 and max(x for x, _ in points) == 100


def test_the_bundled_font_loads_and_the_ai_key_art_is_no_longer_the_default(tmp_path):
    for name in ("AlegreyaSC-Bold.ttf", "Alegreya-Variable.ttf", "OFL.txt"):
        assert (ASSETS / "fonts" / name).exists(), name
    assert not (ASSETS / "images" / "menu.png").exists(), "the generated illustration must not be picked up by default"
    renderer = GameRenderer((1280, 720))
    heading, body = renderer.font(30, True), renderer.font(30, False)
    assert heading.size("Sinag")[0] > 20 and body.size("Sinag")[0] > 20
    assert heading.render("Sinag", True, (255, 255, 255)).get_width() != body.render("Sinag", True, (255, 255, 255)).get_width()
    target = pygame.Surface((640, 360))
    renderer._background(target, "menu")
    assert pygame.surfarray.array3d(target).std() > 18


def test_a_hand_made_image_can_override_a_stage(tmp_path):
    (tmp_path / "images" / "override").mkdir(parents=True)
    pygame.image.save(pygame.Surface((64, 36)), str(tmp_path / "images" / "override" / "menu.png"))
    renderer = GameRenderer((1280, 720), asset_root=tmp_path)
    target = pygame.Surface((320, 180))
    renderer._background(target, "menu")
    assert pygame.surfarray.array3d(target).max() == 0, "the override (a black image) replaced the drawn scene"


def test_play_without_a_camera_uses_the_stage_scene():
    renderer = GameRenderer((1280, 720))
    first = renderer.stage_backdrop("tidelost", (640, 360))
    assert first.shape == (360, 640, 3) and first.dtype == np.uint8
    assert renderer.stage_backdrop("tidelost", (640, 360)) is first
