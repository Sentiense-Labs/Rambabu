from agno.middleware.logging import with_logging
from agno.middleware.timeout import with_timeout
from agno.types.context import HardwareContext
from agno import constants as C

import logging

logger = logging.getLogger("agno.tools")


def _get_hw(run_context=None) -> HardwareContext | None:
    if run_context is None:
        return None
    return run_context.session_state.get("hw")


def _update_session_state(run_context, hw: HardwareContext) -> None:
    if run_context is None or hw is None:
        return
    if hw.movement_manager is not None:
        snap = hw.movement_manager.snapshot()
        run_context.session_state.set("is_moving", snap.get("is_moving", False))
        run_context.session_state.set("direction", snap.get("direction"))
        run_context.session_state.set("zone", "medium")  # updated by guard


@with_logging
@with_timeout(seconds=C.TIMEOUT_START_MOVING)
def start_moving(direction: str, speed: int = C.DEFAULT_SPEED, run_context=None) -> str:
    """Begin continuous movement. Returns immediately — motor runs until
    stop_moving is called or SonarGuard intervenes.
    """
    hw = _get_hw(run_context)
    if hw is None or hw.movement_manager is None:
        return '{"status": "error", "message": "movement_manager not available"}'
    if direction not in {"forward", "back", "left", "right"}:
        return f'{{"status": "error", "message": "invalid direction: {direction}"}}'

    result = hw.movement_manager.go(direction, speed)
    _update_session_state(run_context, hw)
    return str(result)
