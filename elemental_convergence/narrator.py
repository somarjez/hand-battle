"""A storyteller that reads the story scenes aloud.

Speech comes from the machine's own text-to-speech voice (Windows SAPI through ``pyttsx3``), so nothing
has to be downloaded and no audio files are bundled. Everything slow happens on one background thread:
the game never waits for the voice. If no voice is available the narrator quietly stays off and the story
scenes fall back to their normal timed text.

The story text and the voice are kept in step: while a narration is running, each line of text fades in
when the narrator starts saying it.

Environment: ``SINAG_VOICE=<part of a voice name>`` picks a particular installed voice,
``SINAG_NARRATOR=off`` disables the narrator.
"""

from __future__ import annotations

import importlib.util
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Callable, Protocol, Sequence

VOICE_HINTS = ("zira", "hazel", "aria", "jenny", "susan", "samantha", "female", "rosa", "blessica")
START_TIMEOUT = 8.0             # seconds to wait for the first word before giving up
RATE = 150                      # words per minute: unhurried, like someone telling a story


class Backend(Protocol):
    def speak(self, text: str, volume: float, should_stop: Callable[[], bool]) -> None: ...


class Pyttsx3Backend:
    """Blocking speech through pyttsx3. Created and used on the narrator thread only."""

    def __init__(self) -> None:
        import pyttsx3

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", RATE)
        wanted = os.environ.get("SINAG_VOICE", "").lower().strip()
        try:
            voices = list(self.engine.getProperty("voices"))
        except Exception:
            voices = []
        hints = (wanted,) if wanted else VOICE_HINTS
        for hint in hints:
            match = next((v for v in voices if hint and hint in f"{v.name} {v.id}".lower()), None)
            if match is not None:
                self.engine.setProperty("voice", match.id)
                break

    def speak(self, text: str, volume: float, should_stop: Callable[[], bool]) -> None:
        self.engine.setProperty("volume", max(0.0, min(1.0, volume)))

        def on_word(name, location, length) -> None:             # called on this thread for every word
            if should_stop():
                self.engine.stop()

        token = self.engine.connect("started-word", on_word)
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        finally:
            self.engine.disconnect(token)


POWERSHELL_SCRIPT = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = -1
$s.Volume = [int]$env:SINAG_VOLUME
$want = $env:SINAG_VOICE
if (-not $want) { $want = 'Zira|Hazel|Aria|Jenny|Susan|Rosa|Blessica' }
$v = $s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo } | Where-Object { $_.Name -match $want } | Select-Object -First 1
if ($v) { try { $s.SelectVoice($v.Name) } catch {} }
$s.Speak($env:SINAG_TEXT)
"""


class CommandBackend:
    """Speaks by running the operating system's own speech command: no Python packages needed."""

    def __init__(self, build: Callable[[str, float], tuple[list[str], dict[str, str]]]) -> None:
        self.build = build

    def speak(self, text: str, volume: float, should_stop: Callable[[], bool]) -> None:
        args, extra = self.build(text, volume)
        flags = 0x08000000 if sys.platform == "win32" else 0          # CREATE_NO_WINDOW
        proc = subprocess.Popen(args, env={**os.environ, **extra}, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=flags)
        try:
            while proc.poll() is None:
                if should_stop():
                    proc.terminate()
                    return
                time.sleep(0.02)
            if proc.returncode not in (0, None):
                raise RuntimeError((proc.stderr.read() or b"").decode("utf-8", "replace").strip()[:300]
                                   or f"speech command exited with {proc.returncode}")
        finally:
            if proc.poll() is None:
                proc.kill()


def _windows_command(text: str, volume: float):
    return (["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", POWERSHELL_SCRIPT],
            {"SINAG_TEXT": text, "SINAG_VOLUME": str(int(max(0.0, min(1.0, volume)) * 100))})


def command_backend() -> CommandBackend | None:
    if sys.platform == "win32" and shutil.which("powershell"):
        return CommandBackend(_windows_command)
    if sys.platform == "darwin" and shutil.which("say"):
        return CommandBackend(lambda t, v: (["say", "-r", str(RATE), t], {}))
    for tool in ("espeak-ng", "espeak"):
        if shutil.which(tool):
            return CommandBackend(lambda t, v, tool=tool: ([tool, "-s", str(RATE), "-a", str(int(v * 200)), t], {}))
    return None


