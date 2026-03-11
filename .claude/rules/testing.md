---
description: Testing conventions
paths: ["tests/**"]
---

# Testing Rules

## Directory Structure

```
tests/
  unit/       # Mock GPIO, run anywhere
  hardware/   # Require Pi + wiring, never in CI
```

## DO

- Mock all GPIO and hardware dependencies in unit tests
- Separate unit tests (`tests/unit/`) from hardware tests (`tests/hardware/`)
- Mirror source structure: `lib/motor.py` -> `tests/unit/test_motor.py`
- Clean up GPIO in test teardown — even on failure (use `finally` or `addCleanup`)
- Test error paths and structured error codes, not just happy paths
- Use `pytest` as the test runner
- Run `uv run black .` and `uv run ruff check` before committing

## DO NOT

- Require physical hardware for unit tests
- Skip GPIO cleanup in test teardown
- Use `unittest.mock.patch` on `config` values — pass them as parameters instead
- Write tests that depend on execution order
- Import `RPi.GPIO` directly in unit tests — always mock it

## Running Tests

```bash
uv run pytest tests/unit/          # Safe anywhere
uv run pytest tests/hardware/      # Pi with wiring only
uv run pytest tests/unit/test_motor.py -v  # Single file, verbose
```
