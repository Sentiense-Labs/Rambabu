"""
SessionManager — event bus + short-run agent loop.

Each goal runs in a background thread. The loop drains queued BrainEvents
and feeds them to the agent as user messages, simulating the event-driven
wake pattern of the original brain.py.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Callable

from agno.types.context import HardwareContext
from agno.types.events import BrainEvent

logger = logging.getLogger("agno.session")


class SessionManager:
    def __init__(
        self,
        agent,
        hw: HardwareContext,
        publish_callback: Callable[[dict], None] | None = None,
        obs_memory=None,
        session_compactor=None,
    ) -> None:
        self._agent = agent
        self._hw = hw
        self._publish = publish_callback
        self._obs_memory = obs_memory
        self._session_compactor = session_compactor
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._bus: queue.Queue[BrainEvent] = queue.Queue()
        self._transcript: list[str] = []

        # Register callbacks on MovementManager to populate the bus
        if hw.movement_manager is not None:
            hw.movement_manager._on_zone_change = self._on_zone_change  # noqa: SLF001
            hw.movement_manager._on_emergency_stop = (
                self._on_emergency_stop
            )  # noqa: SLF001

    # ── public ────────────────────────────────────────────────────────────────

    def start_goal(self, goal: str) -> dict:
        if self._thread is not None and self._thread.is_alive():
            return {
                "status": "busy",
                "current_goal": getattr(self, "_current_goal", None),
            }
        self._current_goal = goal
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(goal,),
            daemon=True,
            name="agno-session",
        )
        self._thread.start()
        logger.info(f"SessionManager: started goal: {goal[:80]}")
        return {"status": "started", "goal": goal}

    def stop(self) -> dict:
        self._stop_event.set()
        if self._hw.movement_manager is not None:
            self._hw.movement_manager.stop()
        logger.info("SessionManager: stop requested")
        return {"status": "stop_requested"}

    def flush_transcript(self, goal: str) -> None:
        if self._obs_memory and self._transcript:
            self._obs_memory.flush(goal, list(self._transcript))

    @property
    def current_goal(self) -> str | None:
        return getattr(self, "_current_goal", None)

    # ── internal ─────────────────────────────────────────────────────────────

    def _on_zone_change(self, old_zone: str, new_zone: str, distance: float) -> None:
        kind = "OBSTACLE" if new_zone == "close" else "ZONE_CHANGE"
        self._bus.put(
            BrainEvent(
                kind=kind,
                zone=new_zone,
                distance_cm=distance,
                extra={"old_zone": old_zone},
            )
        )

    def _on_emergency_stop(self, distance: float) -> None:
        self._bus.put(
            BrainEvent(
                kind="EMERGENCY_STOP",
                zone="critical",
                distance_cm=distance,
            )
        )

    def drain_events(self) -> list[BrainEvent]:
        drained: list[BrainEvent] = []
        while True:
            try:
                drained.append(self._bus.get_nowait())
            except queue.Empty:
                return drained

    def _run(self, goal: str) -> None:
        session_id = "rambabu-rover"
        self._transcript = [f"GOAL: {goal}"]
        self._publish({"status": "started", "goal": goal})

        try:
            while not self._stop_event.is_set():
                events = self.drain_events()
                msg = self._build_message(events, goal)

                output = self._agent.run(msg, session_id=session_id)

                text = output.content or ""
                if text:
                    self._transcript.append(f"AGENT: {text}")

                if self._session_compactor:
                    self._session_compactor.on_run_complete()

                # Check if goal is complete (no tool calls + not moving)
                if not self._has_tool_calls(output):
                    moving = (
                        self._hw.movement_manager is not None
                        and self._hw.movement_manager.is_moving
                    )
                    if not moving:
                        final = text
                        self._publish(
                            {"status": "complete", "goal": goal, "result": final}
                        )
                        logger.info(f"SessionManager: complete — {final[:100]}")
                        if self._obs_memory:
                            self._obs_memory.on_run_complete(
                                goal, list(self._transcript)
                            )
                        return
                    # Still moving but returned text — synthesize a GOAL_CHECK
                    # and continue (loop will re-evaluate)
                    if moving:
                        goal = "GOAL_CHECK"

                # If movement_manager is no longer moving due to safety stop,
                # synthesize a SAFETY_HALT message
                if self._hw.movement_manager is not None:
                    snap = self._hw.movement_manager.snapshot()
                    if (
                        snap.get("is_moving") is False
                        and self._hw.movement_manager.was_safety_stopped
                    ):
                        info = self._hw.movement_manager.safety_stop_info
                        reason = (
                            info.get("reason", "SAFETY_HALT") if info else "SAFETY_HALT"
                        )
                        dist = info.get("distance_cm") if info else None
                        safety_msg = (
                            f"EVENT: SAFETY_HALT reason={reason} "
                            f"distance={dist:.0f}cm\n"
                            "The motor is STOPPED. You MUST now call a tool."
                        )
                        self._agent.run(safety_msg, session_id=session_id)
                        self._transcript.append("AGENT: [SAFETY_HALT triggered]")

        except Exception as exc:
            logger.error(f"SessionManager: error — {exc}")
            self._publish({"status": "error", "goal": goal, "message": str(exc)})
            if self._obs_memory:
                self._obs_memory.on_run_complete(goal, list(self._transcript))

    def _build_message(self, events: list[BrainEvent], current_goal: str) -> str:
        parts = []

        # Prepend persistent observations from previous sessions
        if self._obs_memory and current_goal != "GOAL_CHECK":
            observations = self._obs_memory.get_observations()
            if observations:
                parts.append(
                    f"PERSISTENT OBSERVATIONS (from previous sessions):\n{observations}"
                )

        if current_goal == "GOAL_CHECK":
            snap = (
                self._hw.movement_manager.snapshot()
                if self._hw.movement_manager
                else {}
            )
            parts.append(
                f"EVENT: GOAL_CHECK "
                f"elapsed={snap.get('elapsed_s', 0):.1f}s "
                f"estimated_distance={snap.get('estimated_distance_cm', 0):.0f}cm "
                f"direction={snap.get('direction', 'unknown')}"
            )
        else:
            if events:
                parts.append("\n".join(ev.to_user_message() for ev in events))
            if current_goal:
                parts.append(current_goal)

        return "\n\n".join(parts)

    @staticmethod
    def _has_tool_calls(output) -> bool:
        if not output:
            return False
        return bool(output.tools)
