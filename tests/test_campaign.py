import itertools
import json
import random

import pytest

from elemental_convergence import session as sm
from elemental_convergence import story
from elemental_convergence.combat import ENEMY_KINDS, BOSS_KINDS, CombatField
from elemental_convergence.content import ContentError, HAZARD_KINDS, Objective, load_levels
from elemental_convergence.models import Difficulty, GestureFrame, HandPose
from elemental_convergence.persistence import SaveData
from elemental_convergence.session import GameEventType, GameSession, SessionState, complete_level, record_seen

LEVELS = load_levels()


def hand(x=640, y=520, element=None, key="Right"):
    return HandPose(key, element, (x, y), (0, -1), 90, 1.0)


def new(level="stonewake", seed=1):
    s = GameSession(LEVELS, seed=seed)
    s.start_level(level, Difficulty.BALANCED)
    s.loot_timer = 1e9
    s.hazard_timer = 1e9
    return s


_CLOCK = itertools.count(1)


def run(s, hands=None, n=1, dt=1 / 60):
    hands = [hand()] if hands is None else hands
    out = []
    for _ in range(n):
        out.extend(s.update(dt, GestureFrame(float(next(_CLOCK)), tuple(hands), True)))
    return out


def calm(s, count=1, hp=99999):
    foes = []
    for i in range(count):
        e = s._enemy("shooter", hp, at=(150 + 120 * i, 150))
        e.atk = 1e9
        foes.append(e)
    s.enemies[:] = foes
    return foes


# ------------------------------------------------------------------ story & content
def test_every_level_has_a_complete_story():
    for level in LEVELS.values():
        assert level.subtitle and level.keeper and level.boss_name
        assert len(level.intro) >= 3 and level.outro and level.lore
        assert len(level.wave_titles) == 4
        assert {"intro", "phase2", "phase3", "defeat"} <= set(level.boss_lines)
        assert level.hazard is not None and level.hazard.kind in HAZARD_KINDS
        assert level.boss in BOSS_KINDS


def test_every_wave_mix_is_a_known_enemy_and_each_stage_has_a_hunt_and_an_elite():
    for level in LEVELS.values():
        objectives = [w.objective for w in level.waves]
        assert objectives == [Objective.DEFEAT_ALL, Objective.HUNT, Objective.SURVIVE]
        for wave in level.waves:
            assert set(wave.enemies) <= set(ENEMY_KINDS) and set(wave.elite) <= set(ENEMY_KINDS)
        assert level.waves[1].quota >= 8 and level.waves[2].elite


def test_story_text_covers_every_enemy_hazard_and_page():
    assert set(ENEMY_KINDS) | set(BOSS_KINDS) <= set(story.ENEMY_LORE)
    assert set(HAZARD_KINDS) == set(story.HAZARD_LORE)
    assert len(story.PROLOGUE) >= 4 and len(story.EPILOGUE) >= 3 and len(story.HOW_TO_PLAY) >= 5


def write_levels(tmp_path, mutate):
    raw = json.loads(json.dumps(json.loads(open(__import__("elemental_convergence.content", fromlist=["x"]).DEFAULT_LEVELS_PATH, encoding="utf-8").read())))
    mutate(raw)
    path = tmp_path / "levels.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def test_hunt_waves_need_a_quota_and_hazards_must_be_known(tmp_path):
    with pytest.raises(ContentError, match="quota"):
        load_levels(write_levels(tmp_path, lambda raw: raw[0]["waves"][1].pop("quota")))
    with pytest.raises(ContentError, match="hazard"):
        load_levels(write_levels(tmp_path, lambda raw: raw[0]["hazard"].update(kind="meteor")))


def test_old_content_without_story_fields_still_loads(tmp_path):
    def strip(raw):
        for level in raw:
            for key in ("subtitle", "keeper", "wave_titles", "boss_name", "boss_lines", "lore", "hazard"):
                level.pop(key, None)
    levels = load_levels(write_levels(tmp_path, strip))
    assert levels["stonewake"].hazard is None and levels["stonewake"].wave_titles == ()


