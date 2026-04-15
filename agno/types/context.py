"""
HardwareContext — holds live hardware references injected at boot.

Tools access it via run_context.session_state.get("hw").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HardwareContext:
    """Live hardware references from main.py. Any field may be None if that
    peripheral failed to initialise — tools must handle None gracefully.
    """

    motor: Any = None
    ultrasonic: Any = None
    pan_tilt: Any = None
    camera: Any = None
    speaker: Any = None
    sonar_guard: Any = None
    movement_manager: Any = None
