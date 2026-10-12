import random

import pytest

from elemental_convergence.combat import (
    BOSS_ATTACKS,
    BOSS_KINDS,
    ENEMY_KINDS,
    CombatField,
    Enemy,
    hand_zone_radius,
    kind_info,
)
from elemental_convergence.content import load_levels
from elemental_convergence.models import Difficulty, Element, GestureFrame, HandPose, scale_frame
from elemental_convergence.session import GameEventType, GameSession, SessionState


def make_enemy(kind="shooter", x=300.0, y=200.0, boss=False) -> Enemy:
    return Enemy(1, kind, 100.0, 100.0, x, y, 0.0, 0.0, r=40.0, atk=99.0, boss=boss)


def zones_at(x=640.0, y=500.0, r=60.0):
    return [(x, y, r)]


def run(field, enemies, zones, seconds, dt=1 / 60, **kw):
    hits = []
    for _ in range(int(seconds / dt)):
        hits.extend(field.update(dt, enemies, zones, **kw))
    return hits


def test_every_level_enemy_and_boss_has_art_and_attack_data():
    for level in load_levels().values():
        for wave in level.waves:
            for kind in wave.enemies:
                assert kind in ENEMY_KINDS
        assert level.boss in BOSS_KINDS
    assert kind_info("totally_unknown").title == "SHOOTER"
    assert kind_info("some_guardian").boss


@pytest.mark.parametrize("attack", sorted(set(BOSS_ATTACKS) | {"orb", "wall", "blink", "dash"}))
def test_every_attack_pattern_runs_without_error(attack):
    field = CombatField(random.Random(3))
    enemy = make_enemy(boss=attack in BOSS_ATTACKS)
    enemy.atk = 0.0
    field._do_attack(enemy, attack, [enemy], zones_at(), 1.0, 1.0)
    run(field, [enemy], zones_at(), 4.0)


def test_enemies_hold_fire_when_no_hands_are_visible():
    field = CombatField(random.Random(1))
    enemy = make_enemy()
    enemy.atk = 0.0
    run(field, [enemy], [], 3.0)
    assert not field.shots and not field.lasers and not field.bombs


def test_orb_aimed_at_a_hand_hurts_it_and_is_consumed():
    field = CombatField(random.Random(1))
    enemy = make_enemy(x=640, y=150)
    enemy.atk = 0.0
    hits = run(field, [enemy], zones_at(640, 500), 3.0)
    assert hits and hits[0].source in {"orb", "homing"}
    assert hits[0].amount > 0


def test_dodging_means_no_damage():
    field = CombatField(random.Random(1))
    enemy = make_enemy(x=640, y=150)
    enemy.kind = "shooter"
    field._do_attack(enemy, "orb", [enemy], [(640.0, 600.0, 40.0)], 1.0, 1.0)
    assert run(field, [enemy], [(60.0, 650.0, 40.0)], 3.0) == []


def test_laser_warns_before_it_fires_and_only_then_hurts():
    field = CombatField(random.Random(1))
    enemy = make_enemy(x=640, y=100)
    field._do_attack(enemy, "laser", [enemy], zones_at(640, 500), 1.0, 1.0)
    laser = field.lasers[0]
    assert not laser.firing
    early = run(field, [enemy], zones_at(640, 500), 1.0)
    assert early == []
    late = run(field, [enemy], zones_at(640, 500), 1.2)
    assert any(hit.source == "laser" for hit in late)


def test_bomb_only_hurts_inside_the_circle_after_the_fuse():
    inside, outside = CombatField(random.Random(1)), CombatField(random.Random(1))
    for field in (inside, outside):
        enemy = make_enemy()
        field._do_attack(enemy, "bomb", [enemy], zones_at(640, 500), 1.0, 1.0)
    assert any(h.source == "bomb" for h in run(inside, [make_enemy()], zones_at(640, 500), 2.5))
    assert not any(h.source == "bomb" for h in run(outside, [make_enemy()], [(50.0, 50.0, 20.0)], 2.5))


def test_charger_telegraphs_then_dashes_towards_the_hand():
    field = CombatField(random.Random(1))
    enemy = make_enemy("charger", x=640, y=150)
    field._do_attack(enemy, "dash", [enemy], zones_at(640, 600), 1.0, 1.0)
    assert enemy.wind > 0
    y0 = enemy.y
    run(field, [enemy], zones_at(640, 600), 0.5)
    assert abs(enemy.y - y0) < 1.0               # still winding up
    run(field, [enemy], zones_at(640, 600), 0.7)
    assert enemy.y > y0 + 100                    # it lunged


