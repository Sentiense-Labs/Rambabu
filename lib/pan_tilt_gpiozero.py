#!/usr/bin/env python3
"""
PanTilt class for AI RC Car
Controls pan and tilt servos using hardware PWM (gpiozero + lgpio)
"""

from gpiozero import AngularServo
from gpiozero.pins.lgpio import LGPIOFactory
from time import sleep
import config
from utils.logger import log_debug, log_info, log_warning


class PanTilt:
    """Controls pan and tilt servos using hardware PWM for jitter-free operation."""

    def __init__(self):
        """Initialize pan-tilt servos with hardware PWM."""
        # Force hardware PWM via lgpio factory
        factory = LGPIOFactory()

        # Initialize pan servo on GPIO 12 (hardware PWM0)
        # Use default angle range (-90 to 90) and map our angles in methods
        self.pan_servo = AngularServo(
            config.PAN_SERVO,
            min_pulse_width=0.5 / 1000,  # 0.5ms
            max_pulse_width=2.5 / 1000,  # 2.5ms
            pin_factory=factory,
        )

        # Initialize tilt servo on GPIO 13 (hardware PWM1)
        # Use default angle range (-90 to 90) and map our angles in methods
        self.tilt_servo = AngularServo(
            config.TILT_SERVO,
            min_pulse_width=0.5 / 1000,
            max_pulse_width=2.5 / 1000,
            pin_factory=factory,
        )

        # Track current angles
        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER

        log_info(
            f"Camera: Pan-tilt initialized with hardware PWM "
            f"({self.pan_angle}°/{self.tilt_angle}°)"
        )

    def _clamp_angle(self, angle: int, min_angle: int, max_angle: int) -> int:
        """Clamp angle to valid range."""
        return max(min_angle, min(angle, max_angle))

    def _apply_offset(self, angle: int, offset: int) -> int:
        """Apply calibration offset to a logical angle."""
        return angle + offset

    def set_as_current_center(self) -> None:
        """Mark current physical position as 90°/90° reference."""
        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER
        log_info(
            f"Camera: Current physical position set as center "
            f"({self.pan_angle}°/{self.tilt_angle}°)"
        )

    def pan_to(self, angle: int) -> None:
        """Pan to absolute angle using hardware PWM."""
        old_angle = self.pan_angle
        clamped_angle = self._clamp_angle(angle, config.PAN_MIN, config.PAN_MAX)

        if clamped_angle != angle:
            log_warning(f"Pan angle {angle}° clamped to {clamped_angle}°")

        if clamped_angle != old_angle:
            servo_angle = self._apply_offset(clamped_angle, config.PAN_OFFSET)
            # Map 0-180 to -90 to 90 for gpiozero
            gpiozero_angle = servo_angle - 90
            self.pan_servo.angle = gpiozero_angle
            sleep(config.SERVO_MOVE_DELAY)
            self.pan_angle = clamped_angle
            log_info(f"Pan: {old_angle}° → {clamped_angle}°")
        else:
            log_debug(f"Pan already at {clamped_angle}°, no movement")

    def tilt_to(self, angle: int) -> None:
        """Tilt to absolute angle using hardware PWM."""
        old_angle = self.tilt_angle
        clamped_angle = self._clamp_angle(angle, config.TILT_MIN, config.TILT_MAX)

        if clamped_angle != angle:
            log_warning(f"Tilt angle {angle}° clamped to {clamped_angle}°")

        if clamped_angle != old_angle:
            servo_angle = self._apply_offset(clamped_angle, config.TILT_OFFSET)
            # Map 0-180 to -90 to 90 for gpiozero
            gpiozero_angle = servo_angle - 90
            self.tilt_servo.angle = gpiozero_angle
            sleep(config.SERVO_MOVE_DELAY)
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
        # With hardware PWM, we can just keep the angle set
        # No need to refresh - hardware handles it
        servo = self.pan_servo if axis == "pan" else self.tilt_servo
        # Map 0-180 to -90 to 90 for gpiozero
        gpiozero_angle = angle - 90
        servo.angle = gpiozero_angle
        sleep(duration_sec)

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
            # Map 0-180 to -90 to 90 for gpiozero
            gpiozero_angle = servo_angle - 90
            self.pan_servo.angle = gpiozero_angle
            sleep(0.05)
            self.pan_angle = angle

        # Hardware PWM is stable, no need to kill
        log_info(f"Scan complete, holding at {clamped_end}°")

    def cleanup(self) -> None:
        """Clean shutdown."""
        try:
            self.center()
            self.pan_servo.close()
            self.tilt_servo.close()
        except Exception:
            pass  # Ignore cleanup errors
