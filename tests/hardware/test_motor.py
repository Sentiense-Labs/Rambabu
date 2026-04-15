#!/usr/bin/env python3
"""Hardware test — Rear drive motor (forward/back) and steering motor (left/right).

Drive tests: GPIO HIGH/LOW at configurable speed and duration.
Steer tests: hold left / hold right / center (like steer_left_hold / steer_right_hold).

Usage:
    uv run python tests/hardware/test_motor.py                # full test
    uv run python tests/hardware/test_motor.py --drive-only   # forward/back only
    uv run python tests/hardware/test_motor.py --steer-only   # steering only
    uv run python tests/hardware/test_motor.py --speed 50     # custom speed
    uv run pytest tests/hardware/test_motor.py -v -s          # pytest mode
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
_pwm_steer_l = None
_pwm_steer_r = None


def _init_gpio() -> None:
    """Initialize GPIO and create PWM objects for all 4 motor pins."""
    global _pwm_fwd, _pwm_bwd, _pwm_steer_l, _pwm_steer_r

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    GPIO.setup(config.MOTOR_REAR_FORWARD, GPIO.OUT)
    GPIO.setup(config.MOTOR_REAR_BACKWARD, GPIO.OUT)
    GPIO.setup(config.MOTOR_STEER_LEFT, GPIO.OUT)
    GPIO.setup(config.MOTOR_STEER_RIGHT, GPIO.OUT)

    _pwm_fwd = GPIO.PWM(config.MOTOR_REAR_FORWARD, config.MOTOR_PWM_FREQ)
    _pwm_bwd = GPIO.PWM(config.MOTOR_REAR_BACKWARD, config.MOTOR_PWM_FREQ)
    _pwm_steer_l = GPIO.PWM(config.MOTOR_STEER_LEFT, config.MOTOR_PWM_FREQ)
    _pwm_steer_r = GPIO.PWM(config.MOTOR_STEER_RIGHT, config.MOTOR_PWM_FREQ)

    _pwm_fwd.start(0)
    _pwm_bwd.start(0)
    _pwm_steer_l.start(0)
    _pwm_steer_r.start(0)


def _stop_all() -> None:
    """Set all PWM duty to 0 and pull pins LOW."""
    for pwm in (_pwm_fwd, _pwm_bwd, _pwm_steer_l, _pwm_steer_r):
        if pwm:
            pwm.ChangeDutyCycle(0)
    GPIO.output(config.MOTOR_STEER_LEFT, GPIO.LOW)
    GPIO.output(config.MOTOR_STEER_RIGHT, GPIO.LOW)


def _cleanup_gpio() -> None:
    """Stop all PWMs then clean up GPIO — avoids the __del__ crash."""
    _stop_all()
    time.sleep(0.1)
    for pwm in (_pwm_fwd, _pwm_bwd, _pwm_steer_l, _pwm_steer_r):
        if pwm:
            pwm.stop()
    time.sleep(0.1)
    GPIO.cleanup()


# ---------------------------------------------------------------------------
# Drive: forward / back
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


def drive_speed_ramp(duration_per_step: float = 1.0) -> None:
    """Ramp forward: MIN → DEFAULT → MAX → stop."""
    _pwm_bwd.ChangeDutyCycle(0)
    for speed in (config.MIN_SPEED, config.DEFAULT_SPEED, config.MAX_SPEED):
        print(f"  RAMP → {speed}% ...")
        _pwm_fwd.ChangeDutyCycle(speed)
        time.sleep(duration_per_step)
    _pwm_fwd.ChangeDutyCycle(0)
    print(f"  RAMP done — stopped")


# ---------------------------------------------------------------------------
# Steering: left hold / right hold / center
# ---------------------------------------------------------------------------


def _steer_center() -> None:
    """Center steering with dead time."""
    _pwm_steer_l.ChangeDutyCycle(0)
    _pwm_steer_r.ChangeDutyCycle(0)
    GPIO.output(config.MOTOR_STEER_LEFT, GPIO.LOW)
    GPIO.output(config.MOTOR_STEER_RIGHT, GPIO.LOW)
    time.sleep(config.STEER_DEAD_TIME)


def steer_left_hold(duration: float = 1.0) -> None:
    """Hold steering left for duration, then center."""
    _steer_center()
    time.sleep(config.STEER_SETTLE_TIME)
    print(f"  STEER LEFT hold {duration}s ...")
    _pwm_steer_l.ChangeDutyCycle(0)
    _pwm_steer_r.ChangeDutyCycle(100)
    time.sleep(duration)
    _steer_center()
    print(f"  STEER LEFT done — centered")


def steer_right_hold(duration: float = 1.0) -> None:
    """Hold steering right for duration, then center."""
    _steer_center()
    time.sleep(config.STEER_SETTLE_TIME)
    print(f"  STEER RIGHT hold {duration}s ...")
    _pwm_steer_r.ChangeDutyCycle(0)
    _pwm_steer_l.ChangeDutyCycle(100)
    time.sleep(duration)
    _steer_center()
    print(f"  STEER RIGHT done — centered")


# ---------------------------------------------------------------------------
# Pytest tests
# ---------------------------------------------------------------------------


class TestDrive:
    """Rear motor forward and backward."""

    def setup_method(self) -> None:
        _init_gpio()

    def teardown_method(self) -> None:
        _cleanup_gpio()

    def test_forward(self) -> None:
        print(f"\n  Forward at {config.DEFAULT_SPEED}%")
        drive_forward(config.DEFAULT_SPEED, duration=1.5)

    def test_back(self) -> None:
        print(f"\n  Back at {config.DEFAULT_SPEED}%")
        drive_back(config.DEFAULT_SPEED, duration=1.5)

    def test_speed_ramp(self) -> None:
        print(
            f"\n  Ramp: {config.MIN_SPEED} → {config.DEFAULT_SPEED} → {config.MAX_SPEED}"
        )
        drive_speed_ramp(duration_per_step=1.0)


class TestSteering:
    """Steering left/right hold and cycle."""

    def setup_method(self) -> None:
        _init_gpio()

    def teardown_method(self) -> None:
        _cleanup_gpio()

    def test_steer_left(self) -> None:
        print("\n  Steer LEFT hold")
        steer_left_hold(duration=1.0)

    def test_steer_right(self) -> None:
        print("\n  Steer RIGHT hold")
        steer_right_hold(duration=1.0)

    def test_left_right_cycle(self) -> None:
        print("\n  LEFT → CENTER → RIGHT → CENTER")
        steer_left_hold(duration=0.8)
        time.sleep(0.3)
        steer_right_hold(duration=0.8)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Motor hardware test")
    parser.add_argument("--drive-only", action="store_true", help="Forward/back only")
    parser.add_argument("--steer-only", action="store_true", help="Steering only")
    parser.add_argument(
        "--speed",
        type=int,
        default=config.DEFAULT_SPEED,
        help=f"Drive speed 0-100 (default: {config.DEFAULT_SPEED})",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=1.5,
        help="Seconds per drive test (default: 1.5)",
    )
    args = parser.parse_args()

    do_drive = not args.steer_only
    do_steer = not args.drive_only

    print("=== Motor Hardware Test ===")
    print(f"  Rear Forward  → GPIO {config.MOTOR_REAR_FORWARD}")
    print(f"  Rear Backward → GPIO {config.MOTOR_REAR_BACKWARD}")
    print(f"  Steer Left    → GPIO {config.MOTOR_STEER_LEFT}")
    print(f"  Steer Right   → GPIO {config.MOTOR_STEER_RIGHT}")

    _init_gpio()

    try:
        if do_drive:
            print(f"\n{'='*40}")
            print(f"  DRIVE TEST (speed={args.speed}%)")
            print(f"{'='*40}")

            print("\n  1. Forward")
            drive_forward(args.speed, args.duration)
            time.sleep(0.5)

            print("\n  2. Back")
            drive_back(args.speed, args.duration)
            time.sleep(0.5)

            print("\n  3. Speed ramp (forward)")
            drive_speed_ramp(duration_per_step=1.0)
            time.sleep(0.5)

        if do_steer:
            print(f"\n{'='*40}")
            print(f"  STEERING TEST")
            print(f"{'='*40}")

            print("\n  1. Steer LEFT hold")
            steer_left_hold(duration=1.0)
            time.sleep(0.5)

            print("\n  2. Steer RIGHT hold")
            steer_right_hold(duration=1.0)
            time.sleep(0.5)

            print("\n  3. LEFT → RIGHT cycle")
            steer_left_hold(duration=0.8)
            time.sleep(0.3)
            steer_right_hold(duration=0.8)

    except KeyboardInterrupt:
        print("\n\n  Interrupted!")
    finally:
        _cleanup_gpio()
        print("\n[OK] Motors stopped, GPIO cleaned up.")
