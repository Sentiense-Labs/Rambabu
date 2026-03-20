#!/usr/bin/env python3
"""
Direct GPIO motor test — mirrors the ESP32 test sketch exactly.

Cycles: Forward → Backward → Left → Right → Stop
Uses raw RPi.GPIO (no PWM, no library) to isolate wiring issues.

Run with: python3 scripts/test_motor_gpio.py
Stop with: Ctrl+C
"""

import time
import sys
import RPi.GPIO as GPIO

# ── PIN CONFIGURATION (BCM numbering) ─────────────────────────────────────
# Change these if your wiring differs from the defaults in config/__init__.py
MOTOR_A1 = 25  # L9110S A-IA  (was GPIO 18 on ESP32)
MOTOR_A2 = 26  # L9110S A-IB  (was GPIO 19 on ESP32)
MOTOR_B1 = 27  # L9110S B-IA  (was GPIO 14 on ESP32)
MOTOR_B2 = 14  # L9110S B-IB  (was GPIO 27 on ESP32)

STEP_DELAY = 1.0   # seconds per movement
PAUSE_DELAY = 0.5  # seconds between movements


def setup():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    for pin in (MOTOR_A1, MOTOR_A2, MOTOR_B1, MOTOR_B2):
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
    print(f"GPIO setup done. Pins: A1={MOTOR_A1}, A2={MOTOR_A2}, B1={MOTOR_B1}, B2={MOTOR_B2}\n")


def stop():
    GPIO.output(MOTOR_A1, GPIO.LOW)
    GPIO.output(MOTOR_A2, GPIO.LOW)
    GPIO.output(MOTOR_B1, GPIO.LOW)
    GPIO.output(MOTOR_B2, GPIO.LOW)
    print("  STOP")


def forward():
    GPIO.output(MOTOR_A1, GPIO.HIGH)
    GPIO.output(MOTOR_A2, GPIO.LOW)
    GPIO.output(MOTOR_B1, GPIO.HIGH)
    GPIO.output(MOTOR_B2, GPIO.LOW)
    print("  FORWARD  — A1=HIGH A2=LOW  B1=HIGH B2=LOW")


def backward():
    GPIO.output(MOTOR_A1, GPIO.LOW)
    GPIO.output(MOTOR_A2, GPIO.HIGH)
    GPIO.output(MOTOR_B1, GPIO.LOW)
    GPIO.output(MOTOR_B2, GPIO.HIGH)
    print("  BACKWARD — A1=LOW  A2=HIGH B1=LOW  B2=HIGH")


def turn_left():
    # Right motor forward, Left motor backward (tank spin)
    GPIO.output(MOTOR_A1, GPIO.HIGH)
    GPIO.output(MOTOR_A2, GPIO.LOW)
    GPIO.output(MOTOR_B1, GPIO.LOW)
    GPIO.output(MOTOR_B2, GPIO.HIGH)
    print("  LEFT     — A1=HIGH A2=LOW  B1=LOW  B2=HIGH")


def turn_right():
    # Left motor forward, Right motor backward (tank spin)
    GPIO.output(MOTOR_A1, GPIO.LOW)
    GPIO.output(MOTOR_A2, GPIO.HIGH)
    GPIO.output(MOTOR_B1, GPIO.HIGH)
    GPIO.output(MOTOR_B2, GPIO.LOW)
    print("  RIGHT    — A1=LOW  A2=HIGH B1=HIGH B2=LOW")


def run_cycle(cycle: int):
    print(f"\n─── Cycle {cycle} ───────────────────────────")
    forward();   time.sleep(STEP_DELAY)
    stop();      time.sleep(PAUSE_DELAY)
    backward();  time.sleep(STEP_DELAY)
    stop();      time.sleep(PAUSE_DELAY)
    turn_left(); time.sleep(STEP_DELAY)
    stop();      time.sleep(PAUSE_DELAY)
    turn_right();time.sleep(STEP_DELAY)
    stop();      time.sleep(2.0)


def main():
    print("=" * 48)
    print("  Direct GPIO Motor Test")
    print("  Ctrl+C to stop at any time")
    print("=" * 48)
    setup()

    cycle = 1
    try:
        while True:
            run_cycle(cycle)
            cycle += 1
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        stop()
        GPIO.cleanup()
        print("GPIO cleaned up.")


if __name__ == "__main__":
    main()
