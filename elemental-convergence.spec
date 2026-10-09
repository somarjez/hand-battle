# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "handTrack.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "elemental_convergence" / "data" / "levels.json"), "elemental_convergence/data"),
        (str(root / "elemental_convergence" / "assets"), "elemental_convergence/assets"),
    ],
    hiddenimports=["cvzone.HandTrackingModule", "mediapipe", "pygame"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ElementalConvergence",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="ElementalConvergence",
)

