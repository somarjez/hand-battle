# Elemental Convergence

Elemental Convergence is a Windows-first, gesture-controlled action game built with Python, OpenCV, MediaPipe/cvzone, and Pygame. Your webcam becomes the arena: hand poses cast elemental powers while you restore the five seals of the Loom of Dawn and face the Rift Sovereign in a finite five-stage campaign.

> *The sun did not rise on the day the Rift opened. You are the last Warden. Your hands remember how to speak to the elements.*

The project began as a single-file hand-effects prototype. It is now organized into independently testable vision, game, presentation, and persistence modules. The original `python handTrack.py` command remains the supported compatibility entrypoint.

## Game at a glance

- A 30-40 minute campaign with a prologue, named keepers, guardian dialogue, an epilogue and credits.
- Five gestures, five powers, a two-palm ultimate, loot pick-ups and combo scoring.
- Three-star rating per stage, best scores, a lore and bestiary Codex.
- Every stage has its own hazard, music theme and colour, and a guardian that changes phase as it is hurt.
- Story, Balanced and Master difficulty presets.
- Guided camera/gesture calibration and a no-pressure recognition Sandbox.
- Full keyboard and mouse menus (settings with sliders, pause menu, level select, codex); webcam gestures are reserved for combat.
- The camera picture fills any window or fullscreen shape without stretching, and hand positions match it exactly.

### Campaign

| Stage | Keeper | Power | Hazard | Main threats | Music |
| --- | --- | --- | --- | --- | --- |
| Stonewake Sanctuary | Orrin the Unmoving | Earth (fist) | Falling rocks | Shooters, Chargers | low, earthen, steady drums |
| Tidelost Ruins | Sael of the Drowned Bell | Water (spread palm) | Tidal surge | Snipers, Bombers | flowing, bell arpeggios |
| Skyglass Spires | Ysa, Windreader | Air (closed palm) | Lightning storm | Gunners, Casters | bright, fast shimmer |
| Cinderforge | Kael Emberhand | Fire (two fingers) | Forge flare | Spinners, Sweepers, Blinkers | driving, four on the floor |
| Eclipse Citadel | Veyra, the Rift Sovereign | Lightning (point) + Convergence | Eclipse surge (all of them) | Mixed roster | dark and heavy |

Each stage plays out as four beats: **defeat everyone**, **hunt** a quota while reinforcements arrive, **survive** the clock (with an **elite** enemy), then the **guardian**, which opens a new phase (and calls minions) at two thirds and one third health and enrages at half. Losing all three lives restarts only the current stage; progress stays saved.

**Scoring.** Kills are worth 100 (elites 300, guardians 1000) multiplied by a combo: chain kills within three seconds and the multiplier climbs to x5. **Stars:** clear the stage (1), lose no life (2), and take five hits or fewer (3).

**Hazards** are always telegraphed (red circles, tightening lines, a banner): rockfall drops bombs, the tide sends a wall of orbs with one gap, storms drop beams, forge flares cluster bombs around you.

### Combat & look

The battle screen is drawn exactly like the original `gesture_powers.py` prototype (OpenCV drawing, the same colours, Hershey fonts, additive glow, particles, projectiles, chain lightning, screen shake and HUD layout). See `presentation/battle_view.py`. The campaign (levels, waves, guardians, saves) runs underneath it.

Enemies fight back with real, dodgeable attacks aimed at your hands. Dodge with your hands, or shoot incoming orbs out of the air with your own blasts.

| Enemy | Attacks |
| --- | --- |
| Shooter | aimed orbs, 3-orb fans |
| Charger | winds up (red lane), then body-slams your hand |
| Sniper | tracking laser beam |
| Gunner | rapid bursts, a wall of orbs with a gap |
| Bomber | delayed bombs (leave the red circle) |
| Caster | rings of orbs, homing orbs (orange, shoot them down) |
| Spinner | spiral orb streams |
| Sweeper | sweeping beam, cross of beams |
| Blinker | teleports next to you, then fires |
| Guardians | all of the above plus summons, and an enrage at half health |

**Blocking.** Your blasts are also your shield: they shoot down enemy orbs along their path (Air has the widest reach), defuse bombs they cross, and *interrupt* any non-guardian enemy that is still charging (dash wind-up, beam warning, spiral, burst). You'll see BLOCKED, DEFUSED and INTERRUPTED pop up. A beam that is already firing can't be stopped, so dodge it.

