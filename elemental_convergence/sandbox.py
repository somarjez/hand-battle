"""The Gesture Sandbox as a guided lesson.

A short tutorial walks you through showing your hand, the five hand-signs, and the two-palm Kalampag, then
leaves you in free practice. The logic lives here (no drawing, no pygame) so it can be tested with plain data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .models import Element, HandPose
from .session import GameSession

HOLD_SECONDS = 0.8          # keep the sign steady this long to pass a step
TOGETHER_SECONDS = 0.7
CELEBRATE_SECONDS = 1.1     # the little "Maganda!" pause before the next step
LOST_AFTER = 1.5            # no hand for this long: say so
MIN_CONFIDENCE = 0.6


@dataclass(frozen=True)
class Step:
    id: str
    kind: str                       # hello | gesture | together | free
    title: str
    word: str                       # the Filipino word
    instruction: str
    tips: tuple[str, ...]
    spoken: str
    element: str | None = None


STEPS: tuple[Step, ...] = (
    Step("hello", "hello", "Show me your hand", "Kamusta",
         "Raise one hand so the camera can see it, palm toward the screen.",
         ("Keep your hand inside the picture", "Good light on your hand helps a lot", "Hold it about an arm's length away"),
         "Kamusta, warden. Raise one hand so I can see it."),
    Step("earth", "gesture", "Earth", "Lupa", "Make a fist.",
         ("Curl all four fingers into your palm", "Thumb can rest across the front"),
         "Earth. Lupa. Make a fist.", "earth"),
    Step("water", "gesture", "Water", "Tubig", "Open your palm and spread your fingers wide.",
         ("Fingers clearly apart, like a fan", "Spread them more if it reads as Air"),
         "Water. Tubig. Open your palm, fingers spread wide.", "water"),
    Step("air", "gesture", "Air", "Hangin", "Open your palm and keep your fingers together.",
         ("A flat hand, like you are saying stop", "Fingers touching, no gaps"),
         "Air. Hangin. Keep your palm flat, fingers together.", "air"),
    Step("fire", "gesture", "Fire", "Apoy", "Raise two fingers: the index and the middle.",
         ("Ring finger and pinky stay folded", "A small V, like a peace sign"),
         "Fire. Apoy. Raise two fingers.", "fire"),
    Step("lightning", "gesture", "Lightning", "Kidlat", "Point with one finger.",
         ("Only the index finger is up", "Fold the other three down"),
         "Lightning. Kidlat. Point one finger.", "lightning"),
    Step("kalampag", "together", "Kalampag", "Kalampag", "Press both palms together and hold them there.",
         ("Use both hands, palms touching", "This is the big one: it strikes every enemy"),
         "Now the big one. Kalampag. Press both palms together."),
    Step("free", "free", "Free practice", "Malaya", "You know them all. Try any sign you like, as long as you like.",
         ("Each sign lights up as it is recognised", "Esc goes back to the menu"),
         "Maganda. You know every sign. Practise as long as you like."),
)

GUIDED = len(STEPS) - 1          # steps before free practice
NAMES = {"earth": "Earth", "water": "Water", "air": "Air", "fire": "Fire", "lightning": "Lightning"}


class SandboxTutorial:
    def __init__(self) -> None:
        self.restart()

    def restart(self) -> None:
        self.index = 0
        self.hold = 0.0
        self.celebrate = 0.0
        self.no_hand = 0.0
        self.done: set[str] = set()
        self.lit: dict[str, float] = {}          # free practice: recently recognised elements
        self.seen_together = 0.0
        self.time = 0.0

    # ------------------------------------------------------------------ navigation
    @property
    def step(self) -> Step:
        return STEPS[self.index]

    @property
    def finished(self) -> bool:
        return all(s.id in self.done for s in STEPS[:GUIDED])

    def go(self, index: int) -> None:
        self.index = max(0, min(len(STEPS) - 1, index))
        self.hold = 0.0
        self.celebrate = 0.0

    def next(self) -> None:
        self.go(self.index + 1)

    def prev(self) -> None:
        self.go(self.index - 1)

    # ------------------------------------------------------------------ reading the hands
    @staticmethod
    def _usable(hands: Sequence[HandPose]) -> list[HandPose]:
        return [h for h in hands if h.confidence >= MIN_CONFIDENCE]

    def target_met(self, hands: Sequence[HandPose]) -> bool:
        step = self.step
        usable = self._usable(hands)
        if step.kind == "hello":
            return bool(usable)
        if step.kind == "gesture":
            return any(h.gesture is not None and h.gesture.value == step.element for h in usable)
        if step.kind == "together":
            return GameSession._convergence_pair(usable) is not None
        return False

    def seeing(self, hands: Sequence[HandPose]) -> str | None:
        """The name of the sign the camera reads right now, if any."""
        for hand in self._usable(hands):
            if hand.gesture is not None:
                return hand.gesture.value
        return None

    def feedback(self, hands: Sequence[HandPose]) -> tuple[str, str]:
        """(kind, text) where kind is ok | warn | idle: what to tell the player right now."""
        step = self.step
        if step.kind == "free":
            seen = self.seeing(hands)
            return ("ok", f"I see {NAMES[seen]}.") if seen else ("idle", "Show any sign.")
        if not hands:
            if self.no_hand >= LOST_AFTER:
                return "warn", "I can't see a hand. Raise it into the picture, palm toward the camera."
            return "idle", "Waiting for your hand..."
        if step.kind == "hello":
            return "ok", "I can see you."
        if step.kind == "together":
            if len(hands) < 2:
                return "warn", "I only see one hand. Bring the other one in."
            return ("ok", "Hold it...") if self.target_met(hands) else ("warn", "Bring your palms closer, until they touch.")
        seen = self.seeing(hands)
        if seen == step.element:
            return "ok", "That's it. Hold it steady."
        if seen:
            return "warn", f"I see {NAMES[seen]}. {step.tips[0]}."
        return "warn", f"I can see your hand but cannot read the sign. {step.tips[0]}."

    # ------------------------------------------------------------------ per frame
    def update(self, dt: float, hands: Sequence[HandPose]) -> str | None:
        """Advance the lesson. Returns ``"step"`` when a step is passed, ``"finished"`` when the last guided one is."""
        self.time += dt
        self.no_hand = 0.0 if hands else self.no_hand + dt
        for key in list(self.lit):
            self.lit[key] -= dt
            if self.lit[key] <= 0:
                del self.lit[key]
        for hand in self._usable(hands):
            if hand.gesture is not None:
                self.lit[hand.gesture.value] = 0.5
        step = self.step
        if step.kind == "free":
            return None
        if self.celebrate > 0:
            self.celebrate -= dt
            if self.celebrate <= 0:
                self.next()
            return None
        need = TOGETHER_SECONDS if step.kind == "together" else HOLD_SECONDS
        if self.target_met(hands):
            self.hold = min(need, self.hold + dt)
        else:
            self.hold = max(0.0, self.hold - dt * 2.0)
        if self.hold >= need:
            self.done.add(step.id)
            self.hold = 0.0
            self.celebrate = CELEBRATE_SECONDS
            return "finished" if self.index == GUIDED - 1 else "step"
        return None

    @property
    def progress(self) -> float:
        """0..1 fill of the hold ring for the current step."""
        need = TOGETHER_SECONDS if self.step.kind == "together" else HOLD_SECONDS
        return 1.0 if self.celebrate > 0 else min(1.0, self.hold / need)
