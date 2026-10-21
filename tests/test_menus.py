import pytest

from elemental_convergence.menus import Item, Menu, clamp_index


def make():
    state = {"vol": 0.5, "fs": False, "diff": 1, "pressed": 0}
    items = [
        Item("Play", action=lambda: state.__setitem__("pressed", state["pressed"] + 1)),
        Item("Volume", "slider", get=lambda: state["vol"], set=lambda v: state.__setitem__("vol", v)),
        Item("Fullscreen", "toggle", get=lambda: state["fs"], set=lambda v: state.__setitem__("fs", v)),
        Item("Difficulty", "choice", get=lambda: state["diff"], set=lambda v: state.__setitem__("diff", v),
             options=("Story", "Balanced", "Master")),
        Item("Locked", enabled=False),
        Item("Quit", action=lambda: None),
    ]
    return Menu(items), state


def test_navigation_wraps_and_skips_disabled_rows():
    menu, _ = make()
    visited = []
    for _ in range(6):
        menu.move(1)
        visited.append(menu.current.label)
    assert "Locked" not in visited and visited[:5] == ["Volume", "Fullscreen", "Difficulty", "Quit", "Play"]
    assert menu.move(-1) and menu.current.label == "Play"
    assert menu.move(-1) and menu.current.label == "Quit", "backwards wraps past the disabled row"


def test_buttons_toggles_choices_and_sliders():
    menu, state = make()
    assert menu.activate() and state["pressed"] == 1
    menu.move(1)
    assert menu.adjust(1) and state["vol"] == pytest.approx(0.55)
    assert menu.adjust(-1) and menu.adjust(-1) and state["vol"] == pytest.approx(0.45)
    assert not menu.activate(), "enter does nothing on a slider"
    menu.move(1)
    assert menu.activate() and state["fs"] is True
    assert menu.adjust(-1) and state["fs"] is False
    menu.move(1)
    assert menu.current.value_text() == "Balanced"
    menu.adjust(1)
    assert menu.current.value_text() == "Master"
    menu.adjust(1)
    assert menu.current.value_text() == "Story", "choices wrap"


def test_slider_clamps_and_reports_no_change_at_the_ends():
    menu, state = make()
    menu.move(1)
    state["vol"] = 1.0
    assert not menu.adjust(1) and state["vol"] == 1.0
    state["vol"] = 0.0
    assert not menu.adjust(-1) and state["vol"] == 0.0


def test_mouse_hover_and_slider_click():
    menu, state = make()
    assert menu.hover(3) and menu.current.label == "Difficulty"
    assert not menu.hover(4), "disabled rows cannot be hovered"
    assert not menu.hover(3), "hovering the same row is not a change"
    assert menu.set_fraction(1, 0.73) and state["vol"] == pytest.approx(0.75) and menu.index == 1
    assert menu.set_fraction(1, 5.0) and state["vol"] == 1.0
    assert not menu.set_fraction(0, 0.5)


def test_disabled_items_ignore_input_and_empty_menus_are_rejected():
    menu = Menu([Item("A", enabled=False), Item("B", action=lambda: None)])
    assert menu.current.label == "B"
    menu.items[1].enabled = False
    assert not menu.activate() and not menu.adjust(1)
    with pytest.raises(ValueError):
        Menu([])
    assert clamp_index(9, 3) == 2 and clamp_index(-4, 3) == 0 and clamp_index(5, 0) == 0
