#!/usr/bin/env python3
"""Steering profile tester — structured in three phases.

WORKFLOW
────────
Phase 1 — Range sweep (run first)
    Find how long 100% duty needs to run to reach full steering lock.
    Run range-* profiles in order until the wheels reach full lock.
    Note that profile name, then set FULL_LOCK_S below and move to Phase 2.

Phase 2 — Center return (run after Phase 1)
    Confirm the wheels return cleanly to center after full-lock.
    Profiles try passive coast, then progressively stronger counter-steer.

Phase 3 — Smoothness (run after Phase 2)
    Add a ramp in/out so the motor starts and stops smoothly.
    Only needed if Phase 2 result has mechanical jerk.

──────────────────────────────────────────────────────────────────────────────
EDIT THIS after Phase 1:
    Set FULL_LOCK_S to the steer_duration of the first profile that
    reached full steering lock. Phase 2 & 3 profiles use this value.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

FULL_LOCK_S: float = 0.50   # ← UPDATE after Phase 1 (seconds to reach full lock)

# ──────────────────────────────────────────────────────────────────────────────

import argparse
import sys
import time
from dataclasses import dataclass

import RPi.GPIO as GPIO

from config import MOTOR_STEER_LEFT, MOTOR_STEER_RIGHT

STEER_PWM_FREQ = 100   # Hz — 100 Hz is within L9110S spec and avoids coil whine


# ---------------------------------------------------------------------------
# Profile definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SteerProfile:
    """One complete parameter set for LEFT → CENTER → RIGHT → CENTER."""

    name: str
    description: str

    # Steer parameters
    steer_duty: int          # % — how hard to push into the turn
    steer_duration: float    # s — how long to hold at full steer

    # Centering parameters
    return_duty: int         # % — counter-steer duty when returning to center
    return_duration: float   # s — how long to counter-steer

    # Brake and settle
    brake_duration: float    # s — both LOW = motor shorted to GND (L9110S brake)
    center_hold: float       # s — dwell at center so wheels physically settle

    # Ramp (0 steps = instant, no ramp)
    ramp_steps: int          # number of ramp increments each side
    ramp_step_time: float    # s per step


# ---------------------------------------------------------------------------
# Profile catalogue
# ---------------------------------------------------------------------------
#
# ── Phase 1 ─────────────────────────────────────────────────────────────────
# R1  range-300ms    100% × 300 ms  — start here, note range achieved
# R2  range-500ms    100% × 500 ms
# R3  range-700ms    100% × 700 ms
# R4  range-1000ms   100% × 1000 ms
# R5  range-1500ms   100% × 1500 ms — if still not at full lock, check hardware
#
# ── Phase 2 ─────────────────────────────────────────────────────────────────
# C1  center-passive  No counter-steer — do the wheels spring back on their own?
# C2  center-short    Short return pulse (undershoot check)
# C3  center-medium   Medium return pulse — balanced starting point
# C4  center-long     Long return pulse (if wheels stop short of center)
# C5  center-strong   Higher return duty (if medium return is too weak)
#
# ── Phase 3 ─────────────────────────────────────────────────────────────────
# S1  smooth-ramp-3   3-step ramp in/out — quick smoothing
# S2  smooth-ramp-5   5-step ramp in/out — smoother, more gradual

def _p(  # noqa: PLR0913 — builder keeps profile table readable
    name: str,
    description: str,
    steer_duty: int,
    steer_duration: float,
    return_duty: int,
    return_duration: float,
    brake_duration: float = 0.08,
    center_hold: float = 0.70,
    ramp_steps: int = 0,
    ramp_step_time: float = 0.0,
) -> SteerProfile:
    return SteerProfile(
        name=name,
        description=description,
        steer_duty=steer_duty,
        steer_duration=steer_duration,
        return_duty=return_duty,
        return_duration=return_duration,
        brake_duration=brake_duration,
        center_hold=center_hold,
        ramp_steps=ramp_steps,
        ramp_step_time=ramp_step_time,
    )


def _build_profiles() -> dict[str, SteerProfile]:
    fl = FULL_LOCK_S  # alias for readability in Phase 2/3 rows

    return {
        # ── Phase 1: Range sweep ──────────────────────────────────────────────
        # Return_duty=0 → passive coast only (no counter-steer).
        # Observe how far the wheels turn. Stop when you see full lock.
        "range-300ms": _p(
            "range-300ms",
            "[Phase 1] 100% duty × 300ms. Note range — is it full lock?",
            steer_duty=100, steer_duration=0.30,
            return_duty=0,  return_duration=0.0,
            center_hold=1.00,
        ),
        "range-500ms": _p(
            "range-500ms",
            "[Phase 1] 100% duty × 500ms.",
            steer_duty=100, steer_duration=0.50,
            return_duty=0,  return_duration=0.0,
            center_hold=1.00,
        ),
        "range-700ms": _p(
            "range-700ms",
            "[Phase 1] 100% duty × 700ms.",
            steer_duty=100, steer_duration=0.70,
            return_duty=0,  return_duration=0.0,
            center_hold=1.00,
        ),
        "range-1000ms": _p(
            "range-1000ms",
            "[Phase 1] 100% duty × 1000ms.",
            steer_duty=100, steer_duration=1.00,
            return_duty=0,  return_duration=0.0,
            center_hold=1.00,
        ),
        "range-1500ms": _p(
            "range-1500ms",
            "[Phase 1] 100% duty × 1500ms. If still no full lock — check hardware voltage.",
            steer_duty=100, steer_duration=1.50,
            return_duty=0,  return_duration=0.0,
            center_hold=1.00,
        ),

        # ── Phase 2: Center return ────────────────────────────────────────────
        # Uses FULL_LOCK_S from top of file. Set that first!
        "center-passive": _p(
            "center-passive",
            "[Phase 2] Full lock, NO counter-steer. Do wheels spring back on their own?",
            steer_duty=100, steer_duration=fl,
            return_duty=0,  return_duration=0.0,
            center_hold=1.20,
        ),
        "center-short": _p(
            "center-short",
            "[Phase 2] Short counter-steer (30% × 120ms). Use if passive overshoot.",
            steer_duty=100, steer_duration=fl,
            return_duty=30, return_duration=0.12,
            center_hold=0.80,
        ),
        "center-medium": _p(
            "center-medium",
            "[Phase 2] Medium counter-steer (45% × 200ms). Balanced starting point.",
            steer_duty=100, steer_duration=fl,
            return_duty=45, return_duration=0.20,
            center_hold=0.60,
        ),
        "center-long": _p(
            "center-long",
            "[Phase 2] Long counter-steer (45% × 320ms). Use if wheels stop short of center.",
            steer_duty=100, steer_duration=fl,
            return_duty=45, return_duration=0.32,
            center_hold=0.60,
        ),
        "center-strong": _p(
            "center-strong",
            "[Phase 2] Strong counter-steer (65% × 200ms). Use if medium return is too weak.",
            steer_duty=100, steer_duration=fl,
            return_duty=65, return_duration=0.20,
            center_hold=0.60,
        ),

        # ── Phase 3: Smoothness ───────────────────────────────────────────────
        # Copy return_duty/return_duration from whichever Phase 2 profile worked.
        "smooth-ramp-3": _p(
            "smooth-ramp-3",
            "[Phase 3] 3-step ramp in/out. Quick smoothing, minimal added time.",
            steer_duty=100, steer_duration=fl,
            return_duty=45, return_duration=0.20,
            center_hold=0.60,
            ramp_steps=3,   ramp_step_time=0.030,
        ),
        "smooth-ramp-5": _p(
            "smooth-ramp-5",
            "[Phase 3] 5-step ramp in/out. Smoothest motion, lowest mechanical stress.",
            steer_duty=100, steer_duration=fl,
            return_duty=45, return_duration=0.20,
            center_hold=0.60,
            ramp_steps=5,   ramp_step_time=0.025,
        ),
    }


PROFILES: dict[str, SteerProfile] = _build_profiles()


# ---------------------------------------------------------------------------
# GPIO helpers
# ---------------------------------------------------------------------------


def setup_gpio() -> tuple[GPIO.PWM, GPIO.PWM]:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(MOTOR_STEER_LEFT, GPIO.OUT)
    GPIO.setup(MOTOR_STEER_RIGHT, GPIO.OUT)
    GPIO.output(MOTOR_STEER_LEFT, GPIO.LOW)
    GPIO.output(MOTOR_STEER_RIGHT, GPIO.LOW)
    pwm_left = GPIO.PWM(MOTOR_STEER_LEFT, STEER_PWM_FREQ)
    pwm_right = GPIO.PWM(MOTOR_STEER_RIGHT, STEER_PWM_FREQ)
    pwm_left.start(0)
    pwm_right.start(0)
    return pwm_left, pwm_right


def cleanup(
    pwm_left: GPIO.PWM | None = None, pwm_right: GPIO.PWM | None = None
) -> None:
    try:
        if pwm_left and pwm_right:
            pwm_left.ChangeDutyCycle(0)
            pwm_right.ChangeDutyCycle(0)
            GPIO.output(MOTOR_STEER_LEFT, GPIO.LOW)
            GPIO.output(MOTOR_STEER_RIGHT, GPIO.LOW)
            pwm_left.stop()
            pwm_right.stop()
    except Exception:
        pass
    try:
        GPIO.cleanup()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Motion primitives (profile-driven)
# ---------------------------------------------------------------------------


def _ramp(pwm: GPIO.PWM, from_duty: float, to_duty: float, p: SteerProfile) -> None:
    if p.ramp_steps == 0:
        pwm.ChangeDutyCycle(to_duty)
        return
    for step in range(1, p.ramp_steps + 1):
        duty = from_duty + (to_duty - from_duty) * step / p.ramp_steps
        pwm.ChangeDutyCycle(duty)
        time.sleep(p.ramp_step_time)


def _hard_brake(pwm_left: GPIO.PWM, pwm_right: GPIO.PWM, p: SteerProfile) -> None:
    """L9110S dynamic brake: both inputs LOW → both outputs LOW → motor shorted to GND.

    Do NOT use both-HIGH on L9110S — putting both outputs at VCC simultaneously
    triggers overcurrent protection and causes the driver LED to blink.
    Both-LOW is the correct brake for this IC.
    """
    pwm_left.ChangeDutyCycle(0)
    pwm_right.ChangeDutyCycle(0)
    GPIO.output(MOTOR_STEER_LEFT, GPIO.LOW)
    GPIO.output(MOTOR_STEER_RIGHT, GPIO.LOW)
    time.sleep(p.brake_duration)


def step_steer_left(pwm_left: GPIO.PWM, pwm_right: GPIO.PWM, p: SteerProfile) -> None:
    """Apply left steer only. Wheels remain left — CENTER step must follow."""
    pwm_left.ChangeDutyCycle(0)
    pwm_right.ChangeDutyCycle(0)
    _ramp(pwm_right, 0, p.steer_duty, p)
    time.sleep(p.steer_duration)
    _ramp(pwm_right, p.steer_duty, 0, p)
    pwm_right.ChangeDutyCycle(0)


def step_steer_right(pwm_left: GPIO.PWM, pwm_right: GPIO.PWM, p: SteerProfile) -> None:
    """Apply right steer only. Wheels remain right — CENTER step must follow."""
    pwm_left.ChangeDutyCycle(0)
    pwm_right.ChangeDutyCycle(0)
    _ramp(pwm_left, 0, p.steer_duty, p)
    time.sleep(p.steer_duration)
    _ramp(pwm_left, p.steer_duty, 0, p)
    pwm_left.ChangeDutyCycle(0)


def step_center(
    pwm_left: GPIO.PWM,
    pwm_right: GPIO.PWM,
    coming_from: str,
    p: SteerProfile,
) -> None:
    """Actively return to center from the given steer direction.

    coming_from: "LEFT" or "RIGHT"

    1. Counter-steer at return_duty for return_duration (pushes wheels back).
    2. Hard-brake — stops motor dead at center.
    3. Hold center_hold — wheels physically settle before next steer.
    """
    if p.return_duty == 0 or p.return_duration == 0.0:
        # Passive coast — no counter-steer, just brake and hold
        _hard_brake(pwm_left, pwm_right, p)
        time.sleep(p.center_hold)
        return

    if coming_from == "LEFT":
        # Wheels turned left → counter-steer right channel to return
        pwm_left.ChangeDutyCycle(0)
        pwm_right.ChangeDutyCycle(0)
        pwm_left.ChangeDutyCycle(p.return_duty)
        time.sleep(p.return_duration)
        pwm_left.ChangeDutyCycle(0)
    else:
        # Wheels turned right → counter-steer left channel to return
        pwm_left.ChangeDutyCycle(0)
        pwm_right.ChangeDutyCycle(0)
        pwm_right.ChangeDutyCycle(p.return_duty)
        time.sleep(p.return_duration)
        pwm_right.ChangeDutyCycle(0)

    _hard_brake(pwm_left, pwm_right, p)
    time.sleep(p.center_hold)


# ---------------------------------------------------------------------------
# Profile runner
# ---------------------------------------------------------------------------


# Explicit cycle: steer, center, steer the other way, center
_CYCLE: list[tuple[str, str | None]] = [
    ("LEFT",   None),
    ("CENTER", "LEFT"),
    ("RIGHT",  None),
    ("CENTER", "RIGHT"),
]


def _profile_header(p: SteerProfile) -> None:
    ramp_time = p.ramp_steps * p.ramp_step_time
    steer_step = ramp_time + p.steer_duration + ramp_time
    center_step = p.return_duration + p.brake_duration + p.center_hold
    cycle_s = steer_step + center_step  # one steer + one center

    print(f"\n{'=' * 65}")
    print(f"  PROFILE: {p.name}")
    print(f"  {p.description}")
    print(f"{'=' * 65}")
    print(f"  steer    : duty={p.steer_duty}%  duration={p.steer_duration * 1000:.0f}ms")
    if p.ramp_steps:
        print(f"  ramp     : {p.ramp_steps} steps × {p.ramp_step_time * 1000:.0f}ms = {ramp_time * 1000:.0f}ms each side")
    else:
        print(f"  ramp     : none (instant)")
    if p.return_duty:
        print(f"  return   : duty={p.return_duty}%  duration={p.return_duration * 1000:.0f}ms")
    else:
        print(f"  return   : passive coast (no counter-steer)")
    print(f"  brake    : {p.brake_duration * 1000:.0f}ms hard-brake")
    print(f"  hold     : {p.center_hold * 1000:.0f}ms at center")
    print(f"  ~half-cycle: {cycle_s * 1000:.0f}ms  (steer {steer_step * 1000:.0f}ms + center {center_step * 1000:.0f}ms)")
    print(f"{'=' * 65}")
    print(f"  Sequence: LEFT → CENTER → RIGHT → CENTER → ...")
    print(f"{'=' * 65}")


def run_profile(
    pwm_left: GPIO.PWM, pwm_right: GPIO.PWM, p: SteerProfile, cycles: int
) -> None:
    """Run `cycles` complete LEFT→C→RIGHT→C cycles for the given profile."""
    _profile_header(p)

    # Initialise at center
    _hard_brake(pwm_left, pwm_right, p)
    time.sleep(p.center_hold)

    step_num = 0
    start = time.time()

    for cycle in range(1, cycles + 1):
        print(f"\n  -- Cycle {cycle}/{cycles} --")
        for action, coming_from in _CYCLE:
            elapsed = time.time() - start
            step_num += 1
            if action == "LEFT":
                print(f"  [{elapsed:.1f}s] step {step_num}: STEER LEFT")
                step_steer_left(pwm_left, pwm_right, p)
            elif action == "RIGHT":
                print(f"  [{elapsed:.1f}s] step {step_num}: STEER RIGHT")
                step_steer_right(pwm_left, pwm_right, p)
            else:
                print(f"  [{elapsed:.1f}s] step {step_num}: CENTER  (from {coming_from})")
                step_center(pwm_left, pwm_right, coming_from, p)

    elapsed = time.time() - start
    print(f"\n  Profile '{p.name}' done — {cycles} cycles in {elapsed:.1f}s")

    # Return to center and brief silence between profiles
    _hard_brake(pwm_left, pwm_right, p)
    time.sleep(0.8)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def list_profiles() -> None:
    phases = {
        "Phase 1 — Range sweep (find full-lock duration)": [
            k for k in PROFILES if k.startswith("range-")
        ],
        "Phase 2 — Center return (tune after Phase 1)": [
            k for k in PROFILES if k.startswith("center-")
        ],
        "Phase 3 — Smoothness (tune after Phase 2)": [
            k for k in PROFILES if k.startswith("smooth-")
        ],
    }

    col_w = 20
    for phase_title, keys in phases.items():
        print(f"\n{phase_title}")
        print("─" * 100)
        print(f"  {'name':<{col_w}} {'duty':>5} {'dur':>7} {'ret%':>5} {'retms':>6} {'hold':>6}  description")
        print(f"  {'─'*col_w} {'─'*5} {'─'*7} {'─'*5} {'─'*6} {'─'*6}")
        for k in keys:
            p = PROFILES[k]
            print(
                f"  {p.name:<{col_w}} {p.steer_duty:>5}% {p.steer_duration * 1000:>6.0f}ms"
                f" {p.return_duty:>5}% {p.return_duration * 1000:>5.0f}ms"
                f" {p.center_hold * 1000:>5.0f}ms  {p.description}"
            )

    print(f"\n  FULL_LOCK_S = {FULL_LOCK_S}s  (edit top of file after Phase 1)")
    print()
    print("Tuning guide:")
    print("  Phase 1: run range-* in order, stop at the first one that reaches full lock")
    print("  Phase 2: set FULL_LOCK_S, then run center-* to find a clean return")
    print("  Phase 2: wheels stop short of center  → try center-long or center-strong")
    print("  Phase 2: wheels overshoot center      → try center-short")
    print("  Phase 2: wheels return on their own   → center-passive is enough")
    print("  Phase 3: run smooth-ramp-* if you want gradual start/stop")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Steering profile tester — three-phase workflow (range → center → smooth)"
    )
    parser.add_argument("--list", action="store_true", help="List all profiles and exit")
    parser.add_argument(
        "--profile",
        choices=list(PROFILES),
        help="Run a single named profile",
    )
    parser.add_argument(
        "--phase",
        choices=["1", "2", "3"],
        help="Run all profiles in a phase (1=range, 2=center, 3=smooth)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run every profile in order",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="Number of LEFT→C→RIGHT→C cycles per profile (default 3)",
    )
    args = parser.parse_args()

    if args.list:
        list_profiles()
        return 0

    phase_map = {
        "1": [k for k in PROFILES if k.startswith("range-")],
        "2": [k for k in PROFILES if k.startswith("center-")],
        "3": [k for k in PROFILES if k.startswith("smooth-")],
    }

    to_run: list[SteerProfile] = []
    if args.all:
        to_run = list(PROFILES.values())
    elif args.phase:
        to_run = [PROFILES[k] for k in phase_map[args.phase]]
    elif args.profile:
        to_run = [PROFILES[args.profile]]
    else:
        parser.print_help()
        print("\nError: specify --profile NAME, --phase 1|2|3, or --all", file=sys.stderr)
        return 2

    print("\n=== Steering Profile Tester ===")
    print(f"GPIO {MOTOR_STEER_LEFT} → Left channel  |  GPIO {MOTOR_STEER_RIGHT} → Right channel")
    print(f"Profiles to run : {len(to_run)}")
    print(f"Cycles each     : {args.cycles}")
    print(f"FULL_LOCK_S     : {FULL_LOCK_S}s")

    pwm_left = pwm_right = None
    try:
        pwm_left, pwm_right = setup_gpio()

        for p in to_run:
            run_profile(pwm_left, pwm_right, p, args.cycles)
            if len(to_run) > 1:
                print(f"\n  [pause 1.5s before next profile]")
                time.sleep(1.5)

        print("\n=== Done ===")
        if args.phase == "1":
            print("Next: edit FULL_LOCK_S at the top of this file, then run --phase 2")
        elif args.phase == "2":
            print("Next: copy return_duty/return_duration from the best profile into smooth-ramp-*, then run --phase 3")
        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 0
    except Exception as e:
        print(f"\nFailed: {e}", file=sys.stderr)
        return 1
    finally:
        cleanup(pwm_left, pwm_right)


if __name__ == "__main__":
    sys.exit(main())
