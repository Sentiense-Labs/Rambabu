"""
ExplorationSessionManager — continuous autonomous exploration loop.

Unlike SessionManager (goal-based), ExplorationSessionManager runs indefinitely
without a target. When idle (motor stopped, no pending tool calls) it prompts
the agent to pick something to do. The agent calls tools directly and makes
all navigation decisions itself.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from agno_ai.types.context import HardwareContext

logger = logging.getLogger("agno.explore_session")

EXPLORER_SESSION_ID = "rambabu-explorer"


def _motor_is_moving(hw: HardwareContext) -> bool:
    if hw.motor is None:
        return False
    return hw.motor.is_moving_forward or hw.motor.is_moving_backward


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
        self._transcript: list[str] = []
        self._last_activity = time.monotonic()
        self._is_exploring = False

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
        if self._hw.motor is not None:
            self._hw.motor.stop()
        logger.info("ExplorationSessionManager: exploration stopped")
        return {"status": "stopped"}

    def flush_transcript(self) -> None:
        if self._obs_memory and self._transcript:
            self._obs_memory.flush("exploration", list(self._transcript))

    @property
    def is_exploring(self) -> bool:
        return self._is_exploring

    # ── internal ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        self._is_exploring = True
        self._publish({"status": "exploring"})
        self._transcript = []

        try:
            while not self._stop_event.is_set():
                idle_for = time.monotonic() - self._last_activity
                msg = self._build_message(idle_for)

                output = self._agent.run(
                    msg,
                    session_id=EXPLORER_SESSION_ID,
                    stream=True,
                    stream_events=True,
                )

                text = ""
                if output is not None:
                    try:
                        for event in output:
                            if hasattr(event, "content") and event.content:
                                text += event.content
                    except Exception as stream_exc:
                        logger.warning(
                            f"ExplorationSessionManager: streaming error (continuing) — {stream_exc}"
                        )

                if self._session_compactor:
                    self._session_compactor.on_run_complete()

                if text:
                    self._transcript.append(f"AGENT: {text}")
                    self._last_activity = time.monotonic()

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
        if _motor_is_moving(self._hw):
            return False
        return not self._has_tool_calls(output)

    def _has_tool_calls(self, output) -> bool:
        if not output:
            return False
        return bool(output.tools)

    def _prompt_exploration(self) -> None:
        idle_msg = (
            "You are idle and parked. "
            "What do you want to do? Pick a direction, scout something interesting, "
            "or describe what you're curious about right now. "
            "You are Rambabu — curious, adventurous, a little dramatic. "
            "Make a decision and call a tool."
        )
        self._agent.run(idle_msg, session_id=EXPLORER_SESSION_ID)

    def _build_message(self, idle_for: float) -> str:
        parts = []

        if self._obs_memory:
            observations = self._obs_memory.get_observations()
            if observations:
                parts.append(
                    f"PERSISTENT OBSERVATIONS (from previous sessions):\n{observations}"
                )

        if idle_for > 0:
            parts.append(
                f"You have been idle/parked for {idle_for:.0f} seconds. "
                "What do you want to do?"
            )

        return "\n\n".join(parts) if parts else ""
