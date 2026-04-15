"""
BrainEvent — asynchronous events injected into the agent loop by SonarGuard.

TOOL_ADDENDUM and COMPRESS_PROMPT are imported from agno.lib.prompts
so there is a single source of truth for prompt text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agno_ai.lib.prompts import TOOL_ADDENDUM, COMPRESS_PROMPT

# Re-export with underscore prefix for backward compatibility
_TOOL_ADDENDUM = TOOL_ADDENDUM
_COMPRESS_PROMPT = COMPRESS_PROMPT


@dataclass(frozen=True)
class BrainEvent:
    """A single asynchronous event that should wake the brain."""

    kind: str  # ZONE_CHANGE | OBSTACLE | EMERGENCY_STOP | GOAL_CHECK | SAFETY_HALT
    zone: str | None = None
    distance_cm: float | None = None
    extra: dict[str, Any] | None = None

    def to_user_message(self) -> str:
        if self.kind == "GOAL_CHECK":
            extra = self.extra or {}
            return (
                "EVENT: GOAL_CHECK "
                f"elapsed={extra.get('elapsed_s', 0):.1f}s "
                f"estimated_distance={extra.get('estimated_distance_cm', 0):.0f}cm "
                f"direction={extra.get('direction', 'unknown')}"
            )
        dist = f"{self.distance_cm:.0f}cm" if self.distance_cm is not None else "?"
        if self.kind == "ZONE_CHANGE":
            old = (self.extra or {}).get("old_zone", "?")
            return f"EVENT: ZONE_CHANGE zone={old}→{self.zone} distance={dist}"
        if self.kind == "OBSTACLE":
            return (
                f"EVENT: OBSTACLE zone={self.zone} distance={dist} "
                "(motor auto-stopped — assess and replan)"
            )
        if self.kind == "EMERGENCY_STOP":
            return (
                f"EVENT: EMERGENCY_STOP distance={dist} "
                "(motor already halted by SonarGuard)"
            )
        if self.kind == "SAFETY_HALT":
            reason = (self.extra or {}).get("reason", "SAFETY_HALT")
            return (
                f"EVENT: SAFETY_HALT reason={reason} distance={dist}\n"
                "The motor is STOPPED. SonarGuard halted you because the path is "
                "blocked. You MUST now call a tool: look_around() to assess, "
                "then start_moving(direction) to maneuver, or stop_moving() + a "
                "final say() if the goal is over."
            )
        return f"EVENT: {self.kind}"
