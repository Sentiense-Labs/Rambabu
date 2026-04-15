"""
FastAPI service wrapping the GoalDrivenAgent.

Optional AgentOS dashboard mount for os.agno.com UI.

Routes:
    POST /goal     — start a new goal
    POST /stop     — stop the current run
    GET  /health   — liveness check
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from agno_ai.agents.goal_driven import GoalDrivenAgent
from agno_ai.agents.explorer import ExplorerAgent
from agno_ai.constants import check_gemini_key
from agno_ai.types.context import HardwareContext

logger = logging.getLogger("agno.service")


def create_agno_service(
    hw: HardwareContext,
    publish_callback: Callable[[dict[str, Any]], None] | None = None,
    enable_agent_os: bool = False,
    model: str = "gemini-2.5-flash",
    tool_call_limit: int = 100,
) -> Any:
    try:
        from fastapi import FastAPI

        has_fastapi = True
    except ImportError:
        has_fastapi = False

    check_gemini_key()

    goal_agent = GoalDrivenAgent(
        hw=hw,
        publish_callback=publish_callback,
        model=model,
        tool_call_limit=tool_call_limit,
    )
    explorer_agent = ExplorerAgent(
        hw=hw,
        publish_callback=publish_callback,
        model=model,
        tool_call_limit=tool_call_limit,
    )

    if not has_fastapi:
        logger.warning("FastAPI not installed — service returning raw agents")
        return {"rambabu": goal_agent, "explorer": explorer_agent}

    app = FastAPI(title="Rambabu Agno Service")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/goal")
    def goal(payload: dict):
        goal_text = payload.get("goal", "").strip()
        if not goal_text:
            return {"status": "error", "message": "empty goal"}
        return goal_agent.start(goal_text)

    @app.post("/stop")
    def stop():
        goal_agent.stop()
        return explorer_agent.stop()

    @app.post("/explore/start")
    def explore_start():
        return explorer_agent.start()

    @app.post("/explore/stop")
    def explore_stop():
        return explorer_agent.stop()

    if enable_agent_os:
        try:
            from agno.os import AgentOS

            os_app = AgentOS(agents=[goal_agent.agent, explorer_agent.agent]).get_app()
            app.mount("/", os_app)
            logger.info("AgentOS dashboard enabled at /")
        except Exception as exc:
            logger.warning(
                f"AgentOS mount failed: {exc} — continuing without dashboard"
            )

    return app
