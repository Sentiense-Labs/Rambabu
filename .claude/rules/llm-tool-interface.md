---
description: LLM tool interface rules for hardware drivers
paths: ["lib/**"]
---

# LLM Tool Interface Rules

Every `lib/` class is a potential LLM tool. Design accordingly.

## DO

- One public method per action (e.g., `move_forward(speed)`, `stop()`, `pan_to(angle)`)
- Return values an LLM can parse: primitives, dicts, simple strings
- Make methods stateless where possible — action in, result out
- Include clear docstrings with parameter types and return values
- Return structured status after each action (e.g., `{"status": "ok", "speed": 70}`)

## DO NOT

- Require multi-step sequences to complete a single action
- Use callbacks — return results synchronously
- Return opaque objects (custom classes, generators, file handles)
- Require the caller to manage state between calls
- Use `*args` or `**kwargs` in public interfaces — be explicit

## Example: Good Interface

```python
class MotorController:
    def move_forward(self, speed: int = 50) -> dict:
        """Move car forward at given speed (0-100)."""
        # validate, execute, return
        return {"status": "ok", "direction": "forward", "speed": speed}

    def stop(self) -> dict:
        """Stop all motors immediately."""
        return {"status": "ok", "direction": "stopped"}
```
