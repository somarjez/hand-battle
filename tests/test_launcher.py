import handTrack

from elemental_convergence.app import main


def test_legacy_script_is_a_compatibility_launcher_for_the_modular_app():
    assert handTrack.main is main

