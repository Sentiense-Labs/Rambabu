#!/usr/bin/env python3
"""Sweep pan/tilt servos through their full range in 5-degree steps.

Shows each angle, waits for Enter to advance. Helps find the exact
range where the camera sits properly on the mount.

Run on Pi:  python3 scripts/test_servo_range.py
"""

import sys
from time import sleep

import RPi.GPIO as GPIO

# ── Config (from config/__init__.py) ─────────────────────────────────────
PAN_PIN = 12
TILT_PIN = 13
PWM_FREQ = 50
MOVE_DELAY = 0.3

# Test range — clamped to safe mechanical limits
PAN_TEST_MIN = 30
PAN_TEST_MAX = 140
TILT_TEST_MIN = 35
TILT_TEST_MAX = 105
STEP = 5


def angle_to_duty(angle: int) -> float:
    """Convert angle (0-180) to duty cycle (2.5-12.5%)."""
    return 2.5 + (angle / 180) * 10


def move_servo(pwm, angle: int, name: str) -> None:
    """Move servo to angle using move-and-kill."""
    duty = angle_to_duty(angle)
    pwm.ChangeDutyCycle(duty)
    sleep(MOVE_DELAY)
    pwm.ChangeDutyCycle(0)


def sweep_servo(pwm, name: str, test_min: int, test_max: int) -> None:
    """Sweep a servo from min to max in STEP increments."""
    print(f"\n{'='*60}")
    print(f"  {name} SERVO SWEEP")
    print(f"  Range: {test_min} -> {test_max} (step={STEP})")
    print(f"  Press Enter to advance, 'q' to skip, 's' to set limits")
    print(f"{'='*60}\n")

    good_min = None
    good_max = None

    angles = list(range(test_min, test_max + 1, STEP))

    for angle in angles:
        move_servo(pwm, angle, name)
        prompt = f"  {name:>4} = {angle:3d}°  |  OK? [Enter=next / g=good / b=bad / q=quit]: "

        try:
            resp = input(prompt).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return good_min, good_max

        if resp == "q":
            break
        elif resp == "g":
            if good_min is None:
                good_min = angle
            good_max = angle
        elif resp == "b":
            pass  # just skip
        else:
            # plain Enter — assume good
            if good_min is None:
                good_min = angle
            good_max = angle

    return good_min, good_max


def main() -> None:
    print("=" * 60)
    print("  SERVO RANGE FINDER")
    print("  Sweeps pan & tilt in 5° steps through 0-180")
    print("  Mark angles as good (g/Enter) or bad (b)")
    print("=" * 60)

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(PAN_PIN, GPIO.OUT)
    GPIO.setup(TILT_PIN, GPIO.OUT)

    pan_pwm = GPIO.PWM(PAN_PIN, PWM_FREQ)
    tilt_pwm = GPIO.PWM(TILT_PIN, PWM_FREQ)
    pan_pwm.start(0)
    tilt_pwm.start(0)

    # Center both first
    print("\nCentering both servos to 90°...")
    move_servo(pan_pwm, 90, "Pan")
    move_servo(tilt_pwm, 90, "Tilt")
    sleep(0.5)

    try:
        # Ask which servo to test
        print("\nWhich servo to test?")
        print("  1 = Pan only")
        print("  2 = Tilt only")
        print("  3 = Both (pan first, then tilt)")
        choice = input("\nChoice [1/2/3]: ").strip()

        pan_min, pan_max = None, None
        tilt_min, tilt_max = None, None

        if choice in ("1", "3"):
            # Center tilt while testing pan
            move_servo(tilt_pwm, 90, "Tilt")
            pan_min, pan_max = sweep_servo(pan_pwm, "Pan", PAN_TEST_MIN, PAN_TEST_MAX)

        if choice in ("2", "3"):
            # Center pan while testing tilt
            move_servo(pan_pwm, 90, "Pan")
            tilt_min, tilt_max = sweep_servo(tilt_pwm, "Tilt", TILT_TEST_MIN, TILT_TEST_MAX)

        # Summary
        print(f"\n{'='*60}")
        print("  RESULTS — copy these to config/__init__.py")
        print(f"{'='*60}")

        if pan_min is not None:
            pan_center = (pan_min + pan_max) // 2
            print(f"\n  PAN_MIN  = {pan_min}")
            print(f"  PAN_CENTER = {pan_center}")
            print(f"  PAN_MAX  = {pan_max}")
        else:
            print("\n  Pan: not tested")

        if tilt_min is not None:
            tilt_center = (tilt_min + tilt_max) // 2
            print(f"\n  TILT_MIN = {tilt_min}")
            print(f"  TILT_CENTER = {tilt_center}")
            print(f"  TILT_MAX = {tilt_max}")
        else:
            print("\n  Tilt: not tested")

        # Return to center
        print("\nReturning to center (90/90)...")
        move_servo(pan_pwm, 90, "Pan")
        move_servo(tilt_pwm, 90, "Tilt")

    except KeyboardInterrupt:
        print("\n\nAborted.")
    finally:
        pan_pwm.stop()
        tilt_pwm.stop()
        GPIO.cleanup()
        print("GPIO cleaned up.\n")


if __name__ == "__main__":
    main()
