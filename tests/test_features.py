import itertools
import random

import pytest

from elemental_convergence import session as session_module
from elemental_convergence.combat import Bomb, Laser, Shot
from elemental_convergence.content import load_levels
from elemental_convergence.models import Difficulty, Element, GestureFrame, HandPose
from elemental_convergence.session import (
    BOOST_DAMAGE, CAST_DAMAGE, HEART_HEAL, ULTIMATE_TIME, GameEventType, GameSession, Loot, SessionState,
)


def hand(x, y, element=None, key="L", direction=(0, -1)):
    return HandPose(key, element, (x, y), direction, 90, 1.0)


def new_session(level="skyglass", seed=1):
    s = GameSession(load_levels(), seed=seed)
    s.start_level(level, Difficulty.BALANCED)
    s.loot_timer = 999.0
    return s


_CLOCK = itertools.count(1)


def step(s, hands, n=1, dt=1 / 60):
    events = []
    for _ in range(n):
        events.extend(s.update(dt, GestureFrame(float(next(_CLOCK)), tuple(hands), True)))
    return events


# ---------------------------------------------------------------- 1. blocking
def test_blasts_shoot_down_orbs_on_their_path():
    s = new_session()
    s.enemies[:] = [s._enemy("shooter", 500, at=(640, 100))]
    s.field.shots.append(Shot(640, 300, 0, 100, 100, 13, 10, 5))
    events = step(s, [hand(640, 560, Element.EARTH)])
    cast = next(e for e in events if e.type is GameEventType.CAST)
    assert cast.data["popped"] and not s.field.shots


def test_blasts_do_not_pop_orbs_off_the_path():
    s = new_session()
    s.enemies[:] = [s._enemy("shooter", 500, at=(640, 100))]
    s.field.shots.append(Shot(1100, 300, 0, 0, 0, 13, 10, 5))
    step(s, [hand(640, 560, Element.WATER)])
    assert len(s.field.shots) == 1


def test_blasts_defuse_bombs_in_their_circle():
    s = new_session()
    s.enemies[:] = [s._enemy("shooter", 500, at=(640, 100))]
    s.field.bombs.append(Bomb(640, 300, 0.1, 1.5, 100))
    events = step(s, [hand(640, 560, Element.EARTH)])
    cast = next(e for e in events if e.type is GameEventType.CAST)
    assert cast.data["defused"] and not s.field.bombs


def test_hitting_a_charging_sniper_cancels_its_beam():
    s = new_session()
    sniper = s._enemy("sniper", 500, at=(640, 100))
    s.enemies[:] = [sniper]
    s.field.lasers.append(Laser(sniper.id, tgt=(640, 600), t=0.5))
    events = step(s, [hand(640, 560, Element.EARTH)])
    cast = next(e for e in events if e.type is GameEventType.CAST)
    assert cast.data["interrupted"] and not s.field.lasers


def test_a_beam_that_is_already_firing_cannot_be_cancelled():
    s = new_session()
    sniper = s._enemy("sniper", 500, at=(640, 100))
    s.enemies[:] = [sniper]
    s.field.lasers.append(Laser(sniper.id, tgt=(640, 600), t=1.6))   # past the 1.5s warning
    step(s, [hand(640, 560, Element.EARTH)])
    assert s.field.lasers


def test_hitting_a_winding_up_charger_cancels_the_dash_but_bosses_shrug_it_off():
    s = new_session()
    charger = s._enemy("charger", 500, at=(640, 100))
    charger.wind = 0.6
    boss = s._enemy("stone_guardian", 900, at=(300, 100))
    boss.boss, boss.wind = True, 0.6
    s.enemies[:] = [charger]
    step(s, [hand(640, 560, Element.EARTH)])
    assert charger.wind == 0
    s.enemies[:] = [boss]
    boss.x, boss.y = 640, 100
    step(s, [hand(640, 560, Element.EARTH)], 8)
    assert boss.wind > 0 or boss.dash > 0


# ---------------------------------------------------------------- 2. ultimate
def together():
    return [hand(610, 500, key="Left"), hand(690, 500, key="Right")]


def converge(s, frames=30):
    """Hold both hands together long enough to fire the ultimate; returns every event."""
    return step(s, together(), frames)


def test_convergence_defeats_minions_and_does_not_recharge_itself():
    s = new_session("stonewake")
    s.wave_index, s.state = 3, SessionState.BOSS
    s.enemies.clear()
    s._spawn_boss()
    for k in ("shooter", "charger", "shooter"):
        s.enemies.append(s._enemy(k, 100))
    s.convergence = 100
    events = converge(s)
    assert s.enemies == [] and s.state is SessionState.COMPLETE
    assert s.convergence == 0, "the ultimate's own kills must not refill the meter"
    assert sum(1 for e in events if e.type is GameEventType.ENEMY_DEFEATED) == 4


