# AGENTS.md

AI RC Car — autonomous RC car on Raspberry Pi 5. Python >=3.10, managed by `uv`.

## Commands

```bash
# Install dependencies
uv sync

# Run the car (requires Pi hardware)
python3 main.py

# Run as systemd service
sudo systemctl start aicar

# Unit tests (run anywhere — GPIO is mocked)
uv run pytest tests/unit/

# Hardware tests (Pi with wiring only — never in CI)
uv run pytest tests/hardware/

# Single test file
uv run pytest tests/unit/test_motor.py -v

# Format then lint
uv run black . && uv run ruff check

# View service logs
journalctl -u aicar -n 30 --no-pager
```

## Architecture

Single Python package (not a monorepo). Strict one-way imports:

```
main.py  →  server/  →  lib/     →  config/  (constants only)
         →  brain/   →  lib/     →  utils/   (pure helpers)
         →  navigation/ → lib/
         →  vision/  →  lib/camera
```

Never import upward (e.g. `lib/` must not import from `server/`).

### Key directories

- `config/__init__.py` — single source of truth for ALL constants (`typing.Final`). GPIO pins, speed limits, distance thresholds, servo angles, MQTT topics, Flask settings. Never hardcode values elsewhere.
- `lib/` — one file per hardware peripheral. Each class is an LLM-callable tool. No cross-imports within `lib/`.
- `server/` — Flask app factory (`app.py`) + REST routes (`routes.py`). Hardware injected via `set_hardware_dependencies()`.
- `server/mqtt/` — AWS IoT Core client, telemetry, command handler.
- `brain/` — Gemini-powered LLM orchestrator (`brain.py`), tool registry (`tools.py`), hardware tool implementations (`hardware_tools.py`), SonarGuard safety watchdog, MovementManager. Default model: `gemini-2.5-flash`.
- `brain/memory/` — `observations.md` and `environment.md` are auto-updated session memory injected into the LLM system prompt.
- `navigation/` — autonomous driving: state machine, obstacle avoidance, 10Hz decision loop.
- `vision/` — MobileNet SSD detection + MJPEG stream.
- `utils/` — pure Python helpers. No hardware imports.

### Boot sequence (main.py)

GPIO init (BCM) → MotorController → front+rear Ultrasonic (20Hz threads) → Speaker (optional) → PanTilt via PCA9685 (optional) → Camera (optional) → Flask (daemon :5000) → obstacle monitors → MQTT → SonarGuard → BLE GATT → main thread blocks.

## Non-negotiable safety rules

Two independent layers prevent collisions — both must remain operational:

1. **Background monitor threads** — poll ultrasonic at 20Hz, stop motor if obstacle within `OBSTACLE_DETECTION_DISTANCE`.
2. **API guard** — `POST /motor/front` returns 409 if obstacle detected. `POST /motor/back` guards rear similarly.

Never bypass, weaken, or remove either layer. On any hardware error: stop motors first, then log, then return structured error.

## Hardware constraints

- GPIO uses BCM numbering, initialized once in `main.py` before any hardware class.
- `RPi.GPIO` only (via `rpi-lgpio` on Pi 5). **Never use `pigpio`** — incompatible with Pi 5.
- PCA9685 I2C servo driver (smbus2). Move-and-kill pattern eliminates jitter at rest.
- Pan/tilt direction multipliers are inverted (`PAN_DIRECTION = -1`, `TILT_DIRECTION = -1`) — servos mounted mirrored.
- HC-SR04 echo pin needs voltage divider (5V→3.3V).
- Reverse movements hard-capped at 0.5s (no rear sensor on some configs).

## Coding conventions

- No bare `print()` — use `utils/logger.py`.
- No cross-imports within `lib/`.
- All constants use `typing.Final` in `config/__init__.py`.
- API errors: `{"error_code": "...", "message": "..."}` with codes like `SENSOR_TIMEOUT`, `MOTOR_STALL`, `OBSTACLE_DETECTED` (409), `GPIO_FAILURE`, `CAMERA_ERROR`, `SERVO_LIMIT`.
- `lib/` classes are LLM tools: one public method per action, return dicts/primitives, no callbacks, no `*args/**kwargs` in public API.
- Files: 200-400 lines typical, 800 max.
- Package manager is `uv` (not pip). Add deps via `uv add <package>`.

## Testing

- `tests/unit/` — mock all GPIO, run anywhere. Mirror source structure: `lib/motor.py` → `tests/unit/test_motor.py`.
- `tests/hardware/` — require Pi + wiring. Never run in CI.
- `tests/conftest.py` — mocks RPi.GPIO, picamera2, pyttsx3, speech_recognition, faster_whisper, pyaudio, cv2 before any `lib/` import.
- Don't `unittest.mock.patch` config values — pass them as parameters instead.

## Skills

Load these via the `skill` tool when working in specific areas:

- `agno` — Agno framework guide (Smithery skill with full docs + RC car integration notes). Load when replacing or extending `brain/` with Agno SDK.
- `fastdepth` — FastDepth monocular depth estimation. Load when adding depth perception via the Pi Camera.

## MCP tools

- `context7` — fetches up-to-date library documentation. Add `use context7` to prompts when you need current API docs for any library (Agno, PyTorch, Flask, etc.).

## Reference docs

Read these when working in specific areas:

- `docs/PROJECT_PHILOSOPHY.md` — non-negotiable design invariants
- `docs/ENGINEERING_GUIDELINES.md` — day-to-day coding rules and error code table
- `docs/DECISIONS.md` — ADRs (REST over ROS, RPi.GPIO over pigpio, hardware PWM on GPIO 12/13)
- `docs/LIB_REFERENCE.md` — full API reference for every `lib/` class
- `docs/BLE_COMMANDS.md` — BLE GATT command reference and payloads
- `brain/SOUL.md` — LLM persona/system prompt for the rover's autonomous brain
