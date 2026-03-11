# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation

- [Project Philosophy](docs/PROJECT_PHILOSOPHY.md) — non-negotiable invariants and design law
- [Engineering Guidelines](docs/ENGINEERING_GUIDELINES.md) — how code is written day-to-day
- [Architecture Decision Records](docs/DECISIONS.md) — why decisions were made

## Project Overview

AI RC Car — an autonomous RC car running on Raspberry Pi 5. Controls motors, servos, ultrasonic sensors, camera, and audio via GPIO. Provides a Flask web dashboard for remote control and an MQTT integration for AWS IoT Core.

**Target hardware:** Raspberry Pi 5, L9110S motor driver, SG90 servos, HC-SR04 ultrasonic sensor, Pi Camera v2, USB mic/speaker.

## Commands

```bash
# Run the car (requires Pi hardware)
python3 main.py

# Run as systemd service
sudo systemctl start aicar

# Install dependencies
uv sync

# Run tests (hardware tests — must run on Pi with wiring connected)
uv run pytest tests/

# Run a single test
uv run pytest tests/test_motor.py

# Format code
uv run black .

# Lint
uv run ruff check
```

## Architecture

### Layer diagram (strict one-way imports)

```
main.py  →  server/  →  lib/     →  config/  (constants only)
         →  navigation/ →  lib/  →  utils/   (pure Python helpers)
         →  lib/        →  utils/
         →  vision/     →  lib/camera
```

- **`config/__init__.py`** — single source of truth for all GPIO pin assignments, speed limits, distance thresholds, servo angles, MQTT topics, and Flask settings. Uses `typing.Final`. Referenced as `import config` throughout.
- **`lib/`** — one file per hardware concern. Each class wraps GPIO for a single peripheral. These are directly callable as LLM tools. No cross-imports within lib/.
- **`server/`** — Flask app factory (`app.py`) + REST routes (`routes.py`). Hardware instances are injected via `set_hardware_dependencies()`. Routes are thin bridges that call `lib/` methods.
- **`server/mqtt/`** — AWS IoT Core client, telemetry publisher, and command handler. Subscribes to command topics and routes payloads to `lib/` functions.
- **`navigation/`** — autonomous driving logic. `modes.py` (state machine), `avoidance.py` (obstacle avoidance), `navigator.py` (10Hz decision loop).
- **`vision/`** — MobileNet SSD object detection (`detector.py`) and MJPEG stream (`stream.py`). Consumes frames from `lib/camera`.
- **`utils/`** — pure Python helpers (logger, timing, converters). No hardware imports.
- **`static/`** — web dashboard (HTML/CSS/JS). `control.js` sends fetch() calls to REST API for motor/servo control.

### Boot sequence (main.py)

GPIO init (BCM mode) → MotorController → Ultrasonic (background thread at 20Hz) → PanTilt (center at 90/90) → Flask app (daemon thread on :5000) → obstacle monitor (daemon thread) → main thread blocks.

### Obstacle safety

Two layers prevent forward collisions:
1. **Background monitor thread** (`main.py:obstacle_monitor`) — polls ultrasonic at 20Hz, stops motor if forward + obstacle within `OBSTACLE_DETECTION_DISTANCE`.
2. **API guard** (`routes.py`) — `POST /motor/front` returns 409 if obstacle detected.

Both check `motor.is_moving_forward` / distance threshold from config.

### Key conventions

- GPIO uses BCM numbering, initialized once in `main.py` before any hardware class.
- Pan/tilt servos use hardware PWM on GPIO 12/13 (Pi 5 jitter-free).
- HC-SR04 echo pin requires voltage divider (5V→3.3V) on GPIO 24.
- Ultrasonic sensor runs in a background thread; `get_distance()` returns the latest cached value (thread-safe via lock).
- `pigpio` does not work on Pi 5 — use `RPi.GPIO` instead.
- Package manager is `uv` (not pip). Virtual env at `.venv/`. Python >=3.10.

### Structured Error Codes

API errors use structured codes — see full table in [Engineering Guidelines](docs/ENGINEERING_GUIDELINES.md).

| Code | Meaning |
|------|---------|
| `SENSOR_TIMEOUT` | Ultrasonic sensor did not respond |
| `MOTOR_STALL` | Motor command failed |
| `OBSTACLE_DETECTED` | Forward movement blocked (409) |
| `GPIO_FAILURE` | GPIO operation failed |
| `CAMERA_ERROR` | Camera capture failed |
| `SERVO_LIMIT` | Angle clamped to valid range |

Error response format: `{"error_code": "...", "message": "..."}`

### Testing

```bash
# Unit tests (run anywhere — GPIO is mocked)
uv run pytest tests/unit/

# Hardware tests (Pi with wiring only)
uv run pytest tests/hardware/

# Format & lint
uv run black . && uv run ruff check
```

Unit tests live in `tests/unit/`, hardware tests in `tests/hardware/`. Unit tests mock all GPIO — they never require physical hardware.

### REST API endpoints

- `POST /motor/<front|back|left|right|stop>` — body: `{"speed": 70}`
- `POST /steering/<steer_left_hold|steer_right_hold|steer_center>`
- `POST /servo/pan` — body: `{"angle": 90}` or `{"direction": "left", "degrees": 10}`
- `POST /servo/tilt` — body: `{"angle": 90}` or `{"direction": "up", "degrees": 10}`
- `POST /servo/center`
- `GET /status` — full system status JSON
- `GET /sensor/distance` — ultrasonic reading with zone
- `GET /video_feed` — MJPEG stream
