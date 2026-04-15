#!/usr/bin/env python3
"""
Read Rambabu's forward ultrasonic distance.

Prints a single reading in centimeters plus a zone classification
(critical / close / medium / clear). Always exits 0 on successful
read; exits 1 if the sensor fails.

Usage:
    uv run python brain/distance.py
"""

import logging
import sys

sys.path.insert(0, "/home/rambabu/rambabu_rc")

import RPi.GPIO as GPIO

from lib.ultrasonic import Ultrasonic

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("distance")


def classify_zone(distance_cm: float) -> str:
    """Map a distance to a human-readable zone label."""
    if distance_cm < 20:
        return "critical"
    if distance_cm < 50:
        return "close"
    if distance_cm < 150:
        return "medium"
    return "clear"


def main() -> None:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    ultra: Ultrasonic | None = None
    try:
        ultra = Ultrasonic()
        ultra.wait_for_reading(timeout=2.0)
        distance_cm = ultra.get_distance()
        zone = classify_zone(distance_cm)
        print(f"distance_cm: {distance_cm:.1f}")
        print(f"zone: {zone}")
    except Exception as exc:
        logger.error(f"Sonar read failed: {exc}")
        print("status: error")
        print(f"message: {exc}")
        sys.exit(1)
    finally:
        if ultra is not None:
            try:
                ultra.cleanup()
            except Exception:
                pass
        try:
            GPIO.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
