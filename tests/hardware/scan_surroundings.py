#!/usr/bin/env python3
"""Scan all visible surroundings using move-and-kill method (no camera needed)."""

import sys
import time

import RPi.GPIO as GPIO

import config
from lib.pan_tilt import PanTilt
from utils.logger import log_info, log_warning

# Scanning pattern - limited range for safety
SCAN_PATTERN = [
    # (pan, tilt, description, hold_seconds)
    (90, 90, "Center forward", 2.0),
    (120, 90, "Right", 2.0),
    (120, 100, "Right-up", 2.0),
    (120, 80, "Right-down", 2.0),
    (90, 100, "Up", 2.0),
    (90, 80, "Down", 2.0),
    (60, 90, "Left", 2.0),
    (60, 100, "Left-up", 2.0),
    (60, 80, "Left-down", 2.0),
    (90, 90, "Back to center", 2.0),
]

# Extended pattern for more thorough scan
EXTENDED_PATTERN = [
    # Horizontal sweep at different tilt levels
    (60, 100, "Left-up", 1.5),
    (75, 100, "Left-up-center", 1.5),
    (90, 100, "Up-center", 1.5),
    (105, 100, "Right-up-center", 1.5),
    (120, 100, "Right-up", 1.5),
    (120, 90, "Right", 1.5),
    (105, 90, "Right-center", 1.5),
    (90, 90, "Center", 1.5),
    (75, 90, "Left-center", 1.5),
    (60, 90, "Left", 1.5),
    (60, 80, "Left-down", 1.5),
    (75, 80, "Left-down-center", 1.5),
    (90, 80, "Down-center", 1.5),
    (105, 80, "Right-down-center", 1.5),
    (120, 80, "Right-down", 1.5),
    (90, 90, "Back to center", 2.0),
]


def prompt_yes_no(message: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    response = input(message + suffix).strip().lower()
    if not response:
        return default
    return response in {"y", "yes"}


def scan_positions(pan_tilt: PanTilt, pattern: list, scan_name: str) -> None:
    """Execute scanning pattern with move-and-kill."""
    print(f"\n=== {scan_name} ===")
    print(f"Scanning {len(pattern)} positions...")

    for i, (pan, tilt, description, hold_time) in enumerate(pattern, 1):
        print(f"\n[{i}/{len(pattern)}] {description} (pan={pan}°, tilt={tilt}°)")

        # Move both servos
        pan_tilt.pan_to(pan)
        pan_tilt.tilt_to(tilt)

        # Hold position for observation
        print(f"Holding for {hold_time}s - observe surroundings...")
        time.sleep(hold_time)

        # Check for jitter
        if i > 1:  # Skip first position check
            still = prompt_yes_no(
                "Are servos completely still (no jitter)?",
                default=True,
            )
            if not still:
                log_warning("Jitter detected - check power or connections")

    print(f"\n{scan_name} completed")


def continuous_scan(pan_tilt: PanTilt) -> None:
    """Continuous scanning mode - keeps rotating until stopped."""
    print("\n=== Continuous Scan Mode ===")
    print("Press Ctrl+C to stop scanning...")

    scan_angles = [60, 75, 90, 105, 120]
    tilt_angle = 90

    try:
        direction = 1  # 1 for increasing, -1 for decreasing
        current_idx = 0

        while True:
            pan_angle = scan_angles[current_idx]
            print(f"Scanning: pan={pan_angle}°, tilt={tilt_angle}°")

            pan_tilt.pan_to(pan_angle)
            pan_tilt.tilt_to(tilt_angle)

            time.sleep(1.5)  # Hold for observation

            # Update index for next position
            current_idx += direction

            # Reverse direction at ends
            if current_idx >= len(scan_angles) - 1:
                direction = -1
                current_idx = len(scan_angles) - 1
            elif current_idx <= 0:
                direction = 1
                current_idx = 0

    except KeyboardInterrupt:
        print("\nContinuous scan stopped")
        # Return to center
        pan_tilt.center()
        time.sleep(1.0)


def obstacle_check_scan(pan_tilt: PanTilt) -> None:
    """Quick scan for obstacles at critical angles."""
    print("\n=== Obstacle Check Scan ===")
    print("Checking critical angles for obstacles...")

    critical_angles = [
        (90, 90, "Forward"),
        (120, 90, "Right"),
        (60, 90, "Left"),
        (90, 80, "Down"),
        (90, 100, "Up"),
    ]

    for pan, tilt, direction in critical_angles:
        print(f"\nChecking {direction} (pan={pan}°, tilt={tilt}°)")
        pan_tilt.pan_to(pan)
        pan_tilt.tilt_to(tilt)

        # Longer hold for obstacle inspection
        time.sleep(3.0)

        clear = prompt_yes_no(
            f"Is {direction} path clear?",
            default=True,
        )
        if not clear:
            log_warning(f"Obstacle detected {direction}")

    print("\nObstacle check completed")
    pan_tilt.center()


def main() -> int:
    pan_tilt = None
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    try:
        pan_tilt = PanTilt()
        pan_tilt.set_as_current_center()
        print("Surroundings scanner using move-and-kill method")

        while True:
            print("\n" + "=" * 50)
            print("Select scan mode:")
            print("1. Quick scan (10 positions)")
            print("2. Extended scan (16 positions)")
            print("3. Continuous scan (keeps rotating)")
            print("4. Obstacle check (5 critical angles)")
            print("5. Exit")

            choice = input("\nEnter choice [1-5]: ").strip()

            if choice == "1":
                scan_positions(pan_tilt, SCAN_PATTERN, "Quick Scan")
            elif choice == "2":
                scan_positions(pan_tilt, EXTENDED_PATTERN, "Extended Scan")
            elif choice == "3":
                continuous_scan(pan_tilt)
            elif choice == "4":
                obstacle_check_scan(pan_tilt)
            elif choice == "5":
                break
            else:
                print("Invalid choice, try again")

        print("\nScanner completed")
        return 0
    except KeyboardInterrupt:
        log_info("Scanner interrupted by user")
        return 130
    finally:
        if pan_tilt is not None:
            try:
                pan_tilt.center()
                time.sleep(1.0)
                pan_tilt.cleanup()
            except Exception:
                pass
        GPIO.cleanup()


if __name__ == "__main__":
    sys.exit(main())
