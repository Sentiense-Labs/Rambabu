"""
move_cm — distance-aware discrete move.

The agent specifies how far to travel in centimetres. The tool converts to
seconds using the calibrated speed constant, checks the front/rear sonar
before executing, caps the requested distance so it cannot overshoot the
nearest obstacle, then runs the motor and returns immediately (non-blocking).

At duty cycle 80 (DRIVE_SPEED), the rover travels ~56 cm/s (BASE_SPEED_CM_PER_S).

Max single move: 10 s × 56 cm/s = 560 cm (~5.6 m). Sufficient for any room.
"""

from __future__ import annotations

import threading
import time

from agno_ai import get_hw
from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai import constants as C
from agno_ai.lib.nav_log import get_nav_log

_DRIVE_SPEED = C.DRIVE_SPEED    # forward / arc moves: 80% duty
_BACK_SPEED = C.REVERSE_DUTY    # all reverse moves: 100% duty
_SPEED: dict[str, float] = {
    "forward":    C.BASE_SPEED_CM_PER_S,             # 50.0 cm/s at 80%
    "back":       C.REVERSE_SPEED_100_CM_PER_S,      # 55.0 cm/s at 100% (estimated)
    "left":       C.TURN_LEFT_SPEED_CM_PER_S,        # 19.0 cm/s
    "right":      C.TURN_RIGHT_SPEED_CM_PER_S,       # 19.0 cm/s
    "back_left":  C.TURN_BACK_SPEED_CM_PER_S,        # 19.0 cm/s
    "back_right": C.TURN_BACK_SPEED_CM_PER_S,        # 19.0 cm/s
}
_STARTUP_OFFSET_S = C.MOTOR_STARTUP_OFFSET_S    # 0.40 s dead-time
_MAX_SECONDS = 10.0                              # absolute cap
_FRONT_BUFFER_CM = 30.0                         # stop this far from obstacle
_REAR_BUFFER_CM = 15.0                          # rear buffer (was 25; reduced so escape moves aren't tiny)

_FORWARD_FAMILY = frozenset({"forward", "left", "right"})
_BACKWARD_FAMILY = frozenset({"back", "back_left", "back_right"})
_VALID_DIRECTIONS = _FORWARD_FAMILY | _BACKWARD_FAMILY


