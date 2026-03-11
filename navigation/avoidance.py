#!/usr/bin/env python3
"""
Obstacle avoidance logic for AI RC Car
Implements safety checks and navigation decisions
"""

import time
from utils.logger import log_info, log_warning, log_debug
import config


def check_and_avoid(ultrasonic, motor, scanner=None) -> bool:
    """
    Check for obstacles and avoid them if detected

    Args:
        ultrasonic: Ultrasonic sensor instance
        motor: MotorController instance
        scanner: Optional scanner instance for direction checking

    Returns:
        True if avoidance was performed, False if path is clear
    """
    # Check if blocked
    if ultrasonic.is_blocked(config.STOP_DISTANCE):
        log_warning("Obstacle detected - emergency stop")
        motor.stop()

        # Scan for clear direction
        if scanner:
            log_info("Scanning for clear path...")
            direction = _find_clear_direction(ultrasonic, scanner)

            if direction == "left":
                log_info("Turning left to avoid obstacle")
                motor.left()
            elif direction == "right":
                log_info("Turning right to avoid obstacle")
                motor.right()
            elif direction == "back":
                log_info("Reversing to find clear path")
                motor.back()
            else:
                log_warning("No clear direction found - staying stopped")
                return True

            # Small delay after turn
            time.sleep(0.5)

        return True

    # Check warning distance
    elif ultrasonic.get_distance() < config.WARNING_DISTANCE:
        log_debug("Warning distance - slowing down")
        # Could slow down here if needed
        return False

    # Path is clear
    return False


def _find_clear_direction(ultrasonic, scanner) -> str:
    """
    Find the clearest direction by scanning left, center, right

    Returns:
        "left", "right", "back", or "none"
    """
    distances = {}

    # Scan center
    distances["center"] = ultrasonic.get_distance()
    log_debug(f"Center distance: {distances['center']:.1f}cm")

    # Scan left
    if scanner:
        scanner.scan_left()
        time.sleep(0.5)
        distances["left"] = ultrasonic.get_distance()
        log_debug(f"Left distance: {distances['left']:.1f}cm")

    # Scan right
    if scanner:
        scanner.scan_right()
        time.sleep(0.5)
        distances["right"] = ultrasonic.get_distance()
        log_debug(f"Right distance: {distances['right']:.1f}cm")

    # Find best direction
    best_direction = "none"
    best_distance = 0

    for direction, distance in distances.items():
        if distance > best_distance:
            best_distance = distance
            best_direction = direction

    # If no direction is clear, suggest backing up
    if best_distance < config.SAFE_DISTANCE:
        return "back"

    return best_direction
