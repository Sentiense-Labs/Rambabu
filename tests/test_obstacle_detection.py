#!/usr/bin/env python3
"""Test obstacle detection with motor control."""

import RPi.GPIO as GPIO
import time
from lib.motor import MotorController
from lib.ultrasonic import Ultrasonic

STOP_DISTANCE = 100  # Stop if object within 100cm


def test_obstacle_detection():
    """
    Test obstacle detection - car stops when object detected within 100cm
    """
    print("\nMoving forward - Place obstacle to test stop at 100cm\n")

    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        motor = MotorController()
        ultrasonic = Ultrasonic()
        
        time.sleep(1)
        
        # Move forward
        motor.front(70)
        
        for i in range(60):
            distance = ultrasonic.get_distance()
            
            if distance <= STOP_DISTANCE:
                print(f"[{i+1:2d}s] 🛑 OBSTACLE at {distance:.1f}cm - STOPPING")
                motor.stop()
                break
            else:
                print(f"[{i+1:2d}s] Moving... {distance:.1f}cm")
            
            time.sleep(0.5)
        
        motor.stop()
        ultrasonic.stop()
        motor.cleanup()
        GPIO.cleanup()
        
    except KeyboardInterrupt:
        print("\nStopped by user")
        motor.stop()
        ultrasonic.stop()
        motor.cleanup()
        GPIO.cleanup()
    
    except Exception as e:
        print(f"Error: {e}")
        motor.stop()
        ultrasonic.stop()
        motor.cleanup()
        GPIO.cleanup()
        raise


if __name__ == "__main__":
    test_obstacle_detection()
