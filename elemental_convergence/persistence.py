from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

from .models import Difficulty


@dataclass(frozen=True, slots=True)
class SaveData:
    version: int = 1
    unlocked_levels: tuple[str, ...] = ("stonewake",)
    completed_levels: tuple[str, ...] = ()
    best_scores: dict[str, int] = field(default_factory=dict)
    difficulty: Difficulty = Difficulty.BALANCED

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SaveData":
        if raw.get("version") != 1:
            raise ValueError("unsupported save version")
        return cls(
            unlocked_levels=tuple(str(x) for x in raw.get("unlocked_levels", ("stonewake",))),
            completed_levels=tuple(str(x) for x in raw.get("completed_levels", ())),
            best_scores={str(k): int(v) for k, v in raw.get("best_scores", {}).items()},
            difficulty=Difficulty(raw.get("difficulty", Difficulty.BALANCED)),
        )


@dataclass(frozen=True, slots=True)
class Settings:
    version: int = 1
    camera_id: int | None = None
    fullscreen: bool = True
    fill_screen: bool = True
    reduced_flash: bool = False
    reduced_shake: bool = False
    show_hand_overlay: bool = True
    master_volume: float = 0.8
    music_volume: float = 0.6
    sfx_volume: float = 0.8

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Settings":
        if raw.get("version") != 1:
            raise ValueError("unsupported settings version")
        values = {name: raw.get(name, field.default) for name, field in cls.__dataclass_fields__.items()}
        values["version"] = 1
        return cls(**values)


T = TypeVar("T", SaveData, Settings)


class _JsonRepository(Generic[T]):
    def __init__(self, path: Path, model: type[T]):
        self.path = path
        self.model = model

    def load(self) -> T:
        if not self.path.exists():
            value = self.model()
            self.save(value)
            return value
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("root must be an object")
            return self.model.from_dict(raw)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            backup = self.path.with_name(f"{self.path.stem}.corrupt{self.path.suffix}")
            try:
                os.replace(self.path, backup)
            except OSError:
                pass
            value = self.model()
            self.save(value)
            return value

    def save(self, value: T) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = asdict(value)
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, self.path)


class SaveRepository(_JsonRepository[SaveData]):
    def __init__(self, path: Path):
        super().__init__(path, SaveData)


class SettingsRepository(_JsonRepository[Settings]):
    def __init__(self, path: Path):
        super().__init__(path, Settings)


def user_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "ElementalConvergence" if base else Path.home() / ".elemental-convergence"
