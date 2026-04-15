#!/usr/bin/env python3
"""Hardware test: left/right steering at tuned profile (100% x 250ms).

Run with: uv run tests/hardware/test_steer_left_right.py
"""

import time
import sys
import RPi.GPIO as GPIO
from config import (
    MOTOR_STEER_LEFT,
    MOTOR_STEER_RIGHT,
)

TEST_DURATION_SECONDS = 15
PAUSE_BETWEEN_TURNS = 0.3

STEER_PWM_FREQ = 1000
STEER_DUTY = 100  # percent
STEER_DURATION = 0.25  # seconds
DEAD_TIME = 0.05
CENTER_SETTLE_TIME = 0.10


def setup_gpio() -> tuple[GPIO.PWM, GPIO.PWM]:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(MOTOR_STEER_LEFT, GPIO.OUT)
    GPIO.setup(MOTOR_STEER_RIGHT, GPIO.OUT)
    GPIO.output(MOTOR_STEER_LEFT, GPIO.LOW)
    GPIO.output(MOTOR_STEER_RIGHT, GPIO.LOW)
    pwm_left = GPIO.PWM(MOTOR_STEER_LEFT, STEER_PWM_FREQ)
    pwm_right = GPIO.PWM(MOTOR_STEER_RIGHT, STEER_PWM_FREQ)
    pwm_left.start(0)
    pwm_right.start(0)
    return pwm_left, pwm_right


def center(pwm_left: GPIO.PWM, pwm_right: GPIO.PWM) -> None:
    pwm_left.ChangeDutyCycle(0)
    pwm_right.ChangeDutyCycle(0)
    GPIO.output(MOTOR_STEER_LEFT, GPIO.LOW)
    GPIO.output(MOTOR_STEER_RIGHT, GPIO.LOW)
    time.sleep(DEAD_TIME)


def steer_left(pwm_left: GPIO.PWM, pwm_right: GPIO.PWM) -> None:
    center(pwm_left, pwm_right)
    time.sleep(CENTER_SETTLE_TIME)
    pwm_left.ChangeDutyCycle(0)
    pwm_right.ChangeDutyCycle(STEER_DUTY)
    time.sleep(STEER_DURATION)
    center(pwm_left, pwm_right)


def steer_right(pwm_left: GPIO.PWM, pwm_right: GPIO.PWM) -> None:
    center(pwm_left, pwm_right)
    time.sleep(CENTER_SETTLE_TIME)
    pwm_right.ChangeDutyCycle(0)
    pwm_left.ChangeDutyCycle(STEER_DUTY)
    time.sleep(STEER_DURATION)
    center(pwm_left, pwm_right)


def cleanup(
    pwm_left: GPIO.PWM | None = None, pwm_right: GPIO.PWM | None = None
) -> None:
    try:
        if pwm_left and pwm_right:
            center(pwm_left, pwm_right)
            pwm_left.stop()
            pwm_right.stop()
    except Exception:
        pass
    try:
        GPIO.cleanup()
    except Exception:
        pass


def test_left_right_steering_15s() -> None:
    """Alternate left/right steering at 100% x 250ms for 15 seconds."""
    print("\n" + "=" * 50)
    print("STEERING TEST — 100% x 250ms")
    print("=" * 50)
    print(f"GPIO {MOTOR_STEER_LEFT} → Steer Left")
    print(f"GPIO {MOTOR_STEER_RIGHT} → Steer Right")
    print(f"PWM frequency : {STEER_PWM_FREQ}Hz")
    print(f"Duty cycle    : {STEER_DUTY}%")
    print(f"Steer duration: {STEER_DURATION * 1000:.0f}ms")
    print(f"Dead time     : {DEAD_TIME * 1000:.0f}ms")
    print(f"Settle time   : {CENTER_SETTLE_TIME * 1000:.0f}ms")
    print("=" * 50)

    pwm_left, pwm_right = setup_gpio()
    start_time = time.time()
    cycle = 0

    try:
        while (time.time() - start_time) < TEST_DURATION_SECONDS:
            elapsed = time.time() - start_time
            remaining = TEST_DURATION_SECONDS - elapsed

            if remaining < STEER_DURATION + PAUSE_BETWEEN_TURNS:
                break

            cycle += 1
            direction = "LEFT" if cycle % 2 != 0 else "RIGHT"
            print(f"[{elapsed:.1f}s] Cycle {cycle}: Steering {direction}")

            if direction == "LEFT":
                steer_left(pwm_left, pwm_right)
            else:
                steer_right(pwm_left, pwm_right)

            time.sleep(PAUSE_BETWEEN_TURNS)

        elapsed = time.time() - start_time
        print(f"\n[{elapsed:.1f}s] Test complete — centering steering")
        center(pwm_left, pwm_right)
        print(f"Completed {cycle} steering cycles in {elapsed:.1f}s")
        assert cycle > 0, "No steering cycles completed"

    finally:
        cleanup(pwm_left, pwm_right)


if __name__ == "__main__":
    try:
        test_left_right_steering_15s()
        print("\n✓ Steering test passed")
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        cleanup()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        cleanup()
        sys.exit(1)
