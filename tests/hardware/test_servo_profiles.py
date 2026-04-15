#!/usr/bin/env python3
"""Servo movement profile comparison test.

Tests different PWM strategies for pan and tilt servos so you can
pick the smoothest, most jitter-free approach for each.

Wiring:
    PCA9685 ch0 → Tilt servo
    PCA9685 ch1 → Pan servo
    PCA9685 VCC → Pi 3.3V, GND → Pi GND
    PCA9685 SDA → GPIO 2, SCL → GPIO 3
    PCA9685 V+  → Pi 5V

Usage:
    uv run python tests/hardware/test_servo_profiles.py                # run all profiles
    uv run python tests/hardware/test_servo_profiles.py --pan-only     # pan profiles only
    uv run python tests/hardware/test_servo_profiles.py --tilt-only    # tilt profiles only
    uv run python tests/hardware/test_servo_profiles.py --profile 3    # run specific profile
"""

import argparse
import time

from smbus2 import SMBus

import config

# ---------------------------------------------------------------------------
# PCA9685 registers and constants
# ---------------------------------------------------------------------------

_MODE1 = 0x00
_PRESCALE = 0xFE
_LED0_ON_L = 0x06
I2C_BUS = 1

_MIN_TICKS = 102  # 0.5ms → 0°
_MAX_TICKS = 512  # 2.5ms → 180°


# ---------------------------------------------------------------------------
# PCA9685 low-level
# ---------------------------------------------------------------------------


def _init_pca9685(bus: SMBus) -> None:
    addr = config.PCA9685_I2C_ADDRESS
    bus.write_byte_data(addr, _MODE1, 0x10)
    time.sleep(0.005)
    prescale = round(25_000_000 / (4096 * config.SERVO_PWM_FREQ)) - 1
    bus.write_byte_data(addr, _PRESCALE, prescale)
    bus.write_byte_data(addr, _MODE1, 0x20)
    time.sleep(0.005)


def _angle_to_ticks(angle: int) -> int:
    return _MIN_TICKS + int((angle / 180.0) * (_MAX_TICKS - _MIN_TICKS))


def _set_angle(bus: SMBus, ch: int, angle: int) -> None:
    addr = config.PCA9685_I2C_ADDRESS
    reg = _LED0_ON_L + 4 * ch
    ticks = _angle_to_ticks(angle)
    for attempt in range(5):
        try:
            bus.write_byte_data(addr, reg, 0)
            bus.write_byte_data(addr, reg + 1, 0)
            bus.write_byte_data(addr, reg + 2, ticks & 0xFF)
            bus.write_byte_data(addr, reg + 3, (ticks >> 8) & 0xFF)
            return
        except OSError:
            time.sleep(0.01 * (2**attempt))


def _kill(bus: SMBus, ch: int) -> None:
    addr = config.PCA9685_I2C_ADDRESS
    reg = _LED0_ON_L + 4 * ch
    for _ in range(3):
        try:
            bus.write_byte_data(addr, reg, 0)
            bus.write_byte_data(addr, reg + 1, 0)
            bus.write_byte_data(addr, reg + 2, 0)
            bus.write_byte_data(addr, reg + 3, 0x10)
            return
        except OSError:
            time.sleep(0.01)


def _kill_all(bus: SMBus) -> None:
    _kill(bus, config.SERVO_PAN_CHANNEL)
    _kill(bus, config.SERVO_TILT_CHANNEL)


# ---------------------------------------------------------------------------
# Movement profiles
# ---------------------------------------------------------------------------


def _profile_header(num: int, name: str, description: str) -> None:
    print(f"\n{'='*60}")
    print(f"  PROFILE {num}: {name}")
    print(f"  {description}")
    print(f"{'='*60}")


def _make_range(start: int, end: int, step: int) -> range:
    if start < end:
        return range(start, end + 1, step)
    return range(start, end - 1, -step)


