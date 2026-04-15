from agno.middleware.logging import with_logging
from agno.middleware.timeout import with_timeout
from agno_ai.types.context import HardwareContext
from agno_ai import constants as C


def _get_hw(run_context=None) -> HardwareContext | None:
    if run_context is None:
        return None
    return run_context.session_state.get("hw")


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
def distance(run_context=None) -> str:
    """Read forward ultrasonic distance in cm + zone label.
    When SonarGuard is running it is the canonical reader.
    """
    hw = _get_hw(run_context)
    if hw is None:
        return '{"status": "error", "message": "no hardware context"}'

    try:
        if hw.sonar_guard is not None and hw.sonar_guard.is_running:
            distance_cm, zone = hw.sonar_guard.snapshot()
            run_context.session_state.set("zone", zone)
            run_context.session_state.set("distance_cm", distance_cm)
        elif hw.ultrasonic is not None:
            distance_cm = hw.ultrasonic.get_distance()
            zone = _zone(distance_cm)
            run_context.session_state.set("zone", zone)
            run_context.session_state.set("distance_cm", distance_cm)
        else:
            return '{"status": "error", "message": "no sonar available"}'

        return f"distance_cm: {distance_cm:.1f}\nzone: {zone}"
    except Exception as exc:
        return f'{{"status": "error", "message": "{exc}"}}'
