#!/usr/bin/env python3
"""Hardware test — Forward and reverse movement of the car.

Tests rear drive motor forward/backward transitions, speed changes,
and stop behavior on real hardware.

Usage:
    uv run python tests/hardware/test_forward_reverse.py
    uv run python tests/hardware/test_forward_reverse.py --speed 50
    uv run python tests/hardware/test_forward_reverse.py --duration 2.0
    uv run pytest tests/hardware/test_forward_reverse.py -v -s
"""

import argparse
import time

import RPi.GPIO as GPIO

import config

# ---------------------------------------------------------------------------
# GPIO lifecycle
# ---------------------------------------------------------------------------

_pwm_fwd = None
_pwm_bwd = None


def _init_gpio() -> None:
    """Initialize GPIO and create PWM objects for rear motor pins."""
    global _pwm_fwd, _pwm_bwd

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(config.MOTOR_REAR_FORWARD, GPIO.OUT)
    GPIO.setup(config.MOTOR_REAR_BACKWARD, GPIO.OUT)

    _pwm_fwd = GPIO.PWM(config.MOTOR_REAR_FORWARD, config.MOTOR_PWM_FREQ)
    _pwm_bwd = GPIO.PWM(config.MOTOR_REAR_BACKWARD, config.MOTOR_PWM_FREQ)

    _pwm_fwd.start(0)
    _pwm_bwd.start(0)


def _stop_all() -> None:
    """Set both PWM duty cycles to 0."""
    for pwm in (_pwm_fwd, _pwm_bwd):
        if pwm:
            pwm.ChangeDutyCycle(0)


def _cleanup_gpio() -> None:
    """Stop PWMs then clean up GPIO."""
    _stop_all()
    time.sleep(0.1)
    for pwm in (_pwm_fwd, _pwm_bwd):
        if pwm:
            pwm.stop()
    time.sleep(0.1)
    GPIO.cleanup()


# ---------------------------------------------------------------------------
# Drive helpers
# ---------------------------------------------------------------------------


def drive_forward(speed: int = config.DEFAULT_SPEED, duration: float = 1.5) -> None:
    """Run rear motor forward at speed% for duration seconds."""
    duty = min(max(speed, 0), 100)
    print(f"  FORWARD at {duty}% for {duration}s ...")
    _pwm_bwd.ChangeDutyCycle(0)
    _pwm_fwd.ChangeDutyCycle(duty)
    time.sleep(duration)
    _pwm_fwd.ChangeDutyCycle(0)
    print(f"  FORWARD stopped")


def drive_back(speed: int = config.DEFAULT_SPEED, duration: float = 1.5) -> None:
    """Run rear motor backward at speed% for duration seconds."""
    duty = min(max(speed, 0), 100)
    print(f"  BACK at {duty}% for {duration}s ...")
    _pwm_fwd.ChangeDutyCycle(0)
    _pwm_bwd.ChangeDutyCycle(duty)
    time.sleep(duration)
    _pwm_bwd.ChangeDutyCycle(0)
    print(f"  BACK stopped")


# ---------------------------------------------------------------------------
# Pytest tests
# ---------------------------------------------------------------------------


class TestForward:
    """Rear motor forward movement."""

    def setup_method(self) -> None:
        _init_gpio()

    def teardown_method(self) -> None:
        _cleanup_gpio()

    def test_forward_default_speed(self) -> None:
        print(f"\n  Forward at default {config.DEFAULT_SPEED}%")
        drive_forward(config.DEFAULT_SPEED, duration=1.5)

    def test_forward_min_speed(self) -> None:
        print(f"\n  Forward at min {config.MIN_SPEED}%")
        drive_forward(config.MIN_SPEED, duration=1.5)

    def test_forward_max_speed(self) -> None:
        print(f"\n  Forward at max {config.MAX_SPEED}%")
        drive_forward(config.MAX_SPEED, duration=1.0)


