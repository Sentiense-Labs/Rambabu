#!/usr/bin/env python3
"""
PanTilt class for AI RC Car.
Controls pan/tilt servos via PCA9685 I2C PWM driver (smbus2).

Move-and-kill pattern: send PWM pulse, wait for servo to settle,
then turn off the channel. Servo holds position mechanically —
no jitter, no buzzing, no current draw at rest.

During continuous joystick movement, PWM stays alive for smooth sweeps.
PWM is killed only when movement stops.

Supports 8 directions: UP, DOWN, LEFT, RIGHT, UP_LEFT, UP_RIGHT, DOWN_LEFT, DOWN_RIGHT
"""

import threading
import time

from smbus2 import SMBus

import config
from utils.logger import log_debug, log_info, log_warning, log_error

# PCA9685 registers
_MODE1 = 0x00
_PRESCALE = 0xFE
_LED0_ON_L = 0x06

_I2C_BUS = 1

# Continuous movement (joystick)
_PAN_STEP_DEG: int = 1
_PAN_TICK_SEC: float = 0.05
_TILT_STEP_DEG: int = 5
_TILT_TICK_SEC: float = 0.10

# Smooth one-shot sweep (used by pan_to / tilt_to)
_PAN_SWEEP_STEP: int = 1  # degrees per I2C write
_PAN_SWEEP_DELAY: float = 0.02  # seconds between steps (~50 steps/s)
_TILT_SWEEP_STEP: int = 2
_TILT_SWEEP_DELAY: float = 0.04

# SG90 pulse range at 50Hz (20ms period), in 12-bit ticks (0-4095)
_MIN_TICKS = 102  # 0.5ms → 0°
_MAX_TICKS = 512  # 2.5ms → 180°


def _angle_to_ticks(angle: int) -> int:
    """Convert angle (0-180) to PCA9685 OFF tick count."""
    return _MIN_TICKS + int((angle / 180.0) * (_MAX_TICKS - _MIN_TICKS))


def _prescale_value(freq_hz: int) -> int:
    """Calculate PCA9685 prescale for a given frequency."""
    return round(25_000_000 / (4096 * freq_hz)) - 1