# ------------------------------------------------------------------ hunt, elites
def test_a_hunt_wave_ends_at_its_quota_and_keeps_feeding_enemies():
    s = new()
    s.wave_index = 1
    s.enemies.clear()
    s._spawn_wave()
    quota = s.level.waves[1].quota
    events = []
    for _ in range(quota - 1):
        s.enemies[0].hp = 0
        events.extend(s._reap())
        run(s, [hand(1200, 100)], 70)
        assert s.wave_index == 1 and s.enemies, "the hunt must keep sending enemies until the quota is met"
    assert s.snapshot().quota == quota and s.snapshot().quota_done == quota - 1
    s.enemies[0].hp = 0
    s._reap()
    events = run(s, [hand(1200, 100)], 3)
    assert any(e.type is GameEventType.WAVE_COMPLETE for e in events) and s.wave_index == 2


def test_a_hunt_never_overfeeds_past_the_quota():
    s = new()
    s.wave_index = 1
    s.enemies.clear()
    s.wave_kills = s.level.waves[1].quota - 2
    run(s, [hand(1200, 100)], 120)
    assert len(s.enemies) <= 2


def test_elites_are_tougher_bigger_marked_and_always_drop_loot():
    s = new()
    s.wave_index = 2
    s.enemies.clear()
    s._spawn_wave()
    elite = next(e for e in s.enemies if e.elite)
    plain = next(e for e in s.enemies if not e.elite and e.kind == elite.kind)
    assert elite.max_hp > plain.max_hp * 2 and elite.r > plain.r * 1.1
    assert any(snap.elite for snap in s.snapshot().enemies)
    events = s._defeat(elite)
    assert s.loot and next(e for e in events if e.type is GameEventType.ENEMY_DEFEATED).data["elite"]


# ------------------------------------------------------------------ hazards
@pytest.mark.parametrize("kind", HAZARD_KINDS)
def test_every_hazard_pattern_is_telegraphed_and_runs(kind):
    field = CombatField(random.Random(4))
    used = field.hazard(kind, [(640, 500, 60)])
    assert used in HAZARD_KINDS and field.notes
    assert field.bombs or field.lasers or field.shots
    assert all(b.t <= 0 for b in field.bombs) and all(l.warn >= 1.5 for l in field.lasers)
    for _ in range(300):
        field.update(1 / 60, [], [(640, 500, 60)])


def test_hazards_only_fire_while_a_hand_is_visible_and_on_the_stage_timer():
    s = new("tidelost")
    calm(s)
    s.hazard_timer = 0.05
    assert not any(e.detail == "hazard" for e in run(s, [], 30))
    events = run(s, [hand()], 30)
    hazard = [e for e in events if e.type is GameEventType.COMBAT_FX and e.detail == "hazard"]
    assert hazard and hazard[0].data["label"] == "TIDAL SURGE!" and s.hazard_timer > 5


def test_hazards_hurt_if_you_stand_in_them():
    s = new("stonewake")
    calm(s)
    s.field.hazard("rockfall", [(640, 520, 60)])
    events = run(s, [hand(640, 520)], 130)
    assert any(e.type is GameEventType.PLAYER_HIT for e in events)


# ------------------------------------------------------------------ boss phases
def boss_session(level="stonewake"):
    s = new(level)
    s.wave_index, s.state = 3, SessionState.BOSS
    s.enemies.clear()
    s._spawn_boss()
    s.enemies[0].atk = 1e9
    return s


