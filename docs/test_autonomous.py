#!/usr/bin/env python3
"""
Autonomous obstacle avoidance — TEST MODE.

Low-speed (25-30) autonomous driving with Claude vision API
for direction decisions when obstacles are detected.

Safety rules:
  - Forward speed: 25 only
  - Hard stop if distance < 50cm (overrides everything)
  - Stop and scan if distance < 60cm
  - Claude API decides LEFT or RIGHT based on camera images
"""

import sys
sys.path.insert(0, "/home/rambabu/rambabu_rc")

import argparse
import logging
import os
import signal
import time

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import cv2
import RPi.GPIO as GPIO

import config
from lib.motor import MotorController
from lib.camera import Camera
from lib.ultrasonic import Ultrasonic
from lib.pan_tilt import PanTilt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FORWARD_SPEED = 80          # Enough torque to move on ground
TURN_SPEED = 80             # Enough torque to turn on ground
SCAN_THRESHOLD_CM = 60.0    # Stop-and-scan threshold
TURN_DURATION = 0.8         # Seconds to drive while turning
LOOP_INTERVAL = 0.1         # Main loop sleep (seconds)
SAFETY_CHECK_INTERVAL = 0.05  # During movement, check every 50ms

LOG_DIR = "/home/rambabu/rambabu_rc/logs"
LOG_FILE = os.path.join(LOG_DIR, "test_autonomous.log")

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("test_autonomous")
logger.setLevel(logging.DEBUG)

_fmt = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

_fh = logging.FileHandler(LOG_FILE)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_fmt)
logger.addHandler(_fh)

_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(_fmt)
logger.addHandler(_ch)

# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------

motor: MotorController | None = None
ultra: Ultrasonic | None = None
pan_tilt: PanTilt | None = None
camera: Camera | None = None

_shutdown = False


def init_hardware() -> bool:
    """Initialize all hardware. Returns True on success."""
    global motor, ultra, pan_tilt, camera

    # Suppress libcamera stderr noise
    stderr_fd = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)

    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        logger.info("Initializing motor controller...")
        motor = MotorController()

        logger.info("Initializing ultrasonic sensor...")
        ultra = Ultrasonic()
        ultra.wait_for_reading(timeout=2.0)

        motor.set_obstacle_check(
            check_fn=lambda: ultra.is_obstacle_confirmed(),
            clear_fn=lambda: ultra.get_distance() > config.OBSTACLE_CLEAR_DISTANCE,
        )

        logger.info("Initializing pan/tilt...")
        try:
            pan_tilt = PanTilt()
        except Exception as e:
            logger.warning(f"PanTilt not available: {e}")
            return False

        logger.info("Initializing camera...")
        camera = Camera()
        result = camera.start()
        if result.get("status") != "ok":
            logger.error(f"Camera failed to start: {result}")
            return False

        # Let camera warm up
        time.sleep(1.0)
    finally:
        os.dup2(stderr_fd, 2)
        os.close(stderr_fd)
        os.close(devnull)

    dist = ultra.get_distance()
    logger.info(f"Hardware ready. Initial distance: {dist:.1f}cm")
    return True


def cleanup_hardware() -> None:
    """Stop motors and release all hardware."""
    if motor is not None:
        motor.stop()
        motor.cleanup()
    if pan_tilt is not None:
        pan_tilt.cleanup()
    if camera is not None:
        camera.cleanup()
    if ultra is not None:
        ultra.cleanup()
    GPIO.cleanup()
    logger.info("Hardware cleaned up.")


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

def is_safe_to_move() -> bool:
    """True if distance >= SCAN_THRESHOLD_CM."""
    return ultra.get_distance() >= SCAN_THRESHOLD_CM


# ---------------------------------------------------------------------------
# Camera capture helpers
# ---------------------------------------------------------------------------

