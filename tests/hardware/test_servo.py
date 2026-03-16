#!/usr/bin/env python3
"""Test servo pan/tilt with proper cleanup."""

import RPi.GPIO as GPIO
import time
import sys
from config import PAN_SERVO, TILT_SERVO

# Suppress cleanup warnings
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

pwm_pan = None
pwm_tilt = None


def cleanup():
    """Safe cleanup to avoid exceptions."""
    global pwm_pan, pwm_tilt

    if pwm_pan is not None:
        try:
            pwm_pan.ChangeDutyCycle(0)  # Stop signal first
            time.sleep(0.1)
            pwm_pan.stop()
        except:
            pass
        pwm_pan = None

    if pwm_tilt is not None:
        try:
            pwm_tilt.ChangeDutyCycle(0)
            time.sleep(0.1)
            pwm_tilt.stop()
        except:
            pass
        pwm_tilt = None

    # Small delay before GPIO.cleanup()
    time.sleep(0.2)
    try:
        GPIO.cleanup()
    except:
        pass


def angle_to_duty(angle: int) -> float:
    """Convert angle (0-180) to duty cycle (2-12)."""
    return 2 + (angle / 180) * 10


def move_servo_smooth(
    pwm, start_angle: int, end_angle: int, step: int = 1, delay: float = 0.05
):
    """Move servo smoothly from start_angle to end_angle."""
    if start_angle < end_angle:
        angles = range(start_angle, end_angle + 1, step)
    else:
        angles = range(start_angle, end_angle - 1, -step)

    for angle in angles:
        duty = angle_to_duty(angle)
        pwm.ChangeDutyCycle(duty)
        time.sleep(delay)

    # Stop signal to prevent buzzing
    pwm.ChangeDutyCycle(0)
    time.sleep(0.1)


def move_servo_relative(
    pwm, current_angle: int, relative_angle: int, step: int = 1, delay: float = 0.15
):
    """Move servo by relative angle from current position."""
    target_angle = current_angle + relative_angle

    # Safety bounds check
    if target_angle < 60 or target_angle > 120:
        print(
            f"    Warning: Target angle {target_angle}° out of safe range [60-120], skipping"
        )
        return current_angle

    print(f"    Moving {relative_angle:+d}° to {target_angle}°")
    move_servo_smooth(pwm, current_angle, target_angle, step=step, delay=delay)
    return target_angle


def find_safe_center(pwm):
    """Find the actual safe center position by testing small movements."""
    print("  Finding safe center position...")

    # Start at 90° and test small movements
    test_angles = [85, 88, 90, 92, 95]
    safe_center = 90

    for angle in test_angles:
        print(f"    Testing {angle}°...")
        try:
            move_servo_smooth(pwm, 90, angle, step=1, delay=0.1)
            time.sleep(0.5)

            # Test if we can move back
            move_servo_smooth(pwm, angle, 90, step=1, delay=0.1)
            time.sleep(0.5)
            print(f"      {angle}° is safe")

        except Exception as e:
            print(f"      {angle}° caused issues: {e}")
            break

    return safe_center


def test_servo(pin: int, name: str, speed: float = 0.5):
    """Test a single servo with configurable speed."""
    global pwm_pan, pwm_tilt

    print(f"\n{'='*50}")
    print(f"Testing {name} on GPIO {pin} (Minimum Speed)")
    print(f"{'='*50}")

    GPIO.setup(pin, GPIO.OUT)
    pwm = GPIO.PWM(pin, 50)  # 50Hz for servo
    pwm.start(0)

    # Store reference for cleanup
    if name == "PAN":
        pwm_pan = pwm
        # Pan movement: center -> 50 right -> center -> 50 left -> center
        movements = [
            (90, 40),
            (40, 90),
            (90, 140),
            (140, 90),
        ]  # (start, end) angle pairs

        for start_angle, end_angle in movements:
            direction = (
                "right" if end_angle < 90 else "left" if end_angle > 90 else "center"
            )
            print(f"  Moving: {start_angle:3d}° → {end_angle:3d}° ({direction})")
            move_servo_smooth(pwm, start_angle, end_angle, step=2, delay=0.1)

    else:
        pwm_tilt = pwm
        # Tilt movement: first find safe center, then tiny movements
        print("  Starting at 90°...")
        pwm.ChangeDutyCycle(angle_to_duty(90))
        time.sleep(2)  # Longer wait to stabilize
        pwm.ChangeDutyCycle(0)
        time.sleep(0.2)

        # Test very small movements first
        current_angle = 90

        print("  Testing tiny 2° up movement...")
        current_angle = move_servo_relative(pwm, current_angle, -2, step=1, delay=0.2)

        print("  Moving back to center...")
        current_angle = move_servo_relative(pwm, current_angle, +2, step=1, delay=0.2)

        print("  Testing tiny 2° down movement...")
        current_angle = move_servo_relative(pwm, current_angle, +2, step=1, delay=0.2)

        print("  Moving back to center...")
        current_angle = move_servo_relative(pwm, current_angle, -2, step=1, delay=0.2)

        # Stop the servo completely
        pwm.ChangeDutyCycle(0)
        time.sleep(0.5)


