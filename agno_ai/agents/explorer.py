"""
ExplorerAgent — continuous autonomous exploration agent.

Unlike GoalDrivenAgent (goal-driven), ExplorerAgent runs indefinitely,
roaming and narrating without a target. It uses ExplorationSessionManager
instead of SessionManager.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from agno.agent import Agent
from agno.compression import CompressionManager
from agno.db.sqlite import SqliteDb
from agno.memory import MemoryManager
from agno_ai.types.context import HardwareContext
from agno_ai import constants as C
from agno_ai.constants import check_gemini_key
from agno_ai.lib.prompts import (
    build_soul_instructions,
    build_exploration_instructions,
    TOOL_ADDENDUM,
)
from agno_ai.lib.explore_session import ExplorationSessionManager
from agno_ai.lib.memory import ObservationalMemory, SessionCompactor
from agno_ai.models import get_model
from agno_ai.tools import (
    stop_moving,
    move,
    move_cm,
    distance,
    look_around,
    pan_tilt,
    visual_survey,
    say,
    reverse_steer,
    three_point_turn,
    align_to_path,
)

logger = logging.getLogger("agno.explorer")

EXPLORER_SESSION_ID = "rambabu-explorer"


def _build_exploration_instructions(
    agent: Agent | None = None,
    session_state: dict | None = None,
    run_context: Any = None,
) -> str:
    """Callable instructions for ExplorerAgent — soul + exploration overlay."""
    return (
        build_soul_instructions()
        + "\n\n"
        + build_exploration_instructions()
        + "\n\n"
        + TOOL_ADDENDUM
    )


class ExplorerAgent:
    def __init__(
        self,
        hw: HardwareContext,
        publish_callback: Callable[[dict[str, Any]], None] | None = None,
        db_path: str | None = None,
        os_db: "SqliteDb | None" = None,
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

        if os_db is not None:
            self._db = os_db
        else:
            db_file = db_path or (
                ":memory:" if os.environ.get("AGNO_IN_MEMORY") else "agno.db"
            )
            self._db = SqliteDb(db_file=db_file) if db_file != ":memory:" else None

        agent_model = get_model(model_preset)
        compress_model = get_model(compress_model_preset)

        memory_manager = (
            MemoryManager(
                model=compress_model,
                memory_capture_instructions=(
                    "Extract spatial facts discovered during autonomous exploration: "
                    "new rooms or zones entered, interesting landmarks, recurring obstacles, "
                    "dead ends, traversable paths, and any environmental layout details. "
                    "Ignore jokes and personality quips."
                ),
                db=self._db,
                update_memories=True,
                add_memories=True,
            )
            if self._db is not None
            else None
        )

        self._agent = Agent(
            name="Explorer",
            model=agent_model,
            tools=[
                stop_moving,
                move,
                move_cm,
                distance,
                look_around,
                pan_tilt,
                visual_survey,
                say,
                reverse_steer,
                three_point_turn,
                align_to_path,
            ],
            instructions=_build_exploration_instructions,
            num_history_runs=3,
            tool_call_limit=tool_call_limit,
            db=self._db,
            memory_manager=memory_manager,
            update_memory_on_run=self._db is not None,
            user_id="rambabu",
            dependencies={"hw": hw},
            add_dependencies_to_context=True,
            compress_tool_results=True,
            compression_manager=CompressionManager(
                model=compress_model,
                compress_tool_results=True,
                compress_tool_results_limit=3,
            ),
        )

        self._obs_memory: ObservationalMemory | None = None
        self._session_compactor: SessionCompactor | None = None
        if self._db is not None:
            self._obs_memory = ObservationalMemory(
                db=self._db,
                session_id=EXPLORER_SESSION_ID,
                token_reflection_threshold=token_reflection_threshold,
                compress_model=compress_model,
            )
            self._session_compactor = SessionCompactor(
                db=self._db,
                session_id=EXPLORER_SESSION_ID,
                compress_model=compress_model,
            )

        self._session = ExplorationSessionManager(
            agent=self._agent,
            hw=hw,
            publish_callback=publish_callback,
            obs_memory=self._obs_memory,
            session_compactor=self._session_compactor,
        )

    @property
    def agent(self) -> Agent:
        return self._agent

    def start(self) -> dict[str, Any]:
        return self._session.start()

    def stop(self) -> dict[str, Any]:
        self._session.flush_transcript()
        return self._session.stop()

    @property
    def is_exploring(self) -> bool:
        return self._session.is_exploring
