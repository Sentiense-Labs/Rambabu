#!/usr/bin/env python3
"""Slow continuous servo sweep to visually observe jitter.

Sweeps pan and tilt slowly back and forth so jitter is easy to spot.
Uses software PWM (RPi.GPIO) — the current production method.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import config
from lib.pan_tilt_gpiozero import PanTilt

STEP_DEG = 1  # 1° per step
STEP_DELAY = 0.05  # 50ms = 20°/sec
HOLD_DELAY = 1.0  # Pause at each end


def sweep(
    pan_tilt: PanTilt, name: str, min_angle: int, max_angle: int, passes: int = 3
) -> None:
    print(f"\n{name}: sweeping {min_angle}° → {max_angle}° ({passes} passes)")
    print("Watch the servo — hardware PWM should be smooth with no twitches.\n")

    for i in range(passes):
        # Forward pass
        for angle in range(min_angle, max_angle + 1, STEP_DEG):
            if name == "PAN":
                pan_tilt._apply_pan(angle)
                pan_tilt.pan_angle = angle
            else:
                pan_tilt._apply_tilt(angle)
                pan_tilt.tilt_angle = angle
            time.sleep(STEP_DELAY)

        print(
            f"  Pass {i+1}/{passes} — holding at {max_angle}° (hardware PWM active)..."
        )
        time.sleep(HOLD_DELAY)

        # Reverse pass
        for angle in range(max_angle, min_angle - 1, -STEP_DEG):
            if name == "PAN":
                pan_tilt._apply_pan(angle)
                pan_tilt.pan_angle = angle
            else:
                pan_tilt._apply_tilt(angle)
                pan_tilt.tilt_angle = angle
            time.sleep(STEP_DELAY)

        print(f"  Holding at {min_angle}°...")
        time.sleep(HOLD_DELAY)


def main() -> None:
    print("=" * 60)
    print("  SERVO JITTER TEST — Hardware PWM (gpiozero + lgpio)")
    print("  Slow sweep — should be smooth with no twitches.")
    print("=" * 60)

    pan_tilt = PanTilt()

    print("\nCentering servos...")
    pan_tilt.center()
    time.sleep(1.0)

    try:
        print("\nWhich servo?")
        print("  1 = Pan")
        print("  2 = Tilt")
        print("  3 = Both")
        choice = input("Choice [1/2/3]: ").strip()

        if choice in ("1", "3"):
            sweep(pan_tilt, "PAN", config.PAN_MIN, config.PAN_MAX)

        if choice in ("2", "3"):
            sweep(pan_tilt, "TILT", config.TILT_MIN, config.TILT_MAX)

        print("\nReturning to center...")
        pan_tilt.center()
        time.sleep(1.0)

    except KeyboardInterrupt:
        print("\nAborted.")
    finally:
        pan_tilt.cleanup()
        print("Done.\n")


if __name__ == "__main__":
    main()
