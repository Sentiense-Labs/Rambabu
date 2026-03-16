#!/usr/bin/env python3
"""Test HC-SR04 ultrasonic sensor."""

import RPi.GPIO as GPIO
import time
from config import ULTRASONIC_TRIG, ULTRASONIC_ECHO

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)


def cleanup():
    """Safe cleanup."""
    time.sleep(0.1)
    try:
        GPIO.cleanup()
    except:
        pass


def get_distance():
    """Measure distance in cm."""
    # Send 10us pulse
    GPIO.output(ULTRASONIC_TRIG, True)
    time.sleep(0.00001)
    GPIO.output(ULTRASONIC_TRIG, False)

    # Wait for echo
    timeout = time.time() + 0.1

    pulse_start = time.time()
    while GPIO.input(ULTRASONIC_ECHO) == 0:
        pulse_start = time.time()
        if pulse_start > timeout:
            return None

    pulse_end = time.time()
    while GPIO.input(ULTRASONIC_ECHO) == 1:
        pulse_end = time.time()
        if pulse_end > timeout:
            return None

    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    distance = round(distance, 2)

    if 2 <= distance <= 400:
        return distance
    return None


try:
    print("Ultrasonic Sensor Test")
    print("=" * 50)
    print(f"TRIG → GPIO {ULTRASONIC_TRIG}")
    print(f"ECHO → GPIO {ULTRASONIC_ECHO}")
    print("⚠️  Make sure voltage divider is installed!")
    print("=" * 50)

    GPIO.setup(ULTRASONIC_TRIG, GPIO.OUT)
    GPIO.setup(ULTRASONIC_ECHO, GPIO.IN)

    GPIO.output(ULTRASONIC_TRIG, False)
    time.sleep(0.5)

    print("\nMeasuring distance (Ctrl+C to stop)...\n")

    while True:
        distance = get_distance()

        if distance is not None:
            status = "CLEAR" if distance > 30 else "⚠️  CLOSE"
            print(f"Distance: {distance:6.2f} cm  [{status}]")
        else:
            print("Distance: TIMEOUT (no obstacle detected)")

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\n\nTest stopped by user")
except Exception as e:
    print(f"\n✗ Error: {e}")
finally:
    cleanup()
