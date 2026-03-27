#!/usr/bin/env python3
"""
OpenClaw command listener.

Connects to AWS IoT Core MQTT and listens for commands sent from
OpenClaw (WhatsApp, dashboard, or any connected channel).

Every incoming command is:
  1. Logged to openclaw/logs/commands_YYYY-MM-DD.log
  2. Printed to console with status
  3. Executed on the car hardware (motor / steering)

Run:
    cd /home/rambabu/rambabu_rc
    uv run python3 openclaw/listener.py

Stop:
    Ctrl+C
"""

import json
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import RPi.GPIO as GPIO

import config
from server.mqtt.client import MqttClient
from server.mqtt.actions import Action
from lib.motor import MotorController


# ── Log file ─────────────────────────────────────────────────────────────────

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _log_file() -> Path:
    """Returns today's log file path."""
    return LOG_DIR / f"commands_{datetime.now().strftime('%Y-%m-%d')}.log"


def _write_log(entry: dict) -> None:
    """Append a JSON line to today's log file."""
    line = json.dumps(entry, default=str) + "\n"
    with _log_file().open("a") as f:
        f.write(line)


# ── Console colours ──────────────────────────────────────────────────────────

GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


# ── Command handler ───────────────────────────────────────────────────────────

class OpenClawHandler:
    """Receives OpenClaw MQTT messages, logs them, and drives the car."""

    def __init__(self, motor: MotorController):
        self._motor = motor
        self._count = 0

    def handle(self, topic: str, payload: dict) -> None:
        self._count += 1
        ts = datetime.now().isoformat(timespec="milliseconds")

        # Unwrap IoT platform envelope {"data": {...}}
        data = payload.get("data", payload)
        raw_action = data.get("action", "") or data.get("servoactions", "")
        speed = data.get("speed")

        # Log entry
        log_entry = {
            "timestamp": ts,
            "count": self._count,
            "topic": topic,
            "raw_action": raw_action,
            "speed": speed,
            "payload": payload,
            "status": None,
            "result": None,
        }

        print(f"\n{'─' * 55}")
        print(f"{BOLD}[{ts}]  #{self._count}  from OpenClaw{RESET}")
        print(f"  Topic  : {topic}")
        print(f"  Action : {raw_action!r}  speed={speed}")

        if not raw_action:
            msg = "No 'action' field in payload — ignored"
            print(f"{YELLOW}  ⚠ {msg}{RESET}")
            log_entry["status"] = "ignored"
            log_entry["result"] = msg
            _write_log(log_entry)
            return

        # Validate
        try:
            action = Action(raw_action)
        except ValueError:
            msg = f"Unknown action '{raw_action}'"
            print(f"{RED}  ✗ {msg}{RESET}")
            print(f"  Valid: {[a.value for a in Action]}")
            log_entry["status"] = "unknown"
            log_entry["result"] = msg
            _write_log(log_entry)
            return

        # Execute
        result = self._execute(action, speed)
        print(f"{GREEN}  ✓ Executed: {action}  →  {result}{RESET}")

        log_entry["status"] = "executed"
        log_entry["result"] = result
        _write_log(log_entry)

    def _execute(self, action: Action, speed) -> dict:
        m = self._motor
        match action:
            case Action.MOTOR_FRONT:
                return m.front(speed) if speed else m.front()
            case Action.MOTOR_BACK:
                return m.back(speed) if speed else m.back()
            case Action.MOTOR_STOP:
                return m.stop()
            case Action.MOTOR_LEFT:
                return m.left()
            case Action.MOTOR_RIGHT:
                return m.right()
            case Action.MOTOR_STEER_LEFT_HOLD:
                return m.steer_left_hold()
            case Action.MOTOR_STEER_RIGHT_HOLD:
                return m.steer_right_hold()
            case Action.MOTOR_STEER_CENTER:
                return m.steer_center()
            case Action.MOTOR_BACK_STEER_LEFT:
                m.steer_left_hold()
                return m.back(speed) if speed else m.back()
            case Action.MOTOR_BACK_STEER_RIGHT:
                m.steer_right_hold()
                return m.back(speed) if speed else m.back()
            case _:
                return {"status": "skipped", "reason": f"no hardware handler for {action}"}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{'=' * 55}{RESET}")
    print(f"{BOLD}  OpenClaw → Car  Listener{RESET}")
    print(f"{'=' * 55}")
    print(f"  Endpoint : {config.AWS_IOT_ENDPOINT}")
    print(f"  Topic    : {config.MQTT_COMMANDS_TOPIC}")
    print(f"  Log dir  : {LOG_DIR.resolve()}")
    print(f"{'=' * 55}\n")

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    motor = MotorController()
    handler = OpenClawHandler(motor)

    mqtt = MqttClient()
    mqtt.set_command_callback(handler.handle)

    print(f"{CYAN}→ Connecting to AWS IoT Core ...{RESET}")
    result = mqtt.connect()
    if result["status"] != "ok":
        print(f"{RED}✗ MQTT connect failed: {result}{RESET}")
        motor.cleanup()
        GPIO.cleanup()
        sys.exit(1)

    # Wait up to 5 s for connection
    for _ in range(10):
        if mqtt.is_connected:
            break
        time.sleep(0.5)

    if not mqtt.is_connected:
        print(f"{RED}✗ Did not connect within 5 seconds{RESET}")
        motor.cleanup()
        GPIO.cleanup()
        sys.exit(1)

    print(f"{GREEN}✓ Connected{RESET}")
    print(f"{GREEN}✓ Listening on: {config.MQTT_COMMANDS_TOPIC}{RESET}")
    print(f"\n{YELLOW}Send commands from OpenClaw (WhatsApp / dashboard).{RESET}")
    print(f"{YELLOW}All commands are logged to: {_log_file()}{RESET}")
    print("Press Ctrl+C to stop.\n")

    def shutdown(sig, frame):
        print(f"\n{CYAN}→ Shutting down ...{RESET}")
        motor.stop()
        mqtt.cleanup()
        motor.cleanup()
        GPIO.cleanup()
        print(f"{GREEN}✓ Done. Log saved to: {_log_file()}{RESET}")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
