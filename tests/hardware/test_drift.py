#!/usr/bin/env python3
"""
Hardware drift test for Ramu.

Usage:
    uv run python tests/hardware/test_drift.py left
    uv run python tests/hardware/test_drift.py right
    uv run python tests/hardware/test_drift.py figure8

Tuning knobs (edit constants below):
    BUILD_TIME_S   — approach duration at full speed (more = more momentum)
    OVERLAP_S      — powered arc before cut (more = sharper rear kick)
    COAST_S        — drift coast duration (more = longer slide)
    ENTRY_SPEED    — motor duty 0-100 (100 = max)
"""

import sys
import time

from dotenv import load_dotenv

load_dotenv()

import RPi.GPIO as GPIO  # noqa: E402

from lib.motor import MotorController  # noqa: E402

# ── Tuning parameters ─────────────────────────────────────────────────────────
ENTRY_SPEED: int = 100       # duty cycle — max speed for more slide
BUILD_TIME_S: float = 2.0    # straight approach to build momentum
OVERLAP_S: float = 0.2       # powered arc before cut — kicks rear out
COAST_S: float = 0.7         # coast after cut = drift slide
SETTLE_S: float = 0.5        # pause between consecutive drifts
# ─────────────────────────────────────────────────────────────────────────────


def setup() -> MotorController:
    GPIO.setmode(GPIO.BCM)
    motor = MotorController()
    motor.stop()
    motor.steer_center()
    return motor


def _drift(motor: MotorController, direction: str) -> None:
    steer = motor.steer_left_hold if direction == "left" else motor.steer_right_hold
    print(f"  approach {BUILD_TIME_S}s at {ENTRY_SPEED}% → steer {direction} "
          f"({OVERLAP_S}s overlap) → cut → coast {COAST_S}s")

    motor.steer_center()
    motor.front(ENTRY_SPEED)
    time.sleep(BUILD_TIME_S)

    steer()               # lock steering while still powered
    time.sleep(OVERLAP_S) # powered arc kicks rear out
    motor.stop()          # cut power → rear slides
    time.sleep(COAST_S)   # drift coast


def drift_single(motor: MotorController, direction: str) -> None:
    print(f"\n→ drift {direction}")
    _drift(motor, direction)
    motor.steer_center()
    print("  done")


def drift_figure8(motor: MotorController) -> None:
    print("\n→ figure-8 drift")
    _drift(motor, "left")
    time.sleep(SETTLE_S)
    motor.steer_center()

    _drift(motor, "right")
    time.sleep(SETTLE_S)
    motor.steer_center()
    print("  done")


def main() -> None:
    args = sys.argv[1:]
    mode = args[0].lower() if args else "left"

    if mode not in ("left", "right", "figure8"):
        print("Usage: test_drift.py [left|right|figure8]")
        sys.exit(1)

    motor = setup()

    try:
        if mode == "figure8":
            drift_figure8(motor)
        else:
            drift_single(motor, mode)
    finally:
        motor.stop()
        motor.steer_center()
        GPIO.cleanup()
        print("GPIO cleaned up.")


if __name__ == "__main__":
    main()