**Convergence.** Defeat 10 enemies to fill the meter (a guardian counts as 5). Then press both palms together and hold for about half a second; a ring fills between your hands while it charges. It only fires for two distinct hands that are almost touching: one hand, a hand the tracker detects twice, or hands that are merely close will not trigger it, and it can't fire while the meter is below full. The tuning constants (`TOGETHER_NEAR`, `TOGETHER_HOLD`, `CONVERGENCE_KILLS`, ...) are at the top of `session.py`. For about 1.8 seconds everything on screen is hit, including minions, summons and reinforcements that arrive during the light show, and the ultimate's own kills no longer recharge the meter. `CONVERGENCE_BOSS_FRACTION` in `session.py` controls how much of a guardian's health it removes (1.0 = defeats it, 0.5 = half).

**Loot.** Pick-ups float in the arena (and sometimes drop from defeated enemies). Touch them with a hand before they fade (12 s, the ring around each shows the time left):

| Pick-up | Effect |
| --- | --- |
| Heart | +25 HP |
| Regen | +5 HP per second for 6 s |
| Shield | blocks every hit for 8 s (ring around your hands) |
| Boost | blasts do 1.5x damage and fire 35% faster for 10 s |
| Earth / Water / Air / Fire / Lightning mana | refills that element's mana (only elements you have unlocked appear) |

What spawns is weighted by need: hearts are more likely when you're hurt, and mana for an element is more likely when it is low. All the numbers are constants near the top of `session.py`.

### Screen & camera

* The camera picture fills the whole screen. It is cropped to fit, never stretched, and fullscreen uses your monitor's own resolution.
* The game canvas always has the same shape as the window, so there are no black bars on 16:10, 4:3 or ultrawide screens.
* Hand positions are mapped with exactly the same crop as the picture (`models.scale_frame`), so the hand you see is where the game sees it.

Tuning lives in `elemental_convergence/combat.py` (attack speeds, damage, warning times) and the balance block at the top of `elemental_convergence/session.py` (`ENEMY_BASE_HP`, `BOSS_BASE_HP`, protection time). Reduced flash / reduced shake in Settings tone down the flashes and shake.

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
| Arrow keys / `W` `A` `S` `D` | Menus | Move the highlight; Left / Right change sliders, toggles and choices |
| Mouse | Menus | Hover to highlight, click to select, click or drag sliders |
| `Enter` / `Space` | Menus and story | Confirm, or skip the text reveal and then advance |
| Left / Right | Level select, Codex, How to Play | Choose a seal, switch tab, turn page |
| `Esc` | Gameplay | Pause (resume, restart, settings, quit to menu) |
| `Esc` | Any other screen | Go back (the main menu quits) |
| `F11` | Anywhere | Toggle fullscreen |
| `C` / `Space` | Calibration | Try the next camera / continue with default thresholds |

Combat casts automatically while a recognized pose is held and the relevant mana/cooldown permits it. Keep at least one hand visible: after the difficulty-specific grace period, missing hands drain health.

### Menus and settings

The **Settings** screen changes everything live and saves as you go: master, music and effects volume (sliders), difficulty, fullscreen, reduced flash, reduced shake, gesture labels, which camera to use, recalibration, and a confirmed *Reset progress*. The same screen opens from the pause menu and returns to it.

### Audio

All 34 sound effects and 9 music tracks are synthesised in code at startup on a background thread (about two seconds in total), so there are no audio files to ship. Each spell, hit, pick-up and warning has its own sound; every stage has its own theme; the guardian fight switches to a boss theme; results play a victory or defeat stinger. Music crossfades between screens and quietens while paused; a heartbeat quickens as health drops. Run `python tools/export_audio.py` to write everything out as WAV files, and drop an `.ogg` named after a sound into `elemental_convergence/assets/audio/` to replace it.

## Architecture

