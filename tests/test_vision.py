from elemental_convergence.models import Element, GestureFrame, HandPose
from elemental_convergence.vision import (
    CalibrationProfile,
    CalibrationSession,
    GestureSmoother,
    VisionService,
    classify_element,
)


def test_element_gestures_map_to_the_documented_poses():
    assert classify_element((0, 0, 0, 0, 0)) is Element.EARTH
    assert classify_element((0, 1, 1, 0, 0)) is Element.FIRE
    assert classify_element((0, 1, 0, 0, 0)) is Element.LIGHTNING
    assert classify_element((0, 1, 1, 1, 1), spread_degrees=18) is Element.WATER
    assert classify_element((0, 1, 1, 1, 1), spread_degrees=7) is Element.AIR


def test_gesture_smoother_requires_a_majority_before_switching():
    smoother = GestureSmoother(window=5, votes_needed=3)

    assert smoother.update("left", Element.EARTH) is None
    assert smoother.update("left", Element.EARTH) is None
    assert smoother.update("left", Element.EARTH) is Element.EARTH
    assert smoother.update("left", Element.FIRE) is Element.EARTH
    assert smoother.update("left", Element.FIRE) is Element.EARTH
    assert smoother.update("left", Element.FIRE) is Element.FIRE


def test_calibration_requires_every_element_at_sufficient_confidence():
    session = CalibrationSession(CalibrationProfile(min_confidence=0.7))

    for index, element in enumerate(Element):
        confidence = 0.6 if element is Element.FIRE else 0.9
        session.observe(
            GestureFrame(
                timestamp=float(index),
                hands=(HandPose("left", element, (10, 10), (1, 0), 50, confidence),),
            )
        )

    assert session.missing == (Element.FIRE,)
    assert not session.complete
    session.observe(
        GestureFrame(6.0, (HandPose("left", Element.FIRE, (10, 10), (1, 0), 50, 0.9),))
    )
    assert session.complete


class ClosedCamera:
    def is_opened(self):
        return False

    def read(self):
        return False, None

    def release(self):
        pass


def test_vision_service_reports_recoverable_camera_start_failure():
    service = VisionService(camera_factory=lambda _camera_id: ClosedCamera())

    assert service.start(4) is False
    assert service.latest().camera_ok is False
    service.stop()

