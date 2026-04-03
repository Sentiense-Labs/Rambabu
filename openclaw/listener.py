#!/usr/bin/env python3
"""
OpenClaw command listener.

Connects to AWS IoT Core MQTT and listens for commands sent from
OpenClaw (WhatsApp, dashboard, or any connected channel).

Every incoming command is:
  1. Logged to openclaw/logs/commands_YYYY-MM-DD.log
  2. Printed to console with status
  3. Executed on the car hardware (motor / steering)

Autonomous mode:
  - AUTONOMOUS_START → launches run_loop in a background thread
  - AUTONOMOUS_STOP  → stops the loop cleanly
  - Any manual command (MOTOR_*, STEER_*) auto-stops autonomous mode

Run:
    cd /home/rambabu/rambabu_rc
    uv run python3 openclaw/listener.py

Stop:
    Ctrl+C
"""

import json
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import RPi.GPIO as GPIO

import config
from server.mqtt.client import MqttClient
from server.mqtt.actions import Action
from lib.motor import MotorController
from lib.pan_tilt_gpiozero import PanTilt
from lib.ultrasonic import Ultrasonic
from lib.camera import Camera
from openclaw.autonomous import run_loop


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


# ── Actions that count as manual override ─────────────────────────────────────

_MANUAL_ACTIONS: frozenset[Action] = frozenset({
    Action.MOTOR_FRONT,
    Action.MOTOR_BACK,
    Action.MOTOR_STOP,
    Action.MOTOR_LEFT,
    Action.MOTOR_RIGHT,
    Action.MOTOR_STEER_LEFT_HOLD,
    Action.MOTOR_STEER_RIGHT_HOLD,
    Action.MOTOR_STEER_CENTER,
    Action.MOTOR_BACK_STEER_LEFT,
    Action.MOTOR_BACK_STEER_RIGHT,
})


# ── Command handler ───────────────────────────────────────────────────────────

class OpenClawHandler:
    """Receives OpenClaw MQTT messages, logs them, and drives the car."""

    def __init__(
        self,
        motor: MotorController,
        pan_tilt: PanTilt,
        ultrasonic: Ultrasonic,
        camera: Camera,
    ):
        self._motor = motor
        self._pan_tilt = pan_tilt
        self._ultrasonic = ultrasonic
        self._camera = camera
        self._count = 0

        # Autonomous mode state
        self._auto_stop_event: threading.Event = threading.Event()
        self._auto_thread: threading.Thread | None = None

    @property
    def is_autonomous_running(self) -> bool:
        return self._auto_thread is not None and self._auto_thread.is_alive()

    def _stop_autonomous(self, reason: str) -> None:
        """Signal the autonomous loop to stop and wait for it to exit."""
        if not self.is_autonomous_running:
            return
        print(f"{YELLOW}  Stopping autonomous mode ({reason}){RESET}")
        self._auto_stop_event.set()
        self._auto_thread.join(timeout=5.0)
        self._auto_thread = None
        self._auto_stop_event.clear()
        print(f"{GREEN}  Autonomous mode stopped{RESET}")

    def _start_autonomous(self) -> dict:
        """Start autonomous loop in a background thread."""
        if self.is_autonomous_running:
            msg = "Autonomous mode already running — ignoring"
            print(f"{YELLOW}  ⚠ {msg}{RESET}")
            return {"status": "ignored", "reason": msg}

        # Ensure camera is running
        if self._camera.get_frame() is None:
            self._camera.start()
            time.sleep(1.0)

        self._auto_stop_event.clear()
        self._auto_thread = threading.Thread(
            target=run_loop,
            kwargs={
                "motor": self._motor,
                "pan_tilt": self._pan_tilt,
                "ultrasonic": self._ultrasonic,
                "camera": self._camera,
                "stop_event": self._auto_stop_event,
            },
            daemon=True,
            name="autonomous-loop",
        )
        self._auto_thread.start()
        print(f"{GREEN}  Autonomous mode started{RESET}")
        return {"status": "ok", "action": "autonomous_start"}

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

        # Manual command overrides autonomous mode
        if action in _MANUAL_ACTIONS and self.is_autonomous_running:
            self._stop_autonomous("manual override")

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
            case Action.AUTONOMOUS_START:
                return self._start_autonomous()
            case Action.AUTONOMOUS_STOP:
                self._stop_autonomous("AUTONOMOUS_STOP command")
                return {"status": "ok", "action": "autonomous_stop"}
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
    pan_tilt = PanTilt()
    ultrasonic = Ultrasonic()
    camera = Camera()

    # Wait for ultrasonic
    ultrasonic.wait_for_reading(timeout=3.0)

    handler = OpenClawHandler(motor, pan_tilt, ultrasonic, camera)

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
        handler._stop_autonomous("shutdown")
        motor.stop()
        pan_tilt.center()
        mqtt.cleanup()
        camera.cleanup()
        pan_tilt.cleanup()
        ultrasonic.cleanup()
        motor.cleanup()
        GPIO.cleanup()
        print(f"{GREEN}✓ Done. Log saved to: {_log_file()}{RESET}")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
