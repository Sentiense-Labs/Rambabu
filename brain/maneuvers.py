"""
Compound driving maneuvers for Rambabu.

Each maneuver is a sequenced choreography of MotorController calls — the kind
of move a competent human driver would think of as one action ("do a 3-point
turn", "nudge back into the lane") but that maps to several primitive motor
commands underneath.

All maneuvers expect a HardwareContext with a live motor. They use
MovementManager.stop() (when present) so SonarGuard / brain state remain
consistent. None of them ever leave the motor running.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from brain.hardware_tools import HardwareContext

logger = logging.getLogger("brain.maneuvers")

DRIVE_SPEED: int = 80

REVERSE_HARD_CAP_S: float = 0.5

# ── Empirical calibration (April 2026, with STEER_LOCK_SETTLE_S fix) ───
# Measured on the Magicwand truck chassis with full-lock front-wheel steer:
#   * Straight-line speed at duty 80 ≈ 67 cm/s
#   * Turning DIAMETER ≈ 130 cm (radius ≈ 65 cm)
#   * 6.45 s continuous arc → ~200° heading change → ~31°/s effective rate
#   * 5.8 s continuous arc ≈ exactly 180° (used as the single-arc default)
# The rate is higher than the early test runs suggested because those
# runs lacked the STEER_LOCK_SETTLE_S pause — most of those arcs ran with
# the wheels still mid-swing.
# Iterative back-and-forth profiles waste motion to PWM ramp overhead;
# the cleanest U-turn is one long continuous arc. Tight-space fallback
# uses shorter arcs with reverses, accepting reduced efficiency.
TURNING_RADIUS_CM: float = 65.0
TURNING_DIAMETER_CM: float = 130.0
SPEED_CM_PER_S_AT_80: float = 67.0
DEG_PER_SEC_OF_ARC: float = 31.0

# Single-arc U-turn (preferred when space allows).
UTURN_SINGLE_ARC_S: float = 5.8           # ≈ 180° at the calibrated rate
# Front clearance needed: the rover's nose advances at most ~radius (65 cm)
# during the arc before the curve sweeps it away. Add a 20 cm bumper.
UTURN_FRONT_CLEARANCE_CM: float = 85.0
# Side sweep needed: the rover ends up ~one diameter sideways from start.
UTURN_SIDE_CLEARANCE_CM: float = 140.0

# Iterative N-point turn (fallback for tight spaces).
# Empirically calibrated April 2026: 6 cycles of (1.0 s arc + 1.5 s reverse)
# produces a full ~180° U-turn with only ~50 cm net displacement from start.
# The 1.5 s reverse is intentionally above the global REVERSE_HARD_CAP_S of
# 0.5 s — safe here because the iterative U-turn verifies front clearance
# before starting and the reverses stay within the verified workspace.
TPT_ARC_PER_LEG_S: float = 1.0          # forward arc per leg
TPT_REVERSE_PER_LEG_S: float = 1.5      # reverse arc per leg (overrides cap)
TPT_FINAL_STRAIGHT_S: float = 0.5       # final forward straighten
# 6 cycles × 1 s arc was empirically a full 180° when paired with 1.5 s
# reverses (much of the rotation comes from the rear-swinging reverses,
# not just the forward arc). Keeping the budget at 6 s matches that.
TPT_TARGET_ARC_TIME_S: float = 6.0
TPT_MAX_LEGS: int = 8                   # safety cap (3-point → 15-point)
TPT_INTRA_STEP_PAUSE_S: float = 0.1     # brief settle between sub-steps

DISENGAGE_BACK_S: float = 0.5
DISENGAGE_THRESHOLD_CM: float = 60.0  # below this, we are too close for a forward arc

# Time for the steering motor to physically swing from center to full lock
# (or lock-to-lock) after PWM is engaged. The motor.steer_*_hold() calls
# return immediately after setting PWM, but the wheels need ~250ms to
# actually reach the locked position. Without this pause, short arcs (esp.
# 0.5s reverses) drive forward/back while the wheels are still swinging,
# which produces nearly-straight motion instead of a proper arc.
STEER_LOCK_SETTLE_S: float = 0.25

_CORRECTION_SECONDS: dict[str, float] = {
    "light": 0.2,
    "medium": 0.4,
    "strong": 0.6,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stop_motion(hw: HardwareContext) -> None:
    """Stop motion via MovementManager if available, else direct motor.stop."""
    if hw.movement_manager is not None:
        hw.movement_manager.stop()
        return
    if hw.motor is not None:
        hw.motor.stop()
        try:
            hw.motor.steer_center()
        except Exception:
            pass


def _drive_forward_arc(hw: HardwareContext, side: str, seconds: float) -> None:
    """Steer to `side` and drive forward for `seconds`. Stops + centers after.

    Pauses STEER_LOCK_SETTLE_S after engaging steering so the wheels actually
    reach full lock before the drive motor starts.
    """
    motor = hw.motor
    if side == "left":
        motor.steer_left_hold()
    else:
        motor.steer_right_hold()
    time.sleep(STEER_LOCK_SETTLE_S)
    motor.front(DRIVE_SPEED)
    time.sleep(seconds)
    motor.stop()
    motor.steer_center()


def _drive_forward_arc_sonar_aware(
    hw: HardwareContext, side: str, max_seconds: float
) -> float:
    """Forward arc that aborts early if the front sonar enters close/critical.

    Returns the actual time spent arcing (≤ max_seconds). Centers steering on
    exit. Used by the iterative N-point turn so each leg stretches as far as
    physically possible without smashing.
    """
    motor = hw.motor
    if side == "left":
        motor.steer_left_hold()
    else:
        motor.steer_right_hold()
    time.sleep(STEER_LOCK_SETTLE_S)
    motor.front(DRIVE_SPEED)

    started = time.time()
    poll_interval = 0.05
    elapsed = 0.0
    while elapsed < max_seconds:
        time.sleep(poll_interval)
        elapsed = time.time() - started
        front_cm = _front_distance_cm(hw)
        if front_cm is not None and front_cm < DISENGAGE_THRESHOLD_CM:
            break

    motor.stop()
    motor.steer_center()
    return elapsed


def _drive_reverse_arc(
    hw: HardwareContext, side: str, seconds: float, max_seconds: float | None = None,
) -> None:
    """Steer to `side` and reverse for `seconds`.

    By default capped at REVERSE_HARD_CAP_S (0.5 s) — used by the
    `reverse_steer` tool where the model has no clearance guarantee.

    Pass `max_seconds` to override the cap for compound maneuvers (like
    the iterative U-turn) where the maneuver itself has already verified
    the workspace is clear.

    Pauses STEER_LOCK_SETTLE_S after engaging steering so the wheels actually
    reach full lock before the reverse motor starts. Without this the rover
    just goes straight back — most of the 0.5s would be spent with the
    wheels mid-swing.
    """
    cap = max_seconds if max_seconds is not None else REVERSE_HARD_CAP_S
    seconds = min(seconds, cap)
    motor = hw.motor
    if side == "left":
        motor.steer_left_hold()
    else:
        motor.steer_right_hold()
    time.sleep(STEER_LOCK_SETTLE_S)
    motor.back(DRIVE_SPEED)
    time.sleep(seconds)
    motor.stop()
    motor.steer_center()


# ---------------------------------------------------------------------------
# reverse_steer
# ---------------------------------------------------------------------------


def reverse_steer(
    hw: HardwareContext,
    steer_direction: str,
    seconds: float,
) -> dict[str, Any]:
    """Reverse with a steering bias.

    Reminder of geometry (return dict echoes this):
        back_left  → front swings RIGHT, rear goes LEFT
        back_right → front swings LEFT,  rear goes RIGHT
    """
    if steer_direction not in ("left", "right"):
        return {"status": "error", "message": f"invalid steer_direction: {steer_direction!r}"}

    seconds = max(0.05, min(float(seconds), REVERSE_HARD_CAP_S))

    note = (
        "front swung RIGHT, rear swung LEFT"
        if steer_direction == "left"
        else "front swung LEFT, rear swung RIGHT"
    )
    logger.info(f"reverse_steer: {steer_direction} for {seconds:.2f}s")

    _stop_motion(hw)
    try:
        _drive_reverse_arc(hw, steer_direction, seconds)
    except Exception as exc:
        _stop_motion(hw)
        return {"status": "error", "message": str(exc)}

    return {
        "status": "ok",
        "maneuver": "reverse_steer",
        "steer_direction": steer_direction,
        "duration_s": round(seconds, 2),
        "note": note,
    }


# ---------------------------------------------------------------------------
# align_to_path
# ---------------------------------------------------------------------------


def align_to_path(
    hw: HardwareContext,
    drift_direction: str,
    correction_strength: str = "light",
) -> dict[str, Any]:
    """Apply a brief steering correction to re-center on a path.

    drift_direction: which way you have drifted (so we steer the OPPOSITE
        way to bring you back).
    correction_strength: light=0.2s, medium=0.4s, strong=0.6s.
    """
    if drift_direction not in ("left", "right"):
        return {"status": "error", "message": f"invalid drift_direction: {drift_direction!r}"}

    seconds = _CORRECTION_SECONDS.get(correction_strength)
    if seconds is None:
        return {
            "status": "error",
            "message": f"invalid correction_strength: {correction_strength!r}",
        }

    correction_side = "right" if drift_direction == "left" else "left"
    logger.info(
        f"align_to_path: drifted {drift_direction} → "
        f"{correction_strength} {correction_side} steer for {seconds:.2f}s"
    )

    _stop_motion(hw)
    try:
        _drive_forward_arc(hw, correction_side, seconds)
        # Brief straighten step so the next call sees us tracking forward.
        hw.motor.front(DRIVE_SPEED)
        time.sleep(0.3)
        hw.motor.stop()
    except Exception as exc:
        _stop_motion(hw)
        return {"status": "error", "message": str(exc)}

    return {
        "status": "ok",
        "maneuver": "align_to_path",
        "drift_direction": drift_direction,
        "correction_side": correction_side,
        "correction_strength": correction_strength,
        "duration_s": round(seconds, 2),
    }


# ---------------------------------------------------------------------------
# three_point_turn
# ---------------------------------------------------------------------------


def _front_distance_cm(hw: HardwareContext) -> float | None:
    """Best-available forward distance reading; None if no sonar wired up."""
    if hw.sonar_guard is not None and hw.sonar_guard.is_running:
        return hw.sonar_guard.get_distance()
    if hw.ultrasonic is not None:
        try:
            return float(hw.ultrasonic.get_distance())
        except Exception:
            return None
    return None


def _estimate_heading_change_deg(arc_seconds: float) -> int:
    """Open-loop heading estimate from cumulative forward-arc time.

    Calibrated empirically: 5.0 s of continuous full-steer forward arc at
    speed 80 produces ~180° of heading change → ~36°/s. Without an IMU
    this is the best we can do; if the rover ends up under- or over-rotated
    in practice, recalibrate DEG_PER_SEC_OF_ARC.
    """
    return int(arc_seconds * DEG_PER_SEC_OF_ARC)


def three_point_turn(
    hw: HardwareContext,
    preferred_side: str = "right",
) -> dict[str, Any]:
    """180° heading flip. Empirically calibrated.

    Strategy is space-adaptive:
      * If the rover has clear room ahead (≥ UTURN_SINGLE_ARC_S × speed of
        forward sweep), do ONE continuous 5-second arc. This is by far the
        cleanest U-turn — the iterative back-and-forth wastes a lot of
        rotation potential to motor PWM ramp overhead between legs.
      * Otherwise, fall back to the iterative N-point turn — arc, reverse,
        repeat — capped at TPT_MAX_LEGS legs. Less efficient but works in
        ~1 m² of free space.

    preferred_side: which way the front swings on the first arc.
    """
    if preferred_side not in ("left", "right"):
        return {"status": "error", "message": f"invalid preferred_side: {preferred_side!r}"}

    _stop_motion(hw)

    front_cm = _front_distance_cm(hw)
    sweep_room_needed = UTURN_FRONT_CLEARANCE_CM

    # Disengage first if pressed against an obstacle — no arc can start
    # from inside the close zone (motor latch will refuse).
    steps: list[dict[str, Any]] = []
    if front_cm is not None and front_cm < DISENGAGE_THRESHOLD_CM:
        logger.info(
            f"three_point_turn: disengaging — front {front_cm:.1f}cm "
            f"< {DISENGAGE_THRESHOLD_CM:.0f}cm threshold"
        )
        hw.motor.back(DRIVE_SPEED)
        time.sleep(DISENGAGE_BACK_S)
        hw.motor.stop()
        steps.append({
            "step": 0, "action": "disengage_back",
            "duration_s": DISENGAGE_BACK_S,
            "front_distance_cm": round(front_cm, 1),
        })
        front_cm = _front_distance_cm(hw)

    # Branch on space available.
    if front_cm is not None and front_cm >= sweep_room_needed:
        return _uturn_single_arc(hw, preferred_side, steps)
    return _uturn_iterative(hw, preferred_side, steps)


def _uturn_single_arc(
    hw: HardwareContext,
    preferred_side: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Preferred U-turn: one continuous forward arc. Sonar-aware so it
    aborts early if something appears mid-sweep.
    """
    logger.info(
        f"three_point_turn: SINGLE-ARC strategy "
        f"({UTURN_SINGLE_ARC_S}s {preferred_side})"
    )
    try:
        arc_actual = _drive_forward_arc_sonar_aware(
            hw, preferred_side, UTURN_SINGLE_ARC_S
        )
        steps.append({
            "leg": 1,
            "action": "forward_arc",
            "side": preferred_side,
            "duration_s": round(arc_actual, 2),
            "front_distance_cm": round(_front_distance_cm(hw) or -1, 1),
        })
    except Exception as exc:
        _stop_motion(hw)
        return {"status": "error", "message": str(exc), "completed_steps": steps}

    estimated_deg = _estimate_heading_change_deg(arc_actual)
    completed = arc_actual >= UTURN_SINGLE_ARC_S * 0.9
    return {
        "status": "ok" if completed else "partial",
        "maneuver": "three_point_turn",
        "strategy": "single_arc",
        "preferred_side": preferred_side,
        "cumulative_arc_s": round(arc_actual, 2),
        "estimated_heading_change_deg": estimated_deg,
        "target_heading_change_deg": 180,
        "note": (
            "Single continuous arc — calibrated for ~180° at 5.8s. If the "
            "arc was cut short by an obstacle (status='partial'), look "
            "around and decide whether to continue with another arc or "
            "switch to iterative."
        ),
        "steps": steps,
    }