@with_logging
@with_timeout(seconds=60.0)
def move_cm(direction: str, cm: float, run_context=None) -> str:
    """Move the rover a specific distance (cm) then stop automatically.

    Converts cm to seconds using calibrated speed (56 cm/s at duty 80).
    For forward moves, caps the distance so it cannot overshoot the sonar
    reading minus a 30 cm safety buffer. Returns immediately — motor runs
    in a background thread and auto-stops.

    direction: forward | back | left | right | back_left | back_right
    cm: distance to travel in centimetres (1–560 cm)
    """
    if direction not in _VALID_DIRECTIONS:
        return f'{{"status": "error", "message": "invalid direction: {direction}"}}'

    hw = get_hw()
    if hw is None or hw.motor is None:
        return '{"status": "error", "message": "motor not available"}'

    cm = max(1.0, float(cm))
    original_cm = cm

    # ── Forward-family: check front sonar ───────────────────────────────────
    if direction in _FORWARD_FAMILY:
        front_cm: float | None = None
        if hw.sonar_guard is not None and hw.sonar_guard.is_running:
            front_cm, zone = hw.sonar_guard.snapshot()
        elif hw.ultrasonic is not None:
            front_cm = float(hw.ultrasonic.get_distance())
            zone = _zone(front_cm)

        if front_cm is not None:
            if front_cm <= C.ZONE_CRITICAL_CM:
                get_nav_log().record(direction, original_cm, 0, "blocked", f"critical zone {front_cm:.0f}cm")
                return (
                    f'{{"status": "blocked", "reason": "critical_zone", '
                    f'"front_cm": {front_cm:.1f}, '
                    f'"message": "Front distance {front_cm:.0f} cm is critical. '
                    f'Check rear and back up before moving forward."}}'
                )
            # Cap distance only for straight forward — arc moves (left/right) turn
            # away from whatever is straight ahead, so the buffer cap doesn't apply.
            if direction == "forward":
                safe_cm = max(0.0, front_cm - _FRONT_BUFFER_CM)
                if cm > safe_cm:
                    cm = safe_cm
                    if cm <= 0:
                        get_nav_log().record(direction, original_cm, 0, "blocked", f"no safe distance, front {front_cm:.0f}cm")
                        return (
                            f'{{"status": "blocked", "reason": "no_safe_distance", '
                            f'"front_cm": {front_cm:.1f}, "requested_cm": {original_cm:.0f}, '
                            f'"message": "Not enough clearance to move forward safely."}}'
                        )

    # ── Backward-family: check rear sonar ────────────────────────────────────
    if direction in _BACKWARD_FAMILY:
        if hw.rear_ultrasonic is not None:
            rear_cm = float(hw.rear_ultrasonic.get_distance())
            if rear_cm <= C.ZONE_CRITICAL_CM:
                get_nav_log().record(direction, original_cm, 0, "blocked", f"rear critical {rear_cm:.0f}cm")
                return (
                    f'{{"status": "blocked", "reason": "rear_critical", '
                    f'"rear_cm": {rear_cm:.1f}, '
                    f'"message": "Rear distance {rear_cm:.0f} cm is critical. '
                    f'Cannot reverse safely."}}'
                )
            safe_rear = max(0.0, rear_cm - _REAR_BUFFER_CM)
            if cm > safe_rear:
                cm = safe_rear
                if cm <= 0:
                    get_nav_log().record(direction, original_cm, 0, "blocked", f"no safe rear distance, rear {rear_cm:.0f}cm")
                    return (
                        f'{{"status": "blocked", "reason": "no_safe_rear_distance", '
                        f'"rear_cm": {rear_cm:.1f}, "requested_cm": {original_cm:.0f}, '
                        f'"message": "Not enough rear clearance to reverse safely."}}'
                    )

    seconds = min(cm / _SPEED[direction] + _STARTUP_OFFSET_S, _MAX_SECONDS)
    if seconds <= 0.0:
        return '{"status": "ok", "action": "no-op", "reason": "zero_duration"}'

    run_result: dict = {"elapsed_s": 0.0, "sonar_stopped": False, "motor_refused": False}

    def _is_moving(motor) -> bool:
        return motor.is_moving_forward or motor.is_moving_backward

    def _run() -> None:
        motor = hw.motor
        start = time.monotonic()
        try:
            # Engage steering for arc directions
            if direction in ("left", "back_left"):
                motor.steer_left_hold()
            elif direction in ("right", "back_right"):
                motor.steer_right_hold()

            # Start motor
            if direction in _FORWARD_FAMILY:
                motor.front(_DRIVE_SPEED)
            else:
                result = motor.back(_BACK_SPEED)
                if isinstance(result, dict) and result.get("status") == "error":
                    run_result["motor_refused"] = True
                    run_result["elapsed_s"] = time.monotonic() - start
                    return

            # Poll instead of bare sleep — detect SonarGuard early stop
            _POLL = 0.05
            while time.monotonic() - start < seconds:
                time.sleep(_POLL)
                if not _is_moving(motor):
                    run_result["sonar_stopped"] = True
                    break

            motor.stop()

            # Re-center steering for arc directions
            if direction in ("left", "right", "back_left", "back_right"):
                motor.steer_center()
        except Exception:
            try:
                motor.stop()
            except Exception:
                pass
        finally:
            run_result["elapsed_s"] = time.monotonic() - start

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join()  # block until motor stops — enforces move-check-move rhythm

    # Let sonar stabilize after motor stop
    time.sleep(0.15)

    elapsed = run_result["elapsed_s"]
    sonar_stopped = run_result["sonar_stopped"]
    motor_refused = run_result["motor_refused"]
    cruise_s = max(0.0, elapsed - _STARTUP_OFFSET_S)
    estimated_cm = round(_SPEED[direction] * cruise_s)

    if motor_refused:
        get_nav_log().record(direction, original_cm, 0, "blocked", "rear obstacle latch", elapsed)
        return (
            f'{{"status": "blocked", "reason": "rear_obstacle_latch", '
            f'"requested_cm": {original_cm:.0f}, "estimated_cm": 0, '
            f'"duration_s": {elapsed:.2f}, '
            f'"note": "Motor refused reverse — rear obstacle latch active. '
            f'Clear the path or try distance(sensor=rear) to reset."}}'
        )

    if sonar_stopped:
        note = (
            f"SonarGuard stopped move early after {elapsed:.2f}s. "
            f"Estimated {estimated_cm} cm of {cm:.0f} cm covered. Obstacle ahead."
        )
        status = "sonar_stop"
        get_nav_log().record(direction, original_cm, estimated_cm, "sonar_stop", "obstacle ahead", elapsed)
    elif cm < original_cm - 0.5:
        note = f"Capped from {original_cm:.0f} cm to {cm:.0f} cm (obstacle buffer)."
        status = "done"
        estimated_cm = cm
        get_nav_log().record(direction, original_cm, estimated_cm, "capped", None, elapsed)
    else:
        note = f"Moved ~{estimated_cm} cm."
        status = "done"
        get_nav_log().record(direction, original_cm, estimated_cm, "done", None, elapsed)

    return (
        f'{{"status": "{status}", "direction": "{direction}", '
        f'"requested_cm": {original_cm:.0f}, "estimated_cm": {estimated_cm}, '
        f'"duration_s": {elapsed:.2f}, "note": "{note}"}}'
    )


def _zone(d: float) -> str:
    if d < C.ZONE_CRITICAL_CM:
        return "critical"
    if d < C.ZONE_CLOSE_CM:
        return "close"
    if d < C.ZONE_MEDIUM_CM:
        return "medium"
    return "clear"
