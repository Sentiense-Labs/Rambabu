#!/usr/bin/env python3
"""
Navigator class for AI RC Car
Main autonomous navigation loop with decision making
"""

import time
from utils.logger import log_info, log_warning, log_debug, log_error
import config


class Navigator:
    """Autonomous navigation controller"""

    def __init__(self, motor, ultrasonic, mode_manager, microphone=None):
        """
        Initialize navigator

        Args:
            motor: MotorController instance
            ultrasonic: Ultrasonic sensor instance
            mode_manager: ModeManager instance
            microphone: Optional Microphone instance for voice commands
        """
        self.motor = motor
        self.ultrasonic = ultrasonic
        self.mode_manager = mode_manager
        self.microphone = microphone
        self.running = False
        self.loop_interval = config.NAVIGATOR_LOOP_INTERVAL

    def run_loop(self):
        """Main navigation loop (runs at 10Hz)"""
        self.running = True
        log_info("Navigator: Main loop started at 10Hz")

        try:
            while self.running:
                # Check if stopped
                if self.mode_manager.is_stopped():
                    time.sleep(self.loop_interval)
                    continue

                # Get current distance
                distance = self.ultrasonic.get_distance()

                # Safety check first - emergency stop
                if distance < config.STOP_DISTANCE:
                    self.motor.stop()
                    log_warning(f"EMERGENCY STOP: Obstacle at {distance:.1f}cm")
                    time.sleep(self.loop_interval)
                    continue

                # Obstacle detection and avoidance
                if distance < config.STOP_DISTANCE:
                    log_warning(f"Obstacle detected at {distance:.1f}cm - avoiding")
                    self.motor.stop()
                    # Avoidance logic would be handled by avoidance module
                    log_info("Motor: Stopped")

                # Check for voice commands
                if self.microphone:
                    command = self.microphone.get_command()
                    if command:
                        log_info(f"Nav: Executing voice command - {command}")
                        self._process_voice_command(command)
                        self.microphone.clear()

                # Log navigation status
                log_debug(
                    f"Nav: Distance={distance:.1f}cm, Mode={self.mode_manager.get_mode()}"
                )

                # Sleep for navigation interval (10Hz = 100ms)
                time.sleep(self.loop_interval)

        except Exception as e:
            log_error(f"Navigator loop error: {e}")
        finally:
            self.running = False

    def _process_voice_command(self, command: str):
        """
        Process voice command

        Args:
            command: Voice command string
        """
        command = command.lower()

        if "stop" in command:
            self.motor.stop()
            log_warning("EMERGENCY STOP: Voice command")
            self.mode_manager.set_mode(self.mode_manager.STOPPED, source="voice")
        elif "forward" in command or "go" in command:
            self.motor.front(config.DEFAULT_SPEED)
            log_info("Nav: Moving forward")
        elif "backward" in command or "back" in command:
            self.motor.back(config.DEFAULT_SPEED)
            log_info("Nav: Moving backward")
        elif "left" in command:
            self.motor.left()
            log_info("Nav: Turning left")
        elif "right" in command:
            self.motor.right()
            log_info("Nav: Turning right")
        elif "auto" in command or "autonomous" in command:
            self.mode_manager.set_mode(self.mode_manager.AUTONOMOUS, source="voice")
            log_info("Nav: Mode switched to AUTONOMOUS")
        elif "manual" in command:
            self.mode_manager.set_mode(self.mode_manager.MANUAL, source="voice")
            log_info("Nav: Mode switched to MANUAL")

    def stop(self):
        """Stop navigation loop"""
        self.running = False
        log_info("Navigator: Loop stopped")
