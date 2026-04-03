#!/usr/bin/env python3
"""
OpenClaw autonomous driving loop.

Uses the ultrasonic sensor for obstacle detection and Gemini vision
for navigation decisions when an obstacle is encountered.

Loop:
  1. Drive forward at speed 60
  2. Poll ultrasonic every 50ms — when obstacle <= 50cm:
  3. Stop the car
  4. Look left (capture frame), look right (capture frame)
  5. Send both frames to Gemini: "which side has more open space?"
  6. Gemini picks steer_left_hold or steer_right_hold
  7. Execute steer, drive forward 1.5s, center steering
  8. Repeat

Run:
    cd /home/rambabu/rambabu_rc
    uv run python3 openclaw/autonomous.py
"""

import base64
import io
import json
import os
import signal
import sys
import time

import cv2
import httpx
import numpy as np
import RPi.GPIO as GPIO

import config
from lib.motor import MotorController
from lib.pan_tilt_gpiozero import PanTilt
from lib.ultrasonic import Ultrasonic
from lib.camera import Camera
from openclaw.tools import execute

# ── Gemini config ─────────────────────────────────────────────────────────────

_GEMINI_API_KEY = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")
_GEMINI_MODEL = "gemini-2.0-flash"
_GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}"
    f":generateContent?key={_GEMINI_API_KEY}"
)

# ── Driving constants ─────────────────────────────────────────────────────────

_DRIVE_SPEED = 60
_LOOK_PAN_DEG = 45          # Degrees to pan left/right from center
_LOOK_SETTLE_SEC = 0.3      # Wait for servo + camera to settle
_AVOIDANCE_DRIVE_SEC = 1.5  # Seconds to drive while steering around obstacle
_POLL_INTERVAL_SEC = 0.05   # 50ms ultrasonic poll

# ── Console colours ──────────────────────────────────────────────────────────

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


# ── Gemini vision ─────────────────────────────────────────────────────────────

def _frame_to_base64(frame: np.ndarray) -> str:
    """Encode an RGB numpy frame to base64 JPEG."""
    bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        return ""
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def ask_gemini_direction(left_frame: np.ndarray, right_frame: np.ndarray) -> str:
    """Send left and right frames to Gemini, return 'steer_left_hold' or 'steer_right_hold'.

    Falls back to 'steer_right_hold' if Gemini is unreachable or returns
    an unparseable response.
    """
    left_b64 = _frame_to_base64(left_frame)
    right_b64 = _frame_to_base64(right_frame)

    if not left_b64 or not right_b64:
        print(f"{YELLOW}  Frame encoding failed — defaulting right{RESET}")
        return "steer_right_hold"

    if not _GEMINI_API_KEY:
        print(f"{YELLOW}  No GOOGLE_GENERATIVE_AI_API_KEY — defaulting right{RESET}")
        return "steer_right_hold"

    prompt = (
        "You are Ramu's navigation brain. The RC car hit an obstacle. "
        "Image 1 is the LEFT view. Image 2 is the RIGHT view. "
        "Which side has more open space to drive through safely? "
        "Respond with ONLY one word: LEFT or RIGHT. Nothing else."
    )

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": left_b64,
                        }
                    },
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": right_b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 10,
        },
    }

    try:
        resp = httpx.post(_GEMINI_URL, json=body, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()

        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
            .upper()
        )

        print(f"{CYAN}  Gemini says: {text}{RESET}")

        if "LEFT" in text:
            return "steer_left_hold"
        return "steer_right_hold"

    except httpx.TimeoutException:
        print(f"{YELLOW}  Gemini timeout — defaulting right{RESET}")
        return "steer_right_hold"
    except Exception as e:
        print(f"{YELLOW}  Gemini error: {e} — defaulting right{RESET}")
        return "steer_right_hold"


# ── Capture helper ────────────────────────────────────────────────────────────

def capture_frame(camera: Camera) -> np.ndarray | None:
    """Wait briefly for a fresh frame and return it."""
    time.sleep(_LOOK_SETTLE_SEC)
    return camera.get_frame()


# ── Autonomous loop ───────────────────────────────────────────────────────────

