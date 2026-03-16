#!/usr/bin/env python3
"""Find optimal PWM kill delay for move-and-kill method."""

import sys
import time

import RPi.GPIO as GPIO

import config
from lib.pan_tilt import PanTilt
from utils.logger import log_info

DELAYS_TO_TEST = [0.2, 0.3, 0.4, 0.5, 0.6]


def prompt_yes_no(message: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    response = input(message + suffix).strip().lower()
    if not response:
        return default
    return response in {"y", "yes"}


def test_delay(pan_tilt: PanTilt, delay: float) -> bool:
    print(f"\n--- Testing delay: {delay}s ---")

    # Temporarily update delay
    original_delay = config.SERVO_MOVE_DELAY
    config.SERVO_MOVE_DELAY = delay

    try:
        # Move from 90 to 120
        print("Moving pan: 90° → 120°")
        pan_tilt.pan_to(120)

        reached = prompt_yes_no(
            "Did servo reach 120° fully and smoothly?",
            default=True,
        )
        if not reached:
            return False

        # Move back to 90
        print("Moving pan: 120° → 90°")
        pan_tilt.pan_to(90)

        reached = prompt_yes_no(
            "Did servo reach 90° fully and smoothly?",
            default=True,
        )
        if not reached:
            return False

        # Check for jitter after stop
        jitter = prompt_yes_no(
            "Is servo completely still (no jitter) after movement?",
            default=True,
        )
        if not jitter:
            print(f"Delay {delay}s causes jitter")
            return False

        print(f"Delay {delay}s works well")
        return True
    finally:
        config.SERVO_MOVE_DELAY = original_delay


def main() -> int:
    pan_tilt = None
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    try:
        pan_tilt = PanTilt()
        pan_tilt.set_as_current_center()
        print("Finding optimal PWM kill delay for move-and-kill method")

        working_delays = []
        for delay in DELAYS_TO_TEST:
            if test_delay(pan_tilt, delay):
                working_delays.append(delay)

        if not working_delays:
            log_error("No delays worked - check servo power and connections")
            return 1

        optimal_delay = min(working_delays)
        print(f"\n=== Results ===")
        print(f"Working delays: {working_delays}")
        print(f"Optimal delay: {optimal_delay}s (minimum that works)")
        print(f"\nUpdate config/__init__.py:")
        print(f"SERVO_MOVE_DELAY: Final[float] = {optimal_delay}")
        return 0
    except KeyboardInterrupt:
        log_info("Timing calibration interrupted by user")
        return 130
    finally:
        if pan_tilt is not None:
            try:
                pan_tilt.center()
                time.sleep(0.5)
                pan_tilt.cleanup()
            except Exception:
                pass
        GPIO.cleanup()


if __name__ == "__main__":
    sys.exit(main())