def test_player_blasts_shoot_hostile_orbs_down():
    field = CombatField(random.Random(1))
    enemy = make_enemy(x=640, y=150)
    field._do_attack(enemy, "orb", [enemy], zones_at(640, 600), 1.0, 1.0)
    run(field, [enemy], zones_at(640, 600), 0.4)
    popped = field.shoot_down((640.0, 600.0), (640.0, 100.0), 30.0)
    assert popped and not field.shots


def test_difficulty_damage_multiplier_scales_hits():
    def damage(mult):
        field = CombatField(random.Random(1))
        enemy = make_enemy(x=640, y=150)
        field._do_attack(enemy, "orb", [enemy], zones_at(640, 500), mult, 1.0)
        return run(field, [enemy], zones_at(640, 500), 3.0, dmg_mult=mult)[0].amount
    assert damage(2.0) == pytest.approx(2 * damage(1.0))


def test_boss_summons_are_capped():
    field = CombatField(random.Random(1))
    boss = make_enemy("rift_sovereign", boss=True)
    for _ in range(5):
        field._do_attack(boss, "summon", [boss], zones_at(), 1.0, 1.0)
    assert len(field.spawn_requests) <= 4


def test_hand_zone_radius_is_clamped():
    assert hand_zone_radius(5) == 34
    assert hand_zone_radius(10_000) == 100


def test_scale_frame_uses_one_crop_for_both_axes():
    frame = GestureFrame(1.0, (HandPose("L", Element.FIRE, (320, 240), (1, 0), 40, 0.9),))
    scaled = scale_frame(frame, (640, 480), (1280, 720))
    hand = scaled.hands[0]
    assert hand.center == (640.0, 360.0)
    assert hand.size == pytest.approx(80)             # 2x, the same on both axes (no stretching)
    assert scale_frame(frame, (1280, 720), (1280, 720)) is frame


def pose(x, y, element=None, size=90):
    return HandPose("L", element, (x, y), (0, -1), size, 1.0)


def test_session_enemy_attacks_damage_the_player_with_protection_frames():
    session = GameSession(load_levels(), seed=4)
    session.start_level("stonewake", Difficulty.MASTER)
    events = []
    t = 0.0
    for step in range(1, 900):
        t += 1 / 60
        events.extend(session.update(1 / 60, GestureFrame(float(step), (pose(640, 600),))))
        if session.snapshot().state is SessionState.FAILED:
            break
    hits = [e for e in events if e.type is GameEventType.PLAYER_HIT]
    assert hits, "enemies should have hit a stationary hand within 15s"
    assert any(e.type is GameEventType.COMBAT_FX and e.detail == "attack" for e in events)


def test_session_snapshot_exposes_attacks_for_the_renderer():
    session = GameSession(load_levels(), seed=4)
    session.start_level("tidelost", Difficulty.BALANCED)
    seen_warn = seen_beam = False
    for step in range(1, 1500):
        session.update(1 / 60, GestureFrame(float(step), (pose(640, 600),)))
        snap = session.snapshot()
        seen_warn |= any(0 < e.warn <= 1 for e in snap.enemies)
        seen_beam |= bool(snap.lasers or snap.bombs or snap.shots)
        if session.lives < 3:
            break
    assert seen_warn and seen_beam


def test_casting_picks_the_best_aimed_enemy_and_reports_it():
    session = GameSession(load_levels(), seed=1)
    session.start_level("stonewake", Difficulty.BALANCED)
    session.enemies[0].x, session.enemies[0].y = 640, 100
    for other in session.enemies[1:]:
        other.x, other.y = 100, 600
    events = session.update(0.1, GestureFrame(1.0, (pose(640, 500, Element.EARTH),)))
    cast = next(e for e in events if e.type is GameEventType.CAST)
    assert cast.data["target"] == (session.enemies[0].x, session.enemies[0].y) or cast.data["target_id"] == 1
    assert cast.data["damage"] > 0


def test_life_loss_clears_hostile_attacks_and_grants_protection():
    session = GameSession(load_levels(), seed=1)
    session.start_level("stonewake", Difficulty.BALANCED)
    session.field.shots.append(__import__("elemental_convergence.combat", fromlist=["Shot"]).Shot(0, 0, 0, 0, 0, 5, 5, 5))
    session.hurt(500)
    assert not session.field.shots
    assert session.snapshot().invulnerable > 0
