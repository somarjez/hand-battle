from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import math
import os
import threading
import time
from typing import Callable, Protocol, Sequence

import numpy as np

from .models import Element, GestureFrame, HandPose


FingerState = Sequence[int | bool]


def classify_element(
    fingers: FingerState,
    *,
    spread_degrees: float = 0.0,
    pinch_ratio: float = 1.0,
    spread_threshold: float = 12.0,
) -> Element | None:
    """Classify a pose independently of camera orientation and rendering."""
    _, index, middle, ring, pinky = (bool(value) for value in fingers)
    if pinch_ratio < 0.4 and middle and ring and pinky:
        return Element.FIRE
    if index and middle and not (ring or pinky):
        return Element.FIRE
    if not (index or middle or ring or pinky):
        return Element.EARTH
    if index and not (middle or ring or pinky):
        return Element.LIGHTNING
    if index and middle and ring and pinky:
        return Element.WATER if spread_degrees > spread_threshold else Element.AIR
    return None


@dataclass(frozen=True, slots=True)
class CalibrationProfile:
    spread_threshold: float = 12.0
    min_confidence: float = 0.7


class CalibrationSession:
    def __init__(self, profile: CalibrationProfile | None = None):
        self.profile = profile or CalibrationProfile()
        self._detected: set[Element] = set()

    def observe(self, frame: GestureFrame) -> None:
        if not frame.camera_ok:
            return
        self._detected.update(
            hand.gesture
            for hand in frame.hands
            if hand.gesture is not None and hand.confidence >= self.profile.min_confidence
        )

    @property
    def missing(self) -> tuple[Element, ...]:
        return tuple(element for element in Element if element not in self._detected)

    @property
    def complete(self) -> bool:
        return not self.missing


class GestureSmoother:
    def __init__(self, window: int = 7, votes_needed: int = 4):
        self.window = window
        self.votes_needed = votes_needed
        self._history: dict[str, deque[Element | None]] = {}
        self._current: dict[str, Element | None] = {}

    def update(self, key: str, gesture: Element | None) -> Element | None:
        history = self._history.setdefault(key, deque(maxlen=self.window))
        history.append(gesture)
        winner, votes = Counter(history).most_common(1)[0]
        if votes >= self.votes_needed:
            self._current[key] = winner
        return self._current.get(key)

    def retain(self, keys: set[str]) -> None:
        for key in set(self._history) - keys:
            self._history.pop(key, None)
            self._current.pop(key, None)


class Camera(Protocol):
    def is_opened(self) -> bool: ...
    def read(self): ...
    def release(self) -> None: ...


class _OpenCvCamera:
    def __init__(self, camera_id: int):
        import cv2

        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        self.capture = cv2.VideoCapture(camera_id, backend)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    def is_opened(self) -> bool:
        return self.capture.isOpened()

    def read(self):
        return self.capture.read()

    def release(self) -> None:
        self.capture.release()


class _CvZoneDetector:
    def __init__(self):
        from cvzone.HandTrackingModule import HandDetector

        try:
            self.detector = HandDetector(maxHands=2, detectionCon=0.8, minTrackCon=0.6)
        except TypeError:
            self.detector = HandDetector(maxHands=2, detectionCon=0.8)

    def find(self, frame):
        hands, _ = self.detector.findHands(frame, draw=False, flipType=False)
        return hands


def _distance(a, b) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _finger_states(landmarks) -> tuple[int, int, int, int, int]:
    size = _distance(landmarks[0], landmarks[9]) + 1e-6
    values = [1 if _distance(landmarks[4], landmarks[9]) > 0.95 * size else 0]
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        tip_distance = _distance(landmarks[tip], landmarks[0])
        pip_distance = _distance(landmarks[pip], landmarks[0])
        values.append(1 if tip_distance > pip_distance * 1.12 and tip_distance > 1.3 * size else 0)
    return tuple(values)  # type: ignore[return-value]


