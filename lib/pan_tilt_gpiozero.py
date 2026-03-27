#!/usr/bin/env python3
"""
PanTilt class for AI RC Car.
Controls pan/tilt servos via sysfs hardware PWM on Pi 5 (RP1 chip).

Mapping (confirmed on Pi 5):
  GPIO 12 (Pan)  → pwmchip0 / pwm0
  GPIO 13 (Tilt) → pwmchip0 / pwm1

config.txt must have:
  dtoverlay=pwm-2chan,pin=12,func=0,pin2=13,func2=0
"""

import os
import threading
from time import sleep
import config
from utils.logger import log_debug, log_info, log_warning

# Sysfs PWM chip/channel mapping for Pi 5
_PWM_CHIP = 0
_PAN_CHANNEL = 0   # GPIO 12
_TILT_CHANNEL = 1  # GPIO 13

# Servo PWM timing (nanoseconds)
_PERIOD_NS = 20_000_000   # 20ms = 50Hz
_MIN_DUTY_NS = 500_000    # 0.5ms = 0°
_MAX_DUTY_NS = 2_500_000  # 2.5ms = 180°

# Continuous movement
_STEP_DEG: int = 1
_TICK_SEC: float = 0.05


class _HardwarePWM:
    """Sysfs hardware PWM channel wrapper."""

    def __init__(self, chip: int, channel: int) -> None:
        self._chip = chip
        self._channel = channel
        self._base = f"/sys/class/pwm/pwmchip{chip}/pwm{channel}"
        self._export()

    def _write(self, filename: str, value: int) -> None:
        with open(f"{self._base}/{filename}", "w") as f:
            f.write(str(value))

    def _export(self) -> None:
        export_path = f"/sys/class/pwm/pwmchip{self._chip}/export"
        try:
            with open(export_path, "w") as f:
                f.write(str(self._channel))
        except OSError:
            pass  # Already exported
        sleep(0.1)
        self._write("period", _PERIOD_NS)
        self._write("duty_cycle", 0)

    def set_angle(self, angle: float) -> None:
        """Set servo to angle (0–180°)."""
        duty_ns = int(_MIN_DUTY_NS + (angle / 180.0) * (_MAX_DUTY_NS - _MIN_DUTY_NS))
        duty_ns = max(_MIN_DUTY_NS, min(duty_ns, _MAX_DUTY_NS))
        self._write("duty_cycle", duty_ns)

    def enable(self) -> None:
        self._write("enable", 1)

    def disable(self) -> None:
        self._write("enable", 0)

    def close(self) -> None:
        try:
            self.disable()
            unexport = f"/sys/class/pwm/pwmchip{self._chip}/unexport"
            with open(unexport, "w") as f:
                f.write(str(self._channel))
        except OSError:
            pass


