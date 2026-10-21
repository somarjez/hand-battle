import itertools

import pytest

from elemental_convergence import session as sm
from elemental_convergence.combat import BOSS_KINDS, ENEMY_KINDS, RESISTANCE, WEAK_MULT, WEAKNESS, element_multiplier
from elemental_convergence.content import load_levels
from elemental_convergence.models import Difficulty, Element, GestureFrame, HandPose
from elemental_convergence.presentation.audio import sfx_for_event
from elemental_convergence.session import GameEvent, GameEventType, GameSession

CLOCK = itertools.count(1)


def new():
    s = GameSession(load_levels(), seed=1)
    s.start_level("eclipse", Difficulty.BALANCED)
    s.loot_timer = s.hazard_timer = 1e9
    s.enemies.clear()
    return s


def foe(s, kind="shooter", x=640, y=200, hp=10_000):
    e = s._enemy(kind, hp, at=(x, y))
    e.atk = 1e9
    s.enemies.append(e)
    return e


def hit(s, enemy, element, amount=50.0):
    data = {"reactions": [], "effect": "", "interrupted": []}
    s._hurt_enemy(enemy, amount, (0, -1), 0.0, data, element)
    return data


def tick(s, seconds):
    events = []
    for _ in range(int(seconds * 60)):
        events.extend(s.update(1 / 60, GestureFrame(float(next(CLOCK)), (HandPose("R", None, (1200, 650), (0, -1), 60, 1.0),), True)))
        s.hp = 100.0
    return events


# ------------------------------------------------------------------ weakness
def test_every_enemy_and_guardian_has_a_weakness_that_is_not_also_a_resistance():
    for kind in ENEMY_KINDS:
        assert kind in WEAKNESS and WEAKNESS[kind] != RESISTANCE.get(kind)
    for kind in set(BOSS_KINDS) - {"rift_sovereign"}:
        assert kind in WEAKNESS and WEAKNESS[kind] != RESISTANCE.get(kind)
    assert all(v in {e.value for e in Element} for v in (*WEAKNESS.values(), *RESISTANCE.values()))
    assert len(set(WEAKNESS.values())) == 5, "every element is somebody's weakness, so each one matters"


def test_the_final_boss_has_no_weakness_so_it_asks_for_everything():
    assert "rift_sovereign" not in WEAKNESS and "rift_sovereign" not in RESISTANCE


def test_weak_and_resisted_hits_scale_damage_and_are_reported():
    s = new()
    sniper = foe(s, "sniper")
    plain = hit(s, foe(s, "shooter"), Element.EARTH, 100)["effect"]
    assert plain == ""
    before = sniper.hp
    assert hit(s, sniper, Element.EARTH, 100)["effect"] == "weak"
    assert before - sniper.hp == pytest.approx(100 * WEAK_MULT)
    before = sniper.hp
    assert hit(s, sniper, Element.AIR, 100)["effect"] == "resist"
    assert before - sniper.hp == pytest.approx(70)
    assert element_multiplier("sniper", None) == 1.0


# ------------------------------------------------------------------ reactions
def test_water_soaks_and_lightning_then_shocks_for_bonus_damage_and_a_stun():
    s = new()
    e = foe(s, "shooter")
    hit(s, e, Element.WATER)
    assert e.soaked > 0 and "soaked" in s.snapshot().enemies[0].status
    before = e.hp
    data = hit(s, e, Element.LIGHTNING, 50)
    assert [r["name"] for r in data["reactions"]] == ["SHOCKED"]
    assert before - e.hp == pytest.approx(50 * (1 + sm.SHOCK_BONUS))
    assert e.stun == pytest.approx(sm.SHOCK_STUN) and e.soaked == 0
    assert "stun" in s.snapshot().enemies[0].status


def test_lightning_on_a_dry_enemy_does_not_react():
    s = new()
    assert hit(s, foe(s), Element.LIGHTNING)["reactions"] == []


def test_a_stunned_enemy_freezes_and_cannot_attack_until_it_recovers():
    s = new()
    e = foe(s)
    e.atk = 0.2
    s._stun(e, 1.0)
    x, y = e.x, e.y
    tick(s, 0.8)
    assert (e.x, e.y) == (x, y) and not s.field.shots
    tick(s, 0.6)
    assert e.stun == 0 and (e.x, e.y) != (x, y)


def test_stunning_breaks_a_charge_and_a_beam_warning_but_a_guardian_barely_flinches():
    s = new()
    charger = foe(s, "charger")
    charger.wind = 0.5
    s._stun(charger, 1.0)
    assert charger.wind == 0
    boss = foe(s, "tide_guardian")
    boss.boss = True
    hit(s, boss, Element.WATER)
    data = hit(s, boss, Element.LIGHTNING)
    assert boss.stun == pytest.approx(sm.SHOCK_STUN * 0.35) and data["reactions"][0]["name"] == "SHOCKED"