def capture_jpeg() -> bytes | None:
    """Capture a single JPEG frame. Returns bytes or None."""
    frame = camera.get_frame()
    if frame is None:
        logger.error("Camera returned no frame")
        return None
    ok, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if not ok:
        logger.error("JPEG encoding failed")
        return None
    return jpeg.tobytes()


def capture_left_right() -> tuple[bytes | None, bytes | None]:
    """Pan camera left and right, capture images, return to center.

    Returns (left_jpeg, right_jpeg).
    """
    # Capture center first (already facing forward)
    logger.info("Capturing forward image...")
    capture_jpeg()  # discard — just for logging

    # Pan left and capture
    logger.info("Panning camera left...")
    pan_tilt.pan_left(deg=30)
    time.sleep(0.3)  # let servo settle + frame refresh
    left_img = capture_jpeg()
    logger.info(f"Left image: {len(left_img) if left_img else 0} bytes")

    # Pan right (from left, go 60 degrees right to reach right side)
    logger.info("Panning camera right...")
    pan_tilt.pan_right(deg=60)
    time.sleep(0.3)
    right_img = capture_jpeg()
    logger.info(f"Right image: {len(right_img) if right_img else 0} bytes")

    # Return to center
    logger.info("Centering camera...")
    pan_tilt.center()
    time.sleep(0.2)

    return left_img, right_img


# ---------------------------------------------------------------------------
# Claude Vision API — direction decision
# ---------------------------------------------------------------------------

