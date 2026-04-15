#!/usr/bin/env python3
"""
Move Rambabu for a short duration.

One-shot movement primitive. Forward/left/right calls check the
ultrasonic sensor before and during the move and abort if an obstacle
drops below the safety threshold. Max duration is capped at 9 seconds
per call — longer motions must be chained.

Usage:
    uv run python brain/move.py forward 0.5
    uv run python brain/move.py back 0.3
    uv run python brain/move.py left 0.6
    uv run python brain/move.py right 0.6
    uv run python brain/move.py stop
"""

import argparse
import logging
import sys
import time

sys.path.insert(0, "/home/rambabu/rambabu_rc")

import RPi.GPIO as GPIO

from lib.motor import MotorController
from lib.ultrasonic import Ultrasonic

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

DRIVE_SPEED = 80             # 0-100 motor speed
MAX_DURATION = 9.0           # Seconds — hard cap on any single command
REVERSE_MAX_DURATION = 0.5   # Hard cap for any reverse-family direction
SAFETY_DISTANCE_CM = 50.0    # Refuse/abort forward if sonar drops below this
SAFETY_POLL_INTERVAL = 0.05  # Check distance every 50ms while driving

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("move")


# ---------------------------------------------------------------------------
# Hardware lifecycle
# ---------------------------------------------------------------------------

def init_hardware(
    need_sonar: bool,
) -> tuple[MotorController, Ultrasonic | None]:
    """Initialize motor, and ultrasonic if the action needs safety checks."""
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    motor = MotorController()
    ultra: Ultrasonic | None = None
    if need_sonar:
        ultra = Ultrasonic()
        ultra.wait_for_reading(timeout=2.0)
    return motor, ultra


def cleanup_hardware(
    motor: MotorController | None, ultra: Ultrasonic | None
) -> None:
    """Best-effort cleanup — never raises."""
    if motor is not None:
        try:
            motor.stop()
            motor.cleanup()
        except Exception as exc:
            logger.warning(f"Motor cleanup: {exc}")
    if ultra is not None:
        try:
            ultra.cleanup()
        except Exception as exc:
            logger.warning(f"Ultrasonic cleanup: {exc}")
    try:
        GPIO.cleanup()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Movement with safety
# ---------------------------------------------------------------------------

def drive_forward_safe(
    motor: MotorController, ultra: Ultrasonic, duration: float
) -> dict:
    """Drive forward for `duration`, aborting if sonar crosses safety limit.

    Returns a status dict describing what happened.
    """
    dist = ultra.get_distance()
    if dist < SAFETY_DISTANCE_CM:
        return {
            "status": "blocked",
            "reason": "obstacle_too_close",
            "distance_cm": round(dist, 1),
            "threshold_cm": SAFETY_DISTANCE_CM,
        }

    motor.front(DRIVE_SPEED)
    elapsed = 0.0
    while elapsed < duration:
        time.sleep(SAFETY_POLL_INTERVAL)
        elapsed += SAFETY_POLL_INTERVAL
        current = ultra.get_distance()
        if current < SAFETY_DISTANCE_CM:
            motor.stop()
            return {
                "status": "aborted",
                "reason": "safety_stop",
                "elapsed_s": round(elapsed, 2),
                "distance_cm": round(current, 1),
            }

    motor.stop()
    return {
        "status": "ok",
        "direction": "forward",
        "duration_s": round(duration, 2),
        "final_distance_cm": round(ultra.get_distance(), 1),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Move Rambabu briefly")
    parser.add_argument(
        "direction",
        choices=[
            "forward", "back", "left", "right", "stop",
            "back_left", "back_right",
        ],
        help="Direction of travel (left/right steer while driving forward)",
    )
    parser.add_argument(
        "duration",
        type=float,
        nargs="?",
        default=0.0,
        help="Seconds to drive (required for forward/back/left/right, max 9)",
    )
    args = parser.parse_args()

    # Validate duration for moving actions
    if args.direction != "stop":
        if args.duration <= 0:
            print({"status": "error",
                   "message": f"'{args.direction}' needs a duration in seconds"})
            sys.exit(2)
        if args.duration > MAX_DURATION:
            logger.warning(
                f"Duration {args.duration}s > cap {MAX_DURATION}s — clamping"
            )
            args.duration = MAX_DURATION

    # Reverse-family directions are blind (no rear sensor); skip sonar init.
    need_sonar = args.direction in ("forward", "left", "right")

    motor: MotorController | None = None
    ultra: Ultrasonic | None = None
    result: dict = {}
    try:
        motor, ultra = init_hardware(need_sonar=need_sonar)

        if args.direction == "stop":
            motor.stop()
            result = {"status": "ok", "action": "stop"}

        elif args.direction == "forward":
            assert ultra is not None
            result = drive_forward_safe(motor, ultra, args.duration)

        elif args.direction == "back":
            duration = min(args.duration, REVERSE_MAX_DURATION)
            motor.back(DRIVE_SPEED)
            time.sleep(duration)
            motor.stop()
            result = {
                "status": "ok",
                "direction": "back",
                "duration_s": round(duration, 2),
            }

        elif args.direction == "back_left":
            duration = min(args.duration, REVERSE_MAX_DURATION)
            motor.steer_left_hold()
            motor.back(DRIVE_SPEED)
            time.sleep(duration)
            motor.stop()
            motor.steer_center()
            # Note: during reverse, left steer = front swings RIGHT
            result = {
                "status": "ok",
                "direction": "back_left",
                "duration_s": round(duration, 2),
                "note": "front swung RIGHT, rear swung LEFT",
            }

        elif args.direction == "back_right":
            duration = min(args.duration, REVERSE_MAX_DURATION)
            motor.steer_right_hold()
            motor.back(DRIVE_SPEED)
            time.sleep(duration)
            motor.stop()
            motor.steer_center()
            # Note: during reverse, right steer = front swings LEFT
            result = {
                "status": "ok",
                "direction": "back_right",
                "duration_s": round(duration, 2),
                "note": "front swung LEFT, rear swung RIGHT",
            }

        elif args.direction == "left":
            assert ultra is not None
            motor.steer_left_hold()
            result = drive_forward_safe(motor, ultra, args.duration)
            motor.steer_center()

        elif args.direction == "right":
            assert ultra is not None
            motor.steer_right_hold()
            result = drive_forward_safe(motor, ultra, args.duration)
            motor.steer_center()

    except Exception as exc:
        logger.exception(f"Move failed: {exc}")
        result = {"status": "error", "message": str(exc)}
    finally:
        cleanup_hardware(motor, ultra)

    print(result)


if __name__ == "__main__":
    main()
