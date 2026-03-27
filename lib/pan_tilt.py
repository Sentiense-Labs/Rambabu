#!/usr/bin/env python3
"""
PanTilt class for AI RC Car
Controls pan and tilt servos using RPi.GPIO software PWM.

Joystick control model:
  - send  SERVO_<DIRECTION>_START  when joystick pushed  → continuous smooth movement
  - send  SERVO_STOP               when joystick released → holds position, kills PWM
  - send  SERVO_CENTER             anytime               → smoothly returns to center

Supports 8 directions: UP, DOWN, LEFT, RIGHT, UP_LEFT, UP_RIGHT, DOWN_LEFT, DOWN_RIGHT
"""

import RPi.GPIO as GPIO
import threading
from time import sleep
import config
from utils.logger import log_debug, log_info, log_warning, log_error

# Degrees moved per tick during continuous movement
_STEP_DEG: int = 1
# Seconds between ticks — 50 ms = 20°/sec smooth sweep
_TICK_SEC: float = 0.05


class PanTilt:
    """Controls pan and tilt servos with smooth joystick-friendly movement."""

    def __init__(self):
        """Initialize pan-tilt servos."""
        # GPIO.setmode() is handled by main.py before creating this object
        GPIO.setwarnings(False)

        self.pan_pin = config.PAN_SERVO
        self.tilt_pin = config.TILT_SERVO
        GPIO.setup(self.pan_pin, GPIO.OUT)
        GPIO.setup(self.tilt_pin, GPIO.OUT)

        self.pan_pwm = GPIO.PWM(self.pan_pin, config.SERVO_PWM_FREQ)
        self.tilt_pwm = GPIO.PWM(self.tilt_pin, config.SERVO_PWM_FREQ)
        self.pan_pwm.start(0)
        self.tilt_pwm.start(0)

        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER

        # Continuous movement state
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        log_info(
            f"PanTilt: initialized — pan={self.pan_angle} tilt={self.tilt_angle}"
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    def _angle_to_duty(self, angle: int) -> float:
        """Convert angle (0-180) to duty cycle (2.5-12.5%)."""
        return 2.5 + (angle / 180) * 10

    def _clamp(self, value: int, lo: int, hi: int) -> int:
        return max(lo, min(value, hi))

    def _apply_pan_servo(self, logical_angle: int) -> None:
        """Send current pan angle to PWM (keeps PWM live — no kill)."""
        servo_angle = self._clamp(
            logical_angle + config.PAN_OFFSET, 0, 180
        )
        self.pan_pwm.ChangeDutyCycle(self._angle_to_duty(servo_angle))

    def _apply_tilt_servo(self, logical_angle: int) -> None:
        """Send current tilt angle to PWM (keeps PWM live — no kill)."""
        servo_angle = self._clamp(
            logical_angle + config.TILT_OFFSET, 0, 180
        )
        self.tilt_pwm.ChangeDutyCycle(self._angle_to_duty(servo_angle))

    def _kill_pwm(self) -> None:
        """Kill PWM signal after servo has settled — eliminates jitter at rest."""
        sleep(config.SERVO_MOVE_DELAY)
        self.pan_pwm.ChangeDutyCycle(0)
        self.tilt_pwm.ChangeDutyCycle(0)

    def _stop_current_movement(self) -> None:
        """Signal running thread to stop and wait for it to exit."""
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1.0)
        self._stop_event.clear()
        self._thread = None

    def _start_movement(self, pan_delta: int, tilt_delta: int) -> None:
        """
        Launch background thread that moves pan/tilt by (pan_delta, tilt_delta)
        degrees per tick until stopped.

        PWM stays ON during movement for smooth jitter-free sweep.
        PWM is killed only after the thread exits (servo settled).
        """
        self._stop_current_movement()

        def _loop() -> None:
            # Keep PWM alive for the entire duration — no move-and-kill between steps
            while not self._stop_event.is_set():
                moved = False

                if pan_delta != 0:
                    new_pan = self._clamp(
                        self.pan_angle + pan_delta,
                        config.PAN_MIN, config.PAN_MAX
                    )
                    if new_pan != self.pan_angle:
                        self.pan_angle = new_pan
                        self._apply_pan_servo(self.pan_angle)
                        moved = True

                if tilt_delta != 0:
                    new_tilt = self._clamp(
                        self.tilt_angle + tilt_delta,
                        config.TILT_MIN, config.TILT_MAX
                    )
                    if new_tilt != self.tilt_angle:
                        self.tilt_angle = new_tilt
                        self._apply_tilt_servo(self.tilt_angle)
                        moved = True

                if not moved:
                    # Hit both limits — nothing more to do
                    break

                self._stop_event.wait(timeout=_TICK_SEC)

            # Settled — kill PWM to remove jitter at rest
            self._kill_pwm()
            log_debug(
                f"PanTilt: movement stopped — pan={self.pan_angle} tilt={self.tilt_angle}"
            )

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    # ── 8-direction start methods (joystick held) ────────────────────────────

    def tilt_up_start(self) -> dict:
        """Start continuous tilt upward. Call servo_stop() to halt."""
        self._start_movement(0, _STEP_DEG * config.TILT_DIRECTION)
        log_info("PanTilt: tilt UP start")
        return {"status": "ok", "direction": "up"}

    def tilt_down_start(self) -> dict:
        """Start continuous tilt downward. Call servo_stop() to halt."""
        self._start_movement(0, -_STEP_DEG * config.TILT_DIRECTION)
        log_info("PanTilt: tilt DOWN start")
        return {"status": "ok", "direction": "down"}

    def pan_left_start(self) -> dict:
        """Start continuous pan left. Call servo_stop() to halt."""
        self._start_movement(-_STEP_DEG * config.PAN_DIRECTION, 0)
        log_info("PanTilt: pan LEFT start")
        return {"status": "ok", "direction": "left"}

    def pan_right_start(self) -> dict:
        """Start continuous pan right. Call servo_stop() to halt."""
        self._start_movement(_STEP_DEG * config.PAN_DIRECTION, 0)
        log_info("PanTilt: pan RIGHT start")
        return {"status": "ok", "direction": "right"}

    def up_left_start(self) -> dict:
        """Start continuous diagonal up-left. Call servo_stop() to halt."""
        self._start_movement(
            -_STEP_DEG * config.PAN_DIRECTION,
             _STEP_DEG * config.TILT_DIRECTION,
        )
        log_info("PanTilt: UP-LEFT start")
        return {"status": "ok", "direction": "up_left"}

    def up_right_start(self) -> dict:
        """Start continuous diagonal up-right. Call servo_stop() to halt."""
        self._start_movement(
             _STEP_DEG * config.PAN_DIRECTION,
             _STEP_DEG * config.TILT_DIRECTION,
        )
        log_info("PanTilt: UP-RIGHT start")
        return {"status": "ok", "direction": "up_right"}

    def down_left_start(self) -> dict:
        """Start continuous diagonal down-left. Call servo_stop() to halt."""
        self._start_movement(
            -_STEP_DEG * config.PAN_DIRECTION,
            -_STEP_DEG * config.TILT_DIRECTION,
        )
        log_info("PanTilt: DOWN-LEFT start")
        return {"status": "ok", "direction": "down_left"}

    def down_right_start(self) -> dict:
        """Start continuous diagonal down-right. Call servo_stop() to halt."""
        self._start_movement(
             _STEP_DEG * config.PAN_DIRECTION,
            -_STEP_DEG * config.TILT_DIRECTION,
        )
        log_info("PanTilt: DOWN-RIGHT start")
        return {"status": "ok", "direction": "down_right"}

    def servo_stop(self) -> dict:
        """Stop any continuous movement and hold current position."""
        self._stop_current_movement()
        log_info(f"PanTilt: STOP — holding pan={self.pan_angle} tilt={self.tilt_angle}")
        return {"status": "ok", "direction": "stopped",
                "pan": self.pan_angle, "tilt": self.tilt_angle}

    # ── Center return ─────────────────────────────────────────────────────────

    def center(self) -> dict:
        """Smoothly return both axes to center position."""
        self._stop_current_movement()

        def _go_to_center() -> None:
            while not self._stop_event.is_set():
                pan_done = self.pan_angle == config.PAN_CENTER
                tilt_done = self.tilt_angle == config.TILT_CENTER

                if pan_done and tilt_done:
                    break

                if not pan_done:
                    step = _STEP_DEG if self.pan_angle < config.PAN_CENTER else -_STEP_DEG
                    self.pan_angle = self._clamp(
                        self.pan_angle + step, config.PAN_MIN, config.PAN_MAX
                    )
                    self._apply_pan_servo(self.pan_angle)

                if not tilt_done:
                    step = _STEP_DEG if self.tilt_angle < config.TILT_CENTER else -_STEP_DEG
                    self.tilt_angle = self._clamp(
                        self.tilt_angle + step, config.TILT_MIN, config.TILT_MAX
                    )
                    self._apply_tilt_servo(self.tilt_angle)

                self._stop_event.wait(timeout=_TICK_SEC)

            self._kill_pwm()
            log_info(f"PanTilt: centered — pan={self.pan_angle} tilt={self.tilt_angle}")

        self._thread = threading.Thread(target=_go_to_center, daemon=True)
        self._thread.start()
        log_info("PanTilt: CENTER return started")
        return {"status": "ok", "direction": "centering",
                "target_pan": config.PAN_CENTER, "target_tilt": config.TILT_CENTER}

    # ── Single-step methods (kept for backward compatibility) ─────────────────

    def _move_and_kill(self, pwm_object, angle: int, servo_name: str) -> None:
        """Send PWM signal briefly then kill to eliminate jitter (single step)."""
        duty = self._angle_to_duty(angle)
        pwm_object.ChangeDutyCycle(duty)
        log_debug(f"{servo_name}: moving to {angle}")
        sleep(config.SERVO_MOVE_DELAY)
        pwm_object.ChangeDutyCycle(0)

    def pan_to(self, angle: int) -> dict:
        """Pan to absolute angle (single move)."""
        self._stop_current_movement()
        clamped = self._clamp(angle, config.PAN_MIN, config.PAN_MAX)
        if clamped != angle:
            log_warning(f"Pan angle {angle} clamped to {clamped}")
        if clamped != self.pan_angle:
            servo_angle = clamped + config.PAN_OFFSET
            self._move_and_kill(self.pan_pwm, servo_angle, "Pan")
            self.pan_angle = clamped
        return {"status": "ok", "pan": self.pan_angle, "clamped": clamped != angle}

    def tilt_to(self, angle: int) -> dict:
        """Tilt to absolute angle (single move)."""
        self._stop_current_movement()
        clamped = self._clamp(angle, config.TILT_MIN, config.TILT_MAX)
        if clamped != angle:
            log_warning(f"Tilt angle {angle} clamped to {clamped}")
        if clamped != self.tilt_angle:
            servo_angle = clamped + config.TILT_OFFSET
            self._move_and_kill(self.tilt_pwm, servo_angle, "Tilt")
            self.tilt_angle = clamped
        return {"status": "ok", "tilt": self.tilt_angle, "clamped": clamped != angle}

    def pan_left(self, deg: int = 10) -> dict:
        """Pan left by given degrees (single step)."""
        return self.pan_to(self.pan_angle - deg * config.PAN_DIRECTION)

    def pan_right(self, deg: int = 10) -> dict:
        """Pan right by given degrees (single step)."""
        return self.pan_to(self.pan_angle + deg * config.PAN_DIRECTION)

    def tilt_up(self, deg: int = 10) -> dict:
        """Tilt up by given degrees (single step)."""
        return self.tilt_to(self.tilt_angle + deg * config.TILT_DIRECTION)

    def tilt_down(self, deg: int = 10) -> dict:
        """Tilt down by given degrees (single step)."""
        return self.tilt_to(self.tilt_angle - deg * config.TILT_DIRECTION)

    # ── Getters ───────────────────────────────────────────────────────────────

    def get_angles(self) -> dict[str, int]:
        """Returns current angles."""
        return {"pan": self.pan_angle, "tilt": self.tilt_angle}

    def set_as_current_center(self) -> dict:
        """Mark current physical position as reference center."""
        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER
        log_info(f"PanTilt: center reference set ({self.pan_angle}/{self.tilt_angle})")
        return {"status": "ok", "pan": self.pan_angle, "tilt": self.tilt_angle}

    def hold_position(self, angle: int, duration_sec: int, axis: str = "pan") -> dict:
        """Hold position by refreshing PWM periodically (for heavy loads)."""
        from time import time as now
        pwm = self.pan_pwm if axis == "pan" else self.tilt_pwm
        duty = self._angle_to_duty(angle)
        end_time = now() + duration_sec
        while now() < end_time:
            pwm.ChangeDutyCycle(duty)
            sleep(0.1)
        pwm.ChangeDutyCycle(0)
        return {"status": "ok", "axis": axis, "angle": angle}

    def pan_scan(self, start_angle: int, end_angle: int, step: int = 2) -> dict:
        """Scan from start to end angle smoothly."""
        clamped_start = self._clamp(start_angle, config.PAN_MIN, config.PAN_MAX)
        clamped_end = self._clamp(end_angle, config.PAN_MIN, config.PAN_MAX)
        angles = (
            range(clamped_start, clamped_end + 1, step)
            if clamped_start < clamped_end
            else range(clamped_start, clamped_end - 1, -step)
        )
        for angle in angles:
            servo_angle = angle + config.PAN_OFFSET
            self.pan_pwm.ChangeDutyCycle(self._angle_to_duty(servo_angle))
            sleep(0.05)
            self.pan_angle = angle
        self.pan_pwm.ChangeDutyCycle(0)
        log_info(f"PanTilt: scan complete, holding at pan={clamped_end}")
        return {"status": "ok", "pan": self.pan_angle}

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        """Clean shutdown — stop movement, center, kill PWM."""
        try:
            self._stop_current_movement()
            self.pan_pwm.stop()
            self.tilt_pwm.stop()
        except Exception as e:
            log_error(f"PanTilt cleanup error: {e}")
