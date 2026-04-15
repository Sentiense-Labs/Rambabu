#!/usr/bin/env python3
"""
Rambabu look-around — single-shot observation routine.

Captures one frame from the camera in its current position, asks a
Gemini Flash model for a short first-person description, and speaks
it through the Bluetooth speaker via ElevenLabs (with pyttsx3 fallback).

Pan-tilt is intentionally not used here — the PCA9685 board needs the
buck converter rail, which is only live on the full power setup.

Usage:
    uv run python brain/look_around.py
    uv run python brain/look_around.py --print-only   # skip TTS
    uv run python brain/look_around.py -i "count the people you see"
    uv run python brain/look_around.py "is there a cup on the table?"
"""

import argparse
import io
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

sys.path.insert(0, "/home/rambabu/rambabu_rc")
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import cv2  # noqa: E402
import RPi.GPIO as GPIO  # noqa: E402
from google import genai  # type: ignore  # noqa: E402
from google.genai import types  # type: ignore  # noqa: E402
from PIL import Image  # noqa: E402

from lib.camera import Camera  # noqa: E402
from lib.speaker import Speaker  # noqa: E402
from utils.elevenlabs import synthesize  # noqa: E402

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

GEMINI_MODEL = "gemini-2.5-flash-lite"  # Fastest multimodal Gemini
MAX_IMAGE_DIM = 512  # Downscale before sending to Gemini
JPEG_QUALITY = 80

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("look_around")


# ---------------------------------------------------------------------------
# Hardware init — camera and speaker initialize in parallel
# ---------------------------------------------------------------------------


def _init_camera() -> Camera:
    camera = Camera()
    result = camera.start()
    if result.get("status") != "ok":
        raise RuntimeError(f"Camera failed to start: {result}")
    # Wait for the first real frame instead of a blind warmup sleep.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if camera.get_frame() is not None:
            return camera
        time.sleep(0.05)
    raise RuntimeError("Camera did not produce a frame within 2s")


def _init_speaker() -> Speaker:
    return Speaker()


def init_hardware() -> tuple[Camera, Speaker]:
    """Initialize camera and speaker concurrently. Suppresses libcamera noise."""
    stderr_fd = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        logger.info("Initializing camera + speaker (parallel)...")
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=2) as pool:
            cam_future = pool.submit(_init_camera)
            spk_future = pool.submit(_init_speaker)
            camera = cam_future.result()
            speaker = spk_future.result()
        logger.info(f"Hardware ready in {time.time() - t0:.2f}s")
    finally:
        os.dup2(stderr_fd, 2)
        os.close(stderr_fd)
        os.close(devnull)

    return camera, speaker


def cleanup_hardware(camera: Camera | None, speaker: Speaker | None) -> None:
    """Best-effort cleanup — never raises."""
    if camera is not None:
        try:
            camera.cleanup()
        except Exception as exc:
            logger.warning(f"Camera cleanup: {exc}")
    if speaker is not None:
        try:
            speaker.cleanup()
        except Exception as exc:
            logger.warning(f"Speaker cleanup: {exc}")
    try:
        GPIO.cleanup()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def capture_jpeg(camera: Camera) -> bytes | None:
    """Grab a single frame and JPEG-encode it. Returns bytes or None."""
    frame = camera.get_frame()
    if frame is None:
        logger.error("Camera returned no frame")
        return None
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        logger.error("JPEG encoding failed")
        return None
    return jpeg.tobytes()


# ---------------------------------------------------------------------------
# Gemini — scene description
# ---------------------------------------------------------------------------

_BASE_PERSONA = (
    "You are Rambabu, a small AI-powered RC rover with a camera. "
    "This image is what you can see right now."
)

_DEFAULT_TASK = (
    "Describe your surroundings in 2-3 short conversational sentences "
    "— first person, present tense. Mention specific objects you "
    "notice. Be curious and a little opinionated if something catches "
    "your eye. If the view is boring, say so honestly."
)

