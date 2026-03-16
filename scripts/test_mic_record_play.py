#!/usr/bin/env python3
"""Record 10 seconds from USB mic, then play back through the speaker."""

import subprocess
import sys
import tempfile
from pathlib import Path

CARD = 3          # USB PnP Sound Device
DURATION = 10     # seconds
SAMPLE_RATE = 16000
CHANNELS = 1
FORMAT = "S16_LE"  # 16-bit signed little-endian

def main() -> None:
    wav_path = Path(tempfile.gettempdir()) / "mic_test_recording.wav"

    # ── Record ────────────────────────────────────────────────────────────
    print(f"Recording {DURATION}s from hw:{CARD},0 ...")
    result = subprocess.run(
        [
            "arecord",
            "-D", f"hw:{CARD},0",
            "-f", FORMAT,
            "-r", str(SAMPLE_RATE),
            "-c", str(CHANNELS),
            "-d", str(DURATION),
            str(wav_path),
        ],
        capture_output=True,
        text=True,
        timeout=DURATION + 5,
    )

    if result.returncode != 0:
        print(f"Recording failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    print(f"Saved to {wav_path} ({wav_path.stat().st_size} bytes)")

    # ── Playback ──────────────────────────────────────────────────────────
    print("Playing back ...")
    result = subprocess.run(
        ["aplay", "-D", "default", str(wav_path)],
        capture_output=True,
        text=True,
        timeout=DURATION + 5,
    )

    if result.returncode != 0:
        print(f"Playback failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    print("Done.")


if __name__ == "__main__":
    main()
