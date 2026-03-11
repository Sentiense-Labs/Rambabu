# Engineering Guidelines

Day-to-day rules for writing code in this project. For the "why" behind these rules, see [PROJECT_PHILOSOPHY.md](PROJECT_PHILOSOPHY.md).

## Error Handling

### Structured Error Codes

Every error returned by the API or logged by hardware code uses a structured error code:

| Code | Meaning | Default action |
|------|---------|----------------|
| `SENSOR_TIMEOUT` | Ultrasonic sensor did not respond within expected window | Log warning, return last cached value |
| `MOTOR_STALL` | Motor command issued but no movement detected | Stop motors, log error |
| `OBSTACLE_DETECTED` | Forward movement blocked by obstacle within threshold | Reject command (409), log info |
| `GPIO_FAILURE` | GPIO pin operation failed (setup, read, or write) | Stop motors, clean up GPIO, log critical |
| `CAMERA_ERROR` | Camera failed to capture frame | Log error, return empty frame |
| `CONFIG_INVALID` | Configuration value out of expected range | Refuse to start, log critical |
| `SERVO_LIMIT` | Requested servo angle outside allowed range | Clamp to nearest valid angle, log warning |
| `MQTT_DISCONNECT` | MQTT connection lost | Attempt reconnect, log warning |

### API Error Response Format

```json
{
  "error_code": "OBSTACLE_DETECTED",
  "message": "Forward movement blocked — obstacle at 12 cm (threshold: 25 cm)"
}
```

### Rules

- On hardware error: log, stop motors, return structured error
- Never swallow exceptions silently
- Use `utils/logger.py` for all logging — no bare `print()`

## State & Storage

- All runtime state lives in memory (class instances) — no database
- `config/__init__.py` is read-only at runtime
- Sensor data is cached with a thread-safe lock (`threading.Lock`)
- No global mutable state outside of class instances

## Code Structure

### Import Direction (strict one-way)

```
main.py  ->  server/  ->  lib/     ->  config/
         ->  navigation/ ->  lib/  ->  utils/
         ->  lib/        ->  utils/
         ->  vision/     ->  lib/camera
```

Never import upward (e.g., `lib/` must not import from `server/`).

### File Organization

- One class per file in `lib/`
- No cross-imports within `lib/`
- All constants in `config/__init__.py`
- Utilities in `utils/` — pure Python, no hardware imports
- 200-400 lines typical, 800 max per file

### Naming

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE` with `typing.Final`

## Testing

### Directory Structure

```
tests/
  unit/       # Mock GPIO, run anywhere (CI, laptop, Pi)
  hardware/   # Require Pi + wiring — never run in CI
```

### Commands

```bash
# All unit tests
uv run pytest tests/unit/

# All hardware tests (on Pi only)
uv run pytest tests/hardware/

# Single test file
uv run pytest tests/unit/test_motor.py

# Format
uv run black .

# Lint
uv run ruff check
```

### Rules

- Unit tests mock all GPIO and hardware dependencies
- Hardware tests are clearly separated and never run in CI
- Test files mirror source structure: `lib/motor.py` -> `tests/unit/test_motor.py`
- Clean up GPIO in test teardown (even on failure)

## Dependencies

- Package manager: `uv` (not pip)
- Virtual env at `.venv/`
- Add dependencies via `uv add <package>`
- Lock file: `uv.lock` (committed)
