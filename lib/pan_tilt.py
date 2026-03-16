#!/usr/bin/env python3
"""
PanTilt class for AI RC Car
Controls pan and tilt servos using RPi.GPIO software PWM with move-and-kill method
"""

import RPi.GPIO as GPIO
from time import sleep
import config
from utils.logger import log_debug, log_info, log_warning, log_error


class PanTilt:
    """Controls pan and tilt servos using RPi.GPIO software PWM."""

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

        log_info(
            f"Camera: Pan-tilt initialized with software PWM "
            f"({self.pan_angle}/{self.tilt_angle})"
        )

    def _clamp_angle(self, angle: int, min_angle: int, max_angle: int) -> int:
        """Clamp angle to valid range."""
        return max(min_angle, min(angle, max_angle))

    def _apply_offset(self, angle: int, offset: int) -> int:
        """Apply calibration offset to a logical angle."""
        return angle + offset

    def _angle_to_duty(self, angle: int) -> float:
        """Convert angle (0-180) to duty cycle (2.5-12.5%)."""
        return 2.5 + (angle / 180) * 10

    def _move_and_kill(self, pwm_object, angle: int, servo_name: str) -> None:
        """Send PWM signal briefly then kill to eliminate jitter."""
        duty = self._angle_to_duty(angle)
        pwm_object.ChangeDutyCycle(duty)
        log_debug(f"{servo_name}: Moving to {angle}")
        sleep(config.SERVO_MOVE_DELAY)
        pwm_object.ChangeDutyCycle(0)
        log_debug(f"{servo_name}: PWM killed, holding at {angle}")

    def set_as_current_center(self) -> dict:
        """Mark current physical position as 90/90 reference."""
        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER
        log_info(
            f"Camera: Current physical position set as center "
            f"({self.pan_angle}/{self.tilt_angle})"
        )
        return {"status": "ok", "pan": self.pan_angle, "tilt": self.tilt_angle}

    def pan_to(self, angle: int) -> dict:
        """Pan to absolute angle using move-and-kill method."""
        old_angle = self.pan_angle
        clamped_angle = self._clamp_angle(angle, config.PAN_MIN, config.PAN_MAX)
        clamped = clamped_angle != angle

        if clamped:
            log_warning(f"Pan angle {angle} clamped to {clamped_angle}")

        if clamped_angle != old_angle:
            servo_angle = self._apply_offset(clamped_angle, config.PAN_OFFSET)
            self._move_and_kill(self.pan_pwm, servo_angle, "Pan")
            self.pan_angle = clamped_angle
            log_info(f"Pan: {old_angle} -> {clamped_angle}")
        else:
            log_debug(f"Pan already at {clamped_angle}, no movement")

        return {
            "status": "ok",
            "pan": self.pan_angle,
            "clamped": clamped,
        }

    def tilt_to(self, angle: int) -> dict:
        """Tilt to absolute angle using move-and-kill method."""
        old_angle = self.tilt_angle
        clamped_angle = self._clamp_angle(angle, config.TILT_MIN, config.TILT_MAX)
        clamped = clamped_angle != angle

        if clamped:
            log_warning(f"Tilt angle {angle} clamped to {clamped_angle}")

        if clamped_angle != old_angle:
            servo_angle = self._apply_offset(clamped_angle, config.TILT_OFFSET)
            self._move_and_kill(self.tilt_pwm, servo_angle, "Tilt")
            self.tilt_angle = clamped_angle
            log_info(f"Tilt: {old_angle} -> {clamped_angle}")
        else:
            log_debug(f"Tilt already at {clamped_angle}, no movement")

        return {
            "status": "ok",
            "tilt": self.tilt_angle,
            "clamped": clamped,
        }

    def pan_left(self, deg: int = 10) -> dict:
        """Pan left by given degrees."""
        result = self.pan_to(self.pan_angle - deg)
        log_info(f"Camera: Pan left {deg}")
        return result

    def pan_right(self, deg: int = 10) -> dict:
        """Pan right by given degrees."""
        result = self.pan_to(self.pan_angle + deg)
        log_info(f"Camera: Pan right {deg}")
        return result

    def tilt_up(self, deg: int = 10) -> dict:
        """Tilt up by given degrees."""
        result = self.tilt_to(self.tilt_angle + deg)
        log_info(f"Camera: Tilt up {deg}")
        return result

    def tilt_down(self, deg: int = 10) -> dict:
        """Tilt down by given degrees."""
        result = self.tilt_to(self.tilt_angle - deg)
        log_info(f"Camera: Tilt down {deg}")
        return result

    def center(self) -> dict:
        """Reset to 90 center."""
        self.pan_to(config.PAN_CENTER)
        self.tilt_to(config.TILT_CENTER)
        log_info(
            f"Camera: Center command completed "
            f"({config.PAN_CENTER}/{config.TILT_CENTER})"
        )
        return {"status": "ok", "pan": self.pan_angle, "tilt": self.tilt_angle}

    def get_angles(self) -> dict[str, int]:
        """Returns current angles."""
        return {"pan": self.pan_angle, "tilt": self.tilt_angle}

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
        """Scan from start to end angle smoothly using move-and-kill."""
        clamped_start = self._clamp_angle(start_angle, config.PAN_MIN, config.PAN_MAX)
        clamped_end = self._clamp_angle(end_angle, config.PAN_MIN, config.PAN_MAX)

        if clamped_start < clamped_end:
            angles = range(clamped_start, clamped_end + 1, step)
        else:
            angles = range(clamped_start, clamped_end - 1, -step)

        for angle in angles:
            servo_angle = self._apply_offset(angle, config.PAN_OFFSET)
            duty = self._angle_to_duty(servo_angle)
            self.pan_pwm.ChangeDutyCycle(duty)
            sleep(0.05)
            self.pan_angle = angle

        self.pan_pwm.ChangeDutyCycle(0)
        log_info(f"Scan complete, holding at {clamped_end}")
        return {"status": "ok", "pan": self.pan_angle}

    def cleanup(self) -> None:
        """Clean shutdown."""
        try:
            self.center()
            sleep(0.5)
            self.pan_pwm.stop()
            self.tilt_pwm.stop()
            GPIO.cleanup()
        except Exception as e:
            log_error(f"Pan-tilt cleanup error: {e}")
