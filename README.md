# Elemental Convergence

Elemental Convergence is a Windows-first, gesture-controlled action game built with Python, OpenCV, MediaPipe/cvzone, and Pygame. Your webcam becomes the arena: hand poses cast elemental powers while you restore four seals and defeat the Rift Sovereign in a finite five-level campaign.

The project began as a single-file hand-effects prototype. It is now organized into independently testable vision, game, presentation, and persistence modules. The original `python handTrack.py` command remains the supported compatibility entrypoint.

## Game at a glance

- A 20–30 minute campaign with a clear ending, results, and credits.
- Five gestures, five powers, staged enemy introductions, and a two-hand ultimate.
- Story, Balanced, and Master difficulty presets.
- Guided camera/gesture calibration and a no-pressure recognition Sandbox.
- Persistent unlocked levels, completion records, best scores, and accessibility settings.
- Keyboard/mouse menus with webcam gestures reserved for combat.
- A 1280×720 logical playfield that scales to windowed or fullscreen displays.

### Campaign

| Stage | Power introduced | Gesture | Main threats |
| --- | --- | --- | --- |
| Stonewake Sanctuary | Earth | Fist | Shooters and Chargers |
| Tidelost Ruins | Water | Open palm, fingers spread | Snipers and Bombers |
| Skyglass Spires | Air | Open palm, fingers together | Gunners and Casters |
| Cinderforge | Fire | Index and middle fingers | Spinners, Sweepers, and Blinkers |
| Eclipse Citadel | Lightning and Convergence | Point; then bring both hands together | Mixed roster and the Rift Sovereign |

Every level has an illustrated introduction, briefing, three authored waves, a guardian encounter, results, and an outro. Losing all three lives restarts only the current level; unlocked stages remain saved.

## Requirements

- Windows 10/11 is the primary supported platform.
- Python 3.10–3.12.
- A webcam or virtual camera visible to OpenCV.
- Lighting bright enough for MediaPipe to see the full hand.

The game uses `opencv-python`, `cvzone`, `mediapipe`, `numpy`, and `pygame`. Development and packaging additionally use `pytest` and `pyinstaller`.

## Developer setup

From PowerShell:

```powershell
git clone https://github.com/somarjez/hand-battle.git
cd hand-battle
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python handTrack.py --windowed
```

Use a specific camera index when automatic index `0` is not the intended device:

```powershell
python handTrack.py --camera 1 --windowed
```

The installed console entrypoint is equivalent:

```powershell
elemental-convergence --camera 1
```

### Controls

| Input | Context | Action |
| --- | --- | --- |
| Arrow keys / `W` / `S` | Menus | Change selection |
| Mouse click | Main menu | Select an option |
| `Enter` / `Space` | Menus and story | Confirm or advance |
| `Esc` | Gameplay | Pause |
| `Esc` | Secondary screen | Return to the main menu |
| `C` | Calibration | Try the next camera index |
| `Space` | Calibration | Continue with default thresholds |

Combat casts automatically while a recognized pose is held and the relevant mana/cooldown permits it. Keep at least one hand visible: after the difficulty-specific grace period, missing hands drain health.

## Architecture

```text
handTrack.py                         Compatibility launcher
elemental_convergence/
├── app.py                           Pygame loop and subsystem composition
├── models.py                        Shared immutable input and difficulty types
├── vision.py                        Camera worker, landmark classification, calibration
├── content.py                       Validated level schema and loader
├── session.py                       Campaign combat rules and snapshots/events
├── persistence.py                   Versioned atomic save/settings repositories
├── data/levels.json                 Authored campaign content
├── assets/                          Optional original art/audio plus attribution
└── presentation/
    ├── scenes.py                    Pure navigation and player-flow state
    ├── renderer.py                  Responsive Pygame screens and HUD
    └── audio.py                     Best-effort music/SFX playback
tests/                               Hardware-independent unit and smoke tests
```

Runtime data flow:

```text
Camera → VisionService worker → immutable GestureFrame
                                     ↓
Pygame event loop → GameSession.update(dt, frame) → GameEvent values
                                     ↓
                              GameSnapshot → renderer
                                     ↓
                         results → atomic SaveRepository
```

Important boundaries:

- `VisionService.start(camera_id)`, `latest()`, `latest_image()`, and `stop()` own all camera/thread lifecycle behavior.
- `GameSession.start_level(...)`, `update(dt, frame)`, and `snapshot()` contain no Pygame or camera calls.
- `AppModel` contains screen navigation without display dependencies.
- Presentation treats art and audio as optional; a missing asset produces a procedural fallback rather than a crash.
- Combat timing is measured in seconds, not frames, so render-rate changes do not alter cooldowns or objectives.

