"""Backward-compatible launcher for Elemental Convergence.

Existing users can continue running ``python handTrack.py``. Application
code lives in the ``elemental_convergence`` package.
"""

from elemental_convergence.app import main


if __name__ == "__main__":
    raise SystemExit(main())
