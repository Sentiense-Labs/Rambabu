"""
GoalDrivenAgent — Agno Agent wrapper for the rover brain.

System prompt built programmatically via PromptBuilder (agno/lib/prompts.py).
Registers all 10 tools and provides start/stop wired to SessionManager.

Model configuration uses agno.models.ModelPresets:
  model_preset="FAST"       → gemini-2.5-flash
  model_preset="BALANCED"   → gemini-2.5-pro
  compress_model_preset="COMPRESSION" → gemini-2.5-flash-lite
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from agno.agent import Agent
from agno.compression import CompressionManager
from agno.db.sqlite import SqliteDb
from agno.types.context import HardwareContext
from agno import constants as C
from agno.constants import check_gemini_key
from agno.lib.prompts import build_soul_instructions, TOOL_ADDENDUM
from agno.lib.session import SessionManager
from agno.lib.memory import ObservationalMemory, SessionCompactor
from agno.models import get_model
from agno.tools import (
    start_moving,
    stop_moving,
    move,
    distance,
    look_around,
    pan_tilt,
    say,
    reverse_steer,
    three_point_turn,
    align_to_path,
)

logger = logging.getLogger("agno.agent")

SESSION_ID = "rambabu-rover"


def _build_instructions(
    agent: Agent | None = None,
    session_state: dict | None = None,
    run_context: Any = None,
) -> str:
    """Callable instructions for Agno Agent — built programmatically, no file read."""
    return build_soul_instructions() + "\n\n" + TOOL_ADDENDUM


class GoalDrivenAgent:
    def __init__(
        self,
        hw: HardwareContext,
        publish_callback: Callable[[dict[str, Any]], None] | None = None,
        db_path: str | None = None,
        model_preset: str = "FAST",
        tool_call_limit: int = C.DEFAULT_MAX_ITERATIONS,
        token_reflection_threshold: int = 1500,
        compress_model_preset: str = "COMPRESSION",
    ) -> None:
        self._hw = hw
        self._publish = publish_callback
        self._model_preset = model_preset
        self._tool_call_limit = tool_call_limit

        check_gemini_key()

        db_file = db_path or (
            ":memory:" if os.environ.get("AGNO_IN_MEMORY") else "agno.db"
        )

        self._db: SqliteDb | None = (
            SqliteDb(db_file=db_file) if db_file != ":memory:" else None
        )

        agent_model = get_model(model_preset)
        compress_model = get_model(compress_model_preset)

        self._agent = Agent(
            model=agent_model,
            tools=[
                start_moving,
                stop_moving,
                move,
                distance,
                look_around,
                pan_tilt,
                say,
                reverse_steer,
                three_point_turn,
                align_to_path,
            ],
            instructions=_build_instructions,
            num_history_runs=3,
            tool_call_limit=tool_call_limit,
            db=self._db,
            compress_tool_results=True,
            compression_manager=CompressionManager(
                compress_tool_results=True,
                compress_tool_results_limit=5,
            ),
        )

        self._obs_memory: ObservationalMemory | None = None
        self._session_compactor: SessionCompactor | None = None
        if self._db is not None:
            self._obs_memory = ObservationalMemory(
                db=self._db,
                session_id=SESSION_ID,
                token_reflection_threshold=token_reflection_threshold,
                compress_model=compress_model,
            )
            self._session_compactor = SessionCompactor(
                db=self._db,
                session_id=SESSION_ID,
                compress_model=compress_model,
            )

        self._session = SessionManager(
            agent=self._agent,
            hw=hw,
            publish_callback=publish_callback,
            obs_memory=self._obs_memory,
            session_compactor=self._session_compactor,
        )

    @property
    def agent(self) -> Agent:
        return self._agent

    def start(self, goal: str) -> dict[str, Any]:
        return self._session.start_goal(goal)

    def stop(self) -> dict[str, Any]:
        self._session.flush_transcript(self._session.current_goal or "session")
        return self._session.stop()
