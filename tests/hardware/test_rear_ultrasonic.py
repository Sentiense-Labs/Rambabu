#!/usr/bin/env python3
"""
Rear ultrasonic presence test.

Wiring (new rear HC-SR04):
    TRIG -> GPIO 23
    ECHO -> GPIO 22  (⚠️ use 5V->3.3V voltage divider!)

Run directly on the Pi:
    python3 tests/hardware/test_rear_ultrasonic.py

Success: prints plausible distances (2-400 cm) responding to objects
behind the car. If it prints only timeouts or 'no echo', check wiring,
power (VCC=5V), and the voltage divider on ECHO.
"""

import time
import RPi.GPIO as GPIO

REAR_TRIG: int = 23
REAR_ECHO: int = 22

SAMPLES: int = 20
SAMPLE_INTERVAL: float = 0.2  # seconds between reads (5 Hz)
ECHO_TIMEOUT: float = 0.04    # 40ms — covers full 400cm range with margin


def measure_once(trig: int, echo: int) -> float | None:
    """Fire one trigger pulse and return distance in cm, or None on timeout."""
    GPIO.output(trig, True)
    time.sleep(0.00001)  # 10 us pulse
    GPIO.output(trig, False)

    deadline = time.time() + ECHO_TIMEOUT

    pulse_start = time.time()
    while GPIO.input(echo) == 0:
        pulse_start = time.time()
        if pulse_start > deadline:
            return None

    pulse_end = time.time()
    while GPIO.input(echo) == 1:
        pulse_end = time.time()
        if pulse_end > deadline:
            return None

    distance_cm = round((pulse_end - pulse_start) * 17150, 2)
    if 2 <= distance_cm <= 400:
        return distance_cm
    return None


def main() -> None:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(REAR_TRIG, GPIO.OUT)
    GPIO.setup(REAR_ECHO, GPIO.IN)
    GPIO.output(REAR_TRIG, False)

    print(f"Rear ultrasonic test — TRIG={REAR_TRIG}, ECHO={REAR_ECHO}")
    print(f"Taking {SAMPLES} samples at {1/SAMPLE_INTERVAL:.0f} Hz...\n")
    time.sleep(0.2)  # let sensor settle

    hits = 0
    try:
        for i in range(1, SAMPLES + 1):
            distance = measure_once(REAR_TRIG, REAR_ECHO)
            if distance is None:
                print(f"[{i:02d}] no echo (timeout)")
            else:
                hits += 1
                print(f"[{i:02d}] {distance:6.2f} cm")
            time.sleep(SAMPLE_INTERVAL)
    finally:
        GPIO.cleanup([REAR_TRIG, REAR_ECHO])

    print(f"\nValid readings: {hits}/{SAMPLES}")
    if hits == 0:
        print("FAIL: sensor not responding — check VCC(5V), GND, TRIG/ECHO wiring,")
        print("      and the voltage divider on ECHO (1kΩ series, 2kΩ to GND).")
    elif hits < SAMPLES // 2:
        print("WARN: intermittent readings — suspect loose wiring or power.")
    else:
        print("OK: rear ultrasonic is present and responding.")


if __name__ == "__main__":
    main()
