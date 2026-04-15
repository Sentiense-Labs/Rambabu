#!/usr/bin/env python3
import sys
import time
import RPi.GPIO as GPIO

# Set GPIO mode before anything else, as motor.py might initialize it on import
GPIO.setmode(GPIO.BCM)

sys.path.append("/home/rambabu/rambabu_rc")
sys.path.append("/home/rambabu/rambabu_rc/lib")
try:
    from motor import MotorController
except ImportError as e:
    print(
        f"Error: Failed to import MotorController. Make sure motor.py is in the lib folder. Details: {e}"
    )
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 drive_car.py [forward|reverse|left|right|stop]")
        sys.exit(1)

    action = sys.argv[1].lower()

    try:
        mc = MotorController()

        if action == "forward":
            print("Moving forward...")
            mc.front()
            time.sleep(1.5)  # Drive for 1.5s
            mc.stop()
        elif action == "reverse":
            print("Moving reverse...")
            mc.back()
            time.sleep(1.5)  # Drive for 1.5s
            mc.stop()
        elif action == "left":
            print("Turning left...")
            mc.left()
        elif action == "right":
            print("Turning right...")
            mc.right()
        elif action == "stop":
            print("Stopping...")
            mc.stop()
        else:
            print(f"Unknown action: {action}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # The motor class itself should handle cleanup if needed
        # but we ensure stop is called.
        if "mc" in locals():
            mc.stop()
            mc.cleanup()
        GPIO.cleanup()  # Clean up GPIO channels
        print("Operation complete.")


if __name__ == "__main__":
    main()