_OUTPUT_RULES = (
    "Output only the spoken words — no brackets, no stage directions, "
    "no bullet points, no labels."
)


def build_prompt(instruction: str | None) -> str:
    """Compose the Gemini prompt, folding in an optional user instruction."""
    if instruction and instruction.strip():
        task = (
            f'The user just told you: "{instruction.strip()}"\n'
            "Respond to that request based on what you see in the image, "
            "in 2-3 short conversational sentences — first person, present "
            "tense. Stay in character as Rambabu."
        )
    else:
        task = _DEFAULT_TASK
    return f"{_BASE_PERSONA}\n\n{task}\n\n{_OUTPUT_RULES}"


def describe_scene(jpeg: bytes, instruction: str | None = None) -> str | None:
    """Send the captured frame to Gemini and return a short description.

    Returns None on any API failure. Never raises.
    """
    api_key = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY")
    if not api_key:
        logger.error("GOOGLE_GENERATIVE_AI_API_KEY not set")
        return None

    try:
        # Downscale — preserves aspect ratio, only shrinks.
        image = Image.open(io.BytesIO(jpeg))
        image.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM))
        # Re-encode as JPEG for the new SDK (does not accept PIL directly).
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=JPEG_QUALITY)
        image_part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")

        client = genai.Client(api_key=api_key)
        prompt = build_prompt(instruction)
        logger.info(f"Asking {GEMINI_MODEL} ({image.size[0]}x{image.size[1]})...")
        t0 = time.time()
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[image_part, prompt],
        )
        logger.info(f"Gemini replied in {time.time() - t0:.2f}s")

        text = (response.text or "").strip()
    except Exception as exc:
        logger.error(f"Gemini request failed: {exc}")
        return None

    if not text:
        logger.error("Gemini returned empty text")
        return None

    return text


# ---------------------------------------------------------------------------
# Speech
# ---------------------------------------------------------------------------


def speak(speaker: Speaker, text: str) -> None:
    """Speak `text` via ElevenLabs, fall back to pyttsx3 on failure."""
    t0 = time.time()
    mp3 = synthesize(text)
    logger.info(f"ElevenLabs synth in {time.time() - t0:.2f}s")
    if mp3 is not None:
        speaker.play_mp3_bytes(mp3)
    else:
        logger.warning("ElevenLabs failed — using pyttsx3 fallback")
        speaker.speak_sync(text)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Rambabu look-around")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print Gemini's description but don't speak it",
    )
    parser.add_argument(
        "-i",
        "--instruction",
        type=str,
        default=None,
        help="Optional instruction/question for Rambabu about the scene",
    )
    parser.add_argument(
        "instruction_positional",
        nargs="*",
        help="Instruction as trailing positional words (alternative to -i)",
    )
    args = parser.parse_args()

    instruction = args.instruction
    if not instruction and args.instruction_positional:
        instruction = " ".join(args.instruction_positional)
    if instruction:
        logger.info(f"Instruction: {instruction}")

    script_start = time.time()
    logger.info("Rambabu look-around starting...")

    camera: Camera | None = None
    speaker: Speaker | None = None
    try:
        camera, speaker = init_hardware()

        t0 = time.time()
        jpeg = capture_jpeg(camera)
        logger.info(f"Captured frame in {time.time() - t0:.2f}s")
        if jpeg is None:
            logger.error("No frame captured — aborting")
            if not args.print_only:
                speak(speaker, "I can't see anything right now.")
            return

        description = describe_scene(jpeg, instruction)
        if description is None:
            logger.error("Gemini failed — speaking fallback")
            if not args.print_only:
                speak(speaker, "I looked around but I'm not sure what I'm seeing.")
            return

        logger.info(f"Gemini: {description}")
        print(description)
        if not args.print_only:
            speak(speaker, description)

    except Exception as exc:
        logger.exception(f"Unhandled error: {exc}")
    finally:
        cleanup_hardware(camera, speaker)
        logger.info(f"Done. Total: {time.time() - script_start:.2f}s")


if __name__ == "__main__":
    main()
