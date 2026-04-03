#!/usr/bin/env python3
"""
MotorController class for AI RC Car
Controls rear drive motor and steering motor using RPi.GPIO
"""

import RPi.GPIO as GPIO
import time
from utils.logger import log_info, log_error
import config


class MotorController:
    """Controls rear drive and steering motors via L9110S driver"""

    def __init__(self):
        """Initialize motor controller with GPIO pins from config"""
        # Get GPIO pins from config
        self.rear_forward = config.MOTOR_REAR_FORWARD
        self.rear_backward = config.MOTOR_REAR_BACKWARD
        self.steer_left = config.MOTOR_STEER_LEFT
        self.steer_right = config.MOTOR_STEER_RIGHT

        # PWM for speed control (1000Hz)
        self.pwm_forward = None
        self.pwm_backward = None

        # Track current direction so obstacle monitor only stops forward motion
        self._direction = "stopped"

        # Obstacle check callbacks — injected by main.py after ultrasonic init
        self._obstacle_check = None       # Returns True if path is blocked (distance <= 50cm)
        self._obstacle_clear_check = None  # Returns True if path is clear (distance > 70cm)

        # Hysteresis latch: once an obstacle stops forward motion, stay latched
        # until distance exceeds OBSTACLE_CLEAR_DISTANCE (70cm), or
        # the car moves backward (which clears the latch explicitly).
        self._obstacle_latched = False

        # GPIO.setmode() is handled by main.py before creating this object
        GPIO.setwarnings(False)

        # Setup output pins
        GPIO.setup(self.rear_forward, GPIO.OUT)
        GPIO.setup(self.rear_backward, GPIO.OUT)
        GPIO.setup(self.steer_left, GPIO.OUT)
        GPIO.setup(self.steer_right, GPIO.OUT)

        # Initialize PWM for rear motor (speed control)
        self.pwm_forward = GPIO.PWM(self.rear_forward, config.MOTOR_PWM_FREQ)
        self.pwm_backward = GPIO.PWM(self.rear_backward, config.MOTOR_PWM_FREQ)
        self.pwm_forward.start(0)
        self.pwm_backward.start(0)

        # Initialize PWM for steering motor (tuned pulse control)
        self.pwm_steer_left = GPIO.PWM(self.steer_left, config.MOTOR_PWM_FREQ)
        self.pwm_steer_right = GPIO.PWM(self.steer_right, config.MOTOR_PWM_FREQ)
        self.pwm_steer_left.start(0)
        self.pwm_steer_right.start(0)

        # Ensure all outputs are low
        self.stop()

    def set_obstacle_check(self, check_fn, clear_fn=None) -> None:
        """Inject obstacle check callbacks.
        check_fn() -> True if blocked (distance <= detection threshold).
        clear_fn() -> True if genuinely clear (distance > clear threshold with hysteresis).
        """
        self._obstacle_check = check_fn
        self._obstacle_clear_check = clear_fn

    @property
    def is_moving_forward(self) -> bool:
        """True when the car is actively driving forward"""
        return self._direction == "forward"

    def latch_obstacle(self) -> None:
        """Engage obstacle latch — called by monitor when obstacle detected."""
        if not self._obstacle_latched:
            self._obstacle_latched = True
            log_info("Motor: Obstacle latch engaged — forward blocked until obstacle clears")

    def _check_latch(self) -> bool:
        """Returns True if forward is still blocked. Only releases when distance > OBSTACLE_CLEAR_DISTANCE."""
        if not self._obstacle_latched:
            return False
        # Use the clear check (with hysteresis) if available, otherwise fall back to obstacle check
        if self._obstacle_clear_check and self._obstacle_clear_check():
            self._obstacle_latched = False
            log_info("Motor: Obstacle latch released — path is clear (hysteresis passed)")
            return False
        elif not self._obstacle_clear_check and self._obstacle_check and not self._obstacle_check():
            # Fallback: no clear_fn provided, use inverse of obstacle check
            self._obstacle_latched = False
            log_info("Motor: Obstacle latch released — path is clear")
            return False
        return True

    def front(self, speed: int = config.DEFAULT_SPEED) -> dict:
        """Drive forward at given speed (0-100). Refuses if obstacle detected or latched."""
        if self._check_latch():
            log_info("Motor: Forward blocked — obstacle latch active")
            return {"status": "error", "error_code": "OBSTACLE_DETECTED",
                    "message": "Obstacle latched — path not clear yet"}

        if self._obstacle_check and self._obstacle_check():
            self.latch_obstacle()
            self.stop()
            log_info("Motor: Forward BLOCKED by obstacle check")
            return {"status": "error", "error_code": "OBSTACLE_DETECTED",
                    "message": "Obstacle detected — cannot move forward"}

        self.pwm_backward.ChangeDutyCycle(0)
        duty_cycle = min(max(speed, 0), 100)
        self.pwm_forward.ChangeDutyCycle(duty_cycle)
        self._direction = "forward"
        log_info(f"Motor: Forward at {duty_cycle}%")
        return {"status": "ok", "direction": "forward", "speed": duty_cycle}

    def back(self, speed: int = config.DEFAULT_SPEED) -> dict:
        """Drive backward at given speed (0-100). Clears obstacle latch."""
        if self._obstacle_latched:
            self._obstacle_latched = False
            log_info("Motor: Obstacle latch cleared by backward movement")
        self.pwm_forward.ChangeDutyCycle(0)
        duty_cycle = min(max(speed, 0), 100)
        self.pwm_backward.ChangeDutyCycle(duty_cycle)
        self._direction = "backward"
        log_info(f"Motor: Backward at {duty_cycle}%")
        return {"status": "ok", "direction": "backward", "speed": duty_cycle}

    def _steer_center_raw(self) -> None:
        """Center steering with dead time to protect gears on direction change."""
        self.pwm_steer_left.ChangeDutyCycle(0)
        self.pwm_steer_right.ChangeDutyCycle(0)
        GPIO.output(self.steer_left, GPIO.LOW)
        GPIO.output(self.steer_right, GPIO.LOW)
        time.sleep(config.STEER_DEAD_TIME)

    def left(self) -> dict:
        """Turn left for STEER_PULSE_DURATION seconds (auto-reset)."""
        self._direction = "left"
        self._steer_center_raw()
        time.sleep(config.STEER_SETTLE_TIME)
        self.pwm_steer_left.ChangeDutyCycle(0)
        self.pwm_steer_right.ChangeDutyCycle(100)
        time.sleep(config.STEER_PULSE_DURATION)
        self._steer_center_raw()
        self._direction = "stopped"
        log_info("Motor: Steering left")
        return {"status": "ok", "direction": "left"}

    def steer_left_hold(self) -> dict:
        """Start turning left and HOLD position (use steer_center() to reset)."""
        self._direction = "left"
        try:
            self._steer_center_raw()
            time.sleep(config.STEER_SETTLE_TIME)
            self.pwm_steer_left.ChangeDutyCycle(0)
            self.pwm_steer_right.ChangeDutyCycle(100)
            log_info("Motor: Steering left (hold)")
            return {"status": "ok", "direction": "left_hold"}
        except Exception as e:
            log_error(f"Steering left error: {e}")
            return {"status": "error", "error_code": "MOTOR_STALL", "message": str(e)}

    def right(self) -> dict:
        """Turn right for STEER_PULSE_DURATION seconds (auto-reset)."""
        self._direction = "right"
        self._steer_center_raw()
        time.sleep(config.STEER_SETTLE_TIME)
        self.pwm_steer_right.ChangeDutyCycle(0)
        self.pwm_steer_left.ChangeDutyCycle(100)
        time.sleep(config.STEER_PULSE_DURATION)
        self._steer_center_raw()
        self._direction = "stopped"
        log_info("Motor: Steering right")
        return {"status": "ok", "direction": "right"}

    def steer_right_hold(self) -> dict:
        """Start turning right and HOLD position (use steer_center() to reset)."""
        self._direction = "right"
        try:
            self._steer_center_raw()
            time.sleep(config.STEER_SETTLE_TIME)
            self.pwm_steer_right.ChangeDutyCycle(0)
            self.pwm_steer_left.ChangeDutyCycle(100)
            log_info("Motor: Steering right (hold)")
            return {"status": "ok", "direction": "right_hold"}
        except Exception as e:
            log_error(f"Steering right error: {e}")
            return {"status": "error", "error_code": "MOTOR_STALL", "message": str(e)}

    def steer_center(self) -> dict:
        """Return steering to center position."""
        self._direction = "stopped"
        try:
            self._steer_center_raw()
            log_info("Motor: Steering centered")
            return {"status": "ok", "direction": "center"}
        except Exception as e:
            log_error(f"Steering center error: {e}")
            return {"status": "error", "error_code": "MOTOR_STALL", "message": str(e)}

    def stop(self) -> dict:
        """Stop all motors immediately."""
        self.pwm_forward.ChangeDutyCycle(0)
        self.pwm_backward.ChangeDutyCycle(0)
        self.pwm_steer_left.ChangeDutyCycle(0)
        self.pwm_steer_right.ChangeDutyCycle(0)
        GPIO.output(self.steer_left, GPIO.LOW)
        GPIO.output(self.steer_right, GPIO.LOW)
        self._direction = "stopped"
        log_info("Motor: Stopped")
        return {"status": "ok", "direction": "stopped"}

    def cleanup(self) -> None:
        """Clean up GPIO and PWM resources."""
        try:
            self.stop()
            if self.pwm_forward:
                self.pwm_forward.stop()
            if self.pwm_backward:
                self.pwm_backward.stop()
            if self.pwm_steer_left:
                self.pwm_steer_left.stop()
            if self.pwm_steer_right:
                self.pwm_steer_right.stop()
        except Exception as e:
            log_error(f"Motor cleanup error: {e}")