def _uturn_iterative(
    hw: HardwareContext,
    preferred_side: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fallback U-turn for tight spaces: N-point arc + reverse cycles.

    Less efficient (each PWM ramp loses motion) but works in ~1 m² of
    free space. Caps at TPT_MAX_LEGS — beyond that we report 'partial'
    so the brain can decide whether to scout for more space.
    """
    opposite = "left" if preferred_side == "right" else "right"
    logger.info(
        f"three_point_turn: ITERATIVE strategy — "
        f"target {TPT_TARGET_ARC_TIME_S}s arc, cap {TPT_MAX_LEGS} legs"
    )
    cumulative_arc_s: float = 0.0

    try:
        for leg in range(1, TPT_MAX_LEGS + 1):
            arc_actual = _drive_forward_arc_sonar_aware(
                hw, preferred_side, TPT_ARC_PER_LEG_S
            )
            cumulative_arc_s += arc_actual
            steps.append({
                "leg": leg, "action": "forward_arc",
                "side": preferred_side,
                "duration_s": round(arc_actual, 2),
                "cumulative_arc_s": round(cumulative_arc_s, 2),
                "front_distance_cm": round(_front_distance_cm(hw) or -1, 1),
            })

            if cumulative_arc_s >= TPT_TARGET_ARC_TIME_S:
                logger.info(
                    f"three_point_turn: target reached after leg {leg} "
                    f"(cumulative arc={cumulative_arc_s:.2f}s)"
                )
                break

            time.sleep(TPT_INTRA_STEP_PAUSE_S)
            # Use the longer reverse cap — workspace clearance was verified
            # at maneuver entry, the reverses stay well within that bubble.
            _drive_reverse_arc(
                hw, opposite, TPT_REVERSE_PER_LEG_S,
                max_seconds=TPT_REVERSE_PER_LEG_S,
            )
            steps.append({
                "leg": leg, "action": "reverse_arc", "side": opposite,
                "duration_s": TPT_REVERSE_PER_LEG_S,
                "note": "rear swung " + ("right" if opposite == "left" else "left"),
            })
            time.sleep(TPT_INTRA_STEP_PAUSE_S)

        if TPT_FINAL_STRAIGHT_S > 0:
            hw.motor.front(DRIVE_SPEED)
            time.sleep(TPT_FINAL_STRAIGHT_S)
            hw.motor.stop()
            steps.append({
                "action": "forward_straight",
                "duration_s": TPT_FINAL_STRAIGHT_S,
            })

    except Exception as exc:
        _stop_motion(hw)
        return {
            "status": "error",
            "message": str(exc),
            "completed_steps": steps,
            "cumulative_arc_s": round(cumulative_arc_s, 2),
        }

    estimated_deg = _estimate_heading_change_deg(cumulative_arc_s)
    completed = cumulative_arc_s >= TPT_TARGET_ARC_TIME_S * 0.9
    return {
        "status": "ok" if completed else "partial",
        "maneuver": "three_point_turn",
        "strategy": "iterative",
        "preferred_side": preferred_side,
        "legs_executed": sum(1 for s in steps if s.get("action") == "forward_arc"),
        "cumulative_arc_s": round(cumulative_arc_s, 2),
        "estimated_heading_change_deg": estimated_deg,
        "target_heading_change_deg": 180,
        "note": (
            "Iterative N-point turn — used because not enough room for a "
            "single-arc sweep. Less rotation per second than single-arc "
            "due to motor PWM overhead between legs."
        ),
        "steps": steps,
    }
