#!/usr/bin/env python3
"""Test hardware PWM (rpi-hardware-pwm via sysfs) for jitter-free servo operation."""

import sys
import time

import config
from lib.pan_tilt import PanTilt
from utils.logger import log_info, log_warning

TEST_DELAY = 1.0
DRIFT_WAIT_SECONDS = 30


def prompt_yes_no(message: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    response = input(message + suffix).strip().lower()
    if not response:
        return default
    return response in {"y", "yes"}


def test_single_movements(pan_tilt: PanTilt) -> bool:
    print("\n=== Test 1: Single Movements (Hardware PWM) ===")

    # Use angles within configured limits
    movements = [
        (config.PAN_MAX, "right"),
        (config.PAN_MIN, "left"),
        (config.PAN_CENTER, "center"),
    ]

    for angle, direction in movements:
        print(f"Moving pan to {angle}° ({direction})")
        pan_tilt.pan_to(angle)
        time.sleep(TEST_DELAY)

        no_jitter = prompt_yes_no(
            f"Is servo completely still at {angle}° (NO jitter)?",
            default=True,
        )
        if not no_jitter:
            log_warning(
                f"Jitter detected at {angle}° - hardware PWM may not be working"
            )
            return False

    print("✓ Single movements work without jitter (hardware PWM working)")
    return True


def test_drift(pan_tilt: PanTilt) -> bool:
    print(f"\n=== Test 2: Drift Test ({DRIFT_WAIT_SECONDS}s) ===")

    print("Moving pan to 90°")
    pan_tilt.pan_to(90)

    print(f"Waiting {DRIFT_WAIT_SECONDS} seconds...")
    time.sleep(DRIFT_WAIT_SECONDS)

    no_drift = prompt_yes_no(
        f"Did servo stay at 90° for {DRIFT_WAIT_SECONDS}s without drifting?",
        default=True,
    )
    if not no_drift:
        log_warning("Servo drifted - camera may be too heavy")
        return False

    print("✓ No drift detected (hardware PWM is stable)")
    return True


def test_continuous_hold(pan_tilt: PanTilt) -> bool:
    print("\n=== Test 3: Continuous Hold (Hardware PWM Stability) ===")

    print(f"Moving pan to {config.PAN_MAX}° and holding for 10 seconds")
    pan_tilt.pan_to(config.PAN_MAX)

    print("Holding... (watch for any jitter)")
    time.sleep(10)

    stable = prompt_yes_no(
        f"Was servo completely stable for 10 seconds (no jitter at all)?",
        default=True,
    )
    if not stable:
        log_warning("Jitter during continuous hold - hardware PWM issue")
        return False

    print("✓ Continuous hold stable (hardware PWM working correctly)")
    return True


def test_combined_movements(pan_tilt: PanTilt) -> bool:
    print("\n=== Test 4: Combined Pan + Tilt ===")

    print(f"Moving pan to {config.PAN_MAX}°")
    pan_tilt.pan_to(config.PAN_MAX)
    time.sleep(TEST_DELAY)

    print(f"Moving tilt to {config.TILT_MAX}°")
    pan_tilt.tilt_to(config.TILT_MAX)
    time.sleep(TEST_DELAY)

    both_still = prompt_yes_no(
        "Are both servos completely still (no jitter)?",
        default=True,
    )
    if not both_still:
        log_warning("Jitter detected in combined movement")
        return False

    print("✓ Combined pan + tilt work without jitter")
    return True


def test_smooth_scanning(pan_tilt: PanTilt) -> bool:
    print("\n=== Test 5: Smooth Scanning ===")

    scan = prompt_yes_no(
        f"Test smooth pan scanning from {config.PAN_MIN}° to {config.PAN_MAX}°?",
        default=True,
    )
    if not scan:
        return True

    print(f"Starting smooth scan from {config.PAN_MIN}° to {config.PAN_MAX}°...")
    pan_tilt.pan_scan(config.PAN_MIN, config.PAN_MAX, step=2)

    smooth = prompt_yes_no(
        "Was scanning smooth and ended without jitter?",
        default=True,
    )
    if not smooth:
        log_warning("Issue with smooth scanning")
        return False

    print("✓ Smooth scanning works")
    return True


def main() -> int:
    print("=" * 60)
    print("Hardware PWM Test (rpi-hardware-pwm via sysfs)")
    print("=" * 60)
    print(f"Pan servo: GPIO {config.PAN_SERVO}")
    print(f"Tilt servo: GPIO {config.TILT_SERVO}")
    print("=" * 60)

    try:
        pan_tilt = PanTilt()
        pan_tilt.set_as_current_center()
        print("Pan-tilt initialized with hardware PWM (sysfs)")

        tests = [
            test_single_movements,
            test_drift,
            test_continuous_hold,
            test_combined_movements,
            test_smooth_scanning,
        ]

        passed = 0
        for test in tests:
            if test(pan_tilt):
                passed += 1
            else:
                print(f"Test failed: {test.__name__}")

        print(f"\n{'=' * 60}")
        print(f"Results: {passed}/{len(tests)} tests passed")
        print("=" * 60)

        if passed == len(tests):
            print("✓ ALL TESTS PASSED - Hardware PWM working perfectly!")
            print("✓ No jitter, no drift, stable operation")
            return 0
        else:
            print("✗ Some tests failed - check wiring and GPIO pins")
            print("  - Ensure servos are on GPIO 12 and 13")
            print("  - Ensure 'dtoverlay=pwm-2chan' is in /boot/config.txt")
            print("  - Reboot after adding PWM overlay")
            return 1
    except KeyboardInterrupt:
        log_info("Test interrupted by user")
        return 130
    except Exception as e:
        print(f"ERROR: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure 'dtoverlay=pwm-2chan' is in /boot/config.txt")
        print("2. Reboot after adding PWM overlay")
        print("3. Check GPIO pins are correct (12 and 13)")
        print("4. Ensure servos have power from buck converter")
        return 1
    finally:
        try:
            pan_tilt.center()
            time.sleep(0.5)
            pan_tilt.cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