class PanTilt:
    """Controls pan/tilt servos via sysfs hardware PWM — jitter-free on Pi 5."""

    def __init__(self) -> None:
        self._pan_pwm = _HardwarePWM(_PWM_CHIP, _PAN_CHANNEL)
        self._tilt_pwm = _HardwarePWM(_PWM_CHIP, _TILT_CHANNEL)

        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Center on boot
        self._pan_pwm.set_angle(config.PAN_CENTER)
        self._tilt_pwm.set_angle(config.TILT_CENTER)
        self._pan_pwm.enable()
        self._tilt_pwm.enable()
        sleep(config.SERVO_MOVE_DELAY)

        log_info(
            f"PanTilt: hardware PWM ready — "
            f"pan={self.pan_angle}° tilt={self.tilt_angle}°"
        )

    # ── Internals ──────────────────────────────────────────────────────────

    def _clamp(self, value: int, lo: int, hi: int) -> int:
        return max(lo, min(value, hi))

    def _apply_pan(self, logical_angle: int) -> None:
        servo_angle = self._clamp(logical_angle + config.PAN_OFFSET, 0, 180)
        self._pan_pwm.set_angle(servo_angle)

    def _apply_tilt(self, logical_angle: int) -> None:
        servo_angle = self._clamp(logical_angle + config.TILT_OFFSET, 0, 180)
        self._tilt_pwm.set_angle(servo_angle)

    def _stop_current_movement(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1.0)
        self._stop_event.clear()
        self._thread = None

    def _start_movement(self, pan_delta: int, tilt_delta: int) -> None:
        self._stop_current_movement()

        def _loop() -> None:
            while not self._stop_event.is_set():
                if pan_delta != 0:
                    new_pan = self._clamp(
                        self.pan_angle + pan_delta, config.PAN_MIN, config.PAN_MAX
                    )
                    if new_pan != self.pan_angle:
                        self._apply_pan(new_pan)
                        self.pan_angle = new_pan

                if tilt_delta != 0:
                    new_tilt = self._clamp(
                        self.tilt_angle + tilt_delta, config.TILT_MIN, config.TILT_MAX
                    )
                    if new_tilt != self.tilt_angle:
                        self._apply_tilt(new_tilt)
                        self.tilt_angle = new_tilt

                self._stop_event.wait(_TICK_SEC)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    # ── Absolute positioning ───────────────────────────────────────────────

    def pan_to(self, angle: int) -> dict:
        """Pan to absolute angle."""
        self._stop_current_movement()
        clamped = self._clamp(angle, config.PAN_MIN, config.PAN_MAX)
        if clamped != angle:
            log_warning(f"Pan {angle}° clamped to {clamped}°")
        self._apply_pan(clamped)
        sleep(config.SERVO_MOVE_DELAY)
        old, self.pan_angle = self.pan_angle, clamped
        log_info(f"Pan: {old}° → {clamped}°")
        return {"status": "ok", "pan": self.pan_angle}

    def tilt_to(self, angle: int) -> dict:
        """Tilt to absolute angle."""
        self._stop_current_movement()
        clamped = self._clamp(angle, config.TILT_MIN, config.TILT_MAX)
        if clamped != angle:
            log_warning(f"Tilt {angle}° clamped to {clamped}°")
        self._apply_tilt(clamped)
        sleep(config.SERVO_MOVE_DELAY)
        old, self.tilt_angle = self.tilt_angle, clamped
        log_info(f"Tilt: {old}° → {clamped}°")
        return {"status": "ok", "tilt": self.tilt_angle}

    # ── Relative step moves ────────────────────────────────────────────────

    def pan_left(self, deg: int = 10) -> dict:
        return self.pan_to(self.pan_angle - deg * config.PAN_DIRECTION)

    def pan_right(self, deg: int = 10) -> dict:
        return self.pan_to(self.pan_angle + deg * config.PAN_DIRECTION)

    def tilt_up(self, deg: int = 10) -> dict:
        return self.tilt_to(self.tilt_angle + deg * config.TILT_DIRECTION)

    def tilt_down(self, deg: int = 10) -> dict:
        return self.tilt_to(self.tilt_angle - deg * config.TILT_DIRECTION)

    # ── Continuous movement ────────────────────────────────────────────────

    def tilt_up_start(self) -> dict:
        self._start_movement(0, _STEP_DEG * config.TILT_DIRECTION)
        return {"status": "ok", "action": "tilt_up_start"}

    def tilt_down_start(self) -> dict:
        self._start_movement(0, -_STEP_DEG * config.TILT_DIRECTION)
        return {"status": "ok", "action": "tilt_down_start"}

    def pan_left_start(self) -> dict:
        self._start_movement(-_STEP_DEG * config.PAN_DIRECTION, 0)
        return {"status": "ok", "action": "pan_left_start"}

    def pan_right_start(self) -> dict:
        self._start_movement(_STEP_DEG * config.PAN_DIRECTION, 0)
        return {"status": "ok", "action": "pan_right_start"}

    def up_left_start(self) -> dict:
        self._start_movement(-_STEP_DEG * config.PAN_DIRECTION, _STEP_DEG * config.TILT_DIRECTION)
        return {"status": "ok", "action": "up_left_start"}

    def up_right_start(self) -> dict:
        self._start_movement(_STEP_DEG * config.PAN_DIRECTION, _STEP_DEG * config.TILT_DIRECTION)
        return {"status": "ok", "action": "up_right_start"}

    def down_left_start(self) -> dict:
        self._start_movement(-_STEP_DEG * config.PAN_DIRECTION, -_STEP_DEG * config.TILT_DIRECTION)
        return {"status": "ok", "action": "down_left_start"}

    def down_right_start(self) -> dict:
        self._start_movement(_STEP_DEG * config.PAN_DIRECTION, -_STEP_DEG * config.TILT_DIRECTION)
        return {"status": "ok", "action": "down_right_start"}

    def servo_stop(self) -> dict:
        self._stop_current_movement()
        log_info(f"Servo stopped — pan={self.pan_angle}° tilt={self.tilt_angle}°")
        return {"status": "ok", "action": "servo_stop",
                "pan": self.pan_angle, "tilt": self.tilt_angle}

    # ── Utility ───────────────────────────────────────────────────────────

    def center(self) -> dict:
        self.pan_to(config.PAN_CENTER)
        self.tilt_to(config.TILT_CENTER)
        log_info(f"Camera: centered ({config.PAN_CENTER}°/{config.TILT_CENTER}°)")
        return {"status": "ok", "pan": config.PAN_CENTER, "tilt": config.TILT_CENTER}

    def get_angles(self) -> dict[str, int]:
        return {"pan": self.pan_angle, "tilt": self.tilt_angle}

    def set_as_current_center(self) -> None:
        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER
        log_info("Camera: current position set as center")

    def pan_scan(self, start_angle: int, end_angle: int, step: int = 2) -> None:
        start = self._clamp(start_angle, config.PAN_MIN, config.PAN_MAX)
        end = self._clamp(end_angle, config.PAN_MIN, config.PAN_MAX)
        angles = (
            range(start, end + 1, step) if start < end else range(start, end - 1, -step)
        )
        for angle in angles:
            self._apply_pan(angle)
            sleep(0.05)
            self.pan_angle = angle
        log_info(f"Pan scan complete at {end}°")

    def cleanup(self) -> None:
        self._stop_current_movement()
        try:
            self.center()
            sleep(0.5)
        except Exception:
            pass
        self._pan_pwm.close()
        self._tilt_pwm.close()
        log_info("PanTilt: hardware PWM released")
