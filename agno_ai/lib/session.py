"""
SessionManager — agent loop for goal-based execution.

Each goal runs in a background thread. The agent calls tools directly and
decides when the goal is complete. The session ends when the agent stops
calling tools and the motor is not running.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Callable

from agno_ai.types.context import HardwareContext
from agno_ai.lib.nav_log import get_nav_log, reset_nav_log
from agno_ai.lib.target_tracker import get_target_tracker, reset_target_tracker

logger = logging.getLogger("agno.session")


def _motor_is_moving(hw: HardwareContext) -> bool:
    if hw.motor is None:
        return False
    return hw.motor.is_moving_forward or hw.motor.is_moving_backward


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
        self._publish_callback = publish_callback
        self._obs_memory = obs_memory
        self._session_compactor = session_compactor
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._transcript: list[str] = []
        self._iteration: int = 0
        self._prev_motor_moving: bool = False

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
        if self._hw.motor is not None:
            self._hw.motor.stop()
        logger.info("SessionManager: stop requested")
        return {"status": "stop_requested"}

    def flush_transcript(self, goal: str) -> None:
        if self._obs_memory and self._transcript:
            self._obs_memory.flush(goal, list(self._transcript))

    @property
    def current_goal(self) -> str | None:
        return getattr(self, "_current_goal", None)

    # ── internal ─────────────────────────────────────────────────────────────

    def _publish(self, payload: dict) -> None:
        if self._publish_callback is not None:
            try:
                self._publish_callback(payload)
            except Exception as exc:
                logger.warning(f"SessionManager: publish failed — {exc}")

    def _run(self, goal: str) -> None:
        session_id = "rambabu-rover"
        self._transcript = [f"GOAL: {goal}"]
        self._iteration = 0
        self._prev_motor_moving = False
        _start_time = time.monotonic()
        nav_log = reset_nav_log()
        reset_target_tracker()

        try:
            self._publish({"status": "started", "goal": goal})
            while not self._stop_event.is_set():
                motor_was_moving = self._prev_motor_moving
                motor_is_moving_now = _motor_is_moving(self._hw)
                sonar_fired = motor_was_moving and not motor_is_moving_now
                elapsed = time.monotonic() - _start_time

                msg = self._build_message(
                    goal,
                    iteration=self._iteration,
                    elapsed_s=elapsed,
                    motor_moving=motor_is_moving_now,
                    sonar_fired=sonar_fired,
                )
                self._prev_motor_moving = motor_is_moving_now

                output = self._agent.run(
                    msg, session_id=session_id, stream=True, stream_events=True
                )

                text = ""
                if output is not None:
                    try:
                        for event in output:
                            if hasattr(event, "content") and event.content:
                                text += event.content
                    except Exception as stream_exc:
                        # CompressionManager or API errors mid-stream — log and
                        # continue with whatever text we collected so far.
                        # Do NOT crash the run; the agent may have issued tool
                        # calls before the error and those are already executed.
                        logger.warning(
                            f"SessionManager: streaming error (continuing) — {stream_exc}"
                        )

                    if self._session_compactor:
                        self._session_compactor.on_run_complete()

                if text:
                    self._transcript.append(f"AGENT: {text}")

                self._prev_motor_moving = _motor_is_moving(self._hw)
                self._iteration += 1
                self._write_checkpoint(goal)

                # Complete only after ≥ 2 iterations, no tool calls, motor stopped
                if (
                    self._iteration >= 2
                    and not self._has_tool_calls(output)
                    and not _motor_is_moving(self._hw)
                ):
                    self._publish(
                        {"status": "complete", "goal": goal, "result": text}
                    )
                    logger.info(f"SessionManager: complete — {text[:100]}")
                    if self._obs_memory:
                        nav_summary = nav_log.to_transcript_str()
                        transcript = list(self._transcript)
                        if nav_summary:
                            transcript.append(nav_summary)
                        self._obs_memory.on_run_complete(goal, transcript)
                    return

        except Exception as exc:
            logger.error(f"SessionManager: error — {exc}")
            self._publish({"status": "error", "goal": goal, "message": str(exc)})
            if self._obs_memory:
                nav_summary = nav_log.to_transcript_str()
                transcript = list(self._transcript)
                if nav_summary:
                    transcript.append(nav_summary)
                self._obs_memory.on_run_complete(goal, transcript)

    def _write_checkpoint(self, goal: str) -> None:
        try:
            os.makedirs("sessions", exist_ok=True)
            payload = {
                "goal": goal,
                "iteration": self._iteration,
                "timestamp": time.time(),
                "transcript": list(self._transcript),
            }
            tmp = "sessions/checkpoint.tmp"
            with open(tmp, "w") as f:
                json.dump(payload, f)
            os.replace(tmp, "sessions/checkpoint.json")
        except Exception as exc:
            logger.warning(f"SessionManager: checkpoint write failed — {exc}")

    def _build_message(
        self,
        goal: str,
        iteration: int = 0,
        elapsed_s: float = 0.0,
        motor_moving: bool = False,
        sonar_fired: bool = False,
    ) -> str:
        parts = []

        if self._obs_memory:
            observations = self._obs_memory.get_observations()
            if observations:
                parts.append(
                    f"PERSISTENT OBSERVATIONS (from previous sessions):\n{observations}"
                )

        parts.append(goal)

        nav_str = get_nav_log().to_context_str()
        if nav_str:
            parts.append(nav_str)

        target_str = get_target_tracker().to_context_str()
        if target_str:
            parts.append(target_str)

        if iteration > 0:
            motor_state = "running" if motor_moving else "stopped"
            if sonar_fired:
                motor_state = "auto-stopped by SonarGuard"

            dist_str = ""
            if self._hw.sonar_guard is not None and self._hw.sonar_guard.is_running:
                dist_cm, zone = self._hw.sonar_guard.snapshot()
                dist_str = f"Front: {dist_cm:.0f}cm ({zone}). "

            parts.append(
                f"[Iteration {iteration} | Elapsed: {elapsed_s:.0f}s | "
                f"Motor: {motor_state} | {dist_str}"
                f"Continue working on the goal above.]"
            )

        return "\n\n".join(parts)

    @staticmethod
    def _has_tool_calls(output) -> bool:
        if not output:
            return False
        if hasattr(output, "tools"):
            return bool(output.tools)
        return False