def profile_1_smooth_2deg(
    bus: SMBus, ch: int, label: str, lo: int, center: int, hi: int
) -> None:
    """Continuous PWM, 2° steps, 80ms — smooth and slow."""
    _profile_header(
        1, "SMOOTH (2°, 80ms)", "Tiny steps for smoothest motion. PWM on, kill at end."
    )

    _set_angle(bus, ch, center)
    time.sleep(0.5)

    for start, end in [(center, lo), (lo, hi), (hi, center)]:
        print(f"  {label}: {start}° → {end}°")
        for angle in _make_range(start, end, 2):
            _set_angle(bus, ch, angle)
            time.sleep(0.08)

    _kill(bus, ch)
    print(f"  Done — PWM killed")
    time.sleep(1)


def profile_2_smooth_3deg(
    bus: SMBus, ch: int, label: str, lo: int, center: int, hi: int
) -> None:
    """Continuous PWM, 3° steps, 100ms — smooth and steady."""
    _profile_header(
        2, "SMOOTH (3°, 100ms)", "Small steps, generous delay. PWM on, kill at end."
    )

    _set_angle(bus, ch, center)
    time.sleep(0.5)

    for start, end in [(center, lo), (lo, hi), (hi, center)]:
        print(f"  {label}: {start}° → {end}°")
        for angle in _make_range(start, end, 3):
            _set_angle(bus, ch, angle)
            time.sleep(0.10)

    _kill(bus, ch)
    print(f"  Done — PWM killed")
    time.sleep(1)


def profile_3_steady_5deg(
    bus: SMBus, ch: int, label: str, lo: int, center: int, hi: int
) -> None:
    """Continuous PWM, 5° steps, 120ms — visible steps but steady."""
    _profile_header(
        3, "STEADY (5°, 120ms)", "5° steps with long settle. PWM on, kill at end."
    )

    _set_angle(bus, ch, center)
    time.sleep(0.5)

    for start, end in [(center, lo), (lo, hi), (hi, center)]:
        print(f"  {label}: {start}° → {end}°")
        for angle in _make_range(start, end, 5):
            _set_angle(bus, ch, angle)
            time.sleep(0.12)

    _kill(bus, ch)
    print(f"  Done — PWM killed")
    time.sleep(1)


def profile_4_steady_5deg_slow(
    bus: SMBus, ch: int, label: str, lo: int, center: int, hi: int
) -> None:
    """Continuous PWM, 5° steps, 200ms — deliberate, camera-friendly."""
    _profile_header(
        4, "STEADY SLOW (5°, 200ms)", "5° steps, 200ms between. Very deliberate motion."
    )

    _set_angle(bus, ch, center)
    time.sleep(0.5)

    for start, end in [(center, lo), (lo, hi), (hi, center)]:
        print(f"  {label}: {start}° → {end}°")
        for angle in _make_range(start, end, 5):
            _set_angle(bus, ch, angle)
            time.sleep(0.20)

    _kill(bus, ch)
    print(f"  Done — PWM killed")
    time.sleep(1)


def profile_5_burst_and_kill(
    bus: SMBus, ch: int, label: str, lo: int, center: int, hi: int
) -> None:
    """Burst: 15° continuous at 80ms, then kill between bursts."""
    _profile_header(
        5,
        "BURST (15° continuous, kill between)",
        "PWM on for 15° at 80ms per step, kill, next burst.",
    )

    _set_angle(bus, ch, center)
    time.sleep(0.3)
    _kill(bus, ch)

    for start, end in [(center, lo), (lo, hi), (hi, center)]:
        print(f"  {label}: {start}° → {end}°")
        angles = list(_make_range(start, end, 3))
        for i in range(0, len(angles), 5):  # 5 steps of 3° = 15° burst
            burst = angles[i : i + 5]
            for angle in burst:
                _set_angle(bus, ch, angle)
                time.sleep(0.08)
            _kill(bus, ch)
            time.sleep(0.1)

    print(f"  Done — PWM killed")
    time.sleep(1)