def test_a_guardian_opens_a_new_phase_at_two_thirds_and_one_third_health():
    s = boss_session()
    boss = s.enemies[0]
    boss.hp = boss.max_hp * 0.6
    events = run(s, [hand(1200, 100)], 2)
    phase = [e for e in events if e.detail == "boss_phase"]
    assert len(phase) == 1 and phase[0].data["phase"] == 2 and phase[0].data["line"] == s.level.boss_lines["phase2"]
    assert len(s.enemies) >= 2, "each phase calls minions"
    boss.hp = boss.max_hp * 0.2
    events = run(s, [hand(1200, 100)], 2)
    assert [e.data["phase"] for e in events if e.detail == "boss_phase"] == [3]
    assert not [e for e in run(s, [hand(1200, 100)], 30) if e.detail == "boss_phase"], "each phase opens only once"


def test_the_boss_intro_and_wave_titles_reach_the_player():
    s = new("eclipse")
    wave = s._wave_started_event("2")
    assert wave.data["title"] == "Echoes of Veyra"
    boss = s._wave_started_event("boss")
    assert boss.data["name"] == "Rift Sovereign" and "alone" in boss.data["line"]


# ------------------------------------------------------------------ combo, score, stars
def test_chained_kills_raise_the_multiplier_and_it_expires():
    s = new()
    foes = calm(s, 8, hp=1)
    totals = []
    for foe in foes[:7]:
        before = s.score
        s._defeat(foe)
        totals.append(s.score - before)
    assert totals[:3] == [100, 100, 200] or totals[:3] == [100, 200, 200]
    assert totals[-1] == 100 * min(sm.COMBO_MAX, 1 + 7 // sm.COMBO_STEP) and s.snapshot().combo == 7
    run(s, [hand(1200, 100)], int((sm.COMBO_WINDOW + 0.5) * 60))
    assert s.combo == 0
    before = s.score
    s._defeat(foes[7])
    assert s.score - before == 100


def test_elites_and_guardians_are_worth_more():
    s = new()
    elite = s._enemy("shooter", 1)
    elite.elite = True
    s.enemies.append(elite)
    before = s.score
    s._defeat(elite)
    assert s.score - before == sm.SCORE_ELITE


def test_stars_reward_clean_play():
    s = new()
    assert s.stars() == 3
    s.hits_taken = sm.STAR_HIT_LIMIT + 1
    assert s.stars() == 2
    s.lives = 2
    assert s.stars() == 1


def test_level_complete_reports_stars_and_score():
    s = boss_session()
    s.enemies.clear()
    events = run(s, [hand(1200, 100)], 2)
    done = next(e for e in events if e.type is GameEventType.LEVEL_COMPLETE)
    assert done.data["stars"] == 3 and done.data["score"] == s.score


def test_seen_enemies_are_tracked_for_the_codex():
    s = new()
    assert {"shooter"} <= s.seen_kinds
    s.wave_index = 1
    s._spawn_wave()
    assert {"shooter", "charger"} <= s.seen_kinds


# ------------------------------------------------------------------ save data
def test_old_v1_saves_load_and_gain_the_new_fields():
    save = SaveData.from_dict({"version": 1, "unlocked_levels": ["stonewake", "tidelost"], "best_scores": {"stonewake": 900}})
    assert save.version == 2 and save.best_stars == {} and save.seen_enemies == () and not save.prologue_seen
    assert save.best_scores == {"stonewake": 900}


def test_complete_level_keeps_the_best_stars_and_records_enemies():
    level = LEVELS["stonewake"]
    save = complete_level(SaveData(), level, 1200, 3, {"shooter", "charger"})
    assert save.best_stars["stonewake"] == 3 and set(save.seen_enemies) == {"charger", "shooter"}
    worse = complete_level(save, level, 400, 1, {"sniper"})
    assert worse.best_stars["stonewake"] == 3 and worse.best_scores["stonewake"] == 1200
    assert "sniper" in worse.seen_enemies and "tidelost" in worse.unlocked_levels
    assert record_seen(worse, {"sniper"}) is worse


def test_corrupt_star_values_are_clamped():
    assert SaveData.from_dict({"version": 2, "best_stars": {"stonewake": 99, "tidelost": -4}}).best_stars == {"stonewake": 3, "tidelost": 0}
