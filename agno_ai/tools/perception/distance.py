from agno_ai import get_hw
from agno_ai.middleware.logging import with_logging
from agno_ai.middleware.timeout import with_timeout
from agno_ai import constants as C


def _zone(distance_cm: float) -> str:
    if distance_cm < 20:
        return "critical"
    if distance_cm < C.ZONE_CLOSE_CM:
        return "close"
    if distance_cm < C.ZONE_MEDIUM_CM:
        return "medium"
    return "clear"


@with_logging
@with_timeout(seconds=C.TIMEOUT_DISTANCE)
def distance(sensor: str = "front", run_context=None) -> str:
    """Read ultrasonic distance in cm + zone label.

    sensor: "front" (default) or "rear"
    Zones: critical (<20cm), close (<70cm), medium (<150cm), clear (>=150cm)
    Call this regularly when moving to decide when to stop or maneuver.
    """
    hw = get_hw()
    if hw is None:
        return '{"status": "error", "message": "no hardware context"}'

    try:
        if sensor == "rear":
            if hw.rear_ultrasonic is None:
                return '{"status": "error", "message": "rear ultrasonic not available"}'
            distance_cm = hw.rear_ultrasonic.get_distance()
            zone = _zone(distance_cm)
        else:
            # Front sensor — prefer SonarGuard for averaged/hysteresis reading
            if hw.sonar_guard is not None and hw.sonar_guard.is_running:
                distance_cm, zone = hw.sonar_guard.snapshot()
            elif hw.ultrasonic is not None:
                distance_cm = hw.ultrasonic.get_distance()
                zone = _zone(distance_cm)
            else:
                return '{"status": "error", "message": "no front sonar available"}'

        if run_context is not None and hasattr(run_context, "session_state"):
            run_context.session_state.set("zone", zone)
            run_context.session_state.set("distance_cm", distance_cm)

        return f"sensor: {sensor}\ndistance_cm: {distance_cm:.1f}\nzone: {zone}"
    except Exception as exc:
        return f'{{"status": "error", "message": "{exc}"}}'
