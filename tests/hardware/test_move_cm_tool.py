#!/usr/bin/env python3
"""
Hardware test for the move_cm tool.

Run on Pi with motors connected:
    uv run python tests/hardware/test_move_cm_tool.py forward 50
    uv run python tests/hardware/test_move_cm_tool.py back 30
    uv run python tests/hardware/test_move_cm_tool.py left 40
    uv run python tests/hardware/test_move_cm_tool.py right 40

Or run interactively (prompts for direction and cm each time):
    uv run python tests/hardware/test_move_cm_tool.py
"""

import sys
import threading
import time

from dotenv import load_dotenv

load_dotenv()

import RPi.GPIO as GPIO  # noqa: E402

from lib.motor import MotorController  # noqa: E402
from lib.ultrasonic import Ultrasonic  # noqa: E402
from agno_ai.brain.sonar_guard import SonarGuard  # noqa: E402
from agno_ai.types.context import HardwareContext  # noqa: E402
from agno_ai import set_hw  # noqa: E402
from agno_ai.tools.navigation.move_cm import move_cm  # noqa: E402
import config  # noqa: E402
from agno_ai import constants as C  # noqa: E402

VALID_DIRECTIONS = ("forward", "back", "left", "right", "back_left", "back_right")

_SPEED_MAP = {
    "forward":    C.BASE_SPEED_CM_PER_S,
    "back":       C.REVERSE_SPEED_CM_PER_S,
    "left":       C.TURN_LEFT_SPEED_CM_PER_S,
    "right":      C.TURN_RIGHT_SPEED_CM_PER_S,
    "back_left":  C.TURN_BACK_SPEED_CM_PER_S,
    "back_right": C.TURN_BACK_SPEED_CM_PER_S,
}


def setup_hardware() -> HardwareContext:
    GPIO.setmode(GPIO.BCM)
    motor = MotorController()
    ultrasonic = Ultrasonic()
    rear_ultrasonic = Ultrasonic(
        trig_pin=config.ULTRASONIC_REAR_TRIG,
        echo_pin=config.ULTRASONIC_REAR_ECHO,
        detection_distance=config.REAR_OBSTACLE_DETECTION_DISTANCE,
    )
    sonar_guard = SonarGuard(ultrasonic=ultrasonic, motor=motor)
    sonar_guard.start()

    hw = HardwareContext(
        motor=motor,
        ultrasonic=ultrasonic,
        rear_ultrasonic=rear_ultrasonic,
        sonar_guard=sonar_guard,
    )
    set_hw(hw)

    # Wait for sonar to warm up
    print("Waiting for sonar warmup (1s)...")
    time.sleep(1.0)
    dist, zone = sonar_guard.snapshot()
    print(f"Front sonar ready: {dist:.0f} cm ({zone})")
    rear_dist = rear_ultrasonic.get_distance()
    print(f"Rear sonar ready:  {rear_dist:.0f} cm")
    return hw


_BACKWARD_DIRS = frozenset({"back", "back_left", "back_right"})


def run_once(direction: str, cm: float, hw: HardwareContext) -> None:
    speed = _SPEED_MAP[direction]
    expected_s = cm / speed + C.MOTOR_STARTUP_OFFSET_S
    print(f"\n→ move_cm({direction!r}, {cm})")
    print(f"  speed={speed:.0f} cm/s  startup={C.MOTOR_STARTUP_OFFSET_S}s  expected_duration={expected_s:.2f}s")

    use_rear = direction in _BACKWARD_DIRS and hw.rear_ultrasonic is not None
    sensor_label = "rear" if use_rear else "front"

    poll_log: list[tuple[float, float]] = []
    stop_poll = threading.Event()

    def _poll() -> None:
        t0 = time.monotonic()
        while not stop_poll.is_set():
            dist = hw.rear_ultrasonic.get_distance() if use_rear else hw.ultrasonic.get_distance()
            elapsed = time.monotonic() - t0
            poll_log.append((elapsed, dist))
            time.sleep(0.05)  # 20 Hz polling

    poller = threading.Thread(target=_poll, daemon=True)
    poller.start()

    result = move_cm(direction=direction, cm=cm)

    stop_poll.set()
    poller.join(timeout=0.2)

    print(f"  result: {result}")
    print(f"  {sensor_label} sonar profile (t=0 is move start):")
    for t, d in poll_log:
        bar = "█" * int(d / 5)
        print(f"    {t:5.2f}s  {d:6.1f} cm  {bar}")
    if len(poll_log) >= 2:
        start_d = poll_log[0][1]
        end_d = poll_log[-1][1]
        # For rear sensor, distance decreases as rover approaches wall behind it
        traveled = (start_d - end_d) if use_rear else (start_d - end_d)
        direction_sign = "↓ wall approaching" if use_rear else "↑ gap closing"
        elapsed = poll_log[-1][0] - poll_log[0][0]
        cruise = max(0.01, elapsed - C.MOTOR_STARTUP_OFFSET_S)
        implied_speed = abs(traveled) / cruise if abs(traveled) > 0.5 else 0
        print(f"  {sensor_label} sonar Δ={traveled:.1f} cm ({direction_sign}) in {elapsed:.2f}s")
        if implied_speed > 0:
            print(f"  implied cruise speed={implied_speed:.1f} cm/s")


def main() -> None:
    args = sys.argv[1:]
    hw = setup_hardware()

    try:
        if len(args) >= 2:
            direction = args[0].lower()
            try:
                cm = float(args[1])
            except ValueError:
                print(f"Error: cm must be a number, got {args[1]!r}")
                sys.exit(1)
            if direction not in VALID_DIRECTIONS:
                print(f"Error: direction must be one of {VALID_DIRECTIONS}")
                sys.exit(1)
            run_once(direction, cm, hw)
        else:
            # Interactive loop
            print(f"\nValid directions: {', '.join(VALID_DIRECTIONS)}")
            print("Type 'q' to quit.\n")
            while True:
                try:
                    raw = input("direction cm > ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nDone.")
                    break
                if raw.lower() in ("q", "quit", "exit"):
                    break
                parts = raw.split()
                if len(parts) != 2:
                    print("  Usage: <direction> <cm>  e.g. forward 50")
                    continue
                direction, cm_str = parts
                try:
                    cm = float(cm_str)
                except ValueError:
                    print(f"  cm must be a number, got {cm_str!r}")
                    continue
                if direction not in VALID_DIRECTIONS:
                    print(f"  direction must be one of {VALID_DIRECTIONS}")
                    continue
                run_once(direction, cm, hw)
    finally:
        if hw.motor:
            hw.motor.stop()
        GPIO.cleanup()
        print("GPIO cleaned up.")


if __name__ == "__main__":
    main()