def test_ultimate_also_hits_enemies_that_arrive_while_it_lasts():
    s = new_session("stonewake")
    s.wave_index = 2
    s.enemies.clear()
    s._spawn_wave()
    s.wave_elapsed = 5.0
    s.convergence = 100
    converge(s)
    assert s.ultimate > 0 and not s.enemies
    assert s.convergence == 0
    step(s, together(), 40)                      # reinforcements spawn ~0.5s later: they get hit too
    assert not s.enemies
    step(s, [hand(640, 600)], int((ULTIMATE_TIME + 1.5) * 60))
    assert s.enemies, "once the ultimate ends the wave carries on"


def test_guardian_damage_share_is_tunable(monkeypatch):
    monkeypatch.setattr(session_module, "CONVERGENCE_BOSS_FRACTION", 0.5)
    s = new_session("stonewake")
    s.wave_index, s.state = 3, SessionState.BOSS
    s.enemies.clear()
    s._spawn_boss()
    boss = s.enemies[0]
    s.enemies.append(s._enemy("shooter", 100))
    s.convergence = 100
    converge(s)
    assert s.enemies == [boss] and boss.hp == pytest.approx(boss.max_hp * 0.5)


# ---------------------------------------------------------------- 3. loot
def drop(s, kind, x=640, y=500):
    s.loot.append(Loot(99, kind, x, y, y))


def test_touching_a_heart_heals_and_missing_it_does_not():
    s = new_session()
    s.hp = 40
    drop(s, "heart")
    step(s, [hand(100, 200)])
    assert s.hp == 40 and s.loot
    events = step(s, [hand(640, 520)])
    assert s.hp == pytest.approx(40 + HEART_HEAL) and not s.loot
    assert any(e.type is GameEventType.LOOT_COLLECTED for e in events)


def test_heart_never_overheals():
    s = new_session()
    s.hp = 95
    drop(s, "heart")
    step(s, [hand(640, 500)])
    assert s.hp == 100


def calm(s):
    """One tough, peaceful enemy far from the hands, so only the thing under test changes health."""
    foe = s._enemy("shooter", 99999, at=(100, 150))
    foe.atk = 9999
    s.enemies[:] = [foe]


def test_regen_heals_over_time_then_stops():
    s = new_session()
    calm(s)
    s.hp = 30
    drop(s, "regen")
    step(s, [hand(640, 500)])
    step(s, [hand(1200, 100)], 60 * 3)
    mid = s.hp
    assert mid > 40
    step(s, [hand(1200, 100)], 60 * 5)
    after = s.hp
    step(s, [hand(1200, 100)], 60)
    assert after > mid and s.hp == after


def test_shield_blocks_enemy_hits_until_it_runs_out():
    s = new_session()
    calm(s)
    drop(s, "shield")
    step(s, [hand(640, 500)])
    assert s.snapshot().shield > 0
    s.field.shots.append(Shot(640, 500, 0, 0, 0, 13, 10, 5))
    events = step(s, [hand(640, 500)])
    assert s.hp == 100 and not any(e.type is GameEventType.PLAYER_HIT for e in events)
    step(s, [hand(1200, 100)], 60 * 9)
    assert s.snapshot().shield == 0
    s.invuln = 0
    s.field.shots.append(Shot(640, 500, 0, 0, 0, 13, 10, 5))
    step(s, [hand(640, 500)])
    assert s.hp < 100


def test_boost_raises_damage_and_speeds_up_casting():
    def damage_of_first_cast(boost):
        s = new_session()
        s.enemies[:] = [s._enemy("shooter", 500, at=(640, 100))]
        if boost:
            s.boost_time = 5.0
        events = step(s, [hand(640, 560, Element.EARTH)])
        return next(e for e in events if e.type is GameEventType.CAST).data["damage"]
    assert damage_of_first_cast(True) == pytest.approx(damage_of_first_cast(False) * BOOST_DAMAGE)
    assert CAST_DAMAGE[Element.EARTH] * BOOST_DAMAGE == pytest.approx(82.5)


@pytest.mark.parametrize("element", list(Element))
def test_each_element_has_its_own_mana_pickup(element):
    s = new_session("eclipse")
    s.mana[element] = 5.0
    drop(s, f"mana:{element.value}")
    step(s, [hand(640, 500)])
    assert s.mana[element] >= 100.0 - 1e-6
    assert all(s.mana[e] >= 5.0 for e in Element)


def test_loot_expires_and_is_capped():
    s = new_session()
    drop(s, "heart", 100, 100)
    step(s, [hand(1200, 600)], 60 * 13)
    assert not s.loot
    for _ in range(20):
        s._spawn_loot()
    assert len(s.loot) <= session_module.LOOT_MAX


def test_loot_spawns_on_its_own_and_only_offers_unlocked_mana():
    s = new_session("stonewake")                       # only earth is unlocked
    s.loot_timer = 0.01
    s.enemies.clear()
    step(s, [hand(1200, 100)], 5)
    assert s.loot
    kinds = set()
    for seed in range(200):
        s.random = random.Random(seed)
        kinds.add(s._loot_kind())
    assert {"heart", "regen", "shield", "boost", "mana:earth"} <= kinds
    assert not any(k.startswith("mana:") and k != "mana:earth" for k in kinds)


