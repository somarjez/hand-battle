from elemental_convergence.models import DIFFICULTIES, Difficulty


def test_story_mode_is_more_forgiving_than_master_mode():
    story = DIFFICULTIES[Difficulty.STORY]
    master = DIFFICULTIES[Difficulty.MASTER]

    assert story.enemy_health < master.enemy_health
    assert story.enemy_damage < master.enemy_damage
    assert story.attack_interval > master.attack_interval
    assert story.hand_grace_seconds > master.hand_grace_seconds
    assert story.aim_assist > master.aim_assist

