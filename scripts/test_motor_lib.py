#!/usr/bin/env python3
"""
Motor library diagnostic — runs MotorController directly (no Flask/MQTT).

Tests each movement and prints exactly what the library returns.
Also reads the ultrasonic distance to check if obstacle latch is the cause.

Run with: python3 scripts/test_motor_lib.py
"""

import sys
import time
import RPi.GPIO as GPIO
from lib.motor import MotorController
from lib.ultrasonic import Ultrasonic
import config


def banner(text: str):
    print(f"\n{'─' * 48}")
    print(f"  {text}")
    print(f"{'─' * 48}")


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    # ── 1. Check ultrasonic distance first ───────────────────────────────
    banner("Step 1: Ultrasonic sensor reading")
    try:
        ultrasonic = Ultrasonic()
        time.sleep(0.5)
        distance = ultrasonic.get_distance()
        print(f"  Distance: {distance:.1f} cm")
        print(f"  Obstacle threshold (stops forward): {config.OBSTACLE_DETECTION_DISTANCE} cm")
        print(f"  Clear threshold (releases latch): {config.OBSTACLE_CLEAR_DISTANCE} cm")

        if distance <= config.OBSTACLE_DETECTION_DISTANCE:
            print(f"\n  ⚠️  OBSTACLE WITHIN {config.OBSTACLE_DETECTION_DISTANCE}cm — front() will be BLOCKED")
            print("  Move the car away from obstacles, or call back() first to clear the latch.")
        else:
            print(f"\n  ✅ Path is clear ({distance:.1f}cm > {config.OBSTACLE_DETECTION_DISTANCE}cm)")

        obstacle_check = lambda: ultrasonic.get_distance() <= config.OBSTACLE_DETECTION_DISTANCE
        clear_check = lambda: ultrasonic.get_distance() > config.OBSTACLE_CLEAR_DISTANCE
    except Exception as e:
        print(f"  ⚠️  Ultrasonic init failed: {e}")
        print("  Continuing without obstacle check (front() will not be blocked)")
        ultrasonic = None
        obstacle_check = None
        clear_check = None

    # ── 2. Init motor controller ──────────────────────────────────────────
    banner("Step 2: Motor controller init")
    try:
        motor = MotorController()
        if obstacle_check:
            motor.set_obstacle_check(obstacle_check, clear_check)
        print("  ✅ Motor controller initialized")
    except Exception as e:
        print(f"  ❌ Motor init failed: {e}")
        GPIO.cleanup()
        sys.exit(1)

    # ── 3. Test each command ──────────────────────────────────────────────
    banner("Step 3: Testing each command")

    commands = [
        ("BACK (clears latch first)",  lambda: motor.back(70)),
        ("STOP",                        motor.stop),
        ("FRONT",                       lambda: motor.front(70)),
        ("STOP",                        motor.stop),
        ("LEFT (pulse)",                motor.left),
        ("RIGHT (pulse)",               motor.right),
        ("STEER_LEFT_HOLD",             motor.steer_left_hold),
        ("STEER_CENTER",                motor.steer_center),
        ("STEER_RIGHT_HOLD",            motor.steer_right_hold),
        ("STEER_CENTER",                motor.steer_center),
        ("STOP",                        motor.stop),
    ]

    for label, fn in commands:
        result = fn()
        icon = "✅" if result.get("status") in ("ok", "stopped") else "❌"
        print(f"  {icon} {label:30s} → {result}")
        time.sleep(0.8)

    # ── 4. Summary ────────────────────────────────────────────────────────
    banner("Done")
    print("  If FRONT returned an error above, the obstacle latch is the issue.")
    print("  If FRONT returned ok but nothing moved, it's a PWM/wiring issue.")

    motor.stop()
    if ultrasonic:
        ultrasonic.stop()
    GPIO.cleanup()


if __name__ == "__main__":
    main()
