#!/usr/bin/env python3
"""
PanTilt class for AI RC Car
Controls pan and tilt servos for camera movement
"""

import RPi.GPIO as GPIO
from utils.logger import log_debug, log_info, log_warning
import config
import time


class PanTilt:
    """Controls pan and tilt servos for camera positioning"""

    def __init__(self):
        """Initialize pan-tilt servos"""
        # GPIO.setmode() is handled by main.py before creating this object
        GPIO.setwarnings(False)

        # Get GPIO pins from config
        self.pan_pin = config.PAN_SERVO
        self.tilt_pin = config.TILT_SERVO

        GPIO.setup(self.pan_pin, GPIO.OUT)
        GPIO.setup(self.tilt_pin, GPIO.OUT)

        # 50Hz for servos
        self.pan_pwm = GPIO.PWM(self.pan_pin, 50)
        self.tilt_pwm = GPIO.PWM(self.tilt_pin, 50)

        self.pan_pwm.start(0)
        self.tilt_pwm.start(0)

        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER

        log_info(
            f"Camera: Pan-tilt initialized at current center "
            f"({self.pan_angle}°/{self.tilt_angle}°)"
        )

    def _angle_to_duty(self, angle: int) -> float:
        """Convert angle (0-180) to duty cycle (2-12%)."""
        # 0° = 2% duty, 90° = 7%, 180° = 12%
        return 2 + (angle / 180) * 10

    def _clamp_angle(self, angle: int, min_angle: int, max_angle: int) -> int:
        """Clamp angle to valid range"""
        return max(min_angle, min(angle, max_angle))

    def _apply_offset(self, angle: int, offset: int) -> int:
        """Apply calibration offset to a logical angle."""
        return angle + offset

    def _move_servo(self, pwm, angle: int) -> None:
        """Send a PWM command for the provided servo angle."""
        duty = self._angle_to_duty(angle)
        pwm.ChangeDutyCycle(duty)

    def _move_and_kill(self, pwm_object, angle: int, servo_name: str) -> None:
        """Move servo to angle then kill PWM signal to eliminate jitter."""
        duty = self._angle_to_duty(angle)
        pwm_object.ChangeDutyCycle(duty)
        log_debug(f"{servo_name}: Moving to {angle}°")
        time.sleep(config.SERVO_MOVE_DELAY)
        pwm_object.ChangeDutyCycle(0)
        log_debug(f"{servo_name}: PWM killed, holding at {angle}°")

    def set_as_current_center(self) -> None:
        """Mark current physical position as 90°/90° reference."""
        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER
        log_info(
            f"Camera: Current physical position set as center "
            f"({self.pan_angle}°/{self.tilt_angle}°)"
        )

    def pan_to(self, angle: int) -> None:
        """Pan to absolute angle using move and kill."""
        old_angle = self.pan_angle
        clamped_angle = self._clamp_angle(angle, config.PAN_MIN, config.PAN_MAX)

        if clamped_angle != angle:
            log_warning(f"Pan angle {angle}° clamped to {clamped_angle}°")

        if clamped_angle != old_angle:
            servo_angle = self._apply_offset(clamped_angle, config.PAN_OFFSET)
            self._move_and_kill(self.pan_pwm, servo_angle, "Pan")
            self.pan_angle = clamped_angle
            log_info(f"Pan: {old_angle}° → {clamped_angle}°")
        else:
            log_debug(f"Pan already at {clamped_angle}°, no movement")

    def tilt_to(self, angle: int) -> None:
        """Tilt to absolute angle using move and kill."""
        old_angle = self.tilt_angle
        clamped_angle = self._clamp_angle(angle, config.TILT_MIN, config.TILT_MAX)

        if clamped_angle != angle:
            log_warning(f"Tilt angle {angle}° clamped to {clamped_angle}°")

        if clamped_angle != old_angle:
            servo_angle = self._apply_offset(clamped_angle, config.TILT_OFFSET)
            self._move_and_kill(self.tilt_pwm, servo_angle, "Tilt")
            self.tilt_angle = clamped_angle
            log_info(f"Tilt: {old_angle}° → {clamped_angle}°")
        else:
            log_debug(f"Tilt already at {clamped_angle}°, no movement")

    def pan_left(self, deg: int = 10) -> None:
        """Pan left by given degrees."""
        new_angle = self.pan_angle - deg
        self.pan_to(new_angle)
        log_info(f"Camera: Pan left {deg}°")

    def pan_right(self, deg: int = 10) -> None:
        """Pan right by given degrees."""
        new_angle = self.pan_angle + deg
        self.pan_to(new_angle)
        log_info(f"Camera: Pan right {deg}°")

    def tilt_up(self, deg: int = 10) -> None:
        """Tilt up by given degrees."""
        new_angle = self.tilt_angle + deg
        self.tilt_to(new_angle)
        log_info(f"Camera: Tilt up {deg}°")

    def tilt_down(self, deg: int = 10) -> None:
        """Tilt down by given degrees."""
        new_angle = self.tilt_angle - deg
        self.tilt_to(new_angle)
        log_info(f"Camera: Tilt down {deg}°")

    def center(self) -> None:
        """Reset to 90° center."""
        self.pan_to(config.PAN_CENTER)
        self.tilt_to(config.TILT_CENTER)
        log_info(
            f"Camera: Center command completed "
            f"({config.PAN_CENTER}°/{config.TILT_CENTER}°)"
        )

    def get_angles(self) -> dict[str, int]:
        """Returns current angles."""
        return {"pan": self.pan_angle, "tilt": self.tilt_angle}

    def hold_position(self, angle: int, duration_sec: int, axis: str = "pan") -> None:
        """Hold position by refreshing PWM periodically (for heavy loads)."""
        end_time = time.time() + duration_sec
        pwm = self.pan_pwm if axis == "pan" else self.tilt_pwm

        while time.time() < end_time:
            duty = self._angle_to_duty(angle)
            pwm.ChangeDutyCycle(duty)
            time.sleep(0.05)  # 50ms pulse
            pwm.ChangeDutyCycle(0)
            time.sleep(0.95)  # 950ms rest

    def pan_scan(self, start_angle: int, end_angle: int, step: int = 2) -> None:
        """Scan from start to end angle smoothly (keep PWM active during movement)."""
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
            time.sleep(0.05)
            self.pan_angle = angle

        # Kill PWM after scan complete
        time.sleep(config.SERVO_MOVE_DELAY)
        self.pan_pwm.ChangeDutyCycle(0)
        log_info(f"Scan complete, holding at {clamped_end}°")

    def cleanup(self) -> None:
        """Clean shutdown."""
        try:
            self.center()
            self.pan_pwm.ChangeDutyCycle(0)
            self.tilt_pwm.ChangeDutyCycle(0)
            time.sleep(0.1)
            self.pan_pwm.stop()
            self.tilt_pwm.stop()
        except Exception as e:
            log_warning(f"Pan-tilt cleanup error: {e}")
