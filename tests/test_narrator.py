import os
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

from elemental_convergence import app as app_module
from elemental_convergence import story
from elemental_convergence.narrator import Narrator, spoken
from elemental_convergence.presentation.scenes import SceneId
from tests.test_app import app, goto, press, tick  # noqa: F401  (fixtures and helpers)


class FakeVoice:
    """Stands in for the system voice: each line takes a moment, and stops early when told to."""

    def __init__(self, seconds=0.05, log=None):
        self.seconds, self.log = seconds, log if log is not None else []

    def speak(self, text, volume, should_stop):
        self.log.append(text)
        end = time.monotonic() + self.seconds
        while time.monotonic() < end:
            if should_stop():
                return
            time.sleep(0.002)


def wait(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return False


def test_spoken_tidies_story_text():
    assert spoken("Kapre   -   keeper of the tree") == "Kapre, keeper of the tree"


def test_reads_every_line_in_order_and_paces_the_reveal():
    log = []
    n = Narrator(lambda: FakeVoice(0.05, log))
    assert n.read("k", ["one", "two", "three"])
    assert n.driving("k")
    assert wait(lambda: n.done)
    assert log == ["one", "two", "three"]
    assert n.progress() == 3.0 and not n.speaking
    n.close()


def test_stop_interrupts_and_hands_pacing_back_to_the_clock():
    log = []
    n = Narrator(lambda: FakeVoice(5.0, log))
    n.read("k", ["a very long line", "never reached"])
    assert wait(lambda: n.started == 1)
    n.stop()
    assert not n.driving("k") and not n.speaking
    time.sleep(0.05)
    assert log == ["a very long line"]
    n.close()


def test_new_reading_replaces_the_old_one():
    log = []
    n = Narrator(lambda: FakeVoice(0.3, log))
    n.read("first", ["first line", "first two"])
    assert wait(lambda: n.started == 1)
    n.read("second", ["second line"])
    assert wait(lambda: n.done and n.key == "second")
    assert "first two" not in log and "second line" in log
    n.close()


def test_disabled_or_missing_voice_stays_silent():
    assert not Narrator(None).read("k", ["x"])
    off = Narrator(lambda: FakeVoice(), enabled=False)
    assert not off.read("k", ["x"])
    assert not off.driving("k")


def test_a_voice_that_cannot_start_falls_back_quietly():
    def broken():
        raise RuntimeError("no voice")

    n = Narrator(broken)
    n.read("k", ["x"])
    assert wait(lambda: n.failed)
    assert not n.driving("k") and not n.available


def test_story_text_follows_the_voice_and_enter_skips(app):  # noqa: F811
    app.narrator = Narrator(lambda: FakeVoice(0.4), volume=0.5)
    goto(app, SceneId.PROLOGUE)
    app._enter_scene(SceneId.PROLOGUE)
    assert app.narrator.driving(app._narr_key)
    assert app._reveal(story.PROLOGUE) < len(story.PROLOGUE)      # not all shown at once
    app._advance_text()                                            # first Enter: skip to the end of the reveal
    assert not app.narrator.speaking
    assert app._reveal(story.PROLOGUE) >= len(story.PROLOGUE)
    app.narrator.close()


def test_narrator_setting_turns_it_off(app):  # noqa: F811
    app.narrator = Narrator(lambda: FakeVoice(0.4))
    app.narrator.read("k", ["a", "b"])
    app._set_setting(narrator=False)
    assert not app.narrator.speaking and not app.narrator.enabled
    app.narrator.close()


def test_command_backend_speaks_and_can_be_cut_off():
    import sys
    from elemental_convergence.narrator import CommandBackend

    quick = CommandBackend(lambda t, v: ([sys.executable, "-c", "pass"], {}))
    quick.speak("hi", 1.0, lambda: False)
    slow = CommandBackend(lambda t, v: ([sys.executable, "-c", "import time; time.sleep(30)"], {}))
    start = time.monotonic()
    slow.speak("hi", 1.0, lambda: True)                   # told to stop at once: must not wait 30 s
    assert time.monotonic() - start < 5
    bad = CommandBackend(lambda t, v: ([sys.executable, "-c", "import sys; sys.exit(3)"], {}))
    import pytest
    with pytest.raises(RuntimeError):
        bad.speak("hi", 1.0, lambda: False)


def test_voice_moves_on_when_the_first_engine_fails():
    from elemental_convergence.narrator import Voice

    spoken_by = []

    class Good:
        def speak(self, text, volume, should_stop):
            spoken_by.append(text)

    def broken():
        raise RuntimeError("no sapi")

    v = Voice()
    v._choices = [broken, Good]
    v.speak("hello", 1.0, lambda: False)
    assert spoken_by == ["hello"] and any("no sapi" in e for e in v.errors)
    empty = Voice()
    empty._choices = [broken]
    import pytest
    with pytest.raises(RuntimeError):
        empty.speak("x", 1.0, lambda: False)


def test_a_dead_voice_is_reported_and_released():
    n = Narrator(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    n.read("k", ["x"])
    assert wait(lambda: n.failed)
    assert "boom" in n.error or "no text-to-speech" in n.error