class TestReverse:
    """Rear motor reverse movement."""

    def setup_method(self) -> None:
        _init_gpio()

    def teardown_method(self) -> None:
        _cleanup_gpio()

    def test_reverse_default_speed(self) -> None:
        print(f"\n  Reverse at default {config.DEFAULT_SPEED}%")
        drive_back(config.DEFAULT_SPEED, duration=1.5)

    def test_reverse_min_speed(self) -> None:
        print(f"\n  Reverse at min {config.MIN_SPEED}%")
        drive_back(config.MIN_SPEED, duration=1.5)

    def test_reverse_max_speed(self) -> None:
        print(f"\n  Reverse at max {config.MAX_SPEED}%")
        drive_back(config.MAX_SPEED, duration=1.0)


class TestForwardReverseTransitions:
    """Switching between forward, reverse, and stop."""

    def setup_method(self) -> None:
        _init_gpio()

    def teardown_method(self) -> None:
        _cleanup_gpio()

    def test_forward_then_reverse(self) -> None:
        print("\n  Forward → pause → Reverse")
        drive_forward(config.DEFAULT_SPEED, duration=1.5)
        time.sleep(0.5)
        drive_back(config.DEFAULT_SPEED, duration=1.5)

    def test_reverse_then_forward(self) -> None:
        print("\n  Reverse → pause → Forward")
        drive_back(config.DEFAULT_SPEED, duration=1.5)
        time.sleep(0.5)
        drive_forward(config.DEFAULT_SPEED, duration=1.5)

    def test_forward_stop_forward(self) -> None:
        print("\n  Forward → stop → Forward")
        drive_forward(config.DEFAULT_SPEED, duration=1.0)
        _stop_all()
        time.sleep(0.5)
        drive_forward(config.DEFAULT_SPEED, duration=1.0)

    def test_speed_change_forward(self) -> None:
        print(
            f"\n  Speed ramp: {config.MIN_SPEED}% → {config.DEFAULT_SPEED}% → {config.MAX_SPEED}%"
        )
        _pwm_bwd.ChangeDutyCycle(0)
        for speed in (config.MIN_SPEED, config.DEFAULT_SPEED, config.MAX_SPEED):
            print(f"  → {speed}%")
            _pwm_fwd.ChangeDutyCycle(speed)
            time.sleep(1.0)
        _pwm_fwd.ChangeDutyCycle(0)
        print("  Ramp done — stopped")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Forward/reverse hardware test")
    parser.add_argument(
        "--speed",
        type=int,
        default=config.DEFAULT_SPEED,
        help=f"Drive speed 0-100 (default: {config.DEFAULT_SPEED})",
    )
    parser.add_argument(
        "--duration", type=float, default=1.5, help="Seconds per test (default: 1.5)"
    )
    args = parser.parse_args()

    print("=== Forward / Reverse Hardware Test ===")
    print(f"  Rear Forward  → GPIO {config.MOTOR_REAR_FORWARD}")
    print(f"  Rear Backward → GPIO {config.MOTOR_REAR_BACKWARD}")
    print(f"  Speed: {args.speed}%  Duration: {args.duration}s")

    _init_gpio()

    try:
        print(f"\n{'='*40}")
        print(f"  1. Forward at {args.speed}%")
        print(f"{'='*40}")
        drive_forward(args.speed, args.duration)
        time.sleep(0.5)

        print(f"\n{'='*40}")
        print(f"  2. Reverse at {args.speed}%")
        print(f"{'='*40}")
        drive_back(args.speed, args.duration)
        time.sleep(0.5)

        print(f"\n{'='*40}")
        print(f"  3. Forward → Reverse transition")
        print(f"{'='*40}")
        drive_forward(args.speed, args.duration)
        time.sleep(0.3)
        drive_back(args.speed, args.duration)
        time.sleep(0.5)

        print(f"\n{'='*40}")
        print(f"  4. Speed ramp (forward)")
        print(f"{'='*40}")
        _pwm_bwd.ChangeDutyCycle(0)
        for speed in (config.MIN_SPEED, config.DEFAULT_SPEED, config.MAX_SPEED):
            print(f"  → {speed}%")
            _pwm_fwd.ChangeDutyCycle(speed)
            time.sleep(1.0)
        _pwm_fwd.ChangeDutyCycle(0)
        print("  Ramp done — stopped")

    except KeyboardInterrupt:
        print("\n\n  Interrupted!")
    finally:
        _cleanup_gpio()
        print("\n[OK] Motors stopped, GPIO cleaned up.")