def ask_claude_direction(left_img: bytes, right_img: bytes) -> str:
    """Send left and right images to Gemini Flash for direction decision.

    Returns "LEFT" or "RIGHT".
    """
    import io

    import google.generativeai as genai
    from PIL import Image

    genai.configure(api_key=os.environ["GOOGLE_GENERATIVE_AI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-pro")

    left_pil = Image.open(io.BytesIO(left_img))
    right_pil = Image.open(io.BytesIO(right_img))

    prompt = (
        "You are the brain of a small RC car. There is an obstacle ahead. "
        "I'm showing you what the car sees when it looks LEFT and RIGHT.\n\n"
        "Analyze both images and decide which direction has a clearer, "
        "safer path to drive through. Consider:\n"
        "- How much open floor/ground space is visible\n"
        "- Walls, furniture, objects, or people blocking the path\n"
        "- Which side has more room to maneuver\n\n"
        "Respond in this exact format:\n"
        "DIRECTION: LEFT or RIGHT\n"
        "REASON: one short sentence explaining why"
    )

    logger.info("Sending images to Gemini Flash for direction decision...")

    response = model.generate_content(
        ["LEFT side view:", left_pil, "RIGHT side view:", right_pil, prompt]
    )

    answer = response.text.strip()
    logger.info(f"Gemini vision response: {answer}")

    # Parse direction from response
    upper = answer.upper()
    if "DIRECTION: LEFT" in upper or "DIRECTION:LEFT" in upper:
        return "LEFT"
    if "DIRECTION: RIGHT" in upper or "DIRECTION:RIGHT" in upper:
        return "RIGHT"

    # Fallback — check if LEFT or RIGHT appears anywhere
    if "LEFT" in upper:
        return "LEFT"
    if "RIGHT" in upper:
        return "RIGHT"

    logger.warning(f"Ambiguous Gemini response '{answer}', defaulting to RIGHT")
    return "RIGHT"


# ---------------------------------------------------------------------------
# Movement with safety
# ---------------------------------------------------------------------------

def safe_forward(duration: float) -> bool:
    """Drive forward at FORWARD_SPEED for up to `duration` seconds.

    Checks distance every SAFETY_CHECK_INTERVAL. Returns True if
    completed the full duration, False if aborted early.
    """
    result = motor.front(FORWARD_SPEED)
    if result.get("status") != "ok":
        logger.warning(f"Forward refused: {result}")
        return False

    elapsed = 0.0
    while elapsed < duration:
        time.sleep(SAFETY_CHECK_INTERVAL)
        elapsed += SAFETY_CHECK_INTERVAL

        dist = ultra.get_distance()
        if dist < SCAN_THRESHOLD_CM:
            motor.stop()
            logger.warning(
                f"Safety abort during forward! dist={dist:.1f}cm at {elapsed:.2f}s"
            )
            return False

    motor.stop()
    return True


def execute_turn(direction: str) -> None:
    """Steer in `direction` ("LEFT"/"RIGHT"), drive briefly, then straighten."""
    logger.info(f"Executing turn: {direction}")

    # Safety check before turning
    if not is_safe_to_move():
        logger.warning("Cannot turn — too close to obstacle")
        return

    if direction == "LEFT":
        motor.steer_left_hold()
    else:
        motor.steer_right_hold()

    # Brief forward while turning
    completed = safe_forward(TURN_DURATION)

    # Always straighten and stop
    motor.stop()
    motor.steer_center()

    if completed:
        logger.info(f"Turn {direction} completed successfully")
    else:
        logger.info(f"Turn {direction} aborted early (safety)")


# ---------------------------------------------------------------------------
# One autonomous cycle
# ---------------------------------------------------------------------------

def run_one_cycle(_driving: list[bool] = [False]) -> str:
    """Run a single autonomous cycle. Returns a status string.

    Uses _driving mutable default to track whether motor is already running
    so we avoid stop-start between cycles.
    """
    dist = ultra.get_distance()

    if dist >= SCAN_THRESHOLD_CM:
        # Path is clear — keep driving
        if not _driving[0]:
            logger.info(f"Path clear (dist={dist:.1f}cm), driving forward...")
            motor.front(FORWARD_SPEED)
            _driving[0] = True
        return f"DRIVING (dist={dist:.1f}cm)"

    # Obstacle detected — stop, scan, ask Claude, turn
    motor.stop()
    _driving[0] = False
    logger.info(f"Obstacle ({dist:.1f}cm) — scanning left/right...")

    left_img, right_img = capture_left_right()

    if left_img is None or right_img is None:
        logger.error("Failed to capture scan images")
        return "SCAN_FAILED"

    direction = ask_claude_direction(left_img, right_img)
    execute_turn(direction)

    return f"TURNED_{direction} (dist={dist:.1f}cm)"


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

def _signal_handler(sig, frame):
    global _shutdown
    logger.info(f"Signal {sig} received — shutting down...")
    _shutdown = True


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous obstacle avoidance test")
    parser.add_argument(
        "--single",
        action="store_true",
        help="Run only one cycle (test mode), then exit",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("AUTONOMOUS TEST MODE — starting")
    logger.info(f"  Forward speed: {FORWARD_SPEED}")
    logger.info(f"  Scan trigger:  < {SCAN_THRESHOLD_CM}cm")
    logger.info(f"  Mode:          {'SINGLE CYCLE' if args.single else 'CONTINUOUS'}")
    logger.info("=" * 60)

    if not init_hardware():
        logger.error("Hardware init failed — aborting")
        cleanup_hardware()
        sys.exit(1)

    try:
        if args.single:
            # --- Test mode: one cycle only ---
            logger.info("Running single test cycle...")
            result = run_one_cycle()
            logger.info(f"Single cycle result: {result}")
        else:
            # --- Continuous loop ---
            cycle = 0
            while not _shutdown:
                cycle += 1
                logger.info(f"--- Cycle {cycle} ---")
                result = run_one_cycle()
                logger.info(f"Cycle {cycle} result: {result}")
                time.sleep(LOOP_INTERVAL)

            logger.info("Shutdown requested — stopping.")
    except Exception as e:
        logger.exception(f"Unhandled error: {e}")
        if motor is not None:
            motor.stop()
    finally:
        cleanup_hardware()

    logger.info("Autonomous test finished.")


if __name__ == "__main__":
    main()