```text
handTrack.py                         Compatibility launcher
elemental_convergence/
├── app.py                           Pygame loop and subsystem composition
├── models.py                        Shared immutable input and difficulty types
├── vision.py                        Camera worker, landmark classification, calibration
├── content.py                       Validated level schema and loader
├── story.py                         Prologue, epilogue, codex text, how-to-play pages
├── combat.py                        Enemy roster, attack patterns, hazards (pure logic)
├── session.py                       Campaign rules: waves, scoring, loot, snapshots/events
├── menus.py                         Menu model: buttons, sliders, toggles, choices
├── persistence.py                   Versioned atomic save/settings repositories
├── data/levels.json                 Authored campaign content
├── assets/                          Optional original art and audio overrides
└── presentation/
    ├── scenes.py                    Pure navigation and player-flow state
    ├── renderer.py                  Menu backgrounds, text helpers, gameplay entry point
    ├── screens.py                   Menu, level select, results, pause, codex, story scenes
    ├── battle_view.py               The OpenCV battle screen (enemies, effects, HUD)
    ├── synth.py                     Procedural sound effects and music (NumPy only)
    └── audio.py                     Audio engine: crossfades, throttling, event mapping
tools/export_audio.py                Writes every sound and track as WAV
tests/                               Hardware-independent unit and full-app headless tests
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
- Presentation treats art as optional and generates all audio itself; a missing asset or sound device never crashes the game.
- Combat timing is measured in seconds, not frames, so render-rate changes do not alter cooldowns or objectives.

## Authoring levels

Campaign data lives in `elemental_convergence/data/levels.json`. Order in the array is progression order. Every level requires exactly three waves (then the guardian) and may link to one known next level. Story fields are optional, so older content still loads.

```json
{
  "id": "stonewake",
  "title": "Stonewake Sanctuary",
  "subtitle": "The Seal of Stone",
  "keeper": "Orrin the Unmoving",
  "unlock": "earth",
  "intro": ["Opening story lines."],
  "outro": ["Closing story lines."],
  "wave_titles": ["Tremors", "Shadows in the Rubble", "The Long Night", "The Stone Guardian"],
  "boss": "stone_guardian",
  "boss_name": "Stone Guardian",
  "boss_lines": {"intro": "...", "phase2": "...", "phase3": "...", "defeat": "..."},
  "lore": ["Codex text, unlocked when the seal is restored."],
  "hazard": {"kind": "rockfall", "label": "FALLING ROCKS!", "first": 9, "interval": 11},
  "waves": [
    {"objective": "defeat_all", "enemies": {"shooter": 3}},
    {"objective": "hunt", "quota": 8, "enemies": {"shooter": 2, "charger": 2}},
    {"objective": "survive", "duration_seconds": 30, "enemies": {"shooter": 2, "charger": 2}, "elite": ["charger"]}
  ],
  "next_level": "tidelost"
}
```

Objectives are `defeat_all`, `hunt` (needs a positive `quota`; enemies keep arriving until it is met) and `survive` (needs `duration_seconds`; replacements keep arriving). `elite` lists extra, tougher enemies that join the wave. Hazard kinds are `rockfall`, `tide`, `storm`, `forge` and `eclipse`. The loader rejects duplicate IDs, unknown elements, objectives or hazards, malformed durations or quotas, missing links, and levels with other than three waves, at startup and in tests.

When adding a power, enemy or hazard, update the domain behavior first (`combat.py`, `session.py`), add unit tests, then reference the new identifier from JSON. Every enemy needs an entry in `story.ENEMY_LORE` (a test enforces it). Do not put Python behavior names or arbitrary code in content files.

## Saves and settings

User data is stored outside the repository:

```text
%LOCALAPPDATA%\ElementalConvergence\save.json
%LOCALAPPDATA%\ElementalConvergence\settings.json
```

Both formats contain a `version` field and use write-to-temporary-file followed by atomic replacement. Malformed or unsupported files are renamed to `*.corrupt.json`, then replaced with safe defaults. The game saves level unlocks and completions, best scores, best stars, the bestiary and whether the prologue was seen, not mid-level combat state. Save version 2 loads version 1 files unchanged (the new fields default).

Settings include camera ID, fullscreen/fill behavior, hand overlay visibility, reduced flash/shake, and master/music/SFX volume. Delete `settings.json` to re-run defaults; delete both files to reset all local progress.

## Tests

The suite avoids real cameras, windows, and audio hardware. It covers:

- campaign schema and progression links;
- gesture classification, smoothing, calibration, and camera failure;
- seconds-based combat, hand-loss behavior, pause, waves, lives, and unlocks;
- atomic persistence and corrupt-file recovery;
- hunt waves, elites, hazards, boss phases, combo scoring, stars and save migration;
- every sound effect and music track (audible, unclipped, click-free, loops seamlessly) and the event-to-sound mapping;
- the menu model, and full-app flows driven headlessly with keyboard and mouse (settings, pause, results, level select, codex);
- scene navigation, hand-to-screen mapping on any window shape, and headless Pygame rendering.

Run everything:

```powershell
python -m pytest -q
ruff check .
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
