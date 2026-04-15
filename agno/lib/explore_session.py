"""
ExplorationSessionManager — continuous autonomous exploration loop.

Unlike SessionManager (goal-based), ExplorationSessionManager runs indefinitely
without a target. It makes self-directed decisions: when idle it picks a direction
and roams, when events arrive it reacts, when nothing happens it gets bored
and goes somewhere new.

The explorer never returns — it runs until explicitly stopped.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

from agno.types.context import HardwareContext
from agno.types.events import BrainEvent

logger = logging.getLogger("agno.explore_session")


EXPLORER_SESSION_ID = "rambabu-explorer"


class ExplorationSessionManager:
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
        self._last_activity = time.monotonic()
        self._is_exploring = False

        if hw.movement_manager is not None:
            hw.movement_manager._on_zone_change = self._on_zone_change
            hw.movement_manager._on_emergency_stop = self._on_emergency_stop

    # ── public ────────────────────────────────────────────────────────────────

    def start(self) -> dict:
        if self._thread is not None and self._thread.is_alive():
            return {"status": "already_exploring"}
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="agno-explorer",
        )
        self._thread.start()
        logger.info("ExplorationSessionManager: started autonomous exploration")
        return {"status": "exploring"}

    def stop(self) -> dict:
        self._stop_event.set()
        if self._hw.movement_manager is not None:
            self._hw.movement_manager.stop()
        logger.info("ExplorationSessionManager: exploration stopped")
        return {"status": "stopped"}

    def flush_transcript(self) -> None:
        if self._obs_memory and self._transcript:
            self._obs_memory.flush("exploration", list(self._transcript))

    @property
    def is_exploring(self) -> bool:
        return self._is_exploring

    # ── internal ─────────────────────────────────────────────────────────────

    def _on_zone_change(self, old_zone: str, new_zone: str, distance: float) -> None:
        self._last_activity = time.monotonic()
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
        self._last_activity = time.monotonic()
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

    def _run(self) -> None:
        self._is_exploring = True
        self._publish({"status": "exploring"})
        self._transcript = []

        try:
            while not self._stop_event.is_set():
                events = self.drain_events()
                idle_for = time.monotonic() - self._last_activity

                msg = self._build_message(events, idle_for)

                output = self._agent.run(msg, session_id=EXPLORER_SESSION_ID)

                text = output.content or ""
                if text:
                    self._transcript.append(f"AGENT: {text}")

                if self._session_compactor:
                    self._session_compactor.on_run_complete()

                self._handle_safety_stop(output)

                if self._is_idle_and_has_no_pending_action(output):
                    self._prompt_exploration()

        except Exception as exc:
            logger.error(f"ExplorationSessionManager: error — {exc}")
            self._publish({"status": "error", "message": str(exc)})
        finally:
            self._is_exploring = False
            if self._obs_memory:
                self._obs_memory.on_run_complete("exploration", list(self._transcript))

    def _is_idle_and_has_no_pending_action(self, output) -> bool:
        if self._hw.movement_manager is None:
            return False
        if self._hw.movement_manager.is_moving:
            return False
        return not self._has_tool_calls(output)

    def _has_tool_calls(self, output) -> bool:
        if not output:
            return False
        return bool(output.tools)

    def _prompt_exploration(self) -> dict | None:
        idle_msg = (
            "You are idle and parked. "
            "What do you want to do? Pick a direction, scout something interesting, "
            "or describe what you're curious about right now. "
            "You are Rambabu — curious, adventurous, a little dramatic. "
            "Make a decision and call a tool."
        )
        return self._agent.run(idle_msg, session_id=EXPLORER_SESSION_ID)

    def _handle_safety_stop(self, output) -> None:
        if self._hw.movement_manager is None:
            return
        snap = self._hw.movement_manager.snapshot()
        if (
            snap.get("is_moving") is False
            and self._hw.movement_manager.was_safety_stopped
        ):
            info = self._hw.movement_manager.safety_stop_info
            reason = info.get("reason", "SAFETY_HALT") if info else "SAFETY_HALT"
            dist = info.get("distance_cm") if info else None
            safety_msg = (
                f"EVENT: SAFETY_HALT reason={reason} distance={dist:.0f}cm\n"
                "The motor is STOPPED. You MUST call a tool to respond."
            )
            self._agent.run(safety_msg, session_id=EXPLORER_SESSION_ID)
            self._transcript.append("AGENT: [SAFETY_HALT responded]")

    def _build_message(self, events: list[BrainEvent], idle_for: float) -> str:
        parts = []

        if self._obs_memory:
            observations = self._obs_memory.get_observations()
            if observations:
                parts.append(
                    f"PERSISTENT OBSERVATIONS (from previous sessions):\n{observations}"
                )

        if events:
            parts.append("\n".join(ev.to_user_message() for ev in events))

        if idle_for > 0:
            parts.append(
                f"You have been idle/parked for {idle_for:.0f} seconds. "
                "What do you want to do?"
            )

        return "\n\n".join(parts) if parts else ""
