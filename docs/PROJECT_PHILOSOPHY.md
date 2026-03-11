# Project Philosophy

## One-Sentence Definition

A Raspberry Pi 5-based RC car that serves as a learning platform and proving ground for reusable integration packages (LLM-to-hardware bridge, sensor abstractions) and intelligence packages (navigation, vision, obstacle avoidance) intended for future robotics products.

## Why AI RC Car Exists

Existing platforms don't support LLM-as-operator natively, and their opinionated stacks make it hard to extract reusable components. This project provides full control over every layer — so that `lib/` hardware abstractions, `navigation/` logic, and `vision/` pipelines can be validated here and later packaged for other devices and frameworks. The car is the first consumer, not the last.

## What AI RC Car Is NOT

- **Not production or safety-critical** — a learning platform where failure consequences are limited to the car itself
- **Not cloud-dependent** — runs fully on the Pi; AWS IoT is optional telemetry
- **Not a monolith** — packages should remain extractable; avoid tight coupling between layers

## Users

| User | Interface | Role |
|------|-----------|------|
| Human operator | Flask web dashboard on local network | Drives manually, monitors status |
| LLM (Claude) | REST API and `lib/` functions as tools | Autonomous operation |
| AWS IoT Core | MQTT | Consumes telemetry, sends commands |

## Core Philosophy (Non-Negotiable)

### 1. LLM-Callable Interfaces

Every hardware capability exposed as a clean function call an LLM can invoke as a tool. One public method per action, stateless where possible, return values an LLM can parse (primitives, dicts, simple strings).

### 2. Fail-Safe Defaults

On any error or crash, motors stop and GPIO cleans up. Two independent safety layers enforce this:
1. **Background monitor thread** — polls ultrasonic at 20 Hz, stops motor if forward + obstacle within threshold
2. **API guard** — `POST /motor/front` returns 409 if obstacle detected

Neither layer may be bypassed or removed. Both must remain operational at all times.

### 3. Config as Single Source of Truth

All pin assignments, thresholds, limits live in `config/__init__.py` with `typing.Final`. No hardcoded values in `lib/`, `server/`, `navigation/`, or `vision/`.

## Design Litmus Tests

Before merging any change, ask:

1. **Can this module run without the car?** — `lib/` classes should be testable with mocked GPIO. `navigation/` and `vision/` should work with injected sensor data.
2. **Does it keep the safety layers intact?** — Both the background monitor and API guard must remain functional.
3. **Can an LLM call it with a single function?** — No multi-step sequences, no callbacks, no opaque return values.

If any answer is "no", the design is wrong.

## Explicitly Rejected Patterns

| Pattern | Reason |
|---------|--------|
| Event-driven architecture internally | Direct function calls between layers. MQTT is for external communication only. |
| ROS / robot middleware | Too heavy for a learning platform; hides the layers we want to understand. |
| Database for runtime state | All state is in-memory (class instances). Config is read-only. |

## Hard Constraints

- Must run on Raspberry Pi 5 (4 GB or 8 GB)
- Boot to web dashboard in under 10 seconds
- Python >= 3.10, managed by `uv`
- `RPi.GPIO` only (not `pigpio` — incompatible with Pi 5)