def profile_6_move_and_kill(
    bus: SMBus, ch: int, label: str, lo: int, center: int, hi: int
) -> None:
    """Move-and-kill per step — 5° steps, 200ms settle, kill each."""
    _profile_header(
        6,
        "MOVE-AND-KILL (5°, 200ms settle)",
        "Each step: pulse → 200ms → kill. No jitter, slowest.",
    )

    _set_angle(bus, ch, center)
    time.sleep(0.3)
    _kill(bus, ch)

    for start, end in [(center, lo), (lo, hi), (hi, center)]:
        print(f"  {label}: {start}° → {end}°")
        for angle in _make_range(start, end, 5):
            _set_angle(bus, ch, angle)
            time.sleep(0.20)
            _kill(bus, ch)

    print(f"  Done — PWM killed")
    time.sleep(1)


ALL_PROFILES = [
    profile_1_smooth_2deg,
    profile_2_smooth_3deg,
    profile_3_steady_5deg,
    profile_4_steady_5deg_slow,
    profile_5_burst_and_kill,
    profile_6_move_and_kill,
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_profiles(
    bus: SMBus,
    ch: int,
    label: str,
    lo: int,
    center: int,
    hi: int,
    profile_num: int | None = None,
) -> None:
    profiles = ALL_PROFILES
    if profile_num is not None:
        idx = profile_num - 1
        if 0 <= idx < len(profiles):
            profiles = [profiles[idx]]
        else:
            print(f"  Invalid profile {profile_num}. Valid: 1-{len(ALL_PROFILES)}")
            return

    for profile_fn in profiles:
        _kill_all(bus)
        profile_fn(bus, ch, label, lo, center, hi)
        _kill_all(bus)
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servo movement profile comparison")
    parser.add_argument("--pan-only", action="store_true", help="Test pan only")
    parser.add_argument("--tilt-only", action="store_true", help="Test tilt only")
    parser.add_argument(
        "--profile", type=int, default=None, help="Run specific profile (1-6)"
    )
    args = parser.parse_args()

    do_pan = not args.tilt_only
    do_tilt = not args.pan_only

    print("=== Servo Movement Profile Comparison ===")
    print()
    print("  Profile 1: Smooth        (2°, 80ms)  — smoothest")
    print("  Profile 2: Smooth        (3°, 100ms) — small steps")
    print("  Profile 3: Steady        (5°, 120ms) — balanced")
    print("  Profile 4: Steady slow   (5°, 200ms) — deliberate")
    print("  Profile 5: Burst + kill  (3°, 15° bursts)")
    print("  Profile 6: Move-and-kill (5°, 200ms) — no jitter")

    with SMBus(I2C_BUS) as bus:
        _init_pca9685(bus)
        print(f"\n[OK] PCA9685 ready")

        try:
            if do_tilt:
                print(f"\n{'#'*60}")
                print(f"  TILT SERVO (ch {config.SERVO_TILT_CHANNEL})")
                print(
                    f"  Range: {config.TILT_MIN}° – {config.TILT_MAX}°  Center: {config.TILT_CENTER}°"
                )
                print(f"{'#'*60}")
                run_profiles(
                    bus,
                    config.SERVO_TILT_CHANNEL,
                    "TILT",
                    config.TILT_MIN,
                    config.TILT_CENTER,
                    config.TILT_MAX,
                    args.profile,
                )

            if do_pan:
                print(f"\n{'#'*60}")
                print(f"  PAN SERVO (ch {config.SERVO_PAN_CHANNEL})")
                print(
                    f"  Range: {config.PAN_MIN}° – {config.PAN_MAX}°  Center: {config.PAN_CENTER}°"
                )
                print(f"{'#'*60}")
                run_profiles(
                    bus,
                    config.SERVO_PAN_CHANNEL,
                    "PAN",
                    config.PAN_MIN,
                    config.PAN_CENTER,
                    config.PAN_MAX,
                    args.profile,
                )

        except KeyboardInterrupt:
            print("\n\n  Interrupted!")
        finally:
            _kill_all(bus)
            print("\n[OK] All channels killed — servos silent.")
            print()
            print("Pick the best profile for each servo and tell me the number.")