def test_fire_on_a_wet_enemy_bursts_into_steam_that_hurts_neighbours_only():
    s = new()
    centre, near, far = foe(s, x=640), foe(s, x=760), foe(s, x=1180)
    hit(s, centre, Element.WATER)
    near_before, far_before = near.hp, far.hp
    data = hit(s, centre, Element.FIRE, 40)
    assert data["reactions"][0]["name"] == "STEAM" and centre.soaked == 0 and centre.burning == 0
    assert near_before - near.hp == pytest.approx(sm.STEAM_DAMAGE) and far.hp == far_before


def test_fire_on_a_dry_enemy_burns_it_over_time_and_water_douses_it():
    s = new()
    e = foe(s, hp=1000)
    hit(s, e, Element.FIRE, 10)
    assert e.burning == pytest.approx(sm.BURN_TIME)
    before = e.hp
    tick(s, 1.0)
    assert before - e.hp == pytest.approx(sm.BURN_DPS, abs=0.5)
    tick(s, 3.0)
    assert e.burning == 0
    settled = e.hp
    tick(s, 1.0)
    assert e.hp == settled, "burning stops when it runs out"
    hit(s, e, Element.FIRE, 10)
    data = hit(s, e, Element.WATER, 10)
    assert data["reactions"][0]["name"] == "DOUSED" and e.burning == 0 and e.soaked > 0


def test_burning_can_finish_an_enemy_and_it_counts_as_a_kill():
    s = new()
    e = foe(s, hp=5)
    e.burning = 3.0
    events = tick(s, 1.5)
    assert any(ev.type is GameEventType.ENEMY_DEFEATED for ev in events) and s.combo == 1


def test_air_on_a_burning_enemy_starts_a_firestorm_that_spreads_flames():
    s = new()
    source, near, far = foe(s, x=640), foe(s, x=820), foe(s, x=1200)
    hit(s, source, Element.FIRE)
    data = hit(s, source, Element.AIR)
    assert data["reactions"][0]["name"] == "FIRESTORM"
    assert near.burning > 0 and far.burning == 0
    assert hit(s, foe(s, x=300), Element.AIR)["reactions"] == [], "air on a dry enemy does nothing special"


def test_earth_slows_and_a_guardian_is_slowed_less():
    s = new()
    e, boss = foe(s), foe(s, "stone_guardian")
    boss.boss = True
    hit(s, e, Element.EARTH)
    hit(s, boss, Element.FIRE)
    hit(s, boss, Element.EARTH)
    assert e.slow == pytest.approx(sm.SLOW_TIME) and boss.slow == pytest.approx(sm.SLOW_TIME * 0.5)
    fast = foe(s, x=300, y=300)
    fast.vx, fast.vy = 100.0, 0.0
    slowed = foe(s, x=300, y=400)
    slowed.vx, slowed.vy = 100.0, 0.0
    slowed.slow = 5.0
    s.random.seed(0)
    s.field.update(0.5, [fast, slowed], [], tempo=1.0)
    assert (slowed.x - 300) < (fast.x - 300) * 0.8


def test_statuses_expire_and_clear_from_the_snapshot():
    s = new()
    e = foe(s)
    hit(s, e, Element.WATER)
    tick(s, sm.SOAK_TIME + 0.2)
    assert s.snapshot().enemies[0].status == ()


def test_the_snapshot_carries_the_weakness_for_the_pip():
    s = new()
    foe(s, "gunner")
    assert s.snapshot().enemies[0].weak == "lightning"


def test_a_real_cast_reports_reactions_and_effects_to_the_view_and_sound():
    s = new()
    e = foe(s, "sniper", x=640, y=200)
    s.mana = {el: 100.0 for el in Element}
    hand = HandPose("R", Element.WATER, (640, 560), (0, -1), 90, 1.0)
    events = s.update(0.1, GestureFrame(float(next(CLOCK)), (hand,), True))
    assert e.soaked > 0
    s.cooldowns.clear()
    hand = HandPose("R", Element.LIGHTNING, (640, 560), (0, -1), 90, 1.0)
    events = s.update(0.1, GestureFrame(float(next(CLOCK)), (hand,), True))
    cast = next(ev for ev in events if ev.type is GameEventType.CAST)
    assert [r["name"] for r in cast.data["reactions"]] == ["SHOCKED"]
    assert "reaction_shock" in sfx_for_event(cast)


def test_reaction_sounds_exist_for_each_reaction():
    for name, sound in (("SHOCKED", "reaction_shock"), ("STEAM", "reaction_steam"), ("FIRESTORM", "reaction_firestorm"), ("DOUSED", "reaction_steam")):
        event = GameEvent(GameEventType.CAST, "water", {"reactions": [{"name": name}]})
        assert sound in sfx_for_event(event)