def test_combination():
    """Test both servos in combination pattern with minimum speed."""
    global pwm_pan, pwm_tilt

    print(f"\n{'='*50}")
    print("Testing Pan & Tilt Combination (Minimum Speed)")
    print(f"{'='*50}")

    # Setup both servos
    GPIO.setup(PAN_SERVO, GPIO.OUT)
    GPIO.setup(TILT_SERVO, GPIO.OUT)

    pwm_pan = GPIO.PWM(PAN_SERVO, 50)
    pwm_tilt = GPIO.PWM(TILT_SERVO, 50)

    pwm_pan.start(0)
    pwm_tilt.start(0)

    # Combination pattern with smooth movements:
    # From center: 50 right - tilt center - tilt 50 up - tilt 50 down - tilt center - pan center - 50 left - continue vice versa

    # Start from center
    print("  Starting from center position...")
    pwm_pan.ChangeDutyCycle(angle_to_duty(90))
    pwm_tilt.ChangeDutyCycle(angle_to_duty(90))
    time.sleep(1)
    pwm_pan.ChangeDutyCycle(0)
    pwm_tilt.ChangeDutyCycle(0)
    time.sleep(0.1)

    # 50 deg right (slow movement)
    print("  Pan 50° right (slow)...")
    move_servo_smooth(pwm_pan, 90, 40, step=2, delay=0.1)

    # Tilt center (already at center)
    print("  Tilt center...")
    time.sleep(0.5)

    # Tilt 25 up (slow movement) - reduced range for camera mount
    print("  Tilt 25° up (slow)...")
    move_servo_smooth(pwm_tilt, 90, 65, step=1, delay=0.15)

    # Tilt 25 down (slow movement) - reduced range for camera mount
    print("  Tilt 25° down (slow)...")
    move_servo_smooth(pwm_tilt, 65, 115, step=1, delay=0.15)

    # Tilt center (slow movement)
    print("  Tilt center (slow)...")
    move_servo_smooth(pwm_tilt, 115, 90, step=1, delay=0.15)

    # Pan center (slow movement)
    print("  Pan center (slow)...")
    move_servo_smooth(pwm_pan, 40, 90, step=2, delay=0.1)

    # 50 deg left (slow movement)
    print("  Pan 50° left (slow)...")
    move_servo_smooth(pwm_pan, 90, 140, step=2, delay=0.1)

    # Continue vice versa (reverse pattern)
    print("  Reversing pattern...")

    # Tilt center (slow movement)
    print("  Tilt center (slow)...")
    move_servo_smooth(pwm_tilt, 115, 90, step=1, delay=0.15)

    # Pan center (slow movement)
    print("  Pan center (slow)...")
    move_servo_smooth(pwm_pan, 140, 90, step=2, delay=0.1)

    # Tilt 25 up (slow movement) - reduced range for camera mount
    print("  Tilt 25° up (slow)...")
    move_servo_smooth(pwm_tilt, 90, 65, step=1, delay=0.15)

    # Tilt 25 down (slow movement) - reduced range for camera mount
    print("  Tilt 25° down (slow)...")
    move_servo_smooth(pwm_tilt, 65, 115, step=1, delay=0.15)

    # Tilt center (slow movement)
    print("  Tilt center (slow)...")
    move_servo_smooth(pwm_tilt, 115, 90, step=1, delay=0.15)

    # 50 deg right (slow movement)
    print("  Pan 50° right (slow)...")
    move_servo_smooth(pwm_pan, 90, 40, step=2, delay=0.1)

    # Back to center (slow movement)
    print("  Return to center (slow)...")
    move_servo_smooth(pwm_pan, 40, 90, step=2, delay=0.1)
    move_servo_smooth(pwm_tilt, 90, 90, step=2, delay=0.1)  # Already at center

    # Stop signals
    pwm_pan.ChangeDutyCycle(0)
    pwm_tilt.ChangeDutyCycle(0)
    time.sleep(0.2)


try:
    print("Servo Test Script")
    print("=" * 50)
    print("Make sure servos are connected:")
    print(f"  Pan Servo  → GPIO {PAN_SERVO} (Pin 12)")
    print(f"  Tilt Servo → GPIO {TILT_SERVO} (Pin 35)")
    print("=" * 50)

    choice = input(
        "\nTest which servo? (1=Pan, 2=Tilt, 3=Both, 4=Combination): "
    ).strip()

    if choice == "1":
        test_servo(PAN_SERVO, "PAN")
    elif choice == "2":
        test_servo(TILT_SERVO, "TILT")
    elif choice == "3":
        test_servo(PAN_SERVO, "PAN")
        time.sleep(1)
        test_servo(TILT_SERVO, "TILT")
    elif choice == "4":
        test_combination()
    else:
        print("Invalid choice!")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("✓ Test complete!")
    print("=" * 50)

except KeyboardInterrupt:
    print("\n\nInterrupted by user")
except Exception as e:
    print(f"\n✗ Error: {e}")
finally:
    cleanup()
