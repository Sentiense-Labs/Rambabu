#!/usr/bin/env python3
"""
MotorController class for AI RC Car
Controls rear drive motor and steering motor using RPi.GPIO
"""

import RPi.GPIO as GPIO
import time
from typing import Optional
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

        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        # Setup output pins
        GPIO.setup(self.rear_forward, GPIO.OUT)
        GPIO.setup(self.rear_backward, GPIO.OUT)
        GPIO.setup(self.steer_left, GPIO.OUT)
        GPIO.setup(self.steer_right, GPIO.OUT)

        # Initialize PWM for rear motor (speed control)
        self.pwm_forward = GPIO.PWM(self.rear_forward, 1000)
        self.pwm_backward = GPIO.PWM(self.rear_backward, 1000)

        # Start PWM with 0% duty cycle (stopped)
        self.pwm_forward.start(0)
        self.pwm_backward.start(0)

        # Ensure all outputs are low
        self.stop()

    @property
    def is_moving_forward(self) -> bool:
        """True when the car is actively driving forward"""
        return self._direction == "forward"

    def front(self, speed: int = 70) -> None:
        """
        Drive forward at given speed (0-100)
        """
        # Stop backward PWM
        self.pwm_backward.ChangeDutyCycle(0)

        # Start forward PWM with speed
        duty_cycle = min(max(speed, 0), 100)
        self.pwm_forward.ChangeDutyCycle(duty_cycle)
        self._direction = "forward"
        log_info(f"Motor: Forward at {speed}%")

    def back(self, speed: int = 50) -> None:
        """
        Drive backward at given speed (0-100)
        """
        # Stop forward PWM
        self.pwm_forward.ChangeDutyCycle(0)

        # Start backward PWM with speed
        duty_cycle = min(max(speed, 0), 100)
        self.pwm_backward.ChangeDutyCycle(duty_cycle)
        self._direction = "backward"
        log_info(f"Motor: Backward at {speed}%")

    def left(self) -> None:
        """
        Turn left for 0.5 seconds (auto-reset)
        """
        self._direction = "left"
        GPIO.output(self.steer_left, GPIO.LOW)
        GPIO.output(self.steer_right, GPIO.HIGH)
        time.sleep(0.5)
        GPIO.output(self.steer_right, GPIO.LOW)
        self._direction = "stopped"
        log_info("Motor: Steering left")

    def steer_left_hold(self) -> None:
        """
        Start turning left and HOLD position (doesn't auto-reset)
        Use steer_center() to reset
        """
        self._direction = "left"
        try:
            GPIO.output(self.steer_left, GPIO.LOW)
            GPIO.output(self.steer_right, GPIO.HIGH)
            log_info("Motor: Steering left (hold)")
        except Exception as e:
            log_error(f"Steering left error: {e}")

    def right(self) -> None:
        """
        Turn right for 0.5 seconds (auto-reset)
        """
        self._direction = "right"
        GPIO.output(self.steer_left, GPIO.HIGH)
        GPIO.output(self.steer_right, GPIO.LOW)
        time.sleep(0.5)
        GPIO.output(self.steer_left, GPIO.LOW)
        self._direction = "stopped"
        log_info("Motor: Steering right")

    def steer_right_hold(self) -> None:
        """
        Start turning right and HOLD position (doesn't auto-reset)
        Use steer_center() to reset
        """
        self._direction = "right"
        try:
            GPIO.output(self.steer_left, GPIO.HIGH)
            GPIO.output(self.steer_right, GPIO.LOW)
            log_info("Motor: Steering right (hold)")
        except Exception as e:
            log_error(f"Steering right error: {e}")

    def steer_center(self) -> None:
        """
        Return steering to center position
        """
        self._direction = "stopped"
        try:
            GPIO.output(self.steer_left, GPIO.LOW)
            GPIO.output(self.steer_right, GPIO.LOW)
            log_info("Motor: Steering centered")
        except Exception as e:
            log_error(f"Steering center error: {e}")

    def stop(self) -> None:
        """
        Stop all motors immediately
        """
        # Stop PWM
        self.pwm_forward.ChangeDutyCycle(0)
        self.pwm_backward.ChangeDutyCycle(0)

        # Ensure all GPIO outputs are low
        GPIO.output(self.rear_forward, GPIO.LOW)
        GPIO.output(self.rear_backward, GPIO.LOW)
        GPIO.output(self.steer_left, GPIO.LOW)
        GPIO.output(self.steer_right, GPIO.LOW)
        self._direction = "stopped"
        log_info("Motor: Stopped")

    def cleanup(self) -> None:
        """
        Clean up GPIO and PWM resources
        """
        try:
            # Stop PWM first
            if self.pwm_forward:
                self.pwm_forward.stop()
            if self.pwm_backward:
                self.pwm_backward.stop()

            # Stop all motors
            self.stop()

            # Cleanup GPIO
            GPIO.cleanup()
        except Exception as e:
            log_error(f"Motor cleanup error: {e}")