def test_defeated_enemies_can_drop_loot_that_falls_to_reach(monkeypatch):
    monkeypatch.setattr(session_module, "LOOT_DROP_CHANCE", 1.0)
    s = new_session("stonewake")
    s.enemies[:] = [s._enemy("shooter", 10, at=(640, 120))]
    step(s, [hand(640, 560, Element.EARTH)])
    assert s.loot
    y0 = s.loot[0].y
    step(s, [hand(1200, 100)], 30)
    assert s.loot[0].y > y0


def test_loot_resets_between_levels_and_snapshot_reports_it():
    s = new_session()
    drop(s, "boost")
    snap = s.snapshot()
    assert snap.loot and snap.loot[0].kind == "boost"
    s.start_level("stonewake", Difficulty.BALANCED)
    assert not s.loot and s.shield_time == s.boost_time == s.regen_time == 0


# ------------------------------------------------- Convergence trigger rules
def ready_session():
    s = new_session("stonewake")
    calm(s)
    s.convergence = 100.0
    return s


def fired(events):
    return any(e.type is GameEventType.CONVERGENCE_STARTED for e in events)


def test_convergence_needs_ten_kills():
    s = new_session("stonewake")
    for n in range(1, 10):
        foe = s._enemy("shooter", 1, at=(640, 200))
        s.enemies.append(foe)
        s._defeat(foe)
        assert s.convergence == pytest.approx(10.0 * n) and s.convergence < 100
    foe = s._enemy("shooter", 1, at=(640, 200))
    s.enemies.append(foe)
    events = s._defeat(foe)
    assert s.convergence == 100.0 and any(e.type is GameEventType.CONVERGENCE_READY for e in events)


def test_a_guardian_counts_as_five_kills():
    s = new_session("stonewake")
    boss = s._enemy("stone_guardian", 1, at=(640, 300))
    boss.boss = True
    s.enemies.append(boss)
    s._defeat(boss)
    assert s.convergence == pytest.approx(50.0)


def test_it_does_not_fire_before_the_meter_is_full():
    s = ready_session()
    s.convergence = 90.0
    assert not fired(converge(s, 60))


def test_one_hand_never_fires_it():
    s = ready_session()
    assert not fired(step(s, [hand(640, 500, key="Right")], 120))


def test_one_hand_detected_twice_never_fires_it():
    s = ready_session()
    ghost = [hand(640, 500, key="Right"), hand(646, 503, key="Right1")]      # same spot, same label
    assert not fired(step(s, ghost, 120))
    offset = [hand(640, 500, key="Right"), hand(690, 500, key="Right1")]     # same label, still too close to be two hands
    assert not fired(step(s, offset, 120))


def test_a_ghost_detection_of_the_wrong_size_never_fires_it():
    s = ready_session()
    ghost = [hand(620, 500, key="Left"), HandPose("Right", None, (700, 500), (0, -1), 30, 1.0)]
    assert not fired(step(s, ghost, 120))


def test_low_confidence_detections_never_fire_it():
    s = ready_session()
    weak = [HandPose("Left", None, (610, 500), (0, -1), 90, 0.3), HandPose("Right", None, (690, 500), (0, -1), 90, 0.3)]
    assert not fired(step(s, weak, 120))


def test_hands_that_are_merely_close_do_not_fire_it():
    s = ready_session()
    close = [hand(560, 500, key="Left"), hand(760, 500, key="Right")]        # 200px apart = 2.2 hand sizes
    assert not fired(step(s, close, 120))
    almost = [hand(600, 500, key="Left"), hand(720, 500, key="Right")]       # 1.33 hand sizes
    assert not fired(step(s, almost, 120))


def test_a_passing_touch_is_not_enough_it_must_be_held():
    s = ready_session()
    assert not fired(step(s, together(), 12))                                # 0.2 s
    step(s, [hand(100, 100, key="Left"), hand(1000, 100, key="Right")], 30)  # let go
    assert s.snapshot().convergence_hold == 0
    assert not fired(step(s, together(), 12))
    assert fired(step(s, together(), 30))


def test_holding_shows_progress_and_fires_after_the_hold_time():
    s = ready_session()
    step(s, together(), 12)
    assert 0 < s.snapshot().convergence_hold < 1
    assert fired(step(s, together(), 20))
    assert s.convergence == 0 and s.snapshot().convergence_hold == 0


def test_a_brief_tracking_flicker_does_not_reset_the_hold_completely():
    s = ready_session()
    step(s, together(), 15)
    step(s, [hand(100, 100, key="Left")], 2)                                 # one hand lost for 2 frames
    assert s.together_time > 0.1
    assert fired(step(s, together(), 25))


def test_no_stray_blasts_while_clasping_hands_on_a_full_meter():
    s = ready_session()
    s.enemies[:] = [s._enemy("shooter", 500, at=(640, 100))]
    hands = [hand(610, 500, Element.EARTH, key="Left"), hand(690, 500, Element.EARTH, key="Right")]
    events = step(s, hands, 6)
    assert not any(e.type is GameEventType.CAST for e in events)
