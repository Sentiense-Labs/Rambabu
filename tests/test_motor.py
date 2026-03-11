#!/usr/bin/env python3
"""Test L9110S motor driver with proper cleanup."""

import RPi.GPIO as GPIO
import time
import sys
from config import (
    MOTOR_REAR_FORWARD,
    MOTOR_REAR_BACKWARD,
    MOTOR_STEER_LEFT,
    MOTOR_STEER_RIGHT,
)

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

pwm_objects = []


def cleanup():
    """Safe cleanup."""
    global pwm_objects

    # Stop all PWM first
    for pwm in pwm_objects:
        try:
            pwm.ChangeDutyCycle(0)
        except:
            pass

    time.sleep(0.1)

    # Then stop PWM objects
    for pwm in pwm_objects:
        try:
            pwm.stop()
        except:
            pass

    pwm_objects.clear()
    time.sleep(0.2)

    try:
        GPIO.cleanup()
    except:
        pass


def setup_motor():
    """Initialize motor GPIO."""
    global pwm_objects

    pins = [
        MOTOR_REAR_FORWARD,
        MOTOR_REAR_BACKWARD,
        MOTOR_STEER_LEFT,
        MOTOR_STEER_RIGHT,
    ]

    for pin in pins:
        GPIO.setup(pin, GPIO.OUT)
        pwm = GPIO.PWM(pin, 1000)
        pwm.start(0)
        pwm_objects.append(pwm)

    return pwm_objects


def stop_all():
    """Stop all motors."""
    for pwm in pwm_objects:
        pwm.ChangeDutyCycle(0)


def forward(speed=70):
    """Drive forward."""
    pwm_objects[0].ChangeDutyCycle(speed)  # REAR_FORWARD
    pwm_objects[1].ChangeDutyCycle(0)  # REAR_BACKWARD
    pwm_objects[2].ChangeDutyCycle(0)  # STEER_LEFT
    pwm_objects[3].ChangeDutyCycle(0)  # STEER_RIGHT


def backward(speed=70):
    """Drive backward."""
    pwm_objects[0].ChangeDutyCycle(0)  # REAR_FORWARD
    pwm_objects[1].ChangeDutyCycle(speed)  # REAR_BACKWARD
    pwm_objects[2].ChangeDutyCycle(0)  # STEER_LEFT
    pwm_objects[3].ChangeDutyCycle(0)  # STEER_RIGHT


def steer_left():
    """Steer left (0.5s pulse)."""
    pwm_objects[2].ChangeDutyCycle(100)  # STEER_LEFT
    pwm_objects[3].ChangeDutyCycle(0)  # STEER_RIGHT
    time.sleep(0.5)
    pwm_objects[2].ChangeDutyCycle(0)


def steer_right():
    """Steer right (0.5s pulse)."""
    pwm_objects[2].ChangeDutyCycle(0)  # STEER_LEFT
    pwm_objects[3].ChangeDutyCycle(100)  # STEER_RIGHT
    time.sleep(0.5)
    pwm_objects[3].ChangeDutyCycle(0)


try:
    print("Motor Test Script")
    print("=" * 50)
    print("⚠️  WARNING: Make sure car is on blocks!")
    print("=" * 50)
    print(f"GPIO {MOTOR_REAR_FORWARD} → Rear Forward")
    print(f"GPIO {MOTOR_REAR_BACKWARD} → Rear Backward")
    print(f"GPIO {MOTOR_STEER_LEFT} → Steer Left")
    print(f"GPIO {MOTOR_STEER_RIGHT} → Steer Right")
    print("=" * 50)

    input("\nPress Enter to start test...")

    setup_motor()

    print("\n1. Forward (2 seconds)")
    forward(70)
    time.sleep(2)

    print("2. Stop (1 second)")
    stop_all()
    time.sleep(1)

    print("3. Backward (2 seconds)")
    backward(70)
    time.sleep(2)

    print("4. Stop (1 second)")
    stop_all()
    time.sleep(1)

    print("5. Steer Left (0.5 second pulse)")
    steer_left()
    time.sleep(1)

    print("6. Steer Right (0.5 second pulse)")
    steer_right()
    time.sleep(1)

    print("\n✓ Motor test complete!")

except KeyboardInterrupt:
    print("\n\nInterrupted by user")
    stop_all()
except Exception as e:
    print(f"\n✗ Error: {e}")
    stop_all()
finally:
    cleanup()
