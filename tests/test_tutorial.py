import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from elemental_convergence import story
from elemental_convergence.models import Element, HandPose
from elemental_convergence.persistence import SaveData
from elemental_convergence.presentation import handsigns
from elemental_convergence.presentation.scenes import SceneId
from elemental_convergence.sandbox import GUIDED, HOLD_SECONDS, STEPS, SandboxTutorial
from tests.test_app import app, goto, press, tick  # noqa: F401


def hand(gesture, x=300.0, key="Right", size=70.0, conf=1.0):
    return HandPose(key, gesture, (x, 300.0), (0, -1), size, conf)


def run(tut, hands, seconds):
    out = []
    for _ in range(int(seconds * 30)):
        r = tut.update(1 / 30, hands)
        if r:
            out.append(r)
    return out


def test_credits_name_the_team():
    assert story.CREDITS[0] == "Main Creator: Jezreel Ramos"
    assert "Judeelyn Capili" in story.CREDITS[1] and "Shaila Patrice Avellaneda" in story.CREDITS[1]


def test_every_how_to_page_has_a_lola_line():
    assert len(story.HOW_TO_LOLA) >= len(story.HOW_TO_PLAY)


def test_lesson_walks_through_every_sign_in_order():
    t = SandboxTutorial()
    assert t.step.id == "hello"
    assert run(t, [], 3) == [] and t.step.id == "hello"           # nothing to see: waits
    run(t, [hand(Element.AIR)], HOLD_SECONDS + 0.2)
    run(t, [hand(Element.AIR)], 1.5)                              # cheer, then on
    assert t.step.id == "earth"
    for element in ("earth", "water", "air", "fire", "lightning"):
        assert t.step.element == element
        run(t, [hand(Element(element))], HOLD_SECONDS + 0.2)
        run(t, [], 1.3)
    assert t.step.id == "kalampag"


def test_wrong_sign_does_not_pass_and_says_what_it_sees():
    t = SandboxTutorial()
    t.go(2)                                                        # water
    run(t, [hand(Element.AIR)], 3)
    assert t.step.id == "water" and "water" not in t.done
    kind, text = t.feedback([hand(Element.AIR)])
    assert kind == "warn" and "Air" in text


def test_a_wobbly_hand_loses_progress_instead_of_passing():
    t = SandboxTutorial()
    t.go(1)
    run(t, [hand(Element.EARTH)], 0.5)
    run(t, [], 1.0)
    assert t.progress == 0.0


def test_kalampag_needs_two_hands_pressed_together():
    t = SandboxTutorial()
    t.go(6)
    run(t, [hand(Element.AIR, 300, "Left")], 2)
    assert "kalampag" not in t.done
    pair = [hand(Element.AIR, 300, "Left"), hand(Element.AIR, 350, "Right")]
    assert "finished" in run(t, pair, 1.5) and t.finished is False or "kalampag" in t.done


def test_lost_hand_message_appears_after_a_moment():
    t = SandboxTutorial()
    t.go(1)
    run(t, [], 0.5)
    assert t.feedback([])[0] == "idle"
    run(t, [], 2)
    assert t.feedback([])[0] == "warn"


def test_free_practice_lights_up_what_it_sees():
    t = SandboxTutorial()
    t.go(len(STEPS) - 1)
    run(t, [hand(Element.FIRE)], 0.2)
    assert "fire" in t.lit and t.step.kind == "free"


def test_hand_signs_draw_for_every_element():
    pygame.init()
    surf = pygame.Surface((300, 300))
    for name in handsigns.ELEMENT_RGB:
        surf.fill((0, 0, 0))
        handsigns.draw_hand_sign(surf, name, 150, 150, 160)
        assert pygame.surfarray.array3d(surf).sum() > 0
    for kind in ("heart", "regen", "shield", "boost", "mana"):
        handsigns.draw_pickup(surf, kind, 150, 150, 60)
    for kind in ("rockfall", "tide", "storm", "forge"):
        handsigns.draw_hazard(surf, kind, 150, 150, 60)


def test_sandbox_and_how_to_screens_render_and_respond(app):  # noqa: F811
    goto(app, SceneId.SANDBOX)
    tick(app, 3)
    assert len(app.rows) == len(STEPS)
    press(app, pygame.K_RIGHT)
    assert app.sandbox.index == 1
    press(app, pygame.K_r)
    assert app.sandbox.index == 0
    goto(app, SceneId.HOW_TO_PLAY)
    for _ in range(len(story.HOW_TO_PLAY)):
        tick(app, 2)
        press(app, pygame.K_RIGHT)


def test_codex_entries_carry_a_creature_and_render(app):  # noqa: F811
    app.model.save = SaveData(prologue_seen=True, completed_levels=("stonewake",), seen_enemies=("shooter", "rift_sovereign"))
    goto(app, SceneId.CODEX)
    seals = app._codex_entries()
    assert seals[0]["kind"] and seals[0]["boss"]
    press(app, pygame.K_RIGHT)
    beasts = app._codex_entries()
    assert all(b["kind"] for b in beasts) and beasts[0]["weak"] == "air"
    tick(app, 3)
    for i in (0, 1, len(beasts) - 1):
        app.codex_index = i
        tick(app, 2)


def test_story_text_never_dumps_when_the_voice_drops_out(app):  # noqa: F811
    from elemental_convergence.narrator import Narrator

    class Dies:
        def speak(self, text, volume, should_stop):
            raise RuntimeError("voice failed")

    app.narrator = Narrator(lambda: Dies())
    app._enter_scene(SceneId.PROLOGUE)
    lines = list(story.PROLOGUE)
    app._reveal_seed = 2.4                       # it had got to line three when the voice died
    app.narrator.failed = True
    first = app._reveal(lines)
    assert 2.0 <= first < 3.0                     # carries on from there, not from the end
    app._reveal_t += 1.0
    assert app._reveal(lines) < len(lines)
    app.narrator.close()


def test_long_lines_get_more_reading_time(app):  # noqa: F811
    assert app._line_seconds("x" * 120) > app._line_seconds("short")


def test_atmosphere_marks_explosions_and_renders_every_place():
    import numpy as np
    from elemental_convergence.content import load_levels
    from elemental_convergence.models import Difficulty
    from elemental_convergence.presentation.battle_view import BattleView
    from elemental_convergence.session import GameSession

    levels = load_levels()
    for level_id, kind in (("stonewake", "rockfall"), ("tidelost", "tide"), ("skyglass", "storm"),
                           ("cinderforge", "forge"), ("eclipse", "storm")):
        s = GameSession(levels, seed=1)
        s.set_arena((1280, 720))
        s.start_level(level_id, Difficulty.BALANCED)
        s.field.hazard(kind, [(500, 500, 60)], 1.0)
        v = BattleView(1)
        for _ in range(30):
            for b in s.field.bombs:
                b.t += 0.1
            for L in s.field.lasers:
                L.t += 0.1
                s.field._laser_geometry(L, {})
            v.update(1 / 30, s.snapshot())
            img = v.render(s.snapshot(), None, None, (1280, 720))
        assert img.shape == (720, 1280, 3) and img.any()
        if kind in ("rockfall", "forge", "storm"):
            assert v.decals, level_id


def test_defeated_creatures_release_a_spirit():
    from elemental_convergence.presentation.battle_view import BattleView

    v = BattleView(1)
    before = len(v.sparks)
    v._spirit(300, 300, "shooter", False)
    v._spirit(600, 300, "rift_sovereign", True)
    assert len(v.sparks) > before + 20 and v.pops
