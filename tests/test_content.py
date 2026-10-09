import json
from pathlib import Path

import pytest

from elemental_convergence.content import ContentError, load_levels
from elemental_convergence.models import Element


def test_campaign_defines_five_ordered_finishable_levels():
    levels = load_levels()

    assert list(levels) == ["stonewake", "tidelost", "skyglass", "cinderforge", "eclipse"]
    assert [level.unlock for level in levels.values()] == [
        Element.EARTH,
        Element.WATER,
        Element.AIR,
        Element.FIRE,
        Element.LIGHTNING,
    ]
    assert levels["eclipse"].next_level is None
    assert levels["eclipse"].boss == "rift_sovereign"
    assert all(len(level.waves) == 3 for level in levels.values())


def test_level_loader_rejects_unknown_objective(tmp_path: Path):
    source = tmp_path / "levels.json"
    source.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "title": "Bad",
                    "unlock": "earth",
                    "intro": ["x"],
                    "outro": ["y"],
                    "waves": [{"objective": "wander", "enemies": {"shooter": 1}}] * 3,
                    "boss": None,
                    "next_level": None,
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContentError, match="objective"):
        load_levels(source)

