# Rambabu Agno Brain — Implementation Guide

## What Was Built

The old Gemini brain (`brain/brain.py`, `brain/tools.py`, `brain/hardware_tools.py`, `brain/runner.py`) has been replaced with a new agent system built on the [Agno](https://docs.agno.com) framework.

Two agents:
- **`GoalDrivenAgent`** — goal-driven, user-directed sessions
- **`ExplorerAgent`** — continuous autonomous exploration, no target needed

## Architecture

```
agno_ai/                          # Local Agno brain package (shadowed pip agno 2.5.17 — intentional)
├── constants.py               # All hardware constants (GPIO pins, timeouts, zones, speeds)
├── models.py                  # get_model() factory — FAST/BALANCED/COMPRESSION presets
├── service.py                 # FastAPI wrapper (create_agno_service)
├── agents/
│   ├── goal_driven.py         # GoalDrivenAgent class
│   └── explorer.py            # ExplorerAgent class
├── lib/
│   ├── session.py             # SessionManager — goal-based event loop
│   ├── explore_session.py     # ExplorationSessionManager — continuous loop
│   ├── memory.py              # ObservationalMemory + SessionCompactor
│   └── prompts.py             # PromptBuilder, build_soul_instructions(), build_exploration_instructions()
├── tools/                     # 10 hardware tools (same names + signatures as original)
│   ├── navigation/            # start_moving, stop_moving, move
│   ├── perception/           # distance, look_around, pan_tilt
│   ├── speech/               # say
│   └── maneuvers/            # reverse_steer, three_point_turn, align_to_path
├── types/
│   ├── context.py            # HardwareContext dataclass
│   └── events.py             # BrainEvent dataclass
└── middleware/
    ├── logging.py             # @with_logging — logs entry/exit/errors
    └── timeout.py            # @with_timeout — kills tool after N seconds
```

### Hardware Daemons (unchanged — used as-is)
- `sonar_guard` — polls ultrasonic at 20Hz, stops motor on obstacle
- `movement_manager` — PWM speed control, braking
- `lib/` — MotorController, Ultrasonic, PanTilt, Camera, Speaker

## Memory Architecture (3 layers)

1. **Layer 1 — Agno SqliteDb session history** (`num_history_runs=1`)
   - Stores last N complete runs (user message + model response + tool calls + results)
   - Re-injected on every new request via `num_history_runs`

2. **Layer 2 — ObservationalMemory** (Mastra-style two-stage)
   - Buffer accumulates observations in memory
   - When `>= token_threshold` (1500 chars) → `_run_observe()` → stores "observation" in `agno_learnings`
   - When `>= OBSERVATION_COUNT_REFLECT` (3 observations) → `_run_reflect()` → synthesises ALL into one "reflection" entry, deletes observations
   - Both observations AND reflections are prepended to goal context on each run

3. **Layer 3 — SessionCompactor**
   - After `MAX_SESSION_RUNS` (20), summarises oldest runs via LLM
   - Stores as `session_summary` in `agno_learnings`, trims session's `runs` list

## Key Design Decisions

### Namespace shadowing is intentional
`agno_ai/` shadows the installed `agno` 2.5.17 pip package. This is fine because:
- On the Pi, the local `agno_ai/` is the only code that matters
- All internal imports within `agno_ai/` use relative paths (`from agno.models import get_model`)
- Installed agno submodules (`agno.agent`, `agno.db.sqlite`, `agno.models.google`, etc.) are only imported by `agno_ai/models.py` and `agno_ai/lib/memory.py`

### SOUL.md is NOT read at runtime
System prompt is built programmatically via `PromptBuilder` in `agno_ai/lib/prompts.py`. The `build_soul_instructions()` function constructs the SOUL text from hardcoded strings. `brain/SOUL.md` is kept for documentation only.

### Prompt caching
`agno_ai/models.py` supports `cache_system_prompt=True` + `extended_cache_time=True` for Anthropic models, matching Mastra's pattern. Google models use `cached_content` for context caching.

### Tool signatures
All 10 tools keep the **same names and parameter shapes** as the original brain. Tool implementations were rewritten but the interfaces are identical — `main.py` wiring and `command_handler.py` don't need changes.

### Middleware
- `@with_logging` — logs `[tool] <name> called — args=X kwargs=Y` and `[tool] <name> ok in Ns`
- `@with_timeout` — kills tool after configured seconds (each tool has its own timeout in `constants.py`)
- Both preserve `__name__` and `__doc__` so AgentOS UI shows real tool names

## Setup on Raspberry Pi

### 1. Transfer the code
```bash
# On your laptop — push to Pi
rsync -avz --exclude='.git' --exclude='.venv' --exclude='__pycache__' /Users/mrpurple/Wavefuel/rambabu_rc/ pi@<pi-ip>:~/rambabu_rc/
```

### 2. Install dependencies
```bash
cd ~/rambabu_rc
uv sync
```

### 3. Set environment variables
```bash
# In ~/.bashrc or ~/.profile
export GOOGLE_GENERATIVE_AI_API_KEY="your-key-here"
export MQTT_BROKER_URL="your-mqtt-broker-url"
```

### 4. Run
```bash
# Direct
python3 main.py

# Or as systemd service
sudo systemctl start aicar
journalctl -u aicar -n 50 --no-pager
```

## main.py Changes

`main.py` creates `GoalDrivenAgent` and `ExplorerAgent` instead of `ControlRunner`:
```python
from agno.agents import GoalDrivenAgent, ExplorerAgent
from agno.types.context import HardwareContext

hw = HardwareContext(motor=motor, ultrasonic=ultrasonic, ...)
goal_agent = GoalDrivenAgent(hw=hw, publish_callback=lambda r: mqtt_client.publish(...))
explorer_agent = ExplorerAgent(hw=hw, publish_callback=lambda r: mqtt_client.publish(...))
command_handler = CommandHandler(motor=motor, pan_tilt=pan_tilt, speaker=speaker,
                                rambabu_agent=goal_agent, rear_ultrasonic=rear_ultrasonic)
```

Note: `CommandHandler` signature hasn't changed — it still takes `rambabu_agent` (the old name was kept for backward compat, not renamed to `goal_agent` to avoid breaking MQTT command routing).

## REST API

When `main.py` starts the Flask server (`server/app.py`), the agent is available via MQTT commands. The FastAPI service (`agno_ai/service.py`) is optional and not started by default in `main.py`.

To run the FastAPI service standalone:
```bash
GOOGLE_GENERATIVE_AI_API_KEY=... python -c "
from agno.service import create_agno_service
from agno.types.context import HardwareContext
# ... init hardware ...
app = create_agno_service(hw=hw)
import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)
"
```

Routes:
- `POST /goal` — start a new goal
- `POST /stop` — stop current run
- `POST /explore/start` — start explorer
- `POST /explore/stop` — stop explorer
- `GET /health` — liveness

## Model Presets (agno_ai/models.py)

| Preset | Model | Use |
|--------|-------|-----|
| FAST | gemini-2.5-flash | Default agent model |
| BALANCED | gemini-2.5-pro | Complex reasoning |
| COMPRESSION | gemini-2.5-flash-lite | Background synthesis |
| ANTHROPIC | claude-sonnet-4-5 | Expensive, selective |
| ANTHROPIC_FAST | claude-haiku-4-5 | Fast, low-cost Anthropic |

## Agent Configuration

```python
GoalDrivenAgent(
    hw=hw,
    db_path="agno.db",           # SQLite file (use ":memory:" for no persistence)
    model_preset="FAST",          # Which model preset
    tool_call_limit=100,         # Max tool calls per run
    token_reflection_threshold=1500,  # Chars before triggering observe()
    compress_model_preset="COMPRESSION",  # Model for background synthesis
)
```

## MQTT Commands

The agent responds to MQTT commands via `CommandHandler`. Compatible with the existing command format:
- `cmd::goal::<goal text>` — starts goal agent
- `cmd::stop` — stops current run
- `cmd::explore_start` — starts explorer
- `cmd::explore_stop` — stops explorer

## ObservationalMemory Tuning

Thresholds in `agno_ai/lib/memory.py`:
```python
TOKEN_OBSERVATION_THRESHOLD = 1500   # Chars in buffer before _observe()
OBSERVATION_COUNT_REFLECT = 3       # Observations before _reflect()
MAX_SESSION_RUNS = 20              # Runs before SessionCompactor fires
```

The memory system writes to `agno_learnings` table. Check directly:
```bash
sqlite3 agno.db "SELECT learning_type, substr(content,1,200) FROM agno_learnings;"
```

## Error Codes

Same as original — `OBSTACLE_DETECTED` (409), `SENSOR_TIMEOUT`, `MOTOR_STALL`, etc. defined in `config/__init__.py`.

## Testing

```bash
# Unit tests (GPIO mocked — runs anywhere)
uv run pytest tests/unit/ -v

# Specific test
uv run pytest tests/unit/test_motor.py -v

# Format + lint
uv run black .
uv run ruff check .
```

## Troubleshooting

### "Function not found" for tools in AgentOS UI
Caused by middleware not propagating `__name__`. Fixed in `agno_ai/middleware/logging.py` and `agno_ai/middleware/timeout.py` — both add `wrapper.__name__ = fn.__name__` before returning.

### High token counts on every request
`num_history_runs=1` keeps last run in context. With verbose tool results, this inflates tokens. Current setting is 1. To disable history: set `add_history_to_context=False`.

### Memories not showing in AgentOS UI
Ensure `enable_user_memories=True` and a `MemoryManager` with a `db` is provided. In `GoalDrivenAgent`, this is done automatically when `db_path` is set.

### Middleware TypeError: unexpected keyword argument 'args'
Agno sometimes calls tool wrappers with `args` and `kwargs` as **explicit keyword arguments**. The wrapper signature must accept both:
```python
def wrapper(*_args, args=None, kwargs=None, **kw):
    final_args = args if args is not None else (_args if _args else ())
    final_kwargs = kwargs if kwargs is not None else kw
```
Both `logging.py` and `timeout.py` in `agno_ai/middleware/` use this pattern.

## Files Reference

| File | Purpose |
|------|---------|
| `brain/SOUL.md` | Original persona — NOT read at runtime |
| `config/__init__.py` | All constants — single source of truth |
| `lib/motor.py` | MotorController — hardware tool |
| `lib/ultrasonic.py` | Ultrasonic — hardware tool |
| `lib/pan_tilt.py` | PanTilt via PCA9685 — hardware tool |
| `brain/sonar_guard.py` | 20Hz obstacle monitor — unchanged |
| `brain/movement_manager.py` | Speed/brake control — unchanged |
| `brain/maneuvers.py` | three_point_turn, align_to_path, reverse_steer — unchanged |
| `agno_ai/lib/prompts.py` | Programmatic SOUL builder — replaces SOUL.md read |
| `agno_ai/lib/memory.py` | Two-stage memory — Mastra pattern |
| `agno_ai/models.py` | Model factory — mirrors Mastra ModelPresets |
