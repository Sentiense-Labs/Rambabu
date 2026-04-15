# Agno Brain Rewrite — Implementation Plan

## Overview

Replace `brain/brain.py`, `brain/tools.py`, `brain/hardware_tools.py`, and `brain/runner.py` with a new `agno/` package built on the [Agno](https://docs.agno.com) agent framework. Keep all hardware-facing daemons (`sonar_guard`, `movement_manager`, `maneuvers`) unchanged. Wire the new agent into `main.py` and `command_handler.py`.

---

## Folder Structure

```
agno/
├── __init__.py                    # Empty package marker
├── constants.py                   # All numeric/symbolic constants
│
├── agents/
│   ├── __init__.py               # Re-exports: RambabuAgent
│   └── rambabu.py               # Agno Agent definition + RambabuAgent class
│
├── tools/
│   ├── __init__.py              # Re-exports all tools
│   ├── navigation/
│   │   ├── __init__.py          # Re-exports: start_moving, stop_moving, move
│   │   ├── start_moving.py
│   │   ├── stop_moving.py
│   │   └── move.py
│   ├── perception/
│   │   ├── __init__.py          # Re-exports: distance, look_around, pan_tilt
│   │   ├── distance.py
│   │   ├── look_around.py
│   │   └── pan_tilt.py
│   ├── speech/
│   │   ├── __init__.py          # Re-exports: say
│   │   └── say.py
│   └── maneuvers/
│       ├── __init__.py          # Re-exports: reverse_steer, three_point_turn, align_to_path
│       ├── reverse_steer.py
│       ├── three_point_turn.py
│       └── align_to_path.py
│
├── types/
│   ├── __init__.py              # Re-exports: BrainEvent, HardwareContext
│   ├── events.py                # BrainEvent dataclass + _TOOL_ADDENDUM string
│   └── context.py               # HardwareContext dataclass
│
├── middleware/
│   ├── __init__.py              # Re-exports: with_logging, with_timeout
│   ├── logging.py               # Logging decorator for tools
│   └── timeout.py               # Timeout decorator for tools
│
├── lib/
│   ├── __init__.py
│   ├── session.py               # SessionManager: event bus, short-run loop
│   └── compression.py            # Memory compressor
│
└── service.py                   # FastAPI app factory + RambabuOS

brain/
└── SOUL.md                      # (unchanged — read as agent instructions)
```

---

## What Stays vs Goes

### Stays (unchanged)
| Path | Reason |
|---|---|
| `lib/` | All hardware drivers |
| `brain/sonar_guard.py` | Hardware-facing daemon |
| `brain/movement_manager.py` | Hardware-facing daemon |
| `brain/maneuvers.py` | Hardware-facing maneuvers |
| `brain/memory/observations.md` | Compressed memory file |
| `brain/SOUL.md` | Agent instructions source |
| `server/mqtt/` | MQTT infrastructure |
| `server/app.py` | Flask app |

### Replaced
| Old File | New Location |
|---|---|
| `brain/brain.py` (652 lines) | `agno/agents/rambabu.py` + `agno/lib/session.py` |
| `brain/tools.py` (694 lines) | `agno/tools/**/*.py` (10 files, ~30 lines each) |
| `brain/hardware_tools.py` (491 lines) | `agno/types/context.py` + tool functions |
| `brain/runner.py` (91 lines) | `agno/service.py` + `agno/lib/session.py` |

---

## File Specifications

### `agno/constants.py`
All numeric constants centralized from:
- Zone thresholds (`ZONE_CRITICAL_CM = 25.0`, etc.)
- Speed defaults (`DEFAULT_SPEED = 80`, `DRIVE_SPEED = 80`)
- Timing (`REVERSE_HARD_CAP_S = 0.5`, `GOAL_CHECK_INTERVAL_S = 10.0`)
- Vision (`GEMINI_VISION_MODEL = "gemini-2.5-flash-lite"`, `MAX_IMAGE_DIM = 512`, `JPEG_QUALITY = 80`)
- Compression (`COMPRESS_MODEL = "gemini-2.5-flash-lite"`)
- Tool call limits (`DEFAULT_MAX_ITERATIONS = 100`, `DEFAULT_TEMPERATURE = 0.3`)

---

### `agno/types/context.py`
`HardwareContext` dataclass — holds `motor`, `ultrasonic`, `pan_tilt`, `camera`, `speaker`, `sonar_guard`, `movement_manager`. Populated once at boot in `main.py`. Tools access via `run_context.session_state.get("hw")`.

---

### `agno/types/events.py`
`BrainEvent` dataclass (`kind`, `zone`, `distance_cm`, `extra`) with `to_user_message()`. Contains `_TOOL_ADDENDUM` string (tool descriptions + event types for system prompt). Contains `_COMPRESS_PROMPT` string for memory compression.

---

### `agno/middleware/logging.py`
`with_logging` decorator wrapping tool execution with `logger.info` entry/exit. Applied to all tools at registration time.

### `agno/middleware/timeout.py`
`with_timeout` decorator using `signal.alarm` (Unix) or thread-based timer. Returns `"error: timed out after Xs"`.

---

### Tool Functions (10 total, ~20-40 lines each)

All tools follow this pattern:
```python
def tool_name(param1: str, param2: int = 80, run_context=None) -> str:
    """Docstring."""
    hw = _get_hw(run_context)
    # ... hardware call ...
    _update_session_state(run_context, hw)
    return str(result)
```

| Tool | File | Parameters |
|---|---|---|
| `start_moving` | `tools/navigation/start_moving.py` | `direction: str`, `speed: int = 80` |
| `stop_moving` | `tools/navigation/stop_moving.py` | — |
| `move` | `tools/navigation/move.py` | `direction: str`, `seconds: float = 0.5` |
| `distance` | `tools/perception/distance.py` | — |
| `look_around` | `tools/perception/look_around.py` | `question: str | None = None` |
| `pan_tilt` | `tools/perception/pan_tilt.py` | `action: str`, `degrees: int = 40` |
| `say` | `tools/speech/say.py` | `text: str` |
| `reverse_steer` | `tools/maneuvers/reverse_steer.py` | `steer_direction: str`, `seconds: float = 0.4` |
| `three_point_turn` | `tools/maneuvers/three_point_turn.py` | `preferred_side: str` |
| `align_to_path` | `tools/maneuvers/align_to_path.py` | `drift_direction: str`, `correction_strength: str = "light"` |

---

### `agno/lib/session.py` — SessionManager

Manages the short-run event-driven loop:
```python
class SessionManager:
    def start_goal(self, goal: str, hw: HardwareContext, session_id: str) -> dict:
        # Spawns background thread running _run_loop()

    def stop(self) -> dict:
        # Sets stop event, calls movement_manager.stop()

    def drain_events(self) -> list[BrainEvent]:
        # Drains queued BrainEvents from event bus

    def _run_loop(self, goal: str, session_id: str):
        while not self._stop_event.is_set():
            events = self.drain_events()
            msg = _build_message(events)  # events + GOAL_CHECK ping
            output = self._agent.run(msg, session_id=session_id)
            if not _has_tool_calls(output):
                break  # goal complete
        # Fire CompressionManager on exit
```

---

### `agno/lib/compression.py` — CompressionManager

Triggered after every N runs (configurable, default 20) or on explicit session end:
```python
class CompressionManager:
    def compress(self, goal: str, transcript: list[str], model: str = COMPRESS_MODEL):
        # Calls gemini-2.5-flash-lite with _COMPRESS_PROMPT
        # Appends result to brain/memory/observations.md
        # Updates run counter; resets counter on successful write
```

---

### `agno/agents/rambabu.py` — RambabuAgent

```python
class RambabuAgent:
    def __init__(self, hw: HardwareContext, publish_callback):
        self._hw = hw
        self._session_manager = SessionManager(...)
        self.agent = Agent(
            model=Gemini(id="gemini-2.5-flash", ...),
            tools=[all 10 tool functions],
            instructions=SOUL_MARKDOWN + _TOOL_ADDENDUM,
            session_history=True,
            num_history_runs=3,
            tool_call_limit=100,
        )

    def start(self, goal: str) -> dict:
        return self._session_manager.start_goal(goal, self._hw, session_id="rambabu-rover")

    def stop(self) -> dict:
        return self._session_manager.stop()
```

---

### `agno/service.py`

```python
def create_agno_service(
    hw: HardwareContext,
    publish_callback: Callable[[dict], None],
    enable_agent_os: bool = False,
) -> FastAPI:
    """Creates FastAPI app wrapping RambabuAgent. Optionally mounts AgentOS dashboard."""
    agent = RambabuAgent(hw=hw, publish_callback=publish_callback)
    app = FastAPI()
    # Routes: POST /goal, POST /stop, GET /health
    if enable_agent_os:
        app.include_router(AgentOS(agents=[agent.agent]).get_app().routes)
    return app
```

---

## Integration

### `main.py`
```python
# Before
from brain.runner import ControlRunner
control_runner = ControlRunner(publish_callback=..., hw=hw)

# After
from agno.service import create_agno_service
app = create_agno_service(hw=hw, publish_callback=lambda r: mqtt_client.publish(...))
```

### `server/mqtt/command_handler.py`
```python
# Before: self._control_runner.start(goal) / .stop()
# After:  self._rambabu_agent.start(goal) / .stop()
```

### `pyproject.toml`
```toml
dependencies = [
    ...existing...,
    "agno>=2.5,<3.0",
]
```

---

## Build Sequence

1. `uv add "agno>=2.5,<3.0"`
2. `agno/constants.py` + `agno/types/context.py` + `agno/types/events.py`
3. `agno/middleware/logging.py` + `agno/middleware/timeout.py`
4. `agno/tools/navigation/` — 3 tools
5. `agno/tools/perception/` — 3 tools
6. `agno/tools/speech/` — 1 tool
7. `agno/tools/maneuvers/` — 3 tools
8. `agno/tools/__init__.py`
9. `agno/lib/compression.py`
10. `agno/lib/session.py`
11. `agno/agents/rambabu.py`
12. `agno/service.py`
13. Update `main.py` wiring
14. Update `command_handler.py` wiring
15. `uv run pytest tests/unit/`
16. Hardware test on Pi
