#!/usr/bin/env python3
"""
U-turn profile tester — empirical calibration of turning maneuvers.

Each profile is a fixed parameter set (arc duration, leg count, reverse
duration, speed, final straighten). Run them one at a time and tell the
maintainer which one physically completes a 180° flip. The winner's
parameters become the defaults in brain/maneuvers.py.

Usage (aicar service must be stopped first so GPIO is free):
    sudo systemctl stop aicar
    uv run python tests/hardware/test_uturn_profile.py --list
    uv run python tests/hardware/test_uturn_profile.py --profile single-3s
    uv run python tests/hardware/test_uturn_profile.py --profile single-4s --side left
    uv run python tests/hardware/test_uturn_profile.py --custom \
        --arc 2.5 --legs 2 --reverse 0.5 --speed 80 --final 1.0
    sudo systemctl start aicar
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import RPi.GPIO as GPIO

from brain.hardware_tools import HardwareContext
from brain.movement_manager import MovementManager
from brain.sonar_guard import SonarGuard
from lib.motor import MotorController
from lib.ultrasonic import Ultrasonic


@dataclass(frozen=True)
class Profile:
    """A single U-turn parameter set."""
    name: str
    arc_seconds: float          # forward-arc duration per leg
    legs: int                   # number of forward arcs
    reverse_seconds: float      # reverse-arc duration between legs (0 = no reverse)
    speed: int                  # motor duty cycle 0-100
    final_straight_s: float     # forward-straight settle at end
    description: str


# Each profile isolates one variable at a time so we can pinpoint what
# actually matters. Start with single-arc profiles to test pure turning
# radius, then layer in iteration.
PROFILES: dict[str, Profile] = {
    "single-2s": Profile(
        "single-2s", arc_seconds=2.0, legs=1, reverse_seconds=0.0,
        speed=80, final_straight_s=0.0,
        description="One 2.0s forward arc — should produce ~120°-ish",
    ),
    "single-3s": Profile(
        "single-3s", arc_seconds=3.0, legs=1, reverse_seconds=0.0,
        speed=80, final_straight_s=0.0,
        description="One 3.0s forward arc — current default budget",
    ),
    "single-4s": Profile(
        "single-4s", arc_seconds=4.0, legs=1, reverse_seconds=0.0,
        speed=80, final_straight_s=0.0,
        description="One 4.0s forward arc — likely overshoots if turning is tight",
    ),
    "single-5s": Profile(
        "single-5s", arc_seconds=5.0, legs=1, reverse_seconds=0.0,
        speed=80, final_straight_s=0.0,
        description="One 5.0s forward arc — for testing wide turning radius",
    ),
    "single-6s": Profile(
        "single-6s", arc_seconds=6.0, legs=1, reverse_seconds=0.0,
        speed=80, final_straight_s=0.0,
        description="One 6.0s forward arc — extreme; only for very wide radius",
    ),
    "classic-3pt": Profile(
        "classic-3pt", arc_seconds=2.0, legs=2, reverse_seconds=0.5,
        speed=80, final_straight_s=1.0,
        description="2 forward arcs of 2.0s with one 0.5s reverse between",
    ),
    "tight-5pt": Profile(
        "tight-5pt", arc_seconds=1.0, legs=3, reverse_seconds=0.5,
        speed=80, final_straight_s=0.5,
        description="3 short arcs of 1.0s with 0.5s reverses — for tight spaces",
    ),
    "aggressive-2leg": Profile(
        "aggressive-2leg", arc_seconds=2.5, legs=2, reverse_seconds=0.5,
        speed=80, final_straight_s=1.0,
        description="2 long arcs of 2.5s + 0.5s reverse (5s total arc time)",
    ),
    "slow-deep": Profile(
        "slow-deep", arc_seconds=4.0, legs=1, reverse_seconds=0.0,
        speed=60, final_straight_s=0.0,
        description="One 4.0s arc at speed 60 — same arc length as single-3s@80",
    ),
    "fast-quick": Profile(
        "fast-quick", arc_seconds=2.0, legs=1, reverse_seconds=0.0,
        speed=100, final_straight_s=0.0,
        description="One 2.0s arc at full speed 100 — same arc length as single-2.5s@80",
    ),
}


def list_profiles() -> None:
    print(f"\n{'name':<18} {'arc':>5} {'legs':>5} {'rev':>5} {'spd':>5} {'final':>6}  description")
    print("─" * 110)
    for p in PROFILES.values():
        total = p.arc_seconds * p.legs + p.reverse_seconds * max(0, p.legs - 1) + p.final_straight_s
        print(
            f"{p.name:<18} {p.arc_seconds:>5.1f} {p.legs:>5d} "
            f"{p.reverse_seconds:>5.2f} {p.speed:>5d} {p.final_straight_s:>6.1f}  "
            f"{p.description}  (~{total:.1f}s total)"
        )
    print()


# Minimum clearance to start. The rover's nose advances at most ~radius
# (~65 cm) before the arc curves it away, so 70 cm of front clearance is
# enough for any single arc up to ~5 s. Below this, the test prepends a
# back-disengage step to create maneuvering room (mirroring three_point_turn).
MIN_OPEN_SPACE_CM: float = 70.0
DISENGAGE_THRESHOLD_CM: float = 60.0
DISENGAGE_BACK_S: float = 0.5


def init_hardware() -> tuple[MotorController, Ultrasonic, SonarGuard, HardwareContext]:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    motor = MotorController()
    ultra = Ultrasonic()
    ultra.wait_for_reading(timeout=2.0)
    sonar = SonarGuard(ultrasonic=ultra, motor=motor)
    sonar.start()
    time.sleep(1.0)  # let SonarGuard window fill
    mm = MovementManager(motor=motor, sonar_guard=sonar)
    hw = HardwareContext(
        motor=motor, ultrasonic=ultra, sonar_guard=sonar, movement_manager=mm,
    )
    return motor, ultra, sonar, hw


def cleanup_hardware(motor, ultra, sonar) -> None:
    try:
        if sonar is not None:
            sonar.stop()
    except Exception as exc:
        print(f"[cleanup] sonar: {exc}")
    try:
        if motor is not None:
            motor.stop()
            motor.cleanup()
    except Exception as exc:
        print(f"[cleanup] motor: {exc}")
    try:
        if ultra is not None:
            ultra.cleanup()
    except Exception as exc:
        print(f"[cleanup] ultra: {exc}")
    try:
        GPIO.cleanup()
    except Exception:
        pass


def run_profile(hw: HardwareContext, profile: Profile, side: str) -> dict:
    """Execute one profile. side = 'left' or 'right' — first arc direction."""
    motor = hw.motor
    opposite = "left" if side == "right" else "right"

    print(f"\n=== running profile: {profile.name} (side={side}) ===")
    print(f"  arc={profile.arc_seconds}s × {profile.legs} legs, "
          f"reverse={profile.reverse_seconds}s, speed={profile.speed}, "
          f"final_straight={profile.final_straight_s}s")

    # Same as brain/maneuvers.py — wait for steering to physically reach
    # full lock before engaging the drive motor. Without this, short arcs
    # drive nearly straight while the wheels are still mid-swing.
    STEER_LOCK_SETTLE_S = 0.25

    motor.stop()
    motor.steer_center()
    time.sleep(0.2)

    cumulative_arc = 0.0
    started = time.time()

    for leg in range(1, profile.legs + 1):
        # Forward arc
        if side == "left":
            motor.steer_left_hold()
        else:
            motor.steer_right_hold()
        time.sleep(STEER_LOCK_SETTLE_S)
        motor.front(profile.speed)
        time.sleep(profile.arc_seconds)
        motor.stop()
        motor.steer_center()
        cumulative_arc += profile.arc_seconds
        print(f"  leg {leg}: forward-arc {side} {profile.arc_seconds}s done")

        # Reverse arc between legs (skip on the last leg)
        if leg < profile.legs and profile.reverse_seconds > 0:
            time.sleep(0.1)
            if opposite == "left":
                motor.steer_left_hold()
            else:
                motor.steer_right_hold()
            time.sleep(STEER_LOCK_SETTLE_S)
            motor.back(profile.speed)
            # No safety cap for calibration — we already verified front
            # clearance, and the reverses are short enough that a single
            # 1.5s back at 67cm/s = ~100cm of reverse, well within the
            # workspace. Production code still caps at 0.5s.
            time.sleep(min(profile.reverse_seconds, 1.5))
            motor.stop()
            motor.steer_center()
            print(f"  leg {leg}: reverse-arc {opposite} {profile.reverse_seconds}s done")

    # Final straighten
    if profile.final_straight_s > 0:
        time.sleep(0.1)
        motor.front(profile.speed)
        time.sleep(profile.final_straight_s)
        motor.stop()
        print(f"  final straighten {profile.final_straight_s}s done")

    elapsed = time.time() - started
    # Open-loop estimate using current 60°/s constant
    estimated_deg = int(cumulative_arc * 60)

    print(f"\n  cumulative_arc_seconds: {cumulative_arc:.2f}")
    print(f"  open-loop estimate:     {estimated_deg}° "
          f"(at 60°/s — adjust this after physical verification)")
    print(f"  total elapsed:          {elapsed:.2f}s")

    return {
        "profile": profile.name,
        "side": side,
        "cumulative_arc_s": round(cumulative_arc, 2),
        "estimated_deg": estimated_deg,
        "elapsed_s": round(elapsed, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a single U-turn profile")
    parser.add_argument("--list", action="store_true", help="List available profiles")
    parser.add_argument("--profile", choices=list(PROFILES), help="Named profile to run")
    parser.add_argument("--custom", action="store_true",
                        help="Use --arc/--legs/--reverse/--speed/--final instead of a named profile")
    parser.add_argument("--side", choices=["left", "right"], default="right")
    parser.add_argument("--arc", type=float, default=2.0, help="Custom: forward-arc seconds per leg")
    parser.add_argument("--legs", type=int, default=1, help="Custom: number of forward arcs")
    parser.add_argument("--reverse", type=float, default=0.5, help="Custom: reverse seconds (capped 0.5)")
    parser.add_argument("--speed", type=int, default=80, help="Custom: motor speed 0-100")
    parser.add_argument("--final", type=float, default=0.0, help="Custom: final straighten seconds")
    args = parser.parse_args()

    if args.list:
        list_profiles()
        return 0

    if args.custom:
        profile = Profile(
            name=f"custom(arc={args.arc},legs={args.legs},rev={args.reverse},spd={args.speed},fin={args.final})",
            arc_seconds=args.arc, legs=args.legs, reverse_seconds=args.reverse,
            speed=args.speed, final_straight_s=args.final,
            description="custom",
        )
    elif args.profile:
        profile = PROFILES[args.profile]
    else:
        print("error: choose --profile NAME or --custom (see --list)", file=sys.stderr)
        return 2

    motor = ultra = sonar = None
    try:
        print("[init] hardware...")
        motor, ultra, sonar, hw = init_hardware()
        start_d = ultra.get_distance()
        start_safety = sonar.get_safety_distance()
        print(f"[init] starting distance: {start_d:.1f}cm  "
              f"safety_min={start_safety:.1f}cm  zone={sonar.get_zone()}")

        # Auto-disengage if pressed against an obstacle. Mirrors what the
        # production three_point_turn tool does — back up first to create
        # room before starting the arc.
        if start_safety < DISENGAGE_THRESHOLD_CM:
            print(
                f"[disengage] front {start_safety:.1f}cm < "
                f"{DISENGAGE_THRESHOLD_CM:.0f}cm — backing up "
                f"{DISENGAGE_BACK_S}s to create room"
            )
            motor.back(80)
            time.sleep(DISENGAGE_BACK_S)
            motor.stop()
            time.sleep(0.3)
            new_safety = sonar.get_safety_distance()
            print(f"[disengage] after back: safety={new_safety:.1f}cm")
            start_safety = new_safety

        if start_safety < MIN_OPEN_SPACE_CM:
            print(
                f"\n[abort] safety distance {start_safety:.1f}cm < "
                f"{MIN_OPEN_SPACE_CM:.0f}cm minimum (even after disengage).\n"
                "Move the rover to a slightly more open area "
                f"(at least {MIN_OPEN_SPACE_CM/100:.1f}m of clear space ahead)\n"
                "and re-run.",
                file=sys.stderr,
            )
            return 3
        result = run_profile(hw, profile, args.side)
        print(f"\n[done] {result}")
        return 0
    finally:
        cleanup_hardware(motor, ultra, sonar)


if __name__ == "__main__":
    sys.exit(main())