## Authoring levels

Campaign data lives in `elemental_convergence/data/levels.json`. Order in the array is progression order. Every level requires exactly three waves and may link to one known next level.

```json
{
  "id": "stonewake",
  "title": "Stonewake Sanctuary",
  "unlock": "earth",
  "intro": ["Opening story line."],
  "outro": ["Closing story line."],
  "waves": [
    {"objective": "defeat_all", "enemies": {"shooter": 3}},
    {"objective": "defeat_all", "enemies": {"charger": 2}},
    {"objective": "survive", "duration_seconds": 30, "enemies": {"shooter": 2}}
  ],
  "boss": "stone_guardian",
  "next_level": "tidelost"
}
```

Supported objectives are `defeat_all`, `survive`, and `boss`. Enemy counts must be non-negative integers. The loader rejects duplicate IDs, invalid elements/objectives, malformed survival durations, missing links, and levels with other than three waves during startup and tests.

When adding a power or enemy, update the domain behavior first, add unit tests, then reference the new identifier from JSON. Do not put Python behavior names or arbitrary code in content files.

## Saves and settings

User data is stored outside the repository:

```text
%LOCALAPPDATA%\ElementalConvergence\save.json
%LOCALAPPDATA%\ElementalConvergence\settings.json
```

Both formats contain a `version` field and use write-to-temporary-file followed by atomic replacement. Malformed or unsupported files are renamed to `*.corrupt.json`, then replaced with safe defaults. The game saves level unlocks/completions and best scores, not mid-level combat state.

Settings include camera ID, fullscreen/fill behavior, hand overlay visibility, reduced flash/shake, and master/music/SFX volume. Delete `settings.json` to re-run defaults; delete both files to reset all local progress.

## Tests

The suite avoids real cameras, windows, and audio hardware. It covers:

- campaign schema and progression links;
- gesture classification, smoothing, calibration, and camera failure;
- seconds-based combat, hand-loss behavior, pause, waves, lives, and unlocks;
- atomic persistence and corrupt-file recovery;
- scene navigation, application imports, and headless Pygame rendering.

Run everything:

```powershell
python -m pytest -q
python -m compileall -q elemental_convergence handTrack.py
```

For a manual smoke test, launch windowed, finish calibration, enter Stonewake, verify all poses in Sandbox, pause/resume combat, lose/retry a level, complete it, restart the app, and confirm Tidelost remains unlocked.

## Windows packaging

Install development dependencies, then build the checked-in one-directory bundle:

```powershell
python -m PyInstaller --clean --noconfirm elemental-convergence.spec
```

The result is `dist\ElementalConvergence\ElementalConvergence.exe`. The one-directory layout is intentional: OpenCV/MediaPipe native libraries and optional assets are easier to inspect and troubleshoot than in a one-file self-extracting executable.

Before distributing a build, test it on a Windows account without the source checkout, with both a built-in and a virtual camera if available. Code-signing and installer creation are outside the current project scope.

## Troubleshooting

### No camera or a black preview

1. Close applications already using the webcam.
2. Enable Windows **Privacy & security → Camera → Let desktop apps access your camera**.
3. Try `python handTrack.py --camera 1 --windowed`, then indices `2` through `5`.
4. For a phone/virtual camera, start its desktop and phone components before launching the game.

### Gestures flicker or classify incorrectly

- Keep the full wrist and fingertips inside the frame.
- Use even front lighting and avoid a bright window behind the hand.
- Move farther from the camera if fingertips leave the frame.
- Revisit Calibration and hold each pose steadily; Water requires visibly spread fingers while Air keeps them together.

### Low frame rate

- Close other camera and GPU-heavy applications.
- Use windowed mode while diagnosing.
- Avoid very high-resolution virtual-camera output; the game targets a 1280×720 logical arena.
- Confirm the same Python environment contains compatible NumPy, OpenCV, MediaPipe, and Pygame versions.

### No sound

Audio is best-effort. Confirm a Windows output device is enabled and check the three volume settings. Missing optional `.ogg` files do not prevent gameplay.

## Contributing

Keep changes inside the subsystem that owns the behavior. Write a failing test before changing production code, run the full suite afterward, and keep camera/audio dependencies out of domain tests. New art or audio must be original or redistributable and documented in `elemental_convergence/assets/ATTRIBUTION.md`.

Pull requests should explain why the change is needed, list the affected player/developer behavior, and mention any manual camera validation that reviewers must perform locally.

## Credits

- Computer vision: OpenCV, MediaPipe, and cvzone.
- Windowing, rendering, and audio: Pygame.
- Original title artwork: generated specifically for this repository; see the asset attribution file.