class Voice:
    """Tries pyttsx3 first and the system speech command second, moving on if one of them fails."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.name = "none"
        self._choices: list[Callable[[], Backend | None]] = []
        if importlib.util.find_spec("pyttsx3") is not None:
            self._choices.append(Pyttsx3Backend)
        self._choices.append(command_backend)
        self._active: Backend | None = None

    def _next(self) -> Backend | None:
        while self._choices:
            make = self._choices.pop(0)
            try:
                backend = make()
            except Exception as exc:
                self.errors.append(f"{getattr(make, '__name__', make)}: {exc!r}")
                continue
            if backend is not None:
                self.name = type(backend).__name__
                return backend
        return None

    def speak(self, text: str, volume: float, should_stop: Callable[[], bool]) -> None:
        while True:
            if self._active is None:
                self._active = self._next()
                if self._active is None:
                    raise RuntimeError("no text-to-speech voice available. " + "; ".join(self.errors))
            try:
                self._active.speak(text, volume, should_stop)
                return
            except Exception as exc:
                self.errors.append(f"{self.name}: {exc!r}")
                self._active = None


def default_factory() -> Callable[[], Backend] | None:
    if os.environ.get("SINAG_NARRATOR", "").lower() in ("off", "0", "no"):
        return None
    if os.environ.get("SDL_AUDIODRIVER") == "dummy":             # tests and headless runs stay silent
        return None
    return Voice


def spoken(text: str) -> str:
    """Tidy a line of story text for the voice."""
    text = re.sub(r"\s+-\s+", ", ", text)
    return re.sub(r"\s+", " ", text).strip()


class Narrator:
    def __init__(self, factory: Callable[[], Backend] | None | str = "default", enabled: bool = True, volume: float = 0.8):
        self._factory = default_factory() if factory == "default" else factory
        self.enabled = enabled
        self.volume = volume
        self.key: str | None = None
        self.total = 0
        self.started = 0                      # lines the voice has begun
        self.done = True
        self.stopped = False
        self.failed = False
        self.error = ""
        self._line_start = 0.0
        self._read_at = 0.0
        self._gen = 0
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None

    # ---------------------------------------------------------------- state
    @property
    def available(self) -> bool:
        return self._factory is not None and not self.failed

    @property
    def speaking(self) -> bool:
        return self.key is not None and not self.done and not self.stopped and not self.failed

    def driving(self, key: str | None) -> bool:
        """True while the voice (not the clock) is pacing the text for this narration."""
        if key is None or key != self.key or self.stopped or self.failed:
            return False
        if self.started == 0 and not self.done and time.monotonic() - self._read_at > START_TIMEOUT:
            self.error = self.error or "the voice did not start in time"
            self.failed = True                 # a voice that never speaks must not hold the story back
            return False
        return True

    def progress(self, fade_seconds: float = 1.6) -> float:
        """How many lines are revealed, as a float: finished lines plus the fade of the one being spoken."""
        if self.done:
            return float(self.total)
        if self.started <= 0:
            return 0.0
        frac = min(1.0, (time.monotonic() - self._line_start) / max(0.05, fade_seconds))
        return (self.started - 1) + frac

    # ---------------------------------------------------------------- control
    def read(self, key: str, lines: Sequence[str]) -> bool:
        """Start reading ``lines``, replacing anything already being read. Returns False if it cannot."""
        self.stop()
        if not (self.enabled and self.available and lines):
            return False
        with self._lock:
            self._gen += 1
            gen = self._gen
            self.key, self.total, self.started = key, len(lines), 0
            self.done, self.stopped = False, False
            self._read_at = time.monotonic()
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="narrator", daemon=True)
            self._thread.start()
        self._queue.put((gen, [spoken(line) for line in lines]))
        return True

    def stop(self) -> None:
        with self._lock:
            self._gen += 1                    # makes any speech in progress notice and cut itself off
            if not self.done:
                self.stopped = True
            self.done = True

    def set_enabled(self, on: bool) -> None:
        self.enabled = bool(on)
        if not self.enabled:
            self.stop()

    def close(self) -> None:
        self.stop()
        if self._thread is not None:
            self._queue.put(None)

    def _fail(self, why: str) -> None:
        with self._lock:
            self.failed, self.done, self.error = True, True, why
        print(f"[narrator] disabled: {why}", file=sys.stderr)

    # ---------------------------------------------------------------- worker
    def _run(self) -> None:
        backend: Backend | None = None
        while True:
            item = self._queue.get()
            if item is None:
                return
            gen, lines = item
            if gen != self._gen:
                continue
            if backend is None:
                try:
                    backend = self._factory() if self._factory else None
                except Exception:
                    backend = None
                if backend is None:
                    self._fail("no text-to-speech voice available")
                    continue
            for index, line in enumerate(lines):
                if gen != self._gen:
                    break
                with self._lock:
                    if gen != self._gen:
                        break
                    self.started = index + 1
                    self._line_start = time.monotonic()
                try:
                    backend.speak(line, self.volume, lambda g=gen: g != self._gen)
                except Exception as exc:
                    self._fail(str(exc) or repr(exc))
                    backend = None
                    break
            else:
                with self._lock:
                    if gen == self._gen:
                        self.done = True


if __name__ == "__main__":                                       # python -m elemental_convergence.narrator
    os.environ.pop("SDL_AUDIODRIVER", None)
    voice = Voice()
    print("Speaking a test sentence...")
    try:
        voice.speak("Kumain ka na ba? The Bakunawa sleeps, and the sun will rise again.", 1.0, lambda: False)
        print(f"OK, spoke with {voice.name}.")
    except Exception as exc:
        print(f"FAILED: {exc}")
        for line in voice.errors:
            print("  ", line)
        sys.exit(1)
