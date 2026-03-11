#!/usr/bin/env python3
"""Manual calibration workflow for pan/tilt servos."""

import sys
import time

import RPi.GPIO as GPIO

import config
from lib.pan_tilt import PanTilt
from utils.logger import log_error, log_info, log_warning

STEP_DELAY = 0.6
LIMIT_STEP = 5


class CalibrationAborted(Exception):
    """Raised when the operator aborts calibration."""



def prompt_yes_no(message: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    response = input(message + suffix).strip().lower()
    if not response:
        return default
    return response in {"y", "yes"}



def prompt_int(message: str, default: int) -> int:
    response = input(f"{message} [{default}]: ").strip()
    if not response:
        return default
    return int(response)



def move_and_confirm_direction(pan_tilt: PanTilt, axis: str, angle: int, expected: str) -> None:
    if axis == "pan":
        pan_tilt.pan_to(angle)
    else:
        pan_tilt.tilt_to(angle)

    confirmed = prompt_yes_no(
        f"Did {axis} move {expected} when commanded to {angle}°?",
        default=True,
    )
    if not confirmed:
        raise CalibrationAborted(
            f"Unexpected {axis} movement direction at {angle}°; stop and verify linkage/wiring"
        )

    time.sleep(STEP_DELAY)



def find_limit(pan_tilt: PanTilt, axis: str, start: int, stop: int, step: int) -> int:
    current_safe = start
    angles = range(start + step, stop + step, step)

    for angle in angles:
        if axis == "pan":
            pan_tilt.pan_to(angle)
        else:
            pan_tilt.tilt_to(angle)

        time.sleep(STEP_DELAY)
        safe = prompt_yes_no(
            f"{axis.upper()} at {angle}° moved freely with no resistance, buzzing, or cable snag?",
            default=True,
        )
        if not safe:
            if axis == "pan":
                pan_tilt.pan_to(current_safe)
            else:
                pan_tilt.tilt_to(current_safe)
            log_warning(f"{axis.capitalize()} limit reached before {angle}°; using {current_safe}°")
            return current_safe
        current_safe = angle

    return current_safe



def run_phase_1(pan_tilt: PanTilt) -> tuple[int, int]:
    print("\n=== Phase 1: Verify Current 90° Position ===")
    pan_tilt.set_as_current_center()
    pan_tilt.pan_to(config.PAN_CENTER)
    pan_tilt.tilt_to(config.TILT_CENTER)

    pan_still = prompt_yes_no("Pan servo stayed still at 90°?", default=True)
    tilt_still = prompt_yes_no("Tilt servo stayed still at 90°?", default=True)

    pan_offset = 0 if pan_still else prompt_int("Observed pan offset from true center (degrees)", 0)
    tilt_offset = 0 if tilt_still else prompt_int("Observed tilt offset from true center (degrees)", 0)

    if pan_still:
        log_info("Pan servo at 90° - no movement detected ✓")
    else:
        log_warning(f"Pan servo moved at 90°; observed offset {pan_offset}°")

    if tilt_still:
        log_info("Tilt servo at 90° - no movement detected ✓")
    else:
        log_warning(f"Tilt servo moved at 90°; observed offset {tilt_offset}°")

    return pan_offset, tilt_offset



def run_phase_2(pan_tilt: PanTilt) -> None:
    print("\n=== Phase 2: Test Angle Mapping ===")
    pan_tilt.set_as_current_center()

    pan_tilt.pan_to(90)
    pan_tilt.tilt_to(90)
    time.sleep(STEP_DELAY)

    move_and_confirm_direction(pan_tilt, "pan", 80, "left")
    move_and_confirm_direction(pan_tilt, "pan", 100, "right")
    move_and_confirm_direction(pan_tilt, "tilt", 80, "down")
    move_and_confirm_direction(pan_tilt, "tilt", 100, "up")

    pan_tilt.center()
    log_info("Angle mapping verification completed")



def run_phase_3(pan_tilt: PanTilt) -> dict[str, int]:
    print("\n=== Phase 3: Find Mechanical Limits ===")
    pan_tilt.center()

    pan_max = find_limit(pan_tilt, "pan", config.PAN_CENTER, 140, LIMIT_STEP)
    pan_tilt.pan_to(config.PAN_CENTER)
    time.sleep(STEP_DELAY)
    pan_min = find_limit(pan_tilt, "pan", config.PAN_CENTER, 40, -LIMIT_STEP)
    pan_tilt.pan_to(config.PAN_CENTER)
    time.sleep(STEP_DELAY)

    tilt_max = find_limit(pan_tilt, "tilt", config.TILT_CENTER, 120, LIMIT_STEP)
    pan_tilt.tilt_to(config.TILT_CENTER)
    time.sleep(STEP_DELAY)
    tilt_min = find_limit(pan_tilt, "tilt", config.TILT_CENTER, 60, -LIMIT_STEP)
    pan_tilt.tilt_to(config.TILT_CENTER)

    log_info(
        "Suggested calibrated limits: "
        f"PAN_MIN={pan_min}, PAN_CENTER={config.PAN_CENTER}, PAN_MAX={pan_max}, "
        f"TILT_MIN={tilt_min}, TILT_CENTER={config.TILT_CENTER}, TILT_MAX={tilt_max}"
    )

    return {
        "pan_min": pan_min,
        "pan_max": pan_max,
        "tilt_min": tilt_min,
        "tilt_max": tilt_max,
    }



def run_phase_4(pan_tilt: PanTilt, limits: dict[str, int]) -> None:
    print("\n=== Phase 4: Test Movement Range ===")
    pan_tilt.pan_to(limits["pan_min"])
    time.sleep(STEP_DELAY)
    pan_tilt.pan_to(config.PAN_CENTER)
    time.sleep(STEP_DELAY)
    pan_tilt.pan_to(limits["pan_max"])
    time.sleep(STEP_DELAY)
    pan_tilt.pan_to(config.PAN_CENTER)
    time.sleep(STEP_DELAY)

    pan_tilt.tilt_to(limits["tilt_min"])
    time.sleep(STEP_DELAY)
    pan_tilt.tilt_to(config.TILT_CENTER)
    time.sleep(STEP_DELAY)
    pan_tilt.tilt_to(limits["tilt_max"])
    time.sleep(STEP_DELAY)
    pan_tilt.tilt_to(config.TILT_CENTER)
    time.sleep(STEP_DELAY)

    diagonal_points = [
        (limits["pan_min"], limits["tilt_min"]),
        (config.PAN_CENTER, config.TILT_CENTER),
        (limits["pan_max"], limits["tilt_max"]),
        (config.PAN_CENTER, config.TILT_CENTER),
    ]
    for pan_angle, tilt_angle in diagonal_points:
        pan_tilt.pan_to(pan_angle)
        pan_tilt.tilt_to(tilt_angle)
        time.sleep(STEP_DELAY)

    figure_eight = [
        (limits["pan_min"], config.TILT_CENTER),
        (config.PAN_CENTER, limits["tilt_max"]),
        (limits["pan_max"], config.TILT_CENTER),
        (config.PAN_CENTER, limits["tilt_min"]),
        (limits["pan_min"], config.TILT_CENTER),
        (config.PAN_CENTER, config.TILT_CENTER),
    ]
    for pan_angle, tilt_angle in figure_eight:
        pan_tilt.pan_to(pan_angle)
        pan_tilt.tilt_to(tilt_angle)
        time.sleep(STEP_DELAY)

    free_motion = prompt_yes_no(
        "Did full-range motion complete without wire snag, cable pinch, or binding?",
        default=True,
    )
    if not free_motion:
        log_warning("Cable routing or mechanical clearance needs adjustment before regular use")



def print_wiring_checklist() -> None:
    print("\n=== Manual Wiring Verification Checklist ===")
    print("Pan servo (bottom): signal->GPIO18, power->buck 5V rail, ground->common GND")
    print("Tilt servo (top): signal->GPIO19, power->same buck 5V rail, ground->common GND")
    print("Power: both servos on buck converter 5V, not Raspberry Pi 5V pin")
    print("Cable management: CSI cable slack through full pan/tilt range, no pinch or snag")



def main() -> int:
    pan_tilt = None
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    try:
        print("Starting pan/tilt calibration from assumed current center 90°/90°")
        pan_tilt = PanTilt()
        pan_tilt.set_as_current_center()

        pan_offset, tilt_offset = run_phase_1(pan_tilt)
        run_phase_2(pan_tilt)
        limits = run_phase_3(pan_tilt)
        run_phase_4(pan_tilt, limits)
        print_wiring_checklist()

        print("\n=== Calibration Summary ===")
        print(f"PAN_MIN={limits['pan_min']}")
        print(f"PAN_CENTER={config.PAN_CENTER}")
        print(f"PAN_MAX={limits['pan_max']}")
        print(f"TILT_MIN={limits['tilt_min']}")
        print(f"TILT_CENTER={config.TILT_CENTER}")
        print(f"TILT_MAX={limits['tilt_max']}")
        print(f"PAN_OFFSET={pan_offset}")
        print(f"TILT_OFFSET={tilt_offset}")
        print("Update config/__init__.py with any measured values that differ.")
        return 0
    except CalibrationAborted as exc:
        log_error(str(exc))
        return 1
    except KeyboardInterrupt:
        log_warning("Calibration interrupted by user")
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
