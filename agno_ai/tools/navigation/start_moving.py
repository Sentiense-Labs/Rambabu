from agno_ai import get_hw
from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai import constants as C

_FORWARD_FAMILY = frozenset({"forward", "left", "right"})


def _zone(d: float) -> str:
    if d < C.ZONE_CRITICAL_CM:
        return "critical"
    if d < C.ZONE_CLOSE_CM:
        return "close"
    if d < C.ZONE_MEDIUM_CM:
        return "medium"
    return "clear"


@with_logging
@with_timeout(seconds=C.TIMEOUT_START_MOVING)
def start_moving(direction: str, speed: int = C.DEFAULT_SPEED, run_context=None) -> str:
    """Begin continuous movement. Returns immediately — motor runs until
    stop_moving() is called. Call distance() periodically to monitor surroundings
    and decide when to stop or change direction.
    """
    hw = get_hw()
    if hw is None or hw.motor is None:
        return '{"status": "error", "message": "motor not available"}'
    if direction not in {"forward", "back", "left", "right"}:
        return f'{{"status": "error", "message": "invalid direction: {direction}"}}'

    # Preflight distance check for forward-family moves
    if direction in _FORWARD_FAMILY:
        dist_cm: float | None = None
        zone: str | None = None
        if hw.sonar_guard is not None and hw.sonar_guard.is_running:
            dist_cm, zone = hw.sonar_guard.snapshot()
        elif hw.ultrasonic is not None:
            dist_cm = hw.ultrasonic.get_distance()
            zone = _zone(dist_cm)
        if zone == "critical" and dist_cm is not None:
            return (
                f'{{"status": "blocked", "reason": "obstacle_in_path", '
                f'"distance_cm": {dist_cm:.1f}, "zone": "{zone}", '
                f'"message": "Path is {zone} ({dist_cm:.0f}cm). '
                f'Call move(\\"back\\", 0.5) to disengage then look_around."}}'
            )

    speed = max(0, min(int(speed), 100))

    if direction == "forward":
        result = hw.motor.front(speed)
    elif direction == "back":
        result = hw.motor.back(speed)
    elif direction == "left":
        hw.motor.steer_left_hold()
        result = hw.motor.front(speed)
    else:  # right
        hw.motor.steer_right_hold()
        result = hw.motor.front(speed)

    if result.get("status") == "ok":
        return (
            f'{{"status": "running", "direction": "{direction}", "speed": {speed}, '
            f'"note": "Motor running. Call distance() to monitor and stop_moving() when done."}}'
        )
    return str(result)