class PanTilt:
    """Controls pan/tilt servos via PCA9685 I2C PWM driver."""

    def __init__(self) -> None:
        self._bus = SMBus(_I2C_BUS)
        self._addr = config.PCA9685_I2C_ADDRESS

        self._init_pca9685()

        self.pan_angle = config.PAN_CENTER
        self.tilt_angle = config.TILT_CENTER

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        # Center on boot with move-and-kill
        self._move_and_kill(config.SERVO_PAN_CHANNEL, config.PAN_CENTER)
        self._move_and_kill(config.SERVO_TILT_CHANNEL, config.TILT_CENTER)

        log_info(
            f"PanTilt: PCA9685 ready — "
            f"pan={self.pan_angle}° tilt={self.tilt_angle}°"
        )

    # ── PCA9685 low-level ──────────────────────────────────────────────────

    def _init_pca9685(self) -> None:
        """Reset PCA9685 and set PWM frequency, with I2C retry."""
        for attempt in range(10):
            try:
                self._bus.write_byte_data(self._addr, _MODE1, 0x10)  # sleep
                time.sleep(0.005)
                prescale = _prescale_value(config.SERVO_PWM_FREQ)
                self._bus.write_byte_data(self._addr, _PRESCALE, prescale)
                self._bus.write_byte_data(
                    self._addr, _MODE1, 0x20
                )  # wake + auto-increment
                time.sleep(0.005)
                return
            except OSError:
                if attempt == 9:
                    raise
                log_warning(f"PCA9685 init retry {attempt + 1}/10")
                time.sleep(0.5)

    def _write_servo(self, channel: int, angle: int) -> None:
        """Set a PCA9685 channel to the given angle, with I2C retry."""
        off_ticks = _angle_to_ticks(angle)
        reg = _LED0_ON_L + 4 * channel
        for attempt in range(5):
            try:
                self._bus.write_byte_data(self._addr, reg, 0)
                self._bus.write_byte_data(self._addr, reg + 1, 0)
                self._bus.write_byte_data(self._addr, reg + 2, off_ticks & 0xFF)
                self._bus.write_byte_data(self._addr, reg + 3, (off_ticks >> 8) & 0xFF)
                return
            except OSError:
                if attempt == 4:
                    log_error(
                        f"PCA9685 I2C write failed after 5 retries (ch={channel})"
                    )
                time.sleep(0.01 * (2**attempt))

    def _kill_channel(self, channel: int) -> None:
        """Turn off PWM on a single channel (full-off bit)."""
        reg = _LED0_ON_L + 4 * channel
        for attempt in range(3):
            try:
                self._bus.write_byte_data(self._addr, reg, 0)
                self._bus.write_byte_data(self._addr, reg + 1, 0)
                self._bus.write_byte_data(self._addr, reg + 2, 0)
                self._bus.write_byte_data(self._addr, reg + 3, 0x10)  # bit 4 = full off
                return
            except OSError:
                time.sleep(0.01)

    def _move_and_kill(self, channel: int, angle: int) -> None:
        """Send PWM pulse, wait for servo to settle, then kill signal."""
        self._write_servo(channel, angle)
        time.sleep(config.SERVO_MOVE_DELAY)
        self._kill_channel(channel)

    def _kill_both(self) -> None:
        """Kill PWM on both pan and tilt channels."""
        self._kill_channel(config.SERVO_PAN_CHANNEL)
        self._kill_channel(config.SERVO_TILT_CHANNEL)

    # ── Internals ──────────────────────────────────────────────────────────

    def _clamp(self, value: int, lo: int, hi: int) -> int:
        return max(lo, min(value, hi))

    def _apply_pan(self, logical_angle: int) -> None:
        servo_angle = self._clamp(logical_angle + config.PAN_OFFSET, 0, 180)
        self._write_servo(config.SERVO_PAN_CHANNEL, servo_angle)

    def _apply_tilt(self, logical_angle: int) -> None:
        servo_angle = self._clamp(logical_angle + config.TILT_OFFSET, 0, 180)
        self._write_servo(config.SERVO_TILT_CHANNEL, servo_angle)

    def _sweep_channel(
        self,
        channel: int,
        from_servo: int,
        to_servo: int,
        step: int,
        delay: float,
    ) -> None:
        """Sweep a servo degree-by-degree from from_servo to to_servo.

        PWM stays alive throughout (smooth motion). Killed only at the end.
        Mirrors the technique used in tests/hardware/test_pca9685.py.
        """
        if from_servo == to_servo:
            self._move_and_kill(channel, to_servo)
            return
        direction = 1 if to_servo > from_servo else -1
        current = from_servo
        while True:
            self._write_servo(channel, current)
            time.sleep(delay)
            if current == to_servo:
                break
            current += direction * step
            if direction > 0:
                current = min(current, to_servo)
            else:
                current = max(current, to_servo)
        self._kill_channel(channel)

    def _move_and_kill_pan(self, logical_angle: int) -> None:
        """Smoothly sweep pan servo to target then kill PWM — jitter-free hold."""
        from_servo = self._clamp(self.pan_angle + config.PAN_OFFSET, 0, 180)
        to_servo = self._clamp(logical_angle + config.PAN_OFFSET, 0, 180)
        self._sweep_channel(
            config.SERVO_PAN_CHANNEL,
            from_servo,
            to_servo,
            _PAN_SWEEP_STEP,
            _PAN_SWEEP_DELAY,
        )

    def _move_and_kill_tilt(self, logical_angle: int) -> None:
        """Smoothly sweep tilt servo to target then kill PWM — jitter-free hold."""
        from_servo = self._clamp(self.tilt_angle + config.TILT_OFFSET, 0, 180)
        to_servo = self._clamp(logical_angle + config.TILT_OFFSET, 0, 180)
        self._sweep_channel(
            config.SERVO_TILT_CHANNEL,
            from_servo,
            to_servo,
            _TILT_SWEEP_STEP,
            _TILT_SWEEP_DELAY,
        )

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
                        self.pan_angle = new_pan
                        self._apply_pan(new_pan)
                        moved = True

                if tilt_delta != 0:
                    new_tilt = self._clamp(
                        self.tilt_angle + tilt_delta, config.TILT_MIN, config.TILT_MAX
                    )
                    if new_tilt != self.tilt_angle:
                        self.tilt_angle = new_tilt
                        self._apply_tilt(new_tilt)
                        moved = True

                if not moved:
                    break

                # Use slower tick for tilt (gravity load), faster for pan
                tick = _TILT_TICK_SEC if tilt_delta != 0 else _PAN_TICK_SEC
                self._stop_event.wait(tick)

            # Settled — kill PWM to eliminate jitter at rest
            self._kill_both()
            log_debug(
                f"PanTilt: movement stopped — pan={self.pan_angle} tilt={self.tilt_angle}"
            )

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    # ── Absolute positioning ───────────────────────────────────────────────

    def pan_to(self, angle: int) -> dict:
        """Pan to absolute angle (move-and-kill)."""
        self._stop_current_movement()
        clamped = self._clamp(angle, config.PAN_MIN, config.PAN_MAX)
        if clamped != angle:
            log_warning(f"Pan {angle}° clamped to {clamped}°")
        self._move_and_kill_pan(clamped)
        old, self.pan_angle = self.pan_angle, clamped
        log_info(f"Pan: {old}° → {clamped}°")
        return {"status": "ok", "pan": self.pan_angle}

    def tilt_to(self, angle: int) -> dict:
        """Tilt to absolute angle (move-and-kill)."""
        self._stop_current_movement()
        clamped = self._clamp(angle, config.TILT_MIN, config.TILT_MAX)
        if clamped != angle:
            log_warning(f"Tilt {angle}° clamped to {clamped}°")
        self._move_and_kill_tilt(clamped)
        old, self.tilt_angle = self.tilt_angle, clamped
        log_info(f"Tilt: {old}° → {clamped}°")
        return {"status": "ok", "tilt": self.tilt_angle}

    def pan_snap(self, angle: int, settle_s: float = 0.15) -> dict:
        """Jump pan to angle instantly without smooth sweep.

        Skips the degree-by-degree sweep for speed. Intended for rapid
        multi-shot sequences (e.g. visual_survey) where smooth motion is
        unnecessary. The settle_s wait replaces config.SERVO_MOVE_DELAY —
        tune it to the actual servo travel time for the hop distance.
        """
        self._stop_current_movement()
        clamped = self._clamp(angle, config.PAN_MIN, config.PAN_MAX)
        servo_angle = self._clamp(clamped + config.PAN_OFFSET, 0, 180)
        self._write_servo(config.SERVO_PAN_CHANNEL, servo_angle)
        time.sleep(settle_s)
        self._kill_channel(config.SERVO_PAN_CHANNEL)
        old, self.pan_angle = self.pan_angle, clamped
        log_info(f"Pan snap: {old}° → {clamped}°")
        return {"status": "ok", "pan": self.pan_angle}

    def tilt_snap(self, angle: int, settle_s: float = 0.20) -> dict:
        """Jump tilt to angle instantly without smooth sweep.

        Same rationale as pan_snap — use for rapid multi-shot sequences.
        Default settle_s is slightly longer than pan because the tilt servo
        carries the camera weight and needs more margin.
        """
        self._stop_current_movement()
        clamped = self._clamp(angle, config.TILT_MIN, config.TILT_MAX)
        servo_angle = self._clamp(clamped + config.TILT_OFFSET, 0, 180)
        self._write_servo(config.SERVO_TILT_CHANNEL, servo_angle)
        time.sleep(settle_s)
        self._kill_channel(config.SERVO_TILT_CHANNEL)
        old, self.tilt_angle = self.tilt_angle, clamped
        log_info(f"Tilt snap: {old}° → {clamped}°")
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
        self._start_movement(0, _TILT_STEP_DEG * config.TILT_DIRECTION)
        return {"status": "ok", "action": "tilt_up_start"}

    def tilt_down_start(self) -> dict:
        self._start_movement(0, -_TILT_STEP_DEG * config.TILT_DIRECTION)
        return {"status": "ok", "action": "tilt_down_start"}

    def pan_left_start(self) -> dict:
        self._start_movement(-_PAN_STEP_DEG * config.PAN_DIRECTION, 0)
        return {"status": "ok", "action": "pan_left_start"}

    def pan_right_start(self) -> dict:
        self._start_movement(_PAN_STEP_DEG * config.PAN_DIRECTION, 0)
        return {"status": "ok", "action": "pan_right_start"}

    def up_left_start(self) -> dict:
        self._start_movement(
            -_PAN_STEP_DEG * config.PAN_DIRECTION,
            _TILT_STEP_DEG * config.TILT_DIRECTION,
        )
        return {"status": "ok", "action": "up_left_start"}

    def up_right_start(self) -> dict:
        self._start_movement(
            _PAN_STEP_DEG * config.PAN_DIRECTION, _TILT_STEP_DEG * config.TILT_DIRECTION
        )
        return {"status": "ok", "action": "up_right_start"}

    def down_left_start(self) -> dict:
        self._start_movement(
            -_PAN_STEP_DEG * config.PAN_DIRECTION,
            -_TILT_STEP_DEG * config.TILT_DIRECTION,
        )
        return {"status": "ok", "action": "down_left_start"}

    def down_right_start(self) -> dict:
        self._start_movement(
            _PAN_STEP_DEG * config.PAN_DIRECTION,
            -_TILT_STEP_DEG * config.TILT_DIRECTION,
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
            self._apply_pan(angle)
            self.pan_angle = angle
            time.sleep(0.05)
        # Kill after scan completes
        self._kill_channel(config.SERVO_PAN_CHANNEL)
        log_info(f"Pan scan complete at {end}°")

    def cleanup(self) -> None:
        self._stop_current_movement()
        self._kill_both()
        try:
            self._bus.close()
        except Exception as e:
            log_error(f"PanTilt cleanup error: {e}")
        log_info("PanTilt: PCA9685 bus closed")
