"""Menu model: items (buttons, sliders, toggles, choices) and keyboard/mouse navigation.

Pure logic with no pygame, so every behaviour is unit-tested. Screens draw a Menu and feed it input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


@dataclass(eq=False)
class Item:
    label: str
    kind: str = "button"                       # button | slider | toggle | choice
    get: Callable[[], Any] | None = None       # current value (slider 0..1, toggle bool, choice index into options)
    set: Callable[[Any], None] | None = None
    action: Callable[[], None] | None = None   # button press
    options: Sequence[str] = ()                # choice labels
    enabled: bool = True
    hint: str = ""
    step: float = 0.05

    def value_text(self) -> str:
        if self.kind == "slider":
            return f"{round(float(self.get()) * 100)}%"
        if self.kind == "toggle":
            return "On" if self.get() else "Off"
        if self.kind == "choice":
            index = int(self.get())
            return str(self.options[index % len(self.options)]) if self.options else ""
        return ""


@dataclass
class Menu:
    items: list[Item]
    index: int = field(default=0)

    def __post_init__(self) -> None:
        if not self.items:
            raise ValueError("a menu needs at least one item")
        if not self.items[self.index].enabled:
            self.index = self._next_enabled(self.index, 1)

    @property
    def current(self) -> Item:
        return self.items[self.index]

    def _next_enabled(self, start: int, step: int) -> int:
        n = len(self.items)
        for k in range(1, n + 1):
            candidate = (start + step * k) % n
            if self.items[candidate].enabled:
                return candidate
        return start

    def move(self, delta: int) -> bool:
        """Move the highlight (skipping disabled rows, wrapping). True if it changed."""
        before = self.index
        self.index = self._next_enabled(self.index, 1 if delta >= 0 else -1)
        return self.index != before

    def hover(self, index: int) -> bool:
        if 0 <= index < len(self.items) and self.items[index].enabled and index != self.index:
            self.index = index
            return True
        return False

    def activate(self) -> bool:
        """Enter / click on the highlighted row. True if something happened."""
        item = self.current
        if not item.enabled:
            return False
        if item.kind == "button":
            if item.action is not None:
                item.action()
            return True
        if item.kind in ("toggle", "choice"):
            return self.adjust(1)
        return False

    def adjust(self, direction: int) -> bool:
        """Left / right on the highlighted row. True if the value changed."""
        item = self.current
        if not item.enabled or item.set is None or item.get is None:
            return False
        direction = 1 if direction >= 0 else -1
        if item.kind == "slider":
            value = min(1.0, max(0.0, round(float(item.get()) + direction * item.step, 3)))
            changed = value != float(item.get())
            item.set(value)
            return changed
        if item.kind == "toggle":
            item.set(not item.get())
            return True
        if item.kind == "choice" and item.options:
            item.set((int(item.get()) + direction) % len(item.options))
            return True
        return False

    def set_fraction(self, index: int, fraction: float) -> bool:
        """Mouse click / drag on a slider's bar."""
        item = self.items[index]
        if item.kind != "slider" or not item.enabled or item.set is None:
            return False
        value = min(1.0, max(0.0, round(fraction / item.step) * item.step))
        item.set(round(value, 3))
        self.index = index
        return True


def clamp_index(index: int, count: int) -> int:
    return max(0, min(count - 1, index)) if count else 0
