#!/usr/bin/env python3
"""
Direct invocation of the three_point_turn maneuver — no Gemini, no MQTT.

Initializes the bare hardware (motor + ultrasonic + sonar guard + movement
manager), calls maneuvers.three_point_turn(preferred_side="right"), prints
the result, and cleans up.

Usage (aicar service must be stopped first so GPIO is free):
    sudo systemctl stop aicar
    uv run python tests/hardware/test_uturn.py [--side left|right]
    sudo systemctl start aicar
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import RPi.GPIO as GPIO

from brain.hardware_tools import HardwareContext
from brain.maneuvers import three_point_turn
from brain.movement_manager import MovementManager
from brain.sonar_guard import SonarGuard
from lib.motor import MotorController
from lib.ultrasonic import Ultrasonic


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a single three_point_turn")
    parser.add_argument(
        "--side",
        choices=["left", "right"],
        default="right",
        help="Which way to arc on the first leg (default: right)",
    )
    args = parser.parse_args()

    motor = None
    ultra = None
    sonar = None
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        print("[init] motor...")
        motor = MotorController()
        print("[init] ultrasonic...")
        ultra = Ultrasonic()
        ultra.wait_for_reading(timeout=2.0)
        print(f"[init] initial distance: {ultra.get_distance():.1f} cm")

        print("[init] sonar guard...")
        sonar = SonarGuard(ultrasonic=ultra, motor=motor)
        sonar.start()
        # Let the guard fill its window so the safety distance is meaningful.
        time.sleep(1.0)
        print(
            f"[init] guard zone={sonar.get_zone()} "
            f"display={sonar.get_distance():.1f}cm "
            f"safety={sonar.get_safety_distance():.1f}cm"
        )

        print("[init] movement manager...")
        mm = MovementManager(motor=motor, sonar_guard=sonar)
        hw = HardwareContext(
            motor=motor,
            ultrasonic=ultra,
            sonar_guard=sonar,
            movement_manager=mm,
        )

        print(f"\n=== three_point_turn(preferred_side='{args.side}') ===\n")
        result = three_point_turn(hw, preferred_side=args.side)

        print("\n=== result ===")
        for k, v in result.items():
            if k == "steps":
                print(f"  steps:")
                for step in v:
                    print(f"    {step}")
            else:
                print(f"  {k}: {v}")

        print(
            f"\n[final] guard zone={sonar.get_zone()} "
            f"safety={sonar.get_safety_distance():.1f}cm"
        )
        return 0 if result.get("status") in {"ok", "partial"} else 1

    finally:
        try:
            if sonar is not None:
                sonar.stop()
        except Exception as exc:
            print(f"[cleanup] sonar stop: {exc}")
        try:
            if motor is not None:
                motor.stop()
                motor.cleanup()
        except Exception as exc:
            print(f"[cleanup] motor: {exc}")
        try:
            if ultra is not None:
                ultra.cleanup()
        except Exception as exc:
            print(f"[cleanup] ultra: {exc}")
        try:
            GPIO.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
