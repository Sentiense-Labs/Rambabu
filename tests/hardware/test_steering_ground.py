#!/usr/bin/env python3
"""Steering test with kick-start to break static friction.

Rapid PWM bursts break tire grip, then holds full power.
"""

import RPi.GPIO as GPIO
import time
from config import MOTOR_STEER_LEFT, MOTOR_STEER_RIGHT, MOTOR_PWM_FREQ

KICK_CYCLES = 5         # Number of on/off bursts
KICK_ON_SEC = 0.05      # 50ms full power
KICK_OFF_SEC = 0.02     # 20ms off — lets motor bounce
HOLD_SEC = 1.5          # Hold after kick


def kick_start(pwm_active: GPIO.PWM, pwm_idle: GPIO.PWM) -> None:
    """Rapid bursts to break static friction, then hold."""
    pwm_idle.ChangeDutyCycle(0)

    # Kick: rapid on/off pulses create vibration
    for _ in range(KICK_CYCLES):
        pwm_active.ChangeDutyCycle(100)
        time.sleep(KICK_ON_SEC)
        pwm_active.ChangeDutyCycle(0)
        time.sleep(KICK_OFF_SEC)

    # Hold full power
    pwm_active.ChangeDutyCycle(100)
    time.sleep(HOLD_SEC)
    pwm_active.ChangeDutyCycle(0)


def main() -> None:
    print("Steering Ground Test (with kick-start)")
    print("=" * 50)
    print(f"Steer Left:  GPIO {MOTOR_STEER_LEFT}")
    print(f"Steer Right: GPIO {MOTOR_STEER_RIGHT}")
    print("=" * 50)

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(MOTOR_STEER_LEFT, GPIO.OUT)
    GPIO.setup(MOTOR_STEER_RIGHT, GPIO.OUT)

    pwm_left = GPIO.PWM(MOTOR_STEER_LEFT, MOTOR_PWM_FREQ)
    pwm_right = GPIO.PWM(MOTOR_STEER_RIGHT, MOTOR_PWM_FREQ)
    pwm_left.start(0)
    pwm_right.start(0)

    try:
        print("\n[LEFT] Kick-start + hold...")
        kick_start(pwm_right, pwm_left)
        print("  Done — did wheels turn left?")
        time.sleep(1)

        print("\n[RIGHT] Kick-start + hold...")
        kick_start(pwm_left, pwm_right)
        print("  Done — did wheels turn right?")
        time.sleep(1)

        print("\nDone.")

    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        pwm_left.stop()
        pwm_right.stop()
        GPIO.cleanup()


if __name__ == "__main__":
    main()
