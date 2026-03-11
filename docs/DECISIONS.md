# Architecture Decision Records

## ADR-001: LLM-as-Operator via REST API

**Date:** 2025-01
**Status:** Accepted

### Context

The car needs an interface that both human operators (via web dashboard) and LLMs (via tool calls) can use to control hardware. We evaluated:

- **ROS (Robot Operating System)** — industry standard for robotics
- **Serial/UART protocol** — direct hardware communication
- **gRPC** — high-performance RPC framework
- **REST API (Flask)** — simple HTTP endpoints

### Decision

Use a Flask REST API with JSON request/response bodies.

### Rationale

- REST is the native interface for LLM tool calling — no adapter layer needed
- Flask is lightweight and boots fast on Pi 5 (under 2 seconds)
- The web dashboard can call the same endpoints via `fetch()`
- ROS is too heavy for a learning platform and hides the layers we want to understand
- gRPC requires code generation and is harder to debug
- Serial is too low-level and doesn't support multiple concurrent clients

### Consequences

- All hardware actions must be exposed as HTTP endpoints
- Endpoints must return JSON that an LLM can parse without additional processing
- Flask runs in a daemon thread; must not block the main thread

---

## ADR-002: RPi.GPIO over pigpio

**Date:** 2025-01
**Status:** Accepted

### Context

GPIO access on Raspberry Pi requires a library. The two main options:

- **pigpio** — feature-rich, daemon-based, supports hardware PWM
- **RPi.GPIO** — simpler, direct kernel access, widely documented

### Decision

Use `RPi.GPIO` exclusively. Do not use `pigpio`.

### Rationale

- `pigpio` daemon (`pigpiod`) does not work reliably on Raspberry Pi 5
- Pi 5 moved GPIO to RP1 southbridge chip; `pigpio` was not updated for this
- `RPi.GPIO` works on Pi 5 with the `rpi-lgpio` compatibility layer
- Simpler dependency chain — no daemon process to manage

### Consequences

- Software PWM via `RPi.GPIO` has more jitter than hardware PWM via `pigpio`
- Servos use hardware PWM on GPIO 12/13 (Pi 5 PWM channels) to avoid jitter
- Any future GPIO library must be tested on Pi 5 before adoption

---

## ADR-003: Hardware PWM for Servos on GPIO 12/13

**Date:** 2025-01
**Status:** Accepted

### Context

SG90 servos require stable PWM signals. Software PWM introduces jitter that causes servo vibration and inaccurate positioning.

### Decision

Use hardware PWM on GPIO 12 (pan) and GPIO 13 (tilt) — the two hardware PWM channels available on Raspberry Pi 5.

### Rationale

- Pi 5 provides two hardware PWM channels via the RP1 chip
- GPIO 12 and 13 map to PWM0 and PWM1 respectively
- Hardware PWM eliminates jitter completely
- SG90 servos are particularly sensitive to PWM jitter at slow movements

### Consequences

- Pan/tilt servos are permanently assigned to GPIO 12/13
- Only two hardware PWM channels available — other PWM needs use software PWM
- Motor speed control (L9110S) uses software PWM, which is acceptable for DC motors
