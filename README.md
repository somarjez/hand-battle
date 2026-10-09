# Hand Battle

A real-time hand-tracking battle game built with Python, OpenCV, cvzone, and MediaPipe. Use hand gestures through your webcam to control elemental powers, defeat enemies, fight bosses, and activate the Avatar State.

## Features

- Real-time hand tracking and gesture recognition
- Avatar and Classic gameplay modes
- Five elemental attacks
- Enemy waves with multiple enemy types
- Boss battles
- Health, lives, mana, and kill tracking
- Two-hand gesture support
- Fullscreen and camera-switching controls
- Support for built-in and virtual cameras such as Iriun Webcam

## Requirements

- Python 3.10 or later
- A webcam or virtual camera
- OpenCV
- cvzone
- MediaPipe
- NumPy

## Installation

Clone the repository:

```bash
git clone https://github.com/somarjez/hand-battle.git
cd hand-battle
```

Install the dependencies:

```bash
pip install opencv-python cvzone mediapipe numpy
```

## Running the Game

Let the game search for available cameras:

```bash
python handTrack.py
```

Select a specific camera directly:

```bash
python handTrack.py --camera 1
```

Camera `0` is normally the built-in webcam. Virtual cameras such as Iriun may use camera `1` or another index.

## Avatar Mode

Avatar Mode is enabled by default.

| Gesture | Power |
|---|---|
| Fist | Earth Blast |
| Index finger pointing | Lightning |
| Open palm with fingers apart | Water Blast |
| Open palm with fingers together | Air Blast |
| Index and middle fingers raised | Fire Blast |
| Both hands together | Avatar State |

Avatar State becomes available after 10 kills. Hold both hands together to activate all elements temporarily with increased power and invincibility.

## Classic Mode

Press `A` to switch between Avatar Mode and Classic Mode.

| Gesture | Effect |
|---|---|
| Open palm | Fire |
| Fist | Ice |
| Peace sign | Love |
| Index finger pointing | Lightning |

## Survival Gameplay

In Avatar Mode, enemies attack your hands with projectiles, lasers, bombs, and charge attacks.

- Dodge attacks by moving your hands.
- Destroy enemy projectiles using elemental powers.
- Keep at least one hand visible to avoid losing health.
- Defeat enemies to charge the Avatar State.
- Boss battles occur as your kill count increases.
- Press `R` to restart after a game over.

## Controls

| Key | Action |
|---|---|
| `A` | Switch between Avatar and Classic modes |
| `C` | Switch to the next available camera |
| `E` | Toggle enemies on or off |
| `F` | Toggle fullscreen |
| `M` | Switch between fill and fit display modes |
| `R` | Restart the battle |
| `Q` or `Esc` | Quit |

## Troubleshooting

### No camera detected

Make sure your webcam is connected and not being used by another application. If you use Iriun Webcam, start Iriun on both your computer and phone before running the game.

You can also specify the camera manually:

```bash
python handTrack.py --camera 1
```

Try other indexes such as `0`, `2`, or `3` if necessary.

### Poor gesture detection

- Keep your hands fully visible.
- Use a well-lit environment.
- Avoid placing your hands too close to the edge of the camera frame.
- Keep the background reasonably clear.
- Move your hands steadily when changing gestures.

## Technologies

- [Python](https://www.python.org/)
- [OpenCV](https://opencv.org/)
- [cvzone](https://github.com/cvzone/cvzone)
- [MediaPipe](https://developers.google.com/mediapipe)
- [NumPy](https://numpy.org/)

## Acknowledgements

This project builds upon the original hand-tracking implementation by [eshansurendra/handTrackWithOpenCV](https://github.com/eshansurendra/handTrackWithOpenCV).
