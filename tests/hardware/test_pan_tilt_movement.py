#!/usr/bin/env python3
"""Manual movement verification from current 90°/90° position."""

import sys
import time

import RPi.GPIO as GPIO

from lib.pan_tilt import PanTilt
from utils.logger import log_warning

STEP_DELAY = 0.8


MOVES = [
    (95, 90, "Small pan right"),
    (90, 90, "Return center"),
    (85, 90, "Small pan left"),
    (90, 90, "Return center"),
    (120, 90, "Pan far right"),
    (60, 90, "Pan far left"),
    (90, 90, "Pan center"),
    (90, 100, "Tilt up"),
    (90, 90, "Return center"),
    (90, 80, "Tilt down"),
    (90, 90, "Return center"),
    (120, 100, "Upper right"),
    (90, 90, "Center"),
    (60, 80, "Lower left"),
    (90, 90, "Center"),
]


def main() -> int:
    pan_tilt = None
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    try:
        pan_tilt = PanTilt()
        pan_tilt.set_as_current_center()
        print(
            "Starting movement test from current 90°/90° position with no initial command"
        )

        for pan_angle, tilt_angle, label in MOVES:
            print(f"{label}: pan={pan_angle}°, tilt={tilt_angle}°")
            pan_tilt.pan_to(pan_angle)
            pan_tilt.tilt_to(tilt_angle)
            time.sleep(STEP_DELAY)

        print("Movement test completed")
        return 0
    except KeyboardInterrupt:
        log_warning("Movement test interrupted by user")
        return 130
    finally:
        if pan_tilt is not None:
            try:
                pan_tilt.center()
                time.sleep(0.5)
                pan_tilt.cleanup()
            except Exception:
                pass
        GPIO.cleanup()


if __name__ == "__main__":
    sys.exit(main())
