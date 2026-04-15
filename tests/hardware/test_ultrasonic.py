#!/usr/bin/env python3
"""Test HC-SR04 ultrasonic sensor — with median filter + obstacle confirmation.

Matches the filtering logic in lib/ultrasonic.py:
  - Median of 5 readings rejects noise spikes
  - Streak on median (not raw) for obstacle confirmation
  - Emergency fast-path at <10cm
"""

import RPi.GPIO as GPIO
import time
from collections import deque
from config import (
    ULTRASONIC_TRIG,
    ULTRASONIC_ECHO,
    OBSTACLE_DETECTION_DISTANCE,
)

# Match lib/ultrasonic.py constants
_WINDOW_SIZE: int = 5
_CONFIRM_COUNT: int = 2
_EMERGENCY_DISTANCE: float = 10.0
_MAX_DELTA_PER_SAMPLE: float = 25.0

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)


def cleanup():
    time.sleep(0.1)
    try:
        GPIO.cleanup()
    except Exception:
        pass


def measure_distance(last: float) -> float:
    GPIO.output(ULTRASONIC_TRIG, True)
    time.sleep(0.00001)
    GPIO.output(ULTRASONIC_TRIG, False)

    timeout = time.time() + 0.1

    pulse_start = time.time()
    while GPIO.input(ULTRASONIC_ECHO) == 0:
        pulse_start = time.time()
        if pulse_start > timeout:
            return last

    pulse_end = time.time()
    while GPIO.input(ULTRASONIC_ECHO) == 1:
        pulse_end = time.time()
        if pulse_end > timeout:
            return last

    pulse_duration = pulse_end - pulse_start
    distance = round(pulse_duration * 17150, 2)

    if 2 <= distance <= 400:
        return distance
    return last


def median(window: deque) -> float:
    if not window:
        return 999.0
    sorted_values = sorted(window)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2 == 0:
        return (sorted_values[mid - 1] + sorted_values[mid]) / 2
    return sorted_values[mid]


def is_plausible_close(raw: float, current_median: float) -> bool:
    if current_median <= OBSTACLE_DETECTION_DISTANCE * 1.5:
        return True
    delta = current_median - raw
    return delta <= _MAX_DELTA_PER_SAMPLE


try:
    print("Ultrasonic Sensor Test (median + confirmation)")
    print("=" * 60)
    print(f"TRIG → GPIO {ULTRASONIC_TRIG}")
    print(f"ECHO → GPIO {ULTRASONIC_ECHO}")
    print(f"Window: {_WINDOW_SIZE}  |  Confirm: {_CONFIRM_COUNT} consecutive medians")
    print(
        f"Emergency: <{_EMERGENCY_DISTANCE}cm  |  Stop: <={OBSTACLE_DETECTION_DISTANCE}cm"
    )
    print("=" * 60)

    GPIO.setup(ULTRASONIC_TRIG, GPIO.OUT)
    GPIO.setup(ULTRASONIC_ECHO, GPIO.IN)

    GPIO.output(ULTRASONIC_TRIG, False)
    time.sleep(0.5)

    print("\nMeasuring distance (Ctrl+C to stop)...\n")

    window: deque[float] = deque(maxlen=_WINDOW_SIZE)
    last_distance: float = 999.0
    close_streak: int = 0
    emergency: bool = False

    while True:
        raw = measure_distance(last_distance)
        old_median = median(window)

        window.append(raw)
        med = median(window)
        last_distance = med

        if med <= OBSTACLE_DETECTION_DISTANCE:
            close_streak += 1
        else:
            close_streak = 0

        emergency = raw <= _EMERGENCY_DISTANCE and is_plausible_close(raw, old_median)

        confirmed = emergency or close_streak >= _CONFIRM_COUNT

        if confirmed:
            tag = "EMERGENCY" if emergency else "CONFIRMED"
            print(
                f"Distance: {med:6.2f} cm  [!! {tag} !!]  "
                f"(raw: {raw:.1f}  streak: {close_streak})"
            )
        elif med <= OBSTACLE_DETECTION_DISTANCE:
            print(
                f"Distance: {med:6.2f} cm  [CLOSE streak={close_streak}]  "
                f"(raw: {raw:.1f})"
            )
        else:
            status = "CLEAR" if med > 30 else "NEAR"
            print(f"Distance: {med:6.2f} cm  [{status}]  (raw: {raw:.1f})")

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\n\nTest stopped by user")
except Exception as e:
    print(f"\n✗ Error: {e}")
finally:
    cleanup()
