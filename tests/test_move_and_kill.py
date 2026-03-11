#!/usr/bin/env python3
"""Test move-and-kill method for jitter elimination and drift behavior."""

import sys
import time

import RPi.GPIO as GPIO

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
    print("\n=== Test 1: Single Movements ===")
    
    movements = [(120, "right"), (60, "left"), (90, "center")]
    
    for angle, direction in movements:
        print(f"Moving pan to {angle}° ({direction})")
        pan_tilt.pan_to(angle)
        time.sleep(TEST_DELAY)
        
        no_jitter = prompt_yes_no(
            f"Is servo completely still at {angle}° (no jitter)?",
            default=True,
        )
        if not no_jitter:
            log_warning(f"Jitter detected at {angle}°")
            return False
    
    print("✓ Single movements work without jitter")
    return True


def test_drift_after_kill(pan_tilt: PanTilt) -> bool:
    print(f"\n=== Test 2: Drift After PWM Kill ({DRIFT_WAIT_SECONDS}s) ===")
    
    print("Moving pan to 90° and killing PWM")
    pan_tilt.pan_to(90)
    
    print(f"Waiting {DRIFT_WAIT_SECONDS} seconds...")
    time.sleep(DRIFT_WAIT_SECONDS)
    
    no_drift = prompt_yes_no(
        f"Did servo stay at 90° for {DRIFT_WAIT_SECONDS}s without drifting?",
        default=True,
    )
    if not no_drift:
        log_warning("Servo drifted after PWM kill - camera may be too heavy")
        use_hold = prompt_yes_no(
            "Should we test hold_position method for heavy loads?",
            default=True,
        )
        if use_hold:
            print("Testing hold_position for 10 seconds...")
            pan_tilt.hold_position(90, 10, axis="pan")
            return prompt_yes_no(
                "Did hold_position keep servo stable?",
                default=True,
            )
        return False
    
    print("✓ No drift detected after PWM kill")
    return True


def test_multiple_movements(pan_tilt: PanTilt) -> bool:
    print("\n=== Test 3: Multiple Sequential Movements ===")
    
    sequence = [90, 120, 60, 90]
    
    for i, angle in enumerate(sequence):
        print(f"Step {i+1}: Moving to {angle}°")
        pan_tilt.pan_to(angle)
        time.sleep(TEST_DELAY)
        
        accurate = prompt_yes_no(
            f"Did servo reach {angle}° accurately?",
            default=True,
        )
        if not accurate:
            log_warning(f"Inaccurate movement to {angle}°")
            return False
    
    print("✓ Multiple movements work without accumulation errors")
    return True


def test_combined_pan_tilt(pan_tilt: PanTilt) -> bool:
    print("\n=== Test 4: Combined Pan + Tilt ===")
    
    print("Moving pan to 120°")
    pan_tilt.pan_to(120)
    time.sleep(TEST_DELAY)
    
    print("Moving tilt to 100°")
    pan_tilt.tilt_to(100)
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
        "Test smooth pan scanning from 60° to 120°?",
        default=True,
    )
    if not scan:
        return True
    
    print("Starting smooth scan...")
    pan_tilt.pan_scan(60, 120, step=2)
    
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
    pan_tilt = None
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    try:
        pan_tilt = PanTilt()
        pan_tilt.set_as_current_center()
        print("Testing move-and-kill method for jitter elimination")

        tests = [
            test_single_movements,
            test_drift_after_kill,
            test_multiple_movements,
            test_combined_pan_tilt,
            test_smooth_scanning,
        ]
        
        passed = 0
        for test in tests:
            if test(pan_tilt):
                passed += 1
            else:
                print(f"Test failed: {test.__name__}")
        
        print(f"\n=== Results ===")
        print(f"Tests passed: {passed}/{len(tests)}")
        
        if passed == len(tests):
            print("✓ All tests passed - move-and-kill working correctly")
            return 0
        else:
            print("✗ Some tests failed - check power, connections, or timing")
            return 1
    except KeyboardInterrupt:
        log_info("Move-and-kill test interrupted by user")
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
