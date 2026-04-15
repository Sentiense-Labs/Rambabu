#!/usr/bin/env python3
"""
PanTilt class for AI RC Car.
Controls pan/tilt servos via RPi.GPIO software PWM with move-and-kill pattern.

Move-and-kill: send PWM for SERVO_MOVE_DELAY, then set duty to 0.
The servo holds position mechanically — no jitter at rest.

Joystick control model:
  - SERVO_<DIRECTION>_START  → continuous smooth movement (steps with move-and-kill)
  - SERVO_STOP               → holds position, kills PWM
  - SERVO_CENTER             → smoothly returns to center

Supports 8 directions: UP, DOWN, LEFT, RIGHT, UP_LEFT, UP_RIGHT, DOWN_LEFT, DOWN_RIGHT
"""

import RPi.GPIO as GPIO
import threading
from time import sleep
import config
from utils.logger import log_debug, log_info, log_warning

# Continuous movement
_STEP_DEG: int = 1
_TICK_SEC: float = 0.05


def _angle_to_duty(angle: int) -> float:
    """Convert angle (0-180) to duty cycle (2.5-12.5%)."""
    return 2.5 + (angle / 180) * 10


class PanTilt:
    """Controls pan/tilt servos via RPi.GPIO software PWM — move-and-kill for jitter-free hold."""

    def __init__(self) -> None:
        # GPIO.setmode() is handled by main.py before creating this object
        GPIO.setwarnings(False)

        GPIO.setup(config.PAN_SERVO, GPIO.OUT)
        GPIO.setup(config.TILT_SERVO, GPIO.OUT)

        self._pan_pwm = GPIO.PWM(config.PAN_SERVO, config.SERVO_PWM_FREQ)
        self._tilt_pwm = GPIO.PWM(config.TILT_SERVO, config.SERVO_PWM_FREQ)
        self._pan_pwm.start(0)
        self._tilt_pwm.start(0)

        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Center on boot
        self._move_and_kill_pan(config.PAN_CENTER)
        self._move_and_kill_tilt(config.TILT_CENTER)

        log_info(
            f"PanTilt: RPi.GPIO PWM ready — "
            f"pan={self.pan_angle}° tilt={self.tilt_angle}°"
        )

    # ── Internals ──────────────────────────────────────────────────────────

    def _clamp(self, value: int, lo: int, hi: int) -> int:
        return max(lo, min(value, hi))

    def _move_and_kill_pan(self, logical_angle: int) -> None:
        """Send pan PWM pulse then kill — servo holds mechanically."""
        servo_angle = self._clamp(logical_angle + config.PAN_OFFSET, 0, 180)
        self._pan_pwm.ChangeDutyCycle(_angle_to_duty(servo_angle))
        sleep(config.SERVO_MOVE_DELAY)
        self._pan_pwm.ChangeDutyCycle(0)

    def _move_and_kill_tilt(self, logical_angle: int) -> None:
        """Send tilt PWM pulse then kill — servo holds mechanically."""
        servo_angle = self._clamp(logical_angle + config.TILT_OFFSET, 0, 180)
        self._tilt_pwm.ChangeDutyCycle(_angle_to_duty(servo_angle))
        sleep(config.SERVO_MOVE_DELAY)
        self._tilt_pwm.ChangeDutyCycle(0)

    def _apply_pan(self, logical_angle: int) -> None:
        """Send pan PWM (no kill — caller manages duty cycle lifecycle)."""
        servo_angle = self._clamp(logical_angle + config.PAN_OFFSET, 0, 180)
        self._pan_pwm.ChangeDutyCycle(_angle_to_duty(servo_angle))

    def _apply_tilt(self, logical_angle: int) -> None:
        """Send tilt PWM (no kill — caller manages duty cycle lifecycle)."""
        servo_angle = self._clamp(logical_angle + config.TILT_OFFSET, 0, 180)
        self._tilt_pwm.ChangeDutyCycle(_angle_to_duty(servo_angle))

    def _kill_pwm(self) -> None:
        """Kill both PWM signals — servos hold position mechanically."""
        self._pan_pwm.ChangeDutyCycle(0)
        self._tilt_pwm.ChangeDutyCycle(0)

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
                moved = False

                if pan_delta != 0:
                    new_pan = self._clamp(
                        self.pan_angle + pan_delta, config.PAN_MIN, config.PAN_MAX
                    )
                    if new_pan != self.pan_angle:
                        self._apply_pan(new_pan)
                        self.pan_angle = new_pan
                        moved = True

                if tilt_delta != 0:
                    new_tilt = self._clamp(
                        self.tilt_angle + tilt_delta, config.TILT_MIN, config.TILT_MAX
                    )
                    if new_tilt != self.tilt_angle:
                        self._apply_tilt(new_tilt)
                        self.tilt_angle = new_tilt
                        moved = True

                if not moved:
                    break

                self._stop_event.wait(_TICK_SEC)

            # Settled — kill PWM to eliminate jitter at rest
            self._kill_pwm()
            log_debug(
                f"PanTilt: movement stopped — pan={self.pan_angle} tilt={self.tilt_angle}"
            )

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    # ── Absolute positioning ───────────────────────────────────────────────

    def pan_to(self, angle: int) -> dict:
        """Pan to absolute angle."""
        self._stop_current_movement()
        clamped = self._clamp(angle, config.PAN_MIN, config.PAN_MAX)
        if clamped != angle:
            log_warning(f"Pan {angle}° clamped to {clamped}°")
        self._move_and_kill_pan(clamped)
        old, self.pan_angle = self.pan_angle, clamped
        log_info(f"Pan: {old}° → {clamped}°")
        return {"status": "ok", "pan": self.pan_angle}

    def tilt_to(self, angle: int) -> dict:
        """Tilt to absolute angle."""
        self._stop_current_movement()
        clamped = self._clamp(angle, config.TILT_MIN, config.TILT_MAX)
        if clamped != angle:
            log_warning(f"Tilt {angle}° clamped to {clamped}°")
        self._move_and_kill_tilt(clamped)
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
        self._start_movement(
            -_STEP_DEG * config.PAN_DIRECTION, _STEP_DEG * config.TILT_DIRECTION
        )
        return {"status": "ok", "action": "up_left_start"}

    def up_right_start(self) -> dict:
        self._start_movement(
            _STEP_DEG * config.PAN_DIRECTION, _STEP_DEG * config.TILT_DIRECTION
        )
        return {"status": "ok", "action": "up_right_start"}

    def down_left_start(self) -> dict:
        self._start_movement(
            -_STEP_DEG * config.PAN_DIRECTION, -_STEP_DEG * config.TILT_DIRECTION
        )
        return {"status": "ok", "action": "down_left_start"}

    def down_right_start(self) -> dict:
        self._start_movement(
            _STEP_DEG * config.PAN_DIRECTION, -_STEP_DEG * config.TILT_DIRECTION
        )
        return {"status": "ok", "action": "down_right_start"}

    def servo_stop(self) -> dict:
        self._stop_current_movement()
        log_info(f"Servo stopped — pan={self.pan_angle}° tilt={self.tilt_angle}°")
        return {
            "status": "ok",
            "action": "servo_stop",
            "pan": self.pan_angle,
            "tilt": self.tilt_angle,
        }

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
            self._move_and_kill_pan(angle)
            self.pan_angle = angle
        log_info(f"Pan scan complete at {end}°")

    def cleanup(self) -> None:
        self._stop_current_movement()
        try:
            self.center()
            sleep(0.5)
        except Exception:
            pass
        self._pan_pwm.stop()
        self._tilt_pwm.stop()
        log_info("PanTilt: PWM stopped")
