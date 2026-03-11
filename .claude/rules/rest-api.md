---
description: REST API surface rules
paths: ["server/**"]
---

# REST API Rules

## DO

- Return JSON for all responses (success and error)
- Use structured error codes: `{"error_code": "...", "message": "..."}`
- Check obstacle distance before executing `POST /motor/front` — return 409 if blocked
- Keep route handlers thin — delegate to `lib/` methods
- Validate request body fields (speed ranges, angle limits) before calling hardware
- Return appropriate HTTP status codes (200 success, 400 bad request, 409 conflict, 500 internal error)

## DO NOT

- Block in route handlers — no `time.sleep()` or long-running loops
- Expose raw Python exceptions to clients
- Import hardware libraries directly — use injected dependencies via `set_hardware_dependencies()`
- Add endpoints that bypass the two-layer safety system (background monitor + API guard)
- Return HTML from API endpoints (HTML is only for `GET /` and static files)

## Obstacle Safety (API Guard)

The `POST /motor/front` route MUST check `ultrasonic.get_distance()` against `config.OBSTACLE_DETECTION_DISTANCE` before allowing forward movement. This is the second safety layer — the background monitor thread is the first.
