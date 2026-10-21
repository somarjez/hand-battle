"""Automatic graphics quality: protect the frame rate on slower machines without any flicker."""

from __future__ import annotations

GRAPHICS_MODES = ("auto", "high", "fast")


class QualityGovernor:
    """Switch to the cheaper render path after a sustained run of slow frames, and back after a long calm one.

    `record` takes the time one frame's work took (not including the wait for the next frame) and returns
    whether the fast path should be used. The long, asymmetric windows are deliberate hysteresis.
    """

    def __init__(self, slow_seconds: float = 0.019, calm_seconds: float = 0.010,
                 slow_frames: int = 90, calm_frames: int = 900, smoothing: float = 0.9):
        self.slow_seconds, self.calm_seconds = slow_seconds, calm_seconds
        self.slow_frames, self.calm_frames = slow_frames, calm_frames
        self.smoothing = smoothing
        self.average = 0.0
        self.fast = False
        self._slow = 0
        self._calm = 0

    def record(self, work_seconds: float) -> bool:
        self.average = work_seconds if self.average == 0.0 else self.average * self.smoothing + work_seconds * (1 - self.smoothing)
        if not self.fast:
            self._slow = self._slow + 1 if self.average > self.slow_seconds else 0
            if self._slow >= self.slow_frames:
                self.fast, self._slow, self._calm = True, 0, 0
        else:
            self._calm = self._calm + 1 if self.average < self.calm_seconds else 0
            if self._calm >= self.calm_frames:
                self.fast, self._slow, self._calm = False, 0, 0
        return self.fast

    def reset(self) -> None:
        self.average, self.fast, self._slow, self._calm = 0.0, False, 0, 0


def use_fast_path(graphics: str, governor: QualityGovernor) -> bool:
    """High and Fast are fixed choices; Auto follows the governor."""
    if graphics == "fast":
        return True
    if graphics == "high":
        return False
    return governor.fast
