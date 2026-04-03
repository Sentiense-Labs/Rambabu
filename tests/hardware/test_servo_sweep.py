#!/usr/bin/env python3
"""Simulate joystick pan — move-and-kill per degree for jitter-free smooth sweep.

Each 1° step: PWM on for 40ms (2 cycles at 50Hz), then killed.
Servo moves in micro-steps that look smooth, but never jitters because
PWM is off between steps.
"""

import RPi.GPIO as GPIO
from time import sleep

PAN_PIN = 12
PWM_FREQ = 50

PAN_MIN = 30
PAN_MAX = 140
PAN_CENTER = 85

# Timing per 1° step
PULSE_SEC = 0.04   # 40ms = 2 PWM cycles — enough for servo to register 1°
DEAD_SEC = 0.01    # 10ms dead time between steps (PWM off)


def angle_to_duty(angle: int) -> float:
    return 2.5 + (angle / 180) * 10


def joystick_sweep(pwm: GPIO.PWM, start: int, end: int) -> None:
    """Move-and-kill per degree — smooth movement, zero jitter."""
    step = 1 if end > start else -1
    angle = start

    while angle != end:
        angle += step
        pwm.ChangeDutyCycle(angle_to_duty(angle))
        sleep(PULSE_SEC)
        pwm.ChangeDutyCycle(0)
        sleep(DEAD_SEC)

    print(f"  Stopped at {angle}° — holding (no PWM)")


def main() -> None:
    print("Joystick Pan — Move-and-Kill Per Degree")
    print("=" * 50)
    speed = 1.0 / (PULSE_SEC + DEAD_SEC)
    print(f"  Speed: ~{speed:.0f}°/sec")
    print(f"  PWM on for {PULSE_SEC*1000:.0f}ms per step, then killed")
    print("=" * 50)

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(PAN_PIN, GPIO.OUT)

    pwm = GPIO.PWM(PAN_PIN, PWM_FREQ)
    pwm.start(0)

    try:
        print(f"\nCentering to {PAN_CENTER}°...")
        pwm.ChangeDutyCycle(angle_to_duty(PAN_CENTER))
        sleep(0.3)
        pwm.ChangeDutyCycle(0)
        sleep(1)

        print(f"\n[Joystick LEFT] {PAN_CENTER}° → {PAN_MIN}°...")
        joystick_sweep(pwm, PAN_CENTER, PAN_MIN)
        sleep(2)

        print(f"\n[Joystick RIGHT] {PAN_MIN}° → {PAN_MAX}°...")
        joystick_sweep(pwm, PAN_MIN, PAN_MAX)
        sleep(2)

        print(f"\n[Joystick LEFT] {PAN_MAX}° → {PAN_CENTER}°...")
        joystick_sweep(pwm, PAN_MAX, PAN_CENTER)
        sleep(2)

        print("\nDone — was the sweep smooth and holds jitter-free?")

    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        pwm.ChangeDutyCycle(0)
        pwm.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