def run_loop(
    motor: MotorController,
    pan_tilt: PanTilt,
    ultrasonic: Ultrasonic,
    camera: Camera,
    stop_event: "threading.Event | None" = None,
) -> None:
    """Main autonomous driving loop.

    Args:
        stop_event: If provided, the loop exits cleanly when this event is set.
                    Used when run_loop is launched from the listener in a thread.
    """
    import threading

    if stop_event is None:
        stop_event = threading.Event()

    def _stopped() -> bool:
        return stop_event.is_set()

    print(f"\n{BOLD}{'=' * 55}{RESET}")
    print(f"{BOLD}  OpenClaw Autonomous Mode{RESET}")
    print(f"{'=' * 55}")
    print(f"  Speed          : {_DRIVE_SPEED}%")
    print(f"  Stop distance  : {config.OBSTACLE_DETECTION_DISTANCE}cm")
    print(f"  Look angle     : ±{_LOOK_PAN_DEG}°")
    print(f"  Gemini model   : {_GEMINI_MODEL}")
    print(f"{'=' * 55}\n")

    cycle = 0

    while not _stopped():
        cycle += 1
        print(f"\n{BOLD}── Cycle {cycle} ──{RESET}")

        # Step 1: Drive forward
        print(f"{GREEN}  → Driving forward at {_DRIVE_SPEED}%{RESET}")
        result = execute("motor_forward", {"speed": _DRIVE_SPEED}, motor=motor)
        if result.get("error_code") == "OBSTACLE_DETECTED":
            print(f"{RED}  Obstacle already detected — skipping to avoidance{RESET}")
        else:
            # Step 2: Poll ultrasonic until obstacle or stop
            while not _stopped():
                distance = ultrasonic.get_distance()
                if ultrasonic.is_obstacle_confirmed():
                    print(
                        f"{RED}  !! Obstacle confirmed at {distance:.1f}cm{RESET}"
                    )
                    break
                time.sleep(_POLL_INTERVAL_SEC)

        if _stopped():
            break

        # Step 3: Stop
        execute("motor_stop", {}, motor=motor)
        print(f"{YELLOW}  → Stopped{RESET}")
        time.sleep(0.2)

        if _stopped():
            break

        # Step 4: Look left
        print(f"{CYAN}  → Looking left ({_LOOK_PAN_DEG}°)...{RESET}")
        execute("camera_pan_left", {"degrees": _LOOK_PAN_DEG}, pan_tilt=pan_tilt)
        left_frame = capture_frame(camera)

        # Step 5: Look right (pan from left to right = 2x angle)
        print(f"{CYAN}  → Looking right ({_LOOK_PAN_DEG}°)...{RESET}")
        execute(
            "camera_pan_right",
            {"degrees": _LOOK_PAN_DEG * 2},
            pan_tilt=pan_tilt,
        )
        right_frame = capture_frame(camera)

        # Step 6: Center camera
        execute("camera_center", {}, pan_tilt=pan_tilt)

        if _stopped():
            break

        # Step 7: Ask Gemini
        if left_frame is None or right_frame is None:
            print(f"{YELLOW}  Camera frame missing — defaulting right{RESET}")
            steer_tool = "steer_right_hold"
        else:
            print(f"{CYAN}  → Asking Gemini for direction...{RESET}")
            steer_tool = ask_gemini_direction(left_frame, right_frame)

        if _stopped():
            break

        # Step 8 & 9: Steer
        direction_label = "LEFT" if "left" in steer_tool else "RIGHT"
        print(f"{GREEN}  → Steering {direction_label}{RESET}")
        execute(steer_tool, {}, motor=motor)

        # Step 10: Drive forward while steering for 1.5s
        print(f"{GREEN}  → Driving around obstacle for {_AVOIDANCE_DRIVE_SEC}s{RESET}")
        execute("motor_forward", {"speed": _DRIVE_SPEED}, motor=motor)
        stop_event.wait(timeout=_AVOIDANCE_DRIVE_SEC)

        # Step 11: Center steering
        execute("steer_center", {}, motor=motor)
        execute("motor_stop", {}, motor=motor)
        print(f"{GREEN}  → Steering centered, ready for next cycle{RESET}")
        time.sleep(0.3)

    # Clean exit
    execute("motor_stop", {}, motor=motor)
    execute("steer_center", {}, motor=motor)
    execute("camera_center", {}, pan_tilt=pan_tilt)
    print(f"{YELLOW}  Autonomous loop stopped{RESET}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not _GEMINI_API_KEY:
        print(f"{RED}Set GOOGLE_GENERATIVE_AI_API_KEY in .env or environment{RESET}")
        sys.exit(1)

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)

    motor = MotorController()
    pan_tilt = PanTilt()
    ultrasonic = Ultrasonic()
    camera = Camera()

    # Wait for ultrasonic to get a valid reading
    ultrasonic.wait_for_reading(timeout=3.0)

    # Start camera
    cam_result = camera.start()
    if cam_result.get("status") != "ok":
        print(f"{RED}Camera failed: {cam_result}{RESET}")
        motor.cleanup()
        GPIO.cleanup()
        sys.exit(1)

    # Wait for first camera frame
    time.sleep(1.0)

    def shutdown(sig, frame):
        print(f"\n{CYAN}→ Shutting down...{RESET}")
        motor.stop()
        pan_tilt.center()
        camera.cleanup()
        pan_tilt.cleanup()
        ultrasonic.cleanup()
        motor.cleanup()
        GPIO.cleanup()
        print(f"{GREEN}✓ Done{RESET}")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)

    try:
        # Load .env if dotenv is available
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        run_loop(motor, pan_tilt, ultrasonic, camera)
    except Exception as e:
        print(f"{RED}Fatal error: {e}{RESET}")
        motor.stop()
        camera.cleanup()
        pan_tilt.cleanup()
        ultrasonic.cleanup()
        motor.cleanup()
        GPIO.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    # Load .env before anything reads the API key
    try:
        from dotenv import load_dotenv
        load_dotenv()
        # Re-read after dotenv loads
        import openclaw.autonomous as _self
        _self._GEMINI_API_KEY = os.environ.get("GOOGLE_GENERATIVE_AI_API_KEY", "")
        _self._GEMINI_URL = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}"
            f":generateContent?key={_self._GEMINI_API_KEY}"
        )
    except ImportError:
        pass

    main()
