"""Export every synthesised sound effect and music track as WAV files, to audition or tweak them.

    python tools/export_audio.py [output_dir]        (default: ./audio_preview)

The game itself never needs these files: it generates the same audio at startup. To replace a sound with
your own recording, save it as ``elemental_convergence/assets/audio/<name>.ogg`` (same name, e.g.
``cast_fire.ogg`` or ``tidelost.ogg``) and it overrides the synthesised version.
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from elemental_convergence.presentation import synth  # noqa: E402


def write_wav(path: Path, samples) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(synth.SR)
        out.writeframes(samples.tobytes())


def main(argv: list[str]) -> int:
    target = Path(argv[1] if len(argv) > 1 else "audio_preview")
    (target / "sfx").mkdir(parents=True, exist_ok=True)
    (target / "music").mkdir(parents=True, exist_ok=True)
    for name in synth.SFX_NAMES:
        write_wav(target / "sfx" / f"{name}.wav", synth.make_sfx(name))
    for name in synth.MUSIC_NAMES:
        write_wav(target / "music" / f"{name}.wav", synth.make_music(name))
    print(f"wrote {len(synth.SFX_NAMES)} effects and {len(synth.MUSIC_NAMES)} tracks to {target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
