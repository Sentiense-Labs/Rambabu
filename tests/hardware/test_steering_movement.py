#!/usr/bin/env python3
"""Hardware test: left and right steering movement for 15 seconds.

Requires Pi with L9110S motor driver and steering motor wired up.
Run with: uv run pytest tests/hardware/test_steering_movement.py -v -s
"""

import time
import sys
import RPi.GPIO as GPIO
from config import (
    MOTOR_STEER_LEFT,
    MOTOR_STEER_RIGHT,
    STEER_PULSE_DURATION,
)

TEST_DURATION_SECONDS = 15
PAUSE_BETWEEN_TURNS = 0.5  # seconds between left/right alternations


def setup_gpio():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(MOTOR_STEER_LEFT, GPIO.OUT)
    GPIO.setup(MOTOR_STEER_RIGHT, GPIO.OUT)
    GPIO.output(MOTOR_STEER_LEFT, GPIO.LOW)
    GPIO.output(MOTOR_STEER_RIGHT, GPIO.LOW)


def steer_left():
    GPIO.output(MOTOR_STEER_LEFT, GPIO.LOW)
    GPIO.output(MOTOR_STEER_RIGHT, GPIO.HIGH)
    time.sleep(STEER_PULSE_DURATION)
    GPIO.output(MOTOR_STEER_RIGHT, GPIO.LOW)


def steer_right():
    GPIO.output(MOTOR_STEER_LEFT, GPIO.HIGH)
    GPIO.output(MOTOR_STEER_RIGHT, GPIO.LOW)
    time.sleep(STEER_PULSE_DURATION)
    GPIO.output(MOTOR_STEER_LEFT, GPIO.LOW)


def steer_center():
    GPIO.output(MOTOR_STEER_LEFT, GPIO.LOW)
    GPIO.output(MOTOR_STEER_RIGHT, GPIO.LOW)


def cleanup():
    try:
        steer_center()
    except Exception:
        pass
    try:
        GPIO.cleanup()
    except Exception:
        pass


def test_left_right_steering_15s():
    """Alternate left/right steering for 15 seconds, then verify center stop."""
    print("\n" + "=" * 50)
    print("STEERING MOVEMENT TEST — 15 seconds")
    print("=" * 50)
    print(f"GPIO {MOTOR_STEER_LEFT} → Steer Left")
    print(f"GPIO {MOTOR_STEER_RIGHT} → Steer Right")
    print(f"Pulse duration: {STEER_PULSE_DURATION}s")
    print("WARNING: Ensure car is on blocks before running!")
    print("=" * 50)

    setup_gpio()

    start_time = time.time()
    cycle = 0

    try:
        while (time.time() - start_time) < TEST_DURATION_SECONDS:
            elapsed = time.time() - start_time
            remaining = TEST_DURATION_SECONDS - elapsed

            if remaining < STEER_PULSE_DURATION + PAUSE_BETWEEN_TURNS:
                break

            cycle += 1
            direction = "LEFT" if cycle % 2 != 0 else "RIGHT"
            print(f"[{elapsed:.1f}s] Cycle {cycle}: Steering {direction}")

            if direction == "LEFT":
                steer_left()
            else:
                steer_right()

            time.sleep(PAUSE_BETWEEN_TURNS)

        elapsed = time.time() - start_time
        print(f"\n[{elapsed:.1f}s] Test complete — centering steering")
        steer_center()

        print(f"Completed {cycle} steering cycles in {elapsed:.1f}s")
        assert cycle > 0, "No steering cycles completed"
        assert elapsed >= min(
            TEST_DURATION_SECONDS - 1,
            cycle * (STEER_PULSE_DURATION + PAUSE_BETWEEN_TURNS),
        )

    finally:
        cleanup()


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