def _spread_degrees(landmarks) -> float:
    vectors = [
        (landmarks[tip][0] - landmarks[base][0], landmarks[tip][1] - landmarks[base][1])
        for base, tip in ((5, 8), (9, 12), (13, 16), (17, 20))
    ]
    angles = []
    for first, second in zip(vectors[:-1], vectors[1:]):
        cosine = (first[0] * second[0] + first[1] * second[1]) / (
            math.hypot(*first) * math.hypot(*second) + 1e-6
        )
        angles.append(math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
    return sum(angles) / len(angles)


class VisionService:
    """Owns camera and detector lifecycles and publishes the latest snapshot."""

    def __init__(
        self,
        camera_factory: Callable[[int], Camera] | None = None,
        detector_factory: Callable[[], object] | None = None,
        profile: CalibrationProfile | None = None,
    ):
        self.camera_factory = camera_factory or _OpenCvCamera
        self.detector_factory = detector_factory or _CvZoneDetector
        self.profile = profile or CalibrationProfile()
        self._latest = GestureFrame(0.0, (), False)
        self._image = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._camera: Camera | None = None
        self._smoother = GestureSmoother()

    def start(self, camera_id: int) -> bool:
        self.stop()
        camera = self.camera_factory(camera_id)
        if not camera.is_opened():
            camera.release()
            with self._lock:
                self._latest = GestureFrame(time.monotonic(), (), False)
            return False
        self._camera = camera
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="vision-worker", daemon=True)
        self._thread.start()
        return True

    def _run(self) -> None:
        import cv2

        detector = self.detector_factory()
        while not self._stop.is_set() and self._camera is not None:
            ok, image = self._camera.read()
            if not ok:
                with self._lock:
                    self._latest = GestureFrame(time.monotonic(), (), False)
                time.sleep(0.05)
                continue
            image = cv2.flip(image, 1)
            hands = detector.find(image)
            poses = self._poses(hands)
            with self._lock:
                self._image = image
                self._latest = GestureFrame(time.monotonic(), tuple(poses), True)

    def _poses(self, hands) -> list[HandPose]:
        poses: list[HandPose] = []
        seen: set[str] = set()
        for index, hand in enumerate(hands):
            key = str(hand.get("type", "hand"))
            if key in seen:
                key = f"{key}{index}"
            seen.add(key)
            landmarks = hand["lmList"]
            size = _distance(landmarks[0], landmarks[9]) + 1e-6
            fingers = _finger_states(landmarks)
            gesture = classify_element(
                fingers,
                spread_degrees=_spread_degrees(landmarks),
                pinch_ratio=_distance(landmarks[4], landmarks[8]) / size,
                spread_threshold=self.profile.spread_threshold,
            )
            smoothed = self._smoother.update(key, gesture)
            palm = np.mean([[landmarks[i][0], landmarks[i][1]] for i in (0, 5, 9, 13, 17)], axis=0)
            tip = landmarks[8] if fingers[1] else landmarks[9]
            direction = np.asarray((tip[0] - landmarks[0][0], tip[1] - landmarks[0][1]), dtype=float)
            direction /= np.linalg.norm(direction) + 1e-6
            poses.append(
                HandPose(
                    key,
                    smoothed,
                    (float(palm[0]), float(palm[1])),
                    (float(direction[0]), float(direction[1])),
                    size,
                    float(hand.get("score", 1.0)),
                )
            )
        self._smoother.retain(seen)
        return poses

    def latest(self) -> GestureFrame:
        with self._lock:
            return self._latest

    def latest_image(self):
        with self._lock:
            return None if self._image is None else self._image.copy()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        if self._camera is not None:
            self._camera.release()
        self._camera = None


def find_cameras(max_index: int = 6) -> list[int]:
    found: list[int] = []
    for camera_id in range(max_index):
        camera = _OpenCvCamera(camera_id)
        if camera.is_opened():
            ok, _ = camera.read()
            if ok:
                found.append(camera_id)
        camera.release()
    return found

