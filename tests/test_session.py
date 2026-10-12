from elemental_convergence.content import load_levels
from elemental_convergence.models import Difficulty, Element, GestureFrame, HandPose
from elemental_convergence.persistence import SaveData
from elemental_convergence.session import GameEventType, GameSession, SessionState, complete_level


def pose_frame(element: Element, timestamp: float = 1.0) -> GestureFrame:
    return GestureFrame(
        timestamp,
        (HandPose("left", element, (640, 360), (1, 0), 80, 1.0),),
    )


def test_starting_a_level_unlocks_every_power_learned_so_far():
    session = GameSession(load_levels(), seed=3)

    session.start_level("skyglass", Difficulty.BALANCED)

    assert session.snapshot().unlocked_elements == (Element.EARTH, Element.WATER, Element.AIR)


def test_hand_loss_damage_uses_elapsed_seconds_not_frame_count():
    first = GameSession(load_levels(), seed=1)
    second = GameSession(load_levels(), seed=1)
    first.start_level("stonewake", Difficulty.STORY)
    second.start_level("stonewake", Difficulty.STORY)
    missing = GestureFrame(1.0, (), True)

    for _ in range(30):
        first.update(0.1, missing)
    for _ in range(6):
        second.update(0.5, missing)

    assert first.snapshot().hp == second.snapshot().hp == 90.0


def test_pause_freezes_combat_timers():
    session = GameSession(load_levels(), seed=1)
    session.start_level("stonewake", Difficulty.BALANCED)
    session.set_paused(True)

    session.update(10.0, GestureFrame(1.0, (), True))

    assert session.snapshot().hp == 100.0
    assert session.snapshot().elapsed_seconds == 0.0


def test_defeating_a_wave_advances_to_the_next_authored_wave():
    session = GameSession(load_levels(), seed=2)
    session.start_level("stonewake", Difficulty.STORY)

    events = []
    for step in range(1, 40):
        events.extend(session.update(1.0, pose_frame(Element.EARTH, float(step))))
        if session.snapshot().wave_number == 2:
            break

    assert session.snapshot().wave_number == 2
    assert any(event.type is GameEventType.WAVE_COMPLETE for event in events)


def test_completing_a_level_unlocks_the_next_level_without_losing_scores():
    save = SaveData(best_scores={"stonewake": 900})

    updated = complete_level(save, load_levels()["stonewake"], score=1200)

    assert updated.unlocked_levels == ("stonewake", "tidelost")
    assert updated.completed_levels == ("stonewake",)
    assert updated.best_scores == {"stonewake": 1200}


def test_losing_all_lives_finishes_only_the_current_level():
    session = GameSession(load_levels(), seed=5)
    session.start_level("stonewake", Difficulty.MASTER)

    events = []
    for _ in range(3):
        events.extend(session.hurt(200))

    assert session.snapshot().state is SessionState.FAILED
    assert any(event.type is GameEventType.LEVEL_FAILED for event in events)


def test_survive_waves_send_reinforcements_until_the_clock_runs_out():
    session = GameSession(load_levels(), seed=5)
    session.start_level("stonewake", Difficulty.BALANCED)
    session.wave_index = 2                              # the 30 second survive wave
    session.enemies.clear()
    session._spawn_wave()
    wanted = sum(session.level.waves[2].enemies.values())      # the regular roster (an elite also arrives)

    refilled = False
    for step in range(1, 25 * 60):                      # 25 of the 30 seconds
        session.enemies[:] = session.enemies[1:] if step % 120 == 0 else session.enemies   # a kill every 2s
        session.update(1 / 60, GestureFrame(float(step), ()))
        session.hp = 100.0
        refilled |= len(session.enemies) >= wanted and step > 240
    assert refilled and session.enemies, "the arena must not stay empty while time remains"
    assert session.wave_index == 2


def test_survive_wave_stops_reinforcing_near_the_end_and_then_advances():
    session = GameSession(load_levels(), seed=5)
    session.start_level("stonewake", Difficulty.BALANCED)
    session.wave_index = 2
    session.enemies.clear()
    session._spawn_wave()
    session.wave_elapsed = 29.5                         # almost over: nobody new arrives
    session.enemies.clear()
    session.update(1 / 60, GestureFrame(1.0, ()))
    assert not session.enemies
    session.wave_elapsed = 30.0
    events = session.update(1 / 60, GestureFrame(2.0, ()))
    assert any(e.type is GameEventType.WAVE_COMPLETE for e in events)


def test_a_wiped_survive_arena_is_refilled_with_a_full_group_quickly():
    session = GameSession(load_levels(), seed=5)
    session.start_level("stonewake", Difficulty.BALANCED)
    session.wave_index = 2
    session.enemies.clear()
    session._spawn_wave()
    wanted = sum(session.level.waves[2].enemies.values())
    session.wave_elapsed = 10.0
    session.enemies.clear()
    for step in range(1, 90):                           # 1.5 seconds
        session.update(1 / 60, GestureFrame(float(step), ()))
    assert len(session.enemies) == wanted
