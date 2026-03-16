#!/usr/bin/env python3
"""Manual long-running drift check for pan/tilt servos."""

import sys
import time

import RPi.GPIO as GPIO

import config
from lib.pan_tilt import PanTilt
from utils.logger import log_info, log_warning

CHECK_INTERVAL_SECONDS = 30
TOTAL_DURATION_SECONDS = 5 * 60


def main() -> int:
    pan_tilt = None
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    try:
        pan_tilt = PanTilt()
        pan_tilt.set_as_current_center()
        pan_tilt.pan_to(config.PAN_CENTER)
        pan_tilt.tilt_to(config.TILT_CENTER)
        print("Monitoring pan/tilt drift at 90°/90° for 5 minutes")

        iterations = TOTAL_DURATION_SECONDS // CHECK_INTERVAL_SECONDS
        for iteration in range(1, iterations + 1):
            time.sleep(CHECK_INTERVAL_SECONDS)
            print(f"Drift check {iteration}/{iterations}: re-sending 90°/90°")
            pan_tilt.pan_to(config.PAN_CENTER)
            pan_tilt.tilt_to(config.TILT_CENTER)
            drifted = (
                input("Did either servo visibly drift before this refresh? [y/N]: ")
                .strip()
                .lower()
            )
            if drifted in {"y", "yes"}:
                log_warning(
                    f"Drift detected after {iteration * CHECK_INTERVAL_SECONDS} seconds at center"
                )
            else:
                log_info(
                    f"No drift detected after {iteration * CHECK_INTERVAL_SECONDS} seconds at center"
                )

        print("Drift test completed")
        return 0
    except KeyboardInterrupt:
        log_warning("Drift test interrupted by user")
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
