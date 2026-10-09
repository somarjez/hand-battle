import json
from pathlib import Path

from elemental_convergence.models import Difficulty
from elemental_convergence.persistence import SaveData, SaveRepository, Settings, SettingsRepository


def test_save_round_trip_preserves_progress(tmp_path: Path):
    repository = SaveRepository(tmp_path / "save.json")
    expected = SaveData(
        unlocked_levels=("stonewake", "tidelost"),
        completed_levels=("stonewake",),
        best_scores={"stonewake": 1200},
        difficulty=Difficulty.MASTER,
    )

    repository.save(expected)

    assert repository.load() == expected
def test_corrupt_save_is_backed_up_and_replaced_with_defaults(tmp_path: Path):
    path = tmp_path / "save.json"
    path.write_text("not json", encoding="utf-8")

    loaded = SaveRepository(path).load()

    assert loaded == SaveData()
    assert (tmp_path / "save.corrupt.json").read_text(encoding="utf-8") == "not json"
    assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


def test_settings_round_trip_preserves_accessibility_options(tmp_path: Path):
    repository = SettingsRepository(tmp_path / "settings.json")
    expected = Settings(
        camera_id=2,
        fullscreen=False,
        fill_screen=False,
        reduced_flash=True,
        reduced_shake=True,
        master_volume=0.5,
        music_volume=0.25,
        sfx_volume=0.75,
    )

    repository.save(expected)

    assert repository.load() == expected
