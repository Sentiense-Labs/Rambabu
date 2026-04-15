#!/usr/bin/env python3
"""
Make Rambabu speak text through the Bluetooth speaker.

Synthesizes via ElevenLabs and plays the mp3 in-memory. Falls back to
pyttsx3 if ElevenLabs is unavailable.

Usage:
    uv run python brain/say.py "Hello, I am Rambabu."
    uv run python brain/say.py I see a cat           # positional words
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, "/home/rambabu/rambabu_rc")
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from lib.speaker import Speaker  # noqa: E402
from utils.elevenlabs import synthesize  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("say")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rambabu speaks text aloud")
    parser.add_argument(
        "text",
        nargs="+",
        help="The words to speak (quoted string or positional words)",
    )
    args = parser.parse_args()

    text = " ".join(args.text).strip()
    if not text:
        print("status: error")
        print("message: no text provided")
        sys.exit(2)

    speaker: Speaker | None = None
    try:
        speaker = Speaker()
        mp3 = synthesize(text)
        if mp3 is not None:
            speaker.play_mp3_bytes(mp3)
            print("status: ok")
            print("engine: elevenlabs")
            print(f"bytes: {len(mp3)}")
        else:
            logger.warning("ElevenLabs failed — using pyttsx3 fallback")
            speaker.speak_sync(text)
            print("status: ok")
            print("engine: pyttsx3")
    except Exception as exc:
        logger.exception(f"Speech failed: {exc}")
        print("status: error")
        print(f"message: {exc}")
        sys.exit(1)
    finally:
        if speaker is not None:
            try:
                speaker.cleanup()
            except Exception:
                pass


if __name__ == "__main__":
    main()
