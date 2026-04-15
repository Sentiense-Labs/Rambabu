"""
ControlRunner — runs the Gemini brain loop in a background thread.

Receives goals via MQTT (BRAIN_GOAL action), executes run_gemini_loop()
in a daemon thread, and publishes status/results back via a callback.

Thread-safety: all mutable state is protected by _lock. Only one goal
can run at a time — new goals are rejected with status='busy' if the
thread is alive.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from brain.brain import DEFAULT_MAX_ITERATIONS, DEFAULT_MODEL, run_gemini_loop
from brain.hardware_tools import HardwareContext

logger = logging.getLogger("brain.runner")


class ControlRunner:
    """Thread-safe wrapper that drives run_gemini_loop() from MQTT commands."""

    def __init__(
        self,
        publish_callback: Callable[[dict[str, Any]], None],
        model: str = DEFAULT_MODEL,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        hw: HardwareContext | None = None,
    ) -> None:
        self._publish = publish_callback
        self._model = model
        self._max_iterations = max_iterations
        self._hw = hw
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._current_goal: str | None = None
        self._stop_event = threading.Event()

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, goal: str) -> dict[str, Any]:
        """Start a new brain goal. Returns immediately; loop runs in background."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.warning(f"ControlRunner: busy — rejecting new goal: {goal[:60]}")
                return {"status": "busy", "current_goal": self._current_goal}

            self._current_goal = goal
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                args=(goal,),
                daemon=True,
                name="brain-runner",
            )
            self._thread.start()

        logger.info(f"ControlRunner: started — goal: {goal[:80]}")
        return {"status": "started", "goal": goal}

    def stop(self) -> dict[str, Any]:
        """Signal the running loop to stop after its current tool call."""
        self._stop_event.set()
        with self._lock:
            goal = self._current_goal
        logger.info("ControlRunner: stop requested")
        return {"status": "stop_requested", "current_goal": goal}

    # ── Internal ─────────────────────────────────────────────────────────

    def _run(self, goal: str) -> None:
        self._publish({"status": "started", "goal": goal})
        try:
            result = run_gemini_loop(goal, self._model, self._max_iterations, hw=self._hw)
            self._publish({"status": "complete", "goal": goal, "result": result})
            logger.info(f"ControlRunner: complete — goal: {goal[:60]}")
        except Exception as exc:
            logger.error(f"ControlRunner: error — {exc}")
            self._publish({"status": "error", "goal": goal, "message": str(exc)})
        finally:
            with self._lock:
                self._current_goal = None
