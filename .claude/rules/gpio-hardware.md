---
description: GPIO and hardware safety rules
paths: ["lib/**", "main.py"]
---

# GPIO & Hardware Rules

## DO

- Use BCM numbering for all GPIO pins
- Clean up GPIO on exit (`GPIO.cleanup()` in finally/atexit)
- Stop motors on any error before re-raising or returning
- Read pin assignments from `config/__init__.py` — never hardcode pin numbers
- Use `RPi.GPIO` (via `rpi-lgpio` on Pi 5)
- Use hardware PWM on GPIO 12/13 for servos
- Initialize GPIO once in `main.py` before instantiating any hardware class
- Add voltage divider for 5V sensors (HC-SR04 echo pin)

## DO NOT

- Call `GPIO.setmode()` outside of `main.py`
- Use `pigpio` — it is incompatible with Raspberry Pi 5
- Hardcode pin numbers in `lib/` files — all pins come from `config/`
- Leave GPIO pins in an undefined state on error
- Import directly between `lib/` modules — no cross-imports

## On Error

1. Stop motors immediately (`motor.stop()`)
2. Log the error with structured error code (see `docs/ENGINEERING_GUIDELINES.md`)
3. Clean up affected GPIO pins
4. Return structured error — never swallow silently
